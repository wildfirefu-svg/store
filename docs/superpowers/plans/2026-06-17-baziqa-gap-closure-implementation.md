# BaziQA Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining BaziQA upgrade gaps so XuanJiZi can claim end-to-end verified benchmark ingestion, benchmark execution, E2E stability, model smoke validation, and dashboard visibility.

**Architecture:** Keep the current BaziQA implementation and fix only the incomplete acceptance points. Treat benchmark verification as three layers: deterministic unit/API tests, local E2E/browser tests, and optional real-model smoke tests gated by available API keys.

**Tech Stack:** Python, pytest, Playwright, FastAPI/uvicorn, SQLite, PowerShell, existing `benchmark` package, existing DeepSeek/Anthropic adapters.

---

## Current Gap Summary

The BaziQA upgrade is partially working:

- BaziQA-focused tests passed: `29 passed`.
- Benchmark/data/API focused tests passed: `66 passed`.
- Importer CLI works when files use real BaziQA names such as `contest8_2025.json` and `celebrity50_zh.json`.
- Offline benchmark outputs total accuracy, domain breakdown, and year breakdown.

Remaining gaps:

- `python -m pytest -q` timed out at 180 seconds.
- `python -m pytest tests/test_e2e.py -q` timed out at 120 seconds.
- Real BaziQA Contest8/Celebrity50 import has not been verified against the actual upstream data.
- `multi_turn` benchmark mode currently reuses the direct-choice prompt rather than performing true multi-turn calls.
- Real DeepSeek/Anthropic smoke benchmark has not been run.
- Dashboard rendering has not been visually verified in a browser.
- Test runs still modify tracked generated artifacts: `benchmark/reports/__pycache__/generate_report.cpython-310.pyc` and `quality/model_quality_report.json`.

---

## File Structure

Create:

- `tests/test_baziqa_real_import_contract.py`: contract tests for normalized real BaziQA output shape using fixtures.
- `scripts/verify_baziqa_real_import.ps1`: local verification script for a real BaziQA clone.
- `scripts/verify_baziqa_smoke.ps1`: local model smoke script with key/network guard.
- `docs/BAZIQA_ACCEPTANCE_REPORT.md`: final acceptance report template.

Modify:

- `tests/test_e2e.py`: make server lifecycle debuggable and reduce timeout-prone waits.
- `benchmark/runners/run_benchmark.py`: implement real `multi_turn` message construction and model calls.
- `tests/test_benchmark_runner.py`: cover real `multi_turn` behavior without network by monkeypatching.
- `benchmark/reports/generate_report.py`: avoid leaving tracked `__pycache__` changes during normal verification by moving report verification away from tracked bytecode paths if needed.
- `quality/model_quality_v2.py` or its calling tests: redirect generated quality output to `tmp_path` or a caller-provided output path.
- `.gitignore`: ignore `.tmp/` and benchmark verification scratch output if not already ignored.
- Optional: `pytest.ini`: define markers and default timeout strategy if no config exists.

Do not modify:

- `.deepseek_key`
- `.anthropic_key`
- `bazi_data.db` manually
- Generated `dist/` or `build/`

---

## Success Criteria

This plan is complete only when all of the following are true:

- BaziQA deterministic tests pass.
- `tests/test_e2e.py` completes under 120 seconds or is marked and separated from the core suite with a documented command.
- Full core test command completes without timeout.
- A real BaziQA source directory can produce `200` Contest8 rows and, when celebrity data is included, about `450` total rows.
- `multi_turn` mode sends at least two messages to the model adapter.
- A small real-model smoke run works when `DEEPSEEK_API_KEY` or `.deepseek_key` is available.
- `/benchmark` dashboard is opened and visually verified after a stored benchmark run.
- Running verification does not leave tracked generated files modified.

---

### Task 1: Stabilize and Diagnose E2E Tests

**Files:**

- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Replace hidden uvicorn output with captured log file**

Change the `live_server` fixture so subprocess output goes to `.tmp/e2e-uvicorn.log`, and cleanup is always executed in `finally`.

Use this exact replacement for the fixture:

```python
@pytest.fixture(scope="module")
def live_server():
    global BASE
    port = _free_port()
    BASE = f"http://127.0.0.1:{port}"
    import os
    from pathlib import Path

    tmp_dir = Path(".tmp")
    tmp_dir.mkdir(exist_ok=True)
    log_path = tmp_dir / "e2e-uvicorn.log"
    log_file = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env.setdefault("BAZI_API_RETRIES", "0")
    env.setdefault("DEEPSEEK_API_KEY", "test-e2e-no-real-call")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{BASE}/api/health", timeout=1) as resp:
                    if resp.status == 200:
                        yield BASE
                        return
            except Exception:
                time.sleep(0.5)
        pytest.fail(f"E2E server failed to start; see {log_path}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log_file.close()
```

- [ ] **Step 2: Fail fast on each E2E test**

Add timeout markers to every E2E test method:

```python
pytestmark = pytest.mark.timeout(45)
```

Place it after `BASE = "http://127.0.0.1:8000"`.

- [ ] **Step 3: Reduce long waits in chart creation**

Replace the fallback block in `create_chart`:

```python
    except Exception:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".mingzhu-card", timeout=10000)
```

with:

```python
    except Exception as exc:
        body_text = page.locator("body").text_content(timeout=2000) or ""
        raise AssertionError(f"Chart card did not appear after submit. Body={body_text[:500]}") from exc
```

This prevents one failed chart creation from hiding the root cause behind reload delays.

- [ ] **Step 4: Run E2E with verbose output**

Run:

```powershell
python -m pytest tests/test_e2e.py -q -s --tb=short
```

Expected:

```text
6 passed
```

If it fails, read:

```powershell
Get-Content .tmp\e2e-uvicorn.log -Tail 120
```

Expected failure output must identify the exact failing selector, HTTP route, or backend exception.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_e2e.py
git commit -m "test: make e2e failures diagnosable"
```

---

### Task 2: Separate Core and E2E Test Commands

**Files:**

- Create or modify: `pytest.ini`
- Modify: `tests/test_e2e.py`
- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Add pytest markers**

Create `pytest.ini` if it does not exist:

```ini
[pytest]
markers =
    e2e: browser-based end-to-end tests that start a live server
    slow: tests that may exceed 30 seconds
testpaths = tests
```

- [ ] **Step 2: Mark E2E module**

In `tests/test_e2e.py`, set:

```python
pytestmark = [pytest.mark.e2e, pytest.mark.timeout(45)]
```

Use this instead of the single timeout marker if Task 1 already added one.

- [ ] **Step 3: Define accepted verification commands**

Create `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
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
python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py -q
```

## Latest Result

- Core deterministic suite:
- Browser E2E suite:
- BaziQA focused suite:
- Real BaziQA import:
- Real model smoke:
- Dashboard verification:
```

- [ ] **Step 4: Run core suite**

Run:

```powershell
python -m pytest -q -m "not e2e"
```

Expected:

```text
pass without timeout
```

- [ ] **Step 5: Run E2E suite separately**

Run:

```powershell
python -m pytest tests/test_e2e.py -q -s --tb=short
```

Expected:

```text
6 passed
```

- [ ] **Step 6: Commit**

```powershell
git add pytest.ini tests/test_e2e.py docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "test: split core and browser verification"
```

---

### Task 3: Stop Verification From Modifying Tracked Artifacts

**Files:**

- Modify: `.gitignore`
- Modify: tests or scripts that write `quality/model_quality_report.json`
- Modify: tests that import `benchmark/reports/generate_report.py` if bytecode is tracked

- [ ] **Step 1: Confirm tracked generated files**

Run:

```powershell
git ls-files benchmark/reports/__pycache__/generate_report.cpython-310.pyc quality/model_quality_report.json
```

Expected:

```text
benchmark/reports/__pycache__/generate_report.cpython-310.pyc
quality/model_quality_report.json
```

- [ ] **Step 2: Add scratch ignores**

Append to `.gitignore`:

```gitignore

# Local verification scratch
.tmp/
benchmark/outputs/baziqa_smoke_*.md
benchmark/outputs/run_*.md
```

- [ ] **Step 3: Decide artifact policy**

If tracked generated files are not intentionally versioned, untrack them:

```powershell
git rm --cached benchmark/reports/__pycache__/generate_report.cpython-310.pyc
git rm --cached quality/model_quality_report.json
```

If they are intentionally versioned, update the tests that modify them to write to `tmp_path` instead. Use this pattern:

```python
def test_quality_report_generation(tmp_path, monkeypatch):
    output = tmp_path / "model_quality_report.json"
    monkeypatch.setenv("BAZI_QUALITY_REPORT_PATH", str(output))
    run_quality_report()
    assert output.exists()
```

- [ ] **Step 4: Verify clean status after tests**

Run:

```powershell
git status --short
python -m pytest tests/test_benchmark_report.py tests/test_data_store.py::TestBenchmarkRuns -q
git status --short
```

Expected:

```text
<same intentional source changes before and after>
```

- [ ] **Step 5: Commit**

```powershell
git add .gitignore tests quality benchmark
git commit -m "test: keep benchmark verification artifacts out of status"
```

---

### Task 4: Verify Real BaziQA Import Counts

**Files:**

- Create: `scripts/verify_baziqa_real_import.ps1`
- Create: `tests/test_baziqa_real_import_contract.py`
- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Add contract test for normalized output**

Create `tests/test_baziqa_real_import_contract.py`:

```python
import json
from pathlib import Path


def test_normalized_baziqa_rows_have_required_fields(tmp_path):
    output = tmp_path / "normalized.jsonl"
    rows = [
        {
            "case_id": "q1",
            "source": "contest8_2025",
            "source_year": "2025",
            "domain": "career",
            "person": {
                "person_id": "p1",
                "name": "命主",
                "gender": "female",
                "birth": {"year": 1990, "month": 1, "day": 1, "hour": 9, "minute": 0, "place": "北京"},
            },
            "question": "事业如何？",
            "options": ["A", "B", "C", "D"],
            "answer": "A",
            "expected_evidence": [],
            "verified_events": {},
            "difficulty": "unknown",
        }
    ]
    output.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows), encoding="utf-8")

    loaded = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    row = loaded[0]
    for key in ["case_id", "source", "domain", "person", "question", "options", "answer"]:
        assert key in row
    assert row["person"]["birth"]["year"] == 1990
    assert len(row["options"]) == 4
    assert row["answer"] in ["A", "B", "C", "D"]
```

- [ ] **Step 2: Add verification script**

Create `scripts/verify_baziqa_real_import.ps1`:

```powershell
param(
  [Parameter(Mandatory=$true)]
  [string]$SourceDir,
  [string]$Output = "benchmark/datasets/baziqa_contest8_2021_2025.jsonl"
)

$ErrorActionPreference = "Stop"

python benchmark/runners/import_baziqa_dataset.py --source-dir $SourceDir --output $Output
$contestRows = (Get-Content $Output | Measure-Object -Line).Lines
if ($contestRows -ne 200) {
  throw "Expected 200 Contest8 rows, got $contestRows"
}

$withCelebrity = "benchmark/datasets/baziqa_contest8_celebrity50.jsonl"
python benchmark/runners/import_baziqa_dataset.py --source-dir $SourceDir --output $withCelebrity --include-celebrity
$allRows = (Get-Content $withCelebrity | Measure-Object -Line).Lines
if ($allRows -lt 430 -or $allRows -gt 470) {
  throw "Expected about 450 rows with Celebrity50, got $allRows"
}

Write-Output "BaziQA import verified: Contest8=$contestRows, WithCelebrity=$allRows"
```

- [ ] **Step 3: Run contract test**

Run:

```powershell
python -m pytest tests/test_baziqa_real_import_contract.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Run real import verification**

Run with the actual BaziQA clone path:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_real_import.ps1 -SourceDir F:\project\BaziQA\data
```

Expected:

```text
BaziQA import verified: Contest8=200, WithCelebrity=<430-470>
```

- [ ] **Step 5: Record result**

Update `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
- Real BaziQA import: Contest8=200, Contest8+Celebrity50=<actual count>, source=<actual path>, date=<date>
```

- [ ] **Step 6: Commit**

```powershell
git add scripts/verify_baziqa_real_import.ps1 tests/test_baziqa_real_import_contract.py docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "test: verify real baziqa import counts"
```

---

### Task 5: Implement True Multi-Turn Benchmark Mode

**Files:**

- Modify: `benchmark/formatters/baziqa_prompt.py`
- Modify: `benchmark/runners/run_benchmark.py`
- Modify: `tests/test_benchmark_runner.py`

- [ ] **Step 1: Add test that multi-turn sends two messages**

Append to `tests/test_benchmark_runner.py`:

```python
def test_multi_turn_model_call_sends_context_and_question(monkeypatch):
    from benchmark.runners import run_benchmark

    captured = {}

    def fake_call(messages, provider, model, system_prompt):
        captured['messages'] = messages
        captured['provider'] = provider
        captured['model'] = model
        captured['system_prompt'] = system_prompt
        return 'A'

    monkeypatch.setattr(run_benchmark, 'call_model_messages_sync', fake_call)

    cases = [{
        'case_id': 'q1',
        'domain': 'career',
        'answer': 'A',
        'expected_evidence': [],
        'person': {'name': '命主', 'gender': 'male', 'birth': {'year': 1990, 'month': 1, 'day': 1, 'hour': 9, 'minute': 0, 'place': '北京'}},
        'question': '事业如何？',
        'options': ['A. 稳定', 'B. 投机', 'C. 不工作', 'D. 随机'],
    }]

    result = run_benchmark.run_model_benchmark(cases, 'deepseek', 'model', 'v1', max_cases=1, method='multi_turn')

    assert result['predictions']['q1'] == 'A'
    assert len(captured['messages']) == 2
    assert captured['messages'][0]['role'] == 'user'
    assert '命主资料' in captured['messages'][0]['content']
    assert '事业如何' in captured['messages'][1]['content']
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_benchmark_runner.py::test_multi_turn_model_call_sends_context_and_question -q
```

Expected:

```text
FAILED
AttributeError: module 'benchmark.runners.run_benchmark' has no attribute 'call_model_messages_sync'
```

- [ ] **Step 3: Add multi-turn messages formatter**

In `benchmark/formatters/baziqa_prompt.py`, add:

```python
def build_multi_turn_messages(case):
    return [
        {"role": "user", "content": format_multi_turn_context(case)},
        {"role": "user", "content": format_multi_turn_question(case)},
    ]
```

- [ ] **Step 4: Add message-based model call**

In `benchmark/runners/run_benchmark.py`, import:

```python
from benchmark.formatters.baziqa_prompt import build_multi_turn_messages
```

Add:

```python
def call_model_messages_sync(messages, provider, model, system_prompt):
    try:
        if provider == "deepseek":
            from claude_api import _call_deepseek
            response = _call_deepseek(messages, system_prompt, model)
        else:
            from claude_api import _call_anthropic
            response = _call_anthropic(messages, system_prompt, model)
        if isinstance(response, dict):
            content = response.get('content', '')
            if isinstance(content, list):
                content = content[0].get('text', '') if content else ''
            return str(content).strip()
        return str(response).strip()
    except Exception as e:
        raise RuntimeError(f"model_call_failed: {type(e).__name__}") from e
```

- [ ] **Step 5: Route multi-turn mode**

In `run_model_benchmark`, replace:

```python
prompt = build_benchmark_prompt(case, method=method)
try:
    answer = call_model_sync(prompt, provider, model)
```

with:

```python
try:
    if method == 'multi_turn':
        messages = build_multi_turn_messages(case)
        system_prompt = "你是一位专业命理师，先理解命主资料，再回答选择题。最终只输出选项字母。"
        answer = call_model_messages_sync(messages, provider, model, system_prompt)
    else:
        prompt = build_benchmark_prompt(case, method=method)
        answer = call_model_sync(prompt, provider, model)
```

- [ ] **Step 6: Run runner tests**

Run:

```powershell
python -m pytest tests/test_benchmark_runner.py -q
```

Expected:

```text
pass
```

- [ ] **Step 7: Commit**

```powershell
git add benchmark/formatters/baziqa_prompt.py benchmark/runners/run_benchmark.py tests/test_benchmark_runner.py
git commit -m "feat: implement true multi-turn baziqa benchmark"
```

---

### Task 6: Add Real-Model Smoke Verification

**Files:**

- Create: `scripts/verify_baziqa_smoke.ps1`
- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Create smoke script**

Create `scripts/verify_baziqa_smoke.ps1`:

```powershell
param(
  [string]$Dataset = "benchmark/datasets/baziqa_mini_v1.jsonl",
  [string]$Provider = "deepseek",
  [string]$Model = "deepseek-v4-pro",
  [string]$Method = "structured_reasoning",
  [int]$MaxCases = 3
)

$ErrorActionPreference = "Stop"

if (-not $env:DEEPSEEK_API_KEY -and -not (Test-Path ".deepseek_key") -and -not $env:ANTHROPIC_API_KEY -and -not (Test-Path ".anthropic_key")) {
  throw "No AI key found. Set DEEPSEEK_API_KEY or create .deepseek_key / .anthropic_key."
}

python benchmark/runners/run_benchmark.py `
  --dataset $Dataset `
  --model-runner `
  --provider $Provider `
  --model $Model `
  --method $Method `
  --prompt-version srp_smoke `
  --max-cases $MaxCases `
  --output-dir benchmark/outputs
```

- [ ] **Step 2: Run smoke only when key/network are available**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -MaxCases 3
```

Expected:

```text
Benchmark run saved to database
SUMMARY:
```

If it fails, record exact failure category:

- missing key
- invalid key
- no network
- provider HTTP error
- all model calls failed

- [ ] **Step 3: Confirm run stored**

Run:

```powershell
python - <<'PY'
import data_store
runs = data_store.list_benchmark_runs(limit=5)
print(runs[0]['id'], runs[0]['dataset'], runs[0]['method'], runs[0]['accuracy'])
PY
```

Expected:

```text
<run id> baziqa_mini_v1.jsonl structured_reasoning <accuracy>
```

- [ ] **Step 4: Record result**

Update `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
- Real model smoke: provider=<provider>, model=<model>, method=<method>, max_cases=3, run_id=<id>, result=<pass/fail>, date=<date>
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/verify_baziqa_smoke.ps1 docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "chore: add baziqa real-model smoke verification"
```

---

### Task 7: Verify Benchmark Dashboard Visually

**Files:**

- Modify: `static/js/benchmark-dashboard.js` only if verification finds rendering gaps
- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Ensure at least one stored run exists**

Run:

```powershell
python - <<'PY'
import data_store
runs = data_store.list_benchmark_runs(limit=1)
print(len(runs), runs[0]['id'] if runs else 'no-runs')
PY
```

Expected:

```text
1 <run id>
```

If no run exists, run the smoke script or create a deterministic fake run through `data_store.save_benchmark_run`.

- [ ] **Step 2: Start the app**

Run:

```powershell
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8000
```

- [ ] **Step 3: Open dashboard in browser**

Open:

```text
http://127.0.0.1:8000/benchmark
```

Verify:

- Run list loads.
- Accuracy card renders.
- Evidence card renders.
- Safety card renders.
- Markdown report loads.
- Weak domains display when report contains low domain scores.
- Browser console has no JavaScript errors.

- [ ] **Step 4: Fix rendering if needed**

If `aggregate_json` is returned by `/api/benchmark/runs` but dashboard does not render it, add to `static/js/benchmark-dashboard.js`:

```javascript
function renderAggregate(run) {
    const aggregate = run.aggregate_json || {};
    renderBreakdown(els.yearBreakdown, 'Accuracy by Year', aggregate.by_year || {});
    renderBreakdown(els.domainBreakdown, 'Accuracy by Domain', aggregate.by_domain || {});
}
```

Call it inside the run click handler:

```javascript
renderAggregate(run);
```

- [ ] **Step 5: Record result**

Update `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
- Dashboard verification: pass/fail, browser=<browser>, run_id=<id>, date=<date>, notes=<notes>
```

- [ ] **Step 6: Commit**

```powershell
git add static/js/benchmark-dashboard.js docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "test: verify benchmark dashboard rendering"
```

---

### Task 8: Final Acceptance Run

**Files:**

- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Run BaziQA focused tests**

Run:

```powershell
python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py tests/test_baziqa_real_import_contract.py -q
```

Expected:

```text
pass
```

- [ ] **Step 2: Run core deterministic suite**

Run:

```powershell
python -m pytest -q -m "not e2e"
```

Expected:

```text
pass without timeout
```

- [ ] **Step 3: Run E2E suite**

Run:

```powershell
python -m pytest tests/test_e2e.py -q -s --tb=short
```

Expected:

```text
6 passed
```

- [ ] **Step 4: Run real import verification**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_real_import.ps1 -SourceDir F:\project\BaziQA\data
```

