#!/usr/bin/env python3
"""
八字穿壬 — BaZi + Da Liu Ren (大六壬) Cross-Analysis System.
Combines the BaZi day pillar with Liu Ren's 天地盘/四课/三传 for event timing.
"""

import os, sys, json
from datetime import date, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ========== Constants ==========
DIZHI = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
TIANGAN = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']

# 12月将 (Month Generals) — solar term → 月将
YUEJIANG = {
    '大寒': '子', '雨水': '亥', '春分': '戌', '谷雨': '酉',
    '小满': '申', '夏至': '未', '大暑': '午', '处暑': '巳',
    '秋分': '辰', '霜降': '卯', '小雪': '寅', '冬至': '丑',
}

# 12天将 (Heavenly Generals) and their meanings
TIANJIANG = ['贵人','螣蛇','朱雀','六合','勾陈','青龙',
             '天空','白虎','太常','玄武','太阴','天后']

TIANJIANG_MEANING = {
    '贵人': '得贵人助，逢凶化吉',
    '螣蛇': '虚惊怪异，口舌是非',
    '朱雀': '文书口舌，信息传递',
    '六合': '合作婚姻，交易成功',
    '勾陈': '争斗纠缠，官司拖延',
    '青龙': '吉庆喜事，财运亨通',
    '天空': '虚诈不实，计划落空',
    '白虎': '血光伤病，丧服孝事',
    '太常': '宴会饮食，衣食丰足',
    '玄武': '盗贼小人，暗中损失',
    '太阴': '阴私密谋，女性贵人',
    '天后': '婚姻喜庆，女性庇佑',
}

# 12神将 (Spirit Generals) — based on day stem
GUI_REN_MAP = {
    '甲': ('丑','未'), '戊': ('丑','未'), '庚': ('丑','未'),
    '乙': ('子','申'), '己': ('子','申'),
    '丙': ('亥','酉'), '丁': ('亥','酉'),
    '辛': ('午','寅'),
    '壬': ('巳','卯'), '癸': ('巳','卯'),
}

# Liu Ren 课体 interpretations
KETI_JIEXUN = {
    '贼克': '事有阻碍，需努力克服。对方有制我之力，我需等待时机。',
    '比用': '事情平顺，按部就班。与他人合作可成，独立难为。',
    '涉害': '事情复杂，多方牵扯。需仔细分析，不可轻举妄动。',
    '遥克': '远距离的影响，可能是远方之事。被动居多，主动难成。',
    '昴星': '事情不明朗，信息不透明。需要更多线索才能判断。',
    '别责': '事情有转机，另寻他法可成。不要拘泥于一种方式。',
    '八专': '事情集中在一个点上，专一可成。分散精力则会失败。',
    '伏吟': '事情停滞不前，原地踏步。需要等待时机再行动。',
    '返吟': '事情反复多变，来回折腾。适合快速决策后行动。',
}


# ========== Core Functions ==========

def get_yuejiang(month, day):
    """Get 月将 using solar term lookup from bazi_calculator."""
    try:
        from bazi_calculator import get_solar_term_info
        term_info = get_solar_term_info(datetime.now().year, month, day)
        term_name = term_info.get('current_term', '')
        return YUEJIANG.get(term_name, _approx_yuejiang(month, day))
    except Exception:
        return _approx_yuejiang(month, day)

def _approx_yuejiang(month, day):
    """Fallback: approximate 月将 by month range."""
    md = month * 100 + day
    if md >= 120 and md < 219: return '子'
    if md >= 219 and md < 321: return '亥'
    if md >= 321 and md < 420: return '戌'
    if md >= 420 and md < 521: return '酉'
    if md >= 521 and md < 621: return '申'
    if md >= 621 and md < 723: return '未'
    if md >= 723 and md < 823: return '午'
    if md >= 823 and md < 923: return '巳'
    if md >= 923 and md < 1023: return '辰'
    if md >= 1023 and md < 1122: return '卯'
    if md >= 1122 and md < 1222: return '寅'
    return '丑'


def build_tiandi_pan(yuejiang, shichen):
    """Build天地盘:月将加在时辰上 → 天盘分布."""
    yj_idx = DIZHI.index(yuejiang)
    sc_idx = DIZHI.index(shichen)
    offset = (sc_idx - yj_idx) % 12
    # 天盘: each position's original 地支
    tianpan = {}
    for i in range(12):
        tianpan[DIZHI[i]] = DIZHI[(i + offset) % 12]
    return tianpan


