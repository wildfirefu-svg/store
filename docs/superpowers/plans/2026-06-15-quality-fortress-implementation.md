# 「质量堡垒」可执行实施计划

> **For agentic workers:** 使用 executing-plans 按 Task 顺序执行。每个 Step 使用 checkbox (`- [ ]`) 跟踪。不要一次性实现多个 Phase；每个 Task 完成后运行对应测试。除非用户明确要求，不要提交 Git commit。

**Goal:** 基于真实代码库实现「质量堡垒」路线图：先提升 Claude 流式分析质量，再扩展客户工作流、可视化报告、反馈数据飞轮。

**Source Spec:** `docs/superpowers/specs/2026-06-15-quality-fortress-roadmap-design.md`

**Architecture:** 保留现有 `chart_id` 命盘中心架构，新增客户/分析/反馈层。保留现有 `/api/chat/stream` SSE、`auto_analyzer.py` 本地规则引擎、`claude_api.py` Claude 调用、`report_builder.py` Markdown 报告、`report_to_pdf.py` PDF、`/api/analyze/pdf` 异步 Job 系统。

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Anthropic Claude, vanilla JS, ECharts, fpdf2, pytest, GitHub Actions Ubuntu。

**Non-goals:** 不切换 DeepSeek；不引入向量数据库；不重写 PDF 为 HTML 模板；不破坏旧 `charts` / `chat_history` / `reports` 表；不实现登录、多租户、云同步、支付。

---

## Phase 0：预检查与基线确认

### Task 0.1：确认当前测试和服务基线

**Files:**
- Read: `requirements-dev.txt`
- Read: `tests/test_api.py`
- Read: `tests/test_data_store.py`
- Read: `.github/workflows/ci.yml`

**Goal:** 在修改前确认当前项目能安装、导入和运行基础测试。

- [ ] **Step 1：查看测试命令约定**

读取 `.github/workflows/ci.yml`，确认 CI 当前执行：

```bash
python -m pytest tests/ -v --tb=short --timeout=120
```

- [ ] **Step 2：运行语法检查**

```bash
python -m py_compile api_server.py data_store.py auto_analyzer.py claude_api.py report_builder.py report_to_pdf.py bazi_calculator.py
```

Expected: 无语法错误。

- [ ] **Step 3：运行数据层测试**

```bash
python -m pytest tests/test_data_store.py -v --tb=short
```

Expected: 现有 data_store 测试通过。

- [ ] **Step 4：运行 API 测试**

```bash
python -m pytest tests/test_api.py -v --tb=short
```

Expected: API 测试通过或记录当前失败项。不要在此 Task 修复非相关历史失败。

---

## Phase 1：AI 分析质量优化

### Task 1.1：为 PromptEngine 写最小单元测试

**Files:**
- Create: `tests/test_prompt_engine.py`
- Create later: `prompt_engine.py`

**Goal:** 先定义 PromptEngine 的输入输出契约，确保新增模块可独立测试。

- [ ] **Step 1：创建 `tests/test_prompt_engine.py`**

测试用例包含一个最小 chart 和 pre_analysis 字典：

```python
from prompt_engine import PromptEngine


def test_prompt_engine_assemble_contains_required_sections():
    chart = {
        "four_pillars": {
            "year": {"gan": "甲", "zhi": "子"},
            "month": {"gan": "乙", "zhi": "丑"},
            "day": {"gan": "丙", "zhi": "寅"},
            "hour": {"gan": "丁", "zhi": "卯"},
        },
        "day_master": {"gan": "丙", "wuxing": "火"},
        "wuxing_stats": {"金": 1, "木": 2, "水": 1, "火": 2, "土": 2},
    }
    pre_analysis = {
        "pattern": {"conclusion": "测试格局", "confidence": 0.7},
        "yongshen": {"conclusion": "测试用神", "confidence": 0.6},
    }

    system_prompt, user_prompt = PromptEngine().assemble(
        chart=chart,
        pre_analysis=pre_analysis,
        topic="sihechu",
        question="请分析事业",
    )

    assert "结构" in system_prompt or "输出" in system_prompt
    assert "核心判断" in system_prompt
    assert "证据链" in system_prompt
    assert "丙" in user_prompt
    assert "测试格局" in user_prompt
    assert "请分析事业" in user_prompt
```

- [ ] **Step 2：运行预期失败测试**

```bash
python -m pytest tests/test_prompt_engine.py -v
```

Expected: 因 `prompt_engine.py` 不存在而失败。

### Task 1.2：实现 PromptEngine 最小版本

**Files:**
- Create: `prompt_engine.py`

**Goal:** 创建可测试的 Prompt 构建器，不接入外部 CaseRetriever，仅先输出系统 Prompt 和动态上下文。

- [ ] **Step 1：创建 `prompt_engine.py` 文件**

实现：

