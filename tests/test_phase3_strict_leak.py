"""Tests for Phase 3 strict leak detection (Task 10).

Distinguishes auto-detected leak candidates from human-confirmed leaks.
option-grounded retrieval legitimately uses option text, so an auto-hit is
NOT automatically a confirmed leak.
"""

from __future__ import annotations

from benchmark.phase3 import char_overlap_ratio, detect_leak_candidates, normalize_text


def test_normalize_text_strips_whitespace_and_lowercases():
    assert normalize_text("  Hello World  ") == "helloworld"


def test_char_overlap_identical():
    assert char_overlap_ratio("abc", "abc") == 1.0


def test_char_overlap_disjoint():
    assert char_overlap_ratio("xyz", "abc") < 0.3


def test_answer_text_appears_in_evidence_is_candidate():
    evidence = ["命主财运亨通，正财稳中有升", "其他无关文本"]
    candidates = detect_leak_candidates(
        evidence_texts=evidence,
        answer_text="正财稳中有升",
        answer_label="A",
        case_id="case_2024_001",
        holdout_case_ids=set(),
    )
    assert len(candidates) == 1
    assert candidates[0]["evidence_index"] == 0
    assert "answer_text_appears" in candidates[0]["reasons"]


def test_case_id_appears_in_evidence_is_candidate():
    evidence = ["参考 case_2024_001 的解析", "其他"]
    candidates = detect_leak_candidates(
        evidence_texts=evidence,
        answer_text="无关答案",
        answer_label="A",
        case_id="case_2024_001",
        holdout_case_ids={"case_2024_001"},
    )
    assert len(candidates) == 1
    assert "case_id_appears" in candidates[0]["reasons"]


def test_high_overlap_is_candidate():
    evidence = ["命主正财稳中有升偏财平淡，事业内部晋升"]
    candidates = detect_leak_candidates(
        evidence_texts=evidence,
        answer_text="正财稳中有升偏财平淡事业内部晋升",
        answer_label="A",
        case_id="case_x",
        holdout_case_ids=set(),
    )
    assert len(candidates) >= 1


def test_no_leak_returns_empty():
    evidence = ["命主日主身强，官星得地，利于职场发展", "财星生扶，无明显破耗"]
    candidates = detect_leak_candidates(
        evidence_texts=evidence,
        answer_text="肝胆筋骨需注意",
        answer_label="C",
        case_id="case_y",
        holdout_case_ids=set(),
    )
    assert candidates == []


def test_leak_candidate_not_confirmed():
    """detect_leak_candidates only returns candidates; confirmation is manual."""
    evidence = ["正财稳中有升"]
    candidates = detect_leak_candidates(
        evidence_texts=evidence,
        answer_text="正财稳中有升",
        answer_label="A",
        case_id="case_z",
        holdout_case_ids=set(),
    )
    assert len(candidates) == 1
    # confirmed_leak_count is NOT produced by auto-detection
    assert "confirmed" not in candidates[0]
