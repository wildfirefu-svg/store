# 经典文本候选数据人工验收工具链 Implementation Plan (v2, Draft / NOT AN IMPLEMENTATION BASIS)

> **STATUS: DRAFT — NOT AN IMPLEMENTATION BASIS, awaiting plan review (NEEDS_REVISION 2026-08-24).** 设计 v4.6.1 已获有效批准（提交 `e86515f`，批准原文 SHA-256 `44463d31…`），但**本计划 v2 尚未通过复审**，不得开始 Task 1 或任何代码实现。设计批准只授权"修订计划为 v2"，不构成对计划本身的批准。本状态横幅在计划复审通过后移除。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现已批准设计 v4.6.1（Approved，LOCAL_ONLY，有效批准提交 `e86515f`）定义的离线人工验收工具链：确定性抽样清单、609 规则 + 382 MCQ 审核包、审核结果 schema 校验、二审与仲裁状态机（含三方全局身份互异）、扩样计算、判定状态机与 fake 数据端到端测试；生产模式 fail-closed 锁定冻结输入。

**Architecture:** 三个 `scripts/` 平铺模块（common / sampling / review），核心逻辑为纯函数 + 两种数据源（生产：`GitSource` 锁定冻结提交并跑冻结链；测试：`DirSource` 标记 `test_only=true`），全部输出为 LF 确定性 JSON；阈值比较一律整数交叉相乘（无浮点）。测试分三层：小合成 fixture 单测、冻结候选提交的真实数据集成测试（离线、无模型 API）、精确复刻真实人口/边界/零产出计数的 fake 数据端到端场景。

**Tech Stack:** Python 3.11 标准库（hashlib/json/subprocess/re/collections），pytest，git plumbing（只读 `show`/`cat-file`/`hash-object`）。

**关联设计:** `docs/superpowers/specs/2026-08-20-classic-texts-candidate-acceptance-design.md`（**v4.6.1，已批准 LOCAL_ONLY**，有效批准提交 `e86515f`，批准原文 SHA-256 `44463d312b56045fc4548e60de3ed591e1fe9beb09a554854672cd274f678150`）。撤回的无效批准尝试 `3967000`（在 `5065b57` 撤回）仅作审计痕迹，不作为锚点。v1 计划（`b69db99`）已由 v2 取代，不再作为实施依据。

---

## 0. 范围与冻结口径

### 0.1 范围内

1. 确定性抽样清单（`sample_manifest_v1.json`）与扩样清单（`expansion_manifest_v1.json`）。
2. 609 条规则、382 条 MCQ 的审核包（`review_packet_v1.json`）。
3. 审核结果 schema 与校验（primary / second-review / arbitration 三个文件，SHA 绑定链 + 三方身份互异）。
4. 二审与仲裁状态机（`SECOND_REVIEW_PENDING → ADJUDICATED_CRITICAL | ARBITRATION_PENDING → ADJUDICATED_CRITICAL | ADJUDICATED_NON_CRITICAL`；non_critical finding 删除但条目保留分母）。
5. 扩样计算（逐层 `added_s = min(k_s, remaining_s)`，与首轮不相交）。
6. 判定状态机（§6.2 优先级 INTEGRITY → BOUNDARY → STRATUM_CASCADE → REJECT_GATE → EXPAND_GATE → ACCEPT）与 `final_acceptance_package_v1.json` 组装。
7. fake 数据端到端测试（ACCEPT / 各类 REJECT / EXPAND 两轮 / 完整性失败 / 仲裁双向）。
8. 生产模式 fail-closed 冻结输入锁定 + fake 模式 `test_only` 标记（设计 §12）。

### 0.2 范围外（明确不做）

- 不调用任何模型 API；不执行 Phase 8；不触碰正式门禁。
- 不做 audit commit + annotated tag（§8.3 发布链，仅最终 verdict 为 ACCEPT 后另立审批）。
- 不做远端发布、Git LFS、历史重写；不修改冻结链（`CLASSIC_ACCEPTANCE_FREEZE_V1` / `scripts/generate_acceptance_manifests.py` / 两个已冻结 manifest）。
- 不启动真实人工审核（本计划交付工具 + fake smoke；真实审核另行启动）。

### 0.3 冻结口径（v4.6.1 唯一解释，实现不得偏离）

| # | 口径 | 设计依据 |
|---|---|---|
| F1 | **k 公式为准（v4.6.1 已批准勘误，批准提交 `e86515f`）**：卷十一层 k_mcq = **7**（`round_half_up(367×2%)=7`，设计 v4.6 表值 8 为残留笔误）；MCQ 随机合计 **188**（跨四书 128+42+13+5）、边界 **194**、总量 **382**；规则 609（随机 342 + 边界 267） | 设计 §4.2/§4.4 |
| F2 | 非三命通会三书各为**单层 stratum，stratum_index = 1**（哈希输入编码为字符串 `"1"`） | 设计 §4.2 |
| F3 | **仲裁降级语义（v4.6.1）**：`ADJUDICATED_NON_CRITICAL` 的 finding 从 canonical 集**删除**（不计入 critical、不计入 minor-only 分子），但**该审核条目仍计入 reviewed 分母**；条目 verdict 按剩余 findings 重算，无剩余 finding 时为 `PASS`；分母不得因删除 finding 而缩小 | 设计 §6.2/§6.4 |
| F4 | `STRATUM_CASCADE` 仅对**规则**生效（§6.2 规则 3 字面只写 `rule_critical_fail_rate`）；覆盖 sample manifest 中全部规则 strata；MCQ 由 REJECT_GATE 的 M_b 覆盖 | 设计 §6.2 |
| F5 | 全部阈值比较用**整数交叉相乘**（`critical*100 > pct*reviewed`），无浮点；比率在报告中以 `"c/r"` 字符串呈现 | 可机械复算 |
| F6 | 边界门基于 **canonical（裁决后）** findings：任一边界条目存留 canonical critical → REJECT | 设计 §6.2 规则 2 + §6.4 |
| F7 | 每轮 primary 版本配齐**自己的**二审回执（覆盖该版本全部 critical）；扩样后"重跑 ADJUDICATION"（§6.4），旧 critical 一并重裁 | 设计 §6.4 |
| F8 | primary 无 critical 时二审回执可省略；有 ≥1 critical 时 `decide --second` 必填；二审有分歧时 `--arbitration` 必填 | 设计 §8.2 + fail-closed |
| F9 | 扩样分母 = 全部唯一已审项（首轮随机 + 边界 + 扩样）；扩样作用于触发书 × 触发类型的**全部 strata** | 设计 §6.3 |
| F10 | chapter manifest 读取按 **LF 规范化字节**计 SHA-256（CRLF 工作区不破坏冻结绑定 `8687f681…`） | 与冻结身份域一致 |
| F11 | `decide` 从数据源**机械重推**完整性事实（零产出章 raw 存在性 + 3 个 drift 文件存在性），不信任 packet 内嵌值 | 设计 §12.1 fail-closed |
| F12 | 运行产物一律写 `--out <dir>`（真实运行用 `.tmp/` 下运行目录）；不写跟踪目录 | 仓库记忆约束 |
| F13 | **生产模式冻结锁定（设计 §12.1）**：`--candidate-commit` 模式必须先校验全部条件（见 F14）再读取任何数据；fake 模式（`--data-root`）产物顶层必含 `test_only=true`，且 `finalize` 拒绝为 fake 产物收尾 | 设计 §12.1/§12.2 |
| F14 | 生产模式 fail-closed 校验项（任一不符非零退出）：①candidate_commit 精确等于 `80bc630…`（v5.0 干净链 C2）；②chapter manifest LF SHA = `ba8ab35e7b98e3a0578f7b62f758e2faff1bbe73d480e153c25b6c74b497d1cf`；③identity manifest LF SHA = `0279e30b92f70f8b7cce9c786070fc201cfc3fac86826ef6403b15ad90c5aad2` 且其 8 个输出文件 sha256_lf 与候选提交字节一致；④运行 `generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid <oid>` exit 0；⑤锚点记录 `record_type=freeze-anchor-record`、`status=LOCAL_ONLY`、`overall_state="LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED"`、顶层无 `independent_approval` 键、`provenance.independent_approval=="none"` | 设计 §12.1 |
| F15 | **三方身份互异（设计 §12.3）**：primary `reviewer_list` 非空，每条 finding 的 `reviewer` ∈ 该列表；second receipt 顶层 `reviewer` ≠ 任一 primary finding reviewer（条目 reviewer 须等于顶层）；arbitration 顶层 `reviewer_second` = second 顶层 reviewer、`arbitrator` 全局独立（**不得出现在整个 primary `reviewer_list` 中**，也 ≠ `reviewer_second`）；arbitration 每条目带 `reviewer_first`（取自 primary 该 finding 的 reviewer，∈ primary reviewer_list），且该条目三身份两两互异 | 设计 §12.3 |
| F16 | **严格 CLI（设计 §12.4）**：未知 `--flag`、行尾缺值 flag、未声明 positional 一律非零退出并打印 usage；每个子命令显式声明允许的 flag 集合；必填缺失/路径不存在/SHA 非 64 位十六进制均 fail-closed | 设计 §12.4 |
| F17 | **finalize 回执闭环（设计 §12.5）**：拒绝报告未绑定却通过 `--second/--arbitration` 传入的回执；拒绝报告绑定了回执 SHA 却未传或 SHA 不符；final 包每个 SHA 与磁盘实参一致，`final_verdict` ∈ {ACCEPT, REJECT} 且等于报告 verdict | 设计 §12.5 |
| F18 | **冻结校验先于任何数据读取**：生产模式（`--candidate-commit`）在读取 chapter manifest、sample manifest、数据文件之前，必须先完成 `verify_frozen_inputs`；CLI 传入的 `--chapter-manifest` 必须等于冻结章节 manifest（LF SHA 精确匹配），不得是任意自洽文件。所有子命令入口统一先校验后读取 | 设计 §12.1 |
| F19 | **sample/expansion manifest 全量验证 + 扩样授权证据包（重构比对）**：sample 验证以当前 chapter manifest/source 走同一代码路径重构期望 manifest 后做 canonical 字节全等比较。expansion 验证必须持有产生它的 decision report，并校验 report kind/同模式/绑定当前 sample/无前轮 expansion/`verdict=="EXPAND"`/`expanded_pairs==pending_expands`/`round==1`，再重构 expansion body 全等比较。**关键：消费者（`packet`/下一轮 `decide`/`finalize`）不能只校验 report 与 expansion 彼此自洽，必须携带 R1 完整证据包（`--producing-primary`，按需 `--producing-second`/`--producing-arbitration`），通过共享 `verify_producing_report()` 走 `validate_decision_inputs`（与 `decide` 同一路径，含 F22 门禁）重算 producing verdict，并要求磁盘 report **原始字节**与重算的 canonical 字节全等（`read_bytes() == serialize_json(recomputed)`，CRLF/额外空白/键重排/重复 JSON key 一律拒绝）——由此拒绝绕过 `expand` 直接构造的匹配 report+expansion。生产者 `expand` 同样调用 `verify_producing_report`（同一路径、同一字节比对）。`finalize` 不信任 report 字段：它重走冻结输入门禁→sample 验证→（有 expansion 时）producing report/证据验证→`validate_decision_inputs` 重算 terminal verdict→磁盘 report 原始字节全等→terminal 判定（ACCEPT/REJECT），因此手工 `verdict="ACCEPT"` + 自洽 SHA 的 report 无法收尾。**`validate-primary` 与 `finalize`/`decide` 走同一条 producing-evidence 授权链**：Task 4 初版只支持无 expansion（显式拒绝 `--expansion-manifest`）；Task 7 在 `validate_expansion_manifest` 已实现后，用整体替换 `cmd_validate_primary` 的方式扩展为最多一个 expansion，强制 `--decision-report`+`--producing-primary`（second/arbitration 按需），先 `check_producing_evidence_presence`、再 `verify_producing_report`（复用其返回的已验证 report 对象，不重读路径）、再 `validate_expansion_manifest`，且 report/expansion 的磁盘原始字节均只读取一次并据此固定 SHA（无 TOCTOU 窗口）；无 expansion 时拒绝孤立 evidence 参数——从而无法用任意 expansion 让 primary 绑定其 SHA 并覆盖 `new_ids` 来通过校验。设计只允许一次并行扩样，故最多一个 expansion；无 expansion 时传入 `--decision-report`/`--producing-*` 一律拒绝（避免证据被静默忽略）。`validate_primary` 强制要求非空 `chapter_manifest`（无 None/空旁路），并核对三命通会条目的 `source_chapter` 必须等于 chapter manifest 指定章节（§8.1 schema）；篡改该字段会破坏审核条目的章节身份与证据可追溯性（注意：当前决策指标的 boundary/stratum 来自冻结 sample/chapter 元数据的 `item_meta_map`，不直接使用 primary 该字段，但伪造章节归属仍必须 fail-closed）；`validate-primary` CLI 必填 `--chapter-manifest`，`validate_decision_inputs` 由调用方传入冻结/校验过的 chapter manifest。`chapter_manifest_sha256`：生产=冻结 SHA，fake=本次 fake chapter manifest 实际 LF SHA | 设计 §6.3/§6.4/§8.1/§12.1/§12.2/§12.5 |
| F20 | **审核回执链用原始字节 SHA**：`primary`、`second`、`arbitration`、`decision_report` 等审核产物的绑定 SHA 一律用磁盘**原始字节** `sha256(read_bytes())`，**不做 LF 规范化**（CRLF 篡改必须改变绑定 SHA）。LF 规范化只用于身份/章节 manifest 等明确冻结为 LF 口径的文件 | 设计 §12.5 |
| F21 | **仲裁 entry 精确绑定首审人**：`validate_arbitration` 按 `(book,type,id,finding_index)` 精确取 primary 中该 finding 的 `reviewer`（不得要求同 item 全部 findings 同一 reviewer），并校验 arbitration entry 的 `reviewer_first` 等于该值、属于 primary `reviewer_list`、与 `reviewer_second`/`arbitrator` 两两互异。顶层与每条 entry 的 `reviewed_at` 必须存在且为 ISO-8601 字符串 | 设计 §12.3 |
| F22 | **拒绝非状态机要求的回执**：`decide` 只有在 primary 含 critical 时才接受 `--second`，只有在二审存在 disagree 时才接受 `--arbitration`；无 critical 却传 `--second`、无分歧却传 `--arbitration` 一律 fail-closed，且不得把未验证回执的 SHA 写入决策报告。`finalize` 同样拒绝未被报告绑定的额外回执 | 设计 §8.2/§12.5 |

### 0.4 冻结数字（真实数据，已用冻结章节 manifest 实算核对）

- sanmingtonghui 分层人口（rule/mcq）：s1 1542/777、s2 74/59、s3 708/593、s4 291/211、s5 1320/1226、s6 1274/1187、s7 1108/843、s8 505/367、s9 1221/840；合计 8043/6103。
- k_rules（按层）：46、5、21、9、40、38、33、15、37 → **244**；k_mcq：16、5、12、5、25、24、17、**7**、17 → **128**。
- 其余三书 k：qiongtongbaojian 69/42、ditiansui 24/13、zipingzhenquan 5/5。
- 边界章（ch 1、80、81、90、163、185、245、305、347、368、383）实测：规则 **267**、MCQ **194**（逐章 14/14、1/1、2/2、15/14、28/4、40/38、35/32、15/14、12/9、81/49、24/17）。
- 总量：规则 342+267 = **609**；MCQ 188+194 = **382**（随机 188 = 128+42+13+5）；合计 **991** 项。
- 零产出章：0 规则 {25, 56, 72}；0 MCQ {25, 26, 56, 72, 112}。
- 黄金向量（冻结 SEED 编码）：
  - `sample_score("sanmingtonghui","rule",1,"smth_001_r0000") = c54f87a08f89fee93cc4f33b66f480b8c6e0c7601b100a1c306483aa2a2b2a73`
  - `expand_score("sanmingtonghui","rule",1,"smth_001_r0000") = 4eb4053ed0c04a01b5d63d5f99aa6f95911f2c0add7410524607c32514781f0a`
  - SEED bytes hex = `00a5c0de20260820`，十进制 46655431411894304。

### 0.5 文件结构

- Create: `scripts/classic_acceptance_common.py` — 冻结常量、长度前缀编码与哈希抽样键、§2.3 归一化、k 公式、DataSource（Git/Dir）、严格 flag 解析、`verify_frozen_inputs`（生产模式锁定，F13/F14）。
- Create: `scripts/classic_acceptance_sampling.py` — `sample` / `expand` 子命令；sample manifest 与 expansion manifest 生成（生产/ fake 标记）。
- Create: `scripts/classic_acceptance_review.py` — `packet` / `validate-primary` / `validate-second` / `validate-arbitration` / `decide` / `finalize` 子命令。
- Create: `tests/classic_acceptance_fixtures.py` — 共享测试基建（非测试文件，不被收集）。
- Create: `tests/test_classic_acceptance_sampling.py` — common + sampling 单测 + 真实数据集成。
- Create: `tests/test_classic_acceptance_review.py` — packet / schema 校验 / 裁决 / 判定单测 + 真实 packet 集成。
- Create: `tests/test_classic_acceptance_e2e.py` — fake 数据端到端场景。

命名与风格：模块 `snake_case`、`from __future__ import annotations`、fail-closed `require()`、LF 序列化 `json.dumps(ensure_ascii=False, indent=2) + "\n"`（与 `generate_acceptance_manifests.py` 一致）。ruff 基线仅 E9/F821。

---

### Task 1: 共享基础模块（含严格 CLI 与生产冻结锁定）+ 测试基建

**Files:**
- Create: `scripts/classic_acceptance_common.py`
- Create: `tests/classic_acceptance_fixtures.py`
- Create: `tests/test_classic_acceptance_sampling.py`（本任务装 common 的单测；后续任务追加）

- [ ] **Step 1: 写失败测试（黄金向量 + 编码 + k 公式 + 归一化 + 严格 CLI + 生产锁定）**

创建 `tests/test_classic_acceptance_sampling.py`：

```python
"""Tests for the classic-texts manual-acceptance tooling (design v4.6.1,
Approved LOCAL_ONLY). Layer 1: shared common module (frozen SEED encoding,
k formula, section 2.3 normalization, data sources, strict CLI parsing,
production frozen-input locking). Later tasks append sampling/review tests.
Everything runs offline; real-data tests read the frozen candidate commit
51eb92b via `git show` (no model API, no Phase 8).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import classic_acceptance_common as c
import classic_acceptance_fixtures as fixtures


def test_length_prefixed_no_delimiter_ambiguity():
    assert (c.length_prefixed(b"ab") + c.length_prefixed(b"c")
            != c.length_prefixed(b"a") + c.length_prefixed(b"bc"))


def test_seed_matches_design():
    assert c.SEED_BYTES == bytes.fromhex("00a5c0de20260820")
    assert int.from_bytes(c.SEED_BYTES, "big") == c.SEED == 46655431411894304


def test_score_golden_vectors():
    assert c.sample_score("sanmingtonghui", "rule", 1, "smth_001_r0000") == \
        "c54f87a08f89fee93cc4f33b66f480b8c6e0c7601b100a1c306483aa2a2b2a73"
    assert c.expand_score("sanmingtonghui", "rule", 1, "smth_001_r0000") == \
        "4eb4053ed0c04a01b5d63d5f99aa6f95911f2c0add7410524607c32514781f0a"


def test_score_stable_and_distinct():
    args = ("sanmingtonghui", "rule", 1, "smth_001_r0001")
    assert c.sample_score(*args) == c.sample_score(*args)
    assert c.sample_score(*args) != c.sample_score("sanmingtonghui", "rule", 2, "smth_001_r0001")
    assert c.sample_score(*args) != c.sample_score("qiongtongbaojian", "rule", 1, "smth_001_r0001")
    assert c.sample_score(*args) != c.sample_score("sanmingtonghui", "mcq", 1, "smth_001_r0001")
    assert c.sample_score(*args) != c.expand_score(*args)


def test_round_half_up_and_compute_k():
    assert c.round_half_up_int(734, 100) == 7       # 7.34 -> 7 (F1 errata)
    assert c.round_half_up_int(1554, 100) == 16     # 15.54 -> 16
    assert c.round_half_up_int(242, 100) == 2
    assert c.compute_k(1542, 3) == 46
    assert c.compute_k(74, 3) == 5
    assert c.compute_k(367, 2) == 7                 # errata: NOT 8
    assert c.compute_k(155, 2) == 5


def test_normalize_for_source_match():
    assert c.normalize_for_source_match("甲己 合\r\n而不 合\t") == "甲己合而不合"
    assert c.normalize_for_source_match("，。；") == "，。；"


def test_dir_source_read_and_exists():
    base = fixtures.tmp_dir("acceptance_common")
    try:
        (base / "sub").mkdir()
        (base / "sub" / "f.txt").write_bytes("内容\n".encode("utf-8"))
        src = c.DirSource(base)
        assert src.read_bytes("sub/f.txt") == "内容\n".encode("utf-8")
        assert src.exists("sub/f.txt")
        assert not src.exists("sub/missing.txt")
        with pytest.raises(RuntimeError, match="missing path"):
            src.read_bytes("sub/missing.txt")
    finally:
        fixtures.rmtree_force(base)


def test_git_source_rejects_short_commit():
    with pytest.raises(RuntimeError, match="40-hex"):
        c.GitSource(Path("."), "51eb92b")


def test_git_source_reads_frozen_candidate():
    src = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    blob = src.read_bytes("knowledge_base/classic_texts/zipingzhenquan/all_rules.json")
    assert blob.startswith(b"[")
    assert src.exists("knowledge_base/classic_texts/zipingzhenquan/all_rules.json")
    assert not src.exists("knowledge_base/classic_texts/zipingzhenquan/NOPE.json")


# ---- strict CLI parsing (F16) ----

def test_parse_flags_unknown_flag_rejected():
    with pytest.raises(RuntimeError, match="unknown flag"):
        c.parse_flags(["--bogus", "x"], allowed={"out"})


def test_parse_flags_missing_value_rejected():
    with pytest.raises(RuntimeError, match="requires a value"):
        c.parse_flags(["--out"], allowed={"out"})


def test_parse_flags_unexpected_positional_rejected():
    with pytest.raises(RuntimeError, match="unexpected positional"):
        c.parse_flags(["leftover"], allowed={"out"})


def test_parse_flags_repeatable_and_required():
    flags, positional = c.parse_flags(
        ["--out", "o", "--exp", "a", "--exp", "b"],
        allowed={"out"}, repeatable={"exp"})
    assert positional == []
    assert flags["out"] == ["o"]
    assert flags["exp"] == ["a", "b"]
    with pytest.raises(RuntimeError, match="exactly once"):
        c.flag1(flags, "missing")
    # a repeatable flag must not be passed via single-value helpers
    with pytest.raises(RuntimeError, match="at most once"):
        c.flag_opt(flags, "exp")


def test_build_source_git_locks_to_frozen_commit():
    # GitSource rejects non-40-hex at construction; build_source only accepts
    # the frozen candidate commit (verified by verify_frozen_inputs).
    with pytest.raises(RuntimeError, match="40-hex"):
        c.GitSource(fixtures.ROOT, "51eb92b")
    # exactly-one-mode is enforced before any commit check
    with pytest.raises(RuntimeError, match="exactly one"):
        c.build_source({})
    with pytest.raises(RuntimeError, match="exactly one"):
        c.build_source({"candidate-commit": [fixtures.COMMIT],
                        "data-root": [str(fixtures.ROOT)]})


# ---- production frozen-input locking (F13/F14) ----

def test_verify_frozen_inputs_passes_against_real_chain():
    # reads the real anchor record + runs the real --check (may take ~1 min)
    ch_path = fixtures.REPO_ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json"
    anchor = c.verify_frozen_inputs(fixtures.COMMIT, ch_path)
    assert anchor["expected_tag_oid"]
    assert anchor["overall_state"] == "LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED"


def test_verify_frozen_inputs_rejects_wrong_commit():
    ch_path = fixtures.REPO_ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json"
    with pytest.raises(RuntimeError, match="candidate_commit"):
        c.verify_frozen_inputs("0" * 40, ch_path)


def test_verify_frozen_inputs_rejects_nonfrozen_chapter_manifest():
    # F18: a CLI --chapter-manifest that is not the frozen one is rejected
    # before any data read.
    base = fixtures.tmp_dir("acceptance_frozen_ch")
    try:
        real = fixtures.CHAPTER_MANIFEST
        tampered = base / "ch.json"
        data = bytearray(real.read_bytes())
        data[len(data) // 2] ^= 0x01
        tampered.write_bytes(bytes(data))
        with pytest.raises(RuntimeError, match="chapter-manifest LF SHA"):
            c.verify_frozen_inputs(fixtures.COMMIT, tampered)
    finally:
        fixtures.rmtree_force(base)


def test_check_iso8601_accepts_timezone_and_rejects_bad_values():
    # timezone-qualified valid timestamps accepted (Z and offsets)
    c._check_iso8601("2026-08-23T00:00:00+08:00", "x")
    c._check_iso8601("2026-08-23T00:00:00Z", "x")
    c._check_iso8601("2026-08-23T12:34:56.789-05:00", "x")
    # bare timestamp without timezone rejected
    with pytest.raises(RuntimeError, match="timezone"):
        c._check_iso8601("2026-08-23T00:00:00", "x")
    # shape-valid but semantically impossible date/time/timezone rejected
    for bad in ("t", "yesterday", "2026-99-99T99:99:99+99:99",
                "2026-13-01T00:00:00+08:00", "not-a-timestamp"):
        with pytest.raises(RuntimeError):
            c._check_iso8601(bad, "x")


def test_sha256_file_raw_distinguishes_crlf(tmp_path=None):
    # F20: receipt SHA uses raw bytes; CRLF tampering changes the SHA.
    base = fixtures.tmp_dir("acceptance_raw_sha")
    try:
        p = base / "receipt.json"
        p.write_bytes(b'{"a": 1}\n')
        lf = c.sha256_file_raw(p)
        p.write_bytes(b'{"a": 1}\r\n')
        crlf = c.sha256_file_raw(p)
        assert lf != crlf
    finally:
        fixtures.rmtree_force(base)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_classic_acceptance_sampling.py -q`
Expected: collection error / `ModuleNotFoundError: No module named 'classic_acceptance_common'`

- [ ] **Step 3: 实现 `scripts/classic_acceptance_common.py`**

```python
"""Shared constants and helpers for the classic-texts manual-acceptance
tooling (design v4.6.1, Approved LOCAL_ONLY).

Implements: section 2.3 source-match normalization, section 4.1 deterministic
length-prefixed hash sampling keys, section 4.2 k formula (3% rules / 2% MCQ,
min 5, round_half_up), the frozen section 6.2 thresholds, strict CLI flag
parsing (section 12.4), and production-mode frozen-input locking
(section 12.1, fail-closed). LOCAL_ONLY tooling: no model API, no Phase 8, no
formal gate, no remote publication.

k-table errata (v4.6.1 approved): design v4.6 recorded k_mcq(stratum 8)=8,
contradicting the frozen formula (367*2% = 7.34 -> round_half_up -> 7). The
FORMULA is authoritative: k_mcq(stratum 8)=7, MCQ totals random 188 (cross-book
128+42+13+5) + boundary 194 = 382. Rules stay 609.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BOOKS = ["sanmingtonghui", "qiongtongbaojian", "ditiansui", "zipingzhenquan"]
BOOK_ROOT = "knowledge_base/classic_texts"
BOUNDARY_CHAPTERS = [1, 80, 81, 90, 163, 185, 245, 305, 347, 368, 383]
SANMING_STRATA = [
    (1, 1, 80), (2, 81, 89), (3, 90, 162), (4, 163, 184), (5, 185, 244),
    (6, 245, 304), (7, 305, 346), (8, 347, 367), (9, 368, 383),
]
DRIFT_FILES = [
    f"{BOOK_ROOT}/qiongtongbaojian/all_rules.json",
    f"{BOOK_ROOT}/qiongtongbaojian/quarantine_rules.jsonl",
    f"{BOOK_ROOT}/sanmingtonghui/all_rules.json",
]
SEED = 0xA5C0DE20260820
SEED_BYTES = SEED.to_bytes(8, "big")
SEED_DECIMAL = 46655431411894304
EXPAND_TAG = bytes([0x45, 0x58, 0x50])
K_RULE_PCT = 3
K_MCQ_PCT = 2
K_MIN = 5
STRATUM_CASCADE_PCT = 8
REJECT_PCT = 5
EXPAND_LOW_PCT = 2
MINOR_REJECT_PCT = 15

CRITICAL_CATEGORIES = {"distortion", "answer_wrong", "unsupported",
                       "hallucination", "source_mismatch"}
MINOR_CATEGORIES = {"wording", "condition_omission", "option_noise", "citation_bias"}
VERDICTS = {"PASS", "PASS_WITH_MINOR", "FAIL"}

# Design section 12.1 frozen-input constants (the ONLY accepted values for
# production runs). Source: docs/superpowers/specs/2026-08-20-classic-texts-
# freeze-anchor-record.json (LOCAL_ONLY, implementer-maintained, not an
# approval) plus the two frozen manifests. The acceptance tool must fail
# closed if any of these drift.
FROZEN_CANDIDATE_COMMIT = "80bc630396f31c6b6c122e49ef97f6d912e6f636"
FROZEN_CHAPTER_MANIFEST_SHA = "ba8ab35e7b98e3a0578f7b62f758e2faff1bbe73d480e153c25b6c74b497d1cf"
FROZEN_IDENTITY_MANIFEST_SHA = "0279e30b92f70f8b7cce9c786070fc201cfc3fac86826ef6403b15ad90c5aad2"
FROZEN_FREEZE_TAG = "CLASSIC_ACCEPTANCE_FREEZE_V2"
FROZEN_GENERATOR_PATH = "scripts/generate_acceptance_manifests.py"
ANCHOR_RECORD_PATH = ("docs/superpowers/specs/"
                      "2026-08-20-classic-texts-freeze-anchor-record.json")
EXPECTED_ANCHOR_OVERALL_STATE = "LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED"
CHAPTER_MANIFEST_NAME = "2026-08-20-classic-texts-chapter-identity-manifest.json"
IDENTITY_MANIFEST_NAME = "2026-08-20-classic-texts-candidate-identity-manifest.json"


def require(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def length_prefixed(data: bytes) -> bytes:
    return len(data).to_bytes(4, "big") + data


def _lp(value: str) -> bytes:
    return length_prefixed(value.encode("utf-8"))


def sample_score(book, item_type, stratum_index, item_id):
    key = (length_prefixed(SEED_BYTES) + _lp(book) + _lp(item_type)
           + _lp(str(stratum_index)) + _lp(item_id))
    return hashlib.sha256(key).hexdigest()


def expand_score(book, item_type, stratum_index, item_id):
    key = (length_prefixed(SEED_BYTES) + length_prefixed(EXPAND_TAG) + _lp(book)
           + _lp(item_type) + _lp(str(stratum_index)) + _lp(item_id))
    return hashlib.sha256(key).hexdigest()


_WS_RE = re.compile(r"\s+", re.UNICODE)


def normalize_for_source_match(text: str) -> str:
    return _WS_RE.sub("", text)


def round_half_up_int(numerator: int, denominator: int) -> int:
    require(denominator > 0, "round_half_up_int: denominator must be positive")
    return (2 * numerator + denominator) // (2 * denominator)


def compute_k(population: int, pct: int) -> int:
    return max(K_MIN, round_half_up_int(population * pct, 100))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lf_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def sha256_file_lf(path) -> str:
    """LF-normalized SHA, ONLY for manifests whose frozen identity is defined
    in LF bytes (chapter/identity manifests). Review receipts use
    sha256_file_raw instead (F20)."""
    return sha256_bytes(lf_bytes(Path(path).read_bytes()))


def sha256_file_raw(path) -> str:
    """Raw on-disk byte SHA for review receipts (primary/second/arbitration/
    decision report). No LF normalization, so CRLF tampering changes the
    binding SHA (F20, design section 12.5)."""
    return sha256_bytes(Path(path).read_bytes())


def load_json_with_sha(path):
    """F20/P0: read a review artifact's raw on-disk bytes exactly ONCE and
    return (object, raw-byte SHA-256) so the parsed object and its binding
    SHA can never diverge (no TOCTOU re-read window). Callers pin both and
    never re-open the path."""
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw)


def serialize_json(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_json(source, rel: str):
    return json.loads(lf_bytes(source.read_bytes(rel)).decode("utf-8"))


def load_jsonl(source, rel: str):
    lines = lf_bytes(source.read_bytes(rel)).decode("utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def parse_flags(argv, allowed, repeatable=()):
    """Strict CLI parser (design section 12.4): unknown flags, missing values,
    and unexpected positional arguments are all rejected. Returns
    ({name: [values...]}, [positional...])."""
    allowed = set(allowed) | set(repeatable)
    flags = {}
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--"):
            name = arg[2:]
            require(name in allowed, f"unknown flag: --{name}")
            require(i + 1 < len(argv) and not argv[i + 1].startswith("--"),
                    f"--{name} requires a value")
            flags.setdefault(name, []).append(argv[i + 1])
            i += 2
        else:
            positional.append(arg)
            i += 1
    require(not positional, f"unexpected positional arguments: {positional}")
    return flags, positional


def flag1(flags, name):
    values = flags.get(name) or []
    require(len(values) == 1, f"--{name} must be given exactly once (got {len(values)})")
    require(bool(values[0]), f"--{name} requires a value")
    return values[0]


def flag_opt(flags, name):
    values = flags.get(name) or []
    require(len(values) <= 1, f"--{name} may be given at most once")
    return values[0] if values and values[0] else None


def flagn(flags, name):
    return [v for v in (flags.get(name) or []) if v]


class DirSource:
    kind = "dir"

    def __init__(self, root):
        self.root = Path(root)

    def read_bytes(self, rel: str) -> bytes:
        path = self.root / rel
        if not path.is_file():
            raise RuntimeError(f"data source missing path: {rel}")
        return path.read_bytes()

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()


class GitSource:
    kind = "git"

    def __init__(self, repo_root, commit: str):
        self.repo = Path(repo_root)
        require(re.fullmatch(r"[0-9a-f]{40}", commit),
                "GitSource commit must be a full 40-hex sha")
        self.commit = commit

    def _git(self, args, check=True):
        result = subprocess.run(["git", "-C", str(self.repo)] + args, capture_output=True)
        if check and result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: "
                f"{result.stderr.decode('utf-8', 'replace')[:300]}")
        return result

    def read_bytes(self, rel: str) -> bytes:
        return self._git(["show", f"{self.commit}:{rel}"]).stdout

    def exists(self, rel: str) -> bool:
        result = self._git(["cat-file", "-t", f"{self.commit}:{rel}"], check=False)
        return result.returncode == 0 and result.stdout.decode("utf-8").strip() == "blob"


def _read_anchor_record(repo_root):
    path = Path(repo_root) / ANCHOR_RECORD_PATH
    require(path.is_file(), f"anchor record not found: {ANCHOR_RECORD_PATH}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_frozen_inputs(candidate_commit, chapter_manifest_path):
    """Production-mode fail-closed frozen-input verification (design section
    12.1, F13/F14/F18). Runs BEFORE any candidate data or chapter-manifest
    read. Verifies the exact candidate commit, that the CLI-provided chapter
    manifest equals the frozen one (LF SHA), both frozen manifest SHAs from
    their fixed repo paths, the anchor-record honesty fields (including the
    absence/pinning of independent_approval), and the full three-object
    freeze chain via generate_acceptance_manifests.py --check. Returns the
    anchor record on success; raises RuntimeError otherwise."""
    require(isinstance(candidate_commit, str)
            and candidate_commit == FROZEN_CANDIDATE_COMMIT,
            f"production mode requires candidate_commit {FROZEN_CANDIDATE_COMMIT} "
            f"(got {candidate_commit!r})")

    repo_root = Path(__file__).resolve().parents[1]
    # F18: the CLI --chapter-manifest must itself be the frozen chapter manifest
    cli_ch_sha = sha256_file_lf(chapter_manifest_path)
    require(cli_ch_sha == FROZEN_CHAPTER_MANIFEST_SHA,
            f"--chapter-manifest LF SHA {cli_ch_sha[:16]} != frozen "
            f"{FROZEN_CHAPTER_MANIFEST_SHA[:16]}; production mode only accepts "
            f"the frozen chapter manifest")
    chapter_manifest_path = repo_root / "docs" / "superpowers" / "specs" / CHAPTER_MANIFEST_NAME
    identity_manifest_path = repo_root / "docs" / "superpowers" / "specs" / IDENTITY_MANIFEST_NAME
    ch_sha = sha256_file_lf(chapter_manifest_path)
    require(ch_sha == FROZEN_CHAPTER_MANIFEST_SHA,
            f"chapter manifest SHA {ch_sha[:16]} != frozen {FROZEN_CHAPTER_MANIFEST_SHA[:16]}")
    id_sha = sha256_file_lf(identity_manifest_path)
    require(id_sha == FROZEN_IDENTITY_MANIFEST_SHA,
            f"identity manifest SHA {id_sha[:16]} != frozen {FROZEN_IDENTITY_MANIFEST_SHA[:16]}")

    anchor = _read_anchor_record(repo_root)
    require(anchor.get("record_type") == "freeze-anchor-record",
            "anchor record record_type != freeze-anchor-record")
    require(anchor.get("status") == "LOCAL_ONLY",
            "anchor record status != LOCAL_ONLY")
    require(anchor.get("overall_state") == EXPECTED_ANCHOR_OVERALL_STATE,
            f"anchor record overall_state != {EXPECTED_ANCHOR_OVERALL_STATE!r}")
    require("independent_approval" not in anchor,
            "anchor record must NOT have a top-level independent_approval key "
            "(only an explicit re-freeze approval may add one)")
    provenance = anchor.get("provenance")
    require(isinstance(provenance, dict), "anchor record provenance missing/not an object")
    require(provenance.get("independent_approval") == "none",
            'anchor record provenance.independent_approval must == "none" '
            '(a non-"none" value is a false approval claim and fails closed)')
    require(anchor.get("candidate_commit") == FROZEN_CANDIDATE_COMMIT,
            "anchor record candidate_commit mismatch")
    require(anchor["manifests"].get(CHAPTER_MANIFEST_NAME) == FROZEN_CHAPTER_MANIFEST_SHA,
            "anchor record chapter manifest SHA mismatch")
    require(anchor["manifests"].get(IDENTITY_MANIFEST_NAME) == FROZEN_IDENTITY_MANIFEST_SHA,
            "anchor record identity manifest SHA mismatch")

    identity = json.loads(Path(identity_manifest_path).read_text(encoding="utf-8"))
    for f in identity["groups"]["output_files"]:
        require(f["candidate_commit"] == FROZEN_CANDIDATE_COMMIT,
                f"output file {f['path']} candidate_commit mismatch")
        require(re.fullmatch(r"[0-9a-f]{64}", f["sha256_lf"]),
                f"output file {f['path']} sha256_lf invalid")

    expected_oid = anchor.get("expected_tag_oid")
    require(re.fullmatch(r"[0-9a-f]{40}", expected_oid or ""),
            "anchor record expected_tag_oid missing/invalid")
    result = subprocess.run(
        [sys.executable, str(repo_root / FROZEN_GENERATOR_PATH), "--check",
         "--freeze-ref", FROZEN_FREEZE_TAG, "--expected-freeze-tag-oid", expected_oid],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    require(result.returncode == 0,
            f"frozen chain --check failed (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}")
    return anchor


_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def _check_iso8601(value, what):
    """Require an ISO-8601 timestamp with a real date/time AND a non-empty
    timezone offset. Shape-only regex is not enough: 2026-99-99T99:99:99+99:99
    matches the regex but is not a valid instant. Use datetime.fromisoformat
    for semantic parsing; normalize trailing Z to +00:00 first."""
    require(isinstance(value, str) and _ISO8601_RE.match(value),
            f"{what} must be an ISO-8601 timestamp with timezone (got {value!r})")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        require(False, f"{what} is not a valid ISO-8601 timestamp: {value!r}")
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            f"{what} must include a timezone offset: {value!r}")


def build_source(flags, expected_test_only=None):
    """Exactly one of --candidate-commit <40-hex> (production, locked) or
    --data-root <dir> (fake/test only). F18: production runs the full frozen
    lock, including validating the CLI-provided --chapter-manifest, BEFORE any
    data is read. Returns (source, source_desc). When expected_test_only is
    given, callers can additionally assert the resolved mode matches (used by
    the strict CLI entry points)."""
    commit = flag_opt(flags, "candidate-commit")
    data_root = flag_opt(flags, "data-root")
    require(bool(commit) != bool(data_root),
            "exactly one of --candidate-commit <40-hex> or --data-root <dir> is required")
    if commit:
        ch_path = Path(flag1(flags, "chapter-manifest"))
        verify_frozen_inputs(commit, ch_path)
        require(re.fullmatch(r"[0-9a-f]{40}", commit),
                "--candidate-commit must be a full 40-hex sha")
        require(commit == FROZEN_CANDIDATE_COMMIT,
                f"production mode requires candidate_commit {FROZEN_CANDIDATE_COMMIT}")
        if expected_test_only is not None:
            require(expected_test_only is False, "candidate-commit is production, not fake")
        repo_root = Path(__file__).resolve().parents[1]
        return (GitSource(repo_root, commit),
                {"kind": "git", "candidate_commit": commit, "test_only": False})
    if expected_test_only is not None:
        require(expected_test_only is True, "data-root is fake, not production")
    return DirSource(data_root), {"kind": "dir", "root": str(Path(data_root).resolve()),
                                 "test_only": True}
```

