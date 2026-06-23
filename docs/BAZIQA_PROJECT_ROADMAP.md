# BaziQA 项目状态与路线图

> 最后更新：2026-06-19
> 目标：把 BaziQA（八字命理问答）在 40 题 holdout 上的稳定准确率从当前约 30% 提升到 40% 以上，并建立可复现的评测体系。

---

## 一、项目状态概览

| 维度 | 状态 |
|------|------|
| 基准评测 | 可用，`run_benchmark.py` 支持 `direct_choice / structured_reasoning / multi_turn` |
| RAG 检索 | 已实现基于规则的结构化匹配 + domain/地支加权，tie-break 已固定 |
| 可重复性 | `temperature=0` 已透传，重复运行脚本、LOVO 脚本已落地 |
| 当前瓶颈 | `rag-structured` 单跑 42.5% 不可复现，3 次重复均值 30.0%（27.5%–35.0%） |
| 关键发现 | 波动主要来自模型/API 输出不稳定，而非 RAG 检索排序 |
| 下一步 | 降低模型自由度 + k-ablation + 检索质量升级 |

---

## 二、已完成工作

### 2.1 评测体系硬底

| 工作 | 文件/脚本 | 说明 |
|------|-----------|------|
| 透传 temperature | `claude_api.py`、`run_benchmark.py` | 从 CLI 一路传到真实 API 请求 |
| 精确 accuracy | `run_benchmark.py` 输出 `AccuracyExact: correct/total=accuracy` | 避免百分比四舍五入失真 |
| 重复运行统计 | `scripts/run_baziqa_repeated_eval.py`、`benchmark/reports/accuracy_stats.py` | 输出 mean/min/max/stdev |
| LOVO 评估 | `scripts/verify_baziqa_lovo.ps1` | 按年份留一验证泛化性 |
| 年份分割 | `benchmark/runners/split_baziqa_by_year.py` | 生成 corpus/holdout |

### 2.2 RAG 检索

| 工作 | 文件 | 说明 |
|------|------|------|
| 结构化特征提取 | `bazi_features.py` | 日主、月令、性别、年代、地支、问题领域 |
| domain-aware 打分 | `case_index.py` | 同领域命例加权 + 地支重叠加权 |
| 命例格式化 | `rag_prompt_builder.py` | 把命例按统一模板注入 prompt |
| 确定性 tie-break | `case_index.py` | `(-score, person_id, birth_year, name)` 稳定排序 |

### 2.3 诊断能力

| 工作 | 文件 | 说明 |
|------|------|------|
| 每题 trace 导出 | `run_benchmark.py` `--case-details-jsonl` | 每题输出 predicted/raw/correct/rag_trace，且增量落盘 |
| trace 对比分析 | `scripts/analyze_baziqa_trace_runs.py` | 比较多轮运行，定位波动来源 |
| 稳定性报告 | `docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md` | 记录 repeats=3 稳定性实验 |
| trace 诊断报告 | `docs/BAZIQA_TRACE_DIAGNOSIS_REPORT.md` | 10 题 × 3 轮定位实验 |

### 2.4 测试覆盖

- `tests/test_claude_api.py`：temperature 透传
- `tests/test_benchmark_runner.py`：精确 accuracy、trace 导出、增量落盘
- `tests/test_case_index.py`：tie-break 稳定性、domain-aware 检索
- `tests/test_bazi_features.py`：结构化特征
- `tests/test_rag_prompt_builder.py`：RAG prompt 构建
- `tests/test_accuracy_stats.py`：重复统计
- `tests/test_baziqa_split_by_year.py`：年份分割

当前非网络测试：`28 passed`（case index 相关）/ `30 passed`（benchmark runner 相关）。

---

## 三、当前关键结论

### 3.1 原始 few-shot ablation 结果不可复现

- `rag-structured` 单跑 42.5% 是**乐观单跑结果**。
- 重复 3 次后：均值 **30.0%**，最低 **27.5%**，最高 35.0%，标准差 4.3 pp。
- 因此 **尚未达到 40% 验收线**。

