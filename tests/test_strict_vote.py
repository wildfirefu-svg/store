from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.self_consistency import strict_majority


class TestStrictMajority:
    """设计 §5.2.4：≥3 票当选；无 3 票 → None（unresolved 计错）；
    None/invalid 票留在分母（len(votes) 恒 5）；禁止任何形式破平局。"""

    def test_three_of_five_wins(self):
        assert strict_majority(["A", "A", "A", "B", "C"]) == "A"      # 3/1/1

    def test_two_two_one_unresolved(self):
        assert strict_majority(["A", "A", "B", "B", "C"]) is None     # 2/2/1 无破平局

    def test_two_one_one_one_unresolved(self):
        assert strict_majority(["A", "A", "B", "C", "D"]) is None     # 2/1/1/1 不取相对多数

    def test_none_votes_stay_in_denominator(self):
        # 3 有效 A + 2 invalid(None) → 仍 3/5 当选（分母恒 5）
        assert strict_majority(["A", "A", "A", None, None]) == "A"
        # 2 有效 A + 3 invalid → 2/5 < 3 → unresolved
        assert strict_majority(["A", "A", None, None, None]) is None

    def test_all_none_unresolved(self):
        assert strict_majority([None, None, None, None, None]) is None

    def test_exact_threshold_boundary(self):
        assert strict_majority(["B", "B", "B", "A", "A"]) == "B"      # 恰好 3 票当选

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            strict_majority([])

    def test_custom_threshold(self):
        # threshold 参数化（默认 3）；双达阈值并存只可能 n>5，此时返回 None 不任选
        assert strict_majority(["A", "A", "B", "B"], threshold=2) is None
        assert strict_majority(["A", "A", "A", "A"], threshold=4) == "A"
