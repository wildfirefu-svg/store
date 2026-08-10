from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

CATEGORY_TO_DOMAIN: dict[str, str] = {
    "事业": "career",
    "官非": "career",
    "健康": "health",
    "婚姻": "relationship",
    "感情": "relationship",
    "子女": "family",
    "家庭": "family",
    "六亲": "family",
    "财运": "wealth",
    "学业": "study",
    "运势": "annual_fortune",
    "外貌": "unknown",
    "性格": "unknown",
    "灾劫": "unknown",
}


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _extract_chart_input(fortune_entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fortune_entry, dict):
        return {}
    bazi = fortune_entry.get("bazi")
    if isinstance(bazi, dict):
        chart: dict[str, Any] = {}
        for key in ("four_pillars", "day_master", "shishen_stats", "wuxing_stats", "branch_relations", "shensha", "wuyun_liuqi"):
            if key in bazi:
                chart[key] = bazi[key]
        return chart

    api_data = (((fortune_entry.get("api_response") or {}).get("data") or {}).get("data") or {})
    if isinstance(api_data, dict):
        chart = {}
        for key in ("chineseDate", "rawDates", "time", "timeRange", "sign", "zodiac", "fiveElementsClass", "palaces"):
            if key in api_data:
                chart[key] = api_data[key]
        return chart
    return {}


_CANONICAL_BAZI_KEYS = (
    "four_pillars", "day_master", "shishen_stats",
    "wuxing_stats", "branch_relations", "shensha",
)


def to_canonical_chart_input(fortune_entry: dict[str, Any] | None) -> dict[str, Any]:
    """mingli fortune 条目 → approved_v1 可渲染 canonical chart_input（Task 5 修订定稿）。

    bazi 形状：透传批准核心六字段（丢弃 wuyun_liuqi 等非批准键）。
    API 形状：ziwei（已核验真实键映射，供 approved_v1 渲染）+ official_astro
    （官方模板注入所需字段）。缺失字段不虚构（fail-closed），
    由可见性矩阵与覆盖率报告如实呈现。
    """
    if not isinstance(fortune_entry, dict):
        return {}
    bazi = fortune_entry.get("bazi")
    if isinstance(bazi, dict):
        return {k: bazi[k] for k in _CANONICAL_BAZI_KEYS if k in bazi}
    api_data = (((fortune_entry.get("api_response") or {}).get("data") or {}).get("data") or {})
    if isinstance(api_data, dict) and api_data:
        canonical: dict[str, Any] = {}
        palaces = api_data.get("palaces")
        if isinstance(palaces, list) and palaces:
            canonical["ziwei"] = {
                "basic_info": _canon_ziwei_basic_info(api_data, palaces),
                "twelve_palaces": [_canon_palace(p) for p in palaces],
            }
        canonical["official_astro"] = _canon_official_astro(api_data)
        return canonical
    return {}


def _canon_ziwei_basic_info(api_data: dict[str, Any], palaces: list) -> dict[str, Any]:
    """定稿映射（真实数据核验）：soul→命主、body→身主、fiveElementsClass→五行局、
    earthlyBranchOfBodyPalace→身宫；命宫干支取 name=="命宫" 宫的
    heavenlyStem+earthlyBranch（api 顶层只有 earthlyBranchOfSoulPalace 作回退）。"""
    ming = next(
        (p for p in palaces if isinstance(p, dict) and p.get("name") == "命宫"), {}
    )
    ming_gz = f"{ming.get('heavenlyStem') or ''}{ming.get('earthlyBranch') or ''}"
    return {
        "ming_gong_gan_zhi": ming_gz or str(api_data.get("earthlyBranchOfSoulPalace") or ""),
        "shen_gong_position": str(api_data.get("earthlyBranchOfBodyPalace") or ""),
        "wu_xing_ju": str(api_data.get("fiveElementsClass") or ""),
        "ming_zhu": str(api_data.get("soul") or ""),
        "shen_zhu": str(api_data.get("body") or ""),
    }


def _canon_star(star: Any) -> dict[str, str]:
    """星曜保留 name+brightness（用户裁决确认）。"""
    s = star if isinstance(star, dict) else {}
    return {"name": str(s.get("name") or ""), "brightness": str(s.get("brightness") or "")}


def _canon_palace(palace: Any) -> dict[str, Any]:
    """定稿真实键映射（勘察核验）：name/heavenlyStem/earthlyBranch/majorStars/
    minorStars+adjectiveStars/decadal.range/isBodyPalace；禁止兼容猜测键名。"""
    p = palace if isinstance(palace, dict) else {}
    decadal = p.get("decadal") or {}
    rng = decadal.get("range") if isinstance(decadal, dict) else None
    daxian = f"{rng[0]}-{rng[1]}" if isinstance(rng, list) and len(rng) == 2 else ""
    return {
        "name": str(p.get("name") or ""),
        "position": str(p.get("earthlyBranch") or ""),
        "tian_gan": str(p.get("heavenlyStem") or ""),
        "main_stars": [_canon_star(s) for s in (p.get("majorStars") or [])],
        "auxiliary_stars": (
            [_canon_star(s) for s in (p.get("minorStars") or [])]
            + [_canon_star(s) for s in (p.get("adjectiveStars") or [])]
        ),
        "daxian": daxian,
        "is_shengong": bool(p.get("isBodyPalace")),
    }


