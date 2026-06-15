# 「质量堡垒」路线图设计方案

**日期：** 2026-06-15  
**状态：** 已根据当前代码库修订  
**策略：** 方案 A「质量堡垒」— 先夯实 AI 分析质量，再扩展专业工作流、可视化和数据飞轮  
**开发资源：** 个人开发者 + AI 辅助，每周约 20-30 小时  
**适配代码库：** 当前项目以 FastAPI + SQLite + Claude 流式分析 + 本地规则引擎 + Markdown/PDF 报告为核心

---

## 一、修订说明

本版本修正了旧设计文档中与实际代码库不一致的部分。重点修正如下：

1. 移除对不存在的 `bazi_interpretor.py`、`PromptBuilder`、`BaZiInterpretor`、`DeepSeekAgent` 的依赖。
2. 将 AI 服务从 DeepSeek 修正为当前项目实际使用的 Anthropic Claude 调用链。
3. 将核心分析链路对齐到 `api_server.py` 的 `/api/chat/stream`、`auto_analyzer.py`、`claude_api.py`。
4. 将案例检索设计对齐到现有的 `knowledge-base/case_retrieval.py`。
5. 将数据库路径修正为项目根目录下的 `bazi_data.db`，并兼容现有 `charts`、`chat_history`、`reports` 三张表。
6. 将报告系统对齐到现有的 `report_builder.py` + `report_to_pdf.py` + 异步 PDF Job 系统。
7. 将节气数据来源修正为 `knowledge-base/solar_terms.json`。
8. 将 CI 设计对齐到现有 `.github/workflows/ci.yml` 的 Ubuntu 环境。

---

## 二、当前系统真实架构

当前系统已经具备可用原型能力：排盘、知识库检索、AI 流式问答、报告生成、PDF 导出、桌面客户端打包均已存在。真正需要补强的是「AI 分析深度」「专业工作流」「报告呈现能力」和「反馈闭环」。

### 2.1 当前核心链路

```text
用户输入出生信息
    ↓
api_server.py /api/chart
    ↓
bazi_calculator.compute_chart()
    ↓
生成 chart_id + chart_data
    ↓
data_store.py 保存 charts 表
    ↓
用户发起分析或问答
    ↓
api_server.py /api/chat/stream
    ↓
auto_analyzer.auto_analyze(chart)
    ↓
knowledge-base/bazi_kb.py fulltext_search()
    ↓
claude_api.stream_chat(enriched_chart, enriched_message)
    ↓
SSE 推送 reply/report/done
    ↓
前端展示分析结果
```

### 2.2 当前报告链路

```text
用户请求生成报告
    ↓
/api/analyze 或 /api/analyze/pdf
    ↓
report_builder.py build_report()
    ↓
生成 Markdown 报告
    ↓
report_to_pdf.py
    ↓
生成 PDF
    ↓
/api/jobs/{job_id}/download 下载
```

### 2.3 当前持久化模型

当前 `data_store.py` 自动初始化 `bazi_data.db`，已有三张表：

| 表 | 作用 |
|---|---|
| `charts` | 保存命盘基础数据，主键为 `chart_id` |
| `chat_history` | 保存每个命盘的对话记录 |
| `reports` | 保存每个命盘的报告 Tab 内容 |

后续专业工作流应在此基础上扩展，而不是推翻现有结构。

---

## 三、产品策略

### 3.1 定位

采用「两步走」：

1. 第一阶段先做命理师专业工具。
2. 第二阶段在分析质量和工作流稳定后，再向大众市场扩展。

### 3.2 三个核心痛点

1. **AI 分析不够深**：当前已有规则引擎和知识库，但 LLM 缺少优秀案例示范，容易输出泛泛结论。
2. **缺少专业工作流**：当前是命盘中心，不是客户中心；缺少客户档案、历史分析、反馈、复盘。
3. **可视化和报告呈现不足**：已有 PDF 生成能力，但图表、模板化排版、分享卡片还不够专业。

