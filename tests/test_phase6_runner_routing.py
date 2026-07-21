from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.phase6_helpers import RunnerEnv, make_case

AS_OF_MARKERS = ("【四柱】", "【大运】", "【神煞】")

_ZIWEI = {
    "basic_info": {"ming_gong_gan_zhi": "甲子", "shen_gong_position": "午",
                   "wu_xing_ju": "水二局", "ming_zhu": "贪狼", "shen_zhu": "天同"},
    "twelve_palaces": [
        {"name": n, "position": "子", "tian_gan": "甲",
         "main_stars": [{"name": "紫微", "brightness": "庙"}],
         "auxiliary_stars": [], "daxian": "3-12", "is_shengong": False}
        for n in ("命宫", "兄弟宫", "夫妻宫", "子女宫", "财帛宫", "疾厄宫",
                  "迁移宫", "仆役宫", "官禄宫", "田宅宫", "福德宫", "父母宫")
    ],
    "si_hua": {},
}

# 裁决 2A：官方 astro 块取自 case["chart_input"]["official_astro"]（adapter 归一化形状）
_OFFICIAL_ASTRO = {
    "chinese_date": "庚午年戊子月甲子日",
    "time": "寅时",
    "five_elements_class": "水二局",
    "zodiac": "马",
    "palace_stars": {"命宫": "紫微（庙）", "夫妻": "天机（得）",
                     "财帛": "太阳（得）", "官禄": "武曲（庙）"},
}


def mingli_case(case_id: str = "c0", answer: str = "B") -> dict:
    case = make_case(case_id, answer)
    # 裁决 2A 配套（执行偏离，计划 mingli_case 增补）：官方 prompt 读 case["birth_info"]
    case["birth_info"] = {"raw": "1990年1月2日3时0分，男，北京"}
    case["chart_input"] = {
        "four_pillars": {k: {"gan": "甲", "zhi": "子", "gan_wuxing": "木", "zhi_wuxing": "水",
                             "shi_shen_gan": "比肩", "shi_shen_zhi_main": "正印",
                             "cang_gan": ["癸"], "cang_gan_shi_shen": ["正印"],
                             "nayin": "海中金"}
                         for k in ("year", "month", "day", "hour")},
        "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳", "shier_changsheng": "沐浴"},
        "shishen_stats": {"counts": {"比肩": 2}, "missing": [], "missing_human": ""},
        "wuxing_stats": {"jin": 1, "mu": 2, "shui": 1, "huo": 2, "tu": 2,
                         "missing": [], "strongest": "木", "weakest": "金"},
        "branch_relations": [],
        "shensha": [{"name": "天乙贵人", "position": "年干", "meaning": "主贵人扶助"}],
        "ziwei": _ZIWEI,
        "official_astro": _OFFICIAL_ASTRO,
    }
    return case


def last_user_text(env: RunnerEnv) -> str:
    return env.received[-1][-1]["content"]


def test_route_baziqa_xjz_direct_approved(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("B")
    assert env.run(profile="baziqa_xjz_direct") == 0
    text = last_user_text(env)
    for marker in AS_OF_MARKERS:
        assert marker in text
    assert "空亡" not in text


def test_route_baziqa_official_multi_turn(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
    env.model_returns("B")
    assert env.run(profile="baziqa_official_multi_turn") == 0
    first = env.received[0][0]["content"]       # multi_turn 首条 = 命主上下文
    assert "后续问题都围绕此命主" in first
    assert "【大运】" in first                  # approved 段标进入 multi_turn 上下文


def test_route_mingli_xjz_direct(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmark.runners.run_benchmark._mingli_data_ready", lambda: True)
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1, case_factory=mingli_case)
    env.model_returns("B")
    assert env.run(profile="mingli_xjz_direct") == 0
    assert "【紫微斗数·本命】" in last_user_text(env)


def test_route_mingli_official_cot_astro(tmp_path, monkeypatch):
    # 裁决 2A（执行偏离）：官方臂 prompt = format_official_cot_prompt(case) 单参，
    # astro 块为官方标记（八字命盘信息：/十二宫位星曜分布：），输出协议为 '答案：X'，
    # 不再断言计划原文的 "最终答案：" 与 "【紫微斗数·本命】"。
    monkeypatch.setattr("benchmark.runners.run_benchmark._mingli_data_ready", lambda: True)
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1, case_factory=mingli_case)
    env.model_returns("推理略。答案：B")
    assert env.run(profile="mingli_official_cot_astro") == 0
    text = last_user_text(env)
    assert "'答案：X'的格式" in text             # 官方 CoT 输出协议
    assert "八字命盘信息：" in text
    assert "十二宫位星曜分布：" in text


def test_mingli_prerequisite_missing_exit_4(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmark.runners.run_benchmark._mingli_data_ready", lambda: False)
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1, case_factory=mingli_case)
    env.model_returns("B")
    assert env.run(profile="mingli_official_cot_astro") == 4
    assert env.received == []                   # 前置缺失：零模型调用


def test_method_profile_conflict_exit_2(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("B")
    with pytest.raises(SystemExit) as exc:
        env.run(profile="baziqa_official_multi_turn",
                extra_argv=["--method", "direct_choice"])
    assert exc.value.code == 2


def test_visibility_blocked_zero_model_calls(tmp_path, monkeypatch):
    """裁决 1B 配套（计划 Task 6 增补，L2109）：XJZ profile 可见性失败 →
    任何模型调用之前短路；被 BLOCK 的 case 以 terminal_state=unresolved 计入 detail。"""
    monkeypatch.setattr("benchmark.runners.run_benchmark._mingli_data_ready", lambda: True)

    def ziwei_only_case(case_id: str) -> dict:
        case = make_case(case_id)
        case["chart_input"] = {"ziwei": _ZIWEI}   # 模拟真实 MingLi：0 结构化 bazi
        return case

    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2, case_factory=ziwei_only_case)
    env.model_returns("B")
    assert env.run(profile="mingli_xjz_direct") == 0
    assert env.received == []                      # 零模型调用
    rows = env.read_detail()
    assert len(rows) == 2
    assert all(r["terminal_state"] == "unresolved" for r in rows)
    assert all(r["gate_blocked"] is True for r in rows)
    assert env.read_summary()["status"] == "BLOCKED_PRECONDITION"
