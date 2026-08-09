# Phase 6 6D v2：限制性时间上下文注入设计

**日期：** 2026-08-08
**状态：** 修订版 v3（已过独立核验：NEEDS_REVISION 6 处已修订），待确认
**修订历史：** v1（草案）-> v2（补 off 复用决策、hard_cap 核算、成功标准单位）-> v3（独立核验修订：P1-1 产物目录两段式、P1-2 off 校验对象修正、P1-3 版本常量 Task 0b、P2-1 成功标准拆分、P2-2 AB/BA 语义澄清）
**适用范围：** Phase 6 6D v2 时间定位题的「限制性注入」对照实验
**前置依赖：** 6D v1 归档（verdict=`NON_INFERIOR`，commit 含 evidence）+ 6D v1 离线根因分析（11/11 regressed 由干支关系引导）

---

## 1. 背景与决策

### 1.1 6D v1 NON_INFERIOR 的证据指向

6D v1 真实 paired dev（2026-08-08，`deepseek-v4-flash` non-thinking，T=0）已归档，verdict=`NON_INFERIOR`：

| 指标 | 值 |
|---|---|
| off（无时间上下文）准确率 | 20.43%（19/93） |
| on（完整时间上下文）准确率 | 19.35%（18/93） |
| paired 改善 / 退化 / 相同 | 10 / 11 / 72 |
| paired 净变化 | **-1** |

即完整确定性时间上下文注入**没有净提升，反而微弱负向**。

### 1.2 离线根因分析（决定 6D-v2 方向）

对 11 道 regressed 题（off 正确、on 错误）的离线逐题分析：

| 事实 | 比例 | 含义 |
|---|---|---|
| 结论处出现关系关键词（刑/冲/合/害/克/生/伏吟/驿马/桃花） | 11/11 | 模型用它论证错误选项 |
| 是 `ROUTED_WITH_TARGETS`（注入了完整 `option_liunian` 关系） | 11/11 | 关系注入是带偏来源 |
| off 臂答对但也自行做了流年分析（无注入关系数据） | 11/11 | 模型本具备流年推理 |

**根因判定**：不是「解读漂移」（模型对注入数据的解读是忠实的），而是「注入过载」——预计算的流年干支关系被模型当作**强导向信号**，覆盖了它原本基于命局全局的更稳判断。

### 1.3 决策

6D-v2 采用**限制性注入**（方案 A）：仍注入命局 + 大运 + 年份干支 + 十神，但**省略目标流年的干支作用关系**（六冲/六合/三合/六害/三刑、天干生克）。

---

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 将 `on_limited` 注入固化为独立实验臂 `b1a_time_on_limited` | `--time-context-injection on_limited` 输出不含地支/天干关系 |
| G2 | 独立 6D-v2 orchestrator 执行 `off vs on_limited` paired dev | 预声明 temporal-routed 题的 off/on_limited paired gate |
| G3 | 验证限制性注入能否逆转 6D v1 的 regressed 退化 | paired_delta（off→on_limited）相对 6D v1 的 -1 净变化是否改善 |
| G4 | 与 6D v1 证据完全隔离 | 独立目录、独立 run_id、独立 arm，不污染 6D v1 归档 |
| G5 | 为「时间注入方向去留」提供依据 | 若 on_limited 仍 ≤ off，关闭 6D，启动 6C |

### 2.2 非目标

- 不改动 6D v1 已归档 run / gate / receipt / evidence pack（`docs/phase6/6d/` 冻结）
- 不重跑 6D v1 的 `b1a_time_on` 臂
- 不加动态紫微流年
- 不做 6C
- 不用 dual 为实验臂
- 6D-v2 无 reuse/final 阶段，只有单阶段 dev

---

## 3. 注入机制与实验臂设计

### 3.1 注入差异（off vs on vs on_limited）

以 regressed 案例 `female_19831028_P004-Q17`（婚姻年份，targets=2003/2005/2007/2009）为例：

| 注入 | 【目标流年详析】内容 |
|---|---|
| off | 无时间上下文段 |
| on（6D v1，带偏） | `2003年：癸未 十神：偏财 地支关系：三合、刑、冲、刑 天干关系：己克癸` |
| **on_limited（6D v2）** | `2003年：癸未 十神：偏财` |

on_limited 保留：命局结构 + 大运排布 + 年份干支 + 十神。省略：地支关系（六冲/六合/三合/六害/三刑）、天干关系（生克）。

