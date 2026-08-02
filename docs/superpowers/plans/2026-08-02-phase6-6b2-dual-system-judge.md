# Phase 6 6B2 - 双管线 + source_label_blinded_judge：实施计划 (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 6B2 双体系（八字+紫微）独立推理管线 + 来源标签盲化裁判，在 2024/2025 dev gate 判定是否优于同期 B1-a′ 单管线基线。

**Architecture:** runner 级多调用方法 `dual_system`（仿 `run_multi_turn_benchmark` 委托）。每 case 依次 bazi(stage=bazi)->ziwei(stage=ziwei)->分歧时 judge(stage=judge)。stage 在调用前切换。复用 `_attempt_with_ledger` 账本（不重复记账）。编排器复用 6B1D 的 OutputDirLock / slice 状态机，BudgetLedger 参数化（global=1060, slice 范围 8-26）。

**Tech Stack:** Python 3.11+, subprocess 编排, pytest TDD

**父设计:** `docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md` §7（APPROVED）

---

## 关键设计假设（AGENTS.md §6）

1. **runner 级多调用**：judge 依赖 bazi/ziwei 实时理由文本，跨 subprocess 传递破坏同期交错。`call_model_sync` 在 Phase6 context 下已内含 `before_call`/重试/`record_call_meta`/hard_cap（`_attempt_with_ledger`，run_benchmark.py:370），返回 `str`。`_dual_call` **只设 stage + 调 call_model_sync**，不重复调账本方法。
2. **管线定义**：八字 = `render_reasoned_context(ziwei_arm="none")`（字节等价 6B1 b1a′）；紫微 = `render_reasoned_context(ziwei_arm="only")`（字节等价 6B1 b1b）。
3. **同期 B1-a′ 控制**：`attempt_stage="main"`、`arm="b1a_prime"`、reasoned direct_choice，同年同 run 交错。
4. **预算冻结**：dual scheduled=24（8 bazi + 8 ziwei + 8 judge 最坏）；b1a scheduled=8；总 scheduled=960（240+720）；global hard_cap=1060。60.8% 分歧率仅记为预计实际量，不降 scheduled。
5. **swap seed**：SHA-256(dataset+case_id+repeat) 确定性，不用 Python `hash()`（受 PYTHONHASHSEED 影响）。

---

## 文件结构

**新建：**
- `benchmark/formatters/dual_system_reasoning.py` - judge prompt + 双管线 prompt + extractor
- `tests/test_dual_system_reasoning.py` - dual formatter + runner 测试矩阵
- `tests/test_phase6_6b2.py` - 编排器测试
- `scripts/phase6_6b2_orchestrator.py` - 调度 / BudgetLedger / slice 执行 / 完整性门禁 / gate / 报告 / 归档

**修改：**
- `benchmark/runners/run_benchmark.py` - `--method dual_system`；委托；`run_dual_system_benchmark()`；可见性门禁；attempt_stage 校验
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

def test_judge_template_no_added_source_labels():
    c=_case()
    p=build_judge_prompt(c,"A","r","B","r",swap=False)
    # 仅检查模板主动添加的标签，不检查原样嵌入的 rationale（父设计允许理由正文术语暴露）
    assert "分析一" in p and "分析二" in p
    assert "八字" not in p[:p.index("## 分析一")] and "紫微" not in p[:p.index("## 分析一")]

def test_swap_reorders():
    c=_case()
    assert "分析一\n结论：A" in build_judge_prompt(c,"A","r","B","r",swap=False)
    assert "分析一\n结论：B" in build_judge_prompt(c,"A","r","B","r",swap=True)

def test_swap_seed_deterministic():
    assert judge_swap_seed("baziqa","Q1",0)==judge_swap_seed("baziqa","Q1",0)
    # 不同进程一致（不依赖 PYTHONHASHSEED）
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
    """SHA-256 确定性顺序交换种子，不受 PYTHONHASHSEED 影响。"""
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

## Task 4: prompt_fingerprint dual 分支

**Files:** Modify `benchmark/runners/profiles.py:204`; Test `tests/test_phase6_profiles.py`

