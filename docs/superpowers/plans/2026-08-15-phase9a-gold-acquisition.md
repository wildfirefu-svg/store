# Phase 9A-Gold item-centered 人工 Gold 采集 Implementation Plan（v2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 v1.7 规约建立 item-centered 人工 Gold（112 项，A 提议 + B 盲审 + C 裁决），产出 `GOLD_READY / GOLD_BLOCKED_ACQUISITION` 之一终态并密封。

**Architecture:** 纯本地零 LLM API；复用 Phase 9A 冻结语料。执行顺序（依赖链）：**基线复核 → config builder/validator 实现并冻结 → 人工填写角色 + 审核搜索计划（暂停点）→ 冻结最终 config（config_frozen）→ 工具 1a（读取+搜索执行）→ 工具 1b（HN 抽样+packet/receipt+解盲映射）→ 工具 1c（validate+reconcile+finalize+guard）→ 冻结全部代码（code_frozen）→ A 采集并冻结 proposal/HN/no-positive 快照 → 生成 HN sample + r1 packet + verification packet 并冻结 → B/C 人工暂停点（按需 r2/r3）→ finalize_gold.py 双终态发布 + reconcile + guard 验证**。

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

## Task 0: 基线验证 + 输入 SHA 记录

**Files:**
- Create: `docs/phase9a/gold/upstream_inputs_sha.json`
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
        # 上游 SHA 与 Phase 8 manifest 单源一致（jsonl_canonical 口径）
        p8m = _load_json(P8 / "manifest.json")
        assert sha["required_knowledge_sha256"] == p8m["entries"]["required_knowledge"]["sha256"]
        assert sha["knowledge_audit_sha256"] == p8m["entries"]["knowledge_audit"]["sha256"]
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldBaseline -q`
Expected: FAIL。

- [ ] **Step 4: 生成 upstream_inputs_sha.json（单源读取 Phase 8 manifest，非 raw-byte 重算）**

```python
import json, sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
P8 = Path("docs/phase8/marriage-capability")
PG = Path("docs/phase9a/gold")
p8m = json.loads((P8 / "manifest.json").read_text(encoding="utf-8"))
out = {
    "schema_version": "1.0",
    "required_knowledge_sha256": p8m["entries"]["required_knowledge"]["sha256"],
    "knowledge_audit_sha256": p8m["entries"]["knowledge_audit"]["sha256"],
    "item_query_map_sha256": json.loads((Path("docs/phase9a/retrieval") / "manifest_v4.json").read_text(encoding="utf-8"))["entries"]["item_query_map"]["sha256"],
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

## Task 1: config builder/validator 实现并冻结（freeze-before-use）

**Files:**
- Create: `docs/phase9a/gold/build_gold_config.py`（生成 112 项定义 + 搜索计划 + B verification 计划 + HN QC 配置 + 守护配置）
- Create: `docs/phase9a/gold/validate_gold_config.py`（schema 校验 + 112 项覆盖 + 上游 SHA 一致性）
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldConfigBuilder:
    def test_builder_frozen_before_use(self):
        # builder 必须先冻结到 gold_manifest（config_frozen 阶段）再运行
        m = _load_json(PG / "gold_manifest.json")
        assert "build_gold_config_py" in m["entries"]
        assert "validate_gold_config_py" in m["entries"]

    def test_config_schema_valid(self):
        defs = _load_json(PG / "gold_item_definitions.json")
        assert len(defs["items"]) == 112
        plans = _load_json(PG / "gold_search_plans.json")
        assert len(plans["plans"]) == 112
        bvp = _load_json(PG / "gold_b_verification_plans.json")
        assert len(bvp["plans"]) == 112  # 全量预冻结
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigBuilder -q`
Expected: FAIL。

- [ ] **Step 3: 实现 build_gold_config.py + validate_gold_config.py**

build_gold_config.py 职责：从 item_query_map + required_knowledge + knowledge_audit 生成 gold_item_definitions.json（112 项，含上游 SHA 从 upstream_inputs_sha.json 单源读取）+ gold_search_plans.json（每 item 正例步骤 + hn 步骤，机械生成）+ gold_b_verification_plans.json（全量 112 项 `_bv` 步骤）+ gold_hn_qc_config.json + gold_guard_config.json。builder 内部 verify_frozen（自身代码 + upstream_inputs_sha）。

validate_gold_config.py 职责：schema 校验（必填字段/类型/枚举）+ 112 项覆盖（item_id 集合与 item_query_map 一致）+ 上游 SHA 一致性（与 upstream_inputs_sha.json 匹配）+ 搜索计划完整性（每 item 至少 1 正例步骤 + 1 hn 步骤）。

- [ ] **Step 4: 初始化 gold_manifest（config_frozen）→ 冻结 builder/validator → 运行生成 config**

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
    "validate_gold_config_py": (PG / "validate_gold_config.py", "git_canonical_lf"),
})
print("gold_manifest initialized at config_frozen; builder/validator frozen")
```

Run: `.venv/Scripts/python.exe docs/phase9a/gold/build_gold_config.py`
Expected: 生成 5 个 config 文件。

Run: `.venv/Scripts/python.exe docs/phase9a/gold/validate_gold_config.py`
Expected: exit 0（schema + 112 覆盖 + 上游 SHA 一致）。

- [ ] **Step 5: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/build_gold_config.py docs/phase9a/gold/validate_gold_config.py docs/phase9a/gold/gold_item_definitions.json docs/phase9a/gold/gold_search_plans.json docs/phase9a/gold/gold_b_verification_plans.json docs/phase9a/gold/gold_hn_qc_config.json docs/phase9a/gold/gold_guard_config.json tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): config builder/validator frozen + 112 item definitions + search plans generated"
```

**⏸ 暂停点（人工）：** 人工填写 gold_roles.json（A/B/C 互不相同人类身份）+ 审核 gold_search_plans.json（112 项搜索计划完整性与合理性）。**未完成前不得执行 Task 2 的 config 冻结**。

---

## Task 2: 人工确认后冻结最终 config（config_frozen 完成）

**Files:**
- Modify: `docs/phase9a/gold/gold_roles.json`（人工填写身份）
- Modify: `docs/phase9a/gold/gold_search_plans.json`（人工审核后可补充）
- Modify: `docs/phase9a/gold/gold_manifest.json`（追加冻结）
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldConfigFinal:
    def test_roles_real_identities(self):
        roles = _load_json(PG / "gold_roles.json")
        assert roles["curator_A"] != "PLACEHOLDER_HUMAN_A"
        assert roles["curator_B"] != "PLACEHOLDER_HUMAN_B"
        assert roles["curator_A"] != roles["curator_B"]  # 互不相同
        if roles.get("curator_C"):
            assert roles["curator_C"] not in {roles["curator_A"], roles["curator_B"]}

    def test_search_plans_frozen(self):
        m = _load_json(PG / "gold_manifest.json")
        assert "gold_search_plans" in m["entries"]
        assert "gold_roles" in m["entries"]
        # 冻结后禁止补充：SHA 与磁盘一致
        plans = _load_json(PG / "gold_search_plans.json")
        entry = m["entries"]["gold_search_plans"]
        actual = __import__("phase9a_manifest").STRATEGY_FN[entry["strategy"]](PG / "gold_search_plans.json")
        assert actual == entry["sha256"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigFinal -q`
