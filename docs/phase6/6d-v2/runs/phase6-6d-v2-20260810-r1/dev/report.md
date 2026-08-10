# 6D time-context ablation report
- Model protocol: DeepSeek-V4-Flash non-thinking
- Provider: deepseek
- Model: deepseek-v4-flash
- Thinking mode: disabled
- Run ID: phase6-6d-v2-20260810-r1
- OFF data source: 6d-v1:phase6-6d-v1-20260808-r1-6d-dev-2026-08-07-deepseek-deepseek-v4-flash-cc36fefa94c5 (reused from 6D v1 archive)
- gate: **NON_INFERIOR**
- paired_delta: 0.032258
- min_case_delta: -0.333333
- parser rate: 1.0
- budget: scheduled 186 / attempted 93 / cap 243

## Accuracy

| Condition | Correct | Total | Rate |
|---|---|---|---|
| OFF | 19 | 93 | 20.43% |
| ON  | 22 | 93 | 23.66% |

## Yearly Breakdown

| Year | OFF | ON | Delta |
|---|---|---|---|
| 2024 | 11/54 | 14/54 | +5.56pp |
| 2025 | 8/39 | 8/39 | +0.00pp |

## Non-zero Case Deltas

| Case ID | OFF | ON | Delta |
|---|---|---|---|
| chaozhou_male_19720108_P002-Q9 | 1/3 | 0/3 | -1 |
| female_19800921_P007-Q33 | 2/3 | 1/3 | -1 |
| female_19800921_P007-Q34 | 0/3 | 2/3 | +2 |
| female_19830326_P006-Q26 | 0/3 | 1/3 | +1 |
| female_19830326_P006-Q27 | 1/3 | 2/3 | +1 |
| female_19830326_P006-Q28 | 2/3 | 3/3 | +1 |
| female_19830326_P006-Q30 | 1/3 | 3/3 | +2 |
| female_19831028_P004-Q17 | 1/3 | 0/3 | -1 |
| guangdong_female_19511114_P001-Q5 | 3/3 | 2/3 | -1 |
| hongkong_female_19870705_P002-Q6 | 2/3 | 3/3 | +1 |
| hongkong_female_19870705_P002-Q8 | 0/3 | 1/3 | +1 |
| male_19611230_P003-Q12 | 0/3 | 1/3 | +1 |
| male_19710412_P005-Q21 | 2/3 | 1/3 | -1 |
| male_19710412_P005-Q25 | 1/3 | 0/3 | -1 |
| miyazaki_male_19830421_P003-Q15 | 1/3 | 0/3 | -1 |

off/on paired ablation; 31 temporal-routed cases x 3 repeats; group-pair AB/BA scheduling.