# Phase 6 判断分析与命理推理准确率提升设计 v6（上下文先行 · 严格投票基线 · 双体系条件触发）

**日期**：2026-07-17（v6）
**状态**：v1 = NEEDS_MAJOR_REVISION → v2 = NEEDS_MAJOR_REVISION → v3 = NEEDS_REVISION → v4 = NEEDS_REVISION（3 阻塞 + 5 中低）→ v5 = NEEDS_REVISION（3 执行级阻塞 + 2 同步修正）→ **v6 = APPROVED（2026-07-17 第五轮评审：修正落实并经评审确认后批准，可进入 writing-plans）**
**范围**：BaziQA/MingLi 评测准确率提升 —— 已批准字段的完整上下文、严格投票基线、Ziwei 信号消融、（条件触发）双管线裁决

## 0. 修订记录

- **v1 → v2**：执行顺序重构（6A0 地基 / 6A1 投票 / 6B1 探针 / 6B2 条件实施；6C、6D 移出独立成文）。
- **v2 → v3**：严格投票语义、同源配对、双分支预算、本命紫微限定、MingLi 可见性验证、已批准字段 schema、复用验证集改名、统一 `reasoned_choice`、2023 判定规则、设施硬化、Tianfu 断言降级为待验证假设。
- **v3 → v4**：attempt key 扩字段、预算含配对基线重算、profile 加 multi-turn 维度、Δ 聚合公式冻结、2023 三态判定、阻塞规则修正、seed 表述如实化、`source_label_blinded_judge` 改名、provider 漂移限制声明。
- **v4 → v5**：temp-0 同期锚定臂与 PROMOTE 双条件、重试账本与终态集合、6A1 复核预注册仅 2021、per-profile 可见性矩阵、AB/BA 与 Latin square、泄漏扫描分级。
- **v5 → v6**（本轮，3 执行级阻塞 + 2 同步修正，批准后定稿）：

| # | 评审意见 | v6 处理 |
| --- | --- | --- |
| 阻 1 | 重试策略与硬预算冲突：各阶段硬顶恰等于正常调用数，任何重试即破顶 | §4.4.2 与 §8 改**双列预算**：`scheduled_calls`（无重试正常调用数）与 `hard_cap = scheduled + retry_reserve`（储备 = scheduled 的 10%，向上取整到 10 的倍数）；重试仅从储备支出；hard_cap 耗尽且存在非终态 attempt → `BLOCKED_INCOMPLETE`，不得进入任何 gate 决策，追加预算须显式登记。6B2 dev 行值由 1000/3900 修正为 scheduled 960/3840 + hard_cap 1060/4230（显式储备替代隐式余量） |
| 阻 2 | 非同时段 B1-c 承担因果性硬门槛，与 provider drift 声明冲突 | §7.3 重写：B1-c **降为 advisory**（描述性 Δ + 非同时段/provider drift 标注；描述性 Δ < 0 时如实陈述"双管线编排成本可能无增量"）；dev gate 只依赖同期 B1-a′：`Δ_dev ≥ +4pp` + **绝对准确率门槛**（dual 合并 ≥ 32.5% = 真实基线 27.5% + 5pp）+ 年度护栏；删除 B1-c 强制重跑 |
| 阻 3 | 可见字段门禁误杀 legacy 旧上下文对照臂 | §4.3 可见性矩阵改按 `(profile_id, chart_schema_version)` 二元组决定 required/forbidden fields；`legacy_v0` 对照臂用自身旧 schema 断言，approved 专有字段列为 forbidden（串扰检测） |
| 另 1 | 泄漏扫描"答案文本进入 prompt 即失败"过宽：正常选项块必含正确选项文本 | §4.2.4 硬失败收窄为：答案标签/答案键元数据、正常选项块之外额外暴露正确选项、历史评测结果/赛事排名；明确豁免正常 A/B/C/D 选项块 |
| 另 2 | 最终审核完成前自标 APPROVED | 状态流转纪律：修正落实并经评审确认后方标 APPROVED；checklist 同步修正 |

## 1. 背景与决策依据

### 1.1 外部证据（2026-07-17 调研）

**已验证事实（有论文/官方数据支撑）：**

- BaziQA 论文（arXiv:2602.12889）：最强模型 36.7–38.0%，远低于饱和；时间组合与精确时间定位为系统性失败点；结构化协议效果异质；模型间一致率低；R1 类推理模型不优于对话版。论文方法学要点：**注入外部排盘程序生成的完整、固定格式命盘上下文**，并以 **multi-turn**（同一命主 5 题同会话）为主评测协议。
- MingLi-Bench 公开榜单：Tianfu Agent 截尾准确率 50%，最佳通用基线 40%，人类 Top-20 均值 53.5%。

