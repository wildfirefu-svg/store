"""Extract structured + textual features from a BaZi chart for retrieval and prompts."""

from __future__ import annotations

from typing import Any

GAN_WUXING = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

ZHI_MAIN_GAN = {
    "子": "癸", "丑": "己", "寅": "甲", "卯": "乙",
    "辰": "戊", "巳": "丙", "午": "丁", "未": "己",
    "申": "庚", "酉": "辛", "戌": "戊", "亥": "壬",
}


DOMAIN_CN = {
    "career": "事业",
    "wealth": "财运",
    "relationship": "感情",
    "health": "健康",
    "family": "家庭",
    "annual_fortune": "流年",
    "study": "学业",
    "personality": "性格",
    "unknown": "综合",
}


def _safe(d: Any, *keys, default=""):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def _decade(year):
    try:
        y = int(year)
        return (y // 10) * 10
    except (TypeError, ValueError):
        return None


def extract(chart: dict) -> dict[str, Any]:
    pillars = chart.get("four_pillars") or {}
    dm = chart.get("day_master") if isinstance(chart.get("day_master"), dict) else {}
    birth = chart.get("birth_info") or {}

    day_gan = _safe(dm, "gan") or _safe(pillars, "day", "gan")
    day_wuxing = _safe(dm, "wuxing") or GAN_WUXING.get(day_gan, "")

    branches = [
        str(_safe(pillars, "year", "zhi")),
        str(_safe(pillars, "month", "zhi")),
        str(_safe(pillars, "day", "zhi")),
        str(_safe(pillars, "hour", "zhi")),
    ]
    branches = [b for b in branches if b]
    query_domain = str(chart.get("query_domain") or "unknown")
    query_text = str(chart.get("query_text") or "")

    structured = {
        "day_master_gan": str(day_gan or ""),
        "day_master_wuxing": str(day_wuxing or ""),
        "year_gan": str(_safe(pillars, "year", "gan")),
        "year_zhi": str(_safe(pillars, "year", "zhi")),
        "month_gan": str(_safe(pillars, "month", "gan")),
        "month_zhi": str(_safe(pillars, "month", "zhi")),
        "day_zhi": str(_safe(pillars, "day", "zhi")),
        "hour_gan": str(_safe(pillars, "hour", "gan")),
        "hour_zhi": str(_safe(pillars, "hour", "zhi")),
        "gender": str(birth.get("gender") or ""),
        "birth_year": birth.get("year"),
        "birth_decade": _decade(birth.get("year")),
        "month_main_qi": ZHI_MAIN_GAN.get(str(_safe(pillars, "month", "zhi")), ""),
        "branches": branches,
        "query_domain": query_domain,
        "query_text": query_text,
        "wuxing_stats": chart.get("wuxing_stats") or {},
        "shishen_stats": chart.get("shishen_stats") or {},
    }

    parts = []
    if structured["day_master_gan"]:
        parts.append(f"日主{structured['day_master_gan']}{structured['day_master_wuxing']}")
    if structured["month_zhi"]:
        parts.append(f"生于{structured['month_zhi']}月（本气{structured['month_main_qi']}）")
    if structured["year_zhi"]:
        parts.append(f"年柱{structured['year_gan']}{structured['year_zhi']}")
    if structured["day_zhi"]:
        parts.append(f"日支{structured['day_zhi']}")
    if structured["hour_zhi"]:
        parts.append(f"时柱{structured['hour_gan']}{structured['hour_zhi']}")
    if structured["gender"]:
        parts.append(f"性别{structured['gender']}")
    if structured["birth_decade"] is not None:
        parts.append(f"生于{structured['birth_decade']}年代")
    if query_domain:
        parts.append(f"问题领域{DOMAIN_CN.get(query_domain, query_domain)}")
    if query_text:
        parts.append(f"题目选项{query_text[:240]}")
    if branches:
        parts.append("地支" + "".join(branches))
    text_blob = "，".join(p for p in parts if p)
    if len(text_blob) > 600:
        text_blob = text_blob[:600]

    return {"text_blob": text_blob, "structured": structured}
