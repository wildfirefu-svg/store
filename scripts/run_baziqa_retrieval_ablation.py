"""BaziQA retrieval ablation runner.

Drives ``benchmark/runners/run_benchmark.py`` across a configurable set
of retrieval configs (loaded from ``benchmark/configs/baziqa_retrieval_configs.yaml``),
collects per-(config, repeat) ``case_details`` JSONL files, optionally appends
every row into a single rollback JSONL, and emits an aggregated markdown
report with one row per config including model name / config id / runs /
mean / min / max / cost_cny.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIGS_YAML = _PROJECT_ROOT / "benchmark" / "configs" / "baziqa_retrieval_configs.yaml"


# --------------------------------------------------------------------- legacy
# The original 4-mode env table is preserved for the legacy ``summarize`` /
# ``render_report`` callers (e.g. older tests, manual reruns).  New code goes
# through the yaml-driven path below.
def build_configs():
    return [
        {"name": "bm25", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "0", "BAZI_RAG_SEMANTIC": "0"}},
        {"name": "structured", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "0"}},
        {"name": "structured_semantic", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "1", "BAZI_RAG_SEMANTIC_WEIGHT": "1"}},
        {"name": "semantic_low", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "1", "BAZI_RAG_SEMANTIC_WEIGHT": "0.35"}},
    ]


def _accuracy(path: Path) -> float:
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


# ------------------------------------------------------------- yaml-driven v2
def _load_yaml_configs(path: Path) -> List[Dict[str, Any]]:
    import yaml
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a list of retrieval config entries")
    return raw


def _config_envs(cfg: Dict[str, Any]) -> Dict[str, str]:
    """Translate a yaml config entry into the env vars consumed by case_index."""
    env: Dict[str, str] = {}
    env["BAZI_RAG_STRUCTURED_WEIGHT"] = "1" if cfg.get("structured") else "0"
    env["BAZI_RAG_SEMANTIC"] = "1" if cfg.get("semantic") else "0"
    if cfg.get("embedding_vector"):
        env["BAZI_RAG_VECTOR"] = "1"
        model = cfg.get("embedding_model") or ""
        if model:
            env["BAZI_RAG_VECTOR_MODEL"] = model
    elif cfg.get("tfidf_vector"):
        env["BAZI_RAG_VECTOR"] = "1"
        env["BAZI_RAG_VECTOR_MODE"] = "tfidf"
    else:
        env["BAZI_RAG_VECTOR"] = "0"
    return env


def _resolve_configs(args: argparse.Namespace, yaml_path: Path) -> List[Dict[str, Any]]:
    entries = _load_yaml_configs(yaml_path)
    by_id = {e.get("id"): e for e in entries}
    if args.configs:
        ids = [s.strip() for s in args.configs.split(",") if s.strip()]
    elif args.config_id:
        ids = [args.config_id]
    else:
        raise SystemExit("either --configs or --config-id must be supplied")
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise SystemExit(f"unknown config id(s): {missing}; available={sorted(by_id)}")
    return [by_id[i] for i in ids]


def _run_one(cfg: Dict[str, Any], repeat: int, args: argparse.Namespace) -> "tuple[Path, bool]":
    """Invoke run_benchmark.py once for (config, repeat).

    Returns ``(details_path, skipped)``. ``skipped`` is True when --append
    short-circuited a prior complete output; callers MUST NOT re-append the
    rows of a skipped pair into the rollback JSONL, or the rollback grows by
    one full pass on every rerun.
    """
    details = Path(args.output_dir) / f"{cfg['id']}_run{repeat}.jsonl"
    # An empty file (from a previous aborted run) should not satisfy --append;
    # otherwise we silently skip a config that actually needs to be redone.
    if args.append and details.exists() and details.stat().st_size > 0:
        return details, True

    env = os.environ.copy()
    env.update(_config_envs(cfg))
    # Default to HF offline mode so that a flaky huggingface.co HEAD check
    # cannot stall the ablation between subprocess invocations. Caller-set
    # values win (e.g. set to "0" to refresh the local cache).
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    retrieval_mode = cfg.get("retrieval_mode") or args.retrieval_mode
    option_evidence_k = cfg.get("option_evidence_k", args.option_evidence_k)
    command = [
        sys.executable, "benchmark/runners/run_benchmark.py",
        "--dataset", args.dataset,
        "--model-runner",
        "--provider", "deepseek",
        "--model", args.model,
        "--max-cases", str(args.max_cases),
        "--method", args.method,
        "--temperature", str(args.temperature),
        "--rag",
        "--rag-k", str(args.rag_k),
        "--rag-corpus", args.corpus,
        "--case-details-jsonl", str(details),
        "--config-id", cfg["id"],
        "--retrieval-mode", retrieval_mode,
        "--option-evidence-k", str(option_evidence_k),
    ]
    subprocess.run(command, check=True, env=env)
    return details, False


def _backfill_config_id(details_path: Path, cfg_id: str, model_name: str) -> List[Dict[str, Any]]:
    """Ensure every row in details_path carries config_id + model_name.

    Rows produced by older run_benchmark builds may not echo --config-id; this
    function back-fills them so the rollback JSONL is uniformly tagged.
    """
    if not details_path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in details_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("config_id") is None:
            row["config_id"] = cfg_id
        row.setdefault("model_name", model_name)
        rows.append(row)
    # write back so future readers see the unified schema
    with details_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def _append_rollback(rollback_path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    rollback_path.parent.mkdir(parents=True, exist_ok=True)
    with rollback_path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _aggregate_rows(configs: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for cfg in configs:
        accs: List[float] = []
        for repeat in range(1, args.repeats + 1):
            p = Path(args.output_dir) / f"{cfg['id']}_run{repeat}.jsonl"
            if p.exists():
                accs.append(_accuracy(p))
        rows.append({
            "config_id": cfg["id"],
            "model_name": args.model,
            "runs": len(accs),
            "mean": (sum(accs) / len(accs)) if accs else 0.0,
            "min": min(accs) if accs else 0.0,
            "max": max(accs) if accs else 0.0,
            "cost_cny": 0.0,
        })
    return rows


def _render_v2_report(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# BaziQA Retrieval Ablation Report",
        "",
        "| config_id | model_name | runs | mean | min | max | cost_cny | gate |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        gate = "PASS" if row["mean"] >= 0.40 and row["min"] >= 0.35 else "BLOCKED"
        lines.append(
            f"| {row['config_id']} | {row['model_name']} | {row['runs']} | "
            f"{row['mean']:.1%} | {row['min']:.1%} | {row['max']:.1%} | "
            f"{row['cost_cny']:.2f} | {gate} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run BaziQA retrieval ablation.")
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl")
    parser.add_argument("--corpus", default="benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl")
    parser.add_argument("--output-dir", default=".tmp/baziqa_retrieval_ablation")
    parser.add_argument("--report", default="docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--config-id", default=None, help="Single retrieval config id from the yaml")
    parser.add_argument("--configs", default=None, help="Comma-separated list of retrieval config ids; overrides --config-id when set")
    parser.add_argument("--model", default="deepseek-v4-flash", help="Model name passed to run_benchmark.py --model")
    parser.add_argument("--rollback-jsonl", default=None, help="Aggregate every case_details row into this JSONL (appended)")
    parser.add_argument("--append", action="store_true", help="Skip (config, repeat) outputs that already exist on disk")
    parser.add_argument("--retrieval-configs-yaml", default=str(_DEFAULT_CONFIGS_YAML))
    parser.add_argument("--max-cases", type=int, default=40)
    parser.add_argument("--method", default="structured_reasoning")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--rag-k", type=int, default=2)
    parser.add_argument("--retrieval-mode", default="legacy", choices=["legacy", "option_grounded"])
    parser.add_argument("--option-evidence-k", type=int, default=2)
    args = parser.parse_args(argv)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    yaml_path = Path(args.retrieval_configs_yaml)
    configs = _resolve_configs(args, yaml_path)

    if args.run:
        rollback = Path(args.rollback_jsonl) if args.rollback_jsonl else None
        for cfg in configs:
            for repeat in range(1, args.repeats + 1):
                details, skipped = _run_one(cfg, repeat, args)
                # Always backfill so the on-disk schema is uniform, but only
                # rollback-append the rows from a freshly produced output to
                # avoid duplicating entries on every --append rerun.
                rows = _backfill_config_id(details, cfg["id"], args.model)
                if rollback is not None and rows and not skipped:
                    _append_rollback(rollback, rows)

    report_rows = _aggregate_rows(configs, args)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(_render_v2_report(report_rows), encoding="utf-8")
    print(f"Report saved to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
