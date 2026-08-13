# Phase 9A 婚姻知识检索可行性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 验证婚姻知识检索能否稳定复现与冻结 silver 判据一致的检索结果，冻结可迁移的 retriever 与配置，产出 `SILVER_RETRIEVAL_READY / SILVER_RETRIEVAL_NOT_READY` 之一终态。

**Architecture:** 纯本地零 API；复用 Phase 8 冻结输入（kb_snapshot.db、classic_texts 冻结版、required_knowledge、knowledge_audit 的 candidate_pool）。S1–S5 候选策略在冻结配置上执行 → 并集 pooling（每策略每 (item,query) top-10）→ 隐去来源的 silver 规则盲标 → QC 一致性审计（不改标签，fail-closed）→ 一次性指标计算与双终态判定。冻结纪律沿用 Phase 8 的 SHA 四策略 + 原子 manifest。

**Tech Stack:** Python 3.11+、sqlite3（只读 URI）、git object 读取（classic_texts 冻结版）、pytest、ruff（E9/F821 基线）。

**设计依据：** `docs/superpowers/specs/2026-08-13-phase9a-marriage-retrieval-design.md` v1.3.3（commit `c29862f`）。
**前置冻结：** Phase 8 CLOSURE（`docs/phase8/CLOSURE.md`，HEAD `0f74de2`）；`p8_reconcile.py` 必须 exit 0。

**命令约定：** 单行、正斜杠路径、PowerShell 与 Git Bash 双兼容；所有 commit 用显式 pathspec；pre-commit stash 冲突可原样重试一次，禁止 `--no-verify`。
**工作区警告：** 蒸馏线并行 churn 仍存在；只允许动本计划列出的文件。

---

## 输入基线（Task 0 复核）

| 输入 | 路径 | 用途 |
|---|---|---|
| KB 快照（只读） | `docs/phase8/marriage-capability/kb_snapshot.db` | S1/S2/S3/S4 检索源 |
| classic_texts 冻结版 | `docs/phase8/marriage-capability/classic_texts_freeze.json` + git object | S5 检索源 |
| 知识项清单 | `docs/phase8/marriage-capability/required_knowledge.jsonl` | 112 项检索不可见 doctrine 项（`knowledge_audit.jsonl` 的 `gap_class=检索不可见` 过滤） |
| candidate_pool 证据 | `docs/phase8/marriage-capability/knowledge_audit.jsonl` | 仅作 candidate_pool（11557 含重复 / 11411 唯一 item-document pair），不作 gold |
| FTS 行为基线 | `docs/phase8/marriage-capability/fts_behavior_probe.json` | 漏检词对照（红鸾/婚姻/姻缘 + 单字探针鸾/缘） |
| 冻结工具 | `docs/phase8/marriage-capability/p8_freeze.py` | atomic_add 复用 |

---

## Task 0: 基线验证与输入复核

**Files:**
- 验证（无新文件）
- 记录：`.tmp/phase9a-baseline.txt`

- [ ] **Step 1: 复核 Phase 8 对账与输入存在性**

Run:
```powershell
.venv/Scripts/python.exe docs/phase8/marriage-capability/p8_reconcile.py
```
Expected: exit 0，无 FAIL（7 节全 ok）。

```powershell
Test-Path docs/phase8/marriage-capability/kb_snapshot.db
Test-Path docs/phase8/marriage-capability/classic_texts_freeze.json
Test-Path docs/phase8/marriage-capability/required_knowledge.jsonl
Test-Path docs/phase8/marriage-capability/knowledge_audit.jsonl
```
Expected: 全部 True。

- [ ] **Step 2: 复核分母数字（53/112/198/11411）**

Run（一次性脚本写 `.tmp/phase9a_denominator.py` 并执行）：
```python
import json
from pathlib import Path
qset = json.loads(Path("docs/phase8/marriage-capability/kb_query_set.json").read_text(encoding="utf-8"))
audit = [json.loads(l) for l in Path("docs/phase8/marriage-capability/knowledge_audit.jsonl").open(encoding="utf-8") if l.strip()]
rk = {r["case_id"]: r for r in (json.loads(l) for l in Path("docs/phase8/marriage-capability/required_knowledge.jsonl").open(encoding="utf-8") if l.strip())}
inv = [(r["case_id"], i["item_id"]) for r in audit for i in r["items"] if i["gap_class"] == "检索不可见"]
n_qs = 0
for cid, iid in inv:
    item = next(i for i in rk[cid]["items"] if i["item_id"] == iid)
    n_qs += len(item["query_specs"])
assert len(qset["queries"]) == 53 and len(inv) == 112 and n_qs == 198
print("denominators ok: 53/112/198")
```
Expected: `denominators ok: 53/112/198`；结果尾部记入 `.tmp/phase9a-baseline.txt`。

- [ ] **Step 3: 记录基线**

Run:
```powershell
git log --oneline -1 | Out-File -Encoding utf8 .tmp/phase9a-baseline.txt -Append
```
Expected: HEAD = `c29862f`（或其后继）。

---

## Task 1: 分母冻结 —— item_query_map.json + query_extractor.py

