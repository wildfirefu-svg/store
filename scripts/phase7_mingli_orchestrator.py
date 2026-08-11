#!/usr/bin/env python3
"""Phase 7 MingLi-Bench 160-question frozen baseline orchestrator.

Implements plan Task 6 of docs/superpowers/plans/2026-08-10-phase7-mingli-bench-baseline.md
(design v2.3 §3.2/§3.4/§3.5/§3.6/§8). Single-slice scheduling (one 160-question JSONL,
one case_ids_file, one manifest scheduled=160/hard_cap=180 from the start):
normalize -> smoke(max_cases=10) -> quantitative verdict -> resume(max_cases=160)
-> controlled retest with global budget pre-allocation -> hard gates (§8.1 twelve
clauses) -> atomic archive + audit index -> receipt atomic publish (§8.5).

Style references scripts/phase6_6d_v2_orchestrator.py (BudgetLedger, manifest
homology pair, run context), but Phase 7 has NO slice fan-out.

Exit codes (frozen): 0 = PASS/success; 2 = usage/manifest/state-machine/run_id
contract rejection; 4 = BLOCKED (aligned with fetch BLOCKED_EXIT).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import types
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# -- Frozen constants (single source of truth, design v2.3) --

FROZEN_DATE = "2026-08-10"
FROZEN_PROVIDER = "deepseek"
FROZEN_MODEL = "deepseek-v4-flash"
FROZEN_THINKING_MODE = "disabled"
FROZEN_TEMPERATURE = 0.0
FROZEN_PROFILE = "mingli_official_cot_astro"
FROZEN_METHOD = "direct_choice"
FROZEN_ARM = "phase7_mingli_baseline"          # metadata only; no reasoned-arm mapping
MODEL_LABEL = "DeepSeek-V4-Flash non-thinking"
CHART_SCHEMA = "approved_v1"
EXPERIMENT_ID = "phase7-mingli-baseline"

SCHEDULED_CALLS = 160
HARD_CAP = 180
SMOKE_SIZE = 10
MAIN_MAX_CASES = 160

DATA_JSON_PATH = "data/mingli/data.json"
FORTUNE_JSON_PATH = "data/mingli/fortune_api_results.json"
NORMALIZED_DATASET_NAME = "mingli_160"
MAIN_CASE_IDS_NAME = "case_ids_main.json"
RETEST_CASE_IDS_NAME = "case_ids_retest.json"
RETEST_MANIFEST_NAME = "retest_manifest.json"
RECEIPT_FILENAME = "phase7_baseline_receipt.json"
RUN_MANIFEST_NAME = "run_manifest.json"
RUN_CONTEXT_NAME = "run_context.json"
BUDGET_LEDGER_NAME = "budget_ledger.json"
ARCHIVE_DIR_NAME = "archive"
MERGED_DETAILS_NAME = "merged_details.jsonl"
AUDIT_INDEX_NAME = "audit_index.json"

EXIT_OK = 0
EXIT_CONTRACT = 2      # usage/manifest/state-machine/run_id contract rejection
EXIT_BLOCKED = 4       # BLOCKED (aligned with scripts/fetch_mingli_bench.py)

# §3.4: child-process env must explicitly drop these (parent residue must not leak)
ENV_PURGE_VARS = ("BAZI_RAG", "BAZI_RAG_CORPUS", "BAZI_FEWSHOT_FILE", "BAZI_APB_BLOCK")

# run context stages (single-slice state machine)
STAGE_SMOKE = "smoke_first_pass"
STAGE_MAIN_RESUME = "main_resume"
STAGE_RETEST = "controlled_retest"
STAGE_FINALIZE = "finalize"
STAGE_PUBLISHED = "published"

# §3.2: the only legal max_cases transition is {10 -> 160}
MAX_CASES_LEGAL_TRANSITIONS = frozenset({(SMOKE_SIZE, MAIN_MAX_CASES)})

RETEST_ATTEMPT_STAGE = "controlled_retest"
RETEST_ELIGIBLE_STATES = ("invalid", "call_failed")
# identity fields frozen at first retest entry; resume reuses verbatim (v3 P0-3)
RETEST_FROZEN_FIELDS = ("selected_case_ids", "case_ids_sha256", "scheduled_calls",
                        "hard_cap", "attempt_stage")

TERMINAL_STATES = ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed")

# §8.1: this arm never produces unresolved/judge_unresolved (gate_blocked is fatal)
ARM_TERMINAL_STATES = ("parsed", "invalid", "call_failed")
EXPECTED_CHART_COUNT = 32
# §8.1 clause 4 frozen distribution: 30 charts x 5 + case_19 x 6 + case_20 x 4
CHART_QUOTA_OVERRIDES = {"case_19": 6, "case_20": 4}

# §8.4 nine-file phase7 code fingerprint scope (orchestrator-side field,
# parallel to the runner-side _CODE_SCOPE fingerprint; scope must not shrink)
PHASE7_CODE_SCOPE = (
    "scripts/phase7_mingli_orchestrator.py",
    "scripts/fetch_mingli_bench.py",
    "benchmark/runners/mingli_bench_adapter.py",
    "benchmark/runners/run_benchmark.py",
    "benchmark/runners/resume_ledger.py",
    "benchmark/runners/profiles.py",
    "benchmark/formatters/mingli_prompt.py",
    "claude_api.py",
    "config.py",
)

# fetch provenance manifest candidates (Task 7 writes the docs/phase7 one)
FETCH_MANIFEST_CANDIDATES = (
    "docs/phase7/mingli_fetch_manifest.json",
    ".tmp/phase6/mingli_fetch_manifest.json",
)

# §8.2 receipt required field set (+ phase7_code_fingerprint four-layer field)
RECEIPT_REQUIRED_FIELDS = (
    "stage", "run_id", "user_run_id", "archive_dir", "audit_index_sha256",
    "provider", "model", "thinking_mode", "temperature", "model_label",
    "profile", "method", "arm", "attempt_stage",
    "code_fingerprint", "prompt_fingerprint", "phase7_code_fingerprint",
    "mingli_data_sha256", "fortune_api_sha256", "normalized_jsonl_sha256",
    "pinned_commit", "license_sha256",
    "rag", "fewshot", "apb", "shuffle_options",
    "scheduled_calls", "hard_cap", "attempted",
    "first_pass_accuracy", "parser_rate", "terminal_state_counts",
    "completeness_verdict", "smoke_size",
    "question_id_count", "chart_case_count",
    "response_model_values", "response_model_missing_count",
)

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")


# -- Helpers --


def _contract_reject(message):
    print(f"[contract reject] {message}", file=sys.stderr)
    raise SystemExit(EXIT_CONTRACT)


def _blocked(message):
    print(f"[BLOCKED] {message}", file=sys.stderr)
    raise SystemExit(EXIT_BLOCKED)


def _sha256_file(path):
    h = hashlib.sha256()
    if not os.path.exists(path):
        return "0" * 64
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_sha256_text(payload):
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(str(tmp), str(path))


def _load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _count_call_attempts(events_path):
    return sum(1 for r in _load_jsonl(events_path) if r.get("kind") == "call_attempt")


# -- run_id validation (aligned with 6D _validate_run_id) --


def _validate_run_id(run_id):
    if not run_id or not isinstance(run_id, str):
        _contract_reject("run_id reject: must be non-empty string")
    if run_id in (".", ".."):
        _contract_reject(f"run_id reject: cannot be '.' or '..' (got {run_id!r})")
    if os.path.isabs(run_id):
        _contract_reject(f"run_id reject: cannot be absolute path (got {run_id!r})")
    if "/" in run_id or "\\" in run_id:
        _contract_reject(f"run_id reject: cannot contain path separators (got {run_id!r})")
    if not _RUN_ID_RE.match(run_id):
        _contract_reject(
            "run_id reject: only alnum/_/- allowed, starting with alnum/_, len 1-64 "
            f"(got {run_id!r})")


# -- env sanitizer (design §3.4, fail-closed) --


def _build_child_env():
    """Child env = parent env minus the four intervention variables.

    Explicit deletion (not reliance on a clean parent): any residue of
    BAZI_RAG/BAZI_RAG_CORPUS/BAZI_FEWSHOT_FILE/BAZI_APB_BLOCK would contaminate
    the pure baseline.
    """
    env = dict(os.environ)
    for var in ENV_PURGE_VARS:
        env.pop(var, None)
    return env


def _env_flags():
    """Recorded into manifest/run context/receipt: all interventions off."""
    return {"rag": False, "fewshot": False, "apb": False, "shuffle_options": False}


# -- Runner command / manifest homology pair (single slice; NO --ziwei-arm) --


def _main_slice_info(runs_root, max_cases):
    runs_root = Path(runs_root)
    return {
        "dataset_path": str(runs_root / f"{NORMALIZED_DATASET_NAME}.jsonl"),
        "case_ids_file": str(runs_root / MAIN_CASE_IDS_NAME),
        "detail_path": str(runs_root / "main" / "detail.jsonl"),
        "output_dir": str(runs_root / "main"),
        "attempt_stage": "main",
        "scheduled_calls": SCHEDULED_CALLS,
        "hard_cap": HARD_CAP,
        "max_cases": max_cases,
    }


def _build_runner_command(slice_info, resume=False):
    """Frozen argv (design §3.2). `--ziwei-arm` is deliberately ABSENT:
    profiles._visibility_base() would route any non-None ziwei_arm into the
    reasoned-arm matrix and void the official astro required markers."""
    cmd = [
        sys.executable, "-m", "benchmark.runners.run_benchmark",
        "--dataset", slice_info["dataset_path"],
        "--profile", FROZEN_PROFILE,
        "--method", FROZEN_METHOD,
        "--thinking-mode", FROZEN_THINKING_MODE,
        "--temperature", str(FROZEN_TEMPERATURE),
        "--arm", FROZEN_ARM,
        "--attempt-stage", slice_info["attempt_stage"],
        "--scheduled-calls", str(slice_info["scheduled_calls"]),
        "--hard-cap", str(slice_info["hard_cap"]),
        "--case-ids-file", slice_info["case_ids_file"],
        "--case-details-jsonl", slice_info["detail_path"],
        "--output-dir", slice_info["output_dir"],
        "--max-cases", str(slice_info["max_cases"]),
        "--as-of-date", FROZEN_DATE,
        "--chart-schema-version", CHART_SCHEMA,
        "--provider", FROZEN_PROVIDER,
        "--model", FROZEN_MODEL,
        "--model-runner",
        "--repeat-idx", "0",
    ]
    if resume:
        cmd.append("--resume")
    return cmd


def _slice_runner_args(slice_info):
    """Reconstruct the runner argparse namespace from the same slice_info fields
    (single source with _build_runner_command) so the resume manifest built from
    either side is byte-identical (ManifestHomology contract)."""
    return types.SimpleNamespace(
        dataset=slice_info["dataset_path"],
        case_ids_file=slice_info["case_ids_file"],
        profile=FROZEN_PROFILE,
        chart_schema_version=CHART_SCHEMA,
        arm=FROZEN_ARM,
        ziwei_arm=None,
        attempt_stage=slice_info["attempt_stage"],
        repeat_idx=0,
        provider=FROZEN_PROVIDER,
        model=FROZEN_MODEL,
        temperature=FROZEN_TEMPERATURE,
        sample_temperature=0.4,
        n_samples=1,
        aggregate="majority",
        method=FROZEN_METHOD,
        scheduled_calls=slice_info["scheduled_calls"],
        hard_cap=slice_info["hard_cap"],
        as_of_date=FROZEN_DATE,
        thinking_mode=FROZEN_THINKING_MODE,
        time_context_injection="off",
        temporal_routed_cases_file=None,
    )


# -- BudgetLedger (6D semantics, single global ledger hard_cap=180) --


class BudgetLedger:
    def __init__(self, ledger_path, global_hard_cap=HARD_CAP):
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
                _contract_reject(
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
            return  # idempotent: resume never re-claims budget
        if self.total_attempted + actual_attempts > self.hard_cap:
            _blocked(
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


# -- Run context / run manifest (run_id + cross-process resume contract) --

RUN_CONTEXT_REQUIRED_FIELDS = (
    "experiment_id", "run_id", "stage", "smoke_size", "max_cases",
    "provider", "model", "thinking_mode", "temperature", "model_label",
    "profile", "method", "arm", "scheduled_calls", "hard_cap", "as_of_date",
    "env_flags", "created_at",
)

# identity fields compared drift fail-closed on resume
RUN_MANIFEST_IDENTITY_FIELDS = (
    "experiment_id", "provider", "model", "thinking_mode", "temperature",
    "model_label", "profile", "method", "arm", "scheduled_calls", "hard_cap",
    "as_of_date", "chart_schema_version", "data_json_sha256",
    "fortune_json_sha256", "env_flags", "phase7_code_fingerprint",
)


def _phase7_code_fingerprint():
    """§8.4 nine-file scope SHA-256: rel path + bytes concatenated in order;
    any file change -> fingerprint drift -> four-layer validation rejects."""
    h = hashlib.sha256()
    for rel in PHASE7_CODE_SCOPE:
        h.update(rel.encode())
        p = os.path.join(_PROJECT_ROOT, rel)
        h.update(open(p, "rb").read() if os.path.exists(p) else b"<missing>")
    return h.hexdigest()


def _build_run_manifest():
    return {
        "experiment_id": EXPERIMENT_ID,
        "provider": FROZEN_PROVIDER,
        "model": FROZEN_MODEL,
        "thinking_mode": FROZEN_THINKING_MODE,
        "temperature": FROZEN_TEMPERATURE,
        "model_label": MODEL_LABEL,
        "profile": FROZEN_PROFILE,
        "method": FROZEN_METHOD,
        "arm": FROZEN_ARM,
        "scheduled_calls": SCHEDULED_CALLS,
        "hard_cap": HARD_CAP,
        "as_of_date": FROZEN_DATE,
        "chart_schema_version": CHART_SCHEMA,
        "data_json_sha256": _sha256_file(os.path.join(_PROJECT_ROOT, DATA_JSON_PATH)),
        "fortune_json_sha256": _sha256_file(os.path.join(_PROJECT_ROOT, FORTUNE_JSON_PATH)),
        "env_flags": _env_flags(),
        "phase7_code_fingerprint": _phase7_code_fingerprint(),
    }


def _initial_run_context(run_id, run_manifest):
    context = {k: run_manifest[k] for k in RUN_MANIFEST_IDENTITY_FIELDS
               if k in run_manifest}
    context.update({
        "run_id": run_id,
        "stage": STAGE_SMOKE,
        "smoke_size": SMOKE_SIZE,
        "max_cases": SMOKE_SIZE,
        "max_cases_transitions": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    return context


def _prepare_run_context(output_dir, run_id, resume):
    """run_id/resume five-case contract (plan v3 P0-2). Returns (runs_root, context)."""
    output_dir = Path(output_dir)
    runs_root = output_dir / "runs" / run_id
    context_path = runs_root / RUN_CONTEXT_NAME
    manifest_path = runs_root / RUN_MANIFEST_NAME
    receipt_path = runs_root / RECEIPT_FILENAME

    if receipt_path.exists():
        _contract_reject(
            f"run_id reject: receipt already published for run_id={run_id!r}; "
            "re-running a published experiment is forbidden (double billing)")
    if not resume:
        if runs_root.exists():
            _contract_reject(
                f"run context reject: run dir exists ({runs_root}); "
                "interrupted recovery must use --resume")
        runs_root.mkdir(parents=True)
        run_manifest = _build_run_manifest()
        _atomic_write_json(manifest_path, run_manifest)
        context = _initial_run_context(run_id, run_manifest)
        _atomic_write_json(context_path, context)
        return runs_root, context

    if not context_path.exists():
        _contract_reject("run context reject: run_context.json missing; "
                         "cannot resume unknown run")
    if not manifest_path.exists():
        _contract_reject("run context reject: run_manifest.json missing; "
                         "refusing resume without manifest")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    stored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if context.get("experiment_id") != EXPERIMENT_ID:
        _contract_reject(
            f"run context reject: experiment_id={context.get('experiment_id')!r} "
            f"!= {EXPERIMENT_ID!r} (cannot resume other experiment run)")
    missing = [f for f in RUN_CONTEXT_REQUIRED_FIELDS if f not in context]
    if missing:
        _contract_reject(f"run context reject: missing fields {missing}")
    current_manifest = _build_run_manifest()
    for field in RUN_MANIFEST_IDENTITY_FIELDS:
        if stored_manifest.get(field) != current_manifest.get(field):
            _contract_reject(
                f"run manifest drift: field={field} "
                f"stored={stored_manifest.get(field)!r} "
                f"current={current_manifest.get(field)!r}")
    return runs_root, context


def _save_context(runs_root, context):
    _atomic_write_json(Path(runs_root) / RUN_CONTEXT_NAME, context)


# -- max_cases state machine (design §3.2 single-slice: only {10 -> 160}) --


def _advance_max_cases(context, new_max_cases):
    """Legal transition set is exactly {(10, 160)}. Anything else (10->20,
    160->10, jumping to 160 without a smoke record) is a contract rejection."""
    current = context.get("max_cases")
    if context.get("smoke_size") != SMOKE_SIZE or current is None:
        _contract_reject("max_cases state reject: no smoke record in run context")
    if current == new_max_cases:
        return context
    if (current, new_max_cases) not in MAX_CASES_LEGAL_TRANSITIONS:
        _contract_reject(
            f"max_cases state reject: illegal transition {current} -> {new_max_cases} "
            f"(legal: {sorted(MAX_CASES_LEGAL_TRANSITIONS)})")
    context.setdefault("max_cases_transitions", []).append(
        {"from": current, "to": new_max_cases,
         "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    context["max_cases"] = new_max_cases
    return context


# -- smoke quantitative verdict (design §5, frozen) --


def _judge_smoke(detail_path, events_path, smoke_size=SMOKE_SIZE):
    """All five criteria must hold; otherwise the run does not resume (exit 4).

    1. terminal detail rows == smoke_size (exactly 10)
    2. call_failed == 0
    3. gate_blocked == 0 (official astro visibility gate 10/10 PASS)
    4. parsed >= smoke_size - 1 (parser success >= 90%)
    5. per-attempt-key reconciliation: for every completed key,
       call_attempt events == 1 + model_call_failed events; and no orphan
       pre-call journal (call_attempt without terminal detail).
    """
    failures = []
    detail_rows = [r for r in _load_jsonl(detail_path)
                   if r.get("terminal_state") in TERMINAL_STATES]
    events = _load_jsonl(events_path)

    if len(detail_rows) != smoke_size:
        failures.append(f"terminal detail rows={len(detail_rows)} != {smoke_size}")
    n_call_failed = sum(1 for r in detail_rows if r.get("terminal_state") == "call_failed")
    if n_call_failed:
        failures.append(f"call_failed={n_call_failed} != 0")
    n_gate_blocked = sum(1 for r in detail_rows if r.get("gate_blocked"))
    if n_gate_blocked:
        failures.append(f"gate_blocked={n_gate_blocked} != 0")
    n_parsed = sum(1 for r in detail_rows if r.get("terminal_state") == "parsed")
    if n_parsed < smoke_size - 1:
        failures.append(f"parsed={n_parsed} < {smoke_size - 1} (parser rate < 90%)")

    detail_keys = {tuple(r["attempt_key"]) for r in detail_rows if r.get("attempt_key")}
    call_attempts = {}
    call_failures = {}
    for row in events:
        key = row.get("attempt_key")
        if not key:
            continue
        key = tuple(key)
        if row.get("kind") == "call_attempt":
            call_attempts[key] = call_attempts.get(key, 0) + 1
        elif row.get("kind") == "model_call_failed":
            call_failures[key] = call_failures.get(key, 0) + 1
    for key in sorted(call_attempts):
        if key not in detail_keys:
            failures.append(
                f"orphan pre-call journal: attempt key {key[6]} has "
                f"{call_attempts[key]} call_attempt event(s) but no terminal detail")
        elif call_attempts[key] != 1 + call_failures.get(key, 0):
            failures.append(
                f"attempt key {key[6]} reconciliation mismatch: "
                f"call_attempt={call_attempts[key]} != "
                f"1 + model_call_failed={call_failures.get(key, 0)}")

    return {
        "passed": not failures,
        "failures": failures,
        "terminal_count": len(detail_rows),
        "call_failed": n_call_failed,
        "gate_blocked": n_gate_blocked,
        "parsed": n_parsed,
        "smoke_size": smoke_size,
    }


# -- controlled retest: global budget pre-allocation (design §3.6/§7) --


def _retest_paths(runs_root):
    runs_root = Path(runs_root)
    return {
        "dir": runs_root / "retest",
        "detail": runs_root / "retest" / "detail.jsonl",
        "events": runs_root / "retest" / "detail.events.jsonl",
        "manifest": runs_root / "retest" / RETEST_MANIFEST_NAME,
        "case_ids_file": runs_root / "retest" / RETEST_CASE_IDS_NAME,
    }


def _compute_retest_allocation(main_events_path):
    """allocation = 180 - call_attempt(main events total)."""
    return HARD_CAP - _count_call_attempts(main_events_path)


def _eligible_retest_case_ids(main_detail_path):
    """main terminal invalid/call_failed, sorted by mingli_ftb_ id ascending."""
    ids = [r["case_id"] for r in _load_jsonl(main_detail_path)
           if r.get("terminal_state") in RETEST_ELIGIBLE_STATES and r.get("case_id")]
    return sorted(ids)


def _plan_retest(main_detail_path, main_events_path):
    """First retest entry: compute and freeze the identity fields."""
    allocation = _compute_retest_allocation(main_events_path)
    eligible = _eligible_retest_case_ids(main_detail_path)
    scheduled_calls = min(len(eligible), allocation)
    selected = eligible[:scheduled_calls]
    return {
        "attempt_stage": RETEST_ATTEMPT_STAGE,
        "selected_case_ids": selected,
        "case_ids_sha256": _canonical_json_sha256_text(selected),
        "eligible_case_ids": eligible,
        "unselected_eligible_case_ids": eligible[scheduled_calls:],
        "scheduled_calls": scheduled_calls,
        "hard_cap": allocation,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _write_retest_case_ids_file(case_ids_file, selected_case_ids):
    case_ids_file = Path(case_ids_file)
    case_ids_file.parent.mkdir(parents=True, exist_ok=True)
    with open(case_ids_file, "w", encoding="utf-8") as f:
        json.dump(selected_case_ids, f, ensure_ascii=False)


def _validate_retest_manifest_identity(manifest):
    """Fail-closed identity check of the five frozen fields (v3 P0-3).

    Any drift in selected IDs / case_ids_sha256 / scheduled_calls / hard_cap /
    attempt_stage is a contract rejection (exit 2); resume must NOT recompute
    eligible, re-order, or mint a new case IDs file.
    """
    missing = [f for f in RETEST_FROZEN_FIELDS if f not in manifest]
    if missing:
        _contract_reject(f"retest manifest reject: missing frozen fields {missing}")
    if manifest["attempt_stage"] != RETEST_ATTEMPT_STAGE:
        _contract_reject(
            f"retest manifest drift: attempt_stage={manifest['attempt_stage']!r} "
            f"!= {RETEST_ATTEMPT_STAGE!r}")
    selected = manifest["selected_case_ids"]
    if _canonical_json_sha256_text(selected) != manifest["case_ids_sha256"]:
        _contract_reject("retest manifest drift: selected_case_ids != case_ids_sha256")
    if not isinstance(manifest["scheduled_calls"], int) \
            or manifest["scheduled_calls"] != len(selected):
        _contract_reject(
            f"retest manifest drift: scheduled_calls={manifest['scheduled_calls']!r} "
            f"!= len(selected_case_ids)={len(selected)}")
    if not isinstance(manifest["hard_cap"], int) or manifest["hard_cap"] <= 0:
        _contract_reject(
            f"retest manifest drift: hard_cap={manifest['hard_cap']!r} invalid")


def _load_retest_manifest_for_resume(runs_root, main_events_path):
    """Resume path: reuse the five frozen fields verbatim from the stored manifest.

    Forbidden here: recomputing eligible, re-ordering selected IDs, writing a new
    case IDs file. Drift vs the frozen allocation (180 - main call_attempt) or a
    missing/mismatched case IDs file is fail-closed (exit 2).
    """
    paths = _retest_paths(runs_root)
    if not paths["manifest"].exists():
        _contract_reject("retest resume reject: retest manifest missing")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    _validate_retest_manifest_identity(manifest)
    allocation = _compute_retest_allocation(main_events_path)
    if manifest["hard_cap"] != allocation:
        _contract_reject(
            f"retest manifest drift: hard_cap={manifest['hard_cap']} != "
            f"frozen allocation={allocation} (180 - main call_attempt)")
    if not paths["case_ids_file"].exists():
        _contract_reject("retest resume reject: case IDs file missing; "
                         "forbidden to regenerate on resume")
    on_disk = json.loads(paths["case_ids_file"].read_text(encoding="utf-8"))
    if on_disk != manifest["selected_case_ids"]:
        _contract_reject("retest resume reject: case IDs file drift vs manifest "
                         "selected_case_ids (order included)")
    retest_consumed = (_count_call_attempts(paths["events"])
                       if paths["events"].exists() else 0)
    main_consumed = _count_call_attempts(main_events_path)
    if main_consumed + retest_consumed > HARD_CAP:
        _blocked(f"global budget exceeded before retest resume: "
                 f"main={main_consumed} + retest={retest_consumed} > {HARD_CAP}")
    manifest = dict(manifest)
    manifest["retest_consumed"] = retest_consumed
    manifest["remaining_budget"] = manifest["hard_cap"] - retest_consumed
    return manifest


def _retest_slice_info(runs_root, manifest):
    paths = _retest_paths(runs_root)
    return {
        "dataset_path": str(Path(runs_root) / f"{NORMALIZED_DATASET_NAME}.jsonl"),
        "case_ids_file": str(paths["case_ids_file"]),
        "detail_path": str(paths["detail"]),
        "output_dir": str(paths["dir"]),
        "attempt_stage": RETEST_ATTEMPT_STAGE,
        "scheduled_calls": manifest["scheduled_calls"],
        "hard_cap": manifest["hard_cap"],
        "max_cases": manifest["scheduled_calls"],
    }


def _compute_retest_report(manifest, retest_detail_path):
    """Both unretested classes go into the report: eligible-but-unselected
    (budget exhausted) and selected-but-not-executed (squeezed by retries)."""
    retested = {r.get("case_id") for r in _load_jsonl(retest_detail_path)
                if r.get("terminal_state") in TERMINAL_STATES}
    selected_not_executed = [c for c in manifest["selected_case_ids"]
                             if c not in retested]
    return {
        "retested_case_ids": sorted(retested),
        "unselected_eligible_case_ids": list(
            manifest.get("unselected_eligible_case_ids", [])),
        "selected_not_executed_case_ids": selected_not_executed,
    }


# -- Completeness hard gates / archive / receipt (design §8) --


def _expected_chart_quota(chart_case_id):
    return CHART_QUOTA_OVERRIDES.get(chart_case_id, 5)


def _check_completeness(runs_root, merged_details_path=None, audit_index=None):
    """Design §8.1 twelve hard gates, fail-closed. Any failure ->
    completeness_verdict = BLOCKED_INCOMPLETE (no baseline receipt published).

    Clause 9 is only meaningful after the archive exists; pre-archive it is
    deferred (the archive self-verify + post-archive recheck close the hole).
    """
    runs_root = Path(runs_root)
    main_rows = _load_jsonl(runs_root / "main" / "detail.jsonl")
    retest_rows = _load_jsonl(runs_root / "retest" / "detail.jsonl")
    norm_rows = _load_jsonl(runs_root / f"{NORMALIZED_DATASET_NAME}.jsonl")
    norm_chart_by_case = {r.get("case_id"): r.get("chart_case_id") for r in norm_rows}

    main_terminal = [r for r in main_rows
                     if r.get("terminal_state") in ARM_TERMINAL_STATES]
    retest_terminal = [r for r in retest_rows
                       if r.get("terminal_state") in ARM_TERMINAL_STATES]
    all_terminal = main_terminal + retest_terminal
    checks = []

    def _record(clause, name, passed, detail=""):
        checks.append({"clause": clause, "name": name,
                       "passed": bool(passed), "detail": detail})

    # 1. main first-pass terminal rows == 160
    _record(1, "main_terminal_rows", len(main_terminal) == SCHEDULED_CALLS,
            f"{len(main_terminal)} != {SCHEDULED_CALLS}")
    # 2. main unique question case_id (mingli_ftb_*) == 160
    main_ids = [r.get("case_id") for r in main_terminal]
    unique_ids = set(main_ids)
    _record(2, "unique_question_case_ids", len(unique_ids) == SCHEDULED_CALLS,
            f"{len(unique_ids)} != {SCHEDULED_CALLS}")
    # 3. exactly 1 main terminal per case_id
    dup = sorted(c for c, n in Counter(main_ids).items() if n > 1)
    _record(3, "one_terminal_per_case_id", not dup, f"duplicates: {dup[:5]}")
    # 4. unique chart_case_id == 32 + frozen distribution (30x5 + case_19x6 +
    #    case_20x4), cross-validated against the normalized dataset
    detail_chart_counts = Counter(r.get("chart_case_id") for r in main_terminal)
    norm_chart_counts = Counter(norm_chart_by_case.values())
    dist_ok = (
        len(detail_chart_counts) == EXPECTED_CHART_COUNT
        and detail_chart_counts == norm_chart_counts
        and all(n == _expected_chart_quota(c)
                for c, n in detail_chart_counts.items()))
    _record(4, "chart_distribution_frozen", dist_ok,
            f"detail_charts={len(detail_chart_counts)} "
            f"norm_charts={len(norm_chart_counts)}")
    # 5. terminal states only in the frozen arm enum (this arm never produces
    #    unresolved/judge_unresolved; gate_blocked rows are fatal here)
    bad_states = sorted({r.get("terminal_state") for r in main_rows + retest_rows}
                        - set(ARM_TERMINAL_STATES))
    _record(5, "terminal_state_enum", not bad_states, f"bad states: {bad_states}")
    # 6. first_pass denominator fixed = 160 (attempt stage of every main
    #    terminal row must be "main")
    first_pass = [r for r in main_terminal
                  if isinstance(r.get("attempt_key"), list)
                  and len(r["attempt_key"]) > 3
                  and r["attempt_key"][3] == "main"]
    _record(6, "first_pass_denominator", len(first_pass) == SCHEDULED_CALLS,
            f"{len(first_pass)} != {SCHEDULED_CALLS}")
    # 7. controlled_retest <= 1 per question and retest case_ids subset of the
    #    main invalid/call_failed set
    eligible = {r.get("case_id") for r in main_terminal
                if r.get("terminal_state") in RETEST_ELIGIBLE_STATES}
    retest_ids = [r.get("case_id") for r in retest_terminal]
    retest_dups = sorted(c for c, n in Counter(retest_ids).items() if n > 1)
    retest_outside = sorted(set(retest_ids) - eligible)
    _record(7, "retest_once_and_subset", not retest_dups and not retest_outside,
            f"dups={retest_dups[:5]} outside={retest_outside[:5]}")
    # 8. main + retest call_attempt events <= 180
    main_attempts = _count_call_attempts(runs_root / "main" / "detail.events.jsonl")
    retest_attempts = _count_call_attempts(
        runs_root / "retest" / "detail.events.jsonl")
    attempted = main_attempts + retest_attempts
    _record(8, "global_budget", attempted <= HARD_CAP,
            f"{main_attempts}+{retest_attempts}={attempted} > {HARD_CAP}")
    # 9. merged_details SHA-256 matches the audit index record
    if merged_details_path is None and audit_index is None:
        _record(9, "merged_details_sha", True, "deferred to archive self-verify")
    else:
        ok = False
        detail = ""
        if merged_details_path is None or audit_index is None:
            detail = "merged_details_path/audit_index incomplete"
        elif not os.path.exists(merged_details_path):
            detail = f"merged details missing: {merged_details_path}"
        else:
            recorded = audit_index.get("merged_details_sha256")
            actual = _sha256_file(merged_details_path)
            ok = recorded is not None and recorded == actual
            detail = f"recorded={recorded!r} actual={actual!r}"
        _record(9, "merged_details_sha", ok, detail)
    # 10. all successful calls thinking_mode == disabled
    bad_thinking = sorted({r.get("case_id") for r in all_terminal
                           if r.get("terminal_state") in ("parsed", "invalid")
                           and r.get("thinking_mode") != FROZEN_THINKING_MODE})
    _record(10, "thinking_mode_disabled", not bad_thinking,
            f"rows: {bad_thinking[:5]}")
    # 11. response_model, when present, must equal the frozen model
    bad_model = sorted({r.get("response_model") for r in all_terminal
                        if r.get("response_model") is not None
                        and r.get("response_model") != FROZEN_MODEL})
    _record(11, "response_model_frozen", not bad_model, f"values: {bad_model}")
    # 12. per-row chart_case_id joins the normalized dataset by question
    #     case_id (no missing, no mismatch), main and retest rows alike
    join_missing = sorted({r.get("case_id") for r in all_terminal
                           if r.get("case_id") not in norm_chart_by_case})
    join_mismatch = sorted({r.get("case_id") for r in all_terminal
                            if r.get("case_id") in norm_chart_by_case
                            and r.get("chart_case_id")
                            != norm_chart_by_case[r.get("case_id")]})
    _record(12, "chart_case_id_join", not join_missing and not join_mismatch,
            f"missing={join_missing[:5]} mismatch={join_mismatch[:5]}")

    n_parsed = sum(1 for r in main_terminal if r.get("terminal_state") == "parsed")
    n_correct = sum(1 for r in main_terminal if r.get("correct"))
    stats = {
        "question_id_count": len(unique_ids),
        "chart_case_count": len(detail_chart_counts),
        "chart_distribution": dict(sorted(detail_chart_counts.items())),
        "terminal_state_counts": {
            "main": dict(sorted(Counter(r.get("terminal_state")
                                        for r in main_terminal).items())),
            "controlled_retest": dict(sorted(Counter(r.get("terminal_state")
                                                     for r in retest_terminal).items())),
        },
        # §8.1 clause 6: denominators are fixed at 160 regardless of row count
        "parser_rate": n_parsed / SCHEDULED_CALLS,
        "first_pass_accuracy": n_correct / SCHEDULED_CALLS,
        "attempted": attempted,
        "response_model_values": sorted({r.get("response_model") for r in all_terminal
                                         if r.get("response_model") is not None}),
        "response_model_missing_count": sum(
            1 for r in all_terminal if r.get("response_model") is None),
    }
    verdict = "COMPLETE" if all(c["passed"] for c in checks) else "BLOCKED_INCOMPLETE"
    return {"verdict": verdict, "checks": checks, "stats": stats}


def _runner_code_fingerprint():
    from benchmark.runners.resume_ledger import _code_fingerprint
    return _code_fingerprint()


def _prompt_fingerprint():
    from benchmark.runners.profiles import prompt_fingerprint, resolve_profile
    return prompt_fingerprint(resolve_profile(FROZEN_PROFILE, CHART_SCHEMA))


def _pinned_commit():
    from scripts.fetch_mingli_bench import PINNED_COMMIT
    return PINNED_COMMIT


def _load_fetch_provenance():
    """license_sha256 from the fetch manifest if one exists; pinned_commit is
    the frozen constant (three-way verified). Missing manifest records None."""
    for rel in FETCH_MANIFEST_CANDIDATES:
        p = os.path.join(_PROJECT_ROOT, rel)
        if os.path.exists(p):
            try:
                data = json.loads(open(p, encoding="utf-8").read())
            except (OSError, json.JSONDecodeError):
                continue
            return {"pinned_commit": data.get("pinned_commit"),
                    "license_sha256": data.get("license_sha256")}
    return {"pinned_commit": None, "license_sha256": None}


def _build_audit_index(archive_dir, context, completeness, merged_sha):
    """Design §8.3: receipt-level fields + per-artifact SHA + per-clause
    results + retest lists + run context."""
    archive_dir = Path(archive_dir)
    artifact_sha = {}
    for label, rel in (
            ("main_detail", "main/detail.jsonl"),
            ("main_events", "main/detail.events.jsonl"),
            ("retest_detail", "retest/detail.jsonl"),
            ("retest_events", "retest/detail.events.jsonl"),
            ("retest_manifest", f"retest/{RETEST_MANIFEST_NAME}"),
            ("run_manifest", RUN_MANIFEST_NAME),
            ("normalized_jsonl", f"{NORMALIZED_DATASET_NAME}.jsonl")):
        artifact_sha[f"{label}_sha256"] = _sha256_file(archive_dir / rel)
    prov = _load_fetch_provenance()
    return {
        "run_id": context["run_id"],
        "user_run_id": context["run_id"],
        "experiment_id": EXPERIMENT_ID,
        "stage": "baseline",
        "frozen_date": FROZEN_DATE,
        "provider": FROZEN_PROVIDER,
        "model": FROZEN_MODEL,
        "thinking_mode": FROZEN_THINKING_MODE,
        "temperature": FROZEN_TEMPERATURE,
        "model_label": MODEL_LABEL,
        "profile": FROZEN_PROFILE,
        "method": FROZEN_METHOD,
        "arm": FROZEN_ARM,
        "code_fingerprint": _runner_code_fingerprint(),
        "prompt_fingerprint": _prompt_fingerprint(),
        "phase7_code_fingerprint": _phase7_code_fingerprint(),
        "mingli_data_sha256": context.get("data_json_sha256"),
        "fortune_api_sha256": context.get("fortune_json_sha256"),
        "normalized_jsonl_sha256": artifact_sha["normalized_jsonl_sha256"],
        "pinned_commit": _pinned_commit(),
        "license_sha256": prov["license_sha256"],
        "env_flags": _env_flags(),
        "budget": {"scheduled_calls": SCHEDULED_CALLS, "hard_cap": HARD_CAP,
                   "attempted": completeness["stats"]["attempted"]},
        "smoke_size": SMOKE_SIZE,
        "smoke_verdict": context.get("smoke_verdict"),
        "max_cases_transitions": context.get("max_cases_transitions", []),
        "completeness_verdict": completeness["verdict"],
        "completeness_checks": completeness["checks"],
        "retest_report": context.get("retest_report"),
        "merged_details_sha256": merged_sha,
        "artifact_sha256": artifact_sha,
        "run_context": dict(context),
        "archived_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _create_archive(runs_root, context, completeness):
    """Atomic archive (design §8.5): build in a tmp dir, self-verify the
    merged_details SHA, then os.replace into place."""
    runs_root = Path(runs_root)
    archive_dir = runs_root / ARCHIVE_DIR_NAME
    tmp_dir = runs_root / f".{ARCHIVE_DIR_NAME}.tmp-{os.getpid()}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        for name in ("main", "retest"):
            src = runs_root / name
            if src.exists():
                shutil.copytree(str(src), str(tmp_dir / name))
        for name in (f"{NORMALIZED_DATASET_NAME}.jsonl", MAIN_CASE_IDS_NAME,
                     RUN_MANIFEST_NAME, RUN_CONTEXT_NAME):
            src = runs_root / name
            if src.exists():
                shutil.copy2(str(src), str(tmp_dir / name))
        merged_rows = [
            r for r in _load_jsonl(runs_root / "main" / "detail.jsonl")
            + _load_jsonl(runs_root / "retest" / "detail.jsonl")
            if r.get("terminal_state") in ARM_TERMINAL_STATES]
        merged_path = tmp_dir / MERGED_DETAILS_NAME
        with open(merged_path, "w", encoding="utf-8") as f:
            for row in merged_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        md_sha = _sha256_file(merged_path)
        audit = _build_audit_index(tmp_dir, context, completeness, md_sha)
        audit_path = tmp_dir / AUDIT_INDEX_NAME
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        if _sha256_file(merged_path) != md_sha:
            raise SystemExit("archive self-verify reject: merged_details SHA unstable")
        audit_sha = _sha256_file(audit_path)
        if archive_dir.exists():
            shutil.rmtree(archive_dir)
        os.replace(str(tmp_dir), str(archive_dir))
        return {"archive_dir": str(archive_dir),
                "audit_index": audit,
                "audit_index_path": str(archive_dir / AUDIT_INDEX_NAME),
                "audit_index_sha256": audit_sha,
                "merged_details_path": str(archive_dir / MERGED_DETAILS_NAME),
                "merged_details_sha256": md_sha}
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _build_receipt(runs_root, context, completeness, archive_result):
    """Design §8.2 field set. audit_index_sha256 is the value captured at
    archive time so post-archive tampering is detected before publish."""
    runs_root = Path(runs_root)
    stats = completeness["stats"]
    prov = _load_fetch_provenance()
    env_flags = _env_flags()
    return {
        "stage": "baseline",
        "run_id": context["run_id"],
        "user_run_id": context["run_id"],
        "archive_dir": archive_result["archive_dir"],
        "audit_index_sha256": archive_result["audit_index_sha256"],
        "provider": FROZEN_PROVIDER,
        "model": FROZEN_MODEL,
        "thinking_mode": FROZEN_THINKING_MODE,
        "temperature": FROZEN_TEMPERATURE,
        "model_label": MODEL_LABEL,
        "profile": FROZEN_PROFILE,
        "method": FROZEN_METHOD,
        "arm": FROZEN_ARM,
        "attempt_stage": "main",
        "code_fingerprint": _runner_code_fingerprint(),
        "prompt_fingerprint": _prompt_fingerprint(),
        "phase7_code_fingerprint": _phase7_code_fingerprint(),
        "mingli_data_sha256": context.get("data_json_sha256"),
        "fortune_api_sha256": context.get("fortune_json_sha256"),
        "normalized_jsonl_sha256": _sha256_file(
            runs_root / f"{NORMALIZED_DATASET_NAME}.jsonl"),
        "pinned_commit": _pinned_commit(),
        "license_sha256": prov["license_sha256"],
        "rag": env_flags["rag"],
        "fewshot": env_flags["fewshot"],
        "apb": env_flags["apb"],
        "shuffle_options": env_flags["shuffle_options"],
        "scheduled_calls": SCHEDULED_CALLS,
        "hard_cap": HARD_CAP,
        "attempted": stats["attempted"],
        "first_pass_accuracy": stats["first_pass_accuracy"],
        "parser_rate": stats["parser_rate"],
        "terminal_state_counts": stats["terminal_state_counts"],
        "completeness_verdict": completeness["verdict"],
        "smoke_size": SMOKE_SIZE,
        "question_id_count": stats["question_id_count"],
        "chart_case_count": stats["chart_case_count"],
        "response_model_values": stats["response_model_values"],
        "response_model_missing_count": stats["response_model_missing_count"],
    }


def _validate_receipt_fields(receipt):
    """§8.2 fail-closed presence + consistency check (exit 4 on violation)."""
    missing = [f for f in RECEIPT_REQUIRED_FIELDS if f not in receipt]
    if missing:
        _blocked(f"receipt reject: missing fields {missing}")
    if receipt["model_label"] != MODEL_LABEL:
        _blocked(f"receipt reject: model_label={receipt['model_label']!r} "
                 f"!= {MODEL_LABEL!r}")
    if receipt["scheduled_calls"] != SCHEDULED_CALLS \
            or receipt["hard_cap"] != HARD_CAP:
        _blocked("receipt reject: scheduled_calls/hard_cap drift "
                 f"({receipt['scheduled_calls']}/{receipt['hard_cap']})")
    if receipt["question_id_count"] != SCHEDULED_CALLS:
        _blocked(f"receipt reject: question_id_count="
                 f"{receipt['question_id_count']} != {SCHEDULED_CALLS}")
    if receipt["chart_case_count"] != EXPECTED_CHART_COUNT:
        _blocked(f"receipt reject: chart_case_count="
                 f"{receipt['chart_case_count']} != {EXPECTED_CHART_COUNT}")
    if receipt["completeness_verdict"] != "COMPLETE":
        _blocked(f"receipt reject: completeness_verdict="
                 f"{receipt['completeness_verdict']!r} != 'COMPLETE'")
    for flag in ("rag", "fewshot", "apb", "shuffle_options"):
        if receipt[flag] is not False:
            _blocked(f"receipt reject: env flag {flag}={receipt[flag]!r} not False")
    bad = [v for v in receipt["response_model_values"] if v != FROZEN_MODEL]
    if bad:
        _blocked(f"receipt reject: response_model_values drift {bad}")


def _validate_four_layer_fingerprint(run_manifest, run_context, audit_index, receipt):
    """§8.4/§8.3: phase7_code_fingerprint must be present and identical to the
    freshly computed value in all four layers (manifest/context/audit/receipt)."""
    expected = _phase7_code_fingerprint()
    for layer_name, layer in (("run_manifest", run_manifest),
                              ("run_context", run_context),
                              ("audit_index", audit_index),
                              ("receipt", receipt)):
        value = layer.get("phase7_code_fingerprint") if isinstance(layer, dict) else None
        if value is None:
            _blocked(f"phase7_code_fingerprint missing in {layer_name}")
        if value != expected:
            _blocked(f"phase7_code_fingerprint drift in {layer_name}: "
                     f"{value} != {expected}")


def _publish_receipt_atomic(target_dir, receipt_name,
                            validated_bytes=None, expected_sha256=None):
    """Aligned with 6D _publish_receipt_atomic (:1280): write pre-validated
    bytes to tmp, recompute SHA and compare, then os.replace. Never re-reads a
    mutable source after validation (TOCTOU fix)."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    receipt_dst = target_dir / receipt_name
    tmp_dst = receipt_dst.with_suffix(".tmp")
    if validated_bytes is None:
        raise SystemExit("publish receipt reject: validated_bytes required")
    tmp_dst.write_bytes(validated_bytes)
    actual_sha = _sha256_file(str(tmp_dst))
    if expected_sha256 is None or actual_sha != expected_sha256:
        tmp_dst.unlink(missing_ok=True)
        raise SystemExit(
            f"publish receipt reject: SHA mismatch "
            f"(expected={expected_sha256!r}, actual={actual_sha!r})")
    os.replace(str(tmp_dst), str(receipt_dst))


