# Phase 9A-R1 silver relevance 标签校准 Implementation Plan（v2.6）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 校准 silver relevance 标签边界（cat_ok 规则修订），使独立验证集（61 条，37 item 覆盖）人工 QC effective_disagreement ≤6，产出 `SILVER_LABEL_CALIBRATED / SILVER_LABEL_NOT_CALIBRATED` 之一终态。

**Architecture:** 纯本地零 API；复用 Phase 9A 冻结输入（kb_snapshot.db、classic_texts 冻结版、strategy_outputs.jsonl、item_query_map.json）。执行顺序：**R1 manifest 创建（config_frozen）→ 归因证据入库 → 验证集样本 + 盲评 packet 冻结（在 v3 规则与任何 v3 label 前）→ 校准规则冻结（code_frozen）→ 校准 judgment 生成 → 人工 QC 盲评 → 一次性终态判定（原子发布）→ 产物封存（sealed）**。全部产物版本化新文件（不修改 Phase 9A sealed 产物）。

**Tech Stack:** Python 3.11+、sqlite3（只读 URI）、git object 读取（classic_texts 冻结版）、pytest、ruff（E9/F821 基线）。

**设计依据：** `docs/superpowers/specs/2026-08-14-phase9a-r1-silver-calibration-design.md` v1.2（commit `f2d65ea`，APPROVED）。
**前置冻结：** Phase 9A 已冻结（`docs/phase9a/CLOSURE_v2.md`，manifest_v4 sealed，reconcile exit 0）。

**命令约定：** PowerShell（本仓库主要 shell）；所有脚本的路径推导基于 `__file__`，可在任意工作目录（含 worktree）执行；commit 用显式 pathspec；pre-commit stash 冲突可原样重试一次，禁止 `--no-verify`。
**提交纪律：** 每个 commit 前先 `git status --porcelain` + `git diff --cached --name-only` 核对暂存清单，防止卷入并行蒸馏线 churn。

---

## 输入基线（Task 0 复核）

| 输入 | 路径 | 用途 |
|---|---|---|
| KB 快照（只读） | `docs/phase8/marriage-capability/kb_snapshot.db` | 检索源（不变） |
| classic_texts 冻结版 | `docs/phase8/marriage-capability/classic_texts_freeze.json` + git object | 检索源（不变） |
| 知识项清单 | `docs/phase9a/retrieval/item_query_map.json` | 112 项检索不可见 doctrine 项 |
| 冻结 strategy_outputs | `docs/phase9a/retrieval/strategy_outputs.jsonl` | 候选池（不变） |
| Phase 9A silver judgment | `docs/phase9a/retrieval/silver_relevance_judgment.jsonl` | 校准前基线（673 条） |
| Phase 9A QC 复核 | `docs/phase9a/retrieval/qc_human_review.jsonl` | 开发校准集（67 条） |
| Phase 9A manifest | `docs/phase9a/retrieval/manifest_v4.json` | 冻结产物清单（30 条目 sealed） |
| Phase 9A treatment fingerprint | `docs/phase9a/retrieval/treatment_fingerprint.json` | 原指纹（字节不变断言依据） |

---

## Task 0: R1 manifest 创建（config_frozen）+ 归因证据入库

**Files:**
- Create: `docs/phase9a/r1/manifest_v5.json`（初始 config_frozen）
- Create: `docs/phase9a/r1/attribution.py`
- Create: `docs/phase9a/r1/attribution.json`
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 复核 Phase 9A 对账与输入存在性**

Run:
```powershell
.venv/Scripts/python.exe docs/phase9a/retrieval/reconcile9a.py
Test-Path docs/phase9a/retrieval/strategy_outputs.jsonl
Test-Path docs/phase9a/retrieval/silver_relevance_judgment.jsonl
Test-Path docs/phase9a/retrieval/qc_human_review.jsonl
Test-Path docs/phase9a/retrieval/item_query_map.json
Test-Path docs/phase9a/retrieval/treatment_fingerprint.json
```
Expected: exit 0 无 FAIL；全部 True。

- [ ] **Step 2: 写失败测试**

`tests/test_phase9a_r1.py`（新建文件，顶部 helper）：
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
P8 = REPO / "docs" / "phase8" / "marriage-capability"

sys.path.insert(0, str(P8))
sys.path.insert(0, str(P9))
sys.path.insert(0, str(P9R1))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestR1ManifestInit:
    def test_manifest_v5_config_frozen(self):
        m = _load_json(P9R1 / "manifest_v5.json")
        assert m["stage"] == "config_frozen"
        # 冻结上游 manifest_v4 + 原 treatment fingerprint + manifest helper + 归因证据
        # P0 修订：真实 manifest_v4 不含 phase9a_manifest_py 条目，helper 冻结到 R1 manifest_v5
        for name in ("upstream_manifest_v4", "upstream_treatment_fingerprint", "phase9a_manifest_py", "attribution_py", "attribution_json"):
            assert name in m["entries"], f"{name} not frozen"


