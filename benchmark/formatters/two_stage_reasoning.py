# -*- coding: utf-8 -*-
"""Two-stage reasoning formatter for Phase 4.

Stage 1: Label-blind reasoning (no A/B/C/D labels, can see option text).
Stage 2: Option matching with evidence.
"""

import hashlib
import random
import re
from typing import List, Optional

# Time/location keywords for identifying time-location questions
_TIME_KEYWORDS = [
    "哪年", "何时", "什么时候", "时间", "年份", "何年", "哪一年",
    "几年", "几时", "何時", "那年", "多久", "大运", "流年",
    "岁运", "年运", "年份",
]

# Stage 1 prompt template (normal mode with options)
_STAGE1_PROMPT_TEMPLATE = """你是一位严谨的八字命理评测助手。

## 命主信息
{birth_line}

## 问题
{question}

## 选项（仅作参考，禁止引用选项编号）
{options}

## 任务要求
请按以下结构化推理协议进行分析，然后直接给出你对问题答案的推断：

### 第一阶段：量化扫描
清点五行、日主强弱、十神分布、格局倾向、用神喜忌。

### 第二阶段：冲突定级
识别刑冲合害、空亡、入墓、忌神成局，并判断轻微/中度/严重。

### 第三阶段：应象映射
将命理结构映射到题目领域和现实事件。
{time_phase}

不要引用"选项1""选项2"等编号，直接描述内容。

请在最后一行以如下格式输出你的推断：
【内容假设】：你的推断内容
"""

# Stage 1 prompt template (Experiment A: no options, neutral description only)
_STAGE1_PROMPT_TEMPLATE_EXP_A = """你是一位严谨的八字命理评测助手。

## 命主信息
{birth_line}

## 问题
{question}

## 任务要求（重要：不看选项，只分析命局结构）
请按以下结构化推理协议进行分析，然后直接给出你对问题答案的推断：

### 第一阶段：量化扫描
清点五行、日主强弱、十神分布、格局倾向、用神喜忌。

### 第二阶段：冲突定级
识别刑冲合害、空亡、入墓、忌神成局，并判断轻微/中度/严重。

### 第三阶段：应象映射
将命理结构映射到题目领域和现实事件。
{time_phase}

**输出约束（极其重要）**：
- 你**没有看到任何选项**，只能基于命局结构进行纯命理分析。
- 不要引用任何选项编号（如"选项1""选项2"），也不要引用选项中的具体内容。
- 输出必须是**中性命理描述**，例如："该事件应发生在印星受克、忌神成局的大运流年"。
- 不要输出"答案是A""选B"等直接选择某个选项的内容。
- 你的推断应该聚焦于命理结构特征（五行、十神、刑冲合害、用神喜忌），让 Stage 2 根据你的描述去匹配选项。

请在最后一行以如下格式输出你的推断：
【内容假设】：你的中性命理推断内容
"""

def _build_dayun_summary_for_stage1(case: dict) -> str:
    """Build a concise dayun summary string for Stage 1 prompt injection.

    Returns pre-computed dayun data as a formatted string, or empty string
    if no dayun data available.
    """
    chart = case.get("chart_input") or {}
    da_yun = chart.get("da_yun") or []
    if not da_yun:
        return ""

    lines = ["【预计算大运排布（系统精确计算，请以此为依据）】"]
    dayun_summary = chart.get("dayun_summary", {})
    direction = dayun_summary.get("direction", "未知")
    starting_age = dayun_summary.get("starting_age", 0)
    lines.append(f"起运方向：{direction}，起运年龄：{starting_age}岁")
    lines.append("大运列表：")
    for dy in da_yun:
        lines.append(
            f"  {dy.get('index', 0)}. {dy.get('gan', '')}{dy.get('zhi', '')} "
            f"({dy.get('start_age', 0)}-{dy.get('end_age', 0)}岁, "
            f"{dy.get('shi_shen_gan', '')}/{dy.get('shi_shen_zhi', '')})"
        )
    return "\n".join(lines)


