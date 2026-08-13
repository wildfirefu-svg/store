# Phase 9A 婚姻知识检索可行性 Implementation Plan（v2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 验证婚姻知识检索能否稳定复现与冻结 silver 判据一致的检索结果，冻结可迁移的 retriever 与配置，产出 `SILVER_RETRIEVAL_READY / SILVER_RETRIEVAL_NOT_READY` 之一终态（`HUMAN_QC_REQUIRED` 为暂停状态，非终态）。

**Architecture:** 纯本地零 API；复用 Phase 8 冻结输入（kb_snapshot.db、classic_texts 冻结版、required_knowledge、knowledge_audit 的 candidate_pool）。执行顺序：**基线与输入 SHA → 冻结 query/全部策略配置/QC 参数/初始 manifest → 实现并全量双跑 S1–S5 → 生成 pair pool 与 summary → silver 标注 → pool 后冻结 QC 样本 → 暂停等待完整人工 QC → QC fail-closed → 真实 bundle + 每策略/union 一次性评测 → 原子 provenance 对账与关闭报告**。每个策略独立评估 + union 评估；正式评测产物只生成一次。

**Tech Stack:** Python 3.11+、sqlite3（只读 URI）、git object 读取（classic_texts 冻结版）、pytest、ruff（E9/F821 基线）。

**设计依据：** `docs/superpowers/specs/2026-08-13-phase9a-marriage-retrieval-design.md` v1.3.3（commit `c29862f`）。
**前置冻结：** Phase 8 CLOSURE（HEAD `0f74de2`）；`p8_reconcile.py` 必须 exit 0。
**命令约定：** PowerShell（本仓库主要 shell）；所有脚本的路径推导基于 `__file__`，可在任意工作目录（含 worktree）执行；commit 用显式 pathspec。
**提交纪律：** 每个 commit 前先 `git status --porcelain` + `git diff --cached --name-only` 核对暂存清单，防止卷入并行蒸馏线 churn；pre-commit stash 冲突原样重试一次，禁止 `--no-verify`。

---

## Task 0: 基线验证与输入 SHA

**Files:**
- 验证（无新文件）
- Create: `docs/phase9a/retrieval/upstream_inputs_sha.json`

- [ ] **Step 1: 复核 Phase 8 对账与输入存在性**

Run:
```powershell
.venv/Scripts/python.exe docs/phase8/marriage-capability/p8_reconcile.py
Test-Path docs/phase8/marriage-capability/kb_snapshot.db
Test-Path docs/phase8/marriage-capability/classic_texts_freeze.json
Test-Path docs/phase8/marriage-capability/required_knowledge.jsonl
Test-Path docs/phase8/marriage-capability/knowledge_audit.jsonl
```
Expected: exit 0 无 FAIL；全部 True。

- [ ] **Step 2: 断言全部分母（含 11,411 pair）**

写 `.tmp/phase9a_denominator.py` 并执行：
```python
import json
from pathlib import Path
P8 = Path("docs/phase8/marriage-capability")
qset = json.loads((P8 / "kb_query_set.json").read_text(encoding="utf-8"))
audit = [json.loads(l) for l in (P8 / "knowledge_audit.jsonl").open(encoding="utf-8") if l.strip()]
rk = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "required_knowledge.jsonl").open(encoding="utf-8") if l.strip())}
inv = [(r["case_id"], i["item_id"]) for r in audit for i in r["items"] if i["gap_class"] == "检索不可见"]
n_qs = sum(len(next(i for i in rk[cid]["items"] if i["item_id"] == iid)["query_specs"]) for cid, iid in inv)
pairs = set()
for r in audit:
    for i in r["items"]:
        if i["gap_class"] != "检索不可见":
            continue
        for q in i["evidence"]["kb_queries"]:
            pairs.update((i["item_id"], q["entrypoint"], h) for h in q["hit_ids"])
        for c in i["evidence"]["classic_queries"]:
            pairs.update((i["item_id"], h.get("file"), h.get("line"), h.get("record_id")) for h in c["hits"])
assert len(qset["queries"]) == 53 and len(inv) == 112 and n_qs == 198 and len(pairs) == 11411, (len(qset["queries"]), len(inv), n_qs, len(pairs))
print("denominators ok: 53/112/198/11411")
```
Expected: `denominators ok: 53/112/198/11411`。

- [ ] **Step 3: 落盘上游输入 SHA（复用 Phase 8 manifest 的 canonical SHA，非 raw bytes）**

写 `.tmp/phase9a_upstream_sha.py` 并执行：
```python
import json
from pathlib import Path
P8 = Path("docs/phase8/marriage-capability")
m = json.loads((P8 / "phase8_freeze_manifest.json").read_text(encoding="utf-8"))
entries = {e["path"]: e for e in m["entries"]}
names = {
    "kb_snapshot_db": "docs/phase8/marriage-capability/kb_snapshot.db",
    "classic_texts_freeze_json": "docs/phase8/marriage-capability/classic_texts_freeze.json",
    "required_knowledge_jsonl": "docs/phase8/marriage-capability/required_knowledge.jsonl",
    "knowledge_audit_jsonl": "docs/phase8/marriage-capability/knowledge_audit.jsonl",
    "kb_query_set_json": "docs/phase8/marriage-capability/kb_query_set.json",
}
out = {"schema_version": "1.0", "source": "phase8_freeze_manifest.json (canonical SHA 复用)",
       "files": {k: {"strategy": entries[v]["strategy"], "sha256": entries[v]["sha256"]} for k, v in names.items()}}
Path("docs/phase9a/retrieval/upstream_inputs_sha.json").write_text(
    json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print("upstream inputs sha written (canonical from Phase 8 manifest)")
```
Expected: `upstream inputs sha written (canonical from Phase 8 manifest)`。

- [ ] **Step 4: Commit**

```powershell
git add -- docs/phase9a/retrieval/upstream_inputs_sha.json
git diff --cached --name-only
git commit -m "feat(phase9a): freeze upstream input SHA baseline"
```

---

## Task 1: 冻结 query 集、全部策略配置、QC 参数与初始 manifest

**Files:**
- Create: `docs/phase9a/retrieval/query_set_frozen.json`
- Create: `docs/phase9a/retrieval/synonym_table.json`
- Create: `docs/phase9a/retrieval/ranking_config.json`
- Create: `docs/phase9a/retrieval/truncation_config.json`
- Create: `docs/phase9a/retrieval/qc_config.json`
- Create: `docs/phase9a/retrieval/manifest.json`（原子冻结，策略执行前）
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

`tests/test_phase9a_retrieval.py`（文件顶部 helper）：
```python
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFrozenConfigs:
    def test_query_set_53_queries(self):
        qs = _load_json(P9 / "query_set_frozen.json")
        assert len(qs["queries"]) == 53
        for q in qs["queries"]:
            assert {"query_id", "entrypoint", "args", "top_n"} <= set(q)

    def test_qc_params_frozen(self):
        cfg = _load_json(P9 / "qc_config.json")
        assert cfg["seed"] and cfg["sample_ratio"] == 0.1
        assert cfg["max_disagreement_rate"] == 0.1
        assert cfg["sampling"] == "stratified_by_item"  # 分层抽样，非平面 random.sample

    def test_truncation_numeric(self):
        cfg = _load_json(P9 / "truncation_config.json")
        assert cfg["N_chars_per_doc"] == 200 and cfg["M_docs_per_item"] == 5 and cfg["K_chars_per_question"] == 1200

    def test_manifest_frozen_before_strategy(self):
        m = _load_json(P9 / "manifest.json")
        assert m["stage"] == "config_frozen"
        for name in ("query_set_frozen", "synonym_table", "ranking_config", "truncation_config", "qc_config", "upstream_inputs_sha"):
            assert name in m["entries"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestFrozenConfigs -q`
Expected: FAIL。

- [ ] **Step 3: 生成冻结配置（一次性脚本）**

写 `.tmp/phase9a_freeze_configs.py` 并执行：
```python
import json, sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
import p8_freeze
REPO = Path(".").resolve()
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9.mkdir(parents=True, exist_ok=True)
qset = json.loads((REPO / "docs/phase8/marriage-capability/kb_query_set.json").read_text(encoding="utf-8"))
json.dump({"schema_version": "1.0", "source": "kb_query_set.json (Phase 8 冻结)", "queries": qset["queries"]},
          (P9 / "query_set_frozen.json").open("w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
json.dump({"schema_version": "1.0", "synonyms": {"结婚": ["婚期", "成婚", "姻缘", "婚恋"], "婚姻": ["婚配", "姻缘", "婚恋"], "红鸾": ["天喜"]}},
          (P9 / "synonym_table.json").open("w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
json.dump({"schema_version": "1.0", "sort_key": ["-score", "source_priority", "category", "stable_document_id"],
           "source_priority": {"gejue": 1, "shensha": 2, "shishen_combos": 2, "nayin": 2, "bingyao": 2, "xiangyi": 2, "classic": 3},
           "pooling_depth_per_strategy_per_query": 10,
           "strategy_selection_rule": "FIXED: union of S1-S5 is the final bundle baseline; per-strategy metrics are diagnostic only, never used to choose the bundle after seeing results"},
          (P9 / "ranking_config.json").open("w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
json.dump({"schema_version": "1.0", "N_chars_per_doc": 200, "M_docs_per_item": 5, "K_chars_per_question": 1200,
           "token_estimate": "中文字符 1.5 字符/token", "note": "N=P90 上界；M=Phase8 top_n 对齐；K=800 token 预算"},
          (P9 / "truncation_config.json").open("w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
json.dump({"schema_version": "1.0", "seed": 20260813, "sampling": "stratified_by_item", "sample_ratio": 0.1,
           "max_disagreement_rate": 0.1, "note": "执行前冻结；样本列表在 pool 生成后冻结；QC 只审计不改标签；分歧超门 → SILVER_RETRIEVAL_NOT_READY；总样本数 = int(pool_size × 0.1)，按 item 比例 floor 分配，余数由 rng 从剩余 pool 补足"},
          (P9 / "qc_config.json").open("w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
print("configs written")
```

