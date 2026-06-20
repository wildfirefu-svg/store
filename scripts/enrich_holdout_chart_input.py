"""Enrich holdout dataset with chart_input from bazi_calculator."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bazi_calculator import compute_chart


def enrich_row(row: dict) -> dict:
    """Add chart_input to a holdout row by computing the bazi chart."""
    person = row.get("person") or {}
    birth = person.get("birth") or {}
    year = birth.get("year")
    month = birth.get("month")
    day = birth.get("day")
    if not (year and month and day):
        return row

    try:
        chart = compute_chart(
            year=int(year),
            month=int(month),
            day=int(day),
            hour=int(birth.get("hour", 0)),
            minute=int(birth.get("minute", 0)),
            gender=person.get("gender", "male"),
        )
        row["chart_input"] = chart
    except Exception as e:
        row["chart_input_error"] = str(e)
    return row


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = []
    success = 0
    fail = 0
    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            enrich_row(row)
            rows.append(row)
            if row.get("chart_input"):
                success += 1
            else:
                fail += 1

    with open(args.output, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Enriched {success}/{len(rows)} rows (fail={fail})")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
