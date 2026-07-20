from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.phase6_helpers import RunnerEnv

EMIT = ["--n-samples", "5", "--aggregate", "emit_samples",
        "--profile", "baziqa_xjz_direct", "--chart-schema-version", "legacy_v0",
        "--arm", "vote5_samples", "--sample-temperature", "0.4"]


def _keys(rows):
    return {tuple(r["attempt_key"]) for r in rows}


class TestEmitSamples:
    def test_emit_writes_per_sample_rows(self, tmp_path, monkeypatch):
        """每 case 写 5 行；attempt key 10 字段且 sample_idx 0..4 互异；行带 emit 标记。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10
        for r in rows:
            assert r["aggregate"] == "emit_samples" and r["n_samples"] == 5
            assert r["sample_idx"] in range(5)
            assert r["attempt_key"][3] == "main"               # 默认 attempt_stage
        per_case = {}
        for r in rows:
            per_case.setdefault(r["case_id"], set()).add(r["attempt_key"][8])
        assert per_case == {"c0": {0, 1, 2, 3, 4}, "c1": {0, 1, 2, 3, 4}}

    def test_emit_uses_sample_temperature(self, tmp_path, monkeypatch):
        """5 个样本全部以 sample_temperature=0.4 发起（非 --temperature 0.0）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        temps = [kw.get("temperature") for kw in env.received_kw]
        assert temps == [0.4] * 5

    def test_attempt_stage_param_flows_to_keys(self, tmp_path, monkeypatch):
        """--attempt-stage anchor → 全部行 attempt_key[3] == 'anchor'。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT + ["--attempt-stage", "anchor"]) == 0
        assert {r["attempt_key"][3] for r in env.read_detail()} == {"anchor"}

    def test_emit_resume_per_sample(self, tmp_path, monkeypatch):
        """7 次成功后崩溃（c0 5 + c1 头 2）；resume 只补 c1 余 3 样本；
        最终键集合 == 一次性运行（续跑幂等）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_succeeds_then_crash("A", successes=7)
        env.run_expect_crash(extra_argv=EMIT)
        env.model_returns("A")
        assert env.run(resume=True, extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10 and len(_keys(rows)) == 10     # 无重复键

    def test_emit_case_level_prefilter_not_applied(self, tmp_path, monkeypatch):
        """全量后删掉 c0 的 sample 1-4 行（留 sample 0）→ resume 恰好补 4 次调用；
        若错误沿用 case 级预过滤（sample_idx=0 键已完成），c0 会被整体跳过（0 次）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        kept = [r for r in env.read_detail()
                if not (r["case_id"] == "c0" and r["sample_idx"] != 0)]
        env.detail.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                      for r in kept), encoding="utf-8")
        before = len(env.received)
        assert env.run(resume=True, extra_argv=EMIT) == 0
        assert len(env.received) - before == 4                 # 只补 c0 样本 1-4
        rows = env.read_detail()
        assert len(rows) == 10 and len(_keys(rows)) == 10

    def test_emit_sample_failure_row_and_budget(self, tmp_path, monkeypatch):
        """头 3 次网络失败 → c0/sample0 重试耗尽写 call_failed 行（占分母），
        后续样本继续；总调用 3 + 9 = 12；重试账本只记 sample0。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_fails(times=3)
        assert env.run(extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10
        failed = [r for r in rows if r["terminal_state"] == "call_failed"]
        assert len(failed) == 1 and failed[0]["case_id"] == "c0" \
            and failed[0]["sample_idx"] == 0
        assert len(env.read_events("call_attempt")) == 12
        assert len(env.read_events("model_call_failed")) == 3
        assert {tuple(e["attempt_key"]) for e in env.read_events("model_call_failed")} \
            == {tuple(failed[0]["attempt_key"])}

    def test_emit_hard_cap_exit3_and_blocked_resume(self, tmp_path, monkeypatch):
        """hard_cap=3 → exit 3（BLOCKED_INCOMPLETE）；manifest 锁 cap，同 cap resume 仍 3
        且不新增调用（设计 §12.6：追加预算须新开 run/slice 目录，不得改 cap 续跑）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(scheduled_calls=10, hard_cap=3, extra_argv=EMIT) == 3
        assert len(env.read_events("call_attempt")) == 3
        assert env.run(resume=True, scheduled_calls=10, hard_cap=3, extra_argv=EMIT) == 3
        assert len(env.read_events("call_attempt")) == 3

    def test_emit_requires_profile_and_n_samples(self, tmp_path, monkeypatch):
        """emit_samples 无 profile → ValueError；n_samples=1 → ValueError。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        with pytest.raises(ValueError, match="emit_samples"):
            env.run(extra_argv=["--n-samples", "5", "--aggregate", "emit_samples"])
        with pytest.raises(ValueError, match="emit_samples"):
            env.run(extra_argv=["--n-samples", "1", "--aggregate", "emit_samples",
                                "--profile", "baziqa_xjz_direct",
                                "--chart-schema-version", "legacy_v0"])

    def test_emit_manifest_records_vote_fields(self, tmp_path, monkeypatch):
        """manifest 记录 aggregate/n_samples/sample_temperature/attempt_stage/temperature。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        m = json.loads((tmp_path / "detail.manifest.json").read_text(encoding="utf-8"))
        assert m["aggregate"] == "emit_samples" and m["n_samples"] == 5
        assert m["sample_temperature"] == 0.4 and m["temperature"] == 0.0
        assert m["attempt_stage"] == "main"                    # 决策 7 反转

    def test_resume_rejects_attempt_stage_change(self, tmp_path, monkeypatch):
        """决策 7 反转：先以 main 跑，再以 --attempt-stage anchor 续跑 → SystemExit(2)
        （manifest attempt_stage 不一致 fail-closed；同目录混合 stage 被禁止）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        with pytest.raises(SystemExit) as exc:
            env.run(resume=True, extra_argv=EMIT + ["--attempt-stage", "anchor"])
        assert exc.value.code == 2
