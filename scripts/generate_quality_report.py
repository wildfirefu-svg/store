"""
generate_quality_report.py
Generate a SHA-stamped quality report for classic-text distillation artifacts.
Step 8 of the remediation plan: produce a report before deciding whether to
ingest into RAG / BaziQA.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "knowledge_base" / "classic_texts"

BOOKS = {
    "ditiansui": "滴天髓",
    "zipingzhenquan": "子平真诠",
    "qiongtongbaojian": "穷通宝鉴",
    "sanmingtonghui": "三命通会",
}


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "validator": "scripts/validate_classic_distillation.py",
        "books": {},
        "known_limitations": [],
    }

    for dir_key, name in BOOKS.items():
        p = BASE / dir_key
        entry = {"name": name, "dir": dir_key}

        rules_f = p / "all_rules.json"
        mcq_f = p / "all_mcq.jsonl"
        q_rules_f = p / "quarantine_rules.jsonl"
        q_mcq_f = p / "quarantine_mcq.jsonl"
        provenance_f = p / "provenance.json"

        if rules_f.exists():
            rules = json.loads(rules_f.read_text(encoding="utf-8"))
            entry["rules"] = {"count": len(rules), "sha256": sha256_file(rules_f)}
            cats = Counter(r.get("category", "?") for r in rules)
            entry["rules"]["categories"] = dict(cats.most_common())
        if mcq_f.exists():
            mcqs = [json.loads(l) for l in mcq_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["mcq"] = {"count": len(mcqs), "sha256": sha256_file(mcq_f)}
            ans = Counter(m.get("answer", "?") for m in mcqs)
            entry["mcq"]["answer_dist"] = dict(ans)
            valid = sum(v for k, v in ans.items() if k in "ABCD")
            entry["mcq"]["answer_pct"] = {k: round(v / max(1, valid), 4) for k, v in ans.items() if k in "ABCD"}
        if q_rules_f.exists():
            qr = [l for l in q_rules_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["quarantine_rules"] = {"count": len(qr), "sha256": sha256_file(q_rules_f)}
        else:
            entry["quarantine_rules"] = {"count": 0}
        if q_mcq_f.exists():
            qm = [l for l in q_mcq_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["quarantine_mcq"] = {"count": len(qm), "sha256": sha256_file(q_mcq_f)}
        else:
            entry["quarantine_mcq"] = {"count": 0}
        if provenance_f.exists():
            entry["provenance"] = json.loads(provenance_f.read_text(encoding="utf-8"))

        # validation snapshot
        val_f = BASE / "_validation_report.json"
        if val_f.exists():
            val = json.loads(val_f.read_text(encoding="utf-8"))
            for v in val:
                if v.get("dir") == dir_key:
                    entry["gates"] = {k: g.get("pass") for k, g in v.get("gates", {}).items()}
                    entry["all_gates_pass"] = v.get("passed", False)
                    break

        report["books"][dir_key] = entry

    # known limitations
    smth = report["books"].get("sanmingtonghui", {})
    if not smth.get("all_gates_pass", True):
        report["known_limitations"].append(
            "三命通会 G7 章节完整性: 80/383 章已蒸馏 (卷一-卷五基础内容)，"
            "缺 303 章 (卷五-卷十二格局与赋)。需 ~606 API calls 补齐，本轮未 scope。"
        )

    out = BASE / "QUALITY_REPORT.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Quality report written to {out}")
    print(f"\n=== Summary ===")
    total_rules = 0
    total_mcq = 0
    total_q_rules = 0
    total_q_mcq = 0
    for dir_key, e in report["books"].items():
        r = e.get("rules", {}).get("count", 0)
        m = e.get("mcq", {}).get("count", 0)
        qr = e.get("quarantine_rules", {}).get("count", 0)
        qm = e.get("quarantine_mcq", {}).get("count", 0)
        passed = "PASS" if e.get("all_gates_pass") else "FAIL"
        total_rules += r
        total_mcq += m
        total_q_rules += qr
        total_q_mcq += qm
        print(f"  {e['name']:<8} gates={passed:<4} rules={r:<5} mcq={m:<5} q_rules={qr:<3} q_mcq={qm:<3}")
    print(f"  {'TOTAL':<8} {'':<11} rules={total_rules:<5} mcq={total_mcq:<5} q_rules={total_q_rules:<3} q_mcq={total_q_mcq:<3}")
    print(f"\nKnown limitations: {len(report['known_limitations'])}")
    for lim in report["known_limitations"]:
        print(f"  - {lim}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
