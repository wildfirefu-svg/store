import json
from pathlib import Path

from scripts.build_baziqa_domain_subsets import DOMAINS, build_domain_subsets


def _row(case_id: str, domain: str, source: str = "holdout") -> dict:
    return {
        "case_id": case_id,
        "domain": domain,
        "source": source,
        "question": f"{domain} question {case_id}",
        "options": ["A", "B", "C", "D"],
        "answer": "A",
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_build_domain_subsets_outputs_all_domains_between_min_and_max(tmp_path):
    holdout = tmp_path / "holdout.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    out_dir = tmp_path / "subsets"

    holdout_rows = (
        [_row(f"h{i}", "health") for i in range(3)]
        + [_row(f"a{i}", "annual_fortune") for i in range(2)]
        + [_row(f"r{i}", "relationship") for i in range(6)]
        + [_row(f"u{i}", "unknown") for i in range(12)]
    )
    corpus_rows = (
        [_row(f"ch{i}", "health", "corpus") for i in range(4)]
        + [_row(f"ca{i}", "annual_fortune", "corpus") for i in range(4)]
        + [_row(f"cr{i}", "relationship", "corpus") for i in range(4)]
        + [_row(f"cu{i}", "unknown", "corpus") for i in range(4)]
    )
    _write_jsonl(holdout, holdout_rows)
    _write_jsonl(corpus, corpus_rows)

    stats = build_domain_subsets(holdout, corpus, out_dir)

    assert set(stats) == set(DOMAINS)
    for domain in DOMAINS:
        rows = _read_jsonl(out_dir / f"{domain}.jsonl")
        assert 5 <= len(rows) <= 10
        assert all(row["domain"] == domain for row in rows)
        assert stats[domain]["total"] == len(rows)


def test_underfilled_domain_uses_corpus_fill_source(tmp_path):
    holdout = tmp_path / "holdout.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    out_dir = tmp_path / "subsets"

    _write_jsonl(holdout, [_row(f"h{i}", "health") for i in range(3)])
    _write_jsonl(corpus, [_row(f"ch{i}", "health", "corpus") for i in range(5)])

    stats = build_domain_subsets(holdout, corpus, out_dir, domains=["health"])
    rows = _read_jsonl(out_dir / "health.jsonl")

    assert len(rows) == 5
    assert stats["health"] == {"holdout": 3, "corpus_fill": 2, "total": 5}
    assert sum(1 for row in rows if row["source"] == "corpus_fill") == 2
    assert [row["case_id"] for row in rows[:3]] == ["h0", "h1", "h2"]


def test_sufficient_domain_does_not_use_corpus_fill(tmp_path):
    holdout = tmp_path / "holdout.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    out_dir = tmp_path / "subsets"

    _write_jsonl(holdout, [_row(f"r{i}", "relationship") for i in range(7)])
    _write_jsonl(corpus, [_row(f"cr{i}", "relationship", "corpus") for i in range(5)])

    stats = build_domain_subsets(holdout, corpus, out_dir, domains=["relationship"])
    rows = _read_jsonl(out_dir / "relationship.jsonl")

    assert len(rows) == 7
    assert stats["relationship"] == {"holdout": 7, "corpus_fill": 0, "total": 7}
    assert all(row["source"] != "corpus_fill" for row in rows)


def test_sufficient_domain_is_capped_at_max_cases(tmp_path):
    holdout = tmp_path / "holdout.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    out_dir = tmp_path / "subsets"

    _write_jsonl(holdout, [_row(f"u{i}", "unknown") for i in range(12)])
    _write_jsonl(corpus, [_row(f"cu{i}", "unknown", "corpus") for i in range(5)])

    stats = build_domain_subsets(holdout, corpus, out_dir, domains=["unknown"])
    rows = _read_jsonl(out_dir / "unknown.jsonl")

    assert len(rows) == 10
    assert stats["unknown"] == {"holdout": 10, "corpus_fill": 0, "total": 10}
    assert [row["case_id"] for row in rows] == [f"u{i}" for i in range(10)]
