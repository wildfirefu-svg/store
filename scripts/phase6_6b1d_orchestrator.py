#!/usr/bin/env python3
"""Phase 6 6B1-D orchestrator - 紫微斗数与子平八字的干扰机制探索.

协议摘要（与 6b1d plan 一致）：
  - 纯探索性研究，非正式 6B2
  - 双年度: 2024 holdout + 2025 holdout, 各 40 题
  - 5 arms × 5 groups × 2 years × 3 repeats = 150 slices
  - 每 slice 8 题, local cap 10, 全局 hard cap 1320 (1200 + 120 reserve)
  - 5×5 Latin square 全程交错
  - 动态 effective_cap, BudgetLedger.allocated_cap_by_slice 权威
  - 五 smoke 状态机 (fresh/resume/completed/blocked_corrupt)
  - 全描述性分析，不作显著性宣称

用法:
  python scripts/phase6_6b1d_orchestrator.py --provider deepseek --model deepseek-chat \
    --output-dir benchmark/outputs/phase6_6b1d --dry-run
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

# Ensure project root on sys.path for benchmark.* imports
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

# arm -> ziwei_arm (6B1-D 5 arms)
ARM_ZIWEI_MAP = {
    "b1a_prime": "none",
    "b1b": "only",
    "b1c": "combined",
    "b2b": "ziwei_mini",
    "b2c": "sequential",
}

ARMS = list(ARM_ZIWEI_MAP.keys())
YEARS = ["2024", "2025"]
REPEATS = [0, 1, 2]
QUESTIONS_PER_CELL = 40

# 每 cell 拆 5 组, 每组 8 题
SLICE_LAYOUT = [8, 8, 8, 8, 8]
GROUPS_PER_CELL = 5
SLICE_SIZE = 8

# 5×5 Latin square: position -> group -> arm
LATIN_SQUARE = {
    0: {0: "b1a_prime", 1: "b1b",      2: "b1c",   3: "b2b",   4: "b2c"},
    1: {0: "b1c",       1: "b2b",      2: "b2c",   3: "b1a_prime", 4: "b1b"},
    2: {0: "b2b",       1: "b2c",      2: "b1a_prime", 3: "b1b",  4: "b1c"},
    3: {0: "b2c",       1: "b1a_prime", 2: "b1b",   3: "b1c",   4: "b2b"},
    4: {0: "b1b",       1: "b1c",      2: "b2b",   3: "b2c",   4: "b1a_prime"},
}

# Frozen experiment date
FROZEN_DATE = "2026-07-22"

# Env vars to strip from subprocess
ENV_CLEANUP = ["BAZI_RAG", "BAZI_RAG_CORPUS", "BAZI_FEWSHOT_FILE", "BAZI_APB_BLOCK"]

# Budget constants
SLICE_BASE_CALLS = 8
SLICE_RESERVE = 2
SLICE_MAX_CAP = SLICE_BASE_CALLS + SLICE_RESERVE  # 10
GLOBAL_LEDGER_CAP = 1320   # 1200 scheduled + 120 reserve
TOTAL_SCHEDULED_CALLS = 1200
TOTAL_SLICES = 150         # 5 × 5 × 2 × 3

# Smoke constants
SMOKE_ARMS_ORDER = ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]
SMOKE_PARSER_RATE_THRESHOLD = 1.0   # 100% (8/8)

# Terminal states (复用 6B1)
TERMINAL_STATES = {"parsed", "invalid", "unresolved", "call_failed"}

# Bootstrap fingerprint scope
FINGERPRINT_SCOPE = [
    "scripts/phase6_6b1d_orchestrator.py",
    "benchmark/runners/run_benchmark.py",
    "benchmark/formatters/chart_context.py",
    "benchmark/formatters/baziqa_prompt.py",
    "benchmark/runners/profiles.py",
]

ARCHIVE_ROOT = "docs/phase6/6b1d"
EXPERIMENT_ID_PREFIX = "6b1d"


def atomic_write_json(path: str, data: dict) -> None:
    """Atomically write JSON to disk (write temp + rename)."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_jsonl(path: str) -> list:
    """Load JSONL file, return list of records."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


# ---- BudgetLedger (6B1-D, with allocated_cap_by_slice schema) ----

class BudgetLedger:
    """Global budget ledger with fail-closed corruption checks.

    6B1-D 扩展: 新增 allocated_cap_by_slice 字段作为 effective_cap 权威来源.
    """

    def __init__(self, ledger_path: str):
        self.path = ledger_path
        self._data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {
                "global_hard_cap": GLOBAL_LEDGER_CAP,
                "slices_completed": [],
                "calls_attempted_by_slice": {},
                "total_calls_attempted": 0,
                "allocated_cap_by_slice": {},
            }
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            print(json.dumps({
                "status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path, "error": str(e),
                "reason": "账本 JSON 损坏，无法继续 - fail-closed",
            }, ensure_ascii=False))
            raise SystemExit(2)

        # Validate required fields
        for field in ("global_hard_cap", "slices_completed",
                      "calls_attempted_by_slice", "total_calls_attempted"):
            if field not in data:
                print(json.dumps({
                    "status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path, "error": f"缺少字段 {field}",
                    "reason": "账本结构不完整 - fail-closed",
                }, ensure_ascii=False))
                raise SystemExit(2)

        # allocated_cap_by_slice: 可选字段（旧 ledger 可能没有），默认空 dict
        if "allocated_cap_by_slice" not in data:
            data["allocated_cap_by_slice"] = {}

        # Validate global_hard_cap
        if data["global_hard_cap"] != GLOBAL_LEDGER_CAP:
            print(json.dumps({
                "status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"global_hard_cap={data['global_hard_cap']} != {GLOBAL_LEDGER_CAP}",
                "reason": "账本硬上限被篡改 - fail-closed",
            }, ensure_ascii=False))
            raise SystemExit(2)

        # Validate calls_attempted_by_slice
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

        # Validate total == sum(per_slice)
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

        # Validate allocated_cap_by_slice structure (6B1-D)
        allocated = data["allocated_cap_by_slice"]
        if not isinstance(allocated, dict):
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path, "error": "allocated_cap_by_slice 非 dict",
                "reason": "账本结构损坏 - fail-closed"}, ensure_ascii=False))
            raise SystemExit(2)
        for sid, cap in allocated.items():
            if not isinstance(cap, int) or cap < SLICE_BASE_CALLS or cap > SLICE_MAX_CAP:
                print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path,
                    "error": f"slice {sid} allocated_cap {cap!r} 不在 [{SLICE_BASE_CALLS}, {SLICE_MAX_CAP}]",
                    "reason": "allocated_cap 非法 - fail-closed"}, ensure_ascii=False))
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

        self._data["total_calls_attempted"] = sum(
            self._data["calls_attempted_by_slice"].values()
        )
        self._save()

    def budget_ok(self, remaining_scheduled: int) -> bool:
        return self.total_attempted + remaining_scheduled <= self.hard_cap

    def budget_ok_for_slice(self, slice_id: str, slice_hard_cap: int) -> bool:
        """Frozen formula:
        total_attempted + (slice_hard_cap - already_attempted_for_slice) <= 1320
        """
        already = self._data["calls_attempted_by_slice"].get(slice_id, 0)
        remaining_for_slice = max(0, slice_hard_cap - already)
        return self.total_attempted + remaining_for_slice <= self.hard_cap

    def record_calls_only(self, slice_id: str, calls: int) -> None:
        """Record calls consumed WITHOUT marking slice as completed."""
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
        """Validate ALL ledger slice IDs belong to schedule. Fail-closed.

        6B1-D 扩展: 同时校验 allocated_cap_by_slice 的 key 和与 manifest hard_cap 的一致性.
        """
        schedule_ids = {sl["slice_id"] for sl in schedule["slices"]}
        schedule_by_id = {sl["slice_id"]: sl for sl in schedule["slices"]}

        # 1. calls_attempted_by_slice 的 key 必须属于 schedule
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

        # 2. slices_completed 必须有对应调用记录
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

        # 3. slices_completed 的 key 必须属于 schedule
        unknown_completed = completed_set - schedule_ids
        if unknown_completed:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"slices_completed 含未知 slice ID: "
                         f"{sorted(unknown_completed)[:5]}",
                "reason": "completed slice 不在 schedule 中 - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)

        # 4. allocated_cap_by_slice 的 key 必须属于 schedule
        allocated_keys = set(self._data["allocated_cap_by_slice"].keys())
        unknown_allocated = allocated_keys - schedule_ids
        if unknown_allocated:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"allocated_cap_by_slice 含未知 slice ID: "
                         f"{sorted(unknown_allocated)[:5]}",
                "reason": "allocated_cap 含虚假 slice ID - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)

        # 5. allocated_cap 与 manifest hard_cap 一致性检查
        #    对于已有 manifest 的 slice, allocated_cap 必须等于 manifest hard_cap
        for sid, allocated_cap in self._data["allocated_cap_by_slice"].items():
            sl = schedule_by_id.get(sid)
            if sl is None:
                continue  # 已被第 4 步拦截
            manifest_path = sl.get("manifest_path")
            if manifest_path and os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        runner_manifest = json.load(f)
                    manifest_hard_cap = runner_manifest.get("hard_cap")
                    if manifest_hard_cap is not None and manifest_hard_cap != allocated_cap:
                        print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                            "path": self.path,
                            "error": f"slice {sid}: allocated_cap={allocated_cap} "
                                     f"!= manifest hard_cap={manifest_hard_cap}",
                            "reason": "allocated_cap 与 manifest hard_cap 不一致 - fail-closed"},
                            ensure_ascii=False))
                        raise SystemExit(2)
                except (json.JSONDecodeError, OSError):
                    # manifest 损坏由 verify_slice_manifest 处理，这里跳过
                    pass


# ---- effective cap helpers ----

def compute_effective_cap(slice_id: str, ledger: BudgetLedger,
                          already_attempted_for_slice: int) -> int:
    """首次启动分配 cap, 写入 BudgetLedger._data["allocated_cap_by_slice"].
    resume 从 ledger 读取, 不重新分配, 但必须执行全局预算公式检查.

    already_attempted_for_slice: 必须显式传入, 无默认值.
    来源: ledger._data["calls_attempted_by_slice"][slice_id] (经 events reconciliation).
    resume 前必须先完成 events -> ledger reconciliation, 再计算预算.
    """
    # 0. 验证 already_attempted_for_slice 已显式传入且合法
    if already_attempted_for_slice is None:
        raise SystemExit(2)
    if already_attempted_for_slice < 0:
        raise SystemExit(2)

    cumulative_calls = ledger._data["total_calls_attempted"]
    allocations = ledger._data.setdefault("allocated_cap_by_slice", {})

    # 1. resume 路径: 已有分配
    if slice_id in allocations:
        effective_cap = allocations[slice_id]
        if already_attempted_for_slice > effective_cap:
            raise SystemExit(2)
        # 执行冻结的 resume 预算公式:
        # total_attempted + (effective_cap - already_attempted) <= 1320
        remaining_budget = cumulative_calls + (effective_cap - already_attempted_for_slice)
        if remaining_budget > GLOBAL_LEDGER_CAP:
            print(json.dumps({"status": "BLOCKED_BUDGET_EXHAUSTED",
                             "slice_id": slice_id,
                             "cumulative_calls": cumulative_calls,
                             "effective_cap": effective_cap,
                             "already_attempted": already_attempted_for_slice,
                             "projected_total": remaining_budget},
                             ensure_ascii=False))
            raise SystemExit(2)
        return effective_cap

    # 2. 首次分配
    global_remaining = GLOBAL_LEDGER_CAP - cumulative_calls
    effective_cap = min(SLICE_MAX_CAP, global_remaining)

    if effective_cap < SLICE_BASE_CALLS:
        print(json.dumps({"status": "BLOCKED_BUDGET_EXHAUSTED",
                         "slice_id": slice_id,
                         "cumulative_calls": cumulative_calls,
                         "remaining": global_remaining},
                         ensure_ascii=False))
        raise SystemExit(2)

    # 3. 原子写入 BudgetLedger
    allocations[slice_id] = effective_cap
    ledger._save()
    return effective_cap


def verify_cap_consistency_on_resume(slice_id: str, runner_manifest: dict,
                                     ledger: BudgetLedger):
    """resume 时验证 ledger 分配值与 runner manifest hard_cap 一致.

    返回 ledger_cap (已分配的 cap), 供后续步骤使用.
    """
    ledger_cap = ledger._data.get("allocated_cap_by_slice", {}).get(slice_id)
    manifest_cap = runner_manifest.get("hard_cap")

    if ledger_cap is None and manifest_cap is None:
        return None  # 两者都无, 首跑
    if ledger_cap is None and manifest_cap is not None:
        raise SystemExit(2)  # runner manifest 存在但 ledger 缺失
    if ledger_cap is not None and manifest_cap is None:
        return ledger_cap  # ledger 有分配但 runner 无产物, 允许首跑
    if ledger_cap != manifest_cap:
        raise SystemExit(2)  # 两者不一致
    return ledger_cap


# ---- events helpers (复用 6B1) ----

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
                     hard_cap: int) -> tuple:
    """Validate events file: parseable, count within [scheduled_calls, hard_cap].
    Returns (ok, count, reason).
    """
    if not events_path or not os.path.exists(events_path):
        return False, 0, "events file missing"
    count = 0
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("kind") == "call_attempt":
                    count += 1
    except (json.JSONDecodeError, OSError) as e:
        return False, 0, f"events file corrupt: {e}"
    if count < scheduled_calls:
        return False, count, f"calls {count} < scheduled {scheduled_calls}"
    if count > hard_cap:
        return False, count, f"calls {count} > hard_cap {hard_cap}"
    return True, count, "ok"


def _validate_partial_events(events_path: str, allocated_cap: int) -> tuple:
    """Validate partial events: parseable, 1 <= count <= allocated_cap.
    Allows calls < scheduled_calls (partial resume).
    Rejects count == 0 (零调用 events 视为损坏, 合法零调用走 manifest-only 分支).
    Returns (ok, count, reason).
    """
    if not events_path or not os.path.exists(events_path):
        return False, 0, "events file missing"
    count = 0
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("kind") == "call_attempt":
                    count += 1
    except (json.JSONDecodeError, OSError) as e:
        return False, 0, f"events file corrupt: {e}"
    if count == 0:
        return False, 0, "events file exists but has 0 call_attempt (corrupt, use manifest-only branch for zero calls)"
    if count > allocated_cap:
        return False, count, f"calls {count} > allocated_cap {allocated_cap}"
    return True, count, "ok"


def reconcile_partial_events(sl: dict, ledger: BudgetLedger,
                             allocated_cap: int) -> int:
    """Partial resume 的证据回算 helper.

    用于崩溃后已产生部分调用的 slice (smoke 或普通 slice).
    与 verify_smoke_completed 不同, 本函数:
    - 允许调用数小于 scheduled_calls;
    - 不要求 details 完整、expected keys 完全相等、parser 8/8;
    - 不标记 slice 为 completed;
    - 只按 events 中的 call_attempt 回算 ledger.

    参数 allocated_cap: 从 ledger._data["allocated_cap_by_slice"] 读取的历史分配值
    (不是 compute_effective_cap 的返回值, 避免循环依赖).

    Manifest-only 状态处理 (events 不存在):
    - events 不存在时, 不调用 _validate_partial_events
    - 仅真正 manifest-only (manifest 存在、details 不存在、ledger 历史调用数为 0) 时返回 0
    - 若 details 已存在或 ledger 历史调用数非零, 说明调用证据丢失, BLOCKED_EVIDENCE_LOST
    """
    events_path = sl["events_path"]
    events_exists = os.path.exists(events_path)

    # 1. Manifest-only 状态严格判定 (events 不存在)
    if not events_exists:
        details_exists = os.path.exists(sl["detail_path"])
        ledger_calls = ledger._data["calls_attempted_by_slice"].get(sl["slice_id"], 0)

        # 仅当 details 不存在且 ledger 历史调用数为 0 时才是合法 manifest-only
        if details_exists or ledger_calls != 0:
            print(json.dumps({"status": "BLOCKED_EVIDENCE_LOST",
                             "slice_id": sl["slice_id"],
                             "reason": "events missing but details exists or ledger_calls non-zero",
                             "details_exists": details_exists,
                             "ledger_calls": ledger_calls},
                             ensure_ascii=False))
            raise SystemExit(2)

        # 真正的 manifest-only: 无证据可回算, already_attempted = 0
        return 0

    # 2. events 存在: 解析, 只统计 kind == "call_attempt"
    ok, calls, reason = _validate_partial_events(events_path, allocated_cap)
    if not ok:
        print(json.dumps({"status": "BLOCKED_PARTIAL_EVENTS_CORRUPT",
                         "slice_id": sl["slice_id"],
                         "reason": reason}, ensure_ascii=False))
        raise SystemExit(2)

    # 3. 事务式 ledger 回算 (先在副本上验证, 全部通过后一次性提交)
    new_calls_by_slice = dict(ledger._data["calls_attempted_by_slice"])
    new_calls_by_slice[sl["slice_id"]] = calls
    new_total = sum(new_calls_by_slice.values())

    # 4. 预算检查
    if new_total > ledger.hard_cap:
        print(json.dumps({"status": "BUDGET_EXCEEDED",
                         "slice_id": sl["slice_id"],
                         "new_total": new_total}, ensure_ascii=False))
        raise SystemExit(2)

    # 5. 全部验证通过, 一次性替换内存状态 (不加入 slices_completed)
    ledger._data["calls_attempted_by_slice"] = new_calls_by_slice
    ledger._data["total_calls_attempted"] = new_total
    ledger._save()

    return calls


# ---- smoke state machine ----

def determine_smoke_state(smoke_sl: dict) -> str:
    """直接复用 6B1 五状态判定逻辑.

    路径来源: schedule 中已冻结的 smoke_sl["detail_path"]/events_path/manifest_path.
    返回: fresh / resume / completed / blocked_corrupt
    """
    smoke_detail = Path(smoke_sl["detail_path"])
    smoke_manifest = Path(smoke_sl["manifest_path"])
    smoke_events = Path(smoke_sl["events_path"])

    detail_exists = smoke_detail.exists()
    manifest_exists = smoke_manifest.exists()
    events_exists = smoke_events.exists()

    # 1. 无任何产物 -> fresh
    if not detail_exists and not manifest_exists and not events_exists:
        return "fresh"

    # 2. detail + manifest 都存在 -> 检查终态数量
    if detail_exists and manifest_exists:
        rows = load_jsonl(str(smoke_detail))
        terminal_count = sum(
            1 for r in rows
            if r.get("terminal_state") in TERMINAL_STATES
        )
        if terminal_count >= smoke_sl["size"]:
            return "completed"
        else:
            return "resume"

    # 3. manifest 存在但 detail 不存在 -> 合法 resume (manifest-only)
    if manifest_exists and not detail_exists:
        return "resume"

    # 4. detail 存在但 manifest 不存在 -> blocked_corrupt
    if detail_exists and not manifest_exists:
        return "blocked_corrupt"

    # 5. 其他情况 -> blocked_corrupt
    return "blocked_corrupt"


def verify_smoke_completed(smoke_sl: dict, args, ledger: BudgetLedger):
    """completed 状态的完整验证, 直接复用 6B1 完整验证路径.
    验证成功后执行原子 ledger reconciliation.
    Returns (ok, reason).
    """
    smoke_detail = Path(smoke_sl["detail_path"])
    smoke_manifest = Path(smoke_sl["manifest_path"])
    smoke_events = Path(smoke_sl["events_path"])

    # 1. events 必须存在
    if not smoke_events.exists():
        return False, "completed state but events file missing"

    # 2. verify_slice_manifest 全字段指纹
    ok, diff = verify_slice_manifest(smoke_sl, args.provider, args.model)
    if not ok:
        return False, f"smoke manifest 与当前配置不一致: {diff}"

    # 3. expected attempt-key 集合完全相等
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

    # 4. details 数量 == expected 数量
    if len(detail_keys) != len(expected_keys):
        return False, f"details 数量不匹配: expected={len(expected_keys)} got={len(detail_keys)}"

    # 5. 无重复 attempt key
    if len(completed_keys) != len(detail_keys):
        return False, "存在重复 attempt key"

    # 6. completed keys == expected keys
    if completed_keys != expected_keys:
        return False, "completed keys != expected keys"

    # 7. parser rate (8 题 -> 8/8 = 100%)
    parse_ok = sum(1 for r in rows if r.get("terminal_state") == "parsed")
    parser_rate = parse_ok / len(rows) if rows else 0
    if parser_rate < SMOKE_PARSER_RATE_THRESHOLD:
        return False, f"parser_rate={parser_rate} < {SMOKE_PARSER_RATE_THRESHOLD}"

    # 8. events 可解析 + 调用数 ∈ [scheduled, hard_cap]
    ev_ok, calls, ev_reason = _validate_events(
        str(smoke_events), smoke_sl["size"], smoke_sl["hard_cap"])
    if not ev_ok:
        return False, f"events validation failed: {ev_reason}"

    # 9. 事务式 ledger reconciliation
    new_calls_by_slice = dict(ledger._data["calls_attempted_by_slice"])
    new_calls_by_slice[smoke_sl["slice_id"]] = calls
    new_total = sum(new_calls_by_slice.values())

    if new_total > ledger.hard_cap:
        return False, f"BUDGET_EXCEEDED after reconciliation: total={new_total}"
    if new_total != sum(new_calls_by_slice.values()):
        return False, f"ledger total mismatch: new_total={new_total}"

    ledger._data["calls_attempted_by_slice"] = new_calls_by_slice
    ledger._data["total_calls_attempted"] = new_total
    if smoke_sl["slice_id"] not in ledger._data["slices_completed"]:
        ledger._data["slices_completed"].append(smoke_sl["slice_id"])
    ledger._save()

    return True, "ok"


# ---- manifest verification (reuse runner's RESUME_MANIFEST_FIELDS) ----

def _build_current_manifest(sl: dict, provider: str, model: str) -> dict:
    """Build manifest dict matching runner's build_resume_manifest()."""
    from benchmark.runners.run_benchmark import _sha256_file, _code_fingerprint, RESUME_MANIFEST_FIELDS
    from benchmark.runners.profiles import prompt_fingerprint, resolve_profile

    profile = resolve_profile(REASONED_PROFILE, sl.get("chart_schema_version", CHART_SCHEMA))
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


