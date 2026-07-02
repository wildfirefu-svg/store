# Phase 2 · Hybrid Retrieval + Reranker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `option_grounded_hybrid` retrieval path that fuses sparse BM25/structured/semantic ranking with dense embedding similarity (RRF) and an optional cross-encoder reranker, improving BaziQA gold-answer top1 rate from 27.5% to ≥40% offline and 40×3 mean from 28.3% to ≥30% online, while keeping strict leak at 0.

**Architecture:** Keep the existing `option_grounded` path untouched for backward compatibility. Introduce a new `case_dense_index.py` module for cached dense embeddings, `hybrid_retrieval.py` for RRF fusion, and `case_reranker.py` for cross-encoder reranking. Extend `CaseIndex.option_evidence()` to support a new `retrieval_mode='option_grounded_hybrid'`, wired through `rag_prompt_builder.py` and `benchmark/runners/run_benchmark.py`.

**Tech Stack:** Python 3.11, `sentence-transformers` (BAAI/bge-small-zh-v1.5, BAAI/bge-reranker-v2-m3), NumPy, pytest.

---

## File Structure

| File | Responsibility |
|---|---|
| `case_dense_index.py` (create) | Encode corpus cases into dense vectors; save/load a pickle cache keyed by model name and corpus metadata. |
| `scripts/build_dense_index.py` (create) | CLI to pre-build the dense index for a corpus JSONL. |
| `hybrid_retrieval.py` (create) | Reciprocal Rank Fusion (RRF) over multiple ranked candidate lists. |
| `case_reranker.py` (create) | Cross-encoder wrapper: score (query, passage) pairs and rerank candidates. |
| `case_index.py` (modify) | Integrate dense index, RRF, and reranker into `CaseIndex`; add `retrieval_mode='option_grounded_hybrid'`. |
| `rag_prompt_builder.py` (modify) | Pass through `retrieval_mode='option_grounded_hybrid'` to `case_index.option_evidence()`. |
| `benchmark/runners/run_benchmark.py` (modify) | Accept `option_grounded_hybrid` as a `--retrieval-mode` choice and forward it. |
| `scripts/run_baziqa_retrieval_ablation.py` (modify) | Accept `option_grounded_hybrid` and forward to runner; add yaml config entry. |
| `benchmark/configs/baziqa_retrieval_configs.yaml` (modify) | Add an `option_grounded_hybrid` config. |
| `scripts/evaluate_hybrid_offline.py` (create) | Offline evaluation script measuring gold-answer top1/top2 rate without LLM calls. |
| `tests/test_case_dense_index.py` (create) | Tests for dense index encoding and cache. |
| `tests/test_hybrid_rrf.py` (create) | Tests for RRF fusion. |
| `tests/test_reranker_stub.py` (create) | Tests for reranker interface. |
| `tests/test_case_index_hybrid.py` (create) | Tests for hybrid option evidence path. |
| `tests/test_rag_prompt_hybrid.py` (create) | Tests for prompt builder with hybrid mode. |

---

## Pre-Read for Implementers

Read these files before starting:

- `case_index.py` — existing retrieval and `option_evidence()` logic.
- `rag_prompt_builder.py` — how evidence is formatted into prompts.
- `benchmark/runners/run_benchmark.py` — how `--retrieval-mode` is parsed and passed.
- `benchmark/configs/baziqa_retrieval_configs.yaml` — retrieval ablation config schema.
- `docs/superpowers/specs/2026-07-01-accuracy-improvement-design.md` — Phase 2 design goals.

---

## Task 1: Dense Index Module `case_dense_index.py`

**Files:**
- Create: `case_dense_index.py`
- Test: `tests/test_case_dense_index.py`

**Overview:** Build a module that encodes corpus cases into dense vectors and persists them to a pickle cache. The cache is invalidated when the model name or corpus file metadata changes.

- [ ] **Step 1: Write the failing test for `encode_cases`**

```python
# tests/test_case_dense_index.py
from __future__ import annotations

import numpy as np
import pytest


def test_encode_cases_returns_normalized_vectors():
    from case_dense_index import encode_cases

    rows = [
        {"person_id": "p1", "text_blob": "丁火日主身弱财星旺"},
        {"person_id": "p2", "text_blob": "甲木日主身强官杀混杂"},
    ]
    embeddings = encode_cases(rows, model_name="sentence-transformers/all-MiniLM-L6-v2")
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (2, 384)
    norms = np.linalg.norm(embeddings, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/test_case_dense_index.py::test_encode_cases_returns_normalized_vectors -v
```

Expected: `FAIL` with `ModuleNotFoundError: No module named 'case_dense_index'`.

- [ ] **Step 3: Implement `encode_cases`**

