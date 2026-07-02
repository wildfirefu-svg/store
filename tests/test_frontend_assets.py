from pathlib import Path


INDEX = Path("templates/index.html")


def test_index_does_not_depend_on_external_font_or_chart_cdn():
    html = INDEX.read_text(encoding="utf-8")

    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert "cdn.jsdelivr.net" not in html
    assert "/static/vendor/echarts.min.js" in html
    assert "/static/css/fonts.css" in html


def test_local_echarts_bundle_exists_and_looks_like_echarts():
    path = Path("static/vendor/echarts.min.js")

    assert path.exists()
    text = path.read_text(encoding="utf-8", errors="ignore")
    assert "echarts" in text[:5000].lower()
    assert path.stat().st_size > 100_000
