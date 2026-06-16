# 玄机子 Trust Engine Sprint 4 实施计划

> **For agentic workers:** 使用 executing-plans 按 Task 顺序执行。每个 Step 使用 checkbox (`- [ ]`) 跟踪。严格 TDD、小步验证、小步提交。

**Goal:** 完成 Trust Engine 产品闭环：可信顾问模式、conversation_summaries 长期记忆、Benchmark 内部展示页、可信报告元信息。让“可追踪、可评测、可回放”的底座转化为用户可感知的可信体验和内部质量看板。

**Source Spec:** `docs/superpowers/specs/2026-06-16-xuanjizi-baziqa-trust-engine-design.md` Section 8.3 / 8.4 / 8.5 / 9.2 / 9.4

**Architecture:** 在 Sprint 1-3 基础上，复用 `model_outputs`、`benchmark_runs`、`life_events`、`PromptEngine`、`structured_reasoning_v1.md`、`run_benchmark.py`、`generate_report.py`。新增 `conversation_summaries` 表、可信顾问 prompt 约束、Benchmark API、内部 `/benchmark` 页面、报告生成元信息。

**Tech Stack:** Python 3.11+, SQLite, FastAPI, vanilla JS, ECharts/Markdown（已存在），pytest。

**Non-goals:** 不引入用户权限系统；不做公开营销页；不做 PDF 导出；不引入外部 BI；不做多租户后台；不实现复杂 RAG 向量检索。

---

## Phase 0：基线确认与范围冻结

### Task 0.1：确认 Sprint 1-3 基线

**Files:**
- Read: `data_store.py`
- Read: `api_server.py`
- Read: `prompt_engine.py`
- Read: `benchmark/runners/run_benchmark.py`
- Read: `benchmark/reports/generate_report.py`
- Read: `static/js/ui.js`
- Read: `static/js/stream.js`
- Read: `static/app.js`

- [ ] **Step 1：运行语法检查**

```bash
python -m py_compile data_store.py api_server.py prompt_engine.py benchmark/runners/run_benchmark.py benchmark/reports/generate_report.py
```

Expected: 无错误。

- [ ] **Step 2：运行非 e2e 全量测试**

```bash
python -m pytest tests/ -q --tb=short --ignore=tests/test_e2e.py
```

Expected: 当前基线全部通过。

- [ ] **Step 3：查看 Git 状态**

```bash
git status --short
```

Expected: 工作区干净。

- [ ] **Step 4：确认不扩大范围**

本 Sprint 只做：

```text
1. conversation_summaries 表 + API
2. trusted advisor mode
3. benchmark API + 内部页面
4. report trust metadata
```

不做：支付、登录权限、PDF、公开展示页、复杂用户画像系统。

---

## Phase 1：conversation_summaries 长期记忆表

### Task 1.1：先写数据层测试

**Files:**
- Edit: `tests/test_data_store.py`
- Later edit: `data_store.py`

**Goal:** 定义 conversation_summaries 表 CRUD 契约。

- [ ] **Step 1：添加 `TestConversationSummaries` 测试类**

测试点：

```python
def test_save_and_get_conversation_summary(self):
    cid = 'summary-chart-001'
    data_store.save_chart(cid, '总结测试', {}, {})
    try:
        saved = data_store.save_conversation_summary(
            id='sum-001',
            chart_id=cid,
            client_id=None,
            summary_type='trusted_advisor',
            summary_text='用户关注事业和财运，偏好谨慎建议。',
            key_facts_json='["关注事业", "关注财运"]',
            preference_json='{"tone": "practical"}',
            source_output_ids_json='[]',
        )
        assert saved['id'] == 'sum-001'
        loaded = data_store.get_conversation_summary('sum-001')
        assert loaded['summary_text'].startswith('用户关注')
    finally:
        data_store.delete_chart(cid)
```

- [ ] **Step 2：添加 list latest 测试**

```python
items = data_store.list_conversation_summaries(chart_id=cid, limit=10)
assert any(x['id'] == 'sum-001' for x in items)
latest = data_store.get_latest_conversation_summary(chart_id=cid, summary_type='trusted_advisor')
assert latest['id'] == 'sum-001'
```

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_data_store.py -q --tb=short -k conversation_summary
```

Expected: 函数不存在而失败。

### Task 1.2：实现 conversation_summaries 表和 CRUD

**Files:**
- Edit: `data_store.py`

**Goal:** 建立可信顾问长期记忆的数据底座。

- [ ] **Step 1：在 `init_db()` 中新增表**

```sql
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id TEXT PRIMARY KEY,
    chart_id TEXT NOT NULL,
    client_id TEXT,
    summary_type TEXT NOT NULL DEFAULT 'general',
    summary_text TEXT NOT NULL DEFAULT '',
    key_facts_json TEXT NOT NULL DEFAULT '[]',
    preference_json TEXT NOT NULL DEFAULT '{}',
    source_output_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_conversation_summaries_chart ON conversation_summaries(chart_id);
