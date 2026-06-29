import json
from pathlib import Path

import pytest

from case_index import CaseIndex


def _make_corpus(tmp_path: Path, rows):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "tiny_corpus.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def _row(person_id, year, gender, day, q_idx, answer="A", options=None, question="命主财运?", domain="wealth"):
    return {
        "case_id": f"{person_id}-Q{q_idx}",
        "answer": answer,
        "options": options or ["A 富裕", "B 贫穷", "C 普通", "D 早夭"],
        "question": question,
        "domain": domain,
        "person": {
            "person_id": person_id,
            "name": f"{year}年出生{'男性' if gender == 'male' else '女性'}",
            "gender": gender,
            "birth": {"year": year, "month": 1, "day": day, "hour": 8, "minute": 0, "place": "中国"},
        },
        "verified_events": {},
        "source_year": str(year),
    }


def test_rejects_holdout_corpus_path(tmp_path):
    holdout = tmp_path / "baziqa_holdout.jsonl"
    holdout.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        CaseIndex(holdout)


def test_top_k_returns_at_most_k_unique_cases(tmp_path):
    rows = []
    for i in range(5):
        for q in range(2):
            rows.append(_row(f"P{i:02d}", 1970 + i, "male", 1, q))
    corpus = _make_corpus(tmp_path, rows)

    idx = CaseIndex(corpus)
    features = {"text_blob": "日主丁火，生于午月", "structured": {"day_master_gan": "丁", "gender": "male", "birth_decade": 1970}}
    cases = idx.top_k_cases(features, k=3)

    assert 0 < len(cases) <= 3
    person_ids = [c["person_id"] for c in cases]
    assert len(person_ids) == len(set(person_ids))


def test_filter_by_day_master_when_set(tmp_path):
    rows = [_row("PA", 1970, "male", 1, 0), _row("PB", 1980, "female", 2, 0)]
    corpus = _make_corpus(tmp_path, rows)
    idx = CaseIndex(corpus)

    features = {"text_blob": "丁火", "structured": {"day_master_gan": "丁", "gender": "female", "birth_decade": 1980}}
    cases = idx.top_k_cases(features, k=5, filters={"gender": "female"})

    assert all(c["gender"] == "female" for c in cases)


def test_falls_back_to_keyword_when_embed_fn_raises(tmp_path):
    corpus = _make_corpus(tmp_path, [_row("PA", 1970, "male", 1, 0)])

    def boom(_text):
        raise RuntimeError("embed unavailable")

    idx = CaseIndex(corpus, embed_fn=boom)
    cases = idx.top_k_cases({"text_blob": "丁火午月", "structured": {}}, k=3)
    assert len(cases) >= 1


def test_domain_match_boosts_retrieved_cases(tmp_path):
    rows = [
        _row("career-case", 1980, "female", 1, 0, question="命主事业?", domain="career"),
        _row("relationship-case", 1980, "female", 1, 0, question="命主婚姻?", domain="relationship"),
    ]
    corpus = _make_corpus(tmp_path, rows)
    idx = CaseIndex(corpus)

    cases = idx.top_k_cases({
        "text_blob": "丁火 巳月 感情",
        "structured": {
            "gender": "female",
            "birth_decade": 1980,
            "day_master_gan": "丁",
            "query_domain": "relationship",
            "branches": ["巳", "午", "丑", "辰"],
        },
    }, k=1)

    assert cases[0]["person_id"] == "relationship-case"


def test_intent_overlap_boosts_same_domain_keyword_case(tmp_path):
    rows = [
        _row("wealth-invest", 1980, "male", 1, 0, answer="A", options=["A 投资致富", "B 平稳", "C 疾病", "D 婚变"], question="命主是否投资致富?", domain="wealth"),
        _row("wealth-generic", 1980, "male", 1, 0, answer="A", options=["A 普通收入", "B 平稳", "C 疾病", "D 婚变"], question="命主财运普通?", domain="wealth"),
    ]
    corpus = _make_corpus(tmp_path, rows)
    idx = CaseIndex(corpus)

    cases = idx.top_k_cases({
        "text_blob": "问题领域财运，题目选项命主是否投资致富 A 投资致富 B 普通收入",
        "structured": {
            "gender": "male",
            "birth_decade": 1980,
            "query_domain": "wealth",
            "query_text": "命主是否投资致富 A 投资致富 B 普通收入",
        },
    }, k=1)

    assert cases[0]["person_id"] == "wealth-invest"
    assert any(str(r).startswith("intent_overlap") for r in cases[0]["match_reasons"])
    assert cases[0]["_score"] > 0


