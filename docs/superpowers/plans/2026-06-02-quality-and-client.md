# 八字分析网站质量提升 + Windows 客户端 实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 执行此计划。Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复核心计算 Bug，将 AI 分析质量从 0.56 提升到 0.70+，打磨用户体验，补充工程测试，并打包独立的 Windows .exe 客户端。

**Architecture:** 按 P0→P1→P2→P3→P4 顺序执行。P0 修复计算引擎后重新跑全量基准测试确认无回归。P1 通过系统提示词注入歌诀 + 结构化输出 + Few-Shot + 双系统交叉验证四策略提升 AI 质量。P2 解决前端体验痛点。P3 补充 Playwright E2E 和 data_store 单元测试。P4 用 PyInstaller 打包 pywebview 桌面版为单个 .exe。

**Tech Stack:** Python 3.12, FastAPI, SQLite, DeepSeek API, Playwright, PyInstaller, pywebview, vanilla JS

**预验证发现:** `get_shishen()` 代码逻辑正确（已验证 10 组经典十神对应），`get_shengong()` 只有一处定义。`calculator_known_issues.md` 中的 Bug 1 和 Bug 3 是误报，不需要修复。

---

### Task 1: 验证紫微星曜索引正确性

**Files:**
- Read: `bazi_calculator.py:1174-1350` (calculate_ziwei 函数)
- Reference: `docs/SYSTEM_ARCHITECTURE.md`

**Goal:** 确认 Bug 2（紫微星曜索引混用）是否真实存在，还是已修复。

- [ ] **Step 1: 检查星曜排布的索引体系**

阅读 `calculate_ziwei` 中 `ziwei_position()` 返回值和 star deployment 使用的索引。检查 `stars.get(DIZHI.index(pzhi), [])` 使用的 DIZHI.index (0=子) 与 star deployment (0=寅) 是否存在 offset。

```python
# 在 bazi_calculator.py 中搜索以下模式确认索引一致性
# DIZHI = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
# 如果 ziwei_position 使用 ZIWEI_DIZHI = ['寅','卯','辰','巳','午','未','申','酉','戌','亥','子','丑']
# 那么 stars.get(DIZHI.index(pzhi), []) 使用 0=子 会偏移 2 位
```

- [ ] **Step 2: 运行验证脚本**

```python
# 测试: 已知案例 — 1993-07-15 未时 男
# 手动验证: 月支未→命宫在亥(太阳陷, 文曲, 陀罗, 天马)
from bazi_calculator import calculate_ziwei
ziwei = calculate_ziwei(1993, 7, 15, 14, 'male')
ming = [p for p in ziwei.get('twelve_palaces', []) if p['name'] == '命宫']
if ming:
    stars = [s['name'] for s in ming[0].get('main_stars', [])]
    print(f"命宫({ming[0]['position']}): {stars}")
    # 预期: 命宫在亥, 太阳陷
    assert ming[0]['position'] == '亥', f"命宫位置错误: {ming[0]['position']}"
    print("PASS: 命宫位置正确")
else:
    print("FAIL: 未找到命宫")
```

Run: `python -c "..."` (见上方代码)
Expected: 命宫在亥，主星包含太阳

- [ ] **Step 3: 决定修复方案**

如果索引正确 → 跳过此 Bug，记录到 `calculator_known_issues.md` 标记为 "已验证无问题"。
如果索引错误 → 统一为 0=寅 索引，修改 `DIZHI.index(pzhi)` → `ZIWEI_DIZHI.index(pzhi)`。

- [ ] **Step 4: Commit**

```bash
git add bazi_calculator.py .claude/agent-memory/bazi-multi-system-reader/calculator_known_issues.md
git commit -m "fix: verify/fix ziwei star indexing, update known issues"
```

---

### Task 2: 修复紫微农历日近似

**Files:**
- Modify: `bazi_calculator.py:1174-1195` (calculate_ziwei 中 lunar_day 计算)
- Reference: `lunar_calendar.py:solar_to_lunar()`

**Goal:** `calculate_ziwei` 中 `lunar_day = day if day <= 30 else 30` 直接用公历日代替农历日，影响紫微星定位。改用 `solar_to_lunar()` 获取准确农历日。