CREATE INDEX IF NOT EXISTS idx_conversation_summaries_type ON conversation_summaries(summary_type);
```

- [ ] **Step 2：实现 CRUD**

```python
save_conversation_summary(id, chart_id, client_id=None, summary_type='general',
                          summary_text='', key_facts_json='[]', preference_json='{}',
                          source_output_ids_json='[]')

get_conversation_summary(summary_id)

list_conversation_summaries(chart_id, summary_type=None, limit=20)

get_latest_conversation_summary(chart_id, summary_type=None)
```

- [ ] **Step 3：防御性 limit 处理**

复用 `list_model_outputs` 的模式：非法 limit fallback，范围限制 1-100。

- [ ] **Step 4：运行数据层测试**

```bash
python -m pytest tests/test_data_store.py -q --tb=short -k conversation_summary
```

Expected: 全部通过。

---

## Phase 2：conversation summary API

### Task 2.1：先写 API 测试

**Files:**
- Edit: `tests/test_api.py`
- Later edit: `api_server.py`

**Goal:** 为前端可信顾问模式读取/更新总结提供 API。

- [ ] **Step 1：添加 GET API 测试**

```python
def test_list_conversation_summaries_api(self):
    cid = 'api-summary-chart-001'
    data_store.save_chart(cid, 'API总结测试', {}, {})
    data_store.save_conversation_summary(
        id='api-sum-001', chart_id=cid, summary_type='trusted_advisor',
        summary_text='关注事业', key_facts_json='[]', preference_json='{}', source_output_ids_json='[]'
    )
    r = client.get(f'/api/charts/{cid}/conversation-summaries')
    assert r.status_code == 200
    assert any(x['id'] == 'api-sum-001' for x in r.json())
```

- [ ] **Step 2：添加 POST API 测试**

```python
r = client.post(f'/api/charts/{cid}/conversation-summaries', json={
    'summary_type': 'trusted_advisor',
    'summary_text': '用户偏好实际建议',
    'key_facts': ['偏好实际建议'],
    'preference': {'tone': 'practical'},
})
assert r.status_code == 200
assert r.json()['summary_text'] == '用户偏好实际建议'
```

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_api.py -q --tb=short -k conversation_summary
```

Expected: 404 或路由不存在。

### Task 2.2：实现 API 路由

**Files:**
- Edit: `api_server.py`

**Goal:** 暴露 conversation summary 的读写能力。

- [ ] **Step 1：新增 Pydantic 模型**

```python
class ConversationSummaryCreate(BaseModel):
    summary_type: str = 'general'
    summary_text: str = ''
    key_facts: List[str] = []
    preference: Dict[str, Any] = {}
    source_output_ids: List[str] = []
```

- [ ] **Step 2：新增 GET 路由**

```python
@app.get('/api/charts/{chart_id}/conversation-summaries')
def api_list_conversation_summaries(chart_id: str, summary_type: str = None):
    if not _get_chart(chart_id):
        raise HTTPException(404, 'Chart not found')
    return data_store.list_conversation_summaries(chart_id, summary_type=summary_type)
```

- [ ] **Step 3：新增 POST 路由**

```python
@app.post('/api/charts/{chart_id}/conversation-summaries')
def api_create_conversation_summary(chart_id: str, payload: ConversationSummaryCreate):
    ...
```

要求：
1. 生成 `sum_{uuid}` id。
2. `key_facts` / `preference` / `source_output_ids` 用 `json.dumps(..., ensure_ascii=False)` 保存。
3. 返回保存后的 dict。

- [ ] **Step 4：运行 API 测试**

```bash
python -m pytest tests/test_api.py -q --tb=short -k conversation_summary
```

Expected: 全部通过。

---

## Phase 3：可信顾问模式 Prompt 与 chat_stream 参数

### Task 3.1：先写 PromptEngine 测试

**Files:**
- Edit: `tests/test_prompt_engine.py`
- Later edit: `prompt_engine.py`

