# Phase 6D 后续独立探索：Permutation × Model Protocol 2×2 Ablation

> **日期**: 2026-08-09
> **状态**: NEEDS_REVISION / 探索性证据可用
> **性质**: 独立探索性实验，与 6D-v2 无关
> **模型**: deepseek-v4-flash / deepseek-reasoner
> **数据集**: baziqa_contest8_2024_holdout_enriched.jsonl（40 cases，单次运行）

---

## 1. 摘要

本报告记录一次独立的 2×2 消融探索，测试两个因子对 BaziQA 选择题准确率的影响：

- **Permutation**（选项打乱）：on / off
- **Model Protocol**（模型协议）：deepseek-v4-flash（disabled）/ deepseek-reasoner（auto）

6D-v1 实验数据作为参照组列入附录，不构成本实验的阶段。

**本次单次运行的观测结果**：

- 基线（perm=off, flash=disabled）：32.5%
- perm=off, reasoner=auto：30.0%
- perm=on, flash=disabled：22.5%
- perm=on, reasoner=auto：20.0%

以上数字与各 `run_*.md` 一致，可作为探索性结果。单次 40 题不足以断言因果关系或全局最优。

---

## 2. 实验设计

### 2.1 因子与水平

| 因子 | off 水平 | on 水平 | 实现方式 |
|---|---|---|---|
| Permutation | 原始选项顺序 | `--shuffle-options --shuffle-seed 42` | `shuffle_options.py` 随机重排 A/B/C/D |
| Model Protocol | `deepseek-v4-flash` + `thinking=disabled` | `deepseek-reasoner` + `thinking=auto` | API 层切换 model name + max_tokens |

**注意**：`thinking=auto` 在代码中实际将 API 请求的 model 字段从 `deepseek-v4-flash` 切换为 `deepseek-reasoner`。因此 "thinking on/off" 本质上是**模型协议对比**（flash vs reasoner），不是同一模型内部的纯 thinking 开关。

### 2.2 2×2 设计矩阵

| 组名 | Permutation | Model Protocol | Run ID |
|---|---|---|---|
| 基线 | off | flash (disabled) | 29a7d183 |
| C | off | reasoner (auto) | 4135389d |
| D | on | flash (disabled) | 4d2bfdd1 (2024 子集) |
| A | on | reasoner (auto) | 087626ec |

### 2.3 固定参数

| 参数 | 值 |
|---|---|
| provider | deepseek |
| profile | baziqa_xjz_reasoned |
| method | direct_choice |
| arm | b1a_prime |
| ziwei_arm | none |
| temperature | 0.0（flash）/ 删除（reasoner） |
| max_tokens | 16384（flash）/ 65536（reasoner） |
| dataset | 2024 holdout, 40 cases |
| repeat | 1（单次） |

### 2.4 数据完整性限制

本次探索使用 `run_benchmark.py` 直接运行，输出仅包含 `run_*.md`（报告）和 `summary.json`（运行元数据）。与 6D-v1 归档不同，**缺少以下产物**：

- `details.jsonl`（逐题模型输出与解析结果）
- `details.events.jsonl`（API 调用事件流）
- `details.manifest.json`（请求指纹与 provenance）
- `audit_index.json`（审计索引）

因此，无法从文件独立重算逐题结果。准确率数字来源于 `run_*.md` 中的 `SUMMARY` 块。

---

## 3. 观测结果

### 3.1 2×2 准确率

| 组 | Permutation | Model Protocol | 准确率 | vs 基线 | 安全分 |
|---|---|---|---|---|---|
| 基线 | off | flash | 32.5% (13/40) | - | 87.5% |
| C | off | reasoner | 30.0% (12/40) | -2.5pp | 98.8% |
| D | on | flash | 22.5% (9/40) | -10.0pp | 90.0% |
| A | on | reasoner | 20.0% (8/40) | -12.5pp | 97.5% |

### 3.2 Group D 完整 80-case 结果

Group D 额外在 2024+2025 合并数据集（80 cases）上运行了一次：

| 年度 | 正确数 | 准确率 |
|---|---|---|
| 2024 | 9/40 | 22.5% |
| 2025 | 12/40 | 30.0% |
| 总计 | 21/80 | 26.25% |

### 3.3 6D-v1 参照数据（非本实验阶段）

6D-v1 r1 实验在 31 个 routed cases × 3 repeats 上测试时间上下文注入，结果为 NON_INFERIOR。该数据作为背景参照列入附录 A，不参与本实验的对比或结论。

---

## 4. 观测分析

以下分析基于单次 40-case 运行的观测，不构成确定性因果结论。

### 4.1 Permutation 的观测

Permutation on 时准确率低于 off 时（flash: 22.5% vs 32.5%；reasoner: 20.0% vs 30.0%），两次对比均下降约 10pp。

可能原因（非确认性）：
- 模型可能依赖选项位置相关的统计规律，打乱后失效
- 原始选项可能按逻辑顺序排列，打乱后增加理解难度
- `unshuffle_predicted_answer` 代码审查确认使用 reverse map 正确还原标签，排除实现 bug

