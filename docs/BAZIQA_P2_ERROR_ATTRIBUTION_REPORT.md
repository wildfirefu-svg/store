# BaziQA Error Attribution Report

## Overall

- Total cases: 40
- Correct: 9
- Accuracy: 0.2250

## Error Type Counts

| error_type | count |
|------------|-------|
| correct | 9 |
| predicted_wrong | 31 |

## Accuracy by Domain

| domain | total | correct | accuracy |
|--------|-------|---------|----------|
| annual_fortune | 2 | 0 | 0.0000 |
| career | 9 | 3 | 0.3333 |
| family | 4 | 1 | 0.2500 |
| health | 3 | 0 | 0.0000 |
| relationship | 7 | 2 | 0.2857 |
| study | 1 | 0 | 0.0000 |
| unknown | 14 | 3 | 0.2143 |

## Interpretation

- Domains with accuracy significantly below the overall mean are priority areas for corpus expansion or prompt tuning.
- A high `parser_invalid` count indicates the model is not following the confidence/final-answer output contract.
- A high `predicted_wrong` count indicates reasoning or retrieval gaps.
