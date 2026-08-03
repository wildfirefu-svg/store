# Phase 6 6B2 - 双管线 + source_label_blinded_judge：实施计划 (v6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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
    """dual_system + resume -> completed_keys 非空传入。"""
    import benchmark.runners.run_benchmark as rb, json
    detail = tmp_path/"d.jsonl"
    row={"case_id":"Q1","predicted_answer":"A","raw_answer":"x","expected_answer":"A",
         "correct":True,"call_success":True,"dual_stage":"bazi","parser_valid":True,
         "sample_idx":0,"permutation_id":"p0","terminal_state":"parsed",
         "attempt_key":["ds","baziqa_xjz_dual","dual","bazi","p","m","Q1",0,0,"p0"]}
    detail.write_text(json.dumps(row,ensure_ascii=False)+"\n",encoding="utf-8")
    captured={}
    monkeypatch.setattr(rb, "run_dual_system_benchmark",
        lambda cases,*a,**k: captured.update(ck=kw_get(k,"completed_keys")) or {"cases":cases,"predictions":{},"evidence_results":[],"safety_results":[],"case_details":[],"failed_cases":[]})
    # 构造 argv 调 main: --profile baziqa_xjz_dual --method dual_system --resume --model-runner ...
    # 断言 captured["ck"] 非空
    ...
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
    s=_build_schedule(str(tmp_path), years=["2024","2025"])
    assert s["total_slices"]==60
    dual=[x for x in s["slices"] if x["arm"]=="dual"]
    assert all(x["scheduled_calls"]==24 for x in dual)
    assert s["total_scheduled_calls"]==960
    assert s["global_hard_cap"]==1060
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现常量 + _build_schedule** - `B1A_SLICE_SCHEDULED=8; DUAL_SLICE_SCHEDULED=24; GLOBAL_HARD_CAP=1060; JUDGE_DISAGREEMENT_RATE=0.608`；2 arms × 5 groups × 2 years × 3 repeats=60 交错排序
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): orchestrator constants + 60-slice schedule`

---

## Task 11: BudgetLedger6B2 + slice 执行

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写失败测试** - `BudgetLedger6B2(global=1060, slice_min=8, slice_max=26)` 接受 cap=26；`_build_runner_cmd` dual 用 dual_system+dual stage+hard_cap=26
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 BudgetLedger6B2（参数化）+ _build_runner_cmd + _run_slice + _process_slice** - 复制 6B1D 结构，构造接参数；复用 OutputDirLock/atomic_write_json/_count_call_attempts
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): parameterized BudgetLedger + slice execution + cmd builder`

---

## Task 12: 多 stage 完整性门禁（P0-2 修订：验证 judge 基数）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**P0-2：** judge 不能仅当"合法 extra"。必须按 bazi/ziwei 结果验证 judge 基数为 0 或 1：共识题 judge 行必须 0；分歧/单侧 unresolved 必须 1；缺失或多余均失败。

- [ ] **Step 1: 写失败测试 - judge 基数验证**

