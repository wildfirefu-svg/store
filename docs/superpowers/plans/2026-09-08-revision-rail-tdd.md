# §5-R 修订溯源双轨契约 TDD 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现已批准设计 v29.3 的 §5-R 修订溯源双轨契约（工具链 T₀），并完成首批运行序列 R₀ → C₁(R25) → 候选验证 → V₁ → 默认复验。

**Architecture:** 全部修订验证经唯一入口 `evaluate_revision_rail(git_root, book, freeze, evidence)`（七阶段管线①-⑦，顺序即错误优先级）；解析/链哈希等纯函数入 `scripts/classic_artifacts.py`，git 读取、报告集成与 CLI 入 `scripts/generate_quality_report.py`；现行 `_e3_multiset_check` 并入 rail（rail ⑤ 输出即 E3 结果）。信任根为代码常量 `REVISION_ANCHOR_HEAD`/`TOOLCHAIN_REGISTRY_HEAD`，genesis 锚定，仅经 V/R 提交更新。

**Tech Stack:** Python 3.11+，git plumbing（rev-parse/cat-file/ls-tree/merge-base/rev-list），pytest（临时 linked worktree fixture），无新第三方依赖。

**权威设计：** `docs/superpowers/specs/2026-09-02-classic-texts-historical-provenance-exemption-design.md` v29.3（批准锚点见其 §0；提交 `2f5e267a82b0cdabf9b4e67ff890b12f6c6f9b57`）。本计划条款与设计冲突时以设计为准。

---

## 0. 前置事实（实现者必读）

- **分支**：`task/four-books-baseline`（基于 `03c02bb571dec9e2da1f7d503a292da229415d8f` == origin/main；设计批准提交 `2f5e267a82b0cdabf9b4e67ff890b12f6c6f9b57` 已在其上）。全程在此分支开发；T₀ = Part A 完成并通过复审的最终提交。
- **冻结字面量**（测试一律重算比对，不信任抄写）：
  - `BASELINE_COMMIT = "c5cff699fdb547bd9270acbebe1f485380848751"`（冻结基点）
  - `FIRST_BATCH_BASELINE = "03c02bb571dec9e2da1f7d503a292da229415d8f"`（首批门禁向量重跑点）
  - genesis 对象 `{"schema":"sanmingtonghui-revision-genesis-v1","book":"sanmingtonghui","freeze_base_commit":"c5cff699…751","b2_commit":"ccb833a46977c8274c0fb8c8c79c1b2f5d494c5e"}`；`GENESIS_SHA = sha256(_canonical(genesis).encode("utf-8"))`，按该公式重算（参考值 `da56658f061d2487877ef7819a18ef548fdb4eff5aa546509abe3a64141c48c0`，以测试重算为准）。
  - `SNAP = "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/b4e9be580dbecd3e233d3adbe163299f06c6ca5174309dc83e8f14433796aaa2"`（从 `scripts/verify_sanming_source_chain.py` 导入 `SNAP`，不重复定义）。
- **路径**（被跟踪工件，设计 5-R.1）：
  - 修订清单 `knowledge_base/classic_texts/sanmingtonghui/revision_manifest.json`
  - 验收锚 `docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/accepted_anchors.jsonl`
  - 工具链登记 `docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/toolchain_registry.jsonl`
- **可复用既有件**（`scripts/generate_classic_historical_freeze.py`）：`KINDS = ("all_rules","all_mcq","quarantine_rules","quarantine_mcq")`、`_canonical(obj)`、`_loads_strict`、`_book_rel(book,kind)`、`_record_entry(record)`（返回 `{"id":…,"sha256":…}`，sha256 = canonical 记录字节哈希）、`CheckError`。`classic_artifacts.py` 不 import freeze 模块（无环），新增 import 安全。
- **现有代码现状**：`generate_quality_report.py` 已有 B3 常量/`_e0_static_check`/`_e1_artifact_chain`/`_e2_recompute`/`_e3_multiset_check`/`evaluate_provenance_admissibility(book_dir, git_root)`/`generate_report`/`main(--archive-root)`；**无任何 revision 代码**（rg 验证为零命中）。
- **既有行为变更点（设计驱动，需同步改既有测试）**：
  1. E3 失败错误码 `EVIDENCE_STATIC_MISMATCH` → `REVISION_PARTITION_MISMATCH`（设计 5-R.5 ⑤；`tests/test_classic_distillation_quality_report.py::test_e3_multiset_negative_only_e3_fails` 的 3 处断言更新）。
  2. `evaluate_provenance_admissibility` 返回结构新增 `revision_state`/`revision_provenance_valid` 键。
- **错误码族**（设计 5-R，全部字面量冻结）：`REVISION_MANIFEST_MALFORMED`、`REVISION_CHAIN_STALE`、`REVISION_UNACCEPTED`、`REVISION_HISTORY_DRIFT`、`REVISION_PARTITION_MISMATCH`、`REVISION_SOURCE_UNVERIFIABLE`、`REVISION_BASELINE_INVALID`、`REVISION_TOOLCHAIN_INVALID`、`REVISION_UNSUPPORTED_STATE`。
- **退出码**（设计 5-R.9）：参数错误 2；source BLOCKED 3；修订链/E0-E2/B2 常量失败或退化 1；候选全项合格仅待批准 4；默认 overall_pass=true 0；兜底 1。
- **门禁纪律**：每任务先写失败测试（RED 运行不作可信证据），实现后聚焦测试全绿 + `ruff check scripts/<file> tests/<file>`；提交走 pre-commit（ruff E9/F821 + smoke）。测试超时 < 120s（CI pytest timeout），subprocess 用 bounded helper。

- **候选模式四参必选（P0-1 修复）**：`--pending-batch`/`--baseline-commit`/`--toolchain-commit`/`--archive-root` 缺任一 → exit 2（`REVISION_CLI_USAGE`）。`run_baseline` 用基线提交自带脚本 + `--archive-root` 运行，报告读取基线 worktree **本次新生成的 `QUALITY_REPORT.json`**（P0-3：先删基线跟踪的旧报告作为新生成守卫，运行后缺失即拒绝；CLI stdout 只是摘要，不得当 JSON 解析）。
- **测试 worktree 合成 T（P0-4 修复）**：fixture 从 HEAD 检出后，把主工作区当前待测脚本字节（`scripts/generate_quality_report.py`、`scripts/classic_artifacts.py`）复制入 worktree 提交为合成 T；R→C→V 测试全部建立在 T 之上——"实现后、提交前 GREEN"成立，不以先提交生产实现代替 TDD。
- **候选 exit-4 测试边界（P0-1/P0-2 round-3；round-4 接口对齐）**：`test_candidate_exit4_boundary` 用 importlib 从 fixture 脚本**隔离加载模块**（patch `gqr.ROOT` 不更新已导入常量/路径），显式 fake `run_baseline` 与 `verify_source_chain`（**真实接口 `(output_dict, exit_code)`**——status=="OK"、code=0，经 `_run_source_chain_check` 转换为 `{"status":"PASS","reason":None}`）；真实归档重放与完整链集成在 Part B Task 11。基线分类用 `_classify_baseline_rc` 联合退出码与报告形态——`first_batch` 由已验证锚链状态显式传入；rc=3 须**生产形态 BLOCKED 质量报告**（顶层 `status=="BLOCKED"` ∧ `source_e2e_status=="BLOCKED"` ∧ 逐书 `source_blocked_reason` ∈ §4.2 五值）才上抛 exit 3，verifier 三字段 CLI 输出对象不得冒充完整报告；其余归 `REVISION_BASELINE_INVALID`/exit 1。round-5：rc=3 判 BLOCKED 前置 `_report_structure_ok`**结构校验层**（顶层 15 键 + 四书键集精确 + 逐书必需键/类型/reason-status 耦合 + 聚合一致性；只验形态不验门禁通过——未知书名/缺书/缺必需字段/`source_e2e_pass=true` 与 BLOCKED 并存均判 INVALID）。
- **信任根常量字面量（P0-2 修复）**：`REVISION_ANCHOR_HEAD`/`TOOLCHAIN_REGISTRY_HEAD` 初始化为 `== GENESIS_SHA` 的确定 64-hex 字面量（`da56658f061d2487877ef7819a18ef548fdb4eff5aa546609abe3a64141c48c0`）、无行尾注释，fixture 替换器 `^NAME = "[0-9a-f]{64}"$` 才可命中；由 `test_trust_roots_start_at_genesis` 重算验证。
- **聚合文件格式（P0-1 修复）**：`all_rules.json` 是 JSON 数组（`KIND_FILENAME` 实测）；`all_mcq.jsonl`/`quarantine_*.jsonl` 是 JSONL。fixture 与 Part B 对数组一律解析数组、追加对象、序列化数组；rail ⑤⑥⑦ 一律经 `_parse_records`（按扩展名分派）——**JSONL 不得用 `_loads_strict` 直读**。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `scripts/classic_artifacts.py` | 修改 | 纯函数层：genesis/链哈希/JSONL 行解析/修订清单 schema 校验（无 git 依赖） |
| `scripts/generate_quality_report.py` | 修改 | 常量、rail 七阶段、状态矩阵、报告字段、退化比较、基线重跑、候选 CLI、V 结构验证、双常量比较、exit 状态机 |
| `tests/test_revision_rail.py` | 新建 | rail 全部 TDD 测试（含 linked-worktree fixture 与 5-R.12 矩阵） |
| `tests/test_classic_distillation_quality_report.py` | 修改 | 仅两处：E3 错误码断言迁移 + 报告集成新增字段断言（最小 diff） |

Part B（运行序列）另触及：registry/anchor/manifest 三个新工件 + `knowledge_base/classic_texts/sanmingtonghui/all_rules.json`（数组追加）/`all_mcq.jsonl`（JSONL 追加）（R25 批次）。

---

# Part A：工具链实现（TDD；全部合成数据，零真实内容变更）

## Task 1：genesis 与链哈希原语（classic_artifacts.py）

**Files:**
- Modify: `scripts/classic_artifacts.py`
- Test: `tests/test_revision_rail.py`（新建）

- [ ] **Step 1：写失败测试**

```python
"""§5-R 修订溯源双轨契约 TDD 测试（设计 v29.3 §5-R；权威条款见设计文档）。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.classic_artifacts import (
    GENESIS_SHA,
    REVISION_GENESIS,
    RevisionArtifactError,
    chain_head,
    parse_jsonl_line,
)
from scripts.generate_classic_historical_freeze import _canonical

ROOT = Path(__file__).resolve().parent.parent
ANCHOR_REL = ("docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/"
              "accepted_anchors.jsonl")
REGISTRY_REL = ("docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/"
                "toolchain_registry.jsonl")
MANIFEST_REL = "knowledge_base/classic_texts/sanmingtonghui/revision_manifest.json"


def _sha256(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


class TestGenesis:
    def test_genesis_object_frozen(self):
        assert REVISION_GENESIS == {
            "schema": "sanmingtonghui-revision-genesis-v1",
            "book": "sanmingtonghui",
            "freeze_base_commit":
                "c5cff699fdb547bd9270acbebe1f485380848751",
            "b2_commit": "ccb833a46977c8274c0fb8c8c79c1b2f5d494c5e",
        }

    def test_genesis_sha_recomputed(self):
        # 权威公式重算，不信任常量抄写（设计 5-R.3）
        expect = _sha256(_canonical(REVISION_GENESIS).encode("utf-8"))
        assert GENESIS_SHA == expect
        assert len(GENESIS_SHA) == 64


class TestChainHead:
    def _anchor(self, **over):
        a = {"batch_id": "B01", "content_commit": "1" * 40,
             "manifest_sha256_after": "2" * 64,
             "prev_anchor_sha256": GENESIS_SHA,
             "toolchain_commit": "3" * 40, "date": "2026-09-08"}
        a.update(over)
        return a

    def test_single_entry_chain_head(self):
        h1 = chain_head([self._anchor()], GENESIS_SHA)
        expect = _sha256(GENESIS_SHA.encode("ascii")
                         + _canonical(self._anchor()).encode("utf-8"))
        assert h1 == expect

    def test_multi_entry_chain_head(self):
        a1 = self._anchor()
        h1 = chain_head([a1], GENESIS_SHA)
        a2 = self._anchor(batch_id="B02", prev_anchor_sha256=h1)
        assert chain_head([a1, a2], GENESIS_SHA) == _sha256(
            h1.encode("ascii") + _canonical(a2).encode("utf-8"))

    def test_first_prev_must_be_genesis(self):
        with pytest.raises(RevisionArtifactError):
            chain_head([self._anchor(prev_anchor_sha256="0" * 64)], GENESIS_SHA)

    def test_prev_link_mismatch_rejected(self):
        a1 = self._anchor()
        a2 = self._anchor(batch_id="B02", prev_anchor_sha256="f" * 64)
        with pytest.raises(RevisionArtifactError):
            chain_head([a1, a2], GENESIS_SHA)


class TestParseJsonlLine:
    def _line(self, obj) -> bytes:
        return (_canonical(obj) + "\n").encode("utf-8")

    def test_canonical_line_accepted(self):
        obj = {"a": 1, "b": "中"}
        assert parse_jsonl_line(self._line(obj)) == obj

    def test_non_canonical_line_rejected(self):
        raw = (json.dumps({"b": "中", "a": 1}, ensure_ascii=False,
                          separators=(",", ":")) + "\n").encode("utf-8")  # 键序非排序
        with pytest.raises(RevisionArtifactError):
            parse_jsonl_line(raw)

    def test_duplicate_key_rejected(self):
        raw = b'{"a":1,"a":2}\n'
        with pytest.raises(RevisionArtifactError):
            parse_jsonl_line(raw)

    def test_crlf_rejected(self):
        obj = {"a": 1}
        raw = (_canonical(obj) + "\r\n").encode("utf-8")
        with pytest.raises(RevisionArtifactError):
            parse_jsonl_line(raw)
```

- [ ] **Step 2：跑测试确认失败**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: FAIL（`ImportError: cannot import name 'GENESIS_SHA'`）

- [ ] **Step 3：实现（classic_artifacts.py 末尾追加）**

```python
# ---------------------------------------------------------------------------
# §5-R 修订溯源双轨契约：纯函数原语（设计 v29.3 §5-R.2/5-R.3；无 git 依赖）
# ---------------------------------------------------------------------------
from scripts.generate_classic_historical_freeze import _canonical, _loads_strict  # noqa: E402

REVISION_GENESIS = {
    "schema": "sanmingtonghui-revision-genesis-v1",
    "book": "sanmingtonghui",
    "freeze_base_commit": "c5cff699fdb547bd9270acbebe1f485380848751",
    "b2_commit": "ccb833a46977c8274c0fb8c8c79c1b2f5d494c5e",
}
GENESIS_SHA = hashlib.sha256(
    _canonical(REVISION_GENESIS).encode("utf-8")).hexdigest()
EMPTY_BASELINE_MANIFEST = {
    "schema_version": "1.0", "book": "sanmingtonghui",
    "freeze_base_commit": REVISION_GENESIS["freeze_base_commit"],
    "batches": []}

REVISION_MANIFEST_TOP_FIELDS = frozenset(
    {"schema_version", "book", "freeze_base_commit", "batches"})
REVISION_BATCH_FIELDS = frozenset({"batch_id", "date", "author", "records"})
REVISION_RECORD_FIELDS = frozenset(
    {"kind", "id", "sha256", "source_chapter", "snapshot_path",
     "snapshot_sha256", "historical_basis"})
REVISION_ANCHOR_FIELDS = frozenset(
    {"batch_id", "content_commit", "manifest_sha256_after",
     "prev_anchor_sha256", "toolchain_commit", "date"})
REVISION_REGISTRY_FIELDS = frozenset(
    {"toolchain_commit", "date", "review_ref", "prev_registry_sha256"})


class RevisionArtifactError(ValueError):
    """修订工件解析/校验失败（fail-closed，由调用方映射稳定错误码）。"""


def parse_jsonl_line(raw: bytes) -> dict:
    """严格解析一行 JSONL 并做 canonical 行字节自检（设计 5-R.3）。

    行字节（去换行）必须 == _canonical(解析对象).encode("utf-8")；
    拒绝重复 JSON 键、CRLF、尾随内容、非对象。
    """
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if raw.endswith(b"\r"):
        raise RevisionArtifactError("CRLF line ending rejected")
    try:
        obj = _loads_strict(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - 统一转为稳定错误
        raise RevisionArtifactError(f"jsonl line malformed: {e}") from e
    if not isinstance(obj, dict):
        raise RevisionArtifactError("jsonl line not an object")
    if raw != _canonical(obj).encode("utf-8"):
        raise RevisionArtifactError("jsonl line not canonical bytes")
    return obj


def chain_head(entries: list[dict], genesis_sha: str, *,
               prev_field: str = "prev_anchor_sha256",
               fields: frozenset = REVISION_ANCHOR_FIELDS) -> str:
    """重算哈希链头：h_0 = genesis_sha；
    h_i = sha256(h_prev.encode("ascii") + _canonical(entry_i).encode("utf-8"))。

    逐条校验字段集（拒绝未知/缺字段）与 prev 链接（首条 prev == genesis_sha，
    其余 == 前条链头）；违者抛 RevisionArtifactError（设计 5-R.3）。
    """
    h = genesis_sha
    for i, e in enumerate(entries):
        if set(e) != set(fields):
            raise RevisionArtifactError(f"entry {i} fields != {sorted(fields)}")
        if e[prev_field] != h:
            raise RevisionArtifactError(f"entry {i} {prev_field} link mismatch")
        h = hashlib.sha256(
            h.encode("ascii") + _canonical(e).encode("utf-8")).hexdigest()
    return h
```

