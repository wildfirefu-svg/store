from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.baziqa_prompt import format_birth_line, _assemble_reasoned_choice_prompt
from benchmark.formatters.chart_context import (
    APPROVED_BAZI_FIELDS,
    approved_field_presence,
    render_chart_context,
    render_reasoned_context,
    extract_reasoned_choice_answer,
)

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "phase6"
CASE_IDS = (1, 2, 3)
AS_OF = "2026-07-17"


def load_fixture(i: int) -> dict:
    return json.loads((FIXTURE_DIR / f"case_sample_{i}.json").read_text(encoding="utf-8"))


def identity_header(case: dict) -> str:
    """format_birth_line 输出的前 4 行（姓名/性别/出生/地点）。"""
    return "\n".join(format_birth_line(case).split("\n")[:4])


@pytest.mark.parametrize("i", CASE_IDS)
def test_legacy_v0_byte_identical_to_format_birth_line(i: int):
    case = load_fixture(i)
    assert render_chart_context(case, "legacy_v0") == format_birth_line(case)


@pytest.mark.parametrize("i", CASE_IDS)
def test_approved_v1_identity_header_byte_identical(i: int):
    case = load_fixture(i)
    assert render_chart_context(case, "approved_v1", as_of_date=AS_OF).startswith(
        identity_header(case)
    )


@pytest.mark.parametrize("i", CASE_IDS)
def test_approved_v1_golden_snapshot(i: int):
    golden = FIXTURE_DIR / f"approved_v1_case{i}.txt"
    rendered = render_chart_context(load_fixture(i), "approved_v1", as_of_date=AS_OF)
    if os.environ.get("PHASE6_UPDATE_GOLDEN") == "1":
        golden.write_text(rendered, encoding="utf-8")
    assert rendered == golden.read_text(encoding="utf-8")


def test_legacy_v0_golden_snapshot():
    golden = FIXTURE_DIR / "legacy_v0_case1.txt"
    rendered = render_chart_context(load_fixture(1), "legacy_v0")
    if os.environ.get("PHASE6_UPDATE_GOLDEN") == "1":
        golden.write_text(rendered, encoding="utf-8")
    assert rendered == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("i", CASE_IDS)
def test_render_deterministic_across_processes(i: int):
    fixture = FIXTURE_DIR / f"case_sample_{i}.json"
    code = (
        "import json,sys;sys.path.insert(0,'.');"
        "from benchmark.formatters.chart_context import render_chart_context;"
        f"case=json.load(open(r'{fixture}',encoding='utf-8'));"
        f"sys.stdout.write(render_chart_context(case,'approved_v1',as_of_date='{AS_OF}'))"
    )
    # Windows GBK locale：text=True 父进程按 GBK 解码而子进程写 UTF-8 会 UnicodeDecodeError；
    # 显式双边 UTF-8（偏离计划字面代码，意图不变，理由已入提交信息）
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    outs = [
        subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            encoding="utf-8", env=env, cwd=PROJECT_ROOT
        ).stdout
        for _ in range(2)
    ]
    assert outs[0] == outs[1]
    assert outs[0] == render_chart_context(load_fixture(i), "approved_v1", as_of_date=AS_OF)


def test_as_of_date_does_not_change_output():
    """approved_v1 无日期相关字段：as_of_date 仅入 manifest，不影响渲染。"""
    case = load_fixture(1)
    assert render_chart_context(case, "approved_v1", as_of_date="2026-07-17") == (
        render_chart_context(case, "approved_v1", as_of_date="2099-01-01")
    )


def test_denylist_values_never_rendered():
    case = load_fixture(1)
    case["chart_input"]["liu_nian"] = [{"year": 2099, "gan_zhi": "SENTINEL_LIUNIAN"}]
    for pillar in case["chart_input"]["four_pillars"].values():
        pillar["kong_wang"] = "SENTINEL_KONGWANG"
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert "SENTINEL_LIUNIAN" not in rendered
    assert "SENTINEL_KONGWANG" not in rendered


def test_unknown_schema_version_raises():
    with pytest.raises(ValueError, match="unknown schema_version"):
        render_chart_context(load_fixture(1), "v999")


