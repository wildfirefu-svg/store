"""Integration tests for --n-samples / --sample-temperature / --aggregate in
the benchmark runner.

Covers:
- run_model_benchmark(n_samples=3) calls the model 3 times per case, applies
  majority_vote, and writes per-sample records into detail["samples"].
- Backward compatibility: n_samples=1 (default) produces the same detail schema
  as before (no `samples` / `n_samples` / `aggregate` keys).
- Combined with shuffle-options: sampled predictions use shuffled labels and
  are still scored correctly against the shuffled expected label.
- aggregate="unknown" raises ValueError.
- CLI: run_benchmark.main([..., "--n-samples", "3", "--sample-temperature", "0.5"])
  forwards all three calls with temperature=0.5.
"""

from __future__ import annotations

import copy
import json

import pytest


_BASE_CASE = {
    "case_id": "c1",
    "domain": "career",
    "question": "命主家境如何?",
    "options": ["A. 富裕", "B. 贫穷", "C. 父从商母是村干部", "D. 父母当官"],
    "answer": "B",
}


def _patch_common(monkeypatch, run_benchmark, fake_call):
    monkeypatch.setattr(run_benchmark, "call_model_sync", fake_call)
    monkeypatch.setattr(run_benchmark.time, "sleep", lambda *_: None)
    monkeypatch.setattr(run_benchmark, "_resolve_rag_trace", lambda case, k=2: [])
    monkeypatch.setattr(
        run_benchmark,
        "_resolve_option_evidence_trace",
        lambda case, k=2: ({}, {}),
        raising=False,
    )


def test_run_model_benchmark_n_samples_majority_vote(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    votes = iter(["最终答案：A", "最终答案：B", "最终答案：B"])
    seen_temperatures = []

    def fake_call(prompt, provider, model, **kwargs):
        seen_temperatures.append(kwargs.get("temperature"))
        return next(votes)

    _patch_common(monkeypatch, run_benchmark, fake_call)

    result = run_benchmark.run_model_benchmark(
        [copy.deepcopy(_BASE_CASE)],
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_version="v1",
        max_cases=1,
        method="direct_choice",
        case_details_jsonl=str(tmp_path / "d.jsonl"),
        retrieval_mode="legacy",
        option_evidence_k=2,
        n_samples=3,
        sample_temperature=0.5,
    )

    assert seen_temperatures == [0.5, 0.5, 0.5]

    detail = result["case_details"][0]
    assert detail["predicted_answer"] == "B"
    assert detail["correct"] is True
    assert detail["n_samples"] == 3
    assert detail["aggregate"] == "majority"
    assert [s["predicted"] for s in detail["samples"]] == ["A", "B", "B"]
    assert detail["samples"][0]["raw"] == "最终答案：A"
    # raw_answer must reflect the majority-vote winner's first matching sample raw,
    # not samples[0] (which may be a minority vote).
    assert detail["raw_answer"] == "最终答案：B"


def test_run_model_benchmark_default_n_samples_stays_backward_compatible(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    _patch_common(
        monkeypatch,
        run_benchmark,
        lambda prompt, provider, model, **kwargs: "最终答案：B",
    )

    result = run_benchmark.run_model_benchmark(
        [copy.deepcopy(_BASE_CASE)],
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_version="v1",
        max_cases=1,
        method="direct_choice",
        case_details_jsonl=str(tmp_path / "d.jsonl"),
        retrieval_mode="legacy",
        option_evidence_k=2,
    )

    detail = result["case_details"][0]
    assert "samples" not in detail
    assert "n_samples" not in detail
    assert "aggregate" not in detail
    assert detail["correct"] is True


def test_run_model_benchmark_rejects_unknown_aggregate(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    _patch_common(
        monkeypatch,
        run_benchmark,
        lambda prompt, provider, model, **kwargs: "最终答案：B",
    )

    with pytest.raises(ValueError):
        run_benchmark.run_model_benchmark(
            [copy.deepcopy(_BASE_CASE)],
            provider="deepseek",
            model="deepseek-v4-flash",
            prompt_version="v1",
            max_cases=1,
            method="direct_choice",
            case_details_jsonl=str(tmp_path / "d.jsonl"),
            retrieval_mode="legacy",
            option_evidence_k=2,
            n_samples=3,
            aggregate="unknown_agg",
        )


def test_run_model_benchmark_n_samples_composes_with_shuffle_options(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    captured_cases = []

    def fake_call(prompt, provider, model, **kwargs):
        case = kwargs.get("case") or {}
        captured_cases.append(copy.deepcopy(case))
        return f"最终答案：{case['answer']}"

    _patch_common(monkeypatch, run_benchmark, fake_call)

    result = run_benchmark.run_model_benchmark(
        [copy.deepcopy(_BASE_CASE)],
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_version="v1",
        max_cases=1,
        method="direct_choice",
        case_details_jsonl=str(tmp_path / "d.jsonl"),
        retrieval_mode="legacy",
        option_evidence_k=2,
        shuffle_options=True,
        shuffle_seed=42,
        n_samples=3,
        sample_temperature=0.5,
    )

    detail = result["case_details"][0]
    assert detail["correct"] is True
    assert detail["original_expected_answer"] == "B"
    assert detail["original_predicted_answer"] == "B"
    assert detail["n_samples"] == 3
    assert len(captured_cases) == 3
    for case in captured_cases:
        assert case["options"] == captured_cases[0]["options"]


def test_benchmark_cli_forwards_n_samples_flags(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps(_BASE_CASE, ensure_ascii=False) + "\n", encoding="utf-8")

    temperatures = []

    def fake_call(prompt, provider, model, **kwargs):
        temperatures.append(kwargs.get("temperature"))
        return "最终答案：B"

    _patch_common(monkeypatch, run_benchmark, fake_call)

    rc = run_benchmark.main([
        "--dataset", str(dataset),
        "--model-runner",
        "--max-cases", "1",
        "--method", "direct_choice",
        "--output-dir", str(tmp_path / "out"),
        "--n-samples", "3",
        "--sample-temperature", "0.5",
    ])

    assert rc == 0
    assert temperatures == [0.5, 0.5, 0.5]