def build_expected_key(dataset_id: str, profile_id: str, arm: str,
                       case_id: str, repeat_idx: int,
                       provider: str, model: str) -> tuple:
    """Build expected attempt key matching runner's 10-tuple format."""
    return (dataset_id, profile_id, arm, "main", provider, model,
            str(case_id), int(repeat_idx), 0, "p0")


def verify_slice_manifest(sl: dict, provider: str, model: str) -> tuple:
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


def generate_schedule(output_dir) -> dict:
    """Generate atomic 150-slice schedule with 5×5 Latin square.

    5 arms × 5 groups × 2 years × 3 repeats = 150 slices.
    每 slice 8 题, local cap 10, 全局 hard cap 1320.
    5×5 Latin square 全程交错, 每个 (year, repeat) 内 5 个 position 覆盖全部 5 arm.
    """
    output_dir = Path(output_dir)
    os.makedirs(str(output_dir), exist_ok=True)

    slices = []
    # Interleave: cycle positions across all (year, repeat) cells
    # to avoid temporal bias (spec §8.1)
    for position in range(GROUPS_PER_CELL):
        for year in YEARS:
            for repeat in REPEATS:
                for group in range(GROUPS_PER_CELL):
                    arm = LATIN_SQUARE[position][group]
                    size = SLICE_SIZE
                    ziwei_arm = ARM_ZIWEI_MAP[arm]
                    # slice_id format: {year}_{arm}_R{repeat}_P{position}_G{group}
                    slice_id = f"{year}_{arm}_R{repeat}_P{position}_G{group}"

                    case_start = group * SLICE_SIZE
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
                        "hard_cap": SLICE_MAX_CAP,
                        "case_start": case_start,
                        "case_end": case_end,
                        "output_dir": str(slice_dir),
                        "detail_path": str(slice_dir / detail_name),
                        "events_path": str(slice_dir / events_name),
                        "manifest_path": str(slice_dir / manifest_name),
                        "dataset": YEAR_DATASETS[year],
                        "chart_schema_version": CHART_SCHEMA,
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
        "experiment": EXPERIMENT_ID_PREFIX,
        "total_slices": len(slices),
        "total_scheduled_calls": sum(s["size"] for s in slices),
        "total_hard_cap": sum(s["hard_cap"] for s in slices),
        "global_hard_cap": GLOBAL_LEDGER_CAP,
        "frozen_date": FROZEN_DATE,
        "years": YEARS,
        "repeats": len(REPEATS),
        "arms": ARMS,
        "arm_ziwei_map": ARM_ZIWEI_MAP,
        "profile": REASONED_PROFILE,
        "chart_schema_version": CHART_SCHEMA,
        "latin_square": {str(k): v for k, v in LATIN_SQUARE.items()},
        "slice_layout": SLICE_LAYOUT,
        "groups_per_cell": GROUPS_PER_CELL,
        "slice_size": SLICE_SIZE,
        "slice_max_cap": SLICE_MAX_CAP,
        "slices": slices,
    }

    schedule_path = output_dir / "schedule.json"
    atomic_write_json(str(schedule_path), schedule)
    print(f"[schedule] {len(slices)} slices, {schedule['total_scheduled_calls']} calls "
          f"(hard_cap total={schedule['total_hard_cap']}) -> {schedule_path}")
    return schedule


