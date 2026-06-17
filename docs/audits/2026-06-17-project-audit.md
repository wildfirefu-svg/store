# 玄机子项目审计报告

**审计日期：** 2026-06-17  
**审计范围：** 当前仓库源码、前端模块、后端 API、AI 服务链路、测试套件、质量报告、仓库产物管理  
**审计方式：** 静态代码阅读、全量测试、重点模块专项测试、Git 跟踪文件检查  

---

## 1. 结论摘要

项目已经具备完整的八字命理智能体产品雏形：包含排盘、AI 流式分析、命主/客户管理、报告/PDF、择日、流年、取名、合婚、知识库、benchmark、桌面应用和 MCP 服务。核心风险不在“功能缺失”，而在稳定性、测试隔离、安全边界、AI 错误诊断和命理质量评测闭环。

本次审计确认：

- 全量测试未通过：`234 passed, 6 errors, 1 warning`。
- DeepSeek/Anthropic 适配与 chat-stream 存储相关专项测试通过：`12 passed, 1 warning`。
- E2E 测试错误集中在 Playwright 无法连接 `http://localhost:8000`，属于测试基础设施问题。
- 前端 SSE 流式解析存在分包边界 BUG，可能误报“AI 服务连接失败”。
- AI 回复最终渲染存在 HTML 注入风险。
- 后端 fallback 文案仍写死 Anthropic，不符合当前 DeepSeek 使用场景。
- `build/` 与 `dist/` 打包产物被 Git 跟踪，仓库边界不清晰。

---

## 2. 当前功能盘点

### 2.1 后端 API

入口文件：`api_server.py`

已提供能力：

- Web 页面入口：`/`、`/benchmark`、`/test`、`/tools`、`/card`
- 健康检查与指标：`/api/health`、`/api/metrics`
- 排盘：`POST /api/chart`
- 命盘持久化：`/api/charts`、`/api/charts/{chart_id}/data`、`/api/charts/save`
- 聊天历史：`/api/charts/{chart_id}/history`
- 报告保存：`/api/charts/{chart_id}/reports`、`/api/charts/reports/save`
- 客户管理：`/api/clients`
- 模型输出与反馈：`/api/charts/{chart_id}/model-outputs`、`/api/analyses/{analysis_id}/feedback`
- 人生事件与时间线：`/api/charts/{chart_id}/timeline`、`/api/charts/{chart_id}/life-events`
- benchmark：`/api/benchmark/runs`、`/api/benchmark/report/{run_id}`
- 工具：择日、流年、取名、案例检索、合婚、命盘比较
- AI：`GET /api/chat/stream`
- 知识库：`/api/kb/search`、`/api/kb/stats`

### 2.2 命理计算层

入口文件：`bazi_calculator.py`

已提供能力：

- 四柱排盘
- 大运推算
- 神煞计算
- 紫微斗数
- 五运六气
- 五行统计
- 十神统计
- 真太阳时
- 流年推算

### 2.3 AI 与提示词层

相关文件：

- `claude_api.py`
- `prompt_engine.py`
- `prompts/*.md`

已提供能力：

- DeepSeek 与 Anthropic key 自动识别。
- DeepSeek payload 支持 thinking 开关。
- 支持 system prompt。
- 流式解析 `reasoning_content` 与 `content`。
- 可信推理模式会保存模型输出与对话摘要。

### 2.4 前端

相关文件：

- `templates/index.html`
- `static/js/api.js`
- `static/js/stream.js`
- `static/js/state.js`
- `static/js/ui.js`
- `static/js/markdown.js`
- `static/css/*.css`

已提供能力：

- 命主列表与当前命主切换。
- 排盘结果渲染。
- AI 流式聊天。
- 报告 tabs。
- 本地 localStorage 与后端持久化同步。
- 工具条：择日、流年、取名、合婚等。
- Markdown 报告渲染。

### 2.5 报告与 PDF

相关文件：

- `report_builder.py`
- `report_to_pdf.py`
- `chart_to_image.py`

已提供能力：

- 结构化结论转 Markdown。
- 多模式报告构建。
- 多模板 PDF 输出。
- 命盘图像生成。

### 2.6 数据与质量体系

相关文件：

- `data_store.py`
- `quality/model_quality_report_v2.json`
- `benchmark/*`
- `tests/test_benchmark_*.py`

已提供能力：

- SQLite 存储命盘、客户、报告、分析、反馈、模型输出、benchmark、人生事件、对话摘要。
- benchmark runner、报告生成、choice accuracy、evidence、safety、stability 指标。
- 质量报告显示当前整体平均分 `0.62`，正向匹配率 `25.2%`。

---

## 3. 测试审计

### 3.1 全量测试

执行命令：

```powershell
python -m pytest -q
```

结果：

```text
234 passed, 1 warning, 6 errors in 48.34s
```

6 个 error 均来自 `tests/test_e2e.py`。

根因：

- `tests/test_e2e.py:6` 固定 `BASE = "http://localhost:8000"`。
- `tests/test_e2e.py:20` 在 fixture 中直接访问该地址。
- 测试套件没有启动 uvicorn 服务。
- 因此 Playwright 报 `net::ERR_CONNECTION_REFUSED`。

### 3.2 AI 专项测试

执行命令：

```powershell
python -m pytest tests/test_claude_api.py tests/test_api.py::TestChatStreamModelOutputs -q
```

结果：

```text
12 passed, 1 warning in 1.23s
```

结论：

- DeepSeek/Anthropic provider 识别单测通过。
- DeepSeek payload 与 parser 单测通过。
- chat stream 保存模型输出的 API 单测通过。
- 用户遇到的“AI 服务连接失败”不能简单归因于 key 识别失败，还需要排查运行时网络、额度、真实 API 响应，以及前端流式解析。

### 3.3 测试隔离问题

跑测试后工作区出现或保留以下改动：

- `benchmark/reports/__pycache__/generate_report.cpython-310.pyc`
- `quality/model_quality_report.json`
- `benchmark/outputs/test_report_api.md`
- `benchmark/outputs/test_report_relative_api.md`

这说明部分测试会污染工作区。后续应改为写入 `tmp_path` 或测试专用临时目录。

---

## 4. Bug 与风险清单

### P1. E2E 测试不可独立运行

文件：

- `tests/test_e2e.py:6`
- `tests/test_e2e.py:20`
- `tests/test_e2e.py:43`
- `tests/test_e2e.py:51`

问题：

- 测试依赖外部已启动服务。
- 每个测试打开新页面，但部分测试假设页面已有命盘或 AI 状态。
- AI 测试可能真实调用 DeepSeek，造成网络、key、余额、速率限制导致的非确定性失败。

影响：

- CI 无法可靠运行。
- 无法区分产品 bug 与测试环境 bug。
- 前端回归缺乏可信保障。

建议：

- 给 E2E 增加自动启动 uvicorn 的 fixture。
- 每个测试自行创建命盘。
- AI 流式测试改为 mock SSE，而不是打真实模型。

### P1. 前端 SSE 解析会丢失跨 chunk 的事件类型

文件：

- `static/js/api.js:45`

问题：

`eventType` 在每次 `pump()` 处理 chunk 时重新初始化。如果浏览器读取流时刚好把 `event: reply` 与 `data: {...}` 拆到不同 chunk，`data` 到达时事件类型为空，前端会跳过该数据。

影响：

- AI 明明返回了内容，前端可能不显示。
- `gotContent` 可能保持 false，最终显示“AI 服务连接失败”。
- 该问题具有随机性，和网络分包有关，难以复现。

建议：

- 将 SSE parser 改为状态机。
- `currentEventType` 跨 chunk 保存。
- 以空行作为一条 SSE message 的结束。
- 增加 JS 单测或 Playwright mock 流测试。

### P1. AI 回复最终渲染存在 HTML 注入风险

文件：

- `static/js/stream.js:76`
- `static/js/stream.js:71`
- `static/js/stream.js:82`

问题：

流式过程中使用 `textContent`，但完成时又将 `replyText` 直接拼入 `innerHTML`。工具名也通过字符串拼接进入 `innerHTML`。

影响：

- AI 输出或异常内容中若包含 HTML，会被浏览器解析。
- 在本地桌面应用里同样可能造成 UI 注入。

建议：

- 最终回复继续用 `textContent`，或先 escape 再换行。
- 工具标签用 DOM API 创建。
- 增加恶意 HTML 输入测试。

### P2. DeepSeek 场景下错误提示误导

文件：

- `api_server.py:1624`

问题：

fallback 文案写死“请设置 ANTHROPIC_API_KEY”，但当前项目支持 DeepSeek，用户实际使用 DeepSeek key。

影响：

- 用户排查方向错误。
- 运维支持成本增加。

建议：

- 改为“请设置 DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY”。
- 在错误消息中区分：未配置 key、HTTP 401、HTTP 402/余额、HTTP 429、网络超时、解析失败。

### P2. 生产安全边界偏松

文件：

- `config.py:14`
- `api_server.py:76`
- `api_server.py:189`

问题：

- CORS 默认 `*`。
- API key 支持 query 参数 `?api_key=`。

影响：

- 公网部署时跨域范围过宽。
- query key 容易进入浏览器历史、代理日志、Referer。

建议：

- 本地开发允许 `*`，生产必须显式配置 origin。
- 生产禁用 query key，只允许 Authorization Bearer。
- 增加安全配置测试。

### P2. 打包产物被 Git 跟踪

文件：

- `.gitignore`
- `build/*`
- `dist/*`

问题：

`git ls-files build dist .deepseek_key .anthropic_key bazi_data.db .env .env.example` 显示 `build/` 与 `dist/` 中大量 exe、DLL、打包内嵌源码副本被 Git 跟踪。

影响：

