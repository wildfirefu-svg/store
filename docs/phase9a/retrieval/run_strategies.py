"""Phase 9A 全量双跑：53 query × S1–S5，每策略独立命中落盘（双跑字节一致门）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retriever as rt

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"


def main() -> None:
    # 生产级 freeze-before-use 门（P0 修订）：代码/配置/上游指纹未冻结且 SHA 一致前拒绝执行
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    pm.verify_frozen(P9 / "manifest.json", ["retriever_py", "run_strategies_py", "strategy_store_py", "query_set_frozen",
                                            "ranking_config", "synonym_table", "upstream_inputs_sha"])
    qset = json.loads((P9 / "query_set_frozen.json").read_text(encoding="utf-8"))
    cfg = json.loads((P9 / "ranking_config.json").read_text(encoding="utf-8"))
    depth = cfg["pooling_depth_per_strategy_per_query"]
    rows = []
    for q in qset["queries"]:
        for name in ("s1", "s2", "s3", "s4", "s5"):
            args = q["args"]
            term = (args.get("query") or args.get("name") or args.get("combo_name")
                    or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", ""))
            fn = {"s1": lambda: rt.strategy_s1(q["entrypoint"], args, top_n=depth),
                  "s2": lambda: rt.strategy_s2(term, top_n=depth),
                  "s3": lambda: rt.strategy_s3(term, top_n=depth),
                  "s4": lambda: rt.strategy_s4(term, top_n=depth),
                  "s5": lambda: rt.strategy_s5(term, top_n=depth)}[name]
            run1 = [dict(h) for h in fn()]  # 完整命中信息：canonical_key/score/source_priority/category（P0：单源消费）
            run2 = [dict(h) for h in fn()]
            if run1 != run2:
                sys.exit(f"FAIL double-run: {q['query_id']} {name}")
            rows.append({"query_id": q["query_id"], "entrypoint": q["entrypoint"], "strategy": name,
                         "run1_hits": run1, "run2_hits": run2})
    with (P9 / "strategy_outputs.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"strategy outputs written: {len(rows)} rows (53 queries x 5 strategies)")


if __name__ == "__main__":
    main()
