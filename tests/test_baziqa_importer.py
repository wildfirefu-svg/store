import json
from pathlib import Path

from benchmark.runners.import_baziqa_dataset import (
    load_celebrity50_file,
    load_contest8_file,
    normalize_celebrity_questions,
    normalize_contest8_questions,
    write_jsonl,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baziqa"


def test_normalize_contest8_questions():
    data = load_contest8_file(FIXTURE_DIR / "contest8_sample.json")
    rows = normalize_contest8_questions(data)

    assert len(rows) == 2
    assert rows[0]["case_id"] == "fixture_female_19900101_P001-Q1"
    assert rows[0]["person"]["birth"]["year"] == 1990
    assert rows[0]["person"]["gender"] == "female"
    assert rows[0]["domain"] == "career"
    assert rows[0]["answer"] == "A"
    assert rows[0]["source"] == "contest8_2025"


def test_normalize_celebrity_questions_preserves_events():
    data = load_celebrity50_file(FIXTURE_DIR / "celebrity50_sample.json")
    rows = normalize_celebrity_questions(data)

    assert len(rows) == 1
    assert rows[0]["case_id"] == "fixture_celebrity_P001-Q1"
    assert rows[0]["person"]["name"] == "Fixture Celebrity"
    assert "事业" in rows[0]["verified_events"]
    assert rows[0]["answer"] == "B"


def test_write_jsonl(tmp_path):
    rows = [{"case_id": "q1", "answer": "A"}, {"case_id": "q2", "answer": "B"}]
    output = tmp_path / "out.jsonl"

    write_jsonl(rows, output)

    loaded = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert loaded == rows