def _generate_smoke_schedule(output_dir) -> list:
    """Generate 5 smoke slices (one per arm, 8 cases each from 2024 dataset).

    Smoke slices use first 8 cases from 2024 holdout, repeat=0.
    """
    output_dir = Path(output_dir)
    cases_2024 = load_jsonl(YEAR_DATASETS["2024"])
    smoke_cases = cases_2024[:SLICE_SIZE]
    smoke_case_ids = [c["case_id"] for c in smoke_cases]

    smoke_slices = []
    for arm in SMOKE_ARMS_ORDER:
        ziwei_arm = ARM_ZIWEI_MAP[arm]
        slice_id = f"smoke_{arm}"

        slice_dir = output_dir / f"slice_{slice_id}"
        detail_name = f"details_{slice_id}.jsonl"
        events_name = f"details_{slice_id}.events.jsonl"
        manifest_name = f"details_{slice_id}.manifest.json"

        smoke_slices.append({
            "slice_id": slice_id,
            "year": "2024",
            "repeat": 0,
            "arm": arm,
            "ziwei_arm": ziwei_arm,
            "group": 0,
            "position": 0,
            "size": SLICE_SIZE,
            "scheduled_calls": SLICE_SIZE,
            "hard_cap": SLICE_MAX_CAP,
            "case_start": 0,
            "case_end": SLICE_SIZE,
            "output_dir": str(slice_dir),
            "detail_path": str(slice_dir / detail_name),
            "events_path": str(slice_dir / events_name),
            "manifest_path": str(slice_dir / manifest_name),
            "dataset": YEAR_DATASETS["2024"],
            "case_ids": smoke_case_ids,
            "chart_schema_version": CHART_SCHEMA,
        })

    return smoke_slices


