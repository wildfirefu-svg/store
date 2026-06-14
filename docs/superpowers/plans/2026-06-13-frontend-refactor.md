# Frontend Medium Refactor — Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ES modules, CSS split, 1024px responsive, 5 JS bug fixes — zero visual regression.

**Architecture:** 9 JS files become ES modules (export/import), 1056-line CSS splits into 3 files via @import, HTML uses `<script type="module">`. Tablet gets 2×2 grid at 1024px breakpoint.

**Tech Stack:** Vanilla ES modules, CSS @import, no build tools.

---

### Task 1: Create static/css/base.css

**Files:**
- Create: `static/css/base.css`
- Reference: `static/style.css:1-70` (variables, body, layout grid), `static/style.css:1021-1056` (animations)

- [ ] **Step 1: Create base.css with variables, body, layout, and animations**

```css
/* base.css — design tokens, body, layout grid, animations */
@import './panels.css';
@import './modal-mobile.css';

:root {
    --ink: #1C1917;
    --parchment-light: #faf6eb;
    --cinnabar: #c43a31;
    --cinnabar-light: rgba(196,58,49,0.08);
    --coral: #e8816b;
    --gold: #A16207;
    --gold-light: rgba(161,98,7,0.08);
    --text-main: #2c2416;
    --text-dim: #6b6250;
    --text-faint: #9a9078;
    --text-tertiary: #8a7e6e;
    --border-subtle: rgba(161,98,7,0.18);
    --border-strong: rgba(161,98,7,0.32);
    --surface-dark: rgba(245,240,224,0.06);
    --surface-hover: rgba(245,240,224,0.10);
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.15);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.25);
    --shadow-lg: 0 8px 32px rgba(0,0,0,0.35);
    --radius-sm: 6px;
    --radius: 10px;
    --radius-lg: 16px;
    --radius-xl: 20px;
    --font: "Noto Sans TC", "PingFang SC", "SF Pro Display", "Helvetica Neue", sans-serif;
    --font-kai: "Noto Serif TC", "Noto Serif TC", "KaiTi", "STKaiti", "SimSun", serif;
}

body {
    background: var(--ink);
    color: rgba(245,240,224,0.85);
    font-family: var(--font);
    overflow: hidden;
    height: 100vh;
    -webkit-font-smoothing: antialiased;
    position: relative;
}

body::before {
    content: '';
    position: fixed; inset: 0;
    pointer-events: none; z-index: 0;
    opacity: 0.03;
    background:
        radial-gradient(ellipse 80% 60% at 20% 50%, rgba(184,150,12,0.5) 0%, transparent 60%),
        radial-gradient(ellipse 60% 50% at 75% 70%, rgba(196,58,49,0.3) 0%, transparent 50%),
        radial-gradient(ellipse 40% 30% at 50% 20%, rgba(245,240,224,0.2) 0%, transparent 45%);
}

* { margin:0; padding:0; box-sizing:border-box; }

.app-container {
    display: grid;
    grid-template-columns: 200px 30fr 30fr 40fr;
    height: 100vh;
    position: relative;
    z-index: 1;
}
.app-container.panel-collapsed {
    grid-template-columns: 32px 30fr 30fr 40fr;
}

/* Pulse loading animation */
.ai-loading { display: inline-flex; gap: 5px; padding: 4px 0; align-items: center; }
.ai-loading span { width: 7px; height: 7px; border-radius: 50%; background: var(--gold); animation: pulse-dot 1.2s infinite ease-in-out; }
.ai-loading span:nth-child(2) { animation-delay: 0.2s; }
.ai-loading span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot { 0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); } 40% { opacity: 1; transform: scale(1.3); } }

.stream-text { white-space: pre-wrap; word-break: break-word; }
.streaming-cursor { display: inline; animation: cursor-blink 0.8s step-end infinite; color: var(--cinnabar); font-weight: 700; }
@keyframes cursor-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

@keyframes skeleton-pulse { 0% { opacity: 0.4; } 50% { opacity: 0.7; } 100% { opacity: 0.4; } }
@keyframes spin { to { transform: rotate(360deg); } }
```

### Task 2: Create static/css/panels.css

**Files:**
- Create: `static/css/panels.css`
- Reference: `static/style.css:71-940`

- [ ] **Step 1: Extract panels CSS from style.css lines 71-940**

This is the bulk of the CSS — all `.mingzhu-panel`, `.chat-column`, `.chart-column`, `.report-column` rules plus their children. Copy the existing content verbatim from `style.css` lines 71-940 into `panels.css`. No modifications — this is a pure extraction.

