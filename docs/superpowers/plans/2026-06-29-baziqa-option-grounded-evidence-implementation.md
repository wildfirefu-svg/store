# BaziQA Option-grounded Evidence Retrieval 实施计划

> 创建日期：2026-06-29
> 设计来源：
> - [英文设计](file:///f:/project/agent/docs/superpowers/specs/2026-06-29-baziqa-option-grounded-evidence-redesign.md)
> - [中文设计](file:///f:/project/agent/docs/superpowers/specs/2026-06-29-baziqa-option-grounded-evidence-redesign-zh.md)
> 范围：作为 parallel retrieval mode 新增 `option_grounded`，不替换 legacy RAG。
> 执行原则：TDD、小步提交、DRY、YAGNI；先本地无网络验证，再做真实 API smoke。

## 0. 当前代码落点

| 类别 | 文件 | 当前职责 | 本计划变更 |
|---|---|---|---|
| 检索索引 | [case_index.py](file:///f:/project/agent/case_index.py) | `CaseIndex.top_k_cases(...)` 返回相似 case | 新增 `CaseIndex.option_evidence(...)` 与 option-level scorer |
| Prompt 注入 | [rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py) | `build_system_prompt(...)` 注入 `<类似命例>` | 支持 `retrieval_mode="option_grounded"`，注入 `<选项证据>` |
| Benchmark runner | [run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py) | 运行模型、写 `rag_trace`、写 `retrieved_answer_leak` | 加 CLI flag、写 `option_evidence` / `option_evidence_coverage` |
| Ablation runner | [run_baziqa_retrieval_ablation.py](file:///f:/project/agent/scripts/run_baziqa_retrieval_ablation.py) | 批量跑 retrieval configs | 透传 `--retrieval-mode` / `--option-evidence-k` |
| 配置 | [baziqa_retrieval_configs.yaml](file:///f:/project/agent/benchmark/configs/baziqa_retrieval_configs.yaml) | 5 组 legacy retrieval configs | 新增 option-grounded config |
| 测试 | [test_case_index.py](file:///f:/project/agent/tests/test_case_index.py) | case retrieval 单测 | 加 option evidence scorer 单测 |
| 测试 | [test_rag_prompt_builder.py](file:///f:/project/agent/tests/test_rag_prompt_builder.py) | RAG prompt 单测 | 加 `<选项证据>` prompt 单测 |
| 测试 | benchmark runner 相关测试 | trace / CLI 单测 | 加 retrieval mode flag 与 trace 字段单测 |

## 1. 总体验收门槛

### 1.1 本地无网络验收

必须满足：

```text
python -m pytest tests/test_case_index.py tests/test_rag_prompt_builder.py -q
python -m pytest -q -m "not e2e"
```

并且：

| 项 | 目标 |
|---|---:|
| `option_evidence` A/B/C/D key 覆盖 | 100% |
| evidence item 必需字段 | 100% |
| holdout isolation | 继续拒绝 holdout corpus |
| prompt 包含 `<选项证据>` | 100% |
| parser contract | 不回退 |

### 1.2 真实 API smoke 验收

先只跑 10 cases：

| 项 | 目标 |
|---|---:|
| no crash | 100% |
| parser_valid | >= 90% |
| option evidence coverage | 100% |
| accuracy | >= 40% |
| strict leak | 0% 或可解释 |

### 1.3 完整 holdout 验收

10-case smoke 通过后再跑：

| 阶段 | 目标 |
|---|---:|
| flash 40-case × 3 | mean >= 30%，min >= 25% |
| pro Top-2 × 3 | mean >= 35%，min >= 30% |
| Stage gate | 至少 `GRAY_A`，理想 `PASS` |

## 2. 任务列表

### Task 0：提交设计文档

0.1 检查两个设计文档仍是未提交状态：

```powershell
git status --short -- docs/superpowers/specs/2026-06-29-baziqa-option-grounded-evidence-redesign*.md
```

0.2 提交：

```powershell
git add -- docs/superpowers/specs/2026-06-29-baziqa-option-grounded-evidence-redesign.md docs/superpowers/specs/2026-06-29-baziqa-option-grounded-evidence-redesign-zh.md
git commit -m "docs: design option-grounded evidence retrieval"
```

验收：`git log -1 --oneline` 显示该提交。

---

### Task 1：TDD — `CaseIndex.option_evidence` 基础契约测试

1.1 在 [test_case_index.py](file:///f:/project/agent/tests/test_case_index.py) 追加 failing test：

- 构造 tiny corpus，包含 `career` / `relationship` 两类案例；
- 调用 `CaseIndex.option_evidence(features, question, options, domain="career", k_per_option=2)`；
- 断言返回 dict key 恰好包含 `A/B/C/D`；
- 每个 value 都是 list。

运行：

```powershell
python -m pytest tests/test_case_index.py -q -k option_evidence
```

预期：失败，提示 `CaseIndex` 缺少 `option_evidence`。

提交：

```text
test: option_evidence returns per-option buckets
```

1.2 在同一测试文件追加必需字段测试：

断言每条 evidence 至少包含：

```text
case_id
person_id
score
stance
match_reasons
fact_excerpt
source_domain
source_answer_option_text
```

运行同上，预期失败。

提交：

```text
test: option_evidence exposes traceable fields
```

---

### Task 2：实现 `CaseIndex.option_evidence` 最小版本

2.1 在 [case_index.py](file:///f:/project/agent/case_index.py) 新增 public method：

```python
option_evidence(features, question, options, domain=None, k_per_option=2)
```

初版逻辑：

- 对 A/B/C/D 每个选项构造 query：`question + option_text + features.text_blob`；
- 复用现有 `_bm25_scores`、`_score_structured_match`、`_score_chart_structure`、`_score_semantic_overlap`；
- 每个选项单独排序；
- 每个 evidence 生成必需字段；
- `stance` 初版固定为 `related` 或 `support`。

2.2 跑 Task 1 测试：

```powershell
python -m pytest tests/test_case_index.py -q -k option_evidence
```

验收：Task 1 两个测试通过。

提交：

```text
feat: add option_evidence retrieval buckets
```

---

### Task 3：TDD — option keyword / domain / diversity scoring

3.1 新增测试：option keyword 改变排序。

fixture：

- case A：题目/选项包含“升迁”；
- case B：题目/选项包含“婚姻”；
- 当前题 A 选项含“升迁”，B 选项含“婚姻”；
- 断言 A evidence 第一条偏向升迁 case，B evidence 第一条偏向婚姻 case。

预期：如当前实现不足则失败。

提交：

```text
test: option keywords drive evidence ranking
```

3.2 新增测试：domain match 记录到 `match_reasons`。

断言 evidence 中出现：

```text
same_domain:<domain>
```

提交：

```text
test: option evidence records domain match reason
```

3.3 新增测试：source diversity。

fixture：一个高分 case 与一个次高分 case；当 `k_per_option=2` 时，尽量不要同一 `person_id` 重复填满同一选项。

提交：

```text
test: option evidence avoids duplicate source per option
```

---

### Task 4：实现 scoring 增强

4.1 在 [case_index.py](file:///f:/project/agent/case_index.py) 内部拆出 helper：

```python
_score_option_evidence(case, structured, question_text, option_text, domain)
```

4.2 评分项最小实现：

| 分数项 | match_reason |
|---|---|
| domain match | `same_domain:<domain>` |
| option token overlap | `option_overlap:<tokens>` |
| question token overlap | `question_overlap:<tokens>` |
| chart score | 复用现有 chart reasons |
| semantic overlap | `semantic_overlap:<phrases>` |
| source diversity | 去重同一 person_id |

4.3 跑测试：

```powershell
python -m pytest tests/test_case_index.py -q -k "option_evidence or domain_match or intent_overlap or semantic"
```

4.4 若老测试受影响，保持 `top_k_cases` 行为不变。

提交：

```text
feat: score option evidence with option and domain signals
```

---

### Task 5：TDD — Prompt builder 支持 `<选项证据>`

5.1 在 [test_rag_prompt_builder.py](file:///f:/project/agent/tests/test_rag_prompt_builder.py) 新增 failing test：

- 构造 fake `CaseIndex`，实现 `option_evidence`；
- 调用 `build_system_prompt(..., retrieval_mode="option_grounded", question="...", options=[...])`；
- 断言 prompt 包含：

```text
<选项证据>
A.
B.
C.
D.
最终答案：X
```

预期：失败，因为当前 `build_system_prompt` 不支持参数。

提交：

```text
test: prompt builder renders option evidence block
```

5.2 新增测试：legacy RAG 不变。

- 不传 `retrieval_mode` 时仍包含 `<类似命例>`；
- 不应包含 `<选项证据>`。

提交：

```text
test: legacy rag prompt remains default
```

---

### Task 6：实现 prompt builder option-grounded mode

6.1 修改 [rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py)：

- `build_system_prompt` 新增参数：

```python
retrieval_mode: str = "legacy"
question: str | None = None
options: list[str] | None = None
option_evidence_k: int = 2
```

6.2 新增 formatter：

```python
_format_option_evidence_block(option_evidence, options)
```

6.3 option-grounded 模式：

- 调用 `case_index.option_evidence(...)`；
- 注入 `<选项证据>`；
- 附加模型输出契约：逐选项证据表 + `最终答案：X`。

6.4 跑测试：

```powershell
python -m pytest tests/test_rag_prompt_builder.py -q
```

提交：

```text
feat(prompt): render option-grounded evidence block
```

---

### Task 7：TDD — Benchmark runner CLI 与 trace 字段

7.1 在 benchmark runner 相关测试中新增 failing test：

- CLI parser 接受：

```text
--retrieval-mode option_grounded
--option-evidence-k 2
```

如果现有测试文件没有 parser 级单测，则新增最小测试文件：

```text
tests/test_benchmark_runner_option_grounded.py
```

提交：

```text
test: benchmark runner accepts option-grounded flags
```

7.2 新增 trace 测试：

- monkeypatch fake model 返回 `最终答案：A`；
- monkeypatch fake case index 返回 option evidence；
- 跑 1 case；
- 断言 case_details JSONL 包含：

```text
retrieval_mode: option_grounded
option_evidence
evidence_coverage
retrieved_answer_leak
```

提交：

```text
test: benchmark trace includes option evidence
```

---

### Task 8：实现 benchmark runner 集成

8.1 修改 [run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py)：

- `_resolve_system_prompt` 接收并透传 `retrieval_mode` / `option_evidence_k`；
- `call_model_sync` / `call_model_messages_with_history` 增加参数；
- `run_model_benchmark` 和 `run_multi_turn_benchmark` 增加参数；
- CLI 增加：

```text
--retrieval-mode legacy|option_grounded
--option-evidence-k 2
```

8.2 新增 helper：

```python
_resolve_option_evidence_trace(case, k)
```

8.3 trace 写入：

```text
retrieval_mode
option_evidence
option_evidence_coverage
```

legacy 模式下：

```text
retrieval_mode: legacy
option_evidence: {}
option_evidence_coverage: {}
```

8.4 跑测试：

```powershell
python -m pytest tests/test_benchmark_runner_option_grounded.py -q
python -m pytest tests/test_benchmark_runner.py -q
```

提交：

```text
feat(benchmark): trace option-grounded evidence
```

---

### Task 9：TDD — Ablation runner 透传 retrieval mode

9.1 在 [run_baziqa_retrieval_ablation.py](file:///f:/project/agent/scripts/run_baziqa_retrieval_ablation.py) 相关测试中新增 failing test：

断言构造的 subprocess command 包含：

```text
--retrieval-mode option_grounded
--option-evidence-k 2
```

若无合适测试文件，则新增：

```text
tests/test_run_baziqa_retrieval_ablation_option_grounded.py
```

提交：

```text
test: ablation runner forwards option-grounded flags
```

9.2 实现 CLI 参数：

```text
--retrieval-mode legacy
--option-evidence-k 2
```

9.3 `_run_one` 中透传给 `run_benchmark.py`。

9.4 跑测试。

提交：

```text
feat(ablation): forward option-grounded retrieval mode
```

---

### Task 10：新增 retrieval config

10.1 在 [baziqa_retrieval_configs.yaml](file:///f:/project/agent/benchmark/configs/baziqa_retrieval_configs.yaml) 增加配置：

```yaml
- id: option_grounded_tfidf
  bm25: true
  structured: true
  semantic: true
  tfidf_vector: true
  embedding_vector: false
  retrieval_mode: option_grounded
  option_evidence_k: 2
```

10.2 更新 `_config_envs` 或 config resolver：

- env 仍控制 scorer；
- `retrieval_mode` / `option_evidence_k` 通过 CLI 参数透传。

10.3 跑 config 解析测试。

提交：

```text
feat(config): add option_grounded_tfidf retrieval config
```

---

### Task 11：本地无网络 smoke

11.1 新增脚本或测试命令，使用 tiny fixture 生成 option evidence trace。

优先使用 pytest，不新增脚本：

```powershell
python -m pytest tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_benchmark_runner_option_grounded.py -q
```

11.2 跑完整非 e2e 回归：

```powershell
python -m pytest -q -m "not e2e"
```

11.3 记录结果到临时文件：

```text
.tmp/option_grounded_local_smoke.log
```

不提交 `.tmp`。

提交：若仅测试通过无代码变更，不提交。

---

### Task 12：10-case 真实 API smoke

前置：Task 11 通过。

12.1 生成 10-case smoke dataset：优先从 enriched holdout 前 10 条复制到 `.tmp/option_grounded_smoke10.jsonl`。

12.2 运行 flash smoke：

```powershell
$env:DEEPSEEK_API_KEY = (Get-Content .deepseek_key -Raw).Trim()
python scripts/run_baziqa_retrieval_ablation.py `
  --run `
  --dataset .tmp/option_grounded_smoke10.jsonl `
  --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl `
  --configs option_grounded_tfidf `
  --model deepseek-v4-flash `
  --repeats 1 `
  --retrieval-mode option_grounded `
  --option-evidence-k 2 `
  --output-dir .tmp/option_grounded_smoke10 `
  --rollback-jsonl .tmp/option_grounded_smoke10/rollback.jsonl `
  --report .tmp/option_grounded_smoke10/report.md
```

12.3 验收：

- 10 rows；
- `parser_valid >= 90%`；
- 每行有 A/B/C/D 的 `option_evidence` key；
- strict leak 0% 或写明原因；
- accuracy >= 40%。

12.4 如果失败：不要进入 40-case；回到 Task 4/6 调整 scorer 或 prompt。

12.5 如果通过：提交 smoke 结果摘要到报告：

```text
docs: record option-grounded smoke10 result
```

---

### Task 13：40-case flash repeated evaluation

前置：Task 12 通过。

13.1 运行 flash × 3：

```powershell
python scripts/run_baziqa_retrieval_ablation.py `
  --run `
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl `
  --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl `
  --configs option_grounded_tfidf `
  --model deepseek-v4-flash `
  --repeats 3 `
  --retrieval-mode option_grounded `
  --option-evidence-k 2 `
  --output-dir .tmp/option_grounded_flash `
  --rollback-jsonl .tmp/option_grounded_flash/rollback.jsonl `
  --report .tmp/option_grounded_flash/report.md
```

13.2 验收：

| 项 | 目标 |
|---|---:|
| rows | 120 |
| mean | >= 30% |
| min | >= 25% |
| strict leak | 0% 或可解释 |

13.3 不达标：停止，不跑 pro；写失败分析。

13.4 达标：进入 Task 14。

---

### Task 14：pro 复核

前置：Task 13 达标。

14.1 运行 pro × 3：

```powershell
python scripts/run_baziqa_retrieval_ablation.py `
  --run `
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl `
  --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl `
  --configs option_grounded_tfidf `
  --model deepseek-v4-pro `
  --repeats 3 `
  --retrieval-mode option_grounded `
  --option-evidence-k 2 `
  --output-dir .tmp/option_grounded_pro `
  --rollback-jsonl .tmp/option_grounded_pro/rollback.jsonl `
  --report .tmp/option_grounded_pro/report.md
```

14.2 验收：

| 项 | 目标 |
|---|---:|
| rows | 120 |
| mean | >= 35% |
| min | >= 30% |
| Stage gate | 至少 `GRAY_A` |

14.3 生成 gate summary：

```text
.tmp/option_grounded_stage_gate_summary.json
```

14.4 运行：

```powershell
python scripts/verify_baziqa_stage1_gate.py `
  --summary-json .tmp/option_grounded_stage_gate_summary.json `
  --json `
  --output-json .tmp/option_grounded_stage_gate_result.json
```

---

### Task 15：报告与最终提交

15.1 更新 [BAZIQA_RETRIEVAL_ABLATION_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md)：

新增章节：

```text
Option-grounded Evidence Retrieval Follow-up
```

包含：

- smoke10 结果；
- flash × 3 结果；
- pro × 3 结果；
- leak；
- parser_valid；
- evidence coverage；
- 与 Stage 1 baseline 比较。

15.2 更新 [BAZIQA_ACCEPTANCE_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCEPTANCE_REPORT.md)：

- 如果 gate 仍 `ROLLBACK`：记录失败原因；
- 如果达到 `GRAY_A` / `PASS`：记录晋升路径；
- 明确 budget 是否触发。

15.3 验证：

```powershell
python -m pytest -q -m "not e2e"
```

15.4 提交：

```text
docs: report option-grounded evidence retrieval results
```

## 3. 失败处理

如果任一真实 API 阶段失败，不继续扩大调用量。

| 失败点 | 处理 |
|---|---|
| smoke10 accuracy < 40% | 回到 scorer/prompt，小步调整后重跑 smoke10 |
| parser_valid < 90% | 修 prompt 输出契约或 parser，不跑 40-case |
| strict leak > 0 | 修 prompt/context，必须解释或清零 |
| flash mean < 30% | 不跑 pro，写失败报告 |
| pro mean < 30% 且 leak < 5% | 维持 rollback，停止该方案 |
| budget guard 接近 1.5× | 停止真实 API，先离线诊断 |

## 4. 推荐执行顺序

优先执行到 Task 11，本地无网络全部通过后再决定是否花 API 预算：

```text
Task 0 -> Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7 -> Task 8 -> Task 9 -> Task 10 -> Task 11
```

真实 API 阶段必须按 gate 顺序：

```text
Task 12 smoke10 -> Task 13 flash40x3 -> Task 14 pro40x3 -> Task 15 report
```

## 5. 当前不做的事情

1. 不替换 legacy RAG 默认路径。
2. 不新增外部向量数据库。
3. 不做大规模手工 evidence-card 标注。
4. 不在 smoke10 未通过时跑 40-case。
5. 不把 domain subset 的 `annual_fortune` 成功直接等价为主集成功。
