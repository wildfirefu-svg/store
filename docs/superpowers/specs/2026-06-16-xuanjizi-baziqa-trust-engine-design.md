# 玄机子 BaziQA Trust Engine 升级设计

**日期：** 2026-06-16  
**状态：** Draft / 深度设计建议  
**目标版本：** 玄机子 3.0  
**推荐定位：** 可验证的专业命理智能体平台  
**参考对象：** ChenJiangxi/BaziQA、玄机子当前代码库、既有「质量堡垒」路线图  
**设计策略：** 质量底座 + 产品体验 + 商业背书三者融合，先做可信评测与结构化推理，再产品化为人生 K 线、专属顾问和可信报告。

---

## 一、设计结论

BaziQA 对玄机子的价值不应被理解为“导入一批命理题库”。它真正提供的是一套让命理 AI 可评测、可比较、可复现、可回归、可解释的方法论。

玄机子当前已经具备排盘、AI 分析、PromptEngine、客户管理、报告、PDF、图表、命理卡片和反馈闭环雏形。下一阶段最关键的升级不是继续堆 UI 功能，而是建立一套贯穿 AI 生成、质量评测、用户体验和商业背书的可信引擎。

本设计建议将该能力命名为：

```text
Xuanjizi Trust Engine
```

核心目标：

```text
让每一次命理 AI 输出都有来源、有依据、可追踪、可评测、可回放、可改进。
```

最终产品表达：

```text
玄机子 = 命理师工作台 + 专属命理顾问 + BaziQA 风格可信评测系统
```

---

## 二、BaziQA 可迁移能力分析

### 2.1 BaziQA 的核心结构

ChenJiangxi/BaziQA 的主要资产包括：

1. Contest8 系列：2021-2025 年，每年 8 位命主，每位命主 5 道选择题，总计 200 题。
2. Celebrity50：50 位名人，每人 5 道问题，总计 250 题。
3. 数据字段：出生信息、性别、地点、问题、四选一答案、领域分类、事件信息。
4. 评测协议：Multi-turn Conversation 与 Structured Reasoning Protocol。
5. 统计方法：多模型、多年份、多次运行、宏平均、置信区间、领域准确率、配对对比。
6. Benchmark 报告：对模型、Prompt、结构化协议进行可复现比较。

### 2.2 对玄机子的启发

| BaziQA 能力 | 对玄机子的迁移方式 |
|---|---|
| 命主级评测样本 | 建立 benchmark cases，而不是孤立 FAQ |
| 四选一标准答案 | 用于 Choice Accuracy 基础评分 |
| 多轮对话评测 | 对应玄机子的专属顾问连续问答 |
| 结构化推理协议 | 升级 PromptEngine，形成 Xuanjizi-SRP-v1 |
| 领域统计 | 对事业、财富、感情、健康、六亲、流年等分域评测 |
| 多次运行 | 衡量模型输出稳定性，避免单次结果误判 |
| Benchmark 报告 | 形成内部质量报告和未来对外可信背书 |

### 2.3 不应照搬的部分

BaziQA 是评测数据集，不是完整产品。玄机子不能只复制题库与准确率，而应进一步补足：

1. 推理依据覆盖评分。
2. 安全边界评分。
3. 用户可读解释。
4. 命主长期档案。
5. 人生事件回填。
6. 产品化可视化表达。
7. 用户反馈反哺评测。

---

## 三、当前项目差距

### 3.1 已有基础

当前项目已经具备：

| 能力 | 当前状态 |
|---|---|
| 排盘 | 已完成 `/api/chart` 与 `bazi_calculator.py` |
| AI 流式分析 | 已完成 `/api/chat/stream` |
| PromptEngine | 已有 `prompt_engine.py` |
| 本地预分析 | 已有 `auto_analyzer.py` |
| 客户与分析记录 | 已有 `clients`、`client_charts`、`analyses`、`feedback` |
| 分析落库 | `chat_stream` done 前保存 analysis，且已关联 client_id |
| 可视化 | 已有图表 Tab 与 `/api/charts/{id}/visualization` |
| PDF 图表 | 已有 `chart_to_image.py` + PDF 嵌图 |
| 命理卡片 | 已有 `/card?id=` 页面和主页入口 |
| 质量工具 | 已有 `quality/llm_quality_test.py`、`model_quality_test.py` |

### 3.2 关键缺口

| 缺口 | 影响 |
|---|---|
| 没有 benchmark 目录和标准样本 | 无法做 BaziQA 式模型回归 |
| 没有 model_outputs 表 | 无法追踪模型、Prompt、原始输出和结构化推理 |
| PromptEngine 没有 prompt_version / protocol | 难以做 Prompt A/B 测试 |
| 没有 Structured Reasoning JSON | 报告依据不可追踪，K 线和顾问缺数据底座 |
| 没有 life_events | 人生 K 线无法叠加真实事件 |
| 没有长期对话摘要 | 专属顾问还不能长期记忆 |
| 没有 Benchmark 报告页 | 专业可信度无法产品化表达 |

---

## 四、目标架构

### 4.1 总体链路

```text
用户 / Benchmark Case
    ↓
Chart Input / Saved Chart
    ↓
PromptEngine + Xuanjizi-SRP-v1
    ↓
Model Router / claude_api.py / DeepSeek / Claude / 其他模型
    ↓
Raw Output + Structured Reasoning JSON
    ↓
model_outputs 落库
    ↓
analyses / reports / PDF / card / timeline / benchmark report
    ↓
feedback / benchmark scoring / prompt tuning
```

### 4.2 关键原则

1. 不重写当前系统，优先在现有 `PromptEngine`、`data_store.py`、`api_server.py` 上增强。
2. 保持 SQLite，当前阶段不引入 PostgreSQL、Redis、向量数据库等复杂组件。
3. Benchmark 先内部使用，成熟后再考虑对外展示。
4. 所有 AI 输出要兼顾专业可信和安全边界。
5. 用户可见内容不暴露过多技术细节，但系统内部必须保留可追溯推理链。

---

## 五、Xuanjizi-SRP-v1 结构化推理协议

### 5.1 设计目标

Xuanjizi-SRP-v1 的目标是让模型不再直接生成泛化文案，而是按照固定流程完成命理分析：

```text
命盘基础扫描 → 结构关系识别 → 强弱与冲突定级 → 领域映射 → 事件映射 → 用户可读表达
```

### 5.2 六层协议

#### 第一层：命盘基础扫描

输出内容：

- 日主
- 月令
- 季节
- 五行数量
- 五行旺衰
- 十神分布
- 格局倾向
- 用神喜忌候选

#### 第二层：结构关系识别

输出内容：

- 天干合冲
- 地支六合、六冲、三合、刑、害、破
- 藏干关系
- 神煞辅助
- 空亡
- 大运流年触发

#### 第三层：强弱与冲突定级

建议等级：

| 等级 | 含义 |
|---|---|
| 0 | 无明显触发 |
| 1 | 轻微倾向 |
| 2 | 中度影响 |
| 3 | 强触发 |
| 4 | 多重触发，需谨慎解释 |

每个判断必须附带：

```json
{
  "severity": 2,
  "confidence": 0.68,
  "basis": ["月令亥水旺", "巳亥冲"],
  "reason": "结构触发与事业/迁移相关"
}
```

#### 第四层：领域映射

内部 domain 枚举建议：

```text
career
wealth
relationship
health
family
study
personality
annual_fortune
migration
decision
naming
marriage_matching
date_selection
```

#### 第五层：事件映射

输出趋势而非绝对预测：

```json
{
  "domain": "career",
  "period": "2027-2028",
  "tendency": "岗位变化或职责调整概率上升",
  "basis": ["流年冲动官星", "大运引动月柱"],
  "confidence": 0.63,
  "safe_advice": "提前准备技能和资源，不建议冲动裸辞"
}
```

#### 第六层：用户可读表达

最终回答结构：

```text
1. 命理依据
2. 现实解释
3. 谨慎建议
4. 可行动步骤
```

### 5.3 双轨输出

每次 AI 分析应同时生成：

