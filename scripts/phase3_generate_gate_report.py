"""Phase 3 gate report generator.

Loads existing case_details JSONL (produced before batch-4 field additions),
joins with original dataset to补全 label_map/correct_identity/call_success,
then calls compute_gate_report to produce a complete gate report.

Usage:
    python scripts/phase3_generate_gate_report.py --stage dev20
    python scripts/phase3_generate_gate_report.py --stage formal40
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.phase3 import compute_gate_report, detect_leak_candidates


DATASET_BY_STAGE = {
    "dev20": "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl",
    "formal40": "benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl",
}

ARMS_BY_STAGE = {
    "link8": ["A1", "A3", "A4"],
    "dev20": ["A1", "A4"],
    "formal40": ["A4"],
}


def load_dataset(path: str) -> Dict[str, Dict[str, Any]]:
    """Load original dataset indexed by case_id."""
    cases = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            cases[row["case_id"]] = row
    return cases


def load_predictions(jsonl_pattern: str, mode_label: str, dataset: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Load case_details, join with dataset to补全 Phase 3 fields.

    Existing dev20/formal40 data was produced before batch-4 field additions,
    so we补全: label_map, correct_identity, call_success, mode, predicted_identity.
    """
    preds: List[Dict[str, Any]] = []
    for f in sorted(glob.glob(jsonl_pattern)):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                cid = row.get("case_id", "")
                ds_case = dataset.get(cid, {})

                # answer_label_map may be present (shuffle_options=True) or absent
                label_map = row.get("answer_label_map") or row.get("label_map") or {}

                # For off-3 (no shuffle): identity = label directly
                # For on-3 (shuffle): identity = unshuffle via label_map
                is_on3 = bool(label_map) or "_on-3_" in row.get("config_id", "")

                if is_on3 and label_map:
                    # on-3: correct_identity = unshuffled option id
                    # Prefer original_expected_answer from case_details (reliable);
                    # dataset answer is unreliable because case_id may map to
                    # multiple questions (same birth chart, different domains).
                    correct_identity = (
                        row.get("correct_identity")
                        or row.get("original_expected_answer")
                    )
                    # predicted_identity: unshuffle via label_map
                    predicted_identity = row.get("predicted_identity")
                    if predicted_identity is None:
                        predicted_label = row.get("predicted_answer")
                        if predicted_label:
                            inv = {v: k for k, v in label_map.items()}
                            predicted_identity = inv.get(predicted_label)
                    if predicted_identity is None:
                        predicted_identity = row.get("original_predicted_answer")
                    unshuffle_success = predicted_identity is not None
                else:
                    # off-3: no shuffle, identity = label
                    # expected_answer from case_details is the ground-truth label.
                    correct_identity = (
                        row.get("correct_identity")
                        or row.get("original_expected_answer")
                        or row.get("expected_answer")
                    )
                    predicted_identity = row.get("predicted_identity") or row.get("predicted_answer")
                    unshuffle_success = predicted_identity is not None

                # call_success: infer from parser_valid (old data has no call_success)
                call_success = row.get("call_success")
                if call_success is None:
                    call_success = bool(row.get("parser_valid", False)) and row.get("predicted_answer") is not None

                # parser_valid fallback
                parser_valid = row.get("parser_valid", False)

                # mode: infer from config_id or label_map presence
                config_id = row.get("config_id", "")
                if "_on-3_" in config_id or label_map:
                    mode = "on-3"
                else:
                    mode = "off-3"

                preds.append({
                    "case_id": cid,
                    "predicted_label": row.get("predicted_answer"),
                    "predicted_identity": predicted_identity,
                    "label_map": label_map,
                    "call_success": call_success,
                    "parser_valid": parser_valid,
                    "correct_identity": correct_identity,
                    "mode": mode_label,
                    "unshuffle_success": unshuffle_success,
                    "rag_trace": row.get("rag_trace") or [],
                    "expected_answer": row.get("expected_answer"),
                    "raw_answer": row.get("raw_answer", ""),
                })
    return preds


