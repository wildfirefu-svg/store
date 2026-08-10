"""
Fetch + distill 子平真诠 (48 chapters, single page).
Split by chapter headings, then distill each chapter.
"""
import sys, json, re, os, time, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_api import call_model_messages_sync_with_meta

os.environ["DEEPSEEK_API_KEY"] = open("G:/project/agent/.env").read().split("DEEPSEEK_API_KEY=")[1].split("\n")[0].strip()

OUTPUT_DIR = Path("G:/project/agent/knowledge_base/classic_texts/zipingzhenquan")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DISTILL_PROMPT = (
    "你是八字命理知识工程师。从以下古文段落中提取结构化命理规则，输出JSON数组。\n"
    "每条规则格式：\n"
    '{{"id":"zpzq_{seq:03d}","category":"天干|地支|五行|十神|格局|用神|大运|流年|六亲|性情|疾病|其他","subject":"主体","condition":"条件","rule":"白话规则(<=100字)","original_text":"古文引用(<=50字)","source_book":"子平真诠","source_chapter":"{ch}"}}\n\n'
    "古文（子平真诠·{ch}）：\n{text}\n\n"
    "注意：只提取有明确命理含义的规则。无规则则返回[]。只输出JSON数组。"
)

MCQ_PROMPT = (
    "你是八字命理考试出题专家。根据以下规则生成四选一选择题，每条规则一题。\n"
    "输出JSON数组，每题格式：\n"
    '{{"id":"zpzq_mcq_{seq:03d}","question":"题干","options":{{"A":"...","B":"...","C":"...","D":"..."}},"answer":"字母","explanation":"解析","source_rule_id":"对应ID","difficulty":"基础|中级|高级","category":"天干|地支|五行|十神|格局|用神|其他"}}\n\n'
    "规则：\n{rules_json}\n\n只输出JSON数组。"
)

def fetch_and_split():
    url = "https://www.goodu.info/node/2573"
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.encoding = "utf-8"
    html = r.text
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\n{3,}", "\n\n", text)

    start = text.find("论十干十二支")
    if start < 0:
        start = text.find("论干支")
    if start < 0:
        start = 0
    end = text.find("相关阅读")
    if end < 0:
        end = len(text)
    text = text[start:end]

    pattern = r"^[\u4e00\u5341\u767e\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d]{1,4}\u3001\u8bba[\u4e00-\u9fff]{2,20}$"
    splits = []
    lines = text.split("\n")
    chapter_starts = []
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            chapter_starts.append(i)
    for idx, start_line in enumerate(chapter_starts):
        end_line = chapter_starts[idx + 1] if idx + 1 < len(chapter_starts) else len(lines)
        ch_title = lines[start_line].strip()
        ch_text = "\n".join(lines[start_line:end_line]).strip()
        splits.append((ch_title, ch_text))

    return splits


def distill_chapter(ch_name, text, seq_base):
    prompt = DISTILL_PROMPT.replace("{ch}", ch_name).replace("{text}", text[:8000]).replace("{seq}", str(seq_base))
    resp, _ = call_model_messages_sync_with_meta(
        [{"role": "user", "content": prompt}],
        provider="deepseek", model="deepseek-v4-flash",
        thinking_mode="disabled", temperature=0.0, timeout=300,
    )
    try:
        return json.loads(resp.strip())
    except Exception:
        m = re.search(r'\[.*\]', resp, re.DOTALL)
        return json.loads(m.group()) if m else []


def gen_mcq(ch_name, rules, seq_base):
    if not rules:
        return []
    rules_json = json.dumps(rules[:15], ensure_ascii=False, indent=2)
    prompt = MCQ_PROMPT.replace("{rules_json}", rules_json).replace("{seq}", str(seq_base))
    resp, _ = call_model_messages_sync_with_meta(
        [{"role": "user", "content": prompt}],
        provider="deepseek", model="deepseek-v4-flash",
        thinking_mode="disabled", temperature=0.0, timeout=300,
    )
    try:
        return json.loads(resp.strip())
    except Exception:
        m = re.search(r'\[.*\]', resp, re.DOTALL)
        return json.loads(m.group()) if m else []


def main():
    print("Fetching 子平真诠 full text...", flush=True)
    chapters = fetch_and_split()
    print(f"Split into {len(chapters)} chapters", flush=True)

    (OUTPUT_DIR / "chapter_list.txt").write_text(
        "\n".join(f"{i+1}. {t}" for i, (t, _) in enumerate(chapters)), encoding="utf-8"
    )

    progress_file = OUTPUT_DIR / "progress.json"
    if progress_file.exists():
        progress = json.load(open(progress_file, encoding="utf-8"))
        done = set(progress.get("done", []))
        all_rules = progress.get("all_rules", [])
        all_mcqs = progress.get("all_mcqs", [])
    else:
        done = set()
        all_rules = []
        all_mcqs = []

    total = len(chapters)
    for idx, (ch_title, ch_text) in enumerate(chapters):
        if ch_title in done:
            print(f"[{idx+1}/{total}] {ch_title} - SKIP", flush=True)
            continue

        print(f"[{idx+1}/{total}] {ch_title} - distilling...", flush=True)
        (OUTPUT_DIR / f"raw_{idx+1:02d}.txt").write_text(ch_text, encoding="utf-8")

        try:
            rules = distill_chapter(ch_title, ch_text, idx * 10 + 1)
        except Exception as e:
            print(f"  DISTILL ERROR: {e}", flush=True)
            rules = []
        all_rules.extend(rules)

        try:
            mcqs = gen_mcq(ch_title, rules, idx * 10 + 1)
        except Exception as e:
            print(f"  MCQ ERROR: {e}", flush=True)
            mcqs = []
        all_mcqs.extend(mcqs)

        print(f"  rules={len(rules)} mcq={len(mcqs)}", flush=True)

        done.add(ch_title)
        progress = {"done": list(done), "total_rules": len(all_rules), "total_mcqs": len(all_mcqs)}
        progress_file.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(0.5)

    with open(OUTPUT_DIR / "all_rules.json", "w", encoding="utf-8") as f:
        json.dump(all_rules, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "all_mcq.jsonl", "w", encoding="utf-8") as f:
        for m in all_mcqs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    print(f"\n=== DONE: {len(done)}/{total} chapters, {len(all_rules)} rules, {len(all_mcqs)} MCQs ===", flush=True)


if __name__ == "__main__":
    main()