### 3.2 RAG 检索排序已稳定

- 10 题 × 3 轮 trace 诊断中，**RAG top-k 100% 稳定**（10/10）。
- `CaseIndex.top_k_cases` 的 tie-break 修复有效，同分命例按 `person_id/birth_year/name` 稳定排序。
- 继续优化排序确定性的收益已经很小。

### 3.3 主要波动源是模型/API 输出不稳定

- 相同题目、相同 RAG 命例、`temperature=0.0` 条件下：
  - **7/10** 道题预测答案在三runs中发生变化；
  - **4/10** 道题正误发生翻转。
- 模型 raw answer 的完整推理路径和最终答案都在变化，不只是解析器问题。

### 3.4 RAG 命例存在“稳定但可能不够相关”的问题

- 多道题反复召回相同命例（如 `male_19831101_P022`、`male_19740428_P017` 等）。
- 检索稳定不代表检索质量高，需要验证 top-k 数量和增强结构化匹配。

---

## 四、待解决问题清单

| 编号 | 问题 | 影响 | 优先级 |
|------|------|------|--------|
| 1 | 模型/API 输出不稳定 | 即使 context 相同，答案仍波动 | 高 |
| 2 | top-k 数量可能引入噪声 | k=3 是否必要/有害未知 | 高 |
| 3 | 检索命例与问题匹配度不足 | 高频命例重复出现，domain 匹配仍偏粗 | 中 |
| 4 | 缺少对错误 case 的领域/类型归因 | 不知道哪些题型/领域是短板 | 中 |
| 5 | 当前 40 题 holdout 样本量偏小 | 单题差异会放大为 2.5 pp | 低 |

---

## 五、下一阶段路线图

### Milestone A：降低模型输出自由度（已完成）

1. **强制置信度输出协议** ✅
   - 修改 prompt，要求模型先给出 A/B/C/D 每个选项的置信度分数；
   - 最终答案必须是置信度最高的选项；
   - 输出最后一行固定为 `最终答案：X`；
   - benchmark 只抽取最后一行，减少中间推理文本干扰。

2. **实现置信度解析器与 fallback** ✅
   - `extract_choice_with_meta` 优先解析 `最终答案：X`，其次置信度表，最后 fallback 旧模式；
   - 新增测试覆盖 final_answer / confidence / legacy / invalid 四种模式。

3. **解析器元数据与 RAG k 配置** ✅
   - `run_benchmark.py` 支持 `--rag-k`，并在 case details 中记录 `parser_source`、`parser_valid`、`rag_k`；
   - `rag_prompt_builder.py` 接受 `top_k`。

### 待执行验证

- **重复验证**：对 `rag-structured` 跑 repeats=3，比较波动是否下降；
  - 目标：min/max 差距从 7.5 pp 降到 5 pp 以内。

### Milestone B：k-ablation（验证命例噪声）

1. **跑 k=1/k=2/k=3 ablation** ✅
   - 固定 method=`structured_reasoning`、temperature=0、dataset=2025 holdout；
   - 每个 k 跑 repeats=3，输出 per-case trace；
   - 脚本：`scripts/run_baziqa_k_ablation.py`。

2. **分析维度**
   - 准确率随 k 的变化；
   - 错误题在不同 k 下的 RAG signature；
   - 是否存在“多了一个噪声命例导致错误”的 case。

3. **决策**
   - 如果 k=1 或 k=2 显著优于 k=3，则调整默认 k；
   - 如果 k 变化不明显，则问题在检索质量而非数量。

### Milestone C：检索质量升级（进行中）

1. **结构化检索加权升级** ✅
   - 默认 `rag_k` 已从 3 调整为 2；
   - query 的问题与选项文本已进入检索特征 `query_text`；
   - `case_index.py` 增强了性别、年代、领域、选项意图关键词、地支文本重叠等加权；
   - RAG prompt 与 trace 已输出 `匹配原因` / `match_reasons` 和检索分。

2. **问题领域与选项意图匹配** ✅
   - 不仅匹配 `query_domain`，还从问题/选项文本中提取意图关键词；
   - 检索时优先召回同领域且事实摘要中出现相同意图关键词的命例。

