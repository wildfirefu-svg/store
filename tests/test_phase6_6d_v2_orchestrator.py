"""Phase 6 6D v2 orchestrator tests - version constants, resume, schedule."""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

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
    _check_completeness,
    _compute_experiment_code_fingerprint,
    _prepare_run_context,
    _run_all_slices,
    _validate_frozen_protocol,
    build_run_manifest,
    check_6d_gate,
    compute_6d_gate,
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


# -- Task 5.5: gate / completeness use on_limited arm --


def _mk(arm, cid, rep, correct):
    return {"attempt_key": ["baziqa_contest8_2024_holdout_enriched",
                            "baziqa_xjz_reasoned", arm, "main", "deepseek",
                            "deepseek-v4-flash", cid, rep, 0, "p0"],
            "case_id": cid, "terminal_state": "parsed", "correct": correct}


def test_gate_uses_on_limited_and_denominator_n3():
    # N=1, REPEATS=3：c1 在 3 个 repeat 中 on_limited 净增 1 题
    # off 只在 rep==0 对（off_correct=1），on_limited 在 rep!=1 对（on_correct=2）
    # case_delta = on_correct - off_correct = 2 - 1 = +1
    # paired_delta = +1 / (N × REPEATS) = +1/3（分母不含条件数 2）
    details = []
    for rep in range(3):
        details.append(_mk("b1a_time_off", "c1", rep, rep == 0))
        details.append(_mk("b1a_time_on_limited", "c1", rep, rep != 1))
    g = compute_6d_gate(details, 1)  # N=1
    # 容忍度 1e-6：compute_6d_gate 对结果 round(..., 6)（v1 继承行为）
    assert abs(g["paired_delta"] - (1 / 3)) < 1e-6   # 分母 N×3，非 N×3×2
    assert abs(g["min_case_delta"] - (1 / 3)) < 1e-6  # min(+1)/3 = +1/3


def test_completeness_rejects_v1_on():
    merged = [_mk("b1a_time_off", "c1", 0, True),
              _mk("b1a_time_on", "c1", 0, True),   # v1 遗留
              _mk("b1a_time_on_limited", "c1", 0, True)]
    # 构造 schedule 期望 c1 有 off+on_limited
    schedule = {"slices": [{"year": "2024", "repeat": 0,
                            "arm": "b1a_time_on_limited", "case_ids": ["c1"]},
                           {"year": "2024", "repeat": 0,
                            "arm": "b1a_time_off", "case_ids": ["c1"]}]}
    r = _check_completeness(merged, schedule)
    assert r != "PASS"


# -- Task 6.7-6.9: run_dev off 复用接线 --

_V1_ARCHIVE = os.path.join(
    PROJECT_ROOT,
    "docs/phase6/6d/phase6-6d-v1-20260808-r1-6d-dev-2026-08-07"
    "-deepseek-deepseek-v4-flash-cc36fefa94c5")
_V1_RUNS = os.path.join(
    PROJECT_ROOT, "docs/phase6/6d/runs/phase6-6d-v1-20260808-r1")


def _mk_row(arm, cid, rep, dataset_id, correct=True):
    # attempt_key 布局：[dataset, profile, arm, stage, provider, model,
    #                    case_id, repeat_idx, sample_idx, permutation]
    return {"attempt_key": [dataset_id, FROZEN_PROFILE, arm, "main",
                            FROZEN_PROVIDER, FROZEN_MODEL, cid, rep, 0, "p0"],
            "case_id": cid, "terminal_state": "parsed", "correct": correct,
            "predicted_answer": "A" if correct else "B",
            "expected_answer": "A"}


def _mk_on_limited_row(cid, slice_info):
    ds = os.path.splitext(os.path.basename(slice_info["dataset_path"]))[0]
    return _mk_row("b1a_time_on_limited", cid, slice_info["repeat"], ds)


def _all_off_rows_from_schedule(schedule):
    # off mock 必须覆盖 schedule 全部 case_ids：每 (case_id, repeat) 一条 off main 行
    rows = []
    for sl in schedule["slices"]:
        if sl.get("source") != "v1_reuse":
            continue
        ds = os.path.splitext(os.path.basename(sl["dataset_path"]))[0]
        for cid in sl["case_ids"]:
            rows.append(_mk_row("b1a_time_off", cid, sl["repeat"], ds))
    return rows


