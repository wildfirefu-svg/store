# Xuanjizi Report Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the June 18 manual website test findings into automated safeguards so Xuanjizi reports are structurally complete, less prone to obvious BaZi factual errors, and stable in local/offline browser environments.

**Architecture:** Add a deterministic report validation layer that checks LLM report text against the calculated chart before saving or presenting final output. Keep the validator small and rule-based, then strengthen frontend E2E assertions and local asset loading so browser tests catch the exact failures found in manual testing.

**Tech Stack:** Python 3, FastAPI, pytest, Playwright, vanilla ES modules, PowerShell verification scripts, local static assets under `static/`.

---

## Evidence From Current Audit

Manual verification on 2026-06-18 used:

- Local URL: `http://127.0.0.1:8767`
- Test person: `质量测试命主`, female, `1990-05-12 08:30`, Beijing
- Generated report text: `.tmp/manual-ui-fresh-report-text.txt`
- Screenshot: `.tmp/manual-ui-fresh-ai-report.png`
- Check JSON: `.tmp/manual-ui-fresh-check.json`

Observed pass signals:

- Chart creation succeeded.
- Auto overview rendered.
- Real DeepSeek report completed with status `可信推理完成`.
- Report included BaZi, basis text, disclaimer, current luck, future-year discussion, advice, and 7 DOM tables.

Observed gaps:

- The report contained BaZi factual errors: `巳午未会火局` even though the chart has no `未`, and `丑为火库` even though fire storage is `戌`.
- The frontend E2E overview test only rejects `等待输入`; it would miss the placeholder `输入出生信息后，报告将在此显示`.
- `templates/index.html` depends on Google Fonts and jsDelivr ECharts, which produced `net::ERR_NETWORK_ACCESS_DENIED` in the browser run.
- `static/app.js` reads `window._forceDeepReport` before `_expandPrompt(text)` sets it, so `深度报告` can fail to use the intended `deep_report` tab.
- Saved/displayed AI reports start with conversational preface text such as `好的，我将...`, which is not suitable for a formal customer report.

## File Structure

- Create `bazi_report_validator.py`
  - Deterministic text checks for branch-combination claims, storage-branch claims, month-order wealth claims, and conversational preface cleanup.
- Create `tests/test_bazi_report_validator.py`
  - Unit tests for every rule using the same 1990-05-12 chart shape found in manual testing.
- Modify `api_server.py:1504-1607`
  - Clean final report text, run validation, append a visible validation note when hard errors are detected, save validator metadata with model output.
- Modify `tests/test_api.py`
  - Add API-level regression tests that simulate bad AI output and assert the final SSE/report contains validation warnings.
- Modify `static/app.js:94-139`
  - Fix `deep_report` routing by reading `_forceDeepReport` after `_expandPrompt(text)`.
- Modify `tests/test_e2e.py:134-138`
  - Make auto-overview assertions require `命盘总览`, `日主`, `可信度说明`, and reject both placeholder strings.
- Create `tests/test_frontend_assets.py`
  - Assert the main HTML no longer relies on external Google Fonts or external ECharts at runtime.
- Modify `templates/index.html:7-174`
  - Replace CDN font/script dependencies with local CSS and local ECharts script.
- Create `static/vendor/echarts.min.js`
  - Local ECharts bundle used by charts.
- Create `static/css/fonts.css`
  - Local font stack or local font-face declarations.
- Create `scripts/verify_ui_report_quality.ps1`
  - Repeat the clean-database website flow and fail on known bad claims, missing report sections, missing tables, or connection errors.

## Task 1: Deterministic Report Validator

**Files:**
- Create: `bazi_report_validator.py`
- Create: `tests/test_bazi_report_validator.py`

- [ ] **Step 1: Write failing tests for the exact bad claims found in manual testing**

Create `tests/test_bazi_report_validator.py`:

```python
import pytest

from bazi_report_validator import (
    strip_report_preface,
    validate_report_claims,
)


CHART_1990_05_12_FEMALE = {
    "four_pillars": {
        "year": {"gan": "庚", "zhi": "午"},
        "month": {"gan": "辛", "zhi": "巳"},
        "day": {"gan": "丁", "zhi": "丑"},
        "hour": {"gan": "甲", "zhi": "辰"},
    },
    "day_master": {"gan": "丁", "wuxing": "火", "yinyang": "阴"},
    "birth_info": {
        "year": 1990,
        "month": 5,
        "day": 12,
        "hour": 8,
        "minute": 30,
        "gender": "female",
        "location": "北京",
    },
}


def issue_codes(issues):
    return {issue["code"] for issue in issues}


def test_flags_three_meeting_claim_when_required_branch_is_missing():
    report = "丁火生于巳月，地支巳午未会火局，火势极旺。"
    issues = validate_report_claims(CHART_1990_05_12_FEMALE, report)

    assert "missing_branch_for_combo" in issue_codes(issues)
    assert any("未" in issue["message"] for issue in issues)


def test_accepts_three_meeting_claim_when_all_branches_exist():
    chart = {
        **CHART_1990_05_12_FEMALE,
        "four_pillars": {
            "year": {"gan": "庚", "zhi": "午"},
            "month": {"gan": "辛", "zhi": "巳"},
            "day": {"gan": "丁", "zhi": "未"},
            "hour": {"gan": "甲", "zhi": "辰"},
        },
    }
    report = "地支巳午未会火局，火势成方。"
    issues = validate_report_claims(chart, report)

    assert "missing_branch_for_combo" not in issue_codes(issues)


def test_flags_wrong_storage_branch_claim():
    report = "日支丑为火库，能收丁火余气。"
    issues = validate_report_claims(CHART_1990_05_12_FEMALE, report)

    assert "wrong_storage_branch" in issue_codes(issues)
    assert any("火库为戌" in issue["message"] for issue in issues)


def test_flags_month_order_wealth_claim_when_month_branch_main_qi_is_not_wealth():
    report = "月令财星当令，偏财格根气极旺。"
    issues = validate_report_claims(CHART_1990_05_12_FEMALE, report)

    assert "unsupported_month_wealth_order" in issue_codes(issues)
    assert any("巳月本气为丙火" in issue["message"] for issue in issues)


def test_strip_report_preface_removes_conversational_opening():
    raw = "好的，我将遵循结构化推理协议，为您进行四合出综合分析。\n\n***\n\n一、八字排盘\n正文"

    assert strip_report_preface(raw).startswith("一、八字排盘")


def test_strip_report_preface_preserves_report_that_already_starts_with_title():
    raw = "一、八字排盘\n正文"

    assert strip_report_preface(raw) == raw
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
python -m pytest tests/test_bazi_report_validator.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'bazi_report_validator'
```

- [ ] **Step 3: Implement the validator**

Create `bazi_report_validator.py`:

