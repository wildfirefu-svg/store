#!/usr/bin/env python3
"""
姓名×八字匹配系统 — 取名引擎 + 已有名字评测

五格剖象 · 三才配置 · 五行补益 · 生肖喜忌 · 音韵字义

Usage:
    # 已有名字评测
    python knowledge-base/name_analysis.py --name 张伟 --chart chart.json

    # 取名推荐
    python knowledge-base/name_analysis.py --chart chart.json --generate --gender male --top 10
    python knowledge-base/name_analysis.py --chart chart.json --generate --surname 张 --gender female --top 10
"""

import os, sys, json, argparse, random
from itertools import product
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from name_wuxing_data import (
    KANGXI_STROKES, _SIMPLIFIED_TO_KANGXI_MAP as SIMP_KX,
    SURNAME_STROKES, EIGHTY_ONE_NUMBERS, SANCAI_CONFIGS, WUXING_CHARS,
    CHAR_WUXING, ZODIAC_NAME_RULES, WUGE_CATEGORY_NAMES,
    analyze_phonetics, POSITIVE_NAME_CHARS, NEGATIVE_CONNOTATION_CHARS,
    BAD_HOMOPHONES, get_tone,
)
from bazi_calculator import (
    GAN_WUXING, ZHI_WUXING, DIZHI, sexagenary_by_index,
)
from zeri import infer_xishen_from_chart


# =============================================================================
# 1. 康熙笔画查询
# =============================================================================

