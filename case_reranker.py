from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"


def _mock_scores(pairs: list[tuple[str, str]]) -> list[float]:
    """测试或模型未配置时的 fallback 打分。"""
    return [0.5] * len(pairs)


@lru_cache(maxsize=4)
def _load_cross_encoder(model_name: str):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


def rerank_pairs(
    pairs: list[tuple[str, str]],
    model_name: str | None = None,
    batch_size: int = 8,
) -> list[float]:
    """为 (query, passage) 对返回相关性分数。

    如果 model_name 为 None，则返回 mock 分数，方便调用方测试管道。
    """
    if not pairs:
        return []
    if model_name is None:
        return _mock_scores(pairs)

    model = _load_cross_encoder(model_name)
    scores = model.predict(
        pairs,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [float(s) for s in scores]


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    model_name: str | None = None,
    top_k: int = 2,
    text_key: str = "fact_excerpt",
) -> list[dict[str, Any]]:
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
