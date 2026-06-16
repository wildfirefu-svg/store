#!/usr/bin/env python3
import importlib.util
import json
import os

SYSTEM_PROMPTS = {
    "sihechu": """你是一位严谨的命理分析助手。输出必须包含：核心判断、证据链、反证据与不确定性、分项分析、实用建议。每个重要判断都要给出八字证据和置信度。""",
    "career": """你是一位严谨的命理事业分析助手。输出必须包含：核心判断、证据链、反证据与不确定性、事业路径、实用建议。""",
    "marriage": """你是一位严谨的命理婚恋分析助手。输出必须包含：核心判断、证据链、反证据与不确定性、关系建议、实用建议。""",
}


class PromptEngine:
    def __init__(self, prompt_version="srp_v1", reasoning_protocol="xuanjizi_srp_v1"):
        self.prompt_version = prompt_version
        self.reasoning_protocol = reasoning_protocol

    def assemble(self, chart, pre_analysis=None, topic="sihechu", question=""):
        system_prompt = self.build_system_prompt(topic)
        domain_knowledge = self.build_domain_knowledge(chart, topic)
        dynamic_context = self.build_dynamic_context(chart, pre_analysis or {}, question)
        return system_prompt, f"{domain_knowledge}\n\n---\n\n{dynamic_context}"

    def build_system_prompt(self, topic):
        base_prompt = SYSTEM_PROMPTS.get(topic, SYSTEM_PROMPTS["sihechu"])
        protocol_text = self._load_structured_reasoning_protocol()
        return "\n\n".join([
            base_prompt,
            f"Prompt版本：{self.prompt_version}",
            f"推理协议：{self.reasoning_protocol}",
            "请遵循以下结构化推理协议完成分析：",
            protocol_text,
        ])

    def build_domain_knowledge(self, chart, topic):
        cases = self.retrieve_similar_cases(chart)
        case_text = "\n\n".join(cases) if cases else "暂无相似案例。"
        return "\n".join([
            "## 领域知识",
            f"分析主题：{topic}",
            "## 相似案例参考",
            case_text,
        ])

    def build_dynamic_context(self, chart, pre_analysis, question):
        return "\n".join([
            "## 当前命盘数据",
            json.dumps(chart, ensure_ascii=False, indent=2),
            "## 本地预分析",
            json.dumps(pre_analysis, ensure_ascii=False, indent=2),
            "## 用户问题",
            question or "请进行综合分析。",
        ])

    def retrieve_similar_cases(self, chart):
        try:
            module = self._load_case_retrieval_module()
            retriever = module.CaseRetriever()
            query_features = self._chart_to_case_features(chart)
            results = retriever.retrieve(query_features, top_n=3, mode="simple")
            return [module.format_case_for_prompt(case) for case in results[:3]]
        except Exception:
            return []

    def _load_structured_reasoning_protocol(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, "prompts", "structured_reasoning_v1.md")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "\n".join([
                "# Xuanjizi-SRP-v1 结构化推理协议",
                "命盘基础扫描",
                "结构关系识别",
                "强弱与冲突定级",
                "领域映射",
                "事件映射",
                "用户可读表达",
                "不做绝对化预测",
            ])

    def _load_case_retrieval_module(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        module_path = os.path.join(base_dir, "knowledge-base", "case_retrieval.py")
        spec = importlib.util.spec_from_file_location("case_retrieval_for_prompt", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _chart_to_case_features(self, chart):
        day_master = chart.get("day_master") or {}
        four_pillars = chart.get("four_pillars") or {}
        month = four_pillars.get("month") or {}
        wuxing_stats = chart.get("wuxing_stats") or chart.get("wu_counts") or {}
        return {
            "dm_gan": day_master.get("gan") or chart.get("day_gan") or "",
            "dm_wu": day_master.get("wuxing") or day_master.get("wu") or "",
            "month_zhi": month.get("zhi") or chart.get("month_zhi") or "",
            "strongest_wu": self._strongest_wuxing(wuxing_stats),
            "wu_counts": wuxing_stats,
        }

    def _strongest_wuxing(self, wuxing_stats):
        if not isinstance(wuxing_stats, dict) or not wuxing_stats:
            return ""
        normalized = {
            "金": wuxing_stats.get("金", wuxing_stats.get("jin", 0)),
            "木": wuxing_stats.get("木", wuxing_stats.get("mu", 0)),
            "水": wuxing_stats.get("水", wuxing_stats.get("shui", 0)),
            "火": wuxing_stats.get("火", wuxing_stats.get("huo", 0)),
            "土": wuxing_stats.get("土", wuxing_stats.get("tu", 0)),
        }
        return max(normalized, key=normalized.get)
