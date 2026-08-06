# Phase 6 6D v1：八字命局 × 大运 × 目标流年确定性注入设计

**日期：** 2026-08-06
**状态：** 修订版（v3），待确认
**适用范围：** Phase 6 6D v1 时间定位题的确定性上下文注入
**前置依赖：** 6B2 ROLLBACK 证据归档（commit `acb63a1`）
**修订历史：** v1 -> v2（5 阻断修正）-> v3（4 P0 + 3 中优修正）

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

退化集中在时间定位域（annual_fortune / career）；rescue 集中在非时间域（family / relationship）；信号高度集中，不能推翻 ROLLBACK。根因假设：时间定位题退化的主因是确定性时间上下文不足，而非可检测的事实矛盾。这使 6C 后置、6D 优先成立。

### 1.2 决策

6D v1 只做"八字命局 × 大运 × 题目目标流年"的确定性注入，复用并抽离现有 `two_stage_reasoning.py` 的关系计算能力；暂不加入动态紫微流年。

### 1.3 协议路径约束

6B2 已 ROLLBACK 到 `protocol=single`。B1-a′ 使用 `render_reasoned_context(case, schema, ziwei_arm)`（run_benchmark.py:458-467），而非 two-stage 路径（Phase 4 已暂停）。

6D v1 的正确对照：`single B1-a′ off` vs `single B1-a′ + temporal context on`。不以 dual 为实验臂。

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 将 `two_stage_reasoning.py` 中的关系计算抽离为独立可复用模块 | 新模块无 prompt 字符串依赖 |
| G2 | 实现任意目标年份的确定性流年计算 | 算法版本冻结，历史年份可复现 |
| G3 | 对时间定位题注入确定性上下文 | 100% 来自预计算，不含模型推断 |
| G4 | 零 API 离线门验证工程契约 | 全部离线可测，不涉及准确率 |
| G5 | 独立 6D 实验链执行 paired dev 并评估准确率 | 预声明 temporal-routed 题的 off/on paired gate |
| G6 | 6D 字段进入 manifest/receipt/audit 并跨阶段校验 | on/off 不可互续（fail-closed） |

### 2.2 非目标

- 不加入动态紫微流年（后置 6D v2）
- 不改 6B2 gate 或重开 reuse（6B2 已 ROLLBACK）
- 不做 6C（后置，除非逐题复核证明主要错误是事实矛盾）
- 不用 dual 为实验臂
- 不用零 API 离线结果推断准确率

## 3. 历史流年计算设计

### 3.1 问题

现有 `calculate_liunian(current_year, day_master_gan, num_years=3)`（bazi_calculator.py:1915）只生成 `current_year + i`（i=0..2）。BaziQA 大量目标年份为历史年份，`chart_input.liu_nian` 不含这些年份。

### 3.2 方案

新建确定性函数 `calculate_liunian_for_year(target_year, day_master_gan)`，基于 60 甲子循环公式 `(target_year - 4) % 60` -> `sexagenary_by_index(idx)`。

### 3.3 冻结规则

以下规则在 6D v1 中冻结，任何变更需升 `temporal_context_version`：

| 规则 | 冻结值 | 说明 |
|---|---|---|
| 干支算法 | `(target_year - 4) % 60` -> `sexagenary_by_index` | 60 甲子循环 |
| 年龄口径 | **年份差近似年龄**：`age_approx = target_year - birth_year` | 明确不是严格周岁（缺目标月日），仅用于大运匹配 |
| 大运边界 | `start_age <= age_approx <= end_age`（闭区间） | 端点归属明确 |
| 年份范围 | 1900-2100 | 超范围 fail-closed |
| 选项顺序 | 目标年份提取与选项顺序无关 | 选项 shuffle 不影响注入 |
| 立春边界 | 流年干支以公历年为准 | 与 `get_year_pillar` 立春逻辑分离 |
| 多年份选项 | 取第一个 4 位年份 | 冻结提取策略 |

### 3.4 目标流年三态路由（v3 P0 修正）

v2 的 R3-R5 会路由年龄区间题但无目标年份转换，导致"成功路由、空注入"。v3 冻结三态：

