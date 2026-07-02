# Phase 2 统一状态说明

- 日期：2026-07-02
- 适用范围：Phase 2 Hybrid Retrieval + Reranker、k-ablation、Phase 2.5 检索修补实验
- 结论：**Phase 2 工程实现完成，但原始验收未通过；Phase 2.5 有离线改善，但不默认启用；下一步应进入 Phase 3 的抗位置偏差推理稳定化。**

## 1. 最终状态

| 模块 | 状态 | 说明 |
|---|---|---|
| Phase 2 工程实现 | Engineering Done | `option_grounded_hybrid`、dense index、RRF、reranker wrapper、离线评估脚本与相关测试已实现。 |
| Phase 2 原始验收 | Evaluation NO-GO | 原始 hybrid 离线 gold-top1 未提升到目标；在线 40×3 A/B 未运行；strict leak 未在 hybrid 在线路径完整验证。 |
| k-ablation | Incomplete / Diagnostic Only | 每个 k 只完成 1 run，run2/run3 为空；可作为诊断材料，不能作为完整 Phase 2 验收。 |
| Phase 2.5 检索修补 | Offline Candidate Improved | `option-aware query + TF-IDF hybrid + expanded corpus` 离线改善到 gold-top1 30.0%、gold-top2 62.5%、mean rank 2.275。 |
| `bge-reranker-v2-m3` 真 rerank | Runtime Blocked | 当前 Windows 环境加载模型原生崩溃，未完成真实 rerank 评估。 |
| 默认启用 | No | 不把 hybrid / Phase 2.5 候选设为默认。 |
| 下一阶段 | Phase 3 | 重点转向 Self-Consistency、few-shot 和 anti-position-bias prompt，而不是继续大规模 Phase 2 在线 A/B。 |

统一标签：

```text
Phase 2 = Engineering Done / Evaluation NO-GO
Phase 2.5 = Offline Candidate Improved / Reranker Runtime Blocked
Recommended Next = Phase 3 Anti-position-bias Reasoning Stabilization
```

## 2. 依据文档

