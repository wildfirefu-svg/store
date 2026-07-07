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

**Stage 1（标签 blind 推理）**：
```
prompt_1 = base + chart + question + 选项文本（无 A/B/C/D 标签，打乱顺序）
           + 三阶段推理协议 + 时间类两步推理指令（若触发）
（不含 RAG evidence、不含选项位置标签）
→ 输出：三阶段推理 + 【内容假设】（固定标记 + 可比较表述）
```

关键约束：
- Stage 1 可看选项文本但不含 A/B/C/D 标签，切断位置→字母捷径，同时保留应象映射所需的选项语义
- 内容假设用固定标记 `【内容假设】：` 输出，parser 正则提取 + 多前缀容错
- "可比较表述"约束：事业类输出方向+细分，时间类输出大运区间+流年，性质类输出事件性质+程度
- Stage 1 跨 perm 共享：同一 case 的 3 个 perm 共用 1 次 Stage 1 调用

**Stage 2（选项匹配 + 证据决胜）**：
```
prompt_2 = base + chart + question + options(A/B/C/D) + Stage1内容假设
           + evidence + APB + 冲突仲裁指令
→ 输出：四选项置信度 + 最终答案
```

关键约束：
- 证据策略分阶段：smoke 用全选项证据，formal 视 top-2 命中率（≥0.85）决定是否启用 top-2
- 冲突仲裁：假设与证据矛盾时默认相信证据，标记 `phase4_conflict=True`

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

> 原则：每个步骤 2-5 分钟，TDD 红绿循环，小步提交。每个 ✅ 步骤产出可独立测试的变更。

### 阶段 1：formatter 基础设施（TDD）

#### Task 1.1：创建测试文件骨架（红）

- [ ] 创建 `tests/test_two_stage_reasoning.py`，编写 import 和 4 个测试桩（预期 import 失败）
  - `test_is_time_location_question_keywords`
  - `test_format_stage1_prompt_no_labels`
  - `test_parse_stage1_result_marker`
  - `test_build_stage2_evidence_all_mode`
- [ ] 运行 `pytest tests/test_two_stage_reasoning.py -q`，确认 4 个测试因 ImportError 失败（红）
- [ ] 提交：`test(phase4): add two-stage reasoning test scaffolding (red)`

#### Task 1.2：实现 is_time_location_question（绿-1）

- [ ] 创建 `benchmark/formatters/two_stage_reasoning.py`
- [ ] 实现 `is_time_location_question(question, options)`：关键词检测 + 4 位年份选项检测
  - 关键词：哪年/何时/哪一年/几年/时间/年份/什么时候/几时/何年/哪年发生/出现在
  - 4 位年份：选项文本全是 `\d{4}` 格式
- [ ] 完善 `test_is_time_location_question_keywords`：正向（含关键词）+ 负向（不含）+ 4 位年份选项
- [ ] 运行该测试，确认通过（绿）
- [ ] 提交：`feat(phase4): implement is_time_location_question detector`

#### Task 1.3：验证 4 个 unanimous wrong case 触发（绿-2）

- [ ] 在测试中加载 4 个 case（P002-Q9/P003-Q13/P004-Q17/P005-Q22），验证全部返回 True
- [ ] 若有 case 未触发，扩展关键词
- [ ] 运行测试，确认 4/4 通过
- [ ] 提交：`test(phase4): verify 4 unanimous wrong cases trigger time detection`

#### Task 1.4：实现 format_stage1_prompt（绿-3）

- [ ] 实现 `format_stage1_prompt(case)`：
  - 选项打乱（固定 seed = case_id hash）+ 无 A/B/C/D 标签
  - 三阶段协议 + 时间类两步推理指令（若触发）
  - 要求输出 `【内容假设】：` 固定标记
  - prompt 含"禁止引用选项编号"约束
- [ ] 完善 `test_format_stage1_prompt_no_labels`：
  - 断言不含 "A:"/"B:"/"C:"/"D:" 标签
  - 断言含 "选项1"/"选项2" 无标签格式
  - 断言含 `【内容假设】：` 标记要求
  - 断言含"禁止引用选项编号"
  - 断言同一 case 多次调用结果一致（固定 seed）
  - 断言时间类 case 含两步推理指令
- [ ] 运行测试，确认通过
- [ ] 提交：`feat(phase4): implement format_stage1_prompt with label-blind options`

#### Task 1.5：实现 parse_stage1_result（绿-4）

- [ ] 实现 `parse_stage1_result(raw)`：
  - 优先匹配 `【内容假设】：(.+)`
  - 容错匹配"结论："/"假设："/"判断："前缀
  - 最低优先级：取最后一段非空行
  - 返回 `(hypothesis, confidence)` 或 None
- [ ] 完善 `test_parse_stage1_result_marker`：
  - 标准标记格式 → 正确提取
  - 容错前缀 → 正确提取
  - 无任何标记 → 返回 None
  - 空字符串 → 返回 None
