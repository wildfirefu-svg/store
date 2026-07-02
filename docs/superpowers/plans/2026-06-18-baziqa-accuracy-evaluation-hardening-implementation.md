# BaziQA Accuracy Evaluation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable accuracy evaluation system that proves whether BaziQA/RAG changes improve BaZi judgment accuracy, reduces benchmark randomness, and identifies the next low-scoring domains to improve.

**Architecture:** Stabilize model benchmark calls first by forcing deterministic temperature, then add repeated-run statistics and leave-one-year-out evaluation. After measurement is reliable, improve retrieval with domain-aware and chart-feature-aware scoring, and enforce accuracy gates in generated reports.

**Tech Stack:** Python 3, pytest, PowerShell, FastAPI-adjacent benchmark runner, DeepSeek OpenAI-compatible chat API, BaziQA JSONL datasets, local SQLite benchmark run store.

---

## Current Evidence Baseline

Latest verified results on 2026-06-18:

- `docs/BAZIQA_RAG_REPORT.md`
- Holdout: `benchmark/datasets/baziqa_contest8_2025_holdout.jsonl`
- Holdout size: 40 questions
- Baseline direct: 8/40 = 20%
- RAG direct: 11/40 = 27.5%, rounded report value 28%
- RAG structured: 15/40 = 37.5%, rounded report value 38%

Current weakness:

- Single-run benchmark is still noisy.
- Sync model call does not expose deterministic temperature control.
- RAG corpus path is hardcoded to `benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl`.
- Relationship/family/health domains remain weak.
- Existing lift script compares rounded percentages, not exact fractions.

## File Structure

- Modify `claude_api.py`
  - Add optional `temperature` argument to `call_model_messages_sync`.
- Modify `benchmark/runners/run_benchmark.py`
  - Add `--temperature`, `--rag-corpus`, and exact metric output.
- Modify `case_index.py`
  - Add domain-aware and structured-feature-aware ranking.
- Modify `bazi_features.py`
  - Extract more chart features for retrieval scoring.
- Modify `rag_prompt_builder.py`
  - Include domain labels and retrieved-case match reasons in the prompt.
- Modify `scripts/verify_baziqa_rag_lift.ps1`
  - Use exact accuracy fractions and configurable corpus path.
- Create `benchmark/runners/split_baziqa_by_year.py`
  - Generate year-specific corpus/holdout splits.
- Create `benchmark/reports/accuracy_stats.py`
  - Compute mean, min, max, standard deviation, and confidence notes for repeated runs.
- Create `scripts/run_baziqa_repeated_eval.py`
  - Run repeated benchmark configurations and write JSON/Markdown summaries.
- Create `scripts/verify_baziqa_lovo.ps1`
  - Run leave-one-year-out evaluation across available years.
- Create/update tests:
  - `tests/test_claude_api.py`
  - `tests/test_benchmark_runner.py`
  - `tests/test_case_index.py`
  - `tests/test_bazi_features.py`
  - `tests/test_rag_prompt_builder.py`
  - `tests/test_baziqa_split_by_year.py`
  - `tests/test_accuracy_stats.py`

## Task 1: Make Benchmark Model Calls Deterministic

**Files:**
- Modify: `claude_api.py:113-164`
- Modify: `benchmark/runners/run_benchmark.py:75-235`
- Modify: `tests/test_claude_api.py`
- Modify: `tests/test_benchmark_runner.py`

- [ ] **Step 1: Add failing test for sync temperature payload**

Append to `tests/test_claude_api.py`:

```python
import json
import urllib.request


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":"A"}}]}'


def test_call_model_messages_sync_sends_temperature(monkeypatch):
    import claude_api

    captured = {}

    def fake_urlopen(req, timeout=180):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _Resp(captured["payload"])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(claude_api, "ANTHROPIC_API_KEY", "sk-test-deepseek-key-1234567890")

    out = claude_api.call_model_messages_sync(
        [{"role": "user", "content": "只回答A"}],
        provider="deepseek",
        model="deepseek-v4-pro",
        system_prompt="system",
        temperature=0.0,
    )

    assert out == "A"
    assert captured["payload"]["temperature"] == 0.0
```

- [ ] **Step 2: Run test and confirm it fails**

Run:

```powershell
python -m pytest tests/test_claude_api.py::test_call_model_messages_sync_sends_temperature -q
```

Expected:

```text
TypeError: call_model_messages_sync() got an unexpected keyword argument 'temperature'
```

- [ ] **Step 3: Add temperature argument to sync API call**

In `claude_api.py`, change:

```python
def call_model_messages_sync(messages, provider=None, model=None, system_prompt=None, timeout=180):
```

to:

```python
def call_model_messages_sync(messages, provider=None, model=None, system_prompt=None, timeout=180, temperature=None):
```

In the Anthropic payload block, add:

```python
        if temperature is not None:
            payload["temperature"] = float(temperature)
```

In the DeepSeek payload block, add:

```python
        if temperature is not None:
            payload["temperature"] = float(temperature)
```

Place each addition immediately after the payload dict is created.

- [ ] **Step 4: Add benchmark runner test for deterministic temperature**

Append to `tests/test_benchmark_runner.py`:

```python
def test_model_benchmark_passes_temperature_to_model_call(monkeypatch):
    from benchmark.runners import run_benchmark

    seen = {}

    def fake_call(prompt, provider, model, case=None, temperature=None):
        seen["temperature"] = temperature
        return "A"

    monkeypatch.setattr(run_benchmark, "call_model_sync", fake_call)
    cases = [{
        "case_id": "case-1",
        "question": "事业?",
        "options": ["A 好", "B 差", "C 平", "D 无"],
        "answer": "A",
        "domain": "career",
    }]

    result = run_benchmark.run_model_benchmark(
        cases,
        provider="deepseek",
        model="deepseek-v4-pro",
        prompt_version="srp_v1",
        max_cases=1,
        method="direct_choice",
        temperature=0.0,
    )

    assert result["predictions"]["case-1"] == "A"
    assert seen["temperature"] == 0.0
```

- [ ] **Step 5: Update benchmark runner signatures**

In `benchmark/runners/run_benchmark.py`, change:

```python
def call_model_sync(prompt, provider, model, case=None):
```

to:

```python
def call_model_sync(prompt, provider, model, case=None, temperature=None):
```

and pass the argument:

```python
            temperature=temperature,
```

inside `call_model_messages_sync(...)`.

Change:

```python
def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20, method='direct_choice'):
```

to:

```python
def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20, method='direct_choice', temperature=0.0):
```

Change the call:

```python
            answer = call_model_sync(prompt, provider, model, case=case)
```

to:

```python
            answer = call_model_sync(prompt, provider, model, case=case, temperature=temperature)
```

Add parser argument:

```python
    parser.add_argument('--temperature', type=float, default=0.0, help='Benchmark model temperature')
```

Pass it to `run_model_benchmark(...)`:

```python
            cases, args.provider, args.model, args.prompt_version, args.max_cases, method=args.method, temperature=args.temperature
```

- [ ] **Step 6: Run deterministic temperature tests**

Run:

```powershell
python -m pytest tests/test_claude_api.py::test_call_model_messages_sync_sends_temperature tests/test_benchmark_runner.py::test_model_benchmark_passes_temperature_to_model_call -q
```

Expected:

```text
2 passed
```

- [ ] **Step 7: Commit Task 1**

```powershell
git add claude_api.py benchmark/runners/run_benchmark.py tests/test_claude_api.py tests/test_benchmark_runner.py
git commit -m "test: make baziqa benchmark temperature deterministic"
```

## Task 2: Use Exact Accuracy Fractions In RAG Lift Reports

**Files:**
- Modify: `benchmark/runners/run_benchmark.py`
- Modify: `scripts/verify_baziqa_rag_lift.ps1`
- Modify: `scripts/render_baziqa_rag_report.py`
- Modify: `tests/test_benchmark_runner.py`

- [ ] **Step 1: Add exact summary line to benchmark output**

In `benchmark/runners/run_benchmark.py`, after:

```python
        print(f"  Accuracy: {round(choice_result['accuracy'] * 100)}%")
```

add:

```python
        print(f"  AccuracyExact: {choice_result['correct']}/{choice_result['total']}={choice_result['accuracy']:.6f}")
```

- [ ] **Step 2: Add test for exact summary line**

Append to `tests/test_benchmark_runner.py`:

```python
def test_benchmark_cli_prints_exact_accuracy(monkeypatch, tmp_path, capsys):
    from benchmark.runners import run_benchmark

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"c1","question":"?","options":["A","B","C","D"],"answer":"A"}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(run_benchmark, "call_model_sync", lambda *args, **kwargs: "A")
    rc = run_benchmark.main([
        "--dataset", str(dataset),
        "--model-runner",
        "--max-cases", "1",
        "--method", "direct_choice",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert "AccuracyExact: 1/1=1.000000" in out
```

- [ ] **Step 3: Update PowerShell parser to use exact accuracy**

In `scripts/verify_baziqa_rag_lift.ps1`, replace:

```powershell
    $accLine = $captured | Select-String -Pattern 'Accuracy:\s*(\d+(?:\.\d+)?)%'
    if (-not $accLine) {
        throw "Cannot parse accuracy for $Label"
    }
    $acc = [double]$accLine.Matches[0].Groups[1].Value
```

with:

```powershell
    $exactLine = $captured | Select-String -Pattern 'AccuracyExact:\s*(\d+)/(\d+)=(\d+(?:\.\d+)?)'
    if (-not $exactLine) {
        throw "Cannot parse exact accuracy for $Label"
    }
    $correct = [int]$exactLine.Matches[0].Groups[1].Value
    $total = [int]$exactLine.Matches[0].Groups[2].Value
    $acc = [double]$exactLine.Matches[0].Groups[3].Value
```

and return exact fields:

```powershell
    return [pscustomobject]@{ Label = $Label; Method = $Method; Rag = $Rag; Accuracy = $acc; Correct = $correct; Total = $total; RunId = $rid }
```

Change:

```powershell
$threshold = $baseline + 8
```

to:

```powershell
$threshold = $baseline + 0.08
```

- [ ] **Step 4: Update report renderer to display exact counts**

In `scripts/render_baziqa_rag_report.py`, format rows as:

```python
accuracy = float(item["Accuracy"])
correct = item.get("Correct", "")
total = item.get("Total", "")
acc_text = f"{accuracy * 100:.1f}%"
if correct != "" and total != "":
    acc_text += f" ({correct}/{total})"
```

Use `acc_text` in the accuracy table instead of rounded integer percent.

- [ ] **Step 5: Run exact metric tests**

Run:

```powershell
python -m pytest tests/test_benchmark_runner.py::test_benchmark_cli_prints_exact_accuracy -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit Task 2**

```powershell
git add benchmark/runners/run_benchmark.py scripts/verify_baziqa_rag_lift.ps1 scripts/render_baziqa_rag_report.py tests/test_benchmark_runner.py
git commit -m "fix: report exact baziqa accuracy fractions"
```

## Task 3: Add Repeated-Run Accuracy Statistics

**Files:**
- Create: `benchmark/reports/accuracy_stats.py`
- Create: `tests/test_accuracy_stats.py`
- Create: `scripts/run_baziqa_repeated_eval.py`

- [ ] **Step 1: Write accuracy statistics tests**

Create `tests/test_accuracy_stats.py`:

```python
from benchmark.reports.accuracy_stats import summarize_accuracy


def test_summarize_accuracy_computes_mean_min_max_and_spread():
    rows = [
        {"label": "rag-structured", "accuracy": 0.30},
        {"label": "rag-structured", "accuracy": 0.40},
        {"label": "rag-structured", "accuracy": 0.50},
    ]

    summary = summarize_accuracy(rows)
    stats = summary["rag-structured"]

    assert stats["runs"] == 3
    assert stats["mean"] == 0.4
    assert stats["min"] == 0.3
    assert stats["max"] == 0.5
    assert round(stats["stdev"], 6) == 0.1


