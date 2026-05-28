#!/usr/bin/env python3
"""
择日系统 v2.0 — 建除十二神 + 黄道吉日 + 八字个人化择吉

Personalized date selection based on individual BaZi chart.
Layers: 建除十二神 → 黄道吉日 → 日柱与命主互动 → 神煞 → 喜用神

Usage:
    # Generic (no chart)
    python knowledge-base/zeri.py --year 2026 --month 6 --purpose 结婚

    # Personalized (with chart)
    python knowledge-base/zeri.py --year 2026 --month 6 --purpose 结婚 --chart chart.json

    # With explicit 喜用神
    python knowledge-base/zeri.py --year 2026 --month 6 --purpose 开业 --chart chart.json --xishen 木,火
"""

import os, sys, json, argparse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bazi_calculator import (
    TIANGAN, DIZHI, GAN_WUXING, ZHI_WUXING, GAN_YINYANG,
    sexagenary_index, sexagenary_by_index, get_shishen,
    get_month_branch_idx, LIUCHONG, LIUHE, LIUHAI, SANXING,
    TIANYI_GUIREN, WENCHANG,
)

# =============================================================================
# 1. 建除十二神 + 黄道
# =============================================================================

JIANCHU = ['建', '除', '满', '平', '定', '执', '破', '危', '成', '收', '开', '闭']
HUANGDAO = {'除', '危', '定', '执', '成', '开'}
HEIDAO = {'建', '满', '平', '破', '收', '闭'}

DAY_TIPS = {
    '建': {'yi': ['祭祀'], 'ji': ['结婚', '开业', '动土', '出行']},
    '除': {'yi': ['治病', '清洁', '除旧', '祈福'], 'ji': ['结婚', '搬家']},
    '满': {'yi': ['祭祀', '祈福', '入仓'], 'ji': ['出行', '搬家', '开业']},
    '平': {'yi': ['修饰', '装修'], 'ji': ['结婚', '开业', '动土']},
    '定': {'yi': ['订婚', '签约', '入学', '祭祀'], 'ji': ['诉讼', '出行']},
    '执': {'yi': ['结婚', '开业', '动土', '出行'], 'ji': ['安葬']},
    '破': {'yi': ['拆屋', '治病'], 'ji': ['结婚', '开业', '出行', '入宅']},
    '危': {'yi': ['祭祀', '祈福', '安床'], 'ji': ['动土', '搬家', '开业']},
    '成': {'yi': ['结婚', '开业', '搬家', '出行', '签约'], 'ji': ['诉讼']},
    '收': {'yi': ['收藏', '入仓', '祭祀'], 'ji': ['开业', '出行', '结婚']},
    '开': {'yi': ['开业', '出行', '结婚', '入宅'], 'ji': ['安葬']},
    '闭': {'yi': ['安葬', '祭祀', '祈福'], 'ji': ['开业', '结婚', '出行']},
}

# 四离日 (春分/秋分/夏至/冬至前一天) and 四绝日 (立春/立夏/立秋/立冬前一天)
# Approximate: these are taboo for most activities
SI_LI_SI_JUE = {
    # 四离: ~Mar 20, ~Jun 21, ~Sep 22, ~Dec 21
    (3, 19), (3, 20), (3, 21), (6, 20), (6, 21), (6, 22),
    (9, 21), (9, 22), (9, 23), (12, 20), (12, 21), (12, 22),
    # 四绝: ~Feb 3, ~May 5, ~Aug 7, ~Nov 7
    (2, 2), (2, 3), (2, 4), (5, 4), (5, 5), (5, 6),
    (8, 6), (8, 7), (8, 8), (11, 6), (11, 7), (11, 8),
}


def get_ri_chen(year, month, day):
    """Get 建除十二神 value for a given date."""
    mb_idx = get_month_branch_idx(year, month, day)
    offset = (day - 1) % 12
    jian_idx = (mb_idx + offset) % 12
    return JIANCHU[jian_idx]


def is_huangdao(rc):
    return rc in HUANGDAO