@pytest.mark.parametrize("i", CASE_IDS)
def test_approved_field_presence_full(i: int):
    presence = approved_field_presence(load_fixture(i)["chart_input"])
    assert set(presence) == set(APPROVED_BAZI_FIELDS)
    missing = [k for k, ok in presence.items() if not ok]
    assert not missing, f"批准字段缺失: {missing}"


def test_approved_field_presence_partial():
    presence = approved_field_presence({"four_pillars": {}})
    assert presence["four_pillars"] is False
    assert presence["da_yun"] is False


@pytest.mark.parametrize("i", CASE_IDS)
def test_ziwei_section_rendered_when_present(i: int):
    case = load_fixture(i)
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    if case["chart_input"].get("ziwei"):
        assert "【紫微斗数·本命】" in rendered


def test_render_tolerates_partial_chart_input():
    """MingLi 归一化输入仅含部分八字键：缺失段跳过，不抛异常、不虚构。"""
    case = load_fixture(1)
    case["chart_input"] = {
        "four_pillars": case["chart_input"]["four_pillars"],
        "day_master": case["chart_input"]["day_master"],
    }
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert "【四柱】" in rendered
    assert "【大运】" not in rendered
    assert "【神煞】" not in rendered


# ---- 6B1-D: b2b (ziwei_mini) and b2c (sequential) tests ----

# 真实裸名宫位（不含"宫"后缀）
_REAL_PALACE_NAMES = [
    "父母", "福德", "田宅", "官禄", "仆役", "迁移",
    "疾厄", "财帛", "子女", "夫妻", "兄弟",
]

# 八字关键词（b2b 不应包含）
_BAZI_KEYWORDS = ["四柱", "日主", "大运", "神煞"]


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2b_ziwei_mini_contains_required_markers(i: int):
    """b2b 必须包含固定段标【紫微斗数·精简】、【命宫】、【身宫】、【主星】."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "ziwei_mini")
    assert "【紫微斗数·精简】" in rendered
    assert "【命宫】" in rendered
    assert "【身宫】" in rendered
    assert "【主星】" in rendered


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2b_ziwei_mini_excludes_secondary_palaces(i: int):
    """b2b 不应包含真实裸名次要宫位（父母、福德、田宅等）."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "ziwei_mini")
    for palace in _REAL_PALACE_NAMES:
        # 排除命宫和身宫本身
        if palace in ("命宫", "身宫"):
            continue
        assert palace not in rendered, f"b2b 不应包含次要宫位: {palace}"


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2b_ziwei_mini_excludes_bazi_keywords(i: int):
    """b2b 不应包含八字关键词（四柱、日主等）."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "ziwei_mini")
    for kw in _BAZI_KEYWORDS:
        assert kw not in rendered, f"b2b 不应包含八字关键词: {kw}"


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2b_ziwei_mini_excludes_auxiliary_and_daxian(i: int):
    """b2b 不应包含 auxiliary_stars、daxian、si_hua."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "ziwei_mini")
    # 检查不包含辅星段和大限段（_render_ziwei 中有"辅星："和"大限："）
    assert "辅星：" not in rendered
    assert "大限：" not in rendered
    assert "四化：" not in rendered


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2c_sequential_contains_bazi_and_ziwei(i: int):
    """b2c 必须包含八字完整部分和紫微完整部分."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "sequential")
    # 八字部分（format_birth_line 输出含姓名/性别等）
    assert "【紫微斗数·本命】" in rendered
    # 紫微部分
    assert "命宫：" in rendered or "命宫" in rendered


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2c_sequential_contains_separator(i: int):
    """b2c 必须包含分隔线 '--- 八字分析结束 ---'."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "sequential")
    assert "--- 八字分析结束 ---" in rendered


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2c_sequential_contains_instruction(i: int):
    """b2c 必须包含顺序推理指令."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "sequential")
    assert "请先基于八字信息进行初步分析" in rendered
    assert "再基于紫微斗数信息进行补充判断" in rendered
    assert "综合两者得出结论" in rendered


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2c_sequential_order_bazi_before_ziwei(i: int):
    """b2c 顺序: 八字 -> 分隔 -> 紫微 -> 指令."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "sequential")
    sep_pos = rendered.find("--- 八字分析结束 ---")
    ziwei_pos = rendered.find("【紫微斗数·本命】")
    instr_pos = rendered.find("请先基于八字信息")
    assert sep_pos > 0  # 分隔线存在
    assert ziwei_pos > sep_pos  # 紫微在分隔线之后
    assert instr_pos > ziwei_pos  # 指令在紫微之后


