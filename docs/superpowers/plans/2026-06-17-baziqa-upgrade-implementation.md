# BaziQA Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the public ChenJiangxi/BaziQA dataset and benchmark method into XuanJiZi so model, prompt, reasoning protocol, and timeline-quality upgrades are measured by repeatable BaZi-specific tests.

**Architecture:** Keep XuanJiZi's existing FastAPI, SQLite, pytest, and vanilla JS stack. Add a narrow BaziQA ingestion layer under `benchmark/runners/`, a prompt formatter under `benchmark/formatters/`, and extend the existing benchmark runner/data store/dashboard instead of creating a parallel evaluation system.

**Tech Stack:** Python, SQLite, pytest, FastAPI, DeepSeek/Anthropic adapters through `claude_api.py`, existing `benchmark.scorers`, existing `benchmark-dashboard.js`.

---

## Source References

This plan is based on:

- `https://github.com/ChenJiangxi/BaziQA`
- `https://github.com/ChenJiangxi/BaziQA/blob/main/dataset_and_input_format.md`
- `https://github.com/ChenJiangxi/BaziQA/blob/main/benchmark_report.md`
- `https://arxiv.org/abs/2602.12889`

Relevant BaziQA facts to preserve in implementation:

- Contest8 covers 2021-2025.
- Each Contest8 year has 8 persons and 40 questions.
- Contest8 total is 200 four-choice questions.
- Celebrity50 has 50 public figures and about 250 questions.
- Fields include `person_id`, `name`, `profile.birth`, `profile.gender`, `categories`, `questions`, `question_id`, `question`, `options`, and `answer`.
- Benchmark comparison should separate direct/multi-turn/structured methods and aggregate by year/domain rather than only reporting one global score.

---

## Scope Check

This plan covers the evaluation upgrade only. It does not implement the AuraMate-style product UI, subscription flow, social features, or a public benchmark marketing page. Those should follow after this plan proves that model/prompt changes are measurable.

Primary deliverables:

1. Import BaziQA Contest8 and Celebrity50 into XuanJiZi's benchmark storage.
2. Generate XuanJiZi-compatible JSONL benchmark datasets.
3. Run direct-choice, multi-turn, and structured-reasoning benchmark modes.
4. Store run metadata and domain/year scores.
5. Update dashboard/reporting to expose weak domains and year-level drift.
6. Document licensing, citation, data splits, and release quality gates.

---

## File Structure

Create:

- `benchmark/formatters/__init__.py`: package marker for prompt formatters.
- `benchmark/formatters/baziqa_prompt.py`: BaziQA case-to-prompt formatting functions.
- `benchmark/runners/import_baziqa_dataset.py`: importer for BaziQA source JSON files.
- `benchmark/datasets/baziqa/README_SOURCE.md`: source, license, citation, and data split policy.
- `tests/fixtures/baziqa/contest8_sample.json`: small Contest8 fixture.
- `tests/fixtures/baziqa/celebrity50_sample.json`: small Celebrity50 fixture.
- `tests/test_baziqa_importer.py`: importer tests.
- `tests/test_baziqa_prompt_formatter.py`: prompt formatting tests.
- `docs/BAZIQA_UPGRADE.md`: implementation-facing strategy and operating guide.

Modify:

- `benchmark/runners/run_benchmark.py`: add methods, repeat runs, year/domain metadata, and structured prompt mode.
- `benchmark/reports/generate_report.py`: include year/domain/method breakdowns and regression gate summary.
- `data_store.py`: add optional fields to `benchmark_runs` for method details and aggregate metadata if missing.
- `api_server.py`: expose benchmark run detail fields already stored in SQLite.
- `static/benchmark.html`: add year/domain cards if needed.
- `static/js/benchmark-dashboard.js`: render method/year/domain breakdowns.
- `tests/test_benchmark_runner.py`: cover benchmark methods and repeat-run aggregation.
- `tests/test_benchmark_report.py`: cover new report sections.
- `.gitignore`: ignore locally downloaded raw BaziQA clone if not vendored.

Do not modify:

- `.deepseek_key`
- `.anthropic_key`
- `bazi_data.db` manually
- Existing generated `dist/` or `build/` artifacts

---

## Data Policy

Recommended path:

- Vendor only small test fixtures in `tests/fixtures/baziqa/`.
- Keep raw BaziQA clone outside source control or under `benchmark/datasets/baziqa/raw/` only if the owner explicitly wants to vendor the MIT dataset.
- Generated normalized datasets go under `benchmark/datasets/`.

If raw data is vendored, include:

- Original MIT license notice.
- `README_SOURCE.md`.
- Modification note stating that XuanJiZi normalized fields for internal benchmark use.

---

### Task 1: Add BaziQA Fixtures and Source Documentation

**Files:**

- Create: `benchmark/datasets/baziqa/README_SOURCE.md`
- Create: `tests/fixtures/baziqa/contest8_sample.json`
- Create: `tests/fixtures/baziqa/celebrity50_sample.json`

- [ ] **Step 1: Create source documentation**

Create `benchmark/datasets/baziqa/README_SOURCE.md`:

