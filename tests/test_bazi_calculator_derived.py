"""衍生计算测试：统计不变量 / 支关系 / 宫位 / 长生 / 自合 / 五运六气 / format_to_spec。

changsheng 教科书断言先跑出缺陷 #4 的红色证据，Task 10 修复后转绿。
"""
import pytest

import bazi_calculator as bc

PINYIN_ELEMENTS = [('jin', '金'), ('mu', '木'), ('shui', '水'), ('huo', '火'), ('tu', '土')]


def _fp():
    return bc.calculate_four_pillars(1993, 7, 15, 14, 0, 'Beijing')


def _crafted(branches):
    """按 year/month/day/hour 顺序造四支（干统一甲）。"""
    return {k: {'gan': '甲', 'zhi': z} for k, z in zip(['year', 'month', 'day', 'hour'], branches)}


# ── 统计不变量 ──

def test_wuxing_stats_invariants():
    ws = bc.calculate_wuxing_stats(_fp())
    counts = {e: ws[k] for k, e in PINYIN_ELEMENTS}
    assert sum(counts.values()) == 8                          # 四干 + 四支本气
    assert set(ws['missing']) == {e for e, c in counts.items() if c == 0}
    assert counts[ws['strongest']] == max(counts.values())


def test_shishen_stats_invariants():
    fp = _fp()
    ss = bc.calculate_shishen_stats(fp)
    present = [fp[k] for k in ['year', 'month', 'day', 'hour'] if k in fp]
    expected_total = len(present) + sum(len(p.get('cangan_detail', [])) for p in present)
    assert sum(ss['counts'].values()) == expected_total       # 四干 + 全部藏干（:1329-1352）
    assert set(ss['missing']) == {s for s, c in ss['counts'].items() if c == 0}
    # 最强 = argmax（对并列稳健，不假设 tie-break 顺序）
    assert ss['counts'][ss['strongest']] == max(ss['counts'].values())
    assert ss['most_frequent_count'] == max(ss['counts'].values())


# ── 支关系 ──

def test_liuchong():
    rels = bc.detect_branch_relations(_crafted(['子', '午', '子', '丑']))
    assert any(r['type'] == '六冲' for r in rels)


def test_liuhe():
    rels = bc.detect_branch_relations(_crafted(['子', '午', '子', '丑']))
    assert any(r['type'] == '六合' and '子丑' in r['detail'] for r in rels)


def test_sanhe_full():
    rels = bc.detect_branch_relations(_crafted(['申', '子', '辰', '寅']))
    assert any(r['type'] == '三合' and r['pillars'] == 'year-month-day' for r in rels)


def test_sanxing():
    rels = bc.detect_branch_relations(_crafted(['寅', '巳', '申', '戌']))
    assert any(r['type'] == '三刑' for r in rels)


def test_liuhai():
    rels = bc.detect_branch_relations(_crafted(['子', '未', '午', '丑']))
    assert any(r['type'] == '六害' for r in rels)


# ── 宫位 ──

def test_gong_positions_legal():
    fp = _fp()
    for key in ['taiyuan', 'minggong', 'shengong']:
        assert fp[key]['gan'] in bc.TIANGAN
        assert fp[key]['zhi'] in bc.DIZHI
        assert fp[key]['nayin']
    # 直接调用覆盖（附录 A 矩阵；三个辅助函数返回形状各异，已实证：
    # get_taiyuan → (gan, zhi) 元组；get_minggong / get_shengong → 地支字符串）
    ty_gan, ty_zhi = bc.get_taiyuan(fp['month']['gan'], fp['month']['zhi'], fp['year']['gan'], fp['year']['zhi'])
    assert ty_gan in bc.TIANGAN and ty_zhi in bc.DIZHI
    assert bc.get_minggong(fp['month']['zhi'], fp['hour']['zhi']) in bc.DIZHI
    assert bc.get_shengong(fp['month']['zhi'], fp['hour']['zhi']) in bc.DIZHI


# ── 十二长生（教科书五行长生：阳顺阴逆。缺陷#4 红色证据，Task 10 修复后转绿）──

CHANGSHENG_TEXTBOOK = [
    ('甲', '亥'), ('乙', '午'), ('丙', '寅'), ('戊', '寅'), ('庚', '巳'),
    ('辛', '子'), ('壬', '申'), ('癸', '卯'), ('丁', '酉'), ('己', '酉'),
]


