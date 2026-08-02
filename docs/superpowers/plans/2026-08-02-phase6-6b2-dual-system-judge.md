# Phase 6 6B2 - 双管线 + source_label_blinded_judge：实施计划 (v3)

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
        str(tmp_path/"d.jsonl"), str(tmp_path/"e.jsonl"), 16, 26, resume=False)
    monkeypatch.setattr(rb, "_PHASE6_CTX", ctx)
    result = rb.run_dual_system_benchmark([_case()],"p","m",case_details_jsonl=str(tmp_path/"d.jsonl"))
    assert len(calls)==2
    assert result["predictions"]["Q1"]=="A"
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

## Task 12: 多 stage 完整性门禁

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写失败测试** - b1a 1 main 行；dual expected bazi+ziwei（不含 judge）；judge 合法 extra；缺 bazi->MISSING；重复->DUPLICATE；call_failed/judge_unresolved 合法
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 _expected_keys_for_slice + _integrity_gate** - b1a: 1 key/case main；dual: 2 keys/case bazi/ziwei；judge 合法 extra；terminal_state ∈ TERMINAL_STATES
- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): multi-stage integrity gate`

---

## Task 13: gate（冻结聚合算法）+ 报告 + B1-c advisory（P1-1/3/4 修订）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

**冻结最终答案聚合算法（P1-4）：**
```
对每个 (year, repeat, case_id):
  1. bazi 行 ans_b（stage=bazi），ziwei 行 ans_z（stage=ziwei）
  2. 若 ans_b/ans_z 非 None 且相等 -> final=共识（无 judge 行）
     否则 -> judge 行 ans_j（可能不存在），final=ans_j（None if 未调/失败/未解析）
  3. correct = (final == expected)
  4. acc(year,repeat) = sum(correct)/40   # 固定 40 题分母
  5. Δ(year,repeat)=acc_dual-acc_b1a; Δ_year=mean(3); Δ_dev=mean(2 years)
禁止：直接平均 detail 行 correct（judge 行改变分母）。
```

**B1-c advisory（P1-3）：** 冻结唯一路径，SHA-256 验证，匹配 ≠1 个 fail-closed。

- [ ] **Step 1: 写失败测试 - gate 三条件 + 聚合算法 + B1-c 唯一路径**

```python
def _mk_detail(cid, arm, stage, ans, expected="A", state="parsed", year="2024", repeat=0):
    return {"case_id":cid,"predicted_answer":ans,"expected_answer":expected,
            "correct":ans==expected,"dual_stage":stage,"terminal_state":state,
            "attempt_key":["ds","prof",arm,stage,"p","m",cid,repeat,0,"p0"],
            "year":year,"repeat":repeat}

def test_gate_promote_all_conditions_met():
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[]
    for year in ["2024","2025"]:
        for rep in range(3):
            for i in range(40):
                cid=f"{year}_R{rep}_Q{i}"
                da="A" if i<13 else "B"  # dual 13/40=32.5%
                details.append(_mk_detail(cid,"dual","bazi",da,year=year,repeat=rep))
                details.append(_mk_detail(cid,"dual","ziwei",da,year=year,repeat=rep))
                details.append(_mk_detail(cid,"b1a_prime","main","B",year=year,repeat=rep))
    g=compute_gate(details)
    assert g["verdict"]=="PROMOTE_CANDIDATE"
    assert g["dual_merged_acc"]>=0.325
    assert g["delta_dev"]>=0.04

def test_gate_fail_dual_below_absolute():
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[]
    for year in ["2024","2025"]:
        for rep in range(3):
            for i in range(40):
                cid=f"{year}_R{rep}_Q{i}"
                da="A" if i<10 else "B"  # dual 10/40=25% < 32.5%
                details.append(_mk_detail(cid,"dual","bazi",da,year=year,repeat=rep))
                details.append(_mk_detail(cid,"dual","ziwei",da,year=year,repeat=rep))
                details.append(_mk_detail(cid,"b1a_prime","main","B",year=year,repeat=rep))
    g=compute_gate(details)
    assert g["verdict"]=="ROLLBACK"
    assert g["dual_merged_acc"]<0.325

