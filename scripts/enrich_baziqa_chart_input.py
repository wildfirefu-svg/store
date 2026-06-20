import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bazi_calculator import compute_chart


def _birth(row):
    person = row.get("person") or {}
    birth = person.get("birth") or {}
    return person, birth


def enrich_row(row, compute_chart_fn=compute_chart):
    if row.get("chart_input"):
        return row
    person, birth = _birth(row)
    try:
        chart = compute_chart_fn(
            int(birth.get("year")),
            int(birth.get("month")),
            int(birth.get("day")),
            int(birth.get("hour", 0) or 0),
            int(birth.get("minute", 0) or 0),
            person.get("gender") or "male",
            birth.get("place") or "Beijing",
        )
    except (TypeError, ValueError, KeyError):
        return row
    out = dict(row)
    out["chart_input"] = chart
    return out


def load_jsonl(path):
    rows = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_rows(rows):
    total = len(rows)
    with_chart = sum(1 for row in rows if row.get("chart_input"))
    return {"total": total, "with_chart_input": with_chart, "coverage": with_chart / total if total else 0.0}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Enrich BaziQA JSONL rows with chart_input.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", default="docs/BAZIQA_CHART_INPUT_ENRICHMENT_REPORT.md")
    args = parser.parse_args(argv)

    rows = [enrich_row(row) for row in load_jsonl(args.input)]
    write_jsonl(args.output, rows)
    summary = summarize_rows(rows)
    text = "\n".join([
        "# BaziQA Chart Input Enrichment Report",
        "",
        f"- Total: {summary['total']}",
        f"- With chart_input: {summary['with_chart_input']}",
        f"- Coverage: {summary['coverage']:.1%}",
        f"- Output: {args.output}",
        "",
    ])
    Path(args.summary).write_text(text, encoding="utf-8")
    print(f"Enriched file saved to {args.output}")
    print(f"Summary saved to {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