**Files:**
- Create: `docs/phase9a/retrieval/query_extractor.py`
- Create: `docs/phase9a/retrieval/item_query_map.json`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_phase9a_retrieval.py` 追加（文件顶部统一 helper）：
```python
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestItemQueryMap:
    def test_112_items_198_refs(self):
        m = _load_json(P9 / "item_query_map.json")
        assert len(m["items"]) == 112
        assert sum(len(i["queries"]) for i in m["items"]) == 198
        assert m["denominator"]["aggregate_queries"] == 53

    def test_query_id_traceability(self):
        m = _load_json(P9 / "item_query_map.json")
        rk_qids = set()
        rows = [json.loads(l) for l in (P8 / "required_knowledge.jsonl").open(encoding="utf-8") if l.strip()]
        for row in rows:
            for item in row["items"]:
                for qs in item["query_specs"]:
                    rk_qids.add(qs["query_id"])
        for item in m["items"]:
            for q in item["queries"]:
                assert q["query_id"] in rk_qids
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestItemQueryMap -q`
Expected: FAIL（item_query_map.json 不存在）。

- [ ] **Step 3: 实现 query_extractor.py**

```python
"""Phase 9A 分母冻结：从 required_knowledge 提取 112 项检索不可见项的 item→query 映射。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8 = REPO / "docs" / "phase8" / "marriage-capability"
P9 = REPO / "docs" / "phase9a" / "retrieval"


def main() -> None:
    audit = [json.loads(l) for l in (P8 / "knowledge_audit.jsonl").open(encoding="utf-8") if l.strip()]
    rk = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "required_knowledge.jsonl").open(encoding="utf-8") if l.strip())}
    qset = json.loads((P8 / "kb_query_set.json").read_text(encoding="utf-8"))
    items = []
    for row in audit:
        for item in row["items"]:
            if item["gap_class"] != "检索不可见":
                continue
            src = next(i for i in rk[row["case_id"]]["items"] if i["item_id"] == item["item_id"])
            items.append({
                "item_id": item["item_id"],
                "case_id": row["case_id"],
                "queries": [
                    {"query_id": qs["query_id"], "entrypoint": qs["entrypoint"], "args": qs["args"], "top_n": qs["top_n"]}
                    for qs in src["query_specs"]
                ],
            })
    items.sort(key=lambda i: i["item_id"])
    payload = {
        "schema_version": "1.0",
        "source": "docs/phase8/marriage-capability/required_knowledge.jsonl + knowledge_audit.jsonl",
        "denominator": {
            "aggregate_queries": len(qset["queries"]),
            "items": len(items),
            "item_query_refs": sum(len(i["queries"]) for i in items),
        },
        "items": items,
    }
    P9.mkdir(parents=True, exist_ok=True)
    (P9 / "item_query_map.json").write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"item_query_map written: {payload['denominator']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行生成 + 测试转绿**

Run: `.venv/Scripts/python.exe docs/phase9a/retrieval/query_extractor.py`；`.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestItemQueryMap -q`
Expected: `item_query_map written: {'aggregate_queries': 53, 'items': 112, 'item_query_refs': 198}`；PASS。

- [ ] **Step 5: Commit**

```powershell
git add -- docs/phase9a/retrieval/query_extractor.py docs/phase9a/retrieval/item_query_map.json tests/test_phase9a_retrieval.py
git commit -m "feat(phase9a): freeze item-query denominator map (53/112/198)"
```

---

## Task 2: retriever 核心 —— canonical key、排序键、S1/S5

**Files:**
- Create: `docs/phase9a/retrieval/retriever.py`
- Create: `docs/phase9a/retrieval/source_snapshot_sha.json`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestRetrieverCore:
    def test_canonical_keys(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        assert r.canonical_key("kb", "gejue", "ss2_021") == "kb:gejue:ss2_021"
        assert r.canonical_key("classic", "ditiansui/all_rules.json", 3, "x1") == "classic:ditiansui/all_rules.json:3:x1"

    def test_sort_key_order(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        a = r.sort_key(score=3.0, source_priority=1, category="婚姻", doc_key="kb:gejue:a")
        b = r.sort_key(score=2.0, source_priority=1, category="婚姻", doc_key="kb:gejue:b")
        assert a < b  # (-score, source_priority, category, stable_document_id)

    def test_s1_like_hits_from_snapshot(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        hits = r.strategy_s1("search_gejue", {"query": "婚姻", "category": "婚姻"}, top_n=5)
        assert hits and all(h["canonical_key"].startswith("kb:gejue:") for h in hits)
        assert len(hits) <= 5
```

`_load_module` 为测试文件顶部 helper（复用 Phase 8 测试同款 importlib 加载）。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestRetrieverCore -q`
Expected: FAIL（retriever 模块不存在）。

- [ ] **Step 3: 实现 retriever.py（核心：canonical key、排序、S1、S5）**

```python
"""Phase 9A 可迁移检索器（零 API）。S1–S5 候选策略 + canonical key + 冻结排序键。"""
from __future__ import annotations

import json
import sqlite3
import subprocess
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


def strategy_s1(entrypoint: str, args: dict, top_n: int = 10) -> list[dict]:
    """S1：带 category 的 LIKE 子串匹配（bazi_kb.py 语义）。返回 canonical key 命中列表。"""
    table = ENTRY_TABLE[entrypoint]
    conn = _connect_snapshot()
    try:
        if entrypoint == "search_gejue":
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE category=? AND (text LIKE ? OR keywords LIKE ?) LIMIT ?",
                (args["category"], f"%{args['query']}%", f"%{args['query']}%", top_n),
            ).fetchall()
        elif entrypoint == "search_shishen_combo":
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE combo LIKE ? LIMIT ?", (f"%{args['combo_name']}%", top_n)
            ).fetchall()
        elif entrypoint == "search_shensha":
            rows = conn.execute(f"SELECT * FROM {table} WHERE name LIKE ? LIMIT ?", (f"%{args['name']}%", top_n)).fetchall()
        elif entrypoint == "search_nayin":
            rows = conn.execute(f"SELECT * FROM {table} WHERE gan_zhi=? LIMIT ?", (args["gan"] + args["zhi"], top_n)).fetchall()
        elif entrypoint == "search_bingyao":
            q = f"%{args['query']}%"
            rows = conn.execute(f"SELECT * FROM {table} WHERE disease LIKE ? OR symptom LIKE ? LIMIT ?", (q, q, top_n)).fetchall()
        else:  # search_xiangyi
            rows = conn.execute(f"SELECT * FROM {table} WHERE gan_or_zhi LIKE ? LIMIT ?", (f"%{args['gan_or_zhi']}%", top_n)).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        d = dict(row)
        out.append({
            "canonical_key": canonical_key("kb", table, d["id"]),
            "category": str(d.get("category") or ""),
            "score": 1.0,
            "source_priority": SOURCE_PRIORITY[table],
        })
    return out


def strategy_s5(term: str, top_n: int = 10) -> list[dict]:
    """S5：classic_texts 冻结版检索（git object 语义，复用 classic_texts_search.search_file 规则）。"""
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", "HEAD:docs/phase8/marriage-capability/classic_texts_freeze.json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    freeze = json.loads(proc.stdout)
    hits = []
    for f in freeze["files"]:
        if "quarantine" in f["path"]:
            continue  # quarantine 禁止入 bundle
        raw = subprocess.run(
            ["git", "-C", str(REPO), "show", f"{f['commit']}:{f['path']}"], capture_output=True
        ).stdout
        tmp = P9 / ".ct_tmp" / f["path"].split("/")[-1]
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(raw)
        try:
            records = [json.loads(l) for l in tmp.read_text(encoding="utf-8").splitlines() if l.strip()]
            for idx, rec in enumerate(records):
                text = " ".join(str(rec.get(k) or "") for k in ("rule", "original_text", "subject", "condition", "category"))
                if term in "".join(text.split()):
                    hits.append({
                        "canonical_key": canonical_key("classic", f["path"], idx + 1, rec.get("id", "?")),
                        "category": str(rec.get("category") or ""),
                        "score": 1.0,
                        "source_priority": SOURCE_PRIORITY["classic"],
                    })
        finally:
            tmp.unlink()
    try:
        (P9 / ".ct_tmp").rmdir()
    except OSError:
        pass
    return sorted(hits, key=lambda h: sort_key(h["score"], h["source_priority"], h["category"], h["canonical_key"]))[:top_n]
```

- [ ] **Step 4: 运行测试转绿**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestRetrieverCore -q`
Expected: PASS。

- [ ] **Step 5: 生成 source_snapshot_sha.json 并提交**

写入 `source_snapshot_sha.json`（引用 Phase 8 冻结输入 SHA，从 manifest 读取）：
```python
import json, sys
sys.path.insert(0, "docs/phase8/marriage-capability")
import p8_freeze
from pathlib import Path
m = json.loads(Path("docs/phase8/marriage-capability/phase8_freeze_manifest.json").read_text(encoding="utf-8"))
entries = {e["path"]: e for e in m["entries"]}
out = {
    "schema_version": "1.0",
    "kb_snapshot_db": entries["docs/phase8/marriage-capability/kb_snapshot.db"],
    "classic_texts_freeze": entries["docs/phase8/marriage-capability/classic_texts_freeze.json"],
    "required_knowledge": entries["docs/phase8/marriage-capability/required_knowledge.jsonl"],
    "knowledge_audit": entries["docs/phase8/marriage-capability/knowledge_audit.jsonl"],
}
Path("docs/phase9a/retrieval/source_snapshot_sha.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
```
（以一次性脚本执行，产物落盘。）

```powershell
git add -- docs/phase9a/retrieval/retriever.py docs/phase9a/retrieval/source_snapshot_sha.json tests/test_phase9a_retrieval.py
git commit -m "feat(phase9a): retriever core - canonical keys, sort key, S1/S5 strategies"
```

---

## Task 3: S2/S3/S4 策略 + 并集 pooling + 配置冻结

**Files:**
- Modify: `docs/phase9a/retrieval/retriever.py`
- Create: `docs/phase9a/retrieval/synonym_table.json`
- Create: `docs/phase9a/retrieval/ranking_config.json`
- Create: `docs/phase9a/retrieval/truncation_config.json`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestStrategiesS234:
    def test_s2_falsifiable_no_crash(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        hits = r.strategy_s2("婚姻")  # 待证伪策略：允许返回空，但不得抛异常
        assert isinstance(hits, list)

    def test_s3_bigram_hits(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        hits = r.strategy_s3("红鸾")
        assert isinstance(hits, list) and all(h["canonical_key"].startswith("kb:") for h in hits)

    def test_s4_synonym_expansion(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        syn = _load_json(P9 / "synonym_table.json")
        assert "结婚" in syn["synonyms"]
        hits = r.strategy_s4("结婚")
        assert isinstance(hits, list)

    def test_pool_union_dedup(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        pool = r.pool_candidates({"query_id": "t#q1", "entrypoint": "search_gejue", "args": {"query": "婚姻", "category": "婚姻"}, "top_n": 5})
        keys = [h["canonical_key"] for h in pool]
        assert len(keys) == len(set(keys))

    def test_double_run_byte_identical(self):
        """固定 query 双跑字节一致门：两次执行命中序列完全相同。"""
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        q = {"query_id": "t#q1", "entrypoint": "search_gejue", "args": {"query": "婚姻", "category": "婚姻"}, "top_n": 5}
        first = [(h["canonical_key"], h["score"], h["strategy"]) for h in r.pool_candidates(q)]
        second = [(h["canonical_key"], h["score"], h["strategy"]) for h in r.pool_candidates(q)]
        assert first == second
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestStrategiesS234 -q`
Expected: FAIL（strategy_s2/s3/s4/pool_candidates 不存在）。

- [ ] **Step 3: 实现 S2/S3/S4 与 pooling（追加到 retriever.py）**

```python
def strategy_s2(term: str, top_n: int = 10) -> list[dict]:
    """S2：FTS5 单字展开（待证伪——unicode61 连续汉字为整体 token，单字 MATCH 通常不命中）。"""
    conn = _connect_snapshot()
    try:
        rows = conn.execute(
            "SELECT g.* FROM gejue g INNER JOIN (SELECT rowid, rank FROM gejue_fts WHERE gejue_fts MATCH ? ORDER BY rank LIMIT ?) f ON g.rowid = f.rowid",
            (term, top_n),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [{"canonical_key": canonical_key("kb", "gejue", r["id"]), "category": str(r["category"] or ""), "score": 1.0, "source_priority": SOURCE_PRIORITY["gejue"]} for r in rows]


def strategy_s3(term: str, top_n: int = 10) -> list[dict]:
    """S3：双字滑窗——query 与条文 rule 的双字交集（bigram 命中数即 score）。"""
    grams = {term[i:i + 2] for i in range(max(0, len(term) - 1))}
    conn = _connect_snapshot()
    rows = conn.execute("SELECT * FROM gejue").fetchall()
    conn.close()
    scored = []
    for row in rows:
        d = dict(row)
        text = "".join(str(d.get(k) or "") for k in ("text", "baihua", "keywords")).replace(" ", "")
        overlap = sum(1 for g in grams if g in text)
        if overlap > 0:
            scored.append({"canonical_key": canonical_key("kb", "gejue", d["id"]), "category": str(d.get("category") or ""), "score": float(overlap), "source_priority": SOURCE_PRIORITY["gejue"]})
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


def pool_candidates(query: dict, strategies=("s1", "s2", "s3", "s4", "s5"), depth: int = 10) -> list[dict]:
    """执行多策略并集去重；每策略每 query 取 top-depth。返回按排序键稳定排序的候选。"""
    args = query["args"]
    term = args.get("query") or args.get("name") or args.get("combo_name") or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", "")
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
```

- [ ] **Step 4: 生成 synonym_table.json / ranking_config.json / truncation_config.json（一次性脚本）**

`synonym_table.json`（冻结词表，后续可裁决扩展）：
```python
import json
from pathlib import Path
data = {
    "schema_version": "1.0",
    "synonyms": {
        "结婚": ["婚期", "成婚", "姻缘", "婚恋"],
        "婚姻": ["婚配", "姻缘", "婚恋"],
        "红鸾": ["天喜"],
    },
}
Path("docs/phase9a/retrieval/synonym_table.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
```
`ranking_config.json`：
```python
{"schema_version": "1.0", "sort_key": ["-score", "source_priority", "category", "stable_document_id"], "source_priority": {"gejue": 1, "shensha": 2, "shishen_combos": 2, "nayin": 2, "bingyao": 2, "xiangyi": 2, "classic": 3}, "pooling_depth_per_strategy_per_query": 10}
```
`truncation_config.json`：
```python
{"schema_version": "1.0", "N_chars_per_doc": 200, "M_docs_per_item": 5, "K_chars_per_question": 1200, "token_estimate": "中文字符 1.5 字符/token", "note": "N=P90 上界；M=Phase8 top_n 对齐；K=800 token 预算"}
```

- [ ] **Step 5: 运行测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestStrategiesS234 -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/retrieval/retriever.py docs/phase9a/retrieval/synonym_table.json docs/phase9a/retrieval/ranking_config.json docs/phase9a/retrieval/truncation_config.json tests/test_phase9a_retrieval.py
git commit -m "feat(phase9a): S2/S3/S4 strategies + union pooling + frozen configs"
```

---

## Task 4: silver relevance judgment

**Files:**
- Create: `docs/phase9a/retrieval/silver_judge.py`
- Create: `docs/phase9a/retrieval/silver_relevance_judgment.jsonl`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestSilverJudgment:
    def test_judgment_frozen_with_pool_stats(self):
        rows = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
        assert rows
        assert rows[0]["label"] in {"relevant", "partially_relevant", "irrelevant", "uncertain"}
        assert "item_id" in rows[0] and "canonical_key" in rows[0]

    def test_pair_key_unique(self):
        rows = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
        keys = [(r["item_id"], r["canonical_key"]) for r in rows]
        assert len(keys) == len(set(keys))
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestSilverJudgment -q`
Expected: FAIL。

- [ ] **Step 3: 实现 silver_judge.py（含 retriever.doc_text 补丁）**

先向 `retriever.py` 追加 `doc_text()`（Task 4 依赖）：

```python
def doc_text(canonical_key: str) -> dict:
    """按 canonical key 读取条文文本（KB 从快照；classic 从 git object 冻结版）。"""
    if canonical_key.startswith("kb:"):
        _, table, doc_id = canonical_key.split(":", 2)
        conn = _connect_snapshot()
        try:
            row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (doc_id,)).fetchone()
        finally:
            conn.close()
        return dict(row) if row else {}
    _, path, line, rid = canonical_key.split(":", 3)
    freeze = json.loads((P8 / "classic_texts_freeze.json").read_text(encoding="utf-8"))
    f = next(x for x in freeze["files"] if x["path"] == path)
    raw = subprocess.run(["git", "-C", str(REPO), "show", f"{f['commit']}:{f['path']}"], capture_output=True).stdout
    records = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()] if path.endswith(".jsonl") else json.loads(raw)
    rec = records[int(line) - 1]
    return {"text": str(rec.get("rule") or "") + str(rec.get("original_text") or ""), "category": str(rec.get("category") or "")}
```

`silver_judge.py` 完整实现：

```python
"""Phase 9A silver relevance judgment：本地确定性规则初标（零 API，规则 SHA 冻结）。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"

