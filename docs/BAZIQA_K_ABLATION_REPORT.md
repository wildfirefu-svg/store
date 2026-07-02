# BaziQA RAG k-Ablation Report (Phase 2)

> **状态说明**：本报告只作为 Phase 2 k-ablation 诊断材料；run2/run3 未完成，不能作为 Phase 2 完整验收。Phase 2 当前统一状态以 [PHASE2_STATUS_UNIFIED.md](file:///f:/project/agent/docs/PHASE2_STATUS_UNIFIED.md) 为准：Engineering Done / Evaluation NO-GO。

Generated: 2026-07-02

## Executive Summary

| k | runs | mean | min | max | stdev | leak |
|---|------|------|-----|-----|-------|------|
| 1 | 1 | 20.5% | 20.5% | 20.5% | N/A | 0.0% |
| 2 | 1 | **27.5%** | 27.5% | 27.5% | N/A | 0.0% |
| 3 | 1 | 23.1% | 23.1% | 23.1% | N/A | 0.0% |

> **Note**: Only 1 run completed per k due to benchmark runner hanging on CaseIndex initialization. Run2/Run3 were empty (0 bytes).

## Phase 2 Gate Evaluation

| Gate | Threshold | Actual | Status |
|------|-----------|--------|--------|
| Mean accuracy | >= 35% | 27.5% (best k=2) | **FAIL** |
| Retrieved answer leak | >= 5% | 0.0% | **FAIL** |
| Repeats | >= 3 | 1 | **FAIL** |

**Phase 2 Status: ROLLBACK**

## Key Findings

### 1. Bottleneck is retrieval quality, not k-value
All k values (1, 2, 3) perform far below the 35% threshold. The optimal k=2 only achieves 27.5%, indicating the retrieval mechanism itself is the bottleneck.

### 2. Retrieval is fundamentally broken
- **All cases retrieve the same 2-3 persons** (male_19831101_P022, male_19740428_P017, female_19841209_P023)
- **Score is None** for all retrieved cases — no similarity scoring
- **Domain matching is not discriminative**: 82% for correct cases, 86% for wrong cases
- **Retrieved facts are irrelevant** to the actual questions

### 3. Retrieved answer leak = 0%
Strict leak detection found 0 cases where the correct answer appeared in retrieved facts. This confirms the retrieval is not finding relevant cases.

### 4. Answer distribution is balanced
No significant bias toward any option (A: 8-9, B: 12, C: 8-10, D: 9-11), suggesting the LLM is not simply guessing.

## Root Cause Analysis

The `CaseIndex.top_k_cases()` method appears to return the same cases regardless of input query. Likely causes:

1. **Feature extraction homogeneity**: `bazi_features.extract()` may return nearly identical feature vectors for all inputs
2. **Missing score computation**: Retrieved cases have `score=None`, indicating the similarity computation is not working
3. **Index not using dense vectors**: The hybrid retrieval may be falling back to a broken keyword match that always returns the same results

## Recommendations

### Immediate Actions
1. **Debug CaseIndex.top_k_cases()**: Verify that different inputs produce different retrieval results
2. **Fix score computation**: Ensure similarity scores are returned and used for ranking
3. **Validate feature extraction**: Check that `bazi_features.extract()` produces distinct features for different charts

### Next Phase Strategy
Since Phase 2 (k-ablation) confirms the bottleneck is retrieval quality, the next effort should focus on:
1. **Fixing the retrieval index** (CaseIndex / case_dense_index)
2. **Validating dense vector similarity** (case_dense_index.py)
3. **Re-running k-ablation** only after retrieval is fixed

## Interpretation

- If k=1 or k=2 mean >= k=3 mean + 5pp and stdev is not larger, reduce default k.
- **If all k means < 35%, the bottleneck is retrieval quality, not k.** (Current situation)
