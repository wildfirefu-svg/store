# 准确率提升 · 方案 C 设计文档

- **日期**: 2026-07-01
- **作者**: TRAE Agent
- **状态**: Draft，待用户审阅
- **目标**: 基于 baziqa 40-case × 3 与 MingLi-Bench 160 题双基准，把 flash 主流程准确率从 28.3% mean → **35%+（近期）→ 55%+（长期，MingLi-Bench）**，同时不牺牲 strict leak = 0

---

## 1. 背景与已否掉的方向

- 已验证 baseline：`option_grounded_tfidf` + flash，40×3 mean = 28.3%（v1）；pro 单轮 stratified8 3/8，未超过 flash。
- 已尝试并回滚的方向：
  1. v2 scorer 加权 option/fact → 40×3 mean 24.2%（下降）
  2. 抽象 domain prompt guidance → 无净收益
  3. chart_domain_summary 注入 prompt → family/health smoke 1/7，无稳定收益
  4. corpus domain 关键词重分类 → family/health smoke 2/7 有单域收益，stratified8 3/8 无整体收益，且引入 1 例 parser=None
- 已保留：马来西亚地点匹配数据正确性修复（`bazi_calculator.py`）
- Evidence 质量诊断：gold answer top1 27.5%，错误样本中 51.2% 是错误选项 evidence 分反而更高；直接按 evidence top 选答案只 27.5%，说明**当前 evidence score 表示能力不足**。
- 外部主流经验：
  - **BM25/TF-IDF + Dense embedding + RRF + Cross-encoder rerank**（腾讯云/DeepSeek-RAG-Chatbot/蚂蚁 GraphRAG 前置）
  - **Self-Consistency（多样采样 + 多数投票）** 在 CoT 上普遍 +5~15pt
  - **具体 few-shot > 抽象规则**
  - **`--shuffle-options`** 抗位置偏差（MingLi-Bench 默认做法）
  - **Graph RAG / 规则节点** 蚂蚁 60% → 95%

---

## 2. 设计目标与非目标

### 目标

- **T1**：baziqa 40×3 mean 从 28.3% 提到 ≥35%，且 min ≥30%
- **T2**：family + health 7-case 从 v1 均值 0.67/7 提到 ≥3/7
- **T3**：MingLi-Bench 160 题 flash 达到 ≥55%
- **T4**：strict leak 稳定为 0
- **T5**：全部改动可小步验证 + A/B 决策，任一 phase 无收益立即回滚

### 非目标

- 不做 LLM 微调 / RLHF（数据量不足）
- 不引入云端 embedding / 云端 reranker（成本 + 隐私）
- 不做多 Agent 编排（前几轮教训：先解决表示与推理，再谈编排）

---

## 3. 总体架构

```
+----------------------------------------------------+
|            benchmark_runner (扩展)                 |
|  --shuffle-options / --n-samples N /               |
|  --aggregate majority|logprob                      |
+--------------+---------------+---------------------+
               |               |
               v               v
+------------------+   +----------------------------+
|   两阶段推理     |   |   MingLi-Bench 适配器      |
| stage1: 独立分析 |   |  data.json + fortune_api  |
| stage2: top-2   |   |  cot + astro + shuffle    |
| 决胜（查证据）   |   +----------------------------+
+--------+---------+
         |
         v
+-------------------------------------------------+
|         Hybrid Retrieval + Reranker             |
|  case_index (TF-IDF-like) + dense (bge-small)  |
|  → RRF 融合 → bge-reranker-v2-m3 精排          |
+-------------------------------------------------+
                    |
                    v
+-------------------------------------------------+
|        Evidence Sources (统一 top-k 输出)       |
|  a) case fact evidence（旧）                    |
|  b) 规则节点 evidence（新）                     |
|  c) chart_domain_summary（可选辅助字段）        |
+-------------------------------------------------+
```

Prompt 结构（option_grounded_v2）：

```
[few-shot 3 条具体案例]
[基础 system prompt]
[<命主关键项摘要-domain>（family/health/relationship 时启用）]
[<选项证据>：case fact + 规则节点（融合排序后）]
```

---

## 4. Phase 划分

按“先低风险 + 高收益，再结构性改造”排序：

