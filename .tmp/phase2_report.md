# Phase 2 Report: Hybrid Retrieval + Reranker

> 生成时间：2026-07-02
> 更新时间：2026-07-02

## 环境检查

- `sentence-transformers`：已安装（2.7.0，通过清华镜像）
- `torch`：已安装（2.12.1）
- `BAAI/bge-small-zh-v1.5` 模型：已下载并缓存
- 稠密向量缓存：
  - `.cache/baziqa_dense_tfidf.pkl`（TF-IDF fallback，33 cases，512-dim）
  - `.cache/baziqa_dense_bge_small.pkl`（BAAI/bge-small-zh-v1.5，33 cases，512-dim）

## 离线评估

| 指标 | Baseline (`option_grounded`) | Hybrid + tfidf dense | Hybrid + bge-small dense |
|---|---|---|---|
| total | 40 | 40 | 40 |
| gold-top1 | 10 | 10 | 10 |
| **gold-top1 rate** | **25.0%** | **25.0%** | **25.0%** |
| gold-top2 | 20 | 20 | 20 |
| gold-top2 rate | 50.0% | 50.0% | 50.0% |
| mean rank | 2.35 | 2.45 | 2.45 |

**说明：**
- Baseline 与两种 Hybrid 变体的离线 gold-top1 率完全一致（25.0%）。
- 在当前 33-case 语料库上，`option_grounded_hybrid` 的 dense + RRF 融合未带来离线指标提升。
- 可能原因：
  1. 语料库规模较小（33 cases），dense 检索的召回优势难以体现。
  2. 选项级 query 仅简单拼接 `question + option_text`，未针对选项文本做语义对齐。
  3. 尚未启用 cross-encoder reranker。
  4. `BAAI/bge-small-zh-v1.5` 在该任务上的零样本语义匹配能力有限。

## 在线 A/B (40 × 3 flash)

| 配置 | 状态 | mean | min | max |
|---|---|---|---|---|
| Baseline (`option_grounded_tfidf`) | 未运行 | — | — | — |
| Hybrid (`option_grounded_hybrid`) | 未运行 | — | — | — |

未运行原因：离线评估未显示提升；在线 A/B 会消耗 API token，需先确认是否继续。

## Strict Leak

未检查（Hybrid 在线运行未执行）。

## Go / No-Go 决策

**决策：NO-GO / 保留代码但不设为默认。**

理由：
- 离线 gold-top1 率未从 25.0% 提升到目标 40%。
- Hybrid 路径代码、测试、CLI 配置完整保留，作为可选开关。
- 默认 yaml 配置中仍只保留 `option_grounded_tfidf`。
- 进入 Phase 3 时不叠加 hybrid；后续可尝试：
  - 引入 cross-encoder reranker
  - 更大的语料库
  - 选项感知的 query 构造
  - 领域特定的 embedding 模型微调

## 新增/修改文件

- 新增：`case_dense_index.py`、`scripts/build_dense_index.py`、`hybrid_retrieval.py`、`case_reranker.py`、`scripts/evaluate_hybrid_offline.py`、5 个测试文件
- 修改：`case_index.py`、`rag_prompt_builder.py`、`benchmark/runners/run_benchmark.py`、`scripts/run_baziqa_retrieval_ablation.py`、`benchmark/configs/baziqa_retrieval_configs.yaml`
- 额外修改：`case_dense_index.py` 增加 `tfidf` fallback；`case_index.py` 缓存 SentenceTransformer 实例；`scripts/build_dense_index.py` 使用 `CaseIndex` 聚合语料；`scripts/evaluate_hybrid_offline.py` 增加 `--dense-cache` 参数

## 最终回归测试

```bash
python -m pytest tests/test_case_dense_index.py tests/test_hybrid_rrf.py tests/test_reranker_stub.py tests/test_case_index_hybrid.py tests/test_rag_prompt_hybrid.py -q
```

结果：**12 passed**

## 备注

- 真实 dense 模型 `BAAI/bge-small-zh-v1.5` 已完成评估；效果与 TF-IDF fallback 持平。
- 如要启用 reranker 进一步验证，可运行：
  ```bash
  python scripts/evaluate_hybrid_offline.py \
      --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl \
      --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl \
      --retrieval-mode option_grounded_hybrid \
      --dense-model BAAI/bge-small-zh-v1.5 \
      --dense-cache .cache/baziqa_dense_bge_small.pkl \
      --reranker-model BAAI/bge-reranker-v2-m3 \
      --output .tmp/phase2_offline_hybrid_bge_reranker.json
  ```