```python
import json

SYSTEM_PROMPTS = {
    "sihechu": """你是一位严谨的命理分析助手。输出必须包含：核心判断、证据链、反证据与不确定性、分项分析、实用建议。每个重要判断都要给出八字证据和置信度。""",
    "career": """你是一位严谨的命理事业分析助手。输出必须包含：核心判断、证据链、反证据与不确定性、事业路径、实用建议。""",
    "marriage": """你是一位严谨的命理婚恋分析助手。输出必须包含：核心判断、证据链、反证据与不确定性、关系建议、实用建议。""",
}


class PromptEngine:
    def assemble(self, chart, pre_analysis=None, topic="sihechu", question=""):
        system_prompt = self.build_system_prompt(topic)
        domain_knowledge = self.build_domain_knowledge(chart, topic)
        dynamic_context = self.build_dynamic_context(chart, pre_analysis or {}, question)
        return system_prompt, f"{domain_knowledge}\n\n---\n\n{dynamic_context}"

    def build_system_prompt(self, topic):
        return SYSTEM_PROMPTS.get(topic, SYSTEM_PROMPTS["sihechu"])

    def build_domain_knowledge(self, chart, topic):
        return "## 领域知识\n暂无相似案例。"

    def build_dynamic_context(self, chart, pre_analysis, question):
        return "\n".join([
            "## 当前命盘数据",
            json.dumps(chart, ensure_ascii=False, indent=2),
            "## 本地预分析",
            json.dumps(pre_analysis, ensure_ascii=False, indent=2),
            "## 用户问题",
            question or "请进行综合分析。",
        ])
```

- [ ] **Step 2：运行 PromptEngine 测试**

```bash
python -m pytest tests/test_prompt_engine.py -v
```

Expected: 通过。

- [ ] **Step 3：运行语法检查**

```bash
python -m py_compile prompt_engine.py
```

Expected: 通过。

### Task 1.3：增强 CaseRetriever 输出为 Few-shot 文本

**Files:**
- Modify: `knowledge-base/case_retrieval.py`
- Modify: `tests/test_prompt_engine.py`

**Goal:** 复用现有案例检索能力，增加面向 Prompt 注入的格式化函数。

- [ ] **Step 1：阅读现有 CaseRetriever**

查看 `CaseRetriever`、`retrieve_similar()`、`simple_match()`、`extract_case_features()` 的返回结构。

- [ ] **Step 2：新增格式化函数**

在 `knowledge-base/case_retrieval.py` 中新增函数：

```python
def format_case_for_prompt(case):
    name = case.get("name") or case.get("id") or "未知案例"
    pillars = case.get("pillars") or case.get("four_pillars") or ""
    summary = case.get("summary") or case.get("description") or ""
    events = case.get("events") or []
    event_text = "；".join(str(e) for e in events[:3]) if isinstance(events, list) else str(events)
    return "\n".join([
        "【参考案例】",
        f"姓名：{name}",
        f"命局：{pillars}",
        f"要点：{summary}",
        f"验证：{event_text}",
    ])
```

- [ ] **Step 3：新增 PromptEngine 测试覆盖领域知识**

在 `tests/test_prompt_engine.py` 中添加测试，使用 monkeypatch 替代真实 CaseRetriever：

```python
def test_prompt_engine_formats_domain_knowledge(monkeypatch):
    engine = PromptEngine()
    monkeypatch.setattr(engine, "retrieve_similar_cases", lambda chart: ["【参考案例】\n姓名：测试"])
    text = engine.build_domain_knowledge({}, "sihechu")
    assert "参考案例" in text
```

- [ ] **Step 4：更新 PromptEngine 调用格式化结果**

在 `prompt_engine.py` 中增加：

```python
def retrieve_similar_cases(self, chart):
    return []
```

并让 `build_domain_knowledge()` 拼接案例列表。

- [ ] **Step 5：运行测试**

```bash
python -m pytest tests/test_prompt_engine.py -v
python -m py_compile prompt_engine.py knowledge-base/case_retrieval.py
```

Expected: 全部通过。

### Task 1.4：让 PromptEngine 调用真实 CaseRetriever

**Files:**
- Modify: `prompt_engine.py`
- Possibly modify: `knowledge-base/case_retrieval.py`

**Goal:** 在真实运行中从 52 个 benchmark 案例中取 2-3 个参考案例。

- [ ] **Step 1：实现安全导入**

因为目录名 `knowledge-base` 含连字符，不能直接 import。参考 `api_server.py` 的 `_import_tool()` 方式，在 `prompt_engine.py` 中用 `importlib.util.spec_from_file_location()` 加载 `knowledge-base/case_retrieval.py`。

- [ ] **Step 2：实现 `retrieve_similar_cases()`**

逻辑：

```text
1. 定位 case_retrieval.py 绝对路径
2. 加载模块
3. 如果存在 CaseRetriever，则实例化并调用可用检索方法
4. 捕获异常，返回 []
5. 最多返回 3 条格式化文本
```

- [ ] **Step 3：增加异常安全测试**

在 `tests/test_prompt_engine.py` 增加：

