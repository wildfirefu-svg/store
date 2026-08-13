"""strategy_store.py：冻结 strategy_outputs.jsonl 的单源 loader。
路径显式传入（P0：镜像模式校验什么就消费什么，不读模块级真实 P9）。"""
from __future__ import annotations

import json
from pathlib import Path


def load_frozen_strategy_hits(strategy_outputs_path: Path) -> dict[str, dict[str, list[dict]]]:
    """读取冻结 strategy_outputs.jsonl → {query_id: {strategy: [完整命中]}}。
    silver judgment 与 bundle 一律从本函数取候选，不得在 QC 后重跑检索。"""
    rows = [json.loads(l) for l in strategy_outputs_path.open(encoding="utf-8") if l.strip()]
    out: dict[str, dict[str, list[dict]]] = {}
    for r in rows:
        out.setdefault(r["query_id"], {})[r["strategy"]] = r["run1_hits"]
    return out