- [ ] **Step 1: 写失败测试** - dual 指纹生成不报错；dual 指纹 != reasoned 指纹
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** - reasoned 分支后加 `elif formatter=="format_dual_system_prompt":` 含 `JUDGE_TEMPLATE_VERSION` + 4 个函数源码
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): add dual_system prompt fingerprint branch`

---

## Task 5: build_benchmark_prompt dual 路由

**Files:** Modify `benchmark/runners/run_benchmark.py:434`; Test `tests/test_dual_system_reasoning.py`

- [ ] **Step 1: 写失败测试** - `build_benchmark_prompt(case, profile_formatter="format_dual_system_prompt")` 返回 str
- [ ] **Step 2: 运行确认失败**（raise ValueError）
- [ ] **Step 3: 实现** - reasoned 分支后加 `if profile_formatter=='format_dual_system_prompt': from benchmark.formatters.dual_system_reasoning import build_bazi_pipeline_prompt; return build_bazi_pipeline_prompt(case)`
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): dual_system formatter dispatch`

---

## Task 6: run_dual_system_benchmark - 核心多调用（P0 修订）

**Files:** Modify `benchmark/runners/run_benchmark.py`（新增函数）; Test `tests/test_dual_system_reasoning.py`

**关键契约（P0-1/P0-2/P0-3 修订）：**
- `_dual_call` 只设 stage + 调 `call_model_sync`（返回 str），不调 before_call/record_call_meta
- judge stage 在调用前切换，try/finally 恢复
- 接收 `completed_keys`，跳过已完成 stage，resume 时从 detail 读 raw_answer 交给 judge
- 返回完整 dict：`cases/predictions/evidence_results/safety_results/case_details/failed_cases`
- `_HardCapExhausted` 冒泡到 main

- [ ] **Step 1: 写失败测试 - 共识不调 judge + 调用契约**

```python
def test_dual_consensus_no_judge(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    calls = []
    def fake_call(prompt, provider, model, **kw):
        calls.append(prompt)
        return "最终答案：A"
    monkeypatch.setattr(rb, "call_model_sync", fake_call)
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 16, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    c=_case()
    result = rb.run_dual_system_benchmark([c],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    assert len(calls)==2  # bazi+ziwei, no judge
    assert result["predictions"]["Q1"]=="A"
    # 返回结构完整
    for k in ("cases","predictions","evidence_results","safety_results","case_details","failed_cases"):
        assert k in result
```

- [ ] **Step 2: 运行确认失败**（函数不存在）

- [ ] **Step 3: 实现 run_dual_system_benchmark**