```python
def test_prompt_engine_retrieve_cases_never_raises():
    cases = PromptEngine().retrieve_similar_cases({})
    assert isinstance(cases, list)
```

- [ ] **Step 4：运行测试**

```bash
python -m pytest tests/test_prompt_engine.py -v
```

Expected: 通过，即使案例索引不可用也不抛异常。

### Task 1.5：让 claude_api 支持外部 system prompt

**Files:**
- Read: `claude_api.py`
- Modify: `claude_api.py`
- Create or modify: `tests/test_claude_api.py`

**Goal:** 不破坏现有 `stream_chat(chart, message)` 调用，同时允许传入 `system_prompt`。

- [ ] **Step 1：查看 `stream_chat` 函数签名**

找到 `claude_api.py` 中的 `stream_chat` 定义和内部 system prompt 位置。

- [ ] **Step 2：修改函数签名**

从：

```python
def stream_chat(chart, message):
```

改为：

```python
def stream_chat(chart, message, system_prompt=None):
```

- [ ] **Step 3：保留默认行为**

如果 `system_prompt is None`，继续使用原来的内置提示词。否则使用外部传入的 system prompt。

- [ ] **Step 4：增加无 API Key 的单元测试**

测试目标不是调用真实 Claude，而是验证函数可以接收新参数，不因签名错误失败。若现有 `stream_chat` 在无 key 时返回 error event，则断言 error event 存在。

- [ ] **Step 5：运行测试**

```bash
python -m pytest tests/test_claude_api.py -v --tb=short
python -m py_compile claude_api.py
```

Expected: 通过。

### Task 1.6：接入 PromptEngine 到 `/api/chat/stream`

**Files:**
- Modify: `api_server.py`
- Modify: `tests/test_api.py` or create `tests/test_chat_stream_prompt.py`

**Goal:** `chat_stream()` 使用 PromptEngine 构造 system/user prompt，同时保持 SSE 事件格式不变。

- [ ] **Step 1：在 `api_server.py` 顶部导入 PromptEngine**

```python
from prompt_engine import PromptEngine
```

- [ ] **Step 2：在 `chat_stream()` 中保留 `_detect_tab()`**

不要移除 topic 判断逻辑，后续继续复用 `report_tab`。

- [ ] **Step 3：替换 `enriched_msg` 构造**

原逻辑：

```python
enriched_msg = message
if kb_gejue:
    enriched_msg += ...
```

替换为：

```python
system_prompt, enriched_msg = PromptEngine().assemble(
    chart=chart,
    pre_analysis=conclusions,
    topic=report_tab,
    question=message,
)
```

- [ ] **Step 4：调用 Claude 时传 system prompt**

```python
for event in _stream_claude(enriched, enriched_msg, system_prompt=system_prompt):
```

- [ ] **Step 5：确保 fallback 不变**

保留 `_generate_fallback(chart)` 和 error event 逻辑，避免 API Key 缺失时无法响应。

- [ ] **Step 6：测试 SSE 接口无 API Key 可返回 fallback**

如果现有测试已有 TestClient，新增测试：创建 chart 后调用 `/api/chat/stream`，检查响应包含 `event: reply` 或 `event: done`。

- [ ] **Step 7：运行测试**

```bash
python -m pytest tests/test_api.py -v --tb=short
python -m py_compile api_server.py prompt_engine.py claude_api.py
```

Expected: 通过。

### Task 1.7：新增 LLM 文本质量评分器

**Files:**
- Create: `quality/llm_quality_test.py`
- Create: `tests/test_llm_quality.py`

**Goal:** 不依赖真实 API，先实现可测试的文本评分函数。

- [ ] **Step 1：创建 `tests/test_llm_quality.py`**

覆盖：完整文本高分、缺少小节低分、模糊词过多扣分。

- [ ] **Step 2：创建 `quality/llm_quality_test.py`**

实现：

```python
REQUIRED_SECTIONS = ["核心判断", "证据链", "反证据", "分项分析", "实用建议"]
REQUIRED_TERMS = ["格局", "用神", "置信度", "天干", "地支", "十神"]
VAGUE_TERMS = ["可能", "也许", "大概"]


def score_report(text):
    section_score = sum(1 for s in REQUIRED_SECTIONS if s in text) / len(REQUIRED_SECTIONS)
    term_score = sum(1 for t in REQUIRED_TERMS if t in text) / len(REQUIRED_TERMS)
    vague_count = sum(text.count(t) for t in VAGUE_TERMS)
    vague_penalty = min(vague_count, 10) / 10
    return max(0, round(0.5 * section_score + 0.5 * term_score - 0.2 * vague_penalty, 3))
```

- [ ] **Step 3：增加 CLI 输出**

允许：

```bash
python quality/llm_quality_test.py
```

在无输入时运行内置 smoke sample，并打印 JSON。

- [ ] **Step 4：运行测试**

```bash
python -m pytest tests/test_llm_quality.py -v
python quality/llm_quality_test.py
```

Expected: 单元测试通过，CLI 输出包含 `score`。

