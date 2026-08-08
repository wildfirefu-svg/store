"""Phase 6 6D orchestrator tests - schedule/ledger/merge/gate/report/archive/CLI."""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.phase6_6d_orchestrator import (
    FROZEN_METHOD,
    FROZEN_MODEL,
    FROZEN_PROFILE,
    FROZEN_PROVIDER,
    FROZEN_TEMPERATURE,
    FROZEN_THINKING_MODE,
    MODEL_LABEL,
    REPEATS,
    ROUTED_MANIFEST_PATH,
    SIXD_RECEIPT_REQUIRED_FIELDS,
    TEMPORAL_CONTEXT_VERSION,
    BudgetLedger,
    _assign_group_abba_order,
    _build_runner_command,
    _build_schedule,
    _check_completeness,
    _compute_experiment_code_fingerprint,
    _prepare_run_context,
    _validate_frozen_protocol,
    _validate_phase1_receipt,
    build_run_manifest,
    check_6d_gate,
    compute_6d_gate,
)

_MANIFEST = os.path.join(PROJECT_ROOT, ROUTED_MANIFEST_PATH)
_RECEIPT = os.path.join(PROJECT_ROOT, "docs/phase6/6d/phase1_receipt.json")


def _make_detail_row(year, arm, case_id, repeat, correct=True,
                     terminal="parsed"):
    ds = f"baziqa_contest8_{year}_holdout_enriched"
    return {
        "attempt_key": [ds, "baziqa_xjz_reasoned", arm, "main",
                        "deepseek", "deepseek-v4-flash", case_id,
                        repeat, 0, "p0"],
        "case_id": case_id,
        "terminal_state": terminal,
        "correct": correct,
        "predicted_answer": "A",
        "expected_answer": "A",
    }


# -- Schedule tests --


def test_schedule_per_year_grouping():
    sched = _build_schedule("/tmp/6d_test", _MANIFEST)
    by_yg = {}
    for sl in sched["slices"]:
        key = (sl["year"], sl["group"])
        by_yg.setdefault(key, set()).add(sl["slice_id"])
    assert sched["groups_per_year"] == {"2024": 3, "2025": 2}
    for (year, g), ids in by_yg.items():
        assert len(ids) == REPEATS * 2


def test_schedule_group_sizes():
    sched = _build_schedule("/tmp/6d_test", _MANIFEST)
    by_yg = {}
    for sl in sched["slices"]:
        key = (sl["year"], sl["group"])
        if key not in by_yg:
            by_yg[key] = sl["scheduled_calls"]
    assert by_yg[("2024", 0)] == 8
    assert by_yg[("2024", 1)] == 8
    assert by_yg[("2024", 2)] == 2
    assert by_yg[("2025", 0)] == 8
    assert by_yg[("2025", 1)] == 5


def test_schedule_tail_group_scheduled_real_count():
    sched = _build_schedule("/tmp/6d_test", _MANIFEST)
    tail_2024 = [s for s in sched["slices"] if s["year"] == "2024" and s["group"] == 2]
    tail_2025 = [s for s in sched["slices"] if s["year"] == "2025" and s["group"] == 1]
    for s in tail_2024:
        assert s["scheduled_calls"] == 2
        assert s["max_cases"] == 2
    for s in tail_2025:
        assert s["scheduled_calls"] == 5
        assert s["max_cases"] == 5


def test_schedule_global_scheduled_186():
    sched = _build_schedule("/tmp/6d_test", _MANIFEST)
    assert sched["total_scheduled_calls"] == 186


def test_schedule_global_hard_cap_486():
    sched = _build_schedule("/tmp/6d_test", _MANIFEST)
    assert sched["global_hard_cap"] == 486


def test_schedule_arms_are_b1a_time_off_on():
    sched = _build_schedule("/tmp/6d_test", _MANIFEST)
    arms = {s["arm"] for s in sched["slices"]}
    assert arms == {"b1a_time_off", "b1a_time_on"}
    assert len(sched["slices"]) == 30


# -- AB/BA golden mapping --


def test_abba_golden_mapping():
    expected = {
        "2024:g0": "BA", "2024:g1": "AB", "2024:g2": "AB",
        "2025:g0": "AB", "2025:g1": "BA",
    }
    for key, expected_order in expected.items():
        year, g = key.split(":g")
        assert _assign_group_abba_order(year, int(g)) == expected_order
    sched = _build_schedule("/tmp/6d_test", _MANIFEST)
    assert sched["group_abba_order"] == expected


# -- Runner command --


def test_runner_command_includes_frozen_params(tmp_path):
    sched = _build_schedule(str(tmp_path), _MANIFEST)
    sl = sched["slices"][0]
    cmd = _build_runner_command(sl, FROZEN_PROVIDER, FROZEN_MODEL)
    cmd_str = " ".join(cmd)
    assert "--profile" in cmd and FROZEN_PROFILE in cmd
    assert "--method" in cmd and FROZEN_METHOD in cmd
    assert "--model" in cmd and FROZEN_MODEL in cmd
    assert "--thinking-mode" in cmd and FROZEN_THINKING_MODE in cmd
    assert "--temperature" in cmd and "0.0" in cmd
    assert "--ziwei-arm" in cmd and "none" in cmd
    assert "--time-context-injection" in cmd
    assert "--temporal-routed-cases-file" in cmd
    assert sl["routed_manifest_path"] in cmd
    assert "--arm" in cmd and sl["arm"] in cmd