注意：`classic_artifacts.py` 头部需补 `import hashlib`（若未有）。

- [ ] **Step 4：跑测试确认通过**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: PASS（全部）

- [ ] **Step 5：ruff + 提交**

```powershell
python -m ruff check scripts/classic_artifacts.py tests/test_revision_rail.py
git add scripts/classic_artifacts.py tests/test_revision_rail.py
git commit -m "feat(revision-rail): genesis literal, chain-hash and strict JSONL primitives"
```

## Task 2：修订清单 schema 校验（classic_artifacts.py；rail ①② 的纯函数部分）

**Files:**
- Modify: `scripts/classic_artifacts.py`
- Test: `tests/test_revision_rail.py`

- [ ] **Step 1：写失败测试**

```python
from scripts.classic_artifacts import validate_revision_manifest

EMPTY_BASELINE_MANIFEST = {
    "schema_version": "1.0", "book": "sanmingtonghui",
    "freeze_base_commit": "c5cff699fdb547bd9270acbebe1f485380848751",
    "batches": []}


def _manifest_with(batch: dict) -> dict:
    return {**EMPTY_BASELINE_MANIFEST, "batches": [batch]}


def _record(**over) -> dict:
    r = {"kind": "rule", "id": "smth_t_001", "sha256": "a" * 64,
         "source_chapter": "卷二·论坐命宫", "snapshot_path":
         "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/"
         "b4e9be580dbecd3e233d3adbe163299f06c6ca5174309dc83e8f14433796aaa2"
         "/extracted/raw_025.txt",
         "snapshot_sha256": "b" * 64, "historical_basis": None}
    r.update(over)
    return r


class TestManifestSchema:
    def test_empty_baseline_literal_passes(self):
        validate_revision_manifest(EMPTY_BASELINE_MANIFEST)

    def test_top_field_add_rejected(self):
        m = {**EMPTY_BASELINE_MANIFEST, "extra": 1}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(m)

    def test_top_field_missing_rejected(self):
        m = {k: v for k, v in EMPTY_BASELINE_MANIFEST.items() if k != "book"}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(m)

    def test_wrong_book_rejected(self):
        m = {**EMPTY_BASELINE_MANIFEST, "book": "ditiansui"}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(m)

    def test_batch_unknown_field_rejected(self):
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "owner",
             "records": [], "x": 1}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

    @pytest.mark.parametrize("bad", [
        {"kind": "other"},                      # kind 枚举外
        {"sha256": "short"},                    # sha256 非 64-hex
        {"snapshot_path": "../escape.txt"},     # 路径逃逸
        {"snapshot_path": "raw_025.txt"},       # 根目录 raw 文件
        {"snapshot_sha256": "z" * 63},          # 非 64-hex
    ])
    def test_record_shapes_rejected(self, bad):
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "owner",
             "records": [_record(**bad)]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

    def test_record_unknown_field_rejected(self):
        rec = {**_record(), "unknown_field": 1}
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "owner",
             "records": [rec]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

    def test_duplicate_record_identity_rejected(self):
        rec = _record()
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "owner",
             "records": [rec, dict(rec)]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

    def test_duplicate_batch_id_rejected(self):
        b1 = {"batch_id": "B01", "date": "2026-09-08", "author": "o",
              "records": [_record()]}
        b2 = {"batch_id": "B01", "date": "2026-09-08", "author": "o",
              "records": []}
        m = {**EMPTY_BASELINE_MANIFEST, "batches": [b1, b2]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(m)

    def test_historical_basis_shape(self):
        hb = {"commit": "1" * 40, "path": "knowledge_base/classic_texts/"
               "sanmingtonghui/all_rules.json", "source_chapter": "卷二·论坐命宫",
               "record_content_sha256": "c" * 64, "match_count": 1}
        rec = _record(historical_basis=hb)
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "o",
             "records": [rec]}
        validate_revision_manifest(_manifest_with(b))
        bad = _record(historical_basis={**hb, "match_count": 2})
        b2 = {"batch_id": "B01", "date": "2026-09-08", "author": "o",
              "records": [bad]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b2))

    def test_batch_id_unhashable_rejected(self):
        """执行复审 P0-3：batch_id 非法类型（unhashable）→ 稳定
        RevisionArtifactError，不得 TypeError 冒泡。"""
        b = {"batch_id": [], "date": "2026-09-08", "author": "o",
             "records": []}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))
```

- [ ] **Step 2：跑测试确认失败**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: FAIL（`ImportError: validate_revision_manifest`）

- [ ] **Step 3：实现（classic_artifacts.py 追加）**

```python
_SNAP_PREFIX = ("knowledge_base/classic_texts/sanmingtonghui/"
                "formal/source_snapshots/")


def _is_hex(s: str, n: int) -> bool:
    return (isinstance(s, str) and len(s) == n
            and all(c in "0123456789abcdef" for c in s))


def _valid_snapshot_path(p: str) -> bool:
    """白名单：仅 <SNAP>/extracted/raw_{NNN:03d}.txt（设计 5-R.2）。"""
    if not isinstance(p, str) or not p.startswith(_SNAP_PREFIX):
        return False
    parts = p[len(_SNAP_PREFIX):].split("/")
    if len(parts) != 2 or parts[0] != "extracted":
        return False
    name = parts[1]
    return (len(name) == 11 and name.startswith("raw_")
            and name[4:7].isdigit() and name[7:] == ".txt")


def validate_revision_manifest(obj: object) -> None:
    """修订清单 schema 校验（rail ② 的纯函数部分；设计 5-R.2）。

    strict：顶层/批次/记录字段集缺一多一均拒绝；kind ∈ {rule,mcq}；
    sha256/snapshot_sha256 64-hex；snapshot_path 白名单；
    historical_basis 形态与 match_count==1；批内 (id,sha256) 重复拒绝；
    batch_id 全局不重复。不做 git 依赖校验（记录哈希重算、freeze 交集、
    源身份在 rail 内做）。
    """
    err = RevisionArtifactError
    if not isinstance(obj, dict):
        raise err("manifest not an object")
    if set(obj) != set(REVISION_MANIFEST_TOP_FIELDS):
        raise err(f"manifest top fields != {sorted(REVISION_MANIFEST_TOP_FIELDS)}")
    if obj["schema_version"] != "1.0":
        raise err("manifest schema_version != 1.0")
    if obj["book"] != "sanmingtonghui":
        raise err("manifest book != sanmingtonghui")
    if obj["freeze_base_commit"] != REVISION_GENESIS["freeze_base_commit"]:
        raise err("manifest freeze_base_commit mismatch")
    batches = obj["batches"]
    if not isinstance(batches, list):
        raise err("batches not a list")
    seen_batches, seen_ids = set(), set()
    for b in batches:
        if not isinstance(b, dict) or set(b) != set(REVISION_BATCH_FIELDS):
            raise err(f"batch fields != {sorted(REVISION_BATCH_FIELDS)}")
        # 执行复审 P0-3：先验批次标量字段类型（unhashable 值不得进集合操作）
        if not isinstance(b["batch_id"], str) or not b["batch_id"]:
            raise err("batch_id empty/non-string")
        if not isinstance(b["date"], str) or not b["date"]:
            raise err("batch date empty/non-string")
        if not isinstance(b["author"], str) or not b["author"]:
            raise err("batch author empty/non-string")
        if b["batch_id"] in seen_batches:
            raise err(f"duplicate batch_id {b['batch_id']!r}")
        seen_batches.add(b["batch_id"])
        if not isinstance(b["records"], list):
            raise err("batch records not a list")
        for r in b["records"]:
            if not isinstance(r, dict) or set(r) != set(REVISION_RECORD_FIELDS):
                raise err(f"record fields != {sorted(REVISION_RECORD_FIELDS)}")
            if r["kind"] not in ("rule", "mcq"):
                raise err(f"record kind {r['kind']!r} not in (rule, mcq)")
            if not isinstance(r["id"], str) or not r["id"]:
                raise err("record id empty/non-string")
            if not _is_hex(r["sha256"], 64):
                raise err("record sha256 not 64-hex")
            if not _valid_snapshot_path(r["snapshot_path"]):
                raise err(f"snapshot_path not whitelisted: {r['snapshot_path']!r}")
            if not _is_hex(r["snapshot_sha256"], 64):
                raise err("snapshot_sha256 not 64-hex")
            if not isinstance(r["source_chapter"], str) or not r["source_chapter"]:
                raise err("source_chapter empty")
            key = (r["id"], r["sha256"])
            if key in seen_ids:
                raise err(f"duplicate (id, sha256) in manifest: {key}")
            seen_ids.add(key)
            hb = r["historical_basis"]
            if hb is not None:
                if (not isinstance(hb, dict)
                        or set(hb) != {"commit", "path", "source_chapter",
                                       "record_content_sha256", "match_count"}
                        or not _is_hex(hb["commit"], 40)
                        or not isinstance(hb["path"], str) or not hb["path"]
                        or not isinstance(hb["source_chapter"], str)
                        or not _is_hex(hb["record_content_sha256"], 64)
                        or hb["match_count"] != 1):
                    raise err("historical_basis malformed / match_count != 1")
```

- [ ] **Step 4：跑测试确认通过 + ruff + 提交**

Run: `python -m pytest tests/test_revision_rail.py -q && python -m ruff check scripts/classic_artifacts.py tests/test_revision_rail.py`
Expected: PASS

```powershell
git add scripts/classic_artifacts.py tests/test_revision_rail.py
git commit -m "feat(revision-rail): strict revision manifest schema validation"
```

## Task 3：rail 核心 ①-⑤ + linked-worktree fixture（generate_quality_report.py）

**Files:**
- Modify: `scripts/generate_quality_report.py`
- Test: `tests/test_revision_rail.py`

**Fixture 设计（本任务落盘，后续任务复用）**：linked worktree（真实仓库 HEAD 挂临时分支至 tmp 目录）——自带真实 freeze/evidence/E/R/B1/B2/聚合，E0-E2 天然通过；测试在其上构造 R₀/C₁/V₁ 真实提交。清理用 `git worktree remove --force` + `branch -D`（try/finally，fixture yield/cleanup）。

- [ ] **Step 1：写失败测试（fixture + rail ①-⑤ 正负向）**

