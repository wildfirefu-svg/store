# Phase 6 6D v1：八字命局 × 大运 × 流年确定性注入设计

**日期：** 2026-08-06
**状态：** 待确认，待实施计划
**适用范围：** Phase 6 6D v1 时间定位题的确定性上下文注入
**前置依赖：** 6B2 ROLLBACK 证据归档（commit `acb63a1`）

## 1. 背景与决策

### 1.1 6B2 ROLLBACK 的证据指向

6B2 双管线实验已 ROLLBACK。2025 零 API 错误归因（`docs/phase6/6b2/evidence/phase6-6b2-v4flash-nt-20260805-r2/2025_error_attribution.md`）显示按 domain 的净变化：

| domain | n | B1-a′ | dual | Δ | rescue | regression |
|---|---:|---:|---:|---:|---:|---:|
| annual_fortune | 6 | 16.67% | 0.00% | **-16.67%** | 0 | 1 |
| career | 27 | 29.63% | 22.22% | **-7.41%** | 2 | 4 |
| family | 12 | 16.67% | 41.67% | +25.00% | 3 | 0 |
| relationship | 21 | 14.29% | 33.33% | +19.05% | 4 | 0 |
| health | 9 | 22.22% | 22.22% | 0.00% | 1 | 1 |
| study | 3 | 33.33% | 100.00% | +66.67% | 2 | 0 |
| unknown | 42 | 28.57% | 30.95% | +2.38% | 5 | 4 |

关键观察：

1. **退化集中在时间定位域**：`annual_fortune` 和 `career` 是退化最严重的两个域，二者都强依赖"命局 × 大运 × 流年"的确定性时间上下文。
2. **rescue 集中在非时间域**：`family` / `relationship` 的大幅 rescue 来自双管线的紫微臂对人际关系的补充推断，与时间定位无关。
3. **信号高度集中**：净增益最高的 3 道题合计贡献全部 +7，不能视为稳定全局改进，因此 ROLLBACK 不会被局部收益推翻。
4. **根因假设**：时间定位题退化的主因是**确定性时间上下文不足**，而非可检测的事实矛盾。这使 6C（GroundedClaim Verifier）后置、6D（确定性时间注入）优先的排序成立。

### 1.2 决策

6D v1 只做"八字命局 × 大运 × 题目目标流年"的确定性注入，复用并抽离现有 `benchmark/formatters/two_stage_reasoning.py` 的计算能力；暂不加入动态紫微流年。这是成本最低、与 6B2 ROLLBACK 证据最匹配的方案。

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 将 `two_stage_reasoning.py` 中的命局/大运/流年计算抽离为独立可复用模块 | 新模块无 prompt 字符串依赖，可被 formatter 与未来 scorer 共同调用 |
| G2 | 对时间定位题注入"命局 × 大运 × 题目目标流年"的确定性上下文 | 注入内容 100% 来自预计算数据，不含模型生成的命理推断 |
| G3 | 注入范围从 `is_time=True` 扩展到含 `career`/`annual_fortune` 的隐性时间题 | 隐性时间题检测有明确规则且可单测 |
| G4 | 在 6B2 相同 2025 子集上做零 API 消融对照 | 6D v1 注入开/关的 paired 迁移表可复现 |

### 2.2 非目标（v1 显式排除）

- **不加入动态紫微流年**：紫微流年计算成本高、与 6B2 rescue 证据不匹配，后置到 6D v2。
- **不改 6B2 gate 或重开 reuse**：6B2 已 ROLLBACK，`protocol=single` 保持。
- **不引入新的模型调用预算**：6D v1 是确定性预计算注入，不增加 API 调用。
- **不做 6C GroundedClaim Verifier**：除非逐题复核证明主要错误来自事实主张自相矛盾，而非时间信息不足。

## 3. 6D v1 范围定义

### 3.1 注入内容契约

对每道被识别为时间相关题的 case，6D v1 注入以下**确定性**字段（全部来自 `chart_input` 预计算，不含模型推断）：

| 字段 | 来源 | 现有函数 |
|---|---|---|
| 命局四柱 + 日主 | `chart_input.four_pillars` / `day_master` | `_format_birth_line` |
| 原局刑冲合害 | `chart_input.branch_relations` | `_build_dayun_evidence` 内联 |
| 命局缺失十神 | `chart_input.shishen_stats.missing` | `_build_dayun_evidence` 内联 |
| 关键神煞 | `chart_input.shensha`（过滤 `_KEY_SHENSHA`） | `_build_dayun_evidence` 内联 |
| 大运排布 | `chart_input.da_yun` | `_build_dayun_summary_for_stage1` / `_build_dayun_evidence` |
| 题目目标流年详析 | `chart_input.liu_nian` 按选项年份匹配 | `_build_dayun_evidence` 的 option-driven 段 |
| 大运/流年与命局作用关系 | `_compute_branch_relation` / `_compute_gan_relation` | 已存在 |
| 十神组合效应 | `dy_shishen_gan + ln_shishen` 硬编码组合 | `_build_dayun_evidence` 内联 |

