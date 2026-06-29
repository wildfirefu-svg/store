# BaziQA 选项驱动证据检索重设计

日期：2026-06-29

## 1. 背景

BaziQA Hybrid Stage 1 最终 gate 判定为 `ROLLBACK`。

Stage 1 主证据如下：

| 项 | 结果 |
|---|---:|
| 最佳 flash 配置 | `tfidf_vector`，mean 27.5% |
| 最佳 pro Top-2 配置 | `tfidf_vector`，mean 25.8% |
| pro 三次运行结果 | `10/40`、`12/40`、`9/40` |
| strict retrieved-answer leak | 0.0% |
| Stage 1 gate | `ROLLBACK` |

当前检索机制会检索相似历史命例，并把它们作为宽泛上下文注入 prompt。这个机制没有带来稳定的选择题准确率。失败模式说明，“相似命例”本身还不够：模型仍然需要自己判断这些命例如何映射到 A/B/C/D 选项，而这个映射过程不稳定。

Task 5 的 domain subsets 也显示出明显分布差异：

| domain | pro Top-2 信号 |
|---|---|
| `annual_fortune` | 强，两个 Top-2 配置 mean 都是 66.7% |
| `health` | 部分有效，一个 pro 配置通过 |
| `relationship` | blocked |
| `unknown` | blocked |

本次重设计的目标是：把检索材料从“宽泛相似案例上下文”转成“针对每个候选选项的证据”，让证据可以直接支持、反驳或无法支持某个答案选项。

## 2. 问题陈述

当前流程是以案例为中心：

```text
当前命盘 + 题目 -> 检索相似案例 -> 注入案例摘要 -> 模型选择 A/B/C/D
```

这个流程有三个问题：

1. 证据没有对齐到具体答案选项。
2. 检索案例以叙事事实呈现，而不是以“判断原语”呈现。
3. 模型在内部隐式完成“证据到选项”的映射，所以即使检索结果稳定，重复运行也可能给出不同答案。

新流程应该改成以选项为中心：

```text
当前命盘 + 题目 + 每个选项 -> 分别检索选项证据 -> 逐选项比较证据 -> 模型选择 A/B/C/D
```

## 3. 目标

1. 构建 option-grounded retrieval，对 A/B/C/D 分别检索证据。
2. 每条注入证据都必须能追溯到来源案例和匹配原因。
3. 保持严格 holdout 隔离。
4. 初版实现保持本地、确定性；除最终模型调用外不引入随机性。
5. 输出 trace，用于诊断错误来自检索、证据排序还是模型选择。
6. 让下一轮 gate 从 Stage 1 `ROLLBACK` 至少推进到 `GRAY_A`，并保留通往 `PASS` 的路径。

## 4. 非目标

1. 初版不引入外部向量数据库基础设施。
2. 在证明方案有效前，不手工标注大规模 evidence corpus。
3. 不在既有评测协议之外用完整 2025 holdout 答案标签做调参。
4. 检索、prompt 构造和证据排序阶段不得使用当前题标准答案标签。
5. domain subset 的收益不能直接等价为完整 Stage 1 成功，除非 primary holdout gate 通过。

## 5. 设计方案

### 5.1 新检索单元：OptionEvidence

每个选项都有自己的 evidence list。

```json
{
  "option_label": "B",
  "option_text": "2024年事业有明显转折",
  "evidence": [
    {
      "case_id": "2021_xxx",
      "person_id": "p123",
      "score": 0.72,
      "stance": "support",
      "match_reasons": ["domain:annual_fortune", "option_keyword:转折", "chart_feature:食伤生财"],
      "fact_excerpt": "流年变化明显，事业发生转折 -> 事业调整",
      "source_domain": "annual_fortune",
      "source_answer_option_text": "事业调整"
    }
  ]
}
```

必需字段：

| 字段 | 含义 |
|---|---|
| `option_label` | `A/B/C/D` |
| `option_text` | 当前题的选项文本 |
| `case_id` | 来源 corpus 行或聚合后的 person id |
| `score` | 确定性检索分数 |
| `stance` | `support`、`contradict` 或 `related` |
| `match_reasons` | 可读的评分组成 |
| `fact_excerpt` | 展示给模型的短证据文本 |
| `source_domain` | 来源行/案例的 domain |
| `source_answer_option_text` | 历史题正确选项文本，不是当前题答案 |

初版可以只输出 `support` 和 `related`；等负向匹配可靠后再加入 `contradict`。

### 5.2 Option-grounded retrieval API

在现有 case-level retrieval 旁边新增方法：

```python
CaseIndex.option_evidence(
    features,
    question: str,
    options: list[str],
    domain: str | None = None,
    k_per_option: int = 2,
) -> dict[str, list[dict]]
```

期望输出：

```python
{
    "A": [evidence_a1, evidence_a2],
    "B": [evidence_b1, evidence_b2],
    "C": [evidence_c1, evidence_c2],
    "D": [evidence_d1, evidence_d2],
}
```

评分组成：

| 组件 | 目的 |
|---|---|
| domain match | 尽量让证据落在当前题所属 domain 内 |
| option keyword overlap | 让证据对齐到候选答案文本 |
| question keyword overlap | 保留题目意图 |
| chart structure overlap | 比较抽取出的命盘结构特征 |
| annual-fortune temporal cues | 对流年/年份/大运类问题增强时间线索 |
| generic penalty | 惩罚 `情况`、`容易`、`判断` 这类泛化重叠 |
| source diversity penalty | 防止一个人/一个案例垄断四个选项证据 |

评分器需要把每个正负评分组件都记录到 `match_reasons`。

