#!/usr/bin/env python3
"""Unit tests for report_builder.py — rendering functions and report generation."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import report_builder as rb

# ── Sample chart data for tests ──

SAMPLE_CHART = {
    'four_pillars': {
        'year':  {'gan': '癸', 'zhi': '酉', 'cang_gan': ['辛'], 'shi_shen_gan': '偏印', 'nayin': '剑锋金', 'kong_wang': '戌亥'},
        'month': {'gan': '辛', 'zhi': '酉', 'cang_gan': ['辛'], 'shi_shen_gan': '偏印', 'nayin': '石榴木', 'kong_wang': '午未'},
        'day':   {'gan': '丙', 'zhi': '子', 'cang_gan': ['癸'], 'shi_shen_gan': '',         'nayin': '涧下水', 'kong_wang': '申酉'},
        'hour':  {'gan': '甲', 'zhi': '午', 'cang_gan': ['丁','己'], 'shi_shen_gan': '偏印', 'nayin': '砂石金', 'kong_wang': '辰巳'},
    },
    'day_master': {'gan': '丙', 'wuxing': '火', 'yinyang': '阳'},
    'birth_info': {'year': 1963, 'month': 7, 'day': 9, 'hour': 8, 'minute': 0, 'gender': 'male', 'location': 'Beijing'},
    'da_yun': [
        {'gan': '壬', 'zhi': '戌', 'start_age': 8,  'end_age': 17,  'is_current': False},
        {'gan': '癸', 'zhi': '亥', 'start_age': 18, 'end_age': 27,  'is_current': False},
        {'gan': '甲', 'zhi': '子', 'start_age': 28, 'end_age': 37,  'is_current': True},
        {'gan': '乙', 'zhi': '丑', 'start_age': 38, 'end_age': 47,  'is_current': False},
        {'gan': '丙', 'zhi': '寅', 'start_age': 48, 'end_age': 57,  'is_current': False},
        {'gan': '丁', 'zhi': '卯', 'start_age': 58, 'end_age': 67,  'is_current': False},
        {'gan': '戊', 'zhi': '辰', 'start_age': 68, 'end_age': 77,  'is_current': False},
        {'gan': '己', 'zhi': '巳', 'start_age': 78, 'end_age': 87,  'is_current': False},
    ],
    'tai_yuan': {'gan': '庚', 'zhi': '子'},
    'ming_gong': {'gan': '乙', 'zhi': '卯'},
    'shen_gong': {'gan': '己', 'zhi': '酉'},
    'day_master': {'gan': '丙', 'wuxing': '火', 'yinyang': '阳'},
}

SAMPLE_CONCLUSIONS = {
    'wangshuai': {
        'grade': '身弱',
        '得令': {'score': 0, 'note': '不得月令'},
        '得地': {'score': 1, 'note': '日支得地'},
        '得势': {'score': 0, 'note': '不得势'},
        '远近': {'score': -1, 'note': '印星远离'},
    },
    'pattern': {'name': '正官格', 'strength': '中', 'detail': '月令正官透干'},
    'yongshen': {
        'primary': ['木', '火'],
        'secondary': ['土'],
        'forbidden': ['金', '水'],
        'reasoning': '身弱喜印比',
    },
    'seven_dims': {
        'personality': {'score': 70, 'note': '性格刚毅'},
        'career': {'score': 70, 'note': '官印相生'},
        'wealth': {'score': 55, 'note': '财星不显'},
        'love': {'score': 65, 'note': '日坐正官'},
        'health': {'score': 60, 'note': '注意心脏'},
        'study': {'score': 80, 'note': '印星得力'},
        'liunian': {'score': 75, 'note': '贵人相助'},
    },
    'liunian_analysis': {
        'years': [
            {'year': 2026, 'ganzhi': '丙午', 'dayun_rel': '比肩帮身', 'yongshen': '火为用', 'focus': '财运', 'ji_xiong': '吉'},
            {'year': 2027, 'ganzhi': '丁未', 'dayun_rel': '劫财帮身', 'yongshen': '火为用', 'focus': '事业', 'ji_xiong': '平'},
            {'year': 2028, 'ganzhi': '戊申', 'dayun_rel': '食神泄身', 'yongshen': '土为忌', 'focus': '健康', 'ji_xiong': '凶'},
        ],
    },
    'judgments': [
        {'name': '财运分析', 'conclusion': '中等财运', 'confidence': '中', 'evidence': ['财星不旺', '食神生财']},
        {'name': '事业分析', 'conclusion': '稳步上升', 'confidence': '高', 'evidence': ['官印相生', '贵人扶持']},
    ],
}


class TestRenderChartTable:
    def test_returns_string(self):
        result = rb.render_chart_table(
            SAMPLE_CHART['four_pillars'], SAMPLE_CHART['day_master'],
            SAMPLE_CHART['da_yun'], SAMPLE_CHART['tai_yuan'],
            SAMPLE_CHART['ming_gong'], SAMPLE_CHART['shen_gong'])
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_pillar_labels(self):
        result = rb.render_chart_table(
            SAMPLE_CHART['four_pillars'], SAMPLE_CHART['day_master'],
            SAMPLE_CHART['da_yun'], SAMPLE_CHART['tai_yuan'],
            SAMPLE_CHART['ming_gong'], SAMPLE_CHART['shen_gong'])
        assert '年柱' in result
        assert '月柱' in result
        assert '日柱' in result
        assert '时柱' in result

    def test_contains_gan_zhi(self):
        result = rb.render_chart_table(
            SAMPLE_CHART['four_pillars'], SAMPLE_CHART['day_master'],
            SAMPLE_CHART['da_yun'], SAMPLE_CHART['tai_yuan'],
            SAMPLE_CHART['ming_gong'], SAMPLE_CHART['shen_gong'])
        for gan in ['癸', '辛', '丙', '甲']:
            assert gan in result

    def test_day_pillar_has_rizhu(self):
        result = rb.render_chart_table(
            SAMPLE_CHART['four_pillars'], SAMPLE_CHART['day_master'],
            SAMPLE_CHART['da_yun'], SAMPLE_CHART['tai_yuan'],
            SAMPLE_CHART['ming_gong'], SAMPLE_CHART['shen_gong'])
        assert '日主' in result

    def test_handles_empty_dayun(self):
        result = rb.render_chart_table(
            SAMPLE_CHART['four_pillars'], SAMPLE_CHART['day_master'],
            [], SAMPLE_CHART['tai_yuan'],
            SAMPLE_CHART['ming_gong'], SAMPLE_CHART['shen_gong'])
        assert '起运：N/A' in result
        assert '当前大运：N/A' in result


class TestRenderWangshuai:
    def test_returns_table(self):
        result = rb.render_wangshuai(SAMPLE_CONCLUSIONS['wangshuai'])
        assert '| 维度 |' in result
        assert '得令' in result
        assert '得地' in result


class TestRenderPattern:
    def test_returns_string(self):
        result = rb.render_pattern(SAMPLE_CONCLUSIONS['pattern'])
        assert isinstance(result, str)
        assert len(result) > 10


class TestRenderYongshen:
    def test_returns_string(self):
        result = rb.render_yongshen(SAMPLE_CONCLUSIONS['yongshen'])
        assert isinstance(result, str)
        assert len(result) > 10


class TestRenderDayunTable:
    def test_returns_all_steps(self):
        result = rb.render_dayun_table(SAMPLE_CHART['da_yun'])
        assert isinstance(result, str)
        # Should have 8 da yun steps
        for gan in ['壬', '癸', '甲', '乙', '丙', '丁', '戊', '己']:
            assert gan in result

    def test_marks_current_dayun(self):
        result = rb.render_dayun_table(SAMPLE_CHART['da_yun'])
        # 甲子 is the current dayun (is_current=True)
        assert '甲' in result
        assert '子' in result


class TestRenderLiunianTable:
    def test_returns_all_years(self):
        result = rb.render_liunian_table(SAMPLE_CONCLUSIONS['liunian_analysis'])
        for year in ['2026', '2027', '2028']:
            assert year in result


class TestRenderSevenDims:
    def test_returns_all_dims(self):
        result = rb.render_seven_dims(SAMPLE_CONCLUSIONS['seven_dims'])
        # Dimension labels are Chinese (性格特质, 事业方向, etc.)
        for label in ['性格', '事业', '财运', '感情', '健康', '学业', '运势']:
            assert label in result, f'Missing label: {label}'


class TestRenderJudgments:
    def test_returns_all_judgments(self):
        result = rb.render_judgments(SAMPLE_CONCLUSIONS['judgments'])
        assert '财运分析' in result
        assert '事业分析' in result


class TestBuildModeReports:
    def test_build_mode1_returns_string(self):
        result = rb.build_mode1_report(SAMPLE_CHART, SAMPLE_CONCLUSIONS)
        assert isinstance(result, str)
        assert len(result) > 200

    def test_build_mode2_returns_string(self):
        result = rb.build_mode2_report(SAMPLE_CHART, SAMPLE_CONCLUSIONS)
        assert isinstance(result, str)
        assert len(result) > 200

    def test_build_mode3_returns_string(self):
        result = rb.build_mode3_report(SAMPLE_CHART, SAMPLE_CONCLUSIONS)
        assert isinstance(result, str)
        assert len(result) > 200

    def test_all_six_modes_return_non_empty(self):
        # Modes 1-5 work with generic chart data; mode6 (hehun) needs person1/person2
        for mode_fn in [rb.build_mode1_report, rb.build_mode2_report,
                        rb.build_mode3_report, rb.build_mode4_report,
                        rb.build_mode5_report]:
            result = mode_fn(SAMPLE_CHART, SAMPLE_CONCLUSIONS)
            assert isinstance(result, str)
            assert len(result) > 50, f'{mode_fn.__name__} returned short output'

    def test_mode6_handles_missing_data(self):
        """Mode 6 should not crash with incomplete conclusions (missing person data)."""
        # Mode 6 expects person1/person2 in conclusions — give it minimal data
        hehun_conclusions = {
            'person1': {'birth_info': {'year': 1963, 'month': 7, 'day': 9, 'gender': 'male'}, 'day_master': '丙'},
            'person2': {'birth_info': {'year': 1993, 'month': 9, 'day': 3, 'gender': 'female'}, 'day_master': '甲'},
            'chart1_display': '甲盘', 'chart2_display': '乙盘',
            'person1_core': '身弱', 'person2_core': '身旺',
        }
        result = rb.build_mode6_report(SAMPLE_CHART, hehun_conclusions)
        assert isinstance(result, str)
        assert len(result) > 50


class TestBuildReportFileIO:
    def test_build_report_writes_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(SAMPLE_CHART, f, ensure_ascii=False)
            chart_path = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(SAMPLE_CONCLUSIONS, f, ensure_ascii=False)
            concl_path = f.name
        out_path = os.path.join(tempfile.gettempdir(), 'test_report.md')

        try:
            rb.build_report(chart_path, 1, concl_path, out_path)
            assert os.path.isfile(out_path)
            with open(out_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert len(content) > 200
            assert '四柱' in content or '八字' in content or '命盘' in content
        finally:
            for p in [chart_path, concl_path, out_path]:
                if os.path.isfile(p):
                    os.unlink(p)

    def test_build_report_returns_markdown_when_no_output(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(SAMPLE_CHART, f, ensure_ascii=False)
            chart_path = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(SAMPLE_CONCLUSIONS, f, ensure_ascii=False)
            concl_path = f.name
        try:
            result = rb.build_report(chart_path, 1, concl_path, None)
            assert isinstance(result, str)
            assert len(result) > 200
        finally:
            for p in [chart_path, concl_path]:
                if os.path.isfile(p):
                    os.unlink(p)
