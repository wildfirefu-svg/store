from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter
from typing import Any

from benchmark.scorers.choice_accuracy import extract_choice, load_jsonl
from benchmark.formatters.two_stage_reasoning import is_time_location_question


DOMAIN_PRIORITY = ("marriage", "family", "health", "career", "wealth", "personality")

DOMAIN_KEYWORDS = {
    "marriage": ("婚", "结婚", "离婚", "配偶", "丈夫", "老婆", "夫", "妻", "感情", "桃花", "未嫁", "未婚"),
    "family": ("家境", "出生", "出身", "父母", "父亲", "母亲", "父", "母", "祖上", "兄弟姐妹", "家庭"),
    "health": ("病", "健康", "抑郁", "失眠", "手术", "伤", "灾", "残", "精神", "体质"),
    "career": ("事业", "工作", "职业", "行业", "官", "公职", "创业", "升职", "职位", "学历"),
    "wealth": ("财", "富", "贫", "赚钱", "收入", "破财", "经商", "投资", "财富"),
    "personality": ("性格", "个性", "评价", "人缘", "朋友", "暴躁", "内向", "独处", "保守", "义气", "桃花"),
}

WEIGHTS = {"strong": 30, "medium": 18, "weak": 12}


def normalize_option(option: str) -> str:
    return re.sub(r"^[A-D][\.\、\)]?[\s　]*", "", str(option or "")).strip()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _count_matches(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def detect_question_domain(question: str, options: list[str], gender: str = "unknown") -> str:
    text = f"{question or ''} {' '.join(normalize_option(opt) for opt in options)}"
    hits = {
        domain
        for domain, keywords in DOMAIN_KEYWORDS.items()
        if _contains_any(text, keywords)
    }
    if "family" in hits and _contains_any(question or "", DOMAIN_KEYWORDS["family"]):
        return "family"
    if "personality" in hits and _contains_any(question or "", DOMAIN_KEYWORDS["personality"]):
        return "personality"
    if "marriage" in hits:
        return "marriage"
    if "career" in hits and _contains_any(question or "", DOMAIN_KEYWORDS["career"]):
        return "career"
    if "family" in hits and "wealth" in hits and _contains_any(question or "", DOMAIN_KEYWORDS["family"]):
        return "family"
    if "career" in hits and "wealth" in hits:
        career_hits = _count_matches(text, DOMAIN_KEYWORDS["career"])
        wealth_hits = _count_matches(text, DOMAIN_KEYWORDS["wealth"])
        if career_hits > wealth_hits:
            return "career"
        if wealth_hits > career_hits:
            return "wealth"
    if (gender or "").lower() in {"female", "女"} and "官" in text and "婚" in text:
        return "marriage"
    if (gender or "").lower() in {"male", "男"} and "财" in text and "婚" in text:
        return "marriage"
    for domain in DOMAIN_PRIORITY:
        if domain in hits:
            return domain
    return "unknown"


def _shishen_count(counts: dict[str, Any], names: tuple[str, ...]) -> int:
    total = 0
    for name in names:
        try:
            total += int(counts.get(name, 0) or 0)
        except (TypeError, ValueError):
            pass
    return total


def extract_chart_signals(case: dict) -> dict:
    chart = case.get("chart_input") or {}
    shishen = chart.get("shishen_stats") or {}
    counts = shishen.get("counts") or {}
    missing = set(shishen.get("missing") or [])
    relations = chart.get("branch_relations") or []
    relation_text = " ".join(
        f"{rel.get('type', '')}{rel.get('detail', '')}"
        for rel in relations
        if isinstance(rel, dict)
    )
    shensha = chart.get("shensha") or []
    shensha_names = {
        item.get("name")
        for item in shensha
        if isinstance(item, dict) and item.get("name")
    }
    wuxing = chart.get("wuxing_stats") or {}
    return {
        "gender": ((case.get("person") or {}).get("gender") or (chart.get("birth_info") or {}).get("gender") or "unknown"),
        "shishen_counts": counts,
        "missing": missing,
        "wealth_count": _shishen_count(counts, ("正财", "偏财")),
        "officer_count": _shishen_count(counts, ("正官", "七杀")),
        "yin_count": _shishen_count(counts, ("正印", "偏印")),
        "output_count": _shishen_count(counts, ("食神", "伤官")),
        "bijie_count": _shishen_count(counts, ("比肩", "劫财")),
        "has_conflict": any(token in relation_text for token in ("冲", "刑", "害", "破")),
        "has_taohua": bool(shensha_names & {"桃花", "红艳", "红鸾", "天喜"}),
        "has_lonely": bool(shensha_names & {"孤鸾煞", "孤辰", "寡宿", "阴差阳错"}),
        "has_injury": bool(shensha_names & {"白虎", "血刃", "羊刃", "丧门"}),
        "wuxing_missing": set(wuxing.get("missing") or []),
        "wuxing_strongest": wuxing.get("strongest"),
        "wuxing_weakest": wuxing.get("weakest"),
    }


def _add(items: list[dict], kind: str, weight: str, reason: str, rule_id: str) -> None:
    items.append({"kind": kind, "weight": weight, "reason": reason, "rule_id": rule_id})


def _apply_common_rules(domain: str, text: str, signals: dict) -> list[dict]:
    items: list[dict] = []
    wealth = signals["wealth_count"]
    officer = signals["officer_count"]
    yin = signals["yin_count"]
    output = signals["output_count"]
    bijie = signals["bijie_count"]
    conflict = signals["has_conflict"]

    if domain in {"family", "wealth", "unknown"}:
        if _contains_any(text, ("富", "有钱", "盈余", "中产", "大富", "家境好", "发财", "资金", "顺利", "蒸蒸日上", "十万存款")):
            if wealth >= 1 and output >= 1 and bijie < 3 and "正财" not in signals["missing"]:
                _add(items, "support", "strong", "财星有力且食伤可生财", "wealth_score_rich_by_wealth_strength")
            elif wealth >= 1:
                _add(items, "support", "medium", "命局见财星", "wealth_score_rich_by_wealth")
            if wealth == 0 or "正财" in signals["missing"]:
                _add(items, "reject", "strong", "财星弱或缺正财", "wealth_score_rich_by_weak_wealth")
            if bijie >= 3:
                _add(items, "reject", "medium", "比劫旺有夺财风险", "wealth_score_rich_by_bijie")
        if _contains_any(text, ("贫", "欠债", "负债", "捉襟见肘", "普通", "盈余不多", "家境差", "生活困难", "月光", "倒闭", "不够资金")):
            if wealth == 0 or bijie >= 3:
                _add(items, "support", "strong", "财星弱或比劫旺", "wealth_score_poor_by_weak_wealth")
            elif wealth <= 1:
                _add(items, "support", "medium", "财星不旺", "wealth_score_poor_by_weak_wealth")
            if wealth >= 2 and output >= 1 and bijie < 2:
                _add(items, "reject", "strong", "财星有力且有生财结构", "wealth_score_poor_by_wealth_strength")
        if _contains_any(text, ("父从商", "经商", "创业", "投资", "经营", "买卖", "老板", "企业主", "小生意", "生意", "商人", "零售")):
            if wealth >= 1 and output >= 1:
                _add(items, "support", "strong", "财星与食伤并见", "family_score_father_business_by_wealth")
            if officer >= 2 and yin >= 1:
                _add(items, "reject", "medium", "官印结构偏稳定组织", "family_score_business_reject_by_officer_yin")
        if _contains_any(text, ("当官", "公职", "村干部", "管理", "职位", "政府", "高管", "国企", "稳定", "受薪", "上班")):
            if officer >= 1 and yin >= 1:
                _add(items, "support", "strong", "官印相生或官印并见", "family_score_parent_official_by_officer_yin")
            if output >= 3:
                _add(items, "reject", "medium", "伤食旺易冲官星", "family_score_official_reject_by_output")
        if _contains_any(text, ("父亲去世", "母亲去世", "病亡", "去世", "守寡", "患病", "染病")):
            if conflict or signals["has_injury"]:
                _add(items, "support", "strong", "冲刑或伤灾信号对应六亲损伤", "family_score_death_by_conflict_injury")
            elif yin == 0 or wealth == 0:
                _add(items, "support", "medium", "父母星弱", "family_score_death_by_parent_star_weak")
        if _contains_any(text, ("子女", "一子", "一女", "三女", "不能生育", "生育")):
            if output >= 1:
                _add(items, "support", "medium", "食伤子女星可见", "family_score_children_by_output")
            if output == 0 and _contains_any(text, ("没有子女", "不能生育")):
                _add(items, "support", "strong", "食伤子女星弱", "family_score_no_children_by_weak_output")

    if domain in {"marriage", "unknown"}:
        spouse_count = wealth if str(signals.get("gender")).lower() in {"male", "男"} else officer
        if _contains_any(text, ("稳定", "一婚", "婚姻好", "夫妻和", "婚姻美满", "相敬如宾", "已婚")):
            if spouse_count >= 1 and not conflict:
                _add(items, "support", "strong", "配偶星可见且夫妻宫少冲刑", "marriage_score_stable_by_spouse_star")
            elif spouse_count >= 1 and "已婚" in text:
                _add(items, "support", "medium", "配偶星可见", "marriage_score_married_by_spouse_star")
            if spouse_count == 0:
                _add(items, "reject", "strong", "配偶星缺失", "marriage_score_stable_reject_no_spouse")
            if (conflict or signals["has_lonely"]) and not _contains_any(text, ("有育", "子女", "孩子", "子嗣")):
                _add(items, "reject", "strong", "夫妻宫冲刑或孤鸾类信号", "marriage_score_stable_reject_by_conflict")
        if _contains_any(text, ("有育", "子女", "孩子", "子嗣")):
            if spouse_count >= 1:
                _add(items, "support", "strong", "配偶星可见且有子女应象", "marriage_score_children_by_spouse_star")
            if spouse_count == 0 and conflict:
                _add(items, "reject", "medium", "配偶星弱且婚姻冲刑", "marriage_score_children_reject_by_spouse_damage")
        if _contains_any(text, ("二婚", "多婚", "离婚", "离异", "吵闹", "伤害", "责惹", "感情波折", "未婚", "未嫁", "未娶", "失婚", "同性恋")):
            if conflict or signals["has_lonely"]:
                _add(items, "support", "strong", "夫妻宫冲刑或孤鸾类信号", "marriage_score_multiple_by_conflict")
            if spouse_count == 0:
                _add(items, "support", "medium", "配偶星缺失", "marriage_score_multiple_by_missing_spouse")
            if spouse_count >= 1 and not conflict:
                _add(items, "reject", "strong", "配偶星可见且冲刑不重", "marriage_score_multiple_reject_by_spouse_star")
        if _contains_any(text, ("同性恋", "伴侣爱护", "得到伴侣")):
            if conflict or signals["has_lonely"]:
                _add(items, "support", "strong", "婚恋非传统信号较重", "marriage_score_same_sex_by_conflict_lonely")
        if _contains_any(text, ("丈夫病亡", "丈夫去世", "夫亡", "夫早亡", "丧偶")):
            if spouse_count == 0 or conflict or signals["has_lonely"] or signals["has_injury"]:
                _add(items, "support", "strong", "夫星弱或夫妻宫冲刑孤鸾", "marriage_score_widow_by_spouse_damage")
            if spouse_count >= 1 and not conflict:
                _add(items, "reject", "medium", "夫星可见且冲刑不重", "marriage_score_widow_reject_by_spouse_star")
        if _contains_any(text, ("结婚", "成婚")):
            if spouse_count >= 1 and signals["has_taohua"]:
                _add(items, "support", "strong", "配偶星与桃花喜庆信号并见", "marriage_score_marriage_by_spouse_taohua")
            elif spouse_count >= 1:
                _add(items, "support", "medium", "配偶星可见", "marriage_score_marriage_by_spouse_star")
            if spouse_count == 0 and (conflict or signals["has_lonely"]):
                _add(items, "reject", "strong", "配偶星弱且婚姻冲刑孤鸾明显", "marriage_score_marriage_reject_by_conflict")
        if _contains_any(text, ("娶妻", "已娶", "第1段", "第2段", "第3段")):
            if spouse_count >= 1:
                _add(items, "support", "medium", "配偶星可见", "marriage_score_married_by_spouse_star")
            if conflict or signals["has_lonely"]:
                _add(items, "support", "medium", "婚姻冲刑孤鸾信号对应感情波折", "marriage_score_married_conflict_context")
        if _contains_any(text, ("妻即离世", "丈夫逝世", "丈夫病亡", "妻子去世")):
            if conflict or signals["has_lonely"] or signals["has_injury"]:
                _add(items, "support", "strong", "夫妻宫冲刑孤鸾或伤灾信号", "marriage_score_spouse_death_by_damage")
        if _contains_any(text, ("暴力", "互殴", "打骂")):
            if conflict:
                _add(items, "support", "strong", "夫妻宫冲刑对应暴力冲突", "marriage_score_violence_by_conflict")
        if _contains_any(text, ("配偶经商", "妻子经商", "丈夫经商")):
            if wealth >= 1 and output >= 1:
                _add(items, "support", "strong", "财星食伤支持配偶经商", "marriage_score_spouse_business_by_wealth_output")
            if bijie >= 3:
                _add(items, "reject", "medium", "比劫旺对经营稳定性不利", "marriage_score_spouse_business_reject_by_bijie")
        if _contains_any(text, ("配偶是打工", "打工仔", "职级", "收入")):
            if officer >= 1 or yin >= 1:
                _add(items, "support", "medium", "官印信号对应稳定受薪", "marriage_score_spouse_salary_by_officer_yin")
        if _contains_any(text, ("桃花", "异性缘")) and signals["has_taohua"]:
            _add(items, "support", "medium", "桃花/红鸾/天喜类神煞", "marriage_score_romance_by_taohua")

    if domain in {"career", "unknown"}:
        if _contains_any(text, ("公职", "当官", "管理", "职位", "稳定组织", "政府", "国企", "高管", "受薪", "上班", "企业", "普通公司", "私人企业")):
            if officer >= 1 and yin >= 1:
                _add(items, "support", "strong", "官印相生或官印并见", "career_score_official_by_officer_yin")
            if output >= 3:
                _add(items, "reject", "medium", "食伤旺有伤官见官倾向", "career_score_official_reject_by_output")
        if _contains_any(text, ("经商", "创业", "商业", "投机", "经营", "老板", "买卖", "开店", "生意", "家族生意", "商人", "零售")):
            if wealth >= 1 and output >= 1:
                _add(items, "support", "strong", "财星/食伤支持商业经营", "career_score_business_by_wealth_output")
            if officer >= 2 and yin >= 1:
                _add(items, "reject", "medium", "官印重偏稳定路径", "career_score_business_reject_by_officer_yin")
        if _contains_any(text, ("学历", "文职", "教育", "技术", "专业", "大学", "硕士", "博士", "高中", "中学", "小学", "读书", "毕业", "肄业", "文科", "理工", "金融", "美术", "音乐")):
            if yin >= 2 or (yin >= 1 and output >= 1):
                _add(items, "support", "strong", "印星或食伤支持学习技术", "career_score_education_by_yin_output")
            elif yin >= 1 or output >= 1:
                _add(items, "support", "medium", "印星或食伤支持学习技术", "career_score_education_by_yin_output")
            if yin == 0 and output == 0:
                _add(items, "reject", "medium", "印星食伤皆弱", "career_score_education_reject_by_weak_yin_output")
        if _contains_any(text, ("老师", "学校")):
            if yin >= 1:
                _add(items, "support", "medium", "印星支持教育类工作", "career_score_teacher_by_yin")
        if _contains_any(text, ("工厂", "国企")):
            if officer >= 1 or yin >= 1:
                _add(items, "support", "strong", "官印或规则性结构支持组织岗位", "career_score_factory_state_by_officer_yin")
        if _contains_any(text, ("公务员", "退休")):
            if officer >= 1 or yin >= 1:
                _add(items, "support", "strong", "官印支持公职体系", "career_score_public_service_by_officer_yin")
            if output >= 3 and _contains_any(text, ("刑事", "案件", "提早退休")):
                _add(items, "support", "medium", "伤官旺对应体制冲突", "career_score_public_service_conflict_by_output")
        if _contains_any(text, ("建筑工人", "工人", "畜牧场")):
            if bijie >= 2 or output >= 1:
                _add(items, "support", "medium", "比劫食伤对应体力或经营型工作", "career_score_labor_by_bijie_output")
        if _contains_any(text, ("健身", "教练", "运动")):
            if bijie >= 2 or output >= 1:
                _add(items, "support", "medium", "比劫食伤支持体能表达类工作", "career_score_fitness_by_bijie_output")
        if _contains_any(text, ("兼职", "打工", "舞女", "卖艺", "不用工作", "懒惰")):
            if output >= 2 or bijie >= 2:
                _add(items, "support", "medium", "食伤比劫偏旺，职业稳定性不足", "career_score_unstable_by_output_bijie")
            if officer >= 1 and yin >= 1:
                _add(items, "reject", "medium", "官印结构不支持过度漂浮", "career_score_unstable_reject_by_officer_yin")

    if domain in {"health", "unknown"}:
        if _contains_any(text, ("伤", "灾", "手术", "残", "意外")):
            if signals["has_injury"] or conflict:
                _add(items, "support", "strong", "白虎血刃羊刃或冲刑信号", "health_score_injury_by_shensha_conflict")
            if not signals["has_injury"] and not conflict:
                _add(items, "reject", "medium", "伤灾类神煞和冲刑不明显", "health_score_injury_reject_by_stable")
        if _contains_any(text, ("精神", "抑郁", "失眠", "患病", "病症", "住院", "治疗", "病亡")):
            if officer >= 2 or yin >= 3:
                _add(items, "support", "strong", "官杀或印星偏重", "health_score_mental_by_kill_yin")
            if signals["has_injury"] or conflict:
                _add(items, "support", "medium", "冲刑或伤灾信号引动疾病", "health_score_illness_by_conflict")
        if _contains_any(text, ("健康", "身体好", "少病")):
            if not conflict and not signals["has_injury"]:
                _add(items, "support", "medium", "冲刑和伤灾信号不重", "health_score_healthy_by_balance")
            if conflict or signals["has_injury"]:
                _add(items, "reject", "strong", "冲刑或伤灾信号明显", "health_score_healthy_reject_by_conflict")

    if domain in {"personality", "unknown"}:
        if _contains_any(text, ("可靠", "义气", "仗义", "朋友", "人缘", "不怕事")):
            if bijie >= 2:
                _add(items, "support", "strong", "比劫有力", "personality_score_loyal_by_bijie")
        if _contains_any(text, ("内向", "独处", "保守", "沉默", "情绪化")):
            if yin >= 2 or signals["has_lonely"]:
                _add(items, "support", "strong", "印星重或孤辰华盖类信号", "personality_score_introvert_by_yin_kill")
        if _contains_any(text, ("暴躁", "急躁", "冲动", "固执", "外向", "风头", "阳光")):
            if officer >= 2 or output >= 3 or conflict:
                _add(items, "support", "strong", "七杀食伤或冲刑偏重", "personality_score_irritable_by_kill_conflict")
        if _contains_any(text, ("足智多谋", "聪明", "聪敏")):
            if output >= 1 or yin >= 1:
                _add(items, "support", "medium", "食伤印星支持聪敏表达", "personality_score_smart_by_output_yin")
        if _contains_any(text, ("桃花", "异性缘", "女人缘", "风流", "好色")):
            if signals["has_taohua"]:
                _add(items, "support", "strong", "桃花/红鸾/天喜类神煞", "personality_score_romance_by_taohua")
            if signals["has_lonely"]:
                _add(items, "reject", "weak", "孤鸾孤辰类信号削弱桃花", "personality_score_romance_reject_by_lonely")

    return items


def _verdict(score: int) -> str:
    if score >= 75:
        return "strong_support"
    if score >= 60:
        return "weak_support"
    if score >= 41:
        return "neutral"
    if score >= 25:
        return "weak_reject"
    return "strong_reject"


def score_options(case: dict) -> list[dict]:
    options = list(case.get("options") or [])
    if is_time_location_question(case.get("question", ""), options):
        return []
    gender = ((case.get("person") or {}).get("gender") or "unknown")
    domain = detect_question_domain(case.get("question", ""), options, gender=gender)
    signals = extract_chart_signals(case)
    scores = []
    for idx, option in enumerate(options):
        label = chr(ord("A") + idx)
        text = normalize_option(option)
        matches = _apply_common_rules(domain, text, signals)
        support = [m for m in matches if m["kind"] == "support"]
        reject = [m for m in matches if m["kind"] == "reject"]
        support_sum = sum(WEIGHTS[m["weight"]] for m in support)
        reject_sum = sum(WEIGHTS[m["weight"]] for m in reject)
        score = max(0, min(100, 50 + support_sum - reject_sum))
        scores.append({
            "label": label,
            "text": text,
            "domain": domain,
            "score": score,
            "verdict": _verdict(score),
            "support": [m["reason"] for m in support[:3]],
            "reject": [m["reason"] for m in reject[:3]],
            "matched_rules": [m["rule_id"] for m in matches],
        })
    return scores


def _format_reasons(name: str, reasons: list[str]) -> str:
    if not reasons:
        return ""
    return f"{name}: {', '.join(reasons[:3])}"


def format_option_scores(scores: list[dict]) -> list[str]:
    if not scores:
        return []
    lines = ["【逐选项命理评分】"]
    for item in scores:
        reason_parts = [
            part
            for part in (
                _format_reasons("support", item.get("support") or []),
                _format_reasons("reject", item.get("reject") or []),
            )
            if part
        ]
        reason_text = f" [{'; '.join(reason_parts)}]" if reason_parts else ""
        lines.append(
            f"{item.get('label')}. {item.get('text')} -> "
            f"{item.get('score')}/100 ({item.get('verdict')}){reason_text}"
        )
    lines.append("")
    lines.append("【逐选项评分汇总】")
    lines.append(format_option_score_summary(scores))
    return lines


def format_option_score_summary(scores: list[dict]) -> str:
    return " | ".join(
        f"{item.get('label')}={item.get('score')} {item.get('verdict')}"
        for item in scores
    )


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or not xs:
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def summarize_scores(cases: list[dict]) -> dict:
    total_cases = 0
    top_hits = 0
    option_scores = []
    option_is_correct = []
    neutral_count = 0
    strong_count = 0
    correct_scores = []
    wrong_scores = []
    domain_counts = Counter()
    scored_cases = []
    for case in cases:
        scores = score_options(case)
        if not scores:
            continue
        total_cases += 1
        expected = extract_choice(case.get("answer"))
        domain_counts[scores[0].get("domain", "unknown")] += 1
        max_score = max(item["score"] for item in scores)
        top_labels = {item["label"] for item in scores if item["score"] == max_score}
        if expected in top_labels:
            top_hits += 1
        for item in scores:
            is_correct = item["label"] == expected
            option_scores.append(float(item["score"]))
            option_is_correct.append(1.0 if is_correct else 0.0)
            if item["verdict"] == "neutral":
                neutral_count += 1
            if item["verdict"] in {"strong_support", "strong_reject"}:
                strong_count += 1
            if is_correct:
                correct_scores.append(item["score"])
            else:
                wrong_scores.append(item["score"])
        scored_cases.append({
            "case_id": case.get("case_id"),
            "expected_answer": expected,
            "scores": scores,
        })
    option_total = len(option_scores)
    return {
        "n_cases": total_cases,
        "n_options": option_total,
        "top_score_hit_rate": top_hits / total_cases if total_cases else 0.0,
        "correct_option_mean_score": sum(correct_scores) / len(correct_scores) if correct_scores else 0.0,
        "wrong_option_mean_score": sum(wrong_scores) / len(wrong_scores) if wrong_scores else 0.0,
        "score_answer_correlation": _pearson(option_scores, option_is_correct),
        "neutral_option_rate": neutral_count / option_total if option_total else 0.0,
        "strong_signal_option_rate": strong_count / option_total if option_total else 0.0,
        "domain_distribution": dict(domain_counts),
        "cases": scored_cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 C2 per-option scorer calibration")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    cases = load_jsonl(args.dataset)
    if args.max_cases is not None:
        cases = cases[:args.max_cases]
    summary = summarize_scores(cases)
    parent = os.path.dirname(os.path.abspath(args.output))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