```python
# case_dense_index.py
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


def encode_cases(
    cases: List[Dict[str, Any]],
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
) -> np.ndarray:
    """Encode a list of cases into normalized dense vectors."""
    from sentence_transformers import SentenceTransformer

    if not cases:
        # bge-small-zh-v1.5 produces 512-dim vectors
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python -m pytest tests/test_case_dense_index.py::test_encode_cases_returns_normalized_vectors -v
```

Expected: `PASS`.

- [ ] **Step 5: Write the failing test for cache save/load**

```python
# tests/test_case_dense_index.py (append)
from pathlib import Path


def test_cache_roundtrip(tmp_path: Path) -> None:
    from case_dense_index import save_dense_cache, load_dense_cache

    cache_path = tmp_path / "dense.pkl"
    rows = [{"person_id": "p1", "text_blob": "xxx"}]
    embeddings = np.zeros((1, 512), dtype=np.float32)
    save_dense_cache(cache_path, rows, embeddings, model_name="m")
    loaded_rows, loaded_embs, loaded_model = load_dense_cache(cache_path)
    assert loaded_rows == rows
    assert np.allclose(loaded_embs, embeddings)
    assert loaded_model == "m"


def test_cache_invalidated_on_model_change(tmp_path: Path) -> None:
    from case_dense_index import save_dense_cache, is_cache_valid

    cache_path = tmp_path / "dense.pkl"
    save_dense_cache(cache_path, [], np.zeros((0, 512), dtype=np.float32), model_name="old")
    assert is_cache_valid(cache_path, corpus_path=tmp_path / "corpus.jsonl", model_name="new") is False
```

- [ ] **Step 6: Run the tests to verify they fail**

Run:

```bash
python -m pytest tests/test_case_dense_index.py -v
```

Expected: `FAIL` for the new tests.

- [ ] **Step 7: Implement cache functions**

Append to `case_dense_index.py`:

```python
import json
import os
import pickle
from pathlib import Path
from typing import Optional, Tuple


CACHE_VERSION = 1


def save_dense_cache(
    path: Path,
    cases: List[Dict[str, Any]],
    embeddings: np.ndarray,
    model_name: str,
    corpus_path: Optional[Path] = None,
) -> None:
    """Serialize cases + embeddings + metadata to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    corpus_path = Path(corpus_path) if corpus_path else None
    metadata = {
        "version": CACHE_VERSION,
        "model": model_name,
        "corpus_mtime": os.path.getmtime(corpus_path) if corpus_path and corpus_path.exists() else None,
        "corpus_size": os.path.getsize(corpus_path) if corpus_path and corpus_path.exists() else None,
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
    """Load cache; raises if corrupt or version mismatch."""
    with Path(path).open("rb") as f:
        payload = pickle.load(f)
    metadata = payload["metadata"]
    if metadata.get("version") != CACHE_VERSION:
        raise ValueError(f"dense cache version mismatch: {metadata.get('version')} != {CACHE_VERSION}")
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
    """Return True if cache exists and matches model + corpus metadata."""
    if not Path(path).exists():
        return False
    try:
        _, _, cached_model = load_dense_cache(path)
    except Exception:
        return False
    if cached_model != model_name:
        return False
    expected_mtime = os.path.getmtime(corpus_path)
    expected_size = os.path.getsize(corpus_path)
    # Re-read metadata without loading embeddings to save memory
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
    """Return (cases, embeddings), building from corpus if cache is missing or stale."""
    corpus_path = Path(corpus_path)
    if cache_path is None:
        model_slug = model_name.replace("/", "_")
        cache_path = Path(".cache") / f"dense_{model_slug}.pkl"
    cache_path = Path(cache_path)

    if is_cache_valid(cache_path, corpus_path, model_name):
        return load_dense_cache(cache_path)[:2]

    cases = _load_corpus(corpus_path)
    embeddings = encode_cases(cases, model_name=model_name)
    save_dense_cache(cache_path, cases, embeddings, model_name=model_name, corpus_path=corpus_path)
    return cases, embeddings


def _load_corpus(path: Path) -> List[Dict[str, Any]]:
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
```

- [ ] **Step 8: Run the tests to verify they pass**

Run:

```bash
python -m pytest tests/test_case_dense_index.py -v
```

Expected: all `PASS`.

- [ ] **Step 9: Commit**

```bash
git add case_dense_index.py tests/test_case_dense_index.py
git commit -m "feat(retrieval): add case_dense_index with pickle cache"
```

---

## Task 2: Offline Dense Index Build CLI

**Files:**
- Create: `scripts/build_dense_index.py`
- Test: `tests/test_case_dense_index.py` (CLI test)

- [ ] **Step 1: Write the failing test for the CLI**

```python
# tests/test_case_dense_index.py (append)
import subprocess
import sys


def test_build_dense_index_cli_writes_cache(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps({"person_id": "p1", "text_blob": "丁火日主"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    cache = tmp_path / "dense.pkl"
    result = subprocess.run(
        [sys.executable, "scripts/build_dense_index.py", "--corpus", str(corpus), "--cache", str(cache), "--model", "sentence-transformers/all-MiniLM-L6-v2"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert cache.exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/test_case_dense_index.py::test_build_dense_index_cli_writes_cache -v
```

