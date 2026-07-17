# C2 Scorer 评测指标与时间事件路由设计

**日期**：2026-07-17

**状态**：待实现

**范围**：BaziQA C2 scorer 离线评测、direct+C2 题型路由

## 1. 背景

Phase 5 在 2021/2022 独立年度的 scorer-only gate 阶段判定 `ROLLBACK`。两年均只有 `top_score_hit_rate` 通过，`score_answer_correlation`、`neutral_option_rate` 和 `strong_signal_option_rate` 失败。

进一步回放发现：

- 58 个 C2 生效题中只有 6 题的正确选项是唯一最高分。
- 约三分之二选项没有规则覆盖，四项同为 50 分时，现有 `top_score_hit_rate` 仍记为命中。
- 部分指定年份事件题只使用静态原局信号评分，未使用大运/流年信息。
- `score_options()` 返回空列表时，direct+C2 runner 仍构造空的 C2 prompt，不是真正 no-op。

因此下一步先修复评测可解释性和题型路由，不扩展规则数量、不调权重、不发起模型 API 实验。

## 2. 目标与非目标

### 2.1 目标

1. 为 scorer 增加并列校正、唯一最高、分差和规则覆盖指标。
2. 将需要时间维度、但答案是事件或状态的题路由为 C2 no-op。
3. direct+C2 遇到 no-op 时使用与 direct 完全相同的 prompt。
4. 保持现有 scorer 字段和 Phase 5 gate 兼容。
5. 用无网络测试验证指标、路由和 runner 回退。

### 2.2 非目标

- 不修改 C2 规则、关键词、权重或 verdict 阈值。
- 不修改共享的 `is_time_location_question()`。
- 不修改 two-stage 时间推理流程。
- 不修改已完成 Phase 5 的四项 gate 或历史报告。
- 不运行 2023，不读取其题目、答案或 scorer 指标。
- 不调用真实模型 API。

## 3. 组件与职责

| 文件 | 职责 |
|---|---|
| `benchmark/runners/per_option_scorer.py` | 新增 scorer 专用时间事件识别；输出新指标 |
| `benchmark/runners/run_benchmark.py` | scores 为空时回退标准 direct prompt |
| `tests/test_per_option_scorer.py` | 路由与指标单元测试 |
| `tests/test_benchmark_runner.py` | direct+C2 no-op prompt 回退测试 |

不新增生产模块，避免为一次局部改动引入额外抽象层。

## 4. Scorer 专用时间事件路由

### 4.1 接口

在 `per_option_scorer.py` 新增：

```python
def is_temporal_event_question(question: str, options: list[str]) -> bool:
    ...
```

`score_options()` 的入口顺序调整为：

```python
if is_time_location_question(question, options):
    return []
if is_temporal_event_question(question, options):
    return []
```

两个函数含义不同：

- `is_time_location_question()`：答案本身是年份、时间或地点。
- `is_temporal_event_question()`：题目给定时间锚点，答案是该时点的事件、结果或状态。

### 4.2 识别规则

先对问题文本做轻量规范化，不分析答案、不读取 `chart_input`。

以下任一非出生时间锚点命中即返回 `True`：

- 明确公历年份：`2011年`、`2020/2021年`、`截至2017年9月`。
- 年龄或年龄区间：`35岁`、`虚龄35至44`。
- 运程区间：`甲戌大运期间`、`流年`、`岁运`、`年运`。
- 相对时间段与明确年份组合：`前半年的2022`、`2022年下半年`。

在检测年份前，移除仅描述身份的出生年份片段：

- `1970年出生`
- `1970年生`
- `出生于1980年`
- `生于1980年`

