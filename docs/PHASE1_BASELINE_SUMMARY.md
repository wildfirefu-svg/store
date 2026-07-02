# Phase 1 Baseline 总结

- 日期：2026-07-02
- 范围：Phase 1 评测基础设施（shuffle-options、Self-Consistency、MingLi-Bench 适配器）与进入 Phase 2 前的 baseline 记录
- 结论：Phase 1 的代码、测试与 baseline 补跑已完成。`option_grounded_tfidf` shuffle-off 40×3 mean 为 28.3%；shuffle-on(seed=42) 40×3 mean 降至 18.3%，暴露明显选项顺序敏感性；MingLi-Bench 官方 2025 前 20 题 smoke 为 60.0%。

## 1. Phase 1 交付状态

| 项目 | 状态 | 说明 |
|---|---|---|
| `--shuffle-options / --shuffle-seed` | 已完成 | 支持按 seed 打乱选项，并将预测答案反向映射回原始 label 后评分。 |
| Self-Consistency | 已完成 | 支持 `--n-samples`、`--aggregate majority`、`--sample-temperature`，默认 `n_samples=1` 保持兼容。 |
| MingLi-Bench 适配器 | 已完成 | 支持项目旧 fixture 格式，也兼容官方 MingLi-Bench `data.json` 的 `questions` 包装、options 对象格式、fortune list 索引和官方 chart 字段。 |
| 测试覆盖 | 已完成 | Phase 1 相关测试子集通过。 |
| baseline 结果归档 | 已完成 | 已归档 shuffle-off、shuffle-on(seed=42) 与 MingLi 官方 2025 20 题 smoke。 |

## 2. 已验证测试

补跑前后重新验证了 Phase 1 相关测试：

```powershell
python -m pytest tests/test_benchmark_shuffle_options.py tests/test_benchmark_runner_shuffle_options.py tests/test_benchmark_self_consistency.py tests/test_benchmark_runner_self_consistency.py tests/test_mingli_bench_adapter.py tests/test_run_mingli_bench_cli.py -q
```

最近一次适配器修复后验证：

```text
15 passed in 0.23s
```

完整 Phase 1 子集此前验证：

```text
44 passed in 0.39s
```

## 3. Baseline 结果

### 3.1 BaziQA 40-case × 3：shuffle-off baseline

可复用产物：`.tmp/option_grounded_flash/`。

| 配置 | 模型 | rows | run1 | run2 | run3 | mean | min | max | gate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `option_grounded_tfidf` | `deepseek-v4-flash` | 120 | 30.0% | 27.5% | 27.5% | 28.3% | 27.5% | 30.0% | BLOCKED |

辅助指标：

| 指标 | 结果 | 说明 |
|---|---:|---|
| strict leak | 0% (0/120) | 未发现严格答案泄漏。 |
| parser_valid | 100% | 解析链路稳定。 |
| evidence coverage | 100% | 每条样本均有 evidence。 |

与 legacy baseline 对比：

| 配置 | 模型 | mean | 说明 |
|---|---|---:|---|
| `legacy tfidf_vector` | `deepseek-v4-flash` | 27.5% | 旧检索 baseline。 |
| `option_grounded_tfidf` | `deepseek-v4-flash` | 28.3% | 提升 0.8pp，但仍未达 30%。 |

结论：`option_grounded_tfidf` 没有引入 parser 或 strict leak 回归，但准确率仍低于进入更高成本 pro 复核的门槛。

### 3.2 BaziQA 40-case × 3：shuffle-on baseline

补跑命令：

```powershell
python scripts\run_baziqa_retrieval_ablation.py --run --config-id option_grounded_tfidf --retrieval-mode option_grounded --model deepseek-v4-flash --repeats 3 --max-cases 40 --shuffle-options --shuffle-seed 42 --output-dir .tmp\phase1_shuffle_on_seed42 --report .tmp\phase1_shuffle_on_seed42\report.md --rollback-jsonl .tmp\phase1_shuffle_on_seed42\rollback.jsonl
```

归档产物：`.tmp/phase1_shuffle_on_seed42/`。

| 配置 | 模型 | seed | rows | run1 | run2 | run3 | mean | min | max | gate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `option_grounded_tfidf` | `deepseek-v4-flash` | 42 | 120 | 12.5% | 22.5% | 20.0% | 18.3% | 12.5% | 22.5% | BLOCKED |

辅助指标：

| 指标 | 结果 | 说明 |
|---|---:|---|
| parser_valid | 109/120 (90.8%) | 第 3 轮有 11 条 raw answer 为空、predicted=None，属于 API/调用无响应型失败。 |
| shuffle-off → shuffle-on mean 差异 | -10.0pp | 28.3% → 18.3%，差异远超 3pp 阈值。 |

按 domain 粗分：

