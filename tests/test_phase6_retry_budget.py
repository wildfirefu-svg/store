from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.run_benchmark import compute_hard_cap
from tests.phase6_helpers import RunnerEnv


@pytest.mark.parametrize("scheduled,expected", [
    (260, 290), (820, 910), (720, 800), (3600, 3960),
    (960, 1060), (3840, 4230), (480, 530), (1920, 2120),
])
def test_compute_hard_cap_design_values(scheduled, expected):
    assert compute_hard_cap(scheduled) == expected


def test_retry_then_success(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_fails(1)                       # 第 1 次失败，第 2 次成功
    assert env.run(profile="baziqa_xjz_direct") == 0
    assert len(env.read_events("model_call_failed")) == 1
    assert len(env.read_events("call_attempt")) == 2   # 失败 1 次 + 成功 1 次均记账
    assert env.read_detail()[0]["terminal_state"] == "parsed"


def test_retry_exhausted_call_failed(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_fails(3)                       # 3 次网络尝试全部失败
    assert env.run(profile="baziqa_xjz_direct") == 0
    events = env.read_events("model_call_failed")
    assert [e["retry_idx"] for e in events] == [1, 2, 3]
    assert len(env.read_events("call_attempt")) == 3   # 每次失败调用前均已记账
    row = env.read_detail()[0]
    assert row["terminal_state"] == "call_failed"
    assert row["correct"] is False           # call_failed 按错误计入分母


def test_retry_ledger_survives_crash_and_resume(tmp_path, monkeypatch):
    # 执行偏离（Task 6 预登记，Task 7 落实）：计划原文两处断言为 call_attempt==2 / ==3，
    # 与 Task 6 锁死的 Policy A（先记账后调用，崩溃当次也记账）矛盾——
    # 本测试与 test_calls_attempted_restored_across_resume 在任何单一记账策略下都不能
    # 同时成立，Policy A 由 test_resume_first_crash_artifacts_guard 锁定，故修正为 3 / 4。
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_fails_then_crash(2)            # 2 次网络失败后进程崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct")
    assert [e["retry_idx"] for e in env.read_events("model_call_failed")] == [1, 2]
    assert env.read_detail() == []           # 无终态
    assert len(env.read_events("call_attempt")) == 3   # 失败 2 次 + 崩溃当次均已记账（Policy A）
    env.model_fails(1)                       # resume：第 3 次（最后额度）仍失败
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0
    assert [e["retry_idx"] for e in env.read_events("model_call_failed")] == [1, 2, 3]
    assert len(env.read_events("call_attempt")) == 4   # 跨 resume 累计，不重置（Policy A）
    assert env.read_detail()[0]["terminal_state"] == "call_failed"


def test_hard_cap_exhausted_blocked_incomplete(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
    env.model_fails(100)                     # 所有调用都失败
    code = env.run(profile="baziqa_xjz_direct", scheduled_calls=2, hard_cap=4)
    assert code == 3
    summary = env.read_summary()
    assert summary["status"] == "BLOCKED_INCOMPLETE"
    assert summary["calls_attempted"] == 4   # 先记账后调用，耗尽即停


def test_calls_attempted_restored_across_resume(tmp_path, monkeypatch):
    """hard cap 跨 resume 持久化：成功调用同样记账；崩溃 attempt 已消耗额度，
    resume 后不得因计数器归零而获得新额度。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=3)
    env.model_succeeds_then_crash("A", successes=2)   # c1、c2 成功；c3 调用时进程崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct",
                         scheduled_calls=3, hard_cap=3)
    assert len(env.read_events("call_attempt")) == 3   # c3 的 attempt 已发起并记账
    assert len(env.read_detail()) == 2                 # 仅 c1、c2 终态
    env.model_returns("A")
    code = env.run(profile="baziqa_xjz_direct", resume=True,
                   scheduled_calls=3, hard_cap=3)
    assert code == 3                                   # 额度已耗尽 → BLOCKED_INCOMPLETE
    summary = env.read_summary()
    assert summary["status"] == "BLOCKED_INCOMPLETE"
    assert summary["calls_attempted"] == 3             # 从事件恢复，未归零
    assert len(env.read_events("call_attempt")) == 3   # 无新增调用
    assert len(env.read_detail()) == 2                 # c3 未再执行
