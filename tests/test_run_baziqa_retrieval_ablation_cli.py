"""Tests for scripts.run_baziqa_retrieval_ablation Task 4.1 CLI extension.

Locks the contract that the ablation runner:
  - accepts --config-id (single) and --configs (comma-separated list);
  - resolves config metadata from baziqa_retrieval_configs.yaml;
  - forwards --model to the underlying benchmark/runners/run_benchmark.py
    subprocess for every (config, repeat) pair;
  - writes a per-config case_details JSONL with the config_id back-filled,
    and appends every row into --rollback-jsonl when supplied;
  - skips already-existing (config, repeat) outputs when --append is set;
  - emits an aggregated report row with model_name / config_id / runs /
    cost_cny columns.

The tests stub subprocess.run so no real benchmark is invoked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _write_configs(tmp_path: Path) -> Path:
    p = tmp_path / "baziqa_retrieval_configs.yaml"
    p.write_text(
        dedent(
            """
            - id: bm25
              bm25: true
              structured: false
              semantic: false
              tfidf_vector: false
              embedding_vector: false
              embedding_model: ""

            - id: structured
              bm25: true
              structured: true
              semantic: false
              tfidf_vector: false
              embedding_vector: false
              embedding_model: ""

            - id: embedding_vector
              bm25: true
              structured: true
              semantic: true
              tfidf_vector: false
              embedding_vector: true
              embedding_model: "BAAI/bge-small-zh-v1.5"

            - id: option_grounded_tfidf
              bm25: true
              structured: true
              semantic: true
              tfidf_vector: true
              embedding_vector: false
              embedding_model: ""
              retrieval_mode: option_grounded
              option_evidence_k: 2
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def stub_subprocess(monkeypatch):
    """Replace subprocess.run with a recorder that writes a tiny case_details
    JSONL at the --case-details-jsonl path supplied on the command line.
    """
    from scripts import run_baziqa_retrieval_ablation as mod

    calls = []

    def _fake_run(cmd, check=True, env=None):
        cmd_list = list(cmd)
        details_path = None
        model = None
        config_id = None
        for i, tok in enumerate(cmd_list):
            if tok == "--case-details-jsonl":
                details_path = cmd_list[i + 1]
            if tok == "--model":
                model = cmd_list[i + 1]
            if tok == "--config-id":
                config_id = cmd_list[i + 1]
        calls.append({
            "cmd": cmd_list,
            "env": dict(env) if env else None,
            "details_path": details_path,
            "model": model,
            "config_id": config_id,
        })
        if details_path:
            Path(details_path).write_text(
                json.dumps({"case_id": "stub-1", "correct": True}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    return calls


def test_runs_each_config_in_configs_with_forwarded_model(tmp_path, stub_subprocess):
    """--configs bm25,structured must invoke run_benchmark.py twice (× repeats),
    each with --model deepseek-v4-flash and the config_id propagated.
    """
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"
    rollback = tmp_path / "rollback.jsonl"
    report = tmp_path / "report.md"

    rc = mod.main([
        "--run",
        "--configs", "bm25,structured",
        "--model", "deepseek-v4-flash",
        "--repeats", "2",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--rollback-jsonl", str(rollback),
        "--report", str(report),
        "--dataset", "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl",
        "--corpus", "benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl",
    ])

    assert rc == 0
    # 2 configs × 2 repeats == 4 subprocess invocations
    assert len(stub_subprocess) == 4
    # Every call must forward --model and --config-id
    assert all(c["model"] == "deepseek-v4-flash" for c in stub_subprocess)
    seen_ids = sorted({c["config_id"] for c in stub_subprocess})
    assert seen_ids == ["bm25", "structured"]


def test_single_config_id_default_when_configs_missing(tmp_path, stub_subprocess):
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--run",
        "--config-id", "embedding_vector",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--report", str(tmp_path / "r.md"),
    ])
    assert rc == 0
    assert len(stub_subprocess) == 1
    assert stub_subprocess[0]["config_id"] == "embedding_vector"


