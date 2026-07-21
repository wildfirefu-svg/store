# 八字命理智能体 — 系统架构与文件功能报告

> 版本: v3.0 | 日期: 2026-07-17 | 总代码: 50,288行 Python | 文件数: 296 (.py，不含 .venv/.git/__pycache__)

本文档描述整个项目的文件结构、模块功能、依赖关系和调用链路，确保 Agent 能正确理解和使用每个文件。

**v2.2 → v3.0 主要变化**（Phase 2–5 之后）：
- 架构重心从"Agent 直接调用 CLI 工具"转为 **FastAPI 服务 + MCP 服务 + 桌面端 + 评测闭环** 四条交付线。
- 新增根目录模块：`claude_api.py`（五家 LLM 统一客户端）、`prompt_engine.py` / `rag_prompt_builder.py`（两条独立 prompt 链路）、`auto_analyzer.py`（本地规则预分析）、`data_store.py`（SQLite 持久化）、`case_index.py` 四件套（评测 RAG 检索）、`mcp_server.py`、`desktop_app.py`、`config.py` 等。
- 新增 `benchmark/` 评测框架（BaziQA + MingLi-Bench）、`scripts/` 实验脚本群、`prompts/` 模板目录。
- `bazi_calculator.py` 1,916 → 2,351 行；`api_server.py` 350 行/10 端点 → 1,655 行/58 路由；`report_builder.py` 610 → 892 行。

---

## 一、系统定位与总体架构

**玄机子（XuanJiZi）**是基于 LLM + 传统命理知识库的八字命理分析服务。核心原则：**排盘计算完全确定化（纯代码、可离线复现），LLM 只负责文本分析**；分析上下文由结构化排盘 + 知识库检索（RAG）+ 本地规则预分析组装，并有独立的评测闭环（BaziQA / MingLi-Bench）持续量化准确率。

```
                        ┌────────────── 四个交付入口 ──────────────┐
  浏览器/前端 ──► api_server.py (FastAPI :8000)   ◄── desktop_app.py (pywebview 内嵌)
  MCP 客户端 ──► mcp_server.py (FastMCP, stdio / SSE :8001，不调 LLM)
                        │
        ┌───────────────┼────────────────────────┐
        ▼               ▼                        ▼
  bazi_calculator   prompt_engine          knowledge-base/
  (排盘引擎,纯函数)  (在线prompt, SRP协议)   (SQLite FTS5 知识库 + 领域工具
        │               │                   + 名人案例 ChromaDB 检索)
        │               ▼
        │         claude_api.py (DeepSeek/Anthropic/Kimi/GLM/Qwen
        │                        统一 HTTP 客户端，零 SDK)
        │               │
        ▼               ▼
  report_builder → report_to_pdf (Markdown → fpdf2 PDF，子进程调用)

  ─────────── 离线评测线（与在线线并行、互相独立）───────────
  benchmark/runners/run_benchmark.py
    → bazi_features.extract → case_index.py (BM25+稠密向量+RRF融合+CrossEncoder重排)
    → rag_prompt_builder.py → claude_api.call_model_messages_sync
    → scorers/ (准确率/证据/安全/稳定性) → scripts/verify_* 门禁 → docs/ 报告沉淀
```

**关键认知**：项目有**两条互相独立的 prompt/RAG 链路**——在线线走 `prompt_engine`（SRP 推理协议 + 名人案例检索），评测线走 `rag_prompt_builder` + `case_index`（选项证据注入）。向量索引有三套实现（ChromaDB×2 + numpy/pickle×1），嵌入模型三个，互不共享。

---

## 二、目录总览

