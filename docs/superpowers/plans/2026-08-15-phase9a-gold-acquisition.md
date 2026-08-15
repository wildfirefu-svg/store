# Phase 9A-Gold item-centered 人工 Gold 采集 Implementation Plan（v1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 v1.7 规约建立 item-centered 人工 Gold（112 项，A 提议 + B 盲审 + C 裁决），产出 `GOLD_READY / GOLD_BLOCKED_ACQUISITION` 之一终态并密封。

**Architecture:** 纯本地零 LLM API；复用 Phase 9A 冻结语料（kb_snapshot.db、classic_texts 冻结版）。执行顺序：**config_frozen（112 项定义/角色/搜索计划/HN QC 配置/守护配置）→ code_frozen（工具链：读取包装器/搜索执行器/盲审包生成器/解盲映射器/校验器/对账器 + HN 抽样 + r1 盲审包 + B verification packet）→ 人工采集（A 提议 → 搜索执行 → B 盲审 → 解盲 → 分歧裁决）→ gold_validate 全过 → sealed + GOLD_RECEIPT**。

**Tech Stack:** Python 3.11+、sqlite3（只读 URI）、git object 读取、pytest、ruff（E9/F821 基线）。

**设计依据：** `docs/superpowers/specs/2026-08-14-phase9a-gold-data-spec.md` v1.7（commit `c06daec`，APPROVED）。
**前置冻结：** Phase 9A（manifest_v4 sealed）+ Phase 9A-R1（manifest_v5 sealed）。

**命令约定：** PowerShell；路径基于 `__file__`；commit 用显式 pathspec；pre-commit stash 冲突可原样重试一次，禁止 `--no-verify`。
**提交纪律：** 每个 commit 前先 `git status --porcelain` + `git diff --cached --name-only` 核对暂存清单，防止卷入并行蒸馏线 churn。

---

## 输入基线（Task 0 复核）

| 输入 | 路径 | 用途 |
|---|---|---|
| KB 快照（只读） | `docs/phase8/marriage-capability/kb_snapshot.db` | 冻结语料 |
| classic_texts 冻结版 | `docs/phase8/marriage-capability/classic_texts_freeze.json` + git object | 冻结语料 |
| 112 项清单 | `docs/phase9a/retrieval/item_query_map.json` | item 定义来源 |
| Phase 8 语义源 | `docs/phase8/marriage-capability/required_knowledge.jsonl` + `knowledge_audit.jsonl` | required_term/query_specs 来源 |
| Phase 9A manifest | `docs/phase9a/retrieval/manifest_v4.json` | 上游冻结基线 |
| Phase 9A 检索器 | `docs/phase9a/retrieval/retriever.py` | canonical_key 解析 + doc_text（只读复用，不修改） |

---

## Task 0: 基线验证 + gold manifest 初始化（config_frozen）

**Files:**
- Create: `docs/phase9a/gold/gold_manifest.json`（初始 config_frozen）
- Create: `docs/phase9a/gold/gold_item_definitions.json`
- Create: `docs/phase9a/gold/gold_roles.json`（模板，人工填写身份）
- Create: `docs/phase9a/gold/gold_search_plans.json`
- Create: `docs/phase9a/gold/gold_b_verification_plans.json`
- Create: `docs/phase9a/gold/gold_hn_qc_config.json`
- Create: `docs/phase9a/gold/gold_guard_config.json`（禁改守护配置，seal 前冻结）
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 复核 Phase 9A/R1 对账与输入存在性**

Run:
```powershell
.venv/Scripts/python.exe docs/phase9a/retrieval/reconcile9a.py
.venv/Scripts/python.exe docs/phase9a/r1/reconcile_r1.py
Test-Path docs/phase9a/retrieval/item_query_map.json
Test-Path docs/phase8/marriage-capability/required_knowledge.jsonl
Test-Path docs/phase8/marriage-capability/knowledge_audit.jsonl
```
Expected: 两个 reconcile exit 0 无 FAIL；全部 True。

- [ ] **Step 2: 写失败测试**

`tests/test_phase9a_gold.py`（新建文件，顶部 helper 复用 Phase 9A 测试模式）：
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


