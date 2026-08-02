# Phase 6 6B2 - 双管线 + source_label_blinded_judge：实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 6B2 双体系（八字+紫微）独立推理管线 + 来源标签盲化裁判，并在 2024/2025 dev gate 判定是否优于同期 B1-a′ 单管线基线。

**Architecture:** runner 级多调用方法 `dual_system`（仿 `run_multi_turn_benchmark` 委托模式）：每 case 依次调用八字管线、紫微管线，分歧时调 judge；三条 detail 行用 `attempt_stage` ∈ {bazi, ziwei, judge} 区分，通过运行期变更 `ctx.attempt_stage` 实现。编排器复用 6B1D 的 BudgetLedger / OutputDirLock / slice 状态机，新增双臂（b1a_prime 控制 + dual 处理）交错调度与多 stage 完整性门禁。

**Tech Stack:** Python 3.11+, subprocess 编排, pytest TDD

**父设计:** `docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md` §7（APPROVED）
**前置结论:** 6B1 PROMOTE_CANDIDATE（Δ_dev=+7.08pp）；6B1D 测得八字-紫微分歧率 60.8%（repeat-aligned, b1a′ vs b1b），用于修正 judge 预算
**阻塞语义:** 6B1 有信号 -> 6B2 实施；6B2 dev gate 未过 -> 双管线弃用

---

## 关键设计假设（AGENTS.md §6）

1. **runner 级多调用**：spec §7.2 的 `--method dual_system` + `dual_system_reasoning.py`（formatter）指示 judge 编排在 runner 内完成（仿 multi_turn 委托），而非编排器级多阶段 subprocess。理由：judge 依赖 bazi/ziwei 的实时理由文本，跨 subprocess 传递会破坏同期交错。
2. **管线定义**：八字管线 = `render_reasoned_context(ziwei_arm="none")`（与 6B1 b1a′ 字节等价）；紫微管线 = `render_reasoned_context(ziwei_arm="only")`（与 6B1 b1b 字节等价）。不使用 6B1D 的 b2b/b2c。
3. **同期 B1-a′ 控制臂**：`attempt_stage="main"`、`arm="b1a_prime"`、reasoned direct_choice，同年同 run 交错执行。不用 6B1 旧 run（provider drift）。
4. **judge 预算**：6B1D 分歧率 60.8% 修正 judge scheduled 估算；per-slice hard_cap 按最坏（8 case 全分歧=24）+2 retry=26，全局 hard_cap=1060（spec §8 冻结）为回退。

---

## 文件结构

**新建：**
- `benchmark/formatters/dual_system_reasoning.py` - judge prompt + 双管线 prompt 组装 + judge 答案提取
- `tests/test_dual_system_reasoning.py` - spec §7.2 测试矩阵
- `scripts/phase6_6b2_orchestrator.py` - 调度 / BudgetLedger / slice 执行 / 完整性门禁 / gate / 报告 / 归档

**修改：**
- `benchmark/runners/run_benchmark.py` - `--method dual_system`；`run_model_benchmark` 委托；`run_dual_system_benchmark()` 新函数；答案提取；可见性门禁；attempt_stage 校验
- `benchmark/runners/profiles.py` - `baziqa_xjz_dual` profile；`_FORMATTER_MAP`；`visibility_requirements` judge 规则；`prompt_fingerprint` dual 分支；`derive_method`

---

## 预算与调度（冻结）

- 2 臂 × 5 组 × 8 题 × 2 年 × 3 repeat；每 cell 10 slices 交错（b1a-G0, dual-G0, b1a-G1, dual-G1...）
- 总 slices = 60；b1a slice scheduled=8 hard_cap=10；dual slice scheduled=16 hard_cap=26
- 全局 hard_cap = **1060**（spec §8）；ledger 只对在途 slice 保留剩余额度（6B1D 公式复用）
- gate（dev, §7.3，三者全满足）：`Δ_dev(dual vs b1a) ≥ +4pp` **且** `dual 合并准确率 ≥ 32.5%` **且** `min(Δ_2024, Δ_2025) ≥ -2pp`
- dual 准确率：共识=bazi==ziwei；分歧=judge 裁决；单侧 unresolved 仍调 judge；双侧 unresolved 计错不调 judge；judge 失败计错