Expected: FAIL（roles 仍是占位符）。

- [ ] **Step 3: 人工填写 roles + 审核 search plans → 冻结**

人工操作后执行：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {
    "gold_roles": (PG / "gold_roles.json", "json_canonical"),
    "gold_search_plans": (PG / "gold_search_plans.json", "json_canonical"),
})
print("roles + search plans frozen")
```

- [ ] **Step 4: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldConfigFinal -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_roles.json docs/phase9a/gold/gold_search_plans.json tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): final config frozen (roles + search plans confirmed by human)"
```

---

## Task 3: 工具 1a（读取包装器 + 搜索执行器）

**Files:**
- Create: `docs/phase9a/gold/gold_read_access.py`
- Create: `docs/phase9a/gold/gold_search_exec.py`
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldTool1a:
    def test_read_access_logs(self, tmp_path):
        # 读取包装器自动记录 access log
        ra = _load_module("gold_read_access", "docs/phase9a/gold/gold_read_access.py")
        log = tmp_path / "access.jsonl"
        ra.read_corpus("kb:gejue:hy_002", role="curator_A", log_path=log)
        lines = [json.loads(l) for l in log.open(encoding="utf-8") if l.strip()]
        assert len(lines) == 1 and lines[0]["role"] == "curator_A" and lines[0]["canonical_key"] == "kb:gejue:hy_002"

    def test_search_exec_unique_terminal(self):
        # 每 step_id 恰一行终态
        se = _load_module("gold_search_exec", "docs/phase9a/gold/gold_search_exec.py")
        results = [json.loads(l) for l in (PG / "gold_search_results.jsonl").open(encoding="utf-8") if l.strip()]
        step_ids = [r["step_id"] for r in results]
        assert len(step_ids) == len(set(step_ids))  # 无重复
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldTool1a -q`
Expected: FAIL。

- [ ] **Step 3: 实现 gold_read_access.py + gold_search_exec.py**

gold_read_access.py：`read_corpus(canonical_key, role, log_path)` 自动追加 access log（role/timestamp/canonical_key/source_dir）；内部 verify_frozen（自身代码 + upstream）。

gold_search_exec.py：执行 gold_search_plans.json / gold_b_verification_plans.json 的步骤；每步落盘 gold_search_results.jsonl（step_id/item_id/ordered_candidate_keys/candidate_keys_sha256/candidate_count）；唯一终态校验（每 step_id 恰一行，重复执行 fail-closed）；候选排序去重规则与 SHA canonical 规则按规约 §4。

- [ ] **Step 4: 冻结工具 1a → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {
    "gold_read_access_py": (PG / "gold_read_access.py", "git_canonical_lf"),
    "gold_search_exec_py": (PG / "gold_search_exec.py", "git_canonical_lf"),
})
print("tool 1a frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_read_access.py docs/phase9a/gold/gold_search_exec.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): tool 1a frozen (read access wrapper + search executor)"
```

