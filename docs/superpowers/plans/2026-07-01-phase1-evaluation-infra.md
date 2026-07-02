# Phase 1 · 实施计划：评测基础（shuffle-options + Self-Consistency + MingLi-Bench 适配器）

- **日期**：2026-07-01
- **对应设计**：[2026-07-01-accuracy-improvement-design.md](file:///f:/project/agent/docs/superpowers/specs/2026-07-01-accuracy-improvement-design.md)
- **状态**：已完成；baseline 已归档到 [PHASE1_BASELINE_SUMMARY.md](file:///f:/project/agent/docs/PHASE1_BASELINE_SUMMARY.md)
- **执行者假设**：对代码库不熟悉，需按顺序执行
- **原则**：TDD（先写失败测试，再实现）、小步提交、DRY、YAGNI

---

## 0. 准备工作

### 0.1 前置阅读

- `benchmark/runners/run_benchmark.py`：模型调用入口
- `scripts/run_baziqa_retrieval_ablation.py`：评估驱动脚本
- `case_index.py`：evidence 检索
- `rag_prompt_builder.py`：prompt 构造
- `data/celebrity_cases.json`：不使用（events schema 不兼容）

### 0.2 环境检查

- Python 3.10+
- 现有依赖已装：`pytest`、`sentence-transformers` 无需（Phase 2 才要）
- `DEEPSEEK_API_KEY` 已在 `.deepseek_key`

### 0.3 分支约定

在 `main` 上工作；每完成一个小任务立即 `git add -A && git commit -m "<message>"`。

---

## 1. Shuffle-Options 支持

### 1.1 [写测试] 添加 `tests/test_benchmark_shuffle_options.py`

**目标**：验证 shuffle 后：
- 原始 `options` 按 seed 打乱
- `expected_answer` 被映射到 shuffle 后的对应 label
- Runner 输出的 `predicted_answer` 反向映射回原始 label
- 相同 seed 下 shuffle 顺序稳定

```python
# tests/test_benchmark_shuffle_options.py 骨架
def test_shuffle_options_deterministic_seed():
    row = {"case_id": "x", "options": ["A a", "B b", "C c", "D d"], "answer": "A"}
    shuffled = shuffle_options(row, seed=42)
    assert shuffled["options"] != row["options"] or ...
    assert shuffled["answer_label_map"]["A"] in {"A","B","C","D"}


def test_shuffled_answer_matches_original_option_text():
    ...


def test_unshuffle_predicted_answer():
    ...
```

**验收**：`pytest tests/test_benchmark_shuffle_options.py -q` 全部 FAIL（因为函数还没写）

### 1.2 [实现] 新增 `benchmark/runners/shuffle_options.py`

- 函数 `shuffle_options(row, seed) -> Dict`：返回 shuffled row + `answer_label_map`（原 label → 新 label）
- 函数 `unshuffle_predicted_answer(predicted, answer_label_map) -> str`

**验收**：Task 1.1 测试全部 PASS

### 1.3 [集成] 在 `benchmark_runner.py` 主循环里增加 `--shuffle-options / --shuffle-seed` 参数

- 默认 `shuffle_options=False`（保持向后兼容）
- 开启时对每个 case 应用 shuffle；写入 case details 里保留 `answer_label_map`
- 计算 `correct` 时用 unshuffle 后的 predicted 与原始 answer 比较

**验收**：`pytest tests/test_benchmark_shuffle_options.py -q` PASS；`pytest tests/test_benchmark_runner_option_grounded.py -q` 也 PASS（回归）

### 1.4 [提交]

```
git commit -m "feat(benchmark): add shuffle-options with seed and unshuffle mapping"
```

---

## 2. Self-Consistency 多次采样与众数聚合

### 2.1 [写测试] `tests/test_benchmark_self_consistency.py`

```python
def test_majority_vote_returns_mode():
    votes = ["A", "B", "A", "A", "C"]
    assert majority_vote(votes) == "A"


def test_majority_vote_tie_returns_first_seen():
    votes = ["A", "B", "A", "B"]
    assert majority_vote(votes) == "A"


def test_majority_vote_ignores_none():
    votes = ["A", None, "A", None]
    assert majority_vote(votes) == "A"
```

**验收**：FAIL

### 2.2 [实现] `benchmark/runners/self_consistency.py`

- `majority_vote(votes: List[Optional[str]]) -> Optional[str]`
- `sample_answers(runner_call_fn, case, n, temperature) -> List[Optional[str]]`（透明包装，逐次调用现有 single-call 路径）

**验收**：Task 2.1 PASS

### 2.3 [集成] `benchmark_runner.py` 增加 `--n-samples N --aggregate majority --sample-temperature 0.4`

- 默认 `n_samples=1`（保持向后兼容）
- `n_samples > 1` 时按 SC 流程；record 里保存 `samples: [{predicted, raw}...]` 便于诊断
- final `predicted_answer` 与 `correct` 计算基于 aggregate 结果

**验收**：`pytest -q tests/test_benchmark_self_consistency.py tests/test_benchmark_runner_option_grounded.py`

### 2.4 [提交]

```
git commit -m "feat(benchmark): add self-consistency (n-samples + majority vote)"
```

---

## 3. MingLi-Bench 适配器

### 3.1 [写测试] `tests/test_mingli_bench_adapter.py`

- Fixture：极简版 `data_sample.json`（2 题）+ `fortune_api_results_sample.json`
- 断言：适配器输出的每行含 `case_id / question / options / answer / chart_input / domain`
- 特殊字段：`--astro` 注入 `chart_input`，否则字段可为空

**验收**：FAIL

### 3.2 [实现] `scripts/mingli_bench_adapter.py`

- 函数 `load_and_normalize(data_json, fortune_api_json, include_astro) -> List[Dict]`
- `case_id = f"mingli_{q['case_id']}"`
- `domain` 由 `question['category']` 映射（事业→career、健康→health、婚姻→relationship、子女→family、财运→wealth、其余→unknown）

**验收**：Task 3.1 PASS

### 3.3 [CLI] `scripts/run_mingli_bench.py`

- 参数：`--data`, `--fortune`, `--year`, `--categories`, `--output-dir`, `--astro/--no-astro`, 复用 benchmark_runner 参数
- 内部：调用适配器 → 写入临时 JSONL → 调用 benchmark_runner

**验收**：`python scripts/run_mingli_bench.py --help` 正常显示

### 3.4 [示例 fixtures] `tests/fixtures/mingli/data_sample.json` + `fortune_api_results_sample.json`

- 2-4 条真实脱敏数据（可从 MingLi-Bench 官方拷贝极少量）

**验收**：`pytest tests/test_mingli_bench_adapter.py -q` PASS

### 3.5 [提交]

```
git commit -m "feat(bench): add MingLi-Bench adapter and CLI"
```

---

## 4. Baseline 重跑

### 4.1 40×3 shuffle-off baseline

- 命令：现有 `run_baziqa_retrieval_ablation.py --config-id option_grounded_tfidf --repeats 3 --max-cases 40`
- 输出：`.tmp/phase1_baseline_shuffle_off/`

**验收**：mean 与前值 28.3% 在 ±1pt 内（说明代码改动没引入回归）

### 4.2 40×3 shuffle-on baseline

- 命令：追加 `--shuffle-options --shuffle-seed 42`
- 输出：`.tmp/phase1_baseline_shuffle_on/`

**验收**：strict leak = 0；记录 shuffle 前后 mean 差异（用于后续 phase 参考）

### 4.3 MingLi-Bench flash × 1（20 题 smoke）

- 命令：`python scripts/run_mingli_bench.py --data data/data.json --fortune data/fortune_api_results.json --year 2025 --sample 20 --astro --model deepseek-v4-flash`
- 输出：`.tmp/phase1_mingli_smoke/`

**验收**：无 crash，写出 `<model>_results.json`；记录 accuracy 作为 MingLi baseline

### 4.4 [提交报告]

- 写 `.tmp/phase1_baseline_report.md`（含 3 表：shuffle-off / shuffle-on / mingli-smoke）
- 归档提交

```
git commit -m "chore(bench): phase1 baseline results (shuffle + MingLi smoke)"
```

---

## 5. 收尾

### 5.1 回归全测试

```
python -m pytest tests -q -k "benchmark or mingli or shuffle or self_consistency or bazi_calculator or rag_prompt or case_index or reclassify or chart_domain"
```

**验收**：全部 PASS

### 5.2 更新设计文档状态

在 `docs/superpowers/specs/2026-07-01-accuracy-improvement-design.md` 顶部把 Phase 1 状态标记为 `Done`

### 5.3 决定是否进入 Phase 2

- 若 shuffle-on / off 差异 > 3pt，先分析位置偏差再进；
- 若 MingLi smoke accuracy < 30%，先确认适配器归一化正确，再进 Phase 2；
- 否则直接开始 Phase 2 计划（另写实施计划文档）。

---

## 6. 里程碑与提交节奏

| 里程碑 | 提交数 | 关键产物 |
|---|---:|---|
| M1: shuffle-options 就绪 | 1 | `shuffle_options.py` + tests |
| M2: SC 就绪 | 1 | `self_consistency.py` + tests |
| M3: MingLi 适配器就绪 | 1 | `mingli_bench_adapter.py` + CLI + fixtures |
| M4: baseline 报告 | 1 | `.tmp/phase1_baseline_report.md` |
| **合计** | **4** | Phase 1 完成 |

---

## 7. 风险与后备

| 风险 | 后备 |
|---|---|
| shuffle 后 case_index / rag_prompt 有隐含依赖原顺序 | 单元测试 + 40×3 shuffle-off vs shuffle-on 差异检查 |
| SC × 3 API 成本超预算 | 只对 stratified8 做完整 SC，40×3 保持 n=1 直到 Phase 3 |
| MingLi-Bench 数据下载受限 | 用官方 repo raw url 手工下载或先用 fixture 20 题跑通链路 |
| benchmark_runner 内部状态污染（前后行相互影响） | 每 case 之前 clear cache / logger flush |

---

## 8. 完成后转入

- Phase 1 完成 → 写 `docs/superpowers/plans/2026-07-XX-phase2-hybrid-retrieval.md`
- Phase 2 依赖 Phase 1 的 `--shuffle-options` 与 baseline 数据
