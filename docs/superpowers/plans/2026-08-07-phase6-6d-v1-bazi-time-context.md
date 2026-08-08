# Phase 6 6D v1 Bazi Time Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 6D v1 的"八字命局 × 大运 × 目标流年"确定性注入实现为独立可复用模块 + 独立可运行 6D 实验链，通过零 API 离线门验证工程契约，为真实 paired dev 准备完备基础设施。

**Architecture:** 新建 `benchmark/formatters/bazi_time_context.py` 持有关系计算/流年计算/检测/组装层；`chart_context.py` 的 `render_reasoned_context` 末尾按 slice 级 `time_context_injection` 参数追加 temporal context 段；`run_benchmark.py` 的 `Phase6Context` / `RESUME_MANIFEST_FIELDS` / `_REASONED_ARM_MAP` / `_CODE_SCOPE` / `_prepare_prompt` 全链路贯穿 injection；新建 `scripts/phase6_6d_orchestrator.py` 持有完整可执行 schedule/ledger/runner-command/merge/gate/report/archive/receipt/CLI；新建离线门脚本生成并冻结 `temporal_routed_cases.json`。

**Tech Stack:** Python 3.11+、dataclasses、argparse、JSON/JSONL、SHA-256、pytest、monkeypatch、PowerShell。

---

## 实施边界与基线

设计依据：`docs/superpowers/specs/2026-08-06-phase6-6d-v1-bazi-time-context-design.md`（v6.1，commit `a2bb6e0`）。

6B2 已关闭（commit `f96667d`，verdict=ROLLBACK，protocol=single）。6D 是独立实验，不 resume 6B2 run，不共享 6B2 schedule/gate/receipt。

只修改以下生产文件：

- `benchmark/formatters/bazi_time_context.py`（新建）
- `benchmark/formatters/chart_context.py`（改造 `render_reasoned_context`）
- `benchmark/formatters/two_stage_reasoning.py`（关系计算迁移到新模块，旧定义改为 re-export）
- `benchmark/runners/profiles.py`（visibility 矩阵按三态扩展）
- `benchmark/runners/run_benchmark.py`（`Phase6Context` + `RESUME_MANIFEST_FIELDS` + `_REASONED_ARM_MAP` + `_CODE_SCOPE` + `_prepare_prompt` + CLI flag）
- `scripts/phase6_6d_orchestrator.py`（新建，完整可执行）
- `scripts/phase6_6d_offline_gate.py`（新建，离线门 + routed manifest 生成）

只修改/新建以下测试文件：

- `tests/test_bazi_time_context.py`（新建）
- `tests/test_chart_context.py`（新增注入 on/off 测试）
- `tests/test_phase6_6d_orchestrator.py`（新建）
- `tests/test_phase6_6d_offline_gate.py`（新建）

不修改：`claude_api.py`、`phase6_6b2_orchestrator.py`、`phase6_6b2_sealed_workflow.py`、`dual_system_reasoning.py`、`bazi_calculator.py`。

### TDD 约定

每个任务遵循 RED-GREEN-COMMIT 循环：
- **RED**：先写测试，运行确认失败（`python -m pytest <file> -q`）
- **GREEN**：实现最小代码使测试通过
- **COMMIT**：每个子任务完成后提交（语义化提交信息）

---

## Task 1: 基线验证与受控工作区检查

**目标：** 确认起始状态干净，记录基线数字。

- [ ] 1.1 RED：运行 6B2 定向基线并记录数字
  ```powershell
  python -m pytest tests/test_phase6_6b2.py tests/test_phase6_profiles.py tests/test_dual_system_reasoning.py tests/test_claude_api.py -q --basetemp .tmp/pytest-6d-plan-baseline
  ```
  记录 passed/failed 到 `.tmp/6d-baseline.txt`
- [ ] 1.2 RED：运行 Phase 6 广泛基线并记录数字
  ```powershell
  $files = (Get-ChildItem tests -Filter 'test_phase6_*.py').FullName
  python -m pytest $files tests/test_dual_system_reasoning.py tests/test_claude_api.py -q --basetemp .tmp/pytest-6d-plan-phase6-baseline
  ```
  记录 passed/failed 到 `.tmp/6d-baseline.txt`
- [ ] 1.3 GREEN：确认工作区干净（`git status --short` 仅 `docs/phase6/6b2/` untracked）
- [ ] 1.4 GREEN：将基线数字写入持久化审计文件 `docs/phase6/6d/baseline-20260807.md`（含定向 + 广泛 passed/failed）
- [ ] 1.5 COMMIT：`docs(6d): record baseline before implementation`

**验证：** 基线数字记录在持久化文件（非 `.tmp/`）；工作区干净。

---

## Task 2: 关系计算迁移 + 旧实现一致性测试

**目标：** 从 `two_stage_reasoning.py` 迁移关系计算到新模块，旧定义改为 re-export，确保无两份逻辑。

- [ ] 2.1 GREEN：创建 `benchmark/formatters/bazi_time_context.py`（含 docstring + `from __future__ import annotations`）
- [ ] 2.2 RED：写快照一致性测试 `test_legacy_matches_new_branch_relation`：对全部 12 地支两两组合，旧 `_compute_branch_relation` 与新 `compute_branch_relation` 结果一致
  ```python
  # tests/test_bazi_time_context.py
  from benchmark.formatters.two_stage_reasoning import _compute_branch_relation as legacy
  from benchmark.formatters.bazi_time_context import compute_branch_relation as new
  DIZHI = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
  def test_legacy_matches_new_branch_relation():
      for a in DIZHI:
          for b in DIZHI:
              assert legacy(a, b) == new(a, b)
  ```
  运行 `python -m pytest tests/test_bazi_time_context.py::test_legacy_matches_new_branch_relation -q`，确认失败（新函数未实现）
