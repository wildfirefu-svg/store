# Project Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the XuanJiZi project by fixing E2E test infrastructure, AI streaming reliability, frontend rendering safety, production security defaults, repository artifact hygiene, and the BaZi quality evaluation loop.

**Architecture:** Keep the existing FastAPI + vanilla ES module frontend + SQLite architecture. Apply focused fixes at the layer where each problem originates: tests own service lifecycle, frontend owns SSE parsing and DOM safety, backend owns provider-aware diagnostics and production security policy, benchmark code owns quality metrics and temporary outputs.

**Tech Stack:** Python, FastAPI, pytest, Playwright, vanilla JavaScript ES modules, SQLite, DeepSeek/Anthropic streaming APIs, fpdf2.

---

## File Structure

Create:

- `docs/AI_TROUBLESHOOTING.md`: User-facing DeepSeek/Anthropic configuration and runtime error guide.
- `docs/SECURITY.md`: Production security checklist for CORS, auth, logs, data retention, and local key files.
- `docs/QUALITY_EVALUATION.md`: BaZi quality metric definitions and benchmark workflow.

Modify:

- `tests/test_e2e.py`: Make E2E tests self-contained and deterministic.
- `static/js/api.js`: Replace fragile SSE chunk parser with a persistent parser.
- `static/js/stream.js`: Remove raw AI output insertion via `innerHTML`.
- `api_server.py`: Fix fallback provider messaging and optionally disable query-key auth in production.
- `config.py`: Add production security switches.
- `.gitignore`: Ignore build artifacts and generated test outputs.
- `report_builder.py`: Handle empty `da_yun` safely.
- `tests/test_report_builder.py`: Cover empty `da_yun`.
- `tests/test_rate_limit.py`: Cover production query-key policy.
- `tests/test_api.py`: Cover provider-aware fallback text.
- `tests/frontend` or `tests/test_frontend_stream_parser.py`: Add frontend SSE parser regression coverage if a JS test runner is introduced; otherwise use Playwright route mocking.
- Benchmark tests that write to `benchmark/outputs` or `quality/model_quality_report.json`: redirect writes to `tmp_path`.

Do not modify:

- `.deepseek_key`
- `.anthropic_key`
- `bazi_data.db`
- Existing user-created reports or screenshots

---

### Task 1: Make E2E Tests Self-Contained

**Files:**

- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Add a local server fixture**

Add this fixture near the top of `tests/test_e2e.py`:

```python
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = "http://127.0.0.1:8000"


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Server did not start on {host}:{port}: {last_error}")


@pytest.fixture(scope="session")
def live_server():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_port("127.0.0.1", 8000)
        yield BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
```

- [ ] **Step 2: Make the page fixture depend on the server**

Replace the existing `page` fixture with:

```python
@pytest.fixture
def page(browser, live_server) -> Page:
    p = browser.new_page(viewport={"width": 1400, "height": 900})
    p.goto(live_server, wait_until="domcontentloaded")
    p.wait_for_timeout(1000)
    yield p
    p.close()
```

- [ ] **Step 3: Add a helper that creates a chart**

Add:

```python
def create_chart(page: Page, name: str = "E2E测试") -> None:
    page.click("#add-mingzhu-btn")
    page.wait_for_selector("#add-mingzhu-modal:not(.hidden)")
    page.fill("#mingzhu-name", name)
    page.fill("#mingzhu-location", "北京")
    page.click("#mingzhu-submit-btn")
    page.wait_for_selector(".mingzhu-card", timeout=8000)
    page.wait_for_timeout(1000)
```

- [ ] **Step 4: Remove hidden state dependencies**

Change `test_auto_overview_generated` to create a chart first:

```python
def test_auto_overview_generated(self, page):
    create_chart(page, "总览测试")
    report = page.locator("#report-content").text_content() or ""
    assert "等待输入" not in report
    assert len(report.strip()) > 0
```

- [ ] **Step 5: Mock AI stream in chat E2E**

Before filling chat input in `test_send_message_streams_response`, add:

