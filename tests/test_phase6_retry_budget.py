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
    # 与 Task 6 锁死的 Policy A（先记账后调用，崩溃当次也记账）矛盾--
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


def test_truncation_retry_once_then_success(tmp_path, monkeypatch):
    """finish_reason != 'stop' 截断：窄重试 1 次，第 2 次成功则正常返回。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_truncates(1)                   # 第 1 次截断，第 2 次成功
    assert env.run(profile="baziqa_xjz_direct") == 0
    # 截断记 1 次 model_call_failed（retry_idx=None，独立预算）
    fails = env.read_events("model_call_failed")
    assert len(fails) == 1
    assert fails[0]["retry_idx"] is None
    assert "truncated_response" in fails[0]["error_type"]
    # 2 次 call_attempt（截断 1 次 + 成功 1 次）
    assert len(env.read_events("call_attempt")) == 2
    row = env.read_detail()[0]
    assert row["terminal_state"] == "parsed"
    assert row["finish_reason"] == "stop"    # 最终成功的 meta 注入 detail


def test_truncation_budget_exhausted_call_failed(tmp_path, monkeypatch):
    """截断重试 1 次后仍截断 -> truncation budget exhausted -> call_failed。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_truncates(100)                 # 每次都截断
    assert env.run(profile="baziqa_xjz_direct") == 0
    fails = env.read_events("model_call_failed")
    assert len(fails) == 2                   # 截断 2 次（1 次重试额度耗尽）
    assert all(f["retry_idx"] is None for f in fails)
    assert len(env.read_events("call_attempt")) == 2
    row = env.read_detail()[0]
    assert row["terminal_state"] == "call_failed"


def test_truncation_does_not_consume_network_retry_budget(tmp_path, monkeypatch):
    """截断重试独立计数：截断后仍允许 3 次网络重试（互不消耗）。

    脚本：1 次截断 + 2 次网络失败 + 1 次成功。
    若独立：截断不消耗网络预算，retry_counts=2 < 3，第 4 次成功。
    若不独立：截断算 1 次 retry，2 次失败后 retry_counts=3 >= 3 耗尽，成功不会执行。
    """
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env._script = [("trunc", "截断")] + \
        [("fail", RuntimeError("model_call_failed: net"))] * 2 + \
        [("ok", "A")] * 1000
    assert env.run(profile="baziqa_xjz_direct") == 0
    trunc_fails = [e for e in env.read_events("model_call_failed")
                   if "truncated_response" in e["error_type"]]
    net_fails = [e for e in env.read_events("model_call_failed")
                 if e["retry_idx"] is not None]
    assert len(trunc_fails) == 1
    assert len(net_fails) == 2               # 网络预算未被截断消耗，仍剩 1 次
    assert [e["retry_idx"] for e in net_fails] == [1, 2]
    # 1 截断 + 2 网络 + 1 成功 = 4 次 call_attempt
    assert len(env.read_events("call_attempt")) == 4
    row = env.read_detail()[0]
    assert row["terminal_state"] == "parsed"


def test_truncation_budget_survives_crash_and_resume(tmp_path, monkeypatch):
    """截断预算跨 resume 守恒：1 次截断后崩溃，resume 后只剩 1 次截断额度（共 2 次耗尽）。

    防回归：旧实现 truncation_counts 不跨 resume 恢复 -> resume 后重获 2 次额度（额外重试）；
    旧 load_retry_counts 对 retry_idx=None 执行 int(None) -> TypeError。
    """
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_truncates_then_crash(1)         # 1 次截断后进程崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct")
    trunc_fails = [e for e in env.read_events("model_call_failed")
                   if e["retry_idx"] is None]
    assert len(trunc_fails) == 1              # 截断 1 次
    assert env.read_detail() == []            # 无终态
    assert len(env.read_events("call_attempt")) == 2   # 截断 1 次 + 崩溃当次（Policy A）
    # resume：再截断 1 次即耗尽预算（truncation_counts 恢复为 1，第 2 次 -> 2 >= 2）
    env.model_truncates(1)
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0
    trunc_fails = [e for e in env.read_events("model_call_failed")
                   if e["retry_idx"] is None]
    assert len(trunc_fails) == 2              # 跨 resume 累计 2 次，预算耗尽
    assert len(env.read_events("call_attempt")) == 3   # 跨 resume 累计（Policy A）
    row = env.read_detail()[0]
    assert row["terminal_state"] == "call_failed"


def test_resume_with_truncation_events_does_not_typeerror(tmp_path, monkeypatch):
    """含截断事件（retry_idx=None）的账本在 resume 时不得 TypeError。

    防回归：旧 load_retry_counts 无条件 int(row['retry_idx']) -> int(None) 崩溃。
    """
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_truncates_then_crash(1)
    env.run_expect_crash(profile="baziqa_xjz_direct")
    # resume 时 load_retry_counts / load_truncation_counts 都需正常解析截断事件
    env.model_returns("A")
    # 不抛 TypeError 即通过；返回 0 表示成功完成
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0
    row = env.read_detail()[0]
    assert row["terminal_state"] == "parsed"


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


def test_response_model_mismatch_is_not_retried(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    calls = 0

    def fake_call(messages, provider=None, model=None, system_prompt=None,
                  timeout=180, temperature=None, thinking_mode=None):
        nonlocal calls
        calls += 1
        return "A", {
            "provider": provider,
            "model": model,
            "requested_model": model,
            "response_model": "deepseek-v4-pro",
            "thinking_mode": thinking_mode,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(
        "claude_api.call_model_messages_sync_with_meta", fake_call
    )
    with pytest.raises(RuntimeError, match="response_model_mismatch"):
        env.run(
            model="deepseek-v4-flash",
            profile="baziqa_xjz_direct",
            thinking_mode="disabled",
        )
    assert calls == 1
    assert env.read_events("call_meta")[0]["response_model"] == "deepseek-v4-pro"
