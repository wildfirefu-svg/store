# Phase 3 · 多排列原始选项身份聚合设计文档

- **日期**: 2026-07-02
- **修订**: 2026-07-03
- **作者**: TRAE Agent
- **状态**: 设计待审阅，未进入实施
- **对应总设计**: [2026-07-01-accuracy-improvement-design.md](file:///f:/project/agent/docs/superpowers/specs/2026-07-01-accuracy-improvement-design.md)
- **前置状态**:
  - Phase 1: Done / Baseline Archived / Shuffle Sensitivity Found
  - Phase 2: Engineering Done / Evaluation NO-GO
  - Phase 2.5: Offline Candidate Improved / Reranker Runtime Blocked
- **路线选择**: B 平衡对照路线，但主候选从“同顺序 SC + few-shot”修订为“每种 prompt 配置同时输出 per-seed 与 identity aggregation，并用同 prompt 的 off-3 对照和独立 final 数据验证”

---

## 1. 背景

Phase 1 的关键发现来自 [PHASE1_BASELINE_SUMMARY.md](file:///f:/project/agent/docs/PHASE1_BASELINE_SUMMARY.md):

| 指标 | 结果 | 解释 |
|---|---:|---|
| BaziQA `option_grounded_tfidf` shuffle-off 40×3 | 28.3% mean | 原主流程 baseline。 |
| BaziQA `option_grounded_tfidf` shuffle-on(seed=42) 40×3 | 18.3% mean | 比 shuffle-off 低 10.0pp，说明选项顺序敏感严重。 |
| MingLi-Bench 官方 2025 前 20 题 smoke | 60.0% | 官方 MingLi 链路可用，但只是 smoke，不代表完整 160 题指标。 |

Phase 2 状态以 [PHASE2_STATUS_UNIFIED.md](file:///f:/project/agent/docs/PHASE2_STATUS_UNIFIED.md) 为准：原始 hybrid Evaluation NO-GO，Phase 2.5 仅作为 opt-in 检索候选。

本轮修订后的核心实验原则：

1. 每种 prompt 配置都同时输出 per-seed 与 identity aggregation；
2. 每种 aggregation 都必须有同 prompt、同调用次数的 shuffle-off 对照；
3. 所有 prompt 配置复用同一份冻结的 permutation plan；
4. 正式 accuracy 使用 intent-to-evaluate，失败计错；
5. success-only 只用于位置偏差诊断；
6. final_holdout 必须独立，否则 formal 降级并标记统计限制。

---

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 | 验收口径 |
|---|---|---|
| P3-T0 | 恢复测试基线 | Phase 3 实施前先修复现有测试回归，确保相关测试全绿后再改实验逻辑。 |
| P3-T1 | 因果隔离 | 每种 prompt 配置同时输出 per-seed 与 identity aggregation：`A1-agg`、`A3-agg`、`A4-agg`。 |
| P3-T2 | 同 prompt 位置比较 | 正式 shuffle gap 必须比较同 prompt、同调用次数、仅选项排列不同的 pair：`A1-off-3 ↔ A1-agg`、`A3-off-3 ↔ A3-agg`、`A4-off-3 ↔ A4-agg`。 |
| P3-T3 | 消除位置偏差 | 冻结候选在正式评估中 `abs(candidate_off_3_mean - candidate_agg_mean) <= 3pp`。 |
| P3-T4 | 恢复 shuffle-on 表现 | 冻结候选 identity aggregation ITE accuracy ≥28%。 |
| P3-T5 | 保证选项身份一致 | `mean_majority_share >= 80%`，同时报告 `unanimous_case_rate` 和 `pairwise_identity_agreement`。 |
| P3-T6 | parser 稳定且可归因 | parser_valid ≥95%，并分开统计 `model_call_failed`、`empty_raw_answer`、`parser_invalid`、`unshuffle_map_failed`。 |
| P3-T7 | strict leak 保持 0 | 所有进入正式评估的候选 strict leak = 0，检测口径见第 10 节。 |
| P3-T8 | MingLi 同干预不退化 | MingLi 2025 first 20 在通用 APB 指令下 ≥58%，低于 Phase 1 60.0% 必须复核。 |
| P3-T9 | 开发集/最终集隔离 | development 用于 8/20 题和参数选择；final_holdout 必须独立，找不到独立 40 题时 formal 降级为 20 题并标记统计限制。 |

### 2.2 非目标

- 不把 Phase 2.5 hybrid 设为默认检索后端。
- 不在 Phase 3 修复 `bge-reranker-v2-m3` runtime blocked。
- 不在 Phase 3 解决旺衰、从格、格局用神等真实命理算法短板。
- 不用 8-case 准确率淘汰算法方案；8-case 只检查链路正确性。
- 不在 final_holdout 上反复调参。
- 不把 success-only accuracy 当正式准确率。
- 不把 MingLi 20 题 smoke 外推为完整 160 题能力。

---

## 3. 实验矩阵

### 3.1 Prompt 配置

| 配置 | Prompt | Few-shot | shuffle-on 输出 | shuffle-off 同口径对照 |
|---|---|---|---|---|
| A1 | 基础 prompt | 无 | A1 per-seed + A1-agg | A1-off-3 |
| A3 | 基础 prompt + APB block | 无 | A3 per-seed + A3-agg | A3-off-3 |
| A4 | 基础 prompt + APB block | dynamic few-shot | A4 per-seed + A4-agg | A4-off-3 |

A2 保留为同 seed SC=3 诊断臂，不参与正式候选冻结。

候选冻结规则：

```text
candidate in {A1-agg, A3-agg, A4-agg}
candidate >= A1-agg
candidate ITE accuracy >= 23%
parser_valid >= 95%
strict leak = 0
candidate mean_majority_share >= A1-agg mean_majority_share
```

允许 `A1-agg` 成为候选，表示“多排列身份聚合本身有效，APB/few-shot 没有增益”。

当多个候选同时满足 gate 时，使用确定性 tie-break，禁止看到 final 结果后再选：

```text
1. 更高 ITE accuracy
2. 更高 mean_majority_share
3. 更低 failure rate
4. 更低 cost
5. 更低配置复杂度：A1-agg 优先于 A3-agg，A3-agg 优先于 A4-agg
```

tie-break 必须在 development 阶段确定并写入报告。

#### 候选未达正式 28% 时的决策路径

dev20 候选冻结只要求 `ITE accuracy >= 23%`，但正式 gate 要求 `>= 28%`。当冻结候选在 dev20 介于 23%-28% 之间时，按以下决策：

| dev20 候选 ITE | 决策 |
|---|---|
| >= 28% | 进入 formal，目标 operational pass。 |
| 23% <= x < 28% | 标记 `candidate_below_formal_target`，仍可进入 formal，但 formal 必须达到 28% 才算 pass；否则记为 partial。 |
| < 23% | 不进入 formal，Phase 3 dev NO-GO。 |

若 dev20 没有任何候选达到 23%，Phase 3 直接 NO-GO，不进入 formal，也不允许降低 gate。这避免了“聚合本身有效但表现仍差”被包装成通过。

### 3.2 A6 命名

`A6` 只作为最终冻结候选的别名：

```text
A6 = frozen identity-aggregation candidate
A6 source = A1-agg | A3-agg | A4-agg
A6 off-control = A1-off-3 | A3-off-3 | A4-off-3
```

正式报告必须同时写明 `A6 source` 和 `A6 off-control`。

---

## 4. 共享 permutation plan

### 4.1 生成原则

不同实验臂不得各自独立补 seed。必须先生成并冻结：

```text
case_id -> [permutation_1, permutation_2, permutation_3]
```

所有 prompt 配置复用同一列表：

```text
A1 / A3 / A4 使用完全相同的 case_id -> permutation_id 列表
```

### 4.2 受控循环排列要求

3 个不同排列还不足够，因为正确选项可能始终落在同一 label。但排列生成不得读取正确答案，否则属于 label-aware 预处理，与 strict leak 原则冲突。

因此使用与 gold 无关的固定循环排列，对每题的原始选项顺序做循环移位：

```text
permutation_1 = [orig1, orig2, orig3, orig4]
permutation_2 = [orig2, orig3, orig4, orig1]
permutation_3 = [orig3, orig4, orig1, orig2]
```

这样每个原始选项在 3 个排列中自然覆盖 3 个不同位置，无需读取正确答案，也不需要补 seed。

#### 4.2.1 位置覆盖缺口

3 个循环移位中，每个原始选项只覆盖 4 个位置中的 3 个，存在一个系统性缺口位置。例如 `orig1` 会出现在 pos A、pos D、pos C，但永远不会出现在 pos B。

这意味着如果模型对缺失位置有强偏好，而正确答案恰好落在该位置，仍可能产生残余位置偏差。为缓解该缺口，提供两种方案：

| 方案 | permutations | 每选项覆盖位置 | 调用成本 |
|---|---:|---:|---|
| 3-permutation（默认） | 3 | 3/4 | 基线 |
| 4-permutation（可选，完整覆盖） | 4 | 4/4 | +33% |

默认使用 3-permutation。若 link8 或 dev20 的 `position_selection_frequency` 诊断显示聚合后仍存在明显位置偏好，可切换到 4-permutation 重新评估。两种方案的 permutation plan 都必须在 development 阶段冻结，不得在 formal 阶段切换。

link8 阶段的提前触发规则：若 link8 中任何 position 的选中率 >40%（4 选项均匀期望 25%），直接切换到 4-permutation，不等 dev20。这避免对特定位置有强偏好的模型在 3-permutation 下漏检残余偏差。

规则：

1. 不读取正确答案身份；
2. 循环移位对所有题目一致；
3. 记录 `permutation_id`、`label_map`；
4. `answer_position` 只在评分阶段用于诊断，不参与排列生成；
5. 不使用随机 seed，不做 arm 内补种。

### 4.3 permutation_id

`permutation_id` 应由当前选项原始身份顺序组成，例如：

```text
orig2|orig3|orig4|orig1
```

测试必须验证：

- 每题 3 个 permutation_id 均不同；
- 每个原始选项在 3 个排列中覆盖 3 个不同位置（由固定循环移位保证）；
- A1/A3/A4 复用完全相同 permutation plan；
- 排列生成不读取正确答案；
- aggregation 输入不能混入 arm 独立生成的排列。

---

## 5. Prompt 与 few-shot 设计

### 5.1 通用 APB 指令

通用 APB 指令同时用于 BaziQA 和 MingLi：

1. 以当前选项文本为准；
2. 不根据 A/B/C/D 的位置、历史分布或 few-shot 示例字母猜测；
3. evidence 只辅助比较选项内容，不能直接抄标签；
4. 最终输出当前题目的一个 label；
5. 如果选项顺序变化，答案也必须跟随选项文本而不是跟随位置。

### 5.2 Dynamic few-shot

BaziQA 可使用领域 few-shot，但必须避免“领域→答案字母”固定关联。

注入要求：

- 使用无固定 label 的 option identity schema；
- 注入时动态生成 A/B/C/D label；
- 记录 `fewshot_label_map`；
- label 平衡不能只要求“不全相同”；
- 首版 gate：各 label 数量差不超过 1；如果样本数不满足整除，最大占比不得超过 30%；
- 禁止同人物、同题干或近重复样本进入 few-shot；
- 禁止 final_holdout case 进入 few-shot。

### 5.3 Few-shot 内容来源与质量审核

few-shot 示例的生成方式必须明确，否则无法保证无泄漏和领域有效性。

来源规则：

| 来源 | 是否允许 | 约束 |
|---|---|---|
| 手工编写 | 允许（首选） | 不得复制 holdout 题干、人物或选项文本。 |
| 从 corpus 改写 | 允许 | 必须经过 normalization，且与 development/final_holdout 题干近重复检查不通过才能用。 |
| LLM 生成 | 允许 | 必须人工复核命理合理性，且不引入 holdout 近重复。 |
| 直接复制 holdout 题 | 禁止 | 无论是否改写选项顺序。 |

质量审核流程：

1. 每条示例必须经过 `tests/test_phase3_fewshot_pool.py` 的 schema、label 平衡、无泄漏、近重复检查；
2. 命理内容（如旺衰、用神、十神关系）由实施者人工复核，确保不传授错误规则；
3. 示例只展示“逐项按选项文本比较”的推理范式，不写长篇命理规则；
4. 审核结论写入 `docs/PHASE3_EXPERIMENT_REPORT.md` 的 few-shot 来源章节。

---

## 6. 数据划分

优先方案：

| split | 数据来源 | 用途 |
|---|---|---|
| development | 现有 2025 holdout 中 20 题 | link8、dev20、参数选择、候选冻结。 |
| final_holdout | 从未参与调参的另一年份或新题集 40 题 | 方案冻结后只运行一次。 |
| external_validation | LOVO 或下一年份数据 | Phase 3 后泛化验证。 |

#### 6.1 开发集数据重复暴露声明

Phase 1 已对 2025 holdout 40 题跑了 40×3 shuffle-on/off。Phase 3 development 又从同一 40 题中取 20 题。模型已在 Phase 1 中多次"见过"这些题目（即使排列不同），存在惯性/记忆效应，可能抬高 A1-off-3 基线，使 shuffle gap 看起来比真实泛化更小。

因此报告必须显式声明：

```text
development_data_exposed_in_phase1 = true
exposure_direction = optimistic_for_A1_off_3_baseline
```

如果存在未参与 Phase 1 评估的独立题目，应优先用作 development。若实在找不到，则保留现有方案，但 shuffle gap 结论必须标注"基线可能因重复暴露而偏高"。

如果找不到独立 40 题 final_holdout：

| fallback | 规则 |
|---|---|
| final_holdout=20 | 从现有 holdout 中拆分 20 题 final；formal 改成 20 题。 |
| 统计限制 | 单题对应 5pp，无法严格判断 3pp gate。 |
| 报告标记 | 必须标记 `final_holdout_size_limited` 和 `3pp_gate_underpowered`。 |
| 禁止事项 | 不得把全部 40 题同时用于 development 和 final。 |

---

## 7. 准确率与失败口径

必须同时报告：

| 指标 | 分母 | 用途 |
|---|---|---|
| intent-to-evaluate accuracy | 全部题，失败计错 | 正式 gate 使用。 |
| success-only accuracy | 成功调用且解析成功的题 | 诊断位置偏差，不作为正式准确率。 |
| failure rate | 全部调用 | 稳定性指标。 |

parser_valid 也必须分层报告：

| 指标 | 分母 | 说明 |
|---|---|---|
| call-level parser_valid | 全部 model calls | 单次调用是否成功解析。 |
| case-level aggregation eligible | 全部题 | 该题是否有足够成功 permutation 进入聚合。 |
| excluded case count | 全部题 | 因失败被排除出配对/聚合的题数。 |

正式 `candidate_agg_mean >= 28%` 必须使用 intent-to-evaluate accuracy。

位置偏差配对分析只能使用双方都成功的 pair：

```text
pair_analysis_eligible = off_success and on_success and parser_valid_both and unshuffle_success
```

若 `unshuffle_map_failed` 比例较高，pair analysis 样本量会大幅缩减。因此增加 gate：

```text
pair_analysis_eligible_rate >= 80%
```

否则报告标记 `pair_analysis_underpowered=true`，3pp operational gate 只能作为方向性指标，不得宣称通过。

---

## 8. 一致性指标定义

必须报告：

| 指标 | 定义 | 用途 |
|---|---|---|
| `mean_majority_share` | 每题最多票原始选项身份占比的宏平均。例如 2/3=66.7%，3/3=100%。 | 正式 gate，要求 ≥80%。 |
| `unanimous_case_rate` | 三个 permutation 全部预测同一原始选项身份的题目比例。 | 辅助诊断。 |
| `pairwise_identity_agreement` | 同题任意两个 permutation 预测相同原始选项身份的 pair 比例。 | 辅助诊断。 |

Development gate 明确为：

```text
candidate mean_majority_share >= A1-agg mean_majority_share
```

Formal gate 明确为：

```text
candidate mean_majority_share >= 80%
```

---

## 9. 评估顺序

### Step 0: 恢复测试基线

Phase 3 开始前先修复现有测试回归。

### Step 1: 离线 render 与 schema 测试

验证：

- few-shot 使用 option identity，不固定答案字母；
- few-shot 注入时动态 shuffle；
- label 平衡满足差值 ≤1 或最大占比 ≤30%；
- 共享 permutation plan 已生成，使用固定循环移位；
- 排列生成不读取正确答案；
- 每个原始选项在 3 个排列中覆盖 3 个不同位置；
- A1/A3/A4 复用完全相同 permutation plan；
- parser failure reason 可分类；
- 历史 JSONL 缺少新字段时 summarizer 仍可运行。

### Step 2: link8 链路检查

8-case 只检查链路，不用于淘汰算法方案。

### Step 3: development 20-case 配对实验

至少运行：

```text
A1-off-3 + A1 per-permutation + A1-agg
A3-off-3 + A3 per-permutation + A3-agg
A4-off-3 + A4 per-permutation + A4-agg
```

输出：

- A1-agg / A3-agg / A4-agg ITE accuracy；
- A1-off-3 / A3-off-3 / A4-off-3 ITE accuracy；
- 同 prompt shuffle gap；
- success-only accuracy；
- failure rate；
- A1-agg错→候选对数量；
- A1-agg对→候选错数量；
- McNemar exact 或配对 bootstrap 区间；
- mean_majority_share；
- unanimous_case_rate；
- pairwise_identity_agreement；
- position selection frequency；
- domain 分组 accuracy 与 shuffle gap（追踪 Phase 1 弱域 annual_fortune/relationship/health 是否改善）。

候选冻结条件：

```text
candidate in {A1-agg, A3-agg, A4-agg}
candidate >= A1-agg
candidate ITE accuracy >= 23%
parser_valid >= 95%
strict leak = 0
candidate mean_majority_share >= A1-agg mean_majority_share
```

### Step 4: MingLi 同干预 smoke

MingLi 至少比较 baseline direct_choice 与 direct_choice + 通用 APB block。BaziQA 领域 few-shot 不注入 MingLi。

统计效力说明：20 题每题 = 5pp，58% 与 60% 仅差一题，完全在随机波动范围内。此 gate 仅用于检测严重退化（≥2 题差异），不能证明无退化。

### Step 5: final_holdout 正式评估

只运行冻结后的 A6 source 及其同 prompt off-control。

如果 A6 source 是：

| A6 source | 必须运行的 off-control |
|---|---|
| A1-agg | A1-off-3 |
| A3-agg | A3-off-3 |
| A4-agg | A4-off-3 |

如果有独立 40 题 final_holdout，formal 使用 40 题。否则 formal 降级为 20 题，并标记 `final_holdout_size_limited=true` 与 `3pp_gate_underpowered=true`。

---

## 10. strict leak 检测口径

### 10.1 检测对象

strict leak 检测至少覆盖：

- retrieved evidence text；
- prompt 中注入的 few-shot text；
- prompt 中注入的 chart/metadata text；
- model input 中的 question/options 以外上下文；
- case_details 中用于模型输入的 evidence 字段。

### 10.2 禁止泄漏内容

不得在 evidence/few-shot/metadata 中出现：

- expected answer label；
- expected answer text 的完整或近似复现；
- gold/answer/expected_answer 字段名及值；
- final_holdout case_id；
- 人物身份或题干中足以唯一定位答案的近重复文本；
- 同题或近重复题目的解析结论。

### 10.3 自动命中与确认泄漏

option-grounded 检索本身会使用选项文本，正确答案文本出现在 evidence 中可能是正常检索，不一定是泄漏。因此必须区分：

| 指标 | 含义 |
|---|---|
| `leak_candidate_count` | 自动规则命中的可疑数量。 |
| `confirmed_leak_count` | 人工复核后确认的真实泄漏数量。 |

流程：

```text
自动规则命中 -> 记入 leak_candidate_count -> 人工复核 -> 确认后记入 confirmed_leak_count
```

正式 `strict leak = 0` 针对 `confirmed_leak_count`，但报告必须同时保留 `leak_candidate_count`。

### 10.4 分母与阈值

报告两个分母：

| 指标 | 分母 | 阈值 |
|---|---|---:|
| case-level confirmed strict leak | 题数 | 0 |
| evidence-item confirmed strict leak | evidence 条数 | 0 |

### 10.5 近重复阈值

首版使用保守规则：

```text
normalized character overlap >= 0.85
或 answer text 完整出现在 evidence/few-shot 中
或 final_holdout case_id 完整出现
```

命中任一规则即计入 `leak_candidate_count`，需要人工复核后才计入 `confirmed_leak_count`。

---

## 11. 正式 gate

| 指标 | 阈值 |
|---|---:|
| frozen candidate ITE accuracy | ≥28% |
| candidate off-control ITE accuracy | ≥28.3%，目标 ≥32% |
| `abs(candidate_off_3_mean - candidate_agg_mean)` | ≤3pp（operational gate，见下） |
| `mean_majority_share` | ≥80% |
| parser_valid | ≥95% |
| case-level confirmed strict leak | 0 |
| evidence-item confirmed strict leak | 0 |
| success-only paired analysis | A1-agg→candidate 正向翻转不少于负向翻转 |
| MingLi APB smoke | ≥58%，低于 60.0% 必须复核 |

关于 3pp：这是 **operational gate**，即“观测差值 ≤3pp”。40 题时一题即 2.5pp，`≤3pp` 实际等价于两组最多相差一题，不能表述为统计证明“已消除位置偏差”。若需要统计结论，必须扩大样本量，并做等效性检验或报告配对 bootstrap 置信区间。

如果 final 只有 20 题，3pp gate 只能作为方向性指标，不得宣称严格通过。

#### 3pp gate 的 advisory 性质

3pp 在 formal gate 中属于 **operational advisory**，不是 hard gate。与 `confirmed strict leak = 0`、`parser_valid >= 95%` 这类硬 gate 不同：

| gate 类型 | 不达标时动作 |
|---|---|
| hard gate（leak、parser_valid、ITE accuracy） | 自动 NO-GO |
| operational advisory（3pp shuffle gap） | 触发复核与建议，不自动 NO-GO |

3pp 不达标时，报告必须写明残余位置偏差大小，并由人工判断是否进入 Phase 4 或重新设计，而非自动判定 Phase 3 失败。

#### formal20 的整数题对应

20 题时每题 = 5pp，28% 对应 5.6 题，无法整数实现。因此 formal20 时 28% gate 必须转换为整数题对应：

| formal20 命中题数 | accuracy | 决策 |
|---|---:|---|
| < 5/20 | < 25% | NO-GO |
| 5/20 | 25% | operational pass（达到 dev 下限） |
| 6/20 | 30% | strong pass |
| >= 7/20 | >= 35% | strong pass + 接近 Phase 3 原始目标 |

formal20 不存在“刚好 28%”的可能。5/20 视为 operational pass，6/20 视为 strong pass。报告必须写明实际命中题数，不得只写百分比。

---

## 12. 调用预算

采用固定循环排列后不需要补排列预算，因此 `permutation_supplement_budget = 0`。

预算字段：

| 字段 | 含义 |
|---|---|
| planned_primary_calls | 主矩阵计划调用数。 |
| retry_budget | 失败重试预算。 |
| hard_call_cap | 绝对调用上限。达到后停止，不再重试。 |

调用数按实际矩阵重新计算：

- link8：8 cases × 3 configs × 2 modes × 3 permutations = 144；
- dev20：20 cases × 3 configs × 2 modes × 3 permutations = 360；
- MingLi20：20 cases × 3 variants = 60；
- formal40：仅冻结候选及其 off-control，40 cases × 2 modes × 3 permutations = 240；
- formal20 fallback：20 cases × 2 modes × 3 permutations = 120。

| 阶段 | planned_primary_calls | retry_budget | hard_call_cap |
|---|---:|---:|---:|
| link8 | 144 | 30 | 174 |
| dev20 | 360 | 72 | 432 |
| MingLi20 | 60 | 12 | 72 |
| formal40 | 240 | 48 | 288 |
| formal20 fallback | 120 | 24 | 144 |

retry_budget 约为主调用数的 20%。达到 hard cap 后必须停止并在报告中标记 `call_cap_reached=true`。

---

## 13. 对真实命理水平的边界说明

Phase 3 主要提升选择题输出可靠性、评测可信度和抗位置偏差能力，不直接修复旺衰、从格、格局用神、报告一致性等命理算法短板。

---

## 14. 待审阅决策

1. 是否确认 `A1-off-3/A3-off-3/A4-off-3` 为同 prompt 正式对照；
2. 是否确认 candidate 冻结条件使用 `candidate >= A1-agg`，允许 A1-agg 成为候选；
3. 是否确认所有 prompt 配置复用同一份 `case_id -> permutations`；
4. 是否确认使用与 gold 无关的固定循环排列，使每个选项自然覆盖 3 个位置，不读取正确答案；
5. 是否确认 development gate 使用 `candidate mean_majority_share >= A1-agg mean_majority_share`，并采用确定性 tie-break；
6. 是否确认 strict leak 区分 `leak_candidate_count` 与 `confirmed_leak_count`，正式 gate 针对 confirmed；
7. 是否确认 3pp 为 operational gate，不表述为统计证明；
8. 是否确认调用预算为 link8=144 / dev20=360 / MingLi20=60 / formal40=240 / formal20=120，达到 hard cap 后停止；
9. 是否确认 dev20 候选 23%≤x<28% 时仍可进 formal 但必须达 28% 才算 pass，<23% 则 Phase 3 dev NO-GO；
10. 是否确认 formal20 使用整数题对应（5/20=operational pass，6/20=strong pass）；
11. 是否确认 few-shot 优先手工编写，禁止直接复制 holdout，命理内容需人工复核；
12. 是否确认 `pair_analysis_eligible_rate >= 80%`，否则 3pp gate 降级为方向性指标。