- [ ] **Step 4: 实现 `tests/classic_acceptance_fixtures.py`**

```python
"""Shared fixtures for the classic-texts manual-acceptance tooling tests.

Everything runs offline: tiny synthetic datasets live under gitignored .tmp/
(NEVER pytest tmp dirs - sandbox permission issues); the big fake dataset
reproduces the EXACT real populations/strata/boundary/zero-chapter counts;
real-data tests read the frozen candidate commit via `git show` and run the
full production frozen-input lock. Not collected by pytest (no test_ prefix).
"""
import json
import os
import shutil
import subprocess
import sys
import types
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT
SCRIPTS = ROOT / "scripts"
COMMIT = "80bc630396f31c6b6c122e49ef97f6d912e6f636"
CHAPTER_MANIFEST = ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json"
IDENTITY_MANIFEST = ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-candidate-identity-manifest.json"
ANCHOR_RECORD = ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-freeze-anchor-record.json"

sys.path.insert(0, str(SCRIPTS))
import classic_acceptance_common as c  # noqa: E402


def rmtree_force(path):
    def _chmod_retry(func, p, _exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_chmod_retry)


def tmp_dir(prefix):
    path = ROOT / ".tmp" / f"{prefix}_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


# Bounded per-invocation wall time for test CLI subprocesses. This MUST stay
# BELOW the CI pytest per-test gate (--timeout=120) BY A COMFORTABLE MARGIN --
# and, crucially, that margin must also cover the cleanup work that runs after
# the bound fires. A wedged CLI is killed (and its whole process tree reaped)
# by THIS bound BEFORE pytest aborts the test; if pytest interrupted us first
# the cleanup would never run and the CLI + any frozen-chain checker it spawned
# would be orphaned. The post-timeout path is itself fully bounded and
# FAIL-CLOSED: every cleanup step (tree-kill, output drain) draws from ONE
# SHARED CLEANUP_TIMEOUT_SECONDS deadline instead of a fresh budget per step,
# so total worst-case wall time is timeout + CLEANUP_TIMEOUT_SECONDS =
# 100 + 5 = 105s, safely under 120s. The verdicts are also fail-closed: an
# uncertain tool result (timeout, nonzero exit) never counts as "process
# dead" or "tree reaped". Production invocations re-run the frozen lock (F18)
# once and measure ~70-75s.
CLI_TIMEOUT_SECONDS = 100
CLEANUP_TIMEOUT_SECONDS = 5


def _remaining(deadline):
    # Time left on a shared cleanup deadline; 0 once exhausted, so each
    # subsequent cleanup step gets at most the leftover -- never a fresh
    # CLEANUP_TIMEOUT_SECONDS budget that would stack serially.
    return max(0.0, deadline - time.monotonic())


def _script_path(script):
    # Accept either a bare script name (resolved under SCRIPTS) or an absolute
    # Path (e.g. a temp hang script created by a test).
    path = Path(script)
    return path if path.is_absolute() else SCRIPTS / path


def _bounded_subprocess(argv, timeout):
    # subprocess.run with an explicit, SHORT timeout: never let an external
    # housekeeping command (taskkill / tasklist) block the cleanup path for
    # longer than the cleanup budget. Returns the result, or None on timeout.
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def _kill_process_tree(proc, deadline):
    # Terminate the spawned CLI AND every descendant (a CLI may itself spawn
    # the frozen-chain checker). taskkill /T walks the tree on Windows; on
    # POSIX we send SIGKILL to the process group we put the child in. Every
    # external call draws from the SHARED deadline, and the verdict is
    # fail-closed: True only when the whole tree is PROVABLY dead (taskkill
    # exits 0 / SIGKILL delivered); a tool timeout (None), a nonzero exit, or
    # a spawn failure is UNCERTAIN and returns False -- the caller must not
    # report a reaped tree. proc.kill() on the direct child is always
    # attempted as a last resort but never upgrades the verdict by itself.
    try:
        if os.name == "nt":
            r = _bounded_subprocess(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                    _remaining(deadline))
            tree_ok = bool(r) and r.returncode == 0
        else:
            import signal
            # The child was started with start_new_session=True, so its PGID
            # IS proc.pid. Kill by that KNOWN pgid directly -- NOT getpgid:
            # once the group leader (the direct child) has exited but a
            # descendant still sits in the group, getpgid(proc.pid) raises
            # ProcessLookupError and the code below would wrongly report the
            # tree as reaped (a false-green). killpg(proc.pid) reaches the
            # whole group even without the leader, and only raises ESRCH when
            # the group has no member left -- which genuinely proves death.
            os.killpg(proc.pid, signal.SIGKILL)
            tree_ok = True
    except ProcessLookupError:
        tree_ok = True  # the pid/group is already gone: provably dead
    except (PermissionError, OSError):
        tree_ok = False  # could not deliver the kill: uncertain
    try:
        proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass
    return tree_ok


def _drain_output(proc, deadline):
    # Drain the killed child's pipes within the SAME shared deadline so a
    # grandchild that holds the pipe open cannot block us indefinitely, and
    # so the drain never spends a second full cleanup budget; fall back to
    # whatever was captured so far. proc is already being torn down.
    try:
        return proc.communicate(timeout=_remaining(deadline))
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            return proc.communicate(timeout=_remaining(deadline))
        except subprocess.TimeoutExpired:
            return "", ""


def _pid_alive(pid):
    # Fail-closed liveness probe: only a SUCCESSFUL tasklist (exit 0 --
    # verified: "no tasks running" is also exit 0) whose output lacks the pid
    # proves death. A tool timeout (None), a nonzero exit, or a spawn failure
    # is UNCERTAIN and must be reported ALIVE, so a caller can never mistake
    # "unknown" for "dead" (no false-green cleanup checks).
    if not pid:
        return False
    if os.name == "nt":
        r = _bounded_subprocess(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                                CLEANUP_TIMEOUT_SECONDS)
        if r is None or r.returncode != 0:
            return True
        return str(int(pid)) in r.stdout
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def run_argv_result(argv, timeout=CLI_TIMEOUT_SECONDS):
    """Bounded runner for a FULLY-ASSEMBLED argv (must already include the
    python interpreter as argv[0]). Same timeout/process-tree contract as
    run_cli_result; use this when a test builds the argv list itself. The
    timeout AND the post-timeout cleanup are both bounded (one shared
    CLEANUP_TIMEOUT_SECONDS budget), so this returns in at most timeout +
    CLEANUP_TIMEOUT_SECONDS wall time and never hands an unbounded wait back
    to the pytest 120s gate. .cleanup_ok is fail-closed: True only when the
    tree-kill provably succeeded; a timeout/nonzero tool result reports
    False instead of claiming a reaped tree."""
    popen_kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding="utf-8", errors="replace")
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen([str(x) for x in argv], **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return types.SimpleNamespace(returncode=proc.returncode, stdout=stdout,
                                     stderr=stderr, pid=proc.pid, timed_out=False,
                                     cleanup_ok=True)
    except subprocess.TimeoutExpired:
        # ONE shared cleanup budget: the tree-kill and the output drain both
        # draw from the same deadline, so the post-timeout path costs at most
        # CLEANUP_TIMEOUT_SECONDS once (not once per step).
        deadline = time.monotonic() + CLEANUP_TIMEOUT_SECONDS
        cleanup_ok = _kill_process_tree(proc, deadline)
        stdout, stderr = _drain_output(proc, deadline)
        return types.SimpleNamespace(returncode=proc.returncode, stdout=stdout,
                                     stderr=stderr, pid=proc.pid, timed_out=True,
                                     cleanup_ok=cleanup_ok)


def run_cli_result(script, *args, timeout=CLI_TIMEOUT_SECONDS):
    """Run a CLI subprocess with a BOUNDED timeout and full process-tree
    cleanup. Returns a result namespace with .returncode / .stdout / .stderr /
    .pid / .timed_out / .cleanup_ok -- usable by BOTH success callers and
    expected-failure callers (which assert .returncode != 0). On timeout the
    CLI and every descendant are killed and reaped, then .timed_out is True
    (no exception): the timeout/process-tree test asserts the child+
    grandchild PIDs are gone; .cleanup_ok is fail-closed -- False when the
    tree-kill itself timed out or failed, never a silent false-green."""
    argv = [sys.executable, str(_script_path(script)), *(str(x) for x in args)]
    return run_argv_result(argv, timeout=timeout)


def run_cli(script, *args, timeout=CLI_TIMEOUT_SECONDS):
    res = run_cli_result(script, *args, timeout=timeout)
    cmd = f"{script} {' '.join(map(str, args))}"
    assert not res.timed_out, f"{cmd} timed out after {timeout}s (process tree killed):\n{res.stdout}\n{res.stderr}"
    assert res.returncode == 0, f"{cmd} failed:\n{res.stdout}\n{res.stderr}"
    return res.stdout


def sha256_file(path):
    """F20: raw on-disk byte SHA for review-chain artifacts. No LF
    normalization (CRLF tampering must change the binding SHA)."""
    return c.sha256_bytes(Path(path).read_bytes())


def write_json(path, obj):
    Path(path).write_bytes(c.serialize_json(obj))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finding(severity, category):
    return {"severity": severity, "category": category, "evidence_text": "evidence",
            "note": "", "reviewer": "reviewer-1", "reviewed_at": "2026-08-23T00:00:00+08:00"}


def critical():
    return finding("critical", "distortion")


def minor():
    return finding("minor", "wording")


# tiny dataset: 4 sanmingtonghui chapters (1,2,3 in stratum 1; 85 in stratum 2;
# ch1 is a boundary chapter) + 8 rules/8 mcqs per other book.
TINY_CHAPTERS = {1: (2, 2), 2: (6, 6), 3: (6, 6), 85: (6, 6)}
TINY_SNAP = "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/" + "e" * 64


def build_tiny_dataset(base):
    base = Path(base)
    rules, mcqs, chapters = [], [], []
    for ci, (nr, nm) in sorted(TINY_CHAPTERS.items()):
        raw_rel = f"{TINY_SNAP}/extracted/raw_{ci:03d}.txt"
        p = base / raw_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"第{ci}章 原文 甲乙丙丁。\n", encoding="utf-8", newline="\n")
        rule_ids = [f"tiny_{ci:03d}_r{i:03d}" for i in range(nr)]
        mcq_ids = [f"tiny_{ci:03d}_m{i:03d}" for i in range(nm)]
        chapters.append({"chapter_index": ci, "title": f"第{ci}章", "is_legacy": ci <= 80,
                         "raw_source_path": raw_rel, "rule_ids": rule_ids, "mcq_ids": mcq_ids,
                         "rule_count": nr, "mcq_count": nm,
                         "zero_rule": nr == 0, "zero_mcq": nm == 0})
        for i in range(nr):
            rules.append({"id": f"tiny_{ci:03d}_r{i:03d}", "category": "测试", "subject": "测试",
                          "condition": "测试条件", "rule": f"第{ci}章规则{i}。",
                          "original_text": "原文 甲乙丙丁", "source_book": "三命通会",
                          "source_chapter": str(ci)})
        for i in range(nm):
            mcqs.append({"question": f"第{ci}章问题{i}？",
                         "options": {"A": "对", "B": "错", "C": "否", "D": "疑"},
                         "answer": "A", "explanation": "解释。", "difficulty": "初级",
                         "category": "测试", "source_rule_id": f"tiny_{ci:03d}_r000",
                         "id": f"tiny_{ci:03d}_m{i:03d}"})
    sm_dir = base / "knowledge_base" / "classic_texts" / "sanmingtonghui"
    write_json(sm_dir / "all_rules.json", rules)
    (sm_dir / "all_mcq.jsonl").write_bytes(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mcqs).encode("utf-8"))
    for book in ("qiongtongbaojian", "ditiansui", "zipingzhenquan"):
        bdir = base / "knowledge_base" / "classic_texts" / book
        bdir.mkdir(parents=True, exist_ok=True)
        brules = [{"id": f"{book}_r{i:03d}", "category": "测试", "subject": "测试",
                   "condition": "测试", "rule": f"{book}规则{i}。",
                   "original_text": f"{book}原文{i}", "source_book": book,
                   "source_chapter": f"一、{book}节{i}"} for i in range(8)]
        bmcqs = [{"question": f"{book}问题{i}？",
                  "options": {"A": "对", "B": "错", "C": "否", "D": "疑"},
                  "answer": "A", "explanation": "解释。", "difficulty": "初级",
                  "category": "测试", "source_rule_id": f"{book}_r{i:03d}",
                  "id": f"{book}_m{i:03d}"} for i in range(8)]
        write_json(bdir / "all_rules.json", brules)
        (bdir / "all_mcq.jsonl").write_bytes(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in bmcqs).encode("utf-8"))
    (base / "knowledge_base" / "classic_texts" / "qiongtongbaojian"
     / "quarantine_rules.jsonl").write_bytes(b'{"id": "tiny_q_1"}\n')
    chman = {"schema_version": "1.0", "chapter_count": len(chapters),
             "zero_rule_chapters": [], "zero_mcq_chapters": [], "chapters": chapters}
    chman_path = base / "chapter_manifest.json"
    write_json(chman_path, chman)
    return base, chman_path
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_sampling.py -q`
Expected: 全部通过（含真实冻结链 `--check`，约 1 分钟）

- [ ] **Step 6: Commit**

```bash
git add scripts/classic_acceptance_common.py tests/classic_acceptance_fixtures.py tests/test_classic_acceptance_sampling.py
git commit -m "feat(acceptance): shared module, hash keys, frozen-input lock, strict CLI"
```

---

### Task 2: 确定性抽样 + sample manifest（`sample` 子命令）

**Files:**
- Create: `scripts/classic_acceptance_sampling.py`
- Test: `tests/test_classic_acceptance_sampling.py`（追加）

- [ ] **Step 1: 写失败测试（tiny 单测 + 真实数据集成）**

向 `tests/test_classic_acceptance_sampling.py` 追加：

```python
import classic_acceptance_sampling as sampling


def test_tiny_sample_totals_and_disjoint():
    base = fixtures.tmp_dir("acceptance_tiny")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        manifest = sampling.build_sample_manifest(
            man, source, {"kind": "dir", "root": str(data), "test_only": True}, chman_sha)
        assert manifest["test_only"] is True
        assert manifest["totals"] == {"rule": {"random": 25, "boundary": 2, "total": 27},
                                      "mcq": {"random": 25, "boundary": 2, "total": 27}}
        assert manifest["k_table"]["sanmingtonghui"] == {"rule": {"1": 5, "2": 5},
                                                         "mcq": {"1": 5, "2": 5}}
        assert manifest["boundary_samples"]["sanmingtonghui"]["rule"] == \
            ["tiny_001_r000", "tiny_001_r001"]
        bset = (set(manifest["boundary_samples"]["sanmingtonghui"]["rule"])
                | set(manifest["boundary_samples"]["sanmingtonghui"]["mcq"]))
        for book in c.BOOKS:
            for item_type in ("rule", "mcq"):
                for ids in manifest["samples"][book][item_type].values():
                    assert not (set(ids) & bset)
        again = sampling.build_sample_manifest(
            man, source, {"kind": "dir", "root": str(data), "test_only": True}, chman_sha)
        assert c.serialize_json(again) == c.serialize_json(manifest)
        eligible = [f"tiny_002_r{i:03d}" for i in range(6)] + \
                   [f"tiny_003_r{i:03d}" for i in range(6)]
        expected = sorted(sorted(eligible,
                                 key=lambda i: (c.sample_score("sanmingtonghui", "rule", 1, i), i))[:5])
        assert manifest["samples"]["sanmingtonghui"]["rule"]["1"] == expected
        assert manifest["chapter_manifest_sha256"] == fixtures.sha256_file(chman_path)
        assert manifest["normalization"]["function"] == "normalize_for_source_match"
    finally:
        fixtures.rmtree_force(base)


def test_load_chapter_manifest_rejects_bad_structures():
    base = fixtures.tmp_dir("acceptance_chman")
    try:
        bad_dup = {"chapters": [
            {"chapter_index": 1, "raw_source_path": "a.txt", "rule_ids": ["r1"], "mcq_ids": []},
            {"chapter_index": 1, "raw_source_path": "a.txt", "rule_ids": [], "mcq_ids": []}]}
        p = base / "dup.json"
        fixtures.write_json(p, bad_dup)
        with pytest.raises(RuntimeError, match="duplicate chapter_index"):
            sampling.load_chapter_manifest(p)
        bad_twice = {"chapters": [
            {"chapter_index": 1, "raw_source_path": "a.txt", "rule_ids": ["r1"], "mcq_ids": []},
            {"chapter_index": 2, "raw_source_path": "b.txt", "rule_ids": ["r1"], "mcq_ids": []}]}
        p2 = base / "twice.json"
        fixtures.write_json(p2, bad_twice)
        with pytest.raises(RuntimeError, match="multiple chapters"):
            sampling.load_chapter_manifest(p2)
    finally:
        fixtures.rmtree_force(base)


def test_tiny_cli_sample_strict_flags():
    base = fixtures.tmp_dir("acceptance_tiny_cli")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        out = base / "out"
        # unknown flag rejected
        r = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "sample", "--bogus", "x",
            "--chapter-manifest", str(chman_path),
            "--data-root", str(data), "--out", str(out))
        assert not r.timed_out and r.returncode != 0
        assert "unknown flag" in r.stdout + r.stderr
        # missing value rejected
        r = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "sample", "--chapter-manifest",
            "--data-root", str(data), "--out", str(out))
        assert not r.timed_out and r.returncode != 0
        assert "requires a value" in r.stdout + r.stderr
        # positional rejected
        r = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "sample", "positional",
            "--chapter-manifest", str(chman_path),
            "--data-root", str(data), "--out", str(out))
        assert not r.timed_out and r.returncode != 0
        assert "unexpected positional" in r.stdout + r.stderr
        # happy path
        fixtures.run_cli("classic_acceptance_sampling.py", "sample",
                         "--chapter-manifest", str(chman_path),
                         "--data-root", str(data), "--out", str(out))
        manifest = fixtures.read_json(out / "sample_manifest_v1.json")
        assert manifest["totals"]["rule"]["total"] == 27
        assert manifest["test_only"] is True
        assert manifest["generator"]["path"] == "scripts/classic_acceptance_sampling.py"
        assert len(manifest["generator"]["sha256_lf"]) == 64
        assert len(manifest["generator"]["blob_oid"]) == 40
        assert manifest["seed"] == {"hex": "00a5c0de20260820", "decimal": 46655431411894304}
    finally:
        fixtures.rmtree_force(base)


@pytest.fixture(scope="module")
def real_manifest():
    man, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    desc = {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False}
    return sampling.build_sample_manifest(man, source, desc, chman_sha), chman_sha


def test_real_totals_and_k(real_manifest):
    manifest, _ = real_manifest
    assert manifest["totals"] == {"rule": {"random": 342, "boundary": 267, "total": 609},
                                  "mcq": {"random": 188, "boundary": 194, "total": 382}}
    assert manifest["k_table"]["sanmingtonghui"]["rule"] == {
        "1": 46, "2": 5, "3": 21, "4": 9, "5": 40, "6": 38, "7": 33, "8": 15, "9": 37}
    assert manifest["k_table"]["sanmingtonghui"]["mcq"] == {
        "1": 16, "2": 5, "3": 12, "4": 5, "5": 25, "6": 24, "7": 17, "8": 7, "9": 17}
    assert manifest["k_table"]["qiongtongbaojian"] == {"rule": {"1": 69}, "mcq": {"1": 42}}
    assert manifest["k_table"]["ditiansui"] == {"rule": {"1": 24}, "mcq": {"1": 13}}
    assert manifest["k_table"]["zipingzhenquan"] == {"rule": {"1": 5}, "mcq": {"1": 5}}
    assert manifest["test_only"] is False


def test_real_boundary_and_disjoint(real_manifest):
    manifest, _ = real_manifest
    chman = json.loads(c.lf_bytes(fixtures.CHAPTER_MANIFEST.read_bytes()).decode("utf-8"))
    expected = {"rule": [], "mcq": []}
    for ch in chman["chapters"]:
        if ch["chapter_index"] in c.BOUNDARY_CHAPTERS:
            expected["rule"].extend(ch["rule_ids"])
            expected["mcq"].extend(ch["mcq_ids"])
    assert manifest["boundary_samples"]["sanmingtonghui"] == {
        "rule": sorted(expected["rule"]), "mcq": sorted(expected["mcq"])}
    bset = set(expected["rule"]) | set(expected["mcq"])
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in manifest["samples"][book][item_type].values():
                assert not (set(ids) & bset)


def test_real_bindings_to_frozen_chain(real_manifest):
    manifest, chman_sha = real_manifest
    anchor = json.loads(fixtures.ANCHOR_RECORD.read_text(encoding="utf-8"))
    assert chman_sha == anchor["manifests"]["2026-08-20-classic-texts-chapter-identity-manifest.json"]
    identity_sha = c.sha256_bytes(c.lf_bytes(fixtures.IDENTITY_MANIFEST.read_bytes()))
    assert identity_sha == anchor["manifests"]["2026-08-20-classic-texts-candidate-identity-manifest.json"]
    identity = json.loads(fixtures.IDENTITY_MANIFEST.read_text(encoding="utf-8"))
    frozen = {f["path"]: f["sha256_lf"] for f in identity["groups"]["output_files"]}
    assert manifest["data_file_sha256_lf"] == frozen
    common_path = fixtures.SCRIPTS / "classic_acceptance_common.py"
    assert manifest["normalization"]["sha256_lf"] == c.sha256_bytes(c.lf_bytes(common_path.read_bytes()))


def test_real_determinism(real_manifest):
    manifest, _ = real_manifest
    man, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    again = sampling.build_sample_manifest(
        man, source, {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False}, chman_sha)
    assert c.serialize_json(again) == c.serialize_json(manifest)


def test_validate_sample_manifest_roundtrip_cross_mode_and_tamper():
    # F19 reconstruct-and-compare: only a manifest the current code would
    # produce from THIS chapter manifest/source validates; right-shaped
    # hand-crafted or tampered manifests fail closed.
    import copy
    base = fixtures.tmp_dir("acceptance_val_sm")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        # roundtrip: the manifest just built validates in fake mode (fake mode
        # binds the fake chapter manifest's ACTUAL LF SHA, P0-1)
        sampling.validate_sample_manifest(sm, man, source, desc, chman_sha,
                                          expected_test_only=True)
        # cross-mode: retagged test_only=False rejected in fake mode
        with pytest.raises(RuntimeError, match="cross-mode"):
            sampling.validate_sample_manifest(dict(sm, test_only=False), man,
                                              source, desc, chman_sha,
                                              expected_test_only=True)
        # fake artifacts cannot enter production mode even when retagged
        # test_only=False: production requires the FROZEN chapter manifest,
        # and the fake chapter manifest's SHA is not it (P0-1)
        with pytest.raises(RuntimeError, match="frozen chapter manifest"):
            sampling.validate_sample_manifest(dict(sm, test_only=False), man,
                                              source, desc, chman_sha,
                                              expected_test_only=False)
        # a right-shaped hand-crafted manifest (empty k_table/samples, as the
        # old shape-only validator accepted) does NOT validate
        hand = {"schema_version": "1.0", "kind": "sample_manifest_v1",
                "algorithm_version": "1.0",
                "seed": {"hex": c.SEED_BYTES.hex(), "decimal": c.SEED_DECIMAL},
                "data_source": desc, "test_only": True,
                "chapter_manifest_sha256": chman_sha,
                "data_file_sha256_lf": {},
                "generator": sm["generator"],
                "normalization": sm["normalization"],
                "strata": [], "k_table": {b: {} for b in c.BOOKS},
                "boundary_chapters": c.BOUNDARY_CHAPTERS,
                "samples": {b: {} for b in c.BOOKS},
                "boundary_samples": {b: {"rule": [], "mcq": []} for b in c.BOOKS},
                "totals": {}}
        with pytest.raises(RuntimeError, match="reconstructed"):
            sampling.validate_sample_manifest(hand, man, source, desc, chman_sha,
                                              expected_test_only=True)
        # every tampered field is rejected: k_table, sample ids, totals,
        # boundary set, data-file SHA, generator identity, chapter SHA
        for mutate in (
            lambda m: m["k_table"]["sanmingtonghui"]["rule"].__setitem__("1", 4),
            lambda m: m["samples"]["sanmingtonghui"]["rule"]["1"].append("tiny_002_r005"),
            lambda m: m["totals"]["rule"].__setitem__("total", 26),
            lambda m: m["boundary_samples"]["sanmingtonghui"]["rule"].append("tiny_001_r000"),
            lambda m: m["data_file_sha256_lf"].__setitem__("x", "0" * 64),
            lambda m: m["generator"].__setitem__("sha256_lf", "a" * 64),
            lambda m: m.__setitem__("chapter_manifest_sha256", "0" * 64),
        ):
            bad = copy.deepcopy(sm)
            mutate(bad)
            with pytest.raises(RuntimeError):
                sampling.validate_sample_manifest(bad, man, source, desc, chman_sha,
                                                  expected_test_only=True)
    finally:
        fixtures.rmtree_force(base)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_classic_acceptance_sampling.py -q`
Expected: `ModuleNotFoundError: No module named 'classic_acceptance_sampling'`

- [ ] **Step 3: 实现 `scripts/classic_acceptance_sampling.py`（本任务 `sample`；`expand` 由 Task 7 追加）**

```python
"""Deterministic sampling for the classic-texts manual acceptance (design
v4.6.1, Approved LOCAL_ONLY; section 4 initial sampling, section 6.3 expansion).

Subcommands:
    sample   initial sample manifest: per-stratum random samples + mandatory
             boundary items (all rules/MCQs of the boundary chapters)
    expand   (added later) expansion-round manifest for (book, type) pairs a
             decision report marked EXPAND

Deterministic: sha256 over length-prefixed fields with the frozen SEED;
identical inputs produce byte-identical manifests (LF JSON). k is always
derived from the frozen formula (never a hand-listed table). Production mode
runs the section 12.1 frozen-input lock; fake mode marks test_only=true.
LOCAL_ONLY tooling: no model API, no Phase 8, no formal gate, no remote.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import classic_acceptance_common as c

SAMPLING_ALGO_VERSION = "1.0"
GENERATOR_PATH = "scripts/classic_acceptance_sampling.py"
SAMPLE_FLAGS = {"chapter-manifest", "out", "candidate-commit", "data-root"}


def stratum_of(book, chapter_index):
    if book != "sanmingtonghui":
        return 1
    for index, lo, hi in c.SANMING_STRATA:
        if lo <= chapter_index <= hi:
            return index
    raise RuntimeError(f"chapter {chapter_index!r} outside sanmingtonghui strata")


def load_chapter_manifest(path):
    data = c.lf_bytes(Path(path).read_bytes())
    man = json.loads(data.decode("utf-8"))
    chapters = man.get("chapters")
    c.require(isinstance(chapters, list) and chapters,
              "chapter manifest: chapters[] missing/empty")
    seen_ci, seen_rule, seen_mcq = set(), set(), set()
    for ch in chapters:
        ci = ch.get("chapter_index")
        c.require(isinstance(ci, int), f"chapter_index not int: {ci!r}")
        c.require(ci not in seen_ci, f"duplicate chapter_index {ci}")
        seen_ci.add(ci)
        c.require(ch.get("raw_source_path"), f"chapter {ci}: raw_source_path missing")
        for key in ("rule_ids", "mcq_ids"):
            c.require(isinstance(ch.get(key), list), f"chapter {ci}: {key} not a list")
        for rid in ch["rule_ids"]:
            c.require(rid not in seen_rule, f"rule {rid} mapped to multiple chapters")
            seen_rule.add(rid)
        for mid in ch["mcq_ids"]:
            c.require(mid not in seen_mcq, f"mcq {mid} mapped to multiple chapters")
            seen_mcq.add(mid)
    return man, c.sha256_bytes(data)


def load_universe(chapter_manifest, source):
    universe = {}
    file_shas = {}
    sm_rules, sm_mcqs = {}, {}
    for ch in chapter_manifest["chapters"]:
        for rid in ch["rule_ids"]:
            sm_rules[rid] = ch["chapter_index"]
        for mid in ch["mcq_ids"]:
            sm_mcqs[mid] = ch["chapter_index"]
    universe[("sanmingtonghui", "rule")] = sm_rules
    universe[("sanmingtonghui", "mcq")] = sm_mcqs
    for book in c.BOOKS:
        rules_rel = f"{c.BOOK_ROOT}/{book}/all_rules.json"
        mcq_rel = f"{c.BOOK_ROOT}/{book}/all_mcq.jsonl"
        rules_bytes = source.read_bytes(rules_rel)
        file_shas[rules_rel] = c.sha256_bytes(c.lf_bytes(rules_bytes))
        file_shas[mcq_rel] = c.sha256_bytes(c.lf_bytes(source.read_bytes(mcq_rel)))
        rule_ids = [r["id"] for r in json.loads(rules_bytes.decode("utf-8"))]
        mcq_ids = [m["id"] for m in c.load_jsonl(source, mcq_rel)]
        c.require(len(rule_ids) == len(set(rule_ids)), f"{book}: duplicate rule ids")
        c.require(len(mcq_ids) == len(set(mcq_ids)), f"{book}: duplicate mcq ids")
        if book == "sanmingtonghui":
            c.require(set(rule_ids) == set(sm_rules),
                      "sanmingtonghui: all_rules.json ids != chapter manifest rule_ids")
            c.require(set(mcq_ids) == set(sm_mcqs),
                      "sanmingtonghui: all_mcq.jsonl ids != chapter manifest mcq_ids")
        else:
            universe[(book, "rule")] = {iid: None for iid in rule_ids}
            universe[(book, "mcq")] = {iid: None for iid in mcq_ids}
    return universe, file_shas


def boundary_items(chapter_manifest):
    out = {"rule": [], "mcq": []}
    for ch in chapter_manifest["chapters"]:
        if ch["chapter_index"] in c.BOUNDARY_CHAPTERS:
            out["rule"].extend(ch["rule_ids"])
            out["mcq"].extend(ch["mcq_ids"])
    return {"rule": sorted(out["rule"]), "mcq": sorted(out["mcq"])}


def compute_k_table(book, item_type, population):
    pops = defaultdict(int)
    for iid, chapter in population.items():
        pops[stratum_of(book, chapter)] += 1
    pct = c.K_RULE_PCT if item_type == "rule" else c.K_MCQ_PCT
    return {s: c.compute_k(n, pct) for s, n in sorted(pops.items())}


def take_random_sample(book, item_type, population, exclude, k_table):
    eligible = defaultdict(list)
    for iid, chapter in population.items():
        if iid not in exclude:
            eligible[stratum_of(book, chapter)].append(iid)
    samples = {}
    for stratum in sorted(eligible):
        ranked = sorted(eligible[stratum],
                        key=lambda iid: (c.sample_score(book, item_type, stratum, iid), iid))
        k = k_table[stratum]
        c.require(len(ranked) >= k,
                  f"{book}/{item_type} stratum {stratum}: only {len(ranked)} non-boundary for k={k}")
        samples[stratum] = sorted(ranked[:k])
    return samples


def generator_identity():
    data = c.lf_bytes(Path(__file__).read_bytes())
    result = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parents[1]), "hash-object", "--stdin"],
        input=data, capture_output=True)
    c.require(result.returncode == 0, "git hash-object failed")
    return {"path": GENERATOR_PATH, "sha256_lf": c.sha256_bytes(data),
            "blob_oid": result.stdout.decode("utf-8").strip(),
            "algorithm_version": SAMPLING_ALGO_VERSION}


def build_sample_manifest(chapter_manifest, source, source_desc, chman_sha):
    universe, file_shas = load_universe(chapter_manifest, source)
    boundary = boundary_items(chapter_manifest)
    samples, k_table, strata_info = {}, {}, {}
    for book in c.BOOKS:
        samples[book] = {}
        k_table[book] = {}
        populations = {}
        for item_type in ("rule", "mcq"):
            population = universe[(book, item_type)]
            pops = defaultdict(int)
            for iid, chapter in population.items():
                pops[stratum_of(book, chapter)] += 1
            populations[item_type] = pops
            kt = compute_k_table(book, item_type, population)
            k_table[book][item_type] = {str(s): k for s, k in kt.items()}
            exclude = set(boundary["rule"] if item_type == "rule" else boundary["mcq"])
            picked = take_random_sample(book, item_type, population, exclude, kt)
            samples[book][item_type] = {str(s): ids for s, ids in picked.items()}
        strata_info[book] = [
            {"index": s,
             "population": {"rule": populations["rule"].get(s, 0),
                            "mcq": populations["mcq"].get(s, 0)}}
            for s in sorted(set(populations["rule"]) | set(populations["mcq"]))]
    totals = {}
    for item_type in ("rule", "mcq"):
        random_total = sum(len(ids) for book in c.BOOKS
                           for ids in samples[book][item_type].values())
        totals[item_type] = {"random": random_total, "boundary": len(boundary[item_type]),
                             "total": random_total + len(boundary[item_type])}
    boundary_by_book = {book: {"rule": [], "mcq": []} for book in c.BOOKS}
    boundary_by_book["sanmingtonghui"] = boundary
    return {
        "schema_version": "1.0",
        "kind": "sample_manifest_v1",
        "algorithm_version": SAMPLING_ALGO_VERSION,
        "seed": {"hex": c.SEED_BYTES.hex(), "decimal": c.SEED_DECIMAL},
        "data_source": source_desc,
        "test_only": bool(source_desc.get("test_only")),
        "chapter_manifest_sha256": chman_sha,
        "data_file_sha256_lf": file_shas,
        "generator": generator_identity(),
        "normalization": {
            "module": "scripts/classic_acceptance_common.py",
            "function": "normalize_for_source_match",
            "sha256_lf": c.sha256_bytes(c.lf_bytes(
                (Path(__file__).parent / "classic_acceptance_common.py").read_bytes())),
        },
        "strata": strata_info,
        "k_table": k_table,
        "boundary_chapters": c.BOUNDARY_CHAPTERS,
        "samples": samples,
        "boundary_samples": boundary_by_book,
        "totals": totals,
    }


# ---- F19: reconstruct-and-compare manifest validators (fail-closed) ----
#
# Shape-only checks are NOT sufficient: a hand-crafted or cross-mode-retagged
# manifest can have the right keys with bogus k/ids/totals/SHAs. The validators
# live in this module because they must rebuild the expected manifest from the
# SAME code path that generates it, then compare canonical serialized bytes.
# Every field is thus covered: k recomputation, sample ids/counts, the full
# boundary set, dedup, totals, data-file SHAs, and the current-generator
# identity. Production passes the frozen chapter-manifest SHA; fake mode passes
# the LF SHA of the fake chapter manifest actually used.

def validate_sample_manifest(sample, chapter_manifest, source, source_desc,
                             chman_sha, expected_test_only):
    """F19: fully validate a sample_manifest_v1 by reconstruct-and-compare.

    The caller passes the SAME (chapter_manifest, source, source_desc,
    chman_sha) it resolved for the run: production resolves them through the
    F18 frozen lock (so chman_sha IS the frozen chapter-manifest LF SHA); fake
    mode resolves the --data-root DirSource and the fake chapter manifest
    (so chman_sha is the ACTUAL fake chapter-manifest LF SHA, not the frozen
    one). expected_test_only is True for fake and False for production."""
    c.require(isinstance(sample, dict), "sample manifest: not an object")
    test_only = sample.get("test_only")
    c.require(isinstance(test_only, bool), "sample manifest: test_only missing/not bool")
    c.require(test_only is expected_test_only,
              f"sample manifest test_only={test_only} not allowed in "
              f"{'fake' if expected_test_only else 'production'} mode (cross-mode rejection)")
    c.require(sample.get("kind") == "sample_manifest_v1", "sample manifest: wrong kind")
    if not expected_test_only:
        c.require(chman_sha == c.FROZEN_CHAPTER_MANIFEST_SHA,
                  "sample manifest: chapter manifest is not the frozen chapter manifest")
    c.require(sample.get("chapter_manifest_sha256") == chman_sha,
              "sample manifest: chapter_manifest_sha256 does not match the supplied chapter manifest")
    expected = build_sample_manifest(chapter_manifest, source, source_desc, chman_sha)
    c.require(c.serialize_json(sample) == c.serialize_json(expected),
              "sample manifest: does not match the manifest reconstructed from "
              "the current chapter manifest/source (k_table, sample ids, "
              "boundary set, totals, data-file SHAs, or generator identity differ)")


def cmd_sample(argv):
    flags, _ = c.parse_flags(argv, allowed=SAMPLE_FLAGS)
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    # F18: build_source runs verify_frozen_inputs (incl. CLI chapter-manifest
    # SHA check) BEFORE any data read. expected_test_only is derived from mode.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = load_chapter_manifest(chman_path)
    manifest = build_sample_manifest(chapter_manifest, source, source_desc, chman_sha)
    # F19: self-validate the produced manifest against the resolved mode by
    # reconstructing from the SAME chapter manifest/source and comparing bytes.
    # In fake mode chman_sha is the fake chapter manifest's actual LF SHA.
    validate_sample_manifest(manifest, chapter_manifest, source, source_desc,
                             chman_sha, expected_test_only=is_fake)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = c.serialize_json(manifest)
    path = out_dir / "sample_manifest_v1.json"
    path.write_bytes(payload)
    print("sample manifest:", path)
    print("sha256:", c.sha256_bytes(payload))
    print("test_only:", manifest["test_only"], "totals:", manifest["totals"])


def main(argv):
    c.require(argv, "usage: classic_acceptance_sampling.py <sample|expand> [flags]")
    cmd = argv[0]
    try:
        if cmd == "sample":
            cmd_sample(argv[1:])
        else:
            raise RuntimeError(f"unknown subcommand: {cmd!r} (expected sample|expand)")
    except RuntimeError as e:
        print(f"{cmd} FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_sampling.py -q`