### Task 1.8：将 LLM 质量测试接入 CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Goal:** 先做非 API 调用的 smoke test，不增加 CI 成本。

- [ ] **Step 1：在 Run tests 后增加质量 smoke step**

```yaml
      - name: LLM report quality smoke test
        run: |
          python quality/llm_quality_test.py
```

- [ ] **Step 2：本地验证 YAML 缩进**

```bash
python - <<'PY'
from pathlib import Path
p = Path('.github/workflows/ci.yml')
text = p.read_text(encoding='utf-8')
assert 'LLM report quality smoke test' in text
print('PASS')
PY
```

- [ ] **Step 3：运行相关检查**

```bash
python -m py_compile quality/llm_quality_test.py
python quality/llm_quality_test.py
```

Expected: 通过。

---

## Phase 2：专业工作流 MVP

### Task 2.1：为新数据表写 data_store 测试

**Files:**
- Modify: `tests/test_data_store.py`
- Modify later: `data_store.py`

**Goal:** 先定义 clients、client_charts、analyses、feedback 的 CRUD 行为。

- [ ] **Step 1：查看现有 data_store 测试隔离方式**

确认测试是否使用临时 DB，避免污染根目录 `bazi_data.db`。

- [ ] **Step 2：新增客户 CRUD 测试**

测试：

```text
create_client → list_clients → get_client → update_client → delete_client
```

- [ ] **Step 3：新增 client_charts 测试**

先保存一个 chart，再创建 client，再关联 chart，断言 `list_client_charts(client_id)` 返回该 chart。

- [ ] **Step 4：新增 analyses 测试**

创建 analysis，按 client_id 和 chart_id 查询。

- [ ] **Step 5：新增 feedback 测试**

创建 feedback，查询 `get_feedback_stats()` 返回维度准确率。

- [ ] **Step 6：运行预期失败测试**

```bash
python -m pytest tests/test_data_store.py -v --tb=short
```

Expected: 新增函数不存在导致失败。

### Task 2.2：扩展 data_store 表结构

**Files:**
- Modify: `data_store.py`

**Goal:** 在不破坏旧表的基础上新增四张表。

- [ ] **Step 1：在 `init_db()` 的 executescript 中追加 SQL**

新增：`clients`、`client_charts`、`analyses`、`feedback`、相关 index。

- [ ] **Step 2：确保外键指向现有 `charts(chart_id)`**

`client_charts.chart_id` 和 `analyses.chart_id` 必须引用 `charts(chart_id)`。

- [ ] **Step 3：保持时间格式一致**

统一使用现有 `datetime('now','localtime')`。

- [ ] **Step 4：运行 data_store 测试**

```bash
python -m pytest tests/test_data_store.py -v --tb=short
```

Expected: 表存在，但 CRUD 函数仍失败。

### Task 2.3：实现 clients CRUD

**Files:**
- Modify: `data_store.py`

**Goal:** 提供 API 层可直接调用的数据函数。

- [ ] **Step 1：新增 ID 生成 helper**

使用 `uuid.uuid4().hex` 生成 `id`。

- [ ] **Step 2：实现 `create_client(data)`**

输入 dict，输出完整 client dict。

- [ ] **Step 3：实现 `list_clients(search='', tag='')`**

先支持简单 name LIKE 搜索。tag 可先在 Python 中解析 JSON 过滤。

- [ ] **Step 4：实现 `get_client(client_id)`**

找不到返回 None。

- [ ] **Step 5：实现 `update_client(client_id, data)`**

只更新允许字段，更新 `updated_at`。

- [ ] **Step 6：实现 `delete_client(client_id)`**

删除客户，依赖 cascade 删除关联表。

- [ ] **Step 7：运行测试**

```bash
python -m pytest tests/test_data_store.py -v --tb=short
```

Expected: clients 测试通过。

### Task 2.4：实现 client_charts / analyses / feedback 数据函数

**Files:**
- Modify: `data_store.py`

**Goal:** 完成专业工作流数据层。

- [ ] **Step 1：实现 chart 关联函数**

函数：

```python
link_client_chart(client_id, chart_id, relation="primary")
unlink_client_chart(client_id, chart_id)
list_client_charts(client_id)
```

- [ ] **Step 2：实现 analysis 函数**

函数：

```python
save_analysis(client_id, chart_id, analysis_type, topic, question, ai_text, structured_summary=None, report_tab=None)
get_analysis(analysis_id)
list_client_analyses(client_id)
list_chart_analyses(chart_id)
```

- [ ] **Step 3：实现 feedback 函数**

函数：

```python
save_feedback(analysis_id, dimension, judgment_text, is_accurate, user_comment="")
get_feedback_stats()
```

- [ ] **Step 4：确保 JSON 字段读写一致**

`tags`、`structured_summary` 写入 JSON 字符串，读取时转为 Python 对象。

- [ ] **Step 5：运行测试**

```bash
python -m pytest tests/test_data_store.py -v --tb=short
python -m py_compile data_store.py
```

