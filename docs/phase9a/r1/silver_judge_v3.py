"""Phase 9A-R1 silver relevance judgment v3：校准 cat_ok 边界（query 无 category 时不降级）。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "retrieval"))
import retriever as rt

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"

RULE_SOURCE = "silver_rule_v3: synonym-cooccurrence AND category-consistency(query-arg, optional-when-absent) AND canonical-traceability"


def label_pair(term: str, query_category: str | None, doc: dict, synonym_table: dict) -> dict:
    """v3 校准：query 无 category 参数时 cat_ok=True（不降级）；有 category 时才校验匹配。"""
    syns = [term] + synonym_table["synonyms"].get(term, [])
    text = "".join(doc.get("text", "").split())
    syn_hit = any(s and s in text for s in syns)
    if query_category is None or query_category == "":
        cat_ok = True  # v3 修订：无 category 约束时不降级
    else:
        cat_ok = str(doc.get("category") or "") == str(query_category)
    if syn_hit and cat_ok:
        label = "relevant"
    elif syn_hit:
        label = "partially_relevant"
    else:
        label = "irrelevant"
    return {"label": label, "reason": f"syn={syn_hit} cat_match={cat_ok}", "rule_version": RULE_SOURCE}


def main() -> None:
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    import strategy_store as ss
    # 显式校验前代 sealed 状态（manifest_v4 是 sealed，非 code_frozen）
    pm.verify_frozen(P9 / "manifest_v4.json", ["retriever_py", "synonym_table", "query_set_frozen", "item_query_map",
                                               "strategy_store_py", "strategy_outputs"], required_stage="sealed")
    # 校验 R1 manifest 已达 code_frozen（silver_judge_v3_py 已冻结）
    pm.verify_frozen(P9R1 / "manifest_v5.json", ["silver_judge_v3_py"], required_stage="code_frozen")
    frozen = ss.load_frozen_strategy_hits(P9 / "strategy_outputs.jsonl")
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    syn = json.loads((P9 / "synonym_table.json").read_text(encoding="utf-8"))
    RANK = {"relevant": 3, "partially_relevant": 2, "irrelevant": 1, "uncertain": 0}
    agg: dict[tuple, dict] = {}
    for item in item_map["items"]:
        for q in item["queries"]:
            args = q["args"]
            term = (args.get("query") or args.get("name") or args.get("combo_name")
                    or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", ""))
            qcat = args.get("category")
            for hits in frozen.get(q["query_id"], {}).values():
                for h in hits:
                    key = (item["item_id"], h["canonical_key"])
                    doc = rt.doc_text(h["canonical_key"])
                    j = label_pair(term, qcat, doc, syn)
                    cur = agg.get(key)
                    if cur is None:
                        agg[key] = {"item_id": item["item_id"], "query_ids": [q["query_id"]], "canonical_key": h["canonical_key"],
                                    "label": j["label"], "reason": j["reason"], "rule_version": j["rule_version"]}
                    else:
                        if q["query_id"] not in cur["query_ids"]:
                            cur["query_ids"].append(q["query_id"])
                        if RANK[j["label"]] > RANK[cur["label"]]:
                            cur["label"], cur["reason"], cur["rule_version"] = j["label"], j["reason"], j["rule_version"]
    pairs = sorted(agg.values(), key=lambda r: (r["item_id"], r["canonical_key"]))
    # 原子写产物
    tmp_judgment = P9R1 / "silver_relevance_judgment_v3.jsonl.tmp"
    with tmp_judgment.open("w", encoding="utf-8", newline="\n") as f:
        for r in pairs:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp_judgment, P9R1 / "silver_relevance_judgment_v3.jsonl")
    summaries = {}
    for r in pairs:
        s = summaries.setdefault(r["item_id"], {"relevant": 0, "partially_relevant": 0, "irrelevant": 0, "uncertain": 0})
        s[r["label"]] += 1
    summary = {
        "schema_version": "1.0",
        "pool_stats": {"actual_pair_count": len(pairs), "items": len(item_map["items"]),
                       "rule_sha": hashlib.sha256(RULE_SOURCE.encode("utf-8")).hexdigest(),
                       "cross_query_aggregation": "max label rank, all contributing query_ids recorded"},
        "item_summaries": summaries,
        "rule_source": RULE_SOURCE,
    }
    tmp_summary = P9R1 / "silver_judgment_summary_v3.json.tmp"
    tmp_summary.write_text(json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp_summary, P9R1 / "silver_judgment_summary_v3.json")
    print(f"v3 judgment written: {len(pairs)} pairs; summary written")


if __name__ == "__main__":
    main()