def _write_case_ids_file(sl: dict) -> str:
    """Write case_ids JSON file for runner --case-ids-file."""
    case_ids_file = os.path.join(sl["output_dir"], f"case_ids_{sl['slice_id']}.json")
    os.makedirs(sl["output_dir"], exist_ok=True)
    with open(case_ids_file, "w", encoding="utf-8") as f:
        json.dump(sl["case_ids"], f, ensure_ascii=False)
    return case_ids_file


def _build_runner_cmd(sl: dict, args, resume: bool = False) -> list:
    """Build runner subprocess command for a slice."""
    cmd = [
        sys.executable, "-m", "benchmark.runners.run_benchmark",
        "--profile", REASONED_PROFILE,
        "--chart-schema-version", sl.get("chart_schema_version", CHART_SCHEMA),
        "--arm", sl["arm"],
        "--ziwei-arm", sl["ziwei_arm"],
        "--attempt-stage", "main",
        "--repeat-idx", str(sl["repeat"]),
        "--case-details-jsonl", sl["detail_path"],
        "--case-ids-file", _write_case_ids_file(sl),
        "--provider", args.provider,
        "--model", args.model,
        "--method", "direct_choice",
        "--model-runner",
        "--n-samples", "1",
        "--temperature", "0",
        "--scheduled-calls", str(sl["size"]),
        "--hard-cap", str(sl["hard_cap"]),
        "--output-dir", sl["output_dir"],
        "--as-of-date", FROZEN_DATE,
    ]
    if resume:
        cmd.append("--resume")
    return cmd


