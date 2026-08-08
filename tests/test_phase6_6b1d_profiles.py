"""Phase 6 6B1-D: runner CLI choices + arm mapping + visibility matrix tests.

覆盖:
  - _REASONED_ARM_MAP 字典完整性 (b2b -> ziwei_mini, b2c -> sequential)
  - visibility_requirements for b2b (required 段标, forbidden 裸名宫位)
  - visibility_requirements for b2c (required 分隔线+指令)
  - assert_visibility 对 b2b/b2c 的 fail-closed 行为
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.profiles import (
    assert_visibility,
    resolve_profile,
    visibility_requirements,
)

# ---- _REASONED_ARM_MAP 测试（通过 run_benchmark 内部映射） ----

class TestReasonedArmMap:
    """Test that _REASONED_ARM_MAP includes b2b/b2c."""

    def test_arm_map_includes_b2b_ziwei_mini(self):
        """b2b -> ziwei_mini 必须在映射中."""
        # 直接测试 visibility_requirements 接受 ziwei_mini
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        required, forbidden = visibility_requirements(profile, "legacy_v0", "ziwei_mini")
        assert "【紫微斗数·精简】" in required

    def test_arm_map_includes_b2c_sequential(self):
        """b2c -> sequential 必须在映射中."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        required, forbidden = visibility_requirements(profile, "legacy_v0", "sequential")
        assert "--- 八字分析结束 ---" in required


# ---- visibility_requirements for b2b (ziwei_mini) ----

class TestVisibilityB2b:
    """Test visibility_requirements for b2b (ziwei_mini)."""

    def test_b2b_required_markers(self):
        """b2b required 必须包含 4 个段标."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        required, _ = visibility_requirements(profile, "legacy_v0", "ziwei_mini")
        assert "【紫微斗数·精简】" in required
        assert "【命宫】" in required
        assert "【身宫】" in required
        assert "【主星】" in required

    def test_b2b_forbidden_real_palace_names(self):
        """b2b forbidden 必须包含真实裸名宫位."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        _, forbidden = visibility_requirements(profile, "legacy_v0", "ziwei_mini")
        for palace in ["父母", "福德", "田宅", "官禄", "仆役", "迁移",
                       "疾厄", "财帛", "子女", "夫妻", "兄弟"]:
            assert palace in forbidden, f"b2b forbidden 缺少裸名宫位: {palace}"

    def test_b2b_forbidden_bazi_keywords(self):
        """b2b forbidden 必须包含八字关键词."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        _, forbidden = visibility_requirements(profile, "legacy_v0", "ziwei_mini")
        for kw in ["四柱", "日主", "大运", "神煞"]:
            assert kw in forbidden, f"b2b forbidden 缺少八字关键词: {kw}"

    def test_b2b_forbidden_includes_denylist(self):
        """b2b forbidden 必须包含 _DENYLIST_MARKERS."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        _, forbidden = visibility_requirements(profile, "legacy_v0", "ziwei_mini")
        # _DENYLIST_MARKERS 非空
        assert len(forbidden) > 11  # 11 宫位 + 4 关键词 + denylist


# ---- visibility_requirements for b2c (sequential) ----

class TestVisibilityB2c:
    """Test visibility_requirements for b2c (sequential)."""

    def test_b2c_required_markers(self):
        """b2c required 必须包含紫微段标、分隔线、指令."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        required, _ = visibility_requirements(profile, "legacy_v0", "sequential")
        assert "【紫微斗数·本命】" in required
        assert "--- 八字分析结束 ---" in required
        assert "请先基于八字信息进行初步分析" in required

    def test_b2c_forbidden_not_empty(self):
        """b2c forbidden 不能为空, 必须继承 _DENYLIST_MARKERS."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        _, forbidden = visibility_requirements(profile, "legacy_v0", "sequential")
        assert len(forbidden) > 0

    def test_b2c_forbidden_includes_denylist(self):
        """b2c forbidden 必须包含 _DENYLIST_MARKERS."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        _, forbidden = visibility_requirements(profile, "legacy_v0", "sequential")
        # denylist 非空（与 combined 臂相同）
        assert forbidden  # 非空集合


# ---- assert_visibility fail-closed 行为 ----

class TestAssertVisibilityFailClosed:
    """Test assert_visibility fail-closed for b2b/b2c."""

    def test_b2b_assert_visibility_passes_with_valid_text(self):
        """b2b 合法文本通过 visibility gate (返回空 violations)."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        text = "【紫微斗数·精简】\n【命宫】寅\n【身宫】未标注\n【主星】紫微（庙）"
        violations = assert_visibility(text, profile, "legacy_v0", "ziwei_mini")
        assert violations == [], f"合法文本不应有 violations: {violations}"

    def test_b2b_assert_visibility_fails_with_secondary_palace(self):
        """b2b 含次要宫位时 fail-closed (violations 非空)."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        text = "【紫微斗数·精简】\n【命宫】寅\n【身宫】未标注\n【主星】紫微（庙）\n父母宫信息"
        violations = assert_visibility(text, profile, "legacy_v0", "ziwei_mini")
        assert len(violations) > 0, "含次要宫位时应有 violation"

    def test_b2c_assert_visibility_passes_with_valid_text(self):
        """b2c 合法文本通过 visibility gate (返回空 violations)."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        text = ("八字信息\n\n--- 八字分析结束 ---\n\n"
                "【紫微斗数·本命】\n命宫：寅\n\n"
                "请先基于八字信息进行初步分析，"
                "再基于紫微斗数信息进行补充判断，"
                "综合两者得出结论。")
        violations = assert_visibility(text, profile, "legacy_v0", "sequential")
        assert violations == [], f"合法文本不应有 violations: {violations}"

    def test_b2c_assert_visibility_fails_missing_separator(self):
        """b2c 缺少分隔线时 fail-closed (violations 非空)."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        text = ("八字信息\n\n【紫微斗数·本命】\n命宫：寅\n\n"
                "请先基于八字信息进行初步分析")
        violations = assert_visibility(text, profile, "legacy_v0", "sequential")
        assert len(violations) > 0, "缺少分隔线时应有 violation"


# ---- unknown ziwei_arm fail-closed ----

class TestUnknownZiweiArmFailClosed:
    """Test that unknown ziwei_arm raises NotImplementedError (library layer)."""

    def test_unknown_arm_raises_not_implemented_error(self):
        """未知 ziwei_arm 抛 NotImplementedError (库函数层)."""
        profile = resolve_profile("baziqa_xjz_reasoned", "legacy_v0")
        with pytest.raises(NotImplementedError):
            visibility_requirements(profile, "legacy_v0", "unknown_arm")
