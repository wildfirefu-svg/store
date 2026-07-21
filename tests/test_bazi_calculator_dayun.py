"""大运与流年测试：四种方向组合、起运区间、10 步递进、流年序列。"""
import bazi_calculator as bc


def _dayun(year, month, day, hour, gender):
    fp = bc.calculate_four_pillars(year, month, day, hour, 0, 'Beijing')
    yp = (fp['year']['gan'], fp['year']['zhi'])
    mp = (fp['month']['gan'], fp['month']['zhi'])
    return bc.calculate_dayun(yp, mp, gender, year, month, day, hour, 0), mp


def test_direction_yang_male_forward():
    dy, _ = _dayun(2024, 3, 10, 10, 'male')    # 甲辰年 阳男 → 顺排（已实证）
    assert dy['direction'] == '顺排'


def test_direction_yang_female_backward():
    dy, _ = _dayun(2024, 3, 10, 10, 'female')  # 阳女 → 逆排（已实证）
    assert dy['direction'] == '逆排'


def test_direction_yin_male_backward():
    dy, _ = _dayun(1993, 7, 15, 14, 'male')    # 癸酉年 阴男 → 逆排（已实证）
    assert dy['direction'] == '逆排'


def test_direction_yin_female_forward():
    dy, _ = _dayun(1993, 7, 15, 14, 'female')  # 癸酉年 阴女 → 顺排（已实证）
    assert dy['direction'] == '顺排'


def test_starting_age_range():
    dy, _ = _dayun(1993, 7, 15, 14, 'male')
    assert 0 <= dy['starting_age'] <= 10                     # 范围兜底
    assert abs(dy['starting_age'] - 2.5) < 0.3               # 已知盘精确值（已实证 2.5）


def test_pillar_progression_forward():
    # 顺排：第 i 步大运 = 月柱沿六十甲子后移 i 位，连续 10 步且柱数=10（已实证 丁卯→戊辰→己巳…）
    dy, mp = _dayun(2024, 3, 10, 10, 'male')
    assert len(dy['pillars']) == 10
    idx = bc.sexagenary_index(*mp)
    for i, p in enumerate(dy['pillars'], start=1):
        assert (p['gan'], p['zhi']) == bc.sexagenary_by_index((idx + i) % 60)


def test_pillar_progression_backward():
    # 逆排：第 i 步大运 = 月柱前移 i 位（已实证 己未→戊午…）
    dy, mp = _dayun(1993, 7, 15, 14, 'male')
    assert len(dy['pillars']) == 10
    idx = bc.sexagenary_index(*mp)
    for i, p in enumerate(dy['pillars'], start=1):
        assert (p['gan'], p['zhi']) == bc.sexagenary_by_index((idx - i) % 60)


def test_sexagenary_roundtrip():
    for i in range(60):
        assert bc.sexagenary_index(*bc.sexagenary_by_index(i)) == i


def test_liunian_sequence():
    # 甲日主 2026 起 3 年（已实证：丙午食神/丁未伤官/戊申偏财）
    ln = bc.calculate_liunian(2026, '甲', 3)
    assert [e['year'] for e in ln] == [2026, 2027, 2028]
    assert [(e['gan'], e['zhi']) for e in ln] == [('丙', '午'), ('丁', '未'), ('戊', '申')]
    assert [e['shi_shen'] for e in ln] == ['食神', '伤官', '偏财']
    for i in range(1, 3):
        prev = bc.sexagenary_index(ln[i - 1]['gan'], ln[i - 1]['zhi'])
        cur = bc.sexagenary_index(ln[i]['gan'], ln[i]['zhi'])
        assert (cur - prev) % 60 == 1