3. **本地语义短语混合排序** ✅
   - 已实现问题/选项/答案事实中的语义短语抽取；
   - 已过滤 `出生/如何/此命`、纯数字年份片段、`的xx` 等泛词噪声；
   - 排序分数融合 BM25、结构化分、`semantic_overlap`；
   - trace/prompt 输出 `semantic_overlap` 匹配原因。

4. **向量检索 + 混合排序**
   - 后续可用 embedding 模型对命例和 query 向量化；
   - 保留现有结构化分数，与向量相似度加权融合。

5. **日主/月令/五行结构化加权**
   - 当前 corpus 缺少完整四柱 chart，暂不能可靠计算日主/月令；
   - 后续若 corpus 补齐 chart_input，可继续增强日主相同、月令相同/相生、用神/忌神重叠加分。

### Milestone D：错误归因与领域攻坚

1. **按领域/年份/题型 breakdown** ✅
   - case details 已含 `domain`；
   - 生成按领域的正确率报告，识别短板领域；
   - 脚本：`scripts/analyze_baziqa_error_attribution.py`。

2. **真实报告质量门** ✅
   - 使用 `bazi_report_validator.py` 检查生成报告是否存在 hard error；
   - 脚本：`scripts/verify_report_quality_gate.py`。

3. **针对低分领域扩容 corpus 或 few-shot**
   - 若某领域准确率 < 25% 且样本 ≥ 5，则：
     - 补充该领域的高质量命例到 corpus；
     - 或在该领域启用针对性的 few-shot 示例（局部 few-shot，避免 context dilution）。

4. **长期目标：稳定 mean ≥ 40%、min ≥ 35%、LOVO mean ≥ 40%**

---

## 六、优先级与验收标准

| 阶段 | 优先级 | 验收标准 |
|------|--------|----------|
| Milestone A | P0 | `rag-structured` repeats=3 的 min/max 差 ≤ 5 pp；解析器测试通过 |
| Milestone B | P0 | 完成 k=1/2/3 ablation 报告，确定最优 k |
| Milestone C | P1 | 实现向量检索或结构化加权升级，准确率在 holdout 上提升 ≥ 5 pp |
| Milestone D | P1 | 生成领域 breakdown 报告，识别并修复两个以上低分领域 |

---

## 七、近期可执行命令

### 7.1 k-ablation（推荐最先执行）

```powershell
# k=1
python benchmark/runners/run_benchmark.py `
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl `
  --model-runner --provider deepseek --model deepseek-v4-pro `
  --max-cases 40 --method structured_reasoning --temperature 0 --rag `
  --rag-corpus benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl `
  --case-details-jsonl .tmp/trace/k1_run1.jsonl
```

将 `k` 在 `run_benchmark.py` 的 RAG 参数中设为 1/2/3 后分别跑 3 次，用 `analyze_baziqa_trace_runs.py` 对比。

### 7.2 重复稳定性验证

```powershell
python scripts/run_baziqa_repeated_eval.py `
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl `
  --provider deepseek --model deepseek-v4-pro `
  --max-cases 40 --repeats 3 --temperature 0 `
  --configs rag-structured `
  --output docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md
```