```
agent/
├── bazi_calculator.py          ← 排盘核心引擎（2,351行，纯标准库+iztro子进程）
├── auto_analyzer.py            ← 本地规则预分析：旺衰/格局/用神（279行，无LLM）
├── claude_api.py               ← 五家LLM统一HTTP客户端（482行，纯urllib零SDK）
├── prompt_engine.py            ← 在线聊天prompt组装（141行，SRP协议路线）
├── rag_prompt_builder.py       ← 评测RAG prompt构建（311行，选项证据路线）
├── report_builder.py           ← 结构化结论→Markdown（892行，mode1~7）
├── report_to_pdf.py            ← Markdown→PDF（487行，fpdf2，4套模板）
├── bazi_report_validator.py    ← 报告文本规则校验（272行，质量门禁用）
├── api_server.py               ← FastAPI REST服务器（1,655行，58个路由注册）
├── mcp_server.py               ← MCP服务（344行，10个tool，不调LLM）
├── desktop_app.py              ← 桌面端（91行，内嵌API + pywebview）
├── data_store.py               ← SQLite持久化层（1,102行，bazi_data.db）
├── config.py                   ← 集中配置 + .env加载（115行）
├── lunar_calendar.py           ← 农历转换（264行，被calculator/api_server导入）
├── chart_to_image.py           ← 命盘截图（131行，playwright，PDF时动态导入）
├── chart_domain_summary.py     ← 命盘领域摘要：家庭/健康/婚姻（169行，仅测试引用）
├── case_index.py               ← 评测检索编排器（959行，CaseIndex）
├── case_dense_index.py         ← 稠密向量索引+pickle缓存（198行，不用ChromaDB）
├── case_reranker.py            ← CrossEncoder重排（68行，bge-reranker-v2-m3）
├── hybrid_retrieval.py         ← RRF融合（50行，k=60）
├── bazi_features.py            ← 评测特征提取（119行，chart→text_blob+结构化特征）
│
├── knowledge-base/             ← 知识库：13个JSON数据 + 15个Python工具 + bazi_kb.db
├── prompts/                    ← 7个prompt模板（两套加载方，见第九节）
├── benchmark/                  ← 评测框架（26个py：runners/scorers/formatters/datasets/configs）
├── scripts/                    ← 34个实验/数据构建/门禁/分析脚本
├── quality/                    ← 模型质量测试（真实案例对齐验证）
├── tests/                      ← 85个测试文件 + fixtures + benchmark_charts（52个排盘JSON）
├── templates/                  ← 4个服务端直出HTML（index/tools/card/test_minimal）
├── static/                     ← 前端资源（13个ES module + echarts）
├── data/                       ← 质量验证数据（cases_real_db等，不参与检索）
├── reports/                    ← 24个用户报告输出目录（{姓名}_{日期}/）
├── docs/                       ← 文档（审计/实验报告/superpowers工作流沉淀）
├── tools/                      ← 数据采集辅助（名人抓取/命例合并/时辰推断）
│
├── .agents/skills/             ← 项目技能（brainstorming/pdf-templates/writing-plans）
├── .claude/                    ← Claude Agent配置（agents/agent-memory/skills）
├── bazi_data.db                ← 应用持久化数据库（data_store.py管理）
├── .chromadb_case_index/       ← 名人案例ChromaDB索引（持久化）
├── .cache/                     ← 稠密索引pickle缓存（dense_*.pkl）
└── Dockerfile + docker-compose.yml  ← 容器化（api + mcp两服务）
```

---

## 三、根目录核心模块

### 3.1 bazi_calculator.py — 排盘引擎（2,351行）

| 属性 | 值 |
|------|-----|
| 依赖 | 纯标准库（紫微经 iztro_py 子进程，超时 `BAZI_IZTRO_TIMEOUT`=10s） |
| 唯一入口 | `compute_chart(year, month, day, hour, minute, gender, location, use_solar_time)` `:2090` |
| 被调用 | api_server / mcp_server / 所有知识库工具 / 测试 / 评测 |
| 输出 | chart dict（four_pillars/day_master/da_yun/shensha/ziwei/wuyun_liuqi/wuxing_stats/shishen_stats/liu_nian/true_solar_info/birth_info） |

**核心函数**（行号为 `bazi_calculator.py` 内位置）：

| 函数 | 功能 |
|------|------|
| `compute_chart()` `:2090` | 统一排盘入口：真太阳时→四柱→大运→神煞→紫微→五运六气→统计→流年 |
| `compare_charts()` `:2151` | 双人命盘多维对比（不限于合婚） |
| `calculate_four_pillars()` `:721` | 四柱+藏干+十神+纳音+空亡 |
| `get_year/month/day/hour_pillar()` `:481/:514/:526/:538` | 单柱计算（立春/节气边界、五虎遁、儒略日、五鼠遁） |
| `calculate_dayun()` `:813` | 起运岁数（精确节气时刻换算）+顺逆排+10步大运 |
| `calculate_shensha()` `:928` | 30+神煞查表计算；`enhance_shensha()` `:1941` 附含义 |
| `calculate_ziwei()` `:1027` | 紫微斗数全盘（命身宫/五行局/十四主星/辅星/四化） |
| `calculate_true_solar_time()` `:1834` | 经度/时区/均时差校正 |
| `detect_branch_relations()` `:636` | 刑冲合害关系检测 |
| `calculate_liunian()` `:1909` | 未来N年流年 |
| `calculate_wuxing_stats()` / `calculate_shishen_stats()` `:1303/:1329` | 五行/十神统计 |

### 3.2 auto_analyzer.py — 本地规则预分析（279行，无LLM）

`auto_analyze(chart)` `:30`：纯规则的旺衰量化、格局判定、用神选取等结构化结论。在线聊天流中作为 LLM 的"本地预分析"上下文，也是 `POST /api/analyze` 结论的默认来源。

### 3.3 claude_api.py — LLM 调用层（482行，零SDK，纯urllib）

> 命名有误导性：实际是 **DeepSeek/Anthropic/Kimi/GLM/Qwen 五家统一客户端**。

