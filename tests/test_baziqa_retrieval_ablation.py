from scripts.run_baziqa_retrieval_ablation import build_configs, render_report


def test_build_configs_contains_expected_modes():
    configs = build_configs()
    names = [c["name"] for c in configs]
    assert names == ["bm25", "structured", "structured_semantic", "semantic_low"]
    assert configs[0]["env"]["BAZI_RAG_STRUCTURED_WEIGHT"] == "0"
    assert configs[0]["env"]["BAZI_RAG_SEMANTIC"] == "0"
    assert configs[2]["env"]["BAZI_RAG_SEMANTIC"] == "1"


def test_render_report_marks_acceptance_gate():
    text = render_report([
        {"name": "structured", "runs": 3, "mean": 0.40, "min": 0.35, "max": 0.425},
        {"name": "semantic_low", "runs": 3, "mean": 0.325, "min": 0.30, "max": 0.35},
    ])
    assert "| structured | 3 | 40.0% | 35.0% | 42.5% | PASS |" in text
    assert "| semantic_low | 3 | 32.5% | 30.0% | 35.0% | BLOCKED |" in text