- [ ] **Step 4: 新建 phase9a_manifest.py（专用 manifest helper，基于真实 p8_freeze 四策略函数）**

**背景（P0 修正）**：`p8_freeze.atomic_add` 的 entries 是按 path 排序的 **list**、同 path **置换覆盖**、无 stage 字段——与 v2.1 假设的 dict/append-only/stage 不兼容。Phase 9A 专用 helper 以**逻辑名称为键**、实现**真 append-only**（同名已冻结项 SHA 不一致即 fail-closed）与 stage 状态机。

Create: `docs/phase9a/retrieval/phase9a_manifest.py`
```python
"""Phase 9A 专用 manifest helper：逻辑名称为键、真 append-only、stage 状态机。
复用 p8_freeze 四策略 SHA 函数；原子写（tmp → 校验 → os.replace）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import p8_freeze  # docs/phase8/marriage-capability（sys.path 由调用方注入）

STRATEGY_FN = {
    "json_canonical": p8_freeze.json_canonical_sha256,
    "jsonl_canonical": p8_freeze.jsonl_canonical_sha256,
    "raw_bytes": p8_freeze.raw_sha256,
    "git_canonical_lf": p8_freeze.git_canonical_lf_sha256,
}
STAGES = ("config_frozen", "code_frozen", "sealed")


def _load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": "1.0", "stage": None, "entries": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    json.loads(tmp.read_text(encoding="utf-8"))  # 写后校验
    os.replace(tmp, path)


def freeze(manifest_path: Path, entries: dict[str, tuple[Path, str]]) -> dict:
    """append-only 冻结：同名已存在且 SHA 不一致 → fail-closed；一致 → 幂等跳过。"""
    manifest = _load(manifest_path)
    for name, (p, strategy) in entries.items():
        sha = STRATEGY_FN[strategy](p)
        existing = manifest["entries"].get(name)
        if existing is not None and existing["sha256"] != sha:
            sys.exit(f"FAIL: {name} already frozen with different SHA (append-only violated)")
        manifest["entries"][name] = {"path": str(p), "strategy": strategy, "sha256": sha}
    _atomic_write(manifest_path, manifest)
    return manifest


def set_stage(manifest_path: Path, stage: str) -> None:
    if stage not in STAGES:
        sys.exit(f"FAIL: unknown stage {stage}")
    manifest = _load(manifest_path)
    manifest["stage"] = stage
    _atomic_write(manifest_path, manifest)


def verify_frozen(manifest_path: Path, names: list[str]) -> None:
    """生产者首次执行前预检：依赖已冻结且磁盘 SHA == expected，否则 fail-closed。"""
    manifest = _load(manifest_path)
    for name in names:
        entry = manifest["entries"].get(name)
        if entry is None:
            sys.exit(f"FAIL: {name} not frozen before use")
        if STRATEGY_FN[entry["strategy"]](Path(entry["path"])) != entry["sha256"]:
            sys.exit(f"FAIL: {name} SHA drift before use")
```

**测试**（`tests/test_phase9a_retrieval.py` 追加 `TestPhase9aManifest`）：
```python
class TestPhase9aManifest:
    def test_append_only_rejects_change(self, tmp_path):
        sys.path.insert(0, str(P8))
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        f = tmp_path / "a.json"
        f.write_text('{"x": 1}', encoding="utf-8")
        pm.freeze(m, {"a": (f, "json_canonical")})
        f.write_text('{"x": 2}', encoding="utf-8")  # 篡改
        try:
            pm.freeze(m, {"a": (f, "json_canonical")})
            raised = False
        except SystemExit:
            raised = True
        assert raised  # append-only：同名 SHA 变化必须 fail-closed

    def test_idempotent_same_sha(self, tmp_path):
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        f = tmp_path / "a.json"
        f.write_text('{"x": 1}', encoding="utf-8")
        pm.freeze(m, {"a": (f, "json_canonical")})
        pm.freeze(m, {"a": (f, "json_canonical")})  # 幂等：SHA 一致不报错
        assert len(json.loads(m.read_text(encoding="utf-8"))["entries"]) == 1

    def test_verify_frozen_fail_closed(self, tmp_path):
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        pm.set_stage(m, "config_frozen")
        try:
            pm.verify_frozen(m, ["retriever_py"])
            raised = False
        except SystemExit:
            raised = True
        assert raised  # 未冻结即使用 → fail-closed
```

- [ ] **Step 5: 初始化 manifest（config_frozen 阶段，逻辑名称为键）**

写 `.tmp/phase9a_manifest_init.py` 并执行：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm

P9 = Path("docs/phase9a/retrieval")
m = P9 / "manifest.json"
pm.set_stage(m, "config_frozen")
pm.freeze(m, {
    "upstream_inputs_sha": (P9 / "upstream_inputs_sha.json", "json_canonical"),
    "query_set_frozen": (P9 / "query_set_frozen.json", "json_canonical"),
    "synonym_table": (P9 / "synonym_table.json", "json_canonical"),
    "ranking_config": (P9 / "ranking_config.json", "json_canonical"),
    "truncation_config": (P9 / "truncation_config.json", "json_canonical"),
    "qc_config": (P9 / "qc_config.json", "json_canonical"),
    # item_query_map 由 Step 6 生成后再冻结（P0 修订：不得冻结未生成文件）
})
print("manifest initialized at config_frozen:", len(json.loads((m).read_text(encoding="utf-8"))["entries"]), "entries")
```
Expected: `manifest initialized at config_frozen: 6 entries`。

- [ ] **Step 6: 生成 item_query_map.json（分母映射，Task 4 依赖）**

Create: `docs/phase9a/retrieval/query_extractor.py`
```python
"""Phase 9A 分母冻结：从 required_knowledge 提取 112 项检索不可见项的 item→query 映射。"""
from __future__ import annotations

import json
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
            items.append({"item_id": item["item_id"], "case_id": row["case_id"],
                          "queries": [{"query_id": qs["query_id"], "entrypoint": qs["entrypoint"],
                                       "args": qs["args"], "top_n": qs["top_n"]} for qs in src["query_specs"]]})
    items.sort(key=lambda i: i["item_id"])
    payload = {"schema_version": "1.0",
               "source": "docs/phase8/marriage-capability/required_knowledge.jsonl + knowledge_audit.jsonl",
               "denominator": {"aggregate_queries": len(qset["queries"]), "items": len(items),
                                "item_query_refs": sum(len(i["queries"]) for i in items)},
               "items": items}
    P9.mkdir(parents=True, exist_ok=True)
    (P9 / "item_query_map.json").write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n")
    print(f"item_query_map written: {payload['denominator']}")


if __name__ == "__main__":
    main()
```

Run: `.venv/Scripts/python.exe docs/phase9a/retrieval/query_extractor.py`
Expected: `item_query_map written: {'aggregate_queries': 53, 'items': 112, 'item_query_refs': 198}`。

随后立即冻结该条目（P0 修订：生成后立即冻结，供 Task 4+ verify 使用）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
pm.freeze(P9 / "manifest.json", {"item_query_map": (P9 / "item_query_map.json", "json_canonical")})
print("item_query_map frozen; total entries:", len(json.loads((P9 / "manifest.json").read_text(encoding="utf-8"))["entries"]))
```
Expected: `item_query_map frozen; total entries: 7`。

- [ ] **Step 7: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestFrozenConfigs tests/test_phase9a_retrieval.py::TestPhase9aManifest -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/retrieval/phase9a_manifest.py docs/phase9a/retrieval/query_set_frozen.json docs/phase9a/retrieval/synonym_table.json docs/phase9a/retrieval/ranking_config.json docs/phase9a/retrieval/truncation_config.json docs/phase9a/retrieval/qc_config.json docs/phase9a/retrieval/query_extractor.py docs/phase9a/retrieval/item_query_map.json docs/phase9a/retrieval/manifest.json tests/test_phase9a_retrieval.py
git diff --cached --name-only
git commit -m "feat(phase9a): manifest helper (append-only/stage/verify), frozen configs, item-query map"
```

---

## Task 2: retriever 实现（canonical key、排序、S1–S5，含 .json/.jsonl 分支与 fail-closed）

**Files:**
- Create: `docs/phase9a/retrieval/retriever.py`
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
        assert a < b

    def test_s5_parses_json_array(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        hits = r.strategy_s5("婚姻", top_n=5)
        assert isinstance(hits, list)  # .json 数组解析成功即不崩溃（P0-5 修复验证）

    def test_s5_git_show_fail_closed(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        try:
            r._load_frozen_file("docs/phase8/marriage-capability/nonexistent.json", "deadbeef")
            raised = False
        except SystemExit:
            raised = True
        assert raised  # git show 失败必须 fail-closed
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestRetrieverCore -q`
Expected: FAIL。

- [ ] **Step 3: 实现 retriever.py**

