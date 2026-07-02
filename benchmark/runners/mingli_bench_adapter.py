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
    if not isinstance(bazi, dict):
        return {}
    chart: Dict[str, Any] = {}
    for key in ("four_pillars", "day_master", "shishen_stats", "wuxing_stats", "branch_relations", "shensha", "wuyun_liuqi"):
        if key in bazi:
            chart[key] = bazi[key]
    return chart


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

    raw_data = _read_json(data_json_path)
    if not isinstance(raw_data, list):
        raise ValueError(f"MingLi-Bench data.json must be a JSON array, got {type(raw_data).__name__}")

    fortune_data: Dict[str, Any] = {}
    if fortune_api_json_path:
        loaded = _read_json(fortune_api_json_path)
        if isinstance(loaded, dict):
            fortune_data = loaded

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
        options = list(entry.get("options") or [])
        answer = entry.get("answer") or ""
        category = str(entry.get("category") or "")
        year_value = entry.get("year")
        year_normalised = str(year_value) if year_value is not None else ""

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
            chart = _extract_chart_input(fortune_data.get(case_id))
            if chart:
                row["chart_input"] = chart

        rows.append(row)

    return rows