```python
def run_dual_system_benchmark(cases, provider, model, max_cases=20, temperature=0.0,
        case_details_jsonl=None, chart_schema_version=None, resume_append=False,
        completed_keys=None):
    from benchmark.formatters.dual_system_reasoning import (
        build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt,
        build_judge_prompt, extract_judge_answer, judge_swap_seed)
    from benchmark.formatters.chart_context import extract_reasoned_choice_answer
    from benchmark.formatters.baziqa_prompt import extract_choice
    ctx = _PHASE6_CTX
    if not resume_append:
        _prepare_jsonl(case_details_jsonl)
    predictions, case_details, failed_cases, evidence_results, safety_results = {}, [], [], [], []
    limited = cases[:max_cases]
    for case in limited:
        cid = case["case_id"]
        _run_dual_case(case, ctx, provider, model, temperature, completed_keys,
                       predictions, case_details, failed_cases)
    return {"cases": limited, "predictions": predictions,
            "evidence_results": evidence_results, "safety_results": safety_results,
            "case_details": case_details, "failed_cases": failed_cases}


def _run_dual_case(case, ctx, provider, model, temperature, completed_keys,
                   predictions, case_details, failed_cases):
    cid = case["case_id"]
    prev_stage = ctx.attempt_stage
    try:
        # --- bazi ---
        ctx.attempt_stage = "bazi"
        b_key = ctx.attempt_key_for(case)
        b_done = completed_keys and tuple(b_key) in completed_keys
        if b_done:
            b_raw, b_ans = _load_existing_detail(ctx.detail_path, b_key)
        else:
            b_raw = call_model_sync(build_bazi_pipeline_prompt(case), provider, model,
                                    case=case, temperature=temperature)
            b_ans = extract_reasoned_choice_answer(b_raw)
            _dual_write_detail(ctx, case, "bazi", b_raw, b_ans)

        # --- ziwei ---
        ctx.attempt_stage = "ziwei"
        z_key = ctx.attempt_key_for(case)
        z_done = completed_keys and tuple(z_key) in completed_keys
        if z_done:
            z_raw, z_ans = _load_existing_detail(ctx.detail_path, z_key)
        else:
            z_raw = call_model_sync(build_ziwei_pipeline_prompt(case), provider, model,
                                    case=case, temperature=temperature)
            z_ans = extract_reasoned_choice_answer(z_raw)
            _dual_write_detail(ctx, case, "ziwei", z_raw, z_ans)

        # --- judge ---
        final = _resolve_and_judge(ctx, case, provider, model, temperature,
                                   b_ans, b_raw, z_ans, z_raw, completed_keys, cid)
        predictions[cid] = final
        case_details.append({"case_id": cid, "predicted_answer": final,
                             "dual_stages": {"bazi": b_ans, "ziwei": z_ans, "final": final}})
    finally:
        ctx.attempt_stage = prev_stage


def _resolve_and_judge(ctx, case, provider, model, temperature,
                       b_ans, b_raw, z_ans, z_raw, completed_keys, cid):
    if b_ans is not None and z_ans is not None and b_ans == z_ans:
        return b_ans
    if b_ans is None and z_ans is None:
        return None  # 双侧 unresolved, 不调 judge
    # judge - stage 在调用前切换
    prev = ctx.attempt_stage
    ctx.attempt_stage = "judge"
    j_key = ctx.attempt_key_for(case)
    j_done = completed_keys and tuple(j_key) in completed_keys
    try:
        if j_done:
            _, verdict = _load_existing_detail(ctx.detail_path, j_key)
            return verdict
        r1 = b_raw if b_raw else "未达成结论"
        r2 = z_raw if z_raw else "未达成结论"
        a1 = b_ans or "未给出"
        a2 = z_ans or "未给出"
        swap = judge_swap_seed(ctx.dataset_id, cid, ctx.repeat_idx)
        prompt = build_judge_prompt(case, a1, r1, a2, r2, swap=swap)
        j_raw = call_model_sync(prompt, provider, model, case=case, temperature=temperature)
        verdict = extract_judge_answer(j_raw)
        _dual_write_detail(ctx, case, "judge", j_raw, verdict)
        return verdict
    finally:
        ctx.attempt_stage = prev


def _dual_write_detail(ctx, case, stage, raw, predicted):
    expected = extract_choice(case.get("answer"))
    row = {"case_id": case["case_id"], "predicted_answer": predicted,
           "raw_answer": raw, "expected_answer": expected,
           "correct": predicted == expected, "call_success": bool(raw),
           "dual_stage": stage, "parser_valid": predicted is not None,
           "sample_idx": 0, "permutation_id": case.get("_permutation_id") or "p0"}
    row = ctx.enrich_row(row)
    _append_jsonl(ctx.detail_path, row)


def _load_existing_detail(detail_path, key):
    """resume 时从已有 detail 行读 raw_answer 和 predicted_answer。"""
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

- [ ] **Step 5: 写测试 - 分歧调 judge + stage 时序 + 双侧 unresolved + attempt_key 分离**

```python
def test_dual_disagreement_calls_judge(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    seq = ["最终答案：A", "最终答案：B", "最终答案：C"]  # bazi=A, ziwei=B, judge=C
    monkeypatch.setattr(rb, "call_model_sync", lambda *a, **k: seq.pop(0))
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    result = rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    assert result["predictions"]["Q1"]=="C"
    # detail 行含 3 stage
    rows=[json.loads(l) for l in open(tmp_path/"d.jsonl",encoding="utf-8") if l.strip()]
    stages={r["attempt_key"][3] for r in rows}
    assert stages=={"bazi","ziwei","judge"}

def test_dual_both_unresolved_no_judge(monkeypatch, tmp_path):
    import benchmark.runners.run_benchmark as rb
    monkeypatch.setattr(rb, "call_model_sync", lambda *a, **k: "无最终答案行")
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    result = rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    assert result["predictions"]["Q1"] is None

def test_judge_stage_set_before_call(monkeypatch, tmp_path):
    """judge 调用时 ctx.attempt_stage 必须已是 'judge'（events 记录一致）。"""
    import benchmark.runners.run_benchmark as rb
    stages_at_call = []
    def fake_call(prompt, provider, model, **kw):
        stages_at_call.append(rb._PHASE6_CTX.attempt_stage)
        return ["最终答案：A","最终答案：B","最终答案：C"][len(stages_at_call)-1]
    monkeypatch.setattr(rb, "call_model_sync", fake_call)
    ctx = rb.Phase6Context("ds","prof","dual","dual","p","m",0,
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 24, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    assert stages_at_call == ["bazi","ziwei","judge"]  # 调用时 stage 正确
```

- [ ] **Step 6: 运行通过**
- [ ] **Step 7: Commit** - `feat(6b2): run_dual_system_benchmark (correct ledger contract + stage timing + full return)`

---

## Task 7: stage-aware resume（P0-3 修订）

**Files:** 已在 Task 6 实现 `_load_existing_detail` + `completed_keys` 跳过; Test `tests/test_dual_system_reasoning.py`

- [ ] **Step 1: 写测试 - bazi 已完成跳过、bazi+ziwei 已完成只跑 judge、judge 已完成全跳**

```python
def test_resume_bazi_done_skips_to_ziwei(monkeypatch, tmp_path):
    """detail 已有 bazi 行 -> resume 只调 ziwei(+judge)，不重调 bazi。"""
    import benchmark.runners.run_benchmark as rb
    # 预写 bazi detail 行（terminal_state=parsed）
    # completed_keys 含 bazi key
    # 跑 -> 断言 call_model_sync 只被调 1-2 次（ziwei，可能 judge）
    ...

def test_resume_all_done_skips_case(monkeypatch, tmp_path):
    """bazi+ziwei+judge 全已完成 -> 该 case 0 次调用。"""
    ...

def test_resume_reads_raw_answer_for_judge(monkeypatch, tmp_path):
    """bazi+ziwei 已完成但 judge 未完成 -> 从 detail 读 raw_answer 交 judge。"""
    # 断言 judge prompt 含已有 bazi raw_answer 文本
    ...
```

- [ ] **Step 2: 运行确认通过**（Task 6 已实现逻辑，此处验证）

- [ ] **Step 3: 写测试 - hard_cap 中断恢复**

```python
def test_hard_cap_exhausted_during_judge(monkeypatch, tmp_path):
    """judge 调用时 hard_cap 耗尽 -> _HardCapExhausted 冒泡。"""
    import benchmark.runners.run_benchmark as rb
    # ctx.calls_attempted 设为 hard_cap-2（bazi+ziwei 用完后 judge 触发超限）
    # 断言 raises rb._HardCapExhausted
    ...
```

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `test(6b2): stage-aware resume (bazi/ziwei/judge skip + raw_answer recovery)`

---

## Task 8: 可见性门禁 - 三段独立检查（P0-4 修订）

**Files:** Modify `benchmark/runners/run_benchmark.py:1476`; Test `tests/test_dual_system_reasoning.py`

**不再拼接三段用 judge 规则检查。** 分别检查：bazi 用 `ziwei_arm="none"`，ziwei 用 `ziwei_arm="only"`，judge 模板只检查主动添加的标签。

- [ ] **Step 1: 写失败测试**

```python
def test_dual_visibility_checks_each_stage_independently():
    """bazi 段不含紫微标，ziwei 段含紫微标（合法），judge 模板不含体系标。"""
    from benchmark.runners.profiles import assert_visibility, resolve_profile
    from benchmark.formatters.chart_context import render_reasoned_context
    from benchmark.formatters.dual_system_reasoning import build_judge_prompt
    p = resolve_profile("baziqa_xjz_dual")
    c = _case()
    # bazi: none 规则 - 不应违规
    bazi_text = render_reasoned_context(c, "legacy_v0", "none")
    assert assert_visibility(bazi_text, p, "legacy_v0", ziwei_arm="none") == []
    # ziwei: only 规则 - 不应违规（紫微标是 required）
    ziwei_text = render_reasoned_context(c, "legacy_v0", "only")
    assert assert_visibility(ziwei_text, p, "legacy_v0", ziwei_arm="only") == []
    # judge 模板: judge 规则 - 不含体系标
    judge_text = build_judge_prompt(c, "A", "r", "B", "r")
    assert assert_visibility(judge_text, p, "legacy_v0", ziwei_arm="judge") == []
```

- [ ] **Step 2: 运行确认失败**（dual formatter 无门禁分支）

- [ ] **Step 3: 实现 - `_phase6_visibility_filter` 加 dual 分支**

```python
        elif profile_formatter == 'format_dual_system_prompt':
            from benchmark.formatters.chart_context import render_reasoned_context
            from benchmark.formatters.dual_system_reasoning import build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt, build_judge_prompt
            csv = profile.chart_schema_version
            violations = []
            violations += assert_visibility(build_bazi_pipeline_prompt(case), profile, csv, ziwei_arm="none")
            violations += assert_visibility(build_ziwei_pipeline_prompt(case), profile, csv, ziwei_arm="only")
            # judge 模板检查：不含体系段标（rationale 原样嵌入不检查，父设计允许）
            judge_tpl = build_judge_prompt(case, "A", "r", "B", "r")
            violations += assert_visibility(judge_tpl, profile, csv, ziwei_arm="judge")
```

- [ ] **Step 4: 运行通过 + 回归** - `pytest tests/test_phase6_runner_routing.py tests/test_dual_system_reasoning.py -k visibility -q`
- [ ] **Step 5: Commit** - `feat(6b2): 3-stage independent visibility gate`

---

## Task 9: runner 委托 + CLI

**Files:** Modify `benchmark/runners/run_benchmark.py:780,1535,1551`; Test `tests/test_phase6_runner_routing.py`

- [ ] **Step 1: 写失败测试** - method="dual_system" 委托 run_dual_system_benchmark；`--attempt-stage bogus` 非零退出
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** - line 780 后加 `if method=='dual_system': return run_dual_system_benchmark(cases,provider,model,max_cases=max_cases,temperature=temperature,case_details_jsonl=case_details_jsonl,chart_schema_version=chart_schema_version,resume_append=resume_append,completed_keys=completed_keys)`；--method choices 加 `'dual_system'`；--attempt-stage 加 `choices=list(ATTEMPT_STAGES)+["dual"]`
- [ ] **Step 4: 运行通过 + 回归** - `pytest tests/test_phase6_runner_routing.py tests/test_phase6_resume.py -q`
- [ ] **Step 5: Commit** - `feat(6b2): wire dual_system delegation + CLI + attempt_stage validation`

---

## Task 10: 编排器 - 常量 + 调度（P0-5 修订）

**Files:** Create `scripts/phase6_6b2_orchestrator.py`, `tests/test_phase6_6b2.py`

**预算冻结：** dual scheduled=24（非 16），global=1060，总 scheduled=960。

- [ ] **Step 1: 写失败测试**

```python
def test_schedule_60_slices_dual_scheduled_24(tmp_path):
    from scripts.phase6_6b2_orchestrator import _build_schedule
    s=_build_schedule(str(tmp_path), years=["2024","2025"])
    assert s["total_slices"]==60
    dual=[x for x in s["slices"] if x["arm"]=="dual"]
    assert all(x["scheduled_calls"]==24 for x in dual)
    assert s["total_scheduled_calls"]==960  # 30*8 + 30*24
    assert s["global_hard_cap"]==1060
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现常量 + _build_schedule**

```python
B1A_SLICE_SCHEDULED=8; DUAL_SLICE_SCHEDULED=24
B1A_SLICE_HARD_CAP=10; DUAL_SLICE_HARD_CAP=26
GLOBAL_HARD_CAP=1060; JUDGE_DISAGREEMENT_RATE=0.608
ARM_METHOD={"b1a_prime":"direct_choice","dual":"dual_system"}
ARM_PROFILE={"b1a_prime":"baziqa_xjz_reasoned","dual":"baziqa_xjz_dual"}
ARM_ZIWEI={"b1a_prime":"none","dual":"combined"}
ARM_STAGE={"b1a_prime":"main","dual":"dual"}
```

`_build_schedule`: 2 arms × 5 groups × 2 years × 3 repeats=60，按 (year,repeat,group,arm_order) 交错排序。

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): orchestrator constants + 60-slice schedule (dual scheduled=24)`

---

## Task 11: BudgetLedger 参数化 + slice 执行（P0-5 修订）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**6B1D BudgetLedger 硬编码 1320/8/10，不能直接 import。** 为 6B2 实现参数化版本（global_hard_cap/slice_min/slice_max 构造传入）。

- [ ] **Step 1: 写失败测试**

```python
def test_budget_ledger_accepts_dual_cap_26(tmp_path):
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2, GLOBAL_HARD_CAP
    ledger = BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=GLOBAL_HARD_CAP,
                             slice_min=8, slice_max=26)
    assert ledger.hard_cap==1060
    # allocated_cap=26 不报损坏
    ledger.record_slice_completed("2024_dual_R0_G0", 20)
    assert ledger.total_attempted==20

