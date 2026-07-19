"""Phase 6 6A0 编排器：离线 gate、AB/BA 12 切片调度、双列预算接线、Δ 与判定、报告。

决策逻辑均为无网络纯函数（可单测）；真实模型调用仅经 run_slice 子进程边界发起。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.baziqa_prompt import format_direct_choice_prompt
from benchmark.formatters.chart_context import (
    CHART_CONTEXT_TEMPLATE_VERSION,
    approved_field_presence,
    render_chart_context,
)
from benchmark.formatters.leak_scan import scan_prompt_for_leaks
from benchmark.runners.profiles import assert_visibility, resolve_profile
from scripts.enrich_baziqa_chart_input import load_jsonl

ARMS = ("ctx_approved", "ctx_legacy")
ARM_SCHEMA = {"ctx_approved": "approved_v1", "ctx_legacy": "legacy_v0"}
SLICE_ORDER = (("ctx_approved", "group_a"), ("ctx_legacy", "group_a"),
               ("ctx_legacy", "group_b"), ("ctx_approved", "group_b"))
SLICE_CAPS = (23, 23, 22, 22)
PROFILE_ID = "baziqa_xjz_direct"
EXPECTED_CASES = 40


@dataclass(frozen=True)
class AblationConfig:
    run_id: str
    year: int
    root: Path
    enriched_path: Path
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    repeats: int = 3
    smoke_size: int = 20
    seed: int = 20260717
    as_of_date: str = "2026-07-17"
    stage_scheduled: int = 260
    stage_hard_cap: int = 290
    resume: bool = True


@dataclass(frozen=True)
class SliceRun:
    purpose: str                 # "smoke" | "main"
    repeat_idx: int              # smoke 固定 -1
    arm: str                     # "ctx_approved" | "ctx_legacy"
    group: str                   # "group_a" | "group_b" | "smoke"
    case_ids: tuple[str, ...]
    scheduled_calls: int
    hard_cap: int


def split_ab_ba(case_ids: list[str], seed: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids = list(case_ids)
    random.Random(seed).shuffle(ids)
    half = len(ids) // 2
    return tuple(ids[:half]), tuple(ids[half:])


def build_schedule(config: AblationConfig, case_ids: list[str]) -> list[SliceRun]:
    if len(case_ids) != EXPECTED_CASES:
        raise ValueError(f"6A0 dev gate 要求 {EXPECTED_CASES} 题，实得 {len(case_ids)}")
    group_a, group_b = split_ab_ba(case_ids, config.seed)
    schedule = [SliceRun("smoke", -1, "ctx_approved", "smoke", group_a, config.smoke_size,
                         config.smoke_size)]
    groups = {"group_a": group_a, "group_b": group_b}
    for repeat in range(config.repeats):
        for (arm, group), cap in zip(SLICE_ORDER, SLICE_CAPS):
            schedule.append(SliceRun("main", repeat, arm, group, groups[group],
                                     config.smoke_size, cap))
    total_cap = sum(s.hard_cap for s in schedule)
    if total_cap != config.stage_hard_cap:
        raise ValueError(f"切片 cap 和 {total_cap} != 阶段 hard_cap {config.stage_hard_cap}")
    return schedule


def gate_verdict(delta_pp: float) -> str:
    if delta_pp >= 2.0:
        return "ADOPT"
    if delta_pp >= 0.0:
        return "ADOPT_FOUNDATION"
    return "ROLLBACK"


def aggregate_delta(rows: list[dict], repeats: int) -> dict:
    def accuracy(arm: str, repeat: int) -> float:
        # repeat ∈ range(repeats)；smoke 行 repeat_idx=-1 被 == 比较天然排除，不进主指标
        sel = [r for r in rows
               if r.get("arm") == arm and int(r.get("repeat_idx", -1)) == repeat]
        if not sel:
            raise ValueError(f"缺数据：arm={arm} repeat={repeat}")
        return sum(1 for r in sel if r.get("correct")) / len(sel)

    per_repeat = []
    for repeat in range(repeats):
        per_repeat.append(round((accuracy("ctx_approved", repeat)
                                 - accuracy("ctx_legacy", repeat)) * 100, 2))
    delta_dev = round(sum(per_repeat) / len(per_repeat), 2)
    return {
        "per_repeat_delta_pp": per_repeat,
        "delta_dev_pp": delta_dev,
        "verdict": gate_verdict(delta_dev),
        "call_failed": sum(1 for r in rows if r.get("terminal_state") == "call_failed"),
    }


def offline_gate(config: AblationConfig) -> list[str]:
    """无网络离线 gate：批准字段 presence、可见性矩阵、泄漏扫描。返回失败列表（空=通过）。"""
    failures: list[str] = []
    if not config.enriched_path.exists():
        return [f"enriched 文件缺失: {config.enriched_path}（先运行 Task 3 enrichment）"]
    rows = load_jsonl(config.enriched_path)
    for row in rows:
        cid = row.get("case_id")
        presence = approved_field_presence(row.get("chart_input") or {})
        missing = [k for k, ok in presence.items() if not ok]
        if missing:
            failures.append(f"{cid}: 批准字段缺失 {missing}")
            continue
        for arm, schema in ARM_SCHEMA.items():
            rendered = render_chart_context(row, schema, as_of_date=config.as_of_date)
            arm_profile = resolve_profile(PROFILE_ID, schema)
            for v in assert_visibility(rendered, arm_profile, schema):
                failures.append(f"{cid}/{arm}: {v}")
            prompt = format_direct_choice_prompt(row, chart_context_text=rendered)
            for hit in scan_prompt_for_leaks(prompt, row):
                failures.append(f"{cid}/{arm}: leak {hit.kind} {hit.detail}")
    return failures


def run_slice(slice_run: SliceRun, config: AblationConfig, **kwargs) -> object:
    """真实边界：子进程调用 runner。测试中以 RunnerSpy 替换。

    每切片独立目录 slice_{purpose}_{repeat}_{group}/（detail/events/summary 均在其中），
    --repeat-idx 原样透传（smoke 为 -1，禁止 max 修正——否则与 repeat 0 键碰撞）。
    """
    run_dir = (config.root / slice_run.arm / "runs" / config.run_id
               / f"slice_{slice_run.purpose}_{slice_run.repeat_idx}_{slice_run.group}")
    run_dir.mkdir(parents=True, exist_ok=True)
    ids_file = run_dir / "case_ids.json"
    ids_file.write_text(json.dumps(list(slice_run.case_ids), ensure_ascii=False),
                        encoding="utf-8")
    detail_path = run_dir / "detail.jsonl"
    argv = [
        sys.executable, "-m", "benchmark.runners.run_benchmark",
        "--dataset", str(config.enriched_path),
        "--model-runner", "--provider", config.provider, "--model", config.model,
        "--profile", PROFILE_ID,
        "--chart-schema-version", ARM_SCHEMA[slice_run.arm],
        "--arm", slice_run.arm,
        "--repeat-idx", str(slice_run.repeat_idx),
        "--case-ids-file", str(ids_file),
        "--case-details-jsonl", str(detail_path),
        "--output-dir", str(run_dir),
        "--scheduled-calls", str(slice_run.scheduled_calls),
        "--hard-cap", str(slice_run.hard_cap),
    ]
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
        # 崩溃路径：summary 缺失/为 0 时以事件日志为准（call_attempt 含成功与失败调用）
        events_path = run_dir / "detail.events.jsonl"
        if events_path.exists():
            calls_attempted = sum(
                1 for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line).get("kind") == "call_attempt")
    return type("ArmRunResult", (), {"exit_code": proc.returncode, "records": [],
                                     "calls_attempted": calls_attempted,
                                     "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]})


class BudgetLedgerCorrupt(Exception):
    """预算账本损坏：JSON 坏/结构错/非 int/负值/calls_attempted > hard_cap——一律 fail-closed。"""


class BudgetLedger:
    """阶段总预算账本（config.root/budget/<run_id>.jsonl）：**按 slice_id 幂等 + fail-closed**。

    JSON dict 存储 slice_id → {"calls_attempted", "hard_cap", "timestamp"}。
    runner 的 calls_attempted 是切片级累计值（resume 时从事件恢复），因此同一切片
    重复完成时**覆盖**而非追加——smoke-only 后接全量不会把 smoke 记成两倍。
    record 取 max(旧值, 新值)：崩溃等异常路径 summary 缺失时账本不回退。
    **fail-closed**：账本 JSON 损坏、结构错误、非 int、负值、calls_attempted > hard_cap
    一律抛 BudgetLedgerCorrupt（run_ablation 转 BLOCKED_INCOMPLETE）——预算是安全约束，
    损坏时宁可停工也不静默放行。写入经临时文件 + os.replace 原子替换，中断不留半文件。
    正常运行下各切片 cap 和 == 阶段 hard_cap，启动前检查永不触发。
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    @staticmethod
    def _validate(data: dict) -> dict:
        if not isinstance(data, dict):
            raise BudgetLedgerCorrupt("账本顶层结构非 dict")
        for slice_id, row in data.items():
            if not isinstance(row, dict):
                raise BudgetLedgerCorrupt(f"{slice_id}: 记录非 dict")
            calls, cap = row.get("calls_attempted"), row.get("hard_cap")
            if not isinstance(calls, int) or not isinstance(cap, int):
                raise BudgetLedgerCorrupt(f"{slice_id}: calls_attempted/hard_cap 非 int")
            if calls < 0 or cap < 0:
                raise BudgetLedgerCorrupt(f"{slice_id}: 负值 calls={calls} cap={cap}")
            if calls > cap:
                raise BudgetLedgerCorrupt(
                    f"{slice_id}: calls_attempted {calls} > hard_cap {cap}")
        return data

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except BudgetLedgerCorrupt:
            raise
        except Exception as exc:
            raise BudgetLedgerCorrupt(f"账本 JSON 损坏: {self.path}: {exc}") from exc
        return self._validate(data)

    def total_attempted(self) -> int:
        return sum(int(v["calls_attempted"]) for v in self._load().values())

    def attempted_for(self, slice_id: str) -> int:
        return int((self._load().get(slice_id) or {}).get("calls_attempted") or 0)

    def record(self, slice_id: str, hard_cap: int, calls_attempted: int) -> None:
        data = self._load()
        prev = int((data.get(slice_id) or {}).get("calls_attempted") or 0)
        new_row = {"hard_cap": int(hard_cap),
                   "calls_attempted": max(prev, int(calls_attempted)),
                   "timestamp": datetime.now().isoformat(timespec="seconds")}
        self._validate({slice_id: new_row})   # 新值同样 fail-closed（runner 自报超 cap 即损坏）
        data[slice_id] = new_row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self.path) + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)            # 原子替换，中断不留半文件