```python
page.route(
    "**/api/chat/stream**",
    lambda route: route.fulfill(
        status=200,
        headers={"content-type": "text/event-stream"},
        body='event: tool\ndata: {"name":"命盘分析"}\n\n'
             'event: reply\ndata: {"text":"测试回复正常","tool":null}\n\n'
             'event: done\ndata: {"corrections":0}\n\n',
    ),
)
create_chart(page, "聊天测试")
```

- [ ] **Step 6: Run E2E tests**

Run:

```powershell
python -m pytest tests/test_e2e.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 7: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
240 passed
```

- [ ] **Step 8: Commit**

```powershell
git add tests/test_e2e.py
git commit -m "test: make e2e suite self-contained"
```

---

### Task 2: Fix Frontend SSE Parsing

**Files:**

- Modify: `static/js/api.js`
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Extract a persistent SSE parser**

In `static/js/api.js`, add this helper above `apiChatStream`:

```javascript
function createSseParser(handlers) {
    var buffer = '';
    var currentEvent = '';
    var dataLines = [];

    function dispatch() {
        if (!dataLines.length) return;
        var payload = dataLines.join('\n');
        var type = currentEvent || 'message';
        currentEvent = '';
        dataLines = [];
        try {
            var data = JSON.parse(payload);
            handlers.onEvent(type, data);
        } catch(e) {
            if (handlers.onMalformed) handlers.onMalformed(payload);
        }
    }

    return {
        push: function(chunk) {
            buffer += chunk;
            var lines = buffer.split(/\r?\n/);
            buffer = lines.pop();
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (line === '') {
                    dispatch();
                } else if (line.indexOf('event:') === 0) {
                    currentEvent = line.slice(6).trim();
                } else if (line.indexOf('data:') === 0) {
                    dataLines.push(line.slice(5).trimStart());
                }
            }
        },
        finish: function() {
            if (buffer) {
                this.push('\n');
            }
            dispatch();
        }
    };
}
```

- [ ] **Step 2: Replace line-by-line chunk parsing**

Replace the parser block in `pump()` with:

```javascript
var parser = createSseParser({
    onEvent: function(eventType, data) {
        if (eventType === 'tool') {
            gotContent = true;
            onToolStart(data.name);
        } else if (eventType === 'reply') {
            gotContent = true;
            onReplyDelta(data.text, data.tool || null);
        } else if (eventType === 'report') {
            gotContent = true;
            onReportDelta(data.text, data.tab || 'overview');
        } else if (eventType === 'done') {
            onDone(data.corrections || 0);
            aborted = true;
            if (reader) {
                try { reader.cancel(); } catch(e) {}
            }
        }
    }
});
```

Then, inside `reader.read().then`, replace the `buffer += ...` and `lines` loop with:

```javascript
parser.push(decoder.decode(result.value, {stream: true}));
if (aborted) return;
return pump();
```

When `result.done` is true, call:

```javascript
parser.finish();
if (!gotContent) {
    onReplyDelta('\n\n⚠️ AI 服务连接失败。请确认：\n1. 已设置 DEEPSEEK_API_KEY，或在项目目录创建 .deepseek_key / .anthropic_key 文件\n2. API Key 有效且账户余额/额度可用\n3. 当前启动后端的终端可以访问 DeepSeek/Anthropic API', null);
}
onDone(0);
return;
```

- [ ] **Step 3: Add a Playwright route test for split chunks**

In `tests/test_e2e.py`, add a chat test that fulfills a stream where event/data are split across the body:

```python
def test_chat_stream_handles_sse_boundaries(self, page):
    page.route(
        "**/api/chat/stream**",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body='event: reply\n'
                 'data: {"text":"第一段","tool":null}\n\n'
                 'event: reply\n'
                 'data: {"text":"第二段","tool":null}\n\n'
                 'event: done\n'
                 'data: {"corrections":0}\n\n',
        ),
    )
    create_chart(page, "流式边界测试")
    page.fill("#chat-input", "测试流式")
    page.click("#chat-send-btn")
    page.wait_for_timeout(1000)
    text = page.locator(".chat-messages").text_content() or ""
    assert "第一段" in text
    assert "第二段" in text
    assert "连接失败" not in text
```

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_e2e.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 5: Commit**

