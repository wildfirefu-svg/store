from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase6_6a0_ablation import (
    PROFILE_ID,
    AblationConfig,
    BudgetLedger,
    SliceRun,
    aggregate_delta,
    build_schedule,
    gate_verdict,
    offline_gate,
    run_ablation,
    split_ab_ba,
)
from tests.phase6_helpers import RunnerSpy, fake_config, write_jsonl

CASE_IDS = [f"c{i}" for i in range(40)]


def test_split_ab_ba_deterministic_and_disjoint():
    a1, b1 = split_ab_ba(CASE_IDS, seed=20260717)
    a2, b2 = split_ab_ba(CASE_IDS, seed=20260717)
    assert (a1, b1) == (a2, b2)
    assert len(a1) == len(b1) == 20
    assert set(a1).isdisjoint(set(b1))
    assert set(a1) | set(b1) == set(CASE_IDS)


def test_build_schedule_full_sequence():
    """阻 1：逐切片断言 (purpose, repeat, arm, group, case_ids, scheduled, cap) 全序列。"""
    config = fake_config()
    group_a, group_b = split_ab_ba(CASE_IDS, seed=config.seed)
    schedule = build_schedule(config, CASE_IDS)
    assert len(schedule) == 13                      # 1 smoke + 3 repeats × 4 切片

    s = schedule[0]
    assert (s.purpose, s.repeat_idx, s.arm, s.group) == ("smoke", -1, "ctx_approved", "smoke")
    assert s.case_ids == group_a                    # smoke 用 group_a 20 题（canary 复测）
    assert (s.scheduled_calls, s.hard_cap) == (20, 20)

    expected_order = [("ctx_approved", "group_a"), ("ctx_legacy", "group_a"),
                      ("ctx_legacy", "group_b"), ("ctx_approved", "group_b")]
    expected_caps = [23, 23, 22, 22]
    for repeat in range(3):
        for j, ((arm, group), cap) in enumerate(zip(expected_order, expected_caps)):
            s = schedule[1 + repeat * 4 + j]
            assert (s.purpose, s.repeat_idx, s.arm, s.group) == ("main", repeat, arm, group)
            assert s.case_ids == (group_a if group == "group_a" else group_b)
            assert (s.scheduled_calls, s.hard_cap) == (20, cap)


def test_build_schedule_cap_sums():
    schedule = build_schedule(fake_config(), CASE_IDS)
    main_caps = [s.hard_cap for s in schedule if s.purpose == "main"]
    assert len(main_caps) == 12
    assert sum(main_caps) == 270
    assert sum(main_caps) + schedule[0].hard_cap == 290 == fake_config().stage_hard_cap
    assert sum(s.scheduled_calls for s in schedule) == 260 == fake_config().stage_scheduled


def test_build_schedule_requires_40_cases():
    with pytest.raises(ValueError):
        build_schedule(fake_config(), CASE_IDS[:39])


@pytest.mark.parametrize("delta,expected", [
    (2.0, "ADOPT"), (5.0, "ADOPT"),
    (1.99, "ADOPT_FOUNDATION"), (0.0, "ADOPT_FOUNDATION"),
    (-0.01, "ROLLBACK"), (-7.5, "ROLLBACK"),
])
def test_gate_verdict_boundaries(delta, expected):
    assert gate_verdict(delta) == expected


def test_run_ablation_invokes_slices_in_order(tmp_path):
    config = fake_config(root=tmp_path)
    spy = RunnerSpy()
    schedule = build_schedule(config, CASE_IDS)
    run_ablation(config, schedule, slice_runner=spy)   # schedule 由调用方构建传入
    assert len(spy.calls) == 13
    for call, expected in zip(spy.calls, schedule):
        assert call.slice == expected
        assert call.kwargs["hard_cap"] == expected.hard_cap
        assert call.kwargs["scheduled_calls"] == expected.scheduled_calls


def test_run_ablation_smoke_schedule_single_call(tmp_path):
    """阻 1：--smoke-only 语义——传入 smoke schedule 时只执行 1 个切片（函数内不得重建）。"""
    config = fake_config(root=tmp_path)
    spy = RunnerSpy()
    smoke_schedule = [s for s in build_schedule(config, CASE_IDS) if s.purpose == "smoke"]
    assert len(smoke_schedule) == 1
    result = run_ablation(config, smoke_schedule, slice_runner=spy)
    assert len(spy.calls) == 1
    assert spy.calls[0].slice.purpose == "smoke"
    assert result["status"] == "OK"


def test_smoke_attempt_keys_disjoint_from_main(tmp_path):
    """阻 2：smoke（repeat_idx=-1）与 12 个主切片的 attempt key 集合不相交。"""
    from benchmark.runners.run_benchmark import build_attempt_key

    config = fake_config(root=tmp_path)
    schedule = build_schedule(config, CASE_IDS)

    def keys_for(slice_run):
        return {
            build_attempt_key("baziqa", PROFILE_ID, slice_run.arm, "main",
                              config.provider, config.model, cid,
                              slice_run.repeat_idx, 0, "p0")
            for cid in slice_run.case_ids
        }

    smoke_keys = keys_for(schedule[0])
    assert smoke_keys
    for s in schedule[1:]:
        assert smoke_keys.isdisjoint(keys_for(s)), (
            f"smoke 与 {s.arm}/{s.group}/r{s.repeat_idx} 键碰撞")