def _install_run_dev_mocks(monkeypatch, tmp_path, off_rows):
    # 4. monkeypatch ARCHIVE_ROOT 到 tmp_path，避免写真仓库
    monkeypatch.setattr(orch, "ARCHIVE_ROOT", str(tmp_path / "archive"))
    calls = []

    def fake_run_slice(slice_info, ledger, provider, model, resume=False):
        # 修法 (b)：真实写 detail/events + 记账，否则 merge 缺 on_limited main
        calls.append(slice_info["slice_id"])
        os.makedirs(slice_info["output_dir"], exist_ok=True)
        with open(slice_info["detail_path"], "w", encoding="utf-8") as f:
            for cid in slice_info["case_ids"]:
                f.write(json.dumps(_mk_on_limited_row(cid, slice_info)) + "\n")
        with open(slice_info["events_path"], "w", encoding="utf-8") as f:
            for _ in range(slice_info["scheduled_calls"]):
                f.write(json.dumps({"kind": "call_attempt"}) + "\n")
        # 1. record_slice_completed 真实签名为三参 (slice_id, actual, scheduled)
        ledger.record_slice_completed(slice_info["slice_id"],
                                      slice_info["scheduled_calls"],
                                      slice_info["scheduled_calls"])
        return {"exit_code": 0,
                "actual_attempts": slice_info["scheduled_calls"]}

    monkeypatch.setattr(orch, "_run_slice", fake_run_slice)
    # 3. off mock 覆盖 schedule 全部 case_ids（31 题 × 3 repeats 每 cell 有 off main）
    monkeypatch.setattr(orch, "_verify_off_reuse", lambda *a, **k: off_rows)
    monkeypatch.setattr(orch, "_validate_frozen_protocol",
                        lambda *a, **k: {"thinking_mode": FROZEN_THINKING_MODE,
                                         "model_label": orch.MODEL_LABEL})
    monkeypatch.setattr(orch, "_validate_phase1_receipt", lambda *a, **k: {})

    def fake_prepare_run_context(output_dir, run_id, resume, run_manifest,
                                 code_fingerprint):
        # 2. mock 需建目录（run_dev 非 resume 路径用 mkstemp(dir=runs_root) 写 manifest）；
        #    另需写 run_context.json，否则 _validate_four_layer_provenance 拒绝
        runs_root = Path(output_dir) / "runs" / run_id
        runs_root.mkdir(parents=True, exist_ok=True)
        context = dict(run_manifest)
        context["experiment_id"] = EXPERIMENT_ID
        context["created_at"] = "2026-08-09T00:00:00"
        (runs_root / "run_context.json").write_text(
            json.dumps(context, ensure_ascii=False), encoding="utf-8")
        return runs_root, context

    monkeypatch.setattr(orch, "_prepare_run_context", fake_prepare_run_context)
    return calls


def test_run_dev_skips_off_reuse_slices(monkeypatch, tmp_path):
    schedule = orch._build_schedule(str(tmp_path / "sched_probe"))
    off_rows = _all_off_rows_from_schedule(schedule)
    calls = _install_run_dev_mocks(monkeypatch, tmp_path, off_rows)
    orch.run_dev(FROZEN_PROVIDER, FROZEN_MODEL, str(tmp_path), run_id="r1",
                 v1_archive_dir=_V1_ARCHIVE, v1_runs_dir=_V1_RUNS,
                 resume=False)
    off_ids = [c for c in calls if "b1a_time_off" in c]
    assert len(off_ids) == 0, "off (v1_reuse) slices must not be executed"
    assert len(calls) == 15
    assert all("b1a_time_on_limited" in c for c in calls)


def test_run_dev_merged_includes_off(monkeypatch, tmp_path):
    schedule = orch._build_schedule(str(tmp_path / "sched_probe"))
    off_rows = _all_off_rows_from_schedule(schedule)
    _install_run_dev_mocks(monkeypatch, tmp_path, off_rows)
    result = orch.run_dev(FROZEN_PROVIDER, FROZEN_MODEL, str(tmp_path),
                          run_id="r2", v1_archive_dir=_V1_ARCHIVE,
                          v1_runs_dir=_V1_RUNS, resume=False)
    merged_path = Path(result["archive"]["archive_dir"]) / "merged_details.jsonl"
    rows = [json.loads(l) for l in
            merged_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    arms = defaultdict(int)
    for r in rows:
        arms[(r.get("attempt_key") or [None] * 10)[2]] += 1
    assert arms["b1a_time_off"] == 93       # 来自 v1 复用
    assert arms["b1a_time_on_limited"] == 93  # 来自 fake_run_slice 写入
    # 6.6：receipt/audit 携带 off provenance
    receipt = result["archive"]["receipt"]
    expected_source = f"6d-v1:{os.path.basename(_V1_ARCHIVE)}"
    assert receipt["off_source"] == expected_source
    # off_merged_details_sha256 计算方式锁定：_canonical_dict_sha256(off 行列表)
    assert receipt["off_merged_details_sha256"] == \
        orch._canonical_dict_sha256(off_rows)
    audit = result["archive"]["audit"]
    assert audit["off_source"] == expected_source
    assert audit["off_merged_details_sha256"] == \
        receipt["off_merged_details_sha256"]
    report_md = (tmp_path / "runs" / "r2" / "dev" / "report.md").read_text(
        encoding="utf-8")
    assert expected_source in report_md
    # 6.5：ledger cap = on_limited 臂 hard_cap 合计（243），非双臂 486
    summary = json.loads(
        (tmp_path / "runs" / "r2" / "dev" / "summary.json").read_text(
            encoding="utf-8"))
    assert summary["run"]["global_hard_cap"] == 243


def test_run_dev_off_reuse_fail_blocks(monkeypatch, tmp_path):
    # off 校验在 _run_all_slices 之前短路：无需 4 处夹具修正
    calls = []
    monkeypatch.setattr(
        orch, "_run_slice",
        lambda slice_info, *a, **k: calls.append(slice_info["slice_id"]))
    monkeypatch.setattr(orch, "_validate_frozen_protocol",
                        lambda *a, **k: {"thinking_mode": FROZEN_THINKING_MODE,
                                         "model_label": orch.MODEL_LABEL})
    monkeypatch.setattr(orch, "_validate_phase1_receipt", lambda *a, **k: {})

    def boom(*a, **k):
        raise SystemExit("off reuse reject: simulated drift")

    monkeypatch.setattr(orch, "_verify_off_reuse", boom)
    with pytest.raises(SystemExit) as exc:
        orch.run_dev(FROZEN_PROVIDER, FROZEN_MODEL, str(tmp_path), run_id="r3",
                     v1_archive_dir=_V1_ARCHIVE, v1_runs_dir=_V1_RUNS,
                     resume=False)
    assert exc.value.code == 2
    assert calls == [], "off reuse precheck failure must not consume any API"
    assert not (tmp_path / "runs").exists(), "precheck fails before run setup"