# Time-location phase 4 instruction (injected into stage 1 when time question)
_TIME_PHASE_INSTRUCTION = """
### 第四阶段：时间定位（大运锚定 → 流年验证）
由于本题涉及时间定位，必须在第三阶段之后继续执行以下两步：

**Step 1 — 大运锚定**：
- 根据命主出生年份和性别，推算大运排布（顺排/逆排）。
- 判断事件最可能落在哪个10年大运区间。
- 输出格式：事件发生在第 X 步大运（YYYY-YYYY）
- 说明理由：该大运的干支与命局形成了何种作用关系（如刑冲合害、用神受制、忌神成局等）。

**Step 2 — 流年验证**：
- 在已锚定的大运区间内，分析各流年天干地支与命局的互动。
- 找出最符合第三阶段应象映射的流年特征（如"印星受克的流年"、"夫妻宫被冲动的流年"）。
- 输出格式：重点流年为 YYYY 年（XX流年），触发条件是……
- 明确说明该流年的命理结构特征。

**输出约束（重要）**：
- 大运锚定必须给出具体的大运区间（如"第3步大运（2003-2012）"）。
- 流年验证必须给出具体的流年年份（如"重点流年2007丁亥年"）。
- 你的推断应包含：大运区间 + 流年年份 + 命理结构特征（五行、十神、刑冲合害、用神喜忌）。
- 时间定位是核心任务，不要回避具体年份。"""


def is_time_location_question(question: str, options: List[str]) -> bool:
    """Check if a question is time/location related.

    Returns True if:
    - Question contains time-related keywords (哪年, 何时, etc.)
    - Options are all 4-digit years (e.g., 1989, 1990, 2011, 2021)
    """
    if not question:
        return False

    # Check for time keywords
    for kw in _TIME_KEYWORDS:
        if kw in question:
            return True

    # Check if all options are 4-digit years
    year_pattern = re.compile(r"^\d{4}$")
    cleaned_options = []
    for opt in options:
        # Strip prefix like "A. ", "B. " etc.
        cleaned = re.sub(r"^[A-D]\.\s*", "", opt).strip()
        cleaned_options.append(cleaned)

    if len(cleaned_options) >= 2 and all(year_pattern.match(o) for o in cleaned_options):
        return True

    return False


# Stage 2 prompt template
_STAGE2_PROMPT_TEMPLATE = """你是一位严谨的八字命理评测助手。

## 命主信息
{birth_line}

## 问题
{question}

## 选项
{options}

{hypothesis_section}
## 证据（预计算数据，准确可靠，请以以下数据为准）
{evidence}

## 任务要求
请基于上述**证据中的预计算数据**进行独立分析，从 A/B/C/D 中选择一个最符合的选项。

**重要提醒**：
- 证据中的【预计算大运数据】和【各选项对应大运流年详析】是系统精确计算的结果，**请务必以预计算数据为准**。
- 你的分析必须基于预计算数据中的大运排布、流年干支、十神、刑冲合害关系进行。
{time_instruction}

## 输出格式要求
请先进行详细推理分析（包括大运对照、逐项验证、排除法等），然后在最后一行以如下格式给出最终答案：
最终答案：X（X为A/B/C/D中的一个）"""

# Stage 2 hypothesis section template (used when hypothesis is provided)
_STAGE2_HYPOTHESIS_SECTION = """## Stage 1 推断假设（仅供参考，可能不准确）
{hypothesis}

"""

# Stage 2 time-location enhancement instruction
_STAGE2_TIME_INSTRUCTION = """## 时间定位验证（重要）
Stage 1 的推断假设是中性命理描述，未包含具体年份，且可能因自行推算大运而产生错误。**预计算数据中的大运排布和流年信息是准确的，请以预计算数据为准。**

### 强制步骤（必须按此执行）
1. **构建大运对照表**：使用证据中的【预计算大运数据】和【各选项对应大运流年详析】，为每个选项列出：
   - 选项A：年份/年龄 → 大运干支（以预计算数据为准） → 与命局作用关系
   - 选项B：年份/年龄 → 大运干支（以预计算数据为准） → 与命局作用关系
   - 选项C：年份/年龄 → 大运干支（以预计算数据为准） → 与命局作用关系
   - 选项D：年份/年龄 → 大运干支（以预计算数据为准） → 与命局作用关系

2. **逐项验证**：将问题涉及的命理结构（如"印星受克"、"忌神成局"、"刑冲合害"、"夫妻宫引动"等）与每个选项时间点的**预计算流年和大运数据**逐一验证，明确标注"符合"或"不符合"。

3. **流年精确定位**：在符合的选项中，进一步用预计算数据中的流年天干地支、十神、与命局及大运的刑冲合害关系精确定位最可能的年份。

4. **排除法**：若某选项的时间点明显与命理结构矛盾，直接排除。

5. **必须给出明确选择**：基于预计算数据的分析，选择最符合的选项，禁止因为"无法确定"而选择最后一个选项。你的回答必须包含明确的选项字母。"""