def test_summarize_accuracy_groups_multiple_labels():
    rows = [
        {"label": "baseline", "accuracy": 0.20},
        {"label": "rag", "accuracy": 0.35},
    ]

    summary = summarize_accuracy(rows)

    assert summary["baseline"]["mean"] == 0.2
    assert summary["rag"]["mean"] == 0.35
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
python -m pytest tests/test_accuracy_stats.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'benchmark.reports.accuracy_stats'
```

- [ ] **Step 3: Implement statistics helper**

Create `benchmark/reports/accuracy_stats.py`:

```python
"""Accuracy summary helpers for repeated BaziQA benchmark runs."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Iterable, List


def _stdev(values: List[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def summarize_accuracy(rows: Iterable[dict]) -> Dict[str, dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row["label"])].append(float(row["accuracy"]))

    out = {}
    for label, values in grouped.items():
        out[label] = {
            "runs": len(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "stdev": _stdev(values),
        }
    return out
```

- [ ] **Step 4: Create repeated evaluation runner**

Create `scripts/run_baziqa_repeated_eval.py`:

```python
#!/usr/bin/env python3
"""Run repeated BaziQA benchmark commands and summarize accuracy stability."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from benchmark.reports.accuracy_stats import summarize_accuracy


EXACT_RE = re.compile(r"AccuracyExact:\s*(\d+)/(\d+)=(\d+(?:\.\d+)?)")
RUN_RE = re.compile(r"id=([a-f0-9]{8})")


def run_once(label, dataset, method, rag, max_cases, provider, model, temperature):
    cmd = [
        sys.executable,
        "benchmark/runners/run_benchmark.py",
        "--dataset", dataset,
        "--model-runner",
        "--provider", provider,
        "--model", model,
        "--max-cases", str(max_cases),
        "--method", method,
        "--temperature", str(temperature),
    ]
    if rag:
        cmd.append("--rag")
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    output = proc.stdout + "\n" + proc.stderr
    match = EXACT_RE.search(output)
    if not match:
        raise RuntimeError(f"Cannot parse AccuracyExact for {label}:\n{output[-2000:]}")
    run_match = RUN_RE.search(output)
    return {
        "label": label,
        "method": method,
        "rag": rag,
        "correct": int(match.group(1)),
        "total": int(match.group(2)),
        "accuracy": float(match.group(3)),
        "run_id": run_match.group(1) if run_match else "",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--max-cases", type=int, default=40)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output", default="docs/BAZIQA_REPEATED_EVAL_REPORT.md")
    args = parser.parse_args(argv)

    configs = [
        ("baseline-direct", "direct_choice", False),
        ("rag-direct", "direct_choice", True),
        ("rag-structured", "structured_reasoning", True),
    ]
    rows = []
    for _ in range(args.repeats):
        for label, method, rag in configs:
            rows.append(run_once(label, args.dataset, method, rag, args.max_cases, args.provider, args.model, args.temperature))

    summary = summarize_accuracy(rows)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# BaziQA Repeated Evaluation Report",
        "",
        f"Dataset: `{args.dataset}`  MaxCases: {args.max_cases}  Repeats: {args.repeats}  Temperature: {args.temperature}",
        "",
        "| Label | Runs | Mean | Min | Max | Stdev |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, stats in summary.items():
        lines.append(
            f"| {label} | {stats['runs']} | {stats['mean']:.3f} | {stats['min']:.3f} | {stats['max']:.3f} | {stats['stdev']:.3f} |"
        )
    lines.extend(["", "## Raw Runs", "", "```json", json.dumps(rows, ensure_ascii=False, indent=2), "```"])
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run non-network tests**

Run:

```powershell
python -m pytest tests/test_accuracy_stats.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit Task 3**

```powershell
git add benchmark/reports/accuracy_stats.py tests/test_accuracy_stats.py scripts/run_baziqa_repeated_eval.py
git commit -m "test: add repeated baziqa accuracy evaluation"
```

## Task 4: Generate Leave-One-Year-Out Splits

**Files:**
- Create: `benchmark/runners/split_baziqa_by_year.py`
- Create: `tests/test_baziqa_split_by_year.py`
- Modify: `benchmark/runners/run_benchmark.py`
- Modify: `scripts/verify_baziqa_rag_lift.ps1`

- [ ] **Step 1: Add split tests**

Create `tests/test_baziqa_split_by_year.py`:

```python
import json
from pathlib import Path

from benchmark.runners.split_baziqa_by_year import split_by_holdout_year


def _write_rows(path: Path, years):
    with path.open("w", encoding="utf-8") as f:
        for i, year in enumerate(years):
            f.write(json.dumps({
                "case_id": f"c{i}",
                "source_year": str(year),
                "person": {"person_id": f"p{i}", "birth": {"year": 1990}},
                "question": "命主事业?",
                "options": ["A", "B", "C", "D"],
                "answer": "A",
            }, ensure_ascii=False) + "\n")


