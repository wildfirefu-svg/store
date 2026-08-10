"""
Batch fetch + distill 滴天髓 64 chapters.
Fetches each chapter, extracts rules and generates MCQ.
Saves results incrementally to avoid data loss on crash.
"""
import sys, json, re, os, time, hashlib
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_api import call_model_messages_sync_with_meta

os.environ["DEEPSEEK_API_KEY"] = open("G:/project/agent/.env").read().split("DEEPSEEK_API_KEY=")[1].split("\n")[0].strip()

OUTPUT_DIR = Path("G:/project/agent/knowledge_base/classic_texts/ditiansui")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHAPTERS = [
    (548874, "序"), (548877, "天道"), (548880, "坤道"), (548883, "人道"),
    (548886, "知命"), (548889, "理气"), (548892, "配合"), (548895, "天干"),
    (548898, "地支"), (548901, "干支总论"), (548904, "形象"), (548907, "方局"),
    (548910, "八格"), (548913, "体用"), (548915, "精神"), (548917, "月令"),
    (548919, "生时"), (548921, "衰旺"), (548923, "中和"), (548926, "源流"),
    (548929, "通关"), (548932, "官杀"), (548935, "伤官"), (548938, "清气"),
    (548941, "浊气"), (548944, "真神"), (548947, "假神"), (548950, "刚柔"),
    (548953, "顺逆"), (548956, "寒暖"), (548959, "燥湿"), (548962, "隐显"),
    (548965, "众寡"), (548968, "震兑"), (548971, "坎离"), (548974, "夫妻"),
    (548977, "子女"), (548980, "父母"), (548983, "兄弟"), (548986, "何知"),
    (548988, "女命"), (548991, "小儿"), (548994, "才德"), (548997, "奋郁"),
    (549000, "恩怨"), (549003, "闲神"), (549006, "从象"), (549008, "化象"),
    (549011, "假从"), (549014, "假化"), (549017, "顺局"), (549020, "反局"),
    (549023, "战局"), (549026, "合局"), (549028, "君象"), (549030, "臣象"),
    (549033, "母象"), (549036, "子象"), (549039, "性情"), (549042, "疾病"),
    (549045, "出身"), (549047, "地位"), (549049, "岁运"), (549051, "贞元"),
]

DISTILL_PROMPT = (
    "你是八字命理知识工程师。从以下古文段落中提取结构化命理规则，输出JSON数组。\n"
    "每条规则格式：\n"
    '{{"id":"dts_{ch}_{seq:02d}","category":"天干|地支|五行|十神|格局|用神|大运|流年|六亲|性情|疾病|其他","subject":"主体","condition":"条件","rule":"白话规则(<=100字)","original_text":"古文引用(<=50字)","source_book":"滴天髓","source_chapter":"{ch}"}}\n\n'
    "古文（滴天髓·{ch}）：\n{text}\n\n"
    "注意：只提取有明确命理含义的规则，不提取序言议论。无规则则返回[]。只输出JSON数组。"
)

MCQ_PROMPT = (
    "你是八字命理考试出题专家。根据以下规则生成四选一选择题，每条规则一题。\n"
    "输出JSON数组，每题格式：\n"
    '{{"id":"dts_{ch}_mcq_{seq:02d}","question":"题干(含命理背景)","options":{{"A":"...","B":"...","C":"...","D":"..."}},"answer":"正确字母","explanation":"解析","source_rule_id":"对应规则ID","difficulty":"基础|中级|高级","category":"天干|地支|五行|十神|格局|用神|其他"}}\n\n'
    "规则：\n{rules_json}\n\n只输出JSON数组。"
)


def fetch_chapter(url_id):
    url = f"https://m.guoxuemeng.com/guoxue/{url_id}.html"
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.encoding = "utf-8"
    html = r.text
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    start = text.find("作者：")
    if start >= 0:
        text = text[start:]
    end = text.find("相关阅读")
    if end >= 0:
        text = text[:end]
    return text.strip()


def distill_chapter(ch_name, text):
    prompt = DISTILL_PROMPT.replace("{ch}", ch_name).replace("{text}", text[:8000])
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


