"""Tests for Phase 3 runner matrix: permutation plan, aggregation, consistency.

Task 6/8/9 of the Phase 3 implementation plan. Pure function-level tests.
"""

from __future__ import annotations

import pytest

from benchmark.phase3 import (
    aggregate_by_option_identity,
    build_permutation_plan,
    mean_majority_share,
    pairwise_identity_agreement,
    to_original_option_identity,
    unanimous_case_rate,
)

# ---------------------------------------------------------------------------
# Task 6: shared cyclic permutation plan
# ---------------------------------------------------------------------------

def test_permutation_plan_returns_three_perms():
    plan = build_permutation_plan(["o1", "o2", "o3", "o4"])
    assert len(plan) == 3


def test_permutation_ids_are_distinct():
    plan = build_permutation_plan(["o1", "o2", "o3", "o4"])
    ids = {p["permutation_id"] for p in plan}
    assert len(ids) == 3


def test_each_option_covers_three_positions():
    plan = build_permutation_plan(["o1", "o2", "o3", "o4"])
    positions = {opt: set() for opt in ["o1", "o2", "o3", "o4"]}
    for p in plan:
        for label, opt in p["label_map_inv"].items():
            positions[opt].add(label)
    for opt, covered in positions.items():
        assert len(covered) == 3, f"{opt} only covers {covered}"


def test_permutation_plan_does_not_read_answer():
    """build_permutation_plan must accept only option_ids, no answer."""
    import inspect
    sig = inspect.signature(build_permutation_plan)
    params = list(sig.parameters.keys())
    assert "answer" not in params
    assert "is_answer" not in params
    assert "correct" not in params


def test_permutation_plan_reproducible():
    p1 = build_permutation_plan(["a", "b", "c", "d"])
    p2 = build_permutation_plan(["a", "b", "c", "d"])
    assert p1 == p2


def test_permutation_plan_rejects_non_four_options():
    with pytest.raises(ValueError):
        build_permutation_plan(["o1", "o2", "o3"])
    with pytest.raises(ValueError):
        build_permutation_plan(["o1", "o2", "o3", "o4", "o5"])


def test_permutation_label_map_correct():
    plan = build_permutation_plan(["o1", "o2", "o3", "o4"])
    # permutation 0: display order o1,o2,o3,o4 -> A,B,C,D
    assert plan[0]["label_map"]["o1"] == "A"
    assert plan[0]["label_map"]["o4"] == "D"
    # permutation 1: display order o2,o3,o4,o1 -> A,B,C,D
    assert plan[1]["label_map"]["o2"] == "A"
    assert plan[1]["label_map"]["o1"] == "D"


# ---------------------------------------------------------------------------
# Task 8: option identity aggregation
# ---------------------------------------------------------------------------

def test_to_original_option_identity_basic():
    label_map = {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}
    assert to_original_option_identity("A", label_map) == "o1"
    assert to_original_option_identity("C", label_map) == "o3"


def test_to_original_option_identity_missing_label():
    label_map = {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}
    assert to_original_option_identity("E", label_map) is None


def test_aggregate_by_identity_majority():
    predictions = [
        {"case_id": "c1", "permutation_id": "p1", "predicted_label": "A", "label_map": {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p2", "predicted_label": "D", "label_map": {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p3", "predicted_label": "C", "label_map": {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}, "call_success": True},
    ]
    # predicted identities: o1, o1, o1 -> majority o1
    result = aggregate_by_option_identity(predictions)
    assert result["c1"]["final_identity"] == "o1"
    assert result["c1"]["tie"] is False


def test_aggregate_excludes_failed_calls():
    predictions = [
        {"case_id": "c1", "permutation_id": "p1", "predicted_label": "A", "label_map": {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p2", "predicted_label": None, "label_map": {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}, "call_success": False},
        {"case_id": "c1", "permutation_id": "p3", "predicted_label": "C", "label_map": {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}, "call_success": True},
    ]
    result = aggregate_by_option_identity(predictions)
    # only 2 successful: o1, o1 -> majority o1
    assert result["c1"]["final_identity"] == "o1"
    assert result["c1"]["successful_predictions"] == 2


def test_aggregate_tie_recorded():
    predictions = [
        {"case_id": "c1", "permutation_id": "p1", "predicted_label": "A", "label_map": {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p2", "predicted_label": "B", "label_map": {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}, "call_success": True},
    ]
    result = aggregate_by_option_identity(predictions)
    # o1 vs o3 (1 each) -> tie
    assert result["c1"]["tie"] is True


# ---------------------------------------------------------------------------
# Task 9: consistency metrics
# ---------------------------------------------------------------------------

def test_mean_majority_share_unanimous():
    predictions = [
        {"case_id": "c1", "permutation_id": "p1", "predicted_label": "A", "label_map": {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p2", "predicted_label": "D", "label_map": {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p3", "predicted_label": "C", "label_map": {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}, "call_success": True},
    ]
    # all three predict o1 -> majority share 1.0
    assert mean_majority_share(predictions) == pytest.approx(1.0)


def test_mean_majority_share_two_of_three():
    predictions = [
        {"case_id": "c1", "permutation_id": "p1", "predicted_label": "A", "label_map": {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p2", "predicted_label": "D", "label_map": {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p3", "predicted_label": "A", "label_map": {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}, "call_success": True},
    ]
    # identities: o1, o1, o2 -> majority o1 share 2/3
    assert mean_majority_share(predictions) == pytest.approx(2 / 3)


def test_unanimous_case_rate():
    predictions = [
        {"case_id": "c1", "permutation_id": "p1", "predicted_label": "A", "label_map": {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p2", "predicted_label": "D", "label_map": {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p3", "predicted_label": "C", "label_map": {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}, "call_success": True},
        {"case_id": "c2", "permutation_id": "p1", "predicted_label": "A", "label_map": {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}, "call_success": True},
        {"case_id": "c2", "permutation_id": "p2", "predicted_label": "B", "label_map": {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}, "call_success": True},
        {"case_id": "c2", "permutation_id": "p3", "predicted_label": "C", "label_map": {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}, "call_success": True},
    ]
    # c1 unanimous (all o1), c2 split (o1,o3,o1) -> not unanimous
    # wait c2: A->o1, B->o3, C->o1 -> o1,o3,o1 -> not unanimous
    assert unanimous_case_rate(predictions) == pytest.approx(0.5)


def test_pairwise_identity_agreement():
    predictions = [
        {"case_id": "c1", "permutation_id": "p1", "predicted_label": "A", "label_map": {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p2", "predicted_label": "D", "label_map": {"o2": "A", "o3": "B", "o4": "C", "o1": "D"}, "call_success": True},
        {"case_id": "c1", "permutation_id": "p3", "predicted_label": "C", "label_map": {"o3": "A", "o4": "B", "o1": "C", "o2": "D"}, "call_success": True},
    ]
    # all three o1 -> 3 pairs all agree -> 1.0
    assert pairwise_identity_agreement(predictions) == pytest.approx(1.0)
