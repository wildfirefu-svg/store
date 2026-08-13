"""Phase 9A 分母冻结：从 required_knowledge 提取 112 项检索不可见项的 item→query 映射。"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8 = REPO / "docs" / "phase8" / "marriage-capability"
P9 = REPO / "docs" / "phase9a" / "retrieval"


def main() -> None:
    audit = [json.loads(l) for l in (P8 / "knowledge_audit.jsonl").open(encoding="utf-8") if l.strip()]
    rk = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "required_knowledge.jsonl").open(encoding="utf-8") if l.strip())}
    qset = json.loads((P8 / "kb_query_set.json").read_text(encoding="utf-8"))
    items = []
    for row in audit:
        for item in row["items"]:
            if item["gap_class"] != "检索不可见":
                continue
            src = next(i for i in rk[row["case_id"]]["items"] if i["item_id"] == item["item_id"])
            items.append({"item_id": item["item_id"], "case_id": row["case_id"],
                          "queries": [{"query_id": qs["query_id"], "entrypoint": qs["entrypoint"],
                                       "args": qs["args"], "top_n": qs["top_n"]} for qs in src["query_specs"]]})
    items.sort(key=lambda i: i["item_id"])
    payload = {"schema_version": "1.0",
               "source": "docs/phase8/marriage-capability/required_knowledge.jsonl + knowledge_audit.jsonl",
               "denominator": {"aggregate_queries": len(qset["queries"]), "items": len(items),
                                "item_query_refs": sum(len(i["queries"]) for i in items)},
               "items": items}
    P9.mkdir(parents=True, exist_ok=True)
    (P9 / "item_query_map.json").write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n")
    print(f"item_query_map written: {payload['denominator']}")


if __name__ == "__main__":
    main()
