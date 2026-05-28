# 玄机子网站完善与上线 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将玄机子八字命理分析网站从"代码已完成"推进到"可运行、体验完整、移动端可用的产品状态"。

**Architecture:** 基于现有 FastAPI 后端 + 四栏 SPA 前端。修复流式 SSE 体验、动态报告标签、修正反馈机制和移动端适配。不新增依赖，不重构架构。

**Tech Stack:** FastAPI + Jinja2-free vanilla HTML + vanilla JS + CSS Grid + SSE streaming + sessionStorage

---

## File Structure

| 文件 | 操作 | 说明 |
|------|------|------|
| `api_server.py` | 微调 | 修复 SSE 事件格式，添加修正反馈端点 |
| `static/app.js` | 重写部分模块 | 流式渲染、动态标签、修正流程 |
| `static/style.css` | 增补 | 移动端适配、修正计数样式、流式光标 |
| `templates/index.html` | 微调 | 修正按钮、移动端导航 |
| `claude_api.py` | 微调 | 超时处理、重试逻辑 |

---

### Task 1: 启动验证——修复阻塞性启动问题

**Files:**
- Verify: `api_server.py`
- Verify: `claude_api.py`
- Verify: `bazi_calculator.py`

- [ ] **Step 1: 启动服务器**

```bash
python api_server.py &
sleep 3
curl -s http://localhost:8000/api/health
```

预期: `{"status":"ok","version":"1.0.0"}`

若启动失败，检查报错并修复。

- [ ] **Step 2: 测试排盘端点**

```bash
curl -s -X POST http://localhost:8000/api/chart \
  -H "Content-Type: application/json" \
  -d '{"year":1993,"month":7,"day":15,"hour":14,"gender":"male"}' | python -c "import sys,json; d=json.load(sys.stdin); print('chart_id:', d.get('chart_id','MISSING')); print('day_master:', d.get('day_master',{}).get('gan','MISSING')); print('pillars:', len(d.get('four_pillars',{})))"
```

预期: 输出 chart_id、day_master、4 柱。

- [ ] **Step 3: 测试前端三个页面加载**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ && echo " index"
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/tools && echo " tools"
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/test && echo " test"
```

预期: 全部 200。

- [ ] **Step 4: 检查浏览器 Console 报错**

打开 `http://localhost:8000/`，F12 打开 Console，刷新页面。修复所有红色报错（常见问题：`.hidden` class 缺失导致弹窗初始不可见，CSS 变量兼容性等）。

- [ ] **Step 5: 跑现有测试套件**

```bash
python -m pytest tests/test_api.py -v 2>&1 | tail -20
python tests/test_tools.py 2>&1 | tail -10
```

记录通过/失败数量。若有个别失败，在后续任务中修复。

- [ ] **Step 6: 处理 claude_api.py 的 urllib 超时设置**

在 `stream_chat` 的 `urllib.request.Request` 之前添加超时配置，防止 API 不可用时前端无限等待。修改 `claude_api.py:134`：

```python
# 在 req = urllib.request.Request(...) 之前
# 注意: urllib.request.urlopen 不支持 timeout 参数直接传入 Request
# 需要在 urlopen 调用时传入
```

将 `claude_api.py:143` 的 `urllib.request.urlopen(req)` 改为：

```python
urllib.request.urlopen(req, timeout=120)
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "fix: startup verification, add urllib timeout for claude_api"
```

---

### Task 2: 修复 SSE 流式 Typewriter 效果

**Files:**
- Modify: `static/app.js` — 重写 `apiChatStream` 和 `_startLoading/_finishLoading`

**问题:** 当前 `app.js:263-272` 的 `apiChatStream` 把 SSE 回复全部收集到 `_replyBuf`，`_finishLoading` 才一次性渲染。需要改为增量渲染——每个 SSE `reply` 事件立刻追加到对话气泡，每个 `report` 事件立刻更新右侧报告区。

- [ ] **Step 1: 重写 `apiChatStream`——支持增量回调**

替换 `static/app.js:263-272` 的 `apiChatStream` 函数：

