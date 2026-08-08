#!/usr/bin/env python3
"""
Hour Inference Engine (时辰推断引擎)

For BaZi cases with unknown birth hour, enumerate all 12 Dizhi hours,
score each candidate against known life events, and output the best-guess
hour with confidence level.

Pure Python stdlib, no external dependencies.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bazi_calculator as bc

# Map Dizhi to representative clock hour for calculation
DIZHI_TO_HOUR = {
    '子': 23, '丑': 1,  '寅': 3,  '卯': 5,
    '辰': 7,  '巳': 9,  '午': 11, '未': 13,
    '申': 15, '酉': 17, '戌': 19, '亥': 21,
}


def parse_birth(case):
    """Parse birth datetime, returns (year, month, day, hour, minute, gender, tz_offset)."""
    dt_str = case['birth']['datetime']
    tz_offset = 8
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
    return year, month, day, hour, minute, case['gender'], tz_offset


def calc_candidate_chart(year, month, day, hour_clock, minute, gender):
    """Calculate full chart for a candidate hour."""
    four_pillars = bc.calculate_four_pillars(year, month, day, hour_clock, minute)
    day_master = four_pillars['day_master']
    year_pillar = (four_pillars['year']['gan'], four_pillars['year']['zhi'])
    month_pillar = (four_pillars['month']['gan'], four_pillars['month']['zhi'])
    dayun_result = bc.calculate_dayun(year_pillar, month_pillar, gender, year, month, day,
                                      hour_clock, minute)
    ziwei = bc.calculate_ziwei(year, month, day, hour_clock, gender)

    return {
        'four_pillars': four_pillars,
        'day_master': day_master,
        'dayun_result': dayun_result,
        'ziwei': ziwei,
        'hour_pillar': f"{four_pillars['hour']['gan']}{four_pillars['hour']['zhi']}",
    }


# =============================================================================
# Simplified scoring for hour inference
# =============================================================================

# Event category → expected 十神
EVENT_SHISHEN_MAP = {
    'career': {'正官': 2, '七杀': 2, '正印': 1.5, '偏印': 1.5, '食神': 1, '伤官': 1},
    'wealth': {'正财': 2, '偏财': 2, '食神': 1.5, '伤官': 1.5},
    'relationship': {'正财': 1.5, '偏财': 1.5, '正官': 1.5, '七杀': 1.5, '比肩': 0.5, '劫财': 0.5},
    'family': {'正印': 2, '偏印': 2, '比肩': 1.5, '劫财': 1.5},
    'health': {},
    'education': {'正印': 2, '偏印': 2, '食神': 1, '伤官': 1},
}

OPPOSITE_BRANCH = {
    '子': '午', '午': '子', '丑': '未', '未': '丑',
    '寅': '申', '申': '寅', '卯': '酉', '酉': '卯',
    '辰': '戌', '戌': '辰', '巳': '亥', '亥': '巳',
}


def get_year_liunian(year):
    base_year = 1984
    offset = (year - base_year) % 60
    return bc.TIANGAN[offset % 10], bc.DIZHI[offset % 12]


def find_dayun_for_year(pillars, event_year, birth_year, starting_age):
    age = event_year - birth_year
    if age < 0 or age < starting_age:
        return None
    for d in pillars:
        if d['start_age'] <= age <= d['end_age']:
            return d
    return None


def compute_dayun_shishen(dayun, day_master):
    gan_ss = bc.get_shishen(day_master, dayun['gan'])
    zhi_main = bc.CANGAN.get(dayun['zhi'], [('',)])[0][0]
    zhi_ss = bc.get_shishen(day_master, zhi_main) if zhi_main else ''
    return gan_ss, zhi_ss


def score_event_for_inference(event, dayun, liu_nian_gan, liu_nian_zhi, day_master, four_pillars):
    """Score a single event — simplified version for hour inference."""
    category = event['category']
    reasons = []
    score = 0.0

    if dayun is None:
        return 0.0, []

    dayun_shishen_gan, dayun_shishen_zhi = compute_dayun_shishen(dayun, day_master)
    liunian_shishen = bc.get_shishen(day_master, liu_nian_gan)

    # Hour pillar shishen (for differentiation across candidates)
    hour_pillar = four_pillars.get('hour', {})
    hour_shishen_gan = bc.get_shishen(day_master, hour_pillar.get('gan', ''))
    hour_zhi_main = bc.CANGAN.get(hour_pillar.get('zhi', ''), [('',)])[0][0]
    hour_shishen_zhi = bc.get_shishen(day_master, hour_zhi_main) if hour_zhi_main else ''

    liunian_shishen = bc.get_shishen(day_master, liu_nian_gan)
    shishen_map = EVENT_SHISHEN_MAP.get(category, {})

    for ss, weight in shishen_map.items():
        if ss == dayun_shishen_gan:
            score += weight * 0.3
            reasons.append(f'大运天干{ss}')
        if ss == dayun_shishen_zhi:
            score += weight * 0.2
            reasons.append(f'大运地支{ss}')
        # Hour pillar shishen contribution (differentiator across hour candidates)
        if ss == hour_shishen_gan:
            score += weight * 0.1
            reasons.append(f'时干{ss}')
        if ss == hour_shishen_zhi:
            score += weight * 0.08
            reasons.append(f'时支{ss}')

    if liunian_shishen in shishen_map:
        score += shishen_map[liunian_shishen] * 0.15
        reasons.append(f'流年{liunian_shishen}')

    # Hour pillar clash with 流年 (differentiates hour candidates)
    hour_zhi = hour_pillar.get('zhi', '')
    if liu_nian_zhi and OPPOSITE_BRANCH.get(liu_nian_zhi) == hour_zhi:
        score += 0.3
        reasons.append('流年冲时支')

    # Health: clash detection
    if category == 'health':
        day_zhi = four_pillars['day']['zhi']
        if OPPOSITE_BRANCH.get(liu_nian_zhi) == day_zhi:
            score += 1.0
            reasons.append('流年冲日支')
        if dayun and OPPOSITE_BRANCH.get(dayun['zhi']) == day_zhi:
            score += 0.8
            reasons.append('大运冲日支')
        if liu_nian_zhi == day_zhi:
            score += 0.5
            reasons.append('流年伏吟日支')

    score = max(-1.0, min(3.0, score))
    return score, reasons


def score_candidate(candidate, events, birth_year):
    """Score a candidate hour chart against all known events."""
    fp = candidate['four_pillars']
    dm = candidate['day_master']
    dayun_pillars = candidate['dayun_result']['pillars']
    dayun_start = candidate['dayun_result']['starting_age']

    total = 0.0
    n = 0
    event_scores = []

    for evt in events:
        evt_year = evt.get('year')
        if evt_year is None:
            continue
        dayun = find_dayun_for_year(dayun_pillars, evt_year, birth_year, dayun_start)
        liu_nian_gan, liu_nian_zhi = get_year_liunian(evt_year)
        s, reasons = score_event_for_inference(evt, dayun, liu_nian_gan, liu_nian_zhi, dm, fp)
        total += s
        n += 1
        event_scores.append({'year': evt_year, 'score': round(s, 2), 'reasons': reasons[:3]})

    return {
        'total_score': round(total, 4),
        'avg_score': round(total / n, 3) if n else 0,
        'positive_rate': sum(1 for e in event_scores if e['score'] >= 1.0) / n if n else 0,
        'n_events': n,
        'event_scores': event_scores,
    }


def infer_hour(case):
    """Infer the most likely birth hour for a case."""
    try:
        year, month, day, hour, minute, gender, tz_offset = parse_birth(case)
    except Exception as e:
        return {'error': str(e), 'case_name': case.get('name', '?')}

    events = case.get('events', [])
    if len(events) < 3:
        return {
            'case_id': case.get('id', ''),
            'case_name': case.get('name', ''),
            'error': 'Insufficient events for inference (need >= 3)',
            'confidence': 'low',
        }

    candidates = []
    for zhi in bc.DIZHI:
        hour_clock = DIZHI_TO_HOUR[zhi]
        try:
            cand = calc_candidate_chart(year, month, day, hour_clock, minute, gender)
        except Exception:
            continue
        scoring = score_candidate(cand, events, year)
        candidates.append({
            'zhi': zhi,
            'hour': hour_clock,
            'hour_pillar': cand['hour_pillar'],
            'scoring': scoring,
        })

    candidates.sort(key=lambda c: c['scoring']['avg_score'], reverse=True)

    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None

    margin = best['scoring']['avg_score'] - (second['scoring']['avg_score'] if second else 0)
    ratio = best['scoring']['avg_score'] / (second['scoring']['avg_score'] + 0.001) if second else float('inf')

    if margin > 0.15 and ratio > 1.2:
        confidence = 'high'
    elif margin > 0.05:
        confidence = 'medium'
    else:
        confidence = 'low'

    inferred_parts = [
        case['bazi']['year'],
        case['bazi']['month'],
        case['bazi']['day'],
        best['hour_pillar'],
    ]

    return {
        'case_id': case.get('id', ''),
        'case_name': case.get('name', ''),
        'total_events': len(events),
        'tested_events': best['scoring']['n_events'],
        'candidates': [
            {'rank': i+1, 'zhi': c['zhi'], 'hour': c['hour'],
             'pillar': c['hour_pillar'], 'avg_score': c['scoring']['avg_score'],
             'positive_rate': c['scoring']['positive_rate']}
            for i, c in enumerate(candidates[:5])
        ],
        'best_hour_zhi': best['zhi'],
        'best_hour_clock': best['hour'],
        'best_hour_pillar': best['hour_pillar'],
        'best_avg_score': best['scoring']['avg_score'],
        'best_positive_rate': best['scoring']['positive_rate'],
        'confidence': confidence,
        'score_margin': round(margin, 3),
        'score_ratio': round(ratio, 2),
        'inferred_bazi': ' '.join(inferred_parts),
    }


# =============================================================================
# Batch processing & CLI
# =============================================================================

def process_all_unknown(cases_db_path, max_cases=None, min_confidence=None):
    """Process all cases with unknown hour in the database."""
    with open(cases_db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)

    all_cases = db.get('cases', db) if isinstance(db, dict) else db
    if isinstance(all_cases, dict) and 'cases' in all_cases:
        all_cases = all_cases['cases']

    unknown = [c for c in all_cases if c['birth'].get('hour_unknown') and len(c.get('events', [])) >= 3]

    if max_cases:
        unknown = unknown[:max_cases]

    print(f"Processing {len(unknown)} cases with unknown birth hour...")

    results = []
    for i, case in enumerate(unknown):
        name = case.get('name', '?')
        print(f"  [{i+1}/{len(unknown)}] {name}...", end=' ', flush=True)
        r = infer_hour(case)
        results.append(r)
        if 'error' in r:
            print(f"ERROR: {r['error']}")
        else:
            print(f"best={r['best_hour_zhi']}时({r['best_hour_pillar']}) "
                  f"score={r['best_avg_score']} conf={r['confidence']}")

    return results


def main():
    parser = argparse.ArgumentParser(description='BaZi Hour Inference Engine')
    parser.add_argument('--cases', default='cases_real_db.json',
                        help='Cases JSON file path')
    parser.add_argument('--case-id', help='Infer for a specific case by ID')
    parser.add_argument('--output', '-o', default='inferred_hours.json',
                        help='Output file path (JSON)')
    parser.add_argument('--confidence', default='all',
                        choices=['all', 'high', 'medium', 'low'],
                        help='Minimum confidence to include in output')
    parser.add_argument('--max-cases', type=int, default=0,
                        help='Max cases to process (0=all)')
    args = parser.parse_args()

    if args.case_id:
        # Single case mode
        with open(args.cases, 'r', encoding='utf-8') as f:
            db = json.load(f)
        all_cases = db.get('cases', db)
        case = next((c for c in all_cases if c.get('id') == args.case_id), None)
        if not case:
            print(f"Case {args.case_id} not found")
            sys.exit(1)
        result = infer_hour(case)
        results = [result]
    else:
        max_cases = args.max_cases if args.max_cases > 0 else None
        results = process_all_unknown(args.cases, max_cases, args.confidence)

    # Filter by confidence
    if args.confidence != 'all':
        results = [r for r in results if r.get('confidence') == args.confidence]

    # Save
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Summary
    high = sum(1 for r in results if r.get('confidence') == 'high')
    medium = sum(1 for r in results if r.get('confidence') == 'medium')
    low = sum(1 for r in results if r.get('confidence') == 'low')
    errors = sum(1 for r in results if 'error' in r)

    print(f"\nDone. {len(results)} cases processed.")
    print(f"  High confidence: {high}")
    print(f"  Medium confidence: {medium}")
    print(f"  Low confidence: {low}")
    print(f"  Errors: {errors}")
    print(f"Output: {args.output}")


if __name__ == '__main__':
    main()