Expected: 通过。

### Task 2.5：为客户 API 写测试

**Files:**
- Modify or create: `tests/test_clients_api.py`
- Modify later: `api_server.py`

**Goal:** 定义客户 API 响应契约。

- [ ] **Step 1：创建 TestClient 测试**

覆盖：`POST /api/clients`、`GET /api/clients`、`GET /api/clients/{id}`、`PUT`、`DELETE`。

- [ ] **Step 2：测试客户关联 chart**

先调用 `/api/chart` 生成 chart_id，再调用 `/api/clients/{client_id}/charts/{chart_id}`。

- [ ] **Step 3：测试分析和反馈 API**

直接通过 data_store 创建 analysis，再测试 `POST /api/analyses/{analysis_id}/feedback`。

- [ ] **Step 4：运行预期失败测试**

```bash
python -m pytest tests/test_clients_api.py -v --tb=short
```

Expected: API 未实现而失败。

### Task 2.6：实现客户 API Pydantic 模型

**Files:**
- Modify: `api_server.py`

**Goal:** 新增 API 请求模型，保持现有风格。

- [ ] **Step 1：在 MODELS 区域添加模型**

新增：

```python
class ClientCreate(BaseModel): ...
class ClientUpdate(BaseModel): ...
class FeedbackCreate(BaseModel): ...
```

- [ ] **Step 2：字段校验沿用 BirthInfo 风格**

gender 使用 `pattern="^(male|female)$"`，日期字段做基本范围限制。

- [ ] **Step 3：运行语法检查**

```bash
python -m py_compile api_server.py
```

Expected: 通过。

### Task 2.7：实现客户 CRUD API

**Files:**
- Modify: `api_server.py`

**Goal:** 实现客户列表和详情管理。

- [ ] **Step 1：新增 `GET /api/clients`**

调用 `data_store.list_clients(search, tag)`。

- [ ] **Step 2：新增 `POST /api/clients`**

调用 `data_store.create_client(req.model_dump())`。

- [ ] **Step 3：新增 `GET /api/clients/{client_id}`**

找不到返回 404。

- [ ] **Step 4：新增 `PUT /api/clients/{client_id}`**

只更新传入字段。

- [ ] **Step 5：新增 `DELETE /api/clients/{client_id}`**

删除成功返回 `{"ok": True}`。

- [ ] **Step 6：运行 API 测试**

```bash
python -m pytest tests/test_clients_api.py -v --tb=short
```

Expected: 客户 CRUD 部分通过。

### Task 2.8：实现 chart 关联、analysis、feedback API

**Files:**
- Modify: `api_server.py`

**Goal:** 完成 Phase 2 后端接口。

- [ ] **Step 1：实现客户关联命盘接口**

```text
POST /api/clients/{client_id}/charts/{chart_id}
DELETE /api/clients/{client_id}/charts/{chart_id}
GET /api/clients/{client_id}/charts
```

- [ ] **Step 2：实现分析查询接口**

```text
GET /api/clients/{client_id}/analyses
GET /api/charts/{chart_id}/analyses
GET /api/analyses/{analysis_id}
```

- [ ] **Step 3：实现反馈接口**

```text
POST /api/analyses/{analysis_id}/feedback
GET /api/feedback/stats
```

- [ ] **Step 4：运行 API 测试**

```bash
python -m pytest tests/test_clients_api.py -v --tb=short
python -m pytest tests/test_api.py -v --tb=short
```

Expected: 通过，不破坏旧 API。

### Task 2.9：在 chat_stream done 前保存 analysis

**Files:**
- Modify: `api_server.py`
- Modify: `tests/test_clients_api.py` or `tests/test_api.py`

**Goal:** 每次流式分析完成后自动保存分析历史。

- [ ] **Step 1：在 `chat_stream()` 中累计 `reply_text` 和 `report_text`**

现有函数已有变量，确认覆盖所有 text_delta 和 fallback。

- [ ] **Step 2：在 done 前调用 `data_store.save_analysis()`**

如果找不到 client_id，允许 `client_id=None`，但必须保存 `chart_id`。

- [ ] **Step 3：done 事件附带 analysis_id**

原：

```python
yield _sse_event('done', {'corrections': 0})
```

改为：

```python
yield _sse_event('done', {'corrections': 0, 'analysis_id': analysis_id})
```

- [ ] **Step 4：无 API Key fallback 也保存 analysis**

确保 error → fallback → done 的路径也调用保存。

- [ ] **Step 5：运行测试**

```bash
python -m pytest tests/test_api.py tests/test_clients_api.py -v --tb=short
```

Expected: 通过。

### Task 2.10：实现客户前端 API 封装

**Files:**
- Create: `static/js/client-api.js`

**Goal:** 为客户页面提供统一 fetch 封装。

- [ ] **Step 1：创建基础 API 函数**

实现：

