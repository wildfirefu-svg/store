#!/usr/bin/env python3
"""Phase 6 6B1 orchestrator — 紫微信号消融实验 (v9 protocol).

协议摘要（与 design §7 一致）：
  - 双年度: 2024 holdout + 2025 holdout, 各 40 题
  - 3 repeats × 3 arms = 9 cells/年 → 18 cells 总计
  - 每 cell 拆 3 切片(13+13+14) → 54 原子切片
  - Latin square 交错排列避免时序偏差
  - 全局硬上限 792 (720 额定 + 10% 重试余量)
  - Gate: Δ_dev = mean(acc_b1c - acc_b1a_prime) across years/repeats
    PROMOTE_CANDIDATE: Δ_dev ≥ +2pp 且 worst_year ≥ -2pp

用法:
  python scripts/phase6_6b1_orchestrator.py --provider deepseek --model deepseek-chat \
    --output-dir benchmark/outputs/phase6_6b1 --dry-run
  python scripts/phase6_6b1_orchestrator.py --provider deepseek --model deepseek-chat \
    --output-dir benchmark/outputs/phase6_6b1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

# Ensure project root on sys.path for benchmark.* imports (P0: real CLI entry)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---- constants ----

REASONED_PROFILE = "baziqa_xjz_reasoned"
CHART_SCHEMA = "legacy_v0"

YEAR_DATASETS = {
    "2024": "benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl",
    "2025": "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl",
}

# arm → ziwei_arm (design §6)
ARM_ZIWEI_MAP = {
    "b1a_prime": "none",
    "b1b": "only",
    "b1c": "combined",
}

ARMS = list(ARM_ZIWEI_MAP.keys())
YEARS = ["2024", "2025"]
REPEATS = [0, 1, 2]
QUESTIONS_PER_CELL = 40

# 每 cell 拆片: G0=13, G1=14, G2=13 (spec §8.1)
SLICE_LAYOUT = [13, 14, 13]

# Latin square: position → group → arm (spec §8.1)
LATIN_SQUARE = {
    0: {0: "b1a_prime", 1: "b1b", 2: "b1c"},
    1: {0: "b1c", 1: "b1a_prime", 2: "b1b"},
    2: {0: "b1b", 1: "b1c", 2: "b1a_prime"},
}

# Per-slice hard cap (spec §8.3): 13→14 (+1), 14→16 (+2)
HARD_CAP_MAP = {13: 14, 14: 16}

# Frozen experiment date (spec §8.4)
FROZEN_DATE = "2026-07-17"

# Env vars to strip from subprocess (spec §8.6)
ENV_CLEANUP = ["BAZI_RAG", "BAZI_RAG_CORPUS", "BAZI_FEWSHOT_FILE", "BAZI_APB_BLOCK"]

GLOBAL_HARD_CAP = 792         # 720 额定 + 10% 重试 (36×14 + 18×16)
RATED_CALLS = 720

# Gate thresholds
GATE_DELTA_DEV_PP = 2         # +2 percentage points
GATE_WORST_YEAR_PP = -2


# ---- helpers ----

def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def atomic_write_json(path: str, data) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Windows: os.replace may fail with PermissionError if another
        # process (e.g. antivirus) briefly holds the file; retry a few times
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---- schedule generation ----

def generate_schedule(output_dir: Path) -> dict:
    """Generate atomic 54-slice schedule with Latin square (spec §8.1).

    Latin square: each (year, repeat) has 3 positions; each position assigns
    groups to arms via the frozen LATIN_SQUARE matrix. No slice mixes
    different arms, years, or repeats.
    """
    os.makedirs(str(output_dir), exist_ok=True)

    slices = []
    # Interleave: cycle positions across all (year, repeat) cells
    # to avoid temporal bias (spec §8.1)
    for position in range(3):
        for year in YEARS:
            for repeat in REPEATS:
                for group in range(3):
                    arm = LATIN_SQUARE[position][group]
                    size = SLICE_LAYOUT[group]
                    ziwei_arm = ARM_ZIWEI_MAP[arm]
                    # slice_id format: {year}_{arm}_R{repeat}_P{position}_G{group}
                    slice_id = f"{year}_{arm}_R{repeat}_P{position}_G{group}"

                    case_start = sum(SLICE_LAYOUT[:group])
                    case_end = case_start + size

                    slice_dir = output_dir / f"slice_{slice_id}"
                    detail_name = f"details_{slice_id}.jsonl"
                    events_name = f"details_{slice_id}.events.jsonl"
                    manifest_name = f"details_{slice_id}.manifest.json"

                    slices.append({
                        "slice_id": slice_id,
                        "year": year,
                        "repeat": repeat,
                        "arm": arm,
                        "ziwei_arm": ziwei_arm,
                        "group": group,
                        "position": position,
                        "size": size,
                        "scheduled_calls": size,
                        "hard_cap": HARD_CAP_MAP[size],
                        "case_start": case_start,
                        "case_end": case_end,
                        "output_dir": str(slice_dir),
                        "detail_path": str(slice_dir / detail_name),
                        "events_path": str(slice_dir / events_name),
                        "manifest_path": str(slice_dir / manifest_name),
                        "dataset": YEAR_DATASETS[year],
                    })

    # Fill case_ids for each slice
    year_cases = {}
    for year in YEARS:
        year_cases[year] = load_jsonl(YEAR_DATASETS[year])

    for sl in slices:
        sl["case_ids"] = [
            c["case_id"]
            for c in year_cases[sl["year"]][sl["case_start"]:sl["case_end"]]
        ]
        sl["question_ids"] = [
            c.get("question", f"q_{c['case_id']}")
            for c in year_cases[sl["year"]][sl["case_start"]:sl["case_end"]]
        ]

    schedule = {
        "experiment": "phase6_6b1",
        "total_slices": len(slices),
        "total_scheduled_calls": sum(s["size"] for s in slices),
        "total_hard_cap": sum(s["hard_cap"] for s in slices),
        "global_hard_cap": GLOBAL_HARD_CAP,
        "frozen_date": FROZEN_DATE,
        "years": YEARS,
        "repeats": len(REPEATS),
        "arms": ARMS,
        "arm_ziwei_map": ARM_ZIWEI_MAP,
        "profile": REASONED_PROFILE,
        "chart_schema_version": CHART_SCHEMA,
        "latin_square": {str(k): v for k, v in LATIN_SQUARE.items()},
        "slice_layout": SLICE_LAYOUT,
        "hard_cap_map": HARD_CAP_MAP,
        "slices": slices,
    }

    schedule_path = output_dir / "schedule.json"
    atomic_write_json(str(schedule_path), schedule)
    print(f"[schedule] {len(slices)} slices, {schedule['total_scheduled_calls']} calls "
          f"(hard_cap total={schedule['total_hard_cap']}) → {schedule_path}")
    return schedule


# ---- BudgetLedger (fail-closed) ----

class BudgetLedger:
    """Global budget ledger with fail-closed corruption checks and 792 hard cap."""

    def __init__(self, ledger_path: str):
        self.path = ledger_path
        self._data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {"global_hard_cap": GLOBAL_HARD_CAP, "slices_completed": [],
                    "calls_attempted_by_slice": {}, "total_calls_attempted": 0}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            print(json.dumps({
                "status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path, "error": str(e),
                "reason": "账本 JSON 损坏，无法继续 — fail-closed",
            }, ensure_ascii=False))
            raise SystemExit(2)
        # Validate structure
        for field in ("global_hard_cap", "slices_completed", "calls_attempted_by_slice",
                      "total_calls_attempted"):
            if field not in data:
                print(json.dumps({
                    "status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path, "error": f"缺少字段 {field}",
                    "reason": "账本结构不完整 — fail-closed",
                }, ensure_ascii=False))
                raise SystemExit(2)
        # P1-3: validate values (not just field existence) - fail-closed
        if data["global_hard_cap"] != GLOBAL_HARD_CAP:
            print(json.dumps({
                "status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"global_hard_cap={data['global_hard_cap']} != {GLOBAL_HARD_CAP}",
                "reason": "账本硬上限被篡改 - fail-closed",
            }, ensure_ascii=False))
            raise SystemExit(2)
        per_slice = data["calls_attempted_by_slice"]
        if not isinstance(per_slice, dict):
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path, "error": "calls_attempted_by_slice 非 dict",
                "reason": "账本结构损坏 - fail-closed"}, ensure_ascii=False))
            raise SystemExit(2)
        for sid, cnt in per_slice.items():
            if not isinstance(cnt, int) or cnt < 0:
                print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path,
                    "error": f"slice {sid} 调用数 {cnt!r} 非非负整数",
                    "reason": "账本计数非法 - fail-closed"}, ensure_ascii=False))
                raise SystemExit(2)
        recomputed_total = sum(per_slice.values())
        if data["total_calls_attempted"] != recomputed_total:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"total={data['total_calls_attempted']} != sum(per_slice)={recomputed_total}",
                "reason": "账本 total 与明细不一致 - fail-closed"}, ensure_ascii=False))
            raise SystemExit(2)
        if data["total_calls_attempted"] > data["global_hard_cap"]:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"total={data['total_calls_attempted']} > hard_cap={data['global_hard_cap']}",
                "reason": "账本总额超限 - fail-closed"}, ensure_ascii=False))
            raise SystemExit(2)
        return data

    def _save(self) -> None:
        atomic_write_json(self.path, self._data)

    @property
    def total_attempted(self) -> int:
        return self._data["total_calls_attempted"]

    @property
    def hard_cap(self) -> int:
        return self._data["global_hard_cap"]

    def sliced_completed(self, slice_id: str) -> bool:
        return slice_id in self._data["slices_completed"]

    def record_slice_completed(self, slice_id: str, calls: int) -> None:
        """Atomically record slice completion with idempotent max."""
        prev = self._data["calls_attempted_by_slice"].get(slice_id, 0)
        recorded = max(prev, calls)
        self._data["calls_attempted_by_slice"][slice_id] = recorded

        if slice_id not in self._data["slices_completed"]:
            self._data["slices_completed"].append(slice_id)

        # Recompute total from per-slice (idempotent)
        self._data["total_calls_attempted"] = sum(
            self._data["calls_attempted_by_slice"].values()
        )
        self._save()

    def budget_ok(self, remaining_scheduled: int) -> bool:
        """Check: total_attempted + remaining_scheduled ≤ hard_cap."""
        return self.total_attempted + remaining_scheduled <= self.hard_cap

    def budget_ok_for_slice(self, slice_id: str, slice_hard_cap: int) -> bool:
        """Frozen formula (spec §8.7):
        total_attempted + (slice_hard_cap - already_attempted_for_slice) ≤ 792
        """
        already = self._data["calls_attempted_by_slice"].get(slice_id, 0)
        remaining_for_slice = max(0, slice_hard_cap - already)
        return self.total_attempted + remaining_for_slice <= self.hard_cap

    def record_calls_only(self, slice_id: str, calls: int) -> None:
        """Record calls consumed WITHOUT marking slice as completed.
        Used for failed smoke / crashed slices where calls were made
        but the slice is not done."""
        prev = self._data["calls_attempted_by_slice"].get(slice_id, 0)
        recorded = max(prev, calls)
        self._data["calls_attempted_by_slice"][slice_id] = recorded
        self._data["total_calls_attempted"] = sum(
            self._data["calls_attempted_by_slice"].values()
        )
        self._save()

    def remaining_budget(self) -> int:
        return self.hard_cap - self.total_attempted

    def validate_against_schedule(self, schedule: dict,
                                  provider: str, model: str) -> None:
        """P1-3 + P0-B: validate ALL ledger slice IDs belong to schedule.
        Fail-closed SystemExit(2) on any violation."""
        schedule_ids = {sl["slice_id"] for sl in schedule["slices"]}
        # P0-B: validate calls_attempted_by_slice keys (not just slices_completed)
        calls_keys = set(self._data["calls_attempted_by_slice"].keys())
        unknown_call_keys = calls_keys - schedule_ids
        if unknown_call_keys:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"calls_attempted_by_slice 含未知 slice ID: "
                         f"{sorted(unknown_call_keys)[:5]}",
                "reason": "账本调用明细含虚假 slice ID - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)
        # P0-B: slices_completed must be subset of calls_attempted_by_slice
        completed_set = set(self._data["slices_completed"])
        calls_set = set(self._data["calls_attempted_by_slice"].keys())
        orphan_completed = completed_set - calls_set
        if orphan_completed:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"slices_completed 含无调用记录的 ID: "
                         f"{sorted(orphan_completed)[:5]}",
                "reason": "completed slice 无对应调用明细 - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)
        # P0-B: slices_completed must all belong to schedule (redundant but explicit)
        unknown_completed = completed_set - schedule_ids
        if unknown_completed:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"slices_completed 含未知 slice ID: "
                         f"{sorted(unknown_completed)[:5]}",
                "reason": "账本含虚假 completed slice ID - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)
        for sl in schedule["slices"]:
            if not self.sliced_completed(sl["slice_id"]):
                continue
            ok, diff = verify_slice_manifest(sl, provider, model)
            if not ok:
                print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path,
                    "slice_id": sl["slice_id"], "diff": diff,
                    "reason": "completed slice manifest 与当前配置不一致"},
                    ensure_ascii=False))
                raise SystemExit(2)
            ev_ok, ev_count, ev_reason = _validate_events(
                sl["events_path"], sl["size"], sl["hard_cap"])
            if not ev_ok:
                print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path,
                    "slice_id": sl["slice_id"], "reason": ev_reason,
                    "reason_detail": "completed slice events 损坏/缺失"},
                    ensure_ascii=False))
                raise SystemExit(2)
            # P1-C: reconcile ledger call count with events evidence (downward fix)
            ledger_calls = self._data["calls_attempted_by_slice"].get(sl["slice_id"], 0)
            if ledger_calls != ev_count:
                self._data["calls_attempted_by_slice"][sl["slice_id"]] = ev_count
                self._data["total_calls_attempted"] = sum(
                    self._data["calls_attempted_by_slice"].values())
                self._save()
                print(f"      [reconcile] {sl['slice_id']}: "
                      f"ledger {ledger_calls} -> {ev_count}")


# ---- integrity check ----

def build_expected_key(dataset_id: str, profile_id: str, arm: str,
                       case_id: str, repeat_idx: int,
                       provider: str, model: str) -> tuple:
    """Build expected attempt key matching runner's 10-tuple format."""
    # ATTEMPT_KEY_FIELDS = (dataset_id, profile_id, arm, attempt_stage,
    #                       provider, model, case_id, repeat_idx, sample_idx,
    #                       permutation_id)
    return (dataset_id, profile_id, arm, "main", provider, model,
            str(case_id), int(repeat_idx), 0, "p0")