```python
# --- linked worktree fixture（5-R.12 端到端基底）-------------------------------
import re

import scripts.generate_quality_report as gqr


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8")


class RailWorktree:
    """隔离测试仓库（linked worktree + 临时分支）；退出时强制清理。

    从真实仓库 HEAD 检出（自带 freeze/evidence/E/R/B1/B2/聚合，E0-E2 天然
    通过），但 HEAD 看不到主工作区未提交的开发中代码——因此构造**合成 T 提交**：
    把主工作区当前待测脚本字节（scripts/generate_quality_report.py、
    scripts/classic_artifacts.py）复制入 worktree 并提交，R→C→V 全部建立在
    该 T 之上（P0-4 复审修复："实现后、提交前 GREEN"才成立，不以先提交生产
    实现代替 TDD）。
    """

    def __init__(self, tmp_path: Path):
        self.path = tmp_path / "wt"
        self.branch = f"rail-test-{uuid4().hex[:8]}"
        _git(ROOT, "worktree", "add", "-b", self.branch, str(self.path), "HEAD")
        self.sync_synthetic_t()

    def sync_synthetic_t(self) -> None:
        """复制主工作区当前待测脚本字节入 worktree；有差异才提交合成 T，
        无差异（代码已提交——干净 CI 命中）则保持 HEAD 为 T（P0-2：普通
        `git commit` 在无改动时会失败，须先查 `status --porcelain`）。"""
        for rel in ("scripts/generate_quality_report.py",
                    "scripts/classic_artifacts.py"):
            self.write(rel, (ROOT / rel).read_bytes())
        dirty = _git(self.path, "status", "--porcelain", "--",
                     "scripts/generate_quality_report.py",
                     "scripts/classic_artifacts.py").strip()
        if dirty:
            self.commit("T: synthetic toolchain (in-development working-tree bytes)")
        self.toolchain_commit = self.rev("HEAD")
        self.head0 = self.toolchain_commit

    def rev(self, rev: str) -> str:
        return _git(self.path, "rev-parse", rev).strip()

    def blob(self, rev: str, rel: str) -> bytes:
        r = subprocess.run(["git", "-C", str(self.path), "show", f"{rev}:{rel}"],
                           capture_output=True)
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
        return r.stdout

    def write(self, rel: str, data: bytes) -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def append_line(self, rel: str, line: bytes) -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("ab") as f:
            f.write(line)

    def replace_constant(self, name: str, value: str) -> None:
        """唯一替换脚本常量值（其余字节不动；V/R 提交形态）。"""
        rel = "scripts/generate_quality_report.py"
        src = (self.path / rel).read_bytes().decode("utf-8")
        new, n = re.subn(
            rf'^{name} = "[0-9a-f]{{64}}"$', f'{name} = "{value}"',
            src, count=1, flags=re.M)
        assert n == 1, f"constant {name} not found"
        self.write(rel, new.encode("utf-8"))

    def commit(self, msg: str) -> str:
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-m", msg, "--no-verify")
        return self.rev("HEAD")

    def cleanup(self) -> None:
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force",
                        str(self.path)], capture_output=True)
        subprocess.run(["git", "-C", str(ROOT), "branch", "-D", self.branch],
                       capture_output=True)


@pytest.fixture()
def rail_wt(tmp_path):
    wt = RailWorktree(tmp_path)
    yield wt
    wt.cleanup()


def _anchor_line(batch_id: str, content_commit: str, manifest_sha: str,
                 prev: str, toolchain: str) -> bytes:
    obj = {"batch_id": batch_id, "content_commit": content_commit,
           "manifest_sha256_after": manifest_sha, "prev_anchor_sha256": prev,
           "toolchain_commit": toolchain, "date": "2026-09-08"}
    return (_canonical(obj) + "\n").encode("utf-8")


def _registry_line(toolchain: str, prev: str, review_ref: str = "test") -> bytes:
    obj = {"toolchain_commit": toolchain, "date": "2026-09-08",
           "review_ref": review_ref, "prev_registry_sha256": prev}
    return (_canonical(obj) + "\n").encode("utf-8")


def _canonical_bytes(obj) -> bytes:
    return _canonical(obj).encode("utf-8")


def _freeze_of(wt: RailWorktree) -> dict:
    return json.loads(wt.blob("HEAD", gqr.FREEZE_REL))


def _evidence_of(wt: RailWorktree) -> dict:
    return json.loads(wt.blob("HEAD", gqr.EVIDENCE_REL))


def _mk_rule(id_: str, chapter: str, text: str) -> dict:
    return {"id": id_, "category": "格局", "subject": "测试", "condition": "测试",
            "rule": text, "original_text": text, "source_book": "三命通会",
            "source_chapter": chapter}


def _mk_mcq(id_: str, rule_id: str) -> dict:
    return {"id": id_, "question": "测试题干？", "options": {"A": "甲", "B": "乙",
            "C": "丙", "D": "丁"}, "answer": "A", "explanation": "测试",
            "source_rule_id": rule_id, "source_book": "三命通会",
            "source_chapter": "卷二·论坐命宫"}


SNAP_REL = ("knowledge_base/classic_texts/sanmingtonghui/formal/"
            "source_snapshots/b4e9be580dbecd3e233d3adbe163299f06c6ca517"
            "4309dc83e8f14433796aaa2")
RAW025_REL = SNAP_REL + "/extracted/raw_025.txt"


class TestRailCore:
    """rail ①-⑤：解析→schema→锚链→基线比较→分区等式（合成 B01 批次）。"""

    def _make_c1(self, wt: RailWorktree, batch_id: str = "B01",
                 rule_text: str = "测试修订规则") -> dict:
        """在 worktree 构造 C₁：聚合追加 1 rule + 1 mcq + manifest 批次。"""
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        mcq_rel = "knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl"
        snap_sha = _sha256(wt.blob("HEAD", RAW025_REL))
        # original_text 取该章原文去空白前 30 字（保证 ⑦ 子串命中）
        src_text = wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
        probe = re.sub(r"\s+", "", src_text)[:30]
        rule = _mk_rule("smth_t_001", "卷二·论坐命宫", rule_text)
        rule["original_text"] = probe
        mcq = _mk_mcq("smth_t_001_m1", "smth_t_001")
        from scripts.generate_classic_historical_freeze import _record_entry
        rec_rule = {"kind": "rule", "id": rule["id"],
                    "sha256": _record_entry(rule)["sha256"],
                    "source_chapter": "卷二·论坐命宫", "snapshot_path": RAW025_REL,
                    "snapshot_sha256": snap_sha, "historical_basis": None}
        rec_mcq = {"kind": "mcq", "id": mcq["id"],
                   "sha256": _record_entry(mcq)["sha256"],
                   "source_chapter": "卷二·论坐命宫", "snapshot_path": RAW025_REL,
                   "snapshot_sha256": snap_sha, "historical_basis": None}
        # P0-1：all_rules.json 是 JSON 数组（非 JSONL）——解析数组、追加
        # 对象、序列化数组；all_mcq.jsonl 才按 JSONL 追加。
        rules_arr = json.loads(wt.blob("HEAD", rules_rel).decode("utf-8"))
        rules_arr.append(rule)
        wt.write(rules_rel,
                 json.dumps(rules_arr, ensure_ascii=False).encode("utf-8"))
        wt.write(mcq_rel, wt.blob("HEAD", mcq_rel)
                 + (_canonical(mcq) + "\n").encode("utf-8"))
        manifest = {"schema_version": "1.0", "book": "sanmingtonghui",
                    "freeze_base_commit":
                        "c5cff699fdb547bd9270acbebe1f485380848751",
                    "batches": [{"batch_id": batch_id, "date": "2026-09-08",
                                 "author": "test",
                                 "records": [rec_rule, rec_mcq]}]}
        wt.write(MANIFEST_REL, _canonical_bytes(manifest) + b"\n")
        return manifest

    def test_rail_none_when_no_manifest(self, rail_wt):
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["revision_state"] == "NONE"
        assert res["ok"] is True  # 无修订：沿现行 E3 语义（HEAD==freeze）
        assert res["error_code"] is None

    def test_rail_candidate_unaccepted_default_mode(self, rail_wt):
        """默认模式遇未锚合法追加 → REVISION_UNACCEPTED（④）。"""
        self._make_c1(rail_wt)
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["ok"] is False
        assert res["error_code"] == "REVISION_UNACCEPTED"

    def test_rail_malformed_manifest(self, rail_wt):
        rail_wt.write(MANIFEST_REL, b'{"schema_version":"1.0",')
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_MANIFEST_MALFORMED"

    def test_rail_partition_mismatch_unmanifested_extra(self, rail_wt):
        """清单外新增（聚合加了记录、manifest 不列）→ ⑤ MISMATCH +
        unmanifested_extra 明细。"""
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        rule = _mk_rule("smth_t_002", "卷二·论坐命宫", "清单外记录")
        rules_arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        rules_arr.append(rule)
        rail_wt.write(rules_rel,
                      json.dumps(rules_arr, ensure_ascii=False).encode("utf-8"))
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_PARTITION_MISMATCH"
        assert res["partition_detail"]["unmanifested_extra"] >= 1

    def test_rail_legacy_mutated_detail(self, rail_wt):
        """freeze 内记录被改（改首条规则 category）→ ⑤ MISMATCH +
        legacy_mutated 明细。"""
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        arr[0] = {**arr[0], "category": "tampered"}
        rail_wt.write(rules_rel,
                      json.dumps(arr, ensure_ascii=False).encode("utf-8"))
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_PARTITION_MISMATCH"
        assert res["partition_detail"]["legacy_mutated"] >= 1

    def test_rail_other_book_manifest_rejected(self, rail_wt):
        """非锚书出现 manifest → REVISION_SOURCE_UNVERIFIABLE（5-R.0）。"""
        rail_wt.write("knowledge_base/classic_texts/ditiansui/revision_manifest.json",
                      _canonical_bytes(EMPTY_BASELINE_MANIFEST) + b"\n")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "ditiansui", _freeze_of(rail_wt), _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    def test_trust_roots_start_at_genesis(self):
        """P0-2：两信任根以确定 64-hex 字面量初始化且 == genesis_sha
        （测试重算验证；满足设计 5-R.6 首批路径的空链规范值）。"""
        assert gqr.REVISION_ANCHOR_HEAD == GENESIS_SHA
        assert gqr.TOOLCHAIN_REGISTRY_HEAD == GENESIS_SHA

    def test_fixture_no_diff_synthetic_t(self, rail_wt):
        """P0-2：T 已提交后再同步（字节无差异）→ 不产生新提交、T 不变
        （覆盖"代码已提交"的干净场景；普通 commit 在无改动时会失败）。"""
        before = rail_wt.toolchain_commit
        rail_wt.sync_synthetic_t()
        assert rail_wt.toolchain_commit == before
        assert rail_wt.rev("HEAD") == before

    def test_rail_absent_kind_added_record_mismatch(self, rail_wt):
        """执行复审 P0-1：冻结时缺席的 KIND（quarantine_mcq）在 HEAD 新增
        记录 → ⑤ MISMATCH（缺席 KIND 的 baseline Counter 为空而非忽略
        HEAD——不得沿用旧 E3 的 present 跳过语义）。"""
        qrel = ("knowledge_base/classic_texts/sanmingtonghui/"
                "quarantine_mcq.jsonl")
        mcq = _mk_mcq("smth_q_001", "smth_t_001")
        rail_wt.write(qrel, (_canonical(mcq) + "\n").encode("utf-8"))
        rail_wt.commit("absent-kind record added")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_PARTITION_MISMATCH"
        assert res["partition_detail"]["unmanifested_extra"] >= 1

    def test_rail_missing_anchor_nongenesis_constant_stale(self, rail_wt,
                                                            monkeypatch):
        """执行复审 P0-2：manifest 与锚文件均缺失 + 信任根常量非 genesis →
        CHAIN_STALE（缺失与空锚同样必须核对信任根，不得退回 NONE）。
        rail 读取运行中执行体的进程内常量（与评审内存注入复现同源）。"""
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", "f" * 64)
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_CHAIN_STALE"

    def test_rail_malformed_anchor_line_stale(self, rail_wt):
        """执行复审 P0-3：畸形锚行 → 解析异常映射 REVISION_CHAIN_STALE
        返回结构，不向上抛未处理异常。"""
        rail_wt.append_line(gqr.REVISION_ANCHOR_REL, b'{"bad":\n')
        rail_wt.commit("malformed anchor line")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_CHAIN_STALE"

    def test_rail_other_books_none_after_sanming_acceptance(self, rail_wt,
                                                             monkeypatch):
        """执行复审 P0：三命通会合法 C→V 落地后，其他三书不受锚链影响
        ——仍 NONE 且本书历史分区通过（不读三命通会锚、不套用其常量规则）；
        三命通会本身经 ①-⑦ 走到 ACCEPTED。V₁ 后执行体常量 == @HEAD 链头
        （monkeypatch 对齐进程内常量与 HEAD 脚本常量，模拟真实部署同源）。"""
        manifest = self._make_c1(rail_wt)
        c1 = rail_wt.commit("C1")
        anchor = _anchor_line("B01", c1, _sha256(_canonical_bytes(manifest)),
                              GENESIS_SHA, rail_wt.head0)
        rail_wt.append_line(gqr.REVISION_ANCHOR_REL, anchor)
        head = chain_head([json.loads(anchor.decode())], GENESIS_SHA)
        rail_wt.replace_constant("REVISION_ANCHOR_HEAD", head)
        rail_wt.commit("V1")
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", head)
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["revision_state"] == "ACCEPTED"
        assert res["ok"] is True
        for book in ("ditiansui", "qiongtongbaojian", "zipingzhenquan"):
            r = gqr.evaluate_revision_rail(
                rail_wt.path, book, _freeze_of(rail_wt), _evidence_of(rail_wt))
            assert r["revision_state"] == "NONE"
            assert r["ok"] is True and r["e3_ok"] is True

    def test_rail_double_corruption_reports_manifest_first(self, rail_wt):
        """执行复审 P1：manifest 与锚同时损坏 → 按冻结优先级报阶段①
        REVISION_MANIFEST_MALFORMED（锚解析不得抢在阶段①之前）。"""
        rail_wt.write(MANIFEST_REL, b'{"schema_version":"1.0",')
        rail_wt.append_line(gqr.REVISION_ANCHOR_REL, b'{"bad":\n')
        rail_wt.commit("double corruption")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_MANIFEST_MALFORMED"
```

- [ ] **Step 2：跑测试确认失败**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: FAIL（`AttributeError: ... no attribute 'evaluate_revision_rail'`）

- [ ] **Step 3：实现（generate_quality_report.py）**

常量区（`APPROVAL_B2_BY_BOOK` 之后；模块头 import 扩展）：

```python
# §5-R 修订溯源双轨契约（设计 v29.3；批准锚点见设计 §0）
from scripts.verify_sanming_source_chain import SNAP  # noqa: E402

# 空链规范值 == GENESIS_SHA 的确定 64-hex 字面量（设计 5-R.6 首批路径要求
# REVISION_ANCHOR_HEAD@HEAD == genesis_sha）。P0-2 复审：不得用裸名
# GENESIS_SHA 初始化——fixture 替换器只接受 `NAME = "<64位hex>"` 形态，
# 首次 R/V 常量替换才能命中；两行不得带行尾注释（保持替换器正则
# `^NAME = "[0-9a-f]{64}"$` 精确匹配）；字面量由 Task 3 Step 1 的
# test_trust_roots_start_at_genesis 重算验证。
REVISION_ANCHOR_HEAD = "da56658f061d2487877ef7819a18ef548fdb4eff5aa546609abe3a64141c48c0"
TOOLCHAIN_REGISTRY_HEAD = "da56658f061d2487877ef7819a18ef548fdb4eff5aa546609abe3a64141c48c0"
REVISION_ANCHOR_REL = ("docs/superpowers/plans/notes/approvals/revisions/"
                       "sanmingtonghui/accepted_anchors.jsonl")
REVISION_REGISTRY_REL = ("docs/superpowers/plans/notes/approvals/revisions/"
                         "sanmingtonghui/toolchain_registry.jsonl")
REVISION_MANIFEST_REL = ("knowledge_base/classic_texts/sanmingtonghui/"
                         "revision_manifest.json")
REVISION_ALLOWED_RED_ITEMS = {  # 允许红项上界（附录 A.3；仅 sanmingtonghui.G7）
    "sanmingtonghui": {"G7_chapter_complete.missing_count": 303},
}
```

rail 主体（新函数，置于 `evaluate_provenance_admissibility` 之前）：

```python
def _git_show_optional(git_root: Path, rel: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(git_root), "show", f"HEAD:{rel}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def _rail_manifest_bytes(git_root: Path) -> bytes | None:
    return _git_show_optional(git_root, REVISION_MANIFEST_REL)


def _rail_anchor_entries(git_root: Path) -> list[dict] | None:
    """@HEAD 锚文件条目；文件不存在 → None；存在（含零行）→ 条目列表。"""
    from scripts.classic_artifacts import RevisionArtifactError, parse_jsonl_line
    raw = _git_show_optional(git_root, REVISION_ANCHOR_REL)
    if raw is None:
        return None
    entries = []
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            raise RevisionArtifactError("blank anchor line")
        entries.append(parse_jsonl_line(line))
    return entries


def evaluate_revision_rail(git_root: Path, book: str,
                           freeze: dict, evidence: dict) -> dict:
    """§5-R.5 唯一执行入口：①-⑦ 管线，顺序即错误优先级，单次读取 HEAD。

    返回 {ok, revision_state, error_code, e3_ok, partition_detail?}。
    无 manifest 且无锚 → NONE（沿现行 E3 语义，⑤ 退化为 HEAD==freeze）。
    """
    from scripts.classic_artifacts import (
        GENESIS_SHA, RevisionArtifactError, chain_head,
        validate_revision_manifest)

    def _fail(code: str, **extra) -> dict:
        return {"ok": False, "revision_state": "FAILED", "error_code": code,
                "e3_ok": False, **extra}

    raw = None
    if book == "sanmingtonghui":
        raw = _rail_manifest_bytes(git_root)
    elif _git_show_optional(
            git_root,
            f"knowledge_base/classic_texts/{book}/revision_manifest.json"
            ) is not None:
        return _fail("REVISION_SOURCE_UNVERIFIABLE")

    if raw is None:
        # 执行复审 P0：锚文件与信任根常量仅属三命通会——其他书只做本书
        # 历史分区校验（合法 NONE），不读三命通会锚、不套用其常量规则。
        anchors = None
        if book == "sanmingtonghui":
            try:
                anchors = _rail_anchor_entries(git_root)
            except RevisionArtifactError:
                # 执行复审 P0-3：锚文件畸形行 → 稳定错误码，不抛未处理异常
                return _fail("REVISION_CHAIN_STALE")
            if anchors:  # manifest 抹除但锚存在 → 已验收修订被整体移除
                return _fail("REVISION_CHAIN_STALE")
        e3 = _partition_equation(git_root, book, freeze, manifest_recs=[])
        if not e3["ok"]:
            return _fail("REVISION_PARTITION_MISMATCH",
                         partition_detail=e3["detail"])
        # 执行复审 P0-2：缺失（None）与空（[]）同样必须核对信任根
        if (book == "sanmingtonghui" and not anchors
                and chain_head([], GENESIS_SHA) != REVISION_ANCHOR_HEAD):
            return _fail("REVISION_CHAIN_STALE")
        return {"ok": True, "revision_state": "NONE", "error_code": None,
                "e3_ok": True}

    # ① 解析（strict JSON；BOM/尾随内容拒绝）
    try:
        obj = _loads_strict(raw.decode("utf-8"))
    except Exception:
        return _fail("REVISION_MANIFEST_MALFORMED")
    # ② schema/记录身份/与 freeze 交集
    try:
        validate_revision_manifest(obj)
    except RevisionArtifactError:
        return _fail("REVISION_MANIFEST_MALFORMED")
    freeze_ids = set(_freeze_identities(freeze, book))
    for b in obj["batches"]:
        for r in b["records"]:
            if (r["id"], r["sha256"]) in freeze_ids:
                return _fail("REVISION_MANIFEST_MALFORMED",
                             reason="record double-listed with freeze")
    # ③ 锚链（执行复审 P1：锚解析在阶段①②之后，双重损坏按①报告；
    # 逐条链哈希 + 链头==常量@HEAD）
    try:
        anchors = _rail_anchor_entries(git_root)
    except RevisionArtifactError:
        return _fail("REVISION_CHAIN_STALE")
    try:
        head = chain_head(anchors or [], GENESIS_SHA)
    except RevisionArtifactError:
        return _fail("REVISION_CHAIN_STALE")
    if head != REVISION_ANCHOR_HEAD:
        return _fail("REVISION_CHAIN_STALE")
    # ④ HEAD manifest vs 已验收基线（默认模式）
    drift = _baseline_compare(git_root, obj, anchors or [])
    if drift is not None:
        return _fail(drift)
    # ⑤ 分区等式（全 KINDS；Counter 计数，禁 set）
    manifest_recs = [r for b in obj["batches"] for r in b["records"]]
    e3 = _partition_equation(git_root, book, freeze, manifest_recs)
    if not e3["ok"]:
        return _fail("REVISION_PARTITION_MISMATCH", partition_detail=e3["detail"])
    # ⑥⑦ 源身份 + 内容检查（Task 4 实现；本任务接线占位通过）
    src = _source_identity_and_content(git_root, book, evidence, manifest_recs)
    if src is not None:
        return _fail(src)
    return {"ok": True, "revision_state": "ACCEPTED", "error_code": None,
            "e3_ok": True}
```

辅助函数（同文件追加）：