class TestAttribution:
    def test_attribution_frozen(self):
        attr = _load_json(P9R1 / "attribution.json")
        assert attr["total_disagreements"] == 36
        assert attr["distribution"]["partially_relevant_to_relevant"] == 31
        assert attr["distribution"]["partially_relevant_to_irrelevant"] == 4
        assert attr["distribution"]["irrelevant_to_partially_relevant"] == 1
        assert attr["key_finding"]["cat_match_false_count"] == 31
        assert attr["key_finding"]["query_no_category_count"] == 26
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestR1ManifestInit tests/test_phase9a_r1.py::TestAttribution -q`
Expected: FAIL。

- [ ] **Step 4: 实现 attribution.py（零 API 归因脚本）**

```python
"""Phase 9A-R1 归因：36 条分歧的零 API 分析（正式版本化脚本）。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    # P0 修订：脚本内部 verify_frozen，防绕过门禁（当前 manifest stage + 自身代码 + 上游）
    pm.verify_frozen(P9R1 / "manifest_v5.json", ["attribution_py", "upstream_manifest_v4", "upstream_treatment_fingerprint"], required_stage="config_frozen")
    reviews = [json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip()]
    judgment = {r["item_id"] + "|" + r["canonical_key"]: r for r in (json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip())}
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    qid_to_args = {}
    for item in item_map["items"]:
        for q in item["queries"]:
            qid_to_args[q["query_id"]] = q["args"]

    disagreements = []
    for r in reviews:
        key = r["item_id"] + "|" + r["canonical_key"]
        silver_label = judgment[key]["label"]
        human_label = r["human_label"]
        if silver_label != human_label:
            disagreements.append({
                "item_id": r["item_id"],
                "canonical_key": r["canonical_key"],
                "silver": silver_label,
                "human": human_label,
                "note": r.get("note", ""),
                "reason": judgment[key].get("reason", ""),
                "query_ids": judgment[key].get("query_ids", []),
            })

    pairs = Counter((d["silver"], d["human"]) for d in disagreements)
    pr_to_r = [d for d in disagreements if d["silver"] == "partially_relevant" and d["human"] == "relevant"]
    cat_false = sum(1 for d in pr_to_r if "cat_match=False" in d["reason"])
    no_cat_count = 0
    for d in pr_to_r:
        if "cat_match=False" in d["reason"]:
            for qid in d["query_ids"]:
                args = qid_to_args.get(qid, {})
                if not args.get("category"):
                    no_cat_count += 1
                    break

    out = {
        "schema_version": "1.0",
        "source": "Phase 9A qc_human_review.jsonl + silver_relevance_judgment.jsonl + item_query_map.json",
        "total_disagreements": len(disagreements),
        "distribution": {
            "partially_relevant_to_relevant": pairs.get(("partially_relevant", "relevant"), 0),
            "partially_relevant_to_irrelevant": pairs.get(("partially_relevant", "irrelevant"), 0),
            "irrelevant_to_partially_relevant": pairs.get(("irrelevant", "partially_relevant"), 0),
        },
        "key_finding": {
            "cat_match_false_count": cat_false,
            "query_no_category_count": no_cat_count,
            "conclusion": "silver 规则在 query 无 category 参数时强制降级为 partial，但人工判断认为同义词命中即足够",
        },
        "disagreements": disagreements,
    }
    P9R1.mkdir(parents=True, exist_ok=True)
    (P9R1 / "attribution.json").write_text(
        json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"attribution written: {len(disagreements)} disagreements")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 初始化 R1 manifest（config_frozen，冻结上游）→ 冻结 attribution_py → 运行生成归因**

先初始化 manifest_v5（P0 修订：必须 set_stage config_frozen + 冻结上游，否则后续 None→code_frozen 被状态机拒绝）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
P9R1 = Path("docs/phase9a/r1")
m = P9R1 / "manifest_v5.json"
pm.set_stage(m, "config_frozen")
pm.freeze(m, {
    "upstream_manifest_v4": (P9 / "manifest_v4.json", "json_canonical"),
    "upstream_treatment_fingerprint": (P9 / "treatment_fingerprint.json", "json_canonical"),
    # P0 修订：真实 manifest_v4 不含 phase9a_manifest_py 条目，helper 冻结到 R1 manifest_v5 并从其验证
    "phase9a_manifest_py": (P9 / "phase9a_manifest.py", "git_canonical_lf"),
})
print("manifest_v5 initialized at config_frozen (upstream + helper frozen)")
```

然后冻结 attribution 代码（P0 修订：attribution.py 内部也调 verify_frozen，防绕过）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
pm.freeze(P9R1 / "manifest_v5.json", {"attribution_py": (P9R1 / "attribution.py", "git_canonical_lf")})
print("attribution_py frozen")
```

Run: `.venv/Scripts/python.exe docs/phase9a/r1/attribution.py`
Expected: `attribution written: 36 disagreements`（attribution.py 内部 verify_frozen 预检通过）。

随后立即冻结归因结果（原子写）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
pm.freeze(P9R1 / "manifest_v5.json", {"attribution_json": (P9R1 / "attribution.json", "json_canonical")})
print("attribution_json frozen")
```

- [ ] **Step 6: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestR1ManifestInit -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/r1/manifest_v5.json docs/phase9a/r1/attribution.py docs/phase9a/r1/attribution.json tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "feat(phase9a-r1): R1 manifest config_frozen + attribution evidence入库 (freeze-before-use)"
```

---

## Task 1: 验证集样本 + 盲评 packet 冻结（在 v3 规则与任何 v3 label 前）

**Files:**
- Create: `docs/phase9a/r1/generate_validation_sample.py`
- Create: `docs/phase9a/r1/qc_sample_list_v2.json`
- Create: `docs/phase9a/r1/qc_review_packet_v2.jsonl`
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 写失败测试（含开发集隔离负向）**

```python
class TestValidationSample:
    def test_sample_frozen_before_v3(self):
        sample = _load_json(P9R1 / "qc_sample_list_v2.json")
        assert sample["sample_size"] == 61
        assert sample["seed"] == 20260814
        assert len(sample["sample_list"]) == 61
        items = {s["item_id"] for s in sample["sample_list"]}
        assert len(items) == 37
        # 开发集隔离（tuple pair key，非字符串）
        dev_keys = {(r["item_id"], r["canonical_key"]) for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
        for s in sample["sample_list"]:
            assert (s["item_id"], s["canonical_key"]) not in dev_keys
        keys = [(s["item_id"], s["canonical_key"]) for s in sample["sample_list"]]
        assert len(keys) == len(set(keys))

    def test_dev_set_isolation_negative(self):
        # 负向：故意注入开发集 pair 必须被检测
        dev_keys = {(r["item_id"], r["canonical_key"]) for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
        sample = _load_json(P9R1 / "qc_sample_list_v2.json")
        injected = next(iter(dev_keys))
        assert injected in dev_keys  # 注入成功
        # 若样本含开发集 pair，隔离断言必须失败
        sample_keys = {(s["item_id"], s["canonical_key"]) for s in sample["sample_list"]}
        assert injected not in sample_keys  # 实际样本无泄漏

    def test_review_packet_frozen(self):
        # 盲评 packet：含 item_id/canonical_key/item_description/document_text/source_location；不含 label/reason/开发集标签/归因结论
        packet = [json.loads(l) for l in (P9R1 / "qc_review_packet_v2.jsonl").open(encoding="utf-8") if l.strip()]
        assert len(packet) == 61
        for p in packet:
            assert {"item_id", "canonical_key", "item_description", "document_text", "source_location"} <= set(p)
            assert "silver_label" not in p and "reason" not in p and "human_label" not in p
            assert p["item_description"]  # 非空（从 required_knowledge/knowledge_audit 构造）
            assert len(p["document_text"]) > 0  # 完整文本（非截断）
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestValidationSample -q`
Expected: FAIL。

- [ ] **Step 3: 实现抽样 + packet 生成脚本**

写 `docs/phase9a/r1/generate_validation_sample.py`：
```python
"""Phase 9A-R1 验证集抽样 + 盲评 packet 生成（确定性无放回，61 条，37 item 覆盖）。"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
sys.path.insert(0, str(P9))
import retriever as rt


