import pytest

from bazi_report_validator import (
    strip_report_preface,
    validate_report_claims,
    load_yaml_rules,
    validate_against_yaml_rules,
)


CHART_1990_05_12_FEMALE = {
    "four_pillars": {
        "year": {"gan": "庚", "zhi": "午"},
        "month": {"gan": "辛", "zhi": "巳"},
        "day": {"gan": "丁", "zhi": "丑"},
        "hour": {"gan": "甲", "zhi": "辰"},
    },
    "day_master": {"gan": "丁", "wuxing": "火", "yinyang": "阴"},
    "birth_info": {
        "year": 1990,
        "month": 5,
        "day": 12,
        "hour": 8,
        "minute": 30,
        "gender": "female",
        "location": "北京",
    },
}


def issue_codes(issues):
    return {issue["code"] for issue in issues}


def test_flags_three_meeting_claim_when_required_branch_is_missing():
    report = "丁火生于巳月，地支巳午未会火局，火势极旺。"
    issues = validate_report_claims(CHART_1990_05_12_FEMALE, report)

    assert "missing_branch_for_combo" in issue_codes(issues)
    assert any("未" in issue["message"] for issue in issues)


def test_accepts_three_meeting_claim_when_all_branches_exist():
    chart = {
        **CHART_1990_05_12_FEMALE,
        "four_pillars": {
            "year": {"gan": "庚", "zhi": "午"},
            "month": {"gan": "辛", "zhi": "巳"},
            "day": {"gan": "丁", "zhi": "未"},
            "hour": {"gan": "甲", "zhi": "辰"},
        },
    }
    report = "地支巳午未会火局，火势成方。"
    issues = validate_report_claims(chart, report)

    assert "missing_branch_for_combo" not in issue_codes(issues)


def test_flags_wrong_storage_branch_claim():
    report = "日支丑为火库，能收丁火余气。"
    issues = validate_report_claims(CHART_1990_05_12_FEMALE, report)

    assert "wrong_storage_branch" in issue_codes(issues)
    assert any("火库为戌" in issue["message"] for issue in issues)


def test_flags_month_order_wealth_claim_when_month_branch_main_qi_is_not_wealth():
    report = "月令财星当令，偏财格根气极旺。"
    issues = validate_report_claims(CHART_1990_05_12_FEMALE, report)

    assert "unsupported_month_wealth_order" in issue_codes(issues)
    assert any("巳月本气为丙火" in issue["message"] for issue in issues)


def test_strip_report_preface_removes_conversational_opening():
    raw = "好的，我将遵循结构化推理协议，为您进行四合出综合分析。\n\n***\n\n一、八字排盘\n正文"

    assert strip_report_preface(raw).startswith("一、八字排盘")


def test_strip_report_preface_preserves_report_that_already_starts_with_title():
    raw = "一、八字排盘\n正文"

    assert strip_report_preface(raw) == raw


def test_loads_extra_rules_from_yaml(tmp_path):
    yaml_path = tmp_path / "rules.yaml"
    yaml_path.write_text(
        "rules:\n"
        "  - id: ding_si_career_hard\n"
        "    pattern:\n"
        "      day_master_gan: 丁\n"
        "      month_zhi: 巳\n"
        "    expected_event: 事业初期多坎坷\n"
        "    forbidden_phrases: ['事业一帆风顺','少年得志']\n"
        "    support: 4\n"
        "    confidence: 0.75\n"
        "    severity: warning\n"
        "    message: '丁火生巳月，corpus 反推事业初期多坎坷，需复核“事业一帆风顺”表述。'\n"
        "  - id: low_support_rule\n"
        "    pattern:\n"
        "      day_master_gan: 庚\n"
        "    expected_event: x\n"
        "    forbidden_phrases: ['任何']\n"
        "    support: 1\n"
        "    confidence: 0.9\n"
        "    severity: warning\n"
        "    message: 'too few cases'\n",
        encoding="utf-8",
    )
    rules = load_yaml_rules(yaml_path)
    issues = validate_against_yaml_rules(
        CHART_1990_05_12_FEMALE,
        "命主事业一帆风顺，少年得志。",
        rules,
    )
    codes = issue_codes(issues)
    assert "yaml_rule:ding_si_career_hard" in codes


def test_yaml_rule_requires_min_support_3(tmp_path):
    yaml_path = tmp_path / "rules.yaml"
    yaml_path.write_text(
        "rules:\n"
        "  - id: too_few\n"
        "    pattern:\n"
        "      day_master_gan: 丁\n"
        "    expected_event: x\n"
        "    forbidden_phrases: ['xx']\n"
        "    support: 2\n"
        "    confidence: 0.9\n"
        "    severity: warning\n"
        "    message: 'should be filtered'\n",
        encoding="utf-8",
    )
    rules = load_yaml_rules(yaml_path)
    assert all(r["id"] != "too_few" for r in rules)
