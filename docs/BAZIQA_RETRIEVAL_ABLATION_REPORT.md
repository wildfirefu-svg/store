# BaziQA Retrieval Ablation Report

## [model: flash] Retrieval ablation summary

| rank | config_id | model_name | runs | mean | min | max | weak_leak | strict_leak | est_cost_cny | gate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | tfidf_vector | deepseek-v4-flash | 3 | 27.5% | 25.0% | 30.0% | 97.5% | 0.0% | 0.79 | BLOCKED |
| 2 | bm25 | deepseek-v4-flash | 3 | 24.2% | 20.0% | 27.5% | 97.5% | 0.0% | 0.79 | BLOCKED |
| 3 | structured | deepseek-v4-flash | 3 | 21.7% | 12.5% | 27.5% | 78.3% | 0.0% | 0.79 | BLOCKED |
| 4 | embedding_vector | deepseek-v4-flash | 3 | 21.7% | 17.5% | 27.5% | 94.2% | 0.0% | 0.79 | BLOCKED |
| 5 | semantic | deepseek-v4-flash | 3 | 20.0% | 15.0% | 22.5% | 97.5% | 0.0% | 0.79 | BLOCKED |

## Task 4.3 Top-2 selection

Selected Top-2 configs for Task 4.4 pro retest:

1. `tfidf_vector`
2. `bm25`

Selection rule: choose Top-2 by flash mean accuracy. If the Top-1 / Top-2 mean gap is ≤ 1pp, expand to Top-3. Here, `tfidf_vector` mean is 27.5% and `bm25` mean is 24.2%, so the gap is 3.3pp. No Top-3 expansion is required.

Task 4.4 command target:

```powershell
$env:DEEPSEEK_API_KEY = (Get-Content .deepseek_key -Raw).Trim()
python -u scripts/run_baziqa_retrieval_ablation.py `
  --run `
  --configs tfidf_vector,bm25 `
  --model deepseek-v4-pro `
  --repeats 3 `
  --output-dir .tmp/ablation_stage1_pro_top2 `
  --rollback-jsonl .tmp/ablation_stage1_pro_top2/rollback.jsonl `
  --report docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md `
  --append
```

## [model: pro] Task 4.4 Top-2 retest summary

| rank | config_id | model_name | runs | mean | min | max | weak_leak | strict_leak | est_cost_cny | gate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | tfidf_vector | deepseek-v4-pro | 3 | 25.8% | 22.5% | 30.0% | 97.5% | 0.0% | 3.96 | BLOCKED |
| 2 | bm25 | deepseek-v4-pro | 3 | 20.8% | 12.5% | 27.5% | 97.5% | 0.0% | 3.96 | BLOCKED |

Run-level pro results:

| config_id | run1 | run2 | run3 | errors |
|---|---:|---:|---:|---:|
| tfidf_vector | 10/40 | 12/40 | 9/40 | 0 |
| bm25 | 5/40 | 9/40 | 11/40 | 0 |

Task 4.4 conclusion: `tfidf_vector` remains the better Top-2 candidate under `deepseek-v4-pro`, but both pro configs remain below the 40% gate and are therefore `BLOCKED`.

## Task 4.5 Retrieval leak summary

Flash rollback source: `.tmp/ablation_stage1_flash/rollback.jsonl`

| config_id | rows | weak_leak_count | weak_leak_ratio | strict_leak_count | strict_leak_ratio |
|---|---:|---:|---:|---:|---:|
| bm25 | 120 | 117 | 97.5% | 0 | 0.0% |
| structured | 120 | 94 | 78.3% | 0 | 0.0% |
| semantic | 120 | 117 | 97.5% | 0 | 0.0% |
| tfidf_vector | 120 | 117 | 97.5% | 0 | 0.0% |
| embedding_vector | 120 | 113 | 94.2% | 0 | 0.0% |
| **overall** | **600** | **558** | **93.0%** | **0** | **0.0%** |

Pro rollback source: `.tmp/ablation_stage1_pro_top2/rollback.jsonl`

| config_id | rows | weak_leak_count | weak_leak_ratio | strict_leak_count | strict_leak_ratio |
|---|---:|---:|---:|---:|---:|
| tfidf_vector | 120 | 117 | 97.5% | 0 | 0.0% |
| bm25 | 120 | 117 | 97.5% | 0 | 0.0% |
| **overall** | **240** | **234** | **97.5%** | **0** | **0.0%** |

The weak leak metric is intentionally conservative and noisy for this dataset because single-letter expected answers (`A`/`B`/`C`/`D`) frequently appear as substrings in unrelated retrieved facts. The strict rule requires both `-> {answer}` and a current-question substring match; strict retrieved-answer leak is 0 for both flash and pro rollback files, so the ablation results are not explained by question-aligned answer leakage.

## Task 4.6 Cost guard

Unit prices from the implementation plan:

| model tier | price_cny_per_case | calls | estimated_cost_cny |
|---|---:|---:|---:|
| deepseek-v4-flash | 0.0066 | 600 | 3.96 |
| deepseek-v4-pro | 0.0330 | 240 | 7.92 |
| **stage1 total** | - | **840** | **11.88** |

Flash/pro drift guard:

| config_id | flash_mean | pro_mean | absolute_drift | threshold | result |
|---|---:|---:|---:|---:|---|
| tfidf_vector | 27.5% | 25.8% | 1.67pp | 15.00pp | PASS |
| bm25 | 24.2% | 20.8% | 3.33pp | 15.00pp | PASS |

Budget guard:

| guard | observed | threshold | result |
|---|---:|---:|---|
| stage1 calls | 840 | 1980 | PASS |
| stage1 estimated cost | 11.88 CNY | 31.80 CNY | PASS |
| three-stage cumulative cost to date | 11.88 CNY | 68.00 CNY | PASS |

Task 4.6 conclusion: no budget guard is triggered. The stage remains blocked by accuracy (`BLOCKED`), not by budget (`BLOCKED:budget`).
