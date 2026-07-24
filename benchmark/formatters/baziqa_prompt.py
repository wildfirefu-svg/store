def format_birth_line(case):
    if not isinstance(case, dict):
        person = {}
    elif "person" in case:
        person = case.get("person") or {}
    else:
        person = case
    birth = person.get("birth", {})
    lines = [
        f"姓名：{person.get('name', '')}",
        f"性别：{person.get('gender', '')}",
        f"出生：{birth.get('year')}年{birth.get('month')}月{birth.get('day')}日"
        f"{birth.get('hour', 0)}时{birth.get('minute', 0)}分",
        f"地点：{birth.get('place', '')}",
    ]
    chart = case.get("chart_input") or {} if isinstance(case, dict) else {}
    fp = chart.get("four_pillars") or {}
    if fp:
        pillar_names = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
        pillars = []
        for name in ("year", "month", "day", "hour"):
            p = fp.get(name) or {}
            gan = p.get("gan", "")
            zhi = p.get("zhi", "")
            if gan or zhi:
                pillars.append(f"{pillar_names[name]} {gan}{zhi}")
        if pillars:
            lines.append("四柱：" + "，".join(pillars))
        dm = chart.get("day_master") or {}
        if dm.get("gan"):
            lines.append(f"日主：{dm.get('gan')}（{dm.get('wuxing', '')}，{dm.get('yinyang', '')}）")
    return "\n".join(lines)


def format_options(options):
    return "\n".join(str(opt) for opt in options)


def format_direct_choice_prompt(case, chart_context_text=None):
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。",
        "请根据命主信息回答四选一题。请直接回答选项字母 A/B/C/D，不要解释。",
        "## 命主信息",
        chart_context_text or format_birth_line(case),
        "## 问题",
        case.get("question", ""),
        "## 选项",
        format_options(case.get("options", [])),
        "请直接回答选项字母。",
    ])


def format_direct_c2_prompt(case, option_scores):
    score_lines = []
    for item in option_scores or []:
        support = item.get("support") or []
        reject = item.get("reject") or []
        parts = []
        if support:
            parts.append("support: " + ", ".join(support[:3]))
        if reject:
            parts.append("reject: " + ", ".join(reject[:3]))
        reason_text = f" [{'; '.join(parts)}]" if parts else ""
        score_lines.append(
            f"{item.get('label')}. {item.get('text')} -> "
            f"{item.get('score')}/100 ({item.get('verdict')}){reason_text}"
        )
    summary = " | ".join(
        f"{item.get('label')}={item.get('score')} {item.get('verdict')}"
        for item in option_scores or []
    )
    evidence = "\n".join(
        ["【逐选项命理评分】", *score_lines, "", "【逐选项评分汇总】", summary]
    )
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。",
        "请根据命主信息、RAG 证据和逐选项命理评分回答四选一题。请直接回答选项字母 A/B/C/D，不要解释。",
        "逐选项命理评分是结构化参考证据，不得仅因某选项分数最高而选择。",
        "## 命主信息",
        format_birth_line(case),
        "## 问题",
        case.get("question", ""),
        "## 选项",
        format_options(case.get("options", [])),
        "## C2 参考证据",
        evidence,
        "请直接回答选项字母。",
    ])


def format_multi_turn_context(case, chart_context_text=None):
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。以下是命主资料，后续问题都围绕此命主。",
        "## 命主信息",
        chart_context_text or format_birth_line(case),
        f"领域：{case.get('domain', 'unknown')}",
    ])


def _assemble_reasoned_choice_prompt(case: dict, context_text: str) -> str:
    """Assemble the full reasoned-choice prompt (design §4.1.2).

    Appends reasoning instructions requiring the model to produce a structured
    analysis before giving the final answer line.  The *context_text* is the
    output of ``render_reasoned_context()``.
    """
    instruction = (
        "## 输出要求\n"
        "请先进行推理分析，然后给出最终答案。最后一行必须严格为：\n"
        "最终答案：X\n"
        "其中 X 为 A、B、C 或 D 之一。"
    )
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。",
        "请根据命主信息，通过推理分析后回答四选一题。",
        "## 命主信息",
        context_text,
        "## 问题",
        case.get("question", ""),
        "## 选项",
        format_options(case.get("options", [])),
        instruction,
    ])


def format_multi_turn_question(case):
    return "\n\n".join([
        "请回答以下四选一问题，只输出选项字母 A/B/C/D。",
        case.get("question", ""),
        format_options(case.get("options", [])),
    ])


def format_structured_reasoning_prompt(case):
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。必须按三阶段结构化推理后再作答。",
        "## 命主信息",
        format_birth_line(case),
        "## 三阶段结构化推理协议",
        "第一阶段：量化扫描。清点五行、日主强弱、十神分布、格局倾向、用神喜忌。",
        "第二阶段：冲突定级。识别刑冲合害、空亡、入墓、忌神成局，并判断轻微/中度/严重。",
        "第三阶段：应象映射。将命理结构映射到题目领域和现实事件。",
        "## 问题",
        case.get("question", ""),
        "## 选项",
        format_options(case.get("options", [])),
        "## 输出格式",
        "先给出四个选项的置信度，每行一个选项，分数必须是 0 到 100 的整数：",
        "A: 0-100",
        "B: 0-100",
        "C: 0-100",
        "D: 0-100",
        "最终答案必须选择置信度最高的选项；如分数并列，选择命理证据更直接的一项。",
        "最后一行只能写：最终答案：X，其中 X 是 A/B/C/D 之一。",
    ])
