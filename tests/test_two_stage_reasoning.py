"""Tests for two_stage_reasoning formatter.

TDD red-green cycle for Phase 4 two-stage reasoning implementation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestIsTimeLocationQuestion:
    def test_is_time_location_question_keywords(self):
        from benchmark.formatters.two_stage_reasoning import is_time_location_question
        # Positive cases
        assert is_time_location_question("母亲哪年离世？", ["1989", "1990", "2011", "2021"]) is True
        assert is_time_location_question("此人何时结婚？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("哪一年发生官非？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("几年后会转运？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("时间是什么时候？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("年份是哪一年？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("什么时候离婚？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("几时会成功？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("何年去世？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("哪年发生车祸？", ["A", "B", "C", "D"]) is True
        assert is_time_location_question("第一段婚姻出现在哪年？", ["A", "B", "C", "D"]) is True
        # 4-digit year options
        assert is_time_location_question("请选择正确年份", ["1989", "1990", "2011", "2021"]) is True
        # Negative cases
        assert is_time_location_question("事业方向如何？", ["A", "B", "C", "D"]) is False
        assert is_time_location_question("性格特点是什么？", ["A", "B", "C", "D"]) is False
        assert is_time_location_question("健康状况怎样？", ["文职", "武职", "经商", "待业"]) is False


class TestFormatStage1Prompt:
    def test_format_stage1_prompt_no_labels(self):
        from benchmark.formatters.two_stage_reasoning import format_stage1_prompt
        case = {
            "case_id": "test_case_001",
            "person": {
                "name": "某命主",
                "gender": "女",
                "birth": {"year": 1980, "month": 8, "day": 24, "hour": 12, "minute": 0, "place": "广东"},
            },
            "chart_input": {
                "four_pillars": {
                    "year": {"gan": "庚", "zhi": "申"},
                    "month": {"gan": "甲", "zhi": "午"},
                    "day": {"gan": "丙", "zhi": "辰"},
                    "hour": {"gan": "戊", "zhi": "子"},
                },
                "day_master": {"gan": "丙", "wuxing": "火", "yinyang": "阳"},
            },
            "question": "事业方向如何？",
            "options": ["A. 文职/教育", "B. 武职/军警", "C. 经商/创业", "D. 自由职业"],
            "domain": "career",
        }
        prompt = format_stage1_prompt(case)
        # No A/B/C/D labels in Stage 1
        assert "A." not in prompt
        assert "B." not in prompt
        assert "C." not in prompt
        assert "D." not in prompt
        # Has option1/option2 style labels
        assert "选项1" in prompt
        assert "选项2" in prompt
        # Has required marker
        assert "【内容假设】" in prompt
        # Has prohibition on referencing option numbers
        assert "禁止引用选项编号" in prompt or "不要用" in prompt
        # Consistency: same case, same prompt
        prompt2 = format_stage1_prompt(case)
        assert prompt == prompt2

    def test_format_stage1_prompt_time_question(self):
        from benchmark.formatters.two_stage_reasoning import format_stage1_prompt
        case = {
            "case_id": "test_case_002",
            "person": {
                "name": "某命主",
                "gender": "男",
                "birth": {"year": 1972, "month": 1, "day": 8, "hour": 10, "minute": 0, "place": "潮州"},
            },
            "chart_input": {
                "four_pillars": {
                    "year": {"gan": "壬", "zhi": "子"},
                    "month": {"gan": "辛", "zhi": "丑"},
                    "day": {"gan": "甲", "zhi": "寅"},
                    "hour": {"gan": "乙", "zhi": "卯"},
                },
                "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳"},
                "da_yun": [
                    {"index": 1, "gan": "壬", "zhi": "寅", "start_age": 1, "end_age": 10, "shi_shen_gan": "偏印", "shi_shen_zhi": "比肩"},
                    {"index": 2, "gan": "癸", "zhi": "卯", "start_age": 11, "end_age": 20, "shi_shen_gan": "正印", "shi_shen_zhi": "劫财"},
                ],
                "dayun_summary": {"direction": "顺行", "starting_age": 3},
            },
            "question": "母亲哪年离世？",
            "options": ["A. 1989", "B. 1990", "C. 2011", "D. 2021"],
            "domain": "family",
        }
        prompt = format_stage1_prompt(case)
        # Time-location phase 4 injected
        assert "第四阶段：时间定位" in prompt
        assert "大运锚定" in prompt
        assert "流年验证" in prompt
        assert "Step 1" in prompt
        assert "Step 2" in prompt
        # Two-step output requirement
        assert "事件发生在第 X 步大运" in prompt
        assert "重点流年为 YYYY 年" in prompt
        assert "大运区间 + 流年年份 + 命理结构特征" in prompt


class TestFormatStage2Prompt:
    def test_format_stage2_prompt(self):
        from benchmark.formatters.two_stage_reasoning import format_stage2_prompt
        case = {
            "case_id": "test_case_001",
            "person": {
                "name": "某命主",
                "gender": "女",
                "birth": {"year": 1980, "month": 8, "day": 24, "hour": 12, "minute": 0, "place": "广东"},
            },
            "chart_input": {
                "four_pillars": {
                    "year": {"gan": "庚", "zhi": "申"},
                    "month": {"gan": "甲", "zhi": "午"},
                    "day": {"gan": "丙", "zhi": "辰"},
                    "hour": {"gan": "戊", "zhi": "子"},
                },
                "day_master": {"gan": "丙", "wuxing": "火", "yinyang": "阳"},
            },
            "question": "事业方向如何？",
            "options": ["A. 文职/教育", "B. 武职/军警", "C. 经商/创业", "D. 自由职业"],
            "domain": "career",
        }
        hypothesis = "事业方向偏文职/教育"
        evidence = ["A. 文职/教育", "B. 武职/军警"]
        prompt = format_stage2_prompt(case, hypothesis, evidence)
        # Has A/B/C/D labels
        assert "A." in prompt
        assert "B." in prompt
        assert "C." in prompt
        assert "D." in prompt
        # Has hypothesis
        assert hypothesis in prompt
        # Has pre-computed data emphasis
        assert "预计算数据" in prompt
        assert "准确可靠" in prompt
        # Has output format requirement
        assert "最终答案" in prompt
        assert "详细推理分析" in prompt
        # Non-time question: no time instruction
        assert "时间定位验证" not in prompt

    def test_format_stage2_prompt_time_question(self):
        from benchmark.formatters.two_stage_reasoning import format_stage2_prompt
        case = {
            "case_id": "test_case_002",
            "person": {
                "name": "某命主",
                "gender": "男",
                "birth": {"year": 1972, "month": 1, "day": 8, "hour": 10, "minute": 0, "place": "潮州"},
            },
            "chart_input": {
                "four_pillars": {
                    "year": {"gan": "壬", "zhi": "子"},
                    "month": {"gan": "辛", "zhi": "丑"},
                    "day": {"gan": "甲", "zhi": "寅"},
                    "hour": {"gan": "乙", "zhi": "卯"},
                },
                "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳"},
            },
            "question": "母亲哪年离世？",
            "options": ["A. 1989", "B. 1990", "C. 2011", "D. 2021"],
            "domain": "family",
        }
        hypothesis = "该事件应发生在印星受刑冲入墓的流年"
        evidence = ["A. 1989", "B. 1990", "C. 2011", "D. 2021"]
        prompt = format_stage2_prompt(case, hypothesis, evidence, is_time=True)
        # Has time-location verification instruction
        assert "时间定位验证" in prompt
        assert "中性命理描述" in prompt
        assert "大运对照表" in prompt
        assert "逐项验证" in prompt
        assert "排除法" in prompt
        assert "禁止因为" in prompt


class TestParseStage1Result:
    def test_parse_stage1_result_marker(self):
        from benchmark.formatters.two_stage_reasoning import parse_stage1_result
        # Standard marker
        assert parse_stage1_result("...\n【内容假设】：事业方向偏文职/教育\n") == "事业方向偏文职/教育"
        # Fallback prefixes
        assert parse_stage1_result("结论：事业方向偏文职/教育") == "事业方向偏文职/教育"
        assert parse_stage1_result("假设：事业方向偏文职/教育") == "事业方向偏文职/教育"
        assert parse_stage1_result("判断：事业方向偏文职/教育") == "事业方向偏文职/教育"
        # No marker → fallback to last non-empty line
        assert parse_stage1_result("没有任何标记的文本") == "没有任何标记的文本"
        # Empty → None
        assert parse_stage1_result("") is None


class TestBuildStage2Evidence:
    def test_build_stage2_evidence_all_mode(self):
        from benchmark.formatters.two_stage_reasoning import build_stage2_evidence
        case = {
            "case_id": "test_case_001",
            "question": "事业方向如何？",
            "options": ["A. 文职/教育", "B. 武职/军警", "C. 经商/创业", "D. 自由职业"],
        }
        hypothesis = "事业方向偏文职/教育"
        # mode='all' should return evidence for all options
        evidence = build_stage2_evidence(case, hypothesis, mode="all")
        assert isinstance(evidence, list)
        assert len(evidence) == 4
        # mode='top2' should return at most 2 evidence items
        evidence_top2 = build_stage2_evidence(case, hypothesis, mode="top2")
        assert isinstance(evidence_top2, list)
        assert len(evidence_top2) <= 2


class TestRealCases:
    def test_four_unanimous_wrong_cases_trigger(self):
        import json
        import os
        from benchmark.formatters.two_stage_reasoning import is_time_location_question
        path = "benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl"
        if not os.path.exists(path):
            pytest.skip(f"Dataset not found: {path}")
        cases = [json.loads(l) for l in open(path, encoding="utf-8")]
        targets = ["P002-Q9", "P003-Q13", "P004-Q17", "P005-Q22"]
        matched = [c for c in cases if any(t in c["case_id"] for t in targets)]
        assert len(matched) == 4, f"Expected 4 cases, found {len(matched)}"
        for c in matched:
            assert is_time_location_question(c["question"], c["options"]) is True, \
                f"Case {c['case_id']} should trigger time detection"


# Import pytest at the end for the skip functionality
try:
    import pytest
except ImportError:
    pass
