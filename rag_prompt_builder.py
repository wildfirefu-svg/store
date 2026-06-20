"""Compose a system prompt that injects retrieved BaziQA cases into the base prompt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from bazi_features import extract
from case_index import CaseIndex


MAX_TOTAL_CHARS = 8000
MAX_FACT_PER_CASE = 5
MAX_FEWSHOT_EXAMPLES = 3
MAX_FEWSHOT_OPTION_CHARS = 60


def load_fewshot_examples(path: Optional[Any]) -> List[Dict[str, Any]]:
    """Load few-shot examples from a JSONL file.

    Each line should be a BaziQA-style row: question/options/answer plus optional
    person.birth and domain. Returns at most MAX_FEWSHOT_EXAMPLES rows.
    """
    if path is None:
        return []
    p = Path(path)
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if not row.get("question") or not row.get("options") or not row.get("answer"):
                continue
            out.append(row)
            if len(out) >= MAX_FEWSHOT_EXAMPLES:
                break
    return out


def _format_fewshot_example(idx: int, row: Dict[str, Any]) -> str:
    person = row.get("person") or {}
    birth = person.get("birth") or {}
    gender = person.get("gender") or "?"
    year = birth.get("year") or "?"
    domain = row.get("domain") or "unknown"
    question = str(row.get("question") or "").strip()
    options = row.get("options") or []
    options_text_lines: List[str] = []
    for opt in options[:4]:
        text = str(opt).strip()
        if len(text) > MAX_FEWSHOT_OPTION_CHARS:
            text = text[: MAX_FEWSHOT_OPTION_CHARS - 1] + "…"
        options_text_lines.append(f"  {text}")
    options_text = "\n".join(options_text_lines)
    answer = str(row.get("answer") or "").strip().upper()[:1]
    return (
        f"### 示例 {idx}\n"
        f"命主：{year}年生 {gender}，问题领域：{domain}\n"
        f"题目：{question}\n"
        f"选项：\n{options_text}\n"
        f"标准答案：{answer}"
    )


def _format_case(idx: int, case: Dict[str, Any]) -> str:
    facts = case.get("facts") or []
    bullets = "\n".join(f"  - {fact}" for fact in facts[:MAX_FACT_PER_CASE])
    name = case.get("name") or case.get("person_id") or f"案例{idx}"
    year = case.get("birth_year") or "?"
    gender = case.get("gender") or "?"
    domains = case.get("domains") or {}
    domain_text = "、".join(f"{k}:{v}" for k, v in sorted(domains.items())) or "unknown"
    reasons = case.get("match_reasons") or []
    reason_text = "、".join(str(r) for r in reasons) or "keyword_bm25"
    score_text = case.get("_score")
    return (
        f"## 案例 {idx}（仅供参考，非当前命主）\n"
        f"命主：{name}（出生 {year}，性别 {gender}）\n"
        f"命例领域：{domain_text}\n"
        f"匹配原因：{reason_text}；检索分：{score_text}\n"
        f"史实摘要：\n{bullets}".rstrip()
    )


def build_system_prompt(
    base_system: str,
    chart: Dict[str, Any],
    case_index: CaseIndex,
    enable_rag: bool = True,
    k: int = 2,
    few_shot_examples: Optional[List[Dict[str, Any]]] = None,
) -> str:
    base = str(base_system or "")

    fewshot_block = ""
    if few_shot_examples:
        formatted = []
        for i, row in enumerate(few_shot_examples[:MAX_FEWSHOT_EXAMPLES], 1):
            formatted.append(_format_fewshot_example(i, row))
        if formatted:
            fewshot_block = (
                "<示例题（few-shot）>\n"
                "下面是一些**与本题非同一命主**的样题与标准答案，用于示意输出格式与推理风格，不得直接照搬结论。\n\n"
                + "\n\n".join(formatted)
                + "\n</示例题（few-shot）>"
            )

    if not enable_rag:
        if not fewshot_block:
            return base
        full = f"{fewshot_block}\n\n{base}".strip()
        return full[:MAX_TOTAL_CHARS]

    features = extract(chart)
    cases = case_index.top_k_cases(features, k=k)
    if not cases:
        if not fewshot_block:
            return base
        return f"{fewshot_block}\n\n{base}".strip()[:MAX_TOTAL_CHARS]

    blocks: List[str] = []
    blocks.append(
        "<类似命例>\n以下命例**仅供参考，非当前命主**，不得直接照搬，需结合本盘自身格局。\n"
    )
    for i, case in enumerate(cases, 1):
        blocks.append(_format_case(i, case))
    blocks.append("</类似命例>")

    injection = "\n\n".join(blocks)
    parts: List[str] = []
    if fewshot_block:
        parts.append(fewshot_block)
    parts.append(base)
    parts.append(injection)
    full = "\n\n".join(parts).strip()

    if len(full) <= MAX_TOTAL_CHARS:
        return full

    overflow = len(full) - MAX_TOTAL_CHARS
    if overflow >= len(injection):
        return full[:MAX_TOTAL_CHARS]
    base_keep = max(0, len(base) - overflow - 4)
    truncated_base = base[:base_keep] + "..."
    rebuilt_parts: List[str] = []
    if fewshot_block:
        rebuilt_parts.append(fewshot_block)
    rebuilt_parts.append(truncated_base)
    rebuilt_parts.append(injection)
    return "\n\n".join(rebuilt_parts)[:MAX_TOTAL_CHARS]
