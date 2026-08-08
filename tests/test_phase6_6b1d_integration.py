"""Phase 6 6B1-D: integration tests for main() orchestration.

验证 main() 的核心流程:
  - smoke = schedule[0:5] (不是额外 5 个 slice)
  - --from-slice 审计 (跳过的 slice 必须 completed)
  - integrity gate (不完整实验 exit 2)
  - resume 传 --resume 标志
  - completed slice 验证后跳过
  - dry-run 不创建 ledger

注意: 这些测试 mock subprocess.run 来模拟 runner 行为, 但验证的是
orchestrator 的状态机逻辑, 不是 runner 本身.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import scripts.phase6_6b1d_orchestrator as orch
from scripts.phase6_6b1d_orchestrator import (
    ARMS,
    REASONED_PROFILE,
    TOTAL_SLICES,
    BudgetLedger,
    _integrity_gate,
    _process_slice,
    build_expected_key,
    compute_effective_cap,
    generate_schedule,
)

# ---- helpers ----

def _write_valid_detail(sl, provider="deepseek", model="deepseek-v4-pro"):
    """Write valid detail rows with correct attempt keys and parsed terminal_state."""
    dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
    rows = []
    for cid in sl["case_ids"]:
        key = build_expected_key(
            dataset_id, REASONED_PROFILE, sl["arm"],
            cid, sl["repeat"], provider, model)
        rows.append({"case_id": cid, "attempt_key": list(key),
                     "terminal_state": "parsed", "answer": "A",
                     "correct": True})
    os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
    with open(sl["detail_path"], "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def _write_valid_events(sl, n=None):
    """Write n call_attempt events."""
    count = n or sl["size"]
    os.makedirs(os.path.dirname(sl["events_path"]), exist_ok=True)
    with open(sl["events_path"], "w", encoding="utf-8") as f:
        f.writelines(json.dumps({"kind": "call_attempt", "idx": i}) + "\n" for i in range(count))


def _write_valid_manifest(sl):
    """Write a manifest file."""
    os.makedirs(os.path.dirname(sl["manifest_path"]), exist_ok=True)
    manifest = {
        "hard_cap": sl["hard_cap"],
        "scheduled_calls": sl["size"],
        "arm": sl["arm"],
        "ziwei_arm": sl["ziwei_arm"],
    }
    with open(sl["manifest_path"], "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)


def _complete_slice(sl):
    """Write all valid artifacts to make a slice look completed."""
    _write_valid_detail(sl)
    _write_valid_events(sl)
    _write_valid_manifest(sl)


def _write_resume_manifest(output_dir):
    """Write a run_manifest.json with the real labels SHA-256 so main() accepts
    a pre-populated output_dir as a valid resume (P0 #1: artifacts without a
    manifest are now fail-closed)."""
    ok, labels_sha, _, _ = orch.validate_labels(orch.LABELS_DEFAULT_PATH)
    assert ok, "default labels must validate for resume manifest setup"
    orch.write_run_manifest(output_dir, "deepseek", "deepseek-v4-pro",
                            labels_sha256=labels_sha)


def _extract_slice_id_from_cmd(cmd):
    """Extract slice_id from runner cmd."""
    for i, arg in enumerate(cmd):
        if arg == "--case-details-jsonl" and i + 1 < len(cmd):
            detail_path = cmd[i + 1]
            basename = os.path.basename(detail_path)
            if basename.startswith("details_") and basename.endswith(".jsonl"):
                return basename[len("details_"):-len(".jsonl")]
    return None


def _check_resume_flag(cmd):
    """Check if --resume flag is present in cmd."""
    return "--resume" in cmd


# ---- TDD 7: smoke = schedule[0:5] ----

class TestSmokeIsScheduleFirst5:
    """Smoke 必须是 schedule[0:5], 不是额外 5 个 slice."""

    def test_smoke_slices_are_schedule_first5(self, tmp_path, monkeypatch):
        """main() 使用 schedule[0:5] 作为 smoke, 总 budget = 1200 (不是 1240)."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        smoke_slices = schedule["slices"][:5]

        # Mock: 完成所有 smoke slice, 然后 --from-slice 999 应该被审计拦截
        for sl in smoke_slices:
            _complete_slice(sl)

        # Pre-populate ledger with completed smoke
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        for sl in smoke_slices:
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()
        _write_resume_manifest(output_dir)

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # --from-slice 999 -> 审计 slices 5..998 -> 应 fail (未完成)
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "999",
        ])
        # 审计应 fail: slices 5..149 未完成
        assert rc == 2

    def test_smoke_uses_5_different_groups_not_same_8_cases(self, tmp_path):
        """Smoke slices 覆盖 G0-G4 (40 题), 不是 5 个 slice 都用前 8 题."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        smoke_slices = schedule["slices"][:5]

        # 每个 smoke slice 的 case_ids 应该不同 (覆盖 40 题)
        all_case_ids = set()
        for sl in smoke_slices:
            all_case_ids.update(sl["case_ids"])
        assert len(all_case_ids) == 40, \
            f"smoke 应覆盖 40 题, 实际 {len(all_case_ids)}"

        # 5 个 smoke slice 覆盖 5 个 arm
        smoke_arms = {sl["arm"] for sl in smoke_slices}
        assert smoke_arms == set(ARMS)


# ---- TDD 7: --from-slice audit ----

class TestFromSliceAudit:
    """--from-slice 审计: 跳过的 slice 必须 completed."""

    def test_from_slice_with_incomplete_skipped_exits_2(self, tmp_path, monkeypatch):
        """--from-slice 10 但 slice 5 未完成 -> exit 2."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        smoke_slices = schedule["slices"][:5]

        # 完成所有 smoke
        for sl in smoke_slices:
            _complete_slice(sl)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        for sl in smoke_slices:
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()
        _write_resume_manifest(output_dir)

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # --from-slice 10 但 slices 5-9 未完成 -> 审计失败
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "10",
        ])
        assert rc == 2

    def test_from_slice_with_completed_skipped_passes(self, tmp_path, monkeypatch):
        """--from-slice 10 且 slices 0-9 全部 completed -> 审计通过, 继续."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        first_10 = schedule["slices"][:10]

        # 完成前 10 个 slice
        for sl in first_10:
            _complete_slice(sl)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        for sl in first_10:
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()
        _write_resume_manifest(output_dir)

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # Mock subprocess for remaining slices
        def fake_run(cmd, **kwargs):
            slice_id = _extract_slice_id_from_cmd(cmd)
            for s in schedule["slices"]:
                if s["slice_id"] == slice_id:
                    _complete_slice(s)
                    break
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        # --from-slice 10 -> 审计 slices 0-9 (已 completed) -> 通过
        # 但 remaining 140 slices 需要运行 -> 预算不够 (120 calls used, 1080 left, 140*8=1120)
        # 实际: 10*8=80 used, 1320-80=1240 left, 140*8=1120 < 1240, 够
        # 但 fake_run 会运行全部, 然后进入 integrity gate
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "10",
            "--archive-root", str(tmp_path / "archive"),
        ])
        # 应该通过审计, 运行剩余, 然后 integrity gate
        # 但 integrity gate 需要 1200 records, 我们 mock 了全部
        assert rc == 0
        # main() 完成后必须生成 comparison_table.json 和 report.md
        assert (output_dir / "comparison_table.json").exists()
        assert (output_dir / "report.md").exists()

    def test_from_slice_beyond_total_with_all_completed_no_crash(self, tmp_path, monkeypatch):
        """--from-slice 999 且全部 150 slices completed -> 审计通过, 不 IndexError, 返回 0."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)

        # 完成全部 150 slices
        for sl in schedule["slices"]:
            _complete_slice(sl)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        for sl in schedule["slices"]:
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()
        _write_resume_manifest(output_dir)

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # --from-slice 999 (beyond 150) + all completed -> 审计全 150, 无 IndexError
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--from-slice", "999",
            "--archive-root", str(tmp_path / "archive"),
        ])
        assert rc == 0