**待验证假设（厂商材料与二手报道，未经一手验证，仅作为形成探针的假设来源）：**

- Tianfu"八字+紫微双体系独立推演取共识"的架构描述及其归因；"5 轮 ≥3/5 投票 + 截尾均值"为其标准协议的说法。
- 多智能体辩论、Self-Consistency 等通用结论在本领域的可迁移性。

v6 的实验设计不依赖上述假设为真：6A1/6B1 即为以最低成本在本仓库数据上自行检验这些假设的探针。

### 1.2 本仓库现状（经评审核实的关键事实）

- **真实默认基线：direct_choice，temp 0**，2024 holdout 11/40 = 27.5%（deepseek-chat，RAG/few-shot/APB/C2 全关）。一切"PROMOTE"结论必须相对该基线成立。
- Phase 5 C2 已 ROLLBACK；**2021/2022 已被 Phase 5 打开，仅为复用验证集；2023 是唯一最终独立集。**
- `self_consistency.majority_vote()` 为宽松多数（破平局），不符合严格协议，不可复用。
- `run_benchmark.py:276` 每次启动截断 detail JSONL；runner 已有 multi-turn 实现（`run_benchmark.py:811`）。
- `calculate_ziwei()` 仅有本命宫位、宫位大限年龄段与本命 `si_hua`；无动态四化与流年宫位。
- `format_to_spec()` 含 `kong_wang=False` 占位（:1982）与按运行日期生成的 `liu_nian`（:2138）。
- `baziqa_prompt.py:17` 只读 `chart_input.four_pillars`——MingLi 归一化字段 join 成功不等于模型可见命盘。
- **`data/mingli/` 当前不存在**，MingLi profile 需先完成数据获取前置。
- `claude_api.py:145,166` 的请求未传 seed，API 也不返回 `system_fingerprint`：采样不可由 seed 复现，provider 后端漂移不可由 manifest 排除。

### 1.3 决策原则

1. 地基先行：上下文字段以"已批准 schema"为准；模型看不到的东西不可能被用于推理。
2. 每次只改一个变量；配对样本同源；协议语义（投票、裁决、失败处理、Δ 聚合、重试）在设计期预注册。
3. **一切 PROMOTE 必须同时优于同温度对照与 temp-0 真实基线**，禁止"胜过采样噪声却输给默认基线"的假性提升。
4. 高成本结构必须先有低成本信号；信号不存在即止损。
5. 预算按协议分支与完整配对成本（含基线臂、锚定臂）估算，并**区分 `scheduled_calls` 与含重试储备的 `hard_cap`**；基础设施失败才阻塞，增强臂失败回退到上一稳定基线继续。
6. 复用验证年份只作复核，复核范围预注册、杜绝选择性验证；最终结论以 2023 为准，负增益不包装为成功。

## 2. 目标与非目标

### 2.1 目标

1. 6A0：已批准字段的完整八字上下文、五维评测 profile（含四个命名配置）、可安全续跑的评测设施。
2. 6A1：以同源配对 + temp-0 锚定实验判定严格 ≥3/5 投票是否成为默认评测协议。
3. 6B1：以最低成本判定本命紫微上下文对 BaziQA 赛题是否存在可利用信号。
4. 6B2（条件触发）：仅当 6B1 有信号时实现双管线 + source_label_blinded_judge，并证明其优于同期单管线基线与绝对准确率门槛。
5. 报告口径：BaziQA 以 macro-average by year + by_domain 为首类指标，trimmed mean 为辅助；MingLi 以 trimmed mean 为主指标。

### 2.2 非目标

- 不实现 claim verifier（6C）与时间组合预计算（6D）；**目标年份时间上下文归 6D 所有**，本设计不注入任何当前日期流年。
- 不实现动态紫微计算（大限/流年四化、流年宫位）；6B 全部使用本命紫微上下文。
- 不修改 C2 规则、受保护的原始 JSONL；不宣称跨 prompt_style 的分数可直接横向比较。
- 不接入线上生产；不做领域微调；不引入奇门遁甲。
- 不用 2021–2023 结果反向调任何权重/prompt/温度；2023 密封且只使用一次。
- 不把 40 题样本上 1–2 题的波动表述为显著提升。

## 3. 数据角色与隔离

### 3.1 BaziQA 数据

| 年度 | 角色 | 允许用途 |
| --- | --- | --- |
| 2024/2025 | 开发与错误分析集 | 各臂 dev gate、配对消融 |
| 2021/2022 | 复用验证集（Phase 5 已打开，证据强度降级） | 各臂**预注册范围**的复核 gate，不复用于校准 |
| 2023 | 唯一最终独立集 | 全部臂选定后的一次终验 |