def _format_birth_line(case: dict) -> str:
    """Format birth line from case (reuse logic from baziqa_prompt)."""
    person = case.get("person", {}) if isinstance(case, dict) else {}
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


def format_stage1_prompt(case: dict, exp_a: bool = False) -> str:
    """Format Stage 1 (label-blind) prompt.

    - No A/B/C/D labels
    - Options shuffled with fixed seed (case_id hash)
    - Options shown as 选项1, 选项2, etc.
    - Time-location questions get special instruction
    - exp_a: Experiment A mode (no options shown, neutral description only)
    """
    birth_line = _format_birth_line(case)
    question = case.get("question", "")
    options = case.get("options", [])

    # Time-location phase instruction (injected as phase 4)
    time_phase = ""
    if is_time_location_question(question, options):
        time_phase = _TIME_PHASE_INSTRUCTION

    if exp_a:
        # Experiment A: no options shown, force neutral description
        return _STAGE1_PROMPT_TEMPLATE_EXP_A.format(
            birth_line=birth_line,
            question=question,
            time_phase=time_phase,
        )
    else:
        # Normal mode: show options
        # Shuffle options with fixed seed based on case_id hash
        case_id = case.get("case_id", "")
        seed = int(hashlib.md5(case_id.encode()).hexdigest(), 16) % (2**32)
        shuffled = options[:]
        random.Random(seed).shuffle(shuffled)

        # Format options without A/B/C/D labels
        formatted_options = []
        for i, opt in enumerate(shuffled, start=1):
            # Strip A/B/C/D prefix if present
            cleaned = re.sub(r"^[A-D]\.\s*", "", opt).strip()
            formatted_options.append(f"选项{i}：{cleaned}")

        return _STAGE1_PROMPT_TEMPLATE.format(
            birth_line=birth_line,
            question=question,
            options="\n".join(formatted_options),
            time_phase=time_phase,
        )


def format_stage2_prompt(case: dict, hypothesis: Optional[str] = None, evidence: List[str] = None, is_time: bool = False) -> str:
    """Format Stage 2 (option matching) prompt.

    - Includes A/B/C/D labels
    - Includes Stage 1 hypothesis (if provided)
    - Includes evidence
    - Includes conflict arbitration instruction
    - For time-location questions, injects time-anchor verification instruction
    """
    birth_line = _format_birth_line(case)
    question = case.get("question", "")
    options = case.get("options", [])

    formatted_options = "\n".join(str(opt) for opt in options)
    formatted_evidence = "\n".join(str(e) for e in evidence) if evidence else "（无额外证据）"

    # Build hypothesis section (empty if no hypothesis provided)
    if hypothesis and hypothesis.strip():
        hypothesis_section = _STAGE2_HYPOTHESIS_SECTION.format(hypothesis=hypothesis)
    else:
        hypothesis_section = ""

    time_instruction = _STAGE2_TIME_INSTRUCTION if is_time else ""

    return _STAGE2_PROMPT_TEMPLATE.format(
        birth_line=birth_line,
        question=question,
        options=formatted_options,
        hypothesis_section=hypothesis_section,
        evidence=formatted_evidence,
        time_instruction=time_instruction,
    )


def parse_stage1_result(raw: str) -> Optional[str]:
    """Parse Stage 1 result to extract hypothesis.

    Priority:
    1. 【内容假设】：marker
    2. Fallback: "结论：", "假设：", "判断："
    3. No recognized marker → None
    """
    if not raw or not raw.strip():
        return None

    # Priority 1: 【内容假设】 marker
    marker_match = re.search(r"【内容假设】[：:]\s*(.+)", raw, re.DOTALL)
    if marker_match:
        return marker_match.group(1).strip()

    # Priority 2: fallback prefixes
    fallback_match = re.search(r"(?:结论|假设|判断)[：:]\s*(.+)", raw, re.DOTALL)
    if fallback_match:
        return fallback_match.group(1).strip()

    # Priority 3: fallback to last non-empty line
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if lines:
        return lines[-1]

    return None