**Goal:** PromptEngine 支持 `reasoning_mode=trusted`，在 system prompt 中注入可信回答结构。

- [ ] **Step 1：添加测试 `test_prompt_engine_trusted_mode_contains_required_sections`**

```python
engine = PromptEngine(reasoning_mode='trusted')
prompt = engine.build_system_prompt('career')
assert '命理依据' in prompt
assert '现实解释' in prompt
assert '谨慎建议' in prompt
assert '可行动步骤' in prompt
assert '不做绝对化预测' in prompt
```

- [ ] **Step 2：添加测试 `test_prompt_engine_accepts_conversation_summary`**

```python
engine = PromptEngine(reasoning_mode='trusted', conversation_summary='用户关注事业转型')
prompt = engine.build_system_prompt('career')
assert '用户关注事业转型' in prompt
```

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_prompt_engine.py -q --tb=short
```

Expected: 新测试失败。

### Task 3.2：实现 PromptEngine trusted mode

**Files:**
- Edit: `prompt_engine.py`

**Goal:** 可信顾问回答必须具备标准结构和边界提示。

- [ ] **Step 1：扩展 `PromptEngine.__init__`**

```python
def __init__(self, prompt_version='srp_v1', reasoning_protocol='xuanjizi_srp_v1',
             reasoning_mode='normal', conversation_summary=None):
    ...
```

- [ ] **Step 2：在 `build_system_prompt()` 中追加可信模式块**

```text
可信顾问模式要求：
回答必须包含以下四段：
1. 命理依据
2. 现实解释
3. 谨慎建议
4. 可行动步骤
禁止绝对化预测，不替用户做医疗、投资、婚姻等重大决策。
```

- [ ] **Step 3：注入 conversation_summary**

如有总结：

```text
命主长期咨询摘要：
{conversation_summary}
```

- [ ] **Step 4：运行 PromptEngine 测试**

```bash
python -m pytest tests/test_prompt_engine.py -q --tb=short
```

Expected: 全部通过。

### Task 3.3：扩展 chat_stream 支持 trusted mode

**Files:**
- Edit: `api_server.py`
- Edit: `tests/test_api.py`

**Goal:** `/api/chat/stream` 支持 `reasoning_mode` 和 `memory_mode`，并保存可信模式 metadata。

当前设计建议：

```text
reasoning_mode=normal|trusted
prompt_version=srp_v1
memory_mode=none|summary|full
```

- [ ] **Step 1：检查现有 chat_stream 签名**

当前：

```python
async def chat_stream(chart_id: str, message: str):
```

- [ ] **Step 2：修改签名**

```python
async def chat_stream(
    chart_id: str,
    message: str,
    reasoning_mode: str = Query('normal'),
    memory_mode: str = Query('none'),
):
```

- [ ] **Step 3：加载 conversation summary**

当 `memory_mode == 'summary'` 时：

```python
summary = data_store.get_latest_conversation_summary(chart_id, summary_type='trusted_advisor')
conversation_summary = summary['summary_text'] if summary else None
prompt_engine = PromptEngine(reasoning_mode=reasoning_mode, conversation_summary=conversation_summary)
```

- [ ] **Step 4：保存 model_outputs 时记录 trusted metadata**

`structured_reasoning_json` 增加：

```python
{
  'local_analysis': conclusions,
  'confidence': None,
  'reasoning_mode': reasoning_mode,
  'memory_mode': memory_mode,
  'conversation_summary_id': summary['id'] if summary else None,
}
```

- [ ] **Step 5：补充 API 测试**

通过 monkeypatch `_stream_claude`，调用：

```python
client.get('/api/chat/stream', params={
    'chart_id': cid,
    'message': '事业如何',
    'reasoning_mode': 'trusted',
    'memory_mode': 'summary',
})
```

断言落库的 `model_outputs` 中 `structured_reasoning_json.reasoning_mode == 'trusted'`。

- [ ] **Step 6：运行目标测试**

```bash
python -m pytest tests/test_api.py tests/test_prompt_engine.py -q --tb=short
```

---

## Phase 4：自动生成/更新 conversation summary

### Task 4.1：设计最小可用 summary 更新逻辑

**Files:**
- Edit: `api_server.py`
- Edit: `tests/test_api.py`

**Goal:** trusted chat 完成后，根据用户输入和回答自动保存一条简短 summary，先用规则式摘要，不额外调用模型。

**YAGNI 原则：** Sprint 4 不再引入单独总结模型调用，避免成本和复杂度。

- [ ] **Step 1：实现 `_build_conversation_summary_text(chart, message, reply_text, previous_summary=None)`**

规则：

```text
如果 previous_summary 存在：保留前 500 字
追加：最近用户关注：{message[:120]}
追加：最近回答主题：根据 report_tab 或关键词判断 career/wealth/relationship/health
```

- [ ] **Step 2：trusted 模式完成后保存 summary**

当 `reasoning_mode == 'trusted'`：

```python
data_store.save_conversation_summary(
    id=f'sum_{uuid}',
    chart_id=chart_id,
    client_id=_client_id,
    summary_type='trusted_advisor',
    summary_text=summary_text,
    key_facts_json=json.dumps([...], ensure_ascii=False),
    preference_json=json.dumps({'reasoning_mode': 'trusted'}, ensure_ascii=False),
    source_output_ids_json=json.dumps([saved_model_output_id], ensure_ascii=False),
)
```

- [ ] **Step 3：测试 trusted chat 会新增 summary**

断言：

```python
summaries = data_store.list_conversation_summaries(cid, summary_type='trusted_advisor')
assert len(summaries) >= 1
assert '事业如何' in summaries[0]['summary_text']
```

- [ ] **Step 4：运行目标测试**

```bash
python -m pytest tests/test_api.py -q --tb=short -k 'chat_stream or conversation_summary'
```

---

## Phase 5：Benchmark API

### Task 5.1：先写 benchmark API 测试

**Files:**
- Edit: `tests/test_api.py`
- Later edit: `api_server.py`

**Goal:** 为内部页面提供 benchmark_runs 列表、详情、报告读取能力。

- [ ] **Step 1：添加 `TestBenchmarkApi` 测试类**

```python
def test_list_benchmark_runs_api(self):
    data_store.save_benchmark_run(
        id='api-bench-run-001',
        dataset='baziqa_mini_v1.jsonl',
        provider='deepseek',
        model='deepseek-v4-pro',
        n_cases=20,
        n_questions=20,
        accuracy=0.75,
        evidence_score=0.66,
        stability_score=0.8,
        safety_score=1.0,
        report_path='',
    )
    r = client.get('/api/benchmark/runs')
    assert r.status_code == 200
    assert any(x['id'] == 'api-bench-run-001' for x in r.json())
