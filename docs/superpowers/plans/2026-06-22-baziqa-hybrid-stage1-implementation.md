# BaziQA Hybrid Retrieval-Reasoning 阶段 1 实施计划

> 创建日期：2026-06-22
> 设计来源：[2026-06-22-baziqa-hybrid-retrieval-reasoning-design.md](file:///f:/project/agent/docs/superpowers/specs/2026-06-22-baziqa-hybrid-retrieval-reasoning-design.md)
> 范围：仅阶段 1（Retrieval-first 升级 + 报告质量门禁）。阶段 2/3 在阶段 1 通过严格门阈后单独写补丁计划。
> 模型分层：smoke / ablation / debug 默认 `deepseek-v4-flash`；主集 3 repeats / 晋升判定强制 `deepseek-v4-pro`。
> 货币与汇率：所有费用基于设计 §12.1.1 `1 USD = 7.20 CNY`。
> 执行原则：TDD、小步提交、DRY、YAGNI。每个 Task 步骤 2–5 分钟可单独验证。

## 0. 命名与目录约定

| 类别 | 路径模板 | 用途 |
|---|---|---|
| 数据 | `benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl` | 1.1 holdout chart_input 100% 覆盖产物 |
| 数据 | `benchmark/datasets/baziqa_domain_subsets/<domain>.jsonl` | 1.5 领域子集，每个 5–10 题 |
| 脚本 | `scripts/enrich_holdout_chart_input.py` | 已存在，复核 + 覆盖率校验 |
| 脚本 | `scripts/build_baziqa_domain_subsets.py` | 1.5 新增，从主集 + corpus 抽样并标注 `source: corpus_fill` |
| 脚本 | `scripts/compute_retrieved_answer_leak.py` | 1.3 新增，扫描 case_details_jsonl 写出 leak metric |
| 脚本 | `scripts/run_baziqa_retrieval_ablation.py` | 已存在，扩展支持 `--config-id`、`--rollback-jsonl`、`--model` |
| 脚本 | `scripts/verify_baziqa_stage1_gate.py` | 1.6 新增，按 §11 门阈 + §12.3 费用 / 调用上限一次性判定 |
| 脚本 | `scripts/verify_report_quality_gate.py` | 已存在，扩展校验项 |
| 报告 | `docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md` | 1.4 / 1.5 落地，包含 flash 大表 + pro Top-2 复核 |
| 回退数据 | `.tmp/rollback_stage1_{config_id}_{git_short_sha}_{utc_timestamp}.jsonl` | 设计 §12.4 |
| 配置 | `benchmark/configs/baziqa_retrieval_configs.yaml` | 1.2 / 1.4 新增，5 组配置统一声明 |

## 1. 总体里程碑

阶段 1 拆为 6 个 Milestone，逐一交付：

| ID | Milestone | 关键产物 | 模型 | 验收 |
|---|---|---|---|---|
| M1 | retrieved_answer_leak 指标可计算并出现在 trace / 报告 | `scripts/compute_retrieved_answer_leak.py` + benchmark trace 增强 + 单测 | 无（离线） | 单测通过；对历史 case_details 跑出 baseline = 0/40 |
| M2 | holdout chart_input 100% 覆盖 | `baziqa_contest8_2025_holdout_enriched.jsonl` + 覆盖率单测 | 无 | 覆盖率 = 100% |
| M3 | 5 组 retrieval 配置 + TF-IDF baseline + 可插拔 embedding | `baziqa_retrieval_configs.yaml` + `case_index.py` 配置加载 + 单测 | 无 | 5 组配置在小 corpus 单测中均能跑通且 trace 差异化 |
| M4 | retrieval ablation（flash 大表 + pro Top-2 复核） | `BAZIQA_RETRIEVAL_ABLATION_REPORT.md` + `.tmp/rollback_stage1_*.jsonl` | flash + pro | 报告含 5 组 × 3 repeats + Top-2 pro 复核 + `retrieved_answer_leak` 列 + baseline 对比 |
| M5 | 领域子集与 `corpus_fill` | `baziqa_domain_subsets/` + 单测 + 子集运行报告 | flash + pro Top-2 | 4 个 domain 各 5–10 题，`source: corpus_fill` 标注完整 |
| M6 | 报告质量门禁 + 晋升判定 | `verify_report_quality_gate.py` 扩展 + `verify_baziqa_stage1_gate.py` + 单测 | 无 | 门禁单测全部 PASS；晋升判定脚本对当前 ablation 报告输出明确 PASS / FAST_TRACK / GRAY / ROLLBACK / BLOCKED |

## 2. Task 列表（按执行顺序，每条 2–5 分钟）

### Task 1：M1 — retrieved_answer_leak metric

1.1 在 `tests/test_compute_retrieved_answer_leak.py` 新建（先写测试，预期失败）：
- 用 fixture 构造两条 case_details：1 条 retrieved facts 含 ground truth answer、1 条不含；
- 断言 `compute_leak_ratio(rows) == 0.5`；
- 提交：`test: add retrieved_answer_leak compute fixture (failing)`。

1.2 新建 `scripts/compute_retrieved_answer_leak.py`：
- 提供 `compute_leak_ratio(rows, answer_field='answer')`；
- CLI：`--case-details-jsonl <path>`、`--summary-json <path>`；
- 提交：`feat: add retrieved_answer_leak compute script`。

1.3 跑 1.1 测试 → PASS；提交。

1.4 在 `benchmark/runners/run_benchmark.py` 的 case_details trace 中新增 `retrieved_answer_leak: bool`（基于 retrieved facts 是否包含 ground truth answer）。先写测试再实现：
- 1.4.1 在 `tests/test_benchmark_runner.py` 加测试，断言 trace 中存在该字段；
- 1.4.2 实现；
- 1.4.3 跑测试 → PASS；提交：`feat(trace): record retrieved_answer_leak per case`。

1.5 对历史 P2 case_details 跑 baseline，确认结果为 `0/40 = 0%`，把数字写入 [BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md) 末尾的 “阶段 1 baseline” 一节。

历史 P2 case_details 路径模板（按修改时间倒序优先选择最新一份）：

- `.tmp/p2_refined_rag_k2_10_details.jsonl`（refined 10 题 smoke）
- `.tmp/p2_rag_k2_details.jsonl`（P2 初版 40 题）
- 通配：`.tmp/p2_*_details.jsonl` 或 `.tmp/baziqa_p2_*_case_details.jsonl`

若上述均不存在，回退用：`.tmp/ablation_*_pro.jsonl`（来自 Task 4.4 最近一次跑出的 pro 复核 case_details）。

执行命令示例：

```powershell
python scripts/compute_retrieved_answer_leak.py `
  --case-details-jsonl .tmp/p2_rag_k2_details.jsonl `
  --summary-json .tmp/p2_rag_k2_leak_baseline.json
```

把 `summary-json` 中的 leak 数值 1:1 抄进 baseline 报告章节；提交：`docs: record baseline retrieved_answer_leak=0/40`。

### Task 2：M2 — holdout chart_input 补齐

**Task 2 前置条件**：Task 1 已 PASS（包括 retrieved_answer_leak 单测 + benchmark trace 字段）。

2.1 检查现有 enrich 脚本：
- 先执行 `Get-ChildItem scripts/*enrich*chart* -Name` 确认 `enrich_holdout_chart_input.py` 是否存在；
- 若存在：复核实现，确认能从主集生日推 `chart_input`；
- 若不存在（该文件从未在版本控制中出现）：对比 [enrich_baziqa_chart_input.py](file:///f:/project/agent/scripts/enrich_baziqa_chart_input.py)，抽公共函数到 `bazi_features.py`（DRY），再基于公共函数新建 `enrich_holdout_chart_input.py`；
- 若 `enrich_baziqa_chart_input.py` 也不存在：直接基于 `bazi_features.py` 实现 holdout 版；
- 提交：`chore: check enrich script availability`。

2.2 在 `tests/test_enrich_holdout_chart_input.py` 新增（先写测试，预期失败）：
- 输入：3 条带生日 holdout；
- 输出 enriched 后 100% 含 `chart_input` 且字段非空；
- 提交：`test: holdout chart_input coverage must be 100% (failing)`。

2.3 实现 / 调整脚本 → 跑测试 → PASS；提交：`feat: holdout chart_input enrichment 100% coverage`。

2.4 用脚本生成正式产物：

```powershell
python scripts/enrich_holdout_chart_input.py `
  --input benchmark/datasets/baziqa_contest8_2025_holdout.jsonl `
  --output benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl
```

确认输出文件存在，覆盖率 = 100%。

2.5 把 enriched holdout 作为后续 ablation 默认数据集；在 [BAZIQA_PROJECT_ROADMAP.md](file:///f:/project/agent/docs/BAZIQA_PROJECT_ROADMAP.md) 标注；提交：`docs: switch ablation default to enriched holdout`。

### Task 3：M3 — 5 组 retrieval 配置与 embedding 可插拔

**Task 3 前置条件**：Task 1 已 PASS（trace 已能写入 `retrieved_answer_leak`）。Task 2 不阻塞 Task 3 的单测，但 Task 3 的 5 组 yaml 必须保证可在 Task 4 中接入 enriched holdout。

3.1 新增 `benchmark/configs/baziqa_retrieval_configs.yaml`：
- 5 组配置，每组通过布尔开关控制 `bm25`, `structured`, `semantic`, `tfidf_vector`, `embedding_vector` 以及 `embedding_model`；

```yaml
- id: bm25
  bm25: true
  structured: false
  semantic: false
  tfidf_vector: false
  embedding_vector: false
  embedding_model: ""

- id: structured
  bm25: true
  structured: true
  semantic: false
  tfidf_vector: false
  embedding_vector: false
  embedding_model: ""

- id: semantic
  bm25: true
  structured: true
  semantic: true
  tfidf_vector: false
  embedding_vector: false
  embedding_model: ""

- id: tfidf_vector
  bm25: true
  structured: true
  semantic: true
  tfidf_vector: true
  embedding_vector: false
  embedding_model: ""

- id: embedding_vector
  bm25: true
  structured: true
  semantic: true
  tfidf_vector: false
  embedding_vector: true
  embedding_model: "bge-zh-base"
```

- 提交：`feat: add baziqa retrieval ablation configs`。

3.2 在 [case_index.py](file:///f:/project/agent/case_index.py) 增加 `load_retrieval_config(config_id)`：
- 3.2.1 测试：用 fixture yaml 加载 5 个 `config_id` 都成功；
- 3.2.2 实现；
- 3.2.3 跑测试 → PASS；提交：`feat(case_index): load retrieval config by id`。

3.3 接入 `BAZI_RAG_VECTOR_MODEL` env：
- 3.3.1 测试：a) `BAZI_RAG_VECTOR=0` → 不走 ST/TF-IDF，scores 全为 0；b) `BAZI_RAG_VECTOR=1 BAZI_RAG_VECTOR_MODEL=all-MiniLM-L6-v2`（当前依赖中存在且可用）→ 走 ST 路径并返回非零 scores；c) `BAZI_RAG_VECTOR_MODEL=nonexistent-model-xyz` → 降级 TF-IDF fallback，且 `logger.info` 输出 INFO 级别提示（可用 `caplog` 断言）；
- 3.3.2 实现 + 失败时 `logger.info` 提示；
- 3.3.3 跑测试 → PASS；提交：`feat(case_index): pluggable embedding model via env`。

3.4 把 `config_id` 透传到 case_details trace：
- 3.4.1 测试：每个 case_details 写入 `config_id` 字段；
- 3.4.2 实现；
- 3.4.3 跑测试 → PASS；提交：`feat(trace): record retrieval config_id per case`。

### Task 4：M4 — retrieval ablation 矩阵执行

4.1 扩展 [scripts/run_baziqa_retrieval_ablation.py](file:///f:/project/agent/scripts/run_baziqa_retrieval_ablation.py)：
- 4.1.1 测试：CLI 接受 `--config-id`、`--configs`（**逗号分隔多 config，必须按顺序逐一执行并落盘**）、`--model`、`--rollback-jsonl`、`--append`；
- 4.1.2 实现：
  - 调用 `benchmark/runners/run_benchmark.py` 时透传 `--model {flash|pro}`；
  - 按设计 §12.4 命名落 `.tmp/rollback_stage1_{config_id}_{git_short_sha}_{utc_timestamp}.jsonl`；
  - 若 `--configs` 为空，默认走 `--config-id` 单 config；
  - 输出聚合 ablation 表，并在每行附 `model_name`、`config_id`、调用次数、实际费用（CNY）；
- 4.1.3 跑测试 → PASS；提交：`feat: extend retrieval ablation runner with config_id and rollback`。

**Task 4 前置条件**：Task 2（enriched holdout）与 Task 3（5 组 config yaml + `BAZI_RAG_VECTOR_MODEL` 接入）均已 PASS。

4.2 实测：flash 大表（不计入晋升判定）

```powershell
$env:PYTHONUNBUFFERED="1"
python scripts/run_baziqa_retrieval_ablation.py `
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl `
  --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl `
  --configs bm25,structured,semantic,tfidf_vector,embedding_vector `
  --repeats 3 `
  --model deepseek-v4-flash `
  --output docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md
```

4.3 评估 flash 大表 Top-2：
- 写入报告 `[model: flash]` 段；
- 若 Top-1 / Top-2 mean 差距 ≤ 1pp，按设计 §4 脚注扩展为 Top-3。

4.4 实测：pro 复核 Top-2

```powershell
python scripts/run_baziqa_retrieval_ablation.py `
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl `
  --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl `
  --configs <Top-2 from 4.3> `
  --repeats 3 `
  --model deepseek-v4-pro `
  --output docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md `
  --append
```

4.5 计算 retrieval leak：

```powershell
python scripts/compute_retrieved_answer_leak.py `
  --case-details-jsonl .tmp/ablation_*_pro.jsonl `
  --summary-json .tmp/ablation_pro_leak.json
```

把每个 config 的 `retrieved_answer_leak` 写进 ablation 报告对应行。

4.6 cost guard 校验（设计 §12.3，CNY 计价，单价见设计 §12.1.1：pro 0.033 / flash 0.0066 CNY/题）：
- `flash` 与 `pro` 同一配置 mean 差距 > 15pp → 触发命中处理，flash 大表标注 `INVALID:flash_pro_drift>15pp`；
- 单阶段调用 > 1.5 × 估算（设计 §12.2 阶段 1 估算 1200–1320 次 + 10% 余量 ≈ 1320–1452 次，1.5× ≈ **1980–2178 次**）；
- 单阶段费用 > 1.5 × 阶段 1 总预算上限（设计 §12.2 阶段 1 含余量上限 **~21.20 CNY**，1.5× ≈ **~31.80 CNY**）；
- 三阶段累计费用 > 1.5 × 三阶段保守上界（设计 §12.2 ≈ **~45.48 CNY**，1.5× ≈ **~68 CNY**）；
- 任一命中 → `BLOCKED:budget`，按设计 §12.4 落 `.tmp/rollback_stage1_*.jsonl`，停止后续 Task。

4.7 提交：`docs: BAZIQA_RETRIEVAL_ABLATION_REPORT stage1 flash+pro`。

### Task 5：M5 — 领域子集 + corpus_fill

**Task 5 前置条件**：Task 2（enriched holdout）、Task 3（5 组 config）、Task 4 的 Top-2 配置已确定（用于 5.4 pro 复核段）。

5.1 新建 `scripts/build_baziqa_domain_subsets.py`：
- 输入：主集 enriched holdout + corpus；
- 规则：每个 domain 优先从主集按 `domain` 字段抽题；不足 5 题从 corpus 抽样补齐至 5–10 题，并在 record 加 `source: corpus_fill`；
- 输出：`benchmark/datasets/baziqa_domain_subsets/<domain>.jsonl`，4 个 domain：`health / annual_fortune / relationship / unknown`。

5.2 在 `tests/test_build_baziqa_domain_subsets.py` 新增：
- 5.2.1 给定 fixture 主集 + corpus，4 个 domain 输出均 ≥ 5 且 ≤ 10；
- 5.2.2 主集对应 domain < 5 时必然出现 `source: corpus_fill` 标注；
- 5.2.3 主集足量时不出现 `source: corpus_fill`；
- 提交：`test: build_baziqa_domain_subsets coverage and corpus_fill`。

5.3 实现脚本 → 跑测试 → PASS；提交：`feat: build_baziqa_domain_subsets`。

5.4 实测 flash 子集（不计入晋升）+ pro Top-2 子集定稿（计入）。**每个 domain 必须单独跑一次**，共 4 个子集 × 2 轮 = 8 次运行；每次命令示例（以 `health` 为例，其余 domain 把 `--dataset` 替换为对应子集 jsonl 即可）：

flash（5 组配置 × 3 repeats）：

```powershell
$env:PYTHONUNBUFFERED="1"
python scripts/run_baziqa_retrieval_ablation.py `
  --dataset benchmark/datasets/baziqa_domain_subsets/health.jsonl `
  --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl `
  --configs bm25,structured,semantic,tfidf_vector,embedding_vector `
  --repeats 3 `
  --model deepseek-v4-flash `
  --output docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md `
  --append
```

pro 复核 Top-2：

```powershell
python scripts/run_baziqa_retrieval_ablation.py `
  --dataset benchmark/datasets/baziqa_domain_subsets/health.jsonl `
  --corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl `
  --configs <Top-2 from flash subset> `
  --repeats 3 `
  --model deepseek-v4-pro `
  --output docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md `
  --append
```

其余 3 个 domain 命令相同，仅替换 `--dataset` 为：

- `benchmark/datasets/baziqa_domain_subsets/annual_fortune.jsonl`
- `benchmark/datasets/baziqa_domain_subsets/relationship.jsonl`
- `benchmark/datasets/baziqa_domain_subsets/unknown.jsonl`

每次运行结束必须把调用次数 / 实际费用（CNY）填进 ablation 报告子集附录段。

5.5 把子集结果作为附录写入 ablation 报告；提交：`docs: BAZIQA_RETRIEVAL_ABLATION_REPORT add domain subsets`。

### Task 6：M6 — 报告质量门禁 + 晋升判定

**Task 6 前置条件**：Task 4（ablation 报告含 pro 复核段 + cost guard 字段）与 Task 5（子集附录）已生成；Task 1 的 `retrieved_answer_leak` metric 已落盘。Task 6.5 必须在 Task 6.1/6.2/6.4 全部 PASS 后才能写入 ACCEPTANCE 报告。

6.1 扩展 [scripts/verify_report_quality_gate.py](file:///f:/project/agent/scripts/verify_report_quality_gate.py)：
- 6.1.1 测试加入 4 个 sample 报告：
  - 缺 baseline 对比 → error；
  - 只跑 1 repeat 却宣布 “提升” → error；
  - 缺 answer distribution → warn；
  - 缺 `retrieved_answer_leak` → warn；
- 6.1.2 实现校验项；
- 6.1.3 跑测试 → PASS；提交：`feat(quality-gate): stricter baseline/repeat/leak checks`。

6.2 新建 `scripts/verify_baziqa_stage1_gate.py`：
- 输入：ablation 报告 summary json（pro 复核段）；
- 输出：晋升判定结果之一：`PASS / FAST_TRACK / GRAY_A / GRAY_B / BLOCKED:budget / ROLLBACK`；
- 退出码：0 = PASS / FAST_TRACK；1 = 脚本内部错误（参数错误、输入文件不存在、JSON 解析失败等）；2 = GRAY_A / GRAY_B；3 = BLOCKED / ROLLBACK。
- 判定规则严格对齐设计 §11 表格与 §12.3 费用 / 调用上限：

```text
PASS:        mean ≥ 35% AND mean ≥ 3 × stdev AND leak ≥ 15% AND budget OK
FAST_TRACK:  仅 1.3 + 1.1 完成、3 repeats pro 实测同时满足以上门阈
GRAY_A:      (5% ≤ leak < 15%) 或 (30% ≤ mean < 35%) 且未满足晋升且未触发回退
GRAY_B:      leak ≥ 15% 但 mean < 35% 或 mean < 3 × stdev
ROLLBACK:    leak < 5% 且 mean < 30%
BLOCKED:     调用次数 > 1.5× 估算 或 费用 > 1.5× 阶段预算 或 三阶段累计费用 > ≈ 68 CNY
```

6.3 在 `tests/test_verify_baziqa_stage1_gate.py` 加测试：
- 6.3.1 `mean=35, stdev=2, leak=20` → PASS；
- 6.3.2 `mean=33, leak=10` → GRAY_A；
- 6.3.3 `mean=32, stdev=2, leak=20` → GRAY_B（leak ≥ 15% 但 mean=32% < 35%）；
- 6.3.3b（备选边界用例）`mean=36, stdev=13, leak=20` → GRAY_B（leak ≥ 15% 但 mean=36% < 3×13=39%）；
- 6.3.3c（反例，必须 PASS）`mean=36, stdev=10, leak=20` → PASS（36 ≥ 35%，36 ≥ 3×10=30%，leak ≥ 15%）；
- 6.3.4 `mean=20, leak=3` → ROLLBACK；
- 6.3.5 单阶段费用 > 1.5× → BLOCKED:budget；
- 6.3.6 Fast-track 输入：mean=36, stdev=1.5, leak=18, executed_tasks={1.3, 1.1} → FAST_TRACK；
- 提交：`test: stage1 gate decision matrix`。

6.4 实现脚本 → 跑测试 → PASS；提交：`feat: verify_baziqa_stage1_gate`。

6.5 在 [BAZIQA_ACCEPTANCE_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCEPTANCE_REPORT.md) 追加 “Stage 1 Gate” 条目，模板：

> BaziQA Hybrid Stage 1 Gate: `<PASS|FAST_TRACK|GRAY_A|GRAY_B|ROLLBACK|BLOCKED:budget>` (real API, CNY budget), files=[BAZIQA_RETRIEVAL_ABLATION_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RETRIEVAL_ABLATION_REPORT.md)，调用次数=N，实际费用=Y CNY，mean=M%，stdev=Spp，leak=Lp%，date=YYYY-MM-DD。

提交：`docs: BAZIQA acceptance Stage 1 gate placeholder`。

## 3. 验收与门阈检查（与设计 §11 / §12.3 对齐）

执行 Task 4 与 Task 5 完成后必须依次满足：

- [scripts/verify_report_quality_gate.py](file:///f:/project/agent/scripts/verify_report_quality_gate.py) 对 `BAZIQA_RETRIEVAL_ABLATION_REPORT.md` 输出 PASS；
- `scripts/verify_baziqa_stage1_gate.py` 输出之一：
  - **PASS**：mean(pro 复核) ≥ 35%、mean ≥ 3 × stdev、`retrieved_answer_leak` ≥ 15% → 进入阶段 2 计划；
  - **FAST_TRACK**：1.3 + 1.1 完成已满足上述门阈（3 repeats pro 实测，禁用 flash 触发）→ 写 lessons-learned 并申请跳过 1.4 / 1.5；
  - **GRAY_A / GRAY_B**：按设计 §11 灰色带处理；阶段 1 内最多 2 轮子任务级 ablation；
  - **ROLLBACK**：关闭 vector 模式回到 P2 配置；
  - **BLOCKED:budget**：调用次数 / 费用 / 三阶段累计费用超 1.5× 阈值 → 落 `.tmp/rollback_stage1_*.jsonl`，写 lessons-learned。

费用回填（Task 4.6 / Task 5.5 / Task 6.5 各执行后）：
- 把实际 API 调用次数、实际费用（CNY，按当次汇率折算）、与设计 §12.2 估算的偏差比写入对应报告；
- 偏差 > 20% 或 USD→CNY 漂移 > 5% → 同步回填设计 §12.1.1。

## 4. 风险与回退动作（沿用设计 §8 / §11 / §12.3）

| 触发 | 命中后动作 |
|---|---|
| Embedding 噪声召回：`leak +≥ 5pp` 且 `mean +< 2pp` | 冻结当前 retrieval 权重，回到上一稳定配置；做单变量 ablation |
| `flash` 与 `pro` 在同一配置 mean 差距 > 15pp | 停止当前 ablation；后续 ablation 全部切 `pro`；flash 大表标注 `INVALID:flash_pro_drift>15pp` |
| holdout `chart_input` 引入 bug：enriched holdout mean 显著下降 | 立刻回退脚本，重生成 enriched holdout，并保留差异日志 |
| 单阶段 / 三阶段费用超 1.5× 阈值 | `BLOCKED:budget`，落 rollback 文件，停止后续 Task |
| `flash` 与 `pro` 在 ablation Top-1 切换 | 改为 `pro` 重跑 Top-3 才能选最终配置（设计 §12.4） |

## 5. 不在本计划范围内

为防止范围爆炸，本计划**不包含**（沿用设计 §7）：

- 训练 / 微调命理专用 embedding；
- 微调或蒸馏 base LLM；
- 引入向量数据库服务；
- 多模型集成（≥ 3 个）方案；
- 阶段 2（self-consistency / 命理对照表 prompt / confidence-gated re-ask）；
- 阶段 3（Verifier）。

## 6. 提交节奏与回归检查

- 每个 Task 子步骤一次 git commit，commit message 前缀使用 `test/feat/fix/docs/chore` Conventional Commits 风格。
- 每完成一个 Task 末尾必须运行：

```powershell
python -m pytest -q -m "not e2e"
```

并保证：

- 全量非 e2e 测试 PASS；
- 新增/修改文件没有引入 lint 警告（如已有 lint 脚本，跟随执行）。

## 7. 下一步

完成本阶段 1 实施计划后：

- 若 `verify_baziqa_stage1_gate.py` 输出 PASS / FAST_TRACK → 由 brainstorming 阶段确认进入阶段 2 设计补丁；
- 若输出 GRAY_A / GRAY_B → 在阶段 1 内最多 2 轮子任务级 ablation；
- 若输出 ROLLBACK / BLOCKED → 写 lessons-learned，并由用户决定下一步（是否换 embedding、是否调整门阈）。
