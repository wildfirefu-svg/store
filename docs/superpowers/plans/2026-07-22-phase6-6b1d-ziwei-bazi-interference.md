# Phase 6 6B1-D - 紫微斗数与子平八字的干扰机制探索：实施计划

**plan_id**: `phase6-6b1d-v2`
**状态**: `APPROVED`
**父设计**: 6B1 后续探索性研究（非原总设计 §7 的 6B2）
**前置结论**: 6B1 PROMOTE_CANDIDATE（Δ_dev=+7.08pp，worst_year=+4.17pp）
**阻塞语义**: 6B1 PROMOTE_CANDIDATE -> 6B1-D OK；本实验为**纯探索性**，结果不直接决定任何后续实验

---

## 重要声明

> **本实验不是原总设计中已批准的 6B2**（双流水线 + 来源盲化裁判）。
>
> 本实验是 **6B1 的深度探索（6B1 Deep Dive）**，旨在调查一个观测到的描述性结果：b1b 准确率数值上高于 b1c。本实验不作机制确认，所有结论均为探索性、描述性，不构成统计显著性宣称。

---

## 1. 实验目标

### 1.1 研究背景

6B1 观测到一个描述性结果：在全部 6 个 repeat 中，b1c（八字+紫微联合）与 b1b（仅紫微）的准确率差值为：

```
2024-R0:   0 pp
2024-R1: -15 pp
2024-R2:  +5 pp
2025-R0: -2.5 pp
2025-R1:   0 pp
2025-R2:   0 pp
```

均值为 -2.09pp，但主要由单个 repeat（2024-R1）驱动。这是一个**待复现的探索性观察**，不是已确认效应。

### 1.2 核心研究问题

> **在已有紫微斗数提示的条件下，追加子平八字框架是否稳定降低推理准确率？如果是，可能的驱动因素是什么？**

### 1.3 探索性维度（不作假设检验）

本实验不作预设假设的显著性检验，仅系统收集以下维度的描述性数据：

| 探索维度 | 干预方式 | 描述性解读方向 |
|---------|---------|-------------|
| **提示长度/内容** | b1b（完整紫微） vs b2b（精简紫微） | 若 b2b 数值更高，提示长度或字段简化可能相关 |
| **呈现结构** | b1c（并行呈现） vs b2c（顺序呈现） | 若 b2c 数值更高，结构组织可能相关 |
| **基线控制** | b1a'（同期八字基线） vs 历史 6B1 | 量化 provider/time drift 的量级 |

**注意**：b2b、b2c 均为复合干预（同时改变多个变量），不尝试分解单一因果因素。

---

## 2. 实验设计

### 2.1 五臂同期全程交错设计

所有臂在同一实验 run 中**全程交错**执行，控制 provider/time drift。不设执行层的 Stage A/B 分阶段。

| 实验臂 `--arm` | 渲染 `--ziwei-arm` | 上下文内容 | 角色 |
|---|---|---|---|
| **b1a_prime** | `none` | 身份头 + 八字（与 6B1 b1a' 字节等价） | **同期基线臂** |
| **b1b** | `only` | 身份头 + 完整紫微盘（与 6B1 b1b 字节等价） | **参照臂** |
| **b1c** | `combined` | 身份 + 八字 + 紫微（与 6B1 b1c 字节等价） | **复现臂** |
| **b2b** | `ziwei_mini` | 身份 + 精简紫微（命宫/身宫/主星，去除次位宫位） | **长度/内容探索** |
| **b2c** | `sequential` | 身份 + [八字段] + 显式分隔 + [紫微段] + 顺序推理指令 | **结构探索** |

### 2.2 字节等价性承诺（冻结）

- b1a'、b1b、b1c 的 prompt 输出必须与 6B1 逐字节等价
- 这是一个可测试的断言，单元测试将逐字节验证

### 2.3 分析分组（非执行分组）

报告中将结果分为两个**分析块**，但执行时不分阶段：

- **复现分析块**：b1a'、b1b、b1c 的结果，与 6B1 历史值比较
- **机制探索块**：b2b、b2c 与 b1b、b1c 的描述性比较

所有五臂数据在同一 run 中交错采集，避免时间漂移。

---

## 3. 调度与预算（冻结，数学自洽）

### 3.1 调度设计

采用 **5 组 × 5 臂 Latin square** 设计，每个 arm-year-repeat cell 拆成 5 组：

| 维度 | 冻结值 |
|---|---|
| 每 cell 拆组数 | 5 |
| 每 group size | 8 题（40 ÷ 5 = 8） |
| 调度 | 5×5 Latin square，position -> group -> arm 轮换 |
| 每 arm-year-repeat cell | 5 slices × 8 题 = 40 题 |
| 总 slices | 5 arms × 5 groups × 2 years × 3 repeats = **150 slices** |
| 总 scheduled | 150 × 8 = **1200 次调用** |

