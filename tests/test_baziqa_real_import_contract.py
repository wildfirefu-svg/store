"""Contract tests for the BaziQA dataset importer.

These tests are skipped automatically when the upstream BaziQA repository is
not present. To enable, set BAZIQA_REAL_DIR to the directory containing
contest8_*.json files.
"""
import json
import os
from pathlib import Path

import pytest

REAL_DIR = os.environ.get("BAZIQA_REAL_DIR")


@pytest.mark.skipif(not REAL_DIR or not Path(REAL_DIR).exists(), reason="BaziQA real data not present")
def test_real_import_produces_at_least_one_year(tmp_path):
    from benchmark.runners.import_baziqa_dataset import (
        load_contest8_file,
        normalize_contest8_questions,
        write_jsonl,
    )

    rows = []
    for year in range(2021, 2026):
        path = Path(REAL_DIR) / f"contest8_{year}.json"
        if path.exists():
            rows.extend(normalize_contest8_questions(load_contest8_file(path)))

    assert rows, "No rows produced from real BaziQA data"

    output = tmp_path / "real.jsonl"
    write_jsonl(rows, output)

    loaded = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert loaded == rows
    sample = loaded[0]
    assert sample["case_id"]
    assert sample["person"]["birth"]["year"]
    assert sample["options"]
    assert sample["answer"]
