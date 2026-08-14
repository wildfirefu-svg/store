# Phase 9A-R1 silver relevance 标签校准 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 校准 silver relevance 标签边界（cat_ok 规则修订），使独立验证集（61 条，37 item 覆盖）人工 QC effective_disagreement ≤6，产出 `SILVER_LABEL_CALIBRATED / SILVER_LABEL_NOT_CALIBRATED` 之一终态。

**Architecture:** 纯本地零 API；复用 Phase 9A 冻结输入（kb_snapshot.db、classic_texts 冻结版、strategy_outputs.jsonl、item_query_map.json）。执行顺序：**归因证据入库 → 验证集样本冻结（在 v3 规则与任何 v3 label 前）→ 校准规则冻结 → 校准 judgment 生成 → 人工 QC 盲评 → 终态判定 → 产物封存**。全部产物版本化新文件（不修改 Phase 9A sealed 产物）。

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

---

## Task 0: 基线验证与归因证据入库

**Files:**
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
```
Expected: exit 0 无 FAIL；全部 True。

- [ ] **Step 2: 写失败测试**

`tests/test_phase9a_r1.py`（新建文件，顶部 helper 复用 Phase 9A 测试模式）：
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

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestAttribution -q`
Expected: FAIL（attribution.json 不存在）。

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

- [ ] **Step 5: 运行生成 + 测试转绿**

Run: `.venv/Scripts/python.exe docs/phase9a/r1/attribution.py`；`.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestAttribution -q`
Expected: `attribution written: 36 disagreements`；PASS。

- [ ] **Step 6: Commit**

```powershell
git add -- docs/phase9a/r1/attribution.py docs/phase9a/r1/attribution.json tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "feat(phase9a-r1): attribution evidence入库 (36 disagreements, cat_match=False root cause)"
```

---

## Task 1: 验证集样本冻结（在 v3 规则与任何 v3 label 前）

**Files:**
- Create: `docs/phase9a/r1/qc_sample_list_v2.json`
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 写失败测试**

```python
class TestValidationSample:
    def test_sample_frozen_before_v3(self):
        # 样本必须在 v3 规则与任何 v3 label 前冻结（P0：消除选择偏差）
        sample = _load_json(P9R1 / "qc_sample_list_v2.json")
        assert sample["sample_size"] == 61
        assert sample["seed"] == 20260814
        assert len(sample["sample_list"]) == 61
        # 37 item 覆盖
        items = {s["item_id"] for s in sample["sample_list"]}
        assert len(items) == 37
        # 与开发集无重叠
        dev = {r["item_id"] + "|" + r["canonical_key"] for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
        for s in sample["sample_list"]:
            assert s["item_id"] + "|" + s["canonical_key"] not in dev
        # 唯一键
        keys = [(s["item_id"], s["canonical_key"]) for s in sample["sample_list"]]
        assert len(keys) == len(set(keys))
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestValidationSample -q`
Expected: FAIL。

- [ ] **Step 3: 实现抽样脚本（确定性无放回，函数级冻结）**

