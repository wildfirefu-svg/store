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
        if name.startswith("cat:"):
            return m.get("category") == name[4:]
        if name.startswith("year:"):
            return str(m.get("year")) == name[5:]
        raise ValueError(name)

    # allwrong_chart_member 已移除：先按结果选全错盘再检验其成员富集是循环定义，
    # 盘级异质性改用 §6 的非循环 Poisson-binomial sanity check。
    feats = (["question_long", "astro_coverage_low"]
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

    # ---- 5. 盘面引用率（显式匹配规则，逐题结果落盘）----
    # 规则（冻结）：
    #   chinese_date_quoted：official_astro.chinese_date 作为精确子串出现在 raw_answer 中。
    #   palace_star_quoted：official_astro.palace_stars 全部宫位星名去重集合中，
    #                       至少 1 个星名作为精确子串出现在 raw_answer 中。
    quote_rows = []
    for r in details:
        raw = r.get("raw_answer") or ""
        astro = ((r["_meta"].get("chart_input") or {}).get("official_astro") or {})
        cd = str(astro.get("chinese_date") or "")
        stars = {s for v in (astro.get("palace_stars") or {}).values() for s in str(v).split() if s}
        quote_rows.append({
            "case_id": r["case_id"],
            "correct": r["correct"],
            "chinese_date_quoted": bool(cd) and cd in raw,
            "palace_star_quoted": any(s in raw for s in stars),
            "palace_star_total": len(stars),
        })

    def rate(rows, key):
        sub = [q for q in quote_rows if (not q["correct"]) == (rows == "wrong")]
        return {"quoted": sum(q[key] for q in sub), "total": len(sub)}

    out["chart_quote_rates"] = {
        "matching_rules": {
            "chinese_date_quoted": "official_astro.chinese_date 精确子串 ∈ raw_answer",
            "palace_star_quoted": "palace_stars 去重星名集合中 ≥1 个精确子串 ∈ raw_answer",
        },
        "wrong_group": {
            "chinese_date": rate("wrong", "chinese_date_quoted"),
            "palace_star": rate("wrong", "palace_star_quoted"),
        },
        "right_group": {
            "chinese_date": rate("right", "chinese_date_quoted"),
            "palace_star": rate("right", "palace_star_quoted"),
        },
        "per_question": quote_rows,
    }

    # ---- 6. 全错盘非循环 sanity check（Poisson-binomial 精确尾部）----
    # 零假设：各题独立、错误率同为全局 p=107/160。每盘全错概率 q_i = p**(n_i)，
    # 全错盘数 X ~ Poisson-binomial(q_i)。报 E[X] 与 P(X>=observed)。
    p_err = len(wrong) / len(details)
    qs = [(t and (p_err ** t)) for c, (k, t) in sorted(charts.items())]
    observed = len(allwrong)
    # DP 计算 Poisson-binomial 分布
    dist = [1.0]
    for q in qs:
        nd = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist):
            nd[i] += v * (1 - q)
            nd[i + 1] += v * q
        dist = nd
    expected = sum(q for q in qs)
    tail = sum(dist[observed:])
    out["allwrong_chart_sanity_check"] = {
        "null_model": "iid questions, per-question error rate = 107/160; per-chart all-wrong prob = p^n_i; Poisson-binomial exact tail",
        "p_error": round(p_err, 6),
        "expected_allwrong_charts": round(expected, 4),
        "observed_allwrong_charts": observed,
        "p_ge_observed": round(tail, 4),
        "interpretation": "非循环检验：不先按结果选盘。p>=0.05 则不能拒绝同率零假设，盘级聚集不构成统计证据",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"written {OUT}, features={len(feats)}, allwrong_charts={allwrong}")


if __name__ == "__main__":
    main()
