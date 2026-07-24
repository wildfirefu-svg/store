"""Phase 6 6B1-D 专项测试 - BudgetLedger schema + resume/Smoke helpers.

覆盖:
  - BudgetLedger: allocated_cap_by_slice schema, 加载校验, fail-closed
  - compute_effective_cap: 首次分配, resume 预算公式, 边界
  - verify_cap_consistency_on_resume: ledger/manifest 一致性
  - reconcile_partial_events: partial resume, manifest-only, evidence lost
  - determine_smoke_state: 五状态判定
  - verify_smoke_completed: 完整证据验证 + ledger reconciliation
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.phase6_6b1d_orchestrator import (
    BudgetLedger,
    compute_effective_cap,
    verify_cap_consistency_on_resume,
    reconcile_partial_events,
    determine_smoke_state,
    _validate_partial_events,
    _validate_events,
    _count_call_attempts,
    generate_schedule,
    _generate_smoke_schedule,
    build_expected_key,
    GLOBAL_LEDGER_CAP,
    SLICE_BASE_CALLS,
    SLICE_MAX_CAP,
    SLICE_SIZE,
    TERMINAL_STATES,
    SMOKE_PARSER_RATE_THRESHOLD,
    ARM_ZIWEI_MAP,
    LATIN_SQUARE,
    SLICE_LAYOUT,
    ARMS,
    YEARS,
    REPEATS,
    TOTAL_SLICES,
    TOTAL_SCHEDULED_CALLS,
    GROUPS_PER_CELL,
)


# ---- fixtures ----

@pytest.fixture
def tmp_ledger(tmp_path):
    """Create a fresh BudgetLedger in tmp_path."""
    ledger_path = str(tmp_path / "budget_ledger.json")
    return BudgetLedger(ledger_path)


@pytest.fixture
def tmp_ledger_path(tmp_path):
    return str(tmp_path / "budget_ledger.json")


def make_slice(slice_id="slice_001", detail_path=None, events_path=None,
               manifest_path=None, size=8, hard_cap=10, case_ids=None,
               arm="b1a_prime", repeat=0, dataset="ds"):
    """Create a slice dict for testing."""
    return {
        "slice_id": slice_id,
        "detail_path": detail_path or f"/tmp/{slice_id}/details.jsonl",
        "events_path": events_path or f"/tmp/{slice_id}/details.events.jsonl",
        "manifest_path": manifest_path or f"/tmp/{slice_id}/details.manifest.json",
        "size": size,
        "hard_cap": hard_cap,
        "case_ids": case_ids or ["case_1", "case_2"],
        "arm": arm,
        "repeat": repeat,
        "dataset": dataset,
    }


# ---- TDD 1: BudgetLedger schema tests ----

class TestBudgetLedgerSchema:
    """Test allocated_cap_by_slice schema extension and load validation."""

    def test_fresh_ledger_has_allocated_cap_by_slice(self, tmp_ledger):
        """新 ledger 必须包含 allocated_cap_by_slice 字段, 默认空 dict."""
        assert "allocated_cap_by_slice" in tmp_ledger._data
        assert tmp_ledger._data["allocated_cap_by_slice"] == {}

    def test_fresh_ledger_global_hard_cap_is_1320(self, tmp_ledger):
        """新 ledger 的 global_hard_cap 必须是 1320."""
        assert tmp_ledger._data["global_hard_cap"] == GLOBAL_LEDGER_CAP
        assert tmp_ledger._data["global_hard_cap"] == 1320

    def test_load_existing_ledger_without_allocated_cap(self, tmp_ledger_path):
        """旧 ledger (无 allocated_cap_by_slice) 应自动补默认空 dict."""
        # 写一个旧格式 ledger
        old_data = {
            "global_hard_cap": GLOBAL_LEDGER_CAP,
            "slices_completed": [],
            "calls_attempted_by_slice": {},
            "total_calls_attempted": 0,
        }
        with open(tmp_ledger_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f)
        # 加载
        ledger = BudgetLedger(tmp_ledger_path)
        assert ledger._data["allocated_cap_by_slice"] == {}

    def test_load_ledger_allocated_cap_not_dict_fail_closed(self, tmp_ledger_path):
        """allocated_cap_by_slice 非 dict 时 fail-closed."""
        data = {
            "global_hard_cap": GLOBAL_LEDGER_CAP,
            "slices_completed": [],
            "calls_attempted_by_slice": {},
            "total_calls_attempted": 0,
            "allocated_cap_by_slice": "not_a_dict",
        }
        with open(tmp_ledger_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with pytest.raises(SystemExit) as exc_info:
            BudgetLedger(tmp_ledger_path)
        assert exc_info.value.code == 2

    def test_load_ledger_allocated_cap_below_min_fail_closed(self, tmp_ledger_path):
        """allocated_cap < SLICE_BASE_CALLS 时 fail-closed."""
        data = {
            "global_hard_cap": GLOBAL_LEDGER_CAP,
            "slices_completed": [],
            "calls_attempted_by_slice": {},
            "total_calls_attempted": 0,
            "allocated_cap_by_slice": {"slice_001": SLICE_BASE_CALLS - 1},
        }
        with open(tmp_ledger_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with pytest.raises(SystemExit) as exc_info:
            BudgetLedger(tmp_ledger_path)
        assert exc_info.value.code == 2

    def test_load_ledger_allocated_cap_above_max_fail_closed(self, tmp_ledger_path):
        """allocated_cap > SLICE_MAX_CAP 时 fail-closed."""
        data = {
            "global_hard_cap": GLOBAL_LEDGER_CAP,
            "slices_completed": [],
            "calls_attempted_by_slice": {},
            "total_calls_attempted": 0,
            "allocated_cap_by_slice": {"slice_001": SLICE_MAX_CAP + 1},
        }
        with open(tmp_ledger_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with pytest.raises(SystemExit) as exc_info:
            BudgetLedger(tmp_ledger_path)
        assert exc_info.value.code == 2

    def test_load_ledger_allocated_cap_non_int_fail_closed(self, tmp_ledger_path):
        """allocated_cap 非整数时 fail-closed."""
        data = {
            "global_hard_cap": GLOBAL_LEDGER_CAP,
            "slices_completed": [],
            "calls_attempted_by_slice": {},
            "total_calls_attempted": 0,
            "allocated_cap_by_slice": {"slice_001": "ten"},
        }
        with open(tmp_ledger_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with pytest.raises(SystemExit) as exc_info:
            BudgetLedger(tmp_ledger_path)
        assert exc_info.value.code == 2

    def test_save_persists_allocated_cap(self, tmp_ledger):
        """_save() 必须持久化 allocated_cap_by_slice."""
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        tmp_ledger._save()
        # 重新加载
        ledger2 = BudgetLedger(tmp_ledger.path)
        assert ledger2._data["allocated_cap_by_slice"]["slice_001"] == SLICE_MAX_CAP


# ---- TDD 1b: validate_against_schedule allocated_cap tests ----

class TestValidateAgainstScheduleAllocatedCap:
    """Test validate_against_schedule checks allocated_cap_by_slice keys and
    manifest hard_cap consistency."""

    def test_unknown_allocated_key_rejected(self, tmp_ledger, tmp_path):
        """allocated_cap_by_slice 含未知 slice ID 时 fail-closed."""
        tmp_ledger._data["allocated_cap_by_slice"]["fake_slice"] = SLICE_MAX_CAP
        tmp_ledger._save()
        schedule = {"slices": [{"slice_id": "slice_001", "manifest_path": str(tmp_path / "m.json")}]}
        with pytest.raises(SystemExit) as exc_info:
            tmp_ledger.validate_against_schedule(schedule, "deepseek", "deepseek-chat")
        assert exc_info.value.code == 2

    def test_allocated_key_in_schedule_passes(self, tmp_ledger, tmp_path):
        """allocated_cap_by_slice 的 key 属于 schedule 时通过."""
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        tmp_ledger._save()
        schedule = {"slices": [{"slice_id": "slice_001", "manifest_path": str(tmp_path / "m.json")}]}
        # 不应抛异常
        tmp_ledger.validate_against_schedule(schedule, "deepseek", "deepseek-chat")

    def test_allocated_cap_mismatch_with_manifest_rejected(self, tmp_ledger, tmp_path):
        """allocated_cap 与 manifest hard_cap 不一致时 fail-closed."""
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        tmp_ledger._save()
        # 创建 manifest, hard_cap 不一致
        manifest_path = tmp_path / "m.json"
        manifest_path.write_text(json.dumps({"hard_cap": SLICE_MAX_CAP - 1}), encoding="utf-8")
        schedule = {"slices": [{"slice_id": "slice_001", "manifest_path": str(manifest_path)}]}
        with pytest.raises(SystemExit) as exc_info:
            tmp_ledger.validate_against_schedule(schedule, "deepseek", "deepseek-chat")
        assert exc_info.value.code == 2

    def test_allocated_cap_matches_manifest_passes(self, tmp_ledger, tmp_path):
        """allocated_cap 与 manifest hard_cap 一致时通过."""
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        tmp_ledger._save()
        manifest_path = tmp_path / "m.json"
        manifest_path.write_text(json.dumps({"hard_cap": SLICE_MAX_CAP}), encoding="utf-8")
        schedule = {"slices": [{"slice_id": "slice_001", "manifest_path": str(manifest_path)}]}
        tmp_ledger.validate_against_schedule(schedule, "deepseek", "deepseek-chat")


# ---- TDD 2a: compute_effective_cap tests ----

class TestComputeEffectiveCap:
    """Test compute_effective_cap: 首次分配, resume 预算公式, 边界."""

    def test_first_allocation_writes_to_ledger(self, tmp_ledger):
        """首次分配: 写入 allocated_cap_by_slice, 返回 SLICE_MAX_CAP."""
        cap = compute_effective_cap("slice_001", tmp_ledger, 0)
        assert cap == SLICE_MAX_CAP
        assert tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] == SLICE_MAX_CAP

    def test_first_allocation_persists_to_disk(self, tmp_ledger):
        """首次分配必须持久化到磁盘."""
        compute_effective_cap("slice_001", tmp_ledger, 0)
        ledger2 = BudgetLedger(tmp_ledger.path)
        assert ledger2._data["allocated_cap_by_slice"]["slice_001"] == SLICE_MAX_CAP

    def test_resume_uses_historical_allocation(self, tmp_ledger):
        """resume: 从 ledger 读取历史分配, 不重新分配."""
        # 首次分配
        compute_effective_cap("slice_001", tmp_ledger, 0)
        first_cap = tmp_ledger._data["allocated_cap_by_slice"]["slice_001"]
        # resume: already_attempted=4
        cap = compute_effective_cap("slice_001", tmp_ledger, 4)
        assert cap == first_cap  # 沿用历史分配

    def test_resume_rejects_already_attempted_none(self, tmp_ledger):
        """already_attempted is None 时 SystemExit(2)."""
        compute_effective_cap("slice_001", tmp_ledger, 0)
        with pytest.raises(SystemExit) as exc_info:
            compute_effective_cap("slice_001", tmp_ledger, None)
        assert exc_info.value.code == 2

    def test_resume_rejects_already_attempted_negative(self, tmp_ledger):
        """already_attempted < 0 时 SystemExit(2)."""
        compute_effective_cap("slice_001", tmp_ledger, 0)
        with pytest.raises(SystemExit) as exc_info:
            compute_effective_cap("slice_001", tmp_ledger, -1)
        assert exc_info.value.code == 2

    def test_resume_rejects_already_attempted_above_cap(self, tmp_ledger):
        """already_attempted > effective_cap 时 SystemExit(2)."""
        compute_effective_cap("slice_001", tmp_ledger, 0)
        cap = tmp_ledger._data["allocated_cap_by_slice"]["slice_001"]
        with pytest.raises(SystemExit) as exc_info:
            compute_effective_cap("slice_001", tmp_ledger, cap + 1)
        assert exc_info.value.code == 2

    def test_resume_rejects_when_budget_exhausted(self, tmp_ledger):
        """resume 预算公式: total + (cap - already) > 1320 时 BLOCKED_BUDGET_EXHAUSTED."""
        # 模拟累计调用接近上限
        tmp_ledger._data["total_calls_attempted"] = GLOBAL_LEDGER_CAP - 5
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        # already=0 -> projected = (1320-5) + (10-0) = 1325 > 1320
        with pytest.raises(SystemExit) as exc_info:
            compute_effective_cap("slice_001", tmp_ledger, 0)
        assert exc_info.value.code == 2

    def test_resume_allows_when_budget_sufficient(self, tmp_ledger):
        """resume 预算公式: total + (cap - already) <= 1320 时通过."""
        tmp_ledger._data["total_calls_attempted"] = GLOBAL_LEDGER_CAP - 15
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        # already=0 -> projected = (1320-15) + (10-0) = 1315 <= 1320
        cap = compute_effective_cap("slice_001", tmp_ledger, 0)
        assert cap == SLICE_MAX_CAP

    def test_first_allocation_rejects_when_exhausted(self, tmp_ledger):
        """首次分配: global_remaining < SLICE_BASE_CALLS 时 BLOCKED_BUDGET_EXHAUSTED."""
        tmp_ledger._data["total_calls_attempted"] = GLOBAL_LEDGER_CAP - 3
        with pytest.raises(SystemExit) as exc_info:
            compute_effective_cap("slice_001", tmp_ledger, 0)
        assert exc_info.value.code == 2

    def test_missing_third_param_type_error(self, tmp_ledger):
        """缺少第 3 个参数时 TypeError (强制显式传入)."""
        with pytest.raises(TypeError):
            compute_effective_cap("slice_001", tmp_ledger)


# ---- TDD 2b: verify_cap_consistency_on_resume tests ----

class TestVerifyCapConsistency:
    """Test verify_cap_consistency_on_resume: ledger/manifest 一致性."""

    def test_both_none_returns_none(self, tmp_ledger):
        """两者都无 -> 首跑, 返回 None."""
        result = verify_cap_consistency_on_resume(
            "slice_001", {}, tmp_ledger)
        assert result is None

    def test_ledger_none_manifest_exists_fail_closed(self, tmp_ledger):
        """runner manifest 存在但 ledger 缺失 -> fail-closed."""
        manifest = {"hard_cap": 10}
        with pytest.raises(SystemExit) as exc_info:
            verify_cap_consistency_on_resume(
                "slice_001", manifest, tmp_ledger)
        assert exc_info.value.code == 2

    def test_ledger_exists_manifest_none_allows_first_run(self, tmp_ledger):
        """ledger 有分配但 runner 无产物 -> 允许首跑, 返回 ledger_cap."""
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        result = verify_cap_consistency_on_resume(
            "slice_001", {}, tmp_ledger)
        assert result == SLICE_MAX_CAP

    def test_both_consistent_returns_ledger_cap(self, tmp_ledger):
        """两者一致 -> 返回 ledger_cap."""
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        manifest = {"hard_cap": SLICE_MAX_CAP}
        result = verify_cap_consistency_on_resume(
            "slice_001", manifest, tmp_ledger)
        assert result == SLICE_MAX_CAP

    def test_inconsistent_fail_closed(self, tmp_ledger):
        """两者不一致 -> fail-closed."""
        tmp_ledger._data["allocated_cap_by_slice"]["slice_001"] = SLICE_MAX_CAP
        manifest = {"hard_cap": SLICE_MAX_CAP - 1}
        with pytest.raises(SystemExit) as exc_info:
            verify_cap_consistency_on_resume(
                "slice_001", manifest, tmp_ledger)
        assert exc_info.value.code == 2


# ---- TDD 2c: reconcile_partial_events tests ----

class TestReconcilePartialEvents:
    """Test reconcile_partial_events: partial resume, manifest-only, evidence lost."""

    def test_manifest_only_legitimate_returns_zero(self, tmp_ledger, tmp_path):
        """manifest-only + details 不存在 + ledger=0 -> 合法, 返回 0."""
        # 创建 manifest 但不创建 details/events
        manifest_path = tmp_path / "details.manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        sl = make_slice(
            detail_path=str(tmp_path / "details.jsonl"),
            events_path=str(tmp_path / "details.events.jsonl"),
            manifest_path=str(manifest_path),
        )
        result = reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        assert result == 0

    def test_manifest_only_with_details_blocks(self, tmp_ledger, tmp_path):
        """manifest + partial details + events 缺失 -> BLOCKED_EVIDENCE_LOST."""
        manifest_path = tmp_path / "details.manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        detail_path = tmp_path / "details.jsonl"
        detail_path.write_text('{"attempt_key": ["a"]}', encoding="utf-8")
        sl = make_slice(
            detail_path=str(detail_path),
            events_path=str(tmp_path / "details.events.jsonl"),
            manifest_path=str(manifest_path),
        )
        with pytest.raises(SystemExit) as exc_info:
            reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        assert exc_info.value.code == 2

    def test_manifest_only_with_ledger_nonzero_blocks(self, tmp_ledger, tmp_path):
        """manifest-only + ledger 非零 -> BLOCKED_EVIDENCE_LOST."""
        manifest_path = tmp_path / "details.manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        # 设置 ledger 调用数为非零
        tmp_ledger._data["calls_attempted_by_slice"]["slice_001"] = 5
        sl = make_slice(
            slice_id="slice_001",
            detail_path=str(tmp_path / "details.jsonl"),
            events_path=str(tmp_path / "details.events.jsonl"),
            manifest_path=str(manifest_path),
        )
        with pytest.raises(SystemExit) as exc_info:
            reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        assert exc_info.value.code == 2

    def test_events_deleted_after_existence_blocks(self, tmp_ledger, tmp_path):
        """events 曾存在后被删除 (details 存在或 ledger 非零) -> BLOCKED_EVIDENCE_LOST."""
        manifest_path = tmp_path / "details.manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        detail_path = tmp_path / "details.jsonl"
        detail_path.write_text('{"attempt_key": ["a"]}', encoding="utf-8")
        tmp_ledger._data["calls_attempted_by_slice"]["slice_001"] = 3
        sl = make_slice(
            slice_id="slice_001",
            detail_path=str(detail_path),
            events_path=str(tmp_path / "details.events.jsonl"),  # 不存在
            manifest_path=str(manifest_path),
        )
        with pytest.raises(SystemExit) as exc_info:
            reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        assert exc_info.value.code == 2

    def test_partial_events_reconciles_ledger(self, tmp_ledger, tmp_path):
        """崩溃后部分调用 (calls < scheduled) 正确回算 ledger."""
        events_path = tmp_path / "details.events.jsonl"
        # 写 3 个 call_attempt events (小于 scheduled=8)
        with open(events_path, "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"kind": "call_attempt", "idx": i}) + "\n")
        sl = make_slice(
            events_path=str(events_path),
            detail_path=str(tmp_path / "details.jsonl"),
            manifest_path=str(tmp_path / "details.manifest.json"),
        )
        result = reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        assert result == 3
        assert tmp_ledger._data["calls_attempted_by_slice"]["slice_001"] == 3
        assert tmp_ledger._data["total_calls_attempted"] == 3

    def test_partial_events_does_not_mark_completed(self, tmp_ledger, tmp_path):
        """回算后不标记 slice 为 completed."""
        events_path = tmp_path / "details.events.jsonl"
        with open(events_path, "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"kind": "call_attempt", "idx": i}) + "\n")
        sl = make_slice(
            events_path=str(events_path),
            detail_path=str(tmp_path / "details.jsonl"),
            manifest_path=str(tmp_path / "details.manifest.json"),
        )
        reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        assert "slice_001" not in tmp_ledger._data["slices_completed"]

    def test_partial_events_corrupt_jsonl_blocks(self, tmp_ledger, tmp_path):
        """损坏 JSONL 时 SystemExit(2)."""
        events_path = tmp_path / "details.events.jsonl"
        events_path.write_text("not valid json\n", encoding="utf-8")
        sl = make_slice(
            events_path=str(events_path),
            detail_path=str(tmp_path / "details.jsonl"),
            manifest_path=str(tmp_path / "details.manifest.json"),
        )
        with pytest.raises(SystemExit) as exc_info:
            reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        assert exc_info.value.code == 2

    def test_partial_events_exceeds_cap_blocks(self, tmp_ledger, tmp_path):
        """calls > allocated_cap 时 SystemExit(2)."""
        events_path = tmp_path / "details.events.jsonl"
        # 写 11 个 call_attempt (超过 allocated_cap=10)
        with open(events_path, "w", encoding="utf-8") as f:
            for i in range(11):
                f.write(json.dumps({"kind": "call_attempt", "idx": i}) + "\n")
        sl = make_slice(
            events_path=str(events_path),
            detail_path=str(tmp_path / "details.jsonl"),
            manifest_path=str(tmp_path / "details.manifest.json"),
        )
        with pytest.raises(SystemExit) as exc_info:
            reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        assert exc_info.value.code == 2

    def test_partial_events_total_equals_sum(self, tmp_ledger, tmp_path):
        """回算后 total == 各 slice 之和."""
        events_path = tmp_path / "details.events.jsonl"
        with open(events_path, "w", encoding="utf-8") as f:
            for i in range(5):
                f.write(json.dumps({"kind": "call_attempt", "idx": i}) + "\n")
        sl = make_slice(
            events_path=str(events_path),
            detail_path=str(tmp_path / "details.jsonl"),
            manifest_path=str(tmp_path / "details.manifest.json"),
        )
        reconcile_partial_events(sl, tmp_ledger, SLICE_MAX_CAP)
        recomputed = sum(tmp_ledger._data["calls_attempted_by_slice"].values())
        assert recomputed == tmp_ledger._data["total_calls_attempted"]


# ---- TDD 2d: determine_smoke_state tests ----

class TestDetermineSmokeState:
    """Test determine_smoke_state: 五状态判定."""

    def test_fresh_no_artifacts(self, tmp_path):
        """无任何产物 -> fresh."""
        sl = make_slice(
            detail_path=str(tmp_path / "d.jsonl"),
            events_path=str(tmp_path / "e.jsonl"),
            manifest_path=str(tmp_path / "m.json"),
        )
        assert determine_smoke_state(sl) == "fresh"

    def test_resume_manifest_only(self, tmp_path):
        """manifest 存在但 detail 不存在 -> 合法 resume."""
        manifest_path = tmp_path / "m.json"
        manifest_path.write_text("{}", encoding="utf-8")
        sl = make_slice(
            detail_path=str(tmp_path / "d.jsonl"),  # 不存在
            events_path=str(tmp_path / "e.jsonl"),
            manifest_path=str(manifest_path),
        )
        assert determine_smoke_state(sl) == "resume"

    def test_completed_detail_manifest_full(self, tmp_path):
        """detail + manifest 都存在, 终态数 >= size -> completed."""
        manifest_path = tmp_path / "m.json"
        manifest_path.write_text("{}", encoding="utf-8")
        detail_path = tmp_path / "d.jsonl"
        with open(detail_path, "w", encoding="utf-8") as f:
            for i in range(8):
                f.write(json.dumps({"terminal_state": "parsed"}) + "\n")
        sl = make_slice(
            detail_path=str(detail_path),
            events_path=str(tmp_path / "e.jsonl"),
            manifest_path=str(manifest_path),
            size=8,
        )
        assert determine_smoke_state(sl) == "completed"

    def test_resume_detail_manifest_partial(self, tmp_path):
        """detail + manifest 都存在, 终态数 < size -> resume."""
        manifest_path = tmp_path / "m.json"
        manifest_path.write_text("{}", encoding="utf-8")
        detail_path = tmp_path / "d.jsonl"
        with open(detail_path, "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"terminal_state": "parsed"}) + "\n")
        sl = make_slice(
            detail_path=str(detail_path),
            events_path=str(tmp_path / "e.jsonl"),
            manifest_path=str(manifest_path),
            size=8,
        )
        assert determine_smoke_state(sl) == "resume"

    def test_blocked_corrupt_detail_no_manifest(self, tmp_path):
        """detail 存在但 manifest 不存在 -> blocked_corrupt."""
        detail_path = tmp_path / "d.jsonl"
        detail_path.write_text('{"terminal_state": "parsed"}', encoding="utf-8")
        sl = make_slice(
            detail_path=str(detail_path),
            events_path=str(tmp_path / "e.jsonl"),
            manifest_path=str(tmp_path / "m.json"),  # 不存在
        )
        assert determine_smoke_state(sl) == "blocked_corrupt"


# ---- TDD 2e: _validate_partial_events and _validate_events helpers ----

class TestValidateHelpers:
    """Test _validate_partial_events and _validate_events helpers."""

    def test_validate_partial_events_missing_file(self):
        """events 不存在 -> (False, 0, 'events file missing')."""
        ok, count, reason = _validate_partial_events("/nonexistent/path", 10)
        assert ok is False
        assert count == 0

    def test_validate_partial_events_corrupt_json(self, tmp_path):
        """损坏 JSON -> (False, 0, reason contains 'corrupt')."""
        p = tmp_path / "e.jsonl"
        p.write_text("not json\n", encoding="utf-8")
        ok, count, reason = _validate_partial_events(str(p), 10)
        assert ok is False

    def test_validate_partial_events_exceeds_cap(self, tmp_path):
        """calls > allocated_cap -> (False, count, reason)."""
        p = tmp_path / "e.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for i in range(11):
                f.write(json.dumps({"kind": "call_attempt"}) + "\n")
        ok, count, reason = _validate_partial_events(str(p), 10)
        assert ok is False
        assert count == 11

    def test_validate_partial_events_allows_below_scheduled(self, tmp_path):
        """calls < scheduled_calls -> 允许 (ok=True)."""
        p = tmp_path / "e.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"kind": "call_attempt"}) + "\n")
        ok, count, reason = _validate_partial_events(str(p), 10)
        assert ok is True
        assert count == 3

    def test_validate_partial_events_rejects_zero_call_attempts(self, tmp_path):
        """events 存在但 0 个 call_attempt -> 视为损坏 (合法零调用走 manifest-only)."""
        p = tmp_path / "e.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            # 写入非 call_attempt events
            f.write(json.dumps({"kind": "parse_result"}) + "\n")
            f.write(json.dumps({"kind": "other"}) + "\n")
        ok, count, reason = _validate_partial_events(str(p), 10)
        assert ok is False
        assert count == 0

    def test_validate_partial_events_rejects_empty_file(self, tmp_path):
        """空 events 文件 -> 视为损坏."""
        p = tmp_path / "e.jsonl"
        p.write_text("", encoding="utf-8")
        ok, count, reason = _validate_partial_events(str(p), 10)
        assert ok is False
        assert count == 0

    def test_count_call_attempts_only_counts_call_attempt_kind(self, tmp_path):
        """_count_call_attempts 只统计 kind == 'call_attempt'."""
        p = tmp_path / "e.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "call_attempt"}) + "\n")
            f.write(json.dumps({"kind": "parse_result"}) + "\n")
            f.write(json.dumps({"kind": "call_attempt"}) + "\n")
        assert _count_call_attempts(str(p)) == 2

    def test_count_call_attempts_missing_file_returns_zero(self):
        """文件不存在 -> 0."""
        assert _count_call_attempts("/nonexistent") == 0


# ---- TDD 6a: generate_schedule tests ----

class TestGenerateSchedule:
    """Test generate_schedule: 150 slices, 5×5 Latin square, 1200 calls."""

    def test_schedule_has_150_slices(self, tmp_path):
        """schedule 必须包含 150 slices."""
        schedule = generate_schedule(tmp_path)
        assert schedule["total_slices"] == TOTAL_SLICES
        assert schedule["total_slices"] == 150

    def test_schedule_has_1200_scheduled_calls(self, tmp_path):
        """schedule 必须包含 1200 scheduled calls."""
        schedule = generate_schedule(tmp_path)
        assert schedule["total_scheduled_calls"] == TOTAL_SCHEDULED_CALLS
        assert schedule["total_scheduled_calls"] == 1200

    def test_schedule_global_hard_cap_is_1320(self, tmp_path):
        """schedule 的 global_hard_cap 必须是 1320."""
        schedule = generate_schedule(tmp_path)
        assert schedule["global_hard_cap"] == GLOBAL_LEDGER_CAP

    def test_schedule_has_5_arms(self, tmp_path):
        """schedule 必须包含 5 arms."""
        schedule = generate_schedule(tmp_path)
        assert set(schedule["arms"]) == set(ARMS)
        assert len(schedule["arms"]) == 5

    def test_schedule_has_2_years(self, tmp_path):
        """schedule 必须包含 2 years."""
        schedule = generate_schedule(tmp_path)
        assert set(schedule["years"]) == set(YEARS)

    def test_schedule_has_3_repeats(self, tmp_path):
        """schedule 必须包含 3 repeats."""
        schedule = generate_schedule(tmp_path)
        assert schedule["repeats"] == len(REPEATS)

    def test_each_slice_has_8_cases(self, tmp_path):
        """每个 slice 必须有 8 个 case_ids."""
        schedule = generate_schedule(tmp_path)
        for sl in schedule["slices"]:
            assert len(sl["case_ids"]) == SLICE_SIZE, \
                f"slice {sl['slice_id']} case count != 8"

    def test_each_slice_hard_cap_is_10(self, tmp_path):
        """每个 slice 的 hard_cap 必须是 10."""
        schedule = generate_schedule(tmp_path)
        for sl in schedule["slices"]:
            assert sl["hard_cap"] == SLICE_MAX_CAP

    def test_latin_square_coverage(self, tmp_path):
        """每个 (year, repeat) cell 内 5 个 position 覆盖全部 5 arm."""
        schedule = generate_schedule(tmp_path)
        from collections import defaultdict
        cell_arms = defaultdict(set)
        for sl in schedule["slices"]:
            key = (sl["year"], sl["repeat"])
            cell_arms[key].add(sl["arm"])
        # 每个 cell 必须覆盖全部 5 arm
        for key, arms in cell_arms.items():
            assert arms == set(ARMS), \
                f"cell {key} arms coverage incomplete: {arms}"

    def test_latin_square_no_duplicate_slice_ids(self, tmp_path):
        """所有 slice_id 必须唯一."""
        schedule = generate_schedule(tmp_path)
        slice_ids = [sl["slice_id"] for sl in schedule["slices"]]
        assert len(slice_ids) == len(set(slice_ids)), "存在重复 slice_id"

    def test_schedule_json_written_to_disk(self, tmp_path):
        """schedule.json 必须写入磁盘."""
        schedule = generate_schedule(tmp_path)
        schedule_path = tmp_path / "schedule.json"
        assert schedule_path.exists()
        with open(schedule_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["total_slices"] == 150

    def test_slice_paths_are_distinct(self, tmp_path):
        """每个 slice 的 detail_path 必须不同."""
        schedule = generate_schedule(tmp_path)
        paths = [sl["detail_path"] for sl in schedule["slices"]]
        assert len(paths) == len(set(paths)), "存在重复 detail_path"

    def test_slice_case_ids_cover_40_per_year(self, tmp_path):
        """每年 40 题, 5 groups × 8 = 40, 每个 (year, repeat) 覆盖全部 40 题."""
        schedule = generate_schedule(tmp_path)
        from collections import defaultdict
        cell_cases = defaultdict(set)
        for sl in schedule["slices"]:
            key = (sl["year"], sl["repeat"])
            cell_cases[key].update(sl["case_ids"])
        for key, cases in cell_cases.items():
            assert len(cases) == 40, \
                f"cell {key} case coverage != 40: {len(cases)}"


# ---- TDD 6a: _generate_smoke_schedule tests ----

class TestGenerateSmokeSchedule:
    """Test _generate_smoke_schedule: 5 smoke slices, one per arm."""

    def test_smoke_has_5_slices(self, tmp_path):
        """smoke schedule 必须包含 5 slices (one per arm)."""
        smoke_slices = _generate_smoke_schedule(tmp_path)
        assert len(smoke_slices) == 5

    def test_smoke_covers_all_5_arms(self, tmp_path):
        """smoke 必须覆盖全部 5 arm."""
        smoke_slices = _generate_smoke_schedule(tmp_path)
        smoke_arms = {s["arm"] for s in smoke_slices}
        assert smoke_arms == set(ARMS)

    def test_smoke_slice_ids_are_smoke_prefix(self, tmp_path):
        """smoke slice_id 必须以 'smoke_' 开头."""
        smoke_slices = _generate_smoke_schedule(tmp_path)
        for s in smoke_slices:
            assert s["slice_id"].startswith("smoke_")

    def test_smoke_slices_use_2024_dataset(self, tmp_path):
        """smoke slices 必须使用 2024 dataset."""
        smoke_slices = _generate_smoke_schedule(tmp_path)
        for s in smoke_slices:
            assert s["year"] == "2024"
            assert "2024" in s["dataset"]

    def test_smoke_slices_have_8_cases(self, tmp_path):
        """每个 smoke slice 必须有 8 个 case_ids."""
        smoke_slices = _generate_smoke_schedule(tmp_path)
        for s in smoke_slices:
            assert len(s["case_ids"]) == SLICE_SIZE

    def test_smoke_slices_use_same_8_cases(self, tmp_path):
        """所有 smoke slices 使用相同的 8 个 case_ids."""
        smoke_slices = _generate_smoke_schedule(tmp_path)
        first_ids = smoke_slices[0]["case_ids"]
        for s in smoke_slices[1:]:
            assert s["case_ids"] == first_ids


# ---- TDD 6b: build_expected_key tests ----

class TestBuildExpectedKey:
    """Test build_expected_key: 10-tuple format."""

    def test_key_is_10_tuple(self):
        """attempt key 必须是 10-tuple."""
        key = build_expected_key("ds", "profile", "arm", "case1", 0, "p", "m")
        assert len(key) == 10

    def test_key_format_matches_runner(self):
        """key 格式必须匹配 runner 的 10-tuple 格式."""
        key = build_expected_key("ds_id", "profile_id", "b2b", "case_1", 2, "deepseek", "deepseek-chat")
        assert key == ("ds_id", "profile_id", "b2b", "main", "deepseek", "deepseek-chat",
                       "case_1", 2, 0, "p0")

    def test_key_case_id_is_string(self):
        """case_id 必须转为 string."""
        key = build_expected_key("ds", "p", "a", 12345, 0, "prov", "mod")
        assert key[6] == "12345"
        assert isinstance(key[6], str)

    def test_key_repeat_idx_is_int(self):
        """repeat_idx 必须转为 int."""
        key = build_expected_key("ds", "p", "a", "c", "1", "prov", "mod")
        assert key[7] == 1
        assert isinstance(key[7], int)
