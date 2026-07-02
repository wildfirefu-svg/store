"""Failing tests for the yet-to-be-implemented shuffle-options helpers.

Interface under test (see docs/superpowers/plans/2026-07-01-phase1-evaluation-infra.md):

- benchmark.runners.shuffle_options.shuffle_options(row, seed) -> dict
- benchmark.runners.shuffle_options.unshuffle_predicted_answer(predicted, answer_label_map) -> Optional[str]

Behaviour contract covered here:
1. Deterministic given the same seed; different seed produces different order at least sometimes.
2. Options are re-labelled to their new position ("A. x" placed at slot 3 becomes "C. x").
3. Original answer is remapped to the label of its new slot; answer_label_map records original -> new.
4. Non-mutation: input row is not modified in place.
5. Original options / answer are preserved in the shuffled row for downstream introspection.
6. unshuffle_predicted_answer reverses the mapping, passes through None and unknown labels.
7. shuffle_options rejects seed=None (must be reproducible).
"""

from __future__ import annotations

import copy

import pytest

try:
    from benchmark.runners.shuffle_options import (
        shuffle_options,
        unshuffle_predicted_answer,
    )
except ImportError:
    shuffle_options = None
    unshuffle_predicted_answer = None


def _require_implementation():
    if shuffle_options is None or unshuffle_predicted_answer is None:
        pytest.fail(
            "benchmark.runners.shuffle_options is not implemented yet; "
            "see docs/superpowers/plans/2026-07-01-phase1-evaluation-infra.md Task 1.2"
        )


_BASE_ROW = {
    "case_id": "guangdong_female_19511114_P001-Q1",
    "question": "命主家境如何?",
    "options": ["A. 富裕", "B. 贫穷", "C. 父从商母是村干部", "D. 父母当官"],
    "answer": "B",
    "domain": "family",
}


def _copy_row():
    return copy.deepcopy(_BASE_ROW)


def _strip_prefix(option_text: str) -> str:
    text = option_text.split(".", 1)
    return text[1].strip() if len(text) == 2 else option_text.strip()


def test_shuffle_options_is_deterministic_for_same_seed():
    _require_implementation()
    a = shuffle_options(_copy_row(), seed=42)
    b = shuffle_options(_copy_row(), seed=42)

    assert a["options"] == b["options"]
    assert a["answer"] == b["answer"]
    assert a["answer_label_map"] == b["answer_label_map"]


def test_shuffle_options_reorders_options_for_some_seed():
    _require_implementation()
    original = _copy_row()["options"]
    reorders = 0
    for seed in range(10):
        shuffled = shuffle_options(_copy_row(), seed=seed)
        if shuffled["options"] != original:
            reorders += 1
    assert reorders >= 1, "expected at least one seed to actually reorder"


def test_shuffle_options_relabels_prefixes_to_new_positions():
    _require_implementation()
    shuffled = shuffle_options(_copy_row(), seed=42)

    for idx, option in enumerate(shuffled["options"]):
        expected_letter = chr(ord("A") + idx)
        assert option.startswith(f"{expected_letter}. "), option

    original_texts = {_strip_prefix(opt) for opt in _BASE_ROW["options"]}
    shuffled_texts = {_strip_prefix(opt) for opt in shuffled["options"]}
    assert original_texts == shuffled_texts


def test_shuffle_options_updates_answer_and_label_map():
    _require_implementation()
    shuffled = shuffle_options(_copy_row(), seed=42)

    original_correct_text = _strip_prefix(_BASE_ROW["options"][1])
    idx_after = next(
        idx for idx, opt in enumerate(shuffled["options"])
        if _strip_prefix(opt) == original_correct_text
    )
    expected_new_label = chr(ord("A") + idx_after)

    assert shuffled["answer"] == expected_new_label
    assert shuffled["answer_label_map"]["B"] == expected_new_label
    assert set(shuffled["answer_label_map"].keys()) == {"A", "B", "C", "D"}
    assert set(shuffled["answer_label_map"].values()) == {"A", "B", "C", "D"}


def test_shuffle_options_does_not_mutate_input_row():
    _require_implementation()
    row = _copy_row()
    _ = shuffle_options(row, seed=42)

    assert row == _BASE_ROW


def test_shuffle_options_preserves_original_options_and_answer():
    _require_implementation()
    shuffled = shuffle_options(_copy_row(), seed=42)

    assert shuffled["_original_options"] == _BASE_ROW["options"]
    assert shuffled["_original_answer"] == _BASE_ROW["answer"]


def test_shuffle_options_rejects_seed_none():
    _require_implementation()
    with pytest.raises(ValueError):
        shuffle_options(_copy_row(), seed=None)


def test_unshuffle_predicted_answer_reverses_label_map():
    _require_implementation()
    shuffled = shuffle_options(_copy_row(), seed=42)
    label_map = shuffled["answer_label_map"]
    shuffled_correct_label = label_map["B"]

    assert unshuffle_predicted_answer(shuffled_correct_label, label_map) == "B"

    for original in ("A", "B", "C", "D"):
        assert (
            unshuffle_predicted_answer(label_map[original], label_map) == original
        )


def test_unshuffle_predicted_answer_passes_through_none():
    _require_implementation()
    label_map = shuffle_options(_copy_row(), seed=42)["answer_label_map"]

    assert unshuffle_predicted_answer(None, label_map) is None


def test_unshuffle_predicted_answer_passes_through_unknown_label():
    _require_implementation()
    label_map = shuffle_options(_copy_row(), seed=42)["answer_label_map"]

    assert unshuffle_predicted_answer("Z", label_map) == "Z"
    assert unshuffle_predicted_answer("", label_map) == ""