写 `docs/phase9a/r1/generate_validation_sample.py`：
```python
"""Phase 9A-R1 验证集抽样：确定性无放回，61 条，37 item 覆盖。"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"


def pair_key(row):
    return (row["item_id"], row["canonical_key"])


def main() -> None:
    # 全部 judgment pair（673 条）
    all_pairs = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
    # 开发校准集（67 条）
    dev_keys = {r["item_id"] + "|" + r["canonical_key"] for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
    # 剩余候选（606 条）
    remaining = [r for r in all_pairs if r["item_id"] + "|" + r["canonical_key"] not in dev_keys]
    if len(remaining) < 61:
        sys.exit(f"BLOCKED_INPUT_DRIFT: remaining candidates {len(remaining)} < 61")
    # 按 item 分组
    pairs_by_item: dict[str, list] = {}
    for r in remaining:
        pairs_by_item.setdefault(r["item_id"], []).append(r)
    if len(pairs_by_item) < 37:
        sys.exit(f"BLOCKED_INPUT_DRIFT: remaining items {len(pairs_by_item)} < 37")
    # 确定性无放回抽样
    rng = random.Random(20260814)
    first = [rng.choice(sorted(pairs_by_item[item_id], key=pair_key)) for item_id in sorted(pairs_by_item)]
    selected_keys = {pair_key(row) for row in first}
    remaining_pool = sorted((row for row in remaining if pair_key(row) not in selected_keys), key=pair_key)
    extra = rng.sample(remaining_pool, 24)
    sample = first + extra
    # 断言
    assert len(sample) == 61
    assert len({row["item_id"] for row in sample}) == 37
    assert len({pair_key(row) for row in sample}) == 61
    assert all(pair_key(row) not in dev_keys for row in sample)
    payload = {
        "schema_version": "1.0",
        "seed": 20260814,
        "sample_size": 61,
        "pool_size": len(remaining),
        "sample_list": [{"item_id": s["item_id"], "canonical_key": s["canonical_key"]} for s in sample],
    }
    (P9R1 / "qc_sample_list_v2.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"validation sample written: {len(sample)} samples, 37 items")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行生成 + 测试转绿**

Run: `.venv/Scripts/python.exe docs/phase9a/r1/generate_validation_sample.py`；`.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestValidationSample -q`
Expected: `validation sample written: 61 samples, 37 items`；PASS。

- [ ] **Step 5: Commit**

```powershell
git add -- docs/phase9a/r1/generate_validation_sample.py docs/phase9a/r1/qc_sample_list_v2.json tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "feat(phase9a-r1): validation sample frozen before v3 rule (61 samples, 37 items, deterministic)"
```

---

## Task 2: 校准规则冻结 + 校准 judgment 生成

**Files:**
- Create: `docs/phase9a/r1/silver_judge_v3.py`
- Create: `docs/phase9a/r1/silver_relevance_judgment_v3.jsonl`
- Create: `docs/phase9a/r1/silver_judgment_summary_v3.json`
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 写失败测试**

```python
class TestCalibratedJudgment:
    def test_v3_rule_frozen(self):
        # v3 规则：query 无 category 时 cat_ok=True（不降级）
        j = _load_module("silver_judge_v3", "docs/phase9a/r1/silver_judge_v3.py")
        doc = {"text": "婚姻美满", "category": ""}
        syn = {"synonyms": {"结婚": ["婚期", "成婚"]}}
        # query 无 category → relevant（不降级）
        result = j.label_pair("结婚", None, doc, syn)
        assert result["label"] == "relevant"
        # query 有 category 且匹配 → relevant
        result2 = j.label_pair("结婚", "婚姻", {"text": "婚姻美满", "category": "婚姻"}, syn)
        assert result2["label"] == "relevant"
        # query 有 category 但不匹配 → partial
        result3 = j.label_pair("结婚", "事业", {"text": "婚姻美满", "category": "婚姻"}, syn)
        assert result3["label"] == "partially_relevant"

    def test_v3_judgment_generated(self):
        rows = [json.loads(l) for l in (P9R1 / "silver_relevance_judgment_v3.jsonl").open(encoding="utf-8") if l.strip()]
        assert len(rows) == 673  # 全部 pair 重新标注
        # 校准后 relevant 数量应显著增加（26 条 query 无 category 的分歧转为 relevant）
        labels = Counter(r["label"] for r in rows)
        assert labels["relevant"] > 86  # Phase 9A 基线 86
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
    pm.verify_frozen(P9 / "manifest_v4.json", ["retriever_py", "synonym_table", "query_set_frozen", "item_query_map",
                                               "strategy_store_py", "strategy_outputs"])
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
    import os
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
    (P9R1 / "silver_judgment_summary_v3.json").write_text(
        json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"v3 judgment written: {len(pairs)} pairs; summary written")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行生成 + 测试转绿**

Run: `.venv/Scripts/python.exe docs/phase9a/r1/silver_judge_v3.py`；`.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestCalibratedJudgment -q`
Expected: `v3 judgment written: 673 pairs; summary written`；PASS。

- [ ] **Step 5: Commit**

```powershell
git add -- docs/phase9a/r1/silver_judge_v3.py docs/phase9a/r1/silver_relevance_judgment_v3.jsonl docs/phase9a/r1/silver_judgment_summary_v3.json tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "feat(phase9a-r1): v3 calibrated judgment (cat_ok optional when query has no category)"
```

---

## Task 3: 人工 QC 复核（验证集盲评）

**Files:**
- Create: `docs/phase9a/r1/qc_human_review_v2.jsonl`（零字节模板）
- Create: `docs/phase9a/r1/qc_human_review_schema_v2.json`（schema 说明）
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 写失败测试**

```python
class TestQcStateMachineV2:
    def test_pending_review_blocks_eval(self, tmp_path):
        g = _load_module("qc_gate", "docs/phase9a/retrieval/qc_gate.py")
        empty_review = tmp_path / "qc_human_review_v2.jsonl"
        empty_review.write_text("", encoding="utf-8")
        assert g.qc_state(empty_review, P9R1 / "qc_sample_list_v2.json") == "HUMAN_QC_REQUIRED"

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
Expected: FAIL（qc_human_review_v2.jsonl 不存在时 qc_state 返回 HUMAN_QC_REQUIRED 已存在，但需验证模板文件存在）。

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
git commit -m "feat(phase9a-r1): QC v2 state machine + zero-byte template + schema"
```

