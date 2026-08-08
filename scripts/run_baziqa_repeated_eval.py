#!/usr/bin/env python3
"""Run repeated BaziQA benchmark commands and summarize accuracy stability."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.reports.accuracy_stats import summarize_accuracy

EXACT_RE = re.compile(r"AccuracyExact:\s*(\d+)/(\d+)=(\d+(?:\.\d+)?)")
RUN_RE = re.compile(r"id=([a-f0-9]{8})")


def run_once(label, dataset, method, rag, max_cases, provider, model, temperature):
    cmd = [
        sys.executable,
        "benchmark/runners/run_benchmark.py",
        "--dataset", dataset,
        "--model-runner",
        "--provider", provider,
        "--model", model,
        "--max-cases", str(max_cases),
        "--method", method,
        "--temperature", str(temperature),
    ]
    if rag:
        cmd.append("--rag")
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    output = proc.stdout + "\n" + proc.stderr
    match = EXACT_RE.search(output)
    if not match:
        raise RuntimeError(f"Cannot parse AccuracyExact for {label}:\n{output[-2000:]}")
    run_match = RUN_RE.search(output)
    return {
        "label": label,
        "method": method,
        "rag": rag,
        "correct": int(match.group(1)),
        "total": int(match.group(2)),
        "accuracy": float(match.group(3)),
        "run_id": run_match.group(1) if run_match else "",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--max-cases", type=int, default=40)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output", default="docs/BAZIQA_REPEATED_EVAL_REPORT.md")
    parser.add_argument(
        "--configs",
        default="all",
        help="Comma-separated subset of baseline-direct,rag-direct,rag-structured or 'all'",
    )
    args = parser.parse_args(argv)

    all_configs = [
        ("baseline-direct", "direct_choice", False),
        ("rag-direct", "direct_choice", True),
        ("rag-structured", "structured_reasoning", True),
    ]
    if args.configs and args.configs != "all":
        wanted = {x.strip() for x in args.configs.split(",") if x.strip()}
        configs = [c for c in all_configs if c[0] in wanted]
        unknown = wanted - {c[0] for c in all_configs}
        if unknown:
            raise SystemExit(f"Unknown configs: {', '.join(sorted(unknown))}")
        if not configs:
            raise SystemExit("No configs selected")
    else:
        configs = all_configs
    rows = []
    for _ in range(args.repeats):
        for label, method, rag in configs:
            rows.append(
                run_once(
                    label,
                    args.dataset,
                    method,
                    rag,
                    args.max_cases,
                    args.provider,
                    args.model,
                    args.temperature,
                )
            )

    summary = summarize_accuracy(rows)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pipe = chr(124)
    lines = [
        "# BaziQA Repeated Evaluation Report",
        "",
        f"Dataset: `{args.dataset}`  MaxCases: {args.max_cases}  Repeats: {args.repeats}  Temperature: {args.temperature}",
        "",
        f"{pipe} Label {pipe} Runs {pipe} Mean {pipe} Min {pipe} Max {pipe} Stdev {pipe}",
        f"{pipe} --- {pipe} ---: {pipe} ---: {pipe} ---: {pipe} ---: {pipe} ---: {pipe}",
    ]
    for label, stats in summary.items():
        lines.append(
            f"{pipe} {label} {pipe} {stats['runs']} {pipe} {stats['mean']:.3f} {pipe} "
            f"{stats['min']:.3f} {pipe} {stats['max']:.3f} {pipe} {stats['stdev']:.3f} {pipe}"
        )
    lines.extend(["", "## Raw Runs", "", "```json", json.dumps(rows, ensure_ascii=False, indent=2), "```"])
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
