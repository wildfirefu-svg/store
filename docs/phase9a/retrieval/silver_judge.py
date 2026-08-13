"""Phase 9A silver relevance judgment：本地确定性规则初标（零 API，规则 SHA 冻结）。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retriever as rt

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"

RULE_SOURCE = "silver_rule_v2: synonym-cooccurrence AND category-consistency(query-arg) AND canonical-traceability"


def label_pair(term: str, query_category: str | None, doc: dict, synonym_table: dict) -> dict:
    """规则：条文文本含 term 或同义词 → 与 query 的 category 参数一致 → relevant/partial/irrelevant。
    category 一致性 = 条文 category == query category 参数（query 无 category 时降级为 partial）。"""
    syns = [term] + synonym_table["synonyms"].get(term, [])
    text = "".join(doc.get("text", "").split())
    syn_hit = any(s and s in text for s in syns)
    cat_ok = bool(query_category) and str(doc.get("category") or "") == str(query_category)
    if syn_hit and cat_ok:
        label = "relevant"
    elif syn_hit:
        label = "partially_relevant"
    else:
        label = "irrelevant"
    return {"label": label, "reason": f"syn={syn_hit} cat_match={cat_ok}", "rule_version": RULE_SOURCE}


def _atomic_write_text(path: Path, content: str) -> None:
    """原子写（tmp → 校验 → os.replace），与 phase9a_manifest._atomic_write 对齐。"""
    import os
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    json.loads(tmp.read_text(encoding="utf-8"))  # 写后校验
    os.replace(tmp, path)


def main() -> None:
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    import strategy_store as ss
    pm.verify_frozen(P9 / "manifest.json", ["retriever_py", "synonym_table", "query_set_frozen", "item_query_map",
                                            "silver_judge_py", "strategy_store_py", "strategy_outputs"])
    frozen = ss.load_frozen_strategy_hits(P9 / "strategy_outputs.jsonl")  # 单源：候选来自冻结 strategy_outputs（P0：不重跑检索，不依赖 evaluate）
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    syn = json.loads((P9 / "synonym_table.json").read_text(encoding="utf-8"))
    # 跨 query 聚合（冻结规则）：同一 (item, doc) 被多个 query 命中时取 max label
    # （relevant > partially_relevant > irrelevant > uncertain），记录全部 contributing query_ids
    RANK = {"relevant": 3, "partially_relevant": 2, "irrelevant": 1, "uncertain": 0}
    agg: dict[tuple, dict] = {}
    for item in item_map["items"]:
        for q in item["queries"]:
            args = q["args"]  # item_query_map 已含 entrypoint/args/top_n（无需查聚合 qset）
            term = (args.get("query") or args.get("name") or args.get("combo_name")
                    or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", ""))
            qcat = args.get("category")
            for hits in frozen.get(q["query_id"], {}).values():  # 单源：候选来自冻结 strategy_outputs（全策略并集）
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
    # 原子写产物（Important 修复：防截断）
    tmp_judgment = P9 / "silver_relevance_judgment.jsonl.tmp"
    with tmp_judgment.open("w", encoding="utf-8", newline="\n") as f:
        for r in pairs:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    import os
    os.replace(tmp_judgment, P9 / "silver_relevance_judgment.jsonl")
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
    _atomic_write_text(P9 / "silver_judgment_summary.json",
                       json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=1) + "\n")
    print(f"silver judgment written: {len(pairs)} pairs; summary written")


if __name__ == "__main__":
    main()
