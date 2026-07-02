# BaziQA Final Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the remaining BaziQA acceptance items from pending/operator-only into verified project status with a reliable smoke script, real data import result, real model run result, dashboard verification, and clean worktree.

**Architecture:** Keep the existing BaziQA pipeline intact. Fix only the final acceptance layer: scripts, operator commands, acceptance report, and small tests that prevent false-positive verification.

**Tech Stack:** PowerShell, Python, pytest, FastAPI/uvicorn, SQLite, existing BaziQA benchmark runner, existing DeepSeek/Anthropic key loading.

---

## Current State

Already verified:

- BaziQA focused suite: `30 passed, 1 skipped`.
- Browser E2E: `6 passed`.
- Core deterministic suite: `256 passed, 1 skipped, 6 deselected`.
- Offline benchmark: runs and prints total/domain/year breakdown.
- `multi_turn` has a dedicated benchmark path in `benchmark/runners/run_benchmark.py`.

Still pending:

- Real upstream BaziQA data is not present at `F:\project\BaziQA\data`.
- Real BaziQA import has not produced verified row counts.
- Real DeepSeek/Anthropic smoke run has not been executed.
- `/benchmark` has not been visually verified against a stored run.
- `scripts/verify_baziqa_smoke.ps1` defaults to `tests/fixtures/baziqa/contest8_sample.jsonl`, but only `contest8_sample.json` exists. Its auto-build command points at fixture file names that the importer does not scan by default, so it can generate an empty JSONL.
- Worktree currently shows `.codegraph` modifications and two untracked report-test scripts.

---

## File Structure

Modify:

- `scripts/verify_baziqa_smoke.ps1`: make default smoke dataset deterministic and non-empty.
- `docs/BAZIQA_ACCEPTANCE_REPORT.md`: record final command outputs and remaining external blockers.
- `.gitignore`: ignore local report-test scratch scripts if they are not intended source, or intentionally add them with purpose.

Create:

- `tests/test_baziqa_smoke_script_contract.py`: verifies the fixture data path used by the smoke script can produce non-empty JSONL.
- `docs/BAZIQA_FINAL_CHECKLIST.md`: short operator checklist for final manual verification.

No changes:

- Do not modify `.deepseek_key` or `.anthropic_key`.
- Do not vendor upstream BaziQA data unless explicitly approved.
- Do not revert `.codegraph` changes unless the owner confirms they are disposable.

---

## Acceptance Targets

Final acceptance is complete when:

- `scripts/verify_baziqa_smoke.ps1` cannot create an empty fixture dataset silently.
- BaziQA focused tests pass.
- Core non-E2E tests pass.
- E2E tests pass.
- Real BaziQA import script is either passed with row counts recorded or explicitly blocked because upstream data is absent.
- Real model smoke script is either passed with run ID recorded or explicitly blocked because key/network is absent.
- `/benchmark` dashboard is opened and result is recorded.
- Worktree contains only intentional source/doc changes.

---

### Task 1: Fix Smoke Script Fixture Dataset Generation

**Files:**

- Modify: `scripts/verify_baziqa_smoke.ps1`
- Create: `tests/test_baziqa_smoke_script_contract.py`

- [ ] **Step 1: Write a contract test for fixture import**

Create `tests/test_baziqa_smoke_script_contract.py`:

```python
import json
from pathlib import Path

from benchmark.runners.import_baziqa_dataset import (
    load_contest8_file,
    normalize_contest8_questions,
    write_jsonl,
)


def test_smoke_fixture_json_can_build_non_empty_jsonl(tmp_path):
    fixture = Path("tests/fixtures/baziqa/contest8_sample.json")
    rows = normalize_contest8_questions(load_contest8_file(fixture))
    output = tmp_path / "contest8_sample.jsonl"

    write_jsonl(rows, output)

    loaded = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(loaded) == 2
    assert loaded[0]["case_id"]
    assert loaded[0]["answer"] in ["A", "B", "C", "D"]
```

- [ ] **Step 2: Run the contract test**

Run:

