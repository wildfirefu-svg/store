import json

from scripts.export_report_quality_samples import build_row


def test_build_row_creates_quality_gate_shape():
    chart = {"four_pillars": {"day": {"gan": "甲", "zhi": "子"}}, "day_master": {"gan": "甲", "wuxing": "木"}}
    row = build_row("case1", chart, "报告正文")
    assert row == {"case_id": "case1", "chart": chart, "report_text": "报告正文"}