Expected: 全部通过（含真实数据 609/382、锚点/身份绑定、生产冻结链、确定性）

- [ ] **Step 5: Commit**

```bash
git add scripts/classic_acceptance_sampling.py tests/test_classic_acceptance_sampling.py
git commit -m "feat(acceptance): deterministic initial sampling + sample manifest"
```

---

### Task 3: 审核包生成（`packet` 子命令）

**Files:**
- Create: `scripts/classic_acceptance_review.py`
- Create: `tests/test_classic_acceptance_review.py`

- [ ] **Step 1: 写失败测试（tiny packet + 真实 packet + test_only 标记）**

创建 `tests/test_classic_acceptance_review.py`：

```python
"""Tests for the classic-texts manual-acceptance review tooling (design v4.6.1).

Packet, schema validation, adjudication (F3: non_critical finding deleted but
item stays in denominator), decision state machine, final package, and the
section 12 identity/CLI/finalize hard contracts. Unit tests on tiny synthetic
fixtures; the real-packet test reads the frozen candidate commit offline.
"""
import json
import subprocess
import sys
import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import classic_acceptance_common as c
import classic_acceptance_fixtures as fixtures
import classic_acceptance_sampling as sampling
import classic_acceptance_review as review


@pytest.fixture(scope="module")
def tiny():
    base = fixtures.tmp_dir("acceptance_review_tiny")
    data, chman_path = fixtures.build_tiny_dataset(base)
    man, chman_sha = sampling.load_chapter_manifest(chman_path)
    source = c.DirSource(data)
    sm = sampling.build_sample_manifest(
        man, source, {"kind": "dir", "root": str(data), "test_only": True}, chman_sha)
    yield base, data, chman_path, man, source, sm
    fixtures.rmtree_force(base)


def test_packet_tiny(tiny):
    base, data, chman_path, man, source, sm = tiny
    sm_sha = c.sha256_bytes(c.serialize_json(sm))
    packet = review.build_packet(sm, [], man, source, sm_sha, [],
                                 {"kind": "dir", "root": str(data), "test_only": True})
    assert packet["test_only"] is True
    assert packet["sample_manifest_sha256"] == sm_sha
    assert packet["expansion_manifests_sha256"] == []
    assert len(packet["items"]) == 54
    expected_keys = set()
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                expected_keys.update((book, item_type, i) for i in ids)
    for item_type in ("rule", "mcq"):
        expected_keys.update(("sanmingtonghui", item_type, i)
                             for i in sm["boundary_samples"]["sanmingtonghui"][item_type])
    assert {(e["book"], e["type"], e["id"]) for e in packet["items"]} == expected_keys
    mcq_entries = [e for e in packet["items"] if e["type"] == "mcq"]
    assert all("source_rule" in e for e in mcq_entries)
    assert all(e["source_rule"]["id"] == e["content"]["source_rule_id"] for e in mcq_entries)
    sm_entries = [e for e in packet["items"] if e["book"] == "sanmingtonghui"]
    assert all(e["source_chapter"] in (1, 2, 3, 85) for e in sm_entries)
    assert all(e["boundary"] == (e["source_chapter"] == 1) for e in sm_entries)
    assert set(packet["chapters"]) == {"1", "2", "3", "85"}
    assert packet["chapters"]["1"]["raw_text"].startswith("第1章")
    sm_all = [e for e in packet["items"] if e["book"] == "sanmingtonghui"]
    assert all(e["original_text_in_raw"] for e in sm_all)
    assert packet["integrity"]["source_missing_chapters"] == []
    assert packet["integrity"]["missing_drift_files"] == []
    again = review.build_packet(sm, [], man, source, sm_sha, [],
                                {"kind": "dir", "root": str(data), "test_only": True})
    assert c.serialize_json(again) == c.serialize_json(packet)


def test_packet_cli_tiny(tiny):
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    out = base / "packet_out"
    fixtures.run_cli("classic_acceptance_review.py", "packet",
                     "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(out))
    packet = fixtures.read_json(out / "review_packet_v1.json")
    assert len(packet["items"]) == 54
    assert packet["test_only"] is True
    assert packet["sample_manifest_sha256"] == fixtures.sha256_file(sm_path)


@pytest.mark.parametrize("flag", [
    "expansion-manifest", "decision-report",
    "producing-primary", "producing-second", "producing-arbitration"])
def test_packet_cli_rejects_expansion_flags(flag):
    # Task 3 is non-expansion only: these flags are NOT registered, so the
    # strict CLI must reject them as unknown flags (fail-closed) rather than
    # silently ignoring them.
    argv = [sys.executable, str(fixtures.SCRIPTS / "classic_acceptance_review.py"),
            "packet", f"--{flag}", "ghost.json"]
    result = fixtures.run_argv_result(argv)
    assert not result.timed_out and result.returncode != 0, (
        f"--{flag} must be rejected without timing out")
    assert "unknown flag" in result.stdout + result.stderr, (
        f"--{flag} should fail with an unknown-flag error")


@pytest.fixture(scope="module")
def real_packet():
    man, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    sm = sampling.build_sample_manifest(
        man, source, {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False},
        chman_sha)
    packet = review.build_packet(
        sm, [], man, source, c.sha256_bytes(c.serialize_json(sm)), [],
        {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False})
    return packet, sm


def test_real_packet(real_packet):
    packet, sm = real_packet
    assert packet["test_only"] is False
    assert len(packet["items"]) == 991
    assert [z["chapter_index"] for z in packet["integrity"]["zero_output_chapters"]] == \
        [25, 26, 56, 72, 112]
    assert all(z["raw_exists"] for z in packet["integrity"]["zero_output_chapters"])
    assert packet["integrity"]["source_missing_chapters"] == []
    assert packet["integrity"]["missing_drift_files"] == []
    for e in packet["items"]:
        assert e["content"]["id"] == e["id"]
        if e["type"] == "mcq":
            assert e["source_rule"]["id"] == e["content"]["source_rule_id"]
        if e["book"] == "sanmingtonghui":
            assert packet["chapters"][str(e["source_chapter"])]["raw_text"] is not None
            assert isinstance(e["original_text_in_raw"], bool)
    assert all(ch["raw_text"] is not None for ch in packet["chapters"].values())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: `ModuleNotFoundError: No module named 'classic_acceptance_review'`

- [ ] **Step 3: 实现 `scripts/classic_acceptance_review.py`（骨架 + `packet`；后续子命令追加）**

```python
"""Review tooling for the classic-texts manual acceptance (design v4.6.1,
Approved LOCAL_ONLY; section 5 findings, section 6 decision state machine,
section 8 receipt chain, section 12 hard contracts).

Subcommands:
    packet               generate the human-review packet
    validate-primary     validate primary_review_package_v1.json
    validate-second      validate second_review_receipt_v1.json
    validate-arbitration validate arbitration_receipt_v1.json
    decide               adjudicate + run the frozen state machine
    finalize             assemble final_acceptance_package_v1.json

Integer cross-multiplication only (no floats). LF-deterministic JSON to
--out. Production mode runs the section 12.1 lock; fake mode outputs
test_only=true and finalize refuses to close. LOCAL_ONLY: no model API, no
Phase 8, no formal gate, no remote publication, no audit tag.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import classic_acceptance_common as c
import classic_acceptance_sampling as sampling

REVIEW_ALGO_VERSION = "1.0"
REVIEW_GENERATOR_PATH = "scripts/classic_acceptance_review.py"
# Task 3: base packet flags only. Expansion flags (--expansion-manifest,
# --decision-report, --producing-*) are wired in Task 7 and MUST be rejected
# here (fail-closed, strict CLI section 12.4) rather than silently ignored.
PACKET_FLAGS = {"sample-manifest", "chapter-manifest", "out",
                "candidate-commit", "data-root"}


def load_json_file(path):
    # F20: parse raw on-disk bytes (no LF normalization) for review artifacts
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def review_generator_identity():
    data = c.lf_bytes(Path(__file__).read_bytes())
    result = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parents[1]), "hash-object", "--stdin"],
        input=data, capture_output=True)
    c.require(result.returncode == 0, "git hash-object failed")
    return {"path": REVIEW_GENERATOR_PATH, "sha256_lf": c.sha256_bytes(data),
            "blob_oid": result.stdout.decode("utf-8").strip(),
            "algorithm_version": REVIEW_ALGO_VERSION}


def integrity_check(chapter_manifest, source):
    zero_chs = [ch for ch in chapter_manifest["chapters"]
                if ch.get("zero_rule") or ch.get("zero_mcq")]
    return {
        "zero_output_chapters": [
            {"chapter_index": ch["chapter_index"],
             "raw_source_path": ch["raw_source_path"],
             "raw_exists": source.exists(ch["raw_source_path"]),
             "zero_rule": bool(ch.get("zero_rule")),
             "zero_mcq": bool(ch.get("zero_mcq"))}
            for ch in zero_chs],
        "source_missing_chapters": [ch["chapter_index"] for ch in zero_chs
                                    if not source.exists(ch["raw_source_path"])],
        "drift_files": [{"path": p, "exists": source.exists(p)} for p in c.DRIFT_FILES],
        "missing_drift_files": [p for p in c.DRIFT_FILES if not source.exists(p)],
    }


def build_packet(sample_manifest, expansion_manifests, chapter_manifest, source,
                 sample_manifest_sha, expansion_shas, source_desc):
    rules_by_book, mcqs_by_book = {}, {}
    for book in c.BOOKS:
        rules_by_book[book] = {r["id"]: r for r in
                               c.load_json(source, f"{c.BOOK_ROOT}/{book}/all_rules.json")}
        mcqs_by_book[book] = {m["id"]: m for m in
                              c.load_jsonl(source, f"{c.BOOK_ROOT}/{book}/all_mcq.jsonl")}
    chapter_of = {}
    for ch in chapter_manifest["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]

    entries = []

    def add(book, item_type, iid, stratum, boundary, rnd):
        if item_type == "rule":
            content = rules_by_book[book].get(iid)
            c.require(content is not None, f"{book}: rule {iid} missing from all_rules.json")
        else:
            content = mcqs_by_book[book].get(iid)
            c.require(content is not None, f"{book}: mcq {iid} missing from all_mcq.jsonl")
        entry = {"book": book, "type": item_type, "id": iid, "stratum": stratum,
                 "boundary": boundary, "round": rnd, "content": content}
        if item_type == "mcq":
            srid = content.get("source_rule_id")
            srule = rules_by_book[book].get(srid)
            c.require(srule is not None,
                      f"{book}: mcq {iid} source_rule_id {srid!r} not found")
            entry["source_rule"] = srule
        if book == "sanmingtonghui":
            ci = chapter_of.get(iid)
            c.require(ci is not None, f"sanmingtonghui item {iid} not in chapter manifest")
            entry["source_chapter"] = ci
        entries.append(entry)

    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for s, ids in sample_manifest["samples"][book][item_type].items():
                for iid in ids:
                    add(book, item_type, iid, int(s), False, 1)
    for item_type in ("rule", "mcq"):
        for iid in sample_manifest["boundary_samples"]["sanmingtonghui"][item_type]:
            add("sanmingtonghui", item_type, iid,
                sampling.stratum_of("sanmingtonghui", chapter_of[iid]), True, 1)
    for em in expansion_manifests:
        for book, types in em["expansions"].items():
            for item_type, strata in types.items():
                for s, info in strata.items():
                    for iid in info["new_ids"]:
                        add(book, item_type, iid, int(s), False, em["round"])

    entries.sort(key=lambda e: (e["book"], e["type"], e["id"]))
    needed = {e["source_chapter"] for e in entries if e["book"] == "sanmingtonghui"}
    zero_ci = {ch["chapter_index"] for ch in chapter_manifest["chapters"]
               if ch.get("zero_rule") or ch.get("zero_mcq")}
    chapters = {}
    for ch in chapter_manifest["chapters"]:
        ci = ch["chapter_index"]
        if ci not in needed and ci not in zero_ci:
            continue
        exists_ = source.exists(ch["raw_source_path"])
        chapters[str(ci)] = {
            "title": ch.get("title"),
            "raw_source_path": ch["raw_source_path"],
            "raw_exists": exists_,
            "raw_text": (source.read_bytes(ch["raw_source_path"]).decode("utf-8")
                         if exists_ else None),
        }
    for e in entries:
        if e["book"] != "sanmingtonghui":
            continue
        raw = chapters[str(e["source_chapter"])]["raw_text"] or ""
        base_text = (e["source_rule"]["original_text"] if e["type"] == "mcq"
                     else e["content"].get("original_text", ""))
        e["original_text_in_raw"] = (c.normalize_for_source_match(base_text)
                                     in c.normalize_for_source_match(raw))
    return {
        "schema_version": "1.0",
        "kind": "review_packet_v1",
        "test_only": bool(source_desc.get("test_only")),
        "data_source": source_desc,
        "sample_manifest_sha256": sample_manifest_sha,
        "expansion_manifests_sha256": expansion_shas,
        "generator": review_generator_identity(),
        "chapters": chapters,
        "items": entries,
        "integrity": integrity_check(chapter_manifest, source),
    }


def cmd_packet(argv):
    flags, _ = c.parse_flags(argv, allowed=PACKET_FLAGS)
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    # Task 3: non-expansion path only. Expansion wiring (check_producing_
    # evidence_presence / verify_producing_report / validate_expansion_manifest
    # with --expansion-manifest/--decision-report/--producing-*) is added in
    # Task 7; those flags are rejected here by the strict CLI (fail-closed).
    # F18/F19: frozen lock first, then full manifest validation before any read.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    # F20: packet binds the sample manifest by RAW on-disk byte SHA.
    packet = build_packet(sample_manifest, [], chapter_manifest, source,
                          sm_sha, [], source_desc)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = c.serialize_json(packet)
    path = out_dir / "review_packet_v1.json"
    path.write_bytes(payload)
    print("review packet:", path)
    print("items:", len(packet["items"]), "chapters:", len(packet["chapters"]),
          "test_only:", packet["test_only"])


def main(argv):
    c.require(argv, "usage: classic_acceptance_review.py "
                     "<packet|validate-primary|validate-second|validate-arbitration|decide|finalize> [flags]")
    cmd = argv[0]
    try:
        if cmd == "packet":
            cmd_packet(argv[1:])
        else:
            raise RuntimeError(f"unknown subcommand: {cmd!r}")
    except RuntimeError as e:
        print(f"{cmd} FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: 全部通过（tiny 54 项 + 真实 991 项、零产出章、drift 齐全、test_only 标记） + `packet` CLI 负向测试拒绝 5 个扩样 flags（expansion-manifest/decision-report/producing-*）

- [ ] **Step 5: Commit**

```bash
git add scripts/classic_acceptance_review.py tests/test_classic_acceptance_review.py
git commit -m "feat(acceptance): review packet generation with source-match hint"
```

---

### Task 4: primary 包 schema 校验（`validate-primary`，含严格 CLI）

**Files:**
- Modify: `scripts/classic_acceptance_review.py`（追加）
- Test: `tests/test_classic_acceptance_review.py`（追加）

- [ ] **Step 1: 写失败测试**

向 `tests/test_classic_acceptance_review.py` 追加：

```python
def _mini_sample_manifest():
    return {
        "schema_version": "1.0", "kind": "sample_manifest_v1",
        "samples": {
            "sanmingtonghui": {"rule": {"1": ["a", "b"]}, "mcq": {"1": ["m1"]}},
            "qiongtongbaojian": {"rule": {"1": ["q1"]}, "mcq": {"1": []}},
            "ditiansui": {"rule": {"1": []}, "mcq": {"1": []}},
            "zipingzhenquan": {"rule": {"1": []}, "mcq": {"1": []}},
        },
        "boundary_samples": {
            "sanmingtonghui": {"rule": ["x"], "mcq": []},
            "qiongtongbaojian": {"rule": [], "mcq": []},
            "ditiansui": {"rule": [], "mcq": []},
            "zipingzhenquan": {"rule": [], "mcq": []},
        },
    }


def _primary_entry(book, type_, iid, verdict="PASS", findings=None, reviewer="reviewer-1"):
    fs = []
    for f in findings or []:
        f = dict(f)
        # assign (not setdefault): the caller's reviewer must win even when the
        # finding fixture already carries one (F15 outsider rejection test).
        f["reviewer"] = reviewer
        f.setdefault("reviewed_at", "2026-08-23T00:00:00+08:00")
        fs.append(f)
    return {"item": {"book": book, "type": type_, "id": iid, "source_chapter": 1},
            "verdict": verdict, "findings": fs}


def _mini_primary():
    items = [_primary_entry("sanmingtonghui", "rule", "a"),
             _primary_entry("sanmingtonghui", "rule", "b"),
             _primary_entry("sanmingtonghui", "rule", "x"),
             _primary_entry("sanmingtonghui", "mcq", "m1"),
             _primary_entry("qiongtongbaojian", "rule", "q1")]
    return {"schema_version": "1.0", "kind": "primary_review_package",
            "sample_manifest_sha256": "0" * 64, "expansion_manifests_sha256": [],
            "items": items, "overall_stats": {}, "zero_output_report": [],
            "reviewer_list": ["reviewer-1"]}


def test_validate_primary_ok():
    review.validate_primary(_mini_primary(), _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_sha_binding():
    p = _mini_primary()
    p["sample_manifest_sha256"] = "1" * 64
    with pytest.raises(RuntimeError, match="sample manifest"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_coverage_missing_and_extra():
    p = _mini_primary()
    p["items"] = p["items"][:-1]
    with pytest.raises(RuntimeError, match="coverage"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p = _mini_primary()
    p["items"].append(_primary_entry("qiongtongbaojian", "rule", "ghost"))
    with pytest.raises(RuntimeError, match="coverage"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p = _mini_primary()
    p["items"].append(_primary_entry("sanmingtonghui", "rule", "a"))
    with pytest.raises(RuntimeError, match="duplicate"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_verdict_consistency():
    p = _mini_primary()
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "PASS_WITH_MINOR",
                                   [fixtures.minor(), fixtures.minor()])
    review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "PASS", [fixtures.minor()])
    with pytest.raises(RuntimeError, match="inconsistent"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "PASS",
                                   [fixtures.critical()])
    with pytest.raises(RuntimeError, match="inconsistent"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [fixtures.critical(), fixtures.minor()])
    review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_category_and_field_enums():
    p = _mini_primary()
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [{"severity": "critical", "category": "wording",
                                     "evidence_text": "e"}])
    with pytest.raises(RuntimeError, match="critical category"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "MAYBE")
    with pytest.raises(RuntimeError, match="invalid verdict"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [{"severity": "critical", "category": "distortion",
                                     "evidence_text": "  "}])
    with pytest.raises(RuntimeError, match="evidence_text"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [fixtures.critical()])
    p.pop("reviewer_list")
    with pytest.raises(RuntimeError, match="reviewer_list"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_finding_reviewer_must_be_in_list():
    p = _mini_primary()
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [fixtures.critical()], reviewer="outsider")
    with pytest.raises(RuntimeError, match="reviewer"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_finding_reviewed_at_must_be_iso8601():
    # P0-2: primary finding reviewed_at must be a timezone-qualified ISO-8601
    # timestamp (same standard as second/arbitration); bare non-empty strings
    # like "t" or "yesterday" must fail.
    for bad in ("t", "yesterday", "2026-08-23T00:00:00", "2026-99-99T99:99:99+99:99"):
        p = _mini_primary()
        f = fixtures.critical()
        f["reviewed_at"] = bad
        p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL", [f])
        with pytest.raises(RuntimeError, match="ISO-8601|timezone|valid"):
            review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def _mini_chapter_manifest():
    # Every mini sample id lives in chapter 1 (matches _primary_entry's
    # source_chapter=1); used to exercise the source_chapter identity check.
    return {"schema_version": "1.0",
            "chapters": [{"chapter_index": 1, "rule_ids": ["a", "b", "x"],
                          "mcq_ids": ["m1"]}]}


def test_validate_primary_source_chapter_ok_and_tamper():
    # P0: the chapter manifest is MANDATORY (no None/empty bypass), and with
    # it supplied every sanmingtonghui item must carry the SAME source_chapter
    # the manifest assigns to their id; swapping it to another chapter fails
    # closed. Missing or empty chapter manifests are themselves rejected.
    chm = _mini_chapter_manifest()
    review.validate_primary(_mini_primary(), _mini_sample_manifest(),
                            [], "0" * 64, [], chm)
    with pytest.raises(RuntimeError, match="chapter manifest is required"):
        review.validate_primary(_mini_primary(), _mini_sample_manifest(),
                                [], "0" * 64, [], None)
    with pytest.raises(RuntimeError, match="chapter manifest is required"):
        review.validate_primary(_mini_primary(), _mini_sample_manifest(),
                                [], "0" * 64, [], {"chapters": []})
    bad = _mini_primary()
    bad["items"][0]["item"]["source_chapter"] = 2
    with pytest.raises(RuntimeError, match="source_chapter"):
        review.validate_primary(bad, _mini_sample_manifest(), [], "0" * 64, [], chm)


def test_validate_primary_cli_strict(tiny):
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    primary = _mini_primary()
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    entry = _primary_entry(book, item_type, iid)
                    # keep the REAL chapter (id embeds the chapter number);
                    # source_chapter=1 would fail the new identity check.
                    if book == "sanmingtonghui":
                        entry["item"]["source_chapter"] = int(iid.split("_")[1])
                    items.append(entry)
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            entry = _primary_entry("sanmingtonghui", item_type, iid)
            entry["item"]["source_chapter"] = int(iid.split("_")[1])
            items.append(entry)
    primary["items"] = items
    p_path = base / "primary_review_package_v1.json"
    fixtures.write_json(p_path, primary)
    # F18: validate-primary runs the frozen/fake source lock and sample
    # validation, exactly like packet/decide/finalize. Fake happy path:
    fixtures.run_cli("classic_acceptance_review.py", "validate-primary",
                     "--primary", str(p_path), "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data))
    # Missing the mode flag is rejected (exactly one of candidate-commit/data-root):
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "validate-primary",
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path))
    assert not r.timed_out and r.returncode != 0
    assert "exactly one" in r.stdout + r.stderr


def test_validate_primary_cli_rejects_nonfrozen_chapter_manifest():
    # P0-2 / F18: validate-primary runs the production frozen lock. To prove
    # the lock is the ONLY thing stopping a NON-frozen --chapter-manifest,
    # build the three forged files from the REAL frozen GitSource (same
    # candidate commit the CLI will resolve in production), so they are
    # production-mode self-consistent if the frozen SHA gate were removed:
    # tamper the real chapter manifest (append an empty chapter), rebuild the
    # sample from the tampered manifest against GitSource(COMMIT) (so its
    # chapter_manifest_sha256 and data_file SHAs match), and rebuild the
    # primary to cover that sample with real source chapters. The frozen
    # chapter-manifest SHA gate in verify_frozen_inputs runs before any of
    # that is read, so production still rejects.
    import copy as _copy
    base = fixtures.tmp_dir("vp_nonfrozen_chman")
    try:
        real_man, _ = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
        source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
        git_desc = {"kind": "git", "candidate_commit": fixtures.COMMIT,
                    "test_only": False}
        tampered = _copy.deepcopy(real_man)
        tampered["chapters"] = list(tampered["chapters"]) + [{
            "chapter_index": 9999, "title": "forged", "is_legacy": False,
            "raw_source_path": "forged.txt", "rule_ids": [], "mcq_ids": [],
            "rule_count": 0, "mcq_count": 0, "zero_rule": True, "zero_mcq": True}]
        tampered_chman = base / "tampered_chapter_manifest.json"
        tampered_chman.write_bytes(c.serialize_json(tampered))
        tampered_sha = c.sha256_file_lf(tampered_chman)
        rebuilt_sm = sampling.build_sample_manifest(
            tampered, source, git_desc, tampered_sha)
        sm_path = base / "sample_manifest_forged.json"
        sm_path.write_bytes(c.serialize_json(rebuilt_sm))
        assert rebuilt_sm["chapter_manifest_sha256"] == tampered_sha
        # real source chapters for every sanmingtonghui id in the sample
        chapter_of = {}
        for ch in tampered["chapters"]:
            for iid in ch["rule_ids"] + ch["mcq_ids"]:
                chapter_of[iid] = ch["chapter_index"]
        primary = _mini_primary()
        primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
        items = []
        for book in c.BOOKS:
            for item_type in ("rule", "mcq"):
                for ids in rebuilt_sm["samples"][book][item_type].values():
                    for iid in ids:
                        entry = _primary_entry(book, item_type, iid)
                        if book == "sanmingtonghui":
                            entry["item"]["source_chapter"] = chapter_of[iid]
                        items.append(entry)
        for item_type in ("rule", "mcq"):
            for iid in rebuilt_sm["boundary_samples"]["sanmingtonghui"][item_type]:
                entry = _primary_entry("sanmingtonghui", item_type, iid)
                entry["item"]["source_chapter"] = chapter_of[iid]
                items.append(entry)
        primary["items"] = items
        p_path = base / "primary_forged.json"
        fixtures.write_json(p_path, primary)
        r = fixtures.run_cli_result(
            "classic_acceptance_review.py", "validate-primary",
            "--primary", str(p_path),
            "--sample-manifest", str(sm_path),
            "--chapter-manifest", str(tampered_chman),
            "--candidate-commit", fixtures.COMMIT)
        assert not r.timed_out and r.returncode != 0
        out = r.stdout + r.stderr
        assert "frozen" in out.lower() and "chapter manifest" in out.lower()
    finally:
        fixtures.rmtree_force(base)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: `AttributeError: ... has no attribute 'validate_primary'`

- [ ] **Step 3: 实现（追加到 `scripts/classic_acceptance_review.py`）**

```python
def required_item_keys(sample_manifest, expansion_manifests):
    refs = set()
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sample_manifest["samples"][book][item_type].values():
                refs.update((book, item_type, iid) for iid in ids)
    for item_type in ("rule", "mcq"):
        refs.update(("sanmingtonghui", item_type, iid)
                    for iid in sample_manifest["boundary_samples"]["sanmingtonghui"][item_type])
    for em in expansion_manifests:
        for book, types in em["expansions"].items():
            for item_type, strata in types.items():
                for info in strata.values():
                    refs.update((book, item_type, iid) for iid in info["new_ids"])
    return refs


def validate_primary(primary, sample_manifest, expansions, sample_manifest_sha,
                     expansion_shas, chapter_manifest):
    c.require(primary.get("schema_version") == "1.0", "primary: schema_version != 1.0")
    c.require(primary.get("kind") == "primary_review_package", "primary: wrong kind")
    c.require(primary.get("sample_manifest_sha256") == sample_manifest_sha,
              "primary does not bind the sample manifest (SHA mismatch)")
    c.require((primary.get("expansion_manifests_sha256") or []) == expansion_shas,
              "primary expansion_manifests_sha256 mismatch")
    reviewer_list = primary.get("reviewer_list")
    c.require(isinstance(reviewer_list, list) and reviewer_list
              and all(isinstance(r, str) and r for r in reviewer_list),
              "primary reviewer_list missing/empty/invalid")
    reviewer_set = set(reviewer_list)
    # F20/source-chapter identity (design section 8.1 schema): for
    # sanmingtonghui items the primary must declare the SAME source_chapter
    # the chapter manifest assigns to that id. The chapter manifest is
    # mandatory (no None/empty bypass) because a swapped chapter breaks the
    # audit trail and evidence traceability for that review entry; it does
    # not by itself change the decision metrics (boundary/stratum come from
    # the frozen sample/chapter metadata via item_meta_map), but a forged
    # chapter ownership must not validate.
    c.require(isinstance(chapter_manifest, dict)
              and isinstance(chapter_manifest.get("chapters"), list)
              and chapter_manifest["chapters"],
              "validate_primary: a non-empty chapter manifest is required")
    chapter_of = {}
    for ch in chapter_manifest["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]
    required = required_item_keys(sample_manifest, expansions)
    actual = set()
    for entry in primary.get("items", []):
        item = entry.get("item") or {}
        key = (item.get("book"), item.get("type"), item.get("id"))
        c.require(all(isinstance(x, str) and x for x in key),
                  f"primary item missing book/type/id: {item}")
        c.require(key not in actual, f"primary duplicate item: {key}")
        actual.add(key)
        if item.get("book") == "sanmingtonghui":
            expected_ch = chapter_of.get(item["id"])
            c.require(expected_ch is not None,
                      f"{key}: sanmingtonghui item not found in chapter manifest")
            c.require(item.get("source_chapter") == expected_ch,
                      f"{key}: primary source_chapter {item.get('source_chapter')!r} "
                      f"!= chapter manifest {expected_ch!r} (chapter tampering)")
        verdict = entry.get("verdict")
        c.require(verdict in c.VERDICTS, f"{key}: invalid verdict {verdict!r}")
        findings = entry.get("findings")
        c.require(isinstance(findings, list), f"{key}: findings not a list")
        n_crit = n_min = 0
        for f in findings:
            sev, cat = f.get("severity"), f.get("category")
            c.require(sev in ("critical", "minor"), f"{key}: invalid severity {sev!r}")
            c.require(isinstance(f.get("evidence_text"), str) and f["evidence_text"].strip(),
                      f"{key}: evidence_text missing/empty")
            f_reviewer = f.get("reviewer")
            c.require(f_reviewer in reviewer_set,
                      f"{key}: finding reviewer {f_reviewer!r} not in reviewer_list (F15)")
            c._check_iso8601(f.get("reviewed_at"), f"{key} finding reviewed_at")
            if sev == "critical":
                c.require(cat in c.CRITICAL_CATEGORIES,
                          f"{key}: invalid critical category {cat!r}")
                n_crit += 1
            else:
                c.require(cat in c.MINOR_CATEGORIES,
                          f"{key}: invalid minor category {cat!r}")
                n_min += 1
        expected_verdict = "FAIL" if n_crit else ("PASS_WITH_MINOR" if n_min else "PASS")
        c.require(verdict == expected_verdict,
                  f"{key}: verdict {verdict} inconsistent with findings "
                  f"({n_crit} critical, {n_min} minor)")
    c.require(actual == required,
              f"primary item coverage mismatch: missing={sorted(required - actual)[:5]} "
              f"extra={sorted(actual - required)[:5]}")
    c.require(isinstance(primary.get("zero_output_report"), list),
              "primary zero_output_report missing")
    c.require(isinstance(primary.get("overall_stats"), dict), "primary overall_stats missing")


VALIDATE_PRIMARY_FLAGS = {"primary", "sample-manifest", "chapter-manifest",
                          "candidate-commit", "data-root"}


def cmd_validate_primary(argv):
    # F18: every strict CLI entry point runs the frozen lock (production) or
    # resolves the fake DirSource BEFORE any candidate/manifest data is read.
    # validate-primary is not a trusted "is this JSON self-consistent" linter;
    # it must lock the same frozen chain packet/decide/finalize use. Expansion
    # authorization is NOT available yet (validate_expansion_manifest lands in
    # Task 7, alongside its builder/cmd_expand); --expansion-manifest is
    # rejected here and re-added there with the full producing-evidence chain.
    flags, _ = c.parse_flags(argv, allowed=VALIDATE_PRIMARY_FLAGS)
    primary_path = c.flag1(flags, "primary")
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    primary = load_json_file(primary_path)
    validate_primary(primary, sample_manifest, [],
                     sm_sha, [], chapter_manifest)
    print("primary review package OK:", primary_path)
```

dispatch 增加：

```python
        elif cmd == "validate-primary":
            cmd_validate_primary(argv[1:])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add scripts/classic_acceptance_review.py tests/test_classic_acceptance_review.py
git commit -m "feat(acceptance): primary review package schema validation (F15 reviewer)"
```

---

### Task 5: 二审 / 仲裁回执校验（全局身份互异，F15）

**Files:**
- Modify: `scripts/classic_acceptance_review.py`（追加）
- Test: `tests/test_classic_acceptance_review.py`（追加）

- [ ] **Step 1: 写失败测试**

向 `tests/test_classic_acceptance_review.py` 追加：

```python
def _primary_with_criticals():
    p = _mini_primary()
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [fixtures.critical(), fixtures.critical()])
    return p


def _second_receipt(agree0=True, agree1=True, reviewer="reviewer-2"):
    return {"schema_version": "1.0", "kind": "second_review_receipt_v1",
            "primary_sha256": "0" * 64, "reviewer": reviewer,
            "reviewed_at": "2026-08-23T00:00:00+08:00",
            "entries": [
                {"book": "sanmingtonghui", "type": "rule", "id": "a",
                 "finding_index": 0, "first_severity": "critical",
                 "first_category": "distortion", "agree": agree0,
                 "evidence_text": "e", "reviewer": reviewer,
                 "reviewed_at": "2026-08-23T00:00:00+08:00"},
                {"book": "sanmingtonghui", "type": "rule", "id": "a",
                 "finding_index": 1, "first_severity": "critical",
                 "first_category": "distortion", "agree": agree1,
                 "evidence_text": "e", "reviewer": reviewer,
                 "reviewed_at": "2026-08-23T00:00:00+08:00"},
            ]}


def _arb_receipt(decisions, arbitrator="reviewer-3", second_reviewer="reviewer-2",
                 first_reviewer="reviewer-1"):
    return {"schema_version": "1.0", "kind": "arbitration_receipt_v1",
            "primary_sha256": "0" * 64, "second_review_sha256": "1" * 64,
            "reviewer_first": first_reviewer, "reviewer_second": second_reviewer,
            "arbitrator": arbitrator, "reviewed_at": "2026-08-23T00:00:00+08:00",
            "entries": [
                {"book": "sanmingtonghui", "type": "rule", "id": "a",
                 "finding_index": idx, "reviewer_first": first_reviewer,
                 "decision": d, "reasoning": "why", "arbitrator": arbitrator,
                 "reviewed_at": "2026-08-23T00:00:00+08:00"}
                for idx, d in decisions.items()]}


def test_validate_second_ok_and_failures():
    review.validate_second(_second_receipt(), _primary_with_criticals(), "0" * 64)
    bad = _second_receipt()
    bad["primary_sha256"] = "9" * 64
    with pytest.raises(RuntimeError, match="bind the primary"):
        review.validate_second(bad, _primary_with_criticals(), "0" * 64)
    missing = _second_receipt()
    missing["entries"] = missing["entries"][:1]
    with pytest.raises(RuntimeError, match="cover exactly all critical"):
        review.validate_second(missing, _primary_with_criticals(), "0" * 64)
    extra = _second_receipt()
    extra["entries"].append(dict(extra["entries"][0], finding_index=7))
    with pytest.raises(RuntimeError, match="cover exactly all critical"):
        review.validate_second(extra, _primary_with_criticals(), "0" * 64)
    noagree = _second_receipt()
    noagree["entries"][0].pop("agree")
    with pytest.raises(RuntimeError, match="agree"):
        review.validate_second(noagree, _primary_with_criticals(), "0" * 64)
    # second reviewer must differ from every first reviewer (F15)
    same = _second_receipt(reviewer="reviewer-1")
    with pytest.raises(RuntimeError, match="second reviewer"):
        review.validate_second(same, _primary_with_criticals(), "0" * 64)
    review.validate_second({"schema_version": "1.0", "kind": "second_review_receipt_v1",
                            "primary_sha256": "0" * 64, "entries": [],
                            "reviewer": "reviewer-2",
                            "reviewed_at": "2026-08-23T00:00:00+08:00"},
                           _mini_primary(), "0" * 64)
    # reviewed_at must be a timezone-qualified ISO-8601 timestamp (P0-3)
    bad_ts = _second_receipt()
    bad_ts["reviewed_at"] = "t"
    with pytest.raises(RuntimeError, match="ISO-8601"):
        review.validate_second(bad_ts, _primary_with_criticals(), "0" * 64)


def test_validate_arbitration_ok_and_failures():
    second = _second_receipt(agree0=True, agree1=False)
    review.validate_arbitration(_arb_receipt({1: "critical"}),
                                _primary_with_criticals(), second, "0" * 64, "1" * 64)
    review.validate_arbitration(_arb_receipt({1: "non_critical"}),
                                _primary_with_criticals(), second, "0" * 64, "1" * 64)
    bad_bind = _arb_receipt({1: "critical"})
    bad_bind["second_review_sha256"] = "2" * 64
    with pytest.raises(RuntimeError, match="second review"):
        review.validate_arbitration(bad_bind, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)
    with pytest.raises(RuntimeError, match="cover exactly all"):
        review.validate_arbitration(_arb_receipt({}), _primary_with_criticals(),
                                     second, "0" * 64, "1" * 64)
    with pytest.raises(RuntimeError, match="decision"):
        review.validate_arbitration(_arb_receipt({1: "maybe"}),
                                     _primary_with_criticals(), second, "0" * 64, "1" * 64)
    # arbitrator must NOT be in primary reviewer_list (global independence, F15)
    bad_arb = _arb_receipt({1: "critical"}, arbitrator="reviewer-1")
    with pytest.raises(RuntimeError, match="arbitrator"):
        review.validate_arbitration(bad_arb, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)
    # arbitrator must differ from second reviewer
    bad_arb2 = _arb_receipt({1: "critical"}, arbitrator="reviewer-2")
    with pytest.raises(RuntimeError, match="arbitrator"):
        review.validate_arbitration(bad_arb2, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)
    # entry reviewer_first must equal the primary finding's reviewer
    bad_first = _arb_receipt({1: "critical"}, first_reviewer="someone-else")
    with pytest.raises(RuntimeError, match="reviewer_first"):
        review.validate_arbitration(bad_first, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)


def test_validate_arbitration_binds_per_finding_reviewer():
    # F21: one item with TWO critical findings reviewed by DIFFERENT first
    # reviewers; arbitration must bind each entry to its own finding's reviewer.
    p = _mini_primary()
    # Build the entry directly (NOT via _primary_entry): that helper forces a
    # single reviewer onto every finding, but F21 needs two findings with
    # DIFFERENT per-finding reviewers to survive.
    p["items"][0] = {"item": {"book": "sanmingtonghui", "type": "rule", "id": "a",
                              "source_chapter": 1},
                     "verdict": "FAIL", "findings": [
                         {"severity": "critical", "category": "distortion",
                          "evidence_text": "e", "reviewer": "r1",
                          "reviewed_at": "2026-08-23T00:00:00+08:00"},
                         {"severity": "critical", "category": "distortion",
                          "evidence_text": "e", "reviewer": "r2",
                          "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
    p["reviewer_list"] = ["r1", "r2"]
    second = {"schema_version": "1.0", "kind": "second_review_receipt_v1",
              "primary_sha256": "0" * 64, "reviewer": "r3",
              "reviewed_at": "2026-08-23T00:00:00+08:00",
              "entries": [
                  {"book": "sanmingtonghui", "type": "rule", "id": "a",
                   "finding_index": 0, "agree": False, "evidence_text": "e",
                   "reviewer": "r3", "reviewed_at": "2026-08-23T00:00:00+08:00"},
                  {"book": "sanmingtonghui", "type": "rule", "id": "a",
                   "finding_index": 1, "agree": False, "evidence_text": "e",
                   "reviewer": "r3", "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
    arb = {"schema_version": "1.0", "kind": "arbitration_receipt_v1",
           "primary_sha256": "0" * 64, "second_review_sha256": "1" * 64,
           "reviewer_second": "r3", "arbitrator": "r4",
           "reviewed_at": "2026-08-23T00:00:00+08:00",
           "entries": [
               {"book": "sanmingtonghui", "type": "rule", "id": "a",
                "finding_index": 0, "reviewer_first": "r1",
                "decision": "critical", "reasoning": "why", "arbitrator": "r4",
                "reviewed_at": "2026-08-23T00:00:00+08:00"},
               {"book": "sanmingtonghui", "type": "rule", "id": "a",
                "finding_index": 1, "reviewer_first": "r2",
                "decision": "non_critical", "reasoning": "why", "arbitrator": "r4",
                "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
    review.validate_arbitration(arb, p, second, "0" * 64, "1" * 64)  # passes
    # if entry 1 wrongly claims reviewer r1 (instead of its actual r2), fail
    arb["entries"][1]["reviewer_first"] = "r1"
    with pytest.raises(RuntimeError, match="reviewer_first"):
        review.validate_arbitration(arb, p, second, "0" * 64, "1" * 64)


def test_validate_arbitration_rejects_bad_timestamp():
    second = _second_receipt(agree0=False, agree1=True)
    bad = _arb_receipt({0: "critical"})
    bad["reviewed_at"] = "not-a-timestamp"
    with pytest.raises(RuntimeError, match="ISO-8601"):
        review.validate_arbitration(bad, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)


def test_critical_and_disagreement_refs():
    assert review.critical_refs(_primary_with_criticals()) == {
        ("sanmingtonghui", "rule", "a", 0), ("sanmingtonghui", "rule", "a", 1)}
    assert review.critical_refs(_mini_primary()) == set()
    second = _second_receipt(agree0=True, agree1=False)
    assert review.disagreement_refs(second) == {("sanmingtonghui", "rule", "a", 1)}


def test_validate_arbitration_rejects_arbitrator_in_reviewer_list_without_findings():
    # P0-1: design section 12.3 requires the arbitrator to be absent from the
    # ENTIRE primary.reviewer_list, even if that reviewer produced no finding.
    p = _primary_with_criticals()
    p["reviewer_list"] = ["reviewer-1", "reviewer-3"]  # reviewer-3 never reviews
    second = _second_receipt(agree0=True, agree1=False)
    bad = _arb_receipt({1: "critical"}, arbitrator="reviewer-3")
    with pytest.raises(RuntimeError, match="arbitrator"):
        review.validate_arbitration(bad, p, second, "0" * 64, "1" * 64)


def test_validate_second_cli_fake_ok(tiny):
    base, data, chman_path, man, source, sm = tiny
    p = _primary_with_criticals()
    p_path = base / "primary.json"
    fixtures.write_json(p_path, p)
    s = _second_receipt()
    s["primary_sha256"] = fixtures.sha256_file(p_path)
    s_path = base / "second.json"
    fixtures.write_json(s_path, s)
    fixtures.run_cli("classic_acceptance_review.py", "validate-second",
                     "--second", str(s_path), "--primary", str(p_path),
                     "--data-root", str(data))


def test_validate_arbitration_cli_fake_ok(tiny):
    base, data, chman_path, man, source, sm = tiny
    p = _primary_with_criticals()
    p_path = base / "primary.json"
    fixtures.write_json(p_path, p)
    s = _second_receipt(agree0=True, agree1=False)
    s["primary_sha256"] = fixtures.sha256_file(p_path)
    s_path = base / "second.json"
    fixtures.write_json(s_path, s)
    a = _arb_receipt({1: "critical"})
    a["primary_sha256"] = fixtures.sha256_file(p_path)
    a["second_review_sha256"] = fixtures.sha256_file(s_path)
    a_path = base / "arbitration.json"
    fixtures.write_json(a_path, a)
    fixtures.run_cli("classic_acceptance_review.py", "validate-arbitration",
                     "--arbitration", str(a_path), "--primary", str(p_path),
                     "--second", str(s_path), "--data-root", str(data))


def test_validate_second_cli_rejects_nonfrozen_chapter_manifest():
    # P0-2/F18: validate-second runs the production frozen lock BEFORE reading
    # any receipt. Use NONEXISTENT receipts: the frozen chapter-manifest error
    # must still surface first, proving lock-then-read ordering.
    import copy as _copy
    base = fixtures.tmp_dir("vs_nonfrozen_chman")
    try:
        real_man, _ = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
        tampered = _copy.deepcopy(real_man)
        tampered["chapters"] = list(tampered["chapters"]) + [{
            "chapter_index": 9999, "title": "forged", "is_legacy": False,
            "raw_source_path": "forged.txt", "rule_ids": [], "mcq_ids": [],
            "rule_count": 0, "mcq_count": 0, "zero_rule": True, "zero_mcq": True}]
        tampered_chman = base / "tampered_chapter_manifest.json"
        tampered_chman.write_bytes(c.serialize_json(tampered))
        # Point --second/--primary at NONEXISTENT files: if the implementation
        # read receipts before the frozen lock, a file-not-found error would
        # surface instead; the frozen chapter-manifest error must come first.
        missing = base / "missing.json"
        r = fixtures.run_cli_result(
            "classic_acceptance_review.py", "validate-second",
            "--second", str(missing), "--primary", str(missing),
            "--chapter-manifest", str(tampered_chman),
            "--candidate-commit", fixtures.COMMIT)
        assert not r.timed_out and r.returncode != 0
        out = r.stdout + r.stderr
        assert "frozen" in out.lower() and "chapter manifest" in out.lower()
        assert "No such file" not in out and "FileNotFoundError" not in out
    finally:
        fixtures.rmtree_force(base)


def test_validate_arbitration_cli_rejects_nonfrozen_chapter_manifest():
    # P0-2/F18: validate-arbitration runs the production frozen lock BEFORE
    # reading any receipt/primary. Use NONEXISTENT receipts: the frozen
    # chapter-manifest error must still surface first (lock-then-read order).
    import copy as _copy
    base = fixtures.tmp_dir("va_nonfrozen_chman")
    try:
        real_man, _ = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
        tampered = _copy.deepcopy(real_man)
        tampered["chapters"] = list(tampered["chapters"]) + [{
            "chapter_index": 9999, "title": "forged", "is_legacy": False,
            "raw_source_path": "forged.txt", "rule_ids": [], "mcq_ids": [],
            "rule_count": 0, "mcq_count": 0, "zero_rule": True, "zero_mcq": True}]
        tampered_chman = base / "tampered_chapter_manifest.json"
        tampered_chman.write_bytes(c.serialize_json(tampered))
        # Point --arbitration/--primary/--second at NONEXISTENT files: if the
        # implementation read receipts before the frozen lock, a file-not-found
        # error would surface instead; frozen chapter-manifest error comes first.
        missing = base / "missing.json"
        r = fixtures.run_cli_result(
            "classic_acceptance_review.py", "validate-arbitration",
            "--arbitration", str(missing),
            "--primary", str(missing), "--second", str(missing),
            "--chapter-manifest", str(tampered_chman),
            "--candidate-commit", fixtures.COMMIT)
        assert not r.timed_out and r.returncode != 0
        out = r.stdout + r.stderr
        assert "frozen" in out.lower() and "chapter manifest" in out.lower()
        assert "No such file" not in out and "FileNotFoundError" not in out
    finally:
        fixtures.rmtree_force(base)


def test_validate_second_cli_rejects_unknown_flag(tiny):
    base, data, chman_path, man, source, sm = tiny
    p = _primary_with_criticals()
    p_path = base / "primary.json"
    fixtures.write_json(p_path, p)
    s = _second_receipt()
    s["primary_sha256"] = fixtures.sha256_file(p_path)
    s_path = base / "second.json"
    fixtures.write_json(s_path, s)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "validate-second",
        "--second", str(s_path), "--primary", str(p_path),
        "--data-root", str(data), "--bogus", "x")
    assert not r.timed_out and r.returncode != 0
    assert "unknown flag" in r.stdout + r.stderr


def test_validate_arbitration_cli_rejects_unknown_flag(tiny):
    base, data, chman_path, man, source, sm = tiny
    p = _primary_with_criticals()
    p_path = base / "primary.json"
    fixtures.write_json(p_path, p)
    s = _second_receipt(agree0=True, agree1=False)
    s["primary_sha256"] = fixtures.sha256_file(p_path)
    s_path = base / "second.json"
    fixtures.write_json(s_path, s)
    a = _arb_receipt({1: "critical"})
    a["primary_sha256"] = fixtures.sha256_file(p_path)
    a["second_review_sha256"] = fixtures.sha256_file(s_path)
    a_path = base / "arbitration.json"
    fixtures.write_json(a_path, a)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "validate-arbitration",
        "--arbitration", str(a_path),
        "--primary", str(p_path), "--second", str(s_path),
        "--data-root", str(data), "--bogus", "x")
    assert not r.timed_out and r.returncode != 0
    assert "unknown flag" in r.stdout + r.stderr
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: `AttributeError: ... has no attribute 'validate_second'`

- [ ] **Step 3: 实现（追加到 `scripts/classic_acceptance_review.py`）**

```python
def critical_refs(primary):
    out = set()
    for entry in primary["items"]:
        item = entry["item"]
        for idx, f in enumerate(entry.get("findings", [])):
            if f.get("severity") == "critical":
                out.add((item["book"], item["type"], item["id"], idx))
    return out


def _primary_reviewer_of(primary, book, item_type, iid, finding_index):
    """F21: return the reviewer of the SPECIFIC finding at finding_index for
    the primary item (book, type, id). One item may carry multiple findings
    with different reviewers; we must NOT require them all to share one."""
    for entry in primary["items"]:
        item = entry["item"]
        if (item["book"], item["type"], item["id"]) == (book, item_type, iid):
            findings = entry.get("findings", [])
            c.require(0 <= finding_index < len(findings),
                      f"primary item {(book, item_type, iid)} has no finding index "
                      f"{finding_index} (has {len(findings)})")
            reviewer = findings[finding_index].get("reviewer")
            c.require(isinstance(reviewer, str) and reviewer,
                      f"primary finding {finding_index} reviewer missing")
            return reviewer
    raise RuntimeError(f"primary item not found: {(book, item_type, iid)}")


def validate_second(second, primary, primary_sha):
    c.require(second.get("schema_version") == "1.0",
              "second review receipt: schema_version != 1.0")
    c.require(second.get("kind") == "second_review_receipt_v1",
              "second review receipt: wrong kind")
    c.require(second.get("primary_sha256") == primary_sha,
              "second review receipt does not bind the primary package (SHA mismatch)")
    reviewer = second.get("reviewer")
    c.require(isinstance(reviewer, str) and reviewer,
              "second review receipt: top-level reviewer missing")
    primary_reviewers = set()
    for entry in primary["items"]:
        for f in entry.get("findings", []):
            primary_reviewers.add(f.get("reviewer"))
    c.require(reviewer not in primary_reviewers,
              f"second reviewer {reviewer!r} must differ from every first reviewer (F15)")
    c._check_iso8601(second.get("reviewed_at"), "second receipt reviewed_at")
    required = critical_refs(primary)
    seen = set()
    for e in second.get("entries", []):
        ref = (e.get("book"), e.get("type"), e.get("id"), e.get("finding_index"))
        c.require(ref not in seen, f"second review duplicate entry: {ref}")
        seen.add(ref)
        c.require(isinstance(e.get("agree"), bool),
                  f"second review entry missing agree bool: {ref}")
        c.require(isinstance(e.get("evidence_text"), str) and e["evidence_text"].strip(),
                  f"second review entry missing evidence_text: {ref}")
        c.require(e.get("reviewer") == reviewer,
                  f"second review entry reviewer != top-level reviewer: {ref}")
        c._check_iso8601(e.get("reviewed_at"), f"second review entry {ref} reviewed_at")
    c.require(seen == required,
              f"second review must cover exactly all critical findings: "
              f"missing={sorted(required - seen)[:5]} extra={sorted(seen - required)[:5]}")


def disagreement_refs(second):
    return {(e["book"], e["type"], e["id"], e["finding_index"])
            for e in second.get("entries", []) if not e["agree"]}


def validate_arbitration(arbitration, primary, second, primary_sha, second_sha):
    c.require(arbitration.get("schema_version") == "1.0",
              "arbitration receipt: schema_version != 1.0")
    c.require(arbitration.get("kind") == "arbitration_receipt_v1",
              "arbitration receipt: wrong kind")
    c.require(arbitration.get("primary_sha256") == primary_sha,
              "arbitration receipt does not bind the primary package (SHA mismatch)")
    c.require(arbitration.get("second_review_sha256") == second_sha,
              "arbitration receipt does not bind the second review receipt (SHA mismatch)")
    # F21: top-level identity + ISO-8601 timestamp
    c._check_iso8601(arbitration.get("reviewed_at"), "arbitration receipt reviewed_at")
    reviewer_second = arbitration.get("reviewer_second")
    arbitrator = arbitration.get("arbitrator")
    c.require(reviewer_second == second.get("reviewer"),
              "arbitration reviewer_second != second receipt reviewer")
    c.require(isinstance(arbitrator, str) and arbitrator,
              "arbitration: arbitrator missing")
    # P0-1: global independence (design section 12.3) is against the ENTIRE
    # primary.reviewer_list, not just reviewers who produced a finding.
    primary_reviewer_list = set(primary.get("reviewer_list") or [])
    c.require(arbitrator not in primary_reviewer_list,
              f"arbitrator {arbitrator!r} must not be any primary reviewer (F15 global)")
    c.require(arbitrator != reviewer_second,
              f"arbitrator {arbitrator!r} must differ from second reviewer (F15)")
    required = disagreement_refs(second)
    seen = set()
    for e in arbitration.get("entries", []):
        ref = (e.get("book"), e.get("type"), e.get("id"), e.get("finding_index"))
        c.require(ref not in seen, f"arbitration duplicate entry: {ref}")
        seen.add(ref)
        c.require(e.get("decision") in ("critical", "non_critical"),
                  f"arbitration invalid decision {e.get('decision')!r}: {ref}")
        c.require(isinstance(e.get("reasoning"), str) and e["reasoning"].strip(),
                  f"arbitration entry missing reasoning: {ref}")
        c.require(e.get("arbitrator") == arbitrator,
                  f"arbitration entry arbitrator != top-level: {ref}")
        c._check_iso8601(e.get("reviewed_at"), f"arbitration entry {ref} reviewed_at")
        # F21: reviewer_first binds the SPECIFIC finding at finding_index
        first = e.get("reviewer_first")
        actual_first = _primary_reviewer_of(primary, *ref)
        c.require(first == actual_first,
                  f"arbitration reviewer_first {first!r} != primary finding[{ref[3]}] "
                  f"reviewer {actual_first!r}: {ref}")
        c.require(first in primary_reviewer_list,
                  f"arbitration reviewer_first {first!r} not in primary reviewer_list")
        c.require(first not in (reviewer_second, arbitrator),
                  f"arbitration entry identities not pairwise distinct: {ref}")
    c.require(seen == required,
              f"arbitration must cover exactly all second-review disagreements: "
              f"missing={sorted(required - seen)[:5]} extra={sorted(seen - required)[:5]}")


VALIDATE_SECOND_FLAGS = {"second", "primary", "candidate-commit", "data-root",
                         "chapter-manifest"}
VALIDATE_ARBITRATION_FLAGS = {"arbitration", "primary", "second",
                              "candidate-commit", "data-root", "chapter-manifest"}


def cmd_validate_second(argv):
    # F18: run the frozen/fake source lock BEFORE reading any receipt/primary.
    flags, _ = c.parse_flags(argv, allowed=VALIDATE_SECOND_FLAGS)
    second_path = c.flag1(flags, "second")
    primary_path = c.flag1(flags, "primary")
    is_fake = "data-root" in flags
    c.build_source(flags, expected_test_only=(True if is_fake else False))
    second = load_json_file(second_path)
    primary = load_json_file(primary_path)
    validate_second(second, primary, sha256_file(primary_path))
    print("second review receipt OK:", second_path)


def cmd_validate_arbitration(argv):
    # F18: run the frozen/fake source lock BEFORE reading any receipt/primary.
    flags, _ = c.parse_flags(argv, allowed=VALIDATE_ARBITRATION_FLAGS)
    arbitration_path = c.flag1(flags, "arbitration")
    primary_path = c.flag1(flags, "primary")
    second_path = c.flag1(flags, "second")
    is_fake = "data-root" in flags
    c.build_source(flags, expected_test_only=(True if is_fake else False))
    arbitration = load_json_file(arbitration_path)
    primary = load_json_file(primary_path)
    second = load_json_file(second_path)
    validate_arbitration(arbitration, primary, second,
                         sha256_file(primary_path), sha256_file(second_path))
    print("arbitration receipt OK:", arbitration_path)
```

dispatch 增加：

```python
        elif cmd == "validate-second":
            cmd_validate_second(argv[1:])
        elif cmd == "validate-arbitration":
            cmd_validate_arbitration(argv[1:])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add scripts/classic_acceptance_review.py tests/test_classic_acceptance_review.py
git commit -m "feat(acceptance): second/arbitration validation with global identity independence"
```

---

### Task 6: 裁决 + 判定状态机 + `decide`（F3 删 finding 保分母）

**Files:**
- Modify: `scripts/classic_acceptance_review.py`（追加）
- Test: `tests/test_classic_acceptance_review.py`（追加）

- [ ] **Step 1: 写失败测试**

向 `tests/test_classic_acceptance_review.py` 追加：

```python
def test_canonicalize_deletes_noncritical_keeps_item_in_denominator():
    primary = _mini_primary()
    primary["items"][0] = _primary_entry(
        "sanmingtonghui", "rule", "a", "FAIL",
        [fixtures.critical(), fixtures.critical(), fixtures.minor()])
    second = _second_receipt(agree0=True, agree1=False)
    arb = _arb_receipt({1: "non_critical"})
    canonical = review.canonicalize(primary, second, arb)
    a_findings = [f for f in canonical
                  if (f["book"], f["type"], f["id"]) == ("sanmingtonghui", "rule", "a")]
    # finding 0 stays critical; finding 1 DELETED (not retagged minor); finding 2 minor
    assert {f["finding_index"] for f in a_findings} == {0, 2}
    assert a_findings[0]["severity"] == "critical"
    assert a_findings[0]["state"] == "ADJUDICATED_CRITICAL"
    assert a_findings[1]["severity"] == "minor"
    assert a_findings[1]["state"] == "PRIMARY_MINOR"
    # item still FAIL because finding 0 remains critical
    verdicts = review.item_verdicts(canonical)
    assert verdicts[("sanmingtonghui", "rule", "a")] == "FAIL"


def test_canonicalize_downgraded_solo_finding_becomes_pass():
    primary = _mini_primary()
    primary["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                         [fixtures.critical()])
    second = _second_receipt(agree0=False, agree1=False)
    arb = _arb_receipt({0: "non_critical"})
    canonical = review.canonicalize(primary, second, arb)
    assert canonical == []                       # deleted, no remaining findings
    verdicts = review.item_verdicts(canonical)
    assert ("sanmingtonghui", "rule", "a") not in verdicts   # no FAIL, no minor-only
    # BUT the item remains in the reviewed denominator (F3)
    # (compute_metrics counts all reviewed items, not just verdict keys)


def test_canonicalize_missing_receipts_fail_closed():
    primary = _primary_with_criticals()
    with pytest.raises(RuntimeError, match="lacks a second-review entry"):
        review.canonicalize(primary, None, None)
    second = _second_receipt(agree0=False, agree1=False)
    with pytest.raises(RuntimeError, match="lacks an arbitration entry"):
        review.canonicalize(primary, second, None)


def test_item_meta_map_and_metrics_keeps_deleted_finding_in_denominator():
    sm = _mini_sample_manifest()
    chman = {"chapters": [
        {"chapter_index": 1, "rule_ids": ["x"], "mcq_ids": []},
        {"chapter_index": 2, "rule_ids": ["a", "b"], "mcq_ids": ["m1"]},
    ]}
    meta = review.item_meta_map(sm, [], chman)
    assert meta[("sanmingtonghui", "rule", "x")] == {"stratum": 1, "boundary": True}
    # item 'a' has a deleted critical (no verdict key) -> PASS, but still reviewed
    verdicts = {("sanmingtonghui", "mcq", "m1"): "PASS_WITH_MINOR"}
    metrics, stratum_rule, boundary_crit = review.compute_metrics(verdicts, meta)
    assert metrics[("sanmingtonghui", "rule")] == {
        "reviewed": 3, "critical_items": 0, "minor_only_items": 0}  # denominator 3 kept
    assert metrics[("sanmingtonghui", "mcq")] == {
        "reviewed": 1, "critical_items": 0, "minor_only_items": 1}
    assert stratum_rule[("sanmingtonghui", 1)] == {"reviewed": 3, "critical_items": 0}


def test_integrity_check():
    base = fixtures.tmp_dir("acceptance_integrity")
    try:
        man = {"chapters": [
            {"chapter_index": 25, "rule_ids": [], "mcq_ids": [],
             "raw_source_path": "raw/25.txt", "zero_rule": True, "zero_mcq": True},
            {"chapter_index": 26, "rule_ids": ["r1"], "mcq_ids": [],
             "raw_source_path": "raw/26.txt", "zero_rule": False, "zero_mcq": True},
        ]}
        (base / "raw").mkdir(parents=True)
        for ci in (25, 26):
            (base / "raw" / f"{ci}.txt").write_text("原文", encoding="utf-8")
        for p in c.DRIFT_FILES:
            q = base / p
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_text("{}", encoding="utf-8")
        src = c.DirSource(base)
        res = review.integrity_check(man, src)
        assert res["source_missing_chapters"] == []
        assert res["missing_drift_files"] == []
        (base / "raw" / "25.txt").unlink()
        res = review.integrity_check(man, src)
        assert res["source_missing_chapters"] == [25]
        (base / c.DRIFT_FILES[1]).unlink()
        res = review.integrity_check(man, src)
        assert res["missing_drift_files"] == [c.DRIFT_FILES[1]]
    finally:
        fixtures.rmtree_force(base)


def _m(reviewed, critical, minor=0):
    return {"reviewed": reviewed, "critical_items": critical, "minor_only_items": minor}


CLEAN = {"source_missing_chapters": [], "missing_drift_files": []}


def test_decide_state_edges():
    s = review.decide_state({("b", "rule"): _m(100, 2)}, {}, {}, CLEAN, [])
    assert s["verdict"] == "ACCEPT"
    s = review.decide_state({("b", "rule"): _m(100, 3)}, {}, {}, CLEAN, [])
    assert s["verdict"] == "EXPAND"
    assert s["pending_expands"] == [{"book": "b", "type": "rule"}]
    s = review.decide_state({("b", "rule"): _m(100, 5)}, {}, {}, CLEAN, [])
    assert s["verdict"] == "EXPAND"
    s = review.decide_state({("b", "rule"): _m(100, 6)}, {}, {}, CLEAN, [])
    assert s["verdict"] == "REJECT" and s["fired_rules"] == ["REJECT_GATE"]
    s = review.decide_state({("b", "rule"): _m(100, 3)}, {}, {}, CLEAN,
                            [{"book": "b", "type": "rule"}])
    assert s["verdict"] == "REJECT" and s["fired_rules"] == ["EXPAND_GATE"]
    s = review.decide_state({("b", "rule"): _m(200, 4)}, {}, {}, CLEAN,
                            [{"book": "b", "type": "rule"}])
    assert s["verdict"] == "ACCEPT"


def test_decide_state_priority_order():
    s = review.decide_state({("b", "rule"): _m(100, 50)},
                            {("b", 2): {"reviewed": 7, "critical_items": 1}},
                            {("b", "rule"): 1}, CLEAN, [])
    assert s["fired_rules"] == ["BOUNDARY"]
    s = review.decide_state({("b", "rule"): _m(100, 1)},
                            {("b", 2): {"reviewed": 7, "critical_items": 1}},
                            {}, CLEAN, [])
    assert s["fired_rules"] == ["STRATUM_CASCADE"]
    s = review.decide_state({("b", "rule"): _m(100, 50)},
                            {("b", 2): {"reviewed": 7, "critical_items": 1}},
                            {("b", "rule"): 3},
                            {"source_missing_chapters": [25],
                             "missing_drift_files": []}, [])
    assert s["fired_rules"] == ["INTEGRITY"]


def test_check_receipt_requirements_gate():
    # F22: no criticals -> no receipts allowed
    assert review.check_receipt_requirements(False, False, False, False) == (False, False)
    with pytest.raises(RuntimeError, match="not allowed"):
        review.check_receipt_requirements(False, False, True, False)
    with pytest.raises(RuntimeError, match="not allowed"):
        review.check_receipt_requirements(False, False, False, True)
    # criticals but second missing -> required
    with pytest.raises(RuntimeError, match="required"):
        review.check_receipt_requirements(True, False, False, False)
    # criticals, no disagreement -> second required, arbitration forbidden
    assert review.check_receipt_requirements(True, False, True, False) == (True, False)
    with pytest.raises(RuntimeError, match="not allowed"):
        review.check_receipt_requirements(True, False, True, True)
    # criticals, disagreement -> both required
    assert review.check_receipt_requirements(True, True, True, True) == (True, True)
    with pytest.raises(RuntimeError, match="required"):
        review.check_receipt_requirements(True, True, True, False)


def _tiny_all_pass_primary(sm):
    # all-PASS primary over the full tiny sample. sanmingtonghui items must
    # carry their REAL chapter (the id embeds the chapter number) so the new
    # source_chapter identity check in validate_primary passes; _primary_entry
    # defaults to 1, which would fail once chapter 2/3/85 items are checked.
    primary = _mini_primary()
    items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    entry = _primary_entry(book, item_type, iid)
                    if book == "sanmingtonghui":
                        entry["item"]["source_chapter"] = int(iid.split("_")[1])
                    items.append(entry)
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            entry = _primary_entry("sanmingtonghui", item_type, iid)
            entry["item"]["source_chapter"] = int(iid.split("_")[1])
            items.append(entry)
    primary["items"] = items
    return primary


def test_validate_decision_inputs_shared_path_and_f22_gate(tiny):
    # P0-2: the shared helper both computes the verdict and enforces the F22
    # receipt gate; cmd_decide and cmd_expand call the SAME function.
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    # all-PASS -> ACCEPT
    _, _, _, report = review.validate_decision_inputs(
        sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
        p_path, None, None)
    assert report["verdict"] == "ACCEPT"
    # P0-2: decision report must carry its data-source identity (design §12.2)
    assert report["data_source"] == desc
    # an unrequired arbitration receipt is rejected by the F22 gate even
    # though arbitration validation would otherwise accept it
    arb = _arb_receipt({}, arbitrator="r3")
    arb_path = base / "arb.json"
    fixtures.write_json(arb_path, arb)
    with pytest.raises(RuntimeError, match="not allowed"):
        review.validate_decision_inputs(
            sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
            p_path, None, arb_path)


def test_verify_producing_report_rejects_handcrafted_expand(tiny):
    # P0-1: an expansion consumer recomputes the producing verdict from the
    # R1 primary/second/arbitration; a hand-crafted EXPAND report for an
    # all-PASS primary (real verdict ACCEPT) is rejected.
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    _, _, _, real = review.validate_decision_inputs(
        sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
        p_path, None, None)
    assert real["verdict"] == "ACCEPT"
    # forged report: binds the real primary/sample but claims EXPAND
    forged = dict(real, verdict="EXPAND", fired_rules=["EXPAND_GATE"],
                  pending_expands=[{"book": "sanmingtonghui", "type": "rule"}])
    r_path = base / "forged_report.json"
    fixtures.write_json(r_path, forged)
    with pytest.raises(RuntimeError, match="recomputed"):
        review.verify_producing_report(
            r_path, sm, fixtures.sha256_file(sm_path), ch_manifest, source, desc, True,
            p_path, None, None)
    # the genuine ACCEPT report is also rejected (verdict is not EXPAND)
    real_path = base / "real_report.json"
    fixtures.write_json(real_path, real)
    with pytest.raises(RuntimeError, match="not EXPAND"):
        review.verify_producing_report(
            real_path, sm, fixtures.sha256_file(sm_path), ch_manifest, source, desc, True,
            p_path, None, None)


@pytest.mark.parametrize("flag", [
    "expansion-manifest", "decision-report",
    "producing-primary", "producing-second", "producing-arbitration"])
def test_decide_cli_rejects_expansion_flags(flag):
    # P0-1: Task 6 decide is single-round non-expansion; these flags are NOT
    # registered and must be rejected as unknown flags (fail-closed), not
    # crash on the Task-7-only validate_expansion_manifest.
    argv = [sys.executable, str(fixtures.SCRIPTS / "classic_acceptance_review.py"),
            "decide", "--primary", "p.json", "--sample-manifest", "sm.json",
            "--chapter-manifest", "ch.json", "--data-root", ".",
            "--out", "o", f"--{flag}", "ghost.json"]
    result = fixtures.run_argv_result(argv)
    assert not result.timed_out and result.returncode != 0, (
        f"--{flag} must be rejected without timing out")
    assert "unknown flag" in result.stdout + result.stderr, (
        f"--{flag} should fail with an unknown-flag error")


def test_verify_producing_report_reads_report_once(tiny, monkeypatch):
    # P0-3: verify_producing_report must read the report path exactly ONCE.
    # Simulate an in-place file swap on a second read: if the implementation
    # re-read for the parsed object/SHA, the swapped bytes would be used and
    # the byte-equality verdict would rest on a different file version.
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    _, _, _, real = review.validate_decision_inputs(
        sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
        p_path, None, None)
    forged = dict(real, verdict="EXPAND", fired_rules=["EXPAND_GATE"],
                  pending_expands=[{"book": "sanmingtonghui", "type": "rule"}])
    r_path = base / "forged_report.json"
    fixtures.write_json(r_path, forged)
    reads = []
    orig_read_bytes = Path.read_bytes

    def counting_read(self, *a, **k):
        if str(self) == str(r_path):
            reads.append(1)
            if len(reads) >= 2:
                return b'{"kind": "swapped"}'   # simulate a mid-check file swap
        return orig_read_bytes(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", counting_read)
    with pytest.raises(RuntimeError, match="recomputed"):
        review.verify_producing_report(
            r_path, sm, fixtures.sha256_file(sm_path), ch_manifest, source, desc, True,
            p_path, None, None)
    assert len(reads) == 1   # exactly one read of the report path


def _real_all_pass_primary(sm, sm_path, chapter_manifest):
    # Generic all-PASS primary over a real/frozen sample: sanmingtonghui items
    # keep their REAL chapter from the chapter manifest (real ids do NOT embed
    # the chapter number, so we cannot parse it from the id).
    chapter_of = {}
    for ch in chapter_manifest["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]
    items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    sc = chapter_of[iid] if book == "sanmingtonghui" else 1
                    items.append({"item": {"book": book, "type": item_type, "id": iid,
                                           "source_chapter": sc},
                                  "verdict": "PASS", "findings": []})
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            items.append({"item": {"book": "sanmingtonghui", "type": item_type,
                                   "id": iid, "source_chapter": chapter_of[iid]},
                          "verdict": "PASS", "findings": []})
    return {"schema_version": "1.0", "kind": "primary_review_package",
            "sample_manifest_sha256": c.sha256_file_raw(sm_path),
            "expansion_manifests_sha256": [], "items": items,
            "overall_stats": {}, "zero_output_report": [],
            "reviewer_list": ["r1"]}


def test_verify_producing_report_success_returns_pinned_sha(tiny, monkeypatch):
    # P0: SUCCESS path -- a genuine EXPAND report must return (report, report_sha)
    # where report_sha is the SHA of the FIRST read's raw bytes, and the report
    # path is read exactly ONCE (a swapped file on a second read is never seen).
    base, data, chman_path, man, source, sm = tiny
    # custom sample: qiongtongbaojian rule with 40 reviewed items -> 2/40 = 5%
    # critical rate lands in the EXPAND band (2%, 5%]; no other category matters.
    custom_sm = {
        "schema_version": "1.0", "kind": "sample_manifest_v1",
        "samples": {
            "sanmingtonghui": {"rule": {"1": []}, "mcq": {"1": []}},
            "qiongtongbaojian": {"rule": {"1": [f"q{i:03d}" for i in range(40)]},
                                 "mcq": {"1": []}},
            "ditiansui": {"rule": {"1": []}, "mcq": {"1": []}},
            "zipingzhenquan": {"rule": {"1": []}, "mcq": {"1": []}},
        },
        "boundary_samples": {
            "sanmingtonghui": {"rule": [], "mcq": []},
            "qiongtongbaojian": {"rule": [], "mcq": []},
            "ditiansui": {"rule": [], "mcq": []},
            "zipingzhenquan": {"rule": [], "mcq": []},
        },
    }
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(custom_sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = {"schema_version": "1.0", "kind": "primary_review_package",
               "sample_manifest_sha256": fixtures.sha256_file(sm_path),
               "expansion_manifests_sha256": [],
               "overall_stats": {}, "zero_output_report": [],
               "reviewer_list": ["reviewer-1"],
               "items": [
                   {"item": {"book": "qiongtongbaojian", "type": "rule", "id": f"q{i:03d}",
                             "source_chapter": 1},
                    "verdict": ("FAIL" if i < 2 else "PASS"),
                    "findings": ([fixtures.critical()] if i < 2 else [])}
                   for i in range(40)]}
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    second = {"schema_version": "1.0", "kind": "second_review_receipt_v1",
              "primary_sha256": fixtures.sha256_file(p_path),
              "reviewer": "reviewer-2",
              "reviewed_at": "2026-08-23T00:00:00+08:00",
              "entries": [
                  {"book": "qiongtongbaojian", "type": "rule", "id": f"q{i:03d}",
                   "finding_index": 0, "agree": True, "evidence_text": "e",
                   "reviewer": "reviewer-2",
                   "reviewed_at": "2026-08-23T00:00:00+08:00"}
                  for i in range(2)]}
    s_path = base / "second.json"
    fixtures.write_json(s_path, second)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    _, _, _, report = review.validate_decision_inputs(
        custom_sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
        p_path, s_path, None)
    assert report["verdict"] == "EXPAND"
    r_path = base / "expand_report.json"
    fixtures.write_json(r_path, report)
    original_bytes = Path(r_path).read_bytes()
    expected_sha = c.sha256_bytes(original_bytes)
    reads = []
    orig_read_bytes = Path.read_bytes

    def counting_read(self, *a, **k):
        if str(self) == str(r_path):
            reads.append(1)
            if len(reads) >= 2:
                return b'{"kind": "swapped"}'
        return orig_read_bytes(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", counting_read)
    rep, rep_sha = review.verify_producing_report(
        r_path, custom_sm, fixtures.sha256_file(sm_path), ch_manifest, source, desc, True,
        p_path, s_path, None)
    assert rep["verdict"] == "EXPAND"
    assert rep["kind"] == "decision_report_v1"
    assert rep_sha == expected_sha        # SHA pinned to the first read's bytes
    assert reads == [1]                    # success path reads the report once


def test_decide_production_report_data_source():
    # P0-2 (production): a production decision report carries test_only=False
    # and the git data-source identity (design section 12.2).
    base = fixtures.tmp_dir("decide_prod_ds")
    try:
        man, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
        source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
        git_desc = {"kind": "git", "candidate_commit": fixtures.COMMIT,
                    "test_only": False}
        sm = sampling.build_sample_manifest(man, source, git_desc, chman_sha)
        sm_path = base / "sample_manifest_v1.json"
        sm_path.write_bytes(c.serialize_json(sm))
        primary = _real_all_pass_primary(sm, sm_path, man)
        p_path = base / "primary.json"
        fixtures.write_json(p_path, primary)
        _, _, _, report = review.validate_decision_inputs(
            sm, [], man, source, git_desc, fixtures.sha256_file(sm_path), [], False,
            p_path, None, None)
        assert report["verdict"] == "ACCEPT"
        assert report["test_only"] is False
        assert report["data_source"] == {
            "kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False}
    finally:
        fixtures.rmtree_force(base)


def test_validate_decision_inputs_uses_pinned_expansion_sha(tiny):
    # P0: validate_decision_inputs receives expansion_shas (pinned by the
    # caller's single read) and NEVER re-opens the expansion file; the report
    # binds exactly those pinned SHAs, and a tampered pinned sha fails closed.
    base, data, chman_path, man, source, sm = tiny
    custom_sm = {
        "schema_version": "1.0", "kind": "sample_manifest_v1",
        "samples": {
            "sanmingtonghui": {"rule": {"1": []}, "mcq": {"1": []}},
            "qiongtongbaojian": {"rule": {"1": [f"q{i:03d}" for i in range(40)]},
                                 "mcq": {"1": []}},
            "ditiansui": {"rule": {"1": []}, "mcq": {"1": []}},
            "zipingzhenquan": {"rule": {"1": []}, "mcq": {"1": []}},
        },
        "boundary_samples": {
            "sanmingtonghui": {"rule": [], "mcq": []},
            "qiongtongbaojian": {"rule": [], "mcq": []},
            "ditiansui": {"rule": [], "mcq": []},
            "zipingzhenquan": {"rule": [], "mcq": []},
        },
    }
    em = {"schema_version": "1.0", "kind": "expansion_manifest_v1",
          "round": 1, "expanded_pairs": [{"book": "qiongtongbaojian", "type": "rule"}],
          "expansions": {"qiongtongbaojian": {"rule": {
              "1": {"new_ids": ["q040", "q041"]}}}},
          "totals": {"qiongtongbaojian": {"rule": 2}}}
    em_bytes = c.serialize_json(em)
    em_sha = c.sha256_bytes(em_bytes)
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(custom_sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = {"schema_version": "1.0", "kind": "primary_review_package",
               "sample_manifest_sha256": fixtures.sha256_file(sm_path),
               "expansion_manifests_sha256": [em_sha],
               "overall_stats": {}, "zero_output_report": [],
               "reviewer_list": ["reviewer-1"],
               "items": [
                   {"item": {"book": "qiongtongbaojian", "type": "rule",
                             "id": f"q{i:03d}", "source_chapter": 1},
                    "verdict": "PASS", "findings": []}
                   for i in range(42)]}
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    _, _, _, report = review.validate_decision_inputs(
        custom_sm, [em], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [em_sha], True,
        p_path, None, None)
    # the report binds the PINNED sha; no expansion file was ever re-opened
    assert report["expansion_manifests_sha256"] == [em_sha]
    # a tampered pinned sha is rejected by the binding check (proves the
    # pinned value is authoritative, not a re-read)
    with pytest.raises(RuntimeError, match="expansion_manifests_sha256 mismatch"):
        review.validate_decision_inputs(
            custom_sm, [em], ch_manifest, source, desc, fixtures.sha256_file(sm_path), ["0" * 64], True,
            p_path, None, None)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: `AttributeError: ... has no attribute 'canonicalize'`

- [ ] **Step 3: 实现（追加到 `scripts/classic_acceptance_review.py`）**

```python
def canonicalize(primary, second, arbitration):
    """Design section 6.4 ADJUDICATION (v4.6.1, F3): every critical finding
    resolves to ADJUDICATED_CRITICAL (second agrees or arbitration upholds)
    or is DELETED when arbitration says non_critical. A DELETED finding
    contributes to neither the critical nor the minor-only numerator, but its
    item REMAINS in the reviewed denominator (compute_metrics counts every
    reviewed item). Minor primary findings pass through as PRIMARY_MINOR.
    Item verdict is recomputed from the remaining findings; an item with no
    remaining findings is absent from the verdict map (treated as PASS, still
    counted as reviewed)."""
    second_by_ref = {(e["book"], e["type"], e["id"], e["finding_index"]): e
                     for e in (second or {}).get("entries", [])}
    arb_by_ref = {(e["book"], e["type"], e["id"], e["finding_index"]): e
                  for e in (arbitration or {}).get("entries", [])}
    canonical = []
    for entry in primary["items"]:
        item = entry["item"]
        for idx, f in enumerate(entry.get("findings", [])):
            base = {"book": item["book"], "type": item["type"], "id": item["id"],
                    "finding_index": idx, "category": f.get("category")}
            if f.get("severity") != "critical":
                canonical.append({**base, "severity": "minor", "state": "PRIMARY_MINOR"})
                continue
            ref = (item["book"], item["type"], item["id"], idx)
            e = second_by_ref.get(ref)
            c.require(e is not None, f"critical finding {ref} lacks a second-review entry")
            if e["agree"]:
                canonical.append({**base, "severity": "critical",
                                  "state": "ADJUDICATED_CRITICAL"})
                continue
            a = arb_by_ref.get(ref)
            c.require(a is not None,
                      f"disputed critical finding {ref} lacks an arbitration entry")
            if a["decision"] == "critical":
                canonical.append({**base, "severity": "critical",
                                  "state": "ADJUDICATED_CRITICAL"})
            # decision == "non_critical": finding DELETED (F3), not appended.
    return canonical


def item_verdicts(canonical):
    crit, minor = defaultdict(int), defaultdict(int)
    for f in canonical:
        key = (f["book"], f["type"], f["id"])
        if f["severity"] == "critical":
            crit[key] += 1
        else:
            minor[key] += 1
    return {key: ("FAIL" if crit[key] else "PASS_WITH_MINOR")
            for key in set(crit) | set(minor)}


def item_meta_map(sample_manifest, expansions, chapter_manifest):
    meta = {}

    def put(key, stratum, boundary):
        c.require(key not in meta, f"duplicate reviewed item key: {key}")
        meta[key] = {"stratum": stratum, "boundary": boundary}

    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for s, ids in sample_manifest["samples"][book][item_type].items():
                for iid in ids:
                    put((book, item_type, iid), int(s), False)
    chapter_of = {}
    for ch in chapter_manifest["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]
    for item_type in ("rule", "mcq"):
        for iid in sample_manifest["boundary_samples"]["sanmingtonghui"][item_type]:
            put(("sanmingtonghui", item_type, iid),
                sampling.stratum_of("sanmingtonghui", chapter_of[iid]), True)
    for em in expansions:
        for book, types in em["expansions"].items():
            for item_type, strata in types.items():
                for s, info in strata.items():
                    for iid in info["new_ids"]:
                        put((book, item_type, iid), int(s), False)
    return meta


def compute_metrics(verdicts, meta):
    metrics = defaultdict(lambda: {"reviewed": 0, "critical_items": 0, "minor_only_items": 0})
    stratum_rule = defaultdict(lambda: {"reviewed": 0, "critical_items": 0})
    boundary_crit = defaultdict(int)
    for key, m in meta.items():
        book, item_type, _iid = key
        verdict = verdicts.get(key, "PASS")   # absent => no FAIL/minor finding, but reviewed
        mm = metrics[(book, item_type)]
        mm["reviewed"] += 1                   # F3: denominator counts every reviewed item
        if verdict == "FAIL":
            mm["critical_items"] += 1
            if m["boundary"]:
                boundary_crit[(book, item_type)] += 1
            if item_type == "rule":
                stratum_rule[(book, m["stratum"])]["critical_items"] += 1
        elif verdict == "PASS_WITH_MINOR":
            mm["minor_only_items"] += 1
        if item_type == "rule":
            stratum_rule[(book, m["stratum"])]["reviewed"] += 1
    return metrics, stratum_rule, boundary_crit


def decide_state(metrics, stratum_rule, boundary_crit, integrity, expanded_pairs):
    if integrity["source_missing_chapters"] or integrity["missing_drift_files"]:
        return {"verdict": "REJECT", "fired_rules": ["INTEGRITY"], "pending_expands": []}
    for (_book, _item_type), n in sorted(boundary_crit.items()):
        if n > 0:
            return {"verdict": "REJECT", "fired_rules": ["BOUNDARY"], "pending_expands": []}
    for (_book, _stratum), m in sorted(stratum_rule.items()):
        if m["critical_items"] * 100 > c.STRATUM_CASCADE_PCT * m["reviewed"]:
            return {"verdict": "REJECT", "fired_rules": ["STRATUM_CASCADE"],
                    "pending_expands": []}
    for (_book, _item_type), m in sorted(metrics.items()):
        if m["critical_items"] * 100 > c.REJECT_PCT * m["reviewed"]:
            return {"verdict": "REJECT", "fired_rules": ["REJECT_GATE"], "pending_expands": []}
        if m["minor_only_items"] * 100 > c.MINOR_REJECT_PCT * m["reviewed"]:
            return {"verdict": "REJECT", "fired_rules": ["REJECT_GATE"], "pending_expands": []}
    pending = []
    for (book, item_type), m in sorted(metrics.items()):
        in_band = (m["critical_items"] * 100 > c.EXPAND_LOW_PCT * m["reviewed"]
                   and m["critical_items"] * 100 <= c.REJECT_PCT * m["reviewed"])
        if not in_band:
            continue
        if {"book": book, "type": item_type} in expanded_pairs:
            return {"verdict": "REJECT", "fired_rules": ["EXPAND_GATE"], "pending_expands": []}
        pending.append({"book": book, "type": item_type})
    if pending:
        return {"verdict": "EXPAND", "fired_rules": ["EXPAND_GATE"], "pending_expands": pending}
    return {"verdict": "ACCEPT", "fired_rules": [], "pending_expands": []}


def _serialize_book_type_metrics(metrics):
    out = {}
    for (book, item_type), m in sorted(metrics.items()):
        out.setdefault(book, {})[item_type] = {
            "reviewed": m["reviewed"], "critical_items": m["critical_items"],
            "critical_rate": f"{m['critical_items']}/{m['reviewed']}",
            "minor_only_items": m["minor_only_items"],
            "minor_rate": f"{m['minor_only_items']}/{m['reviewed']}"}
    return out


def _serialize_stratum_metrics(stratum_rule):
    out = {}
    for (book, stratum), m in sorted(stratum_rule.items()):
        out.setdefault(book, {})[str(stratum)] = {
            "reviewed": m["reviewed"], "critical_items": m["critical_items"],
            "critical_rate": f"{m['critical_items']}/{m['reviewed']}"}
    return out


# Task 6: decide is single-round non-expansion only. Expansion flags
# (--expansion-manifest/--decision-report/--producing-*) are re-wired in
# Task 7 (alongside validate_expansion_manifest) and MUST be rejected here
# (fail-closed, strict CLI section 12.4) rather than crash on a Task-7-only
# function.
DECIDE_FLAGS = {"primary", "sample-manifest", "chapter-manifest", "out",
                "candidate-commit", "data-root",
                "second", "arbitration"}


def check_receipt_requirements(has_criticals, has_disagreement,
                               second_provided, arbitration_provided):
    """F22: pure state-machine gate on which receipts the CLI may pass.
    Raises if a receipt is provided when not required (or required when
    missing). Returns (need_second, need_arbitration)."""
    if not has_criticals:
        c.require(not second_provided,
                  "--second is not allowed: primary has no critical findings (F22)")
        c.require(not arbitration_provided,
                  "--arbitration is not allowed without critical findings (F22)")
        return False, False
    c.require(second_provided,
              "primary has critical findings: --second <receipt> is required")
    if not has_disagreement:
        c.require(not arbitration_provided,
                  "--arbitration is not allowed: second review has no "
                  "disagreements (F22)")
        return True, False
    c.require(arbitration_provided,
              "second review disagrees on criticals: --arbitration <receipt> is required")
    return True, True


def compute_decision(primary, second, arbitration, sample_manifest, expansions,
                     chapter_manifest, source, source_desc, expansion_shas,
                     primary_sha, second_sha, arbitration_sha, sm_sha):
    """Run the full adjudication + section-6.2 state machine from the raw
    receipts and frozen data, and return the decision report dict. This is the
    SAME code path for both `decide` (producer) and `expand` (which must
    recompute the verdict rather than trust a hand-crafted report). All SHAs
    are pinned by the caller (raw on-disk bytes, F20): this function NEVER
    re-opens any artifact path (no TOCTOU). The caller is responsible for
    validating the manifests and receipts before calling this."""
    canonical = canonicalize(primary, second, arbitration)
    verdicts = item_verdicts(canonical)
    integrity = integrity_check(chapter_manifest, source)
    meta = item_meta_map(sample_manifest, expansions, chapter_manifest)
    metrics, stratum_rule, boundary_crit = compute_metrics(verdicts, meta)
    expanded_pairs = []
    for em in expansions:
        for pair in em.get("expanded_pairs", []):
            if pair not in expanded_pairs:
                expanded_pairs.append(pair)
    state = decide_state(metrics, stratum_rule, boundary_crit, integrity, expanded_pairs)
    return {
        "schema_version": "1.0",
        "kind": "decision_report_v1",
        "test_only": bool(source_desc.get("test_only")),
        # P0-2: design section 12.2 requires the decision product to carry its
        # data-source identity (fake/production provenance).
        "data_source": source_desc,
        "primary_sha256": primary_sha,
        "second_review_sha256": second_sha,
        "arbitration_sha256": arbitration_sha,
        "sample_manifest_sha256": sm_sha,
        # P0: expansion SHAs are pre-pinned by the caller's single read; the
        # decision report never re-opens the expansion file (no TOCTOU).
        "expansion_manifests_sha256": expansion_shas,
        "expanded_pairs": expanded_pairs,
        "adjudication": {
            "canonical_findings": canonical,
            "second_review_entries": len(second["entries"]) if second else 0,
            "arbitration_entries": len(arbitration["entries"]) if arbitration else 0,
        },
        "metrics": _serialize_book_type_metrics(metrics),
        "stratum_rule_metrics": _serialize_stratum_metrics(stratum_rule),
        "boundary_critical_items": {f"{book}/{item_type}": n
                                    for (book, item_type), n in sorted(boundary_crit.items())},
        "integrity": integrity,
        "fired_rules": state["fired_rules"],
        "verdict": state["verdict"],
        "pending_expands": state["pending_expands"],
    }


def validate_decision_inputs(sample_manifest, expansions, chapter_manifest,
                             source, source_desc, sm_sha, expansion_shas,
                             expected_test_only,
                             primary_path, second_path, arbitration_path):
    """Shared single-round decision validation used by `decide` (producer),
    `expand` (which must recompute the producing verdict), and the expansion
    consumers. Reads primary/second/arbitration receipts ONCE each (object +
    raw-byte SHA pinned from the same bytes); sample_manifest and sm_sha are
    pinned by the caller (single read). Enforces the F22 receipt gate,
    validates second/arbitration exactly when the state machine requires, then
    runs compute_decision with the pinned SHAs. Returns
    (primary, second, arbitration, report)."""
    # P0: read each receipt ONCE; its object and raw-byte SHA come from the
    # same bytes and are passed downstream (never re-open a path).
    primary, primary_sha = c.load_json_with_sha(primary_path)
    # P0: expansion_shas are the caller's pinned SHAs from a single read;
    # never re-open the expansion files here.
    validate_primary(primary, sample_manifest, expansions, sm_sha,
                     expansion_shas, chapter_manifest)
    criticals = critical_refs(primary)
    second = second_sha = None
    arbitration = arbitration_sha = None
    has_disagreement = False
    if criticals:
        c.require(second_path,
                  "primary has critical findings: --second <receipt> is required")
        second, second_sha = c.load_json_with_sha(second_path)
        validate_second(second, primary, primary_sha)
        has_disagreement = bool(disagreement_refs(second))
    check_receipt_requirements(bool(criticals), has_disagreement,
                               bool(second_path), bool(arbitration_path))
    if has_disagreement:
        arbitration, arbitration_sha = c.load_json_with_sha(arbitration_path)
        validate_arbitration(arbitration, primary, second, primary_sha, second_sha)
    report = compute_decision(primary, second, arbitration, sample_manifest,
                              expansions, chapter_manifest, source, source_desc,
                              expansion_shas, primary_sha, second_sha,
                              arbitration_sha, sm_sha)
    return primary, second, arbitration, report


def verify_producing_report(report_path, sample_manifest, sm_sha,
                            chapter_manifest, source, source_desc,
                            expected_test_only, producing_primary_path,
                            producing_second_path, producing_arbitration_path):
    """P0: verify an expansion's producing decision report was actually
    produced by the state machine, not hand-crafted. Reads the report as RAW
    on-disk bytes (F20: CRLF, extra whitespace, reordered/duplicate JSON keys
    all change the bytes and are rejected), parses it for field checks, then
    RECOMPUTES the verdict from the producing primary/second/arbitration (via
    validate_decision_inputs with expansions=[]) and requires the on-disk
    bytes to be byte-identical to the recomputed canonical bytes and verdict
    == EXPAND. Returns (report, report_sha): the verified report dict plus the
    raw on-disk byte SHA pinned to the single read, which consumers reuse
    (never re-read the report path). The producing artifacts are the R1 round
    (no expansions)."""
    # P0-3: read the report path ONCE; the parsed object and its pinned SHA
    # both come from those exact bytes (no TOCTOU re-read window). Task 7
    # consumers reuse the returned (report, report_sha) and never re-read.
    actual_bytes = Path(report_path).read_bytes()
    report = json.loads(actual_bytes.decode("utf-8"))
    report_sha = c.sha256_bytes(actual_bytes)
    c.require(isinstance(report, dict), "producing decision report: not an object")
    c.require(report.get("kind") == "decision_report_v1",
              "producing decision report: wrong kind")
    c.require(isinstance(report.get("test_only"), bool),
              "producing decision report: test_only missing")
    c.require(report.get("test_only") is expected_test_only,
              "producing decision report: cross-mode test_only rejected")
    c.require(report.get("sample_manifest_sha256") == sm_sha,
              "producing decision report does not bind this sample manifest")
    c.require(report.get("expansion_manifests_sha256") == [],
              "producing decision report must reference no prior expansions (round 1)")
    c.require(report.get("decision_report_sha256") is None,
              "producing decision report must not reference another decision report")
    # Recompute the verdict from the R1 receipts via the SAME code path
    # `decide` uses (F22 receipt gate included); compare the RAW on-disk bytes
    # to the canonical recomputed bytes so CRLF/whitespace/key-order/duplicate
    # key tampering is rejected.
    _, _, _, recomputed = validate_decision_inputs(
        sample_manifest, [], chapter_manifest, source, source_desc, sm_sha, [],
        expected_test_only, producing_primary_path,
        producing_second_path, producing_arbitration_path)
    expected_bytes = c.serialize_json(recomputed)
    c.require(actual_bytes == expected_bytes,
              "producing decision report bytes do not match the verdict recomputed "
              "from its primary/second/arbitration (hand-crafted or re-serialized "
              "report rejected)")
    c.require(recomputed["verdict"] == "EXPAND" and recomputed["pending_expands"],
              f"producing decision verdict is {recomputed['verdict']!r}, "
              f"not EXPAND; expansion not authorized")
    return report, report_sha


def check_producing_evidence_presence(has_expansion, producing_report_path,
                                      pp_path, ps_path, pa_path, who):
    """Medium: the producing-evidence flags only make sense with an expansion.
    Require them all-or-nothing with --expansion-manifest so a caller cannot
    pass (and then silently ignore) a producing report/evidence bundle when no
    expansion is consumed."""
    if has_expansion:
        c.require(producing_report_path and pp_path,
                  f"{who}: --expansion-manifest requires --decision-report and "
                  f"--producing-primary (the R1 evidence bundle)")
    else:
        stray = [n for n, v in
                 (("--decision-report", producing_report_path),
                  ("--producing-primary", pp_path),
                  ("--producing-second", ps_path),
                  ("--producing-arbitration", pa_path)) if v]
        c.require(not stray,
                  f"{who}: producing-evidence flags {stray} require "
                  f"--expansion-manifest (passed without an expansion; ignored otherwise)")


def cmd_decide(argv):
    # Task 6: single-round decide without an expansion. The expansion path
    # (producing-evidence chain via verify_producing_report +
    # validate_expansion_manifest) is re-wired in Task 7.
    flags, _ = c.parse_flags(argv, allowed=DECIDE_FLAGS)
    primary_path = c.flag1(flags, "primary")
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    second_path = c.flag_opt(flags, "second")
    arbitration_path = c.flag_opt(flags, "arbitration")
    # F18/F19: frozen lock first, then full manifest validation before any read.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    # F22 receipt gate + primary/second/arbitration validation + verdict
    # computation are all in the shared helper (same path as `expand`).
    _primary, _second, _arbitration, report = validate_decision_inputs(
        sample_manifest, [], chapter_manifest, source, source_desc,
        sm_sha, [], is_fake, primary_path, second_path, arbitration_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decision_report_v1.json").write_bytes(c.serialize_json(report))
    print("verdict:", report["verdict"], "| fired:", report["fired_rules"],
          "| pending_expands:", report["pending_expands"],
          "| test_only:", report["test_only"])
```

dispatch 增加：

```python
        elif cmd == "decide":
            cmd_decide(argv[1:])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add scripts/classic_acceptance_review.py tests/test_classic_acceptance_review.py
git commit -m "feat(acceptance): adjudication + decision state machine (F3 denom kept)"
```

---

### Task 7: 扩样（`expand` 子命令）+ `validate-primary` expansion 授权

**Files:**
- Modify: `scripts/classic_acceptance_sampling.py`（追加 `build_expansion_manifest` / `validate_expansion_manifest` / `cmd_expand`）
- Modify: `scripts/classic_acceptance_review.py`（替换 Task 4 的无 expansion 版 `cmd_validate_primary`，接入 producing-evidence 授权链）
- Test: `tests/test_classic_acceptance_sampling.py`（追加）
- Test: `tests/test_classic_acceptance_review.py`（追加 validate-primary expansion 正负向测试）

- [ ] **Step 1: 写失败测试**

向 `tests/test_classic_acceptance_sampling.py` 追加：

```python
def test_expand_formula_min_and_disjoint():
    # The per-stratum formula added=min(k, remaining), disjointness, and the
    # expansion body are pure functions of the sample manifest; test them
    # directly (the CLI authorization/recomputation path is tested below).
    base = fixtures.tmp_dir("acceptance_expand")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        s1_all = [f"tiny_002_r{i:03d}" for i in range(6)] + \
                 [f"tiny_003_r{i:03d}" for i in range(6)]
        s2_all = [f"tiny_085_r{i:03d}" for i in range(6)]
        sampled_s1 = sm["samples"]["sanmingtonghui"]["rule"]["1"]
        sampled_s2 = sm["samples"]["sanmingtonghui"]["rule"]["2"]
        report_sha = "1" * 64
        em = sampling.build_expansion_manifest(
            sm, [{"book": "sanmingtonghui", "type": "rule"}], 1,
            man, source, desc, c.sha256_bytes(c.serialize_json(sm)), report_sha)
        assert em["kind"] == "expansion_manifest_v1"
        assert em["round"] == 1
        rule_exp = em["expansions"]["sanmingtonghui"]["rule"]
        # stratum 1 (chapters 1,2,3): full_population includes the boundary
        # chapter 1 (design section 6.3), so population = 2+6+6 = 14;
        # remaining = 14 - 2 boundary - 5 initial = 7 -> added = min(5, 7) = 5
        assert rule_exp["1"]["population"] == 14
        assert rule_exp["1"]["initial_random"] == 5
        assert rule_exp["1"]["boundary"] == 2
        assert rule_exp["1"]["k"] == 5
        assert rule_exp["1"]["added"] == 5
        # new_ids = the expand_score-ranked top-`added` of the 7 remaining ids
        # (NOT all 7: added caps it at k=5).
        remaining_s1 = sorted(set(s1_all) - set(sampled_s1))
        ranked_s1 = sorted(remaining_s1,
                           key=lambda iid: (c.expand_score("sanmingtonghui", "rule", 1, iid), iid))
        assert rule_exp["1"]["new_ids"] == sorted(ranked_s1[:rule_exp["1"]["added"]])
        # stratum 2: population 6, initial random 5, remaining 1
        # -> added = min(k=5, remaining=1) = 1 (the min-formula branch)
        assert rule_exp["2"]["population"] == 6
        assert rule_exp["2"]["initial_random"] == 5
        assert rule_exp["2"]["boundary"] == 0
        assert rule_exp["2"]["k"] == 5
        assert rule_exp["2"]["added"] == 1
        assert rule_exp["2"]["new_ids"] == sorted(set(s2_all) - set(sampled_s2))
        assert em["totals"]["sanmingtonghui"]["rule"] == 6
        old_ids = set()
        for ids in sm["samples"]["sanmingtonghui"]["rule"].values():
            old_ids.update(ids)
        old_ids.update(sm["boundary_samples"]["sanmingtonghui"]["rule"])
        new_ids = set()
        for info in em["expansions"]["sanmingtonghui"]["rule"].values():
            new_ids.update(info["new_ids"])
        assert not (new_ids & old_ids)
    finally:
        fixtures.rmtree_force(base)


def _all_pass_primary(sm, sm_path):
    items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    # sanmingtonghui items keep the REAL chapter (id embeds the
                    # chapter number); source_chapter=1 would fail the new
                    # validate_primary identity check before the recompute gate.
                    sc = int(iid.split("_")[1]) if book == "sanmingtonghui" else 1
                    items.append({"item": {"book": book, "type": item_type, "id": iid,
                                           "source_chapter": sc},
                                  "verdict": "PASS", "findings": []})
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            items.append({"item": {"book": "sanmingtonghui", "type": item_type,
                                   "id": iid,
                                   "source_chapter": int(iid.split("_")[1])},
                          "verdict": "PASS", "findings": []})
    return {"schema_version": "1.0", "kind": "primary_review_package",
            "sample_manifest_sha256": c.sha256_file_raw(sm_path),
            "expansion_manifests_sha256": [], "items": items,
            "overall_stats": {}, "zero_output_report": [],
            "reviewer_list": ["r1"]}


def test_expand_cli_rejects_handcrafted_expand_report():
    # P0: a hand-crafted decision report claiming verdict=EXPAND (but produced
    # from an all-PASS primary, whose real verdict is ACCEPT) must be rejected
    # by cmd_expand's verdict RECOMPUTATION, not just shape checks.
    import classic_acceptance_review as review
    base = fixtures.tmp_dir("acceptance_expand_authz")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        sm_path = base / "sample_manifest_v1.json"
        sm_path.write_bytes(c.serialize_json(sm))
        primary = _all_pass_primary(sm, sm_path)
        p_path = base / "primary.json"
        p_path.write_bytes(c.serialize_json(primary))
        # forged report: claims EXPAND for an unauthorized pair, binds the
        # real primary/sample SHAs so only recomputation can expose the lie
        forged = {"schema_version": "1.0", "kind": "decision_report_v1",
                  "test_only": True,
                  "primary_sha256": c.sha256_file_raw(p_path),
                  "second_review_sha256": None, "arbitration_sha256": None,
                  "sample_manifest_sha256": c.sha256_file_raw(sm_path),
                  "expansion_manifests_sha256": [], "expanded_pairs": [],
                  "adjudication": {"canonical_findings": [],
                                   "second_review_entries": 0,
                                   "arbitration_entries": 0},
                  "metrics": {}, "stratum_rule_metrics": {},
                  "boundary_critical_items": {},
                  "integrity": {"source_missing_chapters": [],
                                "missing_drift_files": []},
                  "fired_rules": ["EXPAND_GATE"], "verdict": "EXPAND",
                  "pending_expands": [{"book": "sanmingtonghui", "type": "rule"}]}
        r_path = base / "decision_report_v1.json"
        r_path.write_bytes(c.serialize_json(forged))
        result = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "expand",
            "--sample-manifest", str(sm_path),
            "--decision-report", str(r_path), "--primary", str(p_path),
            "--chapter-manifest", str(chman_path),
            "--data-root", str(data), "--out", str(base / "out"))
        assert not result.timed_out and result.returncode != 0
        out = result.stdout + result.stderr
        assert "recomput" in out or "does not match" in out
    finally:
        fixtures.rmtree_force(base)


def test_expand_cli_requires_primary_flag():
    # P0: --primary is now mandatory for recomputation; missing it is rejected
    # by the strict CLI parser (F16) rather than silently trusting the report.
    base = fixtures.tmp_dir("acceptance_expand_flags")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        sm_path = base / "sample_manifest_v1.json"
        sm_path.write_bytes(c.serialize_json(sm))
        r_path = base / "decision_report_v1.json"
        r_path.write_bytes(c.serialize_json({"kind": "decision_report_v1"}))
        result = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "expand",
            "--sample-manifest", str(sm_path),
            "--decision-report", str(r_path),
            "--chapter-manifest", str(chman_path),
            "--data-root", str(data), "--out", str(base / "out"))
        assert not result.timed_out and result.returncode != 0
        assert "exactly once" in (result.stdout + result.stderr) or \
               "requires" in (result.stdout + result.stderr)
    finally:
        fixtures.rmtree_force(base)


def test_validate_expansion_manifest_requires_expand_authorization():
    # P0: even a self-consistent expansion body is rejected without a producing
    # EXPAND report; a report with verdict != EXPAND or a pair not in
    # pending_expands is rejected; packet/decide must supply that report.
    import copy
    base = fixtures.tmp_dir("acceptance_val_exp_authz")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        sm_sha = c.sha256_bytes(c.serialize_json(sm))
        pairs = [{"book": "sanmingtonghui", "type": "rule"}]
        report = {"schema_version": "1.0", "kind": "decision_report_v1",
                  "test_only": True, "sample_manifest_sha256": sm_sha,
                  "expansion_manifests_sha256": [], "expanded_pairs": [],
                  "verdict": "EXPAND", "pending_expands": pairs,
                  "decision_report_sha256": None}
        report_sha = c.sha256_bytes(c.serialize_json(report))
        em = sampling.build_expansion_manifest(sm, pairs, 1, man, source,
                                               desc, sm_sha, report_sha)
        # happy path: authorized EXPAND report
        sampling.validate_expansion_manifest(em, sm, man, source, desc, sm_sha,
                                             expected_test_only=True,
                                             report=report, report_sha=report_sha)
        # no report at all -> rejected
        with pytest.raises(RuntimeError, match="producing decision report is required"):
            sampling.validate_expansion_manifest(
                copy.deepcopy(em), sm, man, source, desc, sm_sha,
                expected_test_only=True, report=None, report_sha=None)
        # verdict ACCEPT -> rejected (not an EXPAND authorization)
        acc = dict(report, verdict="ACCEPT", pending_expands=[])
        with pytest.raises(RuntimeError, match="not EXPAND"):
            sampling.validate_expansion_manifest(
                copy.deepcopy(em), sm, man, source, desc, sm_sha,
                expected_test_only=True, report=acc,
                report_sha=c.sha256_bytes(c.serialize_json(acc)))
        # expansion declares a pair the producing report did NOT authorize ->
        # rejected (unauthorized pair). Keep the SAME report (and report_sha)
        # so the rejected check is the pair mismatch, not the report binding.
        em_other_pair = sampling.build_expansion_manifest(
            sm, [{"book": "ditiansui", "type": "rule"}], 1, man, source,
            desc, sm_sha, report_sha)
        with pytest.raises(RuntimeError, match="pending_expands"):
            sampling.validate_expansion_manifest(
                em_other_pair, sm, man, source, desc, sm_sha,
                expected_test_only=True, report=report, report_sha=report_sha)
        # expansion bound to a different sample manifest -> rejected (tamper
        # the expansion's OWN binding; the report still binds the real one).
        bad_sm = copy.deepcopy(em)
        bad_sm["sample_manifest_sha256"] = "0" * 64
        with pytest.raises(RuntimeError, match="does not bind the current sample"):
            sampling.validate_expansion_manifest(
                bad_sm, sm, man, source, desc, sm_sha,
                expected_test_only=True, report=report, report_sha=report_sha)
    finally:
        fixtures.rmtree_force(base)
```

- [ ] **Step 1b: 写 `validate-primary` expansion 授权失败测试（追加到 `tests/test_classic_acceptance_review.py`）**

这三个门控测试在 `validate_expansion_manifest` 之前的层（flag 解析 / `check_producing_evidence_presence`）就被拒绝，所以用 dummy expansion/evidence 文件即可；genuine 正向路径与重构比对负向路径在 Task 9 的 e2e `test_e2e_validate_primary_expansion_genuine_then_tamper` 中覆盖。

```python
def _vp_base_cmd(tiny, run_name):
    # Shared happy-path base (fake source, valid sample + all-PASS primary)
    # for the validate-primary expansion-authorization CLI gate tests. These
    # never reach producing-report recomputation or expansion reconstruction,
    # so the expansion/evidence paths may point at dummy files.
    base, data, chman_path, man, source, sm = tiny
    run = base / run_name
    run.mkdir(parents=True, exist_ok=True)
    sm_path = run / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = run / "primary.json"
    fixtures.write_json(p_path, primary)
    dummy = run / "dummy.json"
    fixtures.write_json(dummy, {"kind": "whatever"})
    return [sys.executable, str(fixtures.SCRIPTS / "classic_acceptance_review.py"),
            "validate-primary",
            "--primary", str(p_path), "--sample-manifest", str(sm_path),
            "--chapter-manifest", str(chman_path), "--data-root", str(data)], dummy


def test_validate_primary_cli_rejects_expansion_without_producing_evidence(tiny):
    # P0/F19: --expansion-manifest requires the R1 evidence bundle
    # (--decision-report + --producing-primary); without it the expansion is
    # rejected by check_producing_evidence_presence, not silently accepted.
    cmd, dummy = _vp_base_cmd(tiny, "vp_no_evidence")
    result = fixtures.run_argv_result(cmd + ["--expansion-manifest", str(dummy)])
    assert not result.timed_out and result.returncode != 0
    assert "requires --decision-report" in (result.stdout + result.stderr)


def test_validate_primary_cli_rejects_duplicate_expansion(tiny):
    # P0/F19: at most one expansion is allowed (only one parallel expansion
    # round exists); a second --expansion-manifest is rejected by the strict
    # flag parser before any data is read.
    cmd, dummy = _vp_base_cmd(tiny, "vp_dup_exp")
    result = fixtures.run_argv_result(
        cmd + ["--expansion-manifest", str(dummy), "--expansion-manifest", str(dummy)])
    assert not result.timed_out and result.returncode != 0
    assert "at most once" in (result.stdout + result.stderr)


def test_validate_primary_cli_rejects_orphaned_producing_evidence(tiny):
    # Medium/F19: producing-evidence flags without --expansion-manifest are
    # orphaned (they would otherwise be silently ignored); rejected.
    cmd, dummy = _vp_base_cmd(tiny, "vp_orphan")
    result = fixtures.run_argv_result(
        cmd + ["--decision-report", str(dummy), "--producing-primary", str(dummy)])
    assert not result.timed_out and result.returncode != 0
    out = result.stdout + result.stderr
    assert "require --expansion-manifest" in out
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_classic_acceptance_sampling.py -q -k expand`
Expected: exit code != 0（unknown subcommand `expand`）

- [ ] **Step 3: 实现（追加到 `scripts/classic_acceptance_sampling.py`）**

```python
EXPAND_FLAGS = {"sample-manifest", "decision-report", "chapter-manifest", "out",
                "candidate-commit", "data-root",
                "primary", "second", "arbitration"}


def build_expansion_manifest(sample_manifest, pending, round_no, chapter_manifest,
                             source, source_desc, sm_sha, report_sha):
    """Deterministic expansion for the given (book, type) pairs: per stratum
    added_s = min(k_s, remaining_s), ranked by expand_score, disjoint from the
    initial random sample and the boundary set."""
    universe, _ = load_universe(chapter_manifest, source)
    boundary = boundary_items(chapter_manifest)
    expansions = {}
    totals = {}
    for pair in pending:
        book, item_type = pair["book"], pair["type"]
        population = universe[(book, item_type)]
        k_table = compute_k_table(book, item_type, population)
        bset = set(boundary["rule"] if item_type == "rule" else boundary["mcq"])
        initial = set()
        for ids in sample_manifest["samples"][book][item_type].values():
            initial.update(ids)
        chapter_of = {}
        if book == "sanmingtonghui":
            for ch in chapter_manifest["chapters"]:
                for iid in ch["rule_ids"] + ch["mcq_ids"]:
                    chapter_of[iid] = ch["chapter_index"]
        remaining = defaultdict(list)
        for iid, chapter in population.items():
            if iid not in bset and iid not in initial:
                remaining[stratum_of(book, chapter)].append(iid)
        pops = defaultdict(int)
        for iid, chapter in population.items():
            pops[stratum_of(book, chapter)] += 1
        per_stratum = {}
        added_total = 0
        for stratum in sorted(set(pops) | set(remaining)):
            ranked = sorted(remaining.get(stratum, []),
                            key=lambda iid: (c.expand_score(book, item_type, stratum, iid), iid))
            k = k_table.get(stratum, 0)
            added = min(k, len(ranked))
            # P0: boundary ids are sanmingtonghui-only (boundary chapters are
            # sanmingtonghui chapters). For a non-sanmingtonghui book chapter_of
            # is empty and stratum_of(book, None) would short-circuit to 1,
            # wrongly counting every boundary id as stratum 1. Guard by
            # membership so non-sanmingtonghui books report boundary = 0.
            b_in_stratum = sum(1 for iid in bset
                               if iid in chapter_of
                               and stratum_of(book, chapter_of[iid]) == stratum)
            per_stratum[str(stratum)] = {
                "population": pops.get(stratum, 0),
                "initial_random": len(sample_manifest["samples"][book][item_type]
                                      .get(str(stratum), [])),
                "boundary": b_in_stratum,
                "k": k,
                "added": added,
                "new_ids": sorted(ranked[:added]),
            }
            added_total += added
        selected = [iid for info in per_stratum.values() for iid in info["new_ids"]]
        c.require(not (set(selected) & (initial | bset)),
                  f"expansion overlap with initial sample/boundary for {book}/{item_type}")
        expansions.setdefault(book, {})[item_type] = per_stratum
        totals.setdefault(book, {})[item_type] = added_total
    return {
        "schema_version": "1.0",
        "kind": "expansion_manifest_v1",
        "algorithm_version": SAMPLING_ALGO_VERSION,
        "test_only": bool(source_desc.get("test_only")),
        "data_source": source_desc,
        "round": round_no,
        "sample_manifest_sha256": sm_sha,
        "decision_report_sha256": report_sha,
        "expanded_pairs": pending,
        "generator": generator_identity(),
        "expansions": expansions,
        "totals": totals,
    }


def validate_expansion_manifest(expansion, sample_manifest, chapter_manifest,
                                source, source_desc, sm_sha, expected_test_only,
                                report, report_sha):
    """F19/P0: fully validate an expansion_manifest_v1 and PROVE it was
    authorized by a producing decision report.

    The producing report is MANDATORY: an expansion without a verified
    EXPAND verdict from the state machine is rejected even if its internal
    fields are self-consistent (this blocks `build_expansion_manifest()`
    crafted for an arbitrary unauthorized pair). Checks:
      - report is a decision_report_v1 for the same mode, binds THIS sample
        manifest by raw SHA, and has verdict == "EXPAND";
      - expansion binds the report by raw SHA (report_sha);
      - expansion.expanded_pairs == report.pending_expands exactly, and
        round == 1 + len(report.expansion_manifests_sha256);
      - report's primary/second/arbitration and any prior expansion SHAs
        bind the same artifacts the caller passed (provenance chain);
      - the expansion body itself is reconstructed via
        build_expansion_manifest and compared byte-for-byte.
    report_sha is the raw on-disk SHA of the report file the caller holds.
    """
    c.require(isinstance(report, dict),
              "expansion manifest: producing decision report is required (no report -> no authorization)")
    c.require(report.get("kind") == "decision_report_v1",
              "expansion manifest: producing decision report has wrong kind")
    c.require(isinstance(report.get("test_only"), bool),
              "expansion manifest: producing decision report test_only missing")
    c.require(report.get("test_only") is expected_test_only,
              "expansion manifest: producing decision report cross-mode rejected")
    c.require(report.get("sample_manifest_sha256") == sm_sha,
              "expansion manifest: producing decision report does not bind this sample manifest")
    c.require(report.get("verdict") == "EXPAND",
              f"expansion manifest: producing decision report verdict is "
              f"{report.get('verdict')!r}, not EXPAND; expansion only follows "
              f"an EXPAND verdict")
    c.require(report.get("decision_report_sha256") is None,
              "expansion manifest: producing report must not itself reference a decision report")

    c.require(isinstance(expansion, dict), "expansion manifest: not an object")
    test_only = expansion.get("test_only")
    c.require(isinstance(test_only, bool), "expansion manifest: test_only missing/not bool")
    c.require(test_only is expected_test_only,
              "expansion manifest: cross-mode test_only rejected")
    c.require(expansion.get("kind") == "expansion_manifest_v1",
              "expansion manifest: wrong kind")
    c.require(expansion.get("algorithm_version") == SAMPLING_ALGO_VERSION,
              "expansion manifest: algorithm_version mismatch")
    c.require(expansion.get("sample_manifest_sha256") == sm_sha,
              "expansion manifest: does not bind the current sample manifest")
    c.require(expansion.get("decision_report_sha256") == report_sha,
              "expansion manifest: does not bind the producing decision report (raw SHA)")
    pairs = expansion.get("expanded_pairs") or []
    c.require(isinstance(pairs, list) and pairs
              and all(isinstance(p, dict) and {"book", "type"} <= set(p)
                      for p in pairs),
              "expansion manifest: expanded_pairs invalid")
    c.require(pairs == (report.get("pending_expands") or []),
              "expansion manifest: expanded_pairs != decision report pending_expands "
              "(pair not authorized by the state machine)")
    round_no = expansion.get("round")
    c.require(isinstance(round_no, int) and round_no >= 1,
              "expansion manifest: round missing/invalid")
    prior = report.get("expansion_manifests_sha256") or []
    c.require(round_no == 1 + len(prior),
              "expansion manifest: round does not follow the producing decision report")
    expected = build_expansion_manifest(sample_manifest, pairs, round_no,
                                        chapter_manifest, source, source_desc,
                                        sm_sha, report_sha)
    c.require(c.serialize_json(expansion) == c.serialize_json(expected),
              "expansion manifest: does not match the manifest reconstructed "
              "from the current sample manifest/chapter manifest/source "
              "(new ids, added, k, population, totals, data_source, or "
              "generator identity differ)")


def cmd_expand(argv):
    flags, _ = c.parse_flags(argv, allowed=EXPAND_FLAGS)
    sm_path = c.flag1(flags, "sample-manifest")
    report_path = c.flag1(flags, "decision-report")
    chman_path = c.flag1(flags, "chapter-manifest")
    primary_path = c.flag1(flags, "primary")
    out_dir = Path(c.flag1(flags, "out"))
    second_path = c.flag_opt(flags, "second")
    arbitration_path = c.flag_opt(flags, "arbitration")
    # F18/F19: verify frozen inputs FIRST, then validate input manifests.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    validate_sample_manifest(sample_manifest, chapter_manifest, source,
                             source_desc, chman_sha, expected_test_only=is_fake)
    # P0: the producing report is verified via the SAME shared
    # verify_producing_report the consumers use (F22 gate + RAW on-disk byte
    # equality against the recomputed verdict), so cmd_expand and cmd_decide /
    # packet / next-round decide are byte-for-byte the same code path.
    import classic_acceptance_review as review
    # P0-3: reuse the (report, report_sha) pinned to ONE raw read; do NOT
    # re-read the report path for its SHA.
    report, report_sha = review.verify_producing_report(
        report_path, sample_manifest, sm_sha,
        chapter_manifest, source, source_desc, is_fake,
        primary_path, second_path, arbitration_path)
    pending = report["pending_expands"]
    manifest = build_expansion_manifest(sample_manifest, pending, 1,
                                        chapter_manifest, source, source_desc,
                                        sm_sha, report_sha)
    # F19: self-validate the produced manifest against the (recomputed and
    # verified) producing decision report.
    validate_expansion_manifest(manifest, sample_manifest, chapter_manifest,
                                source, source_desc, sm_sha,
                                expected_test_only=is_fake,
                                report=report, report_sha=report_sha)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = c.serialize_json(manifest)
    path = out_dir / "expansion_manifest_v1.json"
    path.write_bytes(payload)
    print("expansion manifest:", path)
    print("sha256:", c.sha256_bytes(payload), "totals:", manifest["totals"],
          "test_only:", manifest["test_only"])
```

dispatch 替换为：

```python
        if cmd == "sample":
            cmd_sample(argv[1:])
        elif cmd == "expand":
            cmd_expand(argv[1:])
        else:
            raise RuntimeError(f"unknown subcommand: {cmd!r} (expected sample|expand)")
```

- [ ] **Step 3b: 替换 `cmd_validate_primary` 接入 expansion 授权链（F19，无 TOCTOU）**

Task 4 落地的无 expansion 版 `cmd_validate_primary` / `VALIDATE_PRIMARY_FLAGS` 现在用下面的版本整体替换（dispatch 入口已在 Task 4 注册）。关键：report 与 expansion 各自的**磁盘原始字节只读取一次**，SHA、JSON 解析、内容验证都基于这同一份已固定的字节/对象向后传递——`verify_producing_report()` 返回的已验证 report 对象被直接复用，不重新 `load_json_file` 报告路径；expansion 字节读出后立即算 SHA 并解析，`validate_expansion_manifest` 与 primary 绑定都用该 SHA，杜绝验证后替换文件的 TOCTOU 窗口。

```python
VALIDATE_PRIMARY_FLAGS = {
    "primary", "sample-manifest", "chapter-manifest",
    "candidate-commit", "data-root",
    "expansion-manifest", "decision-report",
    "producing-primary", "producing-second", "producing-arbitration",
}


def cmd_validate_primary(argv):
    # F18/F19: frozen/fake source lock first, then the SAME producing-evidence
    # authorization chain decide/finalize use. validate-primary is not a
    # trusted "is this JSON self-consistent" linter; an expansion can only
    # extend coverage if its producing EXPAND report is recomputed from the R1
    # receipts and its body is rebuilt against that report. At most one
    # expansion is allowed (only one parallel expansion round exists).
    flags, _ = c.parse_flags(argv, allowed=VALIDATE_PRIMARY_FLAGS)
    primary_path = c.flag1(flags, "primary")
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    expansion_path = c.flag_opt(flags, "expansion-manifest")
    producing_report_path = c.flag_opt(flags, "decision-report")
    pp_path = c.flag_opt(flags, "producing-primary")
    ps_path = c.flag_opt(flags, "producing-second")
    pa_path = c.flag_opt(flags, "producing-arbitration")
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    check_producing_evidence_presence(
        bool(expansion_path), producing_report_path, pp_path, ps_path, pa_path,
        "validate-primary")
    expansions = []
    expansion_shas = []
    if expansion_path:
        # P0-2/TOCTOU: read each artifact's raw bytes ONCE; pin the SHA and
        # parsed object from that same read. verify_producing_report returns
        # the verified report object (it itself compares on-disk bytes against
        # the recomputed verdict internally), and we reuse it rather than re-
        # reading the report path after validation.
        report, report_sha = verify_producing_report(
            producing_report_path, sample_manifest, sm_sha,
            chapter_manifest, source, source_desc, is_fake,
            pp_path, ps_path, pa_path)
        em_bytes = Path(expansion_path).read_bytes()
        em_sha = c.sha256_bytes(em_bytes)
        em = json.loads(em_bytes.decode("utf-8"))
        sampling.validate_expansion_manifest(
            em, sample_manifest, chapter_manifest, source, source_desc,
            sm_sha, expected_test_only=is_fake,
            report=report, report_sha=report_sha)
        expansions = [em]
        expansion_shas = [em_sha]
    primary = load_json_file(primary_path)
    validate_primary(primary, sample_manifest, expansions,
                     sm_sha, expansion_shas, chapter_manifest)
    print("primary review package OK:", primary_path)
```

- [ ] **Step 3b: 回补 `packet` 的扩样路径与 flags**

Task 3 把 `packet` 收窄为基础 flags 并禁用了扩样分支（前向依赖）。此处把 Task 6 的
`verify_producing_report` / `check_producing_evidence_presence` 与 Task 7 的
`sampling.validate_expansion_manifest` 接回 `cmd_packet`，整体替换为：

```python
PACKET_FLAGS = {"sample-manifest", "chapter-manifest", "out",
                "candidate-commit", "data-root",
                "expansion-manifest", "decision-report",
                "producing-primary", "producing-second", "producing-arbitration"}


def cmd_packet(argv):
    flags, _ = c.parse_flags(argv, allowed=PACKET_FLAGS)
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    expansion_path = c.flag_opt(flags, "expansion-manifest")
    producing_report_path = c.flag_opt(flags, "decision-report")
    pp_path = c.flag_opt(flags, "producing-primary")
    ps_path = c.flag_opt(flags, "producing-second")
    pa_path = c.flag_opt(flags, "producing-arbitration")
    # F18/F19: frozen lock first, then full manifest validation before any read.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    check_producing_evidence_presence(
        bool(expansion_path), producing_report_path, pp_path, ps_path, pa_path, "packet")
    expansions = []
    expansion_shas = []
    if expansion_path:
        # P0-3: verify_producing_report reads the R1 report ONCE and returns
        # (report, report_sha); BOTH are reused here, never re-read.
        # P0: read the expansion ONCE too -- object and pinned SHA come from
        # the same bytes and are reused for the packet binding below.
        em_bytes = Path(expansion_path).read_bytes()
        em_sha = c.sha256_bytes(em_bytes)
        em = json.loads(em_bytes.decode("utf-8"))
        rep, rep_sha = verify_producing_report(
            producing_report_path, sample_manifest, sm_sha,
            chapter_manifest, source, source_desc, is_fake,
            pp_path, ps_path, pa_path)
        sampling.validate_expansion_manifest(
            em, sample_manifest, chapter_manifest, source, source_desc,
            sm_sha, expected_test_only=is_fake,
            report=rep, report_sha=rep_sha)
        expansions = [em]
        expansion_shas = [em_sha]
    # F20: packet binds sample/expansion manifests by RAW on-disk byte SHA.
    packet = build_packet(sample_manifest, expansions, chapter_manifest, source,
                          sm_sha, expansion_shas, source_desc)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review_packet_v1.json").write_bytes(c.serialize_json(packet))
    print("review packet:", out_dir / "review_packet_v1.json")
    print("items:", len(packet["items"]), "chapters:", len(packet["chapters"]),
          "test_only:", packet["test_only"])
```

至此 `packet` 恢复到设计中的完整样式。

- [ ] **Step 3c: 回补 `decide` 的扩样路径与 flags**

Task 6 把 `decide` 收窄为单轮非扩样。此处整体替换 `DECIDE_FLAGS` 与 `cmd_decide`，
接入 producing-evidence 授权链（`verify_producing_report` 返回 `(report, report_sha)`，
供 `validate_expansion_manifest` 直接复用，不再重读 report 路径）：

```python
DECIDE_FLAGS = {"primary", "sample-manifest", "chapter-manifest", "out",
                "candidate-commit", "data-root",
                "second", "arbitration",
                "expansion-manifest", "decision-report",
                "producing-primary", "producing-second", "producing-arbitration"}


def cmd_decide(argv):
    flags, _ = c.parse_flags(argv, allowed=DECIDE_FLAGS)
    primary_path = c.flag1(flags, "primary")
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    expansion_path = c.flag_opt(flags, "expansion-manifest")
    producing_report_path = c.flag_opt(flags, "decision-report")
    second_path = c.flag_opt(flags, "second")
    arbitration_path = c.flag_opt(flags, "arbitration")
    pp_path = c.flag_opt(flags, "producing-primary")
    ps_path = c.flag_opt(flags, "producing-second")
    pa_path = c.flag_opt(flags, "producing-arbitration")
    # F18/F19: frozen lock first, then full manifest validation before any read.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    check_producing_evidence_presence(
        bool(expansion_path), producing_report_path, pp_path, ps_path, pa_path, "decide")
    expansions = []
    expansion_shas = []
    if expansion_path:
        # P0-3: verify_producing_report reads the R1 report ONCE and returns
        # (report, report_sha); BOTH are reused here, never re-read.
        # P0: read the expansion ONCE too -- object and pinned SHA come from
        # the same bytes and are passed to validate_decision_inputs.
        em_bytes = Path(expansion_path).read_bytes()
        em_sha = c.sha256_bytes(em_bytes)
        em = json.loads(em_bytes.decode("utf-8"))
        rep, rep_sha = verify_producing_report(
            producing_report_path, sample_manifest, sm_sha,
            chapter_manifest, source, source_desc, is_fake,
            pp_path, ps_path, pa_path)
        sampling.validate_expansion_manifest(
            em, sample_manifest, chapter_manifest, source, source_desc,
            sm_sha, expected_test_only=is_fake,
            report=rep, report_sha=rep_sha)
        expansions = [em]
        expansion_shas = [em_sha]
    # F22 receipt gate + primary/second/arbitration validation + verdict
    # computation are all in the shared helper (same path as `expand`).
    _primary, _second, _arbitration, report = validate_decision_inputs(
        sample_manifest, expansions, chapter_manifest, source, source_desc,
        sm_sha, expansion_shas, is_fake, primary_path, second_path,
        arbitration_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decision_report_v1.json").write_bytes(c.serialize_json(report))
    print("verdict:", report["verdict"], "| fired:", report["fired_rules"],
          "| pending_expands:", report["pending_expands"],
          "| test_only:", report["test_only"])
```

至此 `decide` 恢复到设计中的完整样式。

- [ ] **Step 3d: 两个消费端扩样路径单读测试（packet / decide）**

P0（TOCTOU）收尾：对 `packet` / `decide` 各加一条读次数/替换负向测试，证明
expansion 路径在每个命令中只被读取一次。finalize 的单读测试属于 Task 8
（`cmd_finalize` 在 Task 8 才实现，不能提前到 Task 7，否则 Task 7 无法独立 GREEN）。

证据链不能用 8 条规则的 tiny 数据集：非 sanmingtonghui 书全部落在 stratum 1，
`K_MIN=5` 使 mcq 抽样恒为 5，1 个 critical = 20% > 5%（REJECT）；rule 的 stratum
cascade 阈值是 8%，1/5 = 20% 同样 REJECT。因此构造一个 700 条 qiongtongbaojian
rule 的 fake 数据集：`compute_k(700,3)=21`，1 个 critical = 1/21 = 4.76%，落在
EXPAND 带 `(2%, 5%]` 且低于 8% cascade。helper 真实跑 `decide`(R1)→`expand`→构造
R2 all-pass primary，并断言 R1 verdict==EXPAND（若阈值/抽样漂移，测试在准备阶段就
fail，而不是静默测错路径）。

```python
def _expand_evidence_chain(arbitrate=False):
    # Build a self-contained fake dataset with a large qiongtongbaojian rule
    # universe so the R1 state machine lands in the EXPAND band. Runs the
    # REAL decide (R1) + expand CLIs in-process, then builds an all-pass R2
    # primary over sample+expansion ids. When arbitrate=True the R1 second
    # review DISAGREES and an arbitration receipt adjudicates (keeping the
    # critical), exercising the arbitration branch. Returns every path the
    # single-read consumer tests need.
    base = fixtures.tmp_dir("acceptance_expand_chain")
    data, chman_path = fixtures.build_tiny_dataset(base)
    # widen qiongtongbaojian rule universe to 700: compute_k(700,3)=21, and
    # 1 critical / 21 reviewed = 4.76% -> EXPAND (below 8% stratum cascade,
    # above 2% EXPAND_LOW, <= 5% REJECT). Do NOT overwrite all_rules.json
    # (that orphans the MCQ source_rule_id foreign keys); append new qx ids.
    qdir = data / "knowledge_base" / "classic_texts" / "qiongtongbaojian"
    existing_rules = fixtures.read_json(qdir / "all_rules.json")
    extra_rules = [{"id": f"qx{i:03d}", "category": "测试", "subject": "测试",
                    "condition": "测试", "rule": f"qx规则{i}。",
                    "original_text": f"qx原文{i}", "source_book": "qiongtongbaojian",
                    "source_chapter": f"一、qiongtong节{i}"} for i in range(700)]
    fixtures.write_json(qdir / "all_rules.json", existing_rules + extra_rules)
    man, chman_sha = sampling.load_chapter_manifest(chman_path)
    source = c.DirSource(data)
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))

    def item(book, item_type, iid, verdict="PASS", findings=None):
        sc = int(iid.split("_")[1]) if book == "sanmingtonghui" else 1
        return {"item": {"book": book, "type": item_type, "id": iid,
                         "source_chapter": sc},
                "verdict": verdict, "findings": findings or []}

    # R1 primary: exactly one critical FAIL on a qiongtongbaojian rule.
    crit_id = sorted(sm["samples"]["qiongtongbaojian"]["rule"]["1"])[0]
    r1_items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    if (book, item_type, iid) == ("qiongtongbaojian", "rule", crit_id):
                        r1_items.append(item(book, item_type, iid, "FAIL",
                                             [fixtures.critical()]))
                    else:
                        r1_items.append(item(book, item_type, iid))
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            r1_items.append(item("sanmingtonghui", item_type, iid))
    r1_primary = {"schema_version": "1.0", "kind": "primary_review_package",
                  "sample_manifest_sha256": c.sha256_file_raw(sm_path),
                  "expansion_manifests_sha256": [],
                  "overall_stats": {}, "zero_output_report": [],
                  "reviewer_list": ["reviewer-1"], "items": r1_items}
    r1_p_path = base / "r1_primary.json"
    fixtures.write_json(r1_p_path, r1_primary)

    # second review: agrees (no arbitration) or disagrees (arbitrate=True).
    second = {"schema_version": "1.0", "kind": "second_review_receipt_v1",
              "primary_sha256": c.sha256_file_raw(r1_p_path),
              "reviewer": "reviewer-2", "reviewed_at": "2026-08-23T00:00:00+08:00",
              "entries": [{"book": "qiongtongbaojian", "type": "rule",
                           "id": crit_id, "finding_index": 0,
                           "agree": not arbitrate,
                           "evidence_text": "e", "reviewer": "reviewer-2",
                           "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
    r1_s_path = base / "r1_second.json"
    fixtures.write_json(r1_s_path, second)

    # arbitration receipt only when the second review disagrees (F22).
    r1_a_path = None
    if arbitrate:
        arbitration = {"schema_version": "1.0", "kind": "arbitration_receipt_v1",
                       "primary_sha256": c.sha256_file_raw(r1_p_path),
                       "second_review_sha256": c.sha256_file_raw(r1_s_path),
                       "reviewer_second": "reviewer-2", "arbitrator": "reviewer-3",
                       "reviewed_at": "2026-08-23T00:00:00+08:00",
                       "entries": [{"book": "qiongtongbaojian", "type": "rule",
                                    "id": crit_id, "finding_index": 0,
                                    "reviewer_first": "reviewer-1",
                                    "decision": "critical", "reasoning": "why",
                                    "arbitrator": "reviewer-3",
                                    "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
        r1_a_path = base / "r1_arbitration.json"
        fixtures.write_json(r1_a_path, arbitration)

    # produce the R1 EXPAND report through the REAL decide code path.
    _, _, _, r1_report = review.validate_decision_inputs(
        sm, [], man, source, desc, fixtures.sha256_file(sm_path), [], True,
        r1_p_path, r1_s_path, r1_a_path)
    assert r1_report["verdict"] == "EXPAND", \
        f"fixture drift: R1 verdict is {r1_report['verdict']!r}, not EXPAND"
    assert r1_report["pending_expands"] == [{"book": "qiongtongbaojian", "type": "rule"}]
    r1_report_path = base / "r1_report.json"
    fixtures.write_json(r1_report_path, r1_report)

    # produce the expansion manifest through the REAL expand CLI.
    expand_args = [
        "--sample-manifest", str(sm_path), "--decision-report", str(r1_report_path),
        "--primary", str(r1_p_path), "--second", str(r1_s_path),
        "--chapter-manifest", str(chman_path), "--data-root", str(data),
        "--out", str(base / "exp")]
    if arbitrate:
        expand_args += ["--arbitration", str(r1_a_path)]
    review.sampling.cmd_expand(expand_args)
    exp_path = base / "exp" / "expansion_manifest_v1.json"
    em = fixtures.read_json(exp_path)

    # R2 primary: all-pass over sample ids + expansion new ids, binds em_sha.
    em_sha = c.sha256_bytes(exp_path.read_bytes())
    r2_items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    r2_items.append(item(book, item_type, iid))
    for item_type, strata in em["expansions"]["qiongtongbaojian"].items():
        for info in strata.values():
            for iid in info["new_ids"]:
                r2_items.append(item("qiongtongbaojian", item_type, iid))
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            r2_items.append(item("sanmingtonghui", item_type, iid))
    r2_primary = {"schema_version": "1.0", "kind": "primary_review_package",
                  "sample_manifest_sha256": c.sha256_file_raw(sm_path),
                  "expansion_manifests_sha256": [em_sha],
                  "overall_stats": {}, "zero_output_report": [],
                  "reviewer_list": ["reviewer-1"], "items": r2_items}
    r2_p_path = base / "r2_primary.json"
    fixtures.write_json(r2_p_path, r2_primary)

    return {"base": base, "data": data, "chman_path": chman_path, "man": man,
            "source": source, "desc": desc, "sm": sm, "sm_path": sm_path,
            "r1_p_path": r1_p_path, "r1_s_path": r1_s_path,
            "r1_a_path": r1_a_path,
            "r1_report_path": r1_report_path, "exp_path": exp_path, "em": em,
            "em_sha": em_sha, "r2_p_path": r2_p_path}


def _expansion_read_sentinel(monkeypatch, exp_path):
    # Count reads of exp_path; a SECOND read returns swapped bytes so any
    # double-read / SHA recompute fails closed (TOCTOU). Other paths read
    # normally.
    reads = []
    orig = Path.read_bytes

    def sentinel(self, *a, **k):
        if str(self) == str(exp_path):
            reads.append(1)
            if len(reads) >= 2:
                return b'{"kind": "swapped"}'
        return orig(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", sentinel)
    return reads


def test_packet_expansion_reads_manifest_once(monkeypatch):
    chain = _expand_evidence_chain()
    try:
        out = chain["base"] / "pkg"
        reads = _expansion_read_sentinel(monkeypatch, chain["exp_path"])
        review.cmd_packet([
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"])])
        assert reads == [1]
        packet = fixtures.read_json(out / "review_packet_v1.json")
        # em_sha is pinned by the helper BEFORE the sentinel exists; reading
        # exp_path here would itself be the second read (returns swapped).
        assert packet["expansion_manifests_sha256"] == [chain["em_sha"]]
    finally:
        fixtures.rmtree_force(chain["base"])


def test_decide_expansion_reads_manifest_once(monkeypatch):
    chain = _expand_evidence_chain()
    try:
        out = chain["base"] / "dec"
        reads = _expansion_read_sentinel(monkeypatch, chain["exp_path"])
        review.cmd_decide([
            "--primary", str(chain["r2_p_path"]),
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"])])
        assert reads == [1]
        report = fixtures.read_json(out / "decision_report_v1.json")
        assert report["expansion_manifests_sha256"] == [chain["em_sha"]]
        # R2 is all-pass over sample+expansion -> terminal ACCEPT
        assert report["verdict"] == "ACCEPT"
    finally:
        fixtures.rmtree_force(chain["base"])


def _multi_read_sentinel(monkeypatch, paths):
    # Count reads of each tracked path; a SECOND read of any tracked path
    # returns swapped bytes so a double-read / SHA recompute fails closed
    # (TOCTOU). Other paths read normally.
    reads = {p: [] for p in paths}
    orig = Path.read_bytes

    def sentinel(self, *a, **k):
        key = str(self)
        if key in reads:
            reads[key].append(1)
            if len(reads[key]) >= 2:
                return b'{"kind": "swapped"}'
        return orig(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", sentinel)
    return reads


def test_producing_evidence_chain_reads_each_artifact_once(monkeypatch):
    # P0 (TOCTOU): every artifact in the producing-evidence chain is read
    # exactly ONCE (sample, producing primary, producing second, producing
    # report, expansion). A second read of any tracked path returns swapped
    # bytes, so a double-read / SHA recompute fails closed.
    chain = _expand_evidence_chain()
    try:
        out = chain["base"] / "pkg"
        tracked = [str(chain["sm_path"]), str(chain["r1_p_path"]),
                   str(chain["r1_s_path"]), str(chain["r1_report_path"]),
                   str(chain["exp_path"])]
        reads = _multi_read_sentinel(monkeypatch, tracked)
        review.cmd_packet([
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"])])
        for p in tracked:
            assert reads[p] == [1], f"{p} read {len(reads[p])} times, expected once"
    finally:
        fixtures.rmtree_force(chain["base"])


def test_producing_evidence_chain_arbitration_reads_once(monkeypatch):
    # P0 (TOCTOU), arbitration branch: with a disagreeing second review the
    # producing chain reads the arbitration receipt ONCE too.
    chain = _expand_evidence_chain(arbitrate=True)
    try:
        out = chain["base"] / "pkg"
        tracked = [str(chain["sm_path"]), str(chain["r1_p_path"]),
                   str(chain["r1_s_path"]), str(chain["r1_a_path"]),
                   str(chain["r1_report_path"]), str(chain["exp_path"])]
        reads = _multi_read_sentinel(monkeypatch, tracked)
        review.cmd_packet([
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"]),
            "--producing-arbitration", str(chain["r1_a_path"])])
        for p in tracked:
            assert reads[p] == [1], f"{p} read {len(reads[p])} times, expected once"
    finally:
        fixtures.rmtree_force(chain["base"])
```

- [ ] **Step 3e: 移除 Task 3/6 过时的负向测试**

Task 3 / Task 6 曾加入 `test_packet_cli_rejects_expansion_flags` 与
`test_decide_cli_rejects_expansion_flags`（断言扩样 flags 被当作 unknown flag 拒绝）。
本任务已把扩样 flags 接回 packet/decide，这两条断言不再成立，必须删除（扩样 flags 的
防误用已由 `check_producing_evidence_presence` 的孤儿证据门 + validate-primary 的三个
CLI gate 测试承接）。从 `tests/test_classic_acceptance_review.py` 中删除这两个
`@pytest.mark.parametrize` 测试函数。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_sampling.py tests/test_classic_acceptance_review.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add scripts/classic_acceptance_sampling.py scripts/classic_acceptance_review.py \
        tests/test_classic_acceptance_sampling.py tests/test_classic_acceptance_review.py
git commit -m "feat(acceptance): per-stratum expansion round; validate-primary expansion authz"
```

---

### Task 8: final acceptance package（`finalize`，含回执闭环 F17 + test_only 拒绝）

**Files:**
- Modify: `scripts/classic_acceptance_review.py`（追加）
- Modify: `scripts/classic_acceptance_common.py`（追加原子发布原语 `publish_new_file`）
- Modify: `scripts/classic_acceptance_review.py`（追加 finalize + 接入原子发布）
- Test: `tests/test_classic_acceptance_review.py`（追加；文件顶部 imports 增加 `import threading`）

- [ ] **Step 1: 写失败测试**

向 `tests/test_classic_acceptance_review.py` 追加：

```python
def test_check_finalize_terminal_verdict():
    report = {"kind": "decision_report_v1", "verdict": "EXPAND",
              "primary_sha256": "0" * 64, "sample_manifest_sha256": "1" * 64,
              "second_review_sha256": None, "arbitration_sha256": None,
              "expansion_manifests_sha256": []}
    with pytest.raises(RuntimeError, match="terminal verdict"):
        review.check_finalize(report)


# NOTE: the tiny all-PASS primary builder `_tiny_all_pass_primary(sm)` (added in
# Task 4) is reused by the fake-mode finalize tests below; it is identical for
# this purpose, so no second helper is defined here.


def test_finalize_build_package_pure():
    # P0-1: finalize must refuse fake products, so the happy-path packaging is
    # covered by the pure assembler build_final_package() (no frozen chain, no
    # fake-refusal gate involved) plus a production CLI test below.
    # P0: use a NON-EMPTY expansion SHA so the test proves the pinned em_sha
    # actually flows into the final package (an empty list would trivially
    # pass even if build_final_package dropped the expansion binding).
    exp_sha = "d" * 64
    report = {"kind": "decision_report_v1", "verdict": "ACCEPT",
              "primary_sha256": "a" * 64, "sample_manifest_sha256": "b" * 64,
              "second_review_sha256": None, "arbitration_sha256": None,
              "expansion_manifests_sha256": [exp_sha]}
    primary = {"reviewer_list": ["reviewer-1"]}
    # P0: file identity must be the REAL consumed basenames (here deliberately
    # non-canonical/versioned), not hardcoded canonical names.
    artifact_files = {
        "decision_report": "decision_report_round2_v2.json",
        "primary_review": "primary_review_2026-08-25.json",
        "sample_manifest": "sample_manifest_v3.json",
    }
    package = review.build_final_package(
        report, primary, "c" * 64, [exp_sha], artifact_files,
        exp_files=["expansion_round1.json"], today=datetime.date(2026, 8, 25))
    assert package["kind"] == "final_acceptance_package_v1"
    assert package["final_verdict"] == "ACCEPT"
    assert package["decision_report_sha256"] == "c" * 64
    assert package["primary_sha256"] == "a" * 64
    assert package["sample_manifest_sha256"] == "b" * 64
    assert package["second_review_sha256"] is None
    assert package["arbitration_sha256"] is None
    assert package["expansion_manifests_sha256"] == [exp_sha]
    assert package["reviewer_list"] == ["reviewer-1"]
    assert package["generated_at"] == "2026-08-25"
    # design section 8: explicit per-artifact identity = the REAL consumed
    # (non-canonical, versioned) basename + its content SHA.
    arts = {a["role"]: a for a in package["artifacts"]}
    assert len(package["artifacts"]) == 4
    assert arts["decision_report"] == {
        "role": "decision_report", "file": "decision_report_round2_v2.json",
        "sha256": "c" * 64}
    assert arts["primary_review"]["file"] == "primary_review_2026-08-25.json"
    assert arts["primary_review"]["sha256"] == "a" * 64
    assert arts["sample_manifest"]["file"] == "sample_manifest_v3.json"
    assert arts["sample_manifest"]["sha256"] == "b" * 64
    assert arts["expansion_manifest"]["sha256"] == exp_sha
    assert arts["expansion_manifest"]["file"] == "expansion_round1.json"
    # optional receipts absent -> not listed (F22: only consumed versions sealed)
    assert "second_review" not in arts
    assert "arbitration" not in arts


def test_finalize_package_requires_consumed_file_identity():
    # The assembler must NOT fabricate a filename: a missing consumed-file
    # identity fails closed instead of defaulting to a canonical name.
    exp_sha = "d" * 64
    report = {"kind": "decision_report_v1", "verdict": "ACCEPT",
              "primary_sha256": "a" * 64, "sample_manifest_sha256": "b" * 64,
              "second_review_sha256": None, "arbitration_sha256": None,
              "expansion_manifests_sha256": [exp_sha]}
    with pytest.raises(RuntimeError, match="missing consumed-file identity"):
        review.build_final_package(report, {"reviewer_list": ["r"]}, "c" * 64,
                                   [exp_sha], {"decision_report": "r.json",
                                               "primary_review": "p.json"})
    with pytest.raises(RuntimeError, match="missing consumed-file identity for expansion"):
        review.build_final_package(report, {"reviewer_list": ["r"]}, "c" * 64,
                                   [exp_sha], {"decision_report": "r.json",
                                               "primary_review": "p.json",
                                               "sample_manifest": "s.json"})


def _production_primary(real_packet):
    packet, sm = real_packet
    items = []
    for e in packet["items"]:
        entry = _primary_entry(e["book"], e["type"], e["id"])
        # P0: keep the REAL source_chapter from the packet (design section 8.1
        # schema); _primary_entry defaults to 1, which would silently move
        # every sanmingtonghui item to chapter 1 and break the per-entry
        # chapter identity / evidence traceability (boundary/stratum metrics
        # themselves come from the frozen sample/chapter metadata, not this
        # field, but the forged ownership must not validate).
        entry["item"]["source_chapter"] = e.get("source_chapter")
        items.append(entry)
    primary = _mini_primary()
    primary["items"] = items
    primary["zero_output_report"] = packet["integrity"]["zero_output_chapters"]
    return primary, sm


def _production_inputs(real_packet, tmp_path, run_name):
    """Build a real all-PASS primary + sample manifest in `tmp_path/run_name`.
    Returns (run_dir, p_path, sm_path, primary, man, source, git_desc) wired
    to the REAL frozen data (production mode, test_only=False). The primary
    keeps the REAL per-item source_chapter (design section 8.1) so it
    cross-validates."""
    primary, sm = _production_primary(real_packet)
    run = tmp_path / run_name
    run.mkdir(parents=True, exist_ok=True)
    sm_path = run / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = run / "primary_ok.json"
    fixtures.write_json(p_path, primary)
    man, _chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    git_desc = {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False}
    return run, p_path, sm_path, primary, man, source, git_desc


def _decide_production_inprocess(p_path, sm_path, out_dir, man, source, git_desc):
    """P0 (CI per-test 120s gate): produce the production decision report by
    calling the SAME validation/compute path `cmd_decide` runs, but IN PROCESS.
    Only the CLI entry point `build_source` spawns the ~73s frozen-input lock
    subprocess; calling validate_decision_inputs directly over a real GitSource
    still validates against the REAL frozen data (and enforces F18 reads from
    the pinned commit) without that second freeze-chain run. This keeps each
    production test to AT MOST ONE freeze-chain subprocess (a real `finalize`).
    Writes decision_report_v1.json into out_dir and returns (report, report_path)."""
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      git_desc, chman_sha, expected_test_only=False)
    _, _, _, report = review.validate_decision_inputs(
        sample_manifest, [], chapter_manifest, source, git_desc, sm_sha, [], False,
        p_path, None, None)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "decision_report_v1.json"
    report_path.write_bytes(c.serialize_json(report))
    return report, report_path


def test_finalize_production_happy_path(tmp_path, real_packet):
    # P0-1: the real finalize positive path runs against the REAL frozen data
    # (production mode, test_only=False). The ACCEPT decision report is
    # produced IN PROCESS (same compute path as `decide`, no extra freeze-chain
    # subprocess); exactly ONE production `finalize` subprocess assembles the
    # package, so this test stays under the CI per-test 120s gate while still
    # exercising the real CLI finalize + F17/F22 receipt gate + artifacts.
    run, p_path, sm_path, _primary, man, source, git_desc = _production_inputs(
        real_packet, tmp_path, "prod_happy")
    report, report_path = _decide_production_inprocess(
        p_path, sm_path, run, man, source, git_desc)
    assert report["verdict"] == "ACCEPT"
    assert report["test_only"] is False
    out = tmp_path / "prod_out"
    fixtures.run_cli("classic_acceptance_review.py", "finalize",
                     "--decision-report", str(report_path), "--primary", str(p_path),
                     "--sample-manifest", str(sm_path),
                     "--chapter-manifest", fixtures.CHAPTER_MANIFEST,
                     "--candidate-commit", fixtures.COMMIT, "--out", str(out))
    final = fixtures.read_json(out / "final_acceptance_package_v1.json")
    assert final["final_verdict"] == "ACCEPT"
    assert final["primary_sha256"] == fixtures.sha256_file(p_path)
    assert final["decision_report_sha256"] == fixtures.sha256_file(report_path)
    assert final["sample_manifest_sha256"] == fixtures.sha256_file(sm_path)
    assert final["second_review_sha256"] is None
    assert final["arbitration_sha256"] is None
    assert final["reviewer_list"] == ["reviewer-1"]
    prod_arts = {a["role"]: a for a in final["artifacts"]}
    # file identity = basename of the file ACTUALLY consumed (the primary was
    # passed as primary_ok.json; the package must not claim a canonical name).
    assert prod_arts["decision_report"]["file"] == Path(report_path).name
    assert prod_arts["decision_report"]["sha256"] == fixtures.sha256_file(report_path)
    assert prod_arts["primary_review"]["file"] == Path(p_path).name == "primary_ok.json"
    assert prod_arts["primary_review"]["sha256"] == fixtures.sha256_file(p_path)
    assert prod_arts["sample_manifest"]["file"] == Path(sm_path).name
    assert prod_arts["sample_manifest"]["sha256"] == fixtures.sha256_file(sm_path)
    assert "second_review" not in prod_arts
    assert "arbitration" not in prod_arts


def test_finalize_production_rejects_stray_second(tmp_path, real_packet):
    # F17/F22: a receipt that the state machine does not require (a second
    # review over a no-critical-findings primary) is rejected by the finalize
    # gate even in production. Exactly ONE production finalize subprocess
    # (freeze chain runs once); the report is produced in process.
    run, p_path, sm_path, _primary, man, source, git_desc = _production_inputs(
        real_packet, tmp_path, "prod_stray")
    _report, report_path = _decide_production_inprocess(
        p_path, sm_path, run, man, source, git_desc)
    other_second = run / "stray_second.json"
    fixtures.write_json(other_second, {"kind": "second_review_receipt_v1"})
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(report_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(fixtures.CHAPTER_MANIFEST),
        "--candidate-commit", fixtures.COMMIT,
        "--second", str(other_second), "--out", str(run / "finalize_stray"))
    assert not r.timed_out and r.returncode != 0
    assert "not allowed" in r.stdout + r.stderr


def test_decide_production_rejects_tampered_source_chapter(tmp_path, real_packet):
    # P0: a tampered source_chapter on a real sanmingtonghui item fails closed
    # in production decide. validate_primary receives the frozen chapter
    # manifest and cross-checks every sanmingtonghui item's source_chapter;
    # run IN PROCESS over the real GitSource so this exercises the real
    # production cross-check without a second freeze-chain subprocess.
    import copy
    run, p_path, sm_path, primary, man, source, git_desc = _production_inputs(
        real_packet, tmp_path, "prod_tamper")
    tampered = copy.deepcopy(primary)
    for entry in tampered["items"]:
        if entry["item"]["book"] == "sanmingtonghui":
            real_ch = entry["item"]["source_chapter"]
            entry["item"]["source_chapter"] = 1 if real_ch != 1 else 2
            break
    tampered_path = run / "primary_tampered.json"
    fixtures.write_json(tampered_path, tampered)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    chapter_manifest, _ = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    with pytest.raises(RuntimeError, match="source_chapter"):
        review.validate_decision_inputs(
            sample_manifest, [], chapter_manifest, source, git_desc, sm_sha, [],
            False, tampered_path, None, None)


def test_finalize_production_no_overwrite_leaves_frozen_package(tmp_path, real_packet):
    # P0 (design section 8 no-overwrite): a finalize whose target final-package
    # path already exists must fail closed and leave the already-published
    # frozen bytes untouched. A correction is published by re-running finalize
    # into a NEW --out directory (the toolchain's "_v2"); the sealed package is
    # never modified in place. The package slot is pre-seeded with a sentinel
    # so this needs only ONE production finalize subprocess (freeze chain
    # runs once); it must fail at the atomic create-if-absent publish step and
    # the sentinel bytes must survive unchanged.
    run, p_path, sm_path, _primary, man, source, git_desc = _production_inputs(
        real_packet, tmp_path, "prod_no_overwrite")
    _report, report_path = _decide_production_inprocess(
        p_path, sm_path, run, man, source, git_desc)
    out = tmp_path / "prod_no_overwrite_out"
    out.mkdir(parents=True, exist_ok=True)
    pkg_path = out / "final_acceptance_package_v1.json"
    sentinel = b'{"sentinel": "frozen-must-not-be-touched"}\n'
    pkg_path.write_bytes(sentinel)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(report_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(fixtures.CHAPTER_MANIFEST),
        "--candidate-commit", fixtures.COMMIT, "--out", str(out))
    assert not r.timed_out and r.returncode != 0
    assert "already exists" in r.stdout + r.stderr
    assert pkg_path.read_bytes() == sentinel


def test_run_cli_result_timeout_kills_whole_process_tree(tmp_path):
    # P1: a wedged CLI must be killed WITH every descendant it spawned, and the
    # bounded timeout must fire BEFORE pytest's --timeout=120 aborts the test.
    # The hang script spawns a grandchild (mirroring a CLI that itself spawns
    # the ~73s frozen-chain checker) and records BOTH pids to a file; after the
    # short timeout both pids must be gone, proving _kill_process_tree reaps the
    # whole tree rather than just the direct child.
    import time
    hang = tmp_path / "hang_cli.py"
    pid_file = tmp_path / "pids.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "if os.name == 'nt':\n"
        "    kw = dict(creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))\n"
        "    child = [sys.executable, '-c', 'import time; time.sleep(3600)']\n"
        "else:\n"
        "    # inherit the CLI's process group: the POSIX cleanup kills the\n"
        "    # whole GROUP, so a grandchild escaping into its own session\n"
        "    # would be outside the killpg contract.\n"
        "    kw = {}\n"
        "    child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")
    t0 = time.time()
    res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
    call_elapsed = time.time() - t0
    assert res.timed_out, "run_cli_result should report a timeout for the hung CLI"
    assert res.cleanup_ok is True, "real taskkill on a live tree must prove the reap"
    assert call_elapsed < 5 + fixtures.CLEANUP_TIMEOUT_SECONDS + 10, (
        f"run_cli_result returned in {call_elapsed:.1f}s after a 5s timeout; "
        f"cleanup must stay bounded to beat the 120s pytest gate")
    pids = fixtures.read_json(pid_file)
    parent_pid, child_pid = pids["parent"], pids["child"]
    # the helper reaps the whole tree before returning; a short poll only
    # covers OS scheduling jitter, not unbounded cleanup.
    deadline = time.time() + 3
    while time.time() < deadline and (fixtures._pid_alive(parent_pid)
                                      or fixtures._pid_alive(child_pid)):
        time.sleep(0.1)
    assert not fixtures._pid_alive(parent_pid), "hung CLI parent survived the timeout kill"
    assert not fixtures._pid_alive(child_pid), "hung CLI grandchild survived the process-tree kill"


def test_run_cli_result_cleanup_returns_well_before_pytest_gate(tmp_path):
    # P0: not only must the timeout fire before pytest's --timeout=120, the
    # cleanup that follows (tree-kill + output drain) must ALSO be bounded so
    # the helper returns with comfortable margin. Measure the wall time of
    # run_argv_result itself around a hung CLI that spawns a grandchild, with a
    # short timeout: it must return within timeout + CLEANUP budget (a small
    # scheduling slack), proving taskkill/drain cannot block unbounded and push
    # the worst case (CLI_TIMEOUT_SECONDS + cleanup) past the 120s gate.
    import time
    hang = tmp_path / "hang_cli_bounded.py"
    pid_file = tmp_path / "pids_b.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "if os.name == 'nt':\n"
        "    kw = dict(creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))\n"
        "    child = [sys.executable, '-c', 'import time; time.sleep(3600)']\n"
        "else:\n"
        "    # inherit the CLI's process group: the POSIX cleanup kills the\n"
        "    # whole GROUP, so a grandchild escaping into its own session\n"
        "    # would be outside the killpg contract.\n"
        "    kw = {}\n"
        "    child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")
    timeout = 5
    t0 = time.time()
    res = fixtures.run_argv_result(
        [sys.executable, str(hang), str(pid_file)], timeout=timeout)
    elapsed = time.time() - t0
    assert res.timed_out
    assert res.cleanup_ok is True, "real taskkill on a live tree must prove the reap"
    # bounded cleanup: the helper (timeout + bounded tree-kill/drain) must
    # return within timeout + cleanup budget + small scheduling slack.
    assert elapsed < timeout + fixtures.CLEANUP_TIMEOUT_SECONDS + 10, (
        f"cleanup path took {elapsed:.1f}s after a {timeout}s timeout -- "
        f"unbounded; at production timeout this could cross the 120s gate")
    pids = fixtures.read_json(pid_file)
    # by the time the helper returns the tree must already be reaped (the
    # helper kills the whole tree before returning), with no external polling.
    assert not fixtures._pid_alive(pids["parent"]), "parent not reaped on return"
    assert not fixtures._pid_alive(pids["child"]), "grandchild not reaped on return"


def test_pid_alive_fails_closed_when_probe_cannot_decide(monkeypatch):
    # P0: _pid_alive must NEVER report "dead" from an inconclusive probe. A
    # tasklist timeout (None), a nonzero exit, or a spawn failure is
    # UNCERTAIN and must be treated as ALIVE; only a successful (exit 0)
    # probe whose output lacks the pid proves death (verified on Windows:
    # "no tasks running" is exit 0, so rc != 0 really is a failure).
    if sys.platform != "win32":
        pytest.skip("tasklist fail-closed contract is Windows-specific")
    import types
    for broken in (None,
                   types.SimpleNamespace(returncode=1, stdout="", stderr=""),
                   types.SimpleNamespace(returncode=5, stdout="err", stderr="")):
        monkeypatch.setattr(fixtures, "_bounded_subprocess",
                            lambda argv, timeout, r=broken: r)
        assert fixtures._pid_alive(499999) is True, (
            f"probe result {broken!r} is uncertain and must fail closed as alive")
    ok_absent = types.SimpleNamespace(
        returncode=0, stdout="INFO: No tasks are running which match the specified criteria.\r\n",
        stderr="")
    monkeypatch.setattr(fixtures, "_bounded_subprocess",
                        lambda argv, timeout, r=ok_absent: r)
    assert fixtures._pid_alive(499999) is False


# module-level helper (place after ``import os`` at the top of the file); the
# REAL killpg is captured via getattr so importing on Windows (no os.killpg)
# still works.
_REAL_KILL = os.kill
_REAL_KILLPG = getattr(os, "killpg", None)


def _force_reap_tree(pid):
    """Reap a possibly-leaked CLI tree by its KNOWN root pid, independent of
    the pids JSON and of any monkeypatched fixtures helper. On POSIX the CLI
    runs under start_new_session, so `pid` is also the process GROUP id:
    killpg reaches the whole group (including a surviving grandchild) even
    after the group leader has exited. On Windows taskkill /T walks the child
    tree. Uses the REAL primitives captured at import, so neither an injected
    taskkill nor an injected killpg failure can disable this fallback. Never
    raises (tool timeouts and missing tools are caught), so it is safe to
    call unconditionally in a finally. The bool return is informational
    only; mechanical proof of reaping is a follow-up liveness check."""
    if not pid:
        return False
    if sys.platform == "win32":
        try:
            r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, timeout=10)
            return r.returncode == 0
        except (subprocess.SubprocessError, OSError):
            # TimeoutExpired (hung taskkill), FileNotFoundError (missing
            # taskkill) and other spawn-level OS errors: best effort only.
            return False
    import signal
    reaped = False
    if _REAL_KILLPG is not None:
        try:
            _REAL_KILLPG(int(pid), signal.SIGKILL)
            reaped = True
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        _REAL_KILL(int(pid), signal.SIGKILL)
        reaped = True
    except (ProcessLookupError, PermissionError, OSError):
        pass
    return reaped


@pytest.mark.skipif(sys.platform != "win32",
                     reason="Windows taskkill fail-closed contract")
@pytest.mark.parametrize("failure", [
    pytest.param(None, id="taskkill-times-out"),
    pytest.param(1, id="taskkill-nonzero-exit"),
])
def test_run_cli_result_reports_uncertain_cleanup_when_taskkill_fails(
        tmp_path, monkeypatch, failure):
    # P0 (Windows-only: the POSIX cleanup path never calls taskkill; its
    # mirror is the killpg test below): when the tree-kill tool itself fails
    # (timeout -> None, or a nonzero exit), the helper must NOT claim the
    # tree was reaped: cleanup_ok fails closed to False. The direct child is
    # still reaped by the proc.kill()
    # last resort and the return stays wall-clock bounded (shared deadline);
    # the grandchild may legitimately survive -- exactly the uncertain state
    # being reported -- so it is reaped with the REAL taskkill afterwards.
    import time
    import types
    hang = tmp_path / "hang_cli_uncertain.py"
    pid_file = tmp_path / "pids_u.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "if os.name == 'nt':\n"
        "    kw = dict(creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))\n"
        "    child = [sys.executable, '-c', 'import time; time.sleep(3600)']\n"
        "else:\n"
        "    # inherit the CLI's process group: the POSIX cleanup kills the\n"
        "    # whole GROUP, so a grandchild escaping into its own session\n"
        "    # would be outside the killpg contract.\n"
        "    kw = {}\n"
        "    child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")
    real_bounded = fixtures._bounded_subprocess

    def fake_bounded(argv, timeout):
        if argv and argv[0] == "taskkill":
            if failure is None:
                return None
            return types.SimpleNamespace(returncode=failure, stdout="", stderr="")
        return real_bounded(argv, timeout)

    monkeypatch.setattr(fixtures, "_bounded_subprocess", fake_bounded)
    t0 = time.time()
    res = None
    child_pid = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        elapsed = time.time() - t0
        assert res.timed_out
        assert res.cleanup_ok is False, (
            "a failed/uncertain taskkill must fail closed, not claim a reaped tree")
        assert elapsed < 5 + fixtures.CLEANUP_TIMEOUT_SECONDS + 10
        pids = fixtures.read_json(pid_file)
        # the direct child is reaped by the proc.kill() last resort; a short
        # poll only covers OS scheduling jitter.
        deadline = time.time() + 3
        while time.time() < deadline and fixtures._pid_alive(pids["parent"]):
            time.sleep(0.1)
        assert not fixtures._pid_alive(pids["parent"]), (
            "proc.kill() last resort must still reap the direct child")
    finally:
        # EVERY assertion above is inside this try, so a failure cannot skip
        # the reap. res.pid covers a still-alive leader. If read_json failed,
        # recover the grandchild identity from a RAW pid-file read (bypassing
        # any injected fixtures.read_json): taskkill /T on the already-dead
        # parent cannot reach an orphaned grandchild on Windows, so without
        # this the child would leak. A failing test never leaks a 3600s
        # process.
        if res is not None:
            _force_reap_tree(res.pid)
        if child_pid is None:
            try:
                child_pid = json.loads(
                    Path(pid_file).read_text(encoding="utf-8"))["child"]
            except Exception:
                child_pid = None
        if child_pid is not None:
            _force_reap_tree(child_pid)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX killpg fail-closed contract")
def test_run_cli_result_reports_uncertain_cleanup_when_killpg_fails(
        tmp_path, monkeypatch):
    # P0 (POSIX mirror of the taskkill test): when the group kill cannot be
    # delivered (os.killpg raises PermissionError), cleanup_ok must fail
    # closed to False; the direct child is still reaped by the proc.kill()
    # last resort and the return stays wall-clock bounded (shared deadline).
    # The grandchild may legitimately survive -- exactly the uncertain state
    # being reported -- so it is reaped with POSIX signals only (never
    # taskkill, which does not exist on Ubuntu CI).
    import os
    import time
    hang = tmp_path / "hang_cli_posix_fail.py"
    pid_file = tmp_path / "pids_kp.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "kw = {}\n"
        "child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")

    def fake_killpg(pgid, sig):
        raise PermissionError(f"simulated killpg failure for pgid {pgid}")

    monkeypatch.setattr(os, "killpg", fake_killpg)
    t0 = time.time()
    res = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        elapsed = time.time() - t0
        assert res.timed_out
        assert res.cleanup_ok is False, (
            "a failed/uncertain killpg must fail closed, not claim a reaped tree")
        assert elapsed < 5 + fixtures.CLEANUP_TIMEOUT_SECONDS + 10
        pids = fixtures.read_json(pid_file)
        # the direct child is reaped by the proc.kill() last resort; a short
        # poll only covers OS scheduling jitter.
        deadline = time.time() + 3
        while time.time() < deadline and fixtures._pid_alive(pids["parent"]):
            time.sleep(0.1)
        assert not fixtures._pid_alive(pids["parent"]), (
            "proc.kill() last resort must still reap the direct child")
    finally:
        # EVERY assertion above is inside this try, so a failure cannot skip
        # the reap. res.pid is the process GROUP id (start_new_session), so
        # this test-side REAL killpg reaps the whole group (including a
        # surviving grandchild) WITHOUT reading the pids JSON. It uses the
        # saved REAL killpg, unaffected by the fake killpg monkeypatch above.
        if res is not None:
            _force_reap_tree(res.pid)



@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX group-kill race (known pgid)")
def test_run_cli_result_reaps_descendant_after_group_leader_exits(tmp_path):
    # P0: the POSIX group kill must use the KNOWN pgid (== proc.pid, since
    # start_new_session=True), not getpgid(proc.pid). Here the CLI (group
    # leader) spawns a grandchild that inherits its stdout + process group and
    # then exits immediately; the grandchild keeps the pipe open, so
    # communicate() times out. On cleanup the leader is gone but the group
    # (and its remaining member) still exists -- getpgid(proc.pid) would raise
    # ProcessLookupError and report a false-green. killpg(proc.pid) must kill
    # the surviving grandchild and report cleanup_ok=True.
    import time
    hang = tmp_path / "hang_cli_leader_exits.py"
    pid_file = tmp_path / "pids_le.json"
    hang.write_text(
        "import json, os, subprocess, sys\n"
        "# grandchild inherits the CLI stdout (holding run_argv_result's pipe\n"
        "# open) and its process group; the leader then exits immediately.\n"
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3600)'])\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n",
        encoding="utf-8")
    res = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        assert res.timed_out
        assert res.cleanup_ok is True, (
            "killpg(proc.pid) must prove the whole group reaped even though the "
            "leader had already exited")
        pids = fixtures.read_json(pid_file)
        # the grandchild held the pipe; after killpg it must be gone (a brief
        # poll only covers zombie-reap scheduler jitter, not unbounded cleanup).
        deadline = time.time() + 3
        while time.time() < deadline and fixtures._pid_alive(pids["child"]):
            time.sleep(0.1)
        assert not fixtures._pid_alive(pids["child"]), (
            "surviving grandchild in the departed leader's group was not reaped")
    finally:
        # If the cleanup_ok assertion failed, the production helper did NOT
        # reap the orphaned group; fall back to the test-side REAL killpg by
        # the known group id (res.pid) so a 3600s grandchild is never leaked.
        if res is not None:
            _force_reap_tree(res.pid)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX group-kill fallback proves json-free reaping")
def test_cleanup_finally_reaps_when_read_json_fails(tmp_path, monkeypatch):
    # P1: the finally fallback must not depend on the pids JSON. Inject a
    # read_json failure alongside a production killpg failure (so the
    # grandchild genuinely survives), then prove the group is still reaped by
    # the KNOWN group id (res.pid) -- mechanically, no leak remains.
    import os
    import time
    hang = tmp_path / "hang_cli_readjson_fail.py"
    pid_file = tmp_path / "pids_rij.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "kw = {}\n"
        "child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")

    def fake_killpg(pgid, sig):
        raise PermissionError(f"simulated killpg failure for pgid {pgid}")
    monkeypatch.setattr(os, "killpg", fake_killpg)

    def fail_read_json(path):
        raise OSError("simulated read_json failure")
    monkeypatch.setattr(fixtures, "read_json", fail_read_json)

    res = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        assert res.timed_out
        assert res.cleanup_ok is False, (
            "a failed/uncertain killpg must fail closed")
    finally:
        if res is not None:
            _force_reap_tree(res.pid)
    # After the finally reaped the group by res.pid, read the raw pids directly
    # (fixtures.read_json is still monkeypatched-broken) and prove no leak.
    raw = json.loads(Path(pid_file).read_text(encoding="utf-8"))
    deadline = time.time() + 3
    while time.time() < deadline and fixtures._pid_alive(raw["child"]):
        time.sleep(0.1)
    assert not fixtures._pid_alive(raw["child"]), (
        "json-free finally fallback leaked the grandchild")


@pytest.mark.skipif(sys.platform != "win32",
                    reason="Windows taskkill/json-failure fallback contract")
def test_cleanup_finally_reaps_when_read_json_fails_windows(
        tmp_path, monkeypatch):
    # Windows mirror of the POSIX read_json test: with BOTH the tree-kill
    # (taskkill -> None) and fixtures.read_json failing, the finally must
    # still reap the orphaned grandchild by RAW-reading the pid file (the
    # parent is already dead, so taskkill /T on res.pid cannot reach it) --
    # mechanically, no leak remains on the Windows CI path either.
    import time
    hang = tmp_path / "hang_cli_readjson_fail_win.py"
    pid_file = tmp_path / "pids_rijw.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "kw = dict(creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))\n"
        "child = [sys.executable, '-c', 'import time; time.sleep(3600)']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")
    real_bounded = fixtures._bounded_subprocess

    def fake_bounded(argv, timeout):
        if argv and argv[0] == "taskkill":
            return None
        return real_bounded(argv, timeout)

    def fail_read_json(path):
        raise OSError("simulated read_json failure")

    monkeypatch.setattr(fixtures, "_bounded_subprocess", fake_bounded)
    monkeypatch.setattr(fixtures, "read_json", fail_read_json)
    res = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        assert res.timed_out
        assert res.cleanup_ok is False, (
            "a failed/uncertain taskkill must fail closed")
    finally:
        # the RAW read bypasses the injected fixtures.read_json failure and
        # recovers the grandchild identity the dead parent can no longer
        # provide to taskkill /T.
        if res is not None:
            _force_reap_tree(res.pid)
        child = None
        try:
            child = json.loads(
                Path(pid_file).read_text(encoding="utf-8"))["child"]
        except Exception:
            child = None
        if child is not None:
            _force_reap_tree(child)
    # after the finally reaped the grandchild, prove no leak (raw read again:
    # fixtures.read_json is still monkeypatched-broken).
    raw = json.loads(Path(pid_file).read_text(encoding="utf-8"))
    deadline = time.time() + 3
    while time.time() < deadline and fixtures._pid_alive(raw["child"]):
        time.sleep(0.1)
    assert not fixtures._pid_alive(raw["child"]), (
        "Windows json-free finally fallback leaked the grandchild")


def test_finalize_rejects_handcrafted_accept_report(tiny):
    # P0-1: a hand-crafted report with verdict=ACCEPT and self-consistent
    # on-disk SHAs must NOT finalize; finalize recomputes the terminal verdict
    # from the receipts and requires RAW on-disk byte equality.
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = base / "primary_ok.json"
    fixtures.write_json(p_path, primary)
    out = base / "finalize_forged"
    fixtures.run_cli("classic_acceptance_review.py", "decide",
                     "--primary", str(p_path), "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(out))
    real_report_path = out / "decision_report_v1.json"
    real = fixtures.read_json(real_report_path)
    assert real["verdict"] == "ACCEPT"
    # Tamper with the on-disk report: re-serialize with CRLF (semantically the
    # same JSON, F20 raw bytes differ) -> finalize must reject on byte equality.
    crlf_path = out / "report_crlf.json"
    crlf_path.write_bytes(c.serialize_json(real).replace(b"\n", b"\r\n"))
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(crlf_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path),
        "--data-root", str(data), "--out", str(out / "pkg_crlf"))
    assert not r.timed_out and r.returncode != 0
    assert "bytes do not match" in r.stdout + r.stderr
    # Hand-craft a verdict flip to ACCEPT over an EXPAND-producing primary is
    # covered by the recompute path; here flip a field on the genuine ACCEPT
    # report (generated_at) while keeping every bound SHA identical -> rejected.
    tampered = dict(real, generated_at="1999-01-01T00:00:00+00:00")
    tampered_path = out / "report_tampered.json"
    fixtures.write_json(tampered_path, tampered)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(tampered_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path),
        "--data-root", str(data), "--out", str(out / "pkg_tampered"))
    assert not r.timed_out and r.returncode != 0
    assert "bytes do not match" in r.stdout + r.stderr
    # A completely fabricated verdict=ACCEPT report with correct disk SHAs but
    # a wrong metrics payload is also rejected (recompute mismatch).
    forged = dict(real, fired_rules=["FORGED"], verdict="ACCEPT")
    forged_path = out / "report_forged.json"
    fixtures.write_json(forged_path, forged)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(forged_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path),
        "--data-root", str(data), "--out", str(out / "pkg_forged"))
    assert not r.timed_out and r.returncode != 0
    assert "bytes do not match" in r.stdout + r.stderr


def test_finalize_refuses_test_only(tiny):
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    p_path = base / "primary_ok.json"
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    fixtures.write_json(p_path, primary)
    out = base / "finalize_fake"
    fixtures.run_cli("classic_acceptance_review.py", "decide",
                     "--primary", str(p_path), "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(out))
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(out / "decision_report_v1.json"),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path),
        "--data-root", str(data), "--out", str(out))
    assert not r.timed_out and r.returncode != 0
    assert "fake" in (r.stdout + r.stderr).lower()


def test_finalize_expansion_reads_manifest_once(monkeypatch):
    # P0 (TOCTOU) for finalize: the expansion manifest is read exactly ONCE.
    # finalize refuses fake (test_only) products via check_finalize, so this
    # test runs the fake expansion chain and asserts the fake-refusal
    # RuntimeError fires AFTER the expansion path was read exactly once --
    # the single-read property is proven even though finalize does not seal a
    # fake package. The happy-path package SHA binding is covered separately by
    # test_finalize_build_package_pure (build_final_package assembler) and the
    # production CLI finalize test.
    chain = _expand_evidence_chain()
    try:
        dec_out = chain["base"] / "dec"
        review.cmd_decide([
            "--primary", str(chain["r2_p_path"]),
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(dec_out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"])])
        report_path = dec_out / "decision_report_v1.json"
        reads = []
        orig = Path.read_bytes

        def sentinel(self, *a, **k):
            if str(self) == str(chain["exp_path"]):
                reads.append(1)
                if len(reads) >= 2:
                    return b'{"kind": "swapped"}'
            return orig(self, *a, **k)

        monkeypatch.setattr(Path, "read_bytes", sentinel)
        fin_out = chain["base"] / "fin"
        with pytest.raises(RuntimeError, match="fake"):
            review.cmd_finalize([
                "--decision-report", str(report_path),
                "--primary", str(chain["r2_p_path"]),
                "--sample-manifest", str(chain["sm_path"]),
                "--chapter-manifest", str(chain["chman_path"]),
                "--data-root", str(chain["data"]), "--out", str(fin_out),
                "--expansion-manifest", str(chain["exp_path"]),
                "--decision-report-r1", str(chain["r1_report_path"]),
                "--producing-primary", str(chain["r1_p_path"]),
                "--producing-second", str(chain["r1_s_path"])])
        # expansion read exactly once before the fake-refusal gate fired
        assert reads == [1]
        # no package is sealed for a fake product
        assert not (fin_out / "final_acceptance_package_v1.json").exists()
    finally:
        fixtures.rmtree_force(chain["base"])


# Requires `import threading` in the test file's top imports.
def test_publish_new_file_two_writers_one_wins(tmp_path):
    # P0 (concurrent publication): exists()+write_bytes() is check-then-write;
    # two concurrent publishers can both observe absence and both write the
    # frozen path (overwrite / mixed-partial publication). The atomic
    # publish_new_file primitive must let EXACTLY ONE writer win, make every
    # loser fail closed, leave the sealed bytes equal to one complete canonical
    # payload, and clean up every temporary file (no half-file left behind to
    # block retries).
    target_dir = tmp_path / "pub"
    target_dir.mkdir()
    sealed = target_dir / "final_acceptance_package_v1.json"
    payload = c.serialize_json({"kind": "final_acceptance_package_v1",
                                "final_verdict": "ACCEPT"})
    winners = []
    losers = []

    def publisher(i):
        try:
            c.publish_new_file(sealed, payload)
            winners.append(i)
        except RuntimeError:
            losers.append(i)

    threads = [threading.Thread(target=publisher, args=(i,)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(winners) == 1, f"exactly one publisher must win, got {winners}"
    assert len(losers) == 7, f"all other publishers must fail closed, got {losers}"
    assert sealed.read_bytes() == payload
    leftovers = [p.name for p in target_dir.iterdir() if p.suffix == ".tmp"]
    assert leftovers == [], "temporary files must be cleaned up (no half-file)"


def test_publish_new_file_sequential_rejects_existing(tmp_path):
    # Sequential re-publication also fails closed and leaves the original bytes
    # untouched (the order-independent counterpart to the concurrent test).
    sealed = tmp_path / "final_acceptance_package_v1.json"
    first = c.serialize_json({"v": 1})
    c.publish_new_file(sealed, first)
    before = sealed.read_bytes()
    with pytest.raises(RuntimeError, match="already exists"):
        c.publish_new_file(sealed, c.serialize_json({"v": 2}))
    assert sealed.read_bytes() == before
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q -k finalize`
Expected: `AttributeError: ... has no attribute 'check_finalize'` / unknown subcommand

- [ ] **Step 3: 实现（追加到 `scripts/classic_acceptance_review.py`）**

```python
# --- scripts/classic_acceptance_common.py (追加；文件顶部 import 增加 `import os`
#     与 `import tempfile`) ---

def publish_new_file(path, data):
    """Design section 8 publication primitive: atomically create `path` with
    `data`, failing closed if `path` already exists -- a frozen artifact is
    never overwritten in place, even by concurrent publishers.

    The bytes are fully written to a SAME-DIRECTORY temporary file, fsynced,
    and read back for verification first, so the final path is only ever made
    visible via an atomic create-if-absent link (os.link raises FileExistsError
    when the target already exists on BOTH POSIX and Windows; empirically
    verified on win32). This avoids the two failure modes of `open(path, 'xb')`:
    a mid-write crash cannot leave a half-written file at the frozen path that
    would permanently block retries, and two concurrent publishers cannot both
    observe absence and both write. Each publisher cleans up its own temp file;
    a pre-existing final path is never touched (its bytes remain the first
    complete publication)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                    dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if tmp.read_bytes() != data:
            raise RuntimeError(f"publish: temporary file verification failed for {path}")
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise RuntimeError(
                f"publish: {path} already exists; a frozen artifact must not be "
                f"overwritten in place (design section 8). Publish a correction "
                f"as a new version (new output directory / versioned filename).")
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


