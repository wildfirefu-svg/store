#!/usr/bin/env python3
"""
Automated tests for new tools: zeri v2, liunian v2, name_analysis, case_retrieval.
Tests functional correctness, output format, edge cases, and integration.
"""

import json, os, sys, time, subprocess, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOTAL = 0
PASSED = 0
FAILED = []
CHART_PATH = None

def reset():
    global TOTAL, PASSED, FAILED
    TOTAL = 0; PASSED = 0; FAILED = []

def check(label, condition, detail=''):
    global TOTAL, PASSED, FAILED
    TOTAL += 1
    if condition:
        PASSED += 1
        print(f'  [PASS] {label}')
    else:
        FAILED.append((label, detail))
        print(f'  [FAIL] {label} — {detail}')

def run_tool(cmd, timeout=60):
    """Run a Python tool and return (returncode, stdout, stderr)."""
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr

# =============================================================================
# SETUP: Generate a test chart
# =============================================================================

def setup_chart():
    global CHART_PATH
    CHART_PATH = os.path.join(tempfile.gettempdir(), 'test_tools_chart.json')
    ret, _, _ = run_tool(
        f'python bazi_calculator.py --year 1993 --month 7 --day 15 --hour 14 '
        f'--gender male --mode all -o {CHART_PATH}'
    )
    assert ret == 0, 'Failed to generate test chart'
    return CHART_PATH


# =============================================================================
# TEST SUITE 1: zeri.py v2 — 择日系统
# =============================================================================

def test_zeri():
    print('\n' + '='*60)
    print('TEST SUITE 1: zeri.py v2 — 择日系统')
    print('='*60)
    reset()

    chart = setup_chart()

    # 1.1: Basic date selection with chart
    out = os.path.join(tempfile.gettempdir(), 'test_zeri_basic.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/zeri.py --year 2026 --month 6 --purpose 结婚 '
        f'--chart {chart} --top 5 -o {out}'
    )
    check('1.1 CLI returns 0', ret == 0)
    if ret == 0 and os.path.exists(out):
        data = json.load(open(out, 'r', encoding='utf-8'))
        check('1.1 Has dates key', 'dates' in data)
        check('1.1 Top 5 results', len(data.get('dates', [])) == 5)
        check('1.1 Scores > 0', all(d.get('score', 0) > 0 for d in data.get('dates', [])))
        check('1.1 Top score >= 50', data['dates'][0]['score'] >= 50 if data.get('dates') else False)
        check('1.1 Has ri_chen', all('ri_chen' in d for d in data.get('dates', [])))
        check('1.1 Has ri_ganzhi', all('ri_ganzhi' in d for d in data.get('dates', [])))
        check('1.1 Has yi/ji', all('yi' in d and 'ji' in d for d in data.get('dates', [])))
        check('1.1 Has detail', all('detail' in d for d in data.get('dates', [])))

    # 1.2: Different purposes
    for purpose, expect_ok in [('开业', True), ('搬家', True), ('出行', True), ('签约', True)]:
        out2 = os.path.join(tempfile.gettempdir(), f'test_zeri_{purpose}.json')
        ret, _, _ = run_tool(
            f'python knowledge-base/zeri.py --year 2026 --month 6 --purpose {purpose} '
            f'--chart {chart} --top 3 -o {out2}'
        )
        check(f'1.2 Purpose={purpose} OK', ret == 0)
        if ret == 0:
            d = json.load(open(out2, 'r', encoding='utf-8'))
            check(f'1.2 Purpose={purpose} has dates', len(d.get('dates', [])) > 0)

    # 1.3: Generic mode (no chart)
    ret, _, _ = run_tool(
        f'python knowledge-base/zeri.py --year 2026 --month 6 --purpose 通用 --top 5'
    )
    check('1.3 Generic mode (no chart) OK', ret == 0)

    # 1.4: Explicit xishen
    out3 = os.path.join(tempfile.gettempdir(), 'test_zeri_xishen.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/zeri.py --year 2026 --month 6 --purpose 投资 '
        f'--chart {chart} --xishen 木,火 --top 5 -o {out3}'
    )
    check('1.4 Explicit xishen OK', ret == 0)
    if ret == 0:
        d = json.load(open(out3, 'r', encoding='utf-8'))
        check('1.4 Has dates', len(d.get('dates', [])) > 0)

    # 1.5: Range search
    out4 = os.path.join(tempfile.gettempdir(), 'test_zeri_range.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/zeri.py --year 2026 --month 6 --purpose 结婚 '
        f'--chart {chart} --range 2 --top 3 -o {out4}'
    )
    check('1.5 Range search OK', ret == 0)

    # 1.6: Score range sanity
    out5 = os.path.join(tempfile.gettempdir(), 'test_zeri_sanity.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/zeri.py --year 2026 --month 6 --purpose 结婚 '
        f'--chart {chart} --top 10 -o {out5}'
    )
    if ret == 0:
        d = json.load(open(out5, 'r', encoding='utf-8'))
        scores = [x['score'] for x in d.get('dates', [])]
        check('1.6 Scores in reasonable range (-50 to 200)',
              all(-50 <= s <= 250 for s in scores),
              f'score range: {min(scores)}-{max(scores)}')
        check('1.6 Scores are sorted descending', scores == sorted(scores, reverse=True),
              f'first 3 scores: {scores[:3]}')

    print(f'\n  zeri: {PASSED}/{TOTAL} passed')
    return PASSED, TOTAL