def test_runner_command_off_vs_on_differs(tmp_path):
    sched = _build_schedule(str(tmp_path), _MANIFEST)
    off_sl = next(s for s in sched["slices"] if s["arm"] == "b1a_time_off")
    on_sl = next(s for s in sched["slices"] if s["arm"] == "b1a_time_on")
    off_cmd = _build_runner_command(off_sl, FROZEN_PROVIDER, FROZEN_MODEL)
    on_cmd = _build_runner_command(on_sl, FROZEN_PROVIDER, FROZEN_MODEL)
    off_inj = off_cmd[off_cmd.index("--time-context-injection") + 1]
    on_inj = on_cmd[on_cmd.index("--time-context-injection") + 1]
    assert off_inj == "off"
    assert on_inj == "on"
    off_arm = off_cmd[off_cmd.index("--arm") + 1]
    on_arm = on_cmd[on_cmd.index("--arm") + 1]
    assert off_arm == "b1a_time_off"
    assert on_arm == "b1a_time_on"


# -- Frozen protocol rejection --


def test_frozen_protocol_reject_wrong_model():
    with pytest.raises(SystemExit):
        _validate_frozen_protocol(FROZEN_PROVIDER, "wrong-model",
                                  FROZEN_THINKING_MODE, FROZEN_TEMPERATURE,
                                  FROZEN_PROFILE, FROZEN_METHOD)


def test_frozen_protocol_reject_wrong_thinking():
    with pytest.raises(SystemExit):
        _validate_frozen_protocol(FROZEN_PROVIDER, FROZEN_MODEL,
                                  "enabled", FROZEN_TEMPERATURE,
                                  FROZEN_PROFILE, FROZEN_METHOD)


def test_frozen_protocol_reject_wrong_temperature():
    with pytest.raises(SystemExit):
        _validate_frozen_protocol(FROZEN_PROVIDER, FROZEN_MODEL,
                                  FROZEN_THINKING_MODE, 0.7,
                                  FROZEN_PROFILE, FROZEN_METHOD)


def test_frozen_protocol_reject_wrong_profile():
    with pytest.raises(SystemExit):
        _validate_frozen_protocol(FROZEN_PROVIDER, FROZEN_MODEL,
                                  FROZEN_THINKING_MODE, FROZEN_TEMPERATURE,
                                  "wrong_profile", FROZEN_METHOD)


def test_frozen_protocol_reject_wrong_method():
    with pytest.raises(SystemExit):
        _validate_frozen_protocol(FROZEN_PROVIDER, FROZEN_MODEL,
                                  FROZEN_THINKING_MODE, FROZEN_TEMPERATURE,
                                  FROZEN_PROFILE, "dual_system")


def test_frozen_protocol_accepts_correct():
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    assert protocol["model"] == FROZEN_MODEL
    assert protocol["model_label"] == MODEL_LABEL


# -- Resume protocol drift --


def test_resume_protocol_drift_fail_closed(tmp_path):
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    _prepare_run_context(tmp_path, "test_run", False, rm, code_fp)
    drifted = dict(rm)
    drifted["temporal_context_version"] = "6d-v2"
    with pytest.raises(SystemExit):
        _prepare_run_context(tmp_path, "test_run", True, drifted, code_fp)


def test_resume_abba_drift_fail_closed(tmp_path):
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    _prepare_run_context(tmp_path, "test_run2", False, rm, code_fp)
    drifted = dict(rm)
    drifted["group_abba_order"] = {"2024:g0": "AB"}
    with pytest.raises(SystemExit):
        _prepare_run_context(tmp_path, "test_run2", True, drifted, code_fp)


def test_resume_rejects_dataset_sha256_by_year_drift(tmp_path):
    """Resume must reject when dataset_sha256_by_year drifts."""
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    _prepare_run_context(tmp_path, "ds_year_drift", False, rm, code_fp)
    drifted = dict(rm)
    drifted["dataset_sha256_by_year"] = {"9999": "0" * 64}
    with pytest.raises(SystemExit, match="dataset_sha256_by_year drift"):
        _prepare_run_context(tmp_path, "ds_year_drift", True, drifted, code_fp)


