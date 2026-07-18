from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.baziqa_prompt import format_birth_line
from benchmark.formatters.chart_context import (
    APPROVED_BAZI_FIELDS,
    approved_field_presence,
    render_chart_context,
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