- [ ] 运行测试，确认通过
- [ ] 提交：`feat(phase4): implement parse_stage1_result with multi-prefix fallback`

#### Task 1.6：实现 format_stage2_prompt（绿-5）

- [ ] 实现 `format_stage2_prompt(case, hypothesis, evidence)`：
  - 含选项 A/B/C/D + Stage1 假设 + 证据 + APB
  - 含冲突仲裁指令（"若假设与证据矛盾，以证据为准"）
- [ ] 编写 `test_format_stage2_prompt`：
  - 断言含 A/B/C/D 标签
  - 断言含 hypothesis 内容
  - 断言含冲突仲裁指令
- [ ] 运行测试，确认通过
- [ ] 提交：`feat(phase4): implement format_stage2_prompt with conflict arbitration`

#### Task 1.7：实现 build_stage2_evidence（绿-6）

- [ ] 实现 `build_stage2_evidence(case, hypothesis, mode='all')`：
  - mode='all'：复用 `rag_prompt_builder` 检索全选项证据
  - mode='top2'：TF-IDF cosine 匹配 hypothesis → top-2 选项 → 只检索这 2 个
- [ ] 完善 `test_build_stage2_evidence_all_mode`：
  - mode='all' 返回全选项证据
  - mode='top2' 返回 ≤2 条证据
- [ ] 运行全部 formatter 测试，确认 100% 通过
- [ ] 提交：`feat(phase4): implement build_stage2_evidence with all/top2 modes`

### 阶段 2：benchmark runner 接入

#### Task 2.1：CLI 参数 + build_benchmark_prompt 接入（红→绿）

- [ ] 在 `run_benchmark.py` 的 `--method` choices 新增 `two_stage_reasoning`
- [ ] 在 `build_benchmark_prompt` 新增 `two_stage_reasoning` 分支（返回 Stage 1 prompt）
- [ ] 编写 `test_build_benchmark_prompt_two_stage`：断言 method='two_stage_reasoning' 返回 Stage 1 prompt
- [ ] 运行测试，确认通过
- [ ] 提交：`feat(phase4): add two_stage_reasoning to CLI and build_benchmark_prompt`

#### Task 2.2：两阶段调用编排 + fallback（红→绿）

- [ ] 在 `run_model_benchmark` 新增两阶段调用逻辑：
  1. Stage 1：`call_model_sync(stage1_prompt, temperature=0.0)` → raw1
  2. `parse_stage1_result(raw1)` → hypothesis
  3. 若 None：fallback 到 structured_reasoning 单阶段
  4. 否则：`build_stage2_evidence` + Stage 2 调用 → raw2 → 最终答案
- [ ] `case_details` 记录 `phase4_stage1_raw`/`phase4_stage1_hypothesis`/`phase4_stage2_raw`/`phase4_fallback`/`phase4_fallback_reason`/`phase4_is_time_question`/`phase4_conflict`/`phase4_evidence_mode`
- [ ] 编写集成测试 `test_two_stage_call_chain`：mock call_model_sync，验证调用顺序 + fallback 路径
- [ ] 运行测试，确认通过
- [ ] 提交：`feat(phase4): implement two-stage call orchestration with fallback`

#### Task 2.3：Stage 1 跨 perm 缓存（优化）

- [ ] 在 `run_model_benchmark` 增加 Stage 1 结果缓存：同一 case_id 只调用 1 次 Stage 1
- [ ] 编写 `test_stage1_cross_perm_cache`：mock call_model_sync，验证同 case 3 perm 只触发 1 次 Stage 1
- [ ] 运行测试，确认通过
- [ ] 提交：`perf(phase4): cache Stage 1 across perms (67% Stage 1 call reduction)`

### 阶段 3：smoke 验证

#### Task 3.1：10 case smoke（development 集）

- [ ] 准备 10 case 数据：2025 前 20 题中的 10 题（不污染 2024 holdout）
- [ ] 运行：`--method two_stage_reasoning --max-cases 10 --case-details-jsonl .tmp/phase4/smoke10.jsonl`
- [ ] 验证：
  - parser_valid_rate ≥ 0.90
  - fallback 率 ≤ 0.20
  - 准确率不低于 structured_reasoning baseline（同 10 题）
  - top-2 命中率统计（为 formal 阶段决策提供数据）
- [ ] 若 fallback > 0.20：优化 parser 或 Stage 1 prompt，重跑
- [ ] 提交：`test(phase4): 10-case smoke validation (dev set)`

#### Task 3.2：时间类 4 case 专项 smoke

- [ ] 提取 4 个 unanimous wrong case（P002-Q9/P003-Q13/P004-Q17/P005-Q22）
- [ ] 运行 two_stage_reasoning，检查 Stage 1 raw 输出
- [ ] 验证：
  - `is_time_location_question` 4/4 返回 True
  - Stage 1 是否输出了大运区间 + 流年验证
  - 准确率 ≥ 1/4 正确