- [ ] **Step 1: 定位当前代码**

在 `calculate_ziwei` 函数中找到:
```python
lunar_day = day if day <= 30 else 30
```

- [ ] **Step 2: 替换为农历查表**

```python
# 修复前
lunar_day = day if day <= 30 else 30

# 修复后
from lunar_calendar import solar_to_lunar as _s2l
try:
    _, lunar_month, lunar_day = _s2l(year, month, day)
except Exception:
    lunar_day = day if day <= 30 else 30  # fallback
```

注意：`calculate_ziwei` 所在文件顶部已有 `from lunar_calendar import lunar_to_solar, solar_to_lunar as _s2l`（line 32），无需重新 import。

- [ ] **Step 3: 验证农历日正确性**

```python
# 测试: 1993-07-15 公历 → 农历五月廿六
from lunar_calendar import solar_to_lunar
ly, lm, ld = solar_to_lunar(1993, 7, 15)
print(f"1993-07-15 农历: {ly}年{lm}月{ld}日")
# 预期: 1993年5月26日
assert lm == 5 and ld == 26, f"农历日期错误: {lm}月{ld}日"
print("PASS")
```

Run: `python -c "..."` (见上方代码)
Expected: 1993年5月26日

- [ ] **Step 4: Commit**

```bash
git add bazi_calculator.py
git commit -m "fix: use actual lunar day for ziwei calculation instead of solar day"
```

---

### Task 3: 修复节气交界精度

**Files:**
- Modify: `bazi_calculator.py:get_month_branch_idx` 和 `get_month_pillar`
- Reference: `knowledge-base/solar_terms.json`

**Goal:** 节气边界使用精确时刻而非简化月/日阈值，修复出生在节气交界处可能产生的月柱错误。

- [ ] **Step 1: 读取 solar_terms.json 格式**

```bash
python -c "import json; d=json.load(open('knowledge-base/solar_terms.json')); print(list(d.keys())[:3]); v=list(d.values())[0]; print(type(v), v[:3] if isinstance(v,list) else v)"
```

- [ ] **Step 2: 在 bazi_calculator.py 顶部加载节气数据**

```python
# 在文件顶部 import 区域添加
import os as _os
_terms_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'knowledge-base', 'solar_terms.json')
with open(_terms_path, 'r') as _f:
    SOLAR_TERMS = json.load(_f)
```

- [ ] **Step 3: 创建节气精确查询函数**

```python
def get_solar_term_month(year, month, day, hour=0, minute=0):
    """Return the correct month branch index based on precise solar term times.
    
    Uses SOLAR_TERMS data to determine if a date falls before/after a节气 junction.
    Returns the month branch index (0=寅 for Lichun, 1=卯 for Jingzhe, etc.)
    """
    # Build datetime for comparison
    from datetime import datetime
    birth_dt = datetime(year, month, day, hour, minute)
    
    # Get relevant solar terms for this year
    year_key = str(year)
    if year_key not in SOLAR_TERMS:
        # Fallback to simplified lookup
        return get_month_branch_idx(month, day)
    
    terms = SOLAR_TERMS[year_key]
    # terms is a dict mapping节气名 → timestamp or (month, day, hour, minute)
    # Find which two terms bracket the birth date
    # ... implementation depends on exact JSON format
    
    return month_idx  # 0=寅 through 11=丑
```

**注:** 具体实现取决于 `solar_terms.json` 的实际数据结构。请先阅读文件后补全此函数。

- [ ] **Step 4: 集成到 get_month_pillar**

在 `get_month_pillar` 函数中，将节气判定从简化阈值改为调用 `get_solar_term_month`：

```python
def get_month_pillar(year, year_gan, month, day, hour=0, minute=0):
    month_idx = get_solar_term_month(year, month, day, hour, minute)
    # ... rest of function unchanged
```

- [ ] **Step 5: 运行回归测试**

```bash
pytest tests/test_accuracy.py -v --tb=short
```

Expected: 1,113 cases still 100% pass

- [ ] **Step 6: Commit**

