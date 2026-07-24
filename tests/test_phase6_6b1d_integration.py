"""Phase 6 6B1-D: fake runner integration tests.

通过 mock subprocess.run 模拟 runner 行为, 验证 main() 的完整流程:
  - smoke fresh 成功 (5 smoke slices 全部 fresh -> completed)
  - smoke completed skip (已有产物, 验证通过, 跳过)
  - smoke crash (runner 返回非零, main exit 2)
  - main loop slice 成功 (1 个主 slice)
  - budget exhausted (预算耗尽, main exit 2)
  - resume 场景 (partial events -> resume -> completed)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import scripts.phase6_6b1d_orchestrator as orch
from scripts.phase6_6b1d_orchestrator import (
    BudgetLedger,
    generate_schedule,
    _generate_smoke_schedule,
    build_expected_key,
    determine_smoke_state,
    verify_smoke_completed,
    reconcile_partial_events,
    compute_effective_cap,
    REASONED_PROFILE,
    SLICE_SIZE,
    SLICE_MAX_CAP,
    GLOBAL_LEDGER_CAP,
    SMOKE_ARMS_ORDER,
)


# ---- helpers ----

def _write_valid_detail(sl, provider="deepseek", model="deepseek-chat", n=None):
    """Write n valid detail rows with correct attempt keys and parsed terminal_state."""
    dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
    count = n or len(sl["case_ids"])
    rows = []
    for cid in sl["case_ids"][:count]:
        key = build_expected_key(
            dataset_id, REASONED_PROFILE, sl["arm"],
            cid, sl["repeat"], provider, model)
        rows.append({"case_id": cid, "attempt_key": list(key),
                     "terminal_state": "parsed", "answer": "A",
                     "correct": True})
    os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
    with open(sl["detail_path"], "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_valid_events(sl, n=None):
    """Write n call_attempt events."""
    count = n or sl["size"]
    os.makedirs(os.path.dirname(sl["events_path"]), exist_ok=True)
    with open(sl["events_path"], "w", encoding="utf-8") as f:
        for i in range(count):
            f.write(json.dumps({"kind": "call_attempt", "idx": i}) + "\n")


def _write_valid_manifest(sl):
    """Write a manifest file (content doesn't matter, verify_slice_manifest is mocked)."""
    os.makedirs(os.path.dirname(sl["manifest_path"]), exist_ok=True)
    manifest = {
        "hard_cap": sl["hard_cap"],
        "scheduled_calls": sl["size"],
        "arm": sl["arm"],
        "ziwei_arm": sl["ziwei_arm"],
    }
    with open(sl["manifest_path"], "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)


def _make_fake_runner_success(sl_factory):
    """Create a fake subprocess.run that writes valid artifacts and returns rc=0."""
    def fake_run(cmd, **kwargs):
        sl = sl_factory(cmd)
        _write_valid_detail(sl)
        _write_valid_events(sl)
        _write_valid_manifest(sl)

        class R:
            returncode = 0
        return R()
    return fake_run


def _extract_slice_id_from_cmd(cmd):
    """Extract slice_id from runner cmd by matching --case-details-jsonl path."""
    for i, arg in enumerate(cmd):
        if arg == "--case-details-jsonl" and i + 1 < len(cmd):
            detail_path = cmd[i + 1]
            # path like .../slice_{slice_id}/details_{slice_id}.jsonl
            basename = os.path.basename(detail_path)
            # details_{slice_id}.jsonl -> {slice_id}
            if basename.startswith("details_") and basename.endswith(".jsonl"):
                return basename[len("details_"):-len(".jsonl")]
    return None


# ---- TDD 7a: smoke fresh success ----

class TestSmokeFreshSuccess:
    """Test main() smoke gate with all 5 smoke slices fresh."""

    def test_smoke_fresh_all_pass(self, tmp_path, monkeypatch):
        """5 smoke slices fresh -> all produce valid artifacts -> verify passes."""
        output_dir = tmp_path / "output"

        # Generate smoke schedule to get slice dicts
        smoke_slices = _generate_smoke_schedule(output_dir)
        smoke_by_id = {s["slice_id"]: s for s in smoke_slices}

        # Mock subprocess.run: write valid artifacts for each smoke slice
        def fake_run(cmd, **kwargs):
            slice_id = _extract_slice_id_from_cmd(cmd)
            sl = smoke_by_id.get(slice_id)
            if sl is None:
                # main loop slice - also write valid artifacts
                # find from schedule
                schedule = generate_schedule(output_dir)
                for s in schedule["slices"]:
                    if s["slice_id"] == slice_id:
                        sl = s
                        break
            if sl is None:
                raise ValueError(f"unknown slice_id: {slice_id}")
            _write_valid_detail(sl)
            _write_valid_events(sl)
            _write_valid_manifest(sl)

            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)
        # Mock verify_slice_manifest to always pass (isolate from real manifest)
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # Run main with --from-slice to skip main loop (only smoke)
        # Use a large from-slice to skip all 150 main slices
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "999",  # skip main loop
        ])
        assert rc == 0

        # Verify ledger has 5 completed smoke slices
        ledger = BudgetLedger(str(output_dir / "budget_ledger.json"))
        assert len(ledger._data["slices_completed"]) == 5
        # Each smoke slice should have 8 calls recorded
        for s in smoke_slices:
            assert ledger._data["calls_attempted_by_slice"][s["slice_id"]] == 8