- [ ] 2.3 GREEN：实现 `compute_branch_relation`（从 two_stage_reasoning.py:367 复制逻辑）
- [ ] 2.4 RED：写 `test_legacy_matches_new_gan_relation`：对全部 10 天干两两组合一致性
- [ ] 2.5 GREEN：实现 `compute_gan_relation`（从 two_stage_reasoning.py:438 复制）
- [ ] 2.6 RED：写 `test_calculate_liunian_for_year_1989` -> 己巳
- [ ] 2.7 RED：写 `test_calculate_liunian_for_year_out_of_range` -> 1899/2101 fail-closed
- [ ] 2.8 GREEN：实现 `calculate_liunian_for_year(target_year, day_master_gan)`
- [ ] 2.9 RED：写 `test_legacy_matches_new_shishen_combo`：对全部十神两两组合，旧 inline 逻辑与新 `compute_shishen_combo` 结果一致
- [ ] 2.9a GREEN：实现 `compute_shishen_combo(dy_shishen, ln_shishen)`（从 two_stage_reasoning.py:743 迁移）
- [ ] 2.9b GREEN：改造 `two_stage_reasoning.py` 的 `_build_dayun_evidence`，inline combo 逻辑改为调用新 `compute_shishen_combo`
- [ ] 2.10 GREEN：改造 `two_stage_reasoning.py`，旧 `_compute_branch_relation` / `_compute_gan_relation` 改为从新模块 re-export
  ```python
  from benchmark.formatters.bazi_time_context import (
      compute_branch_relation as _compute_branch_relation,
      compute_gan_relation as _compute_gan_relation,
  )
  ```
- [ ] 2.11 GREEN：运行 `python -m pytest tests/test_bazi_time_context.py tests/test_two_stage_reasoning.py -q`，全部通过
- [ ] 2.12 COMMIT：`feat(6d): migrate relation computation to bazi_time_context module`

**验证：** 旧/新一致性测试通过；`calculate_liunian_for_year(1989)` 返回己巳；超范围 fail-closed；`two_stage_reasoning.py` 无重复逻辑（re-export）。

---

## Task 3: R1-R7 检测原语

**目标：** 实现 `detect_temporal_rules(question, options) -> matched_rules`，只返回命中的规则集合，不返回三态（三态需要 Task 4 的目标年份）。

- [ ] 3.1 RED：写 `test_r1_explicit_time_keyword`："哪年结婚" -> 含 "R1"
- [ ] 3.2 RED：写 `test_r2_option_four_digit_year`：选项 ["1989","1990","1991","1992"] -> 含 "R2"
- [ ] 3.3 RED：写 `test_r3_age_range`：选项 ["25-30岁","31-35岁"] -> 含 "R3"
- [ ] 3.4 RED：写 `test_r4_dayun_keyword`："大运什么时候开始" -> 含 "R4"
- [ ] 3.5 RED：写 `test_r5_when_year_mixed`："何时结婚" + 选项含 "1995" -> 含 "R5"
- [ ] 3.6 RED：写 `test_r6_question_body_year`："1980年发生何事？" -> 含 "R6"
- [ ] 3.7 RED：写 `test_r6_long_digit_no_false_positive`："订单号12345678" -> 不含 "R6"
- [ ] 3.8 RED：写 `test_r7_single_age`：选项 ["A. 30岁","B. 35岁"] -> 含 "R7"
- [ ] 3.9 RED：写 `test_r7_plain_number`：选项 ["A. 30","B. 35"] -> 含 "R7"
- [ ] 3.10 RED：写 `test_no_rules_matched`：普通题 -> 空集合
- [ ] 3.11 GREEN：实现 `detect_temporal_rules(question, options) -> frozenset[str]`
  - R1: 现有 `_TIME_KEYWORDS`
  - R2: 剥离 `A.` 后 `^\d{4}$`
  - R3: 剥离 `A.` 后 `\d+[-–]\d+` 且含"岁"
  - R4: 扩展关键词 ["大运","流年","岁运","年运"]
  - R5: 题目含 ["何时","哪年","几年后","几年"] 且选项含 4 位年份
  - R6: 题目正文 `(?<!\d)\d{4}(?!\d)` 且 1900-2100
  - R7: 剥离 `A.` 后 `^\d+岁?$` 且 1-120
- [ ] 3.12 GREEN：迁移 `_TIME_KEYWORDS` 和 `_KEY_SHENSHA` 到新模块，旧模块 re-export
- [ ] 3.13 GREEN：运行 2024+2025 离线审计（用临时脚本），确认 R1-R7 命中分布与 spec 一致
- [ ] 3.14 GREEN：运行 `python -m pytest tests/test_bazi_time_context.py -q`，全部通过
- [ ] 3.15 COMMIT：`feat(6d): implement R1-R7 temporal detection primitives`

**验证：** R1-R7 各有独立测试；R6 正则避免长数字误命中；2024+2025 命中分布与 spec 一致。

---

## Task 4: 年份提取 + 三态分类 + TimeContext

**目标：** 实现 `extract_target_years` / `classify_route_state` / `build_time_context`，返回 `TimeContext` frozen dataclass。

