#!/usr/bin/env python3
"""
合婚分析 — 双人八字配对评测 CLI 工具。
四法合参：纳音合婚 + 日柱合婚 + 十神合婚 + 用神互补

Usage:
    python knowledge-base/hehun.py --chart1 m.json --chart2 f.json -o report.json
    python knowledge-base/hehun.py --year1 1993 ... --year2 1995 ... -o report.json
"""

import os, sys, json, argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bazi_calculator import (
    calculate_four_pillars, calculate_dayun,
    TIANGAN, DIZHI, GAN_WUXING, ZHI_WUXING, GAN_YINYANG,
    NAYIN, LIUCHONG, LIUHE, LIUHAI, SANXING, SANHE,
    get_shishen,
)

def load_chart(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    fp = data.get('four_pillars', {})
    dm = data.get('day_master', {})
    birth = data.get('birth_info', {})
    dayun = data.get('da_yun', [])
    return fp, dm, birth, dayun

# ============================================================
# 1. 纳音合婚
# ============================================================

def score_nayin(chart1, chart2):
    year_ganzhi1 = chart1['year']['gan'] + chart1['year']['zhi']
    year_ganzhi2 = chart2['year']['gan'] + chart2['year']['zhi']
    nayin1 = NAYIN.get(year_ganzhi1, '')
    nayin2 = NAYIN.get(year_ganzhi2, '')
    wu1 = ZHI_WUXING.get(chart1['year']['zhi'], '')
    wu2 = ZHI_WUXING.get(chart2['year']['zhi'], '')

    # Five-element relationship
    sheng_map = {('木','火'),('火','土'),('土','金'),('金','水'),('水','木')}
    ke_map = {('木','土'),('土','水'),('水','火'),('火','金'),('金','木')}

    score = 50
    detail = []
    if wu1 == wu2:
        score = 70
        detail.append(f'{wu1}同类→70分')
    elif (wu1, wu2) in sheng_map:
        score = 85
        detail.append(f'{wu1}生{wu2}→85分')
    elif (wu2, wu1) in sheng_map:
        score = 80
        detail.append(f'{wu2}生{wu1}→80分')
    elif (wu1, wu2) in ke_map:
        score = 35
        detail.append(f'{wu1}克{wu2}→35分')
    elif (wu2, wu1) in ke_map:
        score = 40
        detail.append(f'{wu2}克{wu1}→40分')

    return {'score': score, 'nayin1': nayin1, 'nayin2': nayin2,
            'wuxing1': wu1, 'wuxing2': wu2, 'detail': '；'.join(detail)}


# ============================================================
# 2. 日柱合婚
# ============================================================

def score_rizhu(chart1, chart2):
    day_zhi1 = chart1['day']['zhi']
    day_zhi2 = chart2['day']['zhi']
    score = 50
    detail = []

    # 六合
    for a, b in LIUHE:
        if (day_zhi1 == a and day_zhi2 == b) or (day_zhi1 == b and day_zhi2 == a):
            score = 95
            detail.append('日支六合→95分(极佳)')
            return {'score': score, 'detail': '；'.join(detail),
                    'zhi1': day_zhi1, 'zhi2': day_zhi2}

    # 六冲
    for a, b in LIUCHONG:
        if (day_zhi1 == a and day_zhi2 == b) or (day_zhi1 == b and day_zhi2 == a):
            score = 20
            detail.append('日支六冲→20分(严重)')
            return {'score': score, 'detail': '；'.join(detail),
                    'zhi1': day_zhi1, 'zhi2': day_zhi2}

    # 六害
    for a, b in LIUHAI:
        if (day_zhi1 == a and day_zhi2 == b) or (day_zhi1 == b and day_zhi2 == a):
            score = 30
            detail.append('日支六害→30分(不利)')
            return {'score': score, 'detail': '；'.join(detail),
                    'zhi1': day_zhi1, 'zhi2': day_zhi2}

    # 三合
    for group in SANHE:
        if day_zhi1 in group and day_zhi2 in group:
            score = 85
            detail.append('日支三合→85分(佳)')
            return {'score': score, 'detail': '；'.join(detail),
                    'zhi1': day_zhi1, 'zhi2': day_zhi2}

    # 三刑
    for group in SANXING:
        if day_zhi1 in group and day_zhi2 in group:
            score = 25
            detail.append('日支相刑→25分(不利)')

    detail.append('日支无特殊关系→50分')
    return {'score': score, 'detail': '；'.join(detail),
            'zhi1': day_zhi1, 'zhi2': day_zhi2}


# ============================================================
# 3. 十神合婚
# ============================================================

def score_shishen(chart1, chart2, gender1='male', gender2='female'):
    day_gan1 = chart1['day']['gan']
    day_gan2 = chart2['day']['gan']
    dm1 = chart1['day_master'] if isinstance(chart1.get('day_master'), str) else chart1['day_master'].get('gan', day_gan1)
    dm2 = chart2['day_master'] if isinstance(chart2.get('day_master'), str) else chart2['day_master'].get('gan', day_gan2)

    # If male, his 财星 (what he controls) vs female's 官星 (what controls her)
    ss1_on_2 = get_shishen(dm1, dm2)
    ss2_on_1 = get_shishen(dm2, dm1)

    score = 50
    detail = []

    # Good combos
    good_for_male = {'正财','偏财'}  # He sees her as wealth = positive
    good_for_female = {'正官','七杀'}  # She sees him as authority = positive
    neutral = {'正印','偏印','食神','比肩'}
    bad = {'劫财','伤官'}

    if ss1_on_2 in good_for_male:
        score += 15
        detail.append(f'男见女为{ss1_on_2}→+15')
    if ss2_on_1 in good_for_female:
        score += 15
        detail.append(f'女见男为{ss2_on_1}→+15')
    if ss1_on_2 in neutral:
        detail.append(f'男见女为{ss1_on_2}→中性')
    if ss2_on_1 in neutral:
        detail.append(f'女见男为{ss2_on_1}→中性')
    if ss1_on_2 in bad:
        score -= 15
        detail.append(f'男见女为{ss1_on_2}→-15')
    if ss2_on_1 in bad:
        score -= 15
        detail.append(f'女见男为{ss2_on_1}→-15')

    # Same element = shared values
    wu1 = GAN_WUXING.get(dm1, '')
    wu2 = GAN_WUXING.get(dm2, '')
    if wu1 == wu2:
        score += 10
        detail.append(f'日主同{wu1}→+10')

    score = max(10, min(100, score))
    return {'score': score, 'ss1_on_2': ss1_on_2, 'ss2_on_1': ss2_on_1,
            'wu1': wu1, 'wu2': wu2, 'detail': '；'.join(detail)}


# ============================================================
# 4. 用神互补
# ============================================================

def score_xishen(chart1, chart2, fp1, fp2):
    # Simplified xishen inference
    def _infer_wu_balance(fp):
        counts = {'金':0,'木':0,'水':0,'火':0,'土':0}
        for pk in ['year','month','day','hour']:
            p = fp.get(pk, {})
            g = p.get('gan',''); z = p.get('zhi','')
            if g in GAN_WUXING: counts[GAN_WUXING[g]] += 1
            if z in ZHI_WUXING: counts[ZHI_WUXING[z]] += 1
        weakest = min(counts, key=counts.get)
        strongest = max(counts, key=counts.get)
        month_zhi = fp.get('month',{}).get('zhi','')
        month_wu = ZHI_WUXING.get(month_zhi, '')
        day_wu = GAN_WUXING.get(fp.get('day',{}).get('gan',''), '')
        # If month supports day master, xishen = weakest; if not, xishen = element that generates day
        sheng = {('木','火'),('火','土'),('土','金'),('金','水'),('水','木')}
        if month_wu == day_wu or (month_wu, day_wu) in sheng:
            favorable = [weakest]
        else:
            generated_by = {'木':'水','火':'木','土':'火','金':'土','水':'金'}
            favorable = [generated_by.get(day_wu, weakest)]
        # Add the weakest as secondary
        if weakest not in favorable:
            favorable.append(weakest)
        return favorable[:2], [strongest]

    fav1, unfav1 = _infer_wu_balance(fp1)
    fav2, unfav2 = _infer_wu_balance(fp2)

    score = 50
    detail = []

    # Does person 2 supply what person 1 needs?
    supply1 = sum(1 for f in fav1 if f in (GAN_WUXING.get(fp2.get('day',{}).get('gan',''),''),))
    supply2 = sum(1 for f in fav2 if f in (GAN_WUXING.get(fp1.get('day',{}).get('gan',''),''),))

    if supply1 > 0:
        score += 10
        detail.append(f'乙方供给甲方喜用神→+10')
    if supply2 > 0:
        score += 10
        detail.append(f'甲方供给乙方喜用神→+10')

    # Does person 2 bring what person 1 dislikes?
    bring_bad = sum(1 for u in unfav1 if u in (GAN_WUXING.get(fp2.get('day',{}).get('gan',''),''),))
    if bring_bad > 0:
        score -= 15
        detail.append(f'乙方带来甲方忌神→-15')

    score = max(10, min(100, score))
    return {'score': score, 'fav1': fav1, 'fav2': fav2, 'unfav1': unfav1, 'unfav2': unfav2,
            'detail': '；'.join(detail)}


# ============================================================
# 5. 综合合婚引擎
# ============================================================

def hehun_analysis(chart1_path, chart2_path, gender1='male', gender2='female'):
    fp1, dm1, birth1, dayun1 = load_chart(chart1_path)
    fp2, dm2, birth2, dayun2 = load_chart(chart2_path)

    # Ensure day_master is string
    if isinstance(dm1, dict): dm1 = dm1.get('gan', fp1['day']['gan'])
    if isinstance(dm2, dict): dm2 = dm2.get('gan', fp2['day']['gan'])

    # Build chart dicts with day_master as string for score functions
    c1 = {'year': fp1['year'], 'month': fp1['month'], 'day': fp1['day'], 'hour': fp1['hour'], 'day_master': dm1}
    c2 = {'year': fp2['year'], 'month': fp2['month'], 'day': fp2['day'], 'hour': fp2['hour'], 'day_master': dm2}

    nayin = score_nayin(c1, c2)
    rizhu = score_rizhu(c1, c2)
    shishen = score_shishen(c1, c2, gender1, gender2)
    xishen = score_xishen(c1, c2, fp1, fp2)

    total = int(nayin['score'] * 0.20 + rizhu['score'] * 0.35 +
                shishen['score'] * 0.25 + xishen['score'] * 0.20)

    if total >= 85:
        grade = 'S — 天作之合'
    elif total >= 75:
        grade = 'A — 佳配'
    elif total >= 60:
        grade = 'B — 可成'
    elif total >= 45:
        grade = 'C — 勉强'
    else:
        grade = 'D — 不宜'

    return {
        'person1': {'name': birth1.get('name','甲方'), 'day_master': dm1,
                    'year': birth1.get('year',''), 'month': birth1.get('month',''),
                    'gender': gender1},
        'person2': {'name': birth2.get('name','乙方'), 'day_master': dm2,
                    'year': birth2.get('year',''), 'month': birth2.get('month',''),
                    'gender': gender2},
        'scores': {
            '纳音合婚(20%)': {'score': nayin['score'], 'detail': nayin['detail']},
            '日柱合婚(35%)': {'score': rizhu['score'], 'detail': rizhu['detail']},
            '十神合婚(25%)': {'score': shishen['score'], 'detail': shishen['detail']},
            '用神互补(20%)': {'score': xishen['score'], 'detail': xishen['detail']},
        },
        'total': total,
        'grade': grade,
        'nayin_info': {'nayin1': nayin['nayin1'], 'nayin2': nayin['nayin2']},
        'rizhu_info': {'zhi1': rizhu['zhi1'], 'zhi2': rizhu['zhi2'],
                       'relation': rizhu['detail'].split('→')[0] if '→' in rizhu['detail'] else '无'},
    }


# ============================================================
# CLI
# ============================================================

def main():
    ap = argparse.ArgumentParser(description='合婚分析 — 双人八字配对评测')
    ap.add_argument('--chart1', '-c1', help='甲方 chart JSON')
    ap.add_argument('--chart2', '-c2', help='乙方 chart JSON')
    ap.add_argument('--year1', type=int, help='甲方出生年')
    ap.add_argument('--month1', type=int, help='甲方出生月')
    ap.add_argument('--day1', type=int, help='甲方出生日')
    ap.add_argument('--hour1', type=int, default=8)
    ap.add_argument('--gender1', default='male', help='甲方性别')
    ap.add_argument('--year2', type=int, help='乙方出生年')
    ap.add_argument('--month2', type=int, help='乙方出生月')
    ap.add_argument('--day2', type=int, help='乙方出生日')
    ap.add_argument('--hour2', type=int, default=8)
    ap.add_argument('--gender2', default='female', help='乙方性别')
    ap.add_argument('--output', '-o', help='Output JSON')
    args = ap.parse_args()

    # Generate charts if birth params provided
    import tempfile
    chart1_path = args.chart1
    chart2_path = args.chart2

    if not chart1_path and args.year1:
        chart1_path = os.path.join(tempfile.gettempdir(), 'hehun_chart1.json')
        ret = os.system(f'python bazi_calculator.py --year {args.year1} --month {args.month1} '
                        f'--day {args.day1} --hour {args.hour1} --gender {args.gender1} '
                        f'--mode all -o {chart1_path}')
        if ret != 0:
            print('Error generating chart1')
            return

    if not chart2_path and args.year2:
        chart2_path = os.path.join(tempfile.gettempdir(), 'hehun_chart2.json')
        ret = os.system(f'python bazi_calculator.py --year {args.year2} --month {args.month2} '
                        f'--day {args.day2} --hour {args.hour2} --gender {args.gender2} '
                        f'--mode all -o {chart2_path}')
        if ret != 0:
            print('Error generating chart2')
            return

    if not chart1_path or not chart2_path:
        ap.error('Provide --chart1/--chart2 or --year1/--year2 birth params')

    result = hehun_analysis(chart1_path, chart2_path, args.gender1, args.gender2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'Saved: {args.output}')
    else:
        print(f'══════ 合婚分析 ══════')
        print(f'甲方: {result["person1"]["day_master"]}日主 '
              f'({result["person1"]["year"]}-{result["person1"]["month"]})')
        print(f'乙方: {result["person2"]["day_master"]}日主 '
              f'({result["person2"]["year"]}-{result["person2"]["month"]})')
        print()
        for dim, s in result['scores'].items():
            bar = '#' * (s['score'] // 5) + '.' * (20 - s['score'] // 5)
            print(f'  {dim:20s} {s["score"]:>3} {bar}')
            print(f'    {s["detail"]}')
        print(f'  {"综合":20s} {result["total"]:>3}')
        print(f'  评级: {result["grade"]}')

    # Cleanup temp files
    if not args.chart1 and chart1_path:
        try: os.remove(chart1_path)
        except: pass
    if not args.chart2 and chart2_path:
        try: os.remove(chart2_path)
        except: pass


if __name__ == '__main__':
    main()