### Phase 1 · Runner 与评测基础（3-5 天）

**目的**：把评测能力先补齐，才能公平衡量后续改动。

- P1.1 `benchmark_runner` 增加 `--shuffle-options`：seed 化的选项顺序随机 + `predicted_answer` 反映到原始 label（对齐 MingLi-Bench）
- P1.2 `benchmark_runner` 增加 `--n-samples N --aggregate majority`：单 case 多次采样 + 众数决出最终答案；tie-break 走首答
- P1.3 新增 `scripts/run_mingli_bench.py`：把 MingLi-Bench `data.json` 归一化到 baziqa 兼容格式（`case_id / question / options / answer / chart_input` 从 `fortune_api_results.json` 注入）
- P1.4 单元测试：
  - `tests/test_benchmark_shuffle_options.py`：确保 shuffle 后仍可正确评分
  - `tests/test_benchmark_self_consistency.py`：多次采样 → 众数聚合
  - `tests/test_mingli_bench_adapter.py`：验证归一化字段完整
- P1.5 Baseline 重跑：40×3 with shuffle-off vs shuffle-on，评估位置偏差影响
- **验收**：baseline 数据表出炉；后续 phase 有可参照的固定评测基准

### Phase 2 · Hybrid Retrieval + Reranker（5-7 天）

**目的**：把 evidence 检索从单一 TF-IDF-like 升级到工业主流。

- P2.1 依赖：`sentence-transformers==2.7.*`，本地缓存 `BAAI/bge-small-zh-v1.5`（≈100MB）与 `BAAI/bge-reranker-v2-m3`（≈600MB，可选量化）
- P2.2 新增 `case_dense_index.py`：
  - 索引：case 级别文本（question + option-derived answer + chart 关键项）→ dense vector
  - 首次运行离线构建缓存到 `.cache/case_dense_index.pkl`
  - CLI：`python scripts/build_dense_index.py --corpus ...`
- P2.3 修改 `case_index.py`：
  - `option_evidence()` 内保留原 sparse scorer；新增 dense scorer；两路各输出 top-K
  - 用 **RRF (k=60)** 融合成候选池 top-20
  - 用 bge-reranker 对 (question + option, candidate_fact) 精排到 top-2
- P2.4 兼容开关：`--retrieval-mode option_grounded_hybrid`（新）与旧 `option_grounded` 并存
- P2.5 单元测试：
  - `tests/test_case_dense_index.py`：dense 向量维度、缓存回读
  - `tests/test_hybrid_rrf.py`：合并顺序稳定性
  - `tests/test_reranker_stub.py`：reranker 输入输出 schema
- P2.6 离线评估（不调用 LLM）：40 case × option 的 gold-answer top1 rank 变化
- P2.7 在线评估：40×3 flash A/B
- **验收**：**T1 达标**（40×3 mean ≥ 30%，min ≥ 27.5%），gold top1 从 27.5% → ≥40%

### Phase 3 · Self-Consistency + 具体 Few-Shot（3-5 天）

**目的**：在 Phase 2 更好的 evidence 上做稳定的推理端聚合。

- P3.1 benchmark_runner 支持 SC 参数：`--n-samples 5 --temperature 0.4`（Phase 1 已铺路，Phase 3 打磨真实调用）
- P3.2 新增 `.tmp/fewshot/` 目录：从 corpus 里挑 3 条**已验证答对**的 family/health/relationship case，写成 `[观察→推理→结论→置信度]` 完整示例
- P3.3 `rag_prompt_builder.build_system_prompt()` 新参数 `fewshot_pool_path`：按 domain 匹配 1-2 条示例注入 prompt 顶部（不影响其他 domain）
- P3.4 单元测试：
  - `tests/test_fewshot_pool.py`：按 domain 抽题正确
  - `tests/test_self_consistency_majority.py`：五次采样 tie 情况
- P3.5 在线评估：40×3 with SC=3 + few-shot
- **验收**：**T1 稳定，T2 达标**（family+health ≥ 3/7），min ≥ 30%

### Phase 4 · 两阶段推理（3-5 天）

**目的**：让模型先独立分析、后针对 top-2 候选查证据，缓解 evidence 噪声。