def test_split_by_holdout_year_excludes_holdout_from_corpus(tmp_path):
    source = tmp_path / "all.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    holdout = tmp_path / "holdout.jsonl"
    _write_rows(source, [2021, 2022, 2025, 2025])

    stats = split_by_holdout_year(source, 2025, corpus, holdout)

    assert stats == {"corpus": 2, "holdout": 2}
    assert all(json.loads(line)["source_year"] != "2025" for line in corpus.read_text(encoding="utf-8").splitlines())
    assert all(json.loads(line)["source_year"] == "2025" for line in holdout.read_text(encoding="utf-8").splitlines())
```

- [ ] **Step 2: Implement split script**

Create `benchmark/runners/split_baziqa_by_year.py`:

```python
#!/usr/bin/env python3
"""Split a combined BaziQA JSONL into corpus and holdout files by source_year."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def split_by_holdout_year(source: Path, holdout_year: int, corpus_out: Path, holdout_out: Path) -> dict:
    source = Path(source)
    corpus_out = Path(corpus_out)
    holdout_out = Path(holdout_out)
    corpus_out.parent.mkdir(parents=True, exist_ok=True)
    holdout_out.parent.mkdir(parents=True, exist_ok=True)
    corpus_count = 0
    holdout_count = 0
    with source.open("r", encoding="utf-8") as src, corpus_out.open("w", encoding="utf-8") as corpus, holdout_out.open("w", encoding="utf-8") as holdout:
        for line in src:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if str(row.get("source_year")) == str(holdout_year):
                holdout.write(json.dumps(row, ensure_ascii=False) + "\n")
                holdout_count += 1
            else:
                corpus.write(json.dumps(row, ensure_ascii=False) + "\n")
                corpus_count += 1
    return {"corpus": corpus_count, "holdout": holdout_count}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--holdout-year", type=int, required=True)
    parser.add_argument("--corpus-out", required=True)
    parser.add_argument("--holdout-out", required=True)
    args = parser.parse_args(argv)
    stats = split_by_holdout_year(Path(args.source), args.holdout_year, Path(args.corpus_out), Path(args.holdout_out))
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Allow benchmark runner to use configurable RAG corpus**

In `benchmark/runners/run_benchmark.py`, replace the hardcoded corpus line:

```python
            corpus = _Path(__file__).resolve().parents[2] / "benchmark" / "datasets" / "baziqa_contest8_2021_2024_corpus.jsonl"
```

with:

```python
            corpus = _Path(os.environ.get(
                "BAZI_RAG_CORPUS",
                str(_Path(__file__).resolve().parents[2] / "benchmark" / "datasets" / "baziqa_contest8_2021_2024_corpus.jsonl"),
            ))
```

Add parser argument:

```python
    parser.add_argument('--rag-corpus', default='', help='JSONL corpus file used when --rag is enabled')
```

After `if args.rag:` add:

```python
        if args.rag_corpus:
            os.environ['BAZI_RAG_CORPUS'] = args.rag_corpus
```

- [ ] **Step 4: Add corpus parameter to RAG lift script**

In `scripts/verify_baziqa_rag_lift.ps1`, add parameter:

```powershell
    [string]$RagCorpus = ""
```

Inside `Invoke-Bench`, after `$argsList` is built and before `if ($Rag)`, add:

```powershell
    if ($Rag -and $RagCorpus) { $argsList += @("--rag-corpus", $RagCorpus) }
```

- [ ] **Step 5: Run split tests**

Run:

```powershell
python -m pytest tests/test_baziqa_split_by_year.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit Task 4**

```powershell
git add benchmark/runners/split_baziqa_by_year.py tests/test_baziqa_split_by_year.py benchmark/runners/run_benchmark.py scripts/verify_baziqa_rag_lift.ps1
git commit -m "feat: support leave-one-year-out baziqa splits"
```

## Task 5: Improve Domain-Aware Retrieval

**Files:**
- Modify: `bazi_features.py`
- Modify: `case_index.py`
- Modify: `rag_prompt_builder.py`
- Modify: `benchmark/runners/run_benchmark.py`
- Modify: `tests/test_bazi_features.py`
- Modify: `tests/test_case_index.py`
- Modify: `tests/test_rag_prompt_builder.py`

- [ ] **Step 1: Add feature extraction tests for domain and branches**

Append to `tests/test_bazi_features.py`:

```python
def test_extract_includes_branch_set_and_query_domain():
    chart = {**CHART_1990, "query_domain": "relationship"}

    out = extract(chart)
    s = out["structured"]

    assert s["query_domain"] == "relationship"
    assert s["branches"] == ["午", "巳", "丑", "辰"]
    assert "感情" in out["text_blob"] or "relationship" in out["text_blob"]
```

- [ ] **Step 2: Implement domain and branch features**

In `bazi_features.py`, add:

```python
DOMAIN_CN = {
    "career": "事业",
    "wealth": "财运",
    "relationship": "感情",
    "health": "健康",
    "family": "家庭",
    "annual_fortune": "流年",
    "study": "学业",
    "personality": "性格",
    "unknown": "综合",
}
```

Inside `extract(...)`, before `structured = { ... }`, add:

```python
    branches = [
        str(_safe(pillars, "year", "zhi")),
        str(_safe(pillars, "month", "zhi")),
        str(_safe(pillars, "day", "zhi")),
        str(_safe(pillars, "hour", "zhi")),
    ]
    branches = [b for b in branches if b]
    query_domain = str(chart.get("query_domain") or "unknown")
```

Add fields to `structured`:

```python
        "branches": branches,
        "query_domain": query_domain,
```

Add to text parts:

```python
    if query_domain:
        parts.append(f"问题领域{DOMAIN_CN.get(query_domain, query_domain)}")
    if branches:
        parts.append("地支" + "".join(branches))
```

- [ ] **Step 3: Add domain-aware retrieval test**

Append to `tests/test_case_index.py`:

```python
def test_domain_match_boosts_retrieved_cases(tmp_path):
    rows = [
        _row("career-case", 1980, "female", 1, 0, question="命主事业?", domain="career"),
        _row("relationship-case", 1980, "female", 1, 0, question="命主婚姻?", domain="relationship"),
    ]
    corpus = _make_corpus(tmp_path, rows)
    idx = CaseIndex(corpus)

    cases = idx.top_k_cases({
        "text_blob": "丁火 巳月 感情",
        "structured": {
            "gender": "female",
            "birth_decade": 1980,
            "day_master_gan": "丁",
            "query_domain": "relationship",
            "branches": ["巳", "午", "丑", "辰"],
        },
    }, k=1)

    assert cases[0]["person_id"] == "relationship-case"
```

- [ ] **Step 4: Store row domains in indexed facts and boost domain matches**

In `case_index.py`, in `_load(...)`, change bucket initialization:

```python
                bucket = people.setdefault(pid, {"person": person, "facts": [], "domains": Counter()})
```

After `fact = self._row_fact(row)`, add:

```python
                domain = str(row.get("domain") or "unknown")
                bucket["domains"][domain] += 1
```

When appending `cases`, add:

```python
                "domains": dict(bucket["domains"]),
```

In `top_k_cases(...)`, add:

```python
        query_domain = structured.get("query_domain")
        branches = set(structured.get("branches") or [])
```

Inside the scoring loop, after decade score:

```python
            if query_domain and case.get("domains", {}).get(query_domain):
                adj += 0.8
            if branches:
                overlap = sum(1 for b in branches if b in case["text_blob"])
                adj += min(overlap * 0.1, 0.4)
```

- [ ] **Step 5: Pass case domain into RAG feature extraction**

In `_resolve_system_prompt(case)` in `benchmark/runners/run_benchmark.py`, after chart is resolved, add:

```python
        if case and isinstance(chart, dict):
            chart = dict(chart)
            chart["query_domain"] = case.get("domain") or "unknown"
```

- [ ] **Step 6: Add match reasons to RAG prompt**

In `rag_prompt_builder.py`, change `_format_case(...)` to include domains:

```python
    domains = case.get("domains") or {}
    domain_text = "、".join(f"{k}:{v}" for k, v in sorted(domains.items())) or "unknown"
```

Add this line to the returned block after gender:

```python
        f"命例领域：{domain_text}\n"
```

- [ ] **Step 7: Run domain retrieval tests**

Run:

```powershell
python -m pytest tests/test_bazi_features.py tests/test_case_index.py tests/test_rag_prompt_builder.py -q
```

Expected:

```text
15 passed
```

- [ ] **Step 8: Commit Task 5**

```powershell
git add bazi_features.py case_index.py rag_prompt_builder.py benchmark/runners/run_benchmark.py tests/test_bazi_features.py tests/test_case_index.py tests/test_rag_prompt_builder.py
git commit -m "feat: boost baziqa retrieval by domain and chart features"
```

## Task 6: Add Accuracy Gates And Leave-One-Year-Out Runner

**Files:**
- Create: `scripts/verify_baziqa_lovo.ps1`
- Modify: `scripts/render_baziqa_rag_report.py`
- Modify: `docs/BAZIQA_RAG_REPORT.md`

- [ ] **Step 1: Create leave-one-year-out PowerShell runner**

Create `scripts/verify_baziqa_lovo.ps1`:

```powershell
param(
    [string]$Source = "benchmark/datasets/baziqa_contest8_2021_2025.jsonl",
    [string]$Years = "2021,2022,2023,2024,2025",
    [int]$MaxCases = 40,
    [string]$Provider = "deepseek",
    [string]$Model = "deepseek-v4-pro",
    [string]$Output = "docs/BAZIQA_LOVO_REPORT.md"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not $env:DEEPSEEK_API_KEY -and (Test-Path ".deepseek_key")) {
    $env:DEEPSEEK_API_KEY = (Get-Content ".deepseek_key" -Raw).Trim()
}
if (-not $env:DEEPSEEK_API_KEY -and -not $env:ANTHROPIC_API_KEY) {
    Write-Error "LOVO evaluation requires DEEPSEEK_API_KEY or ANTHROPIC_API_KEY."
    exit 2
}

$allRows = @()
foreach ($year in $Years.Split(",")) {
    $year = $year.Trim()
    if (-not $year) { continue }
    $corpus = "benchmark/datasets/baziqa_contest8_except_$year`_corpus.jsonl"
    $holdout = "benchmark/datasets/baziqa_contest8_$year`_holdout.jsonl"
    python benchmark/runners/split_baziqa_by_year.py --source $Source --holdout-year $year --corpus-out $corpus --holdout-out $holdout

    $env:BAZI_RAG_CORPUS = $corpus
    $captured = & python benchmark/runners/run_benchmark.py `
        --dataset $holdout `
        --model-runner `
        --provider $Provider `
        --model $Model `
        --max-cases $MaxCases `
        --method structured_reasoning `
        --temperature 0 `
        --rag 2>&1
    $captured | Write-Host
    $exactLine = $captured | Select-String -Pattern 'AccuracyExact:\s*(\d+)/(\d+)=(\d+(?:\.\d+)?)'
    if (-not $exactLine) { throw "Cannot parse exact accuracy for $year" }
    $idLine = $captured | Select-String -Pattern 'id=([a-f0-9]{8})'
    $allRows += [pscustomobject]@{
        Year = $year
        Correct = [int]$exactLine.Matches[0].Groups[1].Value
        Total = [int]$exactLine.Matches[0].Groups[2].Value
        Accuracy = [double]$exactLine.Matches[0].Groups[3].Value
        RunId = if ($idLine) { $idLine.Matches[0].Groups[1].Value } else { "" }
    }
}

$lines = @()
$lines += "# BaziQA Leave-One-Year-Out Report"
$lines += ""
$lines += "| Holdout Year | Correct | Total | Accuracy | RunId |"
$lines += "| --- | ---: | ---: | ---: | --- |"
foreach ($row in $allRows) {
    $pct = "{0:P1}" -f $row.Accuracy
    $lines += "| $($row.Year) | $($row.Correct) | $($row.Total) | $pct | $($row.RunId) |"
}
$mean = ($allRows | Measure-Object -Property Accuracy -Average).Average
$min = ($allRows | Measure-Object -Property Accuracy -Minimum).Minimum
$lines += ""
$lines += "Mean accuracy: $([math]::Round($mean * 100, 1))%"
$lines += "Minimum yearly accuracy: $([math]::Round($min * 100, 1))%"
$lines | Set-Content -Path $Output -Encoding UTF8

if ($mean -lt 0.40) {
    Write-Error "LOVO mean accuracy below 40%."
    exit 1
}
if ($min -lt 0.30) {
    Write-Error "At least one yearly holdout is below 30%."
    exit 1
}
```

- [ ] **Step 2: Define gate thresholds in RAG report renderer**

In `scripts/render_baziqa_rag_report.py`, append a gate section:

```python
lines.extend([
    "",
    "## Accuracy Gates",
    "",
    "- structured RAG target: >= 40.0% on 40-case holdout",
    "- direct RAG target: baseline + >= 8.0 percentage points",
    "- repeated evaluation target: min structured RAG >= 35.0%",
    "- leave-one-year-out target: mean >= 40.0%, minimum yearly accuracy >= 30.0%",
])
```

- [ ] **Step 3: Run smoke tests for split and stats without model calls**

Run:

```powershell
python -m pytest tests/test_baziqa_split_by_year.py tests/test_accuracy_stats.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 4: Run full real-model gates**

Run these only when model-call cost is acceptable:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_baziqa_rag_lift.ps1 -MaxCases 40
python scripts\run_baziqa_repeated_eval.py --repeats 3 --max-cases 40 --temperature 0
powershell -ExecutionPolicy Bypass -File scripts\verify_baziqa_lovo.ps1 -MaxCases 40
```

Expected:

```text
RAG lift: PASS
Repeated eval: rag-structured mean >= 0.40 and min >= 0.35
LOVO: mean >= 0.40 and minimum yearly accuracy >= 0.30
```

- [ ] **Step 5: Commit Task 6**

```powershell
git add scripts/verify_baziqa_lovo.ps1 scripts/render_baziqa_rag_report.py docs/BAZIQA_RAG_REPORT.md
git commit -m "test: add baziqa accuracy gates"
```

## Final Verification Matrix

Run non-network verification first:

```powershell
python -m pytest tests/test_claude_api.py tests/test_benchmark_runner.py tests/test_accuracy_stats.py tests/test_baziqa_split_by_year.py tests/test_bazi_features.py tests/test_case_index.py tests/test_rag_prompt_builder.py -q
python -m pytest -q -m "not e2e"
python -m pytest tests/test_e2e.py -q -s --tb=short
```

Expected:

- All commands exit `0`.
- No regression in browser E2E.
- No skipped test except the real-data test when `BAZIQA_REAL_DIR` is not set.

Run real-model verification when API cost is acceptable:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_baziqa_rag_lift.ps1 -MaxCases 40
python scripts\run_baziqa_repeated_eval.py --repeats 3 --max-cases 40 --temperature 0
powershell -ExecutionPolicy Bypass -File scripts\verify_baziqa_lovo.ps1 -MaxCases 40
```

Key pass points:

- `baseline-direct` and `rag-direct` use exact `Correct/Total` counts.
- `rag-direct` improves over same-session baseline by at least `0.08`.
- `rag-structured` reaches at least `0.40` mean accuracy in repeated runs.
- repeated-run `rag-structured` minimum is at least `0.35`.
- leave-one-year-out mean is at least `0.40`.
- leave-one-year-out minimum yearly accuracy is at least `0.30`.
- domain breakdown does not hide a domain with at least 5 questions below `0.25`.

## Self-Review

Spec coverage:

- Deterministic benchmark temperature: Task 1.
- Exact accuracy reporting: Task 2.
- Repeated evaluation: Task 3.
- Leave-one-year-out evaluation: Task 4 and Task 6.
- Low-domain improvement path: Task 5.
- Verifiable pass/fail gates: Task 6 and final matrix.

Placeholder scan:

- This plan contains concrete file paths, code snippets, commands, and expected outputs.
- The implementation steps are specified with runnable commands and concrete edits.

Type consistency:

- `temperature` is passed consistently from CLI to runner to `call_model_messages_sync`.
- `AccuracyExact` is parsed consistently by the repeated and lift scripts.
- `query_domain` and `branches` are introduced in `bazi_features.extract` and consumed by `case_index.CaseIndex.top_k_cases`.
