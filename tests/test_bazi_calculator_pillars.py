"""四柱与边界测试：规则断言 + 金标参数化 + 节气边界 fixture + 早/晚子时。

断言来源：test_charts.json 金标、五虎遁/五鼠遁口诀、十神/旬空规则、
solar_terms.json 中 verified=True 的冻结数据 fixture（独立于比较算法，UTC+8）。
"""
import json
import os

import pytest

import bazi_calculator as bc

TESTS_DIR = os.path.dirname(__file__)
SOLAR_TERMS_PATH = os.path.join(TESTS_DIR, '..', 'knowledge-base', 'solar_terms.json')


def _load_golden(n=8):
    with open(os.path.join(TESTS_DIR, 'test_charts.json'), encoding='utf-8') as f:
        return json.load(f)['test_cases'][:n]


GOLDEN = _load_golden()


@pytest.mark.parametrize('tc', GOLDEN, ids=lambda t: t['id'])
def test_four_pillars_golden(tc):
    fp = bc.calculate_four_pillars(tc['year'], tc['month'], tc['day'], tc['hour'], 0, 'Beijing')
    exp = tc['expected']
    assert f"{fp['year']['gan']}{fp['year']['zhi']}" == exp['year']
    assert f"{fp['month']['gan']}{fp['month']['zhi']}" == exp['month']
    assert f"{fp['day']['gan']}{fp['day']['zhi']}" == exp['day']
    assert f"{fp['hour']['gan']}{fp['hour']['zhi']}" == exp['hour']
    assert fp['day_master'] == exp['day_master']


def test_wuhudun_month_stem():
    # 五虎遁：甲己之年丙作首 → 甲年正月（立春后）月柱 = 丙寅（已实证）
    assert bc.get_month_pillar(2024, '甲', 2, 20, 0, 0) == ('丙', '寅')


def test_wushudun_hour_stem():
    # 五鼠遁：甲己还加甲 → 甲日子时 = 甲子；乙庚丙作初 → 乙日子时 = 丙子（已实证）
    assert bc.get_hour_pillar('甲', 0, 30) == ('甲', '子')
    assert bc.get_hour_pillar('乙', 0, 30) == ('丙', '子')


def test_shishen_full_table():
    # 甲日主见十干（已实证）
    expected = {'甲': '比肩', '乙': '劫财', '丙': '食神', '丁': '伤官', '戊': '偏财',
                '己': '正财', '庚': '七杀', '辛': '正官', '壬': '偏印', '癸': '正印'}
    for gan, ss in expected.items():
        assert bc.get_shishen('甲', gan) == ss


def test_kongwang():
    assert bc.get_kongwang('甲', '子') == ('戌', '亥')  # 甲子旬中戌亥空（已实证）
    assert bc.get_kongwang('甲', '戌') == ('申', '酉')  # 甲戌旬中申酉空（已实证）


def test_nayin_cangan_present():
    fp = bc.calculate_four_pillars(1993, 7, 15, 14, 0, 'Beijing')
    for key in ['year', 'month', 'day', 'hour']:
        assert fp[key]['nayin']
        assert fp[key]['cangan_detail']


# ── 节气边界（冻结 fixture：solar_terms.json 中 verified=True 条目，UTC+8）──

def _verified_term(year, name):
    """取自 solar_terms.json 的分钟级人工核验条目（独立于比较算法的数据表）。

    fixture 证明的是"比较算法按仓库数据表切换"，天文时刻正确性不在本轮范围。
    注意：本测试与数据表条目强绑定——若此 fixture 失败，先检查 solar_terms.json
    中对应条目是否被修改或降级（verified 变更），而不是测试本身的 bug。
    """
    with open(SOLAR_TERMS_PATH, encoding='utf-8') as f:
        st = json.load(f)
    key = f'{year}|{name}'
    assert key in st, f'fixture 缺失: {key}'
    m, d, h, mi, verified = st[key]
    assert verified is True and h >= 0, f'fixture 无分钟精度: {key}'
    return m, d, h, mi


