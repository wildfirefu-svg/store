#!/usr/bin/env python3
import json

REQUIRED_SECTIONS = ["核心判断", "证据链", "反证据", "分项分析", "实用建议"]
REQUIRED_TERMS = ["格局", "用神", "置信度", "天干", "地支", "十神"]
VAGUE_TERMS = ["可能", "也许", "大概"]


def score_report(text):
    section_score = sum(1 for s in REQUIRED_SECTIONS if s in text) / len(REQUIRED_SECTIONS)
    term_score = sum(1 for t in REQUIRED_TERMS if t in text) / len(REQUIRED_TERMS)
    vague_count = sum(text.count(t) for t in VAGUE_TERMS)
    vague_penalty = min(vague_count, 10) / 10
    return max(0, round(0.5 * section_score + 0.5 * term_score - 0.2 * vague_penalty, 3))


def smoke_sample():
    return """
## 核心判断
格局：七杀格。用神：印星。置信度：0.82。

## 证据链
天干见杀，地支有根，十神组合清楚。

## 反证据与不确定性
地支有合化干扰，需要结合大运。

## 分项分析
事业宜专业路线。

## 实用建议
保持长期主义。
"""


def main():
    text = smoke_sample()
    result = {
        "score": score_report(text),
        "required_sections": REQUIRED_SECTIONS,
        "required_terms": REQUIRED_TERMS,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
