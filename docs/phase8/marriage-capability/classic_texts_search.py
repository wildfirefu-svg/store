"""classic_texts 检索（Phase 8 P8-2B，匹配语义冻结 v3.1）。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md v1.3.1（§P8-2B）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md v3.2（Task 5.1）

匹配语义（冻结）：
- 搜索字段：主要正文 rule、original_text；辅助检索 subject、condition、category；
  不检索 id、source_book、source_chapter、quarantine_reason。
- 同义词组内 OR、不同词组间 AND；子串匹配（去空白后）。
- 结果排序 = 文件序 + 行序（稳定序）；去重 = 同一 (file, line) 只记一次。
- quarantine 文件命中必须标 quarantined=true（只作佐证，不作"已有可靠知识"证据）。
- 启动时文件 schema ≠ 允许 schema 即 fail-closed（SystemExit），禁止静默跳过未知字段。
- 读取 git object 冻结版（classic_texts_freeze.json 的 commit + blob SHA）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8_DIR = REPO / "docs" / "phase8" / "marriage-capability"

PRIMARY_FIELDS = ["rule", "original_text"]
AUX_FIELDS = ["subject", "condition", "category"]
SEARCH_FIELDS = PRIMARY_FIELDS + AUX_FIELDS
ALLOWED_FIELDS = set(SEARCH_FIELDS) | {"id", "source_book", "source_chapter", "quarantine_reason"}
REQUIRED_FIELDS = {"id", "rule", "original_text", "subject", "condition", "category"}


def _norm(text: str) -> str:
    """去空白（空格/制表/换行）；繁简不转换、大小写不转换。"""
    return "".join(str(text or "").split())


def _check_schema(record: dict, path: Path) -> None:
    keys = set(record)
    unknown = keys - ALLOWED_FIELDS
    missing = REQUIRED_FIELDS - keys
    if unknown:
        sys.exit(f"schema fail-closed: {path} 含未知字段 {sorted(unknown)}")
    if missing:
        sys.exit(f"schema fail-closed: {path} 缺必需字段 {sorted(missing)}")


def search_file(path: Path, groups: list[list[str]], quarantined: bool = False) -> list[dict]:
    """对单个冻结文件做组间 AND / 组内 OR 子串检索。返回命中记录（稳定序）。"""
    if path.suffix == ".jsonl":
        records = [
            json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
    else:
        records = json.loads(path.read_text(encoding="utf-8"))
    hits = []
    for idx, record in enumerate(records):
        _check_schema(record, path)
        matched_fields: set[str] = set()
        all_groups_hit = True
        for group in groups:
            group_hit = False
            for term in group:
                needle = _norm(term)
                for field in SEARCH_FIELDS:
                    if needle and needle in _norm(record.get(field)):
                        group_hit = True
                        matched_fields.add(field)
            if not group_hit:
                all_groups_hit = False
                break
        if all_groups_hit:
            hits.append(
                {
                    "record_id": record["id"],
                    "file": path.name,
                    "line": idx + 1,
                    "json_pointer": f"/{idx}",
                    "matched_fields": sorted(matched_fields),
                    "excerpt": _norm(record.get("rule"))[:80],
                    "quarantined": quarantined,
                }
            )
    return hits


def _git_show(commit: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{commit}:{path}"],
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.exit(f"git show {commit}:{path} failed: {proc.stderr.decode('utf-8', 'replace')}")
    return proc.stdout


def search_frozen(groups: list[list[str]], freeze_path: Path, out_path: Path | None = None) -> dict:
    """按 classic_texts_freeze.json 的冻结 commit 逐文件检索（git object，不读工作区）。

    out_path 为 None 时只返回结果不落盘（供逐项核查复用）。
    """
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    results = []
    tmp_dir = P8_DIR / ".classic_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for f in freeze["files"]:
        raw = _git_show(f["commit"], f["path"])
        tmp = tmp_dir / f["path"].split("/")[-1]
        tmp.write_bytes(raw)
        quarantined = "quarantine" in f["path"]
        hits = search_file(tmp, groups, quarantined=quarantined)
        for h in hits:
            h["file"] = f["path"]
        results.extend(hits)
        tmp.unlink()
    tmp_dir.rmdir()  # 清理空临时目录，避免运行残留
    # 去重：同一 (file, line) 只记一次；排序 = 文件序 + 行序
    seen: set[tuple[str, int]] = set()
    deduped = []
    for h in results:
        key = (h["file"], h["line"])
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    payload = {
        "schema_version": "1.0",
        "search_fields": SEARCH_FIELDS,
        "primary_fields": PRIMARY_FIELDS,
        "aux_fields": AUX_FIELDS,
        "normalization": "去空白；繁简不转换；大小写不转换",
        "groups": groups,
        "frozen_commit": freeze["frozen_commit"],
        "results": deduped,
        "summary": {"total_hits": len(deduped), "quarantined_hits": sum(1 for h in deduped if h["quarantined"])},
    }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return payload


def main() -> None:
    # 婚姻类检索词组（冻结）：婚配/婚姻/夫妻/配偶/姻缘/桃花/红鸾 组内 OR，组间 AND
    groups = [["婚配", "婚姻", "夫妻", "配偶", "姻缘", "桃花", "红鸾"]]
    search_frozen(
        groups,
        P8_DIR / "classic_texts_freeze.json",
        P8_DIR / "classic_texts_search_results.json",
    )
    print(f"classic_texts search written to {P8_DIR / 'classic_texts_search_results.json'}")


if __name__ == "__main__":
    main()
