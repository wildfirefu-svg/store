from scripts.reclassify_corpus_domain import infer_domain, reclassify_rows


def _row(domain, question="", options=None):
    return {
        "domain": domain,
        "question": question,
        "options": list(options or []),
    }


def test_infer_domain_family_only():
    row = _row("unknown", "何时可婚?", ["A 娶妻", "B 生子", "C 早", "D 晚"])
    assert infer_domain(row) == "family"


def test_infer_domain_health_only():
    row = _row("unknown", "何时患病?", ["A 心脏", "B 肝", "C 中风", "D 高血压"])
    assert infer_domain(row) == "health"


def test_infer_domain_relationship_only():
    row = _row("unknown", "何时分手?", ["A 恋爱", "B 出轨", "C 桃花", "D 分手"])
    assert infer_domain(row) == "relationship"


def test_infer_domain_multiple_hits_returns_none():
    row = _row("unknown", "何时结婚?", ["A 出轨", "B 生子", "C 早", "D 晚"])
    assert infer_domain(row) is None


def test_infer_domain_no_hit_returns_none():
    row = _row("unknown", "命主属于?", ["A 火", "B 木", "C 水", "D 金"])
    assert infer_domain(row) is None


def test_reclassify_only_touches_unknown():
    rows = [
        _row("career", "何时升职?", ["A 婚", "B 家", "C 早", "D 晚"]),
        _row("unknown", "何时患病?", ["A 心脏", "B 肝", "C 中风", "D 高血压"]),
        _row("unknown", "命主属于?", ["A 火", "B 木", "C 水", "D 金"]),
    ]
    updated, transitions = reclassify_rows(rows)

    assert updated[0]["domain"] == "career"
    assert updated[1]["domain"] == "health"
    assert updated[2]["domain"] == "unknown"
    assert transitions[("career", "career")] == 1
    assert transitions[("unknown", "health")] == 1
    assert transitions[("unknown", "unknown")] == 1


def test_reclassify_preserves_other_fields():
    rows = [
        {
            "domain": "unknown",
            "question": "何时患病?",
            "options": ["A 心脏", "B 肝", "C 中风", "D 高血压"],
            "case_id": "abc",
            "answer": "A",
        }
    ]
    updated, _ = reclassify_rows(rows)
    assert updated[0]["case_id"] == "abc"
    assert updated[0]["answer"] == "A"
    assert updated[0]["domain"] == "health"