```javascript
function apiChatStream(chartId, message, onReplyDelta, onReportDelta, onToolStart, onDone) {
    const params = new URLSearchParams({ chart_id: chartId, message: message });
    const es = new EventSource('/api/chat/stream?' + params);

    es.addEventListener('tool', function(e) {
        const data = JSON.parse(e.data);
        onToolStart(data.name);
    });

    es.addEventListener('reply', function(e) {
        const data = JSON.parse(e.data);
        onReplyDelta(data.text, data.tool || null);
    });

    es.addEventListener('report', function(e) {
        const data = JSON.parse(e.data);
        onReportDelta(data.text, data.tab || 'overview');
    });

    es.addEventListener('done', function(e) {
        const data = JSON.parse(e.data);
        onDone(data.corrections || 0);
        es.close();
    });

    es.addEventListener('error', function() {
        es.close();
        onDone(0);
    });
}
```

- [ ] **Step 2: 重写 `_startLoading` 和 `_finishLoading`——增量渲染**

替换 `static/app.js:440-462` 的 `_startLoading` / `_finishLoading` 和 `chat-send-btn` 的事件处理 `app.js:503-521`。

删除旧的 `_replyBuf`、`_reportBuf`、`_msgEl` 变量和 `_startLoading` / `_finishLoading` 函数（第440-462行）。

替换 chat-send 事件处理器（第503-521行）为：

```javascript
document.getElementById('chat-send-btn').addEventListener('click', function() {
    const inp = document.getElementById('chat-input');
    const text = inp.value.trim();
    if (!text) return;
    const cur = MingzhuManager.getCurrent();
    if (!cur) { addChatMsg('agent', '请先添加命主。'); return; }
    const prompt = _expandPrompt(text);
    addChatMsg('user', text);
    inp.value = '';

    // 状态初始化
    document.getElementById('report-status').classList.remove('done');
    document.getElementById('report-content').innerHTML =
        '<div class="report-loading"><div class="skeleton-line"></div><div class="skeleton-line w70"></div><div class="skeleton-line w50"></div></div>';

    // 创建可增量更新的回复气泡
    const c = document.getElementById('chat-messages');
    const w = c.querySelector('.chat-welcome');
    if (w) w.remove();
    const msgEl = document.createElement('div');
    msgEl.className = 'chat-msg agent';
    msgEl.innerHTML = '<div class="sender">玄机子</div><div class="bubble"><span class="loading-spin">⏳</span> 思考中…</div>';
    c.appendChild(msgEl);
    const bubble = msgEl.querySelector('.bubble');

    let replyText = '';
    let currentTool = null;
    let reportBuf = '';
    let currentTab = 'overview';
    const reportStatus = document.getElementById('report-status');
    const reportContent = document.getElementById('report-content');

    apiChatStream(cur.chart_id, prompt,
        // onReplyDelta — 逐字追加到对话气泡
        function(delta, tool) {
            if (tool) currentTool = tool;
            replyText += delta;
            // 清除加载动画，替换为实际文本
            bubble.innerHTML = replyText.replace(/\n/g, '<br>') + '<span class="streaming-cursor">▌</span>';
            if (c.scrollHeight - c.scrollTop - c.clientHeight < 50) {
                c.scrollTop = c.scrollHeight;
            }
        },
        // onReportDelta — 逐段更新右侧报告
        function(text, tab) {
            currentTab = tab;
            reportBuf = text; // report 事件传的是全量文本
            showReportStreaming(tab, reportBuf);
        },
        // onToolStart
        function(toolName) {
            currentTool = toolName;
            const sender = msgEl.querySelector('.sender');
            sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + toolName + '</span>';
            reportStatus.innerHTML = '⏳ 玄机子正在' + toolName + '…';
        },
        // onDone
        function(corrections) {
            // 移除流式光标
            bubble.innerHTML = replyText.replace(/\n/g, '<br>') || '分析完成，请查看右侧报告。';
            reportStatus.innerHTML = corrections > 0
                ? '<span class="correct-indicator">✅ 已纠正 ' + corrections + ' 处</span>'
                : '✅ 分析完成';
            document.getElementById('correct-count').textContent = corrections > 0 ? '✅ 已纠正' + corrections + '处' : '';
            document.getElementById('correct-count').classList.toggle('hidden', corrections === 0);
            if (reportBuf) {
                showReportFinal(currentTab, reportBuf);
            }
            // 更新 tool tag
            if (currentTool) {
                const sender = msgEl.querySelector('.sender');
                sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + currentTool + '</span>';
            }
        }
    );
});
```

- [ ] **Step 3: 添加 `showReportStreaming` 和 `showReportFinal` 函数**

在 `app.js` 中 `showReport` 函数附近添加两个新函数：

