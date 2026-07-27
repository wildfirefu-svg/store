#!/usr/bin/env python3
"""Phase 6 6B1-D 补充分析: 从 merged_details.jsonl + labels.jsonl 提取 plan §7 要求的全部产出.

计算项 (全部描述性, 不作统计推断):
  1. 各臂 parser rate
  2. 输出长度分析 (raw_answer 字符数 + completion_tokens)
  3. year × repeat × arm 准确率矩阵 (稳定性说明)
  4. 三标签维度分层准确率 (question_complexity / ziwei_info_richness / bazi_info_richness)
  5. 五臂逐题答案一致性矩阵
  6. b2b/b2c 定性案例 (各 5 例, 正确/错误混合)
  7. 2 条严格解析失败记录 + 宽松解析敏感性
  8. 与历史 6B1 的 b1c-b1b 复现对照

用法:
  python scripts/phase6_6b1d_report_analysis.py \
    --r3-merged docs/phase6/6b1d/<archive>/merged_details.jsonl \
    --labels docs/phase6/6b1d/labels.jsonl \
    --hist-merged docs/phase6/6b1/6b1-2026-07-17-deepseek-deepseek-chat-78481de6/merged_details.jsonl \
    --output benchmark/outputs/phase6_6b1d_r3/analysis_supplement.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path


ARMS = ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]
LABEL_DIMS = ["question_complexity", "ziwei_info_richness", "bazi_info_richness"]


def load_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def parse_record(rec: dict) -> dict:
    """从 merged_details 记录提取标准化字段."""
    ak = rec.get("attempt_key", [])
    dataset = ak[0] if len(ak) > 0 else ""
    arm = ak[2] if len(ak) > 2 else ""
    case_id = ak[6] if len(ak) > 6 else rec.get("case_id", "")
    repeat = ak[7] if len(ak) > 7 else 0
    year = "2024" if "2024" in dataset else ("2025" if "2025" in dataset else "")
    usage = rec.get("usage") or {}
    raw_ans = rec.get("raw_answer") or ""
    return {
        "case_id": case_id,
        "arm": arm,
        "year": year,
        "repeat": int(repeat),
        "correct": bool(rec.get("correct", False)),
        "call_success": bool(rec.get("call_success", False)),
        "parser_valid": bool(rec.get("parser_valid", False)),
        "terminal_state": rec.get("terminal_state", ""),
        "parser_source": rec.get("parser_source", ""),
        "parser_failure_reason": rec.get("parser_failure_reason", ""),
        "predicted_answer": rec.get("predicted_answer", ""),
        "expected_answer": rec.get("expected_answer", ""),
        "raw_answer": raw_ans,
        "raw_answer_len": len(raw_ans),
        "completion_tokens": usage.get("completion_tokens", 0),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "finish_reason": rec.get("finish_reason", ""),
        "response_id": rec.get("response_id", ""),
    }


def load_labels(path: str) -> dict:
    """case_id -> final labels dict."""
    out = {}
    for rec in load_jsonl(path):
        out[rec["case_id"]] = rec.get("final", {})
    return out


def acc(records):
    if not records:
        return 0.0, 0, 0
    correct = sum(1 for r in records if r["correct"])
    return correct / len(records), correct, len(records)


def compute_arm_stats(records):
    """1. parser rate + 2. 输出长度 + 6(部分). parser rate per arm."""
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r["arm"]].append(r)
    out = {}
    for arm in ARMS:
        recs = by_arm.get(arm, [])
        if not recs:
            continue
        parsed = sum(1 for r in recs if r["parser_valid"])
        call_ok = sum(1 for r in recs if r["call_success"])
        a, c, n = acc(recs)
        lens = [r["raw_answer_len"] for r in recs]
        ctoks = [r["completion_tokens"] for r in recs if r["completion_tokens"] > 0]
        out[arm] = {
            "n": n,
            "accuracy": round(a, 4),
            "correct": c,
            "parser_valid": parsed,
            "parser_rate": round(parsed / n, 4) if n else 0.0,
            "call_success": call_ok,
            "call_success_rate": round(call_ok / n, 4) if n else 0.0,
            "raw_answer_len_mean": round(statistics.mean(lens), 1) if lens else 0,
            "raw_answer_len_median": int(statistics.median(lens)) if lens else 0,
            "raw_answer_len_min": min(lens) if lens else 0,
            "raw_answer_len_max": max(lens) if lens else 0,
            "completion_tokens_mean": round(statistics.mean(ctoks), 1) if ctoks else 0,
            "completion_tokens_median": int(statistics.median(ctoks)) if ctoks else 0,
        }
    return out


def compute_year_repeat_matrix(records):
    """3. year × repeat × arm 准确率矩阵."""
    by_cell = defaultdict(list)
    for r in records:
        by_cell[(r["year"], r["repeat"], r["arm"])].append(r)
    matrix = {}
    for year in ["2024", "2025"]:
        matrix[year] = {}
        for rep in [0, 1, 2]:
            matrix[year][rep] = {}
            for arm in ARMS:
                recs = by_cell.get((year, rep, arm), [])
                a, c, n = acc(recs)
                matrix[year][rep][arm] = {
                    "accuracy": round(a, 4), "correct": c, "n": n
                }
    # year-level + repeat-level means per arm
    by_year_arm = defaultdict(list)
    by_rep_arm = defaultdict(list)
    for r in records:
        by_year_arm[(r["year"], r["arm"])].append(r)
        by_rep_arm[(r["repeat"], r["arm"])].append(r)
    year_summary = {}
    for year in ["2024", "2025"]:
        year_summary[year] = {}
        for arm in ARMS:
            a, c, n = acc(by_year_arm.get((year, arm), []))
            year_summary[year][arm] = {"accuracy": round(a, 4), "correct": c, "n": n}
    rep_summary = {}
    for rep in [0, 1, 2]:
        rep_summary[rep] = {}
        for arm in ARMS:
            a, c, n = acc(by_rep_arm.get((rep, arm), []))
            rep_summary[rep][arm] = {"accuracy": round(a, 4), "correct": c, "n": n}
    return {"cells": matrix, "year_summary": year_summary, "repeat_summary": rep_summary}


def compute_layered(records, labels):
    """4. 三标签维度分层准确率."""
    by_dim = {dim: defaultdict(list) for dim in LABEL_DIMS}
    for r in records:
        lab = labels.get(r["case_id"])
        if not lab:
            continue
        for dim in LABEL_DIMS:
            val = lab.get(dim)
            if val is None:
                continue
            by_dim[dim][(val, r["arm"])].append(r)
    out = {}
    for dim in LABEL_DIMS:
        out[dim] = {}
        # collect all layer values
        vals = sorted({v for (v, _a) in by_dim[dim].keys()})
        for v in vals:
            out[dim][v] = {}
            for arm in ARMS:
                recs = by_dim[dim].get((v, arm), [])
                a, c, n = acc(recs)
                out[dim][v][arm] = {"accuracy": round(a, 4), "correct": c, "n": n,
                                    "skipped": n < 5}
    return out


def compute_consistency(records):
    """5. 五臂逐题答案一致性矩阵.

    对每个 case_id, 收集 5 臂的 predicted_answer (跨 repeat 取多数或全部),
    统计: 全一致 / 4 臂一致 / 更低一致性 的 case 数.
    """
    by_case = defaultdict(dict)
    for r in records:
        if not r["parser_valid"]:
            continue
        by_case[r["case_id"]].setdefault(r["arm"], []).append(r["predicted_answer"])
    full_agree = 0
    four_agree = 0
    lower = 0
    total = 0
    per_case = []
    for case_id, arm_ans in by_case.items():
        if len(arm_ans) < 5:
            continue
        total += 1
        # 取每臂的众数 predicted_answer
        arm_modes = {}
        for arm, ans_list in arm_ans.items():
            if ans_list:
                # majority
                counts = defaultdict(int)
                for a in ans_list:
                    counts[a] += 1
                arm_modes[arm] = max(counts, key=counts.get)
        distinct = set(arm_modes.values())
        if len(distinct) == 1:
            full_agree += 1
        elif len(distinct) == 2:
            four_agree += 1
        else:
            lower += 1
        per_case.append({"case_id": case_id, "arm_modes": arm_modes,
                         "distinct_answers": sorted(distinct)})
    return {
        "total_cases": total,
        "all_5_arms_agree": full_agree,
        "four_arms_agree": four_agree,
        "lower_agreement": lower,
        "agreement_rate": round(full_agree / total, 4) if total else 0.0,
        "per_case_detail": per_case,
    }


def compute_qualitative(records, arm, k=5):
    """6. b2b/b2c 定性案例 (各 k 例, 正确/错误混合)."""
    arm_recs = [r for r in records if r["arm"] == arm and r["parser_valid"]]
    correct = [r for r in arm_recs if r["correct"]]
    wrong = [r for r in arm_recs if not r["correct"]]
    # 取前 k/2 正确 + k/2 错误 (按 case_id 排序保证可复现)
    correct.sort(key=lambda r: r["case_id"])
    wrong.sort(key=lambda r: r["case_id"])
    half = k // 2
    picked = correct[:half] + wrong[:k - half]
    # 如果某一类不足, 用另一类补
    if len(picked) < k:
        pool = (correct[half:] + wrong[k - half:])
        pool.sort(key=lambda r: r["case_id"])
        picked.extend(pool[:k - len(picked)])
    return [{
        "case_id": r["case_id"],
        "year": r["year"],
        "correct": r["correct"],
        "predicted": r["predicted_answer"],
        "expected": r["expected_answer"],
        "raw_answer_excerpt": r["raw_answer"][:200] + ("..." if len(r["raw_answer"]) > 200 else ""),
        "raw_answer_len": r["raw_answer_len"],
    } for r in picked[:k]]


def compute_parse_failures(records):
    """7. 严格解析失败记录 + 宽松解析敏感性."""
    fails = [r for r in records if not r["parser_valid"] and r["call_success"]]
    fail_detail = [{
        "case_id": r["case_id"],
        "arm": r["arm"],
        "year": r["year"],
        "repeat": r["repeat"],
        "terminal_state": r["terminal_state"],
        "parser_failure_reason": r["parser_failure_reason"],
        "finish_reason": r["finish_reason"],
        "raw_answer_excerpt": r["raw_answer"][:300] + ("..." if len(r["raw_answer"]) > 300 else ""),
        "raw_answer_len": r["raw_answer_len"],
    } for r in fails]
    # 宽松解析: 严格正确不变; 仅对严格解析失败 (parser_valid=false, call_success=true)
    # 且 raw_answer 含 expected 选项的记录翻为正确. 不翻 parser_valid=true 但答错的记录.
    # (仅用于敏感性说明, 不改主结果)
    loose_by_arm = defaultdict(lambda: {"correct": 0, "n": 0})
    for r in records:
        if not r["call_success"]:
            continue
        loose_by_arm[r["arm"]]["n"] += 1
        if r["correct"]:
            loose_by_arm[r["arm"]]["correct"] += 1
        elif not r["parser_valid"]:
            exp = r["expected_answer"]
            if exp and exp in r["raw_answer"]:
                loose_by_arm[r["arm"]]["correct"] += 1
    loose_stats = {}
    for arm, d in loose_by_arm.items():
        n = d["n"]
        loose_stats[arm] = {
            "loose_accuracy": round(d["correct"] / n, 4) if n else 0.0,
            "loose_correct": d["correct"],
            "n": n,
        }
    return {"strict_failures": fail_detail, "loose_sensitivity": loose_stats}


def compute_hist_comparison(hist_records):
    """8. 历史 6B1 b1c-b1b 复现对照."""
    by_arm = defaultdict(list)
    for r in hist_records:
        by_arm[r["arm"]].append(r)
    out = {}
    for arm in ["b1a_prime", "b1b", "b1c"]:
        recs = by_arm.get(arm, [])
        a, c, n = acc(recs)
        out[arm] = {"accuracy": round(a, 4), "correct": c, "n": n}
    if "b1c" in out and "b1b" in out:
        out["b1c_minus_b1b"] = round(out["b1c"]["accuracy"] - out["b1b"]["accuracy"], 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r3-merged", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--hist-merged", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    r3_recs = [parse_record(r) for r in load_jsonl(args.r3_merged)]
    labels = load_labels(args.labels)

    result = {
        "experiment": "6b1d-r3",
        "n_records": len(r3_recs),
        "arm_stats": compute_arm_stats(r3_recs),
        "year_repeat_matrix": compute_year_repeat_matrix(r3_recs),
        "layered": compute_layered(r3_recs, labels),
        "consistency": compute_consistency(r3_recs),
        "qualitative_b2b": compute_qualitative(r3_recs, "b2b", 5),
        "qualitative_b2c": compute_qualitative(r3_recs, "b2c", 5),
        "parse_failures": compute_parse_failures(r3_recs),
    }
    if args.hist_merged and os.path.exists(args.hist_merged):
        hist_recs = [parse_record(r) for r in load_jsonl(args.hist_merged)]
        result["hist_6b1_comparison"] = compute_hist_comparison(hist_recs)

    # labels preflight (layer sizes)
    label_sizes = {dim: defaultdict(int) for dim in LABEL_DIMS}
    for cid, lab in labels.items():
        for dim in LABEL_DIMS:
            v = lab.get(dim)
            if v is not None:
                label_sizes[dim][v] += 1
    result["label_preflight"] = {
        dim: {str(k): v for k, v in sorted(sizes.items())}
        for dim, sizes in label_sizes.items()
    }
    # annotator disagreement
    disagree = 0
    total_dims = 0
    for rec in load_jsonl(args.labels):
        a1 = rec.get("annotator_1", {})
        a2 = rec.get("annotator_2", {})
        for dim in LABEL_DIMS:
            total_dims += 1
            if a1.get(dim) != a2.get(dim):
                disagree += 1
    result["label_preflight"]["annotator_disagreement"] = disagree
    result["label_preflight"]["total_dim_comparisons"] = total_dims

    Path(os.path.dirname(args.output) or ".").mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[analysis] -> {args.output}")
    print(f"  records: {len(r3_recs)}")
    print(f"  parser failures: {len(result['parse_failures']['strict_failures'])}")
    if "hist_6b1_comparison" in result:
        h = result["hist_6b1_comparison"]
        print(f"  hist 6B1: b1c-b1b = {h.get('b1c_minus_b1b', 'N/A')}")


if __name__ == "__main__":
    raise SystemExit(main())