| 函数 | 功能 |
|------|------|
| `_detect_provider()` `:77` | 按 API key 自动识别 provider（`sk-ant-*`→Anthropic，其余按命中的环境变量区分） |
| `call_model_messages_sync()` `:125` | 同步调用（评测框架复用）；Anthropic 走 Messages API，其余走 OpenAI 兼容协议 |
| `stream_chat()` `:405` | SSE 流式调用（在线聊天用），429/连接错误自动重试 |
| `_slim_chart()` `:304` | 裁剪命盘字段降 token（OpenAI 系 payload） |
| `_load_system_prompt()` `:253` | 默认 system prompt（6个模板拼接+歌诀注入，带缓存） |

Provider 优先级：`DEEPSEEK_API_KEY > ANTHROPIC_API_KEY > KIMI > GLM > QWEN`（`config.py:77-102`）。

### 3.4 prompt_engine.py — 在线 prompt 组装（141行）

`PromptEngine.assemble(chart, pre_analysis, topic, question)` `:20` → `(system_prompt, user_message)`：
- system = 主题 prompt + SRP 推理协议（`prompts/structured_reasoning_v1.md`，`:92` 加载）+ 版本信息
- user = chart JSON + auto_analyze 预分析 + 用户问题 + 相似案例（`retrieve_similar_cases` `:82`，top3）+ 会话记忆摘要

调用方：`api_server.py:1493`（`/api/chat/stream`）。

### 3.5 rag_prompt_builder.py — 评测 RAG prompt（311行）

`build_system_prompt(base_system, chart, case_index, ...)` `:166`：few-shot 块（`load_fewshot_examples` `:20`，抗位置偏差乱序 `:293`）+ RAG 证据注入（legacy→`<类似命例>` / option_grounded→`<选项证据>`，截断 8000 字）。

调用方：`benchmark/runners/run_benchmark.py:196/210`。**在线 API 不用它。**

### 3.6 报告三件套

| 模块 | 行数 | 职责 | 关键入口 |
|------|------|------|---------|
| `report_builder.py` | 892 | 结论JSON→Markdown，mode1~7（通用/合婚/流年/名字/四派综合/双人对比/流年详批） | `build_report()` `:773`，按 `REPORT_BUILDERS` `:762` 分发 |
| `report_to_pdf.py` | 487 | Markdown→PDF（fpdf2），4套模板 dark/modern/scroll/night | `generate_pdf()` `:404`；生产中由 api_server 子进程调用 |
| `bazi_report_validator.py` | 272 | 报告文本 vs 排盘规则的规则校验 | `validate_report_claims()`，被 `scripts/verify_report_quality_gate.py` 使用 |

### 3.7 服务与基础设施

| 模块 | 行数 | 职责 |
|------|------|------|
| `data_store.py` | 1,102 | SQLite 持久化（命盘/分析/客户/反馈/模型输出留痕，`bazi_data.db`） |
| `config.py` | 115 | 集中配置 + 轻量 `.env` 加载器 `_load_dotenv()` `:11`，全部可被环境变量覆盖 |
| `lunar_calendar.py` | 264 | 农历⇄公历转换（`bazi_calculator.py:16`、`api_server.py:31` 导入） |
| `chart_to_image.py` | 131 | playwright 命盘截图（`report_to_pdf.py:438` 动态导入） |
| `chart_domain_summary.py` | 169 | 命盘领域摘要（家庭/健康/婚姻），当前仅被测试直接引用 |
| `desktop_app.py` | 91 | 桌面端：daemon 线程起同一 FastAPI app + pywebview 窗口，兼容 PyInstaller |

### 3.8 评测检索四件套 + 特征提取

| 模块 | 行数 | 职责 | 关键入口 |
|------|------|------|---------|
| `case_index.py` | 959 | 评测检索编排器：BM25+结构化匹配+语义短语+稠密向量多信号加权 | `CaseIndex` `:158`、`top_k_cases()` `:551`、`option_evidence()`（按A/B/C/D逐选项检索证据）`:881` |
| `case_dense_index.py` | 198 | 稠密索引（ST 或 sklearn TF-IDF 兜底），numpy+pickle 缓存（**不用 ChromaDB**） | `encode_cases()` `:23`、`build_or_load()` `:152` |
| `case_reranker.py` | 68 | CrossEncoder 重排（默认 `BAAI/bge-reranker-v2-m3`，`BAZI_RERANKER_MODEL` 可覆盖） | `rerank_candidates()` `:46` |
| `hybrid_retrieval.py` | 50 | RRF 融合（k=60） | `rrf_fuse()` `:6`、`hybrid_retrieve()` `:40` |
| `bazi_features.py` | 119 | chart → text_blob + 结构化特征（检索查询侧） | `extract()` |

检索权重全部由环境变量控制（`case_index.py:578-585`）：`BAZI_RAG_STRUCTURED_WEIGHT` / `BAZI_RAG_SEMANTIC(_WEIGHT)` / `BAZI_RAG_VECTOR(_WEIGHT/_MODEL)`；消融配置见 `benchmark/configs/baziqa_retrieval_configs.yaml`（6种）。

