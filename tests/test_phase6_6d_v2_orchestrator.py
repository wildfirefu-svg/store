"""Phase 6 6D v2 orchestrator tests - version constants, resume, schedule."""
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

import scripts.phase6_6d_v2_orchestrator as orch
from scripts.phase6_6d_v2_orchestrator import (
    EXPERIMENT_ID,
    FROZEN_METHOD,
    FROZEN_MODEL,
    FROZEN_PROFILE,
    FROZEN_PROVIDER,
    FROZEN_TEMPERATURE,
    FROZEN_THINKING_MODE,
    SIXD_RECEIPT_REQUIRED_FIELDS,
    TEMPORAL_CONTEXT_VERSION,
    BudgetLedger,
    _build_schedule,
    _compute_experiment_code_fingerprint,
    _prepare_run_context,
    _run_all_slices,
    _validate_frozen_protocol,
    build_run_manifest,
    check_6d_gate,
)

# v1 manifest exists in the repo and is SHA-identical to the v2 manifest
# (asserted by Task 3.11); used here so tests do not depend on generation order.
_V1_MANIFEST = os.path.join(
    PROJECT_ROOT, "docs/phase6/6d/temporal_routed_cases.json")


def _frozen_protocol():
    return _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)


def _run_manifest(code_fp):
    return build_run_manifest(
        FROZEN_PROVIDER, FROZEN_MODEL, _frozen_protocol(), code_fp,
        _V1_MANIFEST)


# -- Task 2.4: version constants --


def test_version_constants_are_6d_v2():
    assert TEMPORAL_CONTEXT_VERSION == "6d-v2"
    assert EXPERIMENT_ID == "6d-v2"


def test_receipt_rejects_v1_version():
    # 构造 temporal_context_version=v1 的 receipt → check_6d_gate 拒绝
    receipt = {f: None for f in SIXD_RECEIPT_REQUIRED_FIELDS}
    receipt["temporal_context_version"] = "6d-v1"
    with pytest.raises(SystemExit):
        check_6d_gate(receipt)


# -- Task 2.4a: resume self-consistency --


def test_resume_self_consistent(tmp_path):
    code_fp = _compute_experiment_code_fingerprint()
    rm = _run_manifest(code_fp)
    # fresh run writes experiment_id=EXPERIMENT_ID into run_context.json
    _prepare_run_context(tmp_path, "self_run", False, rm, code_fp)
    ctx_path = tmp_path / "runs" / "self_run" / "run_context.json"
    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    assert ctx["experiment_id"] == EXPERIMENT_ID
    # resume with the same manifest must pass (v2 can resume itself)
    _prepare_run_context(tmp_path, "self_run", True, rm, code_fp)


def test_resume_rejects_v1_experiment_id(tmp_path):
    code_fp = _compute_experiment_code_fingerprint()
    rm = _run_manifest(code_fp)
    context = dict(rm)
    context["experiment_id"] = "6d-v1"
    context["code_fingerprint"] = code_fp
    context["created_at"] = "2026-01-01T00:00:00"
    runs_root = tmp_path / "runs" / "v1_run"
    runs_root.mkdir(parents=True)
    (runs_root / "run_context.json").write_text(
        json.dumps(context, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit):
        _prepare_run_context(tmp_path, "v1_run", True, rm, code_fp)


# -- Task 3.13-3.17: schedule off/on_limited + off v1 reuse --


def test_schedule_arms_are_off_on_limited(tmp_path):
    schedule = _build_schedule(str(tmp_path / "sched"))
    assert {sl["arm"] for sl in schedule["slices"]} == {
        "b1a_time_off", "b1a_time_on_limited"}
    for sl in schedule["slices"]:
        expected = "off" if sl["arm"] == "b1a_time_off" else "on_limited"
        assert sl["time_context_injection"] == expected


def test_schedule_on_limited_93(tmp_path):
    schedule = _build_schedule(str(tmp_path / "sched"))
    on = [sl for sl in schedule["slices"] if sl["arm"] == "b1a_time_on_limited"]
    assert sum(sl["scheduled_calls"] for sl in on) == 93


def test_schedule_hard_cap_243(tmp_path):
    schedule = _build_schedule(str(tmp_path / "sched"))
    on = [sl for sl in schedule["slices"] if sl["arm"] == "b1a_time_on_limited"]
    assert sum(sl["hard_cap"] for sl in on) == 243


def test_schedule_off_slices_marked_v1_reuse(tmp_path):
    schedule = _build_schedule(str(tmp_path / "sched"))
    off = [sl for sl in schedule["slices"] if sl["arm"] == "b1a_time_off"]
    on = [sl for sl in schedule["slices"] if sl["arm"] == "b1a_time_on_limited"]
    assert len(off) == 15
    assert all(sl["source"] == "v1_reuse" for sl in off)
    assert all(sl["source"] == "run" for sl in on)


def test_off_reuse_skip_precedes_ledger(monkeypatch, tmp_path):
    schedule = _build_schedule(str(tmp_path / "sched"))
    ledger = BudgetLedger(
        str(tmp_path / "ledger.json"), global_hard_cap=10 ** 9)
    run_calls, verify_calls, ledger_checks = [], [], []
    monkeypatch.setattr(
        orch, "_run_slice",
        lambda sl, lg, p, m: run_calls.append(sl["slice_id"]))
    monkeypatch.setattr(
        orch, "_verify_completed_slice",
        lambda sl, p, m: verify_calls.append(sl["slice_id"]))
    orig_slice_completed = ledger.slice_completed

    def spy_slice_completed(slice_id):
        ledger_checks.append(slice_id)
        return orig_slice_completed(slice_id)

    monkeypatch.setattr(ledger, "slice_completed", spy_slice_completed)
    _run_all_slices(schedule, ledger, "deepseek", "deepseek-v4-flash")
    # off (v1_reuse) slices never reach _verify_completed_slice
    assert verify_calls == []
    # only on_limited slices are executed
    assert len(run_calls) == 15
    assert all("b1a_time_on_limited" in sid for sid in run_calls)
    # skip judgment precedes ledger.slice_completed for off slices
    assert not any("b1a_time_off" in sid for sid in ledger_checks)
    # 方案 A: off slices are not recorded in the ledger
    assert not any("b1a_time_off" in sid for sid in ledger._completed)