def is_sili_sijue(month, day):
    """Check if date is approximately a 四离日 or 四绝日."""
    for m, d in SI_LI_SI_JUE:
        if month == m and abs(day - d) <= 1:
            return True
    return False


# =============================================================================
# 2. 日柱干支计算 (万年历算法)
# =============================================================================

def get_day_ganzhi(year, month, day):
    """Get (gan, zhi) for any Gregorian date using Julian day method."""
    from datetime import date as dt_date
    # Known reference: 1900-01-01 = 甲戌日 (index 10)
    ref_date = dt_date(1900, 1, 1)
    target = dt_date(year, month, day)
    delta_days = (target - ref_date).days
    base_idx = sexagenary_index('甲', '戌')
    idx = (base_idx + delta_days) % 60
    return sexagenary_by_index(idx)


# =============================================================================
# 3. 喜用神推断 (简化版)
# =============================================================================

def infer_xishen_from_chart(chart_data):
    """
    Infer 喜用神 from chart data using simplified rules.
    Returns (favorable_elements, unfavorable_elements).
    """
    fp = chart_data.get('four_pillars', {})
    dm = chart_data.get('day_master', {})

    # Count five element occurrences
    wu_counts = {'金': 0, '木': 0, '水': 0, '火': 0, '土': 0}
    for pillar_key in ['year', 'month', 'day', 'hour']:
        p = fp.get(pillar_key, {})
        g = p.get('gan', '')
        z = p.get('zhi', '')
        if g in GAN_WUXING:
            wu_counts[GAN_WUXING[g]] += 1
        if z in ZHI_WUXING:
            wu_counts[ZHI_WUXING[z]] += 1

    dm_wu = dm.get('wuxing', '')
    if not dm_wu:
        return (['木', '火'], ['金', '水'])

    # Month branch check
    month_zhi = fp.get('month', {}).get('zhi', '')
    month_wu = ZHI_WUXING.get(month_zhi, '')

    # Determine if month supports or weakens day master
    # Supporting: month element generates or is same as DM
    generating = {
        ('木', '火'), ('火', '土'), ('土', '金'), ('金', '水'), ('水', '木'),
    }

    month_supports = (month_wu == dm_wu) or ((month_wu, dm_wu) in generating)

    # Infer 喜用神
    if month_supports and wu_counts[dm_wu] >= 3:
        # Strong DM → favor elements DM controls (wealth) or DM generates (output)
        dm_controls = {'木': '土', '火': '金', '土': '水', '金': '木', '水': '火'}
        dm_generates = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
        dm_weakened_by = {'木': '金', '火': '水', '土': '木', '金': '火', '水': '土'}
        favorable = [dm_controls[dm_wu], dm_generates[dm_wu]]
        unfavorable = [dm_weakened_by[dm_wu], dm_wu]
    else:
        # Weak DM → favor elements that generate or same as DM
        dm_generated_by = {'木': '水', '火': '木', '土': '火', '金': '土', '水': '金'}
        dm_controls = {'木': '土', '火': '金', '土': '水', '金': '木', '水': '火'}
        favorable = [dm_generated_by[dm_wu], dm_wu]
        unfavorable = [dm_controls[dm_wu],
                       {'木': '金', '火': '水', '土': '木', '金': '火', '水': '土'}[dm_wu]]

    return (favorable, unfavorable)


# =============================================================================
# 4. 日柱与命主八字互动评分
# =============================================================================