### 3.3 总体原则

1. 不重写已有能力，优先增强现有模块。
2. 不引入大型新架构，保持个人开发者可维护。
3. 所有质量改进都要可回归测试。
4. 先让命理师觉得「准、深、能用」，再做增长功能。

---

## 四、总体路线图

```text
                    Phase 4：数据飞轮
                    ┌─────────────────────────┐
                    │ 反馈闭环                 │
                    │ 节气提醒                 │
                    │ 品牌卡片分享             │
                    └───────────┬─────────────┘
                                │
                    Phase 3：可视化与报告升级
                    ┌───────────┴─────────────┐
                    │ ECharts 图表             │
                    │ Markdown/PDF 报告增强    │
                    │ 命理卡片                 │
                    └───────────┬─────────────┘
                                │
                    Phase 2：专业工作流
                    ┌───────────┴─────────────┐
                    │ 客户档案                 │
                    │ 分析历史                 │
                    │ 反馈记录                 │
                    └───────────┬─────────────┘
                                │
                    Phase 1：AI 质量地基
                    ┌───────────┴─────────────┐
                    │ PromptEngine             │
                    │ CaseRetriever 注入       │
                    │ 结构化输出约束           │
                    │ LLM 质量回归测试         │
                    └─────────────────────────┘
```

---

## 五、总时间表

```text
第 1-2 周：Phase 1 — AI 分析质量优化
    第 1 周：抽取 PromptEngine、接入 CaseRetriever Few-shot
    第 2 周：结构化输出约束、LLM 质量测试、CI 质量门禁

第 3-5 周：Phase 2 — 专业工作流 MVP
    第 3 周：扩展 SQLite，新增 clients / analyses / feedback
    第 4 周：新增客户管理 API + 前端页面
    第 5 周：分析历史、反馈记录、报告关联

第 6-7 周：Phase 3 — 可视化与报告升级
    第 6 周：ECharts 图表组件接入
    第 7 周：PDF 图表嵌入、命理卡片生成

第 8 周以后：Phase 4 — 数据飞轮和增长
    反馈统计、Prompt 优化建议、节气提醒、品牌分享卡片
```

---

## 六、Phase 1：AI 分析质量深度优化

**周期：** 2 周  
**成功标准：** LLM 输出具备明确结论、证据、反证据、置信度、实用建议；质量回归测试可重复运行。

### 6.1 当前问题

当前 `/api/chat/stream` 的分析链路已经能工作，但 Prompt 拼接逻辑集中在 `api_server.py` 内部，存在以下问题：

1. Prompt 拼接分散且不易测试。
2. `auto_analyzer.py` 已经生成结构化判断，但 LLM 没有被强制按结构输出。
3. `CaseRetriever` 已存在，但没有进入主分析 Prompt。
4. 知识库检索只有歌诀片段，缺少相似案例示范。
5. `quality/model_quality_test.py` 更偏向规则引擎评估，还没有专门评估 LLM 文本质量。

### 6.2 改进目标

将当前链路从：

```text
chat_stream() 内联拼 Prompt → Claude → 自由文本
```

升级为：

```text
chat_stream()
    ↓
auto_analyzer.auto_analyze(chart)
    ↓
PromptEngine.assemble(chart, pre_analysis, topic, question)
    ↓
CaseRetriever 注入相似案例
    ↓
知识库歌诀注入
    ↓
Claude 输出结构化 Markdown
    ↓
质量测试校验输出深度
```

### 6.3 新增 PromptEngine

建议新增 `prompt_engine.py`，避免继续加重 `api_server.py`。如果希望最小化文件数量，也可以先在 `api_server.py` 内部实现，稳定后再拆出。