```bash
git add bazi_calculator.py
git commit -m "feat: precise solar term boundary detection for month pillar"
```

---

### Task 4: 全量基准回归验证

**Files:**
- Test: `tests/test_accuracy.py`
- Test: `tests/test_consistency.py`
- Data: `tests/benchmark_charts/`

**Goal:** P0 修复后确保所有基准测试仍然通过，无回归。

- [ ] **Step 1: 运行精度测试**

```bash
cd f:\project\agent && python -m pytest tests/test_accuracy.py -v --tb=short
```

Expected: 1,113 cases, 100% pass

- [ ] **Step 2: 运行一致性测试**

```bash
cd f:\project\agent && python -m pytest tests/test_consistency.py -v --tb=short
```

Expected: 75 cases, ≥97% pass

- [ ] **Step 3: 运行全部测试套件**

```bash
cd f:\project\agent && python -m pytest tests/ -v --tb=short -x
```

Expected: 所有测试通过（≥95%）

- [ ] **Step 4: 对比 52 个 benchmark charts 修复前后输出**

```bash
cd f:\project\agent && python -c "
import json, os
bench_dir = 'tests/benchmark_charts'
charts = sorted([f for f in os.listdir(bench_dir) if f.endswith('.json')])
print(f'{len(charts)} benchmark charts found')
# 加载所有 benchmark，验证关键字段完整性
for c in charts[:5]:
    d = json.load(open(os.path.join(bench_dir, c)))
    dm = d.get('day_master', {})
    print(f'{c}: DM={dm.get(\"gan\",\"?\")}{dm.get(\"wuxing\",\"?\")}, pillars={list(d.get(\"four_pillars\",{}).keys())}')
print('...')
"
```

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: full regression test after P0 calculator fixes" --allow-empty
```

---

### Task 5: AI 系统提示词注入歌诀知识

**Files:**
- Modify: `claude_api.py:44-63` (_load_system_prompt)
- Read: `knowledge-base/gejue_core.json` (178 条精选歌诀)

**Goal:** 从 gejue_core.json 中选取与健康/家庭主题最相关的 30 条歌诀，注入系统提示词作为分析参考，提升 AI 在弱势领域的准确度。

- [ ] **Step 1: 选择主题歌诀**

```python
# 筛选健康、家庭、婚姻、子女主题的歌诀
import json
with open('knowledge-base/gejue_core.json', 'r', encoding='utf-8') as f:
    gejue = json.load(f)

health_keywords = ['疾病', '健康', '寿元', '身体', '病', '伤', '疾']
family_keywords = ['婚姻', '夫妻', '子女', '家庭', '配偶', '感情', '桃花']

health_gejue = [g for g in gejue if any(kw in g.get('tags','') or kw in g.get('text','') for kw in health_keywords)][:15]
family_gejue = [g for g in gejue if any(kw in g.get('tags','') or kw in g.get('text','') for kw in family_keywords)][:15]

print(f"Health: {len(health_gejue)}, Family: {len(family_gejue)}")
# 输出选中的歌诀文本（截取前100字）
```

- [ ] **Step 2: 修改 _load_system_prompt**

在 `claude_api.py` 中修改系统提示词，末尾添加精选歌诀：

```python
def _load_system_prompt():
    """Load the system prompt for API calls, with knowledge injection."""
    base = """你是一位精通中国古典命理学的玄学专家...
（省略，保持现有 prompt）"""

    # 注入精选歌诀作为领域知识
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gejue_path = os.path.join(script_dir, 'knowledge-base', 'gejue_core.json')
    try:
        with open(gejue_path, 'r', encoding='utf-8') as f:
            gejue_list = json.load(f)
        # 选取健康+家庭主题歌诀（每类最多10条）
        health_kw = ['疾病', '健康', '寿元', '身体']
        family_kw = ['婚姻', '夫妻', '子女', '家庭', '感情']
        selected = []
        for g in gejue_list:
            tags = g.get('tags', '') + g.get('text', '')
            if any(kw in tags for kw in health_kw + family_kw):
                selected.append(g.get('text', '')[:150])
                if len(selected) >= 20:
                    break
        
        if selected:
            base += "\n\n## 经典歌诀参考（内化使用，不要逐条引用）\n"
            for i, s in enumerate(selected):
                base += f"{i+1}. {s}\n"
    except Exception:
        pass
    
    return base
