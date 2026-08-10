"""Phase 7 orchestrator tests (plan Task 6).

Covers: frozen CLI contract + run_id/resume five cases (6.1), argv homology (6.1),
env sanitizer (6.2), max_cases state machine (6.3), BudgetLedger + retest budget
pre-allocation (6.4), smoke quantitative verdict (6.5).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import phase7_mingli_orchestrator as orch


# ---------------------------------------------------------------- fixtures


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path):
    return [json.loads(line) for line in
            Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _attempt_key(case_id, stage="main"):
    return ["mingli_160", orch.FROZEN_PROFILE, orch.FROZEN_ARM, stage,
            orch.FROZEN_PROVIDER, orch.FROZEN_MODEL, case_id, 0, 0, "p0"]


def _detail_row(case_id, terminal_state="parsed", stage="main", **extra):
    row = {
        "case_id": case_id,
        "chart_case_id": "case_1",
        "terminal_state": terminal_state,
        "correct": terminal_state == "parsed",
        "attempt_key": _attempt_key(case_id, stage),
    }
    row.update(extra)
    return row


def _call_attempt_event(case_id, stage="main"):
    return {"kind": "call_attempt", "attempt_key": _attempt_key(case_id, stage),
            "retry_idx": None, "error_type": None, "timestamp": "2026-08-10T00:00:00"}


def _smoke_fixtures(tmp_path, n=10, parsed=10, call_failed=0, gate_blocked=0):
    """合规 smoke 夹具：n 条终态 detail + 每键 1 条 call_attempt 事件。"""
    detail_path = tmp_path / "main" / "detail.jsonl"
    events_path = tmp_path / "main" / "detail.events.jsonl"
    rows, events = [], []
    for i in range(n):
        cid = f"mingli_ftb_{i + 1:04d}"
        state = "parsed"
        extra = {}
        if i >= parsed:
            state = "invalid"
        if i < call_failed:
            state = "call_failed"
        if i < gate_blocked:
            state = "unresolved"
            extra = {"gate_blocked": True}
        rows.append(_detail_row(cid, state, **extra))
        if state != "unresolved":
            events.append(_call_attempt_event(cid))
    _write_jsonl(detail_path, rows)
    _write_jsonl(events_path, events)
    return detail_path, events_path


# ---------------------------------------------------------------- 6.1 CLI


class TestCLISkeleton:
    def test_preflight_parses_and_dispatches(self, monkeypatch, tmp_path):
        captured = {}

        def _fake(work_dir):
            captured["work_dir"] = work_dir
            return 0

        monkeypatch.setattr(orch, "run_preflight", _fake)
        rc = orch.main(["preflight", "--work-dir", str(tmp_path / "pf")])
        assert rc == 0
        assert captured["work_dir"] == str(tmp_path / "pf")

    def test_preflight_default_work_dir(self, monkeypatch):
        captured = {}

        def _fake(work_dir):
            captured["work_dir"] = work_dir
            return 0

        monkeypatch.setattr(orch, "run_preflight", _fake)
        assert orch.main(["preflight"]) == 0
        assert captured["work_dir"] == ".tmp/phase7"

    def test_run_parses_and_dispatches(self, monkeypatch, tmp_path):
        captured = {}

        def _fake(run_id, resume=False, output_dir=None):
            captured.update(run_id=run_id, resume=resume, output_dir=output_dir)
            return {"status": "ok"}

        monkeypatch.setattr(orch, "run_mingli_baseline", _fake)
        rc = orch.main(["run", "--run-id", "r1", "--resume",
                        "--output-dir", str(tmp_path)])
        assert rc == 0
        assert captured == {"run_id": "r1", "resume": True, "output_dir": str(tmp_path)}

    def test_invalid_subcommand_exit_2(self):
        with pytest.raises(SystemExit) as exc:
            orch.main(["bogus"])
        assert exc.value.code == 2

    def test_run_requires_run_id(self):
        with pytest.raises(SystemExit) as exc:
            orch.main(["run"])
        assert exc.value.code == 2


class TestRunIdContract:
    """run_id / resume 五情形（计划 Task 6 v3 P0-2 冻结）。"""

    def test_invalid_or_traversal_run_id_rejected(self, tmp_path):
        for bad in ("../x", "a/b", "a\\b", "a b", "..", "/abs", "", "-lead"):
            with pytest.raises(SystemExit) as exc:
                orch.run_mingli_baseline(bad, output_dir=str(tmp_path))
            assert exc.value.code == 2, bad

    def test_existing_artifacts_without_resume_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(orch, "_execute_smoke", lambda *a: None)
        with pytest.raises(SystemExit):  # smoke 判定无 detail → BLOCKED，但产物目录已建
            orch.run_mingli_baseline("r1", output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as exc:
            orch.run_mingli_baseline("r1", output_dir=str(tmp_path))
        assert exc.value.code == 2

    def test_resume_without_context_or_manifest_rejected(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            orch.run_mingli_baseline("ghost", resume=True, output_dir=str(tmp_path))
        assert exc.value.code == 2
        # context 在、manifest 缺失同样拒绝
        runs_root = tmp_path / "runs" / "r2"
        runs_root.mkdir(parents=True)
        (runs_root / "run_context.json").write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            orch.run_mingli_baseline("r2", resume=True, output_dir=str(tmp_path))
        assert exc.value.code == 2

    def test_crash_after_smoke_resume_continues_from_main_resume(
            self, tmp_path, monkeypatch):
        calls = []

        def _boom(runs_root, context):
            raise RuntimeError("simulated crash after smoke judgement")

        monkeypatch.setattr(orch, "_execute_smoke", lambda *a: calls.append("smoke"))
        monkeypatch.setattr(orch, "_judge_smoke",
                            lambda *a, **k: {"passed": True, "failures": []})
        monkeypatch.setattr(orch, "_execute_main_resume", _boom)
        with pytest.raises(RuntimeError):
            orch.run_mingli_baseline("r3", output_dir=str(tmp_path))
        # 崩溃后同 run_id --resume：不得重跑 smoke，从 main_resume 继续
        monkeypatch.setattr(orch, "_execute_smoke",
                            lambda *a: (_ for _ in ()).throw(AssertionError("smoke re-run")))
        monkeypatch.setattr(orch, "_execute_main_resume",
                            lambda *a: calls.append("main_resume"))
        monkeypatch.setattr(orch, "_execute_retest", lambda *a: calls.append("retest"))
        monkeypatch.setattr(orch, "_execute_finalize", lambda *a: calls.append("finalize"))
        result = orch.run_mingli_baseline("r3", resume=True, output_dir=str(tmp_path))
        assert result["status"] == "ok"
        assert calls == ["smoke", "main_resume", "retest", "finalize"]

    def test_published_receipt_rerun_rejected(self, tmp_path):
        runs_root = tmp_path / "runs" / "r4"
        runs_root.mkdir(parents=True)
        (runs_root / orch.RECEIPT_FILENAME).write_text("{}", encoding="utf-8")
        for resume in (False, True):
            with pytest.raises(SystemExit) as exc:
                orch.run_mingli_baseline("r4", resume=resume, output_dir=str(tmp_path))
            assert exc.value.code == 2


class TestArgvHomology:
    def _slice_info(self, tmp_path):
        return {
            "dataset_path": str(tmp_path / "mingli_160.jsonl"),
            "case_ids_file": str(tmp_path / "case_ids_main.json"),
            "detail_path": str(tmp_path / "main" / "detail.jsonl"),
            "output_dir": str(tmp_path / "main"),
            "attempt_stage": "main",
            "scheduled_calls": 160,
            "hard_cap": 180,
            "max_cases": 10,
        }

    def test_frozen_argv_fields(self, tmp_path):
        cmd = orch._build_runner_command(self._slice_info(tmp_path))

        def _val(flag):
            return cmd[cmd.index(flag) + 1]

        assert _val("--profile") == "mingli_official_cot_astro"
        assert _val("--method") == "direct_choice"
        assert _val("--thinking-mode") == "disabled"
        assert _val("--temperature") == "0.0"
        assert _val("--arm") == "phase7_mingli_baseline"
        assert _val("--attempt-stage") == "main"
        assert _val("--scheduled-calls") == "160"
        assert _val("--hard-cap") == "180"
        assert _val("--as-of-date") == orch.FROZEN_DATE
        assert "--case-ids-file" in cmd

    def test_argv_has_no_ziwei_arm(self, tmp_path):
        cmd = orch._build_runner_command(self._slice_info(tmp_path))
        assert "--ziwei-arm" not in cmd

    def test_runner_cmd_and_slice_args_build_identical_manifest(self, tmp_path):
        """ManifestHomology：真实 argv 解析 namespace 与 _slice_runner_args 重建
        namespace 必须产出逐项一致的 resume manifest。"""
        from benchmark.runners.profiles import resolve_profile
        from benchmark.runners.run_benchmark import _build_parser, build_resume_manifest

        sl = self._slice_info(tmp_path)
        (tmp_path / "mingli_160.jsonl").write_text(
            json.dumps({"case_id": "mingli_ftb_0001"}) + "\n", encoding="utf-8")
        Path(sl["case_ids_file"]).write_text(
            json.dumps(["mingli_ftb_0001"]), encoding="utf-8")
        cmd = orch._build_runner_command(sl)
        argv_namespace = _build_parser().parse_args(cmd[3:])  # 跳过 [python, -m, module]
        profile = resolve_profile(orch.FROZEN_PROFILE, orch.CHART_SCHEMA)
        reconstructed = orch._slice_runner_args(sl)
        assert build_resume_manifest(argv_namespace, profile) == \
            build_resume_manifest(reconstructed, profile)


# ---------------------------------------------------------------- 6.2 env 净化


class TestEnvSanitizer:
    def test_child_env_purges_intervention_vars(self, monkeypatch):
        for var in orch.ENV_PURGE_VARS:
            monkeypatch.setenv(var, "1")
        child = orch._build_child_env()
        for var in orch.ENV_PURGE_VARS:
            assert var not in child
        # 其它变量原样继承
        monkeypatch.setenv("BAZI_UNRELATED", "keep")
        assert orch._build_child_env()["BAZI_UNRELATED"] == "keep"

    def test_env_flags_all_false(self):
        assert orch._env_flags() == {
            "rag": False, "fewshot": False, "apb": False, "shuffle_options": False}

    def test_run_context_and_manifest_record_four_false(self, tmp_path):
        runs_root, context = orch._prepare_run_context(str(tmp_path), "envrun", False)
        expected = {"rag": False, "fewshot": False, "apb": False,
                    "shuffle_options": False}
        assert context["env_flags"] == expected
        manifest = _load_json(runs_root / orch.RUN_MANIFEST_NAME)
        assert manifest["env_flags"] == expected


# ---------------------------------------------------------------- 6.3 max_cases 状态机


class TestMaxCasesStateMachine:
    def _fresh_context(self, tmp_path, run_id="sm"):
        _, context = orch._prepare_run_context(str(tmp_path), run_id, False)
        return context

    def test_initial_context_records_smoke_size_and_stage(self, tmp_path):
        context = self._fresh_context(tmp_path)
        assert context["smoke_size"] == 10
        assert context["stage"] == "smoke_first_pass"
        assert context["max_cases"] == 10

    def test_legal_transition_10_to_160(self, tmp_path):
        context = self._fresh_context(tmp_path)
        orch._advance_max_cases(context, 160)
        assert context["max_cases"] == 160
        assert context["max_cases_transitions"][-1]["from"] == 10
        assert context["max_cases_transitions"][-1]["to"] == 160

    def test_illegal_10_to_20_rejected(self, tmp_path):
        context = self._fresh_context(tmp_path)
        with pytest.raises(SystemExit) as exc:
            orch._advance_max_cases(context, 20)
        assert exc.value.code == 2

    def test_illegal_160_to_10_rejected(self, tmp_path):
        context = self._fresh_context(tmp_path)
        orch._advance_max_cases(context, 160)
        with pytest.raises(SystemExit) as exc:
            orch._advance_max_cases(context, 10)
        assert exc.value.code == 2

    def test_direct_160_without_smoke_record_rejected(self):
        context = {"max_cases": 160}  # 无 smoke_size/max_cases=10 的 smoke 记录
        with pytest.raises(SystemExit) as exc:
            orch._advance_max_cases(context, 160)
        assert exc.value.code == 2
        context = {}  # 完全无 smoke 记录
        with pytest.raises(SystemExit) as exc:
            orch._advance_max_cases(context, 160)
        assert exc.value.code == 2

    def test_flow_records_transition_into_run_context(self, tmp_path, monkeypatch):
        monkeypatch.setattr(orch, "_execute_smoke", lambda *a: None)
        monkeypatch.setattr(orch, "_judge_smoke",
                            lambda *a, **k: {"passed": True, "failures": []})
        monkeypatch.setattr(orch, "_execute_main_resume", lambda *a: None)
        monkeypatch.setattr(orch, "_execute_retest", lambda *a: None)
        monkeypatch.setattr(orch, "_execute_finalize", lambda *a: None)
        orch.run_mingli_baseline("smflow", output_dir=str(tmp_path))
        context = _load_json(tmp_path / "runs" / "smflow" / orch.RUN_CONTEXT_NAME)
        assert context["max_cases"] == 160
        assert context["stage"] == "finalize"
        assert [(t["from"], t["to"]) for t in context["max_cases_transitions"]] == [(10, 160)]


# ---------------------------------------------------------------- 6.4 retest 预算预占


def _main_artifacts(runs_root, n_parsed=158, eligible_ids=(), n_call_attempts=160):
    """合成 main 产物：detail（parsed + 指定 invalid/call_failed eligible）+ events。"""
    main_dir = Path(runs_root) / "main"
    rows, events = [], []
    idx = 0
    for i in range(n_parsed):
        idx += 1
        cid = f"mingli_ftb_{idx:04d}"
        rows.append(_detail_row(cid, "parsed"))
        events.append(_call_attempt_event(cid))
    for i, cid in enumerate(eligible_ids):
        state = "invalid" if i % 2 == 0 else "call_failed"
        rows.append(_detail_row(cid, state))
        events.append(_call_attempt_event(cid))
    # 补齐 call_attempt 总数（模拟重试）
    while len(events) < n_call_attempts:
        events.append(_call_attempt_event("mingli_ftb_0001"))
    detail_path = main_dir / "detail.jsonl"
    events_path = main_dir / "detail.events.jsonl"
    _write_jsonl(detail_path, rows)
    _write_jsonl(events_path, events)
    return detail_path, events_path


class TestRetestBudgetPlan:
    def test_three_values_and_ordering(self, tmp_path):
        eligible = ["mingli_ftb_0158", "mingli_ftb_0003", "mingli_ftb_0042"]
        detail, events = _main_artifacts(tmp_path, n_parsed=157,
                                         eligible_ids=eligible, n_call_attempts=165)
        plan = orch._plan_retest(detail, events)
        assert plan["hard_cap"] == 180 - 165          # allocation
        assert plan["scheduled_calls"] == min(3, 15)  # = 3
        assert plan["selected_case_ids"] == [
            "mingli_ftb_0003", "mingli_ftb_0042", "mingli_ftb_0158"]  # 升序
        assert plan["attempt_stage"] == "controlled_retest"
        assert plan["unselected_eligible_case_ids"] == []

    def test_budget_shortfall_caps_selection(self, tmp_path):
        eligible = [f"mingli_ftb_{i:04d}" for i in (1, 5, 9, 20, 33)]
        detail, events = _main_artifacts(tmp_path, n_parsed=155,
                                         eligible_ids=eligible, n_call_attempts=178)
        plan = orch._plan_retest(detail, events)
        assert plan["hard_cap"] == 2
        assert plan["scheduled_calls"] == 2
        assert plan["selected_case_ids"] == ["mingli_ftb_0001", "mingli_ftb_0005"]
        assert plan["unselected_eligible_case_ids"] == [
            "mingli_ftb_0009", "mingli_ftb_0020", "mingli_ftb_0033"]

    def test_retest_argv_frozen_budget_fields(self, tmp_path):
        eligible = ["mingli_ftb_0007", "mingli_ftb_0002"]
        detail, events = _main_artifacts(tmp_path, n_parsed=158,
                                         eligible_ids=eligible, n_call_attempts=170)
        plan = orch._plan_retest(detail, events)
        cmd = orch._build_runner_command(orch._retest_slice_info(tmp_path, plan))

        def _val(flag):
            return cmd[cmd.index(flag) + 1]

        assert _val("--attempt-stage") == "controlled_retest"
        assert _val("--scheduled-calls") == "2"
        assert _val("--hard-cap") == "10"
        assert "--ziwei-arm" not in cmd
        assert "--resume" not in cmd

    def test_retest_report_two_unretested_classes(self, tmp_path):
        plan = {
            "attempt_stage": "controlled_retest",
            "selected_case_ids": ["mingli_ftb_0001", "mingli_ftb_0002",
                                  "mingli_ftb_0003"],
            "case_ids_sha256": "x",
            "unselected_eligible_case_ids": ["mingli_ftb_0009", "mingli_ftb_0020"],
            "scheduled_calls": 3,
            "hard_cap": 3,
        }
        retest_detail = tmp_path / "retest" / "detail.jsonl"
        # 只执行了 0001/0002；0003 入选但被重试挤占未执行
        _write_jsonl(retest_detail, [
            _detail_row("mingli_ftb_0001", "parsed", stage="controlled_retest"),
            _detail_row("mingli_ftb_0002", "parsed", stage="controlled_retest"),
        ])
        report = orch._compute_retest_report(plan, retest_detail)
        assert report["unselected_eligible_case_ids"] == [
            "mingli_ftb_0009", "mingli_ftb_0020"]
        assert report["selected_not_executed_case_ids"] == ["mingli_ftb_0003"]
        assert report["retested_case_ids"] == ["mingli_ftb_0001", "mingli_ftb_0002"]


class TestRetestResumeIdentity:
    def _first_entry(self, tmp_path, monkeypatch, n_call_attempts=170,
                     eligible=("mingli_ftb_0002", "mingli_ftb_0007")):
        runs_root = Path(tmp_path)
        _main_artifacts(runs_root, n_parsed=158, eligible_ids=list(eligible),
                        n_call_attempts=n_call_attempts)
        captured = {}
        monkeypatch.setattr(orch, "_run_runner_subprocess",
                            lambda cmd: captured.setdefault("cmd", cmd))
        context = {}
        manifest = orch._execute_retest(runs_root, context)
        return manifest, captured["cmd"]

    def test_partial_crash_resume_does_not_reclaim_budget(self, tmp_path, monkeypatch):
        manifest1, cmd1 = self._first_entry(tmp_path, monkeypatch)
        # 合成 retest 部分完成：k=3 次 call_attempt（含重试）后崩溃
        paths = orch._retest_paths(tmp_path)
        events = [_call_attempt_event("mingli_ftb_0002", stage="controlled_retest"),
                  _call_attempt_event("mingli_ftb_0002", stage="controlled_retest"),
                  _call_attempt_event("mingli_ftb_0007", stage="controlled_retest")]
        _write_jsonl(paths["events"], events)
        manifest2 = orch._load_retest_manifest_for_resume(
            tmp_path, str(Path(tmp_path) / "main" / "detail.events.jsonl"))
        for field in orch.RETEST_FROZEN_FIELDS:
            assert manifest2[field] == manifest1[field], field
        assert manifest2["hard_cap"] == manifest1["hard_cap"]   # 不变
        assert manifest2["retest_consumed"] == 3
        assert manifest2["remaining_budget"] == manifest1["hard_cap"] - 3
        # 全程总和不超 180
        main_consumed = orch._count_call_attempts(
            str(Path(tmp_path) / "main" / "detail.events.jsonl"))
        assert main_consumed + manifest2["retest_consumed"] <= 180

    def test_first_vs_resume_argv_full_field_homology(self, tmp_path, monkeypatch):
        manifest1, cmd1 = self._first_entry(tmp_path, monkeypatch)
        paths = orch._retest_paths(tmp_path)
        _write_jsonl(paths["events"],
                     [_call_attempt_event("mingli_ftb_0002", stage="controlled_retest")])
        manifest2 = orch._load_retest_manifest_for_resume(
            tmp_path, str(Path(tmp_path) / "main" / "detail.events.jsonl"))
        cmd2 = orch._build_runner_command(
            orch._retest_slice_info(tmp_path, manifest2), resume=True)
        # 除 --resume 标志外逐项一致（五字段同源）
        assert cmd2[:len(cmd1)] == cmd1
        assert cmd2[len(cmd1):] == ["--resume"]

    def test_resume_drift_fail_closed(self, tmp_path, monkeypatch):
        manifest1, _ = self._first_entry(tmp_path, monkeypatch)
        paths = orch._retest_paths(tmp_path)
        main_events = str(Path(tmp_path) / "main" / "detail.events.jsonl")

        # (a) selected_case_ids 漂移（sha 对不上）
        tampered = dict(manifest1, selected_case_ids=["mingli_ftb_9999"])
        _atomic = orch._atomic_write_json
        _atomic(paths["manifest"], tampered)
        with pytest.raises(SystemExit) as exc:
            orch._load_retest_manifest_for_resume(tmp_path, main_events)
        assert exc.value.code == 2

        # (b) scheduled_calls 漂移
        _atomic(paths["manifest"], dict(manifest1, scheduled_calls=99))
        with pytest.raises(SystemExit) as exc:
            orch._load_retest_manifest_for_resume(tmp_path, main_events)
        assert exc.value.code == 2

        # (c) hard_cap 漂移（≠ 180 − main call_attempt）
        _atomic(paths["manifest"], dict(manifest1, hard_cap=manifest1["hard_cap"] + 1))
        with pytest.raises(SystemExit) as exc:
            orch._load_retest_manifest_for_resume(tmp_path, main_events)
        assert exc.value.code == 2

        # (d) attempt_stage 漂移
        _atomic(paths["manifest"], dict(manifest1, attempt_stage="main"))
        with pytest.raises(SystemExit) as exc:
            orch._load_retest_manifest_for_resume(tmp_path, main_events)
        assert exc.value.code == 2

        # 恢复正确 manifest 后可正常 resume（漂移检测非粘性）
        _atomic(paths["manifest"], manifest1)
        ok = orch._load_retest_manifest_for_resume(tmp_path, main_events)
        assert ok["hard_cap"] == manifest1["hard_cap"]

    def test_ledger_prealloc_idempotent_on_resume(self, tmp_path, monkeypatch):
        manifest1, _ = self._first_entry(tmp_path, monkeypatch)
        ledger_path = Path(tmp_path) / orch.BUDGET_LEDGER_NAME
        ledger1 = _load_json(ledger_path)
        assert ledger1["attempts_by_slice"]["retest_prealloc"] == manifest1["hard_cap"]
        assert ledger1["total_attempted"] == manifest1["hard_cap"]
        # 模拟崩溃后续跑：resume 路径不得再次领取预算
        paths = orch._retest_paths(tmp_path)
        _write_jsonl(paths["events"],
                     [_call_attempt_event("mingli_ftb_0002", stage="controlled_retest")])
        context = {}
        orch._execute_retest(tmp_path, context)
        ledger2 = _load_json(ledger_path)
        assert ledger2["total_attempted"] == ledger1["total_attempted"]
        assert ledger2["attempts_by_slice"] == ledger1["attempts_by_slice"]

    def test_no_eligible_short_circuits_without_runner(self, tmp_path, monkeypatch):
        _main_artifacts(tmp_path, n_parsed=160, eligible_ids=[], n_call_attempts=160)
        monkeypatch.setattr(
            orch, "_run_runner_subprocess",
            lambda cmd: (_ for _ in ()).throw(AssertionError("runner must not run")))
        manifest = orch._execute_retest(tmp_path, {})
        assert manifest["scheduled_calls"] == 0
        assert manifest["hard_cap"] == 20
        paths = orch._retest_paths(tmp_path)
        assert paths["manifest"].exists()


# ---------------------------------------------------------------- 6.5 smoke 量化判定


class TestSmokeVerdict:
    def test_all_pass(self, tmp_path):
        detail, events = _smoke_fixtures(tmp_path)
        verdict = orch._judge_smoke(detail, events)
        assert verdict["passed"] is True
        assert verdict["failures"] == []
        assert verdict["terminal_count"] == 10
        assert verdict["parsed"] == 10

    def test_all_pass_with_retry_reconciliation(self, tmp_path):
        """一键含 1 次网络重试：call_attempt=2 = 1 + model_call_failed=1，仍通过。"""
        detail, events = _smoke_fixtures(tmp_path, parsed=9)
        rows = _load_jsonl(events)
        rows.append(_call_attempt_event("mingli_ftb_0001"))
        rows.append({"kind": "model_call_failed",
                     "attempt_key": _attempt_key("mingli_ftb_0001"),
                     "retry_idx": 1, "error_type": "timeout",
                     "timestamp": "2026-08-10T00:00:01"})
        _write_jsonl(events, rows)
        verdict = orch._judge_smoke(detail, events)
        assert verdict["passed"] is True, verdict["failures"]

    def test_fail_wrong_terminal_count(self, tmp_path):
        detail, events = _smoke_fixtures(tmp_path, n=9)
        verdict = orch._judge_smoke(detail, events)
        assert verdict["passed"] is False
        assert any("terminal detail rows=9" in f for f in verdict["failures"])

    def test_fail_call_failed_nonzero(self, tmp_path):
        detail, events = _smoke_fixtures(tmp_path, call_failed=1)
        verdict = orch._judge_smoke(detail, events)
        assert verdict["passed"] is False
        assert any("call_failed=1" in f for f in verdict["failures"])

    def test_fail_gate_blocked_nonzero(self, tmp_path):
        detail, events = _smoke_fixtures(tmp_path, gate_blocked=1)
        verdict = orch._judge_smoke(detail, events)
        assert verdict["passed"] is False
        assert any("gate_blocked=1" in f for f in verdict["failures"])

    def test_fail_parsed_below_9(self, tmp_path):
        detail, events = _smoke_fixtures(tmp_path, parsed=8)
        verdict = orch._judge_smoke(detail, events)
        assert verdict["passed"] is False
        assert any("parsed=8" in f for f in verdict["failures"])

    def test_fail_orphan_precall_journal(self, tmp_path):
        detail, events = _smoke_fixtures(tmp_path)
        rows = _load_jsonl(events)
        rows.append(_call_attempt_event("mingli_ftb_0099"))  # 无终态 detail 的残缺 attempt
        _write_jsonl(events, rows)
        verdict = orch._judge_smoke(detail, events)
        assert verdict["passed"] is False
        assert any("orphan pre-call journal" in f for f in verdict["failures"])

    def test_fail_reconciliation_mismatch(self, tmp_path):
        """call_attempt=2 但无 model_call_failed → 对账不平。"""
        detail, events = _smoke_fixtures(tmp_path)
        rows = _load_jsonl(events)
        rows.append(_call_attempt_event("mingli_ftb_0001"))
        _write_jsonl(events, rows)
        verdict = orch._judge_smoke(detail, events)
        assert verdict["passed"] is False
        assert any("reconciliation mismatch" in f for f in verdict["failures"])

    def test_flow_blocks_when_smoke_fails(self, tmp_path, monkeypatch):
        """smoke 判定失败 → 退出 4 且不进入 main_resume。"""
        monkeypatch.setattr(orch, "_execute_smoke", lambda *a: None)
        monkeypatch.setattr(orch, "_judge_smoke",
                            lambda *a, **k: {"passed": False, "failures": ["x"]})
        monkeypatch.setattr(
            orch, "_execute_main_resume",
            lambda *a: (_ for _ in ()).throw(AssertionError("must not resume")))
        with pytest.raises(SystemExit) as exc:
            orch.run_mingli_baseline("smfail", output_dir=str(tmp_path))
        assert exc.value.code == 4
        context = _load_json(tmp_path / "runs" / "smfail" / orch.RUN_CONTEXT_NAME)
        assert context["stage"] == "smoke_first_pass"  # 未推进
        assert context["max_cases"] == 10
        assert context["smoke_verdict"]["failures"] == ["x"]


# ---------------------------------------------------------------- 6.6-6.9 共享夹具


def _chart_for_question(q_idx):
    """冻结分布映射：case_19 x 6、case_20 x 4、其余 30 盘 x 5（合计 160）。"""
    remaining = q_idx
    for chart_num in range(1, 33):
        chart = f"case_{chart_num}"
        quota = 6 if chart == "case_19" else 4 if chart == "case_20" else 5
        if remaining <= quota:
            return chart
        remaining -= quota
    raise AssertionError(f"q_idx out of range: {q_idx}")


def _full_main_row(i, terminal_state="parsed", stage="main", **extra):
    """合规 160 行夹具行：带 chart_case_id/thinking_mode/response_model。"""
    cid = f"mingli_ftb_{i:04d}"
    row = _detail_row(
        cid, terminal_state, stage=stage,
        chart_case_id=_chart_for_question(i),
        thinking_mode=("disabled"
                       if terminal_state in ("parsed", "invalid") else None),
        response_model=(None if terminal_state == "call_failed"
                        else orch.FROZEN_MODEL),
    )
    row.update(extra)
    return row


def _retest_row(i, terminal_state="parsed"):
    return _full_main_row(i, terminal_state, stage="controlled_retest")


def _normalized_rows():
    return [{"case_id": f"mingli_ftb_{i:04d}",
             "chart_case_id": _chart_for_question(i)}
            for i in range(1, 161)]


def _completeness_env(root, n_main=160, invalid_ids=(), retest_rows=None,
                      main_events=160, retest_events=0, mutate=None):
    """合成 runs_root 布局：main detail/events + 160 行 normalized dataset
    （+ 可选 retest 产物）。mutate(rows) 在写盘前最后应用。"""
    root = Path(root)
    rows = []
    for i in range(1, n_main + 1):
        cid = f"mingli_ftb_{i:04d}"
        state = "invalid" if cid in invalid_ids else "parsed"
        rows.append(_full_main_row(i, state))
    if mutate is not None:
        rows = mutate(rows)
    _write_jsonl(root / "main" / "detail.jsonl", rows)
    events = [_call_attempt_event(f"mingli_ftb_{(i % max(n_main, 1)) + 1:04d}")
              for i in range(main_events)]
    _write_jsonl(root / "main" / "detail.events.jsonl", events)
    _write_jsonl(root / f"{orch.NORMALIZED_DATASET_NAME}.jsonl", _normalized_rows())
    if retest_rows is not None:
        _write_jsonl(root / "retest" / "detail.jsonl", retest_rows)
    if retest_events:
        _write_jsonl(root / "retest" / "detail.events.jsonl",
                     [_call_attempt_event("mingli_ftb_0001",
                                          stage="controlled_retest")
                      for _ in range(retest_events)])
    return root


def _failed_clauses(result):
    return {c["clause"] for c in result["checks"] if not c["passed"]}


# ---------------------------------------------------------------- 6.6 完整性硬门（§8.1 十二条）


class TestCompletenessHardGates:
    def test_complete_positive(self, tmp_path):
        root = _completeness_env(
            tmp_path, invalid_ids=("mingli_ftb_0159", "mingli_ftb_0160"),
            retest_rows=[_retest_row(159), _retest_row(160)], retest_events=2)
        result = orch._check_completeness(root)
        assert result["verdict"] == "COMPLETE"
        assert len(result["checks"]) == 12
        assert all(c["passed"] for c in result["checks"])
        stats = result["stats"]
        assert stats["question_id_count"] == 160
        assert stats["chart_case_count"] == 32
        assert stats["chart_distribution"]["case_19"] == 6
        assert stats["chart_distribution"]["case_20"] == 4
        assert stats["parser_rate"] == 158 / 160
        assert stats["attempted"] == 162
        assert stats["response_model_values"] == [orch.FROZEN_MODEL]

    def test_clause1_main_terminal_row_count(self, tmp_path):
        root = _completeness_env(tmp_path, n_main=159)
        result = orch._check_completeness(root)
        assert result["verdict"] == "BLOCKED_INCOMPLETE"
        assert 1 in _failed_clauses(result)

    def test_clause2_unique_case_id_not_160(self, tmp_path):
        def _mutate(rows):
            rows[159] = dict(rows[0])  # ftb_0001 重复，ftb_0160 缺失 → 159 唯一
            return rows
        root = _completeness_env(tmp_path, mutate=_mutate)
        assert 2 in _failed_clauses(orch._check_completeness(root))

    def test_clause3_duplicate_case_id(self, tmp_path):
        def _mutate(rows):
            rows[159] = dict(rows[0])
            return rows
        root = _completeness_env(tmp_path, mutate=_mutate)
        assert 3 in _failed_clauses(orch._check_completeness(root))

    def test_clause4_chart_distribution(self, tmp_path):
        # detail 与 normalized 同步把 ftb_0001 从 case_1 挪到 case_2：
        # 分布破坏但 join 仍一致（隔离第 4 条）
        root = _completeness_env(
            tmp_path,
            mutate=lambda rows: [
                dict(r, chart_case_id="case_2")
                if r["case_id"] == "mingli_ftb_0001" else r
                for r in rows])
        norm = _load_jsonl(root / f"{orch.NORMALIZED_DATASET_NAME}.jsonl")
        for r in norm:
            if r["case_id"] == "mingli_ftb_0001":
                r["chart_case_id"] = "case_2"
        _write_jsonl(root / f"{orch.NORMALIZED_DATASET_NAME}.jsonl", norm)
        result = orch._check_completeness(root)
        assert 4 in _failed_clauses(result)
        assert 12 not in _failed_clauses(result)

    def test_clause5_terminal_state_enum(self, tmp_path):
        root = _completeness_env(
            tmp_path,
            mutate=lambda rows: [
                dict(r, terminal_state="unresolved", correct=False)
                if i == 0 else r
                for i, r in enumerate(rows)])
        result = orch._check_completeness(root)
        assert 5 in _failed_clauses(result)

    def test_clause6_first_pass_denominator(self, tmp_path):
        def _mutate(rows):
            key = list(rows[0]["attempt_key"])
            key[3] = "dual"  # 非 main stage → first_pass 分母 159
            rows[0] = dict(rows[0], attempt_key=key)
            return rows
        root = _completeness_env(tmp_path, mutate=_mutate)
        result = orch._check_completeness(root)
        assert 6 in _failed_clauses(result)
        assert 1 not in _failed_clauses(result)

    def test_clause7_retest_once_and_subset(self, tmp_path):
        # (a) 同题复测 2 次
        root_a = _completeness_env(
            tmp_path / "a", invalid_ids=("mingli_ftb_0159",),
            retest_rows=[_retest_row(159), _retest_row(159)], retest_events=2)
        assert 7 in _failed_clauses(orch._check_completeness(root_a))
        # (b) 复测题不在 main invalid/call_failed 集合内
        root_b = _completeness_env(
            tmp_path / "b", invalid_ids=(),
            retest_rows=[_retest_row(1)], retest_events=1)
        assert 7 in _failed_clauses(orch._check_completeness(root_b))

    def test_clause8_global_budget_exceeded(self, tmp_path):
        root = _completeness_env(
            tmp_path, invalid_ids=("mingli_ftb_0159", "mingli_ftb_0160"),
            retest_rows=[_retest_row(159), _retest_row(160)],
            retest_events=21)  # 160 + 21 = 181 > 180
        assert 8 in _failed_clauses(orch._check_completeness(root))

    def test_clause9_merged_details_sha(self, tmp_path):
        root = _completeness_env(tmp_path)
        merged = root / "merged_details.jsonl"
        _write_jsonl(merged, _load_jsonl(root / "main" / "detail.jsonl"))
        # (a) audit index 记录的 SHA 漂移
        bad = orch._check_completeness(
            root, merged_details_path=merged,
            audit_index={"merged_details_sha256": "0" * 64})
        assert 9 in _failed_clauses(bad)
        # (b) audit index 缺失记录字段
        missing = orch._check_completeness(
            root, merged_details_path=merged, audit_index={})
        assert 9 in _failed_clauses(missing)
        # (c) 记录一致 → COMPLETE
        good = {"merged_details_sha256": orch._sha256_file(merged)}
        ok = orch._check_completeness(
            root, merged_details_path=merged, audit_index=good)
        assert ok["verdict"] == "COMPLETE"

    def test_clause10_thinking_mode_not_disabled(self, tmp_path):
        root = _completeness_env(
            tmp_path,
            mutate=lambda rows: [
                dict(r, thinking_mode="enabled") if i == 5 else r
                for i, r in enumerate(rows)])
        assert 10 in _failed_clauses(orch._check_completeness(root))

    def test_clause11_response_model_drift(self, tmp_path):
        root = _completeness_env(
            tmp_path,
            mutate=lambda rows: [
                dict(r, response_model="deepseek-v3") if i == 5 else r
                for i, r in enumerate(rows)])
        assert 11 in _failed_clauses(orch._check_completeness(root))

    def test_clause12_chart_case_id_join(self, tmp_path):
        # (a) detail 行 chart_case_id 与 normalized join 错位
        root_a = _completeness_env(
            tmp_path / "a",
            mutate=lambda rows: [
                dict(r, chart_case_id="case_10") if i == 7 else r
                for i, r in enumerate(rows)])
        assert 12 in _failed_clauses(orch._check_completeness(root_a))
        # (b) detail 行 case_id 在 normalized 中不存在
        root_b = _completeness_env(
            tmp_path / "b",
            mutate=lambda rows: [
                dict(r, case_id="mingli_ftb_9999") if i == 7 else r
                for i, r in enumerate(rows)])
        assert 12 in _failed_clauses(orch._check_completeness(root_b))


# ---------------------------------------------------------------- 6.7 receipt + 原子发布


def _finalize_env(tmp_path, run_id="fin", incomplete=False):
    """完整 runs_root（manifest/context + 合规产物），无需 runner 即可 finalize。"""
    runs_root, context = orch._prepare_run_context(str(tmp_path), run_id, False)
    _completeness_env(
        runs_root,
        n_main=159 if incomplete else 160,
        invalid_ids=() if incomplete else ("mingli_ftb_0159", "mingli_ftb_0160"),
        retest_rows=None if incomplete else [_retest_row(159), _retest_row(160)],
        retest_events=0 if incomplete else 2)
    context["stage"] = orch.STAGE_FINALIZE
    context["smoke_verdict"] = {"passed": True, "failures": []}
    orch._save_context(runs_root, context)
    return runs_root, context


class TestReceiptAtomicPublish:
    def test_publish_roundtrip(self, tmp_path):
        payload = json.dumps({"stage": "baseline"}).encode("utf-8")
        orch._publish_receipt_atomic(
            tmp_path, orch.RECEIPT_FILENAME,
            validated_bytes=payload,
            expected_sha256=hashlib.sha256(payload).hexdigest())
        receipt = tmp_path / orch.RECEIPT_FILENAME
        assert receipt.exists()
        assert receipt.read_bytes() == payload
        assert not list(tmp_path.glob("*.tmp"))

    def test_publish_requires_validated_bytes(self, tmp_path):
        with pytest.raises(SystemExit):
            orch._publish_receipt_atomic(tmp_path, orch.RECEIPT_FILENAME)
        assert not (tmp_path / orch.RECEIPT_FILENAME).exists()

    def test_publish_sha_mismatch_rejected_tmp_cleaned(self, tmp_path):
        payload = b'{"stage": "baseline"}'
        with pytest.raises(SystemExit):
            orch._publish_receipt_atomic(
                tmp_path, orch.RECEIPT_FILENAME,
                validated_bytes=payload, expected_sha256="0" * 64)
        assert not (tmp_path / orch.RECEIPT_FILENAME).exists()
        assert not list(tmp_path.glob("*.tmp"))

    def test_corruption_hook_rejected_tmp_cleaned(self, tmp_path, monkeypatch):
        """monkeypatch 使 tmp 写入后的 SHA 校验读到被篡改的字节。"""
        calls = []
        real = orch._sha256_file

        def _hooked(path):
            calls.append(str(path))
            if str(path).endswith(".tmp"):
                return "f" * 64  # 模拟写入后字节被篡改
            return real(path)

        monkeypatch.setattr(orch, "_sha256_file", _hooked)
        payload = b'{"stage": "baseline"}'
        with pytest.raises(SystemExit):
            orch._publish_receipt_atomic(
                tmp_path, orch.RECEIPT_FILENAME,
                validated_bytes=payload,
                expected_sha256=hashlib.sha256(payload).hexdigest())
        # (a) hook 确实被触发（tmp 路径被校验）
        assert any(p.endswith(".tmp") for p in calls)
        # (b) 发布被拒且 tmp 被清理
        assert not list(tmp_path.glob("*.tmp"))
        # (c) 目标 receipt 不存在
        assert not (tmp_path / orch.RECEIPT_FILENAME).exists()

    def test_finalize_publishes_full_receipt(self, tmp_path):
        runs_root, context = _finalize_env(tmp_path)
        orch._execute_finalize(runs_root, context)
        receipt = _load_json(runs_root / orch.RECEIPT_FILENAME)
        for field in orch.RECEIPT_REQUIRED_FIELDS:
            assert field in receipt, field
        assert receipt["model_label"] == "DeepSeek-V4-Flash non-thinking"
        assert receipt["completeness_verdict"] == "COMPLETE"
        assert receipt["smoke_size"] == 10
        assert receipt["question_id_count"] == 160
        assert receipt["chart_case_count"] == 32
        assert receipt["parser_rate"] == 158 / 160
        assert receipt["first_pass_accuracy"] == 158 / 160
        assert receipt["scheduled_calls"] == 160
        assert receipt["hard_cap"] == 180
        assert receipt["attempted"] == 162
        assert receipt["response_model_values"] == [orch.FROZEN_MODEL]
        assert receipt["response_model_missing_count"] == 0
        assert receipt["pinned_commit"] == orch._pinned_commit()
        for flag in ("rag", "fewshot", "apb", "shuffle_options"):
            assert receipt[flag] is False
        saved = _load_json(runs_root / orch.RUN_CONTEXT_NAME)
        assert saved["stage"] == "published"
        # audit index：逐项硬门结果 + 产物 SHA + run context
        archive = Path(receipt["archive_dir"])
        audit_path = archive / orch.AUDIT_INDEX_NAME
        audit = _load_json(audit_path)
        assert orch._sha256_file(audit_path) == receipt["audit_index_sha256"]
        assert audit["merged_details_sha256"] == \
            orch._sha256_file(archive / orch.MERGED_DETAILS_NAME)
        assert all(c["passed"] for c in audit["completeness_checks"])
        assert len(audit["completeness_checks"]) == 12
        assert audit["artifact_sha256"]["main_detail_sha256"] == \
            orch._sha256_file(archive / "main" / "detail.jsonl")
        assert audit["artifact_sha256"]["retest_detail_sha256"] == \
            orch._sha256_file(archive / "retest" / "detail.jsonl")
        assert audit["run_context"]["run_id"] == context["run_id"]
        assert audit["smoke_size"] == 10

    def test_finalize_blocked_incomplete_no_receipt(self, tmp_path):
        runs_root, context = _finalize_env(tmp_path, incomplete=True)
        with pytest.raises(SystemExit) as exc:
            orch._execute_finalize(runs_root, context)
        assert exc.value.code == 4
        assert not (runs_root / orch.RECEIPT_FILENAME).exists()
        assert not (runs_root / orch.ARCHIVE_DIR_NAME).exists()
        saved = _load_json(runs_root / orch.RUN_CONTEXT_NAME)
        assert saved["completeness"]["verdict"] == "BLOCKED_INCOMPLETE"
        assert saved["stage"] == "finalize"  # 未推进到 published

    def test_audit_index_drift_before_publish_blocks(self, tmp_path, monkeypatch):
        runs_root, context = _finalize_env(tmp_path, "fin-drift")
        original = orch._create_archive

        def _tamper(rr, ctx, completeness):
            result = original(rr, ctx, completeness)
            Path(result["audit_index_path"]).write_text("{}", encoding="utf-8")
            return result

        monkeypatch.setattr(orch, "_create_archive", _tamper)
        with pytest.raises(SystemExit) as exc:
            orch._execute_finalize(runs_root, context)
        assert exc.value.code == 4
        assert not (runs_root / orch.RECEIPT_FILENAME).exists()

    def test_audit_index_missing_before_publish_blocks(self, tmp_path, monkeypatch):
        runs_root, context = _finalize_env(tmp_path, "fin-missing")
        original = orch._create_archive

        def _remove(rr, ctx, completeness):
            result = original(rr, ctx, completeness)
            Path(result["audit_index_path"]).unlink()
            return result

        monkeypatch.setattr(orch, "_create_archive", _remove)
        with pytest.raises(SystemExit) as exc:
            orch._execute_finalize(runs_root, context)
        assert exc.value.code == 4
        assert not (runs_root / orch.RECEIPT_FILENAME).exists()


# ---------------------------------------------------------------- 6.8 phase7_code_fingerprint


class TestPhase7CodeFingerprint:
    def test_scope_exact_nine_files(self):
        assert orch.PHASE7_CODE_SCOPE == (
            "scripts/phase7_mingli_orchestrator.py",
            "scripts/fetch_mingli_bench.py",
            "benchmark/runners/mingli_bench_adapter.py",
            "benchmark/runners/run_benchmark.py",
            "benchmark/runners/resume_ledger.py",
            "benchmark/runners/profiles.py",
            "benchmark/formatters/mingli_prompt.py",
            "claude_api.py",
            "config.py",
        )

    def test_fingerprint_stable_hex(self):
        fp = orch._phase7_code_fingerprint()
        assert re.fullmatch(r"[0-9a-f]{64}", fp)
        assert fp == orch._phase7_code_fingerprint()

    def test_manifest_and_context_carry_fingerprint(self, tmp_path):
        runs_root, context = orch._prepare_run_context(str(tmp_path), "fp1", False)
        fp = orch._phase7_code_fingerprint()
        manifest = _load_json(runs_root / orch.RUN_MANIFEST_NAME)
        assert manifest["phase7_code_fingerprint"] == fp
        assert context["phase7_code_fingerprint"] == fp
        # resume 侧漂移比对字段集同步覆盖
        assert "phase7_code_fingerprint" in orch.RUN_MANIFEST_IDENTITY_FIELDS

    def test_resume_fingerprint_drift_rejected(self, tmp_path):
        runs_root, _ = orch._prepare_run_context(str(tmp_path), "fp2", False)
        manifest = _load_json(runs_root / orch.RUN_MANIFEST_NAME)
        manifest["phase7_code_fingerprint"] = "0" * 64
        orch._atomic_write_json(runs_root / orch.RUN_MANIFEST_NAME, manifest)
        with pytest.raises(SystemExit) as exc:
            orch.run_mingli_baseline("fp2", resume=True, output_dir=str(tmp_path))
        assert exc.value.code == 2

    def test_four_layer_consistency_and_tamper_rejected(self):
        fp = orch._phase7_code_fingerprint()
        layers = {name: {"phase7_code_fingerprint": fp}
                  for name in ("run_manifest", "run_context",
                               "audit_index", "receipt")}
        orch._validate_four_layer_fingerprint(
            layers["run_manifest"], layers["run_context"],
            layers["audit_index"], layers["receipt"])
        for name in layers:
            tampered = {k: dict(v) for k, v in layers.items()}
            tampered[name] = {"phase7_code_fingerprint": "0" * 64}
            with pytest.raises(SystemExit) as exc:
                orch._validate_four_layer_fingerprint(
                    tampered["run_manifest"], tampered["run_context"],
                    tampered["audit_index"], tampered["receipt"])
            assert exc.value.code == 4, name
            missing = {k: dict(v) for k, v in layers.items()}
            missing[name] = {}
            with pytest.raises(SystemExit) as exc:
                orch._validate_four_layer_fingerprint(
                    missing["run_manifest"], missing["run_context"],
                    missing["audit_index"], missing["receipt"])
            assert exc.value.code == 4, name


# ---------------------------------------------------------------- 6.9 fake-runner 端到端（no-network）


class _FakeRunner:
    """测试内嵌 fake runner：在 subprocess 边界（_run_runner_subprocess）生成
    合规 detail/events。drop_last=True 模拟 main 缺 1 题的硬门失败分支。"""

    def __init__(self, drop_last=False):
        self.cmds = []
        self.drop_last = drop_last

    def __call__(self, cmd):
        self.cmds.append(list(cmd))

        def _val(flag):
            return cmd[cmd.index(flag) + 1]

        detail = Path(_val("--case-details-jsonl"))
        events = detail.with_name(detail.name.replace(".jsonl", ".events.jsonl"))
        stage = _val("--attempt-stage")
        rows, evs = [], []
        if stage == "main":
            max_cases = int(_val("--max-cases"))
            start, end = (1, 10) if max_cases == 10 else (11, 160)
            if self.drop_last and max_cases == 160:
                end = 159
            for i in range(start, end + 1):
                cid = f"mingli_ftb_{i:04d}"
                state = "invalid" if i in (159, 160) else "parsed"
                rows.append(_full_main_row(i, state))
                evs.append(_call_attempt_event(cid))
        else:  # controlled_retest：按 case-ids-file 逐题产出
            selected = json.loads(
                Path(_val("--case-ids-file")).read_text(encoding="utf-8"))
            for cid in selected:
                i = int(cid.rsplit("_", 1)[1])
                rows.append(_retest_row(i, "parsed"))
                evs.append(_call_attempt_event(cid, stage="controlled_retest"))
        mode = "a" if detail.exists() else "w"
        detail.parent.mkdir(parents=True, exist_ok=True)
        with open(detail, mode, encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with open(events, mode, encoding="utf-8") as f:
            for ev in evs:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return None


def _fake_normalized_dataset(runs_root):
    runs_root = Path(runs_root)
    rows = _normalized_rows()
    dataset = runs_root / f"{orch.NORMALIZED_DATASET_NAME}.jsonl"
    _write_jsonl(dataset, rows)
    (runs_root / orch.MAIN_CASE_IDS_NAME).write_text(
        json.dumps([r["case_id"] for r in rows]), encoding="utf-8")
    return dataset


def _no_network_guard(*args, **kwargs):
    raise AssertionError(
        f"network/subprocess access forbidden in no-network test: {args!r}")


class TestFakeRunnerEndToEnd:
    def _install_guards(self, monkeypatch):
        """真实网络/API/真实 runner 入口全部 monkeypatch 为调用即失败。"""
        import socket
        import subprocess

        import claude_api

        from scripts import fetch_mingli_bench
        monkeypatch.setattr(
            claude_api, "call_model_messages_sync_with_meta", _no_network_guard)
        monkeypatch.setattr(subprocess, "run", _no_network_guard)
        monkeypatch.setattr(socket, "create_connection", _no_network_guard)
        monkeypatch.setattr(fetch_mingli_bench, "_git", _no_network_guard)

    def test_full_chain_no_network(self, tmp_path, monkeypatch):
        self._install_guards(monkeypatch)
        fake = _FakeRunner()
        monkeypatch.setattr(orch, "_run_runner_subprocess", fake)
        monkeypatch.setattr(orch, "_ensure_normalized_dataset",
                            _fake_normalized_dataset)
        preflight_calls = []
        monkeypatch.setattr(
            orch, "run_preflight",
            lambda work_dir: preflight_calls.append(work_dir) or 0)
        # preflight -> run 完整链
        assert orch.main(["preflight", "--work-dir", str(tmp_path / "pf")]) == 0
        assert preflight_calls == [str(tmp_path / "pf")]
        out_dir = tmp_path / "out"
        assert orch.main(["run", "--run-id", "e2e1",
                          "--output-dir", str(out_dir)]) == 0

        runs_root = out_dir / "runs" / "e2e1"
        # run context 状态转换记录
        context = _load_json(runs_root / orch.RUN_CONTEXT_NAME)
        assert context["stage"] == "published"
        assert [(t["from"], t["to"])
                for t in context["max_cases_transitions"]] == [(10, 160)]
        assert context["smoke_verdict"]["passed"] is True
        assert context["retest_report"]["retested_case_ids"] == [
            "mingli_ftb_0159", "mingli_ftb_0160"]

        # retest argv 预算参数（allocation = 180 - 160 = 20，eligible = 2）
        retest_cmds = [c for c in fake.cmds
                       if c[c.index("--attempt-stage") + 1] == "controlled_retest"]
        assert len(retest_cmds) == 1
        rc_cmd = retest_cmds[0]
        assert rc_cmd[rc_cmd.index("--scheduled-calls") + 1] == "2"
        assert rc_cmd[rc_cmd.index("--hard-cap") + 1] == "20"
        assert "--ziwei-arm" not in rc_cmd

        # receipt 字段全集
        receipt = _load_json(runs_root / orch.RECEIPT_FILENAME)
        for field in orch.RECEIPT_REQUIRED_FIELDS:
            assert field in receipt, field
        assert receipt["model_label"] == "DeepSeek-V4-Flash non-thinking"
        assert receipt["completeness_verdict"] == "COMPLETE"
        assert receipt["question_id_count"] == 160
        assert receipt["chart_case_count"] == 32
        assert receipt["parser_rate"] == 158 / 160
        assert receipt["smoke_size"] == 10
        assert receipt["attempted"] == 162
        assert receipt["response_model_values"] == [orch.FROZEN_MODEL]
        assert receipt["response_model_missing_count"] == 0
        for flag in ("rag", "fewshot", "apb", "shuffle_options"):
            assert receipt[flag] is False

        # audit index SHA 一致
        archive = Path(receipt["archive_dir"])
        audit_path = archive / orch.AUDIT_INDEX_NAME
        audit = _load_json(audit_path)
        assert orch._sha256_file(audit_path) == receipt["audit_index_sha256"]
        assert audit["merged_details_sha256"] == \
            orch._sha256_file(archive / orch.MERGED_DETAILS_NAME)
        assert audit["artifact_sha256"]["main_detail_sha256"] == \
            orch._sha256_file(archive / "main" / "detail.jsonl")
        assert audit["artifact_sha256"]["main_events_sha256"] == \
            orch._sha256_file(archive / "main" / "detail.events.jsonl")
        assert audit["artifact_sha256"]["retest_detail_sha256"] == \
            orch._sha256_file(archive / "retest" / "detail.jsonl")
        assert all(c["passed"] for c in audit["completeness_checks"])

        # 四层指纹一致且与现算值一致
        fp = orch._phase7_code_fingerprint()
        manifest = _load_json(runs_root / orch.RUN_MANIFEST_NAME)
        assert receipt["phase7_code_fingerprint"] == fp
        assert audit["phase7_code_fingerprint"] == fp
        assert manifest["phase7_code_fingerprint"] == fp
        assert context["phase7_code_fingerprint"] == fp

    def test_hard_gate_failure_exit4_no_receipt(self, tmp_path, monkeypatch):
        self._install_guards(monkeypatch)
        fake = _FakeRunner(drop_last=True)  # main 缺 1 题（159 行）
        monkeypatch.setattr(orch, "_run_runner_subprocess", fake)
        monkeypatch.setattr(orch, "_ensure_normalized_dataset",
                            _fake_normalized_dataset)
        out_dir = tmp_path / "out"
        with pytest.raises(SystemExit) as exc:
            orch.main(["run", "--run-id", "e2e2", "--output-dir", str(out_dir)])
        assert exc.value.code == 4
        runs_root = out_dir / "runs" / "e2e2"
        assert not (runs_root / orch.RECEIPT_FILENAME).exists()
        assert not (runs_root / orch.ARCHIVE_DIR_NAME).exists()
        context = _load_json(runs_root / orch.RUN_CONTEXT_NAME)
        assert context["completeness"]["verdict"] == "BLOCKED_INCOMPLETE"
        assert 1 in {c["clause"] for c in context["completeness"]["checks"]
                     if not c["passed"]}
