"""
fill_missing_chapters.py
Fill missing chapters for zpzq (34) and qtbj (11) using corrected distill_lib.
Reads the full raw text, splits by chapter heading, distills missing chapters only,
appends to all_rules.json + all_mcq.jsonl, updates progress.json.

Usage: python scripts/fill_missing_chapters.py [book_dir_key ...]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import distill_lib as dl

BASE = ROOT / "knowledge_base" / "classic_texts"

# Chinese numeral map for zpzq chapter headings
CN_NUM = "一二三四五六七八九十"
def _cn_to_int(s: str) -> int:
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + _cn_to_int(s[1:])
    if s.endswith("十"):
        return _cn_to_int(s[:-1]) * 10
    if "十" in s:
        a, b = s.split("十")
        return _cn_to_int(a) * 10 + _cn_to_int(b)
    return CN_NUM.index(s) + 1 if s in CN_NUM else 0


def _split_by_titles(text: str, titles: list[str]) -> dict[str, str]:
    """Split text by known titles: find each title in text, extract until next title."""
    positions = []
    for t in titles:
        idx = text.find(t)
        if idx >= 0:
            positions.append((idx, t))
    positions.sort()
    chapters = {}
    for i, (idx, t) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        chapters[t] = text[idx:end].strip()
    return chapters


def split_zpzq(text: str, titles: list[str]) -> dict[str, str]:
    return _split_by_titles(text, titles)


def split_qtbj(text: str, titles: list[str]) -> dict[str, str]:
    return _split_by_titles(text, titles)


def fill_book(dir_key: str) -> dict:
    if dir_key == "zipingzhenquan":
        name, prefix, book_name = "子平真诠", "zpzq", "子平真诠"
        full_raw = BASE / dir_key / "raw_full.txt"
        if not full_raw.exists():
            return {"book": name, "error": "raw_full.txt not found"}
        text = full_raw.read_text(encoding="utf-8")
        ch_list = (BASE / dir_key / "chapter_list.txt").read_text(encoding="utf-8").splitlines()
        wanted = []
        for line in ch_list:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\d+\.\s*(.+)", line)
            if m:
                wanted.append(m.group(1).strip())
        chapters = split_zpzq(text, wanted)
    elif dir_key == "qiongtongbaojian":
        name, prefix, book_name = "穷通宝鉴", "qtbj", "穷通宝鉴"
        full_raw = BASE / dir_key / "raw_full.txt"
        if not full_raw.exists():
            return {"book": name, "error": "raw_full.txt not found"}
        text = full_raw.read_text(encoding="utf-8")
        sec_list = (BASE / dir_key / "section_list.txt").read_text(encoding="utf-8").splitlines()
        wanted = []
        for line in sec_list:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\d+\.\s*(.+)", line)
            if m:
                wanted.append(m.group(1).strip())
        chapters = split_qtbj(text, wanted)
    else:
        return {"error": f"unsupported book {dir_key}"}

    prog = json.loads((BASE / dir_key / "progress.json").read_text(encoding="utf-8"))
    done = set(prog.get("done", []))

    # find missing
    missing = []
    for w in wanted:
        if w not in done and w in chapters:
            missing.append(w)
    print(f"[{name}] {len(missing)} missing chapters to fill", flush=True)

    # load existing
    rules_path = BASE / dir_key / "all_rules.json"
    mcq_path = BASE / dir_key / "all_mcq.jsonl"
    existing_rules = json.loads(rules_path.read_text(encoding="utf-8"))
    existing_mcqs = [json.loads(l) for l in mcq_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    # determine ch_idx offset (max existing chapter index + 1)
    ch_indices = []
    for r in existing_rules:
        rid = r.get("id", "")
        m = re.search(rf"^{prefix}_(\d{{3}})_", rid)
        if m:
            ch_indices.append(int(m.group(1)))
    next_ch_idx = max(ch_indices) + 1 if ch_indices else 0

    # determine mcq seq offset
    mcq_seqs = []
    for m in existing_mcqs:
        mid = m.get("id", "")
        mt = re.search(r"mcq_(\d{4})$", mid)
        if mt:
            mcq_seqs.append(int(mt.group(1)))
    next_mcq_seq = max(mcq_seqs) + 1 if mcq_seqs else 0

    new_rules_total = []
    new_mcqs_total = []
    for ch_title in missing:
        ch_text = chapters[ch_title]
        print(f"  [{next_ch_idx}] {ch_title[:25]}...", flush=True)
        try:
            rules = dl.distill_chapter(ch_text, book_name, ch_title)
        except Exception as e:
            print(f"    DISTILL ERROR: {e}")
            rules = []
        dl.assign_rule_ids(rules, prefix, next_ch_idx)
        (BASE / dir_key / f"raw_{next_ch_idx:03d}_{ch_title[:10]}.txt").write_text(ch_text, encoding="utf-8")

        try:
            mcqs = dl.generate_mcq(rules, book_name, ch_title)
            mcqs = dl.link_mcq_to_rules(mcqs, rules)
        except Exception as e:
            print(f"    MCQ ERROR: {e}")
            mcqs = []
        next_mcq_seq = dl.assign_mcq_ids(mcqs, prefix, next_ch_idx, next_mcq_seq)

        new_rules_total.extend(rules)
        new_mcqs_total.extend(mcqs)
        done.add(ch_title)
        next_ch_idx += 1
        time.sleep(0.3)

    # merge + write
    all_rules = existing_rules + new_rules_total
    all_mcqs = existing_mcqs + new_mcqs_total
    dl.rotate_answers(all_mcqs)

    rules_path.write_text(json.dumps(all_rules, ensure_ascii=False, indent=2), encoding="utf-8")
    mcq_path.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in all_mcqs), encoding="utf-8")
    prog["done"] = list(done)
    prog["total_rules"] = len(all_rules)
    prog["total_mcqs"] = len(all_mcqs)
    (BASE / dir_key / "progress.json").write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[{name}] added {len(new_rules_total)} rules, {len(new_mcqs_total)} MCQ")
    return {"book": name, "added_rules": len(new_rules_total), "added_mcq": len(new_mcqs_total),
            "total_rules": len(all_rules), "total_mcq": len(all_mcqs)}


def main() -> int:
    targets = [a for a in sys.argv[1:] if a in ("zipingzhenquan", "qiongtongbaojian")]
    if not targets:
        targets = ["zipingzhenquan", "qiongtongbaojian"]
    for k in targets:
        fill_book(k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