Expected: `FAIL` with file not found.

- [ ] **Step 3: Implement the CLI**

```python
# scripts/build_dense_index.py
"""CLI to pre-build a dense embedding cache for a BaziQA corpus."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from case_dense_index import build_or_load, DEFAULT_MODEL


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build dense embedding cache for a corpus.")
    parser.add_argument("--corpus", required=True, help="Path to corpus JSONL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Sentence-transformers model name")
    parser.add_argument("--cache", default=None, help="Output cache path (default: .cache/dense_<model>.pkl)")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--force", action="store_true", help="Rebuild even if cache is valid")
    args = parser.parse_args(argv)

    corpus_path = Path(args.corpus)
    cache_path = Path(args.cache) if args.cache else None

    if args.force and cache_path and cache_path.exists():
        cache_path.unlink()

    # Allow offline HF caches
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    cases, embeddings = build_or_load(
        corpus_path=corpus_path,
        cache_path=cache_path,
        model_name=args.model,
    )
    print(f"Built dense index: {len(cases)} cases, shape={embeddings.shape}, model={args.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python -m pytest tests/test_case_dense_index.py -v
```

Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_dense_index.py tests/test_case_dense_index.py
git commit -m "feat(retrieval): add build_dense_index CLI"
```

---

## Task 3: RRF Fusion Module `hybrid_retrieval.py`

**Files:**
- Create: `hybrid_retrieval.py`
- Test: `tests/test_hybrid_rrf.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hybrid_rrf.py
from __future__ import annotations


def test_rrf_fuse_two_lists():
    from hybrid_retrieval import rrf_fuse

    sparse = [{"person_id": "c1"}, {"person_id": "c2"}, {"person_id": "c3"}]
    dense = [{"person_id": "c3"}, {"person_id": "c1"}, {"person_id": "c2"}]
    fused = rrf_fuse([sparse, dense], k=60)
    ids = [c["person_id"] for c in fused]
    assert ids == ["c1", "c3", "c2"]


def test_rrf_fuse_empty():
    from hybrid_retrieval import rrf_fuse

    assert rrf_fuse([]) == []