def integrity_check(schedule: dict, ledger: BudgetLedger,
                    provider: str, model: str) -> dict:
    """Check integrity: expected keys vs actual detail records.

    Returns {status, expected_count, actual_count, duplicates, missing, extra}.
    Does NOT call sys.exit on failure — caller decides.
    """
    expected_keys = set()
    for sl in schedule["slices"]:
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        for case_id in sl["case_ids"]:
            key = build_expected_key(
                dataset_id, REASONED_PROFILE, sl["arm"],
                case_id, sl["repeat"], provider, model,
            )
            expected_keys.add(key)

    # Collect actual keys (list, not set — need to detect dupes)
    actual_keys = []
    detail_errors = []
    for sl in schedule["slices"]:
        if not ledger.sliced_completed(sl["slice_id"]):
            continue
        detail_path = sl["detail_path"]
        if not os.path.exists(detail_path):
            detail_errors.append(f"slice {sl['slice_id']}: detail missing at {detail_path}")
            continue
        try:
            with open(detail_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        detail_errors.append(
                            f"slice {sl['slice_id']}: malformed JSON line in detail"
                        )
                        continue
                    key = row.get("attempt_key")
                    if key:
                        actual_keys.append(tuple(key))
        except OSError as e:
            detail_errors.append(
                f"slice {sl['slice_id']}: cannot read detail: {e}"
            )

    actual_set = set(actual_keys)
    duplicates = len(actual_keys) - len(actual_set)
    missing = len(expected_keys - actual_set)
    extra = len(actual_set - expected_keys)

    result = {
        "expected_count": len(expected_keys),
        "actual_count": len(actual_keys),
        "unique_actual": len(actual_set),
        "duplicates": duplicates,
        "missing": missing,
        "extra": extra,
        "detail_errors": detail_errors,
        "pass": (missing == 0 and extra == 0 and duplicates == 0
                 and len(detail_errors) == 0
                 and len(actual_keys) == len(expected_keys)),
    }
    return result


# ---- gate computation ----

def compute_gate(schedule: dict, ledger: BudgetLedger) -> dict:
    """Compute Δ gate from completed detail files.

    Gate formula (v9 §8):
      Δ(year, repeat) = acc_b1c - acc_b1a_prime
      Δ_year = mean(Δ over 3 repeats)
      Δ_dev = mean(Δ_2024, Δ_2025)
      worst_year = min(Δ_2024, Δ_2025)

      PROMOTE_CANDIDATE: Δ_dev ≥ +2pp AND worst_year ≥ -2pp
      ROLLBACK_CANDIDATE: Δ_dev ≤ -5pp
    """
    ALL_YEARS = ["2024", "2025"]
    ALL_REPEATS = [0, 1, 2]
    GATE_ARMS = ("b1a_prime", "b1c")            # only these two in Δ
    CONTEXT_ARM = "b1b"                         # reported but excluded from gate

    # cells[(year, repeat, arm)] = (correct, total)
    cells: dict[tuple, tuple[int, int]] = {}

    for sl in schedule["slices"]:
        sl_id = sl["slice_id"]
        if not ledger.sliced_completed(sl_id):
            continue
        year, repeat, arm = sl["year"], sl["repeat"], sl["arm"]
        detail_path = sl["detail_path"]
        if not os.path.exists(detail_path):
            continue

        correct = 0
        total = 0
        with open(detail_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                total += 1
                if row.get("correct") is True:
                    correct += 1

        key = (year, repeat, arm)
        prev_c, prev_t = cells.get(key, (0, 0))
        cells[key] = (prev_c + correct, prev_t + total)

    # Build cell accuracies. Denominator is always 40 (frozen).
    cell_acc = {}
    for year in ALL_YEARS:
        for repeat in ALL_REPEATS:
            for arm in ARMS:
                c, _t = cells.get((year, repeat, arm), (0, 0))
                # Frozen denominator: 40 per cell.
                # Partially-completed cells use current correct / 40.
                cell_acc[(year, repeat, arm)] = c / QUESTIONS_PER_CELL

    # Δ per (year, repeat)
    deltas: list[dict] = []
    for year in ALL_YEARS:
        for repeat in ALL_REPEATS:
            delta = cell_acc[(year, repeat, "b1c")] - cell_acc[(year, repeat, "b1a_prime")]
            deltas.append({
                "year": year, "repeat": repeat,
                "delta": round(delta, 4),
                "acc_b1a_prime": round(cell_acc[(year, repeat, "b1a_prime")], 4),
                "acc_b1b": round(cell_acc[(year, repeat, "b1b")], 4),
                "acc_b1c": round(cell_acc[(year, repeat, "b1c")], 4),
            })

    # Per-year means
    year_means = {}
    for year in ALL_YEARS:
        yds = [d["delta"] for d in deltas if d["year"] == year]
        year_means[year] = sum(yds) / len(yds) if yds else 0.0

    delta_dev = (year_means["2024"] + year_means["2025"]) / 2
    worst_year = min(year_means["2024"], year_means["2025"])

    # Verdict (spec §11: binary — PROMOTE or ROLLBACK, no INCONCLUSIVE)
    if delta_dev >= GATE_DELTA_DEV_PP / 100 and worst_year >= GATE_WORST_YEAR_PP / 100:
        verdict = "PROMOTE_CANDIDATE"
    else:
        verdict = "ROLLBACK"

    # Checks: were all cells completed?
    all_completed = all(
        cells.get((y, r, a), (0, 0))[1] == QUESTIONS_PER_CELL
        for y in ALL_YEARS for r in ALL_REPEATS for a in ARMS
    )

    return {
        "verdict": verdict,
        "delta_dev": round(delta_dev, 4),
        "worst_year": round(worst_year, 4),
        "year_means": {k: round(v, 4) for k, v in year_means.items()},
        "per_cell_deltas": deltas,
        "cell_accuracies": {
            f"{y}/r{r}/{a}": round(cell_acc[(y, r, a)], 4)
            for y in ALL_YEARS for r in ALL_REPEATS for a in ARMS
        },
        "all_cells_completed": all_completed,
        "total_calls_attempted": ledger.total_attempted,
        "budget_remaining": ledger.remaining_budget(),
    }


# ---- runner invocation ----

def _write_case_ids_file(sl: dict) -> str:
    """Write case_ids JSON for a single slice, return path."""
    slice_dir = Path(sl["output_dir"])
    os.makedirs(str(slice_dir), exist_ok=True)
    case_ids_path = str(slice_dir / f"case_ids_{sl['slice_id']}.json")
    atomic_write_json(case_ids_path, sl["case_ids"])
    return case_ids_path


def _ensure_slice_output_dir(sl: dict) -> str:
    d = str(Path(sl["output_dir"]))
    os.makedirs(d, exist_ok=True)
    return d


_CRASH_STATE_ENUM = {"running", "crashed", "deterministic_error"}


def _crash_audit_prefix(sl: dict) -> str:
    """P1-4: v9 §12 contract uses dot-notation files: crash_retry.{returncode,stdout.log,stderr.log}."""
    return os.path.join(sl["output_dir"], "crash_retry")


def _crash_state_path(sl: dict) -> str:
    """P1-5: per-slice crash state file path (control file)."""
    return os.path.join(sl["output_dir"], f"{sl['slice_id']}.crash_state.json")


def _read_crash_state(sl: dict) -> dict | None:
    """P1-5 + P0-A + P1-3: read crash state, fail-closed on corrupt/invalid.
    Schema: state ∈ enum, returncode ∈ {None, int}, retried ∈ bool, combos valid."""
    path = _crash_state_path(sl)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("crash state is not a dict")
        # P1-3: validate frozen schema
        state = data.get("state")
        if state not in _CRASH_STATE_ENUM:
            raise ValueError(f"state {state!r} not in {_CRASH_STATE_ENUM}")
        rc = data.get("returncode")
        if rc is not None and not isinstance(rc, int):
            raise ValueError(f"returncode {rc!r} must be null or int")
        retried = data.get("retried")
        if not isinstance(retried, bool):
            raise ValueError(f"retried {retried!r} must be bool")
        # P1-3: validate state/returncode combos
        if state == "running" and rc is not None:
            raise ValueError("state=running requires returncode=null")
        if state == "crashed" and (rc is None or rc in (2, 3)):
            raise ValueError("state=crashed requires returncode∉{null,2,3}")
        if state == "deterministic_error" and rc not in (2, 3):
            raise ValueError("state=deterministic_error requires returncode∈{2,3}")
        return data
    except (json.JSONDecodeError, ValueError, OSError) as e:
        print(json.dumps({"status": "CRASH_STATE_CORRUPT",
            "slice_id": sl["slice_id"], "path": path, "error": str(e),
            "reason": "crash 恢复控制文件损坏或 schema 非法 - fail-closed"},
            ensure_ascii=False))
        raise SystemExit(2)


def _write_crash_state(sl: dict, state: dict) -> None:
    """P1-5: persist crash state atomically."""
    atomic_write_json(_crash_state_path(sl), state)


def _clear_crash_state(sl: dict) -> None:
    """P1-5: remove crash state on clean completion."""
    path = _crash_state_path(sl)
    if os.path.exists(path):
        os.remove(path)


def _write_crash_audit(sl: dict, returncode: int, stdout: str,
                       stderr: str, retried: bool) -> None:
    """P1-4 + P1-5: write v9 §12 crash audit artifacts (dot-notation files).
    P1-5: distinguish initial vs retry to prevent evidence overwrite.
    initial: crash_retry.{returncode,stdout.log,stderr.log}
    retry:   crash_retry.retry.{returncode,stdout.log,stderr.log}"""
    prefix = _crash_audit_prefix(sl)
    os.makedirs(sl["output_dir"], exist_ok=True)
    # P1-5: retry attempts write to separate files, preserving initial evidence
    suffix = ".retry" if retried else ""
    with open(f"{prefix}{suffix}.returncode", "w", encoding="utf-8") as f:
        f.write(str(returncode))
    with open(f"{prefix}{suffix}.stdout.log", "w", encoding="utf-8") as f:
        f.write(stdout)
    with open(f"{prefix}{suffix}.stderr.log", "w", encoding="utf-8") as f:
        f.write(stderr)
    _write_crash_state(sl, {
        "state": "crashed" if returncode not in (2, 3) else "deterministic_error",
        "returncode": returncode, "retried": retried,
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
    })


def _validate_partial_events(events_path: str, hard_cap: int) -> tuple[bool, int, str]:
    """P0-1: crash recovery uses partial-event rules (not completed-slice lower bound).
    P0-1 fix: only count kind==call_attempt rows; all rows must still parse."""
    if not os.path.exists(events_path):
        return False, 0, "events file missing"
    count = 0
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)               # raise on corrupt (all rows)
                if row.get("kind") == "call_attempt":
                    count += 1
    except (json.JSONDecodeError, OSError) as e:
        return False, count, f"corrupt JSON: {e}"
    if count == 0:
        return False, 0, "no call_attempt events (empty)"
    if count > hard_cap:
        return False, count, f"count {count} > hard_cap {hard_cap}"
    return True, count, "ok"


def _validate_crash_recovery_artifacts(sl: dict, provider: str, model: str) -> None:
    """P0-2: before crash retry, verify manifest/events/partial-detail are valid.
    P0-1: uses partial-event rules (0 < count <= hard_cap), NOT completed lower bound.
    Only allow one recovery when audit artifacts exist and are consistent."""
    # manifest must exist and fully match current config
    ok, diff = verify_slice_manifest(sl, provider, model)
    if not ok:
        print(json.dumps({"status": "CRASH_RECOVERY_ARTIFACT_INVALID",
            "slice_id": sl["slice_id"], "reason": "manifest 缺失或漂移",
            "diff": diff}, ensure_ascii=False))
        raise SystemExit(2)
    # P0-1: partial events - parseable + 0 < count <= hard_cap (not >= scheduled)
    ev_ok, ev_count, ev_reason = _validate_partial_events(
        sl["events_path"], sl["hard_cap"])
    if not ev_ok:
        print(json.dumps({"status": "CRASH_RECOVERY_ARTIFACT_INVALID",
            "slice_id": sl["slice_id"], "reason": f"events: {ev_reason}",
            "calls_found": ev_count}, ensure_ascii=False))
        raise SystemExit(2)
    # partial detail keys must have no duplicates/extras vs expected
    if os.path.exists(sl["detail_path"]):
        rows = load_jsonl(sl["detail_path"])
        detail_keys = [tuple(r.get("attempt_key", [])) for r in rows]
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        expected_keys = set()
        for case_id in sl["case_ids"]:
            expected_keys.add(build_expected_key(
                dataset_id, REASONED_PROFILE, sl["arm"],
                case_id, sl["repeat"], provider, model))
        if len(set(detail_keys)) != len(detail_keys):
            print(json.dumps({"status": "CRASH_RECOVERY_ARTIFACT_INVALID",
                "slice_id": sl["slice_id"],
                "reason": "partial detail 含重复 attempt key"}, ensure_ascii=False))
            raise SystemExit(2)
        extra = set(detail_keys) - expected_keys
        if extra:
            print(json.dumps({"status": "CRASH_RECOVERY_ARTIFACT_INVALID",
                "slice_id": sl["slice_id"],
                "reason": "partial detail 含 extra keys",
                "extra_sample": list(extra)[:3]}, ensure_ascii=False))
            raise SystemExit(2)
        # P0-1: terminal detail rows must not exceed events call_attempt count
        terminal_rows = sum(1 for r in rows if r.get("terminal_state"))
        if terminal_rows > ev_count:
            print(json.dumps({"status": "CRASH_RECOVERY_ARTIFACT_INVALID",
                "slice_id": sl["slice_id"],
                "reason": f"terminal rows {terminal_rows} > events {ev_count}",
                "reason_detail": "detail 终态行数超过 events 调用数"}, ensure_ascii=False))
            raise SystemExit(2)


def run_slice(sl: dict, provider: str, model: str, dry_run: bool) -> int:
    """Run a single slice. Returns subprocess exit code (0=ok, 2=blocked, 3=hardcap).
    P1-5: crash/resume protocol - persist return code, forbid recovery from
    deterministic errors (rc 2/3), allow only one recovery from crash."""
    _ensure_slice_output_dir(sl)
    case_ids_file = _write_case_ids_file(sl)

    # Per-slice hard cap from frozen map (spec §8.3)
    hard_cap = sl["hard_cap"]

    # P1-5: crash/resume protocol - check previous crash state before running
    crash_state = _read_crash_state(sl)
    if crash_state is not None:
        prev_rc = crash_state.get("returncode")
        retried = crash_state.get("retried", False)
        prev_state = crash_state.get("state", "")
        # Deterministic errors (rc 2/3) forbid recovery
        if prev_rc in (2, 3):
            print(json.dumps({"status": "CRASH_RECOVERY_FORBIDDEN",
                "slice_id": sl["slice_id"], "prev_returncode": prev_rc,
                "reason": f"上次返回码 {prev_rc} 为确定性错误，禁止恢复"},
                ensure_ascii=False))
            raise SystemExit(2)
        # Only one recovery allowed
        if retried:
            print(json.dumps({"status": "CRASH_RECOVERY_EXHAUSTED",
                "slice_id": sl["slice_id"],
                "prev_state": prev_state, "prev_returncode": prev_rc,
                "reason": "已用完一次崩溃恢复，禁止再次恢复"},
                ensure_ascii=False))
            raise SystemExit(2)
        # P0-2: crash retry requires valid audit artifacts (manifest/events/detail)
        _validate_crash_recovery_artifacts(sl, provider, model)

    cmd = [
        sys.executable, "-u",
        os.path.join("benchmark", "runners", "run_benchmark.py"),
        "--dataset", sl["dataset"],
        "--profile", REASONED_PROFILE,
        "--chart-schema-version", CHART_SCHEMA,
        "--arm", sl["arm"],
        "--ziwei-arm", sl["ziwei_arm"],
        "--attempt-stage", "main",
        "--repeat-idx", str(sl["repeat"]),
        "--case-details-jsonl", sl["detail_path"],
        "--case-ids-file", case_ids_file,
        "--provider", provider,
        "--model", model,
        "--method", "direct_choice",
        "--model-runner",
        "--n-samples", "1",
        "--temperature", "0",
        "--scheduled-calls", str(sl["size"]),
        "--hard-cap", str(hard_cap),
        "--output-dir", sl["output_dir"],
        "--as-of-date", FROZEN_DATE,
    ]

    print(f"\n[run] {sl['slice_id']} ({sl['size']} calls, cap={hard_cap}) "
          f"year={sl['year']} r={sl['repeat']} arm={sl['arm']} ziwei={sl['ziwei_arm']}")

    if dry_run:
        print(f"      [dry-run] skip")
        return 0

    # Check ARTIFACT_EXISTS: if detail exists, add --resume
    if os.path.exists(sl["detail_path"]) or os.path.exists(sl["manifest_path"]):
        cmd.append("--resume")
        print(f"      [resume] existing artifacts found, resuming")

    # P1-5: mark slice as running BEFORE subprocess (system crash detection)
    is_retry = crash_state is not None
    _write_crash_state(sl, {
        "state": "running", "returncode": None,
        "retried": is_retry, "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
    })

    # Clean env (spec §8.6)
    clean_env = dict(os.environ)
    for var in ENV_CLEANUP:
        clean_env.pop(var, None)

    result = subprocess.run(cmd, capture_output=True, text=True, env=clean_env)

    # P1-5: persist crash state based on return code
    if result.returncode == 0:
        _clear_crash_state(sl)                       # clean completion
    else:
        # P1-D: write v9 contract crash audit artifacts
        _write_crash_audit(sl, result.returncode,
                           result.stdout or "", result.stderr or "", is_retry)

    return result.returncode


# ---- P1-5: formal archive generation (v9 §12) ----

def _compute_context_fingerprint(schedule: dict, provider: str, model: str) -> dict:
    """P1-4: compute SHA-256 of rendered context for 3 cases × 3 arms = 9 fingerprints.
    Records both case_id -> sha256 per arm, and the 3 selected case IDs."""
    from benchmark.formatters.chart_context import render_reasoned_context
    from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt
    arms_seen = {}
    case_ids_used = []
    # Load cases once from first slice's dataset (all arms share same case set)
    first_sl = schedule["slices"][0]
    cases = load_jsonl(first_sl["dataset"])
    # P1-4: use first 3 cases × 3 arms
    selected_cases = cases[:3]
    for case in selected_cases:
        case_ids_used.append(case.get("case_id", "unknown"))
    fingerprints = {}
    for sl in schedule["slices"]:
        arm = sl["arm"]
        if arm in arms_seen:
            continue
        arms_seen[arm] = True
        for i, case in enumerate(selected_cases):
            ctx = render_reasoned_context(case, CHART_SCHEMA, sl["ziwei_arm"])
            prompt = _assemble_reasoned_choice_prompt(case, ctx)
            key = f"{case.get('case_id', f'case{i}')}_{arm}"
            fingerprints[key] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return {
        "case_ids": case_ids_used,
        "arms": list(arms_seen.keys()),
        "fingerprints": fingerprints,                   # 3 cases × 3 arms = 9 entries
        "total": len(fingerprints),
    }


def _compute_dataset_hashes() -> dict:
    """P1-5: SHA-256 of each enriched dataset."""
    hashes = {}
    for year, path in YEAR_DATASETS.items():
        if os.path.exists(path):
            with open(path, "rb") as f:
                hashes[year] = hashlib.sha256(f.read()).hexdigest()
    return hashes


def _merge_artifacts(schedule: dict, archive_dir: Path,
                     provider: str, model: str) -> dict:
    """P1-5: merge all slice details + events into merged_details/events.jsonl.
    P1-5 gate: refuse missing files, enforce expected row counts.
    P0-1: verify each slice manifest with verify_slice_manifest (full fields).
    P2: provider/model are mandatory - empty string is rejected."""
    if not provider or not model:
        raise ValueError("provider and model are mandatory for _merge_artifacts")
    merged_details = archive_dir / "merged_details.jsonl"
    merged_events = archive_dir / "merged_events.jsonl"
    detail_count = 0
    event_count = 0
    expected_details = schedule["total_scheduled_calls"]
    expected_slices = schedule["total_slices"]
    # P1-5: pre-flight - all slices must have detail + events files
    missing = []
    for sl in schedule["slices"]:
        if not os.path.exists(sl["detail_path"]):
            missing.append(f"{sl['slice_id']}/details.jsonl")
        if not os.path.exists(sl["events_path"]):
            missing.append(f"{sl['slice_id']}/details.events.jsonl")
        if not os.path.exists(sl["manifest_path"]):
            missing.append(f"{sl['slice_id']}/details.manifest.json")
    if missing:
        print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
            "reason": f"{len(missing)} 个必需文件缺失，禁止合并",
            "missing_sample": missing[:5]}, ensure_ascii=False))
        raise SystemExit(2)
    # P1-4: per-slice validation before merge (not just global count)
    per_slice_report = []
    for sl in schedule["slices"]:
        # P0-1: verify manifest with full field check (mandatory, not optional)
        ok, diff = verify_slice_manifest(sl, provider, model)
        if not ok:
            print(json.dumps({"status": "ARCHIVE_MANIFEST_DRIFT",
                "slice_id": sl["slice_id"], "diff": diff,
                "reason": "归档前 manifest 完整字段校验失败"},
                ensure_ascii=False))
            raise SystemExit(2)
        rows = load_jsonl(sl["detail_path"])
        # detail row count must equal scheduled size
        if len(rows) != sl["size"]:
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "slice_id": sl["slice_id"],
                "reason": f"detail rows {len(rows)} != scheduled {sl['size']}"},
                ensure_ascii=False))
            raise SystemExit(2)
        # attempt keys must match expected (no dup/extra/missing)
        # P1: use passed-in provider/model (not hardcoded deepseek/deepseek-chat)
        detail_keys = [tuple(r.get("attempt_key", [])) for r in rows]
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        expected_keys = set()
        for case_id in sl["case_ids"]:
            expected_keys.add(build_expected_key(
                dataset_id, REASONED_PROFILE, sl["arm"],
                case_id, sl["repeat"], provider, model))
        if len(set(detail_keys)) != len(detail_keys):
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "slice_id": sl["slice_id"], "reason": "duplicate attempt keys"},
                ensure_ascii=False))
            raise SystemExit(2)
        extra = set(detail_keys) - expected_keys
        if extra:
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "slice_id": sl["slice_id"], "reason": "extra attempt keys",
                "extra_sample": list(extra)[:3]}, ensure_ascii=False))
            raise SystemExit(2)
        # events: call_attempt count in [size, hard_cap]
        ev_rows = load_jsonl(sl["events_path"])
        call_count = sum(1 for r in ev_rows if r.get("kind") == "call_attempt")
        if call_count < sl["size"] or call_count > sl["hard_cap"]:
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "slice_id": sl["slice_id"],
                "reason": f"call_attempt {call_count} not in [{sl['size']}, {sl['hard_cap']}]"},
                ensure_ascii=False))
            raise SystemExit(2)
        per_slice_report.append({"slice_id": sl["slice_id"],
                                  "detail_rows": len(rows),
                                  "call_attempts": call_count})
    with open(merged_details, "w", encoding="utf-8") as df, \
         open(merged_events, "w", encoding="utf-8") as ef:
        for sl in schedule["slices"]:
            for src in (sl["detail_path"], sl["events_path"]):
                with open(src, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if src == sl["detail_path"]:
                            df.write(line + "\n")
                            detail_count += 1
                        else:
                            ef.write(line + "\n")
                            event_count += 1
    # P1-5: enforce expected detail row count (redundant with per-slice, but explicit)
    if detail_count != expected_details:
        print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
            "reason": f"merged detail rows {detail_count} != expected {expected_details}",
            "expected_slices": expected_slices}, ensure_ascii=False))
        raise SystemExit(2)
    return {"detail_rows": detail_count, "event_rows": event_count,
            "expected_detail_rows": expected_details,
            "expected_slices": expected_slices,
            "per_slice": per_slice_report}


