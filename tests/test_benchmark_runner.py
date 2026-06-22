import json
import subprocess
import sys

from benchmark.runners.run_benchmark import run_offline_benchmark


def test_run_offline_benchmark_scores_predictions():
    cases = [
        {'case_id': 'q1', 'domain': 'career', 'answer': 'A'},
        {'case_id': 'q2', 'domain': 'wealth', 'answer': 'B'},
    ]
    preds = {'q1': 'A', 'q2': 'C'}
    result = run_offline_benchmark(cases, preds)
    assert result['accuracy'] == 0.5
    assert result['total'] == 2
    assert result['correct'] == 1


def test_run_benchmark_script_path_cli(tmp_path):
    predictions = tmp_path / 'predictions.json'
    predictions.write_text(json.dumps({'career_001': 'A'}, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        [
            sys.executable,
            'benchmark/runners/run_benchmark.py',
            '--dataset',
            'benchmark/datasets/baziqa_mini_v1.jsonl',
            '--predictions',
            str(predictions),
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output['total'] >= 5
    assert output['correct'] >= 1


def test_run_model_benchmark_respects_limited_cases(monkeypatch):
    from benchmark.runners import run_benchmark

    cases = [
        {'case_id': 'q1', 'domain': 'career', 'answer': 'A', 'expected_evidence': []},
        {'case_id': 'q2', 'domain': 'wealth', 'answer': 'B', 'expected_evidence': []},
        {'case_id': 'q3', 'domain': 'health', 'answer': 'C', 'expected_evidence': []},
    ]
    monkeypatch.setattr(run_benchmark, 'call_model_sync', lambda prompt, provider, model, **kwargs: 'A')
    result = run_benchmark.run_model_benchmark(cases, 'deepseek', 'model', 'v1', max_cases=1)
    choice = run_benchmark.score_choice_answers(result['cases'], result['predictions'])
    assert choice['total'] == 1
    assert choice['correct'] == 1
    assert result['failed_cases'] == []


def test_run_model_benchmark_tracks_failures(monkeypatch):
    from benchmark.runners import run_benchmark

    cases = [{'case_id': 'q1', 'domain': 'career', 'answer': 'A', 'expected_evidence': []}]

    def fail(prompt, provider, model, **kwargs):
        raise RuntimeError('model_call_failed: RuntimeError')

    monkeypatch.setattr(run_benchmark, 'call_model_sync', fail)
    result = run_benchmark.run_model_benchmark(cases, 'deepseek', 'model', 'v1', max_cases=1)
    assert result['predictions'] == {}
    assert result['failed_cases'][0]['case_id'] == 'q1'



def test_build_prompt_supports_direct_choice():
    from benchmark.runners import run_benchmark

    case = {
        'case_id': 'q1',
        'domain': 'career',
        'person': {'name': '命主', 'gender': 'male', 'birth': {'year': 1990, 'month': 1, 'day': 1, 'hour': 9, 'minute': 0, 'place': '北京'}},
        'question': '事业如何？',
        'options': ['A. 稳定', 'B. 投机', 'C. 不工作', 'D. 随机'],
    }

    prompt = run_benchmark.build_benchmark_prompt(case, method='direct_choice')
    assert '请直接回答选项字母' in prompt


def test_build_prompt_supports_structured_reasoning():
    from benchmark.runners import run_benchmark

    case = {
        'case_id': 'q1',
        'domain': 'career',
        'person': {'name': '命主', 'gender': 'male', 'birth': {'year': 1990, 'month': 1, 'day': 1, 'hour': 9, 'minute': 0, 'place': '北京'}},
        'question': '事业如何？',
        'options': ['A. 稳定', 'B. 投机', 'C. 不工作', 'D. 随机'],
    }

    prompt = run_benchmark.build_benchmark_prompt(case, method='structured_reasoning')
    assert '第一阶段：量化扫描' in prompt
    assert '最终答案：X' in prompt



def test_multi_turn_groups_questions_by_person(monkeypatch):
    from benchmark.runners import run_benchmark

    cases = [
        {
            'case_id': 'p1-q1',
            'domain': 'career',
            'person': {'person_id': 'p1', 'name': '甲', 'gender': 'male', 'birth': {'year': 1990, 'month': 1, 'day': 1, 'hour': 9, 'minute': 0, 'place': '北京'}},
            'question': '事业如何？',
            'options': ['A. 稳定', 'B. 投机', 'C. 不工作', 'D. 随机'],
            'answer': 'A',
        },
        {
            'case_id': 'p1-q2',
            'domain': 'wealth',
            'person': {'person_id': 'p1', 'name': '甲', 'gender': 'male', 'birth': {'year': 1990, 'month': 1, 'day': 1, 'hour': 9, 'minute': 0, 'place': '北京'}},
            'question': '财运如何？',
            'options': ['A. 稳定', 'B. 投机', 'C. 一般', 'D. 较差'],
            'answer': 'B',
        },
        {
            'case_id': 'p2-q1',
            'domain': 'health',
            'person': {'person_id': 'p2', 'name': '乙', 'gender': 'female', 'birth': {'year': 1992, 'month': 2, 'day': 2, 'hour': 10, 'minute': 0, 'place': '上海'}},
            'question': '健康如何？',
            'options': ['A. 良好', 'B. 一般', 'C. 偏弱', 'D. 重病'],
            'answer': 'A',
        },
    ]

    captured = []

    def fake_call(messages, provider, model, **kwargs):
        captured.append(list(messages))
        return cases[len(captured) - 1]['answer']

    monkeypatch.setattr(run_benchmark, 'call_model_messages_with_history', fake_call)
    monkeypatch.setattr(run_benchmark.time, 'sleep', lambda *_: None)

    result = run_benchmark.run_model_benchmark(
        cases, 'deepseek', 'deepseek-v4-pro', 'prompt_v1',
        max_cases=10, method='multi_turn',
    )

    assert result['predictions'] == {'p1-q1': 'A', 'p1-q2': 'B', 'p2-q1': 'A'}
    assert len(captured) == 3
    # 第二轮 messages 应包含上一轮的 user/assistant 历史
    second_turn_roles = [m['role'] for m in captured[1]]
    assert second_turn_roles.count('assistant') >= 2
    assert second_turn_roles.count('user') >= 2
    # 第二轮最后一条是当前问题
    assert '财运' in captured[1][-1]['content']
    # 切到 p2 时不应携带 p1 的历史
    third_turn_user = [m['content'] for m in captured[2] if m['role'] == 'user']
    assert not any('事业如何' in c for c in third_turn_user)
    assert any('健康如何' in c for c in third_turn_user)


def test_model_benchmark_passes_temperature_to_model_call(monkeypatch):
    from benchmark.runners import run_benchmark

    seen = {}

    def fake_call(prompt, provider, model, case=None, temperature=None, rag_k=2):
        seen["temperature"] = temperature
        return "A"

    monkeypatch.setattr(run_benchmark, "call_model_sync", fake_call)
    cases = [{
        "case_id": "case-1",
        "question": "事业?",
        "options": ["A 好", "B 差", "C 平", "D 无"],
        "answer": "A",
        "domain": "career",
    }]

    result = run_benchmark.run_model_benchmark(
        cases,
        provider="deepseek",
        model="deepseek-v4-pro",
        prompt_version="srp_v1",
        max_cases=1,
        method="direct_choice",
        temperature=0.0,
    )

    assert result["predictions"]["case-1"] == "A"
    assert seen["temperature"] == 0.0


def test_model_benchmark_defaults_rag_k_to_two(monkeypatch):
    from benchmark.runners import run_benchmark

    seen = {}

    def fake_call(prompt, provider, model, case=None, temperature=None, rag_k=0):
        seen["rag_k"] = rag_k
        return "A"

    monkeypatch.setattr(run_benchmark, "call_model_sync", fake_call)
    cases = [{
        "case_id": "case-1",
        "question": "事业?",
        "options": ["A 好", "B 差", "C 平", "D 无"],
        "answer": "A",
        "domain": "career",
    }]

    result = run_benchmark.run_model_benchmark(
        cases,
        provider="deepseek",
        model="deepseek-v4-pro",
        prompt_version="srp_v1",
        max_cases=1,
        method="direct_choice",
        temperature=0.0,
    )

    assert result["case_details"][0]["rag_k"] == 2
    assert seen["rag_k"] == 2


def test_model_benchmark_records_parser_meta(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    cases = [{
        "case_id": "c1",
        "domain": "wealth",
        "answer": "B",
        "person": {"birth": {"year": 1990, "month": 1, "day": 1, "hour": 0, "minute": 0}},
        "question": "哪项更符合命局？",
        "options": ["A. 木旺", "B. 火旺", "C. 金旺", "D. 水旺"],
    }]

    monkeypatch.setattr(
        run_benchmark,
        "call_model_sync",
        lambda *args, **kwargs: "A: 20\nB: 80\nC: 10\nD: 5\n最终答案：B",
    )

    details = tmp_path / "details.jsonl"
    result = run_benchmark.run_model_benchmark(
        cases,
        provider="deepseek",
        model="deepseek-v4-pro",
        prompt_version="srp_v1",
        max_cases=1,
        method="structured_reasoning",
        temperature=0.0,
        case_details_jsonl=str(details),
        rag_k=2,
    )

    detail = result["case_details"][0]
    assert detail["predicted_answer"] == "B"
    assert detail["parser_source"] == "final_answer"
    assert detail["parser_valid"] is True
    assert detail["rag_k"] == 2


def test_benchmark_cli_prints_exact_accuracy(monkeypatch, tmp_path, capsys):
    from benchmark.runners import run_benchmark

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"c1","question":"?","options":["A","B","C","D"],"answer":"A"}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(run_benchmark, "call_model_sync", lambda *args, **kwargs: "A")
    rc = run_benchmark.main([
        "--dataset", str(dataset),
        "--model-runner",
        "--max-cases", "1",
        "--method", "direct_choice",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert "AccuracyExact: 1/1=1.000000" in out


def test_model_benchmark_writes_case_details_jsonl(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    dataset = tmp_path / "cases.jsonl"
    details = tmp_path / "details.jsonl"
    dataset.write_text(
        '{"case_id":"c1","domain":"career","question":"事业?","options":["A","B","C","D"],"answer":"A"}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(run_benchmark, "call_model_sync", lambda *args, **kwargs: "答案：A")
    rc = run_benchmark.main([
        "--dataset", str(dataset),
        "--model-runner",
        "--max-cases", "1",
        "--method", "direct_choice",
        "--case-details-jsonl", str(details),
    ])

    assert rc == 0
    rows = [json.loads(line) for line in details.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["case_id"] == "c1"
    assert rows[0]["expected_answer"] == "A"
    assert rows[0]["predicted_answer"] == "A"
    assert rows[0]["raw_answer"] == "答案：A"
    assert rows[0]["rag_trace"] == []


def test_case_details_jsonl_keeps_completed_rows_on_later_failure(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    cases = [
        {"case_id": "c1", "domain": "career", "question": "事业?", "options": ["A", "B", "C", "D"], "answer": "A"},
        {"case_id": "c2", "domain": "career", "question": "事业?", "options": ["A", "B", "C", "D"], "answer": "B"},
    ]
    details = tmp_path / "partial.jsonl"
    calls = {"n": 0}

    def fake_call(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("model_call_failed: boom")
        return "A"

    monkeypatch.setattr(run_benchmark, "call_model_sync", fake_call)
    result = run_benchmark.run_model_benchmark(
        cases,
        "deepseek",
        "model",
        "v1",
        max_cases=2,
        method="direct_choice",
        case_details_jsonl=str(details),
    )

    assert result["failed_cases"][0]["case_id"] == "c2"
    rows = [json.loads(line) for line in details.read_text(encoding="utf-8").splitlines()]
    assert [r["case_id"] for r in rows] == ["c1"]


def test_resolve_rag_trace_includes_retrieved_cases(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(json.dumps({
        "case_id": "p1-q1",
        "domain": "career",
        "question": "事业?",
        "answer": "A",
        "options": ["A", "B", "C", "D"],
        "person": {
            "person_id": "p1",
            "name": "甲",
            "gender": "male",
            "birth": {"year": 1980, "month": 1, "day": 1, "hour": 8},
        },
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setenv("BAZI_RAG", "1")
    monkeypatch.setenv("BAZI_RAG_CORPUS", str(corpus))
    run_benchmark._BENCH_CASE_INDEX = None
    run_benchmark._BENCH_CASE_INDEX_PATH = None

    trace = run_benchmark._resolve_rag_trace({
        "case_id": "c1",
        "domain": "career",
        "person": {"gender": "male", "birth": {"year": 1980}},
    })

    assert trace[0]["rank"] == 1
    assert trace[0]["person_id"] == "p1"


def test_case_details_records_retrieved_answer_leak(monkeypatch, tmp_path):
    """Single-turn case_details must mark retrieved_answer_leak based on whether
    any retrieved fact string contains the expected answer letter.
    """
    from benchmark.runners import run_benchmark

    cases = [
        {
            "case_id": "leak-case",
            "domain": "wealth",
            "question": "财运?",
            "options": ["A", "B", "C", "D"],
            "answer": "B",
        },
        {
            "case_id": "clean-case",
            "domain": "wealth",
            "question": "财运?",
            "options": ["A", "B", "C", "D"],
            "answer": "C",
        },
    ]

    def fake_trace(case, k=2):
        if case["case_id"] == "leak-case":
            return [{"rank": 1, "person_id": "p1", "facts": ["命主最终选 B 选项"]}]
        return [{"rank": 1, "person_id": "p2", "facts": ["命主家境普通，无明显应期"]}]

    monkeypatch.setattr(run_benchmark, "_resolve_rag_trace", fake_trace)
    monkeypatch.setattr(run_benchmark, "call_model_sync", lambda *a, **k: "答案：A")

    details = tmp_path / "leak_trace.jsonl"
    result = run_benchmark.run_model_benchmark(
        cases,
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_version="v1",
        max_cases=2,
        method="direct_choice",
        case_details_jsonl=str(details),
    )

    by_id = {d["case_id"]: d for d in result["case_details"]}
    assert by_id["leak-case"]["retrieved_answer_leak"] is True
    assert by_id["clean-case"]["retrieved_answer_leak"] is False

    rows = [json.loads(line) for line in details.read_text(encoding="utf-8").splitlines()]
    persisted = {r["case_id"]: r for r in rows}
    assert persisted["leak-case"]["retrieved_answer_leak"] is True
    assert persisted["clean-case"]["retrieved_answer_leak"] is False


def test_multi_turn_case_details_records_retrieved_answer_leak(monkeypatch):
    """Multi-turn (grouped-by-person) case_details must also mark
    retrieved_answer_leak per case.
    """
    from benchmark.runners import run_benchmark

    cases = [
        {
            "case_id": "p1-q1",
            "domain": "career",
            "person": {"person_id": "p1", "name": "甲", "gender": "male", "birth": {"year": 1990, "month": 1, "day": 1, "hour": 9, "minute": 0, "place": "北京"}},
            "question": "事业如何？",
            "options": ["A. 稳定", "B. 投机", "C. 不工作", "D. 随机"],
            "answer": "A",
        },
        {
            "case_id": "p1-q2",
            "domain": "wealth",
            "person": {"person_id": "p1", "name": "甲", "gender": "male", "birth": {"year": 1990, "month": 1, "day": 1, "hour": 9, "minute": 0, "place": "北京"}},
            "question": "财运如何？",
            "options": ["A. 稳定", "B. 投机", "C. 一般", "D. 较差"],
            "answer": "B",
        },
    ]

    def fake_trace(case, k=2):
        if case["case_id"] == "p1-q1":
            return [{"rank": 1, "person_id": "p1", "facts": ["命主事业方向选 A"]}]
        return [{"rank": 1, "person_id": "p1", "facts": ["命主财源一般，未见暴富"]}]

    monkeypatch.setattr(run_benchmark, "_resolve_rag_trace", fake_trace)
    monkeypatch.setattr(run_benchmark, "call_model_sync", lambda *a, **k: "答案：A")

    result = run_benchmark.run_model_benchmark(
        cases,
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_version="v1",
        max_cases=2,
        method="multi_turn",
    )

    by_id = {d["case_id"]: d for d in result["case_details"]}
    assert by_id["p1-q1"]["retrieved_answer_leak"] is True
    assert by_id["p1-q2"]["retrieved_answer_leak"] is False