```python
class PromptEngine:
    def assemble(self, chart, pre_analysis, topic, question):
        system_prompt = self.build_system_prompt(topic)
        domain_knowledge = self.build_domain_knowledge(chart, topic)
        dynamic_context = self.build_dynamic_context(chart, pre_analysis, question)
        return system_prompt, f"{domain_knowledge}\n\n---\n\n{dynamic_context}"

    def build_system_prompt(self, topic):
        return SYSTEM_PROMPTS.get(topic, SYSTEM_PROMPTS["sihechu"])

    def build_domain_knowledge(self, chart, topic):
        cases = self.retrieve_similar_cases(chart)
        gejue = self.retrieve_gejue(topic)
        warnings = self.match_warnings(chart)
        return self.format_domain_knowledge(cases, gejue, warnings)

    def build_dynamic_context(self, chart, pre_analysis, question):
        return self.format_chart_context(chart, pre_analysis, question)
```

### 6.4 三层 Prompt 结构

```text
第一层：系统指令
    角色设定
    输出结构
    置信度要求
    证据要求
    反证据要求
    禁止空泛表达

第二层：领域知识
    相似真实案例
    相关歌诀
    常见误判警示
    反例模式

第三层：动态上下文
    compute_chart() 输出
    auto_analyze() 输出
    当前问题
    当前分析主题
```

### 6.5 CaseRetriever 接入方式

现有 `knowledge-base/case_retrieval.py` 已具备案例检索能力。Phase 1 不应重写，而应增强它：

1. 在 `PromptEngine` 中调用 `CaseRetriever`。
2. 优先使用 `tests/benchmark_charts/` 的 52 个真实案例。
3. 同时支持 `data/celebrity_cases.json` 作为补充案例源。
4. 将相似案例格式化为 Few-shot 示例。

Few-shot 注入格式：

```text
【参考案例】
姓名：某真实案例
命局特点：日主、格局、旺衰、用神
关键断语：引用具体天干地支和十神关系
实际验证：对应人生事件
可借鉴点：本案例说明了什么判断规律
```

### 6.6 结构化输出约束

Claude 输出仍然保持 Markdown，便于前端和 `report_builder.py` 消费，但必须包含固定小节：

```text
## 核心判断
- 格局：...
- 用神：...
- 置信度：0.xx

## 证据链
1. 天干证据
2. 地支证据
3. 十神证据
4. 大运/流年证据

## 反证据与不确定性
- ...

## 分项分析
### 性格
### 事业
### 财运
### 感情
### 健康

## 实用建议
- ...
```

### 6.7 LLM 质量测试

在现有 `quality/model_quality_test.py` 基础上新增 LLM 输出质量评估，不替代原测试。

建议新增 `quality/llm_quality_test.py`：

```python
REQUIRED_SECTIONS = [
    "核心判断",
    "证据链",
    "反证据",
    "分项分析",
    "实用建议",
]

REQUIRED_TERMS = [
    "格局",
    "用神",
    "置信度",
    "天干",
    "地支",
    "十神",
]

def score_report(text):
    section_score = sum(1 for s in REQUIRED_SECTIONS if s in text) / len(REQUIRED_SECTIONS)
    term_score = sum(1 for t in REQUIRED_TERMS if t in text) / len(REQUIRED_TERMS)
    vague_penalty = min(text.count("可能") + text.count("也许") + text.count("大概"), 10) / 10
    return max(0, 0.5 * section_score + 0.5 * term_score - 0.2 * vague_penalty)
```

### 6.8 CI 质量门禁

现有 CI 使用 Ubuntu，应继续沿用。新增一个非阻塞到阻塞的渐进式门禁：

第一阶段：只生成报告，不阻塞合并。  
第二阶段：稳定后要求评分不低于阈值。

```yaml
- name: Run LLM quality smoke test
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    python quality/llm_quality_test.py
```

