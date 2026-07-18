from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.leak_scan import scan_prompt_for_leaks
from tests.phase6_helpers import make_case


def base_prompt(case: dict) -> str:
    opts = "\n".join(case["options"])
    return (
        "你是一位严谨的八字命理评测助手。\n"
        f"## 命主信息\n姓名：{case['person']['name']}\n"
        f"## 问题\n{case['question']}\n## 选项\n{opts}\n请直接回答选项字母。"
    )


def test_clean_prompt_no_hits():
    case = make_case()
    assert scan_prompt_for_leaks(base_prompt(case), case) == []


def test_answer_metadata_hard_fail():
    case = make_case()
    hits = scan_prompt_for_leaks(base_prompt(case) + "\n正确答案：B", case)
    assert any(h.kind == "answer_metadata" for h in hits)


def test_eval_result_hard_fail():
    case = make_case()
    hits = scan_prompt_for_leaks(base_prompt(case) + "\n上届选手准确率 80%", case)
    assert any(h.kind == "eval_result" for h in hits)


def test_extra_exposure_hard_fail():
    case = make_case(answer="B")  # options[1] = "B 富裕"
    prompt = base_prompt(case) + "\n解析：本例应选富裕，理由略。"
    hits = scan_prompt_for_leaks(prompt, case)
    assert any(h.kind == "extra_exposure" for h in hits)


def test_options_block_is_exempt():
    # 正常选项块必然包含正确选项文本，不产生任何 hit
    case = make_case()
    assert scan_prompt_for_leaks(base_prompt(case), case) == []


def test_identity_fields_exempt():
    case = make_case()
    prompt = base_prompt(case) + "\n补充：命主 1990年1月2日 出生于北京。"
    assert scan_prompt_for_leaks(prompt, case) == []
