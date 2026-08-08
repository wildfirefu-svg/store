"""Rule-based validation for AI-generated BaZi report text."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml
except Exception:  # pragma: no cover - PyYAML is optional but expected.
    _yaml = None


GAN_WUXING = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

ZHI_MAIN_GAN = {
    "子": "癸",
    "丑": "己",
    "寅": "甲",
    "卯": "乙",
    "辰": "戊",
    "巳": "丙",
    "午": "丁",
    "未": "己",
    "申": "庚",
    "酉": "辛",
    "戌": "戊",
    "亥": "壬",
}

CONTROLS = {
    "木": "土",
    "火": "金",
    "土": "水",
    "金": "木",
    "水": "火",
}

BRANCH_COMBOS = {
    "寅卯辰": "东方木三会",
    "巳午未": "南方火三会",
    "申酉戌": "西方金三会",
    "亥子丑": "北方水三会",
    "申子辰": "水三合",
    "亥卯未": "木三合",
    "寅午戌": "火三合",
    "巳酉丑": "金三合",
}

STORAGE_BRANCH_BY_ELEMENT = {
    "木": "未",
    "火": "戌",
    "金": "丑",
    "水": "辰",
}


def _chart_branches(chart: dict) -> set:
    pillars = chart.get("four_pillars") or {}
    return {
        str(pillar.get("zhi"))
        for pillar in pillars.values()
        if isinstance(pillar, dict) and pillar.get("zhi")
    }


def _month_branch(chart: dict) -> str:
    month = (chart.get("four_pillars") or {}).get("month") or {}
    return str(month.get("zhi") or "")


def _day_master_element(chart: dict) -> str:
    dm = chart.get("day_master") or {}
    if isinstance(dm, dict):
        if dm.get("wuxing"):
            return str(dm["wuxing"])
        gan = str(dm.get("gan") or "")
    else:
        gan = str(dm or "")
    return GAN_WUXING.get(gan, "")


def _issue(code: str, severity: str, message: str, evidence: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "evidence": evidence,
    }


def _validate_branch_combos(chart: dict, text: str) -> Iterable[dict[str, str]]:
    branches = _chart_branches(chart)
    for combo, label in BRANCH_COMBOS.items():
        if combo not in text:
            continue
        missing = [zhi for zhi in combo if zhi not in branches]
        if missing:
            yield _issue(
                "missing_branch_for_combo",
                "error",
                f"报告提到{combo}{label}，但命盘地支缺少{'、'.join(missing)}。",
                combo,
            )


def _validate_storage_claims(text: str) -> Iterable[dict[str, str]]:
    for branch, element in re.findall(r"([子丑寅卯辰巳午未申酉戌亥])(?:土)?为([木火金水])库", text):
        expected = STORAGE_BRANCH_BY_ELEMENT[element]
        if branch != expected:
            yield _issue(
                "wrong_storage_branch",
                "error",
                f"{element}库为{expected}，不是{branch}。",
                f"{branch}为{element}库",
            )


def _validate_month_wealth_order(chart: dict, text: str) -> Iterable[dict[str, str]]:
    if not any(phrase in text for phrase in ("财星当令", "月令财星", "财星得令")):
        return
    month_zhi = _month_branch(chart)
    day_element = _day_master_element(chart)
    wealth_element = CONTROLS.get(day_element, "")
    main_gan = ZHI_MAIN_GAN.get(month_zhi, "")
    main_element = GAN_WUXING.get(main_gan, "")
    if month_zhi and wealth_element and main_element != wealth_element:
        yield _issue(
            "unsupported_month_wealth_order",
            "warning",
            f"{month_zhi}月本气为{main_gan}{main_element}，日主{day_element}的财星为{wealth_element}，不能直接写财星当令。",
            "财星当令",
        )


DEFAULT_YAML_RULES_PATH = Path(__file__).resolve().parent / "knowledge-base" / "baziqa_rules.yaml"
_yaml_rules_cache: list[dict[str, Any]] | None = None


def _default_yaml_rules() -> list[dict[str, Any]]:
    global _yaml_rules_cache
    if _yaml_rules_cache is None:
        _yaml_rules_cache = load_yaml_rules(DEFAULT_YAML_RULES_PATH)
    return _yaml_rules_cache


def validate_report_claims(chart: dict, report_text: str) -> list[dict[str, str]]:
    """Return deterministic issues where report text conflicts with chart facts."""
    text = str(report_text or "")
    issues: list[dict[str, str]] = []
    issues.extend(_validate_branch_combos(chart, text))
    issues.extend(_validate_storage_claims(text))
    issues.extend(_validate_month_wealth_order(chart, text))
    issues.extend(validate_against_yaml_rules(chart, text, _default_yaml_rules()))
    return issues


def strip_report_preface(report_text: str) -> str:
    """Remove model preface before the first formal report section."""
    text = str(report_text or "").strip()
    if not text:
        return ""
    patterns = [
        r"(?:\*\*\*\s*)?(一、八字排盘.*)",
        r"(?:\*\*\*\s*)?(#\s*八字排盘.*)",
        r"(?:\*\*\*\s*)?(##\s*一[、.．]\s*八字排盘.*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
    return text


def format_validation_note(issues: list[dict[str, str]]) -> str:
    if not issues:
        return ""
    lines = ["## 系统校验提示", ""]
    for issue in issues:
        label = "错误" if issue["severity"] == "error" else "提醒"
        lines.append(f"- **{label}**：{issue['message']}")
    lines.append("")
    lines.append("> 上述提示由命盘规则校验生成，需优先复核原报告对应段落。")
    return "\n".join(lines).strip()


YAML_RULE_MIN_SUPPORT = 3


def load_yaml_rules(path: Any | None) -> list[dict[str, Any]]:
    """Load corpus-derived BaZi rules from a YAML file.

    Filters out rules whose ``support`` is below ``YAML_RULE_MIN_SUPPORT`` so
    weak signals do not pollute report validation.
    """
    if path is None or _yaml is None:
        return []
    p = Path(path)
    if not p.exists():
        return []
    raw = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rules = raw.get("rules") or []
    out: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        try:
            support = int(rule.get("support") or 0)
        except (TypeError, ValueError):
            support = 0
        if support < YAML_RULE_MIN_SUPPORT:
            continue
        out.append(rule)
    return out


def _chart_matches_pattern(chart: dict, pattern: dict[str, Any]) -> bool:
    if not pattern:
        return False
    pillars = chart.get("four_pillars") or {}
    dm = chart.get("day_master") if isinstance(chart.get("day_master"), dict) else {}
    facts = {
        "day_master_gan": str(dm.get("gan") or (pillars.get("day") or {}).get("gan") or ""),
        "day_master_wuxing": str(dm.get("wuxing") or GAN_WUXING.get(str(dm.get("gan") or ""), "")),
        "month_zhi": str((pillars.get("month") or {}).get("zhi") or ""),
        "day_zhi": str((pillars.get("day") or {}).get("zhi") or ""),
        "year_zhi": str((pillars.get("year") or {}).get("zhi") or ""),
        "gender": str((chart.get("birth_info") or {}).get("gender") or ""),
    }
    for key, expected in pattern.items():
        actual = facts.get(key, "")
        if isinstance(expected, list):
            if actual not in expected:
                return False
        else:
            if actual != str(expected):
                return False
    return True


def validate_against_yaml_rules(
    chart: dict,
    report_text: str,
    rules: list[dict[str, Any]],
) -> list[dict[str, str]]:
    text = str(report_text or "")
    issues: list[dict[str, str]] = []
    for rule in rules or []:
        rule_id = str(rule.get("id") or "unnamed")
        pattern = rule.get("pattern") or {}
        forbidden = rule.get("forbidden_phrases") or []
        if not _chart_matches_pattern(chart, pattern):
            continue
        hits = [phrase for phrase in forbidden if phrase and phrase in text]
        if not hits:
            continue
        issues.append(
            _issue(
                f"yaml_rule:{rule_id}",
                str(rule.get("severity") or "warning"),
                str(rule.get("message") or f"corpus 规律 {rule_id} 命中违例：{','.join(hits)}"),
                "; ".join(hits),
            )
        )
    return issues
