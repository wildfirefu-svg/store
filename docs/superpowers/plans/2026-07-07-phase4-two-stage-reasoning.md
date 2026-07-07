# Phase 4 实施计划：两阶段推理 + 时间类攻坚

> 日期：2026-07-07
> 前置：Phase 3 formal40 A4 已完成（5/6 gate PASS，commit `ff632dc`/`d208037`/`793e2cb`）
> 范围：核心（Option-blind 两阶段推理）+ 时间类攻坚（两步推理）
> 预估：3-5 天（参照原设计文档 [accuracy-improvement-design.md:145-156](file:///f:/project/agent/docs/superpowers/specs/2026-07-01-accuracy-improvement-design.md)）

---

## 1. 背景与动机

### 1.1 Phase 3 遗留问题

Phase 3 formal40 A4 达成 5/6 gate PASS，但有两项未解决：

1. **MMS 天花板**：`gate_mms_80pct` 0.7033 < 0.80。经 6 条路径穷尽验证，确认是 deepseek-v4-flash 模型的系统性位置偏好，prompt/fewshot/SC/换模型均无法修复。**根因**：选项在推理前展示，模型形成 A 位置锚定。

2. **4 个 unanimous wrong case 全是时间定位类**：
   - P002-Q9（母亲哪年离世）
   - P003-Q13（官非刑事时间）
   - P004-Q17（第一段婚姻何时）
   - P005-Q22（哪年登记离婚）
   
   **根因**：模型在"大运→流年"下钻步骤缺失，靠选项字面联想猜答案。

### 1.2 Phase 4 的目标

- **目标 A（MMS 突破）**：通过 Option-blind 两阶段推理，让模型先独立推理形成内容假设，再看选项匹配，切断"位置→字母"捷径。这是 Phase 3 交付报告 §7 方向 1，也是 MMS 的最大理论杠杆。
- **目标 B（准确率提升）**：通过时间类两步推理，强制"先定大运区间，再枚举流年验证触发条件"，攻击 4 个 unanimous wrong case。这是 Phase 3 交付报告 §7 方向 3。
- **目标 C（不退化）**：Phase 4 不得退化 Phase 3 已达成的 5/6 gate。MMS 即使无法突破 80%，也不能低于 70.4%；ITE 不能低于 0.75。

### 1.3 与 Phase 3 失败路径的关系

Phase 4 的两个方向都是 Phase 3 **未尝试**的（不是重复失败路径）：
- Option-blind 是 Prompt 架构专家建议的 MMS 最大杠杆，Phase 3 因实现成本高未做
- 时间类两步推理是命理领域专家建议的准确率攻击点，Phase 3 未做

Phase 3 已确认无效的方向（APB 强化、增加 perm、fewshot、SC、换 pro 模型），Phase 4 **不再尝试**。

---

## 2. 设计

### 2.1 Option-blind 两阶段推理

#### 当前 structured_reasoning（单阶段）

```
prompt = base + chart + question + options + evidence(全部选项) + APB
→ 一次调用 → 输出三阶段推理 + 四选项置信度 + 最终答案
```

问题：模型在推理前就看到 A/B/C/D 选项位置，形成锚定。

#### Phase 4 two_stage_reasoning（两阶段）

**Stage 1（option-blind 推理）**：
```
prompt_1 = base + chart + question + 三阶段推理协议 + 时间类两步推理指令
（不含选项、不含 evidence）
→ 输出：三阶段推理 + "内容假设"（用可比较的具体表述）
```

关键约束：Stage 1 必须要求"可比较表述"（如"日主丙火偏弱，用神取印比，事业方向偏文职/教育"），否则命理语言和选项表述对不上，匹配失败反而降准确率。

**Stage 2（选项匹配 + 证据决胜）**：
```
prompt_2 = base + chart + question + options(A/B/C/D) + Stage1推理结果 + evidence(top-2 only) + APB
→ 输出：四选项置信度 + 最终答案
```

关键约束：Stage 2 只对 Stage 1 的 top-2 候选检索 evidence，减少证据噪声。

#### Fallback

Stage 1 解析失败（无法提取内容假设）时，退化为单阶段 structured_reasoning，保证不崩。

### 2.2 时间类两步推理

#### 问题识别

对"哪年/何时"类问题，强制两步输出：

```
第一步：大运锚定
  - 确定事件对应的大运区间（10年，高置信）
  - 输出：事件发生在第 X 步大运（YYYY-YYYY）

第二步：流年验证
  - 在该大运区间内枚举候选流年
  - 逐个验证触发条件（冲合/十神/神煞）
  - 输出：最可能的具体流年 + 触发判据
```

#### 触发条件

问题文本包含以下关键词时触发：
- "哪年"、"何时"、"哪一年"、"几年"
- "时间"、"年份"
- 选项全是 4 位数字年份（如 1989/1990/2011/2021）

#### 命理依据

大运定区间是高置信步骤，流年定具体是低置信步骤。分开避免"一步错步步错"。

### 2.3 两者的叠加关系

Option-blind（2.1）和时间类两步推理（2.2）正交，可叠加：
- Stage 1 的三阶段推理协议中，对时间类问题注入"两步推理"指令
- Stage 2 不变（选项匹配 + 证据决胜）

---

## 3. 任务分解

### 阶段 1：基础设施（TDD）

#### Task 1.1：编写 two_stage_reasoning formatter 测试

- 文件：`tests/test_two_stage_reasoning.py`
- 测试内容：
  - `format_stage1_prompt(case)` 不含选项文本
  - `format_stage1_prompt(case)` 对时间类问题注入两步推理指令
  - `format_stage2_prompt(case, stage1_result, top2_evidence)` 含选项 + Stage1 结果
  - `parse_stage1_result(raw)` 解析内容假设，失败返回 None
  - `is_time_location_question(question)` 正确识别时间类问题
- 预期：测试失败（实现未写）

#### Task 1.2：实现 two_stage_reasoning formatter

- 文件：`benchmark/formatters/two_stage_reasoning.py`
- 函数：
  - `format_stage1_prompt(case)` → str
  - `format_stage2_prompt(case, stage1_result, top2_options)` → str
  - `parse_stage1_result(raw)` → Optional[str]（内容假设）
  - `is_time_location_question(question, options)` → bool
- 预期：Task 1.1 测试通过

#### Task 1.3：接入 benchmark runner

- 文件：`benchmark/runners/run_benchmark.py`
- 改动：
  - `build_benchmark_prompt` 新增 `two_stage_reasoning` 分支（返回 Stage 1 prompt）
  - CLI `--method` choices 新增 `two_stage_reasoning`
  - `run_model_benchmark` 新增两阶段调用逻辑：Stage 1 调用 → 解析 → Stage 2 调用 → 最终答案
  - Stage 1 失败时 fallback 到 structured_reasoning
- 预期：`--method two_stage_reasoning` 可运行

### 阶段 2：Stage 1 → Stage 2 调用链

#### Task 2.1：实现两阶段调用编排

- 文件：`benchmark/runners/run_benchmark.py` 的 `run_model_benchmark`
- 逻辑：
  1. Stage 1：`call_model_sync(stage1_prompt, temperature=0.0)` → raw1
  2. `stage1_hypothesis = parse_stage1_result(raw1)`
  3. 若 hypothesis is None：fallback 到 structured_reasoning（单阶段）
  4. 否则：对 hypothesis 匹配的 top-2 选项检索 evidence
  5. Stage 2：`call_model_sync(stage2_prompt, temperature=0.0)` → raw2
  6. 最终答案从 raw2 解析
- `case_details` 记录 `stage1_raw`、`stage1_hypothesis`、`stage2_raw`、`fallback`

#### Task 2.2：编写调用链集成测试

- 文件：`tests/test_two_stage_reasoning.py` 追加
- 测试内容：
  - mock call_model_sync，验证两阶段调用顺序
  - Stage 1 返回无法解析的结果时，验证 fallback 路径
  - 时间类问题验证 Stage 1 prompt 含两步推理指令

### 阶段 3：smoke 验证

#### Task 3.1：10 case smoke（development 集）

- 数据：2025 前 20 题中的 10 题（Phase 3 development 集，不污染 2024 holdout）
- 命令：`--method two_stage_reasoning --max-cases 10`
- 验证：
  - parser_valid_rate ≥ 0.90
  - fallback 率 ≤ 0.20
  - 准确率不低于 structured_reasoning baseline（同 10 题）

#### Task 3.2：时间类问题专项 smoke

- 数据：4 个 unanimous wrong case（P002-Q9 / P003-Q13 / P004-Q17 / P005-Q22）
- 验证：
  - Stage 1 是否输出了大运区间 + 流年验证
  - 准确率是否提升（≥ 1/4 正确即有改善）

### 阶段 4：formal40 评测

#### Task 4.1：formal40 on-3 × 3 perm（two_stage_reasoning）

- 数据：2024 holdout 40 case，3 perm（p0/p1/p2）
- 配置：`--method two_stage_reasoning --apb-block --rag --rag-k 2 --retrieval-mode option_grounded --option-evidence-k 2`
- 输出：`formal40_A4_p4_on-3_p{0,1,2}.jsonl`

#### Task 4.2：formal40 off-3 × 3 perm（控制组）

- 同 Task 4.1 但 off 配置
- 输出：`formal40_A4_p4_off-3_p{0,1,2}.jsonl`

#### Task 4.3：生成 gate report

- 命令：`python scripts/phase3_generate_gate_report.py --stage formal40 --pred-dir .tmp/phase4 --output .tmp/phase4/gate_report_p4.json`
- 验证：
  - gate_ite_28pct：≥ 0.28（不退化）
  - gate_mms_80pct：是否突破 0.80？
  - 时间类 4 case 是否改善

### 阶段 5：交付

#### Task 5.1：撰写 Phase 4 交付报告

- 文件：`docs/PHASE4_DELIVERY_REPORT.md`
- 内容：gate 结果、两阶段推理效果、时间类攻坚效果、与 Phase 3 对比

#### Task 5.2：提交

- 小步提交：每个 Task 一个 commit
- 最终 commit 含报告

---

## 4. 验收标准

| 指标 | Phase 3 基线 | Phase 4 目标 | 说明 |
|---|---|---|---|
| on_ite_accuracy | 0.75 | ≥ 0.75 | 不退化 |
| MMS | 0.7033 | ≥ 0.7033（突破 0.80 为成功） | 不退化，突破为 bonus |
| gate_parser_valid_95pct | 0.9598 | ≥ 0.95 | 不退化 |
| confirmed_leak_count | 0 | 0 | 不退化 |
| 时间类 4 case | 0/4 正确 | ≥ 1/4 正确 | 准确率提升 |
| fallback 率 | N/A | ≤ 0.20 | 两阶段稳定性 |

**Phase 4 成功条件**：5/6 gate 维持 PASS + 时间类至少 1/4 改善。MMS 突破 80% 为 stretch goal。

---

## 5. 风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| Stage 1 内容假设与选项表述对不上 | 中 | 强制"可比较表述"约束 + fallback |
| 两阶段调用成本翻倍 | 高 | 接受（评测场景可承受） |
| Stage 1 parser 失败率高 | 中 | fallback 到 structured_reasoning |
| 时间类两步推理指令干扰非时间类 | 低 | `is_time_location_question` 精确触发 |
| API 限流（2x 调用） | 中 | 复用 Phase 3 的 SC retry 机制 |

---

## 6. 不做的事

- 不启用 fewshot（Phase 3 已证退化）
- 不用 Self-Consistency（Phase 3 已证退化）
- 不换 pro 模型（Phase 3 已证流派不匹配）
- 不强化 APB 指令（Phase 3 已证无效）
- 不增加 perm 数量（Phase 3 已证更差）
- 不做 RAG 证据对齐（属 Phase 5 范畴）
- 不做 Contextual Calibration（需先做 feasibility 验证）

---

## 7. 文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `benchmark/formatters/two_stage_reasoning.py` | 新增 | Stage1/Stage2 prompt formatter + parser |
| `benchmark/runners/run_benchmark.py` | 修改 | 接入 two_stage_reasoning method |
| `tests/test_two_stage_reasoning.py` | 新增 | 单元 + 集成测试 |
| `docs/superpowers/specs/2026-07-07-phase4-two-stage-reasoning-design.md` | 新增 | 本计划作为 spec |
| `docs/PHASE4_DELIVERY_REPORT.md` | 新增 | 最终交付报告 |

---

*计划完*
