"""Tests for Phase 3 offline pipeline trace (Task 15).

Validates the full data flow without API calls:
  split -> permutation plan -> prompt render -> mock answer -> parse ->
  unshuffle -> aggregate -> report
"""

from __future__ import annotations

import pytest

from benchmark.phase3 import run_pipeline_trace


def test_pipeline_trace_returns_all_stages():
    trace = run_pipeline_trace(num_cases=3)
    expected_stages = ["split", "permutation_plan", "prompt_render", "mock_answer", "parse", "unshuffle", "aggregate", "report"]
    assert list(trace.keys()) == expected_stages


def test_pipeline_trace_split_count():
    trace = run_pipeline_trace(num_cases=4)
    assert len(trace["split"]) == 4


def test_pipeline_trace_permutation_plan_has_three_perms_per_case():
    trace = run_pipeline_trace(num_cases=2)
    for case in trace["permutation_plan"]:
        assert len(case["permutations"]) == 3


def test_pipeline_trace_prompt_render_has_label_map():
    trace = run_pipeline_trace(num_cases=2)
    for entry in trace["prompt_render"]:
        assert "label_map" in entry
        assert "rendered" in entry


def test_pipeline_trace_mock_answer_valid_label():
    trace = run_pipeline_trace(num_cases=2)
    for ans in trace["mock_answer"]:
        assert ans["predicted_label"] in {"A", "B", "C", "D"}


def test_pipeline_trace_parse_returns_identity():
    trace = run_pipeline_trace(num_cases=2)
    for p in trace["parse"]:
        assert p["identity"] in {"o1", "o2", "o3", "o4"}


def test_pipeline_trace_aggregate_has_final_identity():
    trace = run_pipeline_trace(num_cases=2)
    for case_id, result in trace["aggregate"].items():
        assert "final_identity" in result
        assert "tie" in result


def test_pipeline_trace_report_has_metrics():
    trace = run_pipeline_trace(num_cases=5)
    report = trace["report"]
    assert "ite_accuracy" in report
    assert "success_only_accuracy" in report
    assert "failure_rate" in report
    assert "mean_majority_share" in report
    assert "position_selection_frequency" in report


def test_pipeline_trace_no_api_calls():
    """The trace must not make any external calls — it uses mock data only."""
    trace = run_pipeline_trace(num_cases=3)
    assert trace["report"]["failure_rate"] == 0.0
