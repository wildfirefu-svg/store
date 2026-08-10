"""
distill_lib.py
Unified, corrected distillation library for classical bazi texts.

Root-cause fixes vs original batch scripts:
  - IDs assigned POST-HOC by code (model never generates IDs) -> no collisions
  - source_rule_id set by code from the rule it was generated from -> always valid
  - Deterministic answer rotation built into MCQ generation -> ~25% per letter
  - Relative paths via Path(__file__) -> portable
  - Provenance manifest (URL/SHA/model config) written per run

Public API:
  distill_chapter(text, book, chapter) -> list[dict]   (rules, no IDs)
  generate_mcq(rules, book, chapter) -> list[dict]     (mcq, source_rule_id set)
  assign_rule_ids(rules, prefix, ch_idx) -> None        (mutates, deterministic)
  rotate_answers(mcqs) -> None                          (mutates, deterministic)
  write_provenance(out_dir, cfg) -> None
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RULE_PROMPT = (
    "你是八字命理知识工程师。从以下古文段落中提取结构化命理规则，输出JSON数组。\n"
    "每条规则格式（id 由系统赋值，你不要填 id 字段）：\n"
    '{"category":"天干|地支|五行|十神|格局|用神|大运|流年|六亲|性情|疾病|其他",'
    '"subject":"主体","condition":"条件","rule":"白话规则(<=100字)",'
    '"original_text":"古文引用(<=50字)","source_book":"__BOOK__","source_chapter":"__CH__"}\n\n'
    "古文（__BOOK__·__CH__）：\n__TEXT__\n\n"
    "注意：只提取有明确命理含义的规则。无规则则返回[]。只输出JSON数组。"
)

MCQ_PROMPT = (
    "你是八字命理考试出题专家。根据以下规则生成四选一选择题，每条规则一题。\n"
    "输出JSON数组，每题格式（id 和 source_rule_id 由系统赋值，你不要填）：\n"
    '{"question":"题干(含命理背景)","options":{"A":"...","B":"...","C":"...","D":"..."},'
    '"answer":"正确字母","explanation":"解析","difficulty":"基础|中级|高级",'
    '"category":"天干|地支|五行|十神|格局|用神|其他"}\n\n'
    "规则：\n__RULES__\n\n只输出JSON数组。"
)


def _get_api_key() -> str:
    env = os.environ.get("DEEPSEEK_API_KEY")
    if env:
        return env
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("DEEPSEEK_API_KEY not found in env or .env")


def _call(prompt: str, timeout: int = 300) -> str:
    from claude_api import call_model_messages_sync_with_meta
    resp, _ = call_model_messages_sync_with_meta(
        [{"role": "user", "content": prompt}],
        provider="deepseek", model="deepseek-v4-flash",
        thinking_mode="disabled", temperature=0.0, timeout=timeout,
    )
    return resp


def _parse_json_array(s: str) -> list[dict]:
    s = s.strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return []


def distill_chapter(text: str, book: str, chapter: str) -> list[dict]:
    prompt = (RULE_PROMPT
              .replace("__BOOK__", book)
              .replace("__CH__", chapter)
              .replace("__TEXT__", text[:8000]))
    rules = _parse_json_array(_call(prompt))
    for r in rules:
        r.setdefault("source_book", book)
        r.setdefault("source_chapter", chapter)
        r.pop("id", None)
    return rules


def assign_rule_ids(rules: list[dict], prefix: str, ch_idx: int) -> None:
    for i, r in enumerate(rules):
        r["id"] = f"{prefix}_{ch_idx:03d}_{i:03d}"


def generate_mcq(rules: list[dict], book: str, chapter: str) -> list[dict]:
    if not rules:
        return []
    rules_payload = [{"id": r["id"], "subject": r.get("subject", ""),
                      "condition": r.get("condition", ""), "rule": r.get("rule", "")}
                     for r in rules[:15]]
    prompt = (MCQ_PROMPT
              .replace("__RULES__", json.dumps(rules_payload, ensure_ascii=False, indent=2)))
    mcqs = _parse_json_array(_call(prompt))
    for m in mcqs:
        m.pop("id", None)
        m.pop("source_rule_id", None)
    return mcqs


def link_mcq_to_rules(mcqs: list[dict], rules: list[dict]) -> list[dict]:
    """Link MCQs to rules positionally (1:1 in generation order)."""
    linked = []
    for i, m in enumerate(mcqs):
        m["source_rule_id"] = rules[i]["id"] if i < len(rules) else (rules[-1]["id"] if rules else "")
        linked.append(m)
    return linked


def rotate_answers(mcqs: list[dict]) -> None:
    """Deterministic rotation: target label cycles A,B,C,D so dist ~= 25% each."""
    for i, m in enumerate(mcqs):
        target = "ABCD"[i % 4]
        cur = m.get("answer", "")
        if cur not in "ABCD" or target == cur:
            continue
        opts = m.get("options", {})
        if target in opts and cur in opts:
            opts[cur], opts[target] = opts[target], opts[cur]
            m["answer"] = target


def assign_mcq_ids(mcqs: list[dict], prefix: str, ch_idx: int, start_seq: int) -> int:
    for m in mcqs:
        m["id"] = f"{prefix}_{ch_idx:03d}_mcq_{start_seq:04d}"
        start_seq += 1
    return start_seq


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_provenance(out_dir: Path, cfg: dict) -> None:
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": cfg.get("model", "deepseek-v4-flash"),
        "provider": "deepseek",
        "thinking_mode": "disabled",
        "temperature": 0.0,
        "source_urls": cfg.get("source_urls", {}),
        "file_shas": {},
    }
    for name in ("all_rules.json", "all_mcq.jsonl"):
        f = out_dir / name
        if f.exists():
            manifest["file_shas"][name] = sha256_file(f)
    (out_dir / "provenance.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
