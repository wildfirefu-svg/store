"""CLI wrapper: normalize MingLi-Bench data.json into a baziqa-compatible JSONL
and invoke benchmark/runners/run_benchmark.py --model-runner on it.

Usage:
    python scripts/run_mingli_bench.py --data data/mingli/data.json \
        --fortune data/mingli/fortune_api_results.json --astro \
        --model deepseek-v4-flash --year 2025 --max-cases 40 \
        --output-dir .tmp/mingli --n-samples 3 --sample-temperature 0.4

The adapter is benchmark/runners/mingli_bench_adapter.load_and_normalize.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Allow running as `python scripts/run_mingli_bench.py` from the repo root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmark.runners.mingli_bench_adapter import load_and_normalize


def _write_jsonl(rows, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run benchmark against MingLi-Bench multiple-choice data.")
    parser.add_argument("--data", required=True, help="Path to MingLi-Bench data.json")
    parser.add_argument("--fortune", default=None, help="Path to MingLi-Bench fortune_api_results.json")
    parser.add_argument("--astro", action="store_true", help="Inject chart_input from fortune_api_results.json (requires --fortune)")
    parser.add_argument("--year", default=None, help="Filter by year (e.g. 2025)")
    parser.add_argument("--categories", nargs="+", default=None, help="Filter by chinese category names, e.g. 事业 婚姻")
    parser.add_argument("--jsonl-out", default=None, help="Where to write the normalized JSONL (defaults to <output-dir>/mingli.jsonl)")

    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--method", default="direct_choice")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-cases", type=int, default=200)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--case-details-jsonl", default=None)

    parser.add_argument("--n-samples", type=int, default=1)
    parser.add_argument("--sample-temperature", type=float, default=None)
    parser.add_argument("--aggregate", default=None, choices=[None, "majority"])
    parser.add_argument("--shuffle-options", action="store_true")
    parser.add_argument("--shuffle-seed", type=int, default=None)

    args = parser.parse_args(argv)

    if args.astro and not args.fortune:
        raise SystemExit("--astro requires --fortune")

    rows = load_and_normalize(
        args.data,
        fortune_api_json_path=args.fortune,
        include_astro=args.astro,
        year_filter=args.year,
        category_filter=args.categories,
    )

    output_dir = Path(args.output_dir)
    jsonl_out = Path(args.jsonl_out) if args.jsonl_out else (output_dir / "mingli.jsonl")
    _write_jsonl(rows, jsonl_out)

    case_details = (
        Path(args.case_details_jsonl)
        if args.case_details_jsonl
        else (output_dir / "case_details.jsonl")
    )
    case_details.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable, "benchmark/runners/run_benchmark.py",
        "--dataset", str(jsonl_out),
        "--model-runner",
        "--provider", args.provider,
        "--model", args.model,
        "--max-cases", str(args.max_cases),
        "--method", args.method,
        "--temperature", str(args.temperature),
        "--output-dir", str(output_dir),
        "--case-details-jsonl", str(case_details),
    ]

    if args.n_samples and args.n_samples > 1:
        command.extend(["--n-samples", str(args.n_samples)])
    if args.sample_temperature is not None:
        command.extend(["--sample-temperature", str(args.sample_temperature)])
    if args.aggregate:
        command.extend(["--aggregate", str(args.aggregate)])
    if args.shuffle_options:
        if args.shuffle_seed is None:
            raise SystemExit("--shuffle-options requires --shuffle-seed")
        command.extend(["--shuffle-options", "--shuffle-seed", str(args.shuffle_seed)])

    env = os.environ.copy()
    result = subprocess.run(command, check=False, env=env)
    return int(getattr(result, "returncode", 0) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
