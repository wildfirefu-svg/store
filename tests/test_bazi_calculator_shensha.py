"""神煞测试：A 日干系 / B 三合系(缺陷#1) / C 日柱系(缺陷#2) / enhance / 快照(Task 13 追加)。

B/C 两部分先按教科书规则写断言跑出红色证据，再按 spec §8 流程最小修复引擎转绿。
"""
import pytest

import bazi_calculator as bc
from bazi_snapshot_helper import (
    SNAPSHOT_CASES, SNAPSHOT_DIR,
    assert_snapshot_equal, compute_shensha, freeze_lunar_backend, load_snapshot,
)


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


# ── B. 三合系（缺陷#1：:944 以候选支自身定局。按教科书规则断言，修复后转绿）──

SANHE_GROUPS = [('申', '子', '辰'), ('寅', '午', '戌'), ('巳', '酉', '丑'), ('亥', '卯', '未')]

# (神煞名, 目标支映射表, 参考支口径)：紫微仅日支（源码注释口径，待命理复核）；其余年/日支并集
SANHE_CASES = [
    ('桃花', lambda: bc.TAOHUA_MAP, 'year_or_day'),
    ('驿马', lambda: bc.YIMA_MAP, 'year_or_day'),
    ('华盖', lambda: bc.HUAGAI_MAP, 'year_or_day'),
    ('将星', lambda: bc._jiangxing, 'year_or_day'),
    ('劫煞', lambda: bc._jiesha, 'year_or_day'),
    ('灾煞', lambda: bc._zaisha, 'year_or_day'),
    ('亡神', lambda: bc._wangshen, 'year_or_day'),
    ('紫微', lambda: bc._ziwei_ss, 'day_only'),
    ('三合禄', lambda: bc._sanhelu, 'year_or_day'),
]


@pytest.mark.parametrize('name, get_table, scope', SANHE_CASES)
@pytest.mark.parametrize('group', SANHE_GROUPS)
def test_sanhe_by_year_branch(name, get_table, scope, group):
    if scope == 'day_only':
        pytest.skip('紫微仅以日支为参考')
    target = get_table()[group]
    fp = mk_fp(_ganzhi_for(group[0]), '甲子', '甲子', _ganzhi_for(target, 1))
    ss = bc.calculate_shensha(fp, '甲')
    assert name in ss['hour'], f'年支{group[0]}属{"".join(group)}局，时支{target}应命中{name}'


@pytest.mark.parametrize('name, get_table, scope', SANHE_CASES)
@pytest.mark.parametrize('group', SANHE_GROUPS)
def test_sanhe_by_day_branch(name, get_table, scope, group):
    target = get_table()[group]
    fp = mk_fp('甲子', '甲子', _ganzhi_for(group[1]), _ganzhi_for(target, 1))
    ss = bc.calculate_shensha(fp, '甲')
    assert name in ss['hour'], f'日支{group[1]}属{"".join(group)}局，时支{target}应命中{name}'


@pytest.mark.parametrize('name, get_table, scope', SANHE_CASES)
def test_sanhe_negative(name, get_table, scope):
    # 目标支在盘，但年支(子)与日支(子)均属申子辰局；取寅午戌局目标 → 不命中
    target = get_table()[('寅', '午', '戌')]
    fp = mk_fp('甲子', '甲子', '甲子', _ganzhi_for(target, 1))
    ss = bc.calculate_shensha(fp, '甲')
    assert name not in ss['hour'], f'年/日支均不属寅午戌局，时支{target}不应命中{name}'


def test_sanhe_negative_ziwei_year_only():
    # 紫微(仅日支)：年支属申子辰局、日支午不属局 → 时支酉不命中
    fp = mk_fp('甲申', '甲子', '甲午', '乙酉')
    ss = bc.calculate_shensha(fp, '甲')
    assert '紫微' not in ss['hour']


def test_sanhe_merge_year_and_day():
    # 年支属申子辰局、日支属寅午戌局 → 两局目标支均命中（并集合并）
    fp1 = mk_fp('甲申', '甲子', '甲寅', '乙酉')   # 时支酉 = 申子辰局桃花
    assert '桃花' in bc.calculate_shensha(fp1, '甲')['hour']
    fp2 = mk_fp('甲申', '甲子', '甲寅', _ganzhi_for('申', 1))  # 时支申 = 寅午戌局驿马
    assert '驿马' in bc.calculate_shensha(fp2, '甲')['hour']


def test_sanhe_no_duplicate():
    # 年支(申)与日支(辰)同属申子辰局 → 同柱桃花只出现一次
    ss = bc.calculate_shensha(mk_fp('甲申', '甲子', '甲辰', '乙酉'), '甲')
    assert ss['hour'].count('桃花') == 1


# ── C. 日柱系（缺陷#2：:996-1003 无 key=='day' 限制。修复后转绿）──

DAY_PILLAR_CASES = [
    ('魁罡', '庚辰'), ('孤鸾煞', '甲寅'), ('阴差阳错', '丙子'),
    ('十恶大败', '甲辰'), ('八专', '丁未'), ('悬针', '甲午'), ('天赦', '戊寅'),
]

# 填充柱均不在 7 张日柱系表内——日柱系仅读本柱干支，他柱内容不进入判定逻辑
NEUTRAL_FP = ('乙丑', '丙寅', '丁卯', '戊辰')


@pytest.mark.parametrize('name, ganzhi', DAY_PILLAR_CASES)
def test_day_pillar_positive(name, ganzhi):
    # 对应干支位于日柱时命中（7 张表注释均为"日柱为"）
    fp = mk_fp('甲子', '甲子', ganzhi, '甲子')
    assert name in bc.calculate_shensha(fp, '甲')['day']


@pytest.mark.parametrize('name, ganzhi', DAY_PILLAR_CASES)
@pytest.mark.parametrize('pos', ['year', 'month', 'hour'])
def test_day_pillar_position_negative(name, ganzhi, pos):
    # 同一干支仅位于年/月/时柱时不命中（其余柱填充互不相同的非表干支）
    fp = mk_fp(*NEUTRAL_FP)
    fp[pos] = {'gan': ganzhi[0], 'zhi': ganzhi[1]}
    assert name not in bc.calculate_shensha(fp, '甲')[pos]


# ── 快照（引擎修复后生成基线）──

@pytest.mark.parametrize('case', SNAPSHOT_CASES[:3], ids=lambda c: c['name'])
def test_shensha_snapshot(case, monkeypatch):
    freeze_lunar_backend(monkeypatch)
    actual = compute_shensha(case)
    expected = load_snapshot(SNAPSHOT_DIR / f"shensha_{case['name']}.json")
    assert_snapshot_equal(expected, actual)