# P1-3: experiment-scope sources covered by the code fingerprint.
# Module-level so tests can substitute a scope list; anchored at the repo
# root and fail-closed below (aligned with the 6b2 hardening).
_FINGERPRINT_SCOPE_FILES = [
    "scripts/phase6_6b1_orchestrator.py",
    "benchmark/runners/run_benchmark.py",
    "benchmark/formatters/chart_context.py",
    "benchmark/formatters/baziqa_prompt.py",
    "benchmark/runners/profiles.py",
]


def _compute_experiment_code_fingerprint() -> str:
    """P1-3: hash all experiment-scope source files (not just orchestrator).
    Includes runner, formatters, prompt builder, profiles - any change to
    experiment-affecting code produces a different run_id.

    Fail-closed (aligned with 6b2): a missing scope file aborts instead of
    being silently excluded, and paths are anchored at the repo root so the
    fingerprint never depends on the caller's cwd.
    """
    h = hashlib.sha256()
    for rel in _FINGERPRINT_SCOPE_FILES:
        path = os.path.join(_PROJECT_ROOT, rel)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"experiment code fingerprint: scope file missing: {rel}")
        with open(path, "rb") as f:
            h.update(f.read())
        h.update(b"\x00")                          # separator
    return h.hexdigest()[:8]