def get_kangxi_stroke(c):
    """Get Kangxi stroke count for a character. Falls back to estimation."""
    if c in KANGXI_STROKES:
        return KANGXI_STROKES[c]
    if c in SIMP_KX:
        return SIMP_KX[c]
    # Fallback: try to estimate
    # Most simplified chars have fewer strokes than traditional
    return max(1, len(c.encode('utf-8')) // 3 * 3)


def get_char_wuxing(c):
    """Get 五行 element of a character."""
    return CHAR_WUXING.get(c, None)


# =============================================================================
# 2. 五格剖象计算
# =============================================================================

def calc_wuge(surname, given_name):
    """
    Calculate 五格 (Five Grids) for a name.
    天格, 人格, 地格, 外格, 总格

    Returns dict with stroke counts and 81数理 judgments.
    """
    # Get Kangxi strokes
    s_strokes = [get_kangxi_stroke(c) for c in surname]
    g_strokes = [get_kangxi_stroke(c) for c in given_name]

    # 天格: surname + 1 (single surname; compound surnames handled separately)
    tian_ge = sum(s_strokes) + (1 if len(surname) == 1 else 0)

    # 人格: last char of surname + first char of given name
    ren_ge = s_strokes[-1] + g_strokes[0]

    # 地格: given name strokes (single name + 1, double name = sum)
    if len(given_name) == 1:
        di_ge = g_strokes[0] + 1
    else:
        di_ge = sum(g_strokes)

    # 总格: all strokes
    zong_ge = sum(s_strokes) + sum(g_strokes)

    # 外格: variant formula — (total - ren) + 1
    wai_ge = zong_ge - ren_ge + 1

    # Cap to 1-81 range for 81数理 lookup (cyclic pattern)
    def _num81(n):
        return ((n - 1) % 81) + 1

    wuge = {
        '天格': {'strokes': tian_ge, 'num': _num81(tian_ge)},
        '人格': {'strokes': ren_ge, 'num': _num81(ren_ge)},
        '地格': {'strokes': di_ge, 'num': _num81(di_ge)},
        '外格': {'strokes': wai_ge, 'num': _num81(wai_ge)},
        '总格': {'strokes': zong_ge, 'num': _num81(zong_ge)},
    }

    # Attach 81数理 judgments
    for key in wuge:
        n = wuge[key]['num']
        j = EIGHTY_ONE_NUMBERS.get(n, {'category': 3, 'short': '未知'})
        wuge[key]['shuli'] = WUGE_CATEGORY_NAMES.get(j['category'], '平')
        wuge[key]['shuli_cat'] = j['category']
        wuge[key]['shuli_meaning'] = j['meaning']
        wuge[key]['shuli_short'] = j['short']

    return wuge


def get_sancai(wuge):
    """
    Determine 三才配置 from 五格.
    Element mapping: last digit 1,2→木; 3,4→火; 5,6→土; 7,8→金; 9,0→水
    """
    def _elem(strokes):
        d = strokes % 10
        if d in (1, 2):
            return '木'
        elif d in (3, 4):
            return '火'
        elif d in (5, 6):
            return '土'
        elif d in (7, 8):
            return '金'
        else:
            return '水'

    tian = _elem(wuge['天格']['strokes'])
    ren = _elem(wuge['人格']['strokes'])
    di = _elem(wuge['地格']['strokes'])

    key = f'{tian}_{ren}_{di}'
    config = SANCAI_CONFIGS.get(key, {'category': 3, 'detail': '标准配置'})
    return {
        '天格元素': tian,
        '人格元素': ren,
        '地格元素': di,
        'config': f'{tian}{ren}{di}',
        'judgment': config['detail'],
        'category': config['category'],
        'category_name': WUGE_CATEGORY_NAMES.get(config['category'], '平'),
    }


# =============================================================================
# 3. 五行匹配评分 (Name五行 vs BaZi喜用神)
# =============================================================================

def score_wuxing_match(name_chars, xishen, jishen):
    """
    Score how well the name's 五行 matches BaZi 喜用神.
    Returns (score_out_of_40, detail).
    """
    score = 20  # baseline
    details = []
    char_wuxing_list = []

    for c in name_chars:
        wu = get_char_wuxing(c)
        if wu:
            char_wuxing_list.append(f'{c}={wu}')
            if wu in xishen:
                score += 10
                details.append(f'{c}({wu})补喜用神→+10')
            elif wu in jishen:
                score -= 12
                details.append(f'{c}({wu})为忌神→-12')
            else:
                details.append(f'{c}({wu})中性→0')
        else:
            char_wuxing_list.append(f'{c}=未知')
            details.append(f'{c}五行未知→中性')

    return (min(40, max(0, score)), '；'.join(details), char_wuxing_list)


# =============================================================================
# 4. 五格数理评分
# =============================================================================

def score_wuge(wuge):
    """Score the 五格 based on 81数理. Returns (score_out_of_25, details)."""
    score = 15  # baseline
    details = []

    for key in ['天格', '人格', '地格', '外格', '总格']:
        w = wuge[key]
        cat = w['shuli_cat']
        if cat == 1:  # 大吉
            score += 2
            details.append(f'{key}{w["strokes"]}画={w["shuli"]}→+2')
        elif cat == 2:  # 吉
            score += 1
            details.append(f'{key}{w["strokes"]}画={w["shuli"]}→+1')
        elif cat == 3:  # 平
            details.append(f'{key}{w["strokes"]}画={w["shuli"]}→0')
        elif cat == 4:  # 凶
            # 人格凶扣最多
            if key == '人格':
                score -= 5
                details.append(f'{key}{w["strokes"]}画={w["shuli"]}(凶)→-5')
            elif key == '总格':
                score -= 3
                details.append(f'{key}{w["strokes"]}画={w["shuli"]}(凶)→-3')
            else:
                score -= 2
                details.append(f'{key}{w["strokes"]}画={w["shuli"]}(凶)→-2')
        else:  # 大凶
            if key == '人格':
                score -= 7
                details.append(f'{key}{w["strokes"]}画={w["shuli"]}(大凶)→-7')
            else:
                score -= 4
                details.append(f'{key}{w["strokes"]}画={w["shuli"]}(大凶)→-4')

    return (min(25, max(0, score)), '；'.join(details))


# =============================================================================
# 5. 三才配置评分
# =============================================================================

def score_sancai(sancai):
    """Score the 三才 configuration. Returns (score_out_of_15, details)."""
    cat = sancai.get('category', 3)
    config = sancai.get('config', '???')
    judgment = sancai.get('judgment', '')

    if cat == 1:
        return (15, f'三才{config}大吉：{judgment}')
    elif cat == 2:
        return (12, f'三才{config}吉：{judgment}')
    elif cat == 3:
        return (8, f'三才{config}平：{judgment}')
    else:
        return (3, f'三才{config}凶：{judgment}')


# =============================================================================
# 6. 音韵评分
# =============================================================================

def score_phonetics_wrapper(name_chars):
    """Wrapper around phonetics analysis, returns (score_out_of_10, notes)."""
    s, notes = analyze_phonetics(name_chars)
    return (s, notes)


# =============================================================================
# 7. 字义/生肖评分
# =============================================================================

def score_meaning(name_chars, zodiac=None):
    """
    Score based on character meaning, zodiac compatibility.
    Returns (score_out_of_10, notes).
    """
    score = 5  # baseline
    notes = []

    # Check for negative connotation
    has_negative = False
    for c in name_chars:
        if c in NEGATIVE_CONNOTATION_CHARS:
            has_negative = True
            score -= 5
            notes.append(f'{c}为负面字→-5')

    # Check for positive connotation
    for c in name_chars:
        if c in POSITIVE_NAME_CHARS:
            bonus = min(3, POSITIVE_NAME_CHARS[c] // 3)
            score += bonus
            notes.append(f'{c}字义吉→+{bonus}')
            break  # Only count once

    # Check homophones
    full_name = ''.join(name_chars)
    for bad_name, homophone in BAD_HOMOPHONES.items():
        if full_name == bad_name:
            score -= 5
            notes.append(f'谐音似"{homophone}"→-5')

    # Zodiac compatibility
    if zodiac:
        for c in name_chars:
            if c in ZODIAC_NAME_RULES.get(zodiac, {}).get('忌', []):
                # Check if the character's radical is in the忌 list
                pass  # Simplified — just check common zodiac忌

    return (min(10, max(0, score)), '；'.join(notes) if notes else '字义正常')


# =============================================================================
# 8. 综合评测 (已有名字)
# =============================================================================

def evaluate_name(surname, given_name, chart_data, gender='male'):
    """
    Full evaluation of an existing name against a BaZi chart.
    Returns comprehensive scoring dict.
    """
    full_name = surname + given_name
    all_chars = list(surname) + list(given_name)

    # Infer 喜用神
    fav, unfav = infer_xishen_from_chart(chart_data)

    # Determine zodiac from year pillar
    year_zhi = chart_data.get('four_pillars', {}).get('year', {}).get('zhi', '')
    zodiac_map = {'子':'鼠','丑':'牛','寅':'虎','卯':'兔','辰':'龙','巳':'蛇',
                  '午':'马','未':'羊','申':'猴','酉':'鸡','戌':'狗','亥':'猪'}
    zodiac = zodiac_map.get(year_zhi, '')

    # 1. 五格剖象
    wuge = calc_wuge(surname, given_name)

    # 2. 三才配置
    sancai = get_sancai(wuge)

    # 3. 五行匹配 (only score given name chars for element match)
    name_wu_score, wu_detail, wu_list = score_wuxing_match(
        list(given_name), fav, unfav
    )

    # 4. 五格数理
    shuli_score, shuli_detail = score_wuge(wuge)

    # 5. 三才
    sancai_score, sancai_detail = score_sancai(sancai)

    # 6. 音韵
    yinyun_score, yinyun_detail = score_phonetics_wrapper(list(given_name))

    # 7. 字义
    ziyi_score, ziyi_detail = score_meaning(list(given_name), zodiac)

    total = (name_wu_score + shuli_score + sancai_score +
             yinyun_score + ziyi_score)

    # Rating
    if total >= 90:
        grade = 'S — 绝佳'
        verdict = '此名与八字高度匹配，五格大吉，五行得补，建议使用'
    elif total >= 80:
        grade = 'A — 优良'
        verdict = '此名较好匹配八字，小有不足但整体良好'
    elif total >= 65:
        grade = 'B — 尚可'
        verdict = '此名可接受，但存在一定缺憾，可考虑优化'
    elif total >= 50:
        grade = 'C — 欠佳'
        verdict = '此名与八字匹配度低，存在明显缺陷，建议改名'
    else:
        grade = 'D — 不佳'
        verdict = '此名严重不匹配八字，五格或五行有重大缺陷，强烈建议改名'

    return {
        'name': full_name,
        'surname': surname,
        'given_name': given_name,
        'gender': gender,
        'zodiac': zodiac,
        'xishen': fav,
        'jishen': unfav,
        'wuge': wuge,
        'sancai': sancai,
        'scores': {
            '五行匹配': {'score': name_wu_score, 'max': 40, 'detail': wu_detail, 'wu_list': wu_list},
            '五格数理': {'score': shuli_score, 'max': 25, 'detail': shuli_detail},
            '三才配置': {'score': sancai_score, 'max': 15, 'detail': sancai_detail},
            '音韵': {'score': yinyun_score, 'max': 10, 'detail': yinyun_detail},
            '字义': {'score': ziyi_score, 'max': 10, 'detail': ziyi_detail},
        },
        'total_score': total,
        'max_score': 100,
        'grade': grade,
        'verdict': verdict,
    }


# =============================================================================
# 9. 取名推荐引擎
# =============================================================================

# Good two-character name combinations organized by 五行
_NAME_CHARS_BY_WUXING = {
    '金': ['铭','锐','钧','钰','锦','瑞','瑜','瑾','琛','鑫','铮','键','镜','镇','钟'],
    '木': ['林','森','柏','桐','楠','楷','榕','杰','嘉','建','家','奇','国','君','艺'],
    '水': ['泽','鸿','浩','涵','源','瀚','博','文','学','恒','怀','清','淳','淇','淑'],
    '火': ['煜','炜','烨','辉','耀','明','昶','旭','晨','昕','昊','昱','俊','伦','信'],
    '土': ['安','宇','宸','圣','均','坦','坤','坚','城','堂','维','永','翔','瑞','玮'],
}

# Female-preferred characters (some overlap with above)
_NAME_CHARS_FEMALE = {
    '金': ['钰','锦','瑞','瑜','瑾','琛','珍','珊','玲','玥','琪','琳','瑶','璇','瑷'],
    '木': ['琳','莉','荷','莲','萱','菲','菁','芝','芳','芷','芸','若','茵','花','柳'],
    '水': ['涵','淳','淇','淑','洁','清','漫','汐','澜','雯','雪','雨','云','霞','露'],
    '火': ['婷','丹','彤','红','紫','晓','旭','晴','暄','暖','灵','忆','恬','念','慧'],
    '土': ['安','宛','婉','娟','媛','佳','妍','嫣','瑛','瑶','玥','圣','瑛','碧','瑰'],
}

# Male-preferred characters
_NAME_CHARS_MALE = {
    '金': ['铭','锐','钧','鑫','铮','键','锋','剑','钢','镜','镇','钟','铠','铛','镖'],
    '木': ['林','森','松','柏','桐','楠','楷','杰','嘉','建','毅','刚','坚','奇','国'],
    '水': ['泽','鸿','浩','源','瀚','博','文','学','渊','恒','怀','江','海','涛','洋'],
    '火': ['煜','炜','烨','辉','耀','明','昶','旭','晨','昊','昱','俊','伦','信','亮'],
    '土': ['安','宇','宸','圣','均','坦','坤','坚','城','堂','维','翔','瑞','玮','硕'],
}


def generate_names(surname, chart_data, gender='male', top_n=10):
    """
    Generate name recommendations based on BaZi chart.
    """
    fav, unfav = infer_xishen_from_chart(chart_data)

    # Select primary and secondary elements
    primary_wu = fav[0] if fav else '木'
    secondary_wu = fav[1] if len(fav) > 1 else '火'

    # Get character pools
    char_pool = _NAME_CHARS_FEMALE if gender == 'female' else _NAME_CHARS_MALE

    primary_chars = char_pool.get(primary_wu, [])
    secondary_chars = char_pool.get(secondary_wu, [])

    # If not enough chars in target element, supplement from all pools
    if len(primary_chars) < 5:
        for elem in char_pool:
            if elem not in unfav:
                primary_chars.extend(char_pool[elem])
        primary_chars = list(dict.fromkeys(primary_chars))[:30]

    if len(secondary_chars) < 5:
        for elem in char_pool:
            if elem not in unfav:
                secondary_chars.extend(char_pool[elem])
        secondary_chars = list(dict.fromkeys(secondary_chars))[:30]

    # Filter out chars with missing Kangxi strokes
    primary_chars = [c for c in primary_chars if c in KANGXI_STROKES or c in SIMP_KX]
    secondary_chars = [c for c in secondary_chars if c in KANGXI_STROKES or c in SIMP_KX]

    # Generate candidates
    candidates = []

    # Strategy 1: primary + secondary (best)
    for c1 in primary_chars[:15]:
        for c2 in secondary_chars[:15]:
            if c1 == c2:
                continue
            candidates.append((c1 + c2, f'{primary_wu}+{secondary_wu}'))

    # Strategy 2: primary + primary (good)
    for i, c1 in enumerate(primary_chars[:10]):
        for c2 in primary_chars[i + 1:][:10]:
            candidates.append((c1 + c2, f'{primary_wu}+{primary_wu}'))

    # Strategy 3: secondary + primary (also good)
    for c1 in secondary_chars[:10]:
        for c2 in primary_chars[:10]:
            if c1 == c2:
                continue
            candidates.append((c1 + c2, f'{secondary_wu}+{primary_wu}'))

    # Score each candidate
    scored = []
    for given_name, strategy in candidates:
        result = evaluate_name(surname, given_name, chart_data, gender)
        result['strategy'] = strategy
        scored.append(result)

    # Sort by total score
    scored.sort(key=lambda x: -x['total_score'])

    # Deduplicate similar names (same score = pick first)
    seen = set()
    unique = []
    for r in scored:
        if r['name'] not in seen:
            seen.add(r['name'])
            unique.append(r)

    return unique[:top_n]


# =============================================================================
# 10. 报告格式化
# =============================================================================

def format_name_report(evaluation):
    """Format a name evaluation as a readable text report."""
    lines = []
    lines.append(f'══════ 姓名评测报告 ══════')
    lines.append(f'姓名: {evaluation["name"]}')
    lines.append(f'生肖: {evaluation["zodiac"]}')
    lines.append(f'喜用神: {",".join(evaluation["xishen"])} / 忌神: {",".join(evaluation["jishen"])}')
    lines.append('')

    # 五格 table
    lines.append('【五格剖象】')
    lines.append(f'{"格名":<6} {"笔画":<6} {"数理":<6} {"吉凶":<6} {"含义"}')
    lines.append('─' * 55)
    wuge = evaluation['wuge']
    for key in ['天格','人格','地格','外格','总格']:
        w = wuge[key]
        lines.append(f'{key:<6} {w["strokes"]:<6} {w["num"]:<6} '
                     f'{w["shuli"]:<6} {w["shuli_meaning"]}')
    lines.append("")

    # 三才
    sancai = evaluation['sancai']
    lines.append(f'【三才配置】{sancai["config"]} — {sancai["category_name"]}')
    lines.append(f'  {sancai["judgment"]}')
    lines.append("")

    # Scoring
    lines.append('【综合评分】')
    scores = evaluation['scores']
    for dim, s in scores.items():
        bar = '#' * (s['score'] * 20 // s['max']) + '.' * (20 - s['score'] * 20 // s['max'])
        lines.append(f'  {dim:<8} {s["score"]:>2}/{s["max"]} {bar}')
        if s.get('detail'):
            lines.append(f'          {s["detail"]}')
    lines.append(f'  {"总计":<8} {evaluation["total_score"]:>2}/{evaluation["max_score"]}')
    lines.append("")
    lines.append(f'【评级】{evaluation["grade"]}')
    lines.append(f'【建议】{evaluation["verdict"]}')

    return '\n'.join(lines)


def format_generate_report(names, chart_data):
    """Format name generation results."""
    fav, _ = infer_xishen_from_chart(chart_data)
    lines = []
    lines.append(f'══════ 取名推荐 ══════')
    lines.append(f'喜用神: {",".join(fav)}')
    lines.append("")

    for i, r in enumerate(names):
        lines.append(f'{i+1}. {r["name"]}  评分:{r["total_score"]} | {r["grade"]} | 策略:{r["strategy"]}')
        wu_list = r['scores']['五行匹配'].get('wu_list', [])
        lines.append(f'   五行: {", ".join(wu_list)}')
        wuge = r['wuge']
        lines.append(f'   五格: 天{wuge["天格"]["strokes"]}/人{wuge["人格"]["strokes"]}/地{wuge["地格"]["strokes"]}')
        lines.append(f'   三才: {r["sancai"]["config"]} {r["sancai"]["category_name"]}')
        lines.append()

    return '\n'.join(lines)


# =============================================================================
# 11. CLI
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description='姓名×八字匹配系统')
    ap.add_argument('--name', '-n', help='已有名字(含姓)，如"张伟" — 与--chart配合评测')
    ap.add_argument('--surname', default='张', help='姓 (默认: 张)')
    ap.add_argument('--chart', '-c', required=True, help='BaZi chart JSON 路径')
    ap.add_argument('--generate', '-g', action='store_true', help='生成推荐名字')
    ap.add_argument('--gender', choices=['male','female'], default='male', help='性别')
    ap.add_argument('--top', type=int, default=10, help='推荐数量 (默认10)')
    ap.add_argument('--output', '-o', help='Output JSON file')
    ap.add_argument('--text', action='store_true', help='Text report output')
    args = ap.parse_args()

    with open(args.chart, 'r', encoding='utf-8') as f:
        chart_data = json.load(f)

    if args.generate:
        # Name generation mode
        results = generate_names(args.surname, chart_data, args.gender, args.top)
        if args.text or not args.output:
            print(format_generate_report(results, chart_data))
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f'Saved: {args.output}')

    elif args.name:
        # Name evaluation mode
        surname = args.name[0]  # First char is surname
        given_name = args.name[1:]  # Rest is given name
        result = evaluate_name(surname, given_name, chart_data, args.gender)
        if args.text or not args.output:
            print(format_name_report(result))
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f'Saved: {args.output}')

    else:
        ap.error('Either --name (evaluate) or --generate (suggest names) is required')


if __name__ == '__main__':
    main()
