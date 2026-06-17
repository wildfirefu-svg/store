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
    monkeypatch.setattr(run_benchmark, 'call_model_sync', lambda prompt, provider, model: 'A')
    result = run_benchmark.run_model_benchmark(cases, 'deepseek', 'model', 'v1', max_cases=1)
    choice = run_benchmark.score_choice_answers(result['cases'], result['predictions'])
    assert choice['total'] == 1
    assert choice['correct'] == 1
    assert result['failed_cases'] == []


def test_run_model_benchmark_tracks_failures(monkeypatch):
    from benchmark.runners import run_benchmark

    cases = [{'case_id': 'q1', 'domain': 'career', 'answer': 'A', 'expected_evidence': []}]

    def fail(prompt, provider, model):
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
    assert '答案：A/B/C/D' in prompt



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

    def fake_call(messages, provider, model):
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