1. 用户输出：Markdown / SSE 文本 / PDF 文本。
2. 系统输出：Structured Reasoning JSON。

示例：

```json
{
  "prompt_version": "srp_v1",
  "reasoning_protocol": "xuanjizi_srp_v1",
  "domain": "annual_fortune",
  "scan": {},
  "relations": [],
  "severity_items": [],
  "domain_judgments": [],
  "event_mappings": [],
  "final_answer": "...",
  "confidence": 0.71
}
```

---

## 六、数据模型设计

### 6.1 新增 `model_outputs`

用途：记录每一次模型调用的原始输入、输出、协议、模型和结构化推理结果。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 输出记录 ID |
| analysis_id | TEXT | 关联 analyses |
| chart_id | TEXT | 关联命盘 |
| client_id | TEXT | 关联客户 |
| provider | TEXT | deepseek / anthropic / openai 等 |
| model | TEXT | 模型名称 |
| method | TEXT | single_turn / multi_turn / structured / long_memory |
| prompt_version | TEXT | Prompt 版本 |
| reasoning_protocol | TEXT | srp_v1 等 |
| domain | TEXT | 分析领域 |
| question | TEXT | 用户问题 |
| input_hash | TEXT | 输入内容 hash |
| raw_prompt | TEXT | 实际 prompt 或摘要 |
| raw_output | TEXT | 模型原始输出 |
| parsed_answer | TEXT | benchmark 场景下 A/B/C/D |
| structured_reasoning_json | TEXT | JSON 字符串 |
| latency_ms | INTEGER | 模型响应耗时 |
| token_estimate | INTEGER | token 估算 |
| cost_estimate | REAL | 成本估算 |
| created_at | TEXT | 创建时间 |

### 6.2 新增 `benchmark_cases`

用途：保存内部 benchmark 的命主级样本。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | case ID |
| source | TEXT | baziqa_mini / contest8 / internal |
| person_id | TEXT | 匿名命主 ID |
| name | TEXT | 匿名名称 |
| profile_json | TEXT | 出生信息 |
| chart_input_json | TEXT | 排盘输入 |
| chart_result_json | TEXT | 排盘结果 |
| verified_events_json | TEXT | 已验证事件 |
| anonymized | INTEGER | 是否匿名 |
| license_note | TEXT | 数据来源和许可证 |
| created_at | TEXT | 创建时间 |

### 6.3 新增 `benchmark_questions`

用途：保存每个命主下的问题和标准答案。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | question ID |
| case_id | TEXT | 关联 benchmark_cases |
| domain | TEXT | 领域 |
| question | TEXT | 题干 |
| options_json | TEXT | 选项 |
| answer | TEXT | 标准答案 |
| expected_evidence_json | TEXT | 预期依据 |
| difficulty | TEXT | easy / medium / hard |
| evaluator_notes | TEXT | 评审备注 |

### 6.4 新增 `benchmark_runs`

用途：记录一次评测运行。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | run ID |
| dataset | TEXT | 数据集名称 |
| provider | TEXT | provider |
| model | TEXT | 模型 |
| method | TEXT | multi_turn / structured |
| prompt_version | TEXT | Prompt 版本 |
| reasoning_protocol | TEXT | 协议 |
| n_cases | INTEGER | case 数 |
| n_questions | INTEGER | 问题数 |
| accuracy | REAL | 准确率 |
| evidence_score | REAL | 依据覆盖分 |
| stability_score | REAL | 稳定性 |
| safety_score | REAL | 安全分 |
| report_path | TEXT | 报告路径 |
| created_at | TEXT | 创建时间 |

### 6.5 新增 `life_events`

用途：支撑人生 K 线和长期命主档案。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 事件 ID |
| chart_id | TEXT | 命盘 ID |
| client_id | TEXT | 客户 ID |
| event_date | TEXT | 具体日期，可空 |
| event_year | INTEGER | 事件年份 |
| domain | TEXT | 领域 |
| title | TEXT | 事件标题 |
| description | TEXT | 描述 |
| impact_level | INTEGER | 影响等级 1-5 |
| source | TEXT | user / analyst / imported |
| created_at | TEXT | 创建时间 |

