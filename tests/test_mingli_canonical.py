from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.chart_context import render_chart_context
from benchmark.formatters.mingli_prompt import (
    OFFICIAL_COT_TEMPLATE_VERSION,
    OFFICIAL_SYSTEM_PROMPT,
    format_official_cot_prompt,
)
from benchmark.runners.mingli_bench_adapter import load_and_normalize, to_canonical_chart_input
from benchmark.runners.profiles import (
    assert_visibility,
    resolve_profile,
    visibility_gate,
    visibility_requirements,
)

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "phase6"
SAMPLE = FIXTURE_DIR / "mingli_fortune_sample.json"
AS_OF = "2026-07-17"

BAZI_SHAPE = {
    "bazi": {
        "four_pillars": {
            k: {"gan": "甲", "zhi": "子", "gan_wuxing": "木", "zhi_wuxing": "水",
                "shi_shen_gan": "比肩", "shi_shen_zhi_main": "正印",
                "cang_gan": ["癸"], "cang_gan_shi_shen": ["正印"], "nayin": "海中金"}
            for k in ("year", "month", "day", "hour")
        },
        "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳", "shier_changsheng": "沐浴"},
        "shishen_stats": {"counts": {"比肩": 2}, "missing": [], "missing_human": ""},
        "wuxing_stats": {"jin": 1, "mu": 2, "shui": 1, "huo": 2, "tu": 2,
                         "missing": [], "strongest": "木", "weakest": "金"},
        "branch_relations": [],
        "shensha": [{"name": "天乙贵人", "position": "年干", "meaning": "主贵人扶助"}],
        "wuyun_liuqi": {"unapproved": True},
    }
}


def load_entry() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def make_case(entry: dict) -> dict:
    return {
        "person": {"name": "匿名命主", "gender": "male",
                   "birth": {"year": 1974, "month": 4, "day": 28,
                             "hour": 16, "minute": 40, "place": "usa"}},
        "birth_info": entry["birth_info"],
        "chart_input": to_canonical_chart_input(entry),
        "question": "命主今年财运如何？",
        "options": ["A. 好", "B. 差", "C. 平", "D. 先好后差"],
    }


def test_bazi_shape_canonical_drops_unapproved():
    canonical = to_canonical_chart_input(BAZI_SHAPE)
    assert "wuyun_liuqi" not in canonical
    for key in ("four_pillars", "day_master", "shishen_stats",
                "wuxing_stats", "branch_relations", "shensha"):
        assert key in canonical


def test_bazi_shape_renders_and_visibility_core_passes():
    case = {
        "person": {"name": "匿名命主", "gender": "female",
                   "birth": {"year": 1990, "month": 1, "day": 1, "hour": 0, "minute": 0, "place": "上海"}},
        "chart_input": to_canonical_chart_input(BAZI_SHAPE),
    }
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert "【四柱】" in rendered and "【神煞】" in rendered
    assert "【大运】" not in rendered  # MingLi 源数据缺口：缺失段跳过不虚构
    # bazi 形状无 palaces → 无紫微段：mingli 可见性须如实报缺
    violations = assert_visibility(rendered, resolve_profile("mingli_xjz_direct"), "approved_v1")
    assert any("【紫微斗数·本命】" in v for v in violations)


# ---- 裁决 1B：真实数据（API 形状，0 结构化 bazi）的 canonical 与可见性 ----

def test_real_sample_canonical_ziwei_mapping():
    """定稿真实键映射：basic_info 与十二宫字段逐一对应已核验源键。"""
    canonical = to_canonical_chart_input(load_entry())
    zw = canonical["ziwei"]
    info = zw["basic_info"]
    assert info["ming_gong_gan_zhi"] == "癸酉"      # name=="命宫" 宫 heavenlyStem+earthlyBranch
    assert info["shen_gong_position"] == "丑"       # earthlyBranchOfBodyPalace
    assert info["wu_xing_ju"] == "金四局"           # fiveElementsClass
    assert info["ming_zhu"] == "文曲"               # soul
    assert info["shen_zhu"] == "天梁"               # body
    palaces = zw["twelve_palaces"]
    assert len(palaces) == 12
    by_name = {p["name"]: p for p in palaces}
    ming = by_name["命宫"]
    assert ming["tian_gan"] == "癸" and ming["position"] == "酉"
    assert [(s["name"], s["brightness"]) for s in ming["main_stars"]] == [("天同", "平")]
    # 辅星 = minorStars + adjectiveStars（保留 name+brightness）
    assert [s["name"] for s in ming["auxiliary_stars"]] == ["火星", "天福", "空亡", "破碎"]
    assert ming["auxiliary_stars"][0]["brightness"] == "得"
    assert ming["daxian"] == "4-13"                 # decadal.range
    assert ming["is_shengong"] is False
    guanlu = by_name["官禄"]
    assert guanlu["is_shengong"] is True            # isBodyPalace
    assert guanlu["tian_gan"] == "丁" and guanlu["position"] == "丑"


