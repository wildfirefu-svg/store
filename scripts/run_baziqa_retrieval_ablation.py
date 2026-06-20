import argparse
import json
import os
import subprocess
from pathlib import Path


def build_configs():
    return [
        {"name": "bm25", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "0", "BAZI_RAG_SEMANTIC": "0"}},
        {"name": "structured", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "0"}},
        {"name": "structured_semantic", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "1", "BAZI_RAG_SEMANTIC_WEIGHT": "1"}},
        {"name": "semantic_low", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "1", "BAZI_RAG_SEMANTIC_WEIGHT": "0.35"}},
    ]


def _accuracy(path):
    total = 0
    correct = 0
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1
            if row.get("correct") is True:
                correct += 1
    return correct / total if total else 0.0


def summarize(output_dir, repeats):
    rows = []
    for config in build_configs():
        values = []
        for repeat in range(1, repeats + 1):
            path = Path(output_dir) / f"{config['name']}_run{repeat}.jsonl"
            if path.exists():
                values.append(_accuracy(path))
        if values:
            rows.append({
                "name": config["name"],
                "runs": len(values),
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
            })
    return rows


def render_report(rows):
    lines = [
        "# BaziQA Retrieval Ablation Report",
        "",
        "| mode | runs | mean | min | max | gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        gate = "PASS" if row["mean"] >= 0.40 and row["min"] >= 0.35 else "BLOCKED"
        lines.append(f"| {row['name']} | {row['runs']} | {row['mean']:.1%} | {row['min']:.1%} | {row['max']:.1%} | {gate} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run BaziQA retrieval ablation.")
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl")
    parser.add_argument("--corpus", default="benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl")
    parser.add_argument("--output-dir", default=".tmp/baziqa_retrieval_ablation")
    parser.add_argument("--report", default="docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    if args.run:
        for config in build_configs():
            for repeat in range(1, args.repeats + 1):
                details = Path(args.output_dir) / f"{config['name']}_run{repeat}.jsonl"
                env = os.environ.copy()
                env.update(config["env"])
                command = [
                    "python", "benchmark/runners/run_benchmark.py",
                    "--dataset", args.dataset,
                    "--model-runner",
                    "--provider", "deepseek",
                    "--model", "deepseek-v4-pro",
                    "--max-cases", "40",
                    "--method", "structured_reasoning",
                    "--temperature", "0",
                    "--rag",
                    "--rag-k", "2",
                    "--rag-corpus", args.corpus,
                    "--case-details-jsonl", str(details),
                ]
                subprocess.run(command, check=True, env=env)

    Path(args.report).write_text(render_report(summarize(args.output_dir, args.repeats)), encoding="utf-8")
    print(f"Report saved to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
