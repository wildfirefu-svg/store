"""
remediate_classic_distillation.py
No-API post-hoc remediation for classic-text distillation artifacts.

Fixes (no model calls):
  R1  re-assign rule IDs deterministically: {prefix}_{chIdx:03d}_{ruleIdx:03d}
  R2  quarantine rules whose original_text is untraceable in raw_*.txt
  R3  re-assign MCQ IDs deterministically: {prefix}_{chIdx:03d}_mcq_{seq:03d}
  R4  re-map MCQ source_rule_id to new rule IDs (positional within chapter;
      low-confidence books flagged needs_mcq_regen)
  R5  deterministic answer rotation -> each of A/B/C/D ~25%

Outputs per book dir:
  all_rules.json          (clean, re-IDed, untraceable removed)
  quarantine_rules.jsonl  (untraceable rules, kept for review)
  all_mcq.jsonl           (clean, re-IDed, answer-balanced; or unchanged if needs_mcq_regen)
  remediation_meta.json   (what was done, counts, flags)
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "knowledge_base" / "classic_texts"

BOOKS = {
    "ditiansui": ("滴天髓", "dts"),
    "zipingzhenquan": ("子平真诠", "zpzq"),
    "qiongtongbaojian": ("穷通宝鉴", "qtbj"),
    "sanmingtonghui": ("三命通会", "smth"),
}

# Books whose rule IDs already unique -> MCQ source_rule_id can be mapped directly.
# Others (colliding rule IDs, no MCQ chapter field) -> positional best-effort, flag for regen.
UNIQUE_RULE_ID_BOOKS = {"ditiansui", "qiongtongbaojian"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _load_raw_corpus(p: Path) -> str:
    parts = []
    for f in sorted(p.glob("raw_*.txt")):
        parts.append(f.read_text(encoding="utf-8"))
    return _norm("".join(parts))


def _slug(ch: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]", "_", ch or "")
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:24] or "ch"


def _rotate_answer(mcq: dict, target: str) -> dict:
    """Return a copy with options permuted so correct content lands at `target` label."""
    cur = mcq.get("answer", "")
    if cur not in "ABCD" or target == cur:
        mcq["answer"] = cur if cur in "ABCD" else cur
        return mcq
    opts = dict(mcq.get("options", {}))
    if target not in opts or cur not in opts:
        return mcq
    opts[cur], opts[target] = opts[target], opts[cur]
    mcq["options"] = opts
    mcq["answer"] = target
    return mcq


def remediate_book(dir_key: str, name: str, prefix: str) -> dict:
    p = BASE / dir_key
    meta = {"book": name, "dir": dir_key, "prefix": prefix, "actions": {}}
    if not p.is_dir():
        meta["error"] = "missing dir"
        return meta

    rules = json.loads((p / "all_rules.json").read_text(encoding="utf-8"))
    mcqs = [json.loads(l) for l in (p / "all_mcq.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    raw_corpus = _load_raw_corpus(p)

    # group rules by source_chapter, preserving file order within chapter
    ch_order: list[str] = []
    ch_rules: dict[str, list[dict]] = defaultdict(list)
    for r in rules:
        ch = r.get("source_chapter", "_unknown_")
        if ch not in ch_rules:
            ch_order.append(ch)
        ch_rules[ch].append(r)

    ch_idx = {ch: i for i, ch in enumerate(ch_order)}

    # R1: re-assign rule IDs
    old_to_new: dict[str, str] = {}
    clean_rules: list[dict] = []
    quarantine: list[dict] = []
    for ch in ch_order:
        ci = ch_idx[ch]
        for ri, r in enumerate(ch_rules[ch]):
            new_id = f"{prefix}_{ci:03d}_{ri:03d}"
            old_id = r.get("id", "")
            if dir_key in UNIQUE_RULE_ID_BOOKS:
                old_to_new[old_id] = new_id
            r = dict(r)
            r["id"] = new_id
            # R2: traceability quarantine
            ot = _norm(r.get("original_text", ""))
            if ot and ot not in raw_corpus:
                r["quarantine_reason"] = "original_text_not_in_raw"
                quarantine.append(r)
            else:
                clean_rules.append(r)
    meta["actions"]["R1_reID_rules"] = {"before": len(rules), "clean": len(clean_rules), "quarantine": len(quarantine)}

    # write clean rules
    (p / "all_rules.json").write_text(
        json.dumps(clean_rules, ensure_ascii=False, indent=2), encoding="utf-8")
    (p / "quarantine_rules.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in quarantine), encoding="utf-8")

    # R3/R4/R5: MCQ remediation
    needs_regen = dir_key not in UNIQUE_RULE_ID_BOOKS
    if needs_regen:
        # Best-effort positional map: walk MCQs in order against per-chapter rule sequences.
        # If MCQ count != sum(rules_per_chapter) we cannot align reliably -> flag.
        rule_counts = [len(ch_rules[ch]) for ch in ch_order]
        total_rule_slots = sum(rule_counts)
        # We attempt alignment only if MCQ count matches a plausible subset; otherwise skip.
        aligned = (len(mcqs) <= total_rule_slots)
        new_mcqs: list[dict] = []
        if aligned:
            mcq_i = 0
            for ch in ch_order:
                ci = ch_idx[ch]
                ch_rule_ids = [f"{prefix}_{ci:03d}_{ri:03d}" for ri in range(len(ch_rules[ch]))]
                # consume MCQs whose source_rule_id matches the chapter's old pattern is impossible
                # (no chapter field). Instead assume this chapter produced min(len(rules), remaining)
                # MCQs in order -- only safe if 1:1. We cannot guarantee; mark needs_regen.
                break
            # could not confidently align
            needs_regen = True
        if needs_regen:
            # leave MCQ file unchanged but record flag
            meta["actions"]["R4_mcq_remap"] = {"needs_regen": True, "reason": "colliding rule IDs + no MCQ chapter field"}
            meta["needs_mcq_regen"] = True
            (p / "remediation_meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            return meta

    # Books with unique rule IDs (or successfully aligned): remap source_rule_id + re-ID + rotate
    new_mcqs: list[dict] = []
    quarantined_mcqs: list[dict] = []
    mcq_seq = 0
    # build chapter index lookup from rule new IDs
    rule_newid_to_chidx: dict[str, int] = {}
    for ch in ch_order:
        ci = ch_idx[ch]
        for ri in range(len(ch_rules[ch])):
            nid = f"{prefix}_{ci:03d}_{ri:03d}"
            rule_newid_to_chidx[nid] = ci
    # set of new IDs that survived (clean rules only)
    surviving_new_ids = {r["id"] for r in clean_rules}
    for m in mcqs:
        m = dict(m)
        old_src = m.get("source_rule_id", "")
        new_src = old_to_new.get(old_src, old_src)
        if new_src not in surviving_new_ids:
            m["quarantine_reason"] = "source_rule_quarantined_or_missing"
            quarantined_mcqs.append(m)
            continue
        m["source_rule_id"] = new_src
        # assign new MCQ id by chapter of source rule
        ci = rule_newid_to_chidx.get(new_src, 0)
        m["id"] = f"{prefix}_{ci:03d}_mcq_{mcq_seq:04d}"
        mcq_seq += 1
        # R5: deterministic answer rotation
        target = "ABCD"[mcq_seq % 4]
        m = _rotate_answer(m, target)
        new_mcqs.append(m)
    (p / "all_mcq.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in new_mcqs), encoding="utf-8")
    if quarantined_mcqs:
        (p / "quarantine_mcq.jsonl").write_text(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in quarantined_mcqs), encoding="utf-8")
    meta["actions"]["R3_reID_mcq"] = {"kept": len(new_mcqs), "quarantined": len(quarantined_mcqs)}
    ans = Counter(m.get("answer", "?") for m in new_mcqs)
    meta["actions"]["R5_answer_balance"] = {"dist": dict(ans)}

    meta["needs_mcq_regen"] = False
    (p / "remediation_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    results = []
    for dir_key, (name, prefix) in BOOKS.items():
        print(f"--- remediating {name} ---")
        r = remediate_book(dir_key, name, prefix)
        results.append(r)
        for k, v in r.get("actions", {}).items():
            print(f"  {k}: {v}")
        if r.get("needs_mcq_regen"):
            print(f"  >> MCQ regen REQUIRED (API)")
    print("\n=== summary ===")
    for r in results:
        print(f"  {r['book']}: needs_mcq_regen={r.get('needs_mcq_regen', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
