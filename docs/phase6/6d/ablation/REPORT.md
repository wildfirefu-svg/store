# Phase 6D 消融实验汇总报告

> **日期**: 2026-08-09
> **分支**: main (merge 9a393d5 + 3258170 + f59e42f)
> **模型**: deepseek-v4-flash
> **数据集**: baziqa_contest8_{2024,2025}_holdout_enriched.jsonl

---

## 1. 执行摘要

本报告汇总两轮实验的完整结果：

1. **6D v1 时间上下文注入实验**（r1）：测试预计算大运/流年信息注入 prompt 是否提升准确率
2. **3 因子消融实验**：测试 permutation（选项打乱）、thinking 模式、以及两者组合对准确率的影响

**核心结论**：

- 6D 时间上下文注入：**NON_INFERIOR**，不提升准确率
- Permutation（选项打乱）：**有害**，准确率下降 10pp
- Thinking 模式：**有害**，准确率下降 2.5pp
- 两者组合：**最差**，准确率下降 12.5pp，低于随机基线
- **基线策略（无增强）是最优解**：32.5% 准确率

---

## 2. 实验背景

### 2.1 6D v1 时间上下文注入

Phase 6D 测试假设：将八字时间上下文（大运起止、流年干支、目标年份）预计算并注入 prompt，可以帮助模型更准确地回答时间相关问题。

- **OFF 臂**：标准 prompt，不含时间上下文
- **ON 臂**：prompt 中注入预计算的时间上下文
- **routed cases**：31 个含明确目标年份的 case
- **repeat**：3 次（paired design）
- **总调用**：186 次（31 cases × 3 repeats × 2 arms）

### 2.2 3 因子消融实验

基于 6D 实验中发现的"模型准确率低于 25% 随机基线"现象，设计 3 因子消融实验：

| 因子 | 水平 | 实现 |
|---|---|---|
| Permutation | on / off | `--shuffle-options --shuffle-seed 42` |
| Thinking | auto / disabled | `--thinking-mode auto`（使用 deepseek-reasoner）|
| RAG | on / off | `--rag`（本轮未测试）|

---

## 3. 实验结果

### 3.1 6D v1 时间上下文注入（r1）

**数据集**：31 routed cases × 3 repeats = 93 calls/arm

| 臂 | 正确数 | 准确率 |
|---|---|---|
| OFF（无时间上下文） | 19/93 | 20.43% |
| ON（含时间上下文） | 18/93 | 19.35% |
| paired_delta | -1 | -1.08pp |

按年度拆分：

| 年度 | OFF | ON | Delta |
|---|---|---|---|
| 2024 | 11/54 = 20.4% | 10/54 = 18.5% | -1.85pp |
| 2025 | 8/39 = 20.5% | 8/39 = 20.5% | 0.00pp |

**结论**：NON_INFERIOR（delta 在 -2pp 阈值内）。时间上下文注入不提升准确率。

### 3.2 3 因子消融实验

**数据集**：2024 holdout，40 cases，1 repeat

| 组 | Permutation | Thinking | 准确率 | vs 基线 | 安全分 |
|---|---|---|---|---|---|
| **基线** | off | disabled | **32.5%** (13/40) | - | 87.5% |
| C | off | auto | 30.0% (12/40) | -2.5pp | 98.8% |
| D | on | disabled | 22.5% (9/40) | -10.0pp | 90.0% |
| A | on | auto | 20.0% (8/40) | -12.5pp | 97.5% |

**Group D 完整 80-case 结果**（2024 + 2025）：

| 年度 | 正确数 | 准确率 |
|---|---|---|
| 2024 | 9/40 | 22.5% |
| 2025 | 12/40 | 30.0% |
| 总计 | 21/80 | 26.25% |

---

## 4. 分析

### 4.1 Permutation 为何有害

Permutation 导致准确率从 32.5% 降至 22.5%（-10pp）。原因分析：

1. **位置模式依赖**：模型在训练中学到了选项位置相关的统计规律（如"最长选项通常是正确答案"）。打乱选项后，这些规律失效。

2. **Unshuffle 机制验证**：代码审查确认 `unshuffle_predicted_answer` 使用 reverse map 正确还原标签，排除实现 bug。

3. **选项语义关联**：原始选项可能按逻辑顺序排列（如时间先后、程度递进），打乱后增加了模型理解难度。

### 4.2 Thinking 模式为何有害

Thinking 模式导致准确率从 32.5% 降至 30.0%（-2.5pp）。原因分析：

1. **过度推理**：对于简单问题，thinking 模式让模型过度分析，偏离直觉判断。模型在 reasoning_content 中反复权衡，最终选择了更"复杂"但错误的答案。

2. **资源消耗**：thinking 模式每 call 消耗 13K+ reasoning tokens，耗时 3-5 分钟/call（vs 基线 5 秒/call），但准确率不升反降。

