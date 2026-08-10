"""
Classic Bazi Text Distillation Pipeline
蒸馏三命通会、滴天髓、子平真诠、穷通宝鉴为三层产物：
1. 结构化规则 JSON (供 RAG)
2. 命例 JSONL (供 few-shot)
3. MCQ JSONL (供 benchmark)
"""
import json
import re
import hashlib
import os
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_api import call_model_messages_sync_with_meta

BOOKS = {
    "ditiansui": {
        "name": "滴天髓阐微",
        "author": "京图撰/任铁樵注",
        "source": "https://m.guoxuemeng.com/guoxue/ditiansuichanwei/",
        "chapters": []  # Will be populated
    },
    "sanmingtonghui": {
        "name": "三命通会",
        "author": "万民英",
        "source": "https://www.44414.cn/sanmingtonghui/index.htm",
        "chapters": []
    },
    "zipingzhenquan": {
        "name": "子平真诠",
        "author": "沈孝瞻",
        "source": "https://www.goodu.info/node/2573",
        "chapters": []
    },
    "qiongtongbaojian": {
        "name": "穷通宝鉴",
        "author": "余春台",
        "source": "https://lfglib.cn/text/yilib/208487.html",
        "chapters": []
    },
}

DISTILL_PROMPT = """你是一位八字命理专家和知识工程师。请从以下古文段落中提取结构化的命理规则。

古文段落（来自《{book}》{chapter}）：

{text}

请提取所有可形式化的命理规则，输出 JSON 数组。每条规则的格式：

{{
  "id": "{book}_{chapter}_{seq}",
  "category": "天干|地支|五行|十神|格局|用神|大运|流年|六亲|性情|疾病|其他",
  "subject": "规则主体（如：甲木、丙火、寅申冲、伤官见官）",
  "condition": "适用条件（如：生于春月、柱中无水、日主衰弱）",
  "rule": "规则内容（白话文描述）",
  "original_text": "对应古文原文（简短引用）",
  "source_book": "{book}",
  "source_chapter": "{chapter}"
}}

注意：
- 只提取有明确命理含义的规则，不提取序言或议论
- original_text 引用原文关键句，不超过 50 字
- rule 用现代白话文描述，不超过 100 字
- 如果段落中没有可提取的规则，返回空数组 []

只输出 JSON 数组，不要其他文字。"""

MCQ_PROMPT = """你是一位八字命理考试出题专家。请根据以下命理规则生成选择题。

规则列表：
{rules_json}

请为每条规则生成一道四选一选择题。输出 JSON 数组，每题格式：

{{
  "id": "{book}_{chapter}_mcq_{seq}",
  "question": "题干（含必要命理背景）",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
  "answer": "正确选项字母",
  "explanation": "答案解析（引用规则）",
  "source_rule_id": "对应规则ID",
  "difficulty": "基础|中级|高级",
  "category": "天干|地支|五行|十神|格局|用神|其他"
}}

注意：
- 干扰项必须是合理的命理表述，不能是明显错误
- 题干要包含足够的上下文信息
- 只输出 JSON 数组，不要其他文字。"""


def distill_chapter(book: str, chapter: str, text: str) -> list[dict]:
    """从单个章节文本中提取结构化规则"""
    prompt = DISTILL_PROMPT.replace("{book}", book).replace("{chapter}", chapter).replace("{text}", text[:8000])
    resp, meta = call_model_messages_sync_with_meta(
        [{"role": "user", "content": prompt}],
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_mode="disabled",
        temperature=0.0,
        timeout=300,
    )
    try:
        rules = json.loads(resp.strip())
        if not isinstance(rules, list):
            return []
        return rules
    except (json.JSONDecodeError, ValueError):
        match = re.search(r'\[.*\]', resp, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
        return []


def generate_mcq(book: str, chapter: str, rules: list[dict]) -> list[dict]:
    """从规则列表生成 MCQ"""
    if not rules:
        return []
    rules_json = json.dumps(rules[:10], ensure_ascii=False, indent=2)
    prompt = MCQ_PROMPT.replace("{book}", book).replace("{chapter}", chapter).replace("{rules_json}", rules_json)
    resp, meta = call_model_messages_sync_with_meta(
        [{"role": "user", "content": prompt}],
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_mode="disabled",
        temperature=0.0,
        timeout=300,
    )
    try:
        mcqs = json.loads(resp.strip())
        if not isinstance(mcqs, list):
            return []
        return mcqs
    except (json.JSONDecodeError, ValueError):
        match = re.search(r'\[.*\]', resp, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
        return []


def extract_cases(text: str, book: str, chapter: str) -> list[dict]:
    """从文本中提取命例（八字排盘+分析）"""
    cases = []
    pattern = r'([\甲乙丙丁戊己庚辛壬癸][\子丑寅卯辰巳午未申酉戌亥]{3}\s+[\甲乙丙丁戊己庚辛壬癸][\子丑寅卯辰巳午未申酉戌亥]{3}\s+[\甲乙丙丁戊己庚辛壬癸][\子丑寅卯辰巳午未申酉戌亥]{3}\s+[\甲乙丙丁戊己庚辛壬癸][\子丑寅卯辰巳午未申酉戌亥]{3})'
    matches = list(re.finditer(pattern, text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else min(start + 1000, len(text))
        analysis = text[start:end].strip()
        cases.append({
            "id": f"{book}_{chapter}_case_{i+1}",
            "bazi": m.group(1).strip(),
            "analysis": analysis[:500],
            "source_book": book,
            "source_chapter": chapter,
        })
    return cases


if __name__ == "__main__":
    output_dir = Path("knowledge_base/classic_texts")
    output_dir.mkdir(parents=True, exist_ok=True)

    tiangan_text = open("knowledge_base/classic_texts/raw_ditiansui_tiangan.txt", encoding="utf-8").read()

    print("=== Step 1: Distill rules ===")
    rules = distill_chapter("滴天髓", "天干", tiangan_text)
    print(f"Extracted {len(rules)} rules")
    for r in rules[:3]:
        print(f"  [{r.get('category')}] {r.get('subject')}: {r.get('rule')[:60]}")

    print("\n=== Step 2: Extract cases ===")
    cases = extract_cases(tiangan_text, "滴天髓", "天干")
    print(f"Extracted {len(cases)} cases")
    for c in cases[:2]:
        print(f"  {c['bazi']} -> {c['analysis'][:60]}")

    print("\n=== Step 3: Generate MCQ ===")
    mcqs = generate_mcq("滴天髓", "天干", rules)
    print(f"Generated {len(mcqs)} MCQs")
    for m in mcqs[:2]:
        print(f"  Q: {m.get('question')[:60]}...")

    rules_path = output_dir / "ditiansui_tiangan_rules.json"
    cases_path = output_dir / "ditiansui_tiangan_cases.jsonl"
    mcq_path = output_dir / "ditiansui_tiangan_mcq.jsonl"

    with open(rules_path, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    with open(cases_path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    with open(mcq_path, "w", encoding="utf-8") as f:
        for m in mcqs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    print(f"\n=== Output ===")
    print(f"Rules: {rules_path} ({len(rules)} items)")
    print(f"Cases: {cases_path} ({len(cases)} items)")
    print(f"MCQ: {mcq_path} ({len(mcqs)} items)")