def _copy_slice_artifacts(sl: dict, dest_dir: Path) -> dict:
    """P0-2: copy per-slice evidence (details/manifest/events/crash_retry.*) to archive.
    Returns file hashes for audit_index."""
    import shutil
    hashes = {}
    src_map = {
        "details.jsonl": sl["detail_path"],
        "details.manifest.json": sl["manifest_path"],
        "details.events.jsonl": sl["events_path"],
    }
    for name, src in src_map.items():
        if os.path.exists(src):
            dst = dest_dir / name
            shutil.copy2(src, str(dst))
            with open(dst, "rb") as f:
                hashes[name] = hashlib.sha256(f.read()).hexdigest()
    # P0-2: copy crash_retry.* artifacts if exist
    prefix = _crash_audit_prefix(sl)
    for suffix in (".returncode", ".stdout.log", ".stderr.log",
                   ".retry.returncode", ".retry.stdout.log", ".retry.stderr.log"):
        src = f"{prefix}{suffix}"
        if os.path.exists(src):
            dst_name = f"crash_retry{suffix}"
            dst = dest_dir / dst_name
            shutil.copy2(src, str(dst))
            with open(dst, "rb") as f:
                hashes[dst_name] = hashlib.sha256(f.read()).hexdigest()
    return hashes


