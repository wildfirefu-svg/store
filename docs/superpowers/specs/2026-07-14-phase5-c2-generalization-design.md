# Phase 5 C2 独立泛化验证设计

**日期**：2026-07-14
**状态**：设计已批准
**范围**：BaziQA direct+C2 独立泛化验证与自适应评测编排

## 1. 背景与决策依据

最新实验落点见 `docs/PHASE4_EXPC2_REPORT_2026-07-10.md`：

- direct：11/40，27.5%。
- direct+C2：13/40，32.5%，比 direct 高 5.0pp。
- direct+C2 救回 7 题，同时使 5 题从正确变为错误，净增益仅 2 题。
- two_stage 为 9/40，ExpB 为 10/40，均低于 direct；这两条路线暂停优化。
- C2 规则针对 2024/2025 holdout 错误样式做过校准，当前结果不能证明独立泛化。

Phase 5 不继续增加模板规则数量。第一优先级是验证当前 C2 是否能在未用于校准的年度数据上保持增益，再决定是否进行 Prompt 格式、防锚定和 evidence 压缩消融。

## 2. 目标与非目标

### 2.1 目标

1. 在 2021/2022 独立年度数据上验证当前 C2 的离线信号和模型端增益。
2. 保留 2023 年作为密封最终集，用于验证 Phase 5 选定 Prompt，而不是参与方案选择。
3. 以自适应复测把模型调用集中在 direct 与 direct+C2 的分歧题上。
4. 产出可恢复、可审计、可重复的逐题记录、机器可读汇总和 Markdown 报告。
5. 用明确 gate 把结论分为 `PROMOTE`、`NON_INFERIOR` 和 `ROLLBACK`。

### 2.2 非目标

- 不修改 `benchmark/runners/per_option_scorer.py` 中的 C2 规则。
- 不恢复 two_stage 或 ExpB 优化。
- 不在本阶段把 C2 接入线上生产聊天。
- 不修改受保护的原始 BaziQA JSONL 文件。
- 不用 2021–2023 的结果继续调 C2 规则。
- 不把单次 1–2 题波动表述为统计显著提升。

## 3. 数据角色与隔离

| 年度 | 角色 | 允许用途 |
| --- | --- | --- |
| 2024/2025 | 开发与错误分析集 | 错题回放、Prompt 消融、防锚定、evidence 压缩 |
| 2021/2022 | 独立泛化验证集 | 当前 C2 scorer-only gate 与自适应 direct/direct+C2 配对实验 |
| 2023 | 密封最终集 | Phase 5 选定 Prompt 后的一次最终配对验证 |

仓库现有三个年度 holdout 均为 40 题，但 `chart_input` 覆盖率为 0。C2 依赖 `chart_input.shishen_stats`、地支关系、神煞和五行统计，因此不得直接对原始文件运行 C2。

### 3.1 Enrichment

使用现有 `scripts/enrich_holdout_chart_input.py`，将 enriched 副本写入：

```text
.tmp/phase5_generalization/datasets/
```

不得覆盖 `benchmark/datasets/baziqa_contest8_20xx_holdout.jsonl`。

每个 enriched 年度文件必须满足：

- 对应原始 holdout 文件在运行开始时存在且可读。
- 40 行、40 个唯一 `case_id`。
- `chart_input` 覆盖率为 100%。
- enrichment 前后 `case_id`、人员 ID、题目、选项、答案和来源年份完全一致。
- 文件写完后计算 SHA-256；实验开始后不得改写。

人员重叠和领域分布写入 manifest，用于解释结果，但不在 enrichment 阶段删除样本。

### 3.2 Manifest

`.tmp/phase5_generalization/manifest.json` 至少记录：

- 原始/enriched 文件路径、SHA-256、行数、人员数、领域分布。
- 当前 Git commit。
- `per_option_scorer.py`、`baziqa_prompt.py`、`run_benchmark.py` 的 SHA-256。
- provider、model、method、temperature、RAG/few-shot/APB/two-stage 开关。
- enrichment 时间和命盘计算器文件哈希。
- 固定调度 seed、运行 ID 和创建时间。
- 与实验作用域相关文件的 `git status --short` 快照；不得记录 `.env`、密钥文件或无关路径。

设计时的工作区状态显示 C2 相关代码尚未全部纳入 Git；正式运行时必须重新检查 Git 状态，并始终以单文件哈希作为实验实现的最终标识。manifest 不得保存 API key 或其他密钥。

相关文件存在未提交变更时，脚本必须给出强警告并要求显式 `--allow-dirty-scope` 才能创建新 run；manifest 记录这些文件的状态和哈希。已有 run 的相关文件哈希发生变化时一律拒绝续跑。无关工作区改动只记录总体警告，不阻塞本实验。

## 4. 固定实验口径

为与 Exp C2 报告对齐，默认口径为：

| 参数 | 值 |
| --- | --- |
| provider | `deepseek` |
| model | `deepseek-chat` |
| method | `direct_choice` |
| temperature | `0` |
| RAG | off |
| few-shot | off |
| APB | off |
| two-stage | off |
| 实验臂 | direct、direct+C2 |

