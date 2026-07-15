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