Run after copying:
```bash
python -c "with open('F:/project/agent/static/css/panels.css') as f: print(len(f.read()), 'bytes')"
```
Expected: ~28000 bytes (matches original section).

### Task 3: Create static/css/modal-mobile.css with 1024px breakpoint

**Files:**
- Create: `static/css/modal-mobile.css`
- Reference: `static/style.css:941-1019`

- [ ] **Step 1: Create modal-mobile.css with existing mobile + new 1024px tablet breakpoint**

```css
/* modal-mobile.css — modal, responsive breakpoints */

/* ── Modal ── */
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 100; justify-content: center; align-items: center; }
.modal-overlay.active { display: flex; }
.modal-content { background: var(--ink); border: 1px solid var(--border-strong); border-radius: var(--radius-lg); padding: 24px; max-width: 480px; width: 90vw; max-height: 90vh; overflow-y: auto; color: rgba(245,240,224,0.85); }
.modal-content h3 { color: var(--gold); margin-bottom: 16px; }
.modal-content label { display: block; margin-top: 10px; font-size: 12px; color: var(--text-faint); }
.modal-content input, .modal-content select { width: 100%; padding: 8px 10px; margin-top: 4px; background: rgba(245,240,224,0.06); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); color: rgba(245,240,224,0.85); font-family: var(--font); }
.modal-row { display: flex; gap: 8px; }
.modal-row > * { flex: 1; }
.modal-actions { display: flex; gap: 8px; margin-top: 16px; justify-content: flex-end; }
.modal-actions button { padding: 8px 16px; border-radius: var(--radius-sm); border: none; cursor: pointer; font-family: var(--font); }
.btn-primary { background: var(--cinnabar); color: #fff; }
.btn-secondary { background: rgba(245,240,224,0.08); color: rgba(245,240,224,0.7); border: 1px solid var(--border-subtle); }

/* ── Tablet: 1024px 2×2 grid ── */
@media (max-width: 1024px) {
    .app-container {
        grid-template-columns: 40fr 60fr;
        grid-template-rows: 1fr 1fr;
    }
    .app-container.panel-collapsed {
        grid-template-columns: 40fr 60fr;
    }
    .mingzhu-panel { grid-row: 1; grid-column: 1; }
    .chat-column   { grid-row: 1; grid-column: 2; }
    .chart-column  { grid-row: 2; grid-column: 1; }
    .report-column { grid-row: 2; grid-column: 2; }
}

/* ── Mobile: ≤768px single column ── */
.mobile-nav { display: none; }

@media (max-width: 768px) {
    .app-container {
        grid-template-columns: 1fr;
        grid-template-rows: 1fr auto;
    }

    .mingzhu-panel { display: none; }
    .chart-column { display: none; }
    .report-column { display: none; }

    .mingzhu-panel.mobile-visible,
    .chart-column.mobile-visible,
    .report-column.mobile-visible { display: flex; }
    .chat-column { display: flex; }
    .chat-column.mobile-hidden { display: none; }

    .mobile-nav {
        display: flex;
        background: rgba(26, 26, 31, 0.95);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-top: 1px solid var(--border-subtle);
        z-index: 50;
    }

    .mnav-btn {
        flex: 1; padding: 10px 4px; background: none; border: none;
        color: var(--text-faint); font-size: 12px; font-family: var(--font);
        cursor: pointer; transition: all 0.2s;
        border-bottom: 2px solid transparent;
        display: flex; flex-direction: column; align-items: center; gap: 2px;
    }
    .mnav-btn svg { display: block; }
    .mnav-btn.active { color: var(--gold); border-bottom-color: var(--cinnabar); }

    .modal-content {
        width: 100vw; max-width: 100vw;
        border-radius: var(--radius-lg) var(--radius-lg) 0 0;
        position: fixed; bottom: 0; left: 0; padding: 20px 16px;
    }

    .report-content { padding: 14px; font-size: 13px; }
    .chat-messages { padding: 10px; }
    .chat-input-row { padding: 8px 10px; gap: 4px; }
    .chat-input-row input { font-size: 12px; padding: 8px 10px; }
    #chat-send-btn { padding: 8px 14px; font-size: 11px; }
    .report-tabs { padding: 8px; gap: 4px; overflow-x: auto; flex-wrap: nowrap; }
    .report-tab { font-size: 11px; padding: 5px 10px; white-space: nowrap; flex-shrink: 0; }

    .bazi-container { padding: 12px 8px; }
    .pillar-gan, .pillar-zhi { font-size: 22px; padding: 4px 0; }
    .pillar-label { font-size: 13px; padding: 4px 0; }
    .pillar-shishen { font-size: 11px; }
    .pillar-canggan { font-size: 11px; height: auto; }
    .pillar-nayin { font-size: 11px; }
}
```

