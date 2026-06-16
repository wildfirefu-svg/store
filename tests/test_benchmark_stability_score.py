import pytest


def test_score_stability_perfect():
    from benchmark.scorers.stability_score import score_stability

    runs = [
        {"answer": "A", "evidence": ["官星", "印星"]},
        {"answer": "A", "evidence": ["官星", "印星"]},
        {"answer": "A", "evidence": ["官星", "印星"]},
    ]
    result = score_stability(runs)
    assert result["answer_consistency"] == 1.0
    assert result["evidence_consistency"] == 1.0
    assert result["stability_score"] == 1.0


def test_score_stability_partial():
    from benchmark.scorers.stability_score import score_stability

    runs = [
        {"answer": "A", "evidence": ["官星"]},
        {"answer": "B", "evidence": ["印星"]},
        {"answer": "A", "evidence": ["官星"]},
    ]
    result = score_stability(runs)
    assert result["answer_consistency"] == pytest.approx(2/3)
    assert result["stability_score"] < 1.0
    assert result["dominant_answer"] == "A"


def test_score_stability_no_consistency():
    from benchmark.scorers.stability_score import score_stability

    runs = [
        {"answer": "A", "evidence": ["a"]},
        {"answer": "B", "evidence": ["b"]},
        {"answer": "C", "evidence": ["c"]},
    ]
    result = score_stability(runs)
    assert result["stability_score"] == 0.0


def test_score_stability_two_runs():
    from benchmark.scorers.stability_score import score_stability

    runs = [
        {"answer": "A", "evidence": ["a", "b"]},
        {"answer": "A", "evidence": ["a", "c"]},
    ]
    result = score_stability(runs)
    assert result["answer_consistency"] == 1.0
    assert result["evidence_consistency"] == pytest.approx(1/3)


def test_score_stability_empty_runs():
    from benchmark.scorers.stability_score import score_stability

    result = score_stability([])
    assert result["stability_score"] == 0.0


def test_score_stability_single_run():
    from benchmark.scorers.stability_score import score_stability

    runs = [{"answer": "A", "evidence": ["官星"]}]
    result = score_stability(runs)
    assert result["stability_score"] == 1.0