```python
"""Rule-based validation for AI-generated BaZi report text."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List


GAN_WUXING = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

ZHI_MAIN_GAN = {
    "子": "癸",
    "丑": "己",
    "寅": "甲",
    "卯": "乙",
    "辰": "戊",
    "巳": "丙",
    "午": "丁",
    "未": "己",
    "申": "庚",
    "酉": "辛",
    "戌": "戊",
    "亥": "壬",
}

CONTROLS = {
    "木": "土",
    "火": "金",
    "土": "水",
    "金": "木",
    "水": "火",
}

BRANCH_COMBOS = {
    "寅卯辰": "东方木三会",
    "巳午未": "南方火三会",
    "申酉戌": "西方金三会",
    "亥子丑": "北方水三会",
    "申子辰": "水三合",
    "亥卯未": "木三合",
    "寅午戌": "火三合",
    "巳酉丑": "金三合",
}

STORAGE_BRANCH_BY_ELEMENT = {
    "木": "未",
    "火": "戌",
    "金": "丑",
    "水": "辰",
}


def _chart_branches(chart: Dict) -> set[str]:
    pillars = chart.get("four_pillars") or {}
    return {
        str(pillar.get("zhi"))
        for pillar in pillars.values()
        if isinstance(pillar, dict) and pillar.get("zhi")
    }


def _month_branch(chart: Dict) -> str:
    month = (chart.get("four_pillars") or {}).get("month") or {}
    return str(month.get("zhi") or "")


def _day_master_element(chart: Dict) -> str:
    dm = chart.get("day_master") or {}
    if isinstance(dm, dict):
        if dm.get("wuxing"):
            return str(dm["wuxing"])
        gan = str(dm.get("gan") or "")
    else:
        gan = str(dm or "")
    return GAN_WUXING.get(gan, "")


def _issue(code: str, severity: str, message: str, evidence: str) -> Dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "evidence": evidence,
    }


def _validate_branch_combos(chart: Dict, text: str) -> Iterable[Dict[str, str]]:
    branches = _chart_branches(chart)
    for combo, label in BRANCH_COMBOS.items():
        if combo not in text:
            continue
        missing = [zhi for zhi in combo if zhi not in branches]
        if missing:
            yield _issue(
                "missing_branch_for_combo",
                "error",
                f"报告提到{combo}{label}，但命盘地支缺少{'、'.join(missing)}。",
                combo,
            )


def _validate_storage_claims(text: str) -> Iterable[Dict[str, str]]:
    for branch, element in re.findall(r"([子丑寅卯辰巳午未申酉戌亥])(?:土)?为([木火金水])库", text):
        expected = STORAGE_BRANCH_BY_ELEMENT[element]
        if branch != expected:
            yield _issue(
                "wrong_storage_branch",
                "error",
                f"{element}库为{expected}，不是{branch}。",
                f"{branch}为{element}库",
            )


def _validate_month_wealth_order(chart: Dict, text: str) -> Iterable[Dict[str, str]]:
    if not any(phrase in text for phrase in ("财星当令", "月令财星", "财星得令")):
        return
    month_zhi = _month_branch(chart)
    day_element = _day_master_element(chart)
    wealth_element = CONTROLS.get(day_element, "")
    main_gan = ZHI_MAIN_GAN.get(month_zhi, "")
    main_element = GAN_WUXING.get(main_gan, "")
    if month_zhi and wealth_element and main_element != wealth_element:
        yield _issue(
            "unsupported_month_wealth_order",
            "warning",
            f"{month_zhi}月本气为{main_gan}{main_element}，日主{day_element}的财星为{wealth_element}，不能直接写财星当令。",
            "财星当令",
        )


def validate_report_claims(chart: Dict, report_text: str) -> List[Dict[str, str]]:
    """Return deterministic issues where report text conflicts with chart facts."""
    text = str(report_text or "")
    issues: List[Dict[str, str]] = []
    issues.extend(_validate_branch_combos(chart, text))
    issues.extend(_validate_storage_claims(text))
    issues.extend(_validate_month_wealth_order(chart, text))
    return issues


def strip_report_preface(report_text: str) -> str:
    """Remove model preface before the first formal report section."""
    text = str(report_text or "").strip()
    if not text:
        return ""
    patterns = [
        r"(?:\*\*\*\s*)?(一、八字排盘.*)",
        r"(?:\*\*\*\s*)?(#\s*八字排盘.*)",
        r"(?:\*\*\*\s*)?(##\s*一[、.．]\s*八字排盘.*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.S)
        if match:
            return match.group(1).strip()
    return text


def format_validation_note(issues: List[Dict[str, str]]) -> str:
    if not issues:
        return ""
    lines = ["## 系统校验提示", ""]
    for issue in issues:
        label = "错误" if issue["severity"] == "error" else "提醒"
        lines.append(f"- **{label}**：{issue['message']}")
    lines.append("")
    lines.append("> 上述提示由命盘规则校验生成，需优先复核原报告对应段落。")
    return "\n".join(lines).strip()
```

- [ ] **Step 4: Run validator tests and confirm they pass**

Run:

```powershell
python -m pytest tests/test_bazi_report_validator.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit Task 1**

```powershell
git add bazi_report_validator.py tests/test_bazi_report_validator.py
git commit -m "feat: add deterministic bazi report validator"
```

## Task 2: Integrate Validator Into AI Report Flow

**Files:**
- Modify: `api_server.py:1-40`
- Modify: `api_server.py:1504-1607`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add failing API regression test for validator warnings**

Append this test to `tests/test_api.py` near `TestChatStreamModelOutputs`:

```python
def test_chat_stream_appends_bazi_validation_warning(monkeypatch):
    cid = _get_chart_id("female")

    def fake_stream(chart, message, system_prompt=None):
        yield {
            "type": "text_delta",
            "text": "好的，我将分析。\n\n***\n\n一、八字排盘\n地支巳午未会火局，日支丑为火库。",
        }
        yield {"type": "message_delta", "stop_reason": "end_turn"}

    monkeypatch.setattr(api, "_stream_claude", fake_stream)

    r = client.get(
        "/api/chat/stream",
        params={"chart_id": cid, "message": "报告", "reasoning_mode": "trusted"},
    )

    assert r.status_code == 200
    assert "系统校验提示" in r.text
    assert "火库为戌" in r.text
    assert "好的，我将" not in r.text
```

- [ ] **Step 2: Run the new test and confirm it fails**

Run:

```powershell
python -m pytest tests/test_api.py::test_chat_stream_appends_bazi_validation_warning -q
```

Expected:

```text
FAILED ... assert '系统校验提示' in ...
```

- [ ] **Step 3: Import validator helpers**

Modify the imports near the top of `api_server.py`:

```python
from bazi_report_validator import (
    format_validation_note,
    strip_report_preface,
    validate_report_claims,
)
```

- [ ] **Step 4: Finalize report text before saving and done event**

Inside `event_stream()` in `api_server.py`, replace the block after the streaming loop and before `analysis_id = None` with this structure:

```python
        final_text = strip_report_preface(report_text or reply_text)
        validation_issues = validate_report_claims(chart, final_text)
        validation_note = format_validation_note(validation_issues)
        if validation_note:
            final_text = final_text + "\n\n" + validation_note
        if report_text:
            report_text = final_text
            reply_text = final_text
            yield _sse_event('report', {'text': report_text, 'tab': report_tab})
        else:
            reply_text = final_text
```

Then in the existing `data_store.save_model_output(...)` call, replace `structured_reasoning_json={...}` with:

```python
                    structured_reasoning_json={
                        'local_analysis': conclusions,
                        'confidence': None,
                        'reasoning_mode': reasoning_mode,
                        'memory_mode': memory_mode,
                        'conversation_summary_id': conversation_summary_id,
                        'validation_issues': validation_issues,
                    },
```

Keep `raw_output=report_text or reply_text`; after this change it will contain cleaned final text.

- [ ] **Step 5: Run API tests for chat stream**

Run:

```powershell
python -m pytest tests/test_api.py::TestChatStreamModelOutputs tests/test_api.py::test_chat_stream_appends_bazi_validation_warning -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit Task 2**

```powershell
git add api_server.py tests/test_api.py
git commit -m "feat: validate and clean ai report output"
```

## Task 3: Fix Frontend Report Routing And E2E Coverage

**Files:**
- Modify: `static/app.js:126-140`
- Modify: `tests/test_e2e.py:134-153`

- [ ] **Step 1: Strengthen the auto-overview E2E assertion**

Replace `test_auto_overview_generated` in `tests/test_e2e.py` with:

```python
    def test_auto_overview_generated(self, page):
        create_chart(page, "总览测试")
        report = page.locator("#report-content").text_content() or ""
        assert "等待输入" not in report, "总览报告不应该显示等待输入"
        assert "输入出生信息后，报告将在此显示" not in report, "总览报告不应该停留在占位文案"
        assert "命盘总览" in report, "总览报告应该包含标题"
        assert "日主" in report, "总览报告应该包含日主信息"
        assert "可信度说明" in report, "总览报告应该包含可信度说明"
```

- [ ] **Step 2: Add E2E coverage for deep report tab routing**

Add this test under `class TestChat` in `tests/test_e2e.py`:

```python
    def test_deep_report_routes_to_deep_report_tab(self, page):
        page.unroute("**/api/chat/stream**")
        page.route(
            "**/api/chat/stream**",
            lambda route: route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream; charset=utf-8"},
                body=(
                    'event: report\n'
                    'data: {"text":"# 深度报告\\n## 一、八字排盘\\n正文","tab":"deep_report"}\n\n'
                    'event: done\n'
                    'data: {"corrections":0}\n\n'
                ),
            ),
        )
        create_chart(page, "深度报告测试")
        page.fill("#chat-input", "深度报告")
        page.click("#chat-send-btn")
        page.wait_for_function(
            "() => (document.getElementById('report-status')?.textContent || '').includes('完成')",
            timeout=10000,
        )

        tabs = page.locator("#report-tabs").text_content() or ""
        report = page.locator("#report-content").text_content() or ""
        assert "深度报告" in tabs
        assert "深度报告" in report
```

- [ ] **Step 3: Run the frontend tests and confirm the deep report test fails before app fix**

Run:

```powershell
python -m pytest tests/test_e2e.py::TestChartCreation::test_auto_overview_generated tests/test_e2e.py::TestChat::test_deep_report_routes_to_deep_report_tab -q -s --tb=short
```

Expected before code fix:

```text
FAILED ... assert '深度报告' in tabs
```

- [ ] **Step 4: Fix `static/app.js` deep report routing**

Replace this block in the chat-send click handler:

```javascript
    var isDeep = window._forceDeepReport || false;
    window._forceDeepReport = false;
    const prompt = _expandPrompt(text);
    addChatMsg('user', text);
    inp.value = ''; inp.style.height = 'auto';
    _sendWithStream(cur.chart_id, prompt, null, isDeep ? 'deep_report' : null);
```

with:

```javascript
    const prompt = _expandPrompt(text);
    var isDeep = window._forceDeepReport || false;
    window._forceDeepReport = false;
    addChatMsg('user', text);
    inp.value = ''; inp.style.height = 'auto';
    _sendWithStream(cur.chart_id, prompt, null, isDeep ? 'deep_report' : null);
```

- [ ] **Step 5: Run the targeted E2E tests**

Run:

```powershell
python -m pytest tests/test_e2e.py::TestChartCreation::test_auto_overview_generated tests/test_e2e.py::TestChat::test_deep_report_routes_to_deep_report_tab -q -s --tb=short
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit Task 3**

```powershell
git add static/app.js tests/test_e2e.py
git commit -m "fix: strengthen overview and deep report e2e coverage"
```

## Task 4: Remove Runtime Dependence On External Frontend Assets

**Files:**
- Modify: `templates/index.html:7-174`
- Create: `static/vendor/echarts.min.js`
- Create: `static/css/fonts.css`
- Create: `tests/test_frontend_assets.py`

- [ ] **Step 1: Add failing asset regression tests**

Create `tests/test_frontend_assets.py`:

```python
from pathlib import Path


INDEX = Path("templates/index.html")


def test_index_does_not_depend_on_external_font_or_chart_cdn():
    html = INDEX.read_text(encoding="utf-8")

    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert "cdn.jsdelivr.net" not in html
    assert "/static/vendor/echarts.min.js" in html
    assert "/static/css/fonts.css" in html


def test_local_echarts_bundle_exists_and_looks_like_echarts():
    path = Path("static/vendor/echarts.min.js")

    assert path.exists()
    text = path.read_text(encoding="utf-8", errors="ignore")
    assert "echarts" in text[:5000].lower()
    assert path.stat().st_size > 100_000
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
python -m pytest tests/test_frontend_assets.py -q
```

Expected:

```text
FAILED ... fonts.googleapis.com
FAILED ... static/vendor/echarts.min.js
```

- [ ] **Step 3: Create local asset directories**

Run:

```powershell
New-Item -ItemType Directory -Force static\vendor | Out-Null
```

- [ ] **Step 4: Vendor ECharts locally**

Run one of these commands.

Preferred when internet is available:

```powershell
Invoke-WebRequest -UseBasicParsing https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js -OutFile static\vendor\echarts.min.js
```

Fallback when `node_modules/echarts` already exists:

```powershell
Copy-Item node_modules\echarts\dist\echarts.min.js static\vendor\echarts.min.js
```

After the copy, verify:

```powershell
python -c "from pathlib import Path; p=Path('static/vendor/echarts.min.js'); print(p.exists(), p.stat().st_size)"
```

Expected:

```text
True <a number greater than 100000>
```

- [ ] **Step 5: Add local font CSS**

Create `static/css/fonts.css`:

```css
:root {
    --font-sans: "Noto Sans TC", "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif;
    --font-serif: "Noto Serif TC", "Songti SC", "SimSun", serif;
}

body {
    font-family: var(--font-sans);
}
```

- [ ] **Step 6: Update `templates/index.html`**

Replace:

```html
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&family=Noto+Serif+TC:wght@400;500;600;700&display=swap" rel="stylesheet">
```

with:

```html
    <link rel="stylesheet" href="/static/css/fonts.css?v=20260618a">
```

Replace:

```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
```

with:

```html
<script src="/static/vendor/echarts.min.js?v=5"></script>
```

- [ ] **Step 7: Run asset tests**

Run:

```powershell
python -m pytest tests/test_frontend_assets.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 8: Commit Task 4**

```powershell
git add templates/index.html static/css/fonts.css static/vendor/echarts.min.js tests/test_frontend_assets.py
git commit -m "fix: serve frontend chart assets locally"
```

## Task 5: Add Repeatable UI Report Quality Verification

