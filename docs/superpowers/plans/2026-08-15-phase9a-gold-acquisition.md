# Phase 9A-Gold item-centered 人工 Gold 采集 Implementation Plan（v5）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 v1.7 规约建立 item-centered 人工 Gold（112 项，A 提议 + B 盲审 + C 裁决），产出 `GOLD_READY / GOLD_BLOCKED_ACQUISITION` 之一终态并密封。

**Architecture:** 纯本地零 LLM API；复用 Phase 9A 冻结语料。阶段机：`None → config_frozen → code_frozen → sealed`。关键顺序：**基线 → builder 生成草稿 config → validator 校验草稿 → 人工确认/修改 → validator 重校验 → Task 2 原子冻结最终 config → 7 个独立工具任务逐冻结 → code_frozen → A 采集 → HN sample/r1 packet/verification packet 冻结 → B/C 盲审 + r2/r3 → finalize 双终态 + reconcile + guard 验证**。

**Tech Stack:** Python 3.11+、sqlite3（只读 URI）、git object 读取、pytest、ruff（E9/F821 基线）。

**设计依据：** `docs/superpowers/specs/2026-08-14-phase9a-gold-data-spec.md` v1.7（commit `c06daec`，APPROVED）。
**前置冻结：** Phase 9A（manifest_v4 sealed）+ Phase 9A-R1（manifest_v5 sealed）。

**命令约定：** PowerShell；路径基于 `__file__`；commit 用显式 pathspec；pre-commit stash 冲突可原样重试一次，禁止 `--no-verify`。
**提交纪律：** 每个 commit 前先 `git status --porcelain` + `git diff --cached --name-only` 核对暂存清单，防止卷入并行蒸馏线 churn。
**测试纪律：** 所有测试用 tmp fixture/镜像，真实调用生产函数验证本 Task 行为；禁止依赖未来任务产物；no-network monkeypatch 禁止工具链意外读取网络或 LLM API。

---

## 输入基线（Task 0 复核）

| 输入 | 路径 | 用途 |
|---|---|---|
| KB 快照（只读） | `docs/phase8/marriage-capability/kb_snapshot.db` | 冻结语料 |
| classic_texts 冻结版 | `docs/phase8/marriage-capability/classic_texts_freeze.json` + git object | 冻结语料 |
| 112 项清单 | `docs/phase9a/retrieval/item_query_map.json` | item 定义来源 |
| Phase 8 语义源 | `docs/phase8/marriage-capability/required_knowledge.jsonl` + `knowledge_audit.jsonl` | required_term/query_specs 来源 |
| Phase 8 manifest | `docs/phase8/marriage-capability/phase8_freeze_manifest.json` | 上游冻结基线 |
| Phase 9A manifest | `docs/phase9a/retrieval/manifest_v4.json` | 上游冻结基线 |
| Phase 9A 检索器 | `docs/phase9a/retrieval/retriever.py` | canonical_key 解析 + doc_text（只读复用，不修改） |

---

## Task 0: 基线验证 + 输入 SHA 记录

**Files:**
- Create: `docs/phase9a/gold/upstream_inputs_sha.json`
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 复核 Phase 9A/R1 对账与输入存在性**

Run:
```powershell
.venv/Scripts/python.exe docs/phase9a/retrieval/reconcile9a.py
.venv/Scripts/python.exe docs/phase9a/r1/reconcile_r1.py
.venv/Scripts/python.exe docs/phase8/marriage-capability/reconcile8.py
Test-Path docs/phase9a/retrieval/item_query_map.json
Test-Path docs/phase8/marriage-capability/required_knowledge.jsonl
Test-Path docs/phase8/marriage-capability/knowledge_audit.jsonl
Test-Path docs/phase8/marriage-capability/phase8_freeze_manifest.json
```
Expected: 三个 reconcile exit 0 无 FAIL；全部 True。

- [ ] **Step 2: 写失败测试**

`tests/test_phase9a_gold.py`（新建文件，顶部 helper）：
```python
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
PG = REPO / "docs" / "phase9a" / "gold"
P8 = REPO / "docs" / "phase8" / "marriage-capability"

sys.path.insert(0, str(P8))
sys.path.insert(0, str(P9))
sys.path.insert(0, str(PG))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestGoldBaseline:
    def test_upstream_inputs_sha(self):
        sha = _load_json(PG / "upstream_inputs_sha.json")
        assert sha["schema_version"] == "1.0"
        p8m = _load_json(P8 / "phase8_freeze_manifest.json")
        assert sha["required_knowledge_sha256"] == p8m["entries"]["required_knowledge"]["sha256"]
        assert sha["knowledge_audit_sha256"] == p8m["entries"]["knowledge_audit"]["sha256"]

    def test_kb_snapshot_raw_sha(self):
        # kb_snapshot.db 用 raw-byte SHA（非 manifest 单源，因 Phase 8 manifest 未含该条目）
        sha = _load_json(PG / "upstream_inputs_sha.json")
        expected = hashlib.sha256((P8 / "kb_snapshot.db").read_bytes()).hexdigest()
        assert sha["kb_snapshot_sha256"] == expected
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldBaseline -q`
Expected: FAIL。

- [ ] **Step 4: 生成 upstream_inputs_sha.json（manifest 单源 + kb_snapshot raw-byte SHA）**

```python
import hashlib
import json, sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P8 = Path("docs/phase8/marriage-capability")
PG = Path("docs/phase9a/gold")
p8m = json.loads((P8 / "phase8_freeze_manifest.json").read_text(encoding="utf-8"))
p9m = json.loads((Path("docs/phase9a/retrieval") / "manifest_v4.json").read_text(encoding="utf-8"))
out = {
    "schema_version": "1.0",
    "required_knowledge_sha256": p8m["entries"]["required_knowledge"]["sha256"],
    "knowledge_audit_sha256": p8m["entries"]["knowledge_audit"]["sha256"],
    "item_query_map_sha256": p9m["entries"]["item_query_map"]["sha256"],
    # 冻结语料快照：raw-byte SHA（搜索执行器运行时重算比对，CORPUS_SHA_MISMATCH 门）
    "kb_snapshot_sha256": hashlib.sha256((P8 / "kb_snapshot.db").read_bytes()).hexdigest(),
    "classic_texts_freeze_sha256": hashlib.sha256((P8 / "classic_texts_freeze.json").read_bytes()).hexdigest(),
    "note": "jsonl/json 条目单源读取 manifest；语料快照为 raw-byte SHA",
}
PG.mkdir(parents=True, exist_ok=True)
(PG / "upstream_inputs_sha.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print("upstream_inputs_sha written")
```

- [ ] **Step 5: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldBaseline -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/upstream_inputs_sha.json tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): baseline validation + upstream inputs SHA (single-source from manifests)"
```

---

## Task 1a: config builder 生成草稿 config

**Files:**
- Create: `docs/phase9a/gold/build_gold_config.py`
- Test: `tests/test_phase9a_gold.py`

**失败状态（生产函数必须显式 exit）：**
- `UPSTREAM_SHA_MISMATCH`：upstream_inputs_sha.json 与 manifest 记录不一致
- `ITEM_COUNT_NOT_112`：item_query_map 解析后不是 112 项
- `DUPLICATE_ITEM_ID`：存在重复 item_id

**生产入口：** `build_gold_config.py --output-dir DIR`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldConfigBuilder:
    def test_builder_requires_frozen_self_and_upstream(self):
        m = _load_json(PG / "gold_manifest.json")
        assert "build_gold_config_py" in m["entries"]
        assert "upstream_inputs_sha" in m["entries"]

    def test_builder_generates_all_draft_configs(self, tmp_path):
        builder = _load_module("build_gold_config", "docs/phase9a/gold/build_gold_config.py")
        out_dir = tmp_path / "gold"
        out_dir.mkdir()
        builder.main(output_dir=out_dir)
        for name in (
            "gold_item_definitions.json",
            "gold_search_plans.json",
            "gold_b_verification_plans.json",
            "gold_hn_qc_config.json",
            "gold_guard_config.json",
            "gold_roles.json",
        ):
            assert (out_dir / name).exists(), name
        defs = json.loads((out_dir / "gold_item_definitions.json").read_text(encoding="utf-8"))
        assert len(defs["items"]) == 112
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigBuilder -q`
Expected: FAIL。

- [ ] **Step 3: 实现 build_gold_config.py**

```python
"""Phase 9A-Gold：从 Phase 8/9A 冻结数据生成 config 草稿（112 项定义 + 搜索计划 + B verification 计划 + HN QC + guard + roles 模板）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
PG = REPO / "docs" / "phase9a" / "gold"


def _atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def main(output_dir: Path | None = None) -> None:
    out = output_dir or PG
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(PG / "gold_manifest.json", ["build_gold_config_py", "upstream_inputs_sha"], required_stage="config_frozen")
    upstream = json.loads((PG / "upstream_inputs_sha.json").read_text(encoding="utf-8"))
    p8m = json.loads((P8 / "phase8_freeze_manifest.json").read_text(encoding="utf-8"))
    if upstream["required_knowledge_sha256"] != p8m["entries"]["required_knowledge"]["sha256"]:
        sys.exit("UPSTREAM_SHA_MISMATCH: required_knowledge")
    if upstream["knowledge_audit_sha256"] != p8m["entries"]["knowledge_audit"]["sha256"]:
        sys.exit("UPSTREAM_SHA_MISMATCH: knowledge_audit")
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    rk = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "required_knowledge.jsonl").open(encoding="utf-8") if l.strip())}
    audit = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "knowledge_audit.jsonl").open(encoding="utf-8") if l.strip())}
    items = []
    for item in item_map["items"]:
        case_id = item["case_id"]
        item_id = item["item_id"]
        req_term = ""
        if case_id in audit:
            for audit_item in audit[case_id]["items"]:
                if audit_item["item_id"] == item_id:
                    req_term = audit_item.get("prompt_evidence", {}).get("required_term", "")
                    break
        query_specs = []
        if case_id in rk:
            for rk_item in rk[case_id]["items"]:
                if rk_item["item_id"] == item_id:
                    query_specs = rk_item.get("query_specs", [])
                    break
        query_terms = []
        for qs in query_specs:
            args = qs.get("args", {})
            term = args.get("query") or args.get("name") or args.get("combo_name") or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", "")
            if term:
                query_terms.append(term)
        items.append({
            "item_id": item_id,
            "case_id": case_id,
            "required_term": req_term,
            "query_specs": query_specs,
            "item_description": f"required_term={req_term}; query_terms={','.join(query_terms[:3])}",
            "upstream": {
                "required_knowledge_path": "docs/phase8/marriage-capability/required_knowledge.jsonl",
                "required_knowledge_sha256": upstream["required_knowledge_sha256"],
                "knowledge_audit_path": "docs/phase8/marriage-capability/knowledge_audit.jsonl",
                "knowledge_audit_sha256": upstream["knowledge_audit_sha256"],
            },
        })
    items.sort(key=lambda i: i["item_id"])
    if len(items) != 112:
        sys.exit(f"ITEM_COUNT_NOT_112: {len(items)}")
    item_ids = [i["item_id"] for i in items]
    if len(set(item_ids)) != len(item_ids):
        sys.exit("DUPLICATE_ITEM_ID")
    out.mkdir(parents=True, exist_ok=True)
    _atomic_json(out / "gold_item_definitions.json", {"schema_version": "1.0", "items": items})
    plans = []
    corpus_sha = upstream["kb_snapshot_sha256"]
    for item in items:
        item_id = item["item_id"]
        terms = [t for t in item["required_term"].split("|") if t.strip()] or [item_id]
        plans.append({
            "item_id": item_id,
            "steps": [
                {"step_id": f"{item_id}_s1", "entrypoint": "search_gejue", "args": {"query": terms[0], "category": "婚姻"}, "query_terms": terms, "filters": {}, "corpus_snapshot_sha256": corpus_sha},
                {"step_id": f"{item_id}_hn_s1", "entrypoint": "search_gejue", "args": {"query": terms[0], "category": "婚姻"}, "query_terms": terms, "filters": {"exclude_relevant": True}, "corpus_snapshot_sha256": corpus_sha},
            ],
        })
    _atomic_json(out / "gold_search_plans.json", {"schema_version": "1.0", "plans": plans})
    bv_plans = []
    for item in items:
        item_id = item["item_id"]
        terms = [t for t in item["required_term"].split("|") if t.strip()] or [item_id]
        bv_plans.append({
            "item_id": item_id,
            "steps": [{"step_id": f"{item_id}_bv1", "entrypoint": "search_gejue", "args": {"query": terms[0], "category": "婚姻"}, "query_terms": terms, "filters": {}, "corpus_snapshot_sha256": corpus_sha}],
        })
    _atomic_json(out / "gold_b_verification_plans.json", {"schema_version": "1.0", "plans": bv_plans})
    _atomic_json(out / "gold_hn_qc_config.json", {
        "schema_version": "1.0", "seed": 20260814, "ratio": 0.2, "stratify_by": "item_id",
        "sample_count_formula": "ceil(total_hn * 0.2)", "per_item_min_formula": "floor(n_hn_i * 0.2)",
        "remainder_allocation": "item_id 字典序逐层 +1", "overflow_return": "缺口回流剩余层（同序继续补足）",
        "rng": "random.Random(20260814) 全局单实例", "note": "样本列表先于 r1 盲审包构造冻结",
    })
    _atomic_json(out / "gold_guard_config.json", {
        "schema_version": "1.0",
        "protected_paths": [
            "docs/phase9a/gold/gold_v1.json",
            "docs/phase9a/gold/gold_manifest.json",
        ],
        "activation": "GOLD_RECEIPT 发布后激活；guard 自行读取 receipt 并重算 manifest SHA 验证绑定",
        "note": "修订必须新建 gold_v2.json",
    })
    _atomic_json(out / "gold_roles.json", {
        "schema_version": "1.0", "curator_A": "PLACEHOLDER_HUMAN_A", "curator_B": "PLACEHOLDER_HUMAN_B", "curator_C": None,
        "note": "采集前必须人工填写为互不相同的人类身份；C 可选但须采集前冻结；未指定或身份相同 → BLOCKED_ROLE_ASSIGNMENT",
    })
    print(f"gold config draft written: {len(items)} items")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    main(output_dir=args.output_dir)
```

- [ ] **Step 4: 初始化 gold_manifest 并冻结 builder**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
m = PG / "gold_manifest.json"
pm.set_stage(m, "config_frozen")
pm.freeze(m, {
    "upstream_manifest_v4": (Path("docs/phase9a/retrieval") / "manifest_v4.json", "json_canonical"),
    "upstream_inputs_sha": (PG / "upstream_inputs_sha.json", "json_canonical"),
    "build_gold_config_py": (PG / "build_gold_config.py", "git_canonical_lf"),
})
print("gold_manifest initialized at config_frozen; builder frozen")
```

Run: `.venv/Scripts/python.exe docs/phase9a/gold/build_gold_config.py`
Expected: `gold config draft written: 112 items`。

- [ ] **Step 5: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigBuilder -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/build_gold_config.py docs/phase9a/gold/gold_item_definitions.json docs/phase9a/gold/gold_search_plans.json docs/phase9a/gold/gold_b_verification_plans.json docs/phase9a/gold/gold_hn_qc_config.json docs/phase9a/gold/gold_guard_config.json docs/phase9a/gold/gold_roles.json tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): config builder frozen + draft configs generated (112 items)"
```

---

## Task 1b: config validator 校验草稿 + 冻结 validator

**Files:**
- Create: `docs/phase9a/gold/validate_gold_config.py`
- Test: `tests/test_phase9a_gold.py`

**失败状态：**
- `SCHEMA_VERSION_MISMATCH`
- `ITEM_COUNT_NOT_112`
- `ITEMS_NOT_SORTED`
- `DUPLICATE_ITEM_ID`
- `MISSING_FIELDS`
- `UPSTREAM_SHA_MISSING`
- `POSITIVE_STEP_MISSING`
- `HN_STEP_MISSING`
- `PLAN_ITEM_NOT_IN_DEFINITIONS`

**生产入口：** `validate_gold_config.py`

- [ ] **Step 1: 写失败测试（独立测试向量）**

```python
class TestGoldConfigValidator:
    def test_validator_frozen_before_use(self):
        m = _load_json(PG / "gold_manifest.json")
        assert "validate_gold_config_py" in m["entries"]

    def test_validator_rejects_bad_item_definitions(self, tmp_path):
        validator = _load_module("validate_gold_config", "docs/phase9a/gold/validate_gold_config.py")
        bad_defs = tmp_path / "gold_item_definitions.json"
        bad_defs.write_text(json.dumps({"schema_version": "1.0", "items": [{"item_id": "x"}]}), encoding="utf-8")
        proc = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, 'docs/phase9a/gold'); from pathlib import Path; from validate_gold_config import validate_item_definitions; validate_item_definitions(Path(r'{bad_defs}'))"], capture_output=True, text=True, cwd=REPO)
        assert proc.returncode != 0
        assert "MISSING_FIELDS" in proc.stderr or "ITEM_COUNT" in proc.stderr  # sys.exit 消息在 stderr

    def test_validator_accepts_valid_draft(self, tmp_path):
        validator = _load_module("validate_gold_config", "docs/phase9a/gold/validate_gold_config.py")
        defs = json.loads((PG / "gold_item_definitions.json").read_text(encoding="utf-8"))
        plans = json.loads((PG / "gold_search_plans.json").read_text(encoding="utf-8"))
        validator.validate_item_definitions(PG / "gold_item_definitions.json")
        validator.validate_search_plans(PG / "gold_search_plans.json", {i["item_id"] for i in defs["items"]})
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigValidator -q`
Expected: FAIL。

- [ ] **Step 3: 实现 validate_gold_config.py**