### 3.2 Attempt Identity

runner 的 `build_attempt_key`（run_benchmark.py:55）第 3 位 = `arm`。off 与 on_limited 必须用不同 arm。

| 条件 | arm 值 | profile | method | time_context_injection |
|---|---|---|---|---|
| off | `b1a_time_off` | `baziqa_xjz_reasoned` | `direct_choice` | `off` |
| on_limited | `b1a_time_on_limited` | `baziqa_xjz_reasoned` | `direct_choice` | `on_limited` |

两个 arm 共用 `ziwei_arm=none`（single B1-a′ 基线）。

**6D-v2 必须保证 `b1a_time_on_limited` ≠ `b1a_time_on`**，确保 attempt key 可区分、6D-v2 不误续 6D v1 run。

### 3.3 注入实现（runner/formatter 层）

以下能力**已实现并通过测试**（本轮落地），6D-v2 直接复用：

- `format_temporal_context(ctx, include_relations=False)`：省略干支作用关系（`chart_context.py`）
- `render_reasoned_context(..., time_context_injection="on_limited", ...)`：`on_limited` 自动裁剪关系（`chart_context.py`）
- `run_benchmark.py --time-context-injection {off,on,on_limited}`（CLI choices 已含 on_limited）
- `compute_detail_provenance`：将 `on_limited` 视为真实注入（计算 sha256）

### 3.4 实施前的 runner 改动点（必须补齐，否则 fail-closed 拦截）

**`_REASONED_ARM_MAP`（run_benchmark.py:83-91）当前缺少 `b1a_time_on_limited`。**

现有映射：
```python
_REASONED_ARM_MAP = {
    "b1a_prime": "none", "b1b": "only", "b1c": "combined",
    "b2b": "ziwei_mini", "b2c": "sequential",
    "b1a_time_off": "none", "b1a_time_on": "none",
}
```

runner 的 reasoned fail-closed 映射（run_benchmark.py:1814-1837）要求 `args.arm in _REASONED_ARM_MAP`。**若 6D-v2 传 `b1a_time_on_limited` 而未加映射，将触发 `SystemExit(2) BLOCKED`。**

**必须新增**：
```python
"b1a_time_on_limited": "none",
```

这是 6D-v2 实施的第一项 runner 改动，需在实施计划中列为前置 Task，并补充测试验证 `b1a_time_on_limited` + `ziwei_arm=none` 通过 fail-closed。

---

## 4. 独立 6D-v2 实验链

### 4.1 独立性约束（与 6D v1 的关系）

| 维度 | 6D v1（冻结，不动） | 6D v2（新建） |
|---|---|---|
| orchestrator | `phase6_6d_orchestrator.py` | `phase6_6d_v2_orchestrator.py`（新建） |
| 目录 | `docs/phase6/6d/` | `docs/phase6/6d-v2/` |
| run_id 前缀 | `phase6-6d-v1-` | `phase6-6d-v2-` |
| 实验臂 | `b1a_time_off` + `b1a_time_on` | `b1a_time_off` + `b1a_time_on_limited` |
| experiment_conditions | `("off","on")` | `("off","on_limited")` |
| gate | off vs on | off vs on_limited |

**决策**：新建独立 orchestrator，而非参数化复用 6D v1。理由：(1) 6D v1 的 gate/receipt/completeness 大量 hardcode `b1a_time_on`（如 `compute_6d_gate`、`_check_completeness`、报告聚合），改造会引入回归风险；(2) 独立文件保证 6D v1 证据链不可变；(3) 可复用 6D v1 的 schedule/ledger/merge/archive 架构模式。

### 4.1.1 off 臂数据复用决策

6D-v2 的 off 臂 `b1a_time_off` 与 6D v1 的 off 臂**同名、同配置**（同 profile/method/ziwei_arm/time_context_injection=off/同 frozen 参数）。

**决策：off 臂复用 6D v1 已归档的 `b1a_time_off` 数据，仅新跑 `b1a_time_on_limited` 臂。**

理由：
- 跨实验配对成立：同 case、同 repeat、同模型（deepseek-v4-flash non-thinking）、同温度（T=0），off 臂结果确定可复现
- 节省一半 API：只需跑 93 calls（on_limited），而非完整 186
- 6D v1 的 off 臂 93 条已通过完整性门（parsed 100%）