```python
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
```

- [ ] **Step 4: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestRetrieverCore -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/retrieval/retriever.py tests/test_phase9a_retrieval.py
git diff --cached --name-only
git commit -m "feat(phase9a): retriever S1-S5 with json/jsonl parsing and fail-closed git show"
```

---

## Task 3: 冻结执行代码（freeze-before-use）→ 全量双跑 S1–S5（53 query）

**Files:**
- Modify: `docs/phase9a/retrieval/manifest.json`（追加执行代码条目）
- Create: `docs/phase9a/retrieval/run_strategies.py`
- Create: `docs/phase9a/retrieval/strategy_outputs.jsonl`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试（含 freeze-before-use 门与 265 唯一对断言）**

```python
class TestFullDoubleRun:
    def test_exec_code_frozen_before_run(self):
        # freeze-before-use 门：策略执行代码必须先入 manifest，否则不允许真实运行
        m = _load_json(P9 / "manifest.json")
        for name in ("retriever_py", "run_strategies_py"):
            assert name in m["entries"], f"{name} not frozen before strategy execution"

    def test_all_53_queries_double_run_byte_identical(self):
        # strategy_outputs.jsonl 为全量 53 query 双跑产物：每行 (query_id, strategy, run1_hits, run2_hits)
        rows = [json.loads(l) for l in (P9 / "strategy_outputs.jsonl").open(encoding="utf-8") if l.strip()]
        qids = {r["query_id"] for r in rows}
        qset = _load_json(P9 / "query_set_frozen.json")
        assert len(qids) == 53
        pairs = {(r["query_id"], r["strategy"]) for r in rows}
        assert len(pairs) == 265  # 53 x 5 唯一 (query_id, strategy)
        assert len(rows) == 265
        for r in rows:
            assert r["run1_hits"] == r["run2_hits"]  # 字节一致（canonical key 序列相同）
        per_strategy = {r["strategy"] for r in rows}
        assert per_strategy == {"s1", "s2", "s3", "s4", "s5"}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestFullDoubleRun -q`
Expected: FAIL。

- [ ] **Step 3: 实现 run_strategies.py**

```python
"""Phase 9A 全量双跑：53 query × S1–S5，每策略独立命中落盘（双跑字节一致门）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retriever as rt

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"


def main() -> None:
    qset = json.loads((P9 / "query_set_frozen.json").read_text(encoding="utf-8"))
    cfg = json.loads((P9 / "ranking_config.json").read_text(encoding="utf-8"))
    depth = cfg["pooling_depth_per_strategy_per_query"]
    rows = []
    for q in qset["queries"]:
        for name in ("s1", "s2", "s3", "s4", "s5"):
            args = q["args"]
            term = (args.get("query") or args.get("name") or args.get("combo_name")
                    or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", ""))
            fn = {"s1": lambda: rt.strategy_s1(q["entrypoint"], args, top_n=depth),
                  "s2": lambda: rt.strategy_s2(term, top_n=depth),
                  "s3": lambda: rt.strategy_s3(term, top_n=depth),
                  "s4": lambda: rt.strategy_s4(term, top_n=depth),
                  "s5": lambda: rt.strategy_s5(term, top_n=depth)}[name]
            run1 = [h["canonical_key"] for h in fn()]
            run2 = [h["canonical_key"] for h in fn()]
            if run1 != run2:
                sys.exit(f"FAIL double-run: {q['query_id']} {name}")
            rows.append({"query_id": q["query_id"], "entrypoint": q["entrypoint"], "strategy": name,
                         "run1_hits": run1, "run2_hits": run2})
    with (P9 / "strategy_outputs.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"strategy outputs written: {len(rows)} rows (53 queries x 5 strategies)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结执行代码（freeze-before-use）→ stage=code_frozen**

写 `.tmp/phase9a_manifest_code.py` 并执行：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm

P9 = Path("docs/phase9a/retrieval")
m = P9 / "manifest.json"
pm.freeze(m, {
    "retriever_py": (P9 / "retriever.py", "git_canonical_lf"),
    "run_strategies_py": (P9 / "run_strategies.py", "git_canonical_lf"),
})
pm.set_stage(m, "code_frozen")
pm.verify_frozen(m, ["retriever_py", "run_strategies_py"])
print("exec code frozen; stage=code_frozen")
```
Expected: `exec code frozen; stage=code_frozen`。

- [ ] **Step 5: 运行全量双跑 → 冻结 strategy_outputs → 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe docs/phase9a/retrieval/run_strategies.py`
Expected: `strategy outputs written: 265 rows (53 queries x 5 strategies)`。

随后立即冻结该产物（P0 修订：生成后立即冻结，供 run_eval verify 使用）：
```python
import sys, json
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
pm.freeze(P9 / "manifest.json", {"strategy_outputs": (P9 / "strategy_outputs.jsonl", "jsonl_canonical")})
print("strategy_outputs frozen")
```
Expected: `strategy_outputs frozen`。

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestFullDoubleRun -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/retrieval/manifest.json docs/phase9a/retrieval/run_strategies.py docs/phase9a/retrieval/strategy_outputs.jsonl tests/test_phase9a_retrieval.py
git diff --cached --name-only
git commit -m "feat(phase9a): freeze exec code then full 53-query double-run, freeze strategy outputs"
```

---

## Task 4: pair pool 生成 + silver 标注 + summary

**Files:**
- Create: `docs/phase9a/retrieval/silver_judge.py`
- Create: `docs/phase9a/retrieval/silver_relevance_judgment.jsonl`（**只含 pair 行**，无 _pool_stats 行）
- Create: `docs/phase9a/retrieval/silver_judgment_summary.json`（pool stats + item summaries + 规则 SHA）
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestSilverJudgment:
    def test_pairs_only_no_metadata_rows(self):
        rows = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
        assert rows and all("item_id" in r and "canonical_key" in r for r in rows)
        keys = [(r["item_id"], r["canonical_key"]) for r in rows]
        assert len(keys) == len(set(keys))

    def test_summary_separate_file(self):
        s = _load_json(P9 / "silver_judgment_summary.json")
        assert "pool_stats" in s and "actual_pair_count" in s["pool_stats"]
        assert "item_summaries" in s and "rule_sha" in s
        assert s["pool_stats"]["actual_pair_count"] == len([json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()])
        assert s["pool_stats"]["actual_pair_count"] != 2519  # 不得用全局文档数代替

    def test_label_enum_closed(self):
        rows = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
        assert {r["label"] for r in rows} <= {"relevant", "partially_relevant", "irrelevant", "uncertain"}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestSilverJudgment -q`
Expected: FAIL。

- [ ] **Step 3: 实现 silver_judge.py（category 一致性修正）**

```python
"""Phase 9A silver relevance judgment：本地确定性规则初标（零 API，规则 SHA 冻结）。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retriever as rt

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"

RULE_SOURCE = "silver_rule_v2: synonym-cooccurrence AND category-consistency(query-arg) AND canonical-traceability"