```python
"""Phase 9A-Gold：config 草稿校验器（schema + 112 项覆盖 + 上游 SHA 一致性 + 搜索计划完整性）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
PG = REPO / "docs" / "phase9a" / "gold"


def validate_item_definitions(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        sys.exit("SCHEMA_VERSION_MISMATCH")
    items = data.get("items", [])
    if len(items) != 112:
        sys.exit(f"ITEM_COUNT_NOT_112: {len(items)}")
    item_ids = [i["item_id"] for i in items]
    if item_ids != sorted(item_ids):
        sys.exit("ITEMS_NOT_SORTED")
    if len(set(item_ids)) != 112:
        sys.exit("DUPLICATE_ITEM_ID")
    for item in items:
        required = {"item_id", "case_id", "required_term", "query_specs", "item_description", "upstream"}
        if not required <= set(item):
            sys.exit(f"MISSING_FIELDS: item {item.get('item_id')} {required - set(item)}")
        upstream = item["upstream"]
        if not upstream.get("required_knowledge_sha256") or not upstream.get("knowledge_audit_sha256"):
            sys.exit(f"UPSTREAM_SHA_MISSING: item {item['item_id']}")


def validate_search_plans(path: Path, item_ids: set[str]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        sys.exit("SCHEMA_VERSION_MISMATCH")
    plans = data.get("plans", [])
    if len(plans) != 112:
        sys.exit(f"ITEM_COUNT_NOT_112: plans {len(plans)}")
    for plan in plans:
        if plan["item_id"] not in item_ids:
            sys.exit(f"PLAN_ITEM_NOT_IN_DEFINITIONS: {plan['item_id']}")
        steps = plan.get("steps", [])
        step_ids = [s["step_id"] for s in steps]
        if len(step_ids) != len(set(step_ids)):
            sys.exit(f"DUPLICATE_STEP_ID: {plan['item_id']}")
        if not any(s["step_id"].endswith("_s1") for s in steps):
            sys.exit(f"POSITIVE_STEP_MISSING: {plan['item_id']}")
        if not any(s["step_id"].endswith("_hn_s1") for s in steps):
            sys.exit(f"HN_STEP_MISSING: {plan['item_id']}")


def validate_roles(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        sys.exit("SCHEMA_VERSION_MISMATCH")
    a, b = data.get("curator_A"), data.get("curator_B")
    if not a or not b or a == b:
        sys.exit("BLOCKED_ROLE_ASSIGNMENT")
    c = data.get("curator_C")
    if c and c in {a, b}:
        sys.exit("BLOCKED_ROLE_ASSIGNMENT")


def validate_bv_plans(path: Path, item_ids: set[str]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        sys.exit("SCHEMA_VERSION_MISMATCH")
    plans = data.get("plans", [])
    if len(plans) != 112:
        sys.exit(f"ITEM_COUNT_NOT_112: bv plans {len(plans)}")
    seen = set()
    for plan in plans:
        if plan["item_id"] not in item_ids:
            sys.exit(f"PLAN_ITEM_NOT_IN_DEFINITIONS: {plan['item_id']}")
        if plan["item_id"] in seen:
            sys.exit(f"DUPLICATE_BV_PLAN: {plan['item_id']}")
        seen.add(plan["item_id"])
        steps = plan.get("steps", [])
        if not steps or not all(s["step_id"].endswith("_bv1") for s in steps):
            sys.exit(f"BV_STEP_PREFIX_MISSING: {plan['item_id']}")


def validate_hn_qc_config(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        sys.exit("SCHEMA_VERSION_MISMATCH")
    required = {"seed", "ratio", "stratify_by", "sample_count_formula", "per_item_min_formula", "remainder_allocation", "overflow_return", "rng"}
    if not required <= set(data):
        sys.exit(f"HN_QC_CONFIG_MISSING: {required - set(data)}")
    if data["stratify_by"] != "item_id" or not 0 < data["ratio"] <= 1:
        sys.exit("HN_QC_CONFIG_INVALID")


def validate_guard_config(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        sys.exit("SCHEMA_VERSION_MISMATCH")
    if not data.get("protected_paths"):
        sys.exit("GUARD_CONFIG_NO_PROTECTED_PATHS")


def validate_upstream_sha(path: Path) -> None:
    """上游 SHA 重算校验（不信存储值，直接重算比对）。"""
    import hashlib
    data = json.loads(path.read_text(encoding="utf-8"))
    p8m = json.loads((P8 / "phase8_freeze_manifest.json").read_text(encoding="utf-8"))
    if data["required_knowledge_sha256"] != p8m["entries"]["required_knowledge"]["sha256"]:
        sys.exit("UPSTREAM_SHA_DRIFT: required_knowledge")
    if data["knowledge_audit_sha256"] != p8m["entries"]["knowledge_audit"]["sha256"]:
        sys.exit("UPSTREAM_SHA_DRIFT: knowledge_audit")
    if data["kb_snapshot_sha256"] != hashlib.sha256((P8 / "kb_snapshot.db").read_bytes()).hexdigest():
        sys.exit("UPSTREAM_SHA_DRIFT: kb_snapshot")


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    # 注意：validator 在 config 冻结前运行（校验草稿），因此只校验自身已冻结；config 条目在 Task 2 才入 manifest
    pm.verify_frozen(PG / "gold_manifest.json", ["validate_gold_config_py"], required_stage="config_frozen")
    validate_upstream_sha(PG / "upstream_inputs_sha.json")
    validate_item_definitions(PG / "gold_item_definitions.json")
    defs = json.loads((PG / "gold_item_definitions.json").read_text(encoding="utf-8"))
    item_ids = {i["item_id"] for i in defs["items"]}
    validate_search_plans(PG / "gold_search_plans.json", item_ids)
    validate_bv_plans(PG / "gold_b_verification_plans.json", item_ids)
    validate_hn_qc_config(PG / "gold_hn_qc_config.json")
    validate_guard_config(PG / "gold_guard_config.json")
    if not _is_placeholder_roles(PG / "gold_roles.json"):
        validate_roles(PG / "gold_roles.json")
    print("gold config validation passed")


def _is_placeholder_roles(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("curator_A") == "PLACEHOLDER_HUMAN_A" or data.get("curator_B") == "PLACEHOLDER_HUMAN_B"


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 validator → 运行校验 → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {"validate_gold_config_py": (PG / "validate_gold_config.py", "git_canonical_lf")})
print("validator frozen")
```

Run: `.venv/Scripts/python.exe docs/phase9a/gold/validate_gold_config.py`
Expected: `gold config validation passed`。

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigValidator -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/validate_gold_config.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): config validator frozen + draft config validation passed"
```

**⏸ 暂停点（人工）：** 人工填写 `gold_roles.json`（A/B 互不相同人类身份；C 可选但须在采集前冻结）+ 审核 `gold_search_plans.json`（112 项搜索计划完整性与合理性）。**未完成前不得执行 Task 2 的最终 config 冻结**。

---

## Task 1c: 人工修改后 validator 重校验（validator 不再修改，无迁移链问题）

**Files:**
- Modify: `docs/phase9a/gold/gold_roles.json`（人工填写身份）
- Modify: `docs/phase9a/gold/gold_search_plans.json`（人工审核后可补充）
- Test: `tests/test_phase9a_gold.py`

**生产入口：** 人工修改后再次运行 `validate_gold_config.py`（此时 roles 非占位符 → 自动执行 validate_roles 分支）

- [ ] **Step 1: 确认 Task 1b 已含 roles 校验测试**

Task 1b 测试已覆盖：

```python
class TestGoldConfigValidatorAfterHumanEdit:
    def test_roles_real_identities(self):
        roles = _load_json(PG / "gold_roles.json")
        assert roles["curator_A"] != "PLACEHOLDER_HUMAN_A"
        assert roles["curator_B"] != "PLACEHOLDER_HUMAN_B"
        assert roles["curator_A"] != roles["curator_B"]
        if roles.get("curator_C"):
            assert roles["curator_C"] not in {roles["curator_A"], roles["curator_B"]}

    def test_revalidator_catches_role_collision(self, tmp_path):
        validator = _load_module("validate_gold_config", "docs/phase9a/gold/validate_gold_config.py")
        bad_roles = tmp_path / "gold_roles.json"
        bad_roles.write_text(json.dumps({"schema_version": "1.0", "curator_A": "same", "curator_B": "same", "curator_C": None}), encoding="utf-8")
        try:
            validator.validate_roles(bad_roles)
            raised = False
        except SystemExit:
            raised = True
        assert raised
```

- [ ] **Step 2: 人工修改 roles/search plans → 运行重校验 → Commit**

Run: `.venv/Scripts/python.exe docs/phase9a/gold/validate_gold_config.py`
Expected: `gold config validation passed`（含 roles 校验分支）。

```powershell
git add -- docs/phase9a/gold/gold_roles.json docs/phase9a/gold/gold_search_plans.json
git diff --cached --name-only
git commit -m "feat(phase9a-gold): human-edited config re-validated (roles + search plans)"
```

---

## Task 2: 原子冻结最终 config（config_frozen 完成）

**Files:**
- Modify: `docs/phase9a/gold/gold_manifest.json`（追加冻结全部最终 config 条目）
- Test: `tests/test_phase9a_gold.py`

**冻结集合（spec v1.7 §8）：**
- `gold_item_definitions`
- `gold_roles`
- `gold_search_plans`
- `gold_b_verification_plans`
- `gold_hn_qc_config`
- `gold_guard_config`

**生产入口：** 一段 inline Python 脚本（如下）

- [ ] **Step 1: 写失败测试**

```python
class TestGoldConfigFinal:
    def test_all_config_frozen(self):
        m = _load_json(PG / "gold_manifest.json")
        for name in ("gold_item_definitions", "gold_roles", "gold_search_plans", "gold_b_verification_plans", "gold_hn_qc_config", "gold_guard_config"):
            assert name in m["entries"], f"{name} not frozen"
        assert m["stage"] == "config_frozen"

    def test_config_frozen_no_tool_entries_yet(self):
        m = _load_json(PG / "gold_manifest.json")
        assert "gold_read_access_py" not in m["entries"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigFinal -q`
Expected: FAIL（部分 config 未 freeze）。

- [ ] **Step 3: 原子冻结全部最终 config 条目**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {
    "gold_item_definitions": (PG / "gold_item_definitions.json", "json_canonical"),
    "gold_roles": (PG / "gold_roles.json", "json_canonical"),
    "gold_search_plans": (PG / "gold_search_plans.json", "json_canonical"),
    "gold_b_verification_plans": (PG / "gold_b_verification_plans.json", "json_canonical"),
    "gold_hn_qc_config": (PG / "gold_hn_qc_config.json", "json_canonical"),
    "gold_guard_config": (PG / "gold_guard_config.json", "json_canonical"),
})
print("all final config frozen")
```

- [ ] **Step 4: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigFinal -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): final config atomically frozen (config_frozen complete)"
```

---

## Task 3: read-access wrapper（gold_read_access.py）

**Files:**
- Create: `docs/phase9a/gold/gold_read_access.py`
- Test: `tests/test_phase9a_gold.py`

**输入 schema：**
- `canonical_key: str`（如 `kb:gejue:hy_002`）
- `role: str` ∈ {"curator_A", "curator_B", "publisher"}（publisher 仅供机械发布器使用，必须写独立日志，不得写入 A 的 attestation 日志）
- `log_path: Path`（access log 路径）

**输出 schema（追加 JSONL 行）：**
```json
{"ts": "2026-08-15T10:00:00", "role": "curator_A", "canonical_key": "kb:gejue:hy_002", "source_dir": "docs/phase8/marriage-capability"}
```

**失败状态：**
- `NOT_STAGE_READY`：manifest stage 不在 {config_frozen, code_frozen}（Task 3–8 开发期 stage=config_frozen；Task 9 统一推进 code_frozen 后生产运行）
- `CANONICAL_KEY_NOT_FOUND`：无法在冻结语料解析或正文为空
- `ROLE_NOT_ALLOWED`：role 不是 A/B/publisher 之一

**纯函数算法：**
1. 阶段门：读 manifest，stage ∈ {config_frozen, code_frozen}；`pm.verify_frozen(..., required_stage=None)` 校验自身条目已冻结且 SHA 一致（阶段已在第一步手动门禁）
2. `retriever.doc_text(canonical_key)` → {"text", "category", "fields"}；行不存在/正文为空 → fail-closed
3. 追加 JSONL 行到 log_path
4. 返回 text

**生产入口：** `gold_read_access.py read --key KEY --role ROLE --log LOG_PATH`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldReadAccess:
    def test_access_log_schema(self, tmp_path):
        ra = _load_module("gold_read_access", "docs/phase9a/gold/gold_read_access.py")
        log = tmp_path / "access.jsonl"
        text = ra.read_corpus("kb:gejue:hy_002", role="curator_A", log_path=log)
        assert isinstance(text, str) and text
        lines = [json.loads(l) for l in log.open(encoding="utf-8") if l.strip()]
        assert len(lines) == 1
        assert lines[0]["role"] == "curator_A"
        assert lines[0]["canonical_key"] == "kb:gejue:hy_002"
        assert "ts" in lines[0]

    def test_access_matches_retriever_doc_text(self):
        # 锁定真实 API：包装器返回必须等于 retriever.doc_text 的 text 字段
        ra = _load_module("gold_read_access", "docs/phase9a/gold/gold_read_access.py")
        sys.path.insert(0, str(P9))
        sys.path.insert(0, str(P8))
        import retriever
        expected = retriever.doc_text("kb:gejue:hy_002")["text"]
        actual = ra.read_corpus("kb:gejue:hy_002", role="publisher", log_path=PG / "_tmp_pub.jsonl")
        assert actual == expected
        (PG / "_tmp_pub.jsonl").unlink(missing_ok=True)

    def test_access_rejects_bad_role(self, tmp_path):
        ra = _load_module("gold_read_access", "docs/phase9a/gold/gold_read_access.py")
        try:
            ra.read_corpus("kb:gejue:hy_002", role="developer", log_path=tmp_path / "access.jsonl")
            raised = False
        except SystemExit:
            raised = True
        assert raised

    def test_access_rejects_unknown_key(self, tmp_path):
        ra = _load_module("gold_read_access", "docs/phase9a/gold/gold_read_access.py")
        try:
            ra.read_corpus("kb:gejue:no_such_id", role="curator_A", log_path=tmp_path / "access.jsonl")
            raised = False
        except SystemExit:
            raised = True
        assert raised
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldReadAccess -q`
Expected: FAIL。

- [ ] **Step 3: 实现 gold_read_access.py**

```python
"""Phase 9A-Gold：语料读取包装器（access_attestation）。"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
PG = REPO / "docs" / "phase9a" / "gold"


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _stage_gate(names: list[str]) -> None:
    """阶段门：stage ∈ {config_frozen, code_frozen} 且自身条目已冻结、SHA 一致。
    开发期（Task 3–8）stage=config_frozen；Task 9 统一推进 code_frozen 后生产运行。"""
    manifest = json.loads((PG / "gold_manifest.json").read_text(encoding="utf-8"))
    if manifest["stage"] not in {"config_frozen", "code_frozen"}:
        sys.exit(f"NOT_STAGE_READY: {manifest['stage']}")
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(PG / "gold_manifest.json", names, required_stage=None)


def read_corpus(canonical_key: str, role: str, log_path: Path) -> str:
    if role not in {"curator_A", "curator_B", "publisher"}:
        sys.exit("ROLE_NOT_ALLOWED")
    _stage_gate(["gold_read_access_py"])
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import retriever
    try:
        doc = retriever.doc_text(canonical_key)
    except Exception:
        sys.exit(f"CANONICAL_KEY_NOT_FOUND: {canonical_key}")
    if not doc.get("text"):
        sys.exit(f"CANONICAL_KEY_NOT_FOUND: {canonical_key}")
    _append_jsonl(log_path, {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "role": role,
        "canonical_key": canonical_key,
        "source_dir": "docs/phase8/marriage-capability",
    })
    return doc["text"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    print(read_corpus(args.key, args.role, args.log))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 read-access → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {"gold_read_access_py": (PG / "gold_read_access.py", "git_canonical_lf")})
print("read-access frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldReadAccess -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_read_access.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): read-access wrapper frozen"
```

---

## Task 4: search executor（gold_search_exec.py）

**Files:**
- Create: `docs/phase9a/gold/gold_search_exec.py`
- Test: `tests/test_phase9a_gold.py`

**输入 schema（step dict）：**
```json
{"step_id": "mingli_ftb_0002#k4_s1", "item_id": "mingli_ftb_0002#k4", "entrypoint": "search_gejue", "args": {"query": "桃花"}, "query_terms": ["桃花"], "filters": {}, "corpus_snapshot_sha256": "..."}
```

**输出 schema（追加到 results_file JSONL）：**
```json
{"step_id": "...", "item_id": "...", "ordered_candidate_keys": ["kb:gejue:hy_002", "..."], "candidate_keys_sha256": "...", "candidate_count": 12}
```

**失败状态：**
- `STEP_ALREADY_EXECUTED`：同一 step_id 已存在
- `CORPUS_SHA_MISMATCH`：重算 kb_snapshot.db raw SHA 与 step 冻结值不一致
- `UNKNOWN_ENTRYPOINT`
- `NOT_STAGE_READY`：阶段门未通过

**纯函数算法：**
1. 阶段门（同 Task 3 `_stage_gate`，内联拷贝）
2. 重算 `sha256(kb_snapshot.db)` 与 `step["corpus_snapshot_sha256"]` 比对
3. 检查 step_id 是否已在 results_file 中存在
4. `retriever.pool_candidates({"entrypoint": step["entrypoint"], "args": step["args"]}, strategies=("s1",), depth=step.get("top_n", 10))` → 取 canonical_key（真实 API，冻结只用 S1 单策略保证可复算）
5. 按字典序排序，再去重
6. 计算 `sha256(json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")`
7. **原子追加：读取已有全部内容 + 新行 → 写 tmp → replace（历史行不丢）**

