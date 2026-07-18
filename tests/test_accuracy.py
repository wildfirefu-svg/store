#!/usr/bin/env python3
"""P5 Accuracy Test — cross-validate BaZi calculator against known-correct charts."""

import json, os, sys, time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from bazi_calculator import calculate_four_pillars, calculate_dayun

def run_tests(suite='test_charts.json'):
    test_path = os.path.join(os.path.dirname(__file__), suite)
    if not os.path.exists(test_path):
        test_path = os.path.join(os.path.dirname(__file__), 'test_charts.json')
    with open(test_path, encoding='utf-8') as f:
        data = json.load(f)

    cases = data['test_cases']
    results = []
    errors = []

    t0 = time.time()
    for tc in cases:
        rid = tc['id']
        y, m, d, h = tc['year'], tc['month'], tc['day'], tc['hour']
        gender = tc['gender']
        exp = tc['expected']

        fp = calculate_four_pillars(y, m, d, h, 0, 'Beijing')
        year_p = (fp['year']['gan'], fp['year']['zhi'])
        month_p = (fp['month']['gan'], fp['month']['zhi'])
        dayun = calculate_dayun(year_p, month_p, gender, y, m, d)

        checks = {}
        if 'year' in exp:
            checks['year'] = f"{fp['year']['gan']}{fp['year']['zhi']}" == exp['year']
        if 'month' in exp:
            checks['month'] = f"{fp['month']['gan']}{fp['month']['zhi']}" == exp['month']
        if 'day' in exp:
            checks['day'] = f"{fp['day']['gan']}{fp['day']['zhi']}" == exp['day']
        if 'hour' in exp:
            checks['hour'] = f"{fp['hour']['gan']}{fp['hour']['zhi']}" == exp['hour']
        if 'day_master' in exp:
            checks['day_master'] = fp['day_master'] == exp['day_master']
        if 'dayun_dir' in exp:
            checks['dayun_dir'] = dayun['direction'] == exp['dayun_dir']

        all_pass = all(checks.values())
        results.append(all_pass)

        if not all_pass:
            failures = [k for k, v in checks.items() if not v]
            got = {}
            for k in checks:
                if k == 'year': got['year'] = f"{fp['year']['gan']}{fp['year']['zhi']}"
                elif k == 'month': got['month'] = f"{fp['month']['gan']}{fp['month']['zhi']}"
                elif k == 'day': got['day'] = f"{fp['day']['gan']}{fp['day']['zhi']}"
                elif k == 'hour': got['hour'] = f"{fp['hour']['gan']}{fp['hour']['zhi']}"
                elif k == 'day_master': got['day_master'] = fp['day_master']
                elif k == 'dayun_dir': got['dayun_dir'] = dayun['direction']
            detail = {
                'id': rid, 'note': tc.get('note', ''),
                'failures': failures,
                'expected': {k: exp[k] for k in checks},
                'got': got,
            }
            errors.append(detail)

    elapsed = time.time() - t0
    total = len(cases)
    passed = sum(results)
    accuracy = (passed / total) * 100 if total > 0 else 0

    # Report
    report = {
        'test_date': '2026-05-19',
        'total_cases': total,
        'passed': passed,
        'failed': total - passed,
        'accuracy_pct': round(accuracy, 2),
        'elapsed_sec': round(elapsed, 2),
        'validation_rules': data['validation_rules'],
    }

    if errors:
        report['error_details'] = errors
        # Categorize errors
        fail_types = Counter()
        for e in errors:
            for f in e['failures']:
                fail_types[f] += 1
        report['error_summary'] = dict(fail_types)

    return report

def test_golden_accuracy():
    """pytest 入口：100 例金标四柱/大运回归（原 run_tests 脚本接入 pytest 收集）。

    run_tests() 本身不写文件；但 __main__ 脚本模式会重写跟踪文件 accuracy_report.json，
    为防止该写逻辑未来被移入 run_tests，这里先备份、结束后恢复（当前为无害空操作）。
    """
    report_path = os.path.join(os.path.dirname(__file__), 'accuracy_report.json')
    backup = None
    if os.path.exists(report_path):
        with open(report_path, 'rb') as f:
            backup = f.read()
    try:
        report = run_tests()
    finally:
        if backup is not None:
            with open(report_path, 'wb') as f:
                f.write(backup)
    assert report['failed'] == 0, (
        f"{report['failed']}/{report['total_cases']} 例金标失败: "
        f"{json.dumps(report.get('error_details', [])[:5], ensure_ascii=False)}"
    )

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', default='test_charts.json', help='Test suite JSON file')
    args = ap.parse_args()
    report = run_tests(args.suite)

    print(f"=== BaZi Calculator Accuracy Test ===")
    print(f"Total: {report['total_cases']} | Passed: {report['passed']} | Failed: {report['failed']}")
    print(f"Accuracy: {report['accuracy_pct']}% | Time: {report['elapsed_sec']}s")
    print()

    if report['failed'] > 0:
        print(f"=== Failed Cases ({report['failed']}) ===")
        if 'error_summary' in report:
            print(f"Error distribution: {report['error_summary']}")
        print()
        for e in report.get('error_details', [])[:10]:
            print(f"  {e['id']} ({e['note']}): {e['failures']}")
            print(f"    Expected: {e['expected']}")
            print(f"    Got:      {e['got']}")
            print()

    # Save JSON report FIRST
    out_path = os.path.join(os.path.dirname(__file__), 'accuracy_report.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Full report saved to: {out_path}")

    # Milestone assessment
    acc = report['accuracy_pct']
    if acc >= 99:
        print(f"[M1 MET] Accuracy {acc}% >= 99%")
    elif acc >= 95:
        print(f"[CLOSE] Accuracy {acc}% — need {99-acc:.1f}% more")
    else:
        print(f"[BELOW] Accuracy {acc}% — fixes needed (see error_details in JSON report)")