### 6.6 新增 `conversation_summaries`

用途：支撑专属顾问的长期记忆。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 摘要 ID |
| chart_id | TEXT | 命盘 ID |
| client_id | TEXT | 客户 ID |
| period_start | TEXT | 起始时间 |
| period_end | TEXT | 结束时间 |
| focus_topics_json | TEXT | 用户关注主题 |
| summary_text | TEXT | 对话摘要 |
| preference_json | TEXT | 表达偏好 |
| created_at | TEXT | 创建时间 |

---

## 七、Benchmark 模块设计

### 7.1 目录结构

建议新增：

```text
benchmark/
  datasets/
    baziqa_mini_v1.jsonl
  protocols/
    multi_turn.md
    structured_reasoning_v1.md
  runners/
    run_benchmark.py
    run_single_case.py
  scorers/
    choice_accuracy.py
    evidence_score.py
    domain_breakdown.py
    safety_score.py
    stability_score.py
  reports/
    generate_report.py
  outputs/
    .gitkeep
```

### 7.2 Mini Dataset 格式

先建立 10-20 条内部样本，不一开始追求大规模。

JSONL 示例：

```json
{
  "case_id": "career_001",
  "person": {
    "name": "命主001",
    "gender": "male",
    "birth": {"year": 1988, "month": 3, "day": 12, "hour": 9, "minute": 0, "place": "北京"}
  },
  "domain": "career",
  "question": "此命主事业发展更偏稳定组织还是市场创业？",
  "options": ["A. 稳定组织", "B. 市场创业", "C. 艺术自由职业", "D. 不宜工作"],
  "answer": "A",
  "expected_evidence": ["官星有力", "印星配合", "大运支持组织资源"],
  "difficulty": "medium"
}
```

### 7.3 三类评测模式

| 模式 | 目标 |
|---|---|
| single_turn | 测单次报告能力 |
| multi_turn | 测连续命主问答能力 |
| long_memory | 测长期档案与人生事件注入能力 |

### 7.4 五维质量评分

建议定义综合评分：

```text
Xuanjizi Quality Score =
  30% Choice Accuracy
+ 25% Evidence Coverage
+ 20% Stability
+ 15% Safety
+ 10% Readability
```

| 维度 | 说明 |
|---|---|
| Accuracy | A/B/C/D 或判断题是否正确 |
| Evidence | 是否抓住预期命理依据 |
| Stability | 多次运行答案和依据是否一致 |
| Safety | 是否避免绝对化、医疗化、金融化、决定论 |
| Readability | 普通用户是否看得懂 |

### 7.5 统计口径

借鉴 BaziQA：

1. 每个模型、每个 Prompt 版本至少跑 3 次，成熟后跑 5 次。
2. 先按 case/question 聚合，再按 domain 聚合。
3. 输出宏平均，不只看总准确率。
4. 对比 Prompt 时使用 paired comparison。
5. 报告稳定性，不只报告准确率。

---

## 八、产品化设计

### 8.1 依据展开

报告段落旁提供“查看依据”。展开内容：

```text
命理依据：
- 日主戊土，生于亥月，水旺土弱
- 时支与月支形成冲动
- 当前大运引动事业宫位

置信度：中等偏高

边界提示：这是阶段倾向，不代表必然事件。
```

依赖：`structured_reasoning_json`。

### 8.2 人生 K 线 2.0

当前图表 Tab 已有基础图表，下一步升级为可交互时间轴。

页面结构：

```text
大运区间条
年度趋势线
领域开关：事业 / 财运 / 感情 / 健康 / 家庭
关键年份 marker
用户事件 marker
年份详情面板
未来 3-5 年提醒
```

依赖：

- `life_events`
- `structured_reasoning_json.event_mappings`
- `/api/charts/{id}/timeline`

### 8.3 专属顾问可信模式

聊天入口增加模式：

```text
普通回答 / 可信推理
```

可信推理下，回答必须包含：

```text
1. 命理依据
2. 现实解释
3. 谨慎建议
4. 可行动步骤
```

依赖：

- 命主档案
- conversation_summaries
- model_outputs
- SRP-v1

### 8.4 Benchmark 内部展示页

新增内部页面：

```text
/benchmark
```

展示：

- 模型
- Prompt 版本
- 样本数
- 准确率
- 依据覆盖
- 稳定性
- 安全分
- 领域短板
- 最近回归是否通过

成熟后可选择部分内容对外展示。

### 8.5 可信报告

PDF 或报告页面中增加：

```text
本报告生成信息：
模型：DeepSeek v4 Pro
协议：Xuanjizi-SRP-v1
依据覆盖：xx%
安全边界：已启用
生成时间：实际报告生成时间
```

注意：普通用户不一定需要看到完整评分，但可以看到“依据可追溯、非绝对预测”的提示。

---

## 九、API 设计建议

### 9.1 Model Outputs

```text
GET  /api/model-outputs/{id}
GET  /api/charts/{chart_id}/model-outputs
GET  /api/analyses/{analysis_id}/model-outputs
```

### 9.2 Benchmark

```text
POST /api/benchmark/run
GET  /api/benchmark/runs
GET  /api/benchmark/runs/{run_id}
GET  /api/benchmark/report/{run_id}
```

### 9.3 Timeline

```text
GET  /api/charts/{chart_id}/timeline
POST /api/charts/{chart_id}/life-events
GET  /api/charts/{chart_id}/life-events
DELETE /api/life-events/{event_id}
```

### 9.4 Advisor Mode

现有 `/api/chat/stream` 可扩展参数：

```text
reasoning_mode=normal|trusted
prompt_version=srp_v1
memory_mode=none|summary|full
```

---

## 十、四阶段路线图

### Sprint 1：可信推理底座

目标：让每次 AI 输出可追踪、可评测、可回放。

交付：

1. `prompts/structured_reasoning_v1.md`
2. `model_outputs` 表
3. `PromptEngine` 支持 `prompt_version`、`reasoning_protocol`
4. `chat_stream` 保存模型输出记录
5. `benchmark/datasets/baziqa_mini_v1.jsonl` 初版样本
6. `benchmark/scorers/choice_accuracy.py`

验收标准：

```text
一次 AI 分析可记录：provider、model、prompt_version、protocol、input_hash、raw_output、structured_reasoning_json。
```

### Sprint 2：BaziQA Mini Benchmark

目标：从质量测试脚本升级为命理 benchmark。

交付：

1. `benchmark/runners/run_benchmark.py`
2. `benchmark/scorers/evidence_score.py`
3. `benchmark/scorers/stability_score.py`
4. `benchmark/scorers/safety_score.py`
5. `benchmark/reports/generate_report.py`
6. 10-20 条 mini cases

验收标准：

```text
可以生成 Markdown benchmark 报告，包含准确率、领域准确率、依据覆盖、稳定性、安全分。
```

### Sprint 3：人生 K 线 2.0

目标：把结构化推理转化为用户可感知的长期体验。

交付：

1. `life_events` 表
2. `/api/charts/{id}/timeline`
3. Timeline 前端 Tab 或页面
4. 年份详情面板
5. 用户事件回填
6. 未来 3-5 年提示

验收标准：

```text
用户能看到每一年趋势、原因、领域影响、已发生事件和谨慎建议。
```

### Sprint 4：可信顾问 + Benchmark 展示

目标：形成“专属命理顾问 + 可信背书”的产品闭环。

交付：

1. 顾问可信模式入口
2. conversation_summaries 表
3. 对话摘要写入档案
4. `/benchmark` 内部展示页
5. PDF 加入可信生成信息
6. 报告依据展开

验收标准：

```text
用户提问后，系统能基于命盘、历史摘要和 SRP-v1 输出包含依据、解释、建议、置信度的回答。
```

---

## 十一、风险与边界

### 11.1 数据与许可证

如果使用 BaziQA 原始数据，需要：

1. 保留 MIT License 说明。
2. 标明来源：ChenJiangxi/BaziQA。
3. 声明是否做过修改。
4. 区分内部评测与产品展示。

