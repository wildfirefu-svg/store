from collections import Counter


def _jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def score_stability(runs):
    if not runs:
        return {
            "n_runs": 0,
            "answer_consistency": 0.0,
            "evidence_consistency": 0.0,
            "stability_score": 0.0,
            "dominant_answer": None,
            "dominant_count": 0,
        }

    if len(runs) == 1:
        return {
            "n_runs": 1,
            "answer_consistency": 1.0,
            "evidence_consistency": 1.0,
            "stability_score": 1.0,
            "dominant_answer": runs[0].get("answer"),
            "dominant_count": 1,
        }

    answers = [r.get("answer") for r in runs]
    answer_counter = Counter(answers)
    dominant_answer, dominant_count = answer_counter.most_common(1)[0]
    answer_consistency = dominant_count / len(runs)

    if dominant_count == 1 and len(answer_counter) == len(runs):
        answer_consistency = 0.0

    evidence_lists = []
    for r in runs:
        ev = r.get("evidence") or []
        if isinstance(ev, str):
            ev = [ev]
        evidence_lists.append(set(ev))

    pairs = []
    for i in range(len(evidence_lists)):
        for j in range(i + 1, len(evidence_lists)):
            pairs.append(_jaccard(evidence_lists[i], evidence_lists[j]))

    evidence_consistency = sum(pairs) / len(pairs) if pairs else 0.0

    stability_score = 0.6 * answer_consistency + 0.4 * evidence_consistency

    return {
        "n_runs": len(runs),
        "answer_consistency": answer_consistency,
        "evidence_consistency": evidence_consistency,
        "stability_score": stability_score,
        "dominant_answer": dominant_answer,
        "dominant_count": dominant_count,
    }
