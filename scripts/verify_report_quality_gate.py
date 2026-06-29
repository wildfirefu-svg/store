"""Validate generated BaZi reports text against deterministic chart rules.

Reads a JSONL file where each row contains `chart` and `report_text`, runs
bazi_report_validator.validate_report_claims, and produces a Markdown gate
report. The gate fails if any `error` severity issue is found.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bazi_report_validator import validate_report_claims


SEVERITY_ORDER = {'error': 0, 'warning': 1, 'info': 2}
IMPROVEMENT_TERMS = ('improved', 'improvement', 'outperform', 'outperformed', 'increase', 'gain', '提升', '更好', '优于')
BASELINE_TERMS = ('baseline', 'vs', 'versus', 'compared', 'compare', '基线', '对比')
BENCHMARK_TERMS = ('benchmark', 'ablation', 'accuracy', 'gate', 'retrieval', 'flash', 'pro', '准确率', '消融', '门禁')
ANSWER_DISTRIBUTION_TERMS = ('answer distribution', '答案分布', '选项分布')
LEAK_TERMS = ('retrieved_answer_leak', 'strict_leak', 'weak_leak', 'leak_ratio', 'leak', '泄漏')


def _iter_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _lower_text(text):
    return (text or '').lower()


def _contains_any(text, terms):
    lowered = _lower_text(text)
    return any(term in lowered for term in terms)


def _is_benchmark_report(row, report_text):
    if _contains_any(report_text, BENCHMARK_TERMS):
        return True
    return any(key in row for key in ('repeats', 'runs', 'accuracy', 'model_name', 'config_id'))


def _repeat_count(row):
    for key in ('repeats', 'runs', 'repeat_count', 'n_repeats'):
        value = row.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _has_non_empty_value(row, key):
    if key not in row:
        return False
    value = row.get(key)
    if value is None:
        return False
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) > 0
    return True


def _meta_quality_issues(row, report_text):
    issues = []
    claims_improvement = _contains_any(report_text, IMPROVEMENT_TERMS)
    if claims_improvement and not _contains_any(report_text, BASELINE_TERMS):
        issues.append({
            'severity': 'error',
            'code': 'missing_baseline_comparison',
            'message': 'Report claims an improvement but does not include a baseline comparison.',
        })

    repeats = _repeat_count(row)
    if claims_improvement and repeats is not None and repeats <= 1:
        issues.append({
            'severity': 'error',
            'code': 'insufficient_repeats_for_improvement',
            'message': 'Report claims an improvement from only one repeat; at least 2 repeats are required.',
        })

    if _is_benchmark_report(row, report_text):
        if not _has_non_empty_value(row, 'answer_distribution') and not _contains_any(report_text, ANSWER_DISTRIBUTION_TERMS):
            issues.append({
                'severity': 'warning',
                'code': 'missing_answer_distribution',
                'message': 'Benchmark-style report does not include answer distribution information.',
            })
        if not _has_non_empty_value(row, 'retrieved_answer_leak') and not _contains_any(report_text, LEAK_TERMS):
            issues.append({
                'severity': 'warning',
                'code': 'missing_retrieved_answer_leak',
                'message': 'Benchmark-style report does not include retrieved_answer_leak information.',
            })
    return issues


def verify_quality_gate(reports_jsonl):
    rows = list(_iter_jsonl(reports_jsonl))
    results = []
    for idx, row in enumerate(rows):
        chart = row.get('chart') or {}
        report_text = row.get('report_text') or ''
        issues = validate_report_claims(chart, report_text)
        issues.extend(_meta_quality_issues(row, report_text))
        errors = [i for i in issues if i.get('severity') == 'error']
        warnings = [i for i in issues if i.get('severity') == 'warning']
        results.append({
            'index': idx,
            'case_id': row.get('case_id', f'row_{idx}'),
            'n_issues': len(issues),
            'n_errors': len(errors),
            'n_warnings': len(warnings),
            'issues': issues,
            'passed': len(errors) == 0,
        })
    return results


def build_report(results):
    total = len(results)
    passed = sum(1 for r in results if r['passed'])
    failed = total - passed
    total_errors = sum(r['n_errors'] for r in results)
    total_warnings = sum(r['n_warnings'] for r in results)

    lines = [
        '# BaziQA Report Quality Gate',
        '',
        '## Summary',
        '',
        f'- Total reports: {total}',
        f'- Passed (no errors): {passed}',
        f'- Failed (>=1 error): {failed}',
        f'- Total errors: {total_errors}',
        f'- Total warnings: {total_warnings}',
        f'- Gate status: {"PASS" if failed == 0 else "FAIL"}',
        '',
        '## Per-Report Results',
        '',
        '| case_id | errors | warnings | status |',
        '|---------|--------|----------|--------|',
    ]
    for r in results:
        status = 'PASS' if r['passed'] else 'FAIL'
        lines.append(f"| {r['case_id']} | {r['n_errors']} | {r['n_warnings']} | {status} |")

    lines.extend(['', '## Issue Details', ''])
    for r in results:
        if not r['issues']:
            continue
        lines.append(f"### {r['case_id']}")
        for issue in r['issues']:
            lines.append(f"- **{issue['severity']}** ({issue['code']}): {issue['message']}")
        lines.append('')

    if failed == 0:
        lines.append('Gate passed: no deterministic factual errors found in any report.')
    else:
        lines.append(f'Gate failed: {failed} report(s) contain hard errors that contradict the chart.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate BaZi reports against chart rules.')
    parser.add_argument('--reports-jsonl', required=True, help='JSONL with chart and report_text fields')
    parser.add_argument('--output', required=True, help='Path to Markdown report')
    args = parser.parse_args(argv)

    results = verify_quality_gate(args.reports_jsonl)
    report = build_report(results)
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'Report quality gate saved to {args.output}')

    failed = sum(1 for r in results if not r['passed'])
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
