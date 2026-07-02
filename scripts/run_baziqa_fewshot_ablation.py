#!/usr/bin/env python3
"""Few-shot ablation for BaziQA: compare baseline vs few-shot on 2025 holdout.

This script picks N few-shot examples from the corpus (excluding any persons that
appear in the holdout), writes them to a temp JSONL, then runs the benchmark in
multiple configurations and produces a markdown ablation report.

Configurations evaluated:
  - baseline-direct (no RAG, no few-shot)
  - direct-fewshot (no RAG, with few-shot)
  - rag-direct (RAG only)
  - rag-direct-fewshot (RAG + few-shot)
  - rag-structured (RAG only, structured reasoning)
  - rag-structured-fewshot (RAG + few-shot, structured reasoning)

All runs use temperature=0 for determinism.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXACT_RE = re.compile(r"AccuracyExact:\s*(\d+)/(\d+)=(\d+(?:\.\d+)?)")
RUN_RE = re.compile(r"id=([a-f0-9]{8})")


def collect_holdout_person_ids(holdout_path: Path) -> set:
    pids = set()
    with holdout_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            pid = (row.get("person") or {}).get("person_id") or ""
            if pid:
                pids.add(pid)
    return pids


def pick_fewshot_examples(corpus_path: Path, exclude_pids: set, n: int = 3, seed: int = 42) -> list:
    """Pick n few-shot examples from corpus across distinct domains and persons."""
    import random

    rng = random.Random(seed)
    rows = []
    with corpus_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            pid = (row.get("person") or {}).get("person_id") or ""
            if pid in exclude_pids:
                continue
            if not row.get("question") or not row.get("answer"):
                continue
            rows.append(row)

    rng.shuffle(rows)

    picked: list = []
    seen_domains: set = set()
    seen_pids: set = set()
    for row in rows:
        dom = row.get("domain") or "unknown"
        pid = (row.get("person") or {}).get("person_id") or ""
        if dom in seen_domains or pid in seen_pids:
            continue
        picked.append(row)
        seen_domains.add(dom)
        seen_pids.add(pid)
        if len(picked) >= n:
            break

    if len(picked) < n:
        for row in rows:
            pid = (row.get("person") or {}).get("person_id") or ""
            if pid in seen_pids:
                continue
            picked.append(row)
            seen_pids.add(pid)
            if len(picked) >= n:
                break
    return picked


def write_fewshot_file(out_path: Path, rows: list) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_once(label: str, dataset: Path, method: str, rag: bool, fewshot_file: Path | None,
             max_cases: int, provider: str, model: str, temperature: float,
             rag_corpus: Path) -> dict:
    cmd = [
        sys.executable,
        "benchmark/runners/run_benchmark.py",
        "--dataset", str(dataset),
        "--model-runner",
        "--provider", provider,
        "--model", model,
        "--max-cases", str(max_cases),
        "--method", method,
        "--temperature", str(temperature),
    ]
    if rag:
        cmd.extend(["--rag", "--rag-corpus", str(rag_corpus)])
    if fewshot_file is not None:
        cmd.extend(["--fewshot-file", str(fewshot_file)])

    print(f"\n=== Running {label} ===")
    print(" ".join(cmd))
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    output = proc.stdout + "\n" + proc.stderr
    print(output[-2500:])
    match = EXACT_RE.search(output)
    if not match:
        raise RuntimeError(f"Cannot parse AccuracyExact for {label}:\n{output[-2000:]}")
    run_match = RUN_RE.search(output)
    return {
        "label": label,
        "method": method,
        "rag": rag,
        "fewshot": fewshot_file is not None,
        "correct": int(match.group(1)),
        "total": int(match.group(2)),
        "accuracy": float(match.group(3)),
        "run_id": run_match.group(1) if run_match else "",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl")
    parser.add_argument("--corpus", default="benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--max-cases", type=int, default=40)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--fewshot-n", type=int, default=3)
    parser.add_argument("--fewshot-out", default=".tmp/baziqa_fewshot_examples.jsonl")
    parser.add_argument("--output", default="docs/BAZIQA_FEWSHOT_ABLATION_REPORT.md")
    parser.add_argument("--configs", default="all",
                        help="Comma-separated subset of {baseline-direct,direct-fewshot,rag-direct,rag-direct-fewshot,rag-structured,rag-structured-fewshot} or 'all'")
    args = parser.parse_args(argv)

    dataset = Path(args.dataset)
    corpus = Path(args.corpus)
    fewshot_path = Path(args.fewshot_out)
    out_path = Path(args.output)

    exclude_pids = collect_holdout_person_ids(dataset)
    fewshot_rows = pick_fewshot_examples(corpus, exclude_pids, n=args.fewshot_n)
    write_fewshot_file(fewshot_path, fewshot_rows)
    print(f"Wrote {len(fewshot_rows)} few-shot examples to {fewshot_path}")
    for i, row in enumerate(fewshot_rows, 1):
        print(f"  [{i}] domain={row.get('domain')} pid={(row.get('person') or {}).get('person_id')} answer={row.get('answer')}")

    all_configs = [
        ("baseline-direct", "direct_choice", False, None),
        ("direct-fewshot", "direct_choice", False, fewshot_path),
        ("rag-direct", "direct_choice", True, None),
        ("rag-direct-fewshot", "direct_choice", True, fewshot_path),
        ("rag-structured", "structured_reasoning", True, None),
        ("rag-structured-fewshot", "structured_reasoning", True, fewshot_path),
    ]
    if args.configs and args.configs != "all":
        wanted = {x.strip() for x in args.configs.split(",") if x.strip()}
        configs = [c for c in all_configs if c[0] in wanted]
    else:
        configs = all_configs

    results = []
    for label, method, rag, fewshot in configs:
        res = run_once(label, dataset, method, rag, fewshot, args.max_cases,
                       args.provider, args.model, args.temperature, corpus)
        results.append(res)
        print(f"  -> {label}: {res['correct']}/{res['total']} = {res['accuracy']*100:.1f}% (run {res['run_id']})")

    by_label = {r["label"]: r for r in results}
    baseline_direct = by_label.get("baseline-direct")
    rag_direct = by_label.get("rag-direct")
    rag_structured = by_label.get("rag-structured")

    lines = []
    lines.append("# BaziQA Few-Shot Ablation Report")
    lines.append("")
    lines.append(
        f"Dataset: `{dataset}`  Corpus: `{corpus}`  MaxCases: {args.max_cases}  "
        f"Temperature: {args.temperature}  Provider: `{args.provider}`  Model: `{args.model}`  "
        f"FewShotN: {args.fewshot_n}"
    )
    lines.append("")
    lines.append("| Run | Method | RAG | FewShot | Correct/Total | Accuracy | Δ vs baseline | RunId |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    base_acc = baseline_direct["accuracy"] if baseline_direct else None
    for r in results:
        delta = ""
        if base_acc is not None:
            delta = f"{(r['accuracy'] - base_acc) * 100:+.1f}pp"
        lines.append(
            f"| {r['label']} | {r['method']} | {'ON' if r['rag'] else 'OFF'} | "
            f"{'ON' if r['fewshot'] else 'OFF'} | {r['correct']}/{r['total']} | "
            f"{r['accuracy']*100:.1f}% | {delta} | {r['run_id']} |"
        )
    lines.append("")
    lines.append("## Few-Shot Examples Used")
    lines.append("")
    for i, row in enumerate(fewshot_rows, 1):
        person = row.get("person") or {}
        birth = person.get("birth") or {}
        lines.append(
            f"- 示例 {i}: domain={row.get('domain')}, person={person.get('person_id')}, "
            f"birth_year={birth.get('year')}, answer={row.get('answer')}"
        )
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if baseline_direct and "direct-fewshot" in by_label:
        d = by_label["direct-fewshot"]["accuracy"] - baseline_direct["accuracy"]
        lines.append(f"- direct + few-shot vs baseline-direct: **{d*100:+.1f}pp**")
    if rag_direct and "rag-direct-fewshot" in by_label:
        d = by_label["rag-direct-fewshot"]["accuracy"] - rag_direct["accuracy"]
        lines.append(f"- rag-direct + few-shot vs rag-direct: **{d*100:+.1f}pp**")
    if rag_structured and "rag-structured-fewshot" in by_label:
        d = by_label["rag-structured-fewshot"]["accuracy"] - rag_structured["accuracy"]
        lines.append(f"- rag-structured + few-shot vs rag-structured: **{d*100:+.1f}pp**")
    lines.append("")
    lines.append("## Raw Runs")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(results, ensure_ascii=False, indent=2))
    lines.append("```")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