```javascript
function showReportStreaming(tab, content) {
    // 动态创建/激活 report tab
    ensureReportTab(tab);
    activateReportTab(tab);
    document.getElementById('report-content').innerHTML =
        renderMarkdown(content) + '<span class="streaming-cursor">▌</span>';
    document.getElementById('report-status').classList.remove('done');
}

function showReportFinal(tab, content) {
    ensureReportTab(tab);
    activateReportTab(tab);
    document.getElementById('report-content').innerHTML = renderMarkdown(content);
    document.getElementById('report-status').classList.add('done');
}

// 保留旧的 showReport 兼容其他调用
function showReport(content) {
    document.getElementById('report-content').innerHTML = renderMarkdown(content);
}
```

- [ ] **Step 4: 添加 `renderMarkdown` 辅助函数**

将 markdown 渲染逻辑从旧的 `showReport` 提取为独立函数：

```javascript
function renderMarkdown(md) {
    if (!md) return '';
    return md
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
        .replace(/\n\n/g, '<br><br>')
        .replace(/^\- (.+)$/gm, '<li>$1</li>');
}
```

- [ ] **Step 5: 修复 `_expandPrompt` 中的语法错误**

当前 `app.js:466-500` 中有一个模板字符串缺少闭合反引号的问题。检查并修复：

```javascript
function _expandPrompt(raw) {
    const kw = raw.replace(/\s/g, '');
    if (/^(报告|分析|帮我看看|看看|算|解读|详批|详测)$/.test(kw)) {
        return '请对此八字进行四合出（子平真诠+滴天髓+紫微斗数+盲派）综合分析，按以下12段结构输出完整报告：\n\n' +
            '## 一、八字排盘\n' +
            '## 二、共识结论（四派一致认定）\n' +
            '## 三、旺衰量化基准（得分表）\n' +
            '## 四、各派要点对比（表格）\n' +
            '## 五、各体系深度分析（子平/滴天髓/紫微/盲派各单独一节）\n' +
            '## 六、星平合参（八字←→紫微交叉验证）\n' +
            '## 七、分歧说明\n' +
            '## 八、应期共识（未来3年逐年预报）\n' +
            '## 九、纳音气质+五行补益\n' +
            '## 十、命理依据溯源\n' +
            '## 十一、命主画像（少年/青年/中年/晚年+当前大运+未来三年）\n' +
            '## 十二、免责声明\n\n' +
            '**输出要求**：\n' +
            '- 所有对比/统计类数据必须用 Markdown 表格\n' +
            '- 每张表格必须有表头行\n' +
            '- 评分用 ⭐ 视觉标记\n' +
            '- 每个判断给出理法依据和象法翻译\n' +
            '- 引用经典原文标注出处';
    }
    if (/^(财运|钱|发财|投资)/.test(kw)) {
        return '请对此八字的财运进行深度分析，包括：日主旺衰能否担财、财星是否得力、食伤能否生财、比劫是否夺财、大运流年财运走势、最佳求财方向和行业建议。';
    }
    if (/^(感情|婚姻|结婚|恋爱|桃花|夫妻)/.test(kw)) {
        return '请对此八字的婚姻感情进行深度分析，包括：配偶宫状态、财官星与日主关系、婚姻宫有无冲合刑害、紫微夫妻宫解读、大运流年感情走势、改善建议。';
    }
    if (/^(事业|工作|官运|升职|跳槽|创业)/.test(kw)) {
        return '请对此八字的事业官运进行深度分析，包括：官杀状态、印星配合、食伤制杀、格局层次、适合行业和岗位类型、大运流年事业走势。';
    }
    return raw;
}
```

- [ ] **Step 6: 验证流式效果**

启动服务器，在浏览器中：
1. 添加命主 → 排盘
2. 输入"报告"发送
3. 观察对话区是否逐字显示回复
4. 观察右侧报告区是否逐段更新
5. 确认 `▌` 闪烁光标在流式过程中可见，完成后消失

- [ ] **Step 7: Commit**

```bash
git add static/app.js
git commit -m "fix: SSE streaming typewriter effect — incremental reply/report rendering"
```

---

### Task 3: 动态报告标签系统

**Files:**
- Modify: `static/app.js`
- Modify: `static/style.css`

**目标:** 支持运行时动态新增报告标签（如"财运专题""婚姻专题""四合出"），各标签独立存储内容，用户可自由切换。

- [ ] **Step 1: 添加标签管理函数**

在 `app.js` 中添加：

