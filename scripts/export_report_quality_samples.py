import argparse
import json
from pathlib import Path


def build_row(case_id, chart, report_text):
    return {"case_id": case_id, "chart": chart, "report_text": report_text}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export report quality samples to JSONL gate input.")
    parser.add_argument("--input-json", required=True, help="JSON list with case_id, chart, report_text")
    parser.add_argument("--output-jsonl", default=".tmp/report_quality_samples.jsonl")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("cases", [])
    Path(args.output_jsonl).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.output_jsonl).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(build_row(row["case_id"], row["chart"], row["report_text"]), ensure_ascii=False) + "\n")
    print(f"Report quality samples saved to {args.output_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