---

## Task 1: dual_system_reasoning.py - judge prompt + 管线 prompt

**Files:** Create `benchmark/formatters/dual_system_reasoning.py`; Test `tests/test_dual_system_reasoning.py`

- [ ] **Step 1: 写失败测试 - 双管线 prompt 字节等价 6B1**

```python
def test_bazi_pipeline_prompt_byte_equal_to_6b1_b1a():
    from benchmark.formatters.dual_system_reasoning import build_bazi_pipeline_prompt
    from benchmark.formatters.chart_context import render_reasoned_context
    from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt
    case = {"case_id":"Q1","question":"q","options":["a","b","c","d"],"answer":"A",
            "chart_input":{"ziwei":{"twelve_palaces":[],"si_hua":{}}},
            "person":{"name":"t","birth":{"place":"x"}},"four_pillars":"戊子 甲子 丙寅 戊子"}
    expected = _assemble_reasoned_choice_prompt(case, render_reasoned_context(case,"legacy_v0","none"))
    assert build_bazi_pipeline_prompt(case) == expected
```

- [ ] **Step 2: 运行确认失败** - `pytest tests/test_dual_system_reasoning.py::test_bazi_pipeline_prompt_byte_equal_to_6b1_b1a -v` -> ImportError

- [ ] **Step 3: 实现管线 prompt + judge prompt + extractor**

```python
# benchmark/formatters/dual_system_reasoning.py
from __future__ import annotations
from benchmark.formatters.chart_context import render_reasoned_context, extract_reasoned_choice_answer
from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt, format_options

JUDGE_TEMPLATE_VERSION = "dual_judge_v1"

def build_bazi_pipeline_prompt(case):
    return _assemble_reasoned_choice_prompt(case, render_reasoned_context(case,"legacy_v0","none"))

def build_ziwei_pipeline_prompt(case):
    return _assemble_reasoned_choice_prompt(case, render_reasoned_context(case,"legacy_v0","only"))

def build_judge_prompt(case, ans1, rationale1, ans2, rationale2, swap=False):
    a1,r1,a2,r2 = ans1,rationale1,ans2,rationale2
    if swap: a1,r1,a2,r2 = a2,r2,a1,r1
    return "\n\n".join([
        "你是一位命理评测裁判。下面有两个独立分析对同一道四选一题给出的结论与理由。",
        "请综合两者的推理，选出你认为最合理的选项。",
        "## 问题", case.get("question",""),
        "## 选项", format_options(case.get("options",[])),
        "## 分析一", f"结论：{a1}", f"理由：{r1}",
        "## 分析二", f"结论：{a2}", f"理由：{r2}",
        "## 输出要求\n请先简要说明你的裁决依据，然后给出最终答案。最后一行必须严格为：\n最终答案：X\n其中 X 为 A、B、C 或 D 之一。",
    ])

def extract_judge_answer(raw):
    return extract_reasoned_choice_answer(raw)
```

- [ ] **Step 4: 写测试 - judge 盲化 + 顺序交换 + extractor**（断言：judge prompt 不含"八字"/"紫微"；swap 改变分析一结论；extract_judge_answer 复用 reasoned 语义）
- [ ] **Step 5: 运行全文件通过** - `pytest tests/test_dual_system_reasoning.py -v`
- [ ] **Step 6: Commit** - `feat(6b2): add dual_system_reasoning formatter (pipeline + judge prompts)`

---

## Task 2: baziqa_xjz_dual profile + _FORMATTER_MAP + derive_method

**Files:** Modify `benchmark/runners/profiles.py:21-35,59-65,54-56`; Test `tests/test_phase6_profiles.py`

