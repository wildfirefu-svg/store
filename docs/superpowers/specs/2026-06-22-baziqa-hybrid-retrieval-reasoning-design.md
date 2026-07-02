# BaziQA Hybrid Retrieval-Reasoning 升级 设计文档

> 创建日期：2026-06-22
> 触发：基于现有 P0–P2 报告与 [BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md)，准确率停在 24.2–30.0%，未达 40% 验收线。
> 当前状态：本设计已经过 brainstorming 流程多轮迭代确认（见 §2 决策摘要），**待用户审阅本设计文档后才进入实施**。

## 1. 目标

- 主目标：BaziQA 2025 holdout 40 题主集 mean accuracy ≥ 40%。
- 次目标：max-min ≤ 5pp（最好 ≤ 3pp）。
- 三级目标：报告格式与质量门禁固化，避免重复踩坑。
- 优先级（用户确认）：准确率 > 稳定性 > 报告质量。

## 2. 决策摘要（已确认）

| 项 | 决策 |
|---|---|
| 方案路线 | 方案 3 Hybrid 阶段交付 |
| Embedding 选型 | 可插拔，不锁死单一模型 |
| 阶段间门阈 | 严格门阈：mean ≥ 35%、mean ≥ 3 × stdev，且 `retrieved_answer_leak` 走渐进式中间门阈（见 §11） |
| 是否补 holdout chart_input | 同意 |
| 评测口径 | 40 题主集 + 新加领域子集 |
| 报告质量门禁 | 与方案同步加强 |
| 模型分层（新增） | smoke / ablation / debug 默认 `deepseek-v4-flash`；主集 3 repeats 与晋升判定必须 `deepseek-v4-pro`（见 §6、§12） |

## 3. 当前已知瓶颈

来自 [BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md)：

- holdout 缺 `chart_input` → `_score_chart_structure()` 返回 0；
- enriched corpus 不影响 top-2 召回；
- 模型温度 0 时仍有 27.5–35.0% 抖动；
- 检索 facts 中正确答案出现率为 **0/40**。

## 4. 总体阶段

### 阶段 1：Retrieval-first（必做）

子任务顺序基于“先诊断、再修底、再换 retriever、再做 ablation、最后做子集”的原则。

