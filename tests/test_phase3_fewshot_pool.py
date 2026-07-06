"""Tests for Phase 3 anti-position-bias few-shot pool.

Task 2 of the Phase 3 implementation plan. Written BEFORE the pool file exists,
so the collection/run failure is part of the TDD red phase. Once
`benchmark/fewshot/anti_position_bias_v1.jsonl` lands with the option-identity
schema, these tests should turn green.

Label-balance tests depend on `render_dynamic_fewshot` (Task 4) and live in
`test_phase3_prompt_builder.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


POOL = Path("benchmark/fewshot/anti_position_bias_v1.jsonl")

REQUIRED_DOMAINS = {
    "family",
    "health",
    "relationship",
    "annual_fortune",
    "career",
}

REQUIRED_FIELDS = {
    "id",
    "domain",
    "question",
    "option_identities",
    "observation",
    "reasoning",
    "position_bias_guard",
}

DEV_HOLDOUT = Path("benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl")
FINAL_HOLDOUT = Path("benchmark/datasets/baziqa_contest8_2024_holdout.jsonl")


def _load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _holdout_case_ids_and_questions(paths):
    ids: set[str] = set()
    questions: set[str] = set()
    for p in paths:
        if not p.exists():
            continue
        for row in _load_jsonl(p):
            cid = row.get("case_id")
            if cid:
                ids.add(str(cid))
            q = row.get("question")
            if q:
                questions.add(str(q).strip())
    return ids, questions


@pytest.fixture(scope="module")
def pool_rows():
    if not POOL.exists():
        pytest.fail(f"few-shot pool not found: {POOL}")
    return _load_jsonl(POOL)


def test_pool_has_five_examples(pool_rows):
    assert len(pool_rows) == 5


def test_pool_covers_required_domains(pool_rows):
    domains = {row["domain"] for row in pool_rows}
    assert REQUIRED_DOMAINS.issubset(domains), f"missing domains: {REQUIRED_DOMAINS - domains}"


def test_each_example_has_required_fields(pool_rows):
    for row in pool_rows:
        missing = REQUIRED_FIELDS - set(row.keys())
        assert not missing, f"{row.get('id')} missing fields: {missing}"


def test_example_id_prefix(pool_rows):
    for row in pool_rows:
        assert str(row["id"]).startswith("apb_"), f"id not apb_ prefixed: {row.get('id')}"


def test_option_identities_schema(pool_rows):
    for row in pool_rows:
        opts = row["option_identities"]
        assert isinstance(opts, list), f"{row['id']} option_identities not list"
        assert len(opts) == 4, f"{row['id']} has {len(opts)} options, expected 4"
        answer_flags = []
        for opt in opts:
            assert "id" in opt, f"{row['id']} option missing id"
            assert "text" in opt, f"{row['id']} option missing text"
            assert "is_answer" in opt, f"{row['id']} option missing is_answer"
            assert isinstance(opt["is_answer"], bool)
            answer_flags.append(opt["is_answer"])
        assert sum(answer_flags) == 1, f"{row['id']} must have exactly 1 answer, got {sum(answer_flags)}"


def test_no_fixed_top_level_answer_label(pool_rows):
    """few-shot must not fix a top-level A/B/C/D answer; only option identity marks the answer."""
    forbidden = {"answer", "answer_label", "gold", "expected_answer"}
    for row in pool_rows:
        present = forbidden & set(row.keys())
        assert not present, f"{row['id']} has fixed label fields: {present}"


def test_no_holdout_case_id_leak(pool_rows):
    holdout_ids, _ = _holdout_case_ids_and_questions([DEV_HOLDOUT, FINAL_HOLDOUT])
    for row in pool_rows:
        # few-shot id must not collide with holdout case_id
        assert str(row["id"]) not in holdout_ids, f"{row['id']} collides with holdout case_id"
        # no field value should equal a holdout case_id
        for key in ("case_id", "source_case_id", "holdout_id"):
            if key in row:
                assert str(row[key]) not in holdout_ids, f"{row['id']} {key} leaks holdout id"


def test_no_question_duplicate_with_holdout(pool_rows):
    _, holdout_questions = _holdout_case_ids_and_questions([DEV_HOLDOUT, FINAL_HOLDOUT])
    for row in pool_rows:
        q = str(row.get("question", "")).strip()
        assert q, f"{row['id']} empty question"
        assert q not in holdout_questions, f"{row['id']} question duplicates holdout"


def test_no_mingli_id_leak(pool_rows):
    for row in pool_rows:
        text = json.dumps(row, ensure_ascii=False)
        assert "mingli_" not in text, f"{row['id']} references mingli_ id"


def test_position_bias_guard_nonempty(pool_rows):
    for row in pool_rows:
        guard = str(row.get("position_bias_guard", "")).strip()
        assert guard, f"{row['id']} empty position_bias_guard"


def test_reasoning_is_concise(pool_rows):
    """reasoning should demonstrate per-option comparison, not long domain rules."""
    for row in pool_rows:
        reasoning = str(row.get("reasoning", ""))
        assert len(reasoning) <= 600, f"{row['id']} reasoning too long: {len(reasoning)} chars"