**约束（fail-closed）**：
- 6D-v2 的 on_limited 数据**必须**与 6D v1 的 off 数据在同一 `(case, repeat)` 上配对
- 6D-v2 gate 复用 off 数据时，必须校验 6D v1 归档 `dev_gate.json` / `run_context.json` 中的 `dataset_sha256_by_year` / `temporal_routed_cases_sha256` 与 6D-v2 冻结一致（否则配对无效）
- 若 6D v1 off 数据缺失或 SHA 漂移 → 回退为 off 臂也重跑（完整 186 calls）

**此决策使 6D-v2 的真实 API 预算为 93 calls（on_limited 臂）**，而非 §4.2 的完整 186。

**时间环境风险（需明确接受）**：off 臂数据是 6D v1 时期（2026-08-08）跑的，on_limited 臂在 6D-v2 时期（稍晚）新跑。两者实验环境时间不同。缓解：模型为确定性推理（`deepseek-v4-flash` non-thinking，T=0），理论上对时间顺序不敏感；且 6D v1 与 6D-v2 的 frozen 参数（provider/model/thinking/T/profile/method/dataset SHA）已冻结一致。此风险在 paired 对照中影响有限，但需在报告 provenance 中标注 off 来源时间。

### 4.2 Schedule（沿用 6D v1 按年度分组 + AB/BA paired 协议）

```text
N_2024 = 18（阶段一离线门冻结）
N_2025 = 13（阶段一离线门冻结）

2024: ceil(18/8) = 3 groups（8,8,2）
2025: ceil(13/8) = 2 groups（8,5）

每 slice scheduled_calls = 真实题数（8/5/2）
每 slice hard_cap = _compute_hard_cap(scheduled_calls)
  = scheduled + ceil(scheduled * 0.10 / 10) * 10
  例：8 → 8+10=18；5 → 5+10=15；2 → 2+10=12

**完整 2 臂 schedule 结构**（用于参考，off 臂数据由 6D v1 复用）：
  2024 g0 (8题): off+on_limited × 3 repeats，每 slice cap 18
  2024 g1 (8题): off+on_limited × 3 repeats，每 slice cap 18
  2024 g2 (2题): off+on_limited × 3 repeats，每 slice cap 12
  2025 g0 (8题): off+on_limited × 3 repeats，每 slice cap 18
  2025 g1 (5题): off+on_limited × 3 repeats，每 slice cap 15

full global scheduled = (18×2 + 13×2) × 3 = 186
full global hard_cap = 6 × (18+18+12+18+15) = 6 × 81 = 486
  （与 6D v1 的 BudgetLedger 默认 hard_cap=486 一致）

**实际执行 schedule（按 §4.1.1 off 复用决策）**：仅运行 `b1a_time_on_limited` 臂的 slice（off 臂 slice 不跑，数据来自 6D v1 归档）：
  实际执行 slice 数 = 5 groups × 1 condition(on_limited) × 3 repeats = 15 slices
  实际 global scheduled = 93（off 臂 93 由 6D v1 复用）
  实际 on_limited hard_cap = 3 × (18+18+12+18+15) = 3 × 81 = 243

**AB/BA 轮换与单臂执行的说明**：6D-v2 只跑 on_limited 臂（off 复用），故**没有条件间顺序可轮换**（off 已在过去跑完）。但 `group_abba_order` 字段会进入 `run_context`/receipt（v1 如此）。决策：**v2 保留该字段仅为与 v1 provenance 对齐（receipt/run_context 结构兼容），无实际调度语义**——它记录的是 6D v1 时期 off/on 轮换的 AB/BA 分配，6D-v2 不据此调度 on_limited。备选：从 v2 receipt 移除该字段（需同步改 `_FOUR_LAYER_PROVENANCE_FIELDS` 等校验），但为保持架构最小改动，v2 默认保留。

### 4.3 Attempt Identity 校验（fail-closed）

`check_completeness` 要求每个 `(year, repeat, case_id)` 恰有：
- 一条 `b1a_time_off/main`
- 一条 `b1a_time_on_limited/main`

**fail-closed 条件**（任一命中即拒绝）：
- 出现 `b1a_time_on/main`（6D v1 遗留产物）→ 拒绝
- 缺失 `b1a_time_on_limited` → 拒绝
- 出现重复 arm key → 拒绝

这保证 6D-v2 不会把 6D v1 的 on 臂数据误当 on_limited。

### 4.4 BudgetLedger

沿用 6D v1 的 BudgetLedger 语义（幂等 + fail-closed）：
- `global_hard_cap` 由 schedule 计算：full = 486（off+on_limited 完整），实际执行 = 243（仅 on_limited，off 复用）
- `record_slice_completed` 前检查 `total_attempted + actual > hard_cap` → 拒绝
- 所有重试计入 hard_cap（与 runner 源码一致）
- **off 臂不计入 6D-v2 的 BudgetLedger 消耗**（其 API 已在 6D v1 消耗并归档），但完整性门仍要求 off 数据存在且配对

### 4.5 6D-v2 Gate（五分支，on 臂改用 on_limited）

```text
# 层 2 基础设施门（BLOCKED 优先，早返回）
call_failed(off) > 0 或 call_failed(on_limited) > 0
  → BLOCKED
