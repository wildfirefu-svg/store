# Frontend Medium Refactor — Design Spec

**Date:** 2026-06-13
**Scope:** ES modules, CSS split, responsive fix, 5 JS bug fixes

---

## 1. Goals

1. Replace `window.*` globals with ES module `export`/`import`
2. Split monolithic 1056-line CSS into 3 focused files
3. Fix tablet breakpoint (768-1024px shows cramped 4-column grid)
4. Fix 5 known JS bugs (chart_id null, implicit event, XSS, silent sync fail, dead code)

**Non-goals:** No UI appearance changes, no PWA, no dark/light toggle, no framework introduction.

---

## 2. ES Module Migration

### 2.1 Module graph

```
app.js ──→ api.js, state.js, ui.js, stream.js
ui.js  ──→ state.js, api.js, markdown.js, render-bazi.js, render-ziwei.js
stream.js → api.js, ui.js, state.js
tools.js  → api.js (standalone page, no shared state)
```

All dependencies are acyclic. No circular imports.

### 2.2 File changes

Each `.js` file:
- Add `export` on every symbol currently assigned to `window.*`
- Add `import { ... } from './module.js'` for every consumed symbol
- Remove `window.X = X` assignments

`index.html`:
- Replace `<script src="...">` with `<script type="module" src="...">`
- Remove the load-order comment (order is now compiler-enforced)
- Keep `?v=` cache busters

`tools.html`:
- Same treatment for `tools.js` and `api.js`

### 2.3 Symbols exported per module

| Module | Exports |
|---|---|
| `api.js` | `API`, `apiCreateChart`, `apiChatStream` |
| `state.js` | `MingzhuManager`, `PersistenceSync`, `ChatHistory`, `CorrectionManager` |
| `ui.js` | `ReportTabs`, `addChatMsg`, `refreshPanel`, `switchMingzhu`, `deleteMingzhu`, `showModal`, `renderFullChart`, `showReportFinal`, `_escHtml` |
| `markdown.js` | `renderMarkdown` |
| `render-bazi.js` | `renderBaziTable` |
| `render-ziwei.js` | `renderZiweiTable` |
| `stream.js` | `_sendWithStream` |
| `app.js` | (entry point, no exports) |
| `tools.js` | (entry point, no exports) |

---

## 3. CSS Split

### 3.1 File layout

```
static/css/
  base.css           — :root variables, body, .app-container grid, @keyframes
  panels.css         — .mingzhu-panel, .chat-column, .chart-column, .report-column
  modal-mobile.css   — #add-mingzhu-modal, @media queries
```

### 3.2 base.css

```css
@import './panels.css';
@import './modal-mobile.css';

:root { /* 24 design tokens unchanged */ }
body { /* grain texture, font */ }
.app-container { /* CSS grid */ }
@keyframes pulse-dot { }
@keyframes cursor-blink { }
@keyframes skeleton-pulse { }
@keyframes spin { }
```

### 3.3 panels.css

All `.mingzhu-panel`, `.chat-column`, `.chart-column`, `.report-column` rules plus their children. No `@media` queries — those live in `modal-mobile.css`.

### 3.4 modal-mobile.css

`#add-mingzhu-modal` rules, `@media (max-width: 1024px)`, `@media (max-width: 768px)`, `.mobile-nav`, `.mobile-visible`, `.mobile-hidden`.

### 3.5 HTML change

Replace the single `<link rel="stylesheet" href="/static/style.css?v=...">` with:
```html
<link rel="stylesheet" href="/static/css/base.css?v=...">
```
Remove `style.css`.

---

## 4. Responsive Fix

### 4.1 New breakpoint: 1024px (tablet landscape)

```css
@media (max-width: 1024px) {
  .app-container {
    grid-template-columns: 40fr 60fr;
    grid-template-rows: 1fr 1fr;
  }
  .mingzhu-panel { grid-row: 1; grid-column: 1; }
  .chat-column   { grid-row: 1; grid-column: 2; }
  .chart-column  { grid-row: 2; grid-column: 1; }
  .report-column { grid-row: 2; grid-column: 2; }
}
```

At ≤768px the existing single-column + bottom-nav layout takes over (unchanged).

### 4.2 Tablet panel switching

On tablet (768-1024px), the 4 panels are tiled 2×2. The existing `.mobile-nav` bar remains hidden (it only shows at ≤768px). The user sees all 4 panels at once but at half height each.

---

## 5. Bug Fixes

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | `tools.js` | `chart_id=null` in sessionStorage causes API 400 | Add guard: `if (!chartId) { alert('请先从首页排盘后再使用此工具'); return; }` at each form submit handler |
| 2 | `tools.js` | `switchNameTab` uses implicit global `event` | Replace `onclick="switchNameTab('eval')"` with `addEventListener('click', ...)` |
| 3 | `app.js`, `tools.js` | User-provided text (names, messages) not XSS-escaped in some paths | Wrap with `_escHtml()` or `textContent` assignment |
| 4 | `state.js` | `PersistenceSync` catches all errors silently | Add `console.warn('同步失败，数据暂存本地，将在下次连接时重试', e)` in catch blocks |
| 5 | `api.js` | Dead commented-out `apiGenerateReport` | Remove lines 12-15 |

---

## 6. Verification

- All existing Playwright E2E tests pass
- Manual smoke test: create chart, chat, use tools, generate report
- No visual regression: screenshot diff against current state
- Tablet layout: verify at 900px width both panels visible, no horizontal scroll

---

## 7. Files Changed

| File | Change |
|---|---|
| `static/js/api.js` | +export, -window.X, -dead code |
| `static/js/state.js` | +export, +console.warn |
| `static/js/ui.js` | +export, +import |
| `static/js/markdown.js` | +export |
| `static/js/render-bazi.js` | +export |
| `static/js/render-ziwei.js` | +export |
| `static/js/stream.js` | +export, +import |
| `static/js/app.js` | +import, +XSS fix |
| `static/js/tools.js` | +import, +bug fixes 1-3 |
| `static/css/base.css` | NEW — :root, body, layout, animations |
| `static/css/panels.css` | NEW — 4 column panels |
| `static/css/modal-mobile.css` | NEW — modal, @media 1024+768 |
| `static/style.css` | DELETED |
| `templates/index.html` | `<script type="module">`, `<link>` to base.css |
| `templates/tools.html` | `<script type="module">`, `switchNameTab` onclick removal |