该移除只作用于时间锚点检测使用的文本副本，不修改原问题或最终 prompt。实现采用窄匹配：只识别 `18xx`、`19xx`、`20xx` 四位公历年份；后置形式仅匹配 `<四位年份>年生` 和 `<四位年份>年出生`，前置形式仅匹配 `出生于<四位年份>` 和 `生于<四位年份>`；所有形式的片段后都必须紧接 `的`、标点、空白或文本结尾。不得把 `2011年生意失败`、`2020年生活困难` 中的 `年生` 误判为出生年份。`民国70年生` 不属于四位年份锚点，本次不做历法换算。

移除后没有其他时间锚点时不得判为 temporal event。例如：

```text
1970年出生的游先生，他的婚姻状况与学历如何？
```

仍进入静态 scorer。多领域问题识别不在本次范围。

### 4.3 正反例

应返回 `True`：

- `命主在2011年发生了一件什么事情？`
- `命主2020/2021年的经济状况是？`
- `虚龄35至44甲戌大运期间，其子女运如何？`
- `截至2017年9月，哪项符合命主感情状况？`

应返回 `False`：

- `1970年出生的游先生，他的婚姻状况如何？`
- `1970年生，命主的职业状况如何？`
- `命主的健康状况怎样？`
- `命主目前的职业是什么？`

边界反例：`2011年生意失败，原因是什么？` 和 `2020年生活困难，哪项描述正确？` 仍应返回 `True`。

## 5. 新增 scorer 指标

所有新指标只对 `score_options()` 返回非空列表且进入现有 `n_cases` 的题计算。现有字段保持原义。

### 5.1 并列校正与唯一最高

#### `tie_adjusted_top_credit`

逐题记分后取平均：

- 正确答案不在最高分集合：`0`
- 正确答案与 `k` 个选项并列最高：`1 / k`

因此四项全为 50 分时只得 `0.25`，不再等价于唯一正确最高。
当 `n_cases=0` 时，`tie_adjusted_top_credit` 返回 `0.0`。

#### `unique_top_case_rate`

```text
唯一最高分题数 / n_cases
```

#### `unique_top_accuracy`

```text
唯一最高且正确题数 / 唯一最高分题数
```

没有唯一最高分题时返回 `0.0`，不返回 `null`。

同时输出审计计数：

- `unique_top_cases`
- `unique_top_correct`

### 5.2 正确项与错误项分差

每题定义：

```text
margin = correct_option_score - max(wrong_option_scores)
```

输出：

- `correct_vs_max_wrong_margin_mean`
- `positive_margin_case_rate`
- `zero_margin_case_rate`
- `negative_margin_case_rate`
- `valid_margin_cases`
- `invalid_correct_label_cases`

margin 只对正确答案 label 存在于该题 scores 中，且至少存在一个错误选项的题计算。正确 label 缺失的题仍计入现有 `n_cases` 及其它适用指标，但不计入 margin；同时计入 `invalid_correct_label_cases`。三种 rate 和 margin mean 的分母均为 `valid_margin_cases`；当该值大于 0 时三种 rate 之和必须为 `1.0`（浮点误差除外），为 0 时三种 rate 和 mean 均返回 `0.0`。

### 5.3 规则覆盖

“有规则覆盖”定义为选项的 `matched_rules` 非空。

输出：

- `correct_option_rule_coverage_rate`：正确选项有覆盖的题数 / `n_cases`。
- `wrong_option_rule_coverage_rate`：有覆盖的错误选项数 / 全部错误选项数。
- `all_options_no_rule_case_rate`：四个选项均无覆盖的题数 / `n_cases`。

同时输出审计计数：

- `correct_option_rule_covered_cases`
- `wrong_option_rule_covered_options`
- `wrong_option_total_options`
- `all_options_no_rule_cases`

## 6. 兼容性

以下现有字段不得删除、改名或改变算法：

- `top_score_hit_rate`
- `correct_option_mean_score`
- `wrong_option_mean_score`
- `score_answer_correlation`
- `neutral_option_rate`
- `strong_signal_option_rate`
- `domain_distribution`
- `cases`

`top_score_hit_rate` 继续表示“正确答案是否包含在最高分集合”，用于历史结果兼容；新代码和后续报告不得把它解释为唯一判别准确率。