- [ ] 4.1 RED：写 `test_extract_target_years_four_digit`：选项 "1989" -> (1989,)
- [ ] 4.2 RED：写 `test_extract_target_years_age_range`：选项 "25-30岁" + birth_year=1980 -> (2005, 2010)（起止年，不取中点）
- [ ] 4.3 RED：写 `test_extract_target_years_single_age`：选项 "30岁" + birth_year=1980 -> (2010,)
- [ ] 4.4 RED：写 `test_extract_target_years_routed_without_targets`：R4 命中无年份 -> ()
- [ ] 4.4a RED：写 `test_extract_target_years_years_after_with_base`："2020年起3年后" + base_year=2020 -> (2023,)
- [ ] 4.4b RED：写 `test_extract_target_years_years_after_no_base`："3年后" 无基准年份 -> () + ROUTED_WITHOUT_TARGETS
- [ ] 4.4c RED：写 `test_extract_target_years_years_after_multiple`：多个"几年后"选项，各有 base_year
- [ ] 4.4d RED：写 `test_extract_target_years_out_of_range_fail_closed`：计算结果 > 2100 或 < 1900 -> fail-closed
- [ ] 4.5 RED：写 `test_classify_route_state_with_targets`：matched_rules 含 R6 + target_years 非空 -> ROUTED_WITH_TARGETS
- [ ] 4.6 RED：写 `test_classify_route_state_without_targets`：matched_rules 含 R4 + target_years 空 -> ROUTED_WITHOUT_TARGETS
- [ ] 4.7 RED：写 `test_classify_route_state_not_routed`：matched_rules 空 -> NOT_ROUTED
- [ ] 4.8 RED：写 `test_time_context_is_frozen`：试图修改字段 -> FrozenInstanceError
- [ ] 4.9 RED：写 `test_time_context_uses_tuple_not_list`：dayun_table/option_liunian 是 tuple
- [ ] 4.10 RED：写 `test_time_context_canonical_json_reproducible`：相同输入 -> 相同 canonical JSON + 相同 SHA-256
- [ ] 4.11 GREEN：实现 `extract_target_years(question, options, birth_year) -> tuple[int, ...]`
- [ ] 4.12 GREEN：实现 `classify_route_state(matched_rules, target_years) -> TemporalRouteState`
- [ ] 4.13 GREEN：实现 dataclass `NatalStructure` / `DayunRow` / `OptionLiunian` / `TimeContextKind` / `TemporalRouteState`（全 tuple）
- [ ] 4.14 GREEN：实现 `build_natal_structure(chart)` / `build_dayun_table(chart)` / `build_target_liunian(chart, target_years, birth_year)`
- [ ] 4.15 GREEN：实现 `build_time_context(case) -> TimeContext`，含 `to_dict()` / `canonical_json()` / `sha256()`
- [ ] 4.16 GREEN：运行 `python -m pytest tests/test_bazi_time_context.py -q`，全部通过
- [ ] 4.17 COMMIT：`feat(6d): implement target year extraction and TimeContext dataclass`

**验证：** 年龄区间保留起止年；TimeContext 全 tuple + canonical JSON + SHA 可复现；三态分类正确。

---

## Task 5: 离线 routed manifest 生成与冻结

**目标：** 新建 `scripts/phase6_6d_offline_gate.py`，生成并冻结 `temporal_routed_cases.json`，后续 Task 依赖此文件。

- [ ] 5.1 RED：写 `test_offline_gate_generates_routed_manifest`：给定 2024+2025 数据集，输出 JSON 含每项 `year + dataset_sha256 + case_id + domain + route_state + matched_rules + target_years`
- [ ] 5.2 RED：写 `test_offline_gate_manifest_canonical_json`：相同输入 -> 相同 `temporal_routed_cases_sha256`
- [ ] 5.3 RED：写 `test_offline_gate_atomic_write`：写入是原子的（`.tmp` + rename）
- [ ] 5.4 RED：写 `test_offline_gate_dataset_sha_verified`：每项 dataset_sha256 与实际文件 SHA 一致
- [ ] 5.5 RED：写 `test_offline_gate_n_31`：2024(18) + 2025(13) = 31
- [ ] 5.5a RED：写 `test_offline_gate_blocks_when_n_below_20`：若 N < 20，离线门输出 BLOCKED，不生成 routed manifest
- [ ] 5.5b RED：写 `test_offline_gate_blocks_does_not_overwrite_existing_manifest`：BLOCKED 时若输出路径已有旧 manifest，不覆盖
- [ ] 5.5c RED：写 `test_offline_gate_writes_phase1_receipt_pass`：N>=20 时原子写 `phase1_receipt.json`，含 `status=PASS` + `dataset_set_sha256` + `temporal_routed_cases_sha256` + `n_routed`
- [ ] 5.5d RED：写 `test_offline_gate_writes_phase1_receipt_blocked`：N<20 时原子写 `phase1_receipt.json`，含 `status=BLOCKED`，旧 manifest 不覆盖
- [ ] 5.6 GREEN：实现 `scripts/phase6_6d_offline_gate.py`：含 phase1 receipt 原子写入（PASS/BLOCKED）
  - CLI：`python scripts/phase6_6d_offline_gate.py --datasets 2024,2025 --output docs/phase6/6d/temporal_routed_cases.json`
  - 读取数据集，对每 case 调 `detect_temporal_rules` + `extract_target_years` + `classify_route_state`
  - 原子写入 JSON（`.tmp` + `os.replace`）
  - 计算 `temporal_routed_cases_sha256`（canonical JSON）
  - 输出统计：N_total / N_routed / per-year / per-rule
- [ ] 5.7 GREEN：运行脚本生成 `docs/phase6/6d/temporal_routed_cases.json`
- [ ] 5.8 GREEN：验证 N=31，记录 `temporal_routed_cases_sha256`
- [ ] 5.9 GREEN：运行 `python -m pytest tests/test_phase6_6d_offline_gate.py -q`，全部通过
- [ ] 5.10 COMMIT：`feat(6d): offline gate generates and freezes temporal routed manifest`

**验证：** `temporal_routed_cases.json` 存在且冻结；N=31；canonical SHA 可复现；原子写入。

---

## Task 6: prompt 注入 + visibility 矩阵

**目标：** `render_reasoned_context` 末尾按 `time_context_injection` 追加 temporal context 段；`profiles.py` 按三态分别定义 marker。

- [ ] 6.1 RED：写 `test_render_reasoned_context_off_no_temporal`：injection=off 时输出无 temporal markers
- [ ] 6.2 RED：写 `test_render_reasoned_context_on_routed_with_targets`：injection=on + ROUTED_WITH_TARGETS 时含全部 3 个 markers
- [ ] 6.3 RED：写 `test_render_reasoned_context_on_routed_without_targets`：injection=on + ROUTED_WITHOUT_TARGETS 时含 2 个 markers，不含 `【目标流年详析】`
- [ ] 6.4 RED：写 `test_render_reasoned_context_on_not_routed`：injection=on + NOT_ROUTED 时无 temporal markers
- [ ] 6.5 RED：写 `test_visibility_off_denies_all_temporal`：injection=off 时 3 个 markers 在 deny 侧
- [ ] 6.6 RED：写 `test_visibility_on_not_routed_denies_all`：injection=on + NOT_ROUTED 时 3 个 markers 在 deny 侧
- [ ] 6.7 RED：写 `test_visibility_on_without_targets_denies_liunian`：injection=on + WITHOUT_TARGETS 时 `【目标流年详析】` 在 deny 侧
- [ ] 6.8 RED：写 `test_visibility_on_with_targets_requires_all`：injection=on + WITH_TARGETS 时 3 个 markers 在 required 侧
- [ ] 6.8a RED：写 `test_visibility_requirements_accepts_injection_and_route_state`：`visibility_requirements()` 签名接受 `time_context_injection` 和 `route_state` 参数
- [ ] 6.8b RED：写 `test_assert_visibility_injection_aware`：`assert_visibility()` 接受 injection + route_state，按三态校验
- [ ] 6.8c RED：写 `test_visibility_gate_injection_aware`：`visibility_gate()` 接受 injection + route_state
- [ ] 6.9 GREEN：在 `chart_context.py` 定义 `_TEMPORAL_CONTEXT_MARKERS = frozenset({"【时间上下文·预计算】","【大运排布】","【目标流年详析】"})`
- [ ] 6.10 GREEN：改造 `render_reasoned_context`：加 `time_context_injection` 参数（默认 "off"），末尾按三态追加
- [ ] 6.11 GREEN：在 `profiles.py` 定义 `_TEMPORAL_CONTEXT_MARKERS` 并扩展 `visibility_requirements`，签名加 `time_context_injection` 和 `route_state` 参数，按 injection × route_state 分别返回 required/deny
- [ ] 6.11a GREEN：改造 `assert_visibility` 和 `visibility_gate`，签名加 `time_context_injection` 和 `route_state`，透传给 `visibility_requirements`
- [ ] 6.12 GREEN：实现 `format_temporal_context(ctx: TimeContext) -> str`（在 `bazi_time_context.py` 或 `chart_context.py`）
- [ ] 6.13 GREEN：运行 `python -m pytest tests/test_chart_context.py tests/test_phase6_profiles.py -q`，全部通过
- [ ] 6.14 GREEN：运行 6B2 定向回归，确认无破坏
- [ ] 6.15 COMMIT：`feat(6d): inject temporal context into render_reasoned_context + visibility matrix`

**验证：** off 时无注入；on 时按三态分别注入；可见性矩阵按三态分别定义。

---

## Task 7: runner 全链路接线 + manifest + detail provenance

**目标：** `run_benchmark.py` 全链路贯穿 `time_context_injection`：CLI -> Phase6Context -> _prepare_prompt -> render_reasoned_context -> prompt。同时纳入 RESUME_MANIFEST_FIELDS 和 _REASONED_ARM_MAP。

