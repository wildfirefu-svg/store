#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def trace_signature(row: dict) -> tuple:
    return tuple(item.get("person_id") or item.get("name") or "" for item in row.get("rag_trace") or [])


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    runs = []
    for idx, raw in enumerate(args.inputs, 1):
        path = Path(raw)
        rows = load_jsonl(path)
        runs.append({"idx": idx, "path": path, "rows": rows, "by_case": {r["case_id"]: r for r in rows}})

    case_ids = []
    seen = set()
    for run in runs:
        for row in run["rows"]:
            cid = row["case_id"]
            if cid not in seen:
                seen.add(cid)
                case_ids.append(cid)

    lines = []
    lines.append("# BaziQA Trace Diagnosis Report")
    lines.append("")
    lines.append("## Run Summary")
    lines.append("")
    lines.append("| Run | File | Rows | Correct | Accuracy |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for run in runs:
        rows = run["rows"]
        correct = sum(1 for r in rows if r.get("correct"))
        total = len(rows)
        acc = correct / total if total else 0.0
        lines.append(f"| {run['idx']} | `{run['path']}` | {total} | {correct} | {acc:.1%} |")

    unstable_predictions = []
    unstable_rag = []
    correctness_flips = []

    lines.append("")
    lines.append("## Per-Case Comparison")
    lines.append("")
    lines.append("| Case | Expected | Predictions | Correctness | RAG Top-k Stable | RAG Signatures |")
    lines.append("| --- | --- | --- | --- | --- | --- |")

    for cid in case_ids:
        rows = [run["by_case"].get(cid) for run in runs]
        rows = [r for r in rows if r]
        expected = rows[0].get("expected_answer") if rows else ""
        preds = [r.get("predicted_answer") for r in rows]
        corrects = ["✓" if r.get("correct") else "✗" for r in rows]
        sigs = [trace_signature(r) for r in rows]
        pred_stable = len(set(preds)) <= 1
        rag_stable = len(set(sigs)) <= 1
        correctness_stable = len(set(corrects)) <= 1
        if not pred_stable:
            unstable_predictions.append(cid)
        if not rag_stable:
            unstable_rag.append(cid)
        if not correctness_stable:
            correctness_flips.append(cid)
        sig_text = " / ".join(
            ",".join(x for x in sig if x) or "-" for sig in sigs
        )
        lines.append(
            f"| `{cid}` | {expected} | {' / '.join(str(x) for x in preds)} | "
            f"{' / '.join(corrects)} | {'YES' if rag_stable else 'NO'} | {sig_text} |"
        )

    lines.append("")
    lines.append("## Diagnosis")
    lines.append("")
    lines.append(f"- Total compared cases: **{len(case_ids)}**")
    lines.append(f"- Prediction-unstable cases: **{len(unstable_predictions)}**")
    lines.append(f"- Correctness-flip cases: **{len(correctness_flips)}**")
    lines.append(f"- RAG-topk-unstable cases: **{len(unstable_rag)}**")
    lines.append("")
    lines.append("### Lists")
    lines.append("")
    lines.append(f"- Prediction unstable: {', '.join(unstable_predictions) or 'None'}")
    lines.append(f"- Correctness flips: {', '.join(correctness_flips) or 'None'}")
    lines.append(f"- RAG unstable: {', '.join(unstable_rag) or 'None'}")

    if unstable_predictions and not unstable_rag:
        lines.append("")
        lines.append("### Primary Interpretation")
        lines.append("")
        lines.append("RAG top-k is stable for the compared cases, but model predictions still vary. This points to model/API output instability or answer extraction sensitivity rather than retrieval ordering instability.")
    elif unstable_rag:
        lines.append("")
        lines.append("### Primary Interpretation")
        lines.append("")
        lines.append("At least one case has unstable RAG top-k. Inspect retrieval scoring/tie-breaks and corpus order before attributing variance to the model.")
    else:
        lines.append("")
        lines.append("### Primary Interpretation")
        lines.append("")
        lines.append("Both predictions and RAG top-k are stable on this sample. Larger variance likely comes from broader sample composition rather than per-case nondeterminism in this subset.")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    raise SystemExit(main())
