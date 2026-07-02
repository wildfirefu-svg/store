from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest


def _ensure_fake_sentence_transformers() -> None:
    """Inject a lightweight sentence-transformers mock if not present.

    This keeps the unit tests fast and deterministic even when the real
    ``sentence-transformers`` package is not installed in the environment.
    """
    if "sentence_transformers" in sys.modules:
        return

    class _FakeSentenceTransformer:
        def __init__(self, model_name: str):
            self.model_name = model_name

        def encode(self, sentences, **kwargs):
            # Match the expected dimensions for the two models used in tests.
            dim = 512 if "bge-small-zh" in self.model_name else 384
            rng = np.random.default_rng(42)
            arr = rng.random((len(sentences), dim)).astype(np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            return arr / np.maximum(norms, 1e-12)

    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = _FakeSentenceTransformer
    sys.modules["sentence_transformers"] = mod


@pytest.fixture(autouse=True)
def _inject_fake_st():
    _ensure_fake_sentence_transformers()
    yield


def test_encode_cases_returns_normalized_vectors():
    from case_dense_index import encode_cases

    rows = [
        {"person_id": "p1", "text_blob": "丁火日主身弱财星旺"},
        {"person_id": "p2", "text_blob": "甲木日主身强官杀混杂"},
    ]
    embeddings = encode_cases(
        rows,
        model_name="sentence-transformers/all-MiniLM-L6-v2",
    )
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (2, 384)
    norms = np.linalg.norm(embeddings, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_cache_roundtrip(tmp_path: Path) -> None:
    from case_dense_index import load_dense_cache, save_dense_cache

    cache_path = tmp_path / "dense.pkl"
    rows = [{"person_id": "p1", "text_blob": "xxx"}]
    embeddings = np.zeros((1, 512), dtype=np.float32)
    save_dense_cache(cache_path, rows, embeddings, model_name="m")
    loaded_rows, loaded_embs, loaded_model = load_dense_cache(cache_path)
    assert loaded_rows == rows
    assert np.allclose(loaded_embs, embeddings)
    assert loaded_model == "m"


def test_cache_invalidated_on_model_change(tmp_path: Path) -> None:
    from case_dense_index import is_cache_valid, save_dense_cache

    cache_path = tmp_path / "dense.pkl"
    save_dense_cache(
        cache_path,
        [],
        np.zeros((0, 512), dtype=np.float32),
        model_name="old",
    )
    assert (
        is_cache_valid(
            cache_path,
            corpus_path=tmp_path / "corpus.jsonl",
            model_name="new",
        )
        is False
    )


def _write_fake_sentence_transformers_package(tmp_path: Path) -> Path:
    """Create an importable fake sentence_transformers module for subprocess tests."""
    pkg_dir = tmp_path / "fake_st"
    pkg_dir.mkdir()
    code = '''
import numpy as np

class SentenceTransformer:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def encode(self, sentences, **kwargs):
        dim = 512 if "bge-small-zh" in self.model_name else 384
        rng = np.random.default_rng(7)
        arr = rng.random((len(sentences), dim)).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / np.maximum(norms, 1e-12)
'''
    (pkg_dir / "sentence_transformers.py").write_text(code, encoding="utf-8")
    return pkg_dir


def test_build_dense_index_cli_writes_cache(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps(
            {"person_id": "p1", "text_blob": "丁火日主"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    cache = tmp_path / "dense.pkl"
    fake_pkg = _write_fake_sentence_transformers_package(tmp_path)

    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(fake_pkg) + (os.pathsep + pythonpath if pythonpath else "")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_dense_index.py",
            "--corpus",
            str(corpus),
            "--cache",
            str(cache),
            "--model",
            "sentence-transformers/all-MiniLM-L6-v2",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert cache.exists()
