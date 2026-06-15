#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quality.llm_quality_test import score_report


def test_score_report_gives_high_score_for_complete_report():
    text = """
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

    assert score_report(text) >= 0.9


def test_score_report_penalizes_missing_sections():
    text = "格局不错，用神也可以。"

    assert score_report(text) < 0.5


def test_score_report_penalizes_vague_terms():
    text = """
## 核心判断
格局：可能不错。用神：也许是印星。置信度：0.5。
## 证据链
天干可能有帮助，地支大概有根，十神也许能用。
## 反证据与不确定性
可能、大概、也许。
## 分项分析
可能有发展。
## 实用建议
大概可以努力。
"""

    assert score_report(text) < 0.9
