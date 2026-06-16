import re


def score_evidence_coverage(expected, provided):
    expected = expected or []
    provided = provided or []

    if isinstance(provided, str):
        provided = [provided]

    if not expected:
        return {
            "coverage": 1.0,
            "matched": [],
            "missing": [],
            "extra": list(provided),
        }

    matched = []
    missing = []
    provided_lower = [str(p).lower() for p in provided]

    for ev in expected:
        found = False
        ev_lower = str(ev).lower()
        for p in provided_lower:
            if ev_lower in p or re.search(re.escape(ev_lower), p):
                found = True
                break
        if found:
            matched.append(ev)
        else:
            missing.append(ev)

    provided_set = set(provided)
    expected_set = set(expected)
    extra = list(provided_set - expected_set)

    coverage = len(matched) / len(expected) if expected else 1.0

    return {
        "coverage": coverage,
        "matched": matched,
        "missing": missing,
        "extra": extra,
    }


def score_case_evidence(case, model_output_text):
    expected_evidence = case.get('expected_evidence') or []
    if isinstance(expected_evidence, str):
        import json
        try:
            expected_evidence = json.loads(expected_evidence)
        except Exception:
            expected_evidence = [expected_evidence]

    provided = []
    if model_output_text:
        sentences = re.split(r'[。！？；\n]', str(model_output_text))
        for sent in sentences:
            sent = sent.strip()
            if sent:
                provided.append(sent)

    return score_evidence_coverage(expected_evidence, provided)


def aggregate_evidence_score(scores):
    if not scores:
        return 0.0
    total = sum(s.get('coverage', 0.0) for s in scores)
    return total / len(scores)