parser_rate_off < 0.85 或 parser_rate_on_limited < 0.85
  → BLOCKED

# 层 3 准确率 gate（仅基础设施门通过时）
on_limited_acc = on_limited_correct_total / (N × 3)
off_acc        = off_correct_total        / (N × 3)
paired_delta   = on_limited_acc - off_acc = sum(case_delta) / (N × 3)
min_case_delta = min(case_delta) / 3

PROMOTE:         paired_delta >= +0.05 and min_case_delta >= 0
REVIEW_REQUIRED: paired_delta >= +0.05 and min_case_delta <  0
NON_INFERIOR:   -0.02 <= paired_delta < +0.05
ROLLBACK:        paired_delta < -0.02
```

**关键公式修正**：`paired_delta` 分母为 `N × 3`（不含条件数 2），与 6D v1 的 v6 修正一致。

**决策语义**：
| verdict | 含义 | 后续 |
|---|---|---|
| PROMOTE | 限制性注入显著优于 off 且无单题回退 | 时间注入方向成立 |
| REVIEW_REQUIRED | 整体提升但存在单题回退 | 逐题复核 |
| NON_INFERIOR | 与 off 相当 | 6D 时间注入关闭，启动 6C |
| ROLLBACK | 有害 | 6D 时间注入关闭，启动 6C |

---

## 5. 评估与成功标准

### 5.1 主要对比

| 对比 | 口径 | 决策 |
|---|---|---|
| off → on_limited（6D-v2 主判） | paired_delta | 6D-v2 verdict |
| off → on（6D v1 归档基准） | -1 净退化 | 参照 |
| on_limited vs on（跨实验） | on_limited 是否优于 on | 「关系带偏」假设验证 |

### 5.2 关键问题

6D-v2 回答的核心：**限制性注入能否避免 6D v1 的 regressed 退化？**

### 5.3 成功标准

**单位说明**：`paired_delta` 为准确率差（题数 / N×3），6D v1 的 -1 净变化对应 paired_delta ≈ -1/93 ≈ -1.08pp。下表统一用 paired_delta（pp）对比。

| 结果 | 意义 | 后续 |
|---|---|---|
| paired_delta ≥ +0.05 且 min_case_delta ≥ 0 | PROMOTE | 时间注入 + 限制策略有效 |
| paired_delta > 0（相对 6D v1 的 -1.08pp 为正） | 限制性优于 off | 支持「限制注入有效」 |
| on_limited_acc > 19.35%（独立比较） | 限制性优于完整 on | 支持「关系带偏」假设（需单独验证，不蕴含于 paired_delta） |
| -1.08pp ≤ paired_delta < 0 | 限制性有改善但仍未超 off | 限制方向部分有效，可考虑更精确限制 |
| paired_delta < -1.08pp | 限制性比完整 on 更差 | 时间注入方向关闭，启动 6C |

**注**：`paired_delta > 0` 只证明 on_limited 优于 off，**不蕴含** on_limited 优于完整 on（后者需 `on_limited_acc > 19.35%` 的独立比较）。两结论分列，避免报告解读混淆。

---

## 6. 产物目录（两段式，与 6D v1 布局一致）

6D v1 的真实布局是两段式：**工作区 `runs/`**（运行期产物）+ **归档目录 `<archive_id>/`**（原子快照，不可变）。6D-v2 复用 v1 orchestrator 架构，产物布局沿用同款两段式，避免误导实施。

```text
docs/phase6/6d-v2/
  phase1_receipt.json            # 离线门 receipt（N=31 路由冻结）
  temporal_routed_cases.json     # 路由冻结清单（复用 6D v1 的 31 题）
  runs/<user_run_id>/            # 工作区（运行期，可 resume）
    run_context.json             # 运行上下文（SHA/experiment_id 校验）
    manifest.json                # run manifest
    {dev,gates}/                 # 阶段目录（dev 运行产物 + budget_ledger）
      budget_ledger.json
      schedule.json
      <slice_id>/...             # 每 slice：details.jsonl/events/manifest
      merged_details.jsonl
      merged_events.jsonl
      report.md
  <archive_id>/                  # 归档（原子快照，不可变）
    audit_index.json
    merged_details.jsonl
    merged_events.jsonl
    dev_gate.json                # 即 receipt
    report.md
    schedule.json
    slices/<slice_id>/...
    budget_ledger.json
