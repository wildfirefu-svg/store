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
    prompt_style: str        # "official" | "xjz_direct" | "xjz_reasoned"
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
        EvalProfile("baziqa_xjz_reasoned",
                    "baziqa", "xjz_reasoned", "direct", "legacy_v0", "baziqa_macro"),
        EvalProfile("baziqa_xjz_dual",
                    "baziqa", "xjz_dual", "direct", "legacy_v0", "baziqa_macro"),
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
    if profile.prompt_style == "xjz_dual":
        return "dual_system"
    return "multi_turn" if profile.interaction_mode == "multi_turn" else "direct_choice"


_FORMATTER_MAP = {
    ("baziqa", "official", "multi_turn"): "format_multi_turn",
    ("baziqa", "xjz_direct", "direct"): "format_direct_choice_prompt",
    ("baziqa", "xjz_reasoned", "direct"): "format_reasoned_choice_prompt",
    ("baziqa", "xjz_dual", "direct"): "format_dual_system_prompt",
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
# judge 阶段专用：裸宫位名会误杀命理散文（婚姻题"夫妻二人"、财运题"财帛"等自然表述），
# 改用宫位标签形式（渲染为"夫妻（戌·丙）"）；仅 judge 提示词含推理散文，其余分支保持裸名
_ZIWEI_MARKERS_PROSE_SAFE = frozenset({"【紫微斗数·本命】", "夫妻（", "财帛（", "官禄（"})
_DENYLIST_MARKERS = frozenset({"【流年】", "空亡：", "空亡（"})
_TEMPORAL_CONTEXT_MARKERS = frozenset({
    "【时间上下文·预计算】",
    "【大运排布】",
    "【目标流年详析】",
})
# 裁决 1B：官方臂独立 required（结构性 astro 标记，astro 块注入即恒真，
# 不依赖有星宫位，避免误杀）；不与 mingli_xjz_direct 共享 required。
_OFFICIAL_ASTRO_MARKERS = frozenset({"八字命盘信息：", "紫微命盘信息：", "十二宫位星曜分布："})
_APPROVED_ONLY_MARKERS = frozenset({
    "【四柱】", "【日主】", "【大运】", "【神煞】", "【紫微斗数·本命】",
    "【胎元／命宫／身宫】", "【真太阳时校正】", "【纳音五行】", "【五行统计】",
    "【十神统计】", "【地支关系】",
})
_APPROVED_BAZI_MARKERS_NO_ZIWEI = _APPROVED_BAZI_MARKERS - {"【紫微斗数·本命】"}


def _visibility_base(
    profile: EvalProfile, chart_schema_version: str,
    ziwei_arm: str | None = None,
    stage: str | None = None,
) -> tuple[frozenset[str], frozenset[str]]:
    """Base visibility (profile/schema/ziwei_arm/stage) without temporal rules."""
    if ziwei_arm is not None:
        # Three-arm reasoned visibility matrix (design §6).
        # render_reasoned_context() ignores chart_schema_version - all three arms
        # produce identical marker output regardless of legacy_v0 vs approved_v1.
        # The marker sets below are therefore version-independent.
        if ziwei_arm == "none":
            # format_birth_line(case) only - no section markers at all.
            return frozenset(), _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS
        if ziwei_arm == "only":
            # identity header + 【紫微斗数·本命】only.
            return (
                frozenset({"【紫微斗数·本命】"}),
                _APPROVED_BAZI_MARKERS | _DENYLIST_MARKERS,
            )
        if ziwei_arm == "combined":
            # format_birth_line + 【紫微斗数·本命】.
            # format_birth_line uses no section markers, so only ziwei appears.
            return frozenset({"【紫微斗数·本命】"}), _DENYLIST_MARKERS
        if ziwei_arm == "ziwei_mini":
            # b2b: 精简紫微, required 4 个段标
            # forbidden: 真实裸名次要宫位 + 八字关键词 + _DENYLIST_MARKERS
            _B2B_FORBIDDEN_PALACES = frozenset({
                "父母", "福德", "田宅", "官禄", "仆役", "迁移",
                "疾厄", "财帛", "子女", "夫妻", "兄弟",
            })
            return (
                frozenset({"【紫微斗数·精简】", "【命宫】", "【身宫】", "【主星】"}),
                _B2B_FORBIDDEN_PALACES | frozenset({"四柱", "日主", "大运", "神煞"})
                | _DENYLIST_MARKERS,
            )
        if ziwei_arm == "sequential":
            # b2c: 顺序推理, required 八字+紫微+分隔线+指令
            # forbidden: 继承 combined 臂的 _DENYLIST_MARKERS（不能为空）
            return (
                frozenset({"【紫微斗数·本命】", "--- 八字分析结束 ---",
                           "请先基于八字信息进行初步分析"}),
                _DENYLIST_MARKERS,
            )
        if ziwei_arm == "judge":
            return frozenset(), _APPROVED_BAZI_MARKERS | _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS
        raise NotImplementedError(f"Unknown ziwei_arm: {ziwei_arm!r}")
    # Dual system stage-specific rules (no ziwei_arm, use stage)
    if stage == "bazi":
        return frozenset(), _ZIWEI_MARKERS | _DENYLIST_MARKERS
    if stage == "ziwei":
        return frozenset({"【紫微斗数·本命】"}), _APPROVED_BAZI_MARKERS_NO_ZIWEI | _DENYLIST_MARKERS
    if stage == "judge":
        # Blinded judge: no raw chart markers at all（散文安全变体：宫位名用标签形式，
        # 避免误杀推理散文中的"夫妻/财帛/官禄"自然表述--真实缺陷证据：2025 Q9 同性婚姻题
        # gate_blocked 导致 BAZI_COUNT=0 切片失败）
        return frozenset(), _APPROVED_BAZI_MARKERS | _ZIWEI_MARKERS_PROSE_SAFE | _DENYLIST_MARKERS
    if chart_schema_version == "legacy_v0":
        # 旧上下文对照臂：自身 schema 由渲染器逐字节等价保证；此处只做串扰检测。
        return frozenset(), _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS
    if chart_schema_version == "approved_v1":
        if profile.profile_id == "mingli_official_cot_astro":
            # 裁决 1B：官方臂 required 按 profile_id 独立，不随 dataset 共享。
            return _OFFICIAL_ASTRO_MARKERS, _DENYLIST_MARKERS
        if profile.dataset == "mingli":
            # 决策记录 3 + 裁决 1B：xjz 臂维持六段标+紫微；真实数据 0 结构化
            # bazi -> 必然 BLOCKED_PRECONDITION，缺口如实入报告。
            return _MINGLI_BAZI_CORE_MARKERS | _ZIWEI_MARKERS, _DENYLIST_MARKERS
        return _APPROVED_BAZI_MARKERS, _DENYLIST_MARKERS
    raise SystemExit(f"未知 chart_schema_version: {chart_schema_version!r}")


def visibility_requirements(
    profile: EvalProfile | None = None,
    chart_schema_version: str | None = None,
    ziwei_arm: str | None = None,
    stage: str | None = None,
    time_context_injection: str = "off",
    route_state: str | None = None,
) -> tuple[frozenset[str], frozenset[str]]:
    """Returns (required_markers, denied_markers).

    Temporal context visibility (6D v1 Task 6):
    - ``time_context_injection="off"``: all temporal markers denied.
    - ``time_context_injection="on"`` + ``route_state``:
      - NOT_ROUTED (or None): all temporal markers denied.
      - ROUTED_WITHOUT_TARGETS: 【时间上下文·预计算】 + 【大运排布】 required;
        【目标流年详析】 denied.
      - ROUTED_WITH_TARGETS: all 3 temporal markers required.
    """
    if profile is not None and chart_schema_version is not None:
        required, forbidden = _visibility_base(
            profile, chart_schema_version, ziwei_arm, stage)
    else:
        required, forbidden = frozenset(), frozenset()

    if time_context_injection == "off":
        forbidden = forbidden | _TEMPORAL_CONTEXT_MARKERS
    elif time_context_injection == "on":
        if route_state is None or route_state == "NOT_ROUTED":
            forbidden = forbidden | _TEMPORAL_CONTEXT_MARKERS
        elif route_state == "ROUTED_WITHOUT_TARGETS":
            required = required | frozenset({
                "【时间上下文·预计算】",
                "【大运排布】",
            })
            forbidden = forbidden | frozenset({"【目标流年详析】"})
        elif route_state == "ROUTED_WITH_TARGETS":
            required = required | _TEMPORAL_CONTEXT_MARKERS

    return required, forbidden


def assert_visibility(
    rendered_text: str, profile: EvalProfile | None = None,
    chart_schema_version: str | None = None,
    ziwei_arm: str | None = None, stage: str | None = None,
    time_context_injection: str = "off",
    route_state: str | None = None,
) -> list[str]:
    """渲染文本上的 required/forbidden 子串断言，返回违规列表（空表 = 通过）。"""
    required, forbidden = visibility_requirements(
        profile, chart_schema_version, ziwei_arm, stage,
        time_context_injection, route_state)
    violations = [f"required 缺失: {m}" for m in sorted(required) if m not in rendered_text]
    violations += [f"forbidden 命中: {m}" for m in sorted(forbidden) if m in rendered_text]
    return violations


def visibility_gate(
    rendered_text: str, profile: EvalProfile | None = None,
    chart_schema_version: str | None = None,
    ziwei_arm: str | None = None, stage: str | None = None,
    time_context_injection: str = "off",
    route_state: str | None = None,
) -> str:
    """runner 短路契约（裁决 1B）：返回 "PASS" | "BLOCKED_PRECONDITION"；
    BLOCKED_PRECONDITION 时 runner 禁止任何模型调用（Task 6 接线并以零调用测试断言）。"""
    if assert_visibility(rendered_text, profile, chart_schema_version,
                         ziwei_arm, stage, time_context_injection, route_state):
        return "BLOCKED_PRECONDITION"
    return "PASS"


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
                  mingli_prompt.OFFICIAL_SYSTEM_PROMPT,
                  inspect.getsource(mingli_prompt.format_official_cot_prompt)]
    elif formatter == "format_direct_choice_prompt":
        parts.append(inspect.getsource(baziqa_prompt.format_direct_choice_prompt))
    elif formatter == "format_reasoned_choice_prompt":
        from benchmark.formatters import chart_context as cc
        parts += [
            inspect.getsource(cc.render_reasoned_context),
            inspect.getsource(
                baziqa_prompt._assemble_reasoned_choice_prompt
            ),
            inspect.getsource(cc.extract_reasoned_choice_answer),
        ]
    elif formatter == "format_dual_system_prompt":
        from benchmark.formatters import dual_system_reasoning as ds
        from benchmark.formatters.baziqa_prompt import (
            _assemble_reasoned_choice_prompt,
            format_options,
        )
        from benchmark.formatters.chart_context import (
            extract_reasoned_choice_answer,
            render_reasoned_context,
        )
        parts += [
            ds.JUDGE_TEMPLATE_VERSION,
            inspect.getsource(ds.build_bazi_pipeline_prompt),
            inspect.getsource(ds.build_ziwei_pipeline_prompt),
            inspect.getsource(ds.build_judge_prompt),
            inspect.getsource(ds.extract_judge_answer),
            inspect.getsource(ds.judge_swap_seed),
            inspect.getsource(render_reasoned_context),
            inspect.getsource(_assemble_reasoned_choice_prompt),
            inspect.getsource(extract_reasoned_choice_answer),
            inspect.getsource(format_options),
        ]
    else:  # format_multi_turn
        parts.append(inspect.getsource(baziqa_prompt.format_multi_turn_context))
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()