```

- [ ] **Step 2：添加 get run 测试**

```python
r = client.get('/api/benchmark/runs/api-bench-run-001')
assert r.status_code == 200
assert r.json()['accuracy'] == 0.75
```

- [ ] **Step 3：添加 report 读取测试**

用 tmp 文件或固定 `benchmark/outputs/test_report.md`，保存 run 的 `report_path` 后：

```python
r = client.get('/api/benchmark/report/api-bench-run-001')
assert r.status_code == 200
assert '# Report' in r.text
```

- [ ] **Step 4：运行预期失败测试**

```bash
python -m pytest tests/test_api.py -q --tb=short -k benchmark
```

Expected: 路由不存在。

### Task 5.2：实现 Benchmark API

**Files:**
- Edit: `api_server.py`

**Goal:** 提供内部 benchmark dashboard 所需接口。

- [ ] **Step 1：新增 GET `/api/benchmark/runs`**

```python
@app.get('/api/benchmark/runs')
def api_list_benchmark_runs(dataset: str = None, model: str = None, limit: int = Query(20, ge=1, le=100)):
    return data_store.list_benchmark_runs(dataset=dataset, model=model, limit=limit)
```

- [ ] **Step 2：新增 GET `/api/benchmark/runs/{run_id}`**

```python
run = data_store.get_benchmark_run(run_id)
if not run: raise HTTPException(404, 'Benchmark run not found')
return run
```

- [ ] **Step 3：新增 GET `/api/benchmark/report/{run_id}`**

要求：
1. 读取 run.report_path。
2. 限制路径必须在 `benchmark/outputs` 下，防止任意文件读取。
3. 文件不存在返回 404。
4. 返回 `PlainTextResponse`，media_type 为 `text/markdown; charset=utf-8`。

- [ ] **Step 4：可选 POST `/api/benchmark/run`**

最小实现：先返回 501 或仅支持离线已存在 runner，不在本 Sprint 强制真实触发 benchmark，避免长耗时 API。

- [ ] **Step 5：运行 API 测试**

```bash
python -m pytest tests/test_api.py -q --tb=short -k benchmark
```

---

## Phase 6：内部 `/benchmark` 页面

### Task 6.1：创建 benchmark 前端页面

**Files:**
- Create: `static/benchmark.html`
- Create: `static/js/benchmark-dashboard.js`
- Optionally edit: `api_server.py` static route if needed

**Goal:** 内部展示最新 benchmark_runs 和 Markdown 报告。

**页面结构：**

```text
/benchmark
├── 顶部指标卡
│   ├── 最新准确率
│   ├── 依据覆盖
│   ├── 稳定性
│   └── 安全分
├── 运行列表
│   ├── run_id / model / prompt_version / cases / created_at
│   └── 点击加载详情
├── 领域短板
│   └── 从 report 或 by_domain 摘要读取
└── Markdown 报告预览
```

- [ ] **Step 1：实现 `static/benchmark.html`**

使用现有 CSS 基础样式，避免引入新框架。

- [ ] **Step 2：实现 `benchmark-dashboard.js`**

功能：

```javascript
async function loadRuns() {
  const runs = await fetch('/api/benchmark/runs').then(r => r.json())
  renderCards(runs[0])
  renderRunList(runs)
}

async function loadReport(runId) {
  const text = await fetch(`/api/benchmark/report/${runId}`).then(r => r.text())
  document.querySelector('#report-preview').textContent = text
}
```

- [ ] **Step 3：添加 `/benchmark` 静态页面路由**

如果已有 StaticFiles 可访问 `static/benchmark.html`，则可只提示访问路径 `/static/benchmark.html`。
若需要 `/benchmark`：

```python
@app.get('/benchmark')
def benchmark_page():
    return FileResponse(os.path.join(STATIC_DIR, 'benchmark.html'))
```

- [ ] **Step 4：手工验证页面加载**

启动服务后访问：

```text
http://localhost:8000/benchmark
```

Expected: 可以看到 benchmark runs 列表；点击 run 能显示 report。

---

## Phase 7：可信报告元信息

### Task 7.1：扩展 report metadata 生成

**Files:**
- Edit: `benchmark/reports/generate_report.py`
- Edit: `tests/test_benchmark_report.py`

**Goal:** 报告展示模型、协议、依据覆盖、安全边界、生成时间等可信信息。

- [ ] **Step 1：先写测试**

```python
def test_report_contains_trust_metadata():
    report = generate_markdown_report({...})
    assert '本报告生成信息' in report
    assert '模型' in report
    assert '协议' in report
    assert '依据覆盖' in report
    assert '安全边界' in report
```

- [ ] **Step 2：扩展 `generate_markdown_report()`**

在综合评分之后或结尾增加：

```markdown
## 本报告生成信息

| 项目 | 内容 |
|---|---|
| 模型 | DeepSeek v4 Pro |
| Prompt版本 | srp_v1 |
| 推理协议 | Xuanjizi-SRP-v1 |
| 依据覆盖 | 72% |
| 安全边界 | 已启用 |
| 生成时间 | 2026-06-16 12:00 |
```

- [ ] **Step 3：运行报告测试**

```bash
python -m pytest tests/test_benchmark_report.py -q --tb=short
```

---

## Phase 8：可信顾问前端入口

### Task 8.1：前端增加可信模式开关

**Files:**
- Read/Edit: `static/js/stream.js`
- Read/Edit: `static/app.js` 或 `static/js/ui.js`
- CSS 如需：`static/css/panels.css`

**Goal:** 用户在聊天框选择“普通回答 / 可信推理”。

- [ ] **Step 1：定位聊天提交函数**

搜索：

```bash
# 使用 Grep 搜索 sendMessage / chat_stream / EventSource
```

- [ ] **Step 2：添加模式开关 UI**

在聊天输入区附近添加：

```html
<label class="trusted-mode-toggle">
  <input type="checkbox" id="trusted-mode-toggle">
  可信推理
