# Phase 6 6D v1 Bazi Time Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 6D v1 的"八字命局 × 大运 × 目标流年"确定性注入实现为独立可复用模块 + 独立 6D 实验链，通过零 API 离线门验证工程契约，为真实 paired dev 准备完备基础设施。

**Architecture:** 新建 `benchmark/formatters/bazi_time_context.py` 持有关系计算/流年计算/检测/组装层；`chart_context.py` 的 `render_reasoned_context` 末尾按 slice 级 `time_context_injection` 参数追加 temporal context 段；新建 `scripts/phase6_6d_orchestrator.py` 持有独立 schedule/ledger/gate/receipt/report；`profiles.py` 按三态分别定义 marker 可见性；`run_benchmark.py` 扩展 `_CODE_SCOPE` 和 arm 枚举。

**Tech Stack:** Python 3.11+、dataclasses、argparse、JSON/JSONL、SHA-256、pytest、monkeypatch、PowerShell。

---

## 实施边界与基线

设计依据：`docs/superpowers/specs/2026-08-06-phase6-6d-v1-bazi-time-context-design.md`（v6.1，commit `a2bb6e0`）。

6B2 已关闭（commit `f96667d`，verdict=ROLLBACK，protocol=single）。6D 是独立实验，不 resume 6B2 run，不共享 6B2 schedule/gate/receipt。

只修改以下生产文件：

- `benchmark/formatters/bazi_time_context.py`（新建）
- `benchmark/formatters/chart_context.py`（改造 `render_reasoned_context`）
- `benchmark/formatters/two_stage_reasoning.py`（关系计算迁移，two-stage 路径不改）
- `benchmark/runners/profiles.py`（visibility 矩阵按三态扩展）
- `benchmark/runners/run_benchmark.py`（`_CODE_SCOPE` + arm 枚举 + `--time-context-injection` flag）
- `scripts/phase6_6d_orchestrator.py`（新建）

只修改/新建以下测试文件：

- `tests/test_bazi_time_context.py`（新建）
- `tests/test_chart_context.py`（新增注入 on/off 测试）
- `tests/test_phase6_6d_orchestrator.py`（新建）

不修改：`claude_api.py`、`phase6_6b2_orchestrator.py`、`phase6_6b2_sealed_workflow.py`、`dual_system_reasoning.py`、`bazi_calculator.py`。

### 审核修订映射

| Spec 条目 | 计划落点 |
|---|---|
| §3 历史流年计算 | Task 2 |
| §3.4 三态路由 | Task 4 |
| §3.5 目标年份转换 | Task 4 |
| §5.1-5.5 独立 6D 实验链 | Task 7-8 |
| §6 注入点 | Task 5 |
| §7 可见性/Schema/Resume | Task 5-7 |
| §8 两阶段评估 | Task 8（阶段一）+ Task 9（阶段二前置） |
| §9 检测规则 R1-R7 | Task 3 |
| §10 抽离设计 | Task 2-5 |

---

## Task 1: 基线验证与模块脚手架

**目标：** 确认起始状态干净，创建 `bazi_time_context.py` 空模块与测试文件。

- [ ] 1.1 运行 6B2 定向基线：`python -m pytest tests/test_phase6_6b2.py tests/test_phase6_profiles.py tests/test_dual_system_reasoning.py tests/test_claude_api.py -q`，记录 passed/failed
- [ ] 1.2 运行 Phase 6 广泛基线：`$files = (Get-ChildItem tests -Filter 'test_phase6_*.py').FullName; python -m pytest $files tests/test_dual_system_reasoning.py tests/test_claude_api.py -q`，记录 passed/failed
- [ ] 1.3 创建 `benchmark/formatters/bazi_time_context.py`，含模块 docstring 和 `from __future__ import annotations`
- [ ] 1.4 创建 `tests/test_bazi_time_context.py`，含模块 docstring 和 `from __future__ import annotations`
- [ ] 1.5 运行 `python -m py_compile benchmark/formatters/bazi_time_context.py`，确认编译通过
- [ ] 1.6 运行 `python -m pytest tests/test_bazi_time_context.py -q`，确认空测试通过

**验证：** 基线数字记录在案；新模块和测试文件存在且可编译/可运行。

---

## Task 2: 关系计算层迁移 + 任意年份流年计算

**目标：** 从 `two_stage_reasoning.py` 迁移关系计算函数到新模块；实现 `calculate_liunian_for_year` 支持任意年份。