def generate_archive(schedule: dict, gate: dict, integrity: dict,
                     ledger: BudgetLedger, output_dir: Path,
                     provider: str, model: str,
                     archive_root: Path | None = None) -> str:
    """P1-5 + P0-2 + P0-3: generate v9 §12 formal archive.
    P0-3: unique run_id (date + provider + model + short code hash), refuse overwrite.
    P0-2: copy smoke/ + slices/<id>/ per-slice evidence with file hashes.
    P1-5: atomic publish via temp dir (all-or-nothing).
    P1-6: budget saved as .json (not .jsonl).
    P1: archive_root for test isolation (default: docs/phase6/6b1)."""
    import shutil
    import tempfile
    # P1: archive_root isolation (default to real docs path)
    if archive_root is None:
        archive_root = Path("docs/phase6/6b1")
    archive_root = Path(archive_root)
    # P1-3: unique run_id with provider/model/EXPERIMENT-SCOPE code fingerprint
    # (not just orchestrator - includes runner, formatter, prompt, profile)
    code_hash = _compute_experiment_code_fingerprint()
    run_id = f"6b1-{FROZEN_DATE}-{provider}-{model}-{code_hash}"
    archive_dir = archive_root / run_id
    # P0-3: refuse to overwrite existing archive
    if archive_dir.exists():
        print(json.dumps({"status": "ARCHIVE_ALREADY_EXISTS",
            "archive_dir": str(archive_dir),
            "reason": "归档目录已存在，拒绝覆盖 - 请删除后重试或使用新 run_id"},
            ensure_ascii=False))
        raise SystemExit(2)
    # P1-5: build in temp dir, atomic rename on success
    parent = archive_root
    parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}_", dir=str(parent)))
    try:
        # P0-2: copy smoke/ evidence
        smoke_sl = schedule["slices"][0]
        smoke_dir = tmp_dir / "smoke"
        smoke_dir.mkdir(exist_ok=True)
        smoke_hashes = _copy_slice_artifacts(smoke_sl, smoke_dir)

        # P0-2: copy slices/<id>/ evidence
        slices_dir = tmp_dir / "slices"
        slices_dir.mkdir(exist_ok=True)
        slice_hashes = {}
        for sl in schedule["slices"][1:]:               # skip smoke (index 0)
            sl_dir = slices_dir / sl["slice_id"]
            sl_dir.mkdir(exist_ok=True)
            slice_hashes[sl["slice_id"]] = _copy_slice_artifacts(sl, sl_dir)

        # merged artifacts (P1-5: integrity gate inside)
        merge_counts = _merge_artifacts(schedule, tmp_dir, provider, model)

        # audit_index.json
        audit_index = {
            "run_id": run_id,
            "frozen_date": FROZEN_DATE,
            "provider": provider,
            "model": model,
            "code_fingerprint": code_hash,
            "dataset_hashes": _compute_dataset_hashes(),
            "context_fingerprints": _compute_context_fingerprint(schedule, provider, model),
            "schedule_total_slices": schedule["total_slices"],
            "schedule_total_scheduled_calls": schedule["total_scheduled_calls"],
            "schedule_total_hard_cap": schedule["total_hard_cap"],
            "latin_square": {str(k): v for k, v in LATIN_SQUARE.items()},
            "slice_layout": SLICE_LAYOUT,
            "budget_total_calls": ledger.total_attempted,
            "budget_hard_cap": ledger.hard_cap,
            "merge_counts": merge_counts,
            "integrity": {k: v for k, v in integrity.items() if k != "detail_errors"},
            "gate_verdict": gate["verdict"],
            "gate_delta_dev": gate["delta_dev"],
            "gate_worst_year": gate["worst_year"],
            "smoke_artifact_hashes": smoke_hashes,
            "slice_artifact_hashes": slice_hashes,
            "generated_at": time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        atomic_write_json(str(tmp_dir / "audit_index.json"), audit_index)

        # copy schedule + budget ledger (P1-6: .json not .jsonl)
        # P1-5: budget ledger is mandatory - fail-closed if missing
        shutil.copy2(str(output_dir / "schedule.json"), str(tmp_dir / "schedule.json"))
        ledger_src = output_dir / "budget_ledger.json"
        if not ledger_src.exists():
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "reason": "budget_ledger.json 缺失 - 预算账本为正式审计必需产物",
                "path": str(ledger_src)}, ensure_ascii=False))
            raise SystemExit(2)
        budget_dir = tmp_dir / "budget"
        budget_dir.mkdir(exist_ok=True)
        shutil.copy2(str(ledger_src), str(budget_dir / f"{run_id}.json"))

        # report.md
        generate_report(schedule, gate, integrity, tmp_dir, ledger)

        # P0: atomic publish - os.rename is atomic on same volume; target must
        # not exist (raises FileExistsError/PermissionError if race creates it).
        # This closes the TOCTOU window between exists() check and move.
        try:
            os.rename(str(tmp_dir), str(archive_dir))
        except (FileExistsError, PermissionError, OSError) as e:
            print(json.dumps({"status": "ARCHIVE_RACE_DETECTED",
                "archive_dir": str(archive_dir), "error": str(e),
                "reason": "原子发布失败：目标目录已存在（并发竞争），禁止覆盖"},
                ensure_ascii=False))
            raise SystemExit(2)
    except BaseException:
        # P0-3: cleanup partial archive on ANY failure (incl. SystemExit)
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
        raise
    return str(archive_dir)


# ---- report generation ----

def generate_report(schedule: dict, gate: dict, integrity: dict,
                    output_dir: Path, ledger: BudgetLedger) -> str:
    """Generate Markdown gate report."""
    lines = []
    lines.append(f"# Phase 6 6B1 Gate Report")
    lines.append(f"")
    lines.append(f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Verdict**: **{gate['verdict']}**")
    lines.append(f"")
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"- Δ_dev (mean delta across years): {gate['delta_dev']:.2%}")
    lines.append(f"- Worst year delta: {gate['worst_year']:.2%}")
    lines.append(f"- Total calls attempted: {gate['total_calls_attempted']} / 792")
    lines.append(f"- Budget remaining: {gate['budget_remaining']}")
    lines.append(f"- All cells completed: {gate['all_cells_completed']}")
    lines.append(f"")
    lines.append(f"### Gate Criteria")
    lines.append(f"")
    lines.append(f"| Criterion | Threshold | Actual | Met |")
    lines.append(f"|-----------|-----------|--------|-----|")
    delta_met = gate['delta_dev'] >= GATE_DELTA_DEV_PP / 100
    worst_met = gate['worst_year'] >= GATE_WORST_YEAR_PP / 100
    lines.append(f"| Δ_dev ≥ +{GATE_DELTA_DEV_PP}pp | ≥ {GATE_DELTA_DEV_PP/100:.1%} | {gate['delta_dev']:.2%} | {delta_met} |")
    lines.append(f"| worst_year ≥ {GATE_WORST_YEAR_PP}pp | ≥ {GATE_WORST_YEAR_PP/100:.1%} | {gate['worst_year']:.2%} | {worst_met} |")
    lines.append(f"")

    lines.append(f"## Per-Cell Accuracies (correct / 40)")
    lines.append(f"")
    lines.append(f"| Year | Repeat | b1a_prime (none) | b1b (only) | b1c (combined) | Δ (b1c − b1a') |")
    lines.append(f"|------|--------|-------------------|------------|-----------------|-----------------|")
    for d in gate["per_cell_deltas"]:
        lines.append(
            f"| {d['year']} | {d['repeat']} | {d['acc_b1a_prime']:.2%} | "
            f"{d['acc_b1b']:.2%} | {d['acc_b1c']:.2%} | "
            f"{d['delta']:+.2%} |"
        )
    lines.append(f"")
    lines.append(f"| Year | Mean Δ |")
    lines.append(f"|------|--------|")
    for y, m in gate["year_means"].items():
        lines.append(f"| {y} | {m:+.2%} |")
    lines.append(f"")

    lines.append(f"## Integrity")
    lines.append(f"")
    lines.append(f"- Expected keys: {integrity['expected_count']}")
    lines.append(f"- Actual records: {integrity['actual_count']}")
    lines.append(f"- Duplicates: {integrity['duplicates']}")
    lines.append(f"- Missing: {integrity['missing']}")
    lines.append(f"- Extra: {integrity['extra']}")
    lines.append(f"- Pass: {integrity['pass']}")
    if integrity["detail_errors"]:
        lines.append(f"- Detail errors: {len(integrity['detail_errors'])}")
        for e in integrity["detail_errors"][:10]:
            lines.append(f"  - {e}")
    lines.append(f"")

    lines.append(f"## Schedule")
    lines.append(f"")
    lines.append(f"- Total slices: {schedule['total_slices']}")
    lines.append(f"- Total scheduled: {schedule['total_scheduled_calls']}")
    lines.append(f"- Slices completed: {len(ledger._data['slices_completed'])}")

    report = "\n".join(lines)
    report_path = output_dir / "report.md"
    with open(str(report_path), "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[report] → {report_path}")
    return str(report_path)


# ---- manifest verification (reuse runner's RESUME_MANIFEST_FIELDS) ----