# --- scripts/classic_acceptance_review.py (追加) ---

def check_finalize(report):
    c.require(report.get("kind") == "decision_report_v1",
              "finalize: not a decision report")
    c.require(report.get("verdict") in ("ACCEPT", "REJECT"),
              f"finalize requires a terminal verdict (ACCEPT|REJECT), got {report.get('verdict')!r}")
    c.require(not report.get("test_only"),
              "finalize refuses test_only=fake decision reports (F13/F17); "
              "fake products must not enter final acceptance")


def build_final_package(report, primary, report_sha, exp_shas, artifact_files,
                        exp_files=None, today=None):
    """Pure assembler for final_acceptance_package_v1. `report` is the
    already-verified (recomputed + byte-equal + terminal) decision report and
    `primary` the verified primary package; all SHAs are raw on-disk values.
    Split out so the assembly logic is unit-testable without the frozen
    production chain or the fake-refusal gate.

    `artifact_files` maps each consumed role -> the BASENAME of the file the
    caller actually passed on the CLI (e.g. {"primary_review": "primary_ok.json",
    ...}); `exp_files` is the parallel basename list for `exp_shas`. The
    assembler NEVER fabricates a canonical filename: the recorded file identity
    is the real consumed input (design section 8 "记录所用版本与各自 SHA" -- the
    version is identified by the actually-consumed file plus its content SHA;
    within one package each role is unique and expansion entries carry an
    index, and the content-address SHA disambiguates same-named files from
    different directories). A missing identity fails closed rather than
    defaulting to a name that could be false. Optional receipts (second /
    arbitration / expansions) are listed only when actually consumed."""
    import datetime

    def file_of(role):
        name = artifact_files.get(role)
        c.require(isinstance(name, str) and name,
                  f"finalize: missing consumed-file identity for artifact {role!r}")
        return name

    artifacts = [
        {"role": "decision_report", "file": file_of("decision_report"),
         "sha256": report_sha},
        {"role": "primary_review", "file": file_of("primary_review"),
         "sha256": report["primary_sha256"]},
        {"role": "sample_manifest", "file": file_of("sample_manifest"),
         "sha256": report["sample_manifest_sha256"]},
    ]
    if report.get("second_review_sha256"):
        artifacts.append({"role": "second_review", "file": file_of("second_review"),
                          "sha256": report["second_review_sha256"]})
    if report.get("arbitration_sha256"):
        artifacts.append({"role": "arbitration", "file": file_of("arbitration"),
                          "sha256": report["arbitration_sha256"]})
    exp_files = exp_files or []
    for i, s in enumerate(exp_shas):
        name = exp_files[i] if i < len(exp_files) else None
        c.require(isinstance(name, str) and name,
                  f"finalize: missing consumed-file identity for expansion[{i}]")
        artifacts.append({"role": "expansion_manifest", "index": i,
                          "file": name, "sha256": s})
    return {
        "schema_version": "1.0",
        "kind": "final_acceptance_package_v1",
        "final_verdict": report["verdict"],
        "decision_report_sha256": report_sha,
        "primary_sha256": report["primary_sha256"],
        "second_review_sha256": report.get("second_review_sha256"),
        "arbitration_sha256": report.get("arbitration_sha256"),
        "sample_manifest_sha256": report["sample_manifest_sha256"],
        "expansion_manifests_sha256": exp_shas,
        "artifacts": artifacts,
        "reviewer_list": primary.get("reviewer_list"),
        "generated_at": (today or datetime.date.today()).isoformat(),
    }