def _run_slice(sl: dict, args, ledger: BudgetLedger,
               resume: bool = False) -> int:
    """Run a single slice via runner subprocess.

    Returns: 0=success, 2=config error, 3=budget exhausted, other=crash.
    """
    cmd = _build_runner_cmd(sl, args, resume=resume)

    clean_env = dict(os.environ)
    for var in ENV_CLEANUP:
        clean_env.pop(var, None)

    result = subprocess.run(cmd, capture_output=False, text=True, env=clean_env)

    calls_attempted = _count_call_attempts(sl["events_path"])

    if result.returncode == 0:
        ledger.record_slice_completed(sl["slice_id"], calls_attempted)
    else:
        ledger.record_calls_only(sl["slice_id"], calls_attempted)

    return result.returncode


def main(argv=None):
    """Main entry point for 6B1-D orchestrator.

    5 arms × 5 groups × 2 years × 3 repeats = 150 slices.
    5 smoke slices (one per arm) + 150 main slices.
    Dynamic effective_cap, BudgetLedger.allocated_cap_by_slice 权威.
    """
    parser = argparse.ArgumentParser(description="Phase 6 6B1-D orchestrator")
    parser.add_argument("--provider", default="deepseek", help="模型 provider")
    parser.add_argument("--model", default="deepseek-chat", help="模型名")
    parser.add_argument("--output-dir", default="benchmark/outputs/phase6_6b1d",
                        help="产物输出根目录")
    parser.add_argument("--dry-run", action="store_true", help="仅生成 schedule，不调 API")
    parser.add_argument("--from-slice", type=int, default=0,
                        help="从指定位置开始（smoke 之后的位置索引）")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    os.makedirs(str(output_dir), exist_ok=True)

    # 1. Generate schedule (150 slices)
    schedule = generate_schedule(output_dir)

    if schedule["total_scheduled_calls"] != TOTAL_SCHEDULED_CALLS:
        print(f"ERROR: expected {TOTAL_SCHEDULED_CALLS} scheduled calls, "
              f"got {schedule['total_scheduled_calls']}")
        raise SystemExit(1)

    if schedule["total_slices"] != TOTAL_SLICES:
        print(f"ERROR: expected {TOTAL_SLICES} slices, got {schedule['total_slices']}")
        raise SystemExit(1)

    ledger_path = str(output_dir / "budget_ledger.json")
    ledger = BudgetLedger(ledger_path)

    # 2. Dry-run: print schedule summary and exit
    if args.dry_run:
        print(f"\n[dry-run] schedule OK: {schedule['total_slices']} slices, "
              f"{schedule['total_scheduled_calls']} calls "
              f"(hard_cap total={schedule['total_hard_cap']})")
        print(f"[dry-run] arms: {ARMS}")
        print(f"[dry-run] years: {YEARS}")
        print(f"[dry-run] repeats: {REPEATS}")
        print(f"[dry-run] global hard cap: {GLOBAL_LEDGER_CAP}")
        print("[dry-run] Exiting without API calls.")
        return 0

    # 3. Validate ledger against schedule
    ledger.validate_against_schedule(schedule, args.provider, args.model)

    # 4. Smoke gate - 5 smoke slices (one per arm)
    print("\n=== SMOKE GATE (5 slices, one per arm) ===")
    smoke_slices = _generate_smoke_schedule(output_dir)

    for smoke_sl in smoke_slices:
        smoke_state = determine_smoke_state(smoke_sl)
        print(f"[smoke] {smoke_sl['slice_id']}: state={smoke_state}")

        if smoke_state == "blocked_corrupt":
            print(json.dumps({"status": "BLOCKED_SMOKE_CORRUPT",
                "slice_id": smoke_sl["slice_id"],
                "reason": "smoke 产物损坏，fail-closed"}, ensure_ascii=False))
            return 2

        if smoke_state == "completed":
            # 完整验证 + ledger reconciliation
            ok, reason = verify_smoke_completed(smoke_sl, args, ledger)
            if not ok:
                print(json.dumps({"status": "BLOCKED_SMOKE_VERIFY",
                    "slice_id": smoke_sl["slice_id"],
                    "reason": reason}, ensure_ascii=False))
                return 2
            print(f"[smoke] {smoke_sl['slice_id']}: PASS (completed, verified)")
            continue

        # fresh or resume: allocate cap, run slice
        # resume 路径: 先 reconcile, 再 compute_effective_cap
        allocated_cap = ledger._data["allocated_cap_by_slice"].get(smoke_sl["slice_id"])
        if allocated_cap is None:
            # fresh: 分配 cap
            effective_cap = compute_effective_cap(smoke_sl["slice_id"], ledger, 0)
        else:
            # resume: 先 reconcile_partial_events, 再 compute_effective_cap
            already = reconcile_partial_events(smoke_sl, ledger, allocated_cap)
            effective_cap = compute_effective_cap(smoke_sl["slice_id"], ledger, already)

        smoke_sl["hard_cap"] = effective_cap

        rc = _run_slice(smoke_sl, args, ledger,
                        resume=(smoke_state == "resume"))

        if rc == 2:
            print(json.dumps({"status": "BLOCKED_SMOKE_RUNNER_CONFIG",
                "slice_id": smoke_sl["slice_id"],
                "returncode": 2, "reason": "确定性错误，停止"}, ensure_ascii=False))
            return 2
        if rc == 3:
            print(json.dumps({"status": "BLOCKED_INCOMPLETE",
                "slice_id": smoke_sl["slice_id"],
                "returncode": 3, "reason": "hard cap 耗尽，停止"}, ensure_ascii=False))
            return 2
        if rc != 0:
            print(json.dumps({"status": "BLOCKED_SMOKE_CRASH",
                "slice_id": smoke_sl["slice_id"],
                "returncode": rc, "reason": "子进程崩溃，停止"}, ensure_ascii=False))
            return 2

        # Verify smoke completed successfully
        ok, reason = verify_smoke_completed(smoke_sl, args, ledger)
        if not ok:
            print(json.dumps({"status": "BLOCKED_SMOKE_VERIFY",
                "slice_id": smoke_sl["slice_id"],
                "reason": reason}, ensure_ascii=False))
            return 2
        print(f"[smoke] {smoke_sl['slice_id']}: PASS")

    print("[smoke] All 5 smoke slices passed.")

    # 5. Main loop - 150 slices
    print(f"\n=== MAIN LOOP ({schedule['total_slices']} slices) ===")
    smoke_ids = {s["slice_id"] for s in smoke_slices}

    for idx, sl in enumerate(schedule["slices"]):
        if sl["slice_id"] in smoke_ids:
            continue  # 跳过 smoke ID（如有重名）
        if idx < args.from_slice:
            continue

        # Budget pre-check
        if not ledger.budget_ok_for_slice(sl["slice_id"], sl["hard_cap"]):
            print(json.dumps({"status": "BUDGET_EXHAUSTED",
                "slice_id": sl["slice_id"],
                "total_attempted": ledger.total_attempted,
                "reason": "全局预算耗尽，停止"}, ensure_ascii=False))
            return 2

        print(f"[main] {idx}/{schedule['total_slices']} {sl['slice_id']} "
              f"(budget: {ledger.total_attempted}/{ledger.hard_cap})")

        # Allocate effective_cap
        allocated_cap = ledger._data["allocated_cap_by_slice"].get(sl["slice_id"])
        if allocated_cap is None:
            effective_cap = compute_effective_cap(sl["slice_id"], ledger, 0)
        else:
            already = reconcile_partial_events(sl, ledger, allocated_cap)
            effective_cap = compute_effective_cap(sl["slice_id"], ledger, already)

        sl["hard_cap"] = effective_cap

        rc = _run_slice(sl, args, ledger)

        if rc == 2:
            print(json.dumps({"status": "BLOCKED_RUNNER_CONFIG",
                "slice_id": sl["slice_id"], "returncode": 2,
                "reason": "确定性错误，停止"}, ensure_ascii=False))
            return 2
        if rc == 3:
            print(json.dumps({"status": "BLOCKED_INCOMPLETE",
                "slice_id": sl["slice_id"], "returncode": 3,
                "reason": "hard cap 耗尽，继续下个 slice"}))
            continue
        if rc != 0:
            print(json.dumps({"status": "BLOCKED_SLICE_CRASH",
                "slice_id": sl["slice_id"], "returncode": rc,
                "reason": "子进程崩溃，停止"}, ensure_ascii=False))
            return 2

    print(f"\n=== COMPLETE: {ledger.total_attempted}/{ledger.hard_cap} calls ===")
    return 0


if __name__ == "__main__":
    main()
