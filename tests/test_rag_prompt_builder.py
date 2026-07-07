import json
from pathlib import Path

from case_index import CaseIndex
from rag_prompt_builder import build_system_prompt, load_fewshot_examples


CHART = {
    "four_pillars": {
        "year": {"gan": "庚", "zhi": "午"},
        "month": {"gan": "辛", "zhi": "巳"},
        "day": {"gan": "丁", "zhi": "丑"},
        "hour": {"gan": "甲", "zhi": "辰"},
    },
    "day_master": {"gan": "丁", "wuxing": "火", "yinyang": "阴"},
    "birth_info": {"year": 1990, "month": 5, "day": 12, "hour": 8, "minute": 30, "gender": "female"},
}


def _make_corpus(tmp_path: Path, n=3):
    p = tmp_path / "corpus.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for i in range(n):
            row = {
                "case_id": f"P{i}-Q1",
                "answer": "A",
                "options": ["A 富裕", "B 贫穷", "C 普通", "D 早夭"],
                "question": f"案例{i}财运?",
                "person": {
                    "person_id": f"P{i}",
                    "name": f"测试命主{i}",
                    "gender": "female",
                    "birth": {"year": 1985 + i, "month": 5, "day": 1, "hour": 8, "minute": 0},
                },
                "verified_events": {},
                "source_year": "2022",
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return p


def test_disabled_returns_base_prompt_unchanged(tmp_path):
    corpus = _make_corpus(tmp_path)
    idx = CaseIndex(corpus)
    base = "原始 system prompt"
    out = build_system_prompt(base, CHART, idx, enable_rag=False)
    assert out == base


def test_enabled_injects_top_k_cases_block(tmp_path):
    corpus = _make_corpus(tmp_path)
    idx = CaseIndex(corpus)
    out = build_system_prompt("BASE", CHART, idx, enable_rag=True)
    assert "BASE" in out
    assert "类似命例" in out
    assert "案例" in out


def test_total_length_capped_to_8000_chars(tmp_path):
    corpus = _make_corpus(tmp_path, n=20)
    idx = CaseIndex(corpus)
    base = "x" * 7000
    out = build_system_prompt(base, CHART, idx, enable_rag=True)
    assert len(out) <= 8000


def test_injected_cases_marked_as_reference_only(tmp_path):
    corpus = _make_corpus(tmp_path)
    idx = CaseIndex(corpus)
    out = build_system_prompt("BASE", CHART, idx, enable_rag=True)
    assert "仅供参考" in out or "仅作参考" in out
    assert "非当前命主" in out


def test_injected_cases_include_match_reasons(tmp_path):
    corpus = _make_corpus(tmp_path)
    idx = CaseIndex(corpus)
    chart = {**CHART, "query_domain": "wealth", "query_text": "命主财运 A 富裕 B 贫穷"}
    out = build_system_prompt("BASE", chart, idx, enable_rag=True)
    assert "匹配原因" in out
    assert "检索分" in out


def test_injected_cases_can_include_semantic_overlap_reason(tmp_path):
    rows = []
    for i in range(2):
        rows.append({
            "case_id": f"P{i}-Q1",
            "answer": "A",
            "options": ["A 财源广但暴起暴跌", "B 稳定打工", "C 健康差", "D 婚姻稳"],
            "question": "命主财源特点?",
            "domain": "wealth",
            "person": {
                "person_id": f"P{i}",
                "name": f"测试命主{i}",
                "gender": "female",
                "birth": {"year": 1985 + i, "month": 5, "day": 1, "hour": 8, "minute": 0},
            },
            "verified_events": {},
            "source_year": "2022",
        })
    corpus = tmp_path / "corpus.jsonl"
    with corpus.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    idx = CaseIndex(corpus)
    chart = {**CHART, "query_domain": "wealth", "query_text": "命主财源广但暴起暴跌 A 财源广但暴起暴跌 B 稳定打工"}
    out = build_system_prompt("BASE", chart, idx, enable_rag=True)
    assert "semantic_overlap" in out


def _write_fewshot(tmp_path: Path, n=3) -> Path:
    p = tmp_path / "fewshot.jsonl"
    rows = []
    for i in range(n):
        rows.append({
            "case_id": f"FS{i}-Q1",
            "question": f"示例题{i}：命主财运?",
            "options": ["A 富裕", "B 贫穷", "C 普通", "D 早夭"],
            "answer": "A",
            "domain": "wealth",
            "person": {
                "person_id": f"FS{i}",
                "gender": "male",
                "birth": {"year": 1970 + i, "month": 5, "day": 1, "hour": 8},
            },
        })
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return p


def test_load_fewshot_examples_caps_to_five(tmp_path):
    path = _write_fewshot(tmp_path, n=8)
    rows = load_fewshot_examples(path)
    assert len(rows) == 5


def test_load_fewshot_examples_returns_empty_when_path_missing():
    rows = load_fewshot_examples(None)
    assert rows == []


def test_fewshot_block_injected_when_examples_provided(tmp_path):
    corpus = _make_corpus(tmp_path)
    idx = CaseIndex(corpus)
    fewshot = load_fewshot_examples(_write_fewshot(tmp_path, n=2))
    out = build_system_prompt("BASE", CHART, idx, enable_rag=True, few_shot_examples=fewshot)
    assert "示例题（few-shot）" in out
    assert "标准答案：A" in out
    assert "BASE" in out
    assert "类似命例" in out


def test_fewshot_block_works_without_rag(tmp_path):
    fewshot = load_fewshot_examples(_write_fewshot(tmp_path, n=1))
    out = build_system_prompt("BASE", {}, None, enable_rag=False, few_shot_examples=fewshot)
    assert "示例题（few-shot）" in out
    assert "BASE" in out
    assert "类似命例" not in out


def test_prompt_includes_chart_match_reasons():
    from rag_prompt_builder import _format_case
    case = {
        "name": "同盘",
        "birth_year": 1980,
        "gender": "male",
        "domains": {"career": 1},
        "facts": ["事业 -> 升迁"],
        "_score": 3.2,
        "match_reasons": ["same_day_master", "same_month_branch"],
    }
    text = _format_case(1, case)
    assert "same_day_master" in text
    assert "same_month_branch" in text


class _FakeOptionEvidenceIndex:
    def option_evidence(self, features, question, options, domain=None, k_per_option=2, retrieval_mode=None, exclude_case_id=None):
        return {
            "A": [{"case_id": "ca", "person_id": "pa", "score": 1.2, "stance": "related", "match_reasons": ["option_overlap:升迁"], "fact_excerpt": "事业 -> 升迁", "source_domain": "career", "source_answer_option_text": "A 升迁"}],
            "B": [{"case_id": "cb", "person_id": "pb", "score": 0.8, "stance": "related", "match_reasons": ["option_overlap:婚姻"], "fact_excerpt": "婚姻 -> 稳定", "source_domain": "relationship", "source_answer_option_text": "B 婚姻稳定"}],
            "C": [],
            "D": [],
        }

    def top_k_cases(self, features, k=2):
        return []


def test_option_grounded_prompt_renders_option_evidence_block():
    out = build_system_prompt(
        "BASE",
        {**CHART, "query_domain": "career"},
        _FakeOptionEvidenceIndex(),
        enable_rag=True,
        retrieval_mode="option_grounded",
        question="命主下一阶段哪方面更明显?",
        options=["A 升迁", "B 婚姻", "C 疾病", "D 财运"],
        option_evidence_k=2,
    )

    assert "BASE" in out
    assert "<选项证据>" in out
    assert "A. A 升迁" in out
    assert "B. B 婚姻" in out
    assert "C. C 疾病" in out
    assert "D. D 财运" in out
    assert "option_overlap:升迁" in out
    assert "暂无强证据" in out
    assert "最终答案：X" in out
    assert "<类似命例>" not in out


def test_legacy_rag_prompt_remains_default(tmp_path):
    corpus = _make_corpus(tmp_path)
    idx = CaseIndex(corpus)
    out = build_system_prompt("BASE", CHART, idx, enable_rag=True)

    assert "BASE" in out
    assert "<类似命例>" in out
    assert "<选项证据>" not in out
