"""Render docs/BAZIQA_RAG_REPORT.md from the JSON results dropped by verify_baziqa_rag_lift.ps1."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _load_results(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    return json.loads(text)


def _format_acc(item):
    accuracy = float(item.get("Accuracy", 0.0) or 0.0)
    correct = item.get("Correct", "")
    total = item.get("Total", "")
    text = f"{accuracy * 100:.1f}%"
    if correct != "" and total != "":
        text += f" ({correct}/{total})"
    return accuracy, text


def main():
    results_path = Path(os.environ.get("BAZIQA_RAG_LIFT_RESULTS", ".tmp/baziqa_rag_lift_results.json"))
    output = Path(os.environ.get("BAZIQA_RAG_LIFT_OUTPUT", "docs/BAZIQA_RAG_REPORT.md"))
    holdout = os.environ.get("BAZIQA_RAG_LIFT_HOLDOUT", "")
    provider = os.environ.get("BAZIQA_RAG_LIFT_PROVIDER", "")
    model = os.environ.get("BAZIQA_RAG_LIFT_MODEL", "")
    max_cases = os.environ.get("BAZIQA_RAG_LIFT_MAX", "")
    status = os.environ.get("BAZIQA_RAG_LIFT_STATUS", "?")

    results = _load_results(results_path)
    baseline_item = next(r for r in results if r["Label"] == "baseline-direct")
    baseline = float(baseline_item["Accuracy"])
    threshold = baseline + 0.08

    pipe = chr(124)
    header = f"{pipe} Run {pipe} Method {pipe} RAG {pipe} Accuracy {pipe} Delta {pipe} RunId {pipe}"
    sep = f"{pipe} --- {pipe} ------ {pipe} --- {pipe} -------- {pipe} ----- {pipe} -------- {pipe}"

    lines = ["# BaziQA RAG Lift Report", ""]
    lines.append(
        f"Holdout: `{holdout}`  Provider: `{provider}`  Model: `{model}`  MaxCases: {max_cases}"
    )
    lines.append("")
    lines.append(header)
    lines.append(sep)
    for r in results:
        accuracy, acc_text = _format_acc(r)
        delta = round((accuracy - baseline) * 100, 1)
        delta_str = ("+" if delta >= 0 else "") + f"{delta}pp"
        rag_str = "ON" if r["Rag"] else "OFF"
        lines.append(
            f"{pipe} {r['Label']} {pipe} {r['Method']} {pipe} {rag_str} {pipe} "
            f"{acc_text} {pipe} {delta_str} {pipe} {r['RunId']} {pipe}"
        )

    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(
        f"- baseline={baseline * 100:.1f}%, threshold=baseline+8pp = {threshold * 100:.1f}%"
    )
    rag_direct = next((r for r in results if r["Label"] == "rag-direct"), None)
    rag_structured = next((r for r in results if r["Label"] == "rag-structured"), None)
    if rag_direct:
        _, rd_text = _format_acc(rag_direct)
        lines.append(f"- rag-direct={rd_text}")
    if rag_structured:
        _, rs_text = _format_acc(rag_structured)
        lines.append(f"- rag-structured={rs_text}")
    lines.append(f"- status={status}")

    lines.extend([
        "",
        "## Accuracy Gates",
        "",
        "- structured RAG target: >= 40.0% on 40-case holdout",
        "- direct RAG target: baseline + >= 8.0 percentage points",
        "- repeated evaluation target: min structured RAG >= 35.0%",
        "- leave-one-year-out target: mean >= 40.0%, minimum yearly accuracy >= 30.0%",
    ])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print("Written", output)


if __name__ == "__main__":
    main()