- [ ] 2.1 写测试 `test_compute_branch_relation_chong`：验证子午相冲
- [ ] 2.2 写测试 `test_compute_branch_relation_liuhe`：验证子丑六合
- [ ] 2.3 写测试 `test_compute_gan_relation_sheng`：验证甲生丙
- [ ] 2.4 写测试 `test_compute_gan_relation_ke`：验证庚克甲
- [ ] 2.5 写测试 `test_calculate_liunian_for_year_1989`：验证历史年份 1989 的干支（己巳）
- [ ] 2.6 写测试 `test_calculate_liunian_for_year_2024`：验证当前年份 2024 的干支（甲辰）
- [ ] 2.7 写测试 `test_calculate_liunian_for_year_boundary_1900`：验证 1900 边界
- [ ] 2.8 写测试 `test_calculate_liunian_for_year_out_of_range`：验证 1899 和 2101 fail-closed
- [ ] 2.9 写测试 `test_calculate_liunian_for_year_shishen`：验证十神计算正确
- [ ] 2.10 实现 `compute_branch_relation` / `compute_gan_relation` / `compute_shishen_combo`（从 two_stage_reasoning.py 迁移）
- [ ] 2.11 实现 `calculate_liunian_for_year(target_year, day_master_gan)`，基于 `(target_year - 4) % 60`
- [ ] 2.12 运行 `python -m pytest tests/test_bazi_time_context.py -q`，全部通过
- [ ] 2.13 运行 `python -m pytest tests/test_two_stage_reasoning.py -q`（如存在），确认迁移未破坏现有

**验证：** 关系计算函数在新模块可用；`calculate_liunian_for_year(1989)` 返回己巳；超出 1900-2100 范围 fail-closed。

---

## Task 3: 检测层 R1-R7 + 三态分类

**目标：** 实现 `is_temporal_routed` 和 `detect_time_context`，返回三态。

- [ ] 3.1 写测试 `test_r1_explicit_time_keyword`：题目含"哪年"命中 R1
- [ ] 3.2 写测试 `test_r2_option_four_digit_year`：选项为 4 位年份命中 R2
- [ ] 3.3 写测试 `test_r3_age_range`：选项含"25-30岁"命中 R3
- [ ] 3.4 写测试 `test_r4_dayun_keyword`：题目含"大运"命中 R4
- [ ] 3.5 写测试 `test_r5_when_year_mixed`：题目含"何时"且选项含年份命中 R5
- [ ] 3.6 写测试 `test_r6_question_body_year`：题目正文含"1980年"命中 R6（用 `(?<!\d)\d{4}(?!\d)` 正则）
- [ ] 3.7 写测试 `test_r6_long_digit_no_false_positive`：题目含"12345678"不误命中 R6
- [ ] 3.8 写测试 `test_r7_single_age`：选项 `A. 30岁` 剥离 `A.` 后命中 R7
- [ ] 3.9 写测试 `test_r7_plain_number`：选项 `A. 30` 剥离 `A.` 后命中 R7
- [ ] 3.10 写测试 `test_route_state_routed_with_targets`：R6 命中 -> `ROUTED_WITH_TARGETS`
- [ ] 3.11 写测试 `test_route_state_routed_without_targets`：R4 命中但无年份 -> `ROUTED_WITHOUT_TARGETS`
- [ ] 3.12 写测试 `test_route_state_not_routed`：无规则命中 -> `NOT_ROUTED`
- [ ] 3.13 写测试 `test_domain_not_used_for_routing`：验证 domain 字段不影响路由结果
- [ ] 3.14 实现 `is_temporal_routed(question, options) -> bool`
- [ ] 3.15 实现 `detect_time_context(question, options) -> (route_state, matched_rules)`
- [ ] 3.16 运行 2024+2025 离线路由审计脚本，确认 N=31（2024:18 + 2025:13）
- [ ] 3.17 运行 `python -m pytest tests/test_bazi_time_context.py -q`，全部通过

**验证：** R1-R7 各有独立测试；2024+2025 路由命中数与 spec 一致（31）；domain 不影响路由。

---

## Task 4: 目标年份提取层 + TimeContext 数据契约

**目标：** 实现 `extract_target_years` 和 `build_time_context`，返回 `TimeContext` frozen dataclass。

