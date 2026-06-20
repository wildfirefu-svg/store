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
- Chart-structure scoring enabled but did not improve over baseline (20% vs previous 30% baseline).
- Next step: investigate why enriched corpus with chart-structure scoring degraded accuracy.

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
- 下一步需调查 enriched corpus + chart-structure scoring 为何反而降低准确率（可能是 chart_features 评分权重干扰了原有结构化匹配）。
