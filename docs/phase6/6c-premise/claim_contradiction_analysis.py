"""Phase 6 6C premise quantification: rule-detectable factual contradictions
in the best single-pipeline baseline (B1-a') wrong answers vs correct answers.

Zero-API offline analysis. Reads merged_details.jsonl + holdout datasets,
extracts factual claims from raw_answer via regex, verifies against engine
facts (chart_input four_pillars + project relation tables).

Usage:
    .venv/Scripts/python .tmp/claim_contradiction_analysis.py [--limit N] [--verbose]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

# Archived at docs/phase6/6c-premise/ — repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from bazi_calculator import get_shishen  # noqa: E402
from bazi_report_validator import GAN_WUXING, ZHI_MAIN_GAN  # noqa: E402
from benchmark.formatters.bazi_time_context import compute_branch_relation  # noqa: E402

MERGED = REPO_ROOT / (
    "docs/phase6/6b2/"
    "phase6-6b2-v4flash-nt-20260805-r2-6b2-dev-2026-07-17-deepseek-deepseek-v4-flash-642ba3da19d5/"
    "merged_details.jsonl"
)
DATASETS = [
    REPO_ROOT / "benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl",
    REPO_ROOT / "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl",
]

GANS = "甲乙丙丁戊己庚辛壬癸"
ZHIS = "子丑寅卯辰巳午未申酉戌亥"
WUXING = "木火土金水"
SHISHEN = "正财|偏财|正官|七杀|正印|偏印|食神|伤官|比肩|劫财"

ZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 天干五合
GAN_WUHE = {("甲", "己"), ("乙", "庚"), ("丙", "辛"), ("丁", "壬"), ("戊", "癸")}

GAN_KE = {  # gan1 克 gan2
    ("甲", "戊"), ("甲", "己"), ("乙", "戊"), ("乙", "己"),
    ("丙", "庚"), ("丙", "辛"), ("丁", "庚"), ("丁", "辛"),
    ("戊", "壬"), ("戊", "癸"), ("己", "壬"), ("己", "癸"),
    ("庚", "甲"), ("庚", "乙"), ("辛", "甲"), ("辛", "乙"),
    ("壬", "丙"), ("壬", "丁"), ("癸", "丙"), ("癸", "丁"),
}


def load_cases() -> dict:
    cases = {}
    for path in DATASETS:
        with open(path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                cases[r["case_id"]] = r
    return cases


def extract_claims(text: str) -> list[dict]:
    """Extract factual claims. Each claim: {type, subject(s), claim, span, snippet}."""
    claims = []

    def add(ctype, subj, claim, start, snippet):
        claims.append({
            "type": ctype, "subject": subj, "claim": claim,
            "pos": start, "snippet": snippet,
        })

    # ---- Type A: 十神断言 (stem subject) ----
    # 否定前瞻: 排除"戌为食神之库"(库断言)/"X为Y所生之木"(生克描述)等非归属表述
    _SS_TAIL = r"(?![星过强弱旺衰透藏之])"
    # A1: 壬水为正财 / 甲木为正官 / 甲木是日主的正官
    for m in re.finditer(
        rf"([{GANS}])(?:[{WUXING}])?(?:为|是)(?:日主|命主)?的?({SHISHEN}){_SS_TAIL}",
        text,
    ):
        add("shishen_gan", m.group(1), m.group(2), m.start(), m.group(0))
    # A2: 伤官（庚金）/ 财星（壬水）
    for m in re.finditer(
        rf"({SHISHEN})(?:星)?[（(]([{GANS}])(?:[{WUXING}])?[）)]", text
    ):
        add("shishen_gan", m.group(2), m.group(1), m.start(), m.group(0))
    # A3: 正财为壬水 / 正官是甲木 (reversed); 排除"食神为壬水所生之木"类
    for m in re.finditer(
        rf"({SHISHEN})(?:星)?(?:为|是)([{GANS}])(?:[{WUXING}])?(?!所)", text
    ):
        add("shishen_gan", m.group(2), m.group(1), m.start(), m.group(0))
    # A4: 甲木正官 / 壬水正财 (compact, followed by non-十神 char)
    for m in re.finditer(rf"([{GANS}])([{WUXING}])({SHISHEN})", text):
        add("shishen_gan", m.group(1), m.group(3), m.start(), m.group(0))
    # A5: 以甲为正财
    for m in re.finditer(rf"以([{GANS}])为({SHISHEN})", text):
        add("shishen_gan", m.group(1), m.group(2), m.start(), m.group(0))
    # A6: 支为十神: 申金为伤官 / 寅木为正官 (verify via 本气)
    # 排除干支柱名(如"壬申为正财"指柱,十神按天干论),避免误判
    for m in re.finditer(
        rf"(?<![{GANS}])([{ZHIS}])(?:[{WUXING}])?(?:为|是)(?:日主|命主)?的?({SHISHEN}){_SS_TAIL}",
        text,
    ):
        add("shishen_zhi", m.group(1), m.group(2), m.start(), m.group(0))
    # A7: 柱为十神: 壬申为正财 / 甲申是正官 (十神按柱中天干论)
    for m in re.finditer(
        rf"([{GANS}])([{ZHIS}])(?:为|是)(?:日主|命主)?的?({SHISHEN}){_SS_TAIL}",
        text,
    ):
        add("shishen_gan", m.group(1), m.group(3), m.start(), m.group(0))

    # ---- Type B: 干支关系断言 ----
    # B1: 寅申相冲 / 巳亥相刑 / 子丑相合 / 寅巳相害 / 卯戌六合 / 申子三合
    for m in re.finditer(
        rf"([{ZHIS}])([{ZHIS}])(相冲|相刑|相害|相合|相破|六合|三合|半合|暗合)", text
    ):
        add("branch_rel", (m.group(1), m.group(2)), m.group(3), m.start(), m.group(0))
    # B2: compact 寅申冲 / 子丑合 (single char relation)
    for m in re.finditer(rf"([{ZHIS}])([{ZHIS}])(冲|刑|害|合|破)", text):
        add("branch_rel", (m.group(1), m.group(2)), m.group(3), m.start(), m.group(0))
    # B3: 寅与申相冲 / 巳和亥相冲
    for m in re.finditer(
        rf"([{ZHIS}])(?:与|和)([{ZHIS}])(相冲|相刑|相害|相合|相破|六合|三合)", text
    ):
        add("branch_rel", (m.group(1), m.group(2)), m.group(3), m.start(), m.group(0))
    # B4: 甲己合 / 乙庚相合 / 丙辛相冲
    for m in re.finditer(rf"([{GANS}])([{GANS}])(相合|相冲|相克|合(?!化)|冲|克)", text):
        add("gan_rel", (m.group(1), m.group(2)), m.group(3), m.start(), m.group(0))

    # ---- Type C: 五行属性断言 ----
    # C1: 甲木 / 壬水 (gan immediately followed by wuxing)
    for m in re.finditer(rf"([{GANS}])([{WUXING}])", text):
        add("wuxing_gan", m.group(1), m.group(2), m.start(), m.group(0))
    # C2: 申金 / 寅木 (zhi immediately followed by wuxing)
    for m in re.finditer(rf"([{ZHIS}])([{WUXING}])", text):
        add("wuxing_zhi", m.group(1), m.group(2), m.start(), m.group(0))

    # dedup: same type+subject+claim
    seen = set()
    out = []
    for c in claims:
        key = (c["type"], str(c["subject"]), c["claim"])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def verify_claim(claim: dict, day_gan: str, chart_zhis: set) -> dict:
    """Return verdict dict: {verdict, engine_truth, note}."""
    t = claim["type"]
    if t == "shishen_gan":
        gan, claimed = claim["subject"], claim["claim"]
        truth = get_shishen(day_gan, gan)
        verdict = "consistent" if truth == claimed else "contradiction"
        return {"verdict": verdict, "engine_truth": f"{gan}相对日主{day_gan}的十神={truth}"}
    if t == "shishen_zhi":
        zhi, claimed = claim["subject"], claim["claim"]
        main = ZHI_MAIN_GAN.get(zhi, "")
        truth = get_shishen(day_gan, main) if main else "未知"
        verdict = "consistent" if truth == claimed else "contradiction"
        return {"verdict": verdict,
                "engine_truth": f"{zhi}本气{main}相对日主{day_gan}的十神={truth}"}
    if t == "branch_rel":
        (z1, z2), claimed = claim["subject"], claim["claim"]
        actual = compute_branch_relation(z1, z2)
        # 项目表(bazi_time_context.compute_branch_relation)缺子卯相刑(无礼之刑),按标准规则补
        if {z1, z2} == {"子", "卯"} and "刑" not in actual:
            actual = actual + ["刑"]
        norm = {"相冲": "冲", "相刑": "刑", "相害": "害", "相合": "合", "相破": "破",
                "六合": "合", "三合": "三合", "半合": "三合", "暗合": "暗合",
                "冲": "冲", "刑": "刑", "害": "害", "合": "合", "破": "破"}
        c = norm.get(claimed, claimed)
        if c == "破":
            # 项目关系表无"破"，判 unverifiable
            return {"verdict": "unverifiable", "engine_truth": "项目关系表未覆盖相破"}
        if c == "暗合":
            return {"verdict": "unverifiable", "engine_truth": "项目关系表未覆盖暗合"}
        # 命理惯例:"申子合""巳酉合"等三合半合常简称"合",不判矛盾
        ok = c in actual or (c == "合" and "三合" in actual)
        in_chart = z1 in chart_zhis and z2 in chart_zhis
        note = "" if in_chart else f"注意:{z1}或{z2}不在命盘四支中"
        return {
            "verdict": "consistent" if ok else "contradiction",
            "engine_truth": f"{z1}{z2}实际关系={'+'.join(actual) if actual else '无'}",
            "note": note,
        }
    if t == "gan_rel":
        (g1, g2), claimed = claim["subject"], claim["claim"]
        pair = (g1, g2)
        pair_r = (g2, g1)
        if claimed in ("相合", "合"):
            ok = pair in GAN_WUHE or pair_r in GAN_WUHE
            truth = "五合" if ok else "非五合"
        elif claimed in ("相克", "克"):
            ok = pair in GAN_KE or pair_r in GAN_KE
            truth = "存在克" if ok else "无克"
        elif claimed in ("相冲", "冲"):
            # 天干相冲非标准关系表内容
            return {"verdict": "unverifiable", "engine_truth": "天干相冲未在项目关系表中定义"}
        else:
            return {"verdict": "unverifiable", "engine_truth": "未知关系类型"}
        return {"verdict": "consistent" if ok else "contradiction",
                "engine_truth": f"{g1}{g2}:{truth}"}
    if t == "wuxing_gan":
        gan, claimed = claim["subject"], claim["claim"]
        truth = GAN_WUXING.get(gan, "")
        return {"verdict": "consistent" if truth == claimed else "contradiction",
                "engine_truth": f"{gan}五行属{truth}"}
    if t == "wuxing_zhi":
        zhi, claimed = claim["subject"], claim["claim"]
        truth = ZHI_WUXING.get(zhi, "")
        return {"verdict": "consistent" if truth == claimed else "contradiction",
                "engine_truth": f"{zhi}五行属{truth}"}
    return {"verdict": "unverifiable", "engine_truth": "unknown claim type"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cases = load_cases()
    rows = []
    with open(MERGED, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["attempt_key"][2] != "b1a_prime":
                continue
            if r["terminal_state"] != "parsed":
                continue
            rows.append(r)
    if args.limit:
        rows = rows[: args.limit]
    print(f"b1a_prime parsed rows: {len(rows)}")

    groups = {"correct": [], "wrong": []}
    missing_chart = 0
    for r in rows:
        case = cases.get(r["case_id"])
        if not case or case.get("chart_input", {}).get("status") != "success":
            missing_chart += 1
            continue
        fp = case["chart_input"]["four_pillars"]
        day_gan = fp["day"]["gan"]
        chart_zhis = {fp[p]["zhi"] for p in ("year", "month", "day", "hour")}
        claims = extract_claims(r["raw_answer"])
        results = []
        for c in claims:
            v = verify_claim(c, day_gan, chart_zhis)
            results.append({**c, **v})
        rec = {
            "case_id": r["case_id"],
            "correct": bool(r["correct"]),
            "day_gan": day_gan,
            "claims": results,
        }
        groups["correct" if r["correct"] else "wrong"].append(rec)
        if args.verbose:
            print(f"\n=== {r['case_id']} correct={r['correct']} day_gan={day_gan} "
                  f"claims={len(results)}")
            for c in results:
                print(f"  [{c['verdict']:<12}] {c['type']:<12} {c['snippet']!r} "
                      f"-> {c['engine_truth']} {c.get('note','')}")

    if missing_chart:
        print(f"WARNING: {missing_chart} rows missing chart_input, skipped")

    # ---- aggregate ----
    report = {}
    for gname, recs in groups.items():
        n_rows = len(recs)
        rows_with_contra = 0
        tot = collections.Counter()
        per_type = collections.defaultdict(collections.Counter)
        examples = []
        for rec in recs:
            contra_in_row = 0
            for c in rec["claims"]:
                tot[c["verdict"]] += 1
                per_type[c["type"]][c["verdict"]] += 1
                if c["verdict"] == "contradiction":
                    contra_in_row += 1
                    if len(examples) < 30:
                        examples.append({
                            "case_id": rec["case_id"],
                            "correct": rec["correct"],
                            "claim": c["snippet"],
                            "type": c["type"],
                            "engine_truth": c["engine_truth"],
                            "note": c.get("note", ""),
                        })
            if contra_in_row:
                rows_with_contra += 1
        n_claims = sum(tot.values())
        report[gname] = {
            "rows": n_rows,
            "unique_cases": len({rec["case_id"] for rec in recs}),
            "rows_with_contradiction": rows_with_contra,
            "row_contradiction_rate": round(rows_with_contra / n_rows, 4) if n_rows else 0,
            "claims_total": n_claims,
            "claims_contradiction": tot["contradiction"],
            "claims_consistent": tot["consistent"],
            "claims_unverifiable": tot["unverifiable"],
            "claim_contradiction_rate": round(tot["contradiction"] / n_claims, 4) if n_claims else 0,
            "per_type": {k: dict(v) for k, v in sorted(per_type.items())},
            "examples": examples,
        }

    out_path = Path(__file__).resolve().parent / "claim_contradiction_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    for gname in ("wrong", "correct"):
        g = report[gname]
        print(f"\n[{gname}] rows={g['rows']} unique_cases={g['unique_cases']}  "
              f"rows_with>=1_contra={g['rows_with_contradiction']} "
              f"({g['row_contradiction_rate']:.1%})")
        print(f"  claims: total={g['claims_total']} contra={g['claims_contradiction']} "
              f"consistent={g['claims_consistent']} unverifiable={g['claims_unverifiable']} "
              f"contra_rate={g['claim_contradiction_rate']:.1%}")
        for t, c in g["per_type"].items():
            print(f"    {t}: {c}")
    print(f"\nreport written: {out_path}")


if __name__ == "__main__":
    main()
