"""Accuracy summary helpers for repeated BaziQA benchmark runs."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Iterable, List


def _stdev(values: List[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def summarize_accuracy(rows: Iterable[dict]) -> Dict[str, dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row["label"])].append(float(row["accuracy"]))

    out: Dict[str, dict] = {}
    for label, values in grouped.items():
        out[label] = {
            "runs": len(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "stdev": _stdev(values),
        }
    return out


def trimmed_mean(values: Iterable[float], proportion: float = 0.1) -> float:
    """截尾均值（设计 §2.1/§4.5）：两端各截 int(n*proportion) 后取均值。

    MingLi 主指标、BaziQA 辅助指标；6A0 仅作描述性附列入报告，不入任何 gate。
    """
    vals = sorted(float(v) for v in values)
    if not vals:
        return 0.0
    k = int(len(vals) * proportion)
    core = vals[k:len(vals) - k] if k else vals
    return sum(core) / len(core)