### 6.9 Phase 1 涉及文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `api_server.py` | 修改 | `/api/chat/stream` 改为调用 PromptEngine |
| `prompt_engine.py` | 新建 | 三层 Prompt 构建器 |
| `claude_api.py` | 小改 | 支持 system prompt 或增强消息输入 |
| `auto_analyzer.py` | 小改 | 补充结构化分析字段，供 PromptEngine 使用 |
| `knowledge-base/case_retrieval.py` | 修改 | 增加面向 Prompt 的案例格式化输出 |
| `quality/llm_quality_test.py` | 新建 | LLM 输出质量测试 |
| `.github/workflows/ci.yml` | 修改 | 增加质量测试步骤 |

### 6.10 Phase 1 不做的事

| 不做 | 原因 |
|---|---|
| 替换 Claude 为 DeepSeek | 当前系统已接入 Claude，先稳定一条链路 |
| 重写 CaseRetriever | 现有模块可复用 |
| 引入向量数据库 | 52 个案例 + SQLite/本地检索足够 |
| 本地模型微调 | 数据量不足，成本高 |
| 多 Agent 投票 | 当前瓶颈是 Prompt 和 Few-shot，不是 Agent 数量 |

---

## 七、Phase 2：专业工作流 MVP

**周期：** 3 周  
**成功标准：** 命理师可以管理客户、查看历史分析、保存报告、对分析结果进行反馈。

### 7.1 设计原则

当前系统是「命盘中心」，核心 ID 是 `chart_id`。专业工具需要「客户中心」，但不能破坏现有命盘模型。

因此采用兼容式扩展：

```text
clients
    ↓ 1:N
client_charts
    ↓ N:1
charts
    ↓ 1:N
analyses
    ↓ 1:N
feedback
```

### 7.2 数据库扩展

数据库仍使用项目根目录下的 `bazi_data.db`。保留现有表：

- `charts`
- `chat_history`
- `reports`

新增表：

```sql
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT CHECK(gender IN ('male', 'female')),
    birth_year INTEGER,
    birth_month INTEGER,
    birth_day INTEGER,
    birth_hour INTEGER,
    birth_minute INTEGER DEFAULT 0,
    birth_location TEXT DEFAULT 'Beijing',
    tags TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS client_charts (
    client_id TEXT NOT NULL,
    chart_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'primary',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (client_id, chart_id),
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    client_id TEXT,
    chart_id TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT 'sihechu',
    question TEXT NOT NULL DEFAULT '',
    ai_text TEXT NOT NULL DEFAULT '',
    structured_summary TEXT NOT NULL DEFAULT '{}',
    report_tab TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    judgment_text TEXT NOT NULL,
    is_accurate INTEGER NOT NULL CHECK(is_accurate IN (0, 1)),
    user_comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_clients_updated ON clients(updated_at);
CREATE INDEX IF NOT EXISTS idx_client_charts_client ON client_charts(client_id);
CREATE INDEX IF NOT EXISTS idx_analyses_client ON analyses(client_id, created_at);
CREATE INDEX IF NOT EXISTS idx_analyses_chart ON analyses(chart_id, created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_analysis ON feedback(analysis_id);
```

### 7.3 数据迁移策略

1. `data_store.init_db()` 增加新表创建语句。
2. 不迁移历史数据为客户，避免误绑定。
3. 在前端提供「从现有命盘创建客户」功能。
4. 旧的 `charts`、`chat_history`、`reports` 保持兼容。
5. 所有新表使用 `CREATE TABLE IF NOT EXISTS`，不破坏已有数据库。

### 7.4 API 设计

新增客户 API：

```text
GET    /api/clients
POST   /api/clients
GET    /api/clients/{client_id}
PUT    /api/clients/{client_id}
DELETE /api/clients/{client_id}
```

新增客户-命盘关联 API：

```text
POST   /api/clients/{client_id}/charts/{chart_id}
DELETE /api/clients/{client_id}/charts/{chart_id}
GET    /api/clients/{client_id}/charts
```

新增分析历史 API：

