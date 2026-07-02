# BaziQA Choice And Report Accuracy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise stable BaziQA multiple-choice accuracy while adding deterministic checks that also reduce hard factual errors in real BaZi reports.

**Architecture:** The first layer constrains model output with a fixed confidence protocol and a strict final-answer parser. The second layer runs controlled RAG `k` ablation and per-case error attribution to find whether wrong answers come from model instability, noisy retrieval, weak domain matching, or parser failure. The third layer reuses deterministic BaZi rule validation to gate real report quality so BaziQA improvements are checked against user-facing reports.

**Tech Stack:** Python 3, pytest, FastAPI project modules, DeepSeek model runner, JSONL benchmark datasets, existing BaziQA RAG modules (`case_index.py`, `rag_prompt_builder.py`, `bazi_features.py`), existing report validator (`bazi_report_validator.py`).

---

## Current Baseline

Read these files before starting implementation:

- `docs/BAZIQA_PROJECT_ROADMAP.md`
- `docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md`
- `docs/BAZIQA_ACCEPTANCE_REPORT.md`
- `benchmark/scorers/choice_accuracy.py`
- `benchmark/formatters/baziqa_prompt.py`
- `benchmark/runners/run_benchmark.py`
- `case_index.py`
- `rag_prompt_builder.py`
- `bazi_report_validator.py`

Current evidence:

- `rag-structured` single run reached `42.5%`, but repeats=3 only reached mean `30.0%`, min `27.5%`, max `35.0%`.
- Trace diagnosis shows RAG top-k is stable, but model answers vary under identical context.
- Existing report validator already catches hard errors such as missing branch combinations, wrong storage branch, and unsupported "财星当令" claims.

Target gates for this plan:

- BaziQA `rag-structured` repeats=3: mean >= `40.0%`, min >= `35.0%`, max-min <= `5.0 pp`.
- Parser compliance: >= `95%` of model outputs contain a parseable fixed final answer.
- Report quality smoke: selected real命主 reports contain no validator `error` severity issues.
- No acceptance report should claim the old `42.5%` single run as stable success.

## File Structure

- Modify `benchmark/scorers/choice_accuracy.py`: add strict final-answer extraction and confidence-table parsing while keeping old parser fallback.
- Modify `tests/test_benchmark_choice_accuracy.py`: cover final-answer, confidence, fallback, and invalid outputs.
- Modify `benchmark/formatters/baziqa_prompt.py`: strengthen structured reasoning prompt with A/B/C/D confidence contract.
- Modify `tests/test_baziqa_prompt_formatter.py`: verify the output contract is present.
- Modify `benchmark/runners/run_benchmark.py`: add `--rag-k`, pass it through trace and system prompt retrieval, and store parser metadata in case details.
- Modify `rag_prompt_builder.py`: accept `top_k` if the current implementation has a hardcoded `3`.
- Modify `tests/test_benchmark_runner.py` and `tests/test_rag_prompt_builder.py`: verify `--rag-k` affects retrieval and trace.
- Create `scripts/run_baziqa_k_ablation.py`: run k=1/2/3 repeats and write a Markdown report.
- Create `tests/test_baziqa_k_ablation_script.py`: verify command construction and report rendering without network.
- Create `scripts/analyze_baziqa_error_attribution.py`: turn trace JSONL into domain/type/error attribution.
- Create `tests/test_baziqa_error_attribution.py`: verify attribution labels.
- Create `scripts/verify_report_quality_gate.py`: generate or read sample reports and fail on deterministic validator errors.
- Create `tests/test_report_quality_gate.py`: verify the quality gate fails on hard errors and passes clean reports.
- Update `docs/BAZIQA_PROJECT_ROADMAP.md` and `docs/BAZIQA_ACCEPTANCE_REPORT.md`: separate stable results from historical single-run results.

---

### Task 1: Strict Final Answer Parser

**Files:**
- Modify: `benchmark/scorers/choice_accuracy.py`
- Modify: `tests/test_benchmark_choice_accuracy.py`

- [ ] **Step 1: Add failing parser tests**

Append these tests to `tests/test_benchmark_choice_accuracy.py`:

```python
from benchmark.scorers.choice_accuracy import extract_choice, extract_choice_with_meta


def test_extract_choice_prefers_final_answer_line():
    text = "分析过程里提到 A 和 C。\n最终答案：D"
    assert extract_choice(text) == "D"
    meta = extract_choice_with_meta(text)
    assert meta == {"choice": "D", "source": "final_answer", "valid": True}


def test_extract_choice_uses_confidence_table_when_final_line_missing():
    text = "\n".join([
        "A: 30",
        "B: 65",
        "C: 20",
        "D: 10",
    ])
    assert extract_choice(text) == "B"
    meta = extract_choice_with_meta(text)
    assert meta == {"choice": "B", "source": "confidence", "valid": True}


def test_extract_choice_falls_back_to_legacy_patterns():
    assert extract_choice("我选择 c，因为命局以水为忌。") == "C"
    meta = extract_choice_with_meta("我选择 c，因为命局以水为忌。")
    assert meta == {"choice": "C", "source": "legacy", "valid": True}


def test_extract_choice_returns_invalid_meta_for_unparseable_text():
    assert extract_choice("无法判断") is None
    meta = extract_choice_with_meta("无法判断")
    assert meta == {"choice": None, "source": "none", "valid": False}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_benchmark_choice_accuracy.py -q
```

Expected: FAIL because `extract_choice_with_meta` does not exist and `extract_choice` does not prefer `最终答案：X`.

- [ ] **Step 3: Implement parser metadata**

Replace the current `extract_choice` implementation in `benchmark/scorers/choice_accuracy.py` with this code, keeping imports `json` and `re`:

```python
def _legacy_extract_choice(text):
    if text is None:
        return None
    s = str(text).strip()
    if re.fullmatch(r'[A-Da-d]', s):
        return s.upper()
    patterns = [
        r'答案\s*[:：]?\s*([A-Da-d])',
        r'选择\s*([A-Da-d])',
        r'我选\s*([A-Da-d])',
        r'选项\s*([A-Da-d])',
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return m.group(1).upper()
    return None


def _extract_final_answer_choice(s):
    matches = re.findall(r'最终答案\s*[:：]\s*([A-Da-d])', s)
    if not matches:
        return None
    return matches[-1].upper()


def _extract_confidence_choice(s):
    scores = {}
    for choice, score in re.findall(r'(?m)^\s*([A-Da-d])\s*[:：]\s*([0-9]{1,3})(?:\s*/\s*100)?\s*$', s):
        value = int(score)
        if 0 <= value <= 100:
            scores[choice.upper()] = value
    if not scores:
        return None
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ordered[0][0]


def extract_choice_with_meta(text):
    if text is None:
        return {"choice": None, "source": "none", "valid": False}
    s = str(text).strip()
    choice = _extract_final_answer_choice(s)
    if choice:
        return {"choice": choice, "source": "final_answer", "valid": True}
    choice = _extract_confidence_choice(s)
    if choice:
        return {"choice": choice, "source": "confidence", "valid": True}
    choice = _legacy_extract_choice(s)
    if choice:
        return {"choice": choice, "source": "legacy", "valid": True}
    return {"choice": None, "source": "none", "valid": False}


def extract_choice(text):
    return extract_choice_with_meta(text)["choice"]
```

- [ ] **Step 4: Run parser tests**

Run:

```powershell
python -m pytest tests/test_benchmark_choice_accuracy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit parser change**

Run:

```powershell
git add benchmark/scorers/choice_accuracy.py tests/test_benchmark_choice_accuracy.py
git commit -m "feat: add strict BaziQA answer parser"
```

---

### Task 2: Forced Confidence Prompt Contract

**Files:**
- Modify: `benchmark/formatters/baziqa_prompt.py`
- Modify: `tests/test_baziqa_prompt_formatter.py`

- [ ] **Step 1: Add failing prompt contract test**

Append this test to `tests/test_baziqa_prompt_formatter.py`:

```python
def test_structured_reasoning_prompt_requires_confidence_contract():
    prompt = format_structured_reasoning_prompt(_case())
    assert "A: 0-100" in prompt
    assert "B: 0-100" in prompt
    assert "C: 0-100" in prompt
    assert "D: 0-100" in prompt
    assert "最终答案：X" in prompt
    assert "最后一行只能写" in prompt
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_baziqa_prompt_formatter.py -q
```

Expected: FAIL because the current prompt only asks for `答案：A/B/C/D`.

- [ ] **Step 3: Replace structured prompt ending**

In `benchmark/formatters/baziqa_prompt.py`, replace `format_structured_reasoning_prompt` with:

```python
def format_structured_reasoning_prompt(case):
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。必须按三阶段结构化推理后再作答。",
        "## 命主信息",
        format_birth_line(case.get("person", {})),
        "## 三阶段结构化推理协议",
        "第一阶段：量化扫描。清点五行、日主强弱、十神分布、格局倾向、用神喜忌。",
        "第二阶段：冲突定级。识别刑冲合害、空亡、入墓、忌神成局，并判断轻微/中度/严重。",
        "第三阶段：应象映射。将命理结构映射到题目领域和现实事件。",
        "## 问题",
        case.get("question", ""),
        "## 选项",
        format_options(case.get("options", [])),
        "## 输出格式",
        "先给出四个选项的置信度，每行一个选项，分数必须是 0 到 100 的整数：",
        "A: 0-100",
        "B: 0-100",
        "C: 0-100",
        "D: 0-100",
        "最终答案必须选择置信度最高的选项；如分数并列，选择命理证据更直接的一项。",
        "最后一行只能写：最终答案：X，其中 X 是 A/B/C/D 之一。",
    ])
```

- [ ] **Step 4: Run prompt and parser tests**

Run:

```powershell
python -m pytest tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit prompt change**

Run:

```powershell
git add benchmark/formatters/baziqa_prompt.py tests/test_baziqa_prompt_formatter.py
git commit -m "feat: constrain BaziQA structured prompt output"
```

---

### Task 3: Store Parser Metadata And Configurable RAG K

**Files:**
- Modify: `benchmark/runners/run_benchmark.py`
- Modify: `rag_prompt_builder.py`
- Modify: `tests/test_benchmark_runner.py`
- Modify: `tests/test_rag_prompt_builder.py`

- [ ] **Step 1: Add failing benchmark metadata test**

Append this test to `tests/test_benchmark_runner.py`:

```python
def test_model_benchmark_records_parser_meta(monkeypatch, tmp_path):
    from benchmark.runners import run_benchmark

    cases = [{
        "case_id": "c1",
        "domain": "wealth",
        "answer": "B",
        "person": {"birth": {"year": 1990, "month": 1, "day": 1, "hour": 0, "minute": 0}},
        "question": "哪项更符合命局？",
        "options": ["A. 木旺", "B. 火旺", "C. 金旺", "D. 水旺"],
    }]

    monkeypatch.setattr(
        run_benchmark,
        "call_model_sync",
        lambda *args, **kwargs: "A: 20\nB: 80\nC: 10\nD: 5\n最终答案：B",
    )

    details = tmp_path / "details.jsonl"
    result = run_benchmark.run_model_benchmark(
        cases,
        provider="deepseek",
        model="deepseek-v4-pro",
        prompt_version="srp_v1",
        max_cases=1,
        method="structured_reasoning",
        temperature=0.0,
        case_details_jsonl=str(details),
        rag_k=2,
    )

    detail = result["case_details"][0]
    assert detail["predicted_answer"] == "B"
    assert detail["parser_source"] == "final_answer"
    assert detail["parser_valid"] is True
    assert detail["rag_k"] == 2
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_benchmark_runner.py::test_model_benchmark_records_parser_meta -q
```

Expected: FAIL because `run_model_benchmark` has no `rag_k` parameter and no parser metadata fields.

- [ ] **Step 3: Update benchmark runner signatures**

In `benchmark/runners/run_benchmark.py`, make these changes:

```python
def _resolve_rag_trace(case, k=3):
    case_index = _get_bench_case_index()
    if case_index is None:
        return []
    try:
        from bazi_features import extract
        chart = _case_chart(case)
        features = extract(chart)
        cases = case_index.top_k_cases(features, k=k)
        out = []
        for rank, item in enumerate(cases, 1):
            out.append({
                "rank": rank,
                "person_id": item.get("person_id"),
                "name": item.get("name"),
                "birth_year": item.get("birth_year"),
                "gender": item.get("gender"),
                "domains": item.get("domains") or {},
                "facts": (item.get("facts") or [])[:5],
            })
        return out
    except Exception:
        return []
```

Change the model benchmark signature to:

```python
def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20, method='direct_choice', temperature=0.0, case_details_jsonl=None, rag_k=3):
```

Inside `run_model_benchmark`, replace the parser block with:

```python
        from benchmark.scorers.choice_accuracy import extract_choice, extract_choice_with_meta
        expected = extract_choice(case.get('answer'))
        parser_meta = extract_choice_with_meta(answer)
        predicted = parser_meta["choice"]
```

Add these fields to `detail`:

```python
            "parser_source": parser_meta["source"],
            "parser_valid": parser_meta["valid"],
            "rag_k": rag_k,
            "rag_trace": _resolve_rag_trace(case, k=rag_k),
```

Do the same parser metadata update inside `run_multi_turn_benchmark`; keep `rag_k=3` there unless a separate CLI flag is passed through.

Add a CLI option:

```python
    parser.add_argument('--rag-k', type=int, default=3, choices=[1, 2, 3, 4, 5], help='Number of retrieved BaziQA cases to inject when --rag is enabled')
```

Pass it into `run_model_benchmark`:

```python
            rag_k=args.rag_k,
```

- [ ] **Step 4: Ensure system prompt retrieval uses rag_k**

If `rag_prompt_builder.build_system_prompt` currently hardcodes `top_k=3`, change its signature to accept `top_k=3` and use it when calling `case_index.top_k_cases`.

Use this interface:

```python
def build_system_prompt(base_prompt, chart, case_index, enable_rag=True, few_shot_examples=None, top_k=3):
```

Then update `_resolve_system_prompt(case)` in `benchmark/runners/run_benchmark.py` to accept `rag_k=3` and pass `top_k=rag_k` into `build_system_prompt`.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_benchmark_runner.py tests/test_rag_prompt_builder.py tests/test_benchmark_choice_accuracy.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit benchmark metadata and rag-k**

Run:

```powershell
git add benchmark/runners/run_benchmark.py rag_prompt_builder.py tests/test_benchmark_runner.py tests/test_rag_prompt_builder.py
git commit -m "feat: record BaziQA parser metadata and rag k"
```

---

### Task 4: K Ablation Runner

**Files:**
- Create: `scripts/run_baziqa_k_ablation.py`
- Create: `tests/test_baziqa_k_ablation_script.py`
- Update: `docs/BAZIQA_PROJECT_ROADMAP.md`

- [ ] **Step 1: Add script test**

Create `tests/test_baziqa_k_ablation_script.py`:

```python
from pathlib import Path

from scripts.run_baziqa_k_ablation import build_commands, render_report


def test_build_commands_includes_each_k_and_repeat():
    commands = build_commands(
        dataset="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl",
        corpus="benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl",
        provider="deepseek",
        model="deepseek-v4-pro",
        max_cases=40,
        repeats=2,
        output_dir=".tmp/k_ablation",
    )
    assert len(commands) == 6
    assert any("--rag-k 1" in " ".join(cmd) for cmd in commands)
    assert any("--rag-k 2" in " ".join(cmd) for cmd in commands)
    assert any("--rag-k 3" in " ".join(cmd) for cmd in commands)
    assert all("--method structured_reasoning" in " ".join(cmd) for cmd in commands)


def test_render_report_marks_gate_status():
    rows = [
        {"k": 1, "runs": 3, "mean": 0.425, "min": 0.375, "max": 0.45, "stdev": 0.025},
        {"k": 2, "runs": 3, "mean": 0.35, "min": 0.30, "max": 0.40, "stdev": 0.05},
    ]
    text = render_report(rows)
    assert "| 1 | 3 | 42.5% | 37.5% | 45.0% | 2.5 pp | PASS |" in text
    assert "| 2 | 3 | 35.0% | 30.0% | 40.0% | 5.0 pp | FAIL |" in text
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_baziqa_k_ablation_script.py -q
```

Expected: FAIL because `scripts/run_baziqa_k_ablation.py` does not exist.

- [ ] **Step 3: Create k ablation script**

Create `scripts/run_baziqa_k_ablation.py`:

```python
import argparse
import json
import subprocess
from pathlib import Path


def build_commands(dataset, corpus, provider, model, max_cases, repeats, output_dir):
    commands = []
    out = Path(output_dir)
    for k in (1, 2, 3):
        for repeat in range(1, repeats + 1):
            trace = out / f"k{k}_run{repeat}.jsonl"
            commands.append([
                "python",
                "benchmark/runners/run_benchmark.py",
                "--dataset", dataset,
                "--model-runner",
                "--provider", provider,
                "--model", model,
                "--max-cases", str(max_cases),
                "--method", "structured_reasoning",
                "--temperature", "0",
                "--rag",
                "--rag-k", str(k),
                "--rag-corpus", corpus,
                "--case-details-jsonl", str(trace),
            ])
    return commands


def _read_trace_accuracy(path):
    total = 0
    correct = 0
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1
            if row.get("correct") is True:
                correct += 1
    return correct / total if total else 0.0


def _stdev(values):
    if len(values) <= 1:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def summarize_traces(output_dir, repeats):
    rows = []
    out = Path(output_dir)
    for k in (1, 2, 3):
        values = []
        for repeat in range(1, repeats + 1):
            trace = out / f"k{k}_run{repeat}.jsonl"
            if trace.exists():
                values.append(_read_trace_accuracy(trace))
        if values:
            rows.append({
                "k": k,
                "runs": len(values),
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "stdev": _stdev(values),
            })
    return rows


def render_report(rows):
    lines = [
        "# BaziQA K Ablation Report",
        "",
        "| k | Runs | Mean | Min | Max | Stdev | Gate |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        gate = "PASS" if row["mean"] >= 0.40 and row["min"] >= 0.35 else "FAIL"
        lines.append(
            f"| {row['k']} | {row['runs']} | {row['mean']:.1%} | {row['min']:.1%} | "
            f"{row['max']:.1%} | {row['stdev'] * 100:.1f} pp | {gate} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run BaziQA RAG k ablation.")
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl")
    parser.add_argument("--corpus", default="benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--max-cases", type=int, default=40)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-dir", default=".tmp/baziqa_k_ablation")
    parser.add_argument("--report", default="docs/BAZIQA_K_ABLATION_REPORT.md")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    commands = build_commands(
        args.dataset,
        args.corpus,
        args.provider,
        args.model,
        args.max_cases,
        args.repeats,
        args.output_dir,
    )
    if args.run:
        for command in commands:
            subprocess.run(command, check=True)
    rows = summarize_traces(args.output_dir, args.repeats)
    report = render_report(rows)
    Path(args.report).write_text(report, encoding="utf-8")
    print(f"Report saved to: {args.report}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run script tests**

Run:

```powershell
python -m pytest tests/test_baziqa_k_ablation_script.py -q
```

Expected: PASS.

- [ ] **Step 5: Run real k ablation with DeepSeek**

Run only after confirming `.deepseek_key` or `DEEPSEEK_API_KEY` is available:

```powershell
python scripts/run_baziqa_k_ablation.py --run --repeats 3 --max-cases 40
```

Expected: `docs/BAZIQA_K_ABLATION_REPORT.md` is created with k=1/2/3 rows.

- [ ] **Step 6: Commit k ablation**

Run:

```powershell
git add scripts/run_baziqa_k_ablation.py tests/test_baziqa_k_ablation_script.py docs/BAZIQA_K_ABLATION_REPORT.md docs/BAZIQA_PROJECT_ROADMAP.md
git commit -m "feat: add BaziQA rag k ablation runner"
```

---

### Task 5: Error Attribution From Trace JSONL

**Files:**
- Create: `scripts/analyze_baziqa_error_attribution.py`
- Create: `tests/test_baziqa_error_attribution.py`
- Update: `docs/BAZIQA_PROJECT_ROADMAP.md`

- [ ] **Step 1: Add attribution tests**

Create `tests/test_baziqa_error_attribution.py`:

```python
import json

