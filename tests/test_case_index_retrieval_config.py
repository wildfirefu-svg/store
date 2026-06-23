"""Tests for case_index.load_retrieval_config.

Task 3.2 of the BaziQA Hybrid Stage 1 implementation plan. Locks the
contract that the retrieval config loader resolves config ids defined in
``benchmark/configs/baziqa_retrieval_configs.yaml`` and that it surfaces
clear errors when a caller asks for a missing config.
"""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _write_fixture(tmp_path: Path) -> Path:
    """Write a 5-row retrieval config fixture mirroring the production YAML."""
    path = tmp_path / "baziqa_retrieval_configs.yaml"
    path.write_text(
        dedent(
            """
            - id: bm25
              bm25: true
              structured: false
              semantic: false
              tfidf_vector: false
              embedding_vector: false
              embedding_model: ""

            - id: structured
              bm25: true
              structured: true
              semantic: false
              tfidf_vector: false
              embedding_vector: false
              embedding_model: ""

            - id: semantic
              bm25: true
              structured: true
              semantic: true
              tfidf_vector: false
              embedding_vector: false
              embedding_model: ""

            - id: tfidf_vector
              bm25: true
              structured: true
              semantic: true
              tfidf_vector: true
              embedding_vector: false
              embedding_model: ""

            - id: embedding_vector
              bm25: true
              structured: true
              semantic: true
              tfidf_vector: false
              embedding_vector: true
              embedding_model: "bge-zh-base"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "config_id, expected",
    [
        ("bm25", {"bm25": True, "structured": False, "embedding_vector": False, "embedding_model": ""}),
        ("structured", {"bm25": True, "structured": True, "semantic": False, "embedding_vector": False}),
        ("semantic", {"semantic": True, "tfidf_vector": False, "embedding_vector": False}),
        ("tfidf_vector", {"tfidf_vector": True, "embedding_vector": False}),
        ("embedding_vector", {"embedding_vector": True, "embedding_model": "bge-zh-base"}),
    ],
)
def test_load_retrieval_config_returns_each_known_id(tmp_path, config_id, expected):
    from case_index import load_retrieval_config

    fixture = _write_fixture(tmp_path)
    cfg = load_retrieval_config(config_id, path=fixture)

    assert cfg["id"] == config_id
    for key, value in expected.items():
        assert cfg[key] == value, (config_id, key, cfg)


def test_load_retrieval_config_raises_for_unknown_id(tmp_path):
    from case_index import load_retrieval_config

    fixture = _write_fixture(tmp_path)
    with pytest.raises(KeyError) as excinfo:
        load_retrieval_config("does_not_exist", path=fixture)

    msg = str(excinfo.value)
    assert "does_not_exist" in msg
    assert "bm25" in msg  # error message must list available ids for fast debugging


def test_load_retrieval_config_defaults_to_repo_yaml(monkeypatch):
    """Without an explicit path, the loader must resolve the production YAML
    under benchmark/configs/baziqa_retrieval_configs.yaml.
    """
    from case_index import load_retrieval_config

    cfg = load_retrieval_config("embedding_vector")
    assert cfg["id"] == "embedding_vector"
    assert cfg["embedding_vector"] is True
    assert cfg["embedding_model"] == "bge-zh-base"


def test_load_retrieval_config_rejects_malformed_yaml(tmp_path):
    from case_index import load_retrieval_config

    bad = tmp_path / "bad.yaml"
    bad.write_text("not: [a list of dicts", encoding="utf-8")

    with pytest.raises(Exception):
        load_retrieval_config("bm25", path=bad)
