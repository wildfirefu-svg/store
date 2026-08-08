#!/usr/bin/env python3
"""
流年日历 v2.0 — 个人化12月详细运势月历

Generates a detailed 12-month fortune calendar personalized to an individual's BaZi chart.
Each month includes: 干支, 十神, 大运互动, 四柱互动, 重点领域评分, 宜忌, 神煞.

Usage:
    python knowledge-base/liunian_calendar.py --year 1993 --month 7 --day 15 --hour 14 \\
        --gender male --target-year 2026

    python knowledge-base/liunian_calendar.py --chart chart.json --target-year 2026
"""

import argparse
import json
import os
import sys
from datetime import date as dt_date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bazi_calculator import (
    LIUCHONG,
    LIUHAI,
    LIUHE,
    SANXING,
    TAOHUA_MAP,
    TIANGAN,
    TIANYI_GUIREN,
    WENCHANG,
    ZHI_WUXING,
    calculate_dayun,
    calculate_four_pillars,
    calculate_liunian,
    get_shishen,
    sexagenary_by_index,
)

# =============================================================================
# 1. 五虎遁 — 月干计算
# =============================================================================

WUHUDUN = {
    '甲': '丙', '己': '丙',  # 甲己之年丙作首
    '乙': '戊', '庚': '戊',  # 乙庚之岁戊为头
    '丙': '庚', '辛': '庚',  # 丙辛之岁寻庚上
    '丁': '壬', '壬': '壬',  # 丁壬壬寅顺水流
    '戊': '甲', '癸': '甲',  # 戊癸甲寅好追求
}

# Month branch order (寅=1 ... 丑=12)
MONTH_BRANCHES = ['寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥', '子', '丑']


def get_month_pillars_for_year(year_gan):
    """Get 12 month pillar (gan, zhi) pairs for a given year stem."""
    yin_stem = WUHUDUN[year_gan]
    yin_idx = TIANGAN.index(yin_stem)
    pillars = []
    for i, zhi in enumerate(MONTH_BRANCHES):
        gan = TIANGAN[(yin_idx + i) % 10]
        pillars.append((gan, zhi))
    return pillars


def get_year_ganzhi(year):
    """Get (gan, zhi) for a given Gregorian year."""
    idx = (year - 4) % 60
    return sexagenary_by_index(idx)


# =============================================================================
# 2. 月度详细分析引擎
# =============================================================================

WU_ELEMENT_MONTHS = {
    '寅': '木', '卯': '木', '辰': '土',
    '巳': '火', '午': '火', '未': '土',
    '申': '金', '酉': '金', '戌': '土',
    '亥': '水', '子': '水', '丑': '土',
}

# 旺相休囚死 (by season)
SEASON_WANG_SHUAI = {
    '春': {'旺': '木', '相': '火', '休': '水', '囚': '金', '死': '土'},
    '夏': {'旺': '火', '相': '土', '休': '木', '囚': '水', '死': '金'},
    '秋': {'旺': '金', '相': '水', '休': '土', '囚': '火', '死': '木'},
    '冬': {'旺': '水', '相': '木', '休': '金', '囚': '土', '死': '火'},
}

SEASON_MONTHS = {
    '寅': '春', '卯': '春', '辰': '春',
    '巳': '夏', '午': '夏', '未': '夏',
    '申': '秋', '酉': '秋', '戌': '秋',
    '亥': '冬', '子': '冬', '丑': '冬',
}


def get_season_state(month_zhi, element):
    """Get 旺相休囚死 state of an element in a given month."""
    season = SEASON_MONTHS.get(month_zhi, '春')
    sw = SEASON_WANG_SHUAI[season]
    for state, elem in sw.items():
        if elem == element:
            return state
    return '休'


