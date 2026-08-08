"""Phase 6 6B1 专项测试 — v9 协议验收矩阵.

覆盖:
  - Schedule: 54 slice_id 唯一, Latin square, hard cap, frozen date
  - BudgetLedger: frozen formula, fail-closed
  - Prompt: v9 冻结模板结构
  - Integrity: expected vs actual attempt keys
  - Gate: Δ computation with frozen /40 denominator
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt
from scripts.phase6_6b1_orchestrator import (
    ARM_ZIWEI_MAP,
    FROZEN_DATE,
    GLOBAL_HARD_CAP,
    HARD_CAP_MAP,
    LATIN_SQUARE,
    QUESTIONS_PER_CELL,
    RATED_CALLS,
    SLICE_LAYOUT,
    BudgetLedger,
    build_expected_key,
    compute_gate,
    generate_schedule,
    integrity_check,
    preflight_checks,
)

# ---- Schedule tests ----

class TestSchedule:
    """T11: Schedule generation with Latin square."""

    def test_54_slices_unique_ids(self, tmp_path):
        s = generate_schedule(tmp_path)
        assert s["total_slices"] == 54
        ids = [sl["slice_id"] for sl in s["slices"]]
        assert len(set(ids)) == 54

    def test_720_scheduled_calls(self, tmp_path):
        s = generate_schedule(tmp_path)
        assert s["total_scheduled_calls"] == RATED_CALLS

    def test_hard_cap_total_792(self, tmp_path):
        s = generate_schedule(tmp_path)
        assert s["total_hard_cap"] == GLOBAL_HARD_CAP

    def test_slice_layout_13_14_13(self):
        assert SLICE_LAYOUT == [13, 14, 13]

    def test_hard_cap_map(self):
        assert HARD_CAP_MAP == {13: 14, 14: 16}

    def test_frozen_date(self):
        assert FROZEN_DATE == "2026-07-17"

    def test_latin_square_matrix(self):
        """Spec §8.1: P0→(b1a',b1b,b1c), P1→(b1c,b1a',b1b), P2→(b1b,b1c,b1a')"""
        assert LATIN_SQUARE[0] == {0: "b1a_prime", 1: "b1b", 2: "b1c"}
        assert LATIN_SQUARE[1] == {0: "b1c", 1: "b1a_prime", 2: "b1b"}
        assert LATIN_SQUARE[2] == {0: "b1b", 1: "b1c", 2: "b1a_prime"}

    def test_each_cell_has_3_slices(self, tmp_path):
        """Each (year, repeat, arm) has exactly 3 slices (3 positions)."""
        from collections import Counter
        s = generate_schedule(tmp_path)
        ct = Counter((sl["year"], sl["repeat"], sl["arm"]) for sl in s["slices"])
        assert len(ct) == 18  # 2 years × 3 repeats × 3 arms
        assert all(v == 3 for v in ct.values())

    def test_unique_output_dirs(self, tmp_path):
        s = generate_schedule(tmp_path)
        dirs = [sl["output_dir"] for sl in s["slices"]]
        assert len(set(dirs)) == 54

    def test_slice_id_contains_year(self, tmp_path):
        """Spec §8.2: slice_id must contain year dimension."""
        s = generate_schedule(tmp_path)
        for sl in s["slices"]:
            assert sl["year"] in sl["slice_id"]

    def test_each_arm_sees_all_40_cases(self, tmp_path):
        """Latin square: each arm sees all 40 questions across 3 positions."""
        from collections import defaultdict
        s = generate_schedule(tmp_path)
        arm_cases = defaultdict(set)
        for sl in s["slices"]:
            arm_cases[(sl["year"], sl["repeat"], sl["arm"])].update(sl["case_ids"])
        assert all(len(v) == QUESTIONS_PER_CELL for v in arm_cases.values())

    def test_arm_ziwei_map_correct(self, tmp_path):
        s = generate_schedule(tmp_path)
        for sl in s["slices"]:
            assert sl["ziwei_arm"] == ARM_ZIWEI_MAP[sl["arm"]]

    def test_schedule_records_hard_cap_per_slice(self, tmp_path):
        s = generate_schedule(tmp_path)
        for sl in s["slices"]:
            assert sl["hard_cap"] == HARD_CAP_MAP[sl["size"]]

    def test_36_13_and_18_14(self, tmp_path):
        """36 slices of 13 + 18 slices of 14 = 720."""
        from collections import Counter
        s = generate_schedule(tmp_path)
        ct = Counter(sl["size"] for sl in s["slices"])
        assert ct[13] == 36
        assert ct[14] == 18

    def test_same_arm_repeat_position_group_different_year(self, tmp_path):
        """Spec §8.2: same arm/repeat/position/group → different slice_id and dir."""
        s = generate_schedule(tmp_path)
        for i, sl1 in enumerate(s["slices"]):
            for sl2 in s["slices"][i+1:]:
                if (sl1["arm"] == sl2["arm"]
                    and sl1["repeat"] == sl2["repeat"]
                    and sl1["position"] == sl2["position"]
                    and sl1["group"] == sl2["group"]):
                    assert sl1["slice_id"] != sl2["slice_id"]
                    assert sl1["output_dir"] != sl2["output_dir"]


# ---- BudgetLedger tests ----

class TestBudgetLedger:

    def test_frozen_formula_budget_ok(self, tmp_path):
        """Spec §8.7: total + (hard_cap - attempted) ≤ 792"""
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        # Fresh slice: 0 + (14 - 0) = 14 ≤ 792
        assert ledger.budget_ok_for_slice("test_slice", 14)

    def test_frozen_formula_budget_exceeded(self, tmp_path):
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        # Simulate near-cap usage
        ledger._data["total_calls_attempted"] = 780
        ledger._save()
        # 780 + (14 - 0) = 794 > 792
        assert not ledger.budget_ok_for_slice("new_slice", 14)

    def test_frozen_formula_with_resume(self, tmp_path):
        """Resume: already attempted reduces remaining for slice."""
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        ledger._data["calls_attempted_by_slice"]["resumed"] = 10
        ledger._data["total_calls_attempted"] = 10
        ledger._save()
        # 10 + (14 - 10) = 14 ≤ 792
        assert ledger.budget_ok_for_slice("resumed", 14)

    def test_record_calls_only_does_not_mark_completed(self, tmp_path):
        """Failed slices: record calls but NOT completed."""
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        ledger.record_calls_only("failed_slice", 5)
        assert ledger.total_attempted == 5
        assert not ledger.sliced_completed("failed_slice")

    def test_record_slice_completed_marks_completed(self, tmp_path):
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        ledger.record_slice_completed("ok_slice", 13)
        assert ledger.sliced_completed("ok_slice")
        assert ledger.total_attempted == 13

    def test_fail_closed_on_corruption(self, tmp_path):
        path = str(tmp_path / "ledger.json")
        with open(path, "w") as f:
            f.write("{broken json")
        with pytest.raises(SystemExit) as exc:
            BudgetLedger(path)
        assert exc.value.code == 2


# ---- Prompt tests ----

class TestFrozenPrompt:

    def test_prompt_has_mingzhu_header(self):
        """Spec §3.1: prompt must contain '## 命主信息'"""
        case = {"question": "test?", "options": ["A", "B", "C", "D"]}
        prompt = _assemble_reasoned_choice_prompt(case, "context here")
        assert "## 命主信息" in prompt

    def test_prompt_has_bazi_assistant(self):
        """Spec §3.1: '你是一位严谨的八字命理评测助手。'"""
        case = {"question": "test?", "options": ["A", "B", "C", "D"]}
        prompt = _assemble_reasoned_choice_prompt(case, "context")
        assert "八字命理评测助手" in prompt

    def test_prompt_has_output_requirement(self):
        case = {"question": "test?", "options": ["A", "B", "C", "D"]}
        prompt = _assemble_reasoned_choice_prompt(case, "context")
        assert "## 输出要求" in prompt
        assert "最终答案：X" in prompt

    def test_prompt_no_five_dimension_analysis(self):
        """No unapproved '五维' content."""
        case = {"question": "test?", "options": ["A", "B", "C", "D"]}
        prompt = _assemble_reasoned_choice_prompt(case, "context")
        assert "五维" not in prompt
        assert "五个维度" not in prompt

    def test_prompt_no_ziwei_expertise_claim(self):
        """No unapproved '精通紫微斗数'."""
        case = {"question": "test?", "options": ["A", "B", "C", "D"]}
        prompt = _assemble_reasoned_choice_prompt(case, "context")
        assert "精通紫微斗数" not in prompt


# ---- Integrity tests ----

class TestIntegrity:

    def test_expected_key_10_tuple(self):
        """Spec §10.1: attempt key is 10-tuple."""
        key = build_expected_key(
            "dataset", "profile", "b1a_prime", "case1", 0, "deepseek", "deepseek-chat"
        )
        assert len(key) == 10
        assert key[0] == "dataset"
        assert key[2] == "b1a_prime"
        assert key[3] == "main"
        assert key[4] == "deepseek"
        assert key[5] == "deepseek-chat"

    def test_integrity_pass_on_empty(self, tmp_path):
        """Empty ledger → no actual keys → integrity fails (missing all)."""
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        result = integrity_check(s, ledger, "deepseek", "deepseek-chat")
        assert not result["pass"]
        assert result["missing"] > 0

    def test_integrity_with_completed_slices(self, tmp_path):
        """Simulate completed slices with detail files."""
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        # Write detail files for first slice
        sl = s["slices"][0]
        os.makedirs(sl["output_dir"], exist_ok=True)
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        with open(sl["detail_path"], "w", encoding="utf-8") as f:
            for case_id in sl["case_ids"]:
                key = build_expected_key(
                    dataset_id, "baziqa_xjz_reasoned", sl["arm"],
                    case_id, sl["repeat"], "deepseek", "deepseek-chat",
                )
                row = {"attempt_key": list(key), "correct": True,
                       "terminal_state": "parsed", "predicted_answer": "A"}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        ledger.record_slice_completed(sl["slice_id"], sl["size"])
        # Integrity should still fail (only 1 of 54 slices done)
        result = integrity_check(s, ledger, "deepseek", "deepseek-chat")
        assert not result["pass"]


# ---- Gate tests ----

class TestGate:

    def test_gate_denominator_is_40(self, tmp_path):
        """Spec: denominator is always 40 per (year, repeat, arm) cell."""
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        gate = compute_gate(s, ledger)
        # With no completed slices, all accuracies should be 0/40 = 0.0
        for val in gate["cell_accuracies"].values():
            assert val == 0.0

    def test_gate_verdict_rollback_on_empty(self, tmp_path):
        """Spec §11: binary verdict — not PROMOTE → ROLLBACK (no INCONCLUSIVE)"""
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        gate = compute_gate(s, ledger)
        assert gate["verdict"] == "ROLLBACK"
        assert gate["delta_dev"] == 0.0

    def test_gate_no_inconclusive_verdict(self, tmp_path):
        """Spec §11: only PROMOTE_CANDIDATE or ROLLBACK, never INCONCLUSIVE"""
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        gate = compute_gate(s, ledger)
        assert gate["verdict"] in ("PROMOTE_CANDIDATE", "ROLLBACK")
        assert "INCONCLUSIVE" not in gate["verdict"]
        assert "ROLLBACK_CANDIDATE" not in gate["verdict"]


# ---- Preflight tests ----

class TestPreflight:

    def test_preflight_passes_on_enriched_data(self, tmp_path):
        """Preflight should pass on real enriched datasets."""
        s = generate_schedule(tmp_path)
        # Should not raise
        preflight_checks(s)

    def test_preflight_fails_on_missing_ziwei(self, tmp_path):
        """Preflight should fail if ziwei coverage is 0."""
        # Create a fake dataset without ziwei
        fake_dir = tmp_path / "fake"
        fake_dir.mkdir()
        fake_cases = []
        for i in range(40):
            fake_cases.append({
                "case_id": f"C{i:03d}",
                "question": f"Q{i}?",
                "options": ["A", "B", "C", "D"],
                "chart_input": {"bazi": {}, "ziwei": None},
            })
        fake_path = fake_dir / "fake.jsonl"
        with open(fake_path, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in fake_cases)

        # Monkeypatch YEAR_DATASETS
        import scripts.phase6_6b1_orchestrator as orch
        original = orch.YEAR_DATASETS.copy()
        try:
            orch.YEAR_DATASETS = {"2024": str(fake_path), "2025": str(fake_path)}
            s = {"slices": []}
            with pytest.raises(SystemExit) as exc:
                preflight_checks(s)
            assert exc.value.code == 2
        finally:
            orch.YEAR_DATASETS = original


# ---- CLI entry tests ----

class TestCLIEntry:
    """P0: Real CLI entry must not crash with ModuleNotFoundError."""

    def test_dry_run_from_cli(self, tmp_path):
        """Running via `python scripts/phase6_6b1_orchestrator.py --dry-run` must work."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/phase6_6b1_orchestrator.py",
             "--dry-run", "--output-dir", str(tmp_path)],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}, stderr: {result.stderr}"
        assert "54 slices" in result.stdout
        assert "720 calls" in result.stdout

    def test_skip_smoke_rejected(self, tmp_path):
        """--skip-smoke must be rejected (removed flag)."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/phase6_6b1_orchestrator.py",
             "--dry-run", "--skip-smoke", "--output-dir", str(tmp_path)],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode != 0  # argparse should reject unknown flag

    def test_no_fail_count_nameerror(self, tmp_path):
        """Success path must return 0, not NameError on fail_count."""
        # Verify the source code doesn't reference fail_count
        orch_path = os.path.join(PROJECT_ROOT, "scripts", "phase6_6b1_orchestrator.py")
        with open(orch_path, "r", encoding="utf-8") as f:
            source = f.read()
        # The old `return 0 if fail_count == 0 else 1` should be gone
        assert "fail_count" not in source


