# 玄机子 Trust Engine Sprint 3 实施计划

> **For agentic workers:** 使用 executing-plans 按 Task 顺序执行。每个 Step 使用 checkbox (`- [ ]`) 跟踪。

**Goal:** 实现人生 K 线 2.0——将大运/流年/命盘结构化推理映射到可交互时间轴，并支持用户回填真实人生事件，形成"预测 + 验证"的闭环。

**Source Spec:** `docs/superpowers/specs/2026-06-16-xuanjizi-baziqa-trust-engine-design.md` Section 8.2

**Architecture:** 在 Sprint 1-2 基础上，新增 `life_events` 表、`/api/charts/{id}/timeline` API、timeline 前端（复用现有 `static/js/timeline.js` 和 `static/js/charts.js` 的 ECharts）。

**Tech Stack:** Python 3.11+, SQLite, FastAPI, vanilla JS, ECharts（已引入）。

**Non-goals:** 不实现 conversation_summaries（属 Sprint 4）；不实现专属顾问模式；不引入外部数据库；不改变现有聊天和报告架构。

---

## Phase 0：基线确认

### Task 0.1：确认当前代码基线

**Files:**
- Read: `data_store.py`（确认 model_outputs 和 benchmark 表存在）
- Read: `static/js/timeline.js`（现有 timeline 实现）
- Read: `static/js/charts.js`（现有 BaZiCharts）
- Read: `api_server.py`（_build_visualization_data 和 /api/charts/{id}/visualization）

- [ ] **Step 1：运行基础语法检查**

```bash
python -m py_compile data_store.py api_server.py
```

- [ ] **Step 2：确认 Sprint 2 benchmark 测试通过**

```bash
python -m pytest tests/test_benchmark_evidence_score.py tests/test_benchmark_safety_score.py tests/test_benchmark_stability_score.py tests/test_benchmark_report.py -q --tb=short
```

- [ ] **Step 3：查看 Git 状态**

```bash
git status --short
```

Expected: 无未提交变更。

- [ ] **Step 4：确认 timeline.js 现有实现**

检查 `static/js/timeline.js`，确认当前只是简单列表，下一步升级为 K 线 2.0。

---

## Phase 1：life_events 数据表

### Task 1.1：先写 life_events 数据层测试

**Files:**
- Edit: `tests/test_data_store.py`
- Later edit: `data_store.py`

**Goal:** 定义 life_events 表 CRUD 契约。

- [ ] **Step 1：添加 `test_save_and_get_life_event`**

```python
payload = {
    'id': 'event-001',
    'chart_id': 'chart-life-001',
    'client_id': None,
    'event_date': '2020-03-15',
    'event_year': 2020,
    'domain': 'career',
    'title': '入职新公司',
    'description': '加入某互联网公司担任产品经理',
    'impact_level': 4,
    'source': 'user',
}
saved = data_store.save_life_event(**payload)
assert saved['id'] == 'event-001'
assert saved['domain'] == 'career'
assert saved['impact_level'] == 4
loaded = data_store.get_life_event('event-001')
assert loaded is not None
```

- [ ] **Step 2：添加 `test_list_life_events_for_chart`**

