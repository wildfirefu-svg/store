"""Phase 9A-R1 归因：36 条分歧的零 API 分析（正式版本化脚本）。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    # 脚本内部 verify_frozen，防绕过门禁（当前 manifest stage + 自身代码 + 上游）
    pm.verify_frozen(P9R1 / "manifest_v5.json", ["attribution_py", "upstream_manifest_v4", "upstream_treatment_fingerprint"], required_stage="config_frozen")
    reviews = [json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip()]
    judgment = {r["item_id"] + "|" + r["canonical_key"]: r for r in (json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip())}
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    qid_to_args = {}
    for item in item_map["items"]:
        for q in item["queries"]:
            qid_to_args[q["query_id"]] = q["args"]

    disagreements = []
    for r in reviews:
        key = r["item_id"] + "|" + r["canonical_key"]
        silver_label = judgment[key]["label"]
        human_label = r["human_label"]
        if silver_label != human_label:
            disagreements.append({
                "item_id": r["item_id"],
                "canonical_key": r["canonical_key"],
                "silver": silver_label,
                "human": human_label,
                "note": r.get("note", ""),
                "reason": judgment[key].get("reason", ""),
                "query_ids": judgment[key].get("query_ids", []),
            })

    pairs = Counter((d["silver"], d["human"]) for d in disagreements)
    pr_to_r = [d for d in disagreements if d["silver"] == "partially_relevant" and d["human"] == "relevant"]
    cat_false = sum(1 for d in pr_to_r if "cat_match=False" in d["reason"])
    no_cat_count = 0
    for d in pr_to_r:
        if "cat_match=False" in d["reason"]:
            for qid in d["query_ids"]:
                args = qid_to_args.get(qid, {})
                if not args.get("category"):
                    no_cat_count += 1
                    break

    out = {
        "schema_version": "1.0",
        "source": "Phase 9A qc_human_review.jsonl + silver_relevance_judgment.jsonl + item_query_map.json",
        "total_disagreements": len(disagreements),
        "distribution": {
            "partially_relevant_to_relevant": pairs.get(("partially_relevant", "relevant"), 0),
            "partially_relevant_to_irrelevant": pairs.get(("partially_relevant", "irrelevant"), 0),
            "irrelevant_to_partially_relevant": pairs.get(("irrelevant", "partially_relevant"), 0),
        },
        "key_finding": {
            "cat_match_false_count": cat_false,
            "query_no_category_count": no_cat_count,
            "conclusion": "silver 规则在 query 无 category 参数时强制降级为 partial，但人工判断认为同义词命中即足够",
        },
        "disagreements": disagreements,
    }
    P9R1.mkdir(parents=True, exist_ok=True)
    (P9R1 / "attribution.json").write_text(
        json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"attribution written: {len(disagreements)} disagreements")


if __name__ == "__main__":
    main()
