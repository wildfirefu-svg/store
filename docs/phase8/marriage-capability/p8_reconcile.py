"""Phase 8 阶段间对账脚本（Task 1 首项：亚型 35 题对账；后续任务增量扩展）。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md（v1.3.1，§4）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md（v3.2，Task 1.3）
用法：python docs/phase8/marriage-capability/p8_reconcile.py（全过 exit 0，任一失败 exit 1）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8_DIR = REPO / "docs" / "phase8" / "marriage-capability"
CLASSIFICATION = (
    REPO / "docs" / "phase7" / "error-analysis" / "error_classification.jsonl"
)


def subtype_check() -> list[tuple[str, bool, str]]:
    rows = [json.loads(l) for l in CLASSIFICATION.open(encoding="utf-8") if l.strip()]
    expected = sorted(
        r["case_id"]
        for r in rows
        if r.get("category") == "婚姻" and r.get("error_type") == "knowledge"
    )
    split = json.loads((P8_DIR / "subtype_split.json").read_text(encoding="utf-8"))
    actual = [c["case_id"] for c in split["cases"]]
    enum = split["subtype_enum"]
    summary = split["summary"]
    results: list[tuple[str, bool, str]] = [
        (
            "case_id 集合与输入一致（35 题）",
            actual == expected,
            f"{len(actual)} vs {len(expected)}",
        ),
        (
            "主亚型之和 = 35 = 题目数",
            summary["total"] == 35 and sum(summary["by_primary_subtype"].values()) == 35,
            json.dumps(summary, ensure_ascii=False),
        ),
        (
            "主/副亚型均在冻结枚举内",
            all(c["primary_subtype"] in enum for c in split["cases"])
            and all(
                st in enum
                for c in split["cases"]
                for st in c.get("secondary_subtypes") or []
            ),
            f"enum={enum}",
        ),
        (
            "归并题有 merge_reason，非归并题为 null",
            all((c.get("merged_from") is None) == (c.get("merge_reason") is None) for c in split["cases"]),
            "",
        ),
    ]
    return results


def probe_check() -> list[tuple[str, bool, str]]:
    """探针 item_id 集 == required_knowledge computation 项集（P8-1.5 对账）。"""
    rows = [
        json.loads(l)
        for l in (P8_DIR / "required_knowledge.jsonl").open(encoding="utf-8")
        if l.strip()
    ]
    expected = {
        item["item_id"]
        for row in rows
        for item in row["items"]
        if item["item_type"] == "computation"
    }
    probe = json.loads((P8_DIR / "computability_probe.json").read_text(encoding="utf-8"))
    actual = {i["item_id"] for i in probe["items"]}
    results: list[tuple[str, bool, str]] = [
        ("探针 item_id 集 == computation 项集", actual == expected, f"{len(actual)} vs {len(expected)}"),
        (
            "四态值域合法且总量一致",
            all(
                i["computability_status"] in {"computable", "missing_input", "no_interface", "semantic_gap"}
                for i in probe["items"]
            )
            and probe["summary"]["total"] == len(actual),
            json.dumps(probe["summary"], ensure_ascii=False),
        ),
    ]
    return results


CHECKS: dict[str, list[tuple[str, bool, str]]] = {
    "subtype_split": subtype_check(),
    "computability_probe": probe_check(),
}


def main() -> None:
    all_ok = True
    for section, results in CHECKS.items():
        print(f"[{section}]")
        for name, ok, detail in results:
            flag = "ok" if ok else "FAIL"
            all_ok = all_ok and ok
            print(f"  {flag}  {name}" + (f"  ({detail})" if detail else ""))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
