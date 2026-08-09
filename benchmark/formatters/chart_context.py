"""Phase 6A0 已批准命盘上下文渲染器（schema 版本化，确定性输出）。

确定性契约：同一 case + 同一 schema_version + 同一 as_of_date → 跨进程逐字节一致。
denylist：kong_wang / liu_nian（含 four_pillars.<pillar>.kong_wang 占位键）永不读取。
"""
from __future__ import annotations

import json
import re

from benchmark.formatters.bazi_time_context import (
    TemporalRouteState,
    TimeContext,
    build_time_context,
)
from benchmark.formatters.baziqa_prompt import format_birth_line

CHART_CONTEXT_TEMPLATE_VERSION = "approved_v1"
SCHEMA_VERSIONS = ("legacy_v0", "approved_v1")

APPROVED_BAZI_FIELDS: tuple[str, ...] = (
    "four_pillars",
    "day_master",
    "nayin_wuxing",
    "wuxing_stats",
    "shishen_stats",
    "branch_relations",
    "shensha",
    "da_yun",
    "tai_yuan",
    "ming_gong",
    "shen_gong",
    "true_solar_info",
)
DENYLIST_FIELDS: tuple[str, ...] = ("kong_wang", "liu_nian")

_TEMPORAL_CONTEXT_MARKERS = frozenset({
    "【时间上下文·预计算】",
    "【大运排布】",
    "【目标流年详析】",
})

_PILLAR_ORDER = ("year", "month", "day", "hour")
_PILLAR_LABEL = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
_WUXING_ORDER = ("jin", "mu", "shui", "huo", "tu")
_WUXING_LABEL = {"jin": "金", "mu": "木", "shui": "水", "huo": "火", "tu": "土"}


def render_chart_context(
    case: dict,
    schema_version: str = CHART_CONTEXT_TEMPLATE_VERSION,
    as_of_date: str | None = None,
) -> str:
    """case 为完整题目记录（含 person 与 chart_input）。

    legacy_v0   → 与 format_birth_line(case) 逐字节一致；
    approved_v1 → 身份头 4 行（与 format_birth_line 前 4 行逐字节一致）
                  + 固定模板渲染 chart_input 批准字段；
                  chart_input.ziwei 存在时追加本命紫微宫位段。
    as_of_date 当前不影响 approved_v1 输出（无日期相关批准字段），仅入 manifest。
    """
    if schema_version == "legacy_v0":
        return format_birth_line(case)
    if schema_version != "approved_v1":
        raise ValueError(f"unknown schema_version: {schema_version!r}")
    chart = case.get("chart_input") or {}
    # 按"键存在"渲染：BaziQA enriched 全键（空列表字段也渲染"无"段）；
    # MingLi 归一化输入仅含部分八字键，缺失段跳过（可见性由 profiles 矩阵按 profile 断言）。
    sections = [_identity_header(case)]
    if "four_pillars" in chart:
        sections.append(_render_four_pillars(chart["four_pillars"]))
    if "day_master" in chart:
        sections.append(_render_day_master(chart["day_master"]))
    if "da_yun" in chart:
        sections.append(_render_da_yun(chart["da_yun"], chart.get("dayun_summary") or {}))
    if all(k in chart for k in ("tai_yuan", "ming_gong", "shen_gong")):
        sections.append(_render_three_palaces(chart))
    if "true_solar_info" in chart:
        sections.append(_render_true_solar(chart["true_solar_info"]))
    if "nayin_wuxing" in chart:
        sections.append(_render_nayin(chart["nayin_wuxing"]))
    if "wuxing_stats" in chart:
        sections.append(_render_wuxing_stats(chart["wuxing_stats"]))
    if "shishen_stats" in chart:
        sections.append(_render_shishen_stats(chart["shishen_stats"]))
    if "branch_relations" in chart:
        sections.append(_render_branch_relations(chart["branch_relations"]))
    if "shensha" in chart:
        sections.append(_render_shensha(chart["shensha"]))
    if chart.get("ziwei"):
        sections.append(_render_ziwei(chart["ziwei"]))
    return "\n\n".join(sections) + "\n"


