"""Tests for Phase 3 APB prompt and dynamic few-shot render.

Task 4 of the Phase 3 implementation plan. Pure function-level tests that do
NOT depend on CLI argument passing. Written BEFORE the implementation lands,
so import failure is the TDD red phase.
"""

from __future__ import annotations

import json
from pathlib import Path
from collections import Counter

import pytest

from rag_prompt_builder import (
    format_apb_instruction_block,
    select_fewshot_examples,
    render_dynamic_fewshot,
    load_fewshot_examples,
)


POOL = Path("benchmark/fewshot/anti_position_bias_v1.jsonl")


@pytest.fixture(scope="module")
def pool_examples():
    rows = []
    for line in POOL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_apb_block_contains_key_phrases():
    block = format_apb_instruction_block()
    assert "选项内容" in block
    assert "A/B/C/D" in block or "位置" in block
    assert "label" in block or "标签" in block or "字母" in block


def test_select_fewshot_by_domain(pool_examples):
    selected = select_fewshot_examples(pool_examples, domain="health", limit=1)
    assert len(selected) == 1
    assert selected[0]["domain"] == "health"


def test_select_fewshot_limit(pool_examples):
    selected = select_fewshot_examples(pool_examples, domain=None, limit=2)
    assert len(selected) <= 2


def test_select_fewshot_missing_domain_returns_empty(pool_examples):
    selected = select_fewshot_examples(pool_examples, domain="nonexistent_domain", limit=1)
    assert selected == []


def test_render_returns_label_map(pool_examples):
    ex = pool_examples[0]
    result = render_dynamic_fewshot(ex, seed=42)
    assert "label_map" in result
    assert "answer_label" in result
    assert "rendered" in result
    assert len(result["label_map"]) == 4
    assert set(result["label_map"].values()) == {"A", "B", "C", "D"}


def test_render_answer_label_consistent_with_map(pool_examples):
    ex = pool_examples[0]
    result = render_dynamic_fewshot(ex, seed=42)
    answer_opt = next(o for o in ex["option_identities"] if o["is_answer"])
    assert result["label_map"][answer_opt["id"]] == result["answer_label"]


def test_render_different_seeds_produce_multiple_maps(pool_examples):
    """Different seeds should produce more than one distinct permutation overall.
    Two specific seeds may collide (only 4! permutations exist), so we check
    that across several seeds we observe at least 2 distinct label_maps."""
    ex = pool_examples[0]
    maps = []
    for s in [42, 137, 2026, 1, 2, 3, 4, 5]:
        maps.append(tuple(sorted(render_dynamic_fewshot(ex, seed=s)["label_map"].items())))
    assert len(set(maps)) >= 2, "all seeds produced the same label_map"


def test_render_contains_question_and_options(pool_examples):
    ex = pool_examples[0]
    result = render_dynamic_fewshot(ex, seed=42)
    assert ex["question"] in result["rendered"]
    for opt in ex["option_identities"]:
        assert opt["text"] in result["rendered"]


def test_label_balance_across_renders(pool_examples):
    """Across 5 examples x 20 seeds, answer label distribution must be balanced."""
    seeds = list(range(1, 21))
    labels = []
    for ex in pool_examples:
        for s in seeds:
            labels.append(render_dynamic_fewshot(ex, seed=s)["answer_label"])
    counts = Counter(labels)
    total = len(labels)
    max_count = max(counts.values())
    max_ratio = max_count / total
    assert set(counts.keys()) == {"A", "B", "C", "D"}, f"missing labels: {counts}"
    assert max_ratio <= 0.35, f"label imbalance: {counts}, max_ratio={max_ratio:.2f}"


def test_render_reproducible_with_same_seed(pool_examples):
    ex = pool_examples[0]
    r1 = render_dynamic_fewshot(ex, seed=2026)
    r2 = render_dynamic_fewshot(ex, seed=2026)
    assert r1 == r2
