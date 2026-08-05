#!/usr/bin/env python3
"""Phase 6 6B2 orchestrator - dual-system judge experiment protocol v18.

Implements Task 10-14, 16, 17b per APPROVED v18 plan.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import time
import types
import uuid
from collections import defaultdict
from pathlib import Path

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Task 10: Constants (frozen per spec §8) ──

FROZEN_DATE = "2026-07-17"
FROZEN_CHART_SCHEMA = "legacy_v0"
DEV_REUSE_HARD_CAP = 1060
FINAL_2023_HARD_CAP = 530
FINAL_2023_SCHEDULED = 480
B1A_SLICE_SCHEDULED = 8
B1A_SLICE_HARD_CAP = 10
DUAL_SLICE_SCHEDULED = 24
DUAL_SLICE_HARD_CAP = 26
GLOBAL_HARD_CAP = 1060
JUDGE_DISAGREEMENT_RATE = 0.579
SMOKE_CASES_PER_GROUP = 2
SMOKE_PARSER_RATE_MIN = 0.95

B1C_ARCHIVE_PATH = "docs/phase6/6b1/6b1-2026-07-17-deepseek-deepseek-chat-78481de6/merged_details.jsonl"
B1C_EXPECTED_SHA256 = "10e6b82f92fabd02b7e621b714d330a812f16e6b7aac7ad98adf4a0dd494eafa"
ARCHIVE_ROOT = "docs/phase6/6b2"


def _stage_hard_cap(years):
    years_set = set(years)
    if years_set == {"2023"}:
        return FINAL_2023_HARD_CAP
    return DEV_REUSE_HARD_CAP


# ── Task 10: _build_schedule (frozen 60-slice matrix) ──

def _build_schedule(output_dir, years=None, dataset_paths=None):
    """Build frozen schedule. Per-year independent dataset_paths; exact 40 unique case_ids required."""
    years = years or ["2024", "2025"]
    hard_cap = _stage_hard_cap(years)
    dataset_paths = dataset_paths or {}
    slices = []
    groups = [0, 1, 2, 3, 4]
    for year in years:
        ds_path = dataset_paths.get(year)
        if not ds_path or not os.path.exists(ds_path):
            raise SystemExit(f"_build_schedule 拒绝: {year} 数据集路径不存在或未指定 ({ds_path})")
        all_case_ids = []
        with open(ds_path, encoding="utf-8") as _f:
            for _line in _f:
                if _line.strip():
                    cid = json.loads(_line).get("case_id", "")
                    if cid:
                        all_case_ids.append(cid)
        if len(all_case_ids) != 40:
            raise SystemExit(f"_build_schedule 拒绝: {year} 数据集有 {len(all_case_ids)} 个 case_id，需要恰好 40")
        if len(set(all_case_ids)) != 40:
            raise SystemExit(f"_build_schedule 拒绝: {year} 数据集存在重复 case_id")
        for rep in [0, 1, 2]:
            for arm in ["b1a_prime", "dual"]:
                scheduled = B1A_SLICE_SCHEDULED if arm == "b1a_prime" else DUAL_SLICE_SCHEDULED
                per_group = 8
                for g in groups:
                    start = g * per_group
                    end = start + per_group
                    g_cases = all_case_ids[start:end]
                    if len(g_cases) != 8:
                        raise SystemExit(f"_build_schedule 拒绝: {year}/{arm}/g{g} 有 {len(g_cases)} 题，需要 8")
                    slice_id = f"{year}_{arm}_{rep}_g{g}"
                    out_dir = os.path.join(output_dir, slice_id)
                    slice_hard_cap = B1A_SLICE_HARD_CAP if arm == "b1a_prime" else DUAL_SLICE_HARD_CAP
                    slices.append({
                        "year": year, "repeat": rep, "arm": arm, "group": g,
                        "slice_id": slice_id, "output_dir": out_dir,
                        "detail_path": os.path.join(out_dir, "details.jsonl"),
                        "events_path": os.path.join(out_dir, "details.events.jsonl"),
                        "dataset_path": ds_path,
                        "case_ids_file": os.path.join(out_dir, "case_ids.json"),
                        "profile": "baziqa_xjz_reasoned" if arm == "b1a_prime" else "baziqa_xjz_dual",
                        "method": "direct_choice" if arm == "b1a_prime" else "dual_system",
                        "hard_cap": slice_hard_cap, "max_cases": 8,
                        "scheduled_calls": scheduled, "case_ids": g_cases,
                    })
    return {
        "slices": slices, "global_hard_cap": hard_cap,
        "total_scheduled_calls": sum(s["scheduled_calls"] for s in slices),
        "total_slices": len(slices),
    }


# ── Task 11: BudgetLedger6B2 (parameterized) ──

class BudgetLedger6B2:
    """Parameterized budget ledger. Idempotent record_slice_completed; per-arm range validation."""
    def __init__(self, ledger_path, global_hard_cap=1060, slice_min=8, slice_max=26):
        self.path = Path(ledger_path)
        self._init_hard_cap = global_hard_cap
        self.hard_cap = global_hard_cap
        self.slice_min = slice_min
        self.slice_max = slice_max
        self.total_attempted = 0
        self._completed = set()
        self.attempts_by_slice = {}
        self._load()

    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            file_hard_cap = data.get("hard_cap")
            if file_hard_cap is not None and file_hard_cap != self._init_hard_cap:
                raise SystemExit(f"BudgetLedger6B2 拒绝: 文件 hard_cap ({file_hard_cap}) != 实例化值 ({self._init_hard_cap})")
            self.total_attempted = data.get("total_attempted", 0)
            self._completed = set(data.get("completed_slices", []))
            self.attempts_by_slice = data.get("attempts_by_slice", {})
        else:
            self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "total_attempted": self.total_attempted,
            "completed_slices": sorted(self._completed),
            "attempts_by_slice": self.attempts_by_slice,
            "hard_cap": self.hard_cap,
        }, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(self.path))

    def record_slice_completed(self, slice_id, actual_attempts, arm="b1a_prime"):
        if slice_id in self._completed:
            return
        ARM_RANGES = {"b1a_prime": (8, 10), "dual": (16, 26)}
        arm_min, arm_max = ARM_RANGES.get(arm, (self.slice_min, self.slice_max))
        if not (arm_min <= actual_attempts <= arm_max):
            raise SystemExit(f"BudgetLedger6B2 拒绝: slice {slice_id} ({arm}) actual_attempts={actual_attempts} 不在 [{arm_min},{arm_max}] 范围内")
        if self.total_attempted + actual_attempts > self.hard_cap:
            raise SystemExit(f"BudgetLedger6B2 拒绝: slice {slice_id} 完成后突破 hard_cap")
        self._completed.add(slice_id)
        self.attempts_by_slice[slice_id] = actual_attempts
        self.total_attempted += actual_attempts
        self._save()

    def slice_completed(self, slice_id):
        return slice_id in self._completed

    def can_attempt(self, extra=0):
        return self.total_attempted + extra <= self.hard_cap


# ── Task 11 helpers ──

def _sha256_file(path):
    h = hashlib.sha256()
    if not os.path.exists(path):
        return "0" * 64
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_events(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def _build_runner_cmd(slice_info, provider, model, resume=False):
    """Build subprocess command. Frozen fields read from slice_info only (no arm branching drift)."""
    case_ids_file = slice_info["case_ids_file"]
    os.makedirs(os.path.dirname(case_ids_file), exist_ok=True)
    with open(case_ids_file, "w", encoding="utf-8") as _f:
        json.dump(slice_info["case_ids"], _f)
    base = [sys.executable, "-m", "benchmark.runners.run_benchmark"]
    slice_hard_cap = slice_info["hard_cap"]
    common = [
        "--repeat-idx", str(slice_info["repeat"]),
        "--hard-cap", str(slice_hard_cap),
        "--provider", provider, "--model", model,
        "--model-runner",
        "--case-details-jsonl", slice_info["detail_path"],
        "--case-ids-file", case_ids_file,
        "--max-cases", str(slice_info["max_cases"]),
        "--scheduled-calls", str(slice_info["scheduled_calls"]),
        "--temperature", "0",
        "--output-dir", slice_info["output_dir"],
        "--as-of-date", FROZEN_DATE,
        "--chart-schema-version", FROZEN_CHART_SCHEMA,
    ]
    if resume:
        common.append("--resume")
    if slice_info["arm"] == "b1a_prime":
        cmd = base + [
            "--profile", "baziqa_xjz_reasoned",
            "--method", "direct_choice",
            "--attempt-stage", "main",
            "--arm", "b1a_prime",
            "--ziwei-arm", "none",
            "--dataset", slice_info["dataset_path"],
        ] + common
    else:
        cmd = base + [
            "--profile", "baziqa_xjz_dual",
            "--method", "dual_system",
            "--attempt-stage", "dual",
            "--arm", "dual",
            "--dataset", slice_info["dataset_path"],
        ] + common
    return cmd


def _slice_runner_args(slice_info, provider, model):
    """Reconstruct runner args namespace from slice_info for manifest homology check."""
    is_b1a = slice_info["arm"] == "b1a_prime"
    return types.SimpleNamespace(
        dataset=slice_info["dataset_path"],
        case_ids_file=slice_info["case_ids_file"],
        profile=slice_info["profile"],
        chart_schema_version=FROZEN_CHART_SCHEMA,
        arm=slice_info["arm"],
        ziwei_arm="none" if is_b1a else None,
        attempt_stage="main" if is_b1a else "dual",
        repeat_idx=slice_info["repeat"],
        provider=provider, model=model,
        temperature=0.0, sample_temperature=0.4,
        n_samples=1, aggregate="majority",
        method=slice_info["method"],
        scheduled_calls=slice_info["scheduled_calls"],
        hard_cap=slice_info["hard_cap"],
        as_of_date=FROZEN_DATE,
    )


# ── OutputDirLock (reuse 6B1D token-based lock) ──

class OutputDirLock:
    LOCK_FILENAME = ".orchestrator.lock"

    def __init__(self, lock_path, owner_token):
        self._lock_path = lock_path
        self._owner_token = owner_token
        self._released = False

    @staticmethod
    def _read_lock_file(lock_path):
        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except OSError:
            return None
        parts = content.split("\n", 1)
        if len(parts) != 2:
            return None
        try:
            pid = int(parts[0].strip() or "0")
        except ValueError:
            return None
        token = parts[1].strip()
        if not token:
            return None
        return pid, token

    @classmethod
    def acquire(cls, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        lock_path = os.path.join(output_dir, cls.LOCK_FILENAME)
        pid = os.getpid()
        token = uuid.uuid4().hex

        def _pid_alive(p):
            if p <= 0:
                return False
            if sys.platform == "win32":
                try:
                    import ctypes
                    k32 = ctypes.windll.kernel32
                    h = k32.OpenProcess(0x1000, False, p)
                    if h:
                        k32.CloseHandle(h)
                        return True
                    return k32.GetLastError() == 5
                except Exception:
                    return False
            try:
                os.kill(p, 0)
            except (ProcessLookupError, PermissionError):
                return False
            return True

        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            parsed = cls._read_lock_file(lock_path)
            if parsed is None:
                return None
            holder_pid, _ = parsed
            if _pid_alive(holder_pid):
                return None
            try:
                os.remove(lock_path)
            except OSError:
                return None
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return None
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{pid}\n{token}")
        return cls(lock_path, token)

    def release(self):
        if self._released:
            return
        self._released = True
        parsed = self._read_lock_file(self._lock_path)
        if parsed is None:
            return
        _, token = parsed
        if token != self._owner_token:
            return
        try:
            os.remove(self._lock_path)
        except OSError:
            pass


# ── Task 11: smoke integrity ──

def _smoke_integrity(detail_rows, slice_info):
    """Smoke integrity: per-case bazi+ziwei exactly 1 each, judge by disagreement cardinality."""
    case_ids = set(slice_info["case_ids"])
    present = {r.get("case_id") for r in detail_rows if r.get("case_id") in case_ids}
    if present != case_ids:
        return f"SMOKE_CASE_COUNT: {len(present)}/{len(case_ids)}"
    for cid in case_ids:
        rows = [r for r in detail_rows if r.get("case_id") == cid]
        stages = {}
        by_stage = {}
        for r in rows:
            st = (r.get("attempt_key") or [None] * 10)[3]
            if st not in ("bazi", "ziwei", "judge"):
                return f"SMOKE_UNKNOWN_STAGE: {cid} stage={st}"
            if r.get("terminal_state") not in ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed"):
                return f"SMOKE_TERMINAL: {cid} state={r.get('terminal_state')}"
            stages[st] = stages.get(st, 0) + 1
            by_stage[st] = r
        if stages.get("bazi") != 1 or stages.get("ziwei") != 1:
            return f"SMOKE_STAGE: {cid} {stages}"
        b_ans = by_stage["bazi"].get("predicted_answer")
        z_ans = by_stage["ziwei"].get("predicted_answer")
        n_judge = stages.get("judge", 0)
        consensus = (b_ans is not None and z_ans is not None and b_ans == z_ans)
        both_unresolved = (b_ans is None and z_ans is None)
        if consensus or both_unresolved:
            if n_judge != 0:
                return f"SMOKE_JUDGE_ON_{'CONSENSUS' if consensus else 'BOTH_UNRESOLVED'}: {cid}"
        else:
            if n_judge != 1:
                return f"SMOKE_MISSING_JUDGE: {cid}"
    return "PASS"


def _slice_integrity_gate(detail_rows, slice_info):
    """Single-slice integrity: 8 cases with correct stage counts and judge cardinality."""
    case_ids = set(slice_info["case_ids"])
    present = {r.get("case_id") for r in detail_rows if r.get("case_id") in case_ids}
    if len(present) != 8:
        return f"CASE_COUNT: {len(present)}/8"
    by_case = {}
    for r in detail_rows:
        cid = r.get("case_id")
        if cid in case_ids:
            by_case.setdefault(cid, []).append(r)
    for cid in case_ids:
        rows = by_case.get(cid, [])
        def _stage(r):
            ak = r.get("attempt_key") or [None] * 10
            return ak[3]
        if slice_info["arm"] == "b1a_prime":
            mains = [r for r in rows if _stage(r) == "main"]
            if len(mains) != 1:
                return f"B1A_MAIN: {cid} count={len(mains)}"
            if mains[0].get("terminal_state") not in ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed"):
                return f"B1A_TERMINAL: {cid} state={mains[0].get('terminal_state')}"
        else:
            bazis = [r for r in rows if _stage(r) == "bazi"]
            ziwes = [r for r in rows if _stage(r) == "ziwei"]
            if len(bazis) != 1:
                return f"BAZI_COUNT: {cid} count={len(bazis)}"
            if len(ziwes) != 1:
                return f"ZIWEI_COUNT: {cid} count={len(ziwes)}"
            for r in bazis + ziwes + [r for r in rows if _stage(r) == "judge"]:
                if r.get("terminal_state") not in ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed"):
                    return f"DUAL_TERMINAL: {cid} state={r.get('terminal_state')}"
            b_ans = bazis[0].get("predicted_answer")
            z_ans = ziwes[0].get("predicted_answer")
            judges = [r for r in rows if _stage(r) == "judge"]
            consensus = (b_ans is not None and z_ans is not None and b_ans == z_ans)
            both_unresolved = (b_ans is None and z_ans is None)
            if consensus or both_unresolved:
                if len(judges) != 0:
                    return f"JUDGE_ON_{'CONSENSUS' if consensus else 'BOTH_UNRESOLVED'}: {cid}"
            else:
                if len(judges) != 1:
                    return f"MISSING_JUDGE: {cid} count={len(judges)}"
    return "PASS"


def _run_slice(slice_info, ledger, provider, model, integrity="slice"):
    """Atomically execute a single slice. Supports smoke/slice integrity modes and partial resume."""
    out_dir = Path(slice_info["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    is_smoke = integrity == "smoke"
    status_path = out_dir / "slice_status.json"
    detail_path = Path(slice_info["detail_path"])
    events_path = Path(slice_info["events_path"])
    runner_manifest_path = Path(str(detail_path).replace(".jsonl", ".manifest.json"))
    lock = None
    try:
        lock = OutputDirLock.acquire(str(out_dir))
        if lock is None:
            raise SystemExit(f"slice {slice_info['slice_id']} 输出目录被其他进程持有")
        is_resume = False
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("completed") and status.get("slice_id") == slice_info["slice_id"]:
                if not runner_manifest_path.exists():
                    raise SystemExit(f"slice {slice_info['slice_id']} resume 拒绝: runner manifest 缺失")
                from benchmark.runners.run_benchmark import build_resume_manifest, check_resume_manifest
                from benchmark.runners.profiles import resolve_profile
                profile_obj = resolve_profile(slice_info["profile"], FROZEN_CHART_SCHEMA)
                current_manifest = build_resume_manifest(
                    _slice_runner_args(slice_info, provider, model), profile_obj)
                check_resume_manifest(str(runner_manifest_path), current_manifest)
                if not events_path.exists():
                    raise SystemExit(f"slice {slice_info['slice_id']} resume 拒绝: events 文件缺失")
                actual = sum(1 for r in _load_events(str(events_path)) if r.get("kind") == "call_attempt")
                if actual != status.get("actual_attempts", -1):
                    raise SystemExit(f"slice {slice_info['slice_id']} resume 拒绝: actual_attempts 不一致")
                ledger.record_slice_completed(slice_info["slice_id"], actual,
                                              arm=("smoke" if is_smoke else slice_info["arm"]))
                return
            is_resume = True
        elif runner_manifest_path.exists() or events_path.exists() or detail_path.exists():
            is_resume = True
        existing_attempts = 0
        if is_resume and events_path.exists():
            existing_attempts = sum(1 for r in _load_events(str(events_path)) if r.get("kind") == "call_attempt")
        remaining = slice_info["hard_cap"] - existing_attempts
        if remaining < 0:
            raise SystemExit(f"slice {slice_info['slice_id']} resume 拒绝: events 已超 hard_cap")
        if ledger.total_attempted + existing_attempts + remaining > ledger.hard_cap:
            raise SystemExit(f"slice {slice_info['slice_id']} 拒绝: 预算不足")
        cmd = _build_runner_cmd(slice_info, provider, model, resume=is_resume)
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=_PROJECT_ROOT)
        elapsed = time.time() - start
        if result.returncode != 0:
            raise SystemExit(f"slice {slice_info['slice_id']} 失败 (exit={result.returncode}): {result.stderr[:500]}")
        if not detail_path.exists() or detail_path.stat().st_size == 0:
            raise SystemExit(f"slice {slice_info['slice_id']} 失败: detail jsonl 缺失或为空")
        if not events_path.exists() or events_path.stat().st_size == 0:
            raise SystemExit(f"slice {slice_info['slice_id']} 失败: events jsonl 缺失或为空")
        if not runner_manifest_path.exists():
            raise SystemExit(f"slice {slice_info['slice_id']} 失败: runner 未生成 manifest")
        detail_rows = _load_events(str(detail_path))
        integrity_result = _smoke_integrity(detail_rows, slice_info) if is_smoke else _slice_integrity_gate(detail_rows, slice_info)
        if integrity_result != "PASS":
            raise SystemExit(f"slice {slice_info['slice_id']} 失败: 完整性门禁 ({integrity_result})")
        actual = sum(1 for r in _load_events(str(events_path)) if r.get("kind") == "call_attempt")
        runner_manifest_sha = _sha256_file(str(runner_manifest_path))
        status_path.write_text(json.dumps({
            "slice_id": slice_info["slice_id"], "completed": True,
            "exit_code": result.returncode, "elapsed_s": round(elapsed, 1),
            "actual_attempts": actual, "scheduled_calls": slice_info["scheduled_calls"],
            "hard_cap": slice_info["hard_cap"], "remaining_reserved": remaining,
            "runner_manifest_sha256": runner_manifest_sha,
            "arm": slice_info["arm"], "integrity": integrity,
            "method": "dual_system" if slice_info["arm"] == "dual" else "direct_choice",
        }, ensure_ascii=False), encoding="utf-8")
        ledger.record_slice_completed(slice_info["slice_id"], actual,
                                      arm=("smoke" if is_smoke else slice_info["arm"]))
    finally:
        if lock is not None:
            lock.release()


# ── Task 12: Multi-stage integrity gate (global, per-cell matrix) ──

def _year_from_dataset_id(dataset_id):
    m = re.search(r"baziqa_contest8_(\d{4})_holdout", dataset_id or "")
    return m.group(1) if m else None


def parse_detail_identity(row):
    ak = row["attempt_key"]
    return (_year_from_dataset_id(ak[0]), int(ak[7]), ak[6], ak[2], ak[3])


def _expected_cells(schedule):
    cells = set()
    for sl in schedule["slices"]:
        for cid in sl["case_ids"]:
            cells.add((sl["year"], sl["repeat"], cid, sl["arm"]))
    return cells


def _integrity_gate(merged_details, schedule):
    """Global integrity gate validating expected cell matrix and stage cardinalities."""
    expected = _expected_cells(schedule)
    by_cell = defaultdict(lambda: defaultdict(list))
    seen = set()
    for r in merged_details:
        year, rep, cid, arm, stage = parse_detail_identity(r)
        ak = tuple(r["attempt_key"])
        if ak in seen:
            return f"DUPLICATE: {ak}"
        seen.add(ak)
        by_cell[(year, rep, cid, arm)][stage].append(r)
    actual = set(by_cell.keys())
    VALID_ARMS = {"b1a_prime", "dual"}
    for (yr, rp, cid, arm) in actual:
        if arm not in VALID_ARMS:
            return f"UNKNOWN_ARM: {arm} (cell={yr}/{rp}/{cid})"
    missing = expected - actual
    if missing:
        return f"MISSING_CELLS: {sorted(missing)[:3]}..."
    extra = actual - expected
    if extra:
        return f"EXTRA_CELLS: {sorted(extra)[:3]}..."
    B1A_VALID_STAGES = {"main"}
    DUAL_VALID_STAGES = {"bazi", "ziwei", "judge"}
    for (year, rep, cid, arm), stages in by_cell.items():
        if arm == "b1a_prime":
            extra_stages = set(stages.keys()) - B1A_VALID_STAGES
            if extra_stages:
                return f"B1A_EXTRA_STAGE: {year}/{rep}/{cid} extra={extra_stages}"
            if len(stages.get("main", [])) != 1:
                return f"B1A_MAIN_COUNT: {year}/{rep}/{cid} = {len(stages.get('main', []))}"
        elif arm == "dual":
            extra_stages = set(stages.keys()) - DUAL_VALID_STAGES
            if extra_stages:
                return f"DUAL_EXTRA_STAGE: {year}/{rep}/{cid} extra={extra_stages}"
            if len(stages.get("bazi", [])) != 1:
                return f"BAZI_COUNT: {year}/{rep}/{cid} = {len(stages.get('bazi', []))}"
            if len(stages.get("ziwei", [])) != 1:
                return f"ZIWEI_COUNT: {year}/{rep}/{cid} = {len(stages.get('ziwei', []))}"
            b_ans = stages["bazi"][0].get("predicted_answer")
            z_ans = stages["ziwei"][0].get("predicted_answer")
            judge = stages.get("judge", [])
            consensus = (b_ans is not None and z_ans is not None and b_ans == z_ans)
            both_unresolved = (b_ans is None and z_ans is None)
            if consensus or both_unresolved:
                if len(judge) != 0:
                    return f"JUDGE_ON_{'CONSENSUS' if consensus else 'BOTH_UNRESOLVED'}: {year}/{rep}/{cid}"
            else:
                if len(judge) != 1:
                    return f"MISSING_JUDGE: {year}/{rep}/{cid} (count={len(judge)})"
    for r in merged_details:
        if r.get("terminal_state") not in ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed"):
            return f"INVALID_STATE: {r.get('terminal_state')}"
    return "PASS"


# ── Task 13: compute_gate (3-stage parameterized, real schema) + B1-c advisory ──

def compute_gate(merged_details, stage="dev"):
    """Compute experiment gates. 3-stage parameterized per spec §7.3/§7.4."""
    by_key = defaultdict(list)
    for r in merged_details:
        year, rep, cid, arm, stg = parse_detail_identity(r)
        by_key[(year, rep, cid, arm)].append(r)
    expected_years = {"2024", "2025"} if stage == "dev" else (
        {"2021", "2022"} if stage == "reuse" else {"2023"})
    seen_years = {y for (y, _, _, _) in by_key}
    if seen_years != expected_years:
        raise SystemExit(f"year 集合不匹配: {seen_years} != {expected_years}")
    seen_reps = {rep for (_, rep, _, _) in by_key}
    if seen_reps != {0, 1, 2}:
        raise SystemExit(f"repeat 集合不完整: {seen_reps} != {{0,1,2}}")
    seen_arms = {arm for (_, _, _, arm) in by_key}
    if seen_arms != {"dual", "b1a_prime"}:
        raise SystemExit(f"arm 集合不完整: {seen_arms} != {{dual,b1a_prime}}")
    case_sets = defaultdict(set)
    for (year, rep, cid, arm) in by_key:
        case_sets[(year, rep, arm)].add(cid)
    for (year, rep, arm), cids in case_sets.items():
        if len(cids) != 40:
            raise SystemExit(f"case 数 != 40: {year}/{rep}/{arm} = {len(cids)}")
    for year in expected_years:
        for rep in [0, 1, 2]:
            dual_ids = case_sets.get((year, rep, "dual"), set())
            b1a_ids = case_sets.get((year, rep, "b1a_prime"), set())
            if dual_ids != b1a_ids:
                raise SystemExit(f"两臂 case_id 集合不同: {year}/{rep}")
    acc = defaultdict(lambda: {"dual_correct": 0, "b1a_correct": 0})
    for (year, rep, cid, arm), rows in by_key.items():
        if arm == "b1a_prime":
            acc[(year, rep)]["b1a_correct"] += 1 if rows[0]["correct"] else 0
        elif arm == "dual":
            b = next((r for r in rows if (r.get("attempt_key") or [None] * 10)[3] == "bazi"), None)
            z = next((r for r in rows if (r.get("attempt_key") or [None] * 10)[3] == "ziwei"), None)
            j = next((r for r in rows if (r.get("attempt_key") or [None] * 10)[3] == "judge"), None)
            if b and z and b["predicted_answer"] is not None and z["predicted_answer"] is not None \
                    and b["predicted_answer"] == z["predicted_answer"]:
                final = b["predicted_answer"]
            elif j:
                final = j["predicted_answer"]
            else:
                final = None
            expected = (b or z)["expected_answer"]
            acc[(year, rep)]["dual_correct"] += 1 if final == expected else 0
    delta_yr_rep = {}
    for (year, rep), v in acc.items():
        da = v["dual_correct"] / 40
        ba = v["b1a_correct"] / 40
        delta_yr_rep[(year, rep)] = da - ba
    years = sorted(years_seen := expected_years)
    if stage == "dev":
        delta_year = {y: sum(d for (yy, _), d in delta_yr_rep.items() if yy == y) / 3 for y in years}
        delta_dev = sum(delta_year.values()) / len(years)
        dual_total = 40 * len(years) * 3
        dual_merged_acc = sum(v["dual_correct"] for v in acc.values()) / dual_total
        min_year = min(delta_year.values())
        verdict = "PROMOTE_CANDIDATE" if (delta_dev >= 0.04 and dual_merged_acc >= 0.325 and min_year >= -0.02) else "ROLLBACK"
        return {"verdict": verdict, "delta_dev": delta_dev, "dual_merged_acc": dual_merged_acc,
                "min_year_delta": min_year, "delta_by_year": delta_year,
                "delta_by_year_repeat": delta_yr_rep, "stage": stage}
    elif stage == "reuse":
        delta_year = {y: sum(d for (yy, _), d in delta_yr_rep.items() if yy == y) / 3 for y in years}
        verdict = "PASS" if all(d >= 0.02 for d in delta_year.values()) else "FAIL"
        return {"verdict": verdict, "delta_by_year": delta_year,
                "delta_2021": delta_year.get("2021"), "delta_2022": delta_year.get("2022"), "stage": stage}
    elif stage == "final_2023":
        delta_year = {y: sum(d for (yy, _), d in delta_yr_rep.items() if yy == y) / 3 for y in years}
        d2023 = delta_year.get("2023", -1.0)
        if d2023 >= 0:
            verdict = "CONFIRMED_PROMOTE"
        elif d2023 > -0.05:
            verdict = "INCONCLUSIVE"
        else:
            verdict = "ROLLBACK"
        return {"verdict": verdict, "delta_2023": d2023, "stage": stage}
    else:
        raise SystemExit(f"unknown stage: {stage}")


def load_b1c_advisory():
    import hashlib as _h
    path = B1C_ARCHIVE_PATH
    if not os.path.exists(path):
        raise SystemExit(f"B1-c 归档不存在: {path} (fail-closed)")
    with open(path, "rb") as f:
        sha = _h.sha256(f.read()).hexdigest()
    if sha != B1C_EXPECTED_SHA256:
        raise SystemExit(f"B1-c SHA-256 不匹配: {sha} != {B1C_EXPECTED_SHA256} (fail-closed)")
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    b1c = [r for r in rows if r.get("attempt_key", [None] * 10)[2] == "b1c"]
    return {"path": path, "sha256": sha, "count": len(b1c), "rows": b1c}


# ── Task 13 helpers: _accuracy_final + generate_report ──

def _accuracy_final(rows):
    b1a_rows = [r for r in rows if (r.get("attempt_key") or [None] * 10)[3] == "main"]
    b1a_acc = round(sum(bool(r.get("correct")) for r in b1a_rows) / max(len(b1a_rows), 1), 4)
    cells = {}
    for r in rows:
        ak = r.get("attempt_key") or [None] * 10
        if ak[2] != "dual":
            continue
        m = re.search(r"(20\d\d)", str(ak[0]))
        year = m.group(1) if m else "unknown"
        rep = ak[7]
        cells.setdefault((year, rep, r.get("case_id")), {})[ak[3]] = r
    n_ok = 0
    for cell in cells.values():
        b, z, j = cell.get("bazi"), cell.get("ziwei"), cell.get("judge")
        if b and z and b.get("predicted_answer") and b["predicted_answer"] == z.get("predicted_answer"):
            final = b["predicted_answer"]
        elif j:
            final = j.get("predicted_answer")
        else:
            final = None
        exp = (b or z)["expected_answer"]
        n_ok += (final is not None and final == exp)
    return {"dual_final_accuracy": round(n_ok / max(len(cells), 1), 4),
            "dual_cases": len(cells),
            "b1a_accuracy": b1a_acc, "b1a_rows": len(b1a_rows)}


def generate_report(gate, merged_details, schedule, ledger, b1c_advisory, out_dir):
    rows = merged_details
    total = max(len(rows), 1)
    parsed = sum(1 for r in rows if r.get("terminal_state") == "parsed")
    judge_rows = [r for r in rows if (r.get("attempt_key") or [None] * 10)[3] == "judge"]
    dual_cells = {(str(r.get("attempt_key", [None])[0]),
                   (r.get("attempt_key") or [None] * 10)[7],
                   r.get("case_id"))
                  for r in rows if (r.get("attempt_key") or [None] * 10)[2] == "dual"}
    report = {
        "run": {"slices": len(schedule["slices"]),
                "scheduled": schedule["total_scheduled_calls"],
                "attempted": ledger.total_attempted,
                "global_hard_cap": ledger.hard_cap},
        "gate": gate,
        "accuracy": _accuracy_final(rows),
        "delta": {k: v for k, v in gate.items() if k.startswith(("delta", "min_year"))},
        "judge": {"trigger_rate": round(len(judge_rows) / max(len(dual_cells), 1), 4),
                  "reference_disagreement_rate": JUDGE_DISAGREEMENT_RATE,
                  "judge_calls": len(judge_rows)},
        "parser_rate": round(parsed / total, 4),
        "integrity": {"rows": total, "call_failed": sum(
            1 for r in rows if r.get("terminal_state") == "call_failed")},
        "b1c_advisory": {"count": b1c_advisory["count"], "sha256": b1c_advisory["sha256"],
                         "note": "非同时段比较 + provider drift 风险，描述性附列，非预注册 gate"},
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 6B2 双管线报告",
             f"- gate：**{gate['verdict']}**（{gate.get('stage')}）",
             f"- judge 触发率：{report['judge']['trigger_rate']}（参照 {JUDGE_DISAGREEMENT_RATE}）",
             f"- parser rate：{report['parser_rate']}；call_failed：{report['integrity']['call_failed']}",
             f"- 预算：scheduled {report['run']['scheduled']} / attempted {report['run']['attempted']}"
             f" / cap {report['run']['global_hard_cap']}",
             f"- B1-c advisory（非决策）：{report['b1c_advisory']['note']}",
             "", "如实声明：40 题/年度，2 题即 5pp；请求不携带 seed；B1-c 为 6B1 时段旧 run。"]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


# ── Task 14: smoke gate state machine + smoke slice construction ──

SMOKE_SCHEDULED = 6
SMOKE_HARD_CAP = 10


def _build_smoke_slices(schedule):
    """Build a SINGLE dual smoke slice: first year, dual arm, repeat 0 group 0,
    first SMOKE_CASES_PER_GROUP cases.  v18 口径: 单 dual smoke, scheduled=6/hard_cap=10.
    Returns a list of exactly one smoke slice dict.
    """
    target = None
    for sl in schedule["slices"]:
        if sl["arm"] == "dual" and sl["repeat"] == 0 and sl["group"] == 0:
            target = sl
            break
    if target is None:
        raise SystemExit("_build_smoke_slices 拒绝: schedule 中无 dual/repeat0/group0 切片")
    smoke_cases = target["case_ids"][:SMOKE_CASES_PER_GROUP]
    smoke_id = f"smoke_{target['year']}_dual"
    runs_dir = os.path.dirname(os.path.dirname(target["output_dir"]))
    smoke_out = os.path.join(runs_dir, smoke_id)
    return [{
        "year": target["year"], "repeat": 0, "arm": "dual", "group": 0,
        "slice_id": smoke_id, "output_dir": smoke_out,
        "detail_path": os.path.join(smoke_out, "details.jsonl"),
        "events_path": os.path.join(smoke_out, "details.events.jsonl"),
        "dataset_path": target["dataset_path"],
        "case_ids_file": os.path.join(smoke_out, "case_ids.json"),
        "profile": target["profile"], "method": target["method"],
        "hard_cap": SMOKE_HARD_CAP, "max_cases": SMOKE_CASES_PER_GROUP,
        "scheduled_calls": SMOKE_SCHEDULED, "case_ids": smoke_cases,
    }]


def determine_smoke_state(smoke_dir, expected_case_ids=None):
    smoke_dir = Path(smoke_dir)
    detail = smoke_dir / "details.jsonl"
    if not detail.exists():
        return "fresh"
    try:
        rows = [json.loads(l) for l in detail.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "blocked_corrupt"
    if not rows or expected_case_ids is None:
        return "resume" if rows else "fresh"
    per_case = {}
    for r in rows:
        per_case.setdefault(r.get("case_id"), set()).add((r.get("attempt_key") or [None] * 10)[3])
    for cid in expected_case_ids:
        if not ({"bazi", "ziwei"} <= per_case.get(cid, set())):
            return "resume"
    return "completed"


def verify_smoke_completed(smoke_dir, expected_case_ids):
    smoke_dir = Path(smoke_dir)
    detail = smoke_dir / "details.jsonl"
    if not detail.exists():
        raise SystemExit("smoke 拒绝: details.jsonl 缺失")
    rows = [json.loads(l) for l in detail.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        raise SystemExit("smoke 拒绝: details.jsonl 为空")
    stages = {}
    ziwei_cases = set()
    parsed = 0
    failed = 0
    for r in rows:
        stage = (r.get("attempt_key") or [None] * 10)[3]
        stages[stage] = stages.get(stage, 0) + 1
        if stage == "ziwei":
            ziwei_cases.add(r.get("case_id"))
        if r.get("terminal_state") == "parsed":
            parsed += 1
        elif r.get("terminal_state") == "call_failed":
            failed += 1
    coverage = len(ziwei_cases) / max(len(expected_case_ids), 1)
    if coverage < 1.0:
        raise SystemExit(f"smoke 拒绝: ziwei 覆盖不足 {coverage:.2%}")
    if failed:
        raise SystemExit(f"smoke 拒绝: 存在 {failed} 条 call_failed")
    rate = round(parsed / max(len(rows) - failed, 1), 4)
    if rate < SMOKE_PARSER_RATE_MIN:
        raise SystemExit(f"smoke 拒绝: parser rate {rate} < {SMOKE_PARSER_RATE_MIN}")
    return {"parser_rate": rate, "ziwei_coverage": coverage, "stages": stages,
            "rows": len(rows), "status": "OK"}


def _verify_completed_slice(slice_info, provider, model):
    """Verify an already-completed slice has valid manifest, events, and attempt counts.
    Called instead of blindly skipping ledger-completed slices.
    """
    out_dir = Path(slice_info["output_dir"])
    detail_path = Path(slice_info["detail_path"])
    events_path = Path(slice_info["events_path"])
    runner_manifest_path = Path(str(detail_path).replace(".jsonl", ".manifest.json"))
    status_path = out_dir / "slice_status.json"
    if not status_path.exists():
        raise SystemExit(f"slice {slice_info['slice_id']} completed 验证拒绝: slice_status.json 缺失")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if not status.get("completed"):
        raise SystemExit(f"slice {slice_info['slice_id']} completed 验证拒绝: status.completed != true")
    if status.get("slice_id") != slice_info["slice_id"]:
        raise SystemExit(f"slice {slice_info['slice_id']} completed 验证拒绝: slice_id 不匹配")
    if not runner_manifest_path.exists():
        raise SystemExit(f"slice {slice_info['slice_id']} completed 验证拒绝: runner manifest 缺失")
    from benchmark.runners.run_benchmark import build_resume_manifest, check_resume_manifest
    from benchmark.runners.profiles import resolve_profile
    profile_obj = resolve_profile(slice_info["profile"], FROZEN_CHART_SCHEMA)
    current_manifest = build_resume_manifest(
        _slice_runner_args(slice_info, provider, model), profile_obj)
    check_resume_manifest(str(runner_manifest_path), current_manifest)
    if not events_path.exists():
        raise SystemExit(f"slice {slice_info['slice_id']} completed 验证拒绝: events 文件缺失")
    if not detail_path.exists():
        raise SystemExit(f"slice {slice_info['slice_id']} completed 验证拒绝: detail 文件缺失")
    actual = sum(1 for r in _load_events(str(events_path)) if r.get("kind") == "call_attempt")
    if actual != status.get("actual_attempts", -1):
        raise SystemExit(f"slice {slice_info['slice_id']} completed 验证拒绝: actual_attempts 不一致")
    detail_rows = _load_events(str(detail_path))
    integrity_result = _slice_integrity_gate(detail_rows, slice_info)
    if integrity_result != "PASS":
        raise SystemExit(f"slice {slice_info['slice_id']} completed 验证拒绝: 完整性门禁 ({integrity_result})")
    return actual


# ── Task 16: generate_archive + audit_index ──

def _compute_experiment_code_fingerprint():
    """SHA-256 over source of every function that affects experiment execution,
    admission, or validation. Any drift in these between stages MUST be detected."""
    parts = []
    # Scheduling
    for fn in (_build_schedule, _build_smoke_slices, _compute_schedule_hash):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    # Execution
    for fn in (_run_slice, _run_all_slices, _verify_completed_slice):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    # Integrity / gate / smoke gate
    for fn in (_integrity_gate, compute_gate, _slice_integrity_gate,
               determine_smoke_state, verify_smoke_completed, _smoke_integrity):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    # Run-id and receipt chain
    for fn in (_validate_run_id, _verify_receipt_belongs_to_run, _publish_receipt_atomic):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    # Archive and report
    for fn in (generate_archive, _merge_all_details, _compute_dataset_hashes):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    # Stage entry points (these wire the whole protocol together)
    for fn in (run_dev, run_reuse, run_2023_final):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    # Budget ledger (class source via its methods)
    for fn_name in ("__init__", "record_slice_completed", "can_attempt",
                    "slice_completed"):
        fn = getattr(BudgetLedger6B2, fn_name, None)
        if fn is not None:
            parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    # OutputDirLock
    for fn_name in ("acquire", "release"):
        fn = getattr(OutputDirLock, fn_name, None)
        if fn is not None:
            parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    try:
        from scripts.phase6_6b2_sealed_workflow import (
            check_stage_gate, acquire_2023_run_lock, enrich_year,
            record_enriched_sha_to_lock, finalize_2023_run_lock,
            update_lock_schedule_hash, verify_2023_raw_data)
        for fn in (check_stage_gate, acquire_2023_run_lock, enrich_year,
                   record_enriched_sha_to_lock, finalize_2023_run_lock,
                   update_lock_schedule_hash, verify_2023_raw_data):
            parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    except ImportError:
        pass
    # P0-2: Runner code fingerprint — hashes actual bytes of run_benchmark.py,
    # profiles.py, dual_system_reasoning.py, prompt formatters, API clients.
    # These files control prompt construction, parsing, and model invocation;
    # drift between stages MUST be detected.
    try:
        from benchmark.runners.run_benchmark import _code_fingerprint as _runner_fp
        parts.append(_runner_fp())
    except ImportError:
        # Fail-closed: if runner fingerprint cannot be computed, mark a sentinel
        # that will mismatch any stage that successfully imported it.
        parts.append("<runner_fingerprint_unavailable>")
    return hashlib.sha256("".join(parts).encode()).hexdigest()


def _compute_dataset_hashes(raw_paths=None, enriched_paths=None):
    """Compute SHA-256 of raw and enriched dataset files (concatenated sorted)."""
    raw_h = hashlib.sha256()
    for p in sorted(raw_paths.values()) if raw_paths else []:
        if os.path.exists(p):
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    raw_h.update(chunk)
    enriched_h = hashlib.sha256()
    for p in sorted(enriched_paths.values()) if enriched_paths else []:
        if os.path.exists(p):
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    enriched_h.update(chunk)
    return {"raw": raw_h.hexdigest(), "enriched": enriched_h.hexdigest()}


def _merge_all_details(schedule):
    """Merge all slice detail.jsonl files into a single list preserving order."""
    merged = []
    for sl in schedule["slices"]:
        if os.path.exists(sl["detail_path"]):
            merged.extend(_load_events(sl["detail_path"]))
    return merged


def _merge_all_events(schedule):
    """Merge all slice details.events.jsonl files into a single list preserving order."""
    merged = []
    for sl in schedule["slices"]:
        if os.path.exists(sl["events_path"]):
            merged.extend(_load_events(sl["events_path"]))
    return merged


def _atomic_write_json(path, data):
    """Atomically write JSON to path via temp file + os.replace."""
    import shutil
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(p))


# Fields excluded from schedule hash: runtime-dependent paths derived from output_dir.
_SCHED_HASH_SLICE_KEYS = ("year", "repeat", "arm", "group", "slice_id", "case_ids",
                          "profile", "method", "hard_cap", "max_cases", "scheduled_calls")


def _compute_schedule_hash(schedule):
    """Deterministic SHA-256 over the FULL scheduling matrix (all slices' case_ids,
    caps, profiles, etc.). Excludes only runtime-path fields (output_dir, *_path) that
    vary by run directory. Any change to case ordering, grouping, arm assignment, or
    budget caps produces a different hash."""
    canonical_slices = []
    for sl in schedule["slices"]:
        canonical_slices.append({k: sl[k] for k in _SCHED_HASH_SLICE_KEYS})
    canonical = {
        "global_hard_cap": schedule["global_hard_cap"],
        "total_scheduled_calls": schedule["total_scheduled_calls"],
        "total_slices": schedule["total_slices"],
        "slices": canonical_slices,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def generate_archive(schedule, ledger, run_dir, provider, model, gate_result,
                     archive_root=None, stage="dev", raw_dataset_paths=None,
                     enriched_dataset_paths=None, run_id=None, smoke_attempted=0):
    """Generate archive with audit index, merged details/events, and receipt. Fail-closed.
    Writes to a temporary sibling directory, self-verifies, then atomically publishes
    via os.replace. On any failure the temp directory is cleaned up."""
    import shutil
    archive_root = Path(archive_root or ARCHIVE_ROOT)
    run_dir = Path(run_dir)
    if gate_result.get("verdict") == "BLOCKED_INCOMPLETE":
        raise SystemExit("archive 拒绝: BLOCKED_INCOMPLETE 裁决不得归档")
    completed = {sl["slice_id"] for sl in schedule["slices"] if ledger.slice_completed(sl["slice_id"])}
    expected_ids = {sl["slice_id"] for sl in schedule["slices"]}
    if completed != expected_ids:
        raise SystemExit(f"archive 拒绝: schedule 未全部完成 ({len(completed)}/{len(expected_ids)})")
    if ledger.total_attempted > ledger.hard_cap:
        raise SystemExit("archive 拒绝: ledger 突破 hard_cap")
    merged = _merge_all_details(schedule)
    integrity = _integrity_gate(merged, schedule)
    if integrity != "PASS":
        raise SystemExit(f"archive 拒绝: integrity gate 失败 ({integrity})")
    code_fp = _compute_experiment_code_fingerprint()
    auto_id = f"6b2-{stage}-{FROZEN_DATE}-{provider}-{model}-{code_fp[:12]}"
    archive_run_id = f"{run_id}-{auto_id}" if run_id else auto_id
    target = archive_root / archive_run_id
    if target.exists():
        raise SystemExit(f"archive 拒绝: run_id 已存在 ({target})")
    # Atomic publish: write to temp dir, self-verify, then os.replace
    tmp_dir = archive_root / f".{archive_run_id}.tmp-{os.getpid()}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        for sl in schedule["slices"]:
            sl_dir = Path(sl["output_dir"])
            if sl_dir.exists():
                sl_target = tmp_dir / sl_dir.name
                sl_target.mkdir(exist_ok=True)
                for f in sl_dir.iterdir():
                    if f.is_file():
                        shutil.copy2(f, sl_target / f.name)
        merged_details_path = tmp_dir / "merged_details.jsonl"
        with open(merged_details_path, "w", encoding="utf-8") as f:
            for row in merged:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        merged_events = _merge_all_events(schedule)
        merged_events_path = tmp_dir / "merged_events.jsonl"
        with open(merged_events_path, "w", encoding="utf-8") as f:
            for row in merged_events:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        md_sha = _sha256_file(str(merged_details_path))
        me_sha = _sha256_file(str(merged_events_path))
        ds_hashes = _compute_dataset_hashes(raw_paths=raw_dataset_paths,
                                            enriched_paths=enriched_dataset_paths)
        sched_hash = _compute_schedule_hash(schedule)
        gate_serializable = dict(gate_result)
        if "delta_by_year_repeat" in gate_serializable:
            gate_serializable["delta_by_year_repeat"] = {
                f"{y}_{r}": v for (y, r), v in gate_result["delta_by_year_repeat"].items()
            }
        audit = {
            "run_id": archive_run_id,
            "user_run_id": run_id,
            "experiment_id": "6b2",
            "stage": stage,
            "frozen_date": FROZEN_DATE,
            "provider": provider,
            "model": model,
            "code_fingerprint": code_fp,
            "sched_hash": sched_hash,
            "gate_verdict": gate_result["verdict"],
            "gate_detail": gate_serializable,
            "dataset_hashes": ds_hashes,
            "merged_details_sha256": md_sha,
            "merged_events_sha256": me_sha,
            "budget": {"attempted": ledger.total_attempted, "hard_cap": ledger.hard_cap,
                       "slices": len(schedule["slices"]),
                       "smoke_attempted": smoke_attempted},
            "budget_hard_cap": ledger.hard_cap,
            "smoke_attempted": smoke_attempted,
            "integrity_result": integrity,
            "archived_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        audit_path = tmp_dir / "audit_index.json"
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        # Self-verify: re-read merged files and confirm SHA matches (guards against partial writes)
        if _sha256_file(str(merged_details_path)) != md_sha:
            raise SystemExit("archive 自验拒绝: merged_details.jsonl SHA 不稳定")
        if _sha256_file(str(merged_events_path)) != me_sha:
            raise SystemExit("archive 自验拒绝: merged_events.jsonl SHA 不稳定")
        receipt = {
            "verdict": gate_result["verdict"],
            "stage": stage,
            "run_id": archive_run_id,
            "user_run_id": run_id,
            "archive_dir": str(target),
            "audit_index_sha256": _sha256_file(str(audit_path)),
            "provider": provider,
            "model": model,
            "code_fingerprint": code_fp,
            "dataset_sha256": ds_hashes.get("raw") or ds_hashes.get("enriched"),
            "sched_hash": sched_hash,
            "smoke_attempted": smoke_attempted,
            "issued_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        receipt_name = f"{stage}_gate.json"
        receipt_path = tmp_dir / receipt_name
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        # Atomic publish: rename tmp → final
        os.replace(str(tmp_dir), str(target))
        return {"archive_dir": str(target), "run_id": archive_run_id, "audit": audit, "receipt": receipt}
    except Exception:
        # Clean up temp dir on any failure
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


# ── Task 17b: run_dev / run_reuse / run_2023_final entry points ──

# v18 smoke constants (single dual smoke, hard_cap=10, range [1,10])
SMOKE_GLOBAL_HARD_CAP = SMOKE_HARD_CAP  # = 10
SMOKE_SLICE_MIN = 1
SMOKE_SLICE_MAX = 10

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")


def _validate_run_id(run_id):
    """Validate run_id: must be a simple non-empty slug, no path separators,
    no absolute paths, no '.', '..', or filesystem-illegal characters.
    Raises SystemExit on violation. Called from both CLI and public entry points."""
    if not run_id or not isinstance(run_id, str):
        raise SystemExit("run_id 拒绝: 必须提供非空字符串")
    if run_id in (".", ".."):
        raise SystemExit(f"run_id 拒绝: 不能是 '.' 或 '..' (got {run_id!r})")
    if os.path.isabs(run_id):
        raise SystemExit(f"run_id 拒绝: 不能是绝对路径 (got {run_id!r})")
    if "/" in run_id or "\\" in run_id:
        raise SystemExit(f"run_id 拒绝: 不能包含路径分隔符 (got {run_id!r})")
    if not _RUN_ID_RE.match(run_id):
        raise SystemExit(
            f"run_id 拒绝: 只能包含字母/数字/_/-，且以字母/数字/_开头，长度 1-64 (got {run_id!r})")


def _verify_receipt_belongs_to_run(receipt_path, output_dir, run_id, expected_stage):
    """Verify that a receipt file is EXACTLY at output_dir/runs/<run_id>/gates/<stage>_gate.json
    and that the receipt's own user_run_id matches the current run_id exactly.
    Returns the loaded receipt dict on success."""
    rp = Path(receipt_path).resolve()
    expected_gate_root = (Path(output_dir) / "runs" / run_id / "gates").resolve()
    expected_path = expected_gate_root / f"{expected_stage}_gate.json"
    # Exact path match: reject nested/different files even under gates/
    if rp != expected_path:
        raise SystemExit(
            f"{expected_stage} receipt 路径拒绝: 期望 {expected_path}, 得到 {rp}; "
            f"receipt 必须精确位于 runs/{run_id}/gates/{expected_stage}_gate.json")
    if not rp.exists():
        raise SystemExit(f"{expected_stage} receipt 缺失: {rp}")
    receipt = json.loads(rp.read_text(encoding="utf-8"))
    # Use explicit user_run_id field if present (P1 fix), fall back to prefix split for compat
    rid = receipt.get("user_run_id") or receipt.get("run_id", "")
    if rid != run_id:
        raise SystemExit(
            f"{expected_stage} receipt run_id 不一致: receipt 中为 {rid!r}, 当前 run_id={run_id!r}")
    return receipt


def _run_all_slices(schedule, ledger, provider, model, smoke_slices=None):
    """Run all slices in schedule after OPTIONAL smoke gate (caller decides whether to
    pass smoke_slices; only dev stage runs smoke per v18). Already-completed slices
    are verified (manifest/events/integrity) rather than blindly skipped.
    Returns smoke_attempted count (0 if no smoke)."""
    import shutil
    smoke_attempted = 0
    if smoke_slices:
        print(f"[smoke] running {len(smoke_slices)} smoke slices first")
        smoke_runs_dir = Path(smoke_slices[0]["output_dir"]).parent
        smoke_ledger = BudgetLedger6B2(
            str(smoke_runs_dir / "smoke_ledger.json"),
            global_hard_cap=SMOKE_GLOBAL_HARD_CAP,
            slice_min=SMOKE_SLICE_MIN, slice_max=SMOKE_SLICE_MAX)
        for sl in smoke_slices:
            out_dir = Path(sl["output_dir"])
            state = determine_smoke_state(str(out_dir), sl["case_ids"])
            if state == "completed":
                print(f"[smoke] {sl['slice_id']}: verifying completed smoke")
                verify_smoke_completed(str(out_dir), sl["case_ids"])
                actual = sum(1 for r in _load_events(sl["events_path"]) if r.get("kind") == "call_attempt")
                smoke_ledger.record_slice_completed(sl["slice_id"], actual, arm="smoke")
                smoke_attempted += actual
                continue
            print(f"[smoke] {sl['slice_id']}: running (state={state})")
            _run_slice(sl, smoke_ledger, provider, model, integrity="smoke")
            actual = sum(1 for r in _load_events(sl["events_path"]) if r.get("kind") == "call_attempt")
            smoke_attempted += actual
        print(f"[smoke] all smoke slices passed (attempted={smoke_attempted})")
    for idx, sl in enumerate(schedule["slices"]):
        if ledger.slice_completed(sl["slice_id"]):
            print(f"[slice] {idx+1}/{len(schedule['slices'])} {sl['slice_id']}: verifying completed")
            actual = _verify_completed_slice(sl, provider, model)
            continue
        print(f"[slice] {idx+1}/{len(schedule['slices'])} {sl['slice_id']}: running")
        _run_slice(sl, ledger, provider, model)
    return smoke_attempted


def _publish_receipt_atomic(arch_result, gate_root, receipt_name):
    """Atomically publish a stage receipt to the shared gate directory."""
    import shutil
    gate_root = Path(gate_root)
    gate_root.mkdir(parents=True, exist_ok=True)
    receipt_src = Path(arch_result["archive_dir"]) / receipt_name
    receipt_dst = gate_root / receipt_name
    tmp_dst = receipt_dst.with_suffix(".tmp")
    shutil.copy2(receipt_src, tmp_dst)
    os.replace(str(tmp_dst), str(receipt_dst))


def _stage_run_dir(output_dir, run_id, stage):
    """Return runs/<run_id>/<stage> path for a stage's working directory."""
    return Path(output_dir) / "runs" / run_id / stage