```javascript
const ReportTabs = {
    _cache: {},     // { tabId: markdownContent }
    _active: 'overview',

    init() {
        this._cache = {};
        this._active = 'overview';
        this._renderTabs();
    },

    _renderTabs() {
        const container = document.getElementById('report-tabs');
        // 保留 correct-count 元素
        const correctEl = document.getElementById('correct-count');
        container.innerHTML = '';
        const tabNames = {
            'overview': '总览',
            'sihechu': '四合出',
            'wealth': '财运专题',
            'marriage': '感情专题',
            'career': '事业专题',
            'hehun': '合婚',
            'name': '取名',
            'health': '健康',
        };
        for (const [tabId, label] of Object.entries(tabNames)) {
            if (this._cache[tabId] !== undefined || tabId === 'overview') {
                const span = document.createElement('span');
                span.className = 'report-tab' + (tabId === this._active ? ' active' : '');
                span.dataset.tab = tabId;
                span.textContent = label;
                span.onclick = function() { ReportTabs.switchTo(tabId); };
                container.appendChild(span);
            }
        }
        if (correctEl) container.appendChild(correctEl);
    },

    set(tabId, content) {
        this._cache[tabId] = content;
        this._renderTabs();
    },

    switchTo(tabId) {
        this._active = tabId;
        this._renderTabs();
        const content = this._cache[tabId] || '';
        document.getElementById('report-content').innerHTML = renderMarkdown(content);
    },

    getActive() {
        return this._active;
    }
};
```

- [ ] **Step 2: 修改 `ensureReportTab` 和 `activateReportTab`**

```javascript
function ensureReportTab(tabId) {
    ReportTabs.set(tabId, ReportTabs._cache[tabId] || '');
}

function activateReportTab(tabId) {
    ReportTabs.switchTo(tabId);
}
```

- [ ] **Step 3: 修改流式回调中的 report 处理**

更新 Task 2 中的 `onReportDelta` 回调，确保流式过程中报告内容也被缓存：

更新 `showReportStreaming` 函数中，在渲染前先存储到缓存：

```javascript
function showReportStreaming(tab, content) {
    ReportTabs._cache[tab] = content;  // 缓存增量内容
    ReportTabs._active = tab;
    ReportTabs._renderTabs();
    document.getElementById('report-content').innerHTML =
        renderMarkdown(content) + '<span class="streaming-cursor">▌</span>';
    document.getElementById('report-status').classList.remove('done');
}

function showReportFinal(tab, content) {
    ReportTabs._cache[tab] = content;
    ReportTabs._active = tab;
    ReportTabs._renderTabs();
    document.getElementById('report-content').innerHTML = renderMarkdown(content);
    document.getElementById('report-status').classList.add('done');
}
```

- [ ] **Step 4: 点击已有标签切换时恢复内容**

修改 `switchTo` 确保点击标签时能从缓存恢复内容（已在 Step 1 中实现）。

- [ ] **Step 5: 初始化标签**

在 `app.js` 末尾的初始化代码中添加：

```javascript
// Init
refreshPanel();
ReportTabs.init();
```

- [ ] **Step 6: 修改合婚按钮的回调也使用 ReportTabs**

更新 `hehun-analyze-btn` 的事件处理（app.js:533-538），改为使用 `ReportTabs.set`：

```javascript
document.getElementById('hehun-analyze-btn').addEventListener('click', async function() {
    const p1 = document.getElementById('hehun-p1').value;
    const p2 = document.getElementById('hehun-p2').value;
    if (p1 === p2) { alert('请选择两个不同的命主'); return; }
    const r = await fetch('/api/tools/hehun', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chart_id1: p1, chart_id2: p2 })
    });
    if (r.ok) {
        const d = await r.json();
        let m = '# 合婚分析\n\n<div class="score-card"><div class="big">' + d.total + '分</div><div class="grade">' + d.grade + '</div></div>\n';
        for (const [k, v] of Object.entries(d.scores || {})) {
            m += '## ' + k + '\n' + (v.detail || '') + '\n\n';
        }
        ReportTabs.set('hehun', m);
        ReportTabs.switchTo('hehun');
    }
});
```

- [ ] **Step 7: 添加标签关闭按钮的 CSS**

在 `style.css` 末尾添加：

```css
.report-tab {
    position: relative;
    padding-right: 24px;
}
.report-tab .tab-close {
    position: absolute;
    right: 6px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 12px;
    cursor: pointer;
    color: var(--text-faint);
    line-height: 1;
}
.report-tab .tab-close:hover {
    color: var(--cinnabar);
}
```