class _FailingSpy(RunnerSpy):
    def __init__(self, fail_at: int):
        super().__init__()
        self.fail_at = fail_at

    def __call__(self, slice_run, **kwargs):
        super().__call__(slice_run, **kwargs)
        code = 3 if len(self.calls) == self.fail_at else 0
        return type("ArmRunResult", (), {"exit_code": code, "records": [],
                                         "calls_attempted": 0})


def test_run_ablation_aborts_on_blocked_incomplete(tmp_path):
    config = fake_config(root=tmp_path)
    spy = _FailingSpy(fail_at=2)
    result = run_ablation(config, build_schedule(config, CASE_IDS), slice_runner=spy)
    assert len(spy.calls) == 2                      # 第 2 切片退出码 3 → 后续切片不执行
    assert result["status"] == "BLOCKED_INCOMPLETE"


def test_stage_budget_ledger_overflow_aborts(tmp_path):
    """阻 3：阶段总账本——已记账额度 + 下一切片剩余 cap 超过阶段 hard_cap 即中止，不发起任何调用。"""
    config = fake_config(root=tmp_path)
    ledger_path = tmp_path / "budget" / f"{config.run_id}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps({"external_prior": {"hard_cap": 280, "calls_attempted": 280,
                                       "timestamp": "2026-07-17T00:00:00"}}),
        encoding="utf-8")
    spy = RunnerSpy()
    result = run_ablation(config, build_schedule(config, CASE_IDS), slice_runner=spy)
    assert spy.calls == []                          # 首切片即中止
    assert result["status"] == "FAILED"
    assert "budget" in result["reason"]


class _CountingSpy(RunnerSpy):
    """按切片 scheduled_calls 报告实际调用数（模拟真实跑满且无重试的切片）。"""

    def __call__(self, slice_run, **kwargs):
        super().__call__(slice_run, **kwargs)
        return type("ArmRunResult", (), {"exit_code": 0, "records": [],
                                         "calls_attempted": slice_run.scheduled_calls})


def test_stage_ledger_idempotent_smoke_then_full(tmp_path):
    """v4 阻 1：smoke-only 后接全量，smoke 切片额度按 slice_id 幂等，不重复累计。"""
    config = fake_config(root=tmp_path)
    schedule = build_schedule(config, CASE_IDS)
    spy = _CountingSpy()
    smoke_schedule = [s for s in schedule if s.purpose == "smoke"]
    assert run_ablation(config, smoke_schedule, slice_runner=spy)["status"] == "OK"
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    smoke_id = "smoke_-1_ctx_approved_smoke"
    assert ledger.attempted_for(smoke_id) == 20
    assert ledger.total_attempted() == 20
    assert run_ablation(config, schedule, slice_runner=spy)["status"] == "OK"
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    assert ledger.attempted_for(smoke_id) == 20     # 不变成 40
    assert ledger.total_attempted() == 260          # 13 切片 × 20，smoke 不重复计


def test_stage_ledger_resume_no_phantom_overflow(tmp_path):
    """v4 阻 1：完整实验再次 resume，阶段总数不变，不误报 overflow。"""
    config = fake_config(root=tmp_path)
    schedule = build_schedule(config, CASE_IDS)
    spy = _CountingSpy()
    assert run_ablation(config, schedule, slice_runner=spy)["status"] == "OK"
    first = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl").total_attempted()
    assert first == 260
    # 再次"resume"：各切片报告相同累计值，启动前检查只按剩余额度预占
    assert run_ablation(config, schedule, slice_runner=spy)["status"] == "OK"
    assert BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl").total_attempted() == first


def test_stage_ledger_corrupt_json_blocked(tmp_path):
    """v5 阻 2：账本 JSON 损坏 → fail-closed（BLOCKED_INCOMPLETE），不发起任何调用。"""
    config = fake_config(root=tmp_path)
    ledger_path = tmp_path / "budget" / f"{config.run_id}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("{not json", encoding="utf-8")
    spy = RunnerSpy()
    result = run_ablation(config, build_schedule(config, CASE_IDS), slice_runner=spy)
    assert spy.calls == []
    assert result["status"] == "BLOCKED_INCOMPLETE"
    assert "budget ledger corrupt" in result["reason"]


def test_stage_ledger_over_cap_record_blocked(tmp_path):
    """v5 阻 2：calls_attempted > hard_cap 的账本记录 → fail-closed（负值/结构错误同路径）。"""
    config = fake_config(root=tmp_path)
    ledger_path = tmp_path / "budget" / f"{config.run_id}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps({
        "main_0_ctx_approved_group_a": {"hard_cap": 23, "calls_attempted": 24,
                                        "timestamp": "2026-07-17T00:00:00"}}),
        encoding="utf-8")
    spy = RunnerSpy()
    result = run_ablation(config, build_schedule(config, CASE_IDS), slice_runner=spy)
    assert spy.calls == []
    assert result["status"] == "BLOCKED_INCOMPLETE"
    assert "budget ledger corrupt" in result["reason"]