def analyze_month(month_gan, month_zhi, chart_data, dayun_data, current_pillar, target_year):
    """
    Deep analysis of a single month against the person's BaZi chart.
    Returns a dict with all analysis dimensions.
    """
    fp = chart_data.get('four_pillars', {})
    dm = chart_data.get('day_master', {})
    dm_gan = dm.get('gan', '')
    dm_wu = dm.get('wuxing', '')
    dm_yy = dm.get('yinyang', '')

    # Get four pillar branches
    year_zhi = fp.get('year', {}).get('zhi', '')
    month_p_zhi = fp.get('month', {}).get('zhi', '')
    day_zhi = fp.get('day', {}).get('zhi', '')
    hour_zhi = fp.get('hour', {}).get('zhi', '')
    day_gan = fp.get('day', {}).get('gan', '')

    dayun_gan = current_pillar.get('gan', '') if current_pillar else ''
    dayun_zhi = current_pillar.get('zhi', '') if current_pillar else ''

    # --- (A) 十神 ---
    month_shishen = get_shishen(dm_gan, month_gan)

    # --- (B) 月支与四柱互动 ---
    interactions = []
    interaction_score = 0

    for zhi, label in [(year_zhi, '年柱'), (month_p_zhi, '月柱'),
                        (day_zhi, '日柱'), (hour_zhi, '时柱')]:
        pair = (month_zhi, zhi)
        rpair = (zhi, month_zhi)
        if pair in LIUCHONG or rpair in LIUCHONG:
            interactions.append(f'冲{label}({zhi})')
            interaction_score -= 25
        elif pair in LIUHE or rpair in LIUHE:
            interactions.append(f'合{label}({zhi})')
            interaction_score += 15
        elif pair in LIUHAI or rpair in LIUHAI:
            interactions.append(f'害{label}({zhi})')
            interaction_score -= 15
        elif pair in SANXING or rpair in SANXING:
            interactions.append(f'刑{label}({zhi})')
            interaction_score -= 15

    # --- (C) 与大运互动 ---
    dayun_interaction = ''
    dayun_score = 0
    if dayun_zhi:
        pair = (month_zhi, dayun_zhi)
        rpair = (dayun_zhi, month_zhi)
        if pair in LIUCHONG or rpair in LIUCHONG:
            dayun_interaction = f'流月冲大运({month_zhi}冲{dayun_zhi})→动荡'
            dayun_score = -20
        elif pair in LIUHE or rpair in LIUHE:
            dayun_interaction = f'流月合大运({month_zhi}合{dayun_zhi})→顺遂'
            dayun_score = 15
        elif pair in LIUHAI or rpair in LIUHAI:
            dayun_interaction = '流月害大运→小阻'
            dayun_score = -10
        elif pair in SANXING or rpair in SANXING:
            dayun_interaction = '流月刑大运→口舌'
            dayun_score = -10
        else:
            dayun_interaction = '平稳'
            dayun_score = 5

    # --- (D) 月干与大运天干互动 ---
    dayun_gan_interaction = ''
    if dayun_gan and month_gan:
        # Check if 流月干合大运干
        # 天干五合: 甲己/乙庚/丙辛/丁壬/戊癸
        tian_gan_he = {('甲', '己'), ('乙', '庚'), ('丙', '辛'), ('丁', '壬'), ('戊', '癸')}
        if (month_gan, dayun_gan) in tian_gan_he or (dayun_gan, month_gan) in tian_gan_he:
            dayun_gan_interaction = f'流月干{month_gan}合大运干{dayun_gan}→有缘'
            dayun_score += 10

    # --- (E) 神煞 ---
    shensha = []
    # 天乙贵人
    guiren = TIANYI_GUIREN.get(dm_gan, ())
    if month_zhi in guiren:
        shensha.append('天乙贵人')
    # 文昌
    if month_zhi == WENCHANG.get(dm_gan, ''):
        shensha.append('文昌')
    # 桃花
    for group, taohua_zhi in TAOHUA_MAP.items():
        if month_zhi == taohua_zhi:
            shensha.append('桃花')
            break

    # --- (F) 旺相休囚死 ---
    dm_state = get_season_state(month_zhi, dm_wu)

    # --- (G) 月度重点领域评分 ---
    # Determine what month stem's shishen means for each life area
    career_impact = _score_career(month_shishen, dm_gan, dm_wu, dm_state, month_zhi)
    wealth_impact = _score_wealth(month_shishen, dm_gan, dm_wu, dm_state)
    love_impact = _score_love(month_shishen, month_zhi, day_zhi, shensha)
    health_impact = _score_health(month_zhi, interactions, dm_wu, dm_state)

    # --- (H) 月度宜忌 ---
    yi, ji = _generate_monthly_yiji(month_shishen, month_zhi, interactions,
                                     shensha, dm_wu, dm_state)

    # --- Overall score ---
    base_score = 60  # neutral baseline
    # Shishen quality
    auspicious = {'正财', '偏财', '正官', '正印', '偏印', '食神'}
    neutral = {'比肩', '劫财', '伤官', '七杀'}
    if month_shishen in auspicious:
        base_score += 10
    elif month_shishen == '七杀':
        base_score -= 10
    elif month_shishen == '伤官':
        base_score -= 5

    # DM state
    if dm_state == '旺':
        base_score += 10
    elif dm_state == '死':
        base_score -= 10
    elif dm_state == '囚':
        base_score -= 5

    overall_score = base_score + interaction_score + dayun_score
    overall_score = max(0, min(100, overall_score))

    # Rating
    if overall_score >= 80:
        rating_text = '大吉'
        rating_stars = 5
    elif overall_score >= 65:
        rating_text = '吉'
        rating_stars = 4
    elif overall_score >= 50:
        rating_text = '平'
        rating_stars = 3
    elif overall_score >= 35:
        rating_text = '小凶'
        rating_stars = 2
    else:
        rating_text = '凶'
        rating_stars = 1

    return {
        'month_ganzhi': month_gan + month_zhi,
        'month_shishen': month_shishen,
        'dm_state': dm_state,
        'interactions': interactions,
        'interaction_score': interaction_score,
        'dayun_interaction': dayun_interaction,
        'dayun_gan_interaction': dayun_gan_interaction,
        'dayun_score': dayun_score,
        'shensha': shensha,
        'overall_score': overall_score,
        'rating': rating_text,
        'rating_stars': rating_stars,
        'career': career_impact,
        'wealth': wealth_impact,
        'love': love_impact,
        'health': health_impact,
        'yi': yi,
        'ji': ji,
    }


