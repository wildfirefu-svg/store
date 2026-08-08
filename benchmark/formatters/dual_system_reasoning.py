from __future__ import annotations

import hashlib

from benchmark.formatters.baziqa_prompt import (
    _assemble_reasoned_choice_prompt,
    format_options,
)
from benchmark.formatters.chart_context import (
    extract_reasoned_choice_answer,
    render_reasoned_context,
)

JUDGE_TEMPLATE_VERSION = "dual_judge_v1"


def build_bazi_pipeline_prompt(case):
    return _assemble_reasoned_choice_prompt(case, render_reasoned_context(case, "legacy_v0", "none"))


def build_ziwei_pipeline_prompt(case):
    return _assemble_reasoned_choice_prompt(case, render_reasoned_context(case, "legacy_v0", "only"))


def build_judge_prompt(case, ans1, rationale1, ans2, rationale2, swap=False):
    a1, r1, a2, r2 = ans1, rationale1, ans2, rationale2
    if swap:
        a1, r1, a2, r2 = a2, r2, a1, r1
    sections = [
        "你是一位命理评测裁判。下面有两个独立分析对同一道四选一题给出的结论与理由。",
        "请综合两者的推理，选出你认为最合理的选项。",
        "## 问题", case.get("question", ""),
        "## 选项", format_options(case.get("options", [])),
    ]
    sections.append("\n".join(["## 分析一", f"结论：{a1}", f"理由：{r1}"]))
    sections.append("\n".join(["## 分析二", f"结论：{a2}", f"理由：{r2}"]))
    sections.append(
        "## 输出要求\n请先简要说明你的裁决依据，然后给出最终答案。最后一行必须严格为：\n最终答案：X\n其中 X 为 A、B、C 或 D 之一。"
    )
    return "\n\n".join(sections)


def extract_judge_answer(raw):
    return extract_reasoned_choice_answer(raw)


def judge_swap_seed(dataset, case_id, repeat_idx):
    digest = hashlib.sha256(f"{dataset}|{case_id}|{repeat_idx}".encode()).hexdigest()
    return int(digest, 16) % 2 == 1