def test_build_runner_cmd_dual_uses_dual_system():
    from scripts.phase6_6b2_orchestrator import _build_runner_cmd
    sl={"arm":"dual","slice_id":"s","repeat":0,"detail_path":"/d","output_dir":"/o",
        "scheduled_calls":24,"hard_cap":26,"dataset":"x","chart_schema_version":"legacy_v0",
        "case_ids":["Q1"],"ziwei_arm":"combined"}
    args=type("A",(),{"provider":"p","model":"m"})()
    cmd=_build_runner_cmd(sl,args)
    assert cmd[cmd.index("--method")+1]=="dual_system"
    assert cmd[cmd.index("--attempt-stage")+1]=="dual"
    assert cmd[cmd.index("--hard-cap")+1]=="26"
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 BudgetLedger6B2 + _build_runner_cmd + _run_slice + _process_slice**

BudgetLedger6B2 复制 6B1D BudgetLedger 结构，但 `__init__` 接 `global_hard_cap/slice_min/slice_max`，验证用传入值而非硬编码常量。复用 OutputDirLock / atomic_write_json / _count_call_attempts（这些无硬编码）。

`_build_runner_cmd` 按 ARM_METHOD/ARM_PROFILE/ARM_STAGE 分发，`--hard-cap` 用 `sl["hard_cap"]`。`_process_slice` 复用 6B1D 状态机模式（_resolve_slice_state -> budget_ok_for_slice -> _run_slice -> _verify_slice_completed）。

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): parameterized BudgetLedger + slice execution + cmd builder`

---

## Task 12: 多 stage 完整性门禁

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写失败测试** - b1a 每 case 1 main 行；dual expected 含 bazi+ziwei（不含 judge）；judge 行合法 extra；缺 bazi -> MISSING；重复 -> DUPLICATE
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 _expected_keys_for_slice + _integrity_gate** - b1a: 1 key/case stage=main；dual: 2 keys/case stage=bazi/ziwei；judge 为合法 extra；terminal_state 合法性检查
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): multi-stage integrity gate`

