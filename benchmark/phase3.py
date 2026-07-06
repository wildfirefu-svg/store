"""Phase 3 pure helpers: cyclic permutation plan, option-identity aggregation,
and consistency metrics.

These functions do NOT call models or read correct answers. They support the
multi-permutation identity-aggregation design in
``docs/superpowers/specs/2026-07-02-phase3-anti-position-bias-design.md``.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence


def build_permutation_plan(option_ids: Sequence[str], num_perms: int = 3) -> List[Dict[str, Any]]:
    """Build a shared cyclic-shift permutation plan for one case.

    Does NOT read the correct answer. For 4 options and 3 cyclic shifts, each
    original option covers 3 of the 4 label positions, so position bias is
    testable without label-aware preprocessing.

    Returns a list of ``num_perms`` dicts, each with:
      - permutation_id: ``"o2|o3|o4|o1"`` style id from display order
      - display_order: list of option_ids in A/B/C/D display order
      - label_map: {option_id -> label}
      - label_map_inv: {label -> option_id}
      - shift: integer shift amount
    """
    n = len(option_ids)
    if n != 4:
        raise ValueError(f"expected 4 options, got {n}")
    plans: List[Dict[str, Any]] = []
    for shift in range(num_perms):
        display_order = [option_ids[(i + shift) % n] for i in range(n)]
        label_map = {display_order[i]: chr(65 + i) for i in range(n)}
        label_map_inv = {chr(65 + i): display_order[i] for i in range(n)}
        plans.append(
            {
                "permutation_id": "|".join(display_order),
                "display_order": display_order,
                "label_map": label_map,
                "label_map_inv": label_map_inv,
                "shift": shift,
            }
        )
    return plans


def _strip_option_prefix(option_text: str) -> str:
    """Strip 'A. ' / 'B、' style label prefix from an option string."""
    text = str(option_text or "")
    if len(text) >= 2 and text[0].upper() in {"A", "B", "C", "D"} and text[1] in {".", "、", ")", "．"}:
        return text[2:].lstrip()
    return text.lstrip()


def _relabel_option(body: str, label: str) -> str:
    """Prepend label prefix to option body."""
    return f"{label}. {body}"


def permute_case_by_plan(case: Dict[str, Any], shift: int) -> Dict[str, Any]:
    """Apply a fixed cyclic-shift permutation to a case's options.

    Unlike random ``shuffle_options``, this uses a deterministic cyclic shift
    so every arm / mode reuses the same permutation plan.  The returned case
    carries ``answer_label_map``, ``_original_options``, ``_original_answer``,
    and ``_permutation_shift`` so that downstream aggregation can unshuffle
    predicted labels back to original option identities.
    """
    from copy import deepcopy

    original_options: List[str] = list(case.get("options") or [])
    original_answer: str = str(case.get("answer") or "")
    n = len(original_options)

    if n != 4:
        raise ValueError(f"permute_case_by_plan expects 4 options, got {n}")

    # Cyclic shift: original position i → display position (i+shift) % n
    new_order: List[int] = [(i + shift) % n for i in range(n)]

    new_options: List[str] = []
    label_map: Dict[str, str] = {}  # old_label → new_label
    for new_pos, orig_pos in enumerate(new_order):
        new_label = chr(65 + new_pos)  # A/B/C/D
        old_label = chr(65 + orig_pos)
        body = _strip_option_prefix(original_options[orig_pos])
        new_options.append(_relabel_option(body, new_label))
        label_map[old_label] = new_label

    new_answer = label_map.get(original_answer, original_answer)

    result = deepcopy(case)
    result["options"] = new_options
    result["answer"] = new_answer
    result["answer_label_map"] = label_map
    result["_original_options"] = list(original_options)
    result["_original_answer"] = original_answer
    result["_permutation_shift"] = shift
    result["_permutation_id"] = "|".join(
        _strip_option_prefix(original_options[orig_pos])
        for orig_pos in new_order
    )
    return result


def to_original_option_identity(predicted_label: Optional[str], label_map: Dict[str, str]) -> Optional[str]:
    """Map a predicted A/B/C/D label back to the original option identity."""
    if predicted_label is None:
        return None
    inv = {v: k for k, v in label_map.items()}
    return inv.get(predicted_label)


_VALID_LABELS = {"A", "B", "C", "D"}


def normalize_text(text: str) -> str:
    """Normalize text for near-duplicate comparison: lowercase, strip whitespace."""
    return re.sub(r"\s+", "", str(text).lower())


def char_overlap_ratio(a: str, b: str) -> float:
    """Character-level overlap ratio via SequenceMatcher."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def detect_leak_candidates(
    evidence_texts: Sequence[str],
    answer_text: str,
    answer_label: str,
    case_id: str,
    holdout_case_ids: set,
    overlap_threshold: float = 0.85,
) -> List[Dict[str, Any]]:
    """Auto-detect potential strict-leak candidates in evidence text.

    option-grounded retrieval legitimately surfaces option text, so a
    candidate is NOT a confirmed leak. Each candidate must be human-reviewed
    before counting toward confirmed_leak_count.

    Reasons:
      - answer_text_appears: normalized answer text fully contained in evidence
      - case_id_appears: a holdout case_id appears in evidence
      - high_overlap_<ratio>: character overlap >= threshold
    """
    candidates: List[Dict[str, Any]] = []
    norm_answer = normalize_text(answer_text) if answer_text else ""
    for i, ev in enumerate(evidence_texts):
        reasons: List[str] = []
        norm_ev = normalize_text(ev)
        if norm_answer and norm_answer in norm_ev:
            reasons.append("answer_text_appears")
        if case_id and case_id in ev and case_id in holdout_case_ids:
            reasons.append("case_id_appears")
        if norm_answer:
            ratio = SequenceMatcher(None, norm_answer, norm_ev).ratio()
            if ratio >= overlap_threshold:
                reasons.append(f"high_overlap_{ratio:.2f}")
        if reasons:
            candidates.append({"evidence_index": i, "reasons": reasons})
    return candidates