```python
def _freeze_identities(freeze: dict, book: str) -> list[tuple[str, str]]:
    return [(rec["id"], rec["sha256"])
            for kind in KINDS
            for rec in freeze["books"][book][kind]["records"]]


def _partition_equation(git_root: Path, book: str, freeze: dict,
                        manifest_recs: list[dict]) -> dict:
    """⑤ Counter(HEAD) == Counter(freeze) + Counter(manifest)（全 KINDS）。

    三分类明细：legacy_mutated / unmanifested_extra / manifest_orphan。
    manifest_recs 为空时退化为现行 E3（HEAD == freeze）。
    """
    from collections import Counter
    kind_map = {"rule": "all_rules", "mcq": "all_mcq"}
    head_c, base_c, mani_c = Counter(), Counter(), Counter()
    for kind in KINDS:
        rel = _book_rel(book, kind)
        # 执行复审 P0-1：缺席 KIND 的 baseline Counter 为空而非忽略 HEAD——
        # freeze 无记录但 HEAD 新增文件仍须被检出（unmanifested_extra）。
        for rec in freeze["books"][book][kind]["records"]:
            base_c[(kind, rec["id"], rec["sha256"])] += 1
        data = _git_show_optional(git_root, rel)  # 文件缺失 → None → 空记录
        if data is None:
            continue
        try:
            # JSON 数组（all_rules.json）与 JSONL（*_mcq.jsonl 等）经
            # _parse_records 按扩展名分派；_loads_strict 直读 JSONL 会失败。
            records = _parse_records(data, kind)
        except Exception:
            return {"ok": False, "detail": {"parse_error": rel}}
        for rec in records:
            e = _record_entry(rec)
            head_c[(kind, e["id"], e["sha256"])] += 1
    for r in manifest_recs:
        mani_c[(kind_map[r["kind"]], r["id"], r["sha256"])] += 1
    if head_c == base_c + mani_c:
        return {"ok": True, "detail": {}}
    expected = base_c + mani_c
    detail = {"legacy_mutated": 0, "unmanifested_extra": 0, "manifest_orphan": 0}
    for key in set(head_c) | set(expected):
        h, e = head_c.get(key, 0), expected.get(key, 0)
        b, m = base_c.get(key, 0), mani_c.get(key, 0)
        if h > e:
            detail["unmanifested_extra"] += h - e
        elif h < e:
            missing = e - h
            from_base = min(b, missing)
            detail["legacy_mutated"] += from_base
            detail["manifest_orphan"] += missing - from_base
    return {"ok": False, "detail": detail}


def _baseline_compare(git_root: Path, head_manifest: dict,
                      anchors: list[dict]) -> str | None:
    """④ 默认模式（canonical 层比较）。返回错误码或 None（通过）。

    - 锚空 → 基线 = 空基线 manifest 字面量；
    - HEAD == 基线 → 通过；HEAD == 基线+1 全新批次 → UNACCEPTED；
    - HEAD 批次集 ⊂ 基线（删批）→ CHAIN_STALE；其余 → HISTORY_DRIFT。
    """
    from scripts.classic_artifacts import EMPTY_BASELINE_MANIFEST
    if anchors:
        c_oid = anchors[-1]["content_commit"]
        r = subprocess.run(["git", "-C", str(git_root), "show",
                            f"{c_oid}:{REVISION_MANIFEST_REL}"],
                           capture_output=True)
        if r.returncode != 0:
            return "REVISION_CHAIN_STALE"
        base = _loads_strict(r.stdout.decode("utf-8"))
    else:
        base = EMPTY_BASELINE_MANIFEST
    hb, bb = head_manifest["batches"], base["batches"]
    if _canonical(hb) == _canonical(bb):
        return None
    if (len(hb) == len(bb) + 1
            and _canonical(hb[:len(bb)]) == _canonical(bb)
            and hb[-1]["batch_id"] not in {b["batch_id"] for b in bb}):
        return "REVISION_UNACCEPTED"
    if {b["batch_id"] for b in hb} < {b["batch_id"] for b in bb}:
        return "REVISION_CHAIN_STALE"
    return "REVISION_HISTORY_DRIFT"


def _source_identity_and_content(git_root: Path, book: str, evidence: dict,
                                 manifest_recs: list[dict]) -> str | None:
    """⑥⑦ 占位（Task 4 实现完整锚定链）。"""
    return None
```

本任务**保留** `_e3_multiset_check` 原函数不删（Task 5 做接线替换与删除，避免本任务 diff 过大）。

- [ ] **Step 4：跑测试确认通过**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: PASS（空锚 + HEAD manifest 非空 → `_baseline_compare` 返回 UNACCEPTED，与用例一致）

- [ ] **Step 5：ruff + 提交**

```powershell
python -m ruff check scripts/generate_quality_report.py scripts/classic_artifacts.py tests/test_revision_rail.py
git add scripts/generate_quality_report.py scripts/classic_artifacts.py tests/test_revision_rail.py
git commit -m "feat(revision-rail): seven-phase pipeline core (parse/schema/anchor/baseline/partition)"
```

## Task 4：rail ⑥-⑦ 源身份锚定链 + 内容检查

**Files:**
- Modify: `scripts/generate_quality_report.py`
- Test: `tests/test_revision_rail.py`

- [ ] **Step 1：写失败测试**

```python
class TestRailSourceAndContent:
    def test_source_identity_recomputed(self, rail_wt):
        """⑥：篡改 raw_025.txt（聚合/manifest 不动）→ manifest 记录的
        snapshot_sha256 与 HEAD blob 不符 → SOURCE_UNVERIFIABLE。"""
        core = TestRailCore()
        core._make_c1(rail_wt)
        rail_wt.write(RAW025_REL, rail_wt.blob("HEAD", RAW025_REL) + "篡改".encode())
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    def test_source_manifest_oid_sha_split(self, rail_wt):
        """⑥-1/⑥-2：evidence 钉住的 manifest_blob_oid/manifest_file_sha256
        拦截三件套同步篡改——改 source_manifest.json 一个字节即不符。"""
        core = TestRailCore()
        core._make_c1(rail_wt)
        sm_rel = SNAP_REL + "/source_manifest.json"
        rail_wt.write(sm_rel, rail_wt.blob("HEAD", sm_rel) + b" ")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    def test_original_text_substring(self, rail_wt):
        """⑦：rule.original_text 去空白后非对应章子串 → 拒绝
        （记录 sha 按 HEAD 聚合真实记录重算，仅 ⑦ 失败）。"""
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        snap_sha = _sha256(rail_wt.blob("HEAD", RAW025_REL))
        rule = _mk_rule("smth_t_001", "卷二·论坐命宫", "正文")
        rule["original_text"] = "这段文字绝不出现在raw_025原文中XYZQ"
        mcq = _mk_mcq("smth_t_001_m1", "smth_t_001")
        from scripts.generate_classic_historical_freeze import _record_entry
        rules_arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        rules_arr.append(rule)
        rail_wt.write(rules_rel,
                      json.dumps(rules_arr, ensure_ascii=False).encode("utf-8"))
        mcq_rel = "knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl"
        rail_wt.write(mcq_rel, rail_wt.blob("HEAD", mcq_rel)
                      + (_canonical(mcq) + "\n").encode("utf-8"))
        manifest = {"schema_version": "1.0", "book": "sanmingtonghui",
                    "freeze_base_commit":
                        "c5cff699fdb547bd9270acbebe1f485380848751",
                    "batches": [{"batch_id": "B01", "date": "2026-09-08",
                                 "author": "test", "records": [
                        {"kind": "rule", "id": rule["id"],
                         "sha256": _record_entry(rule)["sha256"],
                         "source_chapter": "卷二·论坐命宫",
                         "snapshot_path": RAW025_REL,
                         "snapshot_sha256": snap_sha,
                         "historical_basis": None},
                        {"kind": "mcq", "id": mcq["id"],
                         "sha256": _record_entry(mcq)["sha256"],
                         "source_chapter": "卷二·论坐命宫",
                         "snapshot_path": RAW025_REL,
                         "snapshot_sha256": snap_sha,
                         "historical_basis": None}]}]}
        rail_wt.write(MANIFEST_REL, _canonical_bytes(manifest) + b"\n")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    def test_mcq_dangling_fk_rejected(self, rail_wt):
        """⑦：mcq.source_rule_id 悬空 → 拒绝（记录 sha 真实重算）。"""
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        mcq_rel = "knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl"
        snap_sha = _sha256(rail_wt.blob("HEAD", RAW025_REL))
        src_text = rail_wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
        probe = re.sub(r"\s+", "", src_text)[:30]
        rule = _mk_rule("smth_t_001", "卷二·论坐命宫", "规则")
        rule["original_text"] = probe
        mcq = _mk_mcq("smth_t_001_m1", "smth_nope")  # 悬空外键
        from scripts.generate_classic_historical_freeze import _record_entry
        rules_arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        rules_arr.append(rule)
        rail_wt.write(rules_rel,
                      json.dumps(rules_arr, ensure_ascii=False).encode("utf-8"))
        rail_wt.write(mcq_rel, rail_wt.blob("HEAD", mcq_rel)
                      + (_canonical(mcq) + "\n").encode("utf-8"))
        manifest = {"schema_version": "1.0", "book": "sanmingtonghui",
                    "freeze_base_commit":
                        "c5cff699fdb547bd9270acbebe1f485380848751",
                    "batches": [{"batch_id": "B01", "date": "2026-09-08",
                                 "author": "test", "records": [
                        {"kind": "rule", "id": rule["id"],
                         "sha256": _record_entry(rule)["sha256"],
                         "source_chapter": "卷二·论坐命宫",
                         "snapshot_path": RAW025_REL,
                         "snapshot_sha256": snap_sha,
                         "historical_basis": None},
                        {"kind": "mcq", "id": mcq["id"],
                         "sha256": _record_entry(mcq)["sha256"],
                         "source_chapter": "卷二·论坐命宫",
                         "snapshot_path": RAW025_REL,
                         "snapshot_sha256": snap_sha,
                         "historical_basis": None}]}]}
        rail_wt.write(MANIFEST_REL, _canonical_bytes(manifest) + b"\n")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"
```

- [ ] **Step 2：跑测试确认失败**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: FAIL（占位实现返回 None，四个负向用例不命中）

- [ ] **Step 3：实现（替换 `_source_identity_and_content` 占位）**

```python
_WS_RE = re.compile(r"\s+")


def _find_head_record(git_root: Path, book: str, rec: dict) -> dict | None:
    """按 (id, sha256) 在 HEAD 对应聚合中找回完整记录 dict。"""
    kind_map = {"rule": "all_rules", "mcq": "all_mcq"}
    kind = kind_map[rec["kind"]]
    data = _git_head_blob(git_root, _book_rel(book, kind))
    arr = _parse_records(data, kind)
    for r in arr:
        e = _record_entry(r)
        if e["id"] == rec["id"] and e["sha256"] == rec["sha256"]:
            return r
    return None


def _source_identity_and_content(git_root: Path, book: str, evidence: dict,
                                 manifest_recs: list[dict]) -> str | None:
    """⑥⑦ 源身份锚定链 + 内容检查（设计 5-R.8）。返回错误码或 None。

    ⑥ 锚点来自 evidence@HEAD.source_chain.{book}（E1 已验证双树一致）：
       ⑥-1 rev-parse HEAD:<SNAP>/source_manifest.json == manifest_blob_oid
       ⑥-2 sha256(blob 原始字节) == manifest_file_sha256
       逐章：sha256(HEAD:<SNAP>/extracted/raw_{NNN}.txt) ==
             source_manifest.chapters[NNN-1].extracted_text_sha256
    ⑦ 每条 manifest 记录：snapshot_path 与章序一致 ∧ snapshot_sha256 ==
       对应章 blob sha；rule.original_text 去空白 ⊆ 该章文本去空白；
       mcq 外键指向 HEAD 存在规则 ∧ G8 形态（options 含 ABCD ∧
       answer ∈ ABCD）。
    """
    sc = (evidence.get("source_chain") or {}).get(book)
    if not isinstance(sc, dict):
        return "REVISION_SOURCE_UNVERIFIABLE"
    oid = _git_rev_parse(git_root, f"HEAD:{SNAP}/source_manifest.json")
    if oid != sc["manifest_blob_oid"]:
        return "REVISION_SOURCE_UNVERIFIABLE"
    sm_bytes = _git_show_blob(git_root, "HEAD", f"{SNAP}/source_manifest.json")
    if hashlib.sha256(sm_bytes).hexdigest() != sc["manifest_file_sha256"]:
        return "REVISION_SOURCE_UNVERIFIABLE"
    sm = _loads_strict(sm_bytes.decode("utf-8"))
    chapters = sm["chapters"]  # 列表序 == 章序（NNN-1 索引）
    chap_blob: dict[str, tuple[int, bytes]] = {}
    for r in manifest_recs:
        nnn = next((i for i, c in enumerate(chapters, 1)
                    if c["title"] == r["source_chapter"]), None)
        if nnn is None:
            return "REVISION_SOURCE_UNVERIFIABLE"  # chapter_list 反解失败（错章）
        rel = f"{SNAP}/extracted/raw_{nnn:03d}.txt"
        if rel != r["snapshot_path"]:
            return "REVISION_SOURCE_UNVERIFIABLE"  # 路径与章不匹配
        if r["source_chapter"] not in chap_blob:
            blob = _git_show_blob(git_root, "HEAD", rel)
            if hashlib.sha256(blob).hexdigest() != \
                    chapters[nnn - 1]["extracted_text_sha256"]:
                return "REVISION_SOURCE_UNVERIFIABLE"
            chap_blob[r["source_chapter"]] = (nnn, blob)
        _, blob = chap_blob[r["source_chapter"]]
        if hashlib.sha256(blob).hexdigest() != r["snapshot_sha256"]:
            return "REVISION_SOURCE_UNVERIFIABLE"
    # ⑦ 内容检查
    head_rule_ids = {_record_entry(r)["id"] for r in _parse_records(
        _git_head_blob(git_root, _book_rel(book, "all_rules")), "all_rules")}
    for r in manifest_recs:
        rec = _find_head_record(git_root, book, r)
        if rec is None:
            return "REVISION_SOURCE_UNVERIFIABLE"
        _, blob = chap_blob[r["source_chapter"]]
        chap_ws = _WS_RE.sub("", blob.decode("utf-8", "replace"))
        if r["kind"] == "rule":
            if _WS_RE.sub("", rec.get("original_text", "")) not in chap_ws:
                return "REVISION_SOURCE_UNVERIFIABLE"
        else:
            if rec.get("source_rule_id") not in head_rule_ids:
                return "REVISION_SOURCE_UNVERIFIABLE"
            opts, ans = rec.get("options"), rec.get("answer")
            if (not isinstance(opts, dict) or not set("ABCD").issubset(opts)
                    or ans not in "ABCD"):
                return "REVISION_SOURCE_UNVERIFIABLE"
    return None
```

（`SNAP` 已在 Task 3 导入；`re` 已在文件头导入。）

- [ ] **Step 4：跑测试确认通过 + ruff + 提交**

```powershell
python -m pytest tests/test_revision_rail.py -q && python -m ruff check scripts/generate_quality_report.py tests/test_revision_rail.py
git add scripts/generate_quality_report.py tests/test_revision_rail.py
git commit -m "feat(revision-rail): evidence-anchored source identity and content checks"
```

## Task 5：E3 并入 rail + 状态矩阵 + 报告字段 + 默认模式退出码

**Files:**
- Modify: `scripts/generate_quality_report.py`
- Modify: `tests/test_classic_distillation_quality_report.py`（最小 diff：错误码断言迁移）
- Test: `tests/test_revision_rail.py`

- [ ] **Step 1：写失败测试**

```python
class TestRailIntegration:
    def test_admissibility_consumes_rail_single_call(self, rail_wt, monkeypatch):
        """evaluate_provenance_admissibility 只调 rail 一次、消费其结果；
        E3_ok = rail ⑤ 结果。"""
        calls = []
        real = gqr.evaluate_revision_rail

        def spy(git_root, book, freeze, evidence):
            calls.append(book)
            return real(git_root, book, freeze, evidence)

        monkeypatch.setattr(gqr, "evaluate_revision_rail", spy)
        adm = gqr.evaluate_provenance_admissibility(
            rail_wt.path / "knowledge_base" / "classic_texts" / "sanmingtonghui",
            rail_wt.path)
        assert calls == ["sanmingtonghui"]
        assert adm["revision_state"] == "NONE"
        assert adm["revision_provenance_valid"] is False  # NONE != ACCEPTED
        assert adm["E3_ok"] is True

    def test_matrix_valid_book_with_manifest_unsupported(self, rail_wt):
        """5-R.10 VALID×manifest 存在 → UNSUPPORTED_STATE（唯一行为修改）。
        构造 VALID：为 ditiansui 写与其磁盘工件一致的 provenance.json。"""
        book_dir = rail_wt.path / "knowledge_base" / "classic_texts" / "ditiansui"
        # 复用 _setup_passing_book 的 provenance 构造逻辑（复制其写入
        # provenance.json 的代码段，file_shas 与磁盘工件真实一致），
        # 落在 worktree 后 git add 使 E1 读到（或 monkeypatch 状态判定输入）
        ...  # 按 _setup_passing_book 源码 53-128 行的 provenance 写入段复制
        rail_wt.write("knowledge_base/classic_texts/ditiansui/revision_manifest.json",
                      _canonical_bytes(EMPTY_BASELINE_MANIFEST) + b"\n")
        adm = gqr.evaluate_provenance_admissibility(book_dir, rail_wt.path)
        assert adm["provenance_state"] == "VALID"
        assert adm["exemption_error_code"] == "REVISION_UNSUPPORTED_STATE"
        assert adm["provenance_admissible"] is False

    def test_matrix_missing_with_anchors_manifest_wiped(self, rail_wt):
        """MISSING × manifest 不存在 × 有已验收锚 → CHAIN_STALE。"""
        core = TestRailCore()
        manifest = core._make_c1(rail_wt)
        c1 = rail_wt.commit("C1: synthetic batch B01")
        anchor = _anchor_line("B01", c1,
                              _sha256(_canonical_bytes(manifest)), GENESIS_SHA,
                              rail_wt.head0)
        rail_wt.append_line(ANCHOR_REL, anchor)
        new_head = chain_head([json.loads(anchor.decode())], GENESIS_SHA)
        rail_wt.replace_constant("REVISION_ANCHOR_HEAD", new_head)
        rail_wt.commit("V1")
        _git(rail_wt.path, "rm", MANIFEST_REL)
        rail_wt.commit("wipe manifest")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_CHAIN_STALE"

    def test_default_mode_accepted_flow(self, rail_wt):
        """完整默认模式正循环：C₁+V₁ 后 ACCEPTED、E0-E2 过、admissible。"""
        core = TestRailCore()
        manifest = core._make_c1(rail_wt)
        c1 = rail_wt.commit("C1")
        anchor = _anchor_line("B01", c1,
                              _sha256(_canonical_bytes(manifest)), GENESIS_SHA,
                              rail_wt.head0)
        rail_wt.append_line(ANCHOR_REL, anchor)
        new_head = chain_head([json.loads(anchor.decode())], GENESIS_SHA)
        rail_wt.replace_constant("REVISION_ANCHOR_HEAD", new_head)
        rail_wt.commit("V1")
        adm = gqr.evaluate_provenance_admissibility(
            rail_wt.path / "knowledge_base" / "classic_texts" / "sanmingtonghui",
            rail_wt.path)
        assert adm["revision_state"] == "ACCEPTED"
        assert adm["revision_provenance_valid"] is True
        assert adm["provenance_admissible"] is True
        assert adm["E0_ok"] and adm["E1_ok"] and adm["E2_ok"] and adm["E3_ok"]
```