---

## 四、服务层

### 4.1 api_server.py — FastAPI REST 服务器（1,655行，58个路由注册）

中间件栈（注册顺序）：CORS → 请求体大小限制（默认1MB）→ API Key 鉴权（`BAZI_API_KEY`，空则放行）→ IP 滑动窗口限流。

核心组件：`BirthInfo`（pydantic 出生信息模型 `:226`）、`ChartCache`（MD5 key FIFO 命盘缓存 `:248`）、`_import_tool()`（懒加载 `knowledge-base/` 模块 `:282`，目录名带连字符无法正常 import 所致）、内存指标 `_metrics`、异步 PDF 任务表 `_pdf_jobs`。

**端点分组**：

| 分组 | 端点 |
|------|------|
| 页面 | `GET /` `/benchmark` `/test` `/tools` `/card` |
| 健康/指标 | `GET /api/health`、`GET /api/metrics`（Prometheus 文本） |
| 排盘 | `POST /api/chart`、`GET/POST /api/charts*`（CRUD/保存/删除）、`POST /api/solar-time`、`POST /api/lunar-to-solar` |
| 命盘衍生 | `history`、`reports`、`visualization`、`card`、`model-outputs`、`timeline`、`life-events`、`conversation-summaries`（均挂在 `/api/charts/{id}/` 下） |
| 客户档案 | `/api/clients` 系列（CRUD + 关联命盘 + 分析记录） |
| 分析与反馈 | `POST /api/analyze`（→Markdown）、`POST /api/analyze/pdf`（异步job）+ `GET /api/jobs/{id}(/download)`、`/api/analyses*`、反馈统计 |
| 自助工具 | `POST /api/tools/{zeri,liunian,name/eval,name/gen,case/search,hehun,compare}` |
| AI 聊天 | `GET /api/chat/stream`（SSE，事件类型 tool/reply/report/done） |
| 知识库 | `GET /api/kb/search`、`GET /api/kb/stats` |
| 评测看板 | `GET /api/benchmark/runs(/ {id})`、`GET /api/benchmark/report/{id}` |

启动：`python api_server.py` → `http://localhost:8000`（Swagger 在 `/docs`）。

### 4.2 mcp_server.py — MCP 服务（344行，10个tool）

`FastMCP("bazi-server")`，stdio（默认，供 Claude Desktop）或 SSE（`--transport sse --port 8001`）。**只返回结构化 JSON，不调 LLM。**

| Tool | 功能 | Tool | 功能 |
|------|------|------|------|
| `bazi_paipan` | 排盘 | `bazi_name_gen` | 取名推荐 |
| `bazi_true_solar_time` | 真太阳时校正 | `bazi_case_search` | 相似案例检索 |
| `bazi_zeri` | 择日 | `bazi_kb_search` | 知识库全文检索 |
| `bazi_liunian` | 全年12月运势日历 | `bazi_kb_stats` | KB 统计 |
| `bazi_name_eval` | 姓名评测 | `bazi_compare` | 两命盘多维对比 |

### 4.3 desktop_app.py — 桌面端（91行）

daemon 线程起 uvicorn 跑同一个 `api_server.app`（`127.0.0.1:8000`），轮询 `/api/health` 就绪后开 pywebview 窗口（1400×900）。

---

## 五、知识库 knowledge-base/

### 5.1 数据层（13个JSON）

| 文件 | 条目 | 内容 |
|------|------|------|
| `gejue.json` | 976 | 盲派歌诀/断语（婚姻/财运/官运/神煞/滴天髓/穷通宝鉴等约37类） |
| `gejue_core.json` | 178 | 精选歌诀（`entries` 列表，在线聊天默认注入健康/家庭类） |
| `shishen-combos.json` | 1,425 | 十神组合释义（事业/财/婚/健康） |
| `shensha.json` | 81 | 神煞（触发条件/宫位含义/强度） |
| `nayin.json` | 60 | 六十甲子纳音 |
| `ziwei-patterns.json` | 60 | 紫微格局 |
| `bingyao.json` | 34 | 病药直断（病症/用药/案例） |
| `xiangyi.json` | 22 | 干支象意 |
| `yangzhai.json` | 10 | 阳宅风水 |
| `wuyun-liuqi.json` | 22 | 五运六气 |
| `hehun.json` | — | 合婚数据 |
| `solar_terms.json` | 3,624 | 节气精确时间（bazi_calculator 内部使用） |
| `star_brightness.json` | — | 紫微星曜亮度 |

### 5.2 bazi_kb.py — SQLite 统一知识库（360行 + bazi_kb.db）

