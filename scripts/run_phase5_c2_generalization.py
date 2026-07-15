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


def year_schedule_seed(config: ExperimentConfig, year: int) -> int:
    return config.seed + year


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
