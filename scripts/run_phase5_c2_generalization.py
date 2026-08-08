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
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def exact_mcnemar_pvalue(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    two_tailed = 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, two_tailed)


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
