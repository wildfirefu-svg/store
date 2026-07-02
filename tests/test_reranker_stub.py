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