沿用 Phase 5 的 enrichment、manifest、seal、哈希、续跑纪律，并新增：

- **as_of_date 冻结**：enrichment 与 manifest 记录固定 `as_of_date`；日期相关派生字段以此为准。
- **已批准字段 schema**：上下文覆盖率以"已批准字段 schema 100%"校验（见 §4.2）。
- 旧上下文与已批准上下文两版 enriched 文件各自 SHA-256 入 manifest；配对实验共用同一文件与 manifest 条目。
- run 目录 `.tmp/phase6/<arm>/runs/<run_id>/`；跨阶段 run 复用仅当模型、参数、数据、代码哈希完全一致。

### 3.2 MingLi 数据获取前置

`data/mingli/` 当前不存在，MingLi profile 的一切 gate 之前必须完成：

1. 来源：`https://github.com/DestinyLinker/MingLi-Bench`（README 声明 MIT），固定到具体 commit/tag 并记录。
2. 获取 `data/data.json` 与 `data/fortune_api_results.json`，计算 SHA-256 入 manifest；记录获取日期、许可证与文件清单。
3. 数据放入 `data/mingli/` 后视为只读外部数据；归一化产物写入 `.tmp/phase6/mingli/`。
4. **前置未完成时，MingLi 相关 gate 记 BLOCKED 并说明，不阻塞 BaziQA 各臂推进。**

## 4. 阶段 6A0：已批准上下文、五维 profile、设施硬化

### 4.1 目标

消除"模型可见上下文不完整/不确定"变量；建立 BaziQA 与 MingLi 的同构评测 profile；让高成本实验可安全续跑。

### 4.2 已批准八字上下文字段 schema

1. **字段批准清单**（设计期冻结）：四柱干支、藏干、十神（干/支）、纳音、五行统计、十神统计、刑冲合害关系、神煞（批准子集）、大运表（起运岁 + 各运干支）、胎元/命宫/身宫、真太阳时校正说明。
2. **denylist**：`kong_wang` 占位字段、按运行日期生成的 `liu_nian`、任何未经快照验证的派生字段。空亡修正计算器并快照验证前不纳入，记为已知缺口。
3. **固定文本模板** `CHART_CONTEXT_TEMPLATE`：同一命主 + 同一 `as_of_date` 跨 run 逐字节一致；模板版本哈希入 manifest。
4. **防泄漏扫描（分级）**：
   - **硬失败**：答案标签或答案键元数据（答案字母映射、"correct"/"answer" 标注等）进入 prompt；在正常 A/B/C/D 选项块**之外**额外暴露正确选项（如解析、高亮、"已知答案"字段）；历史评测结果/赛事排名信息进入 prompt——任一命中即 gate 失败。
   - **明确豁免**：正常 A/B/C/D 选项块本身必然包含正确选项的文本，不构成泄漏。
   - **身份字段**（姓名、出生日期、地点）：属输入协议声明项，不构成扫描失败。BaziQA 使用匿名化 subject ID（对齐论文协议）；MingLi 按官方输入协议。身份处理策略须在 manifest 中声明。
5. **配对消融**：旧上下文 direct（`chart_schema_version=legacy_v0`）vs 已批准上下文 direct（`approved_v1`），同数据集、同 provider；**两臂按 AB/BA 平衡**：题目固定分两组，一组 A 臂先跑、另一组 B 臂先跑，分组与顺序入 manifest。报告附 token 量与成本对比。

### 4.3 五维评测 profile 与四个命名配置

profile 由五维组成（设计期冻结维度，实施期落地）：

```text
dataset            = baziqa | mingli
prompt_style       = official | xjz_direct
interaction_mode   = direct | multi_turn
chart_schema_version  = legacy_v0 | approved_v1（后续版本递增）
scoring_profile
```

四个命名配置：

| 配置名 | 维度组合 | 用途 |
| --- | --- | --- |
| `baziqa_official_multi_turn` | baziqa × official × multi_turn | 对齐论文主协议的外部可比口径 |
| `baziqa_xjz_direct` | baziqa × xjz_direct × direct | **Phase 6 实验默认口径** |
| `mingli_official_cot_astro` | mingli × official(CoT) × direct + astro 注入 | 对齐 MingLi 官方推荐口径 |
| `mingli_xjz_direct` | mingli × xjz_direct × direct + astro 注入 | 跨基准描述性对照 |

- multi_turn 复用 runner 现有实现（`run_benchmark.py:811`）：同一命主 5 题同会话顺序作答。
- **不宣称不同 prompt_style 之间分数可直接横向比较**；跨基准陈述仅作描述性并列。
- **可见性验证（按 `(profile_id, chart_schema_version)` 二元组的 required/forbidden 矩阵）**：