```python
def _mk_detail_row(cid, arm, stage, ans, dataset="baziqa_contest8_2024_holdout_enriched", repeat=0, state="parsed"):
    return {"case_id":cid,"predicted_answer":ans,"expected_answer":"A","correct":ans=="A",
            "dual_stage":stage,"terminal_state":state,
            "attempt_key":[dataset,"prof",arm,stage,"p","m",cid,repeat,0,"p0"]}

def test_integrity_judge_count_consensus_zero():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","b1a_prime","main","A"),
          _mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, ["Q1"])=="PASS"

def test_integrity_judge_extra_on_consensus_fails():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A"),
          _mk_detail_row("Q1","dual","judge","A")]
    assert _integrity_gate(rows, ["Q1"]).startswith("JUDGE_ON_CONSENSUS")

def test_integrity_disagreement_requires_judge():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","B")]
    assert _integrity_gate(rows, ["Q1"]).startswith("MISSING_JUDGE")

def test_integrity_unilateral_unresolved_requires_judge():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","dual","bazi",None,state="call_failed"),
          _mk_detail_row("Q1","dual","ziwei","B")]
    assert _integrity_gate(rows, ["Q1"]).startswith("MISSING_JUDGE")

def test_integrity_both_unresolved_zero_judge():
    """双侧 unresolved -> 0 judge（runner 不调 judge）。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","dual","bazi",None,state="invalid"),
          _mk_detail_row("Q1","dual","ziwei",None,state="invalid")]
    assert _integrity_gate(rows, ["Q1"])=="PASS"

def test_integrity_both_unresolved_with_judge_fails():
    """双侧 unresolved 却有 judge -> 失败。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","dual","bazi",None,state="invalid"),
          _mk_detail_row("Q1","dual","ziwei",None,state="invalid"),
          _mk_detail_row("Q1","dual","judge","A")]
    assert _integrity_gate(rows, ["Q1"]).startswith("JUDGE_ON_BOTH_UNRESOLVED")

def test_integrity_b1a_missing_main_fails():
    """b1a_prime 缺 main 行 -> 失败。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, ["Q1"]).startswith("B1A_MAIN_COUNT")

def test_integrity_b1a_duplicate_main_fails():
    """b1a_prime 2 个 main 行 -> 失败。"""
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","b1a_prime","main","A"),_mk_detail_row("Q1","b1a_prime","main","A"),
          _mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, ["Q1"]).startswith("B1A_MAIN_COUNT")

def test_integrity_missing_bazi_fails():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    assert _integrity_gate([_mk_detail_row("Q1","dual","ziwei","A")], ["Q1"]).startswith("MISSING")

def test_integrity_duplicate_key_fails():
    from scripts.phase6_6b2_orchestrator import _integrity_gate
    rows=[_mk_detail_row("Q1","dual","bazi","A"),_mk_detail_row("Q1","dual","bazi","A"),
          _mk_detail_row("Q1","dual","ziwei","A")]
    assert _integrity_gate(rows, ["Q1"]).startswith("DUPLICATE")
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 _integrity_gate（P0-1 修订：按 (year,repeat,case,arm) 分组）**

```python
def _integrity_gate(merged_details, case_ids):
    """完整性门禁。按 (year,repeat,case_id,arm) 分组（不跨 repeat/arm 合并）。

    冻结规则：
    - b1a_prime: 恰好 1 个 main 行/case
    - dual: 恰好 1 bazi + 1 ziwei/case
    - judge 基数: 共识(b==z 且均非 None) -> 0; 双侧均 unresolved -> 0; 其余 -> 1
    """
    from collections import defaultdict
    by_cell = defaultdict(lambda: defaultdict(list))  # (yr,rep,cid,arm) -> stage -> rows
    seen = set()
    for r in merged_details:
        year, rep, cid, arm, stage = parse_detail_identity(r)
        ak = tuple(r["attempt_key"])
        if ak in seen: return f"DUPLICATE: {ak}"
        seen.add(ak)
        by_cell[(year,rep,cid,arm)][stage].append(r)
    for (year,rep,cid,arm), stages in by_cell.items():
        if arm == "b1a_prime":
            if len(stages.get("main",[])) != 1:
                return f"B1A_MAIN_COUNT: {year}/{rep}/{cid} = {len(stages.get('main',[]))}"
        elif arm == "dual":
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
import re

B1C_ARCHIVE_PATH = "docs/phase6/6b1/6b1-2026-07-17-deepseek-deepseek-chat-78481de6/merged_details.jsonl"
B1C_EXPECTED_SHA256 = "10e6b82f92fabd02b7e621b714d330a812f16e6b7aac7ad98adf4a0dd494eafa"

def _year_from_dataset_id(dataset_id):
    m = re.search(r"baziqa_contest8_(\d{4})_holdout", dataset_id or "")
    return m.group(1) if m else None

