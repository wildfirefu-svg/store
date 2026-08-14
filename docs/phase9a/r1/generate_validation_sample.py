"""Phase 9A-R1 验证集抽样 + 盲评 packet 生成（确定性无放回，61 条，37 item 覆盖）。"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
sys.path.insert(0, str(P9))
import retriever as rt  # noqa: E402


def pair_key(row):
    return (row["item_id"], row["canonical_key"])


def main() -> None:
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    # 脚本内部 verify_frozen，防绕过门禁
    pm.verify_frozen(P9R1 / "manifest_v5.json", ["generate_validation_sample_py", "upstream_manifest_v4"], required_stage="config_frozen")
    # 通过前代 sealed manifest 验证上游依赖
    pm.verify_frozen(P9 / "manifest_v4.json", ["silver_relevance_judgment", "qc_human_review", "item_query_map", "retriever_py"], required_stage="sealed")
    all_pairs = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
    dev_keys = {(r["item_id"], r["canonical_key"]) for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
    remaining = [r for r in all_pairs if pair_key(r) not in dev_keys]
    if len(remaining) < 61:
        sys.exit(f"BLOCKED_INPUT_DRIFT: remaining candidates {len(remaining)} < 61")
    pairs_by_item: dict[str, list] = {}
    for r in remaining:
        pairs_by_item.setdefault(r["item_id"], []).append(r)
    if len(pairs_by_item) != 37:
        sys.exit(f"BLOCKED_INPUT_DRIFT: remaining items {len(pairs_by_item)} != 37")
    rng = random.Random(20260814)
    first = [rng.choice(sorted(pairs_by_item[item_id], key=pair_key)) for item_id in sorted(pairs_by_item)]
    selected_keys = {pair_key(row) for row in first}
    remaining_pool = sorted((row for row in remaining if pair_key(row) not in selected_keys), key=pair_key)
    extra = rng.sample(remaining_pool, 24)
    sample = first + extra
    assert len(sample) == 61
    assert len({row["item_id"] for row in sample}) == 37
    assert len({pair_key(row) for row in sample}) == 61
    assert all(pair_key(row) not in dev_keys for row in sample)
    # 样本列表（原子写）
    payload = {
        "schema_version": "1.0",
        "seed": 20260814,
        "sample_size": 61,
        "pool_size": len(remaining),
        "sample_list": [{"item_id": s["item_id"], "canonical_key": s["canonical_key"]} for s in sample],
    }
    tmp_sample = P9R1 / "qc_sample_list_v2.json.tmp"
    tmp_sample.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    json.loads(tmp_sample.read_text(encoding="utf-8"))
    os.replace(tmp_sample, P9R1 / "qc_sample_list_v2.json")
    # 盲评 packet（不含 label/reason/开发集标签/归因结论；item_description 从 required_knowledge/knowledge_audit 构造）
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    # 从 Phase 8 冻结数据构造 item 需求描述（knowledge_audit 的 prompt_evidence.required_term + required_knowledge 的 query_specs）
    rk = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "required_knowledge.jsonl").open(encoding="utf-8") if l.strip())}
    audit = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "knowledge_audit.jsonl").open(encoding="utf-8") if l.strip())}
    item_desc = {}
    for item in item_map["items"]:
        case_id = item["case_id"]
        item_id = item["item_id"]
        # 从 knowledge_audit 取 required_term（prompt_evidence 字段，非顶层）
        req_term = ""
        if case_id in audit:
            for audit_item in audit[case_id]["items"]:
                if audit_item["item_id"] == item_id:
                    req_term = audit_item.get("prompt_evidence", {}).get("required_term", "")
                    break
        # 从 required_knowledge 取 query_specs（非 knowledge_audit）；
        # args 词键随 entrypoint 变化：query/name/combo_name/gan_or_zhi（与 retriever.pool_candidates 的 term 提取一致）
        query_terms = []
        if case_id in rk:
            for rk_item in rk[case_id]["items"]:
                if rk_item["item_id"] == item_id:
                    for qs in rk_item.get("query_specs", []):
                        args = qs.get("args", {})
                        term = args.get("query") or args.get("name") or args.get("combo_name") or args.get("gan_or_zhi") or ""
                        if term:
                            query_terms.append(term)
                    break
        item_desc[item_id] = f"required_term={req_term}; query_terms={','.join(query_terms[:3])}"
    packet_lines = []
    for s in sample:
        doc = rt.doc_text(s["canonical_key"])
        packet_lines.append({
            "item_id": s["item_id"],
            "canonical_key": s["canonical_key"],
            "item_description": item_desc.get(s["item_id"], ""),
            "document_text": doc.get("text", ""),  # 完整文本（非截断），与 silver 规则消费一致
            "source_location": s["canonical_key"],
        })
    tmp_packet = P9R1 / "qc_review_packet_v2.jsonl.tmp"
    with tmp_packet.open("w", encoding="utf-8", newline="\n") as f:
        for p in packet_lines:
            f.write(json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp_packet, P9R1 / "qc_review_packet_v2.jsonl")
    print(f"validation sample + review packet written: {len(sample)} samples, 37 items")


if __name__ == "__main__":
    main()