def _gate_root(output_dir, run_id):
    """Return runs/<run_id>/gates path for shared receipt directory."""
    return Path(output_dir) / "runs" / run_id / "gates"


def run_dev(provider, model, output_dir, dataset_paths=None, run_id=None):
    """Run dev stage (2024+2025). run_id is REQUIRED; caller must supply a validated slug."""
    _validate_run_id(run_id)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_root = output_dir / "runs" / run_id
    runs_root.mkdir(parents=True, exist_ok=True)
    lock = OutputDirLock.acquire(str(runs_root))
    if lock is None:
        raise SystemExit(f"dev run dir locked: {runs_root}")
    try:
        years = ["2024", "2025"]
        ds_paths = dict(dataset_paths) if dataset_paths else {}
        for y in years:
            if y not in ds_paths:
                ds_paths[y] = f"benchmark/datasets/baziqa_contest8_{y}_holdout_enriched.jsonl"
        stage_dir = _stage_run_dir(output_dir, run_id, "dev")
        schedule = _build_schedule(str(stage_dir), years=years, dataset_paths=ds_paths)
        # v18: smoke ONLY runs in dev stage (single dual smoke on first year)
        smoke_slices = _build_smoke_slices(schedule)
        ledger = BudgetLedger6B2(str(stage_dir / "budget_ledger.json"),
                                global_hard_cap=DEV_REUSE_HARD_CAP)
        smoke_attempted = _run_all_slices(schedule, ledger, provider, model,
                                          smoke_slices=smoke_slices)
        merged = _merge_all_details(schedule)
        integrity = _integrity_gate(merged, schedule)
        if integrity != "PASS":
            raise SystemExit(f"dev integrity failed: {integrity}")
        gate_result = compute_gate(merged, stage="dev")
        b1c = load_b1c_advisory()
        generate_report(gate_result, merged, schedule, ledger, b1c, str(stage_dir))
        arch = generate_archive(schedule, ledger, str(stage_dir),
                                provider, model, gate_result, stage="dev",
                                raw_dataset_paths=ds_paths,
                                enriched_dataset_paths=ds_paths,
                                run_id=run_id,
                                smoke_attempted=smoke_attempted)
        _publish_receipt_atomic(arch, _gate_root(output_dir, run_id), "dev_gate.json")
        return {"status": "ok", "gate": gate_result, "archive": arch, "run_id": run_id}
    finally:
        if lock:
            lock.release()