def approved_field_presence(chart_input: dict) -> dict[str, bool]:
    """返回 APPROVED_BAZI_FIELDS 每项在 chart_input 中是否有可用数据。"""
    fp = chart_input.get("four_pillars") or {}
    fp_ok = all(
        key in fp
        and all(
            sub in fp[key]
            for sub in (
                "gan", "zhi", "gan_wuxing", "zhi_wuxing", "shi_shen_gan",
                "shi_shen_zhi_main", "cang_gan", "cang_gan_shi_shen", "nayin",
            )
        )
        for key in _PILLAR_ORDER
    )
    nayin = chart_input.get("nayin_wuxing") or {}
    return {
        "four_pillars": fp_ok,
        "day_master": bool(chart_input.get("day_master")),
        "nayin_wuxing": all(k in nayin for k in _PILLAR_ORDER),
        "wuxing_stats": bool(chart_input.get("wuxing_stats")),
        "shishen_stats": bool(chart_input.get("shishen_stats")),
        "branch_relations": "branch_relations" in chart_input,
        "shensha": "shensha" in chart_input,
        "da_yun": bool(chart_input.get("da_yun")),
        "tai_yuan": bool(chart_input.get("tai_yuan")),
        "ming_gong": bool(chart_input.get("ming_gong")),
        "shen_gong": bool(chart_input.get("shen_gong")),
        "true_solar_info": bool(chart_input.get("true_solar_info")),
    }


def _identity_header(case: dict) -> str:
    """与 format_birth_line 前 4 行逐字节一致（姓名/性别/出生/地点）。"""
    return "\n".join(format_birth_line(case).split("\n")[:4])


def _render_four_pillars(fp: dict) -> str:
    lines = ["【四柱】"]
    for key in _PILLAR_ORDER:
        p = fp[key]
        cang = "、".join(
            f"{gan}({shen})" for gan, shen in zip(p["cang_gan"], p["cang_gan_shi_shen"])
        )
        lines.append(
            f"{_PILLAR_LABEL[key]}：{p['gan']}{p['zhi']}"
            f"（{p['gan']}·{p['gan_wuxing']}／{p['zhi']}·{p['zhi_wuxing']}）"
            f" 十神：{p['shi_shen_gan']}／{p['shi_shen_zhi_main']}（主气）"
            f" 藏干：{cang} 纳音：{p['nayin']}"
        )
    return "\n".join(lines)


def _render_day_master(dm: dict) -> str:
    return (
        "【日主】\n"
        f"日主：{dm['gan']}（{dm['wuxing']}·{dm['yinyang']}）"
        f" 十二长生：{dm['shier_changsheng']}"
    )


def _render_da_yun(da_yun: list, summary: dict) -> str:
    current = summary.get("current_pillar", "")
    if isinstance(current, dict):
        # enriched 实际形状：current_pillar 为 dict（{gan, zhi, ...}），非字符串
        current = f"{current.get('gan', '')}{current.get('zhi', '')}"
    lines = ["【大运】"]
    lines.append(
        f"起运：{summary.get('starting_age', '')}岁（{summary.get('direction', '')}）"
        f" 当前大运：{current}"
    )
    for item in da_yun:
        mark = "〔当前〕" if item.get("is_current") else ""
        lines.append(
            f"{item['index']}. {item['gan']}{item['zhi']}"
            f"（{item['start_age']}-{item['end_age']}岁）"
            f" 十神：{item['shi_shen_gan']}／{item['shi_shen_zhi']}{mark}"
        )
    return "\n".join(lines)


def _render_three_palaces(chart: dict) -> str:
    ty, mg, sg = chart["tai_yuan"], chart["ming_gong"], chart["shen_gong"]
    return (
        "【胎元／命宫／身宫】\n"
        f"胎元：{ty['gan']}{ty['zhi']}（{ty['nayin']}）"
        f" 命宫：{mg['gan']}{mg['zhi']}（{mg['nayin']}）"
        f" 身宫：{sg['gan']}{sg['zhi']}（{sg['nayin']}）"
    )


