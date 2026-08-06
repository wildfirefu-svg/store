# Phase 6 6D v1：八字命局 × 大运 × 目标流年确定性注入设计

**日期：** 2026-08-06
**状态：** 修订版（v2），待确认
**适用范围：** Phase 6 6D v1 时间定位题的确定性上下文注入
**前置依赖：** 6B2 ROLLBACK 证据归档（commit `acb63a1`）
**修订原因：** v1 存在 5 个阻断问题（零API准确率不可推断、历史流年不存在、协议路径错误、消融集计数错误、缺少可见性/schema/resume 隔离契约）

## 1. 背景与决策

### 1.1 6B2 ROLLBACK 的证据指向

6B2 双管线实验已 ROLLBACK，`protocol=single` 保持。2025 零 API 错误归因显示按 domain 的净变化：

| domain | n（cell 数） | B1-a′ | dual | Δ | rescue | regression |
|---|---:|---:|---:|---:|---:|---:|
| annual_fortune | 6 | 16.67% | 0.00% | **-16.67%** | 0 | 1 |
| career | 27 | 29.63% | 22.22% | **-7.41%** | 2 | 4 |
| family | 12 | 16.67% | 41.67% | +25.00% | 3 | 0 |
| relationship | 21 | 14.29% | 33.33% | +19.05% | 4 | 0 |
| health | 9 | 22.22% | 22.22% | 0.00% | 1 | 1 |
| study | 3 | 33.33% | 100.00% | +66.67% | 2 | 0 |
| unknown | 42 | 28.57% | 30.95% | +2.38% | 5 | 4 |

关键观察：

1. **退化集中在时间定位域**：`annual_fortune` 和 `career` 退化最严重，二者强依赖"命局 × 大运 × 流年"的确定性时间上下文。
2. **rescue 集中在非时间域**：`family` / `relationship` 的大幅 rescue 来自双管线的紫微臂，与时间定位无关。
3. **信号高度集中**：净增益最高的 3 道题合计贡献全部 +7，不能视为稳定全局改进。
4. **根因假设**：时间定位题退化的主因是**确定性时间上下文不足**，而非可检测的事实矛盾。这使 6C 后置、6D 优先成立。

### 1.2 决策

6D v1 只做"八字命局 × 大运 × 题目目标流年"的确定性注入，复用并抽离现有 `two_stage_reasoning.py` 的关系计算能力；暂不加入动态紫微流年。

### 1.3 协议路径约束（v1 阻断 3 修正）

6B2 已 ROLLBACK 到 `protocol=single`。B1-a′ 使用 `render_reasoned_context(case, schema, ziwei_arm)`（run_benchmark.py:458-467），而非 two-stage 路径（Phase 4 已暂停）。

**6D v1 的正确对照**：

| 臂 | 说明 |
|---|---|
| baseline | `single B1-a′`（`render_reasoned_context` + `ziwei_arm=none`，无 6D 注入） |
| 6D-on | `single B1-a′ + temporal context`（同路径 + 6D v1 注入） |

**不以 dual 为实验臂**。注入点在 `render_reasoned_context` 路径，不在 `two_stage_reasoning` 路径。

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 将 `two_stage_reasoning.py` 中的关系计算抽离为独立可复用模块 | 新模块无 prompt 字符串依赖 |
| G2 | 实现任意目标年份的确定性流年计算（不限当前年+2） | 算法版本冻结，历史年份可复现 |
| G3 | 对时间定位题注入"命局 × 大运 × 目标流年"确定性上下文 | 注入内容 100% 来自预计算，不含模型推断 |
| G4 | 零 API 离线门验证路由/覆盖/序列化/可见性/manifest 隔离 | 全部离线可测，不涉及准确率 |
| G5 | 小规模真实 paired dev 评估准确率 | 预声明 temporal-routed 题的 off/on paired gate |

### 2.2 非目标（v1 显式排除）

- **不加入动态紫微流年**：后置 6D v2
- **不改 6B2 gate 或重开 reuse**：6B2 已 ROLLBACK
- **不做 6C GroundedClaim Verifier**：后置，除非逐题复核证明主要错误是事实矛盾
- **不用 dual 为实验臂**：6D v1 只在 single B1-a′ 路径上评估
- **不用零 API 离线结果推断准确率**（v1 阻断 1 修正）：离线门只验证工程契约，准确率由真实 paired dev 评估