def _score_career(shishen, dm_gan, dm_wu, dm_state, month_zhi):
    """Score career dimension for this month."""
    score = 3
    notes = []

    if shishen in ('正官', '七杀'):
        score += 1
        notes.append('官杀透干→事业压力/动力')
    if shishen in ('正印', '偏印'):
        score += 1
        notes.append('印星当令→有贵人/文书支持')
        if shishen == '偏印':
            notes.append('偏印→注意过度思虑')
    if shishen == '食神':
        score += 1
        notes.append('食神→创意/社交活跃')
    if shishen == '伤官':
        score -= 1
        notes.append('伤官→注意口舌/与上级冲突')
    if shishen in ('比肩', '劫财'):
        notes.append('比劫→竞争激烈/合作需谨慎')

    if dm_state in ('旺', '相'):
        score += 1
    elif dm_state in ('死', '囚'):
        score -= 1

    score = max(1, min(5, score))
    return {'score': score, 'notes': '；'.join(notes) if notes else '平稳'}


def _score_wealth(shishen, dm_gan, dm_wu, dm_state):
    """Score wealth dimension for this month."""
    score = 3
    notes = []

    if shishen in ('正财', '偏财'):
        score += 1
        notes.append(f'{shishen}透干→财运机会')
        if shishen == '偏财':
            notes.append('偏财→意外之财/投机')
    if shishen in ('食神', '伤官'):
        notes.append('食伤生财→技术/创意变现')
    if shishen == '劫财':
        score -= 1
        notes.append('劫财透干→注意破财/被借')
    if shishen in ('正印', '偏印'):
        notes.append('印星→财运平稳/利守成')

    if dm_state in ('旺', '相'):
        score += 1

    score = max(1, min(5, score))
    return {'score': score, 'notes': '；'.join(notes) if notes else '平稳'}


def _score_love(shishen, month_zhi, day_zhi, shensha):
    """Score relationship dimension for this month."""
    score = 3
    notes = []

    # 桃花 month
    if '桃花' in shensha:
        score += 1
        notes.append('桃花月→异性缘旺')

    # Month branch interaction with day branch
    pair = (month_zhi, day_zhi)
    rpair = (day_zhi, month_zhi)
    if pair in LIUHE or rpair in LIUHE:
        score += 1
        notes.append('月支合日支→感情顺遂')
    elif pair in LIUCHONG or rpair in LIUCHONG:
        score -= 1
        notes.append('月支冲日支→感情波动')
    elif pair in LIUHAI or rpair in LIUHAI:
        score -= 1
        notes.append('月支害日支→有小摩擦')

    if shishen in ('正官', '七杀') and '桃花' not in shensha:
        notes.append('官杀月→对女性来说桃花/夫缘')

    if shishen == '伤官':
        notes.append('伤官月→女性注意与配偶口舌')

    score = max(1, min(5, score))
    return {'score': score, 'notes': '；'.join(notes) if notes else '平稳'}


