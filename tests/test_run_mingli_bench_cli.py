"""Failing tests for scripts/run_mingli_bench.py CLI.

Interface under test (see docs/superpowers/plans/2026-07-01-phase1-evaluation-infra.md
Task 3.3):

- scripts.run_mingli_bench.main([...]) -> int
  * writes a normalized JSONL from data.json / fortune_api_results.json
  * invokes subprocess run_benchmark.py --dataset <that jsonl> --model-runner ...
  * forwards --model / --n-samples / --sample-temperature / --aggregate /
    --shuffle-options / --shuffle-seed when supplied
  * --astro requires --fortune (fail fast)

Behaviour contract:
1. Happy path: writes a normalized JSONL, calls subprocess once with --dataset
   pointing at that JSONL and --model forwarded.
2. --year filter reduces the JSONL row count.
3. --n-samples 3 --sample-temperature 0.5 --aggregate majority are forwarded.
4. --astro requires --fortune; missing --fortune raises SystemExit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


DATA_FIXTURE = Path("tests/fixtures/mingli/data_sample.json")
FORTUNE_FIXTURE = Path("tests/fixtures/mingli/fortune_api_results_sample.json")


@pytest.fixture
def stub_subprocess(monkeypatch):
    from scripts import run_mingli_bench as mod

    calls = []

    def _fake_run(cmd, check=True, env=None):
        calls.append({"cmd": list(cmd), "env": dict(env) if env else None})

        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    return calls


def test_run_mingli_bench_writes_jsonl_and_invokes_runner(tmp_path, stub_subprocess):
    from scripts import run_mingli_bench as mod

    jsonl_out = tmp_path / "mingli.jsonl"
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--data", str(DATA_FIXTURE),
        "--model", "deepseek-v4-flash",
        "--jsonl-out", str(jsonl_out),
        "--output-dir", str(out_dir),
        "--max-cases", "10",
    ])

    assert rc == 0
    assert jsonl_out.exists()
    rows = [json.loads(l) for l in jsonl_out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 6
    for r in rows:
        assert r.get("case_id")
        assert r.get("options")
        assert r.get("answer")
        assert r.get("domain")

    assert len(stub_subprocess) == 1
    cmd = stub_subprocess[0]["cmd"]
    assert cmd[cmd.index("--dataset") + 1] == str(jsonl_out)
    assert cmd[cmd.index("--model") + 1] == "deepseek-v4-flash"
    assert "--model-runner" in cmd


def test_run_mingli_bench_year_filter_reduces_rows(tmp_path, stub_subprocess):
    from scripts import run_mingli_bench as mod

    jsonl_out = tmp_path / "mingli.jsonl"
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--data", str(DATA_FIXTURE),
        "--model", "deepseek-v4-flash",
        "--jsonl-out", str(jsonl_out),
        "--output-dir", str(out_dir),
        "--year", "2024",
    ])

    assert rc == 0
    rows = [json.loads(l) for l in jsonl_out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert {r["year"] for r in rows} == {"2024"}
    assert len(rows) == 3


def test_run_mingli_bench_forwards_self_consistency_flags(tmp_path, stub_subprocess):
    from scripts import run_mingli_bench as mod

    jsonl_out = tmp_path / "mingli.jsonl"
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--data", str(DATA_FIXTURE),
        "--model", "deepseek-v4-flash",
        "--jsonl-out", str(jsonl_out),
        "--output-dir", str(out_dir),
        "--n-samples", "3",
        "--sample-temperature", "0.5",
        "--aggregate", "majority",
    ])

    assert rc == 0
    cmd = stub_subprocess[0]["cmd"]
    assert cmd[cmd.index("--n-samples") + 1] == "3"
    assert cmd[cmd.index("--sample-temperature") + 1] == "0.5"
    assert cmd[cmd.index("--aggregate") + 1] == "majority"


def test_run_mingli_bench_astro_requires_fortune(tmp_path, stub_subprocess):
    from scripts import run_mingli_bench as mod

    jsonl_out = tmp_path / "mingli.jsonl"
    out_dir = tmp_path / "out"

    with pytest.raises(SystemExit):
        mod.main([
            "--data", str(DATA_FIXTURE),
            "--model", "deepseek-v4-flash",
            "--jsonl-out", str(jsonl_out),
            "--output-dir", str(out_dir),
            "--astro",
        ])


def test_run_mingli_bench_with_astro_includes_chart_input(tmp_path, stub_subprocess):
    from scripts import run_mingli_bench as mod

    jsonl_out = tmp_path / "mingli.jsonl"
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--data", str(DATA_FIXTURE),
        "--fortune", str(FORTUNE_FIXTURE),
        "--model", "deepseek-v4-flash",
        "--jsonl-out", str(jsonl_out),
        "--output-dir", str(out_dir),
        "--astro",
    ])

    assert rc == 0
    rows = [json.loads(l) for l in jsonl_out.read_text(encoding="utf-8").splitlines() if l.strip()]
    with_chart = [r for r in rows if r.get("chart_input")]
    assert len(with_chart) == 4


def test_run_mingli_bench_forwards_apb_block(tmp_path, stub_subprocess):
    """Phase 3 Task 13: --apb-block must be forwarded to run_benchmark.py
    so the MingLi smoke can use the same anti-position-bias intervention."""
    from scripts import run_mingli_bench as mod

    jsonl_out = tmp_path / "mingli.jsonl"
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--data", str(DATA_FIXTURE),
        "--model", "deepseek-v4-flash",
        "--jsonl-out", str(jsonl_out),
        "--output-dir", str(out_dir),
        "--apb-block",
    ])

    assert rc == 0
    cmd = stub_subprocess[0]["cmd"]
    assert "--apb-block" in cmd


def test_run_mingli_bench_omits_apb_block_by_default(tmp_path, stub_subprocess):
    from scripts import run_mingli_bench as mod

    jsonl_out = tmp_path / "mingli.jsonl"
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--data", str(DATA_FIXTURE),
        "--model", "deepseek-v4-flash",
        "--jsonl-out", str(jsonl_out),
        "--output-dir", str(out_dir),
    ])

    assert rc == 0
    cmd = stub_subprocess[0]["cmd"]
    assert "--apb-block" not in cmd