```powershell
python -m pytest tests/test_baziqa_smoke_script_contract.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Replace smoke script auto-build block**

In `scripts/verify_baziqa_smoke.ps1`, replace lines 13-21 with:

```powershell
if (-not (Test-Path $Dataset)) {
    $sampleJson = "tests/fixtures/baziqa/contest8_sample.json"
    if (-not (Test-Path $sampleJson)) {
        Write-Error "Dataset not found and no fixture available: $Dataset"
        exit 1
    }

    $tmpSource = ".tmp/baziqa_smoke_source"
    New-Item -ItemType Directory -Force $tmpSource | Out-Null
    Copy-Item $sampleJson "$tmpSource/contest8_2025.json" -Force
    python benchmark/runners/import_baziqa_dataset.py --source-dir $tmpSource --output $Dataset

    $lineCount = (Get-Content $Dataset -Encoding UTF8 | Measure-Object -Line).Lines
    if ($lineCount -lt 1) {
        Write-Error "Smoke dataset generation produced 0 rows: $Dataset"
        exit 3
    }
}
```

- [ ] **Step 4: Run smoke script without key to verify dataset guard**

Temporarily remove key env vars only for this command:

```powershell
$oldDeepSeek=$env:DEEPSEEK_API_KEY; $oldAnthropic=$env:ANTHROPIC_API_KEY; $env:DEEPSEEK_API_KEY=$null; $env:ANTHROPIC_API_KEY=$null; powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_test.jsonl; $env:DEEPSEEK_API_KEY=$oldDeepSeek; $env:ANTHROPIC_API_KEY=$oldAnthropic
```

Expected:

```text
Smoke aborted: please set DEEPSEEK_API_KEY or ANTHROPIC_API_KEY before running.
```

Also verify:

```powershell
Get-Content .tmp\baziqa_smoke_test.jsonl | Measure-Object -Line
```

Expected:

```text
Lines: 2
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/verify_baziqa_smoke.ps1 tests/test_baziqa_smoke_script_contract.py
git commit -m "fix: prevent empty baziqa smoke datasets"
```

---

### Task 2: Verify Real BaziQA Data Import

**Files:**

- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`
- Modify: `docs/BAZIQA_FINAL_CHECKLIST.md`

- [ ] **Step 1: Locate or clone upstream BaziQA**

Preferred location:

```text
F:\project\BaziQA
```

Expected data directory:

```text
F:\project\BaziQA\data
```

If the directory is missing, clone manually:

```powershell
git clone https://github.com/ChenJiangxi/BaziQA F:\project\BaziQA
```

Expected:

```text
F:\project\BaziQA\data exists
```

- [ ] **Step 2: Run real import script**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_real_import.ps1 -SourceDir F:\project\BaziQA\data
```

Expected:

```text
Imported rows: <count greater than 100>
Distinct years sampled: <one or more years>
Real BaziQA import passed.
```

If the script reports less than the expected 200 Contest8 rows, inspect file names:

```powershell
Get-ChildItem F:\project\BaziQA\data
```

Expected BaziQA files should include contest-year JSON files or an equivalent schema documented by upstream.

- [ ] **Step 3: Record exact result**

Update `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
- Real BaziQA import: PASS, source=`F:\project\BaziQA\data`, rows=<actual>, years=<actual>, date=<YYYY-MM-DD>
```

If source data is unavailable:

```markdown
- Real BaziQA import: BLOCKED, upstream data directory not present at `F:\project\BaziQA\data`, date=<YYYY-MM-DD>
```

- [ ] **Step 4: Commit report update**

```powershell
git add docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "docs: record real baziqa import status"
```

---

### Task 3: Run Real Model Smoke

**Files:**

- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Confirm key availability**

Run:

```powershell
if ($env:DEEPSEEK_API_KEY -or (Test-Path .deepseek_key) -or $env:ANTHROPIC_API_KEY -or (Test-Path .anthropic_key)) { "AI key found" } else { "AI key missing" }
```

Expected:

```text
AI key found
```

- [ ] **Step 2: Run smoke with direct choice first**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_direct.jsonl -MaxCases 2 -Method direct_choice
```

Expected:

```text
Benchmark run saved to database
SUMMARY:
Real-model smoke run finished.
```

- [ ] **Step 3: Run smoke with structured reasoning**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_structured.jsonl -MaxCases 2 -Method structured_reasoning
```

Expected:

```text
Benchmark run saved to database
SUMMARY:
Real-model smoke run finished.
```

- [ ] **Step 4: Run smoke with multi-turn**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_multiturn.jsonl -MaxCases 2 -Method multi_turn
```

Expected:

```text
Benchmark run saved to database
SUMMARY:
Real-model smoke run finished.
```

- [ ] **Step 5: Query latest runs**

Run:

```powershell
python -c "import data_store; [print(r['id'], r['dataset'], r['method'], r['accuracy']) for r in data_store.list_benchmark_runs(limit=5)]"
```

Expected:

```text
<run_id> <dataset> <method> <accuracy>
```

- [ ] **Step 6: Record exact result**

Update `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
- Real model smoke: PASS, provider=<provider>, methods=`direct_choice, structured_reasoning, multi_turn`, max_cases=2, run_ids=<ids>, date=<YYYY-MM-DD>
```

If key or network is unavailable:

```markdown
- Real model smoke: BLOCKED, reason=<missing key/network/provider error>, date=<YYYY-MM-DD>
```

- [ ] **Step 7: Commit**

```powershell
git add docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "docs: record baziqa model smoke status"
```

---

### Task 4: Verify Benchmark Dashboard Visually

**Files:**

- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`
- Modify: `docs/BAZIQA_FINAL_CHECKLIST.md`

- [ ] **Step 1: Ensure a benchmark run exists**

Run:

```powershell
python -c "import data_store; runs=data_store.list_benchmark_runs(limit=1); print(len(runs), runs[0]['id'] if runs else 'no-run')"
```

Expected:

```text
1 <run_id>
```

If no run exists, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_dashboard_smoke.jsonl -MaxCases 2 -Method direct_choice
```

- [ ] **Step 2: Start server**

Run:

```powershell
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8000
```

- [ ] **Step 3: Open dashboard**

Open:

```text
http://127.0.0.1:8000/benchmark
```

Verify these visible items:

- `Benchmark Runs` list is populated.
- `Choice Accuracy` card is not `--`.
- `Evidence Coverage` card is rendered.
- `Safety` card is rendered.
- `Accuracy by Year` appears when aggregate data exists.
- `Accuracy by Domain` appears when aggregate data exists.
- Markdown report loads in the report panel.
- Browser console has no JavaScript errors.

- [ ] **Step 4: Capture screenshot**

Save screenshot as:

```text
reports/baziqa_dashboard_acceptance.png
```

If `reports/` is ignored, keep the screenshot as local evidence and mention the path in the acceptance report.

- [ ] **Step 5: Record exact result**

Update `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
- Dashboard verification: PASS, url=`http://127.0.0.1:8000/benchmark`, run_id=<id>, screenshot=`reports/baziqa_dashboard_acceptance.png`, date=<YYYY-MM-DD>
```

If not verified:

```markdown
- Dashboard verification: BLOCKED, reason=<server/run/browser issue>, date=<YYYY-MM-DD>
```

- [ ] **Step 6: Commit**

```powershell
git add docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "docs: record benchmark dashboard verification"
```

---

### Task 5: Decide and Clean Worktree Artifacts

**Files:**

- Modify: `.gitignore` only if needed
- Possibly add: `scripts/test_all_reports_e2e.py`
- Possibly add: `scripts/test_all_reports_edge.py`

- [ ] **Step 1: Inspect untracked scripts**

Run:

```powershell
Get-Content scripts\test_all_reports_e2e.py -TotalCount 80
Get-Content scripts\test_all_reports_edge.py -TotalCount 80
```

Expected:

```text
Script purpose is clear from imports and main function.
```

- [ ] **Step 2: Decide whether scripts are source or scratch**

If they are useful verification scripts, add a short header comment to each:

```python
"""Manual verification helper for report generation edge cases."""
```

Then commit:

```powershell
git add scripts/test_all_reports_e2e.py scripts/test_all_reports_edge.py
git commit -m "test: add report verification helper scripts"
```

If they are scratch files, delete them:

```powershell
Remove-Item scripts\test_all_reports_e2e.py
Remove-Item scripts\test_all_reports_edge.py
```

Then confirm:

```powershell
git status --short
```

- [ ] **Step 3: Handle `.codegraph` changes**

If `.codegraph` changes are generated local index state, do not commit them. Ask the owner before deleting or reverting. Record decision in final response:

```text
.codegraph changes left untouched because they are generated local agent state.
```

- [ ] **Step 4: Commit `.gitignore` if changed**

If `.gitignore` was updated:

```powershell
git add .gitignore
git commit -m "chore: ignore local acceptance artifacts"
```

---

### Task 6: Final Acceptance Report Update

**Files:**

- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`
- Create: `docs/BAZIQA_FINAL_CHECKLIST.md`