def _render_true_solar(ts: dict) -> str:
    matched = ts["location_matched"]
    matched_text = ("是" if matched else "否") if isinstance(matched, bool) else str(matched)
    return (
        "【真太阳时校正】\n"
        f"原时间：{ts['original_time']} 校正后：{ts['adjusted_time']}"
        f"（{ts['adjustment_minutes']}分钟，方法：{ts['method']}，地点匹配：{matched_text}）"
    )


def _render_nayin(nayin: dict) -> str:
    return (
        "【纳音五行】\n"
        + "　".join(f"{_PILLAR_LABEL[k]}：{nayin[k]}" for k in _PILLAR_ORDER)
    )


def _render_wuxing_stats(ws: dict) -> str:
    counts = " ".join(f"{_WUXING_LABEL[k]}{ws[k]}" for k in _WUXING_ORDER)
    missing = "、".join(str(x) for x in ws["missing"]) if ws["missing"] else "无"
    return (
        "【五行统计】\n"
        f"{counts}；缺：{missing}；最旺：{ws['strongest']}；最弱：{ws['weakest']}"
    )


def _render_shishen_stats(ss: dict) -> str:
    counts = " ".join(f"{name}{num}" for name, num in ss["counts"].items())
    missing = "、".join(str(x) for x in ss["missing"]) if ss["missing"] else "无"
    return f"【十神统计】\n{counts}；缺：{missing}"


def _render_branch_relations(relations: list) -> str:
    lines = ["【地支关系】"]
    if not relations:
        lines.append("无")
    for rel in relations:
        pillars = rel["pillars"]
        if not isinstance(pillars, str):
            # 兼容 list 形状；enriched 实际为 "day-year" 这类字符串，直接渲染
            pillars = "、".join(str(x) for x in pillars)
        lines.append(f"{rel['type']}：{pillars}（{rel['detail']}）")
    return "\n".join(lines)


def _render_shensha(shensha: list) -> str:
    lines = ["【神煞】"]
    if not shensha:
        lines.append("无")
    for item in shensha:
        lines.append(f"{item['name']}（{item['position']}）：{item['meaning']}")
    return "\n".join(lines)


def _star_names(stars: list) -> str:
    names = [str(s.get("name", "")) if isinstance(s, dict) else str(s) for s in stars]
    return "、".join(n for n in names if n) or "无"


