def format_birth_line(person):
    birth = person.get("birth", {})
    return (
        f"姓名：{person.get('name', '')}\n"
        f"性别：{person.get('gender', '')}\n"
        f"出生：{birth.get('year')}年{birth.get('month')}月{birth.get('day')}日"
        f"{birth.get('hour', 0)}时{birth.get('minute', 0)}分\n"
        f"地点：{birth.get('place', '')}"
    )


def format_options(options):
    return "\n".join(str(opt) for opt in options)


def format_direct_choice_prompt(case):
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。",
        "请根据命主信息回答四选一题。请直接回答选项字母 A/B/C/D，不要解释。",
        "## 命主信息",
        format_birth_line(case.get("person", {})),
        "## 问题",
        case.get("question", ""),
        "## 选项",
        format_options(case.get("options", [])),
        "请直接回答选项字母。",
    ])


def format_multi_turn_context(case):
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。以下是命主资料，后续问题都围绕此命主。",
        "## 命主信息",
        format_birth_line(case.get("person", {})),
        f"领域：{case.get('domain', 'unknown')}",
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
        format_birth_line(case.get("person", {})),
        "## 三阶段结构化推理协议",
        "第一阶段：量化扫描。清点五行、日主强弱、十神分布、格局倾向、用神喜忌。",
        "第二阶段：冲突定级。识别刑冲合害、空亡、入墓、忌神成局，并判断轻微/中度/严重。",
        "第三阶段：应象映射。将命理结构映射到题目领域和现实事件。",
        "## 问题",
        case.get("question", ""),
        "## 选项",
        format_options(case.get("options", [])),
        "最后一行必须写：答案：A/B/C/D",
    ])