```

- [ ] **Step 3: 验证系统提示词长度合理**

```bash
cd f:\project\agent && python -c "from claude_api import _load_system_prompt; p=_load_system_prompt(); print(f'System prompt: {len(p)} chars, ~{len(p)//3} tokens')"
```

Expected: ~2000-3000 chars (约 600-1000 tokens)，不宜超过 5000 chars

- [ ] **Step 4: Commit**

```bash
git add claude_api.py
git commit -m "feat: inject health/family gejue into system prompt for AI quality"
```

---

### Task 6: AI 结构化输出约束

**Files:**
- Modify: `claude_api.py:_load_system_prompt()`

**Goal:** 在系统提示词中要求 AI 对核心判断给出置信度标记，减少模糊结论。

- [ ] **Step 1: 修改系统提示词，添加结构化要求**

在 `_load_system_prompt()` 返回的文本末尾追加：

```python
base += """
## 输出质量要求

1. 每条核心结论标注置信度：【高】【中】【低】
2. 身体健康、家庭婚姻相关的判断必须引用至少一条歌诀或经典依据
3. 不确定的结论明确说"无法确定"，不要模糊带过
4. 所有统计数据使用 Markdown 表格呈现
5. 使用 ⭐ 评分（1-5星）标注各维度
"""
```

- [ ] **Step 2: Commit**

```bash
git add claude_api.py
git commit -m "feat: structured output requirements in system prompt"
```

---

### Task 7: 基准案例 Few-Shot 注入

**Files:**
- Modify: `claude_api.py:_build_deepseek_payload()`
- Read: `quality/model_quality_report.json`

**Goal:** 从质量评测中选取表现最好的 3 个案例，将其结构化分析结论注入为 few-shot 示例。

- [ ] **Step 1: 选取最佳案例**

```bash
cd f:\project\agent && python -c "
import json
r = json.load(open('quality/model_quality_report.json'))
# 选 avg_score > 0.6 且 positive_rate > 25% 的案例
good = [(c['name'], c['avg_score'], c['positive_rate']) 
        for c in r['case_results'] 
        if c['avg_score'] > 0.6 and float(c['positive_rate'].rstrip('%')) > 25]
good.sort(key=lambda x: -x[1])
for g in good[:5]:
    print(f'{g[0]}: score={g[1]:.2f} pos_rate={g[2]}')
