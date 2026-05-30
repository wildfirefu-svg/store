# Site And BaZi Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current BaZi prototype into a safer, clearer, more credible website by fixing the entry flow, hardening API/report rendering, making deployment reproducible, and upgrading the interpretation pipeline with measurable quality checks.

**Architecture:** Keep the existing FastAPI + vanilla HTML/CSS/JS structure. Add small focused helpers for sanitization, report rendering, and interpretation evidence instead of rewriting the app. Improve the model layer by making each judgment step produce structured evidence, confidence, and counter-evidence.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, vanilla JavaScript, pytest, Playwright, fpdf2, Docker.

---

## Scope And Order

This plan should be executed in five independent phases:

1. Fix high-risk launch blockers.
2. Repair the website entry and core user flow.
3. Make reports safer and more usable.
4. Upgrade BaZi interpretation quality with structured judgment.
5. Tighten tests, docs, and deployment.

Do not refactor unrelated modules. Do not redesign the full app. Every change should trace to one of the tasks below.

## Files To Touch

- `api_server.py`: request validation, safer PDF generation, CORS/auth behavior, structured analysis endpoint.
- `static/app.js`: entry flow, safe rendering, report tabs, chat behavior.
- `static/style.css`: mobile layout, report empty state, compact tool drawer if needed.
- `templates/index.html`: remove false natural-language promise or wire the promise to real behavior.
- `report_to_pdf.py`: Linux font fallback and template validation support.
- `requirements.txt`: add runtime dependencies that are actually imported.
- `Dockerfile`: install CJK fonts and verify PDF runtime.
- `docker-compose.yml`: pass API key settings consistently.
- `tests/test_api.py`: security, PDF validation, auth/CORS, structured analysis endpoint tests.
- `tests/test_frontend_flow.py`: Playwright smoke flow for desktop and mobile.
- `tests/test_tools.py`: convert return-value pseudo-tests into real pytest assertions.
- `quality/model_quality_v2.py`: split scoring into reusable judgment primitives.
- `quality/model_quality_report_v2.json`: regenerated output after quality changes.
- `docs/USER_GUIDE.md`: update actual website flow and limitations.

## Success Criteria

- Full test suite passes without pytest return-value warnings.
- Local Playwright verifies: open site, add命主, show八字, switch紫微, ask for报告, show report tab.
- `/api/analyze/pdf` rejects invalid templates and never shells user input.
- Docker image can start and generate a Chinese PDF.
- Website no longer claims natural-language birth parsing unless that feature works.
- Interpretation reports include conclusion, evidence, counter-evidence, and confidence for key judgments.
- Quality report improves in transparency even if raw score does not immediately rise: weak domains must be labeled as low confidence.

---

### Task 1: Fix PDF Command Injection And Template Validation

**Files:**
- Modify: `api_server.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write tests for invalid PDF templates**

Add these tests to `tests/test_api.py`:

```python
class TestAnalyzePdfSecurity:
    def test_pdf_rejects_invalid_template(self):
        cid = _get_chart_id()
        r = client.post('/api/analyze/pdf', json={
            'chart_id': cid,
            'mode': 1,
            'template': 'dark; echo hacked'
        })
        assert r.status_code == 422

    def test_pdf_accepts_known_template(self):
        cid = _get_chart_id()
        r = client.post('/api/analyze/pdf', json={
            'chart_id': cid,
            'mode': 1,
            'template': 'dark'
        })
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            assert r.headers['content-type'] == 'application/pdf'
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
python -m pytest tests/test_api.py::TestAnalyzePdfSecurity -q
```

Expected: invalid template test fails because `template` is currently an unrestricted string.

- [ ] **Step 3: Restrict template with Pydantic**

In `api_server.py`, import `Literal` and update `AnalyzeRequest`:

```python
from typing import Literal

class AnalyzeRequest(BaseModel):
    chart_id: str
    mode: int = Field(1, ge=1, le=6)
    conclusions: dict = None
    template: Literal["dark", "modern", "scroll", "night"] = "dark"
```

- [ ] **Step 4: Replace `os.system` with `subprocess.run`**

In `analyze_pdf`, replace the shell call with:

```python
import subprocess

cmd = [sys.executable, "report_to_pdf.py", md_tmp, "-o", pdf_tmp, "-t", req.template]
ret = subprocess.run(cmd, capture_output=True, text=True)
if ret.returncode != 0:
    raise HTTPException(500, f"PDF generation failed: {ret.stderr[-500:]}")
