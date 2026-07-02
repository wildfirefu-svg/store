# Phase 2 · Hybrid Retrieval + Reranker 实施计划

> **状态说明**：本计划作为 Phase 2 实现历史保留。Phase 2 当前统一状态以 [PHASE2_STATUS_UNIFIED.md](file:///f:/project/agent/docs/PHASE2_STATUS_UNIFIED.md) 为准：工程实现完成，但原始验收 NO-GO；Phase 2.5 离线候选改善但不默认启用。

> **面向执行 Agent：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务执行本计划。任务使用复选框（`- [ ]`）语法以便跟踪进度。

**目标：** 新增 `option_grounded_hybrid` 检索路径，将稀疏 BM25/结构化/语义排序与稠密向量相似度（RRF 融合）以及可选的 cross-encoder reranker 结合，把 BaziQA 的 gold-answer top1 离线指标从 27.5% 提升到 ≥40%，40×3 mean 在线指标从 28.3% 提升到 ≥30%，同时保持 strict leak 为 0。

**架构：** 保持现有 `option_grounded` 路径完全不变以确保向后兼容。新增 `case_dense_index.py` 模块负责缓存稠密向量，`hybrid_retrieval.py` 负责 RRF 融合，`case_reranker.py` 负责 cross-encoder 精排。扩展 `CaseIndex.option_evidence()` 支持新的 `retrieval_mode='option_grounded_hybrid'`，并通过 `rag_prompt_builder.py` 与 `benchmark/runners/run_benchmark.py` 贯通。

**技术栈：** Python 3.11、`sentence-transformers`（BAAI/bge-small-zh-v1.5、BAAI/bge-reranker-v2-m3）、NumPy、pytest。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `case_dense_index.py`（新建） | 将语料库 case 编码为稠密向量；按模型名和语料元数据保存/加载 pickle 缓存。 |
| `scripts/build_dense_index.py`（新建） | 离线构建语料 JSONL 稠密索引的 CLI。 |
| `hybrid_retrieval.py`（新建） | 对多个候选排序列表做 Reciprocal Rank Fusion（RRF）。 |
| `case_reranker.py`（新建） | cross-encoder 包装器：为 (query, passage) 对打分并重排候选。 |
| `case_index.py`（修改） | 将稠密索引、RRF、reranker 集成到 `CaseIndex`；新增 `retrieval_mode='option_grounded_hybrid'`。 |
| `rag_prompt_builder.py`（修改） | 将 `retrieval_mode='option_grounded_hybrid'` 透传给 `case_index.option_evidence()`。 |
| `benchmark/runners/run_benchmark.py`（修改） | 接受 `option_grounded_hybrid` 作为 `--retrieval-mode` 选项并转发。 |
| `scripts/run_baziqa_retrieval_ablation.py`（修改） | 接受 `option_grounded_hybrid` 并转发给 runner；在 yaml 中新增配置项。 |
| `benchmark/configs/baziqa_retrieval_configs.yaml`（修改） | 新增 `option_grounded_hybrid` 配置。 |
| `scripts/evaluate_hybrid_offline.py`（新建） | 离线评估脚本，无需调用 LLM 即可测量 gold-answer top1/top2 率。 |
| `tests/test_case_dense_index.py`（新建） | 稠密索引编码与缓存测试。 |
| `tests/test_hybrid_rrf.py`（新建） | RRF 融合测试。 |
| `tests/test_reranker_stub.py`（新建） | reranker 接口测试。 |
| `tests/test_case_index_hybrid.py`（新建） | hybrid option evidence 路径测试。 |
| `tests/test_rag_prompt_hybrid.py`（新建） | hybrid 模式下 prompt builder 测试。 |

---

## 实施者前置阅读

开始前请先阅读以下文件：

- `case_index.py` — 现有检索与 `option_evidence()` 逻辑。
- `rag_prompt_builder.py` — evidence 如何格式化为 prompt。
- `benchmark/runners/run_benchmark.py` — `--retrieval-mode` 如何解析与传递。
- `benchmark/configs/baziqa_retrieval_configs.yaml` — 检索消融配置 schema。
- `docs/superpowers/specs/2026-07-01-accuracy-improvement-design.md` — Phase 2 设计目标。

---

## 任务 1：稠密索引模块 `case_dense_index.py`

**文件：**
- 新建：`case_dense_index.py`
- 测试：`tests/test_case_dense_index.py`

**概述：** 构建一个模块，将语料库 case 编码为稠密向量并持久化到 pickle 缓存。当模型名或语料文件元数据变化时缓存自动失效。

- [ ] **步骤 1：编写 `encode_cases` 的失败测试**

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

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_case_dense_index.py::test_encode_cases_returns_normalized_vectors -v
```

预期：`FAIL`，报错 `ModuleNotFoundError: No module named 'case_dense_index'`。

- [ ] **步骤 3：实现 `encode_cases`**

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
    """将 case 列表编码为已归一化的稠密向量。"""
    from sentence_transformers import SentenceTransformer

    if not cases:
        # bge-small-zh-v1.5 输出 512 维向量
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

- [ ] **步骤 4：运行测试确认通过**

运行：

```bash
python -m pytest tests/test_case_dense_index.py::test_encode_cases_returns_normalized_vectors -v
```

预期：`PASS`。

- [ ] **步骤 5：编写缓存存取失败测试**

```python
# tests/test_case_dense_index.py（追加）
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

- [ ] **步骤 6：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_case_dense_index.py -v
```

预期：新增测试 `FAIL`。

- [ ] **步骤 7：实现缓存函数**

追加到 `case_dense_index.py`：

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
    """将 case、embedding 与元数据序列化到磁盘。"""
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
    """加载缓存；版本不匹配或损坏时抛出异常。"""
    with Path(path).open("rb") as f:
        payload = pickle.load(f)
    metadata = payload["metadata"]
    if metadata.get("version") != CACHE_VERSION:
        raise ValueError(f"dense cache 版本不匹配: {metadata.get('version')} != {CACHE_VERSION}")
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
    """缓存存在且模型名与语料元数据均匹配时返回 True。"""
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
    # 不加载 embedding，直接读取 metadata 以节省内存
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
    """返回 (cases, embeddings)，缓存缺失或过期时从语料库重建。"""
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

- [ ] **步骤 8：运行测试确认通过**

运行：

```bash
python -m pytest tests/test_case_dense_index.py -v
```

预期：全部 `PASS`。

- [ ] **步骤 9：提交**

```bash
git add case_dense_index.py tests/test_case_dense_index.py
git commit -m "feat(retrieval): 新增 case_dense_index 与 pickle 缓存"
```

---

## 任务 2：离线稠密索引构建 CLI

**文件：**
- 新建：`scripts/build_dense_index.py`
- 测试：`tests/test_case_dense_index.py`（CLI 测试）

- [ ] **步骤 1：编写 CLI 失败测试**

```python
# tests/test_case_dense_index.py（追加）
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

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_case_dense_index.py::test_build_dense_index_cli_writes_cache -v
```

预期：`FAIL`，报错文件不存在。

- [ ] **步骤 3：实现 CLI**

```python
# scripts/build_dense_index.py
"""为 BaziQA 语料库预构建稠密 embedding 缓存的 CLI。"""

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
    parser = argparse.ArgumentParser(description="为语料库构建稠密 embedding 缓存。")
    parser.add_argument("--corpus", required=True, help="语料库 JSONL 路径")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="sentence-transformers 模型名")
    parser.add_argument("--cache", default=None, help="输出缓存路径（默认：.cache/dense_<model>.pkl）")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--force", action="store_true", help="即使缓存有效也强制重建")
    args = parser.parse_args(argv)

    corpus_path = Path(args.corpus)
    cache_path = Path(args.cache) if args.cache else None

    if args.force and cache_path and cache_path.exists():
        cache_path.unlink()

    # 允许使用本地 HF 缓存
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

