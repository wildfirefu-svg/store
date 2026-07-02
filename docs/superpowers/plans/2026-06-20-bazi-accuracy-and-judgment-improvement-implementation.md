# Bazi Accuracy And Judgment Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提升 BaziQA 选择题稳定准确率，并把同一套命盘结构化与校验能力用于减少真实命主报告中的命理硬错。

**Architecture:** 先做可复现评测与检索消融，避免把 10 题 smoke 或单次高分当成有效提升。再补齐 corpus 的 `chart_input`，让 RAG 从文本相似推进到命盘结构相似。最后按领域攻坚，并用真实报告质量 gate 验证“题库准确率提升”是否同步改善命理判断水平。

**Tech Stack:** Python 3, pytest, JSONL, DeepSeek model runner, existing benchmark runner, `bazi_calculator.compute_chart`, `case_index.CaseIndex`, `bazi_features.extract`, `rag_prompt_builder`, `bazi_report_validator`.

---

## Current Baseline

Read these files before implementation:

- `docs/BAZIQA_P0_P2_SUMMARY.md`
- `docs/BAZIQA_PROJECT_ROADMAP.md`
- `docs/BAZIQA_ACCEPTANCE_REPORT.md`
- `case_index.py`
- `bazi_features.py`
- `rag_prompt_builder.py`
- `benchmark/runners/run_benchmark.py`
- `scripts/analyze_baziqa_error_attribution.py`
- `scripts/verify_report_quality_gate.py`
- `bazi_report_validator.py`

Known facts:

- P0 parser and `最终答案：X` contract are implemented, but 3-run accuracy is only mean `28.3%`.
- k-ablation single-run shows `k=2` is better than k=1/k=3, but this is not yet a stable repeats=3 conclusion.
- P2 initial semantic overlap full 40-case run dropped to `22.5%`.
- P2 refined 10-case smoke reached `50.0%`, but 10 cases are not enough for acceptance.
- Current corpus lacks complete `chart_input`, so retrieval cannot reliably score day master, month branch, ten gods, useful-god direction, or luck-year timing similarity.

Acceptance gates for this plan:

- Refined P2 full 40-case benchmark is run and recorded.
- Retrieval ablation report exists for `bm25`, `structured`, and `structured_semantic`.
- If a retrieval strategy becomes default, it must have repeats=3 mean >= `35.0%` before soft adoption and mean >= `40.0%`, min >= `35.0%` before acceptance.
- At least `90%` of corpus rows used for RAG contain generated `chart_input`.
- Domain error report identifies at least two actionable weak domains.
- Real report quality gate has zero `error` severity issues on the selected report sample.

## File Structure

- Modify `case_index.py`: add retrieval feature flags and structured chart similarity scoring.
- Modify `bazi_features.py`: expose extra chart features needed by retrieval.
- Modify `rag_prompt_builder.py`: show chart match reasons in prompt.
- Modify `benchmark/runners/run_benchmark.py`: include retrieval mode and richer trace metadata.
- Create `scripts/run_baziqa_retrieval_ablation.py`: run retrieval-mode ablations.
- Create `scripts/enrich_baziqa_chart_input.py`: generate `chart_input` for corpus/holdout JSONL rows.
- Create `scripts/build_domain_action_plan.py`: turn trace JSONL into domain-level action items.
- Create `scripts/export_report_quality_samples.py`: prepare report quality gate input from saved or manual reports.
- Create `docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md`: final execution report.
- Add or modify tests under `tests/` for each script and scoring path.

---

### Task 1: Refined P2 Full-Set Validation

**Files:**
- Create: `scripts/run_baziqa_refined_p2_validation.py`
- Create: `tests/test_baziqa_refined_p2_validation.py`
- Create: `docs/BAZIQA_REFINED_P2_40_REPORT.md`

- [ ] **Step 1: Write the failing test**

Create `tests/test_baziqa_refined_p2_validation.py`:

```python
from scripts.run_baziqa_refined_p2_validation import build_command, render_summary


def test_build_command_uses_refined_p2_defaults():
    command = build_command(
        dataset="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl",
        corpus="benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl",
        output_dir="docs/refined_p2_40_output",
        details=".tmp/refined_p2_40.jsonl",
    )
    joined = " ".join(command)
    assert "--method structured_reasoning" in joined
    assert "--rag-k 2" in joined
    assert "--temperature 0" in joined
    assert "--case-details-jsonl .tmp/refined_p2_40.jsonl" in joined


def test_render_summary_records_non_acceptance_below_gate():
    text = render_summary({
        "total": 40,
        "correct": 12,
        "accuracy": 0.30,
        "report_path": "docs/refined_p2_40_output/run_x.md",
        "details_path": ".tmp/refined_p2_40.jsonl",
    })
    assert "Accuracy: 30.0%" in text
    assert "Gate: BLOCKED" in text
    assert "not enough for acceptance" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_baziqa_refined_p2_validation.py -q
```

Expected: FAIL because `scripts/run_baziqa_refined_p2_validation.py` does not exist.

- [ ] **Step 3: Create the validation script**

Create `scripts/run_baziqa_refined_p2_validation.py`:

```python
import argparse
import json
import subprocess
from pathlib import Path


def build_command(dataset, corpus, output_dir, details):
    return [
        "python",
        "benchmark/runners/run_benchmark.py",
        "--model-runner",
        "--rag",
        "--rag-corpus", corpus,
        "--dataset", dataset,
        "--provider", "deepseek",
        "--model", "deepseek-v4-pro",
        "--method", "structured_reasoning",
        "--max-cases", "40",
        "--temperature", "0",
        "--rag-k", "2",
        "--case-details-jsonl", details,
        "--output-dir", output_dir,
    ]


def summarize_details(details_path):
    total = 0
    correct = 0
    with Path(details_path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1
            if row.get("correct") is True:
                correct += 1
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
    }


def latest_report(output_dir):
    paths = sorted(Path(output_dir).glob("run_*.md"), key=lambda p: p.stat().st_mtime)
    return str(paths[-1]) if paths else ""


def render_summary(summary):
    accuracy = summary["accuracy"]
    gate = "PASS" if accuracy >= 0.40 else "BLOCKED"
    return "\n".join([
        "# BaziQA Refined P2 40-Case Validation",
        "",
        f"- Total: {summary['total']}",
        f"- Correct: {summary['correct']}",
        f"- Accuracy: {accuracy:.1%}",
        f"- Gate: {gate}",
        f"- Benchmark report: {summary.get('report_path', '')}",
        f"- Case details: {summary.get('details_path', '')}",
        "",
        "A single 40-case run is not enough for acceptance; if this run is >=35.0%, run repeats=3 before changing defaults.",
        "",
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run refined P2 full 40-case validation.")
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl")
    parser.add_argument("--corpus", default="benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl")
    parser.add_argument("--output-dir", default="docs/refined_p2_40_output")
    parser.add_argument("--details", default=".tmp/refined_p2_40_details.jsonl")
    parser.add_argument("--summary", default="docs/BAZIQA_REFINED_P2_40_REPORT.md")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    Path(args.details).parent.mkdir(parents=True, exist_ok=True)
    command = build_command(args.dataset, args.corpus, args.output_dir, args.details)
    if args.run:
        subprocess.run(command, check=True)
    summary = summarize_details(args.details) if Path(args.details).exists() else {
        "total": 0,
        "correct": 0,
        "accuracy": 0.0,
    }
    summary["report_path"] = latest_report(args.output_dir)
    summary["details_path"] = args.details
    Path(args.summary).write_text(render_summary(summary), encoding="utf-8")
    print(f"Summary saved to {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
python -m pytest tests/test_baziqa_refined_p2_validation.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the real 40-case validation**

Run only when network and the DeepSeek key are available:

```powershell
python scripts/run_baziqa_refined_p2_validation.py --run
```

Expected:

- `docs/BAZIQA_REFINED_P2_40_REPORT.md` exists.
- `.tmp/refined_p2_40_details.jsonl` contains up to 40 rows.
- Result is recorded as PASS only if accuracy >= `40.0%`; otherwise BLOCKED.

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/run_baziqa_refined_p2_validation.py tests/test_baziqa_refined_p2_validation.py docs/BAZIQA_REFINED_P2_40_REPORT.md
git commit -m "test: add refined P2 full-set validation"
```

---

### Task 2: Retrieval Mode Switches And Ablation

**Files:**
- Modify: `case_index.py`
- Modify: `benchmark/runners/run_benchmark.py`
- Create: `scripts/run_baziqa_retrieval_ablation.py`
- Create: `tests/test_baziqa_retrieval_ablation.py`
- Modify: `tests/test_case_index.py`

- [ ] **Step 1: Add failing unit tests for retrieval switches**

Append to `tests/test_case_index.py`:

```python
import os


def test_semantic_overlap_can_be_disabled(monkeypatch, tmp_path):
    path = tmp_path / "corpus.jsonl"
    path.write_text(
        "\n".join([
            '{"case_id":"c1","answer":"A","domain":"career","person":{"person_id":"p1","name":"甲","gender":"male","birth":{"year":1980}},"question":"事业升迁","options":["A. 升迁","B. 婚姻"]}',
            '{"case_id":"c2","answer":"A","domain":"career","person":{"person_id":"p2","name":"乙","gender":"male","birth":{"year":1980}},"question":"健康疾病","options":["A. 疾病","B. 升迁"]}'
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("BAZI_RAG_SEMANTIC", "0")
    from case_index import CaseIndex
    idx = CaseIndex(path)
    result = idx.top_k_cases({"text_blob": "事业升迁", "structured": {"query_text": "事业升迁"}}, k=2)
    assert all(not any(r.startswith("semantic_overlap:") for r in item["match_reasons"]) for item in result)


def test_structured_weight_changes_score(monkeypatch, tmp_path):
    path = tmp_path / "corpus.jsonl"
    path.write_text(
        '{"case_id":"c1","answer":"A","domain":"career","person":{"person_id":"p1","name":"甲","gender":"male","birth":{"year":1980}},"question":"事业","options":["A. 升迁","B. 婚姻"]}\n',
        encoding="utf-8",
    )
    from case_index import CaseIndex
    monkeypatch.setenv("BAZI_RAG_STRUCTURED_WEIGHT", "0")
    score_low = CaseIndex(path).top_k_cases({"text_blob": "事业", "structured": {"query_domain": "career"}}, k=1)[0]["_score"]
    monkeypatch.setenv("BAZI_RAG_STRUCTURED_WEIGHT", "1")
    score_high = CaseIndex(path).top_k_cases({"text_blob": "事业", "structured": {"query_domain": "career"}}, k=1)[0]["_score"]
    assert score_high > score_low
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_case_index.py::test_semantic_overlap_can_be_disabled tests/test_case_index.py::test_structured_weight_changes_score -q
```

