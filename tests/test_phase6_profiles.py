from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.chart_context import render_chart_context
from benchmark.runners.profiles import (
    PROFILES,
    assert_visibility,
    derive_formatter,
    derive_method,
    prompt_fingerprint,
    resolve_profile,
    visibility_gate,
    visibility_requirements,
)

FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "phase6" / "case_sample_1.json"
AS_OF = "2026-07-17"


def load_case() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_six_named_configs_six_dims():
    expected = {
        "baziqa_official_multi_turn": ("baziqa", "official", "multi_turn", "approved_v1", "baziqa_macro"),
        "baziqa_xjz_direct": ("baziqa", "xjz_direct", "direct", "approved_v1", "baziqa_macro"),
        "baziqa_xjz_reasoned": ("baziqa", "xjz_reasoned", "direct", "legacy_v0", "baziqa_macro"),
        "baziqa_xjz_dual": ("baziqa", "xjz_dual", "direct", "legacy_v0", "baziqa_macro"),
        "mingli_official_cot_astro": ("mingli", "official", "direct", "approved_v1", "mingli_trimmed"),
        "mingli_xjz_direct": ("mingli", "xjz_direct", "direct", "approved_v1", "mingli_trimmed"),
    }
    assert set(PROFILES) == set(expected)
    for pid, dims in expected.items():
        p = PROFILES[pid]
        assert (p.dataset, p.prompt_style, p.interaction_mode,
                p.chart_schema_version, p.scoring_profile) == dims


def test_resolve_profile_schema_override():
    p = resolve_profile("baziqa_xjz_direct", "legacy_v0")
    assert p.chart_schema_version == "legacy_v0"
    assert p.dataset == "baziqa"


def test_resolve_profile_unknown_exits():
    with pytest.raises(SystemExit):
        resolve_profile("nope")
    with pytest.raises(SystemExit):
        resolve_profile("baziqa_xjz_direct", "v999")


def test_derive_method_mapping():
    assert derive_method(resolve_profile("baziqa_official_multi_turn")) == "multi_turn"
    for pid in ("baziqa_xjz_direct", "mingli_official_cot_astro", "mingli_xjz_direct"):
        assert derive_method(resolve_profile(pid)) == "direct_choice"
    assert derive_method(resolve_profile("baziqa_xjz_dual")) == "dual_system"


def test_derive_formatter_all_six():
    assert derive_formatter(resolve_profile("baziqa_official_multi_turn")) == "format_multi_turn"
    assert derive_formatter(resolve_profile("baziqa_xjz_direct")) == "format_direct_choice_prompt"
    assert derive_formatter(resolve_profile("baziqa_xjz_reasoned")) == "format_reasoned_choice_prompt"
    assert derive_formatter(resolve_profile("baziqa_xjz_dual")) == "format_dual_system_prompt"
    assert derive_formatter(resolve_profile("mingli_official_cot_astro")) == "format_official_cot_prompt"
    assert derive_formatter(resolve_profile("mingli_xjz_direct")) == "format_direct_choice_prompt"


def test_visibility_baziqa_approved_passes_on_fixture():
    rendered = render_chart_context(load_case(), "approved_v1", as_of_date=AS_OF)
    assert assert_visibility(rendered, resolve_profile("baziqa_xjz_direct"), "approved_v1") == []


def test_visibility_mingli_approved_requires_ziwei():
    case = load_case()
    profile = resolve_profile("mingli_xjz_direct")
    if case["chart_input"].get("ziwei"):
        rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
        assert assert_visibility(rendered, profile, "approved_v1") == []
    case["chart_input"].pop("ziwei", None)
    rendered_no_ziwei = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    violations = assert_visibility(rendered_no_ziwei, profile, "approved_v1")
    assert any("【紫微斗数·本命】" in v for v in violations)


def test_visibility_legacy_arm_anti_crosstalk():
    case = load_case()
    profile = resolve_profile("baziqa_xjz_direct", "legacy_v0")
    legacy = render_chart_context(case, "legacy_v0")
    assert assert_visibility(legacy, profile, "legacy_v0") == []
    approved = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    violations = assert_visibility(approved, profile, "legacy_v0")
    assert violations
    assert all(v.startswith("forbidden 命中") for v in violations)


def test_visibility_denylist_label_caught():
    rendered = render_chart_context(load_case(), "approved_v1", as_of_date=AS_OF)
    poisoned = rendered + "\n【流年】\n2027年：测试\n"
    violations = assert_visibility(poisoned, resolve_profile("baziqa_xjz_direct"), "approved_v1")
    assert any("【流年】" in v for v in violations)


def test_visibility_official_profile_has_own_required():
    """裁决 1B：mingli_official_cot_astro 独立官方 astro required，不与 xjz 共享。"""
    from benchmark.runners.profiles import visibility_requirements

    official_req, _ = visibility_requirements(resolve_profile("mingli_official_cot_astro"), "approved_v1")
    xjz_req, _ = visibility_requirements(resolve_profile("mingli_xjz_direct"), "approved_v1")
    assert official_req != xjz_req
    assert "八字命盘信息：" in official_req
    assert "【四柱】" not in official_req
    assert "【四柱】" in xjz_req


