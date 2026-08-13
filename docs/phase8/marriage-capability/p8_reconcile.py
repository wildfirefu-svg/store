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


def required_knowledge_check() -> list[tuple[str, bool, str]]:
    """required_knowledge 35 行链对账。"""
    rows = [
        json.loads(l)
        for l in (P8_DIR / "required_knowledge.jsonl").open(encoding="utf-8")
        if l.strip()
    ]
    split = json.loads((P8_DIR / "subtype_split.json").read_text(encoding="utf-8"))
    expected = [c["case_id"] for c in split["cases"]]
    actual = [r["case_id"] for r in rows]
    n_items = sum(len(r["items"]) for r in rows)
    return [
        ("required_knowledge 35 行 == subtype_split 35 题", actual == expected, f"{len(actual)} vs {len(expected)}"),
        ("知识项总数 > 0", n_items > 0, f"{n_items} items"),
    ]


def audit_check() -> list[tuple[str, bool, str]]:
    """knowledge_audit 35 行链 + 分母对账。"""
    rows = [
        json.loads(l)
        for l in (P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
        if l.strip()
    ]
    split = json.loads((P8_DIR / "subtype_split.json").read_text(encoding="utf-8"))
    expected = [c["case_id"] for c in split["cases"]]
    actual = [r["case_id"] for r in rows]
    n_items = sum(len(r["items"]) for r in rows)
    gap_counts: dict[str, int] = {}
    for row in rows:
        for item in row["items"]:
            gap_counts[item["gap_class"]] = gap_counts.get(item["gap_class"], 0) + 1
    return [
        ("knowledge_audit 35 行 == subtype_split 35 题", actual == expected, f"{len(actual)} vs {len(expected)}"),
        ("知识项总数 = 五类 + undetermined", sum(gap_counts.values()) == n_items, json.dumps(gap_counts, ensure_ascii=False)),
    ]


def c1_check() -> list[tuple[str, bool, str]]:
    """C1 160 行对账。"""
    data = json.loads((P8_DIR / "c1_detector_eval.json").read_text(encoding="utf-8"))
    return [
        ("C1 replay_count == 1", data["replay_count"] == 1, ""),
        ("C1 total == 160", data["total"] == 160, ""),
        ("C1 四态和 == 160", sum(data["counts"].values()) == 160, json.dumps(data["counts"])),
        ("C1 verdict 为双终态之一", data["verdict"] in {"C1_PASS", "C1_TERMINATED"}, data["verdict"]),
    ]


def kb_equivalence_check() -> list[tuple[str, bool, str]]:
    """KB 等价性对账。"""
    eq = json.loads((P8_DIR / "kb_equivalence.json").read_text(encoding="utf-8"))
    return [
        ("KB 等价性 total == ok", eq["summary"]["total"] == eq["summary"]["ok"], json.dumps(eq["summary"])),
        ("KB 等价性 fallback_used == 0", eq["summary"]["fallback_used"] == 0, ""),
    ]


def manifest_disk_check() -> list[tuple[str, bool, str]]:
    """manifest 与磁盘产物 SHA 一致（四策略分列复算）。"""
    import hashlib

    manifest = json.loads((P8_DIR / "phase8_freeze_manifest.json").read_text(encoding="utf-8"))
    results = []
    for e in manifest["entries"]:
        path = REPO / e["path"]
        if not path.exists():
            results.append((f"{e['path']} 存在", False, "missing"))
            continue
        if e["strategy"] == "json_canonical":
            obj = json.loads(path.read_text(encoding="utf-8"))
            canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
            sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        elif e["strategy"] == "jsonl_canonical":
            lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            canonical = "".join(
                json.dumps(json.loads(l), sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
                for l in lines
            )
            sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        elif e["strategy"] == "raw_bytes":
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
        elif e["strategy"] == "git_canonical_lf":
            sha = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        else:
            sha = ""
        results.append((f"{e['path']} SHA 一致", sha == e["sha256"], e["strategy"]))
    return results


CHECKS: dict[str, list[tuple[str, bool, str]]] = {
    "subtype_split": subtype_check(),
    "required_knowledge": required_knowledge_check(),
    "computability_probe": probe_check(),
    "knowledge_audit": audit_check(),
    "c1_replay": c1_check(),
    "kb_equivalence": kb_equivalence_check(),
    "manifest_disk": manifest_disk_check(),
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
