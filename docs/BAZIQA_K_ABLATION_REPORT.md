# BaziQA RAG k-Ablation Report

Generated: 2026-06-20 12:45:30

## Summary by k

| k | runs | mean | min | max | stdev |
|---|------|------|-----|-----|-------|
| 1 | 1 | 0.2051 | 0.2051 | 0.2051 | 0.0000 |
| 2 | 1 | 0.2750 | 0.2750 | 0.2750 | 0.0000 |
| 3 | 1 | 0.2308 | 0.2308 | 0.2308 | 0.0000 |

## Per-run Details

| k | repeat | correct | total | accuracy | failed | details |
|---|--------|---------|-------|----------|--------|---------|
| 1 | 1 | 8 | 39 | 0.2051 | 1 | `.tmp/k_ablation/k1_run1.jsonl` |
| 2 | 1 | 11 | 40 | 0.2750 | 0 | `.tmp/k_ablation/k2_run1.jsonl` |
| 3 | 1 | 9 | 39 | 0.2308 | 1 | `.tmp/k_ablation/k3_run1.jsonl` |

## Interpretation

- If k=1 or k=2 mean ≥ k=3 mean + 5 pp and stdev is not larger, reduce default k.
- If all k means < 35%, the bottleneck is retrieval quality, not k.
