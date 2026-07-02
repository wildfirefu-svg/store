# Phase 2 Report: Hybrid Retrieval + Reranker

> 生成时间：2026-07-02
> 执行说明：在线 A/B 未运行，原因见下文。

## 环境检查

- `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` 环境变量：未设置
- `.deepseek_key` / `.anthropic_key` 文件：存在（可读取 API Key）
- `sentence-transformers`：未安装
- 稠密向量缓存 `.cache/baziqa_dense_bge_small.pkl`：不存在

## 离线评估

数据来自 `.tmp/phase2_offline_baseline.json`：

| 指标 | Baseline (`option_grounded`) |
|---|---|
| total | 40 |
| gold-top1 | 10 |
| **gold-top1 rate** | **25.0%** |
| gold-top2 | 20 |
| gold-top2 rate | 50.0% |
| mean rank | 2.35 |

Hybrid 离线评估未运行：依赖 `sentence-transformers` 构建 `BAAI/bge-small-zh-v1.5` 稠密索引，但当前环境未安装该库，且受约束不得下载大模型文件。

## 在线 A/B (40 × 3 flash)

| 配置 | 状态 | mean | min | max |
|---|---|---|---|---|
| Baseline (`option_grounded_tfidf`) | **未运行** | — | — | — |
| Hybrid (`option_grounded_hybrid`) | **未运行** | — | — | — |

未运行原因：
- 虽然 API Key 文件存在，但 Hybrid 路径必须依赖本地稠密向量索引。
- `sentence-transformers` 未安装，且 HF/模型下载在当前环境不允许。
- 由于无法完成 Hybrid 在线 A/B，为避免消耗 API token 却得不到完整 A/B 结论，Baseline 在线 A/B 也一并跳过。

## Strict Leak

未检查（Hybrid 在线运行未执行，无 `.tmp/phase2_hybrid/option_grounded_hybrid_run*.jsonl` 文件）。

## Go / No-Go 决策

**决策：OPT-IN / 保留代码但不设为默认。**

理由：
- 离线 Baseline 指标符合预期（gold-top1 = 25.0%）。
- Hybrid 离线指标与在线 A/B 均无法在当前环境完成，缺少决策所需数据。
- 根据计划任务 8 决策表：结果混合 / 数据不足时，保留 `option_grounded_hybrid` 代码与测试，仅作为可选开关，不带入 Phase 3 默认配置。
- 后续在已安装 `sentence-transformers` 并下载 `BAAI/bge-small-zh-v1.5` 的环境中补跑在线 A/B 后，可重新评估是否将 Hybrid 设为默认。

## 最终回归测试

```bash
python -m pytest tests/test_case_dense_index.py tests/test_hybrid_rrf.py tests/test_reranker_stub.py tests/test_case_index_hybrid.py tests/test_rag_prompt_hybrid.py -q
```

结果：**12 passed in 0.38s**

## 备注

- 未修改计划文件 `docs/superpowers/plans/2026-07-02-phase2-hybrid-retrieval.md`。
- 未提交 `.tmp/` 下除本报告外的任何数据文件。