- [ ] **步骤 4：运行测试确认通过**

运行：

```bash
python -m pytest tests/test_case_dense_index.py -v
```

预期：全部 `PASS`。

- [ ] **步骤 5：提交**

```bash
git add scripts/build_dense_index.py tests/test_case_dense_index.py
git commit -m "feat(retrieval): 新增 build_dense_index CLI"
```

---

## 任务 3：RRF 融合模块 `hybrid_retrieval.py`

**文件：**
- 新建：`hybrid_retrieval.py`
- 测试：`tests/test_hybrid_rrf.py`

- [ ] **步骤 1：编写失败测试**

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

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_hybrid_rrf.py -v
```

预期：`FAIL`，报错 `ModuleNotFoundError: No module named 'hybrid_retrieval'`。

- [ ] **步骤 3：实现 `hybrid_retrieval.py`**

```python
# hybrid_retrieval.py
from __future__ import annotations

from typing import Any, Callable, Dict, List


def rrf_fuse(
    rankings: List[List[Dict[str, Any]]],
    k: int = 60,
    id_key: str = "person_id",
) -> List[Dict[str, Any]]:
    """对多个排序列表做 Reciprocal Rank Fusion。

    得分 = sum(1 / (k + rank))，rank 从 1 开始。
    返回统一排序后的列表，返回的 dict 是输入中首次出现项的浅拷贝。
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
    """分别从稀疏源和稠密源取排序结果，RRF 融合后返回 top-K 候选池。"""
    sparse = sparse_fn()
    dense = dense_fn()
    fused = rrf_fuse([sparse, dense], k=k)
    return fused[:top_k]
```

- [ ] **步骤 4：运行测试确认通过**

运行：

```bash
python -m pytest tests/test_hybrid_rrf.py -v
```

预期：全部 `PASS`。

- [ ] **步骤 5：提交**

```bash
git add hybrid_retrieval.py tests/test_hybrid_rrf.py
git commit -m "feat(retrieval): 新增稀疏 + 稠密排序的 RRF 融合"
```

---

## 任务 4：Cross-Encoder Reranker `case_reranker.py`

**文件：**
- 新建：`case_reranker.py`
- 测试：`tests/test_reranker_stub.py`

- [ ] **步骤 1：编写失败测试**

```python
# tests/test_reranker_stub.py
from __future__ import annotations


def test_rerank_pairs_returns_scores():
    from case_reranker import rerank_pairs

    pairs = [("问题？", "事实一"), ("问题？", "事实二")]
    scores = rerank_pairs(pairs, model_name=None)  # 使用 mock fallback
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

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_reranker_stub.py -v
```

预期：`FAIL`，报错 `ModuleNotFoundError`。

- [ ] **步骤 3：实现 `case_reranker.py`**

```python
# case_reranker.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"


def _mock_scores(pairs: List[tuple[str, str]]) -> List[float]:
    """测试或模型未配置时的 fallback 打分。"""
    return [0.5] * len(pairs)


def rerank_pairs(
    pairs: List[tuple[str, str]],
    model_name: Optional[str] = None,
    batch_size: int = 8,
) -> List[float]:
    """为 (query, passage) 对返回相关性分数。

    如果 model_name 为 None，则返回 mock 分数，方便调用方测试管道。
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
    """按 query 相关性重排候选并返回 top-k。"""
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