### 3.2 隐性时间题检测规则

当前 `is_time_location_question` 只检测显式时间关键词和"选项全为 4 位年份"。6D v1 扩展检测：

| 规则 | 检测方式 | 覆盖 domain |
|---|---|---|
| R1 显式时间关键词 | 现有 `_TIME_KEYWORDS` | annual_fortune |
| R2 选项为 4 位年份 | 现有 `year_pattern` | annual_fortune |
| R3 选项为年龄区间 | `\d+[-–]\d+` 且含"岁" | career / annual_fortune |
| R4 题目含"大运/流年/岁运/年运" | 扩展关键词 | career |
| R5 题目含"何时/哪年/几年后" + 选项含年份 | 关键词 + 选项年份混合 | annual_fortune |

R3-R5 为新增规则，每条必须有独立单测，且在 2025 子集上的命中 case 列表必须可审计。

### 3.3 与现有 `_build_dayun_evidence` 的差异

| 维度 | 现有 `_build_dayun_evidence` | 6D v1 |
|---|---|---|
| 触发条件 | `is_time_location_question=True` | 扩展后的隐性时间题检测 |
| 流年计算 | option-driven（只为匹配选项的年份算） | 保持 option-driven，但补全"选项未覆盖的目标流年" |
| 注入位置 | 仅 Stage 2 evidence | Stage 1 `time_phase` + Stage 2 evidence（双阶段一致） |
| 模块边界 | 内联在 formatter | 抽离为独立 `bazi_time_context` 模块 |

## 4. 现有能力审计

### 4.1 `two_stage_reasoning.py` 可复用部分

| 函数 | 行号 | 复用方式 |
|---|---|---|
| `_compute_branch_relation` | 367 | 直接迁移到新模块 |
| `_compute_gan_relation` | 438 | 直接迁移到新模块 |
| `_get_liunian_for_year` | 358 | 直接迁移到新模块 |
| `_get_question_type_hints` | 460 | 直接迁移到新模块 |
| `_build_dayun_evidence` | 565 | 拆分：计算部分迁移，prompt 拼接留在 formatter |
| `_build_dayun_summary_for_stage1` | 84 | 迁移到新模块 |
| `is_time_location_question` | 134 | 扩展后迁移到新模块 |
| `_TIME_KEYWORDS` | 14 | 扩展后迁移 |
| `_KEY_SHENSHA` | 497 | 直接迁移 |

### 4.2 不复用部分（留在 formatter）

| 函数 | 原因 |
|---|---|
| `format_stage1_prompt` / `format_stage2_prompt` | prompt 模板属于 formatter 层 |
| `parse_stage1_result` | 解析逻辑属于 formatter 层 |
| `_STAGE1_PROMPT_TEMPLATE` / `_STAGE2_PROMPT_TEMPLATE` | prompt 字符串 |
| `_build_nontime_structured_evidence` | 非时间题证据，6D v1 不改 |

## 5. 抽离设计

### 5.1 新模块：`benchmark/formatters/bazi_time_context.py`

```text
benchmark/formatters/bazi_time_context.py
  ├── 关系计算层（无状态）
  │   ├── compute_branch_relation(zhi1, zhi2) -> list[str]
  │   ├── compute_gan_relation(gan1, gan2) -> str
  │   └── get_liunian_for_year(chart, year) -> dict | None
  ├── 检测层
  │   ├── is_time_location_question(question, options) -> bool
  │   └── detect_time_context(question, options) -> TimeContextKind
  ├── 计算层（无 prompt 依赖）
  │   ├── build_natal_structure(chart) -> NatalStructure
  │   ├── build_dayun_table(chart) -> list[DayunRow]
  │   ├── build_target_liunian(chart, options, birth_year) -> list[OptionLiunian]
  │   └── build_shishen_combo(dy_shishen, ln_shishen) -> str | None
  └── 组装层
      └── build_time_context(case) -> TimeContext
```

### 5.2 `two_stage_reasoning.py` 的改造

`_build_dayun_evidence` 改为调用 `bazi_time_context.build_time_context(case)`，再格式化为 prompt 字符串。改造后：

- 计算逻辑零重复
- formatter 只负责"TimeContext -> prompt 字符串"
- 未来 scorer 可直接调用 `build_time_context` 做特征提取

### 5.3 数据契约：`TimeContext`

```python
@dataclass(frozen=True)
class TimeContext:
    natal: NatalStructure          # 四柱、日主、缺失十神、刑冲合害、神煞
    dayun_table: list[DayunRow]    # 大运排布
    option_liunian: list[OptionLiunian]  # 每选项的流年详析
    time_kind: TimeContextKind     # 显式/隐性时间题子类
```

所有字段为纯数据，不含 prompt 字符串，可被 JSON 序列化（便于测试与审计）。

## 6. 确定性注入契约

### 6.1 确定性保证