---

## Task 4: 工具 1b（HN 抽样 + packet/receipt + 解盲映射）

**Files:**
- Create: `docs/phase9a/gold/gold_hn_sampler.py`
- Create: `docs/phase9a/gold/gold_blind_packet_builder.py`
- Create: `docs/phase9a/gold/gold_unblind_mapper.py`
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldTool1b:
    def test_stable_hash_deterministic(self):
        # 调用生产实现（非重写）
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        assert builder.stable_hash("mingli_ftb_0002#k4") == builder.stable_hash("mingli_ftb_0002#k4")
        assert isinstance(builder.stable_hash("mingli_ftb_0002#k4"), int)

    def test_hn_sampling_deterministic(self):
        # 独立重算分层配额和样本列表
        sampler = _load_module("gold_hn_sampler", "docs/phase9a/gold/gold_hn_sampler.py")
        sample = _load_json(PG / "gold_hn_qc_sample_list.json")
        assert sample["seed"] == 20260814
        # 独立重算：从 gold_search_results.jsonl 的 hn 步骤候选重新执行算法
        recomputed = sampler.sample_hn(seed=20260814, ratio=0.2)
        assert recomputed == sample["sample_list"]

    def test_four_state_mapping_frozen(self):
        m = _load_module("gold_unblind_mapper", "docs/phase9a/gold/gold_unblind_mapper.py")
        assert m.FOUR_STATE_MAP[("positive_proposal", "relevant")] == "confirmed"
        assert m.FOUR_STATE_MAP[("hard_negative", "irrelevant")] == "confirmed"
        assert m.FOUR_STATE_MAP[("positive_control", "relevant")] == "diagnostic_only"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldTool1b -q`
Expected: FAIL。

- [ ] **Step 3: 实现三个工具**

gold_hn_sampler.py：分层抽样算法（候选排序键/每层最低/全局目标/余数分配/回流/全局单实例 RNG）；输出 gold_hn_qc_sample_list.json；样本列表必须先于 r1 盲审包构造冻结。

gold_blind_packet_builder.py：生成 r1/r2/r3 混合盲审包；filler 算法（逐 item、独立 RNG、stable_hash 精确定义）；positive_control 契约（diagnostic_only、确定性抽取、有放回循环、source_positive_ref）；全局打乱（轮次派生 seed）；blind_id 编号；r2/r3 生成器 fail-closed 校验前一轮 label receipt + 触发条件。

gold_unblind_mapper.py：冻结四态映射 FOUR_STATE_MAP；解盲映射生成（只能在 B_LABEL_RECEIPT 发布后，校验 SHA 匹配）；输出 gold_blind_unblind_map_rN.json（绑定 packet SHA + label SHA）。

- [ ] **Step 4: 冻结工具 1b → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {
    "gold_hn_sampler_py": (PG / "gold_hn_sampler.py", "git_canonical_lf"),
    "gold_blind_packet_builder_py": (PG / "gold_blind_packet_builder.py", "git_canonical_lf"),
    "gold_unblind_mapper_py": (PG / "gold_unblind_mapper.py", "git_canonical_lf"),
})
print("tool 1b frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_hn_sampler.py docs/phase9a/gold/gold_blind_packet_builder.py docs/phase9a/gold/gold_unblind_mapper.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): tool 1b frozen (HN sampler + blind packet builder + unblind mapper)"
```