def _score_health(month_zhi, interactions, dm_wu, dm_state):
    """Score health dimension for this month."""
    score = 3
    notes = []

    # 冲刑害 → health risk
    has_chong = any('冲' in i for i in interactions)
    has_xing = any('刑' in i for i in interactions)
    if has_chong:
        score -= 1
        notes.append('有冲→注意意外/情绪波动')
    if has_xing:
        score -= 1
        notes.append('有刑→注意小伤病/炎症')

    if dm_state == '死':
        score -= 1
        notes.append('日主处死地→精力不足')

    # Month element vs DM element (克的关系)
    month_wu = ZHI_WUXING.get(month_zhi, '')
    destroy = {('金', '木'), ('木', '土'), ('土', '水'), ('水', '火'), ('火', '金')}
    if (month_wu, dm_wu) in destroy:
        notes.append(f'月{month_wu}克日{dm_wu}→注意对应脏腑')

    score = max(1, min(5, score))
    return {'score': score, 'notes': '；'.join(notes) if notes else '平稳'}


def _generate_monthly_yiji(shishen, month_zhi, interactions, shensha, dm_wu, dm_state):
    """Generate monthly 宜忌 based on the analysis."""
    yi = []
    ji = []

    # Base on shishen
    if shishen in ('正财', '偏财'):
        yi.extend(['理财', '投资(谨慎)', '签约'])
        ji.append('赌博/投机过度')
    elif shishen in ('正官', '七杀'):
        yi.extend(['事业规划', '面试', '签约'])
        ji.extend(['顶撞上司', '诉讼'])
    elif shishen in ('正印', '偏印'):
        yi.extend(['学习', '考试', '文化活动', '签约'])
        ji.append('懒散拖延')
    elif shishen == '食神':
        yi.extend(['社交', '创作', '美食', '出行'])
    elif shishen == '伤官':
        yi.extend(['创作', '技术突破', '演讲'])
        ji.extend(['口舌争执', '顶撞上司'])
    elif shishen == '比肩':
        yi.extend(['合作', '团队活动'])
        ji.extend(['合伙投资', '借钱'])
    elif shishen == '劫财':
        yi.extend(['独立工作'])
        ji.extend(['投资', '合伙', '借钱'])

    # 桃花 month
    if '桃花' in shensha:
        yi.append('社交/约会')
        ji.append('烂桃花/冲动表白')

    # 贵人 month
    if '天乙贵人' in shensha:
        yi.append('拜访贵人/求助')

    # 冲 months
    has_chong = any('冲' in i for i in interactions)
    if has_chong:
        ji.extend(['重大决策', '动土', '远行(注意安全)'])

    return yi[:5], ji[:5]


# =============================================================================
# 3. 年度运势总览
# =============================================================================

def analyze_year_overview(months_analysis, liunian_ganzhi, dayun_pillar, chart_data):
    """Generate year-level overview based on aggregated monthly analysis."""
    dm = chart_data.get('day_master', {})

    # Average scores
    avg_career = sum(m['career']['score'] for m in months_analysis) / 12
    avg_wealth = sum(m['wealth']['score'] for m in months_analysis) / 12
    avg_love = sum(m['love']['score'] for m in months_analysis) / 12
    avg_health = sum(m['health']['score'] for m in months_analysis) / 12

    # Best and worst months
    best_month = max(months_analysis, key=lambda m: m['overall_score'])
    worst_month = min(months_analysis, key=lambda m: m['overall_score'])

    # Key themes
    key_themes = []
    liunian_gan = liunian_ganzhi[0] if liunian_ganzhi else ''
    liunian_shishen = get_shishen(dm.get('gan', ''), liunian_gan) if liunian_gan else ''

    if liunian_shishen in ('正财', '偏财'):
        key_themes.append(f'{liunian_ganzhi}年——财年主事，财运为主线')
    elif liunian_shishen in ('正官', '七杀'):
        key_themes.append(f'{liunian_ganzhi}年——官杀年主事，事业/压力为主线')
    elif liunian_shishen in ('正印', '偏印'):
        key_themes.append(f'{liunian_ganzhi}年——印星年主事，学习/贵人/稳定为主线')
    elif liunian_shishen in ('食神', '伤官'):
        key_themes.append(f'{liunian_ganzhi}年——食伤年主事，创作/变化为主线')
    else:
        key_themes.append(f'{liunian_ganzhi}年——比劫年主事，竞争/合作/人脉为主线')

    if dayun_pillar:
        key_themes.append(f'大运{dayun_pillar.get("gan","")}{dayun_pillar.get("zhi","")}中')

    return {
        'avg_scores': {
            'career': round(avg_career, 1),
            'wealth': round(avg_wealth, 1),
            'love': round(avg_love, 1),
            'health': round(avg_health, 1),
        },
        'best_month': {'month': best_month['month'], 'rating': best_month['rating'],
                        'ganzhi': best_month['month_ganzhi']},
        'worst_month': {'month': worst_month['month'], 'rating': worst_month['rating'],
                         'ganzhi': worst_month['month_ganzhi']},
        'key_themes': key_themes,
        'good_months': [m['month'] for m in months_analysis if m['rating_stars'] >= 4],
        'caution_months': [m['month'] for m in months_analysis if m['rating_stars'] <= 2],
    }


