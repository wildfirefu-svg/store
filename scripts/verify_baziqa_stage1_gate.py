from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PASS = "PASS"
FAST_TRACK = "FAST_TRACK"
GRAY_A = "GRAY_A"
GRAY_B = "GRAY_B"
BLOCKED_BUDGET = "BLOCKED:budget"
ROLLBACK = "ROLLBACK"

PROMOTION_EXIT = 0
INTERNAL_ERROR_EXIT = 1
GRAY_EXIT = 2
BLOCKED_EXIT = 3

DEFAULT_CUMULATIVE_BUDGET_CNY = 68.0


def _first_present(data: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _as_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def _as_percent(value: Any, field: str) -> float:
    number = _as_float(value, field)
    if 0 <= number <= 1:
        return number * 100.0
    return number


def _as_task_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    raise ValueError("executed_tasks must be a string or list")


def load_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("summary JSON must be an object")
    return data


def normalize_summary(data: dict[str, Any]) -> dict[str, Any]:
    mean = _as_percent(_first_present(data, ("mean", "mean_accuracy", "pro_mean", "accuracy_mean")), "mean")
    stdev = _as_percent(_first_present(data, ("stdev", "stddev", "std_dev", "stdev_pp")), "stdev")
    leak = _as_percent(_first_present(data, ("leak", "leak_ratio", "retrieved_answer_leak", "retrieved_answer_leak_ratio")), "leak")
    calls = _as_float(_first_present(data, ("calls", "stage1_calls", "actual_calls"), 0), "calls")
    estimated_calls = _as_float(_first_present(data, ("estimated_calls", "expected_calls", "call_budget"), 0), "estimated_calls")
    stage_cost_cny = _as_float(_first_present(data, ("stage_cost_cny", "cost_cny", "actual_cost_cny"), 0), "stage_cost_cny")
    stage_budget_cny = _as_float(_first_present(data, ("stage_budget_cny", "budget_cny"), 0), "stage_budget_cny")
    cumulative_cost_cny = _as_float(_first_present(data, ("cumulative_cost_cny", "three_stage_cumulative_cost_cny"), stage_cost_cny), "cumulative_cost_cny")
    cumulative_budget_cny = _as_float(_first_present(data, ("cumulative_budget_cny", "three_stage_budget_cny"), DEFAULT_CUMULATIVE_BUDGET_CNY), "cumulative_budget_cny")
    return {
        "mean": mean,
        "stdev": stdev,
        "leak": leak,
        "calls": calls,
        "estimated_calls": estimated_calls,
        "stage_cost_cny": stage_cost_cny,
        "stage_budget_cny": stage_budget_cny,
        "cumulative_cost_cny": cumulative_cost_cny,
        "cumulative_budget_cny": cumulative_budget_cny,
        "executed_tasks": _as_task_set(data.get("executed_tasks")),
    }


def budget_ok(summary: dict[str, Any]) -> bool:
    calls = summary["calls"]
    estimated_calls = summary["estimated_calls"]
    stage_cost_cny = summary["stage_cost_cny"]
    stage_budget_cny = summary["stage_budget_cny"]
    cumulative_cost_cny = summary["cumulative_cost_cny"]
    cumulative_budget_cny = summary["cumulative_budget_cny"]
    if estimated_calls > 0 and calls > estimated_calls * 1.5:
        return False
    if stage_budget_cny > 0 and stage_cost_cny > stage_budget_cny * 1.5:
        return False
    if cumulative_cost_cny > cumulative_budget_cny:
        return False
    return True


def decide_stage1_gate(summary: dict[str, Any]) -> str:
    mean = summary["mean"]
    stdev = summary["stdev"]
    leak = summary["leak"]
    if not budget_ok(summary):
        return BLOCKED_BUDGET

    promotion_ready = mean >= 35.0 and mean >= 3.0 * stdev and leak >= 15.0
    if promotion_ready:
        if summary.get("executed_tasks") == {"1.1", "1.3"}:
            return FAST_TRACK
        return PASS

    if leak < 5.0 and mean < 30.0:
        return ROLLBACK
    if leak >= 15.0 and (mean < 35.0 or mean < 3.0 * stdev):
        return GRAY_B
    if 5.0 <= leak < 15.0 or 30.0 <= mean < 35.0:
        return GRAY_A
    return ROLLBACK


def exit_code_for_decision(decision: str) -> int:
    if decision in {PASS, FAST_TRACK}:
        return PROMOTION_EXIT
    if decision in {GRAY_A, GRAY_B}:
        return GRAY_EXIT
    if decision in {BLOCKED_BUDGET, ROLLBACK}:
        return BLOCKED_EXIT
    return INTERNAL_ERROR_EXIT


def build_result(decision: str, summary: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(summary)
    metrics["executed_tasks"] = sorted(metrics.get("executed_tasks", set()))
    return {
        "decision": decision,
        "exit_code": exit_code_for_decision(decision),
        "metrics": metrics,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify BaziQA Hybrid Stage 1 gate decision")
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raw = load_summary(args.summary_json)
        summary = normalize_summary(raw)
        decision = decide_stage1_gate(summary)
        result = build_result(decision, summary)
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        else:
            print(decision)
        return result["exit_code"]
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return INTERNAL_ERROR_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