```text
GET  /api/clients/{client_id}/analyses
GET  /api/charts/{chart_id}/analyses
GET  /api/analyses/{analysis_id}
POST /api/analyses/{analysis_id}/feedback
GET  /api/feedback/stats
```

保留现有流式分析 API：

```text
GET /api/chat/stream?chart_id=...&message=...
```

在 SSE 完成时追加保存分析记录：

```text
chat_stream 完成
    ↓
将完整 reply_text/report_text 写入 analyses 表
    ↓
返回 done 事件时附带 analysis_id
```

### 7.5 前端页面

新增页面或组件：

| 文件 | 说明 |
|---|---|
| `static/clients.html` | 客户列表页 |
| `static/clients.js` | 客户 CRUD、搜索、标签 |
| `static/js/client-api.js` | 客户 API 封装 |
| `static/js/timeline.js` | 分析时间线 |
| `static/js/feedback.js` | 准/不准反馈按钮 |

客户列表 UI：

```text
客户管理                                  [+ 新建客户]
----------------------------------------------------
搜索框      标签：全部 / 婚姻 / 事业 / VIP / 回访
----------------------------------------------------
张三  男  1985-03-12  北京  [婚姻][VIP]  分析 3 次
李四  女  1990-11-08  上海  [事业]       分析 1 次
```

客户详情 UI：

```text
← 返回客户列表
张三 · 乾造 · 1985-03-12 06:00 · Beijing
[编辑资料] [关联命盘] [新建分析]

分析时间线
2026-06-15  四合出分析     [查看] [报告] [反馈]
2026-03-20  流年分析       [查看] [报告] [反馈]
2025-12-01  首次详批       [查看] [报告] [反馈]
```

### 7.6 Phase 2 涉及文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `data_store.py` | 修改 | 新增 clients / client_charts / analyses / feedback 表和 CRUD |
| `api_server.py` | 修改 | 新增客户、分析、反馈 API；chat_stream 完成后保存 analysis |
| `static/clients.html` | 新建 | 客户管理页面 |
| `static/clients.js` | 新建 | 页面逻辑 |
| `static/js/client-api.js` | 新建 | API 封装 |
| `static/js/timeline.js` | 新建 | 分析时间线 |
| `static/js/feedback.js` | 新建 | 反馈按钮逻辑 |
| `templates/index.html` | 修改 | 加入口或导航 |

### 7.7 Phase 2 不做的事

| 不做 | 原因 |
|---|---|
| 登录系统 | 桌面/本地优先，暂不需要 |
| 云同步 | 数据模型稳定后再做 |
| 支付系统 | 工具价值验证后再做 |
| 多租户权限 | 当前不是 SaaS |
| 复杂 CRM | 先完成客户、命盘、分析、反馈四件事 |

---

## 八、Phase 3：可视化与报告升级

**周期：** 2 周  
**成功标准：** 分析页支持核心图表，PDF 中文无乱码，报告可嵌入图表，命理卡片可下载。

### 8.1 图表数据契约

前端图表不要直接猜字段，应由 API 输出统一图表数据。

新增 API：

```text
GET /api/charts/{chart_id}/visualization
```

返回结构：

```json
{
  "wuxing": {"金": 2, "木": 1, "水": 3, "火": 1, "土": 1},
  "shishen": {"正官": 1, "七杀": 0, "正财": 2, "偏财": 1},
  "dayun": [
    {"age": 5, "gan_zhi": "甲子", "score": 0.62},
    {"age": 15, "gan_zhi": "乙丑", "score": 0.68}
  ],
  "liunian": [
    {"year": 2026, "gan_zhi": "丙午", "score": 0.72}
  ]
}
```

### 8.2 ECharts 图表

新增 `static/js/charts.js`，封装四类图表：

1. 五行雷达图。
2. 十神饼图。
3. 大运趋势折线图。
4. 流年运势柱状图。

