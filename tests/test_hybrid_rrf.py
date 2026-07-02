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
