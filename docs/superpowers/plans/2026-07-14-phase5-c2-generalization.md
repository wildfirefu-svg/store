# Phase 5 C2 Generalization Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现可恢复、可审计且默认密封 2023 数据的 Phase 5 C2 独立泛化验证编排器，用配对实验量化 direct+C2 相对 direct 的准确率变化。

**Architecture:** 新增单一编排脚本，复用现有 enrichment、C2 scorer、benchmark runner 与答案解析器；脚本负责不可变数据副本、manifest、离线门禁、AB/BA 调度、分歧题复测、逐 attempt 持久化和最终报告。所有决策逻辑写成无网络纯函数并由专用单测覆盖，真实模型仅通过注入的 runner 边界调用。

**Tech Stack:** Python 3.11+、标准库（`argparse`、`dataclasses`、`hashlib`、`json`、`math`、`pathlib`、`random`、`subprocess`）、pytest、现有 BaziQA runner/scorer/enrichment。

---

## 文件结构

- Create: `scripts/run_phase5_c2_generalization.py` — Phase 5 唯一编排入口；包含纯函数、manifest、运行恢复、汇总和 CLI。
- Create: `tests/test_phase5_c2_generalization.py` — fake runner 单元/集成测试，不访问网络。
- Create at runtime only: `.tmp/phase5_generalization/**` — enriched 数据、离线结果、attempt 记录和运行状态，不加入 Git。
- Create after a complete real experiment: `docs/phase5/<run_id>/report.md`、`docs/phase5/<run_id>/manifest.json`、`docs/phase5/<run_id>/summary.json` — 每个 run 使用独立目录，由脚本生成；实现阶段不伪造真实实验结果。
- Do not modify: `benchmark/runners/per_option_scorer.py`、`benchmark/runners/run_benchmark.py`、`benchmark/datasets/*.jsonl`。

## 固定接口与数据结构

编排脚本统一使用以下公开类型，后续任务不得改名：

```python
@dataclass(frozen=True)
class ExperimentConfig:
    run_id: str
    root: Path
    years: tuple[int, ...]
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    method: str = "direct_choice"
    prompt_version: str = "srp_v1"
    temperature: float = 0.0
    seed: int = 20260714
    allow_dirty_scope: bool = False
    resume: bool = False
    final_2023: bool = False
    candidate_id: str | None = None


Runner = Callable[..., dict[str, Any]]
```

Attempt JSONL 的唯一键固定为 `(run_id, year, case_id, arm, attempt)`；`arm` 仅允许 `direct` 或 `direct_c2`。每条记录至少包含：

```python
{
    "run_id": "phase5-c2-001",
    "year": 2021,
    "case_id": "P025-Q1",
    "arm": "direct",
    "attempt": 1,
    "raw_answer": "C",
    "predicted_answer": "C",
    "expected_answer": "C",
    "parser_source": "legacy",
    "parser_valid": True,
    "correct": True,
    "call_success": True,
    "failure": None,
    "phase4_option_scores": [],
    "latency_seconds": 1.0,
}
```

## Task 1: 建立纯函数基础与 enrichment 不变量

**Files:**
- Create: `scripts/run_phase5_c2_generalization.py`
- Create: `tests/test_phase5_c2_generalization.py`

- [ ] **Step 1: 写入 enrichment 与哈希的失败测试**

在 `tests/test_phase5_c2_generalization.py` 写入：

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_phase5_c2_generalization as phase5


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def sample_case(case_id: str = "c1", answer: str = "B", domain: str = "wealth") -> dict:
    return {
        "case_id": case_id,
        "answer": answer,
        "domain": domain,
        "question": "命主财运如何？",
        "options": ["A 普通", "B 富裕", "C 破财", "D 平稳"],
        "source_year": "2021",
        "person": {
            "person_id": f"p-{case_id}",
            "gender": "male",
            "birth": {
                "year": 1990,
                "month": 1,
                "day": 2,
                "hour": 3,
                "minute": 0,
                "place": "北京",
            },
        },
    }


def fake_enrich(row: dict) -> dict:
    return {
        **row,
        "chart_input": {
            "shishen_stats": {"counts": {"正财": 1}, "missing": []},
            "branch_relations": [],
            "shensha": [],
            "wuxing_stats": {"missing": [], "strongest": "木", "weakest": "水"},
        },
    }