| (profile, chart_schema_version) | required fields（渲染后断言） | forbidden fields |
| --- | --- | --- |
| `baziqa_* × approved_v1` | §4.2 已批准八字字段清单全部出现 | denylist 字段（`kong_wang` 占位、日期相关 `liu_nian`） |
| `baziqa_* × legacy_v0`（6A0 旧上下文对照臂） | 旧 schema 自身字段（现有 four_pillars 渲染字段） | `approved_v1` 专有字段（出现即上下文串扰） |
| `mingli_* × approved_v1`（astro 注入） | 八字字段 + 紫微宫位名 | denylist 字段 |
| 未来 no-astro 配置 | 按其声明 schema 单独定义 | 按其声明 |

  字段约束由 `(profile_id, chart_schema_version)` 二元组唯一决定：6A0 旧上下文对照臂使用 `legacy_v0` 断言，**不会被 approved 字段门禁误杀**；实验臂使用 `approved_v1`。四层验证不变：归一化 schema 转换单测；逐题 `rendered_chart_context` 非空；按上表的 required/forbidden 断言；prompt 快照 golden test。

### 4.4 评测设施硬化（resume-safe）

1. **attempt key（10 字段，设计期冻结）**：

```text
(dataset_id, profile_id, arm, attempt_stage, provider, model,
 case_id, repeat_idx, sample_idx, permutation_id)
```

   - `case_id` 即 BaziQA 题目 ID（数据集无独立 question_id 字段）。
   - `attempt_stage ∈ {main, bazi, ziwei, judge, diversity_probe, anchor}`：双管线两臂、judge、多样性试测、temp-0 锚定臂各有独立 stage；单管线臂用 `main`。
   - `permutation_id` 为选项/顺序排列标识，默认 `p0`。
   - temperature、prompt 哈希、代码与数据哈希**不入键**，由 resume manifest 约束；不一致即拒绝续跑。
2. **终态与重试账本（预注册）**：
   - 一次**逻辑 attempt** 由 attempt key 唯一标识；每次网络尝试记 `retry_event(retry_idx, error_type, timestamp)` 写入**独立 event log**，不产生新的逻辑键。
   - 每个逻辑 attempt **跨 run 与跨 resume 累计最多 3 次网络尝试**；resume 从已记录的 retry 次数继续，**不重置额度**。
   - 终态集合：`parsed` / `invalid`（解析失败）/ `unresolved`（严格投票）/ `judge_unresolved` / `call_failed`（网络尝试耗尽）。全部为终态完成键；`call_failed` **按错误计入统计分母**。
   - 网络失败/超时/限流不是终态，仅生成 retry_event。
   - **双列预算约束**：每阶段预注册 `scheduled_calls`（无重试正常调用数）与 `hard_cap = scheduled_calls + retry_reserve`（reserve = scheduled 的 10%，向上取整到 10 的倍数，数值见 §8）。**重试仅在阶段累计调用尝试次数 < hard_cap 时允许；达到 hard_cap 即停止一切新重试。**
   - **`BLOCKED_INCOMPLETE`**：hard_cap 耗尽且仍有逻辑 attempt 无终态时，该 run/阶段判 `BLOCKED_INCOMPLETE`——**不得进入任何 gate 决策**；已落盘数据保留供诊断；排查故障源后续跑，追加预算须显式登记入 manifest，不得静默突破原 hard_cap。
3. **append/resume 语义**：detail JSONL 追加写，禁止任何启动路径截断（修复 `run_benchmark.py:276`）；`--resume` 跳过已完成键。
4. **复现性的如实声明**：请求不携带 seed（`claude_api.py:145,166`），**不宣称采样可由 seed 复现**；复现依赖——每次调用的原始响应按 attempt key 持久化，支持结果重放与审计；manifest 记录调用顺序。
5. 单元测试：中断-续跑后 detail 键集合与一次性运行完全一致；10 字段键在双管线 + judge + 试测 + 锚定混合场景无碰撞；重试账本跨 resume 不重置；hard_cap 耗尽触发 `BLOCKED_INCOMPLETE` 且该 run 不计入决策。

### 4.5 落点

- `scripts/enrich_holdout_chart_input.py`：已批准上下文字段 + `as_of_date`。
- `benchmark/formatters/`：`CHART_CONTEXT_TEMPLATE` 渲染与快照测试。
- `benchmark/runners/run_benchmark.py`：五维 profile、append/resume、attempt key、重试账本与双列预算。
- `benchmark/reports/generate_report.py`：trimmed mean（MingLi 主指标、BaziQA 辅助）。
- 测试：模板快照、泄漏分级扫描、MingLi 可见性四层、续跑一致性、键碰撞、重试账本与 BLOCKED_INCOMPLETE。