def run_ablation(config: AblationConfig, schedule: list[SliceRun], slice_runner=None) -> dict:
    """执行**给定的** schedule（函数内不得重建——否则 main() 的 --smoke-only 过滤失效）。

    阶段预算经 BudgetLedger 按 slice_id 幂等累计；每切片启动前检查
    total + (hard_cap − 该切片已计)（已完成切片只按剩余额度预占，resume 不重复计），
    完成后按实际 calls_attempted 记账（含失败中止路径——已发起的调用必须入账）。
    账本损坏（BudgetLedgerCorrupt）或 schedule 与账本背离（remaining < 0）→
    BLOCKED_INCOMPLETE，fail-closed，不得进入决策。
    """
    runner = slice_runner or (lambda s, **kw: run_slice(s, config, **kw))
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    for slice_run in schedule:
        slice_id = f"{slice_run.purpose}_{slice_run.repeat_idx}_{slice_run.arm}_{slice_run.group}"
        try:
            attempted = ledger.attempted_for(slice_id)
            overflow = (ledger.total_attempted() + (slice_run.hard_cap - attempted)
                        > config.stage_hard_cap)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if attempted > slice_run.hard_cap:
            return {"status": "BLOCKED_INCOMPLETE",
                    "reason": f"budget ledger inconsistent: {slice_id} attempted {attempted} "
                              f"> slice hard_cap {slice_run.hard_cap}"}
        if overflow:
            return {"status": "FAILED",
                    "reason": f"stage budget overflow: attempted {ledger.total_attempted()} "
                              f"+ remaining cap {slice_run.hard_cap - attempted} ({slice_id}) "
                              f"> {config.stage_hard_cap}",
                    "abort_at": {"arm": slice_run.arm, "repeat_idx": slice_run.repeat_idx,
                                 "group": slice_run.group}}
        result = runner(slice_run, scheduled_calls=slice_run.scheduled_calls,
                        hard_cap=slice_run.hard_cap)
        try:
            ledger.record(slice_id, slice_run.hard_cap,
                          getattr(result, "calls_attempted", 0) or 0)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if result.exit_code == 3:
            return {"status": "BLOCKED_INCOMPLETE", "abort_at": {
                "arm": slice_run.arm, "repeat_idx": slice_run.repeat_idx,
                "group": slice_run.group}}
        if result.exit_code != 0:
            return {"status": "FAILED", "exit_code": result.exit_code,
                    "abort_at": {"arm": slice_run.arm, "repeat_idx": slice_run.repeat_idx}}
    return {"status": "OK"}