```powershell
git add static/js/api.js tests/test_e2e.py
git commit -m "fix: make ai stream parser chunk-safe"
```

---

### Task 3: Remove Raw AI HTML Insertion

**Files:**

- Modify: `static/js/stream.js`
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Add a safe line rendering helper**

Add near the top of `static/js/stream.js`:

```javascript
function renderPlainTextWithBreaks(el, text) {
    el.textContent = '';
    var parts = String(text || '').split('\n');
    for (var i = 0; i < parts.length; i++) {
        if (i > 0) el.appendChild(document.createElement('br'));
        el.appendChild(document.createTextNode(parts[i]));
    }
}
```

- [ ] **Step 2: Add a safe tool label helper**

Add:

```javascript
function setSenderTool(sender, toolName) {
    sender.textContent = '玄机子 ';
    var tag = document.createElement('span');
    tag.className = 'tool-tag';
    tag.textContent = '🔧 ' + String(toolName || '');
    sender.appendChild(tag);
}
```

- [ ] **Step 3: Replace unsafe `innerHTML` writes**

Replace:

```javascript
sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + toolName + '</span>';
```

with:

```javascript
setSenderTool(sender, toolName);
```

Replace:

```javascript
bubble.innerHTML = (replyText || '分析完成，请查看右侧报告。').replace(/\n/g, '<br>');
```

with:

```javascript
renderPlainTextWithBreaks(bubble, replyText || '分析完成，请查看右侧报告。');
```

Replace:

```javascript
sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + currentTool + '</span>';
```

with:

```javascript
setSenderTool(sender, currentTool);
```

- [ ] **Step 4: Add E2E XSS regression**

Add:

```python
def test_ai_reply_is_rendered_as_text(self, page):
    payload = '<img src=x onerror="window.__xss=1">安全文本'
    page.route(
        "**/api/chat/stream**",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body='event: reply\n'
                 f'data: {{"text":{payload!r},"tool":null}}\n\n'
                 'event: done\n'
                 'data: {"corrections":0}\n\n',
        ),
    )
    create_chart(page, "XSS测试")
    page.fill("#chat-input", "测试")
    page.click("#chat-send-btn")
    page.wait_for_timeout(1000)
    assert page.evaluate("window.__xss") is None
    text = page.locator(".chat-messages").text_content() or ""
    assert "<img src=x" in text
    assert "安全文本" in text
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_e2e.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 6: Commit**

```powershell
git add static/js/stream.js tests/test_e2e.py
git commit -m "fix: render ai replies as plain text"
```

---

### Task 4: Fix Provider-Aware AI Error Diagnostics

**Files:**

- Modify: `api_server.py`
- Modify: `claude_api.py` if needed
- Test: `tests/test_api.py`
- Create: `docs/AI_TROUBLESHOOTING.md`

- [ ] **Step 1: Fix fallback text**

Replace `api_server.py` fallback return text with:

```python
return (
    f'\n\n⚠️ AI 服务暂不可用。请检查 DEEPSEEK_API_KEY / ANTHROPIC_API_KEY 是否已配置、'
    f'Key 是否有效、账户余额/额度是否可用，以及当前后端进程是否能访问模型 API。'
    f'\n\n**本地分析**: 日主{gan}{wu}，{grade}（日主占比{int(dm_pct*100)}%）。'
    f'\n\n请修复 AI 服务连接后重试，以获取四合出深度报告。'
)
```

- [ ] **Step 2: Add fallback text test**

In `tests/test_api.py`, add:

```python
def test_generate_fallback_mentions_deepseek_and_anthropic():
    from api_server import _generate_fallback

    chart = {
        "day_master": {"gan": "甲", "wuxing": "木"},
        "wuxing_stats": {"金": 1, "木": 3, "水": 1, "火": 1, "土": 1},
    }

    text = _generate_fallback(chart)
    assert "DEEPSEEK_API_KEY" in text
    assert "ANTHROPIC_API_KEY" in text
    assert "本地分析" in text
