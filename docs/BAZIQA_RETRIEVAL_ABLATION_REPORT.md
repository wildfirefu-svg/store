# BaziQA Retrieval Ablation Report

## [model: flash] Retrieval ablation summary

| rank | config_id | model_name | runs | mean | min | max | stdev | weak_leak | strict_leak | est_cost_cny | gate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | tfidf_vector | deepseek-v4-flash | 3 | 27.5% | 25.0% | 30.0% | 1.2pp | 97.5% | 0.0% | 0.79 | BLOCKED |
| 2 | bm25 | deepseek-v4-flash | 3 | 24.2% | 20.0% | 27.5% | 2.4pp | 97.5% | 0.0% | 0.79 | BLOCKED |
| 3 | structured | deepseek-v4-flash | 3 | 21.7% | 12.5% | 27.5% | 6.1pp | 78.3% | 0.0% | 0.79 | BLOCKED |
| 4 | embedding_vector | deepseek-v4-flash | 3 | 21.7% | 17.5% | 27.5% | 4.1pp | 94.2% | 0.0% | 0.79 | BLOCKED |
| 5 | semantic | deepseek-v4-flash | 3 | 20.0% | 15.0% | 22.5% | 3.1pp | 97.5% | 0.0% | 0.79 | BLOCKED |

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

| rank | config_id | model_name | runs | mean | min | max | stdev | weak_leak | strict_leak | est_cost_cny | gate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | tfidf_vector | deepseek-v4-pro | 3 | 25.8% | 22.5% | 30.0% | 3.1pp | 97.5% | 0.0% | 3.96 | BLOCKED |
| 2 | bm25 | deepseek-v4-pro | 3 | 20.8% | 12.5% | 27.5% | 6.2pp | 97.5% | 0.0% | 3.96 | BLOCKED |

Run-level pro results:

| config_id | run1 | run2 | run3 | errors |
|---|---:|---:|---:|---:|
| tfidf_vector | 10/40 | 12/40 | 9/40 | 0 |
| bm25 | 5/40 | 9/40 | 11/40 | 0 |

Task 4.4 conclusion: `tfidf_vector` remains the better Top-2 candidate under `deepseek-v4-pro`, but both pro configs remain below the 40% gate and are therefore `BLOCKED`. `tfidf_vector` stdev (3.1pp) passes the `mean >= 3 * stdev` sub-gate (`25.8% >= 9.3%`); `bm25` stdev (6.2pp) fails the sub-gate (`20.8% < 18.6%`).

## Baseline comparison

| phase | config | model | mean | date | source |
|---|---|---|---|---|---|
| P2 baseline | direct_choice (no RAG) | deepseek-v4-pro | 25.0% | 2026-06-18 | BAZIQA_ACCEPTANCE_REPORT.md |
| P2 RAG | rag-structured | deepseek-v4-pro | 30.0% (3 repeats) | 2026-06-19 | BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md |
| Stage 1 | tfidf_vector | deepseek-v4-pro | 25.8% | 2026-06-29 | This report |
| Stage 1 | bm25 | deepseek-v4-pro | 20.8% | 2026-06-29 | This report |

Baseline comparison conclusion: Stage 1 ablation configs do not improve over P2 RAG baseline (`30.0%`). `tfidf_vector` is comparable to P2 no-RAG baseline (`25.0%`), while `bm25` underperforms it. The best historical result remains `rag-structured` single run at `42.5%` (2026-06-19), but that result was unstable across 3 repeats.

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

## Answer distribution (pro Top-2)

| config_id | A | B | C | D | other | total |
|---|---:|---:|---:|---:|---:|---:|
| tfidf_vector | 29 | 37 | 23 | 31 | 0 | 120 |
| bm25 | 25 | 36 | 29 | 30 | 0 | 120 |

Distribution conclusion: Both configs show a slight B-bias (30.8% for tfidf_vector, 30.0% for bm25), but overall distribution is relatively uniform. No single option dominates, suggesting the model is not stuck in a positional bias.

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

## Task 5.5 Domain subset appendix

Task 5 domain subset files:

| domain | subset_file | cases | holdout | corpus_fill |
|---|---|---:|---:|---:|
| health | `benchmark/datasets/baziqa_domain_subsets/health.jsonl` | 5 | 3 | 2 |
| annual_fortune | `benchmark/datasets/baziqa_domain_subsets/annual_fortune.jsonl` | 5 | 2 | 3 |
| relationship | `benchmark/datasets/baziqa_domain_subsets/relationship.jsonl` | 7 | 7 | 0 |
| unknown | `benchmark/datasets/baziqa_domain_subsets/unknown.jsonl` | 10 | 10 | 0 |

Flash subset completeness:

| domain | rows | rollback_rows | errors |
|---|---:|---:|---:|
| health | 75 | 75 | 0 |
| annual_fortune | 75 | 75 | 0 |
| relationship | 105 | 105 | 0 |
| unknown | 150 | 150 | 0 |