Note: The modal CSS above is a simplified extraction. The actual modal/mobile rules come from `style.css` lines 941-1019. The full extraction will preserve the exact original CSS. The key addition is the `@media (max-width: 1024px)` block.

### Task 4: Update index.html — link to base.css, <script type="module">

**Files:**
- Modify: `templates/index.html:6,166-173`

- [ ] **Step 1: Replace CSS link**

```html
<!-- Old (line ~6): -->
<link rel="stylesheet" href="/static/style.css?v=20260604a">

<!-- New: -->
<link rel="stylesheet" href="/static/css/base.css?v=20260613a">
```

- [ ] **Step 2: Replace script tags with type="module"**

```html
<!-- Old (lines 166-173): -->
<!-- JS modules loaded in dependency order — app.js must be last -->
<script src="/static/js/api.js?v=20260604a"></script>
<script src="/static/js/state.js?v=20260604a"></script>
<script src="/static/js/markdown.js?v=20260604a"></script>
<script src="/static/js/render-bazi.js?v=20260604a"></script>
<script src="/static/js/render-ziwei.js?v=20260604a"></script>
<script src="/static/js/ui.js?v=20260604a"></script>
<script src="/static/js/stream.js?v=20260604a"></script>
<script src="/static/app.js?v=20260604a"></script>

<!-- New: -->
<script type="module" src="/static/app.js?v=20260613a"></script>
```

Only `app.js` needs to be loaded — ES module `import` statements pull in all dependencies automatically.

### Task 5: Migrate api.js to ES module

**Files:**
- Modify: `static/js/api.js`

- [ ] **Step 1: Remove dead code (lines 11-15), add export**

```javascript
// api.js — API communication layer
export const API = '/api';

export async function apiCreateChart(birth) {
    const r = await fetch(API + '/chart', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(birth) });
    return r.ok ? r.json() : null;
}

export function apiChatStream(chartId, message, onReplyDelta, onReportDelta, onToolStart, onDone) {
    var params = new URLSearchParams({chart_id: chartId, message: message});
    var url = '/api/chat/stream?' + params;
    var gotContent = false;
    var aborted = false;
    var reader = null;
    var ctrl = new AbortController();
    fetch(url, {signal: ctrl.signal}).then(function(response) {
        if (!response.ok) { throw new Error('HTTP ' + response.status); }
        reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';
        function pump() {
            if (aborted) return;
            return reader.read().then(function(result) {
                if (result.done) {
                    if (!gotContent) { onReplyDelta('\n\n⚠️ AI 服务连接失败…', null); }
                    onDone(0); return;
                }
                buffer += decoder.decode(result.value, {stream: true});
                var lines = buffer.split('\n');
                buffer = lines.pop();
                var eventType = '';
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (line.indexOf('event: ') === 0) { eventType = line.slice(7).trim(); }
                    else if (line.indexOf('data: ') === 0) {
                        var dataStr = line.slice(6);
                        try {
                            var data = JSON.parse(dataStr);
                            if (eventType === 'tool') { gotContent = true; onToolStart(data.name); }
                            else if (eventType === 'reply') { gotContent = true; onReplyDelta(data.text, data.tool || null); }
                            else if (eventType === 'report') { gotContent = true; onReportDelta(data.text, data.tab || 'overview'); }
                            else if (eventType === 'done') { onDone(data.corrections || 0); aborted = true; if (reader) { try { reader.cancel(); } catch(e) {} } return; }
                        } catch(e) {}
                    }
                }
                return pump();
            }).catch(function(e) {
                if (!gotContent) { var detail = (e && e.message) ? e.message : String(e || ''); onReplyDelta('\n\n⚠️ AI 服务连接失败（' + detail + '）…', null); }
                onDone(0);
            });
        }
        return pump();
    }).catch(function(e) {
        if (!gotContent) { var detail = (e && e.message) ? e.message : String(e || ''); onReplyDelta('\n\n⚠️ AI 服务连接失败（' + detail + '）…', null); }
        onDone(0);
    });
}
```

### Task 6: Migrate markdown.js to ES module

**Files:**
- Modify: `static/js/markdown.js`

- [ ] **Step 1: Add export to all functions**

Add `export` before `function _escHtml`, `function _renderMdTable`, `function _renderMdBlock`, `function renderMarkdown`. No other changes — the function bodies are unchanged.

### Task 7: Migrate state.js to ES module + bug fix

**Files:**
- Modify: `static/js/state.js`

- [ ] **Step 1: Add import at top, export on all symbols, add console.warn**

