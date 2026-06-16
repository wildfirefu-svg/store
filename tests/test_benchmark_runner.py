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
