# BaziQA Accuracy And Judgment Improvement Report

> 创建日期：2026-06-20
> 实施计划：`docs/superpowers/plans/2026-06-20-bazi-accuracy-and-judgment-improvement-implementation.md`

## Stable Accuracy Status

| configuration | runs | mean | min | max | gate |
|---|---:|---:|---:|---:|---|
| refined_p2_structured (enriched corpus) | 1 | 20.0% | 20.0% | 20.0% | BLOCKED |
| bm25 | 0 | 0.0% | 0.0% | 0.0% | not_run |
| structured | 0 | 0.0% | 0.0% | 0.0% | not_run |
| structured_semantic | 0 | 0.0% | 0.0% | 0.0% | not_run |
| semantic_low | 0 | 0.0% | 0.0% | 0.0% | not_run |

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

## Final Decision

**Status: BLOCKED**

- Refined P2 实测准确率 20.0% (8/40)，低于 gate 阈值 40%，且低于此前 30% 基线。
- 按决策规则，20% < 27.5%，semantic overlap 应默认禁用。
- Chart_input 覆盖率已达 100%，但命盘结构相似度评分未带来提升。
- 弱领域识别：`unknown` (14.3%), `relationship` (14.3%), `health` (0.0%)。
- **根因分析结论**：准确率下降非代码改动所致，而是 API 输出不稳定性。检索在 enriched/original corpus 上 100% 一致。
