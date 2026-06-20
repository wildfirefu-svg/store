# BaziQA Accuracy And Judgment Improvement Report

> 创建日期：2026-06-20
> 实施计划：`docs/superpowers/plans/2026-06-20-bazi-accuracy-and-judgment-improvement-implementation.md`

## Stable Accuracy Status

| configuration | runs | mean | min | max | gate |
|---|---:|---:|---:|---:|---|
| bm25 | 0 | 0.0% | 0.0% | 0.0% | not_run |
| structured | 0 | 0.0% | 0.0% | 0.0% | not_run |
| structured_semantic | 0 | 0.0% | 0.0% | 0.0% | not_run |
| semantic_low | 0 | 0.0% | 0.0% | 0.0% | not_run |

## Retrieval Decision

- Default retrieval mode: unchanged until repeats=3 supports a change.
- Default rag_k: 2 unless a repeats=3 report proves another k is better.
- Semantic overlap: disabled or reduced if full 40-case validation is below structured baseline.

## Chart Input Coverage

- Corpus chart_input coverage: 0.0%.
- Acceptance threshold: 90.0%.

## Weak Domains

| domain | action |
|---|---|
| none | wait_for_current_trace |

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

Current status is BLOCKED until real 40-case and repeats=3 evidence is recorded.