```markdown
# BaziQA Source Notes

Source repository: https://github.com/ChenJiangxi/BaziQA

Paper: https://arxiv.org/abs/2602.12889

Dataset files used by XuanJiZi:

- `contest8_2021.json`
- `contest8_2022.json`
- `contest8_2023.json`
- `contest8_2024.json`
- `contest8_2025.json`
- `celebrity50_zh.json`

License:

The upstream repository states that the dataset uses the MIT License. Keep the upstream license and attribution when vendoring or redistributing derived files.

XuanJiZi normalization:

- Contest8 questions are converted into JSONL rows with one question per line.
- `person_id`, `profile`, `birth`, `gender`, `question`, `options`, and `answer` are preserved.
- `source_year`, `contest_id`, and `domain` are added when available.
- Celebrity events are preserved as `verified_events` for timeline and life-event evaluation.

Recommended split:

- Development: Contest8 2021-2023
- Validation: Contest8 2024
- Locked test: Contest8 2025
- Timeline calibration: Celebrity50
```

- [ ] **Step 2: Add a Contest8 fixture**

Create `tests/fixtures/baziqa/contest8_sample.json`:

```json
[
  {
    "contest_id": "contest8_2025",
    "current_year": "2025",
    "description": "fixture",
    "total_questions": 2
  },
  {
    "person_id": "fixture_female_19900101_P001",
    "name": "1990年出生女性",
    "profile": {
      "birth": {
        "year": 1990,
        "month": 1,
        "day": 1,
        "hour": 9,
        "minute": 0,
        "place": "北京，中国",
        "approximate": false
      },
      "gender": "female"
    },
    "categories": {
      "事业": [],
      "财富": [],
      "感情": [],
      "健康": [],
      "六亲": []
    },
    "questions": [
      {
        "question_id": "fixture_female_19900101_P001-Q1",
        "question": "此命事业更适合哪类发展？",
        "options": ["A. 稳定组织", "B. 高风险投机", "C. 完全不工作", "D. 随机选择"],
        "answer": "A"
      },
      {
        "question_id": "fixture_female_19900101_P001-Q2",
        "question": "此命健康建议应如何表达？",
        "options": ["A. 规律作息", "B. 断言重病", "C. 替代医生", "D. 恐吓用户"],
        "answer": "A"
      }
    ]
  }
]
```

- [ ] **Step 3: Add a Celebrity50 fixture**

Create `tests/fixtures/baziqa/celebrity50_sample.json`:

```json
[
  {
    "person_id": "fixture_celebrity_P001",
    "name": "Fixture Celebrity",
    "profile": {
      "birth": {
        "year": 1980,
        "month": 5,
        "day": 6,
        "hour": 12,
        "minute": 0,
        "place": "Shanghai, China",
        "approximate": false
      },
      "gender": "male"
    },
    "categories": {
      "事业": ["2005年进入重要事业阶段", "2015年事业转型"],
      "财富": ["2018年财富显著增长"],
      "感情": ["2010年结婚"],
      "健康": ["2020年公开健康事件"],
      "六亲": ["1999年家庭迁居"]
    },
    "questions": [
      {
        "question_id": "fixture_celebrity_P001-Q1",
        "question": "此人在哪一年结婚？",
        "options": ["A. 2009", "B. 2010", "C. 2011", "D. 2012"],
        "answer": "B"
      }
    ]
  }
]
```

- [ ] **Step 4: Commit fixtures and docs**

Run:

```powershell
git add benchmark/datasets/baziqa/README_SOURCE.md tests/fixtures/baziqa/contest8_sample.json tests/fixtures/baziqa/celebrity50_sample.json
git commit -m "docs: add baziqa source notes and fixtures"
```

Expected:

```text
[branch ...] docs: add baziqa source notes and fixtures
```

---

### Task 2: Implement BaziQA Importer

**Files:**

- Create: `benchmark/runners/import_baziqa_dataset.py`
- Test: `tests/test_baziqa_importer.py`

- [ ] **Step 1: Write importer tests**

Create `tests/test_baziqa_importer.py`:

```python
import json
from pathlib import Path

from benchmark.runners.import_baziqa_dataset import (
    load_contest8_file,
    load_celebrity50_file,
    normalize_contest8_questions,
    normalize_celebrity_questions,
    write_jsonl,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baziqa"


def test_normalize_contest8_questions():
    data = load_contest8_file(FIXTURE_DIR / "contest8_sample.json")
    rows = normalize_contest8_questions(data)

    assert len(rows) == 2
    assert rows[0]["case_id"] == "fixture_female_19900101_P001-Q1"
    assert rows[0]["person"]["birth"]["year"] == 1990
    assert rows[0]["person"]["gender"] == "female"
    assert rows[0]["domain"] == "unknown"
    assert rows[0]["answer"] == "A"
    assert rows[0]["source"] == "contest8_2025"


def test_normalize_celebrity_questions_preserves_events():
    data = load_celebrity50_file(FIXTURE_DIR / "celebrity50_sample.json")
    rows = normalize_celebrity_questions(data)

    assert len(rows) == 1
    assert rows[0]["case_id"] == "fixture_celebrity_P001-Q1"
    assert rows[0]["person"]["name"] == "Fixture Celebrity"
    assert "事业" in rows[0]["verified_events"]
    assert rows[0]["answer"] == "B"


def test_write_jsonl(tmp_path):
    rows = [{"case_id": "q1", "answer": "A"}, {"case_id": "q2", "answer": "B"}]
    output = tmp_path / "out.jsonl"

    write_jsonl(rows, output)

    loaded = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert loaded == rows
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_baziqa_importer.py -q
```