Pro Top-2 subset completeness:

| domain | pro_configs | rows | rollback_rows | errors |
|---|---|---:|---:|---:|
| health | `structured,semantic` | 30 | 30 | 0 |
| annual_fortune | `semantic,bm25` | 30 | 30 | 0 |
| relationship | `tfidf_vector,structured` | 42 | 42 | 0 |
| unknown | `bm25,semantic` | 60 | 60 | 0 |

### Domain subset flash results

#### health flash

| rank | config_id | runs | mean | min | max | gate |
|---:|---|---:|---:|---:|---:|---|
| 1 | structured | 3 | 60.0% | 40.0% | 80.0% | PASS |
| 2 | semantic | 3 | 53.3% | 40.0% | 60.0% | PASS |
| 3 | bm25 | 3 | 46.7% | 40.0% | 60.0% | PASS |
| 4 | tfidf_vector | 3 | 46.7% | 40.0% | 60.0% | PASS |
| 5 | embedding_vector | 3 | 40.0% | 40.0% | 40.0% | PASS |

#### annual_fortune flash

| rank | config_id | runs | mean | min | max | gate |
|---:|---|---:|---:|---:|---:|---|
| 1 | semantic | 3 | 66.7% | 60.0% | 80.0% | PASS |
| 2 | bm25 | 3 | 60.0% | 60.0% | 60.0% | PASS |
| 3 | structured | 3 | 60.0% | 60.0% | 60.0% | PASS |
| 4 | tfidf_vector | 3 | 60.0% | 60.0% | 60.0% | PASS |
| 5 | embedding_vector | 3 | 60.0% | 60.0% | 60.0% | PASS |

#### relationship flash

| rank | config_id | runs | mean | min | max | gate |
|---:|---|---:|---:|---:|---:|---|
| 1 | tfidf_vector | 3 | 23.8% | 14.3% | 42.9% | BLOCKED |
| 2 | structured | 3 | 19.0% | 14.3% | 28.6% | BLOCKED |
| 3 | semantic | 3 | 19.0% | 14.3% | 28.6% | BLOCKED |
| 4 | bm25 | 3 | 14.3% | 0.0% | 28.6% | BLOCKED |
| 5 | embedding_vector | 3 | 14.3% | 14.3% | 14.3% | BLOCKED |

#### unknown flash

| rank | config_id | runs | mean | min | max | gate |
|---:|---|---:|---:|---:|---:|---|
| 1 | bm25 | 3 | 40.0% | 30.0% | 60.0% | BLOCKED |
| 2 | semantic | 3 | 33.3% | 30.0% | 40.0% | BLOCKED |
| 3 | embedding_vector | 3 | 33.3% | 30.0% | 40.0% | BLOCKED |
| 4 | structured | 3 | 26.7% | 20.0% | 30.0% | BLOCKED |
| 5 | tfidf_vector | 3 | 23.3% | 20.0% | 30.0% | BLOCKED |

### Domain subset pro Top-2 results

#### health pro

| rank | config_id | runs | mean | min | max | gate |
|---:|---|---:|---:|---:|---:|---|
| 1 | semantic | 3 | 46.7% | 40.0% | 60.0% | PASS |
| 2 | structured | 3 | 40.0% | 20.0% | 60.0% | BLOCKED |

#### annual_fortune pro

| rank | config_id | runs | mean | min | max | gate |
|---:|---|---:|---:|---:|---:|---|
| 1 | bm25 | 3 | 66.7% | 60.0% | 80.0% | PASS |
| 2 | semantic | 3 | 66.7% | 40.0% | 80.0% | PASS |

#### relationship pro

| rank | config_id | runs | mean | min | max | gate |
|---:|---|---:|---:|---:|---:|---|
| 1 | tfidf_vector | 3 | 23.8% | 0.0% | 42.9% | BLOCKED |
| 2 | structured | 3 | 19.0% | 14.3% | 28.6% | BLOCKED |

#### unknown pro

| rank | config_id | runs | mean | min | max | gate |
|---:|---|---:|---:|---:|---:|---|
| 1 | semantic | 3 | 30.0% | 30.0% | 30.0% | BLOCKED |
| 2 | bm25 | 3 | 13.3% | 10.0% | 20.0% | BLOCKED |

Task 5.5 conclusion: domain subsets expose strong distribution differences. `annual_fortune` is the only domain whose pro Top-2 configs both pass the 40% mean / 35% min gate; `health` has one passing pro config (`semantic`), while `relationship` and `unknown` remain blocked. Annual-fortune flash had a four-way tie for second place at 60.0%; relationship flash had a tie between `structured` and `semantic` at 19.0%; unknown flash had a tie between `semantic` and `embedding_vector` at 33.3%. Pro Top-2 selection used mean-descending order with the original retrieval config order as the tie-breaker.