### 4.6 验证与 gate

- **离线 gate**：已批准字段 schema 渲染覆盖率 100%；模板逐字节稳定；泄漏扫描硬失败 0 命中；MingLi 前置 + 四层可见性全过（前置缺失记 BLOCKED）；续跑一致性、键碰撞、重试账本测试通过。
- **dev gate（2024，40 题 × 3 repeats，AB/BA 平衡配对）**：Δ = 已批准上下文 − 旧上下文：
  - `Δ ≥ +2pp` → 采用为默认；
  - `0 ≤ Δ < +2pp` → 默认采用（地基性质，非准确率承诺），报告中标注；
  - `Δ < 0` → 回退并记录，**6A1 沿用旧上下文继续**。
- **预算**：scheduled 260；hard_cap 290（含 10% 重试储备，定义与数值见 §8）。

## 5. 阶段 6A1：严格 ≥3/5 投票的同源配对基线（含 temp-0 锚定）

### 5.1 目标

以单变量、同源样本的配对设计，判定严格多数投票是否提升本仓库**真实默认基线（single@T=0）**。

### 5.2 预注册的严格投票协议

1. **采样**：每题在同一温度 T 下采样 5 次。**T 冻结为 0.4**（仓库现有默认）。
   - *决策记录*：备选方案"全部 T=0 采样（无多样性即证明 vote5 无增量）"未采用——锚定臂方案以 +240 次调用的成本保留温度多样性可能带来的聚合收益，同时消除"胜过采样噪声却输给基线"的假性 PROMOTE 风险。
2. **多样性试测（预注册应急，stage=`diversity_probe`）**：正式运行前对 2024 的 10 题试采样 5 次（不查看答案）；若 < 60% 题目产生 ≥2 个不同选项，则 T 切换为 1.0 并写入 manifest，其后全部运行冻结该值；试测样本作废。
3. **锚定臂（stage=`anchor`）**：与采样臂**同时间窗**运行 `single@T=0`（每题 1 次 × 3 repeats），作为真实默认基线的同期测量。
4. **严格聚合** `strict_majority()`（新增，不复用 `majority_vote()`）：≥3 票当选；无 3 票 → `unresolved` 按错误计入分母；invalid/解析失败仍占一次 attempt，分母恒为 5；**禁止任何形式的破平局**。
5. **同源配对**：`single@T` 臂 = 同组 5 次采样的第 1 次；`vote5@T` 臂 = 同 5 次严格聚合；`single@0` 锚定 = 独立同期调用。manifest 记录调用顺序与原始响应持久化路径（不宣称 seed 复现）。
6. **repeats 聚合**：vote5 仅在 repeat 内部聚合；报告每 repeat 准确率、三轮均值与逐题明细；**禁止跨 repeat 把 15 次样本再投票伪装成一个 repeat**。
7. **首类指标**：准确率、unresolved 率、配对四格表（vote5 vs single@T、vote5 vs single@0）、成本比（trimmed mean 按 §2.1 口径附列）。

### 5.3 验证与 gate

- **离线 gate**：`strict_majority()` 单测覆盖 3/1/1、2/2/1、2/1/1/1、含 invalid 计分母；聚合不跨 repeat。
- **dev gate（2024，40 题 × 3 repeats）**，Δ1 = `vote5@T − single@T`（同源），Δ2 = `vote5@T − single@0`（锚定）：
  - `Δ1 ≥ +3pp` **且** `Δ2 ≥ 0` → **PROMOTE 候选**：vote5 成为后续臂默认协议，**经预注册复核后确认**（见下）；
  - `Δ1 ≥ +3pp` **且** `Δ2 < 0` → **AGGREGATION_EFFECT_ONLY**：聚合能救回采样噪声但不优于 temp-0 基线，不设为默认，结论如实记录；
  - `-3pp < Δ1 < +3pp` → **NON_INFERIOR**，保持 single@0 默认，6B1 以 protocol=single 继续；
  - `Δ1 ≤ -3pp` → **ROLLBACK**，保持 single@0 默认，6B1 以 protocol=single 继续。
- **复核（预注册，仅 2021）**：2021 单年度运行同协议实验，`Δ1_year ≥ +2pp` 且 `Δ2_year ≥ 0` 方确认 PROMOTE。**2022 不参与 6A1 阶段**（保留给 6B2 的双年度复核），杜绝"看完 2021 再决定是否打开 2022"的选择性验证。
- unresolved 率 > 20% 作为显著发现写入报告，不直接否决。
- **预算**：scheduled 820（试测 100 + 采样 600 + 锚定 120）；hard_cap 910。PROMOTE 时 2021 复核 scheduled 720 / hard_cap 800（见 §8）。

