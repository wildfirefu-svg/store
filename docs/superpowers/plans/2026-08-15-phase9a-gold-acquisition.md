# Phase 9A-Gold item-centered 人工 Gold 采集 Implementation Plan（v4）

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
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldBaseline -q`
Expected: FAIL。

- [ ] **Step 4: 生成 upstream_inputs_sha.json（单源读取 Phase 8/9A manifest）**

```python
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
    "note": "单源读取 Phase 8/9A manifest，非 raw-byte 重算",
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
    for item in items:
        item_id = item["item_id"]
        terms = [t for t in item["required_term"].split("|") if t.strip()] or [item_id]
        plans.append({
            "item_id": item_id,
            "steps": [
                {"step_id": f"{item_id}_s1", "entrypoint": "search_gejue", "args": {"query": terms[0]}, "query_terms": terms, "filters": {}, "corpus_snapshot_sha256": upstream["item_query_map_sha256"]},
                {"step_id": f"{item_id}_hn_s1", "entrypoint": "search_gejue", "args": {"query": terms[0]}, "query_terms": terms, "filters": {"exclude_relevant": True}, "corpus_snapshot_sha256": upstream["item_query_map_sha256"]},
            ],
        })
    _atomic_json(out / "gold_search_plans.json", {"schema_version": "1.0", "plans": plans})
    bv_plans = []
    for item in items:
        item_id = item["item_id"]
        terms = [t for t in item["required_term"].split("|") if t.strip()] or [item_id]
        bv_plans.append({
            "item_id": item_id,
            "steps": [{"step_id": f"{item_id}_bv1", "entrypoint": "search_gejue", "args": {"query": terms[0]}, "query_terms": terms, "filters": {}, "corpus_snapshot_sha256": upstream["item_query_map_sha256"]}],
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


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    # 注意：validator 在 config 冻结前运行（校验草稿），因此只校验自身已冻结；config 条目在 Task 2 才入 manifest
    pm.verify_frozen(PG / "gold_manifest.json", ["validate_gold_config_py"], required_stage="config_frozen")
    validate_item_definitions(PG / "gold_item_definitions.json")
    defs = json.loads((PG / "gold_item_definitions.json").read_text(encoding="utf-8"))
    item_ids = {i["item_id"] for i in defs["items"]}
    validate_search_plans(PG / "gold_search_plans.json", item_ids)
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
- `role: str` ∈ {"curator_A", "curator_B"}
- `log_path: Path`（access log 路径）

**输出 schema（追加 JSONL 行）：**
```json
{"ts": "2026-08-15T10:00:00", "role": "curator_A", "canonical_key": "kb:gejue:hy_002", "source_dir": "docs/phase8/marriage-capability"}
```

**失败状态：**
- `NOT_CODE_FROZEN`：manifest 未到 code_frozen
- `CANONICAL_KEY_NOT_FOUND`：无法在冻结语料解析
- `ROLE_NOT_ALLOWED`：role 不是 A/B 之一

**纯函数算法：**
1. `verify_frozen(["gold_read_access_py", "gold_search_plans"], required_stage="code_frozen")`
2. 解析 canonical_key → 从冻结 classic_texts_freeze.json / kb_snapshot.db 读取 doc_text
3. 追加 JSONL 行到 log_path
4. 返回 doc_text

**生产入口：** `gold_read_access.py read --key KEY --role ROLE --log LOG_PATH`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldReadAccess:
    def test_access_log_schema(self, tmp_path):
        ra = _load_module("gold_read_access", "docs/phase9a/gold/gold_read_access.py")
        log = tmp_path / "access.jsonl"
        text = ra.read_corpus("kb:gejue:hy_002", role="curator_A", log_path=log)
        assert isinstance(text, str)
        lines = [json.loads(l) for l in log.open(encoding="utf-8") if l.strip()]
        assert len(lines) == 1
        assert lines[0]["role"] == "curator_A"
        assert lines[0]["canonical_key"] == "kb:gejue:hy_002"
        assert "ts" in lines[0]

    def test_access_rejects_bad_role(self, tmp_path):
        ra = _load_module("gold_read_access", "docs/phase9a/gold/gold_read_access.py")
        try:
            ra.read_corpus("kb:gejue:hy_002", role="developer", log_path=tmp_path / "access.jsonl")
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


def read_corpus(canonical_key: str, role: str, log_path: Path) -> str:
    if role not in {"curator_A", "curator_B"}:
        sys.exit("ROLE_NOT_ALLOWED")
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    import retriever
    pm.verify_frozen(PG / "gold_manifest.json", ["gold_read_access_py", "gold_search_plans"], required_stage="code_frozen")
    doc_text = retriever.fetch(canonical_key)
    if doc_text is None:
        sys.exit(f"CANONICAL_KEY_NOT_FOUND: {canonical_key}")
    _append_jsonl(log_path, {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "role": role,
        "canonical_key": canonical_key,
        "source_dir": "docs/phase8/marriage-capability",
    })
    return doc_text


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
- `CORPUS_SHA_MISMATCH`：实际语料 SHA 与 plan 不一致
- `UNKNOWN_ENTRYPOINT`

**纯函数算法：**
1. verify_frozen
2. 检查 step_id 是否已在 results_file 中存在
3. 调用 entrypoint 获取候选 canonical_key 列表
4. 按字典序排序，再去重
5. 计算 `sha256(json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")`
6. 原子追加 JSONL 行

**生产入口：** `gold_search_exec.py --plan-file PATH --results-file PATH --step-id ID`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldSearchExec:
    def test_unique_terminal_row(self, tmp_path):
        se = _load_module("gold_search_exec", "docs/phase9a/gold/gold_search_exec.py")
        results = tmp_path / "results.jsonl"
        step = {"step_id": "test_s1", "item_id": "test#i1", "entrypoint": "_mock_search", "args": {"query": "x"}, "query_terms": ["x"], "filters": {}, "corpus_snapshot_sha256": "*"}
        se.execute_step(step, results, entrypoints={"_mock_search": lambda args: ["kb:a:1", "kb:a:1", "kb:b:2"]})
        lines = [json.loads(l) for l in results.open(encoding="utf-8") if l.strip()]
        assert len(lines) == 1
        assert lines[0]["ordered_candidate_keys"] == ["kb:a:1", "kb:b:2"]
        assert lines[0]["candidate_count"] == 2

    def test_duplicate_step_fails(self, tmp_path):
        se = _load_module("gold_search_exec", "docs/phase9a/gold/gold_search_exec.py")
        results = tmp_path / "results.jsonl"
        step = {"step_id": "test_s1", "item_id": "test#i1", "entrypoint": "_mock_search", "args": {"query": "x"}, "query_terms": ["x"], "filters": {}, "corpus_snapshot_sha256": "*"}
        se.execute_step(step, results, entrypoints={"_mock_search": lambda args: ["kb:a:1"]})
        try:
            se.execute_step(step, results, entrypoints={"_mock_search": lambda args: ["kb:a:1"]})
            raised = False
        except SystemExit:
            raised = True
        assert raised
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


def execute_step(step: dict, results_file: Path, entrypoints: dict | None = None) -> dict:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(PG / "gold_manifest.json", ["gold_search_exec_py", "gold_search_plans"], required_stage="code_frozen")
    if step["step_id"] in _existing_step_ids(results_file):
        sys.exit(f"STEP_ALREADY_EXECUTED: {step['step_id']}")
    eps = entrypoints or {"search_gejue": _search_gejue}
    fn = eps.get(step["entrypoint"])
    if fn is None:
        sys.exit(f"UNKNOWN_ENTRYPOINT: {step['entrypoint']}")
    raw_keys = fn(step["args"])
    keys = sorted(set(raw_keys))
    row = {
        "step_id": step["step_id"],
        "item_id": step["item_id"],
        "ordered_candidate_keys": keys,
        "candidate_keys_sha256": _canonical_sha(keys),
        "candidate_count": len(keys),
    }
    results_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = results_file.with_name(results_file.name + ".tmp")
    with tmp.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(results_file)
    return row


def _search_gejue(args: dict) -> list[str]:
    import retriever
    return retriever.search(args["query"], filters=args.get("filters", {}))


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
6. 回流：某层候选少于配额时，缺口回流到剩余层（按 item_id 字典序继续补足）
7. RNG：`random.Random(seed)` 全局单实例；每层内用该实例无放回抽取该层配额数

**生产入口：** `gold_hn_sampler.py --proposals PATH --output PATH`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldHNSampler:
    def test_stratified_counts(self):
        sampler = _load_module("gold_hn_sampler", "docs/phase9a/gold/gold_hn_sampler.py")
        candidates = {
            "item_a": [f"k{i}" for i in range(10)],
            "item_b": [f"k{i}" for i in range(10, 20)],
            "item_c": [f"k{i}" for i in range(20, 25)],
        }
        result = sampler.sample_hn(candidates, seed=20260814, ratio=0.2)
        total = sum(len(v) for v in candidates.values())
        expected_total = (total * 2 + 9) // 10  # ceil(total * 0.2)
        sampled = sum(len(v) for v in result["sampled"].values())
        assert sampled == expected_total, f"expected {expected_total}, got {sampled}"

    def test_oracle_matches_production(self):
        sampler = _load_module("gold_hn_sampler", "docs/phase9a/gold/gold_hn_sampler.py")
        candidates = {"item1": ["a", "b", "c"], "item2": ["d", "e"]}
        expected = sampler._compute_stratified_sample(candidates, seed=20260814, ratio=0.2)
        actual = sampler.sample_hn(candidates, seed=20260814, ratio=0.2)
        assert actual == expected
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
    """测试 oracle：纯函数，与生产函数完全独立实现。"""
    if not 0 < ratio <= 1:
        sys.exit("RATIO_OUT_OF_RANGE")
    if not candidates or all(not v for v in candidates.values()):
        sys.exit("EMPTY_CANDIDATE_SET")
    sorted_items = sorted(candidates)
    pools = {item: sorted(set(candidates[item])) for item in sorted_items}
    total = sum(len(pools[item]) for item in sorted_items)
    target = math.ceil(total * ratio)
    floor_sum = 0
    floors = {}
    for item in sorted_items:
        floors[item] = math.floor(len(pools[item]) * ratio)
        floor_sum += floors[item]
    remainder = target - floor_sum
    quotas = dict(floors)
    for item in sorted_items:
        if remainder <= 0:
            break
        add = min(remainder, len(pools[item]) - quotas[item])
        quotas[item] += add
        remainder -= add
    # 回流：某层候选少于配额时，缺口回流到剩余层
    overflow = 0
    sampled = {}
    rng = random.Random(seed)
    for item in sorted_items:
        quota = quotas[item] + overflow
        pool = pools[item]
        if quota > len(pool):
            overflow = quota - len(pool)
            quota = len(pool)
        else:
            overflow = 0
        sampled[item] = sorted(rng.sample(pool, quota))
    # 如果还有 overflow（总候选不足），本函数不失败，但实际生产会报 EMPTY_CANDIDATE_SET 或记录
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
- `BLIND_PACKET_RECEIPT_rN.json`：`{"packet_sha256": "...", "packet_lines": 120, "candidate_keys_sha256": "...", "round": 1}`

**失败状态：**
- `NOT_CODE_FROZEN`
- `R2_R3_TRIGGER_FALSE`：round_num>1 但 trigger_condition_met=False
- `NO_CONFIRMED_POSITIVE_FOR_CONTROL`：positive_control pool 为空
- `FILLER_POOL_EXHAUSTED`：某 item filler 候选不足

**纯函数算法：**
1. verify_frozen
2. 若 round_num > 1 则断言 trigger_condition_met
3. 构建条目：
   - positive proposal 条目（类型标记仅内部，不写入 packet）
   - sampled_hn 条目
   - positive_control 条目：从 confirmed_positives 按 (item_id, canonical_key) 字典序排序；优先无放回；数量 = 该轮真实 HN 条数；不足时按序循环抽取并标记 reused
   - filler 条目：n_filler_i = ceil(max(n_positive_i, n_sampled_hn_i) * 0.5)；候选池 = 全部 canonical_key 字典序排除已用 key；RNG = random.Random(20260815 + stable_hash(item_id))；无放回抽取
4. 全局打乱：random.Random(20260815 + round_num)
5. 分配 blind_id：`blind_r{N}_001` 起
6. 通过 gold_read_access 填充 document_text（role=developer？不，role 应为 publisher，但 spec 只允许 A/B。这里用 publisher 角色并记录 access log）
7. 写 packet 文件；计算 receipt

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

    def test_packet_no_type_leak(self, tmp_path):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        # mock read access
        packet = builder.build_packet(
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


def build_packet(
    round_num: int,
    proposals: dict[str, dict],
    sampled_hn: dict[str, list[str]],
    confirmed_positives: list[tuple[str, str]],
    seed: int,
    trigger_condition_met: bool = True,
    read_corpus: callable | None = None,
    all_keys: list[str] | None = None,
) -> list[dict]:
    if round_num > 1 and not trigger_condition_met:
        sys.exit("R2_R3_TRIGGER_FALSE")
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(PG / "gold_manifest.json", ["gold_blind_packet_builder_py", "gold_search_plans"], required_stage="code_frozen")
    read_fn = read_corpus or _default_read_corpus
    keys_source = all_keys or _default_all_keys()
    internal_entries = []  # (item_id, canonical_key, internal_type)
    for item_id, item in proposals.items():
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
    # 全局打乱
    rng = random.Random(20260815 + round_num)
    shuffled = internal_entries[:]
    rng.shuffle(shuffled)
    packet = []
    for idx, (item_id, key, internal_type) in enumerate(shuffled, start=1):
        packet.append({
            "blind_id": f"blind_r{round_num}_{idx:03d}",
            "item_id": item_id,
            "canonical_key": key,
            "document_text": read_fn(key),
            "_type": internal_type,  # 不写入最终文件；在 write_packet 前移除
        })
    return packet


def write_packet(packet: list[dict], path: Path) -> None:
    out = [{k: v for k, v in row.items() if not k.startswith("_")} for row in packet]
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in out), encoding="utf-8", newline="\n")


def build_packet_receipt(packet: list[dict]) -> dict:
    path = Path("__tmp_packet__.jsonl")
    write_packet(packet, path)
    raw = path.read_bytes()
    keys = [row["canonical_key"] for row in packet]
    path.unlink(missing_ok=True)
    return {
        "packet_sha256": hashlib.sha256(raw).hexdigest(),
        "packet_lines": len(packet),
        "candidate_keys_sha256": _canonical_sha(keys),
    }


def _default_read_corpus(key: str) -> str:
    import gold_read_access as ra
    return ra.read_corpus(key, role="curator_A", log_path=PG / "gold_access_log_a.jsonl")


def _default_all_keys() -> list[str]:
    import retriever
    return retriever.all_keys()


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
    packet = build_packet(args.round, proposals, sampled_hn, controls, seed=20260815, trigger_condition_met=args.trigger)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_path = out_dir / f"gold_blind_review_packet_r{args.round}.jsonl"
    write_packet(packet, packet_path)
    receipt = build_packet_receipt(packet)
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
- `BLIND_ID_NOT_IN_PACKET`
- `LABEL_NOT_FOUR_STATE`

**纯函数算法：**
1. 读取 receipt，校验 packet SHA 与 labels SHA
2. 读取 packet（blind_id -> canonical_key/item_id）
3. 读取 labels（blind_id -> label）
4. 对每条 blind_id 查 FOUR_STATE_MAP 得到 derived 结果
5. 输出 map

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
        receipt.write_text(json.dumps({"packet_sha256": "bad", "label_sha256": "bad"}), encoding="utf-8")
        try:
            mapper.unblind(round_num=1, packet_path=packet, labels_path=labels, receipt_path=receipt, output=tmp_path / "out.json")
            raised = False
        except SystemExit:
            raised = True
        assert raised
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


def unblind(round_num: int, packet_path: Path, labels_path: Path, receipt_path: Path, output: Path, internal_types: dict[str, str] | None = None) -> dict:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(PG / "gold_manifest.json", ["gold_unblind_mapper_py", "gold_blind_packet_builder_py"], required_stage="code_frozen")
    if not receipt_path.exists():
        sys.exit("RECEIPT_MISSING")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("packet_sha256") != _sha256_file(packet_path):
        sys.exit("PACKET_SHA_MISMATCH")
    if receipt.get("label_sha256") != _sha256_file(labels_path):
        sys.exit("LABEL_SHA_MISMATCH")
    packet_rows = [json.loads(l) for l in packet_path.open(encoding="utf-8") if l.strip()]
    label_rows = [json.loads(l) for l in labels_path.open(encoding="utf-8") if l.strip()]
    packet_by_blind = {r["blind_id"]: r for r in packet_rows}
    labels_by_blind = {r["blind_id"]: r for r in label_rows}
    types = internal_types or {}
    result_map = {}
    for blind_id, prow in packet_by_blind.items():
        label_row = labels_by_blind.get(blind_id)
        if label_row is None:
            sys.exit(f"BLIND_ID_NOT_IN_LABELS: {blind_id}")
        label = label_row["label"]
        if label not in VALID_LABELS:
            sys.exit(f"LABEL_NOT_FOUR_STATE: {label}")
        ptype = types.get(blind_id, "positive_proposal")
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
        "map": result_map,
    }
    output.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    unblind(args.round, args.packet, args.labels, args.receipt, args.output)