def test_enrich_dataset_preserves_protected_fields_and_hash(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    output = tmp_path / "enriched.jsonl"
    rows = [sample_case("c1"), sample_case("c2", answer="C")]
    write_jsonl(source, rows)

    metadata = phase5.enrich_dataset(
        source,
        output,
        enrich_fn=fake_enrich,
        expected_rows=2,
    )

    enriched = phase5.load_jsonl(output)
    assert metadata["row_count"] == 2
    assert metadata["chart_input_coverage"] == 1.0
    assert metadata["sha256"] == phase5.sha256_file(output)
    assert [row["case_id"] for row in enriched] == ["c1", "c2"]
    assert [row["answer"] for row in enriched] == ["B", "C"]
    assert [row["person"] for row in enriched] == [row["person"] for row in rows]
    assert all(row["chart_input"] for row in enriched)


def test_validate_enriched_rejects_duplicate_case_id(tmp_path: Path):
    source_rows = [sample_case("c1"), sample_case("c2")]
    enriched_rows = [fake_enrich(sample_case("c1")), fake_enrich(sample_case("c1"))]

    with pytest.raises(ValueError, match="duplicate case_id"):
        phase5.validate_enriched_rows(source_rows, enriched_rows)


def test_validate_enriched_rejects_answer_mutation():
    original = sample_case()
    changed = fake_enrich({**original, "answer": "D"})

    with pytest.raises(ValueError, match="protected field changed"):
        phase5.validate_enriched_rows([original], [changed])


def test_enrich_dataset_requires_expected_holdout_size(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    write_jsonl(source, [sample_case("c1")])

    with pytest.raises(ValueError, match="expected 40 rows"):
        phase5.enrich_dataset(source, tmp_path / "out.jsonl", enrich_fn=fake_enrich)


def test_validate_enriched_rejects_missing_core_chart_signals():
    source = sample_case()
    incomplete = {
        **source,
        "chart_input": {
            "shishen_stats": {"counts": {}},
            "wuxing_stats": {"strongest": None},
        },
    }

    with pytest.raises(ValueError, match="incomplete chart signals"):
        phase5.validate_enriched_rows([source], [incomplete])


def test_classify_c2_applicability_separates_effective_and_noop_cases():
    cases = [sample_case("active"), sample_case("noop")]
    result = phase5.classify_c2_applicability(
        cases,
        score_fn=lambda case: [{"score": 50}] if case["case_id"] == "active" else [],
    )

    assert result == {
        "c2_effective_cases": 1,
        "c2_noop_cases": 1,
        "c2_effective_case_ids": ["active"],
        "c2_noop_case_ids": ["noop"],
        "c2_effective_rate": 0.5,
    }
```

- [ ] **Step 2: 运行测试确认因模块缺失而失败**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: FAIL during collection with `ImportError: cannot import name 'run_phase5_c2_generalization'`。

- [ ] **Step 3: 实现 IO、SHA-256 和 enrichment 校验**

创建 `scripts/run_phase5_c2_generalization.py`，先写入：

```python
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.runners.per_option_scorer import score_options, summarize_scores
from benchmark.runners.run_benchmark import run_model_benchmark
from benchmark.scorers.choice_accuracy import extract_choice
from scripts.enrich_holdout_chart_input import enrich_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / ".tmp" / "phase5_generalization"
PROTECTED_FIELDS = (
    "case_id",
    "person",
    "question",
    "options",
    "answer",
    "source_year",
)
EXPERIMENT_SCOPE = (
    "benchmark/runners/per_option_scorer.py",
    "benchmark/formatters/baziqa_prompt.py",
    "benchmark/runners/run_benchmark.py",
    "scripts/enrich_holdout_chart_input.py",
    "scripts/enrich_baziqa_chart_input.py",
    "bazi_calculator.py",
)
SEAL_AUDIT_NOTE = (
    "2026-07-14 audit loaded the 2023 JSONL only for structural and "
    "time/location classification; no answers or accuracy metrics were used. "
    "User approved retaining 2023 as the final set."
)
OFFLINE_THRESHOLDS = {
    "top_score_hit_rate": (">", 0.35),
    "score_answer_correlation": (">", 0.10),
    "neutral_option_rate": ("<", 0.50),
    "strong_signal_option_rate": (">", 0.30),
}


@dataclass(frozen=True)
class ExperimentConfig:
    run_id: str
    root: Path
    years: tuple[int, ...]
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    method: str = "direct_choice"
    prompt_version: str = "srp_v1"
    temperature: float = 0.0
    seed: int = 20260714
    allow_dirty_scope: bool = False
    resume: bool = False
    final_2023: bool = False
    candidate_id: str | None = None


Runner = Callable[..., dict[str, Any]]


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_enriched_rows(
    source_rows: list[dict[str, Any]],
    enriched_rows: list[dict[str, Any]],
) -> None:
    if len(source_rows) != len(enriched_rows):
        raise ValueError("row count changed during enrichment")
    case_ids = [row.get("case_id") for row in enriched_rows]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("duplicate case_id in enriched dataset")
    for source, enriched in zip(source_rows, enriched_rows):
        for field in PROTECTED_FIELDS:
            if source.get(field) != enriched.get(field):
                raise ValueError(
                    f"protected field changed during enrichment: "
                    f"{source.get('case_id')} {field}"
                )
        if not enriched.get("chart_input"):
            raise ValueError(f"missing chart_input: {source.get('case_id')}")
        chart = enriched["chart_input"]
        counts = ((chart.get("shishen_stats") or {}).get("counts") or {})
        strongest = (chart.get("wuxing_stats") or {}).get("strongest")
        if not counts or not strongest:
            raise ValueError(f"incomplete chart signals: {source.get('case_id')}")


def classify_c2_applicability(
    cases: list[dict[str, Any]],
    score_fn: Callable[[dict[str, Any]], list[dict[str, Any]]] = score_options,
) -> dict[str, Any]:
    effective = []
    noop = []
    for case in cases:
        target = effective if score_fn(case) else noop
        target.append(case["case_id"])
    total = len(cases)
    return {
        "c2_effective_cases": len(effective),
        "c2_noop_cases": len(noop),
        "c2_effective_case_ids": effective,
        "c2_noop_case_ids": noop,
        "c2_effective_rate": len(effective) / total if total else 0.0,
    }


def enrich_dataset(
    source: str | Path,
    output: str | Path,
    enrich_fn: Callable[[dict[str, Any]], dict[str, Any]] = enrich_row,
    expected_rows: int = 40,
) -> dict[str, Any]:
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"holdout dataset not found: {source_path}")
    source_rows = load_jsonl(source_path)
    enriched_rows = [enrich_fn(row) for row in source_rows]
    validate_enriched_rows(source_rows, enriched_rows)
    if len(enriched_rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} rows, got {len(enriched_rows)}")
    write_jsonl(output, enriched_rows)
    return describe_dataset(source_path, output, expected_rows)


def describe_dataset(
    source: str | Path,
    output: str | Path,
    expected_rows: int = 40,
) -> dict[str, Any]:
    source_path = Path(source)
    enriched_rows = load_jsonl(output)
    validate_enriched_rows(load_jsonl(source_path), enriched_rows)
    if len(enriched_rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} rows, got {len(enriched_rows)}")
    return {
        "source_path": str(source_path),
        "source_sha256": sha256_file(source_path),
        "enriched_path": str(Path(output)),
        "sha256": sha256_file(output),
        "row_count": len(enriched_rows),
        "person_count": len({row["person"].get("person_id") for row in enriched_rows}),
        "domain_distribution": dict(Counter(row.get("domain", "unknown") for row in enriched_rows)),
        "chart_input_coverage": (
            sum(bool(row.get("chart_input")) for row in enriched_rows) / len(enriched_rows)
            if enriched_rows else 0.0
        ),
        "enriched_at": datetime.fromtimestamp(
            Path(output).stat().st_mtime,
            timezone.utc,
        ).isoformat(),
        "c2_applicability": classify_c2_applicability(enriched_rows),
    }
```

- [ ] **Step 4: 运行 Task 1 测试确认通过**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: `6 passed`。

- [ ] **Step 5: 提交基础实现**

```powershell
git add scripts/run_phase5_c2_generalization.py tests/test_phase5_c2_generalization.py
git commit -m "feat: validate Phase 5 enriched datasets"
```

## Task 2: Manifest、作用域脏检查与严格恢复

**Files:**
- Modify: `scripts/run_phase5_c2_generalization.py`
- Modify: `tests/test_phase5_c2_generalization.py`

- [ ] **Step 1: 写入 manifest 漂移和 dirty scope 失败测试**

追加到测试文件：

```python
def test_dirty_scope_requires_explicit_override():
    dirty = {"benchmark/runners/per_option_scorer.py": "??"}

    with pytest.raises(RuntimeError, match="--allow-dirty-scope"):
        phase5.enforce_dirty_scope(dirty, allow_dirty_scope=False)

    phase5.enforce_dirty_scope(dirty, allow_dirty_scope=True)


def test_manifest_resume_requires_exact_fingerprint(tmp_path: Path):
    path = tmp_path / "manifest.json"
    expected = {"fingerprint": "abc", "run_id": "r1"}
    phase5.write_json(path, expected)

    assert phase5.load_or_validate_manifest(path, expected, resume=True) == expected
    with pytest.raises(RuntimeError, match="manifest mismatch"):
        phase5.load_or_validate_manifest(
            path,
            {"fingerprint": "changed", "run_id": "r1"},
            resume=True,
        )


def test_existing_manifest_requires_resume(tmp_path: Path):
    path = tmp_path / "manifest.json"
    phase5.write_json(path, {"fingerprint": "abc"})

    with pytest.raises(RuntimeError, match="--resume"):
        phase5.load_or_validate_manifest(path, {"fingerprint": "abc"}, resume=False)


def test_resume_requires_existing_manifest(tmp_path: Path):
    with pytest.raises(RuntimeError, match="cannot resume missing manifest"):
        phase5.load_or_validate_manifest(
            tmp_path / "missing.json",
            {"fingerprint": "abc"},
            resume=True,
        )


def test_manifest_declares_explicit_fingerprint_scope(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(phase5, "EXPERIMENT_SCOPE", ())
    monkeypatch.setattr(phase5, "git_output", lambda *args: "deadbeef")
    config = phase5.ExperimentConfig("r1", tmp_path, (2021, 2022))

    manifest = phase5.build_manifest(config, datasets={}, scope_status={})

    assert manifest["fingerprint_scope"] == {
        "coverage": "explicit_experiment_files_only",
        "files": [],
        "indirect_dependencies_fingerprinted": False,
    }
    assert manifest["seal_audit_note"] == phase5.SEAL_AUDIT_NOTE


def test_fixed_environment_rejects_rag(monkeypatch):
    monkeypatch.setenv("BAZI_RAG", "1")

    with pytest.raises(RuntimeError, match="BAZI_RAG"):
        phase5.assert_fixed_environment()
```

- [ ] **Step 2: 运行新增测试确认函数不存在**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: FAIL with `AttributeError` for `enforce_dirty_scope` or `load_or_validate_manifest`。

- [ ] **Step 3: 实现 manifest 指纹与 Git 快照**

追加到编排脚本：

```python
def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def experiment_scope_status() -> dict[str, str]:
    output = git_output("status", "--short", "--", *EXPERIMENT_SCOPE)
    status: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            continue
        status[line[3:]] = line[:2]
    return status


def enforce_dirty_scope(status: dict[str, str], allow_dirty_scope: bool) -> None:
    if status and not allow_dirty_scope:
        paths = ", ".join(sorted(status))
        raise RuntimeError(
            f"experiment scope has uncommitted changes: {paths}; "
            "pass --allow-dirty-scope to record and run them"
        )


def stable_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(
    config: ExperimentConfig,
    datasets: dict[str, dict[str, Any]],
    scope_status: dict[str, str],
    prior_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    scope_hashes = {
        path: sha256_file(PROJECT_ROOT / path)
        for path in EXPERIMENT_SCOPE
    }
    immutable = {
        "run_id": config.run_id,
        "datasets": datasets,
        "git_commit": git_output("rev-parse", "HEAD"),
        "scope_status": scope_status,
        "scope_hashes": scope_hashes,
        "fingerprint_scope": {
            "coverage": "explicit_experiment_files_only",
            "files": list(EXPERIMENT_SCOPE),
            "indirect_dependencies_fingerprinted": False,
        },
        "provider": config.provider,
        "model": config.model,
        "method": config.method,
        "prompt_version": config.prompt_version,
        "temperature": config.temperature,
        "rag": False,
        "few_shot": False,
        "apb": False,
        "two_stage": False,
        "seed": config.seed,
        "year_schedule_seeds": {
            str(year): year_schedule_seed(config, year)
            for year in config.years
        },
        "years": list(config.years),
        "candidate_id": config.candidate_id,
        "prior_manifest_sha256": prior_manifest_sha256,
        "seal_audit_note": SEAL_AUDIT_NOTE,
    }
    return {
        **immutable,
        "fingerprint": stable_fingerprint(immutable),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "worktree_dirty_warning": bool(git_output("status", "--short")),
    }


def load_or_validate_manifest(
    path: str | Path,
    expected: dict[str, Any],
    resume: bool,
) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        if resume:
            raise RuntimeError(f"cannot resume missing manifest: {target}")
        write_json(target, expected)
        return expected
    if not resume:
        raise RuntimeError(f"run already exists at {target}; use --resume")
    actual = json.loads(target.read_text(encoding="utf-8"))
    if actual.get("fingerprint") != expected.get("fingerprint"):
        raise RuntimeError("manifest mismatch; create a new run_id")
    return actual


def assert_fixed_environment() -> None:
    forbidden = {
        "BAZI_RAG": "1",
        "BAZI_APB_BLOCK": "1",
    }
    active = [name for name, value in forbidden.items() if os.environ.get(name) == value]
    if os.environ.get("BAZI_FEWSHOT_FILE"):
        active.append("BAZI_FEWSHOT_FILE")
    if active:
        raise RuntimeError(f"fixed Phase 5 configuration violated by: {', '.join(active)}")


def validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", run_id):
        raise ValueError(
            "run_id must be 1-80 characters using only letters, digits, '.', '_' or '-'"
        )


def assert_fixed_config(config: ExperimentConfig) -> None:
    actual = (
        config.provider,
        config.model,
        config.method,
        config.temperature,
    )
    expected = ("deepseek", "deepseek-chat", "direct_choice", 0.0)
    if actual != expected:
        raise RuntimeError(f"fixed Phase 5 configuration mismatch: {actual!r}")
```

注意：manifest 只记录 `EXPERIMENT_SCOPE`，绝不执行无路径限定的 `git status` 并写入产物，避免把 `.env` 等无关敏感路径纳入记录。`scope_hashes` 本身位于 `immutable` 内，因此 `fingerprint` 已包含所有显式作用域文件哈希；`--resume` 会重建 expected manifest 并比较 fingerprint，代码漂移无需第二套重复校验。`fingerprint_scope` 明确声明未自动计算完整 Python 间接依赖闭包，避免把显式文件指纹误解为全依赖指纹。

- [ ] **Step 4: 运行 manifest 测试确认通过**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: `12 passed`。

- [ ] **Step 5: 提交 manifest 实现**

```powershell
git add scripts/run_phase5_c2_generalization.py tests/test_phase5_c2_generalization.py
git commit -m "feat: freeze Phase 5 experiment manifests"
```

## Task 3: Scorer-only gate 与 2023 主动密封

**Files:**
- Modify: `scripts/run_phase5_c2_generalization.py`
- Modify: `tests/test_phase5_c2_generalization.py`

- [ ] **Step 1: 写入四项门禁和密封测试**

追加到测试文件：

```python
def passing_metrics() -> dict:
    return {
        "top_score_hit_rate": 0.36,
        "score_answer_correlation": 0.11,
        "neutral_option_rate": 0.49,
        "strong_signal_option_rate": 0.31,
    }


def test_offline_gate_reports_values_thresholds_margins():
    result = phase5.evaluate_offline_gate(passing_metrics())

    assert result["passed"] is True
    assert result["metrics"]["top_score_hit_rate"] == {
        "value": 0.36,
        "operator": ">",
        "threshold": 0.35,
        "margin": pytest.approx(0.01),
        "passed": True,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("top_score_hit_rate", 0.35),
        ("score_answer_correlation", 0.10),
        ("neutral_option_rate", 0.50),
        ("strong_signal_option_rate", 0.30),
    ],
)
def test_offline_gate_uses_strict_boundaries(name: str, value: float):
    metrics = passing_metrics()
    metrics[name] = value
    assert phase5.evaluate_offline_gate(metrics)["passed"] is False


def test_2023_cannot_be_read_without_final_unlock(tmp_path: Path):
    config = phase5.ExperimentConfig(
        run_id="r1",
        root=tmp_path,
        years=(2023,),
        final_2023=False,
    )

    with pytest.raises(RuntimeError, match="2023 is sealed"):
        phase5.assert_year_access(config, 2023, prior_summary=None)


def test_2023_requires_prior_results_and_frozen_candidate(tmp_path: Path):
    config = phase5.ExperimentConfig(
        run_id="r1",
        root=tmp_path,
        years=(2023,),
        final_2023=True,
        candidate_id="candidate-a",
    )
    prior = {"years": {"2021": {}, "2022": {}}, "decision": "NON_INFERIOR"}
    phase5.write_json(tmp_path / "manifest.json", {"run_id": "r1"})

    phase5.assert_year_access(config, 2023, prior_summary=prior)
    with pytest.raises(RuntimeError, match="candidate_id"):
        phase5.assert_year_access(
            phase5.ExperimentConfig(
                run_id="r1",
                root=tmp_path,
                years=(2023,),
                final_2023=True,
            ),
            2023,
            prior_summary=prior,
        )
```

- [ ] **Step 2: 运行新增测试确认失败**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: FAIL because `evaluate_offline_gate` and `assert_year_access` do not exist。

- [ ] **Step 3: 实现离线门禁和主动密封检查**

追加到脚本：

```python
def evaluate_offline_gate(summary: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, dict[str, Any]] = {}
    for name, (operator, threshold) in OFFLINE_THRESHOLDS.items():
        value = float(summary[name])
        passed = value > threshold if operator == ">" else value < threshold
        margin = value - threshold if operator == ">" else threshold - value
        metrics[name] = {
            "value": value,
            "operator": operator,
            "threshold": threshold,
            "margin": margin,
            "passed": passed,
        }
    return {
        "passed": all(metric["passed"] for metric in metrics.values()),
        "metrics": metrics,
    }


def run_offline_gate(
    year: int,
    cases: list[dict[str, Any]],
    output: str | Path,
    scorer: Callable[[list[dict]], dict] = summarize_scores,
) -> dict[str, Any]:
    summary = scorer(cases)
    result = {
        "year": year,
        "gate": evaluate_offline_gate(summary),
        "scorer_summary": summary,
        "c2_applicability": classify_c2_applicability(cases),
    }
    write_json(output, result)
    return result


def assert_year_access(
    config: ExperimentConfig,
    year: int,
    prior_summary: dict[str, Any] | None,
) -> None:
    if year != 2023:
        return
    if not config.final_2023:
        raise RuntimeError("2023 is sealed; pass --final-2023 only after candidate freeze")
    if not config.candidate_id:
        raise RuntimeError("2023 requires a frozen candidate_id")
    initial_manifest_path = config.root / "manifest.json"
    if not initial_manifest_path.is_file():
        raise RuntimeError("2023 requires the immutable 2021/2022 manifest")
    initial_manifest = json.loads(initial_manifest_path.read_text(encoding="utf-8"))
    if initial_manifest.get("run_id") != config.run_id:
        raise RuntimeError("2023 run_id does not match the validation manifest")
    years = (prior_summary or {}).get("years", {})
    if not {"2021", "2022"}.issubset(years):
        raise RuntimeError("2023 requires completed 2021 and 2022 results")
    if (prior_summary or {}).get("decision") == "ROLLBACK":
        raise RuntimeError("2023 remains sealed after validation ROLLBACK")
```

CLI 主流程必须先对 2021 和 2022 全部执行 `run_offline_gate()`，确认两年都通过后才能进入任一 API 调用。不得边完成 2021 gate 边启动 2021 API。

- [ ] **Step 4: 运行 Task 3 测试确认通过**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: `19 passed`。

- [ ] **Step 5: 提交离线门禁**

```powershell
git add scripts/run_phase5_c2_generalization.py tests/test_phase5_c2_generalization.py
git commit -m "feat: gate and seal Phase 5 validation years"
```

## Task 4: AB/BA 调度、逐 attempt 持久化与恢复

**Files:**
- Modify: `scripts/run_phase5_c2_generalization.py`
- Modify: `tests/test_phase5_c2_generalization.py`

- [ ] **Step 1: 写入调度、runner 参数和恢复测试**

追加到测试文件：

```python
def test_balanced_schedule_is_reproducible():
    cases = [sample_case(f"c{i}") for i in range(5)]

    first = phase5.build_schedule(cases, seed=7)
    second = phase5.build_schedule(cases, seed=7)

    assert first == second
    assert abs(
        sum(pair[0] == "direct" for _, pair in first)
        - sum(pair[0] == "direct_c2" for _, pair in first)
    ) <= 1
    assert all(set(pair) == {"direct", "direct_c2"} for _, pair in first)


def test_each_year_has_a_recorded_derived_schedule_seed(tmp_path: Path):
    config = phase5.ExperimentConfig("r1", tmp_path, (2021, 2022), seed=7)

    assert phase5.year_schedule_seed(config, 2021) == 2028
    assert phase5.year_schedule_seed(config, 2022) == 2029


def test_run_attempt_passes_no_case_details_and_persists(tmp_path: Path):
    calls = []

    def fake_runner(cases, provider, model, prompt_version, **kwargs):
        calls.append(kwargs)
        case = cases[0]
        return {
            "case_details": [{
                "case_id": case["case_id"],
                "expected_answer": case["answer"],
                "predicted_answer": "B",
                "raw_answer": "B",
                "parser_source": "legacy",
                "parser_valid": True,
                "correct": True,
                "call_success": True,
                "phase4_option_scores": [],
            }],
            "failed_cases": [],
        }

    path = tmp_path / "attempts.jsonl"
    config = phase5.ExperimentConfig("r1", tmp_path, (2021,))
    phase5.write_json(config.root / "manifest.json", {"fingerprint": "fp"})
    row = phase5.run_attempt(
        config,
        2021,
        sample_case(),
        "direct_c2",
        1,
        path,
        fake_runner,
    )

    assert calls[0]["case_details_jsonl"] is None
    assert calls[0]["phase4_direct_c2"] is True
    assert calls[0]["n_samples"] == 1
    assert row["arm"] == "direct_c2"
    assert phase5.load_jsonl(path) == [row]


def test_completed_attempt_is_not_called_again(tmp_path: Path):
    path = tmp_path / "attempts.jsonl"
    existing = {
        "run_id": "r1",
        "year": 2021,
        "case_id": "c1",
        "arm": "direct",
        "attempt": 1,
    }
    phase5.append_jsonl(path, existing)
    calls = []

    result = phase5.run_attempt(
        phase5.ExperimentConfig("r1", tmp_path, (2021,), resume=True),
        2021,
        sample_case(),
        "direct",
        1,
        path,
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert result == existing
    assert calls == []


def test_failure_marker_is_persisted(tmp_path: Path):
    def failing_runner(*args, **kwargs):
        raise TimeoutError("temporary timeout")

    path = tmp_path / "attempts.jsonl"
    phase5.write_json(tmp_path / "manifest.json", {"fingerprint": "fp"})
    row = phase5.run_attempt(
        phase5.ExperimentConfig("r1", tmp_path, (2021,)),
        2021,
        sample_case(),
        "direct",
        1,
        path,
        failing_runner,
    )

    assert row["call_success"] is False
    assert row["parser_valid"] is False
    assert row["failure"] == "TimeoutError: temporary timeout"
    assert len(phase5.load_jsonl(path)) == 1
```

- [ ] **Step 2: 运行新增测试确认失败**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: FAIL because scheduling and attempt functions do not exist。

- [ ] **Step 3: 实现可恢复调度和模型边界**

追加到脚本：

```python
def year_schedule_seed(config: ExperimentConfig, year: int) -> int:
    return config.seed + year


def build_schedule(
    cases: list[dict[str, Any]],
    seed: int,
) -> list[tuple[dict[str, Any], tuple[str, str]]]:
    ordered = list(cases)
    random.Random(seed).shuffle(ordered)
    return [
        (case, ("direct", "direct_c2") if index % 2 == 0 else ("direct_c2", "direct"))
        for index, case in enumerate(ordered)
    ]


def attempt_key(row: dict[str, Any]) -> tuple[str, int, str, str, int]:
    return (
        row["run_id"],
        int(row["year"]),
        row["case_id"],
        row["arm"],
        int(row["attempt"]),
    )


def load_attempt_index(path: str | Path) -> dict[tuple[str, int, str, str, int], dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return {}
    rows = load_jsonl(target)
    index: dict[tuple[str, int, str, str, int], dict[str, Any]] = {}
    for row in rows:
        key = attempt_key(row)
        if key in index:
            raise RuntimeError(f"duplicate attempt key: {key}")
        index[key] = row
    return index


def run_attempt(
    config: ExperimentConfig,
    year: int,
    case: dict[str, Any],
    arm: str,
    attempt: int,
    attempts_path: str | Path,
    runner: Runner = run_model_benchmark,
) -> dict[str, Any]:
    if arm not in {"direct", "direct_c2"}:
        raise ValueError(f"unsupported arm: {arm}")
    key = (config.run_id, year, case["case_id"], arm, attempt)
    existing = load_attempt_index(attempts_path).get(key)
    if existing is not None:
        return existing
    started = time.perf_counter()
    manifest_path = config.root / ("final_manifest.json" if config.final_2023 else "manifest.json")
    manifest_fingerprint = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )["fingerprint"]
    try:
        result = runner(
            [case],
            config.provider,
            config.model,
            config.prompt_version,
            max_cases=1,
            method=config.method,
            temperature=config.temperature,
            case_details_jsonl=None,
            rag_k=2,
            n_samples=1,
            phase4_direct_c2=arm == "direct_c2",
        )
        details = result.get("case_details") or []
        if len(details) != 1:
            raise RuntimeError("single-case runner did not return exactly one detail")
        detail = details[0]
        record = {
            "run_id": config.run_id,
            "year": year,
            "case_id": case["case_id"],
            "arm": arm,
            "attempt": attempt,
            "provider": config.provider,
            "model": config.model,
            "method": config.method,
            "prompt_version": config.prompt_version,
            "temperature": config.temperature,
            "rag": False,
            "few_shot": False,
            "apb": False,
            "two_stage": False,
            "manifest_fingerprint": manifest_fingerprint,
            "raw_answer": detail.get("raw_answer"),
            "predicted_answer": detail.get("predicted_answer"),
            "expected_answer": extract_choice(case.get("answer")),
            "parser_source": detail.get("parser_source"),
            "parser_valid": detail.get("parser_valid") is True,
            "correct": detail.get("correct") is True,
            "call_success": detail.get("call_success") is not False,
            "failure": None,
            "transport_retry_count": detail.get("transport_retry_count"),
            "phase4_option_scores": detail.get("phase4_option_scores", []),
            "retrieved_answer_leak": detail.get("retrieved_answer_leak", False),
            "elapsed_seconds": time.perf_counter() - started,
            "runner_pacing_seconds": 1.0,
        }
    except Exception as exc:
        record = {
            "run_id": config.run_id,
            "year": year,
            "case_id": case["case_id"],
            "arm": arm,
            "attempt": attempt,
            "provider": config.provider,
            "model": config.model,
            "method": config.method,
            "prompt_version": config.prompt_version,
            "temperature": config.temperature,
            "rag": False,
            "few_shot": False,
            "apb": False,
            "two_stage": False,
            "manifest_fingerprint": manifest_fingerprint,
            "raw_answer": None,
            "predicted_answer": None,
            "expected_answer": extract_choice(case.get("answer")),
            "parser_source": "none",
            "parser_valid": False,
            "correct": False,
            "call_success": False,
            "failure": f"{type(exc).__name__}: {exc}",
            "transport_retry_count": None,
            "phase4_option_scores": [],
            "retrieved_answer_leak": False,
            "elapsed_seconds": time.perf_counter() - started,
            "runner_pacing_seconds": 0.0,
        }
    append_jsonl(attempts_path, record)
    return record


def run_initial_pairs(
    config: ExperimentConfig,
    year: int,
    cases: list[dict[str, Any]],
    attempts_path: str | Path,
    runner: Runner = run_model_benchmark,
) -> list[dict[str, Any]]:
    records = []
    for case, arms in build_schedule(cases, year_schedule_seed(config, year)):
        for arm in arms:
            records.append(run_attempt(config, year, case, arm, 1, attempts_path, runner))
    return records
```

不捕获 `KeyboardInterrupt`/`SystemExit`，它们不是 `Exception`；已有逐条 `fsync` 记录可供下次 `--resume` 恢复。现有 `run_model_benchmark()`/`call_model_sync()` 接口不暴露底层 HTTP 重试次数，因此记录字段固定为 `transport_retry_count`：runner 将来返回该字段时原样保存，否则写 `null`，不得把分歧题的独立重复调用伪装成传输重试次数。

- [ ] **Step 4: 运行 Task 4 测试确认通过**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: `24 passed`。

- [ ] **Step 5: 运行现有 runner 关联测试**

Run: `python -m pytest tests/test_benchmark_runner.py tests/test_per_option_scorer.py tests/test_enrich_holdout_chart_input.py -q`

Expected: all selected tests PASS；不得改变这些文件来迎合新编排器。

- [ ] **Step 6: 提交模型调用边界**

```powershell
git add scripts/run_phase5_c2_generalization.py tests/test_phase5_c2_generalization.py
git commit -m "feat: persist paired Phase 5 model attempts"
```

## Task 5: 分歧题复测、有效票多数与年度止损

**Files:**
- Modify: `scripts/run_phase5_c2_generalization.py`
- Modify: `tests/test_phase5_c2_generalization.py`

- [ ] **Step 1: 写入分歧复测和多数票边界测试**

追加到测试文件：

```python
def attempt(case_id: str, arm: str, number: int, choice: str | None, valid: bool = True) -> dict:
    return {
        "run_id": "r1",
        "year": 2021,
        "case_id": case_id,
        "arm": arm,
        "attempt": number,
        "predicted_answer": choice,
        "expected_answer": "B",
        "parser_valid": valid,
        "correct": valid and choice == "B",
        "call_success": valid,
        "retrieved_answer_leak": False,
    }


def test_only_initial_disagreements_are_retested(tmp_path: Path):
    rows = [
        attempt("same", "direct", 1, "B"),
        attempt("same", "direct_c2", 1, "B"),
        attempt("diff", "direct", 1, "A"),
        attempt("diff", "direct_c2", 1, "B"),
    ]

    assert phase5.disagreement_case_ids(rows) == ["diff"]


def test_majority_vote_uses_only_valid_votes_and_marks_tie_unresolved():
    majority = phase5.resolve_arm([
        attempt("c1", "direct", 1, "B"),
        attempt("c1", "direct", 2, "B"),
        attempt("c1", "direct", 3, None, valid=False),
    ])
    tie = phase5.resolve_arm([
        attempt("c1", "direct", 1, "A"),
        attempt("c1", "direct", 2, "B"),
        attempt("c1", "direct", 3, None, valid=False),
    ])

    assert majority["choice"] == "B"
    assert majority["unresolved"] is False
    assert tie["choice"] is None
    assert tie["unresolved"] is True


def test_all_invalid_is_counted_separately():
    result = phase5.resolve_arm([
        attempt("c1", "direct", 1, None, valid=False),
        attempt("c1", "direct", 2, None, valid=False),
        attempt("c1", "direct", 3, None, valid=False),
    ])

    assert result["unresolved"] is True
    assert result["all_invalid"] is True


def test_repeat_consistency_distinguishes_unanimous_majority_and_unresolved():
    rows = [
        attempt("same", "direct", 1, "B"),
        attempt("same", "direct", 2, "B"),
        attempt("same", "direct", 3, "B"),
        attempt("split", "direct_c2", 1, "A"),
        attempt("split", "direct_c2", 2, "B"),
        attempt("split", "direct_c2", 3, "B"),
        attempt("invalid", "direct", 1, "A"),
        attempt("invalid", "direct", 2, "B"),
        attempt("invalid", "direct", 3, None, valid=False),
    ]

    assert phase5.summarize_repeat_consistency(rows) == {
        "unanimous": 1,
        "majority_2_to_1": 1,
        "unresolved": 1,
    }


def test_initial_regression_stop_triggers_at_four():
    rows = []
    for index in range(4):
        case_id = f"c{index}"
        rows.extend([
            attempt(case_id, "direct", 1, "B"),
            attempt(case_id, "direct_c2", 1, "A"),
        ])

    assert phase5.count_initial_rescues_regressions(rows) == {"rescues": 0, "regressions": 4}
    assert phase5.should_stop_after_initial(rows) is True
```

- [ ] **Step 2: 运行新增测试确认失败**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: FAIL because disagreement, vote and stop functions do not exist。

- [ ] **Step 3: 实现分歧识别、多数票和止损**

追加到脚本：

```python
def disagreement_case_ids(rows: list[dict[str, Any]]) -> list[str]:
    initial = {
        (row["case_id"], row["arm"]): row
        for row in rows
        if int(row["attempt"]) == 1
    }
    case_ids = sorted({row["case_id"] for row in rows})
    return [
        case_id
        for case_id in case_ids
        if initial[(case_id, "direct")].get("predicted_answer")
        != initial[(case_id, "direct_c2")].get("predicted_answer")
    ]


def resolve_arm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid_choices = [
        row.get("predicted_answer")
        for row in rows
        if row.get("parser_valid") is True and row.get("predicted_answer")
    ]
    counts = Counter(valid_choices)
    winner = counts.most_common(1)[0][0] if counts else None
    has_majority = winner is not None and counts[winner] > len(valid_choices) / 2
    return {
        "choice": winner if has_majority else None,
        "unresolved": not has_majority,
        "all_invalid": not valid_choices,
        "valid_votes": len(valid_choices),
        "vote_counts": dict(counts),
    }


# No fourth tie-break request is allowed. A/B/C or valid/invalid ties remain
# unresolved and therefore do not contribute a correct answer for that arm.


def summarize_repeat_consistency(rows: list[dict[str, Any]]) -> dict[str, int]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["case_id"], row["arm"]), []).append(row)
    summary = {"unanimous": 0, "majority_2_to_1": 0, "unresolved": 0}
    for arm_rows in grouped.values():
        if len(arm_rows) != 3:
            continue
        valid_choices = [
            row.get("predicted_answer")
            for row in arm_rows
            if row.get("parser_valid") is True and row.get("predicted_answer")
        ]
        resolved = resolve_arm(arm_rows)
        if len(valid_choices) == 3 and len(set(valid_choices)) == 1:
            summary["unanimous"] += 1
        elif resolved["unresolved"]:
            summary["unresolved"] += 1
        else:
            summary["majority_2_to_1"] += 1
    return summary


def count_initial_rescues_regressions(rows: list[dict[str, Any]]) -> dict[str, int]:
    by_case_arm = {
        (row["case_id"], row["arm"]): row
        for row in rows
        if int(row["attempt"]) == 1
    }
    rescues = 0
    regressions = 0
    for case_id in {row["case_id"] for row in rows}:
        direct = by_case_arm[(case_id, "direct")].get("correct") is True
        c2 = by_case_arm[(case_id, "direct_c2")].get("correct") is True
        rescues += int(c2 and not direct)
        regressions += int(direct and not c2)
    return {"rescues": rescues, "regressions": regressions}


def should_stop_after_initial(rows: list[dict[str, Any]]) -> bool:
    cross = count_initial_rescues_regressions(rows)
    return cross["regressions"] - cross["rescues"] >= 4


def run_disagreement_retests(
    config: ExperimentConfig,
    year: int,
    cases: list[dict[str, Any]],
    attempts_path: str | Path,
    runner: Runner = run_model_benchmark,
) -> list[dict[str, Any]]:
    existing = load_jsonl(attempts_path)
    disagreements = set(disagreement_case_ids(existing))
    case_map = {case["case_id"]: case for case in cases}
    records = []
    for case_id in sorted(disagreements):
        for attempt_number in (2, 3):
            for arm in ("direct", "direct_c2"):
                records.append(
                    run_attempt(
                        config,
                        year,
                        case_map[case_id],
                        arm,
                        attempt_number,
                        attempts_path,
                        runner,
                    )
                )
    return records
```

attempt 2/3 必须继续使用 `config.temperature == 0.0`。复测测量的是相同配置下已在 `docs/BAZIQA_TRACE_DIAGNOSIS_REPORT.md` 实测出现的 API 非确定性；改成 `0.4` 会引入新的实验变量，使多数票不再代表原配置的稳定结论。若三次完全一致，`summarize_repeat_consistency()` 将其记录为 `unanimous` 确定性行为证据，而不是判为复测失败。`all_invalid` 是 arm 级指标：direct 和 direct_c2 各自三次全部不可解析时分别计 1，因此同一题两个 arm 都全无效时总计 2。报告使用 “all-invalid arms” 明示这个分母，不把它误解为题目数。

- [ ] **Step 4: 运行 Task 5 测试确认通过**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: `29 passed`。

- [ ] **Step 5: 提交自适应复测**

```powershell
git add scripts/run_phase5_c2_generalization.py tests/test_phase5_c2_generalization.py
git commit -m "feat: retest only Phase 5 disagreements"
```

## Task 6: 汇总、精确 McNemar 与三档最终判定

**Files:**
- Modify: `scripts/run_phase5_c2_generalization.py`
- Modify: `tests/test_phase5_c2_generalization.py`

- [ ] **Step 1: 写入统计与判定边界测试**

追加到测试文件：

```python
def test_exact_mcnemar_uses_two_sided_binomial():
    assert phase5.exact_mcnemar_pvalue(0, 0) == 1.0
    assert phase5.exact_mcnemar_pvalue(1, 5) == pytest.approx(0.21875)
    assert phase5.exact_mcnemar_pvalue(5, 1) == pytest.approx(0.21875)


def decision_input(rescues: int, regressions: int) -> dict:
    return {
        "total": 120,
        "direct_correct": 40,
        "c2_correct": 40 + rescues - regressions,
        "rescues": rescues,
        "regressions": regressions,
        "non_degrading_years": 2,
        "parser_valid_rate": 0.96,
        "confirmed_answer_leaks": 0,
    }


def test_final_decision_boundaries():
    assert phase5.decide_final(decision_input(3, 2))["decision"] == "PROMOTE"
    assert phase5.decide_final(decision_input(2, 2))["decision"] == "NON_INFERIOR"
    assert phase5.decide_final(decision_input(2, 3))["decision"] == "ROLLBACK"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("c2_correct", 39),
        ("non_degrading_years", 1),
        ("regressions", 13),
        ("parser_valid_rate", 0.949),
        ("confirmed_answer_leaks", 1),
    ],
)
def test_any_hard_gate_failure_rolls_back(field: str, value):
    metrics = decision_input(3, 2)
    metrics[field] = value
    assert phase5.decide_final(metrics)["decision"] == "ROLLBACK"