| 文档 | 当前作用 | 统一解释 |
|---|---|---|
| [BAZIQA_K_ABLATION_REPORT.md](file:///f:/project/agent/docs/BAZIQA_K_ABLATION_REPORT.md) | k-ablation 诊断报告 | 说明 k 值不是主要瓶颈，但实验未跑满 3 repeats，不能作为完整验收。 |
| [BAZIQA_PHASE2_RETRIEVAL_OPTIMIZATION_PLAN.md](file:///f:/project/agent/docs/BAZIQA_PHASE2_RETRIEVAL_OPTIMIZATION_PLAN.md) | 中途优化计划 | 记录当时环境变量、CaseIndex 初始化、score=None 等诊断；其中部分问题已被 Phase 2.5 修补。 |
| [PHASE2_5_HYBRID_RETRIEVAL_EXPERIMENT.md](file:///f:/project/agent/docs/PHASE2_5_HYBRID_RETRIEVAL_EXPERIMENT.md) | Phase 2.5 结果报告 | 当前最接近可用的检索候选，但仍只证明离线候选改善，不证明线上达标。 |
| [2026-07-02-phase2-hybrid-retrieval.md](file:///f:/project/agent/docs/superpowers/plans/2026-07-02-phase2-hybrid-retrieval.md) | Phase 2 实施计划 | 作为实现历史保留；状态以本统一说明为准。 |
| [PHASE1_BASELINE_SUMMARY.md](file:///f:/project/agent/docs/PHASE1_BASELINE_SUMMARY.md) | Phase 1 baseline | 提供进入 Phase 2/3 的最新基线，尤其是 shuffle-on mean 18.3% 的风险信号。 |

## 3. 关键证据

### 3.1 Phase 1 最新 baseline 改变了后续判断

| 指标 | 结果 | 含义 |
|---|---:|---|
| BaziQA shuffle-off 40×3 | 28.3% mean | 原始 baseline。 |
| BaziQA shuffle-on(seed=42) 40×3 | 18.3% mean | 比 shuffle-off 低 10.0pp，说明选项顺序敏感性严重。 |
| MingLi-Bench 官方 2025 20 题 smoke | 60.0% | 官方 MingLi 链路可用，但只是 20 题 smoke，不代表 160 题长期指标。 |

结论：后续不应只优化 shuffle-off；任何进入 Phase 3/4/5 的候选都要至少报告 shuffle-on 风险。

### 3.2 k-ablation 没有完整验收价值

[BAZIQA_K_ABLATION_REPORT.md](file:///f:/project/agent/docs/BAZIQA_K_ABLATION_REPORT.md) 中的结果：

| k | runs | mean | 说明 |
|---:|---:|---:|---|
| 1 | 1 | 20.5% | 只完成单 run。 |
| 2 | 1 | 27.5% | 单 run best，但仍低于目标。 |
| 3 | 1 | 23.1% | 只完成单 run。 |

原报告记录 run2/run3 为空，因此该实验只能说明：

1. 当前 evidence k 值不是主要提升杠杆；
2. 检索链路当时存在同质化、score 缺失或初始化问题；
3. 不能用它证明 Phase 2 完整完成。

### 3.3 Phase 2 原始 hybrid 未达标

原 Phase 2 报告记录：

| 实验 | gold-top1 | gold-top2 | mean rank |
|---|---:|---:|---:|
| baseline option_grounded | 25.0% | 50.0% | 2.35 |
| hybrid + TF-IDF dense | 25.0% | 50.0% | 2.45 |
| hybrid + bge-small dense | 25.0% | 50.0% | 2.45 |

结论：原始 hybrid 没有带来离线 gold-top1 提升，在线 A/B 因此未运行，决策应保持 NO-GO。

### 3.4 Phase 2.5 有改善但不足以默认启用

[PHASE2_5_HYBRID_RETRIEVAL_EXPERIMENT.md](file:///f:/project/agent/docs/PHASE2_5_HYBRID_RETRIEVAL_EXPERIMENT.md) 中当前最佳离线候选：

| 实验 | corpus | dense | reranker | gold-top1 | gold-top2 | mean rank |
|---|---|---|---|---:|---:|---:|
| Hybrid + query-opt + expanded corpus | 648 rows | TF-IDF | 无 | 30.0% | 62.5% | 2.275 |

这说明候选召回质量有改善，尤其 top2 和 mean rank 改善明显。但它仍缺：

- bge-reranker-v2-m3 真实 rerank；
- 线上 40×3 flash A/B；
- shuffle-on 条件验证；
- hybrid strict leak 完整在线检查；
- gold-top1 ≥40% 的原 Phase 2 离线目标。

因此不能默认启用。

## 4. 决策

| 决策项 | 结论 |
|---|---|
| 是否继续把 Phase 2 当主线推进 | 不建议。 |
| 是否回滚 Phase 2 代码 | 不回滚，保留为 opt-in 候选。 |
| 是否默认启用 hybrid | 不启用。 |
| 是否补跑完整 40×3 hybrid | 暂不建议，除非先通过小规模 shuffle-on sanity。 |
| 是否继续追 bge-reranker | 可以，但作为独立环境问题处理，不阻塞 Phase 3。 |
| 下一步主线 | Phase 3：Self-Consistency + anti-position-bias few-shot。 |

## 5. 推荐下一步

### 5.1 Phase 2 收尾

只做低成本收尾：

1. 保留 `option_grounded_hybrid + TF-IDF dense + expanded corpus + option-aware query` 作为候选检索后端；
2. 如果要在线验证，只跑小型 sanity：8-case stratified × 2 repeats，shuffle-off 和 shuffle-on 各一组；
3. 不在当前阶段跑完整 40×3 hybrid A/B；
4. 不把 bge-reranker-v2-m3 作为 Phase 3 的阻塞项。

### 5.2 Phase 3 主线

Phase 3 不应只理解为“多采样 + few-shot”，而应明确为：

```text
Phase 3 = Anti-position-bias Reasoning Stabilization
```

建议实验臂：

| Arm | 配置 | 目的 |
|---|---|---|
| A0 | `option_grounded_tfidf`, n=1, shuffle-off | 对齐 28.3% baseline。 |
| A1 | `option_grounded_tfidf`, n=1, shuffle-on | 对齐 18.3% shuffle 风险基线。 |
| A2 | `option_grounded_tfidf`, SC=3, shuffle-on | 评估 majority vote 是否缓解位置偏差和单次不稳定。 |
| A3 | anti-position-bias few-shot, n=1, shuffle-on | 评估示例是否改善选项文本对齐。 |
| A4 | few-shot + SC=3, shuffle-on | Phase 3 主候选。 |

Phase 3 的首要目标不应设成直接 35%，而应先设为：

| 指标 | 最低 sanity 目标 |
|---|---:|
| shuffle-on mean | 从 18.3% 提到 ≥23% |
| parser_valid | ≥95% |
| strict leak | 0 |
| MingLi 2025 20 题 smoke | 不显著低于 60.0% |

如果 sanity 通过，再进入 20-case smoke 和 40×3 正式评估。

## 6. 文档口径

后续引用 Phase 2 时，统一使用以下表述：

```text
Phase 2 工程实现已完成，但原始评估未通过。k-ablation 不完整，仅作诊断；原 hybrid 离线无收益；Phase 2.5 通过 option-aware query 与 expanded corpus 获得离线候选改善，但未完成 reranker、在线 A/B 和 shuffle-on 验证。因此 hybrid 不默认启用，下一步主线进入 Phase 3 的抗位置偏差推理稳定化。
```