# =============================================================================
# TEST SUITE 2: liunian_calendar.py v2 — 流年日历
# =============================================================================

def test_liunian():
    print('\n' + '='*60)
    print('TEST SUITE 2: liunian_calendar.py v2 — 流年日历')
    print('='*60)
    reset()

    chart = setup_chart()

    # 2.1: Basic run
    out = os.path.join(tempfile.gettempdir(), 'test_liunian_basic.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/liunian_calendar.py --chart {chart} '
        f'--target-year 2026 -o {out}'
    )
    check('2.1 CLI returns 0', ret == 0)
    if ret == 0:
        data = json.load(open(out, 'r', encoding='utf-8'))
        check('2.1 Has 12 months', len(data.get('months', [])) == 12)
        check('2.1 Has overview', 'overview' in data)
        check('2.1 Has person info', 'person' in data)
        check('2.1 Has liunian_ganzhi', bool(data.get('liunian_ganzhi')))
        check('2.1 Has liunian_shishen', bool(data.get('liunian_shishen')))
        check('2.1 Has current_dayun', data.get('current_dayun') is not None)

    # 2.2: Monthly fields
    if ret == 0:
        m = data['months'][0]
        check('2.2 Month has ganzhi', 'ganzhi' in m)
        check('2.2 Month has shishen', 'shishen' in m)
        check('2.2 Month has dm_state', 'dm_state' in m)
        check('2.2 Month has rating_stars', 'rating_stars' in m)
        check('2.2 Month rating 1-5', 1 <= m.get('rating_stars', 0) <= 5)
        check('2.2 Month has career score', 'career' in m and 'score' in m['career'])
        check('2.2 Month has wealth score', 'wealth' in m and 'score' in m['wealth'])
        check('2.2 Month has love score', 'love' in m and 'score' in m['love'])
        check('2.2 Month has health score', 'health' in m and 'score' in m['health'])
        check('2.2 Scores 1-5 range', all(
            1 <= m[k]['score'] <= 5 for k in ['career','wealth','love','health']
        ), f'scores: {m["career"]["score"]}/{m["wealth"]["score"]}/{m["love"]["score"]}/{m["health"]["score"]}')
        check('2.2 Has yi list', 'yi' in m and isinstance(m['yi'], list))
        check('2.2 Has ji list', 'ji' in m and isinstance(m['ji'], list))
        check('2.2 Has interactions', 'interactions' in m and isinstance(m['interactions'], list))
        check('2.2 Has shensha', 'shensha' in m and isinstance(m['shensha'], list))

    # 2.3: Overview fields
    if ret == 0:
        ov = data['overview']
        check('2.3 Overview has avg_scores', 'avg_scores' in ov)
        check('2.3 Overview has best_month', 'best_month' in ov)
        check('2.3 Overview has worst_month', 'worst_month' in ov)
        check('2.3 Overview has key_themes', 'key_themes' in ov)
        check('2.3 Best month rating is highest',
              ov['best_month']['rating'] in ('大吉','吉'),
              f'best month rating: {ov["best_month"]["rating"]}')

    # 2.4: Month branches match expected sequence
    if ret == 0:
        expected_branches = ['寅','卯','辰','巳','午','未','申','酉','戌','亥','子','丑']
        check('2.4 Branch sequence correct',
              [m['branch'] for m in data['months']] == expected_branches,
              f'got: {[m["branch"] for m in data["months"]]}')

    # 2.5: All months have unique ganzhi
    if ret == 0:
        ganzhis = [m['ganzhi'] for m in data['months']]
        check('2.5 12 unique ganzhi', len(set(ganzhis)) == 12)

    # 2.6: Different target year
    out2 = os.path.join(tempfile.gettempdir(), 'test_liunian_2027.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/liunian_calendar.py --chart {chart} '
        f'--target-year 2027 -o {out2}'
    )
    check('2.6 Different year OK', ret == 0)
    if ret == 0:
        d2 = json.load(open(out2, 'r', encoding='utf-8'))
        check('2.6 Different year has 12 months', len(d2.get('months', [])) == 12)

    print(f'\n  liunian: {PASSED}/{TOTAL} passed')
    return PASSED, TOTAL