def build_sike(day_gan, day_zhi):
    """Build四课 from day stem-branch."""
    gan_idx = TIANGAN.index(day_gan)
    zhi_idx = DIZHI.index(day_zhi)

    # 第一课: 日干 + 寄宫
    # 天干寄宫: 甲寄寅, 乙寄辰, 丙戊寄巳, 丁己寄未, 庚寄申, 辛寄戌, 壬寄亥, 癸寄丑
    JIGONG = {'甲':'寅','乙':'辰','丙':'巳','丁':'未','戊':'巳','己':'未',
              '庚':'申','辛':'戌','壬':'亥','癸':'丑'}
    gan_jigong = JIGONG.get(day_gan, '寅')

    # 四课 (simplified)
    sike = [
        {'name':'第一课','stem':day_gan,'branch':gan_jigong,'meaning':'日干自身状态'},
        {'name':'第二课','stem':day_gan,'branch':DIZHI[(zhi_idx+1)%12],'meaning':'日干外部影响'},
        {'name':'第三课','stem':TIANGAN[(gan_idx+2)%10],'branch':day_zhi,'meaning':'日支内部状态'},
        {'name':'第四课','stem':TIANGAN[(gan_idx+3)%10],'branch':DIZHI[(zhi_idx+3)%12],'meaning':'日支外部影响'},
    ]
    return sike


def get_tianjiang(day_gan, shichen):
    """Get天将分布 based on day stem + 时辰."""
    gan_idx = TIANGAN.index(day_gan)
    sc_idx = DIZHI.index(shichen)
    # 贵人起法: 从贵人位开始顺/逆排12将
    guiren = GUI_REN_MAP.get(day_gan, ('丑','未'))
    # 昼贵/夜贵: simplified — use first as starting point
    start_zhi = guiren[0]
    start_idx = DIZHI.index(start_zhi)

    # Determine顺逆: 贵人順治/逆治 based on day stem yin-yang
    YANG_GAN = {'甲','丙','戊','庚','壬'}
    if day_gan in YANG_GAN:
        direction = 1  # 顺排
    else:
        direction = -1  # 逆排

    distribution = {}
    for i in range(12):
        pos = (start_idx + direction * i) % 12
        distribution[DIZHI[pos]] = TIANJIANG[i]
    return distribution


def keshi_to_sanchuan(day_gan, sike):
    """Derive三传 (simplified: 贼克法)."""
    # Simplified: use the most克 relationship for三传
    chu_chuan = sike[0]['branch']
    zhong_chuan = sike[1]['branch']
    mo_chuan = sike[2]['branch']
    return {
        '初传': {'branch': chu_chuan, 'meaning': '事情开始'},
        '中传': {'branch': zhong_chuan, 'meaning': '事情发展'},
        '末传': {'branch': mo_chuan, 'meaning': '事情结果'},
    }


def determine_keti(sike):
    """Determine课体 type (simplified)."""
    branches = [s['branch'] for s in sike]
    if len(set(branches)) < 4: return '八专'
    if branches[0] == branches[1]: return '伏吟'
    return '贼克'


# ========== Main API ==========

