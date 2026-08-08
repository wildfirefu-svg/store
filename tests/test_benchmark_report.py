

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


def test_report_contains_trust_metadata():
    from benchmark.reports.generate_report import generate_markdown_report

    result = {
        "run_id": "run_trust",
        "dataset": "baziqa_mini_v1",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "prompt_version": "srp_v1",
        "reasoning_protocol": "xuanjizi_srp_v1",
        "choice_accuracy": {"total": 1, "correct": 1, "accuracy": 1.0, "by_domain": {}},
        "evidence_score": 0.72,
        "stability_score": 0.85,
        "safety_score": 0.95,
        "case_details": [],
        "run_date": "2026-06-16 12:00:00",
    }
    report = generate_markdown_report(result)
    assert '本报告生成信息' in report
    assert '模型' in report
    assert '协议' in report
    assert '依据覆盖' in report
    assert '安全边界' in report


def test_report_treats_zero_stability_as_zero_score():
    from benchmark.reports.generate_report import generate_markdown_report

    result = {
        "run_id": "run_zero_stability",
        "dataset": "test",
        "provider": "test",
        "model": "test",
        "prompt_version": "v1",
        "reasoning_protocol": "rp1",
        "choice_accuracy": {"total": 10, "correct": 10, "accuracy": 1.0, "by_domain": {}},
        "evidence_score": 1.0,
        "stability_score": 0.0,
        "safety_score": 1.0,
        "case_details": [],
    }
    report = generate_markdown_report(result)
    assert '| Stability | 0% |' in report
    assert 'N/A (单次运行)' not in report


def test_report_escapes_markdown_table_cells():
    from benchmark.reports.generate_report import generate_markdown_report

    result = {
        "run_id": "run_pipe",
        "dataset": "data|set",
        "provider": "deep|seek",
        "model": "model\nname",
        "prompt_version": "v|1",
        "reasoning_protocol": "rp|1",
        "choice_accuracy": {
            "total": 1,
            "correct": 0,
            "accuracy": 0.0,
            "by_domain": {"career|x": {"total": 1, "correct": 0, "accuracy": 0.0}},
        },
        "evidence_score": 0.0,
        "stability_score": None,
        "safety_score": 1.0,
        "case_details": [],
    }
    report = generate_markdown_report(result)
    assert 'career\\|x' in report
    assert 'deep\\|seek' in report
    assert 'model name' in report



def test_report_contains_baziqa_year_and_method_breakdowns():
    from benchmark.reports.generate_report import generate_markdown_report

    data = {
        "run_id": "run1",
        "dataset": "baziqa_contest8_2021_2025.jsonl",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "method": "structured_reasoning",
        "prompt_version": "srp_v2",
        "reasoning_protocol": "baziqa_srp_v1",
        "choice_accuracy": {
            "accuracy": 0.4,
            "total": 200,
            "correct": 80,
            "by_domain": {"career": {"total": 40, "correct": 20, "accuracy": 0.5}},
            "by_year": {"2025": {"total": 40, "correct": 12, "accuracy": 0.3}},
        },
        "evidence_score": 0.5,
        "stability_score": 0.7,
        "safety_score": 0.95,
        "case_details": [],
    }

    report = generate_markdown_report(data)

    assert "structured_reasoning" in report
    assert "Accuracy by Year" in report
    assert "2025" in report
    assert "Accuracy by Domain" in report
    assert "career" in report