- [ ] **步骤 4：运行测试确认通过**

运行：

```bash
python -m pytest tests/test_reranker_stub.py -v
```

预期：全部 `PASS`。

- [ ] **步骤 5：提交**

```bash
git add case_reranker.py tests/test_reranker_stub.py
git commit -m "feat(retrieval): 新增 bge-reranker cross-encoder 包装器"
```

---

## 任务 5：将 Hybrid Retrieval 集成到 `case_index.py`

**文件：**
- 修改：`case_index.py`
- 测试：`tests/test_case_index_hybrid.py`

- [ ] **步骤 1：编写失败测试**

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

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_case_index_hybrid.py -v
```

预期：`FAIL`，报错 `TypeError: option_evidence() got an unexpected keyword argument 'retrieval_mode'`。

- [ ] **步骤 3：修改 `CaseIndex.__init__` 以支持稠密索引**

在 `case_index.py` 中，更新构造函数签名与主体：

```python
# 现有 import 区
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from bazi_features import extract as extract_bazi_features

# 新增 import
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
        # ... 原有校验逻辑 ...
        self.path = path
        self._embed_fn = embed_fn
        self._cases: List[Dict[str, Any]] = self._load(path)
        self._doc_tokens = [_tokenize(c["text_blob"]) for c in self._cases]
        self._idf = self._build_idf(self._doc_tokens)
        self._build_vector_index()

        # Hybrid retrieval 状态
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

- [ ] **步骤 4：新增稠密查询方法**

追加到 `CaseIndex`：

```python
    def top_k_cases_dense(
        self,
        query: str,
        k: int = 20,
    ) -> List[Dict[str, Any]]:
        """使用稠密向量检索 top-k cases。"""
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

- [ ] **步骤 5：新增 hybrid option evidence 路径**

修改 `option_evidence()` 签名：

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

在方法内部，将每个选项的检索循环替换为分支：

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

新增辅助方法 `_option_evidence_hybrid`：

```python
    def _option_evidence_hybrid(
        self,
        option_features: Dict[str, Any],
        option_text: str,
        k_per_option: int = 2,
    ) -> List[Dict[str, Any]]:
        """单个选项的 hybrid 检索：sparse + dense RRF，再可选 reranker 精排。"""
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

        # 使用选项 evidence 启发式重新打分
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

- [ ] **步骤 6：运行测试确认通过**

运行：

```bash
python -m pytest tests/test_case_index_hybrid.py -v
```

预期：全部 `PASS`。