def test_resume_rejects_dataset_set_sha256_drift(tmp_path):
    """Resume must reject when dataset_set_sha256 drifts."""
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    _prepare_run_context(tmp_path, "ds_set_drift", False, rm, code_fp)
    drifted = dict(rm)
    drifted["dataset_set_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="dataset_set_sha256 drift"):
        _prepare_run_context(tmp_path, "ds_set_drift", True, drifted, code_fp)


def test_resume_rejects_experiment_conditions_drift(tmp_path):
    """Resume must reject when experiment_conditions drift."""
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    _prepare_run_context(tmp_path, "exp_cond_drift", False, rm, code_fp)
    drifted = dict(rm)
    drifted["experiment_conditions"] = ["on", "off"]
    with pytest.raises(SystemExit, match="experiment_conditions drift"):
        _prepare_run_context(tmp_path, "exp_cond_drift", True, drifted, code_fp)


def test_no_cross_orchestrator_resume(tmp_path):
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    context = dict(rm)
    context["experiment_id"] = "6b2"
    context["code_fingerprint"] = code_fp
    context["created_at"] = "2026-01-01T00:00:00"
    runs_root = tmp_path / "runs" / "cross_run"
    runs_root.parent.mkdir(parents=True, exist_ok=True)
    runs_root.mkdir()
    import json as _json
    (runs_root / "run_context.json").write_text(
        _json.dumps(context, ensure_ascii=False), encoding="utf-8")
    from scripts.phase6_6d_orchestrator import _prepare_run_context
    with pytest.raises(SystemExit):
        _prepare_run_context(tmp_path, "cross_run", True, rm, code_fp)


# -- Receipt fields --


def test_receipt_fields_complete():
    expected = (
        "verdict", "stage", "run_id", "user_run_id", "archive_dir",
        "audit_index_sha256", "provider", "model",
        "thinking_mode", "model_label",
        "code_fingerprint", "dataset_set_sha256",
        "temporal_context_version", "experiment_conditions",
        "extraction_strategy_sha256", "temporal_routed_cases_sha256",
        "condition_manifest_sha256", "dataset_sha256_by_year",
        "group_abba_order",
    )
    assert SIXD_RECEIPT_REQUIRED_FIELDS == expected
    assert len(SIXD_RECEIPT_REQUIRED_FIELDS) == 19


def test_check_6d_gate_rejects_missing_fields():
    with pytest.raises(SystemExit):
        check_6d_gate({"verdict": "PROMOTE"})


def _make_complete_receipt(archive_dir, audit_sha):
    """Build a receipt with all required fields present and valid protocol
    fields, so checks reach the audit-verification branch. archive_dir and
    audit_index_sha256 are set explicitly (None exercises the fail-closed
    missing-value branches)."""
    receipt = {f: "x" for f in SIXD_RECEIPT_REQUIRED_FIELDS}
    receipt["temporal_context_version"] = TEMPORAL_CONTEXT_VERSION
    receipt["experiment_conditions"] = ["off", "on"]
    receipt["archive_dir"] = archive_dir
    receipt["audit_index_sha256"] = audit_sha
    return receipt


def test_check_6d_gate_accepts_complete(tmp_path):
    import hashlib as _hashlib
    import json as _json
    archive = tmp_path / "archive"
    archive.mkdir()
    audit_path = archive / "audit_index.json"
    audit_path.write_text(
        _json.dumps({"indexed": ["merged_details.jsonl"]}, ensure_ascii=False),
        encoding="utf-8")
    audit_sha = _hashlib.sha256(audit_path.read_bytes()).hexdigest()
    receipt = _make_complete_receipt(
        archive_dir=str(archive), audit_sha=audit_sha)
    assert check_6d_gate(receipt) is True


# -- Audit gate fail-closed --


def test_audit_gate_rejects_missing_archive_dir():
    """archive_dir missing (None) in otherwise-complete receipt -> SystemExit."""
    receipt = _make_complete_receipt(archive_dir=None, audit_sha="abc")
    with pytest.raises(SystemExit, match="archive_dir missing"):
        check_6d_gate(receipt)


def test_audit_gate_rejects_missing_audit_index_sha():
    """audit_index_sha256 missing (None) -> SystemExit."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        receipt = _make_complete_receipt(archive_dir=tmpdir, audit_sha=None)
        with pytest.raises(SystemExit, match="audit_index_sha256 missing"):
            check_6d_gate(receipt)


def test_audit_gate_rejects_nonexistent_archive_dir():
    """archive_dir doesn't exist -> SystemExit."""
    receipt = _make_complete_receipt(
        archive_dir="Z:/definitely-missing-6d-archive", audit_sha="abc")
    with pytest.raises(SystemExit, match="archive_dir not found"):
        check_6d_gate(receipt)


def test_audit_gate_rejects_missing_audit_index():
    """archive_dir exists but audit_index.json missing -> SystemExit."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        receipt = _make_complete_receipt(archive_dir=tmpdir, audit_sha="abc")
        with pytest.raises(SystemExit, match="audit_index.json missing"):
            check_6d_gate(receipt)


def test_audit_gate_rejects_sha_mismatch():
    """audit_index.json exists but SHA mismatch -> SystemExit."""
    import json as _json
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_path = os.path.join(tmpdir, "audit_index.json")
        with open(audit_path, "w", encoding="utf-8") as f:
            _json.dump({"test": "data"}, f)
        receipt = _make_complete_receipt(archive_dir=tmpdir, audit_sha="wrong_sha")
        with pytest.raises(SystemExit, match="audit_index_sha256 mismatch"):
            check_6d_gate(receipt)


# -- Provenance cross-validation --


def test_provenance_8_temporal_run_fields():
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    temporal_fields = (
        "temporal_context_version", "experiment_conditions",
        "extraction_strategy_sha256", "temporal_routed_cases_sha256",
        "condition_manifest_sha256", "dataset_sha256_by_year",
        "dataset_set_sha256", "group_abba_order",
    )
    for f in temporal_fields:
        assert f in rm, f"missing temporal field: {f}"
    assert rm["temporal_context_version"] == TEMPORAL_CONTEXT_VERSION
    assert rm["experiment_conditions"] == ["off", "on"]


def test_provenance_run_context_has_temporal_fields(tmp_path):
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    runs_root, context = _prepare_run_context(tmp_path, "prov_run", False, rm, code_fp)
    temporal_fields = (
        "temporal_context_version", "experiment_conditions",
        "extraction_strategy_sha256", "temporal_routed_cases_sha256",
        "condition_manifest_sha256", "dataset_sha256_by_year",
        "dataset_set_sha256", "group_abba_order",
    )
    for f in temporal_fields:
        assert context[f] == rm[f], f"run_context {f} != run_manifest"


# -- dataset_sha256_by_year --


def test_dataset_sha256_by_year_dual_year():
    from scripts.phase6_6d_orchestrator import _compute_dataset_sha256_by_year
    ds = _compute_dataset_sha256_by_year(_MANIFEST)
    assert "2024" in ds and "2025" in ds
    assert len(ds) == 2
    assert all(len(v) == 64 for v in ds.values())


def test_no_single_dataset_sha256_field():
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    assert "dataset_sha256" not in rm
    assert "dataset_set_sha256" in rm
    assert "dataset_sha256_by_year" in rm


# -- BudgetLedger --


def test_budget_ledger_tracks_attempts(tmp_path):
    ledger = BudgetLedger(str(tmp_path / "ledger.json"), global_hard_cap=486)
    assert ledger.hard_cap == 486
    assert ledger.total_attempted == 0
    assert ledger.remaining_budget() == 486
    ledger.record_slice_completed("s1", 8, 8)
    assert ledger.total_attempted == 8
    assert ledger.total_scheduled == 8
    assert ledger.slice_completed("s1")
    assert ledger.remaining_budget() == 478


def test_budget_ledger_resume(tmp_path):
    ledger = BudgetLedger(str(tmp_path / "ledger.json"), global_hard_cap=486)
    ledger.record_slice_completed("s1", 8, 8)
    ledger.record_slice_completed("s2", 5, 5)
    ledger2 = BudgetLedger(str(tmp_path / "ledger.json"), global_hard_cap=486)
    assert ledger2.total_attempted == 13
    assert ledger2.slice_completed("s1")
    assert ledger2.slice_completed("s2")
    assert ledger2.remaining_budget() == 473


def test_budget_ledger_reject_hard_cap_breach(tmp_path):
    ledger = BudgetLedger(str(tmp_path / "ledger.json"), global_hard_cap=10)
    ledger.record_slice_completed("s1", 8, 8)
    with pytest.raises(SystemExit):
        ledger.record_slice_completed("s2", 5, 5)


# -- Completeness --


def test_completeness_pass(tmp_path):
    sched = _build_schedule(str(tmp_path), _MANIFEST)
    merged = []
    for sl in sched["slices"]:
        for cid in sl["case_ids"]:
            merged.append(_make_detail_row(sl["year"], sl["arm"], cid, sl["repeat"]))
    assert _check_completeness(merged, sched) == "PASS"


def test_completeness_missing_on(tmp_path):
    sched = _build_schedule(str(tmp_path), _MANIFEST)
    merged = []
    for sl in sched["slices"]:
        if sl["arm"] == "b1a_time_off":
            for cid in sl["case_ids"]:
                merged.append(_make_detail_row(sl["year"], sl["arm"], cid, sl["repeat"]))
    result = _check_completeness(merged, sched)
    assert result != "PASS"


# -- Gate: BLOCKED branches --


def test_gate_blocked_call_failed_off():
    rows = [_make_detail_row("2024", "b1a_time_off", "c1", 0, terminal="call_failed")]
    rows += [_make_detail_row("2024", "b1a_time_on", "c1", 0)]
    result = compute_6d_gate(rows, 1)
    assert result["verdict"] == "BLOCKED"


def test_gate_blocked_call_failed_on():
    rows = [_make_detail_row("2024", "b1a_time_off", "c1", 0)]
    rows += [_make_detail_row("2024", "b1a_time_on", "c1", 0, terminal="call_failed")]
    result = compute_6d_gate(rows, 1)
    assert result["verdict"] == "BLOCKED"


def test_gate_blocked_parser_rate_off():
    rows = []
    for i in range(10):
        rows.append(_make_detail_row("2024", "b1a_time_off", f"c{i}", 0,
                                     terminal="invalid"))
    rows += [_make_detail_row("2024", "b1a_time_on", "c0", 0)]
    result = compute_6d_gate(rows, 1)
    assert result["verdict"] == "BLOCKED"


def test_gate_blocked_parser_rate_on():
    rows = [_make_detail_row("2024", "b1a_time_off", "c0", 0)]
    for i in range(10):
        rows.append(_make_detail_row("2024", "b1a_time_on", f"c{i}", 0,
                                     terminal="invalid"))
    result = compute_6d_gate(rows, 1)
    assert result["verdict"] == "BLOCKED"


def test_gate_blocked_early_return_no_overwrite():
    rows = [_make_detail_row("2024", "b1a_time_off", "c1", 0, terminal="call_failed")]
    rows += [_make_detail_row("2024", "b1a_time_on", "c1", 0, correct=True)]
    result = compute_6d_gate(rows, 1)
    assert result["verdict"] == "BLOCKED"
    assert result.get("paired_delta") is None


# -- Gate: paired_delta denominator --


def test_gate_paired_delta_denominator_n3():
    n_cases = 2
    rows = []
    for cid in ["c0", "c1"]:
        for rep in range(3):
            rows.append(_make_detail_row("2024", "b1a_time_off", cid, rep, correct=False))
            rows.append(_make_detail_row("2024", "b1a_time_on", cid, rep, correct=True))
    result = compute_6d_gate(rows, n_cases)
    assert result["verdict"] == "PROMOTE"
    assert abs(result["paired_delta"] - (6 / (n_cases * 3))) < 1e-9


# -- Gate: accuracy branches --


def test_gate_promote():
    n_cases = 2
    rows = []
    for cid in ["c0", "c1"]:
        for rep in range(3):
            rows.append(_make_detail_row("2024", "b1a_time_off", cid, rep, correct=False))
            rows.append(_make_detail_row("2024", "b1a_time_on", cid, rep, correct=True))
    result = compute_6d_gate(rows, n_cases)
    assert result["verdict"] == "PROMOTE"
    assert result["paired_delta"] >= 0.05
    assert result["min_case_delta"] >= 0


def test_gate_review_required():
    n_cases = 10
    rows = []
    for i in range(n_cases - 1):
        for rep in range(3):
            rows.append(_make_detail_row("2024", "b1a_time_off", f"c{i}", rep, correct=False))
            rows.append(_make_detail_row("2024", "b1a_time_on", f"c{i}", rep, correct=True))
    for rep in range(3):
        rows.append(_make_detail_row("2024", "b1a_time_off", "c9", rep, correct=True))
        rows.append(_make_detail_row("2024", "b1a_time_on", "c9", rep, correct=False))
    result = compute_6d_gate(rows, n_cases)
    assert result["paired_delta"] >= 0.05
    assert result["min_case_delta"] < 0
    assert result["verdict"] == "REVIEW_REQUIRED"


def test_gate_non_inferior():
    n_cases = 10
    rows = []
    for cid in range(n_cases):
        for rep in range(3):
            rows.append(_make_detail_row("2024", "b1a_time_off", f"c{cid}", rep, correct=True))
            rows.append(_make_detail_row("2024", "b1a_time_on", f"c{cid}", rep, correct=True))
    result = compute_6d_gate(rows, n_cases)
    assert result["paired_delta"] == 0.0
    assert -0.02 <= result["paired_delta"] < 0.05
    assert result["verdict"] == "NON_INFERIOR"


def test_gate_rollback():
    n_cases = 2
    rows = []
    for cid in ["c0", "c1"]:
        for rep in range(3):
            rows.append(_make_detail_row("2024", "b1a_time_off", cid, rep, correct=True))
            rows.append(_make_detail_row("2024", "b1a_time_on", cid, rep, correct=False))
    result = compute_6d_gate(rows, n_cases)
    assert result["paired_delta"] < -0.02
    assert result["verdict"] == "ROLLBACK"


# -- CLI --


def test_run_dev_help_works():
    import subprocess
    r = subprocess.run(
        [sys.executable, "scripts/phase6_6d_orchestrator.py", "run_dev", "--help"],
        capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=30)
    assert r.returncode == 0
    assert "--provider" in r.stdout
    assert "--model" in r.stdout
    assert "--output-dir" in r.stdout
    assert "--run-id" in r.stdout


# -- Phase1 receipt validation --


def test_phase1_receipt_valid():
    receipt = _validate_phase1_receipt(_RECEIPT, _MANIFEST)
    assert receipt["status"] == "PASS"
    assert receipt["n_routed"] >= 20


def test_phase1_receipt_reject_blocked(tmp_path):
    import json as _json
    bad = _json.loads(open(_RECEIPT, encoding="utf-8").read())
    bad["status"] = "BLOCKED"
    bad_path = str(tmp_path / "bad_receipt.json")
    open(bad_path, "w", encoding="utf-8").write(_json.dumps(bad))
    with pytest.raises(SystemExit):
        _validate_phase1_receipt(bad_path, _MANIFEST)


def test_phase1_receipt_reject_low_n_routed(tmp_path):
    import json as _json
    bad = _json.loads(open(_RECEIPT, encoding="utf-8").read())
    bad["n_routed"] = 10
    bad_path = str(tmp_path / "bad_receipt.json")
    open(bad_path, "w", encoding="utf-8").write(_json.dumps(bad))
    with pytest.raises(SystemExit):
        _validate_phase1_receipt(bad_path, _MANIFEST)


def test_phase1_receipt_reject_sha_mismatch(tmp_path):
    import json as _json
    bad = _json.loads(open(_RECEIPT, encoding="utf-8").read())
    bad["temporal_routed_cases_sha256"] = "0" * 64
    bad_path = str(tmp_path / "bad_receipt.json")
    open(bad_path, "w", encoding="utf-8").write(_json.dumps(bad))
    with pytest.raises(SystemExit):
        _validate_phase1_receipt(bad_path, _MANIFEST)


def test_run_dev_validates_phase1_receipt(tmp_path):
    import subprocess
    r = subprocess.run(
        [sys.executable, "scripts/phase6_6d_orchestrator.py", "run_dev",
         "--provider", "deepseek", "--model", "deepseek-v4-flash",
         "--output-dir", str(tmp_path / "out"),
         "--run-id", "test6d",
         "--phase1-receipt", "nonexistent_receipt.json"],
        capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=30)
    assert r.returncode != 0


# -- Fake-runner E2E --


def _install_fake_runner(monkeypatch, captured=None):
    import types as _types

    import scripts.phase6_6d_orchestrator as _m

    def _flag(cmd, name):
        return cmd[cmd.index(name) + 1]

    def fake_run(cmd, capture_output=False, text=False, timeout=None, cwd=None):
        arm = _flag(cmd, "--arm")
        repeat = int(_flag(cmd, "--repeat-idx"))
        dataset = _flag(cmd, "--dataset")
        case_ids_file = _flag(cmd, "--case-ids-file")
        detail_path = _flag(cmd, "--case-details-jsonl")
        output_dir = _flag(cmd, "--output-dir")
        provider = _flag(cmd, "--provider")
        model = _flag(cmd, "--model")
        case_ids = json.loads(open(case_ids_file, encoding="utf-8").read())
        ds_base = os.path.splitext(os.path.basename(dataset))[0]
        os.makedirs(output_dir, exist_ok=True)
        with open(detail_path, "w", encoding="utf-8") as f:
            for cid in case_ids:
                correct = arm == "b1a_time_on"
                row = {
                    "attempt_key": [ds_base, FROZEN_PROFILE, arm, "main",
                                    provider, model, cid, repeat, 0, "p0"],
                    "case_id": cid,
                    "terminal_state": "parsed",
                    "correct": correct,
                    "predicted_answer": "A" if correct else "B",
                    "expected_answer": "A",
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        events_path = detail_path.replace(".jsonl", ".events.jsonl")
        with open(events_path, "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"kind": "call_attempt"}) + "\n" for _cid in case_ids)
            f.write(json.dumps({"kind": "call_meta",
                                "response_model": model}) + "\n")
        manifest_path = detail_path.replace(".jsonl", ".manifest.json")
        open(manifest_path, "w", encoding="utf-8").write("{}")
        if captured is not None:
            captured.append({"arm": arm, "repeat": repeat,
                             "n_cases": len(case_ids)})
        return _types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(_m.subprocess, "run", fake_run)
    return _m


def test_fake_runner_no_network_calls(tmp_path, monkeypatch):
    import claude_api
    import scripts.phase6_6d_orchestrator as m

    def _boom(*a, **kw):
        raise AssertionError(
            "network call detected: call_model_messages_sync_with_meta "
            "must not be invoked at READY_FOR_SMOKE stage")

    monkeypatch.setattr(claude_api, "call_model_messages_sync_with_meta", _boom)
    monkeypatch.setattr(m, "ARCHIVE_ROOT", str(tmp_path / "archive"))
    _install_fake_runner(monkeypatch)
    result = m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                       str(tmp_path / "out"), run_id="fake-no-net")
    assert result["status"] == "ok"
    assert result["gate"]["verdict"] != "BLOCKED"


def test_fake_runner_paired_e2e(tmp_path, monkeypatch):
    import scripts.phase6_6d_orchestrator as m
    monkeypatch.setattr(m, "ARCHIVE_ROOT", str(tmp_path / "archive"))
    captured = []
    _install_fake_runner(monkeypatch, captured=captured)
    run_id = "fake-paired-e2e"
    result = m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                       str(tmp_path / "out"), run_id=run_id)
    gate = result["gate"]
    assert gate["verdict"] in ("PROMOTE", "REVIEW_REQUIRED",
                               "NON_INFERIOR", "ROLLBACK")
    assert gate["verdict"] != "BLOCKED"
    assert len(captured) == 30
    arms = {c["arm"] for c in captured}
    assert arms == {"b1a_time_off", "b1a_time_on"}
    runs_root = tmp_path / "out" / "runs" / run_id
    report_md = (runs_root / "dev" / "report.md").read_text(encoding="utf-8")
    assert gate["verdict"] in report_md
    receipt = result["archive"]["receipt"]
    for f in ("temporal_context_version", "group_abba_order",
              "experiment_conditions", "extraction_strategy_sha256",
              "temporal_routed_cases_sha256", "condition_manifest_sha256",
              "dataset_sha256_by_year", "dataset_set_sha256"):
        assert f in receipt, f"receipt missing temporal field: {f}"
    assert receipt["temporal_context_version"] == TEMPORAL_CONTEXT_VERSION
    assert receipt["experiment_conditions"] == ["off", "on"]
    archive_dir = result["archive"]["archive_dir"]
    assert os.path.exists(os.path.join(archive_dir, "audit_index.json"))
    assert os.path.exists(os.path.join(archive_dir, "merged_details.jsonl"))
    published = runs_root / "gates" / "dev_gate.json"
    assert published.exists()
    pub = json.loads(published.read_text(encoding="utf-8"))
    assert pub["verdict"] == gate["verdict"]
    assert pub["temporal_context_version"] == TEMPORAL_CONTEXT_VERSION


# -- Issue fixes: min_case_delta normalization, manifest persistence, report --


def test_min_case_delta_normalized_by_repeats():
    """min_case_delta must be min(case_delta) / REPEATS per spec."""
    # Case A: off 0/3 correct, on 3/3 correct -> delta = +3
    # Case B: off 2/3 correct, on 0/3 correct -> delta = -2
    # min delta = -2, normalized = -2/3
    rows = []
    for rep in range(REPEATS):
        rows.append(_make_detail_row("2024", "b1a_time_off", "A", rep, correct=False))
        rows.append(_make_detail_row("2024", "b1a_time_on", "A", rep, correct=True))
    for rep in range(REPEATS):
        rows.append(_make_detail_row("2024", "b1a_time_off", "B", rep, correct=rep < 2))
        rows.append(_make_detail_row("2024", "b1a_time_on", "B", rep, correct=False))
    result = compute_6d_gate(rows, 2)
    assert result["min_case_delta"] == pytest.approx(-2 / 3, abs=1e-6)


def test_run_manifest_persisted(tmp_path, monkeypatch):
    """run_manifest.json must be persisted and pass four-layer provenance."""
    import scripts.phase6_6d_orchestrator as m
    monkeypatch.setattr(m, "ARCHIVE_ROOT", str(tmp_path / "archive"))
    _install_fake_runner(monkeypatch)
    run_id = "fake-manifest"
    result = m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                       str(tmp_path / "out"), run_id=run_id)
    runs_root = tmp_path / "out" / "runs" / run_id
    manifest_path = runs_root / "run_manifest.json"
    context_path = runs_root / "run_context.json"
    assert manifest_path.exists(), "run_manifest.json not persisted"
    assert context_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    context = json.loads(context_path.read_text(encoding="utf-8"))
    for f in ("temporal_context_version", "group_abba_order",
              "experiment_conditions", "extraction_strategy_sha256",
              "temporal_routed_cases_sha256", "condition_manifest_sha256",
              "dataset_sha256_by_year", "dataset_set_sha256",
              "provider", "model", "thinking_mode", "model_label",
              "code_fingerprint"):
        assert manifest[f] == context[f], f"manifest/context {f} mismatch"
    archive_dir = result["archive"]["archive_dir"]
    audit = json.loads(
        open(os.path.join(archive_dir, "audit_index.json"), encoding="utf-8").read())
    receipt = result["archive"]["receipt"]
    for f in ("temporal_context_version", "group_abba_order",
              "experiment_conditions", "dataset_set_sha256",
              "condition_manifest_sha256"):
        assert manifest[f] == audit[f], f"manifest/audit {f} mismatch"
        assert manifest[f] == receipt[f], f"manifest/receipt {f} mismatch"


def test_report_includes_accuracy_and_yearly_breakdown(tmp_path, monkeypatch):
    """report.md must include off/on accuracy, yearly breakdown, non-zero deltas."""
    import scripts.phase6_6d_orchestrator as m
    monkeypatch.setattr(m, "ARCHIVE_ROOT", str(tmp_path / "archive"))
    _install_fake_runner(monkeypatch)
    run_id = "fake-report"
    result = m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                       str(tmp_path / "out"), run_id=run_id)
    runs_root = tmp_path / "out" / "runs" / run_id
    report_md = (runs_root / "dev" / "report.md").read_text(encoding="utf-8")
    assert "## Accuracy" in report_md
    assert "| OFF |" in report_md
    assert "| ON  |" in report_md
    assert "## Yearly Breakdown" in report_md
    assert "| 2024 |" in report_md
    assert "| 2025 |" in report_md
    assert "## Non-zero Case Deltas" in report_md
    summary = json.loads(
        (runs_root / "dev" / "summary.json").read_text(encoding="utf-8"))
    assert "accuracy" in summary
    assert summary["accuracy"]["off"]["total"] == 93
    assert summary["accuracy"]["on"]["total"] == 93
    assert "yearly_breakdown" in summary
    assert "nonzero_case_deltas" in summary
    assert result["gate"]["min_case_delta"] == pytest.approx(1.0, abs=1e-9)


def test_four_layer_provenance_rejects_missing_manifest(tmp_path):
    """_validate_four_layer_provenance rejects when run_manifest.json missing."""
    from scripts.phase6_6d_orchestrator import _validate_four_layer_provenance
    runs_root = tmp_path / "runs" / "x"
    runs_root.mkdir(parents=True)
    (runs_root / "run_context.json").write_text("{}", encoding="utf-8")
    receipt = {"archive_dir": str(tmp_path / "archive")}
    with pytest.raises(SystemExit, match="run_manifest.json missing"):
        _validate_four_layer_provenance(runs_root, receipt)



# -- P0 fixes: validate-before-publish, fingerprint, atomic manifest resume --


def test_four_layer_failure_no_published_receipt(tmp_path, monkeypatch):
    """When four-layer validation fails, dev_gate.json must NOT be published."""
    import scripts.phase6_6d_orchestrator as m
    monkeypatch.setattr(m, "ARCHIVE_ROOT", str(tmp_path / "archive"))
    _install_fake_runner(monkeypatch)

    def _boom(runs_root, receipt):
        raise SystemExit("four-layer provenance reject: forced failure")

    monkeypatch.setattr(m, "_validate_four_layer_provenance", _boom)
    run_id = "fake-4layer-fail"
    with pytest.raises(SystemExit, match="forced failure"):
        m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                  str(tmp_path / "out"), run_id=run_id)
    runs_root = tmp_path / "out" / "runs" / run_id
    published = runs_root / "gates" / "dev_gate.json"
    assert not published.exists(), \
        "dev_gate.json must not be published on four-layer failure"
    failures_path = runs_root / "run_failures.jsonl"
    assert failures_path.exists(), "run_failures.jsonl must record the failure"
    lines = failures_path.read_text(encoding="utf-8").strip().splitlines()
    assert any("forced failure" in ln for ln in lines), \
        "run_failures.jsonl must record the four-layer failure reason"


def test_corrupted_archive_receipt_not_published(tmp_path, monkeypatch):
    """If archive receipt is corrupted after _create_archive, run_dev must
    fail and dev_gate.json must NOT be published."""
    import scripts.phase6_6d_orchestrator as m

    monkeypatch.setattr(m, "ARCHIVE_ROOT", str(tmp_path / "archive"))
    _install_fake_runner(monkeypatch)

    _orig_create_archive = m._create_archive

    def _corrupting_create_archive(*args, **kwargs):
        result = _orig_create_archive(*args, **kwargs)
        receipt_path = os.path.join(result["archive_dir"], "dev_gate.json")
        with open(receipt_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"verdict": "CORRUPTED"}))
        return result

    monkeypatch.setattr(m, "_create_archive", _corrupting_create_archive)

    run_id = "fake-corrupt-receipt"
    with pytest.raises(SystemExit, match="archive receipt drift"):
        m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                  str(tmp_path / "out"), run_id=run_id)
    runs_root = tmp_path / "out" / "runs" / run_id
    published = runs_root / "gates" / "dev_gate.json"
    assert not published.exists(), \
        "dev_gate.json must not be published when archive receipt is corrupted"
    failures_path = runs_root / "run_failures.jsonl"
    assert failures_path.exists(), "run_failures.jsonl must record the failure"
    lines = failures_path.read_text(encoding="utf-8").strip().splitlines()
    assert any("archive receipt drift" in ln for ln in lines), \
        "run_failures.jsonl must record the drift failure reason"


def test_four_layer_validator_in_fingerprint():
    """_validate_four_layer_provenance must be in the fingerprint function list."""
    import inspect

    from scripts.phase6_6d_orchestrator import _compute_experiment_code_fingerprint
    src = inspect.getsource(_compute_experiment_code_fingerprint)
    assert "_validate_four_layer_provenance" in src


def test_resume_rejects_missing_manifest(tmp_path):
    """Resume must fail-closed when run_manifest.json is missing."""
    import scripts.phase6_6d_orchestrator as m
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    # Create run_context.json but NOT run_manifest.json
    _prepare_run_context(tmp_path, "no_manifest", False, rm, code_fp)
    runs_root = tmp_path / "runs" / "no_manifest"
    assert (runs_root / "run_context.json").exists()
    assert not (runs_root / "run_manifest.json").exists()
    with pytest.raises(SystemExit, match="run_manifest.json missing"):
        m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                  str(tmp_path), run_id="no_manifest", resume=True)


def test_resume_rejects_manifest_drift(tmp_path):
    """Resume must fail-closed when run_manifest.json fields drift."""
    import scripts.phase6_6d_orchestrator as m
    protocol = _validate_frozen_protocol(
        FROZEN_PROVIDER, FROZEN_MODEL, FROZEN_THINKING_MODE,
        FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD)
    code_fp = _compute_experiment_code_fingerprint()
    rm = build_run_manifest(FROZEN_PROVIDER, FROZEN_MODEL, protocol, code_fp, _MANIFEST)
    _prepare_run_context(tmp_path, "drift_manifest", False, rm, code_fp)
    runs_root = tmp_path / "runs" / "drift_manifest"
    # Write a manifest with a drifted provenance field
    drifted = json.loads(json.dumps(rm))
    drifted["model"] = "different-model"
    (runs_root / "run_manifest.json").write_text(
        json.dumps(drifted, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")
    with pytest.raises(SystemExit, match="run_manifest.json drift"):
        m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                  str(tmp_path), run_id="drift_manifest", resume=True)


def test_report_contains_accurate_numbers(tmp_path, monkeypatch):
    """report.md must contain off/on accuracy, yearly delta, and non-zero case count."""
    import scripts.phase6_6d_orchestrator as m
    monkeypatch.setattr(m, "ARCHIVE_ROOT", str(tmp_path / "archive"))
    _install_fake_runner(monkeypatch)
    run_id = "fake-numbers"
    result = m.run_dev(FROZEN_PROVIDER, FROZEN_MODEL,
                       str(tmp_path / "out"), run_id=run_id)
    runs_root = tmp_path / "out" / "runs" / run_id
    report_md = (runs_root / "dev" / "report.md").read_text(encoding="utf-8")
    summary = json.loads(
        (runs_root / "dev" / "summary.json").read_text(encoding="utf-8"))
    off = summary["accuracy"]["off"]
    on = summary["accuracy"]["on"]
    # Fake runner: off always wrong, on always right
    assert off["correct"] == 0
    assert on["correct"] == on["total"]
    assert on["total"] > 0
    # report.md must contain the exact accuracy rows
    assert f"| OFF | {off['correct']} | {off['total']} | {off['rate'] * 100:.2f}% |" in report_md
    assert f"| ON  | {on['correct']} | {on['total']} | {on['rate'] * 100:.2f}% |" in report_md
    # Yearly breakdown rows present
    for year in summary["yearly_breakdown"]:
        assert f"| {year} |" in report_md
    # Non-zero case deltas: fake runner makes every case delta positive
    assert "## Non-zero Case Deltas" in report_md
    assert summary["nonzero_case_deltas"], \
        "expected non-zero case deltas from fake runner"
    assert result["gate"]["paired_delta"] == pytest.approx(1.0, abs=1e-9)


def test_publish_receipt_atomic_writes_validated_bytes(tmp_path):
    """Published receipt must be the exact validated bytes, not re-read from source."""
    import hashlib
    import json

    from scripts.phase6_6d_orchestrator import _publish_receipt_atomic

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    gate_dir = tmp_path / "gates"

    # Create a source receipt on disk
    src_receipt = {"verdict": "NON_INFERIOR", "test": True}
    src_bytes = json.dumps(src_receipt, ensure_ascii=False, indent=2).encode("utf-8")
    src_path = archive_dir / "dev_gate.json"
    src_path.write_bytes(src_bytes)

    # Validate and publish
    validated_sha = hashlib.sha256(src_bytes).hexdigest()
    arch = {"archive_dir": str(archive_dir)}
    _publish_receipt_atomic(
        arch, gate_dir, "dev_gate.json",
        validated_bytes=src_bytes,
        expected_sha256=validated_sha)

    # Published file must match validated bytes exactly
    published = (gate_dir / "dev_gate.json").read_bytes()
    assert published == src_bytes, "published bytes != validated bytes"

    # Now corrupt the source AFTER publication
    src_path.write_text('{"verdict": "CORRUPTED_AFTER"}')

    # Published file must still be correct (source not re-read)
    published2 = (gate_dir / "dev_gate.json").read_bytes()
    assert published2 == src_bytes, "published changed after source corruption"


def test_publish_receipt_rejects_sha_mismatch(tmp_path):
    """If tmp file SHA != expected_sha256, publication must fail."""
    import pytest

    from scripts.phase6_6d_orchestrator import _publish_receipt_atomic

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    gate_dir = tmp_path / "gates"

    src_bytes = b'{"verdict": "OK"}'
    wrong_sha = "0" * 64

    arch = {"archive_dir": str(archive_dir)}
    with pytest.raises(SystemExit, match="SHA mismatch"):
        _publish_receipt_atomic(
            arch, gate_dir, "dev_gate.json",
            validated_bytes=src_bytes,
            expected_sha256=wrong_sha)

    # Published file must NOT exist
    assert not (gate_dir / "dev_gate.json").exists()


def test_publish_receipt_in_fingerprint():
    """_publish_receipt_atomic must be in the fingerprint function list."""
    import inspect

    from scripts.phase6_6d_orchestrator import _compute_experiment_code_fingerprint
    src = inspect.getsource(_compute_experiment_code_fingerprint)
    assert "_publish_receipt_atomic" in src


def test_toctou_source_corruption_during_publish(tmp_path, monkeypatch):
    """Corrupting source during publish must not affect published receipt.

    This tests the TOCTOU fix: validated_bytes are written directly,
    source file is never re-read during publication.
    """
    import hashlib
    import json
    from pathlib import Path

    from scripts.phase6_6d_orchestrator import _publish_receipt_atomic

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    gate_dir = tmp_path / "gates"

    src_receipt = {"verdict": "NON_INFERIOR"}
    src_bytes = json.dumps(src_receipt, ensure_ascii=False, indent=2).encode("utf-8")
    src_path = archive_dir / "dev_gate.json"
    src_path.write_bytes(src_bytes)
    validated_sha = hashlib.sha256(src_bytes).hexdigest()

    original_write = Path.write_bytes
    triggered = []

    def corrupting_write(self, data):
        # Path.with_suffix(".tmp") on dev_gate.json -> dev_gate.tmp
        if self.name == "dev_gate.tmp":
            triggered.append(True)
            src_path.write_text('{"verdict": "CORRUPTED_DURING"}')
        return original_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", corrupting_write)

    arch = {"archive_dir": str(archive_dir)}
    _publish_receipt_atomic(
        arch, gate_dir, "dev_gate.json",
        validated_bytes=src_bytes,
        expected_sha256=validated_sha)

    assert triggered, "corruption hook was never triggered (tmp name mismatch)"
    published = (gate_dir / "dev_gate.json").read_bytes()
    assert published == src_bytes, "published bytes were affected by source corruption"
    assert json.loads(published)["verdict"] == "NON_INFERIOR"