def parse_detail_identity(row):
    """从真实 detail row 的 attempt_key 解析 (year, repeat, case_id, arm, stage)。"""
    ak = row["attempt_key"]
    return (_year_from_dataset_id(ak[0]), int(ak[7]), ak[6], ak[2], ak[3])

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
            b = next((r for r in rows if r.get("dual_stage")=="bazi"), None)
            z = next((r for r in rows if r.get("dual_stage")=="ziwei"), None)
            j = next((r for r in rows if r.get("dual_stage")=="judge"), None)
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

generate_report 含：准确率表、Δ 表、gate 裁决、judge 触发率（实际 vs 60.8%）、parser rate、完整性、预算、B1-c advisory 对照（Δ_dual_vs_b1c 非决策）。

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): gate (3-stage parameterized + real schema identity) + B1-c advisory (frozen SHA)`

---

## Task 14: smoke gate + 集成测试

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写测试** - smoke：数据完整性（ziwei 覆盖）、parser rate≥95%（分母=所有 stage 的 detail 行数，含 bazi/ziwei/judge；分子=terminal_state∈{parsed,call_failed} 的行数，排除 invalid/judge_unresolved/unresolved）、状态机；集成：mock call_model_sync 跑 2 case（共识+分歧），断言 detail 行数、attempt_key、gate
- [ ] **Step 2: 实现 smoke gate** - 复用 6B1D determine_smoke_state/verify_smoke_completed；dual smoke 验证 bazi+ziwei+judge 链路
- [ ] **Step 3: 运行通过**
- [ ] **Step 4: Commit** - `feat(6b2): smoke gate + integration test`

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

def check_stage_gate(stage, gate_root="docs/phase6/6b2"):
    r=Path(gate_root)
    if stage=="reuse":
        dev=_load_gate(r/"dev_gate.json")
        if dev.get("verdict")!="PROMOTE_CANDIDATE":
            raise SystemExit(f"dev gate 未通过 ({dev.get('verdict')}), 禁止跑复用验证")
    elif stage=="final_2023":
        dev=_load_gate(r/"dev_gate.json")
        if dev.get("verdict")!="PROMOTE_CANDIDATE":
            raise SystemExit("dev gate 未通过, 禁止解封 2023")
        reuse=_load_gate(r/"reuse_gate.json")
        if reuse.get("verdict")!="PASS":
            raise SystemExit(f"复用验证未通过 ({reuse.get('verdict')}), 禁止解封 2023")

def acquire_2023_run_lock(lock_path, run_id, code_fingerprint, schedule_hash):
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
            if (st.get("run_id")==run_id and st.get("raw_sha256")==BLESSED_2023_RAW_SHA256
                and st.get("code_fingerprint")==code_fingerprint and st.get("schedule_hash")==schedule_hash):
                return "RESUME"
            raise SystemExit("2023 RUNNING 但指纹不匹配, 禁止恢复")
    # 原子排他创建（O_CREAT|O_EXCL），失败说明被其他进程抢
    lp.parent.mkdir(parents=True,exist_ok=True)
    import os as _os
    payload=json.dumps({"status":"RUNNING","run_id":run_id,
        "raw_sha256":BLESSED_2023_RAW_SHA256,
        "code_fingerprint":code_fingerprint,"schedule_hash":schedule_hash,
        "started_at":_now_iso()}, ensure_ascii=False)
    try:
        fd=_os.open(str(lp), _os.O_CREAT|_os.O_EXCL|_os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("2023 锁已被其他进程持有 (fail-closed)")
    with _os.fdopen(fd,"w",encoding="utf-8") as f:
        f.write(payload)
    return "NEW"

def verify_2023_raw_data(raw_path, pre_blessed_sha):
    """RUNNING 锁成功后读取并验证原始数据 SHA。不匹配 -> BLOCKED。"""
    actual=_sha256_file(raw_path)
    if actual != pre_blessed_sha:
        raise SystemExit(f"2023 原始数据 SHA 不匹配: {actual} != {pre_blessed_sha} (BLOCKED)")

def record_enriched_sha_to_lock(lock_path, enriched_path):
    """enrichment 完成后，将派生文件 SHA 写回 RUNNING 锁。

    P1: 必须验证锁处于 RUNNING（不在 RUNNING 状态拒绝写入）。
    """
    lp=Path(lock_path)
    st=json.loads(lp.read_text(encoding="utf-8"))
    if st.get("status") != "RUNNING":
        raise SystemExit(f"record_enriched 拒绝: 锁非 RUNNING (当前 {st.get('status')})")
    st["enriched_sha256"]=_sha256_file(enriched_path)
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
    # P0-5: 验证 audit_index 内容与 RUNNING 锁一致
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("stage") != "final_2023":
        raise SystemExit(f"finalize 拒绝: audit stage={audit.get('stage')} != final_2023")
    if audit.get("gate_verdict") != gate_verdict:
        raise SystemExit(f"finalize 拒绝: audit gate_verdict={audit.get('gate_verdict')} != {gate_verdict}")
    if audit.get("code_fingerprint") != st.get("code_fingerprint"):
        raise SystemExit("finalize 拒绝: audit code_fingerprint 与锁不一致")
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
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock, finalize_2023_run_lock
    import pytest
    lock=tmp_path/"2023.lock"
    arch=tmp_path/"archive"; arch.mkdir()
    (arch/"audit_index.json").write_text("{}",encoding="utf-8")
    acquire_2023_run_lock(lock,"r1","cf","sh")
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
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock, finalize_2023_run_lock, _sha256_file
    lock=tmp_path/"2023.lock"
    arch=tmp_path/"archive"; arch.mkdir()
    (arch/"audit_index.json").write_text('{"x":1}',encoding="utf-8")
    acquire_2023_run_lock(lock,"r1","cf","sh")
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
```