- [ ] **步骤 7：提交**

```bash
git add case_index.py tests/test_case_index_hybrid.py
git commit -m "feat(retrieval): 在 CaseIndex 中集成 hybrid dense + RRF + reranker"
```

---

## 任务 6：将 Hybrid Mode 贯通 Prompt Builder 与 Runner

**文件：**
- 修改：`rag_prompt_builder.py`、`benchmark/runners/run_benchmark.py`、`scripts/run_baziqa_retrieval_ablation.py`
- 测试：`tests/test_rag_prompt_hybrid.py`

- [ ] **步骤 1：编写失败测试**

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

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_rag_prompt_hybrid.py -v
```

预期：`FAIL`，因为 `build_system_prompt` 没有把 `retrieval_mode` 传给 `option_evidence`。

- [ ] **步骤 3：修改 `rag_prompt_builder.py`**

在 `build_system_prompt` 中，将 `retrieval_mode == "option_grounded"` 分支扩展为同时处理 `option_grounded_hybrid`：

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

- [ ] **步骤 4：修改 `benchmark/runners/run_benchmark.py`**

找到 `--retrieval-mode` 的 argparse 定义并增加 `option_grounded_hybrid`：

```python
parser.add_argument(
    '--retrieval-mode',
    default='legacy',
    choices=['legacy', 'option_grounded', 'option_grounded_hybrid'],
    help='RAG retrieval mode',
)
```

确认 `run_model_benchmark` 签名已接受 `retrieval_mode` 并透传（当前代码已支持）。

- [ ] **步骤 5：修改 `scripts/run_baziqa_retrieval_ablation.py`**

更新 `--retrieval-mode` 参数：

```python
parser.add_argument(
    "--retrieval-mode",
    default="legacy",
    choices=["legacy", "option_grounded", "option_grounded_hybrid"],
)
```

- [ ] **步骤 6：新增 yaml 配置项**

追加到 `benchmark/configs/baziqa_retrieval_configs.yaml`：

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

- [ ] **步骤 7：运行测试确认通过**

运行：

```bash
python -m pytest tests/test_rag_prompt_hybrid.py -v
```

预期：`PASS`。

- [ ] **步骤 8：提交**

```bash
git add rag_prompt_builder.py benchmark/runners/run_benchmark.py scripts/run_baziqa_retrieval_ablation.py benchmark/configs/baziqa_retrieval_configs.yaml tests/test_rag_prompt_hybrid.py
git commit -m "feat(bench): 将 option_grounded_hybrid 贯通 prompt builder 与 runner"
```

---

## 任务 7：离线评估脚本

**文件：**
- 新建：`scripts/evaluate_hybrid_offline.py`

- [ ] **步骤 1：实现脚本**

```python
# scripts/evaluate_hybrid_offline.py
"""离线评估 option evidence 排序，无需调用 LLM。"""

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

        # 根据每个选项的 top-1 evidence source_answer_option_text 构建投票
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
    parser = argparse.ArgumentParser(description="Hybrid retrieval 离线评估")
    parser.add_argument("--dataset", required=True, help="holdout JSONL 路径")
    parser.add_argument("--corpus", required=True, help="语料库 JSONL 路径")
    parser.add_argument("--retrieval-mode", default="option_grounded", choices=["option_grounded", "option_grounded_hybrid"])
    parser.add_argument("--dense-model", default=None, help="例如 BAAI/bge-small-zh-v1.5")
    parser.add_argument("--reranker-model", default=None, help="例如 BAAI/bge-reranker-v2-m3")
    parser.add_argument("--option-evidence-k", type=int, default=2)
    parser.add_argument("--output", default=None, help="JSON 输出路径（默认 stdout）")
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

- [ ] **步骤 2：验证脚本可运行**

运行：

```bash
python scripts/evaluate_hybrid_offline.py --help
```

预期：打印帮助信息，退出码 0。

- [ ] **步骤 3：运行 baseline 离线评估**

```bash
python scripts/evaluate_hybrid_offline.py \
    --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl \
    --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl \
    --retrieval-mode option_grounded \
    --output .tmp/phase2_offline_baseline.json
```

预期：JSON 输出中 `gold_top1_rate` 约为 0.275。

- [ ] **步骤 4：运行 hybrid 离线评估**

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

预期：`gold_top1_rate` ≥ 0.40。

- [ ] **步骤 5：提交**

```bash
git add scripts/evaluate_hybrid_offline.py
git commit -m "feat(bench): 新增 hybrid retrieval 离线评估脚本"
```

---

## 任务 8：在线 A/B 评估与 Go/No-Go 决策

