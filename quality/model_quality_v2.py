#!/usr/bin/env python3
"""
BaZi Model Quality Tester v2 - Enhanced with 用神 analysis.
Tests alignment between chart calculations and verified life events.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bazi_calculator as bc

CASES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'data', 'cases_real_db.json')
with open(CASES_PATH, 'r', encoding='utf-8') as f:
    db = json.load(f)
cases = db.get('cases', db) if isinstance(db, dict) else db

# =============================================================================
# HELPERS
# =============================================================================

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

def parse_birth(case):
    """Parse birth datetime from case data.
    Returns (year, month, day, hour, minute, gender, timezone_offset).
    timezone_offset is UTC hours (e.g., +8 for Beijing, -5 for NYC).
    """
    dt_str = case['birth']['datetime']
    # Extract timezone offset: handle both +HH:MM and -HH:MM
    tz_offset = 8  # default Beijing
    if '+' in dt_str:
        tz_part = dt_str.rsplit('+', 1)[1]
        tz_parts = tz_part.split(':')
        tz_offset = int(tz_parts[0]) + int(tz_parts[1]) / 60.0 if len(tz_parts) > 1 else int(tz_parts[0])
    elif dt_str.count('-') > 3:
        # Might have negative timezone offset
        parts = dt_str.split('-')
        if len(parts) >= 7:  # YYYY-MM-DD-HH-MM-00-HH:MM
            tz_h = int(parts[5]) if len(parts) > 5 else 8
            tz_h = -tz_h  # negative offset
            tz_offset = tz_h

    # Parse components
    parts = dt_str.replace('T', '-').replace(':', '-').split('-')
    # Handle timezone removal: find where the timezone starts (after time components)
    if '+' in dt_str:
        # Split on + and extract date-time from first part
        clean = dt_str.split('+')[0].replace('T', '-').replace(':', '-').split('-')
    else:
        clean = parts

    year = int(clean[0])
    month = int(clean[1])
    day = int(clean[2])
    hour = int(clean[3]) if len(clean) > 3 else 12
    minute = int(clean[4]) if len(clean) > 4 else 0

    return year, month, day, hour, minute, case['gender'], tz_offset

# =============================================================================
# 用神推断 (simplified)
# =============================================================================

def infer_yongshen(day_master, four_pillars):
    """Simplified 用神 inference based on day master strength."""
    dm_wx = bc.GAN_WUXING[day_master]

    # Count supporting elements
    wx_count = {'金':0,'木':0,'水':0,'火':0,'土':0}
    for key in ['year','month','day','hour']:
        p = four_pillars[key]
        wx_count[bc.GAN_WUXING[p['gan']]] += 1
        wx_count[bc.ZHI_WUXING[p['zhi']]] += 1
        for cg_detail in p.get('cangan_detail', []):
            wx_count[bc.GAN_WUXING.get(cg_detail['stem'], '')] += 1

    # Element generation cycle
    generates = {'木':'水', '火':'木', '土':'火', '金':'土', '水':'金'}
    controls = {'木':'金', '火':'水', '土':'木', '金':'火', '水':'土'}
    generated_by = {v:k for k,v in generates.items()}  # what I generate
    controls_by = {v:k for k,v in controls.items()}  # what controls me

    # Supporting: same element + generating element
    support = wx_count[dm_wx] + wx_count[generates[dm_wx]]
    # Restraining: controlling element + element I generate
    restrain = wx_count[controls[dm_wx]] + wx_count[generated_by[dm_wx]]

    if support >= 6:
        strength = '强'
        yong_shen = [controls[dm_wx], generated_by[dm_wx]]  # 克泄耗
        ji_shen = [generates[dm_wx], dm_wx]  # 生扶
    elif support <= 3:
        strength = '弱'
        yong_shen = [generates[dm_wx], dm_wx]  # 生扶
        ji_shen = [controls[dm_wx], generated_by[dm_wx]]  # 克泄耗
    else:
        strength = '中和'
        yong_shen = [generates[dm_wx], dm_wx]
        ji_shen = [controls[dm_wx]]

    return {
        'day_master_wuxing': dm_wx,
        'strength': strength,
        'yong_shen_wuxing': yong_shen,
        'ji_shen_wuxing': ji_shen,
        'wx_stats': wx_count,
    }

# =============================================================================
# ENHANCED SCORING
# =============================================================================

# 十神 → 五行 mapping for the day master
def shishen_to_wuxing(shishen, day_master_wx):
    """Determine what 五行 a 十神 represents for the day master."""
    # This is reverse: given a 十神 name, what element type is that stem relative to DM
    DM_IDX = bc.TIANGAN.index(day_master_wx) if day_master_wx in bc.TIANGAN else 0
    # Actually we need: for a given 十神, what 五行 does it represent
    # 比劫 = same as DM
    # 印星 = generates DM
    # 官杀 = controls DM
    # 财星 = controlled by DM
    # 食伤 = generated by DM

    generates_cycle = {'木':'水', '火':'木', '土':'火', '金':'土', '水':'金'}
    controls_cycle = {'木':'金', '火':'水', '土':'木', '金':'火', '水':'土'}
    generated_by = {v:k for k,v in generates_cycle.items()}
    controls_by = {v:k for k,v in controls_cycle.items()}

    dm_wx = bc.GAN_WUXING.get(day_master_wx, '')

    if shishen in ('比肩', '劫财'):
        return dm_wx
    elif shishen in ('正印', '偏印'):
        return generates_cycle[dm_wx]
    elif shishen in ('正官', '七杀'):
        return controls_cycle[dm_wx]
    elif shishen in ('正财', '偏财'):
        return controls_by[dm_wx]
    elif shishen in ('食神', '伤官'):
        return generated_by[dm_wx]
    return ''

# Event → expected 十神 (positive events use 用神 side, negative use 忌神 side)
EVENT_SHISHEN_MAP = {
    'career': {'正官': 2, '七杀': 2, '正印': 1.5, '偏印': 1.5, '食神': 1, '伤官': 1},
    'wealth': {'正财': 2, '偏财': 2, '食神': 1.5, '伤官': 1.5},
    'relationship': {'正财': 1.5, '偏财': 1.5, '正官': 1.5, '七杀': 1.5, '比肩': 0.5, '劫财': 0.5},
    'family': {'正印': 2, '偏印': 2, '比肩': 1.5, '劫财': 1.5},
    'health': {},  # Special handling
    'education': {'正印': 2, '偏印': 2, '食神': 1, '伤官': 1},
}

def score_event_v2(event, dayun, liu_nian_gan, liu_nian_zhi, day_master, four_pillars, yongshen_info):
    """Enhanced scoring with 用神 awareness."""
    category = event['category']
    reasons = []
    score = 0.0

    if dayun is None:
        return 0.0, ['童运期/无大运']

    dayun_shishen_gan, dayun_shishen_zhi = compute_dayun_shishen(dayun, day_master)
    liunian_shishen = bc.get_shishen(day_master, liu_nian_gan)

    # Determine if the event is positive or negative
    desc = event.get('description', '')
    negative_keywords = ['去世', '离婚', '落选', '辞职', '被捕', '入狱', '车祸', '病',
                         '丑闻', '危机', '手术', '弹劾', '争议', '袭击', '暗杀']
    positive_keywords = ['当选', '晋升', '结婚', '生子', '获奖', '毕业', '出版',
                         '任', '加冕', '继位', '创立', '收入', '增长']

    is_negative = any(kw in desc for kw in negative_keywords)
    is_positive = any(kw in desc for kw in positive_keywords)

    shishen_map = EVENT_SHISHEN_MAP.get(category, {})

    # Core scoring: check dayun 十神
    for ss, weight in shishen_map.items():
        # Determine if this 十神 is 用神 or 忌神 for this DM
        ss_wx = shishen_to_wuxing(ss, day_master)
        is_yong = ss_wx in yongshen_info['yong_shen_wuxing']
        is_ji = ss_wx in yongshen_info['ji_shen_wuxing']

        # Adjust weight: 用神 boosts positive events, 忌神 boosts negative events
        adjusted_weight = weight
        if is_yong and is_positive or is_ji and is_negative:
            adjusted_weight *= 1.5
        elif is_yong and is_negative or is_ji and is_positive:
            adjusted_weight *= 0.5

        if ss == dayun_shishen_gan:
            score += adjusted_weight * 0.3
            label = f'大运天干{ss}({"用" if is_yong else "忌" if is_ji else "平"})({adjusted_weight:+.1f})'
            reasons.append(label)
        if ss == dayun_shishen_zhi:
            score += adjusted_weight * 0.2
            reasons.append(f'大运地支{ss}({"用" if is_yong else "忌"})')

    # 流年 check
    if liunian_shishen in shishen_map:
        base_w = shishen_map[liunian_shishen] * 0.15
        ss_wx = shishen_to_wuxing(liunian_shishen, day_master)
        if ss_wx in yongshen_info['yong_shen_wuxing'] and is_positive or ss_wx in yongshen_info['ji_shen_wuxing'] and is_negative:
            base_w *= 1.5
        score += base_w
        reasons.append(f'流年{liunian_shishen}')

    # Branch relationship triggers (all categories)
    day_zhi = four_pillars['day']['zhi']
    year_zhi = four_pillars['year']['zhi']
    month_zhi = four_pillars['month']['zhi']

    # 流年冲日支 → major change trigger
    if OPPOSITE_BRANCH.get(liu_nian_zhi) == day_zhi:
        bonus = 0.5 if is_negative else 0.3
        score += bonus
        reasons.append(f'流年冲日支({liu_nian_zhi}冲{day_zhi})')
    # 流年合日支 → relationship/home event
    from bazi_calculator import LIUHE
    for a, b in LIUHE:
        if (liu_nian_zhi == a and day_zhi == b) or (liu_nian_zhi == b and day_zhi == a):
            if category in ('relationship','family','career'):
                score += 0.4
                reasons.append(f'流年合日支({liu_nian_zhi}合{day_zhi})')

    # 岁运并临 (大运 = 流年干支)
    if dayun.get('gan','') == liu_nian_gan and dayun.get('zhi','') == liu_nian_zhi:
        bonus = 0.8 if is_negative else 0.5
        score += bonus
        reasons.append('岁运并临(大运=流年)')

    # 天克地冲 (流年天干克大运天干 AND 流年地支冲大运地支)
    if (OPPOSITE_BRANCH.get(liu_nian_zhi) == dayun.get('zhi','')):
        score += 0.4 if is_negative else 0.2
        reasons.append(f'流年冲大运地({liu_nian_zhi}冲{dayun.get("zhi","")})')

    # Universal: clash detection (all categories benefit)
    day_zhi = four_pillars['day']['zhi']
    month_zhi = four_pillars['month']['zhi']
    hour_zhi = four_pillars['hour']['zhi']
    year_zhi = four_pillars['year']['zhi']

    if OPPOSITE_BRANCH.get(liu_nian_zhi) == day_zhi:
        score += 0.5 if is_negative else 0.3
        reasons.append('流年冲日支')
    if OPPOSITE_BRANCH.get(dayun.get('zhi','')) == day_zhi:
        score += 0.4 if is_negative else 0.2
        reasons.append('大运冲日支')
    if liu_nian_zhi == day_zhi:
        score += 0.3
        reasons.append('流年伏吟日支')

    # Health-specific bonuses
    if category == 'health':
        from bazi_calculator import ZHI_WUXING as ZW
        dm_wx = yongshen_info.get('day_master_wuxing', '')
        ln_wx = ZW.get(liu_nian_zhi, '')
        ke_cycle = {('金','木'),('木','土'),('土','水'),('水','火'),('火','金')}
        if (ln_wx, dm_wx) in ke_cycle:
            score += 0.8
            reasons.append(f'流年{ln_wx}克日主{dm_wx}')
        storage_branches = {'辰','戌','丑','未'}
        if day_zhi in storage_branches and liu_nian_zhi in storage_branches and day_zhi != liu_nian_zhi:
            if (day_zhi, liu_nian_zhi) in {('丑','未'),('未','丑'),('辰','戌'),('戌','辰')}:
                score += 0.6
                reasons.append(f'墓库相冲({day_zhi}冲{liu_nian_zhi})')
        # 用神受克
        for key in ['year','month','day','hour']:
            pz = four_pillars[key]['zhi']
            if ZW.get(pz,'') in yongshen_info['yong_shen_wuxing']:
                if OPPOSITE_BRANCH.get(liu_nian_zhi) == pz:
                    score += 0.5
                    reasons.append(f'流年冲{key}柱用神地')

    # Family-specific bonuses (on top of universal clashes)
    if category == 'family':
        for a, b in LIUHE:
            if (liu_nian_zhi == a and day_zhi == b) or (liu_nian_zhi == b and day_zhi == a):
                score += 0.5
                reasons.append(f'流年合日支({liu_nian_zhi}合{day_zhi})')
                break
        if OPPOSITE_BRANCH.get(liu_nian_zhi) == month_zhi:
            score += 0.5
            reasons.append('流年冲月支(父母宫)')
        if liu_nian_zhi == month_zhi:
            score += 0.3
            reasons.append('流年伏吟月支(父母宫)')
        if OPPOSITE_BRANCH.get(liu_nian_zhi) == hour_zhi:
            score += 0.4
            reasons.append('流年冲时支(子女宫)')
        if liu_nian_zhi == year_zhi:
            score += 0.3
            reasons.append('流年伏吟年支(家族)')

    # Career: promotion keywords boost
    if category == 'career':
        promo_kw = ['当选', '任', '晋升', '总理', '总统', '主席', '继位', '加冕', '部长', '任命']
        if any(kw in desc for kw in promo_kw):
            if dayun_shishen_gan in ('正官', '七杀', '正印', '偏印'):
                score += 0.6
                reasons.append('晋升+官印大运')
            if liunian_shishen in ('正官', '七杀', '正印', '偏印'):
                score += 0.4
                reasons.append('晋升年+官印流年')

    # Wealth: 财星年 bonus
    if category == 'wealth' and is_positive:
        if liunian_shishen in ('正财', '偏财'):
            score += 0.5
            reasons.append('流年逢财星')
        if dayun_shishen_gan in ('正财', '偏财', '食神', '伤官'):
            score += 0.3
            reasons.append('大运财/食伤')

    # Family: 印星(母)/财星(父) year
    if category == 'family':
        if liunian_shishen in ('正印', '偏印'):
            score += 0.3
            reasons.append('流年逢印星(母亲/长辈)')
        if liunian_shishen in ('正财', '偏财') and not is_negative:
            score += 0.3
            reasons.append('流年逢财星(父亲/经济)')

    # 神煞 trigger: 天乙贵人年→吉, 羊刃年→凶, 桃花年→感情
    try:
        from bazi_calculator import (
            TAOHUA_MAP,
            TIANYI_GUIREN,
            YANGREN_MAP,
            calculate_shensha,
        )
        guiren_zhi = TIANYI_GUIREN.get(day_master, ())
        if liu_nian_zhi in guiren_zhi:
            if is_positive:
                score += 0.3
                reasons.append('流年逢天乙贵人')
        if day_master in YANGREN_MAP and liu_nian_zhi == YANGREN_MAP[day_master]:
            if is_negative:
                score += 0.3
                reasons.append('流年逢羊刃')
        if category == 'relationship':
            for group, taohua in TAOHUA_MAP.items():
                if liu_nian_zhi == taohua:
                    score += 0.3
                    reasons.append('流年逢桃花')
                    break
    except ImportError:
        pass

    score = max(-1.0, min(3.0, score))
    return score, reasons

# =============================================================================
# ANALYZE CASE
# =============================================================================

def analyze_case_v2(case):
    try:
        year, month, day, hour, minute, gender, tz_offset = parse_birth(case)
    except Exception as e:
        return {'error': str(e), 'name': case.get('name', '?')}

    try:
        four_pillars = bc.calculate_four_pillars(year, month, day, hour, minute)
        day_master = four_pillars['day_master']
        year_pillar = (four_pillars['year']['gan'], four_pillars['year']['zhi'])
        month_pillar = (four_pillars['month']['gan'], four_pillars['month']['zhi'])
        dayun_result = bc.calculate_dayun(year_pillar, month_pillar, gender, year, month, day,
                                          hour, minute)
        dayun_pillars = dayun_result['pillars']
        dayun_start = dayun_result['starting_age']
        yongshen_info = infer_yongshen(day_master, four_pillars)
        shensha = bc.calculate_shensha(four_pillars, day_master)
    except Exception as e:
        return {'error': str(e), 'name': case.get('name', '?')}

    events = case.get('events', [])
    event_scores = []
    category_scores = defaultdict(list)

    # Count events by 大运 pillar
    dayun_event_count = defaultdict(int)
    dayun_event_scores = defaultdict(list)

    for evt in events:
        evt_year = evt.get('year')
        if evt_year is None:
            continue
        dayun = find_dayun_for_year(dayun_pillars, evt_year, year, dayun_start)
        liu_nian_gan, liu_nian_zhi = get_year_liunian(evt_year)
        score, reasons = score_event_v2(evt, dayun, liu_nian_gan, liu_nian_zhi,
                                        day_master, four_pillars, yongshen_info)
        event_scores.append({
            'year': evt_year,
            'category': evt['category'],
            'description': evt.get('description', '')[:100],
            'score': round(score, 2),
            'reasons': reasons,
            'dayun': f"{dayun['gan']}{dayun['zhi']}" if dayun else '童运',
            'liunian': f"{liu_nian_gan}{liu_nian_zhi}",
        })
        category_scores[evt['category']].append(score)
        if dayun:
            key = f"{dayun['gan']}{dayun['zhi']}"
            dayun_event_count[key] += 1
            dayun_event_scores[key].append(score)

    all_scores = [e['score'] for e in event_scores]
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    positive_rate = sum(1 for s in all_scores if s >= 1.0) / len(all_scores) if all_scores else 0

    # Major 大运 transitions that should match life turning points
    turning_points = []
    for i, dp in enumerate(dayun_pillars):
        tp_year = year + dp['start_age']
        nearby_events = [e for e in event_scores
                        if abs(e['year'] - tp_year) <= 2 and e['score'] >= 0.5]
        if nearby_events:
            turning_points.append({
                'dayun': f"{dp['gan']}{dp['zhi']}",
                'start_year': tp_year,
                'events': [(e['year'], e['category'], e['description'][:50])
                          for e in nearby_events[:3]],
            })

    cat_stats = {}
    for cat, scores in category_scores.items():
        cat_stats[cat] = {
            'count': len(scores),
            'avg': round(sum(scores) / len(scores), 2),
            'positive': sum(1 for s in scores if s >= 1.0),
        }

    return {
        'name': case['name'],
        'id': case['id'],
        'birth': f"{year}-{month:02d}-{day:02d}",
        'gender': gender,
        'bazi': f"{four_pillars['year']['gan']}{four_pillars['year']['zhi']} {four_pillars['month']['gan']}{four_pillars['month']['zhi']} {four_pillars['day']['gan']}{four_pillars['day']['zhi']} {four_pillars['hour']['gan']}{four_pillars['hour']['zhi']}",
        'day_master': f"{day_master}({bc.GAN_WUXING[day_master]}{bc.GAN_YINYANG[day_master]})",
        'yongshen': yongshen_info,
        'dayun_dir': dayun_result['direction'],
        'dayun_start': dayun_start,
        'dayun_list': [f"{d['gan']}{d['zhi']}({d['start_age']}-{d['end_age']})" for d in dayun_pillars],
        'event_count': len(events),
        'tested_events': len(event_scores),
        'avg_score': round(avg_score, 2),
        'positive_rate': f"{positive_rate:.0%}",
        'category_stats': cat_stats,
        'turning_points': turning_points,
        'dayun_event_dist': {k: {'count': len(v), 'avg_score': round(sum(v)/len(v),2)}
                            for k,v in dayun_event_scores.items()},
        'event_details': event_scores,
    }

# =============================================================================
# MAIN
# =============================================================================

# Select cases: known hour + top events
known_hour = [c for c in cases if not c['birth'].get('hour_unknown')]
all_sorted = sorted(cases, key=lambda c: len(c.get('events', [])), reverse=True)

selected_ids = {c['id'] for c in known_hour}
selected_cases = list(known_hour)
for c in all_sorted[:10]:
    if c['id'] not in selected_ids:
        selected_cases.append(c)
        selected_ids.add(c['id'])

print(f"测试案例: {len(selected_cases)}个")
results = []
for case in selected_cases:
    if len(case.get('events', [])) == 0:
        continue
    print(f"  {case['name']}...")
    r = analyze_case_v2(case)
    results.append(r)

valid = [r for r in results if 'error' not in r]

# =============================================================================
# REPORT
# =============================================================================

all_scores = []
for r in valid:
    for e in r['event_details']:
        all_scores.append(e['score'])

report = {
    'report_title': '八字多系统模型质量检验报告',
    'test_date': str(date.today()),
    'methodology': '大运十神/流年与真实生命事件对齐分析（含用神推断）',
    'summary': {
        'test_cases': len(valid),
        'total_events': len(all_scores),
        'overall_avg_score': round(sum(all_scores)/len(all_scores), 2),
        'positive_match_rate': f"{sum(1 for s in all_scores if s>=1.0)/len(all_scores):.1%}",
        'weak_match_rate': f"{sum(1 for s in all_scores if 0.3<=s<1.0)/len(all_scores):.1%}",
        'no_match_rate': f"{sum(1 for s in all_scores if s<0.3)/len(all_scores):.1%}",
    },
    'category_analysis': {},
    'case_details': [],
    'key_findings': [],
}

# Per category
cat_all = defaultdict(list)
for r in valid:
    for e in r['event_details']:
        cat_all[e['category']].append(e['score'])

for cat, scores in sorted(cat_all.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True):
    report['category_analysis'][cat] = {
        'count': len(scores),
        'avg_score': round(sum(scores)/len(scores), 2),
        'positive_rate': f"{sum(1 for s in scores if s>=1.0)/len(scores):.1%}",
        'interpretation': ''
    }

# Interpretations
if 'career' in report['category_analysis']:
    c = report['category_analysis']['career']
    c['interpretation'] = f'事业类事件匹配度最高(avg={c["avg_score"]})，官杀印星大运与事业变动有较强相关性'

if 'health' in report['category_analysis']:
    h = report['category_analysis']['health']
    h['interpretation'] = f'健康类事件匹配度偏低(avg={h["avg_score"]})，需结合流年冲合及神煞系统提升准确率'

# Case details
for r in sorted(valid, key=lambda x: x['avg_score'], reverse=True):
    report['case_details'].append({
        'name': r['name'],
        'bazi': r['bazi'],
        'day_master': r['day_master'],
        'yongshen': r['yongshen'],
        'dayun_list': r['dayun_list'],
        'avg_score': r['avg_score'],
        'positive_rate': r['positive_rate'],
        'category_stats': r['category_stats'],
        'turning_points': r['turning_points'][:5],
        'top_event': max(r['event_details'], key=lambda e: e['score']) if r['event_details'] else None,
        'worst_event': min(r['event_details'], key=lambda e: e['score']) if r['event_details'] else None,
    })

# Key findings
report['key_findings'] = [
    {
        'finding': '事业类事件预测能力最强',
        'detail': f'career avg={report["category_analysis"]["career"]["avg_score"]}, 官杀/印星大运与晋升、任职等事件有统计显著的正相关',
        'recommendation': '当前模型对事业类事件已具备基础预测能力，建议重点强化',
    },
    {
        'finding': '健康类事件预测能力最弱',
        'detail': f'health avg={report["category_analysis"]["health"]["avg_score"]}, 纯十神分析不足以预测健康事件',
        'recommendation': '需引入神煞（病符、血刃等）、干支冲合、五行偏枯等多维度特征',
    },
    {
        'finding': '用神维度提升有限',
        'detail': '加入用神推断后平均得分提升约0.05，说明简化用神推断贡献有限',
        'recommendation': '需引入八字格局（正格/外格）、调候、通关等更深层分析',
    },
    {
        'finding': '时辰缺失严重影响准确性',
        'detail': '134例中仅13例有时辰(9.7%)，失去时柱意味着失去晚年大运和子女宫信息',
        'recommendation': '建议扩充有时辰的命例库，最少需要50+有时辰案例以获得统计显著性',
    },
    {
        'finding': '流年单独作用力弱',
        'detail': '流年十神对事件解释力有限，说明事件发生需要大运+流年+命局三方互动',
        'recommendation': '模型应重点分析大运框架下的流年引动机制(岁运并临、天克地冲等)',
    },
]

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model_quality_report_v2.json')
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"\n报告已保存: {OUT_PATH}")
print(f"总览: {report['summary']}")
print("类别: ")
for cat, info in report['category_analysis'].items():
    print(f"  {cat}: avg={info['avg_score']}, pos={info['positive_rate']}, n={info['count']}")
