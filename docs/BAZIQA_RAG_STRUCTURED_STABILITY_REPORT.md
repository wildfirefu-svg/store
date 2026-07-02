# BaziQA RAG Structured Stability Report

> 日期：2026-06-19
> 目的：验证 few-shot ablation 中 `rag-structured=42.5%` 是否稳定
> 数据集：`benchmark/datasets/baziqa_contest8_2025_holdout.jsonl`
> Provider：deepseek
> Model：deepseek-v4-pro
> Method：structured_reasoning
> RAG：ON
> Temperature：0.0
> MaxCases：40
> Repeats：3

---

## 一、重复评测结果

| Run | Correct/Total | Accuracy | RunId |
|-----|---------------|---------:|-------|
| 1 | 11/40 | 27.5% | 267d34d4 |
| 2 | 14/40 | 35.0% | d373b30c |
| 3 | 11/40 | 27.5% | 620c0311 |

| Label | Runs | Mean | Min | Max | Stdev |
|-------|-----:|-----:|----:|----:|------:|
| rag-structured | 3 | 30.0% | 27.5% | 35.0% | 4.3 pp |

---

## 二、Gate 判定

| Gate | 阈值 | 当前结果 | 判定 |
|------|------|----------|------|
| repeated mean | ≥ 40.0% | 30.0% | FAIL |
| repeated min | ≥ 35.0% | 27.5% | FAIL |
| single-run optimistic result | 42.5% | 无法复现 | FAIL |

最终状态：**BLOCKED**

---

## 三、关键结论

1. few-shot ablation 中的 `rag-structured=42.5%` 是一次**乐观单跑结果**，不能作为稳定 Gate 依据。
2. 重复 3 次后，`rag-structured` 均值只有 **30.0%**，最低 **27.5%**，与 Gate 仍有明显差距。
3. 即使 `temperature=0.0`，真实 API 评测仍出现大幅波动，说明系统存在以下至少一种情况：
   - 模型服务端仍有非完全确定性；
   - RAG 检索排序存在未固定的 tie-break；
   - 输出解析对边界答案较敏感；
   - 40 题样本量偏小，单题差异会放大为 2.5 pp。
4. 当前最可靠的结论不是"rag-structured 已过线"，而是：**structured reasoning 有正向信号，但尚未稳定达到可验收水平。**

---

## 四、对 few-shot ablation 结论的修正

原 few-shot ablation 观察到：

- `rag-structured` 单跑：42.5%
- `rag-structured-fewshot` 单跑：35.0%

经 repeats=3 验证后，应修正为：

- `rag-structured` 的稳定均值约为 **30.0%**；
- `rag-structured-fewshot=35.0%` 仍不能证明 few-shot 有益，因为它也是单跑；
- few-shot 与 RAG 叠加是否稳定有害，需要在同样 repeats=3 下再验证，但基于 `rag-direct-fewshot=22.5%` 和上下文稀释风险，仍不推荐默认开启。

---

## 五、下一步建议

优先级从高到低：

1. ~~**修复确定性问题**：让 RAG 检索排序完全可复现，给所有 tie-break 添加稳定排序键，例如 `person_id/case_id`。~~ 已完成：`CaseIndex.top_k_cases` 对同分命例按 `person_id/birth_year/name` 稳定排序，并新增 `test_tie_break_is_stable_across_corpus_order`。
2. ~~**落盘每题预测明细**：比较三次 run 中哪些题反复变化，区分"模型输出不稳定"与"检索结果不稳定"。~~ 已完成：`run_benchmark.py` 新增 `--case-details-jsonl`，每题输出 `raw_answer/predicted_answer/correct/rag_trace`。
3. **跑 k=1/k=2/k=3 ablation**：验证当前 top-k 是否引入噪声命例。
4. **进入 Milestone 2**：向量检索 + 日主/月令/五行结构化加权，提升检索质量，而不是继续增加 prompt 示例。

> 详细路线图见 [BAZIQA_PROJECT_ROADMAP.md](file:///f:/project/agent/docs/BAZIQA_PROJECT_ROADMAP.md)。

---

## 七、确定性修复记录

2026-06-19 已完成 RAG 检索排序确定性修复：

- 修改：[case_index.py](file:///f:/project/agent/case_index.py) 的 `CaseIndex.top_k_cases`。
- 修复点：原实现只按分数降序排序，同分命例会继承 corpus 行顺序；现在排序键为 `(-score, person_id, birth_year, name)`。
- 新增测试：[test_case_index.py](file:///f:/project/agent/tests/test_case_index.py) 的 `test_tie_break_is_stable_across_corpus_order`。
- 验证命令：
  ```powershell
  python -m pytest tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_features.py tests/test_benchmark_runner.py -q
  ```
- 验证结果：`28 passed`。

说明：这只消除了 RAG 检索的一个确定性风险，不保证真实模型 API 完全确定。

---

## 八、每题明细落盘记录

2026-06-19 已完成每题预测明细与 RAG trace 落盘能力：

- 修改：[run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py) 新增 `--case-details-jsonl` 参数。
- 每题 JSONL 字段包括：`case_id/domain/question/expected_answer/predicted_answer/raw_answer/correct/evidence_coverage/safety_score/rag_trace`。
- `rag_trace` 包含每个检索命例的 `rank/person_id/name/birth_year/gender/domains/facts`。
- 新增测试：[test_benchmark_runner.py](file:///f:/project/agent/tests/test_benchmark_runner.py) 覆盖 JSONL 落盘和 RAG trace 内容。
- 验证命令：
  ```powershell
  python -m pytest tests/test_benchmark_runner.py tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_features.py -q
  ```
- 验证结果：`30 passed`。

下一步可以用该参数重跑 `rag-structured` 小样本或 k-ablation，直接比较每题检索命例与模型答案差异。

---

## 九、Trace 定位实验记录

2026-06-19 已完成 2025 holdout 前 10 题 `rag-structured × repeats=3` 定位实验，报告见 [BAZIQA_TRACE_DIAGNOSIS_REPORT.md](file:///f:/project/agent/docs/BAZIQA_TRACE_DIAGNOSIS_REPORT.md)。

关键结果：

- 三次准确率：50.0%、60.0%、40.0%。
- 预测答案不稳定：7/10。
- 正误发生翻转：4/10。
- RAG top-k 不稳定：0/10。

结论：本次样本中 RAG top-k 完全稳定，主要波动来自模型/API 在复杂长推理任务中的输出不稳定，而不是检索排序变化。下一步优先降低模型自由度，例如强制输出每个选项置信度并固定最后一行为 `最终答案：X`；同时继续做 k=1/k=2/k=3 ablation 验证命例噪声。

---

## 十、命令记录

```powershell
python scripts/run_baziqa_repeated_eval.py \
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl \
  --provider deepseek \
  --model deepseek-v4-pro \
  --max-cases 40 \
  --repeats 3 \
  --temperature 0 \
  --configs rag-structured \
  --output docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md
```

脚本改动：

- [scripts/run_baziqa_repeated_eval.py](file:///f:/project/agent/scripts/run_baziqa_repeated_eval.py) 新增 `--configs` 参数，可只跑 `rag-structured`，避免重复跑 baseline/direct 浪费 API 成本。