```

**路径一致性**：`docs/phase6/6d-v2/` 与 `docs/phase6/6d/` 分离，避免同 arm/repeat/position/group 目录冲突。

**off 数据来源标注**：6D-v2 复用 6D v1 的 off 臂数据，其 provenance 来源为 `6d-v1:<archive_id>`，须在 `audit_index.json` 和 `report.md` 中显式标注。

---

## 7. 预算

按 §4.1.1 off 复用决策：

- **实际新增 API 预算 = on_limited 臂 93 calls**（off 臂 93 由 6D v1 归档复用，不再消耗 API）
- 实际 on_limited hard_cap = 243（schedule 计算）
- 若 off 复用校验失败 → 回退完整 186 calls / hard_cap 486
- 所有重试计入 hard_cap（与 runner `before_call` 源码一致）
- 阶段一（离线门）零 API

---

## 8. 两阶段评估流程

### 阶段一：离线门（零 API，先于真实 dev）

1. 验证 `temporal_routed_cases.json`（N=31）可用，n_routed ≥ 20
2. 验证 `on_limited` 注入不含地支/天干关系（`format_temporal_context(include_relations=False)`）
3. 验证 `b1a_time_on_limited` + `ziwei_arm=none` 通过 runner fail-closed（新增 arm 映射后）
4. 生成 `phase1_receipt.json`（PASS/BLOCKED）

### 阶段二：真实 paired dev（需用户明确批准 API）

1. **off 数据复用校验**：读取 6D v1 归档的 `dev_gate.json`（receipt）与 `run_context.json`，校验其中 `dataset_sha256_by_year` / `temporal_routed_cases_sha256` / frozen 参数与 6D-v2 冻结一致（detail 行内无这些字段，详见 Task 1）；并核对 off 臂 93 条 detail 完整且 parsed；若漂移 → 回退 off 臂重跑（完整 186）
2. 运行 `phase6_6d_v2_orchestrator.py run_dev`（仅 on_limited 臂 93 calls）
3. off（复用）+ on_limited（新跑）合并 → 完整性门 + 基础设施门 + 准确率 gate
4. 生成 `dev_gate.json` + `report.md` + 原子归档（含 provenance：off 来源 = `6d-v1:<run_id>`）

---

## 9. 风险与回退

| 风险 | 缓解 |
|---|---|
| `b1a_time_on_limited` 未加 `_REASONED_ARM_MAP` → fail-closed 拦截 | 实施 Task 0 明确列出，补测试 |
| off 复用数据 SHA 漂移（6D v1 dataset 被改） | 复用前校验 `dataset_sha256_by_year` / `temporal_routed_cases_sha256`，漂移则 off 重跑 |
| off 复用导致跨实验环境不一致 | 校验 6D v1 off 的 frozen 参数与 6D-v2 完全一致（provider/model/thinking/T/profile/method） |
| on_limited 引入新错误（缺关系无法判断） | 与 off 对照，若 ≤ off 则关闭 |
| 6D v1 的 `b1a_time_on` 产物残留 | 独立目录 + fail-closed completeness 拒绝 |
| 与 6D v1 目录冲突 | 独立 `docs/phase6/6d-v2/` |
| N 过小 | 阶段一若 N<20 阻断 |
| paired_delta 分母误除 2 | 冻结 N×3（沿用 6D v1 v6 修正） |
| on_limited 的 sha 溯源不准 | `compute_detail_provenance` 已含 on_limited |

回退：`--time-context-injection off`（默认），不修改 6D v1 归档。

---

## 10. 实施前置改动点清单（TDD）

### Task 0：runner 层 arm 映射（必须最先）

**改动**：`_REASONED_ARM_MAP` 新增 `"b1a_time_on_limited": "none"`（run_benchmark.py:83-91）

**测试（RED→GREEN）**：
```python
# 测试：b1a_time_on_limited + ziwei_arm=none 通过 reasoned fail-closed
# 测试：b1a_time_on_limited + ziwei_arm=only 拒绝 SystemExit(2)
```

**验证**：`--arm b1a_time_on_limited --ziwei-arm none --time-context-injection on_limited` 不触发 BLOCKED。

### Task 0b：版本常量改值（复制改造必改，易漏）

**改动**：`phase6_6d_v2_orchestrator.py` 两个模块级常量必须改为 `6d-v2`，否则 receipt/run_context 校验自相矛盾、且与 v1 provenance 混淆：
- `TEMPORAL_CONTEXT_VERSION = "6d-v1"` → `"6d-v2"`（源 v1 :42）
- `experiment_id = "6d"` → `"6d-v2"`（源 v1 :1120 audit, :1276 run_context）

**原因**：`check_6d_gate`（:851）对 receipt 强校验 `temporal_context_version == TEMPORAL_CONTEXT_VERSION`；`_prepare_run_context`（:1284）强校验 `context["experiment_id"] == "6d"`。若复制不改，6D-v2 的 receipt/run_context 会自相矛盾（写入 `6d-v1`/`6d` 却校验要求 `6d-v1`/`6d` 不成立或与 v1 混淆）。

**测试**：`test_phase6_6d_v2_orchestrator.py`：`TEMPORAL_CONTEXT_VERSION == "6d-v2"`、`experiment_id == "6d-v2"`、receipt/run_context 校验对 `6d-v1` 值拒绝。

### Task 1：off 数据复用校验器

**改动**：`phase6_6d_v2_orchestrator.py` 新增 `_verify_off_reuse()`——**读取 6D v1 归档的 `dev_gate.json`（receipt）和 `run_context.json`**，校验其 SHA / frozen 参数与 6D-v2 冻结一致：

> **注意**：off detail 行内**不含** `dataset_sha256_by_year` / `temporal_routed_cases_sha256`（行内只有 `time_context_sha256`、`mode`、`temporal_route_state`）。这些字段位于 v1 的 `run_context.json` 和 `dev_gate.json`（receipt），必须从那里读取比对。

校验项：
- `dataset_sha256_by_year` / `temporal_routed_cases_sha256` / `dataset_set_sha256` 与 6D-v2 冻结一致
- `temporal_context_version` 为 v1 值（`6d-v1`，证明 off 数据确属 6D v1 归档）
- frozen 参数（provider/model/thinking/T/profile/method）与 6D-v2 一致
- off 数据完整性（93 条 terminal，parsed 率 ≥ 0.85）
- 任一失败 → `SystemExit(2)`（fail-closed）

**测试**：`test_phase6_6d_v2_off_reuse.py`：SHA 一致通过、SHA 漂移拒绝、off 缺失拒绝、experiment_id 非 6d 拒绝。

### Task 2-N：独立 orchestrator

- `phase6_6d_v2_orchestrator.py`：复制 6D v1 架构，改 ARMS/conditions/arm 名/gate 聚合，on_limited 臂 schedule（93 calls / hard_cap 243）
- 测试 `test_phase6_6d_v2_*.py`：schedule/ledger/merge/gate/archive/CLI/off-reuse

---

## 11. 完成定义

1. 本设计文档进入 Git
2. `_REASONED_ARM_MAP` 含 `b1a_time_on_limited` → none，测试通过（Task 0）
3. `on_limited` 注入（`format_temporal_context(include_relations=False)`）输出不含关系，测试通过
4. 版本常量 `TEMPORAL_CONTEXT_VERSION="6d-v2"`、`experiment_id="6d-v2"`，receipt/run_context 校验对 v1 值拒绝（Task 0b）
5. off 复用校验器（`_verify_off_reuse`）从 v1 `dev_gate.json`/`run_context.json` 读取 SHA 比对，实现并通过测试（SHA 一致/漂移拒绝/缺失拒绝）（Task 1）
6. `phase6_6d_v2_orchestrator.py` 的 schedule（on_limited 93）/gate/receipt/report 契约确认
7. 独立产物目录 `docs/phase6/6d-v2/`（两段式布局）确认
8. gate 五分支 + 分母 N×3 + 阈值冻结确认
9. off 复用决策（§4.1.1）经评审确认后纳入
10. `group_abba_order` 仅 provenance 对齐、无调度语义（§4.2）确认

实施计划（Task 0/0b/1/2-N 详细）在本设计确认后单独编写。
