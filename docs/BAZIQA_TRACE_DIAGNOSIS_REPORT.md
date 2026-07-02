# BaziQA Trace 定位实验报告

> 日期：2026-06-19
> 目的：定位 `rag-structured` 重复评测波动来源
> 方法：固定 2025 holdout 前 10 题，连续运行 3 次 `rag-structured`，每题落盘预测明细与 RAG top-k trace
> Provider：deepseek
> Model：deepseek-v4-pro
> Temperature：0.0
> RAG corpus：`benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl`

---

## 一、运行摘要

| Run | Trace 文件 | Rows | Correct | Accuracy |
|-----|------------|-----:|--------:|---------:|
| 1 | `.tmp/trace/rag_structured_10_run1.jsonl` | 10 | 5 | 50.0% |
| 2 | `.tmp/trace/rag_structured_10_run2.jsonl` | 10 | 6 | 60.0% |
| 3 | `.tmp/trace/rag_structured_10_run3.jsonl` | 10 | 4 | 40.0% |

小样本波动范围：**40%–60%**，即 10 题中相差 2 题。

---

## 二、逐题对比

| Case | Expected | Predictions | Correctness | RAG Top-k Stable | RAG Signatures |
|------|----------|-------------|-------------|------------------|----------------|
| `guangdong_female_19511114_P001-Q1` | B | C / B / C | ✗ / ✓ / ✗ | YES | male_19831101_P022,male_19740428_P017,female_19810526_P018 |
| `guangdong_female_19511114_P001-Q2` | D | C / C / B | ✗ / ✗ / ✗ | YES | female_19841209_P023,male_19831101_P022,male_19740428_P017 |
| `guangdong_female_19511114_P001-Q3` | B | B / B / B | ✓ / ✓ / ✓ | YES | male_19831101_P022,male_19740428_P017,male_19530127_P031 |
| `guangdong_female_19511114_P001-Q4` | A | C / C / B | ✗ / ✗ / ✗ | YES | male_19831101_P022,male_19740428_P017,female_19810526_P018 |
| `guangdong_female_19511114_P001-Q5` | B | B / B / B | ✓ / ✓ / ✓ | YES | male_19831101_P022,male_19740428_P017,female_19810526_P018 |
| `hongkong_female_19870705_P002-Q6` | D | D / D / C | ✓ / ✓ / ✗ | YES | male_19740428_P017,male_19831101_P022,male_19560311_P012 |
| `hongkong_female_19870705_P002-Q7` | B | B / B / B | ✓ / ✓ / ✓ | YES | male_19831101_P022,male_19740428_P017,female_19771026_P020 |
| `hongkong_female_19870705_P002-Q8` | D | D / C / A | ✓ / ✗ / ✗ | YES | male_19831101_P022,male_19740428_P017,female_19771026_P020 |
| `hongkong_female_19870705_P002-Q9` | D | B / D / D | ✗ / ✓ / ✓ | YES | male_19740428_P017,female_19670827_P034,female_19841220_P027 |
| `hongkong_female_19870705_P002-Q10` | B | D / D / C | ✗ / ✗ / ✗ | YES | male_19740428_P017,female_19771026_P020,male_19831101_P022 |

---

## 三、诊断统计

| 指标 | 数量 | 占比 |
|------|-----:|-----:|
| 对比 case 总数 | 10 | 100% |
| 预测答案不稳定 | 7 | 70% |
| 正误发生翻转 | 4 | 40% |
| RAG top-k 不稳定 | 0 | 0% |

### 3.1 预测答案不稳定的 case

- `guangdong_female_19511114_P001-Q1`
- `guangdong_female_19511114_P001-Q2`
- `guangdong_female_19511114_P001-Q4`
- `hongkong_female_19870705_P002-Q6`
- `hongkong_female_19870705_P002-Q8`
- `hongkong_female_19870705_P002-Q9`
- `hongkong_female_19870705_P002-Q10`

### 3.2 正误发生翻转的 case

- `guangdong_female_19511114_P001-Q1`
- `hongkong_female_19870705_P002-Q6`
- `hongkong_female_19870705_P002-Q8`
- `hongkong_female_19870705_P002-Q9`

### 3.3 RAG top-k 稳定性

10 个 case 的 RAG top-k 三次运行全部一致，说明上一轮修复后的检索排序在该样本上已经稳定。

---

## 四、关键定位结论

### 4.1 主要波动源不是 RAG 检索排序

三次运行中，每道题的 RAG top-k signature 都完全相同；因此本次 40%–60% 的小样本波动，不能归因于检索结果变化。

### 4.2 主要波动源是模型/API 输出不稳定

在相同题目、相同 RAG 命例、相同 temperature=0.0 的条件下，7/10 case 的最终选项仍发生变化。这说明 deepseek-v4-pro 的真实 API 在复杂长推理任务上并非完全确定。

### 4.3 不是单纯的答案抽取器问题

抽取器 `extract_choice` 只识别明确的 `答案：A/B/C/D`、`选择 A/B/C/D` 等模式。本次抽样查看 raw answer 后发现，模型的完整推理路径和最终答案本身确实在变化，不只是解析器误抽。

### 4.4 RAG 命例存在“固定但可能不够相关”的问题

虽然 RAG top-k 稳定，但多个题目反复召回相同命例，例如：

- `male_19831101_P022`
- `male_19740428_P017`
- `female_19810526_P018`

这说明当前检索可能过度依赖少数高频命例，稳定不代表高质量。下一步应验证 k=1/k=2/k=3，以及增强结构化匹配。

---

## 五、对后续策略的影响

### 5.1 不应继续把主要精力放在 tie-break 上

tie-break 已修复，且本次 trace 显示 RAG top-k 0% 不稳定。继续优化排序确定性收益有限。

### 5.2 应优先降低模型自由度

建议下一步实现强制输出协议：

1. 先让模型输出每个选项 A/B/C/D 的置信度分数；
2. 最终答案必须是置信度最高的选项；
3. 输出最后一行固定为 `最终答案：X`；
4. benchmark 只抽取最后一行，减少中间推理文本干扰。

### 5.3 同时做 k-ablation

因为 RAG top-k 稳定但命例可能有噪声，建议继续跑：

- `k=1`
- `k=2`
- `k=3`

并输出 trace，对比准确率和错误题的召回命例。

---

## 六、产出物

- Trace 文件：
  - `.tmp/trace/rag_structured_10_run1.jsonl`
  - `.tmp/trace/rag_structured_10_run2.jsonl`
  - `.tmp/trace/rag_structured_10_run3.jsonl`
- 分析脚本：[analyze_baziqa_trace_runs.py](file:///f:/project/agent/scripts/analyze_baziqa_trace_runs.py)
- 增量落盘实现：[run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py)

---

## 七、命令记录

```powershell
python benchmark/runners/run_benchmark.py `
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl `
  --model-runner `
  --provider deepseek `
  --model deepseek-v4-pro `
  --max-cases 10 `
  --method structured_reasoning `
  --temperature 0 `
  --rag `
  --rag-corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl `
  --case-details-jsonl .tmp/trace/rag_structured_10_run1.jsonl `
  --output-dir .tmp/trace/outputs
```

分析命令：

```powershell
python scripts/analyze_baziqa_trace_runs.py `
  --inputs .tmp/trace/rag_structured_10_run1.jsonl .tmp/trace/rag_structured_10_run2.jsonl .tmp/trace/rag_structured_10_run3.jsonl `
  --output docs/BAZIQA_TRACE_DIAGNOSIS_REPORT.md
```