def test_summary_stratifies_c2_applicability_and_parser_sources():
    results = [
        {
            "case_id": "active",
            "year": 2021,
            "domain": "wealth",
            "c2_effective": True,
            "direct": {"correct": False, "all_invalid": False, "unresolved": False},
            "direct_c2": {"correct": True, "all_invalid": False, "unresolved": False},
        },
        {
            "case_id": "noop",
            "year": 2021,
            "domain": "unknown",
            "c2_effective": False,
            "direct": {"correct": True, "all_invalid": False, "unresolved": False},
            "direct_c2": {"correct": True, "all_invalid": False, "unresolved": False},
        },
    ]
    attempts = [
        {"case_id": "active", "arm": "direct", "parser_source": "final_answer", "parser_valid": True},
        {"case_id": "active", "arm": "direct_c2", "parser_source": "confidence", "parser_valid": True},
    ]

    summary = phase5.summarize_stable_results(results, attempts)

    assert summary["by_c2_applicability"]["effective"]["rescues"] == 1
    assert summary["by_c2_applicability"]["noop"]["both_correct"] == 1
    assert summary["parser_source_by_arm"] == {
        "direct": {"final_answer": 1},
        "direct_c2": {"confidence": 1},
    }
```

- [ ] **Step 2: 运行新增测试确认失败**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: FAIL because exact test and final decision functions do not exist。

- [ ] **Step 3: 实现精确检验、逐题稳定结果和 gate**

追加到脚本：

```python
def exact_mcnemar_pvalue(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if discordant == 0:
        return 1.0
    tail = min(left_only, right_only)
    probability = sum(
        math.comb(discordant, k) * (0.5 ** discordant)
        for k in range(tail + 1)
    )
    return min(1.0, 2.0 * probability)


def stable_case_results(
    cases: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in attempts:
        grouped.setdefault((row["case_id"], row["arm"]), []).append(row)
    results = []
    for case in cases:
        case_id = case["case_id"]
        expected = extract_choice(case.get("answer"))
        direct = resolve_arm(grouped[(case_id, "direct")])
        c2_rows = grouped[(case_id, "direct_c2")]
        c2 = resolve_arm(c2_rows)
        results.append({
            "case_id": case_id,
            "year": int(case["source_year"]),
            "domain": case.get("domain", "unknown"),
            "expected_answer": expected,
            "c2_effective": any(row.get("phase4_option_scores") for row in c2_rows),
            "direct": {**direct, "correct": direct["choice"] == expected},
            "direct_c2": {**c2, "correct": c2["choice"] == expected},
        })
    return results


def summarize_stable_results(
    results: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    direct_correct = sum(row["direct"]["correct"] for row in results)
    c2_correct = sum(row["direct_c2"]["correct"] for row in results)
    rescues = sum(
        row["direct_c2"]["correct"] and not row["direct"]["correct"]
        for row in results
    )
    regressions = sum(
        row["direct"]["correct"] and not row["direct_c2"]["correct"]
        for row in results
    )
    by_year = {}
    for year in sorted({row["year"] for row in results}):
        year_rows = [row for row in results if row["year"] == year]
        year_direct = sum(row["direct"]["correct"] for row in year_rows)
        year_c2 = sum(row["direct_c2"]["correct"] for row in year_rows)
        by_year[str(year)] = {
            "total": len(year_rows),
            "direct_correct": year_direct,
            "c2_correct": year_c2,
            "non_degrading": year_c2 >= year_direct,
        }
    by_domain = {}
    for domain in sorted({row["domain"] for row in results}):
        domain_rows = [row for row in results if row["domain"] == domain]
        by_domain[domain] = {
            "total": len(domain_rows),
            "direct_correct": sum(row["direct"]["correct"] for row in domain_rows),
            "c2_correct": sum(row["direct_c2"]["correct"] for row in domain_rows),
        }
    parser_valid = sum(row.get("parser_valid") is True for row in attempts)
    parser_source_by_arm = {
        arm: dict(Counter(
            row.get("parser_source") or "none"
            for row in attempts
            if row.get("arm") == arm
        ))
        for arm in ("direct", "direct_c2")
    }
    by_c2_applicability = {}
    for label, effective in (("effective", True), ("noop", False)):
        group = [row for row in results if row.get("c2_effective") is effective]
        by_c2_applicability[label] = {
            "total": len(group),
            "direct_correct": sum(row["direct"]["correct"] for row in group),
            "c2_correct": sum(row["direct_c2"]["correct"] for row in group),
            "rescues": sum(row["direct_c2"]["correct"] and not row["direct"]["correct"] for row in group),
            "regressions": sum(row["direct"]["correct"] and not row["direct_c2"]["correct"] for row in group),
            "both_correct": sum(row["direct"]["correct"] and row["direct_c2"]["correct"] for row in group),
            "both_wrong": sum(not row["direct"]["correct"] and not row["direct_c2"]["correct"] for row in group),
        }
    elapsed_seconds = sum(float(row.get("elapsed_seconds", 0.0)) for row in attempts)
    pacing_seconds = sum(float(row.get("runner_pacing_seconds", 0.0)) for row in attempts)
    return {
        "total": len(results),
        "direct_correct": direct_correct,
        "c2_correct": c2_correct,
        "rescues": rescues,
        "regressions": regressions,
        "both_correct": sum(row["direct"]["correct"] and row["direct_c2"]["correct"] for row in results),
        "both_wrong": sum(not row["direct"]["correct"] and not row["direct_c2"]["correct"] for row in results),
        "non_degrading_years": sum(item["non_degrading"] for item in by_year.values()),
        "parser_valid_attempts": parser_valid,
        "parser_total_attempts": len(attempts),
        "parser_valid_rate": parser_valid / len(attempts) if attempts else 0.0,
        "all_invalid": sum(row[arm]["all_invalid"] for row in results for arm in ("direct", "direct_c2")),
        "unresolved": sum(row[arm]["unresolved"] for row in results for arm in ("direct", "direct_c2")),
        "confirmed_answer_leaks": sum(bool(row.get("retrieved_answer_leak")) for row in attempts),
        "elapsed_seconds": elapsed_seconds,
        "pacing_seconds": pacing_seconds,
        "estimated_model_seconds": max(0.0, elapsed_seconds - pacing_seconds),
        "repeat_consistency": summarize_repeat_consistency(attempts),
        "mcnemar_exact_p": exact_mcnemar_pvalue(regressions, rescues),
        "by_year": by_year,
        "by_domain": by_domain,
        "by_c2_applicability": by_c2_applicability,
        "parser_source_by_arm": parser_source_by_arm,
    }


def decide_final(metrics: dict[str, Any]) -> dict[str, Any]:
    gates = {
        "c2_not_worse": metrics["c2_correct"] >= metrics["direct_correct"],
        "two_non_degrading_years": metrics["non_degrading_years"] >= 2,
        "regressions_at_most_12": metrics["regressions"] <= 12,
        "parser_valid_at_least_95pct": metrics["parser_valid_rate"] >= 0.95,
        "no_confirmed_answer_leak": metrics["confirmed_answer_leaks"] == 0,
    }
    if not all(gates.values()):
        decision = "ROLLBACK"
    elif metrics["rescues"] > metrics["regressions"]:
        decision = "PROMOTE"
    else:
        decision = "NON_INFERIOR"
    return {"decision": decision, "gates": gates}
```

`NON_INFERIOR` 只在所有硬门槛通过且 `rescues == regressions` 时出现；如果 `rescues < regressions`，`c2_not_worse` 必然失败并进入 `ROLLBACK`。

- [ ] **Step 4: 运行 Task 6 测试确认通过**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: `37 passed`。

- [ ] **Step 5: 提交统计判定**

```powershell
git add scripts/run_phase5_c2_generalization.py tests/test_phase5_c2_generalization.py
git commit -m "feat: decide Phase 5 generalization gates"
```

## Task 7: CLI 编排、报告重建与持久化审计产物

**Files:**
- Modify: `scripts/run_phase5_c2_generalization.py`
- Modify: `tests/test_phase5_c2_generalization.py`

- [ ] **Step 1: 写入端到端 fake-runner 测试**

追加到测试文件：

```python
def test_run_validation_uses_fake_runner_and_writes_summary(tmp_path: Path, monkeypatch):
    cases = [sample_case("c1"), sample_case("c2")]
    for year in (2021, 2022):
        year_rows = [{**row, "source_year": str(year)} for row in cases]
        write_jsonl(tmp_path / f"source-{year}.jsonl", year_rows)

    monkeypatch.setattr(phase5, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(phase5, "EXPERIMENT_SCOPE", ())
    monkeypatch.setattr(phase5, "git_output", lambda *args: "deadbeef")
    monkeypatch.setattr(phase5, "experiment_scope_status", lambda: {})
    monkeypatch.setattr(phase5, "enrich_row", fake_enrich)
    monkeypatch.setattr(
        phase5,
        "summarize_scores",
        lambda rows: {**passing_metrics(), "n_cases": len(rows), "cases": []},
    )

    def fake_runner(cases, provider, model, prompt_version, **kwargs):
        case = cases[0]
        return {
            "case_details": [{
                "case_id": case["case_id"],
                "expected_answer": case["answer"],
                "predicted_answer": case["answer"],
                "raw_answer": case["answer"],
                "parser_source": "legacy",
                "parser_valid": True,
                "correct": True,
                "call_success": True,
                "phase4_option_scores": [],
                "retrieved_answer_leak": False,
            }],
            "failed_cases": [],
        }

    config = phase5.ExperimentConfig("r1", tmp_path / "work", (2021, 2022))
    source_paths = {year: tmp_path / f"source-{year}.jsonl" for year in config.years}
    result = phase5.run_validation(
        config,
        source_paths,
        runner=fake_runner,
        expected_rows=2,
    )

    assert result["decision"] == "NON_INFERIOR"
    assert result["total"] == 4
    assert (config.root / "summary.json").is_file()
    assert (config.root / "runs" / "2021" / "attempts.jsonl").is_file()
    initial_manifest_hash = phase5.sha256_file(config.root / "manifest.json")

    rows_2023 = [{**row, "source_year": "2023"} for row in cases]
    source_2023 = tmp_path / "source-2023.jsonl"
    write_jsonl(source_2023, rows_2023)
    final_config = phase5.ExperimentConfig(
        "r1",
        config.root,
        (2023,),
        final_2023=True,
        candidate_id="candidate-direct-c2-v1",
    )
    final = phase5.run_validation(
        final_config,
        {2023: source_2023},
        runner=fake_runner,
        expected_rows=2,
    )

    assert final["total"] == 6
    assert (config.root / "final_manifest.json").is_file()
    assert phase5.sha256_file(config.root / "manifest.json") == initial_manifest_hash
    archive_dir = tmp_path / "docs" / "phase5" / "r1"
    assert (archive_dir / "manifest.json").is_file()
    assert (archive_dir / "summary.json").is_file()
    assert (archive_dir / "report.md").is_file()


def test_run_validation_rejects_rag_before_model_call(tmp_path: Path, monkeypatch):
    called = {"runner": False}

    def forbidden_runner(*args, **kwargs):
        called["runner"] = True
        raise AssertionError("runner must not be called")

    monkeypatch.setenv("BAZI_RAG", "1")
    config = phase5.ExperimentConfig("rag-off", tmp_path / "work", (2021, 2022))

    with pytest.raises(RuntimeError, match="BAZI_RAG"):
        phase5.run_validation(config, {}, runner=forbidden_runner)

    assert called["runner"] is False


def test_final_2023_offline_failure_preserves_prior_results(tmp_path: Path, monkeypatch):
    work = tmp_path / "work"
    source_2023 = tmp_path / "source-2023.jsonl"
    write_jsonl(source_2023, [{**sample_case("final-c1"), "source_year": "2023"}])
    prior_case_results = [{"case_id": "prior-c1", "year": 2021}]
    prior_years = {
        "2021": {"total": 40, "direct_correct": 10, "c2_correct": 11},
        "2022": {"total": 40, "direct_correct": 12, "c2_correct": 12},
    }
    prior_summary = {
        "decision": "NON_INFERIOR",
        "years": prior_years,
        "case_results": prior_case_results,
        "offline": {
            "2021": {"gate": {"passed": True}},
            "2022": {"gate": {"passed": True}},
        },
    }
    phase5.write_json(work / "manifest.json", {"run_id": "r1"})
    phase5.write_json(work / "summary.json", prior_summary)
    monkeypatch.setattr(phase5, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(phase5, "EXPERIMENT_SCOPE", ())
    monkeypatch.setattr(phase5, "git_output", lambda *args: "deadbeef")
    monkeypatch.setattr(phase5, "experiment_scope_status", lambda: {})
    monkeypatch.setattr(phase5, "enrich_row", fake_enrich)
    monkeypatch.setattr(
        phase5,
        "summarize_scores",
        lambda rows: {
            **passing_metrics(),
            "top_score_hit_rate": 0.35,
            "n_cases": len(rows),
            "cases": [],
        },
    )
    called = {"runner": False}

    def forbidden_runner(*args, **kwargs):
        called["runner"] = True
        raise AssertionError("runner must not be called after offline gate failure")

    config = phase5.ExperimentConfig(
        "r1",
        work,
        (2023,),
        final_2023=True,
        candidate_id="candidate-direct-c2-v1",
    )
    summary = phase5.run_validation(
        config,
        {2023: source_2023},
        runner=forbidden_runner,
        expected_rows=1,
    )

    assert summary["decision"] == "ROLLBACK"
    assert summary["reason"] == "offline_gate_failed"
    assert summary["years"] == prior_years
    assert summary["case_results"] == prior_case_results
    assert set(summary["offline"]) == {"2021", "2022", "2023"}
    assert called["runner"] is False


def test_run_id_rejects_path_traversal():
    with pytest.raises(ValueError, match="run_id must be"):
        phase5.validate_run_id("../overwrite")


def test_run_validation_persists_auditable_year_stop(tmp_path: Path, monkeypatch):
    cases = [sample_case(f"c{i}") for i in range(4)]
    source = tmp_path / "source-2021.jsonl"
    write_jsonl(source, cases)
    monkeypatch.setattr(phase5, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(phase5, "EXPERIMENT_SCOPE", ())
    monkeypatch.setattr(phase5, "git_output", lambda *args: "deadbeef")
    monkeypatch.setattr(phase5, "experiment_scope_status", lambda: {})
    monkeypatch.setattr(phase5, "enrich_row", fake_enrich)
    monkeypatch.setattr(
        phase5,
        "summarize_scores",
        lambda rows: {**passing_metrics(), "n_cases": len(rows), "cases": []},
    )

    def harmful_c2_runner(cases, provider, model, prompt_version, **kwargs):
        case = cases[0]
        choice = "A" if kwargs["phase4_direct_c2"] else case["answer"]
        return {
            "case_details": [{
                "case_id": case["case_id"],
                "expected_answer": case["answer"],
                "predicted_answer": choice,
                "raw_answer": choice,
                "parser_source": "legacy",
                "parser_valid": True,
                "correct": choice == case["answer"],
                "call_success": True,
                "phase4_option_scores": [],
                "retrieved_answer_leak": False,
            }],
            "failed_cases": [],
        }

    config = phase5.ExperimentConfig("stop-r1", tmp_path / "stop-work", (2021,))
    summary = phase5.run_validation(
        config,
        {2021: source},
        runner=harmful_c2_runner,
        expected_rows=4,
    )

    assert summary["decision"] == "ROLLBACK"
    assert summary["reason"] == "year_stop"
    assert summary["initial_stop_metrics"]["regressions"] == 4
    assert len(summary["case_results"]) == 4
    assert summary["attempts_seen"] == 8
    persisted = json.loads((config.root / "summary.json").read_text(encoding="utf-8"))
    assert persisted == summary


def test_render_report_contains_gate_evidence():
    summary = {
        **decision_input(2, 2),
        "decision": "NON_INFERIOR",
        "gates": {"c2_not_worse": True},
        "mcnemar_exact_p": 1.0,
        "all_invalid": 0,
        "unresolved": 0,
        "both_correct": 0,
        "both_wrong": 0,
        "by_year": {},
        "by_domain": {},
        "offline": {},
    }
    report = phase5.render_report(summary, manifest_sha256="abc123")

    assert "NON_INFERIOR" in report
    assert "McNemar" in report
    assert "Discordant pairs: 4" in report
    assert "fewer than 10 discordant pairs" in report
    assert "abc123" in report
    assert "MingLi-Bench" not in report


def test_promote_report_recommends_mingli_without_inventing_command():
    summary = {
        **decision_input(3, 2),
        "decision": "PROMOTE",
        "gates": {},
        "mcnemar_exact_p": 0.5,
        "all_invalid": 0,
        "unresolved": 0,
        "both_correct": 0,
        "both_wrong": 0,
        "by_year": {},
        "by_domain": {},
        "offline": {},
    }
    report = phase5.render_report(summary, manifest_sha256="abc123")

    assert "进入 MingLi-Bench 非退化验证" in report
    assert "--c2-enabled" not in report
```

- [ ] **Step 2: 运行新增测试确认失败**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: FAIL because orchestration and report functions do not exist。

- [ ] **Step 3: 实现报告、归档和完整编排**

追加到脚本：

```python
def render_report(summary: dict[str, Any], manifest_sha256: str) -> str:
    lines = [
        "# Phase 5 C2 Independent Generalization Report",
        "",
        f"- Decision: **{summary['decision']}**",
        f"- Direct: {summary['direct_correct']}/{summary['total']}",
        f"- Direct+C2: {summary['c2_correct']}/{summary['total']}",
        f"- Rescues / regressions: {summary['rescues']} / {summary['regressions']}",
        f"- Both correct / both wrong: {summary['both_correct']} / {summary['both_wrong']}",
        f"- Parser valid rate (attempt-weighted): {summary['parser_valid_rate']:.1%} "
        f"({summary.get('parser_valid_attempts', 0)}/{summary.get('parser_total_attempts', 0)})",
        f"- Unresolved arms / all-invalid arms: {summary['unresolved']} / {summary['all_invalid']}",
        f"- Repeat consistency: {json.dumps(summary.get('repeat_consistency', {}), ensure_ascii=False)}",
        f"- Exact two-sided McNemar p: {summary['mcnemar_exact_p']:.6f}",
        f"- Discordant pairs: {summary['rescues'] + summary['regressions']}",
        f"- Elapsed / pacing seconds: {summary.get('elapsed_seconds', 0.0):.1f} / {summary.get('pacing_seconds', 0.0):.1f}",
        f"- Manifest SHA-256: `{manifest_sha256}`",
        "",
        "## Hard gates",
        "",
    ]
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in summary["gates"].items()
    )
    if summary["rescues"] + summary["regressions"] < 10:
        lines.append(
            "- Statistical caution: fewer than 10 discordant pairs; "
            "the exact p-value is highly sensitive to individual cases."
        )
    lines.extend(["", "## Per-year results", ""])
    for year, metrics in summary.get("by_year", {}).items():
        lines.append(
            f"- {year}: direct {metrics['direct_correct']}/{metrics['total']}, "
            f"direct+C2 {metrics['c2_correct']}/{metrics['total']}"
        )
    lines.extend(["", "## Offline scorer gates", ""])
    for year, payload in summary.get("offline", {}).items():
        lines.append(f"### {year}")
        for name, metric in payload["gate"]["metrics"].items():
            lines.append(
                f"- {name}: {metric['value']:.6f} {metric['operator']} "
                f"{metric['threshold']:.6f}; margin={metric['margin']:.6f}; "
                f"{'PASS' if metric['passed'] else 'FAIL'}"
            )
        applicability = payload.get("c2_applicability", {})
        lines.append(
            f"- C2 effective/noop: {applicability.get('c2_effective_cases', 0)} / "
            f"{applicability.get('c2_noop_cases', 0)}"
        )
    lines.extend(["", "## C2 applicability strata", ""])
    for label, metrics in summary.get("by_c2_applicability", {}).items():
        lines.append(
            f"- {label}: total={metrics['total']}, "
            f"direct={metrics['direct_correct']}, direct+C2={metrics['c2_correct']}, "
            f"rescues={metrics['rescues']}, regressions={metrics['regressions']}, "
            f"both_correct={metrics['both_correct']}, both_wrong={metrics['both_wrong']}"
        )
    lines.extend(["", "## Parser source by arm", ""])
    for arm, distribution in summary.get("parser_source_by_arm", {}).items():
        lines.append(f"- {arm}: {json.dumps(distribution, ensure_ascii=False, sort_keys=True)}")
    lines.extend(["", "## Per-domain results", ""])
    for domain, metrics in summary.get("by_domain", {}).items():
        lines.append(
            f"- {domain}: direct {metrics['direct_correct']}/{metrics['total']}, "
            f"direct+C2 {metrics['c2_correct']}/{metrics['total']}"
        )
    if summary["decision"] == "PROMOTE":
        lines.extend(["", "下一步：进入 MingLi-Bench 非退化验证。"])
    return "\n".join(lines) + "\n"


def archive_final_artifacts(
    run_id: str,
    manifest_path: Path,
    summary_path: Path,
) -> None:
    validate_run_id(run_id)
    archive_dir = PROJECT_ROOT / "docs" / "phase5" / run_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_path, archive_dir / "manifest.json")
    shutil.copy2(summary_path, archive_dir / "summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report = render_report(summary, sha256_file(manifest_path))
    (archive_dir / "report.md").write_text(
        report,
        encoding="utf-8",
    )


def run_validation(
    config: ExperimentConfig,
    source_paths: dict[int, Path],
    runner: Runner = run_model_benchmark,
    expected_rows: int = 40,
) -> dict[str, Any]:
    validate_run_id(config.run_id)
    assert_fixed_environment()
    assert_fixed_config(config)
    scope_status = experiment_scope_status()
    enforce_dirty_scope(scope_status, config.allow_dirty_scope)
    prior_summary_path = config.root / "summary.json"
    prior_summary = (
        json.loads(prior_summary_path.read_text(encoding="utf-8"))
        if prior_summary_path.exists() else None
    )
    initial_manifest_path = config.root / "manifest.json"
    manifest_path = (
        config.root / "final_manifest.json"
        if config.final_2023 else initial_manifest_path
    )
    if manifest_path.exists() and not config.resume:
        raise RuntimeError(f"run already exists at {manifest_path}; use --resume")
    if config.resume and not manifest_path.exists():
        raise RuntimeError(f"cannot resume missing manifest: {manifest_path}")

    datasets = {}
    cases_by_year = {}
    for year in config.years:
        assert_year_access(config, year, prior_summary)
        output = config.root / "datasets" / f"baziqa_{year}_enriched.jsonl"
        if output.exists() and config.resume:
            datasets[str(year)] = describe_dataset(
                source_paths[year],
                output,
                expected_rows=expected_rows,
            )
            cases = load_jsonl(output)
        else:
            datasets[str(year)] = enrich_dataset(
                source_paths[year],
                output,
                enrich_fn=enrich_row,
                expected_rows=expected_rows,
            )
            cases = load_jsonl(output)
        cases_by_year[year] = cases

    prior_manifest_sha256 = (
        sha256_file(initial_manifest_path)
        if config.final_2023 and initial_manifest_path.is_file() else None
    )
    manifest = build_manifest(
        config,
        datasets,
        scope_status,
        prior_manifest_sha256=prior_manifest_sha256,
    )
    load_or_validate_manifest(manifest_path, manifest, config.resume)

    offline = dict((prior_summary or {}).get("offline", {})) if config.final_2023 else {}
    completed_years = dict((prior_summary or {}).get("years", {})) if config.final_2023 else {}
    all_cases = list((prior_summary or {}).get("case_results", [])) if config.final_2023 else []
    for year in config.years:
        offline[str(year)] = run_offline_gate(
            year,
            cases_by_year[year],
            config.root / "offline" / f"{year}.json",
            scorer=summarize_scores,
        )
    if not all(item["gate"]["passed"] for item in offline.values()):
        summary = {
            "decision": "ROLLBACK",
            "reason": "offline_gate_failed",
            "offline": offline,
            "years": completed_years,
            "case_results": all_cases,
        }
        write_json(prior_summary_path, summary)
        return summary

    all_attempts = []
    if config.final_2023:
        for prior_year in (2021, 2022):
            all_attempts.extend(
                load_jsonl(config.root / "runs" / str(prior_year) / "attempts.jsonl")
            )
    for year in config.years:
        attempts_path = config.root / "runs" / str(year) / "attempts.jsonl"
        initial = run_initial_pairs(config, year, cases_by_year[year], attempts_path, runner)
        initial_valid_rate = sum(row["parser_valid"] for row in initial) / len(initial)
        initial_leaks = sum(bool(row.get("retrieved_answer_leak")) for row in initial)
        initial_cross = count_initial_rescues_regressions(initial)
        if initial_valid_rate < 0.95 or initial_leaks > 0 or should_stop_after_initial(initial):
            initial_case_results = stable_case_results(cases_by_year[year], initial)
            summary = {
                "decision": "ROLLBACK",
                "reason": "year_stop",
                "year": year,
                "offline": offline,
                "years": completed_years,
                "case_results": all_cases + initial_case_results,
                "attempts_seen": len(all_attempts) + len(initial),
                "attempts_path": str(attempts_path),
                "initial_stop_metrics": {
                    **initial_cross,
                    "parser_valid_rate": initial_valid_rate,
                    "confirmed_answer_leaks": initial_leaks,
                },
            }
            write_json(prior_summary_path, summary)
            return summary
        run_disagreement_retests(config, year, cases_by_year[year], attempts_path, runner)
        attempts = load_jsonl(attempts_path)
        stable = stable_case_results(cases_by_year[year], attempts)
        year_summary = summarize_stable_results(stable, attempts)
        completed_years[str(year)] = year_summary
        all_cases.extend(stable)
        all_attempts.extend(attempts)
        if year_summary["parser_valid_rate"] < 0.95 or year_summary["confirmed_answer_leaks"] > 0:
            summary = {
                "decision": "ROLLBACK",
                "reason": "year_infrastructure_stop",
                "year": year,
                "offline": offline,
                "years": completed_years,
                "case_results": all_cases,
                "attempts_seen": len(all_attempts),
                "attempts_path": str(attempts_path),
            }
            write_json(prior_summary_path, summary)
            return summary

    metrics = summarize_stable_results(all_cases, all_attempts)
    verdict = decide_final(metrics)
    summary = {
        **metrics,
        **verdict,
        "years": completed_years,
        "offline": offline,
        "case_results": all_cases,
    }
    write_json(prior_summary_path, summary)
    if config.final_2023:
        archive_final_artifacts(config.run_id, manifest_path, prior_summary_path)
    return summary
```

实现时保持以下顺序约束：先校验 2023 访问权，再读取 2023 文件；先完成所有当前验证年度 offline gate，再发起任何 API；报告只从落盘 manifest/summary 重建。

- [ ] **Step 4: 实现 CLI 参数与入口**

在脚本末尾追加：

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 5 C2 generalization validation")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-dirty-scope", action="store_true")
    parser.add_argument("--final-2023", action="store_true")
    parser.add_argument("--candidate-id")
    parser.add_argument("--seed", type=int, default=20260714)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    years = (2023,) if args.final_2023 else (2021, 2022)
    config = ExperimentConfig(
        run_id=args.run_id,
        root=args.root,
        years=years,
        seed=args.seed,
        allow_dirty_scope=args.allow_dirty_scope,
        resume=args.resume,
        final_2023=args.final_2023,
        candidate_id=args.candidate_id,
    )
    sources = {
        year: PROJECT_ROOT / "benchmark" / "datasets" / f"baziqa_contest8_{year}_holdout.jsonl"
        for year in years
    }
    summary = run_validation(config, sources)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["decision"] != "ROLLBACK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 运行专用测试确认通过**

Run: `python -m pytest tests/test_phase5_c2_generalization.py -q`

Expected: `44 passed`。

- [ ] **Step 6: 运行关联回归测试**

Run: `python -m pytest tests/test_phase5_c2_generalization.py tests/test_enrich_holdout_chart_input.py tests/test_per_option_scorer.py tests/test_benchmark_runner.py tests/test_benchmark_choice_accuracy.py -q`

Expected: all selected tests PASS。

- [ ] **Step 7: 运行非 E2E 测试集**

Run: `python -m pytest -m "not e2e" -q`

Expected: all non-E2E tests PASS。若出现任何失败，记录准确测试名与错误并停止本任务；不得修改无关测试，也不得执行 Step 9。若确认是既有无关失败，先向用户报告并取得是否提交的决定。

- [ ] **Step 8: 做静态完整性检查**

Run: `python -m py_compile scripts/run_phase5_c2_generalization.py`

Expected: exit code 0。

Run: `git diff --check`

Expected: exit code 0。

- [ ] **Step 9: 仅在测试门禁通过后提交完整编排器**

```powershell
git add scripts/run_phase5_c2_generalization.py tests/test_phase5_c2_generalization.py
git commit -m "feat: orchestrate Phase 5 C2 validation"
```

## Task 8: 真实实验前的只读预检与人工授权点

**Files:**
- No source changes

- [ ] **Step 1: 核验 API 前提但不打印密钥**

Run:

```powershell
python -c "import os; print('DEEPSEEK_API_KEY=' + ('SET' if os.getenv('DEEPSEEK_API_KEY') else 'MISSING')); print('BAZI_RAG=' + os.getenv('BAZI_RAG','off')); print('BAZI_FEWSHOT_FILE=' + ('SET' if os.getenv('BAZI_FEWSHOT_FILE') else 'off')); print('BAZI_APB_BLOCK=' + os.getenv('BAZI_APB_BLOCK','off'))"
```

Expected: key reports `SET`，RAG/few-shot/APB 均为 `off`。不得输出 key 内容。

- [ ] **Step 2: 查看实验作用域状态**

Run:

```powershell
git status --short -- benchmark/runners/per_option_scorer.py benchmark/formatters/baziqa_prompt.py benchmark/runners/run_benchmark.py scripts/enrich_holdout_chart_input.py scripts/enrich_baziqa_chart_input.py bazi_calculator.py
```

Expected: clean；如果存在改动，先审查并提交属于 Phase 4/C2 的必要实现。只有用户明确接受以未提交代码作为实验实现时，才使用 `--allow-dirty-scope`。

- [ ] **Step 3: 等待用户授权真实 API 成本后启动 2021/2022**

真实调用会产生费用和外部状态，执行前向用户报告 offline gate 数值及预计调用上限。约 380 次调用还包含 runner 固定 pacing 约 380 秒（约 6.3 分钟），总耗时需再加 API 延迟。获授权后运行：

```powershell
python scripts/run_phase5_c2_generalization.py --run-id phase5-c2-generalization-v1
```

Expected: 先生成 2021/2022 enriched/manifest/offline 产物；仅当两年 offline gate 全通过时开始模型调用。中断后使用完全相同参数恢复：

```powershell
python scripts/run_phase5_c2_generalization.py --run-id phase5-c2-generalization-v1 --resume
```

- [ ] **Step 4: 不自动解封 2023**

2021/2022 未 `ROLLBACK` 后，先按设计在 2024/2025 开发集完成 Prompt 候选选择并冻结 `candidate_id`。只有用户再次明确授权，才运行：

```powershell
python scripts/run_phase5_c2_generalization.py --run-id phase5-c2-generalization-v1 --final-2023 --candidate-id candidate-direct-c2-v1
```

Expected: 2023 运行完成后生成 `docs/phase5/phase5-c2-generalization-v1/{report.md,manifest.json,summary.json}`；不同 run_id 使用不同目录，不会相互覆盖，同一 run 的恢复运行可幂等刷新本目录。只有报告为 `PROMOTE` 才进入 MingLi-Bench 非退化验证。

如果 2023 首次运行中断，使用完全相同参数并增加 `--resume`；`final_manifest.json` 的指纹必须完全匹配。

## 最终验收标准

- 原始 `benchmark/datasets/*.jsonl` 的 SHA-256 在实现前后不变。
- 默认路径无法读取、enrich、score 或运行 2023；缺少 `--final-2023`、先前结果或 `candidate_id` 任一项都失败。
- 所有模型 attempt 逐条追加且 `fsync`，恢复时唯一键不会重复调用。
- runner 的每次单题调用固定 `case_details_jsonl=None`、`n_samples=1`、`temperature=0`、RAG/few-shot/APB/two-stage off。
- `BAZI_RAG=1` 时编排器必须在读取数据或调用模型前失败，fake runner 测试确认没有发生调用。
- offline gate 四项数值、阈值、margin 和 pass/fail 均落盘。
- 2023 任一提前 `ROLLBACK` 路径中，`summary.json` 仍保留已完成的 2021/2022 `years`、`case_results` 与 offline 证据。
- manifest 记录 C2 生效/空转题数、case_id、占比和 2023 seal audit note。
- enrichment 核心信号字段 100% 完整；缺失时中止，不排除题目继续运行。
- 报告按 C2 生效/空转分层并按两臂输出 parser source 分布；总体 gate 仍使用全部 120 题。
- 分母不因 API/parser 失败缩小；`unresolved` 和 `all_invalid` 单独统计。
- 最终使用精确双侧二项 McNemar，不使用卡方近似；显著性不替代硬门槛。
- `PROMOTE`、`NON_INFERIOR`、`ROLLBACK` 的所有边界测试通过。
- 专用测试、关联测试和非 E2E 测试完成，真实 API 结果不计作测试通过证据。
