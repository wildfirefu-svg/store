# BaziQA Accuracy And Judgment Improvement Report

> 创建日期：2026-06-20
> 实施计划：`docs/superpowers/plans/2026-06-20-bazi-accuracy-and-judgment-improvement-implementation.md`

## Stable Accuracy Status

| configuration | runs | mean | min | max | stdev | gate |
|---|---:|---:|---:|---:|---:|---|
| enriched_holdout+corpus (3 repeats) | 3 | 24.2% | 22.5% | 25.0% | 1.2pp | BLOCKED |
| refined_p2_structured (enriched corpus) | 1 | 20.0% | 20.0% | 20.0% | — | BLOCKED |
| baseline rag-structured (original) | 3 | 30.0% | 27.5% | 35.0% | 4.3pp | — |
| bm25 | 0 | 0.0% | 0.0% | 0.0% | — | not_run |
| structured | 0 | 0.0% | 0.0% | 0.0% | — | not_run |
| structured_semantic | 0 | 0.0% | 0.0% | 0.0% | — | not_run |
| semantic_low | 0 | 0.0% | 0.0% | 0.0% | — | not_run |

### Refined P2 Run Details (run b99ddab3)

- Dataset: `benchmark/datasets/baziqa_contest8_2025_holdout.jsonl` (40 cases)
- Corpus: `benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl` (160 cases, 100% chart_input coverage)
- Method: `structured_reasoning`, temperature=0, rag_k=2
- Result: **8/40 = 20.0%**
- Evidence Coverage: 100%, Safety Score: 100%

### Per-domain Breakdown

| domain | correct | total | accuracy |
|---|---:|---:|---:|
| unknown | 2 | 14 | 14.3% |
| career | 3 | 9 | 33.3% |
| relationship | 1 | 7 | 14.3% |
| family | 1 | 4 | 25.0% |
| health | 0 | 3 | 0.0% |
| annual_fortune | 0 | 2 | 0.0% |
| study | 1 | 1 | 100.0% |

## Retrieval Decision

- Default retrieval mode: **structured only** (semantic overlap disabled per decision rule: result 20.0% < 27.5% threshold).
- Default rag_k: 2.
- Chart-structure scoring enabled but had NO effect on retrieval (see Root Cause Analysis below).

## Root Cause Analysis (2026-06-20)

### 核心发现

1. **检索 100% 一致**：对全部 40 个 holdout 查询，enriched corpus 与 original corpus 返回完全相同的 top-2 结果（person_id、score 均一致）。
2. **chart_structure scoring 未生效**：holdout 数据集没有 `chart_input` 字段，`_case_chart()` 回退到空的 `four_pillars: {}`，导致查询侧 `day_master_gan`、`month_zhi` 等全部为空，`_score_chart_structure()` 返回 0。
3. **enriched corpus chart_features 已正确提取**：33 个 corpus person 全部有 chart_features（day_master、month_zhi、wuxing_stats、shishen_stats），但查询侧缺少对应数据，无法进行比对。
4. **模型输出不稳定是主因**：此前 `rag-structured` 3 次重复测试结果为 27.5%/35.0%/27.5%（mean=30.0%, stdev=4.3pp），本次 20.0% 偏离均值约 2.3σ，属于低概率事件但仍在已知方差范围内。
5. **C 选项偏置**：本次 40 题中 15 题预测为 C（37.5%），答案分布不均。
6. **检索无答案泄露**：0/40 的正确答案出现在检索到的 facts 中。

### 结论

**准确率下降不是由代码改动（enriched corpus / chart-structure scoring）引起的**，而是 DeepSeek API 在 temperature=0 下的输出不稳定性所致。此前的 30% "基线" 本身就是 3 次重复的均值，单次运行波动范围为 27.5%–35.0%。

### 修复建议

1. **为 holdout 数据补充 chart_input**：使查询侧有完整的八字排盘数据，chart_structure scoring 才能真正生效。
2. **增加 repeats**：至少 3 次重复以平均模型不稳定性。
3. **调查 prompt 工程**：RAG 注入的相似命例 facts 中不含正确答案（0/40 泄露），说明检索质量本身需要提升（可能需要 A1 向量检索）。

## Chart Input Coverage

- Corpus chart_input coverage: **100.0%** (160/160). ✅ Exceeds 90% threshold.

## Weak Domains

| domain | total | accuracy | action |
|---|---:|---:|---|
| unknown | 14 | 14.3% | add_domain_rules_and_examples |
| relationship | 7 | 14.3% | add_domain_rules_and_examples |
| health | 3 | 0.0% | add_domain_rules_and_examples |

## Report Quality Gate

- Total reports: 0
- Failed reports: 0
- Gate: not_run

## Implementation Progress

| 任务 | 状态 | 提交 |
|------|------|------|
| Task 1: Refined P2 Full-Set Validation | ✅ 已实现 | `test: add refined P2 full-set validation` |
| Task 2: Retrieval Mode Switches And Ablation | ✅ 已实现 | `feat: add BaziQA retrieval ablation controls` |
| Task 3: Enrich Corpus With Chart Input | ✅ 已实现 | `feat: enrich BaziQA corpus with chart input` |
| Task 4: Chart-Structure Retrieval Scoring | ✅ 已实现 | `feat: add chart-structure BaziQA retrieval scoring` |
| Task 5: Domain-Specific Action Plan | ✅ 已实现 | `feat: add BaziQA domain action planning` |
| Task 6: Link Report Quality To Accuracy Work | ✅ 已实现 | `test: link report quality gate to BaziQA accuracy work` |