def label_pair(item_id: str, term: str, query_category: str | None, doc: dict, synonym_table: dict) -> dict:
    """规则：条文文本含 term 或同义词 → 与 query 的 category 参数一致 → relevant/partial/irrelevant。
    category 一致性 = 条文 category == query category 参数（query 无 category 时降级为 partial）。"""
    syns = [term] + synonym_table["synonyms"].get(term, [])
    text = "".join(doc.get("text", "").split())
    syn_hit = any(s and s in text for s in syns)
    cat_ok = bool(query_category) and str(doc.get("category") or "") == str(query_category)
    if syn_hit and cat_ok:
        label = "relevant"
    elif syn_hit:
        label = "partially_relevant"
    else:
        label = "irrelevant"
    return {"label": label, "reason": f"syn={syn_hit} cat_match={cat_ok}", "rule_version": RULE_SOURCE}


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    pm.verify_frozen(P9 / "manifest.json", ["retriever_py", "synonym_table", "query_set_frozen", "item_query_map", "silver_judge_py"])
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    syn = json.loads((P9 / "synonym_table.json").read_text(encoding="utf-8"))
    qset = {q["query_id"]: q for q in json.loads((P9 / "query_set_frozen.json").read_text(encoding="utf-8"))["queries"]}
    # 跨 query 聚合（冻结规则）：同一 (item, doc) 被多个 query 命中时取 max label
    # （relevant > partially_relevant > irrelevant > uncertain），记录全部 contributing query_ids
    RANK = {"relevant": 3, "partially_relevant": 2, "irrelevant": 1, "uncertain": 0}
    agg: dict[tuple, dict] = {}
    for item in item_map["items"]:
        for q in item["queries"]:
            fq = qset[q["query_id"]]
            args = fq["args"]
            term = (args.get("query") or args.get("name") or args.get("combo_name")
                    or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", ""))
            qcat = args.get("category")
            for h in rt.pool_candidates(fq):
                key = (item["item_id"], h["canonical_key"])
                doc = rt.doc_text(h["canonical_key"])
                j = label_pair(item["item_id"], term, qcat, doc, syn)
                cur = agg.get(key)
                if cur is None:
                    agg[key] = {"item_id": item["item_id"], "query_ids": [q["query_id"]], "canonical_key": h["canonical_key"],
                                "label": j["label"], "reason": j["reason"], "rule_version": j["rule_version"]}
                else:
                    if q["query_id"] not in cur["query_ids"]:
                        cur["query_ids"].append(q["query_id"])
                    if RANK[j["label"]] > RANK[cur["label"]]:
                        cur["label"], cur["reason"], cur["rule_version"] = j["label"], j["reason"], j["rule_version"]
    pairs = sorted(agg.values(), key=lambda r: (r["item_id"], r["canonical_key"]))
    with (P9 / "silver_relevance_judgment.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in pairs:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    summaries = {}
    for r in pairs:
        s = summaries.setdefault(r["item_id"], {"relevant": 0, "partially_relevant": 0, "irrelevant": 0, "uncertain": 0})
        s[r["label"]] += 1
    summary = {
        "schema_version": "1.0",
        "pool_stats": {"actual_pair_count": len(pairs), "items": len(item_map["items"]),
                       "rule_sha": hashlib.sha256(RULE_SOURCE.encode("utf-8")).hexdigest(),
                       "cross_query_aggregation": "max label rank, all contributing query_ids recorded"},
        "item_summaries": summaries,
        "rule_source": RULE_SOURCE,
    }
    (P9 / "silver_judgment_summary.json").write_text(
        json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"silver judgment written: {len(pairs)} pairs; summary written")


if __name__ == "__main__":
    main()
```

（注：`item_query_map.json` 由 Task 1 Step 5 的 `query_extractor.py` 生成；judgment 行的 `query_ids` 为跨 query 聚合的 contributing query IDs。）

- [ ] **Step 4: 冻结 silver_judge_py（freeze-before-use）→ 运行生成 judgment + 测试转绿**

写 `.tmp/phase9a_freeze_silver_judge.py` 并执行：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
pm.freeze(P9 / "manifest.json", {"silver_judge_py": (P9 / "silver_judge.py", "git_canonical_lf")})
print("silver_judge_py frozen")
```
Expected: `silver_judge_py frozen`。

Run: `.venv/Scripts/python.exe docs/phase9a/retrieval/silver_judge.py`；`.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestSilverJudgment -q`
Expected: `silver judgment written: {n} pairs; summary written`（main() 内 verify_frozen 预检通过）；PASS。

随后立即冻结 judgment 与 summary（P0 修订：生成后立即冻结，供 qc_gate/run_eval verify 使用）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
pm.freeze(P9 / "manifest.json", {"silver_relevance_judgment": (P9 / "silver_relevance_judgment.jsonl", "jsonl_canonical"),
                                 "silver_judgment_summary": (P9 / "silver_judgment_summary.json", "json_canonical")})
print("judgment + summary frozen")
```
Expected: `judgment + summary frozen`。
```powershell
git add -- docs/phase9a/retrieval/manifest.json docs/phase9a/retrieval/silver_judge.py docs/phase9a/retrieval/silver_relevance_judgment.jsonl docs/phase9a/retrieval/silver_judgment_summary.json tests/test_phase9a_retrieval.py
git diff --cached --name-only
git commit -m "feat(phase9a): silver judgment pairs-only schema + summary (frozen before run)"
```

---

## Task 5: pool 后冻结 QC 样本（分层抽样）

**Files:**
- Create: `docs/phase9a/retrieval/qc_sample_list.json`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestQcSampleList:
    def test_stratified_by_item(self):
        lst = _load_json(P9 / "qc_sample_list.json")
        cfg = _load_json(P9 / "qc_config.json")
        assert lst["seed"] == cfg["seed"] and lst["sample_ratio"] == cfg["sample_ratio"]
        sample = lst["sample_list"]
        assert sample and len(sample) >= 10
        by_item = {}
        for s in sample:
            by_item.setdefault(s["item_id"], 0)
            by_item[s["item_id"]] += 1
        assert len(by_item) >= 10  # 分层：覆盖多个 item，而非平面抽样集中于少数 item
        pairs = [(s["item_id"], s["canonical_key"]) for s in sample]
        assert len(pairs) == len(set(pairs))
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestQcSampleList -q`
Expected: FAIL。

- [ ] **Step 3: 生成样本列表（一次性脚本，写入 qc_gate.py 供复用）**

```python
"""qc_gate.py：分层抽样 + QC 状态机（HUMAN_QC_REQUIRED / fail-closed / 分歧判定）。"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"


def generate_sample_list(seed: int, ratio: float, judgment_path: Path, out_path: Path) -> dict:
    """按 item 分层抽样（冻结算法）：总样本 = int(pool_size × ratio)；
    每 item 按比例 floor 分配，余数由 rng 从剩余 pool 补足，保证总样本数精确。"""
    rows = [json.loads(l) for l in judgment_path.open(encoding="utf-8") if l.strip()]
    rng = random.Random(seed)
    by_item: dict[str, list] = {}
    for r in rows:
        by_item.setdefault(r["item_id"], []).append(r)
    total = max(1, int(len(rows) * ratio))
    sample, remaining = [], list(rows)
    for item_id, group in sorted(by_item.items()):
        k = min(len(group), int(len(group) * ratio))  # floor 分配
        chosen = rng.sample(group, k)
        sample.extend(chosen)
        for c in chosen:
            remaining.remove(c)
    if len(sample) < total:  # 余数：从剩余 pool 补足到精确总样本数
        sample.extend(rng.sample(remaining, min(len(remaining), total - len(sample))))
    payload = {"schema_version": "1.0", "seed": seed, "sample_ratio": ratio,
               "pool_size": len(rows), "sample_size": len(sample),
               "sample_list": [{"item_id": s["item_id"], "canonical_key": s["canonical_key"]} for s in sample]}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return payload


LABEL_ENUM = {"relevant", "partially_relevant", "irrelevant", "uncertain"}


def load_human_review(review_path: Path) -> list[dict]:
    """人类复核记录：字段 item_id/canonical_key/human_label/note；校验一一对应。"""
    if not review_path.exists():
        return []
    return [json.loads(l) for l in review_path.open(encoding="utf-8") if l.strip()]


def validate_human_review_schema(reviews: list[dict]) -> None:
    """字段/枚举/非空校验：human_label 必填且属于冻结枚举；note 非空；缺失即 fail-closed（P0 防空标签绕过）。"""
    for r in reviews:
        if not isinstance(r.get("human_label"), str) or r["human_label"] not in LABEL_ENUM:
            sys.exit(f"FAIL: missing or invalid human_label in {r.get('item_id')} {r.get('canonical_key')}: {r.get('human_label')!r}")
        if not isinstance(r.get("note"), str) or not r["note"].strip():
            sys.exit(f"FAIL: empty note in {r.get('item_id')} {r.get('canonical_key')}")


def validate_review_coverage(sample_list: list[dict], reviews: list[dict]) -> None:
    """复核记录与样本一一对应：无缺失、无重复、无额外 pair。失败即 fail-closed。"""
    expected = {(s["item_id"], s["canonical_key"]) for s in sample_list}
    actual = {(r["item_id"], r["canonical_key"]) for r in reviews}
    missing = expected - actual
    extra = actual - expected
    dup = len(reviews) != len(actual)
    if missing or extra or dup:
        sys.exit(f"HUMAN_QC_REQUIRED: coverage mismatch missing={len(missing)} extra={len(extra)} dup={dup}")


def check_disagreement(reviews: list[dict], judgment_path: Path, max_rate: float, result_path: Path) -> dict:
    """分歧率 = 人类标签与 silver 标签不一致占比；结果原子落盘 qc_result.json（tmp + os.replace）。
    返回 dict（verdict/disagreement_rate）供调用方分支；**不在此 sys.exit**——
    QC_FAIL 正式终态由 run_eval.py 发布（P0 修订：失败分支必须形成完整终态链）。"""
    validate_human_review_schema(reviews)
    silver = {(r["item_id"], r["canonical_key"]): r["label"]
              for r in (json.loads(l) for l in judgment_path.open(encoding="utf-8") if l.strip())}
    n_diff = sum(1 for r in reviews if r["human_label"] != silver[(r["item_id"], r["canonical_key"])])
    rate = n_diff / len(reviews) if reviews else 1.0
    result = {"schema_version": "1.0", "disagreement_rate": rate, "n_reviewed": len(reviews), "n_diff": n_diff,
              "max_disagreement_rate": max_rate,
              "verdict": "PASS" if rate <= max_rate else "SILVER_RETRIEVAL_NOT_READY"}
    tmp = result_path.with_name(result_path.name + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    json.loads(tmp.read_text(encoding="utf-8"))  # 写后校验
    os.replace(tmp, result_path)  # 原子落盘
    return result


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    pm.verify_frozen(P9 / "manifest.json", ["qc_config", "silver_relevance_judgment", "qc_gate_py"])
    cfg = json.loads((P9 / "qc_config.json").read_text(encoding="utf-8"))
    generate_sample_list(cfg["seed"], cfg["sample_ratio"], P9 / "silver_relevance_judgment.jsonl", P9 / "qc_sample_list.json")
    print("qc sample list generated")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 qc_gate_py（freeze-before-use）→ 生成样本列表 + 测试转绿**

写 `.tmp/phase9a_freeze_qc_gate.py` 并执行：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
pm.freeze(P9 / "manifest.json", {"qc_gate_py": (P9 / "qc_gate.py", "git_canonical_lf")})
print("qc_gate_py frozen")
```
Expected: `qc_gate_py frozen`。

Run: `.venv/Scripts/python.exe docs/phase9a/retrieval/qc_gate.py`；`.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestQcSampleList -q`
Expected: `qc sample list generated`（main() 内 verify_frozen 预检通过）；PASS。

随后立即冻结样本列表（P0 修订：生成后立即冻结，供 run_eval verify 使用）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
pm.freeze(P9 / "manifest.json", {"qc_sample_list": (P9 / "qc_sample_list.json", "json_canonical")})
print("qc_sample_list frozen")
```
Expected: `qc_sample_list frozen`。
```powershell
git add -- docs/phase9a/retrieval/manifest.json docs/phase9a/retrieval/qc_gate.py docs/phase9a/retrieval/qc_sample_list.json tests/test_phase9a_retrieval.py
git diff --cached --name-only
git commit -m "feat(phase9a): stratified QC sample list frozen after pooling (frozen before run)"
```

---

## Task 6: 暂停点 HUMAN_QC_REQUIRED（完整人工 QC 复核）

**Files:**
- Create: `docs/phase9a/retrieval/qc_human_review.jsonl`（**零字节文件**，不得含注释行）
- Create: `docs/phase9a/retrieval/qc_human_review_schema.json`（独立 schema 说明）
- Create: `docs/phase9a/retrieval/qc_result.json`（分歧判定结果，由 check_disagreement 原子落盘）
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试**

```python
class TestQcStateMachine:
    def test_pending_review_blocks_eval(self):
        g = _load_module("qc_gate", "docs/phase9a/retrieval/qc_gate.py")
        # 无复核记录 → HUMAN_QC_REQUIRED（阻塞指标计算与终态）
        assert g.qc_state(P9 / "qc_human_review.jsonl", P9 / "qc_sample_list.json") == "HUMAN_QC_REQUIRED"

    def test_review_coverage_fail_closed(self):
        g = _load_module("qc_gate", "docs/phase9a/retrieval/qc_gate.py")
        sample = [{"item_id": "a", "canonical_key": "kb:gejue:1"}]
        reviews = [{"item_id": "a", "canonical_key": "kb:gejue:2", "human_label": "relevant"}]  # 额外 pair
        try:
            g.validate_review_coverage(sample, reviews)
            raised = False
        except SystemExit:
            raised = True
        assert raised
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestQcStateMachine -q`
Expected: FAIL（qc_state 不存在）。

- [ ] **Step 3: 实现 qc_state + 落盘模板（零字节 + 独立 schema）**

向 `qc_gate.py` 追加：
```python
def qc_state(review_path: Path, sample_path: Path) -> str:
    """QC 状态机：无完整复核 → HUMAN_QC_REQUIRED；完整复核后由 evaluate 消费分歧判定。"""
    sample = json.loads(sample_path.read_text(encoding="utf-8"))["sample_list"]
    reviews = load_human_review(review_path)
    if len(reviews) < len(sample):
        return "HUMAN_QC_REQUIRED"
    validate_review_coverage(sample, reviews)
    validate_human_review_schema(reviews)
    return "REVIEWED"
```
落盘 `qc_human_review.jsonl` 为**零字节文件**（JSONL 解析器不允许注释行）；字段 schema 写入独立文件 `qc_human_review_schema.json`：
```json
{"schema_version": "1.0", "file": "qc_human_review.jsonl", "line_fields": ["item_id", "canonical_key", "human_label", "note"], "human_label_enum": ["relevant", "partially_relevant", "irrelevant", "uncertain"], "note_required": true, "rules": ["human_label 必填且属于枚举", "note 必填非空", "pair 与 qc_sample_list 一一对应（无缺失/重复/额外）"]}
```
随后立即冻结零字节模板与 schema（P0 修订：生成后立即冻结，供 run_eval verify 使用）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
pm.freeze(P9 / "manifest.json", {"qc_human_review": (P9 / "qc_human_review.jsonl", "jsonl_canonical"),
                                 "qc_human_review_schema": (P9 / "qc_human_review_schema.json", "json_canonical")})
print("qc_human_review + schema frozen")
```
Expected: `qc_human_review + schema frozen`。
`qc_result.json` 由 Task 7 的 `check_disagreement` 原子生成（返回 dict；分歧超门时 QC_FAIL 正式终态由 run_eval.py 发布，不在此 sys.exit）。

- [ ] **Step 4: 测试转绿 + Commit（此任务为显式暂停点）**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestQcStateMachine -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/retrieval/qc_gate.py docs/phase9a/retrieval/qc_human_review.jsonl docs/phase9a/retrieval/qc_human_review_schema.json tests/test_phase9a_retrieval.py
git diff --cached --name-only
git commit -m "feat(phase9a): HUMAN_QC_REQUIRED state machine, zero-byte template + schema file"
```

**⏸ 暂停点（人工）：** 人类对照 `qc_sample_list.json` 逐条填写 `qc_human_review.jsonl`（human_label ∈ {relevant, partially_relevant, irrelevant, uncertain}）。**未完成前不得执行 Task 7 的评测步骤**；完成后再继续。

---

## Task 7: compute_metrics 纯函数 TDD → 真实 bundle → 一次性正式评测（每策略 + union）

**Files:**
- Create: `docs/phase9a/retrieval/evaluate.py`
- Create: `docs/phase9a/retrieval/retrieval_bundle_dev.jsonl`
- Create: `docs/phase9a/retrieval/retrieval_eval.json`（**只生成一次**）
- Create: `docs/phase9a/retrieval/per_strategy_eval.json`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: compute_metrics 纯函数 TDD（合成 fixture，含集合重叠）**

```python
class TestMetricsPure:
    def test_recall_noise_split_with_overlap(self):
        # 合成 fixture：item X 的 gold 含 2 relevant + 1 partial；策略只取回其中 1 relevant + 1 irrelevant
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        judgment = [
            {"item_id": "x", "canonical_key": "kb:gejue:1", "label": "relevant"},
            {"item_id": "x", "canonical_key": "kb:gejue:2", "label": "relevant"},
            {"item_id": "x", "canonical_key": "kb:gejue:3", "label": "partially_relevant"},
            {"item_id": "x", "canonical_key": "kb:gejue:4", "label": "irrelevant"},
        ]
        items = ["x"]  # 冻结 item 集（来自 item_query_map）
        bundles = {"x": [{"canonical_key": "kb:gejue:1"}, {"canonical_key": "kb:gejue:4"}]}
        m = ev.compute_metrics(judgment, items, bundles)
        assert abs(m["per_item"]["x"]["weighted_recall"] - 1.0 / 2.5) < 1e-9  # 取回 1 relevant / gold 2.5 权重
        assert abs(m["per_item"]["x"]["bundle_noise"] - 0.5) < 1e-9  # 2 条中 1 条 irrelevant
        assert m["binary_item_coverage"] == 1.0  # 分母 = items 数

    def test_fixed_112_denominator_with_missing_item(self):
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        judgment = [{"item_id": "x", "canonical_key": "kb:gejue:1", "label": "relevant"}]
        items = ["x", "y"]  # y 无任何 judgment/bundle → 计未覆盖
        bundles = {"x": [{"canonical_key": "kb:gejue:1"}]}
        m = ev.compute_metrics(judgment, items, bundles)
        assert m["n_items"] == 2 and m["binary_item_coverage"] == 0.5
        assert "y" in m["no_gold_mass_items"]

    def test_judgeable_union_no_double_count(self):
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        # u=全部 uncertain(UNJUDGEABLE)；n=仅 irrelevant(gold mass=0)；x=无 judgment 也无 bundle → 同样 no_gold_mass
        # 并集 = {u, n, x}：judgeable_rate = (3-3)/3 = 0（P0：三项均属并集，非 1/3）
        judgment = [
            {"item_id": "u", "canonical_key": "kb:gejue:1", "label": "uncertain"},
            {"item_id": "n", "canonical_key": "kb:gejue:2", "label": "irrelevant"},
        ]
        items = ["u", "n", "x"]
        m = ev.compute_metrics(judgment, items, {"x": [{"canonical_key": "kb:gejue:3"}]})
        assert m["judgeable_item_rate"] == 0.0  # (3 - |{u,n,x}|) / 3
        assert set(m["no_gold_mass_items"]) == {"n", "x"}
        assert m["unjudgeable_items"] == ["u"]
        assert m["binary_item_coverage"] == 0.0  # 无 judged item

    def test_no_keyerror_on_unjudgeable_summary(self):
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        judgment = [{"item_id": "u", "canonical_key": "kb:gejue:1", "label": "uncertain"}]
        m = ev.compute_metrics(judgment, ["u"], {})
        assert m["binary_item_coverage"] == 0.0  # 不抛 KeyError（P0 修复）
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestMetricsPure -q`
Expected: FAIL。

- [ ] **Step 3: 实现 evaluate.py（固定 112 分母 + 集合严格相等 + 每策略评估）**

```python
"""Phase 9A 指标计算与终态判定（冻结公式；QC 通过后一次性执行；每策略 + union）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"

W_RELEVANT, W_PARTIAL = 1.0, 0.5
GATES = {"judgeable_item_rate": 0.90, "macro_weighted_recall": 0.90, "macro_bundle_noise": 0.20, "binary_item_coverage": 0.90}


def compute_metrics(judgment: list[dict], items: list[str], bundles: dict[str, list[dict]]) -> dict:
    """items 来自冻结 item_query_map（固定 112 分母）；judgment/bundle 集合严格相等校验。"""
    item_set = set(items)
    j_items = {r["item_id"] for r in judgment}
    b_items = set(bundles)
    if j_items - item_set or b_items - item_set:
        sys.exit(f"FAIL: judgment/bundle items outside frozen set {sorted((j_items | b_items) - item_set)}")
    lookup = {(r["item_id"], r["canonical_key"]): r["label"] for r in judgment}
    n = len(items)
    per_item = {}
    for iid in items:
        pairs = [r for r in judgment if r["item_id"] == iid]
        gold_mass = sum(W_RELEVANT if r["label"] == "relevant" else W_PARTIAL if r["label"] == "partially_relevant" else 0 for r in pairs)
        # 所有状态分支显式携带 binary_coverage（P0：防汇总 KeyError）
        if pairs and all(r["label"] == "uncertain" for r in pairs):
            per_item[iid] = {"status": "UNJUDGEABLE", "gold_mass": 0.0, "binary_coverage": 0.0}
            continue
        if gold_mass == 0:
            per_item[iid] = {"status": "no_gold_mass", "gold_mass": 0.0, "binary_coverage": 0.0}
            continue
        retrieved = bundles.get(iid, [])
        rec_w = sum(W_RELEVANT if lookup.get((iid, h["canonical_key"])) == "relevant"
                    else W_PARTIAL if lookup.get((iid, h["canonical_key"])) == "partially_relevant" else 0
                    for h in retrieved)
        judged = [lookup[(iid, h["canonical_key"])] for h in retrieved
                  if lookup.get((iid, h["canonical_key"])) in {"relevant", "partially_relevant", "irrelevant"}]
        noise = sum(1 for lb in judged if lb == "irrelevant") / len(judged) if judged else 0.0
        per_item[iid] = {"status": "judged", "gold_mass": gold_mass, "weighted_recall": rec_w / gold_mass,
                         "bundle_noise": noise, "binary_coverage": 1.0 if rec_w > 0 else 0.0}
    unjudgeable = {iid for iid, v in per_item.items() if v["status"] == "UNJUDGEABLE"}
    no_gold = {iid for iid, v in per_item.items() if v["status"] == "no_gold_mass"}
    judged = {iid: v for iid, v in per_item.items() if v["status"] == "judged"}
    judgeable_rate = (n - len(unjudgeable | no_gold)) / n  # 集合并集，防重复扣除
    recalls = [v["weighted_recall"] for v in judged.values()]
    noises = [v["bundle_noise"] for v in judged.values()]
    return {
        "n_items": n,
        "judgeable_item_rate": judgeable_rate,
        "macro_weighted_recall": sum(recalls) / len(recalls) if recalls else 0.0,
        "macro_bundle_noise": sum(noises) / len(noises) if noises else 0.0,
        "binary_item_coverage": sum(v["binary_coverage"] for v in per_item.values()) / n,  # 分母固定 items 数
        "unjudgeable_items": sorted(unjudgeable),
        "no_gold_mass_items": sorted(no_gold),
        "macro_denominator": len(judged),
        "per_item": per_item,
    }


def decide(metrics: dict) -> str:
    ok = (metrics["judgeable_item_rate"] >= GATES["judgeable_item_rate"]
          and metrics["macro_weighted_recall"] >= GATES["macro_weighted_recall"]
          and metrics["macro_bundle_noise"] <= GATES["macro_bundle_noise"]
          and metrics["binary_item_coverage"] >= GATES["binary_item_coverage"])
    return "SILVER_RETRIEVAL_READY" if ok else "SILVER_RETRIEVAL_NOT_READY"
```

- [ ] **Step 4: 纯函数测试转绿**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestMetricsPure -q`
Expected: PASS。

- [ ] **Step 5: 实现 bundle 生成器（K 预算真实截断）+ 题级测试**

`evaluate.py` 追加：
```python
def build_bundle(item_map: list[dict], cfg: dict, strategies=("s1", "s2", "s3", "s4", "s5")) -> list[dict]:
    """每题内跨 item 累计字符预算 K；超预算按排序键截断 docs。"""
    import retriever as rt
    N, M, K = cfg["N_chars_per_doc"], cfg["M_docs_per_item"], cfg["K_chars_per_question"]
    by_case: dict[str, list] = {}
    for item in item_map:
        by_case.setdefault(item["case_id"], []).append(item)
    rows = []
    for case_id, items in sorted(by_case.items()):
        budget = K
        for item in items:
            pooled, seen = [], set()
            for q in item["queries"]:
                for h in rt.pool_candidates(q, strategies=strategies):
                    if h["canonical_key"] not in seen:
                        seen.add(h["canonical_key"])
                        pooled.append(h)
            pooled.sort(key=lambda h: rt.sort_key(h["score"], h["source_priority"], h["category"], h["canonical_key"]))
            docs = []
            for h in pooled[:M]:
                text = (rt.doc_text(h["canonical_key"]).get("text") or "")[:N]
                if len(text) > budget:
                    break  # 题级预算耗尽：按排序键截断剩余条文
                docs.append({"canonical_key": h["canonical_key"], "source": h["canonical_key"].split(":", 1)[0],
                             "text": text, "score": h["score"], "category": h["category"], "quarantined": False})
                budget -= len(text)
            rows.append({"question_case_id": case_id, "item_id": item["item_id"], "docs": docs})
    return rows


def build_bundles_for_eval(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["item_id"], []).extend(r["docs"])
    return out
```

题级测试（`TestMetricsPure` 追加）：
```python
    def test_bundle_k_budget_enforced(self, monkeypatch):
        """monkeypatch 多条长文本：真实触发跨 item 题级 K 截断（非空 query 占位）。"""
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        import retriever as rt
        cfg = {"N_chars_per_doc": 200, "M_docs_per_item": 5, "K_chars_per_question": 300}
        long_text = "婚" * 200
        fake_docs = {"kb:gejue:1": {"text": long_text, "category": "婚姻"},
                     "kb:gejue:2": {"text": long_text, "category": "婚姻"},
                     "kb:gejue:3": {"text": long_text, "category": "婚姻"}}
        monkeypatch.setattr(rt, "doc_text", lambda key: fake_docs[key])
        monkeypatch.setattr(rt, "pool_candidates", lambda q, **kw: [{"canonical_key": k, "score": 1.0, "source_priority": 1, "category": "婚姻"} for k in fake_docs])
        item_map = [{"case_id": "c1", "item_id": "i1", "queries": [{"query_id": "q1", "entrypoint": "search_gejue", "args": {"query": "婚", "category": "婚姻"}, "top_n": 5}]},
                    {"case_id": "c1", "item_id": "i2", "queries": [{"query_id": "q2", "entrypoint": "search_gejue", "args": {"query": "婚", "category": "婚姻"}, "top_n": 5}]}]
        rows = ev.build_bundle(item_map, cfg, strategies=("s1",))
        total = sum(len(d["text"]) for r in rows for d in r["docs"])
        assert total <= 300  # 跨 item 题级预算：K=300 强制
        assert any(len(r["docs"]) < 3 for r in rows)  # 至少一处被截断
```

- [ ] **Step 6: 真实 bundle 生成 + 一次性正式评测（持久化 run_eval.py，QC 完成后）**

追加测试：
```python
class TestRealEval:
    def test_real_bundle_budget(self):
        rows = [json.loads(l) for l in (P9 / "retrieval_bundle_dev.jsonl").open(encoding="utf-8") if l.strip()]
        per_case: dict[str, int] = {}
        for r in rows:
            per_case[r["question_case_id"]] = per_case.get(r["question_case_id"], 0) + sum(len(d["text"]) for d in r["docs"])
        for case_id, total in per_case.items():
            assert total <= 1200, (case_id, total)  # K 预算题级强制

    def test_eval_verdict_terminal(self):
        ev = _load_json(P9 / "retrieval_eval.json")
        assert ev["verdict"] in {"SILVER_RETRIEVAL_READY", "SILVER_RETRIEVAL_NOT_READY"}
        assert ev["qc_state"] in {"REVIEWED", "QC_FAIL"}
        if ev["qc_state"] == "REVIEWED":
            assert ev["metrics"]["n_items"] == 112

    def test_no_overwrite_on_rerun(self):
        """拒绝覆盖：产物已存在时 run_eval 必须 fail-closed（只生成一次）。"""
        proc = subprocess.run([sys.executable, str(P9 / "run_eval.py")], capture_output=True, text=True,
                              encoding="utf-8", cwd=REPO)
        assert proc.returncode != 0 and "already exists" in proc.stdout
```

Create: `docs/phase9a/retrieval/run_eval.py`（**持久化生产入口**，不在 .tmp；`__file__` 推导路径，无硬编码）
```python
"""Phase 9A 正式评测生产入口：QC 门 → 每策略/union 一次性评估 → 原子发布，拒绝覆盖。
双终态链：QC_FAIL（分歧超门）→ SILVER_RETRIEVAL_NOT_READY(metrics=not_computed)；QC_PASS → 正常评估。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
import evaluate as ev
import phase9a_manifest as pm
import qc_gate as qc


def _write_tmp(name: str, payload) -> Path:
    tmp = P9 / f".{name}.tmp"
    if name.endswith(".jsonl"):
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for r in payload:
                f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    else:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return tmp


def _publish(tmp_files: dict[str, Path]) -> None:
    """拒绝覆盖 + 全部校验后统一原子发布（避免半套产物）。
    .jsonl 逐行校验；.json 整文件校验（P0 修订：JSONL 不可整文件 json.loads）。"""
    for name in tmp_files:
        if (P9 / name).exists():
            sys.exit(f"FAIL: {name} already exists - one-shot violated")
    for name, tmp in tmp_files.items():
        if name.endswith(".jsonl"):
            for line in tmp.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    json.loads(line)  # 逐行校验
        else:
            json.loads(tmp.read_text(encoding="utf-8"))
    for name, tmp in tmp_files.items():
        os.replace(tmp, P9 / name)


def main() -> None:
    pm.verify_frozen(P9 / "manifest.json", ["evaluate_py", "qc_gate_py", "retriever_py", "silver_relevance_judgment",
                                            "item_query_map", "truncation_config", "ranking_config", "qc_config", "strategy_outputs"])
    cfg = json.loads((P9 / "qc_config.json").read_text(encoding="utf-8"))
    trun = json.loads((P9 / "truncation_config.json").read_text(encoding="utf-8"))
    state = qc.qc_state(P9 / "qc_human_review.jsonl", P9 / "qc_sample_list.json")
    if state != "REVIEWED":
        sys.exit(f"HUMAN_QC_REQUIRED: state={state}")
    reviews = qc.load_human_review(P9 / "qc_human_review.jsonl")
    qc.validate_review_coverage(json.loads((P9 / "qc_sample_list.json").read_text(encoding="utf-8"))["sample_list"], reviews)
    qc_result = qc.check_disagreement(reviews, P9 / "silver_relevance_judgment.jsonl", cfg["max_disagreement_rate"], P9 / "qc_result.json")
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))["items"]
    items = [i["item_id"] for i in item_map]
    if len(items) != 112:
        sys.exit(f"FAIL: frozen item count {len(items)} != 112")
    judgment = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
    # QC_FAIL 分支：分歧超门 → 正式 NOT_READY 终态（metrics=not_computed），不计算检索指标但完整发布
    if qc_result["verdict"] == "SILVER_RETRIEVAL_NOT_READY":
        payload = {"schema_version": "1.0", "verdict": "SILVER_RETRIEVAL_NOT_READY", "metrics": "not_computed",
                   "qc_state": "QC_FAIL", "qc_result": qc_result,
                   "note": "QC 分歧超门：不计算检索指标；终态/原因/provenance 完整发布"}
        _publish({"retrieval_eval.json": _write_tmp("retrieval_eval.json", payload)})
        print("QC_FAIL chain published: SILVER_RETRIEVAL_NOT_READY (metrics=not_computed)")
        return
    # QC_PASS 分支：每策略诊断 + union 正式评估
    per_strategy = {}
    for name in ("s1", "s2", "s3", "s4", "s5"):
        rows = ev.build_bundle(item_map, trun, strategies=(name,))
        per_strategy[name] = ev.compute_metrics(judgment, items, ev.build_bundles_for_eval(rows))
    rows = ev.build_bundle(item_map, trun, strategies=("s1", "s2", "s3", "s4", "s5"))
    metrics = ev.compute_metrics(judgment, items, ev.build_bundles_for_eval(rows))
    payload = {"schema_version": "1.0", "verdict": ev.decide(metrics), "metrics": metrics, "gates": ev.GATES,
               "qc_state": "REVIEWED", "qc_result": qc_result, "note": "silver 结论限于工程可复现性，不声称语义正确性"}
    _publish({
        "retrieval_bundle_dev.jsonl": _write_tmp("retrieval_bundle_dev.jsonl", rows),
        "per_strategy_eval.json": _write_tmp("per_strategy_eval.json", {"schema_version": "1.0", "per_strategy": per_strategy, "gates": ev.GATES}),
        "retrieval_eval.json": _write_tmp("retrieval_eval.json", payload),
    })
    print(f"one-shot eval published: verdict={payload['verdict']}, macro_recall={metrics['macro_weighted_recall']:.3f}, noise={metrics['macro_bundle_noise']:.3f}")