- [ ] 4.1 写测试 `test_extract_target_years_four_digit`：选项 1989 -> target_years=(1989,)
- [ ] 4.2 写测试 `test_extract_target_years_age_range`：选项"25-30岁" + birth_year=1980 -> target_years=(2005,2010)
- [ ] 4.3 写测试 `test_extract_target_years_single_age`：选项"30岁" + birth_year=1980 -> target_years=(2010,)
- [ ] 4.4 写测试 `test_extract_target_years_routed_without_targets`：R4 命中无年份 -> target_years=()
- [ ] 4.5 写测试 `test_time_context_is_frozen`：验证 dataclass frozen，不可变
- [ ] 4.6 写测试 `test_time_context_uses_tuple_not_list`：验证 dayun_table/option_liunian 是 tuple
- [ ] 4.7 写测试 `test_time_context_to_dict`：验证 to_dict 返回可 JSON 序列化 dict
- [ ] 4.8 写测试 `test_time_context_canonical_json`：验证相同输入产生相同 canonical JSON
- [ ] 4.9 写测试 `test_time_context_sha256`：验证相同输入产生相同 SHA-256
- [ ] 4.10 实现 `extract_target_years(options, question, birth_year) -> (tuple[int,...], route_state)`
- [ ] 4.11 实现 `NatalStructure` / `DayunRow` / `OptionLiunian` / `TimeContextKind` / `TemporalRouteState` dataclass
- [ ] 4.12 实现 `build_natal_structure(chart) -> NatalStructure`
- [ ] 4.13 实现 `build_dayun_table(chart) -> tuple[DayunRow,...]`
- [ ] 4.14 实现 `build_target_liunian(chart, target_years, birth_year) -> tuple[OptionLiunian,...]`
- [ ] 4.15 实现 `build_time_context(case) -> TimeContext`，含 `to_dict` / `canonical_json` / `sha256`
- [ ] 4.16 运行 `python -m pytest tests/test_bazi_time_context.py -q`，全部通过

**验证：** 年龄区间保留起止年（不取中点）；TimeContext 全 tuple + canonical JSON + SHA 可复现。

---

## Task 5: chart_context 注入 + profiles 可见性矩阵

**目标：** `render_reasoned_context` 末尾按 `time_context_injection` 追加 temporal context 段；`profiles.py` 按三态分别定义 marker。

- [ ] 5.1 写测试 `test_render_reasoned_context_off_no_temporal`：injection=off 时无 temporal markers
- [ ] 5.2 写测试 `test_render_reasoned_context_on_routed_with_targets`：injection=on + ROUTED_WITH_TARGETS 时含全部 3 个 markers
- [ ] 5.3 写测试 `test_render_reasoned_context_on_routed_without_targets`：injection=on + ROUTED_WITHOUT_TARGETS 时含 2 个 markers，不含 `【目标流年详析】`
- [ ] 5.4 写测试 `test_render_reasoned_context_on_not_routed`：injection=on + NOT_ROUTED 时无 temporal markers
- [ ] 5.5 写测试 `test_visibility_off_denies_all_temporal`：injection=off 时 3 个 markers 在 deny 侧
- [ ] 5.6 写测试 `test_visibility_on_not_routed_denies_all`：injection=on + NOT_ROUTED 时 3 个 markers 在 deny 侧
- [ ] 5.7 写测试 `test_visibility_on_without_targets_denies_liunian`：injection=on + WITHOUT_TARGETS 时 `【目标流年详析】` 在 deny 侧
- [ ] 5.8 写测试 `test_visibility_on_with_targets_requires_all`：injection=on + WITH_TARGETS 时 3 个 markers 在 required 侧
- [ ] 5.9 改造 `render_reasoned_context`：加 `time_context_injection` 参数，末尾按三态追加
- [ ] 5.10 在 `profiles.py` 定义 `_TEMPORAL_CONTEXT_MARKERS` frozenset
- [ ] 5.11 在 `profiles.py` 扩展 `visibility_requirements`，按 injection × route_state 分别返回 required/deny
- [ ] 5.12 运行 `python -m pytest tests/test_chart_context.py tests/test_phase6_profiles.py -q`，全部通过
- [ ] 5.13 运行 6B2 定向回归，确认无破坏

**验证：** off 时无注入；on 时按三态分别注入；可见性矩阵按三态分别定义。

---

## Task 6: run_benchmark 扩展（_CODE_SCOPE + arm 枚举 + flag）