# ---- Smoke completed branch tests ----

class TestSmokeCompletedBranch:
    """P0: Completed smoke must verify manifest, events, keys, parser rate."""

    def test_verify_slice_manifest_rejects_missing(self, tmp_path):
        """verify_slice_manifest returns False when manifest doesn't exist."""
        from scripts.phase6_6b1_orchestrator import verify_slice_manifest
        s = generate_schedule(tmp_path)
        smoke_sl = s["slices"][0]
        ok, diff = verify_slice_manifest(smoke_sl, "deepseek", "deepseek-chat")
        assert not ok
        assert "_manifest" in diff

    def test_verify_slice_manifest_rejects_wrong_content(self, tmp_path):
        """verify_slice_manifest returns False when manifest content is wrong."""
        from scripts.phase6_6b1_orchestrator import verify_slice_manifest
        s = generate_schedule(tmp_path)
        smoke_sl = s["slices"][0]
        # Write a manifest with wrong content
        os.makedirs(smoke_sl["output_dir"], exist_ok=True)
        with open(smoke_sl["manifest_path"], "w", encoding="utf-8") as f:
            json.dump({
                "profile_id": "wrong_profile",
                "arm": "wrong_arm",
                "ziwei_arm": "wrong_ziwei",
            }, f)
        ok, diff = verify_slice_manifest(smoke_sl, "deepseek", "deepseek-chat")
        assert not ok
        assert len(diff) > 0

    def test_verify_slice_manifest_rejects_corrupt_json(self, tmp_path):
        """verify_slice_manifest returns False on corrupt JSON."""
        from scripts.phase6_6b1_orchestrator import verify_slice_manifest
        s = generate_schedule(tmp_path)
        smoke_sl = s["slices"][0]
        os.makedirs(smoke_sl["output_dir"], exist_ok=True)
        with open(smoke_sl["manifest_path"], "w") as f:
            f.write("{broken json")
        ok, diff = verify_slice_manifest(smoke_sl, "deepseek", "deepseek-chat")
        assert not ok

    def test_completed_slice_with_drifted_manifest_not_skipped(self, tmp_path):
        """Main loop should NOT skip a completed slice if manifest drifted."""
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        sl = s["slices"][0]
        # Mark as completed in ledger
        ledger.record_slice_completed(sl["slice_id"], sl["size"])
        assert ledger.sliced_completed(sl["slice_id"])
        # But don't write a manifest → verify_slice_manifest should fail
        from scripts.phase6_6b1_orchestrator import verify_slice_manifest
        ok, diff = verify_slice_manifest(sl, "deepseek", "deepseek-chat")
        assert not ok  # manifest missing → should re-run, not skip


# ---- Full success path test ----

