"""Tests for scripts.compute_retrieved_answer_leak.

Task 1.1 of the BaziQA Hybrid Stage 1 implementation plan.

This file is intentionally written BEFORE the implementation script exists, so
the import/collection-time failure is part of the TDD red phase. Once
`scripts/compute_retrieved_answer_leak.py` lands with `compute_leak_ratio`,
these tests should turn green without further edits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_case_row(
    case_id: str,
    expected_answer: str,
    facts_per_case: list[list[str]],
) -> dict:
    """Build one case_details-style record matching the live JSONL schema.

    The shape mirrors `.tmp/p2_refined_rag_k2_10_details.jsonl`:
    top-level expected_answer + rag_trace (list of dicts), each rag_trace entry
    has a `facts` list of strings.
    """
    return {
        "case_id": case_id,
        "domain": "wealth",
        "question": "示例问题",
        "expected_answer": expected_answer,
        "predicted_answer": "A",
        "rag_k": 2,
        "rag_trace": [
            {
                "rank": idx + 1,
                "person_id": f"P{idx+1}",
                "name": f"命例{idx+1}",
                "birth_year": 1980,
                "gender": "male",
                "domains": {"wealth": 1},
                "score": 0.5,
                "match_reasons": ["same_domain:wealth"],
                "facts": facts,
            }
            for idx, facts in enumerate(facts_per_case)
        ],
    }


@pytest.fixture
def two_case_rows():
    """Two case_details rows: one with leak, one without."""
    leaky = _make_case_row(
        case_id="leak-1",
        expected_answer="B",
        facts_per_case=[
            ["命主于乙未年破财，最终选 B 选项的情形已发生"],
            ["命主家境普通"],
        ],
    )
    clean = _make_case_row(
        case_id="clean-1",
        expected_answer="C",
        facts_per_case=[
            ["命主于丁酉年家境普通"],
            ["命主性格开朗"],
        ],
    )
    return [leaky, clean]


def test_compute_leak_ratio_returns_half_on_one_leak_one_clean(two_case_rows):
    """50% leak ratio when 1 of 2 case_details has expected_answer appearing
    in some retrieved facts string.
    """
    from scripts.compute_retrieved_answer_leak import compute_leak_ratio

    ratio = compute_leak_ratio(two_case_rows)
    assert ratio == pytest.approx(0.5)


def test_compute_leak_ratio_zero_when_no_rows():
    """Empty input must return 0.0 rather than raising ZeroDivisionError."""
    from scripts.compute_retrieved_answer_leak import compute_leak_ratio

    assert compute_leak_ratio([]) == 0.0


def test_compute_leak_ratio_respects_answer_field_override(two_case_rows):
    """The function must support a custom answer field name so historical
    case_details (which might use `answer` / `correct_answer`) can still be
    scored.
    """
    from scripts.compute_retrieved_answer_leak import compute_leak_ratio

    rows = []
    for row in two_case_rows:
        new = dict(row)
        new["correct_answer"] = new.pop("expected_answer")
        rows.append(new)

    ratio = compute_leak_ratio(rows, answer_field="correct_answer")
    assert ratio == pytest.approx(0.5)


def test_compute_leak_ratio_ignores_empty_or_missing_rag_trace():
    """Rows without rag_trace or with empty rag_trace must count as clean,
    not raise.
    """
    from scripts.compute_retrieved_answer_leak import compute_leak_ratio

    rows = [
        {"case_id": "no-trace", "expected_answer": "A"},
        {"case_id": "empty-trace", "expected_answer": "A", "rag_trace": []},
        {
            "case_id": "leak",
            "expected_answer": "D",
            "rag_trace": [{"facts": ["此命应选 D"]}],
        },
    ]
    ratio = compute_leak_ratio(rows)
    assert ratio == pytest.approx(1 / 3)


def test_compute_leak_ratio_loads_jsonl_via_cli_helper(tmp_path: Path, two_case_rows):
    """The script must expose a helper that loads case_details JSONL so the
    CLI and other scripts can reuse the same loader (DRY).
    """
    from scripts.compute_retrieved_answer_leak import (
        compute_leak_ratio,
        load_case_details_jsonl,
    )

    jsonl_path = tmp_path / "case_details.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in two_case_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    loaded = load_case_details_jsonl(jsonl_path)
    assert compute_leak_ratio(loaded) == pytest.approx(0.5)


def test_compute_strict_leak_ratio_only_counts_question_aligned():
    """Strict variant must require BOTH ``-> {answer}`` AND question overlap.

    A fact from an unrelated neighbour question (different question prefix)
    must NOT count as a leak even though it contains ``-> {answer}``.
    Only facts whose question prefix matches the current row's question
    prefix are counted.
    """
    from scripts.compute_retrieved_answer_leak import compute_strict_leak_ratio

    rows = [
        {
            "case_id": "g1",
            "question": "此命出生家境如何？",
            "expected_answer": "A",
            "rag_trace": [{"facts": ["此命1996年发生何事？ -> A 患上严重抑郁症"]}],
        },
        {
            "case_id": "g2",
            "question": "此命1996年发生何事？",
            "expected_answer": "A",
            "rag_trace": [{"facts": ["此命1996年发生何事？ -> A 患上严重抑郁症"]}],
        },
    ]

    assert compute_strict_leak_ratio(rows) == pytest.approx(0.5)


def test_compute_strict_leak_ratio_zero_when_no_rows():
    from scripts.compute_retrieved_answer_leak import compute_strict_leak_ratio

    assert compute_strict_leak_ratio([]) == 0.0
