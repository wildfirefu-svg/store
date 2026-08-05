#!/usr/bin/env python3
"""Phase 6 6B2 orchestrator tests - v18 specification coverage."""
from __future__ import annotations

import json
import os
import tempfile
import types
from pathlib import Path

import pytest


class TestTask10FrozenSchedule:
    """Task 10: frozen 60-slice schedule matrix."""

    def _make_dataset(self, tmp_path: Path, year: str, n: int = 40) -> str:
        ds_path = tmp_path / f"baziqa_{year}.jsonl"
        with open(ds_path, "w", encoding="utf-8") as f:
            for i in range(n):
                f.write(json.dumps({"case_id": f"{year}_{i:04d}"}) + "\n")
        return str(ds_path)

    def test_build_schedule_dev_has_60_slices(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds24 = self._make_dataset(tmp_path, "2024")
        ds25 = self._make_dataset(tmp_path, "2025")
        sched = _build_schedule(str(tmp_path), years=["2024", "2025"],
                                 dataset_paths={"2024": ds24, "2025": ds25})
        assert sched["total_slices"] == 60
        assert sched["global_hard_cap"] == 1060
        assert sched["total_scheduled_calls"] == 960

    def test_build_schedule_2023_has_30_slices(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds23 = self._make_dataset(tmp_path, "2023")
        sched = _build_schedule(str(tmp_path), years=["2023"],
                                 dataset_paths={"2023": ds23})
        assert sched["total_slices"] == 30
        assert sched["global_hard_cap"] == 530

    def test_each_slice_has_exactly_8_cases(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds24 = self._make_dataset(tmp_path, "2024")
        ds25 = self._make_dataset(tmp_path, "2025")
        sched = _build_schedule(str(tmp_path), years=["2024", "2025"],
                                 dataset_paths={"2024": ds24, "2025": ds25})
        for sl in sched["slices"]:
            assert len(sl["case_ids"]) == 8, f"{sl['slice_id']} has {len(sl['case_ids'])} cases"

    def test_schedule_covers_all_years_repeats_arms_groups(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds24 = self._make_dataset(tmp_path, "2024")
        ds25 = self._make_dataset(tmp_path, "2025")
        sched = _build_schedule(str(tmp_path), years=["2024", "2025"],
                                 dataset_paths={"2024": ds24, "2025": ds25})
        years = {sl["year"] for sl in sched["slices"]}
        reps = {sl["repeat"] for sl in sched["slices"]}
        arms = {sl["arm"] for sl in sched["slices"]}
        groups = {sl["group"] for sl in sched["slices"]}
        assert years == {"2024", "2025"}
        assert reps == {0, 1, 2}
        assert arms == {"b1a_prime", "dual"}
        assert groups == {0, 1, 2, 3, 4}

    def test_b1a_prime_slice_has_correct_caps(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds24 = self._make_dataset(tmp_path, "2024")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": ds24})
        b1a = next(sl for sl in sched["slices"] if sl["arm"] == "b1a_prime")
        assert b1a["scheduled_calls"] == 8
        assert b1a["hard_cap"] == 10
        assert b1a["max_cases"] == 8
        assert b1a["profile"] == "baziqa_xjz_reasoned"
        assert b1a["method"] == "direct_choice"

    def test_dual_slice_has_correct_caps(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds24 = self._make_dataset(tmp_path, "2024")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": ds24})
        dual = next(sl for sl in sched["slices"] if sl["arm"] == "dual")
        assert dual["scheduled_calls"] == 24
        assert dual["hard_cap"] == 26
        assert dual["max_cases"] == 8
        assert dual["profile"] == "baziqa_xjz_dual"
        assert dual["method"] == "dual_system"

    def test_build_schedule_rejects_missing_dataset(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        with pytest.raises(SystemExit):
            _build_schedule(str(tmp_path), years=["2024"],
                            dataset_paths={"2024": "/nonexistent"})

    def test_build_schedule_rejects_wrong_case_count(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds_bad = self._make_dataset(tmp_path, "2024", n=39)
        with pytest.raises(SystemExit):
            _build_schedule(str(tmp_path), years=["2024"],
                            dataset_paths={"2024": ds_bad})

    def test_build_schedule_rejects_duplicate_case_ids(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds_path = tmp_path / "dup.jsonl"
        with open(ds_path, "w", encoding="utf-8") as f:
            for i in range(40):
                f.write(json.dumps({"case_id": "dup_0000"}) + "\n")
        with pytest.raises(SystemExit):
            _build_schedule(str(tmp_path), years=["2024"],
                            dataset_paths={"2024": str(ds_path)})


class TestTask11BudgetLedger:
    """Task 11: parameterized BudgetLedger6B2 with per-arm range validation."""

    def test_ledger_init_and_persist(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        ledger_path = tmp_path / "ledger.json"
        l = BudgetLedger6B2(str(ledger_path), global_hard_cap=100)
        assert l.total_attempted == 0
        assert ledger_path.exists()

    def test_ledger_reloads_state(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        ledger_path = tmp_path / "ledger.json"
        l1 = BudgetLedger6B2(str(ledger_path), global_hard_cap=100)
        l1.record_slice_completed("s1", 8, arm="b1a_prime")
        l2 = BudgetLedger6B2(str(ledger_path), global_hard_cap=100)
        assert l2.total_attempted == 8
        assert l2.slice_completed("s1")

    def test_ledger_rejects_mismatched_hard_cap(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        ledger_path = tmp_path / "ledger.json"
        BudgetLedger6B2(str(ledger_path), global_hard_cap=100)
        with pytest.raises(SystemExit):
            BudgetLedger6B2(str(ledger_path), global_hard_cap=200)

    def test_ledger_b1a_in_range(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=100)
        l.record_slice_completed("s1", 8, arm="b1a_prime")
        l.record_slice_completed("s2", 10, arm="b1a_prime")
        assert l.total_attempted == 18

    def test_ledger_b1a_below_range_rejected(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=100)
        with pytest.raises(SystemExit):
            l.record_slice_completed("s1", 7, arm="b1a_prime")

    def test_ledger_b1a_above_range_rejected(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=100)
        with pytest.raises(SystemExit):
            l.record_slice_completed("s1", 11, arm="b1a_prime")

    def test_ledger_dual_in_range(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=100)
        l.record_slice_completed("s1", 16, arm="dual")
        l.record_slice_completed("s2", 26, arm="dual")
        assert l.total_attempted == 42

    def test_ledger_dual_below_range_rejected(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=100)
        with pytest.raises(SystemExit):
            l.record_slice_completed("s1", 15, arm="dual")

    def test_ledger_dual_above_range_rejected(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=100)
        with pytest.raises(SystemExit):
            l.record_slice_completed("s1", 27, arm="dual")

    def test_ledger_hard_cap_breach_rejected(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=9)
        with pytest.raises(SystemExit):
            l.record_slice_completed("s1", 10, arm="b1a_prime")

    def test_ledger_idempotent_record(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=100)
        l.record_slice_completed("s1", 8, arm="b1a_prime")
        l.record_slice_completed("s1", 8, arm="b1a_prime")
        assert l.total_attempted == 8

    def test_ledger_can_attempt(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
        l = BudgetLedger6B2(str(tmp_path / "l.json"), global_hard_cap=10)
        assert l.can_attempt(8)
        l.record_slice_completed("s1", 8, arm="b1a_prime")
        assert not l.can_attempt(5)


class TestTask11RunnerCmd:
    """Task 11: runner command building with --hard-cap."""

    def test_runner_cmd_includes_hard_cap(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_runner_cmd
        sl = {
            "slice_id": "2024_b1a_prime_0_g0",
            "output_dir": str(tmp_path / "s1"),
            "detail_path": str(tmp_path / "s1" / "details.jsonl"),
            "events_path": str(tmp_path / "s1" / "details.events.jsonl"),
            "dataset_path": str(tmp_path / "ds.jsonl"),
            "case_ids_file": str(tmp_path / "s1" / "case_ids.json"),
            "profile": "baziqa_xjz_reasoned",
            "method": "direct_choice",
            "hard_cap": 10, "max_cases": 8,
            "scheduled_calls": 8,
            "case_ids": ["c1", "c2"],
            "arm": "b1a_prime", "repeat": 0,
            "thinking_mode": "disabled",
        }
        cmd = _build_runner_cmd(sl, "deepseek", "deepseek-v4-flash")
        assert "--hard-cap" in cmd
        hc_idx = cmd.index("--hard-cap")
        assert cmd[hc_idx + 1] == "10"

    def test_runner_cmd_includes_thinking_mode(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_runner_cmd
        sl = {
            "slice_id": "2024_b1a_prime_0_g0",
            "output_dir": str(tmp_path / "s1"),
            "detail_path": str(tmp_path / "s1" / "details.jsonl"),
            "events_path": str(tmp_path / "s1" / "details.events.jsonl"),
            "dataset_path": str(tmp_path / "ds.jsonl"),
            "case_ids_file": str(tmp_path / "s1" / "case_ids.json"),
            "profile": "baziqa_xjz_reasoned",
            "method": "direct_choice",
            "hard_cap": 10, "max_cases": 8,
            "scheduled_calls": 8,
            "case_ids": ["c1", "c2"],
            "arm": "b1a_prime", "repeat": 0,
            "thinking_mode": "disabled",
        }
        cmd = _build_runner_cmd(sl, "deepseek", "deepseek-v4-flash")
        tm_idx = cmd.index("--thinking-mode")
        assert cmd[tm_idx + 1] == "disabled"

    def test_runner_cmd_b1a_uses_direct_choice(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_runner_cmd
        sl = {
            "slice_id": "2024_b1a_prime_0_g0",
            "output_dir": str(tmp_path / "s1"),
            "detail_path": str(tmp_path / "s1" / "details.jsonl"),
            "events_path": str(tmp_path / "s1" / "details.events.jsonl"),
            "dataset_path": str(tmp_path / "ds.jsonl"),
            "case_ids_file": str(tmp_path / "s1" / "case_ids.json"),
            "profile": "baziqa_xjz_reasoned",
            "method": "direct_choice",
            "hard_cap": 10, "max_cases": 8,
            "scheduled_calls": 8,
            "case_ids": ["c1"],
            "arm": "b1a_prime", "repeat": 0,
            "thinking_mode": "disabled",
        }
        cmd = _build_runner_cmd(sl, "deepseek", "deepseek-v4-flash")
        assert "--method" in cmd
        m_idx = cmd.index("--method")
        assert cmd[m_idx + 1] == "direct_choice"

    def test_runner_cmd_dual_uses_dual_system(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_runner_cmd
        sl = {
            "slice_id": "2024_dual_0_g0",
            "output_dir": str(tmp_path / "s1"),
            "detail_path": str(tmp_path / "s1" / "details.jsonl"),
            "events_path": str(tmp_path / "s1" / "details.events.jsonl"),
            "dataset_path": str(tmp_path / "ds.jsonl"),
            "case_ids_file": str(tmp_path / "s1" / "case_ids.json"),
            "profile": "baziqa_xjz_dual",
            "method": "dual_system",
            "hard_cap": 26, "max_cases": 8,
            "scheduled_calls": 24,
            "case_ids": ["c1"],
            "arm": "dual", "repeat": 0,
            "thinking_mode": "disabled",
        }
        cmd = _build_runner_cmd(sl, "deepseek", "deepseek-v4-flash")
        assert "--method" in cmd
        m_idx = cmd.index("--method")
        assert cmd[m_idx + 1] == "dual_system"

    def test_runner_cmd_max_cases_is_8(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_runner_cmd
        sl = {
            "slice_id": "2024_dual_0_g0",
            "output_dir": str(tmp_path / "s1"),
            "detail_path": str(tmp_path / "s1" / "details.jsonl"),
            "events_path": str(tmp_path / "s1" / "details.events.jsonl"),
            "dataset_path": str(tmp_path / "ds.jsonl"),
            "case_ids_file": str(tmp_path / "s1" / "case_ids.json"),
            "profile": "baziqa_xjz_dual",
            "method": "dual_system",
            "hard_cap": 26, "max_cases": 8,
            "scheduled_calls": 24,
            "case_ids": ["c1"],
            "arm": "dual", "repeat": 0,
            "thinking_mode": "disabled",
        }
        cmd = _build_runner_cmd(sl, "deepseek", "deepseek-v4-flash")
        assert "--max-cases" in cmd
        mc_idx = cmd.index("--max-cases")
        assert cmd[mc_idx + 1] == "8"

    def test_runner_cmd_writes_case_ids_file(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_runner_cmd
        case_dir = tmp_path / "s1"
        case_dir.mkdir()
        sl = {
            "slice_id": "2024_b1a_prime_0_g0",
            "output_dir": str(case_dir),
            "detail_path": str(case_dir / "details.jsonl"),
            "events_path": str(case_dir / "details.events.jsonl"),
            "dataset_path": str(tmp_path / "ds.jsonl"),
            "case_ids_file": str(case_dir / "case_ids.json"),
            "profile": "baziqa_xjz_reasoned",
            "method": "direct_choice",
            "hard_cap": 10, "max_cases": 8,
            "scheduled_calls": 8,
            "case_ids": ["c1", "c2"],
            "arm": "b1a_prime", "repeat": 0,
            "thinking_mode": "disabled",
        }
        _build_runner_cmd(sl, "deepseek", "deepseek-v4-flash")
        assert os.path.exists(sl["case_ids_file"])
        with open(sl["case_ids_file"]) as f:
            assert json.load(f) == ["c1", "c2"]


class TestTask11EventsFilename:
    """Task 11: events filename uses details.events.jsonl matching runner."""

    def test_events_path_uses_details_events_jsonl(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds_path = tmp_path / "ds.jsonl"
        with open(ds_path, "w", encoding="utf-8") as f:
            for i in range(40):
                f.write(json.dumps({"case_id": f"c{i:04d}"}) + "\n")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": str(ds_path)})
        for sl in sched["slices"]:
            assert sl["events_path"].endswith("details.events.jsonl")
            # Verify it's NOT just plain "events.jsonl" (the bug)
            assert os.path.basename(sl["events_path"]) == "details.events.jsonl"


class TestTask12IntegrityGate:
    """Task 12: multi-stage integrity gate with per-cell matrix validation."""

    def _make_row(self, year, rep, cid, arm, stage, correct=True, terminal="parsed",
                  predicted="A", expected="A"):
        ak = [f"baziqa_contest8_{year}_holdout_enriched", "baziqa_xjz_reasoned",
              arm, stage, "deepseek", "deepseek-chat", cid, str(rep), "0", "p0"]
        return {
            "attempt_key": ak, "case_id": cid,
            "predicted_answer": predicted if stage != "judge" or predicted != expected else None,
            "expected_answer": expected,
            "correct": (predicted == expected) if stage in ("main", "bazi", "ziwei", "judge") else True,
            "terminal_state": terminal,
        }

    def test_integrity_pass_for_complete_matrix(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule, _integrity_gate
        ds_path = tmp_path / "ds.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": str(ds_path)})
        rows = []
        for sl in sched["slices"]:
            for cid in sl["case_ids"]:
                if sl["arm"] == "b1a_prime":
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "b1a_prime",
                                               "main", predicted="A", expected="A"))
                else:
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "bazi"))
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "ziwei"))
        assert _integrity_gate(rows, sched) == "PASS"

    def test_integrity_rejects_missing_cell(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule, _integrity_gate
        ds_path = tmp_path / "ds.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": str(ds_path)})
        rows = []
        for sl in sched["slices"]:
            for cid in sl["case_ids"]:
                if sl["slice_id"] == "2024_b1a_prime_0_g0" and cid == sl["case_ids"][0]:
                    continue
                if sl["arm"] == "b1a_prime":
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "b1a_prime", "main"))
                else:
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "bazi"))
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "ziwei"))
        result = _integrity_gate(rows, sched)
        assert "MISSING_CELLS" in result

    def test_integrity_rejects_duplicate(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule, _integrity_gate
        ds_path = tmp_path / "ds.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": str(ds_path)})
        rows = []
        for sl in sched["slices"]:
            for cid in sl["case_ids"]:
                if sl["arm"] == "b1a_prime":
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "b1a_prime", "main"))
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "b1a_prime", "main"))
                else:
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "bazi"))
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "ziwei"))
        result = _integrity_gate(rows, sched)
        assert "DUPLICATE" in result

    def test_integrity_rejects_invalid_terminal_state(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule, _integrity_gate
        ds_path = tmp_path / "ds.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": str(ds_path)})
        rows = []
        for sl in sched["slices"]:
            for cid in sl["case_ids"]:
                if sl["arm"] == "b1a_prime":
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "b1a_prime", "main",
                                               terminal="unknown_state"))
                else:
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "bazi"))
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "ziwei"))
        result = _integrity_gate(rows, sched)
        assert "INVALID_STATE" in result

    def test_integrity_dual_consensus_no_judge(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule, _integrity_gate
        ds_path = tmp_path / "ds.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": str(ds_path)})
        rows = []
        for sl in sched["slices"]:
            for cid in sl["case_ids"]:
                if sl["arm"] == "b1a_prime":
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "b1a_prime", "main"))
                else:
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "bazi", predicted="A"))
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "ziwei", predicted="A"))
        assert _integrity_gate(rows, sched) == "PASS"

    def test_integrity_dual_consensus_with_judge_rejected(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule, _integrity_gate
        ds_path = tmp_path / "ds.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": str(ds_path)})
        rows = []
        for sl in sched["slices"]:
            for i, cid in enumerate(sl["case_ids"]):
                if sl["arm"] == "b1a_prime":
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "b1a_prime", "main"))
                else:
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "bazi", predicted="A"))
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "ziwei", predicted="A"))
                    if i == 0:
                        rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "judge"))
        result = _integrity_gate(rows, sched)
        assert "JUDGE_ON_CONSENSUS" in result

    def test_integrity_dual_disagreement_requires_judge(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule, _integrity_gate
        ds_path = tmp_path / "ds.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        sched = _build_schedule(str(tmp_path), years=["2024"], dataset_paths={"2024": str(ds_path)})
        rows = []
        for sl in sched["slices"]:
            for i, cid in enumerate(sl["case_ids"]):
                if sl["arm"] == "b1a_prime":
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "b1a_prime", "main"))
                else:
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "bazi", predicted="A"))
                    rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "ziwei", predicted="B"))
                    if i > 0:
                        rows.append(self._make_row(sl["year"], sl["repeat"], cid, "dual", "judge"))
        result = _integrity_gate(rows, sched)
        assert "MISSING_JUDGE" in result


