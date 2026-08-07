# Agent 工作流增强设计（Harness 五维优化）

**日期：** 2026-08-07（v2 修订）
**状态：** 决策方向已确认（硬拦截 + FULL_SUITE 人工批准），设计 v2 已修订，待进入实施计划
**适用范围：** `.qoder/` 代理资产面（Rules / Hooks / Skills / Custom Agents）与项目 Memory 运营

**v2 变更记录（相对 v1）：**

1. §4.3 Hook 契约冻结：matcher 改用 Qoder 官方工具名 `Write|Edit|Bash`；`exit 2` 拒绝原因写 stderr（deny JSON 仅在 `exit 0` 时解析，两种协议不混用）；新增 Bash 显式写入路径拦截；保护范围如实表述为"阻止直接文件工具和显式 Bash 命令"，不宣称不可绕过。
2. §4.1 第 3 段改为两阶段流程：先干跑 `affected_tests.py` 读映射，命中 `FULL_SUITE` 必须等待用户明确批准后才能 `--run`（源码确认 `--run` + `full_suite` 会立即启动全量 pytest，无确认机会）。
3. §4.2 修正规则优先级：Qoder 平台 Rules 优先级高于 AGENTS.md，故改为"Rules 不得重定义或放宽 AGENTS.md，生成时做一致性检查"。
4. §7 回退清单修正：明确包含 `.qoder/settings.json` 与 `AGENTS.md` 的处理。
5. §4.2 事实修正：`core-boundary.md` 的验证入口表述由"改动后必跑 §9 三脚本"放宽为"按要验证的声明选择对应入口"（AGENTS.md §9 未要求每次改动全跑，Rules 优先级更高，写成必跑会意外增加全局强制约束）。
6. §7 事实修正：当前仓库不存在 `.qoder/settings.json`，回退改为条件化处理（存在则快照恢复，不存在则新建后删除）。
7. §4.5/§6 验收收紧：Memory 验收要求 Qoder Memory 面实际出现至少一条经审核记录（可被 SearchMemory 检索），仅在 AGENTS.md 追加运营约定行不作为通过依据。

## 1. 背景与决策

2026-08-07 Better Harness 分析（报告位于 `.qoder/better-harness/2026-08-07/091636-agent/`）给出五维评分：

| 维度 | 分数 | 主要证据缺口 |
|---|---|---|
| 任务理解 | 68 | 热点目录缺局部指导 |
| 可控执行 | 62 | 无 Hooks / Custom Agents，高频子任务消耗主会话上下文 |
| 改动验证 | 59 | 门禁链（ruff → mypy → affected_tests → smoke）需手动拼命令 |
| 可靠交付 | 50 | 核心数据文件无写保护，无会话结束检查提醒 |
| 经验沉淀 | 35 | 项目 Memory 为 0，跨会话经验不可复用 |

已完成的修复（不属于本设计范围，仅作为基线）：

- 会话观测源已启用（`.qoder` → `.qoder-cn` junction + workspace slug junction），evidence-bundle 现可捕获 16 sessions / 60 task episodes；
- 4 个项目 Skill 已具备 trigger / procedure / output / validation 完整结构，`scripts/verify_skill_sync.py` 校验通过。

Qoder 平台支持的扩展面（依据平台文档）：Rules（`.qoder/rules/`）、Hooks（settings 注册 + 脚本）、Skills（`.qoder/skills/{name}/SKILL.md`）、Custom Agents（`.qoder/agents/{name}.md`）、MCP、Memories。当前仓库中 `hooks/`、`agents/`、`rules/` 三个目录均不存在，Memories 计数为 0。

## 2. 目标

1. 用一条命令完成完整门禁链验证（quality-gate Skill）。
2. 为三个高频变更域提供局部 Rules，降低代理探索成本。
3. 用 Hooks 保护被跟踪的数据产物，并在核心目录编辑后提示受影响测试。
4. 将高频子任务封装为 Custom Agents，保持主上下文干净。
5. 建立项目 Memory 运营约定，使经验沉淀维度可随会话积累提升。

## 3. 非目标

- 不修改既有 4 个 Skill（dev / docker-up / quality-check / test-suite）的内容。
- 不修改核心代码（`bazi_calculator.py`、`scripts/` 门禁脚本本身）。
- 不引入新的第三方依赖或 MCP 服务器。
- 不把本设计的资产镜像到 `.reasonix/skills/`——镜像机制只覆盖 Skills 面（见 AGENTS.md §10），Rules / Hooks / Agents 是 Qoder 原生面。
- 不在本设计中授权任何破坏性 Git 操作或 CI 行为变更。

## 4. 各项设计

### 4.1 quality-gate Skill（改动验证，优先级 P0）

新建 `.qoder/skills/quality-gate/SKILL.md`，frontmatter 结构：

```yaml
---
name: quality-gate
description: 一键运行完整提交前门禁链（ruff → mypy → affected_tests → smoke）
trigger: 用户要求运行完整门禁、提交前检查、或需要一次性验证所有静态检查与聚焦测试时使用；单文件快速迭代优先用 test-suite skill
output: 门禁链逐段结果（每段 pass/fail + 关键输出），任一失败即停止并给出失败段的具体信息与修复方向
validation: 四段命令退出码均为 0；失败时输出具体失败项（lint 规则号 / 类型错误 / 断言信息），不输出笼统报错
---
```

