"""C1 一致性转换器：检测器（Phase 8，6A 单版本开发冻结）。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md v1.3.1（§P8-3）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md v3.2（Task 6A）

检测逻辑（冻结）：正文结论（年份/选项描述）→ 选项映射 → 与最终 `**答案：X**` 比对；
冲突则提取候选 letter 并重选。只用合成 fixture 开发，不读真实输出。
"""
from __future__ import annotations

import re

_FINAL_ANSWER_RE = re.compile(r"\*\*答案：([A-D])\*\*")
_YEAR_RE = re.compile(r"(\d{4})\s*年")
_OPTION_LETTER_RE = re.compile(r"^([A-D])[.、．]\s*(.*)$")
# 结论标记词（正文结论必须含其一才视为有效结论）
_CONCLUSION_MARKERS = ("最符合", "机会最大", "应为", "当选", "综合判断", "结论")


def detect(raw_answer: str, options: list[str] | None = None) -> dict:
    """检测正文结论与最终答案的冲突，返回候选 letter。

    返回字段：conflict / final_letter / body_conclusion / candidate_letter。
    body_conclusion 为正文提取的年份结论（如 "2018"）；candidate_letter 为按结论重选的选项。
    """
    final = _FINAL_ANSWER_RE.search(raw_answer or "")
    final_letter = final.group(1) if final else None

    # 正文结论提取：最终答案之前的文本中的年份结论（需含结论标记词）
    body = raw_answer[: final.start()] if final else raw_answer
    body_conclusion = None
    if any(m in (body or "") for m in _CONCLUSION_MARKERS):
        years = _YEAR_RE.findall(body or "")
        body_conclusion = years[-1] if years else None  # 取正文最后一个年份结论

    candidate_letter = None
    conflict = False
    if final_letter and body_conclusion and options:
        candidate = map_year_to_letter(body_conclusion, options)
        if candidate and candidate != final_letter:
            conflict = True
            candidate_letter = candidate

    return {
        "conflict": conflict,
        "final_letter": final_letter,
        "body_conclusion": body_conclusion,
        "candidate_letter": candidate_letter,
    }


def map_year_to_letter(year: str, options: list[str]) -> str | None:
    """把正文结论年份映射到选项 letter（选项含该年份即命中）。"""
    for opt in options or []:
        m = _OPTION_LETTER_RE.match(opt)
        if m and year in m.group(2):
            return m.group(1)
    return None
