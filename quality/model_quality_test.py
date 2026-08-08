#!/usr/bin/env python3
"""
BaZi Model Quality Tester
Reads cases_real.json, runs chart calculation, and validates event alignment
with 大运 (luck pillars) and 流年 (annual pillars).
"""

import json
import os
import sys
from collections import defaultdict
from datetime import date

# Add parent dir to path so we can import bazi_calculator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bazi_calculator as bc

# =============================================================================
# 1. LOAD DATA
# =============================================================================

CASES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'data', 'cases_real_db.json')
with open(CASES_PATH, 'r', encoding='utf-8') as f:
    db = json.load(f)
cases = db.get('cases', db) if isinstance(db, dict) else db

# Filter: known hour cases only
test_cases = [c for c in cases if not c['birth'].get('hour_unknown')]
print(f"Testable cases (known hour): {len(test_cases)}")

# Also include high-event cases even if hour unknown (we can analyze 三柱)
all_cases_by_events = sorted(cases, key=lambda c: len(c.get('events', [])), reverse=True)

# =============================================================================
# 2. EVENT CATEGORY → 十神 MAPPING
# =============================================================================

# Which 十神 patterns are expected for each event type
# Format: {category: {十神: weight}}
EVENT_SHISHEN_MAP = {
    'career': {
        '正官': 2, '七杀': 2, '正印': 1.5, '偏印': 1.5,
        '食神': 1, '伤官': 1, '正财': -0.5,
    },
    'wealth': {
        '正财': 2, '偏财': 2, '食神': 1.5, '伤官': 1.5,
        '正官': -0.5, '七杀': -0.5,
    },
    'relationship': {
        '正财': 1.5, '偏财': 1.5, '正官': 1.5, '七杀': 1.5,
        '比肩': 0.5, '劫财': 0.5,
    },
    'family': {
        '正印': 2, '偏印': 2, '比肩': 1.5, '劫财': 1.5,
    },
    'health': {
        # Health events often relate to clashes with day master
        # Negative 十神 (忌神) affect health
        # We check clashes/combinations rather than specific 十神
    },
    'education': {
        '正印': 2, '偏印': 2, '食神': 1, '伤官': 1,
    },
}

# =============================================================================
# 3. PARSE BIRTH DATE FROM CASE
# =============================================================================

def parse_birth(case):
    """Extract year, month, day, hour, minute, gender, timezone from case data."""
    dt_str = case['birth']['datetime']
    tz_offset = 8  # default Beijing
    if '+' in dt_str:
        tz_part = dt_str.rsplit('+', 1)[1]
        tz_parts = tz_part.split(':')
        tz_offset = int(tz_parts[0]) + int(tz_parts[1]) / 60.0 if len(tz_parts) > 1 else int(tz_parts[0])
    clean = dt_str.split('+')[0].replace('T', '-').replace(':', '-').split('-')
    year = int(clean[0])
    month = int(clean[1])
    day = int(clean[2])
    hour = int(clean[3]) if len(clean) > 3 else 12
    minute = int(clean[4]) if len(clean) > 4 else 0
    gender = case['gender']
    return year, month, day, hour, minute, gender, tz_offset

# =============================================================================
# 4. MAP YEAR TO LUCK PILLAR AND ANNUAL PILLAR
# =============================================================================

# 地支六冲
OPPOSITE_BRANCH = {
    '子': '午', '午': '子', '丑': '未', '未': '丑',
    '寅': '申', '申': '寅', '卯': '酉', '酉': '卯',
    '辰': '戌', '戌': '辰', '巳': '亥', '亥': '巳',
}

def get_year_liunian(year):
    """Get the 干支 for a given Gregorian year (simplified - uses 60-year cycle)."""
    base_year = 1984
    offset = (year - base_year) % 60
    gan_idx = offset % 10
    zhi_idx = offset % 12
    return bc.TIANGAN[gan_idx], bc.DIZHI[zhi_idx]

def find_dayun_for_year(dayun_pillars, event_year, birth_year, starting_age):
    """Find which luck pillar covers a given year. Returns None for pre-dayun period."""
    age = event_year - birth_year
    if age < 0:
        return None
    if age < starting_age:
        return None  # before luck starts (童运)
    for d in dayun_pillars:
        if d['start_age'] <= age <= d['end_age']:
            return d
    return None

def compute_dayun_shishen(dayun_pillar, day_master):
    """Compute 十神 for a dayun pillar's gan and zhi (main qi)."""
    gan_ss = bc.get_shishen(day_master, dayun_pillar['gan'])
    zhi_main_qi = bc.CANGAN.get(dayun_pillar['zhi'], [('',)])[0][0]
    zhi_ss = bc.get_shishen(day_master, zhi_main_qi) if zhi_main_qi else ''
    return gan_ss, zhi_ss

# =============================================================================
# 5. SCORING ENGINE
# =============================================================================

