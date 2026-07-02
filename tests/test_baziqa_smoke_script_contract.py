import json
from pathlib import Path

from benchmark.runners.import_baziqa_dataset import (
    load_contest8_file,
    normalize_contest8_questions,
    write_jsonl,
)


def test_smoke_fixture_json_can_build_non_empty_jsonl(tmp_path):
    fixture = Path("tests/fixtures/baziqa/contest8_sample.json")
    rows = normalize_contest8_questions(load_contest8_file(fixture))
    output = tmp_path / "contest8_sample.jsonl"

    write_jsonl(rows, output)

    loaded = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(loaded) == 2
    assert loaded[0]["case_id"]
    assert loaded[0]["answer"] in ["A", "B", "C", "D"]


def test_smoke_script_accepts_local_key_files():
    script = Path("scripts/verify_baziqa_smoke.ps1").read_text(encoding="utf-8")
    assert ".deepseek_key" in script
    assert ".anthropic_key" in script
    assert "Get-Content \".deepseek_key\"" in script
    assert "Get-Content \".anthropic_key\"" in script