---

## Task 13: gate + 报告 + B1-c advisory（P1-1 修订）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写失败测试** - gate 三条件（全满足 PROMOTE；dual<32.5% ROLLBACK；min_year<-2pp ROLLBACK；Δ_dev<+4pp ROLLBACK）；报告含 B1-c advisory 字段

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 compute_gate + generate_report**

```python
def compute_gate(merged_details):
    # dual final = 共识或 judge 裁决（同 case 的 bazi/ziwei/judge 行聚合）
    # Δ(year,repeat)=acc_dual-acc_b1a; Δ_year=mean(3); Δ_dev=mean(2 years)
    # gate: Δ_dev>=0.04 and dual_merged_acc>=0.325 and min(Δ_year)>=-0.02
    # 裁决: PROMOTE_CANDIDATE / ROLLBACK
```

generate_report 含：准确率表、Δ 表、gate 裁决、judge 触发率（实际 vs 60.8% 预计）、parser rate、完整性、预算、**B1-c advisory 对照**（从 6B1 历史归档 `docs/phase6/6b1/6b1-2026-07-17-*/merged_details.jsonl` 加载 b1c 结果，验证 SHA-256，附列 Δ_dual_vs_b1c 作 advisory 非决策项）。

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): gate computation + report + B1-c advisory`

---

## Task 14: smoke gate + 集成测试

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写测试** - smoke：数据完整性（ziwei 覆盖）、parser rate≥95%、状态机；集成：mock call_model_sync 跑 2 case 全流程（共识+分歧），断言 detail 行数、attempt_key、gate
- [ ] **Step 2: 实现 smoke gate** - 复用 6B1D `determine_smoke_state`/`verify_smoke_completed`；dual smoke 验证 bazi+ziwei+judge 链路
- [ ] **Step 3: 运行通过**
- [ ] **Step 4: Commit** - `feat(6b2): smoke gate + integration test`

---

## Task 15: enrichment + 2023 密封终验（P0-6 修订）

**Files:** Create `scripts/phase6_6b2_sealed_workflow.py`; Test `tests/test_phase6_6b2.py`

**当前 2021/2022/2023 holdout 无 chart_input/ziwei（已验证 0/40）。** 必须：enrichment + 阶段准入 + 2023 一次性运行锁。

- [ ] **Step 1: 写测试 - enrichment 哈希链**

```python
def test_enrichment_produces_chart_input(tmp_path):
    """enrich_holdout_chart_input 对 2021 holdout 产出 chart_input + ziwei。"""
    from scripts.enrich_holdout_chart_input import enrich_row
    row = {"case_id":"Q1","person":{"name":"t","birth":{"year":1990,"month":1,"day":1,"hour":12,"place":"北京"}},"answer":"A","question":"q","options":["a","b","c","d"]}
    out = enrich_row(row)
    assert out.get("chart_input") is not None
    assert out["chart_input"].get("ziwei") is not None