Expected: FAIL because `case_index.py` does not read `BAZI_RAG_SEMANTIC` or `BAZI_RAG_STRUCTURED_WEIGHT`.

- [ ] **Step 3: Add retrieval switches**

In `case_index.py`, add `import os` and these helpers near the constants:

```python
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_enabled(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")
```

In `CaseIndex.top_k_cases`, replace:

```python
structured_score, reasons = self._score_structured_match(case, structured)
semantic_score, phrase_hits = self._score_semantic_overlap(case, structured.get("query_text") or query)
```

with:

```python
structured_weight = _env_float("BAZI_RAG_STRUCTURED_WEIGHT", 1.0)
semantic_enabled = _env_enabled("BAZI_RAG_SEMANTIC", True)
semantic_weight = _env_float("BAZI_RAG_SEMANTIC_WEIGHT", 1.0)

structured_score, reasons = self._score_structured_match(case, structured)
structured_score *= structured_weight
semantic_score, phrase_hits = (0.0, [])
if semantic_enabled:
    semantic_score, phrase_hits = self._score_semantic_overlap(case, structured.get("query_text") or query)
    semantic_score *= semantic_weight
```

- [ ] **Step 4: Add ablation script tests**

Create `tests/test_baziqa_retrieval_ablation.py`:

```python
from scripts.run_baziqa_retrieval_ablation import build_configs, render_report


def test_build_configs_contains_expected_modes():
    configs = build_configs()
    names = [c["name"] for c in configs]
    assert names == ["bm25", "structured", "structured_semantic", "semantic_low"]
    assert configs[0]["env"]["BAZI_RAG_STRUCTURED_WEIGHT"] == "0"
    assert configs[0]["env"]["BAZI_RAG_SEMANTIC"] == "0"
    assert configs[2]["env"]["BAZI_RAG_SEMANTIC"] == "1"


def test_render_report_marks_acceptance_gate():
    text = render_report([
        {"name": "structured", "runs": 3, "mean": 0.40, "min": 0.35, "max": 0.425},
        {"name": "semantic_low", "runs": 3, "mean": 0.325, "min": 0.30, "max": 0.35},
    ])
    assert "| structured | 3 | 40.0% | 35.0% | 42.5% | PASS |" in text
    assert "| semantic_low | 3 | 32.5% | 30.0% | 35.0% | BLOCKED |" in text
```

- [ ] **Step 5: Create retrieval ablation runner**

Create `scripts/run_baziqa_retrieval_ablation.py`:

```python
import argparse
import json
import os
import subprocess
from pathlib import Path


def build_configs():
    return [
        {"name": "bm25", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "0", "BAZI_RAG_SEMANTIC": "0"}},
        {"name": "structured", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "0"}},
        {"name": "structured_semantic", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "1", "BAZI_RAG_SEMANTIC_WEIGHT": "1"}},
        {"name": "semantic_low", "env": {"BAZI_RAG_STRUCTURED_WEIGHT": "1", "BAZI_RAG_SEMANTIC": "1", "BAZI_RAG_SEMANTIC_WEIGHT": "0.35"}},
    ]


def _accuracy(path):
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


def summarize(output_dir, repeats):
    rows = []
    for config in build_configs():
        values = []
        for repeat in range(1, repeats + 1):
            path = Path(output_dir) / f"{config['name']}_run{repeat}.jsonl"
            if path.exists():
                values.append(_accuracy(path))
        if values:
            rows.append({
                "name": config["name"],
                "runs": len(values),
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
            })
    return rows


def render_report(rows):
    lines = [
        "# BaziQA Retrieval Ablation Report",
        "",
        "| mode | runs | mean | min | max | gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        gate = "PASS" if row["mean"] >= 0.40 and row["min"] >= 0.35 else "BLOCKED"
        lines.append(f"| {row['name']} | {row['runs']} | {row['mean']:.1%} | {row['min']:.1%} | {row['max']:.1%} | {gate} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run BaziQA retrieval ablation.")
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout.jsonl")
    parser.add_argument("--corpus", default="benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl")
    parser.add_argument("--output-dir", default=".tmp/baziqa_retrieval_ablation")
    parser.add_argument("--report", default="docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    if args.run:
        for config in build_configs():
            for repeat in range(1, args.repeats + 1):
                details = Path(args.output_dir) / f"{config['name']}_run{repeat}.jsonl"
                env = os.environ.copy()
                env.update(config["env"])
                command = [
                    "python", "benchmark/runners/run_benchmark.py",
                    "--dataset", args.dataset,
                    "--model-runner",
                    "--provider", "deepseek",
                    "--model", "deepseek-v4-pro",
                    "--max-cases", "40",
                    "--method", "structured_reasoning",
                    "--temperature", "0",
                    "--rag",
                    "--rag-k", "2",
                    "--rag-corpus", args.corpus,
                    "--case-details-jsonl", str(details),
                ]
                subprocess.run(command, check=True, env=env)

    Path(args.report).write_text(render_report(summarize(args.output_dir, args.repeats)), encoding="utf-8")
    print(f"Report saved to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest tests/test_case_index.py tests/test_baziqa_retrieval_ablation.py -q
```

