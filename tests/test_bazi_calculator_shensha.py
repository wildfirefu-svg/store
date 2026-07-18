"""神煞测试：A 日干系 / B 三合系(缺陷#1) / C 日柱系(缺陷#2) / enhance / 快照(Task 13 追加)。

B/C 两部分先按教科书规则写断言跑出红色证据，再按 spec §8 流程最小修复引擎转绿。
"""
import pytest

import bazi_calculator as bc


def mk_fp(year, month, day, hour):
    """构造最小 four_pillars 结构（calculate_shensha 只读各柱 gan/zhi，已验证）。"""
    def _p(ganzhi):
        return {'gan': ganzhi[0], 'zhi': ganzhi[1]}
    return {'year': _p(year), 'month': _p(month), 'day': _p(day), 'hour': _p(hour)}


def _ganzhi_for(zhi, offset=0):
    """天干仅起占位作用——三合系/日柱系神煞均不以天干判定，任意天干不影响结果。"""
    return bc.TIANGAN[offset % 10] + zhi


# ── A. 日干系（读码+实测确认实现正确，直接断言）──

def test_tianyi_guiren():
    # 甲戊庚日主见丑/未 = 天乙贵人（已实测命中）
    ss = bc.calculate_shensha(mk_fp('甲子', '乙丑', '甲子', '甲子'), '甲')
    assert '天乙贵人' in ss['month']


def test_wenchang():
    # 甲日主见巳 = 文昌贵人
    ss = bc.calculate_shensha(mk_fp('甲子', '己巳', '甲子', '甲子'), '甲')
    assert '文昌贵人' in ss['month']


def test_yangren():
    # 甲日主见卯 = 羊刃
    ss = bc.calculate_shensha(mk_fp('甲子', '丁卯', '甲子', '甲子'), '甲')
    assert '羊刃' in ss['month']


def test_enhance_shensha_meaning():
    enh = bc.enhance_shensha(bc.calculate_shensha(mk_fp('甲子', '乙丑', '甲子', '甲子'), '甲'))
    assert isinstance(enh, list) and enh
    for item in enh:
        assert set(item) >= {'name', 'position', 'meaning'}
    assert any(i['name'] == '天乙贵人' and i['meaning'] for i in enh)
