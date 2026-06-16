import pytest


def test_generate_markdown_report():
    from benchmark.reports.generate_report import generate_markdown_report

    result = {
        "run_id": "run_001",
        "dataset": "baziqa_mini_v1",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "prompt_version": "srp_v1",
        "reasoning_protocol": "xuanjizi_srp_v1",
        "choice_accuracy": {
            "total": 15,
            "correct": 10,
            "accuracy": 0.667,
            "by_domain": {
                "career": {"total": 4, "correct": 3, "accuracy": 0.75},
                "wealth": {"total": 4, "correct": 2, "accuracy": 0.5},
            },
        },
        "evidence_score": 0.72,
        "stability_score": 0.85,
        "safety_score": 0.95,
        "case_details": [],
    }

    report = generate_markdown_report(result)
    assert "# 玄机子 BaziQA Benchmark Report" in report
    assert "67%" in report
    assert "Evidence Coverage" in report


def test_generate_report_with_case_details():
    from benchmark.reports.generate_report import generate_markdown_report

    result = {
        "run_id": "run_002",
        "dataset": "test",
        "provider": "test",
        "model": "test",
        "prompt_version": "v1",
        "reasoning_protocol": "rp1",
        "choice_accuracy": {"total": 2, "correct": 1, "accuracy": 0.5, "by_domain": {}},
        "evidence_score": 0.6,
        "stability_score": 0.7,
        "safety_score": 0.8,
        "case_details": [
            {
                "case_id": "career_001",
                "domain": "career",
                "question": "事业？",
                "expected_answer": "A",
                "predicted_answer": "A",
                "correct": True,
                "evidence_coverage": 0.75,
                "safety_score": 1.0,
            },
        ],
    }

    report = generate_markdown_report(result)
    assert "career_001" in report
    assert "事业？" in report
    assert "✓" in report


def test_save_report(tmp_path):
    from benchmark.reports.generate_report import save_report

    result = {
        "run_id": "run_save_test",
        "dataset": "test",
        "provider": "test",
        "model": "test",
        "prompt_version": "v1",
        "reasoning_protocol": "rp1",
        "choice_accuracy": {"total": 1, "correct": 1, "accuracy": 1.0, "by_domain": {}},
        "evidence_score": 1.0,
        "stability_score": 1.0,
        "safety_score": 1.0,
        "case_details": [],
    }

    report_path = save_report(result, output_dir=str(tmp_path))
    assert report_path.endswith("run_run_save_test.md")
    assert (tmp_path / "run_run_save_test.md").exists()