```python
items = data_store.list_life_events(chart_id='chart-life-001')
assert any(e['id'] == 'event-001' for e in items)

# domain 过滤
items = data_store.list_life_events(chart_id='chart-life-001', domain='career')
assert all(e['domain'] == 'career' for e in items)
```

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_data_store.py -q --tb=short -k life_event
```

Expected: 函数不存在而失败。

### Task 1.2：实现 life_events 表

**Files:**
- Edit: `data_store.py`

**Goal:** 在 `init_db()` 中创建 `life_events` 表。

- [ ] **Step 1：添加 CREATE TABLE**

```sql
CREATE TABLE IF NOT EXISTS life_events (
    id TEXT PRIMARY KEY,
    chart_id TEXT NOT NULL,
    client_id TEXT,
    event_date TEXT,
    event_year INTEGER,
    domain TEXT NOT NULL DEFAULT 'unknown',
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    impact_level INTEGER NOT NULL DEFAULT 3,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_life_events_chart ON life_events(chart_id);
CREATE INDEX IF NOT EXISTS idx_life_events_year ON life_events(event_year);
CREATE INDEX IF NOT EXISTS idx_life_events_domain ON life_events(domain);
```

- [ ] **Step 2：实现 CRUD 函数**

```python
save_life_event(id, chart_id, client_id=None, event_date=None, event_year=None,
                domain='unknown', title='', description='', impact_level=3, source='user')

get_life_event(event_id)

list_life_events(chart_id, domain=None, year=None, limit=100)
```

- [ ] **Step 3：运行测试**

```bash
python -m pytest tests/test_data_store.py -q --tb=short -k life_event
```

Expected: 全部通过。

---

## Phase 2：Timeline API

### Task 2.1：实现 `/api/charts/{chart_id}/timeline` API

**Files:**
- Edit: `api_server.py`

**Goal:** 聚合大运/流年/命盘推理/人生事件数据，提供给前端 K 线图。

**API 返回格式：**

```json
{
  "chart_id": "xxx",
  "birth_year": 1990,
  "gender": "male",
  "dayun": [
    {
      "start_age": 0,
      "end_age": 10,
      "gan_zhi": "戊子",
      "score": 0.65,
      "events": [
        {"year": 1990, "title": "出生", "domain": "personality", "impact_level": 5, "source": "system"}
      ]
    }
  ],
  "liunian": [
    {
      "year": 2020,
      "gan_zhi": "庚子",
      "score": 0.72,
      "event_mappings": [
        {"domain": "career", "tendency": "岗位变化概率上升", "confidence": 0.63}
      ],
      "user_events": [
        {"id": "event-001", "title": "入职新公司", "domain": "career", "impact_level": 4}
      ]
    }
  ],
  "domains": ["career", "wealth", "relationship", "health", "family"],
  "future_warnings": [
    {"year": 2027, "domain": "career", "message": "大运转换期，岗位调整概率上升，建议提前准备"}
  ]
}
```

**API 构建逻辑：**

1. 从 `data_store.get_chart(chart_id)` 获取 `chart_data`（含 dayun/liunian）。
2. 从 `data_store.list_life_events(chart_id=chart_id)` 获取用户事件。
3. 从 `data_store.list_model_outputs(chart_id=chart_id)` 获取 `structured_reasoning_json`，提取 `event_mappings`。
4. 计算未来 3-5 年警告（基于大运转换年份 + 流年冲合）。

- [ ] **Step 1：在 api_server.py 中添加 timeline API**

```python
@app.get("/api/charts/{chart_id}/timeline")
def api_timeline(chart_id: str):
    chart = _get_chart(chart_id)
    if not chart:
        raise HTTPException(404, "Chart not found")
    return _build_timeline_data(chart)
```

- [ ] **Step 2：实现 `_build_timeline_data(chart)`**

参考 `_build_visualization_data` 的 dayun/liunian 解析逻辑。

- [ ] **Step 3：添加 life_events API 路由**

```python
@app.post("/api/charts/{chart_id}/life-events")
def api_create_life_event(chart_id: str, event: LifeEventCreate):
    ...

@app.get("/api/charts/{chart_id}/life-events")
def api_list_life_events(chart_id: str, domain: str = None):
    ...

@app.delete("/api/life-events/{event_id}")
def api_delete_life_event(event_id: str):
    ...
```

- [ ] **Step 4：运行 API 测试**

```bash
python -m pytest tests/test_api.py -q --tb=short
```

Expected: 全部通过。

---

## Phase 3：人生 K 线 2.0 前端

### Task 3.1：升级 timeline.js 为交互式 K 线

**Files:**
- Edit: `static/js/timeline.js`

**Goal:** 将简单的分析列表升级为带 ECharts 的交互式时间轴。

**页面布局：**

```
┌─────────────────────────────────────────────────────┐
│ 领域开关：[事业][财运][感情][健康][家庭]  [+添加事件] │
├─────────────────────────────────────────────────────┤
│ 大运区间条 ─────────────────────────────────────── │
│ 流年趋势图（ECharts 折线+柱状）                    │
│ 领域 marker（彩色圆点）                             │
│ 用户事件 marker（星形）                             │
├─────────────────────────────────────────────────────┤
│ 年份详情面板（点击年份展开）                        │
│ - 流年分析摘要                                      │
│ - 命理依据                                          │
│ - 用户已填事件                                     │
│ - 未来 3-5 年提示                                  │
└─────────────────────────────────────────────────────┘
```

**功能要求：**

1. **大运区间条**：横向条带分段显示，鼠标悬停显示"X岁-X岁 大运：庚子 评分：0.72"
2. **流年趋势图**：ECharts 折线图（评分）+ 柱状图（影响强度），年份可点击
3. **领域开关**：多选按钮，切换各领域 marker 的显示/隐藏
4. **用户事件 marker**：星形/三角图标，显示在对应年份上
5. **年份详情面板**：点击年份展开，显示命理分析摘要和用户事件列表
6. **添加事件按钮**：弹窗表单（年份、领域、标题、描述、影响等级）

**ECharts 配置注意事项：**

```javascript
// 年份范围自动从 birth_year 到当前年份 + 5
// 评分范围 0-1，映射到 y 轴
// 大运区间用 markArea 渲染半透明背景条带
// 领域 marker 用 scatter 系列，shape: 'circle'，按领域配色
// 用户事件 marker 用特殊符号 'star'
```

- [ ] **Step 1：重构 `renderTimeline(container, analyses, onFeedbackSubmitted)`**

新签名：

```javascript
export async function renderTimeline(container, chartId) {
    // 1. fetch /api/charts/{chartId}/timeline
    // 2. fetch /api/charts/{chartId}/life-events
    // 3. 初始化 ECharts
    // 4. 绑定领域开关事件
    // 5. 绑定年份点击事件 → 展开详情面板
    // 6. 绑定添加事件按钮
}
```

- [ ] **Step 2：实现 `_renderKLineChart(container, timelineData)`**

用 ECharts 渲染：
- X 轴：年份（从 birth_year 到 birth_year + 80）
- 左 Y 轴：运势评分（0-1）
- markArea：大运区间背景
- scatter：领域影响 marker
- scatter：用户事件 marker

- [ ] **Step 3：实现 `_renderYearDetailPanel(year, timelineData, userEvents)`**

点击年份后，在面板中展示：
- 流年干支和评分
- 命理分析摘要（从 structured_reasoning_json.event_mappings 提取）
- 该年用户已填事件列表
- 未来 3-5 年提示

- [ ] **Step 4：实现 `_showAddEventModal(chartId, year)`**

弹窗表单：
- 年份（自动填充点击的年份，可修改）
- 领域（select: career/wealth/relationship/health/family/personality）
- 标题（text）
- 描述（textarea）
- 影响等级（1-5 星）
- 提交到 POST /api/charts/{chartId}/life-events

- [ ] **Step 5：更新 app.js 中的 timeline tab 渲染调用**

找到现有 `renderTimeline` 调用，更新为新签名：

```javascript
// 之前
renderTimeline(contentDiv, analyses, onFeedbackSubmitted)

// 之后
renderTimeline(contentDiv, cur.chart_id)
```

- [ ] **Step 6：运行前端验证**

启动服务 `python api_server.py`，创建命主，进入 timeline tab，确认 K 线图渲染。

---

## Phase 4：未来 3-5 年提醒

### Task 4.1：在 Timeline API 中计算未来提醒

**Files:**
- Edit: `api_server.py`

**Goal:** 基于大运转换和流年冲合，生成未来 3-5 年关键节点提醒。

**提醒规则：**

1. **大运转换年**（start_age 边界的前后 1 年）：提示"大运转换期，事业/财运可能有较大变化"
2. **流年冲太岁**（年支与出生年支相冲）：提示"今年冲太岁，宜低调"
3. **关键流年**（评分 > 0.8 或 < 0.3）：提示"今年运势特别强/需注意"
4. **领域峰值年**（某领域 confidence 峰值年份）：提示"某年事业/财运特别好"

**未来提醒数据结构：**

```python
future_warnings = [
    {
        "year": 2027,
        "domain": "career",
        "warning_type": "dayun_transition",  # dayun_transition | taiyue_chong | score_peak | score_low
        "message": "大运转换期，岗位调整概率上升，建议提前准备",
        "urgency": "medium",  # low | medium | high
    }
]
```

- [ ] **Step 1：实现 `_generate_future_warnings(chart)`**

读取 chart_data 中的 dayun 和 liunian，计算未来 5 年的关键提醒。

- [ ] **Step 2：将 future_warnings 注入 `_build_timeline_data` 返回值**

- [ ] **Step 3：在 timeline.js 中渲染未来提醒**

在页面顶部或底部，显示"未来 3-5 年关键节点"列表。

---

## Phase 5：全量验证

### Task 5.1：运行所有 Sprint 3 相关测试

- [ ] **Step 1：语法检查**

```bash
python -m py_compile data_store.py api_server.py
```

- [ ] **Step 2：运行数据层测试**

```bash
python -m pytest tests/test_data_store.py -q --tb=short
```

- [ ] **Step 3：运行 API 测试**

```bash
python -m pytest tests/test_api.py -q --tb=short
```

- [ ] **Step 4：运行全量非 e2e 测试**

```bash
python -m pytest tests/ -q --tb=short --ignore=tests/test_e2e.py
```

### Task 5.2：手工验证 Timeline API

- [ ] **Step 1：启动服务**

```bash
python api_server.py
```

- [ ] **Step 2：创建命主后查询 timeline API**

```bash
# 先获取 chart_id
curl "http://localhost:端口/api/charts/{chart_id}/timeline"
```

Expected: 返回 dayun/liunian/life_events/future_warnings。

- [ ] **Step 3：添加并查询 life-event**

```bash
curl -X POST "http://localhost:端口/api/charts/{chart_id}/life-events" \
  -H "Content-Type: application/json" \
  -d '{"event_year": 2020, "domain": "career", "title": "入职", "impact_level": 4}'

curl "http://localhost:端口/api/charts/{chart_id}/life-events"
```

- [ ] **Step 4：打开浏览器验证 Timeline K 线图**

进入命主详情页 → timeline tab，确认 K 线图渲染、领域开关、添加事件按钮工作正常。

### Task 5.3：检查变更范围

- [ ] **Step 1：查看 Git 状态**

```bash
git status --short
```

Expected 修改集中在：

```
data_store.py
api_server.py
static/js/timeline.js
tests/test_data_store.py
tests/test_api.py（可选）
```

不应有非相关文件变更。

---

## Phase 6：提交边界与回滚策略

### Task 6.1：提交 Sprint 3

- [ ] **Step 1：确认所有测试通过**

- [ ] **Step 2：提交（除非用户另有要求）**

```bash
git add -A && git commit -m "feat: add Trust Engine Sprint 3 - Life Timeline 2.0"
```

### Task 6.2：回滚策略

若出现严重回归：

1. 回退 `life_events` 表：新表不影响现有功能（`CREATE TABLE IF NOT EXISTS`）
2. 回退 timeline API：前端自动降级到原有列表视图
3. 回退 timeline.js：保留原列表逻辑（`renderTimeline` 签名变化需同步更新 `app.js` 调用点）

---

## Sprint 3 完成定义

必须满足以下条件才算完成：

```text
1. life_events 表和 CRUD 通过测试
2. /api/charts/{chart_id}/timeline API 返回 dayun/liunian/life_events/future_warnings
3. /api/charts/{chart_id}/life-events POST/GET 和 DELETE API 正常
4. timeline.js 升级为可交互 K 线图（ECharts）
5. 领域开关可切换 marker 显示/隐藏
6. 年份详情面板可展开，显示命理分析和用户事件
7. 添加事件弹窗表单可正常提交并显示
8. 未来 3-5 年关键节点提醒正常显示
9. 全量非 e2e 测试通过
10. 手工验证 timeline tab K 线图正常渲染
```