Expected:

```text
FAILED
ModuleNotFoundError: No module named 'benchmark.runners.import_baziqa_dataset'
```

- [ ] **Step 3: Implement importer**

Create `benchmark/runners/import_baziqa_dataset.py`:

```python
import argparse
import json
from pathlib import Path


DOMAIN_KEYWORDS = {
    "career": ["事业", "工作", "职业", "升职", "官"],
    "wealth": ["财富", "财运", "钱", "富", "投资"],
    "relationship": ["感情", "婚", "恋", "配偶"],
    "health": ["健康", "疾病", "身体", "意外"],
    "family": ["六亲", "父", "母", "兄弟", "子女", "家庭"],
    "study": ["学业", "学历", "学习", "考试"],
    "annual_fortune": ["流年", "哪一年", "年份", "大运"],
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_contest8_file(path):
    data = load_json(path)
    if not isinstance(data, list) or not data:
        raise ValueError("Contest8 file must be a non-empty JSON array")
    return data


def load_celebrity50_file(path):
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError("Celebrity50 file must be a JSON array")
    return data


def infer_domain(question, categories=None):
    text = question or ""
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return domain
    if isinstance(categories, dict):
        for label in categories.keys():
            if label in text:
                return {
                    "事业": "career",
                    "财富": "wealth",
                    "感情": "relationship",
                    "健康": "health",
                    "六亲": "family",
                    "学业": "study",
                }.get(label, "unknown")
    return "unknown"


def normalize_person(person):
    profile = person.get("profile") or {}
    birth = profile.get("birth") or {}
    return {
        "person_id": person.get("person_id", ""),
        "name": person.get("name", ""),
        "gender": profile.get("gender", ""),
        "birth": {
            "year": birth.get("year"),
            "month": birth.get("month"),
            "day": birth.get("day"),
            "hour": birth.get("hour", 0),
            "minute": birth.get("minute", 0),
            "place": birth.get("place", ""),
            "approximate": bool(birth.get("approximate", False)),
        },
    }


def normalize_question(person, question, source, source_year=None):
    return {
        "case_id": question.get("question_id", ""),
        "source": source,
        "source_year": source_year,
        "domain": infer_domain(question.get("question", ""), person.get("categories")),
        "person": normalize_person(person),
        "question": question.get("question", ""),
        "options": question.get("options", []),
        "answer": question.get("answer", ""),
        "expected_evidence": [],
        "verified_events": person.get("categories", {}),
        "difficulty": "unknown",
    }


def normalize_contest8_questions(data):
    meta = data[0]
    contest_id = meta.get("contest_id", "contest8")
    source_year = meta.get("current_year")
    rows = []
    for person in data[1:]:
        for question in person.get("questions", []):
            rows.append(normalize_question(person, question, contest_id, source_year))
    return rows


def normalize_celebrity_questions(data):
    rows = []
    for person in data:
        for question in person.get("questions", []):
            rows.append(normalize_question(person, question, "celebrity50", None))
    return rows


def write_jsonl(rows, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Normalize BaziQA JSON files into XuanJiZi JSONL")
    parser.add_argument("--source-dir", required=True, help="Directory containing BaziQA JSON files")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--include-celebrity", action="store_true")
    args = parser.parse_args(argv)

    source_dir = Path(args.source_dir)
    rows = []
    for year in range(2021, 2026):
        path = source_dir / f"contest8_{year}.json"
        if path.exists():
            rows.extend(normalize_contest8_questions(load_contest8_file(path)))

    celebrity_path = source_dir / "celebrity50_zh.json"
    if args.include_celebrity and celebrity_path.exists():
        rows.extend(normalize_celebrity_questions(load_celebrity50_file(celebrity_path)))

    write_jsonl(rows, args.output)
    print(json.dumps({"output": args.output, "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run importer tests**

Run:

```powershell
python -m pytest tests/test_baziqa_importer.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Generate a local normalized file from a BaziQA clone**

If BaziQA is cloned at `F:\project\BaziQA\data`, run:

```powershell
python benchmark/runners/import_baziqa_dataset.py --source-dir F:\project\BaziQA\data --output benchmark/datasets/baziqa_contest8_2021_2025.jsonl
```

Expected:

```text
{"output": "benchmark/datasets/baziqa_contest8_2021_2025.jsonl", "rows": 200}
```

- [ ] **Step 6: Commit importer**

```powershell
git add benchmark/runners/import_baziqa_dataset.py tests/test_baziqa_importer.py
git commit -m "feat: import baziqa benchmark data"
```

---

### Task 3: Add BaziQA Prompt Formatter

**Files:**

- Create: `benchmark/formatters/__init__.py`
- Create: `benchmark/formatters/baziqa_prompt.py`
- Test: `tests/test_baziqa_prompt_formatter.py`

- [ ] **Step 1: Write formatter tests**

Create `tests/test_baziqa_prompt_formatter.py`:

```python
from benchmark.formatters.baziqa_prompt import (
    format_birth_line,
    format_options,
    format_direct_choice_prompt,
    format_structured_reasoning_prompt,
)


def _case():
    return {
        "case_id": "q1",
        "domain": "career",
        "person": {
            "name": "命主测试",
            "gender": "female",
            "birth": {
                "year": 1990,
                "month": 1,
                "day": 1,
                "hour": 9,
                "minute": 0,
                "place": "北京，中国",
            },
        },
        "question": "此命事业更适合哪类发展？",
        "options": ["A. 稳定组织", "B. 高风险投机", "C. 完全不工作", "D. 随机选择"],
    }


def test_format_birth_line():
    text = format_birth_line(_case()["person"])
    assert "1990年1月1日9时0分" in text
    assert "北京，中国" in text
    assert "female" in text


def test_format_options():
    assert "A. 稳定组织" in format_options(_case()["options"])


def test_format_direct_choice_prompt():
    prompt = format_direct_choice_prompt(_case())
    assert "请直接回答选项字母" in prompt
    assert "此命事业" in prompt
    assert "A. 稳定组织" in prompt


def test_format_structured_reasoning_prompt():
    prompt = format_structured_reasoning_prompt(_case())
    for marker in ["第一阶段：量化扫描", "第二阶段：冲突定级", "第三阶段：应象映射"]:
        assert marker in prompt
    assert "最后一行必须写" in prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_baziqa_prompt_formatter.py -q
```

Expected:

```text
FAILED
ModuleNotFoundError: No module named 'benchmark.formatters'
```

- [ ] **Step 3: Add package marker**

Create `benchmark/formatters/__init__.py`:

```python
"""Prompt formatters for benchmark datasets."""
```

- [ ] **Step 4: Implement formatter**

Create `benchmark/formatters/baziqa_prompt.py`:

```python
def format_birth_line(person):
    birth = person.get("birth", {})
    return (
        f"姓名：{person.get('name', '')}\n"
        f"性别：{person.get('gender', '')}\n"
        f"出生：{birth.get('year')}年{birth.get('month')}月{birth.get('day')}日"
        f"{birth.get('hour', 0)}时{birth.get('minute', 0)}分\n"
        f"地点：{birth.get('place', '')}"
    )


def format_options(options):
    return "\n".join(str(opt) for opt in options)


def format_direct_choice_prompt(case):
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。",
        "请根据命主信息回答四选一题。请直接回答选项字母 A/B/C/D，不要解释。",
        "## 命主信息",
        format_birth_line(case.get("person", {})),
        "## 问题",
        case.get("question", ""),
        "## 选项",
        format_options(case.get("options", [])),
        "请直接回答选项字母。",
    ])


def format_multi_turn_context(case):
    return "\n\n".join([
        "你是一位严谨的八字命理评测助手。以下是命主资料，后续问题都围绕此命主。",
        "## 命主信息",
        format_birth_line(case.get("person", {})),
        f"领域：{case.get('domain', 'unknown')}",
    ])


def format_multi_turn_question(case):
    return "\n\n".join([
        "请回答以下四选一问题，只输出选项字母 A/B/C/D。",
        case.get("question", ""),
        format_options(case.get("options", [])),
    ])


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
        "最后一行必须写：答案：A/B/C/D",
    ])
```

- [ ] **Step 5: Run formatter tests**

Run:

```powershell
python -m pytest tests/test_baziqa_prompt_formatter.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit formatter**

```powershell
git add benchmark/formatters tests/test_baziqa_prompt_formatter.py
git commit -m "feat: add baziqa prompt formatter"
```

---

### Task 4: Extend Benchmark Runner Methods

**Files:**

- Modify: `benchmark/runners/run_benchmark.py`
- Modify: `tests/test_benchmark_runner.py`

- [ ] **Step 1: Add tests for method-specific prompt selection**

Append to `tests/test_benchmark_runner.py`:

```python
def test_build_prompt_supports_direct_choice():
    from benchmark.runners import run_benchmark

    case = {
        'case_id': 'q1',
        'domain': 'career',
        'person': {'name': '命主', 'gender': 'male', 'birth': {'year': 1990, 'month': 1, 'day': 1, 'hour': 9, 'minute': 0, 'place': '北京'}},
        'question': '事业如何？',
        'options': ['A. 稳定', 'B. 投机', 'C. 不工作', 'D. 随机'],
    }

    prompt = run_benchmark.build_benchmark_prompt(case, method='direct_choice')
    assert '请直接回答选项字母' in prompt


def test_build_prompt_supports_structured_reasoning():
    from benchmark.runners import run_benchmark

    case = {
        'case_id': 'q1',
        'domain': 'career',
        'person': {'name': '命主', 'gender': 'male', 'birth': {'year': 1990, 'month': 1, 'day': 1, 'hour': 9, 'minute': 0, 'place': '北京'}},
        'question': '事业如何？',
        'options': ['A. 稳定', 'B. 投机', 'C. 不工作', 'D. 随机'],
    }

    prompt = run_benchmark.build_benchmark_prompt(case, method='structured_reasoning')
    assert '第一阶段：量化扫描' in prompt
    assert '答案：A/B/C/D' in prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_benchmark_runner.py::test_build_prompt_supports_direct_choice tests/test_benchmark_runner.py::test_build_prompt_supports_structured_reasoning -q
