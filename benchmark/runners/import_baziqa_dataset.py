import argparse
import json
from pathlib import Path

DOMAIN_KEYWORDS = {
    "career": ["事业", "工作", "职业", "升职", "官"],
    "wealth": ["财富", "财运", "钱", "富", "投资"],
    "relationship": ["感情", "婚", "恋", "配偶"],
    "health": ["健康", "疾病", "身体", "意外"],
    "family": ["六亲", "父", "母", "兄弟", "子女", "家庭"],
    "study": ["学业", "学历", "学习", "考试"],
    "annual_fortune": ["流年", "哪一年", "年份", "大运"],
}


CATEGORY_DOMAINS = {
    "事业": "career",
    "财富": "wealth",
    "财运": "wealth",
    "感情": "relationship",
    "婚恋": "relationship",
    "健康": "health",
    "六亲": "family",
    "家庭": "family",
    "教育": "study",
    "学业": "study",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_contest8_file(path):
    data = load_json(path)
    if not isinstance(data, list) or not data:
        raise ValueError("Contest8 file must be a non-empty JSON array")
    return data


def load_celebrity50_file(path):
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError("Celebrity50 file must be a JSON array")
    return data


def infer_domain(question, categories=None):
    text = question or ""
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return domain
    if isinstance(categories, dict):
        for label in categories.keys():
            if label in text:
                return CATEGORY_DOMAINS.get(label, "unknown")
    return "unknown"


def normalize_person(person):
    profile = person.get("profile") or {}
    birth = profile.get("birth") or {}
    return {
        "person_id": person.get("person_id", ""),
        "name": person.get("name", ""),
        "gender": profile.get("gender", ""),
        "birth": {
            "year": birth.get("year"),
            "month": birth.get("month"),
            "day": birth.get("day"),
            "hour": birth.get("hour", 0),
            "minute": birth.get("minute", 0),
            "place": birth.get("place", ""),
            "approximate": bool(birth.get("approximate", False)),
        },
    }


def normalize_question(person, question, source, source_year=None):
    return {
        "case_id": question.get("question_id", ""),
        "source": source,
        "source_year": source_year,
        "domain": infer_domain(question.get("question", ""), person.get("categories")),
        "person": normalize_person(person),
        "question": question.get("question", ""),
        "options": question.get("options", []),
        "answer": question.get("answer", ""),
        "expected_evidence": [],
        "verified_events": person.get("categories", {}),
        "difficulty": "unknown",
    }


def normalize_contest8_questions(data):
    meta = data[0]
    contest_id = meta.get("contest_id", "contest8")
    source_year = meta.get("current_year")
    rows = []
    for person in data[1:]:
        for question in person.get("questions", []):
            rows.append(normalize_question(person, question, contest_id, source_year))
    return rows


def normalize_celebrity_questions(data):
    rows = []
    for person in data:
        for question in person.get("questions", []):
            rows.append(normalize_question(person, question, "celebrity50", None))
    return rows


def write_jsonl(rows, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Normalize BaziQA JSON files into XuanJiZi JSONL")
    parser.add_argument("--source-dir", required=True, help="Directory containing BaziQA JSON files")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--include-celebrity", action="store_true")
    args = parser.parse_args(argv)

    source_dir = Path(args.source_dir)
    rows = []
    for year in range(2021, 2026):
        path = source_dir / f"contest8_{year}.json"
        if path.exists():
            rows.extend(normalize_contest8_questions(load_contest8_file(path)))

    celebrity_path = source_dir / "celebrity50_zh.json"
    if args.include_celebrity and celebrity_path.exists():
        rows.extend(normalize_celebrity_questions(load_celebrity50_file(celebrity_path)))

    write_jsonl(rows, args.output)
    print(json.dumps({"output": args.output, "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