Expected: PASS.

- [ ] **Step 7: Run real retrieval ablation**

Run only when network and key are available:

```powershell
python scripts/run_baziqa_retrieval_ablation.py --run --repeats 3
```

Expected:

- `docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md` exists.
- Default retrieval mode is changed only if the report supports it.

- [ ] **Step 8: Commit**

Run:

```powershell
git add case_index.py benchmark/runners/run_benchmark.py scripts/run_baziqa_retrieval_ablation.py tests/test_case_index.py tests/test_baziqa_retrieval_ablation.py docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md
git commit -m "feat: add BaziQA retrieval ablation controls"
```

---

### Task 3: Enrich Corpus With Chart Input

**Files:**
- Create: `scripts/enrich_baziqa_chart_input.py`
- Create: `tests/test_enrich_baziqa_chart_input.py`
- Modify: `bazi_features.py`
- Modify: `tests/test_bazi_features.py`

- [ ] **Step 1: Add enrichment tests**

Create `tests/test_enrich_baziqa_chart_input.py`:

```python
import json

from scripts.enrich_baziqa_chart_input import enrich_row, summarize_rows


def test_enrich_row_adds_chart_input(monkeypatch):
    def fake_compute_chart(year, month, day, hour, minute, gender, location):
        return {
            "four_pillars": {
                "year": {"gan": "庚", "zhi": "午"},
                "month": {"gan": "辛", "zhi": "巳"},
                "day": {"gan": "甲", "zhi": "子"},
                "hour": {"gan": "戊", "zhi": "辰"},
            },
            "day_master": {"gan": "甲", "wuxing": "木"},
            "birth_info": {"year": year, "month": month, "day": day, "hour": hour, "minute": minute, "gender": gender},
            "wuxing_stats": {"木": 2, "火": 2, "土": 2, "金": 1, "水": 1},
            "shishen_stats": {"正官": 1},
        }

    row = {
        "case_id": "c1",
        "person": {
            "gender": "female",
            "birth": {"year": 1990, "month": 5, "day": 12, "hour": 8, "minute": 30, "place": "Beijing"},
        },
    }
    enriched = enrich_row(row, compute_chart_fn=fake_compute_chart)
    assert enriched["chart_input"]["four_pillars"]["day"]["gan"] == "甲"
    assert enriched["chart_input"]["birth_info"]["gender"] == "female"


def test_summarize_rows_counts_chart_input():
    rows = [{"chart_input": {"four_pillars": {}}}, {"person": {}}]
    summary = summarize_rows(rows)
    assert summary == {"total": 2, "with_chart_input": 1, "coverage": 0.5}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_enrich_baziqa_chart_input.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Create enrichment script**

Create `scripts/enrich_baziqa_chart_input.py`:

```python
import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bazi_calculator import compute_chart


def _birth(row):
    person = row.get("person") or {}
    birth = person.get("birth") or {}
    return person, birth


def enrich_row(row, compute_chart_fn=compute_chart):
    if row.get("chart_input"):
        return row
    person, birth = _birth(row)
    try:
        chart = compute_chart_fn(
            int(birth.get("year")),
            int(birth.get("month")),
            int(birth.get("day")),
            int(birth.get("hour", 0) or 0),
            int(birth.get("minute", 0) or 0),
            person.get("gender") or "male",
            birth.get("place") or "Beijing",
        )
    except (TypeError, ValueError, KeyError):
        return row
    out = dict(row)
    out["chart_input"] = chart
    return out