## 6. 阶段 6B1：本命紫微上下文信号消融（探针）

### 6.1 目标

在投入双管线编排成本之前回答：**本命紫微上下文对 BaziQA 赛题是否存在可利用信号？**

### 6.2 方案

1. **统一 `reasoned_choice` 输出协议**：简短理由 + 固定格式最终答案行。6B 全部臂共用（含基线 B1-a′），保证 B1-c 与 6B2 之间无输出格式变量。
2. **本命紫微上下文**（已批准范围）：命宫/身宫、十二宫主星与亮度、本命 `si_hua`、宫位大限年龄段；固定模板 + 2–3 个已知命盘快照测试。**不注入动态四化与流年宫位**；该缺口对时间类题目的影响作为已知限制声明。
3. 三臂配对（同一 `reasoned_choice`、同一选定采样协议）：

| 臂 | 上下文 | 说明 |
| --- | --- | --- |
| B1-a′ | 已批准八字上下文（reasoned） | 新基线；letter-only 旧 run 不可复用 |
| B1-b | 仅本命紫微（不含四柱） | **诊断臂**，不入推进 gate |
| B1-c | 八字 + 本命紫微拼接 | 信号判定臂 |

4. **臂顺序**：三臂按**固定 Latin square** 轮换（题目分 3 组，组间轮换臂执行顺序），顺序配置入 manifest。

### 6.3 Δ 聚合公式（设计期冻结，适用于 6B1/6B2/复用验证/2023）

```text
Δ(year, repeat) = accuracy_treatment(year, repeat) - accuracy_control(year, repeat)
Δ_year        = mean over 3 repeats of Δ(year, repeat)
Δ_dev         = mean(Δ_2024, Δ_2025)
```

### 6.4 验证与 gate

- **离线 gate**：已批准本命紫微字段 schema 覆盖率 100%；模板快照稳定；`reasoned_choice` 解析 smoke ≥ 95%。
- **dev gate（2024/2025，各 40 题 × 3 repeats）**，推进判定**仅看** B1-c 相对 B1-a′：
  - `Δ_dev ≥ +2pp` **且** `min(Δ_2024, Δ_2025) ≥ -2pp` → **有信号，进入 6B2**；
  - 否则 → **Ziwei 路线止损**，写 ROLLBACK 报告（含域分析），6B2 预算回收。
- B1-b 仅作诊断报告（整体与 by_domain 准确率，不做显著性断言）；B1-a′ 与 6A1 基线的差异作为"letter-only → reasoned 格式漂移"诊断记录，不作 gate。
- **预算**：scheduled single 720 / vote5 3600；hard_cap 800 / 3960。

## 7. 阶段 6B2：双管线 + source_label_blinded_judge（仅 6B1 有信号时实施）

### 7.1 预注册的裁决语义

1. **先解析后裁决**：每条管线先按 6A1 选定协议解析出单一答案；**judge 仅在两管线答案分歧时调用，每题每 repeat 一次**。
2. **judge 命名与盲法边界**：命名为 `source_label_blinded_judge`——仅隐藏**来源标签**（"分析一/分析二"，顺序按固定顺序种子交换，模板不得出现"八字/紫微"字样）；**如实声明：理由文本中的宫位/十神等术语可能暴露体系来源，本设计不声称完全盲法**。
3. **judge 输入**：两管线最终选项 + 理由；vote5 下理由取多数侧首个样本（预注册）。
4. **管线 unresolved**：单侧 unresolved → 该侧以"未达成结论 + 首个样本理由"进入 judge；双侧 unresolved → 本题记 unresolved（计错），不调 judge。
5. **judge 解析失败**：记 unresolved（计错）入主指标；"回退八字臂"仅作敏感性分析附列。

### 7.2 落点

- `benchmark/formatters/dual_system_reasoning.py`（双管线编排 + judge）。
- `benchmark/runners/run_benchmark.py`：`--method dual_system`。
- `tests/test_dual_system_reasoning.py`：共识直取、分歧裁决、顺序交换、双侧 unresolved、judge 解析失败计错、attempt key 分 stage 无碰撞。

### 7.3 同期控制与 gate

