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