| domain | rows | correct | accuracy |
|---|---:|---:|---:|
| career | 27 | 9 | 33.3% |
| unknown | 42 | 7 | 16.7% |
| family | 12 | 2 | 16.7% |
| relationship | 21 | 2 | 9.5% |
| study | 3 | 1 | 33.3% |
| health | 9 | 1 | 11.1% |
| annual_fortune | 6 | 0 | 0.0% |

决策：shuffle-on/off 差异为 -10.0pp，说明当前 prompt/runner 组合存在强选项顺序敏感性。后续 Phase 不应只看 shuffle-off；至少应把 shuffle-on 作为回归门禁或风险指标。

### 3.3 MingLi-Bench 官方 2025 20 题 smoke

数据来源：官方仓库 `DestinyLinker/MingLi-Bench`，本地克隆到 `.tmp/mingli_bench_source/`。

- `data/data.json`: 160 道官方归一化选择题
- `data/fortune_api_results.json`: 官方预计算 Bazi/Ziwei chart 数据

补跑命令：

```powershell
python scripts\run_mingli_bench.py --data .tmp\mingli_bench_source\data\data.json --fortune .tmp\mingli_bench_source\data\fortune_api_results.json --astro --year 2025 --max-cases 20 --model deepseek-v4-flash --provider deepseek --method direct_choice --temperature 0 --output-dir .tmp\phase1_mingli_smoke_2025_20 --case-details-jsonl .tmp\phase1_mingli_smoke_2025_20\case_details.jsonl --shuffle-options --shuffle-seed 42
```

归档产物：`.tmp/phase1_mingli_smoke_2025_20/`。

| 数据集 | 年份 | 模型 | sample | astro | shuffle | correct | accuracy | parser_valid |
|---|---:|---|---:|:---:|:---:|---:|---:|---:|
| MingLi-Bench official | 2025 | `deepseek-v4-flash` | 20 | 是 | seed=42 | 12/20 | 60.0% | 20/20 |

按 domain 粗分：

| domain | rows | correct | accuracy |
|---|---:|---:|---:|
| family | 5 | 3 | 60.0% |
| relationship | 6 | 3 | 50.0% |
| career | 2 | 1 | 50.0% |
| health | 2 | 2 | 100.0% |
| unknown | 3 | 2 | 66.7% |
| wealth | 1 | 1 | 100.0% |
| study | 1 | 0 | 0.0% |

说明：这是 2025 前 20 题 smoke，不等同于完整 MingLi-Bench 160 题或官方 trimmed mean。结果可作为链路验证与小样本信号，不应直接外推为长期 T3 指标。

## 4. 错误模式与后续价值

从 `option_grounded_tfidf` 的 40-case × 3 结果看，主要问题不是 Phase 1 runner 能力，而是 evidence 与推理质量：

| 维度 | 发现 |
|---|---|
| smoke10 偏差 | shuffle-off 前 10 case 准确率 46.7%，后 30 case 只有 22.2%，说明小样本 smoke 明显高估整体。 |
| 低分 domain | shuffle-off 中 family、health、relationship 是主要拖累域；shuffle-on 后 relationship/health 仍低。 |
| 选项顺序敏感 | shuffle-on mean 18.3%，比 shuffle-off 28.3% 低 10.0pp，说明位置偏差或选项标号依赖明显。 |
| MingLi smoke | 官方 2025 前 20 题 smoke 达 60.0%，说明 MingLi 适配链路可用，但仍需全量 160 题验证。 |

Phase 1 的实际价值是：

1. 让后续实验可以检测选项位置偏差；
2. 让后续 SC / majority vote 可以复用统一 runner；
3. 让 MingLi-Bench 能纳入同一评测管线；
4. 明确 smoke10 不足以代表整体，后续 smoke 应覆盖全部 8 个命主或按 domain/person 分层抽样；
5. 明确后续 Phase 的报告不能只报 shuffle-off，需要同时报告 shuffle-on 或解释为什么关闭。

## 5. Phase 1 决策

| 决策项 | 结论 |
|---|---|
| Phase 1 是否完成 | 是，代码、测试与 baseline 补跑已完成。 |
| 是否可进入 Phase 2 | 可以，但 Phase 2/3 的 A/B 必须考虑 shuffle-on 风险。 |
| 是否默认启用新 runner 能力 | shuffle/SC 均保持 opt-in，不影响旧流程。 |
| 是否需要补实验 | 建议后续补完整 MingLi-Bench 160 题；BaziQA shuffle-on 已完成。 |

最终结论：Phase 1 可以标记为 **Done / Baseline Archived / Shuffle Sensitivity Found**。工程目标和 baseline 审计闭环已完成；关键发现是 `option_grounded_tfidf` 在 shuffle-on 后 mean 从 28.3% 降到 18.3%，而 MingLi 官方 2025 20 题 smoke 为 60.0%。
