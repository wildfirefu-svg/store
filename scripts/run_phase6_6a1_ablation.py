"""Phase 6 6A1 编排器：严格 ≥3/5 投票同源配对 + temp-0 锚定（设计 v6 §5）。

probe 多样性试测（仅合法选项 + 完整性 BLOCKED）→ AB/BA 12 切片 → 全量完整性检查
→ 离线严格聚合（strict_majority，不跨 repeat）→ Δ1/Δ2 + 四格表 + unresolved + 成本代理 → verdict。
决策逻辑均为无网络纯函数；真实模型调用仅经 run_slice 子进程边界发起。
上下文基线 legacy_v0（6A0 ROLLBACK，设计 §10）。预算复用 6A0 BudgetLedger。
CLI 年份封死（dev 仅 2024 / 复核仅 2021）；复核温度 --dev-run-id 自动读取。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
ARCHIVE_ROOT = PROJECT_ROOT / "docs" / "phase6"        # v6 阻断 2：归档根目录

from benchmark.formatters.baziqa_prompt import format_direct_choice_prompt
from benchmark.formatters.chart_context import render_chart_context
from benchmark.formatters.leak_scan import scan_prompt_for_leaks
from benchmark.reports.accuracy_stats import trimmed_mean
from benchmark.runners.profiles import assert_visibility, resolve_profile
from benchmark.runners.self_consistency import strict_majority
from scripts.build_phase6_audit_index import sha256_file
from scripts.enrich_baziqa_chart_input import load_jsonl
from scripts.run_phase6_6a0_ablation import (
    BudgetLedger,
    BudgetLedgerCorrupt,
    split_ab_ba,
    _git_head,
)

WORKSPACE_FILES = (
    "scripts/run_phase6_6a1_ablation.py",
    "scripts/build_phase6_audit_index.py",
    "benchmark/runners/run_benchmark.py",
    "benchmark/runners/self_consistency.py",
)


def _collect_workspace_state() -> dict:
    """v5 门禁：收集实验范围文件的 dirty 状态与 SHA（真实 API 实验前要求无未提交修改）。"""
    import subprocess
    try:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *WORKSPACE_FILES],
            cwd=PROJECT_ROOT, text=True).strip().splitlines()
    except Exception:
        return {"collect_error": "git status failed"}
    return {
        "dirty_files": [l.strip() for l in dirty if l.strip()],
        "clean": len(dirty) == 0,
        "file_sha256": {f: sha256_file(PROJECT_ROOT / f) for f in WORKSPACE_FILES
                        if (PROJECT_ROOT / f).exists()},
    }

PROFILE_ID = "baziqa_xjz_direct"
SCHEMA = "legacy_v0"                      # 6A0 ROLLBACK 锁定（设计 §10）
EXPECTED_CASES = 40
N_SAMPLES = 5
PROBE_CASES = 10
DIVERSITY_THRESHOLD = 0.6
DEFAULT_T = 0.4
FALLBACK_T = 1.0
ARM_SAMPLE = "vote5_samples"
ARM_ANCHOR = "anchor_single0"
ANCHOR_CAPS = (24, 23, 23, 23, 23, 24)    # 和 140
SAMPLE_CAPS = (110,) * 6                  # 和 660
PROBE_CAP = 55
VALID_LETTERS = frozenset("ABCD")
TERMINAL_OK = frozenset(("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed"))


@dataclass(frozen=True)
class VoteConfig:
    run_id: str
    year: int
    root: Path
    enriched_path: Path
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    repeats: int = 3
    seed: int = 20260717
    stage_hard_cap: int = 910               # 2021 复核：800
    resume: bool = True
    as_of_date: str = ""                    # v4 建议：从 enriched manifest 读取，非运行当天
    dev_dataset_sha256: str = ""            # v6 阻断 1：2024 批准 SHA（复核模式传入）


@dataclass(frozen=True)
class VoteSlice:
    purpose: str                            # "probe" | "main"
    repeat_idx: int                         # probe 固定 -1
    arm: str
    stage: str
    group: str
    case_ids: tuple
    n_samples: int
    temperature: float                      # 采样臂=sample_temperature；锚定=0.0
    scheduled_calls: int
    hard_cap: int


# ---------- 纯函数：probe 多样性（审核阻断 4） ----------

def diversity_rate(rows: list, expected_probe_case_ids: list) -> float:
    """每题 ≥2 个不同合法选项的比例。只计 terminal_state=="parsed" 且答案 ∈ A/B/C/D
    （invalid/None/call_failed 不算第二个选项——审核阻断 4；不查看答案正确性——设计 §5.2.2）。"""
    per_case = {cid: set() for cid in expected_probe_case_ids}
    for r in rows:
        if r.get("terminal_state") != "parsed":
            continue
        ans = r.get("predicted_answer")
        cid = r["case_id"]
        if cid not in per_case:
            raise ValueError(f"预期外 case：{cid} 不在 probe 集合")
        if ans in VALID_LETTERS:
            per_case[cid].add(ans)
    if not per_case:
        return 0.0
    diverse = sum(1 for s in per_case.values() if len(s) >= 2)
    return round(diverse / len(per_case), 4)


def probe_rows_complete(rows: list, expected_probe_case_ids: list, expected_arm: str) -> None:
    """probe 数据完整性（v5 阻断 1）：严格验证 case 集合恰好等于预期 + arm==expected_arm +
    attempt_stage（ak[3]）==diversity_probe + repeat_idx（ak[7]）==-1 + 每题 sample_idx（ak[8]）
    恰好 {0,1,2,3,4} + 无额外行。不再只验证题数。
    v5 修正：attempt_stage 索引 ak[6] -> ak[3]（ak[6] 是 case_id）。
    v5 新增 expected_arm：禁止同文件混合 probe_r1 与 probe_r2。"""
    expected = set(expected_probe_case_ids)
    counts, per_case, arms, stages, repeats = {}, {}, set(), set(), set()
    for r in rows:
        cid = r["case_id"]
        counts[cid] = counts.get(cid, 0) + 1
        ak = r.get("attempt_key") or [None] * 10
        per_case.setdefault(cid, set()).add(ak[8])
        arms.add(ak[2])
        stages.add(ak[3])                   # v5: ak[3]=attempt_stage（原 ak[6] 是 case_id）
        repeats.add(ak[7])                  # ak[7]=repeat_idx
    actual = set(per_case.keys())
    if actual != expected:
        miss = expected - actual
        extra = actual - expected
        raise ValueError(f"不完整：probe case 集合不匹配（缺失 {len(miss)}，额外 {len(extra)}）")
    if arms != {expected_arm}:
        raise ValueError(f"不完整：probe arm 异常 {arms}，预期 {{expected_arm}}")
    if stages - {"diversity_probe"}:
        raise ValueError(f"不完整：attempt_stage 异常 {stages}")
    if repeats - {-1}:
        raise ValueError(f"不完整：repeat_idx 异常 {repeats}")
    for cid, idxs in per_case.items():
        if counts[cid] != N_SAMPLES or idxs != {0, 1, 2, 3, 4}:
            raise ValueError(f"不完整：probe {cid} 行数={counts[cid]} sample_idx={sorted(idxs)}")


def evaluate_t_switch(rate_r1: float, rate_r2) -> tuple:
    """T 冻结链（计划决策 4）：返回 (action, T)。r2 未运行传 None。"""
    if rate_r1 >= DIVERSITY_THRESHOLD:
        return ("freeze", DEFAULT_T)
    if rate_r2 is None:
        return ("probe_r2", DEFAULT_T)
    if rate_r2 >= DIVERSITY_THRESHOLD:
        return ("freeze", FALLBACK_T)
    return ("freeze_low_diversity", FALLBACK_T)


# ---------- 纯函数：调度 ----------

def validate_case_ids(case_ids: list) -> None:
    """v3 中优 6：case_id 早期校验，probe 前即拒绝畸形 dataset（不浪费 API 费用）。"""
    if len(case_ids) != EXPECTED_CASES:
        raise ValueError(f"6A1 要求 {EXPECTED_CASES} 个 case_id，实得 {len(case_ids)}")
    if len(set(case_ids)) != EXPECTED_CASES:
        raise ValueError(f"case_id 不唯一：{len(case_ids)} 项中仅 {len(set(case_ids))} 个唯一")


def validate_enrichment_entry(entry: dict, enriched_path: Path, expected_year: int,
                              expected_as_of_date: str) -> str:
    """v7 高优 4 + v8 阻断/高优 1：enrichment entry 实体校验纯函数（current 与 dev 共用）。
    返回 entry 的 output_sha256（供 manifest 记录）。
    校验：entry.year==expected_year、output_path 存在且 resolve 等于 enriched_path、
    实际文件 SHA==output_sha256、**实际 JSONL 行数==entry.row_count==EXPECTED_CASES**（v8 阻断）、
    as_of_date==expected_as_of_date 且非空（v8 高优 1：与顶层日期绑定）。"""
    if entry.get("year") != expected_year:
        raise ValueError(f"entry year 异常：{entry.get('year')} != {expected_year}")
    out_path = Path(entry["output_path"])
    if not out_path.is_file():
        raise ValueError(f"enriched 文件不存在：{out_path}")
    if out_path.resolve() != enriched_path.resolve():
        raise ValueError(f"output_path 与 enriched_path 不一致：{out_path} != {enriched_path}")
    actual_sha = sha256_file(out_path)
    if actual_sha != entry.get("output_sha256"):
        raise ValueError(f"output_sha256 不匹配：期望 {entry.get('output_sha256')}，实际 {actual_sha}")
    # v8 阻断：统计实际 JSONL 行数，不能只信 entry.row_count
    actual_rows = sum(1 for line in out_path.read_text(encoding="utf-8").splitlines()
                      if line.strip())
    if actual_rows != entry.get("row_count"):
        raise ValueError(f"实际行数与 row_count 不一致：{actual_rows} != {entry.get('row_count')}")
    if actual_rows != EXPECTED_CASES:
        raise ValueError(f"实际行数异常：{actual_rows} != {EXPECTED_CASES}")
    if not entry.get("as_of_date"):
        raise ValueError("as_of_date 为空")
    if entry["as_of_date"] != expected_as_of_date:
        raise ValueError(f"as_of_date 与顶层不一致：{entry['as_of_date']} != {expected_as_of_date}")
    return entry["output_sha256"]


def freeze_temperature(probe_info: dict, temperature: float) -> dict:
    """v8 高优 2：温度冻结纯函数（返回新字典，含 sample_temperature 字段）。
    生产主流程与闭环测试都调用；若生产删除该调用，测试直接失败（不再手工补写字段）。"""
    return {**probe_info, "sample_temperature": temperature}


def build_probe_slice(config: VoteConfig, case_ids: list, arm: str,
                      temperature: float) -> VoteSlice:
    return VoteSlice("probe", -1, arm, "diversity_probe", "probe",
                     tuple(case_ids[:PROBE_CASES]), N_SAMPLES, temperature,
                     PROBE_CASES * N_SAMPLES, PROBE_CAP)


def build_main_schedule(config: VoteConfig, case_ids: list,
                        sample_temperature: float = DEFAULT_T) -> list:
    if len(case_ids) != EXPECTED_CASES or len(set(case_ids)) != EXPECTED_CASES:
        raise ValueError(f"6A1 要求 {EXPECTED_CASES} 个唯一 case_id，"
                         f"实得 {len(case_ids)}（唯一 {len(set(case_ids))}）")
    group_a, group_b = split_ab_ba(case_ids, config.seed)
    groups = {"group_a": group_a, "group_b": group_b}
    schedule = []
    sample_count = 0
    anchor_count = 0
    for rep in range(config.repeats):
        for arm, stage, group, n, temp, sched in (
                (ARM_SAMPLE, "main", "group_a", N_SAMPLES, sample_temperature, 100),
                (ARM_ANCHOR, "anchor", "group_a", 1, 0.0, 20),
                (ARM_ANCHOR, "anchor", "group_b", 1, 0.0, 20),
                (ARM_SAMPLE, "main", "group_b", N_SAMPLES, sample_temperature, 100)):
            if arm == ARM_SAMPLE:
                cap = SAMPLE_CAPS[sample_count]
                sample_count += 1
            else:
                cap = ANCHOR_CAPS[anchor_count]
                anchor_count += 1
            schedule.append(VoteSlice("main", rep, arm, stage, group, groups[group],
                                      n, temp, sched, cap))
    if sum(s.hard_cap for s in schedule) != 660 + sum(ANCHOR_CAPS):
        raise ValueError("cap 和异常")
    return schedule


# ---------- 纯函数：完整性与严格聚合（审核阻断 2） ----------

def strict_rows_complete(rows: list, expected_case_ids: list, repeats: int) -> None:
    """决策数据完整性（审核阻断 2）：唯一 attempt 数精确、无重复、无额外 case/repeat/arm、
    每个预期 (case, repeat) 两臂齐全、终态合法。任一不过 → 上层映射 BLOCKED_INCOMPLETE。"""
    expected_cases = set(expected_case_ids)
    seen_sample, seen_anchor = set(), set()
    for r in rows:
        ak = r.get("attempt_key") or [None] * 10
        arm, rep, idx, cid = ak[2], ak[7], ak[8], r.get("case_id")
        if cid not in expected_cases:
            raise ValueError(f"额外 case：{cid}")
        if not isinstance(rep, int) or not (0 <= rep < repeats):
            raise ValueError(f"额外 repeat：{rep}（{cid}）")
        if r.get("terminal_state") not in TERMINAL_OK:
            raise ValueError(f"终态非法：{r.get('terminal_state')}（{cid}）")
        key = (cid, rep, idx)
        if not isinstance(idx, int) or not (0 <= idx < N_SAMPLES):
            raise ValueError(f"额外 sample_idx：{idx}（{cid}）")
        if arm == ARM_SAMPLE:
            if key in seen_sample:
                raise ValueError(f"重复行：采样 {key}")
            seen_sample.add(key)
        elif arm == ARM_ANCHOR:
            if idx != 0:
                raise ValueError(f"anchor 行 sample_idx 必须 0，实得 {idx}（{cid}）")
            if key in seen_anchor:
                raise ValueError(f"重复行：锚定 {key}")
            seen_anchor.add(key)
        else:
            raise ValueError(f"未知 arm：{arm}（{cid}）")
    expected_sample = {(c, rep, i) for c in expected_cases
                       for rep in range(repeats) for i in range(N_SAMPLES)}
    expected_anchor = {(c, rep, 0) for c in expected_cases for rep in range(repeats)}
    if seen_sample != expected_sample:
        miss_s = expected_sample - seen_sample
        extra_s = seen_sample - expected_sample
        raise ValueError(f"不完整：采样集合不匹配（缺失 {len(miss_s)}，额外 {len(extra_s)}）")
    if seen_anchor != expected_anchor:
        miss_a = expected_anchor - seen_anchor
        extra_a = seen_anchor - expected_anchor
        raise ValueError(f"不完整：锚定集合不匹配（缺失 {len(miss_a)}，额外 {len(extra_a)}）")


def aggregate_metrics(rows: list, expected_case_ids: list, repeats: int) -> dict:
    """按 (case, repeat) 聚合：vote5=strict_majority(5 样本)；single@T=sample_idx 0；锚定=anchor 行。
    unresolved/invalid/call_failed 计错；禁止跨 repeat（§5.2.6）。
    完整性不过 → ValueError（上层映射 BLOCKED_INCOMPLETE，不产出 verdict）。"""
    strict_rows_complete(rows, expected_case_ids, repeats)
    acc = {"vote5": [], "single_t": [], "anchor": []}
    per_repeat_delta1, per_repeat_delta2 = [], []
    unresolved = 0
    grid_t = {"both": 0, "vote5_only": 0, "single_t_only": 0, "neither": 0}
    grid_a = {"both": 0, "vote5_only": 0, "anchor_only": 0, "neither": 0}
    case_records = []
    for rep in range(repeats):
        cases = sorted(expected_case_ids)
        n_v5 = n_st = n_an = 0
        for cid in cases:
            srows = sorted((r for r in rows
                            if r["case_id"] == cid
                            and (r.get("attempt_key") or [None] * 10)[2] == ARM_SAMPLE
                            and (r.get("attempt_key") or [None] * 10)[7] == rep),
                           key=lambda r: r["attempt_key"][8])
            arow = next(r for r in rows
                        if r["case_id"] == cid
                        and (r.get("attempt_key") or [None] * 10)[2] == ARM_ANCHOR
                        and (r.get("attempt_key") or [None] * 10)[7] == rep)
            votes = [r["predicted_answer"] if r["terminal_state"] == "parsed" else None
                     for r in srows]
            v5 = strict_majority(votes)
            if v5 is None:
                unresolved += 1
            exp = srows[0]["expected_answer"]
            ok_v5 = v5 is not None and v5 == exp
            ok_st = (srows[0]["terminal_state"] == "parsed"
                     and srows[0]["predicted_answer"] == exp)
            ok_an = (arow["terminal_state"] == "parsed"
                     and arow["predicted_answer"] == exp)
            n_v5 += ok_v5; n_st += ok_st; n_an += ok_an
            grid_t["both" if ok_v5 and ok_st else
                   "vote5_only" if ok_v5 else
                   "single_t_only" if ok_st else "neither"] += 1
            grid_a["both" if ok_v5 and ok_an else
                   "vote5_only" if ok_v5 else
                   "anchor_only" if ok_an else "neither"] += 1
            case_records.append({
                "case_id": cid, "repeat_idx": rep,
                "domain": srows[0].get("domain", "unknown"),
                "votes": votes, "vote5": v5,
                "single_t": srows[0]["predicted_answer"]
                            if srows[0]["terminal_state"] == "parsed" else None,
                "anchor": arow["predicted_answer"]
                          if arow["terminal_state"] == "parsed" else None,
                "expected": exp, "unresolved": v5 is None,
                "vote5_correct": ok_v5, "single_t_correct": ok_st, "anchor_correct": ok_an,
            })
        n = len(cases)
        acc["vote5"].append(round(n_v5 / n, 4))
        acc["single_t"].append(round(n_st / n, 4))
        acc["anchor"].append(round(n_an / n, 4))
        per_repeat_delta1.append(round((n_v5 - n_st) / n * 100, 2))
        per_repeat_delta2.append(round((n_v5 - n_an) / n * 100, 2))
    total = len(expected_case_ids) * repeats
    from benchmark.reports.accuracy_stats import trimmed_mean
    acc_trimmed_mean = {arm: round(trimmed_mean(acc[arm], 0.1), 4)
                        for arm in ("vote5", "single_t", "anchor")}
    by_domain = {}
    for domain in sorted({r.get("domain", "unknown") for r in case_records}):
        d_recs = [r for r in case_records if r.get("domain", "unknown") == domain]
        dn = len(d_recs)
        v5 = sum(r["vote5_correct"] for r in d_recs) / dn
        st = sum(r["single_t_correct"] for r in d_recs) / dn
        an = sum(r["anchor_correct"] for r in d_recs) / dn
        by_domain[domain] = {
            "vote5": round(v5, 4), "single_t": round(st, 4), "anchor": round(an, 4),
            "delta1_pp": round((v5 - st) * 100, 2), "delta2_pp": round((v5 - an) * 100, 2),
            "n": dn,
        }
    return {
        "acc": acc,
        "per_repeat_delta1": per_repeat_delta1,
        "per_repeat_delta2": per_repeat_delta2,
        "delta1_pp": round(sum(per_repeat_delta1) / repeats, 2),
        "delta2_pp": round(sum(per_repeat_delta2) / repeats, 2),
        "acc_trimmed_mean": acc_trimmed_mean,
        "by_domain": by_domain,
        "unresolved_rate": round(unresolved / max(total, 1), 4),
        "four_grid_vote5_vs_single_t": grid_t,
        "four_grid_vote5_vs_anchor": grid_a,
        "case_records": case_records,
        "call_failed": sum(1 for r in rows if r.get("terminal_state") == "call_failed"),
    }


def gate_verdict(delta1_pp: float, delta2_pp: float) -> str:
    """设计 §5.3 dev gate。"""
    if delta1_pp >= 3.0:
        return "PROMOTE_CANDIDATE" if delta2_pp >= 0.0 else "AGGREGATION_EFFECT_ONLY"
    if delta1_pp <= -3.0:
        return "ROLLBACK"
    return "NON_INFERIOR"


def recheck_verdict(delta1_year: float, delta2_year: float) -> str:
    """设计 §5.3 复核（仅 2021）：双条件通过方确认。"""
    return "PROMOTE_CONFIRMED" if delta1_year >= 2.0 and delta2_year >= 0.0 \
        else "RECHECK_FAILED"


# ---------- 纯函数：成本代理（审核高优 5） ----------

def cost_metrics(per_case_chars: list, repeats: int = 3) -> dict:
    """成本代理（设计 §5.2.7 首类指标）：API 不返回 token usage，用 prompt 字符数 × 调用数 × repeats。
    vote5 = 5 调用/题/轮；single@T 与 anchor 各 1 调用/题/轮。
    v3 中优 5：arm_total_chars 乘 repeats，键名改 arm_total_chars_per_run。"""
    total = sum(per_case_chars)
    totals = {"vote5": total * N_SAMPLES * repeats, "single_t": total * repeats,
              "anchor": total * repeats}
    return {"metric": "prompt_chars_proxy",
            "note": "API 未返回 token usage；prompt 字符数 × 调用数 × repeats 为成本代理",
            "per_case_chars_trimmed_mean": round(trimmed_mean(per_case_chars, 0.1), 1),
            "arm_total_chars_per_run": totals,
            "cost_ratio_vote5_vs_single_t": round(totals["vote5"] / max(totals["single_t"], 1), 2),
            "cost_ratio_vote5_vs_anchor": round(totals["vote5"] / max(totals["anchor"], 1), 2)}


def _prompt_chars_per_case(enriched_rows: list) -> list:
    out = []
    for row in enriched_rows:
        rendered = render_chart_context(row, SCHEMA)
        out.append(len(format_direct_choice_prompt(row, chart_context_text=rendered)))
    return out


# ---------- 纯函数：dev 温度自动读取（审核阻断 3） ----------

def load_dev_temperature(dev_run_id: str, archive_dir: Path, provider: str, model: str,
                         approved_2024_dataset_sha: str | None = None) -> tuple:
    """复核温度来源（v4 高优 5 + v5 高优 4）：从已归档 dev manifest/summary 自动读取并核验，
    禁止人工转录。返回 (temperature, info)。archive_dir = PROJECT_ROOT/docs/phase6。
    v5 高优 4：approved_2024_dataset_sha 由 main 强制从 enrich_manifest 读取传入。
    v10 偏差（按计划测试锁定）：完整归档（write_report + 审计索引产物）全项核验——
    status/year/recheck/run_id/temperature_freeze/dataset SHA/audit_index 存在即必查
    （temperature_freeze 块存在时 sample_temperature 必存且一致，v6 高优 4 不静默跳过）；
    最小归档（仅 manifest+summary 四配置字段，见 TestDevRunId）只核验
    verdict/profile/schema/provider/model/温度合法性。"""
    d = Path(archive_dir) / dev_run_id
    for name in ("manifest.json", "summary.json"):
        if not (d / name).exists():
            raise ValueError(f"dev 归档缺失：{d / name}")
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    if summary.get("verdict") != "PROMOTE_CANDIDATE":
        raise ValueError(f"dev verdict 非 PROMOTE_CANDIDATE：{summary.get('verdict')}")
    if "status" in summary and summary.get("status") != "OK":
        raise ValueError(f"dev summary status 非 OK：{summary.get('status')}")
    if "year" in summary and summary.get("year") != 2024:
        raise ValueError(f"dev summary year 非 2024：{summary.get('year')}")
    if "recheck" in summary and summary.get("recheck") is not False:
        raise ValueError(f"dev summary recheck 非 false：{summary.get('recheck')}")
    if manifest.get("run_id") is not None and manifest.get("run_id") != dev_run_id:
        raise ValueError(f"dev manifest run_id 不一致：{manifest.get('run_id')} != {dev_run_id}")
    for k, expect in (("profile_id", PROFILE_ID), ("chart_schema_version", SCHEMA),
                      ("provider", provider), ("model", model)):
        if manifest.get(k) != expect:
            raise ValueError(f"dev manifest {k} 不一致：{manifest.get(k)} != {expect}")
    temperature = float(manifest["sample_temperature"])
    if temperature not in (DEFAULT_T, FALLBACK_T):
        raise ValueError(f"dev 温度非法 {temperature}，只能 {DEFAULT_T} 或 {FALLBACK_T}")
    tfreeze = manifest.get("temperature_freeze")
    if tfreeze is not None:
        # v6 高优 4：sample_temperature 必存且一致（块内不允许静默通过）
        if "sample_temperature" not in tfreeze:
            raise ValueError(f"dev temperature_freeze 缺 sample_temperature 字段")
        if abs(float(tfreeze["sample_temperature"]) - temperature) > 0.001:
            raise ValueError(f"temperature_freeze.sample_temperature({tfreeze['sample_temperature']})"
                             f" 与 sample_temperature({temperature}) 不一致")
    dataset_sha = manifest.get("dataset_sha256")
    if approved_2024_dataset_sha and dataset_sha != approved_2024_dataset_sha:
        raise ValueError(f"dataset SHA 与已批准 2024 enriched manifest 不对应")
    audit_index = d / "audit_index.json"
    if audit_index.exists():
        ai = json.loads(audit_index.read_text(encoding="utf-8"))
        if ai.get("mode") != "vote":
            raise ValueError(f"dev 审计索引 mode 非 vote：{ai.get('mode')}")
        sc = ai.get("summary_check", {})
        if sc.get("status") != "PASS":
            raise ValueError(f"dev 审计 summary_check 非 PASS：{sc.get('status')}")
        # v6 高优 5：summary_sha256 绑定当前 summary.json 内容（审计后修改 summary 会被发现）
        summary_sha = sha256_file(d / "summary.json")
        if sc.get("summary_sha256") != summary_sha:
            raise ValueError(f"dev 审计 summary_sha256 与当前 summary.json 不一致")
        # v6 高优 5：recomputed 的 Δ1/Δ2 与当前 summary 一致
        recomputed = sc.get("recomputed", {})
        if abs(float(recomputed.get("delta1_pp", 0)) - float(summary.get("delta1_pp", 0))) > 0.01:
            raise ValueError(f"dev 审计 recomputed Δ1 与 summary 不一致")
        if abs(float(recomputed.get("delta2_pp", 0)) - float(summary.get("delta2_pp", 0))) > 0.01:
            raise ValueError(f"dev 审计 recomputed Δ2 与 summary 不一致")
        if dataset_sha is not None and ai.get("dataset_sha256") != dataset_sha:
            raise ValueError(f"dev 审计索引 dataset_sha256 不一致")
        if ai.get("run_id") is not None and ai.get("run_id") != dev_run_id:
            raise ValueError(f"dev 审计索引 run_id 不一致：{ai.get('run_id')}")
        if ai.get("year") is not None and ai.get("year") != 2024:
            raise ValueError(f"dev 审计索引 year 非 2024：{ai.get('year')}")
    info = {"verdict": summary["verdict"], "dev_run_id": dev_run_id,
            "dev_manifest_sha256": sha256_file(d / "manifest.json"),
            "dataset_sha256": dataset_sha, "temperature": temperature}
    return temperature, info


# ---------- 离线 gate / 真实边界 ----------

def offline_gate(config: VoteConfig) -> list:
    """legacy_v0 单上下文：可见性矩阵 + 泄漏扫描（无网络）。"""
    failures = []
    if not config.enriched_path.exists():
        return [f"enriched 文件缺失: {config.enriched_path}"]
    profile = resolve_profile(PROFILE_ID, SCHEMA)
    for row in load_jsonl(config.enriched_path):
        cid = row.get("case_id")
        rendered = render_chart_context(row, SCHEMA)
        for v in assert_visibility(rendered, profile, SCHEMA):
            failures.append(f"{cid}: {v}")
        prompt = format_direct_choice_prompt(row, chart_context_text=rendered)
        for hit in scan_prompt_for_leaks(prompt, row):
            failures.append(f"{cid}: leak {hit.kind} {hit.detail}")
    return failures


def run_slice(slice_run: VoteSlice, config: VoteConfig, **kwargs) -> object:
    """真实边界：子进程调用 runner（emit_samples / 单轮锚定）。--repeat-idx 原样透传。"""
    run_dir = (config.root / slice_run.arm / "runs" / config.run_id
               / f"slice_{slice_run.purpose}_{slice_run.repeat_idx}_{slice_run.group}")
    run_dir.mkdir(parents=True, exist_ok=True)
    ids_file = run_dir / "case_ids.json"
    ids_file.write_text(json.dumps(list(slice_run.case_ids), ensure_ascii=False),
                        encoding="utf-8")
    argv = [
        sys.executable, "-m", "benchmark.runners.run_benchmark",
        "--dataset", str(config.enriched_path),
        "--model-runner", "--provider", config.provider, "--model", config.model,
        "--profile", PROFILE_ID, "--chart-schema-version", SCHEMA,
        "--arm", slice_run.arm, "--attempt-stage", slice_run.stage,
        "--as-of-date", config.as_of_date,               # v6 高优 7
        "--repeat-idx", str(slice_run.repeat_idx),
        "--case-ids-file", str(ids_file),
        "--case-details-jsonl", str(run_dir / "detail.jsonl"),
        "--output-dir", str(run_dir),
        "--scheduled-calls", str(slice_run.scheduled_calls),
        "--hard-cap", str(slice_run.hard_cap),
        "--temperature", "0.0",
        "--n-samples", str(slice_run.n_samples),
        "--sample-temperature", str(slice_run.temperature),
    ]
    if slice_run.n_samples > 1:
        argv += ["--aggregate", "emit_samples"]
    if config.resume:
        argv.append("--resume")
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=PROJECT_ROOT)
    calls_attempted = 0
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        try:
            calls_attempted = int(json.loads(summary_path.read_text(encoding="utf-8"))
                                  .get("calls_attempted") or 0)
        except Exception:
            calls_attempted = 0
    if not calls_attempted:
        events_path = run_dir / "detail.events.jsonl"
        if events_path.exists():
            calls_attempted = sum(
                1 for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line).get("kind") == "call_attempt")
    return type("SliceResult", (), {"exit_code": proc.returncode, "records": [],
                                    "calls_attempted": calls_attempted,
                                    "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]})


def run_vote(config: VoteConfig, schedule: list, slice_runner=None) -> dict:
    """与 6A0 run_ablation 同语义：schedule 调用方传入；BudgetLedger 按 slice_id 幂等。"""
    runner = slice_runner or (lambda s, **kw: run_slice(s, config, **kw))
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    for s in schedule:
        slice_id = f"{s.purpose}_{s.repeat_idx}_{s.arm}_{s.group}"
        try:
            attempted = ledger.attempted_for(slice_id)
            overflow = (ledger.total_attempted() + (s.hard_cap - attempted)
                        > config.stage_hard_cap)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if attempted > s.hard_cap:
            return {"status": "BLOCKED_INCOMPLETE",
                    "reason": f"budget ledger inconsistent: {slice_id}"}
        if overflow:
            return {"status": "FAILED",
                    "reason": f"stage budget overflow at {slice_id}",
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx, "group": s.group}}
        result = runner(s, scheduled_calls=s.scheduled_calls, hard_cap=s.hard_cap)
        try:
            ledger.record(slice_id, s.hard_cap, getattr(result, "calls_attempted", 0) or 0)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if result.exit_code == 3:
            return {"status": "BLOCKED_INCOMPLETE",
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx, "group": s.group}}
        if result.exit_code != 0:
            return {"status": "FAILED", "exit_code": result.exit_code,
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx}}
    return {"status": "OK", "attempted": ledger.total_attempted()}


def _load_run_rows(config: VoteConfig) -> list:
    rows = []
    for arm in (ARM_SAMPLE, ARM_ANCHOR):
        runs_dir = config.root / arm / "runs" / config.run_id
        if not runs_dir.exists():
            continue
        for detail in sorted(runs_dir.glob("slice_main_*/detail.jsonl")):
            for line in detail.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def _build_manifest(config: VoteConfig, executed_schedule: list, attempted: int,
                    temperature: float, probe_info: dict, case_ids: list,
                    dataset_sha256: str, groups_sha256: str,
                    dev_dataset_sha256: str = "") -> dict:
    """v3 阻断 3：manifest 构造纯函数（不读磁盘，便于测试）。
    executed_schedule 含 probe（[probe_r1, optional probe_r2, *main]），
    budget_reconciliation 分别记录 probe/main scheduled、attempted_total、registered_hard_cap。
    v6 阻断 1：dev_dataset_sha256 记录 2024 批准 SHA（复核模式才非空）。"""
    probe_scheduled = sum(s.scheduled_calls for s in executed_schedule
                         if getattr(s, "group", "") == "probe")
    main_scheduled = sum(s.scheduled_calls for s in executed_schedule
                         if getattr(s, "group", "") != "probe")
    return {
        "run_id": config.run_id, "seed": config.seed, "profile_id": PROFILE_ID,
        "chart_schema_version": SCHEMA, "sample_temperature": temperature,
        "as_of_date": config.as_of_date,
        "temperature_freeze": probe_info,
        "dataset_sha256": dataset_sha256,
        "dev_dataset_sha256": dev_dataset_sha256 or dataset_sha256,  # v6 阻断 1
        "case_groups_sha256": groups_sha256,
        "slice_order": [f"{s.arm}:{s.repeat_idx}:{s.group}" for s in executed_schedule],
        "budget_reconciliation": {
            "probe_scheduled": probe_scheduled,
            "main_scheduled": main_scheduled,
            "scheduled_total": probe_scheduled + main_scheduled,
            "attempted_total": attempted,
            "registered_hard_cap": config.stage_hard_cap,
        },
        "provider": config.provider, "model": config.model, "code_hash": _git_head(),
        "workspace_state": _collect_workspace_state(),
        "reproducibility_note": "请求不携带 seed；复现依赖 detail 行 raw_answer 与调用顺序",
    }


def write_report(config: VoteConfig, case_ids: list, temperature: float,
                 probe_info: dict, executed_schedule: list, enriched_rows: list,
                 attempted: int, recheck: bool = False) -> dict:
    """首类指标全量产出（v3 中优 5）：准确率/Δ/四格/unresolved/成本/逐题明细/对账/
    acc_trimmed_mean/by_domain。executed_schedule 含 probe（v3 阻断 3）。"""
    rows = _load_run_rows(config)
    try:
        m = aggregate_metrics(rows, case_ids, config.repeats)
    except ValueError as e:
        return {"run_id": config.run_id, "status": "BLOCKED_INCOMPLETE",
                "reason": f"完整性检查未过：{e}"}
    verdict = (recheck_verdict(m["delta1_pp"], m["delta2_pp"]) if recheck
               else gate_verdict(m["delta1_pp"], m["delta2_pp"]))
    pollution = m["call_failed"] > len(case_ids) * 0.05
    cost = cost_metrics(_prompt_chars_per_case(enriched_rows), repeats=config.repeats)
    out_dir = ARCHIVE_ROOT / config.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"run_id": config.run_id, "year": config.year, "status": "OK",
               "sample_temperature": temperature, "recheck": recheck,
               **{k: v for k, v in m.items() if k != "case_records"},
               "cost": cost, "verdict": verdict, "pollution_flag": pollution,
               "stage_hard_cap": config.stage_hard_cap}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    with (out_dir / "case_details.jsonl").open("w", encoding="utf-8") as f:
        for rec in m["case_records"]:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    group_a, group_b = split_ab_ba(case_ids, config.seed)
    groups_sha256 = sha256_file(_write_tmp_json(config.root / "budget"
                                                / f"{config.run_id}_groups.json",
                                                {"group_a": list(group_a),
                                                 "group_b": list(group_b)}))
    manifest = _build_manifest(config, executed_schedule, attempted, temperature,
                               probe_info, case_ids,
                               dataset_sha256=sha256_file(config.enriched_path),
                               groups_sha256=groups_sha256,
                               dev_dataset_sha256=config.dev_dataset_sha256)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    lines = [
        f"# 6A1 严格投票报告（{config.run_id}，{config.year}{'，2021 复核' if recheck else ''}）",
        "",
        f"- T = {temperature}（冻结链：{json.dumps(probe_info, ensure_ascii=False)}）",
        f"- Δ1（vote5−single@T，同源）= {m['delta1_pp']}pp（每 repeat：{m['per_repeat_delta1']}）",
        f"- Δ2（vote5−single@0，锚定）= {m['delta2_pp']}pp（每 repeat：{m['per_repeat_delta2']}）",
        f"- 准确率 vote5/single@T/anchor：{m['acc']['vote5']} / {m['acc']['single_t']} / {m['acc']['anchor']}",
        f"- unresolved 率：{m['unresolved_rate']}（>20% 为显著发现，不否决）",
        f"- 四格 vote5×single@T：{json.dumps(m['four_grid_vote5_vs_single_t'], ensure_ascii=False)}",
        f"- 四格 vote5×anchor：{json.dumps(m['four_grid_vote5_vs_anchor'], ensure_ascii=False)}",
        f"- 成本代理（{cost['metric']}）：vote5/single@T/anchor 总字符 = "
        f"{cost['arm_total_chars_per_run']}；比值 {cost['cost_ratio_vote5_vs_single_t']} / "
        f"{cost['cost_ratio_vote5_vs_anchor']}；trimmed mean {cost['per_case_chars_trimmed_mean']}",
        f"- 准确率 trimmed mean（附列，不入 gate）：{m['acc_trimmed_mean']}",
        f"- by_domain（设计 §2.1）：{json.dumps(m['by_domain'], ensure_ascii=False)}",
        f"- call_failed：{m['call_failed']}（污染标注：{'是' if pollution else '否'}）",
        f"- 判定：**{verdict}**",
        "",
        "如实声明：API 未返回 token usage（成本为 prompt 字符 × 调用数代理）；采样不可由 seed 复现；"
        "40 题样本，2 题即 5pp，禁止过度表述。逐题明细见 case_details.jsonl。",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def _write_tmp_json(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 6A1 严格投票编排器")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--root", type=Path, default=Path(".tmp/phase6"))
    parser.add_argument("--recheck", action="store_true",
                        help="2021 复核模式：无 probe，必须 --dev-run-id")
    parser.add_argument("--dev-run-id", default=None,
                        help="复核模式必填：dev 运行归档（docs/phase6/<id>/）")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="v6 高优 6：允许实验范围文件 dirty（仅诊断，正式命令禁止）")
    args = parser.parse_args(argv)

    # v7 高优 5：--allow-dirty 与 --yes 互斥（allow-dirty 只能离线诊断，不进模型调用路径）
    if args.allow_dirty and args.yes:
        parser.error("--allow-dirty cannot be combined with --yes")

    # v6 高优 6：workspace clean 在任何 API 调用前检查（采集失败也 fail-closed）
    if not args.allow_dirty:
        workspace = _collect_workspace_state()
        if "collect_error" in workspace or not workspace.get("clean"):
            print(json.dumps({"status": "WORKSPACE_DIRTY", "workspace": workspace},
                             ensure_ascii=False))
            return 2

    # 年份封死（审核阻断 3）：先于任何数据读取。dev 仅 2024；复核仅 2021；2022/2023 密封。
    if args.recheck and args.year != 2021:
        print("复核模式仅允许 --year 2021（2022/2023 密封，设计 §5.3）")
        return 2
    if not args.recheck and args.year != 2024:
        print("dev 模式仅允许 --year 2024（2022/2023 密封，设计 §5.3）")
        return 2

    enriched = args.root / "datasets" / f"baziqa_contest8_{args.year}_holdout_enriched.jsonl"
    hard_cap = 800 if args.recheck else 910
    # v5 阻断 3 + v6 阻断 1：从 enrich_manifest.json 读取 current_entry(args.year) 与 dev_entry(2024)
    if not enriched.is_file():                       # v6 高优 3：前置存在检查
        print(json.dumps({"status": "ENRICHED_MISSING", "path": str(enriched)},
                         ensure_ascii=False))
        return 2
    enrich_manifest = args.root / "enrich_manifest.json"
    if not enrich_manifest.exists():
        print(json.dumps({"status": "ENRICH_MANIFEST_MISSING",
                          "path": str(enrich_manifest)}, ensure_ascii=False))
        return 2
    em = json.loads(enrich_manifest.read_text(encoding="utf-8"))
    current_entry = next((e for e in em.get("entries", []) if e.get("year") == args.year), None)
    if not current_entry:
        print(json.dumps({"status": "ENRICH_ENTRY_MISSING", "year": args.year},
                         ensure_ascii=False))
        return 2
    dev_entry = next((e for e in em.get("entries", []) if e.get("year") == 2024), None)
    if not dev_entry:                                 # v6 阻断 1：dev_entry 必须存在（复核模式用）
        print(json.dumps({"status": "DEV_ENTRY_MISSING"}, ensure_ascii=False))
        return 2
    # v7 高优 4 + v8 阻断/高优 1：先取顶层 as_of_date，传入 validate_enrichment_entry
    top_as_of_date = em.get("as_of_date", "")
    if not top_as_of_date:
        print(json.dumps({"status": "TOP_AS_OF_DATE_EMPTY"}, ensure_ascii=False))
        return 2
    try:
        current_sha = validate_enrichment_entry(current_entry, enriched, args.year, top_as_of_date)
        if args.year == 2024:
            dev_sha = current_sha                     # 开发年度相同，复用结果
        else:
            dev_enriched = args.root / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
            dev_sha = validate_enrichment_entry(dev_entry, dev_enriched, 2024, top_as_of_date)
    except ValueError as e:
        print(json.dumps({"status": "ENRICH_ENTRY_INVALID", "reason": str(e)},
                         ensure_ascii=False))
        return 2
    as_of_date = top_as_of_date                       # v8 高优 1：顶层日期已在 entry 校验绑定
    # v6 阻断 1：approved_2024_dataset_sha 始终取 dev_entry(2024)，不用 current_entry
    approved_dataset_sha = dev_sha
    config = VoteConfig(run_id=args.run_id, year=args.year, root=args.root,
                        enriched_path=enriched, provider=args.provider,
                        model=args.model, stage_hard_cap=hard_cap,
                        as_of_date=as_of_date,
                        dev_dataset_sha256=approved_dataset_sha)
    failures = offline_gate(config)
    if failures:
        print(json.dumps({"status": "OFFLINE_GATE_FAILED", "failures": failures[:20]},
                         ensure_ascii=False))
        return 1
    enriched_rows = list(load_jsonl(enriched))
    case_ids = [str(r["case_id"]) for r in enriched_rows]
    try:
        validate_case_ids(case_ids)
    except ValueError as e:
        print(json.dumps({"status": "INVALID_CASE_IDS", "reason": str(e)},
                         ensure_ascii=False))
        return 2
    group_a, _ = split_ab_ba(case_ids, config.seed)
    probe_slices = []

    probe_info = {"mode": "recheck" if args.recheck else "dev"}
    if args.recheck:
        if not args.dev_run_id:
            print("复核模式必须 --dev-run-id（从 dev 归档自动读取温度，禁止人工转录）")
            return 2
        try:
            temperature, info = load_dev_temperature(
                args.dev_run_id, archive_dir=ARCHIVE_ROOT,
                provider=config.provider, model=config.model,
                approved_2024_dataset_sha=approved_dataset_sha)
        except ValueError as e:
            print(str(e))
            return 2
        probe_info.update(info)
    else:
        r1 = build_probe_slice(config, group_a, "probe_r1", DEFAULT_T)
        print(f"probe_r1：{r1.scheduled_calls} 次调用（cap {r1.hard_cap}）")
        if not args.yes:
            print("加 --yes 确认预算后执行")
            return 0
        result = run_vote(config, [r1])
        probe_slices.append(r1)
        if result["status"] != "OK":
            print(json.dumps(result, ensure_ascii=False))
            return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
        r1_rows = []
        for detail in (config.root / "probe_r1" / "runs" / config.run_id
                       ).glob("slice_probe_*/detail.jsonl"):
            r1_rows += [json.loads(x) for x in
                        detail.read_text(encoding="utf-8").splitlines() if x.strip()]
        try:
            probe_rows_complete(r1_rows, list(group_a[:PROBE_CASES]), "probe_r1")
        except ValueError as e:
            print(json.dumps({"status": "BLOCKED_INCOMPLETE", "reason": str(e)},
                             ensure_ascii=False))
            return 3
        rate1 = diversity_rate(r1_rows, list(group_a[:PROBE_CASES]))
        action, temperature = evaluate_t_switch(rate1, None)
        probe_info.update({"rate_r1": rate1, "action_r1": action})
        if action == "probe_r2":
            r2 = build_probe_slice(config, group_a, "probe_r2", FALLBACK_T)
            result = run_vote(config, [r2])
            probe_slices.append(r2)
            if result["status"] != "OK":
                print(json.dumps(result, ensure_ascii=False))
                return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
            r2_rows = []
            for detail in (config.root / "probe_r2" / "runs" / config.run_id
                           ).glob("slice_probe_*/detail.jsonl"):
                r2_rows += [json.loads(x) for x in
                            detail.read_text(encoding="utf-8").splitlines() if x.strip()]
            try:
                probe_rows_complete(r2_rows, list(group_a[:PROBE_CASES]), "probe_r2")
            except ValueError as e:
                print(json.dumps({"status": "BLOCKED_INCOMPLETE", "reason": str(e)},
                                 ensure_ascii=False))
                return 3
            rate2 = diversity_rate(r2_rows, list(group_a[:PROBE_CASES]))
            action, temperature = evaluate_t_switch(rate1, rate2)
            probe_info.update({"rate_r2": rate2, "action_r2": action})
        print(f"T 冻结为 {temperature}（{probe_info}）")
    probe_info = freeze_temperature(probe_info, temperature)      # v8 高优 2：纯函数抽取

    schedule = build_main_schedule(config, case_ids, sample_temperature=temperature)
    executed_schedule = [*probe_slices, *schedule]
    total = sum(s.scheduled_calls for s in executed_schedule)
    print(f"主实验：{total} 次调用（cap {sum(s.hard_cap for s in executed_schedule)}），"
          f"切片 {len(executed_schedule)}，T={temperature}")
    if not args.yes:
        print("加 --yes 确认预算后执行")
        return 0
    result = run_vote(config, schedule)
    if result["status"] != "OK":
        print(json.dumps(result, ensure_ascii=False))
        return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
    summary = write_report(config, case_ids, temperature, probe_info,
                           executed_schedule, enriched_rows,
                           attempted=result.get("attempted", 0), recheck=args.recheck)
    if summary.get("status") == "BLOCKED_INCOMPLETE":
        print(json.dumps(summary, ensure_ascii=False))
        return 3
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