```javascript
const BaZiCharts = {
  renderWuxingRadar(container, data) {},
  renderShishenPie(container, data) {},
  renderDayunTrend(container, data) {},
  renderLiunianBar(container, data) {}
};
```

### 8.3 PDF 报告升级

现有 PDF 链路为：

```text
report_builder.py → Markdown → report_to_pdf.py → PDF
```

Phase 3 不迁移到 HTML 模板系统，先增强现有链路：

1. `report_builder.py` 增加图表占位符。
2. 前端使用 ECharts 渲染图表。
3. 前端将图表导出为 base64 PNG。
4. 后端在 PDF Job 中接收图表图片。
5. `report_to_pdf.py` 增加图片插入能力。

### 8.4 字体策略

沿用现有字体候选：

| 平台 | 字体 |
|---|---|
| Windows | `C:/Windows/Fonts/simhei.ttf`、`simkai.ttf`、`simfang.ttf` |
| Linux | `NotoSansCJK-Bold.ttc`、`NotoSansCJK-Regular.ttc` |

不再使用旧文档中的 `msyh.ttc` / `wqy-zenhei.ttc` 作为主路径。

### 8.5 命理卡片

新增 `static/js/card.js`，使用 Canvas 生成分享图：

```text
尺寸：750 x 1000
内容：姓名、八字、格局、用神、五行小图、核心断语、品牌信息
输出：PNG 下载
```

### 8.6 Phase 3 涉及文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `api_server.py` | 修改 | 新增 `/api/charts/{chart_id}/visualization` |
| `static/js/charts.js` | 新建 | ECharts 封装 |
| `static/css/charts.css` | 新建 | 图表样式 |
| `static/app.js` | 修改 | 分析页接入图表 Tab |
| `report_builder.py` | 修改 | 报告增加图表占位符 |
| `report_to_pdf.py` | 修改 | 支持图片插入和布局优化 |
| `static/js/card.js` | 新建 | 命理卡片生成 |
| `static/card.html` | 新建 | 卡片预览页 |

### 8.7 Phase 3 不做的事

| 不做 | 原因 |
|---|---|
| 迁移到 WeasyPrint | 当前 fpdf2 链路已可用 |
| 服务端 ECharts 渲染 | 浏览器端即可完成 |
| 3D 图表 | 命理数据不需要 |
| 动画特效 | 专业工具优先清晰和稳定 |

---

## 九、Phase 4：数据飞轮与增长

**周期：** 持续迭代  
**成功标准：** 收集真实反馈，反向优化 Prompt 和案例库；命理师愿意重复使用。

### 9.1 反馈闭环

```text
AI 输出断语
    ↓
命理师点击 准 / 不准
    ↓
feedback 表保存
    ↓
定期统计不准维度
    ↓
修正 Prompt、Few-shot、规则引擎
    ↓
AI 分析质量提升
```

反馈 UI 嵌入分析结果：

```text
格局判断：此命七杀透出，身弱喜印。
[准] [不准] [备注]

事业判断：适合专业技术、研究、咨询类路径。
[准] [不准] [备注]
```

### 9.2 反馈分析脚本

新增 `quality/feedback_analysis.py`：

```python
def analyze_feedback(db_path):
    stats = load_feedback_stats(db_path)
    return {
        "dimension_accuracy": stats["dimension_accuracy"],
        "worst_dimensions": stats["worst_dimensions"],
        "top_inaccurate_judgments": stats["top_inaccurate_judgments"],
        "prompt_suggestions": stats["prompt_suggestions"],
    }
```

### 9.3 节气提醒

节气数据来源为：

```text
knowledge-base/solar_terms.json
```

数据格式类似：

```json
{"1950|立春": [2, 4, 18, 8, true]}
```

新增 `quality/solar_term_push.py`：

```python
def load_solar_terms(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_upcoming_terms(data, today, days_ahead=3):
    return []
```

桌面优先阶段先做「应用内提醒」，不急于做系统级通知。

