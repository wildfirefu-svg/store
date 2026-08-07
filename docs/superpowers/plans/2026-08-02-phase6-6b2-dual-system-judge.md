# Phase 6 6B2 - 双管线 + source_label_blinded_judge：实施计划 (v18)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v14 → v15（第六轮审核 5 P0 + 6 中优修订）：**
> ① smoke 预算单源化——slice 自带冻结 `hard_cap`/`max_cases`/`scheduled_calls`（smoke=10/2/6，b1a=10/8/8，dual=26/8/24），`_build_runner_cmd` 与 `_slice_runner_args` 只读 slice 字段；② `record_slice_completed` 非 b1a/dual 臂（smoke）走构造 `slice_min/slice_max` 范围 + 边界测试（1/10 过、0/11 拒）；③ receipt 指纹修正——`_git_head()`（未定义）→ `_compute_experiment_code_fingerprint()` 且与 audit_index 精确比对；audit_index 缺失即拒绝发布（fail-closed）；smoke 账本按原构造参数加载；④ `check_stage_gate` 字段级强化（必需字段/stage/archive 存在/audit SHA/交叉指纹/provider/model/当前代码指纹 7 项）+ `TestGateReceipt` 真实最小 audit_index 测试（非 mock）；⑤ `_smoke_integrity` judge 按分歧基数校验（共识/双 unresolved→0、分歧/单侧→恰 1、未知 stage 拒绝）；⑥ 中优——partial resume 按剩余量预占（hard_cap − 已有 attempts）、`TestDualIntegration` finally 复位 ctx、`generate_archive` 补 dataset_paths、新增 `test_smoke_homology`、`_ns_from_argv` 提为模块级测试辅助。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v13 → v14（第五轮审核 4 P0 + 4 中优修订）：**
> ① `_run_slice` 完整重写落入 Task 11——`integrity="smoke"` 参数真实入签名；smoke 分支：小预算（SMOKE_HARD_CAP）、manifest 路径按 detail_path 推导（detail.jsonl→detail.manifest.json）、`_smoke_integrity` 自有完整性（不经 8 题门禁）、record 走构造范围；新增 partial resume 三态检测（runner 三件套存在但无 slice_status.json → 自动 --resume）；② gate receipt 顺序与指纹——compute_gate → report → archive 自验 → **原子发布 receipt**（verdict/stage/archive_dir/audit_index_sha256/provider/model/code_fingerprint/dataset_sha256/smoke_attempted）；run 隔离布局 `exp_root/{gates,archive,runs/<run_id>}`（--run-id 真正使用，dev/reuse 账本不再共享）；③ 测试修复——homology 测试先建 slice 目录 + `_ns_from_argv` 补 sample_temperature/n_samples 默认值；reuse 链 mock 的 setdefault 返回值 bug 改显式 dict；`_build_runner_cmd` 写 case_ids.json 前 makedirs；④ 中优——SMOKE_SCHEDULED 8→6（最坏 2×3）、smoke 账本并入 receipt 审计字段、TestDualIntegration finally 复位 `_PHASE6_CTX`、generate_archive 调用补 `dataset_paths`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v12 → v13（第四轮审核 5 P0 修订）：**
> ① 执行链闭合——`run_reuse` 先过 `check_stage_gate("reuse")`（dev 准入）；dev/reuse 原子落盘 `{stage}_gate.json`（2023 准入依赖）；链尾调用 `generate_archive()`；`main()` 的 final-2023 调用改对齐真实签名 `run_2023_final(provider, model, gate_root, archive_root)`；② smoke 真实实现——`_smoke_case_ids`/`_run_smoke_slice` 完整代码（独立小账本 scheduled 6/cap 10、预算可审计、`_run_slice` 加 `integrity="smoke"` 分支绕开 8 题门禁与 dual 16 次下限）；③ smoke 状态机与 parser 门禁——`determine_smoke_state` 需每题 bazi+ziwei 齐全才判 completed；任何 call_failed 即拒且不计入 parser 成功率；④ `_accuracy_final` 聚合键加 year（attempt_key[0] 数据集名提取），judge 触发率分母同步；⑤ 测试修正——dev 链 mock 补 `global_hard_cap` 与新链 mock（archive/gate 文件/准入）、`TestDualIntegration` 先 `init_phase6_context`、新增 `TestManifestHomology`（cmd argv 与 `_slice_runner_args` 两路 manifest 完全相等）。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v11 → v12（第三轮审核 4 P0 + 4 中优修订）：**
> ① manifest 重建改与 `_build_runner_cmd` 同源冻结配置（`_slice_runner_args(slice_info, provider, model)`：per-arm profile/method/ziwei_arm、`repeat`→`repeat_idx`、`case_ids_file`、per-arm hard_cap、FROZEN_DATE/SCHEMA）+ 真实 `resolve_profile` 对象 + 直接调 `check_resume_manifest`（不再传 None、不自写字段循环）；schedule slice dict 同步改 per-arm profile/method + 补 `case_ids_file`；② Task 14 全修：`self._write_smoke`→模块调用、补 `_mk_case`、fake 输出 reasoned 格式（`最终答案：X`）、stage 明细改读落盘 detail.jsonl、预期计数 8→7；③ `generate_report`：`ledger.total_attempted`（int 属性）+ `_accuracy_final` 按 compute_gate 同口径取 dual 最终答案（不再按 stage 行计数）；④ 新增 Task 17b `run_dev`/`run_reuse`/`main` CLI 执行链（smoke→schedule→ledger→integrity→gate→report）；⑤ 删除 Task 9 重复测试名、Task 16 `_sha256_file` 去重、完整性门禁 dual 分支补逐行终态校验。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v10 → v11（第二轮审核 6 P0 + 4 遗留项修订，见 `2026-08-02-phase6-6b2-dual-system-judge-review.md` 第二轮）：**
> ① B1-a′/dual 门禁 stage 统一改从 `attempt_key[3]` 解析（真实 detail 行无顶层 `dual_stage`）；② B1-a′ 合法终态恢复全集（parsed/invalid/unresolved/judge_unresolved/call_failed）；③ 完成态 resume 改为用当前配置重建 manifest 并逐字段比对（不再只比 SHA）；④ Task 9 resume 测试修正 manifest 文件名/完整字段/合法 dataset；⑤ `record_slice_completed` 携带臂上下文；⑥ Task 14 补全为完整 TDD 任务；⑦ judge 分歧率 0.608（无源）→ 实测 0.579（139/240，6B1 merged_details b1a′↔b1b）；⑧ `:2000` 浮点精确比较 → `pytest.approx`；⑨ `generate_report` 补接口/实现/测试；⑩ `_load_events`/`_sha256_file` 定义前移至 Task 11。

**Goal:** 实现 6B2 双体系（八字+紫微）独立推理管线 + 来源标签盲化裁判，在 2024/2025 dev gate 判定是否优于同期 B1-a′ 单管线基线。

**Architecture:** runner 级多调用方法 `dual_system`（仿 `run_multi_turn_benchmark` 委托）。每 case 依次 bazi(stage=bazi)->ziwei(stage=ziwei)->分歧时 judge(stage=judge)。stage 在调用前切换。复用 `_attempt_with_ledger` 账本（不重复记账）。编排器复用 6B1D 的 OutputDirLock / slice 状态机，BudgetLedger 参数化（global=1060, slice 范围 8-26）。

**Tech Stack:** Python 3.11+, subprocess 编排, pytest TDD

**父设计:** `docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md` §7（APPROVED）

---

## 关键设计假设（AGENTS.md §6）

1. **runner 级多调用**：`call_model_sync` 在 Phase6 context 下已内含 `before_call`/重试/`record_call_meta`/hard_cap（`_attempt_with_ledger`，run_benchmark.py:370），返回 `str`。`_call_dual_stage` 只设 stage + 调 `call_model_sync`，不重复调账本方法。
2. **管线定义**：八字 = `render_reasoned_context(ziwei_arm="none")`（字节等价 6B1 b1a′）；紫微 = `render_reasoned_context(ziwei_arm="only")`（字节等价 6B1 b1b）。
3. **同期 B1-a′ 控制**：`attempt_stage="main"`、`arm="b1a_prime"`、reasoned direct_choice，同年同 run 交错。
4. **预算冻结**：dual scheduled=24（8 bazi + 8 ziwei + 8 judge 最坏）；b1a scheduled=8；总 scheduled=960（240+720）；global hard_cap=1060。
5. **swap seed**：SHA-256(dataset+case_id+repeat) 确定性，不用 Python `hash()`。
6. **B1-c advisory 冻结路径**：`docs/phase6/6b1/6b1-2026-07-17-deepseek-deepseek-chat-78481de6/merged_details.jsonl`（已验证唯一存在）。

---

## 文件结构

**新建：**
- `benchmark/formatters/dual_system_reasoning.py` - judge prompt + 双管线 prompt + extractor + swap seed
- `tests/test_dual_system_reasoning.py` - dual formatter + runner 测试矩阵
- `tests/test_phase6_6b2.py` - 编排器测试
- `scripts/phase6_6b2_orchestrator.py` - 调度 / BudgetLedger / slice 执行 / 完整性门禁 / gate / 报告 / 归档
- `scripts/phase6_6b2_sealed_workflow.py` - enrichment + 阶段准入 + 2023 密封状态机

**修改：**
- `benchmark/runners/run_benchmark.py` - `--method dual_system`；委托；`run_dual_system_benchmark()`；可见性门禁；attempt_stage 校验；**主入口 dual resume 分支**
- `benchmark/runners/profiles.py` - `baziqa_xjz_dual` profile；`_FORMATTER_MAP`；judge 可见性；prompt 指纹；derive_method

---

## Task 1: dual_system_reasoning.py

**Files:** Create `benchmark/formatters/dual_system_reasoning.py`, `tests/test_dual_system_reasoning.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dual_system_reasoning.py
from benchmark.formatters.dual_system_reasoning import (
    build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt,
    build_judge_prompt, extract_judge_answer, judge_swap_seed, JUDGE_TEMPLATE_VERSION)
from benchmark.formatters.chart_context import render_reasoned_context
from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt

def _case():
    return {"case_id":"Q1","question":"q","options":["a","b","c","d"],"answer":"A",
            "chart_input":{"ziwei":{"twelve_palaces":[],"si_hua":{}}},
            "person":{"name":"t","birth":{"place":"x"}},"four_pillars":"戊子 甲子 丙寅 戊子"}

def test_bazi_prompt_byte_equal_6b1():
    c=_case()
    assert build_bazi_pipeline_prompt(c)==_assemble_reasoned_choice_prompt(c,render_reasoned_context(c,"legacy_v0","none"))

def test_ziwei_prompt_byte_equal_6b1():
    c=_case()
    assert build_ziwei_pipeline_prompt(c)==_assemble_reasoned_choice_prompt(c,render_reasoned_context(c,"legacy_v0","only"))

def test_judge_template_no_added_source_labels():
    c=_case()
    p=build_judge_prompt(c,"A","r","B","r",swap=False)
    header=p[:p.index("## 分析一")]
    assert "分析一" in p and "分析二" in p
    assert "八字" not in header and "紫微" not in header

def test_swap_reorders():
    c=_case()
    assert "分析一\n结论：A" in build_judge_prompt(c,"A","r","B","r",swap=False)
    assert "分析一\n结论：B" in build_judge_prompt(c,"A","r","B","r",swap=True)

def test_swap_seed_deterministic():
    assert judge_swap_seed("baziqa","Q1",0)==judge_swap_seed("baziqa","Q1",0)
    import hashlib
    expected = int(hashlib.sha256("baziqa|Q1|0".encode()).hexdigest(),16)%2==1
    assert judge_swap_seed("baziqa","Q1",0)==expected
```

- [ ] **Step 2: 运行确认失败** - `pytest tests/test_dual_system_reasoning.py -v` -> ImportError

- [ ] **Step 3: 实现**

```python
# benchmark/formatters/dual_system_reasoning.py
from __future__ import annotations
import hashlib
from benchmark.formatters.chart_context import render_reasoned_context, extract_reasoned_choice_answer
from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt, format_options

JUDGE_TEMPLATE_VERSION = "dual_judge_v1"

def build_bazi_pipeline_prompt(case):
    return _assemble_reasoned_choice_prompt(case, render_reasoned_context(case,"legacy_v0","none"))

def build_ziwei_pipeline_prompt(case):
    return _assemble_reasoned_choice_prompt(case, render_reasoned_context(case,"legacy_v0","only"))

def build_judge_prompt(case, ans1, rationale1, ans2, rationale2, swap=False):
    a1,r1,a2,r2=ans1,rationale1,ans2,rationale2
    if swap: a1,r1,a2,r2=a2,r2,a1,r1
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

def judge_swap_seed(dataset, case_id, repeat_idx):
    digest = hashlib.sha256(f"{dataset}|{case_id}|{repeat_idx}".encode()).hexdigest()
    return int(digest, 16) % 2 == 1
```

- [ ] **Step 4: 运行通过** - `pytest tests/test_dual_system_reasoning.py -v`
- [ ] **Step 5: Commit** - `feat(6b2): add dual_system_reasoning formatter (pipeline+judge+swap seed)`

---

## Task 2: baziqa_xjz_dual profile

**Files:** Modify `benchmark/runners/profiles.py:21-35,54-56,59-65`; Test `tests/test_phase6_profiles.py`

- [ ] **Step 1: 写失败测试** - `resolve_profile("baziqa_xjz_dual")` 存在；`derive_method`=="dual_system"；`derive_formatter`=="format_dual_system_prompt"
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** - profile 列表加 `EvalProfile("baziqa_xjz_dual","baziqa","xjz_dual","direct","legacy_v0","baziqa_macro")`；_FORMATTER_MAP 加 `("baziqa","xjz_dual","direct"):"format_dual_system_prompt"`；derive_method 加 `if profile.prompt_style=="xjz_dual": return "dual_system"`
- [ ] **Step 4: 运行通过 + 回归** - `pytest tests/test_phase6_profiles.py -q`
- [ ] **Step 5: Commit** - `feat(6b2): add baziqa_xjz_dual profile + formatter map + derive_method`

---

## Task 3: visibility_requirements judge arm

**Files:** Modify `benchmark/runners/profiles.py:140`; Test `tests/test_phase6_profiles.py`

- [ ] **Step 1: 写失败测试** - `visibility_requirements(p,"legacy_v0",ziwei_arm="judge")` required=frozenset()，forbidden 含全部体系段标
- [ ] **Step 2: 运行确认失败**（NotImplementedError: Unknown ziwei_arm: 'judge'）
- [ ] **Step 3: 实现** - raise 前加 `if ziwei_arm=="judge": return frozenset(), _APPROVED_BAZI_MARKERS | _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS`
- [ ] **Step 4: 运行通过 + 回归**
- [ ] **Step 5: Commit** - `feat(6b2): add judge arm visibility rules`

---

## Task 4: prompt_fingerprint dual 分支（P1-2 修订：扩大范围）

**Files:** Modify `benchmark/runners/profiles.py:204`; Test `tests/test_phase6_profiles.py`

指纹范围必须包含全部影响 prompt 字节的函数：`build_bazi/ziwei_pipeline_prompt`、`build_judge_prompt`、`extract_judge_answer`、`judge_swap_seed`、`render_reasoned_context`、`_assemble_reasoned_choice_prompt`、`extract_reasoned_choice_answer`、`format_options`。

- [ ] **Step 1: 写失败测试**

```python
def test_dual_fingerprint_includes_all_prompt_sources():
    import inspect
    from benchmark.runners.profiles import prompt_fingerprint, resolve_profile
    p = resolve_profile("baziqa_xjz_dual")
    fp = prompt_fingerprint(p)
    assert isinstance(fp, str) and len(fp) == 64
    fp2 = prompt_fingerprint(resolve_profile("baziqa_xjz_reasoned"))
    assert fp != fp2

def test_dual_fingerprint_source_scope():
    """指纹计算源码应含 judge_swap_seed 等全部函数。"""
    import inspect
    from benchmark.runners.profiles import prompt_fingerprint
    src = inspect.getsource(prompt_fingerprint)
    for fn in ("judge_swap_seed","build_judge_prompt","render_reasoned_context",
               "_assemble_reasoned_choice_prompt","extract_reasoned_choice_answer","format_options"):
        assert fn in src, f"fingerprint 缺少 {fn}"
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现** - reasoned 分支后加

```python
    elif formatter == "format_dual_system_prompt":
        from benchmark.formatters import dual_system_reasoning as ds
        from benchmark.formatters.chart_context import render_reasoned_context, extract_reasoned_choice_answer
        from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt, format_options
        parts += [
            ds.JUDGE_TEMPLATE_VERSION,
            inspect.getsource(ds.build_bazi_pipeline_prompt),
            inspect.getsource(ds.build_ziwei_pipeline_prompt),
            inspect.getsource(ds.build_judge_prompt),
            inspect.getsource(ds.extract_judge_answer),
            inspect.getsource(ds.judge_swap_seed),
            inspect.getsource(render_reasoned_context),
            inspect.getsource(_assemble_reasoned_choice_prompt),
            inspect.getsource(extract_reasoned_choice_answer),
            inspect.getsource(format_options),
        ]
```

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): dual_system prompt fingerprint (full source scope)`

---

## Task 5: build_benchmark_prompt dual 路由

**Files:** Modify `benchmark/runners/run_benchmark.py:434`; Test `tests/test_dual_system_reasoning.py`