```javascript
export async function listClients(params = {}) {}
export async function createClient(data) {}
export async function getClient(id) {}
export async function updateClient(id, data) {}
export async function deleteClient(id) {}
export async function listClientAnalyses(id) {}
export async function submitFeedback(analysisId, data) {}
```

- [ ] **Step 2：统一错误处理**

如果 `!response.ok`，抛出包含状态码和响应文本的 Error。

- [ ] **Step 3：浏览器语法检查**

```bash
node --check static/js/client-api.js
```

Expected: 通过。如果环境没有 node，记录无法运行。

### Task 2.11：实现客户管理页面

**Files:**
- Create: `static/clients.html`
- Create: `static/clients.js`
- Modify: `templates/index.html`

**Goal:** 提供可用的客户列表、新建客户、搜索、打开详情能力。

- [ ] **Step 1：创建 `static/clients.html`**

包含：搜索框、标签筛选、新建客户按钮、客户列表容器、详情容器。

- [ ] **Step 2：创建 `static/clients.js`**

实现：加载客户列表、渲染列表、新建客户表单提交、点击客户显示详情。

- [ ] **Step 3：在 `templates/index.html` 增加入口**

添加一个「客户管理」链接到 `/static/clients.html`。

- [ ] **Step 4：手动验证页面加载**

启动服务：

```bash
python api_server.py
```

打开：

```text
http://localhost:8000/static/clients.html
```

Expected: 页面无 JS 报错，能创建并显示客户。

### Task 2.12：实现分析时间线和反馈按钮

**Files:**
- Create: `static/js/timeline.js`
- Create: `static/js/feedback.js`
- Modify: `static/clients.js`

**Goal:** 客户详情页显示历史分析，并允许提交准/不准反馈。

- [ ] **Step 1：创建 timeline 渲染函数**

输入 analyses 数组，输出时间线 DOM。

- [ ] **Step 2：创建 feedback 绑定函数**

对每条 analysis 渲染「准 / 不准 / 备注」控件。

- [ ] **Step 3：在客户详情中接入 timeline**

`static/clients.js` 加载 `listClientAnalyses(clientId)` 并渲染。

- [ ] **Step 4：手动测试反馈提交**

在页面点击准/不准，检查 `/api/feedback/stats` 统计变化。

---

## Phase 3：可视化与报告升级

### Task 3.1：为 visualization API 写测试

**Files:**
- Create: `tests/test_visualization_api.py`
- Modify later: `api_server.py`

**Goal:** 定义 `/api/charts/{chart_id}/visualization` 输出结构。

- [ ] **Step 1：创建测试**

流程：调用 `/api/chart` 生成 chart_id，再调用 visualization API。

- [ ] **Step 2：断言结构**

必须包含：`wuxing`、`shishen`、`dayun`、`liunian`。

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_visualization_api.py -v --tb=short
```

Expected: API 不存在而失败。

### Task 3.2：实现 visualization 数据构造函数

**Files:**
- Modify: `api_server.py`
- Possibly read: `bazi_calculator.py`

**Goal:** 后端统一图表数据契约。

- [ ] **Step 1：新增 helper `_build_visualization_data(chart)`**

返回：

```python
{
    "wuxing": ..., 
    "shishen": ..., 
    "dayun": ..., 
    "liunian": ...,
}
```

- [ ] **Step 2：兼容中文/英文五行字段**

`wuxing_stats` 可能有 `金` 或 `jin`，helper 中统一转成中文键。

- [ ] **Step 3：兼容大运字段差异**

从 `chart.get('da_yun', [])` 取数据，字段缺失时使用安全默认值。

- [ ] **Step 4：实现 API**

```python
@app.get("/api/charts/{chart_id}/visualization")
def api_chart_visualization(chart_id: str):
    chart = _get_chart(chart_id)
    if not chart:
        raise HTTPException(404, "Chart not found")
    return _build_visualization_data(chart)
```

- [ ] **Step 5：运行测试**

```bash
python -m pytest tests/test_visualization_api.py -v --tb=short
python -m py_compile api_server.py
```

Expected: 通过。

### Task 3.3：新增 ECharts 封装

**Files:**
- Create: `static/js/charts.js`
- Create: `static/css/charts.css`

**Goal:** 前端可复用四类图表。

- [ ] **Step 1：创建 `static/js/charts.js`**

导出 `BaZiCharts` 对象，包含四个 render 函数。

- [ ] **Step 2：每个 render 函数先校验 ECharts 是否存在**

如果 `window.echarts` 不存在，在容器中显示提示文本。

- [ ] **Step 3：创建 `static/css/charts.css`**

定义 `.chart-grid`、`.chart-card`、`.chart-container`。

- [ ] **Step 4：语法检查**

```bash
node --check static/js/charts.js
```

Expected: 通过。如果无 node，记录无法运行。

### Task 3.4：接入图表 Tab 到主页面

**Files:**
- Modify: `static/app.js`
- Modify: `templates/index.html` or current static HTML entry

**Goal:** 分析页可查看可视化数据。

- [ ] **Step 1：确认 ECharts 是否已引入**

检查 `templates/index.html` 是否包含 ECharts CDN。如果没有，新增 script。

- [ ] **Step 2：在报告/分析区域新增「可视化」Tab**

不要重构现有布局，只增加入口。

- [ ] **Step 3：在选择 chart 后请求 visualization API**

调用 `/api/charts/{chart_id}/visualization`。

- [ ] **Step 4：调用 `BaZiCharts` 渲染四类图表**

确保容器存在再渲染。

- [ ] **Step 5：手动验证**

启动服务，生成命盘，点击可视化 Tab。Expected: 四个图表区域正常显示或显示无数据提示。

### Task 3.5：为 report_to_pdf 图片插入写测试

**Files:**
- Modify: `tests/test_report_to_pdf.py`
- Modify later: `report_to_pdf.py`

**Goal:** PDF 支持图表 PNG 插入，不破坏原 Markdown 转 PDF。

- [ ] **Step 1：查看现有 `tests/test_report_to_pdf.py`**

确认测试如何生成临时 Markdown 和 PDF。

- [ ] **Step 2：新增图片占位符测试**

Markdown 示例：

```markdown
# 测试报告

