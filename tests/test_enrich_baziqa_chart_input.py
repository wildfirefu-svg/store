
from scripts.enrich_baziqa_chart_input import enrich_row, summarize_rows


def test_enrich_row_adds_chart_input(monkeypatch):
    def fake_compute_chart(year, month, day, hour, minute, gender, location):
        return {
            "four_pillars": {
                "year": {"gan": "庚", "zhi": "午"},
                "month": {"gan": "辛", "zhi": "巳"},
                "day": {"gan": "甲", "zhi": "子"},
                "hour": {"gan": "戊", "zhi": "辰"},
            },
            "day_master": {"gan": "甲", "wuxing": "木"},
            "birth_info": {"year": year, "month": month, "day": day, "hour": hour, "minute": minute, "gender": gender},
            "wuxing_stats": {"木": 2, "火": 2, "土": 2, "金": 1, "水": 1},
            "shishen_stats": {"正官": 1},
        }

    row = {
        "case_id": "c1",
        "person": {
            "gender": "female",
            "birth": {"year": 1990, "month": 5, "day": 12, "hour": 8, "minute": 30, "place": "Beijing"},
        },
    }
    enriched = enrich_row(row, compute_chart_fn=fake_compute_chart)
    assert enriched["chart_input"]["four_pillars"]["day"]["gan"] == "甲"
    assert enriched["chart_input"]["birth_info"]["gender"] == "female"


def test_summarize_rows_counts_chart_input():
    rows = [{"chart_input": {"four_pillars": {}}}, {"person": {}}]
    summary = summarize_rows(rows)
    assert summary == {"total": 2, "with_chart_input": 1, "coverage": 0.5}
