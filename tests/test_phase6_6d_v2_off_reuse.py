"""Phase 6 6D v2 off-reuse verifier tests (Task 4)."""
import json
import os
import shutil
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from scripts.phase6_6d_v2_orchestrator import (
    FROZEN_METHOD,
    FROZEN_PROFILE,
    FROZEN_TEMPERATURE,
    _verify_off_reuse,
)

V1_ARCHIVE = os.path.join(
    PROJECT_ROOT,
    "docs/phase6/6d/phase6-6d-v1-20260808-r1-6d-dev-2026-08-07-"
    "deepseek-deepseek-v4-flash-cc36fefa94c5")
V1_RUNS = os.path.join(
    PROJECT_ROOT, "docs/phase6/6d/runs/phase6-6d-v1-20260808-r1")


def _v2_frozen_from_v1():
    # 从真实 v1 dev_gate.json 读取 SHA + provider/model/thinking，
    # temperature/profile/method 用冻结常量
    with open(os.path.join(V1_ARCHIVE, "dev_gate.json"), encoding="utf-8") as f:
        dev_gate = json.load(f)
    return {
        "dataset_sha256_by_year": dev_gate["dataset_sha256_by_year"],
        "temporal_routed_cases_sha256": dev_gate["temporal_routed_cases_sha256"],
        "dataset_set_sha256": dev_gate["dataset_set_sha256"],
        "provider": dev_gate["provider"], "model": dev_gate["model"],
        "thinking_mode": dev_gate["thinking_mode"],
        "temperature": FROZEN_TEMPERATURE, "profile": FROZEN_PROFILE,
        "method": FROZEN_METHOD,
    }


def test_reuse_pass():
    off = _verify_off_reuse(V1_ARCHIVE, V1_RUNS, _v2_frozen_from_v1())
    assert len(off) == 93


def test_reuse_sha_drift_reject():
    v2_frozen = _v2_frozen_from_v1()
    v2_frozen["dataset_sha256_by_year"] = {"2024": "x" * 64}  # 漂移
    with pytest.raises(SystemExit):
        _verify_off_reuse(V1_ARCHIVE, V1_RUNS, v2_frozen)


def test_reuse_off_missing_reject(tmp_path):
    # 空 archive（无 dev_gate.json / off slice）→ 拒绝
    with pytest.raises(SystemExit):
        _verify_off_reuse(str(tmp_path), V1_RUNS, _v2_frozen_from_v1())


def test_reuse_experiment_id_reject(tmp_path):
    # 复制 V1_RUNS 并改写 experiment_id 为 6b2 → 拒绝
    runs_copy = tmp_path / "runs"
    shutil.copytree(V1_RUNS, runs_copy)
    ctx_path = runs_copy / "run_context.json"
    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    ctx["experiment_id"] = "6b2"
    ctx_path.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit):
        _verify_off_reuse(V1_ARCHIVE, str(runs_copy), _v2_frozen_from_v1())
