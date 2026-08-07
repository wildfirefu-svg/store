"""Tests for bazi_time_context relation computation (Task 2 of 6D v1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.formatters.bazi_time_context import (
    extract_target_years, classify_route_state, TemporalRouteState,
    TimeContext, NatalStructure, DayunRow, OptionLiunian, TimeContextKind,
)

DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
SHISHEN_LABELS = ["比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"]


def _legacy_combo(dy_shishen: str, ln_shishen: str) -> str:
    """Replicate old inline combo logic (two_stage_reasoning lines 743-760)."""
    combo_hint = ""
    combo = f"{dy_shishen}+{ln_shishen}"
    if "伤官" in combo and "正官" in combo:
        combo_hint = "，组合效应：伤官见官"
    elif "七杀" in combo and "食神" in combo:
        combo_hint = "，组合效应：食神制杀"
    elif "偏财" in combo and "正印" in combo:
        combo_hint = "，组合效应：财坏印"
    elif "劫财" in combo and "正财" in combo:
        combo_hint = "，组合效应：劫财夺财"
    elif "正官" in combo and "七杀" in combo:
        combo_hint = "，组合效应：官杀混杂"
    elif "正印" in combo and "正财" in combo:
        combo_hint = "，组合效应：财坏印"
    elif "偏印" in combo and "食神" in combo:
        combo_hint = "，组合效应：枭神夺食"
    return combo_hint


def test_legacy_matches_new_branch_relation():
    from benchmark.formatters import bazi_time_context
    from benchmark.formatters.two_stage_reasoning import _compute_branch_relation
    for a in DIZHI:
        for b in DIZHI:
            assert _compute_branch_relation(a, b) == bazi_time_context.compute_branch_relation(a, b), \
                f"branch relation mismatch for ({a}, {b})"


def test_legacy_matches_new_gan_relation():
    from benchmark.formatters import bazi_time_context
    from benchmark.formatters.two_stage_reasoning import _compute_gan_relation
    for a in TIANGAN:
        for b in TIANGAN:
            assert _compute_gan_relation(a, b) == bazi_time_context.compute_gan_relation(a, b), \
                f"gan relation mismatch for ({a}, {b})"


def test_legacy_matches_new_shishen_combo():
    from benchmark.formatters.bazi_time_context import compute_shishen_combo
    for a in SHISHEN_LABELS:
        for b in SHISHEN_LABELS:
            assert _legacy_combo(a, b) == compute_shishen_combo(a, b), \
                f"shishen combo mismatch for ({a}, {b})"


def test_calculate_liunian_for_year_1989():
    from benchmark.formatters.bazi_time_context import calculate_liunian_for_year
    result = calculate_liunian_for_year(1989, "甲")
    assert result["year"] == 1989
    assert result["gan"] == "己"
    assert result["zhi"] == "巳"
    assert result["shi_shen"] in SHISHEN_LABELS


def test_calculate_liunian_for_year_2024():
    from benchmark.formatters.bazi_time_context import calculate_liunian_for_year
    result = calculate_liunian_for_year(2024, "甲")
    assert result["year"] == 2024
    assert result["gan"] == "甲"
    assert result["zhi"] == "辰"
    assert result["shi_shen"] in SHISHEN_LABELS


def test_calculate_liunian_for_year_boundary_1900():
    from benchmark.formatters.bazi_time_context import calculate_liunian_for_year
    result = calculate_liunian_for_year(1900, "甲")
    assert result["year"] == 1900
    assert result["gan"] == "庚"
    assert result["zhi"] == "子"
    assert result["shi_shen"] in SHISHEN_LABELS


def test_calculate_liunian_for_year_out_of_range():
    from benchmark.formatters.bazi_time_context import calculate_liunian_for_year
    with pytest.raises(ValueError):
        calculate_liunian_for_year(1899, "甲")
    with pytest.raises(ValueError):
        calculate_liunian_for_year(2101, "甲")


def test_r1_explicit_time_keyword():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("命主哪年结婚？", ["A. 1990年", "B. 1995年"])
    assert "R1" in rules


def test_r2_option_four_digit_year():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("发生何事？", ["A. 1989", "B. 1990", "C. 1991", "D. 1992"])
    assert "R2" in rules


def test_r3_age_range():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("事业如何？", ["A. 25-30岁", "B. 31-35岁"])
    assert "R3" in rules


def test_r4_dayun_keyword():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("大运什么时候开始", ["A. 甲", "B. 乙"])
    assert "R4" in rules


def test_r5_when_year_mixed():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("何时结婚", ["A. 1995年", "B. 1998年"])
    assert "R5" in rules


def test_r6_question_body_year():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("1980年发生何事？", ["A. 结婚", "B. 升职"])
    assert "R6" in rules


def test_r6_long_digit_no_false_positive():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("订单号12345678是什么？", ["A. 甲", "B. 乙"])
    assert "R6" not in rules


def test_r7_single_age():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("何时结婚？", ["A. 30岁", "B. 35岁"])
    assert "R7" in rules


def test_r7_plain_number():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("何时结婚？", ["A. 30", "B. 35"])
    assert "R7" in rules


def test_no_rules_matched():
    from benchmark.formatters.bazi_time_context import detect_temporal_rules
    rules = detect_temporal_rules("命主性格如何？", ["A. 温和", "B. 刚强"])
    assert len(rules) == 0


def test_extract_target_years_four_digit():
    years = extract_target_years("发生何事？", ["A. 1989", "B. 1990"], None)
    assert 1989 in years


def test_extract_target_years_age_range():
    years = extract_target_years("事业如何？", ["A. 25-30岁"], 1980)
    assert years == (2005, 2010)


def test_extract_target_years_single_age():
    years = extract_target_years("何时结婚？", ["A. 30岁"], 1980)
    assert years == (2010,)


def test_extract_target_years_routed_without_targets():
    years = extract_target_years("大运如何？", ["A. 甲", "B. 乙"], None)
    assert years == ()


def test_extract_target_years_years_after_with_base():
    years = extract_target_years("2020年起3年后发生何事？", ["A. 升职", "B. 结婚"], None)
    assert 2023 in years


def test_extract_target_years_years_after_no_base():
    years = extract_target_years("3年后发生何事？", ["A. 升职", "B. 结婚"], None)
    assert years == ()


def test_extract_target_years_years_after_multiple():
    years = extract_target_years(
        "2020年起3年后，2021年起5年后发生何事？", ["A. 升职", "B. 结婚"], None
    )
    assert 2023 in years
    assert 2026 in years


def test_extract_target_years_out_of_range_fail_closed():
    import pytest
    with pytest.raises(ValueError):
        extract_target_years("何时？", ["A. 30岁"], 2095)


def test_classify_route_state_with_targets():
    state = classify_route_state(frozenset({"R6"}), (2020,))
    assert state == TemporalRouteState.ROUTED_WITH_TARGETS


def test_classify_route_state_without_targets():
    state = classify_route_state(frozenset({"R4"}), ())
    assert state == TemporalRouteState.ROUTED_WITHOUT_TARGETS


def test_classify_route_state_not_routed():
    state = classify_route_state(frozenset(), ())
    assert state == TemporalRouteState.NOT_ROUTED


def test_time_context_is_frozen():
    import pytest
    natal = NatalStructure("甲", ("甲子", "乙丑", "丙寅", "丁卯"), (), (), ())
    ctx = TimeContext(
        natal, (), (), TimeContextKind.NATAL,
        TemporalRouteState.ROUTED_WITHOUT_TARGETS, (), "abc",
    )
    with pytest.raises(Exception):
        ctx.natal = natal  # type: ignore


def test_time_context_uses_tuple_not_list():
    natal = NatalStructure("甲", ("甲子",), (), (), ())
    ctx = TimeContext(
        natal, (), (), TimeContextKind.NATAL, TemporalRouteState.NOT_ROUTED, (), "abc"
    )
    assert isinstance(ctx.dayun_table, tuple)
    assert isinstance(ctx.option_liunian, tuple)
    assert isinstance(ctx.target_years, tuple)


def test_time_context_canonical_json_reproducible():
    natal = NatalStructure("甲", ("甲子",), (), (), ())
    ctx1 = TimeContext(
        natal, (), (), TimeContextKind.NATAL, TemporalRouteState.NOT_ROUTED, (), "abc"
    )
    ctx2 = TimeContext(
        natal, (), (), TimeContextKind.NATAL, TemporalRouteState.NOT_ROUTED, (), "abc"
    )
    assert ctx1.canonical_json() == ctx2.canonical_json()
    assert ctx1.sha256() == ctx2.sha256()


def test_time_context_to_dict():
    natal = NatalStructure("甲", ("甲子",), (), (), ())
    ctx = TimeContext(
        natal, (), (), TimeContextKind.NATAL, TemporalRouteState.NOT_ROUTED, (), "abc"
    )
    d = ctx.to_dict()
    assert isinstance(d, dict)
    assert "natal" in d
