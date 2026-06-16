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


def extract_choice(text):
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


def _case_id(case):
    return case.get('case_id') or case.get('id') or case.get('question_id')


def _empty_domain_bucket():
    return {'total': 0, 'correct': 0, 'missing': 0, 'accuracy': 0.0}


def score_choice_answers(cases, predictions):
    total = 0
    correct = 0
    missing = []
    invalid_cases = []
    by_domain = {}
    for case in cases:
        cid = _case_id(case)
        expected = extract_choice(case.get('answer'))
        if expected is None:
            invalid_cases.append(cid)
            continue
        domain = case.get('domain') or 'unknown'
        bucket = by_domain.setdefault(domain, _empty_domain_bucket())
        total += 1
        bucket['total'] += 1
        predicted = extract_choice(predictions.get(cid))
        if predicted is None:
            missing.append(cid)
            bucket['missing'] += 1
            continue
        if predicted == expected:
            correct += 1
            bucket['correct'] += 1
    for bucket in by_domain.values():
        bucket['accuracy'] = bucket['correct'] / bucket['total'] if bucket['total'] else 0.0
    return {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total else 0.0,
        'by_domain': by_domain,
        'missing': missing,
        'invalid_cases': invalid_cases,
    }