- [ ] **Step 1: 写失败测试** - resolve_profile("baziqa_xjz_dual") 存在；derive_method=="dual_system"；derive_formatter=="format_dual_system_prompt"
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** - profile 列表加 `EvalProfile("baziqa_xjz_dual","baziqa","xjz_dual","direct","legacy_v0","baziqa_macro")`；_FORMATTER_MAP 加 `("baziqa","xjz_dual","direct"):"format_dual_system_prompt"`；derive_method 加 `if profile.prompt_style=="xjz_dual": return "dual_system"`
- [ ] **Step 4: 运行通过 + 回归** - `pytest tests/test_phase6_profiles.py -q`
- [ ] **Step 5: Commit** - `feat(6b2): add baziqa_xjz_dual profile + formatter map + derive_method`

---

## Task 3: visibility_requirements - judge arm 规则

**Files:** Modify `benchmark/runners/profiles.py:99-141`; Test `tests/test_phase6_profiles.py`

judge prompt 不含体系段标，required=frozenset()，forbidden=全部体系段标+denylist。

- [ ] **Step 1: 写失败测试** - `visibility_requirements(p,"legacy_v0",ziwei_arm="judge")` required 空、forbidden 含 `【紫微斗数·本命】` 和 `【四柱】`；未知 arm -> NotImplementedError
- [ ] **Step 2: 运行确认失败**（当前 raise NotImplementedError: Unknown ziwei_arm: 'judge'）
- [ ] **Step 3: 实现** - ziwei_arm 分支链末尾 raise 前加：`if ziwei_arm=="judge": return frozenset(), _APPROVED_BAZI_MARKERS | _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS`
- [ ] **Step 4: 运行通过 + 回归**
- [ ] **Step 5: Commit** - `feat(6b2): add judge arm visibility rules (no system markers)`

---

## Task 4: prompt_fingerprint - dual 分支

**Files:** Modify `benchmark/runners/profiles.py:204-215`; Test `tests/test_phase6_profiles.py`

不加会落入 else（multi_turn）分支，指纹错误（6B1 曾有此 bug）。

- [ ] **Step 1: 写失败测试** - dual 指纹生成不报错；dual 指纹 != reasoned 指纹
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** - reasoned 分支后加 `elif formatter=="format_dual_system_prompt":` 含 `JUDGE_TEMPLATE_VERSION` + `build_bazi_pipeline_prompt`/`build_ziwei_pipeline_prompt`/`build_judge_prompt`/`extract_judge_answer` 源码
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): add dual_system prompt fingerprint branch`

---

## Task 5: build_benchmark_prompt - dual formatter 路由

**Files:** Modify `benchmark/runners/run_benchmark.py:434`; Test `tests/test_phase6_run_benchmark.py`

- [ ] **Step 1: 写失败测试** - `build_benchmark_prompt(case, profile_formatter="format_dual_system_prompt")` 返回 str
- [ ] **Step 2: 运行确认失败**（落入 raise ValueError）
- [ ] **Step 3: 实现** - reasoned 分支后加 `if profile_formatter=='format_dual_system_prompt': from benchmark.formatters.dual_system_reasoning import build_bazi_pipeline_prompt; return build_bazi_pipeline_prompt(case)`
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): add dual_system formatter dispatch in build_benchmark_prompt`

---

## Task 6: run_dual_system_benchmark - 核心多调用逻辑

**Files:** Modify `benchmark/runners/run_benchmark.py`（新增函数，约 line 1331 旁）; Test `tests/test_dual_system_reasoning.py`

核心：每 case 依次 bazi(stage=bazi)->ziwei(stage=ziwei)->分歧时 judge(stage=judge)。通过变更 `ctx.attempt_stage` 实现正确 attempt_key（enrich_row 从 ctx.attempt_stage 读 stage）。

- [ ] **Step 1: 写失败测试 - 共识不调 judge**

