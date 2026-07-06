"""Tests for Phase 3 report aggregation and budget hard cap (Task 12 + 14).

Task 12: paired statistics (ITE accuracy, success-only, McNemar-like flip
counts, position frequency, pair_analysis_eligible_rate).
Task 14: budget hard cap enforcement.
"""

from __future__ import annotations

import pytest

from benchmark.phase3 import (
    compute_ite_accuracy,
    compute_success_only_accuracy,
    compute_failure_rate,
    paired_flip_counts,
    position_selection_frequency,
    pair_analysis_eligible_rate,
    check_hard_cap,
)


def _pred(case_id, perm_id, label, label_map, success=True, correct_identity=None):
    return {
        "case_id": case_id,
        "permutation_id": perm_id,
        "predicted_label": label,
        "label_map": label_map,
        "call_success": success,
        "correct_identity": correct_identity,
    }


LM1 = {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}
LM2 = {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}


# ---- Task 12: accuracy metrics ----

def test_ite_accuracy_counts_failures_as_wrong():
    preds = [
        _pred("c1", "p1", "A", LM1, success=True, correct_identity="o1"),
        _pred("c2", "p1", None, LM1, success=False),
    ]
    assert compute_ite_accuracy(preds) == 0.5


def test_success_only_accuracy_excludes_failures():
    preds = [
        _pred("c1", "p1", "A", LM1, success=True, correct_identity="o1"),
        _pred("c2", "p1", None, LM1, success=False),
    ]
    assert compute_success_only_accuracy(preds) == 1.0


def test_ite_accuracy_majority_vote_correct():
    """2/3 permutations agree on correct identity → case is correct."""
    # LM1: o1→A, o2→B, o3→C, o4→D
    # LM2 (cyclic shift): o2→A, o3→B, o4→C, o1→D
    # LM3 (cyclic shift): o3→A, o4→B, o1→C, o2→D
    LM3 = {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}
    preds = [
        _pred("c1", "p1", "A", LM1, success=True, correct_identity="o1"),  # A→o1 ✓
        _pred("c1", "p2", "D", LM2, success=True, correct_identity="o1"),  # D→o1 ✓
        _pred("c1", "p3", "A", LM3, success=True, correct_identity="o1"),  # A→o3 ✗
    ]
    # majority: o1 (2 votes) → matches correct_identity o1 → correct
    assert compute_ite_accuracy(preds) == 1.0


def test_ite_accuracy_only_one_perm_correct_is_wrong():
    """Only 1/3 permutations correct → majority disagrees → case is wrong.
    This is the regression test for the old 'any-perm-correct' bug."""
    LM3 = {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}
    preds = [
        _pred("c1", "p1", "A", LM1, success=True, correct_identity="o1"),  # A→o1 ✓
        _pred("c1", "p2", "A", LM2, success=True, correct_identity="o1"),  # A→o2 ✗
        _pred("c1", "p3", "B", LM3, success=True, correct_identity="o1"),  # B→o4 ✗
    ]
    # majority: o2 (1 vote each, tie-broken to o2 alphabetically) → ≠ o1 → wrong
    assert compute_ite_accuracy(preds) == 0.0


def test_ite_accuracy_tie_is_wrong():
    """2/4 permutations tied between two identities → tie → wrong."""
    LM3 = {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}
    LM4 = {"o4": "A", "o1": "B", "o2": "C", "o3": "D"}
    preds = [
        _pred("c1", "p1", "A", LM1, success=True, correct_identity="o1"),  # A→o1
        _pred("c1", "p2", "A", LM2, success=True, correct_identity="o1"),  # A→o2
        _pred("c1", "p3", "A", LM3, success=True, correct_identity="o1"),  # A→o3
        _pred("c1", "p4", "A", LM4, success=True, correct_identity="o1"),  # A→o4
    ]
    # all different, 4-way tie → tie=True → wrong
    assert compute_ite_accuracy(preds) == 0.0


def test_ite_accuracy_missing_correct_identity_is_wrong():
    """Case without correct_identity field → wrong."""
    preds = [
        _pred("c1", "p1", "A", LM1, success=True, correct_identity="o1"),
        _pred("c2", "p1", "A", LM1, success=True),  # no correct_identity
    ]
    assert compute_ite_accuracy(preds) == 0.5  # c1 correct, c2 no correct_identity → wrong