if __name__ == "__main__":
    main()
```

**执行前冻结 run_eval_py（freeze-before-use）→ 运行**：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
pm.freeze(P9 / "manifest.json", {"evaluate_py": (P9 / "evaluate.py", "git_canonical_lf"), "run_eval_py": (P9 / "run_eval.py", "git_canonical_lf")})
print("evaluate_py + run_eval_py frozen")
```
Run: `.venv/Scripts/python.exe docs/phase9a/retrieval/run_eval.py`
Expected（QC_PASS 链）：`one-shot eval published: verdict=SILVER_RETRIEVAL_READY|NOT_READY, macro_recall=..., noise=...`；
Expected（QC_FAIL 链）：`QC_FAIL chain published: SILVER_RETRIEVAL_NOT_READY (metrics=not_computed)`。

实现要点（均已在上方 run_eval.py 内实现，无临场补全）：
- **持久化与可迁移**：`__file__` 推导 REPO/P9，无硬编码路径；正式入口落为仓库内脚本。
- **原子发布与拒绝覆盖**：全部产物先写 `.tmp` → 存在即 fail-closed → 发布前 JSON 校验 → 统一 `os.replace`。
- **双终态链**：QC_FAIL（分歧超门）→ 正式 `retrieval_eval.json`（SILVER_RETRIEVAL_NOT_READY + qc_state=QC_FAIL + metrics=not_computed + 原因）；QC_PASS → 正常评估链。两条链都产生可对账的正式终态。
- **每策略评估**：`build_bundle(strategies=(name,))` → `compute_metrics` → `per_strategy_eval.json`（仅诊断）。
- **union 评估**：全策略 `build_bundle` → `retrieval_bundle_dev.jsonl`（replay 证据）+ `compute_metrics` → `retrieval_eval.json`（只生成一次）。
- **策略选择规则（冻结于 ranking_config）**：union 固定为最终 bundle 基准；每策略指标仅诊断，**不得为过门修改策略或 judgment**。