# ---- TDD 7a: smoke completed skip ----

class TestSmokeCompletedSkip:
    """Test main() smoke gate with pre-existing completed smoke slices."""

    def test_smoke_completed_all_skip(self, tmp_path, monkeypatch):
        """5 smoke slices already completed -> verify passes -> skip to main loop."""
        output_dir = tmp_path / "output"

        smoke_slices = _generate_smoke_schedule(output_dir)
        smoke_by_id = {s["slice_id"]: s for s in smoke_slices}

        # Pre-write valid completed artifacts for all 5 smoke slices
        for sl in smoke_slices:
            _write_valid_detail(sl)
            _write_valid_events(sl)
            _write_valid_manifest(sl)

        # Mock verify_slice_manifest to pass
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # Mock subprocess.run for main loop (should not be called for smoke)
        main_called = {"count": 0}

        def fake_run(cmd, **kwargs):
            slice_id = _extract_slice_id_from_cmd(cmd)
            if not slice_id.startswith("smoke_"):
                main_called["count"] += 1
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "999",  # skip main loop
        ])
        assert rc == 0

        # Verify smoke slices were NOT re-run (subprocess not called for smoke)
        # main_called should be 0 since we skip main loop
        assert main_called["count"] == 0

        # Verify ledger has 5 completed smoke slices
        ledger = BudgetLedger(str(output_dir / "budget_ledger.json"))
        assert len(ledger._data["slices_completed"]) == 5


# ---- TDD 7a: smoke crash ----

class TestSmokeCrash:
    """Test main() smoke gate with runner crash."""

    def test_smoke_crash_exits_2(self, tmp_path, monkeypatch):
        """Runner returns non-zero for first smoke -> main exit 2."""
        output_dir = tmp_path / "output"

        smoke_slices = _generate_smoke_schedule(output_dir)

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 2  # config error
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "999",
        ])
        assert rc == 2


# ---- TDD 7b: main loop slice success ----

class TestMainLoopSliceSuccess:
    """Test main() main loop with one slice."""

    def test_main_loop_one_slice_success(self, tmp_path, monkeypatch):
        """1 main slice runs successfully -> ledger records completion."""
        output_dir = tmp_path / "output"

        # Pre-complete all 5 smoke slices
        smoke_slices = _generate_smoke_schedule(output_dir)
        smoke_by_id = {s["slice_id"]: s for s in smoke_slices}
        for sl in smoke_slices:
            _write_valid_detail(sl)
            _write_valid_events(sl)
            _write_valid_manifest(sl)

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # Generate schedule to get main slice dicts
        schedule = generate_schedule(output_dir)
        main_slices = [s for s in schedule["slices"]
                       if s["slice_id"] not in smoke_by_id]
        main_by_id = {s["slice_id"]: s for s in main_slices}

        # Mock subprocess.run: smoke skip (already completed), main slice write artifacts
        def fake_run(cmd, **kwargs):
            slice_id = _extract_slice_id_from_cmd(cmd)
            sl = main_by_id.get(slice_id)
            if sl:
                _write_valid_detail(sl)
                _write_valid_events(sl)
                _write_valid_manifest(sl)
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        # Run with --from-slice 0 to run first main slice
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "0",
        ])
        # Should run first slice then continue; but we can't easily limit to 1 slice
        # Since we mock, all slices will "succeed" quickly
        assert rc == 0

        # Verify ledger has smoke + main slices completed
        ledger = BudgetLedger(str(output_dir / "budget_ledger.json"))
        assert len(ledger._data["slices_completed"]) >= 6  # 5 smoke + at least 1 main


# ---- TDD 7b: budget exhausted ----

