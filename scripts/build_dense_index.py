"""Offline CLI to pre-build a dense embedding cache for a BaziQA corpus."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from case_dense_index import DEFAULT_MODEL, build_or_load
from case_index import CaseIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="为语料库构建稠密 embedding 缓存。")
    parser.add_argument("--corpus", required=True, help="语料库 JSONL 路径")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="sentence-transformers 模型名；特殊值 'tfidf' 使用 sklearn TF-IDF fallback",
    )
    parser.add_argument(
        "--cache",
        default=None,
        help="输出缓存路径（默认：.cache/dense_<model>.pkl）",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--force",
        action="store_true",
        help="即使缓存有效也强制重建",
    )
    args = parser.parse_args(argv)

    corpus_path = Path(args.corpus)
    cache_path = Path(args.cache) if args.cache else None

    if args.force and cache_path and cache_path.exists():
        cache_path.unlink()

    # Allow running in air-gapped / offline environments when models are cached.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    # Aggregate the corpus with CaseIndex so that the dense index row order
    # matches the rows CaseIndex will use at retrieval time.
    index = CaseIndex(corpus_path)
    aggregated_cases = [
        {"person_id": c.get("person_id"), "text_blob": c.get("text_blob")}
        for c in index._cases
    ]

    cases, embeddings = build_or_load(
        corpus_path=corpus_path,
        cache_path=cache_path,
        model_name=args.model,
        cases=aggregated_cases,
    )
    print(
        f"Built dense index: {len(cases)} cases, "
        f"shape={embeddings.shape}, model={args.model}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
