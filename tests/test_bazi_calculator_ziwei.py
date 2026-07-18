"""紫微结构测试（calculate_ziwei 为仓库内纯 Python 实现，无 iztro 运行时依赖）。

快照测试由 Task 13 追加（依赖届时创建的 bazi_snapshot_helper）。
"""
import pytest

import bazi_calculator as bc

MAIN_STARS = {'紫微', '天机', '太阳', '武曲', '天同', '廉贞', '天府',
              '太阴', '贪狼', '巨门', '天相', '天梁', '七杀', '破军'}


def test_gong_positions():
    zw = bc.calculate_ziwei(1993, 7, 15, 14, 'male')
    assert zw['minggong'] in bc.DIZHI      # 已实证：亥
    assert zw['shengong'] in bc.DIZHI      # 已实证：丑
    assert '局' in zw['wuxing_ju']         # 已实证：含"水二局"


def test_twelve_palaces():
    zw = bc.calculate_ziwei(1993, 7, 15, 14, 'male')
    assert len(zw['palaces']) == 12
    for _name, p in zw['palaces'].items():
        assert p['zhi'] in bc.DIZHI
        assert p['gan'] in bc.TIANGAN
        assert set(p) >= {'stars', 'aux_stars', 'daxian'}


def test_14_main_stars_deployed():
    zw = bc.calculate_ziwei(1993, 7, 15, 14, 'male')
    deployed = {s['name'] for p in zw['palaces'].values() for s in p['stars']}
    assert MAIN_STARS <= deployed


def test_ziwei_position():
    # 特征化锁定当前算法输出（已实证：水二局 + 农历十五 → 10）
    assert bc.ziwei_position('水二局', 15) == 10
    for ju in ['水二局', '木三局', '金四局', '土五局', '火六局']:
        for day in [1, 15, 30]:
            pos = bc.ziwei_position(ju, day)
            assert isinstance(pos, int)
