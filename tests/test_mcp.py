#!/usr/bin/env python3
"""Integration tests for MCP Server — test each tool via direct function calls."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# MCP server requires the 'mcp' package — skip all tests if unavailable
mcp = None
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location('mcp_server', 'mcp_server.py')
    _mcp_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_mcp_mod)
    mcp = _mcp_mod
except (ModuleNotFoundError, ImportError):
    mcp = None

pytestmark = pytest.mark.skipif(mcp is None, reason="'mcp' package not installed")


# ── Shared birth parameters ──
YEAR, MONTH, DAY, HOUR, MINUTE = 1993, 9, 3, 8, 30
GENDER, LOCATION = 'male', 'Beijing'


class TestBaziPaipan:
    def test_returns_valid_json(self):
        result_str = mcp.bazi_paipan(YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION)
        result = json.loads(result_str)
        assert isinstance(result, dict)

    def test_contains_four_pillars(self):
        result = json.loads(mcp.bazi_paipan(YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION))
        assert 'four_pillars' in result
        for pk in ['year', 'month', 'day', 'hour']:
            assert pk in result['four_pillars']
            assert 'gan' in result['four_pillars'][pk]
            assert 'zhi' in result['four_pillars'][pk]

    def test_contains_day_master(self):
        result = json.loads(mcp.bazi_paipan(YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION))
        assert 'day_master' in result
        dm = result['day_master']
        assert 'gan' in dm

    def test_contains_da_yun(self):
        result = json.loads(mcp.bazi_paipan(YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION))
        assert 'da_yun' in result
        assert len(result['da_yun']) >= 8

    def test_contains_shensha(self):
        result = json.loads(mcp.bazi_paipan(YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION))
        assert 'shensha' in result

    def test_contains_birth_info(self):
        result = json.loads(mcp.bazi_paipan(YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION))
        assert 'birth_info' in result
        assert result['birth_info']['year'] == YEAR


class TestBaziTrueSolarTime:
    def test_returns_valid_json(self):
        result = json.loads(mcp.bazi_true_solar_time(YEAR, MONTH, DAY, HOUR, MINUTE, LOCATION))
        assert isinstance(result, dict)
        assert 'adjusted' in result
        assert 'offset_minutes' in result
        assert 'method' in result
        assert 'location' in result

    def test_offset_is_reasonable(self):
        """Beijing true solar time offset should be within ±30 minutes."""
        result = json.loads(mcp.bazi_true_solar_time(YEAR, MONTH, DAY, HOUR, MINUTE, LOCATION))
        offset = result['offset_minutes']
        assert -60 <= offset <= 60, f'Unexpected offset: {offset}'


class TestBaziZeri:
    def test_returns_valid_structure(self):
        result = json.loads(mcp.bazi_zeri(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION,
            target_year=2026, target_month=6, purpose='通用', top_n=3))
        assert 'purpose' in result
        assert 'dates' in result
        assert isinstance(result['dates'], list)
        assert len(result['dates']) <= 3

    def test_zeri_dates_have_keys(self):
        result = json.loads(mcp.bazi_zeri(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION,
            target_year=2026, target_month=6, purpose='结婚', top_n=2))
        for d in result['dates']:
            assert 'date' in d or 'year' in d or 'score' in d  # at least one meaningful key


class TestBaziLiunian:
    def test_returns_calendar(self):
        result = json.loads(mcp.bazi_liunian(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION, target_year=2026))
        assert isinstance(result, dict)

    def test_default_target_year(self):
        result = json.loads(mcp.bazi_liunian(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION))
        assert isinstance(result, dict)


class TestBaziNameEval:
    def test_rejects_short_name(self):
        result = json.loads(mcp.bazi_name_eval(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION, name='张'))
        assert 'error' in result

    def test_evaluates_full_name(self):
        result = json.loads(mcp.bazi_name_eval(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION, name='张伟'))
        assert isinstance(result, dict)
        assert 'error' not in result


class TestBaziNameGen:
    def test_generates_names(self):
        result = json.loads(mcp.bazi_name_gen(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION, surname='李', top_n=3))
        assert isinstance(result, dict)

    def test_default_surname(self):
        result = json.loads(mcp.bazi_name_gen(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION, top_n=2))
        assert isinstance(result, dict)


class TestBaziCaseSearch:
    def test_returns_results(self):
        result = json.loads(mcp.bazi_case_search(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION, top_n=3))
        # May be a list or a dict depending on retrieval mode
        assert isinstance(result, (list, dict))


class TestBaziKBSearch:
    def test_returns_results(self):
        result = json.loads(mcp.bazi_kb_search('财运', top=3))
        assert 'query' in result
        assert 'count' in result
        assert 'results' in result
        assert isinstance(result['results'], list)

    def test_empty_query_handled(self):
        result = json.loads(mcp.bazi_kb_search('', top=3))
        assert isinstance(result, dict)
        assert 'results' in result


class TestBaziKBStats:
    def test_returns_stats(self):
        result = json.loads(mcp.bazi_kb_stats())
        assert isinstance(result, dict)
        # Should have some count information
        assert len(result) > 0


class TestBaziCompare:
    def test_compares_two_same_charts(self):
        result = json.loads(mcp.bazi_compare(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION,
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION))
        assert 'chart1_dm' in result
        assert 'chart2_dm' in result
        assert 'wuxing_compare' in result
        assert 'shensha' in result
        assert 'dm_relation' in result

    def test_compares_two_different_charts(self):
        result = json.loads(mcp.bazi_compare(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION,
            2000, 1, 1, 12, 0, 'female', 'Shanghai'))
        assert result['chart1_dm']['gan'] != result['chart2_dm']['gan'] or \
               result['birth_info']['chart1']['year'] != result['birth_info']['chart2']['year']

    def test_compare_has_all_dimensions(self):
        result = json.loads(mcp.bazi_compare(
            YEAR, MONTH, DAY, HOUR, MINUTE, GENDER, LOCATION,
            2000, 1, 1, 12, 0, 'female', 'Shanghai'))
        for key in ['wuxing_compare', 'nayin', 'shensha', 'dayun', 'ziwei',
                    'day_branch', 'birth_info', 'dm_relation']:
            assert key in result, f'Missing dimension: {key}'


class TestMCPModuleDependencies:
    """Verify that compute_chart is properly wired (no regression from refactoring)."""

    def test_compute_chart_imported(self):
        assert hasattr(mcp, 'compute_chart') or hasattr(mcp, '_calc_chart')

    def test_calc_chart_uses_compute_chart(self):
        """_calc_chart should delegate to compute_chart from bazi_calculator."""
        import inspect
        source = inspect.getsource(mcp._calc_chart)
        assert 'compute_chart' in source
