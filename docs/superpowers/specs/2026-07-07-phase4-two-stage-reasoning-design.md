# Phase 4 · 两阶段推理 + 时间类攻坚 设计文档

- **日期**: 2026-07-07
- **作者**: TRAE Agent
- **状态**: 设计待审阅，未进入实施
- **对应总设计**: [2026-07-01-accuracy-improvement-design.md](file:///f:/project/agent/docs/superpowers/specs/2026-07-01-accuracy-improvement-design.md)
- **前置状态**:
  - Phase 1: Done / Baseline Archived
  - Phase 2: Engineering Done / Evaluation NO-GO
  - Phase 3: formal40 A4 完成，5/6 gate PASS（仅 `gate_mms_80pct` FAIL @ 0.7033）
- **对应实施计划**: [plans/2026-07-07-phase4-two-stage-reasoning.md](file:///f:/project/agent/docs/superpowers/plans/2026-07-07-phase4-two-stage-reasoning.md)

---

## 1. 背景

### 1.1 Phase 3 遗留问题

Phase 3 formal40 A4 达成 5/6 gate PASS，两项未解决：

1. **MMS 天花板**：`gate_mms_80pct` 0.7033 < 0.80。经 6 条路径穷尽验证（APB 强化、增加 perm、fewshot 修复、Self-Consistency、换 pro 模型），确认是 deepseek-v4-flash 的系统性位置偏好。**根因**：选项在推理前展示，模型形成 A 位置锚定（p2 A 偏好 50%）。

2. **4 个 unanimous wrong case 全是时间定位类**：P002-Q9（母亲离世年份）、P003-Q13（官非刑事时间）、P004-Q17（第一段婚姻）、P005-Q22（登记离婚年份）。**根因**：模型在"大运→流年"下钻步骤缺失，靠选项字面联想猜答案。

### 1.2 Phase 4 的定位

Phase 3 证明了"位置偏差已压制、但模型推理一致性遇天花板"。Phase 4 是突破天花板的第一跳——从"单阶段看证据作答"转向"先独立推理再查证据"，并针对性攻击时间类问题。

### 1.3 与 Phase 3 失败路径的关系

Phase 4 的两个方向都是 Phase 3 **未尝试**的（非重复失败路径）：
- Option-blind 两阶段推理：Phase 3 因实现成本高未做，是 MMS 的最大理论杠杆
- 时间类两步推理：Phase 3 未做，是命理领域专家建议的最具体攻击点

Phase 3 已确认无效的方向（APB 强化、增加 perm、fewshot、SC、换 pro 模型），Phase 4 **不再尝试**。

---

## 2. 目标与非目标

### 2.1 目标

- **目标 A（MMS 突破）**：通过完全 option-blind 两阶段推理，切断"位置→字母"捷径。Stage 1 不含选项，只输出内容假设；Stage 2 用内容假设匹配选项 + top-2 证据决胜。
- **目标 B（准确率提升）**：通过时间类两步推理，强制"先定大运区间，再枚举流年验证触发条件"，攻击 4 个 unanimous wrong case。
- **目标 C（不退化）**：维持 Phase 3 已达成的 5/6 gate PASS。MMS ≥ 0.7033，ITE ≥ 0.75。

### 2.2 非目标

- 不做 RAG 证据对齐（流年触发判据知识库）——属 Phase 5 范畴
- 不做 Contextual Calibration —— 需先做 feasibility 验证
- 不做置信度淘汰制 —— 作为 Phase 4 之后的并行实验臂候选，本轮不纳入
- 不重复 Phase 3 已证无效的方向（见 §1.3）

---

## 3. 核心设计

### 3.1 设计决策（已与用户确认）

| 决策点 | 选择 | 理由 |
|---|---|---|
| Stage 1 option-blind 程度 | **完全 option-blind** | MMS 杠杆最大；Stage 1 不含 A/B/C/D 选项文本，只输出"可比较表述"的内容假设 |
| 时间类触发 | **规则+指令双保险** | 关键词规则保底（确定性强、可测试）+ prompt 指令引导（覆盖隐含时间类） |
| Stage 2 evidence | **top-2 证据** | Stage 1 内容假设语义匹配选 top-2 选项，只检索这 2 个的证据，减少噪声 |
| Stage 1 失败 fallback | **退化为单阶段** | 解析失败时退化为 Phase 3 structured_reasoning，保证 parser_valid_rate 不崩 |

### 3.2 Option-blind 两阶段推理

#### 当前 structured_reasoning（单阶段，Phase 3）

```
prompt = base + chart + question + options(A/B/C/D) + evidence(全部选项) + APB
→ 一次调用 → 三阶段推理 + 四选项置信度 + 最终答案
```

问题：模型在推理前就看到 A/B/C/D 选项位置，形成 A 锚定。

#### Phase 4 two_stage_reasoning（两阶段）

**Stage 1（option-blind 推理）**：
```
prompt_1 = base + chart + question + 三阶段推理协议 + 时间类两步推理指令（若触发）
（不含选项、不含 evidence）
→ 输出：三阶段推理 + "内容假设"（可比较的具体表述）
```

内容假设的"可比较表述"约束（关键）：
- 事业类：输出方向 + 细分（如"文职/教育"、"武职/军警"），而非抽象命理术语
- 时间类：输出大运区间 + 候选流年（如"第3步大运 2003-2012，重点 2007 丁亥"）
- 性质类：输出事件性质 + 程度（如"离婚，中度冲突"）

**Stage 2（选项匹配 + 证据决胜）**：
```
prompt_2 = base + chart + question + options(A/B/C/D) + Stage1内容假设
           + evidence + APB
→ 输出：四选项置信度 + 最终答案
```

**证据检索策略（分阶段）**：
- **smoke 阶段（Task 3.x）**：使用全选项证据（沿用 Phase 3 option_grounded），先验证两阶段框架本身是否有效，不引入 top-2 匹配的复杂度
- **formal 阶段（Task 4.x）**：若 smoke 验证框架有效，再启用 top-2 语义匹配（Stage 1 内容假设 → 选最接近的 2 个选项 → 只检索这 2 个的证据，减少噪声）；若 smoke 显示 top-2 风险高，则保持全选项证据

top-2 语义匹配的候选实现方式（formal 阶段决定）：
- (a) 简单关键词重叠（TF-IDF cosine）
- (b) LLM 二次调用让模型自己选 top-2（增加 1 次调用）
- (c) 保持全选项证据（放弃 top-2，简化实现）

#### Fallback

Stage 1 解析失败（无法提取内容假设）时，退化为 Phase 3 的 structured_reasoning 单阶段调用。`case_details` 记录 `fallback=True`。

### 3.3 时间类两步推理

#### 触发条件（规则+指令双保险）

**规则触发**（`is_time_location_question` 函数）：
- 问题文本含：哪年 / 何时 / 哪一年 / 几年 / 时间 / 年份
- 或：选项全是 4 位数字年份（如 1989/1990/2011/2021）

**指令引导**（注入 Stage 1 prompt）：
> 若本题需要时间定位（如"哪年发生某事"），必须按两步推理：
> 第一步：大运锚定——确定事件对应的大运区间（10年），输出"第 X 步大运（YYYY-YYYY）"
> 第二步：流年验证——在该大运内枚举候选流年，逐个验证触发条件（冲合/十神/神煞），输出最可能流年 + 触发判据

#### 命理依据

大运定区间是高置信步骤，流年定具体是低置信步骤。分开避免"一步错步步错"。

#### 与 Option-blind 的叠加

时间类两步推理指令注入 Stage 1 的三阶段协议中（作为"第三阶段：应象映射"的细化），Stage 2 不变。

### 3.4 调用流程图

```
case → is_time_location_question?
         ├─ yes → Stage1 prompt 含两步推理指令
         └─ no  → Stage1 prompt 标准三阶段
Stage1 调用 (temp=0) → raw1
         ├─ parse_stage1_result(raw1) 成功 → hypothesis
         │   └─ [smoke: 全选项证据 / formal: top-2 证据] 检索 evidence
         │       └─ Stage2 调用 (temp=0) → raw2 → 最终答案
         └─ parse 失败 → fallback: structured_reasoning 单阶段 → 最终答案
```

---

## 4. 数据流与接口

### 4.1 新增模块

**`benchmark/formatters/two_stage_reasoning.py`**

| 函数 | 签名 | 说明 |
|---|---|---|
| `is_time_location_question` | `(question: str, options: list) -> bool` | 关键词 + 4位年份选项检测 |
| `format_stage1_prompt` | `(case: dict) -> str` | 不含选项的三阶段推理 prompt（含时间类指令） |
| `format_stage2_prompt` | `(case: dict, hypothesis: str, top2_options: list, evidence: list) -> str` | 含选项 + 假设 + top-2 证据 |
| `parse_stage1_result` | `(raw: str) -> Optional[str]` | 从 Stage1 输出提取内容假设，失败返回 None |

### 4.2 benchmark_runner 接入

`benchmark/runners/run_benchmark.py`：
- `build_benchmark_prompt` 新增 `two_stage_reasoning` 分支（返回 Stage 1 prompt）
- CLI `--method` choices 新增 `two_stage_reasoning`
- `run_model_benchmark` 新增两阶段调用编排逻辑
- `case_details` 新增字段：`stage1_raw`、`stage1_hypothesis`、`stage2_raw`、`fallback`、`is_time_question`

### 4.3 评测复用

- Permutation plan：沿用 Phase 3 冻结的 `formal40_perm_s{0,1,2}.jsonl`
- Gate：沿用 Phase 3 的 6 项 gate（`phase3_generate_gate_report.py`）
- 数据隔离：development=2025 前 20 题，final=2024 holdout 40 题

---

## 5. 验收标准

| 指标 | Phase 3 基线 | Phase 4 目标 | gate |
|---|---|---|---|
| on_ite_accuracy | 0.75 | ≥ 0.75 | gate_ite_28pct |
| MMS | 0.7033 | ≥ 0.7033（≥ 0.80 为成功） | gate_mms_80pct |
| parser_valid_rate | 0.9598 | ≥ 0.95 | gate_parser_valid_95pct |
| confirmed_leak_count | 0 | 0 | gate_confirmed_leak_zero |
| off_ite_accuracy | 0.65 | ≥ 0.283 | gate_off_control_28_3pct |
| 时间类 4 case | 0/4 正确 | ≥ 1/4 正确 | （非 gate，内部跟踪） |
| fallback 率 | N/A | ≤ 0.20 | （非 gate，内部跟踪） |

**Phase 4 成功条件**：5/6 gate 维持 PASS + 时间类至少 1/4 改善 + fallback 率 ≤ 0.20。MMS 突破 0.80 为 stretch goal。

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Stage 1 内容假设与选项表述对不上 | 中 | 准确率下降 | 强制"可比较表述"约束 + fallback 到单阶段 |
| top-2 语义匹配选错（正确选项不在 top-2） | 中 | 准确率上限被限 | smoke 阶段统计 top-2 命中率，若 < 0.85 则回退全选项证据 |
| 两阶段调用成本翻倍 | 高 | 评测时间 2x | 接受（评测场景可承受）；复用 Phase 3 SC retry 机制防 API 限流 |
| Stage 1 parser 失败率高 | 中 | fallback 率高 | smoke 阶段验证，若 fallback > 0.20 则优化 parser 或调整 Stage 1 prompt |
| 时间类指令干扰非时间类 | 低 | 非时间类退化 | `is_time_location_question` 精确触发，非时间类不注入两步指令 |
| API 限流（2x 调用） | 中 | 部分 case 失败 | 复用 Phase 3 的 SC retry 机制（`sample_answers` 的 retry + delay） |

---

## 7. 不做的事（明确排除）

基于 Phase 3 失败路径归因（[PHASE3_FORMAL40_A4_DELIVERY_REPORT.md](file:///f:/project/agent/docs/PHASE3_FORMAL40_A4_DELIVERY_REPORT.md) §5）：

- 不启用 fewshot（Phase 3 已证退化 20-27pp）
- 不用 Self-Consistency（Phase 3 已证 temp 噪声 + bias 放大）
- 不换 pro 模型（Phase 3 已证流派不匹配，-42.5pp）
- 不强化 APB 指令（Phase 3 已证无效）
- 不增加 perm 数量（Phase 3 已证 3→4 反而 -1.5pp）
- 不做 RAG 证据对齐（属 Phase 5）
- 不做 Contextual Calibration（需先 feasibility 验证）
- 不做置信度淘汰制（本轮不纳入，留作后续并行实验臂）

---

## 8. 实施阶段（概要）

详见实施计划 [plans/2026-07-07-phase4-two-stage-reasoning.md](file:///f:/project/agent/docs/superpowers/plans/2026-07-07-phase4-two-stage-reasoning.md)。

1. **基础设施（TDD）**：formatter 测试 → 实现 → 接入 runner
2. **调用链**：两阶段编排 + fallback + 集成测试
3. **smoke 验证**：10 case development + 时间类 4 case 专项
4. **formal40 评测**：on-3/off-3 × 3 perm + gate report
5. **交付**：报告 + 提交

---

## 9. 待审阅决策点

本设计文档已确认 4 个核心决策（§3.1）。审阅时请重点关注：

1. **证据检索的分阶段策略**（已在 §3.2 明确）：smoke 阶段用全选项证据验证框架，formal 阶段再决定是否启用 top-2 精细化。这避免了"top-2 匹配实现复杂度"与"两阶段框架验证"耦合，降低初期风险。

2. **Stage 1 内容假设的输出格式**：是否需要强制结构化（如 JSON `{"domain": "...", "hypothesis": "...", "confidence": "..."}`）？还是自由文本 + parser 提取？
   
   **建议**：自由文本 + parser 提取（`parse_stage1_result` 容错），避免 JSON 解析失败拉高 fallback 率。parser 通过提取"内容假设："或"结论："后的文本来获取假设。

---

*设计文档完，待审阅*
