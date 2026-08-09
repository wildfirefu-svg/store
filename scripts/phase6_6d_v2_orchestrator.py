#!/usr/bin/env python3
"""Phase 6 6D orchestrator - bazi time-context paired ablation protocol v1.

Implements Task 8 of the 6D v1 plan. Independent of 6B2 (does NOT share
6B2 schedule/gate/receipt). Runs a paired off/on ablation over the frozen
temporal routed manifest with group-pair-level AB/BA scheduling.

Frozen protocol: deepseek-v4-flash / disabled / temperature 0.0 /
profile baziqa_xjz_reasoned / method direct_choice.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
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

# -- Frozen constants (single source of truth) --

FROZEN_DATE = "2026-08-07"
FROZEN_PROVIDER = "deepseek"
FROZEN_MODEL = "deepseek-v4-flash"
FROZEN_THINKING_MODE = "disabled"
FROZEN_TEMPERATURE = 0.0
FROZEN_PROFILE = "baziqa_xjz_reasoned"
FROZEN_METHOD = "direct_choice"
MODEL_LABEL = "DeepSeek-V4-Flash non-thinking"
TEMPORAL_CONTEXT_VERSION = "6d-v2"
EXPERIMENT_ID = "6d-v2"
CHART_SCHEMA = "legacy_v0"

ROUTED_MANIFEST_PATH = "docs/phase6/6d/temporal_routed_cases.json"
PHASE1_RECEIPT_PATH = "docs/phase6/6d/phase1_receipt.json"
ARCHIVE_ROOT = "docs/phase6/6d"

PER_GROUP = 8
REPEATS = 3
ARMS = ("b1a_time_off", "b1a_time_on")
EXPERIMENT_CONDITIONS = ("off", "on")
PARSER_RATE_MIN = 0.85
PHASE1_N_ROUTED_MIN = 20


# -- Frozen protocol validation --


def _validate_frozen_protocol(provider, model, thinking_mode, temperature, profile, method):
    protocol = {
        "provider": FROZEN_PROVIDER,
        "model": FROZEN_MODEL,
        "thinking_mode": FROZEN_THINKING_MODE,
        "temperature": FROZEN_TEMPERATURE,
        "profile": FROZEN_PROFILE,
        "method": FROZEN_METHOD,
        "model_label": MODEL_LABEL,
    }
    checks = [
        ("provider", provider, FROZEN_PROVIDER),
        ("model", model, FROZEN_MODEL),
        ("thinking_mode", thinking_mode, FROZEN_THINKING_MODE),
        ("temperature", temperature, FROZEN_TEMPERATURE),
        ("profile", profile, FROZEN_PROFILE),
        ("method", method, FROZEN_METHOD),
    ]
    for name, actual, expected in checks:
        if name == "temperature":
            if float(actual) != float(expected):
                raise SystemExit(
                    f"6D frozen protocol mismatch: {name}={actual!r}, "
                    f"required={expected!r}")
        elif actual != expected:
            raise SystemExit(
                f"6D frozen protocol mismatch: {name}={actual!r}, "
                f"required={expected!r}")
    return protocol


# -- Helpers --


def _sha256_file(path):
    h = hashlib.sha256()
    if not os.path.exists(path):
        return "0" * 64
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_sha256(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_dict_sha256(d):
    canonical = json.dumps(d, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_events(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def _load_routed_entries(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(p))


def _json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _compute_hard_cap(scheduled_calls):
    reserve = int(math.ceil(scheduled_calls * 0.10 / 10.0)) * 10
    return scheduled_calls + reserve


def _year_from_dataset_id(dataset_id):
    m = re.search(r"baziqa_contest8_(\d{4})_holdout", dataset_id or "")
    return m.group(1) if m else None


def _dataset_path_for_year(year):
    return os.path.join("benchmark", "datasets",
                        f"baziqa_contest8_{year}_holdout_enriched.jsonl")


# -- AB/BA group-pair scheduling --


def _assign_group_abba_order(year, group_idx):
    parity = hashlib.sha256(f"{year}:{group_idx}".encode()).digest()[0] & 1
    return "BA" if parity == 1 else "AB"


# -- Schedule metadata (no output_dir needed) --


def _compute_schedule_metadata(routed_manifest_path):
    entries = _load_routed_entries(routed_manifest_path)
    by_year = defaultdict(list)
    for e in entries:
        by_year[e["year"]].append(e)
    years = sorted(by_year.keys())
    groups_per_year = {}
    n_cases_per_year = {}
    per_slice_scheduled = []
    group_abba_order = {}
    for year in years:
        year_entries = by_year[year]
        n_cases_per_year[year] = len(year_entries)
        n_groups = math.ceil(len(year_entries) / PER_GROUP)
        groups_per_year[year] = n_groups
        year_scheduled = []
        for g in range(n_groups):
            start = g * PER_GROUP
            end = start + PER_GROUP
            group_entries = year_entries[start:end]
            scheduled = len(group_entries)
            year_scheduled.append(scheduled)
            group_abba_order[f"{year}:g{g}"] = _assign_group_abba_order(year, g)
        per_slice_scheduled.append(year_scheduled)
    return {
        "years": years,
        "groups_per_year": groups_per_year,
        "n_cases_per_year": n_cases_per_year,
        "per_slice_scheduled": per_slice_scheduled,
        "group_abba_order": group_abba_order,
    }


# -- Schedule (full, with output_dir) --


def _build_schedule(output_dir, routed_manifest_path=ROUTED_MANIFEST_PATH):
    entries = _load_routed_entries(routed_manifest_path)
    by_year = defaultdict(list)
    for e in entries:
        by_year[e["year"]].append(e)
    years = sorted(by_year.keys())
    routed_sha = _canonical_json_sha256(routed_manifest_path)
    slices = []
    groups_per_year = {}
    n_cases_per_year = {}
    per_slice_scheduled = []
    group_abba_order = {}
    for year in years:
        year_entries = by_year[year]
        n_cases_per_year[year] = len(year_entries)
        n_groups = math.ceil(len(year_entries) / PER_GROUP)
        groups_per_year[year] = n_groups
        dataset_path = _dataset_path_for_year(year)
        year_scheduled = []
        for g in range(n_groups):
            start = g * PER_GROUP
            end = start + PER_GROUP
            group_entries = year_entries[start:end]
            scheduled = len(group_entries)
            year_scheduled.append(scheduled)
            case_ids = [e["case_id"] for e in group_entries]
            order = _assign_group_abba_order(year, g)
            group_abba_order[f"{year}:g{g}"] = order
            hard_cap = _compute_hard_cap(scheduled)
            for rep in range(REPEATS):
                arm_order = ARMS if order == "AB" else tuple(reversed(ARMS))
                for arm in arm_order:
                    injection = "off" if arm == "b1a_time_off" else "on"
                    slice_id = f"{year}_{arm}_r{rep}_g{g}"
                    out_dir = os.path.join(output_dir, slice_id)
                    slices.append({
                        "year": year, "repeat": rep, "arm": arm, "group": g,
                        "slice_id": slice_id, "output_dir": out_dir,
                        "detail_path": os.path.join(out_dir, "details.jsonl"),
                        "events_path": os.path.join(out_dir, "details.events.jsonl"),
                        "case_ids_file": os.path.join(out_dir, "case_ids.json"),
                        "dataset_path": dataset_path,
                        "profile": FROZEN_PROFILE, "method": FROZEN_METHOD,
                        "hard_cap": hard_cap, "max_cases": scheduled,
                        "scheduled_calls": scheduled, "case_ids": case_ids,
                        "thinking_mode": FROZEN_THINKING_MODE,
                        "time_context_injection": injection,
                        "routed_manifest_path": routed_manifest_path,
                        "routed_manifest_sha256": routed_sha,
                    })
        per_slice_scheduled.append(year_scheduled)
    total_scheduled = sum(s["scheduled_calls"] for s in slices)
    global_hard_cap = sum(s["hard_cap"] for s in slices)
    return {
        "slices": slices,
        "global_hard_cap": global_hard_cap,
        "total_scheduled_calls": total_scheduled,
        "total_slices": len(slices),
        "years": years,
        "groups_per_year": groups_per_year,
        "n_cases_per_year": n_cases_per_year,
        "per_slice_scheduled": per_slice_scheduled,
        "group_abba_order": group_abba_order,
    }


# -- BudgetLedger --


class BudgetLedger:
    def __init__(self, ledger_path, global_hard_cap=486):
        self.path = Path(ledger_path)
        self._init_hard_cap = global_hard_cap
        self.hard_cap = global_hard_cap
        self.total_scheduled = 0
        self.total_attempted = 0
        self._completed = set()
        self.attempts_by_slice = {}
        self._load()

    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            file_hard_cap = data.get("hard_cap")
            if file_hard_cap is not None and file_hard_cap != self._init_hard_cap:
                raise SystemExit(
                    f"BudgetLedger reject: file hard_cap ({file_hard_cap}) "
                    f"!= init ({self._init_hard_cap})")
            self.hard_cap = data.get("hard_cap", self._init_hard_cap)
            self.total_attempted = data.get("total_attempted", 0)
            self.total_scheduled = data.get("total_scheduled", 0)
            self._completed = set(data.get("completed_slices", []))
            self.attempts_by_slice = data.get("attempts_by_slice", {})
        else:
            self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "total_attempted": self.total_attempted,
            "total_scheduled": self.total_scheduled,
            "completed_slices": sorted(self._completed),
            "attempts_by_slice": self.attempts_by_slice,
            "hard_cap": self.hard_cap,
        }, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(self.path))

    def record_slice_completed(self, slice_id, actual_attempts, scheduled_calls):
        if slice_id in self._completed:
            return
        if self.total_attempted + actual_attempts > self.hard_cap:
            raise SystemExit(
                f"BudgetLedger reject: slice {slice_id} would exceed hard_cap "
                f"({self.total_attempted}+{actual_attempts}>{self.hard_cap})")
        self._completed.add(slice_id)
        self.attempts_by_slice[slice_id] = actual_attempts
        self.total_attempted += actual_attempts
        self.total_scheduled += scheduled_calls
        self._save()

    def slice_completed(self, slice_id):
        return slice_id in self._completed

    def can_attempt(self, extra=0):
        return self.total_attempted + extra <= self.hard_cap

    def remaining_budget(self):
        return self.hard_cap - self.total_attempted


# -- Provenance computation --


def _compute_extraction_strategy_sha256():
    from benchmark.formatters.bazi_time_context import (
        classify_route_state,
        detect_temporal_rules,
        extract_target_years,
    )
    parts = []
    for fn in (detect_temporal_rules, extract_target_years, classify_route_state):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    return hashlib.sha256("".join(parts).encode()).hexdigest()


def _compute_dataset_sha256_by_year(routed_manifest_path):
    entries = _load_routed_entries(routed_manifest_path)
    sha_by_year = {}
    for e in entries:
        if e["year"] not in sha_by_year:
            sha_by_year[e["year"]] = e["dataset_sha256"]
    return sha_by_year


def _compute_experiment_code_fingerprint():
    parts = []
    for fn in (_build_schedule, _compute_schedule_metadata, _assign_group_abba_order,
               _build_runner_command, _run_slice, _merge_details,
               _check_completeness, compute_6d_gate, check_6d_gate,
               _generate_report, _create_archive, _validate_frozen_protocol,
               _prepare_run_context, run_dev, build_run_manifest,
               _validate_phase1_receipt, _validate_four_layer_provenance,
               _publish_receipt_atomic):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    for fn_name in ("__init__", "record_slice_completed", "can_attempt",
                    "slice_completed", "remaining_budget"):
        fn = getattr(BudgetLedger, fn_name, None)
        if fn is not None:
            parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    try:
        from benchmark.runners.run_benchmark import _code_fingerprint as _runner_fp
    except (ImportError, AttributeError) as exc:
        raise SystemExit(
            f"runner code fingerprint unavailable: {exc}") from exc
    parts.append(_runner_fp())
    return hashlib.sha256("".join(parts).encode()).hexdigest()


# -- Run manifest (8 temporal run-level fields) --


def build_run_manifest(provider, model, protocol, code_fingerprint,
                       routed_manifest_path):
    metadata = _compute_schedule_metadata(routed_manifest_path)
    routed_sha = _canonical_json_sha256(routed_manifest_path)
    extraction_sha = _compute_extraction_strategy_sha256()
    dataset_sha_by_year = _compute_dataset_sha256_by_year(routed_manifest_path)
    dataset_set_sha = _canonical_dict_sha256(dataset_sha_by_year)
    condition_manifest = {
        "conditions": list(EXPERIMENT_CONDITIONS),
        "arms": list(ARMS),
        "years": metadata["years"],
        "n_cases_per_year": metadata["n_cases_per_year"],
        "groups_per_year": metadata["groups_per_year"],
        "repeats": REPEATS,
        "per_slice_scheduled": metadata["per_slice_scheduled"],
        "temporal_context_version": TEMPORAL_CONTEXT_VERSION,
        "extraction_strategy_sha256": extraction_sha,
        "temporal_routed_cases_sha256": routed_sha,
        "group_abba_order": metadata["group_abba_order"],
    }
    condition_manifest_sha = _canonical_dict_sha256(condition_manifest)
    return {
        "provider": provider,
        "model": model,
        "thinking_mode": protocol["thinking_mode"],
        "model_label": protocol["model_label"],
        "code_fingerprint": code_fingerprint,
        "temporal_context_version": TEMPORAL_CONTEXT_VERSION,
        "experiment_conditions": list(EXPERIMENT_CONDITIONS),
        "extraction_strategy_sha256": extraction_sha,
        "temporal_routed_cases_sha256": routed_sha,
        "condition_manifest_sha256": condition_manifest_sha,
        "dataset_sha256_by_year": dataset_sha_by_year,
        "dataset_set_sha256": dataset_set_sha,
        "group_abba_order": metadata["group_abba_order"],
    }


# -- Runner command --


def _build_runner_command(slice_info, provider, model, resume=False):
    case_ids_file = slice_info["case_ids_file"]
    os.makedirs(os.path.dirname(case_ids_file), exist_ok=True)
    with open(case_ids_file, "w", encoding="utf-8") as f:
        json.dump(slice_info["case_ids"], f)
    base = [sys.executable, "-m", "benchmark.runners.run_benchmark"]
    cmd = base + [
        "--dataset", slice_info["dataset_path"],
        "--profile", FROZEN_PROFILE,
        "--method", FROZEN_METHOD,
        "--attempt-stage", "main",
        "--arm", slice_info["arm"],
        "--ziwei-arm", "none",
        "--repeat-idx", str(slice_info["repeat"]),
        "--hard-cap", str(slice_info["hard_cap"]),
        "--provider", provider,
        "--model", model,
        "--model-runner",
        "--case-details-jsonl", slice_info["detail_path"],
        "--case-ids-file", case_ids_file,
        "--max-cases", str(slice_info["max_cases"]),
        "--scheduled-calls", str(slice_info["scheduled_calls"]),
        "--temperature", str(FROZEN_TEMPERATURE),
        "--output-dir", slice_info["output_dir"],
        "--as-of-date", FROZEN_DATE,
        "--chart-schema-version", CHART_SCHEMA,
        "--thinking-mode", slice_info["thinking_mode"],
        "--time-context-injection", slice_info["time_context_injection"],
        "--temporal-routed-cases-file", slice_info["routed_manifest_path"],
    ]
    if resume:
        cmd.append("--resume")
    return cmd


def _slice_runner_args(slice_info, provider, model):
    return types.SimpleNamespace(
        dataset=slice_info["dataset_path"],
        case_ids_file=slice_info["case_ids_file"],
        profile=slice_info["profile"],
        chart_schema_version=CHART_SCHEMA,
        arm=slice_info["arm"],
        ziwei_arm="none",
        attempt_stage="main",
        repeat_idx=slice_info["repeat"],
        provider=provider,
        model=model,
        temperature=FROZEN_TEMPERATURE,
        sample_temperature=0.4,
        n_samples=1,
        aggregate="majority",
        method=slice_info["method"],
        scheduled_calls=slice_info["scheduled_calls"],
        hard_cap=slice_info["hard_cap"],
        as_of_date=FROZEN_DATE,
        thinking_mode=slice_info["thinking_mode"],
        time_context_injection=slice_info["time_context_injection"],
        temporal_routed_cases_file=slice_info["routed_manifest_path"],
    )


# -- OutputDirLock (token-based) --


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


# -- Slice execution --


def _run_slice(slice_info, ledger, provider, model):
    out_dir = Path(slice_info["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "slice_status.json"
    detail_path = Path(slice_info["detail_path"])
    events_path = Path(slice_info["events_path"])
    runner_manifest_path = Path(str(detail_path).replace(".jsonl", ".manifest.json"))
    lock = None
    try:
        lock = OutputDirLock.acquire(str(out_dir))
        if lock is None:
            raise SystemExit(f"slice {slice_info['slice_id']} dir locked")
        current_routed_sha = _canonical_json_sha256(slice_info["routed_manifest_path"])
        if current_routed_sha != slice_info["routed_manifest_sha256"]:
            raise SystemExit(
                f"slice {slice_info['slice_id']} pre-launch reject: routed manifest SHA drift")
        is_resume = False
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("completed") and status.get("slice_id") == slice_info["slice_id"]:
                if not runner_manifest_path.exists():
                    raise SystemExit(f"slice {slice_info['slice_id']} resume reject: manifest missing")
                from benchmark.runners.profiles import resolve_profile
                from benchmark.runners.run_benchmark import (
                    build_resume_manifest,
                    check_resume_manifest,
                )
                profile_obj = resolve_profile(slice_info["profile"], CHART_SCHEMA)
                current_manifest = build_resume_manifest(
                    _slice_runner_args(slice_info, provider, model), profile_obj)
                check_resume_manifest(str(runner_manifest_path), current_manifest)
                if not events_path.exists():
                    raise SystemExit(f"slice {slice_info['slice_id']} resume reject: events missing")
                actual = sum(1 for r in _load_events(str(events_path))
                             if r.get("kind") == "call_attempt")
                if actual != status.get("actual_attempts", -1):
                    raise SystemExit(f"slice {slice_info['slice_id']} resume reject: attempts mismatch")
                ledger.record_slice_completed(
                    slice_info["slice_id"], actual,
                    slice_info["scheduled_calls"])
                return
            is_resume = True
        elif runner_manifest_path.exists() or events_path.exists() or detail_path.exists():
            is_resume = True
        existing_attempts = 0
        if is_resume and events_path.exists():
            existing_attempts = sum(1 for r in _load_events(str(events_path))
                                    if r.get("kind") == "call_attempt")
        remaining = slice_info["hard_cap"] - existing_attempts
        if remaining < 0:
            raise SystemExit(f"slice {slice_info['slice_id']} resume reject: events exceed hard_cap")
        if ledger.total_attempted + existing_attempts + remaining > ledger.hard_cap:
            raise SystemExit(f"slice {slice_info['slice_id']} reject: budget insufficient")
        cmd = _build_runner_command(slice_info, provider, model, resume=is_resume)
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=1800, cwd=_PROJECT_ROOT)
        elapsed = time.time() - start
        if result.returncode != 0:
            raise SystemExit(
                f"slice {slice_info['slice_id']} failed (exit={result.returncode}): "
                f"{result.stderr[:500]}")
        if not detail_path.exists() or detail_path.stat().st_size == 0:
            raise SystemExit(f"slice {slice_info['slice_id']} failed: detail jsonl empty/missing")
        if not events_path.exists() or events_path.stat().st_size == 0:
            raise SystemExit(f"slice {slice_info['slice_id']} failed: events jsonl empty/missing")
        if not runner_manifest_path.exists():
            raise SystemExit(f"slice {slice_info['slice_id']} failed: runner manifest missing")
        actual = sum(1 for r in _load_events(str(events_path))
                     if r.get("kind") == "call_attempt")
        runner_manifest_sha = _sha256_file(str(runner_manifest_path))
        response_models = {
            row.get("response_model")
            for row in _load_events(str(events_path))
            if row.get("kind") == "call_meta" and row.get("response_model")
        }
        if len(response_models) > 1:
            raise SystemExit(
                f"slice {slice_info['slice_id']} response_model drift: "
                f"{sorted(response_models)}")
        response_model = next(iter(response_models), None)
        status_path.write_text(json.dumps({
            "slice_id": slice_info["slice_id"], "completed": True,
            "exit_code": result.returncode, "elapsed_s": round(elapsed, 1),
            "actual_attempts": actual,
            "scheduled_calls": slice_info["scheduled_calls"],
            "hard_cap": slice_info["hard_cap"], "remaining_reserved": remaining,
            "runner_manifest_sha256": runner_manifest_sha,
            "arm": slice_info["arm"],
            "time_context_injection": slice_info["time_context_injection"],
            "method": FROZEN_METHOD,
            "provider": provider, "requested_model": model,
            "thinking_mode": slice_info["thinking_mode"],
            "response_model": response_model,
        }, ensure_ascii=False), encoding="utf-8")
        ledger.record_slice_completed(
            slice_info["slice_id"], actual, slice_info["scheduled_calls"])
    finally:
        if lock is not None:
            lock.release()


def _verify_completed_slice(slice_info, provider, model):
    out_dir = Path(slice_info["output_dir"])
    detail_path = Path(slice_info["detail_path"])
    events_path = Path(slice_info["events_path"])
    runner_manifest_path = Path(str(detail_path).replace(".jsonl", ".manifest.json"))
    status_path = out_dir / "slice_status.json"
    if not status_path.exists():
        raise SystemExit(f"slice {slice_info['slice_id']} verify reject: status missing")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if not status.get("completed"):
        raise SystemExit(f"slice {slice_info['slice_id']} verify reject: not completed")
    if status.get("slice_id") != slice_info["slice_id"]:
        raise SystemExit(f"slice {slice_info['slice_id']} verify reject: slice_id mismatch")
    if not runner_manifest_path.exists():
        raise SystemExit(f"slice {slice_info['slice_id']} verify reject: manifest missing")
    from benchmark.runners.profiles import resolve_profile
    from benchmark.runners.run_benchmark import (
        build_resume_manifest,
        check_resume_manifest,
    )
    profile_obj = resolve_profile(slice_info["profile"], CHART_SCHEMA)
    current_manifest = build_resume_manifest(
        _slice_runner_args(slice_info, provider, model), profile_obj)
    check_resume_manifest(str(runner_manifest_path), current_manifest)
    if not events_path.exists():
        raise SystemExit(f"slice {slice_info['slice_id']} verify reject: events missing")
    if not detail_path.exists():
        raise SystemExit(f"slice {slice_info['slice_id']} verify reject: detail missing")
    actual = sum(1 for r in _load_events(str(events_path))
                 if r.get("kind") == "call_attempt")
    if actual != status.get("actual_attempts", -1):
        raise SystemExit(f"slice {slice_info['slice_id']} verify reject: attempts mismatch")
    return actual


def _run_all_slices(schedule, ledger, provider, model):
    for idx, sl in enumerate(schedule["slices"]):
        if ledger.slice_completed(sl["slice_id"]):
            print(f"[slice] {idx+1}/{len(schedule['slices'])} {sl['slice_id']}: verifying completed")
            _verify_completed_slice(sl, provider, model)
            continue
        print(f"[slice] {idx+1}/{len(schedule['slices'])} {sl['slice_id']}: running")
        _run_slice(sl, ledger, provider, model)


# -- Merge + completeness --


def _merge_details(slices):
    merged = []
    for sl in slices:
        if os.path.exists(sl["detail_path"]):
            merged.extend(_load_events(sl["detail_path"]))
    return merged


def _detail_identity(row):
    ak = row.get("attempt_key") or [None] * 10
    year = _year_from_dataset_id(ak[0])
    rep = int(ak[7]) if ak[7] is not None else 0
    cid = ak[6] or row.get("case_id")
    arm = ak[2]
    stage = ak[3]
    return year, rep, cid, arm, stage


def _check_completeness(merged, schedule):
    by_cell = defaultdict(lambda: defaultdict(list))
    for r in merged:
        year, rep, cid, arm, stage = _detail_identity(r)
        by_cell[(year, rep, cid)][arm].append(stage)
    expected_cells = set()
    for sl in schedule["slices"]:
        for cid in sl["case_ids"]:
            expected_cells.add((sl["year"], sl["repeat"], cid))
    for cell in expected_cells:
        arms = by_cell.get(cell, {})
        off_stages = arms.get("b1a_time_off", [])
        on_stages = arms.get("b1a_time_on", [])
        off_mains = [s for s in off_stages if s == "main"]
        on_mains = [s for s in on_stages if s == "main"]
        if len(off_mains) != 1:
            return f"OFF_MAIN_COUNT: {cell} = {len(off_mains)}"
        if len(on_mains) != 1:
            return f"ON_MAIN_COUNT: {cell} = {len(on_mains)}"
    extra = set(by_cell.keys()) - expected_cells
    if extra:
        return f"EXTRA_CELLS: {sorted(extra)[:3]}..."
    return "PASS"


# -- Gate --


def compute_6d_gate(details, n_cases):
    off_rows = [r for r in details
                if (r.get("attempt_key") or [None] * 10)[2] == "b1a_time_off"]
    on_rows = [r for r in details
               if (r.get("attempt_key") or [None] * 10)[2] == "b1a_time_on"]
    for arm_name, rows in (("b1a_time_off", off_rows), ("b1a_time_on", on_rows)):
        call_failed = sum(1 for r in rows if r.get("terminal_state") == "call_failed")
        if call_failed > 0:
            return {"verdict": "BLOCKED", "reason": f"{arm_name}_call_failed",
                    "call_failed": call_failed, "stage": "dev",
                    "paired_delta": None, "min_case_delta": None}
        total = max(len(rows), 1)
        parsed = sum(1 for r in rows if r.get("terminal_state") == "parsed")
        parser_rate = parsed / total
        if parser_rate < PARSER_RATE_MIN:
            return {"verdict": "BLOCKED", "reason": f"{arm_name}_parser_rate",
                    "parser_rate": round(parser_rate, 4), "stage": "dev",
                    "paired_delta": None, "min_case_delta": None}
    by_case = defaultdict(lambda: {"off_correct": 0, "on_correct": 0})
    for r in off_rows:
        cid = (r.get("attempt_key") or [None] * 10)[6] or r.get("case_id")
        by_case[cid]["off_correct"] += 1 if r.get("correct") else 0
    for r in on_rows:
        cid = (r.get("attempt_key") or [None] * 10)[6] or r.get("case_id")
        by_case[cid]["on_correct"] += 1 if r.get("correct") else 0
    case_deltas = {}
    for cid, v in by_case.items():
        case_deltas[cid] = v["on_correct"] - v["off_correct"]
    denominator = n_cases * REPEATS
    paired_delta = sum(case_deltas.values()) / denominator if denominator else 0.0
    min_case_delta = min(case_deltas.values()) / REPEATS if case_deltas else 0.0
    if paired_delta >= 0.05 and min_case_delta >= 0:
        verdict = "PROMOTE"
    elif paired_delta >= 0.05 and min_case_delta < 0:
        verdict = "REVIEW_REQUIRED"
    elif -0.02 <= paired_delta < 0.05:
        verdict = "NON_INFERIOR"
    else:
        verdict = "ROLLBACK"
    return {
        "verdict": verdict,
        "paired_delta": round(paired_delta, 6),
        "min_case_delta": round(min_case_delta, 6),
        "n_cases": n_cases,
        "case_deltas": case_deltas,
        "stage": "dev",
    }


# -- Receipt required fields --

SIXD_RECEIPT_REQUIRED_FIELDS = (
    "verdict", "stage", "run_id", "user_run_id", "archive_dir",
    "audit_index_sha256", "provider", "model",
    "thinking_mode", "model_label",
    "code_fingerprint", "dataset_set_sha256",
    "temporal_context_version", "experiment_conditions",
    "extraction_strategy_sha256", "temporal_routed_cases_sha256",
    "condition_manifest_sha256", "dataset_sha256_by_year",
    "group_abba_order",
)


def check_6d_gate(receipt):
    missing = [f for f in SIXD_RECEIPT_REQUIRED_FIELDS if f not in receipt]
    if missing:
        raise SystemExit(f"6D receipt missing fields: {missing}")
    if receipt.get("temporal_context_version") != TEMPORAL_CONTEXT_VERSION:
        raise SystemExit(
            f"6D receipt temporal_context_version mismatch: "
            f"{receipt.get('temporal_context_version')!r} != {TEMPORAL_CONTEXT_VERSION!r}")
    expected_conditions = list(EXPERIMENT_CONDITIONS)
    if receipt.get("experiment_conditions") != expected_conditions:
        raise SystemExit(
            f"6D receipt experiment_conditions mismatch: "
            f"{receipt.get('experiment_conditions')!r} != {expected_conditions!r}")
    # Audit verification (fail-closed): archive_dir must exist and contain
    # audit_index.json whose SHA-256 matches the receipt.
    archive_dir = receipt.get("archive_dir")
    audit_index_sha = receipt.get("audit_index_sha256")
    if not archive_dir:
        raise SystemExit(
            "6D receipt audit verification: archive_dir missing in receipt")
    if not audit_index_sha:
        raise SystemExit(
            "6D receipt audit verification: audit_index_sha256 missing in receipt")
    if not os.path.isdir(archive_dir):
        raise SystemExit(
            f"6D receipt audit verification: archive_dir not found: {archive_dir}")
    audit_path = os.path.join(archive_dir, "audit_index.json")
    if not os.path.exists(audit_path):
        raise SystemExit(
            f"6D receipt audit verification: audit_index.json missing: {audit_path}")
    actual_audit_sha = _sha256_file(audit_path)
    if actual_audit_sha != audit_index_sha:
        raise SystemExit(
            f"6D receipt audit_index_sha256 mismatch: "
            f"receipt={audit_index_sha!r} current={actual_audit_sha!r}")
    return True


# -- Four-layer provenance cross-validation --


_FOUR_LAYER_PROVENANCE_FIELDS = (
    "provider", "model", "thinking_mode", "model_label",
    "code_fingerprint", "temporal_context_version",
    "experiment_conditions", "extraction_strategy_sha256",
    "temporal_routed_cases_sha256", "condition_manifest_sha256",
    "dataset_sha256_by_year", "dataset_set_sha256",
    "group_abba_order",
)


def _validate_four_layer_provenance(runs_root, receipt):
    """Cross-validate provenance across manifest / run_context / receipt / audit."""
    runs_root = Path(runs_root)
    manifest_path = runs_root / "run_manifest.json"
    context_path = runs_root / "run_context.json"
    if not manifest_path.exists():
        raise SystemExit(
            f"four-layer provenance reject: run_manifest.json missing: "
            f"{manifest_path}")
    if not context_path.exists():
        raise SystemExit(
            f"four-layer provenance reject: run_context.json missing: "
            f"{context_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    context = json.loads(context_path.read_text(encoding="utf-8"))
    archive_dir = receipt.get("archive_dir")
    if not archive_dir:
        raise SystemExit(
            "four-layer provenance reject: receipt archive_dir missing")
    audit_path = Path(archive_dir) / "audit_index.json"
    if not audit_path.exists():
        raise SystemExit(
            f"four-layer provenance reject: audit_index.json missing: "
            f"{audit_path}")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    layers = {"manifest": manifest, "run_context": context,
              "receipt": receipt, "audit": audit}
    for field in _FOUR_LAYER_PROVENANCE_FIELDS:
        ref = manifest.get(field)
        for name, layer in layers.items():
            if layer.get(field) != ref:
                raise SystemExit(
                    f"four-layer provenance reject: {field} mismatch "
                    f"(manifest={ref!r}, {name}={layer.get(field)!r})")
    return True


# -- Report --


def _generate_report(merged, gate_result, schedule, ledger, out_dir, run_id=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    total = max(len(merged), 1)
    parsed = sum(1 for r in merged if r.get("terminal_state") == "parsed")
    parser_rate = round(parsed / total, 4)
    off_rows = [r for r in merged
                if (r.get("attempt_key") or [None] * 10)[2] == "b1a_time_off"]
    on_rows = [r for r in merged
               if (r.get("attempt_key") or [None] * 10)[2] == "b1a_time_on"]
    off_correct = sum(1 for r in off_rows if r.get("correct"))
    on_correct = sum(1 for r in on_rows if r.get("correct"))
    off_total = len(off_rows)
    on_total = len(on_rows)
    off_rate = off_correct / off_total if off_total else 0.0
    on_rate = on_correct / on_total if on_total else 0.0
    by_year = defaultdict(
        lambda: {"off_correct": 0, "off_total": 0, "on_correct": 0, "on_total": 0})
    for r in off_rows + on_rows:
        year = _year_from_dataset_id((r.get("attempt_key") or [""])[0])
        if year is None:
            continue
        arm = (r.get("attempt_key") or [None] * 10)[2]
        bucket = by_year[year]
        if arm == "b1a_time_off":
            bucket["off_total"] += 1
            bucket["off_correct"] += 1 if r.get("correct") else 0
        elif arm == "b1a_time_on":
            bucket["on_total"] += 1
            bucket["on_correct"] += 1 if r.get("correct") else 0
    case_deltas = gate_result.get("case_deltas") or {}
    nonzero = sorted([(cid, d) for cid, d in case_deltas.items() if d != 0],
                     key=lambda x: x[0])
    by_case = {}
    for r in off_rows:
        cid = (r.get("attempt_key") or [None] * 10)[6] or r.get("case_id")
        by_case.setdefault(cid, {"off": 0, "on": 0})
        by_case[cid]["off"] += 1 if r.get("correct") else 0
    for r in on_rows:
        cid = (r.get("attempt_key") or [None] * 10)[6] or r.get("case_id")
        by_case.setdefault(cid, {"off": 0, "on": 0})
        by_case[cid]["on"] += 1 if r.get("correct") else 0
    yearly_breakdown = {}
    for year in sorted(by_year.keys()):
        s = by_year[year]
        yearly_breakdown[year] = {
            "off_correct": s["off_correct"], "off_total": s["off_total"],
            "on_correct": s["on_correct"], "on_total": s["on_total"],
            "off_rate": round(s["off_correct"] / s["off_total"], 6) if s["off_total"] else 0.0,
            "on_rate": round(s["on_correct"] / s["on_total"], 6) if s["on_total"] else 0.0,
        }
    report = {
        "model_protocol": MODEL_LABEL,
        "provider": FROZEN_PROVIDER,
        "model": FROZEN_MODEL,
        "thinking_mode": FROZEN_THINKING_MODE,
        "run_id": run_id,
        "verdict": gate_result.get("verdict"),
        "paired_delta": gate_result.get("paired_delta"),
        "min_case_delta": gate_result.get("min_case_delta"),
        "parser_rate": parser_rate,
        "accuracy": {
            "off": {"correct": off_correct, "total": off_total,
                    "rate": round(off_rate, 6)},
            "on": {"correct": on_correct, "total": on_total,
                   "rate": round(on_rate, 6)},
        },
        "yearly_breakdown": yearly_breakdown,
        "nonzero_case_deltas": nonzero,
        "gate": _json_safe(gate_result),
        "run": {
            "slices": len(schedule["slices"]),
            "scheduled": schedule["total_scheduled_calls"],
            "attempted": ledger.total_attempted,
            "global_hard_cap": ledger.hard_cap,
        },
    }
    (out / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 6D time-context ablation report",
        f"- Model protocol: {report['model_protocol']}",
        f"- Provider: {report['provider']}",
        f"- Model: {report['model']}",
        f"- Thinking mode: {report['thinking_mode']}",
        f"- Run ID: {run_id}",
        f"- gate: **{gate_result.get('verdict')}**",
        f"- paired_delta: {gate_result.get('paired_delta')}",
        f"- min_case_delta: {gate_result.get('min_case_delta')}",
        f"- parser rate: {parser_rate}",
        f"- budget: scheduled {report['run']['scheduled']} "
        f"/ attempted {report['run']['attempted']} "
        f"/ cap {report['run']['global_hard_cap']}",
        "",
        "## Accuracy",
        "",
        "| Condition | Correct | Total | Rate |",
        "|---|---|---|---|",
        f"| OFF | {off_correct} | {off_total} | {off_rate * 100:.2f}% |",
        f"| ON  | {on_correct} | {on_total} | {on_rate * 100:.2f}% |",
        "",
        "## Yearly Breakdown",
        "",
        "| Year | OFF | ON | Delta |",
        "|---|---|---|---|",
    ]
    for year in sorted(by_year.keys()):
        s = by_year[year]
        y_off_rate = s["off_correct"] / s["off_total"] if s["off_total"] else 0.0
        y_on_rate = s["on_correct"] / s["on_total"] if s["on_total"] else 0.0
        delta_pp = (y_on_rate - y_off_rate) * 100
        lines.append(
            f"| {year} | {s['off_correct']}/{s['off_total']} | "
            f"{s['on_correct']}/{s['on_total']} | {delta_pp:+.2f}pp |")
    lines += [
        "",
        "## Non-zero Case Deltas",
        "",
        "| Case ID | OFF | ON | Delta |",
        "|---|---|---|---|",
    ]
    for cid, d in nonzero:
        c = by_case.get(cid, {"off": 0, "on": 0})
        lines.append(
            f"| {cid} | {c['off']}/{REPEATS} | {c['on']}/{REPEATS} | {d:+d} |")
    lines += [
        "",
        "off/on paired ablation; 31 temporal-routed cases x 3 repeats; "
        "group-pair AB/BA scheduling.",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


# -- Archive --


def _create_archive(schedule, ledger, run_dir, provider, model, gate_result,
                    run_manifest, code_fingerprint, run_id=None,
                    archive_root=None):
    import shutil
    archive_root = Path(archive_root or ARCHIVE_ROOT)
    run_dir = Path(run_dir)
    if gate_result.get("verdict") == "BLOCKED":
        raise SystemExit("archive reject: BLOCKED verdict cannot be archived")
    completed = {sl["slice_id"] for sl in schedule["slices"]
                 if ledger.slice_completed(sl["slice_id"])}
    expected_ids = {sl["slice_id"] for sl in schedule["slices"]}
    if completed != expected_ids:
        raise SystemExit(
            f"archive reject: schedule incomplete ({len(completed)}/{len(expected_ids)})")
    if ledger.total_attempted > ledger.hard_cap:
        raise SystemExit("archive reject: ledger exceeds hard_cap")
    merged = _merge_details(schedule["slices"])
    completeness = _check_completeness(merged, schedule)
    if completeness != "PASS":
        raise SystemExit(f"archive reject: completeness failed ({completeness})")
    auto_id = f"6d-dev-{FROZEN_DATE}-{provider}-{model}-{code_fingerprint[:12]}"
    archive_run_id = f"{run_id}-{auto_id}" if run_id else auto_id
    target = archive_root / archive_run_id
    if target.exists():
        raise SystemExit(f"archive reject: run_id exists ({target})")
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
            f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in merged)
        md_sha = _sha256_file(str(merged_details_path))
        audit = {
            "run_id": archive_run_id,
            "user_run_id": run_id,
            "experiment_id": EXPERIMENT_ID,
            "stage": "dev",
            "frozen_date": FROZEN_DATE,
            "provider": provider,
            "model": model,
            "thinking_mode": FROZEN_THINKING_MODE,
            "model_label": MODEL_LABEL,
            "code_fingerprint": code_fingerprint,
            "gate_verdict": gate_result.get("verdict"),
            "gate_detail": _json_safe(gate_result),
            "merged_details_sha256": md_sha,
            "budget": {
                "attempted": ledger.total_attempted,
                "hard_cap": ledger.hard_cap,
                "slices": len(schedule["slices"]),
            },
            "completeness_result": completeness,
            "archived_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        audit.update(run_manifest)
        audit_path = tmp_dir / "audit_index.json"
        audit_path.write_text(
            json.dumps(_json_safe(audit), ensure_ascii=False, indent=2),
            encoding="utf-8")
        if _sha256_file(str(merged_details_path)) != md_sha:
            raise SystemExit("archive self-verify reject: merged_details SHA unstable")
        receipt = {
            "verdict": gate_result.get("verdict"),
            "stage": "dev",
            "run_id": archive_run_id,
            "user_run_id": run_id,
            "archive_dir": str(target),
            "audit_index_sha256": _sha256_file(str(audit_path)),
            "provider": provider,
            "model": model,
            "thinking_mode": FROZEN_THINKING_MODE,
            "model_label": MODEL_LABEL,
            "code_fingerprint": code_fingerprint,
        }
        receipt.update(run_manifest)
        receipt_path = tmp_dir / "dev_gate.json"
        receipt_path.write_text(
            json.dumps(_json_safe(receipt), ensure_ascii=False, indent=2),
            encoding="utf-8")
        os.replace(str(tmp_dir), str(target))
        return {"archive_dir": str(target), "run_id": archive_run_id,
                "audit": audit, "receipt": receipt}
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _publish_receipt_atomic(arch_result, gate_root, receipt_name,
                             validated_bytes=None, expected_sha256=None):
    """Publish receipt by writing pre-validated bytes (not re-reading source).

    This eliminates TOCTOU: the exact bytes validated in run_dev are the
    bytes written to tmp and verified by SHA before atomic replace.
    """
    gate_root = Path(gate_root)
    gate_root.mkdir(parents=True, exist_ok=True)
    receipt_dst = gate_root / receipt_name
    tmp_dst = receipt_dst.with_suffix(".tmp")
    if validated_bytes is None:
        raise SystemExit(
            "publish receipt reject: validated_bytes required")
    tmp_dst.write_bytes(validated_bytes)
    actual_sha = _sha256_file(str(tmp_dst))
    if expected_sha256 is None or actual_sha != expected_sha256:
        tmp_dst.unlink(missing_ok=True)
        raise SystemExit(
            f"publish receipt reject: SHA mismatch "
            f"(expected={expected_sha256!r}, actual={actual_sha!r})")
    os.replace(str(tmp_dst), str(receipt_dst))


# -- Phase1 receipt validation --


def _validate_phase1_receipt(receipt_path, manifest_path):
    if not os.path.exists(receipt_path):
        raise SystemExit(f"phase1 receipt missing: {receipt_path}")
    receipt = json.loads(open(receipt_path, encoding="utf-8").read())
    if receipt.get("status") != "PASS":
        raise SystemExit(
            f"phase1 receipt status not PASS: {receipt.get('status')!r}")
    n_routed = receipt.get("n_routed", 0)
    if n_routed < PHASE1_N_ROUTED_MIN:
        raise SystemExit(
            f"phase1 receipt n_routed={n_routed} < {PHASE1_N_ROUTED_MIN}")
    manifest_sha = _canonical_json_sha256(manifest_path)
    if receipt.get("temporal_routed_cases_sha256") != manifest_sha:
        raise SystemExit(
            f"phase1 receipt temporal_routed_cases_sha256 mismatch: "
            f"receipt={receipt.get('temporal_routed_cases_sha256')!r} "
            f"manifest={manifest_sha!r}")
    entries = _load_routed_entries(manifest_path)
    if len(entries) != n_routed:
        raise SystemExit(
            f"phase1 receipt n_routed ({n_routed}) != manifest entries ({len(entries)})")
    ds_by_year = {}
    for e in entries:
        ds_by_year.setdefault(e["year"], e["dataset_sha256"])
    receipt_ds = receipt.get("dataset_sha256_by_year", {})
    for year, sha in ds_by_year.items():
        if receipt_ds.get(year) != sha:
            raise SystemExit(
                f"phase1 receipt dataset_sha256_by_year mismatch: "
                f"year={year} receipt={receipt_ds.get(year)!r} "
                f"manifest={sha!r}")
    # Re-compute dataset SHA from current files and compare with receipt
    datasets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "benchmark", "datasets")
    for year, expected_sha in receipt.get("dataset_sha256_by_year", {}).items():
        ds_path = os.path.join(datasets_dir, f"baziqa_contest8_{year}_holdout_enriched.jsonl")
        if not os.path.exists(ds_path):
            raise SystemExit(f"phase1 receipt validation: dataset missing: {ds_path}")
        actual_sha = hashlib.sha256(open(ds_path, "rb").read()).hexdigest()
        if actual_sha != expected_sha:
            raise SystemExit(
                f"phase1 receipt dataset_sha256 mismatch: year={year} "
                f"receipt={expected_sha!r} current={actual_sha!r}")
    # Verify dataset_set_sha256 = canonical(dataset_sha256_by_year)
    expected_set_sha = _canonical_dict_sha256(receipt.get("dataset_sha256_by_year", {}))
    if receipt.get("dataset_set_sha256") != expected_set_sha:
        raise SystemExit(
            f"phase1 receipt dataset_set_sha256 != canonical(dataset_sha256_by_year): "
            f"receipt={receipt.get('dataset_set_sha256')!r} "
            f"expected={expected_set_sha!r}")
    return receipt


# -- Run context + resume isolation --

RUN_CONTEXT_REQUIRED_FIELDS = (
    "provider", "model", "thinking_mode", "model_label", "code_fingerprint",
    "temporal_context_version", "experiment_conditions",
    "extraction_strategy_sha256", "temporal_routed_cases_sha256",
    "condition_manifest_sha256", "dataset_sha256_by_year",
    "dataset_set_sha256", "group_abba_order", "experiment_id", "created_at",
)


def _prepare_run_context(output_dir, run_id, resume, run_manifest, code_fingerprint):
    output_dir = Path(output_dir)
    runs_root = output_dir / "runs" / run_id
    context_path = runs_root / "run_context.json"
    if not resume:
        runs_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.mkdir(str(runs_root))
        except FileExistsError:
            raise SystemExit(
                f"run context reject: run dir exists ({runs_root}); "
                f"interrupted recovery must use --resume") from None
        context = dict(run_manifest)
        context["experiment_id"] = EXPERIMENT_ID
        context["code_fingerprint"] = code_fingerprint
        context["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _atomic_write_json(context_path, context)
        return runs_root, context
    if not context_path.exists():
        raise SystemExit("run_context.json missing: refusing legacy run migration")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    if context.get("experiment_id") != EXPERIMENT_ID:
        raise SystemExit(
            f"run context reject: experiment_id={context.get('experiment_id')!r} "
            f"!= {EXPERIMENT_ID!r} (6D-v2 cannot resume other experiment run)")
    missing = [f for f in RUN_CONTEXT_REQUIRED_FIELDS if f not in context]
    if missing:
        raise SystemExit(f"run context reject: missing fields {missing}")
    for field in ("temporal_context_version", "temporal_routed_cases_sha256",
                  "extraction_strategy_sha256", "condition_manifest_sha256"):
        if context.get(field) != run_manifest.get(field):
            raise SystemExit(
                f"run context reject: {field} drift "
                f"(context={context.get(field)!r}, "
                f"current={run_manifest.get(field)!r})")
    for field in ("dataset_sha256_by_year", "dataset_set_sha256",
                  "experiment_conditions"):
        if context.get(field) != run_manifest.get(field):
            raise SystemExit(
                f"run context reject: {field} drift "
                f"(context={context.get(field)!r}, "
                f"current={run_manifest.get(field)!r})")
    if context.get("group_abba_order") != run_manifest.get("group_abba_order"):
        raise SystemExit(
            "run context reject: group_abba_order drift "
            f"(context={context.get('group_abba_order')!r}, "
            f"current={run_manifest.get('group_abba_order')!r})")
    for field in ("provider", "model", "thinking_mode", "model_label"):
        if context.get(field) != run_manifest.get(field):
            raise SystemExit(
                f"run context reject: {field} drift "
                f"(context={context.get(field)!r}, "
                f"current={run_manifest.get(field)!r})")
    if context.get("code_fingerprint") != code_fingerprint:
        raise SystemExit("run context reject: code fingerprint drift")
    return runs_root, context


def _record_run_failure(runs_root, stage, reason):
    path = Path(runs_root) / "run_failures.jsonl"
    record = {"stage": stage, "reason": reason,
              "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# -- run_dev entry point --

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")


def _validate_run_id(run_id):
    if not run_id or not isinstance(run_id, str):
        raise SystemExit("run_id reject: must be non-empty string")
    if run_id in (".", ".."):
        raise SystemExit(f"run_id reject: cannot be '.' or '..' (got {run_id!r})")
    if os.path.isabs(run_id):
        raise SystemExit(f"run_id reject: cannot be absolute path (got {run_id!r})")
    if "/" in run_id or "\\" in run_id:
        raise SystemExit(f"run_id reject: cannot contain path separators (got {run_id!r})")
    if not _RUN_ID_RE.match(run_id):
        raise SystemExit(
            f"run_id reject: only alnum/_/- allowed, starting with alnum/_, len 1-64 "
            f"(got {run_id!r})")


def run_dev(provider, model, output_dir, run_id=None, resume=False,
            routed_manifest_path=ROUTED_MANIFEST_PATH,
            phase1_receipt_path=PHASE1_RECEIPT_PATH):
    protocol = _validate_frozen_protocol(
        provider, model, FROZEN_THINKING_MODE, FROZEN_TEMPERATURE,
        FROZEN_PROFILE, FROZEN_METHOD)
    _validate_run_id(run_id)
    _validate_phase1_receipt(phase1_receipt_path, routed_manifest_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    code_fp = _compute_experiment_code_fingerprint()
    run_manifest = build_run_manifest(
        provider, model, protocol, code_fp, routed_manifest_path)
    runs_root, _context = _prepare_run_context(
        output_dir=output_dir, run_id=run_id, resume=resume,
        run_manifest=run_manifest, code_fingerprint=code_fp)
    lock = OutputDirLock.acquire(str(runs_root))
    try:
        if lock is None:
            raise SystemExit(f"dev run dir locked: {runs_root}")
        manifest_path = runs_root / "run_manifest.json"
        if resume:
            if not manifest_path.exists():
                raise SystemExit(
                    "run_manifest.json missing: refusing resume without manifest")
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            for field in _FOUR_LAYER_PROVENANCE_FIELDS:
                if existing.get(field) != run_manifest.get(field):
                    raise SystemExit(
                        f"run_manifest.json drift: field={field} "
                        f"existing={existing.get(field)!r} "
                        f"current={run_manifest.get(field)!r}")
        else:
            import tempfile
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(runs_root), suffix=".tmp", prefix="manifest_")
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(run_manifest, f, ensure_ascii=False, indent=2,
                              sort_keys=True)
                os.replace(tmp_path, str(manifest_path))
            except:
                os.unlink(tmp_path)
                raise
        stage_dir = runs_root / "dev"
        stage_dir.mkdir(parents=True, exist_ok=True)
        schedule = _build_schedule(str(stage_dir), routed_manifest_path)
        if schedule["group_abba_order"] != run_manifest["group_abba_order"]:
            raise SystemExit("run reject: schedule group_abba_order != run_manifest")
        ledger = BudgetLedger(
            str(stage_dir / "budget_ledger.json"),
            global_hard_cap=schedule["global_hard_cap"])
        _run_all_slices(schedule, ledger, provider, model)
        merged = _merge_details(schedule["slices"])
        completeness = _check_completeness(merged, schedule)
        if completeness != "PASS":
            raise SystemExit(f"dev completeness failed: {completeness}")
        n_cases = sum(schedule["n_cases_per_year"].values())
        gate_result = compute_6d_gate(merged, n_cases)
        _generate_report(merged, gate_result, schedule, ledger,
                         str(stage_dir), run_id=run_id)
        arch = _create_archive(
            schedule, ledger, str(stage_dir), provider, model, gate_result,
            run_manifest, code_fp, run_id=run_id)
        # Validate the PERSISTED receipt from disk (not in-memory)
        # to prevent corruption between archive creation and publication.
        # Read raw bytes once; these exact bytes are validated and published.
        archive_receipt_path = Path(arch["archive_dir"]) / "dev_gate.json"
        if not archive_receipt_path.exists():
            raise SystemExit(
                f"archive receipt missing on disk: {archive_receipt_path}")
        receipt_bytes = archive_receipt_path.read_bytes()
        validated_sha = hashlib.sha256(receipt_bytes).hexdigest()
        disk_receipt = json.loads(receipt_bytes.decode("utf-8"))
        if disk_receipt != _json_safe(arch["receipt"]):
            raise SystemExit(
                "archive receipt drift: disk receipt != in-memory receipt")
        check_6d_gate(disk_receipt)
        _validate_four_layer_provenance(runs_root, disk_receipt)
        _publish_receipt_atomic(
            arch, runs_root / "gates", "dev_gate.json",
            validated_bytes=receipt_bytes,
            expected_sha256=validated_sha)
        return {"status": "ok", "gate": gate_result, "archive": arch,
                "run_id": run_id}
    except (Exception, SystemExit) as exc:
        _record_run_failure(runs_root, "dev", str(exc))
        raise
    finally:
        if lock:
            lock.release()


# -- CLI --


def main():
    parser = argparse.ArgumentParser(description="Phase 6 6D orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run_dev")
    p.add_argument("--provider", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--run-id", required=True,
                   help="experiment run identifier")
    p.add_argument("--resume", action="store_true",
                   help="explicitly resume an existing run")
    p.add_argument("--routed-manifest", default=ROUTED_MANIFEST_PATH,
                   help="frozen routed manifest JSON path")
    p.add_argument("--phase1-receipt", default=PHASE1_RECEIPT_PATH,
                   help="phase1 receipt JSON path")
    args = parser.parse_args()
    if args.cmd == "run_dev":
        result = run_dev(
            args.provider, args.model, args.output_dir,
            run_id=args.run_id, resume=args.resume,
            routed_manifest_path=args.routed_manifest,
            phase1_receipt_path=args.phase1_receipt)
        print(json.dumps(_json_safe(result), ensure_ascii=False, indent=2,
                         default=str))


if __name__ == "__main__":
    main()