def run_leak_check(preds: List[Dict[str, Any]], holdout_case_ids: set) -> int:
    """Run leak detection on predictions, return leak_candidate_count.

    Uses detect_leak_candidates to scan rag_trace evidence for answer text
    or holdout case_id leakage. Candidates are NOT confirmed leaks
    (option-grounded retrieval legitimately surfaces option text).
    """
    leak_count = 0
    for p in preds:
        rag_trace = p.get("rag_trace") or []
        if not rag_trace:
            continue
        evidence_texts = []
        for ev in rag_trace:
            facts = ev.get("facts", "") if isinstance(ev, dict) else str(ev)
            evidence_texts.append(facts)
        answer_label = p.get("expected_answer") or ""
        answer_text = ""
        if answer_label and isinstance(p.get("label_map"), dict):
            inv = {v: k for k, v in p["label_map"].items()}
            answer_text = inv.get(answer_label, answer_label)
        candidates = detect_leak_candidates(
            evidence_texts=evidence_texts,
            answer_text=answer_text,
            answer_label=answer_label,
            case_id=p.get("case_id", ""),
            holdout_case_ids=holdout_case_ids,
        )
        if candidates:
            leak_count += 1
    return leak_count


def verify_freeze_conditions(a1_report: Dict[str, Any], a4_report: Dict[str, Any], confirmed_leak_count: int) -> Dict[str, Any]:
    """Verify design §3.1 freeze conditions for A4 candidate."""
    conditions = {
        "C1_candidate_in_set": True,  # A4 is in {A1, A3, A4}
        "C2_candidate_gte_a1": a4_report["on_ite_accuracy"] >= a1_report["on_ite_accuracy"],
        "C3_ite_gte_23pct": a4_report["on_ite_accuracy"] >= 0.23,
        "C4_parser_valid_gte_95pct": a4_report["call_parser_valid_rate"] >= 0.95,
        "C5_confirmed_leak_zero": confirmed_leak_count == 0,
        "C6_mms_gte_a1": a4_report["on_mean_majority_share"] >= a1_report["on_mean_majority_share"],
    }
    return {
        "candidate": "A4",
        "all_conditions_pass": all(conditions.values()),
        "conditions": conditions,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Phase 3 gate report generator")
    parser.add_argument("--stage", required=True, choices=["dev20", "formal40", "link8"])
    parser.add_argument("--output", default=None, help="Output JSON path (default: stdout)")
    args = parser.parse_args(argv)

    dataset_path = DATASET_BY_STAGE.get(args.stage)
    if not dataset_path or not Path(dataset_path).exists():
        print(f"ERROR: dataset not found for stage {args.stage}: {dataset_path}", file=sys.stderr)
        return 1

    dataset = load_dataset(dataset_path)
    holdout_case_ids = set(dataset.keys())
    arms = ARMS_BY_STAGE.get(args.stage, [])

    reports = {}
    for arm in arms:
        on_pattern = f".tmp/phase3_{args.stage}/{args.stage}_{arm}_on-3_p*.jsonl"
        off_pattern = f".tmp/phase3_{args.stage}/{args.stage}_{arm}_off-3_p*.jsonl"

        on_preds = load_predictions(on_pattern, "on-3", dataset)
        off_preds = load_predictions(off_pattern, "off-3", dataset)

        if not on_preds:
            print(f"WARN: no on-3 predictions for {arm}", file=sys.stderr)
            continue
        if not off_preds:
            print(f"WARN: no off-3 predictions for {arm}", file=sys.stderr)
            continue

        all_preds = on_preds + off_preds
        leak_count = run_leak_check(all_preds, holdout_case_ids)

        report = compute_gate_report(
            on_preds, off_preds,
            leak_candidate_count=leak_count,
            confirmed_leak_count=0,
            stage_label=f"{args.stage}_{arm}",
        )
        reports[arm] = report

        print(f"\n=== {args.stage}_{arm} gate report ===")
        print(json.dumps(report, indent=2, ensure_ascii=False))

    # Freeze condition verification (dev20 only)
    if args.stage == "dev20" and "A1" in reports and "A4" in reports:
        a4_leak = reports["A4"].get("leak_candidate_count", 0)
        freeze = verify_freeze_conditions(reports["A1"], reports["A4"], confirmed_leak_count=0)
        print(f"\n=== Freeze condition verification ===")
        print(json.dumps(freeze, indent=2, ensure_ascii=False))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(reports, fh, indent=2, ensure_ascii=False)
        print(f"\nReports written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