</label>
```

- [ ] **Step 3：stream 请求追加参数**

```javascript
const trusted = document.getElementById('trusted-mode-toggle')?.checked
params.set('reasoning_mode', trusted ? 'trusted' : 'normal')
params.set('memory_mode', trusted ? 'summary' : 'none')
```

- [ ] **Step 4：可信模式提示**

在 UI 中显示短提示：

```text
可信推理会显示命理依据、现实解释、谨慎建议和可行动步骤。
```

- [ ] **Step 5：手工验证**

启动服务，发送一句“事业接下来怎么走？”，确认 SSE 正常，后端落库 `reasoning_mode=trusted`。

---

## Phase 9：全量验证

### Task 9.1：后端测试

- [ ] **Step 1：语法检查**

```bash
python -m py_compile data_store.py api_server.py prompt_engine.py benchmark/reports/generate_report.py
```

- [ ] **Step 2：目标测试**

```bash
python -m pytest tests/test_data_store.py tests/test_api.py tests/test_prompt_engine.py tests/test_benchmark_report.py -q --tb=short
```

- [ ] **Step 3：全量非 e2e 测试**

```bash
python -m pytest tests/ -q --tb=short --ignore=tests/test_e2e.py
```

Expected: 全部通过。

### Task 9.2：前端语法检查

- [ ] **Step 1：检查新增 JS**

```bash
node --check static/js/benchmark-dashboard.js
node --check static/js/stream.js
node --check static/app.js
```

如果某些文件未修改，可以跳过。

### Task 9.3：手工验证清单

- [ ] `/benchmark` 页面可打开。
- [ ] `/api/benchmark/runs` 返回列表。
- [ ] `/api/benchmark/report/{run_id}` 只允许读取 `benchmark/outputs` 下报告。
- [ ] 聊天框可信模式开关存在。
- [ ] 可信模式回答落库 `model_outputs.structured_reasoning_json.reasoning_mode == trusted`。
- [ ] trusted chat 后生成 `conversation_summaries`。
- [ ] Benchmark report 包含“本报告生成信息”。

### Task 9.4：变更范围检查

- [ ] **Step 1：查看 Git 状态**

```bash
git status --short
```

Expected 修改集中在：

```text
data_store.py
api_server.py
prompt_engine.py
benchmark/reports/generate_report.py
static/benchmark.html
static/js/benchmark-dashboard.js
static/js/stream.js 或 static/app.js
tests/test_data_store.py
tests/test_api.py
tests/test_prompt_engine.py
tests/test_benchmark_report.py
```

---

## Phase 10：提交边界与回滚策略

### Task 10.1：提交 Sprint 4

- [ ] **Step 1：确认所有测试通过**

```bash
python -m pytest tests/ -q --tb=short --ignore=tests/test_e2e.py
```

- [ ] **Step 2：查看 diff 摘要**

```bash
git diff --stat
```

- [ ] **Step 3：提交（除非用户另有要求）**

```bash
git add -A && git commit -m "feat: add Trust Engine Sprint 4 - Trusted Advisor and Benchmark Dashboard"
```

### Task 10.2：回滚策略

若出现严重回归：

1. **Benchmark 页面回滚**：删除 `/benchmark` 路由和 `static/benchmark.html`，不影响主业务。
2. **trusted mode 回滚**：chat_stream 参数保留但默认 normal，不影响普通聊天。
3. **conversation_summaries 回滚**：表为新增表，`CREATE TABLE IF NOT EXISTS`，不影响旧数据。
4. **可信报告元信息回滚**：仅影响 benchmark report 文本，不影响评分器。

---

## Sprint 4 完成定义

必须满足以下条件才算完成：

```text
1. conversation_summaries 表和 CRUD 通过测试
2. /api/charts/{chart_id}/conversation-summaries GET/POST 正常
3. PromptEngine 支持 reasoning_mode=trusted，并注入四段式可信回答结构
4. /api/chat/stream 支持 reasoning_mode 和 memory_mode 参数
5. trusted chat 会读取 latest conversation summary 并写入 model_outputs metadata
6. trusted chat 后会生成或更新 conversation summary
7. /api/benchmark/runs、/api/benchmark/runs/{id}、/api/benchmark/report/{id} 正常
8. /api/benchmark/report/{id} 有路径安全防护，不能任意读文件
9. /benchmark 内部页面可展示最新 benchmark runs 和 markdown report
10. Benchmark report 包含“本报告生成信息”可信元信息
11. 前端聊天入口有可信推理开关
12. 全量非 e2e 测试通过
```

---

## Sprint 4 后续建议

Sprint 4 完成后，玄机子的 Trust Engine 3.0 基本闭环已经形成。后续可以进入两个方向：

```text
产品化：
- 付费报告模板
- PDF 导出
- 用户可见的“依据展开”交互
- 专属顾问订阅模式

质量工程：
- 扩展 benchmark dataset 到 100+ cases
- 多模型对比
- 自动 nightly benchmark
- Regression gate：低于阈值禁止发布
```