`BaziKnowledgeBase.build()` 从 9 个源 JSON 导入 **9 张表 + gejue_fts（FTS5 虚表），共 2,690 行**，WAL 模式。查询 API：`search_gejue()`（FTS5 MATCH，失败回退 LIKE）、`search_shensha/nayin/shishen_combo/bingyao/xiangyi`、`fulltext_search()`、`stats()`。Docker 构建时预建库。

### 5.3 工具层（Python，行数为实测）

| 文件 | 行数 | 功能 |
|------|------|------|
| `name_wuxing_data.py` | 811 | 姓名学数据库（康熙笔画/81数理/三才/五行字库/生肖喜忌） |
| `case_retrieval.py` | 782 | 名人案例检索（ChromaDB `.chromadb_case_index/` + 规则打分兜底，`CaseRetriever`） |
| `liunian_calendar.py` | 670 | 流年日历（12月逐月运势/4维评分） |
| `name_analysis.py` | 602 | 取名引擎 + 名字评测（7维评分） |
| `zeri.py` | 502 | 择日系统（4层评分：建除十二神+八字互动+喜用神+四离四绝） |
| `hehun.py` | 365 | 合婚分析（纳音+日柱+十神+用神四法合参） |
| `bazi_kb.py` | 360 | SQLite 知识库（见 5.2） |
| `chuanren.py` | 322 | 八字穿壬（大六壬天地盘/四课三传） |
| `search.py` | 298 | 三层检索统一入口（见 5.4） |
| `search_gejue.py` | 296 | 歌诀专搜（ChromaDB 优先、bigram 兜底） |
| `search_vector.py` | 195 | ChromaDB 全库向量检索（Layer3 兜底，首次调用建库） |
| `star_brightness.py` | 168 | 紫微星曜亮度 |
| `search_xiangyi.py` | 131 | 干支象意检索 |

另有 `baziqa_rules.yaml`（评测规则）与缓存 `.gejue_tfidf.json` / `.query_classifier.json`。

### 5.4 检索层（产品线）

`search.py` 三层 fallback：Layer0 SQLite FTS5 全文 → Layer1 查询分类（关键词路由 + TF-IDF 质心）→ Layer2 Bigram Jaccard → Layer3 ChromaDB 全库向量（`knowledge-base/.chroma_db`，首次使用才构建，当前不存在）。

`case_retrieval.py`：38 个内置金标名人案例 + `tests/benchmark_charts/REAL*.json` 排盘，ChromaDB（`paraphrase-multilingual-MiniLM-L12-v2`）优先、`simple_match()`（日主五行+30/月令+20/五行分布距离等规则分）兜底。

---

## 六、评测体系（benchmark/ + scripts/ + quality/）

### 6.1 benchmark/ — 评测框架（26个py）

| 子目录 | 角色 |
|--------|------|
| `runners/` | 执行层。总入口 `run_benchmark.py`（CLI `main()` `:933`，核心 `run_model_benchmark()` `:357`），4种 method：`direct_choice` / `multi_turn` / `structured_reasoning` / `two_stage_reasoning`；辅助：选项乱序/self-consistency投票/逐选项打分/数据集导入切分/MingLi-Bench 适配器 |
| `scorers/` | 评分层：`choice_accuracy`（核心准确率）、`evidence_score`（证据覆盖率）、`safety_score`（绝对化预测扣分）、`stability_score`（Jaccard 稳定性）、`regression_gate`（回归门禁：accuracy 跌>3% 或 safety 跌>5% 即失败） |
| `formatters/` | prompt 构造：`baziqa_prompt.py`、`two_stage_reasoning.py`（Phase4 两阶段） |
| `datasets/` | BaziQA 数据：`baziqa_contest8_*` 系列（2021–2025 全量 + 按年 holdout/corpus 切分 + `_enriched` 补全排盘 + 领域子集 + mini 冒烟集） |
| `configs/` | `baziqa_retrieval_configs.yaml`：6种检索消融配置（bm25/structured/semantic/tfidf_vector/embedding_vector/option_grounded_hybrid），`case_index.load_retrieval_config()` 消费 |
| `fewshot/` | 反位置偏置 few-shot 池 |
| `outputs/` | 每次 run 的 `run_<id>.md` 报告（516份） |
| `reports/` | **代码包**（非输出目录）：`generate_report.py`、`accuracy_stats.py` |

根层 `benchmark/phase3.py`：Phase3 反位置偏置度量库（排列计划/泄漏检测/option-identity 聚合/门禁报告）。

**运行方式**：

```bash
python benchmark/runners/run_benchmark.py --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl \
    --model-runner --provider deepseek --model <模型> --max-cases N \
    [--method two_stage_reasoning] [--rag --rag-corpus ...] [--shuffle-options --n-samples K]
python scripts/run_mingli_bench.py   # MingLi-Bench（适配器归一化后复用同一 runner）
```

### 6.2 当前指标状态（2026-07-17）

| 配置 | 数据集 | 成绩 |
|------|--------|------|
| 默认基线 direct_choice（deepseek-chat，temp=0，RAG/few-shot/APB 全关） | 2024 holdout | **27.5%**（11/40） |
| Phase 3 生效配置（反位置偏置，deepseek-v4-flash） | 2024 holdout | on_ite **0.75** / off_ite 0.65 / MMS 0.7033，5/6 gate PASS |
| Phase 4 两阶段推理 | — | 回滚（on_ite -17.5pp） |
| Phase 5 C2 逐选项评分泛化 | 2021/2022 holdout | 离线预筛 gate 失败（score/answer 相关 **-0.046**），判定过拟合，0 次 API 调用即拦截，回滚 |
| 外部参照 | — | BaziQA 论文 SOTA 36.7–38%；MingLi-Bench 最佳基线 40% |

Phase 6（双体系准确率设计）设计文档 v5 已于 2026-07-17 评审 APPROVED，尚未实施（`docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md`）。

### 6.3 scripts/（34个py）与 quality/

- **消融/实验编排**：`run_phase3_ablation.py`、`run_phase5_c2_generalization.py`、`run_baziqa_retrieval_ablation.py`、`run_baziqa_k_ablation.py`、`run_baziqa_fewshot_ablation.py`、`run_baziqa_repeated_eval.py` 等
- **数据构建/索引**：`build_dense_index.py`、`enrich_*_chart_input.py`、`build_baziqa_domain_subsets.py`、`reclassify_corpus_domain.py`
- **门禁/验证**：`verify_baziqa_stage1_gate.py`、`phase3_generate_gate_report.py`、`verify_report_quality_gate.py`（用 `bazi_report_validator`）+ 配套 `.ps1` 流水线
- **分析**：`analyze_baziqa_error_attribution.py`、`compute_retrieved_answer_leak.py`（RAG 答案泄漏率）、各类 `render_*_report.py`
- **离线检索评估**：`evaluate_hybrid_offline.py`（不调 LLM）

`quality/`：`model_quality_test.py` / `model_quality_v2.py`（读 `data/cases_real_db.json` 的 198 案例/1,727 事件，验证大运流年与真实人生事件对齐度）、`llm_quality_test.py`（CI 冒烟）、`feedback_analysis.py`、`solar_term_push.py`。

---

## 七、测试与 CI

- **85 个测试文件**（`tests/test_*.py`），按被测模块平铺：评测框架（~30，runner/scorer/shuffle/各 Phase 编排器）、检索/RAG（~12）、API 层（api/clients/rate_limit/mcp/e2e）、报告与校验、prompt、核心引擎相邻测试。
- 配置在根目录 `pytest.ini`：`testpaths = tests`，自定义 marker 仅 `e2e`（起真实服务的浏览器端到端）与 `slow`。
- 运行：`python -m pytest tests/ -q`（全量）、`-m "not e2e"`（跳过 E2E）、`-m e2e`（仅 E2E）。
- **已知覆盖缺口**：`bazi_calculator.py`（最重的模块）无专属单元测试，只有间接/相邻覆盖；`desktop_app.py` 无测试。
- 测试数据：`tests/case_db.json`（命例库）、`tests/benchmark_charts/`（52个排盘JSON，案例检索数据源）、`tests/fixtures/`。
- **CI**（`.github/workflows/ci.yml`，push/PR 触发，ubuntu + Python 3.11）：① 全量语法编译检查 ② `pytest tests/ -v --timeout=120` ③ `quality/llm_quality_test.py` 冒烟 ④ `docker build` 验证。准确率评测不进 CI（需真实 LLM key，走离线脚本+门禁报告）。

---

## 八、前端与页面

- `templates/`（4个服务端直出 HTML）：`index.html`（主排盘页）、`tools.html`（自助工具）、`card.html`（命理卡片）、`test_minimal.html`。
- `static/`（挂载 `/static`）：`static/js/` 13 个 ES module——`api.js`（fetch 调 `POST /api/chart`；`apiChatStream` 手工解析 SSE）、`state.js`/`ui.js`/`charts.js`/`render-bazi.js`/`render-ziwei.js`/`timeline.js`/`feedback.js`/`stream.js` 等；`benchmark.html` + `benchmark-dashboard.js`（评测看板）；`clients.html/js`（客户档案）；`vendor/echarts.min.js`。
- 交互模式：先 `POST /api/chart` 得 `chart_id`，再 `GET /api/chat/stream?chart_id=...&message=...` 拿 SSE 流式报告。

---

## 九、prompts/ 模板与加载方（两套路径，注意别只改一边）