def test_success_only_majority_vote():
    """Success-only: majority voted, failure cases excluded."""
    LM3 = {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}
    preds = [
        _pred("c1", "p1", "A", LM1, success=True, correct_identity="o1"),  # ✓
        _pred("c1", "p2", "D", LM2, success=True, correct_identity="o1"),  # ✓
        _pred("c1", "p3", "B", LM3, success=True, correct_identity="o1"),  # ✗ (B→o4)
        _pred("c2", "p1", None, LM1, success=False, correct_identity="o1"),  # failed
    ]
    # c1: majority o1 (2/3) → correct. c2 excluded (failed).
    assert compute_success_only_accuracy(preds) == 1.0


def test_failure_rate():
    preds = [
        _pred("c1", "p1", "A", LM1, success=True),
        _pred("c2", "p1", None, LM1, success=False),
        _pred("c3", "p1", "B", LM1, success=True),
    ]
    assert compute_failure_rate(preds) == pytest.approx(1 / 3)


# ---- Task 12: paired flip counts ----

def test_paired_flip_counts():
    """off predicts wrong, on predicts right -> positive flip."""
    off = [
        {"case_id": "c1", "predicted_identity": "o2", "correct_identity": "o1", "eligible": True},
        {"case_id": "c2", "predicted_identity": "o1", "correct_identity": "o1", "eligible": True},
    ]
    on = [
        {"case_id": "c1", "predicted_identity": "o1", "correct_identity": "o1", "eligible": True},
        {"case_id": "c2", "predicted_identity": "o2", "correct_identity": "o1", "eligible": True},
    ]
    flips = paired_flip_counts(off, on)
    assert flips["off_wrong_on_right"] == 1
    assert flips["off_right_on_wrong"] == 1
    assert flips["both_right"] == 0
    assert flips["both_wrong"] == 0


def test_paired_flip_excludes_ineligible():
    off = [
        {"case_id": "c1", "predicted_identity": "o2", "correct_identity": "o1", "eligible": False},
    ]
    on = [
        {"case_id": "c1", "predicted_identity": "o1", "correct_identity": "o1", "eligible": True},
    ]
    flips = paired_flip_counts(off, on)
    assert flips["off_wrong_on_right"] == 0
    assert flips["excluded_due_ineligible"] == 1


# ---- Task 12: position frequency ----

def test_position_selection_frequency():
    preds = [
        _pred("c1", "p1", "A", LM1),
        _pred("c2", "p1", "A", LM1),
        _pred("c3", "p1", "B", LM1),
        _pred("c4", "p1", "C", LM1),
    ]
    freq = position_selection_frequency(preds)
    assert freq["A"] == 2
    assert freq["B"] == 1
    assert freq["C"] == 1
    assert freq["D"] == 0


# ---- Task 12: pair analysis eligibility ----

def test_pair_analysis_eligible_rate():
    preds = [
        {"case_id": "c1", "call_success": True, "parser_valid": True, "unshuffle_success": True, "mode": "off-3"},
        {"case_id": "c1", "call_success": True, "parser_valid": True, "unshuffle_success": True, "mode": "on-3"},
        {"case_id": "c2", "call_success": False, "parser_valid": False, "unshuffle_success": False, "mode": "off-3"},
        {"case_id": "c2", "call_success": True, "parser_valid": True, "unshuffle_success": True, "mode": "on-3"},
    ]
    rate = pair_analysis_eligible_rate(preds)
    # c1 eligible (both success), c2 not (off failed) -> 1/2 = 0.5
    assert rate == pytest.approx(0.5)


def test_pair_analysis_underpowered_flag():
    """When eligible_rate < 0.80, flag as underpowered."""
    preds = [
        {"case_id": "c1", "call_success": True, "parser_valid": True, "unshuffle_success": True, "mode": "off-3"},
        {"case_id": "c1", "call_success": True, "parser_valid": True, "unshuffle_success": True, "mode": "on-3"},
        {"case_id": "c2", "call_success": False, "parser_valid": False, "unshuffle_success": False, "mode": "off-3"},
        {"case_id": "c2", "call_success": True, "parser_valid": True, "unshuffle_success": True, "mode": "on-3"},
    ]
    rate = pair_analysis_eligible_rate(preds)
    assert rate < 0.80


# ---- Task 14: hard cap ----

def test_hard_cap_not_reached():
    result = check_hard_cap(actual_calls=100, hard_cap=174)
    assert result["cap_reached"] is False
    assert result["remaining"] == 74


def test_hard_cap_reached():
    result = check_hard_cap(actual_calls=174, hard_cap=174)
    assert result["cap_reached"] is True
    assert result["remaining"] == 0


def test_hard_cap_exceeded():
    result = check_hard_cap(actual_calls=200, hard_cap=174)
    assert result["cap_reached"] is True
    assert result["remaining"] == 0