- **同期控制（预注册）**：6B2 dev **必跑 contemporaneous B1-a′ 控制臂**作为主对照（不依赖 6B1 时段的旧 run）。
- **B1-c 比较降为 advisory**：B1-c 使用 6B1 时段的旧 run，**不承担任何硬门槛**——provider 后端无可验证指纹（§12.5），跨时段比较不能支撑因果性晋级条件。报告中并列展示 dual vs B1-c 的描述性 Δ_dev，显式标注"非同时段比较 + provider drift 风险"；若描述性 Δ < 0，报告须如实陈述"双管线编排成本可能无增量"，供人工决策参考，但不构成预注册 gate。
- **dev gate（2024/2025）**：同时满足——
  1. `Δ_dev(dual vs 同期 B1-a′) ≥ +4pp`；
  2. **绝对准确率门槛**：dual 臂 2024/2025 合并准确率 ≥ 32.5%（= 真实基线 27.5% + 5pp，设计期冻结；防止基线臂异常塌陷时相对增益虚高）；
  3. `min(Δ_2024, Δ_2025) ≥ -2pp`（年度回退护栏，对 B1-a′ 比较适用）。
- **复用验证 gate（2021/2022）**：`Δ_2021 ≥ +2pp` **且** `Δ_2022 ≥ +2pp`（单一明确条件；比较对象为同年度同期 B1-a′ 基线）。结果标注证据强度降级。

### 7.4 2023 终验（预注册，仅一次）

终验臂 vs B1-a′ 同协议配对（40 题 × 3 repeats；密封前不存在可复用的 2023 基线，必须同跑）：

- `Δ2023 ≥ 0` → **CONFIRMED_PROMOTE**，设为默认路线；
- `-5pp < Δ2023 < 0` → **INCONCLUSIVE**：不设为默认，实现保留为研究分支，结论如实写为"复用验证正向但最终独立集未确认"；
- `Δ2023 ≤ -5pp` → **ROLLBACK**。
- 2023 运行后禁止任何形式的调参再跑。

### 7.5 预算

- dev（双管线+judge+同期 B1-a′）：scheduled single 960 / vote5 3840；hard_cap 1060 / 4230。
- 复用验证与 2023 见 §8（含配对基线完整成本与重试储备）；judge 实际量由 6B1 观测的臂间分歧率在下钻前修正 scheduled 估算（hard_cap 公式不变）。

## 8. 预算汇总（双分支，scheduled_calls 与 hard_cap 双列，含完整配对成本）

**双列定义（预注册）**：`scheduled_calls` = 无重试的正常调用数；`hard_cap = scheduled_calls + retry_reserve`，retry_reserve = scheduled 的 10% 并向上取整到 10 的倍数。一切网络重试从储备中支出；hard_cap 耗尽且存在非终态 attempt → `BLOCKED_INCOMPLETE`（§4.4.2），不得进入决策。

单位 scheduled 成本（40 题 × 3 repeats，judge 按最坏=每题分歧计）：

| 单元 | single | vote5 |
| --- | ---: | ---: |
| 单管线臂/年度（含 B1-a′、锚定臂） | 120 | 600 |
| 双管线+judge/年度 | 360 | 1320 |

分阶段（"—"表示该分支不发生）：

| 阶段 | scheduled single | scheduled vote5 | hard_cap single | hard_cap vote5 |
| --- | ---: | ---: | ---: | ---: |
| 6A0 上下文配对 + smoke | 260 | 260 | 290 | 290 |
| 6A1 dev（试测 100 + 采样 600 + 锚定 120） | 820 | 820 | 910 | 910 |
| 6A1 复用验证（仅 2021，含锚定 120） | — | 720 | — | 800 |
| 6B1 信号消融（2024+2025，3 臂） | 720 | 3600 | 800 | 3960 |
| 6B2 dev（2024+2025，双管线+judge+同期 B1-a′） | 960 | 3840 | 1060 | 4230 |
| 6B2 复用验证（2021+2022，含同期 B1-a′ 基线） | 960 | 3840 | 1060 | 4230 |
| 2023 终验（含 B1-a′ 基线） | 480 | 1920 | 530 | 2120 |
| **合计（6B2 触发）** | **4200** | **15000** | **≤ 4650** | **≤ 16540** |
| **合计（6B1 止损）** | **1800** | **5400** | **≤ 2000** | **≤ 5960** |

注：hard_cap 为含重试的调用尝试次数硬顶；重试账本与 `BLOCKED_INCOMPLETE` 语义见 §4.4.2。合计按各阶段 hard_cap 求和，为保守上限（储备未被消耗时不发生支出）。

## 9. 移出本设计的独立后续设计

1. **6C 推理时论断验证（GroundedClaim Verifier）**：claim 三元组 + 确定性事实校验；独立设计重点为误杀率控制与重推策略。
2. **6D 时间组合预计算**：命局×大运×流年交互的确定性注入；**目标年份时间上下文归 6D 所有**，v6 各臂不得注入任何当前日期流年。
3. 方向性记录：题型路由、知识库收敛与规则条件化、领域微调、动态紫微计算（若 6B1 证明本命紫微已有信号，再评估补全动态四化并配套权威快照验证）。

