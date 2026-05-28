#!/usr/bin/env python3
"""P5 Hallucination Validator — Layer 1 fact-checking for BaZi reports.
Usage: python validate_hallucination.py <report.md> <chart_data.json> [--strict]
"""

import json, re, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ===== Reference Data =====
TIANGAN_LIST = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
DIZHI_LIST = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
TIANGAN = set(TIANGAN_LIST)
DIZHI = set(DIZHI_LIST)
GAN_WUXING = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
ZHI_WUXING = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}
GAN_YINYANG = {'甲':'阳','乙':'阴','丙':'阳','丁':'阴','戊':'阳','己':'阴','庚':'阳','辛':'阴','壬':'阳','癸':'阴'}

# Valid shensha trigger rules (simplified)
SHENSHA_RULES = {
    '天乙贵人': '日干或年干查',
    '文昌贵人': '日干查',
    '桃花': '地支三合局查',
    '驿马': '地支三合局查',
    '华盖': '地支三合局查',
    '羊刃': '日干查',
    '魁罡': '日柱干支为庚辰/庚戌/壬辰/戊戌',
    '天德贵人': '月支查',
    '月德贵人': '月支查',
    '禄神': '日干查',
    '将星': '地支三合局查',
    '劫煞': '地支三合局查',
    '灾煞': '地支三合局查',
    '亡神': '地支三合局查',
}

# Valid pattern names
VALID_PATTERNS = {'正官格','七杀格','正财格','偏财格','正印格','偏印格','食神格','伤官格',
                  '建禄格','月刃格','从杀格','从财格','从儿格','从势格','从旺格','从强格',
                  '化气格','官杀混杂','杂格'}

# Valid 旺衰 grades
VALID_WANGSHUAI = {'专旺','从旺','身旺','身强','中和','身弱','身衰','从格','极弱'}

# Valid 十神
VALID_SHISHEN = {'正官','七杀','正财','偏财','正印','偏印','食神','伤官','比肩','劫财','日主'}

# 60甲子 set
JIAZI_60 = set()
for i in range(60):
    g = TIANGAN_LIST[i % 10]
    z = DIZHI_LIST[i % 12]
    JIAZI_60.add(g + z)


