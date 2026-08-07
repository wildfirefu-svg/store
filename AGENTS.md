# AGENTS.md — 玄机子（XuanJiZi）项目代理规范

> 面向本仓库所有编码代理（Kimi Code / Codex / Claude Code / Reasonix 等）的操作规范。**每个任务开始前先读本文件。**
> 遵循 [AGENTS.md](https://agents.md) 开放标准。`CLAUDE.md` 仅含 Claude Code 专用补充，通用规则以本文件为准。

**只交付可运行的代码。把活干完。看起来对 ≠ 正确。**

---

## 0. 最高原则（与下文冲突时以本节为准）

1. **不奉承、不废话**。不要"好问题""你说得对""我很乐意"这类开场，直接给结论或动手。
2. **该反对就反对**。用户前提错了，先指出再动手；为了礼貌附和错误前提是编码代理最糟的失败模式。
3. **绝不编造**。文件路径、commit、API 名、测试结果、库函数——不确定就去读文件、跑命令，或直说"我不知道，去查一下"。
4. **困惑时停下**。任务有两种合理解读就先问，不要默默选一种往下做。
5. **只碰必须碰的**。每一行改动都要能直接追溯到用户需求；不顺手重构、不重排格式、不做"顺便清理"。

---

## 1. 项目背景

**玄机子**是基于大语言模型 + 传统命理知识的八字命理分析服务，提供 REST API、MCP 服务、桌面端与 PDF 报告。
核心不是"AI 随口给结论"，而是"结构化排盘 + 知识库检索(RAG) + 证据评分 + 可复核的评测闭环"。

当前重心是 **BaziQA / MingLi-Bench 评测准确率与检索(RAG)优化**（见 `docs/` 下大量审计与实验报告，以及 `docs/superpowers/` 下的 specs/plans）。

---

## 2. 技术栈（已由仓库文件验证，勿臆造）

- **语言**：Python 3.11+
- **Web / 服务**：FastAPI + Uvicorn；MCP 服务；桌面端用 pywebview
- **RAG / 检索**：SQLite + ChromaDB + sentence-transformers；另有 TF-IDF / BM25 / 混合检索
- **PDF 报告**：fpdf2
- **测试**：pytest（含 `e2e`、`slow` 标记）；E2E 用 Playwright
- **容器化**：Docker + docker-compose
- **包管理**：pip（`requirements.txt` / `requirements-dev.txt`）

> 禁止在未经本仓库文件验证前，擅自改用其它语言、框架、包管理器、数据库或部署方式。

---

## 3. 常用命令

```powershell
# 安装（首次）
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements-dev.txt
pre-commit install                              # 本地提交门禁（见 §9），每个 clone 跑一次
playwright install
copy .env.example .env   # 编辑填入 DEEPSEEK_API_KEY / ANTHROPIC_API_KEY

# 本地运行
python api_server.py                              # REST API（默认 8000）
python mcp_server.py --transport sse --port 8001  # MCP 服务
python desktop_app.py                             # 桌面端

# 测试
python -m pytest tests/ -q                        # 全量（合并前跑）
python -m pytest tests/test_xxx.py -q             # 单文件（迭代时优先）
python -m pytest -m "not e2e" -q                  # 跳过 E2E
python -m pytest -m e2e -q                        # 仅 E2E（会起真实服务）

# Docker
docker-compose up --build
```

迭代阶段优先跑单文件/单测；全量套件留给最终验证。测试范围可参考 `.qoder/skills/test-suite/SKILL.md` 里“改了什么→跑哪个测试”的映射表。

---

## 4. 目录要点（高风险 / 必须知道）

- `bazi_calculator.py` 是排盘核心引擎；`scripts/` 含验证与门禁脚本（见第 9 节），两者变更受核心代码边界约束。
- 设计与实施计划在 `docs/superpowers/{specs,plans}/`，动手前先看对应文档。
- **不要修改**：被跟踪的数据产物（`knowledge-base/*.json`、`tests/case_db.json`、`data/*.json`、`benchmark/datasets/*.jsonl`）。
- **不要碰**：`.tmp/`、`.cache/`、`.chromadb_case_index/` 等运行产物目录，以及与当前任务无关的用户文件。
- 其余结构直接用工具探索，不在此维护全量目录表。

---

## 5. 关键环境变量

`DEEPSEEK_API_KEY`、`ANTHROPIC_API_KEY`、`BAZI_API_PORT`(8000)、`BAZI_MCP_PORT`(8001)、`BAZI_API_KEY`(服务鉴权，留空不启用)、`BAZI_CORS_ORIGINS`、`BAZI_LOG_LEVEL`(INFO)。完整见 `.env.example`。

**密钥只放 `.env` 或本地安全配置，绝不写入源码、日志、前端产物或提交历史；输出/日志涉及密钥要脱敏。**

---

## 6. 动手前（先理解，再产出 diff）

- 动手前用一两句话说明计划；非平凡任务给出带验证点的编号步骤。
- 读你要改的文件，也读调用它们的文件。探索型任务用子代理（Kimi 的 `Agent`/`explore`），保持主上下文干净。
- **匹配现有模式**：项目用 X 模式就用 X，即使你个人更喜欢别的写法。
- 把假设说出来："我假设你要的是 X/Y/Z，如果不对请纠正"，别把假设埋进实现里。
- 两种方案就摆出来讲权衡，别默默选。例外：改错别字/重命名/加日志这类一句话能说清的小改。

---

## 7. 写代码：简单优先 + 外科手术式改动

- 不做需求外的功能；不给一次性代码加抽象、配置或钩子。
- 不为"不可能发生的场景"加错误处理；只处理真会发生的失败。
- 200 行能压到 50 行就先重写再给我；出现"为了将来可扩展"就停手。
- 倾向删代码而非加代码。
- 不"顺手改进"相邻代码/注释/格式/import；不重构本来能跑的代码；发现死代码只在总结里提，不擅自删。
- 只清理你自己改动产生的孤儿（无用 import/变量/函数）。
- 严格匹配项目既有风格：缩进、引号、命名、文件布局。约定：模块/函数 `snake_case`，类 `PascalCase`；新文件优先 `from __future__ import annotations`，用绝对导入。

判据：每一行改动都能直接追溯到用户需求；追溯不到就回退。

---

## 8. 目标驱动执行与验证

把模糊需求改写成**可验证目标**再动手：

- "加校验" → "为非法输入（空/畸形/超限）写测试，再让它们通过"。
- "修 bug" → "先写能复现症状的失败测试，再让它通过"。
- "重构 X" → "改动前后测试套件都通过，且公共 API 不变"。
- "变准/变快" → "先量化基线，定位瓶颈，改完用同一指标证明变好"。

每个任务：**先定成功标准 → 写验证（测试/脚本/评测）→ 跑验证读输出 → 失败就修根因不是改测试**。

- 优先跑代码而不是猜代码：有测试跑测试，有 E2E 用 `-m e2e`。
- **绝不凭"看起来对的 diff"报完成**。
- 评测/准确率类改动：跑对应 `scripts/` 脚本或 `benchmark/` 流程，用 `report.md` / gate 报告为证，别口头断言分数。
- 读日志/报错/堆栈要读全，半截堆栈会导致错误修复。
- 若测试确实跑不了，说明具体原因，绝不谎称"测试通过"。

---

## 9. 可执行验证入口（harness / agent 可直接触发）

以下脚本由代理或 harness 运行，产出 passed/ok 或具体失败信息，并写入 `.better-harness/verified-claims.json` 供 `core-change-watch` 证据包消费。它们只消除本地实际验证过的声明；远程 CI 状态仍须由 CI 平台证据单独确认。

| 声明 | 命令 | 验证内容 |
|------|------|----------|
| focused smoke tests passed | `python scripts/verify_smoke.py` | 运行 pytest 聚焦 smoke 测试（四柱 + 前端资产），不代表全量测试通过 |
| CI workflow configuration | `python scripts/verify_ci.py` | 校验 `.github/workflows/ci.yml` 结构与 pytest 步骤，不代表远程 CI 已通过 |
| runtime behavior | `python scripts/verify_runtime.py` | 启动 `api_server.py` 并检查 `/api/health` |

一键生成已验证证据包：

```
python scripts/run_verified_evidence_pack.py [.qoder/better-harness/<run-dir>]
```

该命令会依次运行上述三个验证脚本、合并为 `verified-claims.json`、调用 `core-change-watch evidence-pack`、并自动把验证结果写入 evidence pack 的 `reviewMatrix` 与 `evidenceSources`。

按变更范围选测试（affected-tests 门控）：

```
python scripts/affected_tests.py            # git diff 路径 → 最小 pytest 文件列表
python scripts/affected_tests.py --run      # 顺带执行选中的测试
```

CI 中的 `affected-tests` 作业即调用此脚本，为阻塞式快速门禁；全量 `test` 作业仍是最终合并门禁。`test` 作业在 pytest 之前还运行 lint（`ruff check .`，配置见 `ruff.toml`）与类型检查（`mypy`，增量白名单见 `mypy.ini`）两个机械化门禁。

本地提交门禁（pre-commit hook，失败阻塞提交）：

```
pre-commit install    # 每个 clone 安装一次（依赖已在 requirements-dev.txt）
git commit ...        # 自动依次运行 ruff check（E9/F821 基线）+ 聚焦 smoke 测试（scripts/verify_smoke.py），任一失败即阻塞提交
```

配置见 `.pre-commit-config.yaml`。hook 只做本地快速拦截（有界 smoke 层，不含全量套件）；全量验证仍以 CI `test` 作业为准。紧急情况可用 `git commit --no-verify` 绕过，但必须随后补跑验证。

> 为何不直接用 `affected_tests.py --run` 作 hook：改动命中 `tests/`、`pytest.ini`、`requirements*.txt` 时它会触发全量套件（见脚本 `FULL_SUITE_TRIGGERS`），不适合提交级时延，故 hook 用其同层的有界 smoke（`verify_smoke.py`）；`affected_tests.py` 仍供手动与 CI 使用。

---

## 10. 与 Superpowers 技能协同

本机已装 Superpowers 技能。**动手前先判断是否有技能适用**，命中就先读其 `SKILL.md` 并遵循：

- "做个 X" → 先 `brainstorming`；"修 bug" → 先 `systematic-debugging`。
- 有设计 → `writing-plans` 拆 TDD 小任务；执行 → `subagent-driven-development` + `test-driven-development`；收尾 → `finishing-a-development-branch`。
- 本仓库的设计/计划沉淀在 `docs/superpowers/{specs,plans}/`，动手前先看对应文档。
- 项目自带技能（`dev`、`docker-up`、`quality-check`、`test-suite`）的唯一权威面是 `.qoder/skills/`，本文档所有技能引用均指向该面；`.reasonix/skills/` 仅为其他 provider 的镜像副本。两侧一致性用 `python scripts/verify_skill_sync.py` 校验（漂移时报错并提示以 `.qoder/skills/` 为准重新同步）。

---

## 11. Git 与工作区

- 主分支保持稳定基线；功能开发优先用功能分支或 `git worktree` 隔离。
- 提交信息说明"为什么改"（主题 <72 字符，正文讲动机），遵循语义化提交；不写"update file""fix bug"这类空信息；不加 `Co-Authored-By` 除非项目明确要求。
- 提交前跑相关测试或说明为何跑不了。
- **不使用破坏性 Git 命令**（`push --force`、`reset --hard`、`clean -fd` 等），除非用户明确要求。
- 删除/移动文件前以 `git status`、`git worktree list` 实况为准，不按文档路径盲删；不删用户已有文档或未分配文件。

---

## 12. 沟通风格

- 直接，不外交辞令："这样不行，因为 X"胜过"这思路挺有意思，不过……"。
- 默认简洁：两三段短文，除非用户要深入。不复述问题、不加仪式性结尾、不堆无谓的标题/emoji。
- 有明确答案就给；没有就说明并给出你对权衡的最佳判断。
- 只为真正重要的事庆祝（交付、解决真难题、指标真的动了），不为点子或范围膨胀。

---

## 13. 何时问、何时干

**先问**：需求有两种合理解读且影响结果；改动触及被告知是"承重/带迁移路径"的部分；需要你没有的凭据/密钥/生产资源；用户目标与字面需求冲突。

**直接干**：任务琐碎可逆（错别字、重命名局部变量、加日志）；歧义能靠读代码/跑命令消除；同一问题用户本会话已答过。

---

## 14. Project Learnings（由代理维护）

用户纠正你的做法后，在此追加一行**具体**规则（"总是用 X 做 Y"，而非"注意 Y"）。已有行能覆盖就收紧它而不是新增；问题消失（模型升级/重构）就删除对应行。保持精简——本文件越短越会被认真执行（建议 <300 行）。

- 总是用 UpdateMemory 沉淀经验（环境配置、核心边界约束、评测基线、踩坑教训）；只记具体可执行规则，密钥与凭据永不入库。