```

- [ ] **Step 3: Create troubleshooting doc**

Create `docs/AI_TROUBLESHOOTING.md`:

```markdown
# AI 服务连接排查

## 支持的 Key

- DeepSeek: `DEEPSEEK_API_KEY` 或项目根目录 `.deepseek_key`
- Anthropic: `ANTHROPIC_API_KEY` 或项目根目录 `.anthropic_key`

## 常见错误

### 前端显示“AI 服务连接失败”

先确认后端是否启动，再检查后端日志。该提示可能来自：

- 未配置 key
- key 无效
- 账户余额或额度不足
- API 服务网络不可达
- 模型接口返回非 200
- 前端未收到完整 SSE 内容

## 推荐启动方式

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

## 验证

打开：

```text
http://127.0.0.1:8000/api/health
```

再在页面创建命盘并发送一条短问题。
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_api.py::test_generate_fallback_mentions_deepseek_and_anthropic tests/test_claude_api.py -q
```

Expected:

```text
10 passed
```

- [ ] **Step 5: Commit**

```powershell
git add api_server.py tests/test_api.py docs/AI_TROUBLESHOOTING.md
git commit -m "fix: clarify ai provider diagnostics"
```

---

### Task 5: Harden Production Security Defaults

**Files:**

- Modify: `config.py`
- Modify: `api_server.py`
- Modify: `tests/test_rate_limit.py`
- Create: `docs/SECURITY.md`

- [ ] **Step 1: Add production auth config**

In `config.py`, add:

```python
ENV = os.environ.get("BAZI_ENV", "development").lower()
ALLOW_QUERY_API_KEY = os.environ.get(
    "BAZI_ALLOW_QUERY_API_KEY",
    "1" if ENV != "production" else "0",
) in ("1", "true", "True", "yes", "YES")
```

- [ ] **Step 2: Use the config in auth middleware**

In `api_server.py`, import `ALLOW_QUERY_API_KEY` and replace:

```python
if request.query_params.get("api_key") == _BAZI_API_KEY:
    return await call_next(request)
```

with:

```python
if ALLOW_QUERY_API_KEY and request.query_params.get("api_key") == _BAZI_API_KEY:
    return await call_next(request)
```

Update the 401 message:

```python
content={"detail": "需要有效的 API Key。请在 Authorization 头中提供 Bearer token。"},
```

- [ ] **Step 3: Add production query-key test**

In `tests/test_rate_limit.py`, add:

```python
def test_query_api_key_can_be_disabled(monkeypatch):
    import api_server

    monkeypatch.setattr(api_server, "_BAZI_API_KEY", "secret")
    monkeypatch.setattr(api_server, "ALLOW_QUERY_API_KEY", False)

    resp = client.get("/api/charts?api_key=secret")
    assert resp.status_code == 401

    resp = client.get("/api/charts", headers={"Authorization": "Bearer secret"})
    assert resp.status_code == 200
```

- [ ] **Step 4: Create security doc**

Create `docs/SECURITY.md`:

```markdown
# 生产安全配置

## 必填环境变量

- `BAZI_API_KEY`: 后端 API 访问 key
- `BAZI_CORS_ORIGINS`: 生产域名列表，禁止使用 `*`
- `BAZI_ENV=production`
- `BAZI_ALLOW_QUERY_API_KEY=0`

## Key 传递方式

生产环境只允许：

```text
Authorization: Bearer <BAZI_API_KEY>
```

不要使用：

```text
?api_key=<BAZI_API_KEY>
```

## 敏感数据

出生信息、分析报告、人生事件、聊天记录都应视为敏感数据。生产日志不得记录完整 key、完整 prompt、完整出生信息。
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_rate_limit.py -q
```

Expected:

```text
pass
```

- [ ] **Step 6: Commit**

```powershell
git add config.py api_server.py tests/test_rate_limit.py docs/SECURITY.md
git commit -m "chore: harden production api auth defaults"
```

---

### Task 6: Clean Repository Artifact Policy

**Files:**

- Modify: `.gitignore`
- Possibly untrack: `build/`, `dist/`

- [ ] **Step 1: Update `.gitignore`**

Append:

```gitignore

