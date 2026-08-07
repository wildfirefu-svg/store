# -*- coding: utf-8 -*-
"""Bazi time-context relation computation.

Migrated from benchmark.formatters.two_stage_reasoning to centralize
Earthly-Branch / Heavenly-Stem relation logic and stream-year (流年) computation.
"""

from __future__ import annotations

import re

from bazi_calculator import get_shishen, sexagenary_by_index

# Time/location keywords for identifying time-location questions
_TIME_KEYWORDS = [
    "哪年", "何时", "什么时候", "时间", "年份", "何年", "哪一年",
    "几年", "几时", "何時", "那年", "多久", "大运", "流年",
    "岁运", "年运", "年份",
]

# Wuxing generation cycle for computing gan relations
_WUXING_CYCLE = {
    "金": {"生": "水", "克": "木", "被生": "土", "被克": "火"},
    "木": {"生": "火", "克": "土", "被生": "水", "被克": "金"},
    "水": {"生": "木", "克": "火", "被生": "金", "被克": "土"},
    "火": {"生": "土", "克": "金", "被生": "木", "被克": "水"},
    "土": {"生": "金", "克": "水", "被生": "火", "被克": "木"},
}

# Gan to wuxing mapping
_GAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# Key shensha names relevant to common life events (shared with dayun evidence)
_KEY_SHENSHA = [
    "桃花", "红鸾", "天喜", "丧门", "白虎", "驿马", "华盖", "天乙贵人",
    "文昌贵人", "将星", "魁罡", "十恶大败", "阴差阳错", "孤鸾煞", "红艳煞",
]


def compute_branch_relation(zhi1: str, zhi2: str) -> list[str]:
    """Compute branch relations between two zhi (地支).

    Returns list of relation descriptions (六冲/六合/三合/六害/三刑).
    """
    relations = []
    # 六冲
    chong = {
        ("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"),
        ("辰", "戌"), ("巳", "亥"),
    }
    # 六合
    liuhe = {
        ("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"),
        ("巳", "申"), ("午", "未"),
    }
    # 三合 (partial match - any two of the three)
    sanhe = [
        {"申", "子", "辰"}, {"寅", "午", "戌"}, {"巳", "酉", "丑"}, {"亥", "卯", "未"},
    ]
    # 六害
    liuhai = {
        ("子", "未"), ("丑", "午"), ("寅", "巳"), ("卯", "辰"),
        ("申", "亥"), ("酉", "戌"),
    }
    # 三刑
    sanxing = [
        {"寅", "巳", "申"}, {"丑", "戌", "未"},
    ]

    pair = (zhi1, zhi2)
    pair_rev = (zhi2, zhi1)

    if pair in chong or pair_rev in chong:
        relations.append("冲")
    if pair in liuhe or pair_rev in liuhe:
        relations.append("合")
    if pair in liuhai or pair_rev in liuhai:
        relations.append("害")
    for group in sanhe:
        if zhi1 in group and zhi2 in group:
            relations.append("三合")
            break
    for group in sanxing:
        if zhi1 in group and zhi2 in group:
            relations.append("刑")
            break

    return relations


def compute_gan_relation(gan1: str, gan2: str) -> str:
    """Compute relation between two gan (天干) based on wuxing.

    Returns a description like '生', '克', '被生', '被克', '同'.
    """
    wx1 = _GAN_WUXING.get(gan1, "")
    wx2 = _GAN_WUXING.get(gan2, "")
    if not wx1 or not wx2:
        return ""
    if wx1 == wx2:
        return "同"
    cycle = _WUXING_CYCLE.get(wx1, {})
    if cycle.get("生") == wx2:
        return f"{gan1}生{gan2}"
    if cycle.get("克") == wx2:
        return f"{gan1}克{gan2}"
    if cycle.get("被生") == wx2:
        return f"{gan2}生{gan1}"
    if cycle.get("被克") == wx2:
        return f"{gan2}克{gan1}"
    return ""


