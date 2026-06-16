# 玄机子 Trust Engine Sprint 1 可执行实施计划

> **For agentic workers:** 使用 executing-plans 按 Task 顺序执行。每个 Step 使用 checkbox (`- [ ]`) 跟踪。严格小步提交，每个 Task 完成后运行对应测试。除非用户明确要求，不要提交 Git commit。

**Goal:** 基于 `docs/superpowers/specs/2026-06-16-xuanjizi-baziqa-trust-engine-design.md` 实现 Trust Engine Sprint 1：结构化推理协议、模型输出追踪、Prompt 版本化、chat_stream 记录、BaziQA mini benchmark 的最小可运行闭环。

**Source Spec:** `docs/superpowers/specs/2026-06-16-xuanjizi-baziqa-trust-engine-design.md`

**Architecture:** 保留现有 FastAPI + SQLite + PromptEngine + `claude_api.py` 流式输出架构。新增能力不重写现有聊天、报告、PDF、客户系统，只在当前链路中记录 model_outputs，并新增 benchmark 目录作为内部评测工具。

**Tech Stack:** Python 3.11+, FastAPI, SQLite, pytest, vanilla JS（本 Sprint 不涉及前端 UI）, DeepSeek/Claude compatible API, stdlib json/hashlib/dataclasses。

**Non-goals:** 不实现人生 K 线 2.0；不实现 `/benchmark` 前端页面；不引入外部 BaziQA 原始完整数据；不做多模型并发评测；不引入向量数据库；不引入新 ORM；不改变用户可见聊天 UI；不要求一次性解析所有 AI 输出为完美 JSON。

---

## Phase 0：基线确认与范围冻结

### Task 0.1：确认当前代码基线

**Files:**
- Read: `api_server.py`
- Read: `data_store.py`
- Read: `prompt_engine.py`
- Read: `claude_api.py`
- Read: `tests/test_api.py`
- Read: `tests/test_data_store.py`
- Read: `tests/test_prompt_engine.py`

**Goal:** 在修改前确认当前测试、数据层和 PromptEngine 契约，避免破坏已有功能。

- [ ] **Step 1：查看 Git 工作区**

```bash
git status --short
```

Expected: 记录当前未提交文件。若存在用户未说明的代码改动，先停止并询问。

- [ ] **Step 2：运行基础语法检查**

```bash
python -m py_compile api_server.py data_store.py prompt_engine.py claude_api.py
```

Expected: 无语法错误。

- [ ] **Step 3：运行数据层与 PromptEngine 测试**

```bash
python -m pytest tests/test_data_store.py tests/test_prompt_engine.py -q --tb=short
```

Expected: 测试通过，若失败先记录，不在此 Task 修复非相关历史问题。

- [ ] **Step 4：运行 API 基础测试**

```bash
python -m pytest tests/test_api.py -q --tb=short
```

Expected: 测试通过。

---

## Phase 1：SRP-v1 协议文档

### Task 1.1：创建结构化推理协议文档

**Files:**
- Create: `prompts/structured_reasoning_v1.md`

**Goal:** 把 Xuanjizi-SRP-v1 固化为独立 prompt 协议文档，后续 PromptEngine 可读取/引用。

- [ ] **Step 1：创建 `prompts/` 目录（如不存在）**

```bash
python -c "import os; os.makedirs('prompts', exist_ok=True)"
```

Expected: `prompts/` 目录存在。

- [ ] **Step 2：写入 SRP-v1 文档**

文档必须包含以下章节：

```text
# Xuanjizi-SRP-v1 结构化推理协议
1. 角色与边界
2. 六层推理流程
3. 输出安全要求
4. 系统结构化 JSON 字段
5. 用户可读 Markdown 字段
6. 禁止事项
```

- [ ] **Step 3：安全边界必须明确写入**

必须包含以下限制：

```text
不做绝对化预测
不替代医疗诊断
不提供投资指令
不替用户决定婚姻/职业/生育等重大选择
必须用“倾向、可能、建议关注”表达
```

