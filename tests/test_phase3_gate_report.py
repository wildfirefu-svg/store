"""Tests for benchmark.phase3.compute_gate_report.

Verifies gate threshold checks (ITE, MMS, parser_valid, leak, 3pp advisory,
pair_analysis_eligible) and paired flip counts (using aggregated identity).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.phase3 import compute_gate_report


def _make_pred(case_id, label, identity, correct_identity,
               call_success=True, parser_valid=True, mode="on-3"):
    return {
        "case_id": case_id,
        "predicted_label": label,
        "predicted_identity": identity,
        "correct_identity": correct_identity,
        "call_success": call_success,
        "parser_valid": parser_valid,
        "mode": mode,
        "label_map": {"A": "o1", "B": "o2", "C": "o3", "D": "o4"},
        "unshuffle_success": identity is not None,
    }


@pytest.fixture
def on_preds_all_pass():
    """ITE>=23%, MMS>=80%, parser_valid>=95% (20 cases x 3 perms)."""
    preds = []
    for i in range(20):
        correct = "o1" if i < 16 else "o2"
        for perm in range(3):
            preds.append(_make_pred(f"c{i}", "A", "o1", correct, mode="on-3"))
    return preds


@pytest.fixture
def off_preds_all_pass():
    """Off-3 control matching on_preds (shuffle gap < 3pp)."""
    preds = []
    for i in range(20):
        correct = "o1" if i < 16 else "o2"
        for perm in range(3):
            preds.append(_make_pred(f"c{i}", "A", "o1", correct, mode="off-3"))
    return preds


@pytest.fixture
def on_preds_low_ite():
    """ITE < 23% (only 4/20 correct)."""
    preds = []
    for i in range(20):
        correct = "o1" if i < 4 else "o2"
        for perm in range(3):
            preds.append(_make_pred(f"c{i}", "A", "o1", correct, mode="on-3"))
    return preds


@pytest.fixture
def on_preds_low_mms():
    """MMS < 80% (3 perms disagree, MMS=0.33)."""
    preds = []
    for i in range(20):
        labels = ["A", "B", "C"]
        identities = ["o1", "o2", "o3"]
        for perm in range(3):
            preds.append(_make_pred(
                f"c{i}", labels[perm], identities[perm], "o1", mode="on-3"))
    return preds


@pytest.fixture
def on_preds_low_eligible():
    """pair_analysis_eligible_rate < 80% (half cases fail)."""
    preds = []
    for i in range(20):
        for perm in range(3):
            success = i >= 10
            preds.append(_make_pred(
                f"c{i}", "A", "o1", "o1",
                call_success=success, parser_valid=success, mode="on-3"))
    return preds


def test_gate_report_all_pass(on_preds_all_pass, off_preds_all_pass):
    report = compute_gate_report(
        on_preds_all_pass, off_preds_all_pass, confirmed_leak_count=0)
    assert report["gate_ite_28pct"] is True
    assert report["gate_mms_80pct"] is True
    assert report["gate_parser_valid_95pct"] is True
    assert report["gate_confirmed_leak_zero"] is True
    assert report["three_pp_advisory_pass"] is True


def test_gate_report_ite_below_28(on_preds_low_ite, off_preds_all_pass):
    report = compute_gate_report(on_preds_low_ite, off_preds_all_pass)
    assert report["gate_ite_28pct"] is False


def test_gate_report_mms_below_80(on_preds_low_mms, off_preds_all_pass):
    report = compute_gate_report(on_preds_low_mms, off_preds_all_pass)
    assert report["gate_mms_80pct"] is False


def test_gate_report_pair_analysis_underpowered(on_preds_low_eligible, off_preds_all_pass):
    report = compute_gate_report(on_preds_low_eligible, off_preds_all_pass)
    assert report["pair_analysis_underpowered"] is True
    assert report["pair_analysis_eligible_rate"] < 0.80


def test_gate_report_paired_flips_use_aggregated(on_preds_all_pass, off_preds_all_pass):
    """Verify paired_flip_counts receives aggregated results, not per-call."""
    report = compute_gate_report(on_preds_all_pass, off_preds_all_pass)
    assert report["off_wrong_on_right"] == 0
    assert report["off_right_on_wrong"] == 0
    assert report["both_right"] == 16
    assert report["both_wrong"] == 4


def test_gate_report_paired_flips_with_actual_flips():
    """off wrong -> on right for some cases."""
    on_preds = []
    off_preds = []
    for i in range(10):
        correct = "o1"
        on_preds.append(_make_pred(f"c{i}", "A", "o1", correct, mode="on-3"))
        on_preds.append(_make_pred(f"c{i}", "A", "o1", correct, mode="on-3"))
        on_preds.append(_make_pred(f"c{i}", "A", "o1", correct, mode="on-3"))
        # off is wrong (predicts o2)
        off_preds.append(_make_pred(f"c{i}", "B", "o2", correct, mode="off-3"))
        off_preds.append(_make_pred(f"c{i}", "B", "o2", correct, mode="off-3"))
        off_preds.append(_make_pred(f"c{i}", "B", "o2", correct, mode="off-3"))
    report = compute_gate_report(on_preds, off_preds)
    assert report["off_wrong_on_right"] == 10
    assert report["off_right_on_wrong"] == 0
    assert report["both_right"] == 0