def _canon_official_astro(api_data: dict[str, Any]) -> dict[str, Any]:
    """官方模板注入字段（1:1 官方行为）：palace_stars 仅 major+minor 星名、
    空格连接、仅收录有星宫位；宫序由 formatter 按官方固定顺序输出。"""
    palace_stars: dict[str, str] = {}
    for p in api_data.get("palaces") or []:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not name:
            continue
        stars = [
            str(s.get("name") or "")
            for s in (p.get("majorStars") or [])
            if isinstance(s, dict)
        ]
        stars += [
            str(s.get("name") or "")
            for s in (p.get("minorStars") or [])
            if isinstance(s, dict)
        ]
        stars = [s for s in stars if s]
        if stars:
            palace_stars[str(name)] = " ".join(stars)
    return {
        "chinese_date": str(api_data.get("chineseDate") or ""),
        "time": str(api_data.get("time") or ""),
        "five_elements_class": str(api_data.get("fiveElementsClass") or ""),
        "zodiac": str(api_data.get("zodiac") or ""),
        "palace_stars": palace_stars,
    }


def _normalise_options(options: Any) -> list[str]:
    normalised: list[str] = []
    if not isinstance(options, list):
        return normalised
    for idx, option in enumerate(options):
        if isinstance(option, str):
            normalised.append(option)
            continue
        if isinstance(option, dict):
            letter = str(option.get("letter") or chr(ord("A") + idx))
            text = str(option.get("text") or "")
            normalised.append(f"{letter}. {text}".strip())
    return normalised


def _infer_year(entry: dict[str, Any]) -> str:
    for key in ("year", "benchmark_year", "source_year"):
        value = entry.get(key)
        if value is not None:
            return str(value)
    question_number = entry.get("question_number")
    try:
        number = int(question_number)
    except (TypeError, ValueError):
        return ""
    if number < 1:
        return ""
    return str(2022 + ((number - 1) // 40))


def _load_fortune_index(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    loaded = _read_json(path)
    if isinstance(loaded, dict):
        return {str(k): v for k, v in loaded.items()}
    if isinstance(loaded, list):
        indexed: dict[str, Any] = {}
        for item in loaded:
            if isinstance(item, dict) and item.get("case_id"):
                indexed[str(item["case_id"])] = item
        return indexed
    return {}


def load_and_normalize(
    data_json_path: str,
    fortune_api_json_path: str | None = None,
    include_astro: bool = False,
    year_filter: str | None = None,
    category_filter: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    if include_astro and not fortune_api_json_path:
        raise ValueError(
            "load_and_normalize: include_astro=True requires fortune_api_json_path"
        )

    loaded_data = _read_json(data_json_path)
    if isinstance(loaded_data, list):
        raw_data = loaded_data
    elif isinstance(loaded_data, dict) and isinstance(loaded_data.get("questions"), list):
        raw_data = loaded_data["questions"]
    else:
        raise ValueError(f"MingLi-Bench data.json must be a JSON array or object with questions array, got {type(loaded_data).__name__}")

    fortune_data = _load_fortune_index(fortune_api_json_path)

    year_str: str | None = None
    if year_filter is not None:
        year_str = str(year_filter)

    category_set: set | None = None
    if category_filter is not None:
        category_set = {str(c) for c in category_filter}

    rows: list[dict[str, Any]] = []
    for entry in raw_data:
        if not isinstance(entry, dict):
            continue
        case_id = entry.get("case_id")
        if not case_id:
            continue
        chart_case_id = str(case_id)
        # Guard against case_id collisions with the baziqa dataset by
        # prepending a namespace prefix. Fixtures / already-namespaced ids
        # pass through unchanged. Official entries carry a unique question
        # id (ftb_NNNN); it takes precedence over the chart-level case_id
        # (case_N), which is shared by multiple questions on the same chart.
        qid = str(entry.get("id") or "")
        if qid:
            case_id = qid if qid.startswith("mingli_") else f"mingli_{qid}"
        else:
            case_id = chart_case_id
            if not case_id.startswith("mingli_"):
                case_id = f"mingli_{case_id}"
        question = entry.get("question") or ""
        options = _normalise_options(entry.get("options"))
        answer = entry.get("answer") or ""
        category = str(entry.get("category") or "")
        year_normalised = _infer_year(entry)

        if year_str is not None and year_normalised != year_str:
            continue
        if category_set is not None and category not in category_set:
            continue

        domain = CATEGORY_TO_DOMAIN.get(category, "unknown")

        row: dict[str, Any] = {
            "case_id": case_id,
            "chart_case_id": chart_case_id,
            "question": question,
            "options": options,
            "answer": answer,
            "domain": domain,
            "year": year_normalised,
            "category": category,
        }

        if include_astro:
            # fortune join 用命盘键（原始 case_N）；保留对命名空间键的兜底查找，
            # 既有夹具（tests/fixtures/mingli/fortune_api_results_sample.json）
            # 以 mingli_ 前缀键索引，依赖该兜底。
            chart = to_canonical_chart_input(
                fortune_data.get(chart_case_id) or fortune_data.get(case_id)
            )
            if chart:
                row["chart_input"] = chart

        birth_info = entry.get("birth_info")
        if isinstance(birth_info, dict) and birth_info:
            row["birth_info"] = birth_info

        rows.append(row)

    return rows
