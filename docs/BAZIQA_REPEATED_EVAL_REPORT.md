# BaziQA Repeated Evaluation Report

Dataset: `benchmark/datasets/baziqa_contest8_2025_holdout.jsonl`  MaxCases: 40  Repeats: 1  Temperature: 0.0

| Label | Runs | Mean | Min | Max | Stdev |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline-direct | 1 | 0.325 | 0.325 | 0.325 | 0.000 |
| rag-direct | 1 | 0.300 | 0.300 | 0.300 | 0.000 |
| rag-structured | 1 | 0.325 | 0.325 | 0.325 | 0.000 |

## Raw Runs

```json
[
  {
    "label": "baseline-direct",
    "method": "direct_choice",
    "rag": false,
    "correct": 13,
    "total": 40,
    "accuracy": 0.325,
    "run_id": "63e55767"
  },
  {
    "label": "rag-direct",
    "method": "direct_choice",
    "rag": true,
    "correct": 12,
    "total": 40,
    "accuracy": 0.3,
    "run_id": "1f6f816c"
  },
  {
    "label": "rag-structured",
    "method": "structured_reasoning",
    "rag": true,
    "correct": 13,
    "total": 40,
    "accuracy": 0.325,
    "run_id": "016ee6de"
  }
]
```