def test_rrf_fuse_single_list():
    from hybrid_retrieval import rrf_fuse

    rankings = [[{"person_id": "c1"}, {"person_id": "c2"}]]
    fused = rrf_fuse(rankings, k=60)
    assert [c["person_id"] for c in fused] == ["c1", "c2"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/test_hybrid_rrf.py -v
```

Expected: `FAIL` with `ModuleNotFoundError: No module named 'hybrid_retrieval'`.

- [ ] **Step 3: Implement `hybrid_retrieval.py`**

```python
# hybrid_retrieval.py
from __future__ import annotations

from typing import Any, Callable, Dict, List


def rrf_fuse(
    rankings: List[List[Dict[str, Any]]],
    k: int = 60,
    id_key: str = "person_id",
) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion over multiple ranked lists.

    Score = sum(1 / (k + rank)) for each list where the item appears.
    Returns a unified ranking. The returned dicts are shallow copies of the
    first occurrence in the input rankings.
    """
    if not rankings:
        return []

    scores: Dict[str, float] = {}
    first_seen: Dict[str, Dict[str, Any]] = {}
    first_rank: Dict[str, int] = {}

    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            item_id = str(item.get(id_key, ""))
            if not item_id:
                continue
            if item_id not in first_seen:
                first_seen[item_id] = dict(item)
                first_rank[item_id] = rank
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)

    ranked_ids = sorted(
        scores.keys(),
        key=lambda iid: (-scores[iid], first_rank[iid], iid),
    )
    return [first_seen[iid] for iid in ranked_ids]


def hybrid_retrieve(
    sparse_fn: Callable[[], List[Dict[str, Any]]],
    dense_fn: Callable[[], List[Dict[str, Any]]],
    top_k: int = 20,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """Fetch rankings from sparse and dense sources, fuse with RRF, return top-K pool."""
    sparse = sparse_fn()
    dense = dense_fn()
    fused = rrf_fuse([sparse, dense], k=k)
    return fused[:top_k]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python -m pytest tests/test_hybrid_rrf.py -v
```

Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add hybrid_retrieval.py tests/test_hybrid_rrf.py
git commit -m "feat(retrieval): add RRF fusion for sparse + dense rankings"
```

---

## Task 4: Cross-Encoder Reranker `case_reranker.py`

**Files:**
- Create: `case_reranker.py`
- Test: `tests/test_reranker_stub.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reranker_stub.py
from __future__ import annotations


def test_rerank_pairs_returns_scores():
    from case_reranker import rerank_pairs

    pairs = [("问题？", "事实一"), ("问题？", "事实二")]
    scores = rerank_pairs(pairs, model_name=None)  # use mock fallback
    assert len(scores) == 2
    assert all(isinstance(s, float) for s in scores)


def test_rerank_candidates_orders_by_score():
    from case_reranker import rerank_candidates

    candidates = [
        {"person_id": "c1", "fact_excerpt": "事实一"},
        {"person_id": "c2", "fact_excerpt": "事实二"},
    ]
    ranked = rerank_candidates("问题？", candidates, model_name=None, top_k=2)
    assert len(ranked) == 2
    assert ranked[0]["rerank_score"] >= ranked[1]["rerank_score"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/test_reranker_stub.py -v
```

Expected: `FAIL` with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `case_reranker.py`**

```python
# case_reranker.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"


def _mock_scores(pairs: List[tuple[str, str]]) -> List[float]:
    """Fallback scoring for tests or when no model is configured."""
    return [0.5] * len(pairs)


def rerank_pairs(
    pairs: List[tuple[str, str]],
    model_name: Optional[str] = None,
    batch_size: int = 8,
) -> List[float]:
    """Return scalar relevance scores for (query, passage) pairs.

    If model_name is None, returns mock scores so callers can test the plumbing.
    """
    if not pairs:
        return []
    if model_name is None:
        return _mock_scores(pairs)

    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_name)
    scores = model.predict(
        pairs,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [float(s) for s in scores]


def rerank_candidates(
    query: str,
    candidates: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    top_k: int = 2,
    text_key: str = "fact_excerpt",
) -> List[Dict[str, Any]]:
    """Rerank candidates by query relevance and return top-k."""
    if not candidates:
        return []

    resolved_model = model_name or os.environ.get("BAZI_RERANKER_MODEL")
    pairs = [(str(query), str(c.get(text_key) or "")) for c in candidates]
    scores = rerank_pairs(pairs, model_name=resolved_model)

    scored = []
    for candidate, score in zip(candidates, scores):
        item = dict(candidate)
        item["rerank_score"] = float(score)
        scored.append(item)

    scored.sort(key=lambda c: (-c["rerank_score"], str(c.get("person_id") or "")))
    return scored[:top_k]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python -m pytest tests/test_reranker_stub.py -v
```

Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add case_reranker.py tests/test_reranker_stub.py
git commit -m "feat(retrieval): add bge-reranker cross-encoder wrapper"
```

---

## Task 5: Integrate Hybrid Retrieval into `case_index.py`

**Files:**
- Modify: `case_index.py`
- Test: `tests/test_case_index_hybrid.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_case_index_hybrid.py
from __future__ import annotations

from pathlib import Path

import pytest


def _tiny_corpus(tmp_path: Path) -> Path:
    path = tmp_path / "corpus.jsonl"
    lines = [
        {"person_id": "p1", "text_blob": "丁火日主身弱财星旺", "facts": ["问事业 -> A"], "domains": {"career": 1}},
        {"person_id": "p2", "text_blob": "甲木日主身强官杀混杂", "facts": ["问事业 -> B"], "domains": {"career": 1}},
    ]
    import json
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in lines) + "\n", encoding="utf-8")
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/test_case_index_hybrid.py -v
```

Expected: `FAIL` with `TypeError: option_evidence() got an unexpected keyword argument 'retrieval_mode'`.

- [ ] **Step 3: Modify `CaseIndex.__init__` to support dense index**

In `case_index.py`, update the constructor signature and body:

```python
# Existing import section
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from bazi_features import extract as extract_bazi_features

# Add new imports
import case_dense_index
import hybrid_retrieval
import case_reranker


class CaseIndex:
    def __init__(
        self,
        corpus_path: Path,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        dense_model: Optional[str] = None,
        dense_cache_path: Optional[Path] = None,
        use_hybrid: bool = False,
        rrf_k: int = 60,
        reranker_model: Optional[str] = None,
    ):
        # ... existing validation ...
        self.path = path
        self._embed_fn = embed_fn
        self._cases: List[Dict[str, Any]] = self._load(path)
        self._doc_tokens = [_tokenize(c["text_blob"]) for c in self._cases]
        self._idf = self._build_idf(self._doc_tokens)
        self._build_vector_index()

        # Hybrid retrieval state
        self._use_hybrid = use_hybrid
        self._rrf_k = rrf_k
        self._reranker_model = reranker_model
        self._dense_model = dense_model
        self._dense_cache_path = dense_cache_path
        self._case_embeddings: Optional[np.ndarray] = None
        self._dense_case_ids: List[str] = []
        if self._use_hybrid and self._dense_model:
            self._load_dense_index()

    def _load_dense_index(self) -> None:
        try:
            cases, embeddings = case_dense_index.build_or_load(
                corpus_path=self.path,
                cache_path=self._dense_cache_path,
                model_name=self._dense_model,
            )
            self._dense_case_ids = [c.get("person_id") for c in cases]
            self._case_embeddings = embeddings
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to load dense index for %s: %s; hybrid dense path disabled",
                self.path,
                exc,
            )
            self._case_embeddings = None
```

- [ ] **Step 4: Add dense query method**

Append to `CaseIndex`:

```python
    def top_k_cases_dense(
        self,
        query: str,
        k: int = 20,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k cases using dense embeddings."""
        if self._case_embeddings is None or not query:
            return []
        if len(self._dense_case_ids) != len(self._cases):
            return []

        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(self._dense_model)
            q_emb = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)
            q_emb = np.asarray(q_emb, dtype=np.float32)
            sims = (self._case_embeddings @ q_emb.T).flatten()
        except Exception:
            return []

        indexed_sims = list(enumerate(sims.tolist()))
        indexed_sims.sort(key=lambda x: (-x[1], self._cases[x[0]].get("person_id") or ""))

        out: List[Dict[str, Any]] = []
        for idx, score in indexed_sims[:k]:
            case = dict(self._cases[idx])
            case["_score"] = round(float(score), 6)
            case["match_reasons"] = [f"dense_sim:{score:.3f}"]
            out.append(case)
        return out