# Golden fixture: 从独立 fixture 文件加载, 来源 6B1 正式归档 audit_index.json
# 禁止用当前 renderer 重新生成（避免同源自证）
_GOLDEN_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "6b1d_golden_prompts.json"
_GOLDEN_META_PATH = PROJECT_ROOT / "tests" / "fixtures" / "6b1d_golden_prompts.meta.json"

_GOLDEN_FIXTURE_DATA = json.loads(_GOLDEN_FIXTURE_PATH.read_text(encoding="utf-8"))
_GOLDEN_META_DATA = json.loads(_GOLDEN_META_PATH.read_text(encoding="utf-8"))

# 9 个 golden SHA-256（从 fixture 文件加载）
_GOLDEN_FINGERPRINTS = _GOLDEN_FIXTURE_DATA["fingerprints"]

# fixture index -> case_id 映射
_FIXTURE_CASE_IDS = {
    1: "guangdong_female_19800824_P001-Q1",
    2: "guangdong_female_19800824_P001-Q2",
    3: "guangdong_female_19800824_P001-Q3",
}

# arm -> ziwei_arm 映射
_ARM_ZIWEI_MAP = _GOLDEN_FIXTURE_DATA["ziwei_arm_map"]


def test_golden_fixture_source_exists():
    """Golden fixture 源文件必须存在（6B1 正式归档 audit_index.json）."""
    source_path = PROJECT_ROOT / _GOLDEN_FIXTURE_DATA["source"]["audit_index_path"]
    assert source_path.exists(), f"Golden fixture 源缺失: {source_path}"


def test_golden_fixture_meta_exists():
    """Golden fixture meta.json 必须存在."""
    assert _GOLDEN_META_PATH.exists(), f"Golden fixture meta 缺失: {_GOLDEN_META_PATH}"


def test_golden_fixture_audit_index_sha256_matches():
    """fixture meta.json 中的 audit_index SHA-256 必须与实际文件一致."""
    source_path = PROJECT_ROOT / _GOLDEN_META_DATA["source_audit_index_path"]
    actual_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    expected_sha = _GOLDEN_META_DATA["source_audit_index_sha256"]
    assert actual_sha == expected_sha, (
        f"audit_index SHA-256 不匹配\n  actual: {actual_sha}\n  expected: {expected_sha}"
    )


def test_golden_fixture_matches_audit_index():
    """冻结的 9 个 SHA-256 必须与 audit_index.json 中的 context_fingerprints 完全一致."""
    source_path = PROJECT_ROOT / _GOLDEN_FIXTURE_DATA["source"]["audit_index_path"]
    with open(source_path, "r", encoding="utf-8") as f:
        audit = json.load(f)
    cf = audit["context_fingerprints"]
    for key, expected_sha in _GOLDEN_FINGERPRINTS.items():
        assert key in cf["fingerprints"], f"audit_index 缺少 key: {key}"
        assert cf["fingerprints"][key] == expected_sha, (
            f"golden fingerprint 不匹配 audit_index: {key}\n"
            f"  frozen: {expected_sha}\n"
            f"  audit:  {cf['fingerprints'][key]}"
        )


def test_golden_fixture_count_is_9():
    """Golden fixture 必须包含 3 case × 3 arm = 9 个指纹."""
    assert len(_GOLDEN_FINGERPRINTS) == 9
    assert _GOLDEN_FIXTURE_DATA["total"] == 9


@pytest.mark.parametrize("i", CASE_IDS)
@pytest.mark.parametrize("arm", ["b1a_prime", "b1b", "b1c"])
def test_b1_arms_byte_equivalent_to_golden_fixture(i: int, arm: str):
    """b1a'/b1b/b1c 的 prompt SHA-256 必须与 golden fixture 一致.

    Golden fingerprint 来自 6B1 audit_index.json 的 context_fingerprints,
    是对 _assemble_reasoned_choice_prompt(case, ctx) 的 SHA-256, 不是对 ctx 本身.
    cases 来自正式数据集（非 test fixture）.
    避免同源自证.
    """
    # 从正式数据集加载前 3 个 case（与 6B1 _compute_context_fingerprint 一致）
    dataset_path = PROJECT_ROOT / "benchmark" / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
    with open(dataset_path, "r", encoding="utf-8") as f:
        all_cases = [json.loads(line) for line in f if line.strip()]
    case = all_cases[i - 1]  # i=1,2,3 -> index 0,1,2
    case_id = _FIXTURE_CASE_IDS[i]
    ziwei_arm = _ARM_ZIWEI_MAP[arm]
    ctx = render_reasoned_context(case, "legacy_v0", ziwei_arm)
    prompt = _assemble_reasoned_choice_prompt(case, ctx)
    actual_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    golden_key = f"{case_id}_{arm}"
    expected_sha = _GOLDEN_FINGERPRINTS[golden_key]
    assert actual_sha == expected_sha, (
        f"字节不等价: {golden_key}\n"
        f"  actual:   {actual_sha}\n"
        f"  golden:   {expected_sha}\n"
        f"  prompt:   {prompt[:200]}..."
    )