def _get_liunian_for_year(chart: dict, year: int) -> Optional[dict]:
    """Get liu_nian (流年) data for a specific year."""
    liu_nian = chart.get("liu_nian") or []
    for ln in liu_nian:
        if ln.get("year") == year:
            return ln
    return None


def _compute_branch_relation(zhi1: str, zhi2: str) -> List[str]:
    """Compute branch relations between two zhi (地支).
    Returns list of relation descriptions.
    """
    relations = []
    # 六冲
    chong = {
        ("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"),
        ("辰", "戌"), ("巳", "亥"),
    }
    # 六合
    liuhe = {
        ("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"),
        ("巳", "申"), ("午", "未"),
    }
    # 三合 (partial match - any two of the three)
    sanhe = [
        {"申", "子", "辰"}, {"寅", "午", "戌"}, {"巳", "酉", "丑"}, {"亥", "卯", "未"},
    ]
    # 六害
    liuhai = {
        ("子", "未"), ("丑", "午"), ("寅", "巳"), ("卯", "辰"),
        ("申", "亥"), ("酉", "戌"),
    }
    # 三刑
    sanxing = [
        {"寅", "巳", "申"}, {"丑", "戌", "未"},
    ]

    pair = (zhi1, zhi2)
    pair_rev = (zhi2, zhi1)

    if pair in chong or pair_rev in chong:
        relations.append("冲")
    if pair in liuhe or pair_rev in liuhe:
        relations.append("合")
    if pair in liuhai or pair_rev in liuhai:
        relations.append("害")
    for group in sanhe:
        if zhi1 in group and zhi2 in group:
            relations.append("三合")
            break
    for group in sanxing:
        if zhi1 in group and zhi2 in group:
            relations.append("刑")
            break

    return relations


# Wuxing generation cycle for computing gan relations
_WUXING_CYCLE = {
    "金": {"生": "水", "克": "木", "被生": "土", "被克": "火"},
    "木": {"生": "火", "克": "土", "被生": "水", "被克": "金"},
    "水": {"生": "木", "克": "火", "被生": "金", "被克": "土"},
    "火": {"生": "土", "克": "金", "被生": "木", "被克": "水"},
    "土": {"生": "金", "克": "水", "被生": "火", "被克": "木"},
}

# Gan to wuxing mapping
_GAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# Shishen mapping for day master (simplified - only primary relations)
# This is a helper for evidence building, not a full shishen calculator
_SHISHEN_LABELS = ["比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"]


def _compute_gan_relation(gan1: str, gan2: str) -> str:
    """Compute relation between two gan (天干) based on wuxing.
    Returns a description like '生', '克', '被生', '被克', '同'.
    """
    wx1 = _GAN_WUXING.get(gan1, "")
    wx2 = _GAN_WUXING.get(gan2, "")
    if not wx1 or not wx2:
        return ""
    if wx1 == wx2:
        return "同"
    cycle = _WUXING_CYCLE.get(wx1, {})
    if cycle.get("生") == wx2:
        return f"{gan1}生{gan2}"
    if cycle.get("克") == wx2:
        return f"{gan1}克{gan2}"
    if cycle.get("被生") == wx2:
        return f"{gan2}生{gan1}"
    if cycle.get("被克") == wx2:
        return f"{gan2}克{gan1}"
    return ""