```python
def test_dual_consensus_no_judge_call(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    monkeypatch.setattr(rb, "call_model_sync",
        lambda p,pr,m,**k: ("最终答案：A", {"finish_reason":"stop"}))
    # 构造 _PHASE6_CTX，跑 1 case，断言 2 次调用、final="A"、无 judge detail 行
```

- [ ] **Step 2: 运行确认失败**（函数不存在）

- [ ] **Step 3: 实现 run_dual_system_benchmark + 辅助函数**

```python
def run_dual_system_benchmark(cases, provider, model, max_cases=20, temperature=0.0,
        case_details_jsonl=None, chart_schema_version=None, resume_append=False):
    from benchmark.formatters.dual_system_reasoning import (
        build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt,
        build_judge_prompt, extract_judge_answer)
    from benchmark.formatters.chart_context import extract_reasoned_choice_answer
    ctx = _PHASE6_CTX
    if not resume_append: _prepare_jsonl(case_details_jsonl)
    predictions = {}
    for case in cases[:max_cases]:
        cid = case["case_id"]
        ctx.attempt_stage = "bazi"
        b_raw, b_meta = _dual_call(ctx.attempt_key_for(case), build_bazi_pipeline_prompt(case), provider, model, case, temperature)
        b_ans = extract_reasoned_choice_answer(b_raw)
        _dual_write_detail(case, b_raw, b_ans, b_meta, cid)
        ctx.attempt_stage = "ziwei"
        z_raw, z_meta = _dual_call(ctx.attempt_key_for(case), build_ziwei_pipeline_prompt(case), provider, model, case, temperature)
        z_ans = extract_reasoned_choice_answer(z_raw)
        _dual_write_detail(case, z_raw, z_ans, z_meta, cid)
        final, j_raw, j_meta = _resolve_judge(case, b_ans, b_raw, z_ans, z_raw, provider, model, temperature)
        if j_raw is not None:
            ctx.attempt_stage = "judge"
            _dual_write_detail(case, j_raw, final, j_meta, cid)
        predictions[cid] = final
    ctx.attempt_stage = "main"
    return {"predictions": predictions, "case_details": [], "failed_cases": []}
```

辅助 `_dual_call`（before_call + call_model_sync + record_call_meta）、`_dual_write_detail`（写 detail 行，expected/correct 计算）、`_resolve_judge`（共识/分歧/双侧 unresolved 逻辑 + `_judge_swap_seed` 确定性顺序交换）。完整代码见 spec §7.1 语义。

- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 写测试 - 分歧调 judge、双侧 unresolved 不调、attempt_key stage 分离**

```python
def test_dual_disagreement_calls_judge(monkeypatch, tmp_path):
    # bazi=A ziwei=B judge=C -> 3 次调用，final="C"，judge detail 行存在
def test_dual_both_unresolved_no_judge(monkeypatch, tmp_path):
    # bazi=None ziwei=None -> 2 次调用，final=None
def test_dual_attempt_keys_distinct_stages(tmp_path):
    # 触发 judge，读 detail，attempt_key[3] 含 {bazi,ziwei,judge}
```

- [ ] **Step 6: 运行通过**
- [ ] **Step 7: Commit** - `feat(6b2): implement run_dual_system_benchmark (bazi->ziwei->judge multi-call)`

---

## Task 7: run_model_benchmark 委托 + --method choices

**Files:** Modify `benchmark/runners/run_benchmark.py:780,1535`; Test `tests/test_phase6_run_benchmark.py`

