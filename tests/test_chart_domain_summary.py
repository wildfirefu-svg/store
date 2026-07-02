import pytest

from chart_domain_summary import build_domain_summary


SUMMARY_CHART = {
    "four_pillars": {
        "year": {"gan": "庚", "zhi": "午"},
        "month": {"gan": "辛", "zhi": "巳"},
        "day": {
            "gan": "丁",
            "zhi": "丑",
            "cang_gan": ["己", "癸", "辛"],
            "cang_gan_shi_shen": ["食神", "七杀", "偏财"],
        },
        "hour": {"gan": "甲", "zhi": "辰"},
    },
    "day_master": {"gan": "丁", "wuxing": "火", "yinyang": "阴", "shier_changsheng": "墓"},
    "wuxing_stats": {
        "jin": 2,
        "mu": 1,
        "shui": 0,
        "huo": 3,
        "tu": 2,
        "missing": ["水"],
        "strongest": "火",
        "weakest": "水",
    },
    "shishen_stats": {
        "counts": {
            "比肩": 0,
            "劫财": 1,
            "食神": 1,
            "伤官": 0,
            "偏财": 2,
            "正财": 1,
            "正官": 0,
            "七杀": 1,
            "偏印": 0,
            "正印": 0,
        }
    },
    "wuyun_liuqi": {
        "五运": "火运",
        "主事脏腑": "心/小肠",
        "体质倾向": "心脑血管",
        "六气": "厥阴风木",
        "外邪倾向": "风邪",
    },
    "shensha": [
        {"name": "红艳煞", "position": "year_zhi"},
        {"name": "华盖", "position": "month_zhi"},
    ],
    "branch_relations": [{"type": "三刑", "pillars": "month-year", "detail": "巳午刑"}],
}


def test_family_summary_lists_expected_sections():
    out = build_domain_summary(SUMMARY_CHART, "family")

    assert out is not None
    assert "<命主关键项摘要-family>" in out
    assert "配偶星" in out
    assert "父母星(印星)" in out
    assert "子女星(食伤)" in out
    assert "婚姻相关神煞: 红艳煞@year_zhi" in out
    assert "地支关系" in out


def test_health_summary_lists_wuyun_liuqi_and_wuxing_distribution():
    out = build_domain_summary(SUMMARY_CHART, "health")

    assert out is not None
    assert "<命主关键项摘要-health>" in out
    assert "日主=丁火" in out
    assert "五行分布" in out
    assert "五运=火运" in out


def test_relationship_summary_lists_spouse_palace_and_star():
    out = build_domain_summary(SUMMARY_CHART, "relationship")

    assert out is not None
    assert "<命主关键项摘要-relationship>" in out
    assert "配偶宫(日支)=丑" in out
    assert "食伤(子女)" in out


def test_summary_returns_none_for_unsupported_domain():
    assert build_domain_summary(SUMMARY_CHART, "career") is None
    assert build_domain_summary(SUMMARY_CHART, None) is None
    assert build_domain_summary(SUMMARY_CHART, "unknown") is None


def test_summary_returns_none_for_empty_or_missing_chart():
    assert build_domain_summary(None, "family") is None
    assert build_domain_summary({}, "family") is None
    assert build_domain_summary({"four_pillars": None}, "family") is None