| 维度 | 保证 |
|---|---|
| 数据来源 | 100% 来自 `chart_input` 预计算字段 |
| 模型推断 | 不含任何模型生成的命理推断 |
| 关系计算 | `_compute_branch_relation` / `_compute_gan_relation` 为纯函数 |
| 顺序无关 | 选项顺序不影响注入内容（除"选项对应流年"段按选项顺序） |
| 可复现 | 相同 `chart_input` 必须产生相同 `TimeContext`（含 byte 级 SHA） |

### 6.2 注入位置

| 阶段 | 注入内容 | 现状 |
|---|---|---|
| Stage 1 | `time_phase` 指令 + 大运排布摘要 | 已有 `_build_dayun_summary_for_stage1`，6D v1 复用 |
| Stage 2 | `evidence` 段含完整 `TimeContext` | 已有 `_build_dayun_evidence`，6D v1 扩展 |

### 6.3 不注入的内容

- 不注入紫微流年（6D v2）
- 不注入模型生成的命理推断
- 不注入选项文本本身（选项文本仍由现有 `mode="all"` 路径处理）

## 7. 评估方案

### 7.1 零 API 消融对照

在 6B2 相同 2025 子集上，使用归档的 `merged_details.jsonl` 做**零 API**的 paired 对照：

| 配置 | 说明 |
|---|---|
| baseline | 6B2 B1-a′（无 6D 注入） |
| 6D-off | dual 且 6D v1 注入关闭 |
| 6D-on | dual 且 6D v1 注入开启 |

对照口径：

- `annual_fortune` / `career` 域的 Δ 是否从负转正
- rescue/regression 的 case 级迁移是否与"时间上下文缺口"假设一致
- 不调用模型，不改变 6B2 gate

### 7.2 最小消融集

按 2025 归因报告的 case 分布，6D v1 的最小消融集为：

| 子集 | case 数 | 选取依据 |
|---|---|---|
| annual_fortune 全部 | 6 | 退化最严重 |
| career 退化 case | 4（regression） | 验证是否因时间上下文不足 |
| career rescue case | 2 | 验证是否与时间上下文无关 |
| family rescue case | 3 | 对照组（不应受 6D 影响） |

合计 15 个 case × 3 重复 = 45 个配对单元。6D v1 评估必须覆盖此消融集。

### 7.3 不做的事

- 不重开 6B2 reuse
- 不改 6B2 gate 阈值（`dual_merged_acc >= 0.325` 保持）
- 不启动新的真实 API 实验（6D v1 评估为零 API 消融）

## 8. 非目标与后置项

### 8.1 6C GroundedClaim Verifier（后置）

6C 后置到 6D v1 评估完成之后。启动条件：

- 6D v1 评估显示 `annual_fortune` / `career` 退化未因确定性注入而改善
- **且**逐题复核证明主要错误来自事实主张自相矛盾（而非时间信息不足）

若 6D v1 评估显示确定性注入改善了退化，则 6C 进一步后置。

### 8.2 6D v2 动态紫微流年（后置）

6D v2 扩展为含动态紫微流年。启动条件：

- 6D v1 评估显示确定性八字注入有正向收益
- **且** `family` / `relationship` 的 rescue 信号在排除紫微臂后消失（证明紫微流年有独立贡献）

## 9. 风险与回退

### 9.1 风险

| 风险 | 缓解 |
|---|---|
| 隐性时间题检测过宽，误注入非时间题 | R3-R5 每条规则独立单测 + 2025 命中 case 列表审计 |
| 抽离破坏现有 `_build_dayun_evidence` 行为 | 抽离前后对相同 `chart_input` 做 SHA 对比 |
| 注入内容过长导致 prompt 超限 | 注入内容长度上限 + 截断策略（保留大运排布，截断流年详析） |

### 9.2 回退

- 6D v1 通过 feature flag 控制（`--time-context-injection {on,off}`）
- 回退到 6B2 baseline 只需关闭 flag
- 不修改 6B2 的任何已归档证据

## 10. 实施边界

| 文件 | 改动类型 |
|---|---|
| `benchmark/formatters/bazi_time_context.py` | 新建 |
| `benchmark/formatters/two_stage_reasoning.py` | 重构：`_build_dayun_evidence` 改为调用新模块 |
| `tests/test_bazi_time_context.py` | 新建：关系计算 + 检测 + TimeContext 契约测试 |
| `tests/test_two_stage_reasoning.py` | 新增：抽离前后行为等价测试 |
| `benchmark/runners/run_benchmark.py` | 仅加 `--time-context-injection` flag（默认 off） |

不修改：`claude_api.py` / `phase6_6b2_orchestrator.py` / `phase6_6b2_sealed_workflow.py` / `dual_system_reasoning.py`。

## 11. 完成定义

6D v1 设计阶段的完成定义：

1. 本设计文档进入 Git
2. `bazi_time_context.py` 模块边界与数据契约（`TimeContext` 等 dataclass）确认
3. 隐性时间题检测规则 R3-R5 的 2025 命中 case 列表可审计
4. 抽离前后行为等价测试策略确认

实施计划（Task 1-N）在本设计确认后单独编写。