- [ ] **Step 7: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestMetricsPure tests/test_phase9a_retrieval.py::TestRealEval -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/retrieval/manifest.json docs/phase9a/retrieval/evaluate.py docs/phase9a/retrieval/run_eval.py docs/phase9a/retrieval/qc_result.json docs/phase9a/retrieval/retrieval_bundle_dev.jsonl docs/phase9a/retrieval/retrieval_eval.json docs/phase9a/retrieval/per_strategy_eval.json tests/test_phase9a_retrieval.py
git diff --cached --name-only
git commit -m "feat(phase9a): persistent run_eval entry - atomic publish, no overwrite, dual terminal chains"
```

---

## Task 8: 原子 provenance 对账（expected==actual）+ 篡改负向测试 + treatment fingerprint + 关闭报告

**Files:**
- Modify: `docs/phase9a/retrieval/manifest.json`（终态**仅追加**条目；不得 refresh/覆盖已有冻结项）
- Create: `docs/phase9a/retrieval/treatment_fingerprint.json`
- Create: `docs/phase9a/retrieval/reconcile9a.py`
- Create: `docs/phase9a/CLOSURE.md`
- Test: `tests/test_phase9a_retrieval.py`

- [ ] **Step 1: 写失败测试（含篡改镜像 + 双终态链集成）**

```python
class TestReconcile9a:
    def test_reconcile_expected_equals_actual(self):
        proc = subprocess.run([sys.executable, str(P9 / "reconcile9a.py")], capture_output=True, text=True,
                              encoding="utf-8", cwd=REPO)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "FAIL" not in proc.stdout

    def test_tamper_detected_in_mirror(self, tmp_path):
        """篡改负向：在 tmp 镜像中篡改，避免污染真实产物。"""
        import shutil
        mirror = tmp_path / "mirror"
        shutil.copytree(P9, mirror)
        victim = mirror / "ranking_config.json"
        victim.write_text(victim.read_text(encoding="utf-8").replace('"pooling_depth_per_strategy_per_query": 10', '"pooling_depth_per_strategy_per_query": 11'), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(P9 / "reconcile9a.py"), "--manifest", str(mirror / "manifest.json")],
                              capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode != 0
        assert "FAIL" in proc.stdout

    def test_fingerprint_components_recorded(self):
        fp = _load_json(P9 / "treatment_fingerprint.json")
        for c in fp["components"]:
            assert {"path", "strategy", "sha256"} <= set(c)  # 每组件明细，非仅拼接摘要