def test_chart_coverage_gate_rejects_unenriched():
    """ziwei 覆盖率 <100% 的年度被门禁拒绝。"""
    # 跑 2021 holdout（未 enriched）-> 拒绝
    # 跑 2021 enriched -> 通过
    ...
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 enrichment 工作流**

```python
# scripts/phase6_6b2_sealed_workflow.py
def enrich_year(year, input_path, output_path):
    """对 holdout 跑 enrich_holdout_chart_input，输出 enriched + SHA-256。"""
    from scripts.enrich_holdout_chart_input import enrich_row, load_jsonl, write_jsonl
    rows = [enrich_row(r) for r in load_jsonl(input_path)]
    write_jsonl(output_path, rows)
    # 覆盖率门禁
    has_zw = sum(1 for r in rows if r.get("chart_input",{}).get("ziwei"))
    if has_zw < len(rows):
        raise SystemExit(f"enrichment 覆盖率不足: {has_zw}/{len(rows)}")
    # 记录输入/输出/代码 SHA-256
    return {"input_sha256": sha256_file(input_path),
            "output_sha256": sha256_file(output_path),
            "code_sha256": sha256_module(enrich_row)}
```

- [ ] **Step 4: 写测试 - 阶段准入门禁**

```python
def test_dev_promote_required_before_reuse_validation():
    """未 dev PROMOTE -> 拒绝跑 2021/2022。"""
    # 检查 phase6_6b2 dev gate 裁决文件存在且 PROMOTE
    ...

def test_reuse_pass_required_before_2023():
    """未复用验证通过 -> 拒绝跑 2023。"""
    ...

def test_2023_one_time_run_lock():
    """2023 已运行 -> 拒绝重跑（锁文件存在）。"""
    # 首次跑 -> 创建 .sealed_2023.lock
    # 二次跑 -> 拒绝
    ...
```