# =============================================================================
# 4. 主引擎
# =============================================================================

def generate_year_calendar(year, month, day, hour, gender, target_year=None,
                           chart_data=None):
    """Generate detailed annual fortune calendar for a person."""
    if target_year is None:
        target_year = dt_date.today().year

    if chart_data:
        fp_data = chart_data.get('four_pillars', {})
        dm = chart_data.get('day_master', {})
        dayun_data = chart_data.get('da_yun', [])
    else:
        fp_data = calculate_four_pillars(year, month, day, hour, 0, 'Beijing')
        dm = fp_data.get('day_master', {})
        yp = (fp_data['year']['gan'], fp_data['year']['zhi'])
        mp = (fp_data['month']['gan'], fp_data['month']['zhi'])
        dayun_data_raw = calculate_dayun(yp, mp, gender, year, month, day)
        dayun_data = dayun_data_raw.get('pillars', [])
        chart_data = {'four_pillars': fp_data, 'day_master': dm, 'da_yun': dayun_data}

    # Current luck pillar
    current_age = target_year - year
    current_pillar = None
    for p in dayun_data:
        if p.get('start_age', 0) <= current_age < p.get('end_age', 999):
            current_pillar = p
            break

    # 流年干支
    year_gan, year_zhi = get_year_ganzhi(target_year)
    liunian_ganzhi = year_gan + year_zhi

    # 流月 pillars
    month_pillars = get_month_pillars_for_year(year_gan)

    # Analyze each month
    months_analysis = []
    for i, (m_gan, m_zhi) in enumerate(month_pillars):
        analysis = analyze_month(m_gan, m_zhi, chart_data, dayun_data,
                                 current_pillar, target_year)
        analysis['month'] = i + 1
        analysis['month_branch'] = m_zhi
        months_analysis.append(analysis)

    # Year overview
    overview = analyze_year_overview(months_analysis, liunian_ganzhi,
                                     current_pillar, chart_data)

    # Format month data
    months_output = []
    for m in months_analysis:
        months_output.append({
            'month': m['month'],
            'branch': m['month_branch'],
            'ganzhi': m['month_ganzhi'],
            'shishen': m['month_shishen'],
            'dm_state': m['dm_state'],
            'interactions': m['interactions'],
            'dayun_interaction': m['dayun_interaction'],
            'shensha': m['shensha'],
            'rating': m['rating'],
            'rating_stars': m['rating_stars'],
            'overall_score': m['overall_score'],
            'career': m['career'],
            'wealth': m['wealth'],
            'love': m['love'],
            'health': m['health'],
            'yi': m['yi'],
            'ji': m['ji'],
        })

    # Upcoming liunian
    liunian_future = calculate_liunian(target_year, dm.get('gan', ''), 3)

    return {
        'person': {
            'year': year, 'month': month, 'day': day, 'hour': hour, 'gender': gender,
            'day_master_gan': dm.get('gan', ''),
            'day_master_wuxing': dm.get('wuxing', ''),
        },
        'target_year': target_year,
        'liunian_ganzhi': liunian_ganzhi,
        'liunian_shishen': get_shishen(dm.get('gan', ''), year_gan) if dm.get('gan') else '',
        'current_age': current_age,
        'current_dayun': current_pillar,
        'overview': overview,
        'months': months_output,
        'liunian_3years': liunian_future,
    }