FINALIZE_FLAGS = {"decision-report", "primary", "sample-manifest",
                  "chapter-manifest", "out", "candidate-commit", "data-root",
                  "second", "arbitration", "expansion-manifest",
                  "decision-report-r1", "producing-primary",
                  "producing-second", "producing-arbitration"}


def cmd_finalize(argv):
    flags, _ = c.parse_flags(argv, allowed=FINALIZE_FLAGS)
    report_path = c.flag1(flags, "decision-report")
    primary_path = c.flag1(flags, "primary")
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    second_path = c.flag_opt(flags, "second")
    arbitration_path = c.flag_opt(flags, "arbitration")
    # Only one parallel expansion round exists (F19): at most one expansion,
    # and when present it must carry the R1 producing report + evidence bundle.
    expansion_path = c.flag_opt(flags, "expansion-manifest")
    r1_report_path = c.flag_opt(flags, "decision-report-r1")
    pp_path = c.flag_opt(flags, "producing-primary")
    ps_path = c.flag_opt(flags, "producing-second")
    pa_path = c.flag_opt(flags, "producing-arbitration")
    # P0-1: finalize must NOT trust report fields. Re-run the EXACT chain the
    # producer/consumers run. Order matters: recompute -> RAW on-disk byte
    # equality -> check_finalize (terminal verdict + fake refusal) -> package.
    # The byte-equality gate runs BEFORE check_finalize so a tampered fake
    # report is rejected for byte mismatch (the real failure mode), while a
    # canonical fake report is still rejected by the fake-refusal gate.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    check_producing_evidence_presence(
        bool(expansion_path), r1_report_path, pp_path, ps_path, pa_path, "finalize")
    expansions = []
    expansion_shas = []
    if expansion_path:
        # P0: read the expansion ONCE -- object and pinned SHA come from the
        # same bytes and are reused for validation AND the final-package SHA
        # binding (no re-read, no TOCTOU window).
        em_bytes = Path(expansion_path).read_bytes()
        em_sha = c.sha256_bytes(em_bytes)
        em = json.loads(em_bytes.decode("utf-8"))
        rep, rep_sha = verify_producing_report(
            r1_report_path, sample_manifest, sm_sha,
            chapter_manifest, source, source_desc, is_fake,
            pp_path, ps_path, pa_path)
        sampling.validate_expansion_manifest(
            em, sample_manifest, chapter_manifest, source, source_desc,
            sm_sha, expected_test_only=is_fake,
            report=rep, report_sha=rep_sha)
        expansions = [em]
        expansion_shas = [em_sha]
    _primary, _second, _arbitration, recomputed = validate_decision_inputs(
        sample_manifest, expansions, chapter_manifest, source, source_desc,
        sm_sha, expansion_shas,
        is_fake, primary_path, second_path, arbitration_path)
    # P0-2 / F20: the on-disk decision report must be byte-identical to the
    # verdict recomputed from the receipts (CRLF / whitespace / key reorder /
    # duplicate keys all rejected). Runs BEFORE the terminal/fake gate.
    actual_bytes = Path(report_path).read_bytes()
    expected_bytes = c.serialize_json(recomputed)
    c.require(actual_bytes == expected_bytes,
              "finalize: on-disk decision report bytes do not match the verdict "
              "recomputed from the receipts and frozen data (hand-crafted or "
              "re-serialized report rejected)")
    check_finalize(recomputed)
    # design section 8: record the REAL consumed-file identity (basename of
    # each validated CLI input) -- never a fabricated canonical name -- bound
    # to its content SHA.
    artifact_files = {
        "decision_report": Path(report_path).name,
        "primary_review": Path(primary_path).name,
        "sample_manifest": Path(sm_path).name,
    }
    if second_path:
        artifact_files["second_review"] = Path(second_path).name
    if arbitration_path:
        artifact_files["arbitration"] = Path(arbitration_path).name
    exp_files = [Path(expansion_path).name] if expansion_path else []
    package = build_final_package(recomputed, _primary,
                                  c.sha256_bytes(actual_bytes), expansion_shas,
                                  artifact_files, exp_files)
    # P0 (design section 8): publish through the atomic create-if-absent
    # primitive (temp file -> fsync -> read-back verify -> os.link). Both
    # sequential re-runs and CONCURRENT finalize processes fail closed: the
    # sealed final path is created exactly once, never partially written and
    # never overwritten. A correction is published by re-running finalize into
    # a NEW --out directory (the toolchain's "_v2" new-version publication).
    c.publish_new_file(out_dir / "final_acceptance_package_v1.json",
                       c.serialize_json(package))
    print("final acceptance package:", out_dir / "final_acceptance_package_v1.json")
    print("final verdict:", package["final_verdict"])
