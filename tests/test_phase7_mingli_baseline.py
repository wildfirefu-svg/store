"""Phase 7 Task 2：runner 终态 detail 显式写 chart_case_id（mingli_official_cot_astro fail-closed）。

设计依据：docs/superpowers/plans/2026-08-10-phase7-mingli-bench-baseline.md Task 2
（设计 §3.0：双主键——题目键 mingli_ftb_NNNN + 命盘键 case_N，fortune join 与
聚类统计用；chart_case_id 缺失拒绝仅限 mingli_official_cot_astro，BaziQA 系不报错）。

RunnerEnv 够用性说明：RunnerEnv 的 case_factory 参数天然支持自定义 case 字段，
此处用 _mingli_case 模拟 adapter（commit f55f58e）产出的 normalized 行形状
（题目键 mingli_ftb_* + chart_case_id + birth_info + chart_input.official_astro），
不需要最小等价物。_mingli_data_ready 被 monkeypatch 为 True（集成测试零网络，
不依赖真实 fetch 产物 data/mingli/）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners import run_benchmark
from tests.phase6_helpers import RunnerEnv

_OFFICIAL_ARGV = ["--profile", "mingli_official_cot_astro",
                  "--chart-schema-version", "approved_v1"]


def _mingli_case(cid: str) -> dict:
    """最小官方臂 normalized 行：astro 非空 dict（可见性 required 三结构性标记恒真），
    内容避开 _DENYLIST_MARKERS（【流年】/空亡：/空亡（）。"""
    return {
        "case_id": f"mingli_ftb_{cid}",
        "chart_case_id": "case_1",
        "question": "命主2024年事业运势如何？",
        "options": ["A. 顺利", "B. 一般", "C. 波折", "D. 停滞"],
        "answer": "A",
        "domain": "career",
        "birth_info": {"raw": "1990年1月2日3时0分，男，北京"},
        "chart_input": {
            "official_astro": {
                "chinese_date": "己巳年丙子月丁卯日",
                "time": "寅时",
                "five_elements_class": "木三局",
                "zodiac": "蛇",
                "palace_stars": {"命宫": "紫微 天府"},
            },
        },
    }


class TestDetailChartCaseIdHelper:
    def test_official_profile_with_value_returns_it(self):
        case = {"case_id": "mingli_ftb_0001", "chart_case_id": "case_1"}
        assert run_benchmark._detail_chart_case_id(
            case, "mingli_official_cot_astro") == "case_1"

    def test_official_profile_missing_fails_closed(self):
        """mingli_official_cot_astro + 缺失 → RuntimeError（fail-closed，拒绝跑缺键题）。"""
        with pytest.raises(RuntimeError, match="chart_case_id"):
            run_benchmark._detail_chart_case_id(
                {"case_id": "mingli_ftb_0001"}, "mingli_official_cot_astro")

    def test_other_profile_missing_returns_none(self):
        """baziqa 系 profile + 缺失 → None，不报错（缺失拒绝仅限官方臂）。"""
        assert run_benchmark._detail_chart_case_id(
            {"case_id": "c0"}, "baziqa_xjz_reasoned") is None


class TestDetailChartCaseIdIntegration:
    def test_parsed_and_invalid_details_carry_chart_case_id(self, tmp_path, monkeypatch):
        """正常路径 detail（parsed 与 invalid 终态）都带 chart_case_id。"""
        monkeypatch.setattr(run_benchmark, "_mingli_data_ready", lambda: True)
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2, case_factory=_mingli_case)
        env.model_sequence(["答案：A", "综合盘面信息，这里暂时无法给出确定答复。"])
        assert env.run(extra_argv=_OFFICIAL_ARGV) == 0
        rows = env.read_detail()
        assert len(rows) == 2
        by_state = {r["terminal_state"]: r for r in rows}
        assert set(by_state) == {"parsed", "invalid"}
        assert by_state["parsed"]["chart_case_id"] == "case_1"
        assert by_state["invalid"]["chart_case_id"] == "case_1"

    def test_call_failed_detail_carries_chart_case_id(self, tmp_path, monkeypatch):
        """call_failed 路径 failure_detail 带 chart_case_id（重试耗尽终态）。"""
        monkeypatch.setattr(run_benchmark, "_mingli_data_ready", lambda: True)
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1, case_factory=_mingli_case)
        env.model_fails(times=3)
        assert env.run(extra_argv=_OFFICIAL_ARGV) == 0
        rows = env.read_detail()
        assert len(rows) == 1
        failure_detail = rows[0]
        assert failure_detail["terminal_state"] == "call_failed"
        assert failure_detail["chart_case_id"] == "case_1"