def _build_current_manifest(sl: dict, provider: str, model: str) -> dict:
    """Build manifest dict matching runner's build_resume_manifest()."""
    from benchmark.runners.run_benchmark import _sha256_file, _code_fingerprint, RESUME_MANIFEST_FIELDS
    from benchmark.runners.profiles import prompt_fingerprint, resolve_profile

    profile = resolve_profile(REASONED_PROFILE)
    case_ids_file = os.path.join(sl["output_dir"], f"case_ids_{sl['slice_id']}.json")

    manifest = {
        "dataset_sha256": _sha256_file(os.path.abspath(sl["dataset"])),
        "case_ids_sha256": (_sha256_file(os.path.abspath(case_ids_file))
                            if os.path.exists(case_ids_file) else None),
        "profile_id": profile.profile_id,
        "chart_schema_version": profile.chart_schema_version,
        "arm": sl["arm"],
        "ziwei_arm": sl["ziwei_arm"],
        "attempt_stage": "main",
        "repeat_idx": sl["repeat"],
        "provider": provider,
        "model": model,
        "temperature": 0.0,
        "sample_temperature": 0.4,
        "n_samples": 1,
        "aggregate": "majority",
        "method": "direct_choice",
        "prompt_template_sha256": prompt_fingerprint(profile),
        "code_sha256": _code_fingerprint(),
        "scheduled_calls": sl["size"],
        "hard_cap": sl["hard_cap"],
        "as_of_date": FROZEN_DATE,
    }
    return manifest


def verify_slice_manifest(sl: dict, provider: str, model: str) -> tuple[bool, dict]:
    """Verify slice manifest matches current configuration.
    Returns (ok, diff) where diff is {} on success or {field: {stored, current}} on mismatch.
    """
    from benchmark.runners.run_benchmark import RESUME_MANIFEST_FIELDS

    manifest_path = sl["manifest_path"]
    if not os.path.exists(manifest_path):
        return False, {"_manifest": {"stored": "<MISSING>", "current": "exists expected"}}
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            stored = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, {"_manifest": {"stored": f"<ERROR: {e}>", "current": "valid JSON expected"}}

    current = _build_current_manifest(sl, provider, model)
    diff = {}
    for k in RESUME_MANIFEST_FIELDS:
        stored_val = stored.get(k, "<MISSING>")
        current_val = current.get(k)
        if stored_val != current_val:
            diff[k] = {"stored": stored_val, "current": current_val}
    return len(diff) == 0, diff


# ---- preflight checks (T8-T10, spec §9.1-9.4) ----

def _count_call_attempts(events_path: str) -> int:
    """Count call_attempt events from events file."""
    if not events_path or not os.path.exists(events_path):
        return 0
    count = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("kind") == "call_attempt":
                    count += 1
            except json.JSONDecodeError:
                pass
    return count


def _validate_events(events_path: str, scheduled_calls: int,
                     hard_cap: int) -> tuple[bool, int, str]:
    """Validate events file: parseable, count within [scheduled_calls, hard_cap].
    Returns (ok, count, reason).
    """
    if not events_path or not os.path.exists(events_path):
        return False, 0, "events file missing"
    count = 0
    corrupt_lines = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("kind") == "call_attempt":
                    count += 1
            except json.JSONDecodeError:
                corrupt_lines += 1
    if corrupt_lines > 0:
        return False, count, f"events file has {corrupt_lines} corrupt JSON lines"
    if count < scheduled_calls:
        return False, count, f"call_attempt count {count} < scheduled_calls {scheduled_calls}"
    if count > hard_cap:
        return False, count, f"call_attempt count {count} > hard_cap {hard_cap}"
    return True, count, "ok"


def preflight_checks(schedule: dict) -> None:
    """T8-T10 offline gates (spec §9.1-9.4). Fail-closed: SystemExit(2) on any violation."""
    from benchmark.formatters.chart_context import render_reasoned_context

    # §9.1 Data integrity: ziwei coverage 40/40 per year
    for year in YEARS:
        cases = load_jsonl(YEAR_DATASETS[year])
        if len(cases) != QUESTIONS_PER_CELL:
            print(json.dumps({"status": "BLOCKED_PRECONDITION",
                "reason": f"{year} enriched: expected {QUESTIONS_PER_CELL} cases, got {len(cases)}"},
                ensure_ascii=False))
            raise SystemExit(2)
        ziwei_ok = sum(1 for c in cases
                       if c.get("chart_input", {}).get("ziwei"))
        if ziwei_ok != QUESTIONS_PER_CELL:
            print(json.dumps({"status": "BLOCKED_PRECONDITION",
                "reason": f"{year} enriched ziwei coverage: {ziwei_ok}/{QUESTIONS_PER_CELL}",
                "expected": QUESTIONS_PER_CELL}, ensure_ascii=False))
            raise SystemExit(2)
        # §9.1.2-4: verify ziwei sub-structure
        for c in cases:
            ziwei = c.get("chart_input", {}).get("ziwei", {})
            basic = ziwei.get("basic_info", {})
            for field in ("ming_gong_gan_zhi", "shen_gong_position",
                          "wu_xing_ju", "ming_zhu", "shen_zhu"):
                if field not in basic:
                    print(json.dumps({"status": "BLOCKED_PRECONDITION",
                        "reason": f"{year} case {c.get('case_id')}: ziwei.basic_info missing {field}"},
                        ensure_ascii=False))
                    raise SystemExit(2)
            palaces = ziwei.get("twelve_palaces", [])
            if len(palaces) != 12:
                print(json.dumps({"status": "BLOCKED_PRECONDITION",
                    "reason": f"{year} case {c.get('case_id')}: twelve_palaces len={len(palaces)}"},
                    ensure_ascii=False))
                raise SystemExit(2)
            # §9.1.3: palace names must be unique
            palace_names = [p.get("name", "") for p in palaces]
            if len(set(palace_names)) != 12:
                print(json.dumps({"status": "BLOCKED_PRECONDITION",
                    "reason": f"{year} case {c.get('case_id')}: palace names not unique"},
                    ensure_ascii=False))
                raise SystemExit(2)
            if "si_hua" not in ziwei:
                print(json.dumps({"status": "BLOCKED_PRECONDITION",
                    "reason": f"{year} case {c.get('case_id')}: si_hua missing"},
                    ensure_ascii=False))
                raise SystemExit(2)

    # §9.3 B1-b isolation: render_reasoned_context(only) must NOT contain bazi markers
    # Full frozen set from spec §T8 (_BAZI_SECTION_MARKERS_B1B_FORBIDDEN)
    _BAZI_MARKERS = [
        "四柱：", "日主：",
        "【四柱】", "【日主】", "【大运】", "【神煞】",
        "【十神统计】", "【五行统计】", "【纳音五行】",
        "【地支关系】", "【胎元／命宫／身宫】", "【真太阳时校正】",
    ]
    all_cases = []
    for year in YEARS:
        all_cases.extend(load_jsonl(YEAR_DATASETS[year]))
    for c in all_cases:
        ctx = render_reasoned_context(c, CHART_SCHEMA, "only")
        for marker in _BAZI_MARKERS:
            if marker in ctx:
                print(json.dumps({"status": "BLOCKED_B1B_CONTAMINATION",
                    "case_id": c.get("case_id"), "marker": marker,
                    "reason": f"B1-b (only) context contains forbidden bazi marker '{marker}'"},
                    ensure_ascii=False))
                raise SystemExit(2)

    # §9.4 B1-a' isolation: render_reasoned_context(none) must NOT contain ziwei header
    for c in all_cases:
        ctx = render_reasoned_context(c, CHART_SCHEMA, "none")
        if "【紫微斗数·本命】" in ctx:
            print(json.dumps({"status": "BLOCKED_B1A_ZIWEI_LEAK",
                "case_id": c.get("case_id"),
                "reason": "B1-a' (none) context contains ziwei header"},
                ensure_ascii=False))
            raise SystemExit(2)

    print("[preflight] T8-T10 checks PASS (ziwei 80/80, B1-b clean, B1-a' clean)")


def _audit_skipped_slices(schedule: dict, start_idx: int, ledger: BudgetLedger,
                          provider: str, model: str) -> None:
    """P0-2: audit all skipped slices (schedule[1:start_idx]) before main loop.
    --from-slice must not bypass manifest/events verification for completed slices.
    P1-4: reconcile ledger call count with actual events evidence."""
    if start_idx <= 1:
        return
    skipped = schedule["slices"][1:start_idx]
    for sl in skipped:
        if not ledger.sliced_completed(sl["slice_id"]):
            print(json.dumps({"status": "FROM_SLICE_SKIP_INCOMPLETE",
                "slice_id": sl["slice_id"],
                "reason": "--from-slice 跳过了未完成的 slice，禁止继续"},
                ensure_ascii=False))
            raise SystemExit(2)
        ok, diff = verify_slice_manifest(sl, provider, model)
        if not ok:
            print(json.dumps({"status": "FROM_SLICE_MANIFEST_DRIFT",
                "slice_id": sl["slice_id"], "diff": diff,
                "reason": "被跳过的 slice manifest 与当前配置不一致"},
                ensure_ascii=False))
            raise SystemExit(2)
        ev_ok, ev_count, ev_reason = _validate_events(
            sl["events_path"], sl["size"], sl["hard_cap"])
        if not ev_ok:
            print(json.dumps({"status": "FROM_SLICE_EVENTS_INVALID",
                "slice_id": sl["slice_id"], "reason": ev_reason,
                "calls_found": ev_count,
                "reason_detail": "被跳过的 slice events 损坏/缺失"},
                ensure_ascii=False))
            raise SystemExit(2)
        # P1-4: reconcile ledger call count with actual events evidence
        ledger_calls = ledger._data["calls_attempted_by_slice"].get(sl["slice_id"], 0)
        if ledger_calls != ev_count:
            ledger._data["calls_attempted_by_slice"][sl["slice_id"]] = ev_count
            ledger._data["total_calls_attempted"] = sum(
                ledger._data["calls_attempted_by_slice"].values())
            ledger._save()
            print(f"      [reconcile] {sl['slice_id']}: ledger {ledger_calls} -> {ev_count}")
    print(f"[from-slice] {start_idx - 1} skipped slices audited OK")


# ---- main ----