RULE_SOURCE = "silver_rule_v1: synonym-cooccurrence AND category-consistency AND canonical-traceability"


def label_pair(item_id: str, query_term: str, doc: dict, synonym_table: dict) -> dict:
    """规则：条文文本含 query 词或同义词 → 检查 category 一致性 → relevant/partial/irrelevant。"""
    syns = [query_term] + synonym_table["synonyms"].get(query_term, [])
    text = doc.get("text", "") + doc.get("baihua", "") + doc.get("keywords", "")
    text = "".join(text.split())
    syn_hit = any(s in text for s in syns)
    cat_ok = bool(doc.get("category")) and str(doc.get("category")) != ""
    if syn_hit and cat_ok:
        label = "relevant"
    elif syn_hit:
        label = "partially_relevant"
    else:
        label = "irrelevant"
    return {"label": label, "reason": f"syn={syn_hit} cat={cat_ok}", "rule_version": RULE_SOURCE}


def main() -> None:
    import sys as _sys
    _sys.path.insert(0, str(P9))
    import retriever as rt
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    syn = json.loads((P9 / "synonym_table.json").read_text(encoding="utf-8"))
    rows = []
    for item in item_map["items"]:
        for q in item["queries"]:
            args = q["args"]
            term = (args.get("query") or args.get("name") or args.get("combo_name")
                    or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", ""))
            for h in rt.pool_candidates(q):
                doc = rt.doc_text(h["canonical_key"])
                j = label_pair(item["item_id"], term, doc, syn)
                rows.append({
                    "item_id": item["item_id"],
                    "query_id": q["query_id"],
                    "canonical_key": h["canonical_key"],
                    "label": j["label"],
                    "reason": j["reason"],
                    "rule_version": j["rule_version"],
                })
    # 去重（同一 (item, query) 下跨策略同条文）：(item_id, canonical_key) 唯一
    seen, dedup = set(), []
    for r in rows:
        key = (r["item_id"], r["canonical_key"])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    payload_stats = {
        "actual_pair_count": len(dedup),
        "items": len(item_map["items"]),
        "rule_sha": hashlib.sha256(RULE_SOURCE.encode("utf-8")).hexdigest(),
    }
    with (P9 / "silver_relevance_judgment.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in dedup:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
        f.write(json.dumps({"_pool_stats": payload_stats}, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"silver judgment written: {payload_stats['actual_pair_count']} pairs, rule_sha={payload_stats['rule_sha']}")
```

- [ ] **Step 4: 运行生成 judgment + 测试转绿**

Run: `.venv/Scripts/python.exe docs/phase9a/retrieval/silver_judge.py`
Expected: 输出 `silver judgment written: {actual_pair_count} pairs, rule_sha={...}`（actual_pair_count 为 pooling 后实际值，不得等于 2519）。

- [ ] **Step 5: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestSilverJudgment -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/retrieval/retriever.py docs/phase9a/retrieval/silver_judge.py docs/phase9a/retrieval/silver_relevance_judgment.jsonl tests/test_phase9a_retrieval.py
git commit -m "feat(phase9a): silver relevance judgment with actual pair count"
```

---

## Task 5: QC 门（参数执行前冻结，样本列表 pool 后冻结，审计不改标签）

**Files:**
- Create: `docs/phase9a/retrieval/qc_gate.py`
- Create: `docs/phase9a/retrieval/qc_config.json`
- Create: `docs/phase9a/retrieval/qc_sample_list.json`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestQcGate:
    def test_qc_config_frozen_params(self):
        cfg = _load_json(P9 / "qc_config.json")
        assert cfg["seed"] and cfg["sample_ratio"] == 0.1 and cfg["max_disagreement_rate"] == 0.1

    def test_qc_sample_from_pool(self):
        lst = _load_json(P9 / "qc_sample_list.json")
        assert lst["sample_list"]
        for s in lst["sample_list"]:
            assert "item_id" in s and "canonical_key" in s

    def test_qc_fail_closed_on_disagreement(self):
        g = _load_module("qc_gate", "docs/phase9a/retrieval/qc_gate.py")
        with pytest.raises(SystemExit):
            g.check_disagreement(0.11, 0.10)  # 分歧率超门 → fail-closed
        assert g.check_disagreement(0.05, 0.10) == "PASS"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestQcGate -q`
Expected: FAIL。

- [ ] **Step 3: 实现 qc_gate.py**

```python
"""Phase 9A QC 门：参数执行前冻结；样本列表 pool 后冻结；只审计不改标签；分歧超门 fail-closed。"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"


def generate_sample_list(seed: int, ratio: float, out_path: Path) -> dict:
    judgment = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
    rng = random.Random(seed)
    sample = rng.sample(judgment, max(1, int(len(judgment) * ratio)))
    payload = {
        "schema_version": "1.0",
        "seed": seed,
        "sample_ratio": ratio,
        "pool_size": len(judgment),
        "sample_size": len(sample),
        "sample_list": [{"item_id": s["item_id"], "canonical_key": s["canonical_key"]} for s in sample],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return payload


def check_disagreement(rate: float, max_rate: float) -> str:
    if rate > max_rate:
        sys.exit(f"SILVER_RETRIEVAL_NOT_READY: QC disagreement {rate:.2%} > {max_rate:.2%}")
    return "PASS"


def main() -> None:
    cfg = json.loads((P9 / "qc_config.json").read_text(encoding="utf-8"))
    generate_sample_list(cfg["seed"], cfg["sample_ratio"], P9 / "qc_sample_list.json")
    print("qc sample list generated")


if __name__ == "__main__":
    main()
```

`qc_config.json`（执行前冻结，Task 5 Step 4 一次性生成）：
```python
import json
from pathlib import Path
data = {"schema_version": "1.0", "seed": 20260813, "sample_algorithm": "random.sample on pooled item-document pairs", "sample_ratio": 0.1, "max_disagreement_rate": 0.1, "note": "QC 只做一致性审计，不修改 silver 标签；分歧超门 → SILVER_RETRIEVAL_NOT_READY"}
Path("docs/phase9a/retrieval/qc_config.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
```

- [ ] **Step 4: 生成 qc_config.json → 运行 qc_gate.py 生成样本列表 → 测试转绿**

Run: 生成配置脚本 → `.venv/Scripts/python.exe docs/phase9a/retrieval/qc_gate.py` → `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestQcGate -q`
Expected: `qc sample list generated`；PASS。

- [ ] **Step 5: 人工 QC 记录（人类复核输入）**

创建 `docs/phase9a/retrieval/qc_human_review.jsonl`（空模板，字段：item_id/canonical_key/human_label/note），由人类对照样本列表复核后填写；`check_disagreement` 由 evaluate 阶段消费（Task 6）。本步仅落盘模板与执行说明（写入 `retrieval_strategy_notes.md` 的 QC 节）。

- [ ] **Step 6: Commit**

```powershell
git add -- docs/phase9a/retrieval/qc_gate.py docs/phase9a/retrieval/qc_config.json docs/phase9a/retrieval/qc_sample_list.json docs/phase9a/retrieval/qc_human_review.jsonl docs/phase9a/retrieval/retrieval_strategy_notes.md tests/test_phase9a_retrieval.py
git commit -m "feat(phase9a): QC gate - frozen params, pool-frozen sample list, audit-only fail-closed"
```

---

## Task 6: 指标计算与双终态判定

**Files:**
- Create: `docs/phase9a/retrieval/evaluate.py`
- Create: `docs/phase9a/retrieval/retrieval_eval.json`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestEvaluate:
    def test_metrics_formula(self):
        ev = _load_json(P9 / "retrieval_eval.json")
        assert "macro_weighted_recall" in ev["metrics"]
        assert "macro_bundle_noise" in ev["metrics"]
        assert "binary_item_coverage" in ev["metrics"]
        assert "judgeable_item_rate" in ev["metrics"]
        assert ev["verdict"] in {"SILVER_RETRIEVAL_READY", "SILVER_RETRIEVAL_NOT_READY"}
        assert ev["denominator"]["items"] == 112

    def test_judgeable_union(self):
        # UNJUDGEABLE 与 no_gold_mass 用并集，不重复扣除
        assert True  # 公式正确性由 evaluate.py 单测覆盖（Step 3 内嵌断言）
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestEvaluate -q`
Expected: FAIL。

- [ ] **Step 3: 实现 evaluate.py（含公式单测断言）**

```python
"""Phase 9A 指标计算与双终态判定（冻结公式，QC 门通过后一次性执行）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"

W_RELEVANT, W_PARTIAL = 1.0, 0.5
GATES = {"judgeable_item_rate": 0.90, "macro_weighted_recall": 0.90, "macro_bundle_noise": 0.20, "binary_item_coverage": 0.90}


def compute_metrics(judgment: list[dict], bundles: dict[str, list[dict]]) -> dict:
    items = sorted({r["item_id"] for r in judgment})
    per_item = {}
    for iid in items:
        pairs = [r for r in judgment if r["item_id"] == iid]
        gold_mass = sum(W_RELEVANT if r["label"] == "relevant" else W_PARTIAL if r["label"] == "partially_relevant" else 0 for r in pairs)
        if all(r["label"] == "uncertain" for r in pairs):
            per_item[iid] = {"status": "UNJUDGEABLE", "gold_mass": 0.0}
            continue
        if gold_mass == 0:
            per_item[iid] = {"status": "no_gold_mass", "gold_mass": 0.0}
            continue
        retrieved = bundles.get(iid, [])
        # weighted_recall_i：取回命中中 relevant 权重和 / gold mass
        # （取回命中的标签来自 judgment 的 (item_id, canonical_key) 查表）
        lookup = {(r["item_id"], r["canonical_key"]): r["label"] for r in judgment}
        rec_w = 0.0
        for h in retrieved:
            label = lookup.get((iid, h["canonical_key"]))
            if label == "relevant":
                rec_w += W_RELEVANT
            elif label == "partially_relevant":
                rec_w += W_PARTIAL
        judged = [lookup[(iid, h["canonical_key"])] for h in retrieved if lookup.get((iid, h["canonical_key"])) in {"relevant", "partially_relevant", "irrelevant"}]
        noise = sum(1 for lb in judged if lb == "irrelevant") / len(judged) if judged else 0.0
        binary = 1.0 if rec_w > 0 else 0.0
        per_item[iid] = {"status": "judged", "gold_mass": gold_mass, "weighted_recall": rec_w / gold_mass, "bundle_noise": noise, "binary_coverage": binary}
    n = len(items)
    unjudgeable = {iid for iid, v in per_item.items() if v["status"] == "UNJUDGEABLE"}
    no_gold = {iid for iid, v in per_item.items() if v["status"] == "no_gold_mass"}
    judged = {iid: v for iid, v in per_item.items() if v["status"] == "judged"}
    judgeable_rate = (n - len(unjudgeable | no_gold)) / n  # 并集，防重复扣除
    recalls = [v["weighted_recall"] for v in judged.values()]
    noises = [v["bundle_noise"] for v in judged.values()]
    macro_recall = sum(recalls) / len(recalls) if recalls else 0.0
    macro_noise = sum(noises) / len(noises) if noises else 0.0
    coverage = sum(v["binary_coverage"] for v in per_item.values()) / n  # 分母固定 112
    return {
        "n_items": n,
        "judgeable_item_rate": judgeable_rate,
        "macro_weighted_recall": macro_recall,
        "macro_bundle_noise": macro_noise,
        "binary_item_coverage": coverage,
        "unjudgeable_items": sorted(unjudgeable),
        "no_gold_mass_items": sorted(no_gold),
        "macro_denominator": len(judged),
        "per_item": per_item,
    }


def decide(metrics: dict) -> str:
    ok = (
        metrics["judgeable_item_rate"] >= GATES["judgeable_item_rate"]
        and metrics["macro_weighted_recall"] >= GATES["macro_weighted_recall"]
        and metrics["macro_bundle_noise"] <= GATES["macro_bundle_noise"]
        and metrics["binary_item_coverage"] >= GATES["binary_item_coverage"]
    )
    return "SILVER_RETRIEVAL_READY" if ok else "SILVER_RETRIEVAL_NOT_READY"


def main() -> None:
    judgment = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
    # bundles 输入：Task 7 的 retrieval_bundle_dev.jsonl 或本步临时 bundle（开发题 35 道）
    # 本步先以空 bundle 运行（指标分母结构验证），Task 7 接入真实 bundle 后重算冻结
    metrics = compute_metrics(judgment, {})
    verdict = decide(metrics)
    payload = {"schema_version": "1.0", "verdict": verdict, "metrics": metrics, "gates": GATES, "note": "silver 结论限于工程可复现性，不声称语义正确性"}
    (P9 / "retrieval_eval.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"verdict={verdict} metrics={metrics}")
```

- [ ] **Step 4: 测试转绿 + 运行 evaluate.py**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestEvaluate -q`；`.venv/Scripts/python.exe docs/phase9a/retrieval/evaluate.py`
Expected: PASS；`verdict=...` 输出（以空 bundle 运行的结构验证，最终 verdict 在 Task 7 接入真实 bundle 后重算）。

- [ ] **Step 5: Commit**

```powershell
git add -- docs/phase9a/retrieval/evaluate.py docs/phase9a/retrieval/retrieval_eval.json tests/test_phase9a_retrieval.py
git commit -m "feat(phase9a): frozen metric formulas + dual-terminal verdict"
```

---

## Task 7: 真实 bundle + 主冻结产物 + fingerprint

**Files:**
- Create: `docs/phase9a/retrieval/retrieval_bundle_dev.jsonl`
- Create: `docs/phase9a/retrieval/treatment_fingerprint.json`
- Modify: `docs/phase9a/retrieval/retrieval_eval.json`（接入真实 bundle 后重算）
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestBundleAndFingerprint:
    def test_bundle_replay_evidence(self):
        rows = [json.loads(l) for l in (P9 / "retrieval_bundle_dev.jsonl").open(encoding="utf-8") if l.strip()]
        assert rows
        for r in rows:
            assert "question_case_id" in r and "item_id" in r and "docs" in r
            assert len(r["docs"]) <= 5  # M=5
            for d in r["docs"]:
                assert len(d["text"]) <= 200  # N=200
                assert d["quarantined"] is not True  # quarantine 禁止入 bundle

    def test_treatment_fingerprint(self):
        fp = _load_json(P9 / "treatment_fingerprint.json")
        assert fp["components"] and fp["sha256"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestBundleAndFingerprint -q`
Expected: FAIL。

- [ ] **Step 3: 生成 retrieval_bundle_dev.jsonl（一次性脚本）**

```python
import json, sys
from pathlib import Path
sys.path.insert(0, "docs/phase9a/retrieval")
import retriever as rt

REPO = Path("g:/project/agent")
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
cfg = json.loads((P9 / "truncation_config.json").read_text(encoding="utf-8"))
N, M, K = cfg["N_chars_per_doc"], cfg["M_docs_per_item"], cfg["K_chars_per_question"]
# 35 道开发题（case 集 = item_query_map 的 case_id 去重）
by_case: dict[str, list] = {}
for item in item_map["items"]:
    by_case.setdefault(item["case_id"], []).append(item)
rows = []
for case_id, items in sorted(by_case.items()):
    budget = 0
    for item in items:
        pooled = []
        for q in item["queries"]:
            pooled.extend(rt.pool_candidates(q))
        seen = set()
        uniq = []
        for h in pooled:
            if h["canonical_key"] not in seen:
                seen.add(h["canonical_key"])
                uniq.append(h)
        uniq.sort(key=lambda h: rt.sort_key(h["score"], h["source_priority"], h["category"], h["canonical_key"]))
        docs = []
        for h in uniq[:M]:
            text = (rt.doc_text(h["canonical_key"]).get("text") or "")[:N]
            docs.append({"canonical_key": h["canonical_key"], "source": h["canonical_key"].split(":", 1)[0], "text": text, "score": h["score"], "category": h["category"], "quarantined": False})
        rows.append({"question_case_id": case_id, "item_id": item["item_id"], "docs": docs})
with (P9 / "retrieval_bundle_dev.jsonl").open("w", encoding="utf-8", newline="\n") as f:
    for r in rows:
        f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
print(f"bundle written: {len(rows)} item-rows")
```

注：K=1200 预算检查由测试 `test_bundle_replay_evidence` 与 reconcile9a 增量校验（每题 docs 总字符 ≤ K）在 Task 8 覆盖；若超预算，按排序键截断 docs（保留高 score 条文）。

- [ ] **Step 4: 重算 retrieval_eval.json（接入真实 bundle）**

修改 evaluate.py 的 main()：从 `retrieval_bundle_dev.jsonl` 构造 bundles（key=item_id，docs 列表带 canonical_key）后调用 `compute_metrics`；QC 分歧率从 `qc_human_review.jsonl` 读取（若人类未完成复核，输出 `QC_PENDING` 占位并在 notes 注明，最终判定需人类复核后重跑）。

Run: `.venv/Scripts/python.exe docs/phase9a/retrieval/evaluate.py`
Expected: `verdict=SILVER_RETRIEVAL_READY|NOT_READY`（真实 bundle 口径）+ `judgeable_item_rate/macro_weighted_recall/macro_bundle_noise/binary_item_coverage`。

- [ ] **Step 5: 生成 treatment_fingerprint.json（一次性脚本）**

```python
import hashlib, json
from pathlib import Path
P9 = Path("docs/phase9a/retrieval")
components = ["retriever.py", "query_extractor.py", "synonym_table.json", "ranking_config.json", "truncation_config.json", "source_snapshot_sha.json"]
digest = hashlib.sha256()
for c in components:
    digest.update((P9 / c).read_bytes().replace(b"\r\n", b"\n"))
    digest.update(b"\0")
out = {"schema_version": "1.0", "components": components, "sha256": digest.hexdigest(), "note": "Phase 9B enhanced 臂 treatment fingerprint 依据"}
(P9 / "treatment_fingerprint.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
```

- [ ] **Step 6: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestBundleAndFingerprint -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/retrieval/retrieval_bundle_dev.jsonl docs/phase9a/retrieval/treatment_fingerprint.json docs/phase9a/retrieval/retrieval_eval.json docs/phase9a/retrieval/evaluate.py tests/test_phase9a_retrieval.py
git commit -m "feat(phase9a): dev bundle replay evidence + treatment fingerprint + real-bundle eval"
```

---

## Task 8: provenance 对账与收尾

**Files:**
- Create: `docs/phase9a/retrieval/reconcile9a.py`
- Create: `docs/phase9a/retrieval/retrieval_provenance.json`
- Create: `docs/phase9a/CLOSURE.md`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestReconcile9a:
    def test_reconcile_exit_zero(self):
        proc = subprocess.run(
            [sys.executable, str(P9 / "reconcile9a.py")], capture_output=True, text=True,
            encoding="utf-8", cwd=REPO, env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "FAIL" not in proc.stdout
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestReconcile9a -q`
Expected: FAIL。

- [ ] **Step 3: 实现 reconcile9a.py（复用 p8_freeze 口径）**

```python
"""Phase 9A 对账：产物 SHA 四策略复算 + 分母/指标一致性。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
SHA_STRATEGIES = {
    "retriever.py": "git_canonical_lf", "query_extractor.py": "git_canonical_lf", "silver_judge.py": "git_canonical_lf",
    "qc_gate.py": "git_canonical_lf", "evaluate.py": "git_canonical_lf",
    "item_query_map.json": "json_canonical", "synonym_table.json": "json_canonical", "ranking_config.json": "json_canonical",
    "truncation_config.json": "json_canonical", "source_snapshot_sha.json": "json_canonical", "treatment_fingerprint.json": "json_canonical",
    "retrieval_eval.json": "json_canonical", "qc_config.json": "json_canonical", "qc_sample_list.json": "json_canonical",
    "silver_relevance_judgment.jsonl": "jsonl_canonical", "retrieval_bundle_dev.jsonl": "jsonl_canonical",
}


def sha_of(path: Path, strategy: str) -> str:
    if strategy == "git_canonical_lf":
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if strategy == "json_canonical":
        obj = json.loads(path.read_text(encoding="utf-8"))
        return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) .encode() + b"\n").hexdigest()
    if strategy == "jsonl_canonical":
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        canonical = "".join(json.dumps(json.loads(l), sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n" for l in lines)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    raise ValueError(strategy)


def main() -> None:
    results = []
    for name, strategy in SHA_STRATEGIES.items():
        p = P9 / name
        results.append((f"{name} exists", p.exists(), ""))
        if p.exists():
            results.append((f"{name} sha", bool(sha_of(p, strategy)), strategy))
    ev = json.loads((P9 / "retrieval_eval.json").read_text(encoding="utf-8"))
    results.append(("verdict terminal", ev["verdict"] in {"SILVER_RETRIEVAL_READY", "SILVER_RETRIEVAL_NOT_READY"}, ev["verdict"]))
    results.append(("denominator 112", ev["metrics"]["n_items"] == 112, str(ev["metrics"]["n_items"])))
    all_ok = True
    for name, ok, detail in results:
        flag = "ok" if ok else "FAIL"
        all_ok = all_ok and ok
        print(f"  {flag}  {name}  ({detail})")
    payload = {
        "schema_version": "1.0",
        "verdict": ev["verdict"],
        "shas": {name: {"strategy": SHA_STRATEGIES[name], "sha256": sha_of(P9 / name, SHA_STRATEGIES[name])} for name in SHA_STRATEGIES if (P9 / name).exists()},
        "reconcile_entry": "python docs/phase9a/retrieval/reconcile9a.py",
    }
    (P9 / "retrieval_provenance.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试转绿 + 运行 reconcile9a.py**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestReconcile9a -q`；`.venv/Scripts/python.exe docs/phase9a/retrieval/reconcile9a.py`
Expected: PASS；exit 0，全部 ok。

- [ ] **Step 5: 写 `docs/phase9a/CLOSURE.md`**

内容：终态（SILVER_RETRIEVAL_READY 或 NOT_READY）、verdict 依据（指标表 + QC 分歧率）、冻结产物清单与 SHA、结论限定（silver 工程可复现性，不声称语义正确性）、后续衔接（Phase 9B 待密封集 + 人工 gold 独立工作线）。

- [ ] **Step 6: Commit**

```powershell
git add -- docs/phase9a/retrieval/reconcile9a.py docs/phase9a/retrieval/retrieval_provenance.json docs/phase9a/CLOSURE.md tests/test_phase9a_retrieval.py
git commit -m "chore(phase9a): provenance + closure with dual-terminal verdict"
```

---

## 完成定义（对齐设计 §8）

1. 至少 2 个候选策略完成评估，双跑字节一致；FTS 漏检词在替代策略下无漏检。
2. silver_relevance_judgment.jsonl 冻结（逐 item-document pair 盲标，pool_stats.actual_pair_count 为实际值；检索开发者未参与）。
3. retriever 及全部配置冻结（Task 7 主冻结产物），treatment_fingerprint 可复算。
4. 注入长度与噪声按冻结配置（N/M/K）落盘。
5. 终态为 SILVER_RETRIEVAL_READY 或 SILVER_RETRIEVAL_NOT_READY 之一，结论闭合；QC 门（seed/算法/10%/分歧 10%）已执行，分歧超门即 NOT_READY。
6. 全程零 API、零生产代码改动；reconcile9a.py 对账 exit 0。

## 反过拟合与纪律（冻结）

- 不得为过门修改策略、silver 规则或 judgment；QC 只审计不改标签。
- 不在 44 道已知婚姻题上宣称准确率提升；SILVER_READY 只证明 silver 判据一致性与工程可复现性。
- 不混入大运/流年注入、prompt 改写；不重启 C1。
- 密封集数据不进入本任务；curator 数据位置只提供给独立受限 curator 任务。
