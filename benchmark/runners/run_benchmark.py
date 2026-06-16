import argparse
import json
import os
import sys

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from benchmark.scorers.choice_accuracy import load_jsonl, score_choice_answers


def run_offline_benchmark(cases, predictions):
    return score_choice_answers(cases, predictions)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run offline BaziQA-style choice benchmark')
    parser.add_argument('--dataset', required=True, help='Path to JSONL dataset')
    parser.add_argument('--predictions', required=True, help='Path to JSON predictions map')
    args = parser.parse_args(argv)

    cases = load_jsonl(args.dataset)
    with open(args.predictions, 'r', encoding='utf-8') as f:
        predictions = json.load(f)
    result = run_offline_benchmark(cases, predictions)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
