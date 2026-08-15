"""
validate_classic_distillation.py
Blocking gate for classic-text distillation artifacts.

Checks per book:
  G1  rule ID uniqueness        : every rule.id distinct
  G2  MCQ ID uniqueness         : every mcq.id distinct
  G3  schema completeness       : required keys present on every record
  G4  source_rule_id validity   : every MCQ source_rule_id exists in rules AND referenced uniquely
  G5  original_text traceability: original_text (whitespace-normalized) found in some raw_*.txt
  G6  answer distribution       : each of A/B/C/D in [18%, 32%] of valid answers
  G7  chapter completeness      : len(progress.done) >= len(chapter_list)  (or section_list)
  G8  MCQ row well-formedness   : every mcq row has question/options/answer (no rule objects leaked in)

Exit code 0 = all gates pass; 1 = one or more gates failed.
A per-book, per-gate report is printed and also written to
knowledge_base/classic_texts/_validation_report.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "knowledge_base" / "classic_texts"

BOOKS = {
    "ditiansui": "滴天髓",
    "zipingzhenquan": "子平真诠",
    "qiongtongbaojian": "穷通宝鉴",
    "sanmingtonghui": "三命通会",
}

RULE_REQUIRED = {"id", "category", "subject", "condition", "rule", "original_text",
                 "source_book", "source_chapter"}
MCQ_REQUIRED = {"id", "question", "options", "answer", "explanation",
                "source_rule_id", "difficulty", "category"}

ANSWER_MIN_PCT = 0.18
ANSWER_MAX_PCT = 0.32


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _load_rules(p: Path) -> list[dict]:
    f = p / "all_rules.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8"))


def _load_mcq(p: Path) -> list[dict]:
    f = p / "all_mcq.jsonl"
    if not f.exists():
        return []
    out = []
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"_parse_error": True, "_line": i, "_raw": line[:120]})
    return out


def _load_raw_corpus(p: Path) -> str:
    parts = []
    for f in sorted(p.glob("raw_*.txt")):
        parts.append(f.read_text(encoding="utf-8"))
    return _norm("".join(parts))


def _load_chapter_list(p: Path) -> list[str] | None:
    """Return normalized chapter/section names from chapter_list.txt or section_list.txt."""
    for name in ("chapter_list.txt", "section_list.txt"):
        f = p / name
        if f.exists():
            names = []
            for ln in f.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                # strip leading number + dot + whitespace, e.g. "1. 卷一·原造化之始" -> "卷一·原造化之始"
                name_part = ln.split("\t", 1)[0]  # tab-separated: name\tURL
                name_part = re.sub(r"^\d+[\.\s]*", "", name_part).strip()
                names.append(name_part)
            return names
    return None


def _progress_done_list(p: Path) -> list[str]:
    f = p / "progress.json"
    if not f.exists():
        return []
    prog = json.loads(f.read_text(encoding="utf-8"))
    done = prog.get("done", [])
    return done if isinstance(done, list) else []


def _progress_done_count(p: Path) -> int:
    return len(_progress_done_list(p))


def validate_book(dir_key: str, name: str, base_path: Path | None = None) -> dict:
    base = base_path or BASE
    p = base / dir_key
    report = {"book": name, "dir": dir_key, "gates": {}, "passed": True}
    if not p.is_dir():
        report["gates"]["__missing__"] = "directory not found"
        report["passed"] = False
        return report

    rules = _load_rules(p)
    mcqs = _load_mcq(p)
    raw_corpus = _load_raw_corpus(p)

    # G1 rule ID uniqueness
    rule_ids = [r.get("id", "") for r in rules if isinstance(r, dict)]
    dup_rules = len(rule_ids) - len(set(rule_ids))
    report["gates"]["G1_rule_id_unique"] = {
        "total": len(rule_ids), "unique": len(set(rule_ids)), "duplicates": dup_rules,
        "pass": dup_rules == 0,
    }

    # G2 MCQ ID uniqueness
    mcq_ids = [m.get("id", "") for m in mcqs if isinstance(m, dict) and not m.get("_parse_error")]
    dup_mcq = len(mcq_ids) - len(set(mcq_ids))
    report["gates"]["G2_mcq_id_unique"] = {
        "total": len(mcq_ids), "unique": len(set(mcq_ids)), "duplicates": dup_mcq,
        "pass": dup_mcq == 0,
    }

    # G3 schema completeness
    bad_rule_schema = [r.get("id", "?") for r in rules
                       if isinstance(r, dict) and not RULE_REQUIRED.issubset(r.keys())]
    bad_mcq_schema = [(m.get("id", f"line{m.get('_line','?')}")) for m in mcqs
                      if isinstance(m, dict) and not m.get("_parse_error")
                      and not MCQ_REQUIRED.issubset(m.keys())]
    parse_errors = [m for m in mcqs if isinstance(m, dict) and m.get("_parse_error")]
    report["gates"]["G3_schema"] = {
        "bad_rules": len(bad_rule_schema), "bad_mcq": len(bad_mcq_schema),
        "parse_errors": len(parse_errors),
        "pass": not bad_rule_schema and not bad_mcq_schema and not parse_errors,
    }

    # G4 source_rule_id validity: bad = not in rules; ambiguous = same id maps to >1 rule
    # (multiple MCQs referencing the SAME rule is legitimate, not ambiguity)
    valid_rule_ids = set(rule_ids)
    rule_id_counts = Counter(rule_ids)
    src_refs = [m.get("source_rule_id", "") for m in mcqs
                if isinstance(m, dict) and not m.get("_parse_error")]
    bad_refs = [s for s in src_refs if s not in valid_rule_ids]
    ambiguous_refs = [s for s in set(src_refs) if rule_id_counts.get(s, 0) > 1]
    report["gates"]["G4_source_rule_id"] = {
        "total_refs": len(src_refs),
        "bad": len(bad_refs),
        "ambiguous_rule_ids": len(ambiguous_refs),
        "pass": not bad_refs and not ambiguous_refs,
    }

    # G5 original_text traceability
    if raw_corpus:
        untraceable = []
        for r in rules:
            if not isinstance(r, dict):
                continue
            ot = _norm(r.get("original_text", ""))
            if ot and ot not in raw_corpus:
                untraceable.append(r.get("id", "?"))
        rate = 1 - len(untraceable) / max(1, len(rules))
        report["gates"]["G5_traceability"] = {
            "total": len(rules), "untraceable": len(untraceable), "rate": round(rate, 4),
            "pass": len(untraceable) == 0,
        }
    else:
        report["gates"]["G5_traceability"] = {"pass": False, "reason": "no raw files"}

    # G6 answer distribution
    ans = Counter(m.get("answer", "?") for m in mcqs
                  if isinstance(m, dict) and not m.get("_parse_error"))
    valid = sum(v for k, v in ans.items() if k in "ABCD")
    dist_pct = {k: round(v / max(1, valid), 4) for k, v in ans.items() if k in "ABCD"}
    oob = [k for k, v in dist_pct.items()
           if v < ANSWER_MIN_PCT or v > ANSWER_MAX_PCT]
    invalid = sum(v for k, v in ans.items() if k not in "ABCD")
    report["gates"]["G6_answer_dist"] = {
        "dist_pct": dist_pct, "invalid_answers": invalid,
        "out_of_band": oob,
        "pass": not oob and invalid == 0,
    }

    # G7 chapter completeness (set equality, not just count)
    expected_chapters = _load_chapter_list(p)
    done_chapters = _progress_done_list(p)
    if expected_chapters is not None:
        # Normalize both lists: strip whitespace, normalize fullwidth/halfwidth
        def _norm_ch(name: str) -> str:
            return re.sub(r"\s+", "", name.strip())
        expected_set = {_norm_ch(c) for c in expected_chapters if c}
        done_set = {_norm_ch(c) for c in done_chapters if c}
        missing = expected_set - done_set
        extra = done_set - expected_set
        report["gates"]["G7_chapter_complete"] = {
            "expected": len(expected_set), "done": len(done_set),
            "missing": sorted(missing)[:20], "missing_count": len(missing),
            "extra": sorted(extra)[:20], "extra_count": len(extra),
            "pass": not missing and not extra,
        }
    else:
        report["gates"]["G7_chapter_complete"] = {"pass": True, "reason": "no chapter_list"}

    # G8 MCQ row well-formedness (no rule objects leaked)
    leaked = []
    for m in mcqs:
        if isinstance(m, dict) and m.get("_parse_error"):
            continue
        opts = m.get("options")
        if not isinstance(opts, dict) or not set("ABCD").issubset(opts.keys()):
            leaked.append(m.get("id", "?"))
        elif not isinstance(m.get("answer"), str) or m["answer"] not in "ABCD":
            leaked.append(m.get("id", "?"))
    report["gates"]["G8_mcq_well_formed"] = {
        "malformed": len(leaked), "pass": not leaked,
    }

    # G9 content deduplication (global, normalized)
    # Rule text dedup: same normalized rule text must not appear under multiple rule IDs.
    # Cross-chapter duplicates must be merged into a single canonical rule with
    # a source_chapters list (handled by remediation R7).
    rule_text_map: dict[str, list[str]] = {}
    for r in rules:
        if not isinstance(r, dict):
            continue
        rt = _norm(r.get("rule", ""))
        if not rt:
            continue
        rule_text_map.setdefault(rt, []).append(r.get("id", "?"))
    rule_text_dup = {t: ids for t, ids in rule_text_map.items() if len(ids) > 1}
    # MCQ question dedup (global, normalized)
    mcq_questions = [_norm(m.get("question", "")) for m in mcqs
                     if isinstance(m, dict) and not m.get("_parse_error")]
    mcq_q_dup = len(mcq_questions) - len(set(mcq_questions))
    report["gates"]["G9_content_dedup"] = {
        "rule_text_duplicate_groups": len(rule_text_dup),
        "rule_text_duplicate_count": sum(len(ids) - 1 for ids in rule_text_dup.values()),
        "rule_text_duplicate_samples": {
            t[:60]: ids for t, ids in list(rule_text_dup.items())[:5]
        },
        "mcq_question_duplicates": mcq_q_dup,
        "pass": not rule_text_dup and mcq_q_dup == 0,
    }

    report["passed"] = all(g.get("pass", False) for g in report["gates"].values())
    report["totals"] = {"rules": len(rules), "mcq": len(mcqs)}
    return report


def main() -> int:
    overall = True
    out = []
    for dir_key, name in BOOKS.items():
        r = validate_book(dir_key, name)
        out.append(r)
        overall = overall and r["passed"]
        status = "PASS" if r["passed"] else "FAIL"
        print(f"\n=== {name} ({dir_key}): {status} ===")
        for gname, g in r["gates"].items():
            gs = "PASS" if g.get("pass") else "FAIL"
            extra = {k: v for k, v in g.items() if k != "pass"}
            print(f"  {gname}: {gs}  {extra}")

    rep_path = BASE / "_validation_report.json"
    rep_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {rep_path}")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Historical-artifact exemption application (E -> R -> B1 chain, stage 1)
# ---------------------------------------------------------------------------
from scripts.classic_artifacts import verify_exemption_request


def apply_exemption(issues: dict, exemption_request: dict) -> dict:
    """Apply an approved exemption: exempt listed checks (fail-closed on a
    malformed / un-approved request via verify_exemption_request)."""
    verify_exemption_request(exemption_request)
    out = dict(issues)
    for check in exemption_request["exempted_checks"]:
        if check in out: out[check] = "exempted"
    return out