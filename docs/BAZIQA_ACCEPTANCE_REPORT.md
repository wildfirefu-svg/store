# BaziQA Acceptance Report

## Test Commands

Core deterministic suite:

```powershell
python -m pytest -q -m "not e2e"
```

Browser E2E suite:

```powershell
python -m pytest tests/test_e2e.py -q -s --tb=short
```

BaziQA focused suite:

```powershell
python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py tests/test_baziqa_real_import_contract.py -q
```

Real BaziQA import (requires upstream BaziQA clone):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_real_import.ps1 -SourceDir <path-to-BaziQA-data>
```

Real model smoke (requires DeepSeek/Anthropic key + network):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -MaxCases 3
```

Dashboard verification:

```text
http://127.0.0.1:8000/benchmark
```

## Latest Result

- Core deterministic suite: 255 passed, 1 skipped (real-import contract auto-skipped), 6 deselected (E2E)
- Browser E2E suite: 6 passed
- BaziQA focused suite: included in core run, 31 of those pertain to BaziQA pipeline
- Real BaziQA import: requires operator to run `verify_baziqa_real_import.ps1` against upstream clone
- Real model smoke: requires operator to run `verify_baziqa_smoke.ps1` with valid API key
- Dashboard verification: requires operator to open `/benchmark` after a real run

## Final Status

- BaziQA focused tests: PASS
- Core deterministic suite: PASS (255 passed, 1 skipped, 6 deselected)
- Browser E2E: PASS (6/6, isolated DB via BAZI_DB_PATH, mocked SSE)
- Real BaziQA import: PENDING operator (script ready)
- Real model smoke: PENDING operator (script ready)
- Dashboard verification: PENDING operator (renderer covered by API contract test)
- Worktree cleanliness: clean after run; `.tmp/` and pycache untracked and ignored

## Remaining Risks

- BaziQA original repository is not vendored in this commit. Operator must clone it locally before running real-import script. This is by design to keep the repository compact and avoid vendoring upstream MIT-licensed data.
- Real-model smoke requires network and a valid DeepSeek/Anthropic key. CI runs without keys will be skipped by design.
- Dashboard rendering itself is exercised through the `aggregate_json` API contract test rather than a Playwright assertion to avoid false positives from local DB state.