不得把 `deepseek-v4-pro`、`deepseek-v4-flash` 或历史缺失模型字段的 baseline 与本实验拼接比较。续跑时只要模型、参数、数据哈希或代码哈希变化，就必须创建新 run，不能复用旧结果。

脚本提供显式 `--resume`。该标志只在当前配置与 manifest 的模型、参数、数据、代码和调度哈希完全一致时生效；不一致时拒绝续跑，并要求新的 run ID/目录，不自动改写旧 manifest。

## 5. 自适应实验流程

### 5.1 阶段 A：scorer-only 预筛

调用 `per_option_scorer.summarize_scores()`，不调用模型。每个可运行年度必须同时满足：

- `top_score_hit_rate > 35%`
- `score_answer_correlation > 0.1`
- `neutral_option_rate < 50%`
- `strong_signal_option_rate > 30%`

2021 或 2022 任一年度失败时，记录 offline gate 失败，不对该年度发起 API 实验，也不根据失败结果修改 C2 后重新使用该年度验收。

scorer-only gate 只是“C2 能在该年度产生基本可区分信号”的成本止损条件，不是泛化证据。通过该 gate 不构成准确率提升、非退化或 `PROMOTE` 依据；泛化结论只由模型 API 配对结果决定。2021/2022 任一年度 gate 失败时，本轮整体判定为 `ROLLBACK`，2023 保持密封。

终端日志、年度 offline JSON 和最终报告都必须输出四项指标的具体值、阈值、裕量和判定，便于判断门槛是否过严或过松；本轮运行期间不得根据这些数值修改门槛。

2023 在最终候选选定前不得运行 scorer-only；读取其答案计算 scorer 指标同样视为打开密封集。

### 5.2 阶段 B：单次配对运行

每题分别运行 direct 与 direct+C2。每个年度最少 80 次模型调用。

使用固定 seed 生成平衡 AB/BA 顺序：

```text
case 1: direct -> direct+C2
case 2: direct+C2 -> direct
case 3: direct -> direct+C2
...
```

这样可降低同一模型服务随时间漂移产生的系统偏差。每次调用完成后立即追加保存：

- run/year/case/arm/attempt 唯一键。
- Prompt 版本、非敏感运行参数和代码/数据哈希引用。
- 原始输出、解析答案、parser source、parser valid、正确性。
- C2 分数与 matched rules（C2 臂）。
- 延迟、错误和重试次数。

编排器以单题列表调用 `run_model_benchmark()` 时必须传入 `case_details_jsonl=None`。现有 `_prepare_jsonl()` 会在每次调用开始时清空目标文件，不能承担跨单题调用的累计持久化。编排器从返回值读取唯一一条 case detail，并自行追加到 attempt 级 JSONL；不得把同一个 `case_details_jsonl` 路径复用于多次单题调用。

### 5.3 阶段 C：仅复测分歧题

若同一题首次 direct 与 direct+C2 预测答案不同，则两个臂各追加两次调用；首次答案相同的题不复测。

首轮和两次复测都保持 `temperature=0`，并以三个独立 API 请求执行，不使用 runner 的 `n_samples`/`sample_temperature=0.4` 路径。这里的复测目标是测量相同配置下已经在本仓库实测出现的模型/API 非确定性，而不是人为提高采样温度。若三次输出完全一致，则记为一致性证据；若有变化，则以多数票作为该臂的稳定结论。

若三次包含不可解析输出，仍保留三次尝试，按有效票多数决定；没有多数有效票时，该题标记 unresolved，并计入 parser 失败统计。三次均不可解析时另记 `all_invalid`，在年度和总体报告中单独统计，不增加第四次决胜调用。

### 5.4 调用预算

- 2021/2022 初始验证最低 160 次调用。
- 2023 最终验证最低 80 次调用。
- 按 2025 年约 30% 分歧率估算，总调用约 380 次。
- 理论最低为 240 次；上限取决于分歧题数量，但低于全量三重复的 720 次。

### 5.5 年度止损

出现以下任一情况停止当前或后续年度：

- parser valid < 95%：停止实验，先修评测基础设施。
- 单次配对中 C2 的回退数减救回数达到 4 题或更多：判定明显伤害，停止后续年度。
- scorer-only 任一硬门槛失败：本轮 `ROLLBACK`，不进入该年度 API 阶段，也不解封 2023。
- confirmed answer leak > 0：立即 ROLLBACK。

## 6. 2023 密封集解封条件

只有满足以下条件，编排器才允许 `--final-2023`：

1. 2021/2022 的结果和判定已生成。
2. Phase 5 Prompt 候选已在 2024/2025 开发集上选定，并写入 manifest。
3. 候选 Prompt 和 C2 规则哈希已冻结。
4. 调用者显式指定最终运行标志；默认命令不能读取或评估 2023 C2 答案。

2023 解封后不再根据其结果修改本轮候选。若修改，必须声明上一轮最终集已被消费，并寻找新的外部验证来源。

## 7. 总体判定

最终使用 2021–2023 共 120 题的稳定配对结果。

硬门槛：