- [ ] **Step 7: 运行通过**
- [ ] **Step 8: Commit** - `feat(6b2): enrichment + sealed 2023 RUNNING/FINALIZED state machine + stage gating`

---

## Task 16: 复用验证 + 2023 终验执行支持（P0-3 修订：密封事务链 + P0-4 阶段化预算）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**P0-3：** 2023 密封函数必须接入完整事务链（不只 acquire）：
```
check_stage_gate("final_2023")
-> acquire_2023_run_lock (用冻结 SHA)
-> verify_2023_raw_data (验证原始 SHA)
-> enrich 2023 + record_enriched_sha_to_lock
-> run schedule (global_hard_cap=530)
-> integrity gate
-> compute_gate(stage="final_2023")
-> generate_archive
-> finalize_2023_run_lock (验证 archive 后 FINALIZED)
```

**P0-4：** 阶段化预算（spec §8）：
- dev: scheduled=960, hard_cap=1060
- reuse: scheduled=960, hard_cap=1060
- final_2023: scheduled=480, hard_cap=**530**（非 1060）

- [ ] **Step 1: 写测试 - 阶段化预算 + 2023 事务链**

```python
def test_final_2023_hard_cap_is_530():
    """P0-4: 2023 终验 hard_cap=530（非 1060），scheduled=480。"""
    from scripts.phase6_6b2_orchestrator import _build_schedule, FINAL_2023_HARD_CAP, FINAL_2023_SCHEDULED
    s=_build_schedule("/tmp/x", years=["2023"])
    assert s["global_hard_cap"]==530
    assert s["total_scheduled_calls"]==480  # 30 slices * 16... 实际: 1 year*3repeat*10slice, b1a 8 + dual 24
    # b1a: 30*8=240, dual: 30*24=720? No - 2023 是单年: 3 repeat * 10 slice = 30 slices
    # b1a: 15*8=120, dual: 15*24=360, total=480
    assert FINAL_2023_HARD_CAP==530

def test_reuse_hard_cap_is_1060():
    from scripts.phase6_6b2_orchestrator import _build_schedule
    s=_build_schedule("/tmp/x", years=["2021","2022"])
    assert s["global_hard_cap"]==1060

def test_2023_transaction_chain_order(tmp_path, monkeypatch):
    """P0-3: 2023 事务链按正确顺序调用全部密封函数。"""
    from scripts.phase6_6b2_orchestrator import run_2023_final
    calls=[]
    def fake(fn):
        def wrapper(*a,**kw):
            calls.append(fn)
            return {"verdict":"CONFIRMED_PROMOTE","delta_2023":0.1,"stage":"final_2023"}
        return wrapper
    # monkeypatch 各环节，记录调用顺序
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator.check_stage_gate", fake("check_stage_gate"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.acquire_2023_run_lock", fake("acquire"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.verify_2023_raw_data", fake("verify_raw"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.enrich_year", lambda *a,**k: {"output_sha256":"x"})
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.record_enriched_sha_to_lock", fake("record_enriched"))
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator._integrity_gate", lambda *a,**k: "PASS")
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator.compute_gate", fake("compute_gate"))
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator.generate_archive", lambda *a,**k: str(tmp_path/"arch"))
    monkeypatch.setattr("scripts.phase6_6b2_sealed_workflow.finalize_2023_run_lock", fake("finalize"))
    # 需构造 audit_index.json
    (tmp_path/"arch").mkdir()
    (tmp_path/"arch"/"audit_index.json").write_text('{"run_id":"x","stage":"final_2023"}',encoding="utf-8")
    run_2023_final(provider="p", model="m", gate_root=str(tmp_path), archive_root=str(tmp_path))
    expected=["check_stage_gate","acquire","verify_raw","record_enriched","compute_gate","finalize"]
    assert calls==expected

def test_reuse_years_schedule(tmp_path):
    from scripts.phase6_6b2_orchestrator import _build_schedule
    s=_build_schedule(str(tmp_path), years=["2021","2022"])
    assert s["total_slices"]==60
    years={sl["year"] for sl in s["slices"]}
    assert years=={"2021","2022"}
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 run_2023_final 事务链 + 阶段化预算常量**

```python
# 阶段化预算（spec §8）
DEV_REUSE_HARD_CAP = 1060
FINAL_2023_HARD_CAP = 530
FINAL_2023_SCHEDULED = 480