def score_event(event, dayun, liu_nian_gan, liu_nian_zhi, day_master, four_pillars):
    """
    Score how well an event aligns with the chart.
    Returns (score, reasons) tuple.
    score: -1 to 3 (negative=contradicts, 0=neutral, 1=weak, 2=moderate, 3=strong)
    """
    category = event['category']
    max_score = 3.0
    reasons = []
    score = 0.0

    # Special handling for "birth" events (born that year) - always match
    if category == 'family' and event['year'] <= 1960 and '出生' in event.get('description', ''):
        return 1.0, ['出生事件，自动匹配']

    if dayun is None:
        return 0.0, ['无大运数据(童运期)']

    # Get 十神 of dayun
    dayun_shishen_gan, dayun_shishen_zhi = compute_dayun_shishen(dayun, day_master)
    liunian_shishen = bc.get_shishen(day_master, liu_nian_gan)

    shishen_map = EVENT_SHISHEN_MAP.get(category, {})

    # Check dayun 十神 match
    for ss, weight in shishen_map.items():
        if ss == dayun_shishen_gan:
            score += weight * 0.3
            reasons.append(f'大运天干{ss}({weight:+.1f})')
        if ss == dayun_shishen_zhi:
            score += weight * 0.2
            reasons.append(f'大运地支{ss}({weight:+.1f})')

    # Check 流年 match
    if liunian_shishen in shishen_map:
        score += shishen_map[liunian_shishen] * 0.15
        reasons.append(f'流年{liunian_shishen}({shishen_map[liunian_shishen]:+.1f})')

    # Check for clashes with day master (significant for health)
    if category == 'health':
        day_zhi = four_pillars['day']['zhi']
        # 流年冲日支 or 大运冲日支 = health risk
        if liu_nian_zhi and OPPOSITE_BRANCH.get(liu_nian_zhi) == day_zhi:
            score += 1.0
            reasons.append('流年冲日支')
        if dayun and OPPOSITE_BRANCH.get(dayun['zhi']) == day_zhi:
            score += 0.8
            reasons.append('大运冲日支')
        # 流年伏吟日柱
        if liu_nian_zhi == day_zhi:
            score += 0.5
            reasons.append('流年伏吟日支')

    # Check career events: promotion should have 官杀 or 印星
    desc = event.get('description', '')
    if category == 'career':
        promotion_keywords = ['当选', '任', '晋升', '总理', '总统', '主席', '继位', '加冕', '当选']
        if any(kw in desc for kw in promotion_keywords):
            if dayun_shishen_gan in ('正官', '七杀', '正印', '偏印'):
                score += 0.5
                reasons.append('晋升事件+官印大运')

    # Clamp score
    score = max(-1.0, min(3.0, score))
    return score, reasons

# =============================================================================
# 6. RUN ANALYSIS FOR ONE CASE
# =============================================================================

def analyze_case(case):
    """Run full analysis for one case."""
    try:
        year, month, day, hour, minute, gender, tz_offset = parse_birth(case)
    except Exception as e:
        return {'error': f'Failed to parse birth: {e}', 'name': case.get('name', '?')}

    # Run calculator
    try:
        four_pillars = bc.calculate_four_pillars(year, month, day, hour, minute)
        day_master = four_pillars['day_master']
        year_pillar = (four_pillars['year']['gan'], four_pillars['year']['zhi'])
        month_pillar = (four_pillars['month']['gan'], four_pillars['month']['zhi'])
        dayun_result = bc.calculate_dayun(year_pillar, month_pillar, gender, year, month, day,
                                          hour, minute)
        dayun_pillars = dayun_result['pillars']
        dayun_dir = dayun_result['direction']
        dayun_start = dayun_result['starting_age']
    except Exception as e:
        return {'error': f'Calculator error: {e}', 'name': case.get('name', '?')}

    events = case.get('events', [])
    event_scores = []
    category_scores = defaultdict(list)

    for evt in events:
        evt_year = evt.get('year')
        if evt_year is None:
            continue  # skip events without year
        dayun = find_dayun_for_year(dayun_pillars, evt_year, year, dayun_start)
        liu_nian_gan, liu_nian_zhi = get_year_liunian(evt_year)
        score, reasons = score_event(evt, dayun, liu_nian_gan, liu_nian_zhi, day_master, four_pillars)
        event_scores.append({
            'year': evt_year,
            'category': evt['category'],
            'description': evt.get('description', '')[:80],
            'score': round(score, 2),
            'reasons': reasons,
            'dayun': f"{dayun['gan']}{dayun['zhi']}" if dayun else '童运',
            'liunian': f"{liu_nian_gan}{liu_nian_zhi}",
        })
        category_scores[evt['category']].append(score)

    # Aggregate
    all_scores = [e['score'] for e in event_scores]
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    positive_rate = sum(1 for s in all_scores if s >= 1.0) / len(all_scores) if all_scores else 0
    negative_rate = sum(1 for s in all_scores if s < 0.3) / len(all_scores) if all_scores else 0

    cat_stats = {}
    for cat, scores in category_scores.items():
        cat_stats[cat] = {
            'count': len(scores),
            'avg': round(sum(scores) / len(scores), 2),
            'positive': sum(1 for s in scores if s >= 1.0),
            'negative': sum(1 for s in scores if s < 0.3),
        }

    return {
        'name': case['name'],
        'id': case['id'],
        'birth': f"{year}-{month:02d}-{day:02d}",
        'gender': gender,
        'bazi': f"{four_pillars['year']['gan']}{four_pillars['year']['zhi']} {four_pillars['month']['gan']}{four_pillars['month']['zhi']} {four_pillars['day']['gan']}{four_pillars['day']['zhi']} {four_pillars['hour']['gan']}{four_pillars['hour']['zhi']}",
        'day_master': f"{day_master}({bc.GAN_WUXING[day_master]}{bc.GAN_YINYANG[day_master]})",
        'dayun_direction': dayun_dir,
        'dayun_start': dayun_start,
        'dayun_list': [f"{d['gan']}{d['zhi']}({d['start_age']}-{d['end_age']})" for d in dayun_pillars],
        'event_count': len(events),
        'avg_score': round(avg_score, 2),
        'positive_rate': f"{positive_rate:.0%}",
        'negative_rate': f"{negative_rate:.0%}",
        'category_stats': cat_stats,
        'event_details': event_scores,
    }