## 执行命令

### 运行 refined P2 全量 40 题验证

```powershell
python scripts/run_baziqa_refined_p2_validation.py --run
```

### 运行检索消融实验

```powershell
python scripts/run_baziqa_retrieval_ablation.py --run --repeats 3
```

### 生成 enriched corpus

```powershell
python scripts/enrich_baziqa_chart_input.py `
  --input benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl `
  --output benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl
```

### 生成领域行动计划

```powershell
python scripts/build_domain_action_plan.py `
  --summary-json .tmp/baziqa_error_attribution_summary.json `
  --output docs/BAZIQA_DOMAIN_ACTION_PLAN.md
```

### 运行报告质量门禁

```powershell
python scripts/export_report_quality_samples.py `
  --input-json .tmp/report_quality_manual_cases.json `
  --output-jsonl .tmp/report_quality_samples.jsonl

python scripts/verify_report_quality_gate.py `
  --reports-jsonl .tmp/report_quality_samples.jsonl `
  --output docs/REPORT_QUALITY_GATE_REPORT.md
```

## Enriched Holdout 3-Repeat Validation (2026-06-20)

### 方法

- Holdout: `benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl` (40 cases, 100% chart_input coverage)
- Corpus: `benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl` (160 cases)
- Method: `structured_reasoning`, temperature=0, rag_k=2, deepseek-v4-pro
- 3 次独立重复运行

### 结果

| run | correct | total | accuracy |
|---:|---:|---:|---:|
| 1 | 10 | 40 | 25.0% |
| 2 | 9 | 40 | 22.5% |
| 3 | 10 | 40 | 25.0% |
| **mean** | **9.67** | **40** | **24.2%** |

- Stdev: **1.2pp** (vs baseline 4.3pp — 稳定性提升 72%)
- Min/Max: 22.5%/25.0%

### Per-domain Breakdown (Run 3)

| domain | correct | total | accuracy |
|---|---:|---:|---:|
| unknown | 6 | 14 | 43% |
| health | 1 | 3 | 33% |
| career | 2 | 9 | 22% |
| relationship | 1 | 7 | 14% |
| annual_fortune | 0 | 2 | 0% |
| family | 0 | 4 | 0% |
| study | 0 | 1 | 0% |

### Answer Distribution (Run 3)

| answer | count | pct |
|---:|---:|---:|
| A | 11 | 28% |
| B | 13 | 32% |
| C | 5 | 12% |
| D | 11 | 28% |

C 偏置从 37.5% 大幅降至 12%，答案分布更均衡。

### 分析

1. **chart_input 增强有效**：chart_structure scoring 在 10/10 测试 case 上返回非零分数，5/40 查询检索结果发生变化。
2. **稳定性大幅提升**：stdev 从 4.3pp 降至 1.2pp，说明 chart_structure scoring 为检索提供了更一致的锚定。
3. **准确率未达验收线**：mean 24.2% < 40% 验收线，且低于 30% 基线。检索质量本身（而非评分机制）是瓶颈。
4. **检索 facts 不含答案**：0/40 的正确答案出现在 RAG facts 中，说明检索到的命例与查询题目相关性不足。

## 阶段 1 Baseline: retrieved_answer_leak

> 指标定义：[design §11](file:///f:/project/agent/docs/superpowers/specs/2026-06-22-baziqa-hybrid-retrieval-reasoning-design.md)，由 [scripts/compute_retrieved_answer_leak.py](file:///f:/project/agent/scripts/compute_retrieved_answer_leak.py) 计算。

### 计算方法

| 指标 | 算法 | 是否用于晋升判定 |
|---|---|---|
| `weak_leak`（子串包含） | `expected_answer` 字母（A/B/C/D）作为子串出现在任意 `rag_trace[*].facts` 字符串中 | **否**（单字母天然高假阳，已知 92.5–100%） |
| `strict_leak`（问题对齐 + `-> X` 模式） | 同时满足：1) facts 包含 `-> {expected_answer}` 模式；2) facts 包含当前 case 的 question 前 6 个字符（排除邻案不同题目的答案对当前案造成假阳） | **是**（用于晋升门阈） |

### 数据来源

按 [实施计划 Task 1.5](file:///f:/project/agent/docs/superpowers/plans/2026-06-22-baziqa-hybrid-stage1-implementation.md) 使用历史 P2 case_details：

| 源文件 | 样本数 | 来源 | weak_leak | strict_leak |
|---|---|---|---|---|
| `.tmp/p2_rag_k2_details.jsonl` | 40 | P2 初版 40 题 real API 运行 | 37/40 = 92.5% | **0/40 = 0.0%** |
| `.tmp/p2_refined_rag_k2_10_details.jsonl` | 10 | P2 refined 10 题 smoke | 10/10 = 100.0% | **0/10 = 0.0%** |

> 注：`weak_leak` 的 92.5–100% 是“单字母答案在邻案 facts 中自然出现”的假阳，不是真实语义泄露。`strict_leak` 通过问题前缀对齐排除了跨题干扰，反映真实泄露比例。

### 基线结论

**`strict_leak` = 0/40 = 0.0%**：在 P2 检索配置下，**没有任何一条 case 的 retrieved facts 中包含与当前问题题干对齐的正确答案**。这与 [BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md) 中 “检索 facts 不含答案：0/40” 的定性结论完全一致，且用可复现方法量化确认。

阶段 1 的晋升门阈 `retrieved_answer_leak ≥ 15%`（设计 §11 中间门阈）以此为基线。