def _stage_hard_cap(years):
    if years == ["2023"]:
        return FINAL_2023_HARD_CAP
    return DEV_REUSE_HARD_CAP

def _build_schedule(output_dir, years=None):
    # ...（同前，但 global_hard_cap 用 _stage_hard_cap(years)）
    years = years or ["2024","2025"]
    hard_cap = _stage_hard_cap(years)
    # ...


def run_2023_final(provider, model, gate_root, archive_root):
    """2023 终验完整事务链（P0-3）。"""
    from scripts.phase6_6b2_sealed_workflow import (
        check_stage_gate, acquire_2023_run_lock, verify_2023_raw_data,
        enrich_year, record_enriched_sha_to_lock, finalize_2023_run_lock)
    # 1. 阶段准入
    check_stage_gate("final_2023", gate_root=gate_root)
    # 2. 获取 RUNNING 锁（冻结 SHA）
    raw_path = "benchmark/datasets/baziqa_contest8_2023_holdout.jsonl"
    code_fp = _compute_experiment_code_fingerprint()
    sched = _build_schedule(archive_root, years=["2023"])
    sched_hash = hashlib.sha256(json.dumps(sched,sort_keys=True).encode()).hexdigest()
    run_id = f"6b2-final_2023-{FROZEN_DATE}-{provider}-{model}-{code_fp[:12]}"
    lock_path = Path(gate_root)/"2023.lock"
    acquire_2023_run_lock(lock_path, run_id, code_fp, sched_hash)
    # 3. 验证原始数据 SHA
    verify_2023_raw_data(raw_path, BLESSED_2023_RAW_SHA256)
    # 4. enrichment + 记录派生 SHA
    enriched_path = f"benchmark/datasets/baziqa_contest8_2023_holdout_enriched.jsonl"
    enrich_year("2023", raw_path, enriched_path)
    record_enriched_sha_to_lock(lock_path, enriched_path)
    # 5. 运行 schedule（hard_cap=530）
    ledger = BudgetLedger6B2(str(Path(gate_root)/"ledger_2023.json"),
                             global_hard_cap=FINAL_2023_HARD_CAP, slice_min=8, slice_max=26)
    _run_all_slices(sched, ledger, provider, model)
    # 6. 完整性门禁
    merged = _merge_all_details(sched)
    integrity = _integrity_gate(merged, _all_case_ids(sched))
    if integrity != "PASS":
        raise SystemExit(f"2023 integrity 失败: {integrity} (保持 RUNNING)")
    # 7. compute_gate
    gate = compute_gate(merged, stage="final_2023")
    # 8. 归档（generate_archive 内部自验完整性）
    archive_dir = generate_archive(sched, ledger, archive_root, provider, model, gate,
                                   integrity_result=integrity, archive_root=archive_root)
    # 9. FINALIZED（验证 archive 后切换）
    finalize_2023_run_lock(lock_path, archive_dir, gate["verdict"],
                           schedule_complete=True, integrity_passed=True)
    return {"archive_dir":archive_dir,"gate":gate}