- [ ] **Step 4：运行简单内容检查**

```bash
python -c "p='prompts/structured_reasoning_v1.md'; s=open(p,encoding='utf-8').read(); assert '六层推理' in s and '结构化 JSON' in s and '不做绝对化预测' in s; print('OK')"
```

Expected: 输出 `OK`。

### Task 1.2：为 SRP 文档写最小测试

**Files:**
- Create: `tests/test_structured_reasoning_prompt.py`

**Goal:** 防止协议文档被误删或关键字段缺失。

- [ ] **Step 1：创建测试文件**

测试应断言文档存在，且包含：

```text
Xuanjizi-SRP-v1
命盘基础扫描
结构关系识别
强弱与冲突定级
领域映射
事件映射
用户可读表达
不做绝对化预测
```

- [ ] **Step 2：运行测试**

```bash
python -m pytest tests/test_structured_reasoning_prompt.py -q
```

Expected: 通过。

---

## Phase 2：model_outputs 数据层

### Task 2.1：先写 model_outputs 数据层测试

**Files:**
- Edit: `tests/test_data_store.py`
- Later edit: `data_store.py`

**Goal:** 先定义 model_outputs 的数据契约，再实现表和 CRUD。

- [ ] **Step 1：在 `tests/test_data_store.py` 添加 `test_save_and_get_model_output`**

测试准备数据：

```python
payload = {
    "analysis_id": "analysis-1",
    "chart_id": "chart-1",
    "client_id": "client-1",
    "provider": "deepseek",
    "model": "deepseek-v4-pro",
    "method": "structured",
    "prompt_version": "srp_v1",
    "reasoning_protocol": "xuanjizi_srp_v1",
    "domain": "career",
    "question": "请分析事业",
    "input_hash": "abc123",
    "raw_prompt": "prompt text",
    "raw_output": "answer text",
    "parsed_answer": None,
    "structured_reasoning_json": {"confidence": 0.7},
    "latency_ms": 1234,
    "token_estimate": 1000,
    "cost_estimate": 0.01,
}
```

期望：

```python
saved = data_store.save_model_output(**payload)
assert saved["id"]
loaded = data_store.get_model_output(saved["id"])
assert loaded["model"] == "deepseek-v4-pro"
assert loaded["structured_reasoning_json"]["confidence"] == 0.7
```

- [ ] **Step 2：添加 `test_list_model_outputs_for_chart`**

期望：

