"""Phase 8 冻结 manifest 原子更新 helper（全阶段公共基础设施）。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md（v1.3.1，§6）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md（v3.2，Task 1.3）

- `atomic_add(manifest_path, sha_entries)`：写同目录 tmp → 校验 JSON 可解析 → os.replace；
  写中断/替换失败时原 manifest 保持可解析、无半写状态。
- SHA 四策略：json_canonical / jsonl_canonical / raw_bytes / git_canonical_lf。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

STRATEGIES = ("json_canonical", "jsonl_canonical", "raw_bytes", "git_canonical_lf")
REQUIRED_KEYS = ("path", "sha256", "strategy")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STRATEGY_NOTES = {
    "json_canonical": 'sort_keys=True, ensure_ascii=False, separators=(",", ":") + 末尾 \\n',
    "jsonl_canonical": "逐行 canonical JSON、冻结行序、每行及文件末尾均 \\n",
    "raw_bytes": "文件原始字节 SHA-256",
    "git_canonical_lf": "CRLF→LF 归一化后 SHA-256（git canonical LF 文本复算口径）",
}


def json_canonical_sha256(path: Path) -> str:
    obj = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def jsonl_canonical_sha256(path: Path) -> str:
    lines = [
        l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    canonical = "".join(
        json.dumps(json.loads(l), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
        for l in lines
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_canonical_lf_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def atomic_add(manifest_path: Path, sha_entries: list[dict]) -> dict:
    """原子合并写入 sha_entries（按 path 去重置换）。失败时原 manifest 不受影响。"""
    for entry in sha_entries:
        if not isinstance(entry, dict) or any(k not in entry for k in REQUIRED_KEYS):
            raise ValueError(f"invalid sha entry (need {REQUIRED_KEYS}): {entry!r}")
        if entry["strategy"] not in STRATEGIES:
            raise ValueError(f"unknown strategy {entry['strategy']!r}")
        if not _SHA256_RE.fullmatch(entry["sha256"]):
            raise ValueError(f"invalid sha256 hex {entry['sha256']!r} in {entry['path']!r}")

    entries: dict[str, dict] = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"manifest corrupted, refusing to overwrite: {manifest_path}: {exc}") from exc
        entries = {e["path"]: e for e in existing["entries"]}
    for entry in sha_entries:
        entries[entry["path"]] = entry

    payload = {
        "schema_version": "1.0",
        "sha_strategies": STRATEGY_NOTES,
        "entries": sorted(entries.values(), key=lambda e: e["path"]),
    }
    tmp = manifest_path.with_name(manifest_path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    json.loads(tmp.read_text(encoding="utf-8"))  # 写后校验：不可解析即中断，不替换
    os.replace(tmp, manifest_path)
    return payload