def _get_question_type_hints(question: str) -> List[str]:
    """Get domain-specific hints based on question content."""
    hints = []
    q = question.lower()

    # Family-related
    if any(kw in q for kw in ["母亲", "妈妈", "母", "离世", "去世", "亡"]):
        hints.append("母亲对应正印/偏印，需关注印星受克、财星破印")
    if any(kw in q for kw in ["父亲", "爸爸", "父"]):
        hints.append("父亲对应偏财/正财，需关注财星受损、比劫夺财")

    # Marriage-related
    if any(kw in q for kw in ["结婚", "嫁", "婚", "配偶", "妻子", "丈夫", "老公", "老婆"]):
        hints.append("婚姻对应正官/七杀（夫星）或正财/偏财（妻星），需关注夫妻宫引动、夫星/妻星出现")
    if any(kw in q for kw in ["离婚", "分居", "感情破裂"]):
        hints.append("离婚对应夫妻宫被冲、财星/官星受损、伤官见官")

    # Career/wealth-related
    if any(kw in q for kw in ["官非", "刑事", "牢狱", "警察", "官司", "拘留"]):
        hints.append("官非对应七杀攻身、伤官见官、财生杀旺")
    if any(kw in q for kw in ["事业", "工作", "职业", "创业", "升职", "变动"]):
        hints.append("事业对应正官/七杀、印星，需关注官星变化、印星受损")
    if any(kw in q for kw in ["财", "赚钱", "收入", "破财"]):
        hints.append("财运对应正财/偏财，需关注财星透干、比劫夺财")

    # Health-related
    if any(kw in q for kw in ["病", "健康", "抑郁", "手术", "住院"]):
        hints.append("健康对应日主强弱、印星状态，需关注忌神攻身、用神受损")

    # Travel/moving
    if any(kw in q for kw in ["搬迁", "搬家", "出国", "移民", "迁移"]):
        hints.append("迁移对应驿马、流年冲动日支或迁移宫")

    return hints


# Key shensha names relevant to common life events (shared with dayun evidence)
_KEY_SHENSHA = [
    "桃花", "红鸾", "天喜", "丧门", "白虎", "驿马", "华盖", "天乙贵人",
    "文昌贵人", "将星", "魁罡", "十恶大败", "阴差阳错", "孤鸾煞", "红艳煞",
]


def _build_nontime_structured_evidence(case: dict) -> List[str]:
    """Build structured命理 evidence for non-time questions (Experiment C).

    Unlike the default non-time path (which only lists the 4 option texts), this
    produces independent chart-structure evidence so Stage 2 can judge options on
   命理 merit rather than being anchored by Stage 1's hypothesis.
    """
    evidence = []
    chart = case.get("chart_input") or {}
    four_pillars = chart.get("four_pillars") or {}
    day_master = chart.get("day_master", {})

    evidence.append("【命局结构（预计算，用于选项判断）】")
    dm_gan = day_master.get("gan", "")
    if dm_gan:
        evidence.append(
            f"日主：{dm_gan}（{day_master.get('wuxing', '')}，{day_master.get('yinyang', '')}）"
        )

    # 四柱
    pillar_names = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
    pillars = []
    for name in ("year", "month", "day", "hour"):
        p = four_pillars.get(name) or {}
        gan = p.get("gan", "")
        zhi = p.get("zhi", "")
        if gan or zhi:
            pillars.append(f"{pillar_names[name]} {gan}{zhi}")
    if pillars:
        evidence.append("四柱：" + "，".join(pillars))

    # 十神分布
    shishen_stats = chart.get("shishen_stats", {})
    missing = shishen_stats.get("missing", [])
    if missing:
        evidence.append(f"命局缺失十神：{', '.join(missing)}")

    # 原局刑冲合害
    branch_relations = chart.get("branch_relations") or []
    if branch_relations:
        rel_strs = [f"{r['detail']}（{r['type']}）" for r in branch_relations[:5]]
        evidence.append(f"原局刑冲合害：{'; '.join(rel_strs)}")

    # 关键神煞
    shensha = chart.get("shensha") or []
    key = [s for s in shensha if s.get("name") in _KEY_SHENSHA]
    if key:
        evidence.append(
            "关键神煞：" + ", ".join(f"{s['name']}({s.get('position', '')})" for s in key[:8])
        )

    # 问题类型命理提示
    hints = _get_question_type_hints(case.get("question", ""))
    if hints:
        evidence.append("")
        evidence.append("【问题类型命理提示】")
        for h in hints:
            evidence.append(f"  - {h}")

    return evidence