建议初期使用自建 `baziqa_mini_v1`，只保持格式兼容。

### 11.2 避免模型作弊

名人数据必须支持匿名化，否则模型可能通过训练语料直接知道答案。

必须区分：

| 模式 | 是否给真实姓名 |
|---|---|
| 匿名评测 | 否 |
| 案例学习 | 可选 |
| 用户报告 | 是 |

### 11.3 安全表达边界

命理 AI 输出必须避免：

1. 绝对化预测。
2. 医疗诊断。
3. 投资建议。
4. 婚姻替用户做决定。
5. 恐吓式表达。
6. 对重大人生选择给出单一指令。

统一表达原则：

```text
命理倾向 + 现实解释 + 谨慎建议 + 自主决策
```

### 11.4 Benchmark 误读风险

不要把 35%-40% 的选择题准确率包装成“高准确预测”。Benchmark 的意义是：

```text
比较模型和 Prompt 的相对表现，发现短板，防止退化。
```

不是证明命理预测绝对准确。

---

## 十二、成功指标

### 12.1 技术指标

| 指标 | 目标 |
|---|---|
| model_outputs 覆盖率 | 90%+ AI 分析有记录 |
| structured_reasoning_json 解析率 | 80%+ |
| benchmark mini 可运行 | 至少 10 cases |
| Prompt 回归 | 每次 Prompt 改动可跑 benchmark |
| 多运行稳定性 | 可统计并展示 |

### 12.2 产品指标

| 指标 | 目标 |
|---|---|
| 报告依据展开 | 关键结论可查看依据 |
| 人生 K 线 | 可展示未来 3-5 年趋势 |
| 顾问可信模式 | 回答包含依据、解释、建议、置信度 |
| 卡片/PDF | 能体现“非绝对预测”边界 |

### 12.3 质量指标

| 指标 | 初期目标 |
|---|---|
| Choice Accuracy | 建立 baseline，不急于设高目标 |
| Evidence Coverage | 60%+ |
| Stability | 70%+ |
| Safety Score | 90%+ |
| Readability | 人工评审 4/5+ |

---

## 十三、推荐实施顺序

不建议立即做所有页面。推荐顺序：

```text
1. SRP-v1 文档与 PromptEngine 接入
2. model_outputs 表与保存逻辑
3. baziqa_mini_v1 样本和 choice scorer
4. benchmark runner + Markdown 报告
5. evidence / stability / safety scorer
6. life_events 表
7. 人生 K 线 2.0
8. 顾问可信模式
9. /benchmark 内部展示页
10. 对外可信报告与商业背书
```

第一批开发应聚焦：

```text
SRP-v1 + model_outputs + benchmark_mini
```

这是投入最小、收益最大的部分，也是后续人生 K 线、专属顾问、可信报告的地基。

---

## 十四、与当前计划文件的关系

本设计不是替代现有「质量堡垒」路线图，而是它的 3.0 深化版本。

对应关系：

| 当前已完成能力 | 本设计中的位置 |
|---|---|
| PromptEngine | SRP-v1 承载层 |
| analyses / feedback | 长期质量闭环 |
| 图表 Tab | 人生 K 线雏形 |
| PDF 图表 | 可信报告表达 |
| 命理卡片 | 产品化分享表达 |
| DeepSeek v4-pro | 模型路由基础 |
| quality 脚本 | benchmark 前身 |

本设计将这些能力从“功能集合”组织成：

```text
可信分析底座 → 长期命主档案 → 产品化表达 → 商业可信背书
```

---

## 十五、最终建议

玄机子下一阶段不应继续单纯增加按钮或页面，而应优先建立 Trust Engine。

最小可行版本：

```text
Xuanjizi Trust Engine MVP =
  Xuanjizi-SRP-v1
+ model_outputs
+ baziqa_mini_v1
+ benchmark runner
+ Markdown benchmark report
```

完成后，玄机子将从：

```text
会排盘、会聊天、会出报告的命理工具
```

升级为：

```text
能自我评测、持续调优、依据可追溯、长期陪伴用户的专业命理智能体平台
```