def gen_mcq(ch_name, rules):
    if not rules:
        return []
    rules_json = json.dumps(rules[:15], ensure_ascii=False, indent=2)
    prompt = MCQ_PROMPT.replace("{ch}", ch_name).replace("{rules_json}", rules_json)
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


def extract_cases(text, ch_name):
    cases = []
    pattern = r"([\u7532\u4e59\u4e19\u4e01\u620a\u5df1\u5e9a\u8f9b\u58ec\u7678][\u5b50\u4e11\u5bc5\u536f\u8fb0\u5df3\u5348\u672a\u7533\u9149\u620c\u4ea5]{3}\s+[\u7532\u4e59\u4e19\u4e01\u620a\u5df1\u5e9a\u8f9b\u58ec\u7678][\u5b50\u4e11\u5bc5\u536f\u8fb0\u5df3\u5348\u672a\u7533\u9149\u620c\u4ea5]{3}\s+[\u7532\u4e59\u4e19\u4e01\u620a\u5df1\u5e9a\u8f9b\u58ec\u7678][\u5b50\u4e11\u5bc5\u536f\u8fb0\u5df3\u5348\u672a\u7533\u9149\u620c\u4ea5]{3}\s+[\u7532\u4e59\u4e19\u4e01\u620a\u5df1\u5e9a\u8f9b\u58ec\u7678][\u5b50\u4e11\u5bc5\u536f\u8fb0\u5df3\u5348\u672a\u7533\u9149\u620c\u4ea5]{3})"
    for i, m in enumerate(re.finditer(pattern, text)):
        cases.append({
            "id": f"dts_{ch_name}_case_{i+1}",
            "bazi": m.group(1).strip(),
            "raw_context": text[m.start():m.start()+500][:500],
            "source_book": "滴天髓",
            "source_chapter": ch_name,
        })
    return cases


def main():
    all_rules = []
    all_mcqs = []
    all_cases = []

    progress_file = OUTPUT_DIR / "progress.json"
    if progress_file.exists():
        progress = json.load(open(progress_file, encoding="utf-8"))
        done = set(progress.get("done", []))
    else:
        done = set()

    total = len(CHAPTERS)
    for idx, (url_id, ch_name) in enumerate(CHAPTERS):
        if ch_name in done:
            print(f"[{idx+1}/{total}] {ch_name} - SKIP (already done)")
            continue

        print(f"[{idx+1}/{total}] {ch_name} - fetching...", flush=True)
        try:
            text = fetch_chapter(url_id)
        except Exception as e:
            print(f"  FETCH ERROR: {e}")
            continue

        (OUTPUT_DIR / f"raw_{ch_name}.txt").write_text(text, encoding="utf-8")

        print(f"  distilling rules...", flush=True)
        try:
            rules = distill_chapter(ch_name, text)
        except Exception as e:
            print(f"  DISTILL ERROR: {e}")
            rules = []
        all_rules.extend(rules)

        cases = extract_cases(text, ch_name)
        all_cases.extend(cases)

        print(f"  generating MCQ...", flush=True)
        try:
            mcqs = gen_mcq(ch_name, rules)
        except Exception as e:
            print(f"  MCQ ERROR: {e}")
            mcqs = []
        all_mcqs.extend(mcqs)

        print(f"  rules={len(rules)} cases={len(cases)} mcq={len(mcqs)}", flush=True)

        done.add(ch_name)
        progress = {"done": list(done), "total_rules": len(all_rules),
                    "total_mcqs": len(all_mcqs), "total_cases": len(all_cases)}
        progress_file.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

        time.sleep(0.5)

    with open(OUTPUT_DIR / "all_rules.json", "w", encoding="utf-8") as f:
        json.dump(all_rules, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "all_mcq.jsonl", "w", encoding="utf-8") as f:
        for m in all_mcqs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    with open(OUTPUT_DIR / "all_cases.jsonl", "w", encoding="utf-8") as f:
        for c in all_cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"\n=== DONE ===")
    print(f"Chapters: {len(done)}/{total}")
    print(f"Rules: {len(all_rules)}")
    print(f"MCQ: {len(all_mcqs)}")
    print(f"Cases: {len(all_cases)}")


if __name__ == "__main__":
    main()