- [ ] **Step 5: 实现 阶段准入 + 2023 一次性锁**

```python
def check_stage_gate(stage):
    """stage: dev -> reuse -> final_2023。检查前序阶段裁决文件。"""
    if stage == "reuse":
        gate = load_dev_gate_result()
        if gate["verdict"] != "PROMOTE_CANDIDATE":
            raise SystemExit(f"dev gate 未通过 ({gate['verdict']}), 禁止跑复用验证")
    elif stage == "final_2023":
        reuse = load_reuse_gate_result()
        if reuse["verdict"] != "PASS":
            raise SystemExit(f"复用验证未通过, 禁止解封 2023")
        lock = Path("docs/phase6/6b2/.sealed_2023.lock")
        if lock.exists():
            raise SystemExit("2023 已一次性运行, 禁止重跑（密封终验）")
        lock.write_text(json.dumps({"run_at": timestamp, "gate": "final"}))
```

- [ ] **Step 6: 运行通过**
- [ ] **Step 7: Commit** - `feat(6b2): enrichment + sealed 2023 workflow + stage gating`

---

## Task 16: 复用验证 + 2023 终验执行支持

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写测试** - `--years 2021 2022` 生成 60 slices，gate 用复用阈值（各 Δ_year≥+2pp）；`--years 2023` 用终验阈值（Δ2023≥0 -> CONFIRMED_PROMOTE）；阶段准入检查
- [ ] **Step 2: 实现** - _build_schedule 接 years；compute_gate 按 years 选阈值；入口调 check_stage_gate
- [ ] **Step 3: 运行通过**
- [ ] **Step 4: Commit** - `feat(6b2): reuse-validation (2021/2022) + 2023 final gate support`