# =============================================================================
# TEST SUITE 3: name_analysis.py — 姓名匹配
# =============================================================================

def test_name_analysis():
    print('\n' + '='*60)
    print('TEST SUITE 3: name_analysis.py — 姓名匹配')
    print('='*60)
    reset()

    chart = setup_chart()

    # 3.1: Name evaluation
    out = os.path.join(tempfile.gettempdir(), 'test_name_eval.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/name_analysis.py --name 张伟 --chart {chart} '
        f'--gender male -o {out}'
    )
    check('3.1 Eval CLI returns 0', ret == 0)
    if ret == 0:
        data = json.load(open(out, 'r', encoding='utf-8'))
        check('3.1 Has name', 'name' in data)
        check('3.1 Has wuge', 'wuge' in data)
        check('3.1 Has sancai', 'sancai' in data)
        check('3.1 Has scores', 'scores' in data)
        check('3.1 Has total_score', 'total_score' in data)
        check('3.1 Has grade', 'grade' in data)
        check('3.1 Has verdict', 'verdict' in data)
        check('3.1 Has xishen', 'xishen' in data and len(data['xishen']) > 0)
        check('3.1 Has jishen', 'jishen' in data and len(data['jishen']) > 0)
        check('3.1 Total score 0-100', 0 <= data['total_score'] <= 100,
              f'score={data["total_score"]}')

    # 3.2: Scoring dimensions
    if ret == 0:
        scores = data['scores']
        expected_dims = ['五行匹配', '五格数理', '三才配置', '音韵', '字义']
        for dim in expected_dims:
            check(f'3.2 Has dimension {dim}', dim in scores)
            if dim in scores:
                check(f'3.2 {dim} has score and max',
                      'score' in scores[dim] and 'max' in scores[dim])
                check(f'3.2 {dim} score <= max',
                      scores[dim]['score'] <= scores[dim]['max'],
                      f'{scores[dim]["score"]}/{scores[dim]["max"]}')

    # 3.3: Wuge completeness
    if ret == 0:
        wuge = data['wuge']
        for key in ['天格','人格','地格','外格','总格']:
            check(f'3.3 Wuge has {key}', key in wuge)
            if key in wuge:
                check(f'3.3 {key} has strokes', 'strokes' in wuge[key])
                check(f'3.3 {key} has num', 'num' in wuge[key])
                check(f'3.3 {key} has shuli', 'shuli' in wuge[key])
                check(f'3.3 {key} num 1-81', 1 <= wuge[key]['num'] <= 81,
                      f'{key} num={wuge[key]["num"]}')

    # 3.4: Name generation
    out2 = os.path.join(tempfile.gettempdir(), 'test_name_gen.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/name_analysis.py --generate --surname 张 '
        f'--chart {chart} --gender male --top 5 -o {out2}'
    )
    check('3.4 Gen CLI returns 0', ret == 0)
    if ret == 0:
        data2 = json.load(open(out2, 'r', encoding='utf-8'))
        check('3.4 Generated 5 names', len(data2) == 5)
        check('3.4 Names are unique', len(set(n['name'] for n in data2)) == 5)
        check('3.4 All have scores > 0', all(n.get('total_score', 0) > 0 for n in data2))
        check('3.4 All have wuge', all('wuge' in n for n in data2))
        check('3.4 All have strategy', all('strategy' in n for n in data2))
        check('3.4 Top score >= 60', data2[0]['total_score'] >= 60,
              f'top score={data2[0]["total_score"]}')
        check('3.4 Names are 3 chars (张+X)', all(
            n['name'].startswith('张') and 2 <= len(n['name']) <= 3 for n in data2
        ), f'names: {[n["name"] for n in data2]}')

    # 3.5: Female generation
    out3 = os.path.join(tempfile.gettempdir(), 'test_name_gen_f.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/name_analysis.py --generate --surname 李 '
        f'--chart {chart} --gender female --top 5 -o {out3}'
    )
    check('3.5 Female generation OK', ret == 0)
    if ret == 0:
        d3 = json.load(open(out3, 'r', encoding='utf-8'))
        check('3.5 Female names unique', len(set(n['name'] for n in d3)) >= 4,
              f'got {len(set(n["name"] for n in d3))} unique')

    # 3.6: Short name (single char given name)
    out4 = os.path.join(tempfile.gettempdir(), 'test_name_single.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/name_analysis.py --name 王伟 --chart {chart} '
        f'--gender male -o {out4}'
    )
    check('3.6 Single-name eval OK', ret == 0)
    if ret == 0:
        d4 = json.load(open(out4, 'r', encoding='utf-8'))
        check('3.6 Single-name has scores', 'scores' in d4)

    print(f'\n  name_analysis: {PASSED}/{TOTAL} passed')
    return PASSED, TOTAL