```python
items = data_store.list_model_outputs(chart_id="chart-1")
assert len(items) >= 1
```

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_data_store.py -q --tb=short
```

Expected: 因 `save_model_output` 不存在而失败。

### Task 2.2：实现 model_outputs 表迁移

**Files:**
- Edit: `data_store.py`

**Goal:** 在 `_ensure_schema()` 中创建 `model_outputs` 表，保持向后兼容。

- [ ] **Step 1：在 schema 中加入 CREATE TABLE**

字段按设计文档实现：

```sql
CREATE TABLE IF NOT EXISTS model_outputs (
    id TEXT PRIMARY KEY,
    analysis_id TEXT,
    chart_id TEXT,
    client_id TEXT,
    provider TEXT,
    model TEXT,
    method TEXT,
    prompt_version TEXT,
    reasoning_protocol TEXT,
    domain TEXT,
    question TEXT,
    input_hash TEXT,
    raw_prompt TEXT,
    raw_output TEXT,
    parsed_answer TEXT,
    structured_reasoning_json TEXT,
    latency_ms INTEGER,
    token_estimate INTEGER,
    cost_estimate REAL,
    created_at TEXT
)
```

- [ ] **Step 2：增加索引**

建议索引：

```sql
CREATE INDEX IF NOT EXISTS idx_model_outputs_chart_id ON model_outputs(chart_id)
CREATE INDEX IF NOT EXISTS idx_model_outputs_analysis_id ON model_outputs(analysis_id)
CREATE INDEX IF NOT EXISTS idx_model_outputs_prompt_version ON model_outputs(prompt_version)
```

- [ ] **Step 3：运行导入检查**

```bash
python -c "import data_store; data_store.init_db(); print('OK')"
```

Expected: 输出 `OK`。

### Task 2.3：实现 model_outputs CRUD

**Files:**
- Edit: `data_store.py`

**Goal:** 实现最小保存和查询函数。

- [ ] **Step 1：实现 `save_model_output(...)`**

要求：

1. 生成唯一 id。
2. `structured_reasoning_json` 允许 dict/list，入库前 `json.dumps(..., ensure_ascii=False)`。
3. 返回完整字典，且 JSON 字段反序列化。
4. created_at 使用现有时间函数/项目惯例。

- [ ] **Step 2：实现 `get_model_output(output_id)`**

要求：

1. 不存在返回 `None`。
2. JSON 字段返回 Python dict/list。

- [ ] **Step 3：实现 `list_model_outputs(chart_id=None, analysis_id=None, limit=50)`**

要求：

1. 支持 chart_id 过滤。
2. 支持 analysis_id 过滤。
3. 默认按 created_at DESC。
4. limit 防止返回过大。

- [ ] **Step 4：运行数据层测试**

```bash
python -m pytest tests/test_data_store.py -q --tb=short
```

Expected: 新增测试和旧测试全部通过。

---

## Phase 3：PromptEngine 版本化与协议接入

### Task 3.1：先扩展 PromptEngine 测试

**Files:**
- Edit: `tests/test_prompt_engine.py`
- Later edit: `prompt_engine.py`

**Goal:** PromptEngine 能暴露 prompt_version 和 reasoning_protocol，并在 prompt 中体现 SRP-v1。

- [ ] **Step 1：添加 `test_prompt_engine_exposes_version_metadata`**

期望：

```python
engine = PromptEngine(prompt_version="srp_v1", reasoning_protocol="xuanjizi_srp_v1")
assert engine.prompt_version == "srp_v1"
assert engine.reasoning_protocol == "xuanjizi_srp_v1"
```

- [ ] **Step 2：添加 `test_prompt_engine_srp_prompt_contains_required_stages`**

调用 `assemble(...)` 后断言 system_prompt 包含：

```text
命盘基础扫描
结构关系识别
强弱与冲突定级
领域映射
事件映射
用户可读表达
```

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_prompt_engine.py -q --tb=short
```

Expected: 因构造函数参数或内容缺失而失败。

### Task 3.2：实现 PromptEngine 版本化

**Files:**
- Edit: `prompt_engine.py`

**Goal:** 保持旧调用兼容，同时允许新参数。

- [ ] **Step 1：修改 `PromptEngine.__init__`**

新增可选参数：

```python
prompt_version="srp_v1"
reasoning_protocol="xuanjizi_srp_v1"
```

保留旧调用 `PromptEngine()` 可用。

- [ ] **Step 2：读取 SRP 文档**

实现一个私有方法：

```python
_load_structured_reasoning_protocol()
```

要求：

1. 读取 `prompts/structured_reasoning_v1.md`。
2. 文件不存在时返回内置短协议，不让服务崩溃。
3. 不引入新依赖。

- [ ] **Step 3：把 SRP 摘要注入 system_prompt**

要求：

1. system_prompt 中包含 prompt_version 和 reasoning_protocol。
2. system_prompt 包含六层推理标题。
3. 仍保留当前“核心判断 / 证据链 / 建议边界”等约束。

- [ ] **Step 4：运行 PromptEngine 测试**

```bash
python -m pytest tests/test_prompt_engine.py tests/test_structured_reasoning_prompt.py -q --tb=short
```

Expected: 全部通过。

---

## Phase 4：chat_stream 保存 model_outputs

### Task 4.1：为 chat_stream 记录写 API 测试

**Files:**
- Edit: `tests/test_api.py`
- Later edit: `api_server.py`