- [ ] 7.1 RED：写 `test_phase6_context_accepts_time_context_injection`：Phase6Context 构造接受 `time_context_injection="on"`
- [ ] 7.2 RED：写 `test_resume_manifest_includes_time_context_injection`：RESUME_MANIFEST_FIELDS 含 `time_context_injection`
- [ ] 7.3 RED：写 `test_resume_manifest_missing_injection_fail_closed`：旧 manifest 缺 `time_context_injection` -> MANIFEST_MISMATCH
- [ ] 7.4 RED：写 `test_resume_manifest_off_cannot_resume_on`：stored off / current on -> MISMATCH
- [ ] 7.5 RED：写 `test_reasoned_arm_map_includes_b1a_time_off_on`：`_REASONED_ARM_MAP` 含 `b1a_time_off` 和 `b1a_time_on`，映射到 `none`
- [ ] 7.6 RED：写 `test_code_scope_includes_bazi_time_context`：`_CODE_SCOPE` 含 `benchmark/formatters/bazi_time_context.py`
- [ ] 7.7 RED：写端到端测试 `test_cli_to_prompt_off_on_different`：CLI `--time-context-injection off` vs `on` 生成不同 prompt（off 无时空块，on 有时空块）
- [ ] 7.7a RED：写 `test_prompt_diff_only_in_temporal_block`：off/on prompt 差异**仅限** temporal context 段（diff 前后非 temporal 部分逐字节一致）
- [ ] 7.8 RED：写 `test_detail_records_time_context_sha256`：detail.jsonl 每行含 `time_context_sha256`（case 级 provenance）
- [ ] 7.7b RED：写 `test_runner_receives_temporal_routed_cases_file`：runner CLI 接受 `--temporal-routed-cases-file` 参数，按 `(year, case_id)` 查表获取 route_state
- [ ] 7.7c RED：写 `test_runner_manifest_includes_routed_cases_sha`：resume manifest 含 `temporal_routed_cases_sha256`，与冻结文件 SHA 一致
- [ ] 7.7d RED：写 `test_runner_route_state_matches_frozen_manifest`：runner 本地不重算 route_state，必须与冻结 manifest 一致，不一致即阻断
- [ ] 7.8a RED：写 `test_detail_records_temporal_route_state`：detail.jsonl 每行含 `temporal_route_state`（三态之一，从冻结 manifest 查表）
- [ ] 7.8b RED：写 `test_detail_sha_on_routed_is_actual_context_sha`：on + ROUTED_WITH_TARGETS 时 `time_context_sha256` = 实际 TimeContext.sha256()
- [ ] 7.8c RED：写 `test_detail_sha_on_not_routed_is_null`：on + NOT_ROUTED 时 `time_context_sha256` = null
- [ ] 7.8d RED：写 `test_detail_sha_on_without_targets_is_actual_context_sha`：on + ROUTED_WITHOUT_TARGETS 时 `time_context_sha256` = 实际 TimeContext.sha256()（含大运排布但无目标流年）
- [ ] 7.8e RED：写 `test_detail_sha_off_is_null`：off 时 `time_context_sha256` = null（不计算 TimeContext）
- [ ] 7.8f RED：写 `test_detail_route_state_invariant_to_injection`：同一 case 的 off/on 记录**相同** `temporal_route_state`（route_state 是题目属性，不随 injection 变化）
- [ ] 7.8g RED：写 `test_detail_off_on_route_state_pair`：paired detail 中 off 和 on 的 route_state 必须一致，否则 provenance 矛盾
- [ ] 7.9 GREEN：在 `Phase6Context.__init__` 加 `time_context_injection=None` 参数
- [ ] 7.10 GREEN：在 `RESUME_MANIFEST_FIELDS` 加 `"time_context_injection"`
- [ ] 7.11 GREEN：在 `_REASONED_ARM_MAP` 加 `"b1a_time_off": "none"` 和 `"b1a_time_on": "none"`
- [ ] 7.12 GREEN：在 `_CODE_SCOPE` 加 `"benchmark/formatters/bazi_time_context.py"`
- [ ] 7.13 GREEN：改造 `_prepare_prompt` / `format_reasoned_choice_prompt`：从 `Phase6Context.time_context_injection` 读取并传入 `render_reasoned_context`
- [ ] 7.14 GREEN：加 CLI `--time-context-injection {off,on}` flag（默认 off），传入 Phase6Context
- [ ] 7.15 GREEN：在 detail 写入时追加 `time_context_sha256` 和 `temporal_route_state`；**route_state 是题目属性，off/on 相同**；SHA 语义：on+routed=实际 SHA，on+NOT_ROUTED=null，off=null
- [ ] 7.15a GREEN：实现 `compute_detail_provenance(case, route_state, time_context_injection) -> sha256_or_null`：route_state 从冻结 manifest 查表（不随 injection 变化）；off 时返回 None；on 时按 route_state 返回 SHA 或 None
- [ ] 7.15b GREEN：加 CLI 参数 `--temporal-routed-cases-file` 到 argparse，传入 `Phase6Context`
- [ ] 7.15c GREEN：在 `Phase6Context.__init__` 加 `temporal_routed_cases_file` 和 `temporal_routed_cases_sha256` 参数
- [ ] 7.15d1 RED：写 `test_runtime_target_years_match_frozen_manifest`：运行时 `build_time_context` 使用的 `target_years` 与冻结 manifest 完全一致
- [ ] 7.15d GREEN：实现 `load_routed_manifest(path) -> dict`：加载 JSON，计算 canonical SHA-256，返回 `(year, case_id) -> {route_state, matched_rules, target_years}` 完整冻结项
- [ ] 7.15e GREEN：在 `RESUME_MANIFEST_FIELDS` 加 `"temporal_routed_cases_sha256"`
- [ ] 7.15f GREEN：在 `build_resume_manifest()` 写入 `temporal_routed_cases_sha256`
- [ ] 7.15g GREEN：实现 routed manifest 查表 fail-closed：缺 case、重复 case、year/case 不匹配时 SystemExit
- [ ] 7.15h RED：写 `test_runner_preflight_visibility_injection_aware`：monkeypatch runner，验证 preflight 调用 `visibility_requirements` 时传入 `Phase6Context.time_context_injection` 和从 routed manifest 查表的 `route_state`
- [ ] 7.15i GREEN：改造 runner preflight 调用点，从 `Phase6Context.time_context_injection` 和 routed manifest 查表的 `route_state` 读取并传入 visibility 检查
- [ ] 7.16 GREEN：运行 `python -m pytest tests/test_phase6_6b2.py tests/test_phase6_profiles.py tests/test_claude_api.py -q`，确认无破坏
- [ ] 7.17 GREEN：运行 Phase 6 广泛回归，确认无新增失败
- [ ] 7.18 GREEN：运行 `python -m pytest tests/test_phase6_6b2.py tests/test_phase6_profiles.py tests/test_claude_api.py -q`，确认无破坏
- [ ] 7.19 COMMIT：`feat(6d): wire time_context_injection through runner full chain`