def run_reuse(provider, model, output_dir, dev_receipt_path, dataset_paths=None, run_id=None):
    """Run reuse stage (2021+2022). run_id is REQUIRED and MUST match dev receipt's run_id.
    v18: reuse does NOT run smoke (smoke is a dev-only gate)."""
    _validate_run_id(run_id)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_root = output_dir / "runs" / run_id
    runs_root.mkdir(parents=True, exist_ok=True)
    lock = OutputDirLock.acquire(str(runs_root))
    if lock is None:
        raise SystemExit(f"reuse run dir locked: {runs_root}")
    try:
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate as _check
        code_fp = _compute_experiment_code_fingerprint()
        # Verify dev receipt belongs to this run_id and lives in this output_dir's gates/
        _verify_receipt_belongs_to_run(dev_receipt_path, output_dir, run_id, "dev")
        gate_root = _gate_root(output_dir, run_id)
        _check("reuse", gate_root=str(gate_root),
               provider=provider, model=model, current_code_fingerprint=code_fp,
               expected_user_run_id=run_id)
        years = ["2021", "2022"]
        ds_paths = dict(dataset_paths) if dataset_paths else {}
        for y in years:
            if y not in ds_paths:
                ds_paths[y] = f"benchmark/datasets/baziqa_contest8_{y}_holdout_enriched.jsonl"
        stage_dir = _stage_run_dir(output_dir, run_id, "reuse")
        schedule = _build_schedule(str(stage_dir), years=years, dataset_paths=ds_paths)
        # v18: no smoke in reuse stage
        ledger = BudgetLedger6B2(str(stage_dir / "budget_ledger.json"),
                                global_hard_cap=DEV_REUSE_HARD_CAP)
        _run_all_slices(schedule, ledger, provider, model, smoke_slices=None)
        merged = _merge_all_details(schedule)
        integrity = _integrity_gate(merged, schedule)
        if integrity != "PASS":
            raise SystemExit(f"reuse integrity failed: {integrity}")
        gate_result = compute_gate(merged, stage="reuse")
        b1c = load_b1c_advisory()
        generate_report(gate_result, merged, schedule, ledger, b1c, str(stage_dir))
        arch = generate_archive(schedule, ledger, str(stage_dir),
                                provider, model, gate_result, stage="reuse",
                                raw_dataset_paths=ds_paths,
                                enriched_dataset_paths=ds_paths,
                                run_id=run_id,
                                smoke_attempted=0)
        _publish_receipt_atomic(arch, gate_root, "reuse_gate.json")
        return {"status": "ok", "gate": gate_result, "archive": arch, "run_id": run_id}
    finally:
        if lock:
            lock.release()