> 实现注记（VALID 用例）：`tests/test_classic_distillation_quality_report.py::_setup_passing_book`（53-128 行）已含"写 provenance.json 且 file_shas 与磁盘一致"的完整构造；将其 provenance 写入段提取为测试内 helper（复制粘贴进 `test_revision_rail.py`，勿跨文件 import 私有函数），目标目录改为 worktree 内 ditiansui。

既有测试更新（`tests/test_classic_distillation_quality_report.py`，`test_e3_multiset_negative_only_e3_fails`）：

```diff
-    assert adm["exemption_error_code"] == "EVIDENCE_STATIC_MISMATCH"
+    assert adm["exemption_error_code"] == "REVISION_PARTITION_MISMATCH"
```

- [ ] **Step 2：跑测试确认失败**

Run: `python -m pytest tests/test_revision_rail.py tests/test_classic_distillation_quality_report.py -q`
Expected: FAIL（integration 用例 RED；E3 断言迁移用例在接线前仍返回旧码，同为 RED）

- [ ] **Step 3：实现**

1. `evaluate_provenance_admissibility`：
   - VALID 分支前置：manifest 存在（任一形态，`_git_show_optional`）→ `REVISION_UNSUPPORTED_STATE`、`provenance_admissible=false`（不进 E1）。
   - MISSING 分支：原 `_e3_multiset_check(git_root, freeze)` 调用替换为 `rail = evaluate_revision_rail(git_root, book, freeze, evidence)`（evidence 已在该函数内取得；book 名取自 book_dir）；`E3_ok = rail["e3_ok"]`；错误码取 `rail["error_code"]`（沿既有 `exemption_error_code` 写出路径）；返回结构新增 `"revision_state": rail["revision_state"]`、`"revision_provenance_valid": rail["revision_state"] == "ACCEPTED"`。
2. 删除 `_e3_multiset_check`（其逻辑已被 `_partition_equation` 取代；既有直接引用该函数的测试一并迁移到 rail 入口——rg 确认仅一处引用链）。
3. `generate_report` 逐书 entry 增加 `revision_state`/`revision_provenance_valid` 两键。
4. 顶层退出码：`REVISION_*` 失败已由 `provenance_admissible=false` → `overall_pass=false` → exit 1 覆盖（无需独立分支）；fail-closed 错误码经 `exemption_error_code` 透出。

- [ ] **Step 4：跑测试确认通过（含既有文件全量）**

Run: `python -m pytest tests/test_revision_rail.py tests/test_classic_distillation_quality_report.py -q`
Expected: PASS（全量）

- [ ] **Step 5：ruff + 提交**

```powershell
python -m ruff check scripts/generate_quality_report.py tests/
git add scripts/generate_quality_report.py tests/test_revision_rail.py tests/test_classic_distillation_quality_report.py
git commit -m "feat(revision-rail): absorb E3 into rail, state matrix and report fields"
```

## Task 6：REPORT_FIELD_SCHEMA + 基线重跑引擎（合格基线/退化比较）

**Files:**
- Modify: `scripts/generate_quality_report.py`
- Test: `tests/test_revision_rail.py`

- [ ] **Step 1：写失败测试**

```python
class TestFieldSchema:
    def test_report_field_schema_matches_appendix(self):
        """内嵌表与附录 A 逐字段一致（schema_version/字段名/类型/方向/上限）。"""
        s = gqr.REPORT_FIELD_SCHEMA
        assert s["schema_version"] == "1.0"
        top = {f["name"] for f in s["top_level"]}
        assert {"status", "overall_pass", "revision_state",
                "revision_provenance_valid", "approval_b2_constant_valid",
                "validator_ran_live"} <= top
        g7 = [f for f in s["book_gate_details"]
              if f["name"] == "G7_chapter_complete.missing_count"][0]
        assert g7["type"] == "int" and g7["direction"] == "increase_bad"
        assert g7["upper_bound"]["sanmingtonghui"] == 303
        g6i = [f for f in s["book_gate_details"]
               if f["name"] == "G6_answer_dist.invalid_answers"][0]
        assert g6i["pass_value"] == 0

    def test_process_stage_fields_exempt_from_degradation(self):
        """流程阶段字段退出通用退化比较（v29.2 P0）：候选模式合法推进
        ACCEPTED/true → PENDING_ACCEPTANCE/false 不判退化。"""
        cmp = gqr.compare_gate_fields
        assert cmp(
            {"revision_state": "ACCEPTED", "revision_provenance_valid": True},
            {"revision_state": "PENDING_ACCEPTANCE",
             "revision_provenance_valid": False}, mode="candidate") == []

    def test_degradation_detected(self):
        cmp = gqr.compare_gate_fields
        bad = cmp(
            {"books": {"x": {"gates": {"G3_schema": True}}}},
            {"books": {"x": {"gates": {"G3_schema": False}}}}, mode="candidate")
        assert bad == ["x.G3_schema: PASS->FAIL"]

    def test_allowed_red_improvement_accepted_cap_enforced(self):
        cmp = gqr.compare_gate_fields
        base = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 303}}}}}
        improved = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 302}}}}}
        assert cmp(base, improved, mode="candidate") == []
        worse = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 304}}}}}
        assert cmp(base, worse, mode="candidate") == [
            "sanmingtonghui.G7_chapter_complete.missing_count: 304>303"]

    def test_b_minus_n_field_removed_rejected(self):
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"gates": {"G3_schema": True}}}}
        cand = {"books": {"x": {"gates": {}}}}  # 旧有门禁字段消失
        assert cmp(base, cand, mode="candidate") == ["x.G3_schema: removed"]


_BOOK_META = {
    "ditiansui": "滴天髓",
    "zipingzhenquan": "子平真诠",
    "qiongtongbaojian": "穷通宝鉴",
    "sanmingtonghui": "三命通会",
}
_BOOK_GATE_KEYS = (
    "G1_rule_id_unique", "G2_mcq_id_unique", "G3_schema",
    "G4_source_rule_id", "G5_traceability", "G6_answer_dist",
    "G7_chapter_complete", "G8_mcq_well_formed", "G9_content_dedup")


def _passing_book(book: str) -> dict:
    """单书全绿形态：九门布尔全 True + 九门 gate_details 齐备 + 豁免链全过。"""
    return {
        "name": _BOOK_META[book],
        "dir": book,
        "all_gates_pass": True,
        "gates": {g: True for g in _BOOK_GATE_KEYS},
        "gate_details": {
            "G1_rule_id_unique": {"total": 1, "unique": 1, "duplicates": 0,
                                  "pass": True},
            "G2_mcq_id_unique": {"total": 4, "unique": 4, "duplicates": 0,
                                 "pass": True},
            "G3_schema": {"bad_rules": 0, "bad_mcq": 0, "parse_errors": 0,
                          "pass": True},
            "G4_source_rule_id": {"total_refs": 4, "bad": 0,
                                  "ambiguous_rule_ids": 0, "pass": True},
            "G5_traceability": {"total": 1, "untraceable": 0, "rate": 1.0,
                                "pass": True},
            # P0-4：G6 分布须与生产语义一致——A=100% 会被判越界 FAIL；
            # 用四字母各 25%（∈[0.18,0.32]），与 G2.total/G4.total_refs=4 同步。
            "G6_answer_dist": {"dist_pct": {"A": 0.25, "B": 0.25,
                                            "C": 0.25, "D": 0.25},
                               "invalid_answers": 0, "out_of_band": [],
                               "pass": True},
            "G7_chapter_complete": {"expected": 1, "done": 1, "missing": [],
                                    "missing_count": 0, "extra": [],
                                    "extra_count": 0, "pass": True},
            "G8_mcq_well_formed": {"malformed": 0, "pass": True},
            "G9_content_dedup": {"rule_text_duplicate_groups": 0,
                                 "rule_text_duplicate_count": 0,
                                 "rule_text_duplicate_samples": {},
                                 "mcq_question_duplicates": 0, "pass": True},
        },
        "provenance_state": "MISSING",
        "provenance_missing": True,
        "provenance_ok": False,
        "historical_exemption_valid": True,
        "provenance_admissible": True,
        "exemption_error_code": None,
        "exemption_stages": {"E0_ok": True, "E1_ok": True,
                             "E2_ok": True, "E3_ok": True},
        "source_e2e_status": "FAIL" if book != "sanmingtonghui" else "PASS",
        "source_blocked_reason": None,
        "end_to_end_provenance": False,
    }


def _baseline_report_fixture(first_batch: bool = True) -> dict:
    """03c02bb 时点真实形态的**四书完整合格**基线报告（键集/字段以
    03c02bb 自带脚本 `generate_report` 重跑产出实测为准——该时点跟踪的
    QUALITY_REPORT.json 为旧脚本产物，重跑前被新生成守卫删除，不作
    判据；值合成）。

    合格形态（设计 5-R.8）：rc==1 时 status=FAIL ∧ 失败项 ⊆ 允许红项
    （仅 sanmingtonghui.G7 missing_count=303，附录 A.3 上限）；其余全绿；
    三书 source_e2e=FAIL（S 口径）、sanmingtonghui=PASS；E0-E2 全过；
    approval_b2_constant_valid=true；validator_ran_live=true。
    首批例外：无修订字段；first_batch=False 时追加
    revision_state=ACCEPTED ∧ revision_provenance_valid=true。
    """
    books = {b: _passing_book(b) for b in _BOOK_META}
    books["sanmingtonghui"]["all_gates_pass"] = False
    books["sanmingtonghui"]["gates"]["G7_chapter_complete"] = False
    books["sanmingtonghui"]["gate_details"]["G7_chapter_complete"] = {
        "expected": 383, "done": 80, "missing": [], "missing_count": 303,
        "extra": [], "extra_count": 0, "pass": False}
    rep = {
        "generated_at": "2026-09-07T11:04:08",
        "known_limitations": [],
        "validator": "scripts/validate_classic_distillation.py",
        "validator_code_sha256": "0" * 64,
        "validator_ran_live": True,
        "books": books,
        "remediation_pass": False,
        "end_to_end_pass": False,
        "content_gates_pass": False,       # sanmingtonghui G7 红项
        "provenance_admissible_all": True,
        "approval_b2_constant_valid": True,
        "source_e2e_status": "FAIL",       # 三书 S 口径（生成器 §7 聚合必有此键，round-4）
        "source_e2e_pass": False,
        "overall_pass": False,
        "status": "FAIL",
    }
    if not first_batch:
        rep["revision_state"] = "ACCEPTED"
        rep["revision_provenance_valid"] = True
    return rep


def _blocked_report_fixture(reason: str = "archive_root_missing") -> dict:
    """round-4 P0-1：生产形态 source-BLOCKED 质量报告。run_baseline 读取
    的是完整 QUALITY_REPORT.json——生成器 §7 顶层状态机：任一书
    source_e2e_status=BLOCKED → 顶层 source_e2e_status=BLOCKED ∧
    source_e2e_pass=False ∧ status=BLOCKED ∧ overall_pass=False（exit 3）；
    reason 在逐书 source_blocked_reason，不在顶层。"""
    rep = _baseline_report_fixture()
    sm = rep["books"]["sanmingtonghui"]
    sm["source_e2e_status"] = "BLOCKED"
    sm["source_blocked_reason"] = reason
    rep["source_e2e_status"] = "BLOCKED"
    rep["source_e2e_pass"] = False
    rep["status"] = "BLOCKED"
    rep["overall_pass"] = False
    return rep


class TestBaselineQualification:
    def test_first_batch_qualified_fail_report(self):
        assert gqr._qualified_baseline_report(
            1, _baseline_report_fixture(), first_batch=True) is True

    def test_first_batch_allowed_red_improved_still_qualified(self):
        """允许红项改善为 PASS（G7 全过）→ 仍合格（改善向下不设限）。"""
        rep = _baseline_report_fixture()
        sm = rep["books"]["sanmingtonghui"]
        sm["all_gates_pass"] = True
        sm["gates"]["G7_chapter_complete"] = True
        sm["gate_details"]["G7_chapter_complete"] = {
            "expected": 383, "done": 383, "missing": [], "missing_count": 0,
            "extra": [], "extra_count": 0, "pass": True}
        rep["content_gates_pass"] = True
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is True

    def test_first_batch_rc7_rejected(self):
        assert gqr._qualified_baseline_report(
            7, _baseline_report_fixture(), first_batch=True) is False

    def test_baseline_out_of_allowed_fail_rejected(self):
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gates"]["G3_schema"] = False
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False

    def test_missing_book_rejected(self):
        """缺书 → 不合格（四书齐备为合格条件④）。"""
        rep = _baseline_report_fixture()
        del rep["books"]["ditiansui"]
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False

    def test_incomplete_gate_details_rejected(self):
        """gate_details 缺门 → 不合格（九门齐备为合格条件④）。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"] = {
            "G7_chapter_complete": rep["books"]["sanmingtonghui"]
            ["gate_details"]["G7_chapter_complete"]}
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False

    def test_gate_detail_contradicts_bool_rejected(self):
        """P0-4：明细失败却声明 PASS（G6 out_of_band 非空但 pass=True）→ 拒绝
        （合格条件④：布尔与明细推导一致）。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"]["G6_answer_dist"] = {
            "dist_pct": {"A": 1.0}, "invalid_answers": 0,
            "out_of_band": ["A"], "pass": True}   # 明细自相矛盾
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False

    def test_baseline_stale_report_not_accepted(self, rail_wt, monkeypatch):
        """P0-3：基线预置合格旧报告 + 本次 rc=1 且未写出 → 拒绝
        （新生成守卫：旧报告先删、运行后缺失即证明未产出）。"""
        rep_path = (rail_wt.path / "knowledge_base" / "classic_texts"
                    / "QUALITY_REPORT.json")
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        rep_path.write_text(json.dumps(_baseline_report_fixture()),
                            encoding="utf-8")
        base = rail_wt.commit("baseline-with-stale-report")
        monkeypatch.setattr(gqr, "_run_report_in_worktree",
                            lambda tmp, ar: (1, b""))
        rc, rep = gqr.run_baseline(base, rail_wt.path, rail_wt.path,
                                   first_batch=True)
        assert (rc, rep) == (1, {})
        assert gqr._qualified_baseline_report(rc, rep, first_batch=True) is False

    def test_non_first_batch_requires_accepted_fields(self):
        rep = _baseline_report_fixture(first_batch=False)
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=False) is True
        rep2 = _baseline_report_fixture()          # 缺两修订字段 → 不合格
        assert gqr._qualified_baseline_report(
            1, rep2, first_batch=False) is False
        rep3 = _baseline_report_fixture()          # 有 state 缺 valid → 不合格
        rep3["revision_state"] = "ACCEPTED"
        assert gqr._qualified_baseline_report(
            1, rep3, first_batch=False) is False

    def test_rc_status_inconsistency_rejected(self):
        """完整合格 stdout + 异常退出码 / rc 与状态不一致 → 拒绝。"""
        rep = _baseline_report_fixture()
        rep["overall_pass"] = True
        rep["status"] = "PASS"
        assert gqr._qualified_baseline_report(
            7, rep, first_batch=True) is False
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False  # rc=1 与 PASS 状态不一致

    def test_classify_first_batch_context_paired(self):
        """round-4 P0-3：同一份缺修订字段的报告——first_batch=True 判
        QUALIFIED、first_batch=False 判 INVALID；首批上下文由调用方按已
        验证锚链状态显式传入，不从报告缺字段推断。"""
        rep = _baseline_report_fixture()   # 缺 revision_state/revision_provenance_valid
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "QUALIFIED"
        assert gqr._classify_baseline_rc(1, rep, first_batch=False) == "INVALID"

    def test_baseline_rc3_with_missing_report_invalid(self):
        """P0-2：rc=3 但报告缺失（{}）→ 不是 source BLOCKED，判 INVALID。"""
        assert gqr._classify_baseline_rc(3, {}, first_batch=True) == "INVALID"

    def test_baseline_rc3_plain_fail_report_invalid(self):
        """P0-2：rc=3 但报告是普通 FAIL 形态 → 判 INVALID（不能当 BLOCKED）。"""
        assert gqr._classify_baseline_rc(
            3, _baseline_report_fixture(), first_batch=True) == "INVALID"

    def test_baseline_rc3_verifier_shaped_object_invalid(self):
        """round-4 P0-1：verifier CLI 三字段对象 {schema_version,status,reason}
        是 source verifier 输出形态，不是 QUALITY_REPORT.json——run_baseline
        读的是完整质量报告（reason 在逐书 source_blocked_reason），不得冒充。"""
        rep = {"schema_version": "1.0", "status": "BLOCKED",
               "reason": "archive_root_missing"}
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_blocked_report_classified(self):
        """round-4 P0-1：rc=3 ∧ 生产形态 BLOCKED 质量报告（顶层 BLOCKED +
        sanmingtonghui source_e2e_status=BLOCKED + 五值 reason）→ "BLOCKED"。"""
        assert gqr._classify_baseline_rc(
            3, _blocked_report_fixture(), first_batch=True) == "BLOCKED"

    def test_baseline_rc3_blocked_bad_reason_invalid(self):
        """round-4 P0-1：BLOCKED 形态但逐书 reason 非五值 → 判 INVALID。"""
        assert gqr._classify_baseline_rc(
            3, _blocked_report_fixture("BOGUS"), first_batch=True) == "INVALID"

    def test_baseline_rc3_blocked_no_blocked_book_invalid(self):
        """round-4 P0-1：顶层标 BLOCKED 但无任何书 source_e2e_status=BLOCKED
        → 判 INVALID（顶层聚合与逐书状态必须一致）。"""
        rep = _blocked_report_fixture()
        sm = rep["books"]["sanmingtonghui"]
        sm["source_e2e_status"] = "PASS"
        sm["source_blocked_reason"] = None

    def test_baseline_rc3_unknown_book_invalid(self):
        """round-5 P0：报告含未知书名（ghost）→ 结构层拒绝，判 INVALID。"""
        rep = _blocked_report_fixture()
        rep["books"]["ghost"] = rep["books"]["sanmingtonghui"]
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_missing_book_invalid(self):
        """round-5 P0：缺书（四书键集不齐）→ 结构层拒绝，判 INVALID。"""
        rep = _blocked_report_fixture()
        del rep["books"]["ditiansui"]
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_missing_required_field_invalid(self):
        """round-5 P0：顶层缺必需字段（source_e2e_pass）→ 结构层拒绝。"""
        rep = _blocked_report_fixture()
        del rep["source_e2e_pass"]
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_e2e_pass_contradiction_invalid(self):
        """round-5 P0：source_e2e_pass=true 与顶层 BLOCKED 矛盾 → INVALID。"""
        rep = _blocked_report_fixture()
        rep["source_e2e_pass"] = True
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"
```