**⏸ 暂停点（人工）：** 人类对照 `qc_sample_list_v2.json` 逐条填写 `qc_human_review_v2.jsonl`（human_label ∈ {relevant, partially_relevant, irrelevant, uncertain}，note 必填；**盲法：不得看到 silver label/开发集标签/归因结论**）。**未完成前不得执行 Task 4 的终态判定**。

---

## Task 4: 终态判定 + 产物封存

**Files:**
- Create: `docs/phase9a/r1/qc_result_v2.json`
- Create: `docs/phase9a/r1/calibration_fingerprint.json`
- Create: `docs/phase9a/r1/manifest_v5.json`
- Create: `docs/phase9a/r1/CLOSURE.md`
- Test: `tests/test_phase9a_r1.py`

- [ ] **Step 1: 写失败测试**

```python
class TestTerminalV2:
    def test_effective_disagreement_gate(self):
        # effective_disagreement = disagreement + uncertain；≤6 才 CALIBRATED
        result = _load_json(P9R1 / "qc_result_v2.json")
        assert "effective_disagreement" in result
        assert result["effective_disagreement"] == result["disagreement_count"] + result["uncertain_count"]
        assert result["verdict"] in {"SILVER_LABEL_CALIBRATED", "SILVER_LABEL_NOT_CALIBRATED"}
        if result["effective_disagreement"] <= 6:
            assert result["verdict"] == "SILVER_LABEL_CALIBRATED"
        else:
            assert result["verdict"] == "SILVER_LABEL_NOT_CALIBRATED"

    def test_calibration_fingerprint(self):
        fp = _load_json(P9R1 / "calibration_fingerprint.json")
        assert fp["components"] and fp["sha256"]
        # 原 treatment_fingerprint 字节不变断言
        orig_fp = _load_json(P9 / "treatment_fingerprint.json")
        assert orig_fp["sha256"]  # 存在即可（字节不变由 reconcile 校验）

    def test_manifest_v5_sealed(self):
        m = _load_json(P9R1 / "manifest_v5.json")
        assert m["stage"] == "sealed"
        assert "closure" in m["entries"] or "closure_v2" in m["entries"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestTerminalV2 -q`
Expected: FAIL。

- [ ] **Step 3: 实现终态判定脚本**

写 `docs/phase9a/r1/run_calibration_eval.py`：
```python
"""Phase 9A-R1 终态判定：effective_disagreement ≤6 → SILVER_LABEL_CALIBRATED。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
import phase9a_manifest as pm
import qc_gate as qc


def main() -> None:
    pm.verify_frozen(P9 / "manifest_v4.json", ["silver_relevance_judgment", "qc_sample_list"])
    state = qc.qc_state(P9R1 / "qc_human_review_v2.jsonl", P9R1 / "qc_sample_list_v2.json")
    if state != "REVIEWED":
        sys.exit(f"HUMAN_QC_REQUIRED: state={state}")
    reviews = qc.load_human_review(P9R1 / "qc_human_review_v2.jsonl")
    qc.validate_review_coverage(json.loads((P9R1 / "qc_sample_list_v2.json").read_text(encoding="utf-8"))["sample_list"], reviews)
    qc.validate_human_review_schema(reviews)
    # 计算 effective_disagreement（disagreement + uncertain）
    silver = {(r["item_id"], r["canonical_key"]): r["label"]
              for r in (json.loads(l) for l in (P9R1 / "silver_relevance_judgment_v3.jsonl").open(encoding="utf-8") if l.strip())}
    n_diff = sum(1 for r in reviews if r["human_label"] != silver[(r["item_id"], r["canonical_key"])])
    n_uncertain = sum(1 for r in reviews if r["human_label"] == "uncertain")
    effective = n_diff + n_uncertain
    verdict = "SILVER_LABEL_CALIBRATED" if effective <= 6 else "SILVER_LABEL_NOT_CALIBRATED"
    result = {
        "schema_version": "1.0",
        "verdict": verdict,
        "disagreement_count": n_diff,
        "uncertain_count": n_uncertain,
        "effective_disagreement": effective,
        "max_allowed": 6,
        "n_reviewed": len(reviews),
        "note": "effective_disagreement = disagreement + uncertain；≤6 才 CALIBRATED",
    }
    (P9R1 / "qc_result_v2.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"calibration eval: verdict={verdict}, effective_disagreement={effective}/61")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行终态判定**

Run: `.venv/Scripts/python.exe docs/phase9a/r1/run_calibration_eval.py`
Expected: `calibration eval: verdict=SILVER_LABEL_CALIBRATED|NOT_CALIBRATED, effective_disagreement=N/61`。

- [ ] **Step 5: 生成 calibration_fingerprint + CLOSURE.md + manifest_v5（顺序：CLOSURE 先于 manifest）**

先生成 `calibration_fingerprint.json` 与 `CLOSURE.md`（内容见下方），然后执行封存脚本：
```python
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
# calibration_fingerprint（单源：从 manifest_v5 读取）
components = ["attribution.py", "generate_validation_sample.py", "silver_judge_v3.py", "run_calibration_eval.py"]
digest = hashlib.sha256()
for c in components:
    digest.update((P9R1 / c).read_bytes().replace(b"\r\n", b"\n"))
    digest.update(b"\0")