Phase 5 的 `OFFLINE_THRESHOLDS` 暂不新增或替换字段。新指标先作为 C3 设计与年度留一验证的诊断依据，避免追溯改写已完成实验。

## 7. direct+C2 真正 no-op

当前 runner 在 `phase4_direct_c2=True` 时无条件调用 `format_direct_c2_prompt()`。即使 scores 为空，仍会产生空的 C2 证据区块。

改为：

```python
option_scores = score_options(case)
if option_scores:
    prompt = format_direct_c2_prompt(case, option_scores)
else:
    prompt = format_direct_choice_prompt(case)
```

记录行为保持可审计：

- `phase4_direct_c2=True`
- `phase4_option_scores=[]`
- `phase4_option_score_domain=None`

这样 scorer no-op 只关闭 C2 增量，不关闭模型本身；该题仍按 direct 基线调用模型。

## 8. 测试策略

全部测试使用构造数据和 fake model call，不访问网络。

### 8.1 路由测试

1. 明确年份事件题返回 `True`，`score_options()` 返回 `[]`。
2. 年份区间、年龄区间和大运期间题返回 `True`。
3. `1970年出生`、`1970年生`、`出生于1980年`、`生于1980年` 从时间锚点中排除；`2011年生意失败`、`2020年生活困难` 不得被误删。
4. 无时间锚点的健康、职业题仍正常评分。
5. 现有 time/location 用例保持通过。

### 8.2 指标测试

使用 monkeypatch 的固定 scores 分离测试汇总算法：

1. 四项并列且正确答案在其中：旧 top hit 为 `1.0`，tie-adjusted credit 为 `0.25`。
2. 唯一正确最高、唯一错误最高、并列最高混合样本验证 unique 指标。
3. 正、零、负 margin 各一题，验证平均值、三种 rate 和 `valid_margin_cases`。
4. 正确项、错误项和整题无规则覆盖的组合验证覆盖指标与计数。
5. 正确答案 label 缺失时，该题不进入 margin 分母并计入 `invalid_correct_label_cases`；其余现有指标仍按原逻辑汇总。
6. 空输入的所有新增 rate、mean 和 `tie_adjusted_top_credit` 返回 `0.0`，计数返回 `0`。

### 8.3 Runner 测试

1. scores 非空时仍使用 C2 prompt。
2. temporal event/no-op 的 scores 为空时，捕获到的 prompt 与 `format_direct_choice_prompt(case)` 完全相同。
3. no-op detail 保留 `phase4_direct_c2=True` 和空 scores。

### 8.4 回归测试

至少运行：

```powershell
python -m pytest tests/test_per_option_scorer.py -q
python -m pytest tests/test_benchmark_runner.py tests/test_phase5_c2_generalization.py tests/test_two_stage_reasoning.py -q
python -m pytest -m "not e2e" -q
```

若系统临时目录不可写，使用仓库内 `--basetemp .tmp/pytest-c2-routing` 并禁用 pytest cache；该环境调整不得被误报为代码修复。

## 9. 验收标准

- 新增路由只存在于 C2 scorer，不改变共享 time/location 判断。
- 指定年份事件题和大运期间事件题不再生成 C2 scores。
- 出生年份不会单独触发 no-op。
- direct+C2 在 scores 为空时使用与 direct 完全相同的 prompt。
- 所有新增指标数值和分母有单元测试证明。
- 现有 scorer 字段与 Phase 5 gate 保持兼容。
- 关联测试与非 E2E 测试通过。
- 未读取或运行 2023，未发起真实 API 调用。

## 10. 后续

本设计实现并验证后，重新只读计算 2021/2022 新指标，用于 C3 scorer 设计。由于 2021/2022 已经被分析，后续只能作为开发年度；最终候选冻结前采用 2021/2022/2024/2025 年度留一验证，2023 继续保留为唯一最终集。