![五行图](test_chart.png)
```

测试目标：生成 PDF 不抛异常。

- [ ] **Step 3：运行预期失败或跳过测试**

```bash
python -m pytest tests/test_report_to_pdf.py -v --tb=short
```

Expected: 如果当前不支持图片，新增测试失败。

### Task 3.6：实现 report_to_pdf 图片支持

**Files:**
- Modify: `report_to_pdf.py`

**Goal:** Markdown 中的本地图片或临时图表图片可插入 PDF。

- [ ] **Step 1：扩展 Markdown parser**

在 `parse_markdown_to_blocks()` 中识别：

```text
![alt](path)
```

输出 block：`('image', {'alt': alt, 'path': path})`。

- [ ] **Step 2：新增 `draw_image()` 方法**

在 `BaziReportPDF` 中新增方法，检查文件存在后调用 `self.image()`。

- [ ] **Step 3：在 generate_pdf 循环中处理 image block**

```python
elif btype == 'image':
    pdf.draw_image(content)
```

- [ ] **Step 4：运行 PDF 测试**

```bash
python -m pytest tests/test_report_to_pdf.py -v --tb=short
python -m py_compile report_to_pdf.py
```

Expected: 通过。

### Task 3.7：实现命理卡片页面

**Files:**
- Create: `static/js/card.js`
- Create: `static/card.html`

**Goal:** 可基于 chart/analysis 生成 PNG 卡片。

- [ ] **Step 1：创建 Canvas 页面**

`static/card.html` 包含 chart_id 输入、生成按钮、canvas、下载按钮。

- [ ] **Step 2：创建 `static/js/card.js`**

实现：加载 chart data、绘制背景、标题、八字、核心断语、品牌信息。

- [ ] **Step 3：实现下载 PNG**

使用 `canvas.toDataURL('image/png')`。

- [ ] **Step 4：手动验证**

打开 `/static/card.html`，输入 chart_id，点击生成和下载。

---

## Phase 4：数据飞轮与增长

### Task 4.1：实现反馈分析脚本测试

**Files:**
- Create: `tests/test_feedback_analysis.py`
- Create later: `quality/feedback_analysis.py`

**Goal:** 对 feedback 数据生成统计和 Prompt 优化建议。

- [ ] **Step 1：创建测试数据**

使用临时 SQLite 或 monkeypatch data_store，准备准确/不准确反馈。

- [ ] **Step 2：断言输出结构**

必须包含：`dimension_accuracy`、`worst_dimensions`、`top_inaccurate_judgments`、`prompt_suggestions`。

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_feedback_analysis.py -v --tb=short
```

Expected: 模块不存在而失败。

### Task 4.2：实现反馈分析脚本

**Files:**
- Create: `quality/feedback_analysis.py`

**Goal:** 从 `bazi_data.db` 汇总反馈。

- [ ] **Step 1：实现 `analyze_feedback(db_path)`**

使用 sqlite3 查询 feedback 表，按 dimension 聚合准确率。

- [ ] **Step 2：实现不准断语 Top N**

查询 `is_accurate = 0`，按 `judgment_text` 分组计数。

- [ ] **Step 3：生成 Prompt 优化建议**

对准确率最低的维度输出建议文本。

- [ ] **Step 4：增加 CLI**

```bash
python quality/feedback_analysis.py
```

默认读取根目录 `bazi_data.db` 并输出 JSON。

- [ ] **Step 5：运行测试**

```bash
python -m pytest tests/test_feedback_analysis.py -v --tb=short
python -m py_compile quality/feedback_analysis.py
```

Expected: 通过。

### Task 4.3：实现节气提醒脚本测试

**Files:**
- Create: `tests/test_solar_term_push.py`
- Create later: `quality/solar_term_push.py`

**Goal:** 从 `knowledge-base/solar_terms.json` 解析未来 N 天节气。

