#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompt_engine import PromptEngine


def _sample_chart():
    return {
        "four_pillars": {
            "year": {"gan": "甲", "zhi": "子"},
            "month": {"gan": "乙", "zhi": "丑"},
            "day": {"gan": "丙", "zhi": "寅"},
            "hour": {"gan": "丁", "zhi": "卯"},
        },
        "day_master": {"gan": "丙", "wuxing": "火"},
        "wuxing_stats": {"金": 1, "木": 2, "水": 1, "火": 2, "土": 2},
    }


def _sample_pre_analysis():
    return {
        "pattern": {"conclusion": "测试格局", "confidence": 0.7},
        "yongshen": {"conclusion": "测试用神", "confidence": 0.6},
    }


def test_prompt_engine_assemble_contains_required_sections():
    system_prompt, user_prompt = PromptEngine().assemble(
        chart=_sample_chart(),
        pre_analysis=_sample_pre_analysis(),
        topic="sihechu",
        question="请分析事业",
    )

    assert "结构" in system_prompt or "输出" in system_prompt
    assert "核心判断" in system_prompt
    assert "证据链" in system_prompt
    assert "丙" in user_prompt
    assert "测试格局" in user_prompt
    assert "请分析事业" in user_prompt


def test_prompt_engine_uses_default_topic_for_unknown_topic():
    system_prompt, user_prompt = PromptEngine().assemble(
        chart=_sample_chart(),
        pre_analysis=_sample_pre_analysis(),
        topic="unknown",
        question="",
    )

    assert "核心判断" in system_prompt
    assert "请进行综合分析" in user_prompt


def test_prompt_engine_exposes_version_metadata():
    engine = PromptEngine(prompt_version="srp_v1", reasoning_protocol="xuanjizi_srp_v1")
    assert engine.prompt_version == "srp_v1"
    assert engine.reasoning_protocol == "xuanjizi_srp_v1"


def test_prompt_engine_srp_prompt_contains_required_stages():
    system_prompt, _ = PromptEngine(
        prompt_version="srp_v1",
        reasoning_protocol="xuanjizi_srp_v1",
    ).assemble(
        chart=_sample_chart(),
        pre_analysis=_sample_pre_analysis(),
        topic="career",
        question="请分析事业",
    )
    for text in ["命盘基础扫描", "结构关系识别", "强弱与冲突定级", "领域映射", "事件映射", "用户可读表达"]:
        assert text in system_prompt


def test_prompt_engine_formats_domain_knowledge(monkeypatch):
    engine = PromptEngine()
    monkeypatch.setattr(engine, "retrieve_similar_cases", lambda chart: ["【参考案例】\n姓名：测试"])

    text = engine.build_domain_knowledge(_sample_chart(), "sihechu")

    assert "相似案例参考" in text
    assert "参考案例" in text
    assert "姓名：测试" in text


def test_prompt_engine_retrieve_cases_never_raises():
    cases = PromptEngine().retrieve_similar_cases(_sample_chart())
    assert isinstance(cases, list)


def test_prompt_engine_extracts_case_features():
    features = PromptEngine()._chart_to_case_features(_sample_chart())

    assert features["dm_gan"] == "丙"
    assert features["dm_wu"] == "火"
    assert features["month_zhi"] == "丑"
    assert features["strongest_wu"] in {"木", "火", "土"}


def test_prompt_engine_trusted_mode_contains_required_sections():
    system_prompt, _ = PromptEngine(reasoning_mode='trusted').assemble(
        chart=_sample_chart(),
        pre_analysis=_sample_pre_analysis(),
        topic='career',
        question='请分析事业',
    )
    assert '命理依据' in system_prompt
    assert '现实解释' in system_prompt
    assert '谨慎建议' in system_prompt
    assert '可行动步骤' in system_prompt
    assert '不做绝对化预测' in system_prompt


def test_prompt_engine_accepts_conversation_summary():
    system_prompt, _ = PromptEngine(
        reasoning_mode='trusted',
        conversation_summary='用户关注事业转型',
    ).assemble(
        chart=_sample_chart(),
        pre_analysis=_sample_pre_analysis(),
        topic='career',
        question='请分析事业',
    )
    assert '用户关注事业转型' in system_prompt
