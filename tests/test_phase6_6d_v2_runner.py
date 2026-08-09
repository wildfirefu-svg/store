"""Phase 6 6D v2 runner tests - b1a_time_on_limited arm mapping."""
import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import pytest
from benchmark.runners import run_benchmark
from benchmark.runners.run_benchmark import _REASONED_ARM_MAP

# 无 --model-runner → 走离线分支，不触发真实 API；无需 --max-cases 0
_BASE_ARGS = ["--profile", "baziqa_xjz_reasoned", "--arm", "b1a_time_on_limited",
              "--time-context-injection", "on_limited",
              "--dataset", "benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl"]

def test_reasoned_arm_map_includes_on_limited():
    assert _REASONED_ARM_MAP["b1a_time_on_limited"] == "none"

def test_on_limited_ziwei_none_passes_failclosed(tmp_path, capsys):
    # 正向：通过臂检查（ziwei=none 合法）。main() 成功路径返回 int（离线分支 return 1），
    # 不 raise SystemExit。用 tmp_path 作 case-details-jsonl 避免 NUL 设备名问题。
    rc = run_benchmark.main(_BASE_ARGS + ["--ziwei-arm", "none",
        "--case-details-jsonl", str(tmp_path / "d.jsonl")])
    assert rc != 2                 # 不应是 BLOCKED
    assert "要求 arm" not in capsys.readouterr().out  # 不应因 arm 未注册被拒

def test_on_limited_ziwei_only_rejects():
    # 反向：ziwei=only 应在 :1831 raise SystemExit(2)，在任何文件操作之前，安全
    with pytest.raises(SystemExit) as e:
        run_benchmark.main(_BASE_ARGS + ["--ziwei-arm", "only",
            "--case-details-jsonl", "NUL"])
    assert e.value.code == 2