- [ ] **Step 2：跑测试确认失败**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: FAIL（`REPORT_FIELD_SCHEMA`/`compare_gate_fields`/`_qualified_baseline_report` 不存在）

- [ ] **Step 3：实现**

`REPORT_FIELD_SCHEMA`（与附录 A 同构的机器可读表；**字段全集以设计 §14 附录 A 为权威转录源**——A.1 顶层 9 字段、A.2 门禁布尔 9、A.3 计数全字段（含 G6 `invalid_answers`/`out_of_band`、`dist_pct` 合法域 [0,1] 与通过区间 [0.18,0.32]、G7 规范化集合语义、分母标注）、A.4 枚举（含 `exemption_error_code` 五值、BLOCKED reason 五值、候选可接纳值）；`process_stage_fields = ("revision_state","revision_provenance_valid")`）：

```python
REPORT_FIELD_SCHEMA = {
    "schema_version": "1.0",
    "process_stage_fields": ("revision_state", "revision_provenance_valid"),
    "non_gate_fields": (
        "generated_at", "validator_code_sha256", "remediation_pass",
        "end_to_end_pass"),  # 附录 A.0：随内容/运行合法变化，不参与劣化比较
    "top_level": [
        {"name": "status", "type": "enum",
         "values": ["PASS", "FAIL", "BLOCKED"], "candidate_accept": ["FAIL"]},
        {"name": "overall_pass", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [False]},
        # … A.1 其余字段同构转录（content_gates_pass / provenance_admissible_all /
        #   approval_b2_constant_valid / source_e2e_pass / validator_ran_live /
        #   revision_state（enum，候选仅 PENDING_ACCEPTANCE，流程字段）/
        #   revision_provenance_valid（bool，流程字段））
    ],
    "book_gates": [  # A.2：九门布尔，方向 non_allowed_pass_to_fail_bad
        {"name": g, "type": "bool", "direction": "pass_to_fail_bad"}
        for g in ("G1_rule_id_unique", "G2_mcq_id_unique", "G3_schema",
                  "G4_source_rule_id", "G5_traceability", "G6_answer_dist",
                  "G7_chapter_complete", "G8_mcq_well_formed", "G9_content_dedup")
    ],
    "book_gate_details": [
        {"name": "G6_answer_dist.invalid_answers", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G6_answer_dist.out_of_band", "type": "list",
         "direction": "nonempty_bad", "pass_value": []},
        # … A.3 其余字段同构转录；G7_chapter_complete.missing_count 含
        #   upper_bound={"sanmingtonghui": 303}
    ],
}
```

`compare_gate_fields(baseline: dict, candidate: dict, *, mode: str) -> list[str]`：
1. 按 `REPORT_FIELD_SCHEMA` 键集做三分类：B∩N 退化比较（布尔 true→false 拒；计数按 direction；枚举不劣化）；N−B 按 `candidate_accept`/`upper_bound`/枚举可接纳值；B−N 一律拒绝（`<field>: removed`）。
2. `process_stage_fields` 与 `non_gate_fields` 跳过（流程阶段字段按运行模式校验，由 exit-4 判定承担）。
3. 返回违规清单（空 = 零退化）。

`_classify_baseline_rc(rc: int, report: dict, *, first_batch: bool) -> str`（P0-2 复审修复；round-4 P0-1/P0-3 + round-5 P0：按**真实 QUALITY_REPORT.json 形态**联合分类 + 首批上下文显式传入 + **结构校验层前置**——`run_baseline` 读的是完整质量报告而非 source verifier CLI 输出，reason 位于逐书 `source_blocked_reason`；`first_batch` 由调用方按已验证锚链状态计算，不从报告缺字段推断）：
- rc==3 ∧ `_report_structure_ok(report)` ∧ 顶层 `status=="BLOCKED"` ∧ `source_e2e_status=="BLOCKED"` ∧ `overall_pass==False` ∧ 存在书 k 使 `books[k]["source_e2e_status"]=="BLOCKED"` 且其 `source_blocked_reason` ∈ §4.2 五值（`verifier_identity_mismatch`/`archive_root_missing`/`archive_missing`/`archive_sha_mismatch`/`archive_size_mismatch`）→ `"BLOCKED"`（调用方上抛 exit 3，stderr `SOURCE_CHAIN_BLOCKED:<reason>`，reason 取该书 `source_blocked_reason`）；
- rc∈{0,1} → 交 `_qualified_baseline_report(rc, report, first_batch=first_batch)`：合格 → `"QUALIFIED"`，否则 → `"INVALID"`；
- 其余任何组合——rc==3 但报告缺失（`{}`）/JSON 畸形/**verifier 三字段对象（非质量报告形态，不得冒充）**/结构层不过（**未知书名/缺书/缺必需字段或类型不符/聚合矛盾（含 `source_e2e_pass=true` 与 BLOCKED 并存）**）/普通 FAIL 报告、未知 rc、rc 与状态不一致 → `"INVALID"`（`REVISION_BASELINE_INVALID` / exit 1）。

`_report_structure_ok(report: dict) -> bool`（round-5 P0 新增**报告结构校验层**；键集判据以 03c02bb 自带脚本 `generate_report` 重跑产出实测为准（与 HEAD 生成器同构；该时点跟踪的旧 QUALITY_REPORT.json 为旧脚本产物，重跑前被新生成守卫删除，不作判据）。**只验形态不验门禁通过**——红门/红计数/红 source 不拒，否则合法 BLOCKED 基线被误拒）：
- **顶层 15 键齐备且类型**：`generated_at`/`validator` str；`validator_code_sha256` 64-hex str；`validator_ran_live`/`remediation_pass`/`end_to_end_pass`/`content_gates_pass`/`provenance_admissible_all`/`approval_b2_constant_valid`/`source_e2e_pass`/`overall_pass` bool；`known_limitations` list；`source_e2e_status`/`status` ∈ {PASS,FAIL,BLOCKED}。
- **`books` 键集精确 == 四书**（sanmingtonghui/ditiansui/qiongtongbaojian/zipingzhenquan）——未知书名、缺书、多书一律 False。
- **逐书 15 键齐备且类型**：`name` str ∧ `dir` == 键名；`all_gates_pass`/`provenance_missing`/`provenance_ok`/`historical_exemption_valid`/`provenance_admissible`/`end_to_end_provenance` bool；`gates` 九门键集、值全 bool；`gate_details` 九门键集、值 dict；`exemption_stages` 含 `E0_ok`/`E1_ok`/`E2_ok`/`E3_ok` 且全 bool；`exemption_error_code` str|None；`provenance_state` str；`source_e2e_status` ∈ {PASS,FAIL,BLOCKED}；`source_blocked_reason` ∈ 五值 ∪ {None} 且 **BLOCKED ⇒ reason 为五值之一、PASS/FAIL ⇒ reason is None**（`_run_source_chain_check` 实测耦合）。
- **聚合一致性（生产 §7 实测）**：顶层 `source_e2e_status` == 逐书聚合（任一书 BLOCKED → BLOCKED；否则任一 FAIL → FAIL；否则 PASS）；`source_e2e_pass` == (`source_e2e_status`=="PASS")；任一书 BLOCKED ⇒ `status`=="BLOCKED" ∧ `overall_pass`==False；无 BLOCKED ⇒ `status`==("PASS" if `overall_pass` else "FAIL")；`overall_pass` == (`content_gates_pass` ∧ `provenance_admissible_all` ∧ `source_e2e_pass` ∧ `approval_b2_constant_valid`)。

`_qualified_baseline_report(rc: int, report: dict, *, first_batch: bool) -> bool`（设计 5-R.8 定义；P0-3 复审后按四书完整形态校验）：
- **只接收 rc∈{0,1}**（rc==3 由 `_classify_baseline_rc` 先行联合分类，本函数遇 rc==3/7 等一律 False）。
- rc∈{0,1}：①⑤ 非首批须 `revision_state=="ACCEPTED"` ∧ `revision_provenance_valid==true`（**两者齐备**，缺任一不判合格）；首批例外：两修订字段缺失不判不合格；② E0/E1/E2（`exemption_stages` 三键 true）；③ `approval_b2_constant_valid==true`；④ `validator_ran_live==true` ∧ **四书精确齐备**（`books` 键集 == 四书）∧ 逐书 `gates` 九键 ∧ `gate_details` 九门齐备 ∧ **`gates` 布尔与 `gate_details` 推导一致**（`_gate_consistent`，P0-4：G1/G2 pass == duplicates==0；G3 == bad_rules/bad_mcq/parse_errors 全 0；G4 == bad==0 ∧ ambiguous==0；G5 == untraceable==0；G6 == out_of_band 空 ∧ invalid_answers==0；G7 == missing_count==0 ∧ extra_count==0；G8 == malformed==0；G9 == 两重复计数==0——明细失败却声明 PASS → 拒绝）。rc==0 须 `status=="PASS" ∧ overall_pass==true`；rc==1 须 `status=="FAIL"` ∧ 失败项 ⊆ 允许红项（sanmingtonghui.G7）。rc 与状态不一致 → False。

`_gate_consistent(gates: dict, gate_details: dict) -> bool`：逐门按 A.3 推导规则核对 `gates[g]` == 推导结果（判据见 `_qualified_baseline_report` 条件④）；任一门不一致 → False。

`_run_report_in_worktree(tmp: Path, archive_root: Path) -> tuple[int, bytes]`：在基线 worktree 内运行报告 CLI（真实 subprocess，返回 (rc, stdout)；测试可 monkeypatch 注入 rc/不写文件形态）。
`run_baseline(baseline_commit: str, git_root: Path, archive_root: Path, *, first_batch: bool) -> tuple[int, dict]`（P0-1/P0-3 复审修复；round-4 P0-3：`first_batch` 由 `_candidate_mode` 首批路径判定产出并显式传入）：
1. `git worktree add --detach <tmp> <baseline_commit>`（`--detach`，不占分支）。
2. **新生成守卫（P0-3）**：删除 `<tmp>/knowledge_base/classic_texts/QUALITY_REPORT.json`（基线仓库已跟踪该文件——若进程在写报告前失败，旧 FAIL 报告会被误当本次输出）；删除前断言存在、删除后断言不存在，此后该文件必须由本次运行重新生成。
3. 运行 `_run_report_in_worktree(tmp, archive_root)`（基线提交自带脚本 + `--archive-root`，cwd=tmp——**不得修改历史脚本来迎合计划**；`--archive-root` 必传，缺失 → sanmingtonghui source BLOCKED → exit 3）。
4. **本次生成校验**：运行后 `<tmp>/knowledge_base/classic_texts/QUALITY_REPORT.json` 必须存在——旧报告已删、文件缺失即证明本次未产出 → `(rc, {})`，`_qualified_baseline_report` 拒绝（不会被误收）；存在则读取为 report（CLI stdout 只是摘要，不得当 JSON 解析）。
5. 联合核验退出码与报告：`(rc, report)` 交 `_classify_baseline_rc(rc, report, first_batch=first_batch)`（含 rc 与状态一致性；BLOCKED/INVALID/QUALIFIED 三态由调用方 `_candidate_mode` 映射退出码）。
6. finally 清理 worktree（`git worktree remove --force <tmp>`）。

- [ ] **Step 4：跑测试确认通过 + ruff + 提交**

```powershell
python -m pytest tests/test_revision_rail.py -q && python -m ruff check scripts/generate_quality_report.py tests/test_revision_rail.py
git add scripts/generate_quality_report.py tests/test_revision_rail.py
git commit -m "feat(revision-rail): field schema table, degradation compare and baseline rerun engine"
```

## Task 7：候选模式 CLI + 入口前置核验 + V 结构验证 + 双常量矩阵

**Files:**
- Modify: `scripts/generate_quality_report.py`
- Test: `tests/test_revision_rail.py`

- [ ] **Step 1：写失败测试**

