from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.run_benchmark import (
    ATTEMPT_STAGES,
    RESUME_MANIFEST_FIELDS,
    build_attempt_key,
    load_completed_keys,
)
from tests.phase6_helpers import RunnerEnv


def key_of(**overrides):
    base = dict(dataset_id="d", profile_id="p", arm="a", attempt_stage="main",
                provider="deepseek", model="m", case_id="c1",
                repeat_idx=0, sample_idx=0, permutation_id="p0")
    base.update(overrides)
    return build_attempt_key(**base)


def test_attempt_key_no_collision_across_stages():
    keys = {key_of(attempt_stage=s) for s in ATTEMPT_STAGES}
    assert len(keys) == len(ATTEMPT_STAGES)
    assert key_of(attempt_stage="bazi") != key_of(attempt_stage="ziwei")
    assert key_of(arm="x") != key_of(arm="y")
    assert key_of(repeat_idx=0) != key_of(repeat_idx=1)


def test_truncation_guard_requires_intent(tmp_path, monkeypatch):
    """detail 已存在：无 --resume 一律拒绝（Phase 6 无 --overwrite 语义）；--resume 合法续跑。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0          # 首跑：detail 不存在
    with pytest.raises(SystemExit):
        env.run(profile="baziqa_xjz_direct")                  # 已存在且无 --resume → 拒绝
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0


def test_resume_manifest_created_on_first_run(tmp_path, monkeypatch):
    """首跑（含 --resume 首跑）在 detail 旁创建 detail.manifest.json，17 字段齐全。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    manifest = json.loads((tmp_path / "detail.manifest.json").read_text(encoding="utf-8"))
    for field in RESUME_MANIFEST_FIELDS:
        assert field in manifest
    assert manifest["profile_id"] == "baziqa_xjz_direct"
    assert manifest["temperature"] == 0.0              # 仓库 --temperature 默认 0.0（6A0 真实控制温度）
    assert manifest["n_samples"] == 1
    assert manifest["method"] == "direct_choice"       # profile 推导生效值（resolve 后记录）
    assert manifest["hard_cap"] is None or isinstance(manifest["hard_cap"], int)


@pytest.mark.parametrize("field,value", [
    ("dataset_sha256", "tamper"),                    # 数据变化
    ("temperature", 9.9),                            # 真实温度变化（n_samples=1 时控制调用）
    ("sample_temperature", 9.9),                     # 采样温度变化
    ("chart_schema_version", "legacy_v0"),           # schema 变化
    ("method", "multi_turn"),                        # 生效 method 变化
    ("prompt_template_sha256", "tamper"),            # prompt/模板变化
    ("code_sha256", "tamper"),                       # 代码变化
    ("hard_cap", 999),                               # 预算变化
])
def test_resume_manifest_mismatch_refused(tmp_path, monkeypatch, field, value):
    """manifest 任一字段不一致 → SystemExit(2)，禁止向旧 detail 续跑（设计 L168）。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    mpath = tmp_path / "detail.manifest.json"
    stored = json.loads(mpath.read_text(encoding="utf-8"))
    stored[field] = value
    mpath.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True)
    assert exc_info.value.code == 2


def test_resume_manifest_dataset_change_refused(tmp_path, monkeypatch):
    """真实数据变更（非篡改 manifest）→ dataset_sha256 漂移 → SystemExit(2)。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    env.dataset.write_text(env.dataset.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True)
    assert exc_info.value.code == 2


def test_resume_manifest_config_drift_refused(tmp_path, monkeypatch):
    """配置漂移（非篡改存储文件）：resume 时 --temperature 0.0→1.0 → current manifest 漂移 →
    SystemExit(2)。证明配置漂移真实进入 current manifest，而非仅能检测存储文件被改。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0   # 默认 --temperature 0.0
    env.model_returns("A")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True,
                extra_argv=["--temperature", "1.0"])
    assert exc_info.value.code == 2


def test_resume_refused_when_manifest_missing_but_detail_exists(tmp_path, monkeypatch):
    """旧 detail/events 在而 manifest 缺失（被删或旧版本遗留）→ fail-closed SystemExit(2)，
    不得基于当前配置新建 manifest 混合旧结果。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    (tmp_path / "detail.manifest.json").unlink()       # 模拟 manifest 被删/旧版本遗留
    env.model_returns("A")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True)
    assert exc_info.value.code == 2