**验证：** CLI -> Phase6Context -> prompt 端到端贯通；off/on 生成不同 prompt（仅 temporal 段差异）；resume manifest fail-closed（含 `time_context_injection`）；detail 含 case 级 SHA + route_state（off/on route_state 相同）；runner 接入冻结 routed manifest。

> **注：** run manifest / run_context / audit 的 temporal 字段实现移到 Task 8（orchestrator 创建后）。

---

## Task 8: 6D orchestrator 完整实现（schedule/ledger/runner/merge/gate/report/archive/receipt/CLI）

**目标：** 新建 `scripts/phase6_6d_orchestrator.py`，完整可执行，含 `run_dev` 命令。

- [ ] 8.1 RED：写 `test_6d_schedule_per_year_grouping`：2024->3 groups(8,8,2)，2025->2 groups(8,5)
- [ ] 8.2 RED：写 `test_6d_schedule_tail_group_scheduled`：尾组 scheduled=真实题数（2 或 5）
- [ ] 8.3 RED：写 `test_6d_schedule_global_scheduled_186`：global scheduled = 31×2×3 = 186
- [ ] 8.4 RED：写 `test_6d_schedule_global_hard_cap_486`：global hard_cap = 486（精确值，2.61× 上限，group-pair 级 AB/BA 不拆 slice）
- [ ] 8.5 RED：写 `test_6d_schedule_off_on_arms`：每 slice arm 是 `b1a_time_off` 或 `b1a_time_on`
- [ ] 8.6 RED：写 `test_6d_runner_command_construction`：每 slice 生成正确的 `python -m benchmark.runners.run_benchmark` 命令（含 `--time-context-injection`、`--model deepseek-v4-flash`、`--thinking-mode disabled`、`--temperature 0.0`、`--profile baziqa_xjz_reasoned`、`--method direct_choice`、`--ziwei-arm none`、**`--temporal-routed-cases-file <path>`**）
- [ ] 8.6a RED：写 `test_6d_frozen_protocol_rejects_non_frozen_model`：model != deepseek-v4-flash -> SystemExit
- [ ] 8.6b RED：写 `test_6d_frozen_protocol_rejects_non_frozen_thinking`：thinking != disabled -> SystemExit
- [ ] 8.6c RED：写 `test_6d_frozen_protocol_rejects_non_frozen_temperature`：temperature != 0.0 -> SystemExit
- [ ] 8.6d RED：写 `test_6d_frozen_protocol_rejects_non_frozen_profile`：profile != baziqa_xjz_reasoned -> SystemExit
- [ ] 8.6e RED：写 `test_6d_frozen_protocol_rejects_non_frozen_method`：method != direct_choice -> SystemExit
- [ ] 8.6f RED：写 `test_6d_abba_group_pair_level`：按 SHA-256 `hashlib.sha256(f"{year}:{group_idx}".encode()).digest()[0] & 1` 决定整组 off/on 执行顺序（group-pair 级，不拆 slice，不用 Python `hash()`）
- [ ] 8.6f1 RED：写 `test_6d_abba_golden_mapping_exact`：精确断言五项黄金映射：`{"2024:g0":"BA","2024:g1":"AB","2024:g2":"AB","2025:g0":"AB","2025:g1":"BA"}`，不只测试"算法可运行"
- [ ] 8.6f2 RED：写 `test_6d_abba_actual_subprocess_sequence`：断言实际 subprocess 调用序列符合 AB/BA 分配（不只测辅助函数返回值）
- [ ] 8.6g RED：写 `test_6d_resume_protocol_drift_fail_closed`：resume 时 model/thinking/temperature/profile/method 漂移 -> fail-closed
- [ ] 8.6h RED：写 `test_6d_slice_def_contains_routed_manifest_path`：slice definition 含 `routed_manifest_path` 和 `routed_manifest_sha256`
- [ ] 8.6i RED：写 `test_6d_runner_command_includes_routed_manifest_file`：`_build_runner_command()` 显式传 `--temporal-routed-cases-file`
- [ ] 8.6j RED：写 `test_6d_pre_launch_routed_manifest_sha_check`：启动 subprocess 前验证 routed manifest 的 **canonical JSON SHA**（非原始字节 `_sha256_file()`）与 run manifest 一致，不一致阻断
- [ ] 8.7 RED：写 `test_6d_budget_ledger`：BudgetLedger 记录 scheduled/hard_cap/calls_attempted，恢复后剩余预算正确
- [ ] 8.8 RED：写 `test_6d_merge_details`：off+on details 合并为 paired 结构
- [ ] 8.9 RED：写 `test_6d_completeness_check`：每 (year,repeat,case_id) 恰一条 off/main + on/main
- [ ] 8.10 RED：写 `test_6d_receipt_fields`：receipt 含 `6D_RECEIPT_REQUIRED_FIELDS` 完整 tuple（见 8.23 枚举）
- [ ] 8.10a RED：写 `test_6d_provenance_cross_validation`：run manifest == run_context == receipt == audit，8 个 temporal run 级字段（含 `dataset_sha256_by_year` + `dataset_set_sha256` + `group_abba_order`）任何缺失或漂移均拒绝
- [ ] 8.10b RED：写 `test_6d_dataset_sha256_by_year_dual_year`：`dataset_sha256_by_year` = `{"2024":"<sha>","2025":"<sha>"}`，`dataset_set_sha256` = canonical JSON 的 SHA
- [ ] 8.10c RED：写 `test_6d_no_single_dataset_sha256_field`：receipt 不含 6B2 的单值 `dataset_sha256` 字段（改用 `dataset_set_sha256`）
- [ ] 8.11 RED：写 `test_6d_resume_isolation_all_checks`：version/strategy/routed_cases/condition_manifest 不匹配均 fail-closed
- [ ] 8.12 RED：写 `test_6d_condition_manifest_canonical_json`：canonical JSON 排序和字段（含 `group_abba_order`）
- [ ] 8.13 RED：写 `test_6d_no_cross_orchestrator_resume`：6D run 不能 resume 6B2 run
- [ ] 8.14 RED：写 `test_6d_report_generation`：report.md 含 verdict/paired_delta/min_case_delta/parser_rate
- [ ] 8.15 RED：写 `test_6d_archive_creation`：archive 目录含 audit_index.json + summary.json
- [ ] 8.16 RED：写 `test_6d_run_dev_cli`：`python scripts/phase6_6d_orchestrator.py run_dev --help` 显示正确参数
- [ ] 8.16a RED：写 `test_run_dev_validates_phase1_receipt`：`run_dev` 验证 phase1 receipt 状态=PASS + 三方 SHA 一致 + n_routed>=20，否则阻断
- [ ] 8.16b GREEN：实现 `run_dev` 的 phase1 receipt 准入校验：状态=PASS + 三方 SHA 一致 + n_routed>=20
- [ ] 8.17 GREEN：实现 `_build_schedule(years, repeats, per_group, routed_manifest_path)`：读 routed manifest，按年度分组；每 slice def 含 `routed_manifest_path` + `routed_manifest_sha256`
- [ ] 8.17a GREEN：实现 `_build_runner_command()`：显式传 `--temporal-routed-cases-file <path>`
- [ ] 8.17b GREEN：实现 pre-launch SHA 校验：subprocess 启动前验证 routed manifest 的 canonical JSON SHA（与 Task 5 / runner manifest 同口径）与 run manifest 一致
- [ ] 8.18 GREEN：实现 `_build_runner_command(slice_def)`：构造 run_benchmark CLI 命令
- [ ] 8.19 GREEN：实现 `BudgetLedger`：scheduled/hard_cap/calls_attempted 追踪
- [ ] 8.20 GREEN：实现 `_run_slice(slice_def, ledger)`：调用 runner，写 detail/events
- [ ] 8.21 GREEN：实现 `_merge_details(slices)`：off+on 配对合并
- [ ] 8.22 GREEN：实现 `_check_completeness(merged)`：single main-stage 完整性门
- [ ] 8.23 GREEN：实现 `6D_RECEIPT_REQUIRED_FIELDS` 完整 tuple：
  ```python
  6D_RECEIPT_REQUIRED_FIELDS = (
      "verdict", "stage", "run_id", "user_run_id", "archive_dir",
      "audit_index_sha256", "provider", "model",
      "thinking_mode", "model_label",
      "code_fingerprint", "dataset_set_sha256",
      "temporal_context_version", "experiment_conditions",
      "extraction_strategy_sha256", "temporal_routed_cases_sha256",
      "condition_manifest_sha256", "dataset_sha256_by_year",
      "group_abba_order",
  )
  ```