- [ ] **Step 1: Create final checklist**

Create `docs/BAZIQA_FINAL_CHECKLIST.md`:

```markdown
# BaziQA Final Checklist

## Required Before Claiming Full Acceptance

- [ ] BaziQA focused tests pass.
- [ ] Core non-E2E tests pass.
- [ ] Browser E2E tests pass.
- [ ] Real BaziQA data import has a recorded row count.
- [ ] Real model smoke has a recorded run ID or a documented external blocker.
- [ ] Benchmark dashboard has been opened and checked.
- [ ] Worktree has no unexplained generated files.

## Commands

```powershell
python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py tests/test_baziqa_real_import_contract.py tests/test_baziqa_smoke_script_contract.py -q
python -m pytest -q -m "not e2e"
python -m pytest tests/test_e2e.py -q -s --tb=short
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_real_import.ps1 -SourceDir F:\project\BaziQA\data
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_final.jsonl -MaxCases 2 -Method structured_reasoning
```
```

- [ ] **Step 2: Update acceptance report with current checked results**

Update `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
## Final Status

- BaziQA focused tests: PASS/FAIL, command=<command>, result=<exact result>
- Core deterministic suite: PASS/FAIL, command=<command>, result=<exact result>
- Browser E2E: PASS/FAIL, command=<command>, result=<exact result>
- Real BaziQA import: PASS/BLOCKED/FAIL, result=<exact result>
- Real model smoke: PASS/BLOCKED/FAIL, result=<exact result>
- Dashboard verification: PASS/BLOCKED/FAIL, result=<exact result>
- Worktree cleanliness: PASS/FAIL, result=<git status summary>
```

- [ ] **Step 3: Run final deterministic commands**

Run:

```powershell
python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py tests/test_baziqa_real_import_contract.py tests/test_baziqa_smoke_script_contract.py -q
python -m pytest -q -m "not e2e"
python -m pytest tests/test_e2e.py -q -s --tb=short
```

Expected:

```text
all pass except real-import contract may skip when BAZIQA_REAL_DIR is not set
```

- [ ] **Step 4: Commit final docs**

```powershell
git add docs/BAZIQA_ACCEPTANCE_REPORT.md docs/BAZIQA_FINAL_CHECKLIST.md
git commit -m "docs: finalize baziqa acceptance checklist"
```

---

## Execution Order

1. Task 1: Fix smoke script so it cannot create empty fixture datasets.
2. Task 2: Run or explicitly block real BaziQA import.
3. Task 3: Run or explicitly block real model smoke.
4. Task 4: Verify dashboard visually.
5. Task 5: Decide worktree artifacts.
6. Task 6: Finalize acceptance report and checklist.

---

## Self-Review

Spec coverage:

- Real BaziQA import is covered by Task 2.
- Real model smoke is covered by Task 3.
- Dashboard visual acceptance is covered by Task 4.
- Smoke script defect is covered by Task 1.
- Worktree cleanup is covered by Task 5.
- Final documentation is covered by Task 6.

Placeholder scan:

- No placeholder implementation steps remain.
- Every task includes exact paths, commands, and expected outputs.

Type and name consistency:

- Uses existing `scripts/verify_baziqa_smoke.ps1`.
- Uses existing `scripts/verify_baziqa_real_import.ps1`.
- Uses existing `docs/BAZIQA_ACCEPTANCE_REPORT.md`.
- Uses existing BaziQA tests and benchmark modules.
