"""Tests for classic distillation validator gates."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from scripts.validate_classic_distillation import validate_book

RULE_REQUIRED = {"id", "category", "subject", "condition", "rule", "original_text",
                 "source_book", "source_chapter"}
MCQ_REQUIRED = {"id", "question", "options", "answer", "explanation",
                "source_rule_id", "difficulty", "category"}


def _make_full_rule(id: str, chapter: str, rule_text: str, original_text: str = "") -> dict:
    return {
        "id": id,
        "category": "test",
        "subject": "test",
        "condition": "test",
        "rule": rule_text,
        "original_text": original_text or rule_text,
        "source_book": "test",
        "source_chapter": chapter,
    }


def _make_full_mcq(id: str, question: str, answer: str, source_rule_id: str) -> dict:
    return {
        "id": id,
        "question": question,
        "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
        "answer": answer,
        "explanation": "test",
        "source_rule_id": source_rule_id,
        "difficulty": "easy",
        "category": "test",
    }


def _setup_book(
    tmp_path: Path,
    rules: list[dict],
    mcqs: list[dict],
    raw_text: str = "原文",
) -> Path:
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text(
        json.dumps(rules, ensure_ascii=False), encoding="utf-8"
    )
    (book_dir / "all_mcq.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mcqs),
        encoding="utf-8",
    )
    (book_dir / "raw_001.txt").write_text(raw_text, encoding="utf-8")
    return book_dir


def _validate(tmp_path: Path, rules: list[dict], mcqs: list[dict], raw_text: str = "原文") -> dict:
    _setup_book(tmp_path, rules, mcqs, raw_text)
    return validate_book("testbook", "测试书", base_path=tmp_path)


def test_g9_passes_when_no_duplicates(tmp_path):
    rules = [
        _make_full_rule("r1", "ch1", "甲木参天", "甲木参天"),
        _make_full_rule("r2", "ch1", "乙木系甲", "乙木系甲"),
    ]
    mcqs = [
        _make_full_mcq("m1", "问题一", "A", "r1"),
        _make_full_mcq("m2", "问题二", "B", "r2"),
    ]
    report = _validate(tmp_path, rules, mcqs, raw_text="甲木参天乙木系甲")
    g9 = report["gates"]["G9_content_dedup"]
    assert g9["pass"]


def test_g9_fails_on_cross_chapter_duplicate(tmp_path):
    """G9 must flag same rule text in different chapters (global, not just within-chapter)."""
    rules = [
        _make_full_rule("r1", "ch1", "甲木参天", "甲木参天"),
        _make_full_rule("r2", "ch2", "甲木参天", "甲木参天"),
    ]
    mcqs: list[dict] = []
    report = _validate(tmp_path, rules, mcqs, raw_text="甲木参天")
    g9 = report["gates"]["G9_content_dedup"]
    assert not g9["pass"]
    assert g9["rule_text_duplicate_groups"] == 1
    assert g9["rule_text_duplicate_count"] == 1


def test_g9_fails_on_within_chapter_duplicate(tmp_path):
    rules = [
        _make_full_rule("r1", "ch1", "甲木参天", "甲木参天"),
        _make_full_rule("r2", "ch1", "甲木参天", "甲木参天"),
    ]
    mcqs: list[dict] = []
    report = _validate(tmp_path, rules, mcqs, raw_text="甲木参天")
    g9 = report["gates"]["G9_content_dedup"]
    assert not g9["pass"]


def test_g9_normalizes_whitespace(tmp_path):
    """G9 normalizes whitespace before comparing rule texts."""
    rules = [
        _make_full_rule("r1", "ch1", "甲 木 参 天", "甲木参天"),
        _make_full_rule("r2", "ch2", "甲木参天", "甲木参天"),
    ]
    mcqs: list[dict] = []
    report = _validate(tmp_path, rules, mcqs, raw_text="甲木参天")
    g9 = report["gates"]["G9_content_dedup"]
    assert not g9["pass"]


def test_g9_fails_on_duplicate_mcq_questions(tmp_path):
    rules = [_make_full_rule("r1", "ch1", "甲木参天", "甲木参天")]
    mcqs = [
        _make_full_mcq("m1", "相同问题", "A", "r1"),
        _make_full_mcq("m2", "相同问题", "B", "r1"),
    ]
    report = _validate(tmp_path, rules, mcqs, raw_text="甲木参天")
    g9 = report["gates"]["G9_content_dedup"]
    assert not g9["pass"]
    assert g9["mcq_question_duplicates"] == 1


def test_g9_passes_with_canonical_source_chapters(tmp_path):
    """A single canonical rule with source_chapters should not trigger G9."""
    rule = _make_full_rule("r1", "ch1", "甲木参天", "甲木参天")
    rule["source_chapters"] = ["ch1", "ch2", "ch3"]
    rules = [rule, _make_full_rule("r2", "ch1", "乙木系甲", "乙木系甲")]
    mcqs: list[dict] = []
    report = _validate(tmp_path, rules, mcqs, raw_text="甲木参天乙木系甲")
    g9 = report["gates"]["G9_content_dedup"]
    assert g9["pass"]


# ---------------------------------------------------------------------------
# Stage 1: apply_exemption (E -> R -> B1 chain)
# ---------------------------------------------------------------------------
from scripts.validate_classic_distillation import apply_exemption


def test_apply_exemption_exempts_listed_checks_only():
    issues = {"missing_upstream_response_body": ["1"], "artifact_integrity": ["2"]}
    e = {"book": "sanmingtonghui", "baseline_commit": "a" * 40, "artifact_manifest_sha256": "b" * 64,
         "validator_code_sha256": "c" * 64, "exempted_checks": ["missing_upstream_response_body"],
         "non_exempt_checks": ["artifact_integrity", "quality_gates", "future_generation_provenance"],
         "author": "r", "date": "2026-08-13"}
    out = apply_exemption(issues, e)
    assert out["missing_upstream_response_body"] == "exempted"
    assert out["artifact_integrity"] == ["2"]  # 非豁免门保持原样


def test_apply_exemption_rejects_malformed_request():
    issues = {"missing_upstream_response_body": ["1"]}
    e = {"book": "sanmingtonghui"}  # 缺必需字段
    with pytest.raises(ValueError, match="missing"):
        apply_exemption(issues, e)