"""Tests for case_index.CaseIndex vector index env wiring.

Task 3.3 of the BaziQA Hybrid Stage 1 implementation plan. Locks the
three contracts on BAZI_RAG_VECTOR / BAZI_RAG_VECTOR_MODEL behaviour:

(a) BAZI_RAG_VECTOR=0  -> vector path disabled, no embeddings built.
(b) BAZI_RAG_VECTOR=1 + BAZI_RAG_VECTOR_MODEL=<available>
                       -> sentence-transformers path is taken with that model.
(c) BAZI_RAG_VECTOR=1 + BAZI_RAG_VECTOR_MODEL=nonexistent-model-xyz
                       -> graceful fallback to TF-IDF with logger.info notice.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _write_corpus(tmp_path: Path) -> Path:
    rows = [
        {
            "case_id": "c1",
            "domain": "wealth",
            "person": {"gender": "male", "birth": {"year": 1980, "month": 1, "day": 1}},
            "summary": "命主于乙未年破财",
            "facts": ["命主于乙未年破财 -> B"],
            "verified_events": {},
            "source_year": "2022",
        },
        {
            "case_id": "c2",
            "domain": "wealth",
            "person": {"gender": "female", "birth": {"year": 1990, "month": 5, "day": 12}},
            "summary": "命主性格开朗",
            "facts": ["命主性格开朗 -> A"],
            "verified_events": {},
            "source_year": "2022",
        },
    ]
    p = tmp_path / "corpus.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return p


def test_vector_index_disabled_when_env_zero(monkeypatch, tmp_path):
    from case_index import CaseIndex

    monkeypatch.setenv("BAZI_RAG_VECTOR", "0")
    monkeypatch.delenv("BAZI_RAG_VECTOR_MODEL", raising=False)

    idx = CaseIndex(_write_corpus(tmp_path))

    # When the env switch is off, neither ST nor TF-IDF embeddings are built.
    assert idx._case_embeddings is None
    assert idx._vector_model is None

    # And the public similarity score is always zeroed for every case.
    scores = idx._score_vector_similarity("命主于乙未年")
    assert scores == [0.0, 0.0]


def test_vector_index_uses_env_model_name_via_st(monkeypatch, tmp_path):
    """When BAZI_RAG_VECTOR_MODEL is set and ST loads it, the configured
    name must be forwarded to SentenceTransformer().
    """
    import case_index as ci

    monkeypatch.setenv("BAZI_RAG_VECTOR", "1")
    monkeypatch.setenv("BAZI_RAG_VECTOR_MODEL", "fake-mini-model")

    seen = {}

    class _FakeST:
        def __init__(self, name):
            seen["model_name"] = name

        def encode(self, texts, show_progress_bar=False, normalize_embeddings=True):
            arr = np.tile(np.array([[1.0, 0.0]], dtype=float), (len(texts), 1))
            return arr

    fake_module = type(sys)("sentence_transformers")
    fake_module.SentenceTransformer = _FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    idx = ci.CaseIndex(_write_corpus(tmp_path))

    assert seen["model_name"] == "fake-mini-model", (
        "CaseIndex must forward BAZI_RAG_VECTOR_MODEL to SentenceTransformer"
    )
    assert idx._vector_model is not None
    assert idx._case_embeddings is not None
    assert idx._case_embeddings.shape == (2, 2)


def test_vector_index_falls_back_to_tfidf_on_unavailable_model(monkeypatch, caplog, tmp_path):
    """An unavailable BAZI_RAG_VECTOR_MODEL must downgrade to TF-IDF and emit
    a logger.info message (Task 3.3 review #8: caplog assertion).
    """
    import case_index as ci

    monkeypatch.setenv("BAZI_RAG_VECTOR", "1")
    monkeypatch.setenv("BAZI_RAG_VECTOR_MODEL", "nonexistent-model-xyz")

    class _ExplodingST:
        def __init__(self, name):
            raise RuntimeError(f"model {name!r} not found in HF cache")

    fake_module = type(sys)("sentence_transformers")
    fake_module.SentenceTransformer = _ExplodingST
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    with caplog.at_level(logging.INFO, logger="case_index"):
        idx = ci.CaseIndex(_write_corpus(tmp_path))

    # ST path crashed: model must be None, but the TF-IDF fallback must have
    # been built (sentinel zero matrix + non-empty _tfidf_matrix).
    assert idx._vector_model is None
    assert idx._case_embeddings is not None  # TF-IDF sentinel
    assert hasattr(idx, "_tfidf_matrix") and len(idx._tfidf_matrix) == 2

    # An INFO log line must mention the fallback for operators to debug.
    fallback_log = [r for r in caplog.records if "TF-IDF fallback" in r.getMessage()]
    assert fallback_log, f"expected TF-IDF fallback log entry, got {caplog.records}"