```javascript
// state.js — MingzhuManager / ChatHistory / CorrectionManager / PersistenceSync
import { API } from './api.js';

export const MingzhuManager = {
    // ... body unchanged ...
};

export const PersistenceSync = {
    async loadFromServer() {
        try { /* body unchanged */ }
        catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },
    async saveChartToServer(chartId, name, birthInfo, chartData) {
        try { /* body unchanged */ }
        catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },
    async deleteChartFromServer(chartId) {
        try { await fetch(API + '/charts/' + chartId, {method: 'DELETE'}); }
        catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },
    async saveChatMessage(chartId, role, text, tool) {
        try { /* body unchanged */ }
        catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },
    // loadChatHistory and loadReports unchanged (already return null on error)
    async loadChatHistory(chartId) { /* unchanged */ },
    async loadReports(chartId) { /* unchanged */ },
    async saveReport(chartId, tabId, content) {
        try { /* body unchanged */ }
        catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },
};

export const ChatHistory = { /* body unchanged */ };
export const CorrectionManager = { /* body unchanged */ };
```

Note: Keep all function bodies identical. Only add `import` at top, `export` before `const`, and `console.warn` in PersistenceSync catch blocks.

### Task 8: Migrate render-bazi.js to ES module

**Files:**
- Modify: `static/js/render-bazi.js`

- [ ] **Step 1: Add export**

Change `function renderBazi(chart)` to `export function renderBaziTable(chart)`. Remove the old `window.renderBaziTable = renderBazi` line if present. Body unchanged.

### Task 9: Migrate render-ziwei.js to ES module

**Files:**
- Modify: `static/js/render-ziwei.js`

- [ ] **Step 1: Add export**

Change `function renderZiwei(chart)` to `export function renderZiweiTable(chart)`. Remove old `window.renderZiweiTable` line if present. Body unchanged.

### Task 10: Migrate ui.js to ES module

**Files:**
- Modify: `static/js/ui.js`

- [ ] **Step 1: Add imports and exports**

```javascript
// ui.js — DOM manipulation, ReportTabs, chat messages
import { MingzhuManager, PersistenceSync, ChatHistory } from './state.js';
import { API } from './api.js';
import { renderMarkdown, _escHtml } from './markdown.js';
import { renderBaziTable } from './render-bazi.js';
import { renderZiweiTable } from './render-ziwei.js';

export { _escHtml };

export const ReportTabs = { /* body unchanged */ };
export function addChatMsg(role, text, tool) { /* body unchanged */ }
export function refreshPanel() { /* body unchanged */ }
export function switchMingzhu(chartId) { /* body unchanged */ }
export function deleteMingzhu(chartId) { /* body unchanged */ }
export function showModal() { /* body unchanged */ }
export function renderFullChart(chart) { /* body unchanged */ }
export function showReportFinal(tabId, markdown) { /* body unchanged */ }
```

Remove all `window.X = X` lines at the bottom. Keep function bodies identical.

### Task 11: Migrate stream.js to ES module

**Files:**
- Modify: `static/js/stream.js`

- [ ] **Step 1: Add imports and export**

```javascript
// stream.js — SSE streaming handler
import { apiChatStream } from './api.js';
import { ChatHistory, CorrectionManager } from './state.js';
import { addChatMsg, showReportFinal, ReportTabs } from './ui.js';

export function _sendWithStream(chartId, prompt, onSuccess, forceTab) { /* body unchanged */ }
```

### Task 12: Migrate app.js to ES module

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add all imports at top**

```javascript
// app.js — entry point
import { API, apiCreateChart, apiChatStream } from './js/api.js';
import { MingzhuManager, PersistenceSync, ChatHistory, CorrectionManager } from './js/state.js';
import { renderMarkdown, _escHtml } from './js/markdown.js';
import { renderBaziTable } from './js/render-bazi.js';
import { renderZiweiTable } from './js/render-ziwei.js';
import { ReportTabs, addChatMsg, refreshPanel, switchMingzhu, deleteMingzhu, showModal, renderFullChart, showReportFinal } from './js/ui.js';
import { _sendWithStream } from './js/stream.js';

// ── 辅助函数 ──
function _showToolBar(barId) { /* body unchanged */ }
// ... rest of file unchanged ...
```

- [ ] **Step 2: XSS fix — wrap user input in _escHtml where missing**

Find any HTML string concatenation with user-provided values (name fields, message text) in `app.js` and wrap with `_escHtml()`. Example pattern: `'<b>' + mz.name + '</b>'` → `'<b>' + _escHtml(mz.name) + '</b>'`.

### Task 13: Fix tools.js bugs + ES module

