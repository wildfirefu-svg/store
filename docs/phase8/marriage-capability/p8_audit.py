"""P8-2B 四源核对与缺口归类（Phase 8，零 API、审计只打快照）。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md v1.3.1（§P8-2B）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md v3.2（Task 5）

四源：KB 快照（kb_snapshot.db，只读）/ classic_texts（git object 冻结版）/ prompt 重建 / 计算探针。
gap_class 五类 + undetermined；primary_gap 仅从确定类派生，优先级
计算缺失 > 注入缺失 > 检索不可见 > 知识缺失 > 模型未利用。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8_DIR = REPO / "docs" / "phase8" / "marriage-capability"

GAP_CLASSES = ["知识缺失", "检索不可见", "计算缺失", "注入缺失", "模型未利用", "undetermined"]
PRIMARY_GAP_PRIORITY = ["计算缺失", "注入缺失", "检索不可见", "知识缺失", "模型未利用"]
EXPECTED_PROMPT_FINGERPRINT = "e136106a8e8730020eb3631b32b6c24424beaf73f5f0fcbc82a274e2120cb22d"


def _load(name: str, relpath: str):
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod  # dataclass 装饰器依赖 sys.modules 注册
    spec.loader.exec_module(mod)
    return mod


def resolve_profile(name: str):
    profiles = _load("p8_profiles", "benchmark/runners/profiles.py")
    return profiles.resolve_profile(name)


def prompt_fingerprint(profile) -> str:
    profiles = _load("p8_profiles", "benchmark/runners/profiles.py")
    return profiles.prompt_fingerprint(profile)


def rebuild_prompt(case: dict) -> str:
    mingli_prompt = _load("p8_mingli_prompt", "benchmark/formatters/mingli_prompt.py")
    return mingli_prompt.format_official_cot_prompt(case)


def _prompt_evidence(prompt: str) -> list[dict]:
    """prompt 现存字段证据（字段路径 + 逐字摘录）。"""
    evidence = []
    markers = [
        ("命主信息", "birth_info.raw"),
        ("八字命盘信息", "chart_input.official_astro.chinese_date"),
        ("时辰", "chart_input.official_astro.time"),
        ("五行局", "chart_input.official_astro.five_elements_class"),
        ("生肖", "chart_input.official_astro.zodiac"),
        ("紫微命盘信息", "chart_input.official_astro.palace_stars"),
        ("问题", "question"),
        ("选项", "options"),
    ]
    for marker, field_path in markers:
        if marker in prompt:
            idx = prompt.index(marker)
            excerpt = prompt[max(0, idx - 20): idx + len(marker) + 30].replace("\n", " ")
            evidence.append({"field_path": field_path, "excerpt": excerpt})
    return evidence


def _classify_computation(item: dict, probe_status: str, injected: bool) -> dict:
    """计算项归类（冻结映射）。"""
    if probe_status == "no_interface":
        return {"gap_class": "计算缺失", "undetermined_reason": None}
    if probe_status == "missing_input":
        return {"gap_class": "undetermined", "undetermined_reason": "input_missing"}
    if probe_status == "semantic_gap":
        return {"gap_class": "undetermined", "undetermined_reason": "semantic_gap"}
    # computable
    if not injected:
        return {"gap_class": "注入缺失", "undetermined_reason": None}
    return {"gap_class": "模型未利用", "undetermined_reason": None}


def _classify_doctrine(item: dict, kb_hits: int, classic_hits: int, prompt_has: bool) -> dict:
    """doctrine 项归类（KB/经典/prompt 三源核对）。"""
    if kb_hits > 0 or classic_hits > 0:
        if prompt_has:
            return {"gap_class": "模型未利用", "undetermined_reason": None}
        return {"gap_class": "检索不可见", "undetermined_reason": None}
    return {"gap_class": "知识缺失", "undetermined_reason": None}


def _kb_query(conn, entrypoint: str, args: dict) -> list[str]:
    """对 KB 快照执行单个入口查询，返回命中条文 ID 列表（只读）。"""
    if entrypoint == "search_gejue":
        rows = conn.execute(
            "SELECT id FROM gejue WHERE category=? AND (text LIKE ? OR keywords LIKE ?)",
            (args["category"], f"%{args['query']}%", f"%{args['query']}%"),
        ).fetchall()
    elif entrypoint == "search_shishen_combo":
        rows = conn.execute(
            "SELECT id FROM shishen_combos WHERE combo LIKE ?", (f"%{args['combo_name']}%",)
        ).fetchall()
    elif entrypoint == "search_shensha":
        rows = conn.execute(
            "SELECT id FROM shensha WHERE name LIKE ?", (f"%{args['name']}%",)
        ).fetchall()
    elif entrypoint == "search_nayin":
        rows = conn.execute(
            "SELECT id FROM nayin WHERE gan_zhi=?", (args["gan"] + args["zhi"],)
        ).fetchall()
    elif entrypoint == "search_bingyao":
        rows = conn.execute(
            "SELECT id FROM bingyao WHERE disease LIKE ? OR symptom LIKE ?",
            (f"%{args['query']}%", f"%{args['query']}%"),
        ).fetchall()
    elif entrypoint == "search_xiangyi":
        rows = conn.execute(
            "SELECT id FROM xiangyi WHERE gan_or_zhi LIKE ?", (f"%{args['gan_or_zhi']}%",)
        ).fetchall()
    else:
        rows = []
    return [str(r[0]) for r in rows]


def run_audit(rk_path: Path, probe_path: Path, cases160_path: Path, out_path: Path,
              summary_path: Path) -> dict:
    # prompt fingerprint 硬门
    profile = resolve_profile("mingli_official_cot_astro")
    fp = prompt_fingerprint(profile)
    if fp != EXPECTED_PROMPT_FINGERPRINT:
        sys.exit(f"prompt_fingerprint 不一致：{fp} != {EXPECTED_PROMPT_FINGERPRINT}")

    rk_rows = [json.loads(l) for l in rk_path.open(encoding="utf-8") if l.strip()]
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    status_by_id = {i["item_id"]: i["computability_status"] for i in probe["items"]}
    norm = {
        r["case_id"]: r
        for r in (json.loads(l) for l in cases160_path.open(encoding="utf-8") if l.strip())
    }

    # KB 快照检索（只读）
    import sqlite3
    snap = P8_DIR / "kb_snapshot.db"
    conn = sqlite3.connect(snap.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # classic_texts 冻结检索（逐项核查用，不落盘）
    classic_mod = _load(
        "classic_texts_search", "docs/phase8/marriage-capability/classic_texts_search.py"
    )
    freeze_path = P8_DIR / "classic_texts_freeze.json"

    audit_rows = []
    for row in rk_rows:
        cid = row["case_id"]
        case = norm[cid]
        prompt = rebuild_prompt(case)
        prompt_evidence = _prompt_evidence(prompt)
        items = []
        for item in row["items"]:
            if item["item_type"] == "computation":
                status = status_by_id[item["item_id"]]
                # 注入判定：prompt 是否含该计算结果。官方 prompt 只含 birth_info + astro 块
                # （chinese_date/time/五行局/生肖/十二宫星曜），无大运序列/流年映射/四化表
                # （设计 §3 已核实）→ computable 项一律未注入。
                injected = False
                cls = _classify_computation(item, status, injected)
            else:
                # doctrine：KB 快照检索（命中条文 ID 落盘）+ classic_texts 逐项冻结核查 + prompt 现存字段
                kb_hit_ids: list[str] = []
                for qs in item["query_specs"]:
                    kb_hit_ids.extend(_kb_query(conn, qs["entrypoint"], qs["args"]))
                kb_hits = len(kb_hit_ids)
                # 逐项 classic_texts 核查（用该项 query 词组，git object 冻结版）
                classic_groups = [[qs["args"].get("query") or qs["args"].get("name") or qs["args"].get("combo_name") or ""] for qs in item["query_specs"]]
                classic_groups = [g for g in classic_groups if g[0]]
                classic_result = classic_mod.search_frozen(classic_groups, freeze_path, None) if classic_groups else {"results": []}
                classic_hits = len(classic_result["results"])
                # prompt 现存字段：官方 prompt 只含 birth_info + astro 块，无婚姻规则/断语
                # （设计 §3 已核实：零婚姻规则、零大运流年序列、零四化表）→ doctrine 知识一律未注入。
                prompt_has = False
                cls = _classify_doctrine(item, kb_hits, classic_hits, prompt_has)
                evidence = {
                    "kb_hit_ids": sorted(set(kb_hit_ids)),
                    "classic_hits": classic_hits,
                    "not_found_by_frozen_search": kb_hits == 0,
                }
            record = {
                "item_id": item["item_id"],
                "item_type": item["item_type"],
                "gap_class": cls["gap_class"],
                "undetermined_reason": cls["undetermined_reason"],
            }
            if item["item_type"] == "doctrine":
                record["evidence"] = evidence
            items.append(record)
        determined = [i["gap_class"] for i in items if i["gap_class"] != "undetermined"]
        if not determined:
            primary_gap = "undetermined"
            primary_gap_reason = "题内知识项全为 undetermined"
        else:
            primary_gap = min(determined, key=PRIMARY_GAP_PRIORITY.index)
            primary_gap_reason = f"题内最高优先级缺口：{primary_gap}"
        audit_rows.append(
            {
                "case_id": cid,
                "items": items,
                "gap_classes": sorted({i["gap_class"] for i in items}),
                "primary_gap": primary_gap,
                "primary_gap_reason": primary_gap_reason,
                "prompt_evidence": prompt_evidence,
            }
        )
    conn.close()

    # 汇总（双口径：题级多标签 + 知识项级）
    gap_counts: dict[str, int] = {}
    for row in audit_rows:
        for item in row["items"]:
            gap_counts[item["gap_class"]] = gap_counts.get(item["gap_class"], 0) + 1
    case_counts: dict[str, int] = {}
    for row in audit_rows:
        case_counts[row["primary_gap"]] = case_counts.get(row["primary_gap"], 0) + 1
    n_items = sum(len(r["items"]) for r in audit_rows)
    classic_total = json.loads(
        (P8_DIR / "classic_texts_search_results.json").read_text(encoding="utf-8")
    )["summary"]["total_hits"]
    summary = {
        "schema_version": "1.0",
        "n_cases": len(audit_rows),
        "n_items": n_items,
        "gap_counts_item_level": gap_counts,
        "gap_counts_case_level_primary": case_counts,
        "denominator_check": sum(gap_counts.values()) == n_items,
        "classic_texts_hits_total": classic_total,
        "prompt_fingerprint": fp,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in audit_rows:
            f.write(
                json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
    lines = [
        "# knowledge_audit 汇总（P8-2B）",
        "",
        f"- 题数：{summary['n_cases']}；知识项总数：{summary['n_items']}",
        f"- 分母对账（知识项级）：{'通过' if summary['denominator_check'] else '失败'}",
        f"- prompt_fingerprint：`{summary['prompt_fingerprint']}`",
        "",
        "## 知识项级 gap 分布",
        "",
    ]
    for k, v in sorted(summary["gap_counts_item_level"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {k}：{v}")
    lines += ["", "## 题级 primary_gap 分布", ""]
    for k, v in sorted(summary["gap_counts_case_level_primary"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {k}：{v}")
    lines += [
        "",
        "## 口径说明",
        "",
        "- 五类与 undetermined 分列；题级多标签（gap_classes）+ 知识项级双口径汇总。",
        "- 计算项映射：no_interface→计算缺失；missing_input→undetermined(input_missing)；semantic_gap→undetermined；computable 且未注入→注入缺失；computable 且已注入→模型未利用。",
        "- doctrine 项：KB 快照/classic_texts 冻结版核查命中且 prompt 未注入→检索不可见；命中且已注入→模型未利用；双源零命中→知识缺失。",
        f"- classic_texts 冻结检索总命中：{summary['classic_texts_hits_total']}（quarantine 命中只作佐证）。",
    ]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    run_audit(
        P8_DIR / "required_knowledge.jsonl",
        P8_DIR / "computability_probe.json",
        REPO / "docs" / "phase7" / "phase7-mingli-v4flash-nt-20260811-r2" / "mingli_160.jsonl",
        P8_DIR / "knowledge_audit.jsonl",
        P8_DIR / "knowledge_audit_summary.md",
    )
    print(f"audit written to {P8_DIR}")


if __name__ == "__main__":
    main()