def score_day_personal(day_gan, day_zhi, chart_data, purpose):
    """
    Score a specific day (by gan/zhi) against the person's BaZi chart.
    Returns (score, reasons).
    """
    score = 0
    reasons = []

    fp = chart_data.get('four_pillars', {})
    dm = chart_data.get('day_master', {})
    dm_gan = dm.get('gan', '')
    dm_yy = dm.get('yinyang', '')

    # Get person's four pillar branches
    year_zhi = fp.get('year', {}).get('zhi', '')
    month_zhi = fp.get('month', {}).get('zhi', '')
    day_zhi = fp.get('day', {}).get('zhi', '')
    hour_zhi = fp.get('hour', {}).get('zhi', '')

    # --- (A) 日干与日主十神 ---
    shishen = get_shishen(dm_gan, day_gan)
    auspicious_shen = {'正财', '偏财', '正官', '偏官', '正印', '偏印', '食神', '比肩'}
    neutral_shen = {'劫财', '伤官'}
    # 七杀 and 伤官 are situation-dependent

    if shishen in {'正财', '偏财'}:
        if purpose in ('财运', '开业', '投资', '签约'):
            score += 25
            reasons.append(f'日干{shishen}→利{purpose}')
        else:
            score += 10
            reasons.append(f'日干{shishen}')
    elif shishen in {'正官', '偏官'}:
        if purpose in ('事业', '面试', '签约', '诉讼'):
            score += 20
            reasons.append(f'日干{shishen}→利{purpose}')
        else:
            score += 5
            reasons.append(f'日干{shishen}')
    elif shishen in {'正印', '偏印'}:
        if purpose in ('学业', '考试', '入学', '签约'):
            score += 20
            reasons.append(f'日干{shishen}→利{purpose}')
        else:
            score += 10
            reasons.append(f'日干{shishen}')
    elif shishen in {'食神', '伤官'}:
        if purpose in ('创作', '表演', '出行'):
            score += 15
            reasons.append(f'日干{shishen}→利{purpose}')
        elif purpose in ('结婚', '事业'):
            score -= 10  # 伤官见官/克夫
            reasons.append(f'日干{shishen}→不利{purpose}')
        else:
            score += 5
            reasons.append(f'日干{shishen}')
    elif shishen == '比肩':
        score += 5
        reasons.append(f'日干{shishen}→中性')
    elif shishen == '劫财':
        if purpose in ('财运', '投资', '结婚'):
            score -= 15  # 劫财夺财
            reasons.append(f'日干{shishen}→不利{purpose}')
        else:
            score -= 5
            reasons.append(f'日干{shishen}')

    # --- (B) 日支与日柱冲合 ---
    # 六冲 — worst
    if (day_zhi, day_zhi) in LIUCHONG or (day_zhi, day_zhi) in LIUCHONG:
        pass  # skip same-branch check
    for zhi, label in [(year_zhi, '年柱'), (day_zhi, '日柱'), (month_zhi, '月柱')]:
        if (day_zhi, zhi) in LIUCHONG or (zhi, day_zhi) in LIUCHONG:
            score -= 40
            reasons.append(f'日支冲{label}{zhi}→大忌')
            break

    # 六害
    for zhi, label in [(day_zhi, '日柱'), (month_zhi, '月柱')]:
        if (day_zhi, zhi) in LIUHAI or (zhi, day_zhi) in LIUHAI:
            score -= 25
            reasons.append(f'日支害{label}{zhi}→不利')
            break

    # 六合 — good
    for zhi, label in [(day_zhi, '日柱'), (month_zhi, '月柱')]:
        if (day_zhi, zhi) in LIUHE or (zhi, day_zhi) in LIUHE:
            score += 15
            reasons.append(f'日支合{label}{zhi}→吉')
            break

    # --- (C) 岁破 (日支冲年支) ---
    if (day_zhi, year_zhi) in LIUCHONG or (year_zhi, day_zhi) in LIUCHONG:
        score -= 30
        reasons.append(f'岁破日(冲年支{year_zhi})→忌用')

    # --- (D) 日柱纳音/五行匹配 ---
    day_wu = ZHI_WUXING.get(day_zhi, '')
    dm_wu = dm.get('wuxing', '')
    # Day element generates DM → auspicious
    generating = {('木', '火'), ('火', '土'), ('土', '金'), ('金', '水'), ('水', '木')}
    if (day_wu, dm_wu) in generating:
        score += 10
        reasons.append(f'日{day_wu}生{dm_wu}日主→有助')

    # --- (E) 神煞 — 天乙贵人/文昌 ---
    # Check if this day's branch matches 天乙贵人 for day master
    guiren_branches = TIANYI_GUIREN.get(dm_gan, ())
    if day_zhi in guiren_branches:
        score += 25
        reasons.append(f'天乙贵人日→大吉')

    wenchang_zhi = WENCHANG.get(dm_gan, '')
    if day_zhi == wenchang_zhi:
        score += 15
        reasons.append(f'文昌贵人日→利学业/签约')

    return score, reasons