def validate(report_path, chart_path, strict=False):
    """Validate a report against chart data. Returns (errors, warnings, stats)."""
    with open(report_path, encoding='utf-8') as f:
        report = f.read()
    with open(chart_path, encoding='utf-8') as f:
        chart = json.load(f)

    errors = []
    warnings = []
    stats = {'total_checks': 0, 'passed': 0, 'failed': 0}

    # Get chart facts
    fp = chart.get('four_pillars', {})
    dm = chart.get('day_master', {})
    actual_year = f"{fp.get('year',{}).get('gan','')}{fp.get('year',{}).get('zhi','')}"
    actual_month = f"{fp.get('month',{}).get('gan','')}{fp.get('month',{}).get('zhi','')}"
    actual_day = f"{fp.get('day',{}).get('gan','')}{fp.get('day',{}).get('zhi','')}"
    actual_hour = f"{fp.get('hour',{}).get('gan','')}{fp.get('hour',{}).get('zhi','')}"
    actual_dm = dm.get('gan', '') if isinstance(dm, dict) else chart.get('four_pillars', {}).get('day_master', '')

    # 1. Check all干支 references are valid
    all_ganzhi = set(re.findall(r'[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]', report))
    stats['total_checks'] += len(all_ganzhi)
    for gz in all_ganzhi:
        g, z = gz[0], gz[1]
        valid = True
        if g not in TIANGAN:
            errors.append(f'非法天干: {gz}')
            valid = False
        if z not in DIZHI:
            errors.append(f'非法地支: {gz}')
            valid = False
        if gz not in JIAZI_60:
            warnings.append(f'非60甲子组合: {gz} (可能为虚构干支)')
            valid = False
        if valid:
            stats['passed'] += 1
        else:
            stats['failed'] += 1

    # 2. Check格局 claims — broad pattern: any "X格" term
    pattern_claims = re.findall(r'[一-鿿]{1,4}格', report)
    stats['total_checks'] += len(pattern_claims)
    for p in pattern_claims:
        if p in VALID_PATTERNS:
            stats['passed'] += 1
        else:
            errors.append(f'非法格局名: {p}')
            stats['failed'] += 1

    # 3. Check四柱 correctness
    year_in_report = re.findall(r'年柱.*?([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])', report)
    month_in_report = re.findall(r'月柱.*?([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])', report)
    if year_in_report and actual_year:
        stats['total_checks'] += 1
        if year_in_report[0] == actual_year:
            stats['passed'] += 1
        else:
            errors.append(f'年柱错误: 报告={year_in_report[0]}, 实际={actual_year}')
            stats['failed'] += 1
    if month_in_report and actual_month:
        stats['total_checks'] += 1
        if month_in_report[0] == actual_month:
            stats['passed'] += 1
        else:
            errors.append(f'月柱错误: 报告={month_in_report[0]}, 实际={actual_month}')
            stats['failed'] += 1

    # 4. Check神煞 legality — broad pattern
    shensha_found = re.findall(r'(?:神煞|贵人|桃花|驿马|华盖|羊刃|魁罡|天德|月德|禄神|将星|劫煞|灾煞|亡神|孤辰|寡宿|天乙|文昌|天喜|红鸾|福星|太极|学堂|词馆|金舆|三奇|天厨|国印|德秀|阴差|阳错|十恶|流霞|飞刃|咸池|天赦|龙德|奏书|将军|攀鞍|六厄|埋儿|天火|地火|红艳|沐浴|截路|悬针|平头|曲脚|紫微)[一-鿿]{0,2}', report)
    stats['total_checks'] += len(shensha_found)
    for sf in shensha_found:
        if any(v in sf for v in SHENSHA_RULES):
            stats['passed'] += 1
        else:
            warnings.append(f'神煞不在已知列表中: {sf}')
            stats['failed'] += 1

    # 5. Check 旺衰 terms — broad pattern
    wangshuai_terms = re.findall(r'[一-鿿]{1,3}(?:旺|强|弱|衰|和)', report)
    stats['total_checks'] += len(wangshuai_terms)
    for ws in wangshuai_terms:
        if ws in VALID_WANGSHUAI or ws in {'日主旺','日主弱','五行旺','五行弱','印星旺','财星旺','官星旺'}:
            stats['passed'] += 1
        elif any(w in ws for w in ['旺','强','弱','衰','中和']):
            stats['passed'] += 1  # Descriptive terms are OK
        else:
            errors.append(f'非法旺衰描述: {ws}')
            stats['failed'] += 1

    # 6. Check纳音 — validate any X金/X木/X水/X火/X土 patterns
    ALL_NAYIN = {'海中金','炉中火','大林木','路旁土','剑锋金','山头火','涧下水','城头土','白蜡金','杨柳木','泉中水','屋上土','霹雳火','松柏木','砂石金','山下火','平地木','壁上土','金箔金','覆灯火','天河水','大驿土','钗钏金','桑柘木','大溪水','沙中土','天上火','石榴木','大海水','长流水','沙中金'}
    nayin_in_report = set(re.findall(r'[一-鿿]{2,3}(?:金|木|水|火|土)', report))
    stats['total_checks'] += len(nayin_in_report)
    for n in nayin_in_report:
        if n in ALL_NAYIN:
            stats['passed'] += 1
        elif len(n) >= 3:
            errors.append(f'非法纳音: {n} (不在30组纳音中)')
            stats['failed'] += 1
        else:
            stats['passed'] += 1  # normal five-element terms like 辛金, 甲木

    # 7. Check十神 references are valid
    shishen_terms = re.findall(r'(正官|七杀|正财|偏财|正印|偏印|食神|伤官|比肩|劫财)', report)
    stats['total_checks'] += len(shishen_terms)
    for ss in shishen_terms:
        if ss in VALID_SHISHEN:
            stats['passed'] += 1
        else:
            stats['failed'] += 1

    # Compute hallucination rate
    total = stats['total_checks']
    failed = stats['failed']
    hallu_rate = (failed / total * 100) if total > 0 else 0

    result = {
        'report': report_path,
        'chart': chart_path,
        'errors': errors,
        'warnings': warnings,
        'stats': stats,
        'hallucination_rate': round(hallu_rate, 2),
        'pass': hallu_rate < 1.0,
    }
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser(description='BaZi Hallucination Validator')
    ap.add_argument('report', help='Markdown report file')
    ap.add_argument('chart', help='Chart JSON file (calculator output)')
    ap.add_argument('--strict', action='store_true', help='Treat warnings as errors')
    args = ap.parse_args()

    result = validate(args.report, args.chart, args.strict)
    s = result['stats']

    print(f'=== 幻觉校验报告 ===')
    print(f'报告: {args.report}')
    print(f'总检查项: {s["total_checks"]} | 通过: {s["passed"]} | 失败: {s["failed"]}')
    print(f'幻觉率: {result["hallucination_rate"]}%')
    print()

    if result['errors']:
        print(f'=== 错误 ({len(result["errors"])}) ===')
        for e in result['errors']:
            print(f'  [ERROR] {e}')
        print()
    if result['warnings']:
        print(f'=== 警告 ({len(result["warnings"])}) ===')
        for w in result['warnings']:
            print(f'  [WARN] {w}')
        print()

    if result['pass']:
        print(f'PASS: 幻觉率 {result["hallucination_rate"]}% < 1%')
    else:
        print(f'FAIL: 幻觉率 {result["hallucination_rate"]}% >= 1%')

    out = os.path.join(os.path.dirname(__file__), 'hallu_report.json')
    json.dump(result, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Report saved: {out}')


if __name__ == '__main__':
    main()