- [ ] **Step 8: Commit**

```bash
git add static/app.js static/style.css
git commit -m "feat: dynamic report tabs with independent content caching"
```

---

### Task 4: 修正反馈机制

**Files:**
- Modify: `static/app.js`
- Modify: `templates/index.html`

**目标:** 用户可以在对话中指出报告错误，系统重新分析并更新对应章节，显示修正计数。

- [ ] **Step 1: 在 chat-input-row 中添加修正按钮**

修改 `templates/index.html:49-54` 的 input row：

```html
<div class="chat-input-row">
    <button id="hehun-toggle-btn" title="双人合婚">👥</button>
    <button id="add-mingzhu-btn" title="添加命主">＋</button>
    <button id="correct-btn" title="指正报告错误" style="display:none">🔧 指正</button>
    <input type="text" id="chat-input" placeholder="输入出生信息或问题…">
    <button id="chat-send-btn">发送</button>
</div>
```

- [ ] **Step 2: 添加指正按钮的 CSS**

```css
#correct-btn {
    background: var(--surface-dark);
    border: 1px solid var(--gold);
    color: var(--gold);
    font-size: 11px;
    font-weight: 500;
    padding: 8px 10px;
    border-radius: var(--radius);
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
}
#correct-btn:hover {
    background: var(--gold-light);
}
```

- [ ] **Step 3: 修正流程的 JS 逻辑**

在 `app.js` 中添加修正状态管理和处理函数：

```javascript
const CorrectionManager = {
    count: 0,

    reset() {
        this.count = 0;
        document.getElementById('correct-count').classList.add('hidden');
    },

    increment() {
        this.count++;
        const el = document.getElementById('correct-count');
        el.textContent = '✅ 已纠正 ' + this.count + ' 处';
        el.classList.remove('hidden');
    },

    // 用户点击指正按钮
    startCorrection() {
        const inp = document.getElementById('chat-input');
        inp.placeholder = '请描述哪里分析不对…';
        inp.focus();
        document.getElementById('correct-btn').style.display = 'none';
        document.getElementById('chat-send-btn').textContent = '指正';
        document.getElementById('chat-send-btn').style.background = 'var(--gold)';
        document.getElementById('chat-send-btn').style.color = 'var(--ink)';
        this._correcting = true;
    },

    endCorrection() {
        const inp = document.getElementById('chat-input');
        inp.placeholder = '输入出生信息或问题…';
        document.getElementById('chat-send-btn').textContent = '发送';
        document.getElementById('chat-send-btn').style.background = 'var(--cinnabar)';
        document.getElementById('chat-send-btn').style.color = '#fff';
        this._correcting = false;
    },

    isCorrecting() {
        return !!this._correcting;
    }
};
```

- [ ] **Step 4: 修改 chat-send 事件，支持指正模式**

在 `chat-send-btn` 的事件处理器中，开头添加指正模式检测：

```javascript
document.getElementById('chat-send-btn').addEventListener('click', function() {
    const inp = document.getElementById('chat-input');
    const text = inp.value.trim();
    if (!text) return;
    const cur = MingzhuManager.getCurrent();
    if (!cur) { addChatMsg('agent', '请先添加命主。'); return; }

    // 指正模式
    if (CorrectionManager.isCorrecting()) {
        CorrectionManager.endCorrection();
        addChatMsg('user', '🔧 指正：' + text);
        inp.value = '';
        // 构建指正 prompt——要求只修正对应章节
        const activeTab = ReportTabs.getActive();
        const prompt = '用户指出以下分析有误，请重新审视并修正报告中对应的章节（仅修正有误部分，保留其余内容不变）：\n\n用户反馈：' + text + '\n\n当前报告标签：' + activeTab;
        _sendWithStream(cur.chart_id, prompt, function() {
            CorrectionManager.increment();
        });
        return;
    }

    // 正常模式
    const prompt = _expandPrompt(text);
    addChatMsg('user', text);
    inp.value = '';
    _sendWithStream(cur.chart_id, prompt);
});
```

- [ ] **Step 5: 提取 `_sendWithStream` 公共函数**

将 chat-send 中启动流式的逻辑提取为独立函数，避免代码重复：