```

dispatch 增加：

```python
        elif cmd == "finalize":
            cmd_finalize(argv[1:])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_review.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add scripts/classic_acceptance_review.py tests/test_classic_acceptance_review.py
git commit -m "feat(acceptance): final package assembly with receipt closure (F13/F17)"
```

---

### Task 9: fake 数据端到端

**Files:**
- Modify: `tests/classic_acceptance_fixtures.py`（追加大 fake 数据集 + 审核填写辅助）
- Create: `tests/test_classic_acceptance_e2e.py`

- [ ] **Step 1: 向 `tests/classic_acceptance_fixtures.py` 追加**

```python
# ---- big fake dataset: EXACT real populations / strata / boundary counts /
# zero-output chapters (design section 3.3/4.2/4.3 with the v4.6.1 errata).
STRATA = [(1, 1, 80), (2, 81, 89), (3, 90, 162), (4, 163, 184), (5, 185, 244),
          (6, 245, 304), (7, 305, 346), (8, 347, 367), (9, 368, 383)]
POP = {1: (1542, 777), 2: (74, 59), 3: (708, 593), 4: (291, 211), 5: (1320, 1226),
       6: (1274, 1187), 7: (1108, 843), 8: (505, 367), 9: (1221, 840)}
BOUNDARY_COUNTS = {1: (14, 14), 80: (1, 1), 81: (2, 2), 90: (15, 14), 163: (28, 4),
                   185: (40, 38), 245: (35, 32), 305: (15, 14), 347: (12, 9),
                   368: (81, 49), 383: (24, 17)}