### 5.3 Prompt 格式

prompt 应该用“选项证据块”替代旧的宽泛相似案例块。

```text
<选项证据>
A. {option_text}
- support/related evidence 1: ...
- support/related evidence 2: ...

B. {option_text}
- support/related evidence 1: ...
- support/related evidence 2: ...

C. {option_text}
- 暂无强证据

D. {option_text}
- support/related evidence 1: ...
</选项证据>
```

模型必须在最终答案前输出逐选项证据表：

```text
A: 支持/反驳/无证据；理由：...
B: 支持/反驳/无证据；理由：...
C: 支持/反驳/无证据；理由：...
D: 支持/反驳/无证据；理由：...
最终答案：X
```

最终答案解析器保持不变：`最终答案：X` 仍然具有最高优先级。

### 5.4 Trace 格式

per-case detail JSONL 需要包含 option evidence。

```json
{
  "case_id": "2025_001",
  "domain": "annual_fortune",
  "predicted_answer": "B",
  "expected_answer": "B",
  "correct": true,
  "retrieval_mode": "option_grounded",
  "option_evidence": {
    "A": [{"case_id": "...", "score": 0.31, "match_reasons": ["..."]}],
    "B": [{"case_id": "...", "score": 0.72, "match_reasons": ["..."]}],
    "C": [],
    "D": [{"case_id": "...", "score": 0.28, "match_reasons": ["..."]}]
  },
  "evidence_coverage": {
    "A": 1,
    "B": 2,
    "C": 0,
    "D": 1
  }
}
```

Trace 不变量：

1. 每个选项 key 都必须存在。
2. 每条 evidence 都必须有 `case_id`、`score`、`match_reasons` 和 `fact_excerpt`。
3. 检索输入中不得使用当前题答案标签。
4. index 不得加载 holdout 文件。
5. 当前题标准答案只能出现在模型执行后的 scorer output 字段中，不能出现在检索上下文中。

## 6. 评测计划

### 6.1 非联网测试

新增确定性测试：

1. `CaseIndex.option_evidence` 返回 A/B/C/D 四个 key。
2. evidence 数量遵守 `k_per_option`。
3. 不同选项关键词会改变排序。
4. domain match 会记录到 `match_reasons`。
5. 当存在替代来源时，source diversity 会防止一个案例填满所有选项。
6. holdout corpus 加载仍然被拒绝。
7. prompt builder 包含 `<选项证据>` 和逐选项行。
8. per-case detail 导出 `option_evidence` 与 `evidence_coverage`。
9. synthetic fixtures 下 strict answer-leak 仍为 0。

### 6.2 本地 smoke

先跑一个无网络 small fixture smoke：

```text
option_evidence coverage = 100% 的 case 都有 A/B/C/D key
parser contract remains valid
trace JSONL is complete
```

### 6.3 真实 API smoke

先只跑 10 cases：

| gate | target |
|---|---:|
| no crash | 100% |
| parser_valid | >= 90% |
| evidence coverage | 100% |
| accuracy | >= 40% |
| strict leak | 0% 或可解释 |

### 6.4 完整 holdout 评测

如果 10-case smoke 通过：

| stage | target |
|---|---:|
| flash 40-case × 3 | mean >= 30%，min >= 25% |
| pro Top-2 × 3 | mean >= 35%，min >= 30% |
| Stage gate | 至少 `GRAY_A`，理想为 `PASS` |

## 7. 回滚条件

如果出现以下任一情况，就回滚本次重设计：

1. option-grounded flash mean 比当前最佳 flash baseline 低超过 3pp。
2. parser validity 低于 90%。
3. strict retrieved-answer leak 因 prompt 构造变成非 0。
4. primary holdout 上 evidence coverage 低于 95%。
5. prompt 长度截断导致基础 BaziQA 答题契约被移除。
6. repeated pro runs 仍然 mean < 30% 且 leak < 5%。

## 8. 实施阶段

### Phase 1：数据结构与检索

- 新增 `option_evidence` retrieval 方法。
- 新增确定性评分组件。
- 新增 trace schema fixtures。

### Phase 2：Prompt builder 集成

- 新增 `retrieval_mode="option_grounded"`。
- 新增 option evidence block 格式化。
- 保留 legacy mode 的现有 `rag_k` 行为。

### Phase 3：Benchmark runner 集成

新增 CLI flag：

```text
--retrieval-mode option_grounded
--option-evidence-k 2
```

在 case details JSONL 中导出：

```text
option_evidence
evidence_coverage
```

### Phase 4：评测脚本与报告

- 新增 focused smoke command。
- 新增 option-grounded evidence ablation config。
- 对照 Stage 1 baseline 写报告。

## 9. 开放问题

1. v1 是否应该给 `annual_fortune` 加 domain-specific scorer，还是先保持 generic？
2. `contradict` stance 是否立即加入，还是等 support/related scoring 稳定后再加？
3. 模型是否能看到历史正确答案字母，还是只能看到历史选项文本？建议：只给历史选项文本。
4. option-grounded retrieval 是否替换 legacy RAG，还是先作为 parallel retrieval mode？建议：先作为 parallel mode。

## 10. 推荐决策

推进 Option-grounded Evidence Retrieval，但先作为 parallel retrieval mode。

在新模式通过以下三步前，不替换 legacy retrieval path：

1. deterministic non-network tests；
2. 10-case real API smoke；
3. 40-case flash repeated evaluation。

第一版实施计划应聚焦于最小、可追踪的 option evidence，而不是高级语义 embedding 或大规模 evidence-card 人工建设。