- 仓库体积膨胀。
- 审查 diff 噪音大。
- 产物与源码可能漂移。
- 安全扫描范围变大且结果不清晰。

建议：

- 决定是否继续跟踪 release 产物。
- 常规建议是移出 Git，只保留打包脚本与 release artifacts。
- `.gitignore` 增加 `build/`、`dist/`。

### P2. 测试会污染工作区

文件：

- `benchmark/outputs/test_report_api.md`
- `benchmark/outputs/test_report_relative_api.md`
- `quality/model_quality_report.json`

问题：

部分测试运行后留下输出文件或修改质量报告。

影响：

- 开发者无法判断哪些是真改动。
- CI 缓存与本地调试容易混淆。

建议：

- 所有测试输出改用 `tmp_path`。
- 必要 snapshot 放入明确的 `tests/fixtures`。

### P3. 报告构建器对空大运列表不防御

文件：

- `report_builder.py:57`

问题：

`da_yun[0]` 直接访问，若旧数据或异常数据缺失大运列表，会抛 `IndexError`。

影响：

- PDF/报告生成对部分坏数据不鲁棒。

建议：

- 空列表时显示 `起运：N/A 当前大运：N/A`。
- 增加单测覆盖空 `da_yun`。

---

## 5. 八字命理判断质量审计

质量报告文件：

- `quality/model_quality_report_v2.json`

当前指标：

- 测试案例：82
- 事件总数：544
- 总体平均分：0.62
- 正向匹配率：25.2%
- 弱匹配率：44.7%
- 无匹配率：30.1%

分领域表现：

| 领域 | 事件数 | 平均分 | 正向匹配率 | 结论 |
|---|---:|---:|---:|---|
| 事业 | 189 | 0.85 | 38.1% | 当前最强领域 |
| 财运 | 88 | 0.70 | 28.4% | 中等 |
| 婚恋 | 76 | 0.69 | 21.1% | 中等偏弱 |
| 健康 | 78 | 0.44 | 16.7% | 明显偏弱 |
| 家庭 | 111 | 0.27 | 9.9% | 明显偏弱 |
| 教育 | 2 | 0.07 | 0.0% | 样本过少，不能下稳定结论 |

主要问题：

- 当前系统对事业事件较敏感，但对健康、家庭、教育类判断弱。
- 指标更像“事件回放匹配”，还不足以支撑“泛化预测准确率”。
- Prompt 需要强制输出证据链，否则 AI 容易给泛泛判断。
- 需要把命理证据结构化：大运、流年、十神、五行、冲合刑害、神煞、宫位、反例条件。

建议：

- 建立分领域金标集，每条事件都标注命理证据。
- 给每条 AI 输出打分：证据覆盖、选择题准确率、稳定性、安全性、反事实约束。
- 对健康/家庭先做专项数据补强，不先追求全领域平均分。
- 将“绝对化断语、医疗投资建议、恐吓式表达”纳入安全扣分。

---

## 6. 优先级建议

### 第 1 优先级：让项目稳定可测

目标：

- 全量测试稳定通过。
- E2E 可独立运行。
- 测试不污染工作区。

理由：

没有稳定测试，后续所有质量优化都缺少可靠反馈。

### 第 2 优先级：修复 AI 流式链路

目标：

- 解决“AI 服务连接失败”误报。
- 错误提示能明确区分 key、网络、额度、模型响应、前端解析。

理由：

这是当前用户最直接遇到的问题，影响核心体验。

### 第 3 优先级：安全与发布边界

目标：

- 修复 HTML 注入。
- 生产 CORS 与鉴权收口。
- 移除打包产物跟踪或明确产物策略。

理由：

项目涉及出生信息、报告和个人事件，隐私与安全不能后补。

### 第 4 优先级：命理质量闭环

目标：

- 从当前 `0.62` 的总体评分建立可回归的质量提升路径。
- 重点提升健康、家庭、婚恋类判断。

理由：

命理判断质量是产品护城河，但必须在工程稳定后用数据闭环提升。

---

## 7. 审计后建议产物

建议创建或维护以下长期文档：

- `docs/audits/YYYY-MM-DD-project-audit.md`：定期审计。
- `docs/superpowers/plans/YYYY-MM-DD-project-optimization-implementation.md`：可执行优化计划。
- `docs/AI_TROUBLESHOOTING.md`：DeepSeek/Anthropic 配置和错误排查。
- `docs/SECURITY.md`：生产部署安全配置。
- `docs/QUALITY_EVALUATION.md`：命理质量评测方法。

---

## 8. 审计结论

项目当前已经具备产品级功能厚度，但尚未达到产品级稳定性。下一步不应继续大面积加新功能，而应先做四件事：

1. 修测试基础设施。
2. 修 AI 流式链路和错误诊断。
3. 修安全与仓库产物边界。
4. 建立命理质量的可回归评测闭环。

这四项完成后，再推进更复杂的客户画像、长期记忆、专业报告商品化和 benchmark 驱动的模型优化，风险会低很多。