@pytest.mark.parametrize('gan, zhi', CHANGSHENG_TEXTBOOK)
def test_changsheng_textbook(gan, zhi):
    assert bc.get_changsheng(gan, zhi) == '长生'


# ── 日柱干支自合 ──

def test_rizhu_zihe_positive():
    for gan, zhi in [('丁', '亥'), ('戊', '子'), ('辛', '巳')]:
        r = bc.detect_rizhu_zihe(gan, zhi)
        assert r['is_zihe'] is True and r['he_type']


def test_rizhu_zihe_negative():
    assert bc.detect_rizhu_zihe('甲', '子')['is_zihe'] is False


# ── 五运六气（现有 6 键公共契约，不凭空扩展）──

def test_wuyun_liuqi_schema():
    r = bc.calculate_wuyun_liuqi('甲', '子')
    assert set(r.keys()) == {'五运', '主事脏腑', '体质倾向', '六气', '外邪倾向', '易感季节'}


# ── format_to_spec（直接调用，精确 20 键）──

FORMAT_SPEC_KEYS = {
    'status', 'four_pillars', 'dayun_summary', 'day_master', 'wuxing_stats', 'shishen_stats',
    'shensha', 'tai_yuan', 'ming_gong', 'shen_gong', 'da_yun', 'liu_nian', 'ziwei',
    'wuyun_liuqi', 'branch_relations', 'rizhu_zihe', 'nayin_wuxing', 'changsheng',
    'precision_note', 'solar_time',
}


def test_format_to_spec_direct_20_keys():
    # 构造 9 个参数直接调用 format_to_spec（非仅经 compute_chart 间接覆盖）
    fp = _fp()
    dm = fp['day_master']
    yp = (fp['year']['gan'], fp['year']['zhi'])
    mp = (fp['month']['gan'], fp['month']['zhi'])
    dayun = bc.calculate_dayun(yp, mp, 'male', 1993, 7, 15, 14, 0)
    shensha = bc.calculate_shensha(fp, dm)
    ziwei = bc.calculate_ziwei(1993, 7, 15, 14, 'male')
    wuyun = bc.calculate_wuyun_liuqi(yp[0], yp[1])
    wuxing = bc.calculate_wuxing_stats(fp)
    shishen = bc.calculate_shishen_stats(fp)
    liunian = bc.calculate_liunian(2026, dm, 3)
    true_solar_info = {'method': 'no_correction'}
    result = bc.format_to_spec(fp, dayun, shensha, ziwei, wuyun, wuxing, shishen, liunian, true_solar_info)
    assert set(result.keys()) == FORMAT_SPEC_KEYS

# ── compare_charts（缺陷#3：按中文键读 pinyin 键，占比恒 0。修复后转绿）──

def _two_charts():
    c1 = bc.compute_chart(1993, 7, 15, 14, 0, 'male', 'Beijing', False)
    c2 = bc.compute_chart(1988, 2, 20, 10, 0, 'female', 'Beijing', False)
    return c1, c2


def test_compare_structure():
    cc = bc.compare_charts(*_two_charts())
    assert {'wuxing_compare', 'dm_relation', 'nayin', 'shensha', 'dayun'} <= set(cc.keys())


def test_compare_wuxing_pct_sums_100():
    cc = bc.compare_charts(*_two_charts())
    for side in ['chart1_pct', 'chart2_pct']:
        total = sum(v[side] for v in cc['wuxing_compare'].values())
        assert abs(total - 100) <= 0.6, f'{side} 总和 {total}（修复前恒为 0）'


def test_compare_wuxing_nonzero():
    cc = bc.compare_charts(*_two_charts())
    assert any(v['chart1_pct'] > 0 for v in cc['wuxing_compare'].values())


def test_compare_wuxing_matches_input():
    c1, _ = _two_charts()
    cc = bc.compare_charts(*_two_charts())
    ws = c1['wuxing_stats']
    total = sum(ws[k] for k, _ in PINYIN_ELEMENTS)
    for k, e in PINYIN_ELEMENTS:
        assert cc['wuxing_compare'][e]['chart1_pct'] == round(ws[k] / total * 100, 1)


def test_compare_identical_charts_zero_diff():
    c1, _ = _two_charts()
    cc = bc.compare_charts(c1, c1)
    assert all(v['diff'] == 0 for v in cc['wuxing_compare'].values())
