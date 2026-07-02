"""Integration tests for --shuffle-options / --shuffle-seed in the benchmark runner.

Covers:
- run_model_benchmark(shuffle_options=True, shuffle_seed=SEED) rewrites options and answer,
  writes back the mapping into case_details, and scores against the shuffled label.
- unshuffle_predicted_answer round-trip: the original expected answer is preserved
  in detail["original_expected_answer"] and reflects the pre-shuffle label.
- Default behaviour (no shuffle) is unchanged: no answer_label_map field.
- CLI: run_benchmark.main([..., "--shuffle-options", "--shuffle-seed", "42"]) forwards
  a shuffled case to call_model_sync (options prefixes are rewritten in place).
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


def _patch_common(monkeypatch, run_benchmark, fake_answer_provider):
    monkeypatch.setattr(run_benchmark, "call_model_sync", fake_answer_provider)
    monkeypatch.setattr(run_benchmark.time, "sleep", lambda *_: None)
    monkeypatch.setattr(run_benchmark, "_resolve_rag_trace", lambda case, k=2: [])
    monkeypatch.setattr(
        run_benchmark,
        "_resolve_option_evidence_trace",
        lambda case, k=2: ({}, {}),
        raising=False,
    )


def test_run_model_benchmark_shuffle_options_rewrites_options_and_answer(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    captured_cases = []

    def fake_call(prompt, provider, model, **kwargs):
        case = kwargs.get("case") or {}
        captured_cases.append(copy.deepcopy(case))
        return f"最终答案：{case['answer']}"

    _patch_common(monkeypatch, run_benchmark, fake_call)

    input_cases = [copy.deepcopy(_BASE_CASE)]
    details = tmp_path / "details.jsonl"

    result = run_benchmark.run_model_benchmark(
        input_cases,
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_version="v1",
        max_cases=1,
        method="direct_choice",
        case_details_jsonl=str(details),
        retrieval_mode="legacy",
        option_evidence_k=2,
        shuffle_options=True,
        shuffle_seed=42,
    )

    assert input_cases == [_BASE_CASE], "input cases must not be mutated"

    shuffled_case = captured_cases[0]
    assert shuffled_case["answer"] != "B" or shuffled_case["options"] != _BASE_CASE["options"]
    assert set(shuffled_case["answer_label_map"].keys()) == {"A", "B", "C", "D"}
    assert set(shuffled_case["answer_label_map"].values()) == {"A", "B", "C", "D"}

    detail = result["case_details"][0]
    assert detail["answer_label_map"] == shuffled_case["answer_label_map"]
    assert detail["original_expected_answer"] == "B"
    assert detail["expected_answer"] == shuffled_case["answer"]
    assert detail["original_predicted_answer"] == "B"
    assert detail["correct"] is True

    row = json.loads(details.read_text(encoding="utf-8").splitlines()[0])
    assert row["answer_label_map"] == shuffled_case["answer_label_map"]
    assert row["original_expected_answer"] == "B"
    assert row["correct"] is True


def test_run_model_benchmark_shuffle_options_marks_wrong_answer(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    def fake_call(prompt, provider, model, **kwargs):
        return "最终答案：A"

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
    )

    detail = result["case_details"][0]
    assert detail["original_expected_answer"] == "B"
    if detail["answer_label_map"]["B"] == "A":
        assert detail["correct"] is True
        assert detail["original_predicted_answer"] == "B"
    else:
        assert detail["correct"] is False
        assert detail["original_predicted_answer"] != "B"


def test_run_model_benchmark_without_shuffle_stays_identical(monkeypatch, tmp_path):
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
    assert "answer_label_map" not in detail
    assert "original_expected_answer" not in detail
    assert "original_predicted_answer" not in detail
    assert detail["expected_answer"] == "B"
    assert detail["correct"] is True


def test_run_model_benchmark_shuffle_options_requires_seed(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    _patch_common(
        monkeypatch,
        run_benchmark,
        lambda prompt, provider, model, **kwargs: "最终答案：A",
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
            shuffle_options=True,
            shuffle_seed=None,
        )


def test_benchmark_cli_forwards_shuffle_options_flags(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps(_BASE_CASE, ensure_ascii=False) + "\n", encoding="utf-8")

    captured = {}

    def fake_call(prompt, provider, model, **kwargs):
        case = kwargs.get("case") or {}
        captured["case"] = copy.deepcopy(case)
        return f"最终答案：{case['answer']}"

    _patch_common(monkeypatch, run_benchmark, fake_call)

    rc = run_benchmark.main([
        "--dataset", str(dataset),
        "--model-runner",
        "--max-cases", "1",
        "--method", "direct_choice",
        "--output-dir", str(tmp_path / "out"),
        "--shuffle-options",
        "--shuffle-seed", "42",
    ])

    assert rc == 0
    case = captured["case"]
    assert "answer_label_map" in case
    for idx, option in enumerate(case["options"]):
        expected_letter = chr(ord("A") + idx)
        assert option.startswith(f"{expected_letter}. "), option
