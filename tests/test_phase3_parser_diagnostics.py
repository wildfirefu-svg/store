"""Tests for Phase 3 parser failure diagnostics.

Task 7 of the Phase 3 implementation plan. The classifier distinguishes API
failures from position-bias-related parse failures so that failure rate does
not contaminate position-bias analysis.
"""

from __future__ import annotations

from benchmark.phase3 import classify_parser_failure


def test_model_call_failed():
    assert classify_parser_failure("", None, False, None, call_success=False) == "model_call_failed"


def test_empty_raw_answer():
    assert classify_parser_failure("", None, False, None) == "empty_raw_answer"
    assert classify_parser_failure(None, None, False, None) == "empty_raw_answer"
    assert classify_parser_failure("   ", None, False, None) == "empty_raw_answer"


def test_parser_invalid_format():
    assert classify_parser_failure("无法判断", None, False, None) == "parser_invalid"


def test_label_out_of_range():
    assert classify_parser_failure("答案：E", "E", False, None) == "label_out_of_range"


def test_unshuffle_map_failed_empty_map():
    """valid=True but shuffle label_map is empty -> cannot unshuffle."""
    assert classify_parser_failure("答案：A", "A", True, {}) == "unshuffle_map_failed"


def test_unshuffle_map_failed_missing_label():
    """valid=True, label_map present but predicted label not in map."""
    label_map = {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}
    assert classify_parser_failure("答案：Z", "Z", True, label_map) == "unshuffle_map_failed"


def test_success_returns_none():
    label_map = {"o1": "A", "o2": "B", "o3": "C", "o4": "D"}
    assert classify_parser_failure("答案：B", "B", True, label_map) is None


def test_non_shuffle_success_returns_none():
    """Non-shuffle mode (label_map=None) with valid parse returns None."""
    assert classify_parser_failure("答案：A", "A", True, None) is None


def test_model_call_failed_takes_priority():
    """Even with empty raw_answer, call_success=False means model_call_failed."""
    assert classify_parser_failure("", None, False, None, call_success=False) == "model_call_failed"


def test_empty_takes_priority_over_invalid():
    """Empty raw_answer is more specific than parser_invalid."""
    assert classify_parser_failure("", None, False, None) == "empty_raw_answer"