def test_stage_ledger_atomic_write(tmp_path):
    """v5 阻 2：账本经临时文件 + os.replace 原子替换，无 .tmp 残留；覆盖语义保持幂等。"""
    config = fake_config(root=tmp_path)
    ledger = BudgetLedger(tmp_path / "budget" / f"{config.run_id}.jsonl")
    ledger.record("s1", 23, 20)
    ledger.record("s1", 23, 21)                          # 同 slice_id 覆盖
    assert not (tmp_path / "budget" / f"{config.run_id}.jsonl.tmp").exists()
    assert ledger.attempted_for("s1") == 21
    assert ledger.total_attempted() == 21


def detail_row(case_id, correct, repeat_idx, arm):
    return {"case_id": case_id, "correct": correct, "repeat_idx": repeat_idx,
            "arm": arm, "terminal_state": "parsed"}


def test_aggregate_delta_and_verdict():
    rows = []
    for repeat in range(3):
        for i in range(20):
            rows.append(detail_row(f"a{i}", i < 12, repeat, "ctx_approved"))   # 60%
            rows.append(detail_row(f"b{i}", i < 12, repeat, "ctx_approved"))
            rows.append(detail_row(f"a{i}", i < 10, repeat, "ctx_legacy"))     # 50%
            rows.append(detail_row(f"b{i}", i < 10, repeat, "ctx_legacy"))
    agg = aggregate_delta(rows, repeats=3)
    assert agg["per_repeat_delta_pp"] == [10.0, 10.0, 10.0]
    assert agg["delta_dev_pp"] == 10.0
    assert agg["verdict"] == "ADOPT"


def _write_enriched(path: Path, case_ids, leak: str | None = None):
    fixture = json.loads((PROJECT_ROOT / "tests" / "fixtures" / "phase6" / "case_sample_1.json")
                         .read_text(encoding="utf-8"))
    rows = []
    for cid in case_ids:
        row = json.loads(json.dumps(fixture))
        row["case_id"] = cid
        if leak:
            row["question"] = row["question"] + leak
        rows.append(row)
    write_jsonl(path, rows)


def test_offline_gate_passes_and_detects_leak(tmp_path):
    enriched = tmp_path / "enriched.jsonl"
    _write_enriched(enriched, ["c0", "c1"])
    config = fake_config(root=tmp_path, enriched_path=enriched)
    assert offline_gate(config) == []
    _write_enriched(enriched, ["c0", "c1"], leak="（正确答案：B）")
    failures = offline_gate(config)
    assert any("leak" in f or "泄漏" in f for f in failures)


def _runner_real_row(case_id, correct, repeat_idx, arm):
    """真实 runner detail 行形状（Task 10 smoke 实测）：arm/repeat_idx 只在 attempt_key 内。"""
    return {
        "case_id": case_id,
        "correct": correct,
        "terminal_state": "parsed",
        "attempt_key": ["ds", PROFILE_ID, arm, "main", "deepseek", "deepseek-chat",
                        case_id, repeat_idx, 0, "p0"],
    }


def test_write_report_normalizes_runner_real_rows(tmp_path, monkeypatch):
    # 执行期修正（Task 10）：smoke 真实产物证明 runner 不写顶层 arm/repeat_idx；
    # write_report 必须从目录臂 + attempt_key[7] 归一化，否则聚合在 260 次调用后空集报错。
    import scripts.run_phase6_6a0_ablation as mod
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    enriched = tmp_path / "enriched.jsonl"
    _write_enriched(enriched, CASE_IDS)
    config = fake_config(root=tmp_path, enriched_path=enriched, run_id="realrows")
    group_a, group_b = split_ab_ba(CASE_IDS, config.seed)
    for arm, hit in (("ctx_approved", 12), ("ctx_legacy", 10)):
        rows = []
        for repeat in range(3):
            for i, cid in enumerate(group_a):
                rows.append(_runner_real_row(cid, i < hit, repeat, arm))
            for i, cid in enumerate(group_b):
                rows.append(_runner_real_row(cid, i < hit, repeat, arm))
        rows.append(_runner_real_row(group_a[0], True, -1, arm))  # smoke 行不得进主指标
        d = tmp_path / arm / "runs" / config.run_id / "slice_main_0_group_x"
        d.mkdir(parents=True)
        write_jsonl(d / "detail.jsonl", rows)
    summary = mod.write_report(config, CASE_IDS)
    assert summary["per_repeat_delta_pp"] == [10.0, 10.0, 10.0]
    assert summary["delta_dev_pp"] == 10.0
    assert summary["verdict"] == "ADOPT"
    assert (tmp_path / "docs" / "phase6" / "realrows" / "summary.json").exists()