- P4.1 新增 `two_stage_reasoning.py`：
  - Stage 1：`prompt = base + chart + question + options`（**不带 evidence**）→ 输出 top-2 候选 + 简短理由
  - Stage 2：`prompt = base + chart + question + options + evidence(top-2 only)` → 输出最终答案 + 置信度
  - Stage 1 与 Stage 2 都强制 CoT
- P4.2 benchmark_runner 新增 `--method two_stage_reasoning`
- P4.3 单元测试：`tests/test_two_stage_reasoning.py`（parser + fallback：Stage 1 输出解析失败时退化为单阶段）
- P4.4 在线评估：40×3 with SC=3 + few-shot + two_stage
- **验收**：稳态提升 ≥2pt 或 family/health 单域 ≥4/7；否则设开关默认关闭

### Phase 5 · 规则节点（Rule-as-Evidence）（5-7 天）

**目的**：把 bazi 领域规则显式化，作为独立 evidence 与 case fact 并行注入。

- P5.1 新增 `bazi_rules/rules.jsonl`：每条规则 `rule_id / text / trigger_conditions / domains`
  - 触发条件覆盖 chart_input 字段（day_master、wuxing_stats、shishen_stats、branch_relations、shensha、wuyun_liuqi、ziwei 十二宫）
  - 首批 30-50 条：family 15、health 10、relationship 10、annual_fortune 5、通用 10
- P5.2 新增 `rule_index.py`：
  - 加载 rules.jsonl → 索引
  - `match_rules(chart, domain, question, option) → List[RuleEvidence]`
  - 输出与 case fact evidence 同 schema，可被 hybrid retrieval 一起 rerank
- P5.3 `case_index.option_evidence()` 融合：`case_fact + rule` 一起进入 RRF + reranker
- P5.4 单元测试：
  - `tests/test_rule_index.py`：触发条件匹配
  - `tests/test_rule_evidence_schema.py`：与 case fact 输出兼容
- P5.5 在线评估：40×3 + MingLi-Bench 160
- **验收**：MingLi-Bench flash 达到 ≥50%（离 T3 目标 5pt）；40×3 保持 ≥35%

### Phase 6 · 稳定 + 收官（2-3 天）

- P6.1 把有效 phase 的默认开关切到 `on`，回归测试全部通过
- P6.2 更新 `docs/BAZI_ACCURACY_IMPROVEMENT_PLAN.md` 的“实际达到”栏
- P6.3 MingLi-Bench 双 provider（flash + pro）跑一次，作为长期基线
- P6.4 归档所有 phase 的 `.tmp/*_report.md`
- **验收**：**T3 达标**（MingLi-Bench flash ≥ 55%）或明确失败原因

---

## 5. 关键文件变更（预估）

| 文件 | 新增 / 修改 | 说明 |
|---|---|---|
| `benchmark_runner.py` | 修改 | shuffle-options、n_samples、aggregate |
| `case_index.py` | 修改 | 引入 hybrid + reranker 路径，保留旧路径 |
| `case_dense_index.py` | 新增 | dense embedding 缓存 + 检索 |
| `rag_prompt_builder.py` | 修改 | fewshot_pool 参数，chart_domain_summary 可选注入 |
| `two_stage_reasoning.py` | 新增 | 两阶段推理封装 |
| `rule_index.py` | 新增 | 规则节点匹配 |
| `bazi_rules/rules.jsonl` | 新增 | 30-50 条初版规则 |
| `scripts/build_dense_index.py` | 新增 | 离线构建 dense 索引 |
| `scripts/run_mingli_bench.py` | 新增 | MingLi-Bench 适配器 |
| `tests/test_benchmark_shuffle_options.py` | 新增 | shuffle 后评分正确 |
| `tests/test_benchmark_self_consistency.py` | 新增 | 众数聚合 |
| `tests/test_mingli_bench_adapter.py` | 新增 | 归一化 schema |
| `tests/test_case_dense_index.py` | 新增 | dense 索引缓存 |
| `tests/test_hybrid_rrf.py` | 新增 | RRF 融合 |
| `tests/test_reranker_stub.py` | 新增 | reranker schema |
| `tests/test_fewshot_pool.py` | 新增 | domain 抽题 |
| `tests/test_self_consistency_majority.py` | 新增 | tie 处理 |
| `tests/test_two_stage_reasoning.py` | 新增 | 阶段切换 + fallback |
| `tests/test_rule_index.py` | 新增 | 触发条件匹配 |
| `tests/test_rule_evidence_schema.py` | 新增 | schema 兼容 |
| `requirements.txt` | 修改 | 加 `sentence-transformers==2.7.*`、`torch>=2.0`（CPU 版即可）、`FlagEmbedding`（可选） |

