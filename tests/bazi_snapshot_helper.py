"""bazi_calculator 快照测试辅助：用例定义、时变字段剥离、农历后端冻结、快照读写与字段级 diff。

快照 = 冻结现状防回归（characterization），基线由 regenerate.py 手动生成，
变更引擎后人工 review diff 再提交（spec §5）。
"""
import copy
import json
from pathlib import Path

import bazi_calculator as bc
import lunar_calendar

SNAPSHOT_DIR = Path(__file__).parent / 'fixtures' / 'bazi_calculator_snapshots'

SNAPSHOT_CASES = [
    {'name': 'male_1993',   'year': 1993, 'month': 7,  'day': 15, 'hour': 14, 'minute': 0,  'gender': 'male',   'location': 'Beijing', 'use_solar_time': False},
    {'name': 'female_1988', 'year': 1988, 'month': 2,  'day': 20, 'hour': 10, 'minute': 0,  'gender': 'female', 'location': 'Beijing', 'use_solar_time': False},
    {'name': 'solar_my',    'year': 2000, 'month': 1,  'day': 15, 'hour': 8,  'minute': 12, 'gender': 'male',   'location': '马来西亚', 'use_solar_time': True},
    {'name': 'zi_hour',     'year': 1990, 'month': 5,  'day': 10, 'hour': 23, 'minute': 30, 'gender': 'male',   'location': 'Beijing', 'use_solar_time': False},
    {'name': 'female_2000', 'year': 2000, 'month': 12, 'day': 31, 'hour': 8,  'minute': 0,  'gender': 'female', 'location': 'Beijing', 'use_solar_time': False},
]


def freeze_lunar_backend(monkeypatch):
    """强制内置农历后端，快照跨机器不漂移（lunar_calendar.py:46 导入时探测 iztro）。"""
    monkeypatch.setattr(lunar_calendar, '_IZTRO_PYTHON', None)


def strip_volatile(chart):
    """剥离随运行日期变化的字段（spec §5）：liu_nian + 大运当前标记。"""
    c = copy.deepcopy(chart)
    c.pop('liu_nian', None)
    if isinstance(c.get('dayun_summary'), dict):
        c['dayun_summary'].pop('current_pillar', None)
    for p in c.get('da_yun') or []:
        p.pop('is_current', None)
    return c


def compute_e2e(case):
    chart = bc.compute_chart(case['year'], case['month'], case['day'], case['hour'],
                             case['minute'], case['gender'], case['location'], case['use_solar_time'])
    return strip_volatile(chart)


def compute_shensha(case):
    fp = bc.calculate_four_pillars(case['year'], case['month'], case['day'],
                                   case['hour'], case['minute'], case['location'])
    return bc.enhance_shensha(bc.calculate_shensha(fp, fp['day_master']))


def compute_ziwei(case):
    return bc.calculate_ziwei(case['year'], case['month'], case['day'], case['hour'], case['gender'])


def save_snapshot(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {'_meta': {'lunar_backend': 'builtin',
                         'generator': 'tests/fixtures/bazi_calculator_snapshots/regenerate.py'},
               'data': data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def load_snapshot(path):
    return json.loads(path.read_text(encoding='utf-8'))['data']


def assert_snapshot_equal(expected, actual, path=''):
    """规范化后的字段级 diff 断言。"""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in sorted(set(expected) | set(actual)):
            assert k in expected, f'{path}/{k}: 实际输出多出键'
            assert k in actual, f'{path}/{k}: 实际输出缺少键（期望 {expected[k]!r}）'
            assert_snapshot_equal(expected[k], actual[k], f'{path}/{k}')
    elif isinstance(expected, list) and isinstance(actual, list):
        assert len(expected) == len(actual), f'{path}: 长度 {len(expected)} != {len(actual)}'
        for i, (e, a) in enumerate(zip(expected, actual)):
            assert_snapshot_equal(e, a, f'{path}[{i}]')
    else:
        assert expected == actual, f'{path}: 期望 {expected!r}，实际 {actual!r}'