def pair_key(row):
    return (row["item_id"], row["canonical_key"])


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    # P0 修订：脚本内部 verify_frozen，防绕过门禁
    pm.verify_frozen(P9R1 / "manifest_v5.json", ["generate_validation_sample_py", "upstream_manifest_v4"], required_stage="config_frozen")
    # 通过前代 sealed manifest 验证上游依赖
    pm.verify_frozen(P9 / "manifest_v4.json", ["silver_relevance_judgment", "qc_human_review", "item_query_map", "retriever_py"], required_stage="sealed")
    all_pairs = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
    dev_keys = {(r["item_id"], r["canonical_key"]) for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
    remaining = [r for r in all_pairs if pair_key(r) not in dev_keys]
    if len(remaining) < 61:
        sys.exit(f"BLOCKED_INPUT_DRIFT: remaining candidates {len(remaining)} < 61")
    pairs_by_item: dict[str, list] = {}
    for r in remaining:
        pairs_by_item.setdefault(r["item_id"], []).append(r)
    if len(pairs_by_item) < 37:
        sys.exit(f"BLOCKED_INPUT_DRIFT: remaining items {len(pairs_by_item)} < 37")
    rng = random.Random(20260814)
    first = [rng.choice(sorted(pairs_by_item[item_id], key=pair_key)) for item_id in sorted(pairs_by_item)]
    selected_keys = {pair_key(row) for row in first}
    remaining_pool = sorted((row for row in remaining if pair_key(row) not in selected_keys), key=pair_key)
    extra = rng.sample(remaining_pool, 24)
    sample = first + extra
    assert len(sample) == 61
    assert len({row["item_id"] for row in sample}) == 37
    assert len({pair_key(row) for row in sample}) == 61
    assert all(pair_key(row) not in dev_keys for row in sample)
    # 样本列表
    payload = {
        "schema_version": "1.0",
        "seed": 20260814,
        "sample_size": 61,
        "pool_size": len(remaining),
        "sample_list": [{"item_id": s["item_id"], "canonical_key": s["canonical_key"]} for s in sample],
    }
    (P9R1 / "qc_sample_list_v2.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    # 盲评 packet（不含 label/reason/开发集标签/归因结论；item_description 从 required_knowledge/knowledge_audit 构造）
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    # 从 Phase 8 冻结数据构造 item 需求描述（knowledge_audit 的 prompt_evidence.required_term + required_knowledge 的 query_specs）
    rk = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "required_knowledge.jsonl").open(encoding="utf-8") if l.strip())}
    audit = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "knowledge_audit.jsonl").open(encoding="utf-8") if l.strip())}
    item_desc = {}
    for item in item_map["items"]:
        case_id = item["case_id"]
        item_id = item["item_id"]
        # 从 knowledge_audit 取 required_term（prompt_evidence 字段，P0 修订：非顶层）
        req_term = ""
        if case_id in audit:
            for audit_item in audit[case_id]["items"]:
                if audit_item["item_id"] == item_id:
                    req_term = audit_item.get("prompt_evidence", {}).get("required_term", "")
                    break
        # 从 required_knowledge 取 query_specs（P0 修订：非 knowledge_audit）
        query_terms = []
        if case_id in rk:
            for rk_item in rk[case_id]["items"]:
                if rk_item["item_id"] == item_id:
                    for qs in rk_item.get("query_specs", []):
                        args = qs.get("args", {})
                        term = args.get("query") or args.get("name") or args.get("combo_name") or ""
                        if term:
                            query_terms.append(term)
                    break
        item_desc[item_id] = f"required_term={req_term}; query_terms={','.join(query_terms[:3])}"
    packet_lines = []
    for s in sample:
        doc = rt.doc_text(s["canonical_key"])
        packet_lines.append({
            "item_id": s["item_id"],
            "canonical_key": s["canonical_key"],
            "item_description": item_desc.get(s["item_id"], ""),
            "document_text": doc.get("text", ""),  # 完整文本（非截断），与 silver 规则消费一致
            "source_location": s["canonical_key"],
        })
    tmp_packet = P9R1 / "qc_review_packet_v2.jsonl.tmp"
    with tmp_packet.open("w", encoding="utf-8", newline="\n") as f:
        for p in packet_lines:
            f.write(json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    import os
    os.replace(tmp_packet, P9R1 / "qc_review_packet_v2.jsonl")
    print(f"validation sample + review packet written: {len(sample)} samples, 37 items")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 generator（freeze-before-use）→ 运行生成 sample + packet**

先冻结代码（manifest_v5 config_frozen 阶段追加）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
pm.freeze(P9R1 / "manifest_v5.json", {"generate_validation_sample_py": (P9R1 / "generate_validation_sample.py", "git_canonical_lf")})
print("generate_validation_sample_py frozen")
```

Run: `.venv/Scripts/python.exe docs/phase9a/r1/generate_validation_sample.py`
Expected: `validation sample + review packet written: 61 samples, 37 items`（verify_frozen 预检通过）。

随后立即冻结产物：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
pm.freeze(P9R1 / "manifest_v5.json", {
    "qc_sample_list_v2": (P9R1 / "qc_sample_list_v2.json", "json_canonical"),
    "qc_review_packet_v2": (P9R1 / "qc_review_packet_v2.jsonl", "jsonl_canonical"),
})
print("sample + packet frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestValidationSample -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add -- docs/phase9a/r1/manifest_v5.json docs/phase9a/r1/generate_validation_sample.py docs/phase9a/r1/qc_sample_list_v2.json docs/phase9a/r1/qc_review_packet_v2.jsonl tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "feat(phase9a-r1): validation sample + blind review packet frozen before v3 rule"
```

---

## Task 2: 校准规则冻结（code_frozen）+ 校准 judgment 生成

**Files:**
- Create: `docs/phase9a/r1/silver_judge_v3.py`
- Create: `docs/phase9a/r1/silver_relevance_judgment_v3.jsonl`
- Create: `docs/phase9a/r1/silver_judgment_summary_v3.json`
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 写失败测试（含逐 pair 差异断言）**

```python
class TestCalibratedJudgment:
    def test_v3_rule_frozen(self):
        j = _load_module("silver_judge_v3", "docs/phase9a/r1/silver_judge_v3.py")
        syn = {"synonyms": {"结婚": ["婚期", "成婚"]}}
        # query 无 category → relevant（不降级）
        result = j.label_pair("结婚", None, {"text": "婚姻美满", "category": ""}, syn)
        assert result["label"] == "relevant"
        # query 有 category 且匹配 → relevant
        result2 = j.label_pair("结婚", "婚姻", {"text": "婚姻美满", "category": "婚姻"}, syn)
        assert result2["label"] == "relevant"
        # query 有 category 但不匹配 → partial
        result3 = j.label_pair("结婚", "事业", {"text": "婚姻美满", "category": "婚姻"}, syn)
        assert result3["label"] == "partially_relevant"

    def test_v3_judgment_generated(self):
        rows = [json.loads(l) for l in (P9R1 / "silver_relevance_judgment_v3.jsonl").open(encoding="utf-8") if l.strip()]
        assert len(rows) == 673

    def test_v2_v3_pair_diff_only_allowed_transition(self):
        # 逐 pair 比较：只有冻结规则允许的 partial→relevant 可以变化，其余 label 必须一致
        v2 = {r["item_id"] + "|" + r["canonical_key"]: r["label"] for r in (json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip())}
        v3 = {r["item_id"] + "|" + r["canonical_key"]: r["label"] for r in (json.loads(l) for l in (P9R1 / "silver_relevance_judgment_v3.jsonl").open(encoding="utf-8") if l.strip())}
        assert set(v2.keys()) == set(v3.keys())
        for key in v2:
            if v2[key] != v3[key]:
                assert v2[key] == "partially_relevant" and v3[key] == "relevant", f"unexpected transition {v2[key]} -> {v3[key]} for {key}"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestCalibratedJudgment -q`
Expected: FAIL。

- [ ] **Step 3: 实现 silver_judge_v3.py（版本化新文件）**

```python
"""Phase 9A-R1 silver relevance judgment v3：校准 cat_ok 边界（query 无 category 时不降级）。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "retrieval"))
import retriever as rt

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"

RULE_SOURCE = "silver_rule_v3: synonym-cooccurrence AND category-consistency(query-arg, optional-when-absent) AND canonical-traceability"


def label_pair(term: str, query_category: str | None, doc: dict, synonym_table: dict) -> dict:
    """v3 校准：query 无 category 参数时 cat_ok=True（不降级）；有 category 时才校验匹配。"""
    syns = [term] + synonym_table["synonyms"].get(term, [])
    text = "".join(doc.get("text", "").split())
    syn_hit = any(s and s in text for s in syns)
    if query_category is None or query_category == "":
        cat_ok = True  # v3 修订：无 category 约束时不降级
    else:
        cat_ok = str(doc.get("category") or "") == str(query_category)
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
    import strategy_store as ss
    # 显式校验前代 sealed 状态（P0 修订：manifest_v4 是 sealed，非 code_frozen）
    pm.verify_frozen(P9 / "manifest_v4.json", ["retriever_py", "synonym_table", "query_set_frozen", "item_query_map",
                                               "strategy_store_py", "strategy_outputs"], required_stage="sealed")
    # 校验 R1 manifest 已达 code_frozen（silver_judge_v3_py 已冻结）
    pm.verify_frozen(P9R1 / "manifest_v5.json", ["silver_judge_v3_py"], required_stage="code_frozen")
    frozen = ss.load_frozen_strategy_hits(P9 / "strategy_outputs.jsonl")
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    syn = json.loads((P9 / "synonym_table.json").read_text(encoding="utf-8"))
    RANK = {"relevant": 3, "partially_relevant": 2, "irrelevant": 1, "uncertain": 0}
    agg: dict[tuple, dict] = {}
    for item in item_map["items"]:
        for q in item["queries"]:
            args = q["args"]
            term = (args.get("query") or args.get("name") or args.get("combo_name")
                    or (args.get("gan", "") + args.get("zhi", "")) or args.get("gan_or_zhi", ""))
            qcat = args.get("category")
            for hits in frozen.get(q["query_id"], {}).values():
                for h in hits:
                    key = (item["item_id"], h["canonical_key"])
                    doc = rt.doc_text(h["canonical_key"])
                    j = label_pair(term, qcat, doc, syn)
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
    # 原子写产物
    tmp_judgment = P9R1 / "silver_relevance_judgment_v3.jsonl.tmp"
    with tmp_judgment.open("w", encoding="utf-8", newline="\n") as f:
        for r in pairs:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp_judgment, P9R1 / "silver_relevance_judgment_v3.jsonl")
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
    tmp_summary = P9R1 / "silver_judgment_summary_v3.json.tmp"
    tmp_summary.write_text(json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp_summary, P9R1 / "silver_judgment_summary_v3.json")
    print(f"v3 judgment written: {len(pairs)} pairs; summary written")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 冻结 silver_judge_v3_py（code_frozen）→ 运行生成 judgment**

冻结代码（manifest_v5 从 config_frozen → code_frozen）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
m = P9R1 / "manifest_v5.json"
pm.freeze(m, {"silver_judge_v3_py": (P9R1 / "silver_judge_v3.py", "git_canonical_lf")})
pm.set_stage(m, "code_frozen")
print("silver_judge_v3_py frozen; stage=code_frozen")
```

Run: `.venv/Scripts/python.exe docs/phase9a/r1/silver_judge_v3.py`
Expected: `v3 judgment written: 673 pairs; summary written`（verify_frozen 预检通过）。

- [ ] **Step 5: 冻结 judgment + summary → 测试转绿**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
pm.freeze(P9R1 / "manifest_v5.json", {
    "silver_relevance_judgment_v3": (P9R1 / "silver_relevance_judgment_v3.jsonl", "jsonl_canonical"),
    "silver_judgment_summary_v3": (P9R1 / "silver_judgment_summary_v3.json", "json_canonical"),
})
print("judgment + summary frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestCalibratedJudgment -q`
Expected: PASS。

- [ ] **Step 6: Commit**

```powershell
git add -- docs/phase9a/r1/manifest_v5.json docs/phase9a/r1/silver_judge_v3.py docs/phase9a/r1/silver_relevance_judgment_v3.jsonl docs/phase9a/r1/silver_judgment_summary_v3.json tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "feat(phase9a-r1): v3 calibrated judgment (cat_ok optional when query has no category)"
```

---

## Task 3: 人工 QC 复核（验证集盲评）

**Files:**
- Create: `docs/phase9a/r1/qc_human_review_v2.jsonl`（零字节模板）
- Create: `docs/phase9a/r1/qc_human_review_schema_v2.json`（schema 说明）
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 写失败测试（验证新增契约，非已有行为）**

```python
class TestQcStateMachineV2:
    def test_r1_template_and_schema_exist(self):
        # R1 模板/schema/盲评 packet 必须存在（新增契约）
        assert (P9R1 / "qc_human_review_v2.jsonl").exists()
        assert (P9R1 / "qc_human_review_schema_v2.json").exists()
        assert (P9R1 / "qc_review_packet_v2.jsonl").exists()

    def test_packet_no_label_leak(self):
        # packet 不含任何 label/reason/开发集标签/归因结论
        packet = [json.loads(l) for l in (P9R1 / "qc_review_packet_v2.jsonl").open(encoding="utf-8") if l.strip()]
        for p in packet:
            assert "silver_label" not in p and "reason" not in p and "human_label" not in p
            assert "note" not in p  # 开发集标签字段

    def test_packet_matches_sample(self):
        # packet 与 sample 61 条一一对应
        packet = [json.loads(l) for l in (P9R1 / "qc_review_packet_v2.jsonl").open(encoding="utf-8") if l.strip()]
        sample = _load_json(P9R1 / "qc_sample_list_v2.json")
        packet_keys = {(p["item_id"], p["canonical_key"]) for p in packet}
        sample_keys = {(s["item_id"], s["canonical_key"]) for s in sample["sample_list"]}
        assert packet_keys == sample_keys

    def test_review_coverage_fail_closed(self):
        g = _load_module("qc_gate", "docs/phase9a/retrieval/qc_gate.py")
        sample = [{"item_id": "a", "canonical_key": "kb:gejue:1"}]
        reviews = [{"item_id": "a", "canonical_key": "kb:gejue:2", "human_label": "relevant"}]
        try:
            g.validate_review_coverage(sample, reviews)
            raised = False
        except SystemExit:
            raised = True
        assert raised
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestQcStateMachineV2 -q`
Expected: FAIL（qc_human_review_v2.jsonl / qc_human_review_schema_v2.json 不存在）。

- [ ] **Step 3: 落盘模板 + schema**

`qc_human_review_v2.jsonl` 为零字节文件；`qc_human_review_schema_v2.json`：
```json
{"schema_version": "1.0", "file": "qc_human_review_v2.jsonl", "line_fields": ["item_id", "canonical_key", "human_label", "note"], "human_label_enum": ["relevant", "partially_relevant", "irrelevant", "uncertain"], "note_required": true, "rules": ["human_label 必填且属于枚举", "note 必填非空", "pair 与 qc_sample_list_v2 一一对应（无缺失/重复/额外）", "reviewer 盲法：不得看到 silver label/开发集标签/归因结论"]}
```

- [ ] **Step 4: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestQcStateMachineV2 -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/r1/qc_human_review_v2.jsonl docs/phase9a/r1/qc_human_review_schema_v2.json tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "feat(phase9a-r1): QC v2 template + schema (blind review packet as sole input)"
```

**⏸ 暂停点（人工）：** 人类对照 `qc_review_packet_v2.jsonl`（唯一输入，不含 label/reason）逐条填写 `qc_human_review_v2.jsonl`（human_label ∈ {relevant, partially_relevant, irrelevant, uncertain}，note 必填；**盲法：不得看到 silver label/开发集标签/归因结论**）。**未完成前不得执行 Task 4 的终态判定**。

**填写完成后（run_calibration_eval 前）首次冻结 qc_human_review_v2（校验通过后才冻结）：**
```python
import json, sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
import qc_gate as qc
P9R1 = Path("docs/phase9a/r1")
reviews = qc.load_human_review(P9R1 / "qc_human_review_v2.jsonl")
qc.validate_review_coverage(json.loads((P9R1 / "qc_sample_list_v2.json").read_text(encoding="utf-8"))["sample_list"], reviews)
qc.validate_human_review_schema(reviews)
pm.freeze(P9R1 / "manifest_v5.json", {"qc_human_review_v2": (P9R1 / "qc_human_review_v2.jsonl", "jsonl_canonical")})
print("qc_human_review_v2 frozen after full human QC")
```

---

## Task 4: 一次性终态发布（finalize_r1 staging+RECEIPT）+ 产物封存（sealed）

**Files:**
- Create: `docs/phase9a/r1/finalize_r1.py`（单一终态发布脚本，seal 前创建并冻结）
- Create: `docs/phase9a/r1/reconcile_r1.py`（R1 最终对账，seal 前创建并冻结）
- Create: `docs/phase9a/r1/qc_result_v2.json`
- Create: `docs/phase9a/r1/calibration_fingerprint.json`
- Create: `docs/phase9a/r1/CLOSURE.md`
- Create: `docs/phase9a/r1/RECEIPT_r1.json`（完成标记，绑定 sealed manifest SHA，不加入 manifest）
- Modify: `docs/phase9a/r1/manifest_v5.json`（sealed）
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 写失败测试（全部真实调用 finalize_r1.py）**

```python
class TestTerminalV2:
    def test_effective_disagreement_gate(self):
        result = _load_json(P9R1 / "qc_result_v2.json")
        assert "effective_disagreement" in result
        assert result["effective_disagreement"] == result["disagreement_count"] + result["uncertain_count"]
        assert result["verdict"] in {"SILVER_LABEL_CALIBRATED", "SILVER_LABEL_NOT_CALIBRATED"}
        if result["effective_disagreement"] <= 6:
            assert result["verdict"] == "SILVER_LABEL_CALIBRATED"
        else:
            assert result["verdict"] == "SILVER_LABEL_NOT_CALIBRATED"

    def test_uncertain_not_double_counted(self):
        # 单条 uncertain 贡献恰好 1，不是 2
        fin = _load_module("finalize_r1", "docs/phase9a/r1/finalize_r1.py")
        reviews = [{"item_id": "a", "canonical_key": "kb:gejue:1", "human_label": "uncertain", "note": "x"}]
        silver = {("a", "kb:gejue:1"): "relevant"}
        n_diff, n_uncertain = fin._count_disagreement(reviews, silver)
        assert n_diff == 0 and n_uncertain == 1  # uncertain 不计入 diff，只计 1 次

    def test_calibration_fingerprint(self):
        fp = _load_json(P9R1 / "calibration_fingerprint.json")
        assert fp["components"] and fp["sha256"]
        names = {c["logical_name"] for c in fp["components"]}
        assert {"silver_judge_v3_py", "silver_relevance_judgment_v3", "silver_judgment_summary_v3", "qc_sample_list_v2", "attribution_json"} <= names

    def test_treatment_fingerprint_unchanged(self):
        # 原 treatment_fingerprint 字节不变（双 SHA 口径分离：文件 canonical SHA vs 内部组件摘要）
        orig = _load_json(P9 / "treatment_fingerprint.json")
        m4 = _load_json(P9 / "manifest_v4.json")
        expected_file_sha = m4["entries"]["treatment_fingerprint"]["sha256"]
        actual_file_sha = hashlib.sha256(json.dumps(orig, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b"\n").hexdigest()
        assert actual_file_sha == expected_file_sha  # 文件字节不变
        assert orig["sha256"]  # 内部摘要存在（与文件 SHA 语义不同，不混用）

    def test_manifest_v5_sealed(self):
        m = _load_json(P9R1 / "manifest_v5.json")
        assert m["stage"] == "sealed"
        assert "closure" in m["entries"]
        assert "upstream_manifest_v4" in m["entries"]

    def test_receipt_binds_sealed_manifest(self):
        # RECEIPT 绑定 sealed manifest SHA + 产物元数据，不加入 manifest
        receipt = _load_json(P9R1 / "RECEIPT_r1.json")
        m = _load_json(P9R1 / "manifest_v5.json")
        assert receipt["manifest_sha256"] == hashlib.sha256(json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b"\n").hexdigest()
        assert "receipt_r1" not in m["entries"]  # RECEIPT 不加入 manifest（避免循环）
        # P0 修订：RECEIPT artifact 集合精确相等（防空集合/缺项通过）
        assert set(receipt["artifacts"]) == {"qc_result_v2.json", "calibration_fingerprint.json", "CLOSURE.md"}
        # RECEIPT artifact 集合/SHA/size/strategy/verdict
        for name, meta in receipt["artifacts"].items():
            raw = (P9R1 / name).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == meta["sha256"]
            assert len(raw) == meta["size"] and meta["strategy"] == "raw_bytes"

    def test_no_overwrite_on_rerun(self):
        # 正式终态产物已存在时 finalize_r1 必须 fail-closed
        proc = subprocess.run([sys.executable, str(P9R1 / "finalize_r1.py")], capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode != 0 and "already exists" in (proc.stdout + proc.stderr)

    def test_reconcile_r1_exit_zero(self):
        # R1 最终对账入口：sealed 后 reconcile_r1.py 必须 exit 0
        proc = subprocess.run([sys.executable, str(P9R1 / "reconcile_r1.py")], capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "FAIL" not in proc.stdout


class TestFinalizeResumeProtocol:
    """P0 修订：4 个生产路径测试（镜像从 code_frozen 输入构造，不依赖正式终态产物，可在正式发布前运行）。"""

    def _make_r1_mirror(self, tmp_path):
        """从 code_frozen 输入构造镜像：复制冻结输入 + 代码，不含正式终态产物（此时尚未生成）。
        P0 修订：phase9a_manifest.py 位于 P9（copytree 已覆盖），此处只额外复制 p8_freeze.py。"""
        import shutil
        root = tmp_path / "repo"
        mirror_r1 = root / "docs" / "phase9a" / "r1"
        mirror_r1.mkdir(parents=True)
        # 冻结输入 + 代码（manifest_v5 此时仍为 code_frozen；正式终态产物尚不存在，不复制）
        for name in ("manifest_v5.json", "finalize_r1.py", "reconcile_r1.py", "silver_relevance_judgment_v3.jsonl",
                     "silver_judgment_summary_v3.json", "qc_sample_list_v2.json", "qc_human_review_v2.jsonl",
                     "silver_judge_v3.py", "attribution.py", "attribution.json", "generate_validation_sample.py"):
            shutil.copy(P9R1 / name, mirror_r1 / name)
        # P9 copytree（qc_gate 等依赖，已含 phase9a_manifest.py）
        shutil.copytree(P9, root / "docs" / "phase9a" / "retrieval")
        (root / "docs" / "phase8" / "marriage-capability").mkdir(parents=True)
        shutil.copy(P8 / "p8_freeze.py", root / "docs" / "phase8" / "marriage-capability" / "p8_freeze.py")
        return root

    def _run_finalize(self, root):
        mirror_r1 = root / "docs" / "phase9a" / "r1"
        return subprocess.run([sys.executable, str(mirror_r1 / "finalize_r1.py")], capture_output=True, text=True, encoding="utf-8", cwd=root)

    def _reset_manifest_to_code_frozen(self, mirror_r1):
        """镜像 manifest 重置为 code_frozen（模拟未 seal 状态）。"""
        m = mirror_r1 / "manifest_v5.json"
        data = json.loads(m.read_text(encoding="utf-8"))
        data["stage"] = "code_frozen"
        m.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    def test_resume_partial_same_products_completes(self, tmp_path):
        # P0 修订：模拟真实窗口——发布一项后、freeze 前崩溃（fresh 镜像不含三项终态 manifest 条目）
        # control 镜像：完整运行一次，取得规范产物字节
        control_root = self._make_r1_mirror(tmp_path / "control")
        assert self._run_finalize(control_root).returncode == 0
        control_r1 = control_root / "docs" / "phase9a" / "r1"
        closure_bytes = (control_r1 / "CLOSURE.md").read_bytes()
        # fresh 镜像：code_frozen，不含三项终态 manifest 条目（原始 manifest 尚未冻结它们）
        fresh_root = self._make_r1_mirror(tmp_path / "fresh")
        fresh_r1 = fresh_root / "docs" / "phase9a" / "r1"
        # 只从 control 复制一项已发布产物（模拟发布一项后崩溃）
        (fresh_r1 / "CLOSURE.md").write_bytes(closure_bytes)
        proc = self._run_finalize(fresh_root)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert (fresh_r1 / "CLOSURE.md").read_bytes() == closure_bytes  # 既有产物字节未变
        assert (fresh_r1 / "qc_result_v2.json").exists() and (fresh_r1 / "calibration_fingerprint.json").exists()  # 其余产物生成
        assert json.loads((fresh_r1 / "manifest_v5.json").read_text(encoding="utf-8"))["stage"] == "sealed"  # manifest sealed
        assert (fresh_r1 / "RECEIPT_r1.json").exists()  # RECEIPT 发布

    def test_resume_byte_mismatch_rejected(self, tmp_path):
        # P0 修订：fresh 镜像 + 磁盘上留下损坏的已发布产物（真实窗口：发布后字节损坏）→ 拒绝
        control_root = self._make_r1_mirror(tmp_path / "control")
        assert self._run_finalize(control_root).returncode == 0
        control_r1 = control_root / "docs" / "phase9a" / "r1"
        corrupted = (control_r1 / "qc_result_v2.json").read_bytes() + b"tampered"
        fresh_root = self._make_r1_mirror(tmp_path / "fresh")
        fresh_r1 = fresh_root / "docs" / "phase9a" / "r1"
        (fresh_r1 / "qc_result_v2.json").write_bytes(corrupted)  # 字节不一致的已发布产物
        proc = self._run_finalize(fresh_root)
        assert proc.returncode != 0 and "byte mismatch" in (proc.stdout + proc.stderr)

    def test_sealed_no_receipt_republishes(self, tmp_path):
        # sealed + 无 RECEIPT：校验后补发
        root = self._make_r1_mirror(tmp_path)
        mirror_r1 = root / "docs" / "phase9a" / "r1"
        assert self._run_finalize(root).returncode == 0
        (mirror_r1 / "RECEIPT_r1.json").unlink()  # 删除 RECEIPT（manifest 仍 sealed）
        proc = self._run_finalize(root)
        assert proc.returncode == 0 and (mirror_r1 / "RECEIPT_r1.json").exists()

    def test_code_frozen_receipt_exists_rejected(self, tmp_path):
        # code_frozen + RECEIPT 已存在：拒绝且不得覆盖
        root = self._make_r1_mirror(tmp_path)
        mirror_r1 = root / "docs" / "phase9a" / "r1"
        assert self._run_finalize(root).returncode == 0
        self._reset_manifest_to_code_frozen(mirror_r1)  # 保留 RECEIPT，重置 stage
        receipt_before = (mirror_r1 / "RECEIPT_r1.json").read_bytes()
        proc = self._run_finalize(root)
        assert proc.returncode != 0 and "already exists" in (proc.stdout + proc.stderr)
        assert (mirror_r1 / "RECEIPT_r1.json").read_bytes() == receipt_before  # RECEIPT 未被覆盖
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestTerminalV2 -q`
Expected: FAIL。

- [ ] **Step 3: 实现 finalize_r1.py（单一终态发布，RECEIPT 绑定 sealed manifest 最后发布）**

```python
"""Phase 9A-R1 终态发布：单一 finalize 脚本完成终态计算 + fingerprint + closure + 发布 + seal + RECEIPT。
RECEIPT 在 seal manifest 后发布（绑定 sealed manifest SHA），不加入 manifest（避免循环）。
受控 resume：manifest 已 sealed 但 RECEIPT 未发布时，校验产物后补发 RECEIPT。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
STAGING = P9R1 / ".staging_r1"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
import phase9a_manifest as pm  # 仅顶层导入 manifest helper；qc_gate 延迟导入（P0 修订：先验证后导入）


def _count_disagreement(reviews, silver):
    n_uncertain = sum(1 for r in reviews if r["human_label"] == "uncertain")
    n_diff = sum(1 for r in reviews
                 if r["human_label"] != "uncertain" and r["human_label"] != silver[(r["item_id"], r["canonical_key"])])
    return n_diff, n_uncertain


def _atomic_json(path, payload):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def _publish_receipt(m5, verdict):
    """RECEIPT 绑定 sealed manifest SHA，最后原子发布（不加入 manifest）。"""
    manifest_sha = pm.STRATEGY_FN["json_canonical"](m5)
    receipt_artifacts = {}
    for name in ("qc_result_v2.json", "calibration_fingerprint.json", "CLOSURE.md"):
        raw = (P9R1 / name).read_bytes()
        receipt_artifacts[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "strategy": "raw_bytes", "size": len(raw)}
    receipt = {"schema_version": "1.0", "verdict": verdict, "artifacts": receipt_artifacts,
               "manifest_sha256": manifest_sha, "note": "Phase 9A-R1 finalize receipt"}
    STAGING.mkdir(parents=True, exist_ok=True)
    _atomic_json(STAGING / "RECEIPT_r1.json", receipt)
    os.replace(STAGING / "RECEIPT_r1.json", P9R1 / "RECEIPT_r1.json")


def main() -> None:
    m5 = P9R1 / "manifest_v5.json"
    manifest = json.loads(m5.read_text(encoding="utf-8")) if m5.exists() else None
    # P0 修订：先验证 upstream + qc_gate 冻结 SHA，然后才延迟导入 qc_gate（防漂移代码执行）
    entry = manifest["entries"]["upstream_manifest_v4"]
    actual_upstream = pm.STRATEGY_FN[entry["strategy"]](P9 / "manifest_v4.json")
    if actual_upstream != entry["sha256"]:
        sys.exit("FAIL: upstream_manifest_v4 SHA drift")
    # P0 修订：真实 manifest_v4 不含 phase9a_manifest_py，helper 从 R1 manifest_v5 验证
    # P0 修订：verify_frozen 是精确 stage 相等，先读 stage 再按实际 stage 验证（否则 sealed 分支永远不可达）
    stage = manifest.get("stage")
    if stage not in {"code_frozen", "sealed"}:
        sys.exit(f"FAIL: unexpected manifest_v5 stage {stage}")
    pm.verify_frozen(m5, ["phase9a_manifest_py"], required_stage=stage)
    pm.verify_frozen(P9 / "manifest_v4.json", ["qc_gate_py", "qc_gate_py_v2", "retriever_py"], required_stage="sealed")
    import qc_gate as qc  # 延迟导入（验证后）
    # stage == sealed：受控 resume，manifest 已 sealed 但 RECEIPT 未发布 → 校验产物后补发 RECEIPT
    if stage == "sealed":
        if (P9R1 / "RECEIPT_r1.json").exists():
            sys.exit("FAIL: RECEIPT_r1.json already exists - one-shot violated")
        entry_map = {"qc_result_v2.json": "qc_result_v2", "calibration_fingerprint.json": "calibration_fingerprint", "CLOSURE.md": "closure"}
        for name, entry_name in entry_map.items():
            entry = manifest["entries"][entry_name]
            actual = pm.STRATEGY_FN[entry["strategy"]](P9R1 / name)
            if actual != entry["sha256"]:
                sys.exit(f"FAIL: {name} SHA mismatch with manifest - manual intervention required")
        verdict = json.loads((P9R1 / "qc_result_v2.json").read_text(encoding="utf-8"))["verdict"]
        _publish_receipt(m5, verdict)
        print(f"finalize_r1: RECEIPT补发完成（manifest 已 sealed，verdict={verdict}）")
        return
    # 正常流程：stage == code_frozen
    # P0 修订：正常分支先拒绝异常 RECEIPT（不得覆盖）
    if (P9R1 / "RECEIPT_r1.json").exists():
        sys.exit("FAIL: RECEIPT_r1.json already exists but manifest not sealed - one-shot violated")
    pm.verify_frozen(m5, ["silver_relevance_judgment_v3", "qc_sample_list_v2", "qc_human_review_v2", "finalize_r1_py", "reconcile_r1_py"], required_stage="code_frozen")
    state = qc.qc_state(P9R1 / "qc_human_review_v2.jsonl", P9R1 / "qc_sample_list_v2.json")
    if state != "REVIEWED":
        sys.exit(f"HUMAN_QC_REQUIRED: state={state}")
    reviews = qc.load_human_review(P9R1 / "qc_human_review_v2.jsonl")
    qc.validate_review_coverage(json.loads((P9R1 / "qc_sample_list_v2.json").read_text(encoding="utf-8"))["sample_list"], reviews)
    qc.validate_human_review_schema(reviews)
    silver = {(r["item_id"], r["canonical_key"]): r["label"]
              for r in (json.loads(l) for l in (P9R1 / "silver_relevance_judgment_v3.jsonl").open(encoding="utf-8") if l.strip())}
    n_diff, n_uncertain = _count_disagreement(reviews, silver)
    effective = n_diff + n_uncertain
    verdict = "SILVER_LABEL_CALIBRATED" if effective <= 6 else "SILVER_LABEL_NOT_CALIBRATED"
    qc_result = {"schema_version": "1.0", "verdict": verdict, "disagreement_count": n_diff,
                 "uncertain_count": n_uncertain, "effective_disagreement": effective, "max_allowed": 6,
                 "n_reviewed": len(reviews), "note": "effective_disagreement = disagreement + uncertain；≤6 才 CALIBRATED"}
    # 生成三项数据产物到 staging
    staging = STAGING
    staging.mkdir(parents=True, exist_ok=True)
    _atomic_json(staging / "qc_result_v2.json", qc_result)
    manifest = json.loads(m5.read_text(encoding="utf-8"))
    components, digest = [], hashlib.sha256()
    for name in ("silver_judge_v3_py", "silver_relevance_judgment_v3", "silver_judgment_summary_v3", "qc_sample_list_v2", "attribution_json"):
        entry = manifest["entries"][name]
        components.append({"logical_name": name, "path": entry["path"], "strategy": entry["strategy"], "sha256": entry["sha256"]})
        digest.update(entry["sha256"].encode() + b"\0")
    fp = {"schema_version": "1.0", "components": components, "sha256": digest.hexdigest(),
          "note": "Phase 9A-R1 calibration fingerprint；treatment fingerprint 不变（retriever 未改）"}
    _atomic_json(staging / "calibration_fingerprint.json", fp)
    closure = (
        f"# Phase 9A-R1 Closure：silver relevance 标签校准（{verdict}）\n\n"
        f"verdict: {verdict}\n"
        f"effective_disagreement: {effective}/61\n"
        f"disagreement_count: {n_diff}\n"
        f"uncertain_count: {n_uncertain}\n"
        f"max_allowed: 6\n"
        f"sample_size: 61\n"
        f"item_coverage: 37\n"
        f"seed: 20260814\n\n"
        f"校准规则变更点：cat_ok 可选（query 无 category 时不降级）。\n"
        f"后续衔接：R2（候选覆盖）。\n"
    )
    (staging / "CLOSURE.md").write_text(closure, encoding="utf-8", newline="\n")
    # 发布三项数据产物（逐项存在则字节一致校验，防覆盖）
    for name in ("qc_result_v2.json", "calibration_fingerprint.json", "CLOSURE.md"):
        target = P9R1 / name
        if target.exists():
            if target.read_bytes() != (staging / name).read_bytes():
                sys.exit(f"FAIL: existing {name} byte mismatch - manual intervention required")
            continue
        os.replace(staging / name, target)
    # 冻结数据产物 + seal manifest
    pm.freeze(m5, {
        "qc_result_v2": (P9R1 / "qc_result_v2.json", "json_canonical"),
        "calibration_fingerprint": (P9R1 / "calibration_fingerprint.json", "json_canonical"),
        "closure": (P9R1 / "CLOSURE.md", "git_canonical_lf"),
    })
    pm.set_stage(m5, "sealed")
    # RECEIPT 绑定 sealed manifest SHA，最后原子发布（不加入 manifest）
    _publish_receipt(m5, verdict)
    print(f"finalize_r1: verdict={verdict}, effective_disagreement={effective}/61, manifest_v5 sealed, RECEIPT published")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 实现 reconcile_r1.py（R1 最终对账，先实现后冻结，P0 修订）**

reconcile_r1.py（sealed 后执行，验证 sealed manifest + RECEIPT + 产物 + fingerprint；treatment fingerprint 路径从 manifest 条目解析）：
```python
"""Phase 9A-R1 原子对账：manifest_v5 expected SHA == 磁盘 actual SHA（逐项）；FAIL 即 exit 1。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
import phase9a_manifest as pm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(P9R1 / "manifest_v5.json"))
    parser.add_argument("--r1-dir", default=str(P9R1))
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    r1_dir = Path(args.r1_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "sealed":
        sys.exit("FAIL: manifest not sealed")
    base = manifest_path.parent.parent.parent.parent
    all_ok = True
    for name, entry in sorted(manifest["entries"].items()):
        p = base / entry["path"]
        if not p.exists():
            print(f"  FAIL  {name}: missing")
            all_ok = False
            continue
        actual = pm.STRATEGY_FN[entry["strategy"]](p)
        ok = actual == entry["sha256"]
        all_ok = all_ok and ok
        print(f"  {'ok' if ok else 'FAIL'}  {name}  ({entry['strategy']})")
    # upstream manifest_v4 校验（必需）
    upstream = manifest["entries"].get("upstream_manifest_v4")
    if upstream is None:
        print("  FAIL  upstream_manifest_v4 missing")
        all_ok = False
    else:
        upstream_path = base / upstream["path"]
        upstream_data = json.loads(upstream_path.read_text(encoding="utf-8"))
        upstream_ok = upstream_data["stage"] == "sealed" and pm.STRATEGY_FN[upstream["strategy"]](upstream_path) == upstream["sha256"]
        all_ok = all_ok and upstream_ok
        print(f"  {'ok' if upstream_ok else 'FAIL'}  upstream manifest_v4 (stage=sealed, SHA match)")
    # treatment fingerprint 双 SHA 校验（P0 修订：路径从 manifest 条目解析，非 parent.parent）
    tf_entry = manifest["entries"]["upstream_treatment_fingerprint"]
    tf_path = base / tf_entry["path"]
    tf = json.loads(tf_path.read_text(encoding="utf-8"))
    tf_file_sha = hashlib.sha256(json.dumps(tf, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b"\n").hexdigest()
    tf_ok = tf_file_sha == tf_entry["sha256"]
    all_ok = all_ok and tf_ok
    print(f"  {'ok' if tf_ok else 'FAIL'}  treatment fingerprint unchanged")
    # calibration fingerprint 组件与 manifest 条目一致（组件集合精确相等 + 顺序冻结 + 总摘要重算）
    cf = json.loads((r1_dir / "calibration_fingerprint.json").read_text(encoding="utf-8"))
    expected_names = ["silver_judge_v3_py", "silver_relevance_judgment_v3", "silver_judgment_summary_v3", "qc_sample_list_v2", "attribution_json"]
    cf_names = [c["logical_name"] for c in cf["components"]]
    cf_ok = cf_names == expected_names
    for c in cf["components"]:
        if manifest["entries"].get(c["logical_name"], {}).get("sha256") != c["sha256"]:
            cf_ok = False
    digest = hashlib.sha256()
    for c in cf["components"]:
        digest.update(c["sha256"].encode() + b"\0")
    if digest.hexdigest() != cf["sha256"]:
        cf_ok = False
    all_ok = all_ok and cf_ok
    print(f"  {'ok' if cf_ok else 'FAIL'}  calibration fingerprint (components + aggregate SHA)")
    # verdict 与 effective_disagreement 一致
    qr = json.loads((r1_dir / "qc_result_v2.json").read_text(encoding="utf-8"))
    verdict_ok = (qr["verdict"] == "SILVER_LABEL_CALIBRATED" and qr["effective_disagreement"] <= 6) or \
                 (qr["verdict"] == "SILVER_LABEL_NOT_CALIBRATED" and qr["effective_disagreement"] > 6)
    all_ok = all_ok and verdict_ok
    print(f"  {'ok' if verdict_ok else 'FAIL'}  verdict matches effective_disagreement")
    # RECEIPT 校验（P0 修订：artifact 集合精确相等 + SHA/size/strategy/verdict + 绑定 sealed manifest SHA）
    receipt = json.loads((r1_dir / "RECEIPT_r1.json").read_text(encoding="utf-8"))
    receipt_ok = True
    if set(receipt["artifacts"]) != {"qc_result_v2.json", "calibration_fingerprint.json", "CLOSURE.md"}:
        receipt_ok = False  # artifact 集合必须精确等于三项正式产物
    if receipt["verdict"] != qr["verdict"]:
        receipt_ok = False
    if receipt["manifest_sha256"] != pm.STRATEGY_FN["json_canonical"](manifest_path):
        receipt_ok = False
    for name, meta in receipt["artifacts"].items():
        raw = (r1_dir / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != meta["sha256"] or len(raw) != meta["size"] or meta["strategy"] != "raw_bytes":
            receipt_ok = False
    all_ok = all_ok and receipt_ok
    print(f"  {'ok' if receipt_ok else 'FAIL'}  RECEIPT (artifacts + sealed manifest binding)")
    # closure 与 qc_result 一致（P0/中优修订：严格行解析，非子串 in）
    closure = (r1_dir / "CLOSURE.md").read_text(encoding="utf-8")
    fields = {}
    for line in closure.splitlines():
        if ": " in line and not line.startswith("#"):
            k, v = line.split(": ", 1)
            fields[k.strip()] = v.strip()
    closure_ok = (
        fields.get("verdict") == qr["verdict"]
        and fields.get("effective_disagreement") == f"{qr['effective_disagreement']}/61"
        and fields.get("disagreement_count") == str(qr["disagreement_count"])
        and fields.get("uncertain_count") == str(qr["uncertain_count"])
    )
    all_ok = all_ok and closure_ok
    print(f"  {'ok' if closure_ok else 'FAIL'}  closure matches qc_result")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 冻结两脚本 → 先跑恢复协议测试（镜像）→ 正式发布 → 正式对账 → 终态测试 → Commit**

P0 修订：不可逆 one-shot 正式发布必须在恢复协议测试全绿之后。

5a. 冻结两个脚本（两文件均已实现，manifest_v5 code_frozen 阶段追加）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
pm.freeze(P9R1 / "manifest_v5.json", {
    "finalize_r1_py": (P9R1 / "finalize_r1.py", "git_canonical_lf"),
    "reconcile_r1_py": (P9R1 / "reconcile_r1.py", "git_canonical_lf"),
})
print("finalize_r1_py + reconcile_r1_py frozen")
```

5b. 先跑恢复协议测试（镜像从 code_frozen 输入构造，不依赖正式终态产物，在正式发布前证明恢复路径）：

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestFinalizeResumeProtocol -q`
Expected: PASS（4 个生产路径测试全绿后才允许正式发布）。

5c. 执行正式发布：

Run: `.venv/Scripts/python.exe docs/phase9a/r1/finalize_r1.py`
Expected: `finalize_r1: verdict=SILVER_LABEL_CALIBRATED|NOT_CALIBRATED, effective_disagreement=N/61, manifest_v5 sealed, RECEIPT published`。

5d. 执行正式对账：

Run: `.venv/Scripts/python.exe docs/phase9a/r1/reconcile_r1.py`
Expected: exit 0 无 FAIL。

5e. 运行终态测试验证正式产物：

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestTerminalV2 -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/r1/manifest_v5.json docs/phase9a/r1/finalize_r1.py docs/phase9a/r1/reconcile_r1.py docs/phase9a/r1/qc_result_v2.json docs/phase9a/r1/calibration_fingerprint.json docs/phase9a/r1/CLOSURE.md docs/phase9a/r1/RECEIPT_r1.json docs/phase9a/r1/qc_human_review_v2.jsonl tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "chore(phase9a-r1): finalize_r1 single-shot publish + reconcile_r1 final audit"
```

---

## 完成定义（对齐设计 §8）

1. 归因证据入库（attribution.py + attribution.json，SHA 落盘）。
2. 验证集样本 + 盲评 packet 在 v3 规则与任何 v3 label 前冻结（61 条，37 item，确定性无放回）。
3. 校准规则（v3）冻结（query 无 category 时 cat_ok=True）。
4. 校准后 judgment 生成（673 条，版本化新文件）。
5. 验证集人工 QC effective_disagreement ≤6（CALIBRATED）或 >6（NOT_CALIBRATED）；**无论是否超过 6，都继续发布对应终态与证据**。
6. 终态为 SILVER_LABEL_CALIBRATED 或 SILVER_LABEL_NOT_CALIBRATED 之一，结论闭合。
7. 全程零 API、零生产代码改动；manifest_v5 sealed（含前代链记录）。

## 反过拟合与纪律（冻结）

- 不得为过门修改规则、judgment 或验证集；QC 只审计不改标签；正式评测产物只生成一次（one-shot 门）。
- 不在 44 道已知婚姻题上宣称准确率提升；SILVER_LABEL_CALIBRATED 只证明标签规则校准有效。
- 不改 retriever、ranking、truncation、query 集、strategy_outputs（全部保持 Phase 9A 冻结状态）。
- 密封集数据不进入本任务；curator 数据位置只提供给独立受限 curator 任务。
