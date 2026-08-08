from bazi_features import extract

CHART_1990 = {
    "four_pillars": {
        "year": {"gan": "庚", "zhi": "午"},
        "month": {"gan": "辛", "zhi": "巳"},
        "day": {"gan": "丁", "zhi": "丑"},
        "hour": {"gan": "甲", "zhi": "辰"},
    },
    "day_master": {"gan": "丁", "wuxing": "火", "yinyang": "阴"},
    "birth_info": {
        "year": 1990,
        "month": 5,
        "day": 12,
        "hour": 8,
        "minute": 30,
        "gender": "female",
        "location": "北京",
    },
}


def test_extract_returns_text_blob_and_structured_keys():
    out = extract(CHART_1990)
    assert "text_blob" in out
    assert "structured" in out
    s = out["structured"]
    for key in ("day_master_gan", "day_master_wuxing", "month_zhi", "gender", "birth_decade", "year_zhi"):
        assert key in s


def test_text_blob_contains_day_master_and_month_branch():
    out = extract(CHART_1990)
    blob = out["text_blob"]
    assert "丁" in blob
    assert "巳" in blob
    assert len(blob) <= 600


def test_structured_birth_decade_bucketed():
    out = extract(CHART_1990)
    assert out["structured"]["birth_decade"] == 1990


def test_handles_missing_fields_gracefully():
    out = extract({"four_pillars": {}, "day_master": None, "birth_info": {}})
    assert out["structured"]["day_master_gan"] == ""
    assert out["structured"]["birth_decade"] is None
    assert isinstance(out["text_blob"], str)


def test_extract_includes_branch_set_and_query_domain():
    chart = {**CHART_1990, "query_domain": "relationship"}

    out = extract(chart)
    s = out["structured"]

    assert s["query_domain"] == "relationship"
    assert s["branches"] == ["午", "巳", "丑", "辰"]
    assert "感情" in out["text_blob"] or "relationship" in out["text_blob"]


def test_extract_includes_query_text_for_retrieval_intent():
    chart = {**CHART_1990, "query_domain": "wealth", "query_text": "命主是否投资致富 A 投资致富 B 普通收入"}

    out = extract(chart)

    assert out["structured"]["query_text"] == "命主是否投资致富 A 投资致富 B 普通收入"
    assert "投资致富" in out["text_blob"]


def test_extract_includes_wuxing_and_shishen_stats():
    features = extract({
        "four_pillars": {
            "year": {"gan": "庚", "zhi": "午"},
            "month": {"gan": "辛", "zhi": "巳"},
            "day": {"gan": "甲", "zhi": "子"},
            "hour": {"gan": "戊", "zhi": "辰"},
        },
        "day_master": {"gan": "甲", "wuxing": "木"},
        "birth_info": {"gender": "female", "year": 1990},
        "wuxing_stats": {"木": 2, "火": 2, "土": 2, "金": 1, "水": 1},
        "shishen_stats": {"正官": 1},
    })
    structured = features["structured"]
    assert structured["wuxing_stats"]["木"] == 2
    assert structured["shishen_stats"]["正官"] == 1