# =============================================================================
# 7. RUN BATCH ANALYSIS
# =============================================================================

print("=" * 80)
print("BaZi Model Quality Test - 八字模型质量检验")
print("=" * 80)
print()

results = []

# Test: known-hour cases + top event cases (even if hour unknown, use noon as default)
selected_cases = list(test_cases)  # all known-hour cases
# Add top 5 cases by event count if not already included
existing_ids = {c['id'] for c in selected_cases}
for c in all_cases_by_events[:5]:
    if c['id'] not in existing_ids:
        selected_cases.append(c)
        existing_ids.add(c['id'])
print(f"Selected cases for testing: {len(selected_cases)}\n")

for case in selected_cases:
    print(f"Analyzing: {case['name']} ({case['birth']['datetime']})...")
    r = analyze_case(case)
    results.append(r)
    if 'error' in r:
        print(f"  ERROR: {r['error']}")
    else:
        print(f"  Bazi: {r['bazi']}, Day Master: {r['day_master']}")
        print(f"  Events: {r['event_count']}, Avg Score: {r['avg_score']}, Positive: {r['positive_rate']}")
    print()

# =============================================================================
# 8. OVERALL STATISTICS
# =============================================================================

valid_results = [r for r in results if 'error' not in r]

print("=" * 80)
print("OVERALL QUALITY REPORT / 模型质量总报告")
print("=" * 80)

all_event_scores = []
for r in valid_results:
    for e in r['event_details']:
        all_event_scores.append(e['score'])

print(f"\n测试命例数: {len(valid_results)}")
print(f"总事件数: {len(all_event_scores)}")
print(f"平均事件得分: {sum(all_event_scores)/len(all_event_scores):.2f}")
print(f"正向匹配率 (score>=1.0): {sum(1 for s in all_event_scores if s>=1.0)/len(all_event_scores):.1%}")
print(f"无关联率 (score<0.3): {sum(1 for s in all_event_scores if s<0.3)/len(all_event_scores):.1%}")

# Per category
print("\n按事件类别:")
cat_all = defaultdict(list)
for r in valid_results:
    for e in r['event_details']:
        cat_all[e['category']].append(e['score'])

for cat, scores in sorted(cat_all.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True):
    avg = sum(scores) / len(scores)
    pos = sum(1 for s in scores if s >= 1.0) / len(scores)
    print(f"  {cat}: avg={avg:.2f}, positive={pos:.1%}, n={len(scores)}")

# Per case
print("\n按命例:")
for r in sorted(valid_results, key=lambda x: x['avg_score'], reverse=True):
    print(f"  {r['name']}: avg={r['avg_score']}, pos={r['positive_rate']}, n={r['event_count']}")

# Save full report
report = {
    'test_date': str(date.today()),
    'test_cases': len(valid_results),
    'total_events': len(all_event_scores),
    'overall_avg_score': round(sum(all_event_scores)/len(all_event_scores), 2) if all_event_scores else 0,
    'overall_positive_rate': round(sum(1 for s in all_event_scores if s>=1.0)/len(all_event_scores), 3) if all_event_scores else 0,
    'category_stats': {cat: {'avg': round(sum(scores)/len(scores),2), 'count': len(scores)}
                       for cat, scores in cat_all.items()},
    'case_results': [{
        'name': r['name'],
        'id': r['id'],
        'bazi': r['bazi'],
        'day_master': r['day_master'],
        'avg_score': r['avg_score'],
        'positive_rate': r['positive_rate'],
        'category_stats': r['category_stats'],
        'dayun_list': r['dayun_list'],
    } for r in valid_results],
    'event_details': [],
}

# Include event details for top and bottom cases
for r in valid_results:
    for e in r['event_details']:
        if e['score'] >= 2.0 or e['score'] < 0.2:
            report['event_details'].append({
                'case': r['name'],
                'year': e['year'],
                'category': e['category'],
                'score': e['score'],
                'description': e['description'],
                'dayun': e['dayun'],
                'liunian': e['liunian'],
                'reasons': e['reasons'],
            })

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model_quality_report.json')
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"\n详细报告已保存至: {OUT_PATH}")