**Files:**
- Create: `scripts/verify_ui_report_quality.ps1`
- Create: `scripts/run_ui_report_quality.py`
- Modify: `docs/BAZIQA_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Create the Python browser verifier**

Create `scripts/run_ui_report_quality.py`:

```python
#!/usr/bin/env python3
"""Run a clean-browser Xuanjizi report quality check against a local URL."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BAD_PATTERNS = [
    "巳午未会火局",
    "丑为火库",
    "月令财星当令",
]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out-dir", default=".tmp/ui-report-quality")
    parser.add_argument("--timeout-ms", type=int, default=240000)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"base_url": args.base_url, "errors": [], "signals": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.on("pageerror", lambda err: result["errors"].append(f"pageerror: {err}"))
        page.on("requestfailed", lambda req: result["errors"].append(f"requestfailed: {req.url} {req.failure}"))

        page.goto(args.base_url, wait_until="domcontentloaded", timeout=30000)
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        page.reload(wait_until="domcontentloaded", timeout=30000)
        page.click("#add-mingzhu-btn")
        page.wait_for_selector("#add-mingzhu-modal:not(.hidden)", timeout=10000)
        page.fill("#mingzhu-name", "质量验收命主")
        page.fill("#pick-year", "1990")
        page.fill("#pick-month", "5")
        page.fill("#pick-day", "12")
        page.fill("#pick-hour", "8")
        page.fill("#pick-minute", "30")
        page.select_option("#mingzhu-gender", "female")
        page.fill("#mingzhu-location", "北京")
        page.click("#mingzhu-submit-btn")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('.mingzhu-card')).some(el => el.textContent.includes('质量验收命主'))",
            timeout=30000,
        )

        overview = page.locator("#report-content").text_content(timeout=3000) or ""
        if "命盘总览" not in overview:
            result["errors"].append("overview missing 命盘总览")

        page.check("#trusted-mode-toggle")
        page.fill("#chat-input", "报告")
        page.click("#chat-send-btn")
        try:
            page.wait_for_function(
                "() => (document.getElementById('report-status')?.textContent || '').includes('完成')",
                timeout=args.timeout_ms,
            )
        except PlaywrightTimeoutError:
            result["errors"].append("AI report did not finish before timeout")

        report = page.locator("#report-content").text_content(timeout=5000) or ""
        table_count = page.locator("#report-content table").count()
        body = page.locator("body").text_content(timeout=5000) or ""
        page.screenshot(path=str(out_dir / "ui-report-quality.png"), full_page=True)
        (out_dir / "ui-report-quality-report.txt").write_text(report, encoding="utf-8")

        result["signals"] = {
            "report_chars": len(report),
            "table_count": table_count,
            "has_disclaimer": "免责声明" in report or "仅供参考" in report,
            "has_validation_note": "系统校验提示" in report,
            "has_connection_error": any(term in body for term in ["连接失败", "暂不可用", "API 错误"]),
            "bad_patterns": [pattern for pattern in BAD_PATTERNS if pattern in report],
        }

        if result["signals"]["report_chars"] < 2500:
            result["errors"].append("report shorter than 2500 chars")
        if result["signals"]["table_count"] < 5:
            result["errors"].append("report has fewer than 5 rendered tables")
        if not result["signals"]["has_disclaimer"]:
            result["errors"].append("report missing disclaimer")
        if result["signals"]["has_connection_error"]:
            result["errors"].append("page contains AI connection error")
        if result["signals"]["bad_patterns"] and not result["signals"]["has_validation_note"]:
            result["errors"].append("bad BaZi claims present without 系统校验提示")

        (out_dir / "ui-report-quality.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        browser.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
```

- [ ] **Step 2: Create the PowerShell wrapper**

Create `scripts/verify_ui_report_quality.ps1`:

```powershell
param(
    [int]$Port = 8770,
    [string]$OutDir = ".tmp/ui-report-quality"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not $env:DEEPSEEK_API_KEY -and (Test-Path ".deepseek_key")) {
    $env:DEEPSEEK_API_KEY = (Get-Content ".deepseek_key" -Raw).Trim()
}
if (-not $env:DEEPSEEK_API_KEY -and -not $env:ANTHROPIC_API_KEY) {
    Write-Error "UI quality check requires DEEPSEEK_API_KEY or ANTHROPIC_API_KEY."
    exit 2
}

New-Item -ItemType Directory -Force ".tmp" | Out-Null
$dbPath = Join-Path (Get-Location) ".tmp\ui-report-quality.db"
$stdout = ".tmp\ui-report-quality-uvicorn.out.log"
$stderr = ".tmp\ui-report-quality-uvicorn.err.log"
Remove-Item $dbPath -Force -ErrorAction SilentlyContinue

$env:BAZI_API_RETRIES = "0"
$env:BAZI_DB_PATH = $dbPath
$proc = Start-Process -FilePath python `
    -ArgumentList @("-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", [string]$Port) `
    -WorkingDirectory (Get-Location) `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

try {
    $base = "http://127.0.0.1:$Port"
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing "$base/api/health" -TimeoutSec 2
            if ($resp.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) {
        Write-Error "Server did not become ready. See $stderr"
        exit 3
    }

    python scripts/run_ui_report_quality.py --base-url $base --out-dir $OutDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "UI report quality check failed."
        exit $LASTEXITCODE
    }
} finally {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
```

- [ ] **Step 3: Run the quality verifier**

Run with network access allowed for the backend process:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_ui_report_quality.ps1
```

Expected:

```text
"errors": []
```

- [ ] **Step 4: Record the result in acceptance docs**

Append this row to `docs/BAZIQA_ACCEPTANCE_REPORT.md` under the verification table:

```markdown
| UI report quality smoke | PASS | `scripts/verify_ui_report_quality.ps1`; clean DB; generated 1990-05-12 female Beijing report; no connection errors; bad-claim validator present |
```

- [ ] **Step 5: Commit Task 5**

```powershell
git add scripts/run_ui_report_quality.py scripts/verify_ui_report_quality.ps1 docs/BAZIQA_ACCEPTANCE_REPORT.md
git commit -m "test: add ui report quality smoke check"
```

## Final Verification Matrix

Run these commands after all tasks:

```powershell
python -m pytest tests/test_bazi_report_validator.py tests/test_api.py tests/test_frontend_assets.py -q
python -m pytest -q -m "not e2e"
python -m pytest tests/test_e2e.py -q -s --tb=short
python scripts\test_all_reports_e2e.py
python scripts\test_all_reports_edge.py
$env:BAZIQA_REAL_DIR='F:\project\BaziQA\data'; python -m pytest tests/test_baziqa_real_import_contract.py -q
powershell -ExecutionPolicy Bypass -File scripts\verify_baziqa_real_import.ps1 -SourceDir F:\project\BaziQA\data
powershell -ExecutionPolicy Bypass -File scripts\verify_ui_report_quality.ps1
```

Expected final result:

- All pytest commands exit `0`.
- Report helper scripts print no failures.
- Real BaziQA import reports `688` rows or a documented higher count if upstream data grows.
- UI report quality smoke prints `"errors": []`.
- Browser console contains no blocked Google Fonts or jsDelivr ECharts requests.
- Generated reports either avoid deterministic BaZi errors or include `系统校验提示` when a model emits one.

## Completion Checklist

- [ ] Bad claim `巳午未会火局` is flagged when `未` is absent.
- [ ] Bad claim `丑为火库` is flagged with the correct fire storage branch `戌`.
- [ ] Unsupported `财星当令` wording is flagged when month-branch main qi is not wealth.
- [ ] Formal saved reports no longer start with `好的，我将...`.
- [ ] `深度报告` routes to the deep report tab.
- [ ] Auto-overview E2E fails on both old placeholder strings.
- [ ] Main page does not rely on Google Fonts or jsDelivr at runtime.
- [ ] UI report quality smoke is repeatable from one PowerShell command.
- [ ] Acceptance report records the new UI quality smoke result.

## Self-Review

Spec coverage:

- Report quality factual errors are covered by Tasks 1, 2, and 5.
- Weak E2E overview assertion is covered by Task 3.
- External frontend resource failures are covered by Task 4.
- Deep report routing bug is covered by Task 3.
- Conversational preface cleanup is covered by Tasks 1 and 2.

Placeholder scan:

- This plan contains concrete file paths, test code, implementation code, commands, and expected results.
- No step relies on unspecified behavior.

Type consistency:

- Validator API names are consistent across tasks: `validate_report_claims`, `strip_report_preface`, and `format_validation_note`.
- Test fixture chart shape matches current `api_server.py` and `tests/test_api.py` chart dictionaries.