def test_rollback_jsonl_aggregates_rows_with_config_id(tmp_path, stub_subprocess):
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"
    rollback = tmp_path / "rollback.jsonl"

    mod.main([
        "--run",
        "--configs", "bm25,structured",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--rollback-jsonl", str(rollback),
        "--report", str(tmp_path / "r.md"),
    ])

    rows = [json.loads(l) for l in rollback.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 2
    assert {r["config_id"] for r in rows} == {"bm25", "structured"}
    # Every aggregated row must also embed model_name for downstream cost tally.
    assert all(r["model_name"] == "deepseek-v4-flash" for r in rows)


def test_append_skips_existing_files(tmp_path, stub_subprocess):
    """--append must skip a (config, repeat) pair when its jsonl is already on
    disk, so a rerun can resume without redoing API calls.
    """
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Pre-create the file the runner would produce for (bm25, run1).
    pre_existing = out_dir / "bm25_run1.jsonl"
    pre_existing.write_text(
        json.dumps({"case_id": "pre", "correct": True}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    mod.main([
        "--run",
        "--configs", "bm25",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--append",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--report", str(tmp_path / "r.md"),
    ])

    # Nothing was re-invoked because the only (config, repeat) was already there.
    assert stub_subprocess == []
    # And the pre-existing content is untouched.
    assert "pre" in pre_existing.read_text(encoding="utf-8")


def test_append_does_not_skip_empty_existing_files(tmp_path, stub_subprocess):
    """An empty file from a previously aborted run must NOT satisfy --append,
    otherwise we would silently skip a config that still needs to be redone.
    """
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    empty = out_dir / "bm25_run1.jsonl"
    empty.write_text("", encoding="utf-8")

    mod.main([
        "--run",
        "--configs", "bm25",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--append",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--report", str(tmp_path / "r.md"),
    ])

    assert len(stub_subprocess) == 1, "an empty pre-existing file must not block the rerun"


def test_append_does_not_duplicate_rollback_for_skipped_configs(tmp_path, stub_subprocess):
    """When --append skips a (config, repeat) pair, its rows MUST NOT be
    re-appended to the rollback JSONL; otherwise a rerun grows rollback by
    one full pass each time and inflates downstream counts.
    """
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    rollback = tmp_path / "rb.jsonl"

    # First pass: stub records 2 invocations and rollback ends with 2 rows.
    mod.main([
        "--run",
        "--configs", "bm25,structured",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--rollback-jsonl", str(rollback),
        "--report", str(tmp_path / "r.md"),
    ])
    first_rb_rows = [json.loads(l) for l in rollback.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(first_rb_rows) == 2

    # Second pass with --append: both jsonl files exist and non-empty,
    # so subprocess.run must be called 0 times and rollback must not grow.
    stub_subprocess.clear()
    mod.main([
        "--run",
        "--configs", "bm25,structured",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--append",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--rollback-jsonl", str(rollback),
        "--report", str(tmp_path / "r.md"),
    ])
    assert stub_subprocess == []
    second_rb_rows = [json.loads(l) for l in rollback.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(second_rb_rows) == 2, (
        f"rollback must not duplicate rows for skipped configs, got {len(second_rb_rows)}"
    )


def test_subprocess_env_defaults_to_hf_offline(tmp_path, stub_subprocess, monkeypatch):
    """The runner must default to HF offline mode for each subprocess so that
    a flaky huggingface.co connection cannot stall the ablation; an
    externally-set value must be preserved (no clobber).
    """
    from scripts import run_baziqa_retrieval_ablation as mod

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"

    mod.main([
        "--run",
        "--configs", "bm25",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--report", str(tmp_path / "r.md"),
    ])

    env = stub_subprocess[0]["env"]
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == "1"


def test_subprocess_env_respects_caller_hf_setting(tmp_path, stub_subprocess, monkeypatch):
    """If the caller explicitly sets HF_HUB_OFFLINE=0 (e.g. to refresh the
    cache), the runner must NOT silently override it.
    """
    from scripts import run_baziqa_retrieval_ablation as mod

    monkeypatch.setenv("HF_HUB_OFFLINE", "0")

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"

    mod.main([
        "--run",
        "--configs", "bm25",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--report", str(tmp_path / "r.md"),
    ])

    env = stub_subprocess[0]["env"]
    assert env["HF_HUB_OFFLINE"] == "0", "caller override must win"


def test_report_columns_include_model_and_config_id(tmp_path, stub_subprocess):
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"
    report = tmp_path / "r.md"

    mod.main([
        "--run",
        "--configs", "bm25",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--report", str(report),
    ])

    text = report.read_text(encoding="utf-8")
    assert "config_id" in text
    assert "model_name" in text
    assert "deepseek-v4-flash" in text
    assert "bm25" in text


def test_forwards_option_grounded_flags_to_benchmark_runner(tmp_path, stub_subprocess):
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--run",
        "--configs", "bm25",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--report", str(tmp_path / "r.md"),
        "--retrieval-mode", "option_grounded",
        "--option-evidence-k", "2",
    ])

    assert rc == 0
    cmd = stub_subprocess[0]["cmd"]
    assert "--retrieval-mode" in cmd
    assert cmd[cmd.index("--retrieval-mode") + 1] == "option_grounded"
    assert "--option-evidence-k" in cmd
    assert cmd[cmd.index("--option-evidence-k") + 1] == "2"


def test_option_grounded_config_forwards_its_retrieval_mode(tmp_path, stub_subprocess):
    from scripts import run_baziqa_retrieval_ablation as mod

    configs_yaml = _write_configs(tmp_path)
    out_dir = tmp_path / "out"

    rc = mod.main([
        "--run",
        "--configs", "option_grounded_tfidf",
        "--model", "deepseek-v4-flash",
        "--repeats", "1",
        "--retrieval-configs-yaml", str(configs_yaml),
        "--output-dir", str(out_dir),
        "--report", str(tmp_path / "r.md"),
    ])

    assert rc == 0
    cmd = stub_subprocess[0]["cmd"]
    assert cmd[cmd.index("--config-id") + 1] == "option_grounded_tfidf"
    assert cmd[cmd.index("--retrieval-mode") + 1] == "option_grounded"
    assert cmd[cmd.index("--option-evidence-k") + 1] == "2"
