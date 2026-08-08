# 6D v1 r1 Errata

**Date:** 2026-08-08
**Run:** phase6-6d-v1-20260808-r1
**Original merged_details_sha256:** 3539a5fb0e101bff1f07d5b6490cab90ee00cc3bfbbf60bc5f6387547e49086d

## Corrections

### 1. min_case_delta normalization

- **Reported:** -2 (raw min)
- **Correct:** -0.666667 (min / REPEATS)
- **Impact:** Verdict unaffected (NON_INFERIOR depends on paired_delta only)
- **Root cause:** [phase6_6d_orchestrator.py:809](scripts/phase6_6d_orchestrator.py) omitted `/ REPEATS`

### 2. Missing independent run manifest

- **Issue:** run_manifest existed only in memory, not persisted as file
- **Impact:** No four-layer provenance cross-validation (manifest/run_context/receipt/audit)
- **Fix:** run_manifest.json now persisted alongside run_context.json

### 3. Report completeness

- **Issue:** report.md lacked off/on accuracy, yearly breakdown, non-zero delta cases
- **Fix:** Report now includes full breakdown

## Accuracy (recomputed from archived merged_details.jsonl)

| Condition | Correct | Total | Rate |
|---|---|---|---|
| OFF | 19 | 93 | 20.43% |
| ON  | 18 | 93 | 19.35% |

## Yearly Breakdown

| Year | OFF | ON | Delta |
|---|---|---|---|
| 2024 | 11/54 | 10/54 | -1.85pp |
| 2025 | 8/39 | 8/39 | 0.00pp |

## Non-zero Case Deltas

| Case ID | OFF | ON | Delta |
|---|---|---|---|
| chaozhou_male_19720108_P002-Q9 | 1/3 | 0/3 | -1 |
| female_19830326_P006-Q27 | 1/3 | 2/3 | +1 |
| female_19830326_P006-Q28 | 2/3 | 1/3 | -1 |
| female_19830326_P006-Q30 | 1/3 | 3/3 | +2 |
| hongkong_female_19870705_P002-Q6 | 2/3 | 0/3 | -2 |
| hongkong_female_19870705_P002-Q8 | 0/3 | 2/3 | +2 |
| male_19710412_P005-Q21 | 2/3 | 0/3 | -2 |

## Interpretation

- Time context injection did NOT improve accuracy (OFF 20.43% vs ON 19.35%)
- 2024 slight degradation (-1.85pp), 2025 flat (0.00pp)
- NON_INFERIOR is the pre-frozen -2pp threshold classification, not statistical non-inferiority proof
- Recommendation: keep single protocol, do not promote 6D time context injection