**Goal:** SSE 分析完成时，除 analyses 外，还会产生 model_outputs 记录。

- [ ] **Step 1：查找现有 chat_stream 测试**

在 `tests/test_api.py` 搜索：

```text
chat/stream
analysis_id
```

找到可复用测试或决定新增一个最小测试。

- [ ] **Step 2：新增测试 `test_chat_stream_saves_model_output`**

建议测试方式：

1. monkeypatch `claude_api.stream_chat` 为本地 generator，避免真实 LLM。
2. 创建 chart。
3. 调用 `/api/chat/stream?...`。
4. 读取 SSE 直到 done。
5. 用 `data_store.list_model_outputs(chart_id=chart_id)` 检查至少 1 条记录。

期望字段：

```python
assert output["provider"]
assert output["model"]
assert output["prompt_version"] == "srp_v1"
assert output["reasoning_protocol"] == "xuanjizi_srp_v1"
assert "请" in output["question"]
assert output["raw_output"]
```

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_api.py -q --tb=short
```

Expected: 因尚未保存 model_outputs 而失败。

### Task 4.2：在 claude_api 暴露 provider/model 元数据

**Files:**
- Edit: `claude_api.py`
- Edit: `tests/test_claude_api.py`（如已有相关测试）

**Goal:** 让 api_server 不重复猜测 provider/model。

- [ ] **Step 1：新增函数 `get_ai_config()`**

返回：

```python
{
    "provider": provider,
    "model": model,
    "key_configured": bool(ANTHROPIC_API_KEY),
}
```

不能返回完整 key。

- [ ] **Step 2：添加或更新测试**

断言：

```python
cfg = claude_api.get_ai_config()
assert "provider" in cfg
assert "model" in cfg
assert "key_configured" in cfg
assert "key" not in cfg
```

- [ ] **Step 3：运行 claude_api 测试**

```bash
python -m pytest tests/test_claude_api.py -q --tb=short
```

Expected: 通过。

### Task 4.3：保存 model_outputs

**Files:**
- Edit: `api_server.py`

**Goal:** 在 `chat_stream` 完成汇总文本后保存 model_outputs。

- [ ] **Step 1：定位 save_analysis 逻辑**

在 `api_server.py` 搜索：

```text
save_analysis
analysis_id
_sse_event('done'
```

- [ ] **Step 2：在 save_analysis 成功后调用 `save_model_output`**

保存字段：

```python
analysis_id=analysis_id
chart_id=chart_id
client_id=_client_id
provider=claude_api.get_ai_config()["provider"]
model=claude_api.get_ai_config()["model"]
method="structured"
prompt_version=prompt_engine.prompt_version
reasoning_protocol=prompt_engine.reasoning_protocol
domain=report_tab
question=message
input_hash=<hash of chart_id + message + report_tab + prompt_version>
raw_prompt=<可以先保存 user prompt 摘要或空字符串，避免过大>
raw_output=report_text or reply_text
parsed_answer=None
structured_reasoning_json={"local_analysis": conclusions, "confidence": None}
```

- [ ] **Step 3：实现 input_hash**

使用 stdlib：

```python
hashlib.sha256(...).hexdigest()
```

不要把 API key 或密钥放入 hash 原文。

- [ ] **Step 4：失败不能影响 SSE done**

`save_model_output` 应与 `save_analysis` 一样被 try/except 包住。保存失败时记录或静默，不应导致用户对话失败。

- [ ] **Step 5：运行 API 测试**

```bash
python -m pytest tests/test_api.py -q --tb=short
```

Expected: 新增测试通过，旧测试通过。

---

## Phase 5：BaziQA mini dataset 与 choice scorer

### Task 5.1：创建 benchmark 目录结构

**Files:**
- Create: `benchmark/datasets/baziqa_mini_v1.jsonl`
- Create: `benchmark/scorers/choice_accuracy.py`
- Create: `benchmark/__init__.py`
- Create: `benchmark/scorers/__init__.py`
- Create: `tests/test_benchmark_choice_accuracy.py`

**Goal:** 建立最小 benchmark 框架，不引入完整 BaziQA 数据。

- [ ] **Step 1：创建目录**

```bash
python -c "import os; [os.makedirs(p, exist_ok=True) for p in ['benchmark/datasets','benchmark/scorers','benchmark/outputs']]"
```

- [ ] **Step 2：创建 package init 文件**

```bash
python -c "from pathlib import Path; [Path(p).touch() for p in ['benchmark/__init__.py','benchmark/scorers/__init__.py']]"
```

- [ ] **Step 3：写入 5 条 mini 样本**

`baziqa_mini_v1.jsonl` 每行一个 JSON，字段：

```json
{
  "case_id": "career_001",
  "domain": "career",
  "person": {
    "name": "命主001",
    "gender": "male",
    "birth": {"year": 1990, "month": 3, "day": 12, "hour": 9, "minute": 0, "place": "北京"}
  },
  "question": "此命主事业发展更偏稳定组织还是市场创业？",
  "options": ["A. 稳定组织", "B. 市场创业", "C. 艺术自由职业", "D. 不宜工作"],
  "answer": "A",
  "expected_evidence": ["官星有力", "印星配合"],
  "difficulty": "medium"
}
```

要求 5 条样本覆盖至少 3 个 domain：

```text
career
wealth
relationship
health
annual_fortune
```

### Task 5.2：先写 choice scorer 测试

**Files:**
- Create: `tests/test_benchmark_choice_accuracy.py`

**Goal:** 定义选择题评分器契约。

- [ ] **Step 1：测试单题正确**

```python
from benchmark.scorers.choice_accuracy import score_choice_answers


def test_score_choice_answers_counts_accuracy():
    cases = [{"id": "q1", "answer": "A"}, {"id": "q2", "answer": "B"}]
    preds = {"q1": "A", "q2": "C"}
    result = score_choice_answers(cases, preds)
    assert result["total"] == 2
    assert result["correct"] == 1
    assert result["accuracy"] == 0.5
```

- [ ] **Step 2：测试大小写和文本抽取**

输入 `"答案：A"`、`"我选择 b"` 应能解析为 A/B。

- [ ] **Step 3：运行预期失败测试**

```bash
python -m pytest tests/test_benchmark_choice_accuracy.py -q --tb=short
```

Expected: 因 scorer 不存在而失败。

### Task 5.3：实现 choice_accuracy scorer

**Files:**
- Create: `benchmark/scorers/choice_accuracy.py`

**Goal:** 支持基础准确率和 domain breakdown。

- [ ] **Step 1：实现 `extract_choice(text)`**

规则：

1. 如果输入是 `A/B/C/D`，直接返回大写。
2. 如果包含 `答案：A`、`选择 A`、`我选B`，提取字母。
3. 无法解析返回 `None`。

- [ ] **Step 2：实现 `score_choice_answers(cases, predictions)`**

返回：

```python
{
    "total": 5,
    "correct": 3,
    "accuracy": 0.6,
    "by_domain": {
        "career": {"total": 2, "correct": 1, "accuracy": 0.5}
    },
    "missing": [...]
}
```

- [ ] **Step 3：实现 JSONL 读取辅助函数 `load_jsonl(path)`**

用于后续 runner。

- [ ] **Step 4：运行 scorer 测试**

```bash
python -m pytest tests/test_benchmark_choice_accuracy.py -q --tb=short
```

Expected: 通过。

### Task 5.4：验证 mini dataset 可读取

**Files:**
- Edit: `tests/test_benchmark_choice_accuracy.py`

**Goal:** 保证 jsonl 样本格式有效。

- [ ] **Step 1：添加 dataset 测试**

断言：

```python
cases = load_jsonl('benchmark/datasets/baziqa_mini_v1.jsonl')
assert len(cases) >= 5
for c in cases:
    assert c['case_id']
    assert c['domain']
    assert c['person']['birth']['year']
    assert c['question']
    assert c['options']
    assert c['answer'] in ['A','B','C','D']
```

- [ ] **Step 2：运行测试**

```bash
python -m pytest tests/test_benchmark_choice_accuracy.py -q --tb=short
```

Expected: 通过。

---

## Phase 6：最小 Benchmark Runner（可选但推荐纳入 Sprint 1）

### Task 6.1：创建离线 runner，不调用真实 LLM

**Files:**
- Create: `benchmark/runners/run_benchmark.py`
- Create: `benchmark/runners/__init__.py`
- Create: `tests/test_benchmark_runner.py`

**Goal:** 先跑通“读取 cases + 读取 predictions + 输出评分”的离线链路，避免一开始绑定真实模型调用。

- [ ] **Step 1：创建 runner 测试**

测试输入：

```python
cases = [
    {"case_id": "q1", "domain": "career", "answer": "A"},
    {"case_id": "q2", "domain": "wealth", "answer": "B"},
]
preds = {"q1": "A", "q2": "C"}
```

期望：

```python
result = run_offline_benchmark(cases, preds)
assert result["accuracy"] == 0.5
```

- [ ] **Step 2：运行预期失败测试**

```bash
python -m pytest tests/test_benchmark_runner.py -q --tb=short
```

Expected: runner 不存在而失败。

### Task 6.2：实现离线 runner

**Files:**
- Create: `benchmark/runners/run_benchmark.py`

**Goal:** 提供最小 CLI，后续 Sprint 2 扩展为真实模型 runner。

- [ ] **Step 1：实现 `run_offline_benchmark(cases, predictions)`**

内部调用 `score_choice_answers`。

- [ ] **Step 2：实现 CLI**

命令：

```bash
python -m benchmark.runners.run_benchmark --dataset benchmark/datasets/baziqa_mini_v1.jsonl --predictions benchmark/outputs/sample_predictions.json
```

`sample_predictions.json` 格式：

```json
{
  "career_001": "A",
  "wealth_001": "答案：B"
}
```

- [ ] **Step 3：没有 predictions 文件时给出清晰错误**

不要静默失败。

- [ ] **Step 4：运行 runner 测试**

```bash
python -m pytest tests/test_benchmark_runner.py tests/test_benchmark_choice_accuracy.py -q --tb=short
```

Expected: 通过。

---

## Phase 7：API 查询 model_outputs（可选薄 API）

### Task 7.1：添加只读 API 测试

**Files:**
- Edit: `tests/test_api.py`
- Later edit: `api_server.py`

**Goal:** 提供最小只读接口，便于后续 UI 和调试。

- [ ] **Step 1：新增测试 `test_list_model_outputs_for_chart_api`**

流程：

1. 直接 `data_store.save_model_output(...)` 创建记录。
2. 请求 `GET /api/charts/{chart_id}/model-outputs`。
3. 断言返回列表包含该记录。

- [ ] **Step 2：运行预期失败测试**

```bash
python -m pytest tests/test_api.py -q --tb=short
```

Expected: 404 或接口不存在。

### Task 7.2：实现只读 API

**Files:**
- Edit: `api_server.py`

**Goal:** 不做复杂权限，先提供内部调试接口。

- [ ] **Step 1：新增路由**

```python
@app.get("/api/charts/{chart_id}/model-outputs")
def api_list_model_outputs(chart_id: str, limit: int = 50):
    ...
```

- [ ] **Step 2：限制 limit**

`limit` 最大 200，防止一次返回太多。

- [ ] **Step 3：运行 API 测试**

```bash
python -m pytest tests/test_api.py -q --tb=short
```

Expected: 通过。

---

## Phase 8：全量验证

### Task 8.1：运行 Sprint 1 相关测试

**Files:**
- All modified files

**Goal:** 保证新增能力不破坏现有功能。

- [ ] **Step 1：运行 Python 语法检查**

```bash
python -m py_compile api_server.py data_store.py prompt_engine.py claude_api.py benchmark/scorers/choice_accuracy.py benchmark/runners/run_benchmark.py
```

Expected: 无错误。

- [ ] **Step 2：运行单元测试集合**

```bash
python -m pytest tests/test_data_store.py tests/test_prompt_engine.py tests/test_structured_reasoning_prompt.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_claude_api.py tests/test_api.py -q --tb=short
```

Expected: 全部通过。

- [ ] **Step 3：运行非 e2e 全量测试**

```bash
python -m pytest tests/ -q --tb=short --ignore=tests/test_e2e.py
```

Expected: 全部通过。

- [ ] **Step 4：运行 benchmark 离线 smoke test**

先创建 sample predictions：

```bash
python -c "import json, pathlib; pathlib.Path('benchmark/outputs').mkdir(parents=True, exist_ok=True); json.dump({'career_001':'A'}, open('benchmark/outputs/sample_predictions.json','w',encoding='utf-8'), ensure_ascii=False)"
```

再运行：

```bash
python -m benchmark.runners.run_benchmark --dataset benchmark/datasets/baziqa_mini_v1.jsonl --predictions benchmark/outputs/sample_predictions.json
```

Expected: 输出 total / correct / accuracy / by_domain。

### Task 8.2：手工 SSE 验证 model_outputs 落库

**Files:**
- Runtime verification only

**Goal:** 用真实服务走一次 chat_stream，确认 analyses 和 model_outputs 都落库。

- [ ] **Step 1：启动服务**

```powershell
.\start.ps1
```

或者：

```bash
python api_server.py
```

- [ ] **Step 2：创建命主**

调用：

```text
POST /api/chart
```

- [ ] **Step 3：发起 SSE**

调用：

```text
GET /api/chat/stream?chart_id=...&message=请分析事业&report_tab=career
```

- [ ] **Step 4：查询 model_outputs**

调用：

```text
GET /api/charts/{chart_id}/model-outputs
```

Expected: 返回至少一条记录，包含：

```text
provider
model
prompt_version=srp_v1
reasoning_protocol=xuanjizi_srp_v1
raw_output
structured_reasoning_json
```

---

## Phase 9：提交边界与回滚策略

### Task 9.1：检查变更范围

**Files:**
- Runtime only

**Goal:** 确保 Sprint 1 没有意外改 UI 或无关文件。

- [ ] **Step 1：查看状态**

```bash
git status --short
```

Expected 修改集中在：

```text
prompts/structured_reasoning_v1.md
data_store.py
prompt_engine.py
claude_api.py
api_server.py
benchmark/**
tests/**
```

- [ ] **Step 2：查看 diff 摘要**

```bash
git diff --stat
```

- [ ] **Step 3：不自动提交**

除非用户明确要求，否则不要执行 `git commit`。

### Task 9.2：回滚策略

若出现严重回归，可分层回滚：

1. 关闭 `chat_stream` 保存 model_outputs 调用，保留数据层。
2. 回退 PromptEngine SRP 注入，保留 prompt_version 属性。
3. 暂停 benchmark runner，不影响主服务。
4. 数据库新增表无需删除，因为 `CREATE TABLE IF NOT EXISTS` 向后兼容。

---

## Sprint 1 完成定义

必须满足以下条件才算完成：

```text
1. prompts/structured_reasoning_v1.md 存在并通过测试
2. model_outputs 表和 CRUD 通过测试
3. PromptEngine 支持 prompt_version / reasoning_protocol
4. chat_stream 完成后保存 model_outputs
5. benchmark/datasets/baziqa_mini_v1.jsonl 至少 5 条样本
6. choice_accuracy scorer 通过测试
7. 离线 runner 可运行并输出准确率
8. 非 e2e 测试通过
9. 手工 SSE 验证 model_outputs 落库
```

Sprint 1 完成后，再进入 Sprint 2：真实模型 benchmark runner、evidence/stability/safety scorer、Markdown benchmark report。
