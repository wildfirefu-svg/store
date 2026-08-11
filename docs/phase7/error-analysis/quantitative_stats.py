"""Phase 7 错误归因定量统计（设计：docs/superpowers/specs/2026-08-11-phase7-error-analysis-design.md）。

零 API、零三方依赖（Fisher 精确检验用 hypergeometric 尾部手算）。
输入：docs/phase7/phase7-mingli-v4flash-nt-20260811-r2/{merged_details.jsonl, mingli_160.jsonl}
输出：docs/phase7/error-analysis/quantitative_stats.json
"""
from __future__ import annotations

import collections
import json
import math
import re
from pathlib import Path

ARCHIVE = Path("docs/phase7/phase7-mingli-v4flash-nt-20260811-r2")
OUT = Path("docs/phase7/error-analysis/quantitative_stats.json")


def fisher_enrichment(a: int, b: int, c: int, d: int) -> float:
    """2x2 列联表（a=错题且具特征, b=错题无特征, c=对题且具特征, d=对题无特征）
    单侧富集 p 值（超几何分布尾部 P[X >= a]）。"""
    n = a + b + c + d
    k = a + c          # 具特征总数
    n1 = a + b         # 错题总数
    lo, hi = max(0, n1 - (n - k)), min(n1, k)

    def hyp(x: int) -> float:
        return math.comb(k, x) * math.comb(n - k, n1 - x) / math.comb(n, n1)

    return min(1.0, sum(hyp(x) for x in range(a, hi + 1)))


def main() -> None:
    norm = {}
    for line in open(ARCHIVE / "mingli_160.jsonl", encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            norm[row["case_id"]] = row
    details = [json.loads(l) for l in open(ARCHIVE / "merged_details.jsonl", encoding="utf-8") if l.strip()]
    assert len(details) == 160 and len(norm) == 160
    for r in details:
        r["_meta"] = norm[r["case_id"]]
    wrong = [r for r in details if not r["correct"]]
    right = [r for r in details if r["correct"]]
    out: dict = {"n_total": 160, "n_wrong": len(wrong), "n_right": len(right)}

    # ---- 1. 选项 letter 分布（位置偏置检查）----
    def letter_dist(rows, key):
        return dict(sorted(collections.Counter(str(r.get(key) or "?") for r in rows).items()))

    out["letter_distribution"] = {
        "expected_all": letter_dist(details, "expected_answer"),
        "predicted_wrong_group": letter_dist(wrong, "predicted_answer"),
        "predicted_right_group": letter_dist(right, "predicted_answer"),
    }
    conf = collections.Counter(
        (str(r["expected_answer"]), str(r["predicted_answer"])) for r in wrong)
    out["confusion_pairs_wrong"] = {f"{e}->{p}": n for (e, p), n in conf.most_common()}

    # ---- 2. 婚姻类深潜（定量部分）----
    marriage = [r for r in details if r["_meta"].get("category") == "婚姻"]
    buckets = {
        "事件反查(X年发生何事)": re.compile(r"发生何事"),
        "多段婚姻/离婚细节": re.compile(r"第几段|第.段婚姻|结束.*婚姻|婚姻终止|离婚|再婚|复婚|二婚|婚变|结婚离婚"),
        "感情细节(拍拖/分手/桃花)": re.compile(r"拍拖|分手|桃花|恋爱|对象类型"),
        "配偶特征": re.compile(r"配偶|丈夫|妻子|老公|老婆|另一半"),
        "应期(结婚/婚恋时间)": re.compile(r"哪年|何年|哪一年|那一年|当年|何时|什么时候|几时|哪岁"),
        "婚姻状况描述": re.compile(r"婚姻.*如何|婚姻状况|婚姻情况|婚姻感情|婚否|感情生活|感情状况|男女关系|姻缘"),
    }

    def bucket_of(q: str) -> str:
        for name, rx in buckets.items():
            if rx.search(q):
                return name
        return "其他"

    mb = collections.defaultdict(lambda: [0, 0])
    for r in marriage:
        b = bucket_of(r["_meta"].get("question") or "")
        mb[b][0] += r["correct"]
        mb[b][1] += 1
    out["marriage_deepdive"] = {
        "total": len(marriage),
        "wrong": sum(1 for r in marriage if not r["correct"]),
        "by_question_type": {k: {"correct": c, "total": t} for k, (c, t) in sorted(mb.items())},
    }

    # ---- 3. 全错命盘构成 ----
    charts = collections.defaultdict(lambda: [0, 0])
    for r in details:
        charts[r["chart_case_id"]][0] += r["correct"]
        charts[r["chart_case_id"]][1] += 1
    allwrong = sorted([c for c, (k, t) in charts.items() if k == 0],
                      key=lambda c: int(c.split("_")[1]))
    out["allwrong_charts"] = {
        "charts": allwrong,
        "categories": {c: sorted({r["_meta"].get("category") for r in details
                                  if r["chart_case_id"] == c}) for c in allwrong},
        "years": {c: sorted({str(r["_meta"].get("year")) for r in details
                             if r["chart_case_id"] == c}) for c in allwrong},
    }

    # ---- 4. 特征富集（Fisher 单侧）----
    qlens = sorted(len(r["_meta"].get("question") or "") for r in details)
    qlen_med = qlens[len(qlens) // 2]
    astro_counts = sorted(
        len(((r["_meta"].get("chart_input") or {}).get("official_astro") or {}).get("palace_stars") or {})
        for r in details)
    astro_med = astro_counts[len(astro_counts) // 2]

    def feat(row, name):
        m = row["_meta"]
        if name == "question_long":
            return len(m.get("question") or "") > qlen_med
        if name == "astro_coverage_low":
            astro = (m.get("chart_input") or {}).get("official_astro") or {}
            return len(astro.get("palace_stars") or {}) < astro_med
        if name == "allwrong_chart_member":
            return row["chart_case_id"] in allwrong
        if name.startswith("cat:"):
            return m.get("category") == name[4:]
        if name.startswith("year:"):
            return str(m.get("year")) == name[5:]
        raise ValueError(name)

    feats = (["question_long", "astro_coverage_low", "allwrong_chart_member"]
             + [f"cat:{c}" for c in sorted({r['_meta'].get('category') for r in details})]
             + [f"year:{y}" for y in ("2022", "2023", "2024", "2025")])
    enrich = {}
    for f in feats:
        a = sum(1 for r in wrong if feat(r, f))
        c_ = sum(1 for r in right if feat(r, f))
        p = fisher_enrichment(a, len(wrong) - a, c_, len(right) - c_)
        enrich[f] = {"wrong_with": a, "wrong_without": len(wrong) - a,
                     "right_with": c_, "right_without": len(right) - c_,
                     "p_value": round(p, 4)}
    out["feature_enrichment"] = enrich
    out["feature_notes"] = {
        "question_len_median": qlen_med,
        "astro_palace_stars_median": astro_med,
        "test": "Fisher exact one-sided (enrichment), alpha=0.05, no multiple-testing correction",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"written {OUT}, features={len(feats)}, allwrong_charts={allwrong}")


if __name__ == "__main__":
    main()
