from unittest.mock import patch

from scripts.run_baziqa_k_ablation import main


def test_main_with_output_runs_k_ablation_and_writes_report(tmp_path):
    output_file = tmp_path / "refined_p2_40_output.md"
    mock_summary = [{"k": 2, "n": 3, "mean": 0.40, "min": 0.35, "max": 0.45, "stdev": 0.05}]
    with patch("scripts.run_baziqa_k_ablation.run_k_ablation", return_value=mock_summary) as mock_run:
        result = main([
            "--dataset", "benchmark/datasets/baziqa_contest8_2025_holdout.jsonl",
            "--method", "structured_reasoning",
            "--max-cases", "40",
            "--temperature", "0",
            "--repeats", "3",
            "--output", str(output_file),
        ])
        assert result == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "Accuracy: 40.0%" in content
        mock_run.assert_called_once()
