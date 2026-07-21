"""MingLi 官方 CoT prompt 1:1 复刻（Task 5 修订，用户裁决 2A）。

来源：MingLi-Bench mingli_bench/benchmark.py `_prepare_prompt`（钉死 commit
b7433280fd86d7a7c27debbc47d0303c218f0bfd），对照记录：
tests/fixtures/phase6/mingli_official_prompt_template.txt。
评测可复现性以本文件为准（mingli_official_replica_v1）。

与官方源码的唯一适配差异：选项输入除官方 dict 形状外，还接受本仓库 adapter
归一化字符串 "A. 文本"（解析出 letter/text），输出仍按官方语义按 letter 排序、
"{letter}. {text}" 逐行；避免 "A. A. 文本" 双字母。
"""
from __future__ import annotations

import re

OFFICIAL_COT_TEMPLATE_VERSION = "mingli_official_replica_v1"

# 官方 models/base.py SYSTEM_PROMPT 逐字复刻
OFFICIAL_SYSTEM_PROMPT = (
    "你是一位精通中国传统命理学的专家，包括八字命理、紫微斗数等。"
    "请根据给定的信息进行分析和回答。"
)

# 官方 use_cot=True 分支指令（逐字，含前导 \n）
_COT_INSTRUCTION = (
    "\n结合中国传统命理学（包括但不限于四柱八字、紫微斗数等），"
    "请先分析推理过程，然后给出答案。最后用'答案：X'的格式给出你的选择（X为A、B、C或D）。"
)

# 官方固定宫序
_PALACE_ORDER = (
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
    "迁移", "仆役", "官禄", "田宅", "福德", "父母",
)

_OPTION_RE = re.compile(r"^([A-Za-z])[.、．]\s*(.*)$")


def _lettered_options(options: list) -> list[tuple[str, str]]:
    """官方语义：dict 取 letter/text；其余按顺序赋 A-D。适配：归一化字符串
    "A. 文本" 解析为 (letter, text)。输出按 letter 排序（官方 sorted by letter）。"""
    lettered: list[tuple[str, str]] = []
    for idx, opt in enumerate(options[:4]):  # 官方 Max 4 options
        if isinstance(opt, dict):
            lettered.append((str(opt.get("letter") or chr(ord("A") + idx)),
                             str(opt.get("text") or "")))
            continue
        text = str(opt)
        m = _OPTION_RE.match(text)
        if m:
            lettered.append((m.group(1).upper(), m.group(2)))
        else:
            lettered.append((chr(ord("A") + idx), text))
    lettered.sort(key=lambda pair: pair[0])
    return lettered


def format_official_cot_prompt(case: dict) -> str:
    """官方 CoT + astro user prompt（1:1 复刻）。

    case 需含 question/options/birth_info；astro 取自
    case["chart_input"]["official_astro"]（缺 astro 则按官方行为不注入块；
    标量字段缺失按官方行为填 "未知"）。
    """
    birth_info = case.get("birth_info") or {}
    if isinstance(birth_info, dict):
        birth_text = birth_info.get("raw", birth_info)
    else:
        birth_text = birth_info
    prompt = f"以下是一道关于中国传统命理的题目。\n\n命主信息：\n{birth_text}"
    prompt += _COT_INSTRUCTION

    astro = (case.get("chart_input") or {}).get("official_astro")
    if isinstance(astro, dict) and astro:
        chinese_date = astro.get("chinese_date") or "未知"
        time_info = astro.get("time") or "未知"
        five_elements = astro.get("five_elements_class") or "未知"
        zodiac = astro.get("zodiac") or "未知"
        prompt += (
            f"\n\n八字命盘信息：\n八字：{chinese_date}\n时辰：{time_info}"
            f"\n五行局：{five_elements}\n生肖：{zodiac}"
            f"\n\n紫微命盘信息：\n十二宫位星曜分布："
        )
        palace_stars = astro.get("palace_stars") or {}
        for name in _PALACE_ORDER:
            stars = palace_stars.get(name)
            if stars:
                prompt += f"\n{name}：{stars}"

    prompt += f"\n\n问题：{case.get('question', '')}\n\n选项：\n"
    for letter, text in _lettered_options(case.get("options") or []):
        prompt += f"{letter}. {text}\n"
    return prompt