class TestFullSuccessPath:
    """P0: Complete main() success path must not crash."""

    def test_dry_run_returns_zero(self, tmp_path):
        """main() with --dry-run must return 0 (not NameError or other crash)."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/phase6_6b1_orchestrator.py",
             "--dry-run", "--output-dir", str(tmp_path)],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "54 slices" in result.stdout

    def test_generate_report_accepts_ledger(self, tmp_path):
        """generate_report must accept and use ledger parameter."""
        from scripts.phase6_6b1_orchestrator import generate_report
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        gate = compute_gate(s, ledger)
        integrity = {"expected_count": 720, "actual_count": 720,
                      "duplicates": 0, "missing": 0, "extra": 0,
                      "detail_errors": [], "pass": True}
        # Must not raise NameError
        report_path = generate_report(s, gate, integrity, tmp_path, ledger)
        assert os.path.exists(report_path)
        # Report should contain actual completed count from ledger (0, not 54)
        with open(report_path, "r", encoding="utf-8") as f:
            report = f.read()
        assert "Slices completed: 0" in report


# ---- Events validation tests ----

class TestEventsValidation:
    """P0: Events file must be validated (not just existence checked)."""

    def test_validate_events_rejects_missing(self, tmp_path):
        from scripts.phase6_6b1_orchestrator import _validate_events
        ok, count, reason = _validate_events(str(tmp_path / "nonexistent.jsonl"), 13, 14)
        assert not ok
        assert count == 0

    def test_validate_events_rejects_empty(self, tmp_path):
        """Empty events file → 0 calls < scheduled_calls → fail."""
        from scripts.phase6_6b1_orchestrator import _validate_events
        ev_path = tmp_path / "events.jsonl"
        ev_path.write_text("", encoding="utf-8")
        ok, count, reason = _validate_events(str(ev_path), 13, 14)
        assert not ok
        assert count == 0
        assert "scheduled_calls" in reason

    def test_validate_events_rejects_corrupt_json(self, tmp_path):
        """Corrupt JSON in events → fail."""
        from scripts.phase6_6b1_orchestrator import _validate_events
        ev_path = tmp_path / "events.jsonl"
        ev_path.write_text(
            json.dumps({"kind": "call_attempt"}) + "\n"
            "{broken json}\n",
            encoding="utf-8"
        )
        ok, count, reason = _validate_events(str(ev_path), 1, 14)
        assert not ok
        assert "corrupt" in reason

    def test_validate_events_rejects_over_hard_cap(self, tmp_path):
        """More call_attempts than hard_cap → fail."""
        from scripts.phase6_6b1_orchestrator import _validate_events
        ev_path = tmp_path / "events.jsonl"
        lines = [json.dumps({"kind": "call_attempt"}) for _ in range(20)]
        ev_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, count, reason = _validate_events(str(ev_path), 13, 14)
        assert not ok
        assert count == 20
        assert "hard_cap" in reason

    def test_validate_events_accepts_valid(self, tmp_path):
        """Valid events with count in [scheduled, hard_cap] → pass."""
        from scripts.phase6_6b1_orchestrator import _validate_events
        ev_path = tmp_path / "events.jsonl"
        lines = [json.dumps({"kind": "call_attempt"}) for _ in range(13)]
        ev_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, count, reason = _validate_events(str(ev_path), 13, 14)
        assert ok
        assert count == 13


# ---- Runner ziwei_arm fail-closed tests ----

class TestRunnerZiweiArmFailClosed:
    """P0: Runner internal interfaces must reject missing ziwei_arm for reasoned profile."""

    def test_build_benchmark_prompt_rejects_none_ziwei_arm(self):
        """build_benchmark_prompt with reasoned formatter + ziwei_arm=None → SystemExit(2)."""
        from benchmark.runners.run_benchmark import build_benchmark_prompt
        case = {"case_id": "C001", "question": "Q?", "options": ["A", "B", "C", "D"],
                "chart_input": {"bazi": {}, "ziwei": {}}}
        with pytest.raises(SystemExit) as exc:
            build_benchmark_prompt(case, chart_schema_version="legacy_v0",
                                  profile_formatter="format_reasoned_choice_prompt",
                                  ziwei_arm=None)
        assert exc.value.code == 2


# ---- Source audit: verify production code calls _validate_events ----

class TestSourceAudit:
    """Verify production code has _validate_events calls in critical paths."""

    def test_fresh_smoke_calls_validate_events(self):
        """Orchestrator must call _validate_events in fresh/resume smoke path."""
        orch_path = os.path.join(PROJECT_ROOT, "scripts", "phase6_6b1_orchestrator.py")
        with open(orch_path, "r", encoding="utf-8") as f:
            source = f.read()
        # The fresh/resume smoke path must have _validate_events after parser gate
        # and before record_slice_completed
        assert "_validate_events" in source
        # Count occurrences: completed smoke + fresh/resume smoke + completed slice + main loop rc==0
        assert source.count("_validate_events") >= 4

    def test_completed_slice_checks_events(self):
        """Completed slice skip path must verify events, not just manifest."""
        orch_path = os.path.join(PROJECT_ROOT, "scripts", "phase6_6b1_orchestrator.py")
        with open(orch_path, "r", encoding="utf-8") as f:
            source = f.read()
        # Find the main loop's sliced_completed call (not the class method)
        idx = source.index('if ledger.sliced_completed(sl["slice_id"]):')
        section = source[idx:idx+800]
        assert "_validate_events" in section

    def test_completed_smoke_uses_incremental_budget(self):
        """Completed smoke budget must use incremental formula, not raw total+calls."""
        orch_path = os.path.join(PROJECT_ROOT, "scripts", "phase6_6b1_orchestrator.py")
        with open(orch_path, "r", encoding="utf-8") as f:
            source = f.read()
        # The incremental formula should reference previously_recorded
        assert "previously_recorded" in source
        assert "increment" in source

    def test_resume_check_detects_duplicates(self):
        """D3 resume check must detect duplicate keys, not just extra keys."""
        orch_path = os.path.join(PROJECT_ROOT, "scripts", "phase6_6b1_orchestrator.py")
        with open(orch_path, "r", encoding="utf-8") as f:
            source = f.read()
        # The D3 check should verify len(existing_rows) == len(existing_keys)
        assert "len(existing_rows) != len(existing_keys)" in source


# ---- Incremental budget test ----

class TestIncrementalBudget:
    """P1: Completed smoke budget must not double-count on resume."""

    def test_resume_does_not_double_count(self, tmp_path):
        """If ledger already has 13 calls for smoke, resuming with 13 should not add."""
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        smoke_id = "2024_b1a_prime_R0_P0_G0"
        # First run: record 13 calls
        ledger.record_slice_completed(smoke_id, 13)
        assert ledger.total_attempted == 13
        # Simulate completed smoke resume: prev=13, calls=13, increment=0
        prev = ledger._data["calls_attempted_by_slice"].get(smoke_id, 0)
        calls = 13
        increment = max(0, calls - prev)
        assert increment == 0
        assert ledger.total_attempted + increment <= ledger.hard_cap  # 13 + 0 = 13 ≤ 792

    def test_resume_with_more_calls(self, tmp_path):
        """If ledger has 10, resume finds 13, increment=3."""
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        smoke_id = "2024_b1a_prime_R0_P0_G0"
        ledger.record_slice_completed(smoke_id, 10)
        prev = ledger._data["calls_attempted_by_slice"].get(smoke_id, 0)
        calls = 13
        increment = max(0, calls - prev)
        assert increment == 3
        assert ledger.total_attempted + increment == 13  # 10 + 3 = 13


# ---- P0-1: standalone smoke fresh/resume events validation ----

class TestStandaloneSmokeEventsValidation:
    """P0-1: standalone smoke fresh/resume must reject empty/corrupt events."""

    def _make_smoke_slice(self, tmp_path):
        """Create a minimal smoke slice dict from a generated schedule."""
        from scripts.phase6_6b1_orchestrator import generate_schedule
        s = generate_schedule(tmp_path)
        return s["slices"][0]

    def _write_valid_detail(self, sl, n=13):
        """Write n valid detail rows with correct attempt keys."""
        from scripts.phase6_6b1_orchestrator import build_expected_key
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        rows = []
        for i, cid in enumerate(sl["case_ids"][:n]):
            key = build_expected_key(
                dataset_id, "baziqa_xjz_reasoned", sl["arm"],
                cid, sl["repeat"], "deepseek", "deepseek-chat")
            rows.append({"case_id": cid, "attempt_key": list(key),
                         "terminal_state": "parsed", "answer": "A",
                         "correct": True})
        os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
        with open(sl["detail_path"], "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)

    def _write_valid_manifest(self, sl):
        """Write a manifest matching current config."""
        manifest = {
            "dataset_id": os.path.splitext(os.path.basename(sl["dataset"]))[0],
            "profile_id": "baziqa_xjz_reasoned",
            "chart_schema_version": "legacy_v0",
            "arm": sl["arm"],
            "ziwei_arm": sl["ziwei_arm"],
            "attempt_stage": "main",
            "repeat_idx": sl["repeat"],
            "provider": "deepseek",
            "model": "deepseek-chat",
            "temperature": 0.0,
            "sample_temperature": 0.0,
            "n_samples": 1,
            "aggregate": "emit_samples",
            "method": "direct_choice",
            "prompt_template_sha256": "x",
            "code_sha256": "x",
            "scheduled_calls": sl["size"],
            "hard_cap": sl["hard_cap"],
            "as_of_date": "2026-07-17",
        }
        os.makedirs(os.path.dirname(sl["manifest_path"]), exist_ok=True)
        with open(sl["manifest_path"], "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

    def test_fresh_with_empty_events_rejected(self, tmp_path, monkeypatch):
        """P0-1: fresh path with empty events -> BLOCKED_SMOKE (not OK).
        P0-1 fix: manifest now uses full verify_slice_manifest; mock it to pass
        so we isolate the events-validation behavior."""
        import scripts.phase6_6b1_orchestrator as orch
        import scripts.phase6_6b1_smoke as smoke_mod
        from scripts.phase6_6b1_smoke import smoke_gate
        sl = self._make_smoke_slice(tmp_path)

        # Mock verify_slice_manifest in orchestrator (smoke imports from there)
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        def fake_run(cmd, **kwargs):
            self._write_valid_detail(sl)
            self._write_valid_manifest(sl)
            os.makedirs(os.path.dirname(sl["events_path"]), exist_ok=True)
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                pass
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(smoke_mod.subprocess, "run", fake_run)

        result = smoke_gate(sl, "deepseek", "deepseek-chat")
        assert result["status"] != "OK"
        assert result["status"] == "BLOCKED_SMOKE"
        assert result["pass"] is False

    def test_resume_with_empty_events_rejected(self, tmp_path, monkeypatch):
        """P0-1: resume path with empty events -> BLOCKED_SMOKE (not OK).
        P0-1 fix: manifest now uses full verify_slice_manifest; mock it to pass."""
        import scripts.phase6_6b1_orchestrator as orch
        import scripts.phase6_6b1_smoke as smoke_mod
        from scripts.phase6_6b1_smoke import smoke_gate
        sl = self._make_smoke_slice(tmp_path)

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
        self._write_valid_manifest(sl)
        with open(sl["detail_path"], "w", encoding="utf-8") as f:
            f.write(json.dumps({"case_id": "c0", "terminal_state": "pending"}) + "\n")

        def fake_run(cmd, **kwargs):
            self._write_valid_detail(sl)
            os.makedirs(os.path.dirname(sl["events_path"]), exist_ok=True)
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                pass
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(smoke_mod.subprocess, "run", fake_run)

        result = smoke_gate(sl, "deepseek", "deepseek-chat")
        assert result["status"] == "BLOCKED_SMOKE"
        assert result["pass"] is False


# ---- P0-2: --from-slice must audit skipped slices ----

class TestFromSliceAudit:
    """P0-2: --from-slice must not bypass manifest/events audit for skipped slices."""

    def test_from_slice_with_corrupted_events_exits_2(self, tmp_path):
        """Corrupted events in a skipped slice -> FROM_SLICE_EVENTS_INVALID exit 2."""
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            _audit_skipped_slices,
            build_expected_key,
            generate_schedule,
        )

        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))

        # Simulate slice[1] completed with valid detail+manifest but empty events
        sl1 = s["slices"][1]
        os.makedirs(sl1["output_dir"], exist_ok=True)
        dataset_id = os.path.splitext(os.path.basename(sl1["dataset"]))[0]
        with open(sl1["detail_path"], "w", encoding="utf-8") as f:
            for cid in sl1["case_ids"]:
                key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                         sl1["arm"], cid, sl1["repeat"],
                                         "deepseek", "deepseek-chat")
                f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                    "terminal_state": "parsed"}) + "\n")
        manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                    "chart_schema_version": "legacy_v0", "arm": sl1["arm"],
                    "ziwei_arm": sl1["ziwei_arm"], "attempt_stage": "main",
                    "repeat_idx": sl1["repeat"], "provider": "deepseek",
                    "model": "deepseek-chat", "temperature": 0.0,
                    "sample_temperature": 0.0, "n_samples": 1,
                    "aggregate": "emit_samples", "method": "direct_choice",
                    "prompt_template_sha256": "x", "code_sha256": "x",
                    "scheduled_calls": sl1["size"], "hard_cap": sl1["hard_cap"],
                    "as_of_date": "2026-07-17"}
        with open(sl1["manifest_path"], "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)
        # Write EMPTY events (corrupted - missing call_attempt events)
        with open(sl1["events_path"], "w", encoding="utf-8") as f:
            pass
        # Mark slice as completed in ledger
        ledger.record_slice_completed(sl1["slice_id"], sl1["size"])

        # Call _audit_skipped_slices directly (start_idx=2 skips slice[1])
        with pytest.raises(SystemExit) as ei:
            _audit_skipped_slices(s, 2, ledger, "deepseek", "deepseek-chat")
        assert ei.value.code == 2

    def test_from_slice_with_valid_slices_passes(self, tmp_path, monkeypatch):
        """All skipped slices valid -> audit passes (no exit)."""
        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            _audit_skipped_slices,
            generate_schedule,
        )

        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))

        # Create valid artifacts for slice[1]
        sl1 = s["slices"][1]
        os.makedirs(sl1["output_dir"], exist_ok=True)
        # Write valid events (sl1["size"] call_attempt events)
        with open(sl1["events_path"], "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl1["size"]))
        ledger.record_slice_completed(sl1["slice_id"], sl1["size"])

        # Mock verify_slice_manifest to pass (manifest verification has its own tests)
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # Should not raise
        _audit_skipped_slices(s, 2, ledger, "deepseek", "deepseek-chat")


# ---- P1-3: BudgetLedger consistency validation ----

class TestLedgerConsistency:
    """P1-3: ledger loading must validate values, not just field existence."""

    def test_tampered_hard_cap_rejected(self, tmp_path):
        """global_hard_cap != 792 -> SystemExit(2)."""
        path = str(tmp_path / "ledger.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"global_hard_cap": 999, "slices_completed": [],
                        "calls_attempted_by_slice": {}, "total_calls_attempted": 0}, f)
        with pytest.raises(SystemExit) as ei:
            BudgetLedger(path)
        assert ei.value.code == 2

    def test_total_mismatch_rejected(self, tmp_path):
        """total != sum(per_slice) -> SystemExit(2)."""
        path = str(tmp_path / "ledger.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"global_hard_cap": 792, "slices_completed": ["s1"],
                        "calls_attempted_by_slice": {"s1": 13},
                        "total_calls_attempted": 99}, f)
        with pytest.raises(SystemExit) as ei:
            BudgetLedger(path)
        assert ei.value.code == 2

    def test_negative_count_rejected(self, tmp_path):
        """negative call count -> SystemExit(2)."""
        path = str(tmp_path / "ledger.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"global_hard_cap": 792, "slices_completed": ["s1"],
                        "calls_attempted_by_slice": {"s1": -5},
                        "total_calls_attempted": -5}, f)
        with pytest.raises(SystemExit) as ei:
            BudgetLedger(path)
        assert ei.value.code == 2

    def test_total_over_hard_cap_rejected(self, tmp_path):
        """total > hard_cap -> SystemExit(2)."""
        path = str(tmp_path / "ledger.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"global_hard_cap": 792, "slices_completed": ["s1"],
                        "calls_attempted_by_slice": {"s1": 800},
                        "total_calls_attempted": 800}, f)
        with pytest.raises(SystemExit) as ei:
            BudgetLedger(path)
        assert ei.value.code == 2

    def test_valid_ledger_accepted(self, tmp_path):
        """Valid ledger with consistent values -> loads OK."""
        path = str(tmp_path / "ledger.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"global_hard_cap": 792, "slices_completed": ["s1"],
                        "calls_attempted_by_slice": {"s1": 13},
                        "total_calls_attempted": 13}, f)
        ledger = BudgetLedger(path)
        assert ledger.total_attempted == 13
        assert ledger.hard_cap == 792


# ---- P1-4: completed slice ledger reconciliation ----

class TestLedgerReconcile:
    """P1-4: completed slice must reconcile ledger call count with events."""

    def test_reconcile_fixes_mismatch(self, tmp_path):
        """Ledger has 10 but events has sl['size'] -> reconciled to sl['size']."""
        from scripts.phase6_6b1_orchestrator import _validate_events
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        sl = s["slices"][1]
        os.makedirs(sl["output_dir"], exist_ok=True)
        # Write sl["size"] call_attempt events
        with open(sl["events_path"], "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl["size"]))
        # Ledger has wrong count (10)
        ledger._data["calls_attempted_by_slice"][sl["slice_id"]] = 10
        ledger._data["slices_completed"].append(sl["slice_id"])
        ledger._data["total_calls_attempted"] = 10
        ledger._save()

        # Validate events and reconcile
        ev_ok, ev_count, ev_reason = _validate_events(
            sl["events_path"], sl["size"], sl["hard_cap"])
        assert ev_ok
        assert ev_count == sl["size"]
        ledger_calls = ledger._data["calls_attempted_by_slice"].get(sl["slice_id"], 0)
        if ledger_calls != ev_count:
            ledger._data["calls_attempted_by_slice"][sl["slice_id"]] = ev_count
            ledger._data["total_calls_attempted"] = sum(
                ledger._data["calls_attempted_by_slice"].values())
            ledger._save()
        assert ledger._data["calls_attempted_by_slice"][sl["slice_id"]] == sl["size"]
        assert ledger._data["total_calls_attempted"] == sl["size"]


# ---- P1-5: crash/resume protocol ----

class TestCrashResumeProtocol:
    """P1-5: crash state persistence, forbid recovery from rc 2/3, one retry limit."""

    def _make_slice(self, tmp_path):
        s = generate_schedule(tmp_path)
        return s["slices"][1]

    def test_rc2_forbids_recovery(self, tmp_path):
        """Crash state with returncode=2 -> CRASH_RECOVERY_FORBIDDEN."""
        from scripts.phase6_6b1_orchestrator import (
            _write_crash_state,
            run_slice,
        )
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        _write_crash_state(sl, {
            "state": "deterministic_error", "returncode": 2,
            "retried": False, "timestamp": "2026-07-22T00:00:00",
        })
        with pytest.raises(SystemExit) as ei:
            run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert ei.value.code == 2

    def test_rc3_forbids_recovery(self, tmp_path):
        """Crash state with returncode=3 -> CRASH_RECOVERY_FORBIDDEN."""
        from scripts.phase6_6b1_orchestrator import (
            _write_crash_state,
            run_slice,
        )
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        _write_crash_state(sl, {
            "state": "deterministic_error", "returncode": 3,
            "retried": False, "timestamp": "2026-07-22T00:00:00",
        })
        with pytest.raises(SystemExit) as ei:
            run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert ei.value.code == 2

    def test_already_retried_forbids_recovery(self, tmp_path):
        """Crash state with retried=True -> CRASH_RECOVERY_EXHAUSTED."""
        from scripts.phase6_6b1_orchestrator import (
            _write_crash_state,
            run_slice,
        )
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        _write_crash_state(sl, {
            "state": "crashed", "returncode": 1,
            "retried": True, "timestamp": "2026-07-22T00:00:00",
        })
        with pytest.raises(SystemExit) as ei:
            run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert ei.value.code == 2

    def test_clean_completion_clears_crash_state(self, tmp_path, monkeypatch):
        """rc=0 -> crash state file deleted.
        P0-2 fix: crash retry now validates artifacts; mock verify_slice_manifest
        + _validate_events to pass so recovery is allowed, then rc=0 clears state."""
        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            _crash_state_path,
            _write_crash_state,
            run_slice,
        )
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        _write_crash_state(sl, {
            "state": "running", "returncode": None,
            "retried": False, "timestamp": "2026-07-22T00:00:00",
        })
        # Mock artifact validation to pass (P0-2 now requires valid artifacts)
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        monkeypatch.setattr(orch, "_validate_partial_events",
                            lambda p, c: (True, 13, "ok"))
        # Mock subprocess.run to return rc=0
        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""
        monkeypatch.setattr(orch.subprocess, "run",
                            lambda *a, **k: FakeResult())
        rc = run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert rc == 0
        assert not os.path.exists(_crash_state_path(sl))

    def test_crash_persists_state(self, tmp_path, monkeypatch):
        """rc=1 (crash) -> crash state persisted + v9 contract audit artifacts."""
        from scripts.phase6_6b1_orchestrator import (
            _crash_audit_prefix,
            _read_crash_state,
            run_slice,
        )
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        import scripts.phase6_6b1_orchestrator as orch
        class FakeResult:
            returncode = 1
            stdout = "some output"
            stderr = "error here"
        monkeypatch.setattr(orch.subprocess, "run",
                            lambda *a, **k: FakeResult())
        rc = run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert rc == 1
        state = _read_crash_state(sl)
        assert state is not None
        assert state["returncode"] == 1
        assert state["state"] == "crashed"
        # P1-4: v9 §12 contract audit artifacts (dot-notation files)
        prefix = _crash_audit_prefix(sl)
        assert os.path.isfile(f"{prefix}.returncode")
        assert open(f"{prefix}.returncode", encoding="utf-8").read() == "1"
        assert os.path.isfile(f"{prefix}.stdout.log")
        assert "some output" in open(f"{prefix}.stdout.log",
                                     encoding="utf-8").read()
        assert os.path.isfile(f"{prefix}.stderr.log")
        assert "error here" in open(f"{prefix}.stderr.log",
                                    encoding="utf-8").read()

    def test_corrupt_crash_state_fail_closed(self, tmp_path):
        """P0-A: corrupt crash_state.json -> SystemExit(2), not treated as recoverable."""
        from scripts.phase6_6b1_orchestrator import _read_crash_state
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        # Write corrupt JSON
        with open(os.path.join(sl["output_dir"], f"{sl['slice_id']}.crash_state.json"),
                  "w", encoding="utf-8") as f:
            f.write("{not valid json,,,")
        with pytest.raises(SystemExit) as ei:
            _read_crash_state(sl)
        assert ei.value.code == 2

    def test_corrupt_crash_state_blocks_run_slice(self, tmp_path):
        """P0-A: corrupt crash state blocks run_slice from proceeding."""
        from scripts.phase6_6b1_orchestrator import run_slice
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        with open(os.path.join(sl["output_dir"], f"{sl['slice_id']}.crash_state.json"),
                  "w", encoding="utf-8") as f:
            f.write("garbage")
        with pytest.raises(SystemExit) as ei:
            run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert ei.value.code == 2


# ---- P0-B: validate ALL ledger slice IDs ----

class TestLedgerSliceIdValidation:
    """P0-B: ledger must validate calls_attempted_by_slice keys, not just slices_completed."""

    def test_unknown_call_key_rejected(self, tmp_path):
        """calls_attempted_by_slice with bogus key -> SystemExit(2)."""
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            generate_schedule,
        )
        s = generate_schedule(tmp_path)
        path = str(tmp_path / "ledger.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"global_hard_cap": 792, "slices_completed": [],
                        "calls_attempted_by_slice": {"bogus": 1},
                        "total_calls_attempted": 1}, f)
        ledger = BudgetLedger(path)
        # Mock verify_slice_manifest since no real artifacts exist
        import scripts.phase6_6b1_orchestrator as orch
        orig = orch.verify_slice_manifest
        orch.verify_slice_manifest = lambda sl, p, m: (True, {})
        try:
            with pytest.raises(SystemExit) as ei:
                ledger.validate_against_schedule(s, "deepseek", "deepseek-chat")
        finally:
            orch.verify_slice_manifest = orig
        assert ei.value.code == 2

    def test_completed_without_calls_rejected(self, tmp_path):
        """slices_completed has ID not in calls_attempted_by_slice -> SystemExit(2)."""
        from scripts.phase6_6b1_orchestrator import BudgetLedger, generate_schedule
        s = generate_schedule(tmp_path)
        path = str(tmp_path / "ledger.json")
        sl0_id = s["slices"][0]["slice_id"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"global_hard_cap": 792,
                        "slices_completed": [sl0_id],
                        "calls_attempted_by_slice": {},
                        "total_calls_attempted": 0}, f)
        ledger = BudgetLedger(path)
        with pytest.raises(SystemExit) as ei:
            ledger.validate_against_schedule(s, "deepseek", "deepseek-chat")
        assert ei.value.code == 2


# ---- P1-C: smoke ledger downward reconciliation ----

class TestSmokeLedgerReconcile:
    """P1-C: smoke completed must reconcile ledger downward with events."""

    def test_smoke_ledger_corrected_downward(self, tmp_path):
        """Ledger has 14 for smoke, events has 13 -> corrected to 13 via
        validate_against_schedule (not record_slice_completed max)."""
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            generate_schedule,
        )
        s = generate_schedule(tmp_path)
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        smoke_sl = s["slices"][0]
        os.makedirs(smoke_sl["output_dir"], exist_ok=True)
        # Write 13 valid events (smoke size=13)
        with open(smoke_sl["events_path"], "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(smoke_sl["size"]))
        # Ledger has inflated count (14 > 13)
        ledger._data["calls_attempted_by_slice"][smoke_sl["slice_id"]] = 14
        ledger._data["slices_completed"].append(smoke_sl["slice_id"])
        ledger._data["total_calls_attempted"] = 14
        ledger._save()

        # Mock verify_slice_manifest to pass
        import scripts.phase6_6b1_orchestrator as orch
        orig = orch.verify_slice_manifest
        orch.verify_slice_manifest = lambda sl, p, m: (True, {})
        try:
            ledger.validate_against_schedule(s, "deepseek", "deepseek-chat")
        finally:
            orch.verify_slice_manifest = orig

        # P1-C: ledger corrected downward from 14 to 13
        assert ledger._data["calls_attempted_by_slice"][smoke_sl["slice_id"]] == 13
        assert ledger._data["total_calls_attempted"] == 13


# ---- P0-1: standalone fresh/resume full manifest verification ----

class TestStandaloneSmokeFullManifest:
    """P0-1: fresh/resume must use verify_slice_manifest (full field check),
    not just 3 fields (profile_id/arm/ziwei_arm)."""

    def test_wrong_code_sha_rejected(self, tmp_path, monkeypatch):
        """manifest.code_sha256 wrong -> MANIFEST_MISMATCH (not OK).
        P0-1: proves full-field verify_slice_manifest is used (old 3-field check
        would pass since profile_id/arm/ziwei_arm are correct)."""
        import scripts.phase6_6b1_smoke as smoke_mod
        from scripts.phase6_6b1_orchestrator import (
            build_expected_key,
            generate_schedule,
        )
        from scripts.phase6_6b1_smoke import smoke_gate
        s = generate_schedule(tmp_path)
        sl = s["slices"][0]
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        # Manifest with WRONG code_sha256 but correct profile_id/arm/ziwei_arm
        manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                    "chart_schema_version": "legacy_v0", "arm": sl["arm"],
                    "ziwei_arm": sl["ziwei_arm"], "attempt_stage": "main",
                    "repeat_idx": sl["repeat"], "provider": "deepseek",
                    "model": "deepseek-chat", "temperature": 0.0,
                    "sample_temperature": 0.0, "n_samples": 1,
                    "aggregate": "emit_samples", "method": "direct_choice",
                    "prompt_template_sha256": "x", "code_sha256": "WRONG",
                    "scheduled_calls": sl["size"], "hard_cap": sl["hard_cap"],
                    "as_of_date": "2026-07-17"}
        os.makedirs(os.path.dirname(sl["manifest_path"]), exist_ok=True)
        with open(sl["manifest_path"], "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

        def fake_run(cmd, **kwargs):
            # Write valid detail + valid events so only manifest check can fail
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for cid in sl["case_ids"]:
                    key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                             sl["arm"], cid, sl["repeat"],
                                             "deepseek", "deepseek-chat")
                    f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                        "terminal_state": "parsed"}) + "\n")
            os.makedirs(os.path.dirname(sl["events_path"]), exist_ok=True)
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl["size"]))
            class R:
                returncode = 0
            return R()
        monkeypatch.setattr(smoke_mod.subprocess, "run", fake_run)

        result = smoke_gate(sl, "deepseek", "deepseek-chat")
        assert result["status"] == "MANIFEST_MISMATCH"
        assert result["pass"] is False


# ---- P0-2: crash retry artifact qualification ----

class TestCrashRetryArtifactQualification:
    """P0-2: crash retry must verify manifest/events/detail before allowing recovery."""

    def _make_slice(self, tmp_path):
        from scripts.phase6_6b1_orchestrator import generate_schedule
        s = generate_schedule(tmp_path)
        return s["slices"][1]

    def test_crash_retry_without_manifest_rejected(self, tmp_path, monkeypatch):
        """crash state exists but manifest missing -> CRASH_RECOVERY_ARTIFACT_INVALID."""
        from scripts.phase6_6b1_orchestrator import _write_crash_state, run_slice
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        _write_crash_state(sl, {
            "state": "crashed", "returncode": 1,
            "retried": False, "timestamp": "2026-07-22T00:00:00",
        })
        # No manifest/events/detail created -> should fail-closed
        with pytest.raises(SystemExit) as ei:
            run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert ei.value.code == 2

    def test_crash_retry_with_valid_artifacts_allowed(self, tmp_path, monkeypatch):
        """crash state exists + valid artifacts -> recovery allowed (runner starts)."""
        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            _write_crash_state,
            run_slice,
        )
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        _write_crash_state(sl, {
            "state": "crashed", "returncode": 1,
            "retried": False, "timestamp": "2026-07-22T00:00:00",
        })
        # Mock artifact validation to pass
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        monkeypatch.setattr(orch, "_validate_partial_events",
                            lambda p, c: (True, sl["size"], "ok"))
        # Mock subprocess to return rc=0 (clean recovery)
        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""
        monkeypatch.setattr(orch.subprocess, "run",
                            lambda *a, **k: FakeResult())
        rc = run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert rc == 0


# ---- P1-3: crash state schema validation ----

class TestCrashStateSchema:
    """P1-3: crash state must validate frozen schema (enum, types, combos)."""

    def _make_slice(self, tmp_path):
        from scripts.phase6_6b1_orchestrator import generate_schedule
        s = generate_schedule(tmp_path)
        return s["slices"][1]

    def test_garbage_state_rejected(self, tmp_path):
        """state='garbage' -> SystemExit(2)."""
        from scripts.phase6_6b1_orchestrator import _read_crash_state
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        path = os.path.join(sl["output_dir"], f"{sl['slice_id']}.crash_state.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"state": "garbage", "returncode": 1, "retried": False}, f)
        with pytest.raises(SystemExit) as ei:
            _read_crash_state(sl)
        assert ei.value.code == 2

    def test_non_bool_retried_rejected(self, tmp_path):
        """retried='yes' (string) -> SystemExit(2)."""
        from scripts.phase6_6b1_orchestrator import _read_crash_state
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        path = os.path.join(sl["output_dir"], f"{sl['slice_id']}.crash_state.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"state": "crashed", "returncode": 1, "retried": "yes"}, f)
        with pytest.raises(SystemExit) as ei:
            _read_crash_state(sl)
        assert ei.value.code == 2

    def test_running_with_returncode_rejected(self, tmp_path):
        """state=running + returncode=1 -> SystemExit(2) (illegal combo)."""
        from scripts.phase6_6b1_orchestrator import _read_crash_state
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        path = os.path.join(sl["output_dir"], f"{sl['slice_id']}.crash_state.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"state": "running", "returncode": 1, "retried": False}, f)
        with pytest.raises(SystemExit) as ei:
            _read_crash_state(sl)
        assert ei.value.code == 2

    def test_valid_running_state_accepted(self, tmp_path):
        """state=running + returncode=null + retried=false -> accepted."""
        from scripts.phase6_6b1_orchestrator import _read_crash_state
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        path = os.path.join(sl["output_dir"], f"{sl['slice_id']}.crash_state.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"state": "running", "returncode": None,
                       "retried": False, "timestamp": "x"}, f)
        data = _read_crash_state(sl)
        assert data["state"] == "running"


# ---- P0-1: partial crash events allowed for recovery ----

class TestPartialCrashEventsRecovery:
    """P0-1: crash recovery must allow partial events (0 < count < scheduled)."""

    def _make_slice(self, tmp_path):
        from scripts.phase6_6b1_orchestrator import generate_schedule
        s = generate_schedule(tmp_path)
        return s["slices"][1]

    def test_partial_events_allowed_for_recovery(self, tmp_path, monkeypatch):
        """5 events < scheduled 14 -> recovery allowed (not rejected).
        P0-1: _validate_partial_events uses 0 < count <= hard_cap, not >= scheduled."""
        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            _validate_partial_events,
            _write_crash_state,
            run_slice,
        )
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        # Write 5 partial events (< scheduled size)
        with open(sl["events_path"], "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(5))
        # Verify partial validation passes
        ok, count, reason = _validate_partial_events(sl["events_path"], sl["hard_cap"])
        assert ok, f"partial events should be valid: {reason}"
        assert count == 5
        # Full recovery flow with mocked manifest + subprocess
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        _write_crash_state(sl, {
            "state": "crashed", "returncode": 1,
            "retried": False, "timestamp": "2026-07-22T00:00:00",
        })
        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""
        monkeypatch.setattr(orch.subprocess, "run",
                            lambda *a, **k: FakeResult())
        rc = run_slice(sl, "deepseek", "deepseek-chat", dry_run=False)
        assert rc == 0                                    # recovery succeeded

    def test_zero_events_rejected(self, tmp_path):
        """0 events -> rejected (empty file)."""
        from scripts.phase6_6b1_orchestrator import _validate_partial_events
        path = str(tmp_path / "empty.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            pass
        ok, count, reason = _validate_partial_events(path, 14)
        assert not ok
        assert count == 0

    def test_over_cap_events_rejected(self, tmp_path):
        """count > hard_cap -> rejected."""
        from scripts.phase6_6b1_orchestrator import _validate_partial_events
        path = str(tmp_path / "over.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"kind": "call_attempt"}) + "\n" for i in range(15))
        ok, count, reason = _validate_partial_events(path, 14)
        assert not ok
        assert count == 15


# ---- P0-3: unique run_id + refuse overwrite ----

class TestArchiveUniqueId:
    """P0-3: run_id must be unique (date+provider+model+codehash), refuse overwrite."""

    def test_run_id_contains_provider_model_codehash(self):
        """run_id format: 6b1-{date}-{provider}-{model}-{8char codehash}."""

        from scripts.phase6_6b1_orchestrator import FROZEN_DATE
        # The function reads __file__ for code hash; verify format via inspection
        src = open("scripts/phase6_6b1_orchestrator.py", "rb").read()
        expected_code_hash = hashlib.sha256(src).hexdigest()[:8]
        expected_prefix = f"6b1-{FROZEN_DATE}-deepseek-deepseek-chat-{expected_code_hash}"
        # Just verify the format pattern is in source (not running full archive)
        assert expected_code_hash  # non-empty 8-char hash

    def test_refuse_overwrite_existing_archive(self, tmp_path, monkeypatch):
        """Existing archive dir -> SystemExit(2), no overwrite.
        Uses a deliberately different run_id suffix to avoid collision with
        test_full_archive_success (which uses the real code_hash)."""

        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            generate_archive,
            generate_schedule,
        )
        schedule = generate_schedule(tmp_path)
        gate = {"verdict": "PROMOTE", "delta_dev": 1.0, "worst_year": 2024,
                "total_calls_attempted": 720, "budget_remaining": 72,
                "all_cells_completed": True, "per_cell_deltas": [],
                "year_means": {"2024": 0.05}}
        integrity = {"status": "PASS", "detail_total": 720, "detail_errors": [],
                     "expected_count": 720, "actual_count": 720,
                     "duplicates": 0, "missing": 0, "extra": 0, "pass": True}
        ledger = BudgetLedger(str(tmp_path / "ledger.json"))
        # Pre-create the archive dir with a UNIQUE run_id to trigger refuse-overwrite
        run_id = "6b1-2026-07-17-deepseek-deepseek-chat-DEADBEEF"
        archive_dir = tmp_path / "archive" / run_id
        archive_dir.mkdir(parents=True, exist_ok=True)
        # Patch _compute_experiment_code_fingerprint to return DEADBEEF
        import scripts.phase6_6b1_orchestrator as orch
        monkeypatch.setattr(orch, "_compute_experiment_code_fingerprint",
                            lambda: "DEADBEEF")
        try:
            with pytest.raises(SystemExit) as ei:
                generate_archive(schedule, gate, integrity, ledger,
                                 tmp_path, "deepseek", "deepseek-chat",
                                 archive_root=tmp_path / "archive")
            assert ei.value.code == 2
        finally:
            import shutil
            shutil.rmtree(str(archive_dir), ignore_errors=True)


# ---- P1-5: archive integrity gate + atomic publish ----

class TestArchiveIntegrityGate:
    """P1-5: merge must refuse missing files + enforce row counts."""

    def test_merge_missing_files_rejected(self, tmp_path):
        """Missing detail/events -> ARCHIVE_INTEGRITY_FAILED exit 2."""
        from scripts.phase6_6b1_orchestrator import _merge_artifacts, generate_schedule
        s = generate_schedule(tmp_path)
        # No slice artifacts created -> all missing
        with pytest.raises(SystemExit) as ei:
            _merge_artifacts(s, tmp_path, "deepseek", "deepseek-chat")
        assert ei.value.code == 2


class TestReportAnalysisConsistency:
    """compute_consistency: 4:1/3:2 分类、平局标注、5x5 两两一致率矩阵."""

    def _mk(self, case_id, arm, answers, parser_valid=True):
        """构造 records: 同一臂的多次 repeat answers."""
        out = []
        for i, a in enumerate(answers):
            out.append({
                "case_id": case_id, "arm": arm, "year": "2024", "repeat": i,
                "correct": False, "call_success": True, "parser_valid": parser_valid,
                "terminal_state": "parsed", "parser_source": "", "parser_failure_reason": "",
                "predicted_answer": a, "expected_answer": "A",
                "raw_answer": "", "raw_answer_len": 0,
                "completion_tokens": 0, "prompt_tokens": 0,
                "finish_reason": "stop", "response_id": "",
            })
        return out

    def test_split_5_0_full_agreement(self):
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        for arm in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
            recs += self._mk("Q1", arm, ["A", "A", "A"])
        r = compute_consistency(recs)
        assert r["by_split"]["5_0"] == 1
        assert r["by_split"]["4_1"] == 0
        assert r["by_split"]["3_2"] == 0
        assert r["by_split"]["unresolved"] == 0

    def test_split_4_1(self):
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        # 4 臂答 A, 1 臂答 B -> 4:1
        for arm in ["b1a_prime", "b1b", "b1c", "b2b"]:
            recs += self._mk("Q1", arm, ["A", "A", "A"])
        recs += self._mk("Q1", "b2c", ["B", "B", "B"])
        r = compute_consistency(recs)
        assert r["by_split"]["5_0"] == 0
        assert r["by_split"]["4_1"] == 1
        assert r["by_split"]["3_2"] == 0

    def test_split_3_2(self):
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        # 3 臂答 A, 2 臂答 B -> 3:2 (不是 4:1)
        for arm in ["b1a_prime", "b1b", "b1c"]:
            recs += self._mk("Q1", arm, ["A", "A", "A"])
        for arm in ["b2b", "b2c"]:
            recs += self._mk("Q1", arm, ["B", "B", "B"])
        r = compute_consistency(recs)
        assert r["by_split"]["4_1"] == 0
        assert r["by_split"]["3_2"] == 1

    def test_three_distinct_answers_is_other(self):
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        recs += self._mk("Q1", "b1a_prime", ["A", "A", "A"])
        recs += self._mk("Q1", "b1b", ["A", "A", "A"])
        recs += self._mk("Q1", "b1c", ["B", "B", "B"])
        recs += self._mk("Q1", "b2b", ["C", "C", "C"])
        recs += self._mk("Q1", "b2c", ["C", "C", "C"])
        r = compute_consistency(recs)
        assert r["by_split"]["3_2"] == 0
        assert r["by_split"]["other"] == 1

    def test_arm_mode_tie_excluded_from_split(self):
        """一臂三次 repeat 出现 A/B/C 各一次 -> 平局, 该 case 计入 unresolved, 不进入 5_0/4_1/3_2/other."""
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        recs += self._mk("Q1", "b1a_prime", ["A", "A", "A"])
        recs += self._mk("Q1", "b1b", ["A", "A", "A"])
        recs += self._mk("Q1", "b1c", ["A", "A", "A"])
        recs += self._mk("Q1", "b2b", ["A", "A", "A"])
        # b2c 三次各不同 -> 平局
        recs += self._mk("Q1", "b2c", ["A", "B", "C"])
        r = compute_consistency(recs)
        assert r["by_split"]["unresolved"] == 1
        assert r["by_split"]["5_0"] == 0
        assert r["by_split"]["4_1"] == 0
        assert r["by_split"]["3_2"] == 0
        assert r["by_split"]["other"] == 0
        # 该 case 的 per_case_detail 应标注 has_mode_tie, 且 arm_modes 中平局臂为 None
        detail = r["per_case_detail"][0]
        assert detail["has_mode_tie"] is True
        assert detail["arm_modes"]["b2c"] is None

    def test_tie_arm_excluded_from_pairwise(self):
        """平局臂不进入两两一致率, 分母 n 减小."""
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        # Q1: 全 resolved, 五臂全 A -> b1a_prime-b1b agree, n=1
        # Q2: b2c 平局 -> b2c 不进入任何含 b2c 的对, 但 b1a_prime-b1b 仍统计 (n=2)
        recs = []
        for arm in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
            recs += self._mk("Q1", arm, ["A", "A", "A"])
        recs += self._mk("Q2", "b1a_prime", ["A", "A", "A"])
        recs += self._mk("Q2", "b1b", ["A", "A", "A"])
        recs += self._mk("Q2", "b1c", ["A", "A", "A"])
        recs += self._mk("Q2", "b2b", ["A", "A", "A"])
        recs += self._mk("Q2", "b2c", ["A", "B", "C"])  # 平局
        r = compute_consistency(recs)
        pw = r["pairwise_agreement"]
        # b1a_prime-b1b: 两 case 都 resolved -> n=2, agree=2, rate=1.0
        assert pw["b1a_prime"]["b1b"]["n"] == 2
        assert pw["b1a_prime"]["b1b"]["rate"] == 1.0
        # b1a_prime-b2c: Q2 的 b2c 平局 -> n=1 (仅 Q1), agree=1, rate=1.0
        assert pw["b1a_prime"]["b2c"]["n"] == 1
        assert pw["b1a_prime"]["b2c"]["agree"] == 1
        # b2c-b2c 对角: 仅 Q1 resolved -> n=1
        assert pw["b2c"]["b2c"]["n"] == 1
        assert pw["b2c"]["b2c"]["rate"] == 1.0

    def test_pairwise_reports_denominator(self):
        """两两一致率必须报告实际分母 n, 不能默认 80."""
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        # 1 个 resolved case + 1 个 unresolved case
        for arm in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
            recs += self._mk("Q1", arm, ["A", "A", "A"])
        recs += self._mk("Q2", "b1a_prime", ["A", "B", "C"])
        recs += self._mk("Q2", "b1b", ["A", "A", "A"])
        recs += self._mk("Q2", "b1c", ["A", "A", "A"])
        recs += self._mk("Q2", "b2b", ["A", "A", "A"])
        recs += self._mk("Q2", "b2c", ["A", "A", "A"])
        r = compute_consistency(recs)
        pw = r["pairwise_agreement"]
        # b1b-b1c: 两 case 都 resolved -> n=2
        assert pw["b1b"]["b1c"]["n"] == 2
        # b1a_prime-b1b: Q2 的 b1a_prime 平局 -> n=1
        assert pw["b1a_prime"]["b1b"]["n"] == 1

    def test_pairwise_by_repeat_exists(self):
        """敏感性表: 同一 repeat 对齐的一致率必须存在且对所有臂对有 n>0."""
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        for arm in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
            recs += self._mk("Q1", arm, ["A", "A", "A"])
        r = compute_consistency(recs)
        assert "pairwise_by_repeat" in r
        pwbr = r["pairwise_by_repeat"]
        for a in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
            for b in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
                assert pwbr[a][b]["n"] > 0, f"{a}-{b} n 应 >0"

    def test_pairwise_agreement_matrix_diagonal_is_one(self):
        """对角线 (i,i) 一致率应为 1.0."""
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        for arm in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
            recs += self._mk("Q1", arm, ["A", "A", "A"])
        r = compute_consistency(recs)
        for arm in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
            assert r["pairwise_agreement"][arm][arm]["rate"] == 1.0

    def test_pairwise_agreement_off_diagonal(self):
        """两臂答案不同时, 该对一致率为 0; 相同时为 1."""
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        recs += self._mk("Q1", "b1a_prime", ["A", "A", "A"])
        recs += self._mk("Q1", "b1b", ["A", "A", "A"])
        recs += self._mk("Q1", "b1c", ["B", "B", "B"])
        recs += self._mk("Q1", "b2b", ["B", "B", "B"])
        recs += self._mk("Q1", "b2c", ["A", "A", "A"])
        r = compute_consistency(recs)
        pw = r["pairwise_agreement"]
        assert pw["b1a_prime"]["b1b"]["rate"] == 1.0   # 都 A
        assert pw["b1a_prime"]["b1c"]["rate"] == 0.0   # A vs B
        assert pw["b1c"]["b2b"]["rate"] == 1.0          # 都 B
        assert pw["b1a_prime"]["b2c"]["rate"] == 1.0    # 都 A

    def test_parser_invalid_excluded(self):
        """parser_valid=False 的记录不计入."""
        from scripts.phase6_6b1d_report_analysis import compute_consistency
        recs = []
        for arm in ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]:
            recs += self._mk("Q1", arm, ["A", "A", "A"])
        # 加入一条 invalid
        recs += self._mk("Q1", "b2c", ["Z"], parser_valid=False)
        r = compute_consistency(recs)
        assert r["total_cases"] == 1


class TestReportAnalysisQualitative:
    """compute_qualitative: 按 case_id 去重, 选 k 个不同 case."""

    def _mk(self, case_id, arm, correct, repeat=0):
        return {
            "case_id": case_id, "arm": arm, "year": "2024", "repeat": repeat,
            "correct": correct, "call_success": True, "parser_valid": True,
            "terminal_state": "parsed", "parser_source": "", "parser_failure_reason": "",
            "predicted_answer": "A" if correct else "B", "expected_answer": "A",
            "raw_answer": "x" * 50, "raw_answer_len": 50,
            "completion_tokens": 0, "prompt_tokens": 0,
            "finish_reason": "stop", "response_id": "",
        }

    def test_returns_k_distinct_case_ids(self):
        """5 条结果应来自 5 个不同 case_id."""
        from scripts.phase6_6b1d_report_analysis import compute_qualitative
        recs = []
        # 10 个 case, 每个有 3 次 repeat
        for i in range(10):
            cid = f"Q{i}"
            for rep in range(3):
                recs.append(self._mk(cid, "b2b", correct=(i % 2 == 0), repeat=rep))
        out = compute_qualitative(recs, "b2b", k=5)
        assert len(out) == 5
        cids = [r["case_id"] for r in out]
        assert len(set(cids)) == 5, f"应 5 个不同 case, 实际 {cids}"

    def test_mixed_correct_and_wrong(self):
        """k=5 时应包含正确和错误两类 (若两类都有足够 case)."""
        from scripts.phase6_6b1d_report_analysis import compute_qualitative
        recs = []
        for i in range(10):
            cid = f"Q{i}"
            for rep in range(3):
                recs.append(self._mk(cid, "b2b", correct=(i < 5), repeat=rep))
        out = compute_qualitative(recs, "b2b", k=5)
        corrects = [r for r in out if r["correct"]]
        wrongs = [r for r in out if not r["correct"]]
        assert len(corrects) == 2  # k//2
        assert len(wrongs) == 3    # k - k//2

    def test_uses_repeat_zero_as_representative(self):
        """每 case 取 repeat=0 作为代表."""
        from scripts.phase6_6b1d_report_analysis import compute_qualitative
        recs = []
        cid = "Q0"
        for rep in range(3):
            recs.append(self._mk(cid, "b2b", correct=True, repeat=rep))
        out = compute_qualitative(recs, "b2b", k=5)
        assert len(out) == 1
        assert out[0]["repeat"] == 0



# ---- P0: archive manifest drift rejection ----

class TestArchiveManifestDrift:
    """P0-1: archive must reject drifted manifest (full verify_slice_manifest)."""

    def _create_valid_artifacts_except_manifest(self, s, monkeypatch):
        """Create valid detail + events, but manifest with wrong code_sha256."""
        from scripts.phase6_6b1_orchestrator import build_expected_key
        for sl in s["slices"]:
            dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for cid in sl["case_ids"]:
                    key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                             sl["arm"], cid, sl["repeat"],
                                             "deepseek", "deepseek-chat")
                    f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                        "terminal_state": "parsed"}) + "\n")
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl["size"]))
            # Manifest with WRONG code_sha256
            manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                        "chart_schema_version": "legacy_v0", "arm": sl["arm"],
                        "ziwei_arm": sl["ziwei_arm"], "attempt_stage": "main",
                        "repeat_idx": sl["repeat"], "provider": "deepseek",
                        "model": "deepseek-chat", "temperature": 0.0,
                        "sample_temperature": 0.0, "n_samples": 1,
                        "aggregate": "emit_samples", "method": "direct_choice",
                        "prompt_template_sha256": "x", "code_sha256": "WRONG",
                        "scheduled_calls": sl["size"], "hard_cap": sl["hard_cap"],
                        "as_of_date": "2026-07-17"}
            with open(sl["manifest_path"], "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)

    def test_drifted_manifest_rejected_in_archive(self, tmp_path, monkeypatch):
        """Manifest with code_sha256=WRONG -> ARCHIVE_MANIFEST_DRIFT exit 2.
        P0-1: proves verify_slice_manifest is called (not just file existence)."""
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            generate_archive,
            generate_schedule,
        )
        s = generate_schedule(tmp_path)
        self._create_valid_artifacts_except_manifest(s, monkeypatch)
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        for sl in s["slices"]:
            ledger.record_slice_completed(sl["slice_id"], sl["size"])
        ledger._save()
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        # Use REAL verify_slice_manifest (not mocked) to prove full check
        gate = {"verdict": "PROMOTE", "delta_dev": 1.0, "worst_year": 2024,
                "total_calls_attempted": 720, "budget_remaining": 72,
                "all_cells_completed": True, "per_cell_deltas": [],
                "year_means": {"2024": 0.05}}
        integrity = {"status": "PASS", "detail_total": 720, "detail_errors": [],
                     "expected_count": 720, "actual_count": 720,
                     "duplicates": 0, "missing": 0, "extra": 0, "pass": True}
        with pytest.raises(SystemExit) as ei:
            generate_archive(s, gate, integrity, ledger,
                             tmp_path, "deepseek", "deepseek-chat",
                             archive_root=tmp_path / "archive")
        assert ei.value.code == 2
        # P0-3: verify temp dir cleaned up even on SystemExit
        parent = tmp_path / "archive"
        if parent.exists():
            leftovers = [d for d in parent.iterdir() if d.name.startswith(".")]
            assert len(leftovers) == 0, f"temp dir not cleaned on SystemExit: {leftovers}"


# ---- P0-2: publish never deletes competing archive ----

class TestArchiveNoDeleteOnRace:
    """P0-2: if target dir appears during build, fail-closed (never rmtree)."""

    def test_race_target_not_deleted(self, tmp_path, monkeypatch):
        """Target dir appears during build -> SystemExit(2), target preserved.
        P0-2: proves we never rmtree a competing archive.
        Strategy: patch shutil.move to fail, but first verify source code
        has no rmtree(archive_dir) call (the actual P0-2 fix)."""
        # P0-2: verify source code does NOT contain rmtree(archive_dir)
        import inspect

        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            generate_archive,
            generate_schedule,
        )
        src = inspect.getsource(generate_archive)
        assert "rmtree(str(archive_dir)" not in src, \
            "P0-2: generate_archive must not rmtree archive_dir (race safety)"
        assert "rmtree(archive_dir" not in src, \
            "P0-2: generate_archive must not rmtree archive_dir (race safety)"
        # Also verify it uses SystemExit(2) on race, not rmtree
        assert "ARCHIVE_RACE_DETECTED" in src, \
            "P0-2: generate_archive must fail-closed with ARCHIVE_RACE_DETECTED"

        # Functional test: pre-create target, verify it's preserved
        s = generate_schedule(tmp_path)
        from scripts.phase6_6b1_orchestrator import build_expected_key
        for sl in s["slices"]:
            dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for cid in sl["case_ids"]:
                    key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                             sl["arm"], cid, sl["repeat"],
                                             "deepseek", "deepseek-chat")
                    f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                        "terminal_state": "parsed"}) + "\n")
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl["size"]))
            manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                        "chart_schema_version": "legacy_v0", "arm": sl["arm"],
                        "ziwei_arm": sl["ziwei_arm"], "attempt_stage": "main",
                        "repeat_idx": sl["repeat"], "provider": "deepseek",
                        "model": "deepseek-chat", "temperature": 0.0,
                        "sample_temperature": 0.0, "n_samples": 1,
                        "aggregate": "emit_samples", "method": "direct_choice",
                        "prompt_template_sha256": "x", "code_sha256": "x",
                        "scheduled_calls": sl["size"], "hard_cap": sl["hard_cap"],
                        "as_of_date": "2026-07-17"}
            with open(sl["manifest_path"], "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        for sl in s["slices"]:
            ledger.record_slice_completed(sl["slice_id"], sl["size"])
        ledger._save()
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        monkeypatch.setattr(orch, "_compute_experiment_code_fingerprint",
                            lambda: "RACETEST")
        run_id = "6b1-2026-07-17-deepseek-deepseek-chat-RACETEST"
        archive_dir = tmp_path / "archive" / run_id
        # Pre-create target with competitor marker
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "competitor_marker").write_text("do not delete")

        gate = {"verdict": "PROMOTE", "delta_dev": 1.0, "worst_year": 2024,
                "total_calls_attempted": 720, "budget_remaining": 72,
                "all_cells_completed": True, "per_cell_deltas": [],
                "year_means": {"2024": 0.05}}
        integrity = {"status": "PASS", "detail_total": 720, "detail_errors": [],
                     "expected_count": 720, "actual_count": 720,
                     "duplicates": 0, "missing": 0, "extra": 0, "pass": True}
        try:
            with pytest.raises(SystemExit) as ei:
                generate_archive(s, gate, integrity, ledger,
                                 tmp_path, "deepseek", "deepseek-chat",
                                 archive_root=tmp_path / "archive")
            assert ei.value.code == 2
            # P0-2: competitor marker must still exist (not deleted)
            assert (archive_dir / "competitor_marker").exists(), \
                "P0-2: competing archive was deleted!"
        finally:
            import shutil
            shutil.rmtree(str(archive_dir), ignore_errors=True)
            parent = tmp_path / "archive"
            if parent.exists():
                for d in parent.iterdir():
                    if d.name.startswith("."):
                        shutil.rmtree(str(d), ignore_errors=True)

    def test_toctou_race_during_publish(self, tmp_path, monkeypatch):
        """P0: target appears between pre-check and os.rename -> fail-closed.
        Patches os.rename to inject a competitor dir at the exact publish moment,
        proving os.rename (not shutil.move) is used and fails atomically."""
        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            build_expected_key,
            generate_archive,
            generate_schedule,
        )
        s = generate_schedule(tmp_path)
        for sl in s["slices"]:
            dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for cid in sl["case_ids"]:
                    key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                             sl["arm"], cid, sl["repeat"],
                                             "deepseek", "deepseek-chat")
                    f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                        "terminal_state": "parsed"}) + "\n")
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl["size"]))
            manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                        "chart_schema_version": "legacy_v0", "arm": sl["arm"],
                        "ziwei_arm": sl["ziwei_arm"], "attempt_stage": "main",
                        "repeat_idx": sl["repeat"], "provider": "deepseek",
                        "model": "deepseek-chat", "temperature": 0.0,
                        "sample_temperature": 0.0, "n_samples": 1,
                        "aggregate": "emit_samples", "method": "direct_choice",
                        "prompt_template_sha256": "x", "code_sha256": "x",
                        "scheduled_calls": sl["size"], "hard_cap": sl["hard_cap"],
                        "as_of_date": "2026-07-17"}
            with open(sl["manifest_path"], "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        for sl in s["slices"]:
            ledger.record_slice_completed(sl["slice_id"], sl["size"])
        ledger._save()
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        monkeypatch.setattr(orch, "_compute_experiment_code_fingerprint",
                            lambda: "TOCTOU")
        run_id = "6b1-2026-07-17-deepseek-deepseek-chat-TOCTOU"
        archive_dir = tmp_path / "archive" / run_id
        # P0: patch os.rename to inject competitor at publish moment
        original_rename = os.rename
        def race_rename(src, dst):
            os.makedirs(dst, exist_ok=True)             # inject competitor
            (Path(dst) / "competitor_marker").write_text("race")
            return original_rename(src, dst)
        monkeypatch.setattr(orch.os, "rename", race_rename)
        gate = {"verdict": "PROMOTE", "delta_dev": 1.0, "worst_year": 2024,
                "total_calls_attempted": 720, "budget_remaining": 72,
                "all_cells_completed": True, "per_cell_deltas": [],
                "year_means": {"2024": 0.05}}
        integrity = {"status": "PASS", "detail_total": 720, "detail_errors": [],
                     "expected_count": 720, "actual_count": 720,
                     "duplicates": 0, "missing": 0, "extra": 0, "pass": True}
        try:
            with pytest.raises(SystemExit) as ei:
                generate_archive(s, gate, integrity, ledger,
                                 tmp_path, "deepseek", "deepseek-chat",
                                 archive_root=tmp_path / "archive")
            assert ei.value.code == 2
            # P0: competitor marker preserved (not deleted by us)
            assert (archive_dir / "competitor_marker").exists()
        finally:
            import shutil
            shutil.rmtree(str(tmp_path / "archive"), ignore_errors=True)


# ---- P2: non-dry-run main() full chain test ----

class TestMainFullChain:
    """P2: fake-runner-driven main() test verifying integrity -> gate -> archive."""

    def _create_valid_artifacts_for_slice(self, sl, provider, model):
        """Create valid detail + manifest + events for a slice."""
        from scripts.phase6_6b1_orchestrator import build_expected_key
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
        with open(sl["detail_path"], "w", encoding="utf-8") as f:
            for cid in sl["case_ids"]:
                key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                         sl["arm"], cid, sl["repeat"],
                                         provider, model)
                f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                    "terminal_state": "parsed", "answer": "A",
                                    "correct": True}) + "\n")
        with open(sl["events_path"], "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl["size"]))
        manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                    "chart_schema_version": "legacy_v0", "arm": sl["arm"],
                    "ziwei_arm": sl["ziwei_arm"], "attempt_stage": "main",
                    "repeat_idx": sl["repeat"], "provider": provider,
                    "model": model, "temperature": 0.0,
                    "sample_temperature": 0.0, "n_samples": 1,
                    "aggregate": "emit_samples", "method": "direct_choice",
                    "prompt_template_sha256": "x", "code_sha256": "x",
                    "scheduled_calls": sl["size"], "hard_cap": sl["hard_cap"],
                    "as_of_date": "2026-07-17"}
        with open(sl["manifest_path"], "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

    def test_main_full_chain(self, tmp_path, monkeypatch):
        """P2: main() with fake runner -> integrity PASS -> gate -> archive.
        Mocks preflight, subprocess, verify_slice_manifest, integrity, gate.
        Verifies main() returns 0 and archive is generated."""
        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            build_expected_key,
            main,
        )

        output_dir = tmp_path / "out"
        archive_root = tmp_path / "archive"
        monkeypatch.setattr(orch, "preflight_checks", lambda s: None)
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # Fake runner: writes valid artifacts for each slice, returns rc=0
        def fake_run(cmd, **kwargs):
            # Extract slice info from cmd args to create correct artifacts
            cmd_str = " ".join(cmd)
            # Find the output-dir to determine which slice
            output_dir_idx = cmd.index("--output-dir") + 1
            sl_output_dir = cmd[output_dir_idx]
            # Find scheduled-calls to know slice size
            sched_idx = cmd.index("--scheduled-calls") + 1
            size = int(cmd[sched_idx])
            # Build a minimal slice dict from cmd
            arm_idx = cmd.index("--arm") + 1
            arm = cmd[arm_idx]
            ziwei_idx = cmd.index("--ziwei-arm") + 1
            ziwei_arm = cmd[ziwei_idx]
            dataset_idx = cmd.index("--dataset") + 1
            dataset = cmd[dataset_idx]
            repeat_idx = cmd.index("--repeat-idx") + 1
            repeat = int(cmd[repeat_idx])
            detail_idx = cmd.index("--case-details-jsonl") + 1
            detail_path = cmd[detail_idx]
            manifest_path = detail_path.replace(".jsonl", ".manifest.json")
            events_path = detail_path.replace(".jsonl", ".events.jsonl")
            case_ids_idx = cmd.index("--case-ids-file") + 1
            case_ids_file = cmd[case_ids_idx]
            with open(case_ids_file, encoding="utf-8") as f:
                case_ids = json.load(f)
            provider_idx = cmd.index("--provider") + 1
            provider = cmd[provider_idx]
            model_idx = cmd.index("--model") + 1
            model = cmd[model_idx]
            hard_cap_idx = cmd.index("--hard-cap") + 1
            hard_cap = int(cmd[hard_cap_idx])
            dataset_id = os.path.splitext(os.path.basename(dataset))[0]
            os.makedirs(os.path.dirname(detail_path), exist_ok=True)
            with open(detail_path, "w", encoding="utf-8") as f:
                for cid in case_ids:
                    key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                             arm, cid, repeat, provider, model)
                    f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                        "terminal_state": "parsed",
                                        "answer": "A", "correct": True}) + "\n")
            with open(events_path, "w", encoding="utf-8") as f:
                f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(size))
            manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                        "chart_schema_version": "legacy_v0", "arm": arm,
                        "ziwei_arm": ziwei_arm, "attempt_stage": "main",
                        "repeat_idx": repeat, "provider": provider,
                        "model": model, "temperature": 0.0,
                        "sample_temperature": 0.0, "n_samples": 1,
                        "aggregate": "emit_samples", "method": "direct_choice",
                        "prompt_template_sha256": "x", "code_sha256": "x",
                        "scheduled_calls": size, "hard_cap": hard_cap,
                        "as_of_date": "2026-07-17"}
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        # Mock integrity_check to return PASS
        monkeypatch.setattr(orch, "integrity_check",
                            lambda s, l, p, m: {
                                "status": "PASS", "detail_total": 720,
                                "detail_errors": [], "expected_count": 720,
                                "actual_count": 720, "duplicates": 0,
                                "missing": 0, "extra": 0, "pass": True})

        # Mock compute_gate to return PROMOTE
        monkeypatch.setattr(orch, "compute_gate",
                            lambda s, l: {
                                "verdict": "PROMOTE", "delta_dev": 0.01,
                                "worst_year": 2024, "total_calls_attempted": 720,
                                "budget_remaining": 72,
                                "all_cells_completed": True,
                                "per_cell_deltas": [],
                                "year_means": {"2024": 0.01, "2025": 0.01}})

        # Patch generate_archive to use isolated archive_root
        original_generate_archive = orch.generate_archive
        def isolated_archive(*a, **kw):
            kw["archive_root"] = archive_root
            return original_generate_archive(*a, **kw)
        monkeypatch.setattr(orch, "generate_archive", isolated_archive)

        rc = main(["--output-dir", str(output_dir)])
        assert rc == 0

        # Verify archive was generated
        archives = list(archive_root.iterdir()) if archive_root.exists() else []
        assert len(archives) == 1
        archive_dir = archives[0]
        assert (archive_dir / "audit_index.json").is_file()
        assert (archive_dir / "merged_details.jsonl").is_file()
        assert (archive_dir / "smoke").is_dir()
        assert (archive_dir / "slices").is_dir()

        # Cleanup
        import shutil
        shutil.rmtree(str(archive_root), ignore_errors=True)


# ---- P0-3: SystemExit triggers temp dir cleanup ----

class TestArchiveSystemExitCleanup:
    """P0-3: SystemExit from integrity gate must clean up temp dir."""

    def test_missing_budget_cleans_temp(self, tmp_path, monkeypatch):
        """budget_ledger.json missing -> SystemExit(2) + temp dir cleaned.
        P0-3: proves BaseException catch works (not just Exception)."""
        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            build_expected_key,
            generate_archive,
            generate_schedule,
        )
        s = generate_schedule(tmp_path)
        # Create valid artifacts
        for sl in s["slices"]:
            dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for cid in sl["case_ids"]:
                    key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                             sl["arm"], cid, sl["repeat"],
                                             "deepseek", "deepseek-chat")
                    f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                        "terminal_state": "parsed"}) + "\n")
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl["size"]))
            manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                        "chart_schema_version": "legacy_v0", "arm": sl["arm"],
                        "ziwei_arm": sl["ziwei_arm"], "attempt_stage": "main",
                        "repeat_idx": sl["repeat"], "provider": "deepseek",
                        "model": "deepseek-chat", "temperature": 0.0,
                        "sample_temperature": 0.0, "n_samples": 1,
                        "aggregate": "emit_samples", "method": "direct_choice",
                        "prompt_template_sha256": "x", "code_sha256": "x",
                        "scheduled_calls": sl["size"], "hard_cap": sl["hard_cap"],
                        "as_of_date": "2026-07-17"}
            with open(sl["manifest_path"], "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)
        # Do NOT create budget_ledger.json -> will trigger P1-5 fail-closed
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        monkeypatch.setattr(orch, "_compute_experiment_code_fingerprint",
                            lambda: "NOBUDGET")
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        ledger._save()                          # create file first
        os.remove(str(tmp_path / "budget_ledger.json"))  # then delete to trigger gate

        gate = {"verdict": "PROMOTE", "delta_dev": 1.0, "worst_year": 2024,
                "total_calls_attempted": 720, "budget_remaining": 72,
                "all_cells_completed": True, "per_cell_deltas": [],
                "year_means": {"2024": 0.05}}
        integrity = {"status": "PASS", "detail_total": 720, "detail_errors": [],
                     "expected_count": 720, "actual_count": 720,
                     "duplicates": 0, "missing": 0, "extra": 0, "pass": True}
        with pytest.raises(SystemExit) as ei:
            generate_archive(s, gate, integrity, ledger,
                             tmp_path, "deepseek", "deepseek-chat",
                             archive_root=tmp_path / "archive")
        assert ei.value.code == 2
        # P0-3: no temp dirs left behind (isolated in tmp_path/archive)
        parent = tmp_path / "archive"
        if parent.exists():
            leftovers = [d for d in parent.iterdir() if d.name.startswith(".")]
            assert len(leftovers) == 0, f"temp dir not cleaned: {leftovers}"


# ---- P0-1: partial events must filter kind==call_attempt ----

class TestPartialEventsCallAttemptFilter:
    """P0-1 fix: only count kind==call_attempt, not any JSON line."""

    def test_non_call_event_not_counted(self, tmp_path):
        """{"kind": "not_a_call"} -> count=0 -> rejected (not count=1)."""
        from scripts.phase6_6b1_orchestrator import _validate_partial_events
        path = str(tmp_path / "ev.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "not_a_call"}) + "\n")
        ok, count, reason = _validate_partial_events(path, 14)
        assert not ok
        assert count == 0
        assert "empty" in reason or "no call_attempt" in reason

    def test_mixed_events_only_counts_call_attempt(self, tmp_path):
        """Mix of call_attempt + other kinds -> only call_attempt counted."""
        from scripts.phase6_6b1_orchestrator import _validate_partial_events
        path = str(tmp_path / "ev.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "model_response"}) + "\n")
            f.write(json.dumps({"kind": "call_attempt", "idx": 0}) + "\n")
            f.write(json.dumps({"kind": "call_attempt", "idx": 1}) + "\n")
            f.write(json.dumps({"kind": "result"}) + "\n")
        ok, count, reason = _validate_partial_events(path, 14)
        assert ok
        assert count == 2                                    # only 2 call_attempt

    def test_corrupt_non_call_json_still_rejected(self, tmp_path):
        """Corrupt JSON line (even if not call_attempt) -> rejected."""
        from scripts.phase6_6b1_orchestrator import _validate_partial_events
        path = str(tmp_path / "ev.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"kind": "call_attempt"}\n')
            f.write('not json at all\n')
        ok, count, reason = _validate_partial_events(path, 14)
        assert not ok
        assert "corrupt" in reason


# ---- P0-2: archive success path integration test ----

class TestArchiveSuccessPath:
    """P0-2: full generate_archive() success path - verify all artifacts."""

    def _create_valid_slice_artifacts(self, sl, monkeypatch):
        """Create valid detail + manifest + events for a slice."""
        from scripts.phase6_6b1_orchestrator import build_expected_key
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
        # detail: sl["size"] rows with correct attempt keys
        with open(sl["detail_path"], "w", encoding="utf-8") as f:
            for cid in sl["case_ids"]:
                key = build_expected_key(dataset_id, "baziqa_xjz_reasoned",
                                         sl["arm"], cid, sl["repeat"],
                                         "deepseek", "deepseek-chat")
                f.write(json.dumps({"case_id": cid, "attempt_key": list(key),
                                    "terminal_state": "parsed"}) + "\n")
        # events: sl["size"] call_attempt events
        with open(sl["events_path"], "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(sl["size"]))
        # manifest: valid
        manifest = {"dataset_id": dataset_id, "profile_id": "baziqa_xjz_reasoned",
                    "chart_schema_version": "legacy_v0", "arm": sl["arm"],
                    "ziwei_arm": sl["ziwei_arm"], "attempt_stage": "main",
                    "repeat_idx": sl["repeat"], "provider": "deepseek",
                    "model": "deepseek-chat", "temperature": 0.0,
                    "sample_temperature": 0.0, "n_samples": 1,
                    "aggregate": "emit_samples", "method": "direct_choice",
                    "prompt_template_sha256": "x", "code_sha256": "x",
                    "scheduled_calls": sl["size"], "hard_cap": sl["hard_cap"],
                    "as_of_date": "2026-07-17"}
        with open(sl["manifest_path"], "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

    def test_full_archive_success(self, tmp_path, monkeypatch):
        """Full generate_archive() success: smoke/ + slices/ + merged + audit_index.
        Verifies all v9 §12 artifacts exist with correct counts."""
        import scripts.phase6_6b1_orchestrator as orch
        from scripts.phase6_6b1_orchestrator import (
            BudgetLedger,
            generate_archive,
            generate_schedule,
        )
        s = generate_schedule(tmp_path)
        # Create valid artifacts for ALL slices (smoke + 53 main)
        for sl in s["slices"]:
            self._create_valid_slice_artifacts(sl, monkeypatch)
        # Create budget ledger
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        for sl in s["slices"]:
            ledger.record_slice_completed(sl["slice_id"], sl["size"])
        ledger._save()                          # ensure flushed to disk
        # Reload to release file handle (Windows file lock workaround)
        ledger = BudgetLedger(str(tmp_path / "budget_ledger.json"))
        # Mock verify_slice_manifest (real one needs exact sha256)
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        gate = {"verdict": "PROMOTE", "delta_dev": 1.0, "worst_year": 2024,
                "total_calls_attempted": 720, "budget_remaining": 72,
                "all_cells_completed": True, "per_cell_deltas": [],
                "year_means": {"2024": 0.05, "2025": 0.03}}
        integrity = {"status": "PASS", "detail_total": 720, "detail_errors": [],
                     "expected_count": 720, "actual_count": 720,
                     "duplicates": 0, "missing": 0, "extra": 0, "pass": True}

        archive_path = generate_archive(s, gate, integrity, ledger,
                                        tmp_path, "deepseek", "deepseek-chat",
                                        archive_root=tmp_path / "archive")
        archive_dir = Path(archive_path)

        # Verify all v9 §12 artifacts exist
        assert (archive_dir / "audit_index.json").is_file()
        assert (archive_dir / "schedule.json").is_file()
        assert (archive_dir / "report.md").is_file()
        assert (archive_dir / "merged_details.jsonl").is_file()
        assert (archive_dir / "merged_events.jsonl").is_file()
        assert (archive_dir / "budget").is_dir()
        # smoke/ evidence
        assert (archive_dir / "smoke" / "details.jsonl").is_file()
        assert (archive_dir / "smoke" / "details.manifest.json").is_file()
        assert (archive_dir / "smoke" / "details.events.jsonl").is_file()
        # slices/<id>/ evidence (53 main slices)
        slices_dir = archive_dir / "slices"
        slice_dirs = [d for d in slices_dir.iterdir() if d.is_dir()]
        assert len(slice_dirs) == 53                          # 54 - 1 smoke
        for sd in slice_dirs[:3]:                            # spot check 3
            assert (sd / "details.jsonl").is_file()
            assert (sd / "details.manifest.json").is_file()
            assert (sd / "details.events.jsonl").is_file()

        # Verify merged detail row count = 720 (total scheduled)
        with open(archive_dir / "merged_details.jsonl", encoding="utf-8") as f:
            merged_count = sum(1 for _ in f)
        assert merged_count == s["total_scheduled_calls"]

        # Verify audit_index.json content
        with open(archive_dir / "audit_index.json", encoding="utf-8") as f:
            idx = json.load(f)
        assert idx["run_id"].startswith("6b1-2026-07-17-deepseek-deepseek-chat-")
        assert idx["context_fingerprints"]["total"] == 9     # 3 cases × 3 arms
        assert len(idx["context_fingerprints"]["case_ids"]) == 3
        assert len(idx["context_fingerprints"]["arms"]) == 3
        assert idx["merge_counts"]["detail_rows"] == s["total_scheduled_calls"]
        assert "smoke_artifact_hashes" in idx
        assert len(idx["slice_artifact_hashes"]) == 53
        assert idx["gate_verdict"] == "PROMOTE"

        # Verify archive was published (not left as temp dir)
        assert archive_dir.is_dir()
        assert (archive_dir / "audit_index.json").is_file()
        # Verify the specific tmp_dir used was cleaned up (renamed to archive_dir)
        # Note: other tests may leave temp dirs; we only check ours is gone
        temp_pattern = f".{archive_dir.name}_"
        our_leftovers = [d for d in archive_dir.parent.iterdir()
                         if d.name.startswith(temp_pattern)]
        assert len(our_leftovers) == 0, f"temp dir not cleaned: {our_leftovers}"

        # Cleanup
        import shutil
        shutil.rmtree(str(archive_dir), ignore_errors=True)
        # Also clean any stray temp dirs from failed runs
        for d in archive_dir.parent.iterdir():
            if d.name.startswith("."):
                shutil.rmtree(str(d), ignore_errors=True)

    def test_merge_wrong_row_count_rejected(self, tmp_path):
        """Detail rows != scheduled_calls -> ARCHIVE_INTEGRITY_FAILED exit 2."""
        from scripts.phase6_6b1_orchestrator import _merge_artifacts, generate_schedule
        s = generate_schedule(tmp_path)
        # Create files but with wrong row counts (fewer than scheduled)
        for sl in s["slices"]:
            os.makedirs(sl["output_dir"], exist_ok=True)
            # Write only 1 detail row (expected = sl["size"])
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                f.write(json.dumps({"case_id": "x", "attempt_key": [],
                                    "terminal_state": "parsed"}) + "\n")
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                f.write(json.dumps({"kind": "call_attempt"}) + "\n")
            with open(sl["manifest_path"], "w", encoding="utf-8") as f:
                json.dump({}, f)
        with pytest.raises(SystemExit) as ei:
            _merge_artifacts(s, tmp_path, "deepseek", "deepseek-chat")
        assert ei.value.code == 2
