"""Enrich the BaziQA holdout dataset with chart_input.

Thin CLI wrapper that delegates to the corpus-side helpers in
``scripts.enrich_baziqa_chart_input`` (DRY).  Holdout-specific behaviour
is kept minimal: a separate default summary path and an in-module
``compute_chart`` reference so tests can monkeypatch the symbol on this
module without touching the corpus side.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.enrich_baziqa_chart_input import (
    enrich_row as _corpus_enrich_row,
    load_jsonl,
    summarize_rows,
    write_jsonl,
)
from bazi_calculator import compute_chart  # re-exported so tests can monkeypatch it


def enrich_row(row, compute_chart_fn=None):
    """Delegate to corpus enrich_row, defaulting to this module's compute_chart.

    Resolves the default through ``sys.modules[__name__]`` so tests that
    monkeypatch ``scripts.enrich_holdout_chart_input.compute_chart`` see the
    patched function even when this helper is imported with a stale name.
    """
    fn = compute_chart_fn or sys.modules[__name__].compute_chart
    return _corpus_enrich_row(row, compute_chart_fn=fn)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Enrich BaziQA holdout JSONL with chart_input (delegates to corpus helpers).",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--summary",
        default=None,
        help="Optional markdown summary path; default: skip summary.",
    )
    args = parser.parse_args(argv)

    rows = [enrich_row(row) for row in load_jsonl(args.input)]
    write_jsonl(args.output, rows)
    summary = summarize_rows(rows)

    if args.summary:
        text = "\n".join([
            "# BaziQA Holdout Chart Input Enrichment Report",
            "",
            f"- Total: {summary['total']}",
            f"- With chart_input: {summary['with_chart_input']}",
            f"- Coverage: {summary['coverage']:.1%}",
            f"- Output: {args.output}",
            "",
        ])
        Path(args.summary).write_text(text, encoding="utf-8")

    print(
        f"Enriched {summary['with_chart_input']}/{summary['total']} rows "
        f"(coverage {summary['coverage']:.1%}) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