正文步骤（与 CI `test` 作业及 `.pre-commit-config.yaml` 对齐）：

1. `ruff check .`（基线 E9/F821，配置见 `ruff.toml`）
2. `mypy`（增量白名单，配置见 `mypy.ini`）
3. 受影响测试（两阶段流程，不得直接 `--run`）：

```text
阶段 a: python scripts/affected_tests.py          # 干跑，只读测试映射
阶段 b:
  若 stdout 含 FULL_SUITE：
    告知触发原因（tests/ 或 pytest.ini / requirements*.txt 变更）
    与预计范围（全量套件），等待用户明确批准
    批准后：python scripts/affected_tests.py --run
    无人值守或用户未回复：停在本段，不得默认为批准
  否则：
    直接执行 python scripts/affected_tests.py --run
```

   依据：`scripts/affected_tests.py` 在 `--run` 且命中 `full_suite` 时立即 `subprocess.run(pytest_command(["tests/"]))`，中间没有任何确认点。
4. `python scripts/verify_smoke.py`

与既有 test-suite Skill 的分工：test-suite 负责按变更面选择测试范围；quality-gate 负责完整静态 + 动态门禁链。两者不重复覆盖。

### 4.2 嵌套 Rules（任务理解，优先级 P0）

在 `.qoder/rules/` 下创建三个规则文件，采用平台支持的规则类型：

| 规则文件 | 类型 | 适用模式 | 核心内容 |
|---|---|---|---|
| `core-boundary.md` | Always Apply | 全部请求 | 核心代码边界（受 AGENTS.md §4 约束的文件清单）、被跟踪数据产物禁改清单、按要验证的声明选择对应验证入口（AGENTS.md §9 入口表）——不写成"每次改动必跑全部脚本"，AGENTS.md §9 无此要求，Rules 优先级更高，误写必跑会额外增加全局强制约束 |
| `scripts-safety.md` | Specific Files | `scripts/**` | 门禁脚本只增不破坏既有 CLI 契约；运行评测脚本前先确认预算参数；实验指纹范围文件缺失必须 fail-closed |
| `benchmark-conventions.md` | Specific Files | `benchmark/**` | runners/formatters/scorers 的模块职责边界；resume/ledger 子系统入口；outputs/ 为运行产物不得手改 |

规则正文只写约束与入口，不复制 AGENTS.md 全文。

优先级约束（平台事实修正）：Qoder 官方规则优先级中 Rules 高于 AGENTS.md，因此不能声明"冲突时以 AGENTS.md 为准"——那样规则反而会压过 AGENTS.md。本设计改用生成期一致性约束：

- Rules 不得重定义或放宽 AGENTS.md 已有的约束（禁改清单、验证入口、核心边界只可复述，不可改写）；
- 新增或修改任一规则文件时，逐条对照 AGENTS.md §4/§9 做一致性检查，确认无放宽项后才落盘；
- 规则文件中显式写明："本规则复述 AGENTS.md 对应章节的约束，不引入新豁免"。

### 4.3 Hooks（可靠交付，优先级 P1）

在项目级 Qoder settings（`.qoder/settings.json`）注册两个 Hook 脚本，脚本放 `.qoder/hooks/`，用 Python 编写以保证 Windows 兼容（不依赖 bash/jq）。

**冻结的 Hook 契约（v2）：**

```text
guard-data-artifacts.py
  事件: PreToolUse
  matcher: Write|Edit|Bash          # Qoder 官方工具名

  Write / Edit 分支:
    规范化 cwd + file_path（相对路径锚定项目根）
    命中禁改模式 → 拒绝原因写 stderr + exit 2

  Bash 分支:
    命令显式引用禁改路径 且 包含写入/移动/删除操作
      （如 重定向 > >>、mv/move、rm/del/Remove-Item、git rm/checkout -- 等）
      → 拒绝原因写 stderr + exit 2
    其余 → exit 0 放行

remind-affected-tests.py
  事件: PostToolUse
  matcher: Write|Edit
  目标路径命中 scripts/** 或 benchmark/** → stdout 提示运行
    python scripts/affected_tests.py，exit 0（不阻断）
```

协议纪律（两种机制不混用）：