def test_resume_manifest_field_missing_refused(tmp_path, monkeypatch):
    """manifest 字段缺失（如旧版缺 temperature）→ 缺失字段计入 diff，SystemExit(2)；
    即使 current 对应值为 None（此处 case_ids_sha256）也不得经 stored.get 误判相等放行。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    mpath = tmp_path / "detail.manifest.json"
    stored = json.loads(mpath.read_text(encoding="utf-8"))
    del stored["case_ids_sha256"]                      # current 为 None：get 语义会误判相等
    mpath.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    env.model_returns("A")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True)
    assert exc_info.value.code == 2


def test_resume_first_crash_artifacts_guard(tmp_path, monkeypatch):
    """--resume 首跑在第一次调用时崩溃，仅留下 manifest/events（detail 不存在）：
    无 --resume 重跑必须 SystemExit(2)（任一产物守卫，防预算计数被静默重置）；
    --resume 可继续。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
    env.model_succeeds_then_crash("A", successes=0)   # 第一次模型调用即崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct", resume=True)   # resume-first 首跑
    assert not env.detail.exists()                     # 无终态写入
    assert (tmp_path / "detail.manifest.json").exists()
    assert len(env.read_events("call_attempt")) == 1   # 崩溃 attempt 已记账
    env.model_returns("A")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct")           # 无 --resume → 拒绝
    assert exc_info.value.code == 2
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0   # --resume 可继续
    assert len(load_completed_keys(env.detail)) == 2


def test_resume_skips_completed_and_key_set_matches_one_shot(tmp_path, monkeypatch):
    # 两次运行使用完全相同的 case 集合（manifest 契约：case_ids_sha256 不得漂移）；
    # 首跑在第 3 次模型调用时进程崩溃，resume 跳过已完成键续跑至完成，键集合与一次性运行一致。
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=4)
    env.model_succeeds_then_crash("A", successes=2)   # c0、c1 成功；c2 调用时进程崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct")
    assert len(env.read_detail()) == 2                 # 仅 c0、c1 终态
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0
    resumed_keys = load_completed_keys(env.detail)
    assert len(resumed_keys) == 4
    # 一次性运行同 4 题
    oneshot = RunnerEnv(tmp_path / "oneshot", monkeypatch, n_cases=4)
    oneshot.model_returns("A")
    assert oneshot.run(profile="baziqa_xjz_direct") == 0
    assert resumed_keys == load_completed_keys(oneshot.detail)


def test_detail_rows_carry_attempt_key_and_terminal_state(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("B")  # 正确答案（make_case 默认 answer="B"）
    assert env.run(profile="baziqa_xjz_direct", extra_argv=["--arm", "ctx_approved",
                                                            "--repeat-idx", "0"]) == 0
    rows = env.read_detail()
    assert len(rows) == 1
    row = rows[0]
    assert row["attempt_key"][6] == "c0"            # case_id 槽位
    assert row["attempt_key"][1] == "baziqa_xjz_direct"
    assert row["attempt_key"][2] == "ctx_approved"
    assert row["terminal_state"] == "parsed"
    assert row["raw_response_path"].endswith("detail.jsonl")


def test_invalid_parse_is_terminal_not_retried(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("我完全不知道怎么选")   # 解析不出选项
    assert env.run(profile="baziqa_xjz_direct") == 0
    rows = env.read_detail()
    assert rows[0]["terminal_state"] == "invalid"
    assert env.read_events("model_call_failed") == []  # 解析失败不占网络重试额度
    assert len(env.read_events("call_attempt")) == 1   # 但成功记账一次调用
