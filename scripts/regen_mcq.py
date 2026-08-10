"""
regen_mcq.py
Regenerate MCQ for books flagged needs_mcq_regen, using corrected distill_lib.
Reads existing re-IDed all_rules.json, regenerates MCQ per chapter with proper
source_rule_id linkage + deterministic answer rotation.

Usage: python scripts/regen_mcq.py [book_dir_key ...]
Default: all books with remediation_meta.needs_mcq_regen == True
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import distill_lib as dl

BASE = ROOT / "knowledge_base" / "classic_texts"
BOOKS = {
    "zipingzhenquan": ("子平真诠", "zpzq"),
    "sanmingtonghui": ("三命通会", "smth"),
    "qiongtongbaojian": ("穷通宝鉴", "qtbj"),
    "ditiansui": ("滴天髓", "dts"),
}


def regen_book(dir_key: str) -> dict:
    name, prefix = BOOKS[dir_key]
    p = BASE / dir_key
    meta_f = p / "remediation_meta.json"
    if meta_f.exists():
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        if not meta.get("needs_mcq_regen", False) and not (sys.argv.count(dir_key) > 0):
            print(f"[{name}] skip (already clean)")
            return {"book": name, "skipped": True}

    rules = json.loads((p / "all_rules.json").read_text(encoding="utf-8"))
    ch_groups: dict[str, list[dict]] = defaultdict(list)
    ch_order: list[str] = []
    for r in rules:
        ch = r.get("source_chapter", "_unknown_")
        if ch not in ch_groups:
            ch_order.append(ch)
        ch_groups[ch].append(r)

    all_mcqs: list[dict] = []
    total_ch = len(ch_order)
    for ci, ch in enumerate(ch_order):
        ch_rules = ch_groups[ch]
        print(f"[{name}] {ci+1}/{total_ch} {ch[:20]} -> mcq...", flush=True)
        try:
            mcqs = dl.generate_mcq(ch_rules, name, ch)
            mcqs = dl.link_mcq_to_rules(mcqs, ch_rules)
        except Exception as e:
            print(f"  ERROR: {e}")
            mcqs = []
        all_mcqs.extend(mcqs)
        time.sleep(0.3)

    dl.rotate_answers(all_mcqs)
    seq = 0
    for ci, ch in enumerate(ch_order):
        ch_mcqs = [m for m in all_mcqs if m.get("source_rule_id", "").startswith(f"{prefix}_{ci:03d}_")]
        seq = dl.assign_mcq_ids(ch_mcqs, prefix, ci, seq)

    (p / "all_mcq.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in all_mcqs), encoding="utf-8")
    print(f"[{name}] wrote {len(all_mcqs)} MCQ")
    return {"book": name, "mcq_count": len(all_mcqs)}


def main() -> int:
    targets = [a for a in sys.argv[1:] if a in BOOKS]
    if not targets:
        targets = [k for k, _ in BOOKS.items()]
    for k in targets:
        regen_book(k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