def test_prompt_fingerprint_stable_and_sensitive(monkeypatch):
    """resume manifest 字段：指纹跨调用确定；模板版本/渲染源码任一变化 → 指纹变化。"""
    from benchmark.formatters import chart_context

    p = resolve_profile("baziqa_xjz_direct", "approved_v1")
    fp1 = prompt_fingerprint(p)
    assert prompt_fingerprint(p) == fp1
    # 执行偏离（Task 4 审核发现）：计划原文 monkeypatch 的 chart_context.CHART_CONTEXT_TEMPLATE
    # 在 Task 1 已批准实现中不存在（只有 CHART_CONTEXT_TEMPLATE_VERSION），照抄必 AttributeError；
    # 改为打 CHART_CONTEXT_TEMPLATE_VERSION，实现侧指纹 parts 同步去掉该不存在的常量。
    monkeypatch.setattr(chart_context, "CHART_CONTEXT_TEMPLATE_VERSION",
                        chart_context.CHART_CONTEXT_TEMPLATE_VERSION + " ")
    assert prompt_fingerprint(p) != fp1


def test_judge_visibility_rules():
    """ziwei_arm='judge' 时 required 为空，forbidden 包含全部体系标记。"""
    from benchmark.runners.profiles import visibility_requirements
    p = resolve_profile("baziqa_xjz_dual")
    req, forb = visibility_requirements(p, "legacy_v0", ziwei_arm="judge")
    assert req == frozenset()
    assert "【紫微斗数·本命】" in forb
    assert "【四柱】" in forb


def test_dual_fingerprint_includes_all_prompt_sources():
    import inspect
    p = resolve_profile("baziqa_xjz_dual")
    fp = prompt_fingerprint(p)
    assert isinstance(fp, str) and len(fp) == 64
    fp2 = prompt_fingerprint(resolve_profile("baziqa_xjz_reasoned"))
    assert fp != fp2


def test_dual_fingerprint_source_scope():
    """指纹计算源码应含 judge_swap_seed 等全部函数。"""
    import inspect
    src = inspect.getsource(prompt_fingerprint)
    for fn in ("judge_swap_seed", "build_judge_prompt", "render_reasoned_context",
               "_assemble_reasoned_choice_prompt", "extract_reasoned_choice_answer", "format_options"):
        assert fn in src, f"fingerprint 缺少 {fn}"


class TestJudgeVisibilityProseSafe:
    """judge 提示词含命理散文（如婚姻题的"夫妻"自然表述）不得被误杀；
    宫位标签形式（紫微段标记）仍必须拦截。"""

    def test_judge_stage_prose_not_blocked(self):
        from benchmark.runners.profiles import assert_visibility, resolve_profile
        p = resolve_profile("baziqa_xjz_dual", "legacy_v0")
        prose = "分析：此造夫妻恩爱，婚后感情稳定，夫妻二人相敬如宾。"
        assert assert_visibility(prose, p, "legacy_v0", stage="judge") == []

    def test_judge_stage_palace_label_still_blocked(self):
        from benchmark.runners.profiles import assert_visibility, resolve_profile
        p = resolve_profile("baziqa_xjz_dual", "legacy_v0")
        label = "【紫微斗数·本命】夫妻（戌·丙）"
        assert assert_visibility(label, p, "legacy_v0", stage="judge") != []



# ---- 6D v1 Task 6: temporal context visibility matrix ----

def test_visibility_off_denies_all_temporal():
    """injection=off 时 3 个 temporal markers 在 deny 侧."""
    req, deny = visibility_requirements(time_context_injection="off")
    assert "【时间上下文·预计算】" in deny
    assert "【大运排布】" in deny
    assert "【目标流年详析】" in deny


def test_visibility_on_not_routed_denies_all():
    """injection=on + NOT_ROUTED 时 3 个 markers 在 deny 侧."""
    req, deny = visibility_requirements(time_context_injection="on", route_state="NOT_ROUTED")
    assert "【时间上下文·预计算】" in deny
    assert "【大运排布】" in deny
    assert "【目标流年详析】" in deny


def test_visibility_on_without_targets_denies_liunian():
    """injection=on + ROUTED_WITHOUT_TARGETS 时 【目标流年详析】 在 deny 侧."""
    req, deny = visibility_requirements(time_context_injection="on", route_state="ROUTED_WITHOUT_TARGETS")
    assert "【时间上下文·预计算】" in req
    assert "【大运排布】" in req
    assert "【目标流年详析】" in deny


def test_visibility_on_with_targets_requires_all():
    """injection=on + ROUTED_WITH_TARGETS 时 3 个 markers 在 required 侧."""
    req, deny = visibility_requirements(time_context_injection="on", route_state="ROUTED_WITH_TARGETS")
    assert "【时间上下文·预计算】" in req
    assert "【大运排布】" in req
    assert "【目标流年详析】" in req


def test_visibility_requirements_accepts_injection_and_route_state():
    """visibility_requirements 签名接受 time_context_injection 和 route_state 参数."""
    req, deny = visibility_requirements(time_context_injection="on", route_state="ROUTED_WITH_TARGETS")
    assert isinstance(req, frozenset)
    assert isinstance(deny, frozenset)


def test_assert_visibility_injection_aware():
    """assert_visibility 接受 injection + route_state."""
    violations = assert_visibility("test text", time_context_injection="off")
    assert isinstance(violations, list)


def test_visibility_gate_injection_aware():
    """visibility_gate 接受 injection + route_state."""
    result = visibility_gate("test text", time_context_injection="off")
    assert result in ("PASS", "BLOCKED_PRECONDITION")
