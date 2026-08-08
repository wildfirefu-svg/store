from __future__ import annotations

from collections.abc import Callable
from typing import Any


def rrf_fuse(
    rankings: list[list[dict[str, Any]]],
    k: int = 60,
    id_key: str = "person_id",
) -> list[dict[str, Any]]:
    """对多个排序列表做 Reciprocal Rank Fusion。

    得分 = sum(1 / (k + rank))，rank 从 1 开始。
    返回统一排序后的列表，返回的 dict 是输入中首次出现项的浅拷贝。
    """
    if not rankings:
        return []

    scores: dict[str, float] = {}
    first_seen: dict[str, dict[str, Any]] = {}
    first_rank: dict[str, int] = {}

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
    sparse_fn: Callable[[], list[dict[str, Any]]],
    dense_fn: Callable[[], list[dict[str, Any]]],
    top_k: int = 20,
    k: int = 60,
) -> list[dict[str, Any]]:
    """分别从稀疏源和稠密源取排序结果，RRF 融合后返回 top-K 候选池。"""
    sparse = sparse_fn()
    dense = dense_fn()
    fused = rrf_fuse([sparse, dense], k=k)
    return fused[:top_k]
