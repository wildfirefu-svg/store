"""Tests for bazi_time_context relation computation (Task 2 of 6D v1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