### 9.4 品牌卡片

在 Phase 3 命理卡片基础上增加命理师品牌信息：

```text
玄机子命理卡片
张三 · 乾造
八字：乙丑 戊寅 庚午 丙子
格局：七杀格
用神：印星
2026 运势：★★★★☆
命理师：王老师
联系方式：...
```

### 9.5 Phase 4 涉及文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `data_store.py` | 修改 | feedback 查询统计 |
| `api_server.py` | 修改 | 反馈统计 API |
| `static/js/feedback.js` | 修改 | 增加反馈 UI |
| `quality/feedback_analysis.py` | 新建 | 反馈分析 |
| `quality/solar_term_push.py` | 新建 | 节气提醒逻辑 |
| `static/js/card.js` | 修改 | 加入命理师品牌信息 |

---

## 十、成功指标

| 阶段 | 指标 | 目标 |
|---|---|---|
| Phase 1 | LLM 报告结构完整率 | 90%+ |
| Phase 1 | 必需术语覆盖率 | 90%+ |
| Phase 1 | 模糊词惩罚 | 明显下降 |
| Phase 1 | CaseRetriever 注入 | 每次主分析 2-3 个案例 |
| Phase 2 | 客户管理 | 支持 10+ 客户稳定管理 |
| Phase 2 | 历史分析 | 每个客户可查看多次分析 |
| Phase 2 | 反馈记录 | 支持按维度记录准/不准 |
| Phase 3 | 图表渲染 | 4 类图表可正常显示 |
| Phase 3 | PDF 导出 | 中文无乱码，异步 Job 成功率稳定 |
| Phase 4 | 反馈积累 | 首月 50+ 条有效反馈 |
| Phase 4 | 留存 | 命理师愿意在 2 周内重复使用 |

---

## 十一、风险与缓解

| 风险 | 缓解措施 |
|---|---|
| Prompt 改动导致输出变差 | 增加 `quality/llm_quality_test.py` 回归测试 |
| Claude API 不稳定 | 保留 `auto_analyzer.py` 本地兜底 |
| 新客户表破坏旧数据 | 只新增表，不修改旧表语义 |
| SSE 流式分析难保存完整内容 | 在 `chat_stream()` 内累计 reply/report，done 前写入 analyses |
| PDF 图表嵌入复杂 | 先支持 PNG 插入，不做 HTML PDF 重构 |
| 图表字段不一致 | 新增 visualization API 作为统一契约 |
| 节气数据解析错误 | 直接读取 `solar_terms.json`，增加单元测试 |
| CI 调用 LLM 成本过高 | 先做 smoke test，后续再扩大样本 |

---

## 十二、推迟项

| 推迟项 | 原因 |
|---|---|
| DeepSeek 切换 | 当前 Claude 链路已接入，先稳定质量 |
| 向量数据库 | 现有案例规模不需要 |
| Redis / Celery | 桌面/单用户场景暂不需要 |
| 云同步 | 本地工作流稳定后再做 |
| 多租户 SaaS | 当前策略是先做专业单人工具 |
| 本地模型微调 | 数据不足，成本高 |
| 六爻/择吉/风水大模块 | 核心八字质量优先 |
| WeasyPrint 重构 | 现有 Markdown → fpdf2 路线更低风险 |
| 移动端优先 | 命理师工作流以桌面为主 |

---

## 十三、最终实施顺序

1. 先修 Phase 1：PromptEngine + CaseRetriever 注入 + LLM 质量测试。
2. 再修 Phase 2：数据库扩展 + 客户管理 + 分析历史。
3. 然后做 Phase 3：图表 + PDF + 卡片。
4. 最后做 Phase 4：反馈统计 + 节气提醒 + 品牌分享。

**关键原则：** 不重写现有系统，不绕开现有 `chart_id`，不替换现有 PDF Job 系统，不重新发明已有的案例检索、报告构建和规则分析能力。
