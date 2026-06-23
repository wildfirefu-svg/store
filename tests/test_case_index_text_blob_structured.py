"""Tests for case_index structured-feature injection into the vector text blob.

Task M3 review #1 + #2: verify that `_make_text_blob` actually receives
chart-derived structured features (day_master / wuxing / four pillars) and
embeds them into the text blob, instead of silently no-op'ing because the
features live on a different field path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _write_min_corpus(tmp_path: Path) -> Path:
    """Write a 1-row corpus with chart_input so the loader will run
    extract_bazi_features and build chart_features.
    """
    p = tmp_path / "corpus.jsonl"
    row = {
        "case_id": "c1",
        "domain": "wealth",
        "person": {
            "person_id": "p1",
            "name": "甲",
            "gender": "male",
            "birth": {"year": 1990, "month": 5, "day": 12, "hour": 8, "minute": 30, "place": "Beijing"},
        },
        "question": "财运?",
        "options": ["A", "B", "C", "D"],
        "answer": "B",
        "summary": "命主于乙未年破财",
        "facts": ["命主于乙未年破财 -> B"],
        "verified_events": {},
        "source_year": "2022",
        "chart_input": {
            "four_pillars": {
                "year": {"gan": "庚", "zhi": "午"},
                "month": {"gan": "辛", "zhi": "巳"},
                "day": {"gan": "甲", "zhi": "子"},
                "hour": {"gan": "戊", "zhi": "辰"},
            },
            "day_master": {"gan": "甲", "wuxing": "木"},
            "wuxing_stats": {"木": 2, "火": 2, "土": 2, "金": 1, "水": 1},
            "shishen_stats": {"正官": 1},
        },
    }
    p.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def test_make_text_blob_injects_structured_features_from_chart_features(tmp_path, monkeypatch):
    """When chart_features is non-empty, the rendered text blob must
    contain '结构化特征' and at least the day master + four pillars info.
    """
    monkeypatch.delenv("BAZI_RAG_VECTOR", raising=False)
    from case_index import CaseIndex

    idx = CaseIndex(_write_min_corpus(tmp_path))
    assert idx._cases, "expected one case to be indexed"
    blob = idx._cases[0]["text_blob"]

    assert "结构化特征" in blob, f"structured marker missing in text_blob: {blob!r}"
    # day master gan extracted from chart_input.day_master.gan
    assert "日主甲" in blob, blob
    # wuxing of day master
    assert "日主五行木" in blob, blob


def test_text_blob_no_structured_when_chart_features_absent(tmp_path, monkeypatch):
    """A row with no chart_input must NOT contain the structured marker."""
    monkeypatch.delenv("BAZI_RAG_VECTOR", raising=False)
    from case_index import CaseIndex

    p = tmp_path / "corpus.jsonl"
    row = {
        "case_id": "c1",
        "domain": "wealth",
        "person": {
            "person_id": "p1",
            "name": "甲",
            "gender": "male",
            "birth": {"year": 1990, "month": 5, "day": 12},
        },
        "question": "财运?",
        "options": ["A", "B", "C", "D"],
        "answer": "B",
        "summary": "命主于乙未年破财",
        "facts": ["命主于乙未年破财 -> B"],
        "verified_events": {},
        "source_year": "2022",
    }
    p.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    idx = CaseIndex(p)
    blob = idx._cases[0]["text_blob"]
    assert "结构化特征" not in blob, f"unexpected structured marker: {blob!r}"


def test_make_text_blob_does_not_explode_on_dict_four_pillars(tmp_path, monkeypatch):
    """Regression: the injection branch must not raise TypeError when the
    underlying chart_features lacks a `four_pillars` aggregate and only has
    the granular per-pillar keys produced by bazi_features.extract.
    """
    monkeypatch.delenv("BAZI_RAG_VECTOR", raising=False)
    from case_index import CaseIndex

    idx = CaseIndex(_write_min_corpus(tmp_path))
    blob = idx._cases[0]["text_blob"]
    # Must include the per-pillar tian-gan + di-zhi at least for year & day.
    assert "庚午" in blob or "甲子" in blob, blob