| 状态 | 含义 | 触发条件 | 注入行为 |
|---|---|---|---|
| `ROUTED_WITH_TARGETS` | 路由且有目标年份 | R1/R2/R5 命中，提取到 ≥1 个 4 位年份 | 完整 temporal context |
| `ROUTED_WITHOUT_TARGETS` | 路由但无目标年份 | R3/R4 命中，但无法转换为具体年份 | 仅注入大运排布 + 命局结构，不注入目标流年 |
| `NOT_ROUTED` | 不路由 | R1-R5 均不命中 | 不注入任何 temporal context |

### 3.5 年龄/区间/"几年后"转换规则

| 输入 | 转换规则 | 输出 |
|---|---|---|
| 4 位年份（如 1989） | 直接用作 target_year | `ROUTED_WITH_TARGETS` |
| 年龄区间（如 25-30 岁） | `start_year = birth_year + start_age`；`end_year = birth_year + end_age`；取中点年份 `mid_year = (start_year + end_year) // 2` | `ROUTED_WITH_TARGETS`（mid_year 为目标） |
| 单年龄（如 30 岁） | `target_year = birth_year + age` | `ROUTED_WITH_TARGETS` |
| "几年后"（如"3 年后"） | 需题目含基准年份 `base_year`，`target_year = base_year + N`；无基准年份则 `ROUTED_WITHOUT_TARGETS` | 视情况 |
| R4 关键词但无年份 | 无法转换 | `ROUTED_WITHOUT_TARGETS` |

所有转换必须可单测，且输出 `target_years` tuple 参与 `extraction_hash`。

## 4. 现有能力审计

### 4.1 可复用部分（关系计算层）

| 函数 | 行号 | 复用方式 |
|---|---|---|
| `_compute_branch_relation` | 367 | 直接迁移 |
| `_compute_gan_relation` | 438 | 直接迁移 |
| `_get_liunian_for_year` | 358 | **替换**为 `calculate_liunian_for_year` |
| `_get_question_type_hints` | 460 | 直接迁移 |
| `_KEY_SHENSHA` | 497 | 直接迁移 |
| `is_time_location_question` | 134 | 扩展后迁移 |

### 4.2 协议路径与 DENYLIST 约束

| 文件 | 约束 |
|---|---|
| chart_context.py:30 | `DENYLIST_FIELDS = ("kong_wang", "liu_nian")` - liu_nian 字段被禁止 |
| profiles.py:95 | `_DENYLIST_MARKERS = {"【流年】", ...}` - 【流年】标记被禁止 |
| run_benchmark.py:458 | B1-a′ 走 `render_reasoned_context` |
| run_benchmark.py:162 | `_CODE_SCOPE` 必须扩展（v3 中优修正） |

6D v1 注入不能通过 `chart_input.liu_nian` 字段，也不能用 `【流年】` 标记。使用新标记：`【时间上下文·预计算】` / `【大运排布】` / `【目标流年详析】`。

## 5. 独立 6D 实验链设计（v3 P0 修正）

### 5.1 问题

6B2 orchestrator（phase6_6b2_orchestrator.py）硬编码 `b1a_prime + dual` 双臂（line 104），gate 计算 `dual_merged_acc`（line 684）。不能直接执行 single off/on paired 实验。

### 5.2 方案：新建 `scripts/phase6_6d_orchestrator.py`

6D v1 新建独立编排器，不复用 6B2 编排器的 schedule/ledger/merge/gate/report。

| 组件 | 6B2（不动） | 6D v1（新建） |
|---|---|---|
| orchestrator | `phase6_6b2_orchestrator.py` | `phase6_6d_orchestrator.py` |
| schedule | `b1a_prime + dual` × 3 repeat × 5 groups | `b1a_prime` single × off/on × N repeat × M groups |
| gate | `dual_merged_acc >= 0.325` | paired Δ gate（见 §8） |
| receipt | 6B2 RECEIPT_REQUIRED_FIELDS | 6D RECEIPT_REQUIRED_FIELDS（含 temporal 字段） |
| sealed | `phase6_6b2_sealed_workflow.py` | 不需要（6D 无 2023 密封阶段） |

### 5.3 6D schedule 冻结

| 维度 | 冻结值 |
|---|---|
| 臂 | `b1a_prime` only（no dual） |
| 条件 | `off`（time_context_injection=off） / `on`（time_context_injection=on） |
| 年份 | 2025（仅 2025，不用 2024；理由：2025 归因报告的退化域数据最完整） |
| 重复 | 3 次（与 6B2 一致，便于对照） |
| 每组 case | 8 |
| 分组 | 按 temporal 路由预声明分流（见 §7.3） |
| 总 slice | 2 条件 × 3 重复 × 5 组 = 30 slices |