class TestTerminalChains:
    """双终态链 no-network 集成：QC_PASS 与 QC_FAIL 均产出可对账正式终态。"""

    def test_qc_fail_chain_publishes_terminal(self, tmp_path):
        import qc_gate as qc
        sample = [{"item_id": "a", "canonical_key": "kb:gejue:1"}]
        reviews = [{"item_id": "a", "canonical_key": "kb:gejue:1", "human_label": "relevant", "note": "x"}]
        judgment_path = tmp_path / "j.jsonl"
        judgment_path.write_text(json.dumps({"item_id": "a", "canonical_key": "kb:gejue:1", "label": "irrelevant"}, ensure_ascii=False) + "\n", encoding="utf-8")
        result = qc.check_disagreement(reviews, judgment_path, 0.1, tmp_path / "qc_result.json")
        # 不 sys.exit：返回 dict 供 run_eval 发布正式 QC_FAIL 终态（P0 修订）
        assert result["verdict"] == "SILVER_RETRIEVAL_NOT_READY" and result["disagreement_rate"] == 1.0
        # 证据已原子落盘
        disk = json.loads((tmp_path / "qc_result.json").read_text(encoding="utf-8"))
        assert disk["verdict"] == "SILVER_RETRIEVAL_NOT_READY"

    def test_qc_pass_chain_metrics_not_computed_absent(self):
        ev = _load_json(P9 / "retrieval_eval.json")
        if ev["qc_state"] == "QC_FAIL":
            assert ev["verdict"] == "SILVER_RETRIEVAL_NOT_READY" and ev["metrics"] == "not_computed"
        else:
            assert ev["metrics"]["n_items"] == 112
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestReconcile9a tests/test_phase9a_retrieval.py::TestTerminalChains -q`
Expected: FAIL。

- [ ] **Step 3: 生成 treatment_fingerprint + 终态 manifest 仅追加封存 + 实现 reconcile9a.py（顺序冻结）**

**Step 3a: 生成 treatment_fingerprint.json（每组件明细，P0 补缺）**
```python
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
import p8_freeze
P9 = Path("docs/phase9a/retrieval")
components = ["retriever.py", "query_extractor.py", "synonym_table.json", "ranking_config.json", "truncation_config.json", "upstream_inputs_sha.json"]
components_detail = []
digest = hashlib.sha256()
for c in components:
    p = P9 / c
    sha = p8_freeze.git_canonical_lf_sha256(p)
    components_detail.append({"path": str(p), "strategy": "git_canonical_lf", "sha256": sha})
    digest.update(sha.encode() + b"\0")
