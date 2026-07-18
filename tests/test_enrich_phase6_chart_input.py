from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.enrich_phase6_chart_input as enrich6


def fake_chart(year, month, day, hour, minute, gender, place) -> dict:
    """满足批准字段 presence 的最小合成 chart_input。"""
    pillar = {
        "gan": "甲", "zhi": "子", "gan_wuxing": "木", "zhi_wuxing": "水",
        "shi_shen_gan": "比肩", "shi_shen_zhi_main": "正印",
        "cang_gan": ["癸"], "cang_gan_shi_shen": ["正印"],
        "nayin": "海中金", "kong_wang": "占位",
    }
    return {
        "four_pillars": {k: dict(pillar) for k in ("year", "month", "day", "hour")},
        "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳", "shier_changsheng": "沐浴"},
        "nayin_wuxing": {k: "海中金" for k in ("year", "month", "day", "hour")},
        "wuxing_stats": {"jin": 1, "mu": 2, "shui": 1, "huo": 2, "tu": 2,
                         "missing": [], "strongest": "木", "weakest": "金"},
        "shishen_stats": {"counts": {"比肩": 2}, "missing": [], "missing_human": ""},
        "branch_relations": [],
        "shensha": [{"name": "天乙贵人", "position": "年干", "meaning": "主贵人扶助"}],
        "da_yun": [{"index": 1, "gan": "丙", "zhi": "寅", "start_age": 3, "end_age": 12,
                    "shi_shen_gan": "食神", "shi_shen_zhi": "比肩", "is_current": False}],
        "tai_yuan": {"gan": "乙", "zhi": "卯", "nayin": "大溪水"},
        "ming_gong": {"gan": "丙", "zhi": "辰", "nayin": "沙中土"},
        "shen_gong": {"gan": "丁", "zhi": "巳", "nayin": "沙中土"},
        "true_solar_info": {"original_time": "1990-01-02 03:00", "adjusted_time": "1990-01-02 02:48",
                            "adjustment_minutes": -12, "method": "经度修正", "location_matched": True},
        "liu_nian": [{"year": 2099, "gan_zhi": "SENTINEL"}],  # 计算器固有输出，denylist 不读
    }


def make_row(case_id: str) -> dict:
    return {
        "case_id": case_id, "answer": "B", "domain": "wealth",
        "question": "q", "options": ["A 甲", "B 乙", "C 丙", "D 丁"], "source_year": "2021",
        "person": {"person_id": f"p_{case_id}", "name": "某", "gender": "male",
                   "birth": {"year": 1990, "month": 1, "day": 2, "hour": 3, "minute": 0, "place": "北京"}},
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    src = tmp_path / "benchmark" / "datasets"
    src.mkdir(parents=True)
    for year in (2021, 2022, 2023):
        rows = [make_row(f"{year}_c{i}") for i in range(2)]
        (src / f"baziqa_contest8_{year}_holdout.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    monkeypatch.setattr(enrich6, "compute_chart", fake_chart)
    return tmp_path


def run_main(env_tmp, argv):
    out_dir = env_tmp / "out"
    manifest = env_tmp / "manifest.json"
    # 偏离计划登记：补 --root 使测试真正读 tmp fixture（计划缺此参数会读真实 40 题数据集）
    return enrich6.main([*argv, "--out-dir", str(out_dir), "--manifest", str(manifest),
                         "--root", str(env_tmp)]), out_dir, manifest


def test_enrich_years_and_manifest(env):
    code, out_dir, manifest = run_main(env, ["--years", "2021", "2022", "--as-of-date", "2026-07-17"])
    assert code == 0
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["as_of_date"] == "2026-07-17"
    assert m["includes_sealed_2023"] is False
    assert [e["year"] for e in m["entries"]] == [2021, 2022]
    for entry in m["entries"]:
        assert len(entry["source_sha256"]) == 64
        assert len(entry["output_sha256"]) == 64
        assert all(v.endswith("/2") and v.startswith("2/") for v in entry["approved_coverage"].values())
    rows = [json.loads(x) for x in (out_dir / "baziqa_contest8_2021_holdout_enriched.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert all(r.get("chart_input") for r in rows)


def test_2023_rejected_by_default(env):
    with pytest.raises(SystemExit):
        run_main(env, ["--years", "2023", "--as-of-date", "2026-07-17"])


def test_include_2023_flag(env):
    code, _, manifest = run_main(
        env, ["--years", "2021", "--include-2023", "--as-of-date", "2026-07-17"]
    )
    assert code == 0
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["includes_sealed_2023"] is True
    assert 2023 in [e["year"] for e in m["entries"]]


def test_coverage_shortfall_fails_closed(env, monkeypatch):
    def broken_chart(*a, **kw):
        chart = fake_chart(*a, **kw)
        del chart["da_yun"]
        return chart
    monkeypatch.setattr(enrich6, "compute_chart", broken_chart)
    with pytest.raises(SystemExit, match="批准字段覆盖率未达 100%"):
        run_main(env, ["--years", "2021", "--as-of-date", "2026-07-17"])


def test_strip_denylisted():
    obj = {"a": {"kong_wang": 1, "b": [{"liu_nian": 2, "c": 3}]}}
    assert enrich6.strip_denylisted(obj) == {"a": {"b": [{"c": 3}]}}