def test_real_sample_xjz_blocked_precisely():
    """裁决 1B：紫微渲染通过；八字核心六段精确报缺；状态 BLOCKED_PRECONDITION。"""
    case = make_case(load_entry())
    profile = resolve_profile("mingli_xjz_direct")
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert "【紫微斗数·本命】" in rendered           # 紫微段渲染成功
    assert "命宫（酉·癸）" in rendered               # 宫位映射进入渲染文本
    violations = assert_visibility(rendered, profile, "approved_v1")
    expected_missing = {f"required 缺失: {m}" for m in (
        "【四柱】", "【日主】", "【五行统计】", "【十神统计】", "【地支关系】", "【神煞】",
    )}
    assert set(violations) == expected_missing       # 精确六段缺失，无其他违规
    assert visibility_gate(rendered, profile, "approved_v1") == "BLOCKED_PRECONDITION"


# ---- 裁决 2A：官方 profile（1:1 官方模板）真实样例 ----

def test_real_sample_official_profile_passes():
    """0 结构化 bazi 不影响官方臂：官方 astro required 全过，astro 块内容真实。"""
    case = make_case(load_entry())
    profile = resolve_profile("mingli_official_cot_astro")
    prompt = format_official_cot_prompt(case)
    assert assert_visibility(prompt, profile, "approved_v1") == []
    assert visibility_gate(prompt, profile, "approved_v1") == "PASS"
    assert "八字：甲寅 戊辰 己亥 壬申" in prompt
    assert "时辰：申时" in prompt
    assert "五行局：金四局" in prompt
    assert "生肖：虎" in prompt
    assert "命宫：天同 火星" in prompt               # 官方仅 major+minor 星名
    assert "夫妻：天梁 左辅 右弼 天钺 地劫" in prompt


def test_profile_isolation_same_data():
    """同一真实数据：official → PASS；xjz → BLOCKED；required 不因 dataset 相同而共享。"""
    case = make_case(load_entry())
    official = resolve_profile("mingli_official_cot_astro")
    xjz = resolve_profile("mingli_xjz_direct")
    req_official, _ = visibility_requirements(official, "approved_v1")
    req_xjz, _ = visibility_requirements(xjz, "approved_v1")
    assert req_official != req_xjz
    prompt = format_official_cot_prompt(case)
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert visibility_gate(prompt, official, "approved_v1") == "PASS"
    assert visibility_gate(rendered, xjz, "approved_v1") == "BLOCKED_PRECONDITION"


# ---- 官方 prompt golden 与协议细节 ----

def test_official_system_prompt_constant():
    assert OFFICIAL_COT_TEMPLATE_VERSION == "mingli_official_replica_v1"
    assert OFFICIAL_SYSTEM_PROMPT == (
        "你是一位精通中国传统命理学的专家，包括八字命理、紫微斗数等。"
        "请根据给定的信息进行分析和回答。"
    )


def test_official_cot_prompt_golden():
    """golden 覆盖：user prompt 全文（含官方 astro 块）、选项排序、答案：X 格式。"""
    case = make_case(load_entry())
    case["options"] = ["C. 平", "A. 好", "D. 先好后差", "B. 差"]  # 乱序 → golden 验证排序
    prompt = format_official_cot_prompt(case)
    assert prompt.startswith("以下是一道关于中国传统命理的题目。")
    assert "'答案：X'的格式" in prompt
    golden = FIXTURE_DIR / "mingli_prompt_golden.txt"
    if os.environ.get("PHASE6_UPDATE_GOLDEN") == "1":
        golden.write_text(prompt, encoding="utf-8")
    assert prompt == golden.read_text(encoding="utf-8")


def test_official_options_sorted_by_letter():
    case = make_case(load_entry())
    case["options"] = [{"letter": "D", "text": "四"}, {"letter": "B", "text": "二"},
                       {"letter": "A", "text": "一"}, {"letter": "C", "text": "三"}]
    prompt = format_official_cot_prompt(case)
    section = prompt.split("选项：\n", 1)[1]
    assert section == "A. 一\nB. 二\nC. 三\nD. 四\n"


def test_official_prompt_without_astro_omits_block():
    """官方行为：无 fortune 数据则不注入 astro 块。"""
    case = make_case(load_entry())
    case["chart_input"] = {}
    prompt = format_official_cot_prompt(case)
    assert "八字命盘信息：" not in prompt
    assert "紫微命盘信息：" not in prompt
    assert "命主信息：" in prompt and "问题：" in prompt


# ---- adapter 集成：row 携带 birth_info 与 canonical ----

def test_load_and_normalize_row_carries_birth_info_and_canonical(tmp_path):
    entry = load_entry()
    data = tmp_path / "data.json"
    data.write_text(json.dumps([{
        "case_id": entry["case_id"], "question": "Q?",
        "options": ["A. a", "B. b", "C. c", "D. d"], "answer": "A",
        "category": "财运", "year": "2024", "birth_info": entry["birth_info"],
    }], ensure_ascii=False), encoding="utf-8")
    fortune = tmp_path / "fortune.json"
    fortune.write_text(json.dumps([entry], ensure_ascii=False), encoding="utf-8")
    rows = load_and_normalize(str(data), fortune_api_json_path=str(fortune), include_astro=True)
    assert len(rows) == 1
    row = rows[0]
    assert row["birth_info"]["raw"] == entry["birth_info"]["raw"]
    assert row["chart_input"]["ziwei"]["basic_info"]["wu_xing_ju"] == "金四局"
    assert row["chart_input"]["official_astro"]["chinese_date"] == "甲寅 戊辰 己亥 壬申"
    assert row["chart_input"]["official_astro"]["palace_stars"]["命宫"] == "天同 火星"