```

- [ ] **Step 5: Add hybrid option evidence path**

Modify `option_evidence()` signature:

```python
    def option_evidence(
        self,
        features: Dict[str, Any],
        question: str,
        options: List[str],
        domain: Optional[str] = None,
        k_per_option: int = 2,
        retrieval_mode: str = "option_grounded",
    ) -> Dict[str, List[Dict[str, Any]]]:
```

Inside the method, replace the per-option retrieval loop with a branch:

```python
        for i, label in enumerate(labels[:4]):
            option_text = str(options[i]) if i < len(options or []) else ""
            query_text = " ".join(part for part in [str(question or ""), option_text] if part)

            if retrieval_mode == "option_grounded_hybrid" and self._use_hybrid:
                option_structured = dict(base_structured)
                option_structured["query_text"] = query_text
                option_features = {
                    "text_blob": " ".join(part for part in [base_text, query_text] if part),
                    "structured": option_structured,
                }
                ranked = self._option_evidence_hybrid(
                    option_features,
                    option_text,
                    k_per_option=k_per_option,
                )
            else:
                option_structured = dict(base_structured)
                option_structured["query_text"] = query_text
                option_features = {
                    "text_blob": " ".join(part for part in [base_text, query_text] if part),
                    "structured": option_structured,
                }
                ranked = []
                for case in self.top_k_cases(option_features, k=candidate_count):
                    item = dict(case)
                    option_score, option_reasons = self._score_option_evidence(item, option_text)
                    item["_score"] = round(float(item.get("_score") or 0.0) + option_score, 6)
                    item["match_reasons"] = list(item.get("match_reasons") or []) + option_reasons
                    ranked.append(item)
                ranked.sort(
                    key=lambda case: (
                        -float(case.get("_score") or 0.0),
                        str(case.get("person_id") or ""),
                        str(case.get("birth_year") or ""),
                        str(case.get("name") or ""),
                    )
                )

            option_candidates[label] = ranked