ZERO_RULE = {25, 56, 72}
ZERO_MCQ = {25, 26, 56, 72, 112}
OTHER_POP = {"qiongtongbaojian": (2312, 2120), "ditiansui": (799, 646),
             "zipingzhenquan": (156, 155)}
FAKE_SNAP = "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/" + "f" * 64


def _distribute(total, chapters):
    assert total >= len(chapters) >= 1
    base, extra = divmod(total - len(chapters), len(chapters))
    return {ci: 1 + base + (1 if i < extra else 0) for i, ci in enumerate(chapters)}


def build_fake_dataset(base):
    base = Path(base)
    rule_counts, mcq_counts = {}, {}
    for _idx, lo, hi in STRATA:
        pop_r, pop_m = POP[_idx]
        chs = list(range(lo, hi + 1))
        dist_r = [ci for ci in chs if ci not in ZERO_RULE and ci not in BOUNDARY_COUNTS]
        dist_m = [ci for ci in chs if ci not in ZERO_MCQ and ci not in BOUNDARY_COUNTS]
        b_r = sum(BOUNDARY_COUNTS[ci][0] for ci in chs if ci in BOUNDARY_COUNTS)
        b_m = sum(BOUNDARY_COUNTS[ci][1] for ci in chs if ci in BOUNDARY_COUNTS)
        counts_r = _distribute(pop_r - b_r, dist_r)
        counts_m = _distribute(pop_m - b_m, dist_m)
        for ci in chs:
            rule_counts[ci] = (BOUNDARY_COUNTS[ci][0] if ci in BOUNDARY_COUNTS
                               else counts_r.get(ci, 0))
            mcq_counts[ci] = (BOUNDARY_COUNTS[ci][1] if ci in BOUNDARY_COUNTS
                              else counts_m.get(ci, 0))
    assert sum(rule_counts.values()) == 8043
    assert sum(mcq_counts.values()) == 6103
    assert {ci for ci, n in rule_counts.items() if n == 0} == ZERO_RULE
    assert {ci for ci, n in mcq_counts.items() if n == 0} == ZERO_MCQ
    chapters, rules, mcqs = [], [], []
    for ci in range(1, 384):
        raw_rel = f"{FAKE_SNAP}/extracted/raw_{ci:03d}.txt"
        p = base / raw_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(
            (f"第{ci}章 原文内容 其一。\n第{ci}章 原文内容 其二。\n").encode("utf-8"))
        rule_ids = [f"smth_{ci:03d}_r{i:04d}" for i in range(rule_counts[ci])]
        mcq_ids = [f"smth_{ci:03d}_m{i:04d}" for i in range(mcq_counts[ci])]
        chapters.append({"chapter_index": ci, "title": f"第{ci}章·测试",
                         "is_legacy": ci <= 80, "raw_source_path": raw_rel,
                         "rule_ids": rule_ids, "mcq_ids": mcq_ids,
                         "rule_count": len(rule_ids), "mcq_count": len(mcq_ids),
                         "zero_rule": ci in ZERO_RULE, "zero_mcq": ci in ZERO_MCQ})
        for i in range(rule_counts[ci]):
            rules.append({"id": f"smth_{ci:03d}_r{i:04d}", "category": "测试",
                          "subject": "测试", "condition": "测试条件",
                          "rule": f"第{ci}章测试规则{i}。",
                          "original_text": f"第{ci}章 原文内容其一",
                          "source_book": "三命通会", "source_chapter": str(ci)})
        for i in range(mcq_counts[ci]):
            mcqs.append({"question": f"第{ci}章测试问题{i}？",
                         "options": {"A": "对", "B": "错", "C": "否", "D": "疑"},
                         "answer": "A", "explanation": "测试解释。",
                         "difficulty": "初级", "category": "测试",
                         "source_rule_id": f"smth_{ci:03d}_r0000",
                         "id": f"smth_{ci:03d}_m{i:04d}"})
    sm_dir = base / "knowledge_base" / "classic_texts" / "sanmingtonghui"
    write_json(sm_dir / "all_rules.json", rules)
    (sm_dir / "all_mcq.jsonl").write_bytes(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mcqs).encode("utf-8"))
    for book, (nr, nm) in OTHER_POP.items():
        bdir = base / "knowledge_base" / "classic_texts" / book
        bdir.mkdir(parents=True, exist_ok=True)
        brules = [{"id": f"{book}_r{i:05d}", "category": "测试", "subject": "测试",
                   "condition": "测试", "rule": f"{book}测试规则{i}。",
                   "original_text": f"{book}原文{i}", "source_book": book,
                   "source_chapter": f"一、测试节{i}"} for i in range(nr)]
        bmcqs = [{"question": f"{book}测试问题{i}？",
                  "options": {"A": "对", "B": "错", "C": "否", "D": "疑"},
                  "answer": "A", "explanation": "测试解释。", "difficulty": "初级",
                  "category": "测试", "source_rule_id": f"{book}_r{i:05d}",
                  "id": f"{book}_m{i:05d}"} for i in range(nm)]
        write_json(bdir / "all_rules.json", brules)
        (bdir / "all_mcq.jsonl").write_bytes(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in bmcqs).encode("utf-8"))
    (base / "knowledge_base" / "classic_texts" / "qiongtongbaojian"
     / "quarantine_rules.jsonl").write_bytes(b'{"id": "fake_q_1"}\n')
    chman = {"schema_version": "1.0", "chapter_count": 383,
             "zero_rule_chapters": sorted(ZERO_RULE),
             "zero_mcq_chapters": sorted(ZERO_MCQ), "chapters": chapters}
    chman_path = base / "chapter_manifest.json"
    write_json(chman_path, chman)
    return base, chman_path