### 5.4 6D gate 冻结

```
paired_delta = on_acc - off_acc   # 按 case × repeat 配对
verdict:
  PROMOTE    if paired_delta >= +0.05 and min_case_delta >= -0.10
  NON_INFERIOR if -0.02 <= paired_delta < +0.05
  ROLLBACK   if paired_delta < -0.02
```

- `paired_delta`：全量 temporal-routed 题的 on/off 准确率差
- `min_case_delta`：单 case 的最差 on/off 差（防止整体掩盖局部退化）
- 阈值在实验启动前冻结，不可事后调整

## 6. 注入点设计

### 6.1 注入路径

注入在 `render_reasoned_context` 返回值末尾追加，不修改 `chart_input` 渲染逻辑，不绕过 `DENYLIST_FIELDS`。`time_context_injection` 通过函数参数传入。

### 6.2 注入内容标记

新标记（不在 DENYLIST）：

| 标记 | 用途 |
|---|---|
| `【时间上下文·预计算】` | temporal context 段头 |
| `【大运排布】` | 大运表 |
| `【目标流年详析】` | 按目标年份的流年分析（仅 `ROUTED_WITH_TARGETS`） |

## 7. 可见性、Schema 与 Resume 隔离契约

### 7.1 新增字段（v3 中优修正：全部进 manifest/receipt/audit）

| 字段 | 类型 | manifest | run_context | receipt | audit |
|---|---|---|---|---|---|
| `temporal_context_version` | str | ✅ | ✅ | ✅ | ✅ |
| `time_context_injection` | `"on"`/`"off"` | ✅ | ✅ | ✅ | ✅ |
| `target_year_extraction_hash` | str | ✅ | ✅ | ✅ | ✅ |
| `temporal_route_state` | `ROUTED_WITH_TARGETS`/`ROUTED_WITHOUT_TARGETS`/`NOT_ROUTED` | ✅ | ✅ | ✅ | ✅ |

### 7.2 Resume 隔离规则

- `time_context_injection=on` 的 run 不能被 `off` resume
- `temporal_context_version` 不匹配时 fail-closed
- 检查点在 6D orchestrator 的 `_prepare_run_context`（新建，不修改 6B2 的）

### 7.3 可见性矩阵扩展

`profiles.py` 的 `visibility_requirements` 扩展：

- `time_context_injection=off`：temporal context markers 加入 deny 侧
- `time_context_injection=on`：temporal context markers 加入 required 侧（仅对 `ROUTED_WITH_TARGETS` / `ROUTED_WITHOUT_TARGETS` 题）

### 7.4 代码指纹扩展（v3 中优修正）

`run_benchmark.py:_CODE_SCOPE`（line 162）必须扩展，加入：

```python
"benchmark/formatters/bazi_time_context.py",  # 新模块
```

否则 `bazi_time_context.py` 的算法修改不产生 `code_sha256` 漂移，resume manifest 无法拒绝旧 run。

### 7.5 Receipt 契约（v3 P0 修正）

v2 的"不修改 sealed_workflow"与"字段进 receipt"自相矛盾。v3 修正：

- 6D v1 **不使用** `phase6_6b2_sealed_workflow.py` 的 `RECEIPT_REQUIRED_FIELDS` / `check_stage_gate`
- 6D v1 在 `phase6_6d_orchestrator.py` 新建 `6D_RECEIPT_REQUIRED_FIELDS`，含 6B2 的全部字段 + 4 个 temporal 字段
- 6D v1 在 `phase6_6d_orchestrator.py` 新建 `check_6d_gate`，做 field-level validation + temporal 字段跨阶段校验
- **`phase6_6b2_sealed_workflow.py` 不修改**（6B2 已归档，保持冻结）

## 8. 评估方案：两阶段

### 8.1 阶段一：零 API 离线门

不涉及准确率。验证工程契约：