```javascript
function _sendWithStream(chartId, prompt, onSuccess) {
    document.getElementById('report-status').classList.remove('done');
    document.getElementById('report-content').innerHTML =
        '<div class="report-loading"><div class="skeleton-line"></div><div class="skeleton-line w70"></div><div class="skeleton-line w50"></div></div>';

    const c = document.getElementById('chat-messages');
    const msgEl = document.createElement('div');
    msgEl.className = 'chat-msg agent';
    msgEl.innerHTML = '<div class="sender">玄机子</div><div class="bubble"><span class="loading-spin">⏳</span> 思考中…</div>';
    c.appendChild(msgEl);
    const bubble = msgEl.querySelector('.bubble');

    let replyText = '';
    let currentTool = null;
    let reportBuf = '';
    let currentTab = 'overview';
    const reportStatus = document.getElementById('report-status');

    apiChatStream(chartId, prompt,
        function(delta, tool) {
            if (tool) currentTool = tool;
            replyText += delta;
            bubble.innerHTML = replyText.replace(/\n/g, '<br>') + '<span class="streaming-cursor">▌</span>';
            if (c.scrollHeight - c.scrollTop - c.clientHeight < 50) {
                c.scrollTop = c.scrollHeight;
            }
        },
        function(text, tab) {
            currentTab = tab;
            reportBuf = text;
            showReportStreaming(tab, reportBuf);
        },
        function(toolName) {
            currentTool = toolName;
            const sender = msgEl.querySelector('.sender');
            sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + toolName + '</span>';
            reportStatus.innerHTML = '⏳ 玄机子正在' + toolName + '…';
        },
        function(corrections) {
            bubble.innerHTML = replyText.replace(/\n/g, '<br>') || '分析完成，请查看右侧报告。';
            reportStatus.innerHTML = '✅ 分析完成';
            if (reportBuf) showReportFinal(currentTab, reportBuf);
            if (currentTool) {
                const sender = msgEl.querySelector('.sender');
                sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + currentTool + '</span>';
            }
            if (onSuccess) onSuccess();
        }
    );
}
```

- [ ] **Step 6: 报告生成完成后显示指正按钮**

在 `onDone` 回调末尾添加：

```javascript
document.getElementById('correct-btn').style.display = 'inline-block';
```

在 `_sendWithStream` 的 onDone 和 chat-send 原始回调中也添加。

- [ ] **Step 7: 点击指正按钮**

```javascript
document.getElementById('correct-btn').addEventListener('click', function() {
    CorrectionManager.startCorrection();
});
```

- [ ] **Step 8: Commit**

```bash
git add static/app.js templates/index.html static/style.css
git commit -m "feat: correction feedback loop — user corrections trigger targeted re-analysis"
```

---

### Task 5: Claude API 集成 + 错误处理

**Files:**
- Modify: `claude_api.py`
- Modify: `api_server.py`
- Modify: `static/app.js`

- [ ] **Step 1: 在 claude_api.py 中添加连接重试逻辑**

在 `stream_chat` 函数的 `try` 块中添加 retry wrapper：

```python
def stream_chat(chart_json: dict, user_message: str, conversation_history: list = None,
                api_key: str = "", model: str = ""):
    key = api_key or ANTHROPIC_API_KEY
    if not key:
        yield {"type": "error", "text": "未配置 ANTHROPIC_API_KEY。请在项目根目录创建 .anthropic_key 文件。\n\n获取方式: https://console.anthropic.com/"}
        return

    provider, url, default_model = _detect_provider(key)
    mdl = model or default_model
    system = _load_system_prompt()

    if provider == "anthropic":
        payload = _build_anthropic_payload(system, chart_json, user_message, mdl)
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        parser = _parse_anthropic_event
    else:
        payload = _build_deepseek_payload(system, chart_json, user_message, mdl)
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        parser = _parse_deepseek_event

    # 最多重试 2 次
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                buffer = b""
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith(b"data: "):
                            data_str = line[6:].decode("utf-8", errors="replace")
                            if data_str == "[DONE]":
                                return
                            try:
                                event = json.loads(data_str)
                                yield parser(event)
                            except json.JSONDecodeError:
                                continue
            return  # 成功，退出
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            if e.code == 429 and attempt == 0:
                import time
                time.sleep(2)
                continue
            yield {"type": "error", "text": f"API 错误 {e.code}: {body}"}
            return
        except (OSError, Exception) as e:
            if attempt == 0:
                import time
                time.sleep(1)
                continue
            yield {"type": "error", "text": f"连接错误: {str(e)[:300]}"}
            return
```

- [ ] **Step 2: 改进 api_server.py 中 SSE 端点的错误处理**