def _build_dayun_evidence(case: dict) -> List[str]:
    """Build pre-computed dayun (大运) evidence for time-location questions.

    Extracts da_yun from chart_input and formats as structured evidence.
    Also computes age/dayun mapping for each option, and injects liu_nian,
    shen_sha, branch_relations, gan_relations, and other key chart structures.
    """
    evidence = []
    chart = case.get("chart_input") or {}
    da_yun = chart.get("da_yun") or []
    birth = case.get("person", {}).get("birth", {})
    birth_year = birth.get("year", 0)
    options = case.get("options", [])
    question = case.get("question", "")

    if not da_yun or not birth_year:
        return evidence

    # --- Section 1: Dayun summary ---
    evidence.append("【预计算大运数据】")
    dayun_summary = chart.get("dayun_summary", {})
    direction = dayun_summary.get("direction", "未知")
    starting_age = dayun_summary.get("starting_age", 0)
    evidence.append(f"起运方向：{direction}，起运年龄：{starting_age}岁")
    evidence.append("大运排布：")
    for dy in da_yun:
        evidence.append(
            f"  {dy.get('index', 0)}. {dy.get('gan', '')}{dy.get('zhi', '')} "
            f"({dy.get('start_age', 0)}-{dy.get('end_age', 0)}岁, "
            f"{dy.get('shi_shen_gan', '')}/{dy.get('shi_shen_zhi', '')})"
        )

    # --- Section 2: Key chart structures for time-location reasoning ---
    # Extract key structures that help identify event timing
    four_pillars = chart.get("four_pillars") or {}
    day_master = chart.get("day_master", {})
    day_master_gan = day_master.get("gan", "")
    day_master_wx = day_master.get("wuxing", "")

    evidence.append("")
    evidence.append("【命局关键结构（用于时间定位）】")
    evidence.append(f"日主：{day_master_gan}（{day_master_wx}）")

    # Collect all natal gan and zhi with their positions
    natal_gan = {}  # position -> gan
    natal_zhi = {}  # position -> zhi
    for pillar_name in ["year", "month", "day", "hour"]:
        p = four_pillars.get(pillar_name) or {}
        gan = p.get("gan", "")
        zhi = p.get("zhi", "")
        if gan:
            natal_gan[pillar_name] = gan
        if zhi:
            natal_zhi[pillar_name] = zhi

    # Day pillar is special - it's the "day master palace"
    day_zhi = natal_zhi.get("day", "")
    day_gan = natal_gan.get("day", "")

    # Shishen stats - missing key ten gods
    shishen_stats = chart.get("shishen_stats", {})
    missing = shishen_stats.get("missing", [])
    if missing:
        evidence.append(f"命局缺失十神：{', '.join(missing)}")

    # Branch relations in natal chart
    branch_relations = chart.get("branch_relations") or []
    if branch_relations:
        rel_strs = [f"{r['detail']}（{r['type']}）" for r in branch_relations[:5]]
        evidence.append(f"原局刑冲合害：{'; '.join(rel_strs)}")

    # Shensha relevant to common events
    shensha = chart.get("shensha") or []
    key_shensha = [s for s in shensha if s.get("name") in [
        "桃花", "红鸾", "天喜", "丧门", "白虎", "驿马", "华盖", "天乙贵人",
        "文昌贵人", "将星", "魁罡", "十恶大败", "阴差阳错", "孤鸾煞", "红艳煞",
    ]]
    if key_shensha:
        evidence.append("关键神煞：" + ", ".join([
            f"{s['name']}({s.get('position', '')})" for s in key_shensha[:8]
        ]))

    # --- Section 2.5: Question type hints ---
    hints = _get_question_type_hints(question)
    if hints:
        evidence.append("")
        evidence.append("【问题类型命理提示】")
        for h in hints:
            evidence.append(f"  - {h}")

    # --- Section 3: Option-to-dayun mapping with detailed liu_nian analysis ---
    evidence.append("")
    evidence.append("【各选项对应大运流年详析】")

    for opt in options:
        opt_clean = re.sub(r"^[A-D]\.\s*", "", opt).strip()
        year_match = re.search(r"(\d{4})", opt_clean)
        age_match = re.search(r"(\d+)[—-](\d+)", opt_clean)

        if year_match:
            year = int(year_match.group(1))
            age = year - birth_year
            # Find matching dayun
            matched_dy = None
            for dy in da_yun:
                if dy.get("start_age", 0) <= age <= dy.get("end_age", 0):
                    matched_dy = dy
                    break

            if matched_dy:
                dy_gan = matched_dy.get("gan", "")
                dy_zhi = matched_dy.get("zhi", "")
                dy_shishen_gan = matched_dy.get("shi_shen_gan", "")
                dy_shishen_zhi = matched_dy.get("shi_shen_zhi", "")

                # Get liu_nian for this year
                ln = _get_liunian_for_year(chart, year)
                ln_info = ""
                ln_relations = []
                ln_gan_relations = []
                if ln:
                    ln_gan = ln.get("gan", "")
                    ln_zhi = ln.get("zhi", "")
                    ln_shishen = ln.get("shi_shen", "")
                    ln_info = f"，流年{ln_gan}{ln_zhi}（{ln_shishen}）"

                    # Compute relation between liu_nian gan and day_master gan
                    if day_master_gan and ln_gan:
                        gan_rel = _compute_gan_relation(day_master_gan, ln_gan)
                        if gan_rel:
                            ln_gan_relations.append(f"流年天干{ln_gan}与日主{day_master_gan}：{gan_rel}")

                    # Compute relation between liu_nian gan and each natal gan
                    for pos, ng in natal_gan.items():
                        if ng and ln_gan:
                            gan_rel = _compute_gan_relation(ng, ln_gan)
                            if gan_rel:
                                ln_gan_relations.append(f"流年天干{ln_gan}与{pos}柱天干{ng}：{gan_rel}")

                    # Check relations between liu_nian zhi and each natal zhi (with position)
                    for pos, nz in natal_zhi.items():
                        rels = _compute_branch_relation(ln_zhi, nz)
                        if rels:
                            for r in rels:
                                ln_relations.append(f"流年{ln_zhi}{r}{pos}柱{nz}")

                    # Check relations between liu_nian zhi and dayun zhi
                    if dy_zhi:
                        rels = _compute_branch_relation(ln_zhi, dy_zhi)
                        if rels:
                            for r in rels:
                                ln_relations.append(f"流年{ln_zhi}{r}大运{dy_zhi}")

                # Check relations between dayun zhi and each natal zhi (with position)
                dy_relations = []
                if dy_zhi:
                    for pos, nz in natal_zhi.items():
                        rels = _compute_branch_relation(dy_zhi, nz)
                        if rels:
                            for r in rels:
                                dy_relations.append(f"大运{dy_zhi}{r}{pos}柱{nz}")

                # Compute dayun gan relation to day master
                dy_gan_relation = ""
                if day_master_gan and dy_gan:
                    gan_rel = _compute_gan_relation(day_master_gan, dy_gan)
                    if gan_rel:
                        dy_gan_relation = f"，大运天干与日主：{gan_rel}"

                # Compute dayun gan relation to each natal gan
                dy_gan_relations = []
                for pos, ng in natal_gan.items():
                    if ng and dy_gan:
                        gan_rel = _compute_gan_relation(ng, dy_gan)
                        if gan_rel:
                            dy_gan_relations.append(f"大运天干{dy_gan}与{pos}柱{ng}：{gan_rel}")

                # Compute dayun+liunian shishen combination effect
                combo_hint = ""
                if ln and dy_shishen_gan and ln_shishen:
                    combo = f"{dy_shishen_gan}+{ln_shishen}"
                    # Common problematic combinations
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

                # Build detailed relation string
                all_rels = []
                if dy_relations:
                    all_rels.append("【大运与命局】" + ";".join(dy_relations[:3]))
                if ln_relations:
                    all_rels.append("【流年与命局/大运】" + ";".join(ln_relations[:4]))
                if dy_gan_relations:
                    all_rels.append("【大运天干作用】" + ";".join(dy_gan_relations[:3]))
                if ln_gan_relations:
                    all_rels.append("【流年天干作用】" + ";".join(ln_gan_relations[:3]))

                relation_str = ""
                if all_rels:
                    relation_str = "\n    " + "\n    ".join(all_rels)

                evidence.append(
                    f"  {opt}: {year}年 → 命主{age}岁 → "
                    f"{dy_gan}{dy_zhi}大运（{dy_shishen_gan}/{dy_shishen_zhi}）"
                    f"{ln_info}{dy_gan_relation}{combo_hint}{relation_str}"
                )
            else:
                evidence.append(f"  {opt}: {year}年 → 命主{age}岁 → 大运未找到")

        elif age_match:
            start_age = int(age_match.group(1))
            end_age = int(age_match.group(2))
            mid_age = (start_age + end_age) // 2
            matched_dy = None
            for dy in da_yun:
                if dy.get("start_age", 0) <= mid_age <= dy.get("end_age", 0):
                    matched_dy = dy
                    break
            if matched_dy:
                dy_gan = matched_dy.get("gan", "")
                dy_zhi = matched_dy.get("zhi", "")
                dy_shishen_gan = matched_dy.get("shi_shen_gan", "")
                dy_shishen_zhi = matched_dy.get("shi_shen_zhi", "")

                # Check relations between dayun zhi and each natal zhi (with position)
                dy_relations = []
                if dy_zhi:
                    for pos, nz in natal_zhi.items():
                        rels = _compute_branch_relation(dy_zhi, nz)
                        if rels:
                            for r in rels:
                                dy_relations.append(f"大运{dy_zhi}{r}{pos}柱{nz}")

                # Compute dayun gan relation to day master
                dy_gan_relation = ""
                if day_master_gan and dy_gan:
                    gan_rel = _compute_gan_relation(day_master_gan, dy_gan)
                    if gan_rel:
                        dy_gan_relation = f"，大运天干与日主：{gan_rel}"

                # Compute dayun gan relation to each natal gan
                dy_gan_relations = []
                for pos, ng in natal_gan.items():
                    if ng and dy_gan:
                        gan_rel = _compute_gan_relation(ng, dy_gan)
                        if gan_rel:
                            dy_gan_relations.append(f"大运天干{dy_gan}与{pos}柱{ng}：{gan_rel}")

                all_rels = []
                if dy_relations:
                    all_rels.append("【大运与命局】" + ";".join(dy_relations[:3]))
                if dy_gan_relations:
                    all_rels.append("【大运天干作用】" + ";".join(dy_gan_relations[:3]))

                relation_str = ""
                if all_rels:
                    relation_str = "\n    " + "\n    ".join(all_rels)

                evidence.append(
                    f"  {opt}: {start_age}-{end_age}岁 → "
                    f"{dy_gan}{dy_zhi}大运（{dy_shishen_gan}/{dy_shishen_zhi}）"
                    f"{dy_gan_relation}{relation_str}"
                )
            else:
                evidence.append(f"  {opt}: {start_age}-{end_age}岁 → 大运未找到")
        else:
            evidence.append(f"  {opt}: 无法解析年份/年龄")

    return evidence