```python
def _load_report_module(wt: RailWorktree):
    """P0-1：从 fixture 磁盘脚本经 importlib **隔离加载**报告模块。
    patch 已导入模块的 ROOT 不会同步 `TOOLCHAIN_REGISTRY_HEAD`/`BASE`/
    `SCRIPTS_DIR`（导入时定值）——R₀ 替换后的登记链头与旧模块常量不符会被
    入口前置核验提前拒绝；隔离加载使 ROOT、BASE 与两信任根常量全部取
    fixture 态。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"gqr_rail_test_{uuid4().hex[:8]}",
        wt.path / "scripts" / "generate_quality_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCandidateCli:
    FIRST = "03c02bb571dec9e2da1f7d503a292da229415d8f"

    def _cli(self, wt, *args):
        r = subprocess.run(
            [sys.executable,
             str(wt.path / "scripts" / "generate_quality_report.py"), *args],
            capture_output=True, cwd=str(wt.path), timeout=100)
        return (r.returncode, r.stdout.decode("utf-8", "replace"),
                r.stderr.decode("utf-8", "replace"))

    def _r0(self, wt) -> str:
        line = _registry_line(wt.head0, GENESIS_SHA)
        wt.append_line(REGISTRY_REL, line)
        from scripts.classic_artifacts import (
            REVISION_REGISTRY_FIELDS, chain_head as _ch)
        h = _ch([json.loads(line.decode())], GENESIS_SHA,
                prev_field="prev_registry_sha256",
                fields=REVISION_REGISTRY_FIELDS)
        wt.replace_constant("TOOLCHAIN_REGISTRY_HEAD", h)
        return wt.commit("R0: register T0")

    def test_missing_args_exit2(self, rail_wt):
        rc, _, _ = self._cli(rail_wt, "--pending-batch", "B01")
        assert rc == 2

    def test_first_batch_wrong_baseline_exit2(self, rail_wt):
        self._r0(rail_wt)
        rc, _, _ = self._cli(rail_wt, "--pending-batch", "B01",
                             "--baseline-commit", "0" * 40,
                             "--toolchain-commit", rail_wt.head0,
                             "--archive-root", str(rail_wt.path))
        assert rc == 2

    def test_non_first_batch_first_baseline_exit2(self, rail_wt):
        """非首批（有已验收锚）传 03c02bb → exit 2（错配反向）。
        P0-5：先建登记 R₀——否则 T 准入先失败（TOOLCHAIN_INVALID），
        到不了基线错配的 exit 2 分支。"""
        self._r0(rail_wt)
        core = TestRailCore()
        manifest = core._make_c1(rail_wt)
        c1 = rail_wt.commit("C1")
        rail_wt.append_line(ANCHOR_REL, _anchor_line(
            "B01", c1, _sha256(_canonical_bytes(manifest)), GENESIS_SHA,
            rail_wt.head0))
        from scripts.classic_artifacts import chain_head as _ch
        rail_wt.replace_constant(
            "REVISION_ANCHOR_HEAD",
            _ch([json.loads(_anchor_line(
                "B01", c1, _sha256(_canonical_bytes(manifest)), GENESIS_SHA,
                rail_wt.head0).decode())], GENESIS_SHA))
        rail_wt.commit("V1")
        rc, _, _ = self._cli(rail_wt, "--pending-batch", "B02",
                             "--baseline-commit", self.FIRST,
                             "--toolchain-commit", rail_wt.head0,
                             "--archive-root", str(rail_wt.path))
        assert rc == 2

    def test_toolchain_not_registered_exit1(self, rail_wt):
        rc, _, err = self._cli(rail_wt, "--pending-batch", "B01",
                               "--baseline-commit", self.FIRST,
                               "--toolchain-commit", rail_wt.head0,
                               "--archive-root", str(rail_wt.path))
        assert rc == 1 and "REVISION_TOOLCHAIN_INVALID" in err

    def test_disk_tamper_exit1(self, rail_wt):
        """磁盘工具链脚本未提交篡改（仅换行差异）→ TOOLCHAIN_INVALID。"""
        self._r0(rail_wt)
        rel = "scripts/generate_quality_report.py"
        src = (rail_wt.path / rel).read_bytes()
        (rail_wt.path / rel).write_bytes(src.replace(b"\n", b"\r\n", 1))
        rc, _, err = self._cli(rail_wt, "--pending-batch", "B01",
                               "--baseline-commit", self.FIRST,
                               "--toolchain-commit", rail_wt.head0,
                               "--archive-root", str(rail_wt.path))
        assert rc == 1 and "REVISION_TOOLCHAIN_INVALID" in err
        # 注：toolchain 传已登记的 T（head0）——若传未登记 R0 会先在 T 准入
        # 失败，无法单独命中磁盘篡改分支；P0-4 后 head0 == 合成 T。

    def test_candidate_exit4_boundary(self, rail_wt, monkeypatch, capsys):
        """候选 exit 4 边界测试（P0-5/P0-1 round-3）：R₀ → C₁ → exit 4。

        边界声明：**隔离模块加载**（`_load_report_module` 从 fixture 磁盘
        脚本 importlib 加载——patch `gqr.ROOT` 不更新已导入的
        `TOOLCHAIN_REGISTRY_HEAD`/`BASE`/`SCRIPTS_DIR`，隔离加载后 ROOT
        与两信任根常量全为 fixture 态，R₀ 替换的登记链头才与新模块常量
        一致，入口前置核验不提前拒绝）。fakes：`run_baseline`（基线 rc=1
        合格 FAIL，签名含 first_batch）与 `verify_source_chain`（真实接口
        `(output_dict, exit_code)`——status=="OK"、code=0；`--archive-root`
        不提供真实归档，必须 fake；经 `_run_source_chain_check` 转换为
        `{"status":"PASS","reason":None}` 供 §7 聚合消费）。**真实归档重放 + 完整链集成（真实 source/G1-G9/退出码
        联合）在 Part B Task 11 执行**——本测试只证明候选边界（T 准入/执行
        来源/首批基线/rail 候选分支/基线联合分类/退化比较/exit 4）在隔离
        模块下闭合，不替代集成。"""
        self._r0(rail_wt)
        TestRailCore()._make_c1(rail_wt)
        rail_wt.commit("C1")
        mod = _load_report_module(rail_wt)         # P0-1：隔离加载
        monkeypatch.setattr(mod, "run_baseline",
                            lambda bc, gr, ar, first_batch=True: (
                                1, _baseline_report_fixture()))
        monkeypatch.setattr(
            mod, "verify_source_chain",
            # round-4 P0-2：真实接口 (output_dict, exit_code)——
            # verify_sanming_source_chain.verify_source_chain 的 OK 输出
            # （status=="OK"、code=0；生成器 _run_source_chain_check 解包后
            # code==0 ∧ status!=BLOCKED → {"status":"PASS","reason":None}）。
            # 单键 dict 会被 out, code = ... 解包成两个键名字符串致崩溃。
            lambda *a, **k: ({"schema_version": "1.0", "status": "OK",
                              "chapters_expected": 303, "c1_pass": 303,
                              "c2_pass": 303, "c3_pass": 303,
                              "failures": []}, 0))
        rc = mod.main(["--pending-batch", "B01", "--baseline-commit",
                       self.FIRST, "--toolchain-commit", rail_wt.head0,
                       "--archive-root", str(rail_wt.path)])
        out = capsys.readouterr().out
        assert rc == 4
        rep = json.loads(out)
        assert rep["books"]["sanmingtonghui"]["revision_state"] == \
            "PENDING_ACCEPTANCE"
```

> 注记（P0-1/P0-5 round-3 落实为代码；round-4 对齐 fake 接口）：`test_candidate_exit4_boundary` 为**隔离模块驱动的边界测试**（上方代码）——`_load_report_module` 从 fixture 磁盘脚本 importlib 加载（P0-1：patch `gqr.ROOT` 不更新已导入的 `TOOLCHAIN_REGISTRY_HEAD`/`BASE`/`SCRIPTS_DIR`，隔离加载后全为 fixture 态）；fakes 为 `run_baseline`（签名 `(bc, gr, ar, first_batch)`）与 `verify_source_chain`（真实接口 `(output_dict, exit_code)`：status=="OK"、code=0，经 `_run_source_chain_check` 转 `{"status":"PASS","reason":None}`——`--archive-root` 无真实归档，必须 fake）；stdout 经 `capsys` 捕获。真实归档 + 完整链集成在 Part B Task 11。其余 CLI 用例（exit 2 / TOOLCHAIN_INVALID）保持子进程形态（`_cli` 以 worktree 磁盘脚本运行）。

```python
class TestVStructure:
    def _v1(self, wt) -> str:
        core = TestRailCore()
        manifest = core._make_c1(wt)
        c1 = wt.commit("C1")
        anchor = _anchor_line("B01", c1, _sha256(_canonical_bytes(manifest)),
                              GENESIS_SHA, wt.head0)
        wt.append_line(ANCHOR_REL, anchor)
        wt.replace_constant("REVISION_ANCHOR_HEAD", chain_head(
            [json.loads(anchor.decode())], GENESIS_SHA))
        return wt.commit("V1")

    def test_v1_structure_valid(self, rail_wt):
        v1 = self._v1(rail_wt)
        assert gqr.validate_v_structure(rail_wt.path, v1) is None

    def test_v_merge_commit_rejected(self, rail_wt):
        self._v1(rail_wt)
        _git(rail_wt.path, "checkout", "-b", "side", "HEAD~1")
        rail_wt.write("README.side", b"x")
        rail_wt.commit("side")
        _git(rail_wt.path, "checkout", "-")
        _git(rail_wt.path, "merge", "-m", "merge", "side")
        v2 = rail_wt.rev("HEAD")
        assert gqr.validate_v_structure(
            rail_wt.path, v2) == "REVISION_CHAIN_STALE"

    def test_v_extra_diff_path_rejected(self, rail_wt):
        """diff 含第三路径 → 拒绝。"""
        self._v1(rail_wt)
        rail_wt.write("docs/superpowers/plans/notes/approvals/revisions/"
                      "sanmingtonghui/extra.txt", b"x")
        v2 = rail_wt.commit("V-with-extra")
        assert gqr.validate_v_structure(
            rail_wt.path, v2) == "REVISION_CHAIN_STALE"
```

- [ ] **Step 2：跑测试确认失败**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: FAIL（CLI 候选参数与 `validate_v_structure` 均不存在）

- [ ] **Step 3：实现**

1. `main(argv)`：新增三参数 `--pending-batch`/`--baseline-commit`/`--toolchain-commit`；候选模式下 `--archive-root` 亦必选（基线重跑需其驱动归档重放，缺档即 BLOCKED）；任候选参数出现而四参不齐 → stderr 单行 `REVISION_CLI_USAGE`、exit 2；四齐 → `return _candidate_mode(ROOT, batch, baseline, toolchain, archive_root)`，不再进入默认报告路径。
2. `_candidate_mode(git_root, batch_id, baseline_commit, toolchain_commit, archive_root) -> int`（5-R.6 + P0-1）：
   - **T 准入**：`@HEAD` 登记文件解析（`parse_jsonl_line` 逐行）+ 登记链核验（`chain_head(..., prev_field="prev_registry_sha256", fields=REVISION_REGISTRY_FIELDS)`）+ 链头 == `TOOLCHAIN_REGISTRY_HEAD`；`toolchain_commit` ∈ 登记集。失败 → exit 1（stderr `REVISION_TOOLCHAIN_INVALID`）。
   - **执行来源核验**：磁盘 `scripts/generate_quality_report.py` 与 `scripts/classic_artifacts.py` 的 `read_bytes()` 分别 == `git cat-file blob @T` 与 @HEAD（双常量规范化差异允许：`_normalized_script_diff`；classic_artifacts 逐字节相等）；两常量实际值分别与 @HEAD 锚链/登记链头交叉核验。失败 → exit 1（`REVISION_TOOLCHAIN_INVALID`）。
   - **首批路径判定**：`@HEAD` 锚链 genesis 空（锚文件不存在或零行 ∧ `REVISION_ANCHOR_HEAD`@HEAD == `GENESIS_SHA`）→ `baseline_commit` 必须 == `FIRST_BATCH_BASELINE`、`toolchain_commit` 必须 == 登记首条 `toolchain_commit`（T₀）；非首批 → baseline 必须存在 ∧ HEAD 祖先 ∧ 为最新 V（锚链末条对应 V 经 `validate_v_structure` 通过）。违者 exit 2 / exit 1（`REVISION_BASELINE_INVALID`）。**本步同时产出 `first_batch`（锚链 genesis 空 == True）作为已验证锚链状态，显式传入 `run_baseline`（round-4 P0-3：不从报告缺字段推断首批）。**
   - **候选门禁**：rail 以候选模式运行（④ 候选分支：`len(candidate.batches)==n+1 ∧ 前缀逐对象 canonical 相等 ∧ 新 batch_id==batch_id 参数`；违者按删批/改前缀/多批归 STALE/DRIFT/UNACCEPTED）+ E0/E1/E2 + B2 常量 + G1-G9 实际执行。
   - **基线重跑**：`run_baseline(baseline_commit, git_root, archive_root, first_batch=first_batch)`（`first_batch` 取自上一步判定）→ `_classify_baseline_rc(rc, report, first_batch=first_batch)`：`"BLOCKED"` → 上抛 exit 3（stderr `SOURCE_CHAIN_BLOCKED:<reason>`，reason 取 BLOCKED 书 `source_blocked_reason`、属五值）；`"INVALID"`（含 rc==3 但报告缺失/畸形/verifier 三字段对象冒充/顶层 BLOCKED 但无 BLOCKED 书/普通 FAIL、rc 与状态不一致）→ exit 1（`REVISION_BASELINE_INVALID`）；`"QUALIFIED"` → `compare_gate_fields(baseline, candidate_report, mode="candidate")` 非空 → exit 1（首条违规入 stderr）。
   - 全过 → stdout 候选报告 JSON（`revision_state=PENDING_ACCEPTANCE`）、exit 4。
3. `validate_v_structure(git_root, v: str) -> str | None`（5-R.7 七项，任一失败返回 `REVISION_CHAIN_STALE`）：唯一父（`rev-list --parents -n 1 v` 恰 2 OID）；diff 路径恰 `{REVISION_ANCHOR_REL, "scripts/generate_quality_report.py"}`；锚增量（@P 行集为 @V 真前缀 ∧ 新行为 @V 末行）；常量增量（`_normalized_script_diff(blob@P, blob@V)` 且差异唯一为 `REVISION_ANCHOR_HEAD` 值；@V 常量 == @V 锚链头 ∧ @P 常量 == @P 锚链头——链头从各自 blob 重算，不用 HEAD）；C 绑定（新锚 `content_commit` 存在 ∧ V 祖先 ∧ `sha256(_canonical(manifest@C).encode("utf-8")) == manifest_sha256_after`）；P 工具链身份（`script@P` vs `script@T_v` 双常量规范化比较 ∧ `classic_artifacts@P` 逐字节 == `@T_v`；两常量实际值 == @P 重算链头）；V 与 HEAD 锚状态一致（锚 blob @V == @HEAD ∧ 常量 @V == @HEAD——仅最新 V 满足，历史 V 调用时跳过第 7 项：接口加 `require_head_consistency: bool = True`）。
4. `_normalized_script_diff(a: bytes, b: bytes) -> tuple[bool, set[str]]`：按行比较，仅 `REVISION_ANCHOR_HEAD = "…"`/`TOOLCHAIN_REGISTRY_HEAD = "…"` 两行的值允许不同，其余字节全等（5-R.11）。

- [ ] **Step 4：跑测试确认通过 + ruff + 提交**

```powershell
python -m pytest tests/test_revision_rail.py -q && python -m ruff check scripts/generate_quality_report.py tests/test_revision_rail.py
git add scripts/generate_quality_report.py tests/test_revision_rail.py
git commit -m "feat(revision-rail): candidate CLI, entry prechecks, V-structure validation"
```

## Task 8：5-R.12 全矩阵收口 + T₀ 提交

**Files:**
- Test: `tests/test_revision_rail.py`（补齐矩阵缺口）
- Modify: `scripts/generate_quality_report.py`（仅当矩阵暴露缺口）

- [ ] **Step 1：补齐测试矩阵缺口（对照设计 5-R.12 逐条勾稽）**

正向缺口（新增用例，fixture 模式同 Task 5/7）：
- **两批连续验收**：V₁ 基线重跑 ACCEPTED/true → C₂ 候选 PENDING_ACCEPTANCE/false **不判退化**（其余字段照常比较）→ V₂ 默认复验 ACCEPTED ∧ 锚链两锚 ∧ 常量==链头 ∧ V₂ 成为下批基线（设计显式要求，不止首批特例）。
- **工具链升级链**：T₁（脚本合法改动提交）→ R₁ 登记 → C₁ → 候选 → V₁；V₁ 用其锚内 T₀ 仍通过（历史兼容）；R₂ 追加后旧 V₁ 仍通过（不拿 HEAD 新登记头要求旧提交）。
- **候选改善**：允许项 G7 missing_count 下降被接受（`compare_gate_fields` 已单测；此处端到端：候选报告 302 vs 基线 303 → exit 4）。
- **空锚文件零行** + 常量==genesis_sha → 合法；常量为后续值 → CHAIN_STALE。

负向缺口（参数化，逐一断言稳定错误码）：
- 同 batch_id 改记录并同步全部候选 SHA（C/A/常量不动，仅改 HEAD）→ `REVISION_HISTORY_DRIFT`
- 锚文件篡改（含同步改 manifest_sha256_after 但常量不动）→ `REVISION_CHAIN_STALE`
- 删批 → CHAIN_STALE；多批追加（+2）→ UNACCEPTED
- manifest 与 freeze 交集（同一记录双列）→ MALFORMED
- manifest_orphan（manifest 列了记录、HEAD 聚合缺）→ MISMATCH（partition_detail.manifest_orphan ≥ 1）
- VALID 书出现 manifest → UNSUPPORTED_STATE（Task 5 已建，纳入矩阵勾稽表）
- 基线重跑 rc=7 → BASELINE_INVALID；基线含允许集合外 FAIL（G3）→ BASELINE_INVALID（Task 6 已单测，端到端补一例）
- 门禁字段删除 / 同名字段改分母（schema 不一致）→ 拒绝（`compare_gate_fields` B−N + schema 键核对）
- 新增布尔字段 FAIL / 数值超上限 / 枚举不在可接纳集 → 拒绝
- 已提交篡改未登记（worktree 内提交改脚本字节但未走 R）→ TOOLCHAIN_INVALID
- 非空隔离存量书模拟修订（穷通宝鉴 quarantine 聚合记录在等式中保留多重性——HEAD==freeze 分区对该书不回归，rail NONE）
- 首批传非 03c02bb / 非首批传 03c02bb → exit 2（Task 7 已建一方向，补另一方向）
- rc=3 基线 BLOCKED 上抛 → exit 3

- [ ] **Step 2：跑全矩阵**