### 3.2 5×5 Latin Square

```
Position 0:  G0->b1a'  G1->b1b   G2->b1c   G3->b2b   G4->b2c
Position 1:  G0->b1c   G1->b2b   G2->b2c   G3->b1a'  G4->b1b
Position 2:  G0->b2b   G1->b2c   G2->b1a'  G3->b1b   G4->b1c
Position 3:  G0->b2c   G1->b1a'  G2->b1b   G3->b1c   G4->b2b
Position 4:  G0->b1b   G1->b1c   G2->b2b   G3->b2c   G4->b1a'
```

（每个 arm 在每个 position 出现且仅出现一次，每个 group 在每个 position 被每个 arm 处理且仅一次）

### 3.3 预算执行模型（动态 effective_cap，冻结）

总 scheduled = 1200，总 reserve = 120，全局 hard cap = 1320。

**架构约束**：orchestrator 只能在 slice 启动前和完成后更新 ledger，无法逐调用控制子进程。因此采用首次分配持久化的动态 cap 方案。

**设计原则（冻结）**：
1. 每个 slice 首次启动时分配 effective_cap = 10（8+2 reserve）
2. **分配值权威来源：`budget_ledger.json` 的 `allocated_cap_by_slice[slice_id]`**（不是 slice manifest）
3. orchestrator 通过 `--hard-cap effective_cap` 将分配值传给 runner
4. runner 创建的 manifest 中 `hard_cap` 字段是**交叉校验副本**，不是权威来源
5. resume 时同时验证：ledger 分配值 与 runner manifest hard_cap **必须一致**，否则 fail-closed
6. ledger 有分配但 runner 无产物时，允许使用原分配首跑
7. runner manifest 存在但 ledger 分配缺失时，fail-closed
8. slice 启动前检查全局剩余预算：`global_remaining = 1320 - cumulative_calls`
9. `effective_cap = min(10, global_remaining)`
10. 若 `effective_cap < 8` -> BLOCKED_BUDGET_EXHAUSTED，不启动
11. **resume 预算公式（冻结）**：`total_attempted + (effective_cap - already_attempted_for_slice) <= 1320`，启动前必须执行此检查

**重要声明（冻结）**：总 reserve 只有 120，不能保证 150 个 slice 都有完整 2 次重试。动态分配保证先启动的 slice 有重试空间，预算耗尽时优雅终止。**不声称"每个 slice 都至少有 2 次重试"**。

### 3.4 预算验证

- 总 scheduled = 5 × 5 × 2 × 3 × 8 = 1200 ✅
- 总 hard cap = 1200 + 120 reserve = 1320 ✅
- 每 cell scheduled = 5 × 8 = 40 ✅
- 每 slice 初始 local cap = 10 ✅
- 全局 ledger 上限 = 1320 ✅
- 分配值权威来源 = `budget_ledger.json`（非 slice manifest）✅
- runner manifest `hard_cap` = 交叉校验副本 ✅
- resume 预算公式 = `total_attempted + (effective_cap - already_attempted) <= 1320` ✅

---

## 4. 基础协议（冻结）

| 维度 | 冻结值 |
|---|---|
| 输出协议 | reasoned_choice（五臂统一） |
| 采样 | single@T=0 |
| 数据集 | 仅 2024/2025 enriched holdout，各 40 题（与 6B1 完全相同） |
| repeats | 3 |
| 调度 | 5×5 Latin square，全程交错，确定性串行 |
| chart_schema | **legacy_v0**（与 6B1 相同，非 approved_v1） |
| 全局 scheduled | 1200 |
| 全局 hard cap | 1320 |
| total slices | 150 |
| 每 slice size | 8 题 |

---

## 5. 统计方法（冻结，全描述性）

### 5.1 主要分析

1. **配对准确率差值**：
   - 比较单位：`year × question` 单元格（80 个独立单位）
   - 三个 repeat 视为同一题目的重复测量，取均值
   - 报告：b1c-b1b、b2b-b1b、b2c-b1c 的均值和全距

2. **配对 Bootstrap 95% CI**（仅描述，不作显著性判断）：
   - 聚类单位：`year × question`（80 个聚类）
   - 重采样：有放回地抽取 80 个聚类，所有 arm 的三个 repeat 同步抽取
   - Bootstrap seed：`6B1D_BOOTSTRAP_SEED = 42`（冻结）
   - Draw 数：10,000
   - CI 算法：百分位法（2.5%, 97.5%）
   - Invalid 处理：按 wrong 计入准确率，分母固定为 3（3 个 repeat）
   - Call_failed 处理：该 repeat 视为 wrong

