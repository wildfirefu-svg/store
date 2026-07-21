from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.reports.accuracy_stats import trimmed_mean
from benchmark.reports.generate_report import generate_markdown_report


def test_trimmed_mean_known_values():
    assert trimmed_mean([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.1) == 5.5   # k=1，去 1 与 10
    assert trimmed_mean([0.2, 0.3, 0.9], 0.1) == (0.2 + 0.3 + 0.9) / 3  # k=0 不截


def test_trimmed_mean_edge_cases():
    assert trimmed_mean([], 0.1) == 0.0
    assert trimmed_mean([0.5], 0.1) == 0.5
    assert trimmed_mean([1, 100], 0.4) == 1.0 or trimmed_mean([1, 100], 0.4) == 50.5
    # n=2, k=0（int(2*0.4)=0）→ 不截，均值 50.5；断言以此为准：
    assert trimmed_mean([1, 100], 0.4) == 50.5


def test_report_lists_trimmed_mean_when_present():
    result = {
        "run_id": "t1", "provider": "deepseek", "model": "m", "method": "direct_choice",
        "prompt_version": "srp_v1", "reasoning_protocol": "xuanjizi_srp_v1",
        "choice_accuracy": {"accuracy": 0.5, "correct": 1, "total": 2},
        "evidence_score": 0.5, "safety_score": 1.0, "run_date": "2026-07-17",
        "accuracy_trimmed_mean": 0.475,
    }
    md = generate_markdown_report(result)
    assert "截尾均值" in md and "0.475" in md


def test_report_omits_trimmed_mean_when_absent():
    result = {
        "run_id": "t2", "provider": "deepseek", "model": "m", "method": "direct_choice",
        "prompt_version": "srp_v1", "reasoning_protocol": "xuanjizi_srp_v1",
        "choice_accuracy": {"accuracy": 0.5, "correct": 1, "total": 2},
        "evidence_score": 0.5, "safety_score": 1.0, "run_date": "2026-07-17",
    }
    assert "截尾均值" not in generate_markdown_report(result)