- [ ] **Step 1: 写失败测试** - method="dual_system" 时委托 run_dual_system_benchmark
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** - line 780 后加 `if method=='dual_system': return run_dual_system_benchmark(...)`；--method choices 加 `'dual_system'`
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): wire dual_system method delegation + CLI choice`

---

## Task 8: _phase6_visibility_filter - dual gate

**Files:** Modify `benchmark/runners/run_benchmark.py:1476`; Test `tests/test_phase6_run_benchmark.py`

dual gate 拼接 bazi+ziwei+judge 三段 gate_text，用 `ziwei_arm="judge"` 规则一次性检查（judge 规则 forbidden 含全部体系段标，能捕获任一 stage 串扰）。

- [ ] **Step 1: 写失败测试** - dual formatter 走新分支，干净 case 通过，串扰 case 拦截
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** - reasoned 分支后加 `elif profile_formatter=='format_dual_system_prompt':` 拼接三段 gate_text，assert_visibility 用 ziwei_arm="judge"
- [ ] **Step 4: 运行通过 + 回归** - `pytest tests/test_phase6_run_benchmark.py -k visibility -q`
- [ ] **Step 5: Commit** - `feat(6b2): dual_system visibility gate (3-stage marker check)`

---

## Task 9: attempt_stage 校验

**Files:** Modify `benchmark/runners/run_benchmark.py:1551`; Test `tests/test_phase6_run_benchmark.py`

- [ ] **Step 1: 写失败测试** - `--attempt-stage bogus` 非零退出
- [ ] **Step 2: 运行确认失败**（当前接受任意值）
- [ ] **Step 3: 实现** - `--attempt-stage` 加 `choices=list(ATTEMPT_STAGES)+["dual"]`（"dual" 为 dual_system slice 的 manifest 标签）
- [ ] **Step 4: 运行通过 + 回归** - `pytest tests/test_phase6_resume.py -q`
- [ ] **Step 5: Commit** - `feat(6b2): validate attempt_stage against ATTEMPT_STAGES`

---

## Task 10: 6B2 编排器 - 常量 + 调度

**Files:** Create `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

复用 6B1D 的 OutputDirLock、BudgetLedger、atomic_write_json、_count_call_attempts（import）。

- [ ] **Step 1: 写失败测试** - `_build_schedule` 生成 60 slices；arms={b1a_prime,dual}；每 cell 10 slices；slice_id 含年度；交错 b1a 在 dual 前
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现常量 + _build_schedule**

```python
ARM_METHOD = {"b1a_prime":"direct_choice", "dual":"dual_system"}
ARM_PROFILE = {"b1a_prime":"baziqa_xjz_reasoned", "dual":"baziqa_xjz_dual"}
ARM_ZIWEI = {"b1a_prime":"none", "dual":"combined"}
ARM_STAGE = {"b1a_prime":"main", "dual":"dual"}
B1A_SLICE_HARD_CAP=10; DUAL_SLICE_HARD_CAP=26; GLOBAL_HARD_CAP=1060
B1A_SLICE_SCHEDULED=8; DUAL_SLICE_SCHEDULED=16; JUDGE_DISAGREEMENT_RATE=0.608
```

`_build_schedule(output_dir, years)`: 2 arms × 5 groups × 2 years × 3 repeats = 60 slices，按 (year,repeat,group,arm_order) 排序实现交错。

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): orchestrator constants + 60-slice interleaved schedule`

---

## Task 11: 编排器 - BudgetLedger + slice 执行 + cmd builder

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写失败测试** - b1a cmd 用 reasoned+direct_choice+main；dual cmd 用 dual profile+dual_system+dual stage；BudgetLedger global cap=1060
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 _build_runner_cmd + _run_slice + _process_slice** - cmd 按 ARM_METHOD/ARM_PROFILE/ARM_STAGE 分发；_run_slice 复用 6B1D subprocess 模式 + ledger 记账；_process_slice 复用 6B1D 状态机（_resolve_slice_state -> budget 检查 -> _run_slice -> _verify_slice_completed）
- [ ] **Step 4: 运行通过**（注：若 6B1D BudgetLedger 构造不接 hard_cap 参数，适配为 6B2 版本或传 GLOBAL_HARD_CAP）
- [ ] **Step 5: Commit** - `feat(6b2): BudgetLedger + slice execution + arm-aware cmd builder`

---

## Task 12: 编排器 - 完整性门禁（多 stage expected keys）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

dual 每 case 2-3 行（bazi+ziwei+可选 judge）。expected 仅含 bazi+ziwei；judge 行为合法 extra。

- [ ] **Step 1: 写失败测试** - b1a 每 case 1 main 行；dual expected 含 bazi+ziwei 不含 judge；judge 行合法 extra；缺 bazi 行 -> MISSING；重复 key -> DUPLICATE
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 _expected_keys_for_slice + _integrity_gate** - b1a: 1 key/case stage=main；dual: 2 keys/case stage=bazi/ziwei；observed-expected 中 judge 行合法，非 judge extra 失败；terminal_state 合法性检查
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): multi-stage integrity gate (bazi/ziwei/judge expected keys)`