| 检查项 | 验收口径 |
|---|---|
| 目标年份提取覆盖率 | 对 2025 全量 40 题，三态分类可审计 |
| 任意年份流年计算 | 1900-2100 确定性可复现（SHA 锁定） |
| 路由覆盖 | 三态分流边界明确 |
| 上下文序列化 | `TimeContext` canonical JSON + SHA 可复现 |
| 可见性矩阵 | on/off 下 marker 检查通过 |
| manifest 隔离 | on run 不能被 off resume（fail-closed） |
| prompt diff | on vs off 差异仅在 temporal context 段 |
| code_fingerprint | `bazi_time_context.py` 加入 `_CODE_SCOPE` 后产生漂移 |

### 8.2 阶段二：真实 paired dev

准确率评估。对预声明的全部 temporal-routed 题做真实 paired dev。

**冻结参数（v3 P0 修正）**：

| 参数 | 冻结值 |
|---|---|
| 年份 | 2025 |
| case 集 | 预声明 temporal-routed 全量（阶段一冻结） |
| 重复 | 3 次 |
| model | `deepseek-v4-flash` |
| thinking_mode | `disabled` |
| temperature | 0.0（与 6B2 一致） |
| 调度 | AB/BA 平衡：每 case 在 off/on 间交替首跑顺序，按 case_id hash 分配 |
| API 预算 | per-case hard_cap = 4（与 6B2 b1a_prime 一致） |
| parser | 现有 `direct_choice` parser |
| 完整性门 | 现有 `BAZI_COUNT` / `ZIWEI_COUNT` 门（与 6B2 一致） |
| run_id | 全新，不 resume 任何 6B2 run |

**判定阈值（v3 P0 修正）**：

| 判定 | 条件 | 含义 |
|---|---|---|
| PROMOTE | `paired_delta >= +0.05` 且 `min_case_delta >= -0.10` | 6D 注入有显著正向收益且无严重局部退化 |
| NON_INFERIOR | `-0.02 <= paired_delta < +0.05` | 6D 注入无害但也无显著收益，可保留 feature flag |
| ROLLBACK | `paired_delta < -0.02` | 6D 注入有害，关闭 feature flag |

阈值在实验启动前冻结，不可事后调整。

### 8.3 消融集设计

两层分离：

| 层 | 用途 | 选取 | 参与 gate |
|---|---|---|---|
| 全量预声明 temporal-routed 题 | 正式 paired gate | 阶段一离线门完成后预声明 | ✅ |
| rescue/regression 样本 | 诊断回放 | 从 6B2 归因报告选取 | ❌ |

预声明方式：阶段一输出 `temporal_routed_cases.json`（含 case_id + 三态 + 检测规则），在阶段二启动前冻结。

## 9. 隐性时间题检测规则

| 规则 | 检测方式 | 覆盖 domain | 缺目标年份时 |
|---|---|---|---|
| R1 显式时间关键词 | 现有 `_TIME_KEYWORDS` | annual_fortune | 视选项而定 |
| R2 选项为 4 位年份 | 现有 `year_pattern` | annual_fortune | N/A（必有年份） |
| R3 选项为年龄区间 | `\d+[-–]\d+` 且含"岁" | career / annual_fortune | 按 §3.5 转换为 mid_year |
| R4 题目含"大运/流年/岁运/年运" | 扩展关键词 | career | `ROUTED_WITHOUT_TARGETS` |
| R5 题目含"何时/哪年/几年后" + 选项含年份 | 关键词 + 选项年份混合 | annual_fortune | 按 §3.5 转换 |

R3-R5 为新增，每条独立单测。阶段一离线门输出每条规则在 2025 上的命中 case 列表 + 三态分类。

## 10. 抽离设计

### 10.1 新模块：`benchmark/formatters/bazi_time_context.py`

模块分层：

- **关系计算层**（从 two_stage_reasoning.py 迁移）：`compute_branch_relation` / `compute_gan_relation` / `compute_shishen_combo`
- **流年计算层**（新）：`calculate_liunian_for_year`
- **检测层**：`is_temporal_routed` / `detect_time_context` -> 返回三态
- **目标年份提取层**（新）：`extract_target_years` -> 返回 `(target_years_tuple, route_state, extraction_hash)`
- **计算层**：`build_natal_structure` / `build_dayun_table` / `build_target_liunian`
- **组装层**：`build_time_context` -> 返回 `TimeContext`

### 10.2 数据契约：`TimeContext`（v3 中优修正）

v2 用 `frozen dataclass` 含 `list`（非深度不可变）。v3 改为：