```

Expected:

```text
FAILED
TypeError: build_benchmark_prompt() got an unexpected keyword argument 'method'
```

- [ ] **Step 3: Update imports**

In `benchmark/runners/run_benchmark.py`, add:

```python
from benchmark.formatters.baziqa_prompt import (
    format_direct_choice_prompt,
    format_structured_reasoning_prompt,
)
```

- [ ] **Step 4: Update `build_benchmark_prompt`**

Replace the existing function with:

```python
def build_benchmark_prompt(case, method='direct_choice'):
    if method == 'structured_reasoning':
        return format_structured_reasoning_prompt(case)
    if method in ('direct_choice', 'multi_turn'):
        return format_direct_choice_prompt(case)
    raise ValueError(f"Unsupported benchmark method: {method}")
```

- [ ] **Step 5: Pass method into model benchmark**

Change:

```python
def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20):
```

to:

```python
def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20, method='direct_choice'):
```

Change:

```python
prompt = build_benchmark_prompt(case)
```

to:

```python
prompt = build_benchmark_prompt(case, method=method)
```

- [ ] **Step 6: Add CLI method argument**

Add:

```python
parser.add_argument('--method', default='direct_choice', choices=['direct_choice', 'multi_turn', 'structured_reasoning'])
```

Pass into `run_model_benchmark`:

```python
model_result = run_model_benchmark(
    cases, args.provider, args.model, args.prompt_version, args.max_cases, method=args.method
)
```

Set report data:

```python
"method": args.method,
```

Set `data_store.save_benchmark_run(method=args.method, ...)`.

- [ ] **Step 7: Run runner tests**

Run:

```powershell
python -m pytest tests/test_benchmark_runner.py -q
```

Expected:

```text
pass
```

- [ ] **Step 8: Commit runner method support**

```powershell
git add benchmark/runners/run_benchmark.py tests/test_benchmark_runner.py
git commit -m "feat: support baziqa benchmark methods"
```

---

### Task 5: Add Year and Domain Aggregation

**Files:**

- Modify: `benchmark/scorers/choice_accuracy.py`
- Modify: `benchmark/runners/run_benchmark.py`
- Test: `tests/test_benchmark_choice_accuracy.py`

- [ ] **Step 1: Add test for year breakdown**

Append to `tests/test_benchmark_choice_accuracy.py`:

```python
def test_score_choice_answers_breaks_down_by_year():
    cases = [
        {'case_id': 'q1', 'source_year': '2021', 'answer': 'A'},
        {'case_id': 'q2', 'source_year': '2021', 'answer': 'B'},
        {'case_id': 'q3', 'source_year': '2022', 'answer': 'C'},
    ]
    preds = {'q1': 'A', 'q2': 'C', 'q3': 'C'}

    result = score_choice_answers(cases, preds)

    assert result['by_year']['2021']['total'] == 2
    assert result['by_year']['2021']['correct'] == 1
    assert result['by_year']['2022']['accuracy'] == 1.0
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_benchmark_choice_accuracy.py::test_score_choice_answers_breaks_down_by_year -q
```

Expected:

```text
FAILED
KeyError: 'by_year'
```

- [ ] **Step 3: Update scorer**

In `benchmark/scorers/choice_accuracy.py`, add year aggregation using the same pattern as domain aggregation:

```python
def _empty_bucket():
    return {'total': 0, 'correct': 0, 'missing': 0, 'accuracy': 0.0}
```

Inside `score_choice_answers`, initialize:

```python
by_year = {}
```

For each valid case:

```python
year = str(case.get('source_year') or 'unknown')
by_year.setdefault(year, _empty_bucket())
by_year[year]['total'] += 1
```

When missing:

```python
by_year[year]['missing'] += 1
```

When correct:

```python
by_year[year]['correct'] += 1
```

After loop:

```python
for bucket in by_year.values():
    bucket['accuracy'] = bucket['correct'] / bucket['total'] if bucket['total'] else 0.0
```

Return:

```python
'by_year': by_year,
```

- [ ] **Step 4: Run scorer tests**

Run:

```powershell
python -m pytest tests/test_benchmark_choice_accuracy.py -q
```

Expected:

```text
pass
```

- [ ] **Step 5: Add year breakdown to report data**

In `benchmark/runners/run_benchmark.py`, ensure `choice_result` is passed unchanged into `report_data`, since it now includes `by_year`.

- [ ] **Step 6: Commit aggregation**

```powershell
git add benchmark/scorers/choice_accuracy.py benchmark/runners/run_benchmark.py tests/test_benchmark_choice_accuracy.py
git commit -m "feat: add baziqa year accuracy breakdown"
```

---

### Task 6: Enhance Benchmark Report

**Files:**

- Modify: `benchmark/reports/generate_report.py`
- Modify: `tests/test_benchmark_report.py`

- [ ] **Step 1: Add report test for BaziQA breakdowns**

Append to `tests/test_benchmark_report.py`:

```python
def test_report_contains_baziqa_year_and_method_breakdowns():
    from benchmark.reports.generate_report import generate_markdown_report

    data = {
        "run_id": "run1",
        "dataset": "baziqa_contest8_2021_2025.jsonl",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "method": "structured_reasoning",
        "prompt_version": "srp_v2",
        "reasoning_protocol": "baziqa_srp_v1",
        "choice_accuracy": {
            "accuracy": 0.4,
            "total": 200,
            "correct": 80,
            "by_domain": {"career": {"total": 40, "correct": 20, "accuracy": 0.5}},
            "by_year": {"2025": {"total": 40, "correct": 12, "accuracy": 0.3}},
        },
        "evidence_score": 0.5,
        "stability_score": 0.7,
        "safety_score": 0.95,
        "case_details": [],
    }

    report = generate_markdown_report(data)

    assert "structured_reasoning" in report
    assert "Accuracy by Year" in report
    assert "2025" in report
    assert "Accuracy by Domain" in report
    assert "career" in report
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_benchmark_report.py::test_report_contains_baziqa_year_and_method_breakdowns -q
```

Expected:

```text
FAILED
AssertionError
```

- [ ] **Step 3: Update markdown report**

In `benchmark/reports/generate_report.py`, add sections:

```python
def _format_accuracy_table(title, buckets):
    lines = [f"## {title}", "", "| Key | Total | Correct | Accuracy |", "|---|---:|---:|---:|"]
    for key, item in sorted((buckets or {}).items()):
        total = item.get("total", 0)
        correct = item.get("correct", 0)
        accuracy = item.get("accuracy", 0.0)
        lines.append(f"| {key} | {total} | {correct} | {accuracy:.1%} |")
    return "\n".join(lines)