## 10. 实验顺序与依赖

```text
6A0（上下文 + profile + 设施硬化）
 │   基础设施 gate 失败 → 阻塞修复；上下文消融失败 → 回退旧上下文继续
 └─→ 6A1（严格投票 + temp-0 锚定；未 PROMOTE → protocol=single 继续）
       └─→ 6B1（本命紫微信号探针；臂间分歧率修正 6B2 预算）
             ├─ 有信号 → 6B2（含同期 B1-a′）→ 复用验证（2021/2022）→ 2023 终验（一次）
             └─ 无信号 → Ziwei 路线 ROLLBACK，转向 6C/6D 独立设计
```

**阻塞规则**：仅基础设施类 gate（enrichment、模板渲染、续跑一致性、键碰撞、重试账本、MingLi 前置的 BLOCKED 仅影响 MingLi 线）失败才阻塞后续；阶段判 `BLOCKED_INCOMPLETE`（hard_cap 耗尽且存在非终态 attempt）时该阶段不得进入决策，排查故障源后续跑；增强臂未过 gate 时，回退到上一稳定基线继续后续阶段，不整体停工。

## 11. Gate 汇总

| 臂 | PROMOTE / 推进 | 中间结论 | ROLLBACK / 止损 |
| --- | --- | --- | --- |
| 6A0 上下文 | Δ ≥ +2pp 采用为默认 | 0 ≤ Δ < +2pp 默认采用（地基性质） | Δ < 0 回退，旧上下文继续 |
| 6A0 设施/profile | 离线 gate 全过 | MingLi 前置缺失记 BLOCKED（不阻塞 BaziQA） | 修复前不推进；运行期 hard_cap 耗尽判 BLOCKED_INCOMPLETE |
| 6A1 投票 | Δ1 ≥ +3pp 且 Δ2 ≥ 0，2021 复核双条件通过 | Δ1 ≥ +3pp 但 Δ2 < 0 → AGGREGATION_EFFECT_ONLY；-3pp < Δ1 < +3pp 保持 single@0 | Δ1 ≤ -3pp 保持 single@0 |
| 6B1 信号 | Δ_dev ≥ +2pp 且 min(Δ_year) ≥ -2pp → 进 6B2 | B1-b 仅诊断 | 不满足即路线止损 |
| 6B2 双管线 | Δ_dev vs 同期 B1-a′ ≥ +4pp 且 dual 合并准确率 ≥ 32.5% 且年度护栏通过；2021、2022 各 ≥ +2pp | vs B1-c 仅 advisory（描述性，非同时段标注） | 不满足即弃用双管线 |
| 2023 终验 | Δ2023 ≥ 0 → CONFIRMED_PROMOTE | -5pp < Δ2023 < 0 → INCONCLUSIVE（不设默认） | Δ2023 ≤ -5pp → ROLLBACK |

## 12. 风险与开放问题

1. **严格投票的 unresolved 率**：低多样性采样下可能抬高 unresolved 率——已预注册多样性试测与 T 切换；unresolved 率作首类指标报告。
2. **本命紫微对时间类题目的覆盖缺口**：无动态四化，6B1 对流年/应期题的紫微信号可能系统性偏低——报告须声明；这本身是"是否补全动态紫微"的判据之一。
3. **复用验证集的证据强度**：2021/2022 已被 Phase 5 使用，复核结论只能佐证；6A1 复核预注册仅 2021，杜绝选择性验证；最终承诺以 2023 为准，且 2023 负增益不包装为成功。
4. **跨 profile 不可比**：prompt_style 差异混合 prompt 与交互协议双重变量，报告只作描述性并列。
5. **复现性与 provider 漂移的如实边界**：请求不携带 seed、API 不返回 `system_fingerprint`，manifest 只能保证**请求模型 ID 一致**，不能保证 provider 后端未漂移。缓解：原始响应按 attempt key 持久化支持重放审计；配对两臂同时间窗运行（含 temp-0 锚定与 6B2 同期 B1-a′）；模型版本按请求 ID 记录。推论：跨时段比较（如 6B2 vs 6B1 时段的 B1-c）只作 advisory，不承担硬门槛（§7.3）。
6. **网络重试成本与 BLOCKED_INCOMPLETE**：重试从各阶段 hard_cap 储备支出（§8）；网络尝试耗尽先以 `call_failed` 计入分母，报告须单列 `call_failed` 计数，超过题目数 5% 标注环境污染；若 hard_cap 耗尽仍有非终态 attempt，阶段判 `BLOCKED_INCOMPLETE` 不得进入决策，追加预算须显式登记。
7. **小样本统计纪律**：40 题/年度，2 题即 5pp；所有 gate 结论标注样本量，禁止过度表述。
