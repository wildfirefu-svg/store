from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


FAMILY_KEYWORDS: Tuple[str, ...] = (
    "婚", "离", "再婚", "夫", "妻", "子", "女", "父", "母", "兄", "弟", "姐",
    "家", "伴侣", "配偶", "子女", "丧偶", "再嫁", "嫁", "娶", "生子", "堕胎",
    "流产", "六亲", "父亲", "母亲",
)

HEALTH_KEYWORDS: Tuple[str, ...] = (
    "病", "术", "手术", "肿瘤", "癌", "住院", "伤", "车祸", "中风", "心脏",
    "肝", "肾", "脾", "胃", "肺", "糖尿病", "高血压", "失眠", "头痛", "抑郁",
    "焦虑", "中医", "西医", "医院", "健康",
)

RELATIONSHIP_KEYWORDS: Tuple[str, ...] = (
    "恋", "感情", "分手", "交往", "暧昧", "第三者", "出轨", "桃花", "婚外",
    "男友", "女友", "约会", "订婚", "离异",
)

DOMAIN_KEYWORDS = {
    "health": HEALTH_KEYWORDS,
    "relationship": RELATIONSHIP_KEYWORDS,
    "family": FAMILY_KEYWORDS,
}
DOMAIN_ORDER = ("health", "relationship", "family")


def _row_text(row: Dict[str, Any]) -> str:
    parts = [str(row.get("question") or "")]
    options = row.get("options") or []
    if isinstance(options, list):
        parts.extend(str(o) for o in options)
    return " ".join(parts)


def infer_domain(row: Dict[str, Any]) -> Optional[str]:
    text = _row_text(row)
    if not text.strip():
        return None
    hits: List[str] = []
    for domain in DOMAIN_ORDER:
        keywords = DOMAIN_KEYWORDS[domain]
        if any(kw in text for kw in keywords):
            hits.append(domain)
    if len(hits) == 1:
        return hits[0]
    return None


def reclassify_rows(rows: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Counter]:
    updated: List[Dict[str, Any]] = []
    transitions: Counter = Counter()
    for row in rows:
        current = str(row.get("domain") or "unknown")
        target = current
        if current == "unknown":
            inferred = infer_domain(row)
            if inferred:
                target = inferred
        new_row = dict(row)
        new_row["domain"] = target
        updated.append(new_row)
        transitions[(current, target)] += 1
    return updated, transitions


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_summary(path: Path, transitions: Counter, before: Counter, after: Counter) -> None:
    lines = ["# corpus domain reclassification summary", ""]
    lines.append("## Before")
    for domain, count in sorted(before.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {domain}: {count}")
    lines.append("")
    lines.append("## After")
    for domain, count in sorted(after.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {domain}: {count}")
    lines.append("")
    lines.append("## Transitions")
    for (src, dst), count in sorted(transitions.items(), key=lambda kv: (-kv[1], kv[0])):
        if src == dst:
            continue
        lines.append(f"- {src} -> {dst}: {count}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Reclassify BaziQA corpus rows into family/health/relationship domain based on keyword hits (unknown-only).")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", default=None)
    args = parser.parse_args(argv)

    src = Path(args.input)
    dst = Path(args.output)
    rows = _load_jsonl(src)
    before = Counter(str(row.get("domain") or "unknown") for row in rows)
    updated, transitions = reclassify_rows(rows)
    after = Counter(str(row.get("domain") or "unknown") for row in updated)
    _write_jsonl(dst, updated)
    if args.summary:
        _write_summary(Path(args.summary), transitions, before, after)
    print(json.dumps({"before": dict(before), "after": dict(after)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