if __name__ == "__main__":
    main()
```

**注意：** 实际生产时 internal_types 需要通过 packet builder 侧保留的 sidecar（非最终产物）传入，或在 unblind 时由 A 侧 proposals 与 sampled_hn 重新推导。计划 Step 4 实现 `derive_internal_types(packet_path, proposals, sampled_hn)` 函数。

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

**纯函数算法（gold_validate）：**
1. 加载 gold_v1.json
2. 检查 112 项、状态枚举、hard_negative_status 组合
3. 对每个 positive：canonical_key 在对应 step 候选中；evidence_quote 是 doc_text 子串；trace_step_refs 可解析
4. 对每个 no_positive：executed_step_ids 覆盖；all_candidates_reviewed；b_verification 聚合规则满足
5. 检查 HN sample 列表与 sampler 算法输出一致

**纯函数算法（reconcile_gold）：**
1. 加载 manifest、RECEIPT
2. 校验 receipt["manifest_sha256"] == sha256(json_canonical(manifest))
3. 校验 receipt artifact 集合与 spec v1.7 版本化规则一致
4. 逐项核对 artifact SHA
5. 校验每轮 BLIND_PACKET_RECEIPT → packet SHA、B_LABEL_RECEIPT → label SHA + packet SHA、unblind map → packet SHA + label SHA
6. 校验 B access log 无语料读取（B=packet_only）

**生产入口：**
- `gold_validate.py --gold-dir DIR`
- `reconcile_gold.py --gold-dir DIR`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldValidateAndReconcile:
    def test_validate_rejects_invalid_status(self, tmp_path):
        validator = _load_module("gold_validate", "docs/phase9a/gold/gold_validate.py")
        bad = {"schema_version": "1.0", "item_count": 112, "acquisition_verdict": "GOLD_READY", "items": [{"item_id": "x", "status": "weird"}] * 112}
        try:
            validator.validate_gold(bad)
            raised = False
        except SystemExit:
            raised = True
        assert raised

    def test_reconcile_rejects_receipt_manifest_mismatch(self, tmp_path):
        reconciler = _load_module("reconcile_gold", "docs/phase9a/gold/reconcile_gold.py")
        try:
            reconciler.check_receipt_manifest_binding({"manifest_sha256": "bad"}, {"sha256": "good"})
            raised = False
        except SystemExit:
            raised = True
        assert raised
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldValidateAndReconcile -q`
Expected: FAIL。