**目标：** `run_benchmark.py` 加入 `bazi_time_context.py` 到 `_CODE_SCOPE`，加入 `b1a_time_off`/`b1a_time_on` 到 arm 枚举，加 `--time-context-injection` flag。

- [ ] 6.1 写测试 `test_code_scope_includes_bazi_time_context`：验证 `_CODE_SCOPE` 含新模块
- [ ] 6.2 写测试 `test_arm_b1a_time_off_accepted`：验证 arm=`b1a_time_off` 被接受
- [ ] 6.3 写测试 `test_arm_b1a_time_on_accepted`：验证 arm=`b1a_time_on` 被接受
- [ ] 6.4 写测试 `test_time_context_injection_flag_default_off`：默认 off
- [ ] 6.5 写测试 `test_time_context_injection_flag_on`：`--time-context-injection on` 传入
- [ ] 6.6 写测试 `test_attempt_key_off_on_no_collision`：off/on 用不同 arm，attempt_key 不碰撞
- [ ] 6.7 在 `_CODE_SCOPE` 加入 `"benchmark/formatters/bazi_time_context.py"`
- [ ] 6.8 在 arm 枚举加入 `b1a_time_off` / `b1a_time_on`
- [ ] 6.9 加 `--time-context-injection {off,on}` flag（默认 off）
- [ ] 6.10 运行 `python -m pytest tests/test_phase6_6b2.py tests/test_phase6_profiles.py -q`，确认无破坏
- [ ] 6.11 运行 Phase 6 广泛回归，确认无新增失败

**验证：** code_fingerprint 包含新模块；off/on arm 不碰撞；flag 默认 off。

---

## Task 7: 6D orchestrator 新建（schedule + receipt + resume 隔离）

**目标：** 新建 `scripts/phase6_6d_orchestrator.py`，含独立 schedule/ledger/`6D_RECEIPT_REQUIRED_FIELDS`/`check_6d_gate`/`_prepare_run_context`。

- [ ] 7.1 写测试 `test_6d_schedule_per_year_grouping`：2024->3 groups(8,8,2)，2025->2 groups(8,5)
- [ ] 7.2 写测试 `test_6d_schedule_tail_group_scheduled`：尾组 scheduled=真实题数（2 或 5），不是 8
- [ ] 7.3 写测试 `test_6d_schedule_global_scheduled_186`：global scheduled = 31×2×3 = 186
- [ ] 7.4 写测试 `test_6d_schedule_off_on_arms`：每 slice 的 arm 是 `b1a_time_off` 或 `b1a_time_on`
- [ ] 7.5 写测试 `test_6d_receipt_required_fields`：receipt 含 6B2 全部字段 + 5 个 temporal run 级字段
- [ ] 7.6 写测试 `test_6d_resume_isolation_version_mismatch`：temporal_context_version 不匹配 fail-closed
- [ ] 7.7 写测试 `test_6d_resume_isolation_routed_cases_mismatch`：temporal_routed_cases_sha256 不匹配 fail-closed
- [ ] 7.8 写测试 `test_6d_resume_isolation_strategy_mismatch`：extraction_strategy_sha256 不匹配 fail-closed
- [ ] 7.9 写测试 `test_6d_resume_isolation_condition_manifest_mismatch`：condition_manifest_sha256 不匹配 fail-closed
- [ ] 7.10 写测试 `test_6d_condition_manifest_canonical_json`：验证 canonical JSON 排序和字段
- [ ] 7.11 写测试 `test_6d_no_cross_orchestrator_resume`：6D run 不能 resume 6B2 run
- [ ] 7.12 实现 `_build_schedule(years, repeats, per_group=8)`：按年度分组
- [ ] 7.13 实现 `6D_RECEIPT_REQUIRED_FIELDS`：6B2 字段 + temporal run 级字段
- [ ] 7.14 实现 `_prepare_run_context`：含 resume 隔离检查
- [ ] 7.15 实现 `condition_manifest_sha256`：canonical JSON + SHA-256
- [ ] 7.16 实现 `check_6d_gate`：单阶段 receipt 自验
- [ ] 7.17 运行 `python -m pytest tests/test_phase6_6d_orchestrator.py -q`，全部通过

**验证：** schedule 按年度分组；尾组 scheduled=真实题数；resume 隔离 fail-closed；receipt 含 temporal 字段。

---

## Task 8: 6D gate 实现 + 阶段一离线门

**目标：** 实现 `compute_6d_gate`（五分支完备），执行阶段一零 API 离线门。