def load_jsonl(path):
    rows = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_rows(rows):
    total = len(rows)
    with_chart = sum(1 for row in rows if row.get("chart_input"))
    return {"total": total, "with_chart_input": with_chart, "coverage": with_chart / total if total else 0.0}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Enrich BaziQA JSONL rows with chart_input.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", default="docs/BAZIQA_CHART_INPUT_ENRICHMENT_REPORT.md")
    args = parser.parse_args(argv)

    rows = [enrich_row(row) for row in load_jsonl(args.input)]
    write_jsonl(args.output, rows)
    summary = summarize_rows(rows)
    text = "\n".join([
        "# BaziQA Chart Input Enrichment Report",
        "",
        f"- Total: {summary['total']}",
        f"- With chart_input: {summary['with_chart_input']}",
        f"- Coverage: {summary['coverage']:.1%}",
        f"- Output: {args.output}",
        "",
    ])
    Path(args.summary).write_text(text, encoding="utf-8")
    print(f"Enriched file saved to {args.output}")
    print(f"Summary saved to {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Extend chart feature extraction**

Append this test to `tests/test_bazi_features.py`:

```python
def test_extract_includes_wuxing_and_shishen_stats():
    features = extract({
        "four_pillars": {
            "year": {"gan": "庚", "zhi": "午"},
            "month": {"gan": "辛", "zhi": "巳"},
            "day": {"gan": "甲", "zhi": "子"},
            "hour": {"gan": "戊", "zhi": "辰"},
        },
        "day_master": {"gan": "甲", "wuxing": "木"},
        "birth_info": {"gender": "female", "year": 1990},
        "wuxing_stats": {"木": 2, "火": 2, "土": 2, "金": 1, "水": 1},
        "shishen_stats": {"正官": 1},
    })
    structured = features["structured"]
    assert structured["wuxing_stats"]["木"] == 2
    assert structured["shishen_stats"]["正官"] == 1
```

In `bazi_features.py`, add these fields to `structured`:

```python
"wuxing_stats": chart.get("wuxing_stats") or {},
"shishen_stats": chart.get("shishen_stats") or {},
```

- [ ] **Step 5: Run enrichment and feature tests**

Run:

```powershell
python -m pytest tests/test_enrich_baziqa_chart_input.py tests/test_bazi_features.py -q
```

Expected: PASS.

- [ ] **Step 6: Generate enriched corpus**

Run:

```powershell
python scripts/enrich_baziqa_chart_input.py `
  --input benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl `
  --output benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl
```

Expected:

- `benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl` exists.
- `docs/BAZIQA_CHART_INPUT_ENRICHMENT_REPORT.md` shows coverage >= `90.0%`.

- [ ] **Step 7: Commit**

Run:

```powershell
git add scripts/enrich_baziqa_chart_input.py tests/test_enrich_baziqa_chart_input.py bazi_features.py tests/test_bazi_features.py docs/BAZIQA_CHART_INPUT_ENRICHMENT_REPORT.md
git commit -m "feat: enrich BaziQA corpus with chart input"
```

---

### Task 4: Chart-Structure Retrieval Scoring

**Files:**
- Modify: `case_index.py`
- Modify: `rag_prompt_builder.py`
- Modify: `tests/test_case_index.py`
- Modify: `tests/test_rag_prompt_builder.py`

- [ ] **Step 1: Add failing chart-structure retrieval test**

Append to `tests/test_case_index.py`:

```python
def test_chart_structure_boosts_same_day_master_and_month_branch(tmp_path):
    path = tmp_path / "corpus.jsonl"
    rows = [
        {
            "case_id": "same",
            "answer": "A",
            "domain": "career",
            "person": {"person_id": "p1", "name": "同盘", "gender": "male", "birth": {"year": 1980}},
            "question": "事业",
            "options": ["A. 升迁", "B. 婚姻"],
            "chart_input": {
                "four_pillars": {"month": {"zhi": "巳"}, "day": {"gan": "甲", "zhi": "子"}},
                "day_master": {"gan": "甲", "wuxing": "木"},
                "wuxing_stats": {"木": 2, "火": 2},
                "shishen_stats": {"正官": 1},
            },
        },
        {
            "case_id": "diff",
            "answer": "A",
            "domain": "career",
            "person": {"person_id": "p2", "name": "异盘", "gender": "male", "birth": {"year": 1980}},
            "question": "事业",
            "options": ["A. 升迁", "B. 婚姻"],
            "chart_input": {
                "four_pillars": {"month": {"zhi": "亥"}, "day": {"gan": "庚", "zhi": "午"}},
                "day_master": {"gan": "庚", "wuxing": "金"},
                "wuxing_stats": {"金": 3, "水": 2},
                "shishen_stats": {"七杀": 1},
            },
        },
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    from case_index import CaseIndex
    idx = CaseIndex(path)
    result = idx.top_k_cases({
        "text_blob": "事业",
        "structured": {
            "query_domain": "career",
            "day_master_gan": "甲",
            "month_zhi": "巳",
            "wuxing_stats": {"木": 2, "火": 2},
            "shishen_stats": {"正官": 1},
        },
    }, k=2)
    assert result[0]["person_id"] == "p1"
    assert "same_day_master" in result[0]["match_reasons"]
    assert "same_month_branch" in result[0]["match_reasons"]
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_case_index.py::test_chart_structure_boosts_same_day_master_and_month_branch -q
```

Expected: FAIL because `CaseIndex` does not store corpus chart features or score exact chart structure.

- [ ] **Step 3: Store chart features in CaseIndex**

In `case_index.py`, import the feature extractor:

```python
from bazi_features import extract as extract_bazi_features
```

Inside `_load`, when building each case, collect the first usable `chart_input` from rows:

```python
bucket = people.setdefault(pid, {"person": person, "facts": [], "domains": Counter(), "chart_input": None})
if row.get("chart_input") and bucket["chart_input"] is None:
    bucket["chart_input"] = row.get("chart_input")
```

When appending case dict, add:

```python
chart_features = extract_bazi_features(bucket.get("chart_input") or {})["structured"] if bucket.get("chart_input") else {}
```

and include:

```python
"chart_features": chart_features,
```

- [ ] **Step 4: Add chart-structure scoring**

In `case_index.py`, add:

```python
def _score_chart_structure(self, case: Dict[str, Any], structured: Dict[str, Any]) -> tuple:
    score = 0.0
    reasons = []
    chart = case.get("chart_features") or {}
    if not chart:
        return score, reasons
    if structured.get("day_master_gan") and structured.get("day_master_gan") == chart.get("day_master_gan"):
        score += 0.45
        reasons.append("same_day_master")
    if structured.get("day_master_wuxing") and structured.get("day_master_wuxing") == chart.get("day_master_wuxing"):
        score += 0.25
        reasons.append("same_day_master_wuxing")
    if structured.get("month_zhi") and structured.get("month_zhi") == chart.get("month_zhi"):
        score += 0.45
        reasons.append("same_month_branch")
    query_wuxing = structured.get("wuxing_stats") or {}
    case_wuxing = chart.get("wuxing_stats") or {}
    overlap = sum(min(int(query_wuxing.get(k, 0) or 0), int(case_wuxing.get(k, 0) or 0)) for k in ("木", "火", "土", "金", "水"))
    if overlap:
        score += min(overlap * 0.08, 0.40)
        reasons.append(f"wuxing_overlap:{overlap}")
    query_shishen = structured.get("shishen_stats") or {}
    case_shishen = chart.get("shishen_stats") or {}
    hits = sorted(k for k in query_shishen if k in case_shishen)
    if hits:
        score += min(len(hits) * 0.15, 0.45)
        reasons.append("shishen_overlap:" + ",".join(hits[:3]))
    return score, reasons
```

In `top_k_cases`, after structured scoring, add:

```python
chart_score, chart_reasons = self._score_chart_structure(case, structured)
all_reasons = list(reasons) + list(chart_reasons)
adj = score + structured_score + chart_score + semantic_score
```

- [ ] **Step 5: Update prompt formatting expectations**

Append to `tests/test_rag_prompt_builder.py`:

```python
def test_prompt_includes_chart_match_reasons():
    case = {
        "name": "同盘",
        "birth_year": 1980,
        "gender": "male",
        "domains": {"career": 1},
        "facts": ["事业 -> 升迁"],
        "_score": 3.2,
        "match_reasons": ["same_day_master", "same_month_branch"],
    }
    text = format_case_for_prompt(case)
    assert "same_day_master" in text
    assert "same_month_branch" in text
```

If `format_case_for_prompt` has another local name, update the test to the current formatter function and keep the assertion identical.

- [ ] **Step 6: Run retrieval tests**

Run:

```powershell
python -m pytest tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_features.py -q
```

Expected: PASS.

- [ ] **Step 7: Run ablation using enriched corpus**

Run:

```powershell
python scripts/run_baziqa_retrieval_ablation.py `
  --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl `
  --run `
  --repeats 3
```

Expected:

- Chart-structure reasons appear in trace.
- If chart-structure mode beats structured baseline, document the lift.

- [ ] **Step 8: Commit**

Run:

```powershell
git add case_index.py rag_prompt_builder.py tests/test_case_index.py tests/test_rag_prompt_builder.py docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md
git commit -m "feat: add chart-structure BaziQA retrieval scoring"
```

---

### Task 5: Domain-Specific Action Plan

**Files:**
- Create: `scripts/build_domain_action_plan.py`
- Create: `tests/test_build_domain_action_plan.py`
- Create: `docs/BAZIQA_DOMAIN_ACTION_PLAN.md`

- [ ] **Step 1: Add domain action plan tests**

Create `tests/test_build_domain_action_plan.py`:

```python
from scripts.build_domain_action_plan import build_actions, render_report


def test_build_actions_flags_low_accuracy_domains():
    summary = {
        "domain_summary": [
            {"domain": "health", "total": 5, "correct": 1, "accuracy": 0.2},
            {"domain": "career", "total": 8, "correct": 4, "accuracy": 0.5},
            {"domain": "study", "total": 1, "correct": 0, "accuracy": 0.0},
        ]
    }
    actions = build_actions(summary, min_cases=3, threshold=0.25)
    assert actions == [{
        "domain": "health",
        "total": 5,
        "accuracy": 0.2,
        "action": "add_domain_rules_and_examples",
    }]


def test_render_report_contains_domain_actions():
    text = render_report([{
        "domain": "health",
        "total": 5,
        "accuracy": 0.2,
        "action": "add_domain_rules_and_examples",
    }])
    assert "| health | 5 | 20.0% | add_domain_rules_and_examples |" in text
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_build_domain_action_plan.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Create domain action script**

Create `scripts/build_domain_action_plan.py`:

```python
import argparse
import json
from pathlib import Path


def build_actions(summary, min_cases=3, threshold=0.25):
    actions = []
    for row in summary.get("domain_summary", []):
        total = int(row.get("total") or 0)
        accuracy = float(row.get("accuracy") or 0.0)
        if total >= min_cases and accuracy < threshold:
            actions.append({
                "domain": row.get("domain") or "unknown",
                "total": total,
                "accuracy": accuracy,
                "action": "add_domain_rules_and_examples",
            })
    return actions


def render_report(actions):
    lines = [
        "# BaziQA Domain Action Plan",
        "",
        "| domain | total | accuracy | action |",
        "|---|---:|---:|---|",
    ]
    for action in actions:
        lines.append(f"| {action['domain']} | {action['total']} | {action['accuracy']:.1%} | {action['action']} |")
    if not actions:
        lines.append("| none | 0 | 0.0% | no_domain_below_threshold |")
    lines.extend([
        "",
        "Execution rule: only add domain-specific prompt or corpus changes for domains listed above.",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build domain action plan from BaziQA error attribution JSON.")
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--output", default="docs/BAZIQA_DOMAIN_ACTION_PLAN.md")
    parser.add_argument("--min-cases", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.25)
    args = parser.parse_args(argv)

    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    actions = build_actions(summary, min_cases=args.min_cases, threshold=args.threshold)
    Path(args.output).write_text(render_report(actions), encoding="utf-8")
    print(f"Domain action plan saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_build_domain_action_plan.py -q
```

Expected: PASS.

- [ ] **Step 5: Generate domain action plan**

After a current trace report exists, produce JSON summary from `scripts/analyze_baziqa_error_attribution.py` or add a JSON output flag in that script if needed. Then run:

```powershell
python scripts/build_domain_action_plan.py `
  --summary-json .tmp/baziqa_error_attribution_summary.json `
  --output docs/BAZIQA_DOMAIN_ACTION_PLAN.md
```

Expected:

- `docs/BAZIQA_DOMAIN_ACTION_PLAN.md` lists only domains with enough samples and low accuracy.
- Health, annual_fortune, study, and unknown are handled only when they meet sample thresholds.

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/build_domain_action_plan.py tests/test_build_domain_action_plan.py docs/BAZIQA_DOMAIN_ACTION_PLAN.md
git commit -m "feat: add BaziQA domain action planning"
```

---

### Task 6: Link Report Quality To Accuracy Work

**Files:**
- Create: `scripts/export_report_quality_samples.py`
- Create: `tests/test_export_report_quality_samples.py`
- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Add export tests**

Create `tests/test_export_report_quality_samples.py`:

```python
import json

from scripts.export_report_quality_samples import build_row


def test_build_row_creates_quality_gate_shape():
    chart = {"four_pillars": {"day": {"gan": "甲", "zhi": "子"}}, "day_master": {"gan": "甲", "wuxing": "木"}}
    row = build_row("case1", chart, "报告正文")
    assert row == {"case_id": "case1", "chart": chart, "report_text": "报告正文"}
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_export_report_quality_samples.py -q
```

Expected: FAIL because `scripts/export_report_quality_samples.py` does not exist.

- [ ] **Step 3: Create sample exporter**

Create `scripts/export_report_quality_samples.py`:

```python
import argparse
import json
from pathlib import Path


def build_row(case_id, chart, report_text):
    return {"case_id": case_id, "chart": chart, "report_text": report_text}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export report quality samples to JSONL gate input.")
    parser.add_argument("--input-json", required=True, help="JSON list with case_id, chart, report_text")
    parser.add_argument("--output-jsonl", default=".tmp/report_quality_samples.jsonl")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("cases", [])
    Path(args.output_jsonl).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.output_jsonl).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(build_row(row["case_id"], row["chart"], row["report_text"]), ensure_ascii=False) + "\n")
    print(f"Report quality samples saved to {args.output_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_export_report_quality_samples.py tests/test_verify_report_quality_gate.py tests/test_bazi_report_validator.py -q
```

Expected: PASS.

- [ ] **Step 5: Run report quality gate**

Prepare `.tmp/report_quality_manual_cases.json` with at least 5 real命主 reports generated after the retrieval change. Then run:

```powershell
python scripts/export_report_quality_samples.py `
  --input-json .tmp/report_quality_manual_cases.json `
  --output-jsonl .tmp/report_quality_samples.jsonl

python scripts/verify_report_quality_gate.py `
  --reports-jsonl .tmp/report_quality_samples.jsonl `
  --output docs/REPORT_QUALITY_GATE_REPORT.md
```

Expected:

- `docs/REPORT_QUALITY_GATE_REPORT.md` exists.
- Gate is PASS only when no deterministic hard errors are present.

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/export_report_quality_samples.py tests/test_export_report_quality_samples.py docs/REPORT_QUALITY_GATE_REPORT.md docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "test: link report quality gate to BaziQA accuracy work"
```

---

### Task 7: Final Accuracy And Judgment Report

**Files:**
- Create: `docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md`
- Modify: `docs/BAZIQA_PROJECT_ROADMAP.md`
- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Create final report from measured results**

Create `docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md` with this exact structure:

```markdown
# BaziQA Accuracy And Judgment Improvement Report

## Stable Accuracy Status

| configuration | runs | mean | min | max | gate |
|---|---:|---:|---:|---:|---|
| bm25 | 0 | 0.0% | 0.0% | 0.0% | not_run |
| structured | 0 | 0.0% | 0.0% | 0.0% | not_run |
| structured_semantic | 0 | 0.0% | 0.0% | 0.0% | not_run |
| semantic_low | 0 | 0.0% | 0.0% | 0.0% | not_run |

## Retrieval Decision

- Default retrieval mode: unchanged until repeats=3 supports a change.
- Default rag_k: 2 unless a repeats=3 report proves another k is better.
- Semantic overlap: disabled or reduced if full 40-case validation is below structured baseline.

## Chart Input Coverage

- Corpus chart_input coverage: 0.0%.
- Acceptance threshold: 90.0%.

## Weak Domains

| domain | action |
|---|---|
| none | wait_for_current_trace |

## Report Quality Gate

- Total reports: 0
- Failed reports: 0
- Gate: not_run

## Final Decision

Current status is BLOCKED until real 40-case and repeats=3 evidence is recorded.
```

Replace the initial `not_run` rows with measured values as soon as the corresponding reports exist. If a report is still missing at handoff time, keep the row as `not_run` and record the missing command in the execution summary.

- [ ] **Step 2: Update roadmap**

In `docs/BAZIQA_PROJECT_ROADMAP.md`, add a section named:

```markdown
## 当前专项计划：Bazi 准确率与命理判断水平提升

- 先跑 refined P2 完整 40 题，确认 10 题 smoke 是否可复现。
- 用 retrieval ablation 决定 semantic overlap 是否默认启用。
- 补齐 corpus chart_input 后，新增命盘结构相似度检索。
- 用 domain action plan 做 health / annual_fortune / study / unknown 等领域攻坚。
- 用 report quality gate 验证真实命主报告没有确定性命理硬错。
```

- [ ] **Step 3: Update acceptance report**

In `docs/BAZIQA_ACCEPTANCE_REPORT.md`, add a Current Gate Status entry:

```markdown
- Bazi accuracy and judgment专项：BLOCKED until refined P2 40-case validation, retrieval ablation repeats=3, chart_input coverage, and report quality gate are all recorded.
```

- [ ] **Step 4: Documentation self-check**

Run:

```powershell
rg -n "not_run|0.0%|wait_for_current_trace|BLOCKED until" docs\BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md docs\BAZIQA_PROJECT_ROADMAP.md docs\BAZIQA_ACCEPTANCE_REPORT.md
```

Expected:

- `not_run` status appears only before real runs.
- After real runs, `not_run` rows are replaced with measured values.

- [ ] **Step 5: Commit**

Run:

```powershell
git add docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md docs/BAZIQA_PROJECT_ROADMAP.md docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "docs: record BaziQA accuracy and judgment improvement status"
```

---

## Final Verification

Run non-network tests:

```powershell
python -m pytest `
  tests/test_baziqa_refined_p2_validation.py `
  tests/test_baziqa_retrieval_ablation.py `
  tests/test_enrich_baziqa_chart_input.py `
  tests/test_build_domain_action_plan.py `
  tests/test_export_report_quality_samples.py `
  tests/test_case_index.py `
  tests/test_bazi_features.py `
  tests/test_rag_prompt_builder.py `
  tests/test_verify_report_quality_gate.py `
  tests/test_bazi_report_validator.py `
  -q
```

Expected: all selected tests PASS.

Run full deterministic suite:

```powershell
python -m pytest -q -m "not e2e"
```

Expected: PASS.

Run real DeepSeek validation only after confirming network and key:

```powershell
python scripts/run_baziqa_refined_p2_validation.py --run
python scripts/run_baziqa_retrieval_ablation.py --run --repeats 3
```

Expected:

- Full 40-case result is recorded.
- Repeats=3 report decides whether semantic overlap stays enabled.
- Any result below gate is documented as BLOCKED, not PASS.

Run corpus enrichment:

```powershell
python scripts/enrich_baziqa_chart_input.py `
  --input benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl `
  --output benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl
```

Expected: chart_input coverage >= `90.0%`.

Run report quality gate:

```powershell
python scripts/verify_report_quality_gate.py `
  --reports-jsonl .tmp/report_quality_samples.jsonl `
  --output docs/REPORT_QUALITY_GATE_REPORT.md
```

Expected: PASS only when all sampled reports have zero deterministic hard errors.

## Decision Rules

- If refined P2 full 40-case result is below `27.5%`, disable semantic overlap by default.
- If refined P2 full 40-case result is `30.0%` to `34.9%`, keep it experimental and run retrieval ablation.
- If any retrieval mode reaches repeats=3 mean >= `35.0%`, treat it as a candidate but not accepted.
- If any retrieval mode reaches repeats=3 mean >= `40.0%` and min >= `35.0%`, accept it as the new default.
- If chart_input coverage is below `90.0%`, do not claim chart-structure retrieval is fully active.
- If report quality gate fails, do not claim real命主报告质量 improved even when BaziQA accuracy improves.

## Self-Review

- Spec coverage: The plan covers refined P2 validation, retrieval ablation, corpus chart enrichment, chart-structure scoring, domain action planning, and real report quality gating.
- Completion scan: The plan contains explicit initial `not_run` status rows and requires measured values after real runs.
- Type consistency: `chart_input`, `parser_valid`, `rag_k`, `match_reasons`, `wuxing_stats`, and `shishen_stats` match existing project naming.
