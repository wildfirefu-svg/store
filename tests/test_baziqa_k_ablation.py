import json
import os
from pathlib import Path

from scripts import run_baziqa_k_ablation


def test_run_k_ablation_produces_summary_and_report(tmp_path, monkeypatch):
    records = []

    def fake_run_model_benchmark(cases, provider, model, prompt_version, max_cases, method, temperature, case_details_jsonl, rag_k):
        records.append(rag_k)
        correct = rag_k
        total = 4
        case_details = [{"correct": i < correct} for i in range(total)]
        return {
            "case_details": case_details,
            "failed_cases": [],
        }

    monkeypatch.setattr(run_baziqa_k_ablation, "run_model_benchmark", fake_run_model_benchmark)
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text("{}", encoding="utf-8")

    output = tmp_path / "report.md"
    summary = run_baziqa_k_ablation.run_k_ablation(
        dataset=str(dataset),
        provider="deepseek",
        model="deepseek-v4-pro",
        method="structured_reasoning",
        temperature=0.0,
        max_cases=4,
        repeats=2,
        output=str(output),
    )

    assert len(records) == 6
    assert summary[0]["k"] == 1
    assert summary[0]["mean"] == 0.25
    assert summary[-1]["k"] == 3
    assert summary[-1]["mean"] == 0.75
