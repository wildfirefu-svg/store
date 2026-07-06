# Phase 3 · 多排列原始选项身份聚合实施计划

- **日期**：2026-07-02
- **修订**：2026-07-03
- **对应设计**：[2026-07-02-phase3-anti-position-bias-design.md](file:///f:/project/agent/docs/superpowers/specs/2026-07-02-phase3-anti-position-bias-design.md)
- **状态**：计划待审阅，未进入实施
- **执行原则**：TDD、小步验证、DRY、YAGNI、每个任务产出可独立测试的变更
- **执行者假设**：对代码库不熟悉，需按本文顺序执行

---

## 0. Phase 3 目标摘要

Phase 3 每种 prompt 配置都必须同时输出 shuffle-on aggregation 和同 prompt shuffle-off 对照：

```text
A1-agg ↔ A1-off-3
A3-agg ↔ A3-off-3
A4-agg ↔ A4-off-3
```

最终候选：

```text
A6 = 从 development 中冻结的 A1-agg / A3-agg / A4-agg 之一
```

冻结条件允许 `A1-agg` 成为候选：

```text
candidate >= A1-agg
```

---

## 1. 预期文件结构

| 文件 | 类型 | 作用 |
|---|---|---|
| `tests/test_rag_prompt_builder.py` | 修改 | Task 0 修复 fake `option_evidence` 接口。 |
| `benchmark/fewshot/anti_position_bias_v1.jsonl` | 新增 | option identity schema 的 dynamic few-shot pool。 |
| `tests/test_phase3_fewshot_pool.py` | 新增 | schema、label 平衡、无泄漏、近重复检测。 |
| `tests/test_phase3_prompt_builder.py` | 新增 | APB block、dynamic few-shot render、label map。 |
| `tests/test_phase3_parser_diagnostics.py` | 新增 | failure reason、ITE/success-only 字段测试。 |
| `tests/test_phase3_runner_matrix.py` | 新增 | A1/A3/A4 off-3、aggregation、共享 permutation、gate、预算、pair stats。 |
| `rag_prompt_builder.py` | 修改 | APB 指令、dynamic few-shot render。 |
| `benchmark/runners/run_benchmark.py` | 修改 | 可选 parser_failure_reason、option_identity、permutation_id 输出。 |
| `scripts/run_baziqa_retrieval_ablation.py` | 修改 | 前置补 `--fewshot-file` pass-through。 |
| `scripts/run_phase3_ablation.py` | 新增 | 编排、dry-run、split、聚合、报告，不重复模型调用。 |
| `docs/PHASE3_EXPERIMENT_REPORT.md` | 新增 | 记录 development/final 结果。 |

---

## 2. 实验矩阵

| 配置 | shuffle-on 输出 | shuffle-off 同 prompt 对照 | 用途 |
|---|---|---|---|
| A1 | A1 per-permutation + A1-agg | A1-off-3 | 基础 prompt 聚合效果。 |
| A3 | A3 per-permutation + A3-agg | A3-off-3 | APB 指令效果。 |
| A4 | A4 per-permutation + A4-agg | A4-off-3 | dynamic few-shot 增益。 |

A2 保留为同 seed SC=3 诊断臂，不参与候选冻结。

A6 定义：

```text
A6 source = A1-agg | A3-agg | A4-agg
A6 off-control = A1-off-3 | A3-off-3 | A4-off-3
```

---

## 3. Task 0：恢复现有测试基线

**目标**：Phase 3 任何新功能前，先修复已知回归。

已知问题：`rag_prompt_builder.py` 调用 `option_evidence(..., retrieval_mode=...)`，但 `tests/test_rag_prompt_builder.py` 的 fake 未接收该参数。

步骤：

1. 运行 `python -m pytest --version`；
2. 运行 `python -m pytest tests/test_rag_prompt_builder.py -q`；
3. 修改 fake `option_evidence` 签名，接受 `retrieval_mode=None`；
4. 运行 `python -m pytest tests/test_rag_prompt_builder.py tests/test_rag_prompt_hybrid.py -q`；
5. 运行完整 Phase 1 回归测试集，确认全部通过后再进入 Task 1：

```powershell
python -m pytest tests/test_benchmark_shuffle_options.py tests/test_benchmark_runner_shuffle_options.py tests/test_benchmark_self_consistency.py tests/test_benchmark_runner_self_consistency.py tests/test_mingli_bench_adapter.py tests/test_run_mingli_bench_cli.py tests/test_rag_prompt_hybrid.py tests/test_case_index.py tests/test_case_index_hybrid.py tests/test_case_dense_index.py tests/test_reranker_stub.py tests/test_hybrid_rrf.py -q
```

Task 0 不只修复单个测试，而是恢复整个基线全绿。若其他测试也有回归，必须一并修复或记录为已知问题。

---

## 4. Task 1：确定 development/final 数据来源

**目标**：先解决 holdout 有效性，再写实验脚本。

必须在 `docs/PHASE3_EXPERIMENT_REPORT.md` 记录：

```text
development_source = ...
final_holdout_source = ...
final_holdout_size = 40 | 20
final_holdout_independent = true | false
```

如果找不到独立 40 题 final：

- 从现有 40 题拆 20 development / 20 final；
- formal 只跑 20 题；
- 标记 `final_holdout_size_limited=true`；
- 标记 `3pp_gate_underpowered=true`；
- 不得宣称严格通过 3pp gate。

---

## 5. Task 2：few-shot option identity schema 测试

**文件**：`tests/test_phase3_fewshot_pool.py`

测试要求：

- pool 文件存在；
- 行数等于 5；
- 覆盖 family、health、relationship、annual_fortune、career；
- 每条使用 `option_identities`，不固定 A/B/C/D answer；
- 恰好 1 条 `is_answer=true`；
- label 平衡满足各 label 数量差不超过 1；若样本数不满足均分，最大占比不得超过 30%；
- 不包含 final_holdout case_id、expected_answer、gold、mingli_ id；
- 与 development/final_holdout 题干不得完全相同或近重复。

---

## 6. Task 3：创建 dynamic few-shot pool

**文件**：`benchmark/fewshot/anti_position_bias_v1.jsonl`

#### 内容来源（前置）

在写 pool 之前必须先确定来源，避免泄漏：

| 来源 | 是否允许 | 约束 |
|---|---|---|
| 手工编写 | 允许（首选） | 不得复制 holdout 题干、人物或选项文本。 |
| 从 corpus 改写 | 允许 | 必须 normalization，且近重复检查不通过才能用。 |
| LLM 生成 | 允许 | 人工复核命理合理性，且不引入 holdout 近重复。 |
| 直接复制 holdout 题 | 禁止 | 无论是否改写选项顺序。 |

#### 质量审核

1. 每条示例必须通过 `tests/test_phase3_fewshot_pool.py`；
2. 命理内容由实施者人工复核，确保不传授错误规则；
3. 示例只展示“逐项按选项文本比较”，不写长篇命理规则；
4. 审核结论写入 `docs/PHASE3_EXPERIMENT_REPORT.md`。

要求：

- 使用 option identity schema；
- 示例可以合成，但不能复制 holdout；
- 不固定答案 label；
- 不包含人物、题干或 case_id 近重复。

---

## 7. Task 4：APB prompt 与 dynamic few-shot render

**文件**：`tests/test_phase3_prompt_builder.py`、`rag_prompt_builder.py`

**说明**：本任务为纯函数级测试，不依赖 CLI 传参，因此可在 Task 5（`--fewshot-file` pass-through）之前完成。`render_dynamic_fewshot` 直接接收 example 对象，不经过 argparse。

测试：

- APB block 包含“以当前选项文本为准”“不根据 A/B/C/D 位置猜”；
- `render_dynamic_fewshot(example, seed)` 不同 seed 生成不同 label map；
- `fewshot_label_map` 记录 option identity → label；
- final label 与动态映射一致；
- label 分布满足 Task 2 平衡规则。

**依赖说明**：Task 4 完成后 A4 render 函数可用，但 A4 完整链路（runner → CLI → model call）需 Task 5（`--fewshot-file` pass-through）完成后才可执行。不要在 Task 4 后尝试跑在线 A4。

---

## 8. Task 5：补 `--fewshot-file` pass-through

**目标**：实验矩阵前先让 A4 命令可执行。

步骤：

1. 核实实际 CLI 测试文件：`Get-ChildItem tests -Filter '*baziqa*'`；
2. 写 `--fewshot-file` argparse 测试；
3. 实现 pass-through；
4. 不改变默认行为。

---

## 9. Task 6：共享 permutation plan

**目标**：先生成并冻结 `case_id -> permutations`，所有 prompt 配置复用，禁止 arm 内独立补 seed，且不读取正确答案。

使用与 gold 无关的固定循环移位：

```text
permutation_1 = [orig1, orig2, orig3, orig4]
permutation_2 = [orig2, orig3, orig4, orig1]
permutation_3 = [orig3, orig4, orig1, orig2]
```

测试：

- 为每个 case 生成 3 个循环移位 permutation；
- 每题 3 个 `permutation_id` 均不同；
- 每个原始选项在 3 个 permutation 中覆盖 3 个不同位置（由循环移位保证）；
- 记录每个选项的缺失位置，供 `position_selection_frequency` 诊断使用；
- 若 link8/dev20 诊断显示聚合后仍存在明显位置偏好，可切换到 4-permutation 方案（覆盖全部 4 个位置），但必须在 development 冻结，不得在 formal 切换；
- 排列生成不读取正确答案身份；
- A1/A3/A4 使用完全相同的 permutation list；
- `permutation_id` 由原始选项身份顺序生成；
- 不使用随机 seed，不做 arm 内补种；
- 前置断言：所有 case 的 options 长度恰好为 4；若存在非 4 选项 case，降级为 identity 不聚合并记录 `non4_option_case`。

---

## 10. Task 7：parser diagnostics、ITE 与 success-only 字段

字段：

```text
parser_failure_reason
call_success
pair_analysis_eligible
intent_to_evaluate_correct
success_only_eligible
```

要求：

- `parser_failure_reason` 为可选字段；
- 历史 JSONL 不含新字段时 summarizer 可运行；
- 正式 accuracy 用全部题，失败计错；
- success-only 只作诊断；
- parser_valid 分层报告：call-level parser_valid、case-level aggregation eligible、excluded case count。

失败分类：

```text
model_call_failed
empty_raw_answer
parser_invalid
label_out_of_range
unshuffle_map_failed
```

---

## 11. Task 8：原始选项身份聚合 helper

函数：

```python
def to_original_option_identity(predicted_label, label_map):
    ...

def aggregate_by_option_identity(predictions):
    ...
```

要求：

- 当前 label 先还原原始选项身份；
- 不直接对 A/B/C/D 投票；
- 输出 A1-agg/A3-agg/A4-agg；
- 输出 ITE accuracy 和 success-only accuracy 所需字段；
- tie 时记录 `tie=True`；
- 提供确定性候选 tie-break：ITE accuracy → mean_majority_share → failure rate → cost → 配置复杂度（A1-agg 优先于 A3-agg，A3-agg 优先于 A4-agg），并在 development 阶段确定，禁止看到 final 结果后再选。

---

## 12. Task 9：一致性指标 helper

函数：

```python
def mean_majority_share(predictions):
    ...

def unanimous_case_rate(predictions):
    ...

def pairwise_identity_agreement(predictions):
    ...
```

Development gate：

```text
candidate mean_majority_share >= A1-agg mean_majority_share
```

Formal gate：

```text
candidate mean_majority_share >= 80%
```

---

## 13. Task 10：strict leak 检测 helper

检测对象：

- retrieved evidence text；
- few-shot text；
- chart/metadata text；
- question/options 以外的 model input context；
- case_details 中用于模型输入的 evidence 字段。

禁止泄漏：

- expected answer label；
- expected answer text 完整或近似复现；
- gold/answer/expected_answer 字段名及值；
- final_holdout case_id；
- 人物身份或题干中足以唯一定位答案的近重复文本；
- 同题或近重复题目的解析结论。

区分自动命中与确认泄漏：

- option-grounded 检索会正常使用选项文本，自动命中不等于泄漏；
- 自动规则命中记入 `leak_candidate_count`；
- 人工复核确认后记入 `confirmed_leak_count`；
- 正式 `strict leak = 0` 针对 `confirmed_leak_count`，但报告必须保留 `leak_candidate_count`。

报告两个分母：

```text
case-level confirmed strict leak / 题数
evidence-item confirmed strict leak / evidence 条数
```

近重复阈值：

```text
normalized character overlap >= 0.85
或 answer text 完整出现
或 final_holdout case_id 完整出现
```

命中任一规则先计入 `leak_candidate_count`，人工复核后才计入 `confirmed_leak_count`。

---

## 14. Task 11：实验矩阵与 dry-run

`scripts/run_phase3_ablation.py` 必须支持：

```text
A1-off-3 + A1 per-permutation + A1-agg
A3-off-3 + A3 per-permutation + A3-agg
A4-off-3 + A4 per-permutation + A4-agg
A6 source/off-control 冻结记录
```

Dry-run 输出：

- development/final split；
- 共享 permutation plan；
- 每个 arm 的现有 runner 命令；
- prompt 配置；
- 预算估算；
- hard_call_cap。

---

## 15. Task 12：配对统计与报告聚合

报告必须包含：

- A1-agg / A3-agg / A4-agg ITE accuracy；
- A1-off-3 / A3-off-3 / A4-off-3 ITE accuracy；
- 同 prompt shuffle gap；
- success-only accuracy；
- failure rate；
- call-level parser_valid / case-level aggregation eligible / excluded case count；
- leak_candidate_count；
- case-level confirmed strict leak；
- evidence-item confirmed strict leak；
- A1-agg错→候选对；
- A1-agg对→候选错；
- McNemar exact 或配对 bootstrap 区间；
- mean_majority_share；
- unanimous_case_rate；
- pairwise_identity_agreement；
- permutation uniqueness；
- option position coverage；
- position selection frequency；
- pair_analysis_eligible_rate；
- pair_analysis_underpowered 标记（若 eligible_rate < 80%）；
- budget fields。

---

## 16. Task 13：MingLi 同干预 smoke

MingLi 至少比较：

```text
baseline direct_choice
direct_choice + 通用 APB block
```

BaziQA 领域 few-shot 不注入 MingLi。

如果 MingLi runner 不支持 APB block：

1. **首选 fallback**：手动拼接 APB 指令到 MingLi prompt 前缀，作为最小干预，确保与 BaziQA 通用 APB 一致；
2. **次选 fallback**：若 runner 不允许 prompt 前缀注入，则标记为 Phase 3 遗留项，并在报告中明确“MingLi smoke 无法证明 Phase 3 未退化”；
3. 不得为了对齐而临时复制 BaziQA runner 逻辑到 MingLi 脚本。

无论哪种 fallback，报告必须写明 MingLi 实际启用的干预方式。

---

## 17. Task 14：调用预算与 hard cap

采用固定循环排列后不需要补排列预算，因此不设 `permutation_supplement_budget`。

预算字段：

```text
planned_primary_calls
retry_budget
hard_call_cap
```

调用数按实际矩阵计算：

- link8：8 × 3 configs × 2 modes × 3 permutations = 144；
- dev20：20 × 3 configs × 2 modes × 3 permutations = 360；
- MingLi20：20 × 3 variants = 60；
- formal40：仅冻结候选及其 off-control，40 × 2 modes × 3 permutations = 240；
- formal20 fallback：20 × 2 modes × 3 permutations = 120。

| 阶段 | planned_primary_calls | retry_budget | hard_call_cap |
|---|---:|---:|---:|
| link8 | 144 | 30 | 174 |
| dev20 | 360 | 72 | 432 |
| MingLi20 | 60 | 12 | 72 |
| formal40 | 240 | 48 | 288 |
| formal20 fallback | 120 | 24 | 144 |

达到 hard cap 后停止并标记：

```text
call_cap_reached=true
```

---

## 18. Task 15：离线 dry-run 验证

**目标**：在无 API 调用的前提下，验证完整 pipeline 数据流。

除运行测试和编译外，必须额外输出 stage-by-stage 完整 pipeline trace：

```text
split → permutation plan → prompt render → mock answer → parse → unshuffle → aggregate → report
```

每个 stage 的输入/输出必须可检查，且全部在无 API 调用下通过。这确保在线执行时数据流不会在中间环节断裂。

运行：

```powershell
python -m pytest tests/test_rag_prompt_builder.py tests/test_phase3_fewshot_pool.py tests/test_phase3_prompt_builder.py tests/test_phase3_parser_diagnostics.py tests/test_phase3_runner_matrix.py -q
python -m pytest tests/test_benchmark_shuffle_options.py tests/test_benchmark_runner_shuffle_options.py tests/test_benchmark_self_consistency.py tests/test_benchmark_runner_self_consistency.py tests/test_mingli_bench_adapter.py tests/test_run_mingli_bench_cli.py tests/test_rag_prompt_hybrid.py -q
python -m py_compile rag_prompt_builder.py benchmark\runners\run_benchmark.py scripts\run_baziqa_retrieval_ablation.py scripts\run_phase3_ablation.py scripts\run_mingli_bench.py
```

---

## 19. Task 16：在线执行门禁

### link8

只检查链路：无泄漏、parser 可用、unshuffle 正确、共享 permutation plan 正确、循环排列使每个选项覆盖 3 个位置、dynamic few-shot label 分布合理、无明显全选同一位置。

### dev20

运行 A1/A3/A4 的 off-3 和 on aggregation，冻结一个 candidate。

冻结条件：

```text
candidate in {A1-agg, A3-agg, A4-agg}
candidate >= A1-agg
candidate ITE accuracy >= 23%
parser_valid >= 95%
confirmed strict leak = 0
candidate mean_majority_share >= A1-agg mean_majority_share
```

候选并列时使用确定性 tie-break：ITE accuracy → mean_majority_share → failure rate → cost → 配置复杂度（A1-agg > A3-agg > A4-agg），在 development 阶段确定。

#### dev20 决策路径

| dev20 最高候选 ITE | 决策 |
|---|---|
| >= 28% | 进入 formal，目标 operational pass。 |
| 23% <= x < 28% | 标记 `candidate_below_formal_target`，仍可进 formal，但 formal 必须达 28% 才算 pass。 |
| < 23% | Phase 3 dev NO-GO，不进入 formal，不得降低 gate。 |

### formal

只运行冻结后的 candidate 和对应 off-control。

正式 gate：

```text
candidate ITE accuracy >= 28%
candidate off-control ITE accuracy >= 28.3%
abs(candidate_off_3_mean - candidate_agg_mean) <= 3pp  # operational gate，非统计证明
candidate mean_majority_share >= 80%
parser_valid >= 95%
case-level confirmed strict leak = 0
evidence-item confirmed strict leak = 0
```

如果 final_holdout 独立 40 题不存在，formal 改 20 题并标记统计限制。

#### formal20 整数题对应

20 题时 28% = 5.6 题无法整数实现，必须转换为整数题对应：

| formal20 命中题数 | accuracy | 决策 |
|---|---:|---|
| < 5/20 | < 25% | NO-GO |
| 5/20 | 25% | operational pass |
| 6/20 | 30% | strong pass |
| >= 7/20 | >= 35% | strong pass + 接近原始目标 |

报告必须写明实际命中题数，不得只写百分比。

#### pair_analysis gate

若 `pair_analysis_eligible_rate < 80%`，报告标记 `pair_analysis_underpowered=true`，3pp operational gate 降级为方向性指标，不得宣称通过。

---

## 20. 回滚与停止条件

| 条件 | 动作 |
|---|---|
| Task 0 基线测试不绿 | 停止，不进入 Phase 3 新功能。 |
| 找不到独立 final 40 题 | formal 降级 20 题并标记 underpowered。 |
| A1/A3/A4 permutation plan 不一致 | 停止，修共享 plan。 |
| 循环排列未使每个选项覆盖 3 个位置 | 停止，修循环移位实现。 |
| label 平衡不满足差值≤1或最大占比≤30% | 停止，修 dynamic render。 |
| dev20 没有候选达到 `candidate >= A1-agg` | 不进入 formal。 |
| confirmed strict leak 任一分母 > 0 | 停止，修泄漏。 |
| 达到 hard_call_cap | 停止并记录 call_cap_reached。 |
| final 后想继续调参 | 禁止；需新建 Phase 3.1 或重新划分 final_holdout。 |

---

## 21. 计划自审 checklist

- [x] off-control 已按 prompt 配置拆成 A1-off-3/A3-off-3/A4-off-3。
- [x] candidate 冻结条件允许 A1-agg，并有确定性 tie-break。
- [x] A1/A3/A4 复用同一 permutation plan。
- [x] 使用与 gold 无关的固定循环排列，不读取正确答案。
- [x] development consistency gate 可执行。
- [x] strict leak 区分 leak_candidate 与 confirmed，并定义分母和近重复阈值。
- [x] parser 分层报告 call-level / case-level / excluded。
- [x] 调用预算按实际矩阵重算：link8=144 / dev20=360 / MingLi20=60 / formal40=240 / formal20=120。
- [x] 达到 hard cap 后停止。
- [x] dev20 候选 23%≤x<28% 决策路径已定义，<23% 则 dev NO-GO。
- [x] formal20 使用整数题对应（5/20=operational pass，6/20=strong pass）。
- [x] few-shot 内容来源、质量审核和禁止复制 holdout 已定义。
- [x] Task 4 明确为纯函数级测试，不依赖 CLI，顺序正确。
- [x] 位置覆盖缺口已记录，4-permutation 作为可选 fallback。
- [x] pair_analysis_eligible_rate >= 80% gate 已加入，否则 3pp 降级。
- [x] MingLi runner 不支持 APB 时有首选/次选 fallback 路径。
