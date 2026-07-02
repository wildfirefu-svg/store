# BaziQA P0-P2 阶段总结

## 背景

本阶段围绕 BaziQA 2025 holdout 的 RAG + structured reasoning 评测进行迭代，目标是降低输出波动、提升检索质量，并验证默认 RAG 参数是否合理。

评测主数据集：

- `benchmark/datasets/baziqa_contest8_2025_holdout.jsonl`
- 默认样本数：40 cases
- 默认模型：`deepseek/deepseek-v4-pro`
- 默认温度：`temperature=0`
- 默认方法：`structured_reasoning`
- 默认 RAG：开启

相关代码与报告：

- [run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py)
- [case_index.py](file:///f:/project/agent/case_index.py)
- [bazi_features.py](file:///f:/project/agent/bazi_features.py)
- [rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py)
- [BAZIQA_PROJECT_ROADMAP.md](file:///f:/project/agent/docs/BAZIQA_PROJECT_ROADMAP.md)
- [BAZIQA_ACCEPTANCE_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCEPTANCE_REPORT.md)

## 阶段目标

| 阶段 | 目标 | 当前状态 |
|---|---|---|
| P0 | 验证 parser 稳定性与 RAG k 参数 | 已完成，未达准确率/稳定性验收线 |
| P1 | 默认 `rag_k=2`，增强结构化检索加权 | 已完成，测试通过 |
| P2 | 继续 Milestone C 检索质量升级并跑真实 API 验证 | 已完成，技术生效，但整体准确率提升未确认 |

## P0：Parser 稳定性与 k-ablation

### P0-1：新 parser / structured prompt 稳定性

报告：[BAZIQA_PARSER_STABILITY_REPORT.md](file:///f:/project/agent/docs/BAZIQA_PARSER_STABILITY_REPORT.md)

结果：

| Run | Correct / Total | Accuracy |
|---|---:|---:|
| 1 | 13 / 40 | 32.5% |
| 2 | 11 / 40 | 27.5% |
| 3 | 10 / 40 | 25.0% |

汇总：

| 指标 | 值 |
|---|---:|
| Mean | 28.3% |
| Min | 25.0% |
| Max | 32.5% |
| Stdev | 3.8 pp |
| Max-Min | 7.5 pp |

结论：

- `rag-structured` 三轮平均只有 **28.3%**，未达到 40% 目标。
- max-min 为 **7.5pp**，未达到 ≤5pp 稳定性目标。
- 新 parser / structured prompt 对格式可控性有帮助，但没有直接解决模型推理准确率和输出波动。

### P0-2：k-ablation

报告：[BAZIQA_K_ABLATION_REPORT.md](file:///f:/project/agent/docs/BAZIQA_K_ABLATION_REPORT.md)

分段有效结果：

| k | Correct / Total | Accuracy | Failed |
|---|---:|---:|---:|
| 1 | 8 / 39 | 20.5% | 1 |
| 2 | 11 / 40 | 27.5% | 0 |
| 3 | 9 / 39 | 23.1% | 1 |

结论：

- 单轮结果中 `k=2` 最好。
- `k=3` 不如 `k=2`，说明更多召回可能引入噪声。
- 因此默认 `rag_k` 已从 3 调整为 2。
- 但所有 k 都低于 35%，说明瓶颈不只是 k 的数量，而是检索质量和模型推理质量。

### P0 中发现并修复的问题

在排查 P0-2 时发现一个关键 bug：

- 原代码向 `build_system_prompt()` 传入 `top_k=rag_k`。
- 实际函数参数是 `k`。
- 已修复为 `k=rag_k`。

这个修复确保 RAG k 参数真正生效。

## P1：结构化检索质量升级

P1 的核心策略是不引入新依赖，先做可解释、可测试的本地检索增强。

### 实现内容

主要涉及：

- [run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py)
- [bazi_features.py](file:///f:/project/agent/bazi_features.py)
- [case_index.py](file:///f:/project/agent/case_index.py)
- [rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py)

完成内容：

1. 默认 `rag_k=2`。
2. `query_text` 进入检索特征。
   - 包含当前 case 的 question 和 options。
3. `CaseIndex` 增强结构化排序：
   - 同领域加权；
   - 性别匹配；
   - 年代接近；
   - 选项意图关键词匹配；
   - 地支文本重叠；
   - 稳定 tie-break。
4. RAG prompt / trace 输出：
   - `match_reasons`
   - `_score`
   - `匹配原因`
   - `检索分`

### P1 测试

专项测试：

```powershell
python -m pytest tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_features.py tests/test_benchmark_runner.py -q
```

结果曾验证为：

```text
36 passed
```

之后 P2 扩展后，同一组测试增长到 39 个并继续通过。

### P1 结论

P1 完成了默认参数与结构化检索基础能力升级，但 P1 的真实 API 结果仍不足以证明准确率已达到验收线。

P1 之后的判断是：

- `k=2` 应作为默认；
- 单靠结构化加权不足以达到 40%；
- 需要继续做 Milestone C 的检索质量升级。

## P2：Milestone C 检索质量升级

P2 继续在无新依赖前提下增强检索质量，重点是本地语义短语混合排序。

报告：[BAZIQA_P2_RETRIEVAL_REPORT.md](file:///f:/project/agent/docs/BAZIQA_P2_RETRIEVAL_REPORT.md)

### P2 初版实现

在 [case_index.py](file:///f:/project/agent/case_index.py) 中新增：

- 从 question/options/factual answer text 中抽取语义短语；
- 排序分数融合：
  - BM25；
  - P1 结构化分；
  - P2 `semantic_overlap`；
- RAG trace / prompt 输出 `semantic_overlap:*`。

### 初版 40 题真实 API 验证

报告：[run_ecdec259.md](file:///f:/project/agent/docs/p2_real_api_output/run_ecdec259.md)

| 指标 | 结果 |
|---|---:|
| Total | 40 |
| Correct | 9 |
| Accuracy | 22.5% |
| Evidence Coverage | 100% |
| Safety Score | 100% |

按领域：

| Domain | Correct / Total | Accuracy |
|---|---:|---:|
| career | 3 / 9 | 33.3% |
| relationship | 2 / 7 | 28.6% |
| family | 1 / 4 | 25.0% |
| unknown | 3 / 14 | 21.4% |
| annual_fortune | 0 / 2 | 0.0% |
| health | 0 / 3 | 0.0% |
| study | 0 / 1 | 0.0% |

结论：

- 初版 P2 40 题结果为 **22.5%**，低于 P1 k=2 单轮的 27.5%。
- trace 显示语义短语过宽，出现了 `出生`、`如何`、`此命` 等泛词匹配。
- 这些泛词很可能引入了检索噪声。

### P2 refinement：收紧语义短语过滤

随后对语义短语进行过滤：

- 过滤泛词：`出生`、`如何`、`此命`、`命主`、`发生`、`何事` 等；
- 过滤纯数字片段；
- 过滤以 `的` 开头的短语；
- 删除二字 gram，只保留信息量更高的三字/四字短语。

### 收紧后 10 题 smoke 验证

报告：[run_d33408bd.md](file:///f:/project/agent/docs/p2_refined_real_api_output/run_d33408bd.md)

| 指标 | 结果 |
|---|---:|
| Total | 10 |
| Correct | 5 |
| Accuracy | 50.0% |
| Evidence Coverage | 100% |
| Safety Score | 100% |

trace 检查：

- `semantic_overlap` 仍然生效；
- 已不再出现 `出生`、`如何`、`此命` 这类泛词；
- 但样本只有 10 题，不能作为最终 lift 结论。

### P2 测试

专项测试：

```powershell
python -m pytest tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_features.py tests/test_benchmark_runner.py -q
```

结果：

```text
39 passed
```

全量非 e2e：

```powershell
python -m pytest -q -m "not e2e"
```

结果：

```text
316 passed, 1 skipped, 7 deselected
```

## 当前总体结论

### 已完成的能力

1. 默认 `rag_k=2`。
2. RAG k 参数真实生效。
3. structured parser 和 `最终答案：X` 协议已落地。
4. per-case trace 已包含：
   - parser metadata；
   - rag_k；
   - retrieved case details；
   - score；
   - match_reasons。
5. P1 结构化检索加权已完成。
6. P2 本地语义短语混合排序已完成。
7. 检索过程变得可解释，能定位召回噪声。

### 尚未达成的目标

1. `rag-structured` 40 题准确率没有稳定达到 40%。
2. P0 稳定性 max-min 仍为 7.5pp，未达 ≤5pp。
3. P2 初版完整 40 题未提升，反而下降到 22.5%。
4. P2 refined 10 题为 50.0%，但样本太小，不能作为最终结论。

### 关键判断

当前核心瓶颈不是单纯 parser，也不是单纯 k 值，而是：

1. 检索噪声仍可能影响模型判断；
2. 模型在相同或近似 RAG context 下仍有推理波动；
3. corpus 缺少完整四柱 `chart_input`，暂时不能做真正的日主/月令/用神结构化加权；
4. `unknown`、`health`、`annual_fortune`、`study` 等领域短板明显。

## 下一步建议

### 优先级 1：跑 refined P2 的完整 40 题验证

当前最需要确认的是：10 题 smoke 的 50.0% 是否可复现到完整 40 题。

建议命令：

```powershell
$env:PYTHONUNBUFFERED="1"
python benchmark/runners/run_benchmark.py `
  --model-runner `
  --rag `
  --rag-corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl `
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl `
  --provider deepseek `
  --model deepseek-v4-pro `
  --method structured_reasoning `
  --max-cases 40 `
  --temperature 0 `
  --rag-k 2 `
  --case-details-jsonl .tmp/p2_refined_rag_k2_40_details.jsonl `
  --output-dir docs/p2_refined_40_output
```

判定规则：

- 如果 ≥30%，说明 refined P2 至少没有明显退化，可继续做重复稳定性测试。
- 如果 ≥35%，说明 refined P2 有实际 lift 候选价值。
- 如果 <27.5%，说明 semantic overlap 不适合默认启用，建议做开关或降低权重。

### 优先级 2：增加检索开关与 ablation

建议增加可配置项：

- `BAZI_RAG_SEMANTIC=1/0`
- `BAZI_RAG_SEMANTIC_WEIGHT`
- `BAZI_RAG_STRUCTURED_WEIGHT`

这样可以跑：

| 配置 | 目的 |
|---|---|
| BM25 only | 检索 baseline |
| BM25 + structured | P1 效果 |
| BM25 + structured + semantic | P2 效果 |
| semantic low weight | 判断语义分是否过强 |

### 优先级 3：补齐 corpus chart_input

当前 corpus 只有生日、性别、题目、选项、答案事实，缺少完整四柱结构。

如果能为历史 corpus 生成或补齐 chart_input，就可以继续做：

- 日主相同加权；
- 月令相同/相生加权；
- 五行结构相似度；
- 用神/忌神方向一致性；
- 大运/流年应期匹配。

这比当前纯文本/短语检索更接近命理推理本身。

### 优先级 4：领域专项修复

从 P2 40 题看，短板领域包括：

- health：0/3；
- annual_fortune：0/2；
- study：0/1；
- unknown：3/14。

建议下一阶段做 domain-specific prompt / retrieval rules，而不是继续泛化调权。

## 最终状态

P0-P2 的工程能力已经完成，但准确率目标尚未完成。

一句话总结：

> 我们已经把 RAG 从“不可解释的相似文本召回”推进到“可解释的结构化 + 语义短语混合召回”，并确认默认 `rag_k=2` 更合理；但真实 API 准确率仍未稳定过 40%，下一步必须用 refined P2 完整 40 题验证和检索 ablation 来判断 semantic overlap 是否应默认启用。
