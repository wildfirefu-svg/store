from scripts import analyze_baziqa_error_attribution


import json


def test_analyze_error_attribution_counts_domains_and_errors(tmp_path):
    input_path = tmp_path / "details.jsonl"
    lines = [
        {"domain": "wealth", "expected_answer": "A", "predicted_answer": "A", "correct": True, "parser_valid": True},
        {"domain": "wealth", "expected_answer": "B", "predicted_answer": "A", "correct": False, "parser_valid": True},
        {"domain": "health", "expected_answer": "C", "predicted_answer": None, "correct": False, "parser_valid": False},
    ]
    input_path.write_text("".join(f"{json.dumps(line, ensure_ascii=False)}\n" for line in lines), encoding="utf-8")

    output_path = tmp_path / "report.md"
    analyze_baziqa_error_attribution.main([
        "--case-details-jsonl", str(input_path),
        "--output", str(output_path),
    ])

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "BaziQA Error Attribution Report" in content
    assert "Total cases: 3" in content
    assert "Correct: 1" in content
    assert "parser_invalid | 1" in content
    assert "predicted_wrong | 1" in content
    assert "wealth" in content
    assert "health" in content