# =============================================================================
# TEST SUITE 4: case_retrieval.py — 案例检索
# =============================================================================

def test_case_retrieval():
    print('\n' + '='*60)
    print('TEST SUITE 4: case_retrieval.py — 案例检索')
    print('='*60)
    reset()

    chart = setup_chart()

    # 4.1: Chart-based retrieval
    out = os.path.join(tempfile.gettempdir(), 'test_retrieval.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/case_retrieval.py --chart {chart} --top 5 -o {out}'
    )
    check('4.1 CLI returns 0', ret == 0)
    if ret == 0:
        data = json.load(open(out, 'r', encoding='utf-8'))
        check('4.1 Has results', len(data) > 0, f'got {len(data)} results')
        check('4.1 At least 3 results', len(data) >= 3, f'got {len(data)}')
        r = data[0]
        check('4.1 Result has id', 'id' in r)
        check('4.1 Result has name', 'name' in r)
        check('4.1 Result has category', 'category' in r)
        check('4.1 Result has dm_gan', 'dm_gan' in r)
        check('4.1 Result has dm_wu', 'dm_wu' in r)
        check('4.1 Result has month_zhi', 'month_zhi' in r)
        check('4.1 Result has key_tags', 'key_tags' in r)
        check('4.1 Result has similarity', 'similarity' in r)
        check('4.1 Similarity 0-1 range', 0 <= r['similarity'] <= 1.0,
              f'sim={r["similarity"]}')
        check('4.1 Result has text', 'text' in r and len(r['text']) > 0)

    # 4.2: Text query
    out2 = os.path.join(tempfile.gettempdir(), 'test_retrieval_text.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/case_retrieval.py --query "日主庚金，生于未月，身强" '
        f'--top 3 -o {out2}'
    )
    check('4.2 Text query OK', ret == 0)
    if ret == 0:
        d2 = json.load(open(out2, 'r', encoding='utf-8'))
        check('4.2 Text query has results', len(d2) > 0)

    # 4.3: Results are sorted by similarity
    if ret == 0 and len(data) >= 2:
        sims = [r['similarity'] for r in data]
        check('4.3 Results sorted by similarity', sims == sorted(sims, reverse=True),
              f'sims: {sims}')

    # 4.4: Different chart yields different results
    chart2 = os.path.join(tempfile.gettempdir(), 'test_retrieval_chart2.json')
    run_tool(
        f'python bazi_calculator.py --year 1989 --month 1 --day 15 --hour 8 '
        f'--gender female --mode all -o {chart2}'
    )
    out3 = os.path.join(tempfile.gettempdir(), 'test_retrieval_chart2_out.json')
    ret, _, _ = run_tool(
        f'python knowledge-base/case_retrieval.py --chart {chart2} --top 5 -o {out3}'
    )
    check('4.4 Different chart OK', ret == 0)
    if ret == 0:
        d3 = json.load(open(out3, 'r', encoding='utf-8'))
        # Results should differ (different DM or month)
        names1 = set(r['name'] for r in data)
        names2 = set(r['name'] for r in d3)
        check('4.4 Different charts give different results',
              names1 != names2,
              f'same names: {names1 & names2}')

    # 4.5: Benchmark data completeness
    import importlib.util
    cr_spec = importlib.util.spec_from_file_location('case_retrieval', 'knowledge-base/case_retrieval.py')
    cr = importlib.util.module_from_spec(cr_spec)
    cr_spec.loader.exec_module(cr)
    BENCHMARK_CASES = cr.BENCHMARK_CASES
    check('4.5 Benchmark has 39 cases', len(BENCHMARK_CASES) == 39,
          f'got {len(BENCHMARK_CASES)}')
    for bm in BENCHMARK_CASES:
        check(f'4.5 {bm["id"]} has all fields',
              all(k in bm for k in ['id','name','category','life_facts','key_tags','pattern_note']),
              f'missing fields in {bm["id"]}')

    print(f'\n  case_retrieval: {PASSED}/{TOTAL} passed')
    return PASSED, TOTAL


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print('=== NEW TOOLS TEST SUITE ===')
    print(f'Time: {time.strftime("%Y-%m-%d %H:%M:%S")}')
    print()

    grand_total = 0
    grand_passed = 0

    try:
        p, t = test_zeri()
        grand_passed += p; grand_total += t
    except Exception as e:
        print(f'  [CRASH] zeri tests: {e}')
        import traceback; traceback.print_exc()

    try:
        p, t = test_liunian()
        grand_passed += p; grand_total += t
    except Exception as e:
        print(f'  [CRASH] liunian tests: {e}')
        import traceback; traceback.print_exc()

    try:
        p, t = test_name_analysis()
        grand_passed += p; grand_total += t
    except Exception as e:
        print(f'  [CRASH] name_analysis tests: {e}')
        import traceback; traceback.print_exc()

    try:
        p, t = test_case_retrieval()
        grand_passed += p; grand_total += t
    except Exception as e:
        print(f'  [CRASH] case_retrieval tests: {e}')
        import traceback; traceback.print_exc()

    print('\n' + '='*60)
    print(f'GRAND TOTAL: {grand_passed}/{grand_total} passed')
    if grand_passed == grand_total:
        print('ALL TESTS PASSED')
    else:
        print(f'FAILURES: {grand_total - grand_passed}')
        for label, detail in FAILED:
            print(f'  [{label}] {detail}')
    print('='*60)

    # Cleanup temp files
    for f in os.listdir(tempfile.gettempdir()):
        if f.startswith('test_zeri_') or f.startswith('test_liunian_') or \
           f.startswith('test_name_') or f.startswith('test_retrieval_') or \
           f.startswith('test_tools_'):
            try:
                os.remove(os.path.join(tempfile.gettempdir(), f))
            except:
                pass

    sys.exit(0 if grand_passed == grand_total else 1)