- [ ] 若 0/4：分析 Stage 1 输出，调整两步推理指令
- [ ] 提交：`test(phase4): time-location 4-case targeted smoke`

### 阶段 4：formal40 评测

#### Task 4.1：formal40 on-3 × 3 perm

- [ ] 运行 on-3 p0：`--method two_stage_reasoning --apb-block --rag --rag-k 2 --retrieval-mode option_grounded --option-evidence-k 2 --case-details-jsonl .tmp/phase4/formal40_p4_on-3_p0.jsonl`
- [ ] 检查 p0 结果（准确率、fallback 率、parser_valid）
- [ ] 若 p0 准确率 < Phase 3 p0 (80%) - 5pp：触发回滚条件，停止并分析
- [ ] 运行 on-3 p1、p2（可并行）
- [ ] 提交：`test(phase4): formal40 on-3 x3perm two_stage_reasoning`

#### Task 4.2：formal40 off-3 × 3 perm

- [ ] 运行 off-3 p0/p1/p2（Stage 1 与 on-3 共享缓存）
- [ ] 检查 off-3 结果
- [ ] 提交：`test(phase4): formal40 off-3 x3perm two_stage_reasoning`

#### Task 4.3：生成 gate report + 验收

- [ ] 运行：`python scripts/phase3_generate_gate_report.py --stage formal40 --pred-dir .tmp/phase4 --output .tmp/phase4/gate_report_p4.json`
- [ ] 验证 6 项 gate：
  - gate_ite_28pct ≥ 0.28
  - gate_mms_80pct（目标 ≥ 0.80，底线 ≥ 0.7033）
  - gate_parser_valid_95pct ≥ 0.95
  - gate_confirmed_leak_zero = 0
  - gate_off_control_28_3pct ≥ 0.283
  - three_pp_advisory_pass
- [ ] 统计时间类 4 case 改善情况
- [ ] 统计总 API 调用数（验证 ≤ 336）
- [ ] 提交：`test(phase4): formal40 gate report generation`

### 阶段 5：交付

#### Task 5.1：撰写 Phase 4 交付报告

- [ ] 创建 `docs/PHASE4_DELIVERY_REPORT.md`
- [ ] 内容：gate 结果、两阶段推理效果、时间类攻坚效果、与 Phase 3 对比、失败路径归因（若有）
- [ ] 提交：`docs(phase4): add delivery report`

#### Task 5.2：最终提交 + 清理

- [ ] 确认所有测试通过：`pytest tests/test_two_stage_reasoning.py -q`
- [ ] 确认 git status 干净
- [ ] 清理 .tmp/phase4 临时实验文件（保留 gate_report_p4.json 和正式预测文件）
- [ ] 提交：`chore(phase4): cleanup temp experiment files`

---

## 4. 验收标准

| 指标 | Phase 3 基线 | Phase 4 目标 | 说明 |
|---|---|---|---|
| on_ite_accuracy | 0.75 | ≥ 0.75 | 不退化 |
| MMS | 0.7033 | ≥ 0.7033（突破 0.80 为成功） | 不退化，突破为 bonus |
| gate_parser_valid_95pct | 0.9598 | ≥ 0.95 | 不退化 |
| confirmed_leak_count | 0 | 0 | 不退化 |
| off_ite_accuracy | 0.65 | ≥ 0.65 | 不退化（修正） |
| 时间类 4 case | 0/4 正确 | ≥ 1/4 正确 | 准确率提升 |
| fallback 率 | N/A | ≤ 0.20 | 两阶段稳定性 |
| top-2 命中率 | N/A | ≥ 0.85 | formal 启用 top-2 的前提 |
| 总 API 调用 | 240 | ≤ 336（280 基础 + 20% fallback） | Stage 1 跨 perm 共享后 |

**Phase 4 成功条件**：5/6 gate 维持 PASS + 时间类至少 1/4 改善 + fallback 率 ≤ 0.20。MMS 突破 80% 为 stretch goal。

**回滚条件**：任何 Task 后若 on_ite 下降 > 5pp 或 MMS 下降 > 2pp，立即回滚到 Phase 3 noleak v4 配置。

---

## 5. 风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| Stage 1 内容假设与选项表述对不上 | 中 | 标签 blind 保留选项语义 + "可比较表述"约束 + fallback |
| 两阶段调用成本增加 | 中 | Stage 1 跨 perm 共享，总调用 280（vs Phase 3 的 240，+16.7%） |
| Stage 1 parser 失败率高 | 中 | 固定标记 `【内容假设】：` + 多前缀容错 + fallback 到单阶段 |
| 标签 blind 下模型引用选项编号 | 中 | Stage 1 prompt 明确禁止引用选项编号，必须用实际内容表述 |
| 时间类两步推理指令干扰非时间类 | 低 | `is_time_location_question` 精确触发 + smoke 统计误触发率 |
| API 限流 | 中 | 复用 Phase 3 的 SC retry 机制 |
| 假设-证据冲突 | 中 | 默认相信证据 + `phase4_conflict` 标记 |

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