在 `/api/chat/stream` 的 `event_stream` 中增加 stop_reason 检查：

修改 `api_server.py:620-646`，在 text_delta 处理中添加 stop_reason 检查：

```python
if event.get('type') == 'text_delta':
    delta = event.get('text') or ''
    if not delta:
        continue
    reply_text += delta
    report_text += delta

    if not in_report and '#' in delta:
        in_report = True
        report_tab = '四合出'

    if not in_report:
        yield _sse_event('reply', {'text': delta})
    else:
        yield _sse_event('report', {'text': report_text, 'tab': report_tab})

elif event.get('type') == 'message_delta':
    stop_reason = event.get('stop_reason', '')
    if stop_reason == 'max_tokens':
        yield _sse_event('reply', {'text': '\n\n⚠️ 报告因长度限制被截断，可输入"继续"获取后续内容。'})
```

- [ ] **Step 3: 前端 API 不可用时的友好提示**

在 `apiChatStream` 的 `error` 事件处理中增加有意义的错误展示：

```javascript
es.addEventListener('error', function() {
    es.close();
    onReplyDelta('\n\n⚠️ AI 服务连接失败。请确认：\n1. 已在项目目录创建 .anthropic_key 文件\n2. API Key 有效且未过期\n3. 网络可访问 api.anthropic.com', null);
    onDone(0);
});
```

- [ ] **Step 4: 测试 API Key 未配置时的 fallback**

在浏览器中，不配置 `.anthropic_key`，输入"报告"发送，确认显示友好的配置提示，而非白屏或无限 loading。

- [ ] **Step 5: Commit**

```bash
git add claude_api.py api_server.py static/app.js
git commit -m "fix: Claude API retry logic, error UX, SSE error handling"
```

---

### Task 6: 移动端响应式优化

**Files:**
- Modify: `static/style.css`
- Modify: `templates/index.html`

**目标:** 在移动端（≤768px）提供可用的单栏布局，而非仅仅隐藏面板。

- [ ] **Step 1: 添加移动端底部导航栏**

在 `templates/index.html` 的 `</div>` (app-container) 之前添加：

```html
<!-- Mobile bottom nav -->
<nav class="mobile-nav" id="mobile-nav">
    <button class="mnav-btn active" data-panel="chat">💬 对话</button>
    <button class="mnav-btn" data-panel="chart">📊 命盘</button>
    <button class="mnav-btn" data-panel="report">📄 报告</button>
    <button class="mnav-btn" id="mnav-mingzhu">👤 命主</button>
</nav>
```

- [ ] **Step 2: 添加移动端导航 CSS**

在 `style.css` 末尾的 `@media` 块中替换为：

```css
/* ================================================================
   Mobile — Single column with bottom nav
   ================================================================ */
.mobile-nav {
    display: none;
}

@media (max-width: 768px) {
    .app-container {
        grid-template-columns: 1fr;
        grid-template-rows: 1fr auto;
    }

    /* 默认显示对话栏 */
    .mingzhu-panel { display: none; }
    .chart-column { display: none; }
    .report-column { display: none; }

    .mingzhu-panel.mobile-visible,
    .chart-column.mobile-visible,
    .report-column.mobile-visible {
        display: flex;
    }
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
        flex: 1;
        padding: 10px 4px;
        background: none;
        border: none;
        color: var(--text-faint);
        font-size: 12px;
        font-family: var(--font);
        cursor: pointer;
        transition: all 0.2s;
        border-bottom: 2px solid transparent;
    }

    .mnav-btn.active {
        color: var(--gold);
        border-bottom-color: var(--cinnabar);
    }

    /* 移动端弹窗全屏 */
    .modal-content {
        width: 100vw;
        max-width: 100vw;
        border-radius: var(--radius-lg) var(--radius-lg) 0 0;
        position: fixed;
        bottom: 0;
        left: 0;
        padding: 20px 16px;
    }

    /* 移动端小字体 */
    .report-content { padding: 14px; font-size: 13px; }
    .chat-messages { padding: 10px; }
    .chat-input-row { padding: 8px 10px; gap: 4px; }
    .chat-input-row input { font-size: 12px; padding: 8px 10px; }
    #chat-send-btn { padding: 8px 14px; font-size: 11px; }
    .report-tabs { padding: 8px; gap: 4px; overflow-x: auto; flex-wrap: nowrap; }
    .report-tab { font-size: 11px; padding: 5px 10px; white-space: nowrap; flex-shrink: 0; }

    /* 命盘在移动端的简化 */
    .bazi-container { padding: 12px 8px; }
    .pillar-gan, .pillar-zhi { font-size: 22px; padding: 4px 0; }
    .pillar-label { font-size: 13px; padding: 4px 0; }
    .pillar-shishen { font-size: 11px; }
    .pillar-canggan { font-size: 11px; height: auto; }
    .pillar-nayin { font-size: 11px; }
}
```