# -- Stage executors (subprocess boundaries; tests monkeypatch these) --


def _ensure_normalized_dataset(runs_root):
    """Normalize via the dual-primary-key adapter -> single 160-question JSONL +
    single case_ids_file (design §3.2 single slice). SHA goes to the manifest."""
    from benchmark.runners.mingli_bench_adapter import load_and_normalize

    runs_root = Path(runs_root)
    dataset_path = runs_root / f"{NORMALIZED_DATASET_NAME}.jsonl"
    case_ids_file = runs_root / MAIN_CASE_IDS_NAME
    if dataset_path.exists() and case_ids_file.exists():
        return dataset_path
    rows = load_and_normalize(
        os.path.join(_PROJECT_ROOT, DATA_JSON_PATH),
        fortune_api_json_path=os.path.join(_PROJECT_ROOT, FORTUNE_JSON_PATH),
        include_astro=True,
    )
    with open(dataset_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(case_ids_file, "w", encoding="utf-8") as f:
        json.dump([r["case_id"] for r in rows], f, ensure_ascii=False)
    return dataset_path


def _run_runner_subprocess(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=7200, cwd=_PROJECT_ROOT,
                            env=_build_child_env())
    if result.returncode != 0:
        _blocked(f"runner failed (exit={result.returncode}): "
                 f"{(result.stderr or '')[:500]}")
    return result


def _ensure_slice_output_dir(slice_info):
    """真实 runner 的 resume_ledger._atomic_write_json 不建父目录（manifest 路径
    派生自 --case-details-jsonl）；executor 必须在 runner 子进程调用前建好
    detail 父目录，否则首跑即 FileNotFoundError -> runner exit=1 -> BLOCKED。"""
    Path(slice_info["detail_path"]).parent.mkdir(parents=True, exist_ok=True)


def _execute_smoke(runs_root, context):
    _ensure_normalized_dataset(runs_root)
    slice_info = _main_slice_info(runs_root, SMOKE_SIZE)
    _ensure_slice_output_dir(slice_info)
    cmd = _build_runner_command(slice_info)
    _run_runner_subprocess(cmd)
    context["smoke_completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")


def _execute_main_resume(runs_root, context):
    slice_info = _main_slice_info(runs_root, MAIN_MAX_CASES)
    _ensure_slice_output_dir(slice_info)
    cmd = _build_runner_command(slice_info, resume=True)
    _run_runner_subprocess(cmd)
    ledger = BudgetLedger(Path(runs_root) / BUDGET_LEDGER_NAME, HARD_CAP)
    main_events = str(slice_info["detail_path"]).replace(".jsonl", ".events.jsonl")
    ledger.record_slice_completed("main", _count_call_attempts(main_events),
                                  SCHEDULED_CALLS)


def _execute_retest(runs_root, context):
    runs_root = Path(runs_root)
    main_slice = _main_slice_info(runs_root, MAIN_MAX_CASES)
    main_detail = main_slice["detail_path"]
    main_events = main_detail.replace(".jsonl", ".events.jsonl")
    paths = _retest_paths(runs_root)
    ledger = BudgetLedger(runs_root / BUDGET_LEDGER_NAME, HARD_CAP)
    if paths["manifest"].exists():
        # crash/resume: reuse frozen identity, never re-claim budget
        manifest = _load_retest_manifest_for_resume(runs_root, main_events)
        resume = True
    else:
        manifest = _plan_retest(main_detail, main_events)
        if manifest["scheduled_calls"] == 0:
            _atomic_write_json(paths["manifest"], manifest)
            context["retest_report"] = _compute_retest_report(
                manifest, paths["detail"])
            return manifest
        _write_retest_case_ids_file(paths["case_ids_file"],
                                    manifest["selected_case_ids"])
        _atomic_write_json(paths["manifest"], manifest)
        # pre-occupy the remaining budget in the single global ledger
        ledger.record_slice_completed(
            "retest_prealloc", manifest["hard_cap"], manifest["scheduled_calls"])
        resume = False
    slice_info = _retest_slice_info(runs_root, manifest)
    _ensure_slice_output_dir(slice_info)
    cmd = _build_runner_command(slice_info, resume=resume)
    _run_runner_subprocess(cmd)
    context["retest_report"] = _compute_retest_report(manifest, paths["detail"])
    return manifest


def _execute_finalize(runs_root, context):
    """Finalize chain (design §8): §8.1 twelve hard gates -> atomic archive +
    audit_index.json -> clause-9 post-archive recheck -> receipt build +
    fail-closed validation -> four-layer fingerprint check -> audit index SHA
    recheck -> receipt atomic publish -> run context stage=published.

    BLOCKED_INCOMPLETE publishes no receipt (exit 4).
    """
    runs_root = Path(runs_root)
    completeness = _check_completeness(runs_root)
    context["completeness"] = completeness
    if completeness["verdict"] != "COMPLETE":
        _save_context(runs_root, context)
        failed = [c["clause"] for c in completeness["checks"] if not c["passed"]]
        _blocked(f"completeness hard gate: {completeness['verdict']} "
                 f"(failed clauses: {failed}); receipt NOT published")
    archive_result = _create_archive(runs_root, context, completeness)
    recheck = _check_completeness(
        runs_root,
        merged_details_path=archive_result["merged_details_path"],
        audit_index=archive_result["audit_index"])
    failed = [c["clause"] for c in recheck["checks"] if not c["passed"]]
    if failed:
        _blocked(f"archive self-verify failed: clauses {failed}")
    receipt = _build_receipt(runs_root, context, completeness, archive_result)
    _validate_receipt_fields(receipt)
    run_manifest = json.loads(
        (runs_root / RUN_MANIFEST_NAME).read_text(encoding="utf-8"))
    _validate_four_layer_fingerprint(
        run_manifest, context, archive_result["audit_index"], receipt)
    # pre-publish audit index SHA recheck: missing or drift -> exit 4
    audit_path = archive_result["audit_index_path"]
    if not os.path.exists(audit_path):
        _blocked(f"audit index missing before publish: {audit_path}")
    if _sha256_file(audit_path) != receipt["audit_index_sha256"]:
        _blocked("audit index SHA drift before publish; refusing receipt")
    payload = json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8")
    _publish_receipt_atomic(runs_root, RECEIPT_FILENAME,
                            validated_bytes=payload,
                            expected_sha256=hashlib.sha256(payload).hexdigest())
    context["stage"] = STAGE_PUBLISHED
    context["published_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _save_context(runs_root, context)


# -- run flow (single-slice state machine, self-driving) --


def run_mingli_baseline(run_id, resume=False, output_dir=".tmp/phase7/run"):
    _validate_run_id(run_id)
    _validate_preflight_for_run()  # fail-closed 准入门：先于 run 目录创建与任何 runner/API 调用
    runs_root, context = _prepare_run_context(output_dir, run_id, resume)
    stage = context["stage"]
    if stage == STAGE_PUBLISHED:
        _contract_reject(f"run_id={run_id!r} already published")
    if stage == STAGE_SMOKE:
        _execute_smoke(runs_root, context)
        slice_info = _main_slice_info(runs_root, SMOKE_SIZE)
        verdict = _judge_smoke(
            slice_info["detail_path"],
            slice_info["detail_path"].replace(".jsonl", ".events.jsonl"))
        context["smoke_verdict"] = verdict
        if not verdict["passed"]:
            _save_context(runs_root, context)
            _blocked(f"smoke verdict failed: {verdict['failures']}")
        _advance_max_cases(context, MAIN_MAX_CASES)
        context["stage"] = STAGE_MAIN_RESUME
        _save_context(runs_root, context)
        stage = STAGE_MAIN_RESUME
    if stage == STAGE_MAIN_RESUME:
        _execute_main_resume(runs_root, context)
        context["stage"] = STAGE_RETEST
        _save_context(runs_root, context)
        stage = STAGE_RETEST
    if stage == STAGE_RETEST:
        _execute_retest(runs_root, context)
        context["stage"] = STAGE_FINALIZE
        _save_context(runs_root, context)
        stage = STAGE_FINALIZE
    if stage == STAGE_FINALIZE:
        _execute_finalize(runs_root, context)
    return {"status": "ok", "run_id": run_id, "stage": context["stage"]}


# -- preflight (zero-API assertion chain, plan Task 7.2; design §4) --

PREFLIGHT_RECEIPT_PATH = "docs/phase7/preflight_receipt.json"
# 计划头部设计冻结事实（pinned commit b7433280，三方核对一致）
FROZEN_DATA_JSON_SHA256 = "528240929b23859656bf7ec0c126da92e2523c2cf091b11f83c0e8e377412054"
FROZEN_FORTUNE_JSON_SHA256 = "e44ff5201486dc1917bbb24b6905a53e6a1359e76ada0eb8d5b2d9a5a88d29ed"
EXPECTED_YEAR_SET = frozenset({"2022", "2023", "2024", "2025"})
EXPECTED_CATEGORY_COUNT = 12
OFFICIAL_ASTRO_REQUIRED = frozenset(
    {"八字命盘信息：", "紫微命盘信息：", "十二宫位星曜分布："})
_FTB_ID_RE = re.compile(r"^ftb_(\d{4})$")


def _preflight_visibility_required():
    """official profile + ziwei_arm=None 的 required markers（独立函数以便测试
    monkeypatch 强制失败）。"""
    from benchmark.runners.profiles import resolve_profile, visibility_requirements
    profile = resolve_profile(FROZEN_PROFILE, CHART_SCHEMA)
    required, _ = visibility_requirements(profile, CHART_SCHEMA, ziwei_arm=None)
    return profile, required


def _preflight_parse(text):
    """官方 CoT `答案：X` 提取链（runner 计分实际使用的 parser）。"""
    from benchmark.scorers.choice_accuracy import extract_choice_with_meta
    return extract_choice_with_meta(text)


def run_preflight(work_dir, data_json_path=None, fortune_json_path=None,
                  receipt_path=None):
    """Plan Task 7.2 zero-API assertion chain: data integrity + protocol +
    env sanitizer + budget. Always writes the receipt first; any failed check
    -> verdict BLOCKED and exit 4 (fail-closed)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    data_json_path = str(data_json_path or os.path.join(_PROJECT_ROOT, DATA_JSON_PATH))
    fortune_json_path = str(fortune_json_path or os.path.join(_PROJECT_ROOT, FORTUNE_JSON_PATH))
    receipt_path = str(receipt_path or os.path.join(_PROJECT_ROOT, PREFLIGHT_RECEIPT_PATH))

    checks = []

    def _record(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    data_sha = _sha256_file(data_json_path)
    fortune_sha = _sha256_file(fortune_json_path)
    data_bytes = os.path.getsize(data_json_path) if os.path.exists(data_json_path) else 0
    fortune_bytes = os.path.getsize(fortune_json_path) if os.path.exists(fortune_json_path) else 0
    _record("data_sha256",
            data_sha == FROZEN_DATA_JSON_SHA256
            and fortune_sha == FROZEN_FORTUNE_JSON_SHA256,
            f"data={data_sha} fortune={fortune_sha}")

    # -- 完整性（design §4.2）--
    raw_entries = None
    load_error = ""
    try:
        loaded = json.loads(Path(data_json_path).read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            raw_entries = loaded
        elif isinstance(loaded, dict) and isinstance(loaded.get("questions"), list):
            raw_entries = loaded["questions"]
        else:
            load_error = f"unexpected data.json shape: {type(loaded).__name__}"
    except Exception as exc:
        load_error = f"{type(exc).__name__}: {exc}"
    entries = [e for e in raw_entries or [] if isinstance(e, dict)]

    n_questions = len(entries) if raw_entries is not None else -1
    _record("question_count", n_questions == SCHEDULED_CALLS,
            (f"{n_questions} != {SCHEDULED_CALLS} {load_error}").strip())

    ids = [str(e.get("id") or "") for e in entries]
    id_nums = []
    ids_wellformed = len(ids) == n_questions
    for qid in ids:
        m = _FTB_ID_RE.match(qid)
        if m:
            id_nums.append(int(m.group(1)))
        else:
            ids_wellformed = False
    _record("unique_question_ids",
            ids_wellformed and len(set(ids)) == SCHEDULED_CALLS
            and sorted(id_nums) == list(range(1, SCHEDULED_CALLS + 1)),
            f"unique={len(set(ids))} wellformed={ids_wellformed}")

    chart_counts = Counter(str(e.get("case_id") or "") for e in entries)
    _record("unique_chart_case_ids", len(chart_counts) == EXPECTED_CHART_COUNT,
            f"{len(chart_counts)} != {EXPECTED_CHART_COUNT}")
    bad_charts = {c: n for c, n in sorted(chart_counts.items())
                  if not c or n != _expected_chart_quota(c)}
    _record("chart_distribution_frozen",
            len(chart_counts) == EXPECTED_CHART_COUNT and not bad_charts,
            f"bad={bad_charts}" if bad_charts else "30x5+case_19x6+case_20x4")

    norm_rows = None
    norm_error = ""
    try:
        from benchmark.runners.mingli_bench_adapter import load_and_normalize
        norm_rows = load_and_normalize(
            data_json_path, fortune_api_json_path=fortune_json_path,
            include_astro=True)
    except Exception as exc:
        norm_error = f"{type(exc).__name__}: {exc}"
    norm_ids = [r.get("case_id") for r in norm_rows or []]
    norm_charts = {r.get("chart_case_id") for r in norm_rows or []}
    _record("adapter_normalization",
            norm_rows is not None and len(norm_rows) == SCHEDULED_CALLS
            and len(set(norm_ids)) == SCHEDULED_CALLS
            and all(str(i).startswith("mingli_ftb_") for i in norm_ids)
            and len(norm_charts) == EXPECTED_CHART_COUNT,
            norm_error or f"rows={len(norm_rows or [])} "
                          f"unique_ids={len(set(norm_ids))} charts={len(norm_charts)}")

    fortune_keys = set()
    try:
        loaded_f = json.loads(Path(fortune_json_path).read_text(encoding="utf-8"))
        if isinstance(loaded_f, dict):
            fortune_keys = {str(k) for k in loaded_f}
        elif isinstance(loaded_f, list):
            fortune_keys = {str(i.get("case_id")) for i in loaded_f
                            if isinstance(i, dict) and i.get("case_id")}
    except Exception:
        pass
    missing_charts = sorted(norm_charts - fortune_keys)
    rows_with_chart = sum(1 for r in norm_rows or [] if r.get("chart_input"))
    _record("fortune_join",
            len(norm_charts) == EXPECTED_CHART_COUNT and not missing_charts
            and rows_with_chart == SCHEDULED_CALLS,
            f"hit={len(norm_charts & fortune_keys)}/{len(norm_charts)} "
            f"rows_with_chart_input={rows_with_chart} "
            f"missing={missing_charts[:3]}")

    year_dist, cat_dist = {}, {}
    years, categories = [], []
    try:
        from benchmark.runners.mingli_bench_adapter import _infer_year
        years = [_infer_year(e) for e in entries]
        categories = [str(e.get("category") or "") for e in entries]
        year_dist = dict(sorted(Counter(years).items()))
        cat_dist = dict(sorted(Counter(categories).items()))
    except Exception as exc:
        load_error = f"{type(exc).__name__}: {exc}"
    _record("year_category_distribution",
            bool(years) and set(years) <= EXPECTED_YEAR_SET
            and len(cat_dist) == EXPECTED_CATEGORY_COUNT,
            f"years={sorted(set(years))} categories={len(cat_dist)} {load_error}".strip())

    # -- 协议（design §4.3）--
    profile, required, proto_error = None, frozenset(), ""
    try:
        profile, required = _preflight_visibility_required()
    except SystemExit as exc:
        proto_error = f"resolve_profile SystemExit: {exc}"
    except Exception as exc:
        proto_error = f"{type(exc).__name__}: {exc}"
    _record("profile_resolution",
            profile is not None
            and getattr(profile, "profile_id", None) == FROZEN_PROFILE,
            proto_error or FROZEN_PROFILE)
    _record("visibility_gate", frozenset(required) == OFFICIAL_ASTRO_REQUIRED,
            f"required={sorted(required)}")

    parse_failures = []
    for text, want in (("推理过程略。答案：B", "B"), ("分析略。最终答案：C", "C")):
        try:
            meta = _preflight_parse(text)
        except Exception as exc:
            parse_failures.append(f"exception:{exc}")
            continue
        if not meta.get("valid") or meta.get("choice") != want:
            parse_failures.append(f"{text!r}->{meta!r}")
    try:
        garbage = _preflight_parse("无法从文本确定任何选项")
        if garbage.get("valid"):
            parse_failures.append(f"garbage parsed: {garbage!r}")
    except Exception as exc:
        parse_failures.append(f"garbage exception: {exc}")
    _record("parser_synthetic", not parse_failures, "; ".join(parse_failures))

    # -- 环境净化负向核验（design §3.4/§4.4，复用 6.2 的 _build_child_env）--
    sentinel = {v: os.environ.get(v) for v in ENV_PURGE_VARS}
    leaked = []
    try:
        for v in ENV_PURGE_VARS:
            os.environ[v] = "1"
        child = _build_child_env()
        leaked = [v for v in ENV_PURGE_VARS if v in child]
    finally:
        for v, old in sentinel.items():
            if old is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = old
    _record("env_sanitize", not leaked, f"leaked={leaked}")

    # -- 预算与 {10→160} 状态机（design §4.5，复用 6.3 的 _advance_max_cases）--
    _record("budget_frozen",
            SCHEDULED_CALLS == 160 and HARD_CAP == 180 and SMOKE_SIZE == 10
            and MAX_CASES_LEGAL_TRANSITIONS == frozenset({(SMOKE_SIZE, MAIN_MAX_CASES)}),
            f"scheduled={SCHEDULED_CALLS} hard_cap={HARD_CAP} "
            f"smoke={SMOKE_SIZE} transitions={sorted(MAX_CASES_LEGAL_TRANSITIONS)}")

    sm_ok, sm_detail = True, ""
    ctx = {"smoke_size": SMOKE_SIZE, "max_cases": SMOKE_SIZE}
    try:
        _advance_max_cases(ctx, MAIN_MAX_CASES)
        if ctx.get("max_cases") != MAIN_MAX_CASES:
            sm_ok, sm_detail = False, "legal transition did not advance"
    except SystemExit as exc:
        sm_ok, sm_detail = False, f"legal 10->160 rejected (exit {exc.code})"
    if sm_ok:
        ctx2 = {"smoke_size": SMOKE_SIZE, "max_cases": SMOKE_SIZE}
        try:
            _advance_max_cases(ctx2, 20)
            sm_ok, sm_detail = False, "illegal 10->20 accepted"
        except SystemExit as exc:
            if exc.code != EXIT_CONTRACT:
                sm_ok, sm_detail = False, \
                    f"illegal transition exit {exc.code} != {EXIT_CONTRACT}"
    _record("max_cases_state_machine", sm_ok, sm_detail or "{10->160} only")

    verdict = "PASS" if all(c["passed"] for c in checks) else "BLOCKED"
    receipt = {
        "stage": "preflight",
        "verdict": verdict,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "work_dir": str(work_dir),
        "pinned_commit": _pinned_commit(),
        "phase7_code_fingerprint": _phase7_code_fingerprint(),
        "data_json": {"path": data_json_path, "sha256": data_sha,
                      "bytes": data_bytes},
        "fortune_api": {"path": fortune_json_path, "sha256": fortune_sha,
                        "bytes": fortune_bytes},
        "budget": {"scheduled_calls": SCHEDULED_CALLS, "hard_cap": HARD_CAP,
                   "smoke_size": SMOKE_SIZE},
        "env_flags": _env_flags(),
        "year_distribution": year_dist,
        "category_distribution": cat_dist,
        "checks": checks,
    }
    _atomic_write_json(receipt_path, receipt)
    if verdict != "PASS":
        failed = [c["name"] for c in checks if not c["passed"]]
        _blocked(f"preflight BLOCKED: failed checks {failed}; "
                 f"receipt: {receipt_path}")
    return EXIT_OK


def _validate_preflight_for_run(receipt_path=None, data_json_path=None,
                                fortune_json_path=None):
    """run 入口 fail-closed 准入门：三方一致（receipt ↔ 当前磁盘文件 ↔ 模块
    冻结常量）。任一不一致 -> 退出 4；在 run 目录创建与任何 runner/API 调用
    之前执行，无跳过开关。"""
    receipt_path = str(receipt_path or
                       os.path.join(_PROJECT_ROOT, PREFLIGHT_RECEIPT_PATH))
    data_json_path = str(data_json_path or
                         os.path.join(_PROJECT_ROOT, DATA_JSON_PATH))
    fortune_json_path = str(fortune_json_path or
                            os.path.join(_PROJECT_ROOT, FORTUNE_JSON_PATH))
    if not os.path.exists(receipt_path):
        _blocked(f"preflight receipt missing: {receipt_path}; "
                 "run 'preflight' first (fail-closed admission gate)")
    try:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _blocked(f"preflight receipt unreadable: {receipt_path}: {exc}")
    if receipt.get("verdict") != "PASS":
        _blocked(f"preflight receipt verdict={receipt.get('verdict')!r} "
                 f"!= 'PASS': {receipt_path}")
    frozen_commit = _pinned_commit()
    if receipt.get("pinned_commit") != frozen_commit:
        _blocked(f"preflight pinned_commit drift: "
                 f"receipt={receipt.get('pinned_commit')!r} "
                 f"!= frozen={frozen_commit!r}")
    data_sha = _sha256_file(data_json_path)
    receipt_data_sha = (receipt.get("data_json") or {}).get("sha256")
    if receipt_data_sha != FROZEN_DATA_JSON_SHA256 \
            or data_sha != FROZEN_DATA_JSON_SHA256:
        _blocked(f"data.json sha256 three-way drift: receipt={receipt_data_sha!r} "
                 f"frozen={FROZEN_DATA_JSON_SHA256!r} disk={data_sha!r}")
    fortune_sha = _sha256_file(fortune_json_path)
    receipt_fortune_sha = (receipt.get("fortune_api") or {}).get("sha256")
    if receipt_fortune_sha != FROZEN_FORTUNE_JSON_SHA256 \
            or fortune_sha != FROZEN_FORTUNE_JSON_SHA256:
        _blocked(f"fortune_api sha256 three-way drift: "
                 f"receipt={receipt_fortune_sha!r} "
                 f"frozen={FROZEN_FORTUNE_JSON_SHA256!r} disk={fortune_sha!r}")
    current_fp = _phase7_code_fingerprint()
    if receipt.get("phase7_code_fingerprint") != current_fp:
        _blocked(f"phase7 code fingerprint drift: "
                 f"receipt={receipt.get('phase7_code_fingerprint')!r} "
                 f"!= current={current_fp!r} (re-run preflight after code change)")
    budget = receipt.get("budget") or {}
    if budget.get("scheduled_calls") != SCHEDULED_CALLS \
            or budget.get("hard_cap") != HARD_CAP:
        _blocked(f"preflight budget drift: receipt={budget!r} != "
                 f"frozen scheduled={SCHEDULED_CALLS} hard_cap={HARD_CAP}")
    if receipt.get("env_flags") != _env_flags():
        _blocked(f"preflight env_flags drift: "
                 f"receipt={receipt.get('env_flags')!r} != frozen={_env_flags()!r}")
    return receipt


# -- CLI (frozen contract) --


def _build_orchestrator_parser():
    parser = argparse.ArgumentParser(description="Phase 7 MingLi-Bench baseline orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_pre = sub.add_parser(
        "preflight",
        help="zero-API: data integrity + protocol + env sanitizer + budget checks")
    p_pre.add_argument("--work-dir", default=".tmp/phase7")
    p_run = sub.add_parser(
        "run",
        help="production chain: normalize -> smoke(10) -> verdict -> resume(160) "
             "-> retest -> hard gates -> archive+receipt")
    p_run.add_argument("--run-id", required=True, help="safe experiment run identifier")
    p_run.add_argument("--resume", action="store_true",
                       help="explicitly resume an existing run")
    p_run.add_argument("--output-dir", default=".tmp/phase7/run")
    return parser


def main(argv=None):
    parser = _build_orchestrator_parser()
    args = parser.parse_args(argv)
    if args.cmd == "preflight":
        return run_preflight(args.work_dir) or EXIT_OK
    result = run_mingli_baseline(args.run_id, resume=args.resume,
                                 output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
