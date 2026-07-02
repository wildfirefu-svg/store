#!/usr/bin/env python3
"""Split a combined BaziQA JSONL into corpus and holdout files by source_year."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def split_by_holdout_year(source: Path, holdout_year: int, corpus_out: Path, holdout_out: Path) -> dict:
    source = Path(source)
    corpus_out = Path(corpus_out)
    holdout_out = Path(holdout_out)
    corpus_out.parent.mkdir(parents=True, exist_ok=True)
    holdout_out.parent.mkdir(parents=True, exist_ok=True)
    corpus_count = 0
    holdout_count = 0
    with source.open("r", encoding="utf-8") as src, corpus_out.open("w", encoding="utf-8") as corpus, holdout_out.open("w", encoding="utf-8") as holdout:
        for line in src:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if str(row.get("source_year")) == str(holdout_year):
                holdout.write(json.dumps(row, ensure_ascii=False) + "\n")
                holdout_count += 1
            else:
                corpus.write(json.dumps(row, ensure_ascii=False) + "\n")
                corpus_count += 1
    return {"corpus": corpus_count, "holdout": holdout_count}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--holdout-year", type=int, required=True)
    parser.add_argument("--corpus-out", required=True)
    parser.add_argument("--holdout-out", required=True)
    args = parser.parse_args(argv)
    stats = split_by_holdout_year(Path(args.source), args.holdout_year, Path(args.corpus_out), Path(args.holdout_out))
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
