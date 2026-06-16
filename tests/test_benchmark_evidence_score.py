import pytest


def test_score_evidence_coverage_full():
    from benchmark.scorers.evidence_score import score_evidence_coverage

    result = score_evidence_coverage(
        expected=["官星有力", "印星配合", "大运支持"],
        provided=["官星有力", "印星配合", "大运支持", "比劫帮身"],
    )
    assert result["coverage"] == 1.0
    assert result["matched"] == ["官星有力", "印星配合", "大运支持"]
    assert result["missing"] == []
    assert "比劫帮身" in result["extra"]


def test_score_evidence_coverage_partial():
    from benchmark.scorers.evidence_score import score_evidence_coverage

    result = score_evidence_coverage(
        expected=["官星有力", "印星配合"],
        provided=["官星有力"],
    )
    assert 0.4 < result["coverage"] < 0.6
    assert "印星配合" in result["missing"]


def test_score_evidence_coverage_empty_provided():
    from benchmark.scorers.evidence_score import score_evidence_coverage

    result = score_evidence_coverage(expected=["官星有力"], provided=[])
    assert result["coverage"] == 0.0


def test_score_evidence_coverage_empty_expected():
    from benchmark.scorers.evidence_score import score_evidence_coverage

    result = score_evidence_coverage(expected=[], provided=["任何文本"])
    assert result["coverage"] == 1.0


def test_score_case_evidence():
    from benchmark.scorers.evidence_score import score_case_evidence

    case = {
        "case_id": "test_case",
        "expected_evidence": ["官星有力", "印星配合"],
    }
    result = score_case_evidence(case, "此命官星有力，事业运不错")
    assert result["coverage"] > 0.0
    assert "官星有力" in result["matched"]
    assert "印星配合" in result["missing"]


def test_aggregate_evidence_score():
    from benchmark.scorers.evidence_score import aggregate_evidence_score

    scores = [
        {"coverage": 1.0},
        {"coverage": 0.5},
        {"coverage": 0.0},
    ]
    result = aggregate_evidence_score(scores)
    assert result == pytest.approx(0.5)