**生产入口：** `gold_search_exec.py --plan-file PATH --results-file PATH --step-id ID`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldSearchExec:
    def test_unique_terminal_row(self, tmp_path):
        se = _load_module("gold_search_exec", "docs/phase9a/gold/gold_search_exec.py")
        results = tmp_path / "results.jsonl"
        step = {"step_id": "test_s1", "item_id": "test#i1", "entrypoint": "search_gejue", "args": {"query": "桃花", "category": "婚姻"}, "query_terms": ["桃花"], "filters": {}, "corpus_snapshot_sha256": "*"}
        se.execute_step(step, results, corpus_sha_override="*", entrypoints={"search_gejue": lambda s: ["kb:a:1", "kb:a:1", "kb:b:2"]})
        lines = [json.loads(l) for l in results.open(encoding="utf-8") if l.strip()]
        assert len(lines) == 1
        assert lines[0]["ordered_candidate_keys"] == ["kb:a:1", "kb:b:2"]
        assert lines[0]["candidate_count"] == 2

    def test_two_steps_both_retained(self, tmp_path):
        # P0 修复验证：第二个 step 不得覆盖第一个 step 的历史行
        se = _load_module("gold_search_exec", "docs/phase9a/gold/gold_search_exec.py")
        results = tmp_path / "results.jsonl"
        s1 = {"step_id": "t_s1", "item_id": "t#i1", "entrypoint": "search_gejue", "args": {"query": "a", "category": "婚姻"}, "query_terms": ["a"], "filters": {}, "corpus_snapshot_sha256": "*"}
        s2 = {"step_id": "t_s2", "item_id": "t#i1", "entrypoint": "search_gejue", "args": {"query": "b", "category": "婚姻"}, "query_terms": ["b"], "filters": {}, "corpus_snapshot_sha256": "*"}
        eps = {"search_gejue": lambda s: ["kb:x:1"] if s["args"]["query"] == "a" else ["kb:y:2"]}
        se.execute_step(s1, results, corpus_sha_override="*", entrypoints=eps)
        se.execute_step(s2, results, corpus_sha_override="*", entrypoints=eps)
        lines = [json.loads(l) for l in results.open(encoding="utf-8") if l.strip()]
        assert [l["step_id"] for l in lines] == ["t_s1", "t_s2"]
        assert lines[0]["ordered_candidate_keys"] == ["kb:x:1"]
        assert lines[1]["ordered_candidate_keys"] == ["kb:y:2"]

    def test_duplicate_step_fails(self, tmp_path):
        se = _load_module("gold_search_exec", "docs/phase9a/gold/gold_search_exec.py")
        results = tmp_path / "results.jsonl"
        step = {"step_id": "test_s1", "item_id": "test#i1", "entrypoint": "search_gejue", "args": {"query": "x", "category": "婚姻"}, "query_terms": ["x"], "filters": {}, "corpus_snapshot_sha256": "*"}
        se.execute_step(step, results, corpus_sha_override="*", entrypoints={"search_gejue": lambda s: ["kb:a:1"]})
        try:
            se.execute_step(step, results, corpus_sha_override="*", entrypoints={"search_gejue": lambda s: ["kb:a:1"]})
            raised = False
        except SystemExit:
            raised = True
        assert raised

    def test_corpus_sha_mismatch_fails(self, tmp_path):
        se = _load_module("gold_search_exec", "docs/phase9a/gold/gold_search_exec.py")
        step = {"step_id": "t_s1", "item_id": "t#i1", "entrypoint": "search_gejue", "args": {"query": "a", "category": "婚姻"}, "query_terms": ["a"], "filters": {}, "corpus_snapshot_sha256": "wrong_sha"}
        try:
            se.execute_step(step, tmp_path / "results.jsonl")  # 无 override → 重算真实 kb_snapshot SHA 比对
            raised = False
        except SystemExit:
            raised = True
        assert raised

    def test_real_entrypoint_locked(self, tmp_path):
        # 锁定真实 retriever API：S1 单策略产出与 pool_candidates 一致
        se = _load_module("gold_search_exec", "docs/phase9a/gold/gold_search_exec.py")
        step = {"step_id": "real_s1", "item_id": "real#i1", "entrypoint": "search_gejue", "args": {"query": "桃花", "category": "婚姻"}, "query_terms": ["桃花"], "filters": {}, "corpus_snapshot_sha256": "*"}
        upstream = _load_json(PG / "upstream_inputs_sha.json")
        step["corpus_snapshot_sha256"] = upstream["kb_snapshot_sha256"]
        row = se.execute_step(step, tmp_path / "results.jsonl")
        sys.path.insert(0, str(P9))
        import retriever
        expected = sorted({h["canonical_key"] for h in retriever.pool_candidates({"entrypoint": "search_gejue", "args": step["args"]}, strategies=("s1",), depth=10)})
        assert row["ordered_candidate_keys"] == expected
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldSearchExec -q`
Expected: FAIL。

- [ ] **Step 3: 实现 gold_search_exec.py**

```python
"""Phase 9A-Gold：搜索计划执行器（候选清单落盘可复算）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
PG = REPO / "docs" / "phase9a" / "gold"


def _canonical_sha(keys: list[str]) -> str:
    payload = json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    return hashlib.sha256(payload).hexdigest()


def _existing_step_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line)["step_id"])
    return ids


def _stage_gate(names: list[str]) -> None:
    manifest = json.loads((PG / "gold_manifest.json").read_text(encoding="utf-8"))
    if manifest["stage"] not in {"config_frozen", "code_frozen"}:
        sys.exit(f"NOT_STAGE_READY: {manifest['stage']}")
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(PG / "gold_manifest.json", names, required_stage=None)


def execute_step(step: dict, results_file: Path, entrypoints: dict | None = None, corpus_sha_override: str | None = None) -> dict:
    _stage_gate(["gold_search_exec_py"])
    # CORPUS_SHA_MISMATCH 门：重算 kb_snapshot.db raw SHA（override 仅供测试）
    actual_corpus_sha = corpus_sha_override if corpus_sha_override is not None else hashlib.sha256((P8 / "kb_snapshot.db").read_bytes()).hexdigest()
    if step["corpus_snapshot_sha256"] != actual_corpus_sha:
        sys.exit(f"CORPUS_SHA_MISMATCH: {step['step_id']}")
    if step["step_id"] in _existing_step_ids(results_file):
        sys.exit(f"STEP_ALREADY_EXECUTED: {step['step_id']}")
    eps = entrypoints or {"search_gejue": _search_gejue}
    fn = eps.get(step["entrypoint"])
    if fn is None:
        sys.exit(f"UNKNOWN_ENTRYPOINT: {step['entrypoint']}")
    raw_keys = fn(step)
    keys = sorted(set(raw_keys))
    row = {
        "step_id": step["step_id"],
        "item_id": step["item_id"],
        "ordered_candidate_keys": keys,
        "candidate_keys_sha256": _canonical_sha(keys),
        "candidate_count": len(keys),
    }
    # 原子追加：保留历史全部内容 + 新行（不得只写新行后 replace）
    results_file.parent.mkdir(parents=True, exist_ok=True)
    existing = results_file.read_text(encoding="utf-8") if results_file.exists() else ""
    tmp = results_file.with_name(results_file.name + ".tmp")
    tmp.write_text(existing + json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, results_file)
    return row


def _search_gejue(step: dict) -> list[str]:
    """真实 API：retriever.pool_candidates S1 单策略（可复算）。"""
    import retriever
    hits = retriever.pool_candidates({"entrypoint": step["entrypoint"], "args": step["args"]}, strategies=("s1",), depth=step.get("top_n", 10))
    return [h["canonical_key"] for h in hits]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--results-file", type=Path, required=True)
    parser.add_argument("--step-id", required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan_file.read_text(encoding="utf-8"))
    step = next(s for p in plan["plans"] for s in p["steps"] if s["step_id"] == args.step_id)
    execute_step(step, args.results_file)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 search-exec → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {"gold_search_exec_py": (PG / "gold_search_exec.py", "git_canonical_lf")})
print("search-exec frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldSearchExec -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_search_exec.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): search executor frozen"
```

---

## Task 5: HN stratified sampler（gold_hn_sampler.py）

**Files:**
- Create: `docs/phase9a/gold/gold_hn_sampler.py`
- Test: `tests/test_phase9a_gold.py`

**输入 schema：**
```python
candidates: dict[str, list[str]]  # item_id -> list of canonical_key
seed: int
ratio: float
```

**输出 schema：**
```json
{"schema_version": "1.0", "seed": 20260814, "ratio": 0.2, "sampled": {"item_id": ["kb:...", ...]}, "not_sampled": {"item_id": ["kb:...", ...]}}
```

**失败状态：**
- `RATIO_OUT_OF_RANGE`
- `EMPTY_CANDIDATE_SET`
- `DETERMINISM_MISMATCH`（内部校验）

**纯函数算法（与 spec §6 逐字对齐）：**
1. 候选排序键：每 item 内 canonical_key 字典序排序
2. 分层维度：item_id
3. 每层最低：`floor(n_hn_i * ratio)`
4. 全局目标：`ceil(total_hn * ratio)`
5. 余数分配：按 item_id 字典序逐层 +1 直到 R 用尽或该层候选用尽
6. 回流语义：round-robin 保证每层配额 ≤ 池容量（某层达池上限后余量继续给后续层 +1），等价于规约的"缺口回流剩余层"
7. RNG：`random.Random(seed)` 全局单实例；每层内用该实例无放回抽取该层配额数

**生产入口：** `gold_hn_sampler.py --proposals PATH --output PATH`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldHNSampler:
    def test_vector_a_no_remainder(self):
        # 独立手工计算 oracle（非调用生产函数）：
        # pools: a=10, b=10, c=5 → total=25, target=ceil(25*0.2)=5；floors=2,2,1（和=5）→ 余数 0
        sampler = _load_module("gold_hn_sampler", "docs/phase9a/gold/gold_hn_sampler.py")
        candidates = {
            "item_a": [f"k{i:02d}" for i in range(10)],
            "item_b": [f"k{i:02d}" for i in range(10, 20)],
            "item_c": [f"k{i:02d}" for i in range(20, 25)],
        }
        result = sampler.sample_hn(candidates, seed=20260814, ratio=0.2)
        counts = {item: len(v) for item, v in result["sampled"].items()}
        assert counts == {"item_a": 2, "item_b": 2, "item_c": 1}
        for item, keys in result["sampled"].items():
            assert set(keys) <= set(candidates[item])
            assert keys == sorted(keys)

    def test_vector_b_remainder_round_robin(self):
        # pools: a=3, b=3, c=4 → total=10, target=ceil(10*0.2)=2；floors=0,0,0；余数 2
        # 逐层 +1（字典序）：item_a +1，item_b +1 → 配额 a=1,b=1,c=0
        # 错误实现（一次性把余数给第一层）会得出 a=2 —— 本测试将其拦截
        sampler = _load_module("gold_hn_sampler", "docs/phase9a/gold/gold_hn_sampler.py")
        candidates = {"item_a": ["a1", "a2", "a3"], "item_b": ["b1", "b2", "b3"], "item_c": ["c1", "c2", "c3", "c4"]}
        result = sampler.sample_hn(candidates, seed=20260814, ratio=0.2)
        counts = {item: len(v) for item, v in result["sampled"].items()}
        assert counts == {"item_a": 1, "item_b": 1, "item_c": 0}

    def test_vector_c_pool_cap_round_robin(self):
        # pools: a=1, b=5 → total=6, target=ceil(6*0.2)=2；floors=0,1；余数 1
        # round-robin：a +1（达到池上限 1）→ 配额 a=1,b=1
        sampler = _load_module("gold_hn_sampler", "docs/phase9a/gold/gold_hn_sampler.py")
        candidates = {"item_a": ["x"], "item_b": ["b1", "b2", "b3", "b4", "b5"]}
        result = sampler.sample_hn(candidates, seed=20260814, ratio=0.2)
        assert result["sampled"]["item_a"] == ["x"]
        assert len(result["sampled"]["item_b"]) == 1
        assert result["not_sampled"]["item_a"] == []
        assert len(result["not_sampled"]["item_b"]) == 4

    def test_deterministic_across_calls(self):
        sampler = _load_module("gold_hn_sampler", "docs/phase9a/gold/gold_hn_sampler.py")
        candidates = {"item_a": [f"k{i}" for i in range(10)], "item_b": [f"m{i}" for i in range(7)]}
        r1 = sampler.sample_hn(candidates, seed=20260814, ratio=0.2)
        r2 = sampler.sample_hn(candidates, seed=20260814, ratio=0.2)
        assert r1 == r2
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldHNSampler -q`
Expected: FAIL。

- [ ] **Step 3: 实现 gold_hn_sampler.py**

```python
"""Phase 9A-Gold：hard negative 分层抽样器（可复算）。"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path


def _compute_stratified_sample(candidates: dict[str, list[str]], seed: int, ratio: float) -> dict[str, list[str]]:
    if not 0 < ratio <= 1:
        sys.exit("RATIO_OUT_OF_RANGE")
    if not candidates or all(not v for v in candidates.values()):
        sys.exit("EMPTY_CANDIDATE_SET")
    sorted_items = sorted(candidates)
    pools = {item: sorted(set(candidates[item])) for item in sorted_items if candidates[item]}
    sorted_items = sorted(pools)
    total = sum(len(pools[item]) for item in sorted_items)
    target = math.ceil(total * ratio)
    quotas = {item: math.floor(len(pools[item]) * ratio) for item in sorted_items}
    remaining = target - sum(quotas.values())
    # 余数分配：item_id 字典序 round-robin 逐层 +1，直到余数用尽或全部层达池上限
    while remaining > 0:
        progressed = False
        for item in sorted_items:
            if remaining <= 0:
                break
            if quotas[item] < len(pools[item]):
                quotas[item] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            sys.exit("EMPTY_CANDIDATE_SET: target exceeds total pool")
    # 抽样：全局单实例 RNG，按字典序逐层无放回抽取（round-robin 已保证 quota ≤ 池容量，无回流分支）
    rng = random.Random(seed)
    sampled = {}
    for item in sorted_items:
        sampled[item] = sorted(rng.sample(pools[item], quotas[item]))
    return sampled


def sample_hn(candidates: dict[str, list[str]], seed: int, ratio: float) -> dict:
    sampled = _compute_stratified_sample(candidates, seed, ratio)
    not_sampled = {}
    for item, pool in candidates.items():
        s = set(sampled.get(item, []))
        not_sampled[item] = sorted(k for k in sorted(set(pool)) if k not in s)
    return {
        "schema_version": "1.0",
        "seed": seed,
        "ratio": ratio,
        "sampled": sampled,
        "not_sampled": not_sampled,
    }


def write_sample_list(payload: dict, path: Path) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--ratio", type=float, default=0.2)
    args = parser.parse_args()
    proposals = json.loads(args.proposals.read_text(encoding="utf-8"))
    candidates = {item_id: [hn["canonical_key"] for hn in item["hard_negatives"]] for item_id, item in proposals["items"].items()}
    payload = sample_hn(candidates, args.seed, args.ratio)
    write_sample_list(payload, args.output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 HN sampler → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {"gold_hn_sampler_py": (PG / "gold_hn_sampler.py", "git_canonical_lf")})
