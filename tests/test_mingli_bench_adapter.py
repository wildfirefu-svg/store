"""Failing tests for the MingLi-Bench adapter.

Interface under test (see docs/superpowers/plans/2026-07-01-phase1-evaluation-infra.md
Task 3.2):

- benchmark.runners.mingli_bench_adapter.load_and_normalize(
      data_json_path, fortune_api_json_path=None, include_astro=False,
      year_filter=None, category_filter=None) -> List[Dict]

Behaviour contract:
1. Each output row exposes case_id / question / options / answer / domain / year / category.
2. domain mapping is stable: 事业->career, 健康->health, 婚姻->relationship,
   子女->family, 财运->wealth, and unmapped categories (e.g. 外貌) fall back to unknown.
3. include_astro=True fills chart_input from fortune_api_results[case_id]['bazi'];
   include_astro=False keeps chart_input absent.
4. Missing chart entries in fortune_api_results are tolerated (row still produced,
   chart_input either absent or empty dict), never raise.
5. year_filter=YYYY restricts rows to the matching year (str compare, since the
   upstream data.json uses string year like "2025").
6. category_filter=[...] restricts rows to the requested chinese category names.
7. Rejects fortune_api_json_path=None when include_astro=True (fail fast, not
   silently missing chart_input).
"""

from __future__ import annotations

from pathlib import Path

import pytest


DATA_FIXTURE = Path("tests/fixtures/mingli/data_sample.json")
FORTUNE_FIXTURE = Path("tests/fixtures/mingli/fortune_api_results_sample.json")


try:
    from benchmark.runners.mingli_bench_adapter import load_and_normalize
except ImportError:
    load_and_normalize = None


def _require_impl():
    if load_and_normalize is None:
        pytest.fail(
            "benchmark.runners.mingli_bench_adapter is not implemented yet; "
            "see docs/superpowers/plans/2026-07-01-phase1-evaluation-infra.md Task 3.2"
        )


def test_load_and_normalize_exposes_expected_columns():
    _require_impl()
    rows = load_and_normalize(str(DATA_FIXTURE))

    assert len(rows) == 6
    row = rows[0]
    for key in ("case_id", "question", "options", "answer", "domain", "year", "category"):
        assert key in row, f"missing key {key} in row"
    assert row["case_id"] == "mingli_fixture_c001_q1"
    assert row["answer"] == "A"
    assert row["options"][0].startswith("A. ")


def test_load_and_normalize_maps_categories_to_domains():
    _require_impl()
    rows = load_and_normalize(str(DATA_FIXTURE))
    by_id = {r["case_id"]: r for r in rows}

    assert by_id["mingli_fixture_c001_q1"]["domain"] == "career"
    assert by_id["mingli_fixture_c002_q1"]["domain"] == "health"
    assert by_id["mingli_fixture_c003_q1"]["domain"] == "relationship"
    assert by_id["mingli_fixture_c004_q1"]["domain"] == "family"
    assert by_id["mingli_fixture_c005_q1"]["domain"] == "wealth"
    assert by_id["mingli_fixture_c006_q1"]["domain"] == "unknown"


def test_load_and_normalize_include_astro_injects_chart_input():
    _require_impl()
    rows = load_and_normalize(
        str(DATA_FIXTURE),
        fortune_api_json_path=str(FORTUNE_FIXTURE),
        include_astro=True,
    )
    by_id = {r["case_id"]: r for r in rows}

    chart = by_id["mingli_fixture_c001_q1"]["chart_input"]
    assert chart["four_pillars"]["day"]["gan"] == "丁"
    assert chart["day_master"]["wuxing"] == "火"


def test_load_and_normalize_without_astro_omits_chart_input():
    _require_impl()
    rows = load_and_normalize(str(DATA_FIXTURE))

    for row in rows:
        assert "chart_input" not in row


def test_load_and_normalize_tolerates_missing_chart_entries():
    _require_impl()
    rows = load_and_normalize(
        str(DATA_FIXTURE),
        fortune_api_json_path=str(FORTUNE_FIXTURE),
        include_astro=True,
    )
    by_id = {r["case_id"]: r for r in rows}

    row_no_chart = by_id["mingli_fixture_c005_q1"]
    assert row_no_chart.get("chart_input") in (None, {})


def test_load_and_normalize_year_filter():
    _require_impl()
    rows = load_and_normalize(str(DATA_FIXTURE), year_filter="2024")
    years = {r["year"] for r in rows}
    assert years == {"2024"}


def test_load_and_normalize_category_filter():
    _require_impl()
    rows = load_and_normalize(str(DATA_FIXTURE), category_filter=["健康", "婚姻"])
    categories = {r["category"] for r in rows}
    assert categories == {"健康", "婚姻"}


def test_load_and_normalize_rejects_missing_fortune_when_astro_requested():
    _require_impl()
    with pytest.raises(ValueError):
        load_and_normalize(str(DATA_FIXTURE), include_astro=True)


def test_load_and_normalize_prefixes_bare_case_ids(tmp_path):
    _require_impl()
    bare = tmp_path / "bare.json"
    bare.write_text(
        '[{"case_id": "q1_2025_001", "year": "2025", "category": "\u4e8b\u4e1a",'
        ' "question": "?", "options": ["A. a", "B. b", "C. c", "D. d"], "answer": "A"}]',
        encoding="utf-8",
    )
    rows = load_and_normalize(str(bare))
    assert rows[0]["case_id"] == "mingli_q1_2025_001"


def test_load_and_normalize_preserves_existing_mingli_prefix():
    _require_impl()
    rows = load_and_normalize(str(DATA_FIXTURE))
    for row in rows:
        assert row["case_id"].startswith("mingli_")
        assert not row["case_id"].startswith("mingli_mingli_")


def test_load_and_normalize_supports_official_questions_payload(tmp_path):
    _require_impl()
    data = tmp_path / "data.json"
    fortune = tmp_path / "fortune_api_results.json"
    data.write_text(
        '{"questions":[{"case_id":"case_121","question_number":121,"category":"家庭",'
        '"question":"?","options":[{"letter":"A","text":"a"},{"letter":"B","text":"b"},'
        '{"letter":"C","text":"c"},{"letter":"D","text":"d"}],"answer":"B"}]}',
        encoding="utf-8",
    )
    fortune.write_text(
        '[{"case_id":"case_121","api_response":{"data":{"data":{"chineseDate":"x",'
        '"palaces":[{"name":"命宫"}]}}}}]',
        encoding="utf-8",
    )

    rows = load_and_normalize(
        str(data),
        fortune_api_json_path=str(fortune),
        include_astro=True,
        year_filter="2025",
    )

    assert len(rows) == 1
    assert rows[0]["case_id"] == "mingli_case_121"
    assert rows[0]["year"] == "2025"
    assert rows[0]["domain"] == "family"
    assert rows[0]["options"] == ["A. a", "B. b", "C. c", "D. d"]
    assert rows[0]["chart_input"]["chineseDate"] == "x"
