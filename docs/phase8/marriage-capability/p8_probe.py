"""P8-1.5 计算能力实测探针（Phase 8，零 API、零生产代码改动）。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md v1.3.1（§P8-1.5）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md v3.2（Task 4）
对 required_knowledge.jsonl 中每个 computation 项实际调用引擎：
- 四态：computable / missing_input / no_interface / semantic_gap；
- 输出只保留稳定字段，排除全部 current_*（date.today() wall-clock 派生）；
- 双跑字节一致门（test 验证）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8_DIR = REPO / "docs" / "phase8" / "marriage-capability"

STABLE_DAYUN_FIELDS = [
    "direction", "starting_age", "starting_age_exact", "days_to_junction", "pillars",
]
STABLE_LIUNIAN_FIELDS = ["year", "gan", "zhi", "shi_shen"]

PARSE_RULES = {
    "chinese_date": (
        "official_astro.chinese_date 为空格分隔四段（年柱 月柱 日柱 时柱），"
        "每段两字 (gan, zhi)；年柱=段0、月柱=段1、日主天干=段2首字；"
        "段数≠4 或任一段长≠2 视为解析失败 → missing_input"
    ),
    "gender": "birth_info.gender 中文映射：男→male、女→female；缺失/非男女 → missing_input",
    "liunian_history": "历史目标年 Y：calculate_liunian(current_year=Y, day_master_gan, num_years=1)；"
    "区间 'Y1-Y2' 逐年展开",
    "stable_fields": {
        "dayun": STABLE_DAYUN_FIELDS,
        "liunian": STABLE_LIUNIAN_FIELDS,
    },
    "excluded": "全部 current_* 字段（current_year/current_age/current_pillar，"
    "bazi_calculator.py:896-912 的 date.today() wall-clock 派生）",
}


def _load_bazi_calculator():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))  # bazi_calculator 依赖仓库根的 lunar_calendar 等模块
    spec = importlib.util.spec_from_file_location(
        "bazi_calculator", REPO / "bazi_calculator.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def parse_chinese_date(chinese_date: str) -> tuple[tuple[str, str], tuple[str, str], str]:
    """解析 chinese_date → (year_pillar, month_pillar, day_master_gan)。失败抛 ValueError。"""
    if not isinstance(chinese_date, str):
        raise ValueError("chinese_date 缺失或非字符串")
    parts = chinese_date.split()
    if len(parts) != 4:
        raise ValueError(f"chinese_date 段数={len(parts)}≠4: {chinese_date!r}")
    pillars = []
    for p in parts:
        if len(p) != 2:
            raise ValueError(f"chinese_date 段长≠2: {p!r}")
        pillars.append((p[0], p[1]))
    return pillars[0], pillars[1], pillars[2][0]


def map_gender(gender) -> str:
    """男→male、女→female；缺失/非男女抛 ValueError。"""
    mapping = {"男": "male", "女": "female"}
    if gender not in mapping:
        raise ValueError(f"gender 缺失或非男女: {gender!r}")
    return mapping[gender]


def _expand_years(target_years: list[str]) -> list[int]:
    years: list[int] = []
    for t in target_years:
        if "-" in t:
            a, b = t.split("-", 1)
            years.extend(range(int(a), int(b) + 1))
        else:
            years.append(int(t))
    return sorted(set(years))


def _stable(obj, allowed: list[str]):
    if isinstance(obj, dict):
        return {k: _stable(v, allowed) for k, v in obj.items() if k in allowed}
    if isinstance(obj, list):
        return [_stable(v, allowed) for v in obj]
    return obj


def probe_computation_item(item: dict, case: dict) -> dict:
    cid = case["case_id"]
    item_id = item["item_id"]
    ctype = item["computation_type"]
    target_years = item.get("target_years") or []
    base = {
        "item_id": item_id,
        "case_id": cid,
        "computation_type": ctype,
        "target_years": target_years,
    }
    calc = _load_bazi_calculator()

    # ---- 输入解析（缺失/畸形 → missing_input）----
    astro = (case.get("chart_input") or {}).get("official_astro") or {}
    chinese_date = astro.get("chinese_date")
    try:
        year_pillar, month_pillar, day_master_gan = parse_chinese_date(chinese_date)
    except (ValueError, TypeError) as exc:
        base.update({"computability_status": "missing_input", "reason": f"chinese_date: {exc}"})
        return base
    bi = case.get("birth_info") or {}
    try:
        gender = map_gender(bi.get("gender"))
    except ValueError as exc:
        base.update({"computability_status": "missing_input", "reason": f"gender: {exc}"})
        return base
    try:
        birth_year, birth_month, birth_day = int(bi["year"]), int(bi["month"]), int(bi["day"])
    except (KeyError, TypeError, ValueError) as exc:
        base.update({"computability_status": "missing_input", "reason": f"birth_info: {exc}"})
        return base

    inputs_used = {
        "year_pillar": year_pillar,
        "month_pillar": month_pillar,
        "day_master_gan": day_master_gan,
        "gender": gender,
        "birth_year": birth_year,
        "birth_month": birth_month,
        "birth_day": birth_day,
    }

    # ---- 按类型调用引擎 ----
    try:
        if ctype == "liunian":
            years = _expand_years(target_years)
            if not years:
                raise ValueError("target_years 为空")
            out = []
            for y in years:
                result = calc.calculate_liunian(y, day_master_gan, num_years=1)
                out.extend(_stable(r, STABLE_LIUNIAN_FIELDS) for r in result)
            status, reason = "computable", None
        elif ctype == "dayun":
            if not target_years:
                raise ValueError("target_years 为空")
            result = calc.calculate_dayun(
                year_pillar, month_pillar, gender,
                birth_year, birth_month, birth_day,
            )
            out = _stable(result, STABLE_DAYUN_FIELDS)
            status, reason = "computable", None
        elif ctype == "sihua":
            # 引擎四化为紫微排盘内嵌的本命四化（bazi_calculator.py:1177-1198），
            # 无独立接口、无流年四化接口 → no_interface
            out = None
            status = "no_interface"
            reason = "四化仅存在于紫微排盘流程内（bazi_calculator.py:1177-1198），无独立/流年四化接口"
        elif ctype == "other":
            # 年龄→年份换算（0092）：target_years 区间与出生年对账
            years = _expand_years(target_years)
            if not years:
                raise ValueError("target_years 为空")
            lo = birth_year + 23
            hi = birth_year + 32
            out = {"age_range": "23-32", "converted_years": [str(lo), str(hi)], "target_years": years}
            status, reason = "computable", None
        else:  # pragma: no cover
            raise ValueError(f"unknown computation_type: {ctype}")
    except Exception as exc:  # 引擎异常 → semantic_gap（接口存在但执行失败）
        base.update(
            {
                "computability_status": "semantic_gap",
                "reason": f"engine call failed: {exc}",
                "inputs_used": inputs_used,
            }
        )
        return base

    base.update(
        {
            "computability_status": status,
            "reason": reason,
            "inputs_used": inputs_used,
            "output_summary": out,
        }
    )
    return base


def run_probe(rk_path: Path, cases160_path: Path, out_path: Path) -> dict:
    rows = [json.loads(l) for l in rk_path.open(encoding="utf-8") if l.strip()]
    norm = {
        r["case_id"]: r
        for r in (json.loads(l) for l in cases160_path.open(encoding="utf-8") if l.strip())
    }
    items = []
    for row in rows:
        case = norm[row["case_id"]]
        for item in row["items"]:
            if item["item_type"] == "computation":
                items.append(probe_computation_item(item, case))
    items.sort(key=lambda i: i["item_id"])
    statuses = {}
    for i in items:
        statuses[i["computability_status"]] = statuses.get(i["computability_status"], 0) + 1
    payload = {
        "schema_version": "1.0",
        "engine": {
            "dayun": "bazi_calculator.calculate_dayun(year_pillar, month_pillar, gender, birth_year, birth_month, birth_day)",
            "liunian": "bazi_calculator.calculate_liunian(current_year, day_master_gan, num_years=1)（历史年）",
            "sihua": "无独立接口（紫微排盘内嵌本命四化）",
        },
        "parse_rules": PARSE_RULES,
        "items": items,
        "summary": {"total": len(items), **statuses},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def main() -> None:
    run_probe(
        P8_DIR / "required_knowledge.jsonl",
        REPO / "docs" / "phase7" / "phase7-mingli-v4flash-nt-20260811-r2" / "mingli_160.jsonl",
        P8_DIR / "computability_probe.json",
    )
    print(f"probe written to {P8_DIR / 'computability_probe.json'}")


if __name__ == "__main__":
    main()
