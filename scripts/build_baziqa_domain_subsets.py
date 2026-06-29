from __future__ import annotations

import argparse
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Iterable


DOMAINS = ["health", "annual_fortune", "relationship", "unknown"]
DEFAULT_HOLDOUT = Path("benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl")
DEFAULT_CORPUS = Path("benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl")
DEFAULT_OUTPUT_DIR = Path("benchmark/datasets/baziqa_domain_subsets")


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _group_by_domain(rows: Iterable[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("domain") or "unknown")].append(row)
    return dict(grouped)


def _corpus_fill_row(row: dict) -> dict:
    copied = deepcopy(row)
    copied["source"] = "corpus_fill"
    return copied


def select_domain_rows(
    domain: str,
    holdout_rows: list[dict],
    corpus_rows: list[dict],
    min_cases: int = 5,
    max_cases: int = 10,
) -> tuple[list[dict], dict[str, int]]:
    selected = [deepcopy(row) for row in holdout_rows[:max_cases]]
    holdout_count = len(selected)

    fill_needed = max(0, min_cases - len(selected))
    if fill_needed:
        selected.extend(_corpus_fill_row(row) for row in corpus_rows[:fill_needed])

    if len(selected) < min_cases:
        raise ValueError(
            f"domain {domain!r} only has {len(selected)} rows after corpus_fill; "
            f"minimum is {min_cases}"
        )

    selected = selected[:max_cases]
    corpus_fill_count = sum(1 for row in selected if row.get("source") == "corpus_fill")
    return selected, {
        "holdout": holdout_count,
        "corpus_fill": corpus_fill_count,
        "total": len(selected),
    }


def build_domain_subsets(
    holdout_jsonl: Path = DEFAULT_HOLDOUT,
    corpus_jsonl: Path = DEFAULT_CORPUS,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    domains: list[str] | None = None,
    min_cases: int = 5,
    max_cases: int = 10,
) -> dict[str, dict[str, int]]:
    domains = domains or DOMAINS
    holdout_by_domain = _group_by_domain(load_jsonl(holdout_jsonl))
    corpus_by_domain = _group_by_domain(load_jsonl(corpus_jsonl))
    stats: dict[str, dict[str, int]] = {}

    for domain in domains:
        rows, domain_stats = select_domain_rows(
            domain=domain,
            holdout_rows=holdout_by_domain.get(domain, []),
            corpus_rows=corpus_by_domain.get(domain, []),
            min_cases=min_cases,
            max_cases=max_cases,
        )
        write_jsonl(Path(output_dir) / f"{domain}.jsonl", rows)
        stats[domain] = domain_stats

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build BaziQA domain subset JSONL files")
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--domains", default=",".join(DOMAINS))
    parser.add_argument("--min-cases", type=int, default=5)
    parser.add_argument("--max-cases", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    domains = [item.strip() for item in args.domains.split(",") if item.strip()]
    stats = build_domain_subsets(
        holdout_jsonl=args.holdout,
        corpus_jsonl=args.corpus,
        output_dir=args.output_dir,
        domains=domains,
        min_cases=args.min_cases,
        max_cases=args.max_cases,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