def build_stage2_evidence(case: dict, hypothesis: str, mode: str = "all", exp_c: bool = False, exp_c2: bool = False) -> List[str]:
    """Build evidence list for Stage 2.

    Args:
        case: The case dict with question and options.
        hypothesis: The hypothesis from Stage 1.
        mode: "all" for all options, "top2" for top-2 TF-IDF matching.
        exp_c: Experiment C — for non-time questions, prepend structured命理
            evidence (五行/十神/刑冲合害/神煞/问题类型提示) instead of bare options.
        exp_c2: Experiment C2 — for non-time questions, prepend per-option
            score evidence from benchmark.runners.per_option_scorer.

    Returns:
        List of evidence strings.
    """
    options = case.get("options", [])
    question = case.get("question", "")
    is_time = is_time_location_question(question, options)
    if exp_c and exp_c2:
        raise ValueError("build_stage2_evidence: exp_c and exp_c2 are mutually exclusive")

    evidence = []

    # For time-location questions, inject pre-computed dayun data
    if is_time:
        dayun_evidence = _build_dayun_evidence(case)
        evidence.extend(dayun_evidence)
        evidence.append("")  # Separator
    elif exp_c:
        # Experiment C: non-time questions get structured命理 evidence
        evidence.extend(_build_nontime_structured_evidence(case))
        evidence.append("")  # Separator
    elif exp_c2:
        from benchmark.runners.per_option_scorer import format_option_scores, score_options

        evidence.extend(format_option_scores(score_options(case)))
        evidence.append("")  # Separator

    if mode == "all":
        # Return all options as evidence items
        evidence.extend([str(opt) for opt in options])
        return evidence

    elif mode == "top2":
        # Simple TF-IDF-like matching: find top 2 options most similar to hypothesis
        if not hypothesis or not options:
            return evidence

        # Simple word overlap scoring
        hypothesis_words = set(hypothesis)
        scores = []
        for opt in options:
            opt_clean = re.sub(r"^[A-D]\.\s*", "", opt).strip()
            overlap = len(set(opt_clean) & hypothesis_words)
            scores.append((overlap, opt))

        # Sort by score descending, take top 2
        scores.sort(key=lambda x: x[0], reverse=True)
        top2 = [opt for _, opt in scores[:2]]
        evidence.extend(top2)
        return evidence

    return evidence