## 3. 历史流年计算设计（v1 阻断 2 修正）

### 3.1 问题

现有 `calculate_liunian(current_year, day_master_gan, num_years=3)`（bazi_calculator.py:1915）只生成 `current_year + i`（i=0..2）。BaziQA 大量目标年份为历史年份（如 1989、1990），`chart_input.liu_nian` 不含这些年份，`_get_liunian_for_year` 会返回 None。

### 3.2 方案

新建确定性函数 `calculate_liunian_for_year(target_year, day_master_gan)`，基于 60 甲子循环公式 `(target_year - 4) % 60` -> `sexagenary_by_index(idx)`，计算任意年份的干支和十神。

### 3.3 冻结规则（v1 阻断 5 补充）

以下规则在 6D v1 中冻结，任何变更需升 `temporal_context_version`：

| 规则 | 冻结值 | 说明 |
|---|---|---|
| 干支算法 | `(target_year - 4) % 60` -> `sexagenary_by_index` | 60 甲子循环 |
| 年龄口径 | **周岁**：`age = target_year - birth_year` | 不用虚岁 |
| 大运边界 | `start_age <= age <= end_age`（闭区间） | 端点归属明确 |
| 年份范围 | 1900-2100 | 超范围 fail-closed |
| 选项顺序 | 目标年份提取与选项顺序无关（按选项文本解析年份） | 选项 shuffle 不影响注入 |
| 立春边界 | 年柱以立春为界，但流年干支以公历年为准 | 与 `get_year_pillar` 的立春逻辑分离 |
| 多年份选项 | 一个选项含多个年份时，取第一个 4 位年份 | 冻结提取策略 |

## 4. 现有能力审计

### 4.1 `two_stage_reasoning.py` 可复用部分（关系计算层）

| 函数 | 行号 | 复用方式 |
|---|---|---|
| `_compute_branch_relation` | 367 | 直接迁移 |
| `_compute_gan_relation` | 438 | 直接迁移 |
| `_get_liunian_for_year` | 358 | **替换**为 `calculate_liunian_for_year`（支持历史年份） |
| `_get_question_type_hints` | 460 | 直接迁移 |
| `_KEY_SHENSHA` | 497 | 直接迁移 |
| `is_time_location_question` | 134 | 扩展后迁移 |

### 4.2 不复用部分（留在 formatter）

| 函数 | 原因 |
|---|---|
| `format_stage1_prompt` / `format_stage2_prompt` | two-stage 路径已暂停 |
| `_build_dayun_evidence` | option-driven 逻辑改为 target-year-driven |
| `_build_dayun_summary_for_stage1` | 计算部分迁移，prompt 拼接废弃 |

### 4.3 协议路径约束（v1 阻断 3 修正）

| 文件 | 约束 |
|---|---|
| chart_context.py:30 | `DENYLIST_FIELDS = ("kong_wang", "liu_nian")` - **liu_nian 字段被禁止** |
| profiles.py:95 | `_DENYLIST_MARKERS = {"【流年】", ...}` - **【流年】标记被禁止** |
| run_benchmark.py:458 | B1-a′ 走 `render_reasoned_context`，不走 two_stage |

**含义**：6D v1 注入不能通过 `chart_input.liu_nian` 字段，也不能用 `【流年】` 标记。必须用新的独立注入段和新的标记名。

## 5. 注入点设计

### 5.1 注入路径

注入在 `render_reasoned_context` 返回值末尾追加，不修改 `chart_input` 渲染逻辑，不绕过 `DENYLIST_FIELDS`。

### 5.2 注入内容标记

因 `【流年】` 被 `_DENYLIST_MARKERS` 禁止，6D v1 使用新标记：

| 标记 | 用途 | 是否在 DENYLIST |
|---|---|---|
| `【时间上下文·预计算】` | temporal context 段头 | 否（新标记） |
| `【大运排布】` | 大运表 | 否 |
| `【目标流年详析】` | 按选项年份的流年分析 | 否 |