| 模板 | 内容 | 加载方 |
|------|------|--------|
| `core_rules.md` | 核心铁律（模板必出/禁露推理/确定性标注/数据驱动） | `claude_api._load_system_prompt()`（`claude_api.py:253`，6个md全量拼接+歌诀注入，`stream_chat` 不传 system 时的默认） |
| `mode1_general.md` | 通用命盘报告模板 | 同上 |
| `mode2_hehun.md` | 合婚报告模板 | 同上 |
| `mode3_liunian.md` | 流年详批模板 | 同上 |
| `mode4_name.md` | 名字分析模板 | 同上 |
| `conclusion.md` | 输出质量要求与免责声明 | 同上 |
| `structured_reasoning_v1.md` | Xuanjizi-SRP-v1 六层推理协议 | `PromptEngine._load_structured_reasoning_protocol()`（`prompt_engine.py:92`，在线 chat 实际走这条） |

---

## 十、数据与运行时目录

| 路径 | 角色 |
|------|------|
| `data/cases_real_db.json` | 198 案例/1,727 事件真实案例库——**质量验证数据，不参与检索**（quality/ 读取） |
| `data/celebrity_cases.json` | 64 个维基抓取案例，待合并中间产物 |
| `data/charts/` | 6 个演示/夹具命盘 JSON，无检索模块读写 |
| `reports/{姓名}_{日期}/` | 24 个用户报告目录（chart JSON + 各体系 .md/.pdf） |
| `bazi_data.db` | 应用持久化 SQLite（data_store.py 管理） |
| `.chromadb_case_index/` | 名人案例 ChromaDB 持久化（已构建） |
| `knowledge-base/.chroma_db` | 全库向量索引（**当前不存在**，首次调用 Layer3 才构建） |
| `.cache/dense_*.pkl` | 评测稠密索引 pickle 缓存 |
| `.tmp/` `.uploads/` `out/` | 运行时产物目录 |

真正的检索语料：`benchmark/datasets/*.jsonl`（评测线）与 `tests/benchmark_charts/*.json` + 内置金标案例（产品线）。

---

## 十一、环境变量与运行方式

### 11.1 关键环境变量（完整见 `.env.example` / `config.py`）

| 变量 | 用途 | 默认 |
|------|------|------|
| `DEEPSEEK/ANTHROPIC/KIMI/GLM/QWEN_API_KEY` | 五家 LLM key，配一个即可 | 空 |
| `*_MODEL` / `*_BASE_URL` | 各 provider 模型名与 endpoint | `deepseek-v4-pro` 等 |
| `BAZI_TEMPERATURE` / `BAZI_MAX_TOKENS` | 生成参数 | 0.3 / 16384 |
| `BAZI_API_PORT` / `BAZI_MCP_PORT` | 服务端口 | 8000 / 8001 |
| `BAZI_API_KEY` | 服务鉴权 Bearer（空=不启用） | 空 |
| `BAZI_CORS_ORIGINS` / `BAZI_RATE_LIMITS` / `BAZI_MAX_BODY_SIZE` | 安全与限流 | localhost / 120次每60s / 1MB |
| `BAZI_CHART_CACHE_SIZE` | 命盘内存缓存 | 128 |
| `BAZI_RAG_*` | 评测检索权重/模型开关（见 3.8） | 向量默认关 |
| `BAZI_RERANKER_MODEL` / `BAZI_IZTRO_TIMEOUT` / `BAZI_LOG_LEVEL` | 重排模型 / iztro 超时 / 日志 | bge-reranker-v2-m3 / 10s / INFO |

密钥只放 `.env`，绝不入库入日志。

### 11.2 安装与运行

```powershell
# 安装
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements-dev.txt
playwright install
copy .env.example .env   # 填入任一 LLM API Key

# 运行（三选一/可并行）
python api_server.py                              # REST API，0.0.0.0:8000
python mcp_server.py --transport sse --port 8001  # MCP（默认 stdio 供 Claude Desktop）
python desktop_app.py                             # 桌面端

# Docker / 测试
docker-compose up --build                         # api + mcp 两服务，构建时预建 FTS5 知识库
python -m pytest tests/ -q
```

**依赖**（`requirements.txt`）：fastapi + uvicorn[standard] + pydantic 2 / pywebview / fpdf2 / chromadb + sentence-transformers + numpy + scikit-learn / `iztro_py`（紫微/农历）/ matplotlib + playwright / mcp / pyyaml。LLM 调用**无任何官方 SDK**（纯 urllib）。dev 额外：pytest + pytest-timeout + httpx。

**部署说明**：`docker-compose.yml` 的 `api` 服务透传全部五家 LLM key（`ANTHROPIC/DEEPSEEK/KIMI/GLM/QWEN_API_KEY`，2026-07-17 修复，此前只透传 `ANTHROPIC_API_KEY` 导致容器拿不到可用 key）；`mcp` 服务不调 LLM，不透传任何 key。

---

## 十二、完整调用链路

### 12.1 在线聊天报告流（主链路）

