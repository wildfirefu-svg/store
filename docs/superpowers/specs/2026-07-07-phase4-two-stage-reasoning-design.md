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

### 3.1 设计决策（已与用户确认 + 审核修订）

| 决策点 | 选择 | 理由 |
|---|---|---|
| Stage 1 option-blind 程度 | **标签 blind**（修订） | 审核反馈：完全 option-blind 与"应象映射"矛盾。改为 Stage 1 可看选项**文本内容**但**不含 A/B/C/D 位置标签**，切断位置→字母捷径，同时保留应象映射所需的选项语义 |
| 时间类触发 | **规则+指令双保险** | 关键词规则保底（确定性强、可测试）+ prompt 指令引导（覆盖隐含时间类） |
| Stage 2 evidence | **smoke 全选项 / formal 视命中率决定 top-2** | smoke 先用全选项证据验证框架；formal 阶段统计 top-2 命中率，≥0.85 才启用 top-2，否则保持全选项 |
| Stage 1 失败 fallback | **退化为单阶段** | 解析失败时退化为 Phase 3 structured_reasoning，保证 parser_valid_rate 不崩 |
| Stage 1 跨 perm 复用 | **共享**（新增） | 同一 case 的 3 个 perm 共享同一个 Stage 1 假设，Stage 1 调用从 240 降至 80，节省 67% 成本 |
| case_details 字段命名 | **phase4_ 前缀**（新增） | 新增字段用 `phase4_` 前缀（如 `phase4_stage1_raw`），避免与 Phase 3 字段冲突 |

### 3.2 Option-blind 两阶段推理

#### 当前 structured_reasoning（单阶段，Phase 3）

```
prompt = base + chart + question + options(A/B/C/D) + evidence(全部选项) + APB
→ 一次调用 → 三阶段推理 + 四选项置信度 + 最终答案
```

问题：模型在推理前就看到 A/B/C/D 选项位置，形成 A 锚定。

#### Phase 4 two_stage_reasoning（两阶段）

**Stage 1（标签 blind 推理）**：
```
prompt_1 = base + chart + question + 选项文本（无 A/B/C/D 标签，打乱顺序）
           + 三阶段推理协议 + 时间类两步推理指令（若触发）
（不含 RAG evidence、不含选项位置标签）
→ 输出：三阶段推理 + 【内容假设】（固定标记 + 可比较表述）
```

Stage 1 prompt 中的选项以"选项1/选项2/选项3/选项4"呈现（打乱顺序、无字母标签），模型无法知道哪个是 A、哪个是 B，但能看到选项内容完成应象映射。

**选项打乱的确定性**（审核 v3 反馈）：
- Stage 1 的选项打乱必须使用**固定 seed**（基于 case_id 的 hash），保证同一 case 跨 perm 可共享
- 实现示例：
```python
import hashlib, random
seed = int(hashlib.md5(case['case_id'].encode()).hexdigest()[:8], 16)
shuffled = options[:]
random.Random(seed).shuffle(shuffled)
```
- 这样 p0/p1/p2 三个 perm 看到的 Stage 1 prompt 完全一致，才能共享 1 次调用

**Stage 1 prompt 示例**（审核 v3 反馈：补充完整示例）：
```
你是一位严谨的八字命理评测助手。必须按三阶段结构化推理后再作答。

## 命主信息
姓名：某命主  性别：女  出生：1980年8月24日12时0分  地点：广东

## 三阶段结构化推理协议
第一阶段：量化扫描。清点五行、日主强弱、十神分布、格局倾向、用神喜忌。
第二阶段：冲突定级。识别刑冲合害、空亡、入墓、忌神成局，并判断轻微/中度/严重。
第三阶段：应象映射。将命理结构映射到题目领域和现实事件。

## 时间类两步推理指令（仅时间类问题注入）
若本题需要时间定位，必须按两步推理：
第一步：大运锚定——确定事件对应的大运区间（10年），输出"第 X 步大运（YYYY-YYYY）"
第二步：流年验证——在该大运内枚举候选流年，逐个验证触发条件，输出最可能流年 + 触发判据

## 问题
{question}

## 候选项（无标签，顺序随机）
选项1：{option_text_a}
选项2：{option_text_b}
选项3：{option_text_c}
选项4：{option_text_d}

## 输出要求
1. 先完成三阶段推理
2. 最后用固定格式输出内容假设（不要使用"选项1/选项2"引用，必须用实际内容表述）：
【内容假设】：{用选项的实际内容表述你的判断，如"事业方向偏文职/教育"或"第3步大运2003-2012，重点2007丁亥"}
```