def main(argv=None):
    parser = argparse.ArgumentParser(description="Phase 6 6B1 orchestrator")
    parser.add_argument("--provider", default="deepseek", help="模型 provider")
    parser.add_argument("--model", default="deepseek-chat", help="模型名")
    parser.add_argument("--output-dir", default="benchmark/outputs/phase6_6b1",
                        help="产物输出根目录")
    parser.add_argument("--dry-run", action="store_true", help="仅生成 schedule，不调 API")
    parser.add_argument("--from-slice", type=int, default=0,
                        help="从指定位置开始（smoke 之后的位置索引）")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    os.makedirs(str(output_dir), exist_ok=True)

    # 1. Generate schedule
    schedule = generate_schedule(output_dir)

    if schedule["total_scheduled_calls"] != RATED_CALLS:
        print(f"ERROR: expected {RATED_CALLS} scheduled calls, got {schedule['total_scheduled_calls']}")
        raise SystemExit(1)

    ledger_path = str(output_dir / "budget_ledger.json")
    ledger = BudgetLedger(ledger_path)

    # 2. Preflight checks (T8-T10, spec §9.1-9.4)
    if args.dry_run:
        print("\n[dry-run] schedule OK. Exiting without API calls.")
        return 0

    preflight_checks(schedule)

    # P1-3: validate ledger against current schedule (completed slices have
    # valid manifest + events, no fake slice IDs)
    ledger.validate_against_schedule(schedule, args.provider, args.model)

    # 3. Smoke gate — 5-state machine (spec §9.5, mandatory — no skip)
    print("\n=== SMOKE GATE (schedule[0] only) ===")
    smoke_sl = schedule["slices"][0]
    smoke_detail = Path(smoke_sl["detail_path"])
    smoke_manifest = Path(smoke_sl["manifest_path"])
    smoke_events = Path(smoke_sl["events_path"])

    # ---- 5-state resolve ----
    detail_exists = smoke_detail.exists()
    manifest_exists = smoke_manifest.exists()
    events_exists = smoke_events.exists()

    smoke_state = "fresh"
    if not detail_exists and not manifest_exists and not events_exists:
        smoke_state = "fresh"
    elif detail_exists and manifest_exists:
        rows = load_jsonl(str(smoke_detail))
        terminal_count = sum(
            1 for r in rows
            if r.get("terminal_state") in ("parsed", "invalid",
                                           "unresolved", "call_failed")
        )
        if terminal_count >= smoke_sl["size"]:
            smoke_state = "completed"
        else:
            smoke_state = "resume"
    elif manifest_exists and not detail_exists:
        smoke_state = "resume"
    elif detail_exists and not manifest_exists:
        smoke_state = "blocked_corrupt"
    else:
        smoke_state = "blocked_corrupt"

    print(f"[smoke] state={smoke_state} slice={smoke_sl['slice_id']} "
          f"size={smoke_sl['size']} cap={smoke_sl['hard_cap']}")

    if smoke_state == "blocked_corrupt":
        print(json.dumps({"status": "BLOCKED_SMOKE_ARTIFACT_CORRUPT",
            "reason": "detail/events 存在但 manifest 缺失或状态不一致"},
            ensure_ascii=False))
        return 2

    if smoke_state == "completed":
        # Re-verify: events existence, full manifest, parser rate, keys
        if not smoke_events.exists():
            print(json.dumps({"status": "BLOCKED_SMOKE_ARTIFACT_CORRUPT",
                "reason": "completed state but events file missing"},
                ensure_ascii=False))
            return 2
        ok, diff = verify_slice_manifest(smoke_sl, args.provider, args.model)
        if not ok:
            print(json.dumps({"status": "BLOCKED_SMOKE_MANIFEST_MISMATCH",
                "diff": diff,
                "reason": "smoke manifest 与当前配置不一致"},
                ensure_ascii=False))
            return 2

        rows = load_jsonl(str(smoke_detail))
        detail_keys = [tuple(r.get("attempt_key", [])) for r in rows]
        completed_keys = set(detail_keys)
        dataset_id = os.path.splitext(os.path.basename(smoke_sl["dataset"]))[0]
        expected_keys = set()
        for case_id in smoke_sl["case_ids"]:
            expected_keys.add(build_expected_key(
                dataset_id, REASONED_PROFILE, smoke_sl["arm"],
                case_id, smoke_sl["repeat"], args.provider, args.model,
            ))
        if len(detail_keys) != len(expected_keys):
            print(json.dumps({"status": "BLOCKED_SMOKE_INCOMPLETE",
                "expected": len(expected_keys), "got": len(detail_keys)},
                ensure_ascii=False))
            return 2
        if len(completed_keys) != len(detail_keys):
            print(json.dumps({"status": "BLOCKED_SMOKE_DUPLICATE_KEY"},
                ensure_ascii=False))
            return 2
        if completed_keys != expected_keys:
            print(json.dumps({"status": "BLOCKED_SMOKE_INCOMPLETE",
                "reason": "completed keys != expected keys"},
                ensure_ascii=False))
            return 2
        parse_ok = sum(1 for r in rows if r.get("terminal_state") == "parsed")
        parser_rate = parse_ok / len(rows) if rows else 0
        if parser_rate < 0.95:
            print(json.dumps({"status": "BLOCKED_PARSER_SMOKE",
                "parser_rate": parser_rate}, ensure_ascii=False))
            return 2
        # Validate events: parseable + count within [scheduled, hard_cap]
        ev_ok, calls, ev_reason = _validate_events(
            str(smoke_events), smoke_sl["size"], smoke_sl["hard_cap"])
        if not ev_ok:
            print(json.dumps({"status": "BLOCKED_SMOKE_ARTIFACT_CORRUPT",
                "reason": f"events validation failed: {ev_reason}",
                "calls_found": calls}, ensure_ascii=False))
            return 2
        # Budget check: incremental formula (avoid double-counting on resume)
        prev_recorded = ledger._data["calls_attempted_by_slice"].get(smoke_sl["slice_id"], 0)
        increment = max(0, calls - prev_recorded)
        if ledger.total_attempted + increment > ledger.hard_cap:
            print(json.dumps({"status": "BUDGET_EXCEEDED",
                "total_attempted": ledger.total_attempted,
                "smoke_calls": calls,
                "previously_recorded": prev_recorded,
                "increment": increment,
                "hard_cap": ledger.hard_cap,
                "reason": f"completed smoke would breach 792 cap (increment={increment})"},
                ensure_ascii=False))
            return 2
        ledger.record_slice_completed(smoke_sl["slice_id"], calls)
        print(f"[smoke] PASS (completed, resume) — {calls} calls already counted")

    else:
        # fresh or resume: run subprocess
        # Budget pre-check (spec §8.7)
        if not ledger.budget_ok_for_slice(smoke_sl["slice_id"], smoke_sl["hard_cap"]):
            print(json.dumps({"status": "BUDGET_EXCEEDED",
                "total_attempted": ledger.total_attempted,
                "slice_hard_cap": smoke_sl["hard_cap"],
                "hard_cap": ledger.hard_cap,
                "reason": "smoke 预算预占失败"},
                ensure_ascii=False))
            return 2

        # D3 pre-resume checks (spec §9.5): only for resume state
        if smoke_state == "resume":
            # 1. Manifest must match current config
            ok, diff = verify_slice_manifest(smoke_sl, args.provider, args.model)
            if not ok:
                print(json.dumps({"status": "BLOCKED_SMOKE_MANIFEST_MISMATCH",
                    "diff": diff,
                    "reason": "resume 前 manifest 不匹配，禁止续跑"},
                    ensure_ascii=False))
                return 2
            # 2. Observed keys must be strict subset of expected (no extra, no dupes)
            if smoke_detail.exists():
                existing_rows = load_jsonl(str(smoke_detail))
                existing_keys = set(tuple(r.get("attempt_key", [])) for r in existing_rows)
                # Check for duplicate keys
                if len(existing_rows) != len(existing_keys):
                    print(json.dumps({"status": "BLOCKED_SMOKE_DUPLICATE_KEY",
                        "rows": len(existing_rows), "unique_keys": len(existing_keys),
                        "reason": "resume 前 detail 含重复 attempt key"},
                        ensure_ascii=False))
                    return 2
                dataset_id = os.path.splitext(os.path.basename(smoke_sl["dataset"]))[0]
                expected_keys = set()
                for case_id in smoke_sl["case_ids"]:
                    expected_keys.add(build_expected_key(
                        dataset_id, REASONED_PROFILE, smoke_sl["arm"],
                        case_id, smoke_sl["repeat"], args.provider, args.model,
                    ))
                extra = existing_keys - expected_keys
                if extra:
                    print(json.dumps({"status": "BLOCKED_SMOKE_KEY_MISMATCH",
                        "extra_count": len(extra),
                        "extra_sample": list(extra)[:3],
                        "reason": "observed keys 含 expected 之外的 key"},
                        ensure_ascii=False))
                    return 2

        smoke_cmd = [
            sys.executable, "-u",
            os.path.join("benchmark", "runners", "run_benchmark.py"),
            "--dataset", smoke_sl["dataset"],
            "--profile", REASONED_PROFILE,
            "--chart-schema-version", CHART_SCHEMA,
            "--arm", smoke_sl["arm"],
            "--ziwei-arm", smoke_sl["ziwei_arm"],
            "--attempt-stage", "main",
            "--repeat-idx", str(smoke_sl["repeat"]),
            "--case-details-jsonl", smoke_sl["detail_path"],
            "--case-ids-file", _write_case_ids_file(smoke_sl),
            "--provider", args.provider,
            "--model", args.model,
            "--method", "direct_choice",
            "--model-runner",
            "--n-samples", "1",
            "--temperature", "0",
            "--scheduled-calls", str(smoke_sl["size"]),
            "--hard-cap", str(smoke_sl["hard_cap"]),
            "--output-dir", smoke_sl["output_dir"],
            "--as-of-date", FROZEN_DATE,
        ]
        if smoke_state == "resume":
            smoke_cmd.append("--resume")

        clean_env = dict(os.environ)
        for var in ENV_CLEANUP:
            clean_env.pop(var, None)

        smoke_result = subprocess.run(smoke_cmd, capture_output=False,
                                      text=True, env=clean_env)

        calls_attempted = _count_call_attempts(str(smoke_events))

        if smoke_result.returncode == 2:
            ledger.record_calls_only(smoke_sl["slice_id"], calls_attempted)
            print(json.dumps({"status": "BLOCKED_SMOKE_RUNNER_CONFIG",
                "returncode": 2, "calls_attempted": calls_attempted,
                "reason": "确定性错误，已记账，停止"},
                ensure_ascii=False))
            return 2
        if smoke_result.returncode == 3:
            ledger.record_calls_only(smoke_sl["slice_id"], calls_attempted)
            print(json.dumps({"status": "BLOCKED_INCOMPLETE",
                "returncode": 3, "calls_attempted": calls_attempted,
                "reason": "hard cap 耗尽，已记账，停止"},
                ensure_ascii=False))
            return 2
        if smoke_result.returncode != 0:
            ledger.record_calls_only(smoke_sl["slice_id"], calls_attempted)
            print(json.dumps({"status": "BLOCKED_SMOKE_CRASH",
                "returncode": smoke_result.returncode,
                "calls_attempted": calls_attempted,
                "reason": "子进程崩溃，已记账，停止"},
                ensure_ascii=False))
            return 2

        # parser gate (only code 0)
        rows = load_jsonl(str(smoke_detail)) if smoke_detail.exists() else []
        detail_keys = [tuple(r.get("attempt_key", [])) for r in rows]
        completed_keys = set(detail_keys)
        dataset_id = os.path.splitext(os.path.basename(smoke_sl["dataset"]))[0]
        expected_keys = set()
        for case_id in smoke_sl["case_ids"]:
            expected_keys.add(build_expected_key(
                dataset_id, REASONED_PROFILE, smoke_sl["arm"],
                case_id, smoke_sl["repeat"], args.provider, args.model,
            ))

        if len(detail_keys) != len(expected_keys):
            ledger.record_calls_only(smoke_sl["slice_id"], calls_attempted)
            print(json.dumps({"status": "BLOCKED_SMOKE_INCOMPLETE",
                "expected": len(expected_keys), "got": len(detail_keys),
                "calls_attempted": calls_attempted}, ensure_ascii=False))
            return 2
        if len(completed_keys) != len(detail_keys):
            ledger.record_calls_only(smoke_sl["slice_id"], calls_attempted)
            print(json.dumps({"status": "BLOCKED_SMOKE_DUPLICATE_KEY",
                "calls_attempted": calls_attempted}, ensure_ascii=False))
            return 2
        if completed_keys != expected_keys:
            ledger.record_calls_only(smoke_sl["slice_id"], calls_attempted)
            print(json.dumps({"status": "BLOCKED_SMOKE_INCOMPLETE",
                "reason": "keys mismatch", "calls_attempted": calls_attempted},
                ensure_ascii=False))
            return 2

        parse_ok = sum(1 for r in rows if r.get("terminal_state") == "parsed")
        parser_rate = parse_ok / len(rows) if rows else 0
        if parser_rate < 0.95:
            ledger.record_calls_only(smoke_sl["slice_id"], calls_attempted)
            print(json.dumps({"status": "BLOCKED_PARSER_SMOKE",
                "parser_rate": parser_rate,
                "calls_attempted": calls_attempted}, ensure_ascii=False))
            return 2

        # Validate events: parseable + count within [scheduled, hard_cap]
        ev_ok, ev_count, ev_reason = _validate_events(
            str(smoke_events), smoke_sl["size"], smoke_sl["hard_cap"])
        if not ev_ok:
            ledger.record_calls_only(smoke_sl["slice_id"], calls_attempted)
            print(json.dumps({"status": "BLOCKED_SMOKE_ARTIFACT_CORRUPT",
                "reason": f"events validation failed: {ev_reason}",
                "calls_found": ev_count}, ensure_ascii=False))
            return 2

        # P1-C: reconcile smoke ledger with events evidence (downward fix),
        # not record_slice_completed's max semantics which can't correct down
        prev_calls = ledger._data["calls_attempted_by_slice"].get(
            smoke_sl["slice_id"], 0)
        if prev_calls != ev_count:
            ledger._data["calls_attempted_by_slice"][smoke_sl["slice_id"]] = ev_count
            ledger._data["total_calls_attempted"] = sum(
                ledger._data["calls_attempted_by_slice"].values())
        if smoke_sl["slice_id"] not in ledger._data["slices_completed"]:
            ledger._data["slices_completed"].append(smoke_sl["slice_id"])
        ledger._save()
        print(f"[smoke] PASS - {ev_count} calls counted in budget")

    # 4. Main loop over remaining slices (smoke is schedule[0], start from 1)
    start_idx = max(args.from_slice, 1)

    # P0-2: audit all skipped slices before entering main loop
    _audit_skipped_slices(schedule, start_idx, ledger, args.provider, args.model)

    slices_to_run = schedule["slices"][start_idx:]

    print(f"\n=== MAIN LOOP ({len(slices_to_run)} slices) ===")
    for i, sl in enumerate(slices_to_run):
        print(f"\n--- slice {start_idx + i + 1}/{schedule['total_slices']} "
              f"budget: {ledger.total_attempted}/{ledger.hard_cap} ---")

        if ledger.sliced_completed(sl["slice_id"]):
            # Verify manifest matches current config before skipping
            ok, diff = verify_slice_manifest(sl, args.provider, args.model)
            if ok:
                # Also verify events file is valid (not just manifest)
                ev_ok, ev_count, ev_reason = _validate_events(
                    sl["events_path"], sl["size"], sl["hard_cap"])
                if not ev_ok:
                    print(f"      [WARN] events invalid: {ev_reason} — re-running slice")
                else:
                    # P1-4: reconcile ledger call count with actual events evidence
                    ledger_calls = ledger._data["calls_attempted_by_slice"].get(
                        sl["slice_id"], 0)
                    if ledger_calls != ev_count:
                        ledger._data["calls_attempted_by_slice"][sl["slice_id"]] = ev_count
                        ledger._data["total_calls_attempted"] = sum(
                            ledger._data["calls_attempted_by_slice"].values())
                        ledger._save()
                        print(f"      [reconcile] {sl['slice_id']}: "
                              f"ledger {ledger_calls} -> {ev_count}")
                    print(f"      [skip] already completed (manifest+events verified)")
                    continue
            else:
                print(f"      [WARN] manifest drift detected — re-running slice")
                print(json.dumps(diff, ensure_ascii=False, indent=2))
                # Don't skip — fall through to re-run with --resume

        # Budget check with frozen formula (spec §8.7)
        if not ledger.budget_ok_for_slice(sl["slice_id"], sl["hard_cap"]):
            print(json.dumps({"status": "BUDGET_EXCEEDED",
                "total_attempted": ledger.total_attempted,
                "slice_hard_cap": sl["hard_cap"],
                "already_for_slice": ledger._data["calls_attempted_by_slice"].get(sl["slice_id"], 0),
                "hard_cap": ledger.hard_cap,
                "reason": "frozen formula: total + (hard_cap - attempted) > 792"},
                ensure_ascii=False))
            raise SystemExit(2)

        rc = run_slice(sl, args.provider, args.model, dry_run=False)
        calls = _count_call_attempts(sl["events_path"])

        if rc == 0:
            # Validate events: count within [scheduled, hard_cap]
            ev_ok, ev_count, ev_reason = _validate_events(
                sl["events_path"], sl["size"], sl["hard_cap"])
            if not ev_ok:
                ledger.record_calls_only(sl["slice_id"], calls)
                print(json.dumps({"status": "BLOCKED_EVENTS_INVALID",
                    "slice_id": sl["slice_id"], "reason": ev_reason,
                    "calls_found": ev_count}, ensure_ascii=False))
                raise SystemExit(2)
            ledger.record_slice_completed(sl["slice_id"], ev_count)
        elif rc == 2:
            # Deterministic error — stop immediately (spec §8.5)
            ledger.record_calls_only(sl["slice_id"], calls)
            print(json.dumps({"status": "BLOCKED_RUNNER_CONFIG",
                "slice_id": sl["slice_id"], "returncode": 2,
                "calls_attempted": calls,
                "reason": "确定性错误，立即停止"}, ensure_ascii=False))
            raise SystemExit(2)
        elif rc == 3:
            # Hard cap exhausted — stop immediately (spec §8.5)
            ledger.record_calls_only(sl["slice_id"], calls)
            print(json.dumps({"status": "BLOCKED_INCOMPLETE",
                "slice_id": sl["slice_id"], "returncode": 3,
                "calls_attempted": calls,
                "reason": "hard cap 耗尽，立即停止"}, ensure_ascii=False))
            raise SystemExit(2)
        else:
            # Crash — record calls, stop (spec §8.5)
            ledger.record_calls_only(sl["slice_id"], calls)
            print(json.dumps({"status": "BLOCKED_SLICE_CRASH",
                "slice_id": sl["slice_id"], "returncode": rc,
                "calls_attempted": calls,
                "reason": "子进程崩溃，立即停止"}, ensure_ascii=False))
            raise SystemExit(2)

    # 4. Final integrity and gate
    print("\n=== INTEGRITY CHECK ===")
    integrity = integrity_check(schedule, ledger, args.provider, args.model)
    print(json.dumps({k: v for k, v in integrity.items() if k != "detail_errors"},
                     indent=2))
    if integrity["detail_errors"]:
        for e in integrity["detail_errors"]:
            print(f"  ERR: {e}")

    if not integrity["pass"]:
        print(json.dumps({
            "status": "INTEGRITY_FAILED",
            "expected_count": integrity["expected_count"],
            "actual_count": integrity["actual_count"],
            "duplicates": integrity["duplicates"],
            "missing": integrity["missing"],
            "extra": integrity["extra"],
            "reason": "integrity 检查未通过，拒绝基于不完整数据计算 gate 或生成报告",
        }, ensure_ascii=False))
        raise SystemExit(2)

    print("\n=== GATE COMPUTATION ===")
    gate = compute_gate(schedule, ledger)
    print(json.dumps({k: v for k, v in gate.items() if k != "per_cell_deltas"},
                     indent=2))
    print(f"\n  verdict: {gate['verdict']}")
    print(f"  Δ_dev: {gate['delta_dev']:.2%}  "
          f"worst_year: {gate['worst_year']:.2%}")

    # 5. Generate report
    generate_report(schedule, gate, integrity, output_dir, ledger)

    # P1-5: generate formal archive (v9 §12) under docs/phase6/6b1/<run_id>/
    archive_path = generate_archive(schedule, gate, integrity, ledger,
                                    output_dir, args.provider, args.model)
    print(f"\n  archive: {archive_path}")

    print(f"\n=== DONE ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