- [ ] **Step 3: 实现 gold_validate.py 骨架 + reconcile_gold.py 骨架**

由于篇幅限制，计划在此处给出函数签名与核心纯函数，完整实现由 subagent 按骨架补全。

gold_validate.py 骨架：
```python
"""Phase 9A-Gold：终态数据校验器。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VALID_STATUS = {"anchored", "no_relevant_document_found_under_frozen_plan", "BLOCKED_ACQUISITION", "BLOCKED_HARD_NEGATIVE_ACQUISITION"}
VALID_HN_STATUS = {"found", "no_hard_negative_found", "not_applicable"}


def validate_gold(gold: dict) -> None:
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
            for ref in p.get("trace_step_refs", []):
                if "@" not in ref:
                    sys.exit(f"TRACE_REF_UNRESOLVED: {ref}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-dir", type=Path, default=Path("docs/phase9a/gold"))
    args = parser.parse_args()
    gold = json.loads((args.gold_dir / "gold_v1.json").read_text(encoding="utf-8"))
    validate_gold(gold)
    print("gold_validate passed")


if __name__ == "__main__":
    main()
```

reconcile_gold.py 骨架：
```python
"""Phase 9A-Gold：对账脚本。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def json_canonical_sha(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n").hexdigest()


def check_receipt_manifest_binding(receipt: dict, manifest: dict) -> None:
    if receipt.get("manifest_sha256") != json_canonical_sha(manifest):
        sys.exit("RECEIPT_MANIFEST_SHA_MISMATCH")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-dir", type=Path, default=Path("docs/phase9a/gold"))
    args = parser.parse_args()
    gd = args.gold_dir
    manifest = json.loads((gd / "gold_manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((gd / "GOLD_RECEIPT.json").read_text(encoding="utf-8"))
    if manifest.get("stage") != "sealed":
        sys.exit("MANIFEST_STAGE_NOT_SEALED")
    check_receipt_manifest_binding(receipt, manifest)
    # artifact 集合精确相等（spec v1.7 §8 版本化规则）
    rounds = sorted({int(k.split("_r")[1].split(".")[0]) for k in manifest["entries"] if "blind_review_packet_r" in k})
    expected = _expected_artifact_set(rounds)
    actual = set(receipt["artifacts"])
    if actual != expected:
        sys.exit(f"RECEIPT_ARTIFACT_SET_MISMATCH: missing={sorted(expected - actual)[:5]} extra={sorted(actual - expected)[:5]}")
    # B 侧 access log 不得含语料读取（packet-only 证据）
    access_log = args.gold_dir / "gold_access_log.jsonl"
    if access_log.exists():
        b_reads = [json.loads(l) for l in access_log.open(encoding="utf-8") if l.strip() and json.loads(l)["role"] == "curator_B"]
        if b_reads:
            sys.exit("ACCESS_LOG_B_CORPUS_READ")
    print("reconcile_gold passed")


def _expected_artifact_set(rounds: list[int]) -> set[str]:
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


if __name__ == "__main__":
    main()
```

