"""Render docs/BAZIQA_LOVO_REPORT.md from the JSON rows produced by verify_baziqa_lovo.ps1."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _load(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    data = json.loads(text)
    if isinstance(data, dict):
        return [data]
    return data


def main():
    rows = _load(Path(os.environ.get("BAZIQA_LOVO_ROWS", ".tmp/baziqa_lovo_rows.json")))
    output = Path(os.environ.get("BAZIQA_LOVO_OUTPUT", "docs/BAZIQA_LOVO_REPORT.md"))
    source = os.environ.get("BAZIQA_LOVO_SOURCE", "")
    max_cases = os.environ.get("BAZIQA_LOVO_MAX", "")

    pipe = chr(124)
    lines = [
        "# BaziQA Leave-One-Year-Out Report",
        "",
        f"Source: `{source}`  MaxCases per year: {max_cases}",
        "",
        f"{pipe} Holdout Year {pipe} Correct {pipe} Total {pipe} Accuracy {pipe} RunId {pipe}",
        f"{pipe} --- {pipe} ---: {pipe} ---: {pipe} ---: {pipe} --- {pipe}",
    ]
    accs = []
    for row in rows:
        acc = float(row["Accuracy"])
        accs.append(acc)
        lines.append(
            f"{pipe} {row['Year']} {pipe} {row['Correct']} {pipe} {row['Total']} {pipe} "
            f"{acc * 100:.1f}% {pipe} {row.get('RunId', '')} {pipe}"
        )

    mean = sum(accs) / len(accs) if accs else 0.0
    minimum = min(accs) if accs else 0.0
    lines.extend([
        "",
        f"Mean accuracy: {mean * 100:.1f}%",
        f"Minimum yearly accuracy: {minimum * 100:.1f}%",
        "",
        "## Accuracy Gates",
        "",
        "- Mean accuracy gate: >= 40.0%",
        "- Minimum yearly accuracy gate: >= 30.0%",
    ])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Written", output)


if __name__ == "__main__":
    main()
