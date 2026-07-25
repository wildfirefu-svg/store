import json
import re


def load_jsonl(path):
    items = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _legacy_extract_choice(text):
    if text is None:
        return None
    s = str(text).strip()
    if re.fullmatch(r'[A-Da-d]', s):
        return s.upper()
    patterns = [
        r'答案\s*[:：]?\s*([A-Da-d])',
        r'选择\s*([A-Da-d])',
        r'我选\s*([A-Da-d])',
        r'选项\s*([A-Da-d])',
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return m.group(1).upper()
    return None


def _extract_final_answer_choice(s):
    matches = re.findall(r'最终答案\s*[:：]?\s*([A-Da-d])', s)
    if not matches:
        return None
    return matches[-1].upper()


def _extract_confidence_choice(s):
    scores = {}
    for choice, score in re.findall(r'(?m)^\s*([A-Da-d])\s*[:：]\s*([0-9]{1,3})(?:\s*/\s*100)?\s*$', s):
        value = int(score)
        if 0 <= value <= 100:
            scores[choice.upper()] = value
    if not scores:
        return None
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ordered[0][0]


def extract_choice_with_meta(text):
    if text is None:
        return {"choice": None, "source": "none", "valid": False}
    s = str(text).strip()
    choice = _extract_final_answer_choice(s)
    if choice:
        return {"choice": choice, "source": "final_answer", "valid": True}
    choice = _extract_confidence_choice(s)
    if choice:
        return {"choice": choice, "source": "confidence", "valid": True}
    choice = _legacy_extract_choice(s)
    if choice:
        return {"choice": choice, "source": "legacy", "valid": True}
    return {"choice": None, "source": "none", "valid": False}


def extract_choice(text):
    return extract_choice_with_meta(text)["choice"]


def _case_id(case):
    return case.get('case_id') or case.get('id') or case.get('question_id')


def _empty_bucket():
    return {'total': 0, 'correct': 0, 'missing': 0, 'accuracy': 0.0}


def _empty_domain_bucket():
    return _empty_bucket()


def score_choice_answers(cases, predictions):
    total = 0
    correct = 0
    missing = []
    invalid_cases = []
    by_domain = {}
    by_year = {}
    for case in cases:
        cid = _case_id(case)
        expected = extract_choice(case.get('answer'))
        if expected is None:
            invalid_cases.append(cid)
            continue
        domain = case.get('domain') or 'unknown'
        year = str(case.get('source_year') or 'unknown')
        bucket = by_domain.setdefault(domain, _empty_bucket())
        year_bucket = by_year.setdefault(year, _empty_bucket())
        total += 1
        bucket['total'] += 1
        year_bucket['total'] += 1
        predicted = extract_choice(predictions.get(cid))
        if predicted is None:
            missing.append(cid)
            bucket['missing'] += 1
            year_bucket['missing'] += 1
            continue
        if predicted == expected:
            correct += 1
            bucket['correct'] += 1
            year_bucket['correct'] += 1
    for bucket in list(by_domain.values()) + list(by_year.values()):
        bucket['accuracy'] = bucket['correct'] / bucket['total'] if bucket['total'] else 0.0
    return {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total else 0.0,
        'by_domain': by_domain,
        'by_year': by_year,
        'missing': missing,
        'invalid_cases': invalid_cases,
    }