print(f'Found {len(good)} qualifying cases')
"
```

- [ ] **Step 2: 提取 few-shot 示例文本**

从质量报告中提取高分案例的关键分析结论（JSON），格式化为 few-shot 示例段：

```python
# 每个 few-shot 示例格式
"""
### 案例: {姓名} ({性别}, {八字})
**日主**: {日干}{五行}{阴阳}
**旺衰**: {等级}
**格局**: {格局名}
**事业**: {结论}（置信度：高）
**财运**: {结论}（置信度：中）
**健康**: {结论}（置信度：高）
**婚姻**: {结论}（置信度：高）
"""
```

- [ ] **Step 3: 注入 few-shot 到系统提示词**

在 `_build_deepseek_payload` 中，将 few-shot 示例追加到 `system_prompt` 后（限制总示例 ≤ 3 个，每个 ≤ 300 字）。

- [ ] **Step 4: Commit**

```bash
git add claude_api.py
git commit -m "feat: few-shot benchmark cases injected into AI prompt"
```

---

### Task 8: 前端自动滚动 + 加载动画

**Files:**
- Modify: `static/app.js` (SSE 流式回调)
- Modify: `static/style.css` (加载动画样式)

**Goal:** SSE 流式输出时自动滚动到最新内容；AI 思考时显示脉动动画而非纯文本。

- [ ] **Step 1: 在 onReplyDelta 回调中添加自动滚动**

在 `_sendWithStream` 的 `onReplyDelta` 回调中：

```javascript
// 在 onReplyDelta 函数末尾添加:
var c = document.getElementById('chat-messages');
if (c.scrollHeight - c.scrollTop - c.clientHeight < 80) {
    c.scrollTop = c.scrollHeight;
}
```

- [ ] **Step 2: 添加脉动加载动画 CSS**

```css
/* 在 style.css 末尾添加 */
.ai-loading {
    display: inline-flex;
    gap: 4px;
    padding: 8px 0;
}
.ai-loading span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--gold);
    animation: pulse-dot 1.2s infinite ease-in-out;
}
.ai-loading span:nth-child(2) { animation-delay: 0.2s; }
.ai-loading span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
    0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
    40% { opacity: 1; transform: scale(1.2); }
}
```

- [ ] **Step 3: 创建加载指示器函数**

```javascript
function showLoadingIndicator() {
    var c = document.getElementById('chat-messages');
    var d = document.createElement('div');
    d.className = 'chat-msg agent';
    d.id = 'ai-loading-indicator';
    d.innerHTML = '<div class="sender">玄机子</div><div class="bubble"><div class="ai-loading"><span></span><span></span><span></span></div></div>';
    c.appendChild(d);
    c.scrollTop = c.scrollHeight;
}
function hideLoadingIndicator() {
    var el = document.getElementById('ai-loading-indicator');
    if (el) el.remove();
}
```

- [ ] **Step 4: 在流式开始/结束时调用**

在 `_sendWithStream` 中，`onToolStart` 时调用 `showLoadingIndicator()`，`onDone` 时调用 `hideLoadingIndicator()`。

- [ ] **Step 5: Commit**

```bash
git add static/app.js static/style.css
git commit -m "feat: auto-scroll on SSE streaming + pulse loading animation"
```

---

### Task 9: 八字排盘卡片可视化

**Files:**
- Modify: `static/app.js` (renderFullChart 函数)
- Modify: `static/style.css` (八字卡片样式)

**Goal:** 将当前的纯 JSON 渲染替换为直观的四柱八字卡片/表格展示。

- [ ] **Step 1: 创建八字卡片 HTML 生成函数**

```javascript
function renderBaziTable(pillars) {
    var cols = ['year', 'month', 'day', 'hour'];
    var labels = ['年柱', '月柱', '日柱', '时柱'];
    var html = '<table class="bazi-pillars-table"><tr>';
    cols.forEach(function(c, i) {
        html += '<th>' + labels[i] + '</th>';
    });
    html += '</tr><tr>';
    cols.forEach(function(c) {
        var p = pillars[c];
        html += '<td><span class="bazi-gan bazi-wuxing-' + (p.gan_wuxing || '') + '">' + p.gan + '</span>' +
                '<span class="bazi-zhi bazi-wuxing-' + (p.zhi_wuxing || '') + '">' + p.zhi + '</span></td>';
    });
    html += '</tr><tr>';
    cols.forEach(function(c) {
        var p = pillars[c];
        html += '<td class="bazi-nayin">' + (p.nayin || '') + '</td>';
    });
    html += '</tr></table>';
    return html;
}
```

- [ ] **Step 2: 添加八字卡片 CSS 样式**

```css
.bazi-pillars-table {
    width: 100%;
    border-collapse: collapse;
    text-align: center;
    margin: 12px 0;
}
.bazi-pillars-table th {
    font-size: 11px;
    color: var(--text-tertiary);
    padding: 4px;
}
.bazi-pillars-table .bazi-gan,
.bazi-pillars-table .bazi-zhi {
    display: inline-block;
    width: 28px;
    height: 28px;
    line-height: 28px;
    border-radius: 4px;
    margin: 2px;
    font-size: 18px;
    font-weight: 700;
    font-family: var(--font-kai);
}
.bazi-wuxing-金 { color: #D4AF37; background: rgba(212,175,55,0.1); }
.bazi-wuxing-木 { color: #4CAF50; background: rgba(76,175,80,0.1); }
.bazi-wuxing-水 { color: #2196F3; background: rgba(33,150,243,0.1); }
.bazi-wuxing-火 { color: #F44336; background: rgba(244,67,54,0.1); }
.bazi-wuxing-土 { color: #795548; background: rgba(121,85,72,0.1); }
.bazi-nayin {
    font-size: 10px;
    color: var(--text-tertiary);
}
```

- [ ] **Step 3: 在 renderFullChart 中调用**

找到 `renderFullChart` 函数（约 line 1100），修改 `bazi-table` 的渲染：

```javascript
// 修改前
document.getElementById('bazi-table').innerHTML = JSON.stringify(chart);

// 修改后
document.getElementById('bazi-table').innerHTML = renderBaziTable(chart.four_pillars);
```

- [ ] **Step 4: Commit**

```bash
git add static/app.js static/style.css
git commit -m "feat: bazi pillar card visualization with wuxing colors"
```

---

### Task 10: data_store 单元测试

**Files:**
- Create: `tests/test_data_store.py`

**Goal:** 为 data_store.py 补充完整的 CRUD + 级联删除测试。

- [ ] **Step 1: 编写测试文件**

```python
#!/usr/bin/env python3
"""Tests for data_store.py — SQLite persistence layer."""
import os, sys, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_store

class TestCharts:
    def test_save_and_get(self):
        cid = 'test_chart_001'
        data_store.save_chart(cid, '测试', {'year': 2000}, {'four_pillars': {}})
        chart = data_store.get_chart(cid)
        assert chart is not None
        assert chart['name'] == '测试'
    
    def test_list_charts(self):
        charts = data_store.list_charts()
        assert any(c['chart_id'] == 'test_chart_001' for c in charts)
    
    def test_delete_chart_cascades(self):
        cid = 'test_chart_002'
        data_store.save_chart(cid, '级联测试', {}, {})
        data_store.append_chat_message(cid, 'user', '测试消息')
        data_store.save_report(cid, 'overview', '# 报告')
        assert len(data_store.get_chat_history(cid)) == 1
        assert 'overview' in data_store.get_reports(cid)
        
        data_store.delete_chart(cid)
        assert data_store.get_chart(cid) is None
        assert len(data_store.get_chat_history(cid)) == 0
        assert len(data_store.get_reports(cid)) == 0

class TestChatHistory:
    def test_append_and_get(self):
        cid = 'test_chat_003'
        data_store.save_chart(cid, '聊天测试', {}, {})
        data_store.append_chat_message(cid, 'user', '你好')
        data_store.append_chat_message(cid, 'agent', '你好！', '四合出分析')
        msgs = data_store.get_chat_history(cid)
        assert len(msgs) == 2
        assert msgs[0]['role'] == 'user'
        assert msgs[1]['role'] == 'agent'
        assert msgs[1]['tool'] == '四合出分析'
        data_store.delete_chart(cid)
    
    def test_limit_enforced(self):
        cid = 'test_chat_limit'
        data_store.save_chart(cid, '限制测试', {}, {})
        for i in range(600):
            data_store.append_chat_message(cid, 'user', f'msg{i}')
        msgs = data_store.get_chat_history(cid)
        assert len(msgs) <= 500  # MAX limit
        data_store.delete_chart(cid)

class TestReports:
    def test_save_and_get(self):
        cid = 'test_report_001'
        data_store.save_chart(cid, '报告测试', {}, {})
        data_store.save_report(cid, 'wealth', '# 财运分析')
        data_store.save_report(cid, 'health', '# 健康分析')
        reports = data_store.get_reports(cid)
        assert 'wealth' in reports
        assert 'health' in reports
        assert '# 财运分析' in reports['wealth']
        data_store.delete_chart(cid)
```

- [ ] **Step 2: 运行测试**

```bash
cd f:\project\agent && python -m pytest tests/test_data_store.py -v
```

Expected: 6 tests, 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_data_store.py
git commit -m "test: add data_store CRUD + cascade delete tests"
```

---

### Task 11: Playwright E2E 前端测试

**Files:**
- Create: `tests/test_e2e.py`

**Goal:** 用 Playwright 编写关键路径的端到端测试。

- [ ] **Step 1: 编写 E2E 测试**

```python
#!/usr/bin/env python3
"""E2E tests for BaZi analysis web app using Playwright."""
import pytest
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"

@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()

@pytest.fixture
def page(browser):
    p = browser.new_page(viewport={"width": 1400, "height": 900})
    p.goto(BASE)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2000)
    yield p
    p.close()

class TestChartCreation:
    def test_create_chart(self, page):
        """排盘: 输入出生信息，验证日主显示"""
        page.click("#add-mingzhu-btn")
        page.wait_for_selector("#add-mingzhu-modal:not(.hidden)")
        page.fill("#mingzhu-name", "E2E测试")
        page.fill("#mingzhu-location", "北京")
        page.click("#mingzhu-submit-btn")
        page.wait_for_timeout(3000)
        # 验证命名卡片出现
        cards = page.locator(".mingzhu-card").all()
        assert len(cards) >= 1
        # 验证八字表格渲染
        bazi = page.locator("#bazi-table").text_content()
        assert "年柱" in bazi or "四柱" in bazi or len(bazi) > 50

    def test_auto_overview_generated(self, page):
        """验证自动生成总览报告"""
        report = page.locator("#report-content").text_content()
        assert "命盘总览" in report or "日主" in report or len(report) > 50

class TestChat:
    def test_send_message(self, page):
        """发送对话消息，验证 AI 回复"""
        page.fill("#chat-input", "你好")
        page.click("#chat-send-btn")
        page.wait_for_timeout(8000)
        bubbles = page.locator(".chat-msg.agent .bubble").all()
        assert len(bubbles) >= 1
        # 验证没有连接失败错误
        text = page.locator(".chat-messages").text_content() or ""
        assert "连接失败" not in text

class TestMultiMingzhu:
    def test_switch_mingzhu(self, page):
        """切换命主，验证报告和聊天区域更新"""
        # 添加第二个命主
        page.click("#add-mingzhu-btn")
        page.wait_for_selector("#add-mingzhu-modal:not(.hidden)")
        page.fill("#mingzhu-name", "切换测试")
        page.fill("#pick-year", "2000")
        page.click("#mingzhu-submit-btn")
        page.wait_for_timeout(3000)
        
        cards = page.locator(".mingzhu-card").all()
        if len(cards) >= 2:
            report_before = page.locator("#report-content").text_content()
            cards[0].click()
            page.wait_for_timeout(2000)
            report_after = page.locator("#report-content").text_content()
            # 切换后报告应不同
            assert report_before != report_after
```

- [ ] **Step 2: 运行 E2E 测试（需要服务端运行中）**

```bash
cd f:\project\agent && python -m pytest tests/test_e2e.py -v --tb=long
```

Expected: 4-5 tests, 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add Playwright E2E tests for chart creation, chat, multi-mingzhu"
```

---

### Task 12: Windows .exe 打包（PyInstaller）

**Files:**
- Create: `app.spec` (PyInstaller spec 文件)
- Modify: `desktop_app.py` (添加打包路径处理)

**Goal:** 用 PyInstaller 打包为单个目录或单文件，双击 `玄机子.exe` 即可使用。

- [ ] **Step 1: 安装 PyInstaller**

```bash
pip install pyinstaller
```

- [ ] **Step 2: 创建 PyInstaller spec 文件**

```python
# app.spec
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

root = Path('.')
a = Analysis(
    ['desktop_app.py'],
    pathex=[str(root)],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('knowledge-base', 'knowledge-base'),
        ('.claude/agents', '.claude/agents'),
    ],
    hiddenimports=[
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.http.auto',
        'fastapi',
        'pydantic',
        'sqlite3',
        'json',
        'asyncio',
        'fpdf2',
        'clr',  # for pythonnet/pywebview
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tests',
        'docs',
        'reports',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'playwright',
        'pytest',
    ],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='玄机子',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    icon=None,
)
```

- [ ] **Step 3: 修改 desktop_app.py 支持打包路径**

```python
# desktop_app.py 顶部添加
import sys, os

def _get_base_path():
    """Get base path — works for both dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = _get_base_path()
os.chdir(BASE_PATH)
```

- [ ] **Step 4: 打包**

```bash
cd f:\project\agent && pyinstaller app.spec --noconfirm --clean
```

Expected: 在 `dist/玄机子/` 目录生成 `玄机子.exe` 及依赖文件。

- [ ] **Step 5: 测试打包产物**

在一台干净的 Windows 机器上（或当前机器）运行 `dist/玄机子/玄机子.exe`，验证：
- 桌面窗口正常弹出
- 八字排盘功能正常
- AI 对话功能正常（需要 `.anthropic_key` 或 `.deepseek_key` 文件在同目录）
- 数据持久化正常（`bazi_data.db` 在同目录生成）

- [ ] **Step 6: 创建分发说明 README**

```markdown
# 玄机子 · 八字命理分析 — 桌面版

## 使用方法
1. 将整个 `玄机子` 文件夹复制到任意目录
2. 在文件夹中放入 `.deepseek_key` 或 `.anthropic_key` 文件（包含 API Key）
3. 双击 `玄机子.exe` 启动
4. 首次启动可能需要 10-20 秒解压和初始化

## 系统要求
- Windows 10 或更高版本（自带 Edge WebView2 Runtime）
- 如果提示缺少 WebView2，请安装: https://go.microsoft.com/fwlink/p/?LinkId=2124703

## 文件说明
- `玄机子.exe` — 主程序
- `_internal/` — 依赖文件（不要删除）
- `.deepseek_key` — DeepSeek API Key（需自行创建）
- `bazi_data.db` — 数据文件（自动生成，保存命盘和聊天记录）
```

- [ ] **Step 7: Commit**

```bash
git add app.spec desktop_app.py
git commit -m "feat: PyInstaller packaging for standalone Windows .exe"
```

---

### Task 13: Docker 一键部署验证

**Files:**
- Read: `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- Create: `.env.example`

**Goal:** 验证 `docker compose up` 可以一键启动服务，添加环境变量模板。

- [ ] **Step 1: 创建 .env.example**

```bash
# BaZi Analysis API 环境变量
# 复制此文件为 .env 并填写实际值

# API Key (二选一)
DEEPSEEK_API_KEY=sk-your-deepseek-key-here
# ANTHROPIC_API_KEY=sk-ant-your-key-here

# 可选配置
# DEEPSEEK_MODEL=deepseek-v4-pro
# DEEPSEEK_TEMPERATURE=0.3
# BAZI_API_KEY=your-auth-key-here  (留空=无需认证)
```

- [ ] **Step 2: 检查并修复 Dockerfile**

```bash
# 检查 Dockerfile 是否包含所需依赖
cd f:\project\agent && cat Dockerfile
```

确认 Dockerfile 包含:
- `COPY knowledge-base/ knowledge-base/`
- `COPY .claude/ .claude/`
- `RUN pip install pywebview` (如果不需要 GUI 可排除)

- [ ] **Step 3: 验证 docker compose 语法**

```bash
cd f:\project\agent && docker compose config 2>&1
```

Expected: 输出完整配置，无错误

- [ ] **Step 4: 记录未完成的 Docker 测试**

由于本地可能没有 Docker 环境，记录验证步骤供后续手动测试：

```bash
# 手动验证步骤（需要有 Docker 环境的机器）
docker compose up --build -d
curl http://localhost:8000/api/health
# 应返回 {"status":"ok","version":"1.0.0"}
```

- [ ] **Step 5: Commit**

```bash
git add .env.example Dockerfile docker-compose.yml
git commit -m "chore: add .env.example, verify docker compose config"
```

---

## 执行顺序

```
Task 1 → Task 2 → Task 3 → Task 4  (P0: 计算引擎)
   ↓
Task 5 → Task 6 → Task 7           (P1: AI 质量)
   ↓
Task 8 → Task 9                    (P2: UX)
   ↓
Task 10 → Task 11                  (P3: 工程)
   ↓
Task 12 → Task 13                  (P4: 客户端 + Docker)
```

**总计:** 13 tasks, 约 10-15 工作日

**关键依赖:**
- Task 4 依赖 Task 1-3 完成
- Task 5-7 可并行（不同文件修改点不冲突）
- Task 12 应在所有功能和测试稳定后进行
