#!/usr/bin/env python3
"""Phase 6 6B2 sealed workflow unit tests - stage gating, 2023 lock state machine, enrichment.

Direct coverage for scripts/phase6_6b2_sealed_workflow.py admission logic:
normal paths, state-machine rejections, and cross-field consistency.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    from scripts.phase6_6b2_sealed_workflow import _sha256_file as impl
    return impl(str(path))


def _make_receipt(gate_root: Path, name: str, stage: str, verdict: str,
                  run_id: str = "run-1", user_run_id: str = "urid-1",
                  code_fingerprint: str = "fp-1",
                  provider: str = "p", model: str = "m",
                  thinking_mode: str = "tm", model_label: str = "ml",
                  audit_overrides: dict | None = None) -> dict:
    """Write a receipt plus a fully consistent archive/audit_index.json."""
    archive_dir = gate_root / f"archive_{stage}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    audit = {
        "code_fingerprint": code_fingerprint,
        "run_id": run_id,
        "user_run_id": user_run_id,
        "stage": stage,
        "provider": provider,
        "model": model,
        "thinking_mode": thinking_mode,
        "model_label": model_label,
        "gate_verdict": verdict,
    }
    if audit_overrides:
        audit.update(audit_overrides)
    audit_path = archive_dir / "audit_index.json"
    _write_json(audit_path, audit)
    receipt = {
        "verdict": verdict, "stage": stage, "run_id": run_id,
        "user_run_id": user_run_id, "archive_dir": str(archive_dir),
        "audit_index_sha256": _sha256_file(audit_path),
        "provider": provider, "model": model,
        "thinking_mode": thinking_mode, "model_label": model_label,
        "code_fingerprint": code_fingerprint, "dataset_sha256": "ds-1",
    }
    _write_json(gate_root / name, receipt)
    return receipt


def _make_lock(lock_path: Path, status: str = "RUNNING", run_id: str = "run-1",
               code_fingerprint: str = "fp-1", schedule_hash: str = "sched-1",
               **extra) -> None:
    from scripts.phase6_6b2_sealed_workflow import BLESSED_2023_RAW_SHA256
    payload = {
        "status": status, "run_id": run_id,
        "raw_sha256": BLESSED_2023_RAW_SHA256,
        "code_fingerprint": code_fingerprint, "schedule_hash": schedule_hash,
    }
    payload.update(extra)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(lock_path, payload)


def _make_final_audit(archive_dir: Path, run_id: str = "run-1",
                      code_fingerprint: str = "fp-1", sched_hash: str = "sched-1",
                      raw_sha: str | None = None, enriched_sha: str | None = None,
                      budget_hard_cap=None, integrity_result: str = "PASS",
                      gate_verdict: str = "PASS") -> Path:
    from scripts.phase6_6b2_sealed_workflow import BLESSED_2023_RAW_SHA256
    archive_dir.mkdir(parents=True, exist_ok=True)
    audit = {
        "run_id": run_id,
        "stage": "final_2023",
        "gate_verdict": gate_verdict,
        "code_fingerprint": code_fingerprint,
        "sched_hash": sched_hash,
        "dataset_hashes": {
            "raw": BLESSED_2023_RAW_SHA256 if raw_sha is None else raw_sha,
            "enriched": enriched_sha,
        },
        "budget_hard_cap": budget_hard_cap,
        "integrity_result": integrity_result,
    }
    audit_path = archive_dir / "audit_index.json"
    _write_json(audit_path, audit)
    return audit_path


class TestCheckStageGate:
    """Stage gate admission: receipt validation and cross-stage chain checks."""

    def test_reuse_valid_dev_receipt_returns_receipt(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE")
        rec = check_stage_gate("reuse", gate_root=str(gate))
        assert rec["stage"] == "dev"
        assert rec["verdict"] == "PROMOTE_CANDIDATE"

    def test_missing_receipt_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate))

    def test_receipt_missing_required_field_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE")
        rec_path = gate / "dev_gate.json"
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        del rec["dataset_sha256"]
        _write_json(rec_path, rec)
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate))

    def test_receipt_stage_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE")
        rec_path = gate / "dev_gate.json"
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        rec["stage"] = "reuse"
        _write_json(rec_path, rec)
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate))

    def test_verdict_outside_allowed_set_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "FAIL")
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate))

    def test_expected_user_run_id_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE",
                      user_run_id="urid-1")
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate),
                             expected_user_run_id="urid-other")

    def test_missing_archive_dir_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE")
        rec_path = gate / "dev_gate.json"
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        rec["archive_dir"] = str(gate / "no_such_dir")
        _write_json(rec_path, rec)
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate))

    def test_audit_sha_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE")
        audit_path = gate / "archive_dev" / "audit_index.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["tampered"] = True
        _write_json(audit_path, audit)
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate))

    def test_audit_cross_field_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        # Rebuild receipt against an audit whose provider no longer matches.
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE")
        rec_path = gate / "dev_gate.json"
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        rec["provider"] = "other-provider"
        _write_json(rec_path, rec)
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate))

    def test_caller_provider_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE",
                      provider="p")
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate), provider="other")

    def test_current_code_fingerprint_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE",
                      code_fingerprint="fp-1")
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(gate),
                             current_code_fingerprint="fp-other")

    def test_final_2023_valid_chain_returns_both_receipts(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE",
                      user_run_id="urid-1", thinking_mode="tm")
        _make_receipt(gate, "reuse_gate.json", "reuse", "PASS",
                      user_run_id="urid-1", thinking_mode="tm")
        result = check_stage_gate("final_2023", gate_root=str(gate))
        assert result["dev"]["stage"] == "dev"
        assert result["reuse"]["stage"] == "reuse"

    def test_final_2023_cross_stage_user_run_id_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE",
                      user_run_id="urid-1")
        _make_receipt(gate, "reuse_gate.json", "reuse", "PASS",
                      user_run_id="urid-2")
        with pytest.raises(SystemExit):
            check_stage_gate("final_2023", gate_root=str(gate))

    def test_final_2023_cross_stage_thinking_mode_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate = tmp_path / "gate"
        gate.mkdir()
        _make_receipt(gate, "dev_gate.json", "dev", "PROMOTE_CANDIDATE",
                      user_run_id="urid-1", thinking_mode="tm-a")
        _make_receipt(gate, "reuse_gate.json", "reuse", "PASS",
                      user_run_id="urid-1", thinking_mode="tm-b")
        with pytest.raises(SystemExit):
            check_stage_gate("final_2023", gate_root=str(gate))

    def test_unknown_stage_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        with pytest.raises(SystemExit):
            check_stage_gate("bogus", gate_root=str(tmp_path))


class TestAcquire2023RunLock:
    """2023 RUNNING/FINALIZED lock state machine."""

    def test_new_lock_created_with_blessed_sha(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import (
            BLESSED_2023_RAW_SHA256, acquire_2023_run_lock)
        lock_path = tmp_path / "2023.lock.json"
        result = acquire_2023_run_lock(str(lock_path), "run-1", "fp-1",
                                       "sched-1", budget_hard_cap=530)
        assert result == "NEW"
        st = json.loads(lock_path.read_text(encoding="utf-8"))
        assert st["status"] == "RUNNING"
        assert st["raw_sha256"] == BLESSED_2023_RAW_SHA256
        assert st["budget_hard_cap"] == 530

    def test_new_lock_without_budget_has_no_cap_field(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        acquire_2023_run_lock(str(lock_path), "run-1", "fp-1", "sched-1")
        st = json.loads(lock_path.read_text(encoding="utf-8"))
        assert "budget_hard_cap" not in st

    def test_resume_same_run_and_fingerprint(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        assert acquire_2023_run_lock(str(lock_path), "run-1", "fp-1", "s") == "NEW"
        assert acquire_2023_run_lock(str(lock_path), "run-1", "fp-1", "s") == "RESUME"

    def test_running_fingerprint_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        acquire_2023_run_lock(str(lock_path), "run-1", "fp-1", "s")
        with pytest.raises(SystemExit):
            acquire_2023_run_lock(str(lock_path), "run-1", "fp-other", "s")

    def test_running_run_id_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        acquire_2023_run_lock(str(lock_path), "run-1", "fp-1", "s")
        with pytest.raises(SystemExit):
            acquire_2023_run_lock(str(lock_path), "run-2", "fp-1", "s")

    def test_finalized_rerun_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, status="FINALIZED")
        with pytest.raises(SystemExit):
            acquire_2023_run_lock(str(lock_path), "run-1", "fp-1", "s")

    def test_foreign_lock_content_rejected_fail_closed(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        # Existing file with unrecognized status falls through to O_EXCL,
        # which must fail closed instead of truncating someone else's lock.
        _write_json(lock_path, {"status": "SOMETHING_ELSE"})
        with pytest.raises(SystemExit):
            acquire_2023_run_lock(str(lock_path), "run-1", "fp-1", "s")


class TestVerify2023RawData:
    """Raw dataset integrity check against the blessed SHA."""

    def test_matching_sha_passes(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import verify_2023_raw_data
        raw = tmp_path / "baziqa_2023.jsonl"
        raw.write_text('{"case_id": "x"}\n', encoding="utf-8")
        verify_2023_raw_data(str(raw), _sha256_file(raw))

    def test_sha_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import verify_2023_raw_data
        raw = tmp_path / "baziqa_2023.jsonl"
        raw.write_text('{"case_id": "x"}\n', encoding="utf-8")
        with pytest.raises(SystemExit):
            verify_2023_raw_data(str(raw), "deadbeef")


class TestRecordEnrichedShaToLock:
    """Enriched dataset SHA recording on the RUNNING lock."""

    def test_first_record_writes_sha(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import record_enriched_sha_to_lock
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path)
        enriched = tmp_path / "enriched.jsonl"
        enriched.write_text('{"a": 1}\n', encoding="utf-8")
        record_enriched_sha_to_lock(str(lock_path), str(enriched))
        st = json.loads(lock_path.read_text(encoding="utf-8"))
        assert st["enriched_sha256"] == _sha256_file(enriched)

    def test_same_sha_rerecord_is_noop(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import record_enriched_sha_to_lock
        lock_path = tmp_path / "2023.lock.json"
        enriched = tmp_path / "enriched.jsonl"
        enriched.write_text('{"a": 1}\n', encoding="utf-8")
        _make_lock(lock_path, enriched_sha256=_sha256_file(enriched))
        record_enriched_sha_to_lock(str(lock_path), str(enriched))

    def test_different_sha_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import record_enriched_sha_to_lock
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, enriched_sha256="old-sha")
        enriched = tmp_path / "enriched.jsonl"
        enriched.write_text('{"a": 1}\n', encoding="utf-8")
        with pytest.raises(SystemExit):
            record_enriched_sha_to_lock(str(lock_path), str(enriched))

    def test_non_running_lock_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import record_enriched_sha_to_lock
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, status="FINALIZED")
        enriched = tmp_path / "enriched.jsonl"
        enriched.write_text('{"a": 1}\n', encoding="utf-8")
        with pytest.raises(SystemExit):
            record_enriched_sha_to_lock(str(lock_path), str(enriched))


class TestUpdateLockScheduleHash:
    """Schedule hash update on the RUNNING lock."""

    def test_pending_schedule_hash_is_replaced(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import update_lock_schedule_hash
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, schedule_hash="pending")
        update_lock_schedule_hash(str(lock_path), "sched-final")
        st = json.loads(lock_path.read_text(encoding="utf-8"))
        assert st["schedule_hash"] == "sched-final"

    def test_same_schedule_hash_is_noop(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import update_lock_schedule_hash
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, schedule_hash="sched-1")
        update_lock_schedule_hash(str(lock_path), "sched-1")

    def test_different_schedule_hash_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import update_lock_schedule_hash
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, schedule_hash="sched-1")
        with pytest.raises(SystemExit):
            update_lock_schedule_hash(str(lock_path), "sched-other")

    def test_non_running_lock_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import update_lock_schedule_hash
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, status="FINALIZED")
        with pytest.raises(SystemExit):
            update_lock_schedule_hash(str(lock_path), "sched-1")


class TestFinalize2023RunLock:
    """RUNNING -> FINALIZED transactional switch."""

    def _setup(self, tmp_path, budget_hard_cap=None):
        from scripts.phase6_6b2_sealed_workflow import BLESSED_2023_RAW_SHA256
        lock_path = tmp_path / "2023.lock.json"
        enriched_sha = "enr-sha"
        _make_lock(lock_path, budget_hard_cap=budget_hard_cap,
                   enriched_sha256=enriched_sha)
        archive_dir = tmp_path / "archive_final_2023"
        _make_final_audit(archive_dir, enriched_sha=enriched_sha,
                          budget_hard_cap=budget_hard_cap)
        return lock_path, archive_dir

    def test_happy_path_finalizes_lock(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path, budget_hard_cap=530)
        finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                               schedule_complete=True, integrity_passed=True)
        st = json.loads(lock_path.read_text(encoding="utf-8"))
        assert st["status"] == "FINALIZED"
        assert st["archive_id"] == "archive_final_2023"
        assert st["gate_verdict"] == "PASS"
        assert st["audit_index_sha256"] == _sha256_file(
            archive_dir / "audit_index.json")

    def test_incomplete_schedule_rejected_lock_stays_running(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path)
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=False, integrity_passed=True)
        st = json.loads(lock_path.read_text(encoding="utf-8"))
        assert st["status"] == "RUNNING"

    def test_integrity_failure_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path)
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=False)

    def test_missing_audit_index_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path)
        (archive_dir / "audit_index.json").unlink()
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)

    def test_non_running_lock_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path)
        _make_lock(lock_path, status="FINALIZED")
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)

    def test_audit_run_id_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, enriched_sha256="enr-sha")
        archive_dir = tmp_path / "archive_final_2023"
        _make_final_audit(archive_dir, run_id="other-run",
                          enriched_sha="enr-sha")
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)

    def test_gate_verdict_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path)
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "FAIL",
                                   schedule_complete=True, integrity_passed=True)

    def test_code_fingerprint_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, code_fingerprint="fp-1", enriched_sha256="enr-sha")
        archive_dir = tmp_path / "archive_final_2023"
        _make_final_audit(archive_dir, code_fingerprint="fp-other",
                          enriched_sha="enr-sha")
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)

    def test_schedule_hash_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, schedule_hash="sched-1", enriched_sha256="enr-sha")
        archive_dir = tmp_path / "archive_final_2023"
        _make_final_audit(archive_dir, sched_hash="sched-other",
                          enriched_sha="enr-sha")
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)

    def test_raw_dataset_hash_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path)
        audit_path = archive_dir / "audit_index.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["dataset_hashes"]["raw"] = "tampered"
        _write_json(audit_path, audit)
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)

    def test_enriched_hash_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path)
        audit_path = archive_dir / "audit_index.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["dataset_hashes"]["enriched"] = "other-enr-sha"
        _write_json(audit_path, audit)
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)

    def test_budget_hard_cap_mismatch_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path = tmp_path / "2023.lock.json"
        _make_lock(lock_path, budget_hard_cap=530, enriched_sha256="enr-sha")
        archive_dir = tmp_path / "archive_final_2023"
        _make_final_audit(archive_dir, enriched_sha="enr-sha",
                          budget_hard_cap=999)
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)

    def test_audit_integrity_result_not_pass_rejected(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import finalize_2023_run_lock
        lock_path, archive_dir = self._setup(tmp_path)
        audit_path = archive_dir / "audit_index.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["integrity_result"] = "FAIL"
        _write_json(audit_path, audit)
        with pytest.raises(SystemExit):
            finalize_2023_run_lock(str(lock_path), archive_dir, "PASS",
                                   schedule_complete=True, integrity_passed=True)


class TestEnrichYear:
    """Enrichment coverage gate (dependency faked via sys.modules)."""

    def _fake_module(self, rows):
        mod = types.ModuleType("scripts.enrich_holdout_chart_input")

        def enrich_row(row):
            return row

        def load_jsonl(path):
            return rows

        def write_jsonl(path, out_rows):
            Path(path).write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n",
                encoding="utf-8")

        mod.enrich_row = enrich_row
        mod.load_jsonl = load_jsonl
        mod.write_jsonl = write_jsonl
        return mod

    def test_full_coverage_returns_summary(self, tmp_path, monkeypatch):
        from scripts.phase6_6b2_sealed_workflow import enrich_year
        rows = [
            {"case_id": "2023_0001", "chart_input": {"ziwei": {"x": 1}}},
            {"case_id": "2023_0002", "chart_input": {"ziwei": {"x": 2}}},
        ]
        monkeypatch.setitem(sys.modules, "scripts.enrich_holdout_chart_input",
                            self._fake_module(rows))
        input_path = tmp_path / "baziqa_2023.jsonl"
        input_path.write_text("", encoding="utf-8")
        output_path = tmp_path / "baziqa_2023_enriched.jsonl"
        summary = enrich_year("2023", str(input_path), str(output_path))
        assert summary["year"] == "2023"
        assert summary["rows"] == 2
        assert summary["ziwei_coverage"] == 2
        assert summary["input_sha256"] == _sha256_file(input_path)
        assert summary["output_sha256"] == _sha256_file(output_path)
        assert output_path.exists()

    def test_partial_coverage_rejected(self, tmp_path, monkeypatch):
        from scripts.phase6_6b2_sealed_workflow import enrich_year
        rows = [
            {"case_id": "2023_0001", "chart_input": {"ziwei": {"x": 1}}},
            {"case_id": "2023_0002", "chart_input": {}},
        ]
        monkeypatch.setitem(sys.modules, "scripts.enrich_holdout_chart_input",
                            self._fake_module(rows))
        input_path = tmp_path / "baziqa_2023.jsonl"
        input_path.write_text("", encoding="utf-8")
        with pytest.raises(SystemExit):
            enrich_year("2023", str(input_path),
                        str(tmp_path / "baziqa_2023_enriched.jsonl"))