这些标记必须加入 `profiles.py` 的 visibility 矩阵，且仅 `time_context_injection=on` 时允许出现。

## 6. 可见性、Schema 与 Resume 隔离契约（v1 阻断 5 修正）

### 6.1 新增字段

| 字段 | 类型 | 位置 | 说明 |
|---|---|---|---|
| `temporal_context_version` | str（如 `"6d-v1"`） | resume manifest / audit / receipt | 算法版本指纹 |
| `time_context_injection` | `"on"` / `"off"` | resume manifest / audit / receipt / run_context | 注入开关 |
| `target_year_extraction_hash` | str（SHA-256） | audit | 目标年份提取策略的确定性指纹 |

### 6.2 Resume 隔离规则

仿照 6B2 的 `thinking_mode` 隔离：

- `time_context_injection=on` 的 run **不能**被 `off` 的 run resume
- `time_context_injection=off` 的 run **不能**被 `on` 的 run resume
- `temporal_context_version` 不匹配时 fail-closed
- 检查点在 `_prepare_run_context`（与 6B2 `thinking_mode` 检查同层）

### 6.3 可见性矩阵扩展

`profiles.py` 的 `visibility_requirements` 必须扩展：

- `time_context_injection=off`：temporal context markers 加入 deny 侧
- `time_context_injection=on`：temporal context markers 加入 required 侧（仅对 temporal-routed 题）

### 6.4 代码指纹

`temporal_context_version` 进入：
- `run_context.json`
- `gates/*.json` receipt
- `audit_index.json`
- resume manifest

与 6B2 的 `thinking_mode` / `model_label` 同层绑定。

## 7. 评估方案：两阶段（v1 阻断 1 + 4 修正）

### 7.1 阶段一：零 API 离线门

**不涉及准确率**。验证工程契约：

| 检查项 | 验收口径 |
|---|---|
| 目标年份提取覆盖率 | 对 2025 全量 40 题，提取出的目标年份集合可审计 |
| 任意年份流年计算 | 1900-2100 范围内确定性可复现（SHA 锁定） |
| 路由覆盖 | temporal-routed 题与 non-temporal 题的分流边界明确 |
| 上下文序列化 | `TimeContext` 可 JSON 序列化，相同输入产生相同 SHA |
| 可见性矩阵 | `on`/`off` 下 marker 检查通过 |
| manifest 隔离 | `on` run 不能被 `off` resume（fail-closed） |
| prompt diff | `on` vs `off` 的 prompt 差异仅在 temporal context 段 |

**不声明**："6D 注入改善准确率"--离线无法推断。

### 7.2 阶段二：小规模真实 paired dev

**准确率评估**。对预声明的全部 temporal-routed 题做真实 paired dev：

| 配置 | 说明 |
|---|---|
| baseline | `single B1-a′` + `time_context_injection=off` |
| 6D-on | `single B1-a′` + `time_context_injection=on` |
| 对照口径 | paired 迁移表（rescue/regression），domain 级 Δ |
| run_id | 全新，不 resume 任何 6B2 run |

### 7.3 消融集设计（v1 阻断 4 修正）

**取消** v1 的"15 case × 3 重复 = 45 单元"设计（那是结果后筛选，不能做 gate）。

改为**两层分离**：

| 层 | 用途 | 选取方式 | 参与 gate |
|---|---|---|---|
| 全量预声明 temporal-routed 题 | 正式 paired gate | 在跑任何 6D 实验前，按 R1-R5 规则预声明全部 temporal-routed 题 | 是 |
| rescue/regression 样本 | 诊断回放 | 从 6B2 归因报告选取，仅做错误模式分析 | 否 |

预声明方式：在阶段一离线门完成后，输出 `temporal_routed_cases.json`（含 case_id 列表 + 检测命中的规则），**在阶段二真实 dev 启动前冻结**。

### 7.4 不做的事

- 不用零 API 结果推断准确率
- 不用 rescue/regression 样本做晋级判定
- 不重开 6B2 reuse
- 不改 6B2 gate 阈值

## 8. 隐性时间题检测规则

当前 `is_time_location_question` 只检测显式关键词和"选项全为 4 位年份"。6D v1 扩展：