```
用户输入出生信息
    │
    ▼
POST /api/chart → ChartCache.get_or_create → compute_chart 排盘 → data_store.save_chart
    │
    ▼
GET /api/chat/stream?chart_id&message
    │  ① 取 chart（内存缓存→DB 回源）
    │  ② auto_analyzer.auto_analyze(chart) 本地预分析（旺衰/格局/用神，无LLM）
    │  ③ 关键词识别主题（财运/婚姻/事业/健康/名字/流年/综合）→ bazi_kb 歌诀检索
    │  ④ PromptEngine.assemble（SRP协议 system + chart/预分析/相似案例/歌诀 user）
    │  ⑤ claude_api.stream_chat 流式调 LLM → SSE 推送 tool/reply/report/done
    │  ⑥ data_store.save_analysis + save_model_output 留痕（含 input_hash/prompt_version）
    ▼
POST /api/analyze → report_builder.build_report → Markdown
    │
    ▼
POST /api/analyze/pdf（异步job）→ build_report + 子进程 report_to_pdf.py
    → GET /api/jobs/{id}/download 取 PDF
```

### 12.2 评测流（离线）

```
BaziQA 语料 JSONL → CaseIndex(corpus)（拒绝加载含 holdout 的语料防泄漏）
    → bazi_features.extract(chart_input) 提特征
    → option_evidence() / top_k_cases() 检索+打分（BM25+结构化+稠密 RRF+重排）
    → rag_prompt_builder.build_system_prompt() 注入 <类似命例>/<选项证据>（截断8000字）
    → claude_api.call_model_messages_sync
    → scorers/ 打分 → reports/generate_report.py 出 outputs/run_*.md
    → scripts/verify_* / regression_gate.py 卡门禁 → docs/ 报告沉淀
```

### 12.3 MCP 流

```
MCP 客户端 → mcp_server tool → compute_chart / knowledge-base 工具 → 结构化 JSON（无 LLM）
```

### 12.4 依赖图（纵向）

```
┌────────────────────────────────────────────────────────────┐
│  交付层: api_server.py │ mcp_server.py │ desktop_app.py     │
│         templates/ + static/ (前端)                         │
└──────┬──────────────────┬──────────────────────────────────┘
       │                  │
┌──────▼───────┐   ┌──────▼──────────┐   ┌──────────────────┐
│ prompt_engine │   │  knowledge-base/ │   │ benchmark/ +     │
│ (在线)        │   │  工具+检索层      │   │ case_index四件套  │
└──────┬───────┘   └──────┬──────────┘   │ (评测RAG)        │
       │                  │              └────────┬─────────┘
       │           ┌──────▼──────────┐            │
       ├──────────►│ bazi_calculator  │◄───────────┤
       │           │ (排盘引擎,无依赖) │  bazi_features
       │           └─────────────────┘            │
       ▼                                          ▼
┌─────────────────┐                      ┌──────────────────┐
│  claude_api.py   │◄─────────────────────│ rag_prompt_builder│
│ (五家LLM客户端)  │                      └──────────────────┘
└─────────────────┘
       │
┌──────▼──────────────────────────────┐
│ report_builder → report_to_pdf       │
│ data_store (bazi_data.db)            │
└──────────────────────────────────────┘
```

---

## 十三、文件完整性检查清单

| # | 文件 | 必须 | 检查方式 |
|---|------|------|---------|
| 1 | `bazi_calculator.py` | ✅ | `compute_chart` 运行成功=可用 |
| 2 | `api_server.py` | ✅ | `/api/health` 200=可用 |
| 3 | `claude_api.py` + `.env`（任一 LLM key） | ✅ | 聊天/分析功能需要 |
| 4 | `data_store.py` + `bazi_data.db` | ✅ | 持久化层（首次运行自动建表） |
| 5 | `auto_analyzer.py` | ✅ | 在线聊天与 /api/analyze 依赖 |
| 6 | `prompt_engine.py` + `prompts/` | ✅ | 在线聊天 prompt 依赖 |
| 7 | `report_builder.py` / `report_to_pdf.py` | ✅ | 报告与 PDF 生成 |
| 8 | `knowledge-base/bazi_kb.py` + `.db` | ✅ | 9表2,690条 + FTS5（`--build` 可重建） |
| 9 | `knowledge-base/case_retrieval.py` + `.chromadb_case_index/` | ✅ | 相似案例检索（无索引自动降级规则匹配） |
| 10 | `knowledge-base/{zeri,liunian_calendar,name_analysis,hehun,chuanren}.py` | — | 对应自助工具需要 |
| 11 | `mcp_server.py` | — | MCP 客户端接入需要 |
| 12 | `case_index.py` 四件套 + `benchmark/datasets/` | — | 评测/RAG 实验需要 |
| 13 | `config.py` | ✅ | 所有服务启动前置 |
| 14 | `tests/benchmark_charts/` | ✅ | 案例检索数据源（52个JSON） |
| 15 | `lunar_calendar.py` | ✅ | 被 bazi_calculator / api_server 导入 |

---

*文档结束*
