import json

from scripts import verify_report_quality_gate


def _run_gate(tmp_path, row):
    reports = tmp_path / "reports.jsonl"
    reports.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    output = tmp_path / "gate.md"
    rc = verify_report_quality_gate.main([
        "--reports-jsonl", str(reports),
        "--output", str(output),
    ])
    return rc, output.read_text(encoding="utf-8")


def test_quality_gate_passes_for_clean_reports(tmp_path):
    rc, content = _run_gate(
        tmp_path,
        {"case_id": "c1", "chart": {"four_pillars": {}}, "report_text": "这是一份合规报告。"},
    )
    assert rc == 0
    assert "Total reports: 1" in content
    assert "Passed (no errors): 1" in content
    assert "Gate status: PASS" in content


def test_quality_gate_fails_for_erroneous_report(tmp_path):
    report_text = "命局形成寅卯辰东方木三会。"
    chart = {"four_pillars": {"year": {"zhi": "子"}, "month": {"zhi": "丑"}, "day": {"zhi": "寅"}, "hour": {"zhi": "卯"}}}
    rc, content = _run_gate(tmp_path, {"case_id": "c2", "chart": chart, "report_text": report_text})
    assert rc == 1
    assert "Failed (>=1 error): 1" in content
    assert "Gate status: FAIL" in content
    assert "missing_branch_for_combo" in content


def test_quality_gate_errors_when_improvement_lacks_baseline(tmp_path):
    rc, content = _run_gate(
        tmp_path,
        {
            "case_id": "missing_baseline",
            "chart": {"four_pillars": {}},
            "report_text": "Benchmark summary: accuracy improved to 46.7% with three repeats.",
            "repeats": 3,
            "answer_distribution": {"A": 1, "B": 1, "C": 1, "D": 1},
            "retrieved_answer_leak": 0.0,
        },
    )
    assert rc == 1
    assert "missing_baseline_comparison" in content


def test_quality_gate_errors_when_single_repeat_claims_improvement(tmp_path):
    rc, content = _run_gate(
        tmp_path,
        {
            "case_id": "single_repeat_improvement",
            "chart": {"four_pillars": {}},
            "report_text": "Benchmark summary: accuracy improved vs baseline from 30% to 46.7%.",
            "repeats": 1,
            "answer_distribution": {"A": 1, "B": 1, "C": 1, "D": 1},
            "retrieved_answer_leak": 0.0,
        },
    )
    assert rc == 1
    assert "insufficient_repeats_for_improvement" in content


def test_quality_gate_warns_when_benchmark_report_lacks_answer_distribution(tmp_path):
    rc, content = _run_gate(
        tmp_path,
        {
            "case_id": "missing_answer_distribution",
            "chart": {"four_pillars": {}},
            "report_text": "Benchmark summary: accuracy 46.7% vs baseline 30%; retrieved_answer_leak=0.0%.",
            "repeats": 3,
            "retrieved_answer_leak": 0.0,
        },
    )
    assert rc == 0
    assert "missing_answer_distribution" in content
    assert "Total warnings: 1" in content


def test_quality_gate_warns_when_benchmark_report_lacks_retrieved_answer_leak(tmp_path):
    rc, content = _run_gate(
        tmp_path,
        {
            "case_id": "missing_leak",
            "chart": {"four_pillars": {}},
            "report_text": "Benchmark summary: accuracy 46.7% vs baseline 30%; answer distribution is balanced.",
            "repeats": 3,
            "answer_distribution": {"A": 1, "B": 1, "C": 1, "D": 1},
        },
    )
    assert rc == 0
    assert "missing_retrieved_answer_leak" in content
    assert "Total warnings: 1" in content