- [ ] 8.23a GREEN：实现 `build_run_manifest(...)`：含全部 8 个 temporal run 级字段（含 `dataset_sha256_by_year` + `dataset_set_sha256` + `group_abba_order`）
- [ ] 8.23b GREEN：实现 run_context / audit 写入时与 manifest 同源（交叉核对）
- [ ] 8.23c GREEN：实现 `compute_6d_gate(details, n_cases)`（从 Task 9 前移）：基础设施门早返回 BLOCKED + 准确率五分支
- [ ] 8.23d GREEN：实现 `check_6d_gate`（单阶段自验，field-level validation + temporal 字段一致性）
- [ ] 8.23e GREEN：实现冻结协议校验 `_validate_frozen_protocol(args)`：拒绝非冻结 model/thinking/temperature/profile/method
- [ ] 8.23f GREEN：实现 group-pair 级 AB/BA 调度 `_assign_group_abba_order(years, groups)`：按 **SHA-256**（非 Python `hash()`）计算 `parity = hashlib.sha256(f"{year}:{group_idx}".encode()).digest()[0] & 1`，决定整组顺序
- [ ] 8.23g GREEN：将五个 group 的 AB/BA 映射写入 condition manifest、run context、receipt、audit，resume 时交叉核对
- [ ] 8.24 GREEN：实现 `_prepare_run_context`（含 4 项 resume 隔离检查 + AB/BA 映射核对）
- [ ] 8.25 GREEN：实现 `condition_manifest_sha256`（canonical JSON）
- [ ] 8.26 GREEN：实现 `_generate_report(merged, gate_result)` -> report.md
- [ ] 8.27 GREEN：实现 `_create_archive(...)` -> audit_index.json + summary.json
- [ ] 8.28 GREEN：实现 `run_dev(args)` + `main()` + argparse
- [ ] 8.29 GREEN：运行 `python -m pytest tests/test_phase6_6d_orchestrator.py -q`，全部通过
- [ ] 8.30 GREEN：运行 `python scripts/phase6_6d_orchestrator.py run_dev --help`，确认 CLI 可用
- [ ] 8.31 COMMIT：`feat(6d): implement complete 6D orchestrator with schedule/ledger/merge/gate/report/archive/CLI`