---

## Task 5: 工具 1c（validate + reconcile + finalize + guard）

**Files:**
- Create: `docs/phase9a/gold/gold_validate.py`
- Create: `docs/phase9a/gold/reconcile_gold.py`
- Create: `docs/phase9a/gold/finalize_gold.py`
- Modify: `.qoder/hooks/guard_data_artifacts.py`（读取冻结配置并保护文件）
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldTool1c:
    def test_finalize_one_shot(self):
        # 正式终态产物已存在时 finalize_gold 必须 fail-closed
        proc = subprocess.run([sys.executable, str(PG / "finalize_gold.py")], capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode != 0 and "already exists" in (proc.stdout + proc.stderr)

    def test_guard_activated_by_receipt(self):
        # 禁改守护：仅当 GOLD_RECEIPT 有效时读取冻结配置并保护文件
        guard = _load_module("guard_data_artifacts", ".qoder/hooks/guard_data_artifacts.py")
        assert hasattr(guard, "load_gold_guard_config")  # 新增函数
        # receipt 无效时 guard 不保护 gold 文件
        # receipt 有效时 guard 保护 gold_v1.json + gold_manifest.json
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldTool1c -q`
Expected: FAIL。

- [ ] **Step 3: 实现四个工具 + 修改 guard**

gold_validate.py：机器校验全集（112 项状态完整 / canonical key 可解析 / evidence_quote 子串真实 / 搜索计划执行覆盖 / 候选集合严格相等 / 引用完整性 / 双审闭合 / 盲审 receipt 绑定链与时间序 / 四态映射共用 / HN 抽样精确等于算法输出）。

reconcile_gold.py：逐项 SHA + RECEIPT 版本化集合与绑定 + 112 项完整性 + 双审闭合 + 盲审 receipt 绑定链 + 引用完整性 + 候选集合对账 + access log（B 侧）校验 + 四态映射共用校验 + 恒等关系校验。

finalize_gold.py：单一终态发布脚本（staging → 校验 → 发布数据 → freeze/seal → 最后 receipt）；覆盖 partial publish（字节一致校验）、sealed 无 receipt（校验后补发）、重复运行（fail-closed）、字节漂移（fail-closed）。

guard_data_artifacts.py 修改：新增 `load_gold_guard_config()` 函数——仅当 GOLD_RECEIPT.json 存在且 manifest_sha256 与当前 gold_manifest.json 的 json_canonical SHA 一致时，读取 gold_guard_config.json 的 protected_paths 并加入保护；receipt 无效时不保护 gold 文件；receipt 后不得再改 hook（该修改在 seal 前完成并冻结）。

- [ ] **Step 4: 冻结工具 1c + guard 修改 → 推进 code_frozen → 测试转绿 → Commit**

```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
m = PG / "gold_manifest.json"
pm.freeze(m, {
    "gold_validate_py": (PG / "gold_validate.py", "git_canonical_lf"),
    "reconcile_gold_py": (PG / "reconcile_gold.py", "git_canonical_lf"),
    "finalize_gold_py": (PG / "finalize_gold.py", "git_canonical_lf"),
    "guard_data_artifacts_py": (Path(".qoder/hooks/guard_data_artifacts.py"), "git_canonical_lf"),
})
pm.set_stage(m, "code_frozen")
print("tool 1c + guard frozen; stage=code_frozen")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_validate.py docs/phase9a/gold/reconcile_gold.py docs/phase9a/gold/finalize_gold.py .qoder/hooks/guard_data_artifacts.py tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): tool 1c frozen (validate + reconcile + finalize + guard hook)"
```

---

## Task 6: A 采集并冻结 proposal/HN/no-positive 快照

**Files:**
- Create: `docs/phase9a/gold/gold_acquisition_log.jsonl`（过程记录）
- Create: `docs/phase9a/gold/gold_search_results.jsonl`（搜索执行结果）
- Create: `docs/phase9a/gold/gold_access_log.jsonl`
- Create: `docs/phase9a/gold/gold_proposals_snapshot.json`（A 提议快照，冻结）
- Modify: `docs/phase9a/gold/gold_manifest.json`（追加冻结）

**⏸ 暂停点（人工主体）：** curator_A 执行采集：
1. 对每 item 执行搜索计划（gold_search_exec.py 落盘结果）
2. 提议正例（canonical_key + evidence_quote + trace 引用）
3. 选择 hard negative
4. 记录轨迹到 gold_acquisition_log.jsonl
5. 找不到正例 → 完整 no_positive 证据
6. 一切语料读取经 gold_read_access.py（自动 access log）

完成后冻结快照：
```python
import sys
from pathlib import Path
sys.path.insert(0, "docs/phase8/marriage-capability")
sys.path.insert(0, "docs/phase9a/retrieval")
import phase9a_manifest as pm
PG = Path("docs/phase9a/gold")
pm.freeze(PG / "gold_manifest.json", {
    "gold_acquisition_log": (PG / "gold_acquisition_log.jsonl", "jsonl_canonical"),
    "gold_search_results": (PG / "gold_search_results.jsonl", "jsonl_canonical"),
    "gold_access_log": (PG / "gold_access_log.jsonl", "jsonl_canonical"),
    "gold_proposals_snapshot": (PG / "gold_proposals_snapshot.json", "json_canonical"),
})
print("A acquisition snapshot frozen")
```

---

## Task 7: 生成 HN sample + r1 packet + verification packet 并冻结

**Files:**
- Create: `docs/phase9a/gold/gold_hn_qc_sample_list.json`
- Create: `docs/phase9a/gold/gold_blind_review_packet_r1.jsonl`
- Create: `docs/phase9a/gold/BLIND_PACKET_RECEIPT_r1.json`
- Create: `docs/phase9a/gold/gold_b_verification_packet.jsonl`
- Create: `docs/phase9a/gold/B_VERIFICATION_PACKET_RECEIPT.json`
- Modify: `docs/phase9a/gold/gold_manifest.json`（追加冻结）
- Test: `tests/test_phase9a_gold.py`

- [ ] **Step 1: 写失败测试**

```python
class TestGoldPackets:
    def test_hn_sample_frozen_before_r1(self):
        # HN 样本列表先于 r1 盲审包构造冻结
        m = _load_json(PG / "gold_manifest.json")
        assert "gold_hn_qc_sample_list" in m["entries"]
        assert "gold_blind_review_packet_r1" in m["entries"]

    def test_blind_packet_no_type_leak(self):
        packet = [json.loads(l) for l in (PG / "gold_blind_review_packet_r1.jsonl").open(encoding="utf-8") if l.strip()]
        for p in packet:
            assert {"blind_id", "item_id", "canonical_key", "document_text"} <= set(p)
            assert "proposal_type" not in p and "curator" not in p and "reason" not in p

    def test_verification_packet_frozen(self):
        assert (PG / "gold_b_verification_packet.jsonl").exists()
        m = _load_json(PG / "gold_manifest.json")
        assert "gold_b_verification_packet" in m["entries"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldPackets -q`
Expected: FAIL。

- [ ] **Step 3: 生成 HN 抽样 → 冻结 → 生成 r1 盲审包 → 冻结 → 生成 verification packet → 冻结 → 生成 receipts**

顺序：gold_hn_sampler.py 生成样本列表 → 冻结 → gold_blind_packet_builder.py 生成 r1 包 → 冻结 packet SHA → 发布 BLIND_PACKET_RECEIPT_r1.json → gold_search_exec.py 执行 B verification 计划（no-positive 子集）→ 生成 verification packet → 冻结 packet SHA → 发布 B_VERIFICATION_PACKET_RECEIPT.json。

- [ ] **Step 4: 测试转绿 + Commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_hn_qc_sample_list.json docs/phase9a/gold/gold_blind_review_packet_r1.jsonl docs/phase9a/gold/BLIND_PACKET_RECEIPT_r1.json docs/phase9a/gold/gold_b_verification_packet.jsonl docs/phase9a/gold/B_VERIFICATION_PACKET_RECEIPT.json tests/test_phase9a_gold.py
git diff --cached --name-only
git commit -m "feat(phase9a-gold): HN sample + r1 blind packet + B verification packet frozen"
```

---

## Task 8: B/C 人工暂停点（盲审 + 解盲 + 分歧裁决 + 按需 r2/r3）

**Files:**
- Create: `docs/phase9a/gold/gold_b_labels_r1.jsonl`
- Create: `docs/phase9a/gold/B_LABEL_RECEIPT_r1.json`
- Create: `docs/phase9a/gold/gold_blind_unblind_map_r1.json`
- Create: `docs/phase9a/gold/gold_b_verification_labels.jsonl`
- （按需）r2/r3 轮次产物
- Modify: `docs/phase9a/gold/gold_manifest.json`（追加冻结）
- Test: `tests/test_phase9a_gold.py`

**⏸ 暂停点（人工主体）：** curator_B/C 执行盲审与裁决：
1. 发布器校验 BLIND_PACKET_RECEIPT_r1 后复制 r1 包到 B 目录
2. B 对全部条目四态打标 → gold_b_labels_r1.jsonl 冻结 → B_LABEL_RECEIPT_r1 发布
3. gold_unblind_mapper.py 校验 B_LABEL_RECEIPT_r1 后生成 gold_blind_unblind_map_r1.json
4. 按冻结映射派生；分歧 → C 裁决或 BLOCKED_ACQUISITION
5. HN 失败门：r1 抽查有 rejected/uncertain → 生成 r2 包 → B 复核 → 必要时 r3（replacement）
6. no_positive 复核：B 审核 verification packet → 聚合规则判定
7. 每轮机器校验并冻结

**本 Task 有自动化测试**（状态机与 receipt 链）：

```python
class TestGoldBlindReview:
    def test_unblind_after_label_receipt(self):
        # 解盲只能在 B_LABEL_RECEIPT 发布后
        mapper = _load_module("gold_unblind_mapper", "docs/phase9a/gold/gold_unblind_mapper.py")
        # 无 receipt 时 fail-closed
        # 有 receipt 且 SHA 匹配时生成映射

    def test_r2_trigger_fail_closed(self):
        # r2 生成器校验前一轮 label receipt + 触发条件
        builder = _load_module("gold_blind_packet_builder", "docs/phase9a/gold/gold_blind_packet_builder.py")
        # 无触发条件时拒绝生成 r2

    def test_blocked_path_recorded(self):
        # BLOCKED 项的未完成过程记录必须存在于 acquisition log
        log = [json.loads(l) for l in (PG / "gold_acquisition_log.jsonl").open(encoding="utf-8") if l.strip()]
        blocked = [r for r in log if r.get("status", "").startswith("BLOCKED")]
        for r in blocked:
            assert r.get("blocked_reason")
```

---

## Task 9: finalize_gold.py 双终态发布 + reconcile + guard 验证

**Files:**
- Create: `docs/phase9a/gold/gold_v1.json`
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
        gold = _load_json(PG / "gold_v1.json")
        assert receipt["manifest_sha256"] == hashlib.sha256(json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b"\n").hexdigest()
        assert "GOLD_RECEIPT" not in m["entries"]
        assert "gold_v1.json" in receipt["artifacts"]
        assert receipt["acquisition_verdict"] == gold["acquisition_verdict"]

    def test_reconcile_gold_exit_zero(self):
        proc = subprocess.run([sys.executable, str(PG / "reconcile_gold.py")], capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "FAIL" not in proc.stdout

    def test_guard_protects_gold_files(self):
        # 禁改守护：GOLD_RECEIPT 有效时保护 gold_v1.json + gold_manifest.json
        guard = _load_module("guard_data_artifacts", ".qoder/hooks/guard_data_artifacts.py")
        assert guard.load_gold_guard_config() is not None
        # 尝试修改 gold_v1.json 应被 hook 拦截（集成测试，非本单元测试）
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py::TestGoldSealed -q`
Expected: FAIL。

- [ ] **Step 3: 运行 finalize_gold.py（双终态发布）**

finalize_gold.py 内部：gold_validate.py 全过 → 生成 gold_v1.json（裁决后派生结果）→ 生成 GOLD_CLOSURE.md → staging → 校验 → 发布数据 → 冻结条目 → set_stage(sealed) → 最后发布 GOLD_RECEIPT.json（绑定 sealed manifest SHA + 版本化 artifact 集合）。

Run: `.venv/Scripts/python.exe docs/phase9a/gold/finalize_gold.py`
Expected: `finalize_gold: acquisition_verdict=GOLD_READY|GOLD_BLOCKED_ACQUISITION, manifest sealed, GOLD_RECEIPT published`。

- [ ] **Step 4: reconcile_gold exit 0 → 测试转绿 → Commit**

Run: `.venv/Scripts/python.exe docs/phase9a/gold/reconcile_gold.py`
Expected: exit 0 无 FAIL。
Run: `.venv/Scripts/python.exe -m pytest tests/test_phase9a_gold.py -q`
Expected: PASS。
```powershell
git add -- docs/phase9a/gold/gold_manifest.json docs/phase9a/gold/gold_v1.json docs/phase9a/gold/GOLD_CLOSURE.md docs/phase9a/gold/GOLD_RECEIPT.json docs/phase9a/gold/gold_acquisition_log.jsonl docs/phase9a/gold/gold_search_results.jsonl docs/phase9a/gold/gold_b_labels_r1.jsonl docs/phase9a/gold/gold_blind_unblind_map_r1.json docs/phase9a/gold/BLIND_PACKET_RECEIPT_r1.json docs/phase9a/gold/B_LABEL_RECEIPT_r1.json docs/phase9a/gold/gold_access_log.jsonl docs/phase9a/gold/gold_b_verification_labels.jsonl tests/test_phase9a_gold.py
# 按需追加 r2/r3 轮次产物（若实际产生）
git diff --cached --name-only
git commit -m "chore(phase9a-gold): sealed + GOLD_RECEIPT published (acquisition_verdict=...)"
```

- [ ] **Step 5: 禁改守护验证**

GOLD_RECEIPT 发布后，验证 guard_data_artifacts.py 的 load_gold_guard_config() 正确读取冻结配置并保护 gold_v1.json + gold_manifest.json（尝试修改应被 hook 拦截）。

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