- [ ] 8.1 写测试 `test_gate_blocked_call_failed_off`：off 臂 call_failed>0 -> BLOCKED
- [ ] 8.2 写测试 `test_gate_blocked_call_failed_on`：on 臂 call_failed>0 -> BLOCKED
- [ ] 8.3 写测试 `test_gate_blocked_parser_rate_off`：off 臂 parser_rate<0.85 -> BLOCKED
- [ ] 8.4 写测试 `test_gate_blocked_parser_rate_on`：on 臂 parser_rate<0.85 -> BLOCKED
- [ ] 8.5 写测试 `test_gate_blocked_early_return`：call_failed 命中后不继续准确率 gate（verdict 不被覆盖）
- [ ] 8.6 写测试 `test_gate_paired_delta_denominator`：paired_delta = sum(case_delta)/(N×3)，不是 N×2×3
- [ ] 8.7 写测试 `test_gate_promote`：paired_delta>=0.05 且 min_case_delta>=0 -> PROMOTE
- [ ] 8.8 写测试 `test_gate_review_required`：paired_delta>=0.05 且 min_case_delta<0 -> REVIEW_REQUIRED
- [ ] 8.9 写测试 `test_gate_non_inferior`：-0.02<=paired_delta<0.05 -> NON_INFERIOR
- [ ] 8.10 写测试 `test_gate_rollback`：paired_delta<-0.02 -> ROLLBACK
- [ ] 8.11 写测试 `test_gate_completeness_single_main_stage`：每 (year,repeat,case_id) 恰一条 off/main + on/main
- [ ] 8.12 实现 `compute_6d_gate(details, n_cases)`：基础设施门早返回 + 准确率五分支
- [ ] 8.13 运行 `python -m pytest tests/test_phase6_6d_orchestrator.py -q`，全部通过
- [ ] 8.14 执行阶段一离线门脚本：生成 `temporal_routed_cases.json`（含 year+dataset_sha256+case_id+domain+route_state+matched_rules+target_years）
- [ ] 8.15 验证 N=31（2024:18 + 2025:13），N>=20
- [ ] 8.16 验证 `temporal_routed_cases_sha256` 可计算
- [ ] 8.17 运行全量回归：`$files = (Get-ChildItem tests -Filter 'test_phase6_*.py').FullName; python -m pytest $files tests/test_dual_system_reasoning.py tests/test_claude_api.py tests/test_bazi_time_context.py -q`，无新增失败

**验证：** gate 五分支完备；BLOCKED 早返回；paired_delta 分母 N×3；`temporal_routed_cases.json` 冻结。

---

## Task 9: 阶段二前置准备（不启动真实 API）

**目标：** 准备阶段二真实 paired dev 的命令和参数，但不启动真实 API 调用。

- [ ] 9.1 写 `compute_6d_gate` 的 fake runner 集成测试（与 6B2 fake runner 模式一致）
- [ ] 9.2 验证 off/on paired 闭环：fake runner 生成 off+on details，gate 计算 paired_delta
- [ ] 9.3 验证 AB/BA 调度：case_id hash 分配首跑顺序
- [ ] 9.4 输出阶段二启动命令（不执行）：
  ```powershell
  python scripts/phase6_6d_orchestrator.py run_dev --provider deepseek --model deepseek-v4-flash --output-dir docs/phase6/6d --run-id phase6-6d-v1-20260807-r1
  ```
- [ ] 9.5 输出阶段二前置条件清单：
  - `DEEPSEEK_API_KEY` 可用
  - 2024+2025 数据集可读
  - `temporal_routed_cases.json` 已冻结
  - `temporal_context_version` 已冻结
- [ ] 9.6 运行全量回归，确认无新增失败
- [ ] 9.7 输出 Task 9 完成报告，状态=`READY_FOR_SMOKE`

**验证：** fake runner paired 闭环通过；阶段二命令和前置条件清单输出；真实 API 未启动。

---

## 完成定义

6D v1 实施计划阶段的完成定义：

1. Task 1-9 全部完成
2. 全量回归无新增失败
3. `temporal_routed_cases.json` 冻结（N=31）
4. `temporal_context_version` 冻结
5. gate 五分支完备 + BLOCKED 早返回
6. 阶段二前置条件清单输出
7. 真实 API 未启动（状态=`READY_FOR_SMOKE`）

阶段二真实 paired dev 需用户明确批准后启动，不在本计划范围内。
