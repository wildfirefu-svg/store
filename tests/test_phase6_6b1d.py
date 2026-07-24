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

import scripts.phase6_6b1d_orchestrator as orch
from scripts.phase6_6b1d_orchestrator import (
    BudgetLedger,
    compute_effective_cap,
    verify_cap_consistency_on_resume,
    reconcile_partial_events,
    determine_smoke_state,
    verify_smoke_completed,
    _verify_slice_completed,
    _validate_partial_events,
    _validate_events,
    _count_call_attempts,
    generate_schedule,
    build_expected_key,
    REASONED_PROFILE,
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
    generate_comparison_table,
    generate_report,
    FORBIDDEN_WORDS,
    BOOTSTRAP_SEED,
    BOOTSTRAP_DRAWS,
    FINGERPRINT_SCOPE,
    _compute_experiment_code_fingerprint,
    build_run_manifest,
    verify_run_manifest,
    write_run_manifest,
    validate_labels,
    compute_label_distribution,
    get_skipped_layers,
    LABEL_DIMENSIONS,
    LABEL_VALUES,
    LABELS_DEFAULT_PATH,
    LABEL_MIN_LAYER_SIZE,
    generate_archive,
    ARCHIVE_ROOT,
    EXPERIMENT_ID_PREFIX,
    compute_token_stats,
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


# ---- TDD 6a: smoke = schedule[0:5] tests ----

class TestSmokeIsScheduleFirst5:
    """Test smoke = schedule["slices"][:5]: 5 arms, G0-G4, 40 distinct cases.

    P0 #1 修复: smoke 不再是独立生成的 5 个 slice (smoke_ 前缀 + 相同 8 题),
    而是正式 schedule 的前 5 个 slice (position=0, 2024, R0, G0-G4).
    """

    def test_smoke_has_5_slices(self, tmp_path):
        """smoke (schedule[:5]) 必须包含 5 slices."""
        schedule = generate_schedule(tmp_path)
        smoke_slices = schedule["slices"][:5]
        assert len(smoke_slices) == 5

    def test_smoke_covers_all_5_arms(self, tmp_path):
        """smoke 必须覆盖全部 5 arm (b1a_prime, b1b, b1c, b2b, b2c)."""
        schedule = generate_schedule(tmp_path)
        smoke_slices = schedule["slices"][:5]
        smoke_arms = {s["arm"] for s in smoke_slices}
        assert smoke_arms == set(ARMS)

    def test_smoke_slice_ids_are_schedule_ids_not_smoke_prefix(self, tmp_path):
        """smoke slice_id 必须是正式 schedule ID, 不以 'smoke_' 开头."""
        schedule = generate_schedule(tmp_path)
        smoke_slices = schedule["slices"][:5]
        for s in smoke_slices:
            assert not s["slice_id"].startswith("smoke_"), \
                f"smoke 不应有独立 ID: {s['slice_id']}"

    def test_smoke_slices_use_2024_dataset(self, tmp_path):
        """smoke slices 必须使用 2024 dataset (position=0, repeat=0)."""
        schedule = generate_schedule(tmp_path)
        smoke_slices = schedule["slices"][:5]
        for s in smoke_slices:
            assert s["year"] == "2024"
            assert "2024" in s["dataset"]

    def test_smoke_slices_have_8_cases(self, tmp_path):
        """每个 smoke slice 必须有 8 个 case_ids."""
        schedule = generate_schedule(tmp_path)
        smoke_slices = schedule["slices"][:5]
        for s in smoke_slices:
            assert len(s["case_ids"]) == SLICE_SIZE

    def test_smoke_slices_cover_40_distinct_cases(self, tmp_path):
        """5 个 smoke slice 覆盖 G0-G4 共 40 个不同 case (不是相同 8 题)."""
        schedule = generate_schedule(tmp_path)
        smoke_slices = schedule["slices"][:5]
        all_case_ids = set()
        for s in smoke_slices:
            all_case_ids.update(s["case_ids"])
        assert len(all_case_ids) == 40, \
            f"smoke 应覆盖 40 题, 实际 {len(all_case_ids)}"

    def test_smoke_slices_cover_groups_0_to_4(self, tmp_path):
        """5 个 smoke slice 分别对应 group 0-4."""
        schedule = generate_schedule(tmp_path)
        smoke_slices = schedule["slices"][:5]
        groups = sorted(s["group"] for s in smoke_slices)
        assert groups == [0, 1, 2, 3, 4]


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


# ---- TDD: comparison table + report (plan §4.12) ----

def _build_completed_schedule_with_accuracy(tmp_path, arm_correct_count):
    """Build a full 150-slice completed schedule with controlled per-arm accuracy.

    arm_correct_count: {arm: int} -> first N of 8 records correct per slice.
    Returns (schedule, ledger, output_dir).
    """
    output_dir = tmp_path / "output"
    schedule = generate_schedule(output_dir)
    ledger_path = str(output_dir / "budget_ledger.json")
    ledger = BudgetLedger(ledger_path)

    for sl in schedule["slices"]:
        n_correct = arm_correct_count.get(sl["arm"], 0)
        rows = []
        for i, cid in enumerate(sl["case_ids"]):
            rows.append({
                "case_id": cid,
                "terminal_state": "parsed",
                "correct": i < n_correct,
            })
        os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
        with open(sl["detail_path"], "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        compute_effective_cap(sl["slice_id"], ledger, 0)
        ledger.record_slice_completed(sl["slice_id"], 8)
    ledger._save()
    return schedule, ledger, output_dir


_ACC = {"b1a_prime": 4, "b1b": 5, "b1c": 6, "b2b": 3, "b2c": 5}


class TestComparisonTable:
    """Test generate_comparison_table: 5-arm ranking, pairwise diffs, bootstrap CI."""

    def test_five_arms_all_present(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        assert set(table["arm_stats"].keys()) == set(ARMS)

    def test_accuracy_matches_controlled_correctness(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        assert table["arm_stats"]["b1a_prime"]["accuracy"] == 0.5
        assert table["arm_stats"]["b1c"]["accuracy"] == 0.75
        assert table["arm_stats"]["b2b"]["accuracy"] == 0.375

    def test_ci_brackets_accuracy(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        for arm, s in table["arm_stats"].items():
            assert s["ci_low"] <= s["accuracy"] <= s["ci_high"], \
                f"arm {arm}: ci [{s['ci_low']}, {s['ci_high']}] not bracketing {s['accuracy']}"

    def test_ranking_sorted_desc(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        accs = [table["arm_stats"][a]["accuracy"] for a in table["ranking"]]
        assert accs == sorted(accs, reverse=True)
        assert table["ranking"][0] == "b1c"

    def test_ten_pairwise_diffs(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        assert len(table["pairwise_diffs"]) == 10  # 5 choose 2

    def test_pairwise_diff_brackets_point(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        for d in table["pairwise_diffs"]:
            assert d["ci_low"] <= d["diff"] <= d["ci_high"], \
                f"{d['arm_a']}-{d['arm_b']}: ci not bracketing diff {d['diff']}"

    def test_bootstrap_deterministic(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        t1 = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        t2 = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS:
            assert t1["arm_stats"][arm] == t2["arm_stats"][arm]
        assert t1["pairwise_diffs"] == t2["pairwise_diffs"]

    def test_bootstrap_seed_and_draws_recorded(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        assert table["bootstrap"]["seed"] == BOOTSTRAP_SEED
        assert table["bootstrap"]["draws"] == BOOTSTRAP_DRAWS

    def test_n_records_240_per_arm(self, tmp_path):
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS:
            assert table["arm_stats"][arm]["n_records"] == 240


class TestReport:
    """Test generate_report: descriptive, no forbidden words."""

    def test_report_written_no_forbidden_words(self, tmp_path):
        schedule, ledger, output_dir = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        report_path = generate_report(schedule, table, output_dir, ledger)
        assert os.path.exists(report_path)
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        for word in FORBIDDEN_WORDS:
            assert word not in content, f"report contains forbidden word: {word}"

    def test_report_contains_all_arms(self, tmp_path):
        schedule, ledger, output_dir = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        report_path = generate_report(schedule, table, output_dir, ledger)
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        for arm in ARMS:
            assert arm in content

    def test_report_contains_pairwise_section(self, tmp_path):
        schedule, ledger, output_dir = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        report_path = generate_report(schedule, table, output_dir, ledger)
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Pairwise Differences" in content
        assert "Five-Arm Accuracy" in content


# ---- TDD: smoke vs main slice verification split (P0 #2) ----

def _write_slice_details(sl, rows, provider="deepseek", model="deepseek-chat"):
    """Write details.jsonl for a slice with given rows.
    Each row: {case_id, terminal_state, correct, attempt_key}.
    """
    os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
    dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
    full_rows = []
    for i, cid in enumerate(sl["case_ids"]):
        r = rows[i] if i < len(rows) else {"terminal_state": "parsed", "correct": True}
        full_rows.append({
            "case_id": cid,
            "terminal_state": r.get("terminal_state", "parsed"),
            "correct": r.get("correct", True),
            "attempt_key": list(build_expected_key(
                dataset_id, REASONED_PROFILE, sl["arm"],
                cid, sl["repeat"], provider, model)),
        })
    with open(sl["detail_path"], "w", encoding="utf-8") as f:
        for r in full_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_slice_events(sl, call_count=None):
    """Write events.jsonl with call_attempt events."""
    os.makedirs(os.path.dirname(sl["events_path"]), exist_ok=True)
    n = call_count if call_count is not None else sl["size"]
    with open(sl["events_path"], "w", encoding="utf-8") as f:
        for _ in range(n):
            f.write(json.dumps({"kind": "call_attempt"}, ensure_ascii=False) + "\n")


def _write_slice_manifest(sl, provider="deepseek", model="deepseek-chat"):
    """Write a minimal manifest file (verify_slice_manifest will be mocked)."""
    os.makedirs(os.path.dirname(sl["manifest_path"]), exist_ok=True)
    with open(sl["manifest_path"], "w", encoding="utf-8") as f:
        json.dump({"hard_cap": sl["hard_cap"]}, f)


class TestSmokeVsMainVerification:
    """P0 #2: smoke requires 100% parser rate, main does not."""

    def _setup_slice(self, tmp_path, idx, rows, monkeypatch):
        """Create a slice at schedule index `idx` with given detail rows."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        sl = schedule["slices"][idx]

        _write_slice_details(sl, rows)
        _write_slice_events(sl)
        _write_slice_manifest(sl)

        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        compute_effective_cap(sl["slice_id"], ledger, 0)
        ledger.record_slice_completed(sl["slice_id"], sl["size"])
        ledger._save()

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda s, p, m: (True, {}))

        args = type("Args", (), {"provider": "deepseek", "model": "deepseek-chat"})()
        return sl, args, ledger

    def test_smoke_rejects_non_parsed(self, tmp_path, monkeypatch):
        """Smoke slice with <100% parsed must fail."""
        rows = [{"terminal_state": "parsed", "correct": True}] * 7 + \
               [{"terminal_state": "invalid", "correct": False}]
        sl, args, ledger = self._setup_slice(tmp_path, 0, rows, monkeypatch)
        ok, reason = verify_smoke_completed(sl, args, ledger, require_parser_rate=True)
        assert not ok
        assert "parser_rate" in reason

    def test_smoke_accepts_all_parsed(self, tmp_path, monkeypatch):
        """Smoke slice with 8/8 parsed must pass."""
        rows = [{"terminal_state": "parsed", "correct": True}] * 8
        sl, args, ledger = self._setup_slice(tmp_path, 0, rows, monkeypatch)
        ok, reason = verify_smoke_completed(sl, args, ledger, require_parser_rate=True)
        assert ok, f"smoke with 8/8 parsed should pass: {reason}"

    def test_main_accepts_mixed_terminal_states(self, tmp_path, monkeypatch):
        """Main slice with invalid/unresolved/call_failed must pass (no 100% parser gate)."""
        rows = [
            {"terminal_state": "parsed", "correct": True},
            {"terminal_state": "parsed", "correct": False},
            {"terminal_state": "parsed", "correct": True},
            {"terminal_state": "parsed", "correct": True},
            {"terminal_state": "parsed", "correct": False},
            {"terminal_state": "invalid", "correct": False},
            {"terminal_state": "unresolved", "correct": False},
            {"terminal_state": "call_failed", "correct": False},
        ]
        sl, args, ledger = self._setup_slice(tmp_path, 5, rows, monkeypatch)
        ok, reason = verify_smoke_completed(sl, args, ledger, require_parser_rate=False)
        assert ok, f"main slice with mixed terminal states should pass: {reason}"

    def test_main_rejects_non_terminal_state(self, tmp_path, monkeypatch):
        """Main slice must still reject records without a terminal_state."""
        rows = [{"terminal_state": "parsed", "correct": True}] * 7 + \
               [{"terminal_state": "pending", "correct": False}]
        sl, args, ledger = self._setup_slice(tmp_path, 5, rows, monkeypatch)
        ok, reason = verify_smoke_completed(sl, args, ledger, require_parser_rate=False)
        assert not ok
        assert "terminal state" in reason

    def test_verify_slice_completed_smoke_flag(self, tmp_path, monkeypatch):
        """_verify_slice_completed with is_smoke=False allows non-parsed."""
        rows = [{"terminal_state": "parsed", "correct": True}] * 6 + \
               [{"terminal_state": "invalid", "correct": False}] + \
               [{"terminal_state": "unresolved", "correct": False}]
        sl, args, ledger = self._setup_slice(tmp_path, 10, rows, monkeypatch)
        assert _verify_slice_completed(sl, args, ledger, is_smoke=False)

    def test_verify_slice_completed_smoke_flag_rejects(self, tmp_path, monkeypatch):
        """_verify_slice_completed with is_smoke=True rejects <100% parsed."""
        rows = [{"terminal_state": "parsed", "correct": True}] * 7 + \
               [{"terminal_state": "invalid", "correct": False}]
        sl, args, ledger = self._setup_slice(tmp_path, 0, rows, monkeypatch)
        assert not _verify_slice_completed(sl, args, ledger, is_smoke=True)


# ---- TDD: schedule consistency deep-compare (P0: semantic fields) ----

def _build_and_tamper_slice(tmp_path, field, value, slice_idx=0):
    """Build a schedule, deepcopy it, tamper one field on one slice.

    Returns (original, tampered).
    """
    import copy
    from scripts.phase6_6b1d_orchestrator import _build_schedule
    schedule = _build_schedule(tmp_path)
    tampered = copy.deepcopy(schedule)
    tampered["slices"][slice_idx][field] = value
    return schedule, tampered


def _build_and_tamper_top_level(tmp_path, field, value):
    """Build a schedule, deepcopy it, tamper one top-level field.

    Returns (original, tampered).
    """
    import copy
    from scripts.phase6_6b1d_orchestrator import _build_schedule
    schedule = _build_schedule(tmp_path)
    tampered = copy.deepcopy(schedule)
    tampered[field] = value
    return schedule, tampered


class TestScheduleConsistencySemanticFields:
    """P0: _verify_schedule_consistent must catch tampering of any semantic field.

    Previously only total_slices/total_scheduled_calls/slice_id/case_ids were
    compared, so a tampered arm/ziwei_arm/year/etc. passed and the historical
    schedule was trusted with wrong experiment arms.
    """

    def test_consistent_schedule_passes(self, tmp_path):
        """An unmodified schedule is consistent with itself."""
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        schedule = _build_schedule(tmp_path)
        ok, reason = _verify_schedule_consistent(schedule, schedule)
        assert ok, f"identical schedule should be consistent: {reason}"

    def test_tampered_arm_caught(self, tmp_path):
        """Tampering a slice's arm is caught (the original review finding)."""
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "arm", "tampered_arm")
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "arm" in reason

    def test_tampered_ziwei_arm_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "ziwei_arm", "tampered")
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "ziwei_arm" in reason

    def test_tampered_year_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "year", "1999")
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "year" in reason

    def test_tampered_repeat_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "repeat", 99)
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "repeat" in reason

    def test_tampered_group_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "group", 99)
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "group" in reason

    def test_tampered_position_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "position", 99)
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "position" in reason

    def test_tampered_scheduled_calls_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "scheduled_calls", 999)
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "scheduled_calls" in reason

    def test_tampered_hard_cap_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "hard_cap", 999)
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "hard_cap" in reason

    def test_tampered_case_ids_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "case_ids", ["fake_id"])
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "case_ids" in reason

    def test_tampered_dataset_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_slice(tmp_path, "dataset", "fake.jsonl")
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "dataset" in reason

    def test_tampered_total_hard_cap_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_top_level(tmp_path, "total_hard_cap", 99999)
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "total_hard_cap" in reason

    def test_tampered_slice_size_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_top_level(tmp_path, "slice_size", 99)
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "slice_size" in reason

    def test_tampered_slice_max_cap_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_top_level(tmp_path, "slice_max_cap", 99)
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "slice_max_cap" in reason

    def test_tampered_arm_ziwei_map_caught(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import _verify_schedule_consistent
        original, tampered = _build_and_tamper_top_level(tmp_path, "arm_ziwei_map", {})
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "arm_ziwei_map" in reason

    def test_path_fields_not_compared(self, tmp_path):
        """Derived path fields (output_dir/detail_path/etc.) differ between
        schedules built in different output_dirs but must NOT cause a mismatch,
        since they carry no experiment semantics."""
        import copy
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        a = _build_schedule(tmp_path / "a")
        b = _build_schedule(tmp_path / "b")
        ok, reason = _verify_schedule_consistent(a, b)
        assert ok, f"path-only differences must not fail consistency: {reason}"

    def test_historical_none_fails(self, tmp_path):
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        built = _build_schedule(tmp_path)
        ok, reason = _verify_schedule_consistent(None, built)
        assert not ok
        assert "missing" in reason or "corrupt" in reason

    def test_slice_order_swap_caught(self, tmp_path):
        """Swapping two slices (e.g. first and last) is caught.

        The main loop treats slices[0:5] as smoke and iterates the rest in
        order, so a reordering that a dict-based comparison would miss must
        be detected here.
        """
        import copy
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        original = _build_schedule(tmp_path)
        swapped = copy.deepcopy(original)
        swapped["slices"][0], swapped["slices"][-1] = (
            swapped["slices"][-1], swapped["slices"][0])
        ok, reason = _verify_schedule_consistent(original, swapped)
        assert not ok
        assert "pos 0" in reason or "mismatch" in reason

    def test_append_duplicate_slice_caught(self, tmp_path):
        """Appending a duplicate slice (and bumping total_slices) is caught."""
        import copy
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        original = _build_schedule(tmp_path)
        tampered = copy.deepcopy(original)
        tampered["slices"].append(copy.deepcopy(tampered["slices"][0]))
        tampered["total_slices"] = 151
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "total_slices" in reason

    def test_total_slices_disagrees_with_len_slices_caught(self, tmp_path):
        """total_slices=150 but len(slices)=151 (both sides) is caught.

        The count vs declared-total check catches a tampered total_slices that
        still matches between historical/built but disagrees with the actual
        list length.
        """
        import copy
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        schedule = _build_schedule(tmp_path)
        tampered = copy.deepcopy(schedule)
        tampered["slices"].append(copy.deepcopy(tampered["slices"][0]))
        # total_slices stays 150 but len(slices) is now 151
        assert tampered["total_slices"] == 150
        ok, reason = _verify_schedule_consistent(tampered, tampered)
        assert not ok
        assert "len(slices)" in reason or "total_slices" in reason

    def test_duplicate_slice_id_within_list_caught(self, tmp_path):
        """A duplicate slice_id within a single schedule is caught (even if the
        two sides are identical), since a dict-based comparison would fold them
        together."""
        import copy
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        schedule = _build_schedule(tmp_path)
        tampered = copy.deepcopy(schedule)
        tampered["slices"].append(copy.deepcopy(tampered["slices"][0]))
        tampered["total_slices"] = 151
        ok, reason = _verify_schedule_consistent(tampered, tampered)
        assert not ok
        assert "duplicate slice_ids" in reason

    def test_missing_slice_caught(self, tmp_path):
        """Removing a slice (and dropping total_slices) is caught by the count
        check before any position-wise comparison."""
        import copy
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        original = _build_schedule(tmp_path)
        tampered = copy.deepcopy(original)
        tampered["slices"].pop()
        tampered["total_slices"] = 149
        ok, reason = _verify_schedule_consistent(original, tampered)
        assert not ok
        assert "total_slices" in reason or "count" in reason

    def test_slice_count_mismatch_caught(self, tmp_path):
        """historical has 150 slices, built has 149 -> count mismatch caught."""
        import copy
        from scripts.phase6_6b1d_orchestrator import (
            _build_schedule, _verify_schedule_consistent)
        original = _build_schedule(tmp_path)
        shorter = copy.deepcopy(original)
        shorter["slices"].pop()
        shorter["total_slices"] = 149
        ok, reason = _verify_schedule_consistent(original, shorter)
        assert not ok


# ---- TDD: experiment-level code fingerprint (P0 #1) ----

class TestExperimentCodeFingerprint:
    """P0 #1: FINGERPRINT_SCOPE must be used for experiment-level fingerprint."""

    def test_fingerprint_scope_includes_orchestrator(self):
        """FINGERPRINT_SCOPE must include the orchestrator itself."""
        assert "scripts/phase6_6b1d_orchestrator.py" in FINGERPRINT_SCOPE

    def test_fingerprint_scope_has_5_files(self):
        """Exactly 5 approved files in scope."""
        assert len(FINGERPRINT_SCOPE) == 5

    def test_fingerprint_is_deterministic(self):
        """Same code -> same fingerprint."""
        fp1 = _compute_experiment_code_fingerprint()
        fp2 = _compute_experiment_code_fingerprint()
        assert fp1 == fp2

    def test_fingerprint_is_hex_string(self):
        """Fingerprint is a hex string."""
        fp = _compute_experiment_code_fingerprint()
        int(fp, 16)

    def test_fingerprint_changes_with_orchestrator_modification(self, tmp_path):
        """Modifying orchestrator changes fingerprint.

        Uses a tmp mirror of the scope files (not production source) so the test
        cannot corrupt the working tree or alter line endings if interrupted.
        """
        import shutil
        mirror = tmp_path / "mirror"
        mirror.mkdir()
        for rel in FINGERPRINT_SCOPE:
            src = os.path.join(PROJECT_ROOT, rel)
            dst = mirror / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, str(dst))

        original_fp = _compute_experiment_code_fingerprint(
            root=str(mirror), scope=FINGERPRINT_SCOPE)

        orch_copy = mirror / "scripts" / "phase6_6b1d_orchestrator.py"
        with open(str(orch_copy), "r", encoding="utf-8") as f:
            content = f.read()
        with open(str(orch_copy), "w", encoding="utf-8") as f:
            f.write(content + "\n# fingerprint test marker\n")

        new_fp = _compute_experiment_code_fingerprint(
            root=str(mirror), scope=FINGERPRINT_SCOPE)
        assert new_fp != original_fp, "orchestrator modification must change fingerprint"


class TestRunManifest:
    """P0 #1: run manifest creation, verification, and resume rejection."""

    def test_fresh_start_no_manifest(self, tmp_path):
        """No existing run_manifest.json -> ok (fresh start)."""
        ok, reason = verify_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        assert ok
        assert "fresh" in reason

    def test_write_then_verify_ok(self, tmp_path):
        """Write manifest, then verify -> ok."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        ok, reason = verify_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        assert ok, f"should pass: {reason}"

    def test_verify_rejects_fingerprint_drift(self, tmp_path, monkeypatch):
        """Fingerprint drift -> rejected."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        manifest_path = tmp_path / "run_manifest.json"
        with open(str(manifest_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        data["experiment_code_fingerprint"] = "deadbeefdeadbeef"
        with open(str(manifest_path), "w", encoding="utf-8") as f:
            json.dump(data, f)
        ok, reason = verify_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        assert not ok
        assert "fingerprint drift" in reason

    def test_verify_rejects_provider_mismatch(self, tmp_path):
        """Provider mismatch -> rejected."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        ok, reason = verify_run_manifest(tmp_path, "openai", "gpt-4")
        assert not ok
        assert "provider" in reason.lower()

    def test_verify_rejects_model_mismatch(self, tmp_path):
        """Model mismatch -> rejected."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        ok, reason = verify_run_manifest(tmp_path, "deepseek", "deepseek-reasoner")
        assert not ok
        assert "model" in reason.lower()

    def test_verify_rejects_labels_sha256_mismatch(self, tmp_path):
        """Labels SHA-256 mismatch -> rejected."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat",
                           labels_sha256="aaa")
        ok, reason = verify_run_manifest(tmp_path, "deepseek", "deepseek-chat",
                                         labels_sha256="bbb")
        assert not ok
        assert "labels" in reason.lower()

    def test_manifest_contains_fingerprint_scope(self, tmp_path):
        """Run manifest must list fingerprint_scope."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        manifest_path = tmp_path / "run_manifest.json"
        with open(str(manifest_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "fingerprint_scope" in data
        assert "scripts/phase6_6b1d_orchestrator.py" in data["fingerprint_scope"]

    def test_manifest_stores_full_64_char_fingerprint(self, tmp_path):
        """experiment_code_fingerprint must be the FULL 64-hex-char SHA-256.

        Plan §4.14: 实验级指纹保存完整 SHA-256 (not a 16-char truncation).
        """
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        manifest_path = tmp_path / "run_manifest.json"
        with open(str(manifest_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        fp = data["experiment_code_fingerprint"]
        assert len(fp) == 64, f"fingerprint must be 64 chars, got {len(fp)}"
        int(fp, 16)  # must be valid hex

    def test_manifest_contains_experiment_id(self, tmp_path):
        """Run manifest must contain experiment_id = 6b1d."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat")
        manifest_path = tmp_path / "run_manifest.json"
        with open(str(manifest_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["experiment_id"] == "6b1d"


# ---- TDD: labels preflight + distribution (P0 #3a/b/c) ----

def _make_valid_labels(tmp_path, n_cases=80):
    """Create a valid labels.jsonl with n_cases entries matching the datasets."""
    from scripts.phase6_6b1d_orchestrator import _collect_all_case_ids
    expected_ids = sorted(_collect_all_case_ids())
    labels = []
    for i, cid in enumerate(expected_ids[:n_cases]):
        fv = (i % 3) + 1
        dv = (fv % 3) + 1  # distinct value -> annotators disagree, final is adjudicated
        labels.append({
            "case_id": cid,
            "annotator_1_id": "a1",
            "annotator_1": {"question_complexity": fv, "ziwei_info_richness": fv, "bazi_info_richness": fv},
            "annotator_2_id": "a2",
            "annotator_2": {"question_complexity": dv, "ziwei_info_richness": dv, "bazi_info_richness": dv},
            "adjudicator": "ad",
            "final": {"question_complexity": fv, "ziwei_info_richness": fv, "bazi_info_richness": fv},
        })
    path = str(tmp_path / "labels.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for l in labels:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    return path


class TestLabelsPreflight:
    """P0 #3a: labels.jsonl preflight validation."""

    def test_valid_labels_pass(self, tmp_path):
        """Valid labels.jsonl with 80 cases passes validation."""
        path = _make_valid_labels(tmp_path)
        ok, sha, data, reason = validate_labels(path)
        assert ok, f"valid labels should pass: {reason}"
        assert sha is not None
        assert len(data) == 80

    def test_missing_file_fails(self, tmp_path):
        """Missing labels file fails."""
        ok, sha, data, reason = validate_labels(str(tmp_path / "nonexistent.jsonl"))
        assert not ok
        assert "not found" in reason

    def test_duplicate_case_ids_fail(self, tmp_path):
        """Duplicate case IDs fail."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(path, "w", encoding="utf-8") as f:
            f.write(lines[0])
            f.write(lines[0])
        ok, sha, data, reason = validate_labels(path)
        assert not ok
        assert "duplicate" in reason.lower()

    def test_missing_case_ids_fail(self, tmp_path):
        """Missing case IDs (incomplete coverage) fail."""
        path = _make_valid_labels(tmp_path, n_cases=79)
        ok, sha, data, reason = validate_labels(path)
        assert not ok
        assert "missing" in reason.lower()

    def test_invalid_value_fails(self, tmp_path):
        """Value outside {1,2,3} fails."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["final"]["question_complexity"] = 5
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, sha, data, reason = validate_labels(path)
        assert not ok
        assert "not in" in reason

    def test_returns_sha256(self, tmp_path):
        """validate_labels returns a SHA-256 hex string."""
        path = _make_valid_labels(tmp_path)
        ok, sha, data, reason = validate_labels(path)
        assert ok
        assert len(sha) == 64
        int(sha, 16)

    def test_default_labels_file_exists(self):
        """The default labels.jsonl file exists at docs/phase6/6b1d/labels.jsonl."""
        assert os.path.exists(LABELS_DEFAULT_PATH)

    def test_default_labels_valid(self):
        """The default labels.jsonl passes validation."""
        ok, sha, data, reason = validate_labels(LABELS_DEFAULT_PATH)
        assert ok, f"default labels should pass: {reason}"
        assert len(data) == 80


class TestLabelsAnnotatorSchema:
    """P0 #2: validate_labels must enforce the full dual-annotator schema."""

    def test_missing_annotator_1_fails(self, tmp_path):
        """Row missing annotator_1 block fails."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        del first["annotator_1"]
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert not ok
        assert "annotator_1" in reason

    def test_same_annotator_ids_fails(self, tmp_path):
        """annotator_1_id == annotator_2_id fails (must be two independent annotators)."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["annotator_2_id"] = first["annotator_1_id"]
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert not ok
        assert "independent" in reason

    def test_empty_annotator_id_fails(self, tmp_path):
        """Empty annotator_2_id fails."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["annotator_2_id"] = ""
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert not ok
        assert "annotator_2_id" in reason

    def test_missing_adjudicator_fails(self, tmp_path):
        """Row missing adjudicator fails."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        del first["adjudicator"]
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert not ok
        assert "adjudicator" in reason

    def test_annotator_raw_label_out_of_range_fails(self, tmp_path):
        """annotator_2 dimension value outside {1,2,3} fails."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["annotator_2"]["ziwei_info_richness"] = 9
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert not ok
        assert "annotator_2" in reason

    def test_disagreement_with_valid_final_passes(self, tmp_path):
        """Annotators disagree but final (adjudicated) is valid -> passes."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["annotator_1"]["question_complexity"] = 1
        first["annotator_2"]["question_complexity"] = 3
        first["final"]["question_complexity"] = 3
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert ok, f"disagreement with valid final should pass: {reason}"


class TestLabelsAdjudicatorProtocol:
    """Adjudication protocol (plan §5.2: 分歧由第 3 人裁决):
    - adjudicator must be a genuine third person (distinct from both annotators)
    - when annotators agree on a dimension, final MUST equal their common label
    """

    def test_adjudicator_equals_annotator_1_fails(self, tmp_path):
        """adjudicator == annotator_1_id fails (must be a third person)."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["adjudicator"] = first["annotator_1_id"]
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert not ok
        assert "third person" in reason or "distinct" in reason

    def test_adjudicator_equals_annotator_2_fails(self, tmp_path):
        """adjudicator == annotator_2_id fails (must be a third person)."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["adjudicator"] = first["annotator_2_id"]
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert not ok
        assert "third person" in reason or "distinct" in reason

    def test_agreement_but_final_differs_fails(self, tmp_path):
        """Annotators agree on a dimension but final differs -> fails.

        When two annotators give the same label, the adjudicator cannot
        override it; final must equal the agreed value.
        """
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        # Force agreement on question_complexity=2, but final=1 (override)
        first["annotator_1"]["question_complexity"] = 2
        first["annotator_2"]["question_complexity"] = 2
        first["final"]["question_complexity"] = 1
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert not ok
        assert "agree" in reason

    def test_agreement_final_matches_passes(self, tmp_path):
        """Annotators agree AND final matches -> passes (no adjudication needed)."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        # Force full agreement with matching final
        first["annotator_1"] = {"question_complexity": 2, "ziwei_info_richness": 2, "bazi_info_richness": 2}
        first["annotator_2"] = {"question_complexity": 2, "ziwei_info_richness": 2, "bazi_info_richness": 2}
        first["final"] = {"question_complexity": 2, "ziwei_info_richness": 2, "bazi_info_richness": 2}
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert ok, f"agreement with matching final should pass: {reason}"

    def test_partial_agreement_partial_disagreement_passes(self, tmp_path):
        """One dimension agrees (final matches), another disagrees (final adjudicated)."""
        path = _make_valid_labels(tmp_path)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        # question_complexity: agree on 2, final=2 (ok)
        first["annotator_1"]["question_complexity"] = 2
        first["annotator_2"]["question_complexity"] = 2
        first["final"]["question_complexity"] = 2
        # ziwei_info_richness: disagree (1 vs 3), final=3 (adjudicated, ok)
        first["annotator_1"]["ziwei_info_richness"] = 1
        first["annotator_2"]["ziwei_info_richness"] = 3
        first["final"]["ziwei_info_richness"] = 3
        lines[0] = json.dumps(first, ensure_ascii=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        ok, _, _, reason = validate_labels(path)
        assert ok, f"mixed agree/disagree with valid final should pass: {reason}"

    def test_default_labels_satisfy_adjudicator_protocol(self):
        """The shipped labels.jsonl must satisfy the adjudicator protocol."""
        ok, _, _, reason = validate_labels(LABELS_DEFAULT_PATH)
        assert ok, f"default labels must pass adjudicator protocol: {reason}"


class TestLabelDistribution:
    """P0 #3c: 3D label distribution and <5 skip rule."""

    def test_distribution_has_3_dimensions(self, tmp_path):
        """Distribution covers all 3 dimensions."""
        path = _make_valid_labels(tmp_path)
        ok, sha, data, _ = validate_labels(path)
        dist = compute_label_distribution(data)
        assert set(dist.keys()) == set(LABEL_DIMENSIONS)

    def test_distribution_values_sum_to_80(self, tmp_path):
        """Each dimension's values sum to 80."""
        path = _make_valid_labels(tmp_path)
        ok, sha, data, _ = validate_labels(path)
        dist = compute_label_distribution(data)
        for dim in LABEL_DIMENSIONS:
            assert sum(dist[dim].values()) == 80

    def test_skipped_layers_with_small_sample(self, tmp_path):
        """Layers with < 5 samples are in skipped list."""
        from scripts.phase6_6b1d_orchestrator import _collect_all_case_ids
        expected_ids = sorted(_collect_all_case_ids())
        labels = []
        for i, cid in enumerate(expected_ids):
            zr = 3 if i < 3 else 1
            labels.append({
                "case_id": cid,
                "final": {"question_complexity": 1, "ziwei_info_richness": zr, "bazi_info_richness": 1},
            })
        skipped = get_skipped_layers(labels)
        assert ("ziwei_info_richness", 3) in skipped
        assert ("ziwei_info_richness", 1) not in skipped

    def test_no_skipped_layers_when_balanced(self, tmp_path):
        """No layers skipped when all have >= 5 samples."""
        path = _make_valid_labels(tmp_path)
        ok, sha, data, _ = validate_labels(path)
        skipped = get_skipped_layers(data)
        for dim, val in skipped:
            dist = compute_label_distribution(data)
            assert dist[dim][val] < LABEL_MIN_LAYER_SIZE

    def test_default_labels_ziwei_distribution_matches_expected(self):
        """Default labels ziwei_info_richness: ~20/45/15 (plan 附录 A.2)."""
        ok, sha, data, _ = validate_labels(LABELS_DEFAULT_PATH)
        dist = compute_label_distribution(data)
        zr = dist["ziwei_info_richness"]
        assert zr[1] == 20
        assert zr[2] == 45
        assert zr[3] == 15


class TestLabelsInRunManifest:
    """P0 #3b: labels SHA-256 written into run manifest and verified on resume."""

    def test_run_manifest_contains_labels_sha256(self, tmp_path):
        """Run manifest includes labels_sha256 field."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat",
                           labels_sha256="abc123")
        manifest_path = tmp_path / "run_manifest.json"
        with open(str(manifest_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["labels_sha256"] == "abc123"

    def test_resume_rejects_labels_change(self, tmp_path):
        """Labels SHA-256 change on resume is rejected."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat",
                           labels_sha256="old_hash")
        ok, reason = verify_run_manifest(tmp_path, "deepseek", "deepseek-chat",
                                         labels_sha256="new_hash")
        assert not ok
        assert "labels" in reason.lower()

    def test_resume_accepts_same_labels(self, tmp_path):
        """Same labels SHA-256 on resume is accepted."""
        write_run_manifest(tmp_path, "deepseek", "deepseek-chat",
                           labels_sha256="same_hash")
        ok, reason = verify_run_manifest(tmp_path, "deepseek", "deepseek-chat",
                                         labels_sha256="same_hash")
        assert ok


# ---- TDD: formal archive (P0 #3d/e) ----

def _build_full_archiveable_schedule(tmp_path, monkeypatch):
    """Build a full 150-slice completed schedule with all artifacts for archiving.
    Mocks verify_slice_manifest to always pass.
    Returns (schedule, ledger, output_dir, labels_data).
    """
    output_dir = tmp_path / "output"
    schedule = generate_schedule(output_dir)
    ledger_path = str(output_dir / "budget_ledger.json")
    ledger = BudgetLedger(ledger_path)

    for sl in schedule["slices"]:
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        rows = []
        for cid in sl["case_ids"]:
            rows.append({
                "case_id": cid,
                "terminal_state": "parsed",
                "correct": True,
                "attempt_key": list(build_expected_key(
                    dataset_id, REASONED_PROFILE, sl["arm"],
                    cid, sl["repeat"], "deepseek", "deepseek-chat")),
            })
        os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
        with open(sl["detail_path"], "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        _write_slice_events(sl)
        _write_slice_manifest(sl)
        compute_effective_cap(sl["slice_id"], ledger, 0)
        ledger.record_slice_completed(sl["slice_id"], sl["size"])
    ledger._save()

    # Write run manifest and labels
    write_run_manifest(output_dir, "deepseek", "deepseek-chat", labels_sha256="test")
    labels_path = str(output_dir / "labels.jsonl")
    with open(labels_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"case_id": "test", "final": {
            "question_complexity": 1, "ziwei_info_richness": 1, "bazi_info_richness": 1}},
            ensure_ascii=False) + "\n")

    monkeypatch.setattr(orch, "verify_slice_manifest",
                        lambda sl, p, m: (True, {}))
    labels_data = [{"case_id": "test", "final": {
        "question_complexity": 1, "ziwei_info_richness": 1, "bazi_info_richness": 1}}]
    return schedule, ledger, output_dir, labels_data


class TestArchiveGeneration:
    """P0 #3d/e: five smoke archive, audit_index, run ID."""

    def test_five_smoke_directories(self, tmp_path, monkeypatch):
        """Archive creates five smoke_<arm>/ directories."""
        schedule, ledger, output_dir, labels_data = _build_full_archiveable_schedule(tmp_path, monkeypatch)
        archive_root = tmp_path / "archive"
        archive_path = generate_archive(
            schedule, ledger, output_dir, "deepseek", "deepseek-chat",
            labels_sha256="test", labels_data=labels_data, archive_root=archive_root)
        for arm in ARMS:
            smoke_dir = Path(archive_path) / f"smoke_{arm}"
            assert smoke_dir.exists(), f"smoke_{arm}/ not found"
            assert (smoke_dir / "details.jsonl").exists()

    def test_slices_directory_has_145_entries(self, tmp_path, monkeypatch):
        """slices/ has 145 non-smoke slice directories."""
        schedule, ledger, output_dir, labels_data = _build_full_archiveable_schedule(tmp_path, monkeypatch)
        archive_root = tmp_path / "archive"
        archive_path = generate_archive(
            schedule, ledger, output_dir, "deepseek", "deepseek-chat",
            labels_sha256="test", labels_data=labels_data, archive_root=archive_root)
        slices_dir = Path(archive_path) / "slices"
        assert slices_dir.exists()
        slice_dirs = [d for d in slices_dir.iterdir() if d.is_dir()]
        assert len(slice_dirs) == 145

    def test_audit_index_exists_and_has_fields(self, tmp_path, monkeypatch):
        """audit_index.json exists and contains required fields."""
        schedule, ledger, output_dir, labels_data = _build_full_archiveable_schedule(tmp_path, monkeypatch)
        archive_root = tmp_path / "archive"
        archive_path = generate_archive(
            schedule, ledger, output_dir, "deepseek", "deepseek-chat",
            labels_sha256="test", labels_data=labels_data, archive_root=archive_root)
        audit_path = Path(archive_path) / "audit_index.json"
        assert audit_path.exists()
        with open(str(audit_path), "r", encoding="utf-8") as f:
            audit = json.load(f)
        for field in ("run_id", "experiment_id", "code_fingerprint",
                       "labels_sha256", "label_distribution", "skipped_layers",
                       "smoke_artifact_hashes", "slice_artifact_hashes",
                       "merge_counts", "dataset_hashes", "context_fingerprints"):
            assert field in audit, f"audit_index missing {field}"

    def test_run_id_starts_with_6b1d(self, tmp_path, monkeypatch):
        """Run ID starts with 6b1d- (not 6b1-)."""
        schedule, ledger, output_dir, labels_data = _build_full_archiveable_schedule(tmp_path, monkeypatch)
        archive_root = tmp_path / "archive"
        archive_path = generate_archive(
            schedule, ledger, output_dir, "deepseek", "deepseek-chat",
            labels_sha256="test", labels_data=labels_data, archive_root=archive_root)
        run_dir_name = Path(archive_path).name
        assert run_dir_name.startswith("6b1d-")
        assert not run_dir_name.startswith("6b1-")

    def test_archive_refuses_overwrite(self, tmp_path, monkeypatch):
        """Archive refuses to overwrite existing directory."""
        schedule, ledger, output_dir, labels_data = _build_full_archiveable_schedule(tmp_path, monkeypatch)
        archive_root = tmp_path / "archive"
        generate_archive(
            schedule, ledger, output_dir, "deepseek", "deepseek-chat",
            labels_sha256="test", labels_data=labels_data, archive_root=archive_root)
        with pytest.raises(SystemExit):
            generate_archive(
                schedule, ledger, output_dir, "deepseek", "deepseek-chat",
                labels_sha256="test", labels_data=labels_data, archive_root=archive_root)

    def test_smoke_hashes_in_audit_index(self, tmp_path, monkeypatch):
        """audit_index contains hash entries for all 5 smoke arms."""
        schedule, ledger, output_dir, labels_data = _build_full_archiveable_schedule(tmp_path, monkeypatch)
        archive_root = tmp_path / "archive"
        archive_path = generate_archive(
            schedule, ledger, output_dir, "deepseek", "deepseek-chat",
            labels_sha256="test", labels_data=labels_data, archive_root=archive_root)
        with open(str(Path(archive_path) / "audit_index.json"), "r", encoding="utf-8") as f:
            audit = json.load(f)
        smoke_hashes = audit["smoke_artifact_hashes"]
        assert len(smoke_hashes) == 5
        for arm in ARMS:
            assert arm in smoke_hashes
            assert "details.jsonl" in smoke_hashes[arm]

    def test_merged_details_has_1200_rows(self, tmp_path, monkeypatch):
        """merged_details.jsonl has exactly 1200 rows."""
        schedule, ledger, output_dir, labels_data = _build_full_archiveable_schedule(tmp_path, monkeypatch)
        archive_root = tmp_path / "archive"
        archive_path = generate_archive(
            schedule, ledger, output_dir, "deepseek", "deepseek-chat",
            labels_sha256="test", labels_data=labels_data, archive_root=archive_root)
        merged_path = Path(archive_path) / "merged_details.jsonl"
        assert merged_path.exists()
        with open(str(merged_path), "r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())
        assert count == 1200

    def test_archive_contains_budget_and_schedule(self, tmp_path, monkeypatch):
        """Archive contains schedule.json, run_manifest.json, and budget/."""
        schedule, ledger, output_dir, labels_data = _build_full_archiveable_schedule(tmp_path, monkeypatch)
        archive_root = tmp_path / "archive"
        archive_path = generate_archive(
            schedule, ledger, output_dir, "deepseek", "deepseek-chat",
            labels_sha256="test", labels_data=labels_data, archive_root=archive_root)
        assert (Path(archive_path) / "schedule.json").exists()
        assert (Path(archive_path) / "run_manifest.json").exists()
        assert (Path(archive_path) / "budget").exists()

    def test_default_archive_root_is_6b1d(self):
        """Default ARCHIVE_ROOT is docs/phase6/6b1d (not 6b1)."""
        assert ARCHIVE_ROOT == "docs/phase6/6b1d"
        assert "6b1d" in ARCHIVE_ROOT
        assert "6b1/" not in ARCHIVE_ROOT


# ---- TDD: token statistics (P0 #3f) ----

class TestTokenStats:
    """P0 #3f: five-arm token statistics with provider/tiktoken/NOT_AVAILABLE."""

    def test_returns_all_5_arms(self, tmp_path):
        """Token stats returned for all 5 arms."""
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        assert set(stats.keys()) == set(ARMS)

    def test_source_is_tiktoken_or_not_available(self, tmp_path):
        """Without provider usage, source is tiktoken or NOT_AVAILABLE."""
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS:
            assert stats[arm]["source"] in ("tiktoken", "NOT_AVAILABLE")

    def test_provider_usage_preferred(self, tmp_path):
        """When details rows have usage, provider source is used."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)

        for sl in schedule["slices"][:5]:
            rows = []
            for i, cid in enumerate(sl["case_ids"]):
                rows.append({
                    "case_id": cid,
                    "terminal_state": "parsed",
                    "correct": True,
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                })
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()

        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS[:5]:
            if stats[arm]["n"] > 0:
                assert stats[arm]["source"] == "provider"
                assert stats[arm]["avg_input"] == 100
                assert stats[arm]["avg_output"] == 50

    def test_not_available_without_tiktoken(self, tmp_path, monkeypatch):
        """Without tiktoken and no provider usage, returns NOT_AVAILABLE."""
        monkeypatch.setattr(orch, "_HAS_TIKTOKEN", False)
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS:
            assert stats[arm]["source"] == "NOT_AVAILABLE"
            assert stats[arm]["avg_input"] == "NOT_AVAILABLE"

    def test_token_stats_in_comparison_table(self, tmp_path):
        """Comparison table includes token_stats field."""
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        table = generate_comparison_table(schedule, ledger, "deepseek", "deepseek-chat")
        assert "token_stats" in table
        assert "tiktoken_available" in table

    def test_tiktoken_in_requirements(self):
        """tiktoken==0.5.2 must be in requirements-dev.txt."""
        with open("requirements-dev.txt", "r", encoding="utf-8") as f:
            content = f.read()
        assert "tiktoken==0.5.2" in content


# ---- TDD: token statistics P1 #1 (80 cases / per-arm / NOT_AVAILABLE) ----

class _FakeTiktokenEncoder:
    """Fake encoder: encode() returns a list whose length depends on the prompt.

    Length scales with the prompt so different arms (different ziwei_arm -> different
    prompts) produce different counts, proving per-arm rendering rather than a single
    global value.
    """

    def encode(self, text):
        return list(range(len(text)))


class _FakeTiktokenModule:
    """Minimal stand-in for the `tiktoken` module used by compute_token_stats."""

    @staticmethod
    def get_encoding(name):
        return _FakeTiktokenEncoder()


@pytest.fixture
def fake_tiktoken(monkeypatch):
    """Inject a fake tiktoken module so compute_token_stats exercises the fallback path.

    Yields the encoder so tests can inspect call counts if needed. Restores
    _HAS_TIKTOKEN and sys.modules on teardown.
    """
    monkeypatch.setattr(orch, "_HAS_TIKTOKEN", True)
    monkeypatch.setitem(sys.modules, "tiktoken", _FakeTiktokenModule())
    yield _FakeTiktokenEncoder()


class TestTokenStatsP1Fixes:
    """P1 #1: tiktoken fallback must use all 80 cases (not 10), avg_total must be
    NOT_AVAILABLE when output unknown, and source selection must be per-arm."""

    def test_tiktoken_fallback_uses_80_cases_not_10(self, tmp_path, fake_tiktoken):
        """tiktoken fallback n must be 80 (40+40 both years), not the old 10-case sample."""
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS:
            assert stats[arm]["source"] == "tiktoken", \
                f"arm {arm}: expected tiktoken source, got {stats[arm]['source']}"
            assert stats[arm]["n"] == 80, \
                f"arm {arm}: n={stats[arm]['n']} (expected 80, old bug used 10)"

    def test_tiktoken_fallback_avg_total_is_not_available(self, tmp_path, fake_tiktoken):
        """avg_total must be NOT_AVAILABLE when output tokens unknown (tiktoken path).

        Previously avg_total was set equal to avg_input, which is wrong.
        """
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS:
            assert stats[arm]["avg_output"] == "NOT_AVAILABLE", \
                f"arm {arm}: avg_output={stats[arm]['avg_output']}"
            assert stats[arm]["avg_total"] == "NOT_AVAILABLE", \
                f"arm {arm}: avg_total={stats[arm]['avg_total']} (must NOT equal avg_input)"

    def test_tiktoken_fallback_avg_input_is_numeric(self, tmp_path, fake_tiktoken):
        """avg_input must be a numeric mean of rendered prompt lengths."""
        schedule, ledger, _ = _build_completed_schedule_with_accuracy(tmp_path, _ACC)
        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS:
            assert isinstance(stats[arm]["avg_input"], (int, float)), \
                f"arm {arm}: avg_input={stats[arm]['avg_input']}"
            assert stats[arm]["avg_input"] > 0

    def test_per_arm_source_selection_provider_vs_tiktoken(self, tmp_path, fake_tiktoken):
        """One arm with provider usage -> 'provider'; others without -> 'tiktoken'.

        Source selection must be per-arm, not a single global decision.
        """
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)

        # Only b1a_prime slices get provider usage rows
        for sl in schedule["slices"]:
            if sl["arm"] != "b1a_prime":
                continue
            rows = []
            for cid in sl["case_ids"]:
                rows.append({
                    "case_id": cid,
                    "terminal_state": "parsed",
                    "correct": True,
                    "usage": {"prompt_tokens": 200, "completion_tokens": 80},
                })
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()

        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        assert stats["b1a_prime"]["source"] == "provider"
        assert stats["b1a_prime"]["avg_input"] == 200
        assert stats["b1a_prime"]["avg_output"] == 80
        assert stats["b1a_prime"]["avg_total"] == 280
        for arm in ARMS:
            if arm == "b1a_prime":
                continue
            assert stats[arm]["source"] == "tiktoken", \
                f"arm {arm}: expected tiktoken (no provider usage), got {stats[arm]['source']}"
            assert stats[arm]["n"] == 80

    def test_provider_arm_missing_output_tokens_total_not_available(self, tmp_path, fake_tiktoken):
        """Provider usage with input but no output -> avg_total is NOT_AVAILABLE."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)

        for sl in schedule["slices"]:
            rows = []
            for cid in sl["case_ids"]:
                rows.append({
                    "case_id": cid,
                    "terminal_state": "parsed",
                    "correct": True,
                    "usage": {"prompt_tokens": 150},  # no completion_tokens
                })
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()

        stats = compute_token_stats(schedule, ledger, "deepseek", "deepseek-chat")
        for arm in ARMS:
            assert stats[arm]["source"] == "provider"
            assert stats[arm]["avg_input"] == 150
            assert stats[arm]["avg_output"] == "NOT_AVAILABLE"
            assert stats[arm]["avg_total"] == "NOT_AVAILABLE"