- [ ] **Step 1: 写失败测试** - `build_benchmark_prompt(case, profile_formatter="format_dual_system_prompt")` 返回 str
- [ ] **Step 2: 运行确认失败**（raise ValueError）
- [ ] **Step 3: 实现** - reasoned 分支后加 `if profile_formatter=='format_dual_system_prompt': from benchmark.formatters.dual_system_reasoning import build_bazi_pipeline_prompt; return build_bazi_pipeline_prompt(case)`
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): dual_system formatter dispatch`

---

## Task 6: run_dual_system_benchmark（P0-2 修订：终态处理 + 修正 import）

**Files:** Modify `benchmark/runners/run_benchmark.py`; Test `tests/test_dual_system_reasoning.py`

**关键契约：**
- `_call_dual_stage` 只捕获 `model_call_failed`（RuntimeError 前缀），返回 `(raw, ans, failed)`；`_HardCapExhausted` 和崩溃异常冒泡
- bazi/ziwei 失败 -> `terminal_state="call_failed"`，该侧 ans=None，继续另一管线
- bazi/ziwei 解析失败 -> `terminal_state="invalid"`；judge 解析失败 -> `terminal_state="judge_unresolved"`
- `extract_choice` 已在 run_benchmark.py:12 顶层从 `benchmark.scorers.choice_accuracy` 导入，不重复局部 import
- `_dual_write_detail` 不重复调 `enrich_row`（`_append_jsonl` 在路径匹配时自动调，:712）
- 返回完整 dict：`cases/predictions/evidence_results/safety_results/case_details/failed_cases`
- `_HardCapExhausted` 冒泡到 main

- [ ] **Step 1: 写失败测试 - 共识不调 judge + 调用契约 + 返回结构**

```python
def test_dual_consensus_no_judge(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    calls = []
    monkeypatch.setattr(rb, "call_model_sync",
        lambda p,pr,m,**k: calls.append(p) or "最终答案：A")
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    result = rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    assert len(calls)==2
    assert result["predictions"]["Q1"]=="A"
    for k in ("cases","predictions","evidence_results","safety_results","case_details","failed_cases"):
        assert k in result
```

- [ ] **Step 2: 运行确认失败**（函数不存在）

- [ ] **Step 3: 实现 run_dual_system_benchmark（P0-1 修订：模块级 import）**

```python
# benchmark/runners/run_benchmark.py 顶部（与其他 formatter import 同区）
from benchmark.formatters.dual_system_reasoning import (
    build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt,
    build_judge_prompt, extract_judge_answer, judge_swap_seed)
from benchmark.formatters.chart_context import extract_reasoned_choice_answer


def run_dual_system_benchmark(cases, provider, model, max_cases=20, temperature=0.0,
        case_details_jsonl=None, chart_schema_version=None, resume_append=False,
        completed_keys=None):
    ctx = _PHASE6_CTX
    if not resume_append:
        _prepare_jsonl(case_details_jsonl)
    predictions, case_details, failed_cases, evidence_results, safety_results = {}, [], [], [], []
    for case in cases[:max_cases]:
        _run_dual_case(case, ctx, provider, model, temperature, completed_keys,
                       predictions, case_details, failed_cases)
    return {"cases": cases[:max_cases], "predictions": predictions,
            "evidence_results": evidence_results, "safety_results": safety_results,
            "case_details": case_details, "failed_cases": failed_cases}


def _call_dual_stage(ctx, case, provider, model, temperature, stage, prompt):
    """单 stage 调用。只捕获 model_call_failed；HardCapExhausted/崩溃冒泡。

    返回 (raw, ans, failed)。
    """
    prev = ctx.attempt_stage
    ctx.attempt_stage = stage
    try:
        raw = call_model_sync(prompt, provider, model, case=case, temperature=temperature)
        if stage == "judge":
            ans = extract_judge_answer(raw)
            if ans is None:
                _dual_write_detail(ctx, case, stage, raw, None, terminal_state="judge_unresolved")
            else:
                _dual_write_detail(ctx, case, stage, raw, ans)
        else:
            ans = extract_reasoned_choice_answer(raw)
            if ans is None:
                _dual_write_detail(ctx, case, stage, raw, None, terminal_state="invalid")
            else:
                _dual_write_detail(ctx, case, stage, raw, ans)
        return raw, ans, False
    except RuntimeError as exc:
        if not str(exc).startswith("model_call_failed"):
            raise
        _dual_write_detail(ctx, case, stage, "", None, terminal_state="call_failed")
        return "", None, True
    finally:
        ctx.attempt_stage = prev


def _run_dual_case(case, ctx, provider, model, temperature, completed_keys,
                   predictions, case_details, failed_cases):
    cid = case["case_id"]
    prev_stage = ctx.attempt_stage
    try:
        ctx.attempt_stage = "bazi"
        b_key = ctx.attempt_key_for(case)
        if completed_keys and tuple(b_key) in completed_keys:
            b_raw, b_ans = _load_existing_detail(ctx.detail_path, b_key)
        else:
            b_raw, b_ans, _ = _call_dual_stage(
                ctx, case, provider, model, temperature, "bazi", build_bazi_pipeline_prompt(case))

        ctx.attempt_stage = "ziwei"
        z_key = ctx.attempt_key_for(case)
        if completed_keys and tuple(z_key) in completed_keys:
            z_raw, z_ans = _load_existing_detail(ctx.detail_path, z_key)
        else:
            z_raw, z_ans, _ = _call_dual_stage(
                ctx, case, provider, model, temperature, "ziwei", build_ziwei_pipeline_prompt(case))

        final = _resolve_and_judge(ctx, case, provider, model, temperature,
                                   b_ans, b_raw, z_ans, z_raw, completed_keys, cid)
        predictions[cid] = final
        case_details.append({"case_id": cid, "predicted_answer": final,
                             "dual_stages": {"bazi": b_ans, "ziwei": z_ans, "final": final}})
        if final is None:
            failed_cases.append({"case_id": cid, "reason": "unresolved",
                                 "bazi_ans": b_ans, "ziwei_ans": z_ans})
    finally:
        ctx.attempt_stage = prev_stage


def _resolve_and_judge(ctx, case, provider, model, temperature,
                       b_ans, b_raw, z_ans, z_raw, completed_keys, cid):
    if b_ans is not None and z_ans is not None and b_ans == z_ans:
        return b_ans
    if b_ans is None and z_ans is None:
        return None
    prev = ctx.attempt_stage
    ctx.attempt_stage = "judge"
    j_key = ctx.attempt_key_for(case)
    if completed_keys and tuple(j_key) in completed_keys:
        ctx.attempt_stage = prev
        return _load_existing_detail(ctx.detail_path, j_key)[1]
    try:
        r1 = b_raw if b_raw else "未达成结论"
        r2 = z_raw if z_raw else "未达成结论"
        a1 = b_ans or "未给出"
        a2 = z_ans or "未给出"
        swap = judge_swap_seed(ctx.dataset_id, cid, ctx.repeat_idx)
        prompt = build_judge_prompt(case, a1, r1, a2, r2, swap=swap)
        j_raw, verdict, failed = _call_dual_stage(
            ctx, case, provider, model, temperature, "judge", prompt)
        return verdict
    finally:
        ctx.attempt_stage = prev


def _dual_write_detail(ctx, case, stage, raw, predicted, terminal_state=None):
    expected = extract_choice(case.get("answer"))
    row = {"case_id": case["case_id"], "predicted_answer": predicted,
           "raw_answer": raw, "expected_answer": expected,
           "correct": predicted == expected, "call_success": bool(raw),
           "dual_stage": stage, "parser_valid": predicted is not None,
           "sample_idx": 0, "permutation_id": case.get("_permutation_id") or "p0"}
    if terminal_state:
        row["terminal_state"] = terminal_state
    _append_jsonl(ctx.detail_path, row)


def _load_existing_detail(detail_path, key):
    if not detail_path or not os.path.exists(detail_path):
        return "", None
    target = list(key)
    with open(detail_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            row = json.loads(line)
            if row.get("attempt_key") == target:
                return row.get("raw_answer",""), row.get("predicted_answer")
    return "", None
```

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 写测试 - 分歧/judge 时序/双侧 unresolved/call_failed/judge_unresolved/HardCap**

```python
def test_dual_disagreement_calls_judge(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    seq = ["最终答案：A", "最终答案：B", "最终答案：C"]
    monkeypatch.setattr(rb, "call_model_sync", lambda *a, **k: seq.pop(0))
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    result = rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    assert result["predictions"]["Q1"]=="C"
    rows=[json.loads(l) for l in open(tmp_path/"d.jsonl",encoding="utf-8") if l.strip()]
    assert {r["attempt_key"][3] for r in rows}=={"bazi","ziwei","judge"}

def test_judge_stage_set_before_call(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    stages=[]
    def fc(*a,**k):
        stages.append(rb._PHASE6_CTX.attempt_stage)
        return ["最终答案：A","最终答案：B","最终答案：C"][len(stages)-1]
    monkeypatch.setattr(rb, "call_model_sync", fc)
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    assert stages == ["bazi","ziwei","judge"]

def test_bazi_call_failed_writes_call_failed_and_continues(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    seq = [RuntimeError("model_call_failed: timeout"), "最终答案：B", "最终答案：C"]
    def fc(*a,**k):
        v=seq.pop(0)
        if isinstance(v,Exception): raise v
        return v
    monkeypatch.setattr(rb, "call_model_sync", fc)
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    result = rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    rows=[json.loads(l) for l in open(tmp_path/"d.jsonl",encoding="utf-8") if l.strip()]
    bazi_row=[r for r in rows if r["attempt_key"][3]=="bazi"][0]
    assert bazi_row["terminal_state"]=="call_failed"
    assert result["predictions"]["Q1"]=="C"

def test_judge_parse_fail_writes_judge_unresolved(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    seq = ["最终答案：A", "最终答案：B", "裁决但无最终答案格式"]
    monkeypatch.setattr(rb, "call_model_sync", lambda *a,**k: seq.pop(0))
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    result = rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    rows=[json.loads(l) for l in open(tmp_path/"d.jsonl",encoding="utf-8") if l.strip()]
    judge_row=[r for r in rows if r["attempt_key"][3]=="judge"][0]
    assert judge_row["terminal_state"]=="judge_unresolved"
    assert result["predictions"]["Q1"] is None
    # P1: failed_cases 记录 unresolved
    assert len(result["failed_cases"])==1
    assert result["failed_cases"][0]["case_id"]=="Q1"

def test_hardcap_exhausted_propagates(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb, pytest
    monkeypatch.setattr(rb, "call_model_sync",
        lambda *a,**k: (_ for _ in ()).throw(rb._HardCapExhausted("x")))
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    with pytest.raises(rb._HardCapExhausted):
        rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
```

- [ ] **Step 6: 运行通过**
- [ ] **Step 7: Commit** - `feat(6b2): run_dual_system_benchmark (terminal states + correct import + no double enrich)`

---

## Task 7: stage-aware resume

**Files:** 已在 Task 6 实现 `_load_existing_detail` + `completed_keys`; Test `tests/test_dual_system_reasoning.py`

- [ ] **Step 1: 写测试 - bazi 完成/全完成/read raw_answer（完整代码见 Task 6 逻辑，此处给出精确断言测试）**

```python
def _write_detail_row(path, key, raw, ans, stage, state="parsed"):
    import json
    row = {"case_id": key[6], "predicted_answer": ans, "raw_answer": raw,
           "expected_answer": "A", "correct": ans=="A", "call_success": bool(raw),
           "dual_stage": stage, "parser_valid": ans is not None,
           "sample_idx": 0, "permutation_id": "p0", "terminal_state": state,
           "attempt_key": list(key)}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False)+"\n")

def test_resume_bazi_done_skips_to_ziwei(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    detail = str(tmp_path/"d.jsonl")
    ctx = rb.Phase6Context("ds","baziqa_xjz_dual","dual","dual","p","m",0,
        detail, str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    b_key = (ctx.dataset_id,ctx.profile_id,ctx.arm,"bazi",ctx.provider,ctx.model,"Q1",0,0,"p0")
    _write_detail_row(detail, b_key, "最终答案：A", "A", "bazi")
    calls=[]
    monkeypatch.setattr(rb, "call_model_sync", lambda *a,**k: calls.append(0) or "最终答案：A")
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=detail,
        resume_append=True, completed_keys={tuple(b_key)})
    assert len(calls)==1  # only ziwei (共识 A)

def test_resume_reads_raw_answer_for_judge(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    detail = str(tmp_path/"d.jsonl")
    ctx = rb.Phase6Context("ds","baziqa_xjz_dual","dual","dual","p","m",0,
        detail, str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    bk=list(ctx.attempt_key_for(_case())); bk[3]="bazi"
    zk=list(ctx.attempt_key_for(_case())); zk[3]="ziwei"
    _write_detail_row(detail, tuple(bk), "bazi理由xyz最终答案：A", "A", "bazi")
    _write_detail_row(detail, tuple(zk), "紫微理由最终答案：B", "B", "ziwei")
    captured=[]
    monkeypatch.setattr(rb, "call_model_sync", lambda p,*a,**k: captured.append(p) or "最终答案：C")
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=detail,
        resume_append=True, completed_keys={tuple(bk),tuple(zk)})
    assert len(captured)==1
    assert "bazi理由xyz" in captured[0] and "紫微理由" in captured[0]
```

- [ ] **Step 2: 运行确认通过**
- [ ] **Step 3: Commit** - `test(6b2): stage-aware resume (skip + raw_answer recovery)`

---

## Task 8: 可见性门禁 - 三段独立检查

**Files:** Modify `benchmark/runners/run_benchmark.py:1476`; Test `tests/test_dual_system_reasoning.py`

- [ ] **Step 1: 写失败测试**

```python
def test_dual_visibility_checks_each_stage_independently():
    from benchmark.runners.profiles import assert_visibility, resolve_profile
    from benchmark.formatters.dual_system_reasoning import build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt, build_judge_prompt
    p = resolve_profile("baziqa_xjz_dual")
    c = _case()
    assert assert_visibility(build_bazi_pipeline_prompt(c), p, "legacy_v0", ziwei_arm="none") == []
    assert assert_visibility(build_ziwei_pipeline_prompt(c), p, "legacy_v0", ziwei_arm="only") == []
    assert assert_visibility(build_judge_prompt(c, "A", "r", "B", "r"), p, "legacy_v0", ziwei_arm="judge") == []
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**

```python
        elif profile_formatter == 'format_dual_system_prompt':
            from benchmark.formatters.dual_system_reasoning import build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt, build_judge_prompt
            csv = profile.chart_schema_version
            violations = []
            violations += assert_visibility(build_bazi_pipeline_prompt(case), profile, csv, ziwei_arm="none")
            violations += assert_visibility(build_ziwei_pipeline_prompt(case), profile, csv, ziwei_arm="only")
            violations += assert_visibility(build_judge_prompt(case, "A", "r", "B", "r"), profile, csv, ziwei_arm="judge")
```

- [ ] **Step 4: 运行通过 + 回归** - `pytest tests/test_phase6_runner_routing.py tests/test_dual_system_reasoning.py -k visibility -q`
- [ ] **Step 5: Commit** - `feat(6b2): 3-stage independent visibility gate`

---

## Task 9: runner 委托 + CLI + 主入口 dual resume（P0-1 修订）

**Files:** Modify `benchmark/runners/run_benchmark.py:780,1535,1551,1697-1703`; Test `tests/test_phase6_runner_routing.py`

**P0-1：** main() resume（:1697-1703）当前只在 emit_samples 传 completed_keys，否则 case 级预过滤。dual stage=bazi/ziwei/judge 与初始 "dual" 不匹配 -> 预过滤永不命中 -> 全部重调。dual_system 必须走 completed_keys 路径。

- [ ] **Step 1: 写失败测试 - 委托 + main resume**

```python
def test_run_model_benchmark_delegates_dual_system(monkeypatch):
    import benchmark.runners.run_benchmark as rb
    called={}
    monkeypatch.setattr(rb, "run_dual_system_benchmark",
        lambda *a,**k: called.update(invoked=True) or {"cases":[],"predictions":{},"evidence_results":[],"safety_results":[],"case_details":[],"failed_cases":[]})
    rb.run_model_benchmark([], "p","m","v", method="dual_system")
    assert called.get("invoked")

def test_main_dual_resume_passes_completed_keys(monkeypatch, tmp_path):
    """dual_system + resume -> completed_keys 非空传入。

    P0-4 修订：① manifest 文件名与 runner 推导一致（d.jsonl → d.manifest.json）；
    ② manifest 用真实 build_resume_manifest() 产物（全字段，逐字段比对可过）；
    ③ visibility gate 显式 monkeypatch（本测试目标是 completed_keys 透传，非可见性）。
    """
    import benchmark.runners.run_benchmark as rb, json, sys, types
    detail = tmp_path/"d.jsonl"
    row={"case_id":"Q1","predicted_answer":"A","raw_answer":"x","expected_answer":"A",
         "correct":True,"call_success":True,"parser_valid":True,
         "sample_idx":0,"permutation_id":"p0","terminal_state":"parsed",
         "attempt_key":["ds","baziqa_xjz_dual","dual","bazi","p","m","Q1",0,0,"p0"]}
    detail.write_text(json.dumps(row,ensure_ascii=False)+"\n",encoding='utf-8')
    ds = tmp_path/"dataset.jsonl"
    ds.write_text(json.dumps({"case_id":"Q1"})+"\n",encoding="utf-8")
    # ② 真实 build_resume_manifest：真实 profile 对象（不能传 None——函数直接读
    # profile.profile_id / chart_schema_version）；字段与 argv 逐一对应
    # （argv 无 --case-ids-file → case_ids_file=None；无 --attempt-stage → "main"）
    from benchmark.runners.profiles import resolve_profile
    args_like = types.SimpleNamespace(
        dataset=str(ds), case_ids_file=None, profile="baziqa_xjz_dual",
        chart_schema_version=None, arm="dual", ziwei_arm=None, attempt_stage="main",
        repeat_idx=0, provider="deepseek",
        model="deepseek-chat", temperature=0.0, sample_temperature=0.4,
        n_samples=1, aggregate="majority", method="dual_system",
        scheduled_calls=None, hard_cap=None, as_of_date="")
    profile_obj = resolve_profile("baziqa_xjz_dual", None)
    manifest_obj = rb.build_resume_manifest(args_like, profile_obj)
    (tmp_path/"d.manifest.json").write_text(json.dumps(manifest_obj), encoding="utf-8")  # ① 正确文件名
    captured = {}
    monkeypatch.setattr(rb, "run_dual_system_benchmark",
        lambda cases,*a,**k: captured.update(ck=k.get("completed_keys")) or {"cases":cases,"predictions":{},"evidence_results":[],"safety_results":[],"case_details":[],"failed_cases":[]})
    monkeypatch.setattr(rb, "assert_visibility", lambda *a, **k: [])   # ③ 绕过可见性（非本测试目标）
    monkeypatch.setattr(sys, "argv", ["run_benchmark.py","--profile","baziqa_xjz_dual","--method","dual_system",
        "--arm","dual","--resume","--model-runner","--case-details-jsonl",str(detail),"--dataset",str(ds)])
    rb.main()
    assert captured.get("ck") is not None and len(captured["ck"]) > 0
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 - 委托 + main resume 分支 + CLI choices**

line 780 后：
```python
    if method == 'dual_system':
        return run_dual_system_benchmark(cases, provider, model, max_cases=max_cases,
            temperature=temperature, case_details_jsonl=case_details_jsonl,
            chart_schema_version=chart_schema_version, resume_append=resume_append,
            completed_keys=completed_keys)
```

main resume（:1697-1703）改为：
```python
    completed_keys = None
    if args.profile and args.resume:
        completed = load_completed_keys(os.path.abspath(args.case_details_jsonl))
        ctx = _PHASE6_CTX
        if args.method == "dual_system" or args.aggregate == "emit_samples":
            completed_keys = completed
        else:
            cases = [c for c in cases if ctx.attempt_key_for(c) not in completed]
```

`--method` choices 加 `'dual_system'`；`--attempt-stage` 加 `choices=list(ATTEMPT_STAGES)+["dual"]`。

- [ ] **Step 4: 运行通过 + 回归** - `pytest tests/test_phase6_runner_routing.py tests/test_phase6_resume.py -q`
- [ ] **Step 5: Commit** - `feat(6b2): wire dual_system delegation + main resume branch + CLI validation`

---

## Task 10: 编排器 - 常量 + 调度

**Files:** Create `scripts/phase6_6b2_orchestrator.py`, `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写失败测试**

```python
def test_schedule_60_slices_dual_scheduled_24(tmp_path):
    from scripts.phase6_6b2_orchestrator import _build_schedule
    # 创建 40 case 的假数据集
    ds = tmp_path/"ds.jsonl"
    ds.write_text("\n".join([json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)])+"\n", encoding="utf-8")
    s=_build_schedule(str(tmp_path), years=["2024","2025"],
                      dataset_paths={"2024": str(ds), "2025": str(ds)})
    assert s["total_slices"]==60
    dual=[x for x in s["slices"] if x["arm"]=="dual"]
    assert all(x["scheduled_calls"]==24 for x in dual)
    assert s["total_scheduled_calls"]==960
    assert s["global_hard_cap"]==1060
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现常量 + _build_schedule**（复用 Task 17 的 `_build_schedule`，但暴露 `dataset_path` 参数）

```python
# 阶段化预算（spec §8）
FROZEN_DATE = "2026-07-17"
FROZEN_CHART_SCHEMA = "legacy_v0"
DEV_REUSE_HARD_CAP = 1060
FINAL_2023_HARD_CAP = 530
FINAL_2023_SCHEDULED = 480

def _stage_hard_cap(years):
    years_set = set(years)
    if years_set == {"2023"}:
        return FINAL_2023_HARD_CAP
    return DEV_REUSE_HARD_CAP

B1A_SLICE_SCHEDULED = 8
B1A_SLICE_HARD_CAP = 10    # 含重试储备
DUAL_SLICE_SCHEDULED = 24
DUAL_SLICE_HARD_CAP = 26    # 含重试储备
GLOBAL_HARD_CAP = 1060
JUDGE_DISAGREEMENT_RATE = 0.579    # 实测冻结值：6B1 merged_details b1a′↔b1b 分歧 139/240（2024: 58.3%，2025: 57.5%），仅作报告参照，最坏情况预算仍按 960/1060

def _build_schedule(output_dir, years=None, dataset_paths=None):
    """构建 schedule。P0-3: 每年度独立 dataset_paths，严格验证 40 唯一 case_id。

    dataset_paths: {year: path} 映射。years 参数降级为仅用于 stages 过滤。
    每个年度文件必须恰好 40 非空唯一 case_id，否则立即失败。
    """
    years = years or ["2024","2025"]
    hard_cap = _stage_hard_cap(years)
    dataset_paths = dataset_paths or {}
    slices = []
    groups = [0,1,2,3,4]  # 5 groups per arm/year/repeat
    import json as _json
    for year in years:
        ds_path = dataset_paths.get(year)
        if not ds_path or not os.path.exists(ds_path):
            raise SystemExit(f"_build_schedule 拒绝: {year} 数据集路径不存在或未指定 ({ds_path})")
        all_case_ids = []
        with open(ds_path, encoding="utf-8") as _f:
            for _line in _f:
                if _line.strip():
                    cid = _json.loads(_line).get("case_id","")
                    if cid:
                        all_case_ids.append(cid)
        if len(all_case_ids) != 40:
            raise SystemExit(f"_build_schedule 拒绝: {year} 数据集有 {len(all_case_ids)} 个 case_id，需要恰好 40")
        if len(set(all_case_ids)) != 40:
            raise SystemExit(f"_build_schedule 拒绝: {year} 数据集存在重复 case_id")
        for rep in [0,1,2]:
            for arm in ["b1a_prime","dual"]:
                scheduled = B1A_SLICE_SCHEDULED if arm == "b1a_prime" else DUAL_SLICE_SCHEDULED
                per_group = 8  # 40/5 = 8
                for g in groups:
                    start = g * per_group
                    end = start + per_group
                    g_cases = all_case_ids[start:end]
                    if len(g_cases) != 8:
                        raise SystemExit(f"_build_schedule 拒绝: {year}/{arm}/g{g} 有 {len(g_cases)} 题，需要 8")
                    slice_id = f"{year}_{arm}_{rep}_g{g}"
                    out_dir = os.path.join(output_dir, slice_id)
                    slice_hard_cap = B1A_SLICE_HARD_CAP if arm == "b1a_prime" else DUAL_SLICE_HARD_CAP
                    slices.append({"year":year,"repeat":rep,"arm":arm,"group":g,
                                   "slice_id":slice_id,"output_dir":out_dir,
                                   "detail_path":os.path.join(out_dir,"details.jsonl"),
                                   "events_path":os.path.join(out_dir,"details.events.jsonl"),
                                   "dataset_path":ds_path,
                                   "case_ids_file":os.path.join(out_dir,"case_ids.json"),
                                   "profile":("baziqa_xjz_reasoned" if arm == "b1a_prime"
                                              else "baziqa_xjz_dual"),
                                   "method":("direct_choice" if arm == "b1a_prime"
                                             else "dual_system"),
                                   # v15：预算/题数冻结进 slice，cmd 与 manifest 只读 slice 字段（消除分支漂移）
                                   "hard_cap": slice_hard_cap, "max_cases": 8,
                                   "scheduled_calls":scheduled,"case_ids":g_cases})
    return {"slices":slices,"global_hard_cap":hard_cap,
            "total_scheduled_calls":sum(s["scheduled_calls"] for s in slices),
            "total_slices":len(slices)}
```
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): orchestrator constants + 60-slice schedule`

---

## Task 11: BudgetLedger6B2 + slice 执行

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写失败测试**

```python
def test_budget_ledger_6b2_init(tmp_path):
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
    l = BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=1060, slice_min=8, slice_max=26)
    assert l.hard_cap == 1060
    assert l.slice_min == 8
    assert l.slice_max == 26
    assert l.total_attempted == 0
    assert len(l._completed) == 0

def test_budget_ledger_can_attempt_rejects_over_cap(tmp_path):
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
    l = BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=10, slice_min=8, slice_max=26)
    assert l.can_attempt(0)
    l.total_attempted = 10
    assert not l.can_attempt(1)
    assert l.can_attempt(0)

def test_smoke_budget_1_and_10_passed(tmp_path):
    """smoke ledger: 1 和 10 次调用均在 [1,10] 范围内，通过（独立账本）。"""
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
    low = BudgetLedger6B2(str(tmp_path / "low.json"), global_hard_cap=10, slice_min=1, slice_max=10)
    low.record_slice_completed("s1", 1, arm="smoke")
    assert low.total_attempted == 1
    assert low.slice_completed("s1")
    high = BudgetLedger6B2(str(tmp_path / "high.json"), global_hard_cap=10, slice_min=1, slice_max=10)
    high.record_slice_completed("s1", 10, arm="smoke")
    assert high.total_attempted == 10

def test_smoke_budget_0_and_11_rejected(tmp_path):
    """smoke ledger: 0 和 11 次调用超出 [1,10] 范围，拒绝。"""
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
    import pytest
    l = BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=10, slice_min=1, slice_max=10)
    with pytest.raises(SystemExit):
        l.record_slice_completed("s_bad", 0, arm="smoke")
    with pytest.raises(SystemExit):
        l.record_slice_completed("s_bad2", 11, arm="smoke")
    assert l.total_attempted == 0

def test_smoke_budget_persists_reload(tmp_path):
    """smoke ledger: 记录后重新加载，账本一致。"""
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
    l = BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=10, slice_min=1, slice_max=10)
    l.record_slice_completed("s1", 5, arm="smoke")
    l2 = BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=10, slice_min=1, slice_max=10)
    assert l2.total_attempted == 5
    assert l2.slice_completed("s1")
    assert l2.attempts_by_slice == {"s1": 5}

def test_smoke_budget_global_hard_cap_after_completion(tmp_path):
    """smoke ledger: 完成后 total_attempted 不得突破 hard_cap。"""
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2
    import pytest
    l = BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=10, slice_min=1, slice_max=10)
    l.record_slice_completed("s1", 10, arm="smoke")
    assert l.total_attempted == 10
    # 已完成 slice 幂等跳过
    l.record_slice_completed("s1", 10, arm="smoke")
    assert l.total_attempted == 10
    # 再完成一个会导致突破 10
    with pytest.raises(SystemExit):
        l.record_slice_completed("s2", 1, arm="smoke")

def test_build_runner_cmd_dual(tmp_path):
    from scripts.phase6_6b2_orchestrator import _build_runner_cmd, _build_schedule
    import json
    ds = tmp_path/"ds.jsonl"
    ds.write_text("\n".join([json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)])+"\n", encoding="utf-8")
    sched = _build_schedule(str(tmp_path), years=["2024"],
                            dataset_paths={"2024": str(ds)})
    dual = [s for s in sched["slices"] if s["arm"]=="dual"][0]
    Path(dual["output_dir"]).mkdir(parents=True, exist_ok=True)
    cmd = _build_runner_cmd(dual, "p", "m")
    assert "--method dual_system" in " ".join(cmd)
    assert "--attempt-stage dual" in " ".join(cmd)
    assert "--hard-cap 26" in " ".join(cmd)
    assert "--model-runner" in cmd
    assert "--model-runner" != cmd[-1]  # 不是最后一个参数（后面有值）
    assert "benchmark.runners.run_benchmark" in " ".join(cmd)
    assert dual["dataset_path"] in " ".join(cmd) or "--dataset" not in " ".join(cmd)
```

- [ ] **Step 2: 运行确认失败（红灯）**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_phase6_6b2.py -q -k "budget_ledger or smoke_budget or build_runner_cmd_dual"`
Expected before implementation: FAIL（ImportError / AttributeError - BudgetLedger6B2、_build_runner_cmd 未定义）

- [ ] **Step 3: 实现 BudgetLedger6B2（参数化）+ _build_runner_cmd + _run_slice + _process_slice**

```python
class BudgetLedger6B2:
    """参数化账本。global_hard_cap/slice_min/slice_max 可配置。
    
    record_slice_completed 幂等：已完成的 slice 不会重复增加 total_attempted。
    通过 attempts_by_slice 映射追踪每个 slice 的实际调用数。
    """
    def __init__(self, ledger_path, global_hard_cap=1060, slice_min=8, slice_max=26):
        self.path = Path(ledger_path)
        self._init_hard_cap = global_hard_cap
        self.hard_cap = global_hard_cap
        self.slice_min = slice_min
        self.slice_max = slice_max
        self.total_attempted = 0
        self._completed = set()
        self.attempts_by_slice = {}
        self._load()
    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            file_hard_cap = data.get("hard_cap")
            if file_hard_cap is not None and file_hard_cap != self._init_hard_cap:
                raise SystemExit(f"BudgetLedger6B2 拒绝: 文件 hard_cap ({file_hard_cap}) != 实例化值 ({self._init_hard_cap})")
            self.total_attempted = data.get("total_attempted", 0)
            self._completed = set(data.get("completed_slices", []))
            self.attempts_by_slice = data.get("attempts_by_slice", {})
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"total_attempted": self.total_attempted,
             "completed_slices": sorted(self._completed),
             "attempts_by_slice": self.attempts_by_slice,
             "hard_cap": self.hard_cap}, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(self.path))
    def record_slice_completed(self, slice_id, actual_attempts, arm="b1a_prime"):
        """幂等记录。已完成的 slice 不重复增加 total_attempted。
        
        actual_attempts 必须从 events 中统计的 kind=call_attempt 行数。
        按 arm 验证调用计数范围：B1-a′ 8-10，dual 16-26；
        v15：其他臂（如 smoke）走构造时 slice_min/slice_max 范围（不再落入 dual 区间）。
        v16：最终全局 hard-cap 防线——完成后 total_attempted 不得突破 hard_cap。
        首次调用：记录 attempts；重复调用：跳过（不增加 total_attempted）。
        """
        if slice_id in self._completed:
            return
        ARM_RANGES = {"b1a_prime": (8, 10), "dual": (16, 26)}
        arm_min, arm_max = ARM_RANGES.get(arm, (self.slice_min, self.slice_max))
        if not (arm_min <= actual_attempts <= arm_max):
            raise SystemExit(f"BudgetLedger6B2 拒绝: slice {slice_id} ({arm}) actual_attempts={actual_attempts} 不在 [{arm_min},{arm_max}] 范围内")
        if self.total_attempted + actual_attempts > self.hard_cap:
            raise SystemExit(f"BudgetLedger6B2 拒绝: slice {slice_id} 完成后突破 hard_cap ({self.total_attempted}+{actual_attempts} > {self.hard_cap})")
        self._completed.add(slice_id)
        self.attempts_by_slice[slice_id] = actual_attempts
        self.total_attempted += actual_attempts
        self._save()
    def slice_completed(self, slice_id):
        return slice_id in self._completed
    def can_attempt(self, extra=0):
        return self.total_attempted + extra <= self.hard_cap

def _build_runner_cmd(slice_info, provider, model, resume=False):
    """构造 subprocess 参数。按 arm 分支 + 正确 CLI 参数。

    b1a_prime: reasoned profile、direct_choice、stage main、hard_cap=10
    dual: dual profile、dual_system、stage dual、hard_cap=26
    resume=True 时添加 --resume 标志。
    """
    import json as _json, sys
    case_ids_file = os.path.join(slice_info["output_dir"], "case_ids.json")
    os.makedirs(os.path.dirname(case_ids_file), exist_ok=True)  # v14：目录可能未创建
    with open(case_ids_file, "w", encoding="utf-8") as _f:
        _json.dump(slice_info["case_ids"], _f)
    base = [sys.executable, "-m", "benchmark.runners.run_benchmark"]
    # v15：预算/题数单源化——只读 slice 冻结字段（smoke 与普通 slice 同源，无臂分支漂移）
    slice_hard_cap = slice_info["hard_cap"]
    common = [
        "--repeat-idx", str(slice_info["repeat"]),
        "--hard-cap", str(slice_hard_cap),
        "--provider", provider, "--model", model,
        "--model-runner",
        "--case-details-jsonl", slice_info["detail_path"],
        "--case-ids-file", case_ids_file,
        "--max-cases", str(slice_info["max_cases"]),
        "--scheduled-calls", str(slice_info["scheduled_calls"]),
        "--temperature", "0",
        "--output-dir", slice_info["output_dir"],
        "--as-of-date", FROZEN_DATE,
        "--chart-schema-version", FROZEN_CHART_SCHEMA,
    ]
    if resume:
        common.append("--resume")
    if slice_info["arm"] == "b1a_prime":
        cmd = base + [
            "--profile", "baziqa_xjz_reasoned",
            "--method", "direct_choice",
            "--attempt-stage", "main",
            "--arm", "b1a_prime",
            "--ziwei-arm", "none",
            "--dataset", slice_info["dataset_path"]] + common
    else:
        cmd = base + [
            "--profile", "baziqa_xjz_dual",
            "--method", "dual_system",
            "--attempt-stage", "dual",
            "--arm", "dual",
            "--dataset", slice_info["dataset_path"]] + common
    return cmd

def _slice_integrity_gate(detail_rows, slice_info):
    """单 slice 完整性门禁。验证 case 齐全、stage 终态、judge 基数。
    
    B1-a′：8 个 case，每个恰 1 个 main 终态行。
    dual：8 个 case，每个恰 1 bazi + 1 ziwei 终态行；
    judge 基数：共识或双侧 unresolved → 0；分歧/单侧 unresolved → 1。
    """
    case_ids = set(slice_info["case_ids"])
    present = {r.get("case_id") for r in detail_rows if r.get("case_id") in case_ids}
    if len(present) != 8:
        return f"CASE_COUNT: {len(present)}/8"
    by_case = {}
    for r in detail_rows:
        cid = r.get("case_id")
        if cid in case_ids:
            by_case.setdefault(cid, []).append(r)
    for cid in case_ids:
        rows = by_case.get(cid, [])
        # P0-1 修订：stage 统一从 attempt_key[3] 解析——真实 detail 行（enrich_row 契约）
        # 无顶层 dual_stage，顶层 dual_stage 仅 dual 管线诊断附列，不作门禁依据。
        def _stage(r):
            ak = r.get("attempt_key") or [None] * 10
            return ak[3]
        if slice_info["arm"] == "b1a_prime":
            mains = [r for r in rows if _stage(r) == "main"]
            if len(mains) != 1:
                return f"B1A_MAIN: {cid} count={len(mains)}"
            # P0-2 修订：合法终态恢复全集（run_benchmark.py:48 TERMINAL_STATES）——
            # parser invalid 是合法终态，不得判 slice 失败
            if mains[0].get("terminal_state") not in ("parsed", "invalid", "unresolved",
                                                      "judge_unresolved", "call_failed"):
                return f"B1A_TERMINAL: {cid} state={mains[0].get('terminal_state')}"
        else:
            bazis = [r for r in rows if _stage(r) == "bazi"]
            ziwes = [r for r in rows if _stage(r) == "ziwei"]
            if len(bazis) != 1:
                return f"BAZI_COUNT: {cid} count={len(bazis)}"
            if len(ziwes) != 1:
                return f"ZIWEI_COUNT: {cid} count={len(ziwes)}"
            # 中优修订：dual 分支同样逐行验证合法终态（与 B1-a′ 同一 5 态全集）
            for r in bazis + ziwes + [r for r in rows if _stage(r) == "judge"]:
                if r.get("terminal_state") not in ("parsed", "invalid", "unresolved",
                                                   "judge_unresolved", "call_failed"):
                    return f"DUAL_TERMINAL: {cid} state={r.get('terminal_state')}"
            b_ans = bazis[0].get("predicted_answer")
            z_ans = ziwes[0].get("predicted_answer")
            judges = [r for r in rows if _stage(r) == "judge"]
            consensus = (b_ans is not None and z_ans is not None and b_ans == z_ans)
            both_unresolved = (b_ans is None and z_ans is None)
            if consensus or both_unresolved:
                if len(judges) != 0:
                    return f"JUDGE_ON_{'CONSENSUS' if consensus else 'BOTH_UNRESOLVED'}: {cid} count={len(judges)}"
            else:
                if len(judges) != 1:
                    return f"MISSING_JUDGE: {cid} count={len(judges)}"
    return "PASS"


# ── Task 11 helpers（前引用修复：_sha256_file/_load_events/_slice_runner_args 在本任务定义，
#    Task 15/16 复用，不再各自重复定义）──

def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_events(path):
    """读取 events/detail JSONL 为行 dict 列表（缺失文件返回空列表由调用方判 fail-closed）。"""
    import json as _json
    import os as _os
    if not _os.path.exists(path):
        return []
    return [_json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def _slice_runner_args(slice_info, provider, model):
    """由 slice_info + run 级 provider/model 重建 runner argv 对应的 args 命名空间。

    P0-1/v12 修订：与 `_build_runner_cmd` 的冻结配置逐字段同源——per-arm profile/method/
    ziwei_arm（b1a_prime="none"，dual 缺省）、`repeat` → `repeat_idx`、case_ids_file、
    per-arm hard_cap、FROZEN_DATE/FROZEN_CHART_SCHEMA。供完成态 resume 重建当前 manifest。"""
    import types
    is_b1a = slice_info["arm"] == "b1a_prime"
    return types.SimpleNamespace(
        dataset=slice_info["dataset_path"],
        case_ids_file=slice_info["case_ids_file"],
        profile=slice_info["profile"],
        chart_schema_version=FROZEN_CHART_SCHEMA,
        arm=slice_info["arm"],
        ziwei_arm="none" if is_b1a else None,       # dual：argv 不传 → manifest 记 default
        attempt_stage="main" if is_b1a else "dual",
        repeat_idx=slice_info["repeat"],            # schedule 字段名为 repeat
        provider=provider, model=model,             # run 级参数（不在 slice dict 内）
        temperature=0.0, sample_temperature=0.4,
        n_samples=1, aggregate="majority",
        method=slice_info["method"],
        scheduled_calls=slice_info["scheduled_calls"],
        hard_cap=slice_info["hard_cap"],            # v15：读 slice 冻结字段（smoke=10）
        as_of_date=FROZEN_DATE)


def _run_slice(slice_info, ledger, provider, model, integrity="slice"):
    """原子执行单个 slice（v14：integrity="slice"|"smoke" 分支完整落入本函数）。

    smoke 分支差异：独立小预算（SMOKE_HARD_CAP 而非 DUAL_SLICE_HARD_CAP）、
    runner manifest 路径按 detail_path 推导（detail.jsonl → detail.manifest.json）、
    smoke 自有完整性口径（_smoke_integrity，不经 8 题门禁）、record 走构造范围校验。
    partial resume（P0-4）：runner 三件套（manifest/events/detail）任一存在而
    slice_status.json 不存在 → 按 resume 续跑（不传 --resume 会被 runner fail-closed 拒绝）。
    """
    import subprocess, time
    out_dir = Path(slice_info["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    is_smoke = integrity == "smoke"
    status_path = out_dir / "slice_status.json"
    detail_path = Path(slice_info["detail_path"])
    events_path = Path(slice_info["events_path"])
    # manifest 路径按 runner 推导规则（detail.jsonl → detail.manifest.json；smoke 为 detail.manifest.json）
    runner_manifest_path = Path(str(detail_path).replace(".jsonl", ".manifest.json"))
    lock = None
    try:
        # 1. OutputDirLock（复用 6B1D 机制）
        from scripts.phase6_6b1d_orchestrator import OutputDirLock
        lock = OutputDirLock.acquire(str(out_dir))
        if lock is None:
            raise SystemExit(f"slice {slice_info['slice_id']} 输出目录被其他进程持有")
        # 2. Resume 检测（v14 三态：完成态 / slice_status 存在的续跑 / runner 产物的 partial resume）
        is_resume = False
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("completed") and status.get("slice_id") == slice_info["slice_id"]:
                # 完成态校验：manifest 重建比对 + events + actual 计数（同 v12/v13 契约）
                if not runner_manifest_path.exists():
                    raise SystemExit(f"slice {slice_info['slice_id']} resume 拒绝: runner manifest 缺失")
                from benchmark.runners.run_benchmark import (
                    build_resume_manifest, check_resume_manifest)
                from benchmark.runners.profiles import resolve_profile
                profile_obj = resolve_profile(slice_info["profile"], FROZEN_CHART_SCHEMA)
                current_manifest = build_resume_manifest(
                    _slice_runner_args(slice_info, provider, model), profile_obj)
                check_resume_manifest(str(runner_manifest_path), current_manifest)
                if not events_path.exists():
                    raise SystemExit(f"slice {slice_info['slice_id']} resume 拒绝: events 文件缺失 ({events_path})")
                actual = sum(1 for r in _load_events(slice_info["events_path"])
                            if r.get("kind") == "call_attempt")
                if actual != status.get("actual_attempts", -1):
                    raise SystemExit(f"slice {slice_info['slice_id']} resume 拒绝: actual_attempts 不一致 ({actual} != {status.get('actual_attempts')})")
                ledger.record_slice_completed(slice_info["slice_id"], actual,
                                              arm=("smoke" if is_smoke else slice_info["arm"]))
                return
            is_resume = True
        elif runner_manifest_path.exists() or events_path.exists() or detail_path.exists():
            # P0-4：崩溃窗口（runner 已产出 manifest/events/detail、编排器未写 status）
            # → partial resume；不传 --resume 会被 runner fail-closed 拒绝
            is_resume = True
        # 3. Budget reservation（v16：预检包含 completed + existing + remaining；完成后再校验全局上限）
        existing_attempts = 0
        if is_resume and events_path.exists():
            existing_attempts = sum(1 for r in _load_events(str(events_path))
                                    if r.get("kind") == "call_attempt")
        remaining = slice_info["hard_cap"] - existing_attempts
        if remaining < 0:
            raise SystemExit(f"slice {slice_info['slice_id']} resume 拒绝: events 已超 hard_cap ({existing_attempts} > {slice_info['hard_cap']})")
        if ledger.total_attempted + existing_attempts + remaining > ledger.hard_cap:
            raise SystemExit(f"slice {slice_info['slice_id']} 拒绝: 预算不足 ({ledger.total_attempted}+{existing_attempts}+{remaining} > {ledger.hard_cap})")
        # 4. 执行模型
        cmd = _build_runner_cmd(slice_info, provider, model, resume=is_resume)
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        elapsed = time.time() - start
        # 5. 检查退出码
        if result.returncode != 0:
            raise SystemExit(f"slice {slice_info['slice_id']} 失败 (exit={result.returncode}): {result.stderr[:500]}")
        # 6. 验证产物
        if not detail_path.exists() or detail_path.stat().st_size == 0:
            raise SystemExit(f"slice {slice_info['slice_id']} 失败: detail jsonl 缺失或为空")
        if not events_path.exists() or events_path.stat().st_size == 0:
            raise SystemExit(f"slice {slice_info['slice_id']} 失败: events jsonl 缺失或为空")
        if not runner_manifest_path.exists():
            raise SystemExit(f"slice {slice_info['slice_id']} 失败: runner 未生成 manifest")
        # 7. 完整性门禁（smoke 口径 vs slice 口径）
        detail_rows = _load_events(str(detail_path))
        integrity_result = (_smoke_integrity(detail_rows, slice_info) if is_smoke
                            else _slice_integrity_gate(detail_rows, slice_info))
        if integrity_result != "PASS":
            raise SystemExit(f"slice {slice_info['slice_id']} 失败: 完整性门禁 ({integrity_result})")
        # 8. 统计实际调用数（kind=call_attempt）
        actual = sum(1 for r in _load_events(str(events_path)) if r.get("kind") == "call_attempt")
        # 9. 写 slice_status.json（保留 runner manifest 原样）
        runner_manifest_sha = _sha256_file(str(runner_manifest_path))
        status_path.write_text(json.dumps({
            "slice_id": slice_info["slice_id"], "completed": True,
            "exit_code": result.returncode, "elapsed_s": round(elapsed, 1),
            "actual_attempts": actual, "scheduled_calls": slice_info["scheduled_calls"],
            "hard_cap": slice_info["hard_cap"], "remaining_reserved": remaining,
            "runner_manifest_sha256": runner_manifest_sha,
            "arm": slice_info["arm"], "integrity": integrity,
            "method": "dual_system" if slice_info["arm"] == "dual" else "direct_choice",
        }, ensure_ascii=False), encoding="utf-8")
        # 10. 记录实际调用数（smoke 走构造范围 slice_min/max，普通 slice 按臂范围）
        ledger.record_slice_completed(slice_info["slice_id"], actual,
                                      arm=("smoke" if is_smoke else slice_info["arm"]))
    finally:
        if lock is not None:
            lock.release()


def _smoke_integrity(detail_rows, slice_info):
    """smoke 自有完整性（v14/v15）：每题 bazi+ziwei 恰 1 行、终态 5 态全集、
    judge 按分歧基数校验（共识/双侧 unresolved→0；分歧/单侧 unresolved→恰 1）、
    未知额外 stage 拒绝；case 数按 slice_info['case_ids'] 动态，不经 8 题切片门禁。"""
    case_ids = set(slice_info["case_ids"])
    present = {r.get("case_id") for r in detail_rows if r.get("case_id") in case_ids}
    if present != case_ids:
        return f"SMOKE_CASE_COUNT: {len(present)}/{len(case_ids)}"
    for cid in case_ids:
        rows = [r for r in detail_rows if r.get("case_id") == cid]
        stages = {}
        by_stage = {}
        for r in rows:
            st = (r.get("attempt_key") or [None] * 10)[3]
            if st not in ("bazi", "ziwei", "judge"):
                return f"SMOKE_UNKNOWN_STAGE: {cid} stage={st}"
            if r.get("terminal_state") not in ("parsed", "invalid", "unresolved",
                                               "judge_unresolved", "call_failed"):
                return f"SMOKE_TERMINAL: {cid} state={r.get('terminal_state')}"
            stages[st] = stages.get(st, 0) + 1
            by_stage[st] = r
        if stages.get("bazi") != 1 or stages.get("ziwei") != 1:
            return f"SMOKE_STAGE: {cid} {stages}"
        # judge 分歧基数（v15）：与切片门禁同语义
        b_ans = by_stage["bazi"].get("predicted_answer")
        z_ans = by_stage["ziwei"].get("predicted_answer")
        n_judge = stages.get("judge", 0)
        consensus = (b_ans is not None and z_ans is not None and b_ans == z_ans)
        both_unresolved = (b_ans is None and z_ans is None)
        if consensus or both_unresolved:
            if n_judge != 0:
                return f"SMOKE_JUDGE_ON_{'CONSENSUS' if consensus else 'BOTH_UNRESOLVED'}: {cid} count={n_judge}"
        else:
            if n_judge != 1:
                return f"SMOKE_MISSING_JUDGE: {cid} count={n_judge}"
    return "PASS"

def _process_slice(slice_info, output_dir):
    """收集 slice 结果。"""
    detail_path = Path(slice_info["detail_path"])
    events_path = Path(slice_info["events_path"])
    details = []
    events = []
    if detail_path.exists():
        for line in open(detail_path, encoding="utf-8"):
            if line.strip(): details.append(json.loads(line))
    if events_path.exists():
        for line in open(events_path, encoding="utf-8"):
            if line.strip(): events.append(json.loads(line))
    return {"slice_id": slice_info["slice_id"], "details": details, "events": events}
```
- [ ] **Step 4: 运行确认全绿（绿灯）**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_phase6_6b2.py -q -k "budget_ledger or smoke_budget or build_runner_cmd_dual"`
Expected: 7 passed（init / can_attempt_rejects / smoke_1_10 / smoke_0_11_rejected / smoke_persists_reload / smoke_global_hard_cap / build_runner_cmd_dual）

- [ ] **Step 5: Commit** - `feat(6b2): parameterized BudgetLedger + slice execution + cmd builder`

---

## Task 12: 多 stage 完整性门禁（P0-2 修订：验证 judge 基数）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**P0-2：** judge 不能仅当"合法 extra"。必须按 bazi/ziwei 结果验证 judge 基数为 0 或 1：共识题 judge 行必须 0；分歧/单侧 unresolved 必须 1；缺失或多余均失败。

- [ ] **Step 1: 写失败测试 - judge 基数验证 + 预期 cell 矩阵**

```python
def _mk_detail_row(cid, arm, stage, ans, dataset="baziqa_contest8_2024_holdout_enriched", repeat=0, state="parsed", sample_idx=0):
    return {"case_id":cid,"predicted_answer":ans,"expected_answer":"A","correct":ans=="A",
            "dual_stage":stage,"terminal_state":state,
            "attempt_key":[dataset,"prof",arm,stage,"p","m",cid,repeat,sample_idx,"p0"]}

def _simple_schedule(case_ids, year="2024", repeat=0, arms=("b1a_prime","dual")):
    """构建最小 schedule 供完整性测试使用。"""
    slices = []
    for arm in arms:
        slices.append({"year":year,"repeat":repeat,"arm":arm,"case_ids":list(case_ids),
                       "slice_id":f"{year}_{arm}_{repeat}","scheduled_calls":len(case_ids)*8})
    return {"slices":slices,"global_hard_cap":1060,"total_scheduled_calls":sum(s["scheduled_calls"] for s in slices)}

def test_integrity_judge_count_consensus_zero():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"])
    rows=[_mk_detail_row("Q1","b1a_prime","main","A"),
          _mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, sched)=="PASS"

def test_integrity_judge_extra_on_consensus_fails():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"], arms=("dual",))
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A"),
          _mk_detail_row("Q1","dual","judge","A")]
    assert _integrity_gate(rows, sched).startswith("JUDGE_ON_CONSENSUS")

def test_integrity_disagreement_requires_judge():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"], arms=("dual",))
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","B")]
    assert _integrity_gate(rows, sched).startswith("MISSING_JUDGE")

def test_integrity_unilateral_unresolved_requires_judge():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"], arms=("dual",))
    rows=[_mk_detail_row("Q1","dual","bazi",None,state="call_failed"),
          _mk_detail_row("Q1","dual","ziwei","B")]
    assert _integrity_gate(rows, sched).startswith("MISSING_JUDGE")

def test_integrity_both_unresolved_zero_judge():
    """双侧 unresolved -> 0 judge（runner 不调 judge）。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"], arms=("dual",))
    rows=[_mk_detail_row("Q1","dual","bazi",None,state="invalid"),
          _mk_detail_row("Q1","dual","ziwei",None,state="invalid")]
    assert _integrity_gate(rows, sched)=="PASS"

def test_integrity_both_unresolved_with_judge_fails():
    """双侧 unresolved 却有 judge -> 失败。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"], arms=("dual",))
    rows=[_mk_detail_row("Q1","dual","bazi",None,state="invalid"),
          _mk_detail_row("Q1","dual","ziwei",None,state="invalid"),
          _mk_detail_row("Q1","dual","judge","A")]
    assert _integrity_gate(rows, sched).startswith("JUDGE_ON_BOTH_UNRESOLVED")

def test_integrity_b1a_missing_main_fails():
    """b1a_prime 缺 main 行 -> 失败（预期有 cell 但不存在）。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"])
    # 只有 dual 行，缺 b1a_prime cell -> MISSING_CELLS
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, sched).startswith("MISSING_CELLS")

def test_integrity_b1a_duplicate_main_fails():
    """b1a_prime 2 个 main 行（相同 cell）-> B1A_MAIN_COUNT（不是 DUPLICATE）。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"])
    # 两行相同 (year,repeat,case_id,arm) 但不同 attempt_key（不同 sample_idx）
    # -> 同一 cell 内 2 个 main 行，非 DUPLICATE
    rows=[_mk_detail_row("Q1","b1a_prime","main","A",repeat=0),
          _mk_detail_row("Q1","b1a_prime","main","A",repeat=0,state="call_failed",sample_idx=1),
          _mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, sched).startswith("B1A_MAIN_COUNT")

def test_integrity_missing_bazi_fails():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"])
    # 只有 ziwei 无 bazi -> MISSING_CELLS（因为预期 cell 中 dual 需要 bazi+ziwei，但这里只有 ziwei 行）
    # 实际上 _simple_schedule 创建了 b1a_prime 和 dual 两个 arm，因此需要 b1a_prime 的 main 行
    rows=[_mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, sched).startswith("MISSING_CELLS")

def test_integrity_duplicate_key_fails():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"])
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","bazi","A"),
          _mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, sched).startswith("DUPLICATE")

def test_integrity_extra_cell_fails():
    """actual cell 超出预期 -> EXTRA_CELLS。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"], arms=("dual",))
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A"),
          _mk_detail_row("Q2","dual","bazi","A"),_mk_detail_row("Q2","dual","ziwei","A")]
    assert _integrity_gate(rows, sched).startswith("EXTRA_CELLS")

def test_integrity_b1a_extra_stage_judge_fails():
    """b1a_prime 出现 judge stage -> B1A_EXTRA_STAGE。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"])
    rows=[_mk_detail_row("Q1","b1a_prime","main","A"),
          _mk_detail_row("Q1","b1a_prime","judge","A"),
          _mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, sched).startswith("B1A_EXTRA_STAGE")

def test_integrity_dual_extra_stage_main_fails():
    """dual 出现 main stage -> DUAL_EXTRA_STAGE。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"], arms=("dual",))
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A"),
          _mk_detail_row("Q1","dual","main","A")]
    assert _integrity_gate(rows, sched).startswith("DUAL_EXTRA_STAGE")

def test_integrity_unknown_arm_fails():
    """未知 arm -> UNKNOWN_ARM（优先于 MISSING_CELLS）。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    sched = _simple_schedule(["Q1"], arms=("dual",))
    rows=[_mk_detail_row("Q1","b1c","main","A")]
    assert _integrity_gate(rows, sched).startswith("UNKNOWN_ARM")
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 _integrity_gate（P0-1 修订：按 (year,repeat,case,arm) 分组）**

```python
import re

def _year_from_dataset_id(dataset_id):
    m = re.search(r"baziqa_contest8_(\d{4})_holdout", dataset_id or "")
    return m.group(1) if m else None

def parse_detail_identity(row):
    """从真实 detail row 的 attempt_key 解析 (year, repeat, case_id, arm, stage)。"""
    ak = row["attempt_key"]
    return (_year_from_dataset_id(ak[0]), int(ak[7]), ak[6], ak[2], ak[3])

def _expected_cells(schedule):
    """从 schedule 构建预期 cell 矩阵 {(year,repeat,case_id,arm)}。"""
    cells = set()
    for sl in schedule["slices"]:
        for cid in sl["case_ids"]:
            cells.add((sl["year"], sl["repeat"], cid, sl["arm"]))
    return cells

def _integrity_gate(merged_details, schedule):
    """完整性门禁。按 (year,repeat,case_id,arm) 分组（不跨 repeat/arm 合并）。

    P0-2: 从 schedule 构建预期 cell 矩阵，检测缺失 arm/case。
    冻结规则：
    - b1a_prime: 恰好 1 个 main 行/case
    - dual: 恰好 1 bazi + 1 ziwei/case
    - judge 基数: 共识(b==z 且均非 None) -> 0; 双侧均 unresolved -> 0; 其余 -> 1
    """
    from collections import defaultdict
    expected = _expected_cells(schedule)
    by_cell = defaultdict(lambda: defaultdict(list))  # (yr,rep,cid,arm) -> stage -> rows
    seen = set()
    for r in merged_details:
        year, rep, cid, arm, stage = parse_detail_identity(r)
        ak = tuple(r["attempt_key"])
        if ak in seen: return f"DUPLICATE: {ak}"
        seen.add(ak)
        by_cell[(year,rep,cid,arm)][stage].append(r)
    # P1: 先检查未知 arm（优先于 MISSING_CELLS / EXTRA_CELLS / stage 校验）
    actual = set(by_cell.keys())
    VALID_ARMS = {"b1a_prime", "dual"}
    for (yr, rp, cid, arm) in actual:
        if arm not in VALID_ARMS:
            return f"UNKNOWN_ARM: {arm} (cell={yr}/{rp}/{cid})"
    # P0-2: 检查预期 cell 是否全部存在
    missing = expected - actual
    if missing:
        return f"MISSING_CELLS: {sorted(missing)[:3]}..."
    # P0-1: 拒绝额外 cell（actual - expected）
    extra = actual - expected
    if extra:
        return f"EXTRA_CELLS: {sorted(extra)[:3]}..."
    # 对每个实际存在的 cell 做内容校验
    B1A_VALID_STAGES = {"main"}
    DUAL_VALID_STAGES = {"bazi", "ziwei", "judge"}
    for (year,rep,cid,arm), stages in by_cell.items():
        if arm == "b1a_prime":
            extra_stages = set(stages.keys()) - B1A_VALID_STAGES
            if extra_stages:
                return f"B1A_EXTRA_STAGE: {year}/{rep}/{cid} extra={extra_stages}"
            if len(stages.get("main",[])) != 1:
                return f"B1A_MAIN_COUNT: {year}/{rep}/{cid} = {len(stages.get('main',[]))}"
        elif arm == "dual":
            extra_stages = set(stages.keys()) - DUAL_VALID_STAGES
            if extra_stages:
                return f"DUAL_EXTRA_STAGE: {year}/{rep}/{cid} extra={extra_stages}"
            if len(stages.get("bazi",[])) != 1:
                return f"BAZI_COUNT: {year}/{rep}/{cid} = {len(stages.get('bazi',[]))}"
            if len(stages.get("ziwei",[])) != 1:
                return f"ZIWEI_COUNT: {year}/{rep}/{cid} = {len(stages.get('ziwei',[]))}"
            b_ans = stages["bazi"][0].get("predicted_answer")
            z_ans = stages["ziwei"][0].get("predicted_answer")
            judge = stages.get("judge",[])
            consensus = (b_ans is not None and z_ans is not None and b_ans == z_ans)
            both_unresolved = (b_ans is None and z_ans is None)
            if consensus or both_unresolved:
                if len(judge) != 0:
                    return f"JUDGE_ON_{('CONSENSUS' if consensus else 'BOTH_UNRESOLVED')}: {year}/{rep}/{cid}"
            else:
                if len(judge) != 1:
                    return f"MISSING_JUDGE: {year}/{rep}/{cid} (count={len(judge)})"
    for r in merged_details:
        if r.get("terminal_state") not in ("parsed","invalid","unresolved","judge_unresolved","call_failed"):
            return f"INVALID_STATE: {r.get('terminal_state')}"
    return "PASS"
```

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): integrity gate validates judge cardinality`

---

## Task 13: gate（冻结聚合算法 + 三阶段参数化）+ 报告 + B1-c advisory（P0-1/P0-2/P1 修订）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**P0-1：真实 detail row 无顶层 `year`/`repeat`/`arm`（已验证）。** year 从 `attempt_key[0]`（dataset_id，如 `baziqa_contest8_2024_holdout_enriched`）解析，arm 从 `attempt_key[2]`，repeat 从 `attempt_key[7]`。用统一 `parse_detail_identity()`。

**P0-2：compute_gate 硬编码 2024/2025，无法支持 reuse/final_2023。** 参数化 `stage`，三档裁决（spec §7.3/§7.4）：
- dev：`Δ_dev≥+4pp 且 dual_acc≥32.5% 且 min(Δ_2024,Δ_2025)≥-2pp` -> PROMOTE_CANDIDATE/ROLLBACK
- reuse：`Δ_2021≥+2pp 且 Δ_2022≥+2pp` -> PASS/FAIL
- final_2023：`Δ2023≥0` CONFIRMED_PROMOTE；`-5pp<Δ2023<0` INCONCLUSIVE；`Δ2023≤-5pp` ROLLBACK

**P1：** 计算前验证每 `year×repeat×arm` 恰有 40 唯一 case，缺失不隐式计错（显式报错）；B1-c advisory 读 `attempt_key[2]`；冻结 B1-c 归档预期 SHA-256。

**冻结最终答案聚合算法：**
```
parse_detail_identity(row) -> (year, repeat, case_id, arm, stage)
  year = _year_from_dataset_id(row["attempt_key"][0])  # "baziqa_contest8_2024_holdout_enriched" -> "2024"
  arm = row["attempt_key"][2]
  repeat = row["attempt_key"][7]
  stage = row["attempt_key"][3]
  case_id = row["attempt_key"][6]

对每个 (year, repeat, case_id, arm) 聚合：
  b1a_prime: 1 main 行 -> final = predicted_answer
  dual: bazi 行 ans_b + ziwei 行 ans_z
    若 ans_b/ans_z 非 None 且相等 -> final=共识（无 judge 行）
    否则 -> judge 行 ans_j（可能不存在），final=ans_j（None if 未调/失败/未解析）

验证：每 (year, repeat, arm) 恰 40 唯一 case_id，否则 raise（不隐式计错）
acc(year,repeat,arm) = correct / 40
Δ(year,repeat) = acc_dual - acc_b1a
禁止：直接平均 detail 行 correct（judge 行改变分母）。
```

- [ ] **Step 1: 写失败测试 - 真实 schema fixture + dev/reuse/final 三阶段 + B1-c 唯一路径**

```python
def _mk_real_detail(cid, arm, stage, ans, dataset="baziqa_contest8_2024_holdout_enriched",
                    expected="A", state="parsed", repeat=0):
    """真实 schema: 无顶层 year/repeat/arm，全部在 attempt_key。"""
    return {"case_id":cid, "predicted_answer":ans, "expected_answer":expected,
            "correct":ans==expected, "dual_stage":stage, "terminal_state":state,
            "attempt_key":[dataset,"prof",arm,stage,"p","m",cid,repeat,0,"p0"]}

def test_parse_detail_identity_real_schema():
    from scripts.phase6_6b2_orchestrator import parse_detail_identity
    r=_mk_real_detail("Q1","dual","bazi","A")
    ident=parse_detail_identity(r)
    assert ident==("2024",0,"Q1","dual","bazi")  # year/repeat/case/arm/stage

def test_gate_dev_promote_real_schema():
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[]
    for year in ["2024","2025"]:
        ds=f"baziqa_contest8_{year}_holdout_enriched"
        for rep in range(3):
            for i in range(40):
                cid=f"{year}_R{rep}_Q{i}"
                da="A" if i<13 else "B"
                details.append(_mk_real_detail(cid,"dual","bazi",da,dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"dual","ziwei",da,dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"b1a_prime","main","B",dataset=ds,repeat=rep))
    g=compute_gate(details, stage="dev")
    assert g["verdict"]=="PROMOTE_CANDIDATE"
    assert g["dual_merged_acc"]>=0.325
    assert g["delta_dev"]>=0.04

def test_gate_dev_fail_absolute_threshold():
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[]
    for year in ["2024","2025"]:
        ds=f"baziqa_contest8_{year}_holdout_enriched"
        for rep in range(3):
            for i in range(40):
                cid=f"{year}_R{rep}_Q{i}"
                da="A" if i<10 else "B"  # 10/40=25%
                details.append(_mk_real_detail(cid,"dual","bazi",da,dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"dual","ziwei",da,dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"b1a_prime","main","B",dataset=ds,repeat=rep))
    g=compute_gate(details, stage="dev")
    assert g["verdict"]=="ROLLBACK"
    assert g["dual_merged_acc"]<0.325

def test_gate_dev_rejects_incomplete_matrix():
    """整个 repeat/arm/year 缺失 -> raise；两臂 case_id 集合不同 -> raise。"""
    import pytest
    from scripts.phase6_6b2_orchestrator import compute_gate
    # 仅 2 repeat（缺 R2）-> raise
    details=[]
    for year in ["2024","2025"]:
        ds=f"baziqa_contest8_{year}_holdout_enriched"
        for rep in range(2):  # 缺 rep=2
            for i in range(40):
                cid=f"{year}_R{rep}_Q{i}"
                details.append(_mk_real_detail(cid,"dual","bazi","A",dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"dual","ziwei","A",dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"b1a_prime","main","B",dataset=ds,repeat=rep))
    with pytest.raises((SystemExit, ValueError)):
        compute_gate(details, stage="dev")

def test_gate_dev_rejects_mismatched_case_sets():
    """两臂 case_id 集合不同 -> raise。"""
    import pytest
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[]
    for year in ["2024","2025"]:
        ds=f"baziqa_contest8_{year}_holdout_enriched"
        for rep in range(3):
            for i in range(40):
                cid_d=f"{year}_R{rep}_D{i}"; cid_b=f"{year}_R{rep}_B{i}"  # 不同 case_id
                details.append(_mk_real_detail(cid_d,"dual","bazi","A",dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid_d,"dual","ziwei","A",dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid_b,"b1a_prime","main","B",dataset=ds,repeat=rep))
    with pytest.raises((SystemExit, ValueError)):
        compute_gate(details, stage="dev")

def test_gate_dev_rejects_missing_cases():
    """某 (year,repeat,arm) 不足 40 case -> raise，不隐式计错。"""
    import pytest
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[_mk_real_detail("Q1","dual","bazi","A")]  # 仅 1 题
    with pytest.raises((SystemExit, ValueError)):
        compute_gate(details, stage="dev")

def test_gate_reuse_pass():
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[]
    for year in ["2021","2022"]:
        ds=f"baziqa_contest8_{year}_holdout_enriched"
        for rep in range(3):
            for i in range(40):
                cid=f"{year}_R{rep}_Q{i}"
                da="A" if i<15 else "B"  # dual 15/40, b1a 0/40 -> Δ=37.5pp>=2pp
                details.append(_mk_real_detail(cid,"dual","bazi",da,dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"dual","ziwei",da,dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"b1a_prime","main","B",dataset=ds,repeat=rep))
    g=compute_gate(details, stage="reuse")
    assert g["verdict"]=="PASS"
    assert g["delta_2021"]>=0.02 and g["delta_2022"]>=0.02

def test_gate_final_2023_confirmed():
    from scripts.phase6_6b2_orchestrator import compute_gate
    ds="baziqa_contest8_2023_holdout_enriched"
    details=[]
    for rep in range(3):
        for i in range(40):
            cid=f"2023_R{rep}_Q{i}"
            da="A" if i<20 else "B"  # Δ=50pp>=0
            details.append(_mk_real_detail(cid,"dual","bazi",da,dataset=ds,repeat=rep))
            details.append(_mk_real_detail(cid,"dual","ziwei",da,dataset=ds,repeat=rep))
            details.append(_mk_real_detail(cid,"b1a_prime","main","B",dataset=ds,repeat=rep))
    g=compute_gate(details, stage="final_2023")
    assert g["verdict"]=="CONFIRMED_PROMOTE"
    assert g["delta_2023"]>=0

def test_gate_final_2023_inconclusive():
    """-5pp < Δ2023 < 0 -> INCONCLUSIVE。"""
    from scripts.phase6_6b2_orchestrator import compute_gate
    ds="baziqa_contest8_2023_holdout_enriched"
    details=[]
    for rep in range(3):
        for i in range(40):
            cid=f"2023_R{rep}_Q{i}"
            # dual 19/40, b1a 21/40 -> Δ=-5pp... 需 -5pp<Δ<0: dual 20/40,b1a 21/40 -> Δ=-2.5pp
            da="A" if i<20 else "B"  # dual 20/40=50%
            ba="A" if i<21 else "B"  # b1a 21/40=52.5%
            details.append(_mk_real_detail(cid,"dual","bazi",da,dataset=ds,repeat=rep))
            details.append(_mk_real_detail(cid,"dual","ziwei",da,dataset=ds,repeat=rep))
            details.append(_mk_real_detail(cid,"b1a_prime","main",ba,dataset=ds,repeat=rep))
    g=compute_gate(details, stage="final_2023")
    assert g["verdict"]=="INCONCLUSIVE"
    assert -0.05 < g["delta_2023"] < 0

def test_gate_final_2023_rollback():
    """Δ2023 <= -5pp -> ROLLBACK。"""
    from scripts.phase6_6b2_orchestrator import compute_gate
    ds="baziqa_contest8_2023_holdout_enriched"
    details=[]
    for rep in range(3):
        for i in range(40):
            cid=f"2023_R{rep}_Q{i}"
            da="A" if i<15 else "B"  # dual 15/40=37.5%
            ba="A" if i<22 else "B"  # b1a 22/40=55%
            details.append(_mk_real_detail(cid,"dual","bazi",da,dataset=ds,repeat=rep))
            details.append(_mk_real_detail(cid,"dual","ziwei",da,dataset=ds,repeat=rep))
            details.append(_mk_real_detail(cid,"b1a_prime","main",ba,dataset=ds,repeat=rep))
    g=compute_gate(details, stage="final_2023")
    assert g["verdict"]=="ROLLBACK"
    assert g["delta_2023"] <= -0.05

def test_gate_final_2023_boundary_exact_negative_5pp():
    """P1: Δ2023 == -5pp 精确边界 -> ROLLBACK（<= -5pp）。"""
    from scripts.phase6_6b2_orchestrator import compute_gate
    ds="baziqa_contest8_2023_holdout_enriched"
    details=[]
    for rep in range(3):
        for i in range(40):
            cid=f"2023_R{rep}_Q{i}"
            da="A" if i<16 else "B"  # dual 16/40=40%
            ba="A" if i<18 else "B"  # b1a 18/40=45%
            details.append(_mk_real_detail(cid,"dual","bazi",da,dataset=ds,repeat=rep))
            details.append(_mk_real_detail(cid,"dual","ziwei",da,dataset=ds,repeat=rep))
            details.append(_mk_real_detail(cid,"b1a_prime","main",ba,dataset=ds,repeat=rep))
    g=compute_gate(details, stage="final_2023")
    # Δ=-5pp 边界 -> ROLLBACK
    assert abs(g["delta_2023"] - (-0.05)) < 0.001
    assert g["verdict"]=="ROLLBACK"

def test_gate_aggregation_consensus_no_judge_row():
    """共识题无 judge 行，按共识计分，不因缺 judge 计错。用完整 40 题矩阵。"""
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[]
    for year in ["2024","2025"]:
        ds=f"baziqa_contest8_{year}_holdout_enriched"
        for rep in range(3):
            for i in range(40):
                cid=f"{year}_R{rep}_Q{i}"
                # Q0 共识 A(对), 其余共识 B(错) -> dual_correct=1/40
                da = "A" if i==0 else "B"
                details.append(_mk_real_detail(cid,"dual","bazi",da,dataset=ds,repeat=rep))
                details.append(_mk_real_detail(cid,"dual","ziwei",da,dataset=ds,repeat=rep))  # 共识，无 judge
                details.append(_mk_real_detail(cid,"b1a_prime","main","B",dataset=ds,repeat=rep))
    g=compute_gate(details, stage="dev")
    # 关键：共识计分正确（dual 1/40=2.5%），不会因缺 judge 计错
    assert g["dual_merged_acc"] == 1/40

def test_b1c_advisory_reads_attempt_key_arm(tmp_path, monkeypatch):
    """B1-c 筛选用 attempt_key[2]，不是顶层 arm。"""
    from scripts.phase6_6b2_orchestrator import load_b1c_advisory
    adv = load_b1c_advisory()
    assert adv["count"]==240  # b1c 真实行数
    assert adv["sha256"]=="10e6b82f92fabd02b7e621b714d330a812f16e6b7aac7ad98adf4a0dd494eafa"

def test_b1c_advisory_fail_closed_on_missing(tmp_path, monkeypatch):
    from scripts.phase6_6b2_orchestrator import load_b1c_advisory
    import pytest
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator.B1C_ARCHIVE_PATH", str(tmp_path/"nope.jsonl"))
    with pytest.raises(SystemExit):
        load_b1c_advisory()
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 parse_detail_identity + compute_gate + load_b1c_advisory**

```python
B1C_ARCHIVE_PATH = "docs/phase6/6b1/6b1-2026-07-17-deepseek-deepseek-chat-78481de6/merged_details.jsonl"
B1C_EXPECTED_SHA256 = "10e6b82f92fabd02b7e621b714d330a812f16e6b7aac7ad98adf4a0dd494eafa"

# parse_detail_identity / _year_from_dataset_id 来自 Task 12（完整性门禁），此处复用
from scripts.phase6_6b2_orchestrator import parse_detail_identity

def compute_gate(merged_details, stage="dev"):
    from collections import defaultdict
    by_key = defaultdict(list)
    for r in merged_details:
        year, rep, cid, arm, stg = parse_detail_identity(r)
        by_key[(year, rep, cid, arm)].append(r)
    # P0-3: 验证完整矩阵（不能只检查已出现的分组）
    expected_years = {"2024","2025"} if stage=="dev" else (
        {"2021","2022"} if stage=="reuse" else {"2023"})
    seen_years = {y for (y,_,_,_) in by_key}
    if seen_years != expected_years:
        raise SystemExit(f"year 集合不匹配: {seen_years} != {expected_years}")
    seen_reps = {rep for (_,rep,_,_) in by_key}
    if seen_reps != {0,1,2}:
        raise SystemExit(f"repeat 集合不完整: {seen_reps} != {{0,1,2}}")
    seen_arms = {arm for (_,_,_,arm) in by_key}
    if seen_arms != {"dual","b1a_prime"}:
        raise SystemExit(f"arm 集合不完整: {seen_arms} != {{dual,b1a_prime}}")
    # 每 (year,repeat,arm) 恰 40 唯一 case
    case_sets = defaultdict(set)
    for (year, rep, cid, arm) in by_key:
        case_sets[(year, rep, arm)].add(cid)
    for (year, rep, arm), cids in case_sets.items():
        if len(cids) != 40:
            raise SystemExit(f"case 数 != 40: {year}/{rep}/{arm} = {len(cids)}")
    # 两臂 case_id 集合完全相同（同年同 repeat）
    for year in expected_years:
        for rep in [0,1,2]:
            dual_ids = case_sets.get((year,rep,"dual"), set())
            b1a_ids = case_sets.get((year,rep,"b1a_prime"), set())
            if dual_ids != b1a_ids:
                raise SystemExit(f"两臂 case_id 集合不同: {year}/{rep}")
    # 聚合（同前）
    acc = defaultdict(lambda: {"dual_correct":0, "b1a_correct":0})
    years_seen = expected_years
    for (year, rep, cid, arm), rows in by_key.items():
        if arm == "b1a_prime":
            acc[(year, rep)]["b1a_correct"] += 1 if rows[0]["correct"] else 0
        elif arm == "dual":
            # stage 统一从 attempt_key[3] 解析（同 P0-1，真实 detail 行无顶层 dual_stage）
            b = next((r for r in rows if (r.get("attempt_key") or [None]*10)[3]=="bazi"), None)
            z = next((r for r in rows if (r.get("attempt_key") or [None]*10)[3]=="ziwei"), None)
            j = next((r for r in rows if (r.get("attempt_key") or [None]*10)[3]=="judge"), None)
            if b and z and b["predicted_answer"] is not None and z["predicted_answer"] is not None \
               and b["predicted_answer"]==z["predicted_answer"]:
                final = b["predicted_answer"]
            elif j:
                final = j["predicted_answer"]
            else:
                final = None
            expected = (b or z)["expected_answer"]
            acc[(year, rep)]["dual_correct"] += 1 if final==expected else 0
    delta_yr_rep = {}
    for (year, rep), v in acc.items():
        da = v["dual_correct"]/40; ba = v["b1a_correct"]/40
        delta_yr_rep[(year, rep)] = da - ba
    years = sorted(years_seen)

    if stage == "dev":
        delta_year = {y: sum(d for (yy,_),d in delta_yr_rep.items() if yy==y)/3 for y in years}
        delta_dev = sum(delta_year.values())/len(years)
        dual_total = 40 * len(years) * 3
        dual_merged_acc = sum(v["dual_correct"] for v in acc.values())/dual_total
        min_year = min(delta_year.values())
        verdict = "PROMOTE_CANDIDATE" if (delta_dev>=0.04 and dual_merged_acc>=0.325 and min_year>=-0.02) else "ROLLBACK"
        return {"verdict":verdict,"delta_dev":delta_dev,"dual_merged_acc":dual_merged_acc,
                "min_year_delta":min_year,"delta_by_year":delta_year,
                "delta_by_year_repeat":delta_yr_rep,"stage":stage}
    elif stage == "reuse":
        delta_year = {y: sum(d for (yy,_),d in delta_yr_rep.items() if yy==y)/3 for y in years}
        verdict = "PASS" if all(d>=0.02 for d in delta_year.values()) else "FAIL"
        return {"verdict":verdict,"delta_by_year":delta_year,
                "delta_2021":delta_year.get("2021"),"delta_2022":delta_year.get("2022"),"stage":stage}
    elif stage == "final_2023":
        delta_year = {y: sum(d for (yy,_),d in delta_yr_rep.items() if yy==y)/3 for y in years}
        d2023 = delta_year.get("2023", -1.0)
        if d2023 >= 0:
            verdict = "CONFIRMED_PROMOTE"
        elif d2023 > -0.05:
            verdict = "INCONCLUSIVE"
        else:
            verdict = "ROLLBACK"
        return {"verdict":verdict,"delta_2023":d2023,"stage":stage}
    else:
        raise SystemExit(f"unknown stage: {stage}")

def load_b1c_advisory():
    import hashlib, os, json
    path = B1C_ARCHIVE_PATH
    if not os.path.exists(path):
        raise SystemExit(f"B1-c 归档不存在: {path} (fail-closed)")
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    if sha != B1C_EXPECTED_SHA256:
        raise SystemExit(f"B1-c SHA-256 不匹配: {sha} != {B1C_EXPECTED_SHA256} (fail-closed)")
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    b1c = [r for r in rows if r.get("attempt_key",[None]*10)[2] == "b1c"]
    return {"path":path, "sha256":sha, "count":len(b1c), "rows":b1c}
```

**generate_report 接口与实现（v11 补全，替换原一行说明）**：

```python
def generate_report(gate: dict, merged_details: list, schedule: dict,
                    ledger, b1c_advisory: dict, out_dir) -> dict:
    """6B2 报告：准确率表、Δ 表、gate 裁决、judge 触发率、parser rate、完整性、预算、
    B1-c advisory 对照（描述性，非决策）。返回报告 dict 并写 out_dir/report.md + summary.json。"""
    rows = merged_details
    total = max(len(rows), 1)
    parsed = sum(1 for r in rows if r.get("terminal_state") == "parsed")
    judge_rows = [r for r in rows if (r.get("attempt_key") or [None] * 10)[3] == "judge"]
    # v13：分母含 year（attempt_key[0] 数据集名含年份）——跨年同名题不得合并
    dual_cells = {(str(r.get("attempt_key", [None])[0]),
                   (r.get("attempt_key") or [None] * 10)[7],
                   r.get("case_id"))
                  for r in rows if (r.get("attempt_key") or [None] * 10)[2] == "dual"}
    report = {
        "run": {"slices": len(schedule["slices"]),
                "scheduled": schedule["total_scheduled_calls"],
                "attempted": ledger.total_attempted,      # int 属性，非方法（P0-3 修订）
                "global_hard_cap": ledger.hard_cap},
        "gate": gate,
        "accuracy": _accuracy_final(rows),
        "delta": {k: v for k, v in gate.items() if k.startswith(("delta", "min_year"))},
        "judge": {"trigger_rate": round(len(judge_rows) / max(len(dual_cells), 1), 4),
                  "reference_disagreement_rate": JUDGE_DISAGREEMENT_RATE,
                  "judge_calls": len(judge_rows)},
        "parser_rate": round(parsed / total, 4),
        "integrity": {"rows": total, "call_failed": sum(
            1 for r in rows if r.get("terminal_state") == "call_failed")},
        "b1c_advisory": {"count": b1c_advisory["count"], "sha256": b1c_advisory["sha256"],
                         "note": "非同时段比较 + provider drift 风险，描述性附列，非预注册 gate"},
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    lines = [f"# 6B2 双管线报告",
             f"- gate：**{gate['verdict']}**（{gate.get('stage')}）",
             f"- judge 触发率：{report['judge']['trigger_rate']}（参照 {JUDGE_DISAGREEMENT_RATE}）",
             f"- parser rate：{report['parser_rate']}；call_failed：{report['integrity']['call_failed']}",
             f"- 预算：scheduled {report['run']['scheduled']} / attempted {report['run']['attempted']}"
             f" / cap {report['run']['global_hard_cap']}",
             f"- B1-c advisory（非决策）：{report['b1c_advisory']['note']}",
             "", "如实声明：40 题/年度，2 题即 5pp；请求不携带 seed；B1-c 为 6B1 时段旧 run。"]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def _accuracy_final(rows: list) -> dict:
    """准确率口径（P0-3 + v13 修订）：dual 按 compute_gate 同口径取每格最终答案
    （共识→bazi 答案；分歧→judge 答案；双侧 unresolved→不计对），B1-a′ 按 main 行。
    聚合键含 year（attempt_key[0] 数据集名含年份）——2024/2025 复用 Q1-Q40，
    按 (case,repeat) 会跨年覆盖（240 格被压成 120）。"""
    import re

    def _ident(r):
        ak = r.get("attempt_key") or [None] * 10
        m = re.search(r"(20\d\d)", str(ak[0]))
        return (m.group(1) if m else "unknown"), ak[7], ak[3]

    b1a_rows = [r for r in rows if _ident(r)[2] == "main"]
    b1a_acc = round(sum(bool(r.get("correct")) for r in b1a_rows) / max(len(b1a_rows), 1), 4)
    cells = {}
    for r in rows:
        ak = r.get("attempt_key") or [None] * 10
        if ak[2] != "dual":
            continue
        year, rep, stage = _ident(r)
        cells.setdefault((year, rep, r.get("case_id")), {})[stage] = r
    n_ok = 0
    for cell in cells.values():
        b, z, j = cell.get("bazi"), cell.get("ziwei"), cell.get("judge")
        if b and z and b.get("predicted_answer") \
                and b["predicted_answer"] == z.get("predicted_answer"):
            final = b["predicted_answer"]
        elif j:
            final = j.get("predicted_answer")
        else:
            final = None
        exp = (b or z)["expected_answer"]
        n_ok += (final is not None and final == exp)
    return {"dual_final_accuracy": round(n_ok / max(len(cells), 1), 4),
            "dual_cases": len(cells),
            "b1a_accuracy": b1a_acc, "b1a_rows": len(b1a_rows)}
```

**generate_report 测试（追加到 `tests/test_phase6_6b2.py`）**：

```python
class TestGenerateReport:
    def test_report_fields_and_files(self, tmp_path):
        # c0 共识（A==A→对）；c1 分歧（judge=B 错）；2 条 B1-a′ main 行（1 对 1 错）
        rows = [_stage_row("c0", "bazi", "A"), _stage_row("c0", "ziwei", "A"),
                _stage_row("c1", "bazi", "A"), _stage_row("c1", "ziwei", "B"),
                _stage_row("c1", "judge", "B"),
                _stage_row("c0", "main", "A", arm="b1a_prime"),
                _stage_row("c1", "main", "B", arm="b1a_prime")]
        gate = {"verdict": "ROLLBACK", "stage": "dev", "delta_dev": -0.02}
        sched = {"slices": [{}] * 60, "total_scheduled_calls": 960}
        ledger = type("L", (), {"total_attempted": 960, "hard_cap": 1060})()  # int 属性
        rep = generate_report(gate, rows, sched, ledger,
                              {"count": 240, "sha256": "x", "rows": []}, tmp_path)
        assert rep["gate"]["verdict"] == "ROLLBACK"
        assert rep["run"]["scheduled"] == 960 and rep["run"]["attempted"] == 960
        assert rep["judge"]["judge_calls"] == 1 and rep["judge"]["trigger_rate"] == 0.5
        assert rep["parser_rate"] == 1.0
        assert rep["accuracy"]["dual_cases"] == 2
        assert rep["accuracy"]["dual_final_accuracy"] == 0.5   # c0 对 / c1 judge=B 错
        assert rep["accuracy"]["b1a_accuracy"] == 0.5 and rep["accuracy"]["b1a_rows"] == 2
        assert "非同时段" in rep["b1c_advisory"]["note"]
        assert (tmp_path / "summary.json").exists() and (tmp_path / "report.md").exists()
```

（`_stage_row` 复用 Task 14 定义的夹具；`_accuracy_final` 为模块内私有助手，与 generate_report 同任务交付。）

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): gate (3-stage parameterized + real schema identity) + B1-c advisory (frozen SHA)`

---

## Task 14: smoke gate + 集成测试

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**设计**：真实实验启动门禁——smoke 切片（group_a 前 2 题）先跑通 bazi→ziwei→judge 链路，
ziwei 覆盖 100% 且 parser rate ≥95% 才允许主调度；smoke 状态机与 6B1D 同型
（`fresh/resume/completed/blocked_corrupt`，复用其 OutputDirLock 语义）。

- [ ] **Step 1: 写失败测试（完整代码）**

```python
import json
import pytest

from scripts.phase6_6b2_orchestrator import (
    determine_smoke_state,
    verify_smoke_completed,
)


def _stage_row(cid, stage, ans, terminal="parsed", arm="dual"):
    return {"case_id": cid, "predicted_answer": ans, "expected_answer": "A",
            "correct": ans == "A", "terminal_state": terminal,
            "attempt_key": ["ds", "baziqa_xjz_dual", arm, stage, "p", "m", cid, 0, 0, "p0"]}


def _write_smoke(smoke_dir, rows):
    smoke_dir.mkdir(parents=True, exist_ok=True)
    (smoke_dir / "detail.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


class TestSmokeGate:
    """smoke 状态机 + 完成校验 + parser rate 门禁（启动真实实验前置）。"""

    def test_state_fresh_when_no_dir(self, tmp_path):
        assert determine_smoke_state(tmp_path / "smoke") == "fresh"

    def test_state_resume_when_partial(self, tmp_path):
        _write_smoke(tmp_path / "smoke", [_stage_row("c0", "bazi", "A")])
        assert determine_smoke_state(tmp_path / "smoke") == "resume"

    def test_state_blocked_corrupt_on_bad_jsonl(self, tmp_path):
        (tmp_path / "smoke").mkdir()
        (tmp_path / "smoke" / "detail.jsonl").write_text("{bad json\n", encoding="utf-8")
        assert determine_smoke_state(tmp_path / "smoke") == "blocked_corrupt"

    def test_completed_and_verify_pass(self, tmp_path):
        rows = [_stage_row("c0", "bazi", "A"), _stage_row("c0", "ziwei", "A"),
                _stage_row("c1", "bazi", "A"), _stage_row("c1", "ziwei", "B"),
                _stage_row("c1", "judge", "B")]
        _write_smoke(tmp_path / "smoke", rows)
        # v13：completed 需每题 bazi+ziwei 齐全（传入 expected ids）
        assert determine_smoke_state(tmp_path / "smoke",
                                     expected_case_ids=["c0", "c1"]) == "completed"
        result = verify_smoke_completed(tmp_path / "smoke", expected_case_ids=["c0", "c1"])
        assert result["parser_rate"] == 1.0            # 5/5 parsed
        assert result["ziwei_coverage"] == 1.0         # 2/2 case 有 ziwei 行
        assert result["stages"] == {"bazi": 2, "ziwei": 2, "judge": 1}

    def test_partial_completion_is_resume_not_completed(self, tmp_path):
        # v13：c1 缺 ziwei（崩溃现场）→ resume，不得判 completed
        rows = [_stage_row("c0", "bazi", "A"), _stage_row("c0", "ziwei", "A"),
                _stage_row("c1", "bazi", "A")]
        _write_smoke(tmp_path / "smoke", rows)
        assert determine_smoke_state(tmp_path / "smoke",
                                     expected_case_ids=["c0", "c1"]) == "resume"

    def test_call_failed_blocks_smoke(self, tmp_path):
        # v13：存在 call_failed（基础设施污染）即拒，即使 ziwei 行存在、其余全 parsed
        rows = [_stage_row("c0", "bazi", "A"), _stage_row("c0", "ziwei", "A"),
                _stage_row("c1", "bazi", "A", terminal="call_failed"),
                _stage_row("c1", "ziwei", "B")]
        _write_smoke(tmp_path / "smoke", rows)
        with pytest.raises(SystemExit, match="call_failed"):
            verify_smoke_completed(tmp_path / "smoke", expected_case_ids=["c0", "c1"])

    def test_parser_rate_below_95_blocked(self, tmp_path):
        # 20 行中 2 行 invalid → (parsed+call_failed)/total = 18/20 = 0.9 < 0.95 → BLOCKED
        rows = [_stage_row(f"c{i%2}", "bazi" if i % 3 == 0 else "ziwei", "A",
                           terminal="invalid" if i in (0, 1) else "parsed")
                for i in range(20)]
        _write_smoke(tmp_path / "smoke", rows)
        with pytest.raises(SystemExit, match="parser rate"):
            verify_smoke_completed(tmp_path / "smoke", expected_case_ids=["c0", "c1"])

    def test_ziwei_coverage_incomplete_blocked(self, tmp_path):
        rows = [_stage_row("c0", "bazi", "A"), _stage_row("c1", "bazi", "A")]  # 无 ziwei 行
        _write_smoke(tmp_path / "smoke", rows)
        with pytest.raises(SystemExit, match="ziwei"):
            verify_smoke_completed(tmp_path / "smoke", expected_case_ids=["c0", "c1"])


def _mk_case(cid):
    """最小合法 BaziQA 赛题夹具（reasoned direct/dual 通用；若与 Task 6 实际消费字段
    形状不一致，以 Task 6 夹具为准替换并在 commit 登记）。"""
    return {"case_id": cid, "domain": "wealth",
            "question": f"{cid} 的财运判断？", "options": {"A": "吉", "B": "凶", "C": "平", "D": "无"},
            "answer": "A", "chart_input": {}}


class TestDualIntegration:
    """mock call_model_sync 跑 2 case（共识+分歧）：读取落盘 detail.jsonl 验证
    stage 行数、attempt_key[3]、最终答案（v12：fake 输出 reasoned 格式）。"""

    def test_two_cases_consensus_and_divergence(self, tmp_path, monkeypatch):
        import benchmark.runners.run_benchmark as rb, json
        answers = {"bazi": {"c0": "A", "c1": "A"},
                   "ziwei": {"c0": "A", "c1": "B"},
                   "judge": {"c1": "B"}}

        def fake_call(prompt, provider, model, case=None, **kw):
            stage = rb._PHASE6_CTX.attempt_stage
            cid = case.get("case_id") if case else None
            ans = answers.get(stage, {}).get(cid, "A")
            # reasoned_choice 输出协议（chart_context.py:337 parser 要求"最终答案：X"行）
            return f"分析：{stage} 测试理由。\n最终答案：{ans}"

        monkeypatch.setattr(rb, "call_model_sync", fake_call)
        cases = [_mk_case("c0"), _mk_case("c1")]
        detail_path = tmp_path / "detail.jsonl"
        # v13：先初始化 Phase6Context（fake_call 与落盘 enrich 都依赖 _PHASE6_CTX）；
        # v14：finally 复位 None，避免全局上下文污染后续测试（中优）
        rb.init_phase6_context(rb.Phase6Context(
            "ds", "baziqa_xjz_dual", "dual", "main", "deepseek", "deepseek-chat",
            0, str(detail_path), str(tmp_path / "detail.events.jsonl"), 12, 20, resume=False))
        try:
            rb.run_dual_system_benchmark(cases, "deepseek", "deepseek-chat",
                                         case_details_jsonl=str(detail_path))
        finally:
            rb.init_phase6_context(None)
        # result["case_details"] 是 case 级汇总；stage 明细从落盘 detail.jsonl 读取
        rows = [json.loads(l) for l in detail_path.read_text(encoding="utf-8").splitlines()
                if l.strip()]
        stages = [(r.get("attempt_key") or [None] * 10)[3] for r in rows]
        # c0 共识（bazi==ziwei=="A"）无 judge；c1 分歧（A vs B）调 judge 一次
        assert stages == ["bazi", "ziwei", "bazi", "ziwei", "judge"]
        assert [r["predicted_answer"] for r in rows] == ["A", "A", "A", "B", "B"]
        assert rows[-1]["case_id"] == "c1"
        assert all(r["terminal_state"] == "parsed" for r in rows)
```

（`call_model_sync` 的 stage 读取路径以 Task 6 实际实现为准——若 Task 6 不经 `_PHASE6_CTX.attempt_stage` 而是参数传递 stage，fake_call 改从 `kw` 取并在 commit 登记。）

- [ ] **Step 2: 实现 smoke gate（完整代码）**

```python
SMOKE_CASES_PER_GROUP = 2
SMOKE_PARSER_RATE_MIN = 0.95


def determine_smoke_state(smoke_dir, expected_case_ids=None) -> str:
    """smoke 状态机（v13 修订）：completed 仅当**每题** bazi+ziwei 各恰 1 行
    （judge 按分歧基数可选）——旧逻辑"出现任意 ziwei 行即完成"会把
    第一题 ziwei 后崩溃的现场误判为完成，随后验证失败且无法自动 resume。"""
    smoke_dir = Path(smoke_dir)
    detail = smoke_dir / "detail.jsonl"
    if not detail.exists():
        return "fresh"
    try:
        rows = [json.loads(l) for l in detail.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "blocked_corrupt"
    if not rows or expected_case_ids is None:
        return "resume" if rows else "fresh"
    per_case = {}
    for r in rows:
        per_case.setdefault(r.get("case_id"), set()).add((r.get("attempt_key") or [None] * 10)[3])
    for cid in expected_case_ids:
        if not ({"bazi", "ziwei"} <= per_case.get(cid, set())):
            return "resume"
    return "completed"


def verify_smoke_completed(smoke_dir, expected_case_ids: list) -> dict:
    """smoke 完成校验（v13 修订）：ziwei 覆盖 100%；任何 call_failed 即拒
    （基础设施污染，排查后续跑——不得计入 parser 成功率）；parser rate =
    parsed / (总行数 − call_failed) ≥ 0.95（invalid/unresolved/judge_unresolved 计失败）。
    不过 → SystemExit（真实实验启动门禁，BLOCKED 不得进入主调度）。"""
    smoke_dir = Path(smoke_dir)
    detail = smoke_dir / "detail.jsonl"
    if not detail.exists():
        raise SystemExit("smoke 拒绝: detail.jsonl 缺失")
    rows = [json.loads(l) for l in detail.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        raise SystemExit("smoke 拒绝: detail.jsonl 为空")
    stages = {}
    ziwei_cases = set()
    parsed = 0
    failed = 0
    for r in rows:
        stage = (r.get("attempt_key") or [None] * 10)[3]
        stages[stage] = stages.get(stage, 0) + 1
        if stage == "ziwei":
            ziwei_cases.add(r.get("case_id"))
        if r.get("terminal_state") == "parsed":
            parsed += 1
        elif r.get("terminal_state") == "call_failed":
            failed += 1
    coverage = len(ziwei_cases) / max(len(expected_case_ids), 1)
    if coverage < 1.0:
        raise SystemExit(f"smoke 拒绝: ziwei 覆盖不足 {coverage:.2%}（每题必须有 ziwei 行）")
    if failed:
        raise SystemExit(f"smoke 拒绝: 存在 {failed} 条 call_failed（基础设施污染）")
    rate = round(parsed / max(len(rows) - failed, 1), 4)
    if rate < SMOKE_PARSER_RATE_MIN:
        raise SystemExit(f"smoke 拒绝: parser rate {rate} < {SMOKE_PARSER_RATE_MIN}")
    return {"parser_rate": rate, "ziwei_coverage": coverage, "stages": stages,
            "rows": len(rows), "status": "OK"}
```

- [ ] **Step 3: 运行确认全绿**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_phase6_6b2.py -q -k "SmokeGate or DualIntegration"`
Expected: 9 passed（TestSmokeGate 8 + TestDualIntegration 1；既有用例不受影响）

- [ ] **Step 4: Commit（精确路径）**

```powershell
git add scripts/phase6_6b2_orchestrator.py tests/test_phase6_6b2.py
git commit -m "feat(6b2): smoke gate (state machine + ziwei coverage + parser rate) + dual integration test"
```

---

## Task 15: enrichment + 2023 密封终验（P0-3 修订：RUNNING/FINALIZED 状态机）

**Files:** Create `scripts/phase6_6b2_sealed_workflow.py`; Test `tests/test_phase6_6b2.py`

**P0-3：** 2021/2022 可提前 enrichment；2023 enrichment 在复用验证通过后才执行；2023 锁改 RUNNING/FINALIZED，RUNNING 仅允许完全匹配 resume；lock 在读 2023 数据前原子写入。

- [ ] **Step 1: 写测试 - enrichment 产出 + 覆盖率门禁**

```python
def test_enrichment_produces_chart_input():
    from scripts.enrich_holdout_chart_input import enrich_row
    row={"case_id":"Q1","person":{"name":"t","birth":{"year":1990,"month":1,"day":1,"hour":12,"place":"北京"}},"answer":"A","question":"q","options":["a","b","c","d"]}
    out=enrich_row(row)
    assert out.get("chart_input") is not None
    assert out["chart_input"].get("ziwei") is not None

def test_enrich_year_2021_succeeds_full_coverage(tmp_path):
    """真实 2021 holdout enrichment 产出 40/40 chart_input + ziwei（已验证）。"""
    from scripts.phase6_6b2_sealed_workflow import enrich_year
    result = enrich_year("2021",
        "benchmark/datasets/baziqa_contest8_2021_holdout.jsonl",
        str(tmp_path/"out_2021.jsonl"))
    assert result["rows"]==40
    assert result["ziwei_coverage"]==40

def test_enrich_year_rejects_synthetic_missing_ziwei(tmp_path, monkeypatch):
    """合成缺 ziwei 的 fixture -> 覆盖率门禁拒绝。"""
    from scripts.phase6_6b2_sealed_workflow import enrich_year
    import scripts.enrich_holdout_chart_input as eh, pytest, json
    # 构造 2 行：1 行有 ziwei，1 行无
    src = tmp_path/"src.jsonl"
    src.write_text("\n".join([
        json.dumps({"case_id":"Q1","person":{"name":"t","birth":{"year":1990,"month":1,"day":1,"hour":12,"place":"北京"}},"answer":"A","question":"q","options":["a","b","c","d"]}),
        json.dumps({"case_id":"Q2","person":{"name":"t","birth":{"year":1990,"month":1,"day":1,"hour":12,"place":"北京"}},"answer":"A","question":"q","options":["a","b","c","d"]}),
    ]), encoding="utf-8")
    # monkeypatch enrich_row 使 Q2 无 ziwei
    real_enrich = eh.enrich_row
    def patched(row):
        out = real_enrich(row)
        if row.get("case_id")=="Q2":
            out["chart_input"] = {"ziwei": None}
        return out
    monkeypatch.setattr(eh, "enrich_row", patched)
    with pytest.raises(SystemExit):
        enrich_year("2021", str(src), str(tmp_path/"out.jsonl"))
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 enrichment（无占位符）**

```python
# scripts/phase6_6b2_sealed_workflow.py
from __future__ import annotations
import hashlib,json,os,inspect,datetime
from pathlib import Path

def _sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(8192),b""): h.update(chunk)
    return h.hexdigest()

def _sha256_func(fn):
    return hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()

def _now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

def enrich_year(year,input_path,output_path):
    from scripts.enrich_holdout_chart_input import enrich_row,load_jsonl,write_jsonl
    rows=[enrich_row(r) for r in load_jsonl(input_path)]
    write_jsonl(output_path,rows)
    has_zw=sum(1 for r in rows if r.get("chart_input",{}).get("ziwei"))
    if has_zw<len(rows):
        raise SystemExit(f"enrichment 覆盖率不足: {has_zw}/{len(rows)}")
    return {"year":year,"input_sha256":_sha256_file(input_path),
            "output_sha256":_sha256_file(output_path),
            "code_sha256":_sha256_func(enrich_row),"rows":len(rows),"ziwei_coverage":has_zw}
```

- [ ] **Step 4: 写测试 - 阶段准入**

```python
def test_dev_promote_required_before_reuse(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import check_stage_gate
    import pytest
    with pytest.raises(SystemExit):
        check_stage_gate("reuse", gate_root=str(tmp_path))

def test_reuse_pass_required_before_2023(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import check_stage_gate
    import pytest,json
    (tmp_path/"dev_gate.json").write_text(json.dumps({"verdict":"PROMOTE_CANDIDATE"}))
    with pytest.raises(SystemExit):
        check_stage_gate("final_2023", gate_root=str(tmp_path))
```

- [ ] **Step 5: 实现 阶段准入 + 2023 RUNNING/FINALIZED 状态机（P0-3/P0-4 修订）**

**P0-3：** `acquire_2023_run_lock` 用**预登记 SHA**（不读文件），打破循环依赖。流程：预登记 SHA 获取 RUNNING -> 读文件验证原始 SHA -> enrichment 后记派生 SHA -> 任一不匹配 BLOCKED。
**P0-4：** `finalize_2023_run_lock` 必须验证 schedule 完整 + integrity gate + archive 已发布 + 哈希一致后，原子切换 FINALIZED；归档失败保持 RUNNING。

```python
# 2023 原始数据集预登记 SHA-256（已核验：sha256(baziqa_contest8_2023_holdout.jsonl)）
BLESSED_2023_RAW_SHA256 = "8933783ef7da9084adeb0a9940d12277de6a1c3def41374f836bec48c4afcd3d"

def _load_gate(path):
    p=Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

RECEIPT_REQUIRED_FIELDS = ("verdict", "stage", "run_id", "archive_dir",
                           "audit_index_sha256", "provider", "model",
                           "code_fingerprint", "dataset_sha256")


def check_stage_gate(stage, gate_root="docs/phase6/6b2", provider=None, model=None,
                     current_code_fingerprint=None):
    """阶段准入（v16 字段级强化 + 接线修正）：必需字段完整、stage 一致、
    archive/audit_index 存在、audit SHA 与 receipt 一致、receipt↔audit run_id 与
    code_fingerprint 交叉一致、provider/model 与当前请求一致、code fingerprint 与
    当前代码一致、verdict 满足准入。stale receipt 一律拒绝。

    v16：current_code_fingerprint 由调用方显式传入（sealed_workflow 不反向 import
    orchestrator，避免循环依赖——orchestrator 侧调用时传
    `_compute_experiment_code_fingerprint()`；orchestrator 内
    `from scripts.phase6_6b2_sealed_workflow import check_stage_gate`）。
    生产调用必须传 provider/model。返回已验证 receipt（dict）或 SystemExit。"""
    r = Path(gate_root)

    def _validate_receipt(name, expect_stage, expect_verdicts):
        path = r / name
        if not path.exists():
            raise SystemExit(f"{expect_stage} receipt 缺失: {path}")
        rec = json.loads(path.read_text(encoding="utf-8"))
        missing = [k for k in RECEIPT_REQUIRED_FIELDS if k not in rec]
        if missing:
            raise SystemExit(f"{expect_stage} receipt 缺字段 {missing}")
        if rec["stage"] != expect_stage:
            raise SystemExit(f"receipt stage 不符: {rec['stage']} != {expect_stage}")
        if rec["verdict"] not in expect_verdicts:
            raise SystemExit(f"{expect_stage} 未通过 ({rec.get('verdict')})")
        archive_dir = Path(rec["archive_dir"])
        audit_path = archive_dir / "audit_index.json"
        if not archive_dir.exists() or not audit_path.exists():
            raise SystemExit(f"{expect_stage} 归档或 audit_index.json 缺失")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if _sha256_file(str(audit_path)) != rec["audit_index_sha256"]:
            raise SystemExit(f"{expect_stage} audit SHA 与 receipt 不一致")
        if audit.get("code_fingerprint") != rec["code_fingerprint"]:
            raise SystemExit(f"{expect_stage} receipt 与 audit 代码指纹交叉不一致")
        if audit.get("run_id") != rec["run_id"]:
            raise SystemExit(f"{expect_stage} audit.run_id ({audit.get('run_id')}) != receipt.run_id ({rec['run_id']})")
        if audit.get("stage") != rec["stage"]:
            raise SystemExit(f"{expect_stage} audit.stage ({audit.get('stage')}) != receipt.stage ({rec['stage']})")
        if audit.get("provider") != rec.get("provider"):
            raise SystemExit(f"{expect_stage} audit.provider ({audit.get('provider')}) != receipt.provider ({rec.get('provider')})")
        if audit.get("model") != rec.get("model"):
            raise SystemExit(f"{expect_stage} audit.model ({audit.get('model')}) != receipt.model ({rec.get('model')})")
        if audit.get("gate_verdict") != rec.get("verdict"):
            raise SystemExit(f"{expect_stage} audit.gate_verdict ({audit.get('gate_verdict')}) != receipt.verdict ({rec.get('verdict')})")
        if provider and rec["provider"] != provider:
            raise SystemExit(f"{expect_stage} provider 不一致: {rec['provider']} != {provider}")
        if model and rec["model"] != model:
            raise SystemExit(f"{expect_stage} model 不一致: {rec['model']} != {model}")
        if current_code_fingerprint and rec["code_fingerprint"] != current_code_fingerprint:
            raise SystemExit(f"{expect_stage} receipt 代码指纹与当前代码不一致")
        return rec

    if stage == "reuse":
        return _validate_receipt("dev_gate.json", "dev", ("PROMOTE_CANDIDATE",))
    elif stage == "final_2023":
        dev_rec = _validate_receipt("dev_gate.json", "dev", ("PROMOTE_CANDIDATE",))
        reuse_rec = _validate_receipt("reuse_gate.json", "reuse", ("PASS",))
        return {"dev": dev_rec, "reuse": reuse_rec}

def acquire_2023_run_lock(lock_path, run_id, code_fingerprint, schedule_hash,
                          budget_hard_cap=None):
    """用冻结常量 BLESSED_2023_RAW_SHA256 + O_CREAT|O_EXCL 原子排他获取 RUNNING。

    复用 6B1D OutputDirLock 的原子创建机制（os.open O_EXCL）。
    不接受调用方传入 raw_sha（强制使用冻结常量，防止篡改）。
    RUNNING+完全匹配 -> RESUME；FINALIZED -> 拒绝；不匹配 -> 拒绝。
    """
    lp=Path(lock_path)
    if lp.exists():
        st=json.loads(lp.read_text(encoding="utf-8"))
        if st.get("status")=="FINALIZED":
            raise SystemExit("2023 已 FINALIZED, 禁止重跑（密封终验）")
        if st.get("status")=="RUNNING":
            # P0-4: 不检查 schedule_hash（它在锁获取后才设置，RESUME 时必然不匹配传入的 ""）。
            # run_id + code_fingerprint + raw_sha256 已足够恢复验证。
            if (st.get("run_id")==run_id and st.get("raw_sha256")==BLESSED_2023_RAW_SHA256
                and st.get("code_fingerprint")==code_fingerprint):
                return "RESUME"
            raise SystemExit("2023 RUNNING 但指纹不匹配, 禁止恢复")
    # 原子排他创建（O_CREAT|O_EXCL），失败说明被其他进程抢
    lp.parent.mkdir(parents=True,exist_ok=True)
    import os as _os
    payload=dict(status="RUNNING",run_id=run_id,
        raw_sha256=BLESSED_2023_RAW_SHA256,
        code_fingerprint=code_fingerprint,schedule_hash=schedule_hash,
        started_at=_now_iso())
    if budget_hard_cap is not None:
        payload["budget_hard_cap"] = budget_hard_cap
    try:
        fd=_os.open(str(lp), _os.O_CREAT|_os.O_EXCL|_os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("2023 锁已被其他进程持有 (fail-closed)")
    with _os.fdopen(fd,"w",encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False))
    return "NEW"

def verify_2023_raw_data(raw_path, pre_blessed_sha):
    """RUNNING 锁成功后读取并验证原始数据 SHA。不匹配 -> BLOCKED。"""
    actual=_sha256_file(raw_path)
    if actual != pre_blessed_sha:
        raise SystemExit(f"2023 原始数据 SHA 不匹配: {actual} != {pre_blessed_sha} (BLOCKED)")

def record_enriched_sha_to_lock(lock_path, enriched_path):
    """enrichment 完成后，将派生文件 SHA 写回 RUNNING 锁。

    P0-5: RESUME 时若锁中已有 enriched_sha256，验证现有文件一致，
    不能重新生成并覆盖锁中 SHA。P1: 必须验证锁处于 RUNNING。
    """
    lp=Path(lock_path)
    st=json.loads(lp.read_text(encoding="utf-8"))
    if st.get("status") != "RUNNING":
        raise SystemExit(f"record_enriched 拒绝: 锁非 RUNNING (当前 {st.get('status')})")
    new_sha = _sha256_file(enriched_path)
    existing_sha = st.get("enriched_sha256")
    if existing_sha is not None:
        # RESUME 分支：验证现有文件一致，不覆盖锁中 SHA
        if new_sha != existing_sha:
            raise SystemExit(f"record_enriched 拒绝: enriched SHA 不一致 (现有 {existing_sha} != 新 {new_sha})")
        return  # 一致则跳过写入
    st["enriched_sha256"] = new_sha
    tmp=lp.with_suffix(".tmp")
    tmp.write_text(json.dumps(st,ensure_ascii=False),encoding="utf-8")
    os.replace(tmp,lp)

def finalize_2023_run_lock(lock_path, archive_path, gate_verdict,
                           schedule_complete, integrity_passed):
    """事务闭环：验证锁 RUNNING + schedule + integrity + archive 存在 +
    audit_index 内容与锁一致（run_id/stage/code_fp/sched_hash/gate_verdict）+
    重算 audit_index SHA 后，原子切换 FINALIZED。任一失败保持 RUNNING。"""
    if not schedule_complete:
        raise SystemExit("finalize 拒绝: schedule 未完整 (保持 RUNNING)")
    if not integrity_passed:
        raise SystemExit("finalize 拒绝: integrity gate 未通过 (保持 RUNNING)")
    archive_path = Path(archive_path)
    audit_path = archive_path / "audit_index.json"
    if not audit_path.exists():
        raise SystemExit("finalize 拒绝: archive/audit_index.json 不存在 (保持 RUNNING)")
    audit_sha = _sha256_file(str(audit_path))
    lp=Path(lock_path)
    st=json.loads(lp.read_text(encoding="utf-8"))
    if st.get("status") != "RUNNING":
        raise SystemExit(f"finalize 拒绝: 锁非 RUNNING (当前 {st.get('status')})")
    # P0-6: 验证 audit_index 内容与 RUNNING 锁一致（run_id/sched_hash/code_fp/dataset_hashes/budget）
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    # P0-5: 精确匹配 run_id（去除 ds_prefix 后 lock 与 archive 格式一致）
    if audit.get("run_id") != st.get("run_id"):
        raise SystemExit(f"finalize 拒绝: audit run_id={audit.get('run_id')} != 锁 {st.get('run_id')}")
    if audit.get("stage") != "final_2023":
        raise SystemExit(f"finalize 拒绝: audit stage={audit.get('stage')} != final_2023")
    if audit.get("gate_verdict") != gate_verdict:
        raise SystemExit(f"finalize 拒绝: audit gate_verdict={audit.get('gate_verdict')} != {gate_verdict}")
    if audit.get("code_fingerprint") != st.get("code_fingerprint"):
        raise SystemExit("finalize 拒绝: audit code_fingerprint 与锁不一致")
    if audit.get("sched_hash") != st.get("schedule_hash"):
        raise SystemExit("finalize 拒绝: audit sched_hash 与锁不一致")
    raw_hashes = audit.get("dataset_hashes", {}).get("raw")
    if raw_hashes != st.get("raw_sha256"):
        raise SystemExit("finalize 拒绝: audit raw_dataset_hashes 与锁不一致")
    enriched_hash = audit.get("dataset_hashes", {}).get("enriched")
    if enriched_hash != st.get("enriched_sha256"):
        raise SystemExit("finalize 拒绝: audit enriched_sha256 与锁不一致")
    if audit.get("budget_hard_cap") != st.get("budget_hard_cap"):
        raise SystemExit("finalize 拒绝: audit budget_hard_cap 与锁不一致")
    if audit.get("integrity_result") != "PASS":
        raise SystemExit("finalize 拒绝: audit integrity_result 非 PASS")
    st.update({"status":"FINALIZED","finalized_at":_now_iso(),
               "archive_id":archive_path.name,"audit_index_sha256":audit_sha,
               "gate_verdict":gate_verdict})
    tmp=lp.with_suffix(".tmp")
    tmp.write_text(json.dumps(st,ensure_ascii=False),encoding="utf-8")
    os.replace(tmp,lp)
```

- [ ] **Step 6: 写测试 - 2023 锁 RUNNING resume/FINALIZED 事务/归档失败保持 RUNNING**

```python
def test_2023_lock_running_allows_matching_resume(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
    lock=tmp_path/"2023.lock"
    acquire_2023_run_lock(lock,"r1","cf","sh")
    assert acquire_2023_run_lock(lock,"r1","cf","sh")=="RESUME"

def test_2023_lock_running_rejects_mismatch(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
    import pytest
    lock=tmp_path/"2023.lock"
    acquire_2023_run_lock(lock,"r1","cf","sh")
    with pytest.raises(SystemExit):
        acquire_2023_run_lock(lock,"r2","cf","sh")

def test_2023_lock_finalized_rejects_all(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock, finalize_2023_run_lock, BLESSED_2023_RAW_SHA256
    import json, pytest
    lock=tmp_path/"2023.lock"
    arch=tmp_path/"archive"; arch.mkdir()
    audit={"run_id":"r1","stage":"final_2023","gate_verdict":"CONFIRMED_PROMOTE",
           "code_fingerprint":"cf","sched_hash":"sh",
           "dataset_hashes":{"raw":BLESSED_2023_RAW_SHA256,"enriched":"enriched_sha"},
           "integrity_result":"PASS","budget_hard_cap":530}
    (arch/"audit_index.json").write_text(json.dumps(audit),encoding="utf-8")
    acquire_2023_run_lock(lock,"r1","cf","sh",budget_hard_cap=530)
    # P0-6: 写入 enriched_sha256 使 finalizer 通过
    st=json.loads(lock.read_text(encoding="utf-8"))
    st["enriched_sha256"]="enriched_sha"
    lock.write_text(json.dumps(st),encoding="utf-8")
    finalize_2023_run_lock(lock, arch, "CONFIRMED_PROMOTE",
                           schedule_complete=True, integrity_passed=True)
    with pytest.raises(SystemExit):
        acquire_2023_run_lock(lock,"r1","cf","sh")

def test_2023_finalize_rejects_incomplete_schedule(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock, finalize_2023_run_lock
    import pytest
    lock=tmp_path/"2023.lock"
    acquire_2023_run_lock(lock,"r1","cf","sh")
    with pytest.raises(SystemExit):
        finalize_2023_run_lock(lock, tmp_path/"arch", "v", schedule_complete=False, integrity_passed=True)
    st=json.loads(lock.read_text(encoding="utf-8"))
    assert st["status"]=="RUNNING"

def test_2023_finalize_rejects_missing_archive(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock, finalize_2023_run_lock
    import pytest
    lock=tmp_path/"2023.lock"
    acquire_2023_run_lock(lock,"r1","cf","sh")
    # archive 不存在 -> 拒绝
    with pytest.raises(SystemExit):
        finalize_2023_run_lock(lock, tmp_path/"nope", "v", schedule_complete=True, integrity_passed=True)
    st=json.loads(lock.read_text(encoding="utf-8"))
    assert st["status"]=="RUNNING"

def test_2023_finalize_recomputes_audit_sha(tmp_path):
    """finalizer 重算 audit_index SHA，不信任调用方。"""
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock, finalize_2023_run_lock, _sha256_file, BLESSED_2023_RAW_SHA256
    import json
    lock=tmp_path/"2023.lock"
    arch=tmp_path/"archive"; arch.mkdir()
    audit={"run_id":"r1","stage":"final_2023","gate_verdict":"CONFIRMED_PROMOTE",
           "code_fingerprint":"cf","sched_hash":"sh",
           "dataset_hashes":{"raw":BLESSED_2023_RAW_SHA256,"enriched":"enriched_sha"},
           "integrity_result":"PASS","budget_hard_cap":530}
    (arch/"audit_index.json").write_text(json.dumps(audit),encoding="utf-8")
    acquire_2023_run_lock(lock,"r1","cf","sh",budget_hard_cap=530)
    # P0-6: 写入 enriched_sha256 使 finalizer 通过
    st=json.loads(lock.read_text(encoding="utf-8"))
    st["enriched_sha256"]="enriched_sha"
    lock.write_text(json.dumps(st),encoding="utf-8")
    finalize_2023_run_lock(lock, arch, "CONFIRMED_PROMOTE", True, True)
    st=json.loads(lock.read_text(encoding="utf-8"))
    assert st["audit_index_sha256"]==_sha256_file(str(arch/"audit_index.json"))
    assert st["status"]=="FINALIZED"

def test_2023_verify_raw_data_rejects_mismatch(tmp_path):
    """原始数据 SHA 不匹配预登记 -> BLOCKED。"""
    from scripts.phase6_6b2_sealed_workflow import verify_2023_raw_data
    import pytest
    raw=tmp_path/"raw.jsonl"; raw.write_text("x",encoding="utf-8")
    with pytest.raises(SystemExit):
        verify_2023_raw_data(str(raw), "mismatch_sha")

def test_2023_resume_rejects_enriched_sha_mismatch(tmp_path, monkeypatch):
    """P1: RESUME 时 enriched SHA 不一致 -> 拒绝（不覆盖锁中 SHA）。"""
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock, record_enriched_sha_to_lock
    import json
    lock=tmp_path/"2023.lock"
    acquire_2023_run_lock(lock,"r1","cf","sh")
    # 模拟已有 enriched SHA
    st=json.loads(lock.read_text(encoding="utf-8"))
    st["enriched_sha256"]="original_sha"
    lock.write_text(json.dumps(st),encoding="utf-8")
    # 新 enrichment 产生不同 SHA
    enriched=tmp_path/"enriched.jsonl"; enriched.write_text("different",encoding="utf-8")
    with pytest.raises(SystemExit):
        record_enriched_sha_to_lock(str(lock), str(enriched))

def test_gate_final_2023_delta_minus_5pp_boundary(tmp_path):
    """P1: Δ2023 == -5pp 精确边界 -> ROLLBACK（而非 INCONCLUSIVE）。
    3 repeats × 40 case/arm，dual 50% vs b1a 55% → Δ=-5pp。"""
    from scripts.phase6_6b2_orchestrator import compute_gate
    rows=[]
    ds_key = "baziqa_contest8_2023_holdout_enriched"
    for rep in [0,1,2]:
        for i in range(1, 41):
            cid = f"Q{i}"
            # dual: i <= 20 -> correct (A==A), i > 20 -> incorrect (B!=A)
            dual_correct = i <= 20
            dual_ans = "A" if dual_correct else "B"
            rows.append({"case_id":cid,"predicted_answer":dual_ans,"expected_answer":"A",
                         "correct":dual_correct,"dual_stage":"bazi","terminal_state":"parsed",
                         "attempt_key":[ds_key,"prof","dual","bazi","p","m",cid,rep,0,"p0"]})
            rows.append({"case_id":cid,"predicted_answer":dual_ans,"expected_answer":"A",
                         "correct":dual_correct,"dual_stage":"ziwei","terminal_state":"parsed",
                         "attempt_key":[ds_key,"prof","dual","ziwei","p","m",cid,rep,0,"p0"]})
            # b1a: i <= 22 -> correct, i > 22 -> incorrect
            b1a_correct = i <= 22
            b1a_ans = "A" if b1a_correct else "B"
            rows.append({"case_id":cid,"predicted_answer":b1a_ans,"expected_answer":"A",
                         "correct":b1a_correct,"dual_stage":"main","terminal_state":"parsed",
                         "attempt_key":[ds_key,"prof","b1a_prime","main","p","m",cid,rep,0,"p0"]})
    gate=compute_gate(rows, stage="final_2023")
    assert gate["verdict"]=="ROLLBACK"
    assert gate["delta_2023"]==pytest.approx(-0.05)
```

- [ ] **Step 7: 运行通过**
- [ ] **Step 8: Commit** - `feat(6b2): enrichment + sealed 2023 RUNNING/FINALIZED state machine + stage gating`

---

## Task 16: 最终归档与审计索引

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**P0-3：** 归档组件必须先于 2023 密封事务链实施，因为 `run_2023_final` 调用 `generate_archive`。

**关键约束：**
- `generate_archive` 自行调用 `_integrity_gate`（不信任外部 `integrity_result`）
- 归档拒绝覆盖已存在的 `run_id` 目录
- `BLOCKED_INCOMPLETE` 裁决不得生成决策归档
- schedule 未全部完成 → 拒绝归档
- ledger 超 hard_cap → 拒绝归档

- [ ] **Step 1: 写失败测试 - 归档保留 ROLLBACK + 拒绝 BLOCKED + 拒绝覆盖**

```python
def _mk_schedule_ledger_gate(tmp_path, verdict="PROMOTE_CANDIDATE"):
    """构造已完成 schedule + ledger + gate_result 夹具。
    
    为每个 slice 创建 detail/event 文件，使 generate_archive 的 integrity gate
    和 event-ledger 对账均能通过。P1: 按实际调用数（非 scheduled_calls）记录 ledger。
    数据分布使重算 gate 的裁决与传入 verdict 一致：
    - PROMOTE_CANDIDATE: dual 100% 正确, b1a 0% 正确 → delta_dev=1.0
    - ROLLBACK: 双臂 100% 正确 → delta_dev=0
    """
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2, GLOBAL_HARD_CAP, _build_schedule
    import json
    ds = tmp_path/"ds.jsonl"
    ds.write_text("\n".join([json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)])+"\n", encoding="utf-8")
    sched=_build_schedule(str(tmp_path/"run"), years=["2024","2025"],
                          dataset_paths={"2024": str(ds), "2025": str(ds)})
    ledger=BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=GLOBAL_HARD_CAP,
                           slice_min=8, slice_max=26)
    ds_key_prefix = "baziqa_contest8_{year}_holdout_enriched"
    b1a_correct = verdict != "PROMOTE_CANDIDATE"  # PROMOTE: b1a 全错; ROLLBACK: b1a 全对
    for sl in sched["slices"]:
        out_dir = Path(sl["output_dir"]); out_dir.mkdir(parents=True, exist_ok=True)
        ds_key = ds_key_prefix.format(year=sl["year"])
        actual = 0
        with open(out_dir/"details.jsonl","w",encoding="utf-8") as fd, \
             open(out_dir/"details.events.jsonl","w",encoding="utf-8") as fe:
            for i,cid in enumerate(sl["case_ids"]):
                if sl["arm"] == "b1a_prime":
                    ans = "A" if b1a_correct else "B"
                    fd.write(json.dumps({"case_id":cid,"predicted_answer":ans,"expected_answer":"A",
                        "correct":b1a_correct,"dual_stage":"main","terminal_state":"parsed",
                        "attempt_key":[ds_key,"prof","b1a_prime","main","p","m",cid,sl["repeat"],i,"p0"]})+"\n")
                    fe.write(json.dumps({"kind":"call_attempt","case_id":cid})+"\n")
                    actual += 1
                else:
                    fd.write(json.dumps({"case_id":cid,"predicted_answer":"A","expected_answer":"A",
                        "correct":True,"dual_stage":"bazi","terminal_state":"parsed",
                        "attempt_key":[ds_key,"prof","dual","bazi","p","m",cid,sl["repeat"],i,"p0"]})+"\n")
                    fd.write(json.dumps({"case_id":cid,"predicted_answer":"A","expected_answer":"A",
                        "correct":True,"dual_stage":"ziwei","terminal_state":"parsed",
                        "attempt_key":[ds_key,"prof","dual","ziwei","p","m",cid,sl["repeat"],i,"p0"]})+"\n")
                    fe.write(json.dumps({"kind":"call_attempt","case_id":cid})+"\n")
                    fe.write(json.dumps({"kind":"call_attempt","case_id":cid})+"\n")
                    actual += 2
        ledger.record_slice_completed(sl["slice_id"], actual)
    gate={"verdict":verdict,"delta_dev":0.05,"dual_merged_acc":0.35,"stage":"dev"}
    return sched, ledger, gate

def test_archive_preserves_rollback_verdict(tmp_path):
    from scripts.phase6_6b2_orchestrator import generate_archive
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path, verdict="ROLLBACK")
    archive_dir = generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                                   archive_root=str(tmp_path/"arch"))
    import json; from pathlib import Path
    ai = json.loads((tmp_path/"arch"/Path(archive_dir).name/"audit_index.json").read_text(encoding="utf-8"))
    assert ai["gate_verdict"]=="ROLLBACK"

def test_archive_refuses_blocked_incomplete(tmp_path):
    from scripts.phase6_6b2_orchestrator import generate_archive; import pytest
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    gate["verdict"]="BLOCKED_INCOMPLETE"
    with pytest.raises(SystemExit):
        generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                         archive_root=str(tmp_path/"arch"))

def test_archive_runs_integrity_on_merged_rows(tmp_path, monkeypatch):
    from scripts.phase6_6b2_orchestrator import generate_archive; import pytest
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator._integrity_gate",
        lambda *a,**k: "MISSING_JUDGE: Q1")
    with pytest.raises(SystemExit):
        generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                         archive_root=str(tmp_path/"arch"))

def test_archive_refuses_incomplete_schedule(tmp_path):
    from scripts.phase6_6b2_orchestrator import generate_archive, BudgetLedger6B2, GLOBAL_HARD_CAP, _build_schedule
    import pytest, json
    ds = tmp_path/"ds.jsonl"
    ds.write_text("\n".join([json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)])+"\n", encoding="utf-8")
    sched=_build_schedule(str(tmp_path/"run"), years=["2024","2025"],
                          dataset_paths={"2024": str(ds), "2025": str(ds)})
    ledger=BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=GLOBAL_HARD_CAP, slice_min=8, slice_max=26)
    for sl in sched["slices"][:30]:
        ledger.record_slice_completed(sl["slice_id"], sl["scheduled_calls"])
    gate={"verdict":"PROMOTE_CANDIDATE","delta_dev":0.05,"dual_merged_acc":0.35,"stage":"dev"}
    with pytest.raises(SystemExit):
        generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                         archive_root=str(tmp_path/"arch"))

def test_archive_run_id_uses_code_fingerprint(tmp_path, monkeypatch):
    """不同 code_fingerprint 产生不同 run_id → 不同归档目录名。"""
    from scripts.phase6_6b2_orchestrator import generate_archive
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    d1 = generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                          archive_root=str(tmp_path/"arch1"))
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator._compute_experiment_code_fingerprint",
        lambda: "different_code_fp")
    d2 = generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                          archive_root=str(tmp_path/"arch2"))
    from pathlib import Path
    assert Path(d1).name != Path(d2).name

def test_archive_audit_contains_dataset_hashes(tmp_path):
    """归档 audit_index.json 包含 dataset_hashes 字段，反映 schedule 数据路径。"""
    from scripts.phase6_6b2_orchestrator import generate_archive, _sha256_file
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    arch_dir = generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                                archive_root=str(tmp_path/"arch"))
    import json; from pathlib import Path
    audit = json.loads((Path(arch_dir)/"audit_index.json").read_text(encoding="utf-8"))
    assert "dataset_hashes" in audit
    assert "raw" in audit["dataset_hashes"]
    assert "enriched" in audit["dataset_hashes"]

def test_archive_refuses_overwrite(tmp_path):
    from scripts.phase6_6b2_orchestrator import generate_archive; import pytest
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                     archive_root=str(tmp_path/"arch"))
    with pytest.raises(SystemExit):
        generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                         archive_root=str(tmp_path/"arch"))
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 generate_archive + audit_index**

```python
FROZEN_DATE = "2026-07-17"

# _sha256_file 已定义于 Task 11 helpers（同一模块 scripts/phase6_6b2_orchestrator.py），此处不重复定义。

# 从密封工作流导入阶段准入函数（供 _run_dev_reuse 和 TestGateReceipt 使用）
from scripts.phase6_6b2_sealed_workflow import check_stage_gate

def _compute_experiment_code_fingerprint():
    """组合实验相关源文件的 SHA-256。P0-5: 含 runner/formatter/compute_gate/generate_archive/record/finalize。"""
    import inspect
    from scripts.phase6_6b2_orchestrator import (
        _build_schedule, _integrity_gate, _merge_all_details, _run_all_slices,
        compute_gate, generate_archive)
    from scripts.phase6_6b2_sealed_workflow import (
        check_stage_gate, acquire_2023_run_lock, enrich_year,
        record_enriched_sha_to_lock, finalize_2023_run_lock)
    from benchmark.runners.run_benchmark import (
        run_dual_system_benchmark, _call_dual_stage, _run_dual_case)
    from benchmark.formatters.dual_system_reasoning import (
        build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt,
        build_judge_prompt, extract_judge_answer, judge_swap_seed)
    parts = []
    for fn in (_build_schedule, _integrity_gate, _merge_all_details, _run_all_slices,
               compute_gate, generate_archive,
               check_stage_gate, acquire_2023_run_lock, enrich_year,
               record_enriched_sha_to_lock, finalize_2023_run_lock,
               run_dual_system_benchmark, _call_dual_stage, _run_dual_case,
               build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt,
               build_judge_prompt, extract_judge_answer, judge_swap_seed):
        parts.append(hashlib.sha256(inspect.getsource(fn).encode()).hexdigest())
    return hashlib.sha256("".join(parts).encode()).hexdigest()

def _compute_dataset_hashes(raw_paths=None, enriched_paths=None):
    """计算 raw/enriched 数据集的 SHA-256。
    
    raw_paths: {year: raw_path} 映射，用于计算原始数据哈希。
    enriched_paths: {year: enriched_path} 映射，用于计算 enrichment 后哈希。
    返回 {raw: combined_sha_of_raw, enriched: combined_sha_of_enriched}。
    """
    import hashlib
    raw_h = hashlib.sha256()
    for p in sorted(raw_paths.values()) if raw_paths else []:
        if os.path.exists(p):
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    raw_h.update(chunk)
    enriched_h = hashlib.sha256()
    for p in sorted(enriched_paths.values()) if enriched_paths else []:
        if os.path.exists(p):
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    enriched_h.update(chunk)
    return {"raw": raw_h.hexdigest(), "enriched": enriched_h.hexdigest()}

def _compute_context_fingerprint(schedule, provider, model):
    return {"schedule_slices":len(schedule["slices"]), "provider":provider, "model":model}

def _merge_artifacts(schedule, output_dir, provider, model):
    """合并各 slice 的 detail/event 文件到 output_dir。返回计数。"""
    detail_rows, event_rows = 0, 0
    out_d = Path(output_dir)/"merged_details.jsonl"
    out_e = Path(output_dir)/"merged_events.jsonl"
    with open(out_d,"w",encoding="utf-8") as fd, open(out_e,"w",encoding="utf-8") as fe:
        for sl in schedule["slices"]:
            dp = Path(sl["output_dir"])/"details.jsonl"
            if dp.exists():
                for line in open(dp,encoding="utf-8"):
                    if line.strip(): fd.write(line); detail_rows += 1
            ep = Path(sl["output_dir"])/"details.events.jsonl"
            if ep.exists():
                for line in open(ep,encoding="utf-8"):
                    if line.strip(): fe.write(line); event_rows += 1
    return {"detail_rows":detail_rows,"event_rows":event_rows}

# _load_events 已定义于 Task 11 helpers（同一模块 scripts/phase6_6b2_orchestrator.py），此处不重复定义。

def _merge_all_details(schedule):
    """合并所有 slice 的 detail 行到单一列表。"""
    merged = []
    for sl in schedule["slices"]:
        dp = Path(sl["output_dir"])/"details.jsonl"
        if dp.exists():
            for line in open(dp,encoding="utf-8"):
                if line.strip(): merged.append(json.loads(line))
    return merged

def _run_all_slices(schedule, ledger, provider, model):
    """遍历 schedule 逐 slice 执行（同步，由调用方负责验证完整性）。"""
    for sl in schedule["slices"]:
        _run_slice(sl, ledger, provider, model)

def generate_archive(schedule, ledger, output_dir, provider, model, gate_result, archive_root=None, dataset_paths=None, run_id=None):
    """fail-closed 归档：合并后自行运行 _integrity_gate，不信任外部 integrity_result。
    
    dataset_paths: {year: raw_path} 映射，用于计算 raw 数据哈希。
    run_id: 外部 run-id（来自 CLI），冻结进目录名/audit_index/receipt。
    若未传入，则按 stage/years/date/provider/model/code_hash 自动生成。
    """
    import shutil,tempfile
    if archive_root is None: archive_root=Path("docs/phase6/6b2")
    archive_root=Path(archive_root)
    if gate_result.get("verdict") == "BLOCKED_INCOMPLETE":
        raise SystemExit("BLOCKED_INCOMPLETE: 不得生成决策归档 (预算破顶/完整性失败)")
    if ledger.total_attempted > ledger.hard_cap:
        raise SystemExit(f"归档拒绝: ledger 超 hard_cap ({ledger.total_attempted}>{ledger.hard_cap})")
    completed = sum(1 for sl in schedule["slices"] if ledger.slice_completed(sl["slice_id"]))
    if completed != len(schedule["slices"]):
        raise SystemExit(f"归档拒绝: schedule 未全部完成 ({completed}/{len(schedule['slices'])})")
    code_hash=_compute_experiment_code_fingerprint()
    stage = gate_result.get("stage", "dev")
    years_tag = "-".join(sorted(set(s["year"] for s in schedule["slices"])))
    # 从 schedule 中提取 enriched 路径
    enriched_paths = {}
    for sl in schedule["slices"]:
        ds_path = sl.get("dataset_path", "")
        if ds_path and os.path.exists(ds_path):
            enriched_paths[sl["year"]] = ds_path
    dataset_hash = _compute_dataset_hashes(raw_paths=dataset_paths, enriched_paths=enriched_paths)
    if run_id:
        archive_run_id = run_id
    else:
        archive_run_id = f"6b2-{stage}-{years_tag}-{FROZEN_DATE}-{provider}-{model}-{code_hash[:12]}"
    archive_dir=archive_root/archive_run_id
    if archive_dir.exists():
        raise SystemExit(2)
    archive_root.mkdir(parents=True,exist_ok=True)
    tmp_dir=Path(tempfile.mkdtemp(prefix=f".{archive_run_id}_",dir=str(archive_root)))
    try:
        merge_counts=_merge_artifacts(schedule,tmp_dir,provider,model)
        merged_path = tmp_dir/"merged_details.jsonl"
        merged_rows = [json.loads(l) for l in open(merged_path,encoding="utf-8") if l.strip()] if merged_path.exists() else []
        integrity = _integrity_gate(merged_rows, schedule)
        if integrity != "PASS":
            raise SystemExit(f"归档拒绝: integrity gate 失败 ({integrity})")
        judge_count = sum(1 for r in merged_rows if r.get("attempt_key",[None]*10)[3]=="judge")
        event_rows = _load_events(tmp_dir/"merged_events.jsonl")
        if len(merged_rows) != merge_counts["detail_rows"]:
            raise SystemExit(f"归档拒绝: merged 行数不一致 ({len(merged_rows)}!={merge_counts['detail_rows']})")
        if len(event_rows) != merge_counts["event_rows"]:
            raise SystemExit(f"归档拒绝: event 行数不一致 ({len(event_rows)}!={merge_counts['event_rows']})")
        call_attempts = sum(1 for r in event_rows if r.get("kind") == "call_attempt")
        if call_attempts != ledger.total_attempted:
            raise SystemExit(f"归档拒绝: call_attempt 数({call_attempts}) != ledger.attempted({ledger.total_attempted})")
        ctx_fp=_compute_context_fingerprint(schedule,provider,model)
        # P1: 从 merged rows 重算 gate 并与传入 verdict 比较
        gate_recalculated = compute_gate(merged_rows, stage=stage).get("verdict")
        if gate_recalculated != gate_result.get("verdict"):
            raise SystemExit(f"归档拒绝: 重算 gate ({gate_recalculated}) != 传入 ({gate_result.get('verdict')})")
        audit_index={
            "run_id":archive_run_id,"experiment":"6b2","frozen_date":FROZEN_DATE,
            "provider":provider,"model":model,"stage":stage,"years_tag":years_tag,
            "code_fingerprint":code_hash,
            "sched_hash": hashlib.sha256(json.dumps(schedule, sort_keys=True).encode()).hexdigest(),
            "dataset_hashes":dataset_hash,
            "context_fingerprints":ctx_fp,
            "merged_details_rows":merge_counts["detail_rows"],
            "merged_events_rows":merge_counts["event_rows"],
            "judge_rows":judge_count,
            "budget_total_attempted":ledger.total_attempted,
            "budget_hard_cap":ledger.hard_cap,
            "integrity_result":integrity,
            "gate_verdict":gate_result["verdict"],
            "gate_delta_dev":gate_result.get("delta_dev"),
            "gate_dual_merged_acc":gate_result.get("dual_merged_acc"),
            "gate_recalculated_from_merged": gate_recalculated,
        }
        for fn in ["merged_details.jsonl","merged_events.jsonl"]:
            p=tmp_dir/fn
            if p.exists():
                audit_index[f"{fn}_sha256"]=_sha256_file(p)
        (tmp_dir/"audit_index.json").write_text(json.dumps(audit_index,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(tmp_dir, archive_dir)
        return str(archive_dir)
    except Exception:
        shutil.rmtree(tmp_dir,ignore_errors=True)
        raise
```

- [ ] **Step 4: 写测试 - root 与归档哈希一致**

```python
def test_archive_hashes_match_root(tmp_path):
    """归档 merged_details SHA-256 == 运行目录 merged_details SHA-256。
    使用 2 年 × 40 case × 3 repeats × 2 arms 的合法实验矩阵（dev gate 要求 2024+2025）。
    数据分布使重算 gate 产生 PROMOTE_CANDIDATE（dual 全对, b1a 全错 → delta_dev=1.0）。"""
    from scripts.phase6_6b2_orchestrator import generate_archive, _sha256_file, _merge_artifacts, _build_schedule, BudgetLedger6B2, GLOBAL_HARD_CAP
    from pathlib import Path
    import json
    run_dir = tmp_path / "run"
    ds_path = tmp_path / "mini.jsonl"
    lines = [json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)]
    ds_path.write_text("\n".join(lines)+"\n", encoding="utf-8")
    sched = _build_schedule(str(run_dir), years=["2024","2025"],
                            dataset_paths={"2024": str(ds_path), "2025": str(ds_path)})
    ledger = BudgetLedger6B2(str(run_dir/"l.json"), global_hard_cap=GLOBAL_HARD_CAP, slice_min=8, slice_max=26)
    ds_key_prefix = "baziqa_contest8_{year}_holdout_enriched"
    for sl in sched["slices"]:
        out_dir = Path(sl["output_dir"]); out_dir.mkdir(parents=True, exist_ok=True)
        ds_key = ds_key_prefix.format(year=sl["year"])
        actual = 0
        with open(out_dir/"details.jsonl","w",encoding="utf-8") as fd, \
             open(out_dir/"details.events.jsonl","w",encoding="utf-8") as fe:
            for i,cid in enumerate(sl["case_ids"]):
                if sl["arm"] == "b1a_prime":
                    # PROMOTE_CANDIDATE: b1a 全错 → delta_dev=1.0
                    fd.write(json.dumps({"case_id":cid,"predicted_answer":"B","expected_answer":"A",
                        "correct":False,"dual_stage":"main","terminal_state":"parsed",
                        "attempt_key":[ds_key,"prof","b1a_prime","main","p","m",cid,sl["repeat"],i,"p0"]})+"\n")
                    fe.write(json.dumps({"kind":"call_attempt","case_id":cid})+"\n")
                    actual += 1
                else:
                    fd.write(json.dumps({"case_id":cid,"predicted_answer":"A","expected_answer":"A",
                        "correct":True,"dual_stage":"bazi","terminal_state":"parsed",
                        "attempt_key":[ds_key,"prof","dual","bazi","p","m",cid,sl["repeat"],i,"p0"]})+"\n")
                    fd.write(json.dumps({"case_id":cid,"predicted_answer":"A","expected_answer":"A",
                        "correct":True,"dual_stage":"ziwei","terminal_state":"parsed",
                        "attempt_key":[ds_key,"prof","dual","ziwei","p","m",cid,sl["repeat"],i,"p0"]})+"\n")
                    fe.write(json.dumps({"kind":"call_attempt","case_id":cid})+"\n")
                    fe.write(json.dumps({"kind":"call_attempt","case_id":cid})+"\n")
                    actual += 2
        ledger.record_slice_completed(sl["slice_id"], actual)
    gate = {"verdict":"PROMOTE_CANDIDATE","delta_dev":0.05,"dual_merged_acc":0.35,"stage":"dev"}
    arch_dir = generate_archive(sched, ledger, str(run_dir), "p","m", gate, archive_root=str(tmp_path/"arch"))
    arch_sha = _sha256_file(str(Path(arch_dir)/"merged_details.jsonl"))
    merge_counts = _merge_artifacts(sched, str(run_dir), "p", "m")
    root_sha = _sha256_file(str(run_dir/"merged_details.jsonl"))
    assert root_sha == arch_sha
    assert merge_counts["detail_rows"] > 0
```

- [ ] **Step 5: 运行通过**
- [ ] **Step 6: Commit** - `feat(6b2): final archive + audit index (refuse overwrite, BLOCKED guard)`

---
## Task 17: 复用验证 + 2023 终验执行支持（P0-3/P0-4 修订）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**P0-3：** 2023 密封函数必须接入完整事务链（`generate_archive` 已在 Task 16 实现）：
```
check_stage_gate("final_2023")
-> acquire_2023_run_lock (用冻结 SHA)
-> verify_2023_raw_data (验证原始 SHA)
-> enrich 2023 + record_enriched_sha_to_lock
-> run schedule (global_hard_cap=530)
-> integrity gate
-> compute_gate(stage="final_2023")
-> generate_archive (Task 16)
-> finalize_2023_run_lock (验证 archive 后 FINALIZED)
```

**P0-4：** 阶段化预算（spec §8）：
- dev: scheduled=960, hard_cap=1060
- reuse: scheduled=960, hard_cap=1060
- final_2023: scheduled=480, hard_cap=**530**（非 1060）

- [ ] **Step 1: 写测试 - 阶段化预算 + 2023 事务链**

```python
def test_final_2023_hard_cap_is_530(tmp_path):
    """P0-4: 2023 终验 hard_cap=530（非 1060），scheduled=480。"""
    from scripts.phase6_6b2_orchestrator import _build_schedule, FINAL_2023_HARD_CAP, FINAL_2023_SCHEDULED
    import json
    ds = tmp_path/"ds.jsonl"
    ds.write_text("\n".join([json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)])+"\n", encoding="utf-8")
    s=_build_schedule(str(tmp_path), years=["2023"], dataset_paths={"2023": str(ds)})
    assert s["global_hard_cap"]==530
    assert s["total_scheduled_calls"]==480
    assert FINAL_2023_HARD_CAP==530

def test_reuse_hard_cap_is_1060(tmp_path):
    from scripts.phase6_6b2_orchestrator import _build_schedule
    import json
    ds = tmp_path/"ds.jsonl"
    ds.write_text("\n".join([json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)])+"\n", encoding="utf-8")
    s=_build_schedule(str(tmp_path), years=["2021","2022"], dataset_paths={"2021": str(ds), "2022": str(ds)})
    assert s["global_hard_cap"]==1060

def test_2023_transaction_chain_order(tmp_path, monkeypatch):
    """P0-3/P0-4: 2023 事务链按正确顺序调用全部密封函数 + integrity_gate + archive。"""
    from scripts.phase6_6b2_sealed_workflow import BLESSED_2023_RAW_SHA256
    from pathlib import Path
    import json
    calls=[]
    raw_path = "benchmark/datasets/baziqa_contest8_2023_holdout.jsonl"
    enriched_path = None
    def fake(fn):
        def wrapper(*a,**kw):
            nonlocal enriched_path
            calls.append(fn)
            if fn == "acquire":
                lock_path = Path(a[0]) if a else tmp_path / "2023.lock"
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                lock_path.write_text(json.dumps({
                    "status":"RUNNING","run_id":a[1] if len(a)>1 else "r1",
                    "raw_sha256":BLESSED_2023_RAW_SHA256,
                    "enriched_sha256":"enriched_sha",
                    "code_fingerprint":a[2] if len(a)>2 else "cf",
                    "schedule_hash":a[3] if len(a)>3 else "",
                    "budget_hard_cap":kw.get("budget_hard_cap",530)}),encoding="utf-8")
                return "NEW"
            if fn == "enrich":
                enriched_path = a[2] if len(a) > 2 else str(tmp_path / "2023_enriched.jsonl")
                Path(enriched_path).parent.mkdir(parents=True, exist_ok=True)
                lines = [json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)]
                Path(enriched_path).write_text("\n".join(lines)+"\n", encoding="utf-8")
                return {"year":"2023","rows":40,"ziwei_coverage":40}
            if fn == "compute_gate":
                return {"verdict":"CONFIRMED_PROMOTE","delta_2023":0.1,"stage":"final_2023"}
            if fn == "generate_archive":
                arch_dir = tmp_path / "arch_out"
                arch_dir.mkdir(exist_ok=True)
                return str(arch_dir)
            if fn == "integrity_gate":
                return "PASS"
            return None
        return wrapper
    # monkeypatch 各环节，记录调用顺序
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.check_stage_gate", fake("check_stage_gate"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.acquire_2023_run_lock", fake("acquire"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.verify_2023_raw_data", fake("verify_raw"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.enrich_year", fake("enrich"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.record_enriched_sha_to_lock", fake("record_enriched"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.finalize_2023_run_lock", fake("finalize"))
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator._run_all_slices", fake("run_schedule"))
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator._merge_all_details", fake("merge_details"))
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator._integrity_gate", fake("integrity_gate"))
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator.compute_gate", fake("compute_gate"))
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator.generate_archive", fake("generate_archive"))
    # 构造归档 audit_index.json
    arch_dir = tmp_path / "arch_out"
    arch_dir.mkdir(exist_ok=True)
    (arch_dir / "audit_index.json").write_text(json.dumps({
        "run_id":"6b2-final_2023-2026-07-17-p-m-000000000000",
        "stage":"final_2023","gate_verdict":"CONFIRMED_PROMOTE",
        "code_fingerprint":"cf","sched_hash":"sh",
        "dataset_hashes":{"raw":BLESSED_2023_RAW_SHA256,"enriched":"enriched_sha"},
        "integrity_result":"PASS","budget_hard_cap":530
    },ensure_ascii=False),encoding="utf-8")
    run_2023_final(provider="p", model="m", gate_root=str(tmp_path), archive_root=str(tmp_path))
    expected=["check_stage_gate","acquire","verify_raw","enrich","record_enriched",
              "run_schedule","merge_details","integrity_gate",
              "compute_gate","generate_archive","finalize"]
    assert calls==expected, f"Call order mismatch: {calls} != {expected}"

def test_reuse_years_schedule(tmp_path):
    from scripts.phase6_6b2_orchestrator import _build_schedule
    import json
    ds = tmp_path/"ds.jsonl"
    ds.write_text("\n".join([json.dumps({"case_id":f"Q{i+1}"}) for i in range(40)])+"\n", encoding="utf-8")
    s=_build_schedule(str(tmp_path), years=["2021","2022"],
                      dataset_paths={"2021": str(ds), "2022": str(ds)})
    assert s["total_slices"]==60
    years={sl["year"] for sl in s["slices"]}
    assert years=={"2021","2022"}
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 run_2023_final 事务链 + 阶段化预算常量**

```python
def run_2023_final(provider, model, gate_root, archive_root):
    """2023 终验完整事务链（P0-3/P0-4/P0-5）。"""
    from scripts.phase6_6b2_sealed_workflow import (
        check_stage_gate, acquire_2023_run_lock, verify_2023_raw_data,
        enrich_year, record_enriched_sha_to_lock, finalize_2023_run_lock,
        BLESSED_2023_RAW_SHA256)
    # 1. 阶段准入
    code_fp = _compute_experiment_code_fingerprint()
    check_stage_gate("final_2023", gate_root=gate_root, provider=provider, model=model,
                     current_code_fingerprint=code_fp)
    # 2. 获取 RUNNING 锁（冻结 SHA）
    raw_path = "benchmark/datasets/baziqa_contest8_2023_holdout.jsonl"
    # P0-5: run_id 含 years_tag，与 archive run_id 前缀一致
    run_id = f"6b2-final_2023-2023-{FROZEN_DATE}-{provider}-{model}-{code_fp[:12]}"
    lock_path = Path(gate_root)/"2023.lock"
    lock_status = acquire_2023_run_lock(lock_path, run_id, code_fp, "",
                                        budget_hard_cap=FINAL_2023_HARD_CAP)
    # 3. 验证原始数据 SHA
    verify_2023_raw_data(raw_path, BLESSED_2023_RAW_SHA256)
    # 4. 建立 run workspace（先于 schedule）
    run_workspace = Path(gate_root) / "workspace" / run_id
    run_workspace.mkdir(parents=True, exist_ok=True)
    enriched_path = str(run_workspace / "datasets" / "2023_enriched.jsonl")
    if lock_status == "NEW":
        # 首次运行：enrichment + 记录 SHA
        enrich_year("2023", raw_path, enriched_path)
        record_enriched_sha_to_lock(lock_path, enriched_path)
    else:
        # RESUME：验证现有文件 SHA，不重新 enrichment
        if not os.path.exists(enriched_path):
            raise SystemExit(f"RESUME 但 enrichment 文件不存在: {enriched_path}")
        record_enriched_sha_to_lock(lock_path, enriched_path)
    # 5. 构建 schedule（用 enriched 数据 + run workspace 输出目录）
    sched = _build_schedule(str(run_workspace/"slices"), years=["2023"],
                            dataset_paths={"2023": enriched_path})
    sched_hash = hashlib.sha256(json.dumps(sched,sort_keys=True).encode()).hexdigest()
    # 将 sched_hash 写回锁（供 finalize 验证）
    _update_lock_sched_hash(lock_path, sched_hash)
    # 6. 运行 schedule（hard_cap=530）
    ledger = BudgetLedger6B2(str(Path(gate_root)/"ledger_2023.json"),
                             global_hard_cap=FINAL_2023_HARD_CAP, slice_min=8, slice_max=26)
    _run_all_slices(sched, ledger, provider, model)
    # 7. 完整性门禁
    merged = _merge_all_details(sched)
    integrity = _integrity_gate(merged, sched)
    if integrity != "PASS":
        raise SystemExit(f"2023 integrity 失败: {integrity} (保持 RUNNING)")
    # 8. compute_gate
    gate = compute_gate(merged, stage="final_2023")
    # 9. 归档（generate_archive 已在 Task 16 实现，内部自验完整性）
    archive_dir = generate_archive(sched, ledger, str(run_workspace/"slices"), provider, model, gate,
                                   archive_root=str(archive_root),
                                   dataset_paths={"2023": raw_path},
                                   run_id=run_id)
    # 10. FINALIZED（验证 archive 后切换）
    finalize_2023_run_lock(lock_path, archive_dir, gate["verdict"],
                           schedule_complete=True, integrity_passed=True)
    return {"archive_dir":archive_dir,"gate":gate}


def _update_lock_sched_hash(lock_path, sched_hash):
    """将 sched_hash 写入 RUNNING 锁。None/"" 视为未初始化，允许首次写入。"""
    lp = Path(lock_path)
    if not lp.exists():
        return
    st = json.loads(lp.read_text(encoding="utf-8"))
    existing = st.get("schedule_hash")
    if existing and existing != sched_hash:
        raise SystemExit(f"_update_lock_sched_hash 拒绝: RESUME 时 sched_hash 不一致 ({existing[:12]} != {sched_hash[:12]})")
    st["schedule_hash"] = sched_hash
    tmp = lp.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, lp)
```

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): 2023 sealed transaction chain + stage-based budget (530)`

---

## Task 17b: dev/reuse 执行链 + CLI 入口（P0-4 补全）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**设计**：把既有零件串成可执行流程——`run_dev()`（2024/2025：smoke → schedule → ledger →
逐 slice 执行+完整性 → gate → 报告 → 归档）、`run_reuse()`（2021/2022 同链、stage=reuse）、
`main()` CLI（`--stage dev|reuse|final-2023`）。2023 终验走 Task 15/17 的密封事务链。

- [ ] **Step 1: 写失败测试（完整代码）**

```python
def _mock_archive(arch_path, args, kwargs):
    """创建最小 archive 目录 + audit_index.json（与 _compute_experiment_code_fingerprint 一致）。"""
    from scripts.phase6_6b2_orchestrator import _compute_experiment_code_fingerprint
    arch = Path(arch_path)
    arch.mkdir(parents=True, exist_ok=True)
    gate = args[5] if len(args) > 5 else kwargs.get("gate_result", {"stage": "dev"})
    stage = gate.get("stage", "dev") if isinstance(gate, dict) else "dev"
    run_id = kwargs.get("run_id", args[8] if len(args) > 8 else None)
    if not run_id:
        code_fp = _compute_experiment_code_fingerprint()
        run_id = f"6b2-{stage}-2024-2025-2026-07-17-p-m-{code_fp[:12]}"
    code_fp = _compute_experiment_code_fingerprint()
    audit = {"run_id": run_id, "stage": stage, "code_fingerprint": code_fp,
             "dataset_hashes": {"raw": "x", "enriched": "x"}}
    (arch / "audit_index.json").write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
    return str(arch)

class TestRunDevChain:
    """dev 执行链：smoke 先于 schedule；每 slice 执行；gate/报告/归档按序产出（全 spy，无真实调用）。"""

    def _mock_chain(self, orch, monkeypatch, calls):
        monkeypatch.setattr(orch, "determine_smoke_state",
                            lambda d, expected_case_ids=None: calls.append("smoke_state") or "completed")
        monkeypatch.setattr(orch, "verify_smoke_completed",
                            lambda d, expected_case_ids: calls.append("smoke_verify") or {"parser_rate": 1.0})
        monkeypatch.setattr(orch, "_smoke_case_ids", lambda paths: ["c0", "c1"])
        monkeypatch.setattr(orch, "_build_schedule",
                            lambda out, years=None, dataset_paths=None: calls.append("schedule") or
                            {"slices": [{"slice_id": "s0", "arm": "dual", "case_ids": ["c0"] * 8}],
                             "total_scheduled_calls": 24, "global_hard_cap": 26})
        monkeypatch.setattr(orch, "_run_slice", lambda sl, ledger, p, m: calls.append(f"slice:{sl['slice_id']}"))
        monkeypatch.setattr(orch, "_merge_all_details", lambda sched: calls.append("merge") or [])
        monkeypatch.setattr(orch, "compute_gate", lambda rows, stage="dev": calls.append(f"gate:{stage}") or
                            {"verdict": "ROLLBACK", "stage": stage})
        monkeypatch.setattr(orch, "load_b1c_advisory", lambda: {"count": 240, "sha256": "x", "rows": []})
        monkeypatch.setattr(orch, "generate_report",
                            lambda gate, rows, sched, ledger, b1c, out: calls.append("report") or {"gate": gate})
        monkeypatch.setattr(orch, "generate_archive",
                            lambda *a, **k: calls.append("archive") or _mock_archive(
                                str(tmp_path_global / "arch"), a, k))

    def test_dev_chain_order_and_outputs(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        global tmp_path_global
        tmp_path_global = tmp_path
        calls = []
        self._mock_chain(orch, monkeypatch, calls)
        ds = tmp_path / "ds.jsonl"
        ds.write_text("\n".join(f'{{"case_id":"c{i}"}}' for i in range(40)) + "\n", encoding="utf-8")
        # v14 签名：run_dev(run_dir, gate_root, archive_root, dataset_paths, provider, model)
        result = orch.run_dev(str(tmp_path / "runs" / "dev-1"), str(tmp_path / "gates"),
                              str(tmp_path / "archive"),
                              {"2024": str(ds), "2025": str(ds)}, "p", "m")
        assert result["status"] == "OK"
        # 顺序：smoke_state → smoke_verify → schedule → slice(s) → merge → gate → report → archive
        assert calls[:3] == ["smoke_state", "smoke_verify", "schedule"]
        assert calls[3] == "slice:s0"
        assert calls[-3:] == ["gate:dev", "report", "archive"]
        assert calls.index("smoke_verify") < calls.index("schedule")
        # v14：receipt 在归档自验后原子发布，含指纹字段（审核 P0-2）
        receipt = tmp_path / "gates" / "dev_gate.json"
        assert receipt.exists()
        rec = json.loads(receipt.read_text(encoding="utf-8"))
        assert rec["verdict"] == "ROLLBACK" and rec["stage"] == "dev"
        assert rec["provider"] == "p" and rec["model"] == "m"
        assert "dataset_sha256" in rec and "code_fingerprint" in rec

    def test_dev_smoke_incomplete_blocks(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        monkeypatch.setattr(orch, "determine_smoke_state",
                            lambda d, expected_case_ids=None: "blocked_corrupt")
        monkeypatch.setattr(orch, "_smoke_case_ids", lambda paths: ["c0", "c1"])
        with pytest.raises(SystemExit, match="smoke"):
            orch.run_dev(str(tmp_path / "runs" / "d"), str(tmp_path / "gates"),
                         str(tmp_path / "archive"), {"2024": "x", "2025": "y"}, "p", "m")

    def test_reuse_requires_dev_gate_admission(self, tmp_path, monkeypatch):
        # v13/v14：reuse 先过 check_stage_gate（无 dev receipt → SystemExit，不进入执行）
        import scripts.phase6_6b2_orchestrator as orch
        monkeypatch.setattr(orch, "_run_slice", lambda *a, **k: None)
        with pytest.raises(SystemExit):
            orch.run_reuse(str(tmp_path / "runs" / "r"), str(tmp_path / "gates"),
                           str(tmp_path / "archive"), {"2021": "x", "2022": "y"}, "p", "m")

    def test_reuse_chain_uses_reuse_stage(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        seen = {}
        monkeypatch.setattr(orch, "check_stage_gate",
                            lambda stage, gate_root=None, provider=None, model=None,
                                   current_code_fingerprint=None:
                                seen.__setitem__("gate_check", stage) or {"verdict": "PROMOTE_CANDIDATE"})
        monkeypatch.setattr(orch, "_run_slice", lambda sl, ledger, p, m: None)
        monkeypatch.setattr(orch, "_merge_all_details", lambda sched: [])
        def _fake_gate(rows, stage="dev"):
            seen["stage"] = stage
            return {"verdict": "PASS", "stage": stage}
        monkeypatch.setattr(orch, "compute_gate", _fake_gate)
        monkeypatch.setattr(orch, "load_b1c_advisory", lambda: {"count": 0, "sha256": "x", "rows": []})
        monkeypatch.setattr(orch, "generate_report", lambda *a, **k: {"gate": a[0]})
        monkeypatch.setattr(orch, "generate_archive",
                            lambda *a, **k: _mock_archive(str(tmp_path / "archive"), a, k))
        ds = tmp_path / "ds.jsonl"
        ds.write_text("\n".join(f'{{"case_id":"c{i}"}}' for i in range(40)) + "\n", encoding="utf-8")
        result = orch.run_reuse(str(tmp_path / "runs" / "r1"), str(tmp_path / "gates"),
                                str(tmp_path / "archive"),
                                {"2021": str(ds), "2022": str(ds)}, "p", "m")
        assert result["status"] == "OK" and seen["stage"] == "reuse"
        assert seen["gate_check"] == "reuse"
        assert (tmp_path / "gates" / "reuse_gate.json").exists()

    def test_main_cli_rejects_unknown_stage(self, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        with pytest.raises(SystemExit):
            orch.main(["--stage", "dev2023", "--run-id", "x"])

    def test_main_cli_rejects_malicious_run_id(self, monkeypatch, tmp_path):
        import scripts.phase6_6b2_orchestrator as orch
        for bad in ("../etc/passwd", "a/b", ".", "..", "", "-"):
            with pytest.raises(SystemExit, match="run-id"):
                orch._validate_run_id(bad)
        # 合法 run-id 不应拒绝
        monkeypatch.setattr(orch, "run_dev", lambda *a, **k: {"status": "OK"})
        monkeypatch.setattr(orch, "_compute_experiment_code_fingerprint",
                            lambda: "x" * 64)
        result = orch.main(["--stage", "dev", "--run-id", "my-run-1",
                            "--output-dir", str(tmp_path)])
        assert result == 0


def _ns_from_argv(argv):
    """测试内 argv→namespace 解析器（模块级，供 homology/receipt 测试复用）：
    bool 标志/数值/浮点字段按 runner argparse 类型还原。"""
    import types
    ns = {}
    flags = {"--model-runner", "--resume"}
    i = 1  # 跳过 python -m 前缀
    while i < len(argv):
        a = argv[i]
        if a in ("-m", "benchmark.runners.run_benchmark") or a.endswith("python") or a.endswith("python.exe"):
            i += 1
            continue
        if a in flags:
            ns[a.lstrip("-").replace("-", "_")] = True
            i += 1
            continue
        if a.startswith("--"):
            key = a.lstrip("-").replace("-", "_")
            ns[key] = argv[i + 1]
            i += 2
            continue
        i += 1
    for k in ("temperature", "sample_temperature"):
        if k in ns:
            ns[k] = float(ns[k])
    for k in ("n_samples", "repeat_idx", "max_cases", "scheduled_calls", "hard_cap"):
        if k in ns:
            ns[k] = int(ns[k])
    # v14：argv 未显式携带的字段补 runner argparse 默认值——build_resume_manifest
    # 直接读 sample_temperature/n_samples，缺省会 AttributeError（审核 P0-3）
    ns.setdefault("sample_temperature", 0.4)
    ns.setdefault("n_samples", 1)
    ns.setdefault("attempt_stage", "main")
    ns.setdefault("aggregate", "majority")
    ns.setdefault("as_of_date", "")
    ns.setdefault("case_ids_file", None)
    ns.setdefault("ziwei_arm", None)
    return types.SimpleNamespace(**ns)


class TestManifestHomology:
    """同源性（v13 新增）：_build_runner_cmd 产出的 argv 与 _slice_runner_args
    重建的 namespace 生成完全相同的 manifest——防两路配置漂移。"""

    def test_runner_cmd_vs_slice_args_manifest_equal(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as orch
        import benchmark.runners.run_benchmark as rb
        from benchmark.runners.profiles import resolve_profile
        import types, json
        from pathlib import Path

        for year in ("2024",):
            ds = tmp_path / f"ds{year}.jsonl"
            ds.write_text("\n".join(f'{{"case_id":"c{i}"}}' for i in range(40)) + "\n",
                          encoding="utf-8")
            sched = orch._build_schedule(str(tmp_path / "run"), years=[year],
                                         dataset_paths={year: str(ds)})
            for sl in sched["slices"]:
                Path(sl["output_dir"]).mkdir(parents=True, exist_ok=True)  # v14：cmd 会写 case_ids.json
                argv = orch._build_runner_cmd(sl, "p", "m")
                ns = _ns_from_argv(argv)
                profile = resolve_profile(sl["profile"], orch.FROZEN_CHART_SCHEMA)
                m_argv = rb.build_resume_manifest(ns, profile)
                m_args = rb.build_resume_manifest(
                    orch._slice_runner_args(sl, "p", "m"), profile)
                assert m_argv == m_args, f"{sl['slice_id']} manifest 漂移"

    def test_smoke_homology(self, tmp_path, monkeypatch):
        """smoke 命令与 manifest 同为 hard_cap=10/max_cases=2/scheduled=6（审核中优）。"""
        import scripts.phase6_6b2_orchestrator as orch
        import benchmark.runners.run_benchmark as rb
        from benchmark.runners.profiles import resolve_profile
        ds = tmp_path / "ds2024.jsonl"
        ds.write_text("\n".join(f'{{"case_id":"c{i}"}}' for i in range(40)) + "\n",
                      encoding="utf-8")
        sl = {"slice_id": "smoke", "year": "2024", "repeat": 0, "group": "smoke",
              "arm": "dual", "case_ids": ["c0", "c1"],
              "output_dir": str(tmp_path / "smoke"),
              "detail_path": str(tmp_path / "smoke" / "detail.jsonl"),
              "events_path": str(tmp_path / "smoke" / "detail.events.jsonl"),
              "dataset_path": str(ds),
              "case_ids_file": str(tmp_path / "smoke" / "case_ids.json"),
              "profile": "baziqa_xjz_dual", "method": "dual_system",
              "scheduled_calls": orch.SMOKE_SCHEDULED,
              "hard_cap": orch.SMOKE_HARD_CAP, "max_cases": orch.SMOKE_CASES_PER_GROUP}
        argv = orch._build_runner_cmd(sl, "p", "m")
        ns = _ns_from_argv(argv)
        profile = resolve_profile(sl["profile"], orch.FROZEN_CHART_SCHEMA)
        m_argv = rb.build_resume_manifest(ns, profile)
        m_args = rb.build_resume_manifest(orch._slice_runner_args(sl, "p", "m"), profile)
        assert m_argv == m_args
        assert m_args["hard_cap"] == 10 and m_args["scheduled_calls"] == 6
        assert ns.max_cases == 2


class TestGateReceipt:
    """receipt 发布/校验（v17）：真实最小 audit_index.json + SHA 验证 + 全字段交叉校验。"""

    def _make_receipt_archive(self, tmp_path, code_fp, run_id="t", stage="dev",
                              provider="p", model="m", verdict="PROMOTE_CANDIDATE"):
        arch = tmp_path / "archive"
        arch.mkdir()
        audit = {"code_fingerprint": code_fp, "run_id": run_id, "stage": stage,
                 "provider": provider, "model": model, "gate_verdict": verdict}
        (arch / "audit_index.json").write_text(json.dumps(audit), encoding="utf-8")
        return arch

    def _make_receipt(self, arch, code_fp, run_id="t", stage="dev",
                      provider="p", model="m", verdict="PROMOTE_CANDIDATE"):
        return {"verdict": verdict, "stage": stage, "run_id": run_id,
                "archive_dir": str(arch),
                "audit_index_sha256": _sha256_file(str(arch / "audit_index.json")),
                "provider": provider, "model": model, "code_fingerprint": code_fp,
                "dataset_sha256": {"2024": "x"}}

    def test_receipt_roundtrip_and_validate(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        code_fp = orch._compute_experiment_code_fingerprint()
        arch = self._make_receipt_archive(tmp_path, code_fp)
        receipt = self._make_receipt(arch, code_fp)
        gates = tmp_path / "gates"
        gates.mkdir()
        (gates / "dev_gate.json").write_text(json.dumps(receipt), encoding="utf-8")
        rec = orch.check_stage_gate("reuse", gate_root=str(gates), provider="p", model="m")
        assert rec["verdict"] == "PROMOTE_CANDIDATE"

    def test_rejects_missing_audit_index(self, tmp_path):
        import scripts.phase6_6b2_orchestrator as orch
        arch = tmp_path / "archive"
        arch.mkdir()  # 无 audit_index.json
        receipt = {"verdict": "PROMOTE_CANDIDATE", "stage": "dev", "run_id": "t",
                   "archive_dir": str(arch), "audit_index_sha256": "x",
                   "provider": "p", "model": "m", "code_fingerprint": "y",
                   "dataset_sha256": {}}
        gates = tmp_path / "gates"
        gates.mkdir()
        (gates / "dev_gate.json").write_text(json.dumps(receipt), encoding="utf-8")
        with pytest.raises(SystemExit):
            orch.check_stage_gate("reuse", gate_root=str(gates), provider="p", model="m")

    def test_rejects_stale_provider(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        code_fp = orch._compute_experiment_code_fingerprint()
        # audit 和 receipt 一致为 other-provider，但当前请求 provider="p"
        arch = self._make_receipt_archive(tmp_path, code_fp, provider="other-provider")
        receipt = self._make_receipt(arch, code_fp, provider="other-provider")
        gates = tmp_path / "gates"
        gates.mkdir()
        (gates / "dev_gate.json").write_text(json.dumps(receipt), encoding="utf-8")
        with pytest.raises(SystemExit):
            orch.check_stage_gate("reuse", gate_root=str(gates), provider="p", model="m")

    def test_rejects_run_id_mismatch(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        code_fp = orch._compute_experiment_code_fingerprint()
        arch = self._make_receipt_archive(tmp_path, code_fp, run_id="run-1")
        receipt = self._make_receipt(arch, code_fp, run_id="run-2")
        gates = tmp_path / "gates"
        gates.mkdir()
        (gates / "dev_gate.json").write_text(json.dumps(receipt), encoding="utf-8")
        with pytest.raises(SystemExit):
            orch.check_stage_gate("reuse", gate_root=str(gates), provider="p", model="m")

    def test_rejects_stage_mismatch(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        code_fp = orch._compute_experiment_code_fingerprint()
        arch = self._make_receipt_archive(tmp_path, code_fp, stage="reuse")
        receipt = self._make_receipt(arch, code_fp, stage="dev")
        gates = tmp_path / "gates"
        gates.mkdir()
        (gates / "dev_gate.json").write_text(json.dumps(receipt), encoding="utf-8")
        with pytest.raises(SystemExit):
            orch.check_stage_gate("reuse", gate_root=str(gates), provider="p", model="m")

    def test_rejects_audit_gate_verdict_drift(self, tmp_path, monkeypatch):
        import scripts.phase6_6b2_orchestrator as orch
        code_fp = orch._compute_experiment_code_fingerprint()
        arch = self._make_receipt_archive(tmp_path, code_fp, verdict="PASS")
        receipt = self._make_receipt(arch, code_fp, verdict="PROMOTE_CANDIDATE")
        gates = tmp_path / "gates"
        gates.mkdir()
        (gates / "dev_gate.json").write_text(json.dumps(receipt), encoding="utf-8")
        with pytest.raises(SystemExit):
            orch.check_stage_gate("reuse", gate_root=str(gates), provider="p", model="m")
```

（`_ns_from_argv` 为模块级测试辅助（定义于 TestManifestHomology 之前），bool 标志/数值/浮点字段按 runner argparse 类型还原；`tmp_path_global` 是测试内简单的全局传递，实施时可用实例属性替代。）

- [ ] **Step 2: 实现（完整代码）**

```python
def _run_dev_reuse(run_dir, gate_root, archive_root, dataset_paths, provider, model,
                   stage, resume=False):
    """dev/reuse 公共执行链（v14）：smoke（仅 dev）→ schedule → ledger（run 级隔离）→
    逐 slice 执行+完整性 → merge → gate → 报告 → 归档自验 → **原子发布带指纹的 gate receipt**。

    v14 顺序纪律（审核 P0-2）：receipt 在归档自验成功后才发布——报告/归档失败不会留下
    可用的 PROMOTE/PASS 文件。receipt 携带 verdict/stage/archive_dir/audit_index_sha256/
    provider/model/code_fingerprint/dataset_sha256，供 check_stage_gate 字段级校验。
    run 隔离：ledger 在 runs/<run_id>/ 下，gates/archive 在 experiment root 下。"""
    if stage == "reuse":
        code_fp = _compute_experiment_code_fingerprint()
        check_stage_gate("reuse", gate_root=gate_root, provider=provider, model=model,
                         current_code_fingerprint=code_fp)
    if stage == "dev":
        smoke_dir = Path(run_dir) / "smoke"
        case_ids = _smoke_case_ids(dataset_paths)
        state = determine_smoke_state(smoke_dir, expected_case_ids=case_ids)
        if state == "blocked_corrupt":
            raise SystemExit("smoke 损坏（blocked_corrupt），排查后续跑")
        if state != "completed":
            _run_smoke_slice(smoke_dir, dataset_paths, provider, model)
        verify_smoke_completed(smoke_dir, expected_case_ids=case_ids)
    schedule = _build_schedule(run_dir, years=sorted(dataset_paths), dataset_paths=dataset_paths)
    ledger = BudgetLedger6B2(str(Path(run_dir) / "ledger.json"),
                             global_hard_cap=schedule["global_hard_cap"],
                             slice_min=8, slice_max=26)
    for sl in schedule["slices"]:
        _run_slice(sl, ledger, provider, model)
    rows = _merge_all_details(schedule)
    gate = compute_gate(rows, stage=stage)
    b1c = load_b1c_advisory()
    report = generate_report(gate, rows, schedule, ledger, b1c, Path(run_dir) / "report")
    archive = generate_archive(schedule, ledger, run_dir, provider, model, gate,
                               archive_root=archive_root, dataset_paths=dataset_paths,
                               run_id=Path(run_dir).name)
    # 归档自验成功后才发布 receipt（含 smoke 账本并入审计：中优项）
    smoke_ledger_path = Path(run_dir) / "smoke" / "ledger.json"
    smoke_attempted = None
    if smoke_ledger_path.exists():
        smoke_attempted = BudgetLedger6B2(
            str(smoke_ledger_path), global_hard_cap=SMOKE_HARD_CAP,
            slice_min=1, slice_max=SMOKE_HARD_CAP).total_attempted
    audit_path = Path(str(archive)) / "audit_index.json"
    if not audit_path.exists():
        raise SystemExit(f"receipt 拒绝发布: audit_index.json 缺失 ({audit_path})")
    audit_index = json.loads(audit_path.read_text(encoding="utf-8"))
    code_fp = _compute_experiment_code_fingerprint()
    if audit_index.get("code_fingerprint") != code_fp:
        raise SystemExit("receipt 拒绝发布: audit_index 与当前代码指纹不一致")
    if audit_index.get("run_id") != Path(run_dir).name:
        raise SystemExit(f"receipt 拒绝发布: audit_index.run_id ({audit_index.get('run_id')}) != 当前 run_id ({Path(run_dir).name})")
    receipt = {
        "stage": stage, "run_id": Path(run_dir).name, "verdict": gate.get("verdict"),
        "archive_dir": str(archive),
        "audit_index_sha256": _sha256_file(str(audit_path)),
        "provider": provider, "model": model,
        "code_fingerprint": code_fp,          # v15：与 archive 同一函数（_git_head 未定义）
        "dataset_sha256": {y: _sha256_file(p) for y, p in dataset_paths.items()},
        "smoke_attempted": smoke_attempted,
        **{k: v for k, v in gate.items() if k.startswith(("delta", "min_year"))},
    }
    Path(gate_root).mkdir(parents=True, exist_ok=True)
    receipt_path = Path(gate_root) / f"{stage}_gate.json"
    tmp = receipt_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, receipt_path)
    return {"status": "OK", "stage": stage, "gate": gate, "report": report,
            "archive": archive, "receipt": str(receipt_path)}


def run_dev(run_dir, gate_root, archive_root, dataset_paths, provider, model, resume=False):
    """2024/2025 dev gate 执行链（run_dir = runs/<run_id>，独立账本）。"""
    return _run_dev_reuse(run_dir, gate_root, archive_root, dataset_paths,
                          provider, model, stage="dev", resume=resume)


def run_reuse(run_dir, gate_root, archive_root, dataset_paths, provider, model, resume=False):
    """2021/2022 复用验证执行链（前置：dev receipt 准入；gate：Δ_2021/Δ_2022 ≥ +2pp）。"""
    return _run_dev_reuse(run_dir, gate_root, archive_root, dataset_paths,
                          provider, model, stage="reuse", resume=resume)


def _validate_run_id(run_id):
    """校验 run-id 为安全路径组件：字母/数字/点/下划线/连字符，拒绝 . 和 ..。"""
    if run_id in (".", ".."):
        raise SystemExit(f"run-id 无效: {run_id!r}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise SystemExit(f"run-id 包含非法字符: {run_id!r}")

def main(argv=None) -> int:
    """CLI：--stage dev|reuse|final-2023 --run-id --provider --model [--resume]。

    v14 run 隔离布局（审核 P0-2）：
        <output_dir>/            ← experiment root
        ├── gates/               ← 阶段准入 receipt（共享）
        ├── archive/             ← 归档（共享）
        └── runs/<run_id>/       ← 本 run 工作区（ledger/schedule/slices/smoke）
    --run-id 参与 runs 子目录（dev/reuse 各自独立账本，不再共享 ledger）。"""
    import argparse
    p = argparse.ArgumentParser(description="Phase 6 6B2 编排器")
    p.add_argument("--stage", required=True, choices=["dev", "reuse", "final-2023"])
    p.add_argument("--run-id", required=True)
    p.add_argument("--provider", default="deepseek")
    p.add_argument("--model", default="deepseek-chat")
    p.add_argument("--output-dir", default=".tmp/phase6/6b2")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args(argv)
    _validate_run_id(args.run_id)
    exp_root = Path(args.output_dir)
    run_dir = exp_root / "runs" / args.run_id
    gate_root = str(exp_root / "gates")
    archive_root = str(exp_root / "archive")
    ds_dir = exp_root / "datasets"
    if args.stage == "dev":
        paths = {y: str(ds_dir / f"baziqa_contest8_{y}_holdout_enriched.jsonl") for y in ("2024", "2025")}
        result = run_dev(str(run_dir), gate_root, archive_root, paths,
                         args.provider, args.model, resume=args.resume)
    elif args.stage == "reuse":
        paths = {y: str(ds_dir / f"baziqa_contest8_{y}_holdout_enriched.jsonl") for y in ("2021", "2022")}
        result = run_reuse(str(run_dir), gate_root, archive_root, paths,
                           args.provider, args.model, resume=args.resume)
    else:
        # run_2023_final(provider, model, gate_root, archive_root)——签名对齐（v13 修正）
        result = run_2023_final(args.provider, args.model,
                                gate_root=gate_root, archive_root=archive_root)
    print(json.dumps({"status": result.get("status"), "gate": result.get("gate", {}).get("verdict")},
                     ensure_ascii=False))
    return 0


# ---------- smoke 真实实现（v13 补全，替换占位说明） ----------

SMOKE_SCHEDULED = 6         # 2 题 × (bazi+ziwei+judge) 最坏正常调用数（中优修订：重试储备只体现在 hard_cap）
SMOKE_HARD_CAP = 10         # 含重试储备；独立小账本，计入预算审计


def _smoke_case_ids(dataset_paths) -> list:
    """smoke 用例：2024 数据集前 2 个 case_id（确定性，与 dev group_a 起始同源）。"""
    ids = []
    with open(dataset_paths["2024"], encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cid = json.loads(line).get("case_id")
                if cid:
                    ids.append(cid)
            if len(ids) == SMOKE_CASES_PER_GROUP:
                break
    if len(ids) != SMOKE_CASES_PER_GROUP:
        raise SystemExit(f"smoke 拒绝：2024 数据集不足 {SMOKE_CASES_PER_GROUP} 题")
    return ids


def _run_smoke_slice(smoke_dir, dataset_paths, provider, model):
    """真实 smoke：2 题走 dual 链（bazi→ziwei→分歧 judge）。

    v13：独立小账本（scheduled 6 = 2 题×3 stage 最坏 / hard_cap 10，slice_min=1——预算可审计）；
    完整性用 smoke 自有口径（每题 bazi+ziwei 恰 1 行、judge 按分歧基数、
    终态 5 态全集），不经 8 题切片门禁与 dual 16 次下限（_run_slice 的
    integrity="smoke" 分支）。写入 stage 总账本的 smoke slice 记录。"""
    case_ids = _smoke_case_ids(dataset_paths)
    smoke_dir = Path(smoke_dir)
    smoke_dir.mkdir(parents=True, exist_ok=True)
    ledger = BudgetLedger6B2(str(smoke_dir / "ledger.json"),
                             global_hard_cap=SMOKE_HARD_CAP,
                             slice_min=1, slice_max=SMOKE_HARD_CAP)
    sl = {"slice_id": "smoke", "year": "2024", "repeat": 0, "group": "smoke",
          "arm": "dual", "case_ids": case_ids,
          "output_dir": str(smoke_dir),
          "detail_path": str(smoke_dir / "detail.jsonl"),
          "events_path": str(smoke_dir / "detail.events.jsonl"),
          "dataset_path": dataset_paths["2024"],
          "case_ids_file": str(smoke_dir / "case_ids.json"),
          "profile": "baziqa_xjz_dual", "method": "dual_system",
          # v15：预算/题数冻结进 slice（scheduled 6 = 2 题×3 stage 最坏；cap 10 含重试储备）
          "scheduled_calls": SMOKE_SCHEDULED,
          "hard_cap": SMOKE_HARD_CAP, "max_cases": SMOKE_CASES_PER_GROUP}
    _run_slice(sl, ledger, provider, model, integrity="smoke")
```

**`_run_slice` 配套修改（Task 11 登记）**：签名加 `integrity="slice"` 参数；`integrity="smoke"` 时跳过 8 题切片门禁与 B1-a′/dual 预期范围校验，改用 smoke 口径（每题 bazi+ziwei 恰 1 行、judge ∈ {0,1} 按分歧、终态 5 态全集）。

- [ ] **Step 3: 运行确认全绿**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_phase6_6b2.py -q -k "RunDevChain or ManifestHomology or GateReceipt"`
Expected: 14 passed（dev 链顺序/冒烟阻塞/reuse 准入/reuse stage/CLI 拒绝未知 stage/CLI 拒绝恶意 run-id + manifest 同源性×2 + receipt roundtrip/缺失 audit/stale provider/run_id 漂移/stage 漂移/gate_verdict 漂移）

- [ ] **Step 4: Commit（精确路径）**

```powershell
git add scripts/phase6_6b2_orchestrator.py tests/test_phase6_6b2.py
git commit -m "feat(6b2): dev/reuse execution chain + CLI entry (smoke→schedule→ledger→integrity→gate→report)"
```

---
## 自审清单（对照 spec §7 + 审核 P0/P1）

- [ ] §7.1.1 先解析后裁决、judge 仅分歧 -> Task 6
- [ ] §7.1.2 source_label_blinded + SHA-256 swap + 不声称完全盲法 -> Task 1/6
- [ ] §7.1.3 judge 输入（选项+理由）-> Task 1/6
- [ ] §7.1.4 单侧 unresolved 进 judge、双侧不调 -> Task 6
- [ ] §7.1.5 judge 失败计 unresolved -> Task 6 (judge_unresolved)
- [ ] §7.2 落点 -> Task 1/9
- [ ] §7.3 同期 B1-a′、B1-c advisory、dev gate 三条件、复用验证 -> Task 10/13/16
- [ ] §7.4 2023 终验 + 密封 -> Task 15/16
- [ ] §7.5 预算（分歧率按实测 0.579 冻结，最坏情况 960/1060 不变）-> Task 10
- [ ] §4.4.2 双列预算 + BLOCKED_INCOMPLETE -> Task 11/17
- [ ] P0-1 _build_runner_cmd: sys.executable -m + --model-runner 布尔 + baziqa_xjz_reasoned -> Task 11
- [ ] P0-2 artifact 路径: details.events.jsonl + details.manifest.json -> Task 10/11
- [ ] P0-3 resume 幂等 + 指纹验证 + --resume 标志 + fail-closed + finally 锁释放 -> Task 11
- [ ] P0-4 空 schedule_hash 视为未初始化 -> Task 17
- [ ] P0-5 测试修复: test_build_runner_cmd_dual / test_archive_audit / test_reuse_years / test_2023_chain -> Task 11/16/17
- [ ] P1-1 删重复 enrich -> Task 6（_dual_write_detail 不调 enrich_row）
- [ ] P1-2 fingerprint 全函数范围 -> Task 4
- [ ] P1-3 B1-c 读 attempt_key[2] + 冻结预期 SHA -> Task 13
- [ ] P1-4 冻结 gate 聚合算法 + 40 题唯一性验证 -> Task 13
- [ ] P1-5 ziwei 字节等价测试 -> Task 1
- [ ] P1-6 scheduled=24（非 16）-> Task 6 测试
- [ ] P1-7 BudgetLedger6B2._load 拒绝 hard_cap 不一致 -> Task 11
- [ ] P1-8 record_slice_completed 验证调用计数范围 -> Task 11
- [ ] P1-9 _compute_dataset_hashes 仅哈希 schedule 确切路径 -> Task 16
- [ ] P1-10 _run_slice 验证 runner manifest + 终态行 -> Task 11
- [ ] P1-11 --output-dir / --as-of-date / --chart-schema-version 冻结进命令 -> Task 11
- [ ] 放行条件：真实 schema dev/reuse/final 三阶段 gate 测试 -> Task 13
- [ ] 放行条件：ROLLBACK 归档 + BLOCKED 拒绝 -> Task 17
- [ ] 放行条件：2023 RUNNING 恢复 + 归档成功 FINALIZED + 失败保持 RUNNING -> Task 15