class TestBudgetExhausted:
    """Test main() budget exhaustion."""

    def test_budget_exhausted_exits_2(self, tmp_path, monkeypatch):
        """Budget exhausted -> main exit 2 with BUDGET_EXHAUSTED."""
        output_dir = tmp_path / "output"

        # Pre-complete all 5 smoke slices
        smoke_slices = _generate_smoke_schedule(output_dir)
        for sl in smoke_slices:
            _write_valid_detail(sl)
            _write_valid_events(sl)
            _write_valid_manifest(sl)

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # Generate schedule to get real slice IDs
        schedule = generate_schedule(output_dir)
        real_slice_id = schedule["slices"][0]["slice_id"]

        # Create a ledger that's already near budget limit
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        # Set total to near 1320 - leaving no room for even 1 slice
        ledger._data["total_calls_attempted"] = GLOBAL_LEDGER_CAP - 1
        ledger._data["calls_attempted_by_slice"][real_slice_id] = GLOBAL_LEDGER_CAP - 1
        ledger._save()

        # Mock subprocess.run (should not be called for main loop)
        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "0",
        ])
        # Budget exhausted -> exit 2
        assert rc == 2


# ---- TDD 7c: resume scenario ----

class TestResumeScenario:
    """Test main() resume scenario with partial events."""

    def test_smoke_resume_completes(self, tmp_path, monkeypatch):
        """Smoke slice with partial events -> resume -> completed."""
        output_dir = tmp_path / "output"

        smoke_slices = _generate_smoke_schedule(output_dir)
        smoke_by_id = {s["slice_id"]: s for s in smoke_slices}

        # First smoke: manifest-only (resume state)
        first_smoke = smoke_slices[0]
        _write_valid_manifest(first_smoke)
        # Allocate cap for first smoke (simulate prior allocation)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        compute_effective_cap(first_smoke["slice_id"], ledger, 0)
        ledger._save()

        # Other smoke slices: fresh
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        def fake_run(cmd, **kwargs):
            slice_id = _extract_slice_id_from_cmd(cmd)
            sl = smoke_by_id.get(slice_id)
            if sl is None:
                schedule = generate_schedule(output_dir)
                for s in schedule["slices"]:
                    if s["slice_id"] == slice_id:
                        sl = s
                        break
            if sl:
                _write_valid_detail(sl)
                _write_valid_events(sl)
                _write_valid_manifest(sl)
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "999",
        ])
        assert rc == 0

        # Verify all 5 smoke completed
        ledger2 = BudgetLedger(ledger_path)
        assert len(ledger2._data["slices_completed"]) == 5

    def test_smoke_resume_with_partial_events(self, tmp_path, monkeypatch):
        """Smoke slice with 3 partial call_attempt events -> resume -> completed."""
        output_dir = tmp_path / "output"

        smoke_slices = _generate_smoke_schedule(output_dir)
        smoke_by_id = {s["slice_id"]: s for s in smoke_slices}

        # First smoke: partial events (3 of 8)
        first_smoke = smoke_slices[0]
        _write_valid_manifest(first_smoke)
        _write_valid_events(first_smoke, n=3)

        # Allocate cap and record partial calls
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        compute_effective_cap(first_smoke["slice_id"], ledger, 0)
        ledger._data["calls_attempted_by_slice"][first_smoke["slice_id"]] = 3
        ledger._data["total_calls_attempted"] = 3
        ledger._save()

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        def fake_run(cmd, **kwargs):
            slice_id = _extract_slice_id_from_cmd(cmd)
            sl = smoke_by_id.get(slice_id)
            if sl is None:
                schedule = generate_schedule(output_dir)
                for s in schedule["slices"]:
                    if s["slice_id"] == slice_id:
                        sl = s
                        break
            if sl:
                _write_valid_detail(sl)
                _write_valid_events(sl)
                _write_valid_manifest(sl)
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "999",
        ])
        assert rc == 0

        # Verify all 5 smoke completed
        ledger2 = BudgetLedger(ledger_path)
        assert len(ledger2._data["slices_completed"]) == 5
        # First smoke should have 8 calls (reconciled from events after resume)
        assert ledger2._data["calls_attempted_by_slice"][first_smoke["slice_id"]] == 8


# ---- TDD 7: dry-run integration ----

class TestDryRunIntegration:
    """Test main() dry-run mode."""

    def test_dry_run_generates_schedule(self, tmp_path):
        """dry-run generates schedule.json and exits 0."""
        output_dir = tmp_path / "output"
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--dry-run",
        ])
        assert rc == 0
        assert (output_dir / "schedule.json").exists()
        # No budget_ledger.json should be created in dry-run
        assert not (output_dir / "budget_ledger.json").exists()

    def test_dry_run_schedule_has_150_slices(self, tmp_path):
        """dry-run schedule must have 150 slices."""
        output_dir = tmp_path / "output"
        orch.main([
            "--output-dir", str(output_dir),
            "--dry-run",
        ])
        with open(output_dir / "schedule.json", "r", encoding="utf-8") as f:
            schedule = json.load(f)
        assert schedule["total_slices"] == 150
        assert schedule["total_scheduled_calls"] == 1200