def run_2023_final(provider, model, output_dir, reuse_receipt_path, dataset_paths=None, run_id=None):
    """Run 2023 final sealed stage. run_id is REQUIRED and MUST match reuse receipt's run_id.
    v18: final does NOT run smoke."""
    _validate_run_id(run_id)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_root = output_dir / "runs" / run_id
    runs_root.mkdir(parents=True, exist_ok=True)
    lock = OutputDirLock.acquire(str(runs_root))
    if lock is None:
        raise SystemExit(f"2023_final run dir locked: {runs_root}")
    try:
        from scripts.phase6_6b2_sealed_workflow import (
            check_stage_gate as _check, acquire_2023_run_lock,
            verify_2023_raw_data, record_enriched_sha_to_lock, finalize_2023_run_lock,
            enrich_year, update_lock_schedule_hash, BLESSED_2023_RAW_SHA256)
        code_fp = _compute_experiment_code_fingerprint()
        _verify_receipt_belongs_to_run(reuse_receipt_path, output_dir, run_id, "reuse")
        gate_root = _gate_root(output_dir, run_id)
        _check("final_2023", gate_root=str(gate_root),
               provider=provider, model=model, current_code_fingerprint=code_fp,
               expected_user_run_id=run_id)
        ds_paths_in = dict(dataset_paths) if dataset_paths else {}
        raw_path = ds_paths_in.get("2023", "benchmark/datasets/baziqa_contest8_2023_holdout.jsonl")
        archive_run_id = f"{run_id}-6b2-final_2023-{FROZEN_DATE}-{provider}-{model}-{code_fp[:12]}"
        lock_path = runs_root / "2023.lock"
        lock_status = acquire_2023_run_lock(str(lock_path), archive_run_id, code_fp, "pending",
                                            budget_hard_cap=FINAL_2023_HARD_CAP)
        verify_2023_raw_data(raw_path, BLESSED_2023_RAW_SHA256)
        stage_dir = _stage_run_dir(output_dir, run_id, "final_2023")
        stage_dir.mkdir(parents=True, exist_ok=True)
        enriched_path = stage_dir / "baziqa_contest8_2023_holdout_enriched.jsonl"
        if lock_status == "NEW" or not enriched_path.exists():
            enrich_year("2023", raw_path, str(enriched_path))
        record_enriched_sha_to_lock(str(lock_path), str(enriched_path))
        raw_paths = {"2023": raw_path}
        enriched_paths = {"2023": str(enriched_path)}
        schedule = _build_schedule(str(stage_dir), years=["2023"], dataset_paths=enriched_paths)
        sched_hash = _compute_schedule_hash(schedule)
        update_lock_schedule_hash(str(lock_path), sched_hash)
        # v18: no smoke in 2023 final stage
        ledger = BudgetLedger6B2(str(stage_dir / "budget_ledger.json"),
                                global_hard_cap=FINAL_2023_HARD_CAP)
        _run_all_slices(schedule, ledger, provider, model, smoke_slices=None)
        merged = _merge_all_details(schedule)
        integrity = _integrity_gate(merged, schedule)
        gate_result = compute_gate(merged, stage="final_2023")
        b1c = load_b1c_advisory()
        generate_report(gate_result, merged, schedule, ledger, b1c, str(stage_dir))
        arch = generate_archive(schedule, ledger, str(stage_dir), provider, model,
                                gate_result, stage="final_2023",
                                raw_dataset_paths=raw_paths,
                                enriched_dataset_paths=enriched_paths,
                                run_id=run_id,
                                smoke_attempted=0)
        finalize_2023_run_lock(str(lock_path), arch["archive_dir"],
                               gate_result["verdict"],
                               schedule_complete=True,
                               integrity_passed=(integrity == "PASS"))
        _publish_receipt_atomic(arch, gate_root, "final_2023_gate.json")
        return {"status": "ok", "gate": gate_result, "archive": arch, "run_id": run_id}
    finally:
        if lock:
            lock.release()


