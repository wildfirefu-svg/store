from pathlib import Path


def test_structured_reasoning_prompt_contains_required_sections():
    text = Path("prompts/structured_reasoning_v1.md").read_text(encoding="utf-8")
    required = [
        "Xuanjizi-SRP-v1",
        "命盘基础扫描",
        "结构关系识别",
        "强弱与冲突定级",
        "领域映射",
        "事件映射",
        "用户可读表达",
        "不做绝对化预测",
    ]
    for item in required:
        assert item in text