**Files:**
- Modify: `static/tools.js`

- [ ] **Step 1: Add import, chart_id null guard, fix event, XSS**

```javascript
// tools.js — standalone tools page
import { API } from './js/api.js';

const chartId = sessionStorage.getItem('chartId') || '';
if (chartId) {
    document.getElementById('zeri-chart-id').value = chartId;
    document.getElementById('liunian-chart-id').value = chartId;
    document.getElementById('name-chart-id').value = chartId;
}

// Bug fix 1: chart_id null guard (add to each submit handler start)
function _guardChartId() {
    if (!document.getElementById('zeri-chart-id').value) {
        alert('请先从首页排盘后再使用此工具');
        return false;
    }
    return true;
}

// Zeri — add guard
document.getElementById('zeri-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!_guardChartId()) return;
    // ... rest unchanged ...
});

// Liunian — add guard
document.getElementById('liunian-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!_guardChartId()) return;
    // ... rest unchanged ...
});

// Name eval — add guard
document.getElementById('name-eval-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!_guardChartId()) return;
    // ... rest unchanged ...
});

// Name gen — add guard
document.getElementById('name-gen-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!_guardChartId()) return;
    // ... rest unchanged ...
});

// Bug fix 2: switchNameTab — use explicit event parameter, add via addEventListener
function switchNameTab(tab, event) {
    document.querySelectorAll('#name-tabs .tab-btn').forEach(b => b.classList.remove('active'));
    if (event && event.target) event.target.classList.add('active');
    document.getElementById('name-eval-form').classList.toggle('hidden', tab !== 'eval');
    document.getElementById('name-gen-form').classList.toggle('hidden', tab !== 'gen');
    document.getElementById('name-result').innerHTML = '';
}
// Remove onclick="switchNameTab('eval')" from tools.html buttons — they're now bound via JS below
document.getElementById('tab-btn-eval').addEventListener('click', function(e) { switchNameTab('eval', e); });
document.getElementById('tab-btn-gen').addEventListener('click', function(e) { switchNameTab('gen', e); });

// Bug fix 3: XSS — wrap user-provided values in HTML construction
// (tools.js uses .innerHTML with data from API — the name/gen fields are from user input,
//  wrap them with a simple escape)
function _esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
// Apply _esc() to: d.date, d.ri_chen, d.ri_ganzhi, data.name, n.name, and any user-typed values
```

Note: In the actual implementation, apply `_esc()` to each user/API value in string concatenation within the tool result rendering. The key places are:
- Zeri: `d.date`, `d.weekday`
- Name eval: `data.name`  
- Name gen: `n.name`

### Task 14: Update tools.html for ES module

**Files:**
- Modify: `templates/tools.html`

- [ ] **Step 1: Fix script tags and switchNameTab buttons**

```html
<!-- Remove old onclick attributes from name tab buttons -->
<!-- Old: <button class="tab-btn active" onclick="switchNameTab('eval')"> -->
<!-- New: -->
<button class="tab-btn active" id="tab-btn-eval">评测名字</button>
<button class="tab-btn" id="tab-btn-gen">取名推荐</button>

<!-- Replace script tags -->
<!-- Old: <script src="/static/js/api.js?v=..."></script> -->
<!-- Old: <script src="/static/tools.js?v=..."></script> -->
<!-- New: -->
<script type="module" src="/static/tools.js?v=20260613a"></script>
```

### Task 15: Delete old CSS, verify

**Files:**
- Delete: `static/style.css`

- [ ] **Step 1: Remove old monolithic CSS**

```bash
rm F:/project/agent/static/style.css
```

- [ ] **Step 2: Verify all files compile/load**

Start the API server and open the browser:
```bash
cd F:/project/agent && python api_server.py
# Open http://localhost:8000 — verify:
# 1. Page loads without JS errors (check browser console)
# 2. 4-column layout renders correctly
# 3. Modal opens/closes
# 4. Chat input works
# 5. Tools page (/tools) loads and forms submit
# 6. Resize to 900px — verify 2×2 grid
# 7. Resize to 400px — verify single column + bottom nav
```

---

## Self-Review

1. **Spec coverage:** ES modules ✓, CSS split ✓, 1024px breakpoint ✓, 5 bugs (chart_id guard ✓, switchNameTab event ✓, XSS ✓, PersistenceSync warn ✓, dead code removal ✓)
2. **No placeholders:** All steps have exact code or exact extraction instructions
3. **Type consistency:** `renderBaziTable`/`renderZiweiTable` names match between render modules and ui.js imports. `_escHtml` exported from markdown.js, imported by ui.js + app.js.
