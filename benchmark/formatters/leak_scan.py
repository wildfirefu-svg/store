"""防泄漏分级扫描（设计 §4.2.4）。

硬失败三类：answer_metadata / extra_exposure / eval_result。
明确豁免：正常 A/B/C/D 选项块（必含正确选项文本）、身份字段（姓名/出生/地点，
属输入协议声明项）。纯函数；命中即 LeakHit，由调用方决定 gate 失败。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LeakHit:
    kind: str  # "answer_metadata" | "extra_exposure" | "eval_result"
    detail: str


_ANSWER_METADATA_PATTERNS = (
    re.compile(r"(?i)\bcorrect[_\s]?answer\b"),
    re.compile(r"(?i)\banswer[_\s]?key\b"),
    re.compile(r"正确答案"),
    re.compile(r"标准答案"),
    re.compile(r"答案[:：]"),
)
_EVAL_RESULT_PATTERNS = (
    re.compile(r"准确率"),
    re.compile(r"得分率"),
    re.compile(r"(?i)\baccuracy\b"),
    re.compile(r"赛事排名"),
    re.compile(r"历届.{0,12}(答对|正确率)"),
)


def scan_prompt_for_leaks(prompt: str, case: dict) -> list[LeakHit]:
    hits: list[LeakHit] = []
    for pat in _ANSWER_METADATA_PATTERNS:
        m = pat.search(prompt)
        if m:
            hits.append(LeakHit("answer_metadata", f"命中答案元数据 {pat.pattern!r} @{m.start()}"))
    for pat in _EVAL_RESULT_PATTERNS:
        m = pat.search(prompt)
        if m:
            hits.append(LeakHit("eval_result", f"命中评测结果 {pat.pattern!r} @{m.start()}"))
    hits.extend(_scan_extra_exposure(prompt, case))
    return hits


def _option_core(option: str) -> str:
    """去掉字母前缀的选项核心文本（'A 普通' → '普通'）。"""
    text = str(option)
    if text[:1] in "ABCD" and len(text) > 1 and text[1] in " .、　":
        return text[2:].strip() if text[1] == " " else text[1:].strip(" .、　")
    return text


def _scan_extra_exposure(prompt: str, case: dict) -> list[LeakHit]:
    answer = str(case.get("answer") or "")
    options = case.get("options") or []
    idx = "ABCD".find(answer)
    if idx < 0 or idx >= len(options):
        return []
    core = _option_core(options[idx])
    if len(core) < 2:
        return []
    spans = [m.span() for m in re.finditer(re.escape(core), prompt)]
    if len(spans) <= 1:
        return []  # 仅在选项块内出现一次
    block = _options_block_span(prompt, options)
    outside = [
        s for s in spans
        if block is None or s[0] < block[0] or s[0] >= block[1]
    ]
    if outside:
        return [LeakHit("extra_exposure", f"正确选项文本 {core!r} 在选项块外出现 {len(outside)} 次")]
    return []


def _options_block_span(prompt: str, options: list) -> tuple[int, int] | None:
    """包含全部选项核心文本的最小连续区域；任一缺失返回 None（保守判块外）。"""
    positions = []
    for opt in options:
        core = _option_core(opt)
        if not core:
            return None
        pos = prompt.find(core)
        if pos < 0:
            return None
        positions.append((pos, pos + len(core)))
    return min(p[0] for p in positions), max(p[1] for p in positions)
