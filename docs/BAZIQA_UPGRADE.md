# BaziQA Upgrade Guide

## Purpose

BaziQA is used as XuanJiZi's objective benchmark for BaZi-specific symbolic and temporal reasoning. It is not a replacement for user-facing consultation quality, but it is the release gate for model and prompt changes.

## Data Sources

- Upstream: https://github.com/ChenJiangxi/BaziQA
- Paper: https://arxiv.org/abs/2602.12889
- Contest8: 2021-2025, 200 four-choice questions
- Celebrity50: 50 public figures, about 250 questions and event timelines

## Splits

- Development: Contest8 2021-2023
- Validation: Contest8 2024
- Locked test: Contest8 2025
- Timeline calibration: Celebrity50

## Commands

Normalize data:

```powershell
python benchmark/runners/import_baziqa_dataset.py --source-dir F:\project\BaziQA\data --output benchmark/datasets/baziqa_contest8_2021_2025.jsonl
```

Offline scoring:

```powershell
python benchmark/runners/run_benchmark.py --dataset benchmark/datasets/baziqa_contest8_2021_2025.jsonl --predictions benchmark/outputs/sample_predictions.json
```

Model scoring:

```powershell
python benchmark/runners/run_benchmark.py --dataset benchmark/datasets/baziqa_contest8_2021_2025.jsonl --model-runner --provider deepseek --model deepseek-v4-pro --method structured_reasoning --prompt-version srp_v2 --max-cases 40
```

## Release Gate

A prompt or model change may ship only when:

- Locked test accuracy does not drop by more than 0.03.
- Safety score does not drop by more than 0.05.
- Health, family, and relationship domains do not regress if they were touched.
- Failed model calls are below 5%.

## Product Use

- Contest8 improves prompt/model selection.
- Celebrity50 improves life-event mapping and timeline calibration.
- Weak domains should become roadmap items for PromptEngine and local rule improvements.