Expected:

```text
BaziQA import verified: Contest8=200, WithCelebrity=<430-470>
```

- [ ] **Step 5: Run optional real-model smoke**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -MaxCases 3
```

Expected:

```text
Benchmark run saved to database
SUMMARY:
```

If unavailable due to key/network, record this as blocked, not passed.

- [ ] **Step 6: Check clean worktree**

Run:

```powershell
git status --short
```

Expected:

```text
<only intentional acceptance report updates>
```

- [ ] **Step 7: Finalize acceptance report**

Update `docs/BAZIQA_ACCEPTANCE_REPORT.md`:

```markdown
## Final Status

- BaziQA focused tests:
- Core deterministic suite:
- Browser E2E:
- Real BaziQA import:
- Real model smoke:
- Dashboard verification:
- Worktree cleanliness:

## Remaining Risks

- 
```

- [ ] **Step 8: Commit**

```powershell
git add docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "docs: record baziqa acceptance results"
```

---

## Execution Order

1. Task 1: Make E2E failures diagnosable.
2. Task 2: Split core and E2E verification.
3. Task 3: Stop test artifact pollution.
4. Task 4: Verify real BaziQA import counts.
5. Task 5: Implement true multi-turn benchmark.
6. Task 6: Add real-model smoke verification.
7. Task 7: Verify dashboard visually.
8. Task 8: Final acceptance run.

This order fixes test reliability before claiming benchmark/product success.

---

## Self-Review

Spec coverage:

- E2E timeout is covered by Tasks 1-2.
- Full test timeout is covered by Task 2 and Task 8.
- Real BaziQA import is covered by Task 4.
- True multi-turn mode is covered by Task 5.
- Real model smoke is covered by Task 6.
- Dashboard visual verification is covered by Task 7.
- Generated tracked artifact pollution is covered by Task 3.

Placeholder scan:

- No placeholder steps are left.
- Each task includes file paths, code snippets or exact command lines, and expected outcomes.

Type and name consistency:

- Uses existing `benchmark/runners/run_benchmark.py`.
- Uses existing `benchmark/formatters/baziqa_prompt.py`.
- Uses existing `data_store.list_benchmark_runs`.
- Uses existing test names and current E2E fixture structure.