def bazi_chuan_ren(birth_year=None, birth_month=None, birth_day=None, birth_hour=None,
                   query_year=None, query_month=None, query_day=None, query_hour=None,
                   chart_data=None):
    """
    BaZi + Liu Ren cross-analysis.
    Accepts either raw birth params OR chart_data dict (from bazi_calculator output).
    If no query time given, uses current date.
    Returns comprehensive analysis.
    """
    from bazi_calculator import calculate_four_pillars

    # BaZi — prefer chart_data if provided
    if chart_data:
        fp = chart_data.get('four_pillars', {})
        dm = chart_data.get('day_master', {})
        day_gan = dm.get('gan', '')
        day_zhi = fp.get('day', {}).get('zhi', '')
        # Extract birth info from chart if available
        birth = chart_data.get('birth_info', {})
        if birth and not birth_year:
            birth_year = birth.get('year')
            birth_month = birth.get('month')
            birth_day = birth.get('day')
            birth_hour = birth.get('hour')
    else:
        fp = calculate_four_pillars(birth_year, birth_month, birth_day, birth_hour, 0, 'Beijing')
        day_gan = fp['day_master']
        day_zhi = fp['day']['zhi']

    # Query time (for Liu Ren)
    if query_year is None:
        now = datetime.now()
        query_year, query_month, query_day = now.year, now.month, now.day
        query_hour = now.hour

    # Liu Ren
    yuejiang = get_yuejiang(query_month, query_day)
    shichen = DIZHI[(query_hour + 1) // 2 % 12]
    tiandi = build_tiandi_pan(yuejiang, shichen)
    sike = build_sike(day_gan, day_zhi)
    tianjiang = get_tianjiang(day_gan, shichen)
    sanchuan = keshi_to_sanchuan(day_gan, sike)
    keti = determine_keti(sike)

    # Cross-analysis: compare Liu Ren三传 with BaZi day pillar
    bazi_branch = DIZHI.index(day_zhi)
    sanchuan_branches = [sanchuan['初传']['branch'], sanchuan['中传']['branch'], sanchuan['末传']['branch']]

    relationships = []
    for sc_name, sc_branch in [('初传',sanchuan_branches[0]),('中传',sanchuan_branches[1]),('末传',sanchuan_branches[2])]:
        sc_idx = DIZHI.index(sc_branch)
        diff = (sc_idx - bazi_branch) % 12
        if diff == 0:
            rel = '比和-自身状态'
        elif diff == 6:
            rel = '正冲-重大变化'
        elif diff in (2, 7):
            rel = '相生-有利'
        elif diff in (3, 8):
            rel = '相刑-需注意'
        else:
            rel = '一般'
        relationships.append({'stage': sc_name, 'branch': sc_branch, 'relation': rel})

    # 天将 analysis
    day_zhi_tianjiang = tianjiang.get(day_zhi, '贵人')
    tj_meaning = TIANJIANG_MEANING.get(day_zhi_tianjiang, '')

    # Ketijiexun
    jiexun = KETI_JIEXUN.get(keti, '事情有待观察')

    return {
        'bazi': {
            'day_pillar': day_gan + day_zhi,
            'day_master': day_gan,
        },
        'liuren': {
            'query_time': f'{query_year}-{query_month:02d}-{query_day:02d} {query_hour:02d}:00',
            'yuejiang': yuejiang,
            'shichen': shichen,
            'tiandi_pan': tiandi,
            'tianjiang_on_day': day_zhi_tianjiang,
            'tianjiang_meaning': tj_meaning,
            'sike': sike,
            'sanchuan': sanchuan,
            'keti': keti,
            'jiexun': jiexun,
        },
        'cross_analysis': {
            'relationships': relationships,
            'summary': jiexun + ' ' + tj_meaning,
        }
    }


def main():
    import argparse, json as j
    ap = argparse.ArgumentParser(description='八字穿壬 — BaZi x Da Liu Ren')
    ap.add_argument('--chart', '-c', help='Path to BaZi chart JSON (alternative to birth params)')
    ap.add_argument('--year', type=int, help='Birth year')
    ap.add_argument('--month', type=int, help='Birth month')
    ap.add_argument('--day', type=int, help='Birth day')
    ap.add_argument('--hour', type=int, default=8, help='Birth hour')
    ap.add_argument('--qyear', type=int, help='Query year')
    ap.add_argument('--qmonth', type=int, help='Query month')
    ap.add_argument('--qday', type=int, help='Query day')
    ap.add_argument('--qhour', type=int, help='Query hour')
    ap.add_argument('-o', '--output', help='Output JSON')
    args = ap.parse_args()

    chart_data = None
    if args.chart:
        with open(args.chart, 'r', encoding='utf-8') as f:
            chart_data = j.load(f)

    result = bazi_chuan_ren(args.year, args.month, args.day, args.hour,
                            args.qyear, args.qmonth, args.qday, args.qhour,
                            chart_data=chart_data)

    if args.output:
        j.dump(result, open(args.output, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print('Saved: ' + args.output)
    else:
        b = result['bazi']
        lr = result['liuren']
        ca = result['cross_analysis']
        print('══════ 八字穿壬 ══════')
        print(f'八字日柱: {b["day_pillar"]}  日主: {b["day_master"]}')
        print(f'查询时间: {lr["query_time"]}')
        print(f'月将: {lr["yuejiang"]} | 时辰: {lr["shichen"]}')
        print(f'课体: {lr["keti"]}')
        print(f'天将(日支): {lr["tianjiang_on_day"]} — {lr["tianjiang_meaning"]}')
        print(f'解曰: {lr["jiexun"][:100]}')
        print()
        print('三传:')
        sc = lr.get('sanchuan', {})
        for stage in ['初传','中传','末传']:
            s = sc.get(stage, {})
            if s:
                print(f'  {stage}: {s.get("gan","")}{s.get("branch","")} '
                      f'({s.get("meaning","")})')
        print()
        print('三传×日柱关系:')
        for r in ca['relationships']:
            icon = {'比和-自身状态':'○','正冲-重大变化':'⚠','相生-有利':'✅','相刑-需注意':'⚠','一般':'—'}
            print(f'  {icon.get(r["relation"],"—")} {r["stage"]} {r["branch"]} → {r["relation"]}')


if __name__ == '__main__':
    main()