def compute_shishen_combo(dy_shishen: str, ln_shishen: str) -> str:
    """Compute combination-effect hint between dayun and liunian shishen.

    Returns a hint string like '，组合效应：伤官见官' or empty string if no match.
    """
    combo = f"{dy_shishen}+{ln_shishen}"
    if "伤官" in combo and "正官" in combo:
        return "，组合效应：伤官见官"
    if "七杀" in combo and "食神" in combo:
        return "，组合效应：食神制杀"
    if "偏财" in combo and "正印" in combo:
        return "，组合效应：财坏印"
    if "劫财" in combo and "正财" in combo:
        return "，组合效应：劫财夺财"
    if "正官" in combo and "七杀" in combo:
        return "，组合效应：官杀混杂"
    if "正印" in combo and "正财" in combo:
        return "，组合效应：财坏印"
    if "偏印" in combo and "食神" in combo:
        return "，组合效应：枭神夺食"
    return ""


def calculate_liunian_for_year(target_year: int, day_master_gan: str) -> dict:
    """Compute the liunian (流年) pillar for a target year via the 60-jiazi cycle.

    Uses idx = (target_year - 4) % 60 to locate the sexagenary pillar, then
    derives the ten-god (十神) relative to the day master.

    Returns dict with keys: year, gan, zhi, shi_shen.
    Raises ValueError if target_year is outside [1900, 2100].
    """
    if not 1900 <= target_year <= 2100:
        raise ValueError(
            f"target_year {target_year} out of range [1900, 2100]"
        )
    idx = (target_year - 4) % 60
    gan, zhi = sexagenary_by_index(idx)
    shi_shen = get_shishen(day_master_gan, gan)
    return {
        "year": target_year,
        "gan": gan,
        "zhi": zhi,
        "shi_shen": shi_shen,
    }


# Option prefix pattern (e.g. "A. ", "B. ")
_OPTION_PREFIX = re.compile(r"^[A-D]\.\s*")

# Keywords that mark dayun/liunian routing questions (R4)
_DAYUN_KEYWORDS = ("大运", "流年", "岁运", "年运")

# When-keywords used by R5
_WHEN_KEYWORDS = ("何时", "哪年", "几年后", "几年")


def detect_temporal_rules(question: str, options: list[str]) -> frozenset[str]:
    """Detect temporal/routing rules in a BaziQA question and its options.

    Returns a frozenset of matched rule names (R1..R7). Each rule is an
    independent signal; multiple rules may fire for the same question.
    """
    matched: set[str] = set()

    stripped = [_OPTION_PREFIX.sub("", o) for o in options]

    # R1: question contains any time keyword
    if any(kw in question for kw in _TIME_KEYWORDS):
        matched.add("R1")

    # R2: all options (>=2) are bare 4-digit years
    if len(stripped) >= 2 and all(re.match(r"^\d{4}$", s) for s in stripped):
        matched.add("R2")

    # R3: any option contains a numeric range AND "岁"
    if any(re.search(r"\d+[-–]\d+", s) and "岁" in s for s in stripped):
        matched.add("R3")

    # R4: question contains dayun/liunian routing keywords
    if any(kw in question for kw in _DAYUN_KEYWORDS):
        matched.add("R4")

    # R5: question contains a when-keyword AND any option has a 4-digit year
    if any(kw in question for kw in _WHEN_KEYWORDS) and any(
        re.search(r"\d{4}", s) for s in stripped
    ):
        matched.add("R5")

    # R6: question body contains a standalone 4-digit year in [1900, 2100]
    for m in re.finditer(r"(?<!\d)\d{4}(?!\d)", question):
        year = int(m.group())
        if 1900 <= year <= 2100:
            matched.add("R6")
            break

    # R7: any option is a bare age (with optional 岁) in [1, 120]
    for s in stripped:
        m = re.match(r"^(\d+)岁?$", s)
        if m and 1 <= int(m.group(1)) <= 120:
            matched.add("R7")
            break

    return frozenset(matched)
