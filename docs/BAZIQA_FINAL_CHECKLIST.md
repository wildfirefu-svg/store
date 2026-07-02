# BaziQA Final Checklist

## Required Before Claiming Full Acceptance

- [x] BaziQA focused tests pass.
- [x] Core non-E2E tests pass.
- [x] Browser E2E tests pass.
- [x] Real BaziQA data import has a recorded row count: 688 rows across 2021-2025.
- [x] Real model smoke has recorded run IDs or a documented external blocker.
- [x] Benchmark dashboard has been opened and checked.
- [x] Worktree has no unexplained generated files after removing `.codegraph` generated diffs.

## Commands

```powershell
python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py tests/test_baziqa_real_import_contract.py tests/test_baziqa_smoke_script_contract.py -q
python -m pytest -q -m "not e2e"
python -m pytest tests/test_e2e.py -q -s --tb=short
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_real_import.ps1 -SourceDir F:\project\BaziQA\data
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_final.jsonl -MaxCases 2 -Method structured_reasoning
```

## Current External Blockers

- No BaziQA acceptance blocker remains after the real import passed.
- `.codegraph` generated local agent state was restored to avoid committing local index state.
