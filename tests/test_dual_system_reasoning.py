from benchmark.formatters.dual_system_reasoning import (
    build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt,
    build_judge_prompt, extract_judge_answer, judge_swap_seed, JUDGE_TEMPLATE_VERSION)
from benchmark.formatters.chart_context import render_reasoned_context
from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt


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


def _case():
    return {"case_id": "Q1", "question": "q", "options": ["a", "b", "c", "d"], "answer": "A",
            "chart_input": {"ziwei": _ZIWEI},
            "person": {"name": "t", "birth": {"place": "x"}}, "four_pillars": "戊子 甲子 丙寅 戊子"}


def test_bazi_prompt_byte_equal_6b1():
    c = _case()
    assert build_bazi_pipeline_prompt(c) == _assemble_reasoned_choice_prompt(
        c, render_reasoned_context(c, "legacy_v0", "none"))


def test_ziwei_prompt_byte_equal_6b1():
    c = _case()
    assert build_ziwei_pipeline_prompt(c) == _assemble_reasoned_choice_prompt(
        c, render_reasoned_context(c, "legacy_v0", "only"))


def test_judge_template_no_added_source_labels():
    c = _case()
    p = build_judge_prompt(c, "A", "r", "B", "r", swap=False)
    header = p[:p.index("## 分析一")]
    assert "分析一" in p and "分析二" in p
    assert "八字" not in header and "紫微" not in header


def test_swap_reorders():
    c = _case()
    assert "分析一\n结论：A" in build_judge_prompt(c, "A", "r", "B", "r", swap=False)
    assert "分析一\n结论：B" in build_judge_prompt(c, "A", "r", "B", "r", swap=True)


def test_swap_seed_deterministic():
    assert judge_swap_seed("baziqa", "Q1", 0) == judge_swap_seed("baziqa", "Q1", 0)
    import hashlib
    expected = int(hashlib.sha256("baziqa|Q1|0".encode()).hexdigest(), 16) % 2 == 1
    assert judge_swap_seed("baziqa", "Q1", 0) == expected