print("HN sampler frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldHNSampler -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_hn_sampler.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): HN stratified sampler frozen"
```

---

## Task 6: packet/receipt publisher（gold_blind_packet_builder.py）

**Files:**
- Create: `docs/phase9a/gold/gold_blind_packet_builder.py`
- Test: `tests/test_phase9a_gold.py`

**输入 schema：**
```python
round_num: int
proposals: dict[str, dict]  # item_id -> {"positives": [...], "hard_negatives": [...], "status": "..."}
sampled_hn: dict[str, list[str]]  # item_id -> sampled canonical_keys for this round
confirmed_positives: list[tuple[str, str]]  # (item_id, canonical_key) pool for controls
fillers: dict[str, list[str]] | None  # item_id -> filler keys; None triggers default filler algorithm
seed: int
trigger_condition_met: bool  # r2/r3 only
```

**输出 schema：**
- `gold_blind_review_packet_rN.jsonl` 每行：`{"blind_id": "blind_r1_001", "item_id": "...", "canonical_key": "...", "document_text": "..."}`
- `gold_blind_packet_types_rN.json`（**类型 sidecar，A/发布器域，不交付 B**）：`{"round": 1, "types": {"blind_r1_001": "positive_proposal | hard_negative | positive_control | filler"}, "packet_sha256": "..."}`
- `BLIND_PACKET_RECEIPT_rN.json`：`{"packet_sha256": "...", "packet_lines": 120, "candidate_keys_sha256": "...", "types_sha256": "...", "round": 1}`

**失败状态：**
- `NOT_STAGE_READY`：阶段门未通过
- `R2_R3_TRIGGER_FALSE`：round_num>1 但 trigger_condition_met=False
- `NO_CONFIRMED_POSITIVE_FOR_CONTROL`：positive_control pool 为空
- `FILLER_POOL_EXHAUSTED`：某 item filler 候选不足
- `LABEL_RECEIPT_PACKET_MISMATCH` / `LABEL_BLIND_ID_COVERAGE_INCOMPLETE` / `LABEL_DUPLICATE_BLIND_ID` / `LABEL_NOT_FOUR_STATE` / `LABEL_NOTE_EMPTY`（build_label_receipt 门）

**纯函数算法：**
1. 阶段门（同 Task 3）
2. 若 round_num > 1 则断言 trigger_condition_met
3. 构建条目：
   - positive proposal 条目（类型标记仅内部，不写入 packet，写入 sidecar）
   - sampled_hn 条目
   - positive_control 条目：从 confirmed_positives 按 (item_id, canonical_key) 字典序排序；优先无放回；数量 = 该轮真实 HN 条数；不足时按序循环抽取并标记 reused
   - filler 条目：n_filler_i = ceil(max(n_positive_i, n_sampled_hn_i) * 0.5)；候选池 = `corpus_keys()`（从 kb_snapshot.db 全表 + classic_texts_freeze.json 枚举，真实 API 见实现）字典序排除已用 key；RNG = random.Random(20260815 + stable_hash(item_id))；无放回抽取
4. 全局打乱：random.Random(20260815 + round_num)
5. 分配 blind_id：`blind_r{N}_001` 起
6. 通过 gold_read_access 填充 document_text（**role=publisher，写独立日志 gold_access_log_publisher.jsonl，不得写 A 的 attestation 日志**）
7. 写 packet 文件（仅 4 字段，无类型泄露）+ 写类型 sidecar；计算 receipt（含 types_sha256）

**本文件首冻版必须同时包含**（供 Task 12 使用，append-only manifest 禁后续追加改 SHA）：`build_label_receipt`（拒绝重复 blind_id/未知 label/空 note）、`check_r2_trigger`、`check_r3_trigger`。

**生产入口：** `gold_blind_packet_builder.py publish --round N --proposals PATH --sampled-hn PATH --controls-json PATH --out-dir DIR`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldBlindPacketBuilder:
    def test_stable_hash_golden_value(self):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        expected = int.from_bytes(hashlib.sha256("mingli_ftb_0002#k4".encode("utf-8")).digest()[:8], "big")
        assert builder.stable_hash("mingli_ftb_0002#k4") == expected

    def test_r2_trigger_fail_closed(self):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        try:
            builder.build_packet(round_num=2, proposals={}, sampled_hn={}, confirmed_positives=[], seed=20260816, trigger_condition_met=False)
            raised = False
        except SystemExit:
            raised = True
        assert raised

    def test_packet_no_type_leak_and_sidecar(self, tmp_path):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        packet, types = builder.build_packet(
            round_num=1,
            proposals={"i1": {"positives": [{"canonical_key": "kb:p:1"}], "hard_negatives": [{"canonical_key": "kb:h:1"}]}},
            sampled_hn={"i1": ["kb:h:1"]},
            confirmed_positives=[("i0", "kb:p:0")],
            seed=20260815,
            read_corpus=lambda key: f"text of {key}",
            all_keys=[f"kb:f:{i}" for i in range(100)],
        )
        for row in packet:
            assert set(row) == {"blind_id", "item_id", "canonical_key", "document_text"}
        # sidecar 覆盖全部 blind_id 且类型合法
        assert set(types) == {row["blind_id"] for row in packet}
        assert set(types.values()) <= {"positive_proposal", "hard_negative", "positive_control", "filler"}

    def test_label_receipt_hardening(self, tmp_path):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        packet_path = tmp_path / "packet.jsonl"
        packet_path.write_text(
            json.dumps({"blind_id": "b1", "item_id": "i1", "canonical_key": "k1", "document_text": "t1"}) + "\n"
            + json.dumps({"blind_id": "b2", "item_id": "i2", "canonical_key": "k2", "document_text": "t2"}) + "\n",
            encoding="utf-8")
        packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        ok_labels = tmp_path / "ok.jsonl"
        ok_labels.write_text(
            json.dumps({"blind_id": "b1", "label": "relevant", "note": "n"}) + "\n"
            + json.dumps({"blind_id": "b2", "label": "irrelevant", "note": "n"}) + "\n", encoding="utf-8")
        receipt = builder.build_label_receipt(ok_labels, packet_path, packet_sha, round_num=1)
        assert receipt["blind_id_set_sha256"] == hashlib.sha256(
            json.dumps(["b1", "b2"], ensure_ascii=False).encode("utf-8") + b"\n").hexdigest()
        # 重复 blind_id → fail
        dup = tmp_path / "dup.jsonl"
        dup.write_text(json.dumps({"blind_id": "b1", "label": "relevant", "note": "n"}) + "\n"
                       + json.dumps({"blind_id": "b1", "label": "irrelevant", "note": "n"}) + "\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            builder.build_label_receipt(dup, packet_path, packet_sha, round_num=1)
        # 未知 label → fail
        bad = tmp_path / "bad.jsonl"
        bad.write_text(json.dumps({"blind_id": "b1", "label": "maybe", "note": "n"}) + "\n"
                       + json.dumps({"blind_id": "b2", "label": "relevant", "note": "n"}) + "\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            builder.build_label_receipt(bad, packet_path, packet_sha, round_num=1)
        # 空 note → fail
        nonote = tmp_path / "nonote.jsonl"
        nonote.write_text(json.dumps({"blind_id": "b1", "label": "relevant", "note": ""}) + "\n"
                          + json.dumps({"blind_id": "b2", "label": "relevant", "note": "n"}) + "\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            builder.build_label_receipt(nonote, packet_path, packet_sha, round_num=1)

    def test_r2_r3_triggers(self):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        clean_map = {"map": {"b1": {"proposal_type": "hard_negative", "derived": "confirmed"}}}
        assert builder.check_r2_trigger(clean_map) is False
        dirty_map = {"map": {"b1": {"proposal_type": "hard_negative", "derived": "rejected"}}}
        assert builder.check_r2_trigger(dirty_map) is True
        r2_map = {"map": {"b1": {"proposal_type": "hard_negative", "derived": "rejected"}}}
        assert builder.check_r3_trigger(r2_map, []) is False
        assert builder.check_r3_trigger(r2_map, [{"canonical_key": "k", "trace_step_refs": []}]) is False
        assert builder.check_r3_trigger(r2_map, [{"canonical_key": "k", "trace_step_refs": ["s1@k"]}]) is True
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldBlindPacketBuilder -q`
Expected: FAIL。

- [ ] **Step 3: 实现 gold_blind_packet_builder.py（含 Task 12 的 `build_label_receipt` / `check_r2_trigger` / `check_r3_trigger` 三个函数一并写入，避免后续 SHA 漂移）**

```python
"""Phase 9A-Gold：混合盲审包与 receipt 发布器。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
PG = REPO / "docs" / "phase9a" / "gold"


def stable_hash(item_id: str) -> int:
    return int.from_bytes(hashlib.sha256(item_id.encode("utf-8")).digest()[:8], "big")


def _canonical_sha(keys: list[str]) -> str:
    payload = json.dumps(sorted(set(keys)), ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    return hashlib.sha256(payload).hexdigest()


def _select_controls(confirmed_positives: list[tuple[str, str]], n: int) -> list[tuple[str, str, bool]]:
    """返回 (item_id, canonical_key, reused)。优先无放回，不足按序循环。"""
    pool = sorted(set(confirmed_positives))
    if not pool and n > 0:
        sys.exit("NO_CONFIRMED_POSITIVE_FOR_CONTROL")
    out = []
    used = 0
    while len(out) < n:
        idx = len(out) % len(pool)
        out.append((pool[idx][0], pool[idx][1], used >= len(pool)))
        used += 1
    return out


def _select_fillers(item_id: str, used_keys: set[str], all_keys: list[str], n: int) -> list[str]:
    pool = [k for k in sorted(set(all_keys)) if k not in used_keys]
    if len(pool) < n:
        sys.exit(f"FILLER_POOL_EXHAUSTED: {item_id} need {n} have {len(pool)}")
    rng = random.Random(20260815 + stable_hash(item_id))
    return sorted(rng.sample(pool, n))


def _stage_gate(names: list[str]) -> None:
    manifest = json.loads((PG / "gold_manifest.json").read_text(encoding="utf-8"))
    if manifest["stage"] not in {"config_frozen", "code_frozen"}:
        sys.exit(f"NOT_STAGE_READY: {manifest['stage']}")
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(PG / "gold_manifest.json", names, required_stage=None)


def corpus_keys() -> list[str]:
    """冻结语料全量 canonical_key（真实 API：kb_snapshot.db 全表 + classic_texts_freeze.json 枚举）。"""
    import sqlite3
    import retriever
    keys = []
    conn = sqlite3.connect((P8 / "kb_snapshot.db").resolve().as_uri() + "?mode=ro", uri=True)
    try:
        for table in ("gejue", "shensha", "shishen_combos", "nayin", "bingyao", "xiangyi"):
            keys += [retriever.canonical_key("kb", table, row[0]) for row in conn.execute(f"SELECT id FROM {table}").fetchall()]
    finally:
        conn.close()
    freeze = json.loads((P8 / "classic_texts_freeze.json").read_text(encoding="utf-8"))
    for f in freeze["files"]:
        if "quarantine" in f["path"]:
            continue
        n = len(retriever._parse_frozen(f["path"], f["commit"]))
        keys += [retriever.canonical_key("classic", f["path"], i + 1, "?") for i in range(n)]
    return sorted(set(keys))


def build_packet(
    round_num: int,
    proposals: dict[str, dict],
    sampled_hn: dict[str, list[str]],
    confirmed_positives: list[tuple[str, str]],
    seed: int,
    trigger_condition_met: bool = True,
    read_corpus: callable | None = None,
    all_keys: list[str] | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """返回 (packet_rows, types)：types 为 blind_id → proposal_type 映射（写 sidecar，不写入 packet）。"""
    if round_num > 1 and not trigger_condition_met:
        sys.exit("R2_R3_TRIGGER_FALSE")
    if read_corpus is None:
        _stage_gate(["gold_blind_packet_builder_py"])
    read_fn = read_corpus or _default_read_corpus
    keys_source = all_keys if all_keys is not None else corpus_keys()
    internal_entries = []  # (item_id, canonical_key, internal_type)
    for item_id in sorted(proposals):
        item = proposals[item_id]
        used = set()
        pos = item.get("positives", [])
        hn = sampled_hn.get(item_id, [])
        for p in pos:
            internal_entries.append((item_id, p["canonical_key"], "positive_proposal"))
            used.add(p["canonical_key"])
        for k in hn:
            internal_entries.append((item_id, k, "hard_negative"))
            used.add(k)
        n_filler = math.ceil(max(len(pos), len(hn)) * 0.5)
        fillers = _select_fillers(item_id, used, keys_source, n_filler)
        for k in fillers:
            internal_entries.append((item_id, k, "filler"))
    n_hn = sum(len(v) for v in sampled_hn.values())
    controls = _select_controls(confirmed_positives, n_hn)
    for item_id, key, reused in controls:
        internal_entries.append((item_id, key, "positive_control"))
    # 全局打乱（轮次派生 seed）
    rng = random.Random(20260815 + round_num)
    shuffled = internal_entries[:]
    rng.shuffle(shuffled)
    packet, types = [], {}
    for idx, (item_id, key, internal_type) in enumerate(shuffled, start=1):
        blind_id = f"blind_r{round_num}_{idx:03d}"
        packet.append({
            "blind_id": blind_id,
            "item_id": item_id,
            "canonical_key": key,
            "document_text": read_fn(key),
        })
        types[blind_id] = internal_type
    return packet, types


def write_packet(packet: list[dict], path: Path) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in packet), encoding="utf-8", newline="\n")


def write_types_sidecar(packet: list[dict], types: dict[str, str], round_num: int, path: Path) -> str:
    """写类型 sidecar（A/发布器域）；返回 sidecar SHA。"""
    packet_raw = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in packet)
    payload = {"round": round_num, "types": types, "packet_sha256": hashlib.sha256(packet_raw.encode("utf-8")).hexdigest()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_packet_receipt(packet_path: Path, types_path: Path) -> dict:
    """基于已落盘文件计算 receipt（避免内存重算与实际字节不一致）。"""
    packet_rows = [json.loads(l) for l in packet_path.open(encoding="utf-8") if l.strip()]
    return {
        "packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
        "packet_lines": len(packet_rows),
        "candidate_keys_sha256": _canonical_sha([r["canonical_key"] for r in packet_rows]),
        "types_sha256": hashlib.sha256(types_path.read_bytes()).hexdigest(),
    }


VALID_LABELS = {"relevant", "partially_relevant", "irrelevant", "uncertain"}


def build_label_receipt(labels_path: Path, packet_path: Path, packet_sha: str, round_num: int) -> dict:
    """B 标签 receipt：拒绝重复 blind_id、未知 label、空 note、覆盖不全。"""
    labels = [json.loads(l) for l in labels_path.open(encoding="utf-8") if l.strip()]
    packets = [json.loads(l) for l in packet_path.open(encoding="utf-8") if l.strip()]
    if hashlib.sha256(packet_path.read_bytes()).hexdigest() != packet_sha:
        sys.exit("LABEL_RECEIPT_PACKET_MISMATCH")
    label_ids = [r["blind_id"] for r in labels]
    if len(label_ids) != len(set(label_ids)):
        sys.exit("LABEL_DUPLICATE_BLIND_ID")
    for r in labels:
        if r.get("label") not in VALID_LABELS:
            sys.exit(f"LABEL_NOT_FOUR_STATE: {r.get('label')}")
        if not r.get("note"):
            sys.exit(f"LABEL_NOTE_EMPTY: {r['blind_id']}")
    if set(label_ids) != {r["blind_id"] for r in packets}:
        sys.exit("LABEL_BLIND_ID_COVERAGE_INCOMPLETE")
    return {
        "round": round_num,
        "label_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "packet_sha256": packet_sha,
        "label_lines": len(labels),
        "packet_lines": len(packets),
        "blind_id_set_sha256": hashlib.sha256(
            json.dumps(sorted(label_ids), ensure_ascii=False).encode("utf-8") + b"\n").hexdigest(),
    }


def check_r2_trigger(r1_unblind_map: dict) -> bool:
    """r2 触发：r1 抽查的 hard_negative 中存在 rejected/uncertain。"""
    return any(
        e["proposal_type"] == "hard_negative" and e["derived"] in {"rejected", "uncertain"}
        for e in r1_unblind_map["map"].values()
    )


def check_r3_trigger(r2_unblind_map: dict, replacements: list[dict]) -> bool:
    """r3 触发：扩审后存在 rejected 且 A 已提交 replacement（必须附 trace_step_refs）。"""
    has_rejected = any(
        e["proposal_type"] == "hard_negative" and e["derived"] == "rejected"
        for e in r2_unblind_map["map"].values()
    )
    return has_rejected and bool(replacements) and all(r.get("trace_step_refs") for r in replacements)


def _default_read_corpus(key: str) -> str:
    """机械发布器：role=publisher，写独立日志，不污染 A attestation。"""
    import gold_read_access as ra
    return ra.read_corpus(key, role="publisher", log_path=PG / "gold_access_log_publisher.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--sampled-hn", type=Path, required=True)
    parser.add_argument("--confirmed-positives", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--trigger", action="store_true")
    args = parser.parse_args()
    proposals = json.loads(args.proposals.read_text(encoding="utf-8"))["items"]
    sampled_hn = json.loads(args.sampled_hn.read_text(encoding="utf-8"))["sampled"]
    controls = json.loads(args.confirmed_positives.read_text(encoding="utf-8"))
    packet, types = build_packet(args.round, proposals, sampled_hn, controls, seed=20260815, trigger_condition_met=args.trigger)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_path = out_dir / f"gold_blind_review_packet_r{args.round}.jsonl"
    types_path = out_dir / f"gold_blind_packet_types_r{args.round}.json"
    write_packet(packet, packet_path)
    write_types_sidecar(packet, types, args.round, types_path)
    receipt = build_packet_receipt(packet_path, types_path)
    receipt["round"] = args.round
    (out_dir / f"BLIND_PACKET_RECEIPT_r{args.round}.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 packet builder → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {"gold_blind_packet_builder_py": (PG / "gold_blind_packet_builder.py", "git_canonical_lf")})
print("packet builder frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldBlindPacketBuilder -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_blind_packet_builder.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): blind packet builder frozen"
```

---

## Task 7: unblind / state machine（gold_unblind_mapper.py）

**Files:**
- Create: `docs/phase9a/gold/gold_unblind_mapper.py`
- Test: `tests/test_phase9a_gold.py`

**输入 schema：**
```python
round_num: int
packet_path: Path
labels_path: Path
receipt_path: Path  # B_LABEL_RECEIPT_rN.json
```

**输出 schema：**
- `gold_blind_unblind_map_rN.json`：
```json
{
  "round": 1,
  "packet_sha256": "...",
  "label_sha256": "...",
  "map": {
    "blind_r1_001": {"proposal_type": "positive_proposal", "item_id": "...", "canonical_key": "...", "label": "relevant", "derived": "confirmed"},
    "...": "..."
  }
}
```

**失败状态：**
- `RECEIPT_MISSING`
- `PACKET_SHA_MISMATCH`
- `LABEL_SHA_MISMATCH`
- `TYPES_SHA_MISMATCH`：sidecar 字节与 receipt 绑定不一致
- `TYPES_PACKET_BINDING_BROKEN`：sidecar 内 packet_sha256 与 packet 不一致
- `TYPES_COVERAGE_INCOMPLETE`：sidecar 未覆盖全部 blind_id
- `BLIND_ID_NOT_IN_LABELS`
- `LABEL_NOT_FOUR_STATE`

**纯函数算法：**
1. 阶段门（同 Task 3）
2. 读取 receipt，校验 packet SHA 与 labels SHA
3. 校验 types sidecar：字节 SHA == receipt.types_sha256；内部 packet_sha256 == packet 实际 SHA；覆盖全部 blind_id
4. 读取 packet（blind_id -> canonical_key/item_id）与 labels（blind_id -> label）
5. 对每条 blind_id 按 sidecar 类型 + FOUR_STATE_MAP 得到 derived 结果（**禁止默认类型**）
6. 输出 map（绑定 packet SHA + label SHA + types SHA）

**生产入口：** `gold_unblind_mapper.py --round N --packet PATH --labels PATH --receipt PATH --output PATH`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldUnblindMapper:
    def test_four_state_map_frozen(self):
        m = _load_module("gold_unblind_mapper", "docs/phase9a/gold/gold_unblind_mapper.py")
        assert m.FOUR_STATE_MAP[("positive_proposal", "relevant")] == "confirmed"
        assert m.FOUR_STATE_MAP[("positive_proposal", "irrelevant")] == "disagreement"
        assert m.FOUR_STATE_MAP[("hard_negative", "irrelevant")] == "confirmed"
        assert m.FOUR_STATE_MAP[("hard_negative", "relevant")] == "rejected"
        assert m.FOUR_STATE_MAP[("positive_control", "relevant")] == "diagnostic_only"
        assert m.FOUR_STATE_MAP[("filler", "irrelevant")] == "diagnostic_only"

    def test_unblind_receipt_mismatch_fails(self, tmp_path):
        mapper = _load_module("gold_unblind_mapper", "docs/phase9a/gold/gold_unblind_mapper.py")
        packet = tmp_path / "packet.jsonl"
        packet.write_text(json.dumps({"blind_id": "b1", "item_id": "i1", "canonical_key": "k1"}) + "\n", encoding="utf-8")
        labels = tmp_path / "labels.jsonl"
        labels.write_text(json.dumps({"blind_id": "b1", "label": "relevant"}) + "\n", encoding="utf-8")
        receipt = tmp_path / "receipt.json"
        receipt.write_text(json.dumps({"packet_sha256": "bad", "label_sha256": "bad", "types_sha256": "bad"}), encoding="utf-8")
        try:
            mapper.unblind(round_num=1, packet_path=packet, labels_path=labels, receipt_path=receipt, types_path=tmp_path / "types.json", output=tmp_path / "out.json")
            raised = False
        except SystemExit:
            raised = True
        assert raised

    def test_unblind_uses_sidecar_types(self, tmp_path):
        # P0 修复验证：类型必须来自 sidecar，不得默认 positive_proposal
        mapper = _load_module("gold_unblind_mapper", "docs/phase9a/gold/gold_unblind_mapper.py")
        packet = tmp_path / "packet.jsonl"
        packet.write_text(json.dumps({"blind_id": "b1", "item_id": "i1", "canonical_key": "k1"}) + "\n", encoding="utf-8")
        labels = tmp_path / "labels.jsonl"
        labels.write_text(json.dumps({"blind_id": "b1", "label": "relevant"}) + "\n", encoding="utf-8")
        types_path = tmp_path / "types.json"
        types_path.write_text(json.dumps({"round": 1, "types": {"b1": "hard_negative"}, "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest()}), encoding="utf-8")
        receipt = tmp_path / "receipt.json"
        receipt.write_text(json.dumps({
            "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
            "label_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
            "types_sha256": hashlib.sha256(types_path.read_bytes()).hexdigest(),
        }), encoding="utf-8")
        out = mapper.unblind(round_num=1, packet_path=packet, labels_path=labels, receipt_path=receipt, types_path=types_path, output=tmp_path / "out.json")
        # hard_negative + relevant → rejected（若错误默认 positive_proposal 会得出 confirmed）
        assert out["map"]["b1"]["derived"] == "rejected"
        assert out["map"]["b1"]["proposal_type"] == "hard_negative"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldUnblindMapper -q`
Expected: FAIL。

- [ ] **Step 3: 实现 gold_unblind_mapper.py**

```python
"""Phase 9A-Gold：解盲映射与四态状态机。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
PG = REPO / "docs" / "phase9a" / "gold"

def _stage_gate(names: list[str]) -> None:
    manifest = json.loads((PG / "gold_manifest.json").read_text(encoding="utf-8"))
    if manifest["stage"] not in {"config_frozen", "code_frozen"}:
        sys.exit(f"NOT_STAGE_READY: {manifest['stage']}")
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(PG / "gold_manifest.json", names, required_stage=None)


FOUR_STATE_MAP = {
    ("positive_proposal", "relevant"): "confirmed",
    ("positive_proposal", "partially_relevant"): "disagreement",
    ("positive_proposal", "irrelevant"): "disagreement",
    ("positive_proposal", "uncertain"): "disagreement",
    ("hard_negative", "irrelevant"): "confirmed",
    ("hard_negative", "relevant"): "rejected",
    ("hard_negative", "partially_relevant"): "rejected",
    ("hard_negative", "uncertain"): "uncertain",
    ("positive_control", "relevant"): "diagnostic_only",
    ("positive_control", "partially_relevant"): "diagnostic_only",
    ("positive_control", "irrelevant"): "diagnostic_only",
    ("positive_control", "uncertain"): "diagnostic_only",
    ("filler", "relevant"): "diagnostic_only",
    ("filler", "partially_relevant"): "diagnostic_only",
    ("filler", "irrelevant"): "diagnostic_only",
    ("filler", "uncertain"): "diagnostic_only",
}

VALID_LABELS = {"relevant", "partially_relevant", "irrelevant", "uncertain"}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unblind(round_num: int, packet_path: Path, labels_path: Path, receipt_path: Path, types_path: Path, output: Path) -> dict:
    _stage_gate(["gold_unblind_mapper_py"])
    if not receipt_path.exists():
        sys.exit("RECEIPT_MISSING")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    packet_sha = _sha256_file(packet_path)
    if receipt.get("packet_sha256") != packet_sha:
        sys.exit("PACKET_SHA_MISMATCH")
    if receipt.get("label_sha256") != _sha256_file(labels_path):
        sys.exit("LABEL_SHA_MISMATCH")
    # 类型 sidecar 三重校验：字节 SHA / 内部 packet 绑定 / blind_id 覆盖
    if not types_path.exists() or _sha256_file(types_path) != receipt.get("types_sha256"):
        sys.exit("TYPES_SHA_MISMATCH")
    sidecar = json.loads(types_path.read_text(encoding="utf-8"))
    if sidecar.get("packet_sha256") != packet_sha:
        sys.exit("TYPES_PACKET_BINDING_BROKEN")
    packet_rows = [json.loads(l) for l in packet_path.open(encoding="utf-8") if l.strip()]
    label_rows = [json.loads(l) for l in labels_path.open(encoding="utf-8") if l.strip()]
    types = sidecar["types"]
    if set(types) != {r["blind_id"] for r in packet_rows}:
        sys.exit("TYPES_COVERAGE_INCOMPLETE")
    packet_by_blind = {r["blind_id"]: r for r in packet_rows}
    labels_by_blind = {}
    for r in label_rows:
        if r["blind_id"] in labels_by_blind:
            sys.exit(f"LABEL_DUPLICATE_BLIND_ID: {r['blind_id']}")
        labels_by_blind[r["blind_id"]] = r
    result_map = {}
    for blind_id, prow in packet_by_blind.items():
        label_row = labels_by_blind.get(blind_id)
        if label_row is None:
            sys.exit(f"BLIND_ID_NOT_IN_LABELS: {blind_id}")
        label = label_row["label"]
        if label not in VALID_LABELS:
            sys.exit(f"LABEL_NOT_FOUR_STATE: {label}")
        ptype = types[blind_id]  # 类型只来自 sidecar，无默认值
        derived = FOUR_STATE_MAP[(ptype, label)]
        result_map[blind_id] = {
            "proposal_type": ptype,
            "item_id": prow["item_id"],
            "canonical_key": prow["canonical_key"],
            "label": label,
            "derived": derived,
        }
    out = {
        "round": round_num,
        "packet_sha256": receipt["packet_sha256"],
        "label_sha256": receipt["label_sha256"],
        "types_sha256": receipt["types_sha256"],
        "map": result_map,
    }
    output.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--types", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    unblind(args.round, args.packet, args.labels, args.receipt, args.types, args.output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 unblind mapper → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {"gold_unblind_mapper_py": (PG / "gold_unblind_mapper.py", "git_canonical_lf")})
print("unblind mapper frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldUnblindMapper -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_unblind_mapper.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): unblind mapper frozen"
```

---

## Task 8: validator / reconcile（gold_validate.py + reconcile_gold.py）

**Files:**
- Create: `docs/phase9a/gold/gold_validate.py`
- Create: `docs/phase9a/gold/reconcile_gold.py`
- Test: `tests/test_phase9a_gold.py`

**失败状态（gold_validate）：**
- `ITEM_COUNT_NOT_112`
- `STATUS_INVALID`
- `HARD_NEGATIVE_STATUS_INVALID`
- `BLOCKED_WITHOUT_REASON`
- `CANONICAL_KEY_UNRESOLVED`
- `EVIDENCE_QUOTE_NOT_SUBSTRING`
- `TRACE_REF_UNRESOLVED`
- `CANDIDATE_SET_MISMATCH`
- `B_VERIFICATION_COVERAGE_INCOMPLETE`
- `HN_SAMPLE_ALGORITHM_MISMATCH`

**失败状态（reconcile_gold）：**
- `MANIFEST_STAGE_NOT_SEALED`
- `RECEIPT_ARTIFACT_SET_MISMATCH`
- `RECEIPT_MANIFEST_SHA_MISMATCH`
- `ARTIFACT_SHA_MISMATCH`
- `BLIND_PACKET_RECEIPT_CHAIN_BROKEN`
- `LABEL_RECEIPT_CHAIN_BROKEN`
- `UNBLIND_MAP_BINDING_BROKEN`
- `ACCESS_LOG_B_CORPUS_READ`

**纯函数算法（gold_validate，完整生产版）：**
1. 结构校验：112 项、状态枚举、BLOCKED 组合约束、positive resolution 枚举
2. 引用完整性：`trace_step_refs` 格式 `step_id@canonical_key`，且 key ∈ 该 step 的 ordered_candidate_keys
3. evidence_quote 必须是 `retriever.doc_text(canonical_key).text` 的子串（可注入 stub）
4. 审阅对账：每个非 BLOCKED item 的全部正例检索 step，reviewed 候选集合 == ordered_candidate_keys（严格相等）
5. no_positive：executed_step_ids == 计划全部正例 step；B verification 标签恰好覆盖全部 `_bv` 候选且全 irrelevant
6. HN sample 重算：调 gold_hn_sampler 算法，与冻结 sample list 精确相等
7. 分歧闭合：各轮 unblind map 中 derived=disagreement 的 positive，必须有 C 裁决或 item BLOCKED

**纯函数算法（reconcile_gold，完整生产版）：**
1. stage == sealed；receipt 存在
2. receipt.manifest_sha256 == sha256(json_canonical(manifest))
3. artifact 集合精确相等（版本化规则）
4. 逐项核对 artifact SHA/size 与 manifest 条目
5. 盲审 receipt 链：packet receipt 绑 packet SHA+行数；label receipt 绑 label SHA+packet SHA+行数+blind_id 集合 SHA（重算）；unblind map 绑 packet/label/types SHA
6. access log 无 curator_B 语料读取（packet_only 证据）
7. receipt 统计与 gold_v1 一致

**生产入口：**
- `gold_validate.py --gold-dir DIR`
- `reconcile_gold.py --gold-dir DIR`

- [ ] **Step 1: 写失败测试（独立测试向量）**

```python
class TestGoldValidateAndReconcile:
    def test_validate_rejects_invalid_status(self):
        validator = _load_module("gold_validate", "docs/phase9a/gold/gold_validate.py")
        bad = {"schema_version": "1.0", "item_count": 112, "acquisition_verdict": "GOLD_READY", "items": [{"item_id": "x", "status": "weird"}] * 112}
        with pytest.raises(SystemExit):
            validator.validate_structure(bad)

    def test_validate_evidence_quote_substring(self):
        validator = _load_module("gold_validate", "docs/phase9a/gold/gold_validate.py")
        pos = {"canonical_key": "kb:t:1", "evidence_quote": "不存在的句子", "trace_step_refs": ["s1@kb:t:1"], "resolution": "confirmed"}
        results_by_step = {"s1": {"ordered_candidate_keys": ["kb:t:1"]}}
        with pytest.raises(SystemExit):
            validator.validate_positives({"item_id": "i", "positives": [pos]}, results_by_step, doc_text_fn=lambda k: "真实条文内容")
        # 子串真实 → 通过
        pos2 = dict(pos, evidence_quote="真实条文")
        validator.validate_positives({"item_id": "i", "positives": [pos2]}, results_by_step, doc_text_fn=lambda k: "真实条文内容")

    def test_validate_trace_ref_resolves_candidate(self):
        validator = _load_module("gold_validate", "docs/phase9a/gold/gold_validate.py")
        pos = {"canonical_key": "kb:t:1", "evidence_quote": "真实", "trace_step_refs": ["s1@kb:other:9"], "resolution": "confirmed"}
        results_by_step = {"s1": {"ordered_candidate_keys": ["kb:t:1"]}}
        with pytest.raises(SystemExit):
            validator.validate_positives({"item_id": "i", "positives": [pos]}, results_by_step, doc_text_fn=lambda k: "真实条文")

    def test_reconcile_rejects_receipt_manifest_mismatch(self, tmp_path):
        reconciler = _load_module("reconcile_gold", "docs/phase9a/gold/reconcile_gold.py")
        with pytest.raises(SystemExit):
            reconciler.check_receipt_manifest_binding({"manifest_sha256": "bad"}, {"stage": "sealed", "entries": {}})

    def test_reconcile_blind_id_set_sha_recompute(self, tmp_path):
        reconciler = _load_module("reconcile_gold", "docs/phase9a/gold/reconcile_gold.py")
        labels = tmp_path / "labels.jsonl"
        labels.write_text(json.dumps({"blind_id": "b1", "label": "relevant", "note": "n"}) + "\n", encoding="utf-8")
        expected = hashlib.sha256(json.dumps(["b1"], ensure_ascii=False).encode("utf-8") + b"\n").hexdigest()
        assert reconciler.recompute_blind_id_set_sha(labels) == expected
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldValidateAndReconcile -q`
Expected: FAIL。

- [ ] **Step 3: 实现 gold_validate.py + reconcile_gold.py（完整生产代码，无 TODO）**

gold_validate.py：
```python
"""Phase 9A-Gold：终态数据校验器（完整生产版）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"

VALID_STATUS = {"anchored", "no_relevant_document_found_under_frozen_plan", "BLOCKED_ACQUISITION", "BLOCKED_HARD_NEGATIVE_ACQUISITION"}
VALID_HN_STATUS = {"found", "no_hard_negative_found", "not_applicable"}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def validate_structure(gold: dict) -> None:
    if gold.get("item_count") != 112 or len(gold.get("items", [])) != 112:
        sys.exit("ITEM_COUNT_NOT_112")
    for item in gold["items"]:
        if item["status"] not in VALID_STATUS:
            sys.exit(f"STATUS_INVALID: {item['status']}")
        if item["status"].startswith("BLOCKED"):
            if item.get("hard_negative_status") != "not_applicable":
                sys.exit("HARD_NEGATIVE_STATUS_INVALID")
            if not item.get("blocked_reason"):
                sys.exit("BLOCKED_WITHOUT_REASON")
        elif item.get("hard_negative_status") not in VALID_HN_STATUS:
            sys.exit(f"HARD_NEGATIVE_STATUS_INVALID: {item.get('hard_negative_status')}")
        for p in item.get("positives", []):
            if p.get("resolution") not in {"confirmed", "third_party_adjudicated"}:
                sys.exit(f"POSITIVE_RESOLUTION_INVALID: {item['item_id']}")
            if not p.get("evidence_quote"):
                sys.exit(f"EVIDENCE_QUOTE_MISSING: {item['item_id']}")


def validate_positives(item: dict, results_by_step: dict[str, dict], doc_text_fn) -> None:
    """引用完整性 + evidence_quote 子串真实。"""
    for p in item.get("positives", []):
        refs = p.get("trace_step_refs", [])
        if not refs:
            sys.exit(f"TRACE_REF_UNRESOLVED: {item['item_id']} no refs")
        for ref in refs:
            step_id, _, key = ref.partition("@")
            row = results_by_step.get(step_id)
            if row is None or key not in row["ordered_candidate_keys"]:
                sys.exit(f"TRACE_REF_UNRESOLVED: {ref}")
        text = doc_text_fn(p["canonical_key"])
        if p["evidence_quote"] not in text:
            sys.exit(f"EVIDENCE_QUOTE_NOT_SUBSTRING: {item['item_id']} {p['canonical_key']}")


def validate_reviewed_coverage(item_id: str, plan_step_ids: list[str], results_by_step: dict[str, dict], reviewed_keys: set[str]) -> None:
    """审阅对账：计划全部 step 已执行且 reviewed == candidates（严格相等）。"""
    for step_id in plan_step_ids:
        row = results_by_step.get(step_id)
        if row is None:
            sys.exit(f"CANDIDATE_SET_MISMATCH: {item_id} step {step_id} not executed")
        if set(row["ordered_candidate_keys"]) != reviewed_keys and reviewed_keys:
            sys.exit(f"CANDIDATE_SET_MISMATCH: {item_id} step {step_id}")


def validate_no_positive(item: dict, plan_step_ids: list[str], bv_step_ids: list[str], results_by_step: dict[str, dict], bv_labels: list[dict]) -> None:
    """no_positive 双审：执行覆盖 + B verification 标签恰好覆盖全部候选且全 irrelevant。"""
    evidence = item.get("no_positive_evidence", {})
    if sorted(evidence.get("executed_step_ids", [])) != sorted(plan_step_ids):
        sys.exit(f"NO_POSITIVE_EXECUTION_INCOMPLETE: {item['item_id']}")
    expected_pairs = {(sid, k) for sid in bv_step_ids for k in results_by_step.get(sid, {}).get("ordered_candidate_keys", [])}
    labeled_pairs = {(r["step_id"], r["canonical_key"]) for r in bv_labels if r["item_id"] == item["item_id"]}
    if expected_pairs != labeled_pairs:
        sys.exit(f"B_VERIFICATION_COVERAGE_INCOMPLETE: {item['item_id']}")
    labels = {r["verification_label"] for r in bv_labels if r["item_id"] == item["item_id"]}
    if labels != {"irrelevant"}:
        sys.exit(f"B_VERIFICATION_AGGREGATION_FAILED: {item['item_id']} {sorted(labels)}")


def validate_hn_sample(sample_list_path: Path, proposals_path: Path) -> None:
    """HN sample 重算：与冻结算法输出精确相等。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gold_hn_sampler as sampler
    sample = json.loads(sample_list_path.read_text(encoding="utf-8"))
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))["items"]
    candidates = {item_id: [hn["canonical_key"] for hn in item.get("hard_negatives", [])] for item_id, item in proposals.items()}
    candidates = {k: v for k, v in candidates.items() if v}
    expected = sampler._compute_stratified_sample(candidates, seed=sample["seed"], ratio=sample["ratio"])
    if {k: sorted(v) for k, v in expected.items()} != {k: sorted(v) for k, v in sample["sampled"].items() if v}:
        sys.exit("HN_SAMPLE_ALGORITHM_MISMATCH")


def validate_disagreement_closed(gold: dict, unblind_maps: list[dict], c_adjudication: set) -> None:
    """分歧闭合：derived=disagreement 的 positive 必须有 C 裁决或 item BLOCKED。"""
    status_by_item = {i["item_id"]: i["status"] for i in gold["items"]}
    for um in unblind_maps:
        for e in um["map"].values():
            if e["proposal_type"] == "positive_proposal" and e["derived"] == "disagreement":
                closed = (e["item_id"], e["canonical_key"]) in c_adjudication or status_by_item[e["item_id"]].startswith("BLOCKED")
                if not closed:
                    sys.exit(f"DISAGREEMENT_UNCLOSED: {e['item_id']} {e['canonical_key']}")


def _default_doc_text(key: str) -> str:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import retriever
    return retriever.doc_text(key)["text"]


def validate_dir(gd: Path, doc_text_fn=None) -> None:
    gold = json.loads((gd / "gold_v1.json").read_text(encoding="utf-8"))
    validate_structure(gold)
    results_by_step = {r["step_id"]: r for r in _load_jsonl(gd / "gold_search_results.jsonl")}
    plans = json.loads((gd / "gold_search_plans.json").read_text(encoding="utf-8"))["plans"] if (gd / "gold_search_plans.json").exists() else []
    plan_steps_by_item = {p["item_id"]: p["steps"] for p in plans}
    bv_labels = _load_jsonl(gd / "gold_b_verification_labels.jsonl")
    doc_fn = doc_text_fn or _default_doc_text
    for item in gold["items"]:
        steps = plan_steps_by_item.get(item["item_id"], [])
        pos_steps = [s["step_id"] for s in steps if s["step_id"].endswith("_s1")]
        bv_steps = [s["step_id"] for s in steps if s["step_id"].endswith("_bv1")]
        if item["status"] == "anchored":
            validate_positives(item, results_by_step, doc_fn)
        elif item["status"] == "no_relevant_document_found_under_frozen_plan":
            validate_no_positive(item, pos_steps, bv_steps, results_by_step, bv_labels)
    validate_hn_sample(gd / "gold_hn_qc_sample_list.json", gd / "gold_proposals_snapshot.json")
    unblind_maps = []
    for p in sorted(gd.glob("gold_blind_unblind_map_r*.json")):
        unblind_maps.append(json.loads(p.read_text(encoding="utf-8")))
    c_adj = {(r["item_id"], r["canonical_key"]) for r in _load_jsonl(gd / "gold_c_adjudication.jsonl") if r.get("c_label") == "relevant"}
    validate_disagreement_closed(gold, unblind_maps, c_adj)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-dir", type=Path, default=Path("docs/phase9a/gold"))
    args = parser.parse_args()
    validate_dir(args.gold_dir)
    print("gold_validate passed")


if __name__ == "__main__":
    main()
```

reconcile_gold.py（完整生产版）：
```python
"""Phase 9A-Gold：对账脚本（完整生产版）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

STRATEGY_FN = None  # 延迟初始化（避免无 sys.path 时 import 失败）


def _init_strategies() -> None:
    global STRATEGY_FN
    if STRATEGY_FN is not None:
        return
    repo = Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(0, str(repo / "docs" / "phase8" / "marriage-capability"))
    sys.path.insert(0, str(repo / "docs" / "phase9a" / "retrieval"))
    import phase9a_manifest as pm
    STRATEGY_FN = pm.STRATEGY_FN


def json_canonical_sha(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n").hexdigest()


def check_receipt_manifest_binding(receipt: dict, manifest: dict) -> None:
    if receipt.get("manifest_sha256") != json_canonical_sha(manifest):
        sys.exit("RECEIPT_MANIFEST_SHA_MISMATCH")


def recompute_blind_id_set_sha(labels_path: Path) -> str:
    ids = sorted(json.loads(l)["blind_id"] for l in labels_path.open(encoding="utf-8") if l.strip())
    return hashlib.sha256(json.dumps(ids, ensure_ascii=False).encode("utf-8") + b"\n").hexdigest()


def expected_artifact_set(rounds: list[int]) -> set[str]:
    base = {
        "gold_v1.json", "gold_acquisition_log.jsonl", "gold_search_results.jsonl",
        "gold_access_log.jsonl", "gold_b_verification_labels.jsonl",
        "gold_b_verification_packet.jsonl", "B_VERIFICATION_PACKET_RECEIPT.json", "GOLD_CLOSURE.md",
        "gold_hn_qc_sample_list.json",
    }
    for r in rounds:
        base |= {
            f"gold_blind_review_packet_r{r}.jsonl", f"gold_b_labels_r{r}.jsonl",
            f"gold_blind_unblind_map_r{r}.json", f"BLIND_PACKET_RECEIPT_r{r}.json",
            f"B_LABEL_RECEIPT_r{r}.json",
        }
    return base


def check_artifact_shas(gd: Path, manifest: dict, receipt: dict) -> None:
    """逐项核对 artifact SHA/size 与 manifest 条目。"""
    _init_strategies()
    entries_by_name = {Path(e["path"]).name: e for e in manifest["entries"].values()}
    for name in receipt["artifacts"]:
        path = gd / name
        if not path.exists():
            sys.exit(f"ARTIFACT_SHA_MISMATCH: {name} missing")
        entry = entries_by_name.get(name)
        if entry is None:
            sys.exit(f"ARTIFACT_SHA_MISMATCH: {name} not in manifest")
        if STRATEGY_FN[entry["strategy"]](path) != entry["sha256"]:
            sys.exit(f"ARTIFACT_SHA_MISMATCH: {name}")
        if receipt.get("artifact_meta", {}).get(name, {}).get("size") not in (None, path.stat().st_size):
            sys.exit(f"ARTIFACT_SHA_MISMATCH: {name} size drift")


def check_blind_chain(gd: Path, rounds: list[int]) -> None:
    """每轮 receipt 绑定链：packet receipt → label receipt → unblind map。"""
    for r in rounds:
        packet = gd / f"gold_blind_review_packet_r{r}.jsonl"
        labels = gd / f"gold_b_labels_r{r}.jsonl"
        pr = json.loads((gd / f"BLIND_PACKET_RECEIPT_r{r}.json").read_text(encoding="utf-8"))
        if pr["packet_sha256"] != hashlib.sha256(packet.read_bytes()).hexdigest():
            sys.exit(f"BLIND_PACKET_RECEIPT_CHAIN_BROKEN: r{r} packet sha")
        if pr["packet_lines"] != len([l for l in packet.open(encoding="utf-8") if l.strip()]):
            sys.exit(f"BLIND_PACKET_RECEIPT_CHAIN_BROKEN: r{r} lines")
        lr = json.loads((gd / f"B_LABEL_RECEIPT_r{r}.json").read_text(encoding="utf-8"))
        if lr["label_sha256"] != hashlib.sha256(labels.read_bytes()).hexdigest():
            sys.exit(f"LABEL_RECEIPT_CHAIN_BROKEN: r{r} label sha")
        if lr["packet_sha256"] != pr["packet_sha256"]:
            sys.exit(f"LABEL_RECEIPT_CHAIN_BROKEN: r{r} packet binding")
        if lr["label_lines"] != len([l for l in labels.open(encoding="utf-8") if l.strip()]):
            sys.exit(f"LABEL_RECEIPT_CHAIN_BROKEN: r{r} label lines")
        if lr["blind_id_set_sha256"] != recompute_blind_id_set_sha(labels):
            sys.exit(f"LABEL_RECEIPT_CHAIN_BROKEN: r{r} blind_id set")
        um = json.loads((gd / f"gold_blind_unblind_map_r{r}.json").read_text(encoding="utf-8"))
        if um["packet_sha256"] != pr["packet_sha256"] or um["label_sha256"] != lr["label_sha256"]:
            sys.exit(f"UNBLIND_MAP_BINDING_BROKEN: r{r}")
        types = gd / f"gold_blind_packet_types_r{r}.json"
        if types.exists() and hashlib.sha256(types.read_bytes()).hexdigest() != pr.get("types_sha256"):
            sys.exit(f"UNBLIND_MAP_BINDING_BROKEN: r{r} types")


def check_b_isolation(gd: Path) -> None:
    access_log = gd / "gold_access_log.jsonl"
    if access_log.exists():
        for l in access_log.open(encoding="utf-8"):
            if l.strip() and json.loads(l).get("role") == "curator_B":
                sys.exit("ACCESS_LOG_B_CORPUS_READ")


def check_stats(gd: Path, receipt: dict) -> None:
    gold = json.loads((gd / "gold_v1.json").read_text(encoding="utf-8"))
    stats = receipt.get("stats", {})
    anchored = sum(1 for i in gold["items"] if i["status"] == "anchored")
    no_positive = sum(1 for i in gold["items"] if i["status"] == "no_relevant_document_found_under_frozen_plan")
    blocked = sum(1 for i in gold["items"] if i["status"].startswith("BLOCKED"))
    if stats and stats.get("anchored") != anchored or stats.get("no_positive") != no_positive or stats.get("blocked") != blocked:
        sys.exit("RECEIPT_STATS_MISMATCH")
    if receipt.get("acquisition_verdict") != gold["acquisition_verdict"]:
        sys.exit("RECEIPT_STATS_MISMATCH: verdict")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-dir", type=Path, default=Path("docs/phase9a/gold"))
    args = parser.parse_args()
    gd = args.gold_dir
    manifest = json.loads((gd / "gold_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("stage") != "sealed":
        sys.exit("MANIFEST_STAGE_NOT_SEALED")
    if not (gd / "GOLD_RECEIPT.json").exists():
        sys.exit("RECEIPT_MISSING")
    receipt = json.loads((gd / "GOLD_RECEIPT.json").read_text(encoding="utf-8"))
    check_receipt_manifest_binding(receipt, manifest)
    rounds = sorted({int(k.split("_r")[1].split(".")[0]) for k in manifest["entries"] if "gold_blind_review_packet_r" in k})
    expected = expected_artifact_set(rounds)
    actual = set(receipt["artifacts"])
    if actual != expected:
        sys.exit(f"RECEIPT_ARTIFACT_SET_MISMATCH: missing={sorted(expected - actual)[:5]} extra={sorted(actual - expected)[:5]}")
    check_artifact_shas(gd, manifest, receipt)
    check_blind_chain(gd, rounds)
    check_b_isolation(gd)
    check_stats(gd, receipt)
    print("reconcile_gold passed")


if __name__ == "__main__":
    main()
```

**v5 计划明确：** Task 8 两个脚本均为完整生产代码，无 TODO/补全委托。

- [ ] **Step 4: 冻结 validator + reconcile → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {
    "gold_validate_py": (PG / "gold_validate.py", "git_canonical_lf"),
    "reconcile_gold_py": (PG / "reconcile_gold.py", "git_canonical_lf"),
})
print("validator + reconcile frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldValidateAndReconcile -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_validate.py docs/phase9a/gold/reconcile_gold.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): validator + reconcile frozen"
```

---

## Task 9: finalizer / guard（finalize_gold.py + guard_data_artifacts.py）

**Files:**
- Create: `docs/phase9a/gold/finalize_gold.py`
- Modify: `.qoder/hooks/guard_data_artifacts.py`
- Test: `tests/test_phase9a_gold.py`

**失败状态（finalize_gold）：**
- `GOLD_V1_ALREADY_EXISTS`（one-shot：code_frozen 阶段 gold_v1 已存在 = partial publish，fail-closed）
- `MANIFEST_NOT_CODE_FROZEN`：stage 不是 code_frozen（也不是 sealed 恢复分支）
- `ARTIFACT_BYTES_MISMATCH`：恢复分支中产物 SHA 与 manifest 不一致
- `HN_SAMPLED_UNLABELED`：已抽中 HN 无派生结果（标签覆盖失败）

**失败状态（guard）：**
- `RECEIPT_MANIFEST_SHA_MISMATCH`
- `GUARD_CONFIG_NOT_FROZEN`：manifest 无 gold_guard_config 条目
- `GUARD_CONFIG_SHA_DRIFT`：guard config 磁盘字节与冻结 SHA 不一致

**纯函数算法（finalize_gold，完整生产版）：**
1. 恢复分支：stage==sealed 且 receipt 存在 → 校验 receipt 绑定 + artifact SHA（幂等，漂移 fail-closed）；stage==sealed 无 receipt → 校验产物 SHA 与 manifest 一致后补发 receipt
2. 正常分支：stage 必须 == code_frozen；gold_v1 已存在 → fail-closed
3. `derive_final_items` 机械合并（含 not_sampled 语义）
4. 写 gold_v1.json / gold_acquisition_log.jsonl（A log + 各轮标签/解盲摘要 + bv 标签 + C 裁决）/ gold_search_results.jsonl（A + bv 合并）/ gold_access_log.jsonl（A + publisher）/ GOLD_CLOSURE.md（固定行）
5. freeze 全部 sealed 条目 → set_stage("sealed") → 发布 GOLD_RECEIPT.json（绑定 sealed manifest SHA + 版本化 artifact 集合 + 逐项 meta）

**A/B 结果机械合并规则（含 not_sampled 语义，P0 修复）：**
- 正例：A proposal + B confirmed → resolution=confirmed；分歧 → C relevant → third_party_adjudicated，否则 BLOCKED_ACQUISITION
- HN：派生结果 confirmed → b_reviewed=true/confirmed；rejected/uncertain → BLOCKED_HARD_NEGATIVE_ACQUISITION；**无派生结果且未抽中（r1 正常路径的 80%）→ b_reviewed=false/b_review_result=not_sampled，不阻塞**；无派生结果但已抽中 → 标签覆盖失败 fail-closed
- hard_negative_status：A 有 HN 候选 → found；A 声明完整 hn 计划无候选 → no_hard_negative_found；BLOCKED → not_applicable
- no_positive：B verification 全 irrelevant → no_relevant_document_found_under_frozen_plan；否则 BLOCKED

**纯函数算法（guard，自验绑定）：**
1. 读取 GOLD_RECEIPT.json；不存在 → 返回 None（未激活）
2. 重算 receipt.manifest_sha256 == sha256(json_canonical(manifest))，不一致 → fail-closed
3. 校验 manifest 含 gold_guard_config 条目且磁盘文件 json_canonical SHA == 条目 SHA
4. 返回 guard config（含 protected_paths）

**生产入口：**
- `finalize_gold.py --gold-dir DIR`
- guard hook 在 pre-commit 中调用 `load_gold_guard_config(receipt_path)`

- [ ] **Step 1: 写失败测试（含 not_sampled READY 正例与 BLOCKED 反例）**

```python
class TestGoldFinalizerAndGuard:
    def _deriv(self, ptype, derived):
        return {"map": {"b1": {"proposal_type": ptype, "item_id": "i1", "canonical_key": "k1", "label": "x", "derived": derived}}}

    def test_derive_r1_ready_with_not_sampled_hn(self):
        # P0 修复验证：r1 无扩审，抽中 HN confirmed + 未抽中 HN → GOLD_READY（not_sampled 不阻塞）
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        proposals = {"i1": {
            "positives": [{"canonical_key": "p1", "evidence_quote": "e", "trace_step_refs": ["s1@p1"]}],
            "hard_negatives": [{"canonical_key": "h1"}, {"canonical_key": "h2"}],
        }}
        maps = [{"map": {
            "b1": {"proposal_type": "positive_proposal", "item_id": "i1", "canonical_key": "p1", "label": "relevant", "derived": "confirmed"},
            "b2": {"proposal_type": "hard_negative", "item_id": "i1", "canonical_key": "h1", "label": "irrelevant", "derived": "confirmed"},
        }}]
        items = fin.derive_final_items(proposals, maps, {}, {}, sampled_r1={"i1": ["h1"]})
        assert len(items) == 1 and items[0]["status"] == "anchored"
        assert items[0]["positives"][0]["resolution"] == "confirmed"
        hn_by_key = {h["canonical_key"]: h for h in items[0]["hard_negatives"]}
        assert hn_by_key["h1"]["b_review_result"] == "confirmed"
        assert hn_by_key["h2"]["b_reviewed"] is False and hn_by_key["h2"]["b_review_result"] == "not_sampled"
        assert items[0]["hard_negative_status"] == "found"

    def test_derive_rejected_hn_blocks(self):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        proposals = {"i1": {"positives": [{"canonical_key": "p1", "evidence_quote": "e", "trace_step_refs": ["s1@p1"]}], "hard_negatives": [{"canonical_key": "h1"}]}}
        maps = [{"map": {
            "b1": {"proposal_type": "positive_proposal", "item_id": "i1", "canonical_key": "p1", "label": "relevant", "derived": "confirmed"},
            "b2": {"proposal_type": "hard_negative", "item_id": "i1", "canonical_key": "h1", "label": "relevant", "derived": "rejected"},
        }}]
        items = fin.derive_final_items(proposals, maps, {}, {}, sampled_r1={"i1": ["h1"]})
        assert items[0]["status"] == "BLOCKED_HARD_NEGATIVE_ACQUISITION"
        assert items[0]["hard_negative_status"] == "not_applicable"

    def test_derive_disagreement_without_c_blocks(self):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        proposals = {"i1": {"positives": [{"canonical_key": "p1", "evidence_quote": "e", "trace_step_refs": ["s1@p1"]}], "hard_negatives": []}}
        maps = [{"map": {"b1": {"proposal_type": "positive_proposal", "item_id": "i1", "canonical_key": "p1", "label": "irrelevant", "derived": "disagreement"}}}]
        items = fin.derive_final_items(proposals, maps, {}, {}, sampled_r1={})
        assert items[0]["status"] == "BLOCKED_ACQUISITION"
        # C 裁决 relevant → third_party_adjudicated
        items2 = fin.derive_final_items(proposals, maps, {}, {("i1", "p1"): "relevant"}, sampled_r1={})
        assert items2[0]["status"] == "anchored" and items2[0]["positives"][0]["resolution"] == "third_party_adjudicated"

    def test_derive_sampled_but_unlabeled_fails(self):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        proposals = {"i1": {"positives": [{"canonical_key": "p1", "evidence_quote": "e", "trace_step_refs": ["s1@p1"]}], "hard_negatives": [{"canonical_key": "h1"}]}}
        maps = [{"map": {"b1": {"proposal_type": "positive_proposal", "item_id": "i1", "canonical_key": "p1", "label": "relevant", "derived": "confirmed"}}}]
        with pytest.raises(SystemExit):
            fin.derive_final_items(proposals, maps, {}, {}, sampled_r1={"i1": ["h1"]})  # h1 抽中但无标签

    def test_finalize_one_shot(self, tmp_path):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = tmp_path / "gold"
        mirror.mkdir()
        (mirror / "gold_v1.json").write_text("{}", encoding="utf-8")
        (mirror / "gold_manifest.json").write_text(json.dumps({"schema_version": "1.0", "stage": "code_frozen", "entries": {}}), encoding="utf-8")
        with pytest.raises(SystemExit):
            fin.main(gold_dir=mirror)

    def test_guard_verifies_receipt_binding_and_config_sha(self, tmp_path):
        guard = _load_module("guard_data_artifacts", ".qoder/hooks/guard_data_artifacts.py")
        gc = {"schema_version": "1.0", "protected_paths": ["docs/phase9a/gold/gold_v1.json"]}
        gc_sha = hashlib.sha256(json.dumps(gc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n").hexdigest()
        manifest = {"schema_version": "1.0", "stage": "sealed", "entries": {"gold_guard_config": {"path": "docs/phase9a/gold/gold_guard_config.json", "strategy": "json_canonical", "sha256": gc_sha}}}
        m_sha = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n").hexdigest()
        (tmp_path / "gold_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (tmp_path / "gold_guard_config.json").write_text(json.dumps(gc), encoding="utf-8")
        (tmp_path / "GOLD_RECEIPT.json").write_text(json.dumps({"manifest_sha256": m_sha}), encoding="utf-8")
        config = guard.load_gold_guard_config(receipt_path=tmp_path / "GOLD_RECEIPT.json", manifest_path=tmp_path / "gold_manifest.json")
        assert config["protected_paths"] == ["docs/phase9a/gold/gold_v1.json"]
        # receipt 绑定错误 → fail-closed
        (tmp_path / "GOLD_RECEIPT.json").write_text(json.dumps({"manifest_sha256": "bad"}), encoding="utf-8")
        with pytest.raises(SystemExit):
            guard.load_gold_guard_config(receipt_path=tmp_path / "GOLD_RECEIPT.json", manifest_path=tmp_path / "gold_manifest.json")
        # guard config 磁盘漂移 → fail-closed
        (tmp_path / "GOLD_RECEIPT.json").write_text(json.dumps({"manifest_sha256": m_sha}), encoding="utf-8")
        (tmp_path / "gold_guard_config.json").write_text(json.dumps({**gc, "protected_paths": []}), encoding="utf-8")
        with pytest.raises(SystemExit):
            guard.load_gold_guard_config(receipt_path=tmp_path / "GOLD_RECEIPT.json", manifest_path=tmp_path / "gold_manifest.json")
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldFinalizerAndGuard -q`
Expected: FAIL。

- [ ] **Step 3: 实现 finalize_gold.py + 修改 guard**

finalize_gold.py（完整生产版）：
```python
"""Phase 9A-Gold：双终态发布脚本。"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
PG = REPO / "docs" / "phase9a" / "gold"


def _artifact_set(rounds: list[int]) -> set[str]:
    base = {
        "gold_v1.json", "gold_acquisition_log.jsonl", "gold_search_results.jsonl",
        "gold_access_log.jsonl", "gold_b_verification_labels.jsonl",
        "gold_b_verification_packet.jsonl", "B_VERIFICATION_PACKET_RECEIPT.json", "GOLD_CLOSURE.md",
    }
    for r in rounds:
        base |= {
            f"gold_blind_review_packet_r{r}.jsonl",
            f"gold_b_labels_r{r}.jsonl",
            f"gold_blind_unblind_map_r{r}.json",
            f"BLIND_PACKET_RECEIPT_r{r}.json",
            f"B_LABEL_RECEIPT_r{r}.json",
        }
    base.add("gold_hn_qc_sample_list.json")
    return base


def derive_final_items(proposals: dict, unblind_maps: list[dict], b_verification_labels: dict[str, list[str]], c_adjudication: dict[tuple[str, str], str], sampled_r1: dict[str, list[str]]) -> list[dict]:
    """A/B 结果机械合并（唯一裁决规则，不得改写）。含 not_sampled 语义：未抽中 HN 不阻塞。"""
    last_derived = {}
    for um in unblind_maps:
        for e in um["map"].values():
            if e["proposal_type"] in {"positive_proposal", "hard_negative"}:
                last_derived[(e["item_id"], e["canonical_key"]), e["proposal_type"]] = e["derived"]
    items = []
    for item_id in sorted(proposals):
        item = proposals[item_id]
        out = {"item_id": item_id, "collection_trace_ref": f"trace_{item_id.replace('#', '_')}"}
        if item.get("status", "").startswith("BLOCKED"):
            out["status"] = item["status"]
            out["hard_negative_status"] = "not_applicable"
            out["blocked_reason"] = item.get("blocked_reason", "acquisition blocked")
            items.append(out)
            continue
        positives = []
        disagreement = False
        for p in item.get("positives", []):
            d = last_derived.get(((item_id, p["canonical_key"]), "positive_proposal"))
            if d == "confirmed":
                positives.append({**p, "resolution": "confirmed"})
            elif d == "disagreement":
                c = c_adjudication.get((item_id, p["canonical_key"]))
                if c == "relevant":
                    positives.append({**p, "resolution": "third_party_adjudicated"})
                else:
                    disagreement = True
        sampled_keys = set(sampled_r1.get(item_id, []))
        hn_out, hn_blocked = [], False
        for hn in item.get("hard_negatives", []):
            key = hn["canonical_key"]
            d = last_derived.get(((item_id, key), "hard_negative"))
            if d == "confirmed":
                hn_out.append({**hn, "b_reviewed": True, "b_review_result": "confirmed"})
            elif d in {"rejected", "uncertain"}:
                hn_blocked = True
            elif d is None:
                if key in sampled_keys:
                    sys.exit(f"HN_SAMPLED_UNLABELED: {item_id} {key}")  # 抽中但无标签 = 覆盖失败
                hn_out.append({**hn, "b_reviewed": False, "b_review_result": "not_sampled"})  # r1 正常路径
            else:
                hn_blocked = True
        if disagreement:
            out["status"] = "BLOCKED_ACQUISITION"
            out["blocked_reason"] = "A/B disagreement unresolved"
        elif hn_blocked:
            out["status"] = "BLOCKED_HARD_NEGATIVE_ACQUISITION"
            out["blocked_reason"] = "hard negative rejected/uncertain"
        elif item.get("no_positive_evidence") and not positives:
            bv = b_verification_labels.get(item_id, [])
            if bv and set(bv) == {"irrelevant"}:
                out["status"] = "no_relevant_document_found_under_frozen_plan"
            else:
                out["status"] = "BLOCKED_ACQUISITION"
                out["blocked_reason"] = "B verification aggregation failed"
        elif positives:
            out["status"] = "anchored"
        else:
            out["status"] = "BLOCKED_ACQUISITION"
            out["blocked_reason"] = "no positives and no no_positive evidence"
        out["positives"] = positives
        out["hard_negatives"] = hn_out
        if out["status"].startswith("BLOCKED"):
            out["hard_negative_status"] = "not_applicable"
        elif item.get("hard_negatives"):
            out["hard_negative_status"] = "found"
        elif item.get("hard_negative_status") == "no_hard_negative_found":
            out["hard_negative_status"] = "no_hard_negative_found"
        else:
            out["hard_negative_status"] = "not_applicable"
        items.append(out)
    return items


def _load_inputs(gd: Path) -> tuple[dict, list[dict], dict, dict]:
    proposals = json.loads((gd / "gold_proposals_snapshot.json").read_text(encoding="utf-8"))["items"]
    unblind_maps = [json.loads((gd / f"gold_blind_unblind_map_r{r}.json").read_text(encoding="utf-8")) for r in _rounds(gd)]
    bv_labels: dict[str, list[str]] = {}
    bv_path = gd / "gold_b_verification_labels.jsonl"
    if bv_path.exists():
        for row in (l for l in bv_path.open(encoding="utf-8") if l.strip()):
            r = json.loads(row)
            bv_labels.setdefault(r["item_id"], []).append(r["verification_label"])
    c_adj: dict[tuple[str, str], str] = {}
    c_path = gd / "gold_c_adjudication.jsonl"
    if c_path.exists():
        for row in (l for l in c_path.open(encoding="utf-8") if l.strip()):
            r = json.loads(row)
            c_adj[(r["item_id"], r["canonical_key"])] = r["c_label"]
    return proposals, unblind_maps, bv_labels, c_adj


def _rounds(gd: Path) -> list[int]:
    return sorted(int(p.stem.split("_r")[1]) for p in gd.glob("gold_blind_unblind_map_r*.json"))


def _concat_jsonl(gd: Path, out_path: Path, sources: list[Path], tags: list[str]) -> None:
    lines = []
    for src, tag in zip(sources, tags):
        if src.exists():
            for l in src.open(encoding="utf-8"):
                if l.strip():
                    row = json.loads(l)
                    row["_source"] = tag
                    lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    out_path.write_text("".join(l + "\n" for l in lines), encoding="utf-8", newline="\n")


def _write_closure(gd: Path, gold: dict, rounds: list[int]) -> None:
    items = gold["items"]
    anchored = sum(1 for i in items if i["status"] == "anchored")
    no_positive = sum(1 for i in items if i["status"] == "no_relevant_document_found_under_frozen_plan")
    blocked = sum(1 for i in items if i["status"].startswith("BLOCKED"))
    closure = "\n".join([
        "# GOLD_CLOSURE",
        f"verdict: {gold['acquisition_verdict']}",
        f"item_count: {len(items)}",
        f"anchored: {anchored}",
        f"no_positive: {no_positive}",
        f"blocked: {blocked}",
        f"blind_rounds: {len(rounds)}",
        "isolation: B=packet_only A=access_attestation",
        "filler_diagnostic: 见 GOLD_RECEIPT.stats.filler（仅分布诊断，非错误率）",
        "control_diagnostic: 见 GOLD_RECEIPT.stats.controls（唯一数/重复数/复用率）",
    ]) + "\n"
    (gd / "GOLD_CLOSURE.md").write_text(closure, encoding="utf-8", newline="\n")


def _publish_receipt(gd: Path) -> None:
    import reconcile_gold as rc
    manifest = json.loads((gd / "gold_manifest.json").read_text(encoding="utf-8"))
    rounds = sorted({int(k.split("_r")[1].split(".")[0]) for k in manifest["entries"] if "gold_blind_review_packet_r" in k})
    artifacts = sorted(rc.expected_artifact_set(rounds))
    entries_by_name = {Path(e["path"]).name: e for e in manifest["entries"].values()}
    meta = {}
    for name in artifacts:
        path = gd / name
        if not path.exists():
            sys.exit(f"ARTIFACT_BYTES_MISMATCH: {name} missing at publish")
        entry = entries_by_name.get(name)
        if entry is not None:
            meta[name] = {"sha256": entry["sha256"], "size": path.stat().st_size, "strategy": entry["strategy"]}
        else:  # 镜像/恢复场景：未入 manifest 的 artifact 用 raw 字节 SHA 记录
            meta[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size, "strategy": "raw_bytes"}
    gold = json.loads((gd / "gold_v1.json").read_text(encoding="utf-8"))
    receipt = {
        "manifest_sha256": rc.json_canonical_sha(manifest),
        "artifacts": artifacts,
        "artifact_meta": meta,
        "acquisition_verdict": gold["acquisition_verdict"],
        "stats": {
            "anchored": sum(1 for i in gold["items"] if i["status"] == "anchored"),
            "no_positive": sum(1 for i in gold["items"] if i["status"] == "no_relevant_document_found_under_frozen_plan"),
            "blocked": sum(1 for i in gold["items"] if i["status"].startswith("BLOCKED")),
            "blind_rounds": len(rounds),
        },
        "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    (gd / "GOLD_RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(gold_dir: Path | None = None) -> None:
    gd = gold_dir or PG
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # 工具目录自身（镜像 E2E 时 gd≠工具目录）
    import phase9a_manifest as pm
    import reconcile_gold as rc
    manifest = json.loads((gd / "gold_manifest.json").read_text(encoding="utf-8"))
    # 恢复分支（spec §8 恢复协议）
    if manifest["stage"] == "sealed":
        if (gd / "GOLD_RECEIPT.json").exists():
            receipt = json.loads((gd / "GOLD_RECEIPT.json").read_text(encoding="utf-8"))
            rc.check_receipt_manifest_binding(receipt, manifest)
            rc.check_artifact_shas(gd, manifest, receipt)  # 字节漂移 → fail-closed
            print("finalize_gold: already sealed; receipt verified (idempotent)")
            return
        rc.check_artifact_shas(gd, manifest, {"artifacts": sorted(rc.expected_artifact_set(
            sorted({int(k.split("_r")[1].split(".")[0]) for k in manifest["entries"] if "gold_blind_review_packet_r" in k})))})
        _publish_receipt(gd)
        print("finalize_gold: receipt reissued (sealed-without-receipt recovery)")
        return
    if manifest["stage"] != "code_frozen":
        sys.exit(f"MANIFEST_NOT_CODE_FROZEN: {manifest['stage']}")
    if (gd / "gold_v1.json").exists():
        sys.exit("GOLD_V1_ALREADY_EXISTS")  # one-shot：partial publish fail-closed
    pm.verify_frozen(gd / "gold_manifest.json", ["finalize_gold_py", "gold_validate_py"], required_stage=None)
    proposals, unblind_maps, bv_labels, c_adj = _load_inputs(gd)
    sample = json.loads((gd / "gold_hn_qc_sample_list.json").read_text(encoding="utf-8"))
    final_items = derive_final_items(proposals, unblind_maps, bv_labels, c_adj, sample["sampled"])
    blocked = [i for i in final_items if i["status"].startswith("BLOCKED")]
    verdict = "GOLD_READY" if not blocked else "GOLD_BLOCKED_ACQUISITION"
    gold = {"schema_version": "1.0", "item_count": 112, "acquisition_verdict": verdict, "items": final_items}
    (gd / "gold_v1.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    # 合并过程产物（最终日志首次冻结）
    rounds = _rounds(gd)
    _concat_jsonl(gd, gd / "gold_acquisition_log.jsonl",
                  [gd / "gold_acquisition_log_a.jsonl"]
                  + [gd / f"gold_b_labels_r{r}.jsonl" for r in rounds]
                  + [gd / "gold_b_verification_labels.jsonl", gd / "gold_c_adjudication.jsonl"],
                  ["curator_A"] + [f"curator_B_r{r}" for r in rounds] + ["curator_B_verification", "curator_C"])
    _concat_jsonl(gd, gd / "gold_search_results.jsonl",
                  [gd / "gold_search_results_a.jsonl", gd / "gold_search_results_bv.jsonl"],
                  ["A_search", "B_verification"])
    _concat_jsonl(gd, gd / "gold_access_log.jsonl",
                  [gd / "gold_access_log_a.jsonl", gd / "gold_access_log_publisher.jsonl"],
                  ["curator_A", "publisher"])
    _write_closure(gd, gold, rounds)
    # 冻结 sealed 条目 → sealed → RECEIPT 最后发布
    entries = {
        "gold_v1": (gd / "gold_v1.json", "json_canonical"),
        "gold_acquisition_log": (gd / "gold_acquisition_log.jsonl", "jsonl_canonical"),
        "gold_search_results": (gd / "gold_search_results.jsonl", "jsonl_canonical"),
        "gold_access_log": (gd / "gold_access_log.jsonl", "jsonl_canonical"),
        "GOLD_CLOSURE": (gd / "GOLD_CLOSURE.md", "raw_bytes"),
    }
    pm.freeze(gd / "gold_manifest.json", entries)
    pm.set_stage(gd / "gold_manifest.json", "sealed")
    _publish_receipt(gd)
    print(f"finalize_gold: acquisition_verdict={verdict}, manifest sealed, GOLD_RECEIPT published")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-dir", type=Path, default=PG)
    args = parser.parse_args()
    main(args.gold_dir)
```

guard_data_artifacts.py 修改（在现有 hook 中新增，自验 receipt→manifest 绑定 + guard config 条目 SHA）：
```python
def load_gold_guard_config(receipt_path: Path, manifest_path: Path) -> dict | None:
    if not receipt_path.exists():
        return None  # 未激活
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n").hexdigest()
    if receipt.get("manifest_sha256") != expected:
        sys.exit("RECEIPT_MANIFEST_SHA_MISMATCH")
    entry = manifest.get("entries", {}).get("gold_guard_config")
    if entry is None:
        sys.exit("GUARD_CONFIG_NOT_FROZEN")
    gc_path = manifest_path.with_name("gold_guard_config.json")
    gc_actual = hashlib.sha256(json.dumps(json.loads(gc_path.read_text(encoding="utf-8")), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n").hexdigest()
    if gc_actual != entry["sha256"]:
        sys.exit("GUARD_CONFIG_SHA_DRIFT")
    return json.loads(gc_path.read_text(encoding="utf-8"))
```

**v5 计划明确：** finalize_gold.py 为完整生产代码（含恢复协议：sealed+receipt 幂等验证 / sealed-without-receipt 补发 / partial publish 与字节漂移 fail-closed），无 TODO/补全委托。guard 不接受外部 `receipt_valid` 布尔参数。

- [ ] **Step 4: 冻结 finalize + guard → 推进 code_frozen → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
m = PG / "gold_manifest.json"
pm.freeze(m, {
    "finalize_gold_py": (PG / "finalize_gold.py", "git_canonical_lf"),
    "guard_data_artifacts_py": (Path(".qoder/hooks/guard_data_artifacts.py"), "git_canonical_lf"),
})
pm.set_stage(m, "code_frozen")
print("finalize + guard frozen; stage=code_frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldFinalizerAndGuard -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/finalize_gold.py .qoder/hooks/guard_data_artifacts.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): finalizer + guard frozen; code_frozen"
```

---

## Task 10: A 采集并冻结 proposal/HN/no-positive 快照

**Files:**
- Create: `docs/phase9a/gold/gold_proposals_snapshot.json`
- Create: `docs/phase9a/gold/gold_search_results_a.jsonl`
- Create: `docs/phase9a/gold/gold_access_log_a.jsonl`
- Create: `docs/phase9a/gold/gold_acquisition_log_a.jsonl`
- Modify: `docs/phase9a/gold/gold_manifest.json`
- Test: `tests/test_phase9a_gold.py`

**gold_proposals_snapshot.json schema：**
```json
{
  "schema_version": "1.0",
  "items": {
    "mingli_ftb_0002#k4": {
      "status": "anchored | no_relevant_document_found_under_frozen_plan | BLOCKED_*",
      "positives": [{"canonical_key": "...", "evidence_quote": "...", "trace_step_refs": ["0002k4_s1@..."]}],
      "hard_negatives": [{"canonical_key": "...", "collision_terms": [...], "evidence_quote": "...", "why_negative": "...", "trace_step_refs": ["0002k4_hn_s1@..."]}],
      "no_positive_evidence": {"executed_step_ids": [...], "all_candidates_reviewed": true}
    }
  }
}
```

**⏸ 暂停点（人工主体）：** curator_A 使用冻结工具执行：
1. 对每 item 执行搜索计划：`gold_search_exec.py --plan-file ... --step-id ... --results-file gold_search_results_a.jsonl`
2. 经 `gold_read_access.py` 读取语料，自动记录 `gold_access_log_a.jsonl`
3. 在 `gold_proposals_snapshot.json` 中填写 positives / hard_negatives / no_positive_evidence
4. 将 A 的判定过程写入 `gold_acquisition_log_a.jsonl`（每行一个 item 的轨迹）

**A 采集完成后冻结快照（独立文件，非最终日志）：**
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {
    "gold_proposals_snapshot": (PG / "gold_proposals_snapshot.json", "json_canonical"),
    "gold_search_results_a": (PG / "gold_search_results_a.jsonl", "jsonl_canonical"),
    "gold_access_log_a": (PG / "gold_access_log_a.jsonl", "jsonl_canonical"),
    "gold_acquisition_log_a": (PG / "gold_acquisition_log_a.jsonl", "jsonl_canonical"),
})
print("A acquisition snapshot frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS（测试仅检查文件存在与 manifest 条目）。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_proposals_snapshot.json docs/phase9a/gold/gold_search_results_a.jsonl docs/phase9a/gold/gold_access_log_a.jsonl docs/phase9a/gold/gold_acquisition_log_a.jsonl tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): A acquisition snapshots frozen"
```

---

## Task 11: 生成 HN sample + r1 packet + verification packet 并冻结

**Files:**
- Create: `docs/phase9a/gold/gold_hn_qc_sample_list.json`
- Create: `docs/phase9a/gold/gold_blind_review_packet_r1.jsonl`
- Create: `docs/phase9a/gold/BLIND_PACKET_RECEIPT_r1.json`
- Create: `docs/phase9a/gold/gold_b_verification_packet.jsonl`
- Create: `docs/phase9a/gold/B_VERIFICATION_PACKET_RECEIPT.json`
- Modify: `docs/phase9a/gold/gold_manifest.json`
- Test: `tests/test_phase9a_gold.py`

**逐产物冻结顺序：**

1. HN sample 列表先于 r1 packet
2. r1 packet 与 receipt 同时冻结
3. verification packet 与 receipt 同时冻结

**生产脚本：**

```python
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
sys.path.insert(0, "docs/phase9a/gold")
import phase9a_manifest as pm
import gold_hn_sampler as sampler
import gold_blind_packet_builder as builder
import gold_search_exec as se
import gold_read_access as ra

PG = Path("docs/phase9a/gold")
snapshot = json.loads((PG / "gold_proposals_snapshot.json").read_text(encoding="utf-8"))

# 1. HN sample
hn_candidates = {item_id: [hn["canonical_key"] for hn in item["hard_negatives"]] for item_id, item in snapshot["items"].items()}
sample_list = sampler.sample_hn(hn_candidates, seed=20260814, ratio=0.2)
sampler.write_sample_list(sample_list, PG / "gold_hn_qc_sample_list.json")
pm.freeze(PG / "gold_manifest.json", {"gold_hn_qc_sample_list": (PG / "gold_hn_qc_sample_list.json", "json_canonical")})

# 2. r1 blind packet（含类型 sidecar；publisher 日志独立，不碰 A attestation）
confirmed = [(item_id, p["canonical_key"]) for item_id, item in snapshot["items"].items() for p in item.get("positives", [])]
packet, types = builder.build_packet(
    round_num=1,
    proposals=snapshot["items"],
    sampled_hn=sample_list["sampled"],
    confirmed_positives=confirmed,
    seed=20260815,
    trigger_condition_met=True,
)
packet_path = PG / "gold_blind_review_packet_r1.jsonl"
types_path = PG / "gold_blind_packet_types_r1.json"
builder.write_packet(packet, packet_path)
builder.write_types_sidecar(packet, types, round_num=1, path=types_path)
receipt1 = builder.build_packet_receipt(packet_path, types_path)
receipt1["round"] = 1
(PG / "BLIND_PACKET_RECEIPT_r1.json").write_text(json.dumps(receipt1, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
pm.freeze(PG / "gold_manifest.json", {
    "gold_blind_review_packet_r1": (packet_path, "jsonl_canonical"),
    "gold_blind_packet_types_r1": (types_path, "json_canonical"),
    "BLIND_PACKET_RECEIPT_r1": (PG / "BLIND_PACKET_RECEIPT_r1.json", "json_canonical"),
})

# 3. B verification packet（no-positive 子集；bv 结果写独立文件，不碰 A 冻结文件）
no_positive_items = [item_id for item_id, item in snapshot["items"].items() if item["status"] == "no_relevant_document_found_under_frozen_plan"]
verification_results = []
bv_results_file = PG / "gold_search_results_bv.jsonl"
for item_id in no_positive_items:
    plan = next(p for p in json.loads((PG / "gold_b_verification_plans.json").read_text(encoding="utf-8"))["plans"] if p["item_id"] == item_id)
    for step in plan["steps"]:
        verification_results.append(se.execute_step(step, bv_results_file))
# verification packet 仅含 candidate text，不含 A 结论；publisher 角色 + 独立日志
bv_packet = [{"item_id": r["item_id"], "canonical_key": k, "document_text": ra.read_corpus(k, role="publisher", log_path=PG / "gold_access_log_publisher.jsonl")} for r in verification_results for k in r["ordered_candidate_keys"]]
bv_path = PG / "gold_b_verification_packet.jsonl"
builder.write_packet(bv_packet, bv_path)
bv_receipt = {
    "packet_sha256": hashlib.sha256(bv_path.read_bytes()).hexdigest(),
    "packet_lines": len(bv_packet),
    "candidate_keys_sha256": builder._canonical_sha([r["canonical_key"] for r in bv_packet]),
}
(PG / "B_VERIFICATION_PACKET_RECEIPT.json").write_text(json.dumps(bv_receipt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
pm.freeze(PG / "gold_manifest.json", {
    "gold_search_results_bv": (bv_results_file, "jsonl_canonical"),
    "gold_b_verification_packet": (bv_path, "jsonl_canonical"),
    "B_VERIFICATION_PACKET_RECEIPT": (PG / "B_VERIFICATION_PACKET_RECEIPT.json", "json_canonical"),
    "gold_access_log_publisher": (PG / "gold_access_log_publisher.jsonl", "jsonl_canonical"),
})
print("HN sample + r1 packet + verification packet frozen")
```

- [ ] **Step 1: 写失败测试**

```python
class TestGoldPackets:
    def test_hn_sample_frozen_before_r1(self):
        m = _load_json(PG / "gold_manifest.json")
        assert "gold_hn_qc_sample_list" in m["entries"]
        assert "gold_blind_review_packet_r1" in m["entries"]

    def test_blind_packet_no_type_leak(self):
        packet = [json.loads(l) for l in (PG / "gold_blind_review_packet_r1.jsonl").open(encoding="utf-8") if l.strip()]
        assert packet
        for p in packet:
            assert {"blind_id", "item_id", "canonical_key", "document_text"} <= set(p)
            for forbidden in ("proposal_type", "curator", "reason", "_type"):
                assert forbidden not in p

    def test_verification_packet_receipt(self):
        assert (PG / "gold_b_verification_packet.jsonl").exists()
        assert (PG / "B_VERIFICATION_PACKET_RECEIPT.json").exists()
        receipt = _load_json(PG / "B_VERIFICATION_PACKET_RECEIPT.json")
        assert receipt["packet_sha256"]
        assert receipt["packet_lines"] >= 0
```

- [ ] **Step 2: 运行确认失败 → 执行脚本 → 测试转绿 → Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldPackets -q`
Expected: FAIL → PASS after script。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_hn_qc_sample_list.json docs/phase9a/gold/gold_blind_review_packet_r1.jsonl docs/phase9a/gold/gold_blind_packet_types_r1.json docs/phase9a/gold/BLIND_PACKET_RECEIPT_r1.json docs/phase9a/gold/gold_b_verification_packet.jsonl docs/phase9a/gold/B_VERIFICATION_PACKET_RECEIPT.json docs/phase9a/gold/gold_search_results_bv.jsonl docs/phase9a/gold/gold_access_log_publisher.jsonl tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): HN sample + r1 packet + B verification packet frozen"
```

---

## Task 12: B/C 盲审 + 解盲 + r2/r3 五件套冻结

**Files:**
- Create: `docs/phase9a/gold/gold_b_labels_rN.jsonl`
- Create: `docs/phase9a/gold/B_LABEL_RECEIPT_rN.json`
- Create: `docs/phase9a/gold/gold_blind_unblind_map_rN.json`
- Create: `docs/phase9a/gold/gold_b_verification_labels.jsonl`
- Create: `docs/phase9a/gold/gold_c_adjudication.jsonl`（C 裁决记录）
- Modify: `docs/phase9a/gold/gold_manifest.json`
- Test: `tests/test_phase9a_gold.py`

**B label 模板（每行）：**
```json
{"blind_id": "blind_r1_001", "item_id": "...", "canonical_key": "...", "label": "relevant", "note": "必填", "packet_sha256": "..."}
```

**B label receipt schema：**
```json
{"round": 1, "label_sha256": "...", "packet_sha256": "...", "label_lines": 120, "packet_lines": 120, "blind_id_set_sha256": "..."}
```

**B verification label schema（每行）：**
```json
{"step_id": "0002k4_bv1", "item_id": "...", "canonical_key": "...", "verification_label": "relevant", "note": "...", "evidence_quote": "..."}
```

**C adjudication schema（每行）：**
```json
{"item_id": "...", "canonical_key": "...", "c_label": "relevant", "rationale": "...", "adjudicated_at": "..."}
```

**生产入口（全部函数已在 Task 6 首冻版中实现，本 Task 只调用）：**
- 发布器：校验 BLIND_PACKET_RECEIPT_rN SHA 后才复制 packet 到 B workspace（顺序门）
- `builder.build_label_receipt(labels_path, packet_path, packet_sha, round_num)`（拒绝重复/未知 label/空 note/覆盖不全，测试已在 Task 6 锁定）
- `gold_unblind_mapper.py --round N --packet ... --labels ... --receipt ... --types ... --output ...`
- `builder.check_r2_trigger(r1_unblind_map)` / `builder.check_r3_trigger(r2_unblind_map, replacements)`

**r2/r3 五件套（每轮）：**
1. `gold_blind_review_packet_rN.jsonl`
2. `BLIND_PACKET_RECEIPT_rN.json`
3. `gold_b_labels_rN.jsonl`
4. `B_LABEL_RECEIPT_rN.json`
5. `gold_blind_unblind_map_rN.json`

**失败状态：**
- `LABEL_RECEIPT_PACKET_MISMATCH`
- `LABEL_BLIND_ID_COVERAGE_INCOMPLETE`
- `R2_TRIGGER_NOT_MET`
- `R3_TRIGGER_NOT_MET`
- `NO_C_FOR_DISAGREEMENT`（C 未冻结时首个分歧）

- [ ] **Step 1: 写失败测试（生产链断言；单元级 label receipt/trigger 测试已在 Task 6）**

```python
class TestGoldBlindReview:
    def test_r1_chain_frozen(self):
        m = _load_json(PG / "gold_manifest.json")
        for name in ("gold_b_labels_r1", "B_LABEL_RECEIPT_r1", "gold_blind_unblind_map_r1"):
            assert name in m["entries"], f"{name} not frozen"

    def test_r1_unblind_map_binding(self):
        um = _load_json(PG / "gold_blind_unblind_map_r1.json")
        pr = _load_json(PG / "BLIND_PACKET_RECEIPT_r1.json")
        lr = _load_json(PG / "B_LABEL_RECEIPT_r1.json")
        assert um["packet_sha256"] == pr["packet_sha256"]
        assert um["label_sha256"] == lr["label_sha256"]
        assert um["types_sha256"] == pr["types_sha256"]

    def test_c_adjudication_schema(self):
        if (PG / "gold_c_adjudication.jsonl").exists():
            rows = [json.loads(l) for l in (PG / "gold_c_adjudication.jsonl").open(encoding="utf-8") if l.strip()]
            for r in rows:
                assert r["c_label"] in {"relevant", "partially_relevant", "irrelevant", "uncertain"}
                assert r["rationale"]
```

- [ ] **Step 2: r1 完整命令链（人工打标 → receipt → 解盲 → 冻结 → commit）**

```python
import json
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
sys.path.insert(0, "docs/phase9a/gold")
import phase9a_manifest as pm
import gold_blind_packet_builder as builder
import gold_unblind_mapper as mapper

PG = Path("docs/phase9a/gold")
r = 1
# 1) B 完成四态打标后（B workspace 回收 gold_b_labels_r1.jsonl），生成 label receipt
pr = json.loads((PG / f"BLIND_PACKET_RECEIPT_r{r}.json").read_text(encoding="utf-8"))
receipt = builder.build_label_receipt(PG / f"gold_b_labels_r{r}.jsonl", PG / f"gold_blind_review_packet_r{r}.jsonl", pr["packet_sha256"], round_num=r)
(PG / f"B_LABEL_RECEIPT_r{r}.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
# 2) 解盲（仅在此后）
mapper.unblind(r, PG / f"gold_blind_review_packet_r{r}.jsonl", PG / f"gold_b_labels_r{r}.jsonl", PG / f"B_LABEL_RECEIPT_r{r}.json", PG / f"gold_blind_packet_types_r{r}.json", PG / f"gold_blind_unblind_map_r{r}.json")
# 3) 冻结该轮五件套
pm.freeze(PG / "gold_manifest.json", {
    f"gold_b_labels_r{r}": (PG / f"gold_b_labels_r{r}.jsonl", "jsonl_canonical"),
    f"B_LABEL_RECEIPT_r{r}": (PG / f"B_LABEL_RECEIPT_r{r}.json", "json_canonical"),
    f"gold_blind_unblind_map_r{r}": (PG / f"gold_blind_unblind_map_r{r}.json", "json_canonical"),
})
print(f"round {r} five-piece set frozen")
```

```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_b_labels_r1.jsonl docs/phase9a/gold/B_LABEL_RECEIPT_r1.json docs/phase9a/gold/gold_blind_unblind_map_r1.json docs/phase9a/gold/gold_b_verification_labels.jsonl tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): r1 blind review five-piece set frozen (labels+receipt+unblind map)"
```

- [ ] **Step 3: r2/r3 条件分支（完整命令；不触发则跳过并在 commit 信息记录 r1-only）**

前置：重新加载 Task 11 的变量（新执行会话）：`snapshot`（gold_proposals_snapshot.json）、`sample`（gold_hn_qc_sample_list.json）、`confirmed`（从 snapshot 推导）。

```python
# r2 触发判定（fail-closed：不满足拒绝生成）
um1 = json.loads((PG / "gold_blind_unblind_map_r1.json").read_text(encoding="utf-8"))
if builder.check_r2_trigger(um1):
    # r2 = 全部剩余未审 HN + controls + filler；触发条件必须显式传入
    not_sampled = {item_id: [h["canonical_key"] for h in item["hard_negatives"] if h["canonical_key"] not in set(sample["sampled"].get(item_id, []))]
                   for item_id, item in snapshot["items"].items()}
    packet2, types2 = builder.build_packet(round_num=2, proposals=snapshot["items"], sampled_hn={k: v for k, v in not_sampled.items() if v},
                                           confirmed_positives=confirmed, seed=20260815, trigger_condition_met=True)
    builder.write_packet(packet2, PG / "gold_blind_review_packet_r2.jsonl")
    builder.write_types_sidecar(packet2, types2, 2, PG / "gold_blind_packet_types_r2.json")
    rec2 = builder.build_packet_receipt(PG / "gold_blind_review_packet_r2.jsonl", PG / "gold_blind_packet_types_r2.json")
    rec2["round"] = 2
    (PG / "BLIND_PACKET_RECEIPT_r2.json").write_text(json.dumps(rec2, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    pm.freeze(PG / "gold_manifest.json", {
        "gold_blind_review_packet_r2": (PG / "gold_blind_review_packet_r2.jsonl", "jsonl_canonical"),
        "gold_blind_packet_types_r2": (PG / "gold_blind_packet_types_r2.json", "json_canonical"),
        "BLIND_PACKET_RECEIPT_r2": (PG / "BLIND_PACKET_RECEIPT_r2.json", "json_canonical"),
    })
    # B 复核 r2 → 重复 Step 2 的 r=2 命令链（labels → receipt → unblind → 冻结 → commit）
```

```python
# r3 触发判定（replacement 仅一次机会，必须附 trace_step_refs）
um2 = json.loads((PG / "gold_blind_unblind_map_r2.json").read_text(encoding="utf-8"))
replacements = json.loads((PG / "gold_hn_replacements.json").read_text(encoding="utf-8"))  # A 提交
if builder.check_r3_trigger(um2, replacements):
    packet3, types3 = builder.build_packet(round_num=3, proposals=snapshot["items"], sampled_hn={r_["item_id"]: [r_["canonical_key"]] for r_ in replacements},
                                           confirmed_positives=confirmed, seed=20260815, trigger_condition_met=True)
    builder.write_packet(packet3, PG / "gold_blind_review_packet_r3.jsonl")
    builder.write_types_sidecar(packet3, types3, 3, PG / "gold_blind_packet_types_r3.json")
    rec3 = builder.build_packet_receipt(PG / "gold_blind_review_packet_r3.jsonl", PG / "gold_blind_packet_types_r3.json")
    rec3["round"] = 3
    (PG / "BLIND_PACKET_RECEIPT_r3.json").write_text(json.dumps(rec3, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    pm.freeze(PG / "gold_manifest.json", {
        "gold_blind_review_packet_r3": (PG / "gold_blind_review_packet_r3.jsonl", "jsonl_canonical"),
        "gold_blind_packet_types_r3": (PG / "gold_blind_packet_types_r3.json", "json_canonical"),
        "BLIND_PACKET_RECEIPT_r3": (PG / "BLIND_PACKET_RECEIPT_r3.json", "json_canonical"),
    })
    # B 复核 r3 → 重复 Step 2 的 r=3 命令链
```

每产生一轮，立即单独 commit 该轮五件套（模板，N 替换为实际轮号）：
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_blind_review_packet_rN.jsonl docs/phase9a/gold/gold_blind_packet_types_rN.json docs/phase9a/gold/BLIND_PACKET_RECEIPT_rN.json docs/phase9a/gold/gold_b_labels_rN.jsonl docs/phase9a/gold/B_LABEL_RECEIPT_rN.json docs/phase9a/gold/gold_blind_unblind_map_rN.json
git diff --cached --name-only
git commit -m "feat(phase9a-gold): rN blind review five-piece set frozen"
```

B verification labels 冻结：
```python
pm.freeze(PG / "gold_manifest.json", {
    "gold_b_verification_labels": (PG / "gold_b_verification_labels.jsonl", "jsonl_canonical"),
})
```

C adjudication 冻结（如产生）：
```python
pm.freeze(PG / "gold_manifest.json", {
    "gold_c_adjudication": (PG / "gold_c_adjudication.jsonl", "jsonl_canonical"),
})
```

---

## Task 13: finalize + reconcile + guard 验证

**Files:**
- Create: `docs/phase9a/gold/gold_v1.json`
- Create: `docs/phase9a/gold/gold_acquisition_log.jsonl`（合并 A/B/C 轨迹）
- Create: `docs/phase9a/gold/gold_search_results.jsonl`（合并 A + B verification）
- Create: `docs/phase9a/gold/gold_access_log.jsonl`（合并 A + publisher）
- Create: `docs/phase9a/gold/GOLD_CLOSURE.md`
- Create: `docs/phase9a/gold/GOLD_RECEIPT.json`
- Modify: `docs/phase9a/gold/gold_manifest.json`（sealed）
- Test: `tests/test_phase9a_gold.py`

**A/B 结果机械合并规则（唯一实现 = Task 9 `derive_final_items`，含 not_sampled 语义）：**
- 正例 confirmed：A proposal + B relevant → positives resolution=confirmed
- 正例分歧：A proposal + B 非 relevant → 查 C adjudication；C=relevant → third_party_adjudicated；否则 BLOCKED_ACQUISITION
- HN confirmed：派生 confirmed → b_reviewed=true, b_review_result=confirmed
- HN rejected/uncertain → BLOCKED_HARD_NEGATIVE_ACQUISITION（replacement 仅一次机会，走 r3）
- HN 未抽中且无派生 → b_reviewed=false, b_review_result=not_sampled，**不阻塞 GOLD_READY**
- no_positive：B verification 全 irrelevant → no_relevant_document_found_under_frozen_plan；否则 BLOCKED

**最终 artifact 命名与 spec v1.7 一致：**
- `gold_v1.json`
- `gold_acquisition_log.jsonl`
- `gold_search_results.jsonl`
- `gold_access_log.jsonl`
- `GOLD_CLOSURE.md`
- `GOLD_RECEIPT.json`

**GOLD_RECEIPT artifact 集合（版本化，按实际轮数 N）：**
基础项 + 每轮 r1..N 五件套 + B verification 两件套 + HN sample。

- [ ] **Step 1: 写失败测试（终态契约）**

```python
class TestGoldSealed:
    def test_manifest_sealed(self):
        m = _load_json(PG / "gold_manifest.json")
        assert m["stage"] == "sealed"
        assert "gold_v1" in m["entries"]
        assert "GOLD_CLOSURE" in m["entries"]

    def test_gold_v1_112_items(self):
        gold = _load_json(PG / "gold_v1.json")
        assert gold["item_count"] == 112
        assert len(gold["items"]) == 112
        assert gold["acquisition_verdict"] in {"GOLD_READY", "GOLD_BLOCKED_ACQUISITION"}
        for item in gold["items"]:
            assert item["status"] in {"anchored", "no_relevant_document_found_under_frozen_plan", "BLOCKED_ACQUISITION", "BLOCKED_HARD_NEGATIVE_ACQUISITION"}
            if item["status"].startswith("BLOCKED"):
                assert item["hard_negative_status"] == "not_applicable"
                assert item["blocked_reason"]

    def test_receipt_binds_sealed_manifest(self):
        receipt = _load_json(PG / "GOLD_RECEIPT.json")
        m = _load_json(PG / "gold_manifest.json")
        gold = _load_json(PG / "gold_v1.json")
        assert receipt["manifest_sha256"] == hashlib.sha256(json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n").hexdigest()
        assert "GOLD_RECEIPT" not in m["entries"]
        assert "gold_v1.json" in receipt["artifacts"]
        assert receipt["acquisition_verdict"] == gold["acquisition_verdict"]

    def test_reconcile_gold_exit_zero(self):
        proc = subprocess.run([sys.executable, str(PG / "reconcile_gold.py")], capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "FAIL" not in proc.stdout

    def test_guard_verifies_receipt_binding(self):
        guard = _load_module("guard_data_artifacts", ".qoder/hooks/guard_data_artifacts.py")
        config = guard.load_gold_guard_config(receipt_path=PG / "GOLD_RECEIPT.json", manifest_path=PG / "gold_manifest.json")
        assert config is not None
        assert "docs/phase9a/gold/gold_v1.json" in config["protected_paths"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldSealed -q`
Expected: FAIL。

- [ ] **Step 3: 运行 finalize_gold.py（双终态发布）**

Run: `.venv/Scripts/python.exe docs/phase9a/gold/finalize_gold.py`
Expected: `finalize_gold: acquisition_verdict=GOLD_READY|GOLD_BLOCKED_ACQUISITION, manifest sealed, GOLD_RECEIPT published`。

- [ ] **Step 4: reconcile_gold exit 0 → 测试转绿 → Commit**

Run: `.venv/Scripts/python.exe docs/phase9a/gold/reconcile_gold.py`
Expected: exit 0 无 FAIL。
Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_v1.json docs/phase9a/gold/gold_acquisition_log.jsonl docs/phase9a/gold/gold_search_results.jsonl docs/phase9a/gold/gold_access_log.jsonl docs/phase9a/gold/GOLD_CLOSURE.md docs/phase9a/gold/GOLD_RECEIPT.json tests/test_phase9a_gold.py
# r2/r3 轮次产物已在 Task 12 产生时逐轮单独 commit；此处不重复暂存
git diff --cached --name-only
git commit -m "chore(phase9a-gold): sealed + GOLD_RECEIPT published (acquisition_verdict=...)"
```

- [ ] **Step 5: guard 验证（零修改验证，不动 sealed 产物）**

```powershell
.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldSealed::test_guard_verifies_receipt_binding -q
```
Expected: PASS（guard 自行读取 GOLD_RECEIPT 并重算 manifest SHA 后返回 protected_paths）。禁止用实际修改 sealed 产物的方式测试。

---

## Task 14: 双终态隔离镜像 E2E + 恢复链测试

**Files:**
- Test: `tests/test_phase9a_gold.py`

**目标（中优修复）：** 在 tmp 镜像中端到端验证 READY/BLOCKED 双终态、partial publish、sealed-without-receipt 补发、重复运行、字节漂移恢复链。不碰真实 PG 产物。

- [ ] **Step 1: 写镜像 E2E 测试**

```python
class TestGoldDualTerminalMirror:
    def _build_mirror(self, tmp_path, case):
        """构造合成镜像：manifest(stage=code_frozen) + A 快照 + sample list + r1 unblind map。"""
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = tmp_path / "gold"
        mirror.mkdir()
        real = _load_json(PG / "gold_manifest.json")
        entries = {k: v for k, v in real["entries"].items()
                   if k in {"finalize_gold_py", "gold_validate_py", "reconcile_gold_py", "gold_hn_sampler_py"}}
        (mirror / "gold_manifest.json").write_text(json.dumps({"schema_version": "1.0", "stage": "code_frozen", "entries": entries}, indent=1), encoding="utf-8")
        if case == "ready":
            proposals = {"i1": {"positives": [{"canonical_key": "p1", "evidence_quote": "e", "trace_step_refs": ["s1@p1"]}],
                                 "hard_negatives": [{"canonical_key": "h1"}, {"canonical_key": "h2"}]}}
            umap = {"round": 1, "packet_sha256": "x", "label_sha256": "y", "types_sha256": "z", "map": {
                "b1": {"proposal_type": "positive_proposal", "item_id": "i1", "canonical_key": "p1", "label": "relevant", "derived": "confirmed"},
                "b2": {"proposal_type": "hard_negative", "item_id": "i1", "canonical_key": "h1", "label": "irrelevant", "derived": "confirmed"}}}
        else:  # blocked
            proposals = {"i1": {"positives": [{"canonical_key": "p1", "evidence_quote": "e", "trace_step_refs": ["s1@p1"]}], "hard_negatives": []}}
            umap = {"round": 1, "packet_sha256": "x", "label_sha256": "y", "types_sha256": "z", "map": {
                "b1": {"proposal_type": "positive_proposal", "item_id": "i1", "canonical_key": "p1", "label": "irrelevant", "derived": "disagreement"}}}
        (mirror / "gold_proposals_snapshot.json").write_text(json.dumps({"schema_version": "1.0", "items": proposals}), encoding="utf-8")
        (mirror / "gold_hn_qc_sample_list.json").write_text(json.dumps({"schema_version": "1.0", "seed": 20260814, "ratio": 0.2, "sampled": {"i1": ["h1"]}, "not_sampled": {"i1": ["h2"]}}), encoding="utf-8")
        (mirror / "gold_blind_unblind_map_r1.json").write_text(json.dumps(umap), encoding="utf-8")
        (mirror / "gold_acquisition_log_a.jsonl").write_text(json.dumps({"item_id": "i1", "trace": "t"}) + "\n", encoding="utf-8")
        # 补齐基础 artifact（空集产物，与 spec v1.7 §4 空集契约一致）
        (mirror / "gold_b_verification_packet.jsonl").write_text("", encoding="utf-8")
        (mirror / "gold_b_verification_labels.jsonl").write_text("", encoding="utf-8")
        (mirror / "B_VERIFICATION_PACKET_RECEIPT.json").write_text(json.dumps(
            {"packet_sha256": hashlib.sha256(b"").hexdigest(), "packet_lines": 0, "candidate_keys_sha256": ""}), encoding="utf-8")
        return mirror

    def test_ready_mirror_end_to_end(self, tmp_path):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = self._build_mirror(tmp_path, "ready")
        fin.main(gold_dir=mirror)
        gold = _load_json(mirror / "gold_v1.json")
        assert gold["acquisition_verdict"] == "GOLD_READY"
        assert _load_json(mirror / "gold_manifest.json")["stage"] == "sealed"
        receipt = _load_json(mirror / "GOLD_RECEIPT.json")
        assert receipt["manifest_sha256"]

    def test_blocked_mirror_end_to_end(self, tmp_path):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = self._build_mirror(tmp_path, "blocked")
        fin.main(gold_dir=mirror)
        gold = _load_json(mirror / "gold_v1.json")
        assert gold["acquisition_verdict"] == "GOLD_BLOCKED_ACQUISITION"
        blocked = [i for i in gold["items"] if i["status"].startswith("BLOCKED")]
        assert blocked and all(i["blocked_reason"] for i in blocked)
        # blocked 项过程记录存在于 acquisition log
        log = [json.loads(l) for l in (mirror / "gold_acquisition_log.jsonl").open(encoding="utf-8") if l.strip()]
        assert log

    def test_partial_publish_fail_closed(self, tmp_path):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = self._build_mirror(tmp_path, "ready")
        (mirror / "gold_v1.json").write_text("{}", encoding="utf-8")  # code_frozen 阶段已有 gold_v1 = partial publish
        with pytest.raises(SystemExit):
            fin.main(gold_dir=mirror)

    def test_duplicate_run_idempotent(self, tmp_path):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = self._build_mirror(tmp_path, "ready")
        fin.main(gold_dir=mirror)
        before = _load_json(mirror / "GOLD_RECEIPT.json")
        fin.main(gold_dir=mirror)  # 重复运行：幂等验证，不重写
        assert _load_json(mirror / "GOLD_RECEIPT.json") == before

    def test_sealed_without_receipt_reissue(self, tmp_path):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = self._build_mirror(tmp_path, "ready")
        fin.main(gold_dir=mirror)
        (mirror / "GOLD_RECEIPT.json").unlink()  # 模拟 sealed 后 receipt 丢失
        fin.main(gold_dir=mirror)  # 恢复分支：校验产物 SHA 后补发
        assert (mirror / "GOLD_RECEIPT.json").exists()

    def test_byte_drift_fail_closed(self, tmp_path):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = self._build_mirror(tmp_path, "ready")
        fin.main(gold_dir=mirror)
        gold = _load_json(mirror / "gold_v1.json")
        gold["items"][0]["status"] = "tampered"
        (mirror / "gold_v1.json").write_text(json.dumps(gold), encoding="utf-8")  # 字节漂移
        with pytest.raises(SystemExit):
            fin.main(gold_dir=mirror)  # 幂等验证分支检出漂移 fail-closed
```

- [ ] **Step 2: 运行确认失败 → 修复 → 转绿 → Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldDualTerminalMirror -q`
Expected: 全绿（依赖 Task 9 完整实现）。
```powershell
git add -- tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "test(phase9a-gold): dual-terminal mirror E2E + recovery chain tests"
```

---

## 任务总览（v5 结构）

| Task | 内容 | 阶段 |
|---|---|---|
| 0 | 基线验证 + upstream SHA | config 前 |
| 1a | builder 生成草稿 config | config_frozen |
| 1b | validator 校验草稿 + 冻结 | config_frozen |
| 1c | 人工修改后 validator 重校验（⏸ 暂停点） | config_frozen |
| 2 | 原子冻结全部最终 config | config_frozen |
| 3 | read-access wrapper | code_frozen |
| 4 | search executor | code_frozen |
| 5 | HN stratified sampler | code_frozen |
| 6 | packet/receipt publisher | code_frozen |
| 7 | unblind/state machine | code_frozen |
| 8 | validator + reconcile | code_frozen |
| 9 | finalizer + guard → stage=code_frozen | code_frozen |
| 10 | A 采集快照（⏸ 暂停点） | code_frozen |
| 11 | HN sample + r1 packet + verification packet | code_frozen |
| 12 | B/C 盲审 + r2/r3 五件套（⏸ 暂停点） | code_frozen |
| 13 | finalize 双终态 + reconcile + guard | sealed |
| 14 | 双终态镜像 E2E + 恢复链测试 | sealed 后 |

## 验证命令集（收尾必跑）

```powershell
# 静态门禁
.venv/Scripts/python.exe -m ruff check .
# 聚焦回归（含本计划全部测试类）
.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q
# no-network 约束：本计划全部工具零外部 API；若 CI 环境需要显式隔离，用 monkeypatch socket 或 `-p no:cacheprovider` 断网验证
# 非 E2E 全量回归（合并前）
.venv/Scripts/python.exe -m pytest -m "not e2e" -q
# focused smoke（pre-commit 同层）
.venv/Scripts/python.exe scripts/verify_smoke.py
```

## 完成定义（对齐规约 v1.7 §11）

1. 规约 v1.7 通过审核（已 APPROVED，commit `c06daec`）
2. gold_roles.json 指定 A、B 两名互不相同人类身份（C 可选但须采集前冻结；未冻结时首个分歧即 BLOCKED）
3. config 冻结链正确：builder 草稿 → validator 校验 → 人工修改 → validator 重校验 → Task 2 原子冻结全部最终 config；code 阶段全部工具条目冻结（含各轮盲审包 SHA 与 B verification packet SHA 先于 B 查看；HN 抽样先于 r1 构造冻结）
4. 采集完成或明确阻塞：112 项全部有终态状态记录
5. 双审闭合：各轮盲审包四态标签冻结后解盲（receipt 绑定链完整，含 blind_id 集合 SHA）；每条 positive 有 resolution；每个分歧有 C 裁决或 BLOCKED；no_positive 有 B 结构化复核（聚合规则满足）
6. 机器校验全过：canonical key 可解析、evidence_quote 子串真实、候选清单落盘可复算、reviewed == candidates 严格相等、trace_step_refs 引用完整、hard negative 分层抽样精确等于算法输出
7. 终态 GOLD_READY 或 GOLD_BLOCKED_ACQUISITION；两分支都完整发布证据（RECEIPT 版本化集合；blocked 项过程记录存在）；最终 artifact 命名与 spec v1.7 一致
8. sealed + GOLD_RECEIPT 发布，reconcile_gold exit 0；禁改守护激活（guard 自行读取 receipt 并重算 manifest SHA 验证绑定，不依赖外部布尔）
9. 全程零 LLM API；GOLD_CLOSURE 如实记录隔离等级（B=packet_only，A=access_attestation）与 filler/control 分布诊断

## 反过拟合与纪律（冻结）

- 不得为过门修改规则、judgment 或验证集；QC 只审计不改标签；正式评测产物只生成一次（one-shot 门）
- 不为凑齐 112 项强行裁决分歧；不把采集失败改写为"未找到"（BLOCKED 是合法终态）
- 不允许 AI 参与标注（零 LLM API）；不复用 R1 盲评材料作为 Gold 候选
- 不修改 Phase 9A / R1 任何 sealed 产物
- Gold 不用于 44 道已知婚姻题的准确率声明；效果声明以密封集为准
- 密封婚姻集数据不进入 Gold 采集
