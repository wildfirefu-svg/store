import json


def test_benchmark_cli_accepts_option_grounded_flags(monkeypatch, tmp_path, capsys):
    from benchmark.runners import run_benchmark

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"c1","domain":"career","question":"事业?","options":["A 升迁","B 婚姻","C 疾病","D 财运"],"answer":"A"}\n',
        encoding="utf-8",
    )
    seen = {}

    def fake_call(prompt, provider, model, **kwargs):
        seen.update(kwargs)
        return "最终答案：A"

    monkeypatch.setattr(run_benchmark, "call_model_sync", fake_call)
    monkeypatch.setattr(run_benchmark.time, "sleep", lambda *_: None)

    rc = run_benchmark.main([
        "--dataset", str(dataset),
        "--model-runner",
        "--max-cases", "1",
        "--method", "direct_choice",
        "--output-dir", str(tmp_path / "out"),
        "--retrieval-mode", "option_grounded",
        "--option-evidence-k", "2",
    ])

    assert rc == 0
    assert seen["retrieval_mode"] == "option_grounded"
    assert seen["option_evidence_k"] == 2


def test_model_benchmark_traces_option_grounded_evidence(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    cases = [{
        "case_id": "c1",
        "domain": "career",
        "question": "事业?",
        "options": ["A 升迁", "B 婚姻", "C 疾病", "D 财运"],
        "answer": "A",
    }]

    def fake_option_trace(case, k=2):
        return (
            {
                "A": [{"case_id": "ca", "person_id": "pa", "score": 1.2, "match_reasons": ["option_overlap:升迁"], "fact_excerpt": "事业 -> 升迁"}],
                "B": [],
                "C": [],
                "D": [],
            },
            {"A": 1, "B": 0, "C": 0, "D": 0},
        )

    monkeypatch.setattr(run_benchmark, "call_model_sync", lambda *args, **kwargs: "最终答案：A")
    monkeypatch.setattr(run_benchmark, "_resolve_rag_trace", lambda case, k=2: [])
    monkeypatch.setattr(run_benchmark, "_resolve_option_evidence_trace", fake_option_trace, raising=False)
    monkeypatch.setattr(run_benchmark.time, "sleep", lambda *_: None)

    details = tmp_path / "details.jsonl"
    result = run_benchmark.run_model_benchmark(
        cases,
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_version="v1",
        max_cases=1,
        method="direct_choice",
        case_details_jsonl=str(details),
        retrieval_mode="option_grounded",
        option_evidence_k=2,
    )

    detail = result["case_details"][0]
    assert detail["retrieval_mode"] == "option_grounded"
    assert detail["option_evidence"]["A"][0]["person_id"] == "pa"
    assert detail["option_evidence_coverage"] == {"A": 1, "B": 0, "C": 0, "D": 0}
    assert detail["retrieved_answer_leak"] is False

    rows = [json.loads(line) for line in details.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["retrieval_mode"] == "option_grounded"
    assert rows[0]["option_evidence"]["A"][0]["match_reasons"] == ["option_overlap:升迁"]