---

## Task 13: 编排器 - gate 计算 + 报告 + 归档

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写失败测试** - gate 三条件：全满足 PROMOTE；dual_acc<32.5% ROLLBACK；min_year<-2pp ROLLBACK；Δ_dev<+4pp ROLLBACK
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 compute_gate + generate_report + generate_archive**

```python
def compute_gate(merged_details):
    # dual final = 共识或 judge 裁决（同 case 的 bazi/ziwei/judge 行聚合）
    # Δ(year,repeat) = acc_dual - acc_b1a; Δ_year=mean(3); Δ_dev=mean(2 years)
    # gate: Δ_dev>=0.04 and dual_merged_acc>=0.325 and min(Δ_year)>=-0.02
```

generate_report 含：准确率表、Δ 表、gate 裁决、judge 触发率、parser rate、完整性、预算。generate_archive 复用 6B1D 模式（merged_details + audit_index + report.md）。

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): gate computation + report + archive`

---

## Task 14: smoke gate + 集成测试

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写测试 - smoke gate** - 数据完整性（ziwei 覆盖）、parser rate≥95%、五状态机（复用 6B1D）、退出码保护
- [ ] **Step 2: 实现 smoke gate** - 复用 6B1D `determine_smoke_state`/`verify_smoke_completed`，smoke slice 取 schedule[0]（b1a_prime，单调用）；dual smoke 单独验证 bazi+ziwei+judge 链路
- [ ] **Step 3: 写集成测试** - mock call_model_sync，跑 2 case 全流程（1 共识 + 1 分歧），断言 detail 行数、attempt_key、gate 计算
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): smoke gate + integration test`

---

## Task 15: 复用验证 + 2023 终验支持

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

编排器支持 `--years 2021 2022`（复用验证 gate: 各 Δ_year≥+2pp）和 `--years 2023`（终验: Δ2023≥0 CONFIRMED_PROMOTE）。

- [ ] **Step 1: 写测试** - `--years 2021 2022` 生成 60 slices（2年×3repeat×10slice）；gate 用复用验证阈值；`--years 2023` 用终验阈值
- [ ] **Step 2: 实现** - _build_schedule 接 years 参数；compute_gate 按 years 集合选阈值
- [ ] **Step 3: 运行通过**
- [ ] **Step 4: Commit** - `feat(6b2): support reuse-validation (2021/2022) + 2023 final gate`

---

## 自审清单

- [ ] spec §7.1 裁决语义（先解析后裁决、judge 仅分歧、盲法边界、unresolved 处理）-> Task 6 `_resolve_judge`
- [ ] spec §7.2 落点（dual_system_reasoning.py、--method dual_system、test_dual_system_reasoning.py）-> Task 1,7
- [ ] spec §7.3 同期控制（contemporaneous B1-a′、B1-c advisory、dev gate 三条件、复用验证）-> Task 10,13,15
- [ ] spec §7.4 2023 终验 -> Task 15
- [ ] spec §7.5 预算（judge 量由 6B1D 分歧率修正）-> Task 10 常量 JUDGE_DISAGREEMENT_RATE
- [ ] spec §4.4.2 双列预算 + BLOCKED_INCOMPLETE -> Task 11 复用 6B1D ledger
- [ ] spec §7.2 测试矩阵（共识直取、分歧裁决、顺序交换、双侧 unresolved、judge 失败计错、attempt key 分 stage 无碰撞）-> Task 6
