# 玄机子（XuanJiZi）

基于大语言模型与传统命理知识的八字命理分析服务，支持 REST API、MCP 服务、桌面端与 PDF 报告生成。

---

## 技术栈

- **语言**：Python 3.11+
- **Web 框架**：FastAPI + Uvicorn
- **桌面端**：pywebview
- **RAG**：SQLite + ChromaDB + sentence-transformers
- **PDF 报告**：fpdf2
- **容器化**：Docker + docker-compose

---

## 安装

```bash
# 1. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements-dev.txt

# 3. 安装 Playwright 浏览器（首次需要）
playwright install

# 4. 复制环境变量配置
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY
```

---

## 运行

### 本地开发

```bash
# 启动 API 服务
python api_server.py

# 启动 MCP 服务
python mcp_server.py --transport sse --port 8001

# 启动桌面端
python desktop_app.py
```

### Docker

```bash
docker-compose up --build
```

---

## 测试

```bash
# 全部测试
python -m pytest tests/ -q

# 仅运行 Phase 1 相关测试
python -m pytest tests/test_benchmark_shuffle_options.py \
                 tests/test_benchmark_self_consistency.py \
                 tests/test_mingli_bench_adapter.py -q
```

---

## 主要目录

| 目录 | 说明 |
|---|---|
| `api_server.py` | FastAPI REST 服务入口 |
| `mcp_server.py` | MCP 服务入口 |
| `bazi_calculator.py` | 八字排盘核心引擎 |
| `report_builder.py` / `report_to_pdf.py` | 报告渲染与 PDF 生成 |
| `case_index.py` | 案例检索与 evidence 评分 |
| `knowledge-base/` | SQLite 知识库与传统命理工具 |
| `benchmark/` | 评测框架（BaziQA + MingLi-Bench） |
| `tests/` | 单元测试与集成测试 |
| `scripts/` | 离线评估、数据构建等脚本 |
| `prompts/` | 各模式 prompt 模板 |

---

## 关键环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |
| `ANTHROPIC_API_KEY` | Anthropic API Key | - |
| `BAZI_API_PORT` | API 服务端口 | `8000` |
| `BAZI_MCP_PORT` | MCP 服务端口 | `8001` |
| `BAZI_API_KEY` | 服务鉴权 Key（留空不启用） | - |
| `BAZI_CORS_ORIGINS` | CORS 允许来源 | `http://localhost:8000,...` |
| `BAZI_LOG_LEVEL` | 日志级别 | `INFO` |

完整变量见 `.env.example`。

---

## 基准测试

```bash
# BaziQA 40×3 flash baseline
python scripts/run_baziqa_retrieval_ablation.py \
    --config-id option_grounded_tfidf --repeats 3 --max-cases 40

# MingLi-Bench smoke
python scripts/run_mingli_bench.py \
    --data data/mingli/data.json \
    --fortune data/mingli/fortune_api_results.json \
    --astro --model deepseek-v4-flash --year 2025 \
    --max-cases 20 --output-dir .tmp/mingli_smoke
```

---

## 文档

- 系统架构：`docs/SYSTEM_ARCHITECTURE.md`
- 准确率提升设计：`docs/superpowers/specs/2026-07-01-accuracy-improvement-design.md`
- Phase 1 实施计划：`docs/superpowers/plans/2026-07-01-phase1-evaluation-infra.md`

---

## 许可证

待定 / 私有项目