- 阻断用 `exit 2`，拒绝原因写 **stderr**；
- `exit 0` + stdout deny JSON 是另一套精细控制协议，本设计不使用；
- 参照：[Qoder Hooks](https://docs.qoder.com/extensions/hooks)。

禁改模式清单（与 AGENTS.md §4 单一事实源同步）：`knowledge-base/*.json`、`tests/case_db.json`、`data/*.json`、`benchmark/datasets/*.jsonl`。脚本内清单以注释标注"与 AGENTS.md §4 同步"。

**保护范围的如实表述：** Bash 分支只能识别命令文本中显式出现的禁改路径，无法保证识别动态拼接、变量展开或间接脚本调用产生的路径。因此本 Hook 的保护承诺是"阻止直接文件工具（Write/Edit）和显式 Bash 命令触碰禁改文件"，不宣称绝对不可绕过。文档、规则与验收表述均以此为准。

其他约束：

- 脚本从 stdin 读取 JSON 事件上下文；脚本自身不得回显原始 prompt、环境变量或疑似密钥。
- Hook 只做守护与提示，不自动执行测试（避免提交级时延陷阱，参照 pre-commit 选型教训）。

### 4.4 Custom Agents（可控执行，优先级 P1）

在 `.qoder/agents/` 下创建三个专用代理，工具权限最小化：

| Agent | 职责 | tools | 触发示例 |
|---|---|---|---|
| `bench-runner.md` | 运行 benchmark/phase 评测并汇总准确率对比 | Read, Bash | "跑一次 6B2 定向回归" |
| `core-guard.md` | 核心文件变更影响面审查（只读） | Read, Grep, Glob | "审查这次改动对核心链路的影响" |
| `rag-debugger.md` | RAG 检索问题诊断（检索日志、命中分析） | Read, Bash, Grep | "这个 case 为什么检索不到正确条文" |

每个 Agent 文件格式遵循平台契约（frontmatter：name / description / tools；正文为 system prompt）。只读代理不给 Write/Edit 权限；需要执行命令的代理，其 Write/Edit 与显式 Bash 写入受 4.3 Hook 的 PreToolUse 保护（保护范围以 4.3 的如实表述为准，动态拼接路径不在承诺内）。

### 4.5 项目 Memory 运营约定（经验沉淀，优先级 P2）

不创建新文件，建立运营约定（写入 AGENTS.md §14 追加一行——这是对既有文件的修改，已列入 §7 回退清单）：

- 沉淀类别：已验证的环境配置、核心边界约束、评测基线数值、踩坑教训（fail-closed、编码陷阱等）。
- 触发时机：修复任务验证通过后、用户纠正做法后、发现可复用结论后。
- 质量约束：只记具体可执行规则，不记泛泛提醒；密钥与凭据永不入库。
- 度量：Qoder Memory 面实际出现至少一条经审核的项目级记录（后续会话可被 SearchMemory 检索）；仅在 AGENTS.md 追加运营约定行不作为通过依据。learning-capture 维度分数提升作为后续观察项。

## 5. 实施顺序与依赖

```text
P0: 4.1 quality-gate Skill ─┐
    4.2 Rules × 3           ─┴─ 无依赖，可并行
P1: 4.3 Hooks（依赖 4.2 core-boundary 的禁改清单定稿）
    4.4 Custom Agents（无强依赖）
P2: 4.5 Memory 运营（持续进行，无交付物）
```

## 6. 验收标准

| 项 | 验证方式 |
|---|---|
| quality-gate | 触发该 Skill 后四段门禁依次执行；人为引入一处 E9 错误时在第 1 段失败并输出规则号 |
| Rules | 编辑 `scripts/` 下文件时会话上下文中出现对应规则约束；`core-boundary` 在任意请求中可见 |
| Hooks | Write/Edit 写 `knowledge-base/*.json` 被拒（exit 2 且 stderr 含原因）；Bash 显式 `Remove-Item knowledge-base/xxx.json` 同样被拒；编辑 `scripts/` 文件后出现 affected_tests 提示；动态拼接路径场景记录为已知不覆盖，不算验收失败 |
| Custom Agents | 三个代理可通过 `/agent-name` 或自然语言触发，工具权限与 frontmatter 声明一致 |
| Memory | Qoder Memory 面实际出现至少一条经审核的项目级记录（后续会话可被 SearchMemory 检索到）；仅完成 AGENTS.md §14 追加行不算通过 |
| 回归 | 实施后运行 `python scripts/verify_smoke.py` 与 `python -m pytest -m "not e2e" -q` 不新增失败 |

## 7. 风险与回退

- Hook 误拦截：deny 清单仅限 AGENTS.md §4 已声明的禁改文件；误报时从清单移除对应模式即可，脚本无状态。
- 规则漂移：Rules 平台优先级高于 AGENTS.md，靠生成期一致性检查防止放宽（见 §4.2）；发现规则与 AGENTS.md 不一致时以删除或修正规则为准。
- Bash 绕过：显式命令拦截不覆盖动态拼接路径（见 §4.3），残余风险由 code review 与 CI 兜底。
- 回退清单（`AGENTS.md` 为既有文件；`.qoder/settings.json` 当前仓库不存在，条件化处理）：

| 资产 | 回退动作 |
|---|---|
| `.qoder/skills/quality-gate/` | 删除目录 |
| `.qoder/rules/` | 删除目录 |
| `.qoder/hooks/` | 删除目录 |
| `.qoder/agents/` | 删除目录 |
| `.qoder/settings.json` | 实施前若存在：保存原内容，回退时恢复；实施前若不存在（当前状态）：实施时新建，回退时删除 |
| `AGENTS.md` | **既有文件**：若 §14 追加了 Memory 运营行，回退时删除该行（实施前记录原始行内容） |