def test_semantic_phrase_overlap_boosts_case(tmp_path):
    rows = [
        _row("wealth-swing", 1980, "male", 1, 0, answer="A", options=["A 财源广但暴起暴跌", "B 普通收入", "C 健康差", "D 婚姻稳"], question="命主财运特点?", domain="wealth"),
        _row("wealth-stable", 1980, "male", 1, 0, answer="A", options=["A 稳定打工收入", "B 普通收入", "C 健康差", "D 婚姻稳"], question="命主财运特点?", domain="wealth"),
    ]
    corpus = _make_corpus(tmp_path, rows)
    idx = CaseIndex(corpus)

    cases = idx.top_k_cases({
        "text_blob": "问题领域财运，题目选项命主财源广但暴起暴跌 A 财源广但暴起暴跌 B 稳定打工收入",
        "structured": {
            "gender": "male",
            "birth_decade": 1980,
            "query_domain": "wealth",
            "query_text": "命主财源广但暴起暴跌 A 财源广但暴起暴跌 B 稳定打工收入",
        },
    }, k=1)

    assert cases[0]["person_id"] == "wealth-swing"
    assert any(str(r).startswith("semantic_overlap") for r in cases[0]["match_reasons"])


def test_semantic_overlap_filters_generic_phrases(tmp_path):
    rows = [_row("generic", 1980, "male", 1, 0, question="此命出生家境如何？", domain="unknown")]
    corpus = _make_corpus(tmp_path, rows)
    idx = CaseIndex(corpus)

    cases = idx.top_k_cases({
        "text_blob": "此命出生家境如何？",
        "structured": {"query_domain": "unknown", "query_text": "此命出生家境如何？"},
    }, k=1)

    semantic_reasons = [r for r in cases[0]["match_reasons"] if str(r).startswith("semantic_overlap")]
    assert not semantic_reasons or "出生" not in semantic_reasons[0]
    assert not semantic_reasons or "如何" not in semantic_reasons[0]


def test_tie_break_is_stable_across_corpus_order(tmp_path):
    rows_a = [
        _row("PB", 1980, "male", 1, 0, question="命主综合?", domain="unknown"),
        _row("PA", 1980, "male", 1, 0, question="命主综合?", domain="unknown"),
        _row("PC", 1980, "male", 1, 0, question="命主综合?", domain="unknown"),
    ]
    rows_b = list(reversed(rows_a))
    corpus_a = _make_corpus(tmp_path / "a", rows_a)
    corpus_b = _make_corpus(tmp_path / "b", rows_b)
    features = {"text_blob": "", "structured": {}}

    ids_a = [c["person_id"] for c in CaseIndex(corpus_a).top_k_cases(features, k=3)]
    ids_b = [c["person_id"] for c in CaseIndex(corpus_b).top_k_cases(features, k=3)]

    assert ids_a == ["PA", "PB", "PC"]
    assert ids_b == ["PA", "PB", "PC"]