**v4 计划明确：** gold_validate 骨架已覆盖状态枚举/组合约束/positive resolution/trace_ref 格式校验；subagent 实现时在此骨架上追加 canonical_key 可解析、evidence_quote 子串真实、候选集合严格相等、HN sample 算法重算四项检查（均有独立测试向量）；reconcile 骨架已覆盖 receipt-manifest 绑定、artifact 集合精确相等、B 侧 access log 校验；subagent 追加逐项 SHA 核对与盲审 receipt 链校验。sealed 产物中不允许残留 TODO。

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
- `GOLD_V1_ALREADY_EXISTS`（one-shot）
- `VALIDATION_FAILED`
- `MANIFEST_NOT_CODE_FROZEN`
- `ARTIFACT_BYTES_MISMATCH`

**失败状态（guard）：**
- `RECEIPT_MISSING`
- `RECEIPT_MANIFEST_SHA_MISMATCH`
- `GUARD_CONFIG_NOT_FROZEN`

**纯函数算法（finalize_gold）：**
1. verify_frozen 所需代码/配置
2. 读取 A/B 结果，按规则合并为最终 gold_v1.json
3. 生成 gold_acquisition_log.jsonl（合并 A log + B labels + unblind maps + verification labels）
4. 生成 gold_search_results.jsonl（合并 A search results + B verification steps）
5. 生成 gold_access_log.jsonl（合并 A/B access logs）
6. 生成 GOLD_CLOSURE.md
7. freeze 全部 sealed 条目
8. set_stage("sealed")
9. 生成 GOLD_RECEIPT.json（绑定 sealed manifest SHA + 版本化 artifact 集合）

