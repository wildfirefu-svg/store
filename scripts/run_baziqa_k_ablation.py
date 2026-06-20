"""Run BaziQA k-ablation experiments across k=1,2,3 with repeats.

This script orchestrates repeated benchmark runs for different RAG top-k values,
capturing per-case trace and producing an aggregate Markdown report.
"""

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from benchmark.runners.run_benchmark import load_jsonl, run_model_benchmark


K_VALUES = [1, 2, 3]


def _accuracy(result):
    correct = sum(1 for d in result.get("case_details", []) if d.get("correct"))
    total = len(result.get("case_details", []))
    return correct, total, correct / total if total else 0.0


def _run_single(dataset, provider, model, method, temperature, max_cases, k, repeat):
    cases = load_jsonl(dataset)
    run_id = f"k{k}_run{repeat}"
    details_path = f".tmp/k_ablation/{run_id}.jsonl"
    os.makedirs(".tmp/k_ablation", exist_ok=True)
    result = run_model_benchmark(
        cases,
        provider=provider,
        model=model,
        prompt_version="srp_v1",
        max_cases=max_cases,
        method=method,
        temperature=temperature,
        case_details_jsonl=details_path,
        rag_k=k,
    )
    correct, total, acc = _accuracy(result)
    return {
        "k": k,
        "repeat": repeat,
        "correct": correct,
        "total": total,
        "accuracy": acc,
        "details_path": details_path,
        "failed": len(result.get("failed_cases", [])),
    }


def run_k_ablation(dataset, provider, model, method, temperature, max_cases, repeats, output):
    records = []
    print(f"Starting k-ablation: dataset={dataset}, k in {K_VALUES}, repeats={repeats}, max_cases={max_cases}")
    for k in K_VALUES:
        for r in range(1, repeats + 1):
            print(f"Running k={k}, repeat={r}/{repeats}")
            record = _run_single(dataset, provider, model, method, temperature, max_cases, k, r)
            records.append(record)

    grouped = {}
    for rec in records:
        grouped.setdefault(rec["k"], []).append(rec["accuracy"])

    summary_rows = []
    for k in K_VALUES:
        accs = grouped[k]
        mean_acc = sum(accs) / len(accs)
        min_acc = min(accs)
        max_acc = max(accs)
        stdev_acc = statistics.stdev(accs) if len(accs) > 1 else 0.0
        summary_rows.append({
            "k": k,
            "n": len(accs),
            "mean": round(mean_acc, 6),
            "min": round(min_acc, 6),
            "max": round(max_acc, 6),
            "stdev": round(stdev_acc, 6),
        })

    return summary_rows


def _build_report(records, summary_rows):
    lines = [
        "# BaziQA RAG k-Ablation Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary by k",
        "",
        "| k | runs | mean | min | max | stdev |",
        "|---|------|------|-----|-----|-------|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['k']} | {row['n']} | {row['mean']:.4f} | {row['min']:.4f} | {row['max']:.4f} | {row['stdev']:.4f} |"
        )

    lines.extend(["", "## Per-run Details", "", "| k | repeat | correct | total | accuracy | failed | details |", "|---|--------|---------|-------|----------|--------|---------|"])
    for rec in records:
        lines.append(
            f"| {rec['k']} | {rec['repeat']} | {rec['correct']} | {rec['total']} | {rec['accuracy']:.4f} | {rec['failed']} | `{rec['details_path']}` |"
        )

    lines.extend(["", "## Interpretation", "", "- If k=1 or k=2 mean ≥ k=3 mean + 5 pp and stdev is not larger, reduce default k.", "- If all k means < 35%, the bottleneck is retrieval quality, not k.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run BaziQA RAG k-ablation.")
    parser.add_argument('--dataset', required=True, help='Path to JSONL dataset')
    parser.add_argument('--provider', default='deepseek', help='Model provider')
    parser.add_argument('--model', default='deepseek-v4-pro', help='Model name')
    parser.add_argument('--method', default='structured_reasoning', choices=['direct_choice', 'structured_reasoning', 'multi_turn'])
    parser.add_argument('--max-cases', type=int, default=40, help='Max cases per run')
    parser.add_argument('--repeats', type=int, default=3, help='Number of repeats per k')
    parser.add_argument('--temperature', type=float, default=0.0, help='Model temperature')
    parser.add_argument('--output', default='docs/BAZIQA_K_ABLATION_REPORT.md', help='Markdown report output path')
    args = parser.parse_args(argv)

    summary = run_k_ablation(
        args.dataset,
        args.provider,
        args.model,
        args.method,
        args.temperature,
        args.max_cases,
        args.repeats,
        args.output,
    )
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    report_lines = [
        "# BaziQA Refined P2 40-Case Validation",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary by k",
        "",
        "| k | runs | mean | min | max | stdev |",
        "|---|------|------|-----|-----|-------|",
    ]
    for row in summary:
        report_lines.append(
            f"| {row['k']} | {row['n']} | {row['mean']:.1%} | {row['min']:.1%} | {row['max']:.1%} | {row['stdev']:.4f} |"
        )
        report_lines.append(f"\nAccuracy: {row['mean']:.1%} (k={row['k']})")
    report_lines.extend(["", "## Interpretation", "",
        "- If k=1 or k=2 mean >= k=3 mean + 5pp and stdev is not larger, reduce default k.",
        "- If all k means < 35%, the bottleneck is retrieval quality, not k.", ""])
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"\nK-ablation report saved to {args.output}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
