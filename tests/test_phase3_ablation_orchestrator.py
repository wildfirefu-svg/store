"""Tests for scripts.run_phase3_ablation Task 11 orchestrator.

Verifies command generation, budget estimation, and dry-run plan output
WITHOUT invoking any subprocess.

v4 update: tests adapted to pre-permuted dataset scheme (on-3 mode no
longer passes --shuffle-options; instead uses pre-permuted dataset files).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase3_ablation import (
    build_command_list,
    estimate_budget,
    ARMS,
    STAGES,
)


def _make_case(i: int) -> dict:
    return {
        "case_id": f"c{i}",
        "question": f"q{i}",
        "options": [
            {"id": f"o{i}_1", "text": "alpha"},
            {"id": f"o{i}_2", "text": "beta"},
            {"id": f"o{i}_3", "text": "gamma"},
            {"id": f"o{i}_4", "text": "delta"},
        ],
        "answer": f"o{i}_1",
    }


@pytest.fixture
def mini_dataset(tmp_path: Path) -> str:
    path = tmp_path / "mini.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for i in range(8):
            fh.write(json.dumps(_make_case(i), ensure_ascii=False) + "\n")
    return str(path)


def test_build_command_list_dev20_count(mini_dataset: str, tmp_path: Path):
    """dev20: 3 arms x 2 modes x 3 perms = 18 commands."""
    cmds = build_command_list(
        stage="dev20",
        dataset=mini_dataset,
        corpus="c.jsonl",
        model="m",
        fewshot_file="f.jsonl",
        output_dir=str(tmp_path / "out"),
        n_perms=3,
    )
    assert len(cmds) == 18


def test_build_command_list_link8_count(mini_dataset: str, tmp_path: Path):
    """link8: 3 arms x 2 modes x 3 perms = 18 commands."""
    cmds = build_command_list(
        "link8", mini_dataset, "c.jsonl", "m", "f.jsonl", str(tmp_path / "out")
    )
    assert len(cmds) == 18


def test_each_command_has_required_fields(mini_dataset: str, tmp_path: Path):
    cmds = build_command_list(
        "dev20", mini_dataset, "c.jsonl", "m", "f.jsonl", str(tmp_path / "out")
    )
    for c in cmds:
        assert "arm" in c
        assert "mode" in c
        assert "perm_idx" in c
        assert "command" in c
        assert "details_path" in c
        assert "config" in c


def test_on3_mode_uses_permuted_dataset(mini_dataset: str, tmp_path: Path):
    """on-3 mode uses pre-permuted dataset file, does NOT pass --shuffle-options."""
    cmds = build_command_list(
        "dev20", mini_dataset, "c.jsonl", "m", "f.jsonl", str(tmp_path / "out")
    )
    on3_cmds = [c for c in cmds if c["mode"] == "on-3"]
    assert len(on3_cmds) == 9
    for c in on3_cmds:
        cmd_str = " ".join(c["command"])
        assert "--shuffle-options" not in cmd_str
        assert "--shuffle-seed" not in cmd_str
        idx = c["command"].index("--dataset")
        ds_arg = c["command"][idx + 1]
        assert ds_arg != mini_dataset


def test_off3_mode_has_no_shuffle(mini_dataset: str, tmp_path: Path):
    cmds = build_command_list(
        "dev20", mini_dataset, "c.jsonl", "m", "f.jsonl", str(tmp_path / "out")
    )
    off_cmds = [c for c in cmds if c["mode"] == "off-3"]
    assert len(off_cmds) == 9
    for c in off_cmds:
        cmd_str = " ".join(c["command"])
        assert "--shuffle-options" not in cmd_str


def test_a4_has_fewshot_file(mini_dataset: str, tmp_path: Path):
    cmds = build_command_list(
        "dev20", mini_dataset, "c.jsonl", "m", "f.jsonl", str(tmp_path / "out")
    )
    a4_cmds = [c for c in cmds if c["arm"] == "A4"]
    for c in a4_cmds:
        cmd_str = " ".join(c["command"])
        assert "--fewshot-file" in cmd_str


def test_a1_has_no_fewshot(mini_dataset: str, tmp_path: Path):
    cmds = build_command_list(
        "dev20", mini_dataset, "c.jsonl", "m", "f.jsonl", str(tmp_path / "out")
    )
    a1_cmds = [c for c in cmds if c["arm"] == "A1"]
    for c in a1_cmds:
        cmd_str = " ".join(c["command"])
        assert "--fewshot-file" not in cmd_str


def test_a3_a4_have_apb_a1_does_not(mini_dataset: str, tmp_path: Path):
    cmds = build_command_list(
        "dev20", mini_dataset, "c.jsonl", "m", "f.jsonl", str(tmp_path / "out")
    )
    for c in cmds:
        if c["arm"] in ("A3", "A4"):
            assert c["config"]["apb"] is True
        else:
            assert c["config"]["apb"] is False


def test_estimate_budget_dev20():
    b = estimate_budget("dev20")
    assert b["planned_primary_calls"] == 360
    assert b["hard_call_cap"] == 432


def test_estimate_budget_formal40():
    b = estimate_budget("formal40")
    assert b["planned_primary_calls"] == 240
    assert b["hard_call_cap"] == 288


def test_estimate_budget_link8():
    b = estimate_budget("link8")
    assert b["planned_primary_calls"] == 144
    assert b["hard_call_cap"] == 174


def test_all_stages_have_hard_cap():
    for stage in STAGES:
        b = estimate_budget(stage)
        assert b["hard_call_cap"] >= b["planned_primary_calls"]


def test_dry_run_returns_zero(capsys, mini_dataset: str, tmp_path: Path):
    from scripts.run_phase3_ablation import main
    rc = main([
        "--dry-run", "--stage", "link8",
        "--dataset", mini_dataset,
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "link8" in captured.out
    assert "dataset:" in captured.out
    assert "total commands:" in captured.out


def test_no_dry_run_returns_error(capsys, mini_dataset: str, tmp_path: Path):
    from scripts.run_phase3_ablation import main
    rc = main([
        "--stage", "link8",
        "--dataset", mini_dataset,
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 1