class TestTask13ComputeGate:
    """Task 13: 3-stage compute_gate with real thresholds."""

    def _make_dev_rows(self, delta: float = 0.05, min_year: float = 0.0):
        """Generate minimal valid dev rows for gate testing."""
        rows = []
        for year in ["2024", "2025"]:
            for rep in [0, 1, 2]:
                for i in range(40):
                    cid = f"c{i:04d}"
                    b1a_correct = i < 13
                    # Use larger delta to ensure thresholds are met
                    year_delta = delta if year == "2025" else max(min_year, delta)
                    dual_correct = i < int(13 + 40 * year_delta)
                    ak_b1a = [f"baziqa_contest8_{year}_holdout_enriched", "baziqa_xjz_reasoned",
                              "b1a_prime", "main", "deepseek", "deepseek-chat", cid, str(rep), "0", "p0"]
                    rows.append({
                        "attempt_key": ak_b1a, "case_id": cid,
                        "predicted_answer": "A" if b1a_correct else "B",
                        "expected_answer": "A",
                        "correct": b1a_correct,
                        "terminal_state": "parsed",
                    })
                    ak_b = [f"baziqa_contest8_{year}_holdout_enriched", "baziqa_xjz_dual",
                            "dual", "bazi", "deepseek", "deepseek-chat", cid, str(rep), "0", "p0"]
                    ak_z = [f"baziqa_contest8_{year}_holdout_enriched", "baziqa_xjz_dual",
                            "dual", "ziwei", "deepseek", "deepseek-chat", cid, str(rep), "0", "p0"]
                    # Make bazi always correct when dual_correct, ziwei disagree when needed
                    b_pred = "A" if dual_correct else "B"
                    z_pred = "B"  # Always disagree to trigger judge
                    rows.append({
                        "attempt_key": ak_b, "case_id": cid,
                        "predicted_answer": b_pred,
                        "expected_answer": "A", "correct": dual_correct,
                        "terminal_state": "parsed",
                    })
                    rows.append({
                        "attempt_key": ak_z, "case_id": cid,
                        "predicted_answer": z_pred,
                        "expected_answer": "A", "correct": False,
                        "terminal_state": "parsed",
                    })
                    # Judge resolves correctly when dual_correct
                    ak_j = [f"baziqa_contest8_{year}_holdout_enriched", "baziqa_xjz_dual",
                            "dual", "judge", "deepseek", "deepseek-chat", cid, str(rep), "0", "p0"]
                    rows.append({
                        "attempt_key": ak_j, "case_id": cid,
                        "predicted_answer": "A" if dual_correct else "B",
                        "expected_answer": "A", "correct": dual_correct,
                        "terminal_state": "parsed",
                    })
        return rows

    def test_dev_gate_promote_candidate(self):
        from scripts.phase6_6b2_orchestrator import compute_gate
        rows = self._make_dev_rows(delta=0.05, min_year=0.01)
        gate = compute_gate(rows, stage="dev")
        assert gate["verdict"] == "PROMOTE_CANDIDATE"
        assert gate["delta_dev"] >= 0.04
        assert gate["dual_merged_acc"] >= 0.325
        assert gate["min_year_delta"] >= -0.02

    def test_dev_gate_rollback_low_delta(self):
        from scripts.phase6_6b2_orchestrator import compute_gate
        rows = self._make_dev_rows(delta=0.02)
        gate = compute_gate(rows, stage="dev")
        assert gate["verdict"] == "ROLLBACK"

    def test_reuse_gate_pass(self):
        from scripts.phase6_6b2_orchestrator import compute_gate
        rows = self._make_dev_rows(delta=0.03)
        for r in rows:
            ak = r["attempt_key"]
            for idx, yr in enumerate(["2021", "2022"]):
                if f"202{4+idx}" in ak[0]:
                    ak[0] = ak[0].replace(f"202{4+idx}", yr)
        gate = compute_gate(rows, stage="reuse")
        assert gate["verdict"] in ("PASS", "FAIL")

    def test_final_2023_gate_verdict_range(self):
        from scripts.phase6_6b2_orchestrator import compute_gate
        rows = self._make_dev_rows(delta=0.01)
        for r in rows:
            r["attempt_key"][0] = r["attempt_key"][0].replace("2024", "2023").replace("2025", "2023")
        gate = compute_gate(rows, stage="final_2023")
        assert gate["verdict"] in ("CONFIRMED_PROMOTE", "INCONCLUSIVE", "ROLLBACK")

    def test_gate_rejects_wrong_years(self):
        from scripts.phase6_6b2_orchestrator import compute_gate
        rows = self._make_dev_rows(delta=0.05)
        for r in rows:
            r["attempt_key"][0] = r["attempt_key"][0].replace("2025", "2023")
        with pytest.raises(SystemExit):
            compute_gate(rows, stage="dev")


