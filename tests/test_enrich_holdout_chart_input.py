"""Tests for scripts.enrich_holdout_chart_input.

Task 2.2 of the BaziQA Hybrid Stage 1 implementation plan.

Red phase: locks the contract that the holdout enrichment script must
(a) achieve 100% chart_input coverage on a well-formed dataset,
(b) populate non-empty chart_input fields,
(c) be idempotent when a row already carries chart_input,
(d) reuse the corpus-side helpers (DRY) rather than reimplementing IO.

These assertions are expected to fail until Task 2.3 lands the
implementation that delegates to scripts.enrich_baziqa_chart_input.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _fake_compute_chart(year, month, day, hour, minute, gender, location="Beijing"):
    return {
        "four_pillars": {
            "year": {"gan": "庚", "zhi": "午"},
            "month": {"gan": "辛", "zhi": "巳"},
            "day": {"gan": "甲", "zhi": "子"},
            "hour": {"gan": "戊", "zhi": "辰"},
        },
        "day_master": {"gan": "甲", "wuxing": "木"},
        "birth_info": {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "minute": minute,
            "gender": gender,
            "place": location,
        },
        "wuxing_stats": {"木": 2, "火": 2, "土": 2, "金": 1, "水": 1},
        "shishen_stats": {"正官": 1},
    }


def _holdout_rows():
    return [
        {
            "case_id": "h1",
            "domain": "wealth",
            "person": {
                "gender": "female",
                "birth": {"year": 1990, "month": 5, "day": 12, "hour": 8, "minute": 30},
            },
        },
        {
            "case_id": "h2",
            "domain": "career",
            "person": {
                "gender": "male",
                "birth": {"year": 1985, "month": 11, "day": 2, "hour": 17, "minute": 0, "place": "Shanghai"},
            },
        },
        {
            "case_id": "h3",
            "domain": "relationship",
            "person": {
                "gender": "female",
                "birth": {"year": 2001, "month": 1, "day": 1, "hour": 23, "minute": 59},
            },
        },
    ]


def test_holdout_enrich_row_populates_chart_input(monkeypatch):
    """Each well-formed row must come back with a non-empty chart_input dict
    (Task 2.2 acceptance: coverage = 100% on the fixture).
    """
    from scripts import enrich_holdout_chart_input as mod

    enriched = [mod.enrich_row(row, compute_chart_fn=_fake_compute_chart) for row in _holdout_rows()]

    assert all(r.get("chart_input") for r in enriched)
    assert all(r["chart_input"].get("four_pillars") for r in enriched)
    # The first row had no `place` => the helper must fall back to a default.
    assert enriched[0]["chart_input"]["birth_info"]["place"] == "Beijing"


def test_holdout_enrich_row_is_idempotent(monkeypatch):
    """If a row already has chart_input, the helper must NOT overwrite it."""
    from scripts import enrich_holdout_chart_input as mod

    sentinel = {"four_pillars": {"day": {"gan": "preserved"}}}
    row = {
        "case_id": "h-precomputed",
        "chart_input": sentinel,
        "person": {
            "gender": "male",
            "birth": {"year": 1990, "month": 5, "day": 12, "hour": 8, "minute": 30},
        },
    }

    enriched = mod.enrich_row(row, compute_chart_fn=_fake_compute_chart)
    assert enriched["chart_input"] is sentinel


def test_holdout_cli_writes_jsonl_with_100_percent_coverage(monkeypatch, tmp_path):
    """End-to-end: CLI must produce an enriched JSONL with 100% coverage and
    emit a summary log line that reports the 100% number.
    """
    from scripts import enrich_holdout_chart_input as mod

    src = tmp_path / "holdout.jsonl"
    src.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in _holdout_rows()) + "\n",
        encoding="utf-8",
    )
    dst = tmp_path / "holdout_enriched.jsonl"

    monkeypatch.setattr(mod, "compute_chart", _fake_compute_chart, raising=False)

    rc = mod.main(["--input", str(src), "--output", str(dst)])
    assert rc == 0

    rows = [json.loads(line) for line in dst.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 3
    assert all(r.get("chart_input") for r in rows)


def test_holdout_summary_reports_full_coverage(monkeypatch):
    """The holdout script must reuse corpus-side summarize_rows so coverage
    metrics stay consistent (DRY acceptance).
    """
    from scripts import enrich_holdout_chart_input as mod
    from scripts import enrich_baziqa_chart_input as corpus_mod

    assert mod.summarize_rows is corpus_mod.summarize_rows, (
        "holdout script must reuse corpus summarize_rows; reimplementation drifts the metric"
    )

    rows = [mod.enrich_row(row, compute_chart_fn=_fake_compute_chart) for row in _holdout_rows()]
    summary = mod.summarize_rows(rows)
    assert summary == {"total": 3, "with_chart_input": 3, "coverage": 1.0}