- [ ] **Step 1：创建最小数据测试**

用 dict：`{"2026|立春": [2, 4, 10, 0, True]}`。

- [ ] **Step 2：测试 `get_upcoming_terms()`**

today = 2026-02-02，days_ahead=3，应该返回立春。

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_solar_term_push.py -v --tb=short
```

Expected: 模块不存在而失败。

### Task 4.4：实现节气提醒脚本

**Files:**
- Create: `quality/solar_term_push.py`

**Goal:** 支持应用内节气提醒数据生成。

- [ ] **Step 1：实现 `load_solar_terms(path)`**

读取 JSON。

- [ ] **Step 2：实现 `get_upcoming_terms(data, today, days_ahead=3)`**

解析 key：`year|term_name`，value：`[month, day, hour, minute, is_jie]`。

- [ ] **Step 3：实现 `generate_push_message(client_name, term_name)`**

返回短提示文本。

- [ ] **Step 4：增加 CLI smoke**

默认读取 `knowledge-base/solar_terms.json`，输出未来 3 天节气。

- [ ] **Step 5：运行测试**

```bash
python -m pytest tests/test_solar_term_push.py -v --tb=short
python -m py_compile quality/solar_term_push.py
```

Expected: 通过。

### Task 4.5：增强品牌卡片

**Files:**
- Modify: `static/js/card.js`
- Modify: `static/card.html`

**Goal:** 命理卡片支持命理师姓名、联系方式和品牌信息。

- [ ] **Step 1：在 card.html 增加品牌信息输入框**

字段：命理师姓名、联系方式、品牌口号。

- [ ] **Step 2：在 card.js 绘制底部品牌区域**

包含姓名、联系方式、品牌口号。

- [ ] **Step 3：保存本地偏好**

使用 localStorage 保存命理师品牌信息。

- [ ] **Step 4：手动验证**

刷新页面后品牌信息仍保留。

---

## Final Verification：全量验证

### Task 5.1：运行后端语法和测试

**Files:**
- All modified Python files

- [ ] **Step 1：运行语法检查**

```bash
python -m py_compile api_server.py data_store.py auto_analyzer.py claude_api.py prompt_engine.py report_builder.py report_to_pdf.py quality/llm_quality_test.py quality/feedback_analysis.py quality/solar_term_push.py
```

Expected: 全部通过。

- [ ] **Step 2：运行目标测试**

```bash
python -m pytest tests/test_prompt_engine.py tests/test_llm_quality.py tests/test_data_store.py tests/test_clients_api.py tests/test_visualization_api.py tests/test_feedback_analysis.py tests/test_solar_term_push.py -v --tb=short
```

Expected: 全部通过。

- [ ] **Step 3：运行现有主测试**

```bash
python -m pytest tests/ -v --tb=short --timeout=120
```

Expected: 记录所有失败。如果失败为本次修改引入，必须修复；如果是历史失败，记录但不扩大范围。

### Task 5.2：运行前端语法检查

**Files:**
- `static/js/client-api.js`
- `static/clients.js`
- `static/js/timeline.js`
- `static/js/feedback.js`
- `static/js/charts.js`
- `static/js/card.js`

- [ ] **Step 1：如果 Node 可用，运行 JS 语法检查**

```bash
node --check static/js/client-api.js
node --check static/clients.js
node --check static/js/timeline.js
node --check static/js/feedback.js
node --check static/js/charts.js
node --check static/js/card.js
```

Expected: 全部通过。

### Task 5.3：手动端到端验证

**Files:**
- Runtime verification

- [ ] **Step 1：启动服务**

```bash
python api_server.py
```

- [ ] **Step 2：验证现有排盘流程**

打开首页，输入出生信息，确认生成 chart_id 和命盘。

- [ ] **Step 3：验证流式分析**

发送一个问题，确认 SSE 输出 reply/report/done，且 done 包含 analysis_id。

- [ ] **Step 4：验证客户管理**

打开 `/static/clients.html`，创建客户，关联命盘，查看分析历史。

- [ ] **Step 5：验证反馈**

对分析提交准/不准，检查 `/api/feedback/stats`。

- [ ] **Step 6：验证可视化**

打开可视化 Tab，确认四类图表显示。

- [ ] **Step 7：验证 PDF**

调用现有 PDF 导出流程，确认 `/api/jobs/{job_id}/download` 可下载 PDF。

- [ ] **Step 8：验证命理卡片**

打开 `/static/card.html`，生成并下载 PNG。

---

## Implementation Notes

1. 每个 Task 完成后立即运行该 Task 的测试，不要等到最后。
2. 如果已有测试失败，先判断是否本次修改引入；不是本次引入则记录，不扩大范围。
3. 新增功能优先写后端测试，再写实现，再接前端。
4. 不要删除旧 API、旧表、旧报告链路。
5. 不要在没有用户明确授权时提交 Git commit。
6. 如果某一步需要外部 API Key，必须提供无 API Key 的 fallback 测试路径。