fp = {"schema_version": "1.0", "components": components, "sha256": digest.hexdigest(),
      "note": "Phase 9A-R1 calibration fingerprint；treatment fingerprint 不变（retriever 未改）"}
(P9R1 / "calibration_fingerprint.json").write_text(json.dumps(fp, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print("calibration_fingerprint written")
```

`docs/phase9a/r1/CLOSURE.md` 内容：终态（SILVER_LABEL_CALIBRATED / NOT_CALIBRATED）、effective_disagreement、校准规则变更点（cat_ok 可选）、验证集构成（61 条/37 item/seed=20260814）、后续衔接（R2 候选覆盖）。

封存脚本（CLOSURE 与 fingerprint 先落盘，随后 seal）：
```python
import json, sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9R1 = Path("docs/phase9a/r1")
m = P9R1 / "manifest_v5.json"
pm.set_stage(m, "config_frozen")
pm.set_stage(m, "code_frozen")
targets = {
    "attribution_py": (P9R1 / "attribution.py", "git_canonical_lf"),
    "attribution_json": (P9R1 / "attribution.json", "json_canonical"),
    "generate_validation_sample_py": (P9R1 / "generate_validation_sample.py", "git_canonical_lf"),
    "qc_sample_list_v2": (P9R1 / "qc_sample_list_v2.json", "json_canonical"),
    "silver_judge_v3_py": (P9R1 / "silver_judge_v3.py", "git_canonical_lf"),
    "silver_relevance_judgment_v3": (P9R1 / "silver_relevance_judgment_v3.jsonl", "jsonl_canonical"),
    "silver_judgment_summary_v3": (P9R1 / "silver_judgment_summary_v3.json", "json_canonical"),
    "qc_human_review_v2": (P9R1 / "qc_human_review_v2.jsonl", "jsonl_canonical"),
    "qc_human_review_schema_v2": (P9R1 / "qc_human_review_schema_v2.json", "json_canonical"),
    "qc_result_v2": (P9R1 / "qc_result_v2.json", "json_canonical"),
    "run_calibration_eval_py": (P9R1 / "run_calibration_eval.py", "git_canonical_lf"),
    "calibration_fingerprint": (P9R1 / "calibration_fingerprint.json", "json_canonical"),
    "closure": (P9R1 / "CLOSURE.md", "git_canonical_lf"),
}
pm.freeze(m, targets)
pm.set_stage(m, "sealed")
print("manifest_v5 sealed")
```

- [ ] **Step 6: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_r1.py::TestTerminalV2 -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/r1/qc_result_v2.json docs/phase9a/r1/calibration_fingerprint.json docs/phase9a/r1/manifest_v5.json docs/phase9a/r1/CLOSURE.md docs/phase9a/r1/run_calibration_eval.py tests/test_phase9a_r1.py
git diff --cached --name-only
git commit -m "chore(phase9a-r1): calibration terminal + fingerprint + manifest_v5 sealed"
```

---

## 完成定义（对齐设计 §8）

1. 归因证据入库（attribution.py + attribution.json，SHA 落盘）。
2. 验证集样本在 v3 规则与任何 v3 label 前冻结（61 条，37 item，确定性无放回）。
3. 校准规则（v3）冻结（query 无 category 时 cat_ok=True）。
4. 校准后 judgment 生成（673 条，版本化新文件）。
5. 验证集人工 QC effective_disagreement ≤6（CALIBRATED）或 >6（NOT_CALIBRATED）；**无论是否超过 6，都继续发布对应终态与证据**。
6. 终态为 SILVER_LABEL_CALIBRATED 或 SILVER_LABEL_NOT_CALIBRATED 之一，结论闭合。
7. 全程零 API、零生产代码改动；manifest_v5 sealed。

## 反过拟合与纪律（冻结）

- 不得为过门修改规则、judgment 或验证集；QC 只审计不改标签；正式评测产物只生成一次。
- 不在 44 道已知婚姻题上宣称准确率提升；SILVER_LABEL_CALIBRATED 只证明标签规则校准有效。
- 不改 retriever、ranking、truncation、query 集、strategy_outputs（全部保持 Phase 9A 冻结状态）。
- 密封集数据不进入本任务；curator 数据位置只提供给独立受限 curator 任务。
