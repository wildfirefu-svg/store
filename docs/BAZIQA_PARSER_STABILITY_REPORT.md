# BaziQA Repeated Evaluation Report

Dataset: `benchmark/datasets/baziqa_contest8_2025_holdout.jsonl`  MaxCases: 40  Repeats: 3  Temperature: 0.0

| Label | Runs | Mean | Min | Max | Stdev |
| --- | ---: | ---: | ---: | ---: | ---: |
| rag-structured | 3 | 0.283 | 0.250 | 0.325 | 0.038 |

## Raw Runs

```json
[
  {
    "label": "rag-structured",
    "method": "structured_reasoning",
    "rag": true,
    "correct": 13,
    "total": 40,
    "accuracy": 0.325,
    "run_id": "d9e7d510"
  },
  {
    "label": "rag-structured",
    "method": "structured_reasoning",
    "rag": true,
    "correct": 11,
    "total": 40,
    "accuracy": 0.275,
    "run_id": "214a0707"
  },
  {
    "label": "rag-structured",
    "method": "structured_reasoning",
    "rag": true,
    "correct": 10,
    "total": 40,
    "accuracy": 0.25,
    "run_id": "1cfcaded"
  }
]
```