| 规则 | 检测方式 | 覆盖 domain |
|---|---|---|
| R1 显式时间关键词 | 现有 `_TIME_KEYWORDS` | annual_fortune |
| R2 选项为 4 位年份 | 现有 `year_pattern` | annual_fortune |
| R3 选项为年龄区间 | `\d+[-–]\d+` 且含"岁" | career / annual_fortune |
| R4 题目含"大运/流年/岁运/年运" | 扩展关键词 | career |
| R5 题目含"何时/哪年/几年后" + 选项含年份 | 关键词 + 选项年份混合 | annual_fortune |

R3-R5 为新增，每条独立单测。阶段一离线门输出每条规则在 2025 上的命中 case 列表。

## 9. 抽离设计

### 9.1 新模块：`benchmark/formatters/bazi_time_context.py`

模块分层：

- **关系计算层**（无状态，从 two_stage_reasoning.py 迁移）：`compute_branch_relation` / `compute_gan_relation` / `compute_shishen_combo`
- **流年计算层**（新，支持任意年份）：`calculate_liunian_for_year`
- **检测层**：`is_temporal_routed` / `detect_time_context`
- **目标年份提取层**（新）：`extract_target_years`（冻结策略 + hash）
- **计算层**（无 prompt 依赖）：`build_natal_structure` / `build_dayun_table` / `build_target_liunian`
- **组装层**：`build_time_context`

### 9.2 数据契约：`TimeContext`

`TimeContext` 为 frozen dataclass，含 `natal` / `dayun_table` / `option_liunian` / `time_kind` / `target_years` / `extraction_hash`。纯数据，可 JSON 序列化，相同输入产生相同 SHA。

### 9.3 `chart_context.py` 改造

`render_reasoned_context` 末尾追加 temporal context 段（当 `time_context_injection == "on"` 且 case 为 temporal-routed 时）。`time_context_injection` 通过函数参数传入，不通过 `chart_input`。

## 10. 实施边界

| 文件 | 改动类型 |
|---|---|
| `benchmark/formatters/bazi_time_context.py` | 新建 |
| `benchmark/formatters/chart_context.py` | 改造：`render_reasoned_context` 加 `time_context_injection` 参数 |
| `benchmark/formatters/two_stage_reasoning.py` | 重构：关系计算迁移到新模块（two-stage 路径本身不改） |
| `benchmark/runners/profiles.py` | 扩展：visibility 矩阵加 temporal context markers |
| `benchmark/runners/run_benchmark.py` | 加 `--time-context-injection {on,off}` flag（默认 off） |
| `scripts/phase6_6b2_orchestrator.py` | 加 `time_context_injection` 到 `run_context` / receipt / audit |
| `tests/test_bazi_time_context.py` | 新建 |
| `tests/test_chart_context.py` | 新增：注入 on/off 行为测试 |

不修改：`claude_api.py` / `phase6_6b2_sealed_workflow.py` / `dual_system_reasoning.py` / `bazi_calculator.py`（只读取已有函数）。

## 11. 风险与回退

| 风险 | 缓解 |
|---|---|
| 隐性时间题检测过宽 | R3-R5 独立单测 + 2025 命中 case 审计 |
| 历史流年计算与排盘不一致 | 算法冻结 + SHA 锁定 + 与 `get_year_pillar` 立春逻辑分离 |
| 注入内容过长 | 长度上限 + 截断策略 |
| 6D-on/off 误续跑 | resume 隔离 fail-closed |

回退：`--time-context-injection off`（默认），不修改 6B2 已归档证据。

## 12. 完成定义

6D v1 设计阶段的完成定义：

1. 本设计文档进入 Git（修订版）
2. `bazi_time_context.py` 模块边界与 `TimeContext` 契约确认
3. 历史流年计算算法版本冻结（`temporal_context_version`）
4. 目标年份提取策略冻结 + hash 规则确认
5. 隐性时间题检测规则 R3-R5 的 2025 命中 case 列表可审计
6. 可见性矩阵扩展方案确认（不绕过现有 DENYLIST）
7. resume 隔离规则确认（on/off 不可互续）
8. 两阶段评估方案确认（离线门 + 真实 paired dev）

实施计划（Task 1-N）在本设计确认后单独编写。