def test_semantic_overlap_can_be_disabled(monkeypatch, tmp_path):
    import json as _json
    path = tmp_path / "corpus.jsonl"
    path.write_text(
        "\n".join([
            _json.dumps({"case_id":"c1","answer":"A","domain":"career","person":{"person_id":"p1","name":"甲","gender":"male","birth":{"year":1980}},"question":"事业升迁","options":["A. 升迁","B. 婚姻"]}, ensure_ascii=False),
            _json.dumps({"case_id":"c2","answer":"A","domain":"career","person":{"person_id":"p2","name":"乙","gender":"male","birth":{"year":1980}},"question":"健康疾病","options":["A. 疾病","B. 升迁"]}, ensure_ascii=False),
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("BAZI_RAG_SEMANTIC", "0")
    from case_index import CaseIndex
    idx = CaseIndex(path)
    result = idx.top_k_cases({"text_blob": "事业升迁", "structured": {"query_text": "事业升迁"}}, k=2)
    assert all(not any(r.startswith("semantic_overlap:") for r in item.get("match_reasons", [])) for item in result)


def test_structured_weight_changes_score(monkeypatch, tmp_path):
    import json as _json
    path = tmp_path / "corpus.jsonl"
    path.write_text(
        _json.dumps({"case_id":"c1","answer":"A","domain":"career","person":{"person_id":"p1","name":"甲","gender":"male","birth":{"year":1980}},"question":"事业","options":["A. 升迁","B. 婚姻"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    from case_index import CaseIndex
    monkeypatch.setenv("BAZI_RAG_STRUCTURED_WEIGHT", "0")
    idx1 = CaseIndex(path)
    score_low = idx1.top_k_cases({"text_blob": "事业", "structured": {"query_domain": "career"}}, k=1)[0]["_score"]
    monkeypatch.setenv("BAZI_RAG_STRUCTURED_WEIGHT", "1")
    idx2 = CaseIndex(path)
    score_high = idx2.top_k_cases({"text_blob": "事业", "structured": {"query_domain": "career"}}, k=1)[0]["_score"]
    assert score_high > score_low


def test_chart_structure_boosts_same_day_master_and_month_branch(tmp_path):
    import json as _json
    path = tmp_path / "corpus.jsonl"
    rows = [
        {
            "case_id": "same",
            "answer": "A",
            "domain": "career",
            "person": {"person_id": "p1", "name": "同盘", "gender": "male", "birth": {"year": 1980}},
            "question": "事业",
            "options": ["A. 升迁", "B. 婚姻"],
            "chart_input": {
                "four_pillars": {"month": {"zhi": "巳"}, "day": {"gan": "甲", "zhi": "子"}},
                "day_master": {"gan": "甲", "wuxing": "木"},
                "wuxing_stats": {"木": 2, "火": 2},
                "shishen_stats": {"正官": 1},
            },
        },
        {
            "case_id": "diff",
            "answer": "A",
            "domain": "career",
            "person": {"person_id": "p2", "name": "异盘", "gender": "male", "birth": {"year": 1980}},
            "question": "事业",
            "options": ["A. 升迁", "B. 婚姻"],
            "chart_input": {
                "four_pillars": {"month": {"zhi": "亥"}, "day": {"gan": "庚", "zhi": "午"}},
                "day_master": {"gan": "庚", "wuxing": "金"},
                "wuxing_stats": {"金": 3, "水": 2},
                "shishen_stats": {"七杀": 1},
            },
        },
    ]
    path.write_text("\n".join(_json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    from case_index import CaseIndex
    idx = CaseIndex(path)
    result = idx.top_k_cases({
        "text_blob": "事业",
        "structured": {
            "query_domain": "career",
            "day_master_gan": "甲",
            "month_zhi": "巳",
            "wuxing_stats": {"木": 2, "火": 2},
            "shishen_stats": {"正官": 1},
        },
    }, k=2)
    assert result[0]["person_id"] == "p1"
    assert "same_day_master" in result[0]["match_reasons"]
    assert "same_month_branch" in result[0]["match_reasons"]


def test_option_evidence_returns_per_option_buckets(tmp_path):
    rows = [
        _row("career-case", 1980, "male", 1, 0, answer="A", options=["A 升迁", "B 婚姻", "C 疾病", "D 财运"], question="命主事业是否升迁?", domain="career"),
        _row("relationship-case", 1982, "female", 2, 0, answer="B", options=["A 升迁", "B 婚姻稳定", "C 疾病", "D 财运"], question="命主婚姻是否稳定?", domain="relationship"),
    ]
    corpus = _make_corpus(tmp_path, rows)
    idx = CaseIndex(corpus)

    evidence = idx.option_evidence(
        {"text_blob": "事业 升迁 甲木", "structured": {"query_domain": "career", "day_master_gan": "甲"}},
        question="命主事业是否升迁?",
        options=["A 升迁", "B 婚姻", "C 疾病", "D 财运"],
        domain="career",
        k_per_option=2,
    )

    assert set(evidence) == {"A", "B", "C", "D"}
    assert all(isinstance(items, list) for items in evidence.values())


def test_option_evidence_items_expose_traceable_fields(tmp_path):
    rows = [
        _row("career-case", 1980, "male", 1, 0, answer="A", options=["A 升迁", "B 婚姻", "C 疾病", "D 财运"], question="命主事业是否升迁?", domain="career"),
        _row("wealth-case", 1982, "male", 2, 0, answer="D", options=["A 升迁", "B 婚姻", "C 疾病", "D 财运改善"], question="命主财运是否改善?", domain="wealth"),
    ]
    corpus = _make_corpus(tmp_path, rows)
    idx = CaseIndex(corpus)

    evidence = idx.option_evidence(
        {"text_blob": "事业 升迁 甲木", "structured": {"query_domain": "career", "day_master_gan": "甲"}},
        question="命主事业是否升迁?",
        options=["A 升迁", "B 婚姻", "C 疾病", "D 财运"],
        domain="career",
        k_per_option=1,
    )

    required = {
        "case_id",
        "person_id",
        "score",
        "stance",
        "match_reasons",
        "fact_excerpt",
        "source_domain",
        "source_answer_option_text",
    }
    first_item = evidence["A"][0]
    assert required <= set(first_item)