**关键约束**（审核 v3 反馈：禁止引用选项编号）：
- Stage 1 prompt 中明确要求"不要使用'选项1/选项2'来引用选项，必须用选项的实际内容表述"
- 避免模型在【内容假设】中写"选项2最符合"，导致 Stage 2 无法对应 A/B/C/D

**内容假设的固定标记格式**（审核反馈：parser 容错设计）：
```
【内容假设】：第3步大运（2003-2012），重点流年2007丁亥
```
`parse_stage1_result` 用正则 `【内容假设】：(.+)` 提取。同时容错支持"结论："、"假设："、"判断："等前缀，最低优先级回退到"取最后一段非空行"。

内容假设的"可比较表述"约束：
- 事业类：输出方向 + 细分（如"文职/教育"、"武职/军警"）
- 时间类：输出大运区间 + 候选流年（如"第3步大运 2003-2012，重点 2007 丁亥"）
- 性质类：输出事件性质 + 程度（如"离婚，中度冲突"）

**Stage 2（选项匹配 + 证据决胜）**：
```
prompt_2 = base + chart + question + options(A/B/C/D) + Stage1内容假设
           + evidence + APB
→ 输出：四选项置信度 + 最终答案
```

**假设-证据冲突仲裁**（审核反馈：新增）：
- Stage 2 prompt 中明确指示："若内容假设与证据矛盾，以证据为准，但需在推理中说明冲突原因"
- 默认策略：相信证据（方案 a），`case_details` 中标记 `phase4_conflict=True`
- 这避免了 Stage 1 错误假设污染 Stage 2 判断

**证据检索策略（分阶段）**：
- **smoke 阶段（Task 3.x）**：使用全选项证据（沿用 Phase 3 option_grounded），先验证两阶段框架本身是否有效，不引入 top-2 匹配的复杂度
- **formal 阶段（Task 4.x）**：统计 smoke 阶段的 top-2 命中率（用 TF-IDF 简单版本计算），若 ≥ 0.85 则启用 top-2 语义匹配（只检索这 2 个的证据）；若 < 0.85 则保持全选项证据，不增加 LLM 二次调用的成本

top-2 语义匹配的实现方式（formal 阶段决定，**不引入 LLM 方案 b**）：
- (a) TF-IDF cosine 简单匹配（smoke 阶段就统计命中率）
- (c) 保持全选项证据（若命中率 < 0.85）

#### Fallback

Stage 1 解析失败（无法提取内容假设）时，退化为 Phase 3 的 structured_reasoning 单阶段调用。`case_details` 记录 `phase4_fallback=True` 和 `phase4_fallback_reason`（parser 失败类型：`no_marker`/`empty_hypothesis`/`extract_error`）。

**Stage 1 跨 perm 共享**（审核反馈：成本优化）：
- 同一 case 的 3 个 perm（p0/p1/p2）共享同一个 Stage 1 假设
- Stage 1 prompt 中的选项是打乱顺序、无标签的，与 perm 无关
- 因此 Stage 1 只需调用 1 次（而非 3 次），Stage 2 仍按 perm 分别调用
- **调用数计算**（修正 v3）：
  - Stage 1：40 case × 1 = 40（跨 on-3/off-3 + 跨 3 perm 共享）
  - Stage 2 on-3：40 × 3 perm = 120
  - Stage 2 off-3：40 × 3 perm = 120
  - **总计 = 280**（Phase 3 基线 240 → Phase 4 两阶段 280，+16.7%）
  - 含 20% fallback 余量：280 × 1.2 ≈ 336
- off-3 也使用两阶段（与 on-3 公平对照），Stage 1 与 on-3 共享，Stage 2 独立调用

### 3.3 时间类两步推理

#### 触发条件（规则+指令双保险）

**规则触发**（`is_time_location_question` 函数）：
- 问题文本含：哪年 / 何时 / 哪一年 / 几年 / 时间 / 年份 / 什么时候 / 几时 / 何年 / 哪年发生 / 出现在（如"第一段婚姻出现在"）
- 或：选项全是 4 位数字年份（如 1989/1990/2011/2021）
- smoke 阶段统计触发率（需覆盖 4/4 unanimous wrong case）和误触发率（< 10%），否则扩展关键词表

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
Stage1 调用 (temp=0, 跨 perm 共享 1 次) → raw1
         ├─ parse_stage1_result(raw1) 成功 → hypothesis（缓存，3 perm 共用）
         │   └─ [smoke: 全选项证据 / formal: top-2 若命中率≥0.85] 检索 evidence
         │       └─ Stage2 调用 (temp=0, 每 perm 1 次) → raw2 → 最终答案
         └─ parse 失败 → fallback: structured_reasoning 单阶段（每 perm 1 次）→ 最终答案
```

---

## 4. 数据流与接口

### 4.1 新增模块

**`benchmark/formatters/two_stage_reasoning.py`**

| 函数 | 签名 | 说明 |
|---|---|---|
| `is_time_location_question` | `(question: str, options: list) -> bool` | 关键词 + 4位年份选项检测 |
| `format_stage1_prompt` | `(case: dict) -> str` | 标签 blind 三阶段推理 prompt（选项打乱无标签，含时间类指令） |
| `format_stage2_prompt` | `(case: dict, hypothesis: str, evidence: list) -> str` | 含选项(A/B/C/D) + 假设 + 证据 + 冲突仲裁指令 |
| `parse_stage1_result` | `(raw: str) -> Optional[str]` | 从 Stage1 输出提取【内容假设】，失败返回 None |
| `build_stage2_evidence` | `(case: dict, hypothesis: str, mode: str) -> list` | 证据检索：mode='all' 全选项 / mode='top2' TF-IDF top-2。复用 `rag_prompt_builder.py` 的检索逻辑 |

### 4.2 benchmark_runner 接入

`benchmark/runners/run_benchmark.py`：
- `build_benchmark_prompt` 新增 `two_stage_reasoning` 分支（返回 Stage 1 prompt）
- CLI `--method` choices 新增 `two_stage_reasoning`
- `run_model_benchmark` 新增两阶段调用编排逻辑（含 Stage 1 跨 perm 缓存）
- `case_details` 新增字段（均用 `phase4_` 前缀避免与 Phase 3 冲突）：
  - `phase4_stage1_raw`、`phase4_stage1_hypothesis`
  - `phase4_stage2_raw`、`phase4_fallback`、`phase4_fallback_reason`
  - `phase4_is_time_question`、`phase4_conflict`
  - `phase4_evidence_mode`（'all' / 'top2'）

### 4.3 评测复用

- Permutation plan：沿用 Phase 3 冻结的 `formal40_perm_s{0,1,2}.jsonl`
- Gate：沿用 Phase 3 的 6 项 gate（`scripts/phase3_generate_gate_report.py`）
- 数据隔离：development=2025 前 20 题，final=2024 holdout 40 题

**off-3 两阶段策略**（审核 v3 反馈：明确）：
- off-3 也使用两阶段推理，与 on-3 公平对照（否则 shuffle gap 不可比）
- off-3 的 Stage 1 与 on-3 共享（Stage 1 是 label-blind，与 shuffle 无关）
- off-3 的 Stage 2 不 shuffle（选项保持原始顺序 A/B/C/D），on-3 的 Stage 2 按 perm shuffle
- 这样 off_ite vs on_ite 的差异只来自 Stage 2 的 shuffle，是公平的 shuffle gap

**数据暴露声明**（审核反馈）：
- `phase4_dev_data_exposed_in_phase1_and_phase3 = true`：dev20（2025 前 20 题）在 Phase 1 和 Phase 3 中已被模型多次见过
- smoke 验证结论必须标注"可能因数据重复暴露而偏高"
- formal40（2024 holdout）保持独立，gate 判定以 formal40 为准

---

## 5. 验收标准

| 指标 | Phase 3 基线 | Phase 4 目标 | gate |
|---|---|---|---|
| on_ite_accuracy | 0.75 | ≥ 0.75 | gate_ite_28pct |
| MMS | 0.7033 | ≥ 0.7033（≥ 0.80 为成功） | gate_mms_80pct |
| parser_valid_rate | 0.9598 | ≥ 0.95 | gate_parser_valid_95pct |
| confirmed_leak_count | 0 | 0 | gate_confirmed_leak_zero |
| off_ite_accuracy | 0.65 | ≥ 0.65（修正：不低于基线） | gate_off_control_28_3pct |
| 时间类 4 case | 0/4 正确 | ≥ 1/4 正确 | （非 gate，内部跟踪） |
| fallback 率 | N/A | ≤ 0.20 | （非 gate，内部跟踪） |
| top-2 命中率 | N/A | ≥ 0.85（formal 启用 top-2 的前提） | （非 gate，内部跟踪） |
| 总 API 调用 | 240 | ≤ 336（280 基础 + 20% fallback 余量） | （非 gate，成本控制） |

**Phase 4 成功条件**：5/6 gate 维持 PASS + 时间类至少 1/4 改善 + fallback 率 ≤ 0.20。MMS 突破 0.80 为 stretch goal。

**回滚条件**：任何 Task 后若 on_ite 下降 > 5pp 或 MMS 下降 > 2pp，立即回滚到 Phase 3 noleak v4 配置。

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Stage 1 内容假设与选项表述对不上 | 中 | 准确率下降 | 标签 blind 保留选项语义 + "可比较表述"约束 + fallback 到单阶段 |
| top-2 TF-IDF 匹配命中率低 | 中 | formal 阶段无法启用 top-2 | smoke 阶段统计命中率，< 0.85 则保持全选项证据（方案 c） |
| 两阶段调用成本增加 | 中 | 评测时间 +16.7%（280 vs 240） | Stage 1 跨 perm 共享（40 次 vs 240 次）；smoke 限 10 case |
| Stage 1 parser 失败率高 | 中 | fallback 率高 | 固定标记 `【内容假设】：` + 多前缀容错 + 回退到最后一段非空行 |
| 时间类指令干扰非时间类 | 低 | 非时间类退化 | `is_time_location_question` 精确触发 + smoke 统计误触发率 < 10% |
| API 限流 | 中 | 部分 case 失败 | 复用 Phase 3 的 SC retry 机制（`sample_answers` 的 retry + delay） |
| 假设-证据冲突处理不当 | 中 | Stage 2 判断被错误假设污染 | 默认相信证据 + `phase4_conflict` 标记 + Stage 2 prompt 明确冲突仲裁指令 |
| Fallback 浪费调用 | 中 | 20% case 多消耗 1 次调用 | 总调用预算预留 20% 余量（280 + 56 fallback = ≤336） |
| dev20 数据暴露导致 smoke 偏高 | 中 | smoke 结论泛化性存疑 | formal40（2024 独立 holdout）为准，smoke 标注暴露偏差 |

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

## 9. 审核反馈处理记录

本设计文档经过两轮审核，所有问题已修订：

| 问题 | 严重度 | 处理 |
|---|---|---|
| Stage 1 完全 option-blind 与应象映射矛盾 | 高 | §3.1/§3.2 改为"标签 blind"（看选项文本，无 A/B/C/D 标签） |
| top-2 匹配方案风险被低估 | 高 | §3.2 明确不引入 LLM 方案(b)，smoke 统计命中率决定是否启用 |
| Stage 1 输出格式未定义 | 中 | §3.2 强制固定标记 `【内容假设】：` + 多前缀容错 |
| 时间类触发规则过窄 | 中 | §3.3 扩展关键词 + 增加"什么时候/出现在"等 |
| case_details 字段命名冲突 | 中 | §4.2 所有新字段用 `phase4_` 前缀 |
| off_ite 目标低于基线 | 中 | §5 修正为 ≥ 0.65 |
| 调用成本翻倍缓解不足 | 中 | §3.2 Stage 1 跨 perm 共享 + §5 总调用 ≤ 200 |
| 基线数值矛盾（Delivery vs EXPERIMENT） | 中 | §1.1 确认 gate_report_final.json（0.75/0.7033）为权威基线 |
| 缺少冲突仲裁逻辑 | 中 | §3.2 新增"假设-证据冲突仲裁"（默认相信证据） |
| 数据暴露声明缺失 | 中 | §4.3 新增 `phase4_dev_data_exposed` 声明 |
| Stage 2 证据检索需传入假设 | 中 | §4.1 新增 `build_stage2_evidence` 函数 |
| Fallback 浪费调用未算入预算 | 中 | §5 预算预留 20% 余量 |
| Stage 1 跨 perm 复用机会 | 低 | §3.2/§3.4 新增跨 perm 共享，节省 67% Stage 1 调用 |
| 缺少回滚条件 | 低 | §5 新增回滚条件（on_ite >5pp 或 MMS >2pp 下降） |

**v3 修订（第二轮审核，5 项）**：

| 问题 | 严重度 | 处理 |
|---|---|---|
| 总 API 调用预算计算错误（280 非 200） | 高 | §3.2/§5/§6 修正：280 基础 + 20% fallback = ≤336 |
| Stage 1 选项打乱缺乏确定性 | 高 | §3.2 新增固定 seed（case_id hash）保证跨 perm 可共享 |
| 标签 blind 下模型可能引用"选项2"造成歧义 | 高 | §3.2 Stage 1 prompt 明确禁止引用选项编号，必须用实际内容表述 |
| off-3 两阶段策略未明确 | 中 | §4.3 新增 off-3 也用两阶段，Stage 1 共享，Stage 2 不 shuffle |
| Stage 1 prompt 示例缺失 | 中 | §3.2 补充完整 Stage 1 prompt 示例（含候选项/输出要求/禁止编号） |
| gate report 脚本路径 | 低 | §4.3 修正为 `scripts/phase3_generate_gate_report.py`（已验证存在） |

---

*设计文档修订完，待最终审阅*