# ---- TDD 7: integrity gate ----

class TestIntegrityGate:
    """Integrity gate: 不完整实验不能返回 0."""

    def test_integrity_gate_missing_slices_exits_2(self, tmp_path, monkeypatch):
        """只有 5 smoke completed, 145 main 未完成 -> integrity gate exit 2."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        smoke_slices = schedule["slices"][:5]

        for sl in smoke_slices:
            _complete_slice(sl)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        for sl in smoke_slices:
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        # 直接测试 _integrity_gate
        ok, reason = _integrity_gate(schedule, ledger, type("Args", (), {
            "provider": "deepseek", "model": "deepseek-chat"})())
        assert ok is False
        assert "未完成" in reason or "missing" in reason.lower()

    def test_integrity_gate_complete_passes(self, tmp_path, monkeypatch):
        """全部 150 slices completed -> integrity gate 通过."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)

        for sl in schedule["slices"]:
            _complete_slice(sl)
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        ok, reason = _integrity_gate(schedule, ledger, type("Args", (), {
            "provider": "deepseek", "model": "deepseek-chat"})())
        assert ok is True

    def test_integrity_gate_wrong_record_count_exits_2(self, tmp_path, monkeypatch):
        """records 数量不等于 1200 -> integrity gate fail."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)

        for sl in schedule["slices"]:
            # 只写 7 条 (不是 8)
            _write_valid_manifest(sl)
            _write_valid_events(sl, n=7)
            dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
            rows = []
            for cid in sl["case_ids"][:7]:
                key = build_expected_key(
                    dataset_id, REASONED_PROFILE, sl["arm"],
                    cid, sl["repeat"], "deepseek", "deepseek-chat")
                rows.append({"case_id": cid, "attempt_key": list(key),
                             "terminal_state": "parsed", "answer": "A"})
            os.makedirs(os.path.dirname(sl["detail_path"]), exist_ok=True)
            with open(sl["detail_path"], "w", encoding="utf-8") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
            compute_effective_cap(sl["slice_id"], ledger, 0)
            ledger.record_slice_completed(sl["slice_id"], 7)
        ledger._save()

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        ok, reason = _integrity_gate(schedule, ledger, type("Args", (), {
            "provider": "deepseek", "model": "deepseek-chat"})())
        assert ok is False
        assert "1200" in reason or "记录" in reason


# ---- TDD 7: resume passes --resume flag ----

class TestResumePassesFlag:
    """Resume 状态必须传 --resume 给 runner."""

    def test_resume_state_passes_resume_flag(self, tmp_path, monkeypatch):
        """slice 在 resume 状态时, runner cmd 必须包含 --resume."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        sl = schedule["slices"][0]

        # Create manifest-only state (resume)
        _write_valid_manifest(sl)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        compute_effective_cap(sl["slice_id"], ledger, 0)
        ledger._save()

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        resume_flags_seen = []

        def fake_run(cmd, **kwargs):
            if _check_resume_flag(cmd):
                resume_flags_seen.append(True)
            _complete_slice(sl)
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        args = type("Args", (), {
            "provider": "deepseek", "model": "deepseek-v4-pro"})()
        result = _process_slice(sl, 0, TOTAL_SLICES, args, ledger)
        assert result == 1  # success
        assert len(resume_flags_seen) > 0, "resume 状态必须传 --resume"

    def test_fresh_state_no_resume_flag(self, tmp_path, monkeypatch):
        """slice 在 fresh 状态时, runner cmd 不应包含 --resume."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        sl = schedule["slices"][0]

        # fresh: no artifacts
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        resume_flags_seen = []

        def fake_run(cmd, **kwargs):
            if _check_resume_flag(cmd):
                resume_flags_seen.append(True)
            _complete_slice(sl)
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        args = type("Args", (), {
            "provider": "deepseek", "model": "deepseek-v4-pro"})()
        result = _process_slice(sl, 0, TOTAL_SLICES, args, ledger)
        assert result == 1  # success
        assert len(resume_flags_seen) == 0, "fresh 状态不应传 --resume"


# ---- TDD 7: completed slice skip ----

class TestCompletedSliceSkip:
    """Completed slice 验证后跳过, 不调用 runner."""

    def test_completed_slice_skips_runner(self, tmp_path, monkeypatch):
        """completed slice 不调用 subprocess.run."""
        output_dir = tmp_path / "output"
        schedule = generate_schedule(output_dir)
        sl = schedule["slices"][0]

        _complete_slice(sl)
        ledger_path = str(output_dir / "budget_ledger.json")
        ledger = BudgetLedger(ledger_path)
        compute_effective_cap(sl["slice_id"], ledger, 0)
        ledger.record_slice_completed(sl["slice_id"], 8)
        ledger._save()

        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))

        runner_called = {"count": 0}

        def fake_run(cmd, **kwargs):
            runner_called["count"] += 1
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(orch.subprocess, "run", fake_run)

        args = type("Args", (), {
            "provider": "deepseek", "model": "deepseek-v4-pro"})()
        result = _process_slice(sl, 0, TOTAL_SLICES, args, ledger)
        assert result == 0  # skipped
        assert runner_called["count"] == 0, "completed slice 不应调用 runner"


# ---- TDD 7: dry-run ----

class TestDryRun:
    """Dry-run 模式."""

    def test_dry_run_no_ledger(self, tmp_path):
        """dry-run 不创建 budget_ledger.json."""
        output_dir = tmp_path / "output"
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--dry-run",
        ])
        assert rc == 0
        assert (output_dir / "schedule.json").exists()
        assert not (output_dir / "budget_ledger.json").exists()

    def test_dry_run_150_slices(self, tmp_path):
        """dry-run schedule 150 slices, 1200 calls."""
        output_dir = tmp_path / "output"
        orch.main(["--output-dir", str(output_dir), "--dry-run"])
        with open(output_dir / "schedule.json", "r", encoding="utf-8") as f:
            schedule = json.load(f)
        assert schedule["total_slices"] == 150
        assert schedule["total_scheduled_calls"] == 1200


# ---- P0 #1: resume/fresh detection before schedule write ----

class TestResumeProtection:
    """P0 #1: manifest must be verified BEFORE schedule write; artifacts without
    manifest are fail-closed; schedule drift on resume is fail-closed."""

    def test_dry_run_schedule_alone_is_not_an_artifact(self, tmp_path):
        """schedule.json from a dry-run does NOT count as a historical artifact."""
        output_dir = tmp_path / "output"
        orch.main(["--output-dir", str(output_dir), "--dry-run"])
        assert (output_dir / "schedule.json").exists()
        assert not orch._has_historical_artifacts(output_dir)

    def test_budget_ledger_counts_as_artifact(self, tmp_path):
        """budget_ledger.json presence counts as a historical artifact."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        ledger = BudgetLedger(str(output_dir / "budget_ledger.json"))
        ledger._save()
        assert orch._has_historical_artifacts(output_dir)

    def test_slice_dir_counts_as_artifact(self, tmp_path):
        """A slice_* directory counts as a historical artifact."""
        output_dir = tmp_path / "output"
        (output_dir / "slice_2024_b1a_prime_R0_P0_G0").mkdir(parents=True)
        assert orch._has_historical_artifacts(output_dir)

    def test_artifacts_without_manifest_fail_closed(self, tmp_path, monkeypatch):
        """Historical artifacts (budget_ledger) but no run_manifest.json -> exit 2."""
        output_dir = tmp_path / "output"
        generate_schedule(output_dir)
        ledger = BudgetLedger(str(output_dir / "budget_ledger.json"))
        ledger._save()
        assert not (output_dir / "run_manifest.json").exists()

        rc = orch.main(["--output-dir", str(output_dir)])
        assert rc == 2

    def test_schedule_drift_on_resume_fail_closed(self, tmp_path, monkeypatch):
        """Resume with a manifest but tampered on-disk schedule.json -> exit 2.

        main() builds an in-memory candidate and compares against the historical
        schedule BEFORE any write, so the on-disk schedule.json is left untouched.
        """
        output_dir = tmp_path / "output"
        generate_schedule(output_dir)
        _write_resume_manifest(output_dir)

        # Tamper with on-disk schedule.json
        sched_path = output_dir / "schedule.json"
        with open(str(sched_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        data["total_slices"] = 999
        with open(str(sched_path), "w", encoding="utf-8") as f:
            json.dump(data, f)

        # Snapshot the (tampered) bytes so we can prove they are untouched
        with open(str(sched_path), "rb") as f:
            before = f.read()

        rc = orch.main(["--output-dir", str(output_dir)])
        assert rc == 2

        # The historical schedule.json must be byte-identical after the block
        with open(str(sched_path), "rb") as f:
            after = f.read()
        assert after == before, "schedule.json was overwritten despite drift block"

    def test_drift_block_leaves_schedule_byte_identical(self, tmp_path, monkeypatch):
        """A real code drift (manifest fingerprint mismatch) must NOT overwrite
        schedule.json. main() must exit 2 with the historical file untouched.

        This simulates the scenario where the experiment code changed between
        runs: the run manifest fingerprint no longer matches, so resume is
        rejected. The historical schedule.json must survive untouched as
        evidence of what was actually run.
        """
        output_dir = tmp_path / "output"
        generate_schedule(output_dir)
        _write_resume_manifest(output_dir)

        sched_path = output_dir / "schedule.json"
        with open(str(sched_path), "rb") as f:
            before = f.read()

        # Simulate code drift: tamper the manifest's fingerprint so it no longer
        # matches the current code.
        manifest_path = output_dir / "run_manifest.json"
        with open(str(manifest_path), "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["experiment_code_fingerprint"] = "deadbeef" * 8
        with open(str(manifest_path), "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        rc = orch.main(["--output-dir", str(output_dir)])
        assert rc == 2

        with open(str(sched_path), "rb") as f:
            after = f.read()
        assert after == before, "schedule.json overwritten on manifest drift block"

    def test_resume_consistent_does_not_rewrite_schedule(self, tmp_path, monkeypatch):
        """A consistent resume reuses the historical schedule.json without
        rewriting it (byte-identical)."""
        output_dir = tmp_path / "output"
        generate_schedule(output_dir)
        _write_resume_manifest(output_dir)

        sched_path = output_dir / "schedule.json"
        with open(str(sched_path), "rb") as f:
            before = f.read()

        # main() on a consistent resume proceeds to smoke gate; mock the slice
        # processing so we can observe the schedule-write behavior without a
        # full run. Integrity gate will fail (no slices completed) -> exit 2,
        # but schedule.json must not have been rewritten.
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        monkeypatch.setattr(orch, "_process_slice",
                            lambda sl, idx, total, args, ledger, is_smoke=True: 0)

        rc = orch.main([
            "--output-dir", str(output_dir),
            "--archive-root", str(tmp_path / "archive"),
        ])
        # integrity gate fails -> rc 2, but schedule preserved
        assert rc == 2
        with open(str(sched_path), "rb") as f:
            after = f.read()
        assert after == before, "consistent resume must not rewrite schedule.json"

    def test_fresh_start_writes_run_manifest(self, tmp_path, monkeypatch):
        """A truly fresh output_dir (no artifacts) proceeds past the artifact
        check and writes run_manifest.json after schedule generation."""
        output_dir = tmp_path / "output"
        generate_schedule(output_dir)  # schedule.json only, not an artifact
        assert not orch._has_historical_artifacts(output_dir)

        # main() will write run_manifest on fresh start. It then proceeds to
        # smoke gate; mock _process_slice to skip all slices as completed.
        monkeypatch.setattr(orch, "verify_slice_manifest",
                            lambda sl, p, m: (True, {}))
        monkeypatch.setattr(orch, "_process_slice",
                            lambda sl, idx, total, args, ledger, is_smoke=True: 0)

        # Stop after smoke gate by making integrity gate fail fast (no slices
        # actually completed in ledger) -> exit 2, but run_manifest must exist.
        rc = orch.main([
            "--output-dir", str(output_dir),
            "--archive-root", str(tmp_path / "archive"),
        ])
        # integrity gate fails (0 slices completed) -> rc 2, but manifest written
        assert (output_dir / "run_manifest.json").exists()