**文件：**
- 使用现有脚本；在 `.tmp/` 生成报告

- [ ] **步骤 1：运行 baseline 在线 A/B**

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

预期：报告显示 mean ≈ 28.3%。

- [ ] **步骤 2：运行 hybrid 在线 A/B**

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

预期：报告显示 mean ≥ 30%。

- [ ] **步骤 3：检查 strict leak**

```bash
python scripts/compute_retrieved_answer_leak.py \
    --case-details .tmp/phase2_hybrid/option_grounded_hybrid_run*.jsonl \
    --strict
```

预期：leak ratio = 0。

- [ ] **步骤 4：做出 go/no-go 决策**

| 条件 | 行动 |
|---|---|
| 离线 hybrid gold-top1 ≥ 40% 且在线 mean ≥ 30% 且 leak = 0 | 保留 `option_grounded_hybrid` 配置；以 hybrid 为默认进入 Phase 3 |
| 离线 hybrid gold-top1 < 35% 或在线 mean < 30% 或 leak > 0 | 从默认 yaml 配置中移除 `option_grounded_hybrid`；保留代码与测试；不带 hybrid 进入 Phase 3 |
| 结果混合 | 写入 `.tmp/phase2_report.md`；hybrid 仅作为可选开关保留 |

- [ ] **步骤 5：撰写 Phase 2 总结报告**

创建 `.tmp/phase2_report.md`：

```markdown
# Phase 2 Report: Hybrid Retrieval + Reranker

## 离线评估
- Baseline gold-top1: X%
- Hybrid gold-top1: Y%

## 在线 A/B (40×3 flash)
- Baseline mean: X%
- Hybrid mean: Y%

## Strict Leak
- Hybrid: Z%

## 决策
[GO / NO-GO / OPT-IN]
```

- [ ] **步骤 6：最终回归测试**

运行：

```bash
python -m pytest tests/test_case_dense_index.py tests/test_hybrid_rrf.py tests/test_reranker_stub.py tests/test_case_index_hybrid.py tests/test_rag_prompt_hybrid.py -q
```

预期：全部 `PASS`。

- [ ] **步骤 7：提交报告**

```bash
git add .tmp/phase2_report.md
git commit -m "chore(bench): phase2 hybrid retrieval A/B 结果与决策"
```

---

## 验收标准

| 检查项 | 目标 |
|---|---|
| 单元测试 | 全部新测试通过：`pytest tests/test_case_dense_index.py tests/test_hybrid_rrf.py tests/test_reranker_stub.py tests/test_case_index_hybrid.py tests/test_rag_prompt_hybrid.py -q` |
| 离线 gold-top1 | Hybrid ≥ 40%（baseline 27.5%） |
| 在线 40×3 mean | Hybrid ≥ 30% |
| strict leak | 0 |
| 向后兼容 | `option_grounded` 路径 mean 与 Phase 1 差异 ≤ 1pt |

---

## 自查清单

**需求覆盖：**
- [x] 带本地缓存的稠密索引 — 任务 1
- [x] Hybrid 检索（稀疏 + 稠密）— 任务 5
- [x] RRF 融合 — 任务 3
- [x] Cross-encoder reranker — 任务 4
- [x] `option_grounded_hybrid` 检索模式 — 任务 5-6
- [x] 无需 LLM 的离线评估 — 任务 7
- [x] 在线 A/B 与 go/no-go — 任务 8
- [x] 向后兼容 / 默认关闭 — 任务 5、任务 8

**占位符检查：**
- [x] 无 "TBD"、"TODO"、"implement later"
- [x] 无模糊 "add error handling" 步骤
- [x] 无 "write tests for the above" 而无代码
- [x] 无 "Similar to Task N"

**类型一致性：**
- `retrieval_mode` 参数统一为 `str`，允许取值 `"option_grounded" | "option_grounded_hybrid"`。
- `option_evidence()` 签名在任务 5 中扩展，并在任务 6 中以 `retrieval_mode` 调用。
- `case_dense_index.py` 中的缓存函数统一使用 `Path` 与 `np.ndarray`。

---

## 执行交接

**计划已完成并保存至 `docs/superpowers/plans/2026-07-02-phase2-hybrid-retrieval.md`。**

两种执行方式可选：

**1. Subagent-Driven（推荐）** — 每个任务派一个独立 subagent 执行，我在每任务完成后 review，适合长时间、多文件、严格 TDD 的场景。

**2. Inline Execution** — 在当前会话中按任务顺序执行，我可以批量处理若干任务后给你一个 checkpoint review。

你选哪种？