def score_day_with_xishen(day_gan, day_zhi, xishen_elements):
    """Score a day based on matching 喜用神 elements."""
    score = 0
    reasons = []

    day_wu = ZHI_WUXING.get(day_zhi, '')
    gan_wu = GAN_WUXING.get(day_gan, '')

    if day_wu in xishen_elements:
        score += 10
        reasons.append(f'日支{day_wu}为喜用神')
    if gan_wu in xishen_elements:
        score += 10
        reasons.append(f'日干{gan_wu}为喜用神')

    return score, reasons


# =============================================================================
# 5. 综合择日引擎
# =============================================================================

def find_good_dates(year, month, purpose='通用', top_n=5, chart_data=None, xishen=None):
    """Find auspicious dates, optionally personalized to a BaZi chart."""
    results = []

    for day in range(1, 29):
        d = date(year, month, day)
        rc = get_ri_chen(year, month, day)
        tips = DAY_TIPS.get(rc, {'yi': [], 'ji': []})

        # Layer 1: 建除 + 黄道
        score = 0
        detail = []

        if is_huangdao(rc):
            score += 60
            detail.append(f'{rc}日(黄道)')
        else:
            score += 10  # baseline, not zero
            detail.append(f'{rc}日(黑道)')

        # Layer 1b: 四离四绝
        if is_sili_sijue(month, day):
            score -= 50
            detail.append('四离/四绝日→忌用')

        # Layer 1c: Purpose match
        if purpose in tips.get('yi', []):
            score += 30
            detail.append(f'宜{purpose}')
        if purpose in tips.get('ji', []):
            score -= 50
            detail.append(f'忌{purpose}')

        # Layer 2: BaZi personalization
        if chart_data:
            day_gan, day_zhi = get_day_ganzhi(year, month, day)
            p_score, p_reasons = score_day_personal(day_gan, day_zhi, chart_data, purpose)
            score += p_score
            detail.extend(p_reasons)

            # Layer 3: 喜用神 match
            if xishen:
                x_score, x_reasons = score_day_with_xishen(day_gan, day_zhi, xishen)
                score += x_score
                detail.extend(x_reasons)

        # Build result
        day_gan, day_zhi = get_day_ganzhi(year, month, day)
        weekday_names = ['一', '二', '三', '四', '五', '六', '日']
        results.append({
            'date': str(d),
            'weekday': weekday_names[d.weekday()],
            'ri_chen': rc,
            'ri_ganzhi': day_gan + day_zhi,
            'huangdao': is_huangdao(rc),
            'score': score,
            'yi': tips.get('yi', []),
            'ji': tips.get('ji', []),
            'detail': detail,
        })

    results.sort(key=lambda x: -x['score'])
    return results[:top_n]


def find_good_dates_range(start_date, end_date, purpose='通用', top_n=10,
                          chart_data=None, xishen=None):
    """Find auspicious dates over a date range."""
    results = []
    d = start_date
    while d <= end_date:
        rc = get_ri_chen(d.year, d.month, d.day)
        tips = DAY_TIPS.get(rc, {'yi': [], 'ji': []})
        score = 0
        detail = []

        if is_huangdao(rc):
            score += 60
            detail.append(f'{rc}日(黄道)')
        else:
            score += 10
            detail.append(f'{rc}日(黑道)')

        if is_sili_sijue(d.month, d.day):
            score -= 50
            detail.append('四离/四绝日→忌用')

        if purpose in tips.get('yi', []):
            score += 30
            detail.append(f'宜{purpose}')
        if purpose in tips.get('ji', []):
            score -= 50
            detail.append(f'忌{purpose}')

        if chart_data:
            day_gan, day_zhi = get_day_ganzhi(d.year, d.month, d.day)
            p_score, p_reasons = score_day_personal(day_gan, day_zhi, chart_data, purpose)
            score += p_score
            detail.extend(p_reasons)
            if xishen:
                x_score, x_reasons = score_day_with_xishen(day_gan, day_zhi, xishen)
                score += x_score
                detail.extend(x_reasons)

        weekday_names = ['一', '二', '三', '四', '五', '六', '日']
        results.append({
            'date': str(d),
            'weekday': weekday_names[d.weekday()],
            'ri_chen': rc,
            'ri_ganzhi': get_day_ganzhi(d.year, d.month, d.day)[0] +
                         get_day_ganzhi(d.year, d.month, d.day)[1],
            'huangdao': is_huangdao(rc),
            'score': score,
            'yi': tips.get('yi', []),
            'ji': tips.get('ji', []),
            'detail': detail,
        })
        d += timedelta(days=1)

    results.sort(key=lambda x: -x['score'])
    return results[:top_n]


