# Phase 2 Report: Hybrid Retrieval + Reranker

> 生成时间：2026-07-02

## 环境检查

- `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` 环境变量：未设置
- `.deepseek_key` / `.anthropic_key` 文件：存在
- `sentence-transformers`：未安装（网络原因无法下载 transformers/torch 依赖）
- 替代方案：使用 scikit-learn TF-IDF 作为 lightweight dense fallback（`--model tfidf`）验证 hybrid 流程
- 稠密向量缓存 `.cache/baziqa_dense_tfidf.pkl`：已构建（33 cases，512-dim）

## 离线评估

| 指标 | Baseline (`option_grounded`) | Hybrid (`option_grounded_hybrid` + tfidf dense) |
|---|---|---|
| total | 40 | 40 |
| gold-top1 | 10 | 10 |
| **gold-top1 rate** | **25.0%** | **25.0%** |
| gold-top2 | 20 | 20 |
| gold-top2 rate | 50.0% | 50.0% |
| mean rank | 2.35 | 2.45 |

**说明：**
- Hybrid 流程已跑通（`build_dense_index.py` → `evaluate_hybrid_offline.py`）。
- 使用 TF-IDF 作为 dense fallback 时，指标与 baseline 持平，未观察到提升。
- 真实语义模型 `BAAI/bge-small-zh-v1.5` 尚未能下载验证；在当前网络受限环境下无法完成真实 dense 模型的离线/在线评估。

## 在线 A/B (40 × 3 flash)

| 配置 | 状态 | mean | min | max |
|---|---|---|---|---|
| Baseline (`option_grounded_tfidf`) | 未运行 | — | — | — |
| Hybrid (`option_grounded_hybrid`) | 未运行 | — | — | — |

未运行原因：
- 在线 A/B 需要 sentence-transformers 下载真实 dense 模型；当前环境无法完成安装。
- 为避免消耗 API token 却得不到完整 A/B 结论，Baseline 在线 A/B 也一并跳过。

## Strict Leak

未检查（Hybrid 在线运行未执行）。

## Go / No-Go 决策

**决策：OPT-IN / 保留代码但不设为默认。**

理由：
- Hybrid 代码路径、单元测试、CLI 配置均已实现并通过。
- 当前环境无法验证真实 dense 模型（bge-small-zh-v1.5）的效果。
- TF-IDF fallback 验证表明流程正确，但指标未提升；真实模型效果待补测。
- 根据计划任务 8 决策表：结果混合 / 数据不足时，保留 `option_grounded_hybrid` 代码与测试，仅作为可选开关，不带入 Phase 3 默认配置。

## 新增/修改文件

- 新增：`case_dense_index.py`、`scripts/build_dense_index.py`、`hybrid_retrieval.py`、`case_reranker.py`、`scripts/evaluate_hybrid_offline.py`、5 个测试文件
- 修改：`case_index.py`、`rag_prompt_builder.py`、`benchmark/runners/run_benchmark.py`、`scripts/run_baziqa_retrieval_ablation.py`、`benchmark/configs/baziqa_retrieval_configs.yaml`
- 额外修改：`case_dense_index.py` 增加 `tfidf` fallback；`scripts/build_dense_index.py` 使用 `CaseIndex` 聚合语料；`scripts/evaluate_hybrid_offline.py` 增加 `--dense-cache` 参数

## 最终回归测试

```bash
python -m pytest tests/test_case_dense_index.py tests/test_hybrid_rrf.py tests/test_reranker_stub.py tests/test_case_index_hybrid.py tests/test_rag_prompt_hybrid.py -q
```

结果：**12 passed**

## 后续行动

在已安装 `sentence-transformers` 并能下载 `BAAI/bge-small-zh-v1.5` 的环境中补跑：

```bash
python scripts/build_dense_index.py \
    --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl \
    --model BAAI/bge-small-zh-v1.5 \
    --cache .cache/baziqa_dense_bge_small.pkl

python scripts/evaluate_hybrid_offline.py \
    --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl \
    --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl \
    --retrieval-mode option_grounded_hybrid \
    --dense-model BAAI/bge-small-zh-v1.5 \
    --dense-cache .cache/baziqa_dense_bge_small.pkl \
    --output .tmp/phase2_offline_hybrid_bge.json
```
