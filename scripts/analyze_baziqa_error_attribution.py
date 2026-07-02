"""Error attribution analysis for BaziQA benchmark case details.

Reads per-case detail JSONL written by run_benchmark.py and produces a
Markdown report grouped by domain and parser source.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _iter_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def classify_error(row):
    if row.get('expected_answer') is None:
        return 'expected_unparseable'
    if not row.get('parser_valid'):
        return 'parser_invalid'
    if row.get('predicted_answer') != row.get('expected_answer'):
        return 'predicted_wrong'
    return 'correct'


def analyze_error_attribution(input_path):
    domain_stats = defaultdict(lambda: {'total': 0, 'correct': 0})
    error_counts = defaultdict(int)

    for row in _iter_jsonl(input_path):
        domain = row.get('domain', 'unknown')
        domain_stats[domain]['total'] += 1
        if row.get('correct'):
            domain_stats[domain]['correct'] += 1
        error_counts[classify_error(row)] += 1

    summary = []
    for domain, stats in sorted(domain_stats.items()):
        total = stats['total']
        correct = stats['correct']
        accuracy = correct / total if total else 0.0
        summary.append({
            'domain': domain,
            'total': total,
            'correct': correct,
            'accuracy': accuracy,
        })

    return {
        'domain_summary': summary,
        'error_counts': dict(error_counts),
        'total': sum(stats['total'] for stats in domain_stats.values()),
        'total_correct': sum(stats['correct'] for stats in domain_stats.values()),
    }


def build_report(result):
    lines = [
        '# BaziQA Error Attribution Report',
        '',
        '## Overall',
        '',
        f"- Total cases: {result['total']}",
        f"- Correct: {result['total_correct']}",
        f"- Accuracy: {result['total_correct'] / result['total']:.4f}" if result['total'] else '- Accuracy: N/A',
        '',
        '## Error Type Counts',
        '',
        '| error_type | count |',
        '|------------|-------|',
    ]
    for error_type, count in sorted(result['error_counts'].items()):
        lines.append(f'| {error_type} | {count} |')

    lines.extend([
        '',
        '## Accuracy by Domain',
        '',
        '| domain | total | correct | accuracy |',
        '|--------|-------|---------|----------|',
    ])
    for row in result['domain_summary']:
        lines.append(f"| {row['domain']} | {row['total']} | {row['correct']} | {row['accuracy']:.4f} |")

    lines.extend(['', '## Interpretation', '',
                  '- Domains with accuracy significantly below the overall mean are priority areas for corpus expansion or prompt tuning.',
                  '- A high `parser_invalid` count indicates the model is not following the confidence/final-answer output contract.',
                  '- A high `predicted_wrong` count indicates reasoning or retrieval gaps.',
                  ''])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Analyze BaziQA benchmark error attribution.')
    parser.add_argument('--case-details-jsonl', required=True, help='Path to per-case detail JSONL')
    parser.add_argument('--output', required=True, help='Path to output Markdown report')
    args = parser.parse_args(argv)

    result = analyze_error_attribution(args.case_details_jsonl)
    report = build_report(result)
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'Error attribution report saved to {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