3. **逐题一致性矩阵**：
   - 五臂两两之间的答案一致率（按 question 聚合）

### 5.2 题目标签（运行前冻结，盲化标注）

以下标签必须在运行前完成，写入独立 `labels.jsonl` 文件，记录 SHA-256，并将哈希加入 run manifest、resume fingerprint 和归档审计索引。**不得依据本次实验结果或 6B1 准确率事后分组**。

| 标签 | 定义（冻结） | 标注指南 |
|------|-------------|---------|
| `question_complexity` | 1=简单（单一维度判断），2=中等（双维度），3=复杂（三维度以上或反直觉） | 见附录 A |
| `ziwei_info_richness` | 1=紫微信息少，2=中等，3=紫微信息丰富 | 见附录 A |
| `bazi_info_richness` | 1=八字信息少，2=中等，3=八字信息丰富 | 见附录 A |

标注者不得接触 6B1 的准确率数据。标注由 2 名标注者独立完成，分歧由第 3 人裁决。

### 5.3 探索性分层分析

仅作描述性比较，不检验：
- 准确率差值按 `question_complexity` 分层
- 准确率差值按 `ziwei_info_richness` 分层
- 准确率差值按 `bazi_info_richness` 分层

---

## 6. 与 6B1 的关系

### 6.1 保持不变的部分
- 数据集（相同的 80 题 holdout）
- 模型（DeepSeek deepseek-chat）
- T=0 采样
- reasoned_choice 输出协议
- parser 逻辑
- **chart_schema = legacy_v0**（与 6B1 相同）
- b1a'、b1b、b1c 的 prompt 逐字节等价

### 6.2 新增的部分
- 2 个新实验臂（b2b, b2c）
- 运行前冻结的题目复杂度/信息丰富度标签（独立 labels.jsonl）
- 独立的 archive 目录（不污染 6B1）

### 6.3 预期资源
- 1200 次 API 调用
- 成本与运行时间为**粗估**：约 $20-30、4-6 小时；将由 smoke 的输入/输出 token 实测后更新
- 存储：独立归档，约 50MB 磁盘空间

---

## 7. 分析产出（全部描述性）

实验报告将包含：
1. 五臂准确率排序及两两差值（含 95% Bootstrap CI）
2. b1c-b1b 与 6B1 历史值的并排比较
3. 按复杂度/信息丰富度的分层描述
4. b2b/b2c 的定性案例检视（各 5 例）
5. parser rate 五臂对比
6. 输入 token 计数（五臂对比）
7. 输出长度分析

**不作**：
- 任何 p 值或"显著/不显著"的宣称
- 任何单一因果因素的确定结论
- 任何直接指导后续实验设计的"已确认"机制

---

## 8. 后续规划

无论结果如何，本实验完成后都不自动推进任何后续实验。所有结论均为探索性，供后续正式实验（如真正的 6B2）设计参考。

---

## 附录 A：题目标签标注指南

### A.1 question_complexity

- **1=简单**：题目仅要求单一维度判断（如"学历高低"）
- **2=中等**：题目要求双维度综合（如"事业+财运"）
- **3=复杂**：题目要求三维度以上或涉及反直觉判断（如"婚姻时机+配偶特征+感情稳定性"）

边界案例：若题目含多个子问但核心判断单一，记为 1。

**Preflight 分布检查（冻结）**：运行前输出三层样本数，任意一层 < 5 时自动跳过该层分层分析。

### A.2 ziwei_info_richness

（按真实 80 题分布冻结：命宫主星只可能为 0、1、2 颗）

- **1 = 少**：命宫主星数 = 0（空宫）
- **2 = 中**：命宫主星数 = 1
- **3 = 丰富**：命宫主星数 = 2

**Preflight 分布检查（冻结）**：
```python
# 运行前输出三层样本数
# - layer1 (0 星): 预期 ≈ 20 题
# - layer2 (1 星): 预期 ≈ 45 题
# - layer3 (2 星): 预期 ≈ 15 题
#
# 任意一层样本数 < 5 → 自动跳过该层的分层分析（不是实验失败）
# 仅保留样本量充足层的对比
```

**注意**：当前 normalized ziwei schema 不含"特殊格局"字段，故不作为判断依据。

### A.3 bazi_info_richness

- **1=少**：五行偏枯，无明显合冲
- **2=中等**：五行平衡，含 1-2 处合冲
- **3=丰富**：五行活跃，含 ≥ 3 处合冲或特殊神煞

**Preflight 分布检查（冻结）**：运行前输出三层样本数，任意一层 < 5 时自动跳过该层分层分析。

---

**草稿待审核**。下一步：确认调度与预算自洽 -> 实现代码骨架 -> 预审核 -> 正式执行。