# =============================================================================
# 6. CLI
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description='择日系统 v2.0 — 八字个人化择吉')
    ap.add_argument('--year', type=int, default=2026, help='Target year')
    ap.add_argument('--month', type=int, default=6, help='Target month (1-12)')
    ap.add_argument('--purpose', default='通用',
                    help='Purpose: 结婚/开业/搬家/出行/订婚/签约/入学/诉讼/投资')
    ap.add_argument('--range', type=int, default=1, help='Months to search')
    ap.add_argument('--chart', '-c', help='Path to BaZi chart JSON (from bazi_calculator.py)')
    ap.add_argument('--xishen', help='喜用神五行, comma-separated (e.g. "木,火")')
    ap.add_argument('--output', '-o', help='Output JSON file')
    ap.add_argument('--top', type=int, default=5, help='Top N results (default 5)')
    args = ap.parse_args()

    # Load chart if provided
    chart_data = None
    xishen = None
    if args.chart:
        with open(args.chart, 'r', encoding='utf-8') as f:
            chart_data = json.load(f)
        if not args.xishen:
            fav, unfav = infer_xishen_from_chart(chart_data)
            xishen = fav
            print(f'[自动推断喜用神: {",".join(fav)} / 忌神: {",".join(unfav)}]')
        else:
            xishen = [x.strip() for x in args.xishen.split(',')]
    elif args.xishen:
        xishen = [x.strip() for x in args.xishen.split(',')]

    # Search
    if args.range == 1:
        dates = find_good_dates(args.year, args.month, args.purpose,
                                top_n=args.top, chart_data=chart_data, xishen=xishen)
    else:
        start = date(args.year, args.month, 1)
        end_month = args.month + args.range - 1
        end_year = args.year + (end_month - 1) // 12
        end_month = ((end_month - 1) % 12) + 1
        end = date(end_year, end_month, 28)
        dates = find_good_dates_range(start, end, args.purpose,
                                      top_n=args.top, chart_data=chart_data, xishen=xishen)

    # Output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump({'purpose': args.purpose, 'dates': dates}, f,
                      ensure_ascii=False, indent=2)
        print(f'Saved: {args.output}')
    else:
        personalized = '(个人化)' if chart_data else '(通用)'
        print(f'=== {args.purpose}吉日推荐 {personalized} {args.year}年{args.month}月 ===')
        if xishen:
            print(f'喜用神: {",".join(xishen)}')
        if chart_data:
            dm = chart_data.get('day_master', {})
            print(f'日主: {dm.get("gan", "?")}({dm.get("wuxing", "?")})')
        print()
        for i, d in enumerate(dates):
            icon = '吉' if d['huangdao'] else '平'
            yi_str = ' '.join(d['yi'][:4]) or '无'
            ji_str = ' '.join(d['ji'][:4]) or '无'
            print(f'{i + 1}. {d["date"]} 周{d["weekday"]} [{icon}] '
                  f'{d["ri_chen"]}日 {d["ri_ganzhi"]} (score:{d["score"]})')
            print(f'   宜: {yi_str}  忌: {ji_str}')
            if d['detail']:
                detail_str = ' | '.join(d['detail'][:5])
                print(f'   分析: {detail_str}')


if __name__ == '__main__':
    main()
