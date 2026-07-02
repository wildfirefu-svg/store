# BaziQA RAG Lift Report

Holdout: `benchmark/datasets/baziqa_contest8_2025_holdout.jsonl`  Provider: `deepseek`  Model: `deepseek-v4-pro`  MaxCases: 40  Temperature: 0.0

| Run | Method | RAG | Accuracy | Delta | RunId |
| --- | ------ | --- | -------- | ----- | ----- |
| baseline-direct | direct_choice | OFF | 22.5% (9/40) | +0.0pp | e7702f6d |
| rag-direct | direct_choice | ON | 27.5% (11/40) | +5.0pp | b6678bbc |
| rag-structured | structured_reasoning | ON | 32.5% (13/40) | +10.0pp | 5be0a212 |

## Verdict

- baseline=22.5%, direct threshold=baseline+8pp = 30.5%
- rag-direct=27.5% (below direct threshold)
- rag-structured=32.5% (below structured target 40.0%)
- status=BLOCKED

## Accuracy Gates

- structured RAG target: >= 40.0% on 40-case holdout
- direct RAG target: baseline + >= 8.0 percentage points
- repeated evaluation target: min structured RAG >= 35.0%
- leave-one-year-out target: mean >= 40.0%, minimum yearly accuracy >= 30.0%

## Notes

- 这次是真实 API + `temperature=0.0` 的确定性评测结果，覆盖完整 2025 holdout 40 题。
- RAG 相对 baseline 有提升：direct +5.0pp，structured +10.0pp。
- 但 direct 未达到 baseline+8pp gate，structured 也未达到 40% gate，因此按 hardening 计划应标记为 BLOCKED，而不是 PASS。
- 与早先非确定性运行的 38% 不同，本次确定性评测更适合作为后续 gate 基线。
