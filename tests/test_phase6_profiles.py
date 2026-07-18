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
)

FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "phase6" / "case_sample_1.json"
AS_OF = "2026-07-17"


def load_case() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_four_named_configs_five_dims():
    expected = {
        "baziqa_official_multi_turn": ("baziqa", "official", "multi_turn", "approved_v1", "baziqa_macro"),
        "baziqa_xjz_direct": ("baziqa", "xjz_direct", "direct", "approved_v1", "baziqa_macro"),
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


def test_derive_formatter_all_four():
    assert derive_formatter(resolve_profile("baziqa_official_multi_turn")) == "format_multi_turn"
    assert derive_formatter(resolve_profile("baziqa_xjz_direct")) == "format_direct_choice_prompt"
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
