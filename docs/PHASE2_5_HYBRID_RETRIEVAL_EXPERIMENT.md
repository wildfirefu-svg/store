# Phase 2.5 Hybrid Retrieval 实验报告

> **状态说明**：本报告记录 Phase 2.5 的离线修补实验。它证明检索候选有改善，但不代表 Phase 2 通过验收，也不代表 hybrid 默认启用。Phase 2 当前统一状态以 [PHASE2_STATUS_UNIFIED.md](file:///f:/project/agent/docs/PHASE2_STATUS_UNIFIED.md) 为准。

- 日期：2026-07-02
- 范围：`bge-reranker-v2-m3` 真重排可用性、expanded corpus、安全性校验、option-aware query 优化
- 结论：option-aware query + TF-IDF hybrid dense + expanded corpus 的离线指标有明显改善；`bge-reranker-v2-m3` 在当前 Windows Python 环境中原生崩溃，真实 rerank 评估暂时阻塞。

## 1. 本次改动

| 项目 | 状态 | 说明 |
|---|---|---|
| CrossEncoder 加载缓存 | 已完成 | `case_reranker.py` 使用 LRU cache，避免每个选项重复加载 reranker。 |
| Dense index 聚合输入修复 | 已完成 | `CaseIndex` 现在把聚合后的 `person_id/text_blob` 传给 dense index，避免运行时从原始 corpus row 构建空文本。 |
| Option-aware query | 已完成 | 查询显式包含 domain、question、clean option、option keywords、命盘结构化特征和原始 base text。 |
| Reranker passage | 已完成 | passage 显式包含 domain、命主、原答案、相关事实和部分全部事实，比单独 `fact_excerpt` 更适合 cross-encoder。 |
| Expanded corpus | 已验证 | 使用 `benchmark/datasets/baziqa_contest8_except_2025_corpus.jsonl`，648 rows，不含 2025 holdout。 |
| `bge-reranker-v2-m3` 真重排 | 阻塞 | 依赖已安装，但加载模型时 Python 进程以 Windows 原生错误 `3221225477` 退出，没有 Python traceback。 |

## 2. Holdout 泄漏检查

检查对象：

- holdout：`benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl`
- expanded corpus：`benchmark/datasets/baziqa_contest8_except_2025_corpus.jsonl`

结果：

```text
holdout rows 40
corpus rows 648
overlap full keys 0
corpus 2025 rows 0
```

说明：expanded corpus 没有包含 2025 rows，也没有与 holdout 在 `(source_year, case_id, person_id, question)` full-key 上重叠。

## 3. 离线评估结果

评估命令示例：

```powershell
python scripts\evaluate_hybrid_offline.py --dataset benchmark\datasets\baziqa_contest8_2025_holdout_enriched.jsonl --corpus benchmark\datasets\baziqa_contest8_except_2025_corpus.jsonl --retrieval-mode option_grounded_hybrid --dense-model tfidf --dense-cache .cache\dense_tfidf_corpus648_queryopt.pkl --output .tmp\phase2_hybrid_tfidf_queryopt_corpus648.json
```

| 实验 | corpus | dense | reranker | gold-top1 | gold-top2 | mean rank |
|---|---|---|---|---:|---:|---:|
| Baseline after query change | 2021-2024 enriched, 160 rows | 无 | 无 | 22.5% | 42.5% | 2.675 |
| Hybrid + query-opt | 2021-2024 enriched, 160 rows | TF-IDF | 无 | 30.0% | 42.5% | 2.600 |
| Hybrid + query-opt + expanded corpus | 2021-2024 except 2025, 648 rows | TF-IDF | 无 | 30.0% | 62.5% | 2.275 |

对比 Phase 2 原报告中的 best hybrid：

| 实验 | gold-top1 | gold-top2 | mean rank |
|---|---:|---:|---:|
| Phase 2 hybrid + bge-small dense | 25.0% | 50.0% | 2.45 |
| Phase 2.5 TF-IDF hybrid + query-opt + expanded corpus | 30.0% | 62.5% | 2.275 |

说明：expanded corpus 对 top2 和 mean rank 的提升更明显，gold-top1 只到 30%。这说明检索候选质量有改善，但最终 top1 决策仍可能需要 reranker 或答案聚合策略继续提升。

## 4. `bge-reranker-v2-m3` 阻塞详情

已安装依赖：

```text
torch 2.12.1+cpu
transformers 4.57.6
sentence_transformers 2.7.0
```

加载命令：

```powershell
$env:HF_HUB_DISABLE_XET='1'
python -c "from sentence_transformers import CrossEncoder; print('start'); m=CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512); print('loaded')"
```

结果：

```text
exit code 3221225477
```

该退出码通常代表 Windows 原生访问冲突或底层二进制崩溃。进程没有抛出 Python 异常，因此当前环境无法完成真实 `bge-reranker-v2-m3` 离线评估。

建议排查路径：

1. 在 Linux/WSL 或 CI Linux 环境重新加载 `BAAI/bge-reranker-v2-m3`；
2. 固定更保守的组合，例如 `torch==2.3.*`、`transformers==4.41.*`、`sentence-transformers==2.7.0`；
3. 如果仍在 Windows，先用更小 cross-encoder smoke model 验证 `CrossEncoder` 链路，再切回 v2-m3；
4. 将真实 rerank 评估单独拆成可失败的实验，不阻塞 TF-IDF hybrid + expanded corpus 的后续在线 A/B。

## 5. 决策建议

| 决策项 | 建议 |
|---|---|
| 是否默认启用 | 暂不默认启用。 |
| 是否继续保留代码 | 保留。此次 query/passage/dense 修复是正向基础设施改进。 |
| 是否值得在线 A/B | 可以考虑小规模跑 `Hybrid + query-opt + expanded corpus`，因为离线 top2 与 mean rank 改善明显。 |
| 是否继续追 reranker | 值得，但需要先换稳定运行环境完成真实 rerank。 |

最终结论：Phase 2.5 可以标为 **Engineering Improved / Reranker Runtime Blocked / Offline Candidate Improved**。当前最佳离线候选是 `option_grounded_hybrid + tfidf dense + expanded corpus + option-aware query`，结果为 gold-top1 30.0%、gold-top2 62.5%、mean rank 2.275。
