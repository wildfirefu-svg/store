"""离线评估 option evidence 排序，无需调用 LLM。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bazi_features import extract
from case_index import CaseIndex


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _case_chart(case: Dict[str, Any]) -> Dict[str, Any]:
    """复现 benchmark/runners/run_benchmark.py 中的 chart 构造逻辑。"""
    chart = (case or {}).get("chart_input") or {}
    if not chart:
        person = (case or {}).get("person") or {}
        birth = person.get("birth") or {}
        chart = {
            "four_pillars": {},
            "day_master": {},
            "birth_info": {
                "year": birth.get("year"),
                "month": birth.get("month"),
                "day": birth.get("day"),
                "hour": birth.get("hour"),
                "minute": birth.get("minute"),
                "gender": person.get("gender") or "",
            },
        }
    if case and isinstance(chart, dict):
        chart = dict(chart)
        chart["query_domain"] = case.get("domain") or "unknown"
        options = case.get("options") or []
        chart["query_text"] = " ".join(
            [str(case.get("question") or "")] + [str(opt) for opt in options]
        )
    return chart


def _extract_option_label(text: str) -> str:
    text = str(text or "").strip()
    if text and text[0].upper() in "ABCD":
        return text[0].upper()
    return ""


def evaluate(
    dataset_path: Path,
    corpus_path: Path,
    retrieval_mode: str,
    dense_model: Optional[str],
    reranker_model: Optional[str],
    option_evidence_k: int = 2,
) -> Dict[str, Any]:
    os.environ["BAZI_RAG"] = "1"
    os.environ["BAZI_RAG_CORPUS"] = str(corpus_path)

    cases = _load_jsonl(dataset_path)
    index = CaseIndex(
        corpus_path,
        use_hybrid=(retrieval_mode == "option_grounded_hybrid"),
        dense_model=dense_model,
        reranker_model=reranker_model,
    )

    top1 = 0
    top2 = 0
    ranks: List[int] = []
    per_case: List[Dict[str, Any]] = []

    for case in cases:
        chart = _case_chart(case)
        features = extract(chart)
        options = list(case.get("options") or [])
        answer = str(case.get("answer") or "").upper()

        evidence = index.option_evidence(
            features,
            question=str(case.get("question") or ""),
            options=options,
            domain=case.get("domain") or chart.get("query_domain"),
            k_per_option=option_evidence_k,
            retrieval_mode=retrieval_mode,
        )

        # 根据每个选项的 top-1 evidence source_answer_option_text 构建投票
        option_scores: Dict[str, float] = {}
        for label in ["A", "B", "C", "D"]:
            items = evidence.get(label) or []
            if items:
                item = items[0]
                source_label = _extract_option_label(item.get("source_answer_option_text") or "")
                option_scores[label] = item.get("score", 0.0)
                if source_label:
                    option_scores[source_label] = option_scores.get(source_label, 0.0) + item.get("score", 0.0)
            else:
                option_scores[label] = 0.0

        ranked = sorted(option_scores.items(), key=lambda x: -x[1])
        rank_of_gold = next(
            (i for i, (label, _) in enumerate(ranked, start=1) if label == answer),
            None,
        )

        if rank_of_gold == 1:
            top1 += 1
        if rank_of_gold is not None and rank_of_gold <= 2:
            top2 += 1
        if rank_of_gold is not None:
            ranks.append(rank_of_gold)

        per_case.append({
            "case_id": case.get("case_id"),
            "answer": answer,
            "rank": rank_of_gold,
            "ranked_options": [label for label, _ in ranked],
        })

    total = len(cases)
    return {
        "total": total,
        "retrieval_mode": retrieval_mode,
        "dense_model": dense_model,
        "reranker_model": reranker_model,
        "gold_top1": top1,
        "gold_top1_rate": top1 / total if total else 0.0,
        "gold_top2": top2,
        "gold_top2_rate": top2 / total if total else 0.0,
        "mean_rank": sum(ranks) / len(ranks) if ranks else None,
        "per_case": per_case,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Hybrid retrieval 离线评估")
    parser.add_argument("--dataset", required=True, help="holdout JSONL 路径")
    parser.add_argument("--corpus", required=True, help="语料库 JSONL 路径")
    parser.add_argument(
        "--retrieval-mode",
        default="option_grounded",
        choices=["option_grounded", "option_grounded_hybrid"],
        help="检索模式",
    )
    parser.add_argument("--dense-model", default=None, help="例如 BAAI/bge-small-zh-v1.5")
    parser.add_argument("--reranker-model", default=None, help="例如 BAAI/bge-reranker-v2-m3")
    parser.add_argument("--option-evidence-k", type=int, default=2)
    parser.add_argument("--output", default=None, help="JSON 输出路径（默认 stdout）")
    args = parser.parse_args(argv)

    result = evaluate(
        dataset_path=Path(args.dataset),
        corpus_path=Path(args.corpus),
        retrieval_mode=args.retrieval_mode,
        dense_model=args.dense_model,
        reranker_model=args.reranker_model,
        option_evidence_k=args.option_evidence_k,
    )

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
