"""Compute retrieved_answer_leak from case_details JSONL artifacts.

The leak ratio is defined as the proportion of cases where the
expected answer string (case-insensitive, whitespace-stripped) appears
in at least one retrieved fact string.

Usage:
    python scripts/compute_retrieved_answer_leak.py \
        --case-details-jsonl .tmp/p2_refined_rag_k2_10_details.jsonl \
        --summary-json .tmp/leak_summary.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_case_details_jsonl(path: Path) -> list[dict]:
    """Load case_details JSONL into a list of dicts (preserve order)."""
    path = Path(path)
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _case_is_leaky(row: dict, answer_field: str) -> bool:
    """Return True when expected_answer appears in any retrieved fact string."""
    answer = str(row.get(answer_field) or "").strip().lower()
    if not answer:
        return False

    rag_trace = row.get("rag_trace") or []
    for hit in rag_trace:
        facts = hit.get("facts") or []
        for fact in facts:
            if not isinstance(fact, str):
                continue
            if answer in fact.lower():
                return True
    return False


def compute_leak_ratio(rows: list[dict], answer_field: str = "expected_answer") -> float:
    """Return proportion of rows in which the answer value appears in facts.

    Empty input returns 0.0.
    """
    if not rows:
        return 0.0

    leaky = 0
    for row in rows:
        if _case_is_leaky(row, answer_field):
            leaky += 1

    return leaky / len(rows)


def build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compute retrieved answer leak ratio")
    p.add_argument("--case-details-jsonl", type=Path, required=True)
    p.add_argument("--summary-json", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    rows = load_case_details_jsonl(args.case_details_jsonl)
    ratio = compute_leak_ratio(rows)

    summary = {
        "source": str(args.case_details_jsonl),
        "row_count": len(rows),
        "leak_count": sum(1 for r in rows if _case_is_leaky(r, "expected_answer")),
        "leak_ratio": round(ratio, 6),
    }

    if args.summary_json:
        with args.summary_json.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
