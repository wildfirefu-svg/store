from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


CATEGORY_TO_DOMAIN: Dict[str, str] = {
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


def _extract_chart_input(fortune_entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(fortune_entry, dict):
        return {}
    bazi = fortune_entry.get("bazi")
    if isinstance(bazi, dict):
        chart: Dict[str, Any] = {}
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


def _normalise_options(options: Any) -> List[str]:
    normalised: List[str] = []
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


def _infer_year(entry: Dict[str, Any]) -> str:
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


def _load_fortune_index(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    loaded = _read_json(path)
    if isinstance(loaded, dict):
        return {str(k): v for k, v in loaded.items()}
    if isinstance(loaded, list):
        indexed: Dict[str, Any] = {}
        for item in loaded:
            if isinstance(item, dict) and item.get("case_id"):
                indexed[str(item["case_id"])] = item
        return indexed
    return {}


def load_and_normalize(
    data_json_path: str,
    fortune_api_json_path: Optional[str] = None,
    include_astro: bool = False,
    year_filter: Optional[str] = None,
    category_filter: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
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

    year_str: Optional[str] = None
    if year_filter is not None:
        year_str = str(year_filter)

    category_set: Optional[set] = None
    if category_filter is not None:
        category_set = {str(c) for c in category_filter}

    rows: List[Dict[str, Any]] = []
    for entry in raw_data:
        if not isinstance(entry, dict):
            continue
        case_id = entry.get("case_id")
        if not case_id:
            continue
        # Guard against case_id collisions with the baziqa dataset by
        # prepending a namespace prefix. Fixtures / already-namespaced ids
        # pass through unchanged.
        case_id = str(case_id)
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

        row: Dict[str, Any] = {
            "case_id": case_id,
            "question": question,
            "options": options,
            "answer": answer,
            "domain": domain,
            "year": year_normalised,
            "category": category,
        }

        if include_astro:
            original_case_id = str(entry.get("case_id") or "")
            chart = _extract_chart_input(fortune_data.get(case_id) or fortune_data.get(original_case_id))
            if chart:
                row["chart_input"] = chart

        rows.append(row)

    return rows