---

## 6. 风险与回滚策略

| 风险 | 缓解 |
|---|---|
| bge 模型下载失败 / 内网无法访问 HF | 提前手工下载到 `.cache/models/`，脚本从本地路径加载 |
| reranker CPU 延迟过高 | rerank 只作用于 top-20 → top-2；可开关；必要时用 mini 版本 |
| Self-Consistency × 5 成本翻倍 | 默认 3，可关；对 40 题成本约 120 次调用/轮 |
| 两阶段推理引入更多 parser=None | Stage 1 解析失败自动 fallback 单阶段（Phase 4 已含） |
| 规则节点变成“抽象 guidance” 无收益 | 每条规则挂 `trigger_conditions`，只在命中时展示；ban 无触发规则 |
| shuffle-options 打乱评分 | 单元测试保证正确；同时保存原始 label ↔ shuffled label 映射 |
| 大改动导致 strict leak > 0 | CI 强制 `compute_retrieved_answer_leak --strict` 通过 |

**回滚原则**：每个 phase 结束后如果 T1/T2 未达标或 strict leak > 0，**默认开关切回 off**，代码保留、开关关闭；下一 phase 依赖 phase-N-1 通过。

---

## 7. 验收标准（对齐用户目标）

| 指标 | 现值 | Phase 2 目标 | Phase 3 目标 | Phase 5 目标 |
|---|---:|---:|---:|---:|
| baziqa 40×3 mean | 28.3% | ≥30% | ≥33% | ≥35% |
| baziqa 40×3 min | 27.5% | ≥27.5% | ≥30% | ≥32% |
| family+health 7-case | 0.67/7 | ≥1.5/7 | ≥3/7 | ≥3/7 |
| MingLi-Bench 160 flash | 未测 | ≥45% | ≥50% | ≥55% |
| strict leak | 0 | 0 | 0 | 0 |

如 Phase 2 结束未达到 30% mean，视为“hybrid+rerank 收益不足”，回滚 Phase 2 并直接进入 Phase 3（不叠加 hybrid）。

---

## 8. 时间估算

| Phase | 工时 | 里程碑 |
|---|---|---|
| P1 | 3-5 天 | shuffle + SC + MingLi 适配器 + baseline |
| P2 | 5-7 天 | hybrid + reranker + 40×3 A/B |
| P3 | 3-5 天 | SC + few-shot + family/health smoke |
| P4 | 3-5 天 | 两阶段推理 |
| P5 | 5-7 天 | 规则节点 + rules.jsonl 30-50 条 |
| P6 | 2-3 天 | 稳定 + 收官 |
| **合计** | **≈21-32 天** | 双基准双数据 |

---

## 9. 未决项

- 是否需要在 CI 里直接自动跑 MingLi-Bench 160 题？（默认：本地手工触发，避免每次 PR 都消耗大量 API）
- 是否引入 log-prob 聚合 vs 纯 majority？（Phase 1 里已留 `--aggregate` 参数，默认 majority）
- 规则库的 `trigger_conditions` DSL 语法（第一版建议 `{"day_master.wuxing":"火","wuxing_stats.strongest":"火"}` 这种简单键值，避免过度设计）

---

## 10. 规格自审 checklist

- [x] 无占位符（所有 phase 时间、目标数值、依赖版本都明确）
- [x] 无矛盾（Phase 4 与 Phase 5 均在 Phase 2 evidence 之上做，不冲突）
- [x] 范围明确（不做微调 / 云端 embedding / 多 Agent）
- [x] 有回滚策略（每 phase 开关默认 off）
- [x] 有量化验收（T1-T5）
- [x] 双基准（baziqa + MingLi-Bench）
- [x] 依赖列表清晰（sentence-transformers、torch cpu、可选 FlagEmbedding）
- [x] 每 phase 都有专属单元测试
