import json
from pathlib import Path

from benchmark.runners.split_baziqa_by_year import split_by_holdout_year


def _write_rows(path: Path, years):
    with path.open("w", encoding="utf-8") as f:
        for i, year in enumerate(years):
            f.write(json.dumps({
                "case_id": f"c{i}",
                "source_year": str(year),
                "person": {"person_id": f"p{i}", "birth": {"year": 1990}},
                "question": "命主事业?",
                "options": ["A", "B", "C", "D"],
                "answer": "A",
            }, ensure_ascii=False) + "\n")


def test_split_by_holdout_year_excludes_holdout_from_corpus(tmp_path):
    source = tmp_path / "all.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    holdout = tmp_path / "holdout.jsonl"
    _write_rows(source, [2021, 2022, 2025, 2025])

    stats = split_by_holdout_year(source, 2025, corpus, holdout)

    assert stats == {"corpus": 2, "holdout": 2}
    assert all(json.loads(line)["source_year"] != "2025" for line in corpus.read_text(encoding="utf-8").splitlines())
    assert all(json.loads(line)["source_year"] == "2025" for line in holdout.read_text(encoding="utf-8").splitlines())