def test_lichun_year_boundary_minute():
    # 2024 立春 2月4日 16:27（verified=True）：前 1 分钟癸卯年，整点甲辰年（已实证）
    m, d, h, mi = _verified_term(2024, '立春')
    assert bc.get_year_pillar(2024, m, d, h, mi - 1) == ('癸', '卯')
    assert bc.get_year_pillar(2024, m, d, h, mi) == ('甲', '辰')


def test_qingming_month_boundary_minute():
    # 2025 清明 4月4日 20:49（verified=True）：乙巳年 己卯月→庚辰月（已实证）
    m, d, h, mi = _verified_term(2025, '清明')
    assert bc.get_month_pillar(2025, '乙', m, d, h, mi - 1) == ('己', '卯')
    assert bc.get_month_pillar(2025, '乙', m, d, h, mi) == ('庚', '辰')


def test_jingzhe_month_boundary_date_only():
    # 2024 惊蛰 3月6日（verified=False → 日期级切换，已实证）
    # 断言的是"按日期切换"的外部行为，不验证内部 term_minutes=-1 的实现细节
    with open(SOLAR_TERMS_PATH, encoding='utf-8') as f:
        m, d, _h, _mi, verified = json.load(f)['2024|惊蛰']
    assert verified is False
    assert bc.get_month_pillar(2024, '甲', m, d - 1, 12, 0) == ('丙', '寅')
    assert bc.get_month_pillar(2024, '甲', m, d, 12, 0) == ('丁', '卯')


def test_solar_term_info_modes():
    # verified 条目分钟级 / 非 verified 条目日期级（读码确认行为 bazi_calculator.py:187-193）
    # 注：断言基于当前 solar_terms.json 全部为 5 字段条目的已知数据形状
    name_before, *_ = bc.get_solar_term_info(2024, 2, 4, 16, 26)
    name_after, *_ = bc.get_solar_term_info(2024, 2, 4, 16, 27)
    assert name_before != name_after  # 立春 16:27 精确切换
    name_d1, *_ = bc.get_solar_term_info(2024, 3, 5, 12, 0)
    name_d2, *_ = bc.get_solar_term_info(2024, 3, 6, 12, 0)
    assert name_d1 != name_d2  # 惊蛰按日切换


def test_month_branch_idx_boundary():
    before = bc.get_month_branch_idx(2024, 2, 4, 16, 26)
    after = bc.get_month_branch_idx(2024, 2, 4, 16, 27)
    assert (after - before) % 12 == 1


def test_next_jie_info_shape():
    name, m, d = bc.get_next_jie_info(2024, 6, 15, 12, 0)
    assert name in bc.SOLAR_TERM_NAMES
    assert 1 <= m <= 12 and 1 <= d <= 31


# ── 早/晚子时（特征化：锁定引擎当前语义，见 spec §4.1）──

def test_zi_hour_early_uses_same_day_stem():
    # 早子时 0:00-0:59：时干按当日干起（甲日 → 甲子，已实证）
    assert bc.get_hour_pillar('甲', 0, 30) == ('甲', '子')


def test_zi_hour_late_uses_next_day_stem():
    # 晚子时 23:00-23:59：时干按次日干起（甲日→次日乙→丙子；乙日→次日丙→戊子，已实证）
    assert bc.get_hour_pillar('甲', 23, 30) == ('丙', '子')
    assert bc.get_hour_pillar('乙', 23, 30) == ('戊', '子')


def test_zi_hour_day_pillar_not_rolled():
    # 引擎语义：日柱不随 23 点切换（get_day_pillar 无时刻参数）——特征化锁定
    early = bc.calculate_four_pillars(1990, 5, 10, 0, 30, 'Beijing')
    late = bc.calculate_four_pillars(1990, 5, 10, 23, 30, 'Beijing')
    assert f"{early['day']['gan']}{early['day']['zhi']}" == f"{late['day']['gan']}{late['day']['zhi']}"
    assert early['hour']['zhi'] == late['hour']['zhi'] == '子'
    assert early['hour']['gan'] != late['hour']['gan']