```python
@dataclass(frozen=True)
class TimeContext:
    natal: NatalStructure
    dayun_table: tuple[DayunRow, ...]      # tuple, not list
    option_liunian: tuple[OptionLiunian, ...]  # tuple, not list
    time_kind: TimeContextKind
    route_state: TemporalRouteState         # 三态
    target_years: tuple[int, ...]           # tuple
    extraction_hash: str

    def to_dict(self) -> dict: ...          # canonical JSON-serializable
    def canonical_json(self) -> str: ...    # sorted keys, no whitespace
    def sha256(self) -> str: ...            # sha256(canonical_json)
```

所有 `list` 字段改为 `tuple`。`to_dict()` / `canonical_json()` / `sha256()` 三个方法定义明确的序列化与哈希输入字段。

### 10.3 `chart_context.py` 改造

`render_reasoned_context` 末尾追加 temporal context 段（当 `time_context_injection == "on"` 且 route_state != NOT_ROUTED 时）。

## 11. 实施边界（v3 P0 修正）

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `benchmark/formatters/bazi_time_context.py` | 新建 | 关系计算 + 流年 + 检测 + 组装 |
| `benchmark/formatters/chart_context.py` | 改造 | `render_reasoned_context` 加 `time_context_injection` 参数 |
| `benchmark/formatters/two_stage_reasoning.py` | 重构 | 关系计算迁移到新模块（two-stage 路径本身不改） |
| `benchmark/runners/profiles.py` | 扩展 | visibility 矩阵加 temporal context markers |
| `benchmark/runners/run_benchmark.py` | 扩展 | `_CODE_SCOPE` 加 `bazi_time_context.py`；加 `--time-context-injection` flag |
| `scripts/phase6_6d_orchestrator.py` | **新建** | 6D 独立编排器：schedule / ledger / gate / receipt / report |
| `tests/test_bazi_time_context.py` | 新建 | 关系计算 + 流年 + 检测 + TimeContext 契约 |
| `tests/test_chart_context.py` | 新增 | 注入 on/off 行为测试 |
| `tests/test_phase6_6d_orchestrator.py` | 新建 | 6D schedule / gate / receipt / resume 隔离 |

**不修改**：
- `claude_api.py`（6B2 已冻结）
- `phase6_6b2_orchestrator.py`（6B2 已归档）
- `phase6_6b2_sealed_workflow.py`（6B2 已归档，`RECEIPT_REQUIRED_FIELDS` 保持冻结）
- `dual_system_reasoning.py`（6D 不用 dual）
- `bazi_calculator.py`（只读取已有函数）

## 12. 风险与回退

| 风险 | 缓解 |
|---|---|
| 隐性时间题检测过宽 | R3-R5 独立单测 + 2025 命中 case 审计 + 三态分类 |
| 历史流年计算与排盘不一致 | 算法冻结 + SHA 锁定 + 立春逻辑分离 |
| 注入内容过长 | 长度上限 + 截断策略 |
| 6D-on/off 误续跑 | resume 隔离 fail-closed |
| 6D orchestrator 与 6B2 冲突 | 独立文件，不共享 schedule/gate/receipt |
| `TimeContext` 不可变性 | tuple 字段 + canonical JSON + SHA |

回退：`--time-context-injection off`（默认），不修改 6B2 已归档证据。

## 13. 完成定义

6D v1 设计阶段的完成定义：

1. 本设计文档进入 Git（v3）
2. `bazi_time_context.py` 模块边界与 `TimeContext` 契约确认（tuple + to_dict + canonical_json + sha256）
3. 历史流年计算算法版本冻结（`temporal_context_version`）
4. 目标年份提取策略冻结 + hash 规则确认
5. 隐性时间题检测规则 R3-R5 的 2025 命中 case 列表 + 三态分类可审计
6. 可见性矩阵扩展方案确认（不绕过现有 DENYLIST）
7. resume 隔离规则确认（on/off 不可互续）
8. 两阶段评估方案确认（离线门 + 真实 paired dev）
9. 独立 6D orchestrator 的 schedule/gate/receipt/report 契约确认（v3 新增）
10. paired dev 冻结参数 + 判定阈值确认（v3 新增）
11. `_CODE_SCOPE` 扩展确认（v3 新增）
12. 4 个 temporal 字段进 manifest/receipt/audit 的跨阶段校验确认（v3 新增）

实施计划（Task 1-N）在本设计确认后单独编写。