# Build artifacts
build/
dist/

# Generated benchmark test outputs
benchmark/outputs/test_report_*.md
benchmark/reports/__pycache__/
quality/model_quality_report.json
```

- [ ] **Step 2: Inspect tracked artifacts**

Run:

```powershell
git ls-files build dist
```

Expected:

```text
<tracked artifact list>
```

- [ ] **Step 3: Untrack artifacts if release artifacts are not intentionally versioned**

Run only after confirming with the project owner:

```powershell
git rm -r --cached build dist
```

Expected:

```text
rm 'build/...'
rm 'dist/...'
```

- [ ] **Step 4: Run tests and status check**

Run:

```powershell
python -m pytest -q
git status --short
```

Expected:

- Tests pass.
- No generated test output appears except intended source changes.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore
git commit -m "chore: ignore generated build artifacts"
```

If artifacts were untracked:

```powershell
git add -u build dist
git commit -m "chore: remove generated artifacts from source control"
```

---

### Task 7: Stop Tests From Polluting the Worktree

**Files:**

- Modify benchmark/report tests that write to `benchmark/outputs`
- Modify quality tests that write to `quality/model_quality_report.json`

- [ ] **Step 1: Locate writes**

Run:

```powershell
rg -n "benchmark/outputs|model_quality_report.json|open\\(|write_text|save_report" tests benchmark quality
```

Expected:

```text
<list of tests and helpers that write files>
```

- [ ] **Step 2: Redirect outputs to `tmp_path`**

For each test that writes generated files, change hard-coded project paths to `tmp_path`.

Pattern:

```python
def test_report_output(tmp_path):
    output_path = tmp_path / "report.md"
    result = generate_report(..., output_path=str(output_path))
    assert output_path.exists()
```

- [ ] **Step 3: Verify worktree cleanliness**

Run:

```powershell
git status --short
python -m pytest -q
git status --short
```

Expected:

- Status before and after tests only shows intentional source changes.
- No `benchmark/outputs/test_report_*.md`.
- No modified `quality/model_quality_report.json`.

- [ ] **Step 4: Commit**

```powershell
git add tests benchmark quality
git commit -m "test: isolate generated report outputs"
```

---

### Task 8: Make Report Builder Robust to Empty Da Yun

**Files:**

- Modify: `report_builder.py`
- Modify: `tests/test_report_builder.py`

- [ ] **Step 1: Add failing test**

In `tests/test_report_builder.py`, add:

```python
def test_render_chart_table_handles_empty_dayun(sample_four_pillars):
    text = render_chart_table(
        sample_four_pillars,
        {"gan": "甲", "wuxing": "木"},
        [],
        {},
        {},
        {},
    )
    assert "起运：N/A" in text
    assert "当前大运：N/A" in text
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_report_builder.py::test_render_chart_table_handles_empty_dayun -q
```

Expected:

```text
FAILED
IndexError
```

- [ ] **Step 3: Implement minimal fix**

In `report_builder.py`, replace:

```python
lines.append(f'起运：{da_yun[0].get("start_age","?")}岁  当前大运：{dy_str}')
```

with:

```python
start_age = da_yun[0].get("start_age", "?") if da_yun else "N/A"
start_suffix = "岁" if da_yun else ""
lines.append(f'起运：{start_age}{start_suffix}  当前大运：{dy_str}')
```

- [ ] **Step 4: Run report builder tests**

Run:

```powershell
python -m pytest tests/test_report_builder.py -q
```

Expected:

```text
pass
```

- [ ] **Step 5: Commit**

```powershell
git add report_builder.py tests/test_report_builder.py
git commit -m "fix: handle reports without da yun data"
```

---

### Task 9: Establish BaZi Quality Evaluation Workflow

**Files:**

- Create: `docs/QUALITY_EVALUATION.md`
- Modify: benchmark docs or tests only if needed

- [ ] **Step 1: Create metric definitions**

Create `docs/QUALITY_EVALUATION.md`:

```markdown
# 八字判断质量评测

## 当前基线

来源：`quality/model_quality_report_v2.json`

- 测试案例：82
- 事件总数：544
- 总体平均分：0.62
- 正向匹配率：25.2%
- 弱匹配率：44.7%
- 无匹配率：30.1%

## 分领域基线

| 领域 | 平均分 | 正向匹配率 | 优先级 |
|---|---:|---:|---|
| 事业 | 0.85 | 38.1% | 保持 |
| 财运 | 0.70 | 28.4% | 中 |
| 婚恋 | 0.69 | 21.1% | 中 |
| 健康 | 0.44 | 16.7% | 高 |
| 家庭 | 0.27 | 9.9% | 高 |
| 教育 | 0.07 | 0.0% | 先补样本 |

## 输出必须包含

每条判断必须包含：

- 判断结论
- 命理证据：大运、流年、十神、五行、冲合刑害、神煞
- 置信度
- 反例条件
- 安全边界：不得给确定性医疗、投资、灾祸断言

## 回归门槛

每次 prompt 或模型策略修改后必须生成 benchmark 报告，并比较：

- 总体平均分不得下降超过 0.03
- 健康、家庭领域不得下降
- 安全分不得下降
- 稳定性分不得下降
```

- [ ] **Step 2: Add next dataset requirements**

Append:

```markdown
## 下一批数据补强

优先补：

1. 健康事件：至少 100 条，标注疾病类型、年份、严重程度、命理证据。
2. 家庭事件：至少 100 条，标注父母、子女、迁居、家族责任、关系变化。
3. 婚恋事件：至少 80 条，标注恋爱、结婚、分离、复合、冲突类型。
4. 教育事件：至少 50 条，否则不纳入评分排名。
```

- [ ] **Step 3: Commit**

```powershell
git add docs/QUALITY_EVALUATION.md
git commit -m "docs: define bazi quality evaluation workflow"
```

---

### Task 10: Final Verification

**Files:**

- No code changes unless previous tasks reveal a defect.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
240+ passed
```

- [ ] **Step 2: Run app smoke test**

Run:

```powershell
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

Verify:

- Page loads.
- A chart can be created.
- A mocked or real AI stream displays without “连接失败” when service is healthy.
- The browser console has no JavaScript errors.

- [ ] **Step 3: Check git status**

Run:

```powershell
git status --short
```

Expected:

```text
<only intentional source/doc changes>
```

- [ ] **Step 4: Prepare release notes**

Write a short summary:

```markdown
## Stabilization Summary

- E2E suite now starts its own local server.
- AI streaming parser is chunk-safe.
- AI replies render as text, preventing HTML injection.
- DeepSeek/Anthropic diagnostics are provider-aware.
- Production auth defaults are safer.
- Build artifacts and test outputs are excluded from source control.
- BaZi quality evaluation workflow is documented.
```

---

## Execution Order

1. Task 1: E2E self-contained tests.
2. Task 2: SSE parser.
3. Task 3: AI HTML safety.
4. Task 4: AI diagnostics.
5. Task 8: Report builder robustness.
6. Task 7: Test output isolation.
7. Task 5: Production security.
8. Task 6: Artifact policy.
9. Task 9: Quality workflow.
10. Task 10: Final verification.

This order fixes the feedback loop first, then fixes user-visible AI failures, then hardens security and quality process.

---

## Self-Review

Spec coverage:

- Project audit findings are covered in `docs/audits/2026-06-17-project-audit.md`.
- E2E failure is covered by Task 1.
- AI connection failure and streaming parser risk are covered by Tasks 2 and 4.
- HTML injection risk is covered by Task 3.
- Security defaults are covered by Task 5.
- Build artifact tracking is covered by Task 6.
- Test pollution is covered by Task 7.
- Report builder empty data risk is covered by Task 8.
- BaZi judgment quality improvement is covered by Task 9.

Placeholder scan:

- No `TBD`.
- No generic “add tests” without concrete examples.
- Each task includes exact files, commands, and expected outcomes.

Type and name consistency:

- Existing file names match the audited repository.
- New docs live under `docs/`.
- Test commands use the existing pytest setup.