def classify_parser_failure(
    raw_answer: Optional[str],
    parsed_choice: Optional[str],
    valid: bool,
    label_map: Optional[Dict[str, str]] = None,
    call_success: bool = True,
) -> Optional[str]:
    """Classify a parser failure reason so API failures are not mixed into
    position-bias analysis.

    Returns one of:
      - model_call_failed
      - empty_raw_answer
      - parser_invalid
      - label_out_of_range
      - unshuffle_map_failed
      - None (success)
    """
    if not call_success:
        return "model_call_failed"
    if raw_answer is None or not str(raw_answer).strip():
        return "empty_raw_answer"
    if not valid:
        if parsed_choice is not None and str(parsed_choice).strip().upper() not in _VALID_LABELS:
            return "label_out_of_range"
        return "parser_invalid"
    if label_map is not None:
        inv = {v: k for k, v in label_map.items()}
        if parsed_choice not in inv:
            return "unshuffle_map_failed"
    return None


def _identity_per_prediction(predictions: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    by_case: Dict[str, List[str]] = defaultdict(list)
    for p in predictions:
        if not p.get("call_success"):
            continue
        # Prefer predicted_identity (already unshuffled by caller);
        # fallback to label_map inversion; fallback to predicted_label
        # (off-3 mode: no shuffle, identity = label).
        identity = p.get("predicted_identity")
        if identity is None:
            pred = p.get("predicted_label")
            if pred is None:
                continue
            label_map = p.get("label_map", {})
            if label_map:
                inv = {v: k for k, v in label_map.items()}
                identity = inv.get(pred)
            else:
                identity = pred
        if identity is None:
            continue
        by_case[p.get("case_id", "")].append(identity)
    return by_case


def aggregate_by_option_identity(predictions: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Aggregate multi-permutation predictions by original option identity.

    Only successful calls with a valid unshuffle are included. Ties are broken
    deterministically by sorted option identity.
    """
    by_case = _identity_per_prediction(predictions)
    result: Dict[str, Dict[str, Any]] = {}
    for case_id, identities in by_case.items():
        counts = Counter(identities)
        if not counts:
            continue
        max_count = max(counts.values())
        winners = sorted(ident for ident, c in counts.items() if c == max_count)
        tie = len(winners) > 1
        result[case_id] = {
            "final_identity": winners[0],
            "tie": tie,
            "successful_predictions": len(identities),
            "identity_counts": dict(counts),
        }
    return result


def mean_majority_share(predictions: Sequence[Dict[str, Any]]) -> float:
    """Macro-average of per-case majority option-identity share.

    E.g. 2/3 predictions agree -> 0.667 for that case.
    """
    by_case = _identity_per_prediction(predictions)
    shares: List[float] = []
    for identities in by_case.values():
        if not identities:
            continue
        counts = Counter(identities)
        shares.append(max(counts.values()) / len(identities))
    return sum(shares) / len(shares) if shares else 0.0


def unanimous_case_rate(predictions: Sequence[Dict[str, Any]]) -> float:
    """Fraction of cases where all successful predictions agree on one identity."""
    by_case = _identity_per_prediction(predictions)
    unanimous = 0
    total = 0
    for identities in by_case.values():
        if len(identities) < 2:
            continue
        total += 1
        if len(set(identities)) == 1:
            unanimous += 1
    return unanimous / total if total else 0.0


def pairwise_identity_agreement(predictions: Sequence[Dict[str, Any]]) -> float:
    """Fraction of same-case prediction pairs that agree on option identity."""
    by_case = _identity_per_prediction(predictions)
    total_pairs = 0
    agree_pairs = 0
    for identities in by_case.values():
        for a, b in combinations(identities, 2):
            total_pairs += 1
            if a == b:
                agree_pairs += 1
    return agree_pairs / total_pairs if total_pairs else 0.0


def compute_ite_accuracy(predictions: Sequence[Dict[str, Any]]) -> float:
    """Intent-to-evaluate accuracy: all cases as denominator, failures count wrong.

    Uses majority voting by option identity across permutations (via
    :func:`aggregate_by_option_identity`). A case is correct iff the
    majority identity matches ``correct_identity`` and there is no tie.

    This is the formal ITE metric required by Phase 3 gate — NOT per-call
    accuracy and NOT "any permutation answers correctly".
    """
    if not predictions:
        return 0.0

    # Denominator: every unique case_id that appears in predictions
    all_case_ids: set[str] = set()
    case_correct: Dict[str, str] = {}
    for p in predictions:
        cid = str(p.get("case_id", ""))
        all_case_ids.add(cid)
        if p.get("correct_identity") and cid not in case_correct:
            case_correct[cid] = str(p["correct_identity"])

    total = len(all_case_ids)
    if total == 0:
        return 0.0

    aggregated = aggregate_by_option_identity(predictions)

    correct = 0
    for cid in all_case_ids:
        cci = case_correct.get(cid)
        if cci is None:
            continue  # no correct_identity → wrong
        agg = aggregated.get(cid)
        if agg is None:
            continue  # no successful predictions → wrong
        if not agg["tie"] and agg["final_identity"] == cci:
            correct += 1

    return correct / total


def compute_success_only_accuracy(predictions: Sequence[Dict[str, Any]]) -> float:
    """Success-only accuracy: only cases with >=1 successful call in denominator.

    Uses majority voting by option identity — same logic as
    :func:`compute_ite_accuracy` but denominator excludes cases where
    every call failed. Diagnostic only, NOT used for formal gate.
    """
    if not predictions:
        return 0.0

    aggregated = aggregate_by_option_identity(predictions)

    # Correct identity lookup (from successful calls only)
    case_correct: Dict[str, str] = {}
    for p in predictions:
        if not p.get("call_success"):
            continue
        cid = str(p.get("case_id", ""))
        if p.get("correct_identity") and cid not in case_correct:
            case_correct[cid] = str(p["correct_identity"])

    # Denominator: cases present in aggregated AND have correct_identity
    candidate = set(aggregated.keys()) & set(case_correct.keys())
    total = len(candidate)
    if total == 0:
        return 0.0

    correct = 0
    for cid in candidate:
        agg = aggregated[cid]
        if not agg["tie"] and agg["final_identity"] == case_correct[cid]:
            correct += 1

    return correct / total


def compute_failure_rate(predictions: Sequence[Dict[str, Any]]) -> float:
    """Fraction of calls that failed."""
    if not predictions:
        return 0.0
    failed = sum(1 for p in predictions if not p.get("call_success"))
    return failed / len(predictions)


def paired_flip_counts(off_preds: Sequence[Dict[str, Any]], on_preds: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """Count paired flips between off-control and on-aggregation.

    Each pair must be eligible (both success + parser_valid + unshuffle_success).
    """
    off_by_case = {p["case_id"]: p for p in off_preds}
    on_by_case = {p["case_id"]: p for p in on_preds}
    result = {"off_wrong_on_right": 0, "off_right_on_wrong": 0, "both_right": 0, "both_wrong": 0, "excluded_due_ineligible": 0}
    for case_id in off_by_case:
        if case_id not in on_by_case:
            continue
        o = off_by_case[case_id]
        n = on_by_case[case_id]
        if not (o.get("eligible") and n.get("eligible")):
            result["excluded_due_ineligible"] += 1
            continue
        o_right = o.get("predicted_identity") == o.get("correct_identity")
        n_right = n.get("predicted_identity") == n.get("correct_identity")
        if o_right and n_right:
            result["both_right"] += 1
        elif not o_right and not n_right:
            result["both_wrong"] += 1
        elif not o_right and n_right:
            result["off_wrong_on_right"] += 1
        else:
            result["off_right_on_wrong"] += 1
    return result


def position_selection_frequency(predictions: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """Count how often each A/B/C/D label is selected (successful calls only)."""
    freq: Dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    for p in predictions:
        if not p.get("call_success"):
            continue
        label = p.get("predicted_label")
        if label in freq:
            freq[label] += 1
    return freq


def pair_analysis_eligible_rate(predictions: Sequence[Dict[str, Any]]) -> float:
    """Fraction of cases where both off and on are eligible for pair analysis."""
    by_case: Dict[str, Dict[str, bool]] = defaultdict(dict)
    for p in predictions:
        eligible = p.get("call_success") and p.get("parser_valid") and p.get("unshuffle_success")
        by_case[p.get("case_id", "")][p.get("mode", "")] = bool(eligible)
    if not by_case:
        return 0.0
    eligible_cases = sum(1 for modes in by_case.values() if modes.get("off-3") and modes.get("on-3"))
    return eligible_cases / len(by_case)


def check_hard_cap(actual_calls: int, hard_cap: int) -> Dict[str, Any]:
    """Check whether actual calls have reached the hard cap."""
    return {"cap_reached": actual_calls >= hard_cap, "remaining": max(0, hard_cap - actual_calls)}


def compute_gate_report(
    on_preds: Sequence[Dict[str, Any]],
    off_preds: Sequence[Dict[str, Any]],
    leak_candidate_count: int = 0,
    confirmed_leak_count: int = 0,
    stage_label: str = "",
) -> Dict[str, Any]:
    """Produce a complete Phase 3 formal-gate report dict.

    Parameters
    ----------
    on_preds : per-call predictions for the on-3 (shuffle-on / aggregation) arm.
        Must include ``case_id``, ``predicted_label``, ``label_map``,
        ``call_success``, ``correct_identity``, ``mode`` (``"on-3"``).
    off_preds : per-call predictions for the off-3 control arm.
        Same schema, with ``mode`` = ``"off-3"``.
    leak_candidate_count : auto-detected leak candidate count (design §10.3).
    confirmed_leak_count : human-reviewed confirmed leak count.
    stage_label : label for the report heading (e.g. ``"dev20"``, ``"formal40"``).

    Returns a dict suitable for JSON serialisation / markdown rendering with
    keys matching the formal gate table in design §11.
    """
    # ---- accuracy (aggregated majority-vote) ----
    on_ite = compute_ite_accuracy(on_preds)
    off_ite = compute_ite_accuracy(off_preds)
    shuffle_gap = off_ite - on_ite

    on_success_only = compute_success_only_accuracy(on_preds)
    off_success_only = compute_success_only_accuracy(off_preds)

    # ---- consistency ----
    on_mms = mean_majority_share(on_preds)
    on_unan = unanimous_case_rate(on_preds)
    on_pairwise = pairwise_identity_agreement(on_preds)

    # ---- parser diagnostics ----
    all_preds = list(on_preds) + list(off_preds)
    failure_rate = compute_failure_rate(all_preds)

    # call-level parser_valid
    total_calls = len(all_preds)
    call_parser_valid = sum(1 for p in all_preds if p.get("call_success") and p.get("parser_valid", True))
    call_parser_valid_rate = call_parser_valid / total_calls if total_calls else 0.0

    # case-level aggregation eligible
    aggregated = aggregate_by_option_identity(on_preds)
    all_case_ids = set(p.get("case_id", "") for p in all_preds)
    case_eligible = len(aggregated)
    excluded_count = len(all_case_ids) - case_eligible
    case_eligible_rate = case_eligible / len(all_case_ids) if all_case_ids else 0.0

    # ---- position frequency ----
    on_pos_freq = position_selection_frequency(on_preds)
    off_pos_freq = position_selection_frequency(off_preds)

    # ---- pair analysis ----
    # Aggregate per-call predictions to per-case identity before flip analysis.
    # paired_flip_counts expects one entry per case (not per-call), otherwise
    # the internal case_id dict only keeps the last per-call record.
    on_agg = aggregate_by_option_identity(on_preds)
    off_agg = aggregate_by_option_identity(off_preds)

    def _build_case_list(agg, preds):
        correct_by_case = {}
        for p in preds:
            cid = p.get("case_id", "")
            if cid and cid not in correct_by_case:
                correct_by_case[cid] = p.get("correct_identity")
        return [
            {
                "case_id": cid,
                "predicted_identity": r["final_identity"],
                "correct_identity": correct_by_case.get(cid),
                "eligible": r["successful_predictions"] > 0,
            }
            for cid, r in agg.items()
        ]

    flipped = paired_flip_counts(
        _build_case_list(off_agg, off_preds),
        _build_case_list(on_agg, on_preds),
    )
    eligible_rate = pair_analysis_eligible_rate(
        [dict(p, mode=p.get("mode", "on-3")) for p in on_preds]
        + [dict(p, mode=p.get("mode", "off-3")) for p in off_preds]
    )

    # ---- 3pp advisory ----
    three_pp_pass = abs(shuffle_gap) <= 3.0

    return {
        "stage": stage_label,
        # accuracy
        "on_ite_accuracy": on_ite,
        "off_ite_accuracy": off_ite,
        "shuffle_gap_pp": round(shuffle_gap, 2),
        "on_success_only_accuracy": on_success_only,
        "off_success_only_accuracy": off_success_only,
        # consistency
        "on_mean_majority_share": round(on_mms, 4),
        "on_unanimous_case_rate": round(on_unan, 4),
        "on_pairwise_identity_agreement": round(on_pairwise, 4),
        # parser
        "failure_rate": round(failure_rate, 4),
        "call_parser_valid_rate": round(call_parser_valid_rate, 4),
        "case_aggregation_eligible_rate": round(case_eligible_rate, 4),
        "excluded_case_count": excluded_count,
        # leak
        "leak_candidate_count": leak_candidate_count,
        "confirmed_leak_count": confirmed_leak_count,
        # position
        "on_position_frequency": on_pos_freq,
        "off_position_frequency": off_pos_freq,
        # paired flips
        "off_wrong_on_right": flipped["off_wrong_on_right"],
        "off_right_on_wrong": flipped["off_right_on_wrong"],
        "both_right": flipped["both_right"],
        "both_wrong": flipped["both_wrong"],
        "pair_excluded_ineligible": flipped["excluded_due_ineligible"],
        # pair analysis
        "pair_analysis_eligible_rate": round(eligible_rate, 4),
        "pair_analysis_underpowered": eligible_rate < 0.80,
        # 3pp advisory
        "three_pp_advisory_pass": three_pp_pass,
        "abs_shuffle_gap_pp": round(abs(shuffle_gap), 2),
        # formal gate checks (design §11)
        "gate_ite_28pct": on_ite >= 0.28,
        "gate_mms_80pct": on_mms >= 0.80,
        "gate_parser_valid_95pct": call_parser_valid_rate >= 0.95,
        "gate_confirmed_leak_zero": confirmed_leak_count == 0,
        "gate_off_control_28_3pct": off_ite >= 0.283,
    }


def run_pipeline_trace(num_cases: int = 5) -> Dict[str, Any]:
    """Run a full offline pipeline trace with mock data (no API calls).

    Stages: split -> permutation_plan -> prompt_render -> mock_answer ->
    parse -> unshuffle -> aggregate -> report.

    Used by Task 15 to verify data flow integrity before online execution.
    """
    option_ids = ["o1", "o2", "o3", "o4"]

    # stage: split
    split = [{"case_id": f"mock_case_{i}", "options": [{"id": oid, "text": f"option {oid}", "is_answer": oid == "o1"} for oid in option_ids], "correct_identity": "o1"} for i in range(num_cases)]

    # stage: permutation_plan
    permutation_plan = []
    for case in split:
        plan = build_permutation_plan(option_ids)
        permutation_plan.append({"case_id": case["case_id"], "option_ids": option_ids, "permutations": plan})

    # stage: prompt_render (mock — no actual model)
    prompt_render = []
    for case in split:
        for perm in permutation_plan:
            if perm["case_id"] != case["case_id"]:
                continue
            for p in perm["permutations"]:
                prompt_render.append({"case_id": case["case_id"], "permutation_id": p["permutation_id"], "label_map": p["label_map"], "rendered": f"mock prompt for {case['case_id']} {p['permutation_id']}"})

    # stage: mock_answer (always predict A — deterministic mock)
    mock_answer = []
    for entry in prompt_render:
        mock_answer.append({"case_id": entry["case_id"], "permutation_id": entry["permutation_id"], "predicted_label": "A", "label_map": entry["label_map"]})

    # stage: parse (unshuffle label to identity)
    parse = []
    for ans in mock_answer:
        identity = to_original_option_identity(ans["predicted_label"], ans["label_map"])
        parse.append({"case_id": ans["case_id"], "permutation_id": ans["permutation_id"], "predicted_label": ans["predicted_label"], "identity": identity})

    # stage: unshuffle (already done in parse; record identity)
    unshuffle = [{"case_id": p["case_id"], "permutation_id": p["permutation_id"], "identity": p["identity"]} for p in parse]

    # stage: aggregate
    predictions = [{"case_id": p["case_id"], "permutation_id": p["permutation_id"], "predicted_label": p["predicted_label"], "label_map": next(e["label_map"] for e in prompt_render if e["case_id"] == p["case_id"] and e["permutation_id"] == p["permutation_id"]), "call_success": True, "correct_identity": next(c["correct_identity"] for c in split if c["case_id"] == p["case_id"])} for p in parse]
    aggregate = aggregate_by_option_identity(predictions)

    # stage: report
    report = {
        "ite_accuracy": compute_ite_accuracy(predictions),
        "success_only_accuracy": compute_success_only_accuracy(predictions),
        "failure_rate": compute_failure_rate(predictions),
        "mean_majority_share": mean_majority_share(predictions),
        "unanimous_case_rate": unanimous_case_rate(predictions),
        "pairwise_identity_agreement": pairwise_identity_agreement(predictions),
        "position_selection_frequency": position_selection_frequency(predictions),
    }

    return {
        "split": split,
        "permutation_plan": permutation_plan,
        "prompt_render": prompt_render,
        "mock_answer": mock_answer,
        "parse": parse,
        "unshuffle": unshuffle,
        "aggregate": aggregate,
        "report": report,
    }