Run: `python -m pytest tests/test_revision_rail.py -q`
Expected: PASS（全量；单文件 < 120s——worktree 建链用例合并共享 fixture，避免每用例重复 `worktree add`）

- [ ] **Step 3：全量回归 + ruff**

```powershell
python -m pytest tests/test_classic_distillation_quality_report.py tests/test_classic_historical_freeze.py tests/test_classic_exemption_tooling.py tests/test_revision_rail.py -q
python -m ruff check scripts/generate_quality_report.py scripts/classic_artifacts.py tests/test_revision_rail.py tests/test_classic_distillation_quality_report.py
```

- [ ] **Step 4：T₀ 提交（Part A 收口）**

```powershell
git add scripts/generate_quality_report.py scripts/classic_artifacts.py tests/test_revision_rail.py tests/test_classic_distillation_quality_report.py
git commit -m "feat(revision-rail): complete 5-R.12 test matrix (T0 toolchain)"
```

T₀ = 本提交（Part A 中间提交为其祖先；T₀ OID 在 Part B R₀ 登记时冻结）。**门禁**：聚焦全绿 + ruff + 四文件回归全绿。T₀ 提交后暂停，等用户复审放行 Part B。

---

# Part B：首批运行序列（真实数据；每步含用户门禁，未获批不执行）

## Task 9：R₀ 登记（登记 T₀）

**Files:**
- Create: `docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/toolchain_registry.jsonl`（一行）
- Modify: `scripts/generate_quality_report.py`（唯一替换 `TOOLCHAIN_REGISTRY_HEAD` 值）

- [ ] **Step 1：前置确认**：T₀ OID（`git rev-parse HEAD`）已获用户复审放行；工作区干净（`QUALITY_REPORT.json` 处置方案已明确）。
- [ ] **Step 2：写登记行**：`{"toolchain_commit":"<T₀>","date":"<当日 ISO-8601>","review_ref":"T0-review","prev_registry_sha256":"<GENESIS_SHA>"}`，canonical 单行 LF。
- [ ] **Step 3：唯一替换常量**：`TOOLCHAIN_REGISTRY_HEAD` = 登记链头（`chain_head` 公式重算；脚本仅此一处字节差异）。
- [ ] **Step 4：提交 R₀**：`chore(revision-rail): register T0 toolchain (R0)`。
- [ ] **Step 5：验证**：候选 CLI 干跑（缺参 → exit 2 证明 CLI 活）+ 默认模式报告无回归（sanmingtonghui G7/source 红项保留，退出码与 Part A 前一致）。

## Task 10：C₁ 内容提交（R25 批次；真实内容）

**Files:**
- Modify: `knowledge_base/classic_texts/sanmingtonghui/all_rules.json`（JSON 数组，+2 对象 `smth_077_000/001`；解析数组、追加对象、序列化数组）
- Modify: `knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl`（JSONL，+2 行，id 自 `smth_0777` 顺序后缀）
- Create: `knowledge_base/classic_texts/sanmingtonghui/revision_manifest.json`（批次 `R25`）

- [ ] **Step 1：内容取证（离线，零 API）**：读 `HEAD:<SNAP>/extracted/raw_025.txt` 全文与历史聚合中 #25 章既有记录（`all_rules.json` 数组内 `source_chapter=="卷二·论坐命宫"` 记录），确定两条规则各自的精确连续引文区间（原省略号引文的展开；「甲已」保留原文不断言笔误；校读如需置于 `textual_note` 附加字段——G3 允许附加字段）。
- [ ] **Step 2：构造规则/MCQ**：`smth_077_000/001` 字段齐备（G3 必需键 + `original_text` 为 raw_025 精确连续子串，满足 G5 整串命中）；2 条 MCQ 引用新规则 id（单批不管控答案分布——G6 全书口径）。
- [ ] **Step 3：构造 manifest 批次 R25**：两条 rule + 两条 mcq 记录；`sha256` 按 `_record_entry` 重算；`snapshot_sha256` = HEAD raw_025 blob sha；`historical_basis` 绑历史记录（`{commit:"c5cff699fdb547bd9270acbebe1f485380848751", path:"knowledge_base/classic_texts/sanmingtonghui/all_rules.json", source_chapter:"卷二·论坐命宫", record_content_sha256:<该历史记录 canonical sha>, match_count:1}`——从冻结基点 `git show` 重算恰好 1 条匹配）。
- [ ] **Step 4：验证（不提交）**：G5 对新记录整串命中（跑 `scripts/validate_classic_distillation.py` 聚焦）；rail ②⑤⑥⑦ 对新增四记录全过（进程内调用 `evaluate_revision_rail`）；MCQ 外键存在。
- [ ] **Step 5：提交 C₁**：`data(sanmingtonghui): R25 revision batch (chapter 25 recovery)`；提交后默认模式报告允许 FAIL（预期状态，修订未接纳）。

## Task 11：候选验证 → 用户批准 → V₁

- [ ] **Step 1：候选验证（真实）**：`python scripts/generate_quality_report.py --pending-batch R25 --baseline-commit 03c02bb571dec9e2da1f7d503a292da229415d8f --toolchain-commit <T₀> --archive-root <真实归档根>`（主 worktree；`--archive-root` 传生产链所用归档根——当前门禁与基线重跑都依赖它重放 sanmingtonghui source，缺失即 BLOCKED；基线重跑真实执行：03c02bb 干净 worktree + 自带脚本，报告读取其新生成的 QUALITY_REPORT.json，非 stdout）。预期 exit 4 + `revision_state=PENDING_ACCEPTANCE`。失败按错误码修根因（不改测试不改门禁）。
- [ ] **Step 2：用户门禁**：候选报告呈报用户；等待聊天正文第一人称批准（模板：`我批准 R25 修订批次，执行 V₁ 验收提交。`）。
- [ ] **Step 3：构造 V₁**（获批后）：锚行 `{batch_id:"R25", content_commit:<C₁>, manifest_sha256_after:<sha256(_canonical(manifest@C₁).encode("utf-8"))>, prev_anchor_sha256:<GENESIS_SHA>, toolchain_commit:<T₀>, date:<ISO-8601>}`；唯一替换 `REVISION_ANCHOR_HEAD` = 新锚链头；提交 `chore(revision-rail): accept R25 batch (V1)`。
- [ ] **Step 4：V₁ 结构自检**：`validate_v_structure` 七项全过（进程内）。

## Task 12：默认复验 + 收尾

- [ ] **Step 1：默认复验**：HEAD 运行默认模式；断言 `revision_state=ACCEPTED` ∧ 指定检查通过 ∧ 无退化（G7 missing_count 303→301 允许改善；source 红项按 S 口径保留；整体 exit 1 属预期——允许红项存在）。
- [ ] **Step 2：既有回归**：`tests/test_revision_rail.py` + 四个 classic 测试文件全绿 + ruff。
- [ ] **Step 3：设计文档 §13 追加执行记录**（T₀/R₀/C₁/V₁ OID、候选与复验结果、门禁边界：数据验收状态不因复验转 PASS、三书 source S 口径不变）——单独 docs 提交。
- [ ] **Step 4：推送 + 正式 CI**（用户批准推送后）：`task/four-books-baseline` 推 origin，PR CI 全绿（Syntax/Ruff/mypy/pytest/LLM smoke/Docker）后方宣布完成。

---

## Self-Review（已执行）

1. **Spec 覆盖**：5-R.0 双轨/适用书（Task 3 other-book + ⑤）、5-R.1 工件（Task 3 常量+路径）、5-R.2 manifest schema（Task 2）、5-R.3 genesis/锚/登记（Task 1/3）、5-R.4 提交流程（Part B Task 9-12）、5-R.5 管线①-⑦（Task 3/4）、5-R.6 候选 CLI+前置（Task 7）、5-R.7 V 结构（Task 7）、5-R.8 源身份+基线重验+退化比较+流程字段例外（Task 4/6）、5-R.9 退出码（Task 5/7）、5-R.10 矩阵（Task 5）、5-R.11 双常量（Task 7）、5-R.12 测试矩阵（Task 8）、5-R.13 内容范围（Task 10）、§14 附录 A（Task 6）。缺口：无。
2. **占位符扫描**：Task 5 VALID 用例的 `...` 附确定性构造指引（复制 `_setup_passing_book` provenance 写入段，指明源码行号 53-128）；`REPORT_FIELD_SCHEMA` 字段全集以设计附录 A 为单一权威转录源（避免计划与实现双写漂移）；Task 7 注记明确 monkeypatch 与子进程边界及 `main(argv)` 进程内驱动修正。无 TBD 类占位。
3. **类型一致性**：`evaluate_revision_rail(git_root, book, freeze, evidence) -> dict{ok, revision_state, error_code, e3_ok, partition_detail?}` 全计划一致；`chain_head(entries, genesis_sha, *, prev_field, fields)` 锚/登记两用；错误码/退出码字面量与设计逐一核对。
4. **已知风险显式化**：E3 错误码迁移改既有断言（Task 5 Step 1）；CLI 候选测试的 monkeypatch 边界（Task 7 注记）；worktree fixture 清理（yield/cleanup）；单文件测试时长约束（Task 8 Step 2）。

5. **复审（第 1 轮 NEEDS_REVISION，4 P0）修订记录**：P0-1 基线重跑改读基线 worktree 新生成 `QUALITY_REPORT.json`（非 stdout）+ 候选模式四参必选（含 `--archive-root`）+ `run_baseline` 传归档；P0-2 信任根常量改确定 64-hex 字面量（`da5665…c0` == GENESIS_SHA），fixture 替换器可命中，新增 `test_trust_roots_start_at_genesis`；P0-3 基线 fixture 重写为四书完整合格形态（九门布尔 + 九门 gate_details 齐备），缺书/缺明细/缺模式字段各成负向测试；P0-4 测试 worktree 构造合成 T 提交（复制主工作区待测脚本字节），R→C→V 建于其上，不以先提交实现代替 TDD。批准来源：v29.3 批准句见本聊天正文（§0 已记录），非附件转述。

6. **复审（第 2 轮 NEEDS_REVISION，5 P0）修订记录**：P0-1 聚合文件格式——`all_rules.json` 为 JSON 数组（`KIND_FILENAME` 实测），fixture 各用例与 Part B 改数组解析/追加/序列化（MCQ 继续 JSONL），rail ⑤⑥⑦ 改 `_parse_records` 分派（JSONL 不可 `_loads_strict` 直读）；P0-2 `sync_synthetic_t` 提交前查 `status --porcelain`，无差异（代码已提交/干净 CI）则 HEAD 即 T，新增无差异正向测试；P0-3 `run_baseline` 新增"新生成守卫"（先删基线跟踪旧报告、运行后缺失即拒绝），拆 `_run_report_in_worktree` 可注入，新增预置旧报告+rc=1 未写出负向测试；P0-4 `_passing_book` G6 改四字母各 25%（同步 G2.total/G4.total_refs=4），`_qualified_baseline_report` 条件④增 `gates` 布尔与 `gate_details` 推导一致校验（`_gate_consistent`），新增"明细失败却声明 PASS"负向测试；P0-5 非首批测试补 R₀ 登记（先过 T 准入再验证基线错配 exit 2），候选成功测试改进程内驱动（`patch gqr.ROOT` 绑定 fixture Git 根 + capsys 捕获，注记落实为代码）。

7. **复审（第 3 轮 NEEDS_REVISION，2 P0）修订记录**：P0-1 候选 exit-4 测试由"patch `gqr.ROOT`"改为**隔离模块加载**——patch 已导入模块的 ROOT 不会同步 `TOOLCHAIN_REGISTRY_HEAD`/`BASE`/`SCRIPTS_DIR`（导入时定值），R₀ 后登记链头与旧模块常量不符会被入口前置核验提前拒绝；新增 `_load_report_module`（importlib 从 fixture 磁盘脚本加载，ROOT/常量全为 fixture 态），测试改名 `test_candidate_exit4_boundary` 并显式 fake `run_baseline`/`verify_source_chain`（`--archive-root` 无真实归档），真实归档 + 完整链集成在 Part B Task 11。P0-2 基线分类改 `_classify_baseline_rc` 联合"退出码 × 合法报告状态"——rc=3 须 BLOCKED schema（顶层键 `{schema_version,status,reason}`、`status=="BLOCKED"`、`reason` 属 §4.2 五值）才上抛 exit 3，rc=3 配缺失/畸形/普通 FAIL 报告归 `REVISION_BASELINE_INVALID`/exit 1；新增四类分类负向测试。

8. **复审（第 4 轮 NEEDS_REVISION，3 P0）修订记录**：P0-1 `_classify_baseline_rc` 的 BLOCKED 判定改按**真实 QUALITY_REPORT.json 形态**——顶层 `status=="BLOCKED"` ∧ `source_e2e_status=="BLOCKED"` ∧ 存在逐书 `source_e2e_status=="BLOCKED"` 且 `source_blocked_reason` ∈ §4.2 五值（原顶层键精确 `{schema_version,status,reason}` 是 source verifier CLI 输出形态，run_baseline 读的是完整质量报告，合法 BLOCKED 基线必被误拒）；新增 `_blocked_report_fixture`（生产形态正向 fixture）、verifier 三字段对象冒充与顶层 BLOCKED 无 BLOCKED 书负向测试。P0-2 候选测试 `verify_source_chain` fake 改真实接口 `(output_dict, exit_code)`（status=="OK"、code=0，经 `_run_source_chain_check` 转换；原单键 dict 会被 `out, code = ...` 解包成键名字符串致 `out.get` 崩溃）。P0-3 `first_batch` 由 `_candidate_mode` 首批路径判定（已验证锚链 genesis 空）产出，显式传入 `run_baseline` → `_classify_baseline_rc` → `_qualified_baseline_report`，不从报告缺字段推断；新增成对测试（同一缺修订字段报告：首批 QUALIFIED、非首批 INVALID）。
9. **复审（第 5 轮 NEEDS_REVISION，1 P0 + 1 非阻断）修订记录**：P0 BLOCKED 判据不验报告完整性（ghost 残缺对象可获 exit 3）——新增 `_report_structure_ok` 结构校验层作 rc==3 判 BLOCKED 前置：顶层 15 键/类型 + `books` 键集精确四书 + 逐书 15 键/九门 gates/gate_details 类型 + 逐书 reason-status 耦合（BLOCKED⇒五值 str、PASS/FAIL⇒None）+ 聚合一致性（§7 实测）；**只验形态不验门禁通过**（红门/红 source 不拒，合法 BLOCKED 不误拒）；补未知书名（ghost）/缺书/缺必需字段/`source_e2e_pass=true` 与 BLOCKED 矛盾四负向测试。键集依据修正：03c02bb 自带脚本已产出全字段（`source_e2e_status`/`status`/`approval_b2`/`exemption_stages` 实测在源码），跟踪的旧 QUALITY_REPORT.json 为旧脚本过期产物、重跑前被新生成守卫删除——fixture docstring 键集判据措辞同步修正并补 `known_limitations`。非阻断：1290 行 diff 示例围栏 python → diff。

9. **执行修正（Task 1-3 复审 NEEDS_REVISION，3 P0）同步记录**：P0-1 `_partition_equation` 缺席 KIND 由 present 跳过改为 **baseline Counter 为空 + `_git_show_optional` 读取 HEAD**（新增记录计入 `unmanifested_extra`，不得沿用旧 E3 跳过语义），补 absent-kind 负向测试；P0-2 NONE 分支信任根核对由 `anchors == []` 放宽为 `not anchors`（锚文件缺失同样核对，非 genesis → CHAIN_STALE），补"缺失 manifest+锚 + 非 genesis 常量 → STALE"负向测试（monkeypatch 进程常量——rail 读取运行中执行体的常量，与评审内存注入复现同源）；P0-3 `validate_revision_manifest` 批次标量字段（batch_id/date/author）类型检查前置（unhashable 不再 TypeError 冒泡），`_rail_anchor_entries` 异常包 try 映射 REVISION_CHAIN_STALE，补 unhashable 与 malformed-anchor 两个负向测试。

10. **执行修正（Task 1-3 复审第 2 轮，1 P0 + 1 P1）同步记录**：P0 三命通会锚链误伤其他三书——`evaluate_revision_rail` 对**所有书**读取同一份三命通会锚文件，三命通会有锚时其他书（无自身 manifest 的合法状态）在第 402 行被误判 manifest 删除；改为**书籍分流**：其他三书拒绝自身 revision manifest，但仅执行本书历史分区校验（`_partition_equation`），不读三命通会锚、不套用其"锚存在而 manifest 缺失"规则；补"三命通会 C→V 落地后其余三书仍 NONE 且历史分区通过"正向测试（V₁ 后执行体常量== @HEAD 链头，monkeypatch 对齐进程内常量，与真实部署同源）。P1 锚解析抢在阶段①之前——同时损坏 manifest 与锚时实测报 CHAIN_STALE 而非冻结优先级要求的 MANIFEST_MALFORMED；改为有 manifest 时锚解析移到①②之后（无 manifest 分支另行处理），补"双重损坏只报阶段①"测试。