# =============================================================================
# 5. CLI
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description='流年日历 v2.0 — 个人化12月运势月历')
    ap.add_argument('--year', type=int, help='Birth year')
    ap.add_argument('--month', type=int, help='Birth month')
    ap.add_argument('--day', type=int, help='Birth day')
    ap.add_argument('--hour', type=int, default=8, help='Birth hour')
    ap.add_argument('--gender', default='male')
    ap.add_argument('--target-year', type=int, help='Target year (default: current)')
    ap.add_argument('--chart', '-c', help='Path to BaZi chart JSON (alternative to birth params)')
    ap.add_argument('--output', '-o', help='Output JSON file')
    ap.add_argument('--text', action='store_true', help='Human-readable text output')
    args = ap.parse_args()

    # Load chart or use birth params
    chart_data = None
    if args.chart:
        with open(args.chart, 'r', encoding='utf-8') as f:
            chart_data = json.load(f)
        fp = chart_data.get('four_pillars', {})
        dm = chart_data.get('day_master', {})
        # Use birth_info from chart if available, else estimate
        birth = chart_data.get('birth_info', {})
        if birth:
            args.year = args.year or birth.get('year')
            args.month = args.month or birth.get('month')
            args.day = args.day or birth.get('day')
            args.hour = birth.get('hour', args.hour)
            args.gender = birth.get('gender', args.gender)
        else:
            by = args.target_year - 35 if args.target_year else dt_date.today().year - 35
            args.year = args.year or by
            args.month = args.month or 1
            args.day = args.day or 1
    elif not args.year:
        ap.error('Either --chart or --year/--month/--day is required')

    cal = generate_year_calendar(args.year, args.month, args.day, args.hour,
                                  args.gender, args.target_year, chart_data)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(cal, f, ensure_ascii=False, indent=2)
        print(f'Saved: {args.output}')

    if args.text or not args.output:
        person = cal['person']
        dm = f"{person['day_master_gan']}({person['day_master_wuxing']})"
        print(f'══════ {cal["target_year"]}年 流年运势月历 ══════')
        print(f'命主日主: {dm} | 流年: {cal["liunian_ganzhi"]}({cal["liunian_shishen"]})')
        cp = cal['current_dayun']
        if cp:
            print(f'当前大运: {cp["gan"]}{cp["zhi"]} '
                  f'({cp.get("start_age","")}-{cp.get("end_age","")}岁)')
        print()

        ov = cal['overview']
        print('【年度总览】')
        for t in ov['key_themes']:
            print(f'  - {t}')
        avg = ov['avg_scores']
        print(f'  年均评分 — 事业:{avg["career"]} 财运:{avg["wealth"]} '
              f'感情:{avg["love"]} 健康:{avg["health"]}')
        print(f'  最佳月: {ov["best_month"]["month"]}月 '
              f'({ov["best_month"]["ganzhi"]} · {ov["best_month"]["rating"]})')
        print(f'  需注意月: {ov["worst_month"]["month"]}月 '
              f'({ov["worst_month"]["ganzhi"]} · {ov["worst_month"]["rating"]})')
        print()

        print('【12月逐月】')
        print(f'{"月":<4} {"干支":<6} {"十神":<6} {"评分":<6} {"运":<4} '
              f'{"事业":<4} {"财运":<4} {"感情":<4} {"健康":<4} {"要点"}')
        print('─' * 70)
        for m in cal['months']:
            stars = '★' * m['rating_stars'] + '☆' * (5 - m['rating_stars'])
            interactions_str = ','.join(m['interactions']) if m['interactions'] else '-'
            print(f'{m["month"]:<4} {m["ganzhi"]:<6} {m["shishen"]:<6} {stars:<6} '
                  f'{m["dm_state"]:<4} '
                  f'{m["career"]["score"]:<4} {m["wealth"]["score"]:<4} '
                  f'{m["love"]["score"]:<4} {m["health"]["score"]:<4} '
                  f'{interactions_str}')
            if m['shensha']:
                print(f'    神煞: {",".join(m["shensha"])}')
            if m['yi']:
                print(f'    宜: {", ".join(m["yi"][:4])}')
            if m['ji']:
                print(f'    忌: {", ".join(m["ji"][:4])}')
            print(f'    事业: {m["career"]["notes"]}')


if __name__ == '__main__':
    main()