| 顺序 | 子任务 | 内容 | 验收 |
|---|---|---|---|
| 1.3 | retrieved_answer_leak 指标（先做，作为诊断） | 在 case_details 与最终报告中新增：检索 top-k facts 是否包含 ground truth answer | 该 metric 必须出现在 trace 与所有真实 API 报告中；最先跑一次 baseline 以确认当前 0/40 仍成立 |
| 1.1 | holdout chart_input 补齐（基础设施） | 复用 enriched corpus 脚本，把 40 题 holdout `chart_input` 覆盖率达到 100% | 覆盖率指标 = 100% 且 holdout enriched 文件存在 |
| 1.2 | Embedding 可插拔接入（必须含 TF-IDF baseline） | 通过 `BAZI_RAG_VECTOR_MODEL` env 切换 `bge-zh / m3e-base / all-MiniLM-L6-v2`；TF-IDF 不仅作为 fallback，也作为“is embedding model helping?” 的对照基线 | `BAZI_RAG_VECTOR=0`(纯 BM25+structured+TF-IDF) 与 `BAZI_RAG_VECTOR=1`(各 embedding) 必须在同一报告中对照展示 |
| 1.4 | retrieval ablation 矩阵 | 在主集上跑 5 组配置 × 3 repeats：bm25 / +structured / +semantic / +tfidf-vector / +embedding-vector。**执行策略**：5 组配置先全部用 `deepseek-v4-flash` 跑出大表筛选 Top-2 配置，再仅用 `deepseek-v4-pro` 对 Top-2 复核 3 repeats，详见 §12.2 | 输出 ablation 表（含 flash 大表 + pro Top-2 复核两段，并行对比） |
| 1.5 | 领域子集评测 | 主集 40 题按 `domain` 字段划分（health / annual_fortune / unknown / relationship）；不足 5 题的 domain 从 [baziqa_contest8_2021_2024_corpus.jsonl](file:///f:/project/agent/benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl) 中抽取补齐至 5–10 题，并在 case_details 中标注 `source: corpus_fill`；独立评测，不并入主集 mean | 输出子集结果 + `source: corpus_fill` 标注完整 |

> 脚注：1.4 的“flash 大表 + pro 复核 Top-2”是默认策略；若 1.4 大表上 Top-1 / Top-2 之间 mean 差距 ≤ 1pp，则将 pro 复核扩展为 Top-3，避免单次抖动造成的误选。

进入阶段 2 的严格门阈：

```text
mean_main_set >= 35.0%
mean_main_set >= 3 * stdev_main_set
retrieved_answer_leak_ratio >= 15%   # 中间门阈，详见 §11
```

任一项不满足，**回退优化阶段 1**，不进入阶段 2。

#### 快速验证路径（Fast-track）

若 1.3 与 1.1 完成后，主集在当前默认 retrieval 配置上已**经 3 repeats** 实测均值同时满足所有阶段 2 晋升门阈（`mean ≥ 35%`、`mean ≥ 3 × stdev`、`retrieved_answer_leak ≥ 15%`），则允许**申请跳过 1.4 / 1.5**，直接进入阶段 2。约束如下：

- 必须使用 `deepseek-v4-pro` 实测，**不允许用 flash 触发 fast-track**；
- 3 repeats 实测结果与 case_details 必须落盘并写入报告；
- 跳过 1.4 时，必须在最终报告中独立列出“**未执行 ablation 矩阵**”的说明，避免后续阶段做检索回退时无法定位最优配置；
- 跳过 1.5 时，必须在阶段 2 完成后**补做 1.5 领域子集评测**，作为阶段 2 → 3 晋升的硬前置条件；
- 任何门阈在 fast-track 后退化 ≥ 5pp，立即回到阶段 1 完成 1.4 / 1.5。**“退化基线”定义**：相对于触发 fast-track 时所用的那次 3-repeat 实测均值（即 1.3 + 1.1 完成后第一份满足阶段 2 门阈的 3-repeat 结果），同口径计算绝对差值；与 §11 的“本阶段最近一次满足晋升门阈的 3-repeat 稳定运行均值”定义对齐，但在 fast-track 段落内显式锚定，避免反复跳转。

### 阶段 2：Reasoning stabilization（条件触发）

| 子任务 | 内容 |
|---|---|
| 2.1 Self-consistency voting | 每题跑 3 次 majority vote |
| 2.2 命理对照表 prompt | `(日主, 月令, 身强弱) → 喜忌方向` 简版规则表，作为可拒绝提示，**不写死打分** |
| 2.3 confidence-gated re-ask | 模型输出 confidence < `confidence_threshold` 时再调用一次 self-consistency。`confidence_threshold = 0.6` 作为初始值，可通过阶段 2 内部 ablation 调整（候选区间 0.5–0.75，步长 0.05） |

进入阶段 3 的严格门阈：

```text
mean_main_set >= 38.0%
stdev_main_set <= 2.0pp
retrieved_answer_leak_ratio >= 25%   # 见 §11
```

### 阶段 3：Verifier（最后才考虑）

| 子任务 | 内容 |
|---|---|
| 3.1 Verifier LLM | 用同型号或更强模型对 top-1 结果与 retrieved evidence 做 “是否自洽” 二元裁决 |
| 3.2 verdict 回退策略 | verifier 拒绝时降级到第二候选 |
| 3.3 cost guard | 设上限 API 倍率，超出立即降级到阶段 2 模式 |

## 5. 报告质量门禁（与阶段 1 并行）

更新 [scripts/verify_report_quality_gate.py](file:///f:/project/agent/scripts/verify_report_quality_gate.py)：

新增校验项（error 级别）：

- 只跑 1 repeat 但宣布 “提升” → error；
- 报告缺 baseline 对比 → error。

新增校验项（warn 级别）：

- 报告缺 answer distribution → warn；
- 报告缺 retrieved_answer_leak → warn；
- 报告未列出 retrieval 配置 hash → warn。

## 6. 评测口径

- 主集：`benchmark/datasets/baziqa_contest8_2025_holdout.jsonl`，40 题，3 repeats，作为对外可比指标。
- 领域子集：health / annual_fortune / relationship / unknown 各 5–10 题，来源优先主集 `domain` 字段划分，不足则从 corpus 抽取补齐并标注 `source: corpus_fill`；独立评测，不并入主集 mean。
- 所有 real API 报告必须包含：mean / min / max / stdev / per-domain / answer distribution / retrieved_answer_leak / baseline 对比 / 配置 hash。

### 6.1 模型分层策略

| 场景 | 模型 | 是否计入晋升判定 |
|---|---|---|
| smoke（10 题） | `deepseek-v4-flash` 默认 | 否 |
| 阶段 1 ablation 矩阵（5 配置 × 3 repeats × 40 题） | `deepseek-v4-flash` 默认 | 否，仅用于挑选最佳 retrieval 配置 |
| 阶段 1 / 2 / 3 主集 3 repeats 晋升判定 | `deepseek-v4-pro` **强制** | 是 |
| 阶段 2 self-consistency | `deepseek-v4-flash` 默认（先验证 vote 是否降 stdev），最后一次定稿用 `pro` | 仅 `pro` 计入 |
| 阶段 3 Verifier | 由阶段 1/2 数据决定（同型号或更强），但 verifier 与 base 模型不应同时为 `flash` | 是 |

约束：

- **任何写入 [BAZIQA_ACCEPTANCE_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCEPTANCE_REPORT.md) 的“晋升 / 阻塞 / 验收”判定，必须基于 `deepseek-v4-pro` 实测值**；
- 报告中所有 `flash` 结果，标题与表格必须显式标注 `[model: flash]`；
- 不允许把 `flash` 的 mean 直接与 `pro` 的 baseline 比较得出“提升”结论；
- 跨模型对比时，必须在同一报告中同时给出 `flash` 与 `pro` 两组数字。

模型切换方式：

- 通过现有 `benchmark/runners/run_benchmark.py` 的 `--model` CLI 参数显式指定，例如 `--model deepseek-v4-pro` 或 `--model deepseek-v4-flash`；
- 自动化批跑（如 [run_baziqa_k_ablation.py](file:///f:/project/agent/scripts/run_baziqa_k_ablation.py)、[run_baziqa_retrieval_ablation.py](file:///f:/project/agent/scripts/run_baziqa_retrieval_ablation.py)）已支持 `--model` 透传；
- 不引入额外的 `BAZI_MODEL_NAME` 环境变量，避免与 CLI 双写造成不一致；
- case_details 与最终报告必须把 `model_name` 字段连同 `git_short_sha`、`utc_timestamp`、`config_id` 一起落盘，便于回溯。

## 7. 不会做

为避免范围爆炸，本设计**不包含**：

- 训练 / 微调命理专用 embedding；
- 微调或蒸馏 base LLM；
- 引入向量数据库服务（保持本地内存 + 文件）；
- 多模型集成（≥3 个）方案。

这些留待后续阶段视效果决定。

## 8. 风险与回退

| 风险 | 触发条件 | 回退策略 |
|---|---|---|
| Embedding 噪声召回 | retrieved_answer_leak 下降 | 限阈值 / 提升 structured weight |
| API 成本翻倍 | 阶段 2/3 单题 cost > 阶段 1 × 3 | 关闭 verifier，回到阶段 2 |
| 同源 voting 收益边际递减 | 阶段 2 stdev 未降 | 评估更换 verifier 模型 |
| Holdout chart_input 引入 bug | enriched holdout 上 mean 显著下降 | 立刻回退脚本，重生成 enriched holdout |

## 9. 验收与交付物

阶段 1 交付：

- `benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl`（chart_input 100%）；
- 可插拔 embedding 路径与 `BAZI_RAG_VECTOR_MODEL` env；
- `docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md`（5 组配置 × 3 repeats 表格，含 `retrieved_answer_leak` 与 baseline 对比）；
- 报告质量门禁脚本扩展 + tests；
- 严格门阈判定结果（是否进入阶段 2）。

阶段 2 / 3 交付物：阶段 1 通过门阈后再单独写设计补丁。

## 10. 下一步

待用户审阅本设计文档并确认后，由 `writing-plans` 技能生成实施计划，再进入实施。

## 11. 中间门阈说明（answer_leak 渐进式）

考虑到当前 `retrieved_answer_leak` 实测值为 **0/40 = 0%**（见 [BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md)），从 0% 一次性跳到 25% 是“质的飞跃”，会让阶段 1 看起来很难通过、容易导致团队提前放弃 retrieval 路线或为了通过门阈而过拟合到测试集。改为渐进式中间门阈：

| 项目 | 阈值 | 触发动作 |
|---|---|---|
| `retrieved_answer_leak` ≥ 5% | 最低有效信号 | 在阶段 1 内继续打磨检索权重 / vector model，不直接进阶段 2 |
| `retrieved_answer_leak` ≥ 15%（结合 mean ≥ 35%、mean ≥ 3 × stdev） | 进入阶段 2 | 允许启动 self-consistency / 命理对照表 prompt |
| `retrieved_answer_leak` ≥ 25%（结合 mean ≥ 38%、stdev ≤ 2pp） | 进入阶段 3 | 允许启动 Verifier |
| `retrieved_answer_leak` < 5% 且 mean < 30% | 触发回退 | 关闭 vector 模式，回到 P2 已有配置，避免误伤 baseline |
| **灰色带 A**：`5% ≤ leak < 15%`，或 `30% ≤ mean < 35%`，且既不满足晋升也未触发回退 | 阶段 1 内持续优化 | 不晋升、不回退；最多再做 **2 轮**子任务级 ablation（检索权重 / vector model 切换 / TF-IDF 对照），仍不达标则降级到只优化结构化与语义短语 |
| **灰色带 B**：`leak ≥ 15%` 但 `mean < 35%` 或 `mean < 3 × stdev` | 阶段 1 内权重排查 | 触发 §11 的“量化判定”路径，冻结当前 retrieval 权重并做单变量 ablation；不晋升 |

补充：

- 阶段间晋升必须**至少 3 repeats** 的实测值，单轮通过不算；
- 一旦 leak 上升但 mean 没跟上，说明检索召回了“能引诱模型答错”的命例，触发权重排查；**量化判定**：`leak 上升 ≥ 5pp` 且同一 3-repeat 窗口内 `mean 上升 < 2pp`，立即冻结当前 retrieval 权重，回到上一稳定配置并做单变量 ablation；
- 任何阶段 leak 退化 ≥ 5pp，必须先回退到上一阶段稳定配置。**“退化 5pp”定义**：相对于**本阶段最近一次满足晋升门阈的 3-repeat 稳定运行均值**计算的绝对差值；若本阶段尚未产生满足门阈的 3-repeat 运行，则相对于阶段开始时的初始 baseline 计算。

## 12. 成本/时间预算与限额

成本与时间是当前最容易失控的工程风险，本节为每个阶段固定预算，并设定硬上限触发回退。

### 12.1 单次 API 调用预估口径（按模型分层）

| 模型 | 单题平均时延 | 单题相对成本（pro=1.0） | 适用场景 |
|---|---|---|---|
| `deepseek-v4-pro` | ~25–30 s | 1.0 | 晋升判定、对外可比指标 |
| `deepseek-v4-flash` | ~8–12 s（经验值） | ~0.2（经验值，需运行后实际校准） | smoke / ablation / debug / self-consistency 探索 |

单题 token 量：约 prompt 1.5–3k + completion 0.3–0.8k（与模型无关）。
单次 retry 触发率：≤ 2 / 40。

> 注：`flash` 的单题时延与单题相对成本数值是经验值，**首次阶段 1 sanity 运行时必须实测并把实测值写回本节**，再以实测为准做后续预算。

#### 12.1.1 费率与单题估价（用于 §12.2 费用列）

> 计费假设（首次运行后必须校准并回填本表，过时则不得用作晋升预算判定）：
>
> 1. 单题 token 估算：prompt 2.2k（取上下区间均值），completion 0.55k；
> 2. 输入价、输出价采用 DeepSeek 官方公开计费 USD/1k tokens 区间，取上界以做保守预算；
> 3. **货币与汇率假设**：本设计统一使用 **CNY (人民币)** 计价，USD→CNY 汇率按 **1 USD = 7.20 CNY** 折算（取保守上界，便于做预算）；
> 4. retry 不重复计费；
> 5. 不含 embedding 调用（embedding 模型本地推理为主，按 §7 “不会做” 不引入向量数据库服务）。

| 模型 | 输入价（USD/1k tokens，估） | 输出价（USD/1k tokens，估） | 单题估价（USD/题，估） | 单题估价（CNY/题，估） | 备注 |
|---|---|---|---|---|---|
| `deepseek-v4-pro` | 0.0014 | 0.0028 | ~0.0046 | **~0.033** | 用作晋升判定主成本基准 |
| `deepseek-v4-flash` | 0.00028 | 0.00056 | ~0.00092 | **~0.0066** | 与 §12.1 相对成本 0.2 一致；仅用于 ablation/sanity |

> 上述单价是 **估算占位**，需在首次 sanity 运行时按真实账单回填；§12.3 cost guard 的 "API 倍率" 即基于此基准。
> 如汇率漂移 > 5%，需要同步更新本表 USD→CNY 换算结果，再传播到 §12.2 / §12.3 / §12.4。

### 12.2 阶段成本估算（已按模型分层）

| 阶段 / 任务 | 模型 | 单次方案 | 调用次数 | 预计耗时 | 预估费用（CNY） |
|---|---|---|---|---|---|
| 1.3 retrieved_answer_leak 诊断 baseline | `pro` | 主集 × 1 repeat | 40 | ~17–20 min | ~1.32 |
| 1.2 Embedding 模型对照 sanity | `flash` | 5 配置 × 主集 × 1 repeat | 200 | ~30–40 min | ~1.32 |
| 1.4 retrieval ablation 矩阵（候选筛选） | `flash` | 5 组 × 3 repeats × 40 题 | 600 | ~85–115 min | ~3.96 |
| 1.4 ablation 复核（仅 Top-2 候选配置） | `pro` | 2 配置 × 3 repeats × 40 题 | 240 | ~100–120 min | ~7.92 |
| 1.5 领域子集评测 | `flash` | 4 子集 × 3 repeats × 5–10 题 | 60–120 | ~10–25 min | ~0.40–0.79 |
| 1.5 领域子集定稿 | `pro` | 同上仅 Top-2 配置 | 60–120 | ~25–60 min | ~1.98–3.96 |
| 阶段 1 总预算 | flash + pro 混合 | — | **1200–1320 次调用 + 10% 重跑余量（≈ 120–132 次）** | **~4–6 h API 时间 + 余量** | **~16.90–19.27 CNY + 10% 余量（合计 ~18.59–21.20 CNY）** |
| 阶段 2 self-consistency 探索 | `flash` | 主集 × **2 vote**（默认探索值） × 3 repeats | 240 | ~35–50 min | ~1.58 |
| 阶段 2 self-consistency 定稿 | `pro` | 主集 × **3 vote**（仅定稿） × 3 repeats | 360 | ~2.5–3 h | ~11.88 |
| 阶段 2 condition-gated re-ask | `pro` | 增量 ≤ 主集 × 1 repeat | ≤ 40 | ≤ 17–20 min | ≤ ~1.32 |
| 阶段 2 总预算 | flash + pro 混合 | — | **≤ 640 次（含 ~120 次空间余量）** | **~3.5–4.5 h** | **≤ ~14.78 CNY** |
| 阶段 3 Verifier sanity | `flash` 作为 base + `pro` 作为 verifier | 主集 × 1 repeat | 40 + 40 verifier | ~30–40 min | ~1.58 |
| 阶段 3 Verifier 定稿 | `pro` base + 强模型 verifier | 主集 × 1 verifier-pass × 3 repeats | 120 + 120 verifier | ~2–2.5 h | ~7.92 |
| 阶段 3 cost guard 触发上限 | — | API 倍率 ≤ 5 × baseline | — | — | ≤ 5 × 阶段 1 单次 sanity 成本 |
| 阶段 3 总预算（估） | flash + pro 混合 | — | 320 | ~3 h | **~9.50 CNY** |
| **三阶段合计预算（估，保守上界）** | — | — | — | **~10–14 h** | **~41.18–43.55 CNY（保守取阶段总预算上界后 ≈ ~45.48 CNY）** |

> 费用估算口径与假设：
>
> 1. 单题估价取自 §12.1.1：`pro ≈ 0.033 CNY/题`、`flash ≈ 0.0066 CNY/题`（USD→CNY 1:7.20）；
> 2. 表中数字为四舍五入到 2 位小数后的保守估算；
> 3. 不含 embedding 模型一次性加载与本地推理成本（本地 CPU 推理，已按 §7 不引入向量数据库服务）；
> 4. 不含 retry 重复计费、cost guard 触发后的额外切换成本；
> 5. **首次 sanity 运行后必须按真实账单回填 §12.1.1，并按 1.2 × 实际单价更新本表上限**；
> 6. `三阶段合计预算` 仅作总览，**不允许把跨阶段费用并到同一晋升判定中**；
> 7. 汇率：本节所有 CNY 数字基于 1 USD = 7.20 CNY，如汇率漂移 > 5% 必须按 §12.1.1 同步更新。


> 该预算基于 “每个阶段先用 flash 跑大表，再用 pro 复核 Top-2” 的混合策略，相比全 pro 方案的阶段 1 节省约 60%–70% 时间。具体比例首次跑完 sanity 后必须校准。

### 12.3 硬限额（任一触发立即停跑）

- 单次实验运行墙钟时间 > 12 h；
- 单阶段累计 API 调用 > 1.5 × 估算上限；
- 单阶段累计费用 > 1.5 × §12.2 “阶段总预算（CNY）” 估值（按 §12.1.1 单价折算）；
- 三阶段累计费用 > 1.5 × **~45.48 CNY（即 ≈ ~68 CNY）**；
- API 失败率 > 10%；
- 单次完整运行（40 题）**API 调用失败**（HTTP 非 2xx、超时、JSON 解析失败等）> 4 次。注意：**预测错误不属于预算范畴**，不计入此项；
- `flash` 与 `pro` 在同一配置上 mean 差距 > 15pp。命中后的处理：
  - 立即停止当前 ablation；
  - 后续 ablation **全部切换为 `pro` 执行**，不再使用 `flash` 代理；
  - 已落盘的 flash 大表结果保留但标注 `INVALID:flash_pro_drift>15pp`，不进入 Top-2 / Top-3 选型；
  - 在 lessons-learned 中追加一条 “flash 不再适合代理 pro 做 ablation 的条件”。

任意命中：

1. 停止运行并保留已落盘 `case_details_jsonl`；命名规范：
   - 阶段 1：`.tmp/rollback_stage1_{config_id}_{git_short_sha}_{utc_timestamp}.jsonl`
   - 阶段 2：`.tmp/rollback_stage2_{config_id}_{git_short_sha}_{utc_timestamp}.jsonl`
   - 阶段 3：`.tmp/rollback_stage3_{config_id}_{git_short_sha}_{utc_timestamp}.jsonl`
   - `config_id` 由 retrieval 配置 hash 截取前 8 位生成，确保唯一回退点；
   - 同一时间戳文件不允许重写，已存在则追加 `_dup1` / `_dup2`；
2. 在结果报告中标注 `BLOCKED:budget` 并列出对应 rollback 文件路径；
3. 不进入晋升判定。

### 12.4 节流与回退手段

- 优先用 `--max-cases 10` + `--model deepseek-v4-flash` 做 sanity，再放完整 40 题；
- 阶段 1 大 ablation 默认 `flash`，仅对 Top-2 retrieval 配置用 `pro` 复核；
- 阶段 2 self-consistency 默认 3 vote，可降为 2 vote；
- 阶段 3 verifier 默认全量执行，cost guard 触发后切为 confidence-gated（≤ 30% case 触发）；
- 一旦本阶段成本超出 1.2 × 预算，**强制降级到上一稳定阶段**并写入 lessons-learned；
- 若 `flash` 与 `pro` 在 ablation 上排序不一致（Top-1 配置切换），必须用 `pro` 重跑 Top-3 才能选最终配置；
- **每次完整运行结束必须把 “实际 API 调用次数、实际费用（CNY，按当次实际汇率折算）、与 §12.2 估算的偏差比”写入对应报告**，并在偏差 > 20% 或 USD→CNY 汇率漂移 > 5% 时同步回填 §12.1.1 单价与汇率。
