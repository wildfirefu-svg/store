"""strategy_store.py：冻结 strategy_outputs.jsonl 的单源 loader。
路径显式传入（P0：镜像模式校验什么就消费什么，不读模块级真实 P9）。
畸形输入 fail-closed（Important 修复：损坏产物不得静默返回空候选）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_frozen_strategy_hits(strategy_outputs_path: Path) -> dict[str, dict[str, list[dict]]]:
    """读取冻结 strategy_outputs.jsonl → {query_id: {strategy: [完整命中]}}。
    silver judgment 与 bundle 一律从本函数取候选，不得在 QC 后重跑检索。
    畸形行/缺键/空产物 → fail-closed（sys.exit）。"""
    out: dict[str, dict[str, list[dict]]] = {}
    for i, line in enumerate(strategy_outputs_path.open(encoding="utf-8"), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            out.setdefault(r["query_id"], {})[r["strategy"]] = r["run1_hits"]
        except (json.JSONDecodeError, KeyError) as e:
            sys.exit(f"FAIL: corrupt strategy_outputs line {i}: {e}")
    if not out:
        sys.exit(f"FAIL: empty strategy_outputs: {strategy_outputs_path}")
    return out
