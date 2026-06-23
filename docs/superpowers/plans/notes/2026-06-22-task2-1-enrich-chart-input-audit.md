# Task 2.1 判定记录：enrich-chart-input 脚本现状

> 关联：[阶段 1 实施计划 Task 2.1](file:///f:/project/agent/docs/superpowers/plans/2026-06-22-baziqa-hybrid-stage1-implementation.md)
> 创建日期：2026-06-22

## 1. 脚本存在性

执行 `Get-ChildItem scripts/*enrich*chart* -Name` 输出：

```
enrich_baziqa_chart_input.py
enrich_holdout_chart_input.py
```

两个脚本均已存在于版本控制中。

## 2. 能力对比

| 维度 | `scripts/enrich_baziqa_chart_input.py`（corpus 版） | `scripts/enrich_holdout_chart_input.py`（holdout 版） |
|---|---|---|
| `enrich_row` 幂等 | ✅ 已存在 `chart_input` 直接返回 | ❌ 永远覆盖 |
| place 字段处理 | ✅ 默认 `"Beijing"` | ❌ 不传 `place` |
| 计算入口 DI | ✅ `compute_chart_fn=compute_chart` 便于单测 | ❌ 直接 `compute_chart(...)` |
| 异常路径 | 静默跳过失败 case | 落盘 `chart_input_error` 但不计入成功 |
| `load_jsonl` / `write_jsonl` | ✅ 已抽出 | ❌ 内联 IO |
| `summarize_rows` | ✅ 返回 `total / with_chart_input / coverage` | ❌ 仅 `print` 字符串 |
| CLI summary 报告 | ✅ 写 markdown | ❌ 不写 |

## 3. DRY 抽取去向选择

候选方案：

- A：把 corpus 版工具函数提升到 `bazi_features.py`；
- B：让 holdout 版直接 import 复用 corpus 版工具函数（`from scripts.enrich_baziqa_chart_input import enrich_row, load_jsonl, write_jsonl, summarize_rows`）；
- C：把工具函数提升到 `scripts/_enrich_chart_common.py` 这个新模块。

**采用 B**。理由：

1. `bazi_features.py` 的职责是“特征抽取”，IO 与 CLI 工具不应越界；
2. corpus 版已经是事实上的公共实现，单测覆盖更稳；
3. 方案 B 改动最小，零新增文件，符合 YAGNI；
4. 方案 C 引入新模块但只有 2 个调用者，过度设计。

## 4. Task 2.2 / 2.3 实际工作量预估

- Task 2.2：写 `tests/test_enrich_holdout_chart_input.py`，要求 enriched 输出在 fixture 上覆盖率 100%、产物字段非空、保持幂等。
- Task 2.3：把 `enrich_holdout_chart_input.py` 重写为复用 corpus 版工具函数（DRY），并满足覆盖率合同；保留 holdout 版的 CLI 入口与默认输出路径。

本判定记录不修改任何业务代码，只为 Task 2.2 / 2.3 提供执行依据。