def _parse_dataset_path_args(args_list):
    """Parse --dataset-path key=value arguments into a dict."""
    result = {}
    if not args_list:
        return result
    for item in args_list:
        if "=" not in item:
            raise SystemExit(f"--dataset-path 格式错误 (需要 key=value): {item}")
        k, v = item.split("=", 1)
        result[k.strip()] = v.strip()
    return result


def main():
    parser = argparse.ArgumentParser(description="Phase 6 6B2 orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd_name in ("run_dev", "run_reuse", "run_2023_final"):
        p = sub.add_parser(cmd_name)
        p.add_argument("--provider", required=True)
        p.add_argument("--model", required=True)
        p.add_argument("--output-dir", required=True)
        p.add_argument("--run-id", required=True,
                       help="实验运行标识 (同一实验 dev/reuse/final 必须共用同一 run_id)")
        p.add_argument("--dataset-path", action="append", default=[],
                       help="数据集路径覆盖，格式 year=path，可多次指定")
        if cmd_name == "run_reuse":
            p.add_argument("--dev-receipt", required=True,
                           help="dev 阶段 receipt 路径 (runs/<run_id>/gates/dev_gate.json)")
        if cmd_name == "run_2023_final":
            p.add_argument("--reuse-receipt", required=True,
                           help="reuse 阶段 receipt 路径 (runs/<run_id>/gates/reuse_gate.json)")
    args = parser.parse_args()
    ds_paths = _parse_dataset_path_args(args.dataset_path)
    if args.cmd == "run_dev":
        result = run_dev(args.provider, args.model, args.output_dir,
                         dataset_paths=ds_paths, run_id=args.run_id)
    elif args.cmd == "run_reuse":
        result = run_reuse(args.provider, args.model, args.output_dir,
                           args.dev_receipt, dataset_paths=ds_paths, run_id=args.run_id)
    elif args.cmd == "run_2023_final":
        result = run_2023_final(args.provider, args.model, args.output_dir,
                                args.reuse_receipt, dataset_paths=ds_paths, run_id=args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