**验证：** orchestrator 完整可执行；`run_dev --help` 可用；schedule 按年度分组；resume 隔离 fail-closed。

---

## Task 9: gate 实现 + fake-runner 端到端闭环 + READY_FOR_SMOKE

**目标：** 实现 `compute_6d_gate`（五分支完备），用 fake runner 走完整 CLI/slice/merge/report/archive/receipt 链，输出 READY_FOR_SMOKE。

- [ ] 9.1 RED：写 `test_gate_blocked_call_failed_off`：off 臂 call_failed>0 -> BLOCKED（早返回，不进准确率 gate）
- [ ] 9.2 RED：写 `test_gate_blocked_call_failed_on`：on 臂 call_failed>0 -> BLOCKED
- [ ] 9.3 RED：写 `test_gate_blocked_parser_rate_off`：off 臂 parser_rate<0.85 -> BLOCKED
- [ ] 9.4 RED：写 `test_gate_blocked_parser_rate_on`：on 臂 parser_rate<0.85 -> BLOCKED
- [ ] 9.5 RED：写 `test_gate_blocked_early_return_no_overwrite`：call_failed 命中后 verdict=BLOCKED，不被准确率 gate 覆盖
- [ ] 9.6 RED：写 `test_gate_paired_delta_denominator_n3`：paired_delta = sum(case_delta)/(N×3)
- [ ] 9.7 RED：写 `test_gate_promote`：paired_delta>=0.05 且 min_case_delta>=0 -> PROMOTE
- [ ] 9.8 RED：写 `test_gate_review_required`：paired_delta>=0.05 且 min_case_delta<0 -> REVIEW_REQUIRED
- [ ] 9.9 RED：写 `test_gate_non_inferior`：-0.02<=paired_delta<0.05 -> NON_INFERIOR
- [ ] 9.10 RED：写 `test_gate_rollback`：paired_delta<-0.02 -> ROLLBACK
- [ ] 9.11 GREEN：实现 `compute_6d_gate(details, n_cases)`：基础设施门早返回 + 准确率五分支
- [ ] 9.12 RED：写 fake-runner 端到端测试 `test_fake_runner_paired_e2e`：
  - 用 fake runner 生成 off+on details（与 6B2 fake runner 模式一致）
  - 调 `run_dev` 走完整 slice/merge/gate/report/archive/receipt 链
  - 验证 report.md 含 verdict
  - 验证 receipt 含 temporal 字段
  - 验证 archive 含 audit_index.json
- [ ] 9.13 RED：写 `test_fake_runner_no_network_calls`：monkeypatch 网络调用为"调用即失败"，证明 READY_FOR_SMOKE 阶段无真实 API 请求（fake runner 不触发网络层）
- [ ] 9.13a GREEN：实现 fake runner 集成测试夹具
- [ ] 9.14 GREEN：运行 `python -m pytest tests/test_phase6_6d_orchestrator.py -q`，全部通过
- [ ] 9.15 GREEN：运行全量回归：`$files = (Get-ChildItem tests -Filter 'test_phase6_*.py').FullName; python -m pytest $files tests/test_dual_system_reasoning.py tests/test_claude_api.py tests/test_bazi_time_context.py tests/test_phase6_6d_orchestrator.py tests/test_phase6_6d_offline_gate.py -q`，无新增失败
- [ ] 9.16 GREEN：输出阶段二启动命令（不执行）：
  ```powershell
  python scripts/phase6_6d_orchestrator.py run_dev --provider deepseek --model deepseek-v4-flash --output-dir docs/phase6/6d --run-id phase6-6d-v1-20260807-r1
  ```
- [ ] 9.17 GREEN：输出阶段二前置条件清单：
  - `DEEPSEEK_API_KEY` 可用
  - 2024+2025 数据集可读
  - `temporal_routed_cases.json` 已冻结（SHA 记录）
  - `temporal_context_version` 已冻结
  - fake-runner 端到端闭环通过
- [ ] 9.18 COMMIT：`feat(6d): complete gate + fake-runner e2e, READY_FOR_SMOKE`

**验证：** gate 五分支完备；BLOCKED 早返回不覆盖；fake runner 走完整 CLI/slice/merge/report/archive/receipt 链；状态=`READY_FOR_SMOKE`。

---

## 完成定义

6D v1 实施计划阶段的完成定义：

1. Task 1-9 全部完成
2. 全量回归无新增失败
3. `temporal_routed_cases.json` 冻结（N=31，SHA 记录）
4. `temporal_context_version` 冻结
5. gate 五分支完备 + BLOCKED 早返回
6. `time_context_injection` 全链路贯通（CLI -> Phase6Context -> prompt）
7. `RESUME_MANIFEST_FIELDS` 含 `time_context_injection`，off/on fail-closed
8. `_CODE_SCOPE` 含 `bazi_time_context.py`
9. `_REASONED_ARM_MAP` 含 `b1a_time_off` / `b1a_time_on`
10. orchestrator 完整可执行（`run_dev --help` 可用）
11. fake-runner 端到端闭环通过（slice/merge/gate/report/archive/receipt）
12. 真实 API 未启动（状态=`READY_FOR_SMOKE`）

阶段二真实 paired dev 需用户明确批准后启动，不在本计划范围内。