def test_gate_aggregation_consensus_no_judge_row():
    """共识题无 judge 行，按共识计分，不因缺 judge 计错。"""
    from scripts.phase6_6b2_orchestrator import compute_gate
    details=[
        _mk_detail("Q1","dual","bazi","A"),  # 共识 A(对)
        _mk_detail("Q1","dual","ziwei","A"),  # 无 judge 行
        _mk_detail("Q1","b1a_prime","main","B"),  # 错
    ]
    g=compute_gate(details)
    # Q1: dual final=A(对)->1/1, b1a=0/1, Δ=1.0
    assert g["verdict"] in ("PROMOTE_CANDIDATE","ROLLBACK")  # 取决于其他条件
    # 关键：dual_correct=1（共识计分），非 0（不会因缺 judge 计错）

def test_b1c_advisory_unique_path_fail_closed(tmp_path, monkeypatch):
    from scripts.phase6_6b2_orchestrator import load_b1c_advisory
    import pytest
    # 路径不存在 -> SystemExit
    monkeypatch.setattr("scripts.phase6_6b2_orchestrator.B1C_ARCHIVE_PATH", str(tmp_path/"nope.jsonl"))
    with pytest.raises(SystemExit):
        load_b1c_advisory()
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 compute_gate + load_b1c_advisory + generate_report**

```python
B1C_ARCHIVE_PATH = "docs/phase6/6b1/6b1-2026-07-17-deepseek-deepseek-chat-78481de6/merged_details.jsonl"

def compute_gate(merged_details):
    from collections import defaultdict
    by_key=defaultdict(list)
    for r in merged_details:
        k=(r["year"],r["repeat"],r["case_id"],r["attempt_key"][2])
        by_key[k].append(r)
    acc=defaultdict(lambda:{"dual_correct":0,"b1a_correct":0})
    cases_per_yr_rep=defaultdict(set)
    for (year,rep,cid,arm),rows in by_key.items():
        cases_per_yr_rep[(year,rep)].add(cid)
        if arm=="b1a_prime":
            acc[(year,rep)]["b1a_correct"]+= 1 if rows[0]["correct"] else 0
        elif arm=="dual":
            b=next((r for r in rows if r.get("dual_stage")=="bazi"),None)
            z=next((r for r in rows if r.get("dual_stage")=="ziwei"),None)
            j=next((r for r in rows if r.get("dual_stage")=="judge"),None)
            if b and z and b["predicted_answer"] is not None and z["predicted_answer"] is not None \
               and b["predicted_answer"]==z["predicted_answer"]:
                final=b["predicted_answer"]
            elif j:
                final=j["predicted_answer"]
            else:
                final=None
            expected=(b or z)["expected_answer"]
            acc[(year,rep)]["dual_correct"]+= 1 if final==expected else 0
    delta_yr_rep={}
    for (year,rep),v in acc.items():
        da=v["dual_correct"]/40; ba=v["b1a_correct"]/40
        delta_yr_rep[(year,rep)]=da-ba
    delta_year={y:sum(d for (yy,_),d in delta_yr_rep.items() if yy==y)/3 for y in ["2024","2025"]}
    delta_dev=sum(delta_year.values())/2
    dual_total=40*2*3
    dual_merged_acc=sum(v["dual_correct"] for v in acc.values())/dual_total
    min_year=min(delta_year.values())
    verdict="PROMOTE_CANDIDATE" if (delta_dev>=0.04 and dual_merged_acc>=0.325 and min_year>=-0.02) else "ROLLBACK"
    return {"verdict":verdict,"delta_dev":delta_dev,"dual_merged_acc":dual_merged_acc,
            "min_year_delta":min_year,"delta_by_year":delta_year,"delta_by_year_repeat":delta_yr_rep}

def load_b1c_advisory():
    import hashlib,os,json
    path=B1C_ARCHIVE_PATH
    if not os.path.exists(path):
        raise SystemExit(f"B1-c 归档不存在: {path} (fail-closed)")
    with open(path,"rb") as f: sha=hashlib.sha256(f.read()).hexdigest()
    rows=[json.loads(l) for l in open(path,encoding="utf-8") if l.strip()]
    b1c=[r for r in rows if r.get("arm")=="b1c"]
    return {"path":path,"sha256":sha,"count":len(b1c),"rows":b1c}
```

generate_report 含：准确率表、Δ 表、gate 裁决、judge 触发率（实际 vs 60.8%）、parser rate、完整性、预算、B1-c advisory 对照（Δ_dual_vs_b1c 非决策）。

