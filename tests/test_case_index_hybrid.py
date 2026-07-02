from __future__ import annotations

import json
from pathlib import Path

import pytest


def _tiny_corpus(tmp_path: Path) -> Path:
    path = tmp_path / "corpus.jsonl"
    lines = [
        {
            "person": {
                "person_id": "p1",
                "name": "命主一",
                "gender": "male",
                "birth": {"year": 1980, "month": 1, "day": 1},
            },
            "question": "问事业",
            "answer": "A",
            "options": ["升职", "跳槽"],
            "domain": "career",
        },
        {
            "person": {
                "person_id": "p2",
                "name": "命主二",
                "gender": "female",
                "birth": {"year": 1990, "month": 2, "day": 2},
            },
            "question": "问事业",
            "answer": "B",
            "options": ["稳定", "转行"],
            "domain": "career",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in lines) + "\n",
        encoding="utf-8",
    )
    return path


def test_option_evidence_hybrid_returns_expected_schema(tmp_path: Path) -> None:
    from case_index import CaseIndex

    corpus = _tiny_corpus(tmp_path)
    index = CaseIndex(corpus)
    features = {
        "text_blob": "问事业",
        "structured": {"query_domain": "career", "query_text": "问事业"},
    }
    evidence = index.option_evidence(
        features,
        question="问事业",
        options=["A. 升职", "B. 跳槽", "C. 稳定", "D. 转行"],
        domain="career",
        k_per_option=1,
        retrieval_mode="option_grounded_hybrid",
    )
    for label in ["A", "B", "C", "D"]:
        assert label in evidence
        assert isinstance(evidence[label], list)
        for item in evidence[label]:
            assert "person_id" in item
            assert "fact_excerpt" in item
            assert "score" in item


def test_option_evidence_legacy_mode_unchanged(tmp_path: Path) -> None:
    from case_index import CaseIndex

    corpus = _tiny_corpus(tmp_path)
    index = CaseIndex(corpus)
    features = {
        "text_blob": "问事业",
        "structured": {"query_domain": "career", "query_text": "问事业"},
    }
    evidence = index.option_evidence(
        features,
        question="问事业",
        options=["A. 升职", "B. 跳槽", "C. 稳定", "D. 转行"],
        domain="career",
        k_per_option=1,
        retrieval_mode="option_grounded",
    )
    assert "A" in evidence