def _fmt_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _render_ziwei(ziwei: dict) -> str:
    info = ziwei["basic_info"]
    lines = ["【紫微斗数·本命】"]
    lines.append(
        f"命宫：{info['ming_gong_gan_zhi']} 身宫：{info['shen_gong_position']}"
        f" 五行局：{info['wu_xing_ju']} 命主：{info['ming_zhu']} 身主：{info['shen_zhu']}"
    )
    for palace in ziwei["twelve_palaces"]:
        mains = "、".join(
            f"{s['name']}（{s['brightness']}）" for s in palace["main_stars"]
        ) or "无"
        sg = "〔身宫〕" if palace.get("is_shengong") else ""
        lines.append(
            f"{palace['name']}（{palace['position']}·{palace['tian_gan']}）{sg}"
            f" 主星：{mains} 辅星：{_star_names(palace['auxiliary_stars'])}"
            f" 大限：{_fmt_value(palace['daxian'])}"
        )
    si_hua = ziwei.get("si_hua")
    if si_hua:
        lines.append("四化：" + json.dumps(si_hua, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def _render_ziwei_mini(ziwei: dict) -> str:
    """Render simplified ziwei context for b2b arm.

    仅保留命宫、身宫、主星，排除 auxiliary_stars、daxian、si_hua 和其他宫位.
    使用固定段标【紫微斗数·精简】、【命宫】、【身宫】、【主星】.
    """
    palaces = ziwei.get("twelve_palaces", [])
    ming_palace = None
    shen_palace = None
    for palace in palaces:
        if palace.get("name") == "命宫":
            ming_palace = palace
        if palace.get("is_shengong") is True:
            shen_palace = palace

    lines = ["【紫微斗数·精简】"]

    # 命宫
    if ming_palace:
        ming_mains = "、".join(
            f"{s['name']}（{s['brightness']}）" for s in ming_palace.get("main_stars", [])
        ) or "无"
        if shen_palace is ming_palace:
            lines.append(f"【命宫】命身同宫 {ming_palace['position']} 主星：{ming_mains}")
        else:
            lines.append(f"【命宫】{ming_palace['position']} 主星：{ming_mains}")
    else:
        lines.append("【命宫】未标注")

    # 身宫（命身同宫时已在命宫行标注，不重复输出段标以外的内容但仍输出标记）
    if shen_palace and shen_palace is not ming_palace:
        shen_mains = "、".join(
            f"{s['name']}（{s['brightness']}）" for s in shen_palace.get("main_stars", [])
        ) or "无"
        lines.append(f"【身宫】{shen_palace['position']} 主星：{shen_mains}")
    elif not shen_palace:
        lines.append("【身宫】未标注")
    # 命身同宫时身宫标记已包含在命宫行，但为满足 visibility required 仍输出段标
    elif shen_palace is ming_palace:
        lines.append("【身宫】命身同宫（见上）")

    # 主星汇总段标（visibility required）
    all_mains = []
    if ming_palace:
        for s in ming_palace.get("main_stars", []):
            all_mains.append(f"{s['name']}（{s['brightness']}）")
    lines.append("【主星】" + ("、".join(all_mains) if all_mains else "无"))

    return "\n".join(lines)


def _render_sequential(case: dict, ziwei: dict) -> str:
    """Render sequential (bazi then ziwei) context for b2c arm.

    第一部分: 八字完整排盘
    分隔线: --- 八字分析结束 ---
    第二部分: 紫微完整排盘
    推理指令: 先八字再紫微综合判断
    """
    birth = format_birth_line(case)
    ziwei_text = _render_ziwei(ziwei)
    instruction = (
        "请先基于八字信息进行初步分析，"
        "再基于紫微斗数信息进行补充判断，"
        "综合两者得出结论。"
    )
    return (
        birth
        + "\n\n--- 八字分析结束 ---\n\n"
        + ziwei_text
        + "\n\n"
        + instruction
    )


def extract_reasoned_choice_answer(raw: str) -> str | None:
    """Parse reasoned choice answer from model output.

    Matches line-final '最终答案：X' (colon-tolerant, case-tolerant, period-tolerant).
    Also handles Markdown variants: **最终答案：X** (bold) and ### 最终答案：X (heading).

    Reasoning models (e.g. deepseek-v4-pro) sometimes put the answer letter on a
    separate line after '最终答案' with no colon (e.g. '### 最终答案\\nB'); this is
    handled by the two-line fallback pattern.

    Returns the LAST match as the canonical answer (design §4.1.2: last 最终答案 wins).
    Returns None when no match found. No fallback to any generic/extended parser.
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    matches = re.findall(
        r"^\s*(?:[#*]+\s*)?最终答案[：:]\s*([A-Da-d])\s*[。.]?\s*[#*]*\s*$",
        text, re.MULTILINE,
    )
    if matches:
        return matches[-1].upper()
    matches = re.findall(
        r"^\s*(?:[#*]+\s*)?最终答案\s*[#*]*\s*\n+\s*\*{0,2}([A-Da-d])\*{0,2}\s*[。.]?\s*$",
        text, re.MULTILINE,
    )
    if matches:
        return matches[-1].upper()
    return None


def format_temporal_context(ctx: TimeContext, include_relations: bool = True) -> str:
    """Format TimeContext as a prompt section string.

    Args:
        ctx: The TimeContext to format.
        include_relations: When True (default), the 目标流年详析 section includes
            the precomputed 地支关系 (六冲/六合/三合/害/刑) and 天干关系 (生克).
            When False (limited injection, 6D 方案 A), only the year + gan/zhi +
            十神 are emitted — the branch/gan relation hints are omitted to avoid
            steering the model toward a single year's 刑冲合害.
    """
    lines = ["【时间上下文·预计算】"]
    if ctx.dayun_table:
        lines.append("【大运排布】")
        for row in ctx.dayun_table:
            lines.append(
                f"{row.gan}{row.zhi}（{row.start_age}-{row.end_age}岁，"
                f"{row.start_year}年起）十神：{row.shishen}"
            )
    if ctx.option_liunian:
        lines.append("【目标流年详析】")
        for opt in ctx.option_liunian:
            if include_relations:
                rels = "、".join(opt.branch_relation) if opt.branch_relation else "无"
                gan_rel = opt.gan_relation or "无"
                lines.append(
                    f"{opt.target_year}年：{opt.gan}{opt.zhi} 十神：{opt.shishen}"
                    f" 地支关系：{rels} 天干关系：{gan_rel}"
                )
            else:
                lines.append(
                    f"{opt.target_year}年：{opt.gan}{opt.zhi} 十神：{opt.shishen}"
                )
    return "\n".join(lines)


def render_reasoned_context(
    case: dict,
    chart_schema_version: str,
    ziwei_arm: str,
    time_context_injection: str = "off",
    route_state=None,
    frozen_target_years: tuple[int, ...] | None = None,
    include_relations: bool = True,
) -> str:
    """Render context for reasoned choice ablation arm.

    Args:
        case: Benchmark case dict (must contain chart_input.ziwei for ziwei
            arms).
        chart_schema_version: Schema version (passed through; not used for
            output branching, but available for isolation assertions).
        ziwei_arm:
            ``"none"`` - format_birth_line(case) only (八字基线, no ziwei).
            ``"only"`` - identity header + 本命紫微盘 (no 四柱, no 日主).
            ``"combined"`` - format_birth_line(case) + 本命紫微盘.
            ``"ziwei_mini"`` - identity header + 精简紫微 (命宫/身宫/主星 only).
            ``"sequential"`` - 八字 + 分隔 + 紫微 + 顺序推理指令.
        time_context_injection: ``"off"`` (default) skips temporal context;
            ``"on"`` appends temporal context per ``route_state``.
        route_state: ``TemporalRouteState`` or its string value; only used
            when ``time_context_injection == "on"``.

    Returns:
        Rendered context string.

    Raises:
        ValueError: If *ziwei_arm* is not one of ``"none"``, ``"only"``,
            ``"combined"``, ``"ziwei_mini"``, ``"sequential"``.
    """
    if ziwei_arm == "none":
        result = format_birth_line(case)
    else:
        identity = _identity_header(case)
        ziwei_data = case.get("chart_input", {}).get("ziwei", {})

        if ziwei_arm == "only":
            ziwei_text = _render_ziwei(ziwei_data)
            result = identity + "\n\n" + ziwei_text
        elif ziwei_arm == "combined":
            birth = format_birth_line(case)
            ziwei_text = _render_ziwei(ziwei_data)
            result = birth + "\n\n" + ziwei_text
        elif ziwei_arm == "ziwei_mini":
            ziwei_text = _render_ziwei_mini(ziwei_data)
            result = identity + "\n\n" + ziwei_text
        elif ziwei_arm == "sequential":
            result = _render_sequential(case, ziwei_data)
        else:
            raise ValueError(
                f"Unknown ziwei_arm: {ziwei_arm!r}. "
                "Expected one of: none, only, combined, ziwei_mini, sequential."
            )

    # time_context_injection "on" (full) or "on_limited" (方案 A: no relations)
    if time_context_injection in ("on", "on_limited") and route_state is not None:
        state = route_state
        if isinstance(state, str):
            state = TemporalRouteState(state)
        if state != TemporalRouteState.NOT_ROUTED:
            ctx = build_time_context(case, state, frozen_target_years=frozen_target_years)
            if ctx is not None:
                effective_include = (
                    include_relations if time_context_injection == "on"
                    else False
                )
                result = result + "\n\n" + format_temporal_context(
                    ctx, include_relations=effective_include
                )

    return result