```

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest tests/test_api.py::TestAnalyzePdfSecurity -q
python -m pytest tests/test_api.py -q
```

Expected: focused tests pass. Full API tests pass or PDF known-template test returns `500` only if local fonts/dependencies are missing.

- [ ] **Step 6: Commit**

```bash
git add api_server.py tests/test_api.py
git commit -m "fix: harden pdf generation"
```

---

### Task 2: Make Runtime Dependencies And Docker Reproducible

**Files:**
- Modify: `requirements.txt`
- Modify: `Dockerfile`
- Modify: `report_to_pdf.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Add missing dependency**

Update `requirements.txt`:

```text
fastapi>=0.100.0
uvicorn[standard]>=0.20.0
pydantic>=2.0.0
fpdf2>=2.7.0
```

- [ ] **Step 2: Install CJK fonts in Docker**

Update the `apt-get install` block in `Dockerfile`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Add Linux font fallback**

In `report_to_pdf.py`, replace the two font constants with:

```python
FONT_CANDIDATES_HEADER = [
    'C:/Windows/Fonts/simhei.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc',
]
FONT_CANDIDATES_BODY = [
    'C:/Windows/Fonts/simsun.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',
]

def _first_existing(paths):
    return next((p for p in paths if os.path.exists(p)), '')

FONT_HEADER = _first_existing(FONT_CANDIDATES_HEADER)
FONT_BODY = _first_existing(FONT_CANDIDATES_BODY)
```

- [ ] **Step 4: Run local PDF test**

Run:

```bash
python -m pytest tests/test_api.py::TestAnalyzePdfSecurity::test_pdf_accepts_known_template -q
```

Expected: pass with `200` locally after `fpdf2` is installed.

- [ ] **Step 5: Build container**

Run:

```bash
docker build -t bazi-api:test .
```

Expected: image builds without missing `fpdf`.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt Dockerfile report_to_pdf.py tests/test_api.py
git commit -m "fix: make pdf runtime reproducible"
```

---

### Task 3: Fix Website Entry Flow

**Files:**
- Modify: `templates/index.html`
- Modify: `static/app.js`
- Modify: `static/style.css`
- Test: `tests/test_frontend_flow.py`

- [ ] **Step 1: Decide entry behavior**

Use this behavior:

- If no命主 exists and user types birth-like text, open the add命主 modal and prefill only fields that can be parsed safely.
- If parsing is not implemented in this task, remove the natural-language claim and make the visible primary action “添加命主”.
- Keep direct chat blocked until a chart exists.

- [ ] **Step 2: Remove false natural-language promise for first pass**

In `templates/index.html`, change the welcome copy to:

```html
<p><b>欢迎使用玄机子八字分析</b></p>
<p>先添加命主，系统会生成八字与紫微命盘。</p>
<p class="example">示例：公历 1993年7月15日 14:30 男 北京</p>
<p class="welcome-action">点击左侧或下方的添加命主按钮开始。</p>
```

- [ ] **Step 3: Improve no-chart send behavior**

In `static/app.js`, replace the no-current-chart branch:

```javascript
if (!cur) {
    addChatMsg('agent', '请先添加命主。');
    return;
}
```

with:

```javascript
if (!cur) {
    showModal();
    addChatMsg('agent', '请先添加命主并完成排盘，然后再开始分析。');
    return;
}
```

- [ ] **Step 4: Add CSS for welcome action**

In `static/style.css`, add:

```css
.chat-welcome .welcome-action {
    margin-top: 12px;
    color: var(--text-faint);
    font-size: 12px;
}
```

- [ ] **Step 5: Add Playwright smoke test**

Create `tests/test_frontend_flow.py`:

```python
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright


def test_home_add_chart_flow():
    proc = subprocess.Popen(
        [sys.executable, "api_server.py"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            assert "先添加命主" in page.locator("body").inner_text()
            page.click("#add-mingzhu-btn")
            page.fill("#mingzhu-name", "测试命主")
            page.click("#mingzhu-submit-btn")
            page.wait_for_selector(".pillar", timeout=10000)
            body = page.locator("body").inner_text()
            assert "测试命主" in body
            assert "大运流年" in body
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

- [ ] **Step 6: Run smoke test**

Run:

```bash
python -m pytest tests/test_frontend_flow.py -q
```

Expected: one passing test.

- [ ] **Step 7: Commit**

```bash
git add templates/index.html static/app.js static/style.css tests/test_frontend_flow.py
git commit -m "fix: clarify site entry flow"
```

---

### Task 4: Harden Frontend Rendering Against HTML Injection

**Files:**
- Modify: `static/app.js`
- Test: `tests/test_frontend_flow.py`

- [ ] **Step 1: Add malicious content test**

Append to `tests/test_frontend_flow.py`:

```python
def test_markdown_renderer_escapes_script():
    proc = subprocess.Popen(
        [sys.executable, "api_server.py"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            rendered = page.evaluate("renderMarkdown('# 标题\\n\\n<script>window.__xss=1</script>')")
            assert "<script>" not in rendered
            assert "&lt;script&gt;" in rendered
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

- [ ] **Step 2: Escape streamed chat deltas**

In `_sendWithStream`, replace:

```javascript
bubble.innerHTML = replyText.replace(/\n/g, '<br>') + '<span class="streaming-cursor">▌</span>';
```

with:

```javascript
bubble.innerHTML = _escHtml(replyText).replace(/\n/g, '<br>') + '<span class="streaming-cursor">▌</span>';
```

Replace final rendering:

```javascript
bubble.innerHTML = replyText.replace(/\n/g, '<br>') || '分析完成，请查看右侧报告。';
```

with:

```javascript
bubble.innerHTML = replyText ? _escHtml(replyText).replace(/\n/g, '<br>') : '分析完成，请查看右侧报告。';
```

- [ ] **Step 3: Escape tool labels**

Replace sender HTML updates that concatenate `toolName` or `currentTool` with:

```javascript
sender.innerHTML = '玄机子 <span class="tool-tag">' + _escHtml(toolName) + '</span>';
```

and:

```javascript
sender.innerHTML = '玄机子 <span class="tool-tag">' + _escHtml(currentTool) + '</span>';
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/test_frontend_flow.py -q
```

Expected: renderer escapes scripts and chart flow still passes.

- [ ] **Step 5: Commit**

```bash
git add static/app.js tests/test_frontend_flow.py
git commit -m "fix: escape streamed frontend content"
```

---

### Task 5: Improve Mobile Layout And Report Empty State

**Files:**
- Modify: `templates/index.html`
- Modify: `static/style.css`
- Test: `tests/test_frontend_flow.py`

- [ ] **Step 1: Add a useful report empty state**

Replace the report placeholder in `templates/index.html`:

```html
<div class="report-content" id="report-content">
    <div class="report-empty">
        <h2>等待分析</h2>
        <p>添加命主后，可生成四合出、财运、感情、事业、健康等报告。</p>
    </div>
</div>
```

- [ ] **Step 2: Add CSS**

In `static/style.css`, add:

```css
.report-empty {
    max-width: 420px;
    margin: 18vh auto 0;
    color: var(--text-dim);
    text-align: center;
    line-height: 1.8;
}

.report-empty h2 {
    color: var(--gold);
    font-size: 18px;
    margin-bottom: 10px;
}

@media (max-width: 700px) {
    .chat-input-row {
        grid-template-columns: repeat(5, 36px) 1fr 54px;
        gap: 6px;
    }

    #chat-input {
        min-width: 0;
        font-size: 12px;
    }

    #chat-send-btn {
        min-width: 48px;
        padding: 0 10px;
    }
}
```

- [ ] **Step 3: Add mobile smoke assertion**

Add to `tests/test_frontend_flow.py`:

```python
def test_mobile_initial_layout_has_no_horizontal_overflow():
    proc = subprocess.Popen(
        [sys.executable, "api_server.py"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
            page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            assert overflow is False
            assert page.locator("#chat-send-btn").is_visible()
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

- [ ] **Step 4: Run frontend tests**

Run:

```bash
python -m pytest tests/test_frontend_flow.py -q
```

Expected: all frontend flow tests pass.

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/style.css tests/test_frontend_flow.py
git commit -m "fix: improve empty and mobile states"
```

---

### Task 6: Convert Tool Tests Into Real Pytest Assertions

**Files:**
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Replace `return`-based tests**

For each `test_zeri`, `test_liunian`, `test_name_analysis`, and `test_case_retrieval`, replace final return statements like:

```python
return PASSED, TOTAL, FAILED
```

with:

```python
assert not FAILED, f"Failed checks: {FAILED}"
assert PASSED == TOTAL
```

- [ ] **Step 2: Run warning-producing tests**

Run:

```bash
python -m pytest tests/test_tools.py -q
```

Expected: pass with no `PytestReturnNotNoneWarning`.

- [ ] **Step 3: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests pass without pytest return-value warnings.

- [ ] **Step 4: Commit**

```bash
git add tests/test_tools.py
git commit -m "test: make tool tests assert failures"
```

---

### Task 7: Add Structured Judgment Objects For BaZi Analysis

**Files:**
- Modify: `api_server.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Define structured judgment output**

Add this helper near `_auto_analyze`:

```python
def _judgment(name, conclusion, confidence, evidence, counter_evidence=None):
    return {
        "name": name,
        "conclusion": conclusion,
        "confidence": confidence,
        "evidence": evidence,
        "counter_evidence": counter_evidence or [],
    }
```

- [ ] **Step 2: Add judgments to `_auto_analyze` return**

Before returning from `_auto_analyze`, build:

```python
judgments = [
    _judgment(
        "旺衰",
        grade,
        "medium" if grade == "中和" else "high",
        [
            f"日主五行占比{dm_pct * 100:.0f}%",
            f"月令{month_zhi}({month_wu})对日主为{month_support}",
        ],
        [
            "当前算法未完整计算透干、根气远近和合化后的强弱变化"
        ],
    ),
    _judgment(
        "格局",
        pattern_name,
        "medium",
        [
            f"月干{month_gan}对日主为{shishen_of_month}",
            f"月令本气{month_main}",
        ],
        [
            "当前仅按月干/月令粗判，未完整处理变格、从格、合化和格局破救"
        ],
    ),
    _judgment(
        "用神",
        yongshen["assessment"],
        "low" if grade == "中和" else "medium",
        [
            f"日主{grade}",
            f"初步取{yong[0]}为用",
        ],
        [
            "当前用神未完全区分格局用神、调候用神、通关用神和病药用神"
        ],
    ),
]
```

Then include it in the return:

```python
"judgments": judgments,
```

- [ ] **Step 3: Add API test**

Add to `tests/test_api.py`:

```python
class TestAnalyzeStructuredJudgments:
    def test_auto_analyze_contains_judgment_evidence(self):
        cid = _get_chart_id()
        chart = api.chart_cache._cache[cid]
        result = api._auto_analyze(chart)
        assert "judgments" in result
        assert len(result["judgments"]) >= 3
        for item in result["judgments"]:
            assert item["name"]
            assert item["conclusion"]
            assert item["confidence"] in ("low", "medium", "high")
            assert isinstance(item["evidence"], list)
            assert isinstance(item["counter_evidence"], list)
```

- [ ] **Step 4: Run test**

Run:

```bash
python -m pytest tests/test_api.py::TestAnalyzeStructuredJudgments -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add api_server.py tests/test_api.py
git commit -m "feat: add structured bazi judgments"
```

---

### Task 8: Surface Judgment Evidence In Reports

**Files:**
- Modify: `report_builder.py`
- Test: create or modify `tests/test_report_builder.py`

- [ ] **Step 1: Add report builder test**

Create `tests/test_report_builder.py`:

```python
import report_builder as rb


def test_render_judgments_table():
    judgments = [
        {
            "name": "旺衰",
            "conclusion": "身强",
            "confidence": "high",
            "evidence": ["日主占比40%", "月令得生"],
            "counter_evidence": ["未计算合化"],
        }
    ]
    md = rb.render_judgments(judgments)
    assert "| 判断 | 结论 | 置信度 | 依据 | 反证/限制 |" in md
    assert "旺衰" in md
    assert "未计算合化" in md
```

- [ ] **Step 2: Implement renderer**

Add to `report_builder.py`:

```python
def render_judgments(judgments):
    if not judgments:
        return ""
    lines = [
        "## 判断依据与置信度",
        "",
        "| 判断 | 结论 | 置信度 | 依据 | 反证/限制 |",
        "|---|---|---|---|---|",
    ]
    for item in judgments:
        evidence = "<br>".join(item.get("evidence", []))
        counter = "<br>".join(item.get("counter_evidence", []))
        lines.append(
            f"| {item.get('name', '')} | {item.get('conclusion', '')} | "
            f"{item.get('confidence', '')} | {evidence} | {counter} |"
        )
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 3: Insert into mode reports**

In each `build_mode*_report` function, insert after chart/table basics:

```python
sections.append(render_judgments(conclusions.get("judgments", [])))
```

Use the local variable name already used by each function. If the function concatenates strings rather than a `sections` list, insert:

```python
report += "\n" + render_judgments(conclusions.get("judgments", [])) + "\n"
```

- [ ] **Step 4: Run report tests**

Run:

```bash
python -m pytest tests/test_report_builder.py -q
python -m pytest tests/test_api.py::TestAnalyzeStructuredJudgments -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add report_builder.py tests/test_report_builder.py
git commit -m "feat: show bazi judgment evidence"
```

---

### Task 9: Upgrade Quality Scoring To Penalize Unsupported Claims

**Files:**
- Modify: `quality/model_quality_v2.py`
- Test: create `tests/test_quality_scoring.py`

- [ ] **Step 1: Add unit tests for confidence policy**

Create `tests/test_quality_scoring.py`:

```python
from quality.model_quality_v2 import confidence_from_score


def test_confidence_from_score():
    assert confidence_from_score(1.2) == "high"
    assert confidence_from_score(0.6) == "medium"
    assert confidence_from_score(0.2) == "low"
```

- [ ] **Step 2: Add confidence helper**

In `quality/model_quality_v2.py`, add:

```python
def confidence_from_score(score):
    if score >= 1.0:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"
```

- [ ] **Step 3: Include confidence in event scores**

In `analyze_case_v2`, when appending each event score, add:

```python
"confidence": confidence_from_score(score),
```

- [ ] **Step 4: Regenerate quality report**

Run:

```bash
python quality/model_quality_v2.py
```

Expected: `quality/model_quality_report_v2.json` is regenerated and event details include confidence.

- [ ] **Step 5: Run quality tests**

Run:

```bash
python -m pytest tests/test_quality_scoring.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add quality/model_quality_v2.py quality/model_quality_report_v2.json tests/test_quality_scoring.py
git commit -m "feat: add confidence to quality scoring"
```

---

### Task 10: Improve BaZi Judgment Rules By Domain

**Files:**
- Modify: `quality/model_quality_v2.py`
- Modify: `api_server.py`
- Test: `tests/test_quality_scoring.py`

- [ ] **Step 1: Add domain confidence floor rules**

In `quality/model_quality_v2.py`, add:

```python
LOW_CONFIDENCE_DOMAINS_WITHOUT_TIME = {"health", "family", "relationship"}


def domain_confidence_cap(category, has_precise_hour):
    if category in LOW_CONFIDENCE_DOMAINS_WITHOUT_TIME and not has_precise_hour:
        return "low"
    return "high"
```

- [ ] **Step 2: Add tests**

Append:

```python
from quality.model_quality_v2 import domain_confidence_cap


def test_domain_confidence_cap_without_precise_hour():
    assert domain_confidence_cap("health", False) == "low"
    assert domain_confidence_cap("family", False) == "low"
    assert domain_confidence_cap("career", False) == "high"
```

- [ ] **Step 3: Apply cap in event scoring**

In `analyze_case_v2`, derive:

```python
has_precise_hour = "T" in case["birth"]["datetime"] and len(case["birth"]["datetime"].split("T")[-1]) >= 5
```

When appending event score:

```python
raw_confidence = confidence_from_score(score)
cap = domain_confidence_cap(evt["category"], has_precise_hour)
confidence = "low" if cap == "low" else raw_confidence
```

Then store:

```python
"confidence": confidence,
```

- [ ] **Step 4: Mirror limitation in `_auto_analyze`**

In `api_server.py`, if the birth hour is defaulted or missing, set health/family judgments to low confidence in generated reports. Use:

```python
birth = chart.get("birth_info", {})
hour_known = birth.get("hour") is not None
```

For health/family text, include:

```python
"涉及健康、六亲、子女、晚运的判断高度依赖准确时辰；时辰不准时仅作低置信参考。"
```

- [ ] **Step 5: Run tests and regenerate report**

Run:

```bash
python -m pytest tests/test_quality_scoring.py -q
python quality/model_quality_v2.py
```

Expected: tests pass; quality report includes capped confidence where applicable.

- [ ] **Step 6: Commit**

```bash
git add api_server.py quality/model_quality_v2.py quality/model_quality_report_v2.json tests/test_quality_scoring.py
git commit -m "feat: cap weak-domain confidence without precise hour"
```

---

### Task 11: Add API And Frontend Auth/CORS Launch Policy

**Files:**
- Modify: `api_server.py`
- Modify: `docker-compose.yml`
- Test: `tests/test_api.py`

- [ ] **Step 1: Restrict CORS by environment**

In `api_server.py`, replace wildcard CORS with:

```python
def _cors_origins():
    raw = os.environ.get("BAZI_CORS_ORIGINS", "")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return ["http://127.0.0.1:8000", "http://localhost:8000"]

app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_methods=["*"], allow_headers=["*"])
```

- [ ] **Step 2: Remove unused `_PROTECTED_PATHS` or enforce it**

Current middleware requires auth for all non-public paths when key is set. Delete `_PROTECTED_PATHS` if unused to avoid misleading future readers.

- [ ] **Step 3: Add compose env**

In `docker-compose.yml`:

```yaml
environment:
  - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
  - BAZI_API_KEY=${BAZI_API_KEY:-}
  - BAZI_CORS_ORIGINS=${BAZI_CORS_ORIGINS:-http://localhost:8000,http://127.0.0.1:8000}
```

- [ ] **Step 4: Add CORS test**

Add to `tests/test_api.py`:

```python
class TestCorsPolicy:
    def test_cors_origins_are_not_wildcard_by_default(self):
        assert "*" not in api._cors_origins()
```

- [ ] **Step 5: Run API tests**

Run:

```bash
python -m pytest tests/test_api.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add api_server.py docker-compose.yml tests/test_api.py
git commit -m "fix: restrict default cors policy"
```

---

### Task 12: Update User Guide And Limitations

**Files:**
- Modify: `docs/USER_GUIDE.md`

- [ ] **Step 1: Update website flow**

Replace the “自然语言输入” usage section with:

```markdown
### Web 使用流程

1. 点击“添加命主”。
2. 输入公历或农历生日、时间、性别、出生地。
3. 点击“排盘”，系统生成八字与紫微盘。
4. 在对话框输入“报告”或具体问题。
5. 右侧报告区会显示分析结果，可切换财运、感情、事业、健康等标签。
```

- [ ] **Step 2: Add confidence limitation**

Add:

```markdown
### 置信度说明

系统会区分排盘确定性和解释置信度。四柱排盘属于规则计算；事业、财运、婚恋、健康、家庭等解释属于传统命理推断。健康、家庭、子女、晚运类判断对时辰高度敏感，如果出生时间不确定，报告会降低置信度。
```

- [ ] **Step 3: Add data safety note**

Add:

```markdown
### 数据安全

浏览器端会在当前会话中缓存命主信息，刷新后可继续使用；关闭浏览器会话后缓存可能消失。公开部署时建议开启 `BAZI_API_KEY`，并避免在多人共享环境输入真实敏感身份信息。
```

- [ ] **Step 4: Commit**

```bash
git add docs/USER_GUIDE.md
git commit -m "docs: update web flow and confidence notes"
```

---

## Final Verification

- [ ] Run all tests:

```bash
python -m pytest -q
```

Expected: all tests pass with no pytest return-value warnings.

- [ ] Run local website smoke check:

```bash
python api_server.py
```

Open `http://127.0.0.1:8000/`, add a sample命主, switch八字/紫微, generate a report, download PDF.

- [ ] Run Docker build:

```bash
docker build -t bazi-api:test .
```

Expected: build succeeds.

- [ ] Optional Docker runtime check:

```bash
docker run --rm -p 8000:8000 bazi-api:test
```

Open `http://127.0.0.1:8000/api/health`.

---

## Execution Notes

Recommended execution order:

1. Task 1
2. Task 2
3. Task 6
4. Task 3
5. Task 4
6. Task 5
7. Task 7
8. Task 8
9. Task 9
10. Task 10
11. Task 11
12. Task 12

Tasks 1, 2, 4, 6, and 11 are launch blockers. Tasks 7 through 10 improve the命理判断 quality and can be shipped behind the current UI if needed.

## Self-Review

- Spec coverage: covers website entry, security, deployment, report rendering, interpretation quality, tests, and docs.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: `confidence` uses `"low" | "medium" | "high"` consistently; `judgments` uses `name`, `conclusion`, `confidence`, `evidence`, `counter_evidence`.