```

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): 2023 sealed transaction chain + stage-based budget (530)`

---

## Task 17: 最终归档与审计索引（P0-4 修订：新增）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

复用 6B1D `generate_archive` 模式（:2126-2242）：merged_details/events、audit_index.json、哈希、原子发布、归档拒绝覆盖、BLOCKED_INCOMPLETE 禁止决策归档。

- [ ] **Step 1: 写失败测试 - 归档保留 ROLLBACK + run_id 含 stage + 拒绝 BLOCKED_INCOMPLETE + 拒绝覆盖**

```python
def _mk_schedule_ledger_gate(tmp_path, verdict="PROMOTE_CANDIDATE", blocked=False):
    """构造已完成 schedule + ledger + gate_result 夹具。"""
    from scripts.phase6_6b2_orchestrator import BudgetLedger6B2, GLOBAL_HARD_CAP, _build_schedule
    sched=_build_schedule(str(tmp_path/"run"), years=["2024","2025"])
    ledger=BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=GLOBAL_HARD_CAP,
                           slice_min=8, slice_max=26)
    for sl in sched["slices"]:
        ledger.record_slice_completed(sl["slice_id"], sl["scheduled_calls"])
    gate={"verdict":verdict,"delta_dev":0.05,"dual_merged_acc":0.35,"stage":"dev"}
    return sched, ledger, gate

def test_archive_preserves_rollback_verdict(tmp_path):
    from scripts.phase6_6b2_orchestrator import generate_archive
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path, verdict="ROLLBACK")
    archive_dir = generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                                   archive_root=str(tmp_path/"arch"))
    import json
    ai = json.loads((tmp_path/"arch"/Path(archive_dir).name/"audit_index.json").read_text(encoding="utf-8"))
    assert ai["gate_verdict"]=="ROLLBACK"

def test_archive_refuses_blocked_incomplete(tmp_path):
    from scripts.phase6_6b2_orchestrator import generate_archive
    import pytest
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    gate["verdict"]="BLOCKED_INCOMPLETE"
    with pytest.raises(SystemExit):
        generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                         archive_root=str(tmp_path/"arch"))

def test_archive_runs_integrity_on_merged_rows(tmp_path, monkeypatch):
    """P0-5: generate_archive 合并后自行运行 _integrity_gate，不信任外部。"""
    from scripts.phase6_6b2_orchestrator import generate_archive
    import pytest
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    # monkeypatch _integrity_gate 返回失败
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator._integrity_gate",
        lambda *a,**k: "MISSING_JUDGE: Q1")
    with pytest.raises(SystemExit):
        generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                         archive_root=str(tmp_path/"arch"))

def test_archive_refuses_incomplete_schedule(tmp_path):
    """P0-6: schedule 未全部完成 -> 拒绝归档。"""
    from scripts.phase6_6b2_orchestrator import generate_archive, BudgetLedger6B2, GLOBAL_HARD_CAP, _build_schedule
    import pytest
    sched=_build_schedule(str(tmp_path/"run"), years=["2024","2025"])
    ledger=BudgetLedger6B2(str(tmp_path/"l.json"), global_hard_cap=GLOBAL_HARD_CAP, slice_min=8, slice_max=26)
    for sl in sched["slices"][:30]:
        ledger.record_slice_completed(sl["slice_id"], sl["scheduled_calls"])
    gate={"verdict":"PROMOTE_CANDIDATE","delta_dev":0.05,"dual_merged_acc":0.35,"stage":"dev"}
    with pytest.raises(SystemExit):
        generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                         archive_root=str(tmp_path/"arch"))

def test_archive_run_id_dataset_hash_changes_with_data(tmp_path, monkeypatch):
    """P1: 数据变化 -> dataset hash 变化 -> run_id 不同。"""
    from scripts.phase6_6b2_orchestrator import generate_archive
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    # 第一次归档
    d1 = generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                          archive_root=str(tmp_path/"arch1"))
    # monkeypatch dataset hash 变化
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator._compute_dataset_hashes",
        lambda: {"2024":"DIFFERENT_HASH"})
    d2 = generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                          archive_root=str(tmp_path/"arch2"))
    assert Path(d1).name != Path(d2).name  # run_id 不同

def test_archive_refuses_overwrite(tmp_path):
    from scripts.phase6_6b2_orchestrator import generate_archive
    import pytest
    sched, ledger, gate = _mk_schedule_ledger_gate(tmp_path)
    generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                     archive_root=str(tmp_path/"arch"))
    with pytest.raises(SystemExit):
        generate_archive(sched, ledger, str(tmp_path/"run"), "p","m", gate,
                         archive_root=str(tmp_path/"arch"))
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 generate_archive + audit_index（P0-5/P0-6 修订：合并后自跑 integrity）**

```python
def generate_archive(schedule, ledger, output_dir, provider, model, gate_result, archive_root=None):
    """fail-closed 归档：合并后自行运行 _integrity_gate，不信任外部 integrity_result。"""
    import shutil,tempfile
    if archive_root is None: archive_root=Path("docs/phase6/6b2")
    archive_root=Path(archive_root)
    if gate_result.get("verdict") == "BLOCKED_INCOMPLETE":
        raise SystemExit("BLOCKED_INCOMPLETE: 不得生成决策归档 (预算破顶/完整性失败)")
    # P0-6: fail-closed 自验（不信任调用方）
    if ledger.total_attempted > ledger.hard_cap:
        raise SystemExit(f"归档拒绝: ledger 超 hard_cap ({ledger.total_attempted}>{ledger.hard_cap})")
    completed = sum(1 for sl in schedule["slices"] if ledger.slice_completed(sl["slice_id"]))
    if completed != len(schedule["slices"]):
        raise SystemExit(f"归档拒绝: schedule 未全部完成 ({completed}/{len(schedule['slices'])})")
    code_hash=_compute_experiment_code_fingerprint()
    stage = gate_result.get("stage", "dev")
    years_tag = "-".join(sorted(set(s["year"] for s in schedule["slices"])))
    dataset_hash = _compute_dataset_hashes()
    ds_prefix = hashlib.sha256(json.dumps(dataset_hash,sort_keys=True).encode()).hexdigest()[:8]
    run_id=f"6b2-{stage}-{years_tag}-{ds_prefix}-{FROZEN_DATE}-{provider}-{model}-{code_hash[:12]}"
    archive_dir=archive_root/run_id
    if archive_dir.exists():
        raise SystemExit(2)
    archive_root.mkdir(parents=True,exist_ok=True)
    tmp_dir=Path(tempfile.mkdtemp(prefix=f".{run_id}_",dir=str(archive_root)))
    try:
        merge_counts=_merge_artifacts(schedule,tmp_dir,provider,model)
        # P0-5: 合并后自行运行 _integrity_gate（不信任外部传入）
        merged_path = tmp_dir/"merged_details.jsonl"
        merged_rows = [json.loads(l) for l in open(merged_path,encoding="utf-8") if l.strip()] if merged_path.exists() else []
        all_case_ids = _all_case_ids(schedule)
        integrity = _integrity_gate(merged_rows, all_case_ids)
        if integrity != "PASS":
            raise SystemExit(f"归档拒绝: integrity gate 失败 ({integrity})")
        # P0-5: 动态验证 judge 行数（从真实 rows 计算，不用固定 expected）
        judge_count = sum(1 for r in merged_rows if r.get("attempt_key",[None]*10)[3]=="judge")
        # ledger events 对账
        event_rows = _load_events(tmp_dir/"merged_events.jsonl")
        if len(merged_rows) != merge_counts["detail_rows"]:
            raise SystemExit(f"归档拒绝: merged 行数不一致 ({len(merged_rows)}!={merge_counts['detail_rows']})")
        ctx_fp=_compute_context_fingerprint(schedule,provider,model)
        audit_index={
            "run_id":run_id,"experiment":"6b2","frozen_date":FROZEN_DATE,
            "provider":provider,"model":model,"stage":stage,"years_tag":years_tag,
            "dataset_hash_prefix":ds_prefix,
            "code_fingerprint":code_hash,
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
    """归档 merged_details SHA-256 == 运行目录 merged_details SHA-256。"""
    ...
```

- [ ] **Step 5: 运行通过**
- [ ] **Step 6: Commit** - `feat(6b2): final archive + audit index (refuse overwrite, BLOCKED guard)`

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
- [ ] §7.5 预算（60.8% 修正）-> Task 10
- [ ] §4.4.2 双列预算 + BLOCKED_INCOMPLETE -> Task 11/17
- [ ] P0-1 compute_gate 用 parse_detail_identity 从 attempt_key 解析（真实 schema）-> Task 13
- [ ] P0-2 compute_gate 参数化 stage（dev/reuse/final_2023 三档裁决）-> Task 13
- [ ] P0-3 2023 锁用预登记 SHA，打破循环依赖 -> Task 15
- [ ] P0-4 FINALIZED 与归档事务闭环（验证后原子切换，失败保持 RUNNING）-> Task 15
- [ ] P0-5 归档保留 ROLLBACK + run_id 含 stage + 显式拒绝 BLOCKED_INCOMPLETE -> Task 17
- [ ] P1-1 删重复 enrich -> Task 6（_dual_write_detail 不调 enrich_row）
- [ ] P1-2 fingerprint 全函数范围 -> Task 4
- [ ] P1-3 B1-c 读 attempt_key[2] + 冻结预期 SHA -> Task 13
- [ ] P1-4 冻结 gate 聚合算法 + 40 题唯一性验证 -> Task 13
- [ ] P1-5 ziwei 字节等价测试 -> Task 1
- [ ] P1-6 scheduled=24（非 16）-> Task 6 测试
- [ ] 放行条件：真实 schema dev/reuse/final 三阶段 gate 测试 -> Task 13
- [ ] 放行条件：ROLLBACK 归档 + BLOCKED 拒绝 -> Task 17
- [ ] 放行条件：2023 RUNNING 恢复 + 归档成功 FINALIZED + 失败保持 RUNNING -> Task 15