**A/B 结果机械合并规则：**
- 正例：A proposal + B confirmed → gold_v1 positives（resolution=confirmed）
- 分歧：A proposal + B disagreement → 若存在 C adjudication label=relevant → third_party_adjudicated；否则 item 状态 BLOCKED_ACQUISITION
- HN：A 选择 + B confirmed/rejected/uncertain → 按映射派生；replacement 仅一次机会
- no_positive：A 声明 + B verification 全 irrelevant → no_relevant_document_found_under_frozen_plan；否则分歧处理

**纯函数算法（guard）：**
1. 读取 GOLD_RECEIPT.json
2. 重算 receipt["manifest_sha256"] == sha256(gold_manifest.json canonical)
3. 读取 gold_guard_config.json（已在 config_frozen 冻结）
4. 返回 protected_paths；否则返回 None 或 sys.exit

**生产入口：**
- `finalize_gold.py --gold-dir DIR`
- guard hook 在 pre-commit 中调用 `load_gold_guard_config(receipt_path)`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldFinalizerAndGuard:
    def test_finalize_one_shot(self, tmp_path):
        fin = _load_module("finalize_gold", "docs/phase9a/gold/finalize_gold.py")
        mirror = tmp_path / "gold"
        mirror.mkdir()
        (mirror / "gold_v1.json").write_text("{}", encoding="utf-8")
        try:
            fin.main(gold_dir=mirror)
            raised = False
        except SystemExit:
            raised = True
        assert raised

    def test_guard_verifies_receipt_binding(self, tmp_path):
        guard = _load_module("guard_data_artifacts", ".qoder/hooks/guard_data_artifacts.py")
        # 用真实 GOLD_RECEIPT + manifest 验证
        receipt_path = PG / "GOLD_RECEIPT.json"
        manifest_path = PG / "gold_manifest.json"
        if receipt_path.exists() and manifest_path.exists():
            config = guard.load_gold_guard_config(receipt_path=receipt_path, manifest_path=manifest_path)
            assert config is not None
            assert "docs/phase9a/gold/gold_v1.json" in config["protected_paths"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldFinalizerAndGuard -q`
Expected: FAIL。

- [ ] **Step 3: 实现 finalize_gold.py + 修改 guard**

finalize_gold.py 骨架：
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


def derive_final_items(proposals: dict, unblind_maps: list[dict], b_verification_labels: dict[str, list[str]], c_adjudication: dict[tuple[str, str], str]) -> list[dict]:
    """A/B 结果机械合并（唯一裁决规则，subagent 不得改写）。按 (item_id, canonical_key) 取最后一轮派生结果。"""
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
        hn_out, hn_blocked = [], False
        for hn in item.get("hard_negatives", []):
            d = last_derived.get(((item_id, hn["canonical_key"]), "hard_negative"))
            if d == "confirmed":
                hn_out.append({**hn, "b_reviewed": True, "b_review_result": "confirmed"})
            elif d in {"rejected", "uncertain", None}:
                hn_blocked = True
        if disagreement:
            out["status"] = "BLOCKED_ACQUISITION"
            out["blocked_reason"] = "A/B disagreement unresolved"
        elif hn_blocked:
            out["status"] = "BLOCKED_HARD_NEGATIVE_ACQUISITION"
            out["blocked_reason"] = "hard negative rejected/uncertain/unreviewed"
        elif item.get("no_positive_evidence"):
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
        out["hard_negative_status"] = (
            "found" if hn_out else ("no_hard_negative_found" if item.get("hard_negative_status") == "no_hard_negative_found" else "not_applicable")
        )
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


def main(gold_dir: Path | None = None) -> None:
    gd = gold_dir or PG
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    import gold_validate as gv
    pm.verify_frozen(gd / "gold_manifest.json", ["finalize_gold_py", "gold_validate_py"], required_stage="code_frozen")
    if (gd / "gold_v1.json").exists():
        sys.exit("GOLD_V1_ALREADY_EXISTS")
    proposals, unblind_maps, bv_labels, c_adj = _load_inputs(gd)
    final_items = derive_final_items(proposals, unblind_maps, bv_labels, c_adj)
    blocked = [i for i in final_items if i["status"].startswith("BLOCKED")]
    verdict = "GOLD_READY" if not blocked else "GOLD_BLOCKED_ACQUISITION"
    gold = {"schema_version": "1.0", "item_count": 112, "acquisition_verdict": verdict, "items": final_items}
    gv.validate_gold(gold)
    # subagent 补全剩余编排：写 sealed 产物（gold_v1.json / gold_acquisition_log.jsonl / gold_search_results.jsonl / gold_access_log.jsonl / GOLD_CLOSURE.md）→ freeze → set_stage(sealed) → 发布 GOLD_RECEIPT（细节见下方 v4 计划明确）
    print(f"finalize_gold: acquisition_verdict={verdict}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-dir", type=Path, default=PG)
    args = parser.parse_args()
    main(args.gold_dir)
```

guard_data_artifacts.py 修改（在现有 hook 中新增）：
```python
def load_gold_guard_config(receipt_path: Path, manifest_path: Path) -> dict | None:
    if not receipt_path.exists():
        return None
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n").hexdigest()
    if receipt.get("manifest_sha256") != expected:
        sys.exit("RECEIPT_MANIFEST_SHA_MISMATCH")
    gc = json.loads(manifest_path.with_name("gold_guard_config.json").read_text(encoding="utf-8"))
    return gc
```

**v4 计划明确：** 骨架已提供完整机械合并规则 `derive_final_items`（不得改写）；subagent 补全剩余编排（读取 A 快照/各轮 unblind map/B verification labels/C adjudication → 写 sealed 产物 → freeze → set_stage(sealed) → 发布 GOLD_RECEIPT）并写对应测试；sealed 产物中不允许残留 TODO。guard 修改必须通过 receipt 自行重算 manifest SHA 验证绑定，不接受外部 `receipt_valid` 布尔参数。

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

# 2. r1 blind packet
confirmed = [(item_id, p["canonical_key"]) for item_id, item in snapshot["items"].items() for p in item.get("positives", [])]
packet = builder.build_packet(
    round_num=1,
    proposals=snapshot["items"],
    sampled_hn=sample_list["sampled"],
    confirmed_positives=confirmed,
    seed=20260815,
    trigger_condition_met=True,
)
builder.write_packet(packet, PG / "gold_blind_review_packet_r1.jsonl")
receipt1 = builder.build_packet_receipt(packet)
receipt1["round"] = 1
(PG / "BLIND_PACKET_RECEIPT_r1.json").write_text(json.dumps(receipt1, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
pm.freeze(PG / "gold_manifest.json", {
    "gold_blind_review_packet_r1": (PG / "gold_blind_review_packet_r1.jsonl", "jsonl_canonical"),
    "BLIND_PACKET_RECEIPT_r1": (PG / "BLIND_PACKET_RECEIPT_r1.json", "json_canonical"),
})

# 3. B verification packet（no-positive 子集）
no_positive_items = [item_id for item_id, item in snapshot["items"].items() if item["status"] == "no_relevant_document_found_under_frozen_plan"]
verification_results = []
for item_id in no_positive_items:
    plan = next(p for p in json.loads((PG / "gold_b_verification_plans.json").read_text(encoding="utf-8"))["plans"] if p["item_id"] == item_id)
    for step in plan["steps"]:
        row = se.execute_step(step, PG / "gold_search_results.jsonl")
        verification_results.append(row)
# verification packet 仅含 candidate text，不含 A 结论
bv_packet = [{"item_id": r["item_id"], "canonical_key": k, "document_text": ra.read_corpus(k, role="curator_A", log_path=PG / "gold_access_log_a.jsonl")} for r in verification_results for k in r["ordered_candidate_keys"]]
builder.write_packet(bv_packet, PG / "gold_b_verification_packet.jsonl")
bv_receipt = builder.build_packet_receipt(bv_packet)
bv_receipt["round"] = "verification"
(PG / "B_VERIFICATION_PACKET_RECEIPT.json").write_text(json.dumps(bv_receipt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
pm.freeze(PG / "gold_manifest.json", {
    "gold_b_verification_packet": (PG / "gold_b_verification_packet.jsonl", "jsonl_canonical"),
    "B_VERIFICATION_PACKET_RECEIPT": (PG / "B_VERIFICATION_PACKET_RECEIPT.json", "json_canonical"),
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
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_hn_qc_sample_list.json docs/phase9a/gold/gold_blind_review_packet_r1.jsonl docs/phase9a/gold/BLIND_PACKET_RECEIPT_r1.json docs/phase9a/gold/gold_b_verification_packet.jsonl docs/phase9a/gold/B_VERIFICATION_PACKET_RECEIPT.json docs/phase9a/gold/gold_search_results.jsonl tests/test_phase9a_gold.py
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

**生产入口：**
- 发布器脚本：校验 BLIND_PACKET_RECEIPT_rN 后复制 packet 到 B workspace
- B 打标后运行 label receipt 生成脚本：`build_label_receipt(labels_path, packet_path, packet_sha, round_num)`（见下方实现）
- `gold_unblind_mapper.py --round N ...` 生成解盲映射
- r2/r3 生成脚本：`check_r2_trigger(r1_unblind_map)` / `check_r3_trigger(r2_unblind_map, replacements)`（见下方实现）

**label receipt 与触发条件生成器（冻结实现，追加到 gold_blind_packet_builder.py，追加后重新冻结该条目——注意：append-only manifest 下同条目 SHA 变化会 fail-closed，因此这三个函数必须在 Task 6 冻结 builder 时一并写入；若 Task 6 已冻结，则改放入新文件 `gold_round_gate.py` 并作为新条目冻结，测试同步改从该文件导入）：**

```python
import hashlib
import json
import sys
from pathlib import Path


def build_label_receipt(labels_path: Path, packet_path: Path, packet_sha: str, round_num: int) -> dict:
    label_raw = labels_path.read_bytes()
    label_sha = hashlib.sha256(label_raw).hexdigest()
    labels = [json.loads(l) for l in labels_path.open(encoding="utf-8") if l.strip()]
    packets = [json.loads(l) for l in packet_path.open(encoding="utf-8") if l.strip()]
    packet_sha_actual = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    if packet_sha_actual != packet_sha:
        sys.exit("LABEL_RECEIPT_PACKET_MISMATCH")
    label_ids = {r["blind_id"] for r in labels}
    packet_ids = {r["blind_id"] for r in packets}
    if label_ids != packet_ids:
        sys.exit(f"LABEL_BLIND_ID_COVERAGE_INCOMPLETE: missing={sorted(packet_ids - label_ids)[:5]}")
    blind_id_set_sha = hashlib.sha256(
        json.dumps(sorted(label_ids), ensure_ascii=False).encode("utf-8") + b"\n"
    ).hexdigest()
    return {
        "round": round_num,
        "label_sha256": label_sha,
        "packet_sha256": packet_sha,
        "label_lines": len(labels),
        "packet_lines": len(packets),
        "blind_id_set_sha256": blind_id_set_sha,
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
    return has_rejected and all(r.get("trace_step_refs") for r in replacements) and bool(replacements)
```

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

- [ ] **Step 1: 写失败测试（独立测试向量）**

```python
class TestGoldBlindReview:
    def test_label_receipt_blind_id_set(self, tmp_path):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        packet_path = tmp_path / "packet.jsonl"
        packet_path.write_text(
            json.dumps({"blind_id": "b1", "item_id": "i1", "canonical_key": "k1", "document_text": "t1"}) + "\n"
            + json.dumps({"blind_id": "b2", "item_id": "i2", "canonical_key": "k2", "document_text": "t2"}) + "\n",
            encoding="utf-8")
        labels_path = tmp_path / "labels.jsonl"
        labels_path.write_text(
            json.dumps({"blind_id": "b1", "label": "relevant", "note": "n"}) + "\n"
            + json.dumps({"blind_id": "b2", "label": "irrelevant", "note": "n"}) + "\n",
            encoding="utf-8")
        packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        receipt = builder.build_label_receipt(labels_path, packet_path, packet_sha, round_num=1)
        assert receipt["label_lines"] == 2 and receipt["packet_lines"] == 2
        assert receipt["blind_id_set_sha256"] == hashlib.sha256(
            json.dumps(["b1", "b2"], ensure_ascii=False).encode("utf-8") + b"\n").hexdigest()

    def test_label_receipt_coverage_fail_closed(self, tmp_path):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        packet_path = tmp_path / "packet.jsonl"
        packet_path.write_text(json.dumps({"blind_id": "b1", "item_id": "i", "canonical_key": "k", "document_text": "t"}) + "\n", encoding="utf-8")
        labels_path = tmp_path / "labels.jsonl"
        labels_path.write_text(json.dumps({"blind_id": "b9", "label": "relevant", "note": "n"}) + "\n", encoding="utf-8")
        packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        try:
            builder.build_label_receipt(labels_path, packet_path, packet_sha, round_num=1)
            raised = False
        except SystemExit:
            raised = True
        assert raised

    def test_r2_trigger_condition(self):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        clean_map = {"map": {"b1": {"proposal_type": "hard_negative", "derived": "confirmed"}}}
        assert builder.check_r2_trigger(clean_map) is False
        dirty_map = {"map": {"b1": {"proposal_type": "hard_negative", "derived": "rejected"}}}
        assert builder.check_r2_trigger(dirty_map) is True

    def test_r3_requires_replacement_trace(self):
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        r2_map = {"map": {"b1": {"proposal_type": "hard_negative", "derived": "rejected"}}}
        assert builder.check_r3_trigger(r2_map, []) is False
        assert builder.check_r3_trigger(r2_map, [{"canonical_key": "k", "trace_step_refs": []}]) is False
        assert builder.check_r3_trigger(r2_map, [{"canonical_key": "k", "trace_step_refs": ["s1@k"]}]) is True

    def test_c_adjudication_schema(self):
        if (PG / "gold_c_adjudication.jsonl").exists():
            rows = [json.loads(l) for l in (PG / "gold_c_adjudication.jsonl").open(encoding="utf-8") if l.strip()]
            for r in rows:
                assert r["c_label"] in {"relevant", "partially_relevant", "irrelevant", "uncertain"}
                assert r["rationale"]
```

- [ ] **Step 2: 人工执行 B/C 流程 → 每轮 receipt 生成 → 冻结 → Commit**

每轮 B label 冻结后：
```python
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {
    f"gold_b_labels_r{r}": (PG / f"gold_b_labels_r{r}.jsonl", "jsonl_canonical"),
    f"B_LABEL_RECEIPT_r{r}": (PG / f"B_LABEL_RECEIPT_r{r}.json", "json_canonical"),
    f"gold_blind_unblind_map_r{r}": (PG / f"gold_blind_unblind_map_r{r}.json", "json_canonical"),
})
print(f"round {r} blind review artifacts frozen")
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
- Create: `docs/phase9a/gold/gold_access_log.jsonl`（合并 A/B）
- Create: `docs/phase9a/gold/GOLD_CLOSURE.md`
- Create: `docs/phase9a/gold/GOLD_RECEIPT.json`
- Modify: `docs/phase9a/gold/gold_manifest.json`（sealed）
- Test: `tests/test_phase9a_gold.py`

**A/B 结果机械合并规则：**
- 正例 confirmed：A proposal + B relevant → positives resolution=confirmed
- 正例分歧：A proposal + B 非 relevant → 查 C adjudication；C=relevant → third_party_adjudicated；否则 BLOCKED_ACQUISITION
- HN confirmed：A 选择 + B irrelevant → hard_negatives 标记 b_reviewed=true, b_review_result=confirmed
- HN rejected：A 选择 + B relevant/partially_relevant → A 可重选一次 replacement → r3；仍 rejected → BLOCKED_HARD_NEGATIVE_ACQUISITION
- HN uncertain：A 选择 + B uncertain → BLOCKED_HARD_NEGATIVE_ACQUISITION（无法裁决）
- no_positive：A 声明 + B verification 全 irrelevant → no_relevant_document_found_under_frozen_plan；任何 relevant/partially_relevant/uncertain → 分歧处理 → BLOCKED 或 C 裁决

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
# 按需追加 r2/r3 轮次产物
git diff --cached --name-only
git commit -m "chore(phase9a-gold): sealed + GOLD_RECEIPT published (acquisition_verdict=...)"
```

- [ ] **Step 5: guard 验证（零修改验证，不动 sealed 产物）**

```powershell
.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldSealed::test_guard_verifies_receipt_binding -q
```
Expected: PASS（guard 自行读取 GOLD_RECEIPT 并重算 manifest SHA 后返回 protected_paths）。禁止用实际修改 sealed 产物的方式测试。

---

## 任务总览（v4 结构）

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