3. **Token 限制**：初始实验中 max_tokens=16384 不足以容纳完整推理 + 最终答案（finish_reason=length），修复后 max_tokens=65536 解决了截断问题，但准确率仍低于基线。

### 4.3 组合效应

Permutation + Thinking 组合（Group A）准确率 20.0%，低于随机基线 25%。两者叠加产生负面协同效应：

- Permutation 破坏了模型的位置线索
- Thinking 模式让模型在缺失线索的情况下过度推理
- 两者叠加导致模型系统性选错

### 4.4 6D routed cases vs 全 holdout 对比

| 数据集 | 基线准确率 | 说明 |
|---|---|---|
| 6D routed cases (31×3) | 20.43% | 仅含时间相关问题（最难） |
| 2024 full holdout (40) | 32.5% | 含所有题型（混合难度） |

6D 实验的低准确率（~20%）是因为只测试了最难的 routed cases。在完整 holdout 上，模型基线准确率为 32.5%，超过 25% 随机基线，说明模型具备一定的八字命理知识。

### 4.5 Per-case 分析（6D r1，31 routed cases）

| 类别 | 数量 | 说明 |
|---|---|---|
| 不变（delta=0） | 24 | 多数 0/3 正确（知识瓶颈） |
| 变好（delta>0） | 3 | +1, +2, +2 |
| 变差（delta<0） | 4 | -1, -1, -2, -2 |
| 净 delta | -1 | 与整体 -1.08pp 一致 |

7 个非零 delta case 中，变好与变差几乎对冲（3 vs 4），说明时间上下文对个别 case 有帮助但对另一些造成干扰，无净收益。

---

## 5. 关键发现

1. **模型基线 32.5% 超过随机**：deepseek-v4-flash 在八字 MCQ 上具备一定能力，不需要额外增强。

2. **Permutation 有害（-10pp）**：打乱选项破坏模型依赖的位置模式，是最大的负面因子。

3. **Thinking 模式有害（-2.5pp）**：过度推理对简单判断有害无益，且资源消耗极大。

4. **时间上下文注入无收益**：6D 实验确认预计算大运/流年信息不提升准确率。

5. **最难的 routed cases 准确率 ~20%**：31 个时间相关 case 是知识瓶颈区，24/31 全错，需要领域知识补充而非推理增强。

---

## 6. 建议

### 短期（不重跑 API）

- **保持基线策略**：`direct_choice + thinking=disabled + no shuffle` 已是最优
- **放弃 permutation**：unshuffle 机制正确但打乱本身有害
- **放弃 thinking 模式**：过度推理降低准确率且资源消耗过大

### 中期（需要 API 调用）

| 优先级 | 实验 | 预期 | 成本 |
|---|---|---|---|
| P1 | RAG alone（无 perm, 无 thinking） | +3-5pp | 40 calls, ~7 min |
| P2 | Few-shot 示例注入 | +3-5pp | 40 calls, ~7 min |
| P3 | 结构化 JSON 命盘格式 | +2-3pp | 40 calls, ~7 min |

### 长期

- **错误分析**：对基线答错的 27 个 case 逐题分析，区分"知识缺口"和"推理错误"
- **知识库扩充**：针对错误率最高的领域（如 career, study）补充命理规则
- **模型升级**：测试 deepseek-v4-pro（更强基础模型）是否在不启用 thinking 的情况下有更好表现

---

## 7. 附录

### 7.1 实验配置

| 参数 | 值 |
|---|---|
| provider | deepseek |
| model | deepseek-v4-flash |
| profile | baziqa_xjz_reasoned |
| method | direct_choice |
| arm | b1a_prime |
| ziwei_arm | none |
| temperature | 0.0（disabled）/ 删除（auto） |
| max_tokens | 16384（disabled）/ 65536（auto） |

### 7.2 Run IDs

| 实验 | Run ID | 数据集 | Cases | 准确率 |
|---|---|---|---|---|
| 6D r1 OFF | (archived) | routed × 3 | 93 | 20.43% |
| 6D r1 ON | (archived) | routed × 3 | 93 | 19.35% |
| 基线 2024 | 29a7d183 | 2024 holdout | 40 | 32.5% |
| Group D (80) | 4d2bfdd1 | 2024+2025 holdout | 80 | 26.25% |
| Group C (2024) | 4135389d | 2024 holdout | 40 | 30.0% |
| Group A (2024) | 087626ec | 2024 holdout | 40 | 20.0% |

### 7.3 代码变更

| Commit | 说明 |
|---|---|
| 3258170 | 支持 thinking_mode=auto（deepseek-reasoner） |
| f59e42f | max_tokens=65536 + reasoning_content fallback |

### 7.4 6D r1 实验归档位置

```
docs/phase6/6d/runs/phase6-6d-v1-20260808-r1/
  ├── dev/           # 186 次 API 调用详情
  ├── gates/         # dev_gate.json（NON_INFERIOR 判定）
  ├── run_context.json
  ├── report.md
  └── errata.md
```

---

*Generated by Phase 6D Ablation Experiment Pipeline*