```

Inside `generate_markdown_report`, append:

```python
choice = data.get("choice_accuracy") or {}
lines.append(f"- Method: {data.get('method', '')}")
lines.append(f"- Prompt Version: {data.get('prompt_version', '')}")
lines.append("")
lines.append(_format_accuracy_table("Accuracy by Year", choice.get("by_year", {})))
lines.append("")
lines.append(_format_accuracy_table("Accuracy by Domain", choice.get("by_domain", {})))
lines.append("")
```

- [ ] **Step 4: Run report tests**

Run:

```powershell
python -m pytest tests/test_benchmark_report.py -q
```

Expected:

```text
pass
```

- [ ] **Step 5: Commit report enhancement**

```powershell
git add benchmark/reports/generate_report.py tests/test_benchmark_report.py
git commit -m "feat: report baziqa year and domain accuracy"
```

---

### Task 7: Add Regression Gates

**Files:**

- Create or modify: `benchmark/scorers/regression_gate.py`
- Test: `tests/test_benchmark_regression_gate.py`
- Modify: `benchmark/runners/run_benchmark.py`

- [ ] **Step 1: Write regression gate tests**

Create `tests/test_benchmark_regression_gate.py`:

```python
from benchmark.scorers.regression_gate import evaluate_regression_gate


def test_regression_gate_passes_for_improvement():
    baseline = {"accuracy": 0.35, "safety_score": 0.9}
    current = {"accuracy": 0.38, "safety_score": 0.92}

    result = evaluate_regression_gate(current, baseline)

    assert result["passed"] is True
    assert result["failures"] == []


def test_regression_gate_fails_for_accuracy_drop():
    baseline = {"accuracy": 0.40, "safety_score": 0.9}
    current = {"accuracy": 0.34, "safety_score": 0.91}

    result = evaluate_regression_gate(current, baseline, max_accuracy_drop=0.03)

    assert result["passed"] is False
    assert any("accuracy" in item for item in result["failures"])


def test_regression_gate_fails_for_safety_drop():
    baseline = {"accuracy": 0.40, "safety_score": 0.95}
    current = {"accuracy": 0.41, "safety_score": 0.80}

    result = evaluate_regression_gate(current, baseline, max_safety_drop=0.05)

    assert result["passed"] is False
    assert any("safety" in item for item in result["failures"])
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_benchmark_regression_gate.py -q
```

Expected:

```text
FAILED
ModuleNotFoundError
```

- [ ] **Step 3: Implement regression gate**

Create `benchmark/scorers/regression_gate.py`:

```python
def evaluate_regression_gate(current, baseline, max_accuracy_drop=0.03, max_safety_drop=0.05):
    failures = []

    base_acc = float(baseline.get("accuracy") or 0.0)
    cur_acc = float(current.get("accuracy") or 0.0)
    if base_acc - cur_acc > max_accuracy_drop:
        failures.append(f"accuracy dropped from {base_acc:.3f} to {cur_acc:.3f}")

    base_safety = float(baseline.get("safety_score") or 0.0)
    cur_safety = float(current.get("safety_score") or 0.0)
    if base_safety - cur_safety > max_safety_drop:
        failures.append(f"safety dropped from {base_safety:.3f} to {cur_safety:.3f}")

    return {
        "passed": not failures,
        "failures": failures,
        "current": current,
        "baseline": baseline,
    }
```

- [ ] **Step 4: Run gate tests**

Run:

```powershell
python -m pytest tests/test_benchmark_regression_gate.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit regression gate**

```powershell
git add benchmark/scorers/regression_gate.py tests/test_benchmark_regression_gate.py
git commit -m "feat: add benchmark regression gate"
```

---

### Task 8: Connect BaziQA Metrics to Dashboard

**Files:**

- Modify: `static/benchmark.html`
- Modify: `static/js/benchmark-dashboard.js`

- [ ] **Step 1: Add dashboard placeholders**

In `static/benchmark.html`, under `weak-domains`, add:

```html
<div id="year-breakdown" class="weak-domains"></div>
<div id="domain-breakdown" class="weak-domains"></div>
```

- [ ] **Step 2: Update dashboard element map**

In `static/js/benchmark-dashboard.js`, add:

```javascript
yearBreakdown: document.getElementById('year-breakdown'),
domainBreakdown: document.getElementById('domain-breakdown'),
```