@pytest.mark.parametrize("i", CASE_IDS)
def test_b1c_combined_contains_both_bazi_and_ziwei(i: int):
    """b1c (combined) 必须包含八字和紫微."""
    case = load_fixture(i)
    rendered = render_reasoned_context(case, "legacy_v0", "combined")
    assert "【紫微斗数·本命】" in rendered


def test_invalid_ziwei_arm_raises_value_error():
    """未知 ziwei_arm 必须抛 ValueError（库函数层）."""
    case = load_fixture(1)
    with pytest.raises(ValueError):
        render_reasoned_context(case, "legacy_v0", "unknown_arm")


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2b_ziwei_mini_missing_shengong(i: int):
    """缺失身宫时输出 '【身宫】未标注'."""
    case = load_fixture(i)
    # 删除身宫标记
    ziwei = case.get("chart_input", {}).get("ziwei", {})
    for palace in ziwei.get("twelve_palaces", []):
        palace["is_shengong"] = False
    rendered = render_reasoned_context(case, "legacy_v0", "ziwei_mini")
    assert "【身宫】未标注" in rendered


@pytest.mark.parametrize("i", CASE_IDS)
def test_b2b_ziwei_mini_shengong_same_as_ming(i: int):
    """命身同宫时输出 '命身同宫'."""
    case = load_fixture(i)
    ziwei = case.get("chart_input", {}).get("ziwei", {})
    # 找到命宫，把身宫标记设到命宫上
    for palace in ziwei.get("twelve_palaces", []):
        if palace.get("name") == "命宫":
            palace["is_shengong"] = True
        else:
            palace["is_shengong"] = False
    rendered = render_reasoned_context(case, "legacy_v0", "ziwei_mini")
    assert "命身同宫" in rendered


# ---- extract_reasoned_choice_answer: parser robustness ----

class TestExtractReasonedChoiceAnswer:
    """Parser must handle the answer formats deepseek-v4-pro actually produces.

    The reasoning model sometimes puts the answer letter on a separate line after
    '最终答案' with no colon (e.g. '### 最终答案\\nB'), which the original regex
    (requiring a colon + same-line) missed, causing parser_invalid in the smoke gate.
    """

    def test_same_line_full_width_colon(self):
        assert extract_reasoned_choice_answer("推理...\n最终答案：B") == "B"

    def test_same_line_half_width_colon(self):
        assert extract_reasoned_choice_answer("最终答案: C") == "C"

    def test_markdown_heading_same_line(self):
        assert extract_reasoned_choice_answer("### 最终答案：D") == "D"

    def test_markdown_heading_letter_on_next_line(self):
        """deepseek-v4-pro: '### 最终答案\\nB' (no colon, letter on next line)."""
        assert extract_reasoned_choice_answer("### 推理分析\n...\n### 最终答案\nB") == "B"

    def test_trailing_spaces_before_newline(self):
        """'### 最终答案  \\nC' (trailing spaces, letter on next line)."""
        assert extract_reasoned_choice_answer("### 最终答案  \nC") == "C"

    def test_last_match_wins(self):
        """When multiple 最终答案 lines exist, the last one wins (design §4.1.2)."""
        text = "最终答案：A\n更多推理...\n最终答案：B"
        assert extract_reasoned_choice_answer(text) == "B"

    def test_no_match_returns_none(self):
        assert extract_reasoned_choice_answer("无法判断") is None
        assert extract_reasoned_choice_answer("") is None
        assert extract_reasoned_choice_answer(None) is None