from scripts.analyze_baziqa_error_attribution import classify_row, summarize_rows


def test_classify_parser_failure():
    row = {"correct": False, "parser_valid": False, "rag_trace": [{"person_id": "p1"}]}
    assert classify_row(row) == "parser_failure"


def test_classify_retrieval_empty():
    row = {"correct": False, "parser_valid": True, "rag_trace": []}
    assert classify_row(row) == "retrieval_empty"


def test_classify_model_reasoning_error():
    row = {"correct": False, "parser_valid": True, "rag_trace": [{"person_id": "p1"}]}
    assert classify_row(row) == "model_or_knowledge_error"


def test_summarize_rows_by_domain_and_error_type():
    rows = [
        {"domain": "wealth", "correct": False, "parser_valid": False, "rag_trace": [{"person_id": "p1"}]},
        {"domain": "wealth", "correct": False, "parser_valid": True, "rag_trace": []},
        {"domain": "career", "correct": True, "parser_valid": True, "rag_trace": [{"person_id": "p2"}]},
    ]
    summary = summarize_rows(rows)
    assert summary["overall"]["total"] == 3
    assert summary["overall"]["correct"] == 1
    assert summary["by_error_type"]["parser_failure"] == 1
    assert summary["by_error_type"]["retrieval_empty"] == 1
    assert summary["by_domain"]["wealth"]["total"] == 2
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_baziqa_error_attribution.py -q
```

Expected: FAIL because the attribution script does not exist.

- [ ] **Step 3: Create attribution script**

Create `scripts/analyze_baziqa_error_attribution.py`:

```python
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def classify_row(row):
    if row.get("correct") is True:
        return "correct"
    if row.get("parser_valid") is False:
        return "parser_failure"
    if not row.get("rag_trace"):
        return "retrieval_empty"
    if row.get("parser_source") == "legacy":
        return "legacy_parser_fallback"
    return "model_or_knowledge_error"


def summarize_rows(rows):
    overall = {"total": 0, "correct": 0, "accuracy": 0.0}
    by_error_type = Counter()
    by_domain = defaultdict(lambda: {"total": 0, "correct": 0, "accuracy": 0.0})
    for row in rows:
        overall["total"] += 1
        domain = row.get("domain") or "unknown"
        by_domain[domain]["total"] += 1
        if row.get("correct") is True:
            overall["correct"] += 1
            by_domain[domain]["correct"] += 1
        kind = classify_row(row)
        if kind != "correct":
            by_error_type[kind] += 1
    overall["accuracy"] = overall["correct"] / overall["total"] if overall["total"] else 0.0
    for bucket in by_domain.values():
        bucket["accuracy"] = bucket["correct"] / bucket["total"] if bucket["total"] else 0.0
    return {
        "overall": overall,
        "by_error_type": dict(by_error_type),
        "by_domain": dict(by_domain),
    }


def load_jsonl(path):
    rows = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def render_markdown(summary):
    lines = [
        "# BaziQA Error Attribution Report",
        "",
        f"- Total: {summary['overall']['total']}",
        f"- Correct: {summary['overall']['correct']}",
        f"- Accuracy: {summary['overall']['accuracy']:.1%}",
        "",
        "## Error Types",
        "",
        "| Type | Count |",
        "|---|---:|",
    ]
    for kind, count in sorted(summary["by_error_type"].items()):
        lines.append(f"| {kind} | {count} |")
    lines.extend(["", "## Domains", "", "| Domain | Total | Correct | Accuracy |", "|---|---:|---:|---:|"])
    for domain, bucket in sorted(summary["by_domain"].items()):
        lines.append(f"| {domain} | {bucket['total']} | {bucket['correct']} | {bucket['accuracy']:.1%} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyze BaziQA trace JSONL error attribution.")
    parser.add_argument("--trace", required=True)
    parser.add_argument("--output", default="docs/BAZIQA_ERROR_ATTRIBUTION_REPORT.md")
    args = parser.parse_args(argv)
    summary = summarize_rows(load_jsonl(args.trace))
    Path(args.output).write_text(render_markdown(summary), encoding="utf-8")
    print(f"Report saved to: {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run attribution tests**

Run:

```powershell
python -m pytest tests/test_baziqa_error_attribution.py -q
```

Expected: PASS.

- [ ] **Step 5: Generate attribution report from the best k trace**

After Task 4 produces traces, run:

```powershell
python scripts/analyze_baziqa_error_attribution.py --trace .tmp/baziqa_k_ablation/k1_run1.jsonl --output docs/BAZIQA_ERROR_ATTRIBUTION_REPORT.md
```

If k=2 or k=3 is better, replace the trace path with that run's JSONL file.

- [ ] **Step 6: Commit attribution tooling**

Run:

```powershell
git add scripts/analyze_baziqa_error_attribution.py tests/test_baziqa_error_attribution.py docs/BAZIQA_ERROR_ATTRIBUTION_REPORT.md docs/BAZIQA_PROJECT_ROADMAP.md
git commit -m "feat: add BaziQA error attribution report"
```

---

### Task 6: Real Report Quality Gate

**Files:**
- Create: `scripts/verify_report_quality_gate.py`
- Create: `tests/test_report_quality_gate.py`
- Update: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Add report quality gate tests**

Create `tests/test_report_quality_gate.py`:

```python
from scripts.verify_report_quality_gate import evaluate_report


def _chart():
    return {
        "four_pillars": {
            "year": {"gan": "庚", "zhi": "午"},
            "month": {"gan": "辛", "zhi": "巳"},
            "day": {"gan": "甲", "zhi": "子"},
            "hour": {"gan": "戊", "zhi": "辰"},
        },
        "day_master": {"gan": "甲", "wuxing": "木"},
        "birth_info": {"gender": "female"},
    }


def test_report_quality_gate_fails_on_hard_validator_error():
    result = evaluate_report(_chart(), "此命局巳午未会火局，且丑为火库。")
    assert result["passed"] is False
    assert result["error_count"] >= 1


def test_report_quality_gate_passes_clean_report():
    result = evaluate_report(_chart(), "此命局火势有根，但不能直接断巳午未会局。")
    assert result["passed"] is True
    assert result["error_count"] == 0
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_report_quality_gate.py -q
```

Expected: FAIL because `scripts/verify_report_quality_gate.py` does not exist.

- [ ] **Step 3: Create report quality gate script**

Create `scripts/verify_report_quality_gate.py`:

```python
import argparse
import json
from pathlib import Path

from bazi_report_validator import validate_report_claims


def evaluate_report(chart, report_text):
    issues = validate_report_claims(chart, report_text)
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") != "error"]
    return {
        "passed": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
    }


def load_cases(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("cases", [])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify deterministic BaZi report quality gate.")
    parser.add_argument("--cases", required=True, help="JSON file with chart and report_text cases")
    parser.add_argument("--output", default="docs/REPORT_QUALITY_GATE_REPORT.md")
    args = parser.parse_args(argv)

    rows = []
    passed = 0
    for case in load_cases(args.cases):
        result = evaluate_report(case.get("chart") or {}, case.get("report_text") or "")
        if result["passed"]:
            passed += 1
        rows.append({
            "case_id": case.get("case_id") or "unknown",
            "passed": result["passed"],
            "error_count": result["error_count"],
            "warning_count": result["warning_count"],
            "issues": result["issues"],
        })

    lines = [
        "# Report Quality Gate Report",
        "",
        f"- Cases: {len(rows)}",
        f"- Passed: {passed}",
        f"- Failed: {len(rows) - passed}",
        "",
        "| Case | Passed | Errors | Warnings |",
        "|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['case_id']} | {row['passed']} | {row['error_count']} | {row['warning_count']} |")
    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report saved to: {args.output}")
    return 0 if len(rows) == passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run quality gate tests**

Run:

```powershell
python -m pytest tests/test_report_quality_gate.py tests/test_bazi_report_validator.py -q
```

Expected: PASS.

- [ ] **Step 5: Run quality gate on real sample reports**

Prepare a JSON file at `.tmp/report_quality_cases.json` with this shape:

```json
{
  "cases": [
    {
      "case_id": "manual_quality_case_001",
      "chart": {
        "four_pillars": {
          "year": {"gan": "庚", "zhi": "午"},
          "month": {"gan": "辛", "zhi": "巳"},
          "day": {"gan": "甲", "zhi": "子"},
          "hour": {"gan": "戊", "zhi": "辰"}
        },
        "day_master": {"gan": "甲", "wuxing": "木"},
        "birth_info": {"gender": "female"}
      },
      "report_text": "粘贴一次真实网页输出报告全文"
    }
  ]
}
```

Run:

```powershell
python scripts/verify_report_quality_gate.py --cases .tmp/report_quality_cases.json --output docs/REPORT_QUALITY_GATE_REPORT.md
```

Expected: exit code `0` only when no hard validator errors are found.

- [ ] **Step 6: Commit report quality gate**

Run:

```powershell
git add scripts/verify_report_quality_gate.py tests/test_report_quality_gate.py docs/REPORT_QUALITY_GATE_REPORT.md docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "feat: add deterministic report quality gate"
```

---

## Final Verification

Run non-network tests first:

```powershell
python -m pytest tests/test_benchmark_choice_accuracy.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_runner.py tests/test_rag_prompt_builder.py tests/test_baziqa_k_ablation_script.py tests/test_baziqa_error_attribution.py tests/test_report_quality_gate.py tests/test_bazi_report_validator.py -q
```

Expected: all selected tests PASS.

Run full deterministic suite:

```powershell
python -m pytest -q -m "not e2e"
```

Expected: PASS with no new failures.

Run real-model evaluation only after confirming network and DeepSeek key:

```powershell
python scripts/run_baziqa_k_ablation.py --run --repeats 3 --max-cases 40
```

Expected:

- `docs/BAZIQA_K_ABLATION_REPORT.md` exists.
- At least one k setting has lower variance than the old `rag-structured` range.
- If no k reaches the target gates, the result is recorded as BLOCKED rather than PASS.

Run report gate:

```powershell
python scripts/verify_report_quality_gate.py --cases .tmp/report_quality_cases.json --output docs/REPORT_QUALITY_GATE_REPORT.md
```

Expected:

- Exit code `0` for clean reports.
- Exit code `1` when deterministic hard errors are found.

## Decision Rules After Implementation

- If parser compliance improves but accuracy stays near `30%`, the next bottleneck is model reasoning or knowledge quality, not output parsing.
- If k=1 or k=2 beats k=3 by at least `5 pp` mean accuracy and has equal or lower variance, change default RAG k to that value.
- If all k settings remain below `35%` mean, invest in retrieval quality: add structured scoring for day master, month branch, ten gods, useful god, and option intent.
- If report quality gate catches hard errors after BaziQA accuracy improves, prioritize deterministic report validation before prompt expansion.
- If a result depends on one run only, record it as exploratory evidence, not acceptance evidence.

## Documentation Updates

After all tasks:

- Update `docs/BAZIQA_PROJECT_ROADMAP.md` with the selected k and the latest stable gate result.
- Update `docs/BAZIQA_ACCEPTANCE_REPORT.md` with a "Current Stable Status" section above historical runs.
- Link `docs/BAZIQA_K_ABLATION_REPORT.md`, `docs/BAZIQA_ERROR_ATTRIBUTION_REPORT.md`, and `docs/REPORT_QUALITY_GATE_REPORT.md`.
- Keep historical `42.5%` single-run result, but label it as non-reproducible exploratory evidence.

## Self-Review

- Spec coverage: The plan covers strict output parsing, structured prompt constraints, configurable RAG k, k ablation, error attribution, and real report quality gating.
- Placeholder scan: The plan contains no unresolved implementation placeholders; sample data shape is explicit and executable.
- Type consistency: Parser metadata uses `choice/source/valid`; benchmark case details use `parser_source/parser_valid/rag_k`; scripts consume those exact fields.