- 总体 direct+C2 准确率不低于 direct。
- 至少两个年度 direct+C2 不退化。
- C2 新增回退题不超过 12/120（10%）。
- parser valid >= 95%。
- confirmed answer leak = 0。

判定：

- `PROMOTE`：全部硬门槛通过，且总体救回数大于回退数。
- `NON_INFERIOR`：全部硬门槛通过，且总体救回数等于回退数；只能声称未退化，不能声称提高准确率。
- `ROLLBACK`：任一硬门槛失败。

报告额外输出年度/领域准确率、救回数、回退数、共同正确/共同错误、分歧题多数票，以及基于不一致配对数的精确二项 McNemar 检验；不使用大样本卡方近似。统计显著性用于表达证据强弱，不替代硬门槛。

通过 BaziQA `PROMOTE` 后，下一步是 MingLi-Bench 非退化验证；在此之前不得把 C2 设为默认生产路径。

## 8. 实现结构

新增 `scripts/run_phase5_c2_generalization.py`，职责限定为：

1. 数据 enrichment 与不变量校验。
2. manifest 创建/校验。
3. scorer-only gate。
4. 固定 AB/BA 调度和逐题调用。
5. 分歧题复测、恢复和汇总。
6. gate 判定与报告生成。

复用现有接口：

- `scripts.enrich_holdout_chart_input.enrich_row()` / IO helpers。
- `benchmark.runners.per_option_scorer.summarize_scores()`。
- `benchmark.runners.run_benchmark.run_model_benchmark()`，以单题列表、`case_details_jsonl=None` 调用。
- `benchmark.scorers.choice_accuracy` 的答案解析逻辑。

编排器拥有全部跨调用持久化职责。`run_model_benchmark()` 内置的每题 1 秒 pacing 保留，用于避免高频请求；预算报告单独记录模型调用耗时和 pacing 开销。

运行产物结构：

```text
.tmp/phase5_generalization/
  manifest.json
  datasets/
  offline/
  runs/2021/
  runs/2022/
  runs/2023/
  summary.json
docs/PHASE5_C2_GENERALIZATION_REPORT.md
docs/phase5/phase5_c2_generalization_manifest.json
docs/phase5/phase5_c2_generalization_summary.json
```

`.tmp/` 中保存可恢复的运行中状态。实验完成并通过完整性检查后，将最终 manifest 与 summary 复制为 `docs/phase5/` 下的审计证据；报告引用其 SHA-256，避免清理 `.tmp/` 后失去复现依据。

## 9. 失败处理与恢复

- 数据/代码/参数哈希不匹配：拒绝续跑，要求新 run 目录。
- `--resume` 未提供时拒绝复用已有 run；提供后仍需完整 manifest 匹配。
- API 超时或暂时错误：沿用已有有限重试；最终失败写 failure marker。
- 不得因调用失败删除题目或缩小统计分母。
- parser invalid 保留原始输出，并计入 parser valid 分母。
- 每次调用独立追加落盘；重启后按唯一键跳过已完成 attempt。
- 报告仅从完整持久化记录重建，不依赖终端输出。
- 日志和产物不保存 API key。

## 10. 测试策略

新增单元测试，不访问网络，使用 fake model runner 覆盖：

1. enrichment 后行数、唯一 ID、100% `chart_input` 和题目/答案不变。
2. manifest 内容、SHA-256 和参数/代码漂移拒绝逻辑。
3. AB/BA 调度在固定 seed 下可复现且数量平衡。
4. scorer-only 四项 gate 和年度止损。
5. 仅分歧题进入复测。
6. 三次多数票、invalid 输出和 unresolved 边界。
   - 包括三次均不可解析时的 `all_invalid` 独立统计。
7. 中断恢复不会重复调用已完成 attempt。
8. API failure marker 不改变分母。
9. 默认禁止读取/运行 2023，只有最终标志和冻结候选齐备时解封。
10. `PROMOTE`、`NON_INFERIOR`、`ROLLBACK` 的所有边界。
11. 在未解封状态下直接调用 2023 enrichment、scorer-only 或 API 调度均必须报错。
12. 单题 runner 调用固定传 `case_details_jsonl=None`，attempt JSONL 由编排器追加且恢复时不被截断。
13. 作用域内 dirty 文件需要 `--allow-dirty-scope`，且其 Git 状态与哈希写入 manifest。
14. `--resume` 只接受 manifest 完全匹配的 run，参数或哈希漂移必须拒绝。

迭代阶段先运行新增测试及 C2/runner 关联测试；最终实现完成后运行非 E2E 测试集。真实 API 实验与单元测试分离，不能把网络结果伪装成测试通过。

## 11. 后续顺序

1. 完成 2021/2022 当前 C2 泛化验证。
2. 若未 ROLLBACK，在 2024/2025 开发集进行错题回放、direct+C2 Prompt 格式/位置/权重消融、防高分锚定与 evidence 压缩；不增加模板规则数量。
3. 冻结唯一 Prompt 候选。
4. 解封 2023，执行最终配对验证并生成总判定。
5. 只有 `PROMOTE` 才进入 MingLi-Bench 非退化验证和默认路径评估。
