"""Dense vector index for BaziQA corpus cases.

Encodes a corpus of cases into normalized dense embeddings and persists them
to a versioned pickle cache.  The cache is invalidated automatically when the
underlying corpus file or the embedding model changes.
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
CACHE_VERSION = 1


def encode_cases(
    cases: List[Dict[str, Any]],
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
) -> np.ndarray:
    """Encode a list of cases into normalized dense vectors."""
    from sentence_transformers import SentenceTransformer

    if not cases:
        # bge-small-zh-v1.5 outputs 512-dimensional vectors.
        return np.zeros((0, 512), dtype=np.float32)

    model = SentenceTransformer(model_name)
    texts = [str(c.get("text_blob") or "") for c in cases]
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return np.asarray(embeddings, dtype=np.float32)


def save_dense_cache(
    path: Path,
    cases: List[Dict[str, Any]],
    embeddings: np.ndarray,
    model_name: str,
    corpus_path: Optional[Path] = None,
) -> None:
    """Serialize cases, embeddings and metadata to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    corpus_path = Path(corpus_path) if corpus_path else None
    metadata = {
        "version": CACHE_VERSION,
        "model": model_name,
        "corpus_mtime": (
            os.path.getmtime(corpus_path) if corpus_path and corpus_path.exists() else None
        ),
        "corpus_size": (
            os.path.getsize(corpus_path) if corpus_path and corpus_path.exists() else None
        ),
    }
    payload = {
        "metadata": metadata,
        "case_ids": [c.get("person_id") for c in cases],
        "text_blobs": [str(c.get("text_blob") or "") for c in cases],
        "embeddings": embeddings,
    }
    with path.open("wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_dense_cache(path: Path) -> Tuple[List[Dict[str, Any]], np.ndarray, str]:
    """Load a cache; raise on version mismatch or corruption."""
    with Path(path).open("rb") as f:
        payload = pickle.load(f)
    metadata = payload["metadata"]
    if metadata.get("version") != CACHE_VERSION:
        raise ValueError(
            f"dense cache version mismatch: {metadata.get('version')} != {CACHE_VERSION}"
        )
    cases = [
        {"person_id": cid, "text_blob": text}
        for cid, text in zip(payload["case_ids"], payload["text_blobs"])
    ]
    return cases, np.asarray(payload["embeddings"], dtype=np.float32), str(metadata["model"])


def is_cache_valid(
    path: Path,
    corpus_path: Path,
    model_name: str,
) -> bool:
    """Return True when a cache exists and matches the corpus and model."""
    if not Path(path).exists():
        return False
    try:
        _, _, cached_model = load_dense_cache(path)
    except Exception:
        return False
    if cached_model != model_name:
        return False
    corpus_path = Path(corpus_path)
    if not corpus_path.exists():
        return False
    expected_mtime = os.path.getmtime(corpus_path)
    expected_size = os.path.getsize(corpus_path)
    # Avoid loading embeddings just to validate metadata.
    with Path(path).open("rb") as f:
        payload = pickle.load(f)
    metadata = payload["metadata"]
    return (
        metadata.get("version") == CACHE_VERSION
        and metadata.get("corpus_mtime") == expected_mtime
        and metadata.get("corpus_size") == expected_size
    )


def build_or_load(
    corpus_path: Path,
    cache_path: Optional[Path] = None,
    model_name: str = DEFAULT_MODEL,
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """Return (cases, embeddings), rebuilding from the corpus when needed."""
    corpus_path = Path(corpus_path)
    if cache_path is None:
        model_slug = model_name.replace("/", "_")
        cache_path = Path(".cache") / f"dense_{model_slug}.pkl"
    cache_path = Path(cache_path)

    if is_cache_valid(cache_path, corpus_path, model_name):
        return load_dense_cache(cache_path)[:2]

    cases = _load_corpus(corpus_path)
    embeddings = encode_cases(cases, model_name=model_name)
    save_dense_cache(
        cache_path,
        cases,
        embeddings,
        model_name=model_name,
        corpus_path=corpus_path,
    )
    return cases, embeddings


def _load_corpus(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL corpus into a list of dictionaries."""
    cases: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            cases.append(row)
    return cases