def cost_proxy(config: AblationConfig, rows: list[dict]) -> dict:
    """成本代理指标：各臂 prompt 字符数（API 不返回 token usage，如实标注）。"""
    out = {}
    by_id = {str(r.get("case_id")): r for r in rows}
    for arm, schema in ARM_SCHEMA.items():
        total = 0
        for row in by_id.values():
            rendered = render_chart_context(row, schema, as_of_date=config.as_of_date)
            total += len(format_direct_choice_prompt(row, chart_context_text=rendered))
        out[arm] = {"prompt_chars_total": total,
                    "prompt_chars_mean": round(total / max(len(by_id), 1))}
    return {"metric": "prompt_chars_proxy", "note": "API 未返回 token usage；字符数为成本代理", "arms": out}


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, cwd=PROJECT_ROOT).stdout.strip()
    except Exception:
        return "unknown"


def write_report(config: AblationConfig, case_ids: list[str]) -> dict:
    rows = []
    for arm in ARMS:
        runs_dir = config.root / arm / "runs" / config.run_id
        if not runs_dir.exists():
            continue
        for detail in sorted(runs_dir.glob("slice_*/detail.jsonl")):   # 每切片独立目录聚合
            for line in detail.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
    enriched_rows = load_jsonl(config.enriched_path)
    agg = aggregate_delta(rows, config.repeats)
    n_cases = len(case_ids)
    pollution = agg["call_failed"] > n_cases * 0.05
    out_dir = PROJECT_ROOT / "docs" / "phase6" / config.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"run_id": config.run_id, "year": config.year, "status": "OK",
               "as_of_date": config.as_of_date, **agg,
               "pollution_flag": pollution,
               "stage_scheduled": config.stage_scheduled,
               "stage_hard_cap": config.stage_hard_cap}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    manifest = {
        "run_id": config.run_id, "seed": config.seed, "as_of_date": config.as_of_date,
        "profile_id": PROFILE_ID, "template_version": CHART_CONTEXT_TEMPLATE_VERSION,
        "identity_strategy": "passthrough_pseudo_anonymized_dataset",
        "group_split": split_ab_ba(case_ids, config.seed),
        "slice_order": [f"{s.arm}:{s.group}:r{s.repeat_idx}" for s in build_schedule(config, case_ids)],
        "provider": config.provider, "model": config.model,
        "code_hash": _git_head(),
        "enriched_path": str(config.enriched_path),
        "reproducibility_note": "请求不携带 seed；复现依赖 detail 行 raw_answer 与调用顺序",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    proxy = cost_proxy(config, enriched_rows)
    lines = [
        f"# 6A0 上下文消融报告（{config.run_id}，{config.year}）",
        "",
        f"- Δ_dev = {agg['delta_dev_pp']}pp（每 repeat：{agg['per_repeat_delta_pp']}）",
        f"- 判定：**{agg['verdict']}**（≥+2 ADOPT；0≤Δ<+2 ADOPT_FOUNDATION；<0 ROLLBACK）",
        f"- call_failed：{agg['call_failed']}（{n_cases} 题；污染标注：{'是' if pollution else '否'}）",
        f"- 成本代理（prompt 字符数，非 token）：{json.dumps(proxy['arms'], ensure_ascii=False)}",
        "",
        "如实声明：API 未返回 token usage，成本对比为字符数代理；采样不可由 seed 复现。",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 6A0 上下文消融编排器")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--root", type=Path, default=Path(".tmp/phase6"))
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--yes", action="store_true", help="确认预算后发起真实模型调用")
    args = parser.parse_args(argv)

    enriched = args.root / "datasets" / f"baziqa_contest8_{args.year}_holdout_enriched.jsonl"
    config = AblationConfig(run_id=args.run_id, year=args.year, root=args.root,
                            enriched_path=enriched, provider=args.provider, model=args.model)
    failures = offline_gate(config)
    if failures:
        print(json.dumps({"status": "OFFLINE_GATE_FAILED", "failures": failures[:20]},
                         ensure_ascii=False))
        return 1
    case_ids = [str(r["case_id"]) for r in load_jsonl(enriched)]
    schedule = build_schedule(config, case_ids)
    if args.smoke_only:
        schedule = [s for s in schedule if s.purpose == "smoke"]
    total = sum(s.scheduled_calls for s in schedule)
    cap = sum(s.hard_cap for s in schedule)
    print(f"即将发起 {total} 次模型调用（hard_cap {cap}），切片数 {len(schedule)}")
    if not args.yes:
        print("加 --yes 确认预算后执行")
        return 0
    result = run_ablation(config, schedule)   # schedule 已按 --smoke-only 过滤；默认走 run_slice 子进程
    if result["status"] != "OK":
        print(json.dumps(result, ensure_ascii=False))
        return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
    if args.smoke_only:
        print(json.dumps({"status": "SMOKE_OK"}, ensure_ascii=False))
        return 0
    summary = write_report(config, case_ids)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