- [ ] **Step 3: Render breakdowns safely**

Add:

```javascript
function renderBreakdown(el, title, buckets) {
    el.textContent = '';
    if (!buckets || Object.keys(buckets).length === 0) return;
    const heading = document.createElement('strong');
    heading.textContent = title;
    el.appendChild(heading);
    for (const key of Object.keys(buckets).sort()) {
        const item = buckets[key] || {};
        const line = document.createElement('div');
        line.textContent = `${key}: ${item.correct || 0}/${item.total || 0} (${pct(item.accuracy)})`;
        el.appendChild(line);
    }
}
```

In `loadReport`, if the report endpoint only returns markdown, do not parse markdown. Instead add a later task for JSON detail. For now, render breakdowns in `renderCards(run)` only if API list includes `by_year_json` and `by_domain_json`.

- [ ] **Step 4: Extend API only if needed**

If dashboard needs detailed run JSON, update `api_server.py` `api_get_benchmark_run` to return saved aggregate JSON fields after Task 9. Keep this task UI-only if the fields are not yet available.

- [ ] **Step 5: Manual verification**

Run the app:

```powershell
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/benchmark
```

Expected:

- Existing metrics still render.
- No JavaScript console errors.
- Runs with breakdown metadata show year/domain summaries.

- [ ] **Step 6: Commit dashboard changes**

```powershell
git add static/benchmark.html static/js/benchmark-dashboard.js
git commit -m "feat: show baziqa benchmark breakdowns"
```

---

### Task 9: Store Aggregate Benchmark Metadata

**Files:**

- Modify: `data_store.py`
- Modify: `tests/test_data_store.py`
- Modify: `api_server.py`

- [ ] **Step 1: Add data store test**

In `tests/test_data_store.py`, add to `TestBenchmarkRuns`:

```python
def test_save_benchmark_run_with_aggregate_json(self):
    saved = data_store.save_benchmark_run(
        id='run-agg-001',
        dataset='baziqa_contest8',
        provider='deepseek',
        model='deepseek-v4-pro',
        method='structured_reasoning',
        n_cases=200,
        n_questions=200,
        accuracy=0.38,
        aggregate_json='{"by_year":{"2025":{"accuracy":0.3}},"by_domain":{"career":{"accuracy":0.5}}}',
    )

    loaded = data_store.get_benchmark_run('run-agg-001')
    assert loaded['aggregate_json']['by_year']['2025']['accuracy'] == 0.3
    assert saved['aggregate_json']['by_domain']['career']['accuracy'] == 0.5
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_data_store.py::TestBenchmarkRuns::test_save_benchmark_run_with_aggregate_json -q
```

Expected:

```text
FAILED
TypeError or KeyError
```

- [ ] **Step 3: Add column migration**

In `data_store.py`, add `aggregate_json` to the `benchmark_runs` table:

```sql
aggregate_json TEXT NOT NULL DEFAULT '{}',
```

Also include it in `_ensure_columns` for existing DBs:

```python
_ensure_columns(conn, 'benchmark_runs', {
    'aggregate_json': "TEXT NOT NULL DEFAULT '{}'",
})
```

- [ ] **Step 4: Update row conversion**

In the benchmark run row conversion function, parse:

```python
d['aggregate_json'] = _json_loads(d.get('aggregate_json'), {})
```

- [ ] **Step 5: Update save function**

Add `aggregate_json='{}'` to `save_benchmark_run(...)` parameters and include it in insert/update values.

- [ ] **Step 6: Pass aggregate JSON from runner**

In `benchmark/runners/run_benchmark.py`, after `choice_result` is computed:

```python
aggregate_json = json.dumps({
    "by_year": choice_result.get("by_year", {}),
    "by_domain": choice_result.get("by_domain", {}),
    "failed_cases": failed_cases,
}, ensure_ascii=False)
```

Pass it to `data_store.save_benchmark_run`.

- [ ] **Step 7: Run data store and API tests**

Run:

```powershell
python -m pytest tests/test_data_store.py tests/test_api.py::TestBenchmarkApi -q
```

Expected:

```text
pass
```

- [ ] **Step 8: Commit aggregate metadata**

```powershell
git add data_store.py benchmark/runners/run_benchmark.py tests/test_data_store.py
git commit -m "feat: store benchmark aggregate metadata"
```

---

### Task 10: Create Operating Guide

**Files:**

- Create: `docs/BAZIQA_UPGRADE.md`

- [ ] **Step 1: Create guide**

Create `docs/BAZIQA_UPGRADE.md`:

```markdown
# BaziQA Upgrade Guide

## Purpose

BaziQA is used as XuanJiZi's objective benchmark for BaZi-specific symbolic and temporal reasoning. It is not a replacement for user-facing consultation quality, but it is the release gate for model and prompt changes.

## Data Sources

- Upstream: https://github.com/ChenJiangxi/BaziQA
- Paper: https://arxiv.org/abs/2602.12889
- Contest8: 2021-2025, 200 four-choice questions
- Celebrity50: 50 public figures, about 250 questions and event timelines

## Splits

- Development: Contest8 2021-2023
- Validation: Contest8 2024
- Locked test: Contest8 2025
- Timeline calibration: Celebrity50

## Commands

Normalize data:

```powershell
python benchmark/runners/import_baziqa_dataset.py --source-dir F:\project\BaziQA\data --output benchmark/datasets/baziqa_contest8_2021_2025.jsonl
```

Offline scoring:

```powershell
python benchmark/runners/run_benchmark.py --dataset benchmark/datasets/baziqa_contest8_2021_2025.jsonl --predictions benchmark/outputs/sample_predictions.json
```

Model scoring:

```powershell
python benchmark/runners/run_benchmark.py --dataset benchmark/datasets/baziqa_contest8_2021_2025.jsonl --model-runner --provider deepseek --model deepseek-v4-pro --method structured_reasoning --prompt-version srp_v2 --max-cases 40
```

## Release Gate

A prompt or model change may ship only when:

- Locked test accuracy does not drop by more than 0.03.
- Safety score does not drop by more than 0.05.
- Health, family, and relationship domains do not regress if they were touched.
- Failed model calls are below 5%.

## Product Use

- Contest8 improves prompt/model selection.
- Celebrity50 improves life-event mapping and timeline calibration.
- Weak domains should become roadmap items for PromptEngine and local rule improvements.
```

- [ ] **Step 2: Commit guide**

```powershell
git add docs/BAZIQA_UPGRADE.md
git commit -m "docs: add baziqa upgrade operating guide"
```

---

### Task 11: Final Verification

**Files:**

- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py -q
```

Expected:

```text
pass
```

- [ ] **Step 2: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
pass
```

If existing E2E tests still fail because local server is not started, record the failure and execute the E2E stabilization plan from `docs/superpowers/plans/2026-06-17-project-optimization-implementation.md` before calling this upgrade complete.

- [ ] **Step 3: Generate one sample benchmark report**

Run:

```powershell
python benchmark/runners/run_benchmark.py --dataset benchmark/datasets/baziqa_mini_v1.jsonl --predictions benchmark/outputs/sample_predictions.json
```

Expected:

```json
{
  "total": 20,
  "correct": 1,
  ...
}
```

- [ ] **Step 4: Run model smoke benchmark with a small cap**

Run only when DeepSeek key and network are available:

```powershell
python benchmark/runners/run_benchmark.py --dataset benchmark/datasets/baziqa_mini_v1.jsonl --model-runner --provider deepseek --model deepseek-v4-pro --method structured_reasoning --prompt-version srp_v2 --max-cases 3
```

Expected:

```text
Benchmark run saved to database
SUMMARY:
```

- [ ] **Step 5: Open dashboard**

Run:

```powershell
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/benchmark
```

Expected:

- Recent benchmark run appears.
- Accuracy, evidence, safety render.
- Report can be opened.
- No browser console errors.

- [ ] **Step 6: Check worktree**

Run:

```powershell
git status --short
```

Expected:

```text
<only intentional source/doc changes>
```

---

## Execution Order

1. Task 1: Fixtures and source documentation.
2. Task 2: Importer.
3. Task 3: Prompt formatter.
4. Task 4: Runner methods.
5. Task 5: Year/domain aggregation.
6. Task 6: Report enhancement.
7. Task 7: Regression gates.
8. Task 9: Aggregate metadata storage.
9. Task 8: Dashboard rendering.
10. Task 10: Operating guide.
11. Task 11: Final verification.

This order keeps each step independently testable and avoids changing the product UI before the benchmark data and scoring are reliable.

---

## Upgrade Impact on XuanJiZi Roadmap

After this plan is complete:

- XuanJiZi can replace subjective prompt evaluation with repeatable BaziQA scores.
- PromptEngine changes can be blocked when they regress locked-year accuracy.
- DeepSeek, Anthropic, and future Qwen/OpenAI adapters can be compared using the same dataset.
- Celebrity50 can feed `life_events` and improve life K-line calibration.
- Weak domains from reports can drive the next local-rule and prompt improvements.

Recommended follow-up plans:

1. `baziqa-celebrity50-timeline-calibration`: import Celebrity50 categories into `life_events` and compare timeline scoring.
2. `model-router-qwen-openai`: add provider adapters beyond DeepSeek/Anthropic.
3. `talent-mindmap-productization`: build the missing talent mindmap from chart visualization data.
4. `knowledge-rag-qa`: turn `/api/kb/search` into a user-facing encyclopedia Q&A.

---

## Self-Review

Spec coverage:

- BaziQA source dataset and paper are represented in Source References and Data Policy.
- Dataset import is covered by Tasks 1-2.
- Prompt protocol is covered by Task 3.
- Runner methods and model comparison are covered by Task 4.
- Year/domain aggregation is covered by Task 5.
- Report/dashboard integration is covered by Tasks 6 and 8.
- Release gates are covered by Task 7.
- Persistent metadata is covered by Task 9.
- Operating documentation is covered by Task 10.

Placeholder scan:

- No placeholder implementation steps remain.
- No step says to write unspecified tests.
- Every code-changing task includes concrete code or exact replacement instructions.

Type and name consistency:

- `case_id`, `source_year`, `domain`, `person`, `question`, `options`, `answer`, `expected_evidence`, and `verified_events` are used consistently.
- Benchmark method names are `direct_choice`, `multi_turn`, and `structured_reasoning`.
- Existing modules are reused: `data_store.py`, `benchmark/runners/run_benchmark.py`, `benchmark/scorers`, and `benchmark/reports/generate_report.py`.