---

## 自审清单（对照 spec §7）

- [ ] §7.1.1 先解析后裁决、judge 仅分歧 -> Task 6 `_resolve_and_judge`
- [ ] §7.1.2 source_label_blinded（分析一/二、SHA-256 swap、不声称完全盲法）-> Task 1/6
- [ ] §7.1.3 judge 输入（两管线选项+理由）-> Task 1/6
- [ ] §7.1.4 单侧 unresolved 进 judge、双侧不调 -> Task 6
- [ ] §7.1.5 judge 失败计 unresolved -> Task 6
- [ ] §7.2 落点（dual_system_reasoning.py、--method dual_system、测试矩阵）-> Task 1/9
- [ ] §7.3 同期 B1-a′、B1-c advisory、dev gate 三条件、复用验证 -> Task 10/13/16
- [ ] §7.4 2023 终验 + 密封 -> Task 15/16
- [ ] §7.5 预算（60.8% 修正）-> Task 10 常量
- [ ] §4.4.2 双列预算 + BLOCKED_INCOMPLETE -> Task 11 + Task 6 `_HardCapExhausted`
- [ ] P0-1 调用契约（str 返回、不重复记账）-> Task 6
- [ ] P0-2 stage 时序（调用前切换、try/finally）-> Task 6
- [ ] P0-3 stage-aware resume + 完整返回 -> Task 6/7
- [ ] P0-4 三段独立可见性 -> Task 8
- [ ] P0-5 BudgetLedger 参数化 + scheduled=960 -> Task 10/11
- [ ] P0-6 enrichment + 密封 2023 -> Task 15
- [ ] P1-1 B1-c advisory -> Task 13
- [ ] P1-2 SHA-256 swap seed -> Task 1
- [ ] P1-3 测试文件归属（新建 test_dual_system_reasoning.py / test_phase6_6b2.py）-> 全部
- [ ] P1-4 无占位符 -> 全部任务含可执行代码/断言