# review-fill helpers: first reviewer defaults to "e2e-r1", second to
# "e2e-r2", arbitrator to "e2e-arb" (all pairwise distinct, F15).

def make_primary(packet_path, out_path, verdicts=None, default="PASS",
                 first_reviewer="e2e-r1"):
    packet = read_json(packet_path)
    items = []
    for e in packet["items"]:
        key = (e["book"], e["type"], e["id"])
        verdict, findings = (verdicts or {}).get(key, (default, []))
        fs = []
        for f in findings:
            f = dict(f)
            f["reviewer"] = first_reviewer
            f.setdefault("reviewed_at", "2026-08-23T00:00:00+08:00")
            fs.append(f)
        items.append({"item": {"book": e["book"], "type": e["type"], "id": e["id"],
                               "source_chapter": e.get("source_chapter")},
                      "verdict": verdict, "findings": fs})
    primary = {"schema_version": "1.0", "kind": "primary_review_package",
               "sample_manifest_sha256": packet["sample_manifest_sha256"],
               "expansion_manifests_sha256": packet.get("expansion_manifests_sha256") or [],
               "items": items, "overall_stats": {"note": "recomputed by decide"},
               "zero_output_report": packet["integrity"]["zero_output_chapters"],
               "reviewer_list": [first_reviewer]}
    write_json(out_path, primary)
    return str(out_path)


def make_second(primary_path, out_path, agree=None, default_agree=True,
                second_reviewer="e2e-r2"):
    primary = read_json(primary_path)
    entries = []
    for entry in primary["items"]:
        item = entry["item"]
        for idx, f in enumerate(entry["findings"]):
            if f["severity"] != "critical":
                continue
            ref = (item["book"], item["type"], item["id"], idx)
            a = agree.get(ref, default_agree) if agree else default_agree
            entries.append({"book": item["book"], "type": item["type"], "id": item["id"],
                            "finding_index": idx, "first_severity": "critical",
                            "first_category": f["category"], "agree": a,
                            "evidence_text": "e2e second review evidence",
                            "reviewer": second_reviewer,
                            "reviewed_at": "2026-08-23T00:00:00+08:00"})
    receipt = {"schema_version": "1.0", "kind": "second_review_receipt_v1",
               "primary_sha256": sha256_file(primary_path), "reviewer": second_reviewer,
               "reviewed_at": "2026-08-23T00:00:00+08:00", "entries": entries}
    write_json(out_path, receipt)
    return str(out_path)


def make_arbitration(primary_path, second_path, out_path, decisions=None,
                     default_decision="critical", arbitrator="e2e-arb"):
    primary = read_json(primary_path)
    second = read_json(second_path)
    first_by_ref = {}
    for entry in primary["items"]:
        item = entry["item"]
        for idx, f in enumerate(entry["findings"]):
            if f["severity"] == "critical":
                first_by_ref[(item["book"], item["type"], item["id"], idx)] = f["reviewer"]
    entries = []
    for e in second["entries"]:
        if e["agree"]:
            continue
        ref = (e["book"], e["type"], e["id"], e["finding_index"])
        d = decisions.get(ref, default_decision) if decisions else default_decision
        entries.append({"book": e["book"], "type": e["type"], "id": e["id"],
                        "finding_index": e["finding_index"], "reviewer_first": first_by_ref[ref],
                        "decision": d, "reasoning": "e2e arbitration reasoning",
                        "arbitrator": arbitrator,
                        "reviewed_at": "2026-08-23T00:00:00+08:00"})
    receipt = {"schema_version": "1.0", "kind": "arbitration_receipt_v1",
               "primary_sha256": sha256_file(primary_path),
               "second_review_sha256": sha256_file(second_path),
               "reviewer_first": None, "reviewer_second": second["reviewer"],
               "arbitrator": arbitrator, "reviewed_at": "2026-08-23T00:00:00+08:00",
               "entries": entries}
    write_json(out_path, receipt)
    return str(out_path)
```

注意：`make_arbitration` 顶层 `reviewer_first` 设为 `None`（因 primary 可有多个首审人，F15 按 entry 绑定）；Task 5 的 `validate_arbitration` 不读取顶层 `reviewer_first`，只校验 entry 级字段。

- [ ] **Step 2: 创建 `tests/test_classic_acceptance_e2e.py`（失败测试）**

```python
"""Fake-data end-to-end tests for the classic-texts manual acceptance (design
v4.6.1). The fake dataset reproduces the EXACT real stratum populations,
boundary chapter counts and zero-output chapters, so e2e asserts the real
frozen totals (609 rules + 382 MCQ) and every section 6.2 decision path.
Fully offline: no model API, no Phase 8, no network; fake outputs are
test_only=true and finalize refuses them.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import classic_acceptance_common as c
import classic_acceptance_fixtures as fixtures


@pytest.fixture(scope="module")
def big():
    base = fixtures.tmp_dir("acceptance_e2e")
    data, chman_path = fixtures.build_fake_dataset(base / "data")
    yield base, data, chman_path
    fixtures.rmtree_force(base)


def _sample(big, run_name):
    base, data, chman_path = big
    run = base / run_name
    run.mkdir(parents=True, exist_ok=True)
    fixtures.run_cli("classic_acceptance_sampling.py", "sample",
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(run))
    return run / "sample_manifest_v1.json"


def _packet(big, run, sm_path, expansion=None, producing_report=None,
            producing_primary=None, producing_second=None,
            producing_arbitration=None):
    base, data, chman_path = big
    args = ["classic_acceptance_review.py", "packet", "--sample-manifest", str(sm_path)]
    if expansion:
        args += ["--expansion-manifest", str(expansion)]
        # P0/F19: an expansion must carry its producing EXPAND decision report
        # AND the full R1 evidence bundle (report is recomputed from them).
        args += ["--decision-report", str(producing_report)]
        args += ["--producing-primary", str(producing_primary)]
        if producing_second:
            args += ["--producing-second", str(producing_second)]
        if producing_arbitration:
            args += ["--producing-arbitration", str(producing_arbitration)]
    args += ["--chapter-manifest", str(chman_path), "--data-root", str(data),
             "--out", str(run)]
    fixtures.run_cli(*args)
    return run / "review_packet_v1.json"


def _decide(big, run, primary, sm_path, second=None, arbitration=None,
            expansion=None, producing_report=None, producing_primary=None,
            producing_second=None, producing_arbitration=None):
    base, data, chman_path = big
    args = ["classic_acceptance_review.py", "decide", "--primary", str(primary)]
    if second:
        args += ["--second", str(second)]
    if arbitration:
        args += ["--arbitration", str(arbitration)]
    if expansion:
        args += ["--expansion-manifest", str(expansion)]
        args += ["--decision-report", str(producing_report)]
        args += ["--producing-primary", str(producing_primary)]
        if producing_second:
            args += ["--producing-second", str(producing_second)]
        if producing_arbitration:
            args += ["--producing-arbitration", str(producing_arbitration)]
    args += ["--sample-manifest", str(sm_path), "--chapter-manifest", str(chman_path),
             "--data-root", str(data), "--out", str(run)]
    fixtures.run_cli(*args)
    return fixtures.read_json(run / "decision_report_v1.json")


def test_e2e_sample_totals(big):
    sm_path = _sample(big, "run_totals")
    sm = fixtures.read_json(sm_path)
    assert sm["totals"] == {"rule": {"random": 342, "boundary": 267, "total": 609},
                            "mcq": {"random": 188, "boundary": 194, "total": 382}}
    assert sm["k_table"]["sanmingtonghui"]["mcq"]["8"] == 7


def test_e2e_accept(big):
    run = big[0] / "run_accept"
    sm_path = _sample(big, "run_accept")
    packet = _packet(big, run, sm_path)
    assert len(fixtures.read_json(packet)["items"]) == 991
    primary = fixtures.make_primary(packet, run / "primary_review_package_v1.json")
    report = _decide(big, run, primary, sm_path)
    assert report["verdict"] == "ACCEPT"
    assert report["fired_rules"] == []
    assert report["second_review_sha256"] is None
    assert report["test_only"] is True
    assert report["metrics"]["zipingzhenquan"]["rule"]["critical_rate"] == "0/5"


def test_e2e_boundary_critical_reject(big):
    run = big[0] / "run_boundary"
    sm_path = _sample(big, "run_boundary")
    sm = fixtures.read_json(sm_path)
    bid = sm["boundary_samples"]["sanmingtonghui"]["rule"][0]
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("sanmingtonghui", "rule", bid): ("FAIL", [fixtures.critical()])})
    second = fixtures.make_second(primary, run / "second_review_receipt_v1.json")
    report = _decide(big, run, primary, sm_path, second=second)
    assert report["verdict"] == "REJECT"
    assert report["fired_rules"] == ["BOUNDARY"]


def test_e2e_boundary_arbitration(big):
    run = big[0] / "run_arbitration"
    sm_path = _sample(big, "run_arbitration")
    sm = fixtures.read_json(sm_path)
    bid = sm["boundary_samples"]["sanmingtonghui"]["rule"][0]
    ref = ("sanmingtonghui", "rule", bid, 0)
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("sanmingtonghui", "rule", bid): ("FAIL", [fixtures.critical()])})
    second = fixtures.make_second(primary, run / "second_review_receipt_v1.json",
                                  agree={ref: False})
    arb = fixtures.make_arbitration(primary, second, run / "arbitration_receipt_v1.json")
    report = _decide(big, run, primary, sm_path, second=second, arbitration=arb)
    assert report["verdict"] == "REJECT" and report["fired_rules"] == ["BOUNDARY"]
    arb2 = fixtures.make_arbitration(primary, second, run / "arbitration_receipt_v2.json",
                                     decisions={ref: "non_critical"})
    report2 = _decide(big, run, primary, sm_path, second=second, arbitration=arb2)
    # F3: finding deleted, no critical/minor numerator; sanmingtonghui rule
    # denominator is random rules (244) + boundary rules (267) = 511 (NOT 609,
    # which is the four-book rule total; P0-7 correction).
    assert report2["verdict"] == "ACCEPT"
    assert report2["metrics"]["sanmingtonghui"]["rule"]["critical_items"] == 0
    assert report2["metrics"]["sanmingtonghui"]["rule"]["minor_only_items"] == 0
    assert report2["metrics"]["sanmingtonghui"]["rule"]["reviewed"] == 511


def test_e2e_stratum_cascade_reject(big):
    run = big[0] / "run_cascade"
    sm_path = _sample(big, "run_cascade")
    sm = fixtures.read_json(sm_path)
    iid = sm["samples"]["sanmingtonghui"]["rule"]["2"][0]
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("sanmingtonghui", "rule", iid): ("FAIL", [fixtures.critical()])})
    second = fixtures.make_second(primary, run / "second_review_receipt_v1.json")
    report = _decide(big, run, primary, sm_path, second=second)
    assert report["verdict"] == "REJECT"
    assert report["fired_rules"] == ["STRATUM_CASCADE"]


def test_e2e_reject_gate(big):
    run = big[0] / "run_gate"
    sm_path = _sample(big, "run_gate")
    sm = fixtures.read_json(sm_path)
    mid = sm["samples"]["zipingzhenquan"]["mcq"]["1"][0]
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("zipingzhenquan", "mcq", mid): ("FAIL", [fixtures.critical()])})
    second = fixtures.make_second(primary, run / "second_review_receipt_v1.json")
    report = _decide(big, run, primary, sm_path, second=second)
    assert report["verdict"] == "REJECT"
    assert report["fired_rules"] == ["REJECT_GATE"]


def test_e2e_minor_gate_reject(big):
    run = big[0] / "run_minor"
    sm_path = _sample(big, "run_minor")
    sm = fixtures.read_json(sm_path)
    mid = sm["samples"]["zipingzhenquan"]["mcq"]["1"][0]
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("zipingzhenquan", "mcq", mid): ("PASS_WITH_MINOR", [fixtures.minor()])})
    report = _decide(big, run, primary, sm_path)
    assert report["verdict"] == "REJECT"
    assert report["fired_rules"] == ["REJECT_GATE"]


def test_e2e_expand_then_accept(big):
    base, data, chman_path = big
    r1 = base / "run_expand_r1"
    sm_path = _sample(big, "run_expand_r1")
    sm = fixtures.read_json(sm_path)
    verdicts = {}
    for s, n in (("1", 4), ("5", 6), ("6", 5)):
        for iid in sm["samples"]["sanmingtonghui"]["rule"][s][:n]:
            verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    packet = _packet(big, r1, sm_path)
    primary = fixtures.make_primary(packet, r1 / "primary_review_package_v1.json", verdicts)
    second = fixtures.make_second(primary, r1 / "second_review_receipt_v1.json")
    report = _decide(big, r1, primary, sm_path, second=second)
    assert report["verdict"] == "EXPAND"
    assert report["pending_expands"] == [{"book": "sanmingtonghui", "type": "rule"}]
    assert report["metrics"]["sanmingtonghui"]["rule"]["critical_rate"] == "15/511"
    fixtures.run_cli("classic_acceptance_sampling.py", "expand",
                     "--sample-manifest", str(sm_path),
                     "--decision-report", str(r1 / "decision_report_v1.json"),
                     "--primary", str(primary), "--second", str(second),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(r1))
    exp_path = r1 / "expansion_manifest_v1.json"
    exp = fixtures.read_json(exp_path)
    assert sum(info["added"] for info in
               exp["expansions"]["sanmingtonghui"]["rule"].values()) == 244
    old_ids = set()
    for ids in sm["samples"]["sanmingtonghui"]["rule"].values():
        old_ids.update(ids)
    old_ids.update(sm["boundary_samples"]["sanmingtonghui"]["rule"])
    new_ids = set()
    for info in exp["expansions"]["sanmingtonghui"]["rule"].values():
        new_ids.update(info["new_ids"])
    assert not (new_ids & old_ids)
    r2 = base / "run_expand_r2"
    r1_report = r1 / "decision_report_v1.json"
    r1_primary = primary
    r1_second = second
    packet2 = _packet(big, r2, sm_path, expansion=exp_path,
                      producing_report=r1_report,
                      producing_primary=r1_primary,
                      producing_second=r1_second)
    assert len(fixtures.read_json(packet2)["items"]) == 1235
    primary2 = fixtures.make_primary(packet2, r2 / "primary_review_package_v1.json", verdicts)
    second2 = fixtures.make_second(primary2, r2 / "second_review_receipt_v1.json")
    report2 = _decide(big, r2, primary2, sm_path, second=second2,
                      expansion=exp_path, producing_report=r1_report,
                      producing_primary=r1_primary, producing_second=r1_second)
    assert report2["verdict"] == "ACCEPT"
    assert report2["expanded_pairs"] == [{"book": "sanmingtonghui", "type": "rule"}]
    assert report2["metrics"]["sanmingtonghui"]["rule"]["critical_rate"] == "15/755"


def test_e2e_expanded_pair_fail_closed(big):
    base, data, chman_path = big
    r1 = base / "run_fc_r1"
    sm_path = _sample(big, "run_fc_r1")
    sm = fixtures.read_json(sm_path)
    verdicts = {}
    for s, n in (("1", 4), ("5", 6), ("6", 5)):
        for iid in sm["samples"]["sanmingtonghui"]["rule"][s][:n]:
            verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    packet = _packet(big, r1, sm_path)
    primary = fixtures.make_primary(packet, r1 / "primary_review_package_v1.json", verdicts)
    second = fixtures.make_second(primary, r1 / "second_review_receipt_v1.json")
    report = _decide(big, r1, primary, sm_path, second=second)
    assert report["verdict"] == "EXPAND"
    fixtures.run_cli("classic_acceptance_sampling.py", "expand",
                     "--sample-manifest", str(sm_path),
                     "--decision-report", str(r1 / "decision_report_v1.json"),
                     "--primary", str(primary), "--second", str(second),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(r1))
    exp_path = r1 / "expansion_manifest_v1.json"
    exp = fixtures.read_json(exp_path)
    new_by_stratum = exp["expansions"]["sanmingtonghui"]["rule"]
    picks = (new_by_stratum["3"]["new_ids"][:2] + new_by_stratum["7"]["new_ids"][:3]
             + new_by_stratum["9"]["new_ids"][:11])
    assert len(picks) == 16
    for iid in picks:
        verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    r2 = base / "run_fc_r2"
    r1_report = r1 / "decision_report_v1.json"
    packet2 = _packet(big, r2, sm_path, expansion=exp_path,
                      producing_report=r1_report,
                      producing_primary=primary, producing_second=second)
    primary2 = fixtures.make_primary(packet2, r2 / "primary_review_package_v1.json", verdicts)
    second2 = fixtures.make_second(primary2, r2 / "second_review_receipt_v1.json")
    report2 = _decide(big, r2, primary2, sm_path, second=second2,
                      expansion=exp_path, producing_report=r1_report,
                      producing_primary=primary, producing_second=second)
    assert report2["verdict"] == "REJECT"
    assert report2["fired_rules"] == ["EXPAND_GATE"]
    assert report2["metrics"]["sanmingtonghui"]["rule"]["critical_rate"] == "31/755"


def test_e2e_producing_report_byte_tampering_rejected(big):
    # P0-2: the producing EXPAND report must match the recomputed verdict at
    # the RAW on-disk byte level. CRLF, trailing whitespace, reordered keys
    # and duplicate JSON keys all survive a parse round-trip but must be
    # rejected by both the consumer (packet) and the producer (expand).
    import json as _json
    base, data, chman_path = big
    r1 = base / "run_byte_tamper"
    sm_path = _sample(big, "run_byte_tamper")
    sm = fixtures.read_json(sm_path)
    verdicts = {}
    for s, n in (("1", 4), ("5", 6), ("6", 5)):
        for iid in sm["samples"]["sanmingtonghui"]["rule"][s][:n]:
            verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    packet = _packet(big, r1, sm_path)
    primary = fixtures.make_primary(packet, r1 / "primary_review_package_v1.json", verdicts)
    second = fixtures.make_second(primary, r1 / "second_review_receipt_v1.json")
    report = _decide(big, r1, primary, sm_path, second=second)
    assert report["verdict"] == "EXPAND"
    real_path = r1 / "decision_report_v1.json"
    canonical = real_path.read_bytes()

    def expect_reject(label, payload, subcmd):
        tampered = r1 / f"report_{label}.json"
        tampered.write_bytes(payload)
        if subcmd == "packet":
            cmd = ["classic_acceptance_review.py", "packet",
                   "--sample-manifest", str(sm_path),
                   "--chapter-manifest", str(chman_path),
                   "--data-root", str(data), "--out", str(r1 / f"pkt_{label}"),
                   "--expansion-manifest", str(r1 / "expansion_manifest_v1.json"),
                   "--decision-report", str(tampered),
                   "--producing-primary", str(primary),
                   "--producing-second", str(second)]
        else:
            cmd = ["classic_acceptance_sampling.py", "expand",
                   "--sample-manifest", str(sm_path),
                   "--decision-report", str(tampered),
                   "--primary", str(primary), "--second", str(second),
                   "--chapter-manifest", str(chman_path),
                   "--data-root", str(data), "--out", str(r1 / f"exp_{label}")]
        r = fixtures.run_cli_result(cmd[0], *cmd[1:])
        assert not r.timed_out and r.returncode != 0, f"{label}/{subcmd} unexpectedly passed"
        assert "bytes do not match" in r.stdout + r.stderr, (label, r.stdout, r.stderr)

    # a genuine expansion manifest must exist for the packet consumer path
    fixtures.run_cli("classic_acceptance_sampling.py", "expand",
                     "--sample-manifest", str(sm_path),
                     "--decision-report", str(real_path),
                     "--primary", str(primary), "--second", str(second),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(r1))
    reordered = _json.dumps(
        {k: report[k] for k in reversed(list(report.keys()))},
        indent=2, ensure_ascii=False).encode("utf-8")
    cases = {
        "crlf": canonical.replace(b"\n", b"\r\n"),
        "trailing_ws": canonical + b"\n",
        "reordered": reordered,
        "dup_key": canonical.replace(b'"verdict": "EXPAND"',
                                     b'"verdict": "ACCEPT", "verdict": "EXPAND"', 1),
    }
    for label, payload in cases.items():
        expect_reject(label, payload, "packet")
        expect_reject(label, payload, "expand")


def _r2_primary_covering_expansion(sm, exp, sm_path, exp_path, chman, out_path):
    # Build an all-PASS round-2 primary that covers BOTH the original sample
    # and every expansion new_id, binds the sample manifest SHA and the
    # expansion manifest raw-byte SHA. The chapter manifest maps every
    # sanmingtonghui id to its source chapter (expansion new_ids carry the
    # smth_ prefix, not the tiny_ prefix, so the chapter cannot be parsed from
    # the id alone).
    chapter_of = {}
    for ch in chman["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]
    items = []

    def add(book, item_type, iid):
        sc = chapter_of.get(iid, 1) if book == "sanmingtonghui" else 1
        items.append({"item": {"book": book, "type": item_type, "id": iid,
                               "source_chapter": sc},
                      "verdict": "PASS", "findings": []})

    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    add(book, item_type, iid)
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            add("sanmingtonghui", item_type, iid)
    for book, types in exp["expansions"].items():
        for item_type, strata in types.items():
            for info in strata.values():
                for iid in info["new_ids"]:
                    add(book, item_type, iid)
    primary = {"schema_version": "1.0", "kind": "primary_review_package",
               "sample_manifest_sha256": fixtures.sha256_file(sm_path),
               "expansion_manifests_sha256": [fixtures.sha256_file(exp_path)],
               "items": items, "overall_stats": {}, "zero_output_report": [],
               "reviewer_list": ["e2e-r1"]}
    fixtures.write_json(out_path, primary)
    return out_path


def test_e2e_validate_primary_expansion_genuine_then_tamper(big):
    # P0/F19: validate-primary runs the SAME producing-evidence authorization
    # chain as decide/finalize. Genuine path: a real R1 EXPAND bundle -> genuine
    # expansion -> a round-2 primary that covers the expansion and binds its
    # SHA -> validate-primary exits 0. Then the SAME expansion body is hand-
    # forged (a new_id swapped) while keeping the genuine producing report;
    # validate-primary must reject via the reconstruct-and-compare gate. This
    # proves expansion validation is actually exercised, not just earlier
    # flag/evidence gates.
    import copy
    base, data, chman_path = big
    r1 = base / "run_vp_exp"
    sm_path = _sample(big, "run_vp_exp")
    sm = fixtures.read_json(sm_path)
    verdicts = {}
    for s, n in (("1", 4), ("5", 6), ("6", 5)):
        for iid in sm["samples"]["sanmingtonghui"]["rule"][s][:n]:
            verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    packet = _packet(big, r1, sm_path)
    primary = fixtures.make_primary(packet, r1 / "primary_review_package_v1.json", verdicts)
    second = fixtures.make_second(primary, r1 / "second_review_receipt_v1.json")
    report = _decide(big, r1, primary, sm_path, second=second)
    assert report["verdict"] == "EXPAND"
    report_path = r1 / "decision_report_v1.json"
    fixtures.run_cli("classic_acceptance_sampling.py", "expand",
                     "--sample-manifest", str(sm_path),
                     "--decision-report", str(report_path),
                     "--primary", str(primary), "--second", str(second),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(r1))
    exp_path = r1 / "expansion_manifest_v1.json"
    exp = fixtures.read_json(exp_path)
    chman = fixtures.read_json(chman_path)
    r2_primary = _r2_primary_covering_expansion(
        sm, exp, sm_path, exp_path, chman, r1 / "r2_primary.json")
    common = [sys.executable, str(fixtures.SCRIPTS / "classic_acceptance_review.py"),
              "validate-primary", "--primary", str(r2_primary),
              "--sample-manifest", str(sm_path), "--chapter-manifest", str(chman_path),
              "--data-root", str(data),
              "--expansion-manifest", None,
              "--decision-report", str(report_path),
              "--producing-primary", str(primary),
              "--producing-second", str(second)]
    # genuine expansion -> exit 0
    ok_cmd = list(common)
    ok_cmd[ok_cmd.index(None)] = str(exp_path)
    ok = fixtures.run_argv_result(ok_cmd)
    assert not ok.timed_out and ok.returncode == 0, ok.stdout + ok.stderr
    assert "primary review package OK" in ok.stdout
    # tampered expansion (swap a new_id for an unsampled id) -> rejected by
    # reconstruct-and-compare; the producing report remains genuine, so the
    # failure is proven to come from expansion body validation.
    forged = copy.deepcopy(exp)
    strata = forged["expansions"]["sanmingtonghui"]["rule"]
    target_key = next(k for k, info in strata.items() if info["new_ids"])
    swapped = strata[target_key]["new_ids"][0]
    strata[target_key]["new_ids"][0] = "smth_999_r999"
    forged_path = r1 / "forged_expansion.json"
    fixtures.write_json(forged_path, forged)
    bad_cmd = list(common)
    bad_cmd[bad_cmd.index(None)] = str(forged_path)
    bad = fixtures.run_argv_result(bad_cmd)
    assert not bad.timed_out and bad.returncode != 0
    assert "does not match the manifest reconstructed" in (bad.stdout + bad.stderr)
    assert swapped != "smth_999_r999"


def test_e2e_integrity_reject(big):
    base, data, chman_path = big
    for name, rel in (("raw", f"{fixtures.FAKE_SNAP}/extracted/raw_025.txt"),
                      ("drift", "knowledge_base/classic_texts/qiongtongbaojian/quarantine_rules.jsonl")):
        copy = fixtures.tmp_dir(f"acceptance_e2e_integrity_{name}")
        shutil.copytree(data, copy / "data")
        (copy / "data" / rel).unlink()
        run = copy / "run"
        run.mkdir(parents=True, exist_ok=True)
        fixtures.run_cli("classic_acceptance_sampling.py", "sample",
                         "--chapter-manifest", str(chman_path),
                         "--data-root", str(copy / "data"), "--out", str(run))
        sm_path = run / "sample_manifest_v1.json"
        args = ["classic_acceptance_review.py", "packet", "--sample-manifest", str(sm_path),
                "--chapter-manifest", str(chman_path), "--data-root", str(copy / "data"),
                "--out", str(run)]
        fixtures.run_cli(*args)
        primary = fixtures.make_primary(run / "review_packet_v1.json",
                                        run / "primary_review_package_v1.json")
        report = _decide_paths(run, primary, sm_path, chman_path, copy / "data")
        assert report["verdict"] == "REJECT"
        assert report["fired_rules"] == ["INTEGRITY"]
        assert report["integrity"]["source_missing_chapters"] == ([25] if name == "raw" else [])
        assert report["integrity"]["missing_drift_files"] == (
            [] if name == "raw" else
            ["knowledge_base/classic_texts/qiongtongbaojian/quarantine_rules.jsonl"])
        fixtures.rmtree_force(copy)


def _decide_paths(run, primary, sm_path, chman_path, data_root):
    fixtures.run_cli("classic_acceptance_review.py", "decide", "--primary", str(primary),
                     "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data_root), "--out", str(run))
    return fixtures.read_json(run / "decision_report_v1.json")
```

- [ ] **Step 3: 运行测试确认通过**

Run: `python -m pytest tests/test_classic_acceptance_e2e.py -q`
Expected: 12 passed

- [ ] **Step 4: 全量回归**

Run: `python -m pytest tests/test_classic_acceptance_sampling.py tests/test_classic_acceptance_review.py tests/test_classic_acceptance_e2e.py tests/test_generate_acceptance_manifests.py -q`
Expected: 全部通过（冻结链测试不受影响）

- [ ] **Step 5: Commit**

```bash
git add tests/classic_acceptance_fixtures.py tests/test_classic_acceptance_e2e.py
git commit -m "test(acceptance): fake-data e2e (609+382, expand, fail-closed, F3)"
```

---

## 附：CLI 速查（实现完成后真实运行的入口）

```powershell
# 1) 初始抽样（生产模式自动跑冻结链 --check，约 1 分钟；--identity-manifest 不需要，
#    生产模式从仓库固定路径读取冻结 chapter/identity manifest 并校验；产物在 .tmp/）
python scripts/classic_acceptance_sampling.py sample `
  --chapter-manifest docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json `
  --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 `
  --out .tmp/classic_acceptance_run/r1

# 2) 审核包
python scripts/classic_acceptance_review.py packet `
  --sample-manifest .tmp/classic_acceptance_run/r1/sample_manifest_v1.json `
  --chapter-manifest docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json `
  --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 `
  --out .tmp/classic_acceptance_run/r1

# 3) 人工填写 primary_review_package_v1.json 后校验
#    （与其它子命令同走 F18 冻结/数据源锁；--chapter-manifest 核对三命通会 source_chapter。
#     携带 expansion 时与 decide/finalize 同走 producing-evidence 授权链：
#     最多一个 expansion，强制 R1 证据包，重算 producing report 并字节比对）
python scripts/classic_acceptance_review.py validate-primary `
  --primary <path> --sample-manifest <path> --chapter-manifest <path> `
  (--candidate-commit <sha> | --data-root <dir>) `
  [--expansion-manifest <path> --decision-report <r1-report> `
   --producing-primary <r1-primary> [--producing-second <r1-second>] `
   [--producing-arbitration <r1-arb>]]

# 4) 二审/仲裁回执 + 校验（F18 冻结/数据源锁：先锁定再读取；fake/production 二选一）
python scripts/classic_acceptance_review.py validate-second --second <path> --primary <path> --data-root <dir>
python scripts/classic_acceptance_review.py validate-arbitration --arbitration <path> --primary <path> --second <path> --data-root <dir>
#    生产模式（与其它子命令一致）：
python scripts/classic_acceptance_review.py validate-second --second <path> --primary <path> `
  --chapter-manifest docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json `
  --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636
python scripts/classic_acceptance_review.py validate-arbitration --arbitration <path> --primary <path> --second <path> `
  --chapter-manifest docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json `
  --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636

# 5) 判定（首轮或扩样后重判；扩样后必须携带 R1 完整证据包重算 producing report）
python scripts/classic_acceptance_review.py decide `
  --primary <path> [--second <path>] [--arbitration <path>] `
  --sample-manifest <path> `
  [--expansion-manifest <path> --decision-report <r1-report> `
   --producing-primary <r1-primary> [--producing-second <r1-second>] `
   [--producing-arbitration <r1-arb>]] `
  --chapter-manifest docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json `
  --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 `
  --out <run-dir>

# 6) 扩样（report 必须由 decide 产生且 verdict == EXPAND；复用 validate_decision_inputs
#    重算判定并字节比对，含 F22 回执门禁，不信任 report 字段）
python scripts/classic_acceptance_sampling.py expand `
  --sample-manifest <path> --decision-report <path> --primary <path> `
  [--second <path>] [--arbitration <path>] `
  --chapter-manifest docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json `
  --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 `
  --out <run-dir>

# 7) 终局（finalize 重走完整链：冻结门禁→sample→扩样授权证据→validate_decision_inputs
#    重算→磁盘 report 原始字节全等→terminal verdict；test_only 产物被拒绝）
python scripts/classic_acceptance_review.py finalize `
  --decision-report <path> --primary <path> [--second <path>] [--arbitration <path>] `
  --sample-manifest <path> --chapter-manifest <path> `
  [--expansion-manifest <path> --decision-report-r1 <r1-report> `
   --producing-primary <r1-primary> [--producing-second <r1-second>] `
   [--producing-arbitration <r1-arb>]] `
  --candidate-commit <sha> --out <run-dir>
```

> 真实运行完成后**不**自动做 audit commit / annotated tag / 远端发布——那些属于 §8.3 发布链与正式门禁前置条件，维持 BLOCKED，仅当最终 verdict 为 `ACCEPT` 且逐项另行批准后执行。fake smoke（`--data-root`）产物全部带 `test_only=true`，`finalize` 拒绝收尾，不能进入真实验收。
