"""MingLi APB smoke gate verification script (P3-T8).

Usage:
    python scripts/phase3_mingli_gate.py

Reads:
    .tmp/phase3_mingli20/baseline.jsonl
    .tmp/phase3_mingli20/apb.jsonl

Gate (P3-T8): MingLi 2025 first-20 cases under APB intervention >= 58%.
Advisory: if apb_acc < 60.0%, flag for review (non-blocking).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASELINE_PATH = ".tmp/phase3_mingli20/baseline.jsonl"
APB_PATH = ".tmp/phase3_mingli20/apb_v2.jsonl"

GATE_THRESHOLD = 0.58
ADVISORY_THRESHOLD = 0.60


def parse_accuracy(jsonl_path: str) -> float:
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing: {jsonl_path}")
    total = 0
    correct = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1
            if row.get("correct"):
                correct += 1
    if total == 0:
        raise ValueError(f"Empty JSONL: {jsonl_path}")
    return correct / total


def verify() -> bool:
    baseline_acc = parse_accuracy(BASELINE_PATH)
    apb_acc = parse_accuracy(APB_PATH)

    print(f"baseline_acc = {baseline_acc:.1%}")
    print(f"apb_acc      = {apb_acc:.1%}")
    print(f"gate (>=58%) : {'PASS' if apb_acc >= GATE_THRESHOLD else 'FAIL'}")

    if apb_acc < GATE_THRESHOLD:
        print(f"FAIL: MingLi APB smoke {apb_acc:.1%} < {GATE_THRESHOLD:.0%}")
        return False

    if apb_acc < ADVISORY_THRESHOLD:
        print(f"advisory: apb_acc {apb_acc:.1%} < {ADVISORY_THRESHOLD:.1%}, review required")

    return True


if __name__ == "__main__":
    ok = verify()
    if ok:
        print("P3-T8 gate PASS")
    else:
        print("P3-T8 gate FAIL")
    sys.exit(0 if ok else 1)
