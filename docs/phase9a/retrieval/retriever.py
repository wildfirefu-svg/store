"""Phase 9A 可迁移检索器（零 API）。S1–S5 候选策略 + canonical key + 冻结排序键 + fail-closed。"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8 = REPO / "docs" / "phase8" / "marriage-capability"
P9 = REPO / "docs" / "phase9a" / "retrieval"

SOURCE_PRIORITY = {"gejue": 1, "shensha": 2, "shishen_combos": 2, "nayin": 2, "bingyao": 2, "xiangyi": 2, "classic": 3}
ENTRY_TABLE = {
    "search_gejue": "gejue", "search_shensha": "shensha", "search_shishen_combo": "shishen_combos",
    "search_nayin": "nayin", "search_bingyao": "bingyao", "search_xiangyi": "xiangyi",
}


def canonical_key(source: str, table_or_path: str, line_or_id, record_id=None) -> str:
    if source == "kb":
        return f"kb:{table_or_path}:{line_or_id}"
    return f"classic:{table_or_path}:{line_or_id}:{record_id}"


def sort_key(score: float, source_priority: int, category: str, doc_key: str) -> tuple:
    return (-score, source_priority, category, doc_key)


def _connect_snapshot():
    conn = sqlite3.connect((P8 / "kb_snapshot.db").resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_frozen_file(path: str, commit: str) -> bytes:
    """git show 冻结对象；返回码/输出非零即 fail-closed。"""
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path}"], capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        sys.exit(f"FAIL: git show {commit}:{path} rc={proc.returncode}")
    return proc.stdout


def _parse_frozen(rel_path: str, commit: str) -> list[dict]:
    raw = _load_frozen_file(rel_path, commit)
    text = raw.decode("utf-8")
    if rel_path.endswith(".jsonl"):
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    obj = json.loads(text)
    return obj if isinstance(obj, list) else [obj]  # .json 数组 / 单对象兼容


def _kb_text(row: dict) -> str:
    """KB 统一正文提取器：拼接所有非空字段（shensha/nayin 等无 text 字段的表也覆盖）。"""
    return " ".join(str(v) for v in row.values() if v is not None and str(v) != "")


def strategy_s1(entrypoint: str, args: dict, top_n: int = 10) -> list[dict]:
    table = ENTRY_TABLE[entrypoint]
    conn = _connect_snapshot()
    try:
        if entrypoint == "search_gejue":
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE category=? AND (text LIKE ? OR keywords LIKE ?) LIMIT ?",
                (args["category"], f"%{args['query']}%", f"%{args['query']}%", top_n)).fetchall()
        elif entrypoint == "search_shishen_combo":
            rows = conn.execute(f"SELECT * FROM {table} WHERE combo LIKE ? LIMIT ?", (f"%{args['combo_name']}%", top_n)).fetchall()
        elif entrypoint == "search_shensha":
            rows = conn.execute(f"SELECT * FROM {table} WHERE name LIKE ? LIMIT ?", (f"%{args['name']}%", top_n)).fetchall()
        elif entrypoint == "search_nayin":
            rows = conn.execute(f"SELECT * FROM {table} WHERE gan_zhi=? LIMIT ?", (args["gan"] + args["zhi"], top_n)).fetchall()
        elif entrypoint == "search_bingyao":
            q = f"%{args['query']}%"
            rows = conn.execute(f"SELECT * FROM {table} WHERE disease LIKE ? OR symptom LIKE ? LIMIT ?", (q, q, top_n)).fetchall()
        else:
            rows = conn.execute(f"SELECT * FROM {table} WHERE gan_or_zhi LIKE ? LIMIT ?", (f"%{args['gan_or_zhi']}%", top_n)).fetchall()
    finally:
        conn.close()
    return [{"canonical_key": canonical_key("kb", table, d["id"]), "category": str(d.get("category") or ""),
             "score": 1.0, "source_priority": SOURCE_PRIORITY[table]} for d in (dict(r) for r in rows)]


def strategy_s2(term: str, top_n: int = 10) -> list[dict]:
    """S2：FTS5 单字展开（待证伪——unicode61 连续汉字为整体 token，单字 MATCH 通常不命中）。"""
    conn = _connect_snapshot()
    try:
        rows = conn.execute(
            "SELECT g.* FROM gejue g INNER JOIN (SELECT rowid, rank FROM gejue_fts WHERE gejue_fts MATCH ? ORDER BY rank LIMIT ?) f ON g.rowid = f.rowid",
            (term, top_n)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [{"canonical_key": canonical_key("kb", "gejue", d["id"]), "category": str(d.get("category") or ""),
             "score": 1.0, "source_priority": SOURCE_PRIORITY["gejue"]} for d in (dict(r) for r in rows)]


def strategy_s3(term: str, top_n: int = 10) -> list[dict]:
    """S3：双字滑窗——query 与条文文本的双字交集（bigram 命中数即 score）。"""
    grams = {term[i:i + 2] for i in range(max(0, len(term) - 1))}
    conn = _connect_snapshot()
    rows = [dict(r) for r in conn.execute("SELECT * FROM gejue").fetchall()]
    conn.close()
    scored = []
    for d in rows:
        text = _kb_text(d).replace(" ", "")
        overlap = sum(1 for g in grams if g in text)
        if overlap > 0:
            scored.append({"canonical_key": canonical_key("kb", "gejue", d["id"]), "category": str(d.get("category") or ""),
                           "score": float(overlap), "source_priority": SOURCE_PRIORITY["gejue"]})
    scored.sort(key=lambda h: sort_key(h["score"], h["source_priority"], h["category"], h["canonical_key"]))
    return scored[:top_n]


def strategy_s4(term: str, top_n: int = 10) -> list[dict]:
    """S4：同义词扩展后组合 S1 并查（synonym_table.json 冻结词表）。"""
    syn = json.loads((P9 / "synonym_table.json").read_text(encoding="utf-8"))
    terms = [term] + syn["synonyms"].get(term, [])
    hits, seen = [], set()
    for t in terms:
        for h in strategy_s1("search_gejue", {"query": t, "category": "婚姻"}, top_n=top_n):
            if h["canonical_key"] not in seen:
                seen.add(h["canonical_key"])
                hits.append(h)
    hits.sort(key=lambda h: sort_key(h["score"], h["source_priority"], h["category"], h["canonical_key"]))
    return hits[:top_n]


def _frozen_files() -> list[dict]:
    freeze = json.loads((P8 / "classic_texts_freeze.json").read_text(encoding="utf-8"))
    return [f for f in freeze["files"] if "quarantine" not in f["path"]]


def strategy_s5(term: str, top_n: int = 10) -> list[dict]:
    """S5：classic_texts 冻结版检索；.json/.jsonl 分支解析；quarantine 排除；git show fail-closed。"""
    hits = []
    for f in _frozen_files():
        for idx, rec in enumerate(_parse_frozen(f["path"], f["commit"])):
            if not isinstance(rec, dict):
                sys.exit(f"FAIL: non-dict record in {f['path']} line {idx + 1}")  # fail-closed，不静默跳过
            text = "".join(str(rec.get(k) or "") for k in ("rule", "original_text", "subject", "condition", "category")).replace(" ", "")
            if term and term in text:
                hits.append({"canonical_key": canonical_key("classic", f["path"], idx + 1, rec.get("id", "?")),
                             "category": str(rec.get("category") or ""), "score": 1.0,
                             "source_priority": SOURCE_PRIORITY["classic"]})
    hits.sort(key=lambda h: sort_key(h["score"], h["source_priority"], h["category"], h["canonical_key"]))
    return hits[:top_n]


def doc_text(canonical_key: str) -> dict:
    """按 canonical key 读取条文文本（KB 全字段拼接；classic 从 git object 冻结版）。"""
    if canonical_key.startswith("kb:"):
        _, table, doc_id = canonical_key.split(":", 2)
        conn = _connect_snapshot()
        try:
            row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (doc_id,)).fetchone()
        finally:
            conn.close()
        d = dict(row) if row else {}
        return {"text": _kb_text(d), "category": str(d.get("category") or ""), "fields": list(d.keys())}
    _, path, line, rid = canonical_key.split(":", 3)
    f = next(x for x in _frozen_files() if x["path"] == path)
    records = _parse_frozen(path, f["commit"])
    rec = records[int(line) - 1]
    return {"text": str(rec.get("rule") or "") + str(rec.get("original_text") or ""),
            "category": str(rec.get("category") or ""), "fields": list(rec.keys())}


def pool_candidates(query: dict, strategies=("s1", "s2", "s3", "s4", "s5"), depth: int = 10) -> list[dict]:
    """执行多策略并集去重；每策略每 query 取 top-depth；按排序键稳定排序。"""
    args = query["args"]
    term = (args.get("query") or args.get("name") or args.get("combo_name")
            or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", ""))
    out, seen = [], set()
    for name in strategies:
        if name == "s1":
            hits = strategy_s1(query["entrypoint"], args, top_n=depth)
        elif name == "s2":
            hits = strategy_s2(term, top_n=depth)
        elif name == "s3":
            hits = strategy_s3(term, top_n=depth)
        elif name == "s4":
            hits = strategy_s4(term, top_n=depth)
        else:
            hits = strategy_s5(term, top_n=depth)
        for h in hits:
            if h["canonical_key"] not in seen:
                seen.add(h["canonical_key"])
                h["strategy"] = name
                out.append(h)
    out.sort(key=lambda h: sort_key(h["score"], h["source_priority"], h["category"], h["canonical_key"]))
    return out