out = {"schema_version": "1.0", "components": components_detail, "sha256": digest.hexdigest(),
       "note": "Phase 9B enhanced 臂 treatment fingerprint 依据；每组件 path/strategy/SHA 可独立复算"}
(P9 / "treatment_fingerprint.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print("treatment fingerprint written with per-component details")
```

**Step 3b: 一次性生成最终 CLOSURE.md（终态产物必须先于 closure 存在）**
`docs/phase9a/CLOSURE.md` 内容：终态（SILVER_RETRIEVAL_READY / NOT_READY；QC_PASS 或 QC_FAIL）、verdict 依据（union + 每策略指标表；QC_FAIL 时 metrics=not_computed + 分歧原因）、QC 分歧率、冻结产物清单与 expected SHA、结论限定（silver 工程可复现性，不声称语义正确性；检索效果声明须依赖人工 gold 独立工作线）、后续衔接（Phase 9B 待密封集）。**本文件在 seal 前一次性定稿，seal 后禁止修改**（如需修订 → 以新版本号新建文件并重新走 seal 流程，旧版保留不动）。

**Step 3c: 封存（reconcile9a.py 先落盘，CLOSURE 已定稿，随后 seal；不得 refresh/覆盖）**
⚠️ 顺序注意：先创建 reconcile9a.py（下方代码块），再执行本 seal 脚本（seal 需计算其 SHA）。
写 `.tmp/phase9a_seal.py` 并执行：
```python
import json
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
# 按终态分支冻结（P0 修订：QC_FAIL 只发布 retrieval_eval.json，不冻结缺失产物）
eval_state = json.loads((P9 / "retrieval_eval.json").read_text(encoding="utf-8"))["qc_state"]
common_entries = {
    "silver_judge_py": (P9 / "silver_judge.py", "git_canonical_lf"),
    "qc_gate_py": (P9 / "qc_gate.py", "git_canonical_lf"),
    "evaluate_py": (P9 / "evaluate.py", "git_canonical_lf"),
    "run_eval_py": (P9 / "run_eval.py", "git_canonical_lf"),
    "silver_relevance_judgment": (P9 / "silver_relevance_judgment.jsonl", "jsonl_canonical"),
    "silver_judgment_summary": (P9 / "silver_judgment_summary.json", "json_canonical"),
    "qc_sample_list": (P9 / "qc_sample_list.json", "json_canonical"),
    "qc_human_review": (P9 / "qc_human_review.jsonl", "jsonl_canonical"),
    "qc_human_review_schema": (P9 / "qc_human_review_schema.json", "json_canonical"),
    "qc_result": (P9 / "qc_result.json", "json_canonical"),
    "strategy_outputs": (P9 / "strategy_outputs.jsonl", "jsonl_canonical"),
    "retrieval_eval": (P9 / "retrieval_eval.json", "json_canonical"),
    "treatment_fingerprint": (P9 / "treatment_fingerprint.json", "json_canonical"),
    "reconcile9a_py": (P9 / "reconcile9a.py", "git_canonical_lf"),
    "closure": (Path("docs/phase9a/CLOSURE.md"), "git_canonical_lf"),
}
if eval_state != "QC_FAIL":  # QC_PASS 分支额外冻结诊断与 replay 产物
    common_entries["per_strategy_eval"] = (P9 / "per_strategy_eval.json", "json_canonical")
    common_entries["retrieval_bundle_dev"] = (P9 / "retrieval_bundle_dev.jsonl", "jsonl_canonical")
pm.freeze(P9 / "manifest.json", common_entries)  # append-only：已存在项 SHA 变化即 fail-closed
pm.set_stage(P9 / "manifest.json", "sealed")
print("manifest sealed; entries:", len(json.loads((P9 / "manifest.json").read_text(encoding="utf-8"))["entries"]))
```

`reconcile9a.py`：
```python
"""Phase 9A 原子对账：manifest expected SHA == 磁盘 actual SHA（逐项）；FAIL 即 exit 1。
--manifest 可选参数：指向镜像 manifest（篡改负向测试用）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
import phase9a_manifest as pm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(P9 / "manifest.json"))
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "sealed":
        sys.exit("FAIL: manifest not sealed")
    base = manifest_path.parent  # 镜像模式下条目路径指向镜像目录同名文件
    all_ok = True
    for name, entry in sorted(manifest["entries"].items()):
        rel = entry["path"]
        p = base / Path(rel).name if manifest_path.parent != P9 else REPO / rel
        if not p.exists():
            print(f"  FAIL  {name}: missing")
            all_ok = False
            continue
        actual = pm.STRATEGY_FN[entry["strategy"]](p)
        ok = actual == entry["sha256"]
        all_ok = all_ok and ok
        print(f"  {'ok' if ok else 'FAIL'}  {name}  ({entry['strategy']})")
    ev = json.loads((P9 / "retrieval_eval.json").read_text(encoding="utf-8"))
    if ev["qc_state"] == "QC_FAIL":
        terminal_ok = ev["verdict"] == "SILVER_RETRIEVAL_NOT_READY" and ev["metrics"] == "not_computed"
        denom_ok = True  # QC_FAIL 不计算检索指标
    else:
        terminal_ok = ev["verdict"] in {"SILVER_RETRIEVAL_READY", "SILVER_RETRIEVAL_NOT_READY"} and ev["qc_state"] == "REVIEWED"
        denom_ok = ev["metrics"]["n_items"] == 112
    fp_ok = (P9 / "treatment_fingerprint.json").exists()
    all_ok = all_ok and terminal_ok and denom_ok and fp_ok
    print(f"  {'ok' if terminal_ok else 'FAIL'}  terminal verdict ({ev['verdict']}, qc={ev['qc_state']})")
    print(f"  {'ok' if denom_ok else 'FAIL'}  fixed-112 denominator")
    print(f"  {'ok' if fp_ok else 'FAIL'}  treatment fingerprint")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 测试转绿 + 运行 reconcile（封存后执行）**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_retrieval.py::TestReconcile9a tests/test_phase9a_retrieval.py::TestTerminalChains -q`；`.venv/Scripts/python.exe docs/phase9a/retrieval/reconcile9a.py`
Expected: PASS；exit 0，全部 ok（含 treatment fingerprint 明细；篡改镜像测试 FAIL 后恢复）。

- [ ] **Step 5: Commit（seal 后禁止修改任何冻结产物）**

```powershell
git add -- docs/phase9a/retrieval/manifest.json docs/phase9a/retrieval/treatment_fingerprint.json docs/phase9a/retrieval/reconcile9a.py docs/phase9a/CLOSURE.md tests/test_phase9a_retrieval.py
git diff --cached --name-only
git commit -m "chore(phase9a): seal manifest (append-only), treatment fingerprint details, reconcile + closure"
```

---

## 完成定义（对齐设计 §8）

1. 至少 2 个候选策略完成评估（本计划全 5 个），**全量 53 query 双跑字节一致**。
2. silver_relevance_judgment.jsonl 冻结（逐 item-document pair，`actual_pair_count` 于 summary；检索开发者未参与）。
3. retriever 及全部配置在策略执行前冻结（Task 1/3 manifest）；`treatment_fingerprint.json` 生成并对账（Task 8，Phase 9B enhanced 臂依据）。
4. N/M/K 冻结并在真实 bundle 中强制（题级 K 预算测试）。
5. 终态 ∈ {SILVER_RETRIEVAL_READY, SILVER_RETRIEVAL_NOT_READY}；QC 状态为 REVIEWED（正常链）或 QC_FAIL（分歧超门，metrics=not_computed 但终态/原因/产物完整发布）；**QC 未完成时状态 HUMAN_QC_REQUIRED（暂停状态，不得计算指标或发布终态）**；分歧 >10% → QC_FAIL → SILVER_RETRIEVAL_NOT_READY。
6. 全程零 API、零生产代码改动；reconcile9a.py 逐项 expected==actual 对账 exit 0（含篡改负向测试）。

## 反过拟合与纪律（冻结）

- 不得为过门修改策略、silver 规则、judgment 或 manifest；QC 只审计不改标签；正式评测产物只生成一次。
- 不在 44 道已知婚姻题上宣称准确率提升；SILVER_READY 只证明 silver 判据一致性与工程可复现性。
- 不混入大运/流年注入、prompt 改写；不重启 C1。
- 密封集数据不进入本任务；curator 数据位置只提供给独立受限 curator 任务。
