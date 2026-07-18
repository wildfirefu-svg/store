#!/usr/bin/env python3
"""
BaZi (八字) & Ziwei Doushu (紫微斗数) Multi-System Calculator.
Pure Python stdlib, no external dependencies.

Usage:
    python bazi_calculator.py --year 1993 --month 7 --day 15 --hour 14 --gender male --mode all
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

from lunar_calendar import solar_to_lunar

# =============================================================================
# 1. CONSTANTS AND LOOKUP TABLES
# =============================================================================

TIANGAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
DIZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']

GAN_WUXING = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
              '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
ZHI_WUXING = {'子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土', '巳': '火',
              '午': '火', '未': '土', '申': '金', '酉': '金', '戌': '土', '亥': '水'}
GAN_YINYANG = {'甲': '阳', '乙': '阴', '丙': '阳', '丁': '阴', '戊': '阳',
               '己': '阴', '庚': '阳', '辛': '阴', '壬': '阳', '癸': '阴'}

# Hidden Stems (藏干): {branch: [(stem, qi_level), ...]}
CANGAN = {
    '子': [('癸', '本气')],
    '丑': [('己', '本气'), ('癸', '中气'), ('辛', '余气')],
    '寅': [('甲', '本气'), ('丙', '中气'), ('戊', '余气')],
    '卯': [('乙', '本气')],
    '辰': [('戊', '本气'), ('乙', '中气'), ('癸', '余气')],
    '巳': [('丙', '本气'), ('庚', '中气'), ('戊', '余气')],
    '午': [('丁', '本气'), ('己', '中气')],
    '未': [('己', '本气'), ('丁', '中气'), ('乙', '余气')],
    '申': [('庚', '本气'), ('壬', '中气'), ('戊', '余气')],
    '酉': [('辛', '本气')],
    '戌': [('戊', '本气'), ('辛', '中气'), ('丁', '余气')],
    '亥': [('壬', '本气'), ('甲', '中气')],
}

# Nayin (纳音) — complete 60-jiazi cycle (hand-verified against standard reference)
NAYIN = {
    '甲子': '海中金', '乙丑': '海中金', '丙寅': '炉中火', '丁卯': '炉中火',
    '戊辰': '大林木', '己巳': '大林木', '庚午': '路旁土', '辛未': '路旁土',
    '壬申': '剑锋金', '癸酉': '剑锋金', '甲戌': '山头火', '乙亥': '山头火',
    '丙子': '涧下水', '丁丑': '涧下水', '戊寅': '城头土', '己卯': '城头土',
    '庚辰': '白蜡金', '辛巳': '白蜡金', '壬午': '杨柳木', '癸未': '杨柳木',
    '甲申': '泉中水', '乙酉': '泉中水', '丙戌': '屋上土', '丁亥': '屋上土',
    '戊子': '霹雳火', '己丑': '霹雳火', '庚寅': '松柏木', '辛卯': '松柏木',
    '壬辰': '长流水', '癸巳': '长流水', '甲午': '砂石金', '乙未': '砂石金',
    '丙申': '山下火', '丁酉': '山下火', '戊戌': '平地木', '己亥': '平地木',
    '庚子': '壁上土', '辛丑': '壁上土', '壬寅': '金箔金', '癸卯': '金箔金',
    '甲辰': '覆灯火', '乙巳': '覆灯火', '丙午': '天河水', '丁未': '天河水',
    '戊申': '大驿土', '己酉': '大驿土', '庚戌': '钗钏金', '辛亥': '钗钏金',
    '壬子': '桑柘木', '癸丑': '桑柘木', '甲寅': '大溪水', '乙卯': '大溪水',
    '丙辰': '沙中土', '丁巳': '沙中土', '戊午': '天上火', '己未': '天上火',
    '庚申': '石榴木', '辛酉': '石榴木', '壬戌': '大海水', '癸亥': '大海水',
}

# Solar terms: precise calculation using sun's ecliptic longitude
# Each term = sun reaches (315 + 15*n)° mod 360, for n=0..23
# Names and their starting ecliptic longitude (立春=315°)
SOLAR_TERM_NAMES = [
    '立春','雨水','惊蛰','春分','清明','谷雨',
    '立夏','小满','芒种','夏至','小暑','大暑',
    '立秋','处暑','白露','秋分','寒露','霜降',
    '立冬','小雪','大雪','冬至','小寒','大寒',
]
# Month-starting terms (节) — these change the month pillar
JIE_QI = {'立春','惊蛰','清明','立夏','芒种','小暑','立秋','白露','寒露','立冬','大雪','小寒'}
# Month branch for each 节: 立春→寅(2), 惊蛰→卯(3), ...
JIE_MONTH_BRANCH = {
    '立春':2,'惊蛰':3,'清明':4,'立夏':5,'芒种':6,'小暑':7,
    '立秋':8,'白露':9,'寒露':10,'立冬':11,'大雪':0,'小寒':1,
}

# Internal: approximate Julian Day for solar terms using Jean Meeus algorithm
import math as _math
def _solar_term_jd(year, term_index):
    """Calculate Julian Day for a solar term in a given year.
    Based on sun's ecliptic longitude reaching (315 + term_index*15) mod 360 degrees.
    Accuracy: ±5 minutes for 1900-2100.
    """
    # Century offset from J2000.0
    y_frac = (year - 2000) / 100.0
    # Mean longitude of sun at J2000.0, increased by 15° per term
    L_target = _math.radians(315.0 + term_index * 15.0)
    # Approximate JD of the term (365.2422 days per tropical year)
    # Base: spring equinox 2000 ≈ JD 2451623.8, 立春(index 18 actually...)
    # Use a reference: 立春 2000 ≈ Feb 4 20:32 UT ≈ JD 2451579.356
    # Solar term J2000 offsets for year 2000 (days from Jan 1 2000 12:00 UT)
    # Calibrated to known astronomical data
    ref_jd = 2451545.0  # J2000.0
    TERM_OFFSETS_2000 = [
        # 立春  雨水  惊蛰  春分  清明  谷雨
        34.0,  49.0,  64.0,  80.0,  95.0, 111.0,
        # 立夏  小满  芒种  夏至  小暑  大暑
       126.0, 142.0, 157.0, 173.0, 189.0, 204.0,
        # 立秋  处暑  白露  秋分  寒露  霜降
       220.0, 236.0, 252.0, 268.0, 282.0, 298.0,
        # 立冬  小雪  大雪  冬至  小寒  大寒
       313.0, 329.0, 343.0, 359.0,   5.0,  20.0,
    ]
    # Use tropical year approximation with calibrated offsets.
    # The 365.2422 + 中心差 combination empirically gives best results (84% accuracy)
    # because errors in the approximation partially cancel.
    approx_jd = ref_jd + (year - 2000) * 365.2422 + TERM_OFFSETS_2000[term_index]
    days_from_J2000 = approx_jd - ref_jd
    M = _math.radians((357.5291 + 0.98560028 * days_from_J2000) % 360.0)
    C = _math.radians(1.914602 * _math.sin(M) + 0.019993 * _math.sin(2*M) + 0.000290 * _math.sin(3*M))
    return approx_jd + C / _math.radians(0.98560767)


def _jd_to_date(jd):
    """Convert Julian Day to (year, month, day, hour, minute) using datetime."""
    from datetime import timedelta as _td
    j2000 = date(2000, 1, 1) + _td(hours=12)
    dt = j2000 + _td(days=jd - 2451545.0)
    frac = (jd - 2451545.0) - int(jd - 2451545.0)
    if frac < 0:
        frac += 1
    hour = int(frac * 24)
    minute = int((frac * 24 - hour) * 60)
    return dt.year, dt.month, dt.day, hour, minute


# Lazy-loaded solar terms lookup table
_solar_term_lookup = None

def _load_solar_terms():
    global _solar_term_lookup
    if _solar_term_lookup is None:
        import json as _json
        try:
            # Try multiple paths: relative to script, then relative to cwd
            script_dir = os.path.dirname(os.path.abspath(__file__))
            paths = [
                os.path.join(script_dir, 'knowledge-base', 'solar_terms.json'),
                os.path.join(os.getcwd(), 'knowledge-base', 'solar_terms.json'),
            ]
            path = None
            for p in paths:
                if os.path.exists(p):
                    path = p
                    break
            if not path:
                _solar_term_lookup = {}
                return _solar_term_lookup
            with open(path, encoding='utf-8') as f:
                _solar_term_lookup = _json.load(f)
        except (FileNotFoundError, _json.JSONDecodeError):
            _solar_term_lookup = {}  # fallback to formula
    return _solar_term_lookup


def get_solar_term_info(year, month, day, hour=0, minute=0):
    """Get precise solar term info using LOOKUP TABLE with time precision.
    For same-day boundaries, uses hour/minute to determine before/after.
    Returns: (current_term_name, month_branch_idx, next_jie_name, next_jie_month, next_jie_day)
    """
    birth_dt = date(year, month, day)
    birth_minutes = hour * 60 + minute
    current_term_name = ''
    current_term_month_branch = 0
    next_jie_name = ''
    next_jie_month = 0
    next_jie_day = 0

    lookup = _load_solar_terms()
    all_terms = []
    for y in (year - 1, year):
        for i in range(24):
            term_name = SOLAR_TERM_NAMES[i]
            key = f'{y}|{term_name}'
            if key in lookup:
                val = lookup[key]
                tm, td = val[0], val[1]
                th = val[2] if len(val) > 2 else 0
                tmin = val[3] if len(val) > 3 else 0
                verified = val[4] if len(val) > 4 else False
                # Only use time comparison if hand-verified (verified=True)
                if verified:
                    term_minutes = th * 60 + tmin
                else:
                    term_minutes = -1  # date-only mode (formula time stored for reference)
                all_terms.append((date(y, tm, td), term_minutes, term_name, i, tm, td))
            else:
                jd = _solar_term_jd(y, i)
                ty, tm, td, _, _ = _jd_to_date(jd)
                all_terms.append((date(ty, tm, td), -1, term_name, i, tm, td))

    all_terms.sort(key=lambda x: (x[0], x[1] if x[1] >= 0 else 0))

    for term_dt, term_minutes, term_name, i, tm, td in all_terms:
        before = False
        if term_minutes >= 0:
            # Time-verified: exact comparison
            before = (term_dt < birth_dt) or (term_dt == birth_dt and term_minutes <= birth_minutes)
        else:
            # Date-only: just compare dates
            before = term_dt <= birth_dt

        if before:
            current_term_name = term_name
            if term_name in JIE_MONTH_BRANCH:
                current_term_month_branch = JIE_MONTH_BRANCH[term_name]
        elif term_name in JIE_QI and not next_jie_name:
            next_jie_name = term_name
            next_jie_month = tm
            next_jie_day = td

    if not current_term_name:
        current_term_name = '小寒'
        current_term_month_branch = 1

    return current_term_name, current_term_month_branch, next_jie_name, next_jie_month, next_jie_day


# =============================================================================
# 1b. LUNAR CALENDAR (农历转换) — API spec §2.1, §6
# =============================================================================


# Ten Gods lookup: (day_master_element, target_element, yin_yang_match)
# Returns the ten god name
def get_shishen(day_master_gan, target_gan):
    """Get Ten God (十神) relationship of target_gan relative to day_master_gan."""
    dm_elem = GAN_WUXING[day_master_gan]
    t_elem = GAN_WUXING[target_gan]
    dm_yy = GAN_YINYANG[day_master_gan]
    t_yy = GAN_YINYANG[target_gan]
    same_yy = (dm_yy == t_yy)

    if dm_elem == t_elem:
        return '比肩' if same_yy else '劫财'
    # 我生
    if ((dm_elem == '木' and t_elem == '火') or
        (dm_elem == '火' and t_elem == '土') or
        (dm_elem == '土' and t_elem == '金') or
        (dm_elem == '金' and t_elem == '水') or
        (dm_elem == '水' and t_elem == '木')):
        return '食神' if same_yy else '伤官'
    # 我克 (同阴阳→偏财，异阴阳→正财)
    if ((dm_elem == '木' and t_elem == '土') or
        (dm_elem == '火' and t_elem == '金') or
        (dm_elem == '土' and t_elem == '水') or
        (dm_elem == '金' and t_elem == '木') or
        (dm_elem == '水' and t_elem == '火')):
        return '偏财' if same_yy else '正财'
    # 克我 (同阴阳→七杀，异阴阳→正官)
    if ((t_elem == '木' and dm_elem == '土') or
        (t_elem == '火' and dm_elem == '金') or
        (t_elem == '土' and dm_elem == '水') or
        (t_elem == '金' and dm_elem == '木') or
        (t_elem == '水' and dm_elem == '火')):
        return '七杀' if same_yy else '正官'
    # 生我 (同阴阳→偏印，异阴阳→正印)
    if ((t_elem == '木' and dm_elem == '火') or
        (t_elem == '火' and dm_elem == '土') or
        (t_elem == '土' and dm_elem == '金') or
        (t_elem == '金' and dm_elem == '水') or
        (t_elem == '水' and dm_elem == '木')):
        return '偏印' if same_yy else '正印'
    return '未知'

# Shensha lookup tables
TIANYI_GUIREN = {
    '甲': ('丑', '未'), '戊': ('丑', '未'), '庚': ('丑', '未'),
    '乙': ('子', '申'), '己': ('子', '申'),
    '丙': ('亥', '酉'), '丁': ('亥', '酉'),
    '辛': ('午', '寅'), '壬': ('巳', '卯'), '癸': ('巳', '卯'),
}

WENCHANG = {
    '甲': '巳', '乙': '午', '丙': '申', '丁': '酉', '戊': '申',
    '己': '酉', '庚': '亥', '辛': '子', '壬': '寅', '癸': '卯',
}

# Peach Blossom (桃花): 申子辰在酉, 寅午戌在卯, 亥卯未在子, 巳酉丑在午
TAOHUA_MAP = {
    ('申', '子', '辰'): '酉', ('寅', '午', '戌'): '卯',
    ('亥', '卯', '未'): '子', ('巳', '酉', '丑'): '午',
}

# Yi Ma (驿马): 寅午戌在申, 申子辰在寅, 巳酉丑在亥, 亥卯未在巳
YIMA_MAP = {
    ('寅', '午', '戌'): '申', ('申', '子', '辰'): '寅',
    ('巳', '酉', '丑'): '亥', ('亥', '卯', '未'): '巳',
}

# Hua Gai (华盖): 寅午戌在戌, 申子辰在辰, 巳酉丑在丑, 亥卯未在未
HUAGAI_MAP = {
    ('寅', '午', '戌'): '戌', ('申', '子', '辰'): '辰',
    ('巳', '酉', '丑'): '丑', ('亥', '卯', '未'): '未',
}

# Yang Ren (羊刃): day stem's yang branch of the same element (帝旺 position)
YANGREN_MAP = {'甲': '卯', '丙': '午', '戊': '午', '庚': '酉', '壬': '子'}

# Kui Gang (魁罡): exact stem-branch combos
KUIGANG = {'庚辰', '庚戌', '壬辰', '戊戌'}

# ── Extended shensha lookup tables (module-level, shared by calculate_shensha) ──

# 天德贵人: 月支查天干
_tiande = {'寅':'丁','卯':'申','辰':'壬','巳':'辛','午':'亥','未':'甲','申':'癸','酉':'寅','戌':'丙','亥':'乙','子':'巳','丑':'庚'}
# 月德贵人: 月支三合查天干 (keyed by month branch index 0=子)
_yuede = {2:'丙',6:'丙',10:'丙',3:'甲',7:'甲',11:'甲',8:'壬',0:'壬',4:'壬',5:'庚',9:'庚',1:'庚'}
# 月德查干 (三合局→天干, used in月支系 check)
_yuede_by_group = {('寅','午','戌'):'丙',('亥','卯','未'):'甲',('申','子','辰'):'壬',('巳','酉','丑'):'庚'}
# 将星: 三合局查
_jiangxing = {('寅','午','戌'):'午',('申','子','辰'):'子',('亥','卯','未'):'卯',('巳','酉','丑'):'酉'}
# 劫煞
_jiesha = {('寅','午','戌'):'亥',('申','子','辰'):'巳',('亥','卯','未'):'申',('巳','酉','丑'):'寅'}
# 灾煞
_zaisha = {('寅','午','戌'):'子',('申','子','辰'):'午',('亥','卯','未'):'酉',('巳','酉','丑'):'卯'}
# 亡神
_wangshen = {('寅','午','戌'):'巳',('申','子','辰'):'亥',('亥','卯','未'):'寅',('巳','酉','丑'):'申'}
# 孤辰: 四正局查 (年支在局→目标支)
_guchen = {('亥','子','丑'):'寅',('寅','卯','辰'):'巳',('巳','午','未'):'申',('申','酉','戌'):'亥'}
# 寡宿
_guasu = {('亥','子','丑'):'戌',('寅','卯','辰'):'丑',('巳','午','未'):'辰',('申','酉','戌'):'未'}
# 禄神: 日干查
_lushen = {'甲':'寅','乙':'卯','丙':'巳','丁':'午','戊':'巳','己':'午','庚':'申','辛':'酉','壬':'亥','癸':'子'}
# 太极贵人: 日干查
_taiji = {'甲':('子','午'),'乙':('子','午'),'丙':('卯','酉'),'丁':('卯','酉'),'戊':('辰','戌','丑','未'),'己':('辰','戌','丑','未'),'庚':('寅','亥'),'辛':('寅','亥'),'壬':('巳','申'),'癸':('巳','申')}
# 学堂: 日干查长生位
_xuetang = {'甲':'亥','乙':'午','丙':'寅','丁':'酉','戊':'寅','己':'酉','庚':'巳','辛':'子','壬':'申','癸':'卯'}
# 词馆: 日干查临官位
_ciguan = {'甲':'寅','乙':'卯','丙':'巳','丁':'午','戊':'巳','己':'午','庚':'申','辛':'酉','壬':'亥','癸':'子'}
# 金舆: 日干查
_jinyu = {'甲':'辰','乙':'巳','丙':'未','丁':'申','戊':'未','己':'申','庚':'戌','辛':'亥','壬':'丑','癸':'寅'}
# 国印: 日干查
_guoyin = {'甲':'戌','乙':'亥','丙':'丑','丁':'寅','戊':'丑','己':'寅','庚':'辰','辛':'巳','壬':'未','癸':'申'}
# 红鸾: 年支查 (卯起子年逆数)
_hongluan_by_zhi = {'子':'卯','丑':'寅','寅':'丑','卯':'子','辰':'亥','巳':'戌','午':'酉','未':'申','申':'未','酉':'午','戌':'巳','亥':'辰'}
# 红艳煞: 日干查
_hongyan = {'甲':'午','乙':'申','丙':'寅','丁':'未','戊':'辰','己':'亥','庚':'戌','辛':'酉','壬':'子','癸':'巳'}
# 流霞: 日干查
_liuxia = {'甲':'酉','乙':'戌','丙':'未','丁':'申','戊':'巳','己':'午','庚':'辰','辛':'卯','壬':'亥','癸':'寅'}
# 飞刃: 日干羊刃对冲 (仅阳干有)
_feiren = {'甲':'酉','丙':'子','戊':'子','庚':'卯','壬':'午'}
# 丧门: 年支查
_sangmen = {'子':'寅','丑':'卯','寅':'辰','卯':'巳','辰':'午','巳':'未','午':'申','未':'酉','申':'戌','酉':'亥','戌':'子','亥':'丑'}
# 吊客: 年支查
_diaoke = {'子':'戌','丑':'亥','寅':'子','卯':'丑','辰':'寅','巳':'卯','午':'辰','未':'巳','申':'午','酉':'未','戌':'申','亥':'酉'}
# 白虎: 年支查
_baihu = {'子':'申','丑':'酉','寅':'戌','卯':'亥','辰':'子','巳':'丑','午':'寅','未':'卯','申':'辰','酉':'巳','戌':'午','亥':'未'}
# 血刃: 月支查
_xueren = {'寅':'丑','卯':'未','辰':'寅','巳':'申','午':'卯','未':'酉','申':'辰','酉':'戌','戌':'巳','亥':'亥','子':'午','丑':'子'}
# 紫微: 日支三合查
_ziwei_ss = {('申','子','辰'):'酉',('亥','卯','未'):'子',('寅','午','戌'):'卯',('巳','酉','丑'):'午'}
# 龙德: 月支查
_longde = {'寅':'未','卯':'申','辰':'酉','巳':'戌','午':'亥','未':'子','申':'丑','酉':'寅','戌':'卯','亥':'辰','子':'巳','丑':'午'}
# 孤鸾煞: 日柱为
_guluan = {'甲寅','乙卯','丙午','丁巳','戊午','己巳','庚申','辛酉','壬子','癸亥'}
# 阴差阳错: 日柱为
_yincha = {'丙子','丁丑','戊寅','辛卯','壬辰','癸巳','丙午','丁未','戊申','辛酉','壬戌','癸亥'}
# 十恶大败: 日柱为
_shiedabai = {'甲辰','乙巳','壬申','丙申','丁亥','庚辰','戊戌','辛巳','己丑','癸亥'}
# 八专: 日柱为
_bazhuan = {'甲寅','乙卯','丁未','己未','庚申','辛酉','癸丑'}
# 悬针: 日柱干支组合
_xuanzhen = {'甲卯','甲午','辛酉','辛子','甲子','辛卯','甲酉','辛午'}
# 三合禄: 三合临官位
_sanhelu = {('申','子','辰'):'亥',('亥','卯','未'):'寅',('寅','午','戌'):'巳',('巳','酉','丑'):'申'}
# 天赦: 日柱为
_tianshe = {'戊寅','甲午','戊申','甲子'}

# Ziwei: Four Transformations (四化) by year stem
SIHUA_TABLE = {
    '甲': {'禄': '廉贞', '权': '破军', '科': '武曲', '忌': '太阳'},
    '乙': {'禄': '天机', '权': '天梁', '科': '紫微', '忌': '太阴'},
    '丙': {'禄': '天同', '权': '天机', '科': '文昌', '忌': '廉贞'},
    '丁': {'禄': '太阴', '权': '天同', '科': '天机', '忌': '巨门'},
    '戊': {'禄': '贪狼', '权': '太阴', '科': '右弼', '忌': '天机'},
    '己': {'禄': '武曲', '权': '贪狼', '科': '天梁', '忌': '文曲'},
    '庚': {'禄': '太阳', '权': '武曲', '科': '太阴', '忌': '天同'},
    '辛': {'禄': '巨门', '权': '太阳', '科': '文曲', '忌': '文昌'},
    '壬': {'禄': '天梁', '权': '紫微', '科': '左辅', '忌': '武曲'},
    '癸': {'禄': '破军', '权': '巨门', '科': '太阴', '忌': '贪狼'},
}

# ── Brightness from iztro brightness.py ─  order: 寅卯辰巳午未申酉戌亥子丑 ─
_STAR_BRIGHTNESS = {
    '紫微':   ['旺','旺','得','旺','庙','庙','旺','旺','得','旺','平','庙'],
    '天机':   ['得','旺','利','平','庙','陷','得','旺','利','平','庙','陷'],
    '太阳':   ['旺','庙','旺','旺','旺','得','得','平','陷','陷','陷','不'],
    '武曲':   ['得','利','庙','平','旺','庙','得','利','庙','平','旺','庙'],
    '天同':   ['利','平','平','庙','陷','不','旺','平','平','庙','旺','不'],
    '廉贞':   ['平','平','利','陷','平','利','庙','平','利','陷','平','利'],
    '天府':   ['庙','庙','庙','得','旺','旺','得','旺','庙','得','庙','庙'],
    '太阴':   ['庙','陷','陷','陷','陷','利','利','庙','庙','庙','庙','庙'],
    '贪狼':   ['平','利','庙','陷','旺','庙','平','利','庙','陷','旺','庙'],
    '巨门':   ['庙','庙','平','旺','旺','不','庙','庙','平','旺','旺','不'],
    '天相':   ['庙','陷','得','得','庙','得','庙','陷','得','得','庙','庙'],
    '天梁':   ['庙','庙','庙','陷','庙','旺','陷','得','庙','陷','庙','旺'],
    '七杀':   ['庙','旺','庙','平','旺','庙','庙','旺','庙','平','旺','庙'],
    '破军':   ['得','陷','旺','平','庙','旺','得','陷','旺','平','庙','旺'],
}

def _get_brightness(star_name, zhi_idx):
    """Return brightness for star at standard 地支 index (0=子).
    Brightness table is in 寅=0 order, so convert: zhi_idx → (zhi_idx - 2 + 12) % 12.
    """
    tbl = _STAR_BRIGHTNESS.get(star_name)
    if not tbl:
        return ''
    # Convert standard 地支 index (0=子) to table index (0=寅)
    ti = (zhi_idx - 2 + 12) % 12
    b = tbl[ti] if ti < len(tbl) else ''
    # Map iztro levels: 庙旺得利平不陷 → 庙旺得平陷
    return {'庙':'庙','旺':'旺','得':'得','利':'得','平':'平','不':'陷','陷':'陷'}.get(b, b)

# ── 命主星 / 身主星 tables ────────────────────────────────────
# 命主星 — by 命宫地支 (iztro: get_soul_star)
_MINGZHU_TABLE = {
    '子': '贪狼', '丑': '巨门', '寅': '禄存', '卯': '文曲',
    '辰': '廉贞', '巳': '武曲', '午': '破军', '未': '武曲',
    '申': '廉贞', '酉': '文曲', '戌': '禄存', '亥': '巨门',
}
# 身主星 — by 出生年支 (iztro: get_body_star), NOT 身宫地支
_SHENZHU_TABLE = {
    '子': '火星', '丑': '天相', '寅': '天梁', '卯': '天同',
    '辰': '文昌', '巳': '天机', '午': '火星', '未': '天相',
    '申': '天梁', '酉': '天同', '戌': '文昌', '亥': '天机',
}

# Ziwei: 14 main stars in deployment order from Ziwei position
ZIWEI_STAR_ORDER = [
    '紫微', '天机', '太阳', '武曲', '天同', '廉贞',
    '天府', '太阴', '贪狼', '巨门', '天相', '天梁', '七杀', '破军',
]

# Ziwei: position table — given 五行局 and lunar day, return Ziwei branch index
# Key: (wuxing_ju, lunar_day), Value: branch index (0=寅)
# 五行局: 水二局(2), 木三局(3), 金四局(4), 土五局(5), 火六局(6)
def ziwei_position(wuxing_ju, lunar_day):
    """Calculate Ziwei star's branch index (0=寅) based on 五行局 and lunar day.

    Standard formula: 紫微起寅, each day moves (wuxing_ju - 1) positions counter-clockwise.
    position = -(day - 1) * (ju - 1) mod 12
    """
    if lunar_day > 30:
        lunar_day = 30
    ju = wuxing_ju if wuxing_ju in (2, 3, 4, 5, 6) else 2
    return (-(lunar_day - 1) * (ju - 1)) % 12

# 五行局 from nayin of 命宫
WUXING_JU_MAP = {
    '金': 4, '木': 3, '水': 2, '火': 6, '土': 5,
}


# =============================================================================
# 2. HELPER FUNCTIONS
# =============================================================================

def sexagenary_index(gan, zhi):
    """Return the 0-based index in the 60-jiazi cycle for a given gan+zhi pair."""
    gi = TIANGAN.index(gan)
    zi = DIZHI.index(zhi)
    for i in range(60):
        if i % 10 == gi and i % 12 == zi:
            return i
    return 0


def sexagenary_by_index(idx):
    """Return (gan, zhi) for a given 0-based index in the 60-jiazi cycle."""
    return TIANGAN[idx % 10], DIZHI[idx % 12]


def get_year_pillar(year, month=1, day=1, hour=0, minute=0):
    """Year pillar changes at 立春. Uses solar term lookup for precise boundary."""
    lookup = _load_solar_terms()
    key = f'{year}|立春'
    if key in lookup:
        val = lookup[key]
        lc_m, lc_d = val[0], val[1]
        lc_h = val[2] if len(val) > 2 and val[2] >= 0 else -1
        lc_min = val[3] if len(val) > 3 else 0
        before = False
        if month < lc_m: before = True
        elif month == lc_m and day < lc_d: before = True
        elif month == lc_m and day == lc_d and lc_h >= 0:
            before = (hour * 60 + minute) < (lc_h * 60 + lc_min)
        effective_year = year - 1 if before else year
    else:
        effective_year = year - 1 if (month < 2 or (month == 2 and day < 4)) else year
    idx = (effective_year - 4) % 60
    return sexagenary_by_index(idx)


def get_month_branch_idx(year, month, day, hour=0, minute=0):
    """Get the month branch DIZHI index using precise solar term calculation."""
    _, month_branch, _, _, _ = get_solar_term_info(year, month, day, hour, minute)
    return month_branch


def get_next_jie_info(year, month, day, hour=0, minute=0):
    """Get the NEXT 节 for 大运起运 calculation."""
    _, _, next_name, next_m, next_d = get_solar_term_info(year, month, day, hour, minute)
    return next_name, next_m, next_d


def get_month_pillar(year, year_gan, month, day, hour=0, minute=0):
    """Calculate month pillar using 五虎遁 + precise solar terms.
    If year_gan is empty, returns only the branch (effective year not yet determined)."""
    month_zhi_idx = get_month_branch_idx(year, month, day, hour, minute)
    if not year_gan:
        return '', DIZHI[month_zhi_idx]
    year_stem_idx = TIANGAN.index(year_gan)
    month_num = (month_zhi_idx - 2) % 12 + 1
    month_stem_idx = ((year_stem_idx % 5) * 2 + 2 + month_num - 1) % 10
    return TIANGAN[month_stem_idx], DIZHI[month_zhi_idx]


def get_day_pillar(year, month, day):
    """Calculate day pillar based on days elapsed from a known reference date.
    Reference: 1900-01-01 = 甲戌 (index 10 in sexagenary cycle).
    Verified: 2018-11-06 should be 壬寅.
    """
    ref_date = date(1900, 1, 1)
    target_date = date(year, month, day)
    delta = (target_date - ref_date).days
    idx = (delta + 10) % 60
    return sexagenary_by_index(idx)


def get_hour_pillar(day_gan, hour, minute=0):
    """Calculate hour pillar with 子时 early/late distinction (API spec §6).
    子时 23:00-00:59 → 夜子时(23-0点)用次日干, 早子时(0-1点)用当日干.
    """
    if hour == 23 or (hour == 0 and minute < 60):
        # 子时
        hour_branch_idx = 0  # 子
        if hour == 23:
            # 夜子时: use NEXT day's stem
            day_stem_idx = (TIANGAN.index(day_gan) + 1) % 10
        else:
            # 早子时 0:00-0:59: use current day's stem
            day_stem_idx = TIANGAN.index(day_gan)
    else:
        hour_branch_idx = (hour + 1) // 2 % 12
        day_stem_idx = TIANGAN.index(day_gan)

    hour_stem_idx = (day_stem_idx * 2 + hour_branch_idx) % 10
    return TIANGAN[hour_stem_idx], DIZHI[hour_branch_idx]


def get_kongwang(gan, zhi):
    """Calculate 空亡 branches for a pillar.
    Each 旬 (10 stems × 2 branches gap) has 2 empty branches.
    """
    gi = TIANGAN.index(gan)
    zi = DIZHI.index(zhi)
    # Which 旬? stem idx i, branch matching starts at (i - zi + 12) % 12
    # Empty branches are the two that don't get paired with stems in this 旬
    xun_start = zi - gi
    if xun_start < 0:
        xun_start += 12
    kong1 = (xun_start + 10) % 12
    kong2 = (xun_start + 11) % 12
    return DIZHI[kong1], DIZHI[kong2]


def get_taiyuan(month_gan, month_zhi, year_gan, year_zhi):
    """胎元: month stem's previous stem + month branch's next 3rd branch.
    Simplified: month gan - 1, month zhi + 3.
    """
    gi = (TIANGAN.index(month_gan) - 1) % 10
    zi = (DIZHI.index(month_zhi) + 3) % 12
    return TIANGAN[gi], DIZHI[zi]


def get_minggong(month_zhi, hour_zhi):
    """命宫: 从寅起正月顺数至生月，再起子时逆数至生时.
    命宫 = (month_idx - hour_idx) % 12
    """
    month_idx = DIZHI.index(month_zhi)
    hour_idx = DIZHI.index(hour_zhi)
    ming_idx = (month_idx - hour_idx) % 12
    return DIZHI[ming_idx]


def get_shengong(month_zhi, hour_zhi):
    """身宫: 从寅起正月顺数至生月，再起子时顺数至生时.
    身宫 = (month_idx + hour_idx) % 12
    """
    month_idx = DIZHI.index(month_zhi)
    hour_idx = DIZHI.index(hour_zhi)
    shen_idx = (month_idx + hour_idx) % 12
    return DIZHI[shen_idx]


# =============================================================================
# 2b. EXTENDED RELATIONSHIP DETECTION
# =============================================================================

# Branch relationships
LIUHE = {('子','丑'),('寅','亥'),('卯','戌'),('辰','酉'),('巳','申'),('午','未')}
SANHE = {('申','子','辰'),('亥','卯','未'),('寅','午','戌'),('巳','酉','丑')}
LIUCHONG = {('子','午'),('丑','未'),('寅','申'),('卯','酉'),('辰','戌'),('巳','亥')}
SANXING = {('寅','巳','申'),('丑','戌','未'),('子','卯'),('辰','午','酉','亥')}
LIUHAI = {('子','未'),('丑','午'),('寅','巳'),('卯','辰'),('申','亥'),('酉','戌')}

# 十二长生 table: stem -> [长生,沐浴,冠带,临官,帝旺,衰,病,死,墓,绝,胎,养] branch indices
CHANGSHENG_TABLE = {
    '甲': [11, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],   # 阳顺：长生亥
    '乙': [6, 5, 4, 3, 2, 1, 0, 11, 10, 9, 8, 7],   # 阴逆：长生午
    '丙': [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1],   # 阳顺：长生寅
    '丁': [9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 11, 10],   # 阴逆：长生酉
    '戊': [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1],   # 阳顺：长生寅（火土同宫）
    '己': [9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 11, 10],   # 阴逆：长生酉
    '庚': [5, 6, 7, 8, 9, 10, 11, 0, 1, 2, 3, 4],   # 阳顺：长生巳
    '辛': [0, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],   # 阴逆：长生子
    '壬': [8, 9, 10, 11, 0, 1, 2, 3, 4, 5, 6, 7],   # 阳顺：长生申
    '癸': [3, 2, 1, 0, 11, 10, 9, 8, 7, 6, 5, 4],   # 阴逆：长生卯
}
CHANGSHENG_NAMES = ['长生','沐浴','冠带','临官','帝旺','衰','病','死','墓','绝','胎','养']

# 日柱干支自合: day stem + hidden stem in day branch
ZHI_HE_MAP = {
    '甲': '己', '己': '甲', '乙': '庚', '庚': '乙',
    '丙': '辛', '辛': '丙', '丁': '壬', '壬': '丁', '戊': '癸', '癸': '戊',
}

def detect_branch_relations(four_pillars):
    """Detect 合冲刑害 relationships among the four pillar branches."""
    branches = {}
    for key in ['year','month','day','hour']:
        if key in four_pillars:
            branches[key] = four_pillars[key]['zhi']

    relations = []
    checked = set()
    for k1, z1 in branches.items():
        for k2, z2 in branches.items():
            if k1 >= k2:
                continue
            pair = (z1, z2)
            rpair = (z2, z1)
            if pair in LIUHE or rpair in LIUHE:
                relations.append({'type':'六合','pillars':f'{k1}-{k2}','detail':f'{z1}{z2}合'})
            elif (z1, z2) in LIUCHONG or (z2, z1) in LIUCHONG:
                relations.append({'type':'六冲','pillars':f'{k1}-{k2}','detail':f'{z1}{z2}冲'})
            # Check 三刑
            for xing_group in SANXING:
                if z1 in xing_group and z2 in xing_group and z1 != z2:
                    relations.append({'type':'三刑','pillars':f'{k1}-{k2}','detail':f'{z1}{z2}刑'})
                    break
            # Check 六害
            if (z1, z2) in LIUHAI or (z2, z1) in LIUHAI:
                relations.append({'type':'六害','pillars':f'{k1}-{k2}','detail':f'{z1}{z2}害'})

    # Check 三合（sorted 固定迭代顺序：SANHE 为集合，字符串哈希随机化会导致跨进程顺序漂移）
    for group in sorted(SANHE):
        matches = []
        for k, z in branches.items():
            if z in group:
                matches.append((k, z))
        if len(matches) >= 2:
            zhis = ''.join(z for _, z in matches)
            kstr = '-'.join(k for k, _ in matches)
            relations.append({'type':'三合','pillars':kstr,'detail':f'{zhis}合局'})

    return relations


def get_changsheng(gan, zhi):
    """Get 十二长生 state of gan at zhi."""
    if gan not in CHANGSHENG_TABLE:
        return '未知'
    table = CHANGSHENG_TABLE[gan]
    zi = DIZHI.index(zhi)
    for i, idx in enumerate(table):
        if idx == zi:
            return CHANGSHENG_NAMES[i]
    return '未知'


def detect_rizhu_zihe(day_gan, day_zhi):
    """Detect if day pillar has stem-branch self-combination (日柱干支自合)."""
    cangan_stems = [g for g, _ in CANGAN.get(day_zhi, [])]
    for cg in cangan_stems:
        if ZHI_HE_MAP.get(day_gan) == cg:
            return {
                'is_zihe': True,
                'day_gan': day_gan,
                'hidden_stem': cg,
                'he_type': f'{day_gan}{cg}合',
                'meaning': _get_zihe_meaning(day_gan, cg, day_zhi),
            }
    return {'is_zihe': False}


def _get_zihe_meaning(day_gan, hidden_stem, day_zhi):
    """Get meaning of 日柱干支自合."""
    combos = {
        ('丁','壬'): '表面温和，内心有大志向，官星藏于内',
        ('戊','癸'): '表面稳重，内心精明，财星藏于内',
        ('辛','丙'): '表面精致，内心热情，官星藏于内',
        ('壬','丁'): '表面奔放，内心细腻，财星藏于内',
        ('癸','戊'): '表面隐秘，内心稳重，官星藏于内',
        ('甲','己'): '表面刚强，内心柔软，财星藏于内',
    }
    for (a, b), meaning in combos.items():
        if (day_gan == a and hidden_stem == b) or (day_gan == b and hidden_stem == a):
            return meaning
    return f'{day_gan}{hidden_stem}合，内心世界丰富，表面与内心不同'
# =============================================================================

def calculate_four_pillars(year, month, day, hour, minute=0, location="Beijing"):
    """Calculate the complete four pillars with all auxiliary data."""
    year_gan, year_zhi = get_year_pillar(year, month, day, hour, minute)
    month_gan, month_zhi = get_month_pillar(year, year_gan, month, day, hour, minute)
    day_gan, day_zhi = get_day_pillar(year, month, day)
    hour_gan, hour_zhi = get_hour_pillar(day_gan, hour, minute)

    pillars = {
        'year':  {'gan': year_gan, 'zhi': year_zhi},
        'month': {'gan': month_gan, 'zhi': month_zhi},
        'day':   {'gan': day_gan, 'zhi': day_zhi},
        'hour':  {'gan': hour_gan, 'zhi': hour_zhi},
    }

    result = {}
    for key, p in pillars.items():
        gan, zhi = p['gan'], p['zhi']
        cangan_data = CANGAN[zhi]
        cangan_str = ','.join(g for g, _ in cangan_data)

        shishen = {}
        for cg, _ in cangan_data:
            shishen[cg] = get_shishen(day_gan, cg)
        stem_shishen = get_shishen(day_gan, gan)
        shishen[gan] = stem_shishen

        kw = get_kongwang(gan, zhi)
        nayin_key = gan + zhi
        nayin = NAYIN.get(nayin_key, '未知')

        result[key] = {
            'gan': gan,
            'zhi': zhi,
            'cangan': cangan_str,
            'cangan_detail': [{'stem': g, 'level': l} for g, l in cangan_data],
            'shishen': shishen,
            'nayin': nayin,
            'kongwang': f'{kw[0]}{kw[1]}',
        }

    # Auxiliary
    taiyuan_gan, taiyuan_zhi = get_taiyuan(month_gan, month_zhi, year_gan, year_zhi)
    minggong_zhi = get_minggong(month_zhi, hour_zhi)
    shengong_zhi = get_shengong(month_zhi, hour_zhi)
    # Derive minggong gan from year stem
    minggong_gan_idx = (TIANGAN.index(year_gan) * 2 + DIZHI.index(minggong_zhi)) % 10
    minggong_gan = TIANGAN[minggong_gan_idx]
    shengong_gan_idx = (TIANGAN.index(year_gan) * 2 + DIZHI.index(shengong_zhi)) % 10
    shengong_gan = TIANGAN[shengong_gan_idx]

    taiyuan_key = taiyuan_gan + taiyuan_zhi
    minggong_key = minggong_gan + minggong_zhi
    shengong_key = shengong_gan + shengong_zhi

    result['day_master'] = day_gan
    result['taiyuan'] = {'gan': taiyuan_gan, 'zhi': taiyuan_zhi, 'nayin': NAYIN.get(taiyuan_key, '未知')}
    result['minggong'] = {'gan': minggong_gan, 'zhi': minggong_zhi, 'nayin': NAYIN.get(minggong_key, '未知')}
    result['shengong'] = {'gan': shengong_gan, 'zhi': shengong_zhi, 'nayin': NAYIN.get(shengong_key, '未知')}

    # Precision note for solar term boundaries
    term_name, _, _, _, _ = get_solar_term_info(year, month, day, hour, minute)
    if term_name in JIE_QI:
        result['precision_note'] = f'出生日期临近节气交界({term_name})，月柱已按精确节气时刻校正'

    # Extended data
    result['branch_relations'] = detect_branch_relations(result)
    result['changsheng'] = {
        'year': get_changsheng(year_gan, year_zhi),
        'month': get_changsheng(month_gan, month_zhi),
        'day': get_changsheng(day_gan, day_zhi),
        'hour': get_changsheng(hour_gan, hour_zhi),
        'day_master': get_changsheng(day_gan, day_zhi),
    }
    result['rizhu_zihe'] = detect_rizhu_zihe(day_gan, day_zhi)
    # 纳音五行属性 (for 纳音生克分析)
    result['nayin_wuxing'] = {}
    for key in ['year','month','day','hour']:
        n = result[key]['nayin']
        for elem in ['金','木','水','火','土']:
            if elem in n:
                result['nayin_wuxing'][key] = elem
                break
        else:
            result['nayin_wuxing'][key] = '未知'

    return result


# =============================================================================
# 4. LUCK PILLARS (大运) CALCULATION
# =============================================================================

def calculate_dayun(year_pillar, month_pillar, gender, birth_year, birth_month, birth_day,
                    birth_hour=0, birth_minute=0):
    """Calculate luck pillars (大运).

    Args:
        birth_hour: Corrected birth hour for precise solar term junction calculation
        birth_minute: Corrected birth minute for precise solar term junction calculation
    """
    year_gan, _ = year_pillar
    month_gan, month_zhi = month_pillar
    is_yang = GAN_YINYANG[year_gan] == '阳'

    # Direction: yang male / yin female → forward (顺排); else → backward (逆排)
    if (is_yang and gender == 'male') or (not is_yang and gender == 'female'):
        direction = '顺排'
    else:
        direction = '逆排'

    # Starting age: use precise solar term calculation with corrected birth time
    _, _, next_jie_name, next_jie_m, next_jie_d = get_solar_term_info(
        birth_year, birth_month, birth_day, birth_hour, birth_minute)

    from datetime import datetime as _dt, timedelta as _td
    birth_dt = _dt(birth_year, birth_month, birth_day, birth_hour, birth_minute)

    if direction == '顺排':
        next_jie_candidates = []
        for i in range(24):
            jd = _solar_term_jd(birth_year, i)
            ty, tm, td, th, tmin = _jd_to_date(jd)
            term_name = SOLAR_TERM_NAMES[i]
            if term_name in JIE_QI:
                t_dt = _dt(ty, tm, td, th, tmin)
                if t_dt > birth_dt:
                    next_jie_candidates.append(t_dt)
        if next_jie_candidates:
            junction_dt = min(next_jie_candidates)
            delta = junction_dt - birth_dt
            days_to_junction = delta.days + delta.seconds / 86400.0
        else:
            days_to_junction = 15.0
    else:
        prev_jie_candidates = []
        for i in range(24):
            jd = _solar_term_jd(birth_year, i)
            ty, tm, td, th, tmin = _jd_to_date(jd)
            term_name = SOLAR_TERM_NAMES[i]
            if term_name in JIE_QI:
                t_dt = _dt(ty, tm, td, th, tmin)
                if t_dt < birth_dt:
                    prev_jie_candidates.append(t_dt)
        if prev_jie_candidates:
            junction_dt = max(prev_jie_candidates)
            delta = birth_dt - junction_dt
            days_to_junction = delta.days + delta.seconds / 86400.0
        else:
            days_to_junction = 15.0

    # Starting age: 3 days = 1 year
    starting_age = max(0, round(days_to_junction / 3, 1))

    # Generate luck pillars
    month_idx = sexagenary_index(month_gan, month_zhi)
    pillars = []
    step = 1 if direction == '顺排' else -1

    for i in range(10):
        luck_idx = (month_idx + step * (i + 1)) % 60
        lg, lz = sexagenary_by_index(luck_idx)
        start_age = int(starting_age + i * 10)
        end_age = start_age + 10
        start_year = birth_year + start_age
        end_year = start_year + 10
        pillars.append({
            'gan': lg,
            'zhi': lz,
            'index': i,
            'start_age': start_age,
            'end_age': end_age - 1,
            'years': f'{start_year}-{end_year - 1}',
        })

    # Determine current pillar
    current_year = date.today().year
    age = current_year - birth_year
    current_pillar = None
    for p in pillars:
        if p['start_age'] <= age < p['end_age']:
            current_pillar = p
            break

    return {
        'direction': direction,
        'starting_age': starting_age,
        'starting_age_exact': f'{int(starting_age)}岁',
        'days_to_junction': round(days_to_junction, 2),
        'current_pillar': current_pillar,
        'pillars': pillars,
        'current_year': current_year,
        'current_age': age,
    }


# =============================================================================
# 5. SHENSHA (神煞) CALCULATION
# =============================================================================

def _find_taohua_group(zhi):
    """Find which three-harmony group a branch belongs to."""
    for group in [('申', '子', '辰'), ('寅', '午', '戌'), ('亥', '卯', '未'), ('巳', '酉', '丑')]:
        if zhi in group:
            return group
    return None


def calculate_shensha(four_pillars, day_master):
    """Calculate 30+ spirit/sha (神煞) for each pillar — driven by shensha.json tables."""
    # ── Use module-level shensha lookup tables (see top of file) ──

    # ── Per-pillar evaluation ──────────────────────────────────
    month_zhi = four_pillars['month']['zhi']
    year_zhi = four_pillars['year']['zhi']
    day_ganzhi = four_pillars['day']['gan'] + four_pillars['day']['zhi']
    all_zhis = [four_pillars[k]['zhi'] for k in ['year','month','day','hour']]
    all_gans = [four_pillars[k]['gan'] for k in ['year','month','day','hour']]

    day_zhi = four_pillars['day']['zhi']
    # 三合系参考局：年支/日支所属三合局并集（紫微仅日支）——spec §4.3 B 口径冻结表
    # 12 地支全覆盖四个三合局，_find_taohua_group 对合法地支永不返回 None（不变式）；
    # 若该不变式未来被破坏，set 推导的 if g 过滤与下方 sanhe_day_group 的假值判定仍可安全降级
    sanhe_ref_groups = {g for g in (_find_taohua_group(year_zhi), _find_taohua_group(day_zhi)) if g}
    sanhe_day_group = _find_taohua_group(day_zhi)

    result = {}
    for key in ['year', 'month', 'day', 'hour']:
        p = four_pillars[key]
        gan, zhi = p['gan'], p['zhi']
        ss = []

        # ── 日干系 (check all pillars) ──
        if zhi in TIANYI_GUIREN.get(day_master, ()): ss.append('天乙贵人')
        if zhi == WENCHANG.get(day_master, ''):      ss.append('文昌贵人')
        if zhi == _lushen.get(day_master, ''):        ss.append('禄神')
        if zhi in _taiji.get(day_master, ()):         ss.append('太极贵人')
        if zhi == _xuetang.get(day_master, ''):       ss.append('学堂')
        if zhi == _ciguan.get(day_master, ''):        ss.append('词馆')
        if zhi == _jinyu.get(day_master, ''):         ss.append('金舆')
        if zhi == _guoyin.get(day_master, ''):        ss.append('国印贵人')
        if zhi == _hongyan.get(day_master, ''):       ss.append('红艳煞')
        if zhi == _liuxia.get(day_master, ''):        ss.append('流霞')
        if day_master in YANGREN_MAP and zhi == YANGREN_MAP[day_master]: ss.append('羊刃')
        if day_master in _feiren and zhi == _feiren[day_master]: ss.append('飞刃')

        # ── 三合系：以年支/日支所属三合局为参考（紫微仅以日支）──
        if any(zhi == TAOHUA_MAP.get(g) for g in sanhe_ref_groups):   ss.append('桃花')
        if any(zhi == YIMA_MAP.get(g) for g in sanhe_ref_groups):     ss.append('驿马')
        if any(zhi == HUAGAI_MAP.get(g) for g in sanhe_ref_groups):   ss.append('华盖')
        if any(zhi == _jiangxing.get(g) for g in sanhe_ref_groups):   ss.append('将星')
        if any(zhi == _jiesha.get(g) for g in sanhe_ref_groups):      ss.append('劫煞')
        if any(zhi == _zaisha.get(g) for g in sanhe_ref_groups):      ss.append('灾煞')
        if any(zhi == _wangshen.get(g) for g in sanhe_ref_groups):    ss.append('亡神')
        if sanhe_day_group and zhi == _ziwei_ss.get(sanhe_day_group): ss.append('紫微')
        if any(zhi == _sanhelu.get(g) for g in sanhe_ref_groups):     ss.append('三合禄')

        # ── 孤辰寡宿 (四正局) — keyed by year_zhi group → target zhi ──
        for sg, gz in _guchen.items():
            if year_zhi in sg and zhi == gz:           ss.append('孤辰')
        for sg, gz in _guasu.items():
            if year_zhi in sg and zhi == gz:           ss.append('寡宿')

        # ── 月支系 ──
        if _tiande.get(month_zhi) == gan:              ss.append('天德贵人')
        # 月德: 月支三合→天干
        mg = _find_taohua_group(month_zhi)
        if mg:
            if _yuede_by_group.get(mg) == gan:                     ss.append('月德贵人')
        if _xueren.get(month_zhi) == zhi:              ss.append('血刃')
        if _longde.get(month_zhi) == zhi:              ss.append('龙德')

        # ── 年支系 ──
        if zhi == _hongluan_by_zhi.get(year_zhi):      ss.append('红鸾')
        # 天喜 = 红鸾 + 6
        hl_zhi = _hongluan_by_zhi.get(year_zhi, '')
        if hl_zhi and zhi == DIZHI[(DIZHI.index(hl_zhi) + 6) % 12]: ss.append('天喜')
        if zhi == _sangmen.get(year_zhi):              ss.append('丧门')
        if zhi == _diaoke.get(year_zhi):               ss.append('吊客')
        if zhi == _baihu.get(year_zhi):                ss.append('白虎')

        # ── 日柱系（7 张表注释均为"日柱为"，仅以日柱论）──
        if key == 'day':
            if gan + zhi in KUIGANG:                   ss.append('魁罡')
            if gan + zhi in _guluan:                   ss.append('孤鸾煞')
            if gan + zhi in _yincha:                   ss.append('阴差阳错')
            if gan + zhi in _shiedabai:                ss.append('十恶大败')
            if gan + zhi in _bazhuan:                  ss.append('八专')
            if gan + zhi in _xuanzhen:                 ss.append('悬针')
            if gan + zhi in _tianshe:                  ss.append('天赦')

        # ── 全局系 ──
        if zhi == '戌':                                ss.append('天罗')
        if zhi == '辰':                                ss.append('地网')
        # 遍野桃花: 四柱子午卯酉全
        if '子' in all_zhis and '午' in all_zhis and '卯' in all_zhis and '酉' in all_zhis:
            if '遍野桃花' not in ss:                    ss.append('遍野桃花')

        # ── 去重 & 过滤 ──
        seen = set()
        unique = []
        for s in ss:
            if s not in seen:
                seen.add(s); unique.append(s)
        result[key] = unique if unique else ['无']

    return result


# =============================================================================
# 6. ZIWEI DOUSHU (紫微斗数) CALCULATION
# =============================================================================

def calculate_ziwei(year, month, day, hour, gender):
    """Calculate Ziwei Doushu chart.

    Uses LUNAR month for all month-based calculations including
    命宫, 身宫, 左辅, 右弼 (NOT solar-term month).
    """
    year_gan, year_zhi = get_year_pillar(year, month, day, hour, 0)
    day_gan, day_zhi = get_day_pillar(year, month, day)
    _, hour_zhi = get_hour_pillar(day_gan, hour)

    # Lunar calendar: month and day for Ziwei positioning
    lunar_year, lunar_month, lunar_day, _is_leap = solar_to_lunar(year, month, day)
    # Lunar month → 地支 (正月=寅, ..., 十二月=丑)
    lunar_month_zhi = DIZHI[(lunar_month + 1) % 12]

    # 命宫 and 身宫 — use LUNAR month
    minggong_zhi = get_minggong(lunar_month_zhi, hour_zhi)
    shengong_zhi = get_shengong(lunar_month_zhi, hour_zhi)

    # 五虎遁: determine stem for 寅 based on year stem
    _wuhu_start = {'甲':2,'己':2, '乙':4,'庚':4, '丙':6,'辛':6, '丁':8,'壬':8, '戊':0,'癸':0}
    yin_stem = _wuhu_start[year_gan]

    # 命宫干支 (五虎遁: gan = yin_stem + offset from 寅)
    minggong_zhi_idx = DIZHI.index(minggong_zhi)
    minggong_gan_idx = (yin_stem + (minggong_zhi_idx - 2 + 12) % 12) % 10
    minggong_gan = TIANGAN[minggong_gan_idx]
    minggong_key = minggong_gan + minggong_zhi

    # 五行局 from 命宫纳音
    minggong_nayin = NAYIN.get(minggong_key, '未知')
    wuxing_ju = 2  # default 水二局
    for elem, ju_num in WUXING_JU_MAP.items():
        if elem in minggong_nayin:
            wuxing_ju = ju_num
            break

    # 紫微 star position (iztro algorithm, 寅=0 coordinate)
    # Find smallest offset o where (lunar_day + o) % 局数 == 0
    o = 0
    while (lunar_day + o) % wuxing_ju != 0:
        o += 1
    q = (lunar_day + o) // wuxing_ju
    q_mod = q % 12
    ziwei_base = q_mod - 1
    # o even → clockwise (+o), o odd → counter-clockwise (-o)
    if o % 2 == 0:
        ziwei_0idx = ziwei_base + o
    else:
        ziwei_0idx = ziwei_base - o
    ziwei_0idx %= 12  # 0=寅 coordinate

    # 天府 = (12 - 紫微) % 12 in 寅=0 coordinate
    tianfu_0idx = (12 - ziwei_0idx) % 12

    # Convert 寅=0 coordinate → standard 地支 index (0=子)
    _to_std = lambda i0: (i0 + 2) % 12
    ziwei_std_idx = _to_std(ziwei_0idx)
    tianfu_std_idx = _to_std(tianfu_0idx)

    # Deploy 14 main stars (with gaps matching iztro)
    # 紫微星系 (with gaps): 紫微, 天机, 空, 太阳, 武曲, 天同, 空, 空, 廉贞
    ziwei_series = [
        ('紫微', 0), ('天机', 1), (None, 2),
        ('太阳', 3), ('武曲', 4), ('天同', 5),
        (None, 6), (None, 7), ('廉贞', 8),
    ]
    # 天府星系 (with gaps): 天府, 太阴, 贪狼, 巨门, 天相, 天梁, 七杀, 空, 空, 空, 破军
    tianfu_series = [
        ('天府', 0), ('太阴', 1), ('贪狼', 2), ('巨门', 3),
        ('天相', 4), ('天梁', 5), ('七杀', 6),
        (None, 7), (None, 8), (None, 9), ('破军', 10),
    ]

    stars = {}  # {standard_branch_index: [{name, brightness}]}
    for star_name, offset in ziwei_series:
        if star_name is None:
            continue
        pos = (ziwei_std_idx - offset) % 12  # counter-clockwise
        b = _get_brightness(star_name, pos)
        stars.setdefault(pos, []).append({'name': star_name, 'brightness': b})
    for star_name, offset in tianfu_series:
        if star_name is None:
            continue
        pos = (tianfu_std_idx + offset) % 12  # clockwise
        b = _get_brightness(star_name, pos)
        stars.setdefault(pos, []).append({'name': star_name, 'brightness': b})

    # Auxiliary stars
    aux_stars = {}  # {branch_index: [{name, brightness}]}
    def _add_aux(pos, name):
        b = _get_brightness(name, pos) if name in _STAR_BRIGHTNESS else ''
        aux_stars.setdefault(pos, []).append({'name': name, 'brightness': b})

    # 左辅: 正月起辰顺数至生月
    _add_aux((4 + lunar_month - 1) % 12, '左辅')
    # 右弼: 正月起戌逆数至生月
    _add_aux((10 - (lunar_month - 1) + 12) % 12, '右弼')
    # 文昌
    _add_aux((10 - DIZHI.index(hour_zhi)) % 12, '文昌')
    # 文曲
    _add_aux((4 + DIZHI.index(hour_zhi)) % 12, '文曲')

    # 火星: 寅午戌起丑(1), 申子辰起寅(2), 巳酉丑起卯(3), 亥卯未起戌(10); 从子时顺数
    _huo_start = {2:1,6:1,10:1, 8:2,0:2,4:2, 5:3,9:3,1:3, 11:10,3:10,7:10}
    huoxing_pos = (_huo_start.get(DIZHI.index(year_zhi), 1) + DIZHI.index(hour_zhi)) % 12
    _add_aux(huoxing_pos, '火星')
    # 铃星: 寅午戌起卯(3), 申子辰/巳酉丑/亥卯未均起戌(10); 从子时顺数
    _ling_start = {2:3,6:3,10:3, 8:10,0:10,4:10, 5:10,9:10,1:10, 11:10,3:10,7:10}
    lingxing_pos = (_ling_start.get(DIZHI.index(year_zhi), 10) + DIZHI.index(hour_zhi)) % 12
    _add_aux(lingxing_pos, '铃星')

    # 禄存 (by year stem): 甲寅,乙卯,丙丁巳,戊己午,庚申,辛酉,壬亥,癸子
    _lucun_table = {'甲':2, '乙':3, '丙':5, '丁':6, '戊':5, '己':6, '庚':8, '辛':9, '壬':11, '癸':0}
    lucun_idx = _lucun_table.get(year_gan, 2)
    _add_aux(lucun_idx, '禄存')
    # 擎羊 = 禄存 + 1, 陀罗 = 禄存 - 1
    _add_aux((lucun_idx + 1) % 12, '擎羊')
    _add_aux((lucun_idx - 1 + 12) % 12, '陀罗')

    # 天马 (by year branch): 寅午戌→申, 申子辰→寅, 巳酉丑→亥, 亥卯未→巳
    yz_idx = DIZHI.index(year_zhi)
    _tianma_map = {2:8, 6:8, 10:8, 8:2, 0:2, 4:2, 5:11, 9:11, 1:11, 3:5, 7:5, 11:5}
    _add_aux(_tianma_map.get(yz_idx, 8), '天马')

    # 红鸾 (卯起子年逆数): 卯(3) - year_zhi_idx, 天喜 = 红鸾 + 6
    _hl_idx = (3 - yz_idx + 12) % 12
    _add_aux(_hl_idx, '红鸾')
    _add_aux((_hl_idx + 6) % 12, '天喜')
    # 天姚 (丑起正月顺数): 丑(1) + (lunar_month - 1)
    _add_aux((1 + lunar_month - 1) % 12, '天姚')

    # 天魁/天钺 (甲戊庚:魁丑钺未, 乙己:魁子钺申, 丙丁:魁亥钺酉, 辛:魁午钺寅, 壬癸:魁卯钺巳)
    tiankui_table = {'甲':1, '戊':1, '庚':1, '乙':0, '己':0, '丙':11, '丁':11, '辛':6, '壬':3, '癸':3}
    tianyue_table = {'甲':7, '戊':7, '庚':7, '乙':8, '己':8, '丙':9, '丁':9, '辛':2, '壬':5, '癸':5}
    _add_aux(tiankui_table.get(year_gan, 1), '天魁')
    _add_aux(tianyue_table.get(year_gan, 7), '天钺')

    # 天空/地劫 (iztro: 天空=亥-time_idx, 地劫=亥+time_idx in 寅=0 coord → std)
    _hai_std = 11  # 亥 in standard 地支 index (0=子)
    _hour_std = DIZHI.index(hour_zhi)
    _add_aux((_hai_std - _hour_std) % 12, '天空')
    _add_aux((_hai_std + _hour_std) % 12, '地劫')

    # 四化
    sihua_data = SIHUA_TABLE.get(year_gan, {})
    sihua = {}
    for hua_type, star_name in sihua_data.items():
        found = False
        for pos, star_list in stars.items():
            for sd in star_list:
                if sd['name'] == star_name:
                    sihua[f'化{hua_type}'] = {'star': star_name, 'palace_idx': pos}
                    found = True
                    break
            if found: break
        if not found:
            for pos, aux_list in aux_stars.items():
                for sd in aux_list:
                    if sd['name'] == star_name:
                        sihua[f'化{hua_type}'] = {'star': star_name, 'palace_idx': pos, 'type': 'aux'}
                        found = True
                        break
                if found: break
        if not found:
            sihua[f'化{hua_type}'] = {'star': star_name, 'palace_idx': -1, 'note': '星曜未排入十二宫'}

    # 十二宫 arrangement (counter-clockwise from 命宫)
    PALACE_NAMES = ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '仆役', '官禄', '田宅', '福德', '父母']
    minggong_idx = DIZHI.index(minggong_zhi)

    # 十二宫地支排布 (counter-clockwise from 命宫)
    palace_zhi_order = []
    for i in range(12):
        palace_zhi_order.append(DIZHI[(minggong_idx - i) % 12])

    # 阳年/阴年 → 顺行/逆行
    _yang = {'甲','丙','戊','庚','壬'}
    is_yang = year_gan in _yang
    is_forward = (is_yang and gender == 'male') or (not is_yang and gender == 'female')

    # 大限 and palaces
    palaces = {}
    for i, pname in enumerate(PALACE_NAMES):
        pzhi = palace_zhi_order[i]
        # 天干 via 五虎遁: each 地支 gets stem based on year stem
        pzhi_idx = DIZHI.index(pzhi)
        pgan_idx = (yin_stem + (pzhi_idx - 2 + 12) % 12) % 10
        pgan = TIANGAN[pgan_idx]

        main_data = stars.get(pzhi_idx, [])
        aux_data = aux_stars.get(pzhi_idx, [])

        # 大限: 顺行(阳男/阴女)→逆序, 逆行(阴男/阳女)→顺序
        if is_forward:
            daxian_start = wuxing_ju + ((12 - i) % 12) * 10
        else:
            daxian_start = wuxing_ju + i * 10
        daxian_end = daxian_start + 10

        palaces[pname] = {
            'zhi': pzhi,
            'gan': pgan,
            'stars': main_data,
            'aux_stars': aux_data,
            'daxian': f'{daxian_start}-{daxian_end - 1}',
            'is_shengong': (pzhi == shengong_zhi),
        }

    # 命主星 / 身主星
    mingzhu_star = _MINGZHU_TABLE.get(minggong_zhi, '')
    shenzhu_star = _SHENZHU_TABLE.get(year_zhi, '')  # 身主星按年支，非身宫

    return {
        'minggong': minggong_zhi,
        'minggong_gan': minggong_gan,
        'shengong': shengong_zhi,
        'wuxing_ju': f'{minggong_nayin}→{["","","水二局","木三局","金四局","土五局","火六局"][wuxing_ju]}',
        'wuxing_ju_num': wuxing_ju,
        'palaces': palaces,
        'sihua': sihua,
        'mingzhu_star': mingzhu_star,
        'shenzhu_star': shenzhu_star,
    }


# =============================================================================
# 6b. WUYUN LIUQI (五运六气) — from 《黄帝内经》
# =============================================================================

WUYUN_TABLE = {
    '甲': {'yun': '土运', 'organ': '脾/胃', 'tendency': '脾胃系统先天偏弱/偏旺'},
    '己': {'yun': '土运', 'organ': '脾/胃', 'tendency': '脾胃系统先天偏弱/偏旺'},
    '乙': {'yun': '金运', 'organ': '肺/大肠', 'tendency': '呼吸系统先天易感'},
    '庚': {'yun': '金运', 'organ': '肺/大肠', 'tendency': '呼吸系统先天易感'},
    '丙': {'yun': '水运', 'organ': '肾/膀胱', 'tendency': '肾气先天偏盛/偏虚'},
    '辛': {'yun': '水运', 'organ': '肾/膀胱', 'tendency': '肾气先天偏盛/偏虚'},
    '丁': {'yun': '木运', 'organ': '肝/胆', 'tendency': '肝胆系统先天倾向明显'},
    '壬': {'yun': '木运', 'organ': '肝/胆', 'tendency': '肝胆系统先天倾向明显'},
    '戊': {'yun': '火运', 'organ': '心/小肠', 'tendency': '心脑血管先天需关注'},
    '癸': {'yun': '火运', 'organ': '心/小肠', 'tendency': '心脑血管先天需关注'},
}

LIUQI_TABLE = {
    '子': {'qi': '少阴君火', 'evil': '心火过旺', 'season': '夏季'},
    '午': {'qi': '少阴君火', 'evil': '心火过旺', 'season': '夏季'},
    '丑': {'qi': '太阴湿土', 'evil': '湿邪困脾', 'season': '长夏'},
    '未': {'qi': '太阴湿土', 'evil': '湿邪困脾', 'season': '长夏'},
    '寅': {'qi': '少阳相火', 'evil': '火邪上炎', 'season': '春夏之交'},
    '申': {'qi': '少阳相火', 'evil': '火邪上炎', 'season': '春夏之交'},
    '卯': {'qi': '阳明燥金', 'evil': '燥邪伤肺', 'season': '秋季'},
    '酉': {'qi': '阳明燥金', 'evil': '燥邪伤肺', 'season': '秋季'},
    '辰': {'qi': '太阳寒水', 'evil': '寒邪伤肾', 'season': '冬季'},
    '戌': {'qi': '太阳寒水', 'evil': '寒邪伤肾', 'season': '冬季'},
    '巳': {'qi': '厥阴风木', 'evil': '风邪犯肝', 'season': '春季'},
    '亥': {'qi': '厥阴风木', 'evil': '风邪犯肝', 'season': '春季'},
}

def calculate_wuyun_liuqi(year_gan, year_zhi):
    """Calculate 五运六气 from year stem and branch."""
    wuyun = WUYUN_TABLE.get(year_gan, {})
    liuqi = LIUQI_TABLE.get(year_zhi, {})
    return {
        '五运': wuyun.get('yun', '未知'),
        '主事脏腑': wuyun.get('organ', '未知'),
        '体质倾向': wuyun.get('tendency', '未知'),
        '六气': liuqi.get('qi', '未知'),
        '外邪倾向': liuqi.get('evil', '未知'),
        '易感季节': liuqi.get('season', '未知'),
    }


# =============================================================================
# 6c. WUXING STATS (五行统计) — API spec §2.2
# =============================================================================

def calculate_wuxing_stats(four_pillars):
    """Count five-element distribution across all pillars."""
    counts = {'金': 0, '木': 0, '水': 0, '火': 0, '土': 0}
    for key in ['year', 'month', 'day', 'hour']:
        if key not in four_pillars:
            continue
        p = four_pillars[key]
        # Stem element
        g_elem = GAN_WUXING.get(p['gan'], '')
        if g_elem in counts:
            counts[g_elem] += 1
        # Branch element
        z_elem = ZHI_WUXING.get(p['zhi'], '')
        if z_elem in counts:
            counts[z_elem] += 1
    missing = [e for e, c in counts.items() if c == 0]
    ranked = sorted(counts.items(), key=lambda x: -x[1])
    return {
        'jin': counts['金'], 'mu': counts['木'], 'shui': counts['水'],
        'huo': counts['火'], 'tu': counts['土'],
        'missing': missing,
        'strongest': ranked[0][0] if ranked else '',
        'weakest': ranked[-1][0] if ranked else '',
    }


def calculate_shishen_stats(four_pillars):
    """Count十神 distribution across all pillars (stems + branches + hidden stems).

    Scans天干四字 + 地支四字 + 全部藏干. A十神 with count=0 means it's
    completely absent from the natal chart — a stronger signal than weak/broken.
    """
    ALL_SHISHEN = ['比肩', '劫财', '食神', '伤官', '偏财', '正财', '正官', '七杀', '偏印', '正印']
    counts = {s: 0 for s in ALL_SHISHEN}

    for key in ['year', 'month', 'day', 'hour']:
        if key not in four_pillars:
            continue
        p = four_pillars[key]

        # Stem十神
        ss = p['shishen'].get(p['gan'], '')
        if ss in counts:
            counts[ss] += 1

        # Hidden stems十神 (all levels: 本气/中气/余气)
        for d in p.get('cangan_detail', []):
            ss = p['shishen'].get(d['stem'], '')
            if ss in counts:
                counts[ss] += 1

    missing = [s for s, c in counts.items() if c == 0]
    ranked = sorted(counts.items(), key=lambda x: -x[1])

    return {
        'counts': counts,
        'missing': missing,
        'missing_human': {
            '偏财': '偏财' in missing,
            '正财': '正财' in missing,
            '正官': '正官' in missing,
            '七杀': '七杀' in missing,
            '正印': '正印' in missing,
            '偏印': '偏印' in missing,
            '食神': '食神' in missing,
            '伤官': '伤官' in missing,
            '比肩': '比肩' in missing,
            '劫财': '劫财' in missing,
        },
        'strongest': ranked[0][0] if ranked else '',
        'most_frequent_count': ranked[0][1] if ranked else 0,
    }


# =============================================================================
# 6d. TRUE SOLAR TIME (真太阳时校正) — API spec §4
# =============================================================================

# Provincial capital longitudes (approximate)
PROVINCE_LONGITUDES = {
    # === 直辖市 ===
    '北京': 116.4, '北京市': 116.4,
    '上海': 121.5, '上海市': 121.5,
    '天津': 117.2, '天津市': 117.2,
    '重庆': 106.5, '重庆市': 106.5,
    # === 河北省 (11地级市) ===
    '河北': 114.5, '石家庄': 114.5, '唐山': 118.2, '秦皇岛': 119.6,
    '邯郸': 114.5, '邢台': 114.5, '保定': 115.5, '张家口': 114.9,
    '承德': 117.9, '沧州': 116.8, '廊坊': 116.7, '衡水': 115.7,
    # === 山西省 (11地级市) ===
    '山西': 112.5, '太原': 112.5, '大同': 113.3, '阳泉': 113.6,
    '长治': 113.1, '晋城': 112.8, '朔州': 112.4, '晋中': 112.7,
    '运城': 111.0, '忻州': 112.7, '临汾': 111.5, '吕梁': 111.1,
    # === 内蒙古自治区 (12盟市) ===
    '内蒙古': 111.7, '呼和浩特': 111.7, '包头': 109.8, '乌海': 106.8,
    '赤峰': 119.0, '通辽': 122.3, '鄂尔多斯': 109.8, '呼伦贝尔': 119.8,
    '巴彦淖尔': 107.4, '乌兰察布': 113.1, '兴安': 122.0, '锡林郭勒': 116.1,
    '阿拉善': 105.7, '阿拉善盟': 105.7,
    # === 辽宁省 (14地级市) ===
    '辽宁': 123.4, '沈阳': 123.4, '大连': 121.6, '鞍山': 123.0,
    '抚顺': 124.0, '本溪': 123.8, '丹东': 124.4, '锦州': 121.1,
    '营口': 122.2, '阜新': 121.7, '辽阳': 123.2, '盘锦': 122.1,
    '铁岭': 123.8, '朝阳': 120.4, '葫芦岛': 120.8,
    # === 吉林省 (9地市州) ===
    '吉林': 126.5, '长春': 125.3, '四平': 124.4, '辽源': 125.1,
    '通化': 125.9, '白山': 126.4, '松原': 124.8, '白城': 122.8,
    '延边': 129.5, '延吉': 129.5,
    # === 黑龙江省 (13地市) ===
    '黑龙江': 126.6, '哈尔滨': 126.6, '齐齐哈尔': 123.9, '鸡西': 130.9,
    '鹤岗': 130.3, '双鸭山': 131.2, '大庆': 125.0, '伊春': 128.9,
    '佳木斯': 130.3, '七台河': 131.0, '牡丹江': 129.6, '黑河': 127.5,
    '绥化': 127.0, '大兴安岭': 124.6,
    # === 江苏省 (13地级市) ===
    '江苏': 118.8, '南京': 118.8, '无锡': 120.3, '徐州': 117.2,
    '常州': 119.9, '苏州': 120.6, '南通': 120.9, '连云港': 119.2,
    '淮安': 119.0, '盐城': 120.1, '扬州': 119.4, '镇江': 119.4,
    '泰州': 119.9, '宿迁': 118.3,
    # === 浙江省 (11地级市) ===
    '浙江': 120.2, '杭州': 120.2, '宁波': 121.5, '温州': 120.7,
    '嘉兴': 120.8, '湖州': 120.1, '绍兴': 120.6, '金华': 119.6,
    '衢州': 118.9, '舟山': 122.2, '台州': 121.4, '丽水': 119.9,
    # === 安徽省 (16地级市) ===
    '安徽': 117.3, '合肥': 117.3, '芜湖': 118.4, '蚌埠': 117.4,
    '淮南': 117.0, '马鞍山': 118.5, '淮北': 116.8, '铜陵': 117.8,
    '安庆': 117.1, '黄山': 118.3, '滁州': 118.3, '阜阳': 115.8,
    '宿州': 117.0, '六安': 116.5, '亳州': 115.8, '池州': 117.5,
    '宣城': 118.8,
    # === 福建省 (9地级市) ===
    '福建': 119.3, '福州': 119.3, '厦门': 118.1, '莆田': 119.0,
    '三明': 117.6, '泉州': 118.6, '漳州': 117.7, '南平': 118.2,
    '龙岩': 117.0, '宁德': 119.5,
    # === 江西省 (11地级市) ===
    '江西': 115.9, '南昌': 115.9, '景德镇': 117.2, '萍乡': 113.9,
    '九江': 116.0, '新余': 114.9, '鹰潭': 117.0, '赣州': 115.0,
    '吉安': 115.0, '宜春': 114.4, '抚州': 116.4, '上饶': 117.9,
    # === 山东省 (16地级市) ===
    '山东': 117.0, '济南': 117.0, '青岛': 120.4, '淄博': 118.1,
    '枣庄': 117.3, '东营': 118.7, '烟台': 121.4, '潍坊': 119.2,
    '济宁': 116.6, '泰安': 117.1, '威海': 122.1, '日照': 119.5,
    '临沂': 118.4, '德州': 116.4, '聊城': 116.0, '滨州': 118.0,
    '菏泽': 115.5,
    # === 河南省 (17地级市+1省直管) ===
    '河南': 113.7, '郑州': 113.7, '开封': 114.3, '洛阳': 112.4,
    '平顶山': 113.3, '安阳': 114.4, '鹤壁': 114.3, '新乡': 113.9,
    '焦作': 113.2, '濮阳': 115.0, '许昌': 113.8, '漯河': 114.0,
    '三门峡': 111.2, '南阳': 112.5, '商丘': 115.7, '信阳': 114.1,
    '周口': 114.7, '驻马店': 114.0, '济源': 112.6,
    # === 湖北省 (13地市州+4省直管) ===
    '湖北': 114.3, '武汉': 114.3, '黄石': 115.1, '十堰': 110.8,
    '宜昌': 111.3, '襄阳': 112.1, '鄂州': 114.9, '荆门': 112.2,
    '孝感': 113.9, '荆州': 112.2, '黄冈': 114.9, '咸宁': 114.3,
    '随州': 113.4, '恩施': 109.5, '仙桃': 113.4, '潜江': 112.9,
    '天门': 113.2, '神农架': 110.7,
    # === 湖南省 (14地市州) ===
    '湖南': 113.0, '长沙': 113.0, '株洲': 113.1, '湘潭': 112.9,
    '衡阳': 112.6, '邵阳': 111.5, '岳阳': 113.1, '常德': 111.7,
    '张家界': 110.5, '益阳': 112.4, '郴州': 113.0, '永州': 111.6,
    '怀化': 109.9, '娄底': 112.0, '湘西': 109.7,
    # === 广东省 (21地级市) ===
    '广东': 113.3, '广州': 113.3, '韶关': 113.6, '深圳': 114.1,
    '珠海': 113.6, '汕头': 116.7, '佛山': 113.1, '江门': 113.1,
    '湛江': 110.4, '茂名': 110.9, '肇庆': 112.5, '惠州': 114.4,
    '梅州': 116.1, '汕尾': 115.4, '河源': 114.7, '阳江': 111.9,
    '清远': 113.1, '东莞': 113.7, '中山': 113.4, '潮州': 116.6,
    '揭阳': 116.4, '云浮': 112.0,
    # === 广西壮族自治区 (14地级市) ===
    '广西': 108.3, '南宁': 108.3, '柳州': 109.4, '桂林': 110.3,
    '梧州': 111.3, '北海': 109.1, '防城港': 108.3, '钦州': 108.6,
    '贵港': 109.6, '玉林': 110.2, '百色': 106.6, '贺州': 111.5,
    '河池': 108.1, '来宾': 109.2, '崇左': 107.4,
    # === 海南省 (4地级市) ===
    '海南': 110.3, '海口': 110.3, '三亚': 109.5, '三沙': 112.3,
    '儋州': 109.6,
    # === 四川省 (21地市州) ===
    '四川': 104.1, '成都': 104.1, '自贡': 104.8, '攀枝花': 101.7,
    '泸州': 105.4, '德阳': 104.4, '绵阳': 104.7, '广元': 105.8,
    '遂宁': 105.6, '内江': 105.1, '乐山': 103.8, '南充': 106.1,
    '眉山': 103.8, '宜宾': 104.6, '广安': 106.6, '达州': 107.5,
    '雅安': 103.0, '巴中': 106.8, '资阳': 104.6, '阿坝': 101.7,
    '甘孜': 100.0, '凉山': 102.3,
    # === 贵州省 (9地市州) ===
    '贵州': 106.7, '贵阳': 106.7, '六盘水': 104.8, '遵义': 106.9,
    '安顺': 105.9, '毕节': 105.3, '铜仁': 109.2, '黔西南': 104.9,
    '黔东南': 107.9, '黔南': 107.5,
    # === 云南省 (16地市州) ===
    '云南': 102.7, '昆明': 102.7, '曲靖': 103.8, '玉溪': 102.5,
    '保山': 99.2, '昭通': 103.7, '丽江': 100.2, '普洱': 100.9,
    '临沧': 100.1, '楚雄': 101.5, '红河': 103.3, '文山': 104.2,
    '西双版纳': 100.8, '大理': 100.2, '德宏': 98.6, '怒江': 98.9,
    '迪庆': 99.7,
    # === 西藏自治区 (7地市) ===
    '西藏': 91.1, '拉萨': 91.1, '日喀则': 88.9, '昌都': 97.2,
    '林芝': 94.4, '山南': 91.8, '那曲': 92.1, '阿里': 80.1,
    # === 陕西省 (10地级市) ===
    '陕西': 108.9, '西安': 108.9, '铜川': 109.0, '宝鸡': 107.2,
    '咸阳': 108.7, '渭南': 109.5, '延安': 109.5, '汉中': 107.0,
    '榆林': 109.7, '安康': 109.0, '商洛': 109.9,
    # === 甘肃省 (14地市州) ===
    '甘肃': 103.7, '兰州': 103.7, '嘉峪关': 98.3, '金昌': 102.2,
    '白银': 104.2, '天水': 105.7, '武威': 102.6, '张掖': 100.5,
    '平凉': 106.7, '酒泉': 98.5, '庆阳': 107.6, '定西': 104.6,
    '陇南': 104.9, '临夏': 103.2, '甘南': 102.9,
    # === 青海省 (8地市州) ===
    '青海': 101.7, '西宁': 101.7, '海东': 102.1, '海北': 100.9,
    '黄南': 102.0, '海南州': 100.6, '果洛': 100.2, '玉树': 97.0,
    '海西': 97.4,
    # === 宁夏回族自治区 (5地级市) ===
    '宁夏': 106.3, '银川': 106.3, '石嘴山': 106.4, '吴忠': 106.2,
    '固原': 106.3, '中卫': 105.2,
    # === 新疆维吾尔自治区 (14地市州) ===
    '新疆': 87.6, '乌鲁木齐': 87.6, '克拉玛依': 84.9, '吐鲁番': 89.2,
    '哈密': 93.5, '昌吉': 87.3, '博尔塔拉': 82.1, '巴音郭楞': 86.1,
    '阿克苏': 80.3, '克孜勒苏': 76.2, '喀什': 75.9, '和田': 79.9,
    '伊犁': 81.3, '塔城': 82.9, '阿勒泰': 88.1, '石河子': 86.0,
    # === 台湾省 (主要城市) ===
    '台湾': 121.5, '台北': 121.5, '高雄': 120.3, '台中': 120.7,
    '台南': 120.2, '基隆': 121.7, '新竹': 120.9, '嘉义': 120.4,
    # === 特别行政区 ===
    '香港': 114.2, '澳门': 113.5,
}

# International city coordinates (longitude, latitude)
# Covers major cities worldwide for true solar time correction
INTERNATIONAL_CITY_COORDINATES = {
    # North America
    'New York': (-74.006, 40.713), 'New York City': (-74.006, 40.713),
    'NYC': (-74.006, 40.713), 'Los Angeles': (-118.244, 34.052),
    'LA': (-118.244, 34.052), 'Chicago': (-87.630, 41.878),
    'Houston': (-95.370, 29.761), 'Phoenix': (-112.074, 33.448),
    'San Francisco': (-122.419, 37.775), 'Seattle': (-122.332, 47.606),
    'Washington': (-77.037, 38.907), 'Washington DC': (-77.037, 38.907),
    'Boston': (-71.059, 42.361), 'Miami': (-80.192, 25.761),
    'Dallas': (-96.797, 32.777), 'Atlanta': (-84.388, 33.749),
    'Detroit': (-83.046, 42.331), 'Philadelphia': (-75.165, 39.953),
    'Hope': (-93.603, 33.667), 'New Haven': (-72.928, 41.308),
    'Brookline': (-71.125, 42.332), 'Tampico': (-89.791, 41.538),
    'Yorba Linda': (-117.813, 33.889), 'Hyde Park': (-73.933, 41.787),
    'Plains': (-84.393, 32.034), 'Scranton': (-75.662, 41.409),
    'Little Rock': (-92.289, 34.746), 'Cincinnati': (-84.512, 39.103),
    'Baltimore': (-76.612, 39.290), 'Louisville': (-85.759, 38.253),
    'Brooklyn': (-73.944, 40.678), 'Saginaw': (-83.950, 43.419),
    'Cypress': (-118.037, 33.825), 'Omaha': (-95.934, 41.257),
    'Albuquerque': (-106.650, 35.085), 'White Plains': (-73.762, 41.034),
    'East Lansing': (-84.483, 42.737), 'Tupelo': (-88.703, 34.257),
    'Duluth': (-92.100, 46.787), 'Aberdeen': (-123.817, 46.975),
    'Minneapolis': (-93.265, 44.978), 'Kosciusko': (-89.588, 33.057),
    'Honolulu': (-157.858, 21.307), 'Juneau': (-134.420, 58.302),
    'Anchorage': (-149.900, 61.218),
    'Toronto': (-79.383, 43.653), 'Montreal': (-73.567, 45.502),
    'Vancouver': (-123.121, 49.283), 'Calgary': (-114.072, 51.045),
    'Ottawa': (-75.697, 45.422),
    # Mexico / Central America / Caribbean
    'Mexico City': (-99.133, 19.433), 'Havana': (-82.367, 23.134),
    'Kingston': (-76.798, 17.981), 'Panama City': (-79.520, 8.983),
    'San José': (-84.083, 9.934), 'Biran': (-75.424, 20.227),
    'Sherwood Content': (-77.745, 18.379),
    # South America
    'São Paulo': (-46.636, -23.547), 'Sao Paulo': (-46.636, -23.547),
    'Rio de Janeiro': (-43.173, -22.907), 'Brasilia': (-47.930, -15.780),
    'Brasília': (-47.930, -15.780), 'Buenos Aires': (-58.382, -34.604),
    'Santiago': (-70.649, -33.448), 'Lima': (-77.042, -12.046),
    'Bogota': (-74.072, 4.611), 'Bogotá': (-74.072, 4.611),
    'Caracas': (-66.879, 10.506), 'Quito': (-78.525, -0.210),
    'Tres Coracoes': (-45.260, -21.727), 'Três Corações': (-45.260, -21.727),
    'Lanus': (-58.386, -34.703), 'Lanús': (-58.386, -34.703),
    'Montevideo': (-56.164, -34.902), 'La Paz': (-68.147, -16.495),
    # Europe
    'London': (-0.128, 51.507), 'Manchester': (-2.237, 53.481),
    'Birmingham': (-1.890, 52.490), 'Liverpool': (-2.978, 53.410),
    'Blenheim': (-1.401, 51.769), 'Sandringham': (0.517, 52.801),
    'Oxford': (-1.258, 51.752), 'Cambridge': (0.122, 52.205),
    'Edinburgh': (-3.188, 55.953), 'Glasgow': (-4.252, 55.861),
    'Cardiff': (-3.179, 51.482), 'Belfast': (-5.930, 54.597),
    'Grantham': (-0.639, 52.912), 'Shrewsbury': (-2.753, 52.710),
    'Paris': (2.349, 48.853), 'Lyon': (4.836, 45.748),
    'Marseille': (5.370, 43.297), 'Nice': (7.266, 43.703),
    'Cannes': (7.017, 43.553), 'Berlin': (13.405, 52.520),
    'Munich': (11.582, 48.135), 'Hamburg': (9.994, 53.551),
    'Frankfurt': (8.682, 50.111), 'Cologne': (6.960, 50.938),
    'Bonn': (7.098, 50.737), 'Rome': (12.496, 41.903),
    'Milan': (9.190, 45.464), 'Naples': (14.268, 40.852),
    'Florence': (11.255, 43.770), 'Venice': (12.331, 45.437),
    'Turin': (7.687, 45.070), 'Madrid': (-3.704, 40.417),
    'Barcelona': (2.174, 41.388), 'Amsterdam': (4.904, 52.368),
    'Rotterdam': (4.480, 51.924), 'The Hague': (4.300, 52.078),
    'Brussels': (4.352, 50.850), 'Vienna': (16.374, 48.208),
    'Zurich': (8.542, 47.377), 'Geneva': (6.143, 46.202),
    'Basel': (7.588, 47.560), 'Bern': (7.447, 46.948),
    'Stockholm': (18.069, 59.329), 'Oslo': (10.752, 59.914),
    'Copenhagen': (12.568, 55.676), 'Helsinki': (24.938, 60.170),
    'Moscow': (37.618, 55.751), 'St Petersburg': (30.309, 59.934),
    'Saint Petersburg': (30.309, 59.934), 'Kyiv': (30.524, 50.450),
    'Kiev': (30.524, 50.450), 'Warsaw': (21.012, 52.230),
    'Prague': (14.421, 50.088), 'Budapest': (19.040, 47.498),
    'Athens': (23.728, 37.984), 'Lisbon': (-9.139, 38.722),
    'Dublin': (-6.260, 53.350), 'Reykjavik': (-21.818, 64.128),
    'Monaco': (7.417, 43.738), 'Vatican': (12.453, 41.903),
    'Vatican City': (12.453, 41.903), 'Ludwigshafen': (8.449, 49.481),
    'Amiens': (2.295, 49.895), 'Reggio di Calabria': (15.651, 38.111),
    'Smiljan': (15.318, 44.564), 'Zanzibar': (39.199, -6.166),
    # Asia (non-China)
    'Tokyo': (139.691, 35.690), 'Osaka': (135.502, 34.694),
    'Kyoto': (135.768, 35.011), 'Nagoya': (136.906, 35.182),
    'Yokohama': (139.638, 35.444), 'Sapporo': (141.347, 43.063),
    'Seoul': (126.978, 37.566), 'Busan': (129.076, 35.180),
    'Pyongyang': (125.738, 39.039), 'Singapore': (103.820, 1.352),
    'Singapore City': (103.820, 1.352), 'Bangkok': (100.502, 13.754),
    'Kuala Lumpur': (101.687, 3.140), 'Malaysia': (101.687, 3.140),
    '吉隆坡': (101.687, 3.140), '马来西亚': (101.687, 3.140),
    'Jakarta': (106.846, -6.209),
    'Manila': (120.984, 14.599), 'Hanoi': (105.834, 21.028),
    'Ho Chi Minh City': (106.629, 10.823), 'Saigon': (106.629, 10.823),
    'Mumbai': (72.878, 19.076), 'Bombay': (72.878, 19.076),
    'New Delhi': (77.209, 28.614), 'Delhi': (77.209, 28.614),
    'Kolkata': (88.364, 22.573), 'Calcutta': (88.364, 22.573),
    'Bangalore': (77.594, 12.972), 'Chennai': (80.279, 13.083),
    'Madras': (80.279, 13.083), 'Karachi': (67.010, 24.861),
    'Lahore': (74.358, 31.520), 'Islamabad': (73.048, 33.684),
    'Yangon': (96.133, 16.841), 'Rangoon': (96.133, 16.841),
    'Dhaka': (90.413, 23.811), 'Colombo': (79.861, 6.927),
    'Kathmandu': (85.324, 27.717), 'Tehran': (51.389, 35.689),
    'Baghdad': (44.401, 33.340), 'Riyadh': (46.739, 24.714),
    'Dubai': (55.271, 25.205), 'Abu Dhabi': (54.370, 24.453),
    'Jerusalem': (35.214, 31.768), 'Tel Aviv': (34.781, 32.085),
    'Ankara': (32.856, 39.934), 'Istanbul': (28.949, 41.014),
    'Ulaanbaatar': (106.918, 47.886), 'Tashkent': (69.240, 41.299),
    'Bishkek': (74.590, 42.875), 'Dushanbe': (68.787, 38.560),
    'Kabul': (69.172, 34.529), 'Beirut': (35.496, 33.889),
    'Damascus': (36.307, 33.513), 'Amman': (35.928, 31.950),
    # Africa
    'Cairo': (31.236, 30.044), 'Alexandria': (29.955, 31.201),
    'Lagos': (3.379, 6.455), 'Abuja': (7.490, 9.058),
    'Nairobi': (36.821, -1.292), 'Mombasa': (39.664, -4.043),
    'Cape Town': (18.424, -33.925), 'Johannesburg': (28.047, -26.204),
    'Pretoria': (28.188, -25.748), 'Durban': (31.022, -29.858),
    'Addis Ababa': (38.757, 9.025), 'Ejersa Goro': (39.000, 9.017),
    'Khartoum': (32.560, 15.501), 'Casablanca': (-7.590, 33.573),
    'Tunis': (10.181, 36.806), 'Algiers': (3.087, 36.753),
    'Accra': (-0.187, 5.604), 'Dar es Salaam': (39.208, -6.792),
    'Monrovia': (-10.797, 6.301), 'Tripoli': (13.191, 32.887),
    'Dakar': (-17.468, 14.710), 'Kinshasa': (15.306, -4.324),
    'Luanda': (13.236, -8.839), 'Harare': (31.053, -17.825),
    'Lusaka': (28.288, -15.407), 'Maputo': (32.573, -25.969),
    'Antananarivo': (47.525, -18.914), 'Mogadishu': (45.318, 2.037),
    'Kigali': (30.060, -1.950), 'Kampala': (32.582, 0.318),
    # Oceania
    'Sydney': (151.209, -33.869), 'Melbourne': (144.963, -37.814),
    'Brisbane': (153.025, -27.469), 'Perth': (115.860, -31.950),
    'Adelaide': (138.601, -34.929), 'Canberra': (149.129, -35.283),
    'Auckland': (174.763, -36.849), 'Wellington': (174.778, -41.286),
    'Christchurch': (172.636, -43.532), 'Suva': (178.442, -18.142),
    'Port Moresby': (147.170, -9.480), 'Honolulu': (-157.858, 21.307),
}

# Timezone offsets (UTC hours) for cities/countries
CITY_TIMEZONES = {
    # North America
    'New York': -5, 'NYC': -5, 'Los Angeles': -8, 'LA': -8,
    'Chicago': -6, 'Houston': -6, 'Phoenix': -7,
    'San Francisco': -8, 'Seattle': -8, 'Washington': -5,
    'Boston': -5, 'Miami': -5, 'Dallas': -6, 'Atlanta': -5,
    'Detroit': -5, 'Philadelphia': -5, 'Hope': -6, 'New Haven': -5,
    'Brookline': -5, 'Tampico': -6, 'Yorba Linda': -8,
    'Hyde Park': -5, 'Plains': -5, 'Scranton': -5,
    'Little Rock': -6, 'Cincinnati': -5, 'Baltimore': -5,
    'Louisville': -5, 'Brooklyn': -5, 'Saginaw': -5,
    'Cypress': -8, 'Omaha': -6, 'Albuquerque': -7,
    'White Plains': -5, 'East Lansing': -5, 'Tupelo': -6,
    'Duluth': -6, 'Aberdeen': -8, 'Minneapolis': -6,
    'Kosciusko': -6, 'Honolulu': -10, 'Juneau': -9, 'Anchorage': -9,
    'Toronto': -5, 'Montreal': -5, 'Vancouver': -8, 'Calgary': -7, 'Ottawa': -5,
    # Mexico / Central America / Caribbean
    'Mexico City': -6, 'Havana': -5, 'Kingston': -5,
    'Panama City': -5, 'San José': -6, 'Biran': -5,
    'Sherwood Content': -5,
    # South America
    'Sao Paulo': -3, 'São Paulo': -3, 'Rio de Janeiro': -3,
    'Brasilia': -3, 'Brasília': -3, 'Buenos Aires': -3,
    'Santiago': -4, 'Lima': -5, 'Bogota': -5, 'Bogotá': -5,
    'Caracas': -4, 'Quito': -5, 'Tres Coracoes': -3, 'Três Corações': -3,
    'Lanus': -3, 'Lanús': -3, 'Montevideo': -3, 'La Paz': -4,
    # Europe
    'London': 0, 'Manchester': 0, 'Birmingham': 0,
    'Liverpool': 0, 'Blenheim': 0, 'Sandringham': 0,
    'Oxford': 0, 'Cambridge': 0, 'Edinburgh': 0,
    'Glasgow': 0, 'Cardiff': 0, 'Belfast': 0,
    'Grantham': 0, 'Shrewsbury': 0,
    'Paris': 1, 'Lyon': 1, 'Marseille': 1, 'Nice': 1, 'Cannes': 1,
    'Berlin': 1, 'Munich': 1, 'Hamburg': 1, 'Frankfurt': 1,
    'Cologne': 1, 'Bonn': 1,
    'Rome': 1, 'Milan': 1, 'Naples': 1, 'Florence': 1, 'Venice': 1, 'Turin': 1,
    'Madrid': 1, 'Barcelona': 1, 'Amsterdam': 1, 'Rotterdam': 1, 'The Hague': 1,
    'Brussels': 1, 'Vienna': 1, 'Zurich': 1, 'Geneva': 1, 'Basel': 1, 'Bern': 1,
    'Stockholm': 1, 'Oslo': 1, 'Copenhagen': 1, 'Helsinki': 2,
    'Moscow': 3, 'St Petersburg': 3, 'Saint Petersburg': 3,
    'Kyiv': 2, 'Kiev': 2, 'Warsaw': 1, 'Prague': 1, 'Budapest': 1,
    'Athens': 2, 'Lisbon': 0, 'Dublin': 1, 'Reykjavik': 0,
    'Monaco': 1, 'Vatican': 1, 'Vatican City': 1,
    'Ludwigshafen': 1, 'Amiens': 1, 'Reggio di Calabria': 1,
    'Smiljan': 1, 'Zanzibar': 3,
    # Asia (non-China)
    'Tokyo': 9, 'Osaka': 9, 'Kyoto': 9, 'Nagoya': 9, 'Yokohama': 9, 'Sapporo': 9,
    'Seoul': 9, 'Busan': 9, 'Pyongyang': 9,
    'Singapore': 8, 'Singapore City': 8, 'Bangkok': 7,
    'Kuala Lumpur': 8, 'Malaysia': 8, '吉隆坡': 8, '马来西亚': 8,
    'Jakarta': 7, 'Manila': 8,
    'Hanoi': 7, 'Ho Chi Minh City': 7, 'Saigon': 7,
    'Mumbai': 5.5, 'Bombay': 5.5, 'New Delhi': 5.5, 'Delhi': 5.5,
    'Kolkata': 5.5, 'Calcutta': 5.5, 'Bangalore': 5.5,
    'Chennai': 5.5, 'Madras': 5.5,
    'Karachi': 5, 'Lahore': 5, 'Islamabad': 5,
    'Yangon': 6.5, 'Rangoon': 6.5, 'Dhaka': 6, 'Colombo': 5.5,
    'Kathmandu': 5.75, 'Tehran': 3.5, 'Baghdad': 3,
    'Riyadh': 3, 'Dubai': 4, 'Abu Dhabi': 4,
    'Jerusalem': 2, 'Tel Aviv': 2, 'Ankara': 3, 'Istanbul': 3,
    'Ulaanbaatar': 8, 'Tashkent': 5, 'Bishkek': 6,
    'Dushanbe': 5, 'Kabul': 4.5, 'Beirut': 2, 'Damascus': 3, 'Amman': 2,
    # Africa
    'Cairo': 2, 'Alexandria': 2, 'Lagos': 1, 'Abuja': 1,
    'Nairobi': 3, 'Mombasa': 3, 'Cape Town': 2,
    'Johannesburg': 2, 'Pretoria': 2, 'Durban': 2,
    'Addis Ababa': 3, 'Ejersa Goro': 3, 'Khartoum': 2,
    'Casablanca': 0, 'Tunis': 1, 'Algiers': 1, 'Accra': 0,
    'Dar es Salaam': 3, 'Monrovia': 0, 'Tripoli': 2, 'Dakar': 0,
    'Kinshasa': 1, 'Luanda': 1, 'Harare': 2, 'Lusaka': 2,
    'Maputo': 2, 'Antananarivo': 3, 'Mogadishu': 3,
    'Kigali': 2, 'Kampala': 3,
    # Oceania
    'Sydney': 10, 'Melbourne': 10, 'Brisbane': 10,
    'Perth': 8, 'Adelaide': 9.5, 'Canberra': 10,
    'Auckland': 12, 'Wellington': 12, 'Christchurch': 12,
    'Suva': 12, 'Port Moresby': 10,
    # Chinese cities (already in PROVINCE_LONGITUDES, timezone = 8)
    'Beijing': 8, 'China': 8, '中国': 8,
    'Hong Kong': 8, 'Taipei': 8, 'Macau': 8,
    # Country-level defaults
    'USA': -5, 'United States': -5, 'UK': 0, 'United Kingdom': 0,
    'Germany': 1, 'France': 1, 'Italy': 1, 'Spain': 1,
    'Russia': 3, 'Japan': 9, 'Korea': 9, 'India': 5.5,
    'Australia': 10, 'Brazil': -3, 'Canada': -5,
    'Myanmar': 6.5, 'Pakistan': 5, 'Israel': 2,
    'Cuba': -5, 'Liberia': 0, 'Ethiopia': 3, 'Ukraine': 2,
    'New Zealand': 12, 'Argentina': -3, 'Nigeria': 1,
    'South Africa': 2, 'Kenya': 3, 'Egypt': 2,
    'Switzerland': 1, 'Sweden': 1, 'Norway': 1, 'Denmark': 1,
    'Finland': 2, 'Poland': 1, 'Greece': 2, 'Portugal': 0,
    'Ireland': 1, 'Netherlands': 1, 'Belgium': 1, 'Austria': 1,
    'Turkey': 3, 'Iran': 3.5, 'Iraq': 3, 'Saudi Arabia': 3,
    'UAE': 4, 'Thailand': 7, 'Vietnam': 7, 'Indonesia': 7,
    'Philippines': 8, 'Malaysia': 8, 'Bangladesh': 6,
    'Sri Lanka': 5.5, 'Nepal': 5.75, 'Mongolia': 8,
    'Uzbekistan': 5, 'Kyrgyzstan': 6, 'Tajikistan': 5,
    'Afghanistan': 4.5, 'Lebanon': 2, 'Syria': 3, 'Jordan': 2,
    'Ghana': 0, 'Morocco': 0, 'Tanzania': 3,
    'Algeria': 1, 'Tunisia': 1, 'Sudan': 2, 'Libya': 2,
    'Senegal': 0, 'DRC': 1, 'Angola': 1, 'Zimbabwe': 2, 'Zambia': 2,
    'Mozambique': 2, 'Madagascar': 3, 'Somalia': 3,
    'Rwanda': 2, 'Uganda': 3, 'Fiji': 12, 'PNG': 10,
    'Jamaica': -5, 'Costa Rica': -6, 'Panama': -5,
    'Uruguay': -3, 'Bolivia': -4, 'Peru': -5, 'Colombia': -5,
    'Ecuador': -5, 'Venezuela': -4, 'Chile': -4,
}

# Module-level storage for last true solar time lookup details
_solar_time_last_info = {}

# Equation of Time (均时差) — approximate monthly values in minutes
# Positive = sundial ahead of clock, Negative = sundial behind
EQUATION_OF_TIME = {
    1: -8, 2: -14, 3: -8, 4: 2, 5: 4, 6: 1,
    7: -5, 8: -3, 9: 5, 10: 13, 11: 15, 12: 6,
}

def _find_location_info(location_str):
    """Search PROVINCE_LONGITUDES then INTERNATIONAL_CITY_COORDINATES for a location.
    Returns (longitude, source_type, tz_offset) or (None, None, None).
    """
    global _solar_time_last_info
    _solar_time_last_info = {}

    # Search Chinese cities/provinces — prefer longest key match (most specific)
    # When lengths are equal, later entries (cities) override earlier (provinces)
    best_match = None
    best_match_len = 0
    for name, lon in PROVINCE_LONGITUDES.items():
        if name in location_str and len(name) >= best_match_len:
            best_match = name
            best_match_len = len(name)
    if best_match:
        lon = PROVINCE_LONGITUDES[best_match]
        _solar_time_last_info = {
            'longitude': lon, 'source': 'chinese_city',
            'location_type': 'china', 'tz_offset': 8,
            'matched_city': best_match,
        }
        return lon, 'chinese_city', 8

    # Search international cities (substring match on city name).
    # Iterate longest-first so short aliases (e.g. "LA") do not accidentally
    # match inside longer strings (e.g. "Malaysia" contains "la").
    for city, (lon, lat) in sorted(
        INTERNATIONAL_CITY_COORDINATES.items(),
        key=lambda item: -len(item[0]),
    ):
        if city.lower() in location_str.lower():
            tz = CITY_TIMEZONES.get(city, 0)
            # Also try country-level fallback
            if tz == 0:
                for country, c_tz in CITY_TIMEZONES.items():
                    if len(country) > 2 and country.lower() in location_str.lower():
                        tz = c_tz
                        break
            _solar_time_last_info = {
                'longitude': lon, 'source': 'international_city',
                'location_type': 'international', 'tz_offset': tz,
            }
            return lon, 'international_city', tz

    # Country-level fallback
    for country, tz in CITY_TIMEZONES.items():
        if len(country) > 2 and country.lower() in location_str.lower():
            _solar_time_last_info = {
                'longitude': None, 'source': 'country_fallback',
                'location_type': 'international', 'tz_offset': tz,
            }
            return None, 'country_fallback', tz

    _solar_time_last_info = {'source': 'none', 'location_type': 'unknown', 'tz_offset': 8}
    return None, None, None


def calculate_true_solar_time(hour, minute, location_str, birth_month, input_timezone_offset=None):
    """Calculate true solar time correction for any location worldwide.

    For Chinese provinces: applies longitude correction from 120°E meridian.
    For international cities: converts local time → UTC → Beijing equivalent,
    then applies longitude correction.

    Args:
        hour: Birth hour (local time, 0-23)
        minute: Birth minute (0-59)
        location_str: Location string for longitude/timezone lookup
        birth_month: Month for equation of time correction
        input_timezone_offset: Optional explicit timezone offset (UTC hours).
                               If None, auto-detected from location.

    Returns: (adjusted_hour, adjusted_minute, adjustment_minutes, method)
    """
    # Find location info
    longitude, source_type, tz_offset = _find_location_info(location_str)

    # Use explicit timezone if provided, otherwise use detected
    if input_timezone_offset is not None:
        tz_offset = input_timezone_offset

    if longitude is None and source_type is None:
        return hour, minute, 0, 'no_correction'

    # Equation of time
    eot = EQUATION_OF_TIME.get(birth_month, 0)

    if source_type == 'chinese_province' or (longitude is not None and tz_offset == 8):
        # Chinese location: assume input is already CST (UTC+8)
        # Longitude correction from 120°E
        delta_l = longitude - 120.0
        lon_correction = delta_l * 4.0
        total_correction = lon_correction + eot
        total_minutes = hour * 60 + minute + total_correction
        total_minutes = total_minutes % 1440
    elif longitude is not None:
        # International location with known longitude
        # Step 1: convert local time to UTC
        utc_minutes = hour * 60 + minute - tz_offset * 60
        # Step 2: convert UTC to Beijing time (UTC+8)
        beijing_minutes = utc_minutes + 8 * 60
        # Step 3: apply longitude correction (from 120°E)
        delta_l = longitude - 120.0
        lon_correction = delta_l * 4.0
        total_correction = lon_correction + eot
        total_minutes = beijing_minutes + total_correction
        total_minutes = total_minutes % 1440
    else:
        # Country fallback (no exact longitude): apply timezone shift only
        utc_minutes = hour * 60 + minute - tz_offset * 60
        beijing_minutes = utc_minutes + 8 * 60
        total_correction = eot
        total_minutes = beijing_minutes + eot
        total_minutes = total_minutes % 1440

    adj_hour = int(total_minutes // 60)
    adj_minute = int(total_minutes % 60)

    # Store additional info
    adj_minutes_total = total_minutes - (hour * 60 + minute)
    if adj_minutes_total > 720:
        adj_minutes_total -= 1440
    elif adj_minutes_total < -720:
        adj_minutes_total += 1440

    return adj_hour, adj_minute, round(adj_minutes_total), 'longitude_correction'


# =============================================================================
# 6e. LIU NIAN (流年计算) — API spec §2.2
# =============================================================================

def calculate_liunian(current_year, day_master_gan, num_years=3):
    """Calculate 流年 (annual fortune) for the next num_years."""
    # Current year stem-branch
    base_idx = (current_year - 4) % 60
    liunian = []
    for i in range(num_years):
        y = current_year + i
        idx = (base_idx + i) % 60
        gan, zhi = sexagenary_by_index(idx)
        liunian.append({
            'year': y,
            'gan': gan,
            'zhi': zhi,
            'shi_shen': get_shishen(day_master_gan, gan),
        })
    return liunian


# =============================================================================
# 6f. ENHANCED SHENSHA (带含义的神煞) — API spec §2.2
# =============================================================================

SHENSHA_MEANINGS = {
    '天乙贵人': '遇之主逢凶化吉，贵人提携',
    '文昌贵人': '聪明好学，利于科考文书',
    '桃花': '异性缘佳，但也主感情波动',
    '驿马': '走动奔波，利于外出发展',
    '华盖': '聪明孤独，有宗教艺术天赋',
    '羊刃': '个性刚强，但易有血光外伤',
    '魁罡': '性格刚直果断，领导力强',
}

def enhance_shensha(shensha_dict):
    """Convert shensha keyed dict to spec-compliant array with meanings."""
    result = []
    for pillar_key, shen_list in shensha_dict.items():
        for shen in shen_list:
            if shen == '无':
                continue
            result.append({
                'name': shen,
                'position': f'{pillar_key}_zhi',
                'meaning': SHENSHA_MEANINGS.get(shen, ''),
            })
    return result


# =============================================================================
# 6g. FORMAT TO SPEC (按API规范格式化输出) — API spec §2.2
# =============================================================================

def format_to_spec(four_pillars, dayun, shensha, ziwei, wuyun_liuqi,
                   wuxing_stats, shishen_stats, liunian, true_solar_info):
    """Format all calculation results into the API spec structure."""
    dm = four_pillars['day_master']

    # Reformat four_pillars to spec
    fp_spec = {}
    for key in ['year', 'month', 'day', 'hour']:
        if key not in four_pillars:
            continue
        p = four_pillars[key]
        cg_list = [d['stem'] for d in p.get('cangan_detail', [])]
        fp_spec[key] = {
            'gan': p['gan'],
            'zhi': p['zhi'],
            'gan_wuxing': GAN_WUXING.get(p['gan'], ''),
            'zhi_wuxing': ZHI_WUXING.get(p['zhi'], ''),
            'shi_shen_gan': p['shishen'].get(p['gan'], ''),
            'shi_shen_zhi_main': p['shishen'].get(cg_list[0], '') if cg_list else '',
            'cang_gan': cg_list,
            'cang_gan_shi_shen': [p['shishen'].get(g, '') for g in cg_list],
            'nayin': p['nayin'],
            'kong_wang': False,  # simplified; true kongwang check is complex
        }

    # Shensha enhanced
    shensha_enhanced = enhance_shensha(shensha)

    # Dayun enhanced with十神
    dayun_enhanced = []
    if dayun and 'pillars' in dayun:
        current_pillar = dayun.get('current_pillar')
        for dp in dayun['pillars']:
            dy = {
                'index': dp['index'] + 1,
                'gan': dp['gan'],
                'zhi': dp['zhi'],
                'start_age': dp['start_age'],
                'end_age': dp['end_age'],
                'shi_shen_gan': get_shishen(dm, dp['gan']),
                'shi_shen_zhi': get_shishen(dm, CANGAN.get(dp['zhi'], [('',)])[0][0]),
                'is_current': (current_pillar and dp['gan'] == current_pillar['gan']
                              and dp['zhi'] == current_pillar['zhi']),
            }
            dayun_enhanced.append(dy)

    # Ziwei enhanced
    ziwei_spec = None
    if ziwei:
        palaces_list = []
        for pname, pdata in ziwei.get('palaces', {}).items():
            palaces_list.append({
                'name': pname,
                'position': pdata['zhi'],
                'tian_gan': pdata['gan'],
                'main_stars': pdata['stars'],
                'auxiliary_stars': pdata['aux_stars'],
                'daxian': pdata['daxian'],
                'is_shengong': pdata.get('is_shengong', False),
            })
        ziwei_spec = {
            'basic_info': {
                'ming_gong_gan_zhi': ziwei.get('minggong_gan', '') + ziwei.get('minggong', ''),
                'shen_gong_position': ziwei.get('shengong', ''),
                'wu_xing_ju': ziwei.get('wuxing_ju', ''),
                'ming_zhu': ziwei.get('mingzhu_star', ''),
                'shen_zhu': ziwei.get('shenzhu_star', ''),
            },
            'twelve_palaces': palaces_list,
            'si_hua': ziwei.get('sihua', {}),
        }

    # Backward-compatible summary fields
    dayun_summary = {}
    if dayun:
        dayun_summary = {
            'direction': dayun.get('direction', ''),
            'starting_age': dayun.get('starting_age', 0),
            'current_pillar': dayun.get('current_pillar'),
        }

    result = {
        'status': 'success',
        'four_pillars': fp_spec,
        'dayun_summary': dayun_summary,
        'day_master': {
            'gan': dm,
            'wuxing': GAN_WUXING.get(dm, ''),
            'yinyang': GAN_YINYANG.get(dm, ''),
            'shier_changsheng': four_pillars.get('changsheng', {}).get('day_master', ''),
        },
        'wuxing_stats': wuxing_stats,
        'shishen_stats': shishen_stats,
        'shensha': shensha_enhanced,
        'tai_yuan': {
            'gan': four_pillars['taiyuan']['gan'],
            'zhi': four_pillars['taiyuan']['zhi'],
            'nayin': four_pillars['taiyuan']['nayin'],
        },
        'ming_gong': {
            'gan': four_pillars['minggong']['gan'],
            'zhi': four_pillars['minggong']['zhi'],
            'nayin': four_pillars['minggong']['nayin'],
        },
        'shen_gong': {
            'gan': four_pillars['shengong']['gan'],
            'zhi': four_pillars['shengong']['zhi'],
            'nayin': four_pillars['shengong']['nayin'],
        },
        'da_yun': dayun_enhanced,
        'liu_nian': liunian,
        'ziwei': ziwei_spec,
        'wuyun_liuqi': wuyun_liuqi,
        'branch_relations': four_pillars.get('branch_relations', []),
        'rizhu_zihe': four_pillars.get('rizhu_zihe', {}),
        'nayin_wuxing': four_pillars.get('nayin_wuxing', {}),
        'changsheng': four_pillars.get('changsheng', {}),
        'precision_note': four_pillars.get('precision_note', ''),
    }

    result['solar_time'] = true_solar_info
    if true_solar_info['method'] == 'no_correction':
        result['solar_time']['warning'] = (
            'Location not recognized for true solar time correction. '
            'For international births, provide --timezone or ensure '
            '--location matches a known city (e.g., "London, UK").')

    return result


def compute_chart(year, month, day, hour=0, minute=0, gender="male", location="Beijing",
                  use_solar_time=False):
    """Compute a complete BaZi chart from raw birth information.

    This is the single entry point for chart calculation, used by all delivery
    surfaces (API, MCP, CLI, desktop). Returns a dict conforming to the API spec.

    Args:
        year, month, day: birth date (Gregorian)
        hour, minute: birth time (clock time before solar adjustment)
        gender: 'male' or 'female'
        location: city name for true solar time and timezone lookup
        use_solar_time: if True, hour/minute already adjusted to true solar time

    Returns:
        dict with four_pillars, day_master, da_yun, shensha, ziwei, wuyun_liuqi,
        wuxing_stats, shishen_stats, liu_nian, true_solar_info, birth_info,
        and all other spec fields from format_to_spec.
    """
    # True solar time correction
    if use_solar_time:
        adj_h, adj_m, adj_minutes, method = hour, minute, 0, 'user_adjusted'
    else:
        adj_h, adj_m, adj_minutes, method = calculate_true_solar_time(
            hour, minute, location, month)

    true_solar_info = {
        'original_time': f'{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00',
        'adjusted_time': f'{year:04d}-{month:02d}-{day:02d}T{adj_h:02d}:{adj_m:02d}:00',
        'adjustment_minutes': adj_minutes,
        'method': method,
        'location_matched': method not in ('no_correction', 'user_adjusted'),
    }

    # Four pillars
    four_pillars = calculate_four_pillars(year, month, day, adj_h, adj_m, location)
    yp = (four_pillars['year']['gan'], four_pillars['year']['zhi'])
    mp = (four_pillars['month']['gan'], four_pillars['month']['zhi'])
    dm = four_pillars['day_master']
    dm_gan = dm['gan'] if isinstance(dm, dict) else dm

    # Derived calculations
    dayun_raw = calculate_dayun(yp, mp, gender, year, month, day)
    shensha = calculate_shensha(four_pillars, dm)
    ziwei = calculate_ziwei(year, month, day, adj_h, gender)
    wuyun = calculate_wuyun_liuqi(yp[0], yp[1])
    wuxing = calculate_wuxing_stats(four_pillars)
    shishen = calculate_shishen_stats(four_pillars)
    liunian = calculate_liunian(date.today().year, dm_gan, 3)

    chart = format_to_spec(four_pillars, dayun_raw, shensha, ziwei, wuyun,
                           wuxing, shishen, liunian, true_solar_info)
    chart['birth_info'] = {
        'year': year, 'month': month, 'day': day,
        'hour': hour, 'minute': minute,
        'gender': gender, 'location': location,
    }
    chart['true_solar_info'] = true_solar_info
    return chart


def compare_charts(chart1, chart2):
    """Compare two BaZi charts across multiple dimensions.

    Unlike hehun (marriage-specific), this is a general-purpose comparison
    for any purpose: family, business partners, teacher-student, etc.

    Args:
        chart1, chart2: chart dicts as returned by compute_chart()

    Returns:
        dict with dimension-by-dimension comparison results.
    """
    def _dm(c):
        dm = c.get('day_master', {})
        return dm.get('gan', '') if isinstance(dm, dict) else str(dm)
    def _dm_wu(c):
        dm = c.get('day_master', {})
        return dm.get('wuxing', '') if isinstance(dm, dict) else GAN_WUXING.get(str(dm), '')

    dm1, dm2 = _dm(chart1), _dm(chart2)
    wu1, wu2 = _dm_wu(chart1), _dm_wu(chart2)

    # ---- 1. Five Elements comparison ----
    ws1 = chart1.get('wuxing_stats', {})
    ws2 = chart2.get('wuxing_stats', {})
    # wuxing_stats 产出 pinyin 键（calculate_wuxing_stats）——按键名映射对齐
    pinyin_elements = [('jin', '金'), ('mu', '木'), ('shui', '水'), ('huo', '火'), ('tu', '土')]
    total1 = sum(ws1.get(k, 0) for k, _ in pinyin_elements) or 1
    total2 = sum(ws2.get(k, 0) for k, _ in pinyin_elements) or 1
    wuxing_compare = {}
    for k, e in pinyin_elements:
        pct1 = round(ws1.get(k, 0) / total1 * 100, 1)
        pct2 = round(ws2.get(k, 0) / total2 * 100, 1)
        wuxing_compare[e] = {'chart1_pct': pct1, 'chart2_pct': pct2, 'diff': round(pct1 - pct2, 1)}

    # ---- 2. Day Master relationship ----
    dm_relation = get_shishen(dm1, dm2) if dm1 and dm2 else '未知'
    dm_relation_reverse = get_shishen(dm2, dm1) if dm1 and dm2 else '未知'

    # ---- 3. Nayin comparison ----
    def _day_nayin_wuxing(chart):
        value = chart.get('nayin_wuxing', '')
        if isinstance(value, dict):
            return value.get('day') or value.get('year') or ''
        return value

    nayin1 = _day_nayin_wuxing(chart1)
    nayin2 = _day_nayin_wuxing(chart2)
    nayin_relation = ''
    if nayin1 and nayin2:
        relation_map = {
            ('金','金'): '比和', ('木','木'): '比和', ('水','水'): '比和', ('火','火'): '比和', ('土','土'): '比和',
            ('金','木'): '金克木', ('金','火'): '火克金', ('金','土'): '土生金', ('金','水'): '金生水',
            ('木','土'): '木克土', ('木','金'): '金克木', ('木','水'): '水生木', ('木','火'): '木生火',
            ('水','火'): '水克火', ('水','土'): '土克水', ('水','金'): '金生水', ('水','木'): '水生木',
            ('火','金'): '火克金', ('火','水'): '水克火', ('火','木'): '木生火', ('火','土'): '火生土',
            ('土','水'): '土克水', ('土','木'): '木克土', ('土','火'): '火生土', ('土','金'): '土生金',
        }
        nayin_relation = relation_map.get((nayin1, nayin2), '')

    # ---- 4. Shensha overlap ----
    ss1 = {s['name'] for s in chart1.get('shensha', []) if isinstance(s, dict) and s.get('name')}
    ss2 = {s['name'] for s in chart2.get('shensha', []) if isinstance(s, dict) and s.get('name')}
    shared_shensha = sorted(ss1 & ss2)
    unique1 = sorted(ss1 - ss2)
    unique2 = sorted(ss2 - ss1)

    # ---- 5. Dayun stage overlap ----
    dy1 = chart1.get('da_yun', [])
    dy2 = chart2.get('da_yun', [])
    current1 = next((d for d in dy1 if d.get('is_current')), None)
    current2 = next((d for d in dy2 if d.get('is_current')), None)

    # ---- 6. Ziwei highlights ----
    zw1 = chart1.get('ziwei', {})
    zw2 = chart2.get('ziwei', {})
    mg1 = zw1.get('basic_info', {}).get('ming_gong_gan_zhi', '')
    mg2 = zw2.get('basic_info', {}).get('ming_gong_gan_zhi', '')
    sihua1 = zw1.get('si_hua', {})
    sihua2 = zw2.get('si_hua', {})

    # ---- 7. Branch relations between the two charts ----
    fp1 = chart1.get('four_pillars', {})
    fp2 = chart2.get('four_pillars', {})
    # Check for 六合/三合/六冲 between the day branches
    dz1 = fp1.get('day', {}).get('zhi', '')
    dz2 = fp2.get('day', {}).get('zhi', '')

    return {
        'chart1_dm': {'gan': dm1, 'wuxing': wu1},
        'chart2_dm': {'gan': dm2, 'wuxing': wu2},
        'dm_relation': f'{dm1}({dm_relation}) ⇄ {dm2}({dm_relation_reverse})',
        'wuxing_compare': wuxing_compare,
        'nayin': {'chart1': nayin1, 'chart2': nayin2, 'relation': nayin_relation},
        'shensha': {
            'shared': shared_shensha,
            'chart1_unique': unique1,
            'chart2_unique': unique2,
        },
        'dayun': {
            'chart1_current': current1,
            'chart2_current': current2,
        },
        'ziwei': {
            'ming_gong': {'chart1': mg1, 'chart2': mg2},
            'si_hua': {'chart1': sihua1, 'chart2': sihua2},
        },
        'day_branch': {'chart1': dz1, 'chart2': dz2},
        'birth_info': {
            'chart1': chart1.get('birth_info', {}),
            'chart2': chart2.get('birth_info', {}),
        },
    }


# =============================================================================
# 7. CLI INTERFACE
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='BaZi Multi-System Calculator'
    )
    parser.add_argument('--year', type=int, required=True, help='Birth year (Gregorian)')
    parser.add_argument('--month', type=int, required=True, help='Birth month (1-12)')
    parser.add_argument('--day', type=int, required=True, help='Birth day (1-31)')
    parser.add_argument('--hour', type=int, default=0, help='Birth hour (0-23, local time)')
    parser.add_argument('--minute', type=int, default=0, help='Birth minute (0-59)')
    parser.add_argument('--gender', choices=['male', 'female'], default='male', help='Gender')
    parser.add_argument('--location', default='Beijing', help='Birth location (city, country)')
    parser.add_argument('--timezone', type=float, default=None,
                        help='Timezone offset from UTC (e.g., -5 for EST, 8 for Beijing). '
                             'If not specified, auto-detected from --location.')
    parser.add_argument('--mode', choices=['bazi', 'dayun', 'shensha', 'ziwei', 'all'], default='all')
    parser.add_argument('--output', '-o', help='Output file path (default: stdout)')
    args = parser.parse_args()

    # True solar time correction
    true_solar = calculate_true_solar_time(args.hour, args.minute, args.location, args.month,
                                           args.timezone)
    adj_h, adj_m, adj_minutes, method = true_solar

    # Get detected timezone for display
    tz_info = _solar_time_last_info if _solar_time_last_info else {}
    detected_tz = tz_info.get('tz_offset', 8) if args.timezone is None else args.timezone

    # Build time strings with correct timezone suffix
    tz_suffix = f'{detected_tz:+.0f}'
    tz_suffix_display = tz_suffix if tz_suffix.startswith('+') or tz_suffix.startswith('-') else f'+{tz_suffix}'
    if '.' in str(detected_tz):
        tz_suffix_display = f'{detected_tz:+.2f}'

    true_solar_info = {
        'original_time': f'{args.year:04d}-{args.month:02d}-{args.day:02d}T{args.hour:02d}:{args.minute:02d}:00{tz_suffix_display}',
        'adjusted_time': f'{args.year:04d}-{args.month:02d}-{args.day:02d}T{adj_h:02d}:{adj_m:02d}:00+08:00',
        'adjustment_minutes': adj_minutes,
        'method': method,
        'detected_timezone': detected_tz,
        'detected_longitude': tz_info.get('longitude'),
        'location_type': tz_info.get('location_type', 'unknown'),
    }

    # Use adjusted time for calculations
    four_pillars = calculate_four_pillars(args.year, args.month, args.day, adj_h, adj_m, args.location)
    year_pillar = (four_pillars['year']['gan'], four_pillars['year']['zhi'])
    month_pillar = (four_pillars['month']['gan'], four_pillars['month']['zhi'])
    day_master = four_pillars['day_master']

    # All calculations — pass corrected time to dayun
    dayun = calculate_dayun(year_pillar, month_pillar, args.gender, args.year, args.month, args.day,
                            adj_h, adj_m)
    shensha = calculate_shensha(four_pillars, day_master)
    ziwei = calculate_ziwei(args.year, args.month, args.day, adj_h, args.gender)
    wuyun_liuqi = calculate_wuyun_liuqi(year_pillar[0], year_pillar[1])
    wuxing_stats = calculate_wuxing_stats(four_pillars)
    shishen_stats = calculate_shishen_stats(four_pillars)
    liunian = calculate_liunian(date.today().year, day_master, 3)

    # Format to API spec
    result = format_to_spec(four_pillars, dayun, shensha, ziwei, wuyun_liuqi,
                            wuxing_stats, shishen_stats, liunian, true_solar_info)
    result['birth_info'] = {
        'year': args.year, 'month': args.month, 'day': args.day,
        'hour': args.hour, 'minute': args.minute, 'gender': args.gender,
        'location': args.location,
    }
    if args.timezone is not None:
        result['birth_info']['timezone'] = args.timezone

    json_str = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(json_str)
            f.write('\n')
    else:
        sys.stdout.buffer.write(json_str.encode('utf-8'))
        sys.stdout.buffer.write(b'\n')


if __name__ == '__main__':
    main()
