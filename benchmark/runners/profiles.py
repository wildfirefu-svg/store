"""五维评测 profile 注册表与路由（设计 §4.3）。profile 是五维唯一来源。

可见性矩阵按 (profile.dataset, chart_schema_version) 二元组决定 required/forbidden；
forbidden 只用"段标／字段标"级子串，避免神煞释义等自然文本误杀。
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class EvalProfile:
    profile_id: str
    dataset: str             # "baziqa" | "mingli"
    prompt_style: str        # "official" | "xjz_direct"
    interaction_mode: str    # "direct" | "multi_turn"
    chart_schema_version: str
    scoring_profile: str     # "baziqa_macro" | "mingli_trimmed"


PROFILES: dict[str, EvalProfile] = {
    p.profile_id: p
    for p in (
        EvalProfile("baziqa_official_multi_turn",
                    "baziqa", "official", "multi_turn", "approved_v1", "baziqa_macro"),
        EvalProfile("baziqa_xjz_direct",
                    "baziqa", "xjz_direct", "direct", "approved_v1", "baziqa_macro"),
        EvalProfile("mingli_official_cot_astro",
                    "mingli", "official", "direct", "approved_v1", "mingli_trimmed"),
        EvalProfile("mingli_xjz_direct",
                    "mingli", "xjz_direct", "direct", "approved_v1", "mingli_trimmed"),
    )
}

SCHEMA_VERSIONS = ("legacy_v0", "approved_v1")


def resolve_profile(name: str, chart_schema_version: str | None = None) -> EvalProfile:
    try:
        profile = PROFILES[name]
    except KeyError:
        raise SystemExit(f"未知 profile: {name!r}；可选：{sorted(PROFILES)}")
    if chart_schema_version is not None:
        if chart_schema_version not in SCHEMA_VERSIONS:
            raise SystemExit(
                f"未知 chart_schema_version: {chart_schema_version!r}；可选：{SCHEMA_VERSIONS}"
            )
        profile = replace(profile, chart_schema_version=chart_schema_version)
    return profile


def derive_method(profile: EvalProfile) -> str:
    """interaction_mode → runner method；runner 不得接受与之冲突的显式 --method。"""
    return "multi_turn" if profile.interaction_mode == "multi_turn" else "direct_choice"


_FORMATTER_MAP = {
    ("baziqa", "official", "multi_turn"): "format_multi_turn",
    ("baziqa", "xjz_direct", "direct"): "format_direct_choice_prompt",
    ("mingli", "official", "direct"): "format_official_cot_prompt",
    ("mingli", "xjz_direct", "direct"): "format_direct_choice_prompt",
}


def derive_formatter(profile: EvalProfile) -> str:
    try:
        return _FORMATTER_MAP[(profile.dataset, profile.prompt_style, profile.interaction_mode)]
    except KeyError:
        raise SystemExit(f"无 formatter 映射: {profile}")


_APPROVED_BAZI_MARKERS = frozenset({
    "【四柱】", "【日主】", "【大运】", "【胎元／命宫／身宫】", "【真太阳时校正】",
    "【纳音五行】", "【五行统计】", "【十神统计】", "【地支关系】", "【神煞】",
    "藏干", "起运",
})
_MINGLI_BAZI_CORE_MARKERS = frozenset({
    "【四柱】", "【日主】", "【五行统计】", "【十神统计】", "【地支关系】", "【神煞】",
})
# 执行偏离（Task 4 审核发现）：计划原文为 "夫妻宫/财帛宫/官禄宫"，但真实 enriched 渲染
# 宫位名无"宫"后缀（golden approved_v1_case1.txt：`夫妻（戌·丙）`），照抄导致 mingli
# 可见性测试必失败。裸名已核实仅在紫微段出现，无误杀；同时兼容带"宫"后缀的变体。
_ZIWEI_MARKERS = frozenset({"【紫微斗数·本命】", "夫妻", "财帛", "官禄"})
_DENYLIST_MARKERS = frozenset({"【流年】", "空亡：", "空亡（"})
_APPROVED_ONLY_MARKERS = frozenset({
    "【四柱】", "【日主】", "【大运】", "【神煞】", "【紫微斗数·本命】",
    "【胎元／命宫／身宫】", "【真太阳时校正】", "【纳音五行】", "【五行统计】",
    "【十神统计】", "【地支关系】",
})


def visibility_requirements(
    profile: EvalProfile, chart_schema_version: str,
) -> tuple[frozenset[str], frozenset[str]]:
    if chart_schema_version == "legacy_v0":
        # 旧上下文对照臂：自身 schema 由渲染器逐字节等价保证；此处只做串扰检测。
        return frozenset(), _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS
    if chart_schema_version == "approved_v1":
        if profile.dataset == "mingli":
            # 决策记录 3：MingLi 源数据只有八字核心六字段 + palaces；缺口入报告。
            return _MINGLI_BAZI_CORE_MARKERS | _ZIWEI_MARKERS, _DENYLIST_MARKERS
        return _APPROVED_BAZI_MARKERS, _DENYLIST_MARKERS
    raise SystemExit(f"未知 chart_schema_version: {chart_schema_version!r}")


def assert_visibility(
    rendered_text: str, profile: EvalProfile, chart_schema_version: str,
) -> list[str]:
    """渲染文本上的 required/forbidden 子串断言，返回违规列表（空表 = 通过）。"""
    required, forbidden = visibility_requirements(profile, chart_schema_version)
    violations = [f"required 缺失: {m}" for m in sorted(required) if m not in rendered_text]
    violations += [f"forbidden 命中: {m}" for m in sorted(forbidden) if m in rendered_text]
    return violations


def prompt_fingerprint(profile: EvalProfile) -> str:
    """prompt/模板指纹（resume manifest 字段，设计 L168）：模板版本 +
    渲染器与 profile formatter 源码，拼接后 SHA-256。模板版本、渲染逻辑或
    formatter 路由任一变化 → 指纹变化 → resume 拒绝。"""
    import hashlib
    import inspect

    from benchmark.formatters import baziqa_prompt, chart_context

    formatter = derive_formatter(profile)
    # 执行偏离（Task 4 审核发现）：计划原文 parts 含 chart_context.CHART_CONTEXT_TEMPLATE，
    # 该常量在 Task 1 已批准实现中不存在（只有 CHART_CONTEXT_TEMPLATE_VERSION），照抄必
    # AttributeError；已去掉，模板实际文本变更由 render_chart_context 源码变化覆盖。
    parts = [formatter,
             chart_context.CHART_CONTEXT_TEMPLATE_VERSION,
             inspect.getsource(chart_context.render_chart_context),
             inspect.getsource(baziqa_prompt.format_birth_line)]
    if formatter == "format_official_cot_prompt":
        from benchmark.formatters import mingli_prompt
        parts += [mingli_prompt.OFFICIAL_COT_TEMPLATE_VERSION,
                  inspect.getsource(mingli_prompt.format_official_cot_prompt)]
    elif formatter == "format_direct_choice_prompt":
        parts.append(inspect.getsource(baziqa_prompt.format_direct_choice_prompt))
    else:  # format_multi_turn
        parts.append(inspect.getsource(baziqa_prompt.format_multi_turn_context))
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()