- [ ] **Step 3: 添加移动端导航 JS 逻辑**

在 `app.js` 末尾添加：

```javascript
// Mobile navigation
document.querySelectorAll('.mnav-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        const panel = this.dataset.panel;

        // Update active state
        document.querySelectorAll('.mnav-btn').forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');

        // Show/hide panels
        const chat = document.querySelector('.chat-column');
        const chart = document.querySelector('.chart-column');
        const report = document.querySelector('.report-column');
        const mingzhu = document.querySelector('.mingzhu-panel');

        [chat, chart, report, mingzhu].forEach(function(el) {
            el.classList.remove('mobile-visible', 'mobile-hidden');
        });

        if (panel === 'chat') {
            chat.classList.remove('mobile-hidden');
        } else if (panel === 'chart') {
            chat.classList.add('mobile-hidden');
            chart.classList.add('mobile-visible');
        } else if (panel === 'report') {
            chat.classList.add('mobile-hidden');
            report.classList.add('mobile-visible');
        } else if (panel === 'mingzhu') {
            chat.classList.add('mobile-hidden');
            mingzhu.classList.add('mobile-visible');
        }
    });
});
```

- [ ] **Step 4: 提交前验证移动端效果**

用浏览器 DevTools 切换到 375px 宽度（iPhone 尺寸）：
1. 确认底部导航栏出现
2. 默认显示对话区
3. 点击"命盘"可查看八字排盘
4. 点击"报告"可查看分析
5. 点击"命主"可管理命主列表
6. 弹窗占满屏幕宽度

- [ ] **Step 5: Commit**

```bash
git add static/style.css templates/index.html static/app.js
git commit -m "feat: mobile responsive layout with bottom tab navigation"
```

---

### Task 7: 端到端验证 + Bug 修复

**Files:**
- Verify: 所有已修改文件

- [ ] **Step 1: 跑完整测试套件**

```bash
python -m pytest tests/test_api.py -v 2>&1
python tests/test_tools.py 2>&1
```

记录结果，修复所有 FAIL。

- [ ] **Step 2: 手动浏览器端到端流程**

按以下流程完整走一遍：

1. 打开 `http://localhost:8000/`
2. 点击 + 添加命主 → 填写 1993-07-15 14:00 男 北京 → 排盘
3. 确认：命主面板出现卡片，中间八字+紫微盘正确渲染
4. 输入"报告"发送
5. 确认：流式 typewriter 效果，右侧报告区逐段出现
6. 输入"财运怎么样"发送
7. 确认：新增"财运专题"标签，可切换回"总览"
8. 点击"指正"按钮，输入"日主喜忌分析有误"→ 发送
9. 确认：修正计数更新
10. 添加第二个命主（女，1988-02-20 08:00）
11. 点击 👥 合婚 → 选两个命主 → 分析
12. 确认：新增"合婚"标签，显示评分卡
13. 浏览器切到 375px 宽度，走一遍移动端流程

- [ ] **Step 3: 修复手动测试中发现的 bug**

任何异常行为均需修复。记录修复内容。

- [ ] **Step 4: 最终检查清单**

- [ ] 三个页面均 200（/、/tools、/test）
- [ ] /api/health 返回 ok
- [ ] /api/chart POST 返回完整排盘 JSON
- [ ] /api/chat/stream SSE 流式正常
- [ ] CSS 无 404（F12 Network 面板确认）
- [ ] JS 无 Console 报错
- [ ] 移动端 375px 可正常使用
- [ ] 无 API Key 时友好提示

- [ ] **Step 5: 最终 Commit**

```bash
git add -A
git commit -m "chore: end-to-end verification, final bug fixes"
```

---

## 执行顺序

```
Task 1 (启动验证) → Task 2 (流式修复) → Task 3 (动态标签)
                                            ↓
Task 5 (API 集成) ← Task 4 (修正反馈) ←-------┘
       ↓
Task 6 (移动端) → Task 7 (端到端验证)
```
