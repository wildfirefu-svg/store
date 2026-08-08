"""compute_chart 端到端：22 键 schema + 5 盘快照 + 时变字段结构断言 + solar_time 开关。"""
from datetime import date

import pytest
from bazi_snapshot_helper import (
    SNAPSHOT_CASES,
    SNAPSHOT_DIR,
    assert_snapshot_equal,
    compute_e2e,
    freeze_lunar_backend,
    load_snapshot,
)

import bazi_calculator as bc

EXPECTED_TOP_KEYS = {
    'status', 'four_pillars', 'dayun_summary', 'day_master', 'wuxing_stats', 'shishen_stats',
    'shensha', 'tai_yuan', 'ming_gong', 'shen_gong', 'da_yun', 'liu_nian', 'ziwei',
    'wuyun_liuqi', 'branch_relations', 'rizhu_zihe', 'nayin_wuxing', 'changsheng',
    'precision_note', 'solar_time', 'birth_info', 'true_solar_info',
}


def test_compute_chart_schema_22_keys():
    chart = bc.compute_chart(1993, 7, 15, 14, 0, 'male', 'Beijing', False)  # 显式传参
    assert set(chart.keys()) == EXPECTED_TOP_KEYS


@pytest.mark.parametrize('case', SNAPSHOT_CASES, ids=lambda c: c['name'])
def test_e2e_snapshot(case, monkeypatch):
    freeze_lunar_backend(monkeypatch)
    actual = compute_e2e(case)
    expected = load_snapshot(SNAPSHOT_DIR / f"e2e_{case['name']}.json")
    assert_snapshot_equal(expected, actual)


def test_liunian_structure():
    # 时变字段改用结构断言（spec §5）：3 条、年份依次 [当年,+1,+2]、含干支/十神
    chart = bc.compute_chart(1993, 7, 15, 14, 0, 'male', 'Beijing', False)
    ln = chart['liu_nian']
    assert len(ln) == 3
    assert [e['year'] for e in ln] == [date.today().year + i for i in range(3)]
    for e in ln:
        assert set(e) >= {'year', 'gan', 'zhi', 'shi_shen'}
        assert e['gan'] in bc.TIANGAN and e['zhi'] in bc.DIZHI


def test_dayun_current_structure():
    chart = bc.compute_chart(1993, 7, 15, 14, 0, 'male', 'Beijing', False)
    currents = [p for p in chart['da_yun'] if p.get('is_current')]
    assert len(currents) <= 1
    cp = chart['dayun_summary'].get('current_pillar')
    if currents:
        assert cp and cp['gan'] == currents[0]['gan'] and cp['zhi'] == currents[0]['zhi']
    # 起运前 current_pillar 为 None 亦合法


def test_use_solar_time_flag_controls_auto_correction():
    # 实测语义（bazi_calculator.py:2110-2114）：
    #   use_solar_time=False → 自动调用 calculate_true_solar_time 经度校正（马来西亚 8:12→6:50，辰时→卯时）
    #   use_solar_time=True  → 输入视为已校正（user_adjusted），保持原辰时
    corrected = bc.compute_chart(2000, 1, 15, 8, 12, 'male', '马来西亚', False)
    pre_adjusted = bc.compute_chart(2000, 1, 15, 8, 12, 'male', '马来西亚', True)
    assert corrected['true_solar_info']['method'] == 'longitude_correction'
    assert pre_adjusted['true_solar_info']['method'] == 'user_adjusted'
    assert corrected['four_pillars']['hour']['zhi'] == '卯'
    assert pre_adjusted['four_pillars']['hour']['zhi'] == '辰'