### 4.2 Model Protocol 的观测

Reasoner 准确率低于 flash（perm off: 30.0% vs 32.5%；perm on: 20.0% vs 22.5%），两次对比均下降约 2.5pp。

需要注意：这是 flash vs reasoner 的**模型间对比**，不是同一模型的 thinking 开关。reasoner 的 reasoning_content 平均消耗 13K+ tokens，单 call 耗时 3-5 分钟（vs flash 5 秒）。

### 4.3 组合观测

Permutation on + reasoner 的组合准确率 20.0%，低于 25% 随机基线。两个因子的下降幅度大致叠加（-10pp + -2.5pp ≈ -12.5pp），未观察到明显的协同放大或抵消。

### 4.4 样本量限制

每组仅 40 cases × 1 repeat。以基线 32.5% 为例，95% 置信区间约为 ±14.5pp（Wilson 区间）。因此：

- 10pp 的 permutation 效应**可能**显著，但单次运行不足以确认
- 2.5pp 的 model protocol 效应**在统计噪声范围内**，无法区分真实效应与随机波动
- 需要 3+ repeats 或更大样本才能做出可靠推断

---

## 5. 待修订事项

| # | 问题 | 修订方向 |
|---|---|---|
| 1 | 缺少 details/events/manifest/audit | 后续运行应使用 6D orchestrator 或添加 `--dump-details` 选项 |
| 2 | 单次 40 题无重复 | 需要 3+ repeats 才能计算统计显著性 |
| 3 | `thinking=auto` 实为模型切换 | 报告中应始终称"model protocol"而非"thinking" |
| 4 | 无 2025 数据的 reasoner 组 | Group C/A 仅在 2024 上运行 |
| 5 | 未测试 RAG 因子 | 原设计的第三个因子（RAG）未执行 |

---

## 6. 后续方向建议

以下为探索性建议，不构成承诺：

| 方向 | 说明 | 前置条件 |
|---|---|---|
| 带重复的 2×2 | 3 repeats × 40 cases × 4 组 = 480 calls | 预算 ~4h（flash）/ ~12h（reasoner） |
| RAG alone | 在基线（perm=off, flash）上添加 `--rag` | 验证 RAG 索引可用性 |
| Few-shot 注入 | 在 prompt 中加入正确推理示例 | 设计示例选取策略 |
| 结构化命盘格式 | JSON 格式 vs 纯文本对比 | 修改 `chart_context.py` |
| 基线错误分析 | 对基线答错的 27 case 逐题分类 | 需要 details.jsonl（当前缺失） |

---

## 附录 A：6D-v1 r1 参照数据

> 以下数据来自独立的 6D-v1 实验，仅作背景参照。

### A.1 实验设计

- 数据集：31 routed cases × 3 repeats = 93 calls/arm
- 臂：OFF（无时间上下文）vs ON（含时间上下文）
- 判定阈值：min_case_delta / 3 = -2pp

### A.2 结果

| 臂 | 正确数 | 准确率 |
|---|---|---|
| OFF | 19/93 | 20.43% |
| ON | 18/93 | 19.35% |
| paired_delta | -1 | -1.08pp |

按年度：

| 年度 | OFF | ON | Delta |
|---|---|---|---|
| 2024 | 11/54 = 20.4% | 10/54 = 18.5% | -1.85pp |
| 2025 | 8/39 = 20.5% | 8/39 = 20.5% | 0.00pp |

判定：NON_INFERIOR

### A.3 Per-case 分布（6D-v1，31 routed cases）

| 类别 | 数量 |
|---|---|
| delta=0（on/off 无变化） | 24 |
| delta>0（on 更好） | 3 |
| delta<0（on 更差） | 4 |
| 净 delta | -1 |

24 个 delta=0 的 case 中，多数在 on/off 两个臂均 0/3 正确。这表明这些 case 的瓶颈在于模型知识而非上下文信息。

### A.4 归档位置

```
docs/phase6/6d/runs/phase6-6d-v1-20260808-r1/
  ├── dev/           # 186 次 API 调用详情
  ├── gates/         # dev_gate.json（NON_INFERIOR 判定）
  ├── run_context.json
  ├── report.md
  └── errata.md
```

---

## 附录 B：Run IDs 与代码变更

### B.1 Run IDs

| 组 | Run ID | 数据集 | Cases | 准确率 |
|---|---|---|---|---|
| 基线 | 29a7d183 | 2024 holdout | 40 | 32.5% |
| C (reasoner) | 4135389d | 2024 holdout | 40 | 30.0% |
| D (perm, 80) | 4d2bfdd1 | 2024+2025 holdout | 80 | 26.25% |
| A (perm+reasoner) | 087626ec | 2024 holdout | 40 | 20.0% |

### B.2 代码变更

| Commit | 说明 |
|---|---|
| 3258170 | 支持 thinking_mode=auto（切换为 deepseek-reasoner） |
| f59e42f | max_tokens=65536 + reasoning_content fallback |

---

*探索性实验报告，不构成确定性结论。*