class TestGoldConfigFrozen:
    def test_manifest_config_frozen(self):
        m = _load_json(PG / "gold_manifest.json")
        assert m["stage"] == "config_frozen"
        for name in ("upstream_manifest_v4", "gold_item_definitions", "gold_roles", "gold_search_plans",
                     "gold_b_verification_plans", "gold_hn_qc_config", "gold_guard_config"):
            assert name in m["entries"], f"{name} not frozen"

    def test_item_definitions_112(self):
        defs = _load_json(PG / "gold_item_definitions.json")
        assert defs["schema_version"] == "1.0"
        assert len(defs["items"]) == 112
        item_ids = [i["item_id"] for i in defs["items"]]
        assert item_ids == sorted(item_ids)  # 按 item_id 排序
        assert len(set(item_ids)) == 112
        for item in defs["items"]:
            assert {"item_id", "case_id", "required_term", "query_specs", "item_description", "upstream"} <= set(item)
            assert item["upstream"]["required_knowledge_sha256"] and item["upstream"]["knowledge_audit_sha256"]

    def test_roles_template(self):
        roles = _load_json(PG / "gold_roles.json")
        assert roles["schema_version"] == "1.0"
        # 模板状态：身份为占位符，采集前必须人工填写为互不相同的人类身份
        assert roles["curator_A"] and roles["curator_B"]
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigFrozen -q`
Expected: FAIL（文件不存在）。

- [ ] **Step 4: 实现 gold_item_definitions 生成器 + 生成**

写 `docs/phase9a/gold/build_item_definitions.py`：
```python
"""Phase 9A-Gold：从 Phase 8 冻结数据生成 112 项定义（含上游路径与 SHA）。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"
PG = REPO / "docs" / "phase9a" / "gold"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(P8))
    import phase9a_manifest as pm
    pm.verify_frozen(P9 / "manifest_v4.json", ["item_query_map"], required_stage="sealed")
    item_map = json.loads((P9 / "item_query_map.json").read_text(encoding="utf-8"))
    rk = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "required_knowledge.jsonl").open(encoding="utf-8") if l.strip())}
    audit = {r["case_id"]: r for r in (json.loads(l) for l in (P8 / "knowledge_audit.jsonl").open(encoding="utf-8") if l.strip())}
    rk_sha = _sha(P8 / "required_knowledge.jsonl")
    audit_sha = _sha(P8 / "knowledge_audit.jsonl")
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
                "required_knowledge_sha256": rk_sha,
                "knowledge_audit_path": "docs/phase8/marriage-capability/knowledge_audit.jsonl",
                "knowledge_audit_sha256": audit_sha,
            },
        })
    items.sort(key=lambda i: i["item_id"])
    assert len(items) == 112
    out = {"schema_version": "1.0", "items": items}
    PG.mkdir(parents=True, exist_ok=True)
    (PG / "gold_item_definitions.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"gold_item_definitions written: {len(items)} items")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 生成其余 config 文件 + 初始化 manifest（config_frozen）**

`gold_roles.json`（模板，人工填写身份）：
```json
{"schema_version": "1.0", "curator_A": "PLACEHOLDER_HUMAN_A", "curator_B": "PLACEHOLDER_HUMAN_B", "curator_C": null, "note": "采集前必须人工填写为互不相同的人类身份；C 可选但须采集前冻结；未指定或身份相同 → BLOCKED_ROLE_ASSIGNMENT"}
```

`gold_search_plans.json`（模板，人工/工具生成）：每 item 一份搜索计划（正例步骤 + hn 步骤），每步 `step_id/entrypoint/args/query_terms/filters/corpus_snapshot_sha256`。初版可由工具从 item_query_map 的 query_specs 机械生成（每 item 一个正例步骤 + 一个 hn 步骤），人工可补充。

`gold_b_verification_plans.json`（全量 112 项预冻结）：每项 `_bv` 步骤（entrypoint/args/query_terms/filters）。

`gold_hn_qc_config.json`：
```json
{"schema_version": "1.0", "seed": 20260814, "ratio": 0.2, "stratify_by": "item_id", "sample_count_formula": "ceil(total_hn * 0.2)", "per_item_min_formula": "floor(n_hn_i * 0.2)", "remainder_allocation": "item_id 字典序逐层 +1", "overflow_return": "缺口回流剩余层（同序继续补足）", "rng": "random.Random(20260814) 全局单实例", "note": "样本列表先于 r1 盲审包构造冻结"}
```

`gold_guard_config.json`（禁改守护配置，seal 前冻结）：
```json
{"schema_version": "1.0", "protected_paths": ["docs/phase9a/gold/gold_v1.json", "docs/phase9a/gold/gold_manifest.json"], "activation": "GOLD_RECEIPT 发布后激活", "note": "修订必须新建 gold_v2.json"}
```

初始化 manifest（config_frozen）：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P9 = Path("docs/phase9a/retrieval")
PG = Path("docs/phase9a/gold")
m = PG / "gold_manifest.json"
pm.set_stage(m, "config_frozen")
pm.freeze(m, {
    "upstream_manifest_v4": (P9 / "manifest_v4.json", "json_canonical"),
    "gold_item_definitions": (PG / "gold_item_definitions.json", "json_canonical"),
    "gold_roles": (PG / "gold_roles.json", "json_canonical"),
    "gold_search_plans": (PG / "gold_search_plans.json", "json_canonical"),
    "gold_b_verification_plans": (PG / "gold_b_verification_plans.json", "json_canonical"),
    "gold_hn_qc_config": (PG / "gold_hn_qc_config.json", "json_canonical"),
    "gold_guard_config": (PG / "gold_guard_config.json", "json_canonical"),
})
print("gold_manifest initialized at config_frozen")
```

- [ ] **Step 6: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigFrozen -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_item_definitions.json docs/phase9a/gold/gold_roles.json docs/phase9a/gold/gold_search_plans.json docs/phase9a/gold/gold_b_verification_plans.json docs/phase9a/gold/gold_hn_qc_config.json docs/phase9a/gold/gold_guard_config.json docs/phase9a/gold/build_item_definitions.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): config_frozen - 112 item definitions + roles/search plans/HN QC config/guard config"
```

---

## Task 1: 工具链冻结（code_frozen）

**Files:**
- Create: `docs/phase9a/gold/gold_read_access.py`（读取包装器，自动 access log）
- Create: `docs/phase9a/gold/gold_search_exec.py`（搜索计划执行器，落盘 gold_search_results.jsonl）
- Create: `docs/phase9a/gold/gold_blind_packet_builder.py`（混合盲审包生成器，含 filler/positive_control）
- Create: `docs/phase9a/gold/gold_unblind_mapper.py`（解盲映射生成器，含冻结四态映射）
- Create: `docs/phase9a/gold/gold_validate.py`（机器校验器）
- Create: `docs/phase9a/gold/reconcile_gold.py`（对账入口）
- Create: `docs/phase9a/gold/gold_hn_qc_sample_list.json`（HN 抽样，先于 r1 构造冻结）
- Create: `docs/phase9a/gold/gold_blind_review_packet_r1.jsonl`（r1 盲审包，packet SHA 冻结）
- Create: `docs/phase9a/gold/gold_b_verification_packet.jsonl`（B verification packet，packet SHA 冻结）
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 写失败测试（工具链核心契约）**

```python
class TestGoldToolchain:
    def test_stable_hash_deterministic(self):
        # stable_hash 跨进程可复现
        import hashlib
        def stable_hash(item_id: str) -> int:
            return int.from_bytes(hashlib.sha256(item_id.encode("utf-8")).digest()[:8], "big")
        assert stable_hash("mingli_ftb_0002#k4") == stable_hash("mingli_ftb_0002#k4")
        assert isinstance(stable_hash("mingli_ftb_0002#k4"), int)

    def test_four_state_mapping_frozen(self):
        # 四态映射冻结（解盲工具与 reconcile 共用）
        m = _load_module("gold_unblind_mapper", "docs/phase9a/gold/gold_unblind_mapper.py")
        assert m.FOUR_STATE_MAP[("positive_proposal", "relevant")] == "confirmed"
        assert m.FOUR_STATE_MAP[("positive_proposal", "partially_relevant")] == "disagreement"
        assert m.FOUR_STATE_MAP[("hard_negative", "irrelevant")] == "confirmed"
        assert m.FOUR_STATE_MAP[("hard_negative", "relevant")] == "rejected"
        assert m.FOUR_STATE_MAP[("hard_negative", "uncertain")] == "uncertain"
        assert m.FOUR_STATE_MAP[("positive_control", "relevant")] == "diagnostic_only"
        assert m.FOUR_STATE_MAP[("filler", "irrelevant")] == "diagnostic_only"

    def test_hn_sampling_deterministic(self):
        # HN 分层抽样精确等于算法输出
        sample = _load_json(PG / "gold_hn_qc_sample_list.json")
        assert sample["seed"] == 20260814
        assert sample["sample_count"] == len(sample["sample_list"])
        # 样本列表在 r1 构造前冻结（manifest code_frozen 阶段含该条目）
        m = _load_json(PG / "gold_manifest.json")
        assert "gold_hn_qc_sample_list" in m["entries"]

    def test_blind_packet_no_type_leak(self):
        # r1 盲审包不含类型/身份/理由字段
        packet = [json.loads(l) for l in (PG / "gold_blind_review_packet_r1.jsonl").open(encoding="utf-8") if l.strip()]
        for p in packet:
            assert {"blind_id", "item_id", "canonical_key", "document_text"} <= set(p)
            assert "proposal_type" not in p and "curator" not in p and "reason" not in p and "collision_terms" not in p

    def test_verification_packet_frozen(self):
        # B verification packet 冻结（无 no-positive 时为空集产物）
        assert (PG / "gold_b_verification_packet.jsonl").exists()
        m = _load_json(PG / "gold_manifest.json")
        assert "gold_b_verification_packet" in m["entries"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldToolchain -q`
Expected: FAIL。

- [ ] **Step 3: 实现六个工具脚本**

各脚本职责（完整实现代码较长，此处给出关键契约；实现时严格遵循规约 §3-§6）：

**gold_read_access.py**：唯一语料读取包装器；`read_corpus(canonical_key, role)` 自动追加 `gold_access_log.jsonl`（role/timestamp/canonical_key/source_dir）；A 侧调用必须经此（access_attestation）。

**gold_search_exec.py**：执行 gold_search_plans.json / gold_b_verification_plans.json 的步骤；每步落盘 `gold_search_results.jsonl`（step_id/item_id/ordered_candidate_keys/candidate_keys_sha256/candidate_count）；唯一终态校验（每 step_id 恰一行）；候选排序去重规则与 SHA canonical 规则按规约 §4。

**gold_blind_packet_builder.py**：生成 r1/r2/r3 混合盲审包；filler 算法（逐 item、独立 RNG、stable_hash）；positive_control 契约（diagnostic_only、确定性抽取、有放回循环、source_positive_ref）；全局打乱（轮次派生 seed）；blind_id 编号；r2/r3 生成器 fail-closed 校验前一轮 label receipt + 触发条件。

**gold_unblind_mapper.py**：冻结四态映射 FOUR_STATE_MAP；解盲映射生成（只能在 B_LABEL_RECEIPT 发布后，校验 SHA 匹配）；输出 gold_blind_unblind_map_rN.json（绑定 packet SHA + label SHA）。

**gold_validate.py**：机器校验全集（112 项状态完整 / canonical key 可解析 / evidence_quote 子串真实 / 搜索计划执行覆盖 / 候选集合严格相等 / 引用完整性 / 双审闭合 / 盲审 receipt 绑定链与时间序 / 四态映射共用 / HN 抽样精确等于算法输出）。

**reconcile_gold.py**：逐项 SHA + RECEIPT 版本化集合与绑定 + 112 项完整性 + 双审闭合 + 盲审 receipt 绑定链 + 引用完整性 + 候选集合对账 + access log（B 侧）校验 + 四态映射共用校验 + 恒等关系校验。

- [ ] **Step 4: 冻结工具链（code_frozen）→ 生成 HN 抽样 + r1 盲审包 + B verification packet**

冻结六个脚本 + 推进 code_frozen：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
m = PG / "gold_manifest.json"
pm.freeze(m, {
    "gold_read_access_py": (PG / "gold_read_access.py", "git_canonical_lf"),
    "gold_search_exec_py": (PG / "gold_search_exec.py", "git_canonical_lf"),
    "gold_blind_packet_builder_py": (PG / "gold_blind_packet_builder.py", "git_canonical_lf"),
    "gold_unblind_mapper_py": (PG / "gold_unblind_mapper.py", "git_canonical_lf"),
    "gold_validate_py": (PG / "gold_validate.py", "git_canonical_lf"),
    "reconcile_gold_py": (PG / "reconcile_gold.py", "git_canonical_lf"),
})
pm.set_stage(m, "code_frozen")
print("toolchain frozen; stage=code_frozen")
```

生成 HN 抽样（先于 r1 构造冻结）→ 生成 r1 盲审包 → 冻结 packet SHA → 生成 B verification packet → 冻结 packet SHA → 生成 B_VERIFICATION_PACKET_RECEIPT.json。

- [ ] **Step 5: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_read_access.py docs/phase9a/gold/gold_search_exec.py docs/phase9a/gold/gold_blind_packet_builder.py docs/phase9a/gold/gold_unblind_mapper.py docs/phase9a/gold/gold_validate.py docs/phase9a/gold/reconcile_gold.py docs/phase9a/gold/gold_hn_qc_sample_list.json docs/phase9a/gold/gold_blind_review_packet_r1.jsonl docs/phase9a/gold/gold_b_verification_packet.jsonl docs/phase9a/gold/B_VERIFICATION_PACKET_RECEIPT.json tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): code_frozen - toolchain + HN sampling + r1 blind packet + B verification packet"
```

---

## Task 2: 人工采集（A 提议 → 搜索执行 → B 盲审 → 解盲 → 分歧裁决）

**Files:**
- Create: `docs/phase9a/gold/gold_acquisition_log.jsonl`（过程记录，含 blocked 项）
- Create: `docs/phase9a/gold/gold_search_results.jsonl`（搜索执行结果）
- Create: `docs/phase9a/gold/gold_b_labels_r1.jsonl`（B 盲审标签）
- Create: `docs/phase9a/gold/BLIND_PACKET_RECEIPT_r1.json` + `B_LABEL_RECEIPT_r1.json`
- Create: `docs/phase9a/gold/gold_blind_unblind_map_r1.json`
- Create: `docs/phase9a/gold/gold_access_log.jsonl`
- Create: `docs/phase9a/gold/gold_b_verification_labels.jsonl`
- （按需）r2/r3 轮次产物

**⏸ 暂停点（人工主体工作）：** 本 Task 是 curator_A/B/C 的人工采集流程，开发者只提供工具与校验。流程：

1. **角色确认**：gold_roles.json 填写互不相同人类身份（否则 BLOCKED_ROLE_ASSIGNMENT）
2. **A 采集**：对每 item 执行搜索计划（gold_search_exec.py 落盘结果）→ 提议正例（canonical_key + evidence_quote + trace 引用）→ 选择 hard negative → 记录轨迹到 gold_acquisition_log.jsonl；找不到正例 → 完整 no_positive 证据
3. **B 盲审**：发布器校验 BLIND_PACKET_RECEIPT_r1 后复制 r1 包到 B 目录 → B 对全部条目四态打标 → gold_b_labels_r1.jsonl 冻结 → B_LABEL_RECEIPT_r1 发布
4. **解盲**：gold_unblind_mapper.py 校验 B_LABEL_RECEIPT_r1 后生成 gold_blind_unblind_map_r1.json
5. **分歧处理**：按冻结映射派生；分歧 → C 裁决或 BLOCKED_ACQUISITION
6. **HN 失败门**：r1 抽查有 rejected/uncertain → 生成 r2 包（全部剩余 HN + positive controls + filler）→ B 复核 → 必要时 r3（replacement）
7. **no_positive 复核**：B 审核 verification packet → 聚合规则判定
8. **机器校验**：gold_validate.py 全过

**本 Task 无自动化测试**（人工主体）；完成标志是 gold_validate.py exit 0 + 全部过程产物落盘。

---

## Task 3: 密封发布（sealed + GOLD_RECEIPT）

**Files:**
- Create: `docs/phase9a/gold/gold_v1.json`（裁决后派生结果）
- Create: `docs/phase9a/gold/GOLD_CLOSURE.md`
- Create: `docs/phase9a/gold/GOLD_RECEIPT.json`
- Modify: `docs/phase9a/gold/gold_manifest.json`（sealed）
- Test: `tests/test_phase9a_gold.py`

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
        assert receipt["manifest_sha256"] == hashlib.sha256(json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b"\n").hexdigest()
        assert "GOLD_RECEIPT" not in m["entries"]  # RECEIPT 不加入 manifest
        # 版本化集合：基础项 + 每轮项 + HN 样本列表
        assert "gold_v1.json" in receipt["artifacts"]
        assert receipt["acquisition_verdict"] == gold["acquisition_verdict"]

    def test_reconcile_gold_exit_zero(self):
        proc = subprocess.run([sys.executable, str(PG / "reconcile_gold.py")], capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "FAIL" not in proc.stdout
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldSealed -q`
Expected: FAIL。

- [ ] **Step 3: 生成 gold_v1.json + GOLD_CLOSURE.md → 冻结 → sealed → GOLD_RECEIPT**

gold_v1.json 由 gold_unblind_mapper.py 从裁决后派生结果生成（只含 confirmed/third_party_adjudicated 的 positive + hard negative + no_positive/BLOCKED 状态）。

GOLD_CLOSURE.md 内容：acquisition_verdict、统计（anchored/no_positive/blocked 计数 + 实际盲审轮数）、隔离等级（B=packet_only，A=access_attestation）、filler/control 分布诊断（含 control 唯一数/重复数/复用率）、后续衔接（R2）。

发布链：发布 gold_v1.json + 审计产物 → 冻结条目 → set_stage(sealed) → 最后发布 GOLD_RECEIPT.json（绑定 sealed manifest SHA + 版本化 artifact 集合）。

- [ ] **Step 4: reconcile_gold exit 0 → 测试转绿 → Commit**

Run: `.venv/Scripts/python.exe docs/phase9a/gold/reconcile_gold.py`
Expected: exit 0 无 FAIL。
Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_v1.json docs/phase9a/gold/GOLD_CLOSURE.md docs/phase9a/gold/GOLD_RECEIPT.json docs/phase9a/gold/gold_acquisition_log.jsonl docs/phase9a/gold/gold_search_results.jsonl docs/phase9a/gold/gold_b_labels_r1.jsonl docs/phase9a/gold/gold_blind_unblind_map_r1.json docs/phase9a/gold/BLIND_PACKET_RECEIPT_r1.json docs/phase9a/gold/B_LABEL_RECEIPT_r1.json docs/phase9a/gold/gold_access_log.jsonl docs/phase9a/gold/gold_b_verification_labels.jsonl tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "chore(phase9a-gold): sealed + GOLD_RECEIPT published (acquisition_verdict=...)"
```

- [ ] **Step 5: 禁改守护激活**

GOLD_RECEIPT 发布后，按 gold_guard_config.json 将 gold_v1.json + gold_manifest.json 加入 Qoder Hook 禁改数据产物清单（只激活既有配置，不修改受保护代码）。

---

## 完成定义（对齐规约 §11）

1. 规约 v1.7 通过审核（已 APPROVED）
2. gold_roles.json 指定 A、B 两名互不相同人类身份（C 可选但须采集前冻结）
3. config/code 阶段全部条目冻结（含各轮盲审包 SHA 与 B verification packet SHA 先于 B 查看；HN 抽样先于 r1 构造冻结）
4. 采集完成或明确阻塞：112 项全部有终态状态记录
5. 双审闭合：各轮盲审包四态标签冻结后解盲（receipt 绑定链完整）；每条 positive 有 resolution；每个分歧有 C 裁决或 BLOCKED；no_positive 有 B 结构化复核
6. 机器校验全过：canonical key 可解析、evidence_quote 子串真实、候选清单落盘可复算、reviewed == candidates 严格相等、trace_step_refs 引用完整、hard negative 分层抽样精确等于算法输出
7. 终态 GOLD_READY 或 GOLD_BLOCKED_ACQUISITION；两分支都完整发布证据（RECEIPT 版本化集合；blocked 项过程记录存在）
8. sealed + GOLD_RECEIPT 发布，reconcile_gold exit 0；禁改守护激活
9. 全程零 LLM API；GOLD_CLOSURE 如实记录隔离等级与 filler/control 分布诊断

## 反过拟合与纪律（冻结）

- 不得为过门修改规则、judgment 或验证集；QC 只审计不改标签；正式评测产物只生成一次（one-shot 门）
- 不为凑齐 112 项强行裁决分歧；不把采集失败改写为"未找到"（BLOCKED 是合法终态）
- 不允许 AI 参与标注（零 LLM API）；不复用 R1 盲评材料作为 Gold 候选
- 不修改 Phase 9A / R1 任何 sealed 产物
- Gold 不用于 44 道已知婚姻题的准确率声明；效果声明以密封集为准
- 密封婚姻集数据不进入 Gold 采集