### 7.3 LOVO 泛化验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_lovo.ps1 -MaxCases 40
```

---

## 八、相关文档链接

- [验收报告](file:///f:/project/agent/docs/BAZIQA_ACCEPTANCE_REPORT.md)
- [RAG 稳定性报告](file:///f:/project/agent/docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md)
- [Trace 诊断报告](file:///f:/project/agent/docs/BAZIQA_TRACE_DIAGNOSIS_REPORT.md)
- [RAG 提升报告](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md)
- [Few-shot Ablation 报告](file:///f:/project/agent/docs/BAZIQA_FEWSHOT_ABLATION_REPORT.md)
- [实现计划](file:///f:/project/agent/docs/superpowers/plans/2026-06-18-baziqa-accuracy-evaluation-hardening-implementation.md)

---

## 九、结论

当前项目已经从“跑通单次评测”推进到“定位波动来源”阶段。核心结论是：**检索排序已稳定，模型输出不稳定是主要矛盾**。因此下一步不应继续在 tie-break 上消耗精力，而应优先：

1. 通过强制置信度/固定最终答案格式降低模型自由度；
2. 通过 k-ablation 验证命例噪声；
3. 再进入向量检索 + 结构化加权的检索质量升级。

只有在评测波动被控制、且能稳定复现之后，再谈准确率提升才有意义。

---

## 十、当前专项计划：Bazi 准确率与命理判断水平提升

> 实施计划：[2026-06-20-bazi-accuracy-and-judgment-improvement-implementation.md](file:///f:/project/agent/docs/superpowers/plans/2026-06-20-bazi-accuracy-and-judgment-improvement-implementation.md)
> 状态报告：[BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md)

- 先跑 refined P2 完整 40 题，确认 10 题 smoke 是否可复现。
- 用 retrieval ablation 决定 semantic overlap 是否默认启用。
- 补齐 corpus chart_input 后，新增命盘结构相似度检索。
- 用 domain action plan 做 health / annual_fortune / study / unknown 等领域攻坚。
- 用 report quality gate 验证真实命主报告没有确定性命理硬错。

### 已实现脚本

| 脚本 | 功能 |
|------|------|
| `scripts/run_baziqa_refined_p2_validation.py` | Refined P2 全量 40 题验证 |
| `scripts/run_baziqa_retrieval_ablation.py` | 检索消融实验（bm25/structured/structured_semantic/semantic_low） |
| `scripts/enrich_baziqa_chart_input.py` | 为 corpus 生成 chart_input |
| `scripts/build_domain_action_plan.py` | 从 trace JSONL 生成领域行动计划 |
| `scripts/export_report_quality_samples.py` | 导出报告质量门禁样本 |

---

## 十一、Hybrid 阶段 1：默认数据集 = enriched holdout

> 设计：[2026-06-22-baziqa-hybrid-retrieval-reasoning-design.md](file:///f:/project/agent/docs/superpowers/specs/2026-06-22-baziqa-hybrid-retrieval-reasoning-design.md)
> 实施计划：[2026-06-22-baziqa-hybrid-stage1-implementation.md](file:///f:/project/agent/docs/superpowers/plans/2026-06-22-baziqa-hybrid-stage1-implementation.md)
> 状态：阶段 1 进行中（已完成 Task 1.1–1.5 / 2.1–2.4）

从 Hybrid 阶段 1 起，所有 ablation / smoke / baseline 评测默认使用 enriched holdout 主集：

| 项 | 值 |
|---|---|
| 主集（默认 `--dataset`） | `benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl` |
| 生成命令 | `python scripts/enrich_holdout_chart_input.py --input benchmark/datasets/baziqa_contest8_2025_holdout.jsonl --output benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl` |
| 覆盖率验收 | `coverage = 100.0%`（40/40 行均含非空 `chart_input.four_pillars` 与 `chart_input.day_master`） |
| 默认 corpus | `benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl` |
| 主集规模 | 40 题 |
| 模型分层 | smoke / ablation / debug 默认 `deepseek-v4-flash`；3 repeats / 晋升判定强制 `deepseek-v4-pro` |

约束：

1. **任何 ablation / 晋升判定脚本** 默认必须读取 enriched 版本；如果显式指定旧 `baziqa_contest8_2025_holdout.jsonl`，必须在报告中以 `[dataset: pre-enriched]` 标注，且**不允许进入晋升判定**；
2. enriched 文件因 `chart_input` 携带派生字段，跨 chart 算法版本会产生 “40 insertions / 40 deletions” 级别的 diff——这是正常现象，每次升级 chart 算法必须按 [Task 2.4](file:///f:/project/agent/docs/superpowers/plans/2026-06-22-baziqa-hybrid-stage1-implementation.md) 重新生成并提交；
3. 与 ablation 相关的 case_details JSONL 必须同时记录 `dataset` 路径，便于后期回溯。
