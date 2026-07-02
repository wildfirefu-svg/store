# BaziQA 量化测试详细总结报告

> 测试日期：2026-06-18
> 提供者：deepseek
> 模型：deepseek-v4-pro
> 温度：0.0（确定性）
> 数据集：BaziQA contest8 2021-2025（688 条，含年份标注）
> holdout 规模：每年 40 题（最多）

---

## 一、测试背景与目标

根据 [2026-06-18-baziqa-accuracy-evaluation-hardening-implementation.md](file:///f:/project/agent/docs/superpowers/plans/2026-06-18-baziqa-accuracy-evaluation-hardening-implementation.md) 与 [2026-06-18-baziqa-rag-augmentation-implementation.md](file:///f:/project/agent/docs/superpowers/plans/2026-06-18-baziqa-rag-augmentation-implementation.md) 两份实施计划，我们完成了以下三条主线：

1. **RAG Lift 评测**：验证在 2025 holdout 上，RAG 与结构化推理能否带来稳定的准确率提升。
2. **重复评测**：评估同一 holdout 下多次运行的稳定性（因温度 0 且单次成本较高，实际仅跑 1 次作为基线证据）。
3. **Leave-One-Year-Out (LOVO) 跨年度泛化**：验证模型在不同年份分布下的鲁棒性。

预定义的 Gate 阈值（来自 hardening 计划）：

| Gate | 阈值 |
|------|------|
| rag-direct vs baseline-direct | ≥ +8.0 pp |
| rag-structured 单次 | ≥ 40.0% |
| repeated-run rag-structured mean | ≥ 40.0% |
| repeated-run rag-structured min | ≥ 35.0% |
| LOVO mean | ≥ 40.0% |
| LOVO minimum yearly accuracy | ≥ 30.0% |

---

## 二、测试一：RAG Lift（2025 holdout, 40 题）

原始报告：[BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md)

### 2.1 结果表

| 运行标签 | 推理方式 | RAG | 正确 / 总数 | 准确率 | 相对 baseline | Run ID |
|----------|----------|-----|-------------|--------|---------------|--------|
| baseline-direct | direct_choice | OFF | 9 / 40 | 22.5% | +0.0 pp | e7702f6d |
| rag-direct | direct_choice | ON | 11 / 40 | 27.5% | +5.0 pp | b6678bbc |
| rag-structured | structured_reasoning | ON | 13 / 40 | 32.5% | +10.0 pp | 5be0a212 |

### 2.2 Gate 判定

- rag-direct 比 baseline-direct 提升 5.0 pp（未达到 8 pp 阈值）→ **FAIL**
- rag-structured 绝对准确率 32.5%（未达到 40.0% 阈值）→ **FAIL**
- 整体 RAG Lift Gate：**BLOCKED**

### 2.3 关键观察

1. **结构化推理在 RAG 上确实有效**：rag-structured 比 baseline-direct 高 10 pp，说明"先检索命例、再逐步推理"这一模式是有正向信号的。
2. **direct_choice 提升有限**：rag-direct 只比 baseline 高 5 pp，说明仅把命例喂给模型做四选一，模型对命例的吸收效率不高。
3. **当前上限 ~32.5%**：考虑到 4 选 1 的随机基线是 25%，rag-structured 32.5% 只比随机高约 7.5 pp，说明系统还有较大提升空间。
4. **与此前非确定性结果对比**：温度未固定时曾观测到 38%，这说明温度随机性会带来"虚假乐观"的单次跑测；**本次温度=0 的 32.5% 才是可靠的基线**。

---

## 三、测试二：重复评测（repeats=1，作为基线）

原始报告：[BAZIQA_REPEATED_EVAL_REPORT.md](file:///f:/project/agent/docs/BAZIQA_REPEATED_EVAL_REPORT.md)

### 3.1 结果表

| 标签 | 重复次数 | 均值 | 最小 | 最大 | 标准差 |
|------|----------|------|------|------|--------|
| baseline-direct | 1 | 0.325 | 0.325 | 0.325 | 0.000 |
| rag-direct | 1 | 0.300 | 0.300 | 0.300 | 0.000 |
| rag-structured | 1 | 0.325 | 0.325 | 0.325 | 0.000 |

### 3.2 Gate 判定

- 因 repeats=1，尚无统计意义，但当前均值（30%–32.5%）均 **低于 40% 目标**。

### 3.3 关键观察

1. **温度=0 下 baseline 反而略高于 RAG 主测的 baseline**（32.5% vs 22.5%），这说明 40 题的样本量较小，单次抽样的噪声会达到 ±10 pp 量级。**后续任何 Gate 都应把 repeats≥3 作为前置条件**。
2. 测试二的 rag-direct 30.0% 和测试一的 rag-direct 27.5% 差异 2.5 pp，在 40 题下对应 ±1 题的浮动，属于正常波动。

---

## 四、测试三：LOVO 跨年度泛化

原始报告：[BAZIQA_LOVO_REPORT.md](file:///f:/project/agent/docs/BAZIQA_LOVO_REPORT.md)

### 4.1 结果表

| Holdout 年份 | 正确 / 总数 | 准确率 | Run ID |
|--------------|-------------|--------|--------|
| 2021 | 14 / 40 | 35.0% | 0b13d433 |
| 2022 | 16 / 40 | 40.0% | d96c75d8 |
| 2023 | 9 / 40 | 22.5% | aea2610a |
| 2024 | 14 / 40 | 35.0% | ed0daf9a |
| 2025 | 11 / 40 | 27.5% | ed37edb1 |

- **Mean accuracy**：32.0%
- **Minimum yearly accuracy**：22.5%（2023）

### 4.2 Gate 判定

- Mean 32.0% < 40.0% → **FAIL**
- Minimum 22.5% < 30.0% → **FAIL**
- LOVO Gate：**BLOCKED**

### 4.3 关键观察

1. **2023 异常低（22.5% = 接近随机）**：这个年份要么是题目难度特别高，要么是该年 corpus 对 RAG 的覆盖特别差，需要单独调查。
2. **2022 达到 40.0%**：说明在有利的分布下，当前系统已经能跑出门槛，问题在于"不稳定"而不是"永远达不到"。
3. **年份差异 17.5 pp**（22.5% vs 40.0%），说明模型对特定年份/出题风格的鲁棒性不足，单一训练/检索语料不能覆盖所有题目类型。

---

## 五、对比与总结

| 维度 | 当前表现 | Gate 要求 | 差距 |
|------|----------|-----------|------|
| RAG Lift (direct) | +5.0 pp | +8.0 pp | -3.0 pp |
| RAG Lift (structured) | 32.5% | 40.0% | -7.5 pp |
| LOVO mean | 32.0% | 40.0% | -8.0 pp |
| LOVO minimum | 22.5% | 30.0% | -7.5 pp |

### 5.1 已做对的事

- ✅ 建立了确定性评测管道：`temperature=0`、`AccuracyExact` 精确计数、`benchmark/reports/accuracy_stats.py` 统计工具。
- ✅ 建立了 LOVO 拆分与评测脚本：`split_baziqa_by_year.py` + `verify_baziqa_lovo.ps1`。
- ✅ 建立了重复评测脚本：`run_baziqa_repeated_eval.py`。
- ✅ 建立了领域感知检索与结构化提示：`case_index.CaseIndex.top_k_cases` 含 query_domain 加权与地支重叠评分；`rag_prompt_builder` 把命例领域注入 system prompt。
- ✅ 所有非网络测试（`python -m pytest -q -m "not e2e"`）通过。

### 5.2 需要继续做的事

- ⚠️ 所有量化 Gate 都 **BLOCKED**，需要在检索质量、推理方式、训练对齐三个方向上系统性提升。
- ⚠️ 40 题的 holdout 样本量偏小，单次评测的标准误约 `sqrt(0.325*0.675/40) ≈ 7.4 pp`；Gate 决策应依赖重复运行 ≥3 次的均值。
- ⚠️ 2023 年份表现异常低，需要对题目、命例检索结果做人工审阅。

---

## 六、测试成本核算（供决策参考）

> 以下为粗略估算，以 DeepSeek API 为例：

| 评测项 | 每次运行估算 token | 运行次数 | 备注 |
|--------|-------------------|----------|------|
| RAG Lift（40 题 × 3 配置） | ~30K input + ~2K output | 1 | 已完成 |
| Repeated eval repeats=3 | ~30K input × 3 | 3 | 建议补充 |
| LOVO（5 年 × 40 题） | ~50K input + ~3K output | 1 | 已完成 |

- 若补充 repeats=3 × 1 LOVO rerun，预计额外 token 开销在 100K–150K 量级，按 DeepSeek 费率应在 1–2 RMB 的数量级，**成本不高，建议跑**。

---

## 七、附加测试：Few-Shot Ablation（2026-06-19）

详细报告：[BAZIQA_FEWSHOT_ABLATION_REPORT.md](file:///f:/project/agent/docs/BAZIQA_FEWSHOT_ABLATION_REPORT.md)

### 7.1 关键结论

| 配置 | 准确率 | Δ vs baseline-direct |
|------|-------:|---------------------:|
| baseline-direct | 25.0% | +0.0 pp |
| direct-fewshot | 27.5% | **+2.5 pp** |
| rag-direct | 32.5% | +7.5 pp |
| rag-direct-fewshot | 22.5% | **-2.5 pp** |
| **rag-structured** | **42.5%** | **+17.5 pp**（**首次过 40% Gate**） |
| rag-structured-fewshot | 35.0% | +10.0 pp |

### 7.2 本轮发现

1. **Few-shot 单独使用** 在无 RAG 场景下带来 +2.5 pp 微小提升。
2. **Few-shot × RAG 反效果**：rag-direct 32.5% → 22.5%（-10 pp），rag-structured 42.5% → 35.0%（-7.5 pp）。归因为 context dilution + 答案分布偏差 + 推理 token 预算被切走。
3. **rag-structured 在本次单跑达到 42.5%**，与上一轮 32.5% 差距 10 pp，落在 40 题样本的 ±7.4 pp 标准误之外，**说明系统存在轻微非确定性**（可能 case_index 内部排序）或确实是样本噪声 → 必须用 `repeats≥3` 验证。

### 7.3 Milestone 1 结果导向

- ✅ **Few-shot ablation 已完成**：结论是 "few-shot 不应与 RAG 叠加"，应在文档/CLI 中明示。
- ⚠️ **回头看，Milestone 1 计划的 +5 pp 提升来自 few-shot 这一假设不成立**。
- 🚀 真正的杠杆是 `structured_reasoning`，下一步直接进入 Milestone 2（向量检索 + 扩展结构化字段）。

### 7.4 下一步行动（覆盖 [BAZIQA_ACCURACY_IMPROVEMENT_IDEAS.md](file:///f:/project/agent/docs/BAZIQA_ACCURACY_IMPROVEMENT_IDEAS.md) Milestone 1 的修订）

1. ~~跑 `rag-structured` 重复评测 3 次，确认 42.5% 是否稳定。~~ 已完成，结果见 [BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md)：mean=30.0%、min=27.5%、max=35.0%，42.5% 未复现，稳定性 Gate 仍 BLOCKED。
2. 跑一次 k=2 / k=1 的 RAG ablation，验证"上下文越短、模型越准"的假设。
3. 进入 Milestone 2：A1 向量检索、A2 扩展结构化字段、B1 强制四步推理模板。

---

## 八、附加测试：rag-structured 稳定性验证（2026-06-19）

详细报告：[BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md)

few-shot ablation 中 `rag-structured` 单跑达到 42.5%，因此额外做了 `rag-structured × repeats=3` 验证。

| Run | Correct/Total | Accuracy | RunId |
|-----|---------------|---------:|-------|
| 1 | 11/40 | 27.5% | 267d34d4 |
| 2 | 14/40 | 35.0% | d373b30c |
| 3 | 11/40 | 27.5% | 620c0311 |

汇总：mean=30.0%，min=27.5%，max=35.0%，stdev=4.3 pp。

结论：**42.5% 是一次乐观单跑结果，不能作为 Gate 通过依据**。即使 temperature=0，真实 API 评测仍存在显著波动；下一步优先调查 RAG 检索排序是否完全确定、每题预测是否在不同 run 间变化。