class TestTask14SmokeGate:
    """Task 14: smoke gate state machine and verification."""

    def test_smoke_state_fresh_when_no_detail(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import determine_smoke_state
        state = determine_smoke_state(str(tmp_path))
        assert state == "fresh"

    def test_smoke_state_completed_when_all_stages_present(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import determine_smoke_state
        detail = tmp_path / "details.jsonl"
        rows = []
        for cid in ["c0001", "c0002"]:
            for stage in ["bazi", "ziwei"]:
                rows.append({"case_id": cid, "attempt_key": ["", "", "dual", stage],
                             "terminal_state": "parsed"})
        with open(detail, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        state = determine_smoke_state(str(tmp_path), expected_case_ids=["c0001", "c0002"])
        assert state == "completed"

    def test_smoke_state_resume_when_incomplete(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import determine_smoke_state
        detail = tmp_path / "details.jsonl"
        rows = [{"case_id": "c0001", "attempt_key": ["", "", "dual", "bazi"],
                 "terminal_state": "parsed"}]
        with open(detail, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        state = determine_smoke_state(str(tmp_path), expected_case_ids=["c0001", "c0002"])
        assert state == "resume"

    def test_smoke_state_blocked_corrupt(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import determine_smoke_state
        detail = tmp_path / "details.jsonl"
        detail.write_text("not json\n{bad", encoding="utf-8")
        state = determine_smoke_state(str(tmp_path))
        assert state == "blocked_corrupt"

    def test_verify_smoke_pass(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import verify_smoke_completed
        detail = tmp_path / "details.jsonl"
        rows = []
        for cid in ["c0001", "c0002"]:
            for stage in ["bazi", "ziwei"]:
                rows.append({"case_id": cid, "attempt_key": ["", "", "dual", stage],
                             "predicted_answer": "A", "expected_answer": "A",
                             "terminal_state": "parsed"})
        with open(detail, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        result = verify_smoke_completed(str(tmp_path), ["c0001", "c0002"])
        assert result["status"] == "OK"
        assert result["ziwei_coverage"] == 1.0
        assert result["parser_rate"] >= 0.95

    def test_verify_smoke_rejects_call_failed(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import verify_smoke_completed
        detail = tmp_path / "details.jsonl"
        rows = []
        for cid in ["c0001", "c0002"]:
            for stage in ["bazi", "ziwei"]:
                rows.append({"case_id": cid, "attempt_key": ["", "", "dual", stage],
                             "terminal_state": "call_failed"})
        with open(detail, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        with pytest.raises(SystemExit):
            verify_smoke_completed(str(tmp_path), ["c0001", "c0002"])


class TestTask16GenerateArchive:
    """Task 16: generate_archive with fail-closed validation."""

    def _make_complete_run(self, tmp_path, years=None):
        from scripts.phase6_6b2_orchestrator import (
            _build_schedule, BudgetLedger6B2, _load_events,
        )
        years = years or ["2024", "2025"]
        ds_paths = {}
        for year in years:
            ds_path = tmp_path / f"ds_{year}.jsonl"
            cids = [f"c{i:04d}" for i in range(40)]
            with open(ds_path, "w", encoding="utf-8") as f:
                for cid in cids:
                    f.write(json.dumps({"case_id": cid}) + "\n")
            ds_paths[year] = str(ds_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        sched = _build_schedule(str(run_dir), years=years, dataset_paths=ds_paths)
        cap = 530 if set(years) == {"2023"} else 1060
        ledger = BudgetLedger6B2(str(run_dir / "ledger.json"), global_hard_cap=cap)
        all_rows = []
        for sl in sched["slices"]:
            os.makedirs(sl["output_dir"], exist_ok=True)
            sl_rows = []
            for cid in sl["case_ids"]:
                if sl["arm"] == "b1a_prime":
                    ak = [f"baziqa_contest8_{sl['year']}_holdout_enriched", "baziqa_xjz_reasoned",
                          "b1a_prime", "main", "deepseek", "deepseek-chat", cid, str(sl["repeat"]), "0", "p0"]
                    sl_rows.append({
                        "attempt_key": ak, "case_id": cid,
                        "predicted_answer": "A", "expected_answer": "A",
                        "correct": True, "terminal_state": "parsed",
                    })
                else:
                    for stg_idx, stg in enumerate(["bazi", "ziwei"]):
                        ak = [f"baziqa_contest8_{sl['year']}_holdout_enriched", "baziqa_xjz_dual",
                              "dual", stg, "deepseek", "deepseek-chat", cid, str(sl["repeat"]), "0", "p0"]
                        sl_rows.append({
                            "attempt_key": ak, "case_id": cid,
                            "predicted_answer": "A" if stg_idx == 0 else "B",
                            "expected_answer": "A", "correct": stg_idx == 0,
                            "terminal_state": "parsed",
                        })
                    ak_j = [f"baziqa_contest8_{sl['year']}_holdout_enriched", "baziqa_xjz_dual",
                            "dual", "judge", "deepseek", "deepseek-chat", cid, str(sl["repeat"]), "0", "p0"]
                    sl_rows.append({
                        "attempt_key": ak_j, "case_id": cid,
                        "predicted_answer": "A", "expected_answer": "A",
                        "correct": True, "terminal_state": "parsed",
                    })
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for r in sl_rows:
                    f.write(json.dumps(r) + "\n")
            actual_calls = 8 if sl["arm"] == "b1a_prime" else 24
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                for _ in range(actual_calls):
                    f.write(json.dumps({"kind": "call_attempt"}) + "\n")
            (Path(sl["output_dir"]) / "details.manifest.json").write_text("{}", encoding="utf-8")
            (Path(sl["output_dir"]) / "slice_status.json").write_text(json.dumps({
                "slice_id": sl["slice_id"], "completed": True,
                "actual_attempts": actual_calls, "runner_manifest_sha256": "abc",
            }), encoding="utf-8")
            ledger.record_slice_completed(sl["slice_id"], actual_calls, arm=sl["arm"])
            all_rows.extend(sl_rows)
        return sched, ledger, str(run_dir), all_rows

    def test_archive_requires_complete_schedule(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule, BudgetLedger6B2, generate_archive
        ds_path = tmp_path / "ds.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        sched = _build_schedule(str(run_dir), years=["2024"], dataset_paths={"2024": str(ds_path)})
        ledger = BudgetLedger6B2(str(run_dir / "l.json"), global_hard_cap=530)
        with pytest.raises(SystemExit, match="未全部完成"):
            generate_archive(sched, ledger, str(run_dir), "deepseek", "deepseek-chat",
                             {"verdict": "PASS"})

    def test_archive_rejects_blocked_incomplete(self, tmp_path):
        sched, ledger, run_dir, _ = self._make_complete_run(tmp_path)
        from scripts.phase6_6b2_orchestrator import generate_archive
        with pytest.raises(SystemExit, match="BLOCKED_INCOMPLETE"):
            generate_archive(sched, ledger, run_dir, "deepseek", "deepseek-chat",
                             {"verdict": "BLOCKED_INCOMPLETE"})

    def test_archive_creates_audit_index(self, tmp_path):
        sched, ledger, run_dir, _ = self._make_complete_run(tmp_path)
        from scripts.phase6_6b2_orchestrator import (
            generate_archive, compute_gate, _merge_all_details,
        )
        merged = _merge_all_details(sched)
        gate = compute_gate(merged, stage="dev")
        arch_root = tmp_path / "archives"
        result = generate_archive(sched, ledger, run_dir, "deepseek", "deepseek-chat",
                                  gate, archive_root=str(arch_root), stage="dev")
        audit_path = Path(result["archive_dir"]) / "audit_index.json"
        assert audit_path.exists()
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        assert audit["gate_verdict"] in ("PROMOTE_CANDIDATE", "ROLLBACK")
        assert audit["experiment_id"] == "6b2"
        receipt_path = Path(result["archive_dir"]) / "dev_gate.json"
        assert receipt_path.exists()


class TestTask17bEntryPoints:
    """Task 17b: run_dev / run_reuse / run_2023_final entry points exist."""

    def test_run_dev_callable(self):
        from scripts.phase6_6b2_orchestrator import run_dev
        assert callable(run_dev)

    def test_run_reuse_callable(self):
        from scripts.phase6_6b2_orchestrator import run_reuse
        assert callable(run_reuse)

    def test_run_2023_final_callable(self):
        from scripts.phase6_6b2_orchestrator import run_2023_final
        assert callable(run_2023_final)


class TestTask15SealedWorkflow:
    """Task 15: sealed workflow module functions."""

    def test_sealed_workflow_functions_exist(self):
        from scripts.phase6_6b2_sealed_workflow import (
            check_stage_gate, acquire_2023_run_lock, enrich_year,
            verify_2023_raw_data, record_enriched_sha_to_lock,
            finalize_2023_run_lock, BLESSED_2023_RAW_SHA256,
        )
        assert callable(check_stage_gate)
        assert callable(acquire_2023_run_lock)
        assert callable(enrich_year)
        assert callable(verify_2023_raw_data)
        assert callable(record_enriched_sha_to_lock)
        assert callable(finalize_2023_run_lock)
        assert len(BLESSED_2023_RAW_SHA256) == 64

    def test_2023_lock_new_then_finalized(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import (
            acquire_2023_run_lock, finalize_2023_run_lock,
            record_enriched_sha_to_lock, BLESSED_2023_RAW_SHA256,
        )
        lock_path = tmp_path / "2023.lock"
        run_id = "run1"
        code_fp = "fp123"
        sched_hash = "hash456"
        # Create a fake enriched dataset
        enriched_path = tmp_path / "enriched.jsonl"
        enriched_path.write_text(json.dumps({"case_id": "test"}), encoding="utf-8")
        status = acquire_2023_run_lock(str(lock_path), run_id, code_fp, sched_hash,
                                       budget_hard_cap=530)
        assert status == "NEW"
        # Record enriched SHA (normally done by run_2023_final after enrich_year)
        record_enriched_sha_to_lock(str(lock_path), str(enriched_path))
        assert lock_path.exists()
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["status"] == "RUNNING"
        assert data["budget_hard_cap"] == 530
        assert data["raw_sha256"] == BLESSED_2023_RAW_SHA256
        # Create mock archive with audit_index.json matching lock state
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        audit_path = archive_dir / "audit_index.json"
        audit = {
            "run_id": run_id,
            "stage": "final_2023",
            "gate_verdict": "CONFIRMED_PROMOTE",
            "code_fingerprint": code_fp,
            "sched_hash": sched_hash,
            "dataset_hashes": {"raw": data["raw_sha256"], "enriched": data["enriched_sha256"]},
            "budget_hard_cap": 530,
            "integrity_result": "PASS",
        }
        audit_path.write_text(json.dumps(audit), encoding="utf-8")
        finalize_2023_run_lock(str(lock_path), str(archive_dir), "CONFIRMED_PROMOTE",
                               schedule_complete=True, integrity_passed=True)
        data2 = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data2["status"] == "FINALIZED"
        assert data2["gate_verdict"] == "CONFIRMED_PROMOTE"

    def test_2023_lock_prevents_double_acquire(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
        lock_path = tmp_path / "2023.lock"
        acquire_2023_run_lock(str(lock_path), "run1", "fp123", "hash456")
        with pytest.raises(SystemExit):
            acquire_2023_run_lock(str(lock_path), "run2", "fp123", "hash456")

    def test_check_stage_gate_rejects_no_receipt(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(tmp_path))

    def _make_minimal_receipt(self, gate_dir, stage, verdict, user_run_id,
                              archive_run_id=None, provider="p", model="m",
                              code_fp="fp" * 8, dataset_sha="c" * 64):
        """Helper: place a minimal valid receipt + audit under gate_dir."""
        archive_dir = gate_dir.parent / f"archive_{stage}"
        archive_dir.mkdir(exist_ok=True)
        arid = archive_run_id or f"{user_run_id}-6b2-{stage}-x"
        audit = {
            "run_id": arid, "user_run_id": user_run_id,
            "stage": stage, "provider": provider, "model": model,
            "code_fingerprint": code_fp, "gate_verdict": verdict,
        }
        audit_path = archive_dir / "audit_index.json"
        audit_path.write_text(json.dumps(audit), encoding="utf-8")
        receipt = {
            "verdict": verdict, "stage": stage, "run_id": arid,
            "user_run_id": user_run_id, "archive_dir": str(archive_dir),
            "audit_index_sha256": m_sha256(str(audit_path)),
            "provider": provider, "model": model,
            "code_fingerprint": code_fp, "dataset_sha256": dataset_sha,
        }
        rpath = gate_dir / f"{stage}_gate.json"
        rpath.write_text(json.dumps(receipt), encoding="utf-8")
        return str(rpath)

    def test_reuse_gate_rejects_wrong_expected_user_run_id(self, tmp_path):
        """P0-1: check_stage_gate(reuse) must reject dev receipt whose
        user_run_id doesn't match expected_user_run_id."""
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate_dir = tmp_path / "gates"
        gate_dir.mkdir()
        self._make_minimal_receipt(gate_dir, "dev", "PROMOTE_CANDIDATE",
                                   user_run_id="run-A")
        with pytest.raises(SystemExit, match="user_run_id 不一致"):
            check_stage_gate("reuse", gate_root=str(gate_dir),
                             expected_user_run_id="run-B")

    def test_final_gate_rejects_mixed_user_run_id_chain(self, tmp_path):
        """P0-1: final_2023 must reject when dev.user_run_id != reuse.user_run_id,
        even when expected_user_run_id is not provided (defense in depth)."""
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate_dir = tmp_path / "gates"
        gate_dir.mkdir()
        # dev from run-A, reuse from run-B → MIXED chain must be rejected
        self._make_minimal_receipt(gate_dir, "dev", "PROMOTE_CANDIDATE",
                                   user_run_id="run-A")
        self._make_minimal_receipt(gate_dir, "reuse", "PASS",
                                   user_run_id="run-B")
        with pytest.raises(SystemExit, match="跨阶段 user_run_id 不一致"):
            # No expected_user_run_id — the cross-stage check itself must catch it
            check_stage_gate("final_2023", gate_root=str(gate_dir))

    def test_final_gate_expected_user_run_id_catches_mismatch(self, tmp_path):
        """P0-1: expected_user_run_id parameter rejects any receipt that doesn't match."""
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate_dir = tmp_path / "gates"
        gate_dir.mkdir()
        self._make_minimal_receipt(gate_dir, "dev", "PROMOTE_CANDIDATE",
                                   user_run_id="run-A")
        self._make_minimal_receipt(gate_dir, "reuse", "PASS",
                                   user_run_id="run-A")
        with pytest.raises(SystemExit, match="user_run_id 不一致"):
            check_stage_gate("final_2023", gate_root=str(gate_dir),
                             expected_user_run_id="run-C")

    def test_final_gate_accepts_consistent_chain(self, tmp_path):
        """P0-1: final_2023 accepts when all receipts share the same user_run_id."""
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        gate_dir = tmp_path / "gates"
        gate_dir.mkdir()
        self._make_minimal_receipt(gate_dir, "dev", "PROMOTE_CANDIDATE",
                                   user_run_id="run-A")
        self._make_minimal_receipt(gate_dir, "reuse", "PASS",
                                   user_run_id="run-A")
        result = check_stage_gate("final_2023", gate_root=str(gate_dir),
                                  expected_user_run_id="run-A")
        assert result["dev"]["user_run_id"] == "run-A"
        assert result["reuse"]["user_run_id"] == "run-A"


class TestOutputDirLock:
    """OutputDirLock exclusive locking."""

    def test_lock_acquire_and_release(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import OutputDirLock
        run_dir = tmp_path / "run"
        lock = OutputDirLock.acquire(str(run_dir))
        assert lock is not None
        assert os.path.exists(run_dir / ".orchestrator.lock")
        lock.release()
        assert not os.path.exists(run_dir / ".orchestrator.lock")

    def test_lock_exclusive(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import OutputDirLock
        run_dir = tmp_path / "run"
        lock1 = OutputDirLock.acquire(str(run_dir))
        assert lock1 is not None
        lock2 = OutputDirLock.acquire(str(run_dir))
        assert lock2 is None
        lock1.release()
        lock3 = OutputDirLock.acquire(str(run_dir))
        assert lock3 is not None
        lock3.release()


class TestManifestHomology:
    """Manifest homology check for resume."""

    def test_slice_runner_args_reconstructs_namespace(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _slice_runner_args
        sl = {
            "slice_id": "test", "arm": "dual", "repeat": 1,
            "dataset_path": str(tmp_path / "ds.jsonl"),
            "case_ids_file": str(tmp_path / "cids.json"),
            "profile": "baziqa_xjz_dual", "method": "dual_system",
            "scheduled_calls": 24, "hard_cap": 26,
            "thinking_mode": "disabled",
        }
        args = _slice_runner_args(sl, "deepseek", "deepseek-v4-flash")
        assert args.profile == "baziqa_xjz_dual"
        assert args.arm == "dual"
        assert args.repeat_idx == 1
        assert args.hard_cap == 26
        assert args.as_of_date == "2026-07-17"
        assert args.chart_schema_version == "legacy_v0"
        assert args.thinking_mode == "disabled"

    def test_runner_cmd_and_slice_args_build_identical_manifest(self, tmp_path):
        """同源契约：真实 argv 解析出的 namespace 与 _slice_runner_args 重建的 namespace
        必须产生完全一致的 resume manifest（thinking_mode 只从 slice 字段单源读取）。"""
        from scripts.phase6_6b2_orchestrator import (
            FROZEN_CHART_SCHEMA, _build_runner_cmd, _slice_runner_args,
        )
        from benchmark.runners.run_benchmark import _build_parser, build_resume_manifest
        from benchmark.runners.profiles import resolve_profile
        ds_path = tmp_path / "ds.jsonl"
        ds_path.write_text(json.dumps({"case_id": "c1"}) + "\n", encoding="utf-8")
        sl = {
            "slice_id": "2024_b1a_prime_0_g0",
            "output_dir": str(tmp_path / "s1"),
            "detail_path": str(tmp_path / "s1" / "details.jsonl"),
            "events_path": str(tmp_path / "s1" / "details.events.jsonl"),
            "dataset_path": str(ds_path),
            "case_ids_file": str(tmp_path / "s1" / "case_ids.json"),
            "profile": "baziqa_xjz_reasoned",
            "method": "direct_choice",
            "hard_cap": 10, "max_cases": 8,
            "scheduled_calls": 8,
            "case_ids": ["c1"],
            "arm": "b1a_prime", "repeat": 0,
            "thinking_mode": "disabled",
        }
        cmd = _build_runner_cmd(sl, "deepseek", "deepseek-v4-flash")
        argv_namespace = _build_parser().parse_args(cmd[3:])  # 跳过 [python, -m, module]
        profile = resolve_profile(sl["profile"], FROZEN_CHART_SCHEMA)
        reconstructed = _slice_runner_args(sl, "deepseek", "deepseek-v4-flash")
        assert build_resume_manifest(argv_namespace, profile) == \
            build_resume_manifest(reconstructed, profile)


class TestSliceStatusResponseModel:
    """Task 4: slice_status.json 从 events 的 call_meta 聚合 response_model
    （唯一值写入；全缺失写 null；多值 fail-closed），并记录协议字段。"""

    def _make_slice(self, tmp_path):
        out = tmp_path / "s1"
        return {
            "slice_id": "2024_b1a_prime_0_g0",
            "output_dir": str(out),
            "detail_path": str(out / "details.jsonl"),
            "events_path": str(out / "details.events.jsonl"),
            "dataset_path": str(tmp_path / "ds.jsonl"),
            "case_ids_file": str(out / "case_ids.json"),
            "profile": "baziqa_xjz_reasoned",
            "method": "direct_choice",
            "hard_cap": 10, "max_cases": 8,
            "scheduled_calls": 8,
            "case_ids": ["c1"],
            "arm": "b1a_prime", "repeat": 0,
            "thinking_mode": "disabled",
        }

    def _run_with_meta(self, tmp_path, monkeypatch, metas):
        import types as _types
        import scripts.phase6_6b2_orchestrator as m
        sl = self._make_slice(tmp_path)
        ledger = m.BudgetLedger6B2(str(tmp_path / "ledger.json"),
                                   global_hard_cap=1060)

        def fake_run(cmd, capture_output=False, text=False, timeout=None, cwd=None):
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                f.write(json.dumps({"case_id": "c1"}) + "\n")
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                for _ in range(8):
                    f.write(json.dumps({"kind": "call_attempt"}) + "\n")
                for meta in metas:
                    f.write(json.dumps({"kind": "call_meta",
                                        "response_model": meta}) + "\n")
            Path(sl["detail_path"].replace(".jsonl", ".manifest.json")).write_text(
                "{}", encoding="utf-8")
            return _types.SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr(m.subprocess, "run", fake_run)
        monkeypatch.setattr(m, "_slice_integrity_gate", lambda rows, info: "PASS")
        m._run_slice(sl, ledger, "deepseek", "deepseek-v4-flash")
        return json.loads(
            (Path(sl["output_dir"]) / "slice_status.json").read_text(encoding="utf-8"))

    def test_unique_response_model_recorded(self, tmp_path, monkeypatch):
        status = self._run_with_meta(tmp_path, monkeypatch,
                                     ["deepseek-v4-flash"] * 8)
        assert status["response_model"] == "deepseek-v4-flash"
        assert status["provider"] == "deepseek"
        assert status["requested_model"] == "deepseek-v4-flash"
        assert status["thinking_mode"] == "disabled"

    def test_all_missing_response_model_writes_null(self, tmp_path, monkeypatch):
        status = self._run_with_meta(tmp_path, monkeypatch, [None] * 8)
        assert status["response_model"] is None

    def test_multiple_response_models_fail_closed(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit, match="response_model drift"):
            self._run_with_meta(tmp_path, monkeypatch,
                                ["deepseek-v4-flash"] * 7 + ["deepseek-v4-pro"])


class TestB1CAdvisory:
    """B1-c advisory loading with SHA check."""

    def test_b1c_advisory_rejects_missing_file(self):
        from scripts.phase6_6b2_orchestrator import load_b1c_advisory, B1C_ARCHIVE_PATH
        orig = B1C_ARCHIVE_PATH
        try:
            import scripts.phase6_6b2_orchestrator as m
            m.B1C_ARCHIVE_PATH = "/nonexistent/path.jsonl"
            with pytest.raises(SystemExit, match="fail-closed"):
                load_b1c_advisory()
        finally:
            import scripts.phase6_6b2_orchestrator as m
            m.B1C_ARCHIVE_PATH = orig


class TestConstantsFrozen:
    """Verify v18 frozen constants."""

    def test_frozen_date(self):
        from scripts.phase6_6b2_orchestrator import FROZEN_DATE
        assert FROZEN_DATE == "2026-07-17"

    def test_hard_caps(self):
        from scripts.phase6_6b2_orchestrator import (
            DEV_REUSE_HARD_CAP, FINAL_2023_HARD_CAP,
            B1A_SLICE_HARD_CAP, DUAL_SLICE_HARD_CAP,
        )
        assert DEV_REUSE_HARD_CAP == 1060
        assert FINAL_2023_HARD_CAP == 530
        assert B1A_SLICE_HARD_CAP == 10
        assert DUAL_SLICE_HARD_CAP == 26


# ── New tests for P0 fixes ──

class TestSmokeSliceConstruction:
    """Task 14 smoke gate: _build_smoke_slices produces correct slices."""

    def _make_dev_schedule(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds_paths = {}
        for year in ["2024", "2025"]:
            ds_path = tmp_path / f"ds_{year}.jsonl"
            cids = [f"c{i:04d}" for i in range(40)]
            with open(ds_path, "w", encoding="utf-8") as f:
                for cid in cids:
                    f.write(json.dumps({"case_id": cid}) + "\n")
            ds_paths[year] = str(ds_path)
        return _build_schedule(str(tmp_path / "run"), years=["2024", "2025"],
                               dataset_paths=ds_paths)

    def test_smoke_slices_count(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_smoke_slices
        sched = self._make_dev_schedule(tmp_path)
        smoke = _build_smoke_slices(sched)
        # v18: SINGLE dual smoke slice (first year, dual arm, repeat 0 group 0)
        assert len(smoke) == 1
        assert smoke[0]["arm"] == "dual"

    def test_smoke_slices_have_2_cases_each(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_smoke_slices
        sched = self._make_dev_schedule(tmp_path)
        smoke = _build_smoke_slices(sched)
        for sl in smoke:
            assert len(sl["case_ids"]) == 2
            assert sl["max_cases"] == 2
            assert sl["scheduled_calls"] == 6
            assert sl["hard_cap"] == 10

    def test_smoke_uses_details_jsonl(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_smoke_slices
        sched = self._make_dev_schedule(tmp_path)
        smoke = _build_smoke_slices(sched)
        for sl in smoke:
            assert sl["detail_path"].endswith("details.jsonl")
            assert sl["events_path"].endswith("details.events.jsonl")

    def test_smoke_slices_use_repeat_0_group_0(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_smoke_slices
        sched = self._make_dev_schedule(tmp_path)
        smoke = _build_smoke_slices(sched)
        for sl in smoke:
            assert sl["repeat"] == 0
            assert sl["group"] == 0
            assert sl["arm"] == "dual"
            assert sl["year"] == "2024"  # first year in dev schedule

    def test_schedule_and_smoke_slices_carry_thinking_mode(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import (
            FROZEN_THINKING_MODE, _build_smoke_slices,
        )
        sched = self._make_dev_schedule(tmp_path)
        assert all(sl["thinking_mode"] == FROZEN_THINKING_MODE
                   for sl in sched["slices"])
        smoke = _build_smoke_slices(sched)
        assert all(sl["thinking_mode"] == FROZEN_THINKING_MODE for sl in smoke)


class TestVerifyCompletedSlice:
    """P0-5: _verify_completed_slice validates manifest/events/integrity."""

    def _make_slice(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        ds_path = tmp_path / "ds_2024.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        sched = _build_schedule(str(tmp_path / "run"), years=["2024"],
                                dataset_paths={"2024": str(ds_path)})
        return sched["slices"][0]

    def test_verify_rejects_missing_status(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _verify_completed_slice
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        with pytest.raises(SystemExit, match="slice_status.json 缺失"):
            _verify_completed_slice(sl, "deepseek", "deepseek-chat")

    def test_verify_rejects_not_completed(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _verify_completed_slice
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        status_path = Path(sl["output_dir"]) / "slice_status.json"
        status_path.write_text(json.dumps({"completed": False}), encoding="utf-8")
        with pytest.raises(SystemExit, match="completed != true"):
            _verify_completed_slice(sl, "deepseek", "deepseek-chat")

    def test_verify_rejects_mismatched_slice_id(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _verify_completed_slice
        sl = self._make_slice(tmp_path)
        os.makedirs(sl["output_dir"], exist_ok=True)
        status_path = Path(sl["output_dir"]) / "slice_status.json"
        status_path.write_text(json.dumps({"completed": True, "slice_id": "wrong"}),
                               encoding="utf-8")
        with pytest.raises(SystemExit, match="slice_id 不匹配"):
            _verify_completed_slice(sl, "deepseek", "deepseek-chat")


class TestArchiveMergedFiles:
    """P0-6: Archive produces merged_details.jsonl and merged_events.jsonl."""

    def _make_complete_run(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import (
            _build_schedule, BudgetLedger6B2,
        )
        years = ["2024", "2025"]
        ds_paths = {}
        for year in years:
            ds_path = tmp_path / f"ds_{year}.jsonl"
            cids = [f"c{i:04d}" for i in range(40)]
            with open(ds_path, "w", encoding="utf-8") as f:
                for cid in cids:
                    f.write(json.dumps({"case_id": cid}) + "\n")
            ds_paths[year] = str(ds_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        sched = _build_schedule(str(run_dir), years=years, dataset_paths=ds_paths)
        cap = 1060
        ledger = BudgetLedger6B2(str(run_dir / "ledger.json"), global_hard_cap=cap)
        for sl in sched["slices"]:
            os.makedirs(sl["output_dir"], exist_ok=True)
            sl_rows = []
            for cid in sl["case_ids"]:
                if sl["arm"] == "b1a_prime":
                    ak = [f"baziqa_contest8_{sl['year']}_holdout_enriched", "baziqa_xjz_reasoned",
                          "b1a_prime", "main", "deepseek", "deepseek-chat", cid, str(sl["repeat"]), "0", "p0"]
                    sl_rows.append({
                        "attempt_key": ak, "case_id": cid,
                        "predicted_answer": "A", "expected_answer": "A",
                        "correct": True, "terminal_state": "parsed",
                    })
                else:
                    for stg_idx, stg in enumerate(["bazi", "ziwei"]):
                        ak = [f"baziqa_contest8_{sl['year']}_holdout_enriched", "baziqa_xjz_dual",
                              "dual", stg, "deepseek", "deepseek-chat", cid, str(sl["repeat"]), "0", "p0"]
                        sl_rows.append({
                            "attempt_key": ak, "case_id": cid,
                            "predicted_answer": "A", "expected_answer": "A",
                            "correct": True, "terminal_state": "parsed",
                        })
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                for r in sl_rows:
                    f.write(json.dumps(r) + "\n")
            actual_calls = 8 if sl["arm"] == "b1a_prime" else 16
            with open(sl["events_path"], "w", encoding="utf-8") as f:
                for _ in range(actual_calls):
                    f.write(json.dumps({"kind": "call_attempt"}) + "\n")
            (Path(sl["output_dir"]) / "details.manifest.json").write_text("{}", encoding="utf-8")
            (Path(sl["output_dir"]) / "slice_status.json").write_text(json.dumps({
                "slice_id": sl["slice_id"], "completed": True,
                "actual_attempts": actual_calls, "runner_manifest_sha256": "abc",
            }), encoding="utf-8")
            ledger.record_slice_completed(sl["slice_id"], actual_calls, arm=sl["arm"])
        return sched, ledger, str(run_dir), ds_paths

    def test_archive_produces_merged_files(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import (
            generate_archive, compute_gate, _merge_all_details,
        )
        sched, ledger, run_dir, ds_paths = self._make_complete_run(tmp_path)
        merged = _merge_all_details(sched)
        gate = compute_gate(merged, stage="dev")
        arch_root = tmp_path / "archives"
        result = generate_archive(sched, ledger, run_dir, "deepseek", "deepseek-chat",
                                  gate, archive_root=str(arch_root), stage="dev",
                                  raw_dataset_paths=ds_paths,
                                  enriched_dataset_paths=ds_paths)
        arch_dir = Path(result["archive_dir"])
        merged_d = arch_dir / "merged_details.jsonl"
        merged_e = arch_dir / "merged_events.jsonl"
        assert merged_d.exists()
        assert merged_e.exists()
        # Verify SHA-256 fields in audit
        audit = json.loads((arch_dir / "audit_index.json").read_text(encoding="utf-8"))
        assert "merged_details_sha256" in audit
        assert "merged_events_sha256" in audit
        assert len(audit["merged_details_sha256"]) == 64
        assert len(audit["merged_events_sha256"]) == 64
        assert audit["dataset_hashes"]["raw"] != "0" * 64
        assert audit["dataset_hashes"]["enriched"] != "0" * 64


class TestCLIDatasetPathParsing:
    """P0-3: CLI --dataset-path parsing works correctly."""

    def test_parse_empty(self):
        from scripts.phase6_6b2_orchestrator import _parse_dataset_path_args
        assert _parse_dataset_path_args([]) == {}

    def test_parse_single(self):
        from scripts.phase6_6b2_orchestrator import _parse_dataset_path_args
        result = _parse_dataset_path_args(["2024=/path/to/ds.jsonl"])
        assert result == {"2024": "/path/to/ds.jsonl"}

    def test_parse_multiple(self):
        from scripts.phase6_6b2_orchestrator import _parse_dataset_path_args
        result = _parse_dataset_path_args([
            "2024=/a.jsonl", "2025=/b.jsonl"
        ])
        assert result == {"2024": "/a.jsonl", "2025": "/b.jsonl"}

    def test_parse_rejects_no_equals(self):
        from scripts.phase6_6b2_orchestrator import _parse_dataset_path_args
        with pytest.raises(SystemExit, match="格式错误"):
            _parse_dataset_path_args(["invalid"])


class TestSealedWorkflowScheduleHash:
    """P0-1: update_lock_schedule_hash writes back to lock; finalize verifies it."""

    def test_update_lock_schedule_hash(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import (
            acquire_2023_run_lock, update_lock_schedule_hash,
        )
        lock_path = tmp_path / "2023.lock"
        acquire_2023_run_lock(str(lock_path), "run1", "fp1", "pending",
                              budget_hard_cap=530)
        update_lock_schedule_hash(str(lock_path), "real_hash_abc")
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["schedule_hash"] == "real_hash_abc"
        assert data["status"] == "RUNNING"

    def test_update_lock_rejects_mismatch(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import (
            acquire_2023_run_lock, update_lock_schedule_hash,
        )
        lock_path = tmp_path / "2023.lock"
        acquire_2023_run_lock(str(lock_path), "run1", "fp1", "pending",
                              budget_hard_cap=530)
        update_lock_schedule_hash(str(lock_path), "hash1")
        with pytest.raises(SystemExit, match="schedule_hash 不一致"):
            update_lock_schedule_hash(str(lock_path), "hash2")

    def test_finalize_rejects_pending_sched_hash(self, tmp_path):
        """finalize must fail if schedule_hash is still 'pending'."""
        from scripts.phase6_6b2_sealed_workflow import (
            acquire_2023_run_lock, finalize_2023_run_lock,
            record_enriched_sha_to_lock,
        )
        lock_path = tmp_path / "2023.lock"
        run_id = "run1"
        code_fp = "fp1"
        sched_hash = "pending"
        # Create fake enriched file
        enriched = tmp_path / "enriched.jsonl"
        enriched.write_text("{}", encoding="utf-8")
        # Create archive with pending sched_hash in audit
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        lock_status = acquire_2023_run_lock(str(lock_path), run_id, code_fp, sched_hash,
                                            budget_hard_cap=530)
        record_enriched_sha_to_lock(str(lock_path), str(enriched))
        # Write audit with wrong sched_hash (pending)
        lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
        audit = {
            "run_id": run_id, "stage": "final_2023",
            "gate_verdict": "CONFIRMED_PROMOTE",
            "code_fingerprint": code_fp,
            "sched_hash": "real_hash",  # different from lock's "pending"
            "dataset_hashes": {"raw": lock_data["raw_sha256"],
                              "enriched": lock_data["enriched_sha256"]},
            "budget_hard_cap": 530, "integrity_result": "PASS",
        }
        (archive_dir / "audit_index.json").write_text(
            json.dumps(audit, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(SystemExit, match="sched_hash 与锁不一致"):
            finalize_2023_run_lock(str(lock_path), str(archive_dir),
                                   "CONFIRMED_PROMOTE", True, True)


class TestRunDirIsolation:
    """P0-3/P0-6: runs/<run_id>/<stage> subdirectory isolation with user run_id."""

    def test_run_dev_uses_runs_runid_subdir(self, tmp_path, monkeypatch):
        """run_dev places schedule under runs/<run_id>/dev/ with explicit --run-id."""
        import scripts.phase6_6b2_orchestrator as m
        captured = {}
        original_run_all = m._run_all_slices
        original_integrity = m._integrity_gate
        original_merge = m._merge_all_details
        original_compute = m.compute_gate
        original_b1c = m.load_b1c_advisory
        original_report = m.generate_report
        original_archive = m.generate_archive
        def fake_run_all(schedule, ledger, provider, model, smoke_slices=None):
            captured["sched_output_dir"] = schedule["slices"][0]["output_dir"]
            captured["smoke_count"] = len(smoke_slices) if smoke_slices else 0
            for sl in schedule["slices"]:
                if not ledger.slice_completed(sl["slice_id"]):
                    ledger.record_slice_completed(sl["slice_id"],
                        8 if sl["arm"] == "b1a_prime" else 16, arm=sl["arm"])
            return captured["smoke_count"] * 3  # return smoke_attempted
        def fake_merge(sched):
            return []
        def fake_integrity(merged, sched):
            return "PASS"
        def fake_gate(merged, stage="dev"):
            return {"verdict": "PROMOTE_CANDIDATE", "delta_dev": 0.05,
                    "dual_merged_acc": 0.4, "min_year_delta": 0.01,
                    "delta_by_year": {}, "delta_by_year_repeat": {}, "stage": stage}
        def fake_b1c():
            return {"count": 0, "sha256": "x", "rows": []}
        def fake_report(gate, merged, sched, ledger, b1c, out_dir, run_id=None):
            captured["report_dir"] = out_dir
            captured["report_run_id"] = run_id
        def fake_archive(sched, ledger, run_dir, provider, model, gate_result,
                         archive_root=None, stage="dev", raw_dataset_paths=None,
                         enriched_dataset_paths=None, run_id=None, smoke_attempted=0):
            arch_dir = tmp_path / "fake_archive"
            arch_dir.mkdir(exist_ok=True)
            receipt_name = f"{stage}_gate.json"
            (arch_dir / receipt_name).write_text(json.dumps({
                "verdict": gate_result["verdict"], "stage": stage,
                "run_id": run_id or "fake", "archive_dir": str(arch_dir),
                "audit_index_sha256": "a" * 64, "provider": provider,
                "model": model, "code_fingerprint": "fp",
                "dataset_sha256": "b" * 64, "sched_hash": "c" * 64,
                "smoke_attempted": smoke_attempted,
            }), encoding="utf-8")
            (arch_dir / "audit_index.json").write_text(
                json.dumps({"smoke_attempted": smoke_attempted}), encoding="utf-8")
            return {"archive_dir": str(arch_dir), "run_id": run_id or "fake", "receipt": {}}
        monkeypatch.setattr(m, "_run_all_slices", fake_run_all)
        monkeypatch.setattr(m, "_merge_all_details", fake_merge)
        monkeypatch.setattr(m, "_integrity_gate", fake_integrity)
        monkeypatch.setattr(m, "compute_gate", fake_gate)
        monkeypatch.setattr(m, "load_b1c_advisory", fake_b1c)
        monkeypatch.setattr(m, "generate_report", fake_report)
        monkeypatch.setattr(m, "generate_archive", fake_archive)
        ds_paths = {}
        for year in ["2024", "2025"]:
            ds_path = tmp_path / f"ds_{year}.jsonl"
            cids = [f"c{i:04d}" for i in range(40)]
            with open(ds_path, "w", encoding="utf-8") as f:
                for cid in cids:
                    f.write(json.dumps({"case_id": cid}) + "\n")
            ds_paths[year] = str(ds_path)
        out = tmp_path / "experiment"
        result = m.run_dev("deepseek", "deepseek-v4-flash", str(out),
                           dataset_paths=ds_paths, run_id="testrun1")
        assert result["run_id"] == "testrun1"
        assert "runs" + os.sep + "testrun1" + os.sep + "dev" in captured["sched_output_dir"]
        assert captured["smoke_count"] == 1  # single dual smoke per v18
        assert captured["report_run_id"] == "testrun1"  # report receives user run id
        assert (out / "runs" / "testrun1" / "gates" / "dev_gate.json").exists()


class TestReceiptChain:
    """P0-2: dev→reuse→final receipt chain closes, receipts bound to same run_id."""

    def _place_receipt(self, output_dir, run_id, stage, verdict="PROMOTE_CANDIDATE",
                       custom_rid=None):
        """Place a valid receipt under output_dir/runs/<run_id>/gates/<stage>_gate.json."""
        from scripts.phase6_6b2_orchestrator import _gate_root
        gate_dir = _gate_root(output_dir, run_id)
        gate_dir.mkdir(parents=True, exist_ok=True)
        archive_dir = gate_dir.parent / f"archive_{stage}"
        archive_dir.mkdir(exist_ok=True)
        archive_rid = custom_rid or f"{run_id}-6b2-{stage}-20260801-p-m-fp1234567890ab"
        audit = {
            "run_id": archive_rid,
            "user_run_id": run_id,
            "stage": stage, "provider": "deepseek", "model": "deepseek-v4-flash",
            "code_fingerprint": "fp" * 8, "gate_verdict": verdict,
        }
        audit_path = archive_dir / "audit_index.json"
        audit_path.write_text(json.dumps(audit), encoding="utf-8")
        receipt = {
            "verdict": verdict, "stage": stage, "run_id": archive_rid,
            "user_run_id": run_id,
            "archive_dir": str(archive_dir),
            "audit_index_sha256": m_sha256(str(audit_path)),
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "code_fingerprint": "fp" * 8, "dataset_sha256": "c" * 64,
        }
        rpath = gate_dir / f"{stage}_gate.json"
        rpath.write_text(json.dumps(receipt), encoding="utf-8")
        return str(rpath)

    def test_reuse_rejects_missing_dev_receipt(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        with pytest.raises(SystemExit):
            check_stage_gate("reuse", gate_root=str(tmp_path / "nope"))

    def test_final_requires_both_dev_and_reuse(self, tmp_path):
        from scripts.phase6_6b2_sealed_workflow import check_stage_gate
        out = tmp_path / "exp"
        out.mkdir()
        self._place_receipt(out, "r1", "dev")
        gate_dir = out / "runs" / "r1" / "gates"
        with pytest.raises(SystemExit, match="reuse receipt 缺失"):
            check_stage_gate("final_2023", gate_root=str(gate_dir))

    def test_verify_receipt_rejects_outside_gates(self, tmp_path):
        """P0-B: receipt must be EXACTLY at gates/<stage>_gate.json (not under gates subdir)."""
        from scripts.phase6_6b2_orchestrator import _verify_receipt_belongs_to_run
        out = tmp_path / "exp"
        out.mkdir()
        # Place a valid-looking receipt in a NESTED directory under gates/
        gate_dir = out / "runs" / "r1" / "gates"
        nested = gate_dir / "nested"
        nested.mkdir(parents=True)
        bad_receipt = nested / "dev_gate.json"
        bad_receipt.write_text(json.dumps({
            "verdict": "PROMOTE_CANDIDATE", "stage": "dev",
            "run_id": "r1-6b2-dev-x", "user_run_id": "r1",
        }), encoding="utf-8")
        with pytest.raises(SystemExit, match="路径拒绝"):
            _verify_receipt_belongs_to_run(str(bad_receipt), str(out), "r1", "dev")

    def test_verify_receipt_rejects_wrong_run_id(self, tmp_path):
        """P0-2/P1: receipt's embedded user_run_id must match the current run_id."""
        from scripts.phase6_6b2_orchestrator import _verify_receipt_belongs_to_run
        out = tmp_path / "exp"
        out.mkdir()
        # Place receipt in correct location but with wrong user_run_id
        self._place_receipt(out, "r1", "dev", custom_rid="r2-6b2-dev-20260801-p-m-fp000000000000")
        # Overwrite with wrong user_run_id in receipt itself
        rpath = out / "runs" / "r1" / "gates" / "dev_gate.json"
        data = json.loads(rpath.read_text(encoding="utf-8"))
        data["user_run_id"] = "r2"
        rpath.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(SystemExit, match="run_id 不一致"):
            _verify_receipt_belongs_to_run(str(rpath), str(out), "r1", "dev")

    def test_verify_receipt_rejects_wrong_filename(self, tmp_path):
        """File with wrong name under gates/ is rejected by exact path match."""
        from scripts.phase6_6b2_orchestrator import _verify_receipt_belongs_to_run
        out = tmp_path / "exp"
        out.mkdir()
        gate_dir = out / "runs" / "r1" / "gates"
        gate_dir.mkdir(parents=True)
        wrong = gate_dir / "reuse_gate.json"  # wrong stage for dev check
        wrong.write_text(json.dumps({
            "verdict": "PROMOTE_CANDIDATE", "stage": "reuse",
            "run_id": "r1-6b2-reuse-x", "user_run_id": "r1",
        }), encoding="utf-8")
        with pytest.raises(SystemExit, match="路径拒绝"):
            _verify_receipt_belongs_to_run(str(wrong), str(out), "r1", "dev")

    def test_verify_receipt_accepts_valid(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _verify_receipt_belongs_to_run
        out = tmp_path / "exp"
        out.mkdir()
        rpath = self._place_receipt(out, "chain1", "dev")
        receipt = _verify_receipt_belongs_to_run(rpath, str(out), "chain1", "dev")
        assert receipt["stage"] == "dev"
        assert receipt["verdict"] == "PROMOTE_CANDIDATE"


class TestScheduleHashCoversSlices:
    """P0-2: _compute_schedule_hash covers full slice matrix, not just summary fields."""

    def _make_schedule(self, tmp_path, case_ids=None):
        from scripts.phase6_6b2_orchestrator import _build_schedule
        tmp_path = Path(str(tmp_path))
        tmp_path.mkdir(parents=True, exist_ok=True)
        ds_path = tmp_path / "ds.jsonl"
        cids = case_ids or [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        run_dir = tmp_path / "run"
        run_dir.mkdir(exist_ok=True)
        return _build_schedule(str(run_dir), years=["2024"],
                               dataset_paths={"2024": str(ds_path)})

    def test_hash_differs_when_case_order_reversed(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _compute_schedule_hash
        cids_normal = [f"c{i:04d}" for i in range(40)]
        cids_reversed = list(reversed(cids_normal))
        s1 = self._make_schedule(tmp_path / "a", case_ids=cids_normal)
        s2 = self._make_schedule(tmp_path / "b", case_ids=cids_reversed)
        h1 = _compute_schedule_hash(s1)
        h2 = _compute_schedule_hash(s2)
        assert h1 != h2, "Reversing case order MUST produce different schedule hash"

    def test_same_schedule_same_hash(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _compute_schedule_hash
        s1 = self._make_schedule(tmp_path / "a")
        s2 = self._make_schedule(tmp_path / "b")
        # Same content, different output_dir (runtime paths differ)
        h1 = _compute_schedule_hash(s1)
        h2 = _compute_schedule_hash(s2)
        assert h1 == h2, "Identical scheduling must produce identical hash"

    def test_hash_is_stable_sha256_hex(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import _compute_schedule_hash
        s = self._make_schedule(tmp_path)
        h = _compute_schedule_hash(s)
        assert len(h) == 64
        int(h, 16)  # valid hex

    def test_hash_covers_thinking_mode(self, tmp_path):
        from scripts.phase6_6b2_orchestrator import (
            _SCHED_HASH_SLICE_KEYS, _compute_schedule_hash,
        )
        assert "thinking_mode" in _SCHED_HASH_SLICE_KEYS
        s = self._make_schedule(tmp_path)
        h1 = _compute_schedule_hash(s)
        s["slices"][0]["thinking_mode"] = "enabled"
        assert _compute_schedule_hash(s) != h1


class TestAtomicArchive:
    """P0-4: generate_archive uses temp dir + self-verify + atomic os.replace."""

    def _make_ready_schedule(self, tmp_path, monkeypatch):
        """Create a fully-completed schedule/ledger and monkeypatch integrity/gate to pass."""
        import scripts.phase6_6b2_orchestrator as m
        ds_path = tmp_path / "ds_2024.jsonl"
        cids = [f"c{i:04d}" for i in range(40)]
        with open(ds_path, "w", encoding="utf-8") as f:
            for cid in cids:
                f.write(json.dumps({"case_id": cid}) + "\n")
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        sched = m._build_schedule(str(run_dir), years=["2024"],
                                  dataset_paths={"2024": str(ds_path)})
        ledger = m.BudgetLedger6B2(str(run_dir / "ledger.json"),
                                    global_hard_cap=10000)
        for sl in sched["slices"]:
            out = Path(sl["output_dir"])
            out.mkdir(parents=True, exist_ok=True)
            # Write valid details for dual slices (bazi+ziwei stages)
            with open(sl["detail_path"], "w", encoding="utf-8") as df:
                for idx, cid in enumerate(sl["case_ids"]):
                    if sl["arm"] == "dual":
                        df.write(json.dumps({
                            "case_id": cid, "attempt_key": ["x","x","x","bazi",str(idx),"0"],
                            "terminal_state": "parsed", "predicted_answer": "A", "is_correct": True,
                        }) + "\n")
                        df.write(json.dumps({
                            "case_id": cid, "attempt_key": ["x","x","x","ziwei",str(idx),"0"],
                            "terminal_state": "parsed", "predicted_answer": "A", "is_correct": True,
                        }) + "\n")
                    else:
                        df.write(json.dumps({
                            "case_id": cid, "attempt_key": ["x","x","x","main",str(idx),"0"],
                            "terminal_state": "parsed", "predicted_answer": "A", "is_correct": True,
                        }) + "\n")
            with open(sl["events_path"], "w", encoding="utf-8") as ef:
                for _ in range(sl["scheduled_calls"]):
                    ef.write(json.dumps({"kind": "call_attempt"}) + "\n")
            namespace = {
                "dataset": sl["dataset_path"], "profile": sl["profile"],
                "method": sl["method"], "max_cases": sl["max_cases"],
                "scheduled_calls": sl["scheduled_calls"], "hard_cap": sl["hard_cap"],
                "model": "m", "provider": "p",
            }
            Path(str(sl["detail_path"]).replace(".jsonl", ".manifest.json")).write_text(
                json.dumps({"namespace": namespace, "slice_id": sl["slice_id"], "completed": True}),
                encoding="utf-8")
            (out / "slice_status.json").write_text(json.dumps({
                "completed": True, "slice_id": sl["slice_id"]}), encoding="utf-8")
            ledger.record_slice_completed(sl["slice_id"], sl["scheduled_calls"], arm=sl["arm"])
        # Monkeypatch integrity and code fingerprint
        monkeypatch.setattr(m, "_integrity_gate", lambda merged, sched: "PASS")
        monkeypatch.setattr(m, "_compute_experiment_code_fingerprint", lambda: "fp" * 8)
        monkeypatch.setattr(m, "_compute_dataset_hashes",
                            lambda raw_paths=None, enriched_paths=None: {"raw": "d"*64})
        return sched, ledger, run_dir

    def test_successful_archive_no_temp_leftover(self, tmp_path, monkeypatch):
        from scripts.phase6_6b2_orchestrator import generate_archive
        sched, ledger, run_dir = self._make_ready_schedule(tmp_path, monkeypatch)
        arch_root = tmp_path / "archives"
        gate_result = {"verdict": "PROMOTE_CANDIDATE", "delta_by_year_repeat": {}}
        arch = generate_archive(sched, ledger, str(run_dir), "p", "m",
                                gate_result, archive_root=str(arch_root),
                                stage="dev", raw_dataset_paths={"2024": "x"},
                                enriched_dataset_paths={"2024": "x"},
                                run_id="test_atomic")
        target = Path(arch["archive_dir"])
        assert target.exists()
        assert (target / "merged_details.jsonl").exists()
        assert (target / "merged_events.jsonl").exists()
        assert (target / "audit_index.json").exists()
        assert (target / "dev_gate.json").exists()
        # No temp dirs left behind
        temp_leftovers = list(arch_root.glob(".test_atomic-*.tmp-*"))
        assert len(temp_leftovers) == 0, f"Temp dirs not cleaned: {temp_leftovers}"

    def test_archive_failure_cleans_up_temp(self, tmp_path, monkeypatch):
        """If archive fails mid-way, no temp directory remains."""
        import scripts.phase6_6b2_orchestrator as m
        from scripts.phase6_6b2_orchestrator import generate_archive
        sched, ledger, run_dir = self._make_ready_schedule(tmp_path, monkeypatch)
        arch_root = tmp_path / "archives"
        # Make _merge_all_details raise to simulate mid-write failure
        def boom(*a, **kw):
            raise RuntimeError("simulated failure")
        monkeypatch.setattr(m, "_merge_all_details", boom)
        gate_result = {"verdict": "PROMOTE_CANDIDATE", "delta_by_year_repeat": {}}
        with pytest.raises(RuntimeError, match="simulated failure"):
            generate_archive(sched, ledger, str(run_dir), "p", "m",
                             gate_result, archive_root=str(arch_root),
                             stage="dev", raw_dataset_paths={"2024": "x"},
                             enriched_dataset_paths={"2024": "x"},
                             run_id="test_fail")
        temp_leftovers = list(arch_root.glob(".test_fail-*.tmp-*"))
        assert len(temp_leftovers) == 0


class TestCLIRunIdParam:
    """P0-1+P0-3: --run-id CLI parameter is REQUIRED."""

    def test_cli_shows_run_id_in_help(self, tmp_path):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "scripts/phase6_6b2_orchestrator.py", "run_dev", "--help"],
            capture_output=True, text=True, cwd="G:/project/agent",
        )
        assert result.returncode == 0
        assert "--run-id" in result.stdout

    def test_cli_requires_run_id(self, tmp_path):
        """Omitting --run-id must fail argparse (required=True)."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "scripts/phase6_6b2_orchestrator.py", "run_dev",
             "--provider", "p", "--model", "m", "--output-dir", str(tmp_path)],
            capture_output=True, text=True, cwd="G:/project/agent",
        )
        assert result.returncode != 0
        assert "--run-id" in (result.stderr + result.stdout)


class TestValidateRunId:
    """P0-1: _validate_run_id rejects path-escape and illegal inputs."""

    @pytest.mark.parametrize("bad", [
        None, "", ".", "..", "../escape", "..\\escape",
        "C:\\Windows", "/abs/path", "a/b", "a\\b",
        "has space", "bad;char", "-leadingdash", "a" * 65,
    ])
    def test_rejects_invalid_run_id(self, bad):
        from scripts.phase6_6b2_orchestrator import _validate_run_id
        with pytest.raises(SystemExit):
            _validate_run_id(bad)

    @pytest.mark.parametrize("good", [
        "run1", "my-exp_1", "A_b-C2", "a", "x" * 64, "_leading_uscore",
    ])
    def test_accepts_valid_run_id(self, good):
        from scripts.phase6_6b2_orchestrator import _validate_run_id
        _validate_run_id(good)

    def test_run_dev_rejects_none_run_id(self, tmp_path):
        """Public entry points must validate run_id (not just CLI)."""
        import scripts.phase6_6b2_orchestrator as m
        with pytest.raises(SystemExit, match="run_id 拒绝"):
            m.run_dev("deepseek", "deepseek-v4-flash", str(tmp_path), run_id=None)


class TestSmokeOnlyInDev:
    """P0-3: smoke runs ONLY in dev; reuse and final pass smoke_slices=None."""

    def _patch_all(self, m, monkeypatch, tmp_path, captured):
        def fake_run_all(schedule, ledger, provider, model, smoke_slices=None):
            captured["smoke_count"] = len(smoke_slices) if smoke_slices else 0
            for sl in schedule["slices"]:
                if not ledger.slice_completed(sl["slice_id"]):
                    # b1a_prime range [8,10], dual range [16,26]
                    calls = 9 if sl["arm"] == "b1a_prime" else 20
                    ledger.record_slice_completed(sl["slice_id"], calls, arm=sl["arm"])
            return 0
        def fake_merge(sched):
            return []
        def fake_integrity(merged, sched):
            return "PASS"
        def fake_gate(merged, stage="dev"):
            return {"verdict": "PROMOTE_CANDIDATE", "delta_by_year": {},
                    "delta_by_year_repeat": {}, "stage": stage,
                    "dual_merged_acc": 0.4, "min_year_delta": 0.01}
        def fake_b1c():
            return {"count": 0, "sha256": "x", "rows": []}
        def fake_report(*a, **kw):
            pass
        def fake_archive(sched, ledger, run_dir, provider, model, gate_result,
                         archive_root=None, stage="dev", raw_dataset_paths=None,
                         enriched_dataset_paths=None, run_id=None, smoke_attempted=0):
            arch_dir = tmp_path / f"fake_arch_{stage}"
            arch_dir.mkdir(exist_ok=True)
            rn = f"{stage}_gate.json"
            arch_run_id = f"{run_id}-6b2-{stage}-x"
            code_fp = "fp" * 8
            audit_doc = {
                "run_id": arch_run_id, "user_run_id": run_id,
                "stage": stage,
                "provider": provider, "model": model,
                "code_fingerprint": code_fp,
                "gate_verdict": gate_result["verdict"],
            }
            audit_path = arch_dir / "audit_index.json"
            audit_path.write_text(json.dumps(audit_doc), encoding="utf-8")
            (arch_dir / rn).write_text(json.dumps({
                "verdict": gate_result["verdict"], "stage": stage,
                "run_id": arch_run_id, "user_run_id": run_id,
                "archive_dir": str(arch_dir),
                "audit_index_sha256": m_sha256(str(audit_path)),
                "provider": provider, "model": model,
                "code_fingerprint": code_fp,
                "dataset_sha256": "b" * 64, "sched_hash": "c" * 64,
            }), encoding="utf-8")
            return {"archive_dir": str(arch_dir), "run_id": arch_run_id,
                    "receipt": {}}
        monkeypatch.setattr(m, "_run_all_slices", fake_run_all)
        monkeypatch.setattr(m, "_merge_all_details", fake_merge)
        monkeypatch.setattr(m, "_integrity_gate", fake_integrity)
        monkeypatch.setattr(m, "compute_gate", fake_gate)
        monkeypatch.setattr(m, "load_b1c_advisory", fake_b1c)
        monkeypatch.setattr(m, "generate_report", fake_report)
        monkeypatch.setattr(m, "generate_archive", fake_archive)
        monkeypatch.setattr(m, "_compute_experiment_code_fingerprint", lambda: "fp" * 8)

    def _make_ds(self, tmp_path, years):
        ds_paths = {}
        for y in years:
            p = tmp_path / f"ds_{y}.jsonl"
            cids = [f"c{i:04d}" for i in range(40)]
            with open(p, "w", encoding="utf-8") as f:
                for cid in cids:
                    f.write(json.dumps({"case_id": cid}) + "\n")
            ds_paths[y] = str(p)
        return ds_paths

    def _prepare_context(self, m, out, run_id):
        """Create a real run context via _prepare_run_context, consistent with the
        (possibly monkeypatched) fingerprint the entry point will compute."""
        m._prepare_run_context(
            output_dir=out, run_id=run_id, stage="dev", resume=False,
            protocol=m._validate_frozen_protocol("deepseek", "deepseek-v4-flash"),
            code_fingerprint=m._compute_experiment_code_fingerprint())

    def test_reuse_does_not_run_smoke(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        captured = {}
        self._patch_all(m, monkeypatch, tmp_path, captured)
        out = tmp_path / "exp"
        out.mkdir()
        self._prepare_context(m, out, "r1")
        dev_rpath = TestReceiptChain()._place_receipt(out, "r1", "dev")
        ds_paths = self._make_ds(tmp_path, ["2021", "2022"])
        m.run_reuse("deepseek", "deepseek-v4-flash", str(out), dev_rpath,
                    dataset_paths=ds_paths, run_id="r1", resume=True)
        assert captured["smoke_count"] == 0, "reuse must NOT run smoke"

    def test_2023_final_does_not_run_smoke(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        import scripts.phase6_6b2_sealed_workflow as sw
        captured = {}
        self._patch_all(m, monkeypatch, tmp_path, captured)
        out = tmp_path / "exp"
        out.mkdir()
        self._prepare_context(m, out, "r1")
        TestReceiptChain()._place_receipt(out, "r1", "dev")
        # sealed workflow requires reuse verdict="PASS" (not PROMOTE_CANDIDATE)
        reuse_rpath = TestReceiptChain()._place_receipt(out, "r1", "reuse", verdict="PASS")
        monkeypatch.setattr(sw, "acquire_2023_run_lock",
                            lambda *a, **kw: "NEW")
        monkeypatch.setattr(sw, "verify_2023_raw_data", lambda *a, **kw: None)
        monkeypatch.setattr(sw, "record_enriched_sha_to_lock", lambda *a, **kw: None)
        monkeypatch.setattr(sw, "enrich_year",
                            lambda y, raw, out_path: Path(out_path).write_text(
                                Path(raw).read_text(encoding="utf-8"), encoding="utf-8"))
        monkeypatch.setattr(sw, "update_lock_schedule_hash", lambda *a, **kw: None)
        monkeypatch.setattr(sw, "finalize_2023_run_lock", lambda *a, **kw: None)
        ds_2023 = tmp_path / "ds_2023.jsonl"
        with open(ds_2023, "w", encoding="utf-8") as f:
            for i in range(40):
                f.write(json.dumps({"case_id": f"c{i:04d}"}) + "\n")
        m.run_2023_final("deepseek", "deepseek-v4-flash", str(out), reuse_rpath,
                         dataset_paths={"2023": str(ds_2023)}, run_id="r1", resume=True)
        assert captured["smoke_count"] == 0, "2023 final must NOT run smoke"

    def test_dev_runs_single_smoke(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        captured = {}
        self._patch_all(m, monkeypatch, tmp_path, captured)
        out = tmp_path / "exp"
        ds_paths = self._make_ds(tmp_path, ["2024", "2025"])
        m.run_dev("deepseek", "deepseek-v4-flash", str(out),
                  dataset_paths=ds_paths, run_id="r1")
        assert captured["smoke_count"] == 1, "dev must run exactly 1 smoke slice"


class TestSmokeLedgerBudget:
    """P0-3: smoke ledger uses hard_cap=10, range [1,10]."""

    def test_smoke_ledger_constants(self):
        from scripts.phase6_6b2_orchestrator import (
            SMOKE_GLOBAL_HARD_CAP, SMOKE_SLICE_MIN, SMOKE_SLICE_MAX, SMOKE_HARD_CAP)
        assert SMOKE_HARD_CAP == 10
        assert SMOKE_GLOBAL_HARD_CAP == 10
        assert SMOKE_SLICE_MIN == 1
        assert SMOKE_SLICE_MAX == 10


class TestSmokeAttemptedInAudit:
    """P0-3: smoke_attempted is recorded in archive audit and receipt."""

    def test_smoke_attempted_in_audit_and_receipt(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        sched, ledger, run_dir = TestAtomicArchive()._make_ready_schedule(
            tmp_path, monkeypatch)
        arch_root = tmp_path / "archives"
        gate_result = {"verdict": "PROMOTE_CANDIDATE", "delta_by_year_repeat": {}}
        smoke_val = 7
        arch = m.generate_archive(sched, ledger, str(run_dir), "p", "m",
                                  gate_result, archive_root=str(arch_root),
                                  stage="dev", raw_dataset_paths={"2024": "x"},
                                  enriched_dataset_paths={"2024": "x"},
                                  run_id="sa_test", smoke_attempted=smoke_val)
        target = Path(arch["archive_dir"])
        audit = json.loads((target / "audit_index.json").read_text(encoding="utf-8"))
        receipt = json.loads((target / "dev_gate.json").read_text(encoding="utf-8"))
        assert audit["smoke_attempted"] == smoke_val
        assert audit["budget"]["smoke_attempted"] == smoke_val
        assert receipt["smoke_attempted"] == smoke_val


class TestCodeFingerprintCriticalCoverage:
    """P0-A: code fingerprint MUST cover all functions affecting experiment execution
    and admission decisions; drift in any of them between stages must be detected."""

    CRITICAL_FUNCTIONS = [
        # Scheduling
        "_build_schedule", "_build_smoke_slices", "_compute_schedule_hash",
        # Execution
        "_run_slice", "_run_all_slices", "_verify_completed_slice",
        # Integrity / gate / smoke gate
        "_integrity_gate", "compute_gate", "_slice_integrity_gate",
        "determine_smoke_state", "verify_smoke_completed", "_smoke_integrity",
        # Run-id and receipt chain (NEW in this revision)
        "_validate_run_id", "_verify_receipt_belongs_to_run", "_publish_receipt_atomic",
        # Archive and report
        "generate_archive", "_merge_all_details", "_compute_dataset_hashes",
        # Stage entry points
        "run_dev", "run_reuse", "run_2023_final",
    ]

    def test_fingerprint_includes_all_critical_functions(self):
        """If this fails, a newly added critical function was not added to the
        fingerprint hash — dev→reuse→final drift would be silent."""
        import inspect
        import scripts.phase6_6b2_orchestrator as m
        fp_src = inspect.getsource(m._compute_experiment_code_fingerprint)
        for fn_name in self.CRITICAL_FUNCTIONS:
            assert fn_name in fp_src, (
                f"CRITICAL: {fn_name} is not referenced in _compute_experiment_code_fingerprint; "
                f"code drift between stages will be undetectable"
            )

    def test_fingerprint_changes_when_validate_run_id_changes(self, monkeypatch):
        """Monkey-patching _validate_run_id MUST change the fingerprint."""
        import scripts.phase6_6b2_orchestrator as m
        fp1 = m._compute_experiment_code_fingerprint()

        # Replace with a differently-named function (different source) to simulate drift
        def _validate_run_id_v2(run_id):
            # Drift: allow uppercase letters (original doesn't)
            if not run_id:
                raise SystemExit("empty")
            return run_id
        monkeypatch.setattr(m, "_validate_run_id", _validate_run_id_v2)
        fp2 = m._compute_experiment_code_fingerprint()
        assert fp1 != fp2, "_validate_run_id change must alter fingerprint"

    def test_fingerprint_changes_when_verify_receipt_changes(self, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        fp1 = m._compute_experiment_code_fingerprint()

        # Replace with a function that has different source (simulates drift)
        def _verify_receipt_belongs_to_run_v2(receipt_path, output_dir, run_id, expected_stage):
            return {"drifted": True}
        monkeypatch.setattr(m, "_verify_receipt_belongs_to_run",
                            _verify_receipt_belongs_to_run_v2)
        fp2 = m._compute_experiment_code_fingerprint()
        assert fp1 != fp2, "_verify_receipt_belongs_to_run change must alter fingerprint"

    def test_fingerprint_includes_runner_code_fingerprint(self, monkeypatch):
        """P0-2: experiment fingerprint MUST include the runner _code_fingerprint() result,
        so changes to run_benchmark.py / profiles.py / dual_system_reasoning.py are detected."""
        import scripts.phase6_6b2_orchestrator as m
        import benchmark.runners.run_benchmark as rb
        fp1 = m._compute_experiment_code_fingerprint()

        # Monkey-patch runner _code_fingerprint to return a different value.
        # The local `from ... import _code_fingerprint` reads from the cached module,
        # so setattr on the module object is seen by subsequent local imports.
        monkeypatch.setattr(rb, "_code_fingerprint", lambda: "deadbeef" * 8)
        fp2 = m._compute_experiment_code_fingerprint()
        assert fp1 != fp2, (
            "runner _code_fingerprint() change must alter experiment fingerprint; "
            "runner code drift would otherwise be undetected across stages")

    def test_fingerprint_fails_closed_when_runner_fp_missing(self, monkeypatch):
        """P0: if runner _code_fingerprint() cannot be imported, _compute_experiment_code_fingerprint
        MUST raise SystemExit (fail-closed), not silently return a degraded fingerprint."""
        import scripts.phase6_6b2_orchestrator as m
        import benchmark.runners.run_benchmark as rb
        # Simulate AttributeError: _code_fingerprint was removed/renamed in runner
        monkeypatch.delattr(rb, "_code_fingerprint", raising=False)
        with pytest.raises(SystemExit, match="runner code fingerprint unavailable"):
            m._compute_experiment_code_fingerprint()

    def test_fingerprint_fails_closed_when_sealed_workflow_unimportable(self, monkeypatch):
        """P0: if sealed_workflow functions cannot be imported, fingerprint MUST raise
        SystemExit (fail-closed), not silently skip the entire admission/lock layer."""
        import sys
        import types
        import scripts.phase6_6b2_orchestrator as m

        # Replace the module in sys.modules with a stub that lacks all required
        # symbols, simulating a broken/truncated install (triggers ImportError from
        # the `from ... import (a, b, c)` statement when names are missing).
        saved = sys.modules.get("scripts.phase6_6b2_sealed_workflow")
        stub = types.ModuleType("scripts.phase6_6b2_sealed_workflow")
        sys.modules["scripts.phase6_6b2_sealed_workflow"] = stub
        try:
            with pytest.raises(SystemExit, match="sealed workflow fingerprint unavailable"):
                m._compute_experiment_code_fingerprint()
        finally:
            if saved is not None:
                sys.modules["scripts.phase6_6b2_sealed_workflow"] = saved
            else:
                sys.modules.pop("scripts.phase6_6b2_sealed_workflow", None)


class TestDash6b2UserRunId:
    """P1: run_id containing '-6b2-' (e.g. 'alpha-6b2-beta') must be usable across all
    stages because user_run_id is stored explicitly, not parsed via split('-6b2-')."""

    def test_user_run_id_with_dash_6b2_passes_validate(self):
        from scripts.phase6_6b2_orchestrator import _validate_run_id
        # Must not raise SystemExit (valid slug containing "-6b2-")
        _validate_run_id("alpha-6b2-beta")

    def test_reuse_accepts_dash_6b2_run_id(self, tmp_path, monkeypatch):
        """A run_id that itself contains '-6b2-' must successfully pass
        _verify_receipt_belongs_to_run because the receipt stores user_run_id."""
        import scripts.phase6_6b2_orchestrator as m
        weird_run_id = "alpha-6b2-beta"
        out = tmp_path / "exp"
        out.mkdir()
        # Place a valid dev receipt using TestReceiptChain helper
        rc = TestReceiptChain()
        rc._place_receipt(out, weird_run_id, "dev")
        rpath = out / "runs" / weird_run_id / "gates" / "dev_gate.json"
        # Must NOT raise — prior bug: split("-6b2-",1)[0] would give "alpha" not "alpha-6b2-beta"
        receipt = m._verify_receipt_belongs_to_run(
            str(rpath), str(out), weird_run_id, "dev")
        assert receipt["user_run_id"] == weird_run_id

    def test_user_run_id_persisted_in_archive_audit_and_receipt(
            self, tmp_path, monkeypatch):
        """generate_archive must embed user_run_id in both audit and receipt."""
        import scripts.phase6_6b2_orchestrator as m
        weird_run_id = "x-6b2-y"
        sched, ledger, run_dir = TestAtomicArchive()._make_ready_schedule(
            tmp_path, monkeypatch)
        gate_result = {"verdict": "PROMOTE_CANDIDATE", "delta_by_year_repeat": {}}
        arch = m.generate_archive(
            sched, ledger, str(run_dir), "p", "m", gate_result,
            archive_root=str(tmp_path / "ar"), stage="dev",
            raw_dataset_paths={"2024": "x"}, enriched_dataset_paths={"2024": "x"},
            run_id=weird_run_id, smoke_attempted=3,
        )
        target = Path(arch["archive_dir"])
        audit = json.loads((target / "audit_index.json").read_text(encoding="utf-8"))
        receipt = json.loads((target / "dev_gate.json").read_text(encoding="utf-8"))
        assert audit["user_run_id"] == weird_run_id
        assert receipt["user_run_id"] == weird_run_id
        # archive run_id is different (has suffix), but user_run_id matches input
        assert receipt["run_id"] != weird_run_id  # archive run_id has suffix


class TestFrozenV4FlashProtocol:
    def test_constants_are_exact(self):
        import scripts.phase6_6b2_orchestrator as m
        assert m.FROZEN_PROVIDER == "deepseek"
        assert m.FROZEN_MODEL == "deepseek-v4-flash"
        assert m.FROZEN_THINKING_MODE == "disabled"
        assert m.MODEL_LABEL == "DeepSeek-V4-Flash non-thinking"

    @pytest.mark.parametrize("provider,model", [
        ("anthropic", "deepseek-v4-flash"),
        ("deepseek", "deepseek-v4-pro"),
        ("deepseek", "deepseek-chat"),
        ("DeepSeek", "deepseek-v4-flash"),
    ])
    def test_protocol_drift_is_rejected(self, provider, model):
        import scripts.phase6_6b2_orchestrator as m
        with pytest.raises(SystemExit, match="6B2 frozen protocol mismatch"):
            m._validate_frozen_protocol(provider, model)

    def test_valid_protocol_returns_frozen_values(self):
        import scripts.phase6_6b2_orchestrator as m
        assert m._validate_frozen_protocol(
            "deepseek", "deepseek-v4-flash"
        ) == {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "thinking_mode": "disabled",
            "model_label": "DeepSeek-V4-Flash non-thinking",
        }

    def test_environment_cannot_override_frozen_protocol(self, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
        assert m._validate_frozen_protocol(
            "deepseek", "deepseek-v4-flash"
        ) == {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "thinking_mode": "disabled",
            "model_label": "DeepSeek-V4-Flash non-thinking",
        }

    def _install_lock_probe(self, m, monkeypatch):
        def fail_acquire(*a, **kw):
            raise AssertionError(
                "OutputDirLock.acquire must not be reached on protocol drift")
        monkeypatch.setattr(m.OutputDirLock, "acquire", fail_acquire)

    def test_run_dev_rejects_drift_before_lock_or_artifacts(
            self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        self._install_lock_probe(m, monkeypatch)
        with pytest.raises(SystemExit, match="6B2 frozen protocol mismatch"):
            m.run_dev("deepseek", "deepseek-chat", str(tmp_path), run_id="r1")
        assert not (tmp_path / "runs").exists()

    def test_run_reuse_rejects_drift_before_lock_or_artifacts(
            self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        self._install_lock_probe(m, monkeypatch)
        with pytest.raises(SystemExit, match="6B2 frozen protocol mismatch"):
            m.run_reuse("deepseek", "deepseek-chat", str(tmp_path),
                        str(tmp_path / "dev_gate.json"), run_id="r1")
        assert not (tmp_path / "runs").exists()

    def test_run_2023_final_rejects_drift_before_lock_or_artifacts(
            self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        self._install_lock_probe(m, monkeypatch)
        with pytest.raises(SystemExit, match="6B2 frozen protocol mismatch"):
            m.run_2023_final("deepseek", "deepseek-chat", str(tmp_path),
                             str(tmp_path / "reuse_gate.json"), run_id="r1")
        assert not (tmp_path / "runs").exists()


class TestRunContext:
    """Task 5: atomic run_context.json creation; resume only via explicit opt-in
    with exact frozen-field and code fingerprint match. No legacy migration."""

    def _protocol(self, m):
        return m._validate_frozen_protocol("deepseek", "deepseek-v4-flash")

    def _fresh_dev_context(self, m, output_dir, run_id="r1",
                           code_fingerprint="a" * 64):
        return m._prepare_run_context(
            output_dir=output_dir, run_id=run_id, stage="dev",
            resume=False, protocol=self._protocol(m),
            code_fingerprint=code_fingerprint)

    def _publish_receipt(self, runs_root, stage):
        gates = runs_root / "gates"
        gates.mkdir(parents=True, exist_ok=True)
        (gates / f"{stage}_gate.json").write_text(json.dumps({
            "verdict": "PROMOTE_CANDIDATE", "stage": stage,
        }), encoding="utf-8")

    def test_fresh_dev_creates_context_atomically(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        runs_root, context = self._fresh_dev_context(m, tmp_path)
        assert runs_root == tmp_path / "runs" / "r1"
        assert (tmp_path / "runs").is_dir()  # parent created by helper
        context_path = runs_root / "run_context.json"
        assert context_path.exists()
        on_disk = json.loads(context_path.read_text(encoding="utf-8"))
        for field in m.RUN_CONTEXT_REQUIRED_FIELDS:
            assert field in on_disk, f"required field missing: {field}"
        assert on_disk["provider"] == "deepseek"
        assert on_disk["model"] == "deepseek-v4-flash"
        assert on_disk["thinking_mode"] == "disabled"
        assert on_disk["model_label"] == "DeepSeek-V4-Flash non-thinking"
        assert on_disk["code_fingerprint"] == "a" * 64
        assert on_disk == context
        # atomic write via _atomic_write_json: no temp leftover
        assert not (runs_root / "run_context.tmp").exists()

    def test_fresh_dev_rejects_existing_run_dir_without_modifying_it(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        runs_root = tmp_path / "runs" / "r1"
        runs_root.mkdir(parents=True)
        marker = runs_root / "marker.txt"
        marker.write_text("keep", encoding="utf-8")
        with pytest.raises(SystemExit):
            self._fresh_dev_context(m, tmp_path)
        assert not (runs_root / "run_context.json").exists()
        assert marker.read_text(encoding="utf-8") == "keep"

    def test_existing_run_without_context_is_rejected_without_migration(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        runs_root = tmp_path / "runs" / "legacy-v4-pro"
        runs_root.mkdir(parents=True)
        legacy = runs_root / "legacy.events.jsonl"
        legacy.write_text('{"usage":{"reasoning_tokens":12}}\n', encoding="utf-8")
        before = legacy.read_bytes()

        with pytest.raises(SystemExit, match="run_context.json missing"):
            m._prepare_run_context(
                output_dir=tmp_path,
                run_id="legacy-v4-pro",
                stage="dev",
                resume=True,
                protocol=m._validate_frozen_protocol(
                    "deepseek", "deepseek-v4-flash"
                ),
                code_fingerprint="a" * 64,
            )

        assert not (runs_root / "run_context.json").exists()
        assert legacy.read_bytes() == before

    @pytest.mark.parametrize("field,value", [
        ("provider", "anthropic"),
        ("model", "deepseek-v4-pro"),
        ("thinking_mode", "enabled"),
        ("model_label", "DeepSeek-V4-Pro"),
        ("code_fingerprint", "b" * 64),
    ])
    def test_resume_rejects_context_drift(self, tmp_path, field, value):
        import scripts.phase6_6b2_orchestrator as m
        runs_root, _ = self._fresh_dev_context(m, tmp_path)
        context_path = runs_root / "run_context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context[field] = value
        context_path.write_text(json.dumps(context), encoding="utf-8")
        with pytest.raises(SystemExit):
            m._prepare_run_context(
                output_dir=tmp_path, run_id="r1", stage="dev",
                resume=True, protocol=self._protocol(m),
                code_fingerprint="a" * 64)

    def test_resume_allows_unfinished_dev(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        runs_root, created = self._fresh_dev_context(m, tmp_path)
        resumed_root, context = m._prepare_run_context(
            output_dir=tmp_path, run_id="r1", stage="dev",
            resume=True, protocol=self._protocol(m),
            code_fingerprint="a" * 64)
        assert resumed_root == runs_root
        assert context == created

    def test_dev_rerun_rejected_after_dev_receipt_published(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        runs_root, _ = self._fresh_dev_context(m, tmp_path)
        self._publish_receipt(runs_root, "dev")
        with pytest.raises(SystemExit):
            m._prepare_run_context(
                output_dir=tmp_path, run_id="r1", stage="dev",
                resume=True, protocol=self._protocol(m),
                code_fingerprint="a" * 64)

    def test_reuse_requires_resume_and_dev_receipt(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        runs_root, _ = self._fresh_dev_context(m, tmp_path)
        # reuse without resume is rejected even with a valid context
        with pytest.raises(SystemExit):
            m._prepare_run_context(
                output_dir=tmp_path, run_id="r1", stage="reuse",
                resume=False, protocol=self._protocol(m),
                code_fingerprint="a" * 64)
        # resume without published dev receipt is rejected
        with pytest.raises(SystemExit):
            m._prepare_run_context(
                output_dir=tmp_path, run_id="r1", stage="reuse",
                resume=True, protocol=self._protocol(m),
                code_fingerprint="a" * 64)
        # dev receipt published, reuse receipt not yet: allowed
        self._publish_receipt(runs_root, "dev")
        resumed_root, _ = m._prepare_run_context(
            output_dir=tmp_path, run_id="r1", stage="reuse",
            resume=True, protocol=self._protocol(m),
            code_fingerprint="a" * 64)
        assert resumed_root == runs_root
        # reuse receipt already published: rerun rejected
        self._publish_receipt(runs_root, "reuse")
        with pytest.raises(SystemExit):
            m._prepare_run_context(
                output_dir=tmp_path, run_id="r1", stage="reuse",
                resume=True, protocol=self._protocol(m),
                code_fingerprint="a" * 64)

    def test_final_2023_requires_resume_and_reuse_receipt(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        runs_root, _ = self._fresh_dev_context(m, tmp_path)
        # final_2023 without resume is rejected
        with pytest.raises(SystemExit):
            m._prepare_run_context(
                output_dir=tmp_path, run_id="r1", stage="final_2023",
                resume=False, protocol=self._protocol(m),
                code_fingerprint="a" * 64)
        # resume with only dev receipt is rejected (needs reuse receipt)
        self._publish_receipt(runs_root, "dev")
        with pytest.raises(SystemExit):
            m._prepare_run_context(
                output_dir=tmp_path, run_id="r1", stage="final_2023",
                resume=True, protocol=self._protocol(m),
                code_fingerprint="a" * 64)
        # reuse receipt published, final receipt not yet: allowed
        self._publish_receipt(runs_root, "reuse")
        resumed_root, _ = m._prepare_run_context(
            output_dir=tmp_path, run_id="r1", stage="final_2023",
            resume=True, protocol=self._protocol(m),
            code_fingerprint="a" * 64)
        assert resumed_root == runs_root
        # final receipt already published: rerun rejected
        self._publish_receipt(runs_root, "final_2023")
        with pytest.raises(SystemExit):
            m._prepare_run_context(
                output_dir=tmp_path, run_id="r1", stage="final_2023",
                resume=True, protocol=self._protocol(m),
                code_fingerprint="a" * 64)

    def test_failure_after_context_creation_is_recorded(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        missing_ds = tmp_path / "missing.jsonl"
        with pytest.raises(SystemExit):
            m.run_dev("deepseek", "deepseek-v4-flash", str(tmp_path),
                      dataset_paths={"2024": str(missing_ds),
                                     "2025": str(missing_ds)},
                      run_id="r1")
        failures = tmp_path / "runs" / "r1" / "run_failures.jsonl"
        assert failures.exists()
        lines = [json.loads(l) for l in
                 failures.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1
        assert lines[0]["stage"] == "dev"
        assert "数据集路径不存在" in lines[0]["reason"]

    def test_wrong_provider_model_rejected_before_context_without_files(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as m
        with pytest.raises(SystemExit, match="6B2 frozen protocol mismatch"):
            m.run_dev("deepseek", "deepseek-chat", str(tmp_path), run_id="r1")
        assert not (tmp_path / "runs").exists()


def m_sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