```

Add helper method `_option_evidence_hybrid`:

```python
    def _option_evidence_hybrid(
        self,
        option_features: Dict[str, Any],
        option_text: str,
        k_per_option: int = 2,
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval for one option: sparse + dense RRF, then optional reranker."""
        k_pool = max(k_per_option * 10, 20)

        def sparse_fn():
            return self.top_k_cases(option_features, k=k_pool)

        def dense_fn():
            query = str(option_features.get("text_blob") or "")
            return self.top_k_cases_dense(query, k=k_pool)

        pool = hybrid_retrieval.hybrid_retrieve(
            sparse_fn=sparse_fn,
            dense_fn=dense_fn,
            top_k=k_pool,
            k=self._rrf_k,
        )

        if not pool:
            return []

        # Re-score with option evidence heuristic
        scored = []
        for case in pool:
            item = dict(case)
            option_score, option_reasons = self._score_option_evidence(item, option_text)
            item["_score"] = round(float(item.get("_score") or 0.0) + option_score, 6)
            item["match_reasons"] = list(item.get("match_reasons") or []) + option_reasons
            scored.append(item)

        if self._reranker_model:
            query = str(option_features.get("text_blob") or "")
            reranked = case_reranker.rerank_candidates(
                query=query,
                candidates=scored,
                model_name=self._reranker_model,
                top_k=k_per_option,
                text_key="fact_excerpt",
            )
            return reranked

        scored.sort(
            key=lambda case: (
                -float(case.get("_score") or 0.0),
                str(case.get("person_id") or ""),
                str(case.get("birth_year") or ""),
                str(case.get("name") or ""),
            )
        )
        return scored[:k_per_option]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
python -m pytest tests/test_case_index_hybrid.py -v
```

Expected: all `PASS`.

- [ ] **Step 7: Commit**

```bash
git add case_index.py tests/test_case_index_hybrid.py
git commit -m "feat(retrieval): integrate hybrid dense + RRF + reranker into CaseIndex"
```

---

## Task 6: Wire Hybrid Mode Through Prompt Builder and Runner

**Files:**
- Modify: `rag_prompt_builder.py`, `benchmark/runners/run_benchmark.py`, `scripts/run_baziqa_retrieval_ablation.py`
- Test: `tests/test_rag_prompt_hybrid.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rag_prompt_hybrid.py
from __future__ import annotations

from unittest.mock import MagicMock


def test_build_system_prompt_hybrid_mode_calls_option_evidence():
    from rag_prompt_builder import build_system_prompt

    mock_index = MagicMock()
    mock_index.option_evidence.return_value = {
        "A": [{"person_id": "p1", "fact_excerpt": "fact", "score": 1.0, "match_reasons": [], "stance": "related", "source_domain": "career", "source_answer_option_text": ""}],
        "B": [],
        "C": [],
        "D": [],
    }

    prompt = build_system_prompt(
        base_system="base",
        chart={"query_domain": "career", "query_text": "问事业", "four_pillars": {}},
        case_index=mock_index,
        enable_rag=True,
        retrieval_mode="option_grounded_hybrid",
        question="问事业",
        options=["A. 升职", "B. 跳槽", "C. 稳定", "D. 转行"],
        option_evidence_k=1,
    )
    mock_index.option_evidence.assert_called_once()
    call_kwargs = mock_index.option_evidence.call_args.kwargs
    assert call_kwargs.get("retrieval_mode") == "option_grounded_hybrid"
    assert "<选项证据>" in prompt
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/test_rag_prompt_hybrid.py -v
```

Expected: `FAIL` because `build_system_prompt` does not pass `retrieval_mode` to `option_evidence`.

- [ ] **Step 3: Modify `rag_prompt_builder.py`**

In `build_system_prompt`, update the `retrieval_mode == "option_grounded"` branch to also handle `option_grounded_hybrid`:

```python
    if retrieval_mode in ("option_grounded", "option_grounded_hybrid"):
        option_list = list(options or [])
        query_question = str(question or chart.get("query_text") or "")
        structured = features.get("structured") or {}
        domain = chart.get("query_domain") or structured.get("query_domain")
        option_evidence = case_index.option_evidence(
            features,
            question=query_question,
            options=option_list,
            domain=domain,
            k_per_option=option_evidence_k,
            retrieval_mode=retrieval_mode,
        )
        injection = _format_option_evidence_block(option_evidence, option_list)
        return _compose_prompt(base, fewshot_block, injection)
```

- [ ] **Step 4: Modify `benchmark/runners/run_benchmark.py`**

Find the `--retrieval-mode` argparse definition and add `option_grounded_hybrid`:

```python
parser.add_argument(
    '--retrieval-mode',
    default='legacy',
    choices=['legacy', 'option_grounded', 'option_grounded_hybrid'],
    help='RAG retrieval mode',
)
```

Ensure `run_model_benchmark` signature already accepts `retrieval_mode` and passes it through (it does).

- [ ] **Step 5: Modify `scripts/run_baziqa_retrieval_ablation.py`**

Update the `--retrieval-mode` argument:

```python
parser.add_argument(
    "--retrieval-mode",
    default="legacy",
    choices=["legacy", "option_grounded", "option_grounded_hybrid"],
)
```

- [ ] **Step 6: Add yaml config entry**

Append to `benchmark/configs/baziqa_retrieval_configs.yaml`:

```yaml
- id: option_grounded_hybrid
  bm25: true
  structured: true
  semantic: true
  tfidf_vector: false
  embedding_vector: false
  embedding_model: ""
  retrieval_mode: option_grounded_hybrid
  option_evidence_k: 2
```

- [ ] **Step 7: Run the tests to verify they pass**

Run:

```bash
python -m pytest tests/test_rag_prompt_hybrid.py -v
```

Expected: `PASS`.

- [ ] **Step 8: Commit**

```bash
git add rag_prompt_builder.py benchmark/runners/run_benchmark.py scripts/run_baziqa_retrieval_ablation.py benchmark/configs/baziqa_retrieval_configs.yaml tests/test_rag_prompt_hybrid.py
git commit -m "feat(bench): wire option_grounded_hybrid through prompt builder and runner"
```

---

## Task 7: Offline Evaluation Script

**Files:**
- Create: `scripts/evaluate_hybrid_offline.py`

- [ ] **Step 1: Implement the script**

```python
# scripts/evaluate_hybrid_offline.py
"""Offline evaluation of option evidence ranking without LLM calls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bazi_features import extract
from case_index import CaseIndex


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _case_chart(case: Dict[str, Any]) -> Dict[str, Any]:
    chart = (case or {}).get("chart_input") or {}
    if chart:
        chart = dict(chart)
        chart["query_domain"] = case.get("domain") or "unknown"
        chart["query_text"] = " ".join([str(case.get("question") or "")] + [str(opt) for opt in (case.get("options") or [])])
    return chart


def _extract_option_label(text: str) -> str:
    text = str(text or "").strip()
    if text and text[0].upper() in "ABCD":
        return text[0].upper()
    return ""


def evaluate(
    dataset_path: Path,
    corpus_path: Path,
    retrieval_mode: str,
    dense_model: Optional[str],
    reranker_model: Optional[str],
    option_evidence_k: int = 2,
) -> Dict[str, Any]:
    os.environ["BAZI_RAG"] = "1"
    os.environ["BAZI_RAG_CORPUS"] = str(corpus_path)

    cases = _load_jsonl(dataset_path)
    index = CaseIndex(
        corpus_path,
        use_hybrid=(retrieval_mode == "option_grounded_hybrid"),
        dense_model=dense_model,
        reranker_model=reranker_model,
    )

    top1 = 0
    top2 = 0
    ranks: List[int] = []
    per_case: List[Dict[str, Any]] = []

    for case in cases:
        chart = _case_chart(case)
        features = extract(chart)
        options = list(case.get("options") or [])
        answer = str(case.get("answer") or "").upper()

        evidence = index.option_evidence(
            features,
            question=str(case.get("question") or ""),
            options=options,
            domain=case.get("domain") or chart.get("query_domain"),
            k_per_option=option_evidence_k,
            retrieval_mode=retrieval_mode,
        )

        # Build a vote per option based on its top-1 evidence source_answer_option_text
        option_scores: Dict[str, float] = {}
        for label in ["A", "B", "C", "D"]:
            items = evidence.get(label) or []
            if items:
                item = items[0]
                source_label = _extract_option_label(item.get("source_answer_option_text") or "")
                option_scores[label] = item.get("score", 0.0)
                if source_label:
                    option_scores[source_label] = option_scores.get(source_label, 0.0) + item.get("score", 0.0)
            else:
                option_scores[label] = 0.0

        ranked = sorted(option_scores.items(), key=lambda x: -x[1])
        rank_of_gold = next((i for i, (label, _) in enumerate(ranked, start=1) if label == answer), None)

        if rank_of_gold == 1:
            top1 += 1
        if rank_of_gold is not None and rank_of_gold <= 2:
            top2 += 1
        if rank_of_gold is not None:
            ranks.append(rank_of_gold)

        per_case.append({
            "case_id": case.get("case_id"),
            "answer": answer,
            "rank": rank_of_gold,
            "ranked_options": [label for label, _ in ranked],
        })

    total = len(cases)
    return {
        "total": total,
        "retrieval_mode": retrieval_mode,
        "dense_model": dense_model,
        "reranker_model": reranker_model,
        "gold_top1": top1,
        "gold_top1_rate": top1 / total if total else 0.0,
        "gold_top2": top2,
        "gold_top2_rate": top2 / total if total else 0.0,
        "mean_rank": sum(ranks) / len(ranks) if ranks else None,
        "per_case": per_case,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Offline hybrid retrieval evaluation")
    parser.add_argument("--dataset", required=True, help="Path to holdout JSONL")
    parser.add_argument("--corpus", required=True, help="Path to corpus JSONL")
    parser.add_argument("--retrieval-mode", default="option_grounded", choices=["option_grounded", "option_grounded_hybrid"])
    parser.add_argument("--dense-model", default=None, help="e.g. BAAI/bge-small-zh-v1.5")
    parser.add_argument("--reranker-model", default=None, help="e.g. BAAI/bge-reranker-v2-m3")
    parser.add_argument("--option-evidence-k", type=int, default=2)
    parser.add_argument("--output", default=None, help="JSON output path (default: stdout)")
    args = parser.parse_args(argv)

    result = evaluate(
        dataset_path=Path(args.dataset),
        corpus_path=Path(args.corpus),
        retrieval_mode=args.retrieval_mode,
        dense_model=args.dense_model,
        reranker_model=args.reranker_model,
        option_evidence_k=args.option_evidence_k,
    )

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify it runs**

Run:

```bash
python scripts/evaluate_hybrid_offline.py --help
```

Expected: help text prints, exit 0.

- [ ] **Step 3: Run baseline offline evaluation**

```bash
python scripts/evaluate_hybrid_offline.py \
    --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl \
    --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl \
    --retrieval-mode option_grounded \
    --output .tmp/phase2_offline_baseline.json
```

Expected: JSON output with `gold_top1_rate` ≈ 0.275.

- [ ] **Step 4: Run hybrid offline evaluation**

```bash
python scripts/build_dense_index.py \
    --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl \
    --model BAAI/bge-small-zh-v1.5 \
    --cache .cache/baziqa_dense_bge_small.pkl

python scripts/evaluate_hybrid_offline.py \
    --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl \
    --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl \
    --retrieval-mode option_grounded_hybrid \
    --dense-model BAAI/bge-small-zh-v1.5 \
    --output .tmp/phase2_offline_hybrid.json
```

Expected: `gold_top1_rate` ≥ 0.40.

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_hybrid_offline.py
git commit -m "feat(bench): add offline hybrid retrieval evaluation"
```

---

## Task 8: Online A/B Evaluation and Go/No-Go

**Files:**
- Use existing scripts; produce reports in `.tmp/`

- [ ] **Step 1: Run baseline online A/B**

```bash
python scripts/run_baziqa_retrieval_ablation.py \
    --run \
    --config-id option_grounded_tfidf \
    --model deepseek-v4-flash \
    --repeats 3 \
    --max-cases 40 \
    --method structured_reasoning \
    --output-dir .tmp/phase2_baseline \
    --report .tmp/phase2_baseline/report.md
```

Expected: report shows mean ≈ 28.3%.

- [ ] **Step 2: Run hybrid online A/B**

```bash
python scripts/run_baziqa_retrieval_ablation.py \
    --run \
    --config-id option_grounded_hybrid \
    --model deepseek-v4-flash \
    --repeats 3 \
    --max-cases 40 \
    --method structured_reasoning \
    --output-dir .tmp/phase2_hybrid \
    --report .tmp/phase2_hybrid/report.md
```

Expected: report shows mean ≥ 30%.

- [ ] **Step 3: Check strict leak**

```bash
python scripts/compute_retrieved_answer_leak.py \
    --case-details .tmp/phase2_hybrid/option_grounded_hybrid_run*.jsonl \
    --strict
```

Expected: leak ratio = 0.

- [ ] **Step 4: Make go/no-go decision**

| Condition | Action |
|---|---|
| Offline hybrid gold-top1 ≥ 40% AND online mean ≥ 30% AND leak = 0 | Keep `option_grounded_hybrid` config; proceed to Phase 3 with hybrid as default |
| Offline hybrid gold-top1 < 35% OR online mean < 30% OR leak > 0 | Remove `option_grounded_hybrid` from default yaml configs; keep code and tests; proceed to Phase 3 without hybrid |
| Mixed results | Document in `.tmp/phase2_report.md`; keep hybrid as opt-in only |

- [ ] **Step 5: Write Phase 2 summary report**

Create `.tmp/phase2_report.md` with:

```markdown
# Phase 2 Report: Hybrid Retrieval + Reranker

## Offline Evaluation
- Baseline gold-top1: X%
- Hybrid gold-top1: Y%

## Online A/B (40×3 flash)
- Baseline mean: X%
- Hybrid mean: Y%

## Strict Leak
- Hybrid: Z%

## Decision
[GO / NO-GO / OPT-IN]
```

- [ ] **Step 6: Final regression test**

Run:

```bash
python -m pytest tests/test_case_dense_index.py tests/test_hybrid_rrf.py tests/test_reranker_stub.py tests/test_case_index_hybrid.py tests/test_rag_prompt_hybrid.py -q
```

Expected: all `PASS`.

- [ ] **Step 7: Commit report**

```bash
git add .tmp/phase2_report.md
git commit -m "chore(bench): phase2 hybrid retrieval A/B results and decision"
```

---

## Acceptance Criteria

| Criterion | Target |
|---|---|
| Unit tests | All new tests pass: `pytest tests/test_case_dense_index.py tests/test_hybrid_rrf.py tests/test_reranker_stub.py tests/test_case_index_hybrid.py tests/test_rag_prompt_hybrid.py -q` |
| Offline gold-top1 | Hybrid ≥ 40% (baseline 27.5%) |
| Online 40×3 mean | Hybrid ≥ 30% |
| strict leak | 0 |
| Backward compatibility | `option_grounded` path mean difference vs Phase 1 ≤ 1pt |

---

## Self-Review Checklist

**Spec coverage:**
- [x] Dense index with local cache — Task 1
- [x] Hybrid retrieval (sparse + dense) — Task 5
- [x] RRF fusion — Task 3
- [x] Cross-encoder reranker — Task 4
- [x] `option_grounded_hybrid` retrieval mode — Tasks 5-6
- [x] Offline evaluation without LLM — Task 7
- [x] Online A/B and go/no-go — Task 8
- [x] Backward compatibility / default-off — Task 5, Task 8

**Placeholder scan:**
- [x] No "TBD", "TODO", "implement later"
- [x] No vague "add error handling" steps
- [x] No "write tests for the above" without code
- [x] No "Similar to Task N"

**Type consistency:**
- `retrieval_mode` parameter consistently `str` with allowed values `"option_grounded" | "option_grounded_hybrid"`.
- `option_evidence()` signature extended in Task 5 and called with `retrieval_mode` in Task 6.
- Cache functions in `case_dense_index.py` use `Path` and `np.ndarray` consistently.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-02-phase2-hybrid-retrieval.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints for review.

Which approach would you like?
