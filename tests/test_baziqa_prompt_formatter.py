from benchmark.formatters.baziqa_prompt import (
    format_birth_line,
    format_direct_c2_prompt,
    format_direct_choice_prompt,
    format_options,
    format_structured_reasoning_prompt,
)


def _case():
    return {
        "case_id": "q1",
        "domain": "career",
        "person": {
            "name": "命主测试",
            "gender": "female",
            "birth": {
                "year": 1990,
                "month": 1,
                "day": 1,
                "hour": 9,
                "minute": 0,
                "place": "北京，中国",
            },
        },
        "question": "此命事业更适合哪类发展？",
        "options": ["A. 稳定组织", "B. 高风险投机", "C. 完全不工作", "D. 随机选择"],
    }


def test_format_birth_line():
    text = format_birth_line(_case()["person"])
    assert "1990年1月1日9时0分" in text
    assert "北京，中国" in text
    assert "female" in text


def test_format_options():
    assert "A. 稳定组织" in format_options(_case()["options"])


def test_format_direct_choice_prompt():
    prompt = format_direct_choice_prompt(_case())
    assert "请直接回答选项字母" in prompt
    assert "此命事业" in prompt
    assert "A. 稳定组织" in prompt


def test_format_direct_c2_prompt_injects_scores_without_changing_direct_prompt():
    prompt = format_direct_c2_prompt(
        _case(),
        [{
            "label": "A",
            "text": "稳定组织",
            "score": 68,
            "verdict": "weak_support",
            "support": ["官印相生"],
            "reject": [],
        }],
    )
    assert "## C2 参考证据" in prompt
    assert "A. 稳定组织 -> 68/100" in prompt
    assert "不得仅因某选项分数最高而选择" in prompt


def test_format_structured_reasoning_prompt():
    prompt = format_structured_reasoning_prompt(_case())
    for marker in ["第一阶段：量化扫描", "第二阶段：冲突定级", "第三阶段：应象映射"]:
        assert marker in prompt
    assert "最后一行只能写" in prompt


def test_structured_reasoning_prompt_requires_confidence_contract():
    prompt = format_structured_reasoning_prompt(_case())
    assert "A: 0-100" in prompt
    assert "B: 0-100" in prompt
    assert "C: 0-100" in prompt
    assert "D: 0-100" in prompt
    assert "最终答案：X" in prompt
    assert "最后一行只能写" in prompt
