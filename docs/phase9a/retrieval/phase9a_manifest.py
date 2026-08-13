"""Phase 9A 专用 manifest helper：逻辑名称为键、真 append-only、单向 stage 状态机。
复用 p8_freeze 四策略 SHA 函数；原子写（tmp → 校验 → os.replace）。
路径统一以仓库根相对路径保存，由 __file__ 推导的 REPO_ROOT 解析（任意 cwd/worktree 可执行）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import p8_freeze  # docs/phase8/marriage-capability（sys.path 由调用方注入）

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
STRATEGY_FN = {
    "json_canonical": p8_freeze.json_canonical_sha256,
    "jsonl_canonical": p8_freeze.jsonl_canonical_sha256,
    "raw_bytes": p8_freeze.raw_sha256,
    "git_canonical_lf": p8_freeze.git_canonical_lf_sha256,
}
STAGES = ("config_frozen", "code_frozen", "sealed")
STAGE_ORDER = {None: 0, "config_frozen": 1, "code_frozen": 2, "sealed": 3}
EXPECTED_NEXT = {None: "config_frozen", "config_frozen": "code_frozen", "code_frozen": "sealed"}  # P0：相邻阶段校验，禁跳级


def _load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": "1.0", "stage": None, "entries": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    json.loads(tmp.read_text(encoding="utf-8"))  # 写后校验
    os.replace(tmp, path)


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO_ROOT).as_posix()  # 统一正斜杠，跨平台可移植
    except ValueError:
        return str(p)  # 目录外路径（如 tmp 镜像）原样保存


def _abs(rel: str) -> Path:
    p = Path(rel.replace("\\", "/"))  # 归一已 committed 的反斜杠路径，避免重写 SHA
    return p if p.is_absolute() else REPO_ROOT / p


def freeze(manifest_path: Path, entries: dict[str, tuple[Path, str]]) -> dict:
    """append-only 冻结：同名已存在且 SHA 不一致 → fail-closed；一致 → 幂等跳过。
    sealed 后拒绝任何新增（幂等核验除外，P0 修订：封存不可变）。"""
    manifest = _load(manifest_path)
    if manifest["stage"] == "sealed":
        # 幂等核验：全部条目 SHA 与磁盘一致才允许（不写盘）；否则 fail-closed
        for name, (p, strategy) in entries.items():
            existing = manifest["entries"].get(name)
            if existing is None or existing["sha256"] != STRATEGY_FN[strategy](p):
                sys.exit(f"FAIL: manifest sealed; cannot modify entry {name}")
        return manifest
    for name, (p, strategy) in entries.items():
        sha = STRATEGY_FN[strategy](p)
        existing = manifest["entries"].get(name)
        if existing is not None and existing["sha256"] != sha:
            sys.exit(f"FAIL: {name} already frozen with different SHA (append-only violated)")
        manifest["entries"][name] = {"path": _rel(p), "strategy": strategy, "sha256": sha}
    _atomic_write(manifest_path, manifest)
    return manifest


def set_stage(manifest_path: Path, stage: str) -> None:
    """相邻单向状态机（P0 修订）：仅允许 None→config_frozen→code_frozen→sealed 逐级迁移，禁跳级/回退。"""
    if stage not in STAGES:
        sys.exit(f"FAIL: unknown stage {stage}")
    manifest = _load(manifest_path)
    current = manifest["stage"]
    if EXPECTED_NEXT.get(current) != stage:
        sys.exit(f"FAIL: stage transition {current} -> {stage} forbidden (expected next: {EXPECTED_NEXT.get(current)})")
    manifest["stage"] = stage
    _atomic_write(manifest_path, manifest)


def verify_frozen(manifest_path: Path, names: list[str], required_stage: str | None = "code_frozen") -> None:
    """生产者首次执行前预检：依赖已冻结、磁盘 SHA == expected、且 manifest 已达 required_stage，
    否则 fail-closed（中优：防条目存在但状态仍停在 config_frozen 时执行）。"""
    manifest = _load(manifest_path)
    if required_stage is not None and manifest["stage"] != required_stage:
        sys.exit(f"FAIL: manifest stage {manifest['stage']} != required {required_stage}")
    for name in names:
        entry = manifest["entries"].get(name)
        if entry is None:
            sys.exit(f"FAIL: {name} not frozen before use")
        if STRATEGY_FN[entry["strategy"]](_abs(entry["path"])) != entry["sha256"]:
            sys.exit(f"FAIL: {name} SHA drift before use")