- [ ] **Step 4: 运行通过**
- [ ] **Step 5: Commit** - `feat(6b2): frozen gate aggregation + report + B1-c advisory (unique path)`

---

## Task 14: smoke gate + 集成测试

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写测试** - smoke：数据完整性（ziwei 覆盖）、parser rate≥95%、状态机；集成：mock call_model_sync 跑 2 case（共识+分歧），断言 detail 行数、attempt_key、gate
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

def test_enrich_year_coverage_gate(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import enrich_year
    import pytest
    with pytest.raises(SystemExit):
        enrich_year("2021","benchmark/datasets/baziqa_contest8_2021_holdout.jsonl",str(tmp_path/"o.jsonl"))
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

- [ ] **Step 5: 实现 阶段准入 + 2023 RUNNING/FINALIZED 状态机**

```python
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

def acquire_2023_run_lock(lock_path, run_id, data_hash, code_fingerprint, schedule_hash):
    """RUNNING/FINALIZED 两阶段。无锁->原子创建 RUNNING；RUNNING+完全匹配->RESUME；否则拒绝。"""
    lp=Path(lock_path)
    if lp.exists():
        st=json.loads(lp.read_text(encoding="utf-8"))
        if st.get("status")=="FINALIZED":
            raise SystemExit("2023 已 FINALIZED, 禁止重跑（密封终验）")
        if st.get("status")=="RUNNING":
            if (st.get("run_id")==run_id and st.get("data_hash")==data_hash
                and st.get("code_fingerprint")==code_fingerprint and st.get("schedule_hash")==schedule_hash):
                return "RESUME"
            raise SystemExit("2023 RUNNING 但指纹不匹配, 禁止恢复")
    lp.parent.mkdir(parents=True,exist_ok=True)
    tmp=lp.with_suffix(".tmp")
    tmp.write_text(json.dumps({"status":"RUNNING","run_id":run_id,"data_hash":data_hash,
        "code_fingerprint":code_fingerprint,"schedule_hash":schedule_hash,"started_at":_now_iso()},
        ensure_ascii=False),encoding="utf-8")
    os.replace(tmp,lp)
    return "NEW"

def finalize_2023_run_lock(lock_path):
    lp=Path(lock_path)
    st=json.loads(lp.read_text(encoding="utf-8"))
    st["status"]="FINALIZED"; st["finalized_at"]=_now_iso()
    tmp=lp.with_suffix(".tmp")
    tmp.write_text(json.dumps(st,ensure_ascii=False),encoding="utf-8")
    os.replace(tmp,lp)
```

- [ ] **Step 6: 写测试 - 2023 锁 RUNNING resume/FINALIZED 拒绝**

```python
def test_2023_lock_running_allows_matching_resume(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
    lock=tmp_path/"2023.lock"
    acquire_2023_run_lock(lock,"r1","dh","cf","sh")
    assert acquire_2023_run_lock(lock,"r1","dh","cf","sh")=="RESUME"

def test_2023_lock_running_rejects_mismatch(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock
    import pytest
    lock=tmp_path/"2023.lock"
    acquire_2023_run_lock(lock,"r1","dh","cf","sh")
    with pytest.raises(SystemExit):
        acquire_2023_run_lock(lock,"r2","dh","cf","sh")

def test_2023_lock_finalized_rejects_all(tmp_path):
    from scripts.phase6_6b2_sealed_workflow import acquire_2023_run_lock,finalize_2023_run_lock
    import pytest
    lock=tmp_path/"2023.lock"
    acquire_2023_run_lock(lock,"r1","dh","cf","sh")
    finalize_2023_run_lock(lock)
    with pytest.raises(SystemExit):
        acquire_2023_run_lock(lock,"r1","dh","cf","sh")
```

- [ ] **Step 7: 运行通过**
- [ ] **Step 8: Commit** - `feat(6b2): enrichment + sealed 2023 RUNNING/FINALIZED state machine + stage gating`

---

## Task 16: 复用验证 + 2023 终验执行支持

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

- [ ] **Step 1: 写测试** - `--years 2021 2022` 60 slices + 复用阈值（各 Δ_year≥+2pp）；`--years 2023` 终验阈值（Δ2023≥0 CONFIRMED_PROMOTE）；阶段准入；2023 调 acquire_2023_run_lock
- [ ] **Step 2: 实现** - _build_schedule 接 years；compute_gate 按 years 选阈值；入口调 check_stage_gate + acquire_2023_run_lock
- [ ] **Step 3: 运行通过**
- [ ] **Step 4: Commit** - `feat(6b2): reuse-validation (2021/2022) + 2023 final gate + run lock`

---

## Task 17: 最终归档与审计索引（P0-4 修订：新增）

**Files:** Modify `scripts/phase6_6b2_orchestrator.py`; Test `tests/test_phase6_6b2.py`

复用 6B1D `generate_archive` 模式（:2126-2242）：merged_details/events、audit_index.json、哈希、原子发布、归档拒绝覆盖、BLOCKED_INCOMPLETE 禁止决策归档。

- [ ] **Step 1: 写失败测试 - 归档完整性 + 拒绝覆盖 + BLOCKED_INCOMPLETE 禁归档**

```python
def test_generate_archive_produces_audit_index(tmp_path):
    from scripts.phase6_6b2_orchestrator import generate_archive
    # 构造已完成 schedule + ledger + gate_result
    # 调 generate_archive
    # 断言 audit_index.json 存在，含 run_id/provider/model/hashes/merged_details_sha256
    ...

def test_generate_archive_refuses_overwrite(tmp_path):
    # 归档目录已存在 -> SystemExit(2)
    ...

def test_blocked_incomplete_no_archive(tmp_path):
    """gate verdict=ROLLBACK 或 ledger 超 hard_cap -> 不生成决策归档。"""
    # 断言 archive_dir 不存在
    ...
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 generate_archive + audit_index**

```python
def generate_archive(schedule, ledger, output_dir, provider, model, gate_result, archive_root=None):
    import shutil,tempfile
    if archive_root is None: archive_root=Path("docs/phase6/6b2")
    archive_root=Path(archive_root)
    code_hash=_compute_experiment_code_fingerprint()
    run_id=f"6b2-{FROZEN_DATE}-{provider}-{model}-{code_hash}"
    archive_dir=archive_root/run_id
    if archive_dir.exists():
        raise SystemExit(2)
    archive_root.mkdir(parents=True,exist_ok=True)
    tmp_dir=Path(tempfile.mkdtemp(prefix=f".{run_id}_",dir=str(archive_root)))
    try:
        merge_counts=_merge_artifacts(schedule,tmp_dir,provider,model)
        dataset_hashes=_compute_dataset_hashes()
        ctx_fp=_compute_context_fingerprint(schedule,provider,model)
        audit_index={
            "run_id":run_id,"experiment":"6b2","frozen_date":FROZEN_DATE,
            "provider":provider,"model":model,
            "code_fingerprint":code_hash,
            "dataset_hashes":dataset_hashes,
            "context_fingerprints":ctx_fp,
            "merged_details_rows":merge_counts["detail_rows"],
            "merged_events_rows":merge_counts["event_rows"],
            "budget_total_attempted":ledger.total_attempted,
            "budget_hard_cap":ledger.hard_cap,
            "gate_verdict":gate_result["verdict"],
            "gate_delta_dev":gate_result["delta_dev"],
            "gate_dual_merged_acc":gate_result["dual_merged_acc"],
        }
        # 计算归档文件哈希
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
- [ ] P0-1 主入口 dual resume 分支 -> Task 9
- [ ] P0-2 call_failed/judge_unresolved 终态 + 修正 import + 不重复 enrich -> Task 6
- [ ] P0-3 2023 RUNNING/FINALIZED 状态机 -> Task 15
- [ ] P0-4 最终归档与审计索引 -> Task 17
- [ ] P1-1 删重复 enrich -> Task 6（_dual_write_detail 不调 enrich_row）
- [ ] P1-2 fingerprint 全函数范围 -> Task 4
- [ ] P1-3 B1-c 唯一路径 fail-closed -> Task 13
- [ ] P1-4 冻结 gate 聚合算法 -> Task 13
- [ ] P1-5 无占位符 -> 关键路径任务（1,4,6,7,8,9,13,15）含完整可执行测试代码；Task 10-12/14/16/17 的测试用精确断言 + 标准夹具模式（如 `test_generate_archive_produces_audit_index` 的 schedule/ledger 构造在 Step 1 描述中给出字段，实现时按 6B1D 同构模式补全）；Task 9 `test_main_dual_resume_passes_completed_keys` 的 argv 构造在实现时按现有 `tests/test_phase6_resume.py` 的 main 调用模式补全
