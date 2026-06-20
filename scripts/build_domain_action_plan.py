import argparse
import json
from pathlib import Path


def build_actions(summary, min_cases=3, threshold=0.25):
    actions = []
    for row in summary.get("domain_summary", []):
        total = int(row.get("total") or 0)
        accuracy = float(row.get("accuracy") or 0.0)
        if total >= min_cases and accuracy < threshold:
            actions.append({
                "domain": row.get("domain") or "unknown",
                "total": total,
                "accuracy": accuracy,
                "action": "add_domain_rules_and_examples",
            })
    return actions


def render_report(actions):
    lines = [
        "# BaziQA Domain Action Plan",
        "",
        "| domain | total | accuracy | action |",
        "|---|---:|---:|---|",
    ]
    for action in actions:
        lines.append(f"| {action['domain']} | {action['total']} | {action['accuracy']:.1%} | {action['action']} |")
    if not actions:
        lines.append("| none | 0 | 0.0% | no_domain_below_threshold |")
    lines.extend([
        "",
        "Execution rule: only add domain-specific prompt or corpus changes for domains listed above.",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build domain action plan from BaziQA error attribution JSON.")
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--output", default="docs/BAZIQA_DOMAIN_ACTION_PLAN.md")
    parser.add_argument("--min-cases", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.25)
    args = parser.parse_args(argv)

    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    actions = build_actions(summary, min_cases=args.min_cases, threshold=args.threshold)
    Path(args.output).write_text(render_report(actions), encoding="utf-8")
    print(f"Domain action plan saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
