# Phase 6 6D v2 Limited Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **修订历史：** v1（概要 08-09 初版）→ v2（详尽扩充）→ v3（独立核验修订：3 P0 + 4 P1 + 4 P2）→ v3.1（复审修订：1 P1 + 2 P2，已放行）→ v3.2（再审修订：2 P1 + 4 P2；on_limited 地基已提交 `00f43c6`）→ v3.3（终审修订：Task 6.7 夹具 4 处执行缺口，已放行）

**Goal:** 实现 6D-v2「限制性注入」对照实验链：`off vs on_limited`（off 复用 6D v1 归档数据，仅新跑 `b1a_time_on_limited` 臂 93 calls），通过零 API 离线门验证工程契约，为真实 paired dev（需用户批准 API）准备完备基础设施。

**Architecture:** 复用 6D v1 已完成的基础设施（`bazi_time_context.py` 的 `on_limited` 注入、6D v1 off 数据），新建独立 orchestrator `phase6_6d_v2_orchestrator.py`（复制 6D v1 架构 + 改 arm/常量/off 复用注入点），新增 `_REASONED_ARM_MAP` 项、版本常量、off 复用校验器。

**设计依据：** `docs/superpowers/specs/2026-08-08-phase6-6d-v2-limited-injection-design.md`（v3，已过独立核验）。

**设计关键决策（来自 spec）：**
- 实验臂：`b1a_time_off`（复用 6D v1）+ `b1a_time_on_limited`（新跑）
- 实际新增 API = on_limited 臂 93 calls（off 臂 93 由 6D v1 归档复用）
- gate 分母 N×3，on 臂用 `b1a_time_on_limited`
- 独立目录 `docs/phase6/6d-v2/`，不污染 6D v1

---

## 实施边界与基线

6D v1 已归档冻结（verdict=`NON_INFERIOR`）。6D-v2 独立，不 resume 6D v1 run，不共享 6D v1 schedule/gate/receipt。

### on_limited 地基（前置依赖，已入库）

**on_limited 地基（`chart_context.py` 的 `include_relations` 参数 + `run_benchmark.py` 的 on_limited 分支/CLI + 测试）已作为独立 commit 入库：`00f43c6`（`feat(6d): add on_limited limited temporal injection (6D scheme A)`，2026-08-09）。**

- 这三个文件在 6D-v2 实施中**只复用不改**（地基已提交，无脏树依赖）
- `test_bazi_time_context.py` 已含修复后的 `test_detail_provenance_on_limited_computes_sha`（真实 case 对照：on_limited 时 sha 非 None、off 时 sha 为 None）
- 一次性调试脚本 `.tmp_check_thinking.py` 已删除，不混入任何 commit

**验证**：`git log --oneline` 应显示 `00f43c6`；`git status` 中三个文件无未提交改动。

只修改以下生产文件（除 on_limited 地基外）：

- `benchmark/runners/run_benchmark.py`（仅 `_REASONED_ARM_MAP` 新增 1 项）
- `scripts/phase6_6d_v2_orchestrator.py`（新建，复制 6D v1 架构改造）
- `scripts/phase6_6d_v2_offline_gate.py`（新建，可复用 v1 离线门逻辑）

只新建以下测试文件：

- `tests/test_phase6_6d_v2_runner.py`
- `tests/test_phase6_6d_v2_off_reuse.py`
- `tests/test_phase6_6d_v2_orchestrator.py`
- `tests/test_phase6_6d_v2_offline_gate.py`（Task 7 离线门测试）

不修改：`claude_api.py`、`phase6_6d_orchestrator.py`、`phase6_6b2_orchestrator.py`、`phase6_6b2_sealed_workflow.py`、`dual_system_reasoning.py`、`bazi_calculator.py`、`benchmark/formatters/chart_context.py`、`benchmark/formatters/bazi_time_context.py`（这些已就绪，6D-v2 只复用不改）。

### TDD 约定

每个任务遵循 RED-GREEN-COMMIT：
- **RED**：先写测试，运行确认失败（`python -m pytest <file> -q`）
- **GREEN**：实现最小代码使测试通过
- **COMMIT**：每个子任务完成后提交（语义化提交信息）
- 合并前全量回归（见 Task 0 基线命令）

---

## Task 0: 基线验证与受控工作区检查

**目标：** 确认起始状态干净，记录基线数字，确认 6D v1 off 数据可用。

- [ ] 0.0 GREEN：确认 on_limited 地基已入库（P1-1）：
  ```powershell
  git log --oneline -1
  # 应显示 00f43c6 feat(6d): add on_limited limited temporal injection (6D scheme A)
  git status --short benchmark/formatters/chart_context.py benchmark/runners/run_benchmark.py tests/test_bazi_time_context.py
  # 应无输出（三文件无未提交改动）
  ```
  若地基未入库（HEAD 不含 on_limited），**先提交地基再继续**（不能带脏树进 Task 1 的 RED）。此步骤确保 Task 1 RED 在干净树上执行、Task 8 的 code_fingerprint 可对应 commit。
- [ ] 0.1 RED：运行 Phase 6 定向基线并记录数字
  ```powershell
  python -m pytest tests/test_phase6_6b2.py tests/test_phase6_profiles.py tests/test_dual_system_reasoning.py tests/test_claude_api.py tests/test_phase6_6d_orchestrator.py -q --basetemp .tmp/pytest-6d-v2-plan-baseline
  ```
  记录 passed/failed 到 `.tmp/6d-v2-baseline.txt`
- [ ] 0.2 RED：运行 Phase 6 广泛基线并记录数字
  ```powershell
  $files = (Get-ChildItem tests -Filter 'test_phase6_*.py').FullName
  python -m pytest $files tests/test_dual_system_reasoning.py tests/test_claude_api.py -q --basetemp .tmp/pytest-6d-v2-plan-phase6-baseline
  ```
  记录 passed/failed 到 `.tmp/6d-v2-baseline.txt`
- [ ] 0.3 GREEN：确认 6D v1 归档存在：
  ```powershell
  # 归档目录（含 dev_gate.json / merged_details.jsonl）——注意 run_context.json 在 runs/ 工作区，不在归档目录
  dir docs\phase6\6d\phase6-6d-v1-*
  dir docs\phase6\6d\runs\phase6-6d-v1-20260808-r1\run_context.json
  # off 臂 93 条全 parsed（从归档 merged_details.jsonl）
  python -c "import json; rows=[json.loads(l) for l in open('docs/phase6/6d/phase6-6d-v1-20260808-r1-6d-dev-2026-08-07-deepseek-deepseek-v4-flash-cc36fefa94c5/merged_details.jsonl',encoding='utf-8') if l.strip()]; off=[r for r in rows if r['attempt_key'][2]=='b1a_time_off']; print(len(off), all(r['terminal_state']=='parsed' for r in off))"
  ```
  预期输出 `93 True`
- [ ] 0.4 GREEN：确认 `on_limited` 注入已就绪（临时脚本验证）：
  > **P2 修正**：不能取数据集第一条 `[0]`——若该 case 为 NOT_ROUTED，`build_time_context` 返回 None → `format_temporal_context(None)` 崩溃。改为从 v1 归档的 `temporal_routed_cases.json` 中选一个 `ROUTED_WITH_TARGETS` 的 case。
  ```powershell
  python -c "
  import json
  from benchmark.formatters.chart_context import format_temporal_context
  from benchmark.formatters.bazi_time_context import build_time_context, classify_route_state, detect_temporal_rules, extract_target_years, TemporalRouteState
  # 从 routed manifest 选一个 ROUTED_WITH_TARGETS 的 case
  routed = json.load(open('docs/phase6/6d/temporal_routed_cases.json', encoding='utf-8'))
  target_entry = next(e for e in routed if e['route_state'] == 'ROUTED_WITH_TARGETS')
  cid = target_entry['case_id']
  # 从对应数据集加载该 case
  ds_path = f'benchmark/datasets/baziqa_contest8_{target_entry[\"year\"]}_holdout_enriched.jsonl'
  case = next(json.loads(l) for l in open(ds_path, encoding='utf-8') if l.strip() and json.loads(l)['case_id'] == cid)
  birth = case.get('birth_year') or case.get('person', {}).get('birth', {}).get('year')
  s = classify_route_state(detect_temporal_rules(case['question'], case.get('options', [])),
                           extract_target_years(case['question'], case.get('options', []), birth))
  assert s == TemporalRouteState.ROUTED_WITH_TARGETS
  ctx = build_time_context(case, s, frozen_target_years=tuple(target_entry['target_years']))
  t = format_temporal_context(ctx, include_relations=False)
  assert '地支关系' not in t and '天干关系' not in t, 'limited should omit relations'
  print('on_limited OK (case=%s)' % cid)
  "
  ```
- [ ] 0.5 GREEN：将基线写入 `docs/phase6/6d-v2/baseline-20260809.md`（含定向 + 广泛 passed/failed）
- [ ] 0.6 COMMIT：`docs(6d-v2): record baseline before implementation`

**验证：** 基线持久化；6D v1 off 数据 93 条可用；on_limited 注入就绪。

---

## Task 1: `_REASONED_ARM_MAP` 新增 `b1a_time_on_limited`

**目标：** 使 `b1a_time_on_limited` arm 通过 reasoned fail-closed 映射。当前 `_REASONED_ARM_MAP`（run_benchmark.py:83-91）缺此项，传该 arm 会在 run_benchmark.py:1816 `SystemExit(2)`。

**背景（代码路径）：** runner 的 reasoned fail-closed 映射（run_benchmark.py:1814-1837）：
```python
if profile.profile_id == "baziqa_xjz_reasoned":
    ziwei_arg = getattr(args, "ziwei_arm", None)
    if args.arm not in _REASONED_ARM_MAP:      # :1816
        print(json.dumps({"status": "BLOCKED", "reason": f"baziqa_xjz_reasoned 要求 arm ∈ ..."}))
        raise SystemExit(2)
    expected_ziwei = _REASONED_ARM_MAP[args.arm]
    # ... ziwei_arg is None 或 != expected_ziwei → SystemExit(2)
```

- [ ] 1.1 RED：写 `tests/test_phase6_6d_v2_runner.py`
  > **P1-4 + 复审修正（v3.1）**：`main()` 成功路径**返回 int，不 raise SystemExit**（只有 `__main__` 才包 `SystemExit(main())`，run_benchmark.py:2089 `return 0`）。`_BASE_ARGS` 未传 `--model-runner` → 走 :2079 离线分支 → 无 `--predictions` → `return 1`。因此 `pytest.raises(SystemExit)` 会 DID NOT RAISE。且进程内 `--case-details-jsonl NUL` 会在 :1886 触发 `_atomic_write_json(cwd\NUL.manifest.json)`——Windows 保留设备名的 tmp+replace 行为不确定。而 monkeypatch `run_model_benchmark` 无效——无 `--model-runner` 时该函数根本不会被调用（:1935）。
  ```python
  """Phase 6 6D v2 runner tests - b1a_time_on_limited arm mapping."""
  import os, sys
  PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
  if PROJECT_ROOT not in sys.path:
      sys.path.insert(0, PROJECT_ROOT)
  import pytest
  from benchmark.runners import run_benchmark
  from benchmark.runners.run_benchmark import _REASONED_ARM_MAP

  # 无 --model-runner → 走离线分支，不触发真实 API；无需 --max-cases 0
  _BASE_ARGS = ["--profile", "baziqa_xjz_reasoned", "--arm", "b1a_time_on_limited",
                "--time-context-injection", "on_limited",
                "--dataset", "benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl"]

  def test_reasoned_arm_map_includes_on_limited():
      assert _REASONED_ARM_MAP["b1a_time_on_limited"] == "none"

  def test_on_limited_ziwei_none_passes_failclosed(tmp_path, capsys):
      # 正向：通过臂检查（ziwei=none 合法）。main() 成功路径返回 int（离线分支 return 1），
      # 不 raise SystemExit。用 tmp_path 作 case-details-jsonl 避免 NUL 设备名问题。
      rc = run_benchmark.main(_BASE_ARGS + ["--ziwei-arm", "none",
          "--case-details-jsonl", str(tmp_path / "d.jsonl")])
      assert rc != 2                 # 不应是 BLOCKED
      assert "要求 arm" not in capsys.readouterr().out  # 不应因 arm 未注册被拒

  def test_on_limited_ziwei_only_rejects():
      # 反向：ziwei=only 应在 :1831 raise SystemExit(2)，在任何文件操作之前，安全
      with pytest.raises(SystemExit) as e:
          run_benchmark.main(_BASE_ARGS + ["--ziwei-arm", "only",
              "--case-details-jsonl", "NUL"])
      assert e.value.code == 2
  ```
  运行 `python -m pytest tests/test_phase6_6d_v2_runner.py -q`，确认测试失败（正向断言 `rc != 2` 与反向 `SystemExit(2)` 此时均失败/异常，因 arm 未注册）
- [ ] 1.2 GREEN：`_REASONED_ARM_MAP` 新增 `"b1a_time_on_limited": "none"`
- [ ] 1.3 GREEN：运行 `python -m pytest tests/test_phase6_6d_v2_runner.py tests/test_phase6_6d_runner.py tests/test_phase6_6b1.py -q`，全部通过
- [ ] 1.4 COMMIT：`feat(6d-v2): register b1a_time_on_limited arm in reasoned arm map`

**验证：** arm 映射通过 fail-closed；on_limited 进程内 main 走离线分支不触发真实 API；ziwei_only 正确 BLOCKED（exit 2）；回归无新增失败。

---

## Task 2: 版本常量改值（复制改造前置）

**目标：** 新建 `phase6_6d_v2_orchestrator.py`（复制 6D v1 完整文件），改两个版本常量，避免 receipt/run_context 自相矛盾、与 v1 provenance 混淆。

**背景（代码路径）：**
- `TEMPORAL_CONTEXT_VERSION = "6d-v1"`（:42），被 `check_6d_gate`（:851）强校验 `receipt["temporal_context_version"] == TEMPORAL_CONTEXT_VERSION`
- `experiment_id` 字面量 `"6d"` 有**三处**（非两处）：
  - `:1120`（audit 写入 `"experiment_id": "6d"`）
  - `:1276`（run_context 写入 `context["experiment_id"] = "6d"`）
  - `:1284`（resume 校验 `context.get("experiment_id") != "6d"` → SystemExit）
  
  **三处必须全改**。若 :1284 漏改，v2 写入 `"6d-v2"` 后 `--resume` 会被自己的校验拒绝（自相矛盾）。**建议引入 `EXPERIMENT_ID = "6d-v2"` 常量统一替换三处字面量，避免散弹式。**

**复制步骤：**
- [ ] 2.1 GREEN：复制 `phase6_6d_orchestrator.py` → `phase6_6d_v2_orchestrator.py`（作为起点，后续 Task 逐步改造）
- [ ] 2.2 GREEN：`TEMPORAL_CONTEXT_VERSION = "6d-v1"` → `"6d-v2"`（:42）
- [ ] 2.3 GREEN：新增 `EXPERIMENT_ID = "6d-v2"` 模块常量，并替换 `"6d"` 全部三处字面量（:1120 audit, :1276 run_context 写入, :1284 resume 校验）
- [ ] 2.4 RED：写 `tests/test_phase6_6d_v2_orchestrator.py`
  ```python
  import os, sys, json
  PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
  if PROJECT_ROOT not in sys.path:
      sys.path.insert(0, PROJECT_ROOT)
  import pytest
  from scripts.phase6_6d_v2_orchestrator import (
      TEMPORAL_CONTEXT_VERSION, EXPERIMENT_ID, check_6d_gate,
      _prepare_run_context, SIXD_RECEIPT_REQUIRED_FIELDS,
  )

  def test_version_constants_are_6d_v2():
      assert TEMPORAL_CONTEXT_VERSION == "6d-v2"
      assert EXPERIMENT_ID == "6d-v2"

  def test_receipt_rejects_v1_version():
      # 构造 temporal_context_version=v1 的 receipt → check_6d_gate 拒绝
      receipt = {f: None for f in SIXD_RECEIPT_REQUIRED_FIELDS}
      receipt["temporal_context_version"] = "6d-v1"
      with pytest.raises(SystemExit):
          check_6d_gate(receipt)   # 注意：check_6d_gate 只收 1 个参数（:847）
  ```
  运行确认失败（TEMPORAL_CONTEXT_VERSION 还是 6d-v1 / EXPERIMENT_ID 未定义）
- [ ] 2.4a RED：写 `test_resume_self_consistent`：构造 `run_context.json` 含 `experiment_id="6d-v2"`，`_prepare_run_context` resume 时应通过；构造 `experiment_id="6d-v1"` 应拒绝。**此测试验证 :1284 已改用 EXPERIMENT_ID（否则 v2 无法 resume 自己）**
- [ ] 2.5 GREEN：运行 `python -m pytest tests/test_phase6_6d_v2_orchestrator.py -q`，通过
- [ ] 2.6 COMMIT：`feat(6d-v2): fork orchestrator, bump version constants, add EXPERIMENT_ID`

**验证：** 独立 orchestrator 存在；常量 `6d-v2`；receipt/run_context 校验对 v1 值拒绝。

---

## Task 3: orchestrator 改造（arm / conditions / schedule / off 复用注入点）

**目标：** 将 v2 orchestrator 的 arm/conditions/schedule 改为 off+on_limited，并接入 off 复用。

### 3.1 arm 与 conditions

- [ ] 3.1 GREEN：`ARMS = ("b1a_time_off", "b1a_time_on")` → `("b1a_time_off", "b1a_time_on_limited")`（:51）
- [ ] 3.2 GREEN：`EXPERIMENT_CONDITIONS = ("off", "on")` → `("off", "on_limited")`（:52）
- [ ] 3.3 GREEN：`_build_schedule` 中 injection 映射（:239）`"off" if arm == "b1a_time_off" else "on"` → `"off" if arm == "b1a_time_off" else "on_limited"`

### 3.2 产物路径

- [ ] 3.4 GREEN：`ROUTED_MANIFEST_PATH`（:45）`docs/phase6/6d/temporal_routed_cases.json` → `docs/phase6/6d-v2/temporal_routed_cases.json`
- [ ] 3.5 GREEN：`PHASE1_RECEIPT_PATH`（:46）→ `docs/phase6/6d-v2/phase1_receipt.json`
- [ ] 3.6 GREEN：`ARCHIVE_ROOT`（:47）→ `docs/phase6/6d-v2`

> **注意**：`ROUTED_MANIFEST_PATH` 同时被 `run_dev` 的 `_validate_phase1_receipt`（:1356）读取。**必须由 Task 3.10-3.12（§3.4 新增）生成 v2 的 `temporal_routed_cases.json` + `phase1_receipt.json`，且先于 Task 4 的 off 复用校验（off 校验需读 manifest SHA）。** 这条链此前断裂（改路径后无 Task 生成），本轮已补。

### 3.3 schedule 单臂语义（off 复用）

`_build_schedule` 当前对每个 `(year,group,repeat)` 生成 off+on 双 slice。6D-v2 只跑 on_limited，off 复用。**设计决策：schedule 仍生成 off+on_limited 双 slice（保持结构对齐），但运行阶段只跑 on_limited slice，off slice 标记 `reuse_from_v1`。**

实现方式（在 v2 `_build_schedule` 增加逻辑）：
- [ ] 3.7 GREEN：`_build_schedule` 对 off 臂 slice 增加字段 `"source": "v1_reuse"`，on_limited 臂 slice 增加 `"source": "run"`
- [ ] 3.8 GREEN：`_run_all_slices` 跳过 `source == "v1_reuse"` 的 slice（不消耗 API）。**记账决策（P1-6，二选一，本计划选 A）**：
  - **方案 A（推荐）**：off slice **不计入** BudgetLedger（与设计 §4.4 一致），`_check_completeness`/`_create_archive` 只检查 `source=="run"` 的 slice。off slice 在 `_run_all_slices` 中跳过判断**先于** `ledger.slice_completed` 判断，避免 resume 时因缺 `slice_status.json` 而 SystemExit。
  - 备选方案 B：off slice 以 v1 的 93 次记账（会导致 resume 走 `_verify_completed_slice` 缺 slice_status.json → 需额外处理，不推荐）
- [ ] 3.9 GREEN：新增 `_load_v1_off_data(v1_archive_dir)`：**从 v1 归档的每个 `*_b1a_time_off_*/details.jsonl` slice 逐行读取并合并所有 `b1a_time_off` 行**（而非读 `merged_details.jsonl`——P1-5 已证 merged 的 SHA 与 audit 不匹配，slice 源头更可靠）。实现：
  ```python
  def _load_v1_off_data(v1_archive_dir):
      """从 v1 归档的 off slice 源头 details.jsonl 重建 off 数据。"""
      off = []
      for sl_dir in glob.glob(os.path.join(v1_archive_dir, "*_b1a_time_off_*")):
          p = os.path.join(sl_dir, "details.jsonl")
          if os.path.exists(p):
              off.extend(_load_events(p))
      # 只保留 off 臂行（防御性）
      return [r for r in off if (r.get("attempt_key") or [None]*10)[2] == "b1a_time_off"]
  ```
  验证：15 个 off slice → 93 行 → 19 correct（与 v1 公布的 19/93 吻合）。

### 3.4 生成 v2 temporal_routed_cases.json + phase1_receipt.json（P0-3，必须先于 Task 4）

> **receipt 双生成者与权威性（P1-2）**：`phase1_receipt.json` 有两个生成者——
> - Task 3.10 用 **v1 离线门**（`phase6_6d_offline_gate.py`）生成（中间产物）
> - Task 7.2 用 **v2 离线门**（`phase6_6d_v2_offline_gate.py`，新建）生成（权威）
>
> **决策**：Task 7.2 的 v2 receipt 为**权威**，覆盖写。但必须**保留 `_validate_phase1_receipt` 强校验的全部 6 个字段**，否则 `run_dev` 拒启：
> `status`（必须 PASS）、`n_routed`（≥20）、`temporal_routed_cases_sha256`（== manifest canonical SHA）、`dataset_sha256_by_year`（含逐字节重算）、`dataset_set_sha256`（== canonical(dataset_sha256_by_year)）。
> v2 离线门在保留这些字段基础上，**追加 v2 检查项**：`on_limited` 注入无关系、`b1a_time_on_limited` arm fail-closed、off 复用预检。Task 3.10 产物仅为 Task 4 off 复用校验的中间依据。

- [ ] 3.10 GREEN：用 v1 离线门生成**中间** manifest + receipt（Task 4 off 复用校验的 SHA 依据）：
  ```powershell
  python scripts/phase6_6d_offline_gate.py --datasets 2024,2025 --output docs/phase6/6d-v2/temporal_routed_cases.json
  ```
  该脚本会自动写 `phase1_receipt.json` 到同目录（`phase6_6d_offline_gate.py:166-167`），其 schema 满足 `_validate_phase1_receipt`（中间 receipt，Task 7 会用 v2 权威 receipt 覆盖）。
- [ ] 3.11 GREEN：断言 v2 manifest 的 canonical SHA == v1 的 `a80fbe7a…`（`temporal_routed_cases_sha256`）：
  ```powershell
  python -c "import json; s=json.load(open('docs/phase6/6d-v2/temporal_routed_cases.json',encoding='utf-8')); import hashlib; sha=hashlib.sha256(json.dumps(s,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(); print(sha); assert sha=='a80fbe7a87262dc826d9f8eb834ac958b43ad1c64f29e624aa25114c8ecfac63', 'manifest drift - off reuse precondition broken'"
  ```
  若 SHA 漂移 → off 复用前提不成立，停止。
- [ ] 3.12 GREEN：确认中间 receipt 存在且 `status=PASS`、`n_routed=31`（Task 7 会用 v2 权威 receipt 覆盖）

### 3.5 测试

- [ ] 3.13 RED：`test_schedule_arms_are_off_on_limited`：schedule 只含 `b1a_time_off`/`b1a_time_on_limited`
- [ ] 3.14 RED：`test_schedule_on_limited_93`：on_limited 臂 scheduled 总计 = 93
- [ ] 3.15 RED：`test_schedule_hard_cap_243`：on_limited 臂 hard_cap 总计 = 243
- [ ] 3.16 RED：`test_schedule_off_slices_marked_v1_reuse`：off slice 含 `source == "v1_reuse"`
- [ ] 3.17 RED：`test_off_reuse_skip_precedes_ledger`：mock `_verify_completed_slice`，验证 off slice 在 `_run_all_slices` 中被跳过（`_verify_completed_slice` 未被调用），**先于** `ledger.slice_completed` 判断
- [ ] 3.18 GREEN：运行 `python -m pytest tests/test_phase6_6d_v2_orchestrator.py -q`，通过
- [ ] 3.19 COMMIT：`feat(6d-v2): off vs on_limited schedule with off v1 reuse, generate v2 manifest`

**验证：** schedule 结构正确；on_limited 93/hard_cap 243；off slice 标记 v1_reuse；v2 manifest SHA == v1（off 复用前提成立）。

---

## Task 4: off 数据复用校验器（`_verify_off_reuse`）

**目标：** 从 6D v1 归档的 `dev_gate.json`（receipt）和 `run_context.json` 读取 SHA / frozen 参数，与 6D-v2 冻结比对；任一漂移 → fail-closed（回退 off 重跑）。

> **关键**：off detail 行内**不含** `dataset_sha256_by_year` / `temporal_routed_cases_sha256`（行内只有 `time_context_sha256`/`mode`/`temporal_route_state`）。这些字段位于 v1 的 `dev_gate.json`（归档目录）和 `run_context.json`（runs/ 工作区），必须从那里读取比对。

**背景（v1 实际字段来源，已实证）**：
- 归档目录 `<archive_id>/dev_gate.json`（即 receipt）：含 `provider`/`model`/`thinking_mode`/`model_label`/`temporal_context_version`/`experiment_conditions`/`dataset_sha256_by_year`/`temporal_routed_cases_sha256`/`dataset_set_sha256`/`group_abba_order`（不含 `experiment_id`）
- 工作区 `runs/<user_run_id>/run_context.json`：含 `provider`/`model`/`thinking_mode`/`experiment_id`/`temporal_context_version`/`dataset_sha256_by_year`/`group_abba_order` 等（**不含 `temperature`/`profile`/`method`——这三个是冻结常量，v2 直接用 `FROZEN_TEMPERATURE`/`FROZEN_PROFILE`/`FROZEN_METHOD` 比对**）

- [ ] 4.1 GREEN：实现 `_verify_off_reuse(v1_archive_dir, v1_runs_dir, v2_frozen)`：
  ```python
  def _verify_off_reuse(v1_archive_dir, v1_runs_dir, v2_frozen):
      """校验 6D v1 off 数据可复用。任一漂移 → SystemExit(2)。
      v1_archive_dir 含 dev_gate.json；v1_runs_dir 含 run_context.json。"""
      dev_gate = json.load(open(os.path.join(v1_archive_dir, "dev_gate.json"), encoding="utf-8"))
      # 1. temporal_context_version 必须为 6d-v1（证明 off 数据确属 v1）
      if dev_gate.get("temporal_context_version") != "6d-v1":
          raise SystemExit("off reuse reject: temporal_context_version != 6d-v1")
      # 2. SHA 比对（从 dev_gate.json）
      for k in ("dataset_sha256_by_year", "temporal_routed_cases_sha256", "dataset_set_sha256"):
          if dev_gate.get(k) != v2_frozen.get(k):
              raise SystemExit(f"off reuse reject: {k} drift")
      # 3. frozen 参数比对：provider/model/thinking_mode 从 dev_gate；temperature/profile/method 用冻结常量
      for k in ("provider", "model", "thinking_mode"):
          if dev_gate.get(k) != v2_frozen.get(k):
              raise SystemExit(f"off reuse reject: {k} drift")
      for k, expected in (("temperature", FROZEN_TEMPERATURE),
                          ("profile", FROZEN_PROFILE),
                          ("method", FROZEN_METHOD)):
          if v2_frozen.get(k) != expected:
              raise SystemExit(f"off reuse reject: {k} mismatch")
      # 4. experiment_id 校验（从 run_context.json，runs/ 工作区）
      run_ctx = json.load(open(os.path.join(v1_runs_dir, "run_context.json"), encoding="utf-8"))
      if run_ctx.get("experiment_id") != "6d":
          raise SystemExit(f"off reuse reject: experiment_id != '6d'")
      # 5. merged_details 字节完整性校验（P1-5）
      #    注意：实证发现 6D v1 归档的 audit_index["merged_details_sha256"]（3539a5...）
      #    与磁盘实际 merged_details.jsonl 的 sha256（c4537d...）不一致——这是 6D v1
      #    归档自身的已知问题，非 v2 引入。因此**不硬性要求两者相等**（否则 off 复用
      #    永远 fail-closed）。改为：从每个 off slice 的 details.jsonl 重建 off 数据
      #    （比 merged 更源头），并校验每行可解析 + off 覆盖完整。同时记录该 mismatch 到
      #    report 作为 6D v1 归档数据完整性警示。
      off = _load_v1_off_data(v1_archive_dir)   # 见 Task 3.9：从 off slice 的 details.jsonl 重建
      if len(off) != 93:
          raise SystemExit(f"off reuse reject: off count {len(off)} != 93")
      parsed = sum(1 for r in off if r.get("terminal_state") == "parsed")
      if parsed / len(off) < 0.85:
          raise SystemExit(f"off reuse reject: parsed rate {parsed/len(off)}")
      return off  # 返回复用的 off 数据
  ```

  **P1-5 修订说明**：实证发现 6D v1 归档的 `audit_index.json` 含 `merged_details_sha256`（3539a5...），但磁盘 `merged_details.jsonl` 实际 SHA 为 c4537d...，**二者不一致**。这是 6D v1 归档的数据完整性问题（归档后 merged_details 被改写或归档逻辑缺陷）。因此 `_verify_off_reuse` 改用 Task 3.9 的 `_load_v1_off_data`（从源头 off slice 的 `details.jsonl` 逐行重建 off 数据），既保证 off 数据可靠，又规避了 merged_details SHA 不可信的问题。此 mismatch 需在 report 中标注为 6D v1 已知警示。
- [ ] 4.2 RED：写 `tests/test_phase6_6d_v2_off_reuse.py`：
  ```python
  import os, sys, json
  PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
  if PROJECT_ROOT not in sys.path:
      sys.path.insert(0, PROJECT_ROOT)
  import pytest
  from scripts.phase6_6d_v2_orchestrator import _verify_off_reuse

  V1_ARCHIVE = "docs/phase6/6d/phase6-6d-v1-20260808-r1-6d-dev-2026-08-07-deepseek-deepseek-v4-flash-cc36fefa94c5"
  V1_RUNS = "docs/phase6/6d/runs/phase6-6d-v1-20260808-r1"

  def _v2_frozen_from_v1():
      # 从真实 v1 dev_gate.json 读取 SHA + provider/model/thinking，temperature/profile/method 用冻结常量
      dev_gate = json.load(open(os.path.join(V1_ARCHIVE, "dev_gate.json"), encoding="utf-8"))
      return {
          "dataset_sha256_by_year": dev_gate["dataset_sha256_by_year"],
          "temporal_routed_cases_sha256": dev_gate["temporal_routed_cases_sha256"],
          "dataset_set_sha256": dev_gate["dataset_set_sha256"],
          "provider": dev_gate["provider"], "model": dev_gate["model"],
          "thinking_mode": dev_gate["thinking_mode"],
          "temperature": FROZEN_TEMPERATURE, "profile": FROZEN_PROFILE, "method": FROZEN_METHOD,
      }

  def test_reuse_pass():
      off = _verify_off_reuse(V1_ARCHIVE, V1_RUNS, _v2_frozen_from_v1())
      assert len(off) == 93

  def test_reuse_sha_drift_reject():
      v2_frozen = _v2_frozen_from_v1()
      v2_frozen["dataset_sha256_by_year"] = {"2024": "x"*64}  # 漂移
      with pytest.raises(SystemExit):
          _verify_off_reuse(V1_ARCHIVE, V1_RUNS, v2_frozen)
  ```
- [ ] 4.3 RED：`test_reuse_off_missing_reject`（构造空 archive，merged 缺失 → 拒绝）
- [ ] 4.4 RED：`test_reuse_experiment_id_reject`：monkeypatch `run_context.json` 的 `experiment_id` 为 `6b2`（用 tmp_path 复制 V1_RUNS 并改写）→ 拒绝
- [ ] 4.5 GREEN：运行 `python -m pytest tests/test_phase6_6d_v2_off_reuse.py -q`，通过（注意测试文件需 `from scripts.phase6_6d_v2_orchestrator import FROZEN_TEMPERATURE, FROZEN_PROFILE, FROZEN_METHOD`）
- [ ] 4.6 COMMIT：`feat(6d-v2): off data reuse verifier with SHA fail-closed`

**验证：** 从 receipt/run_context 读取 SHA 比对；漂移/缺失/experiment_id 异常均拒绝；真实 v1 归档 PASS。

---

## Task 5: gate / 完整性门 / merge 改造

**目标：** 将 `compute_6d_gate`、`_check_completeness`、`_merge_details` 中 hardcode 的 `b1a_time_on` 改为 `b1a_time_on_limited`，并将复用的 off 数据并入 merged。

**背景（代码路径）：**
- `compute_6d_gate`（:788-789）：on 臂 `== "b1a_time_on"`
- `_check_completeness`（:767-768）：`arms.get("b1a_time_on", [])`
- `_merge_details`（:738-743）：只从本 run slice 的 detail_path 读取

**改造：**
- [ ] 5.1 GREEN：`compute_6d_gate` 中 `"b1a_time_on"` → `"b1a_time_on_limited"`（:788,789）
- [ ] 5.2 GREEN：`_check_completeness` 中 `"b1a_time_on"` → `"b1a_time_on_limited"`（:768）
- [ ] 5.3 GREEN：新增 fail-closed：若 merged 中出现 `b1a_time_on`（v1 遗留），`_check_completeness` 返回 `V1_ON_LEAK`
- [ ] 5.4 GREEN：`_merge_details(slices, v1_off_data=None)` 增加可选参数：合并时把 `v1_off_data`（Task 4 返回值）并入
- [ ] 5.5 RED：写 `tests/test_phase6_6d_v2_orchestrator.py`：
  ```python
  from scripts.phase6_6d_v2_orchestrator import compute_6d_gate, _check_completeness

  def _mk(arm, cid, rep, correct):
      return {"attempt_key": ["baziqa_contest8_2024_holdout_enriched", "baziqa_xjz_reasoned",
                              arm, "main", "deepseek", "deepseek-v4-flash", cid, rep, 0, "p0"],
              "case_id": cid, "terminal_state": "parsed", "correct": correct}

  def test_gate_uses_on_limited_and_denominator_n3():
      # N=1, REPEATS=3：c1 在 3 个 repeat 中 on_limited 净增 1 题
      # off 只在 rep==0 对（off_correct=1），on_limited 在 rep!=1 对（on_correct=2）
      # case_delta = on_correct - off_correct = 2 - 1 = +1
      # paired_delta = +1 / (N × REPEATS) = +1/3（分母不含条件数 2）
      details = []
      for rep in range(3):
          details.append(_mk("b1a_time_off", "c1", rep, rep == 0))          # off 仅 rep0 对
          details.append(_mk("b1a_time_on_limited", "c1", rep, rep != 1))    # on 2/3 对
      g = compute_6d_gate(details, 1)  # N=1
      assert abs(g["paired_delta"] - (1/3)) < 1e-9   # 分母 N×3，非 N×3×2
      assert abs(g["min_case_delta"] - (1/3)) < 1e-9 # min(+1)/3 = +1/3

  def test_completeness_rejects_v1_on():
      merged = [_mk("b1a_time_off", "c1", 0, True),
                _mk("b1a_time_on", "c1", 0, True),   # v1 遗留
                _mk("b1a_time_on_limited", "c1", 0, True)]
      # 构造 schedule 期望 c1 有 off+on_limited
      schedule = {"slices": [{"year": "2024", "repeat": 0, "arm": "b1a_time_on_limited",
                              "case_ids": ["c1"]},
                             {"year": "2024", "repeat": 0, "arm": "b1a_time_off",
                              "case_ids": ["c1"]}]}
      r = _check_completeness(merged, schedule)
      assert r != "PASS"
  ```
- [ ] 5.6 GREEN：运行 `python -m pytest tests/test_phase6_6d_v2_orchestrator.py -q`，通过（含 5.5 的分母 N×3 验证）
- [ ] 5.7 COMMIT：`feat(6d-v2): gate and completeness use on_limited arm, reject v1 on leak`

**验证：** gate 聚合 on_limited；完整性门拒绝 v1 的 `b1a_time_on` 遗留；merged 并入复用的 off 数据；分母 N×3。

---

## Task 6: run_dev 流程接线（off 复用 + 单臂执行）

**目标：** `run_dev` 完整流程：off 复用校验 → 只跑 on_limited → merged 并入 off → gate → report → archive。

**背景（代码路径）：** `run_dev`（:1349-...）当前流程：
```python
protocol = _validate_frozen_protocol(...)
_validate_run_id(run_id)
_validate_phase1_receipt(phase1_receipt_path, routed_manifest_path)
output_dir = Path(output_dir)
runs_root, context = _prepare_run_context(...)
run_manifest = build_run_manifest(...)
...
stage_dir = runs_root / "dev"; stage_dir.mkdir(...)
schedule = _build_schedule(str(stage_dir), routed_manifest_path)
if schedule["group_abba_order"] != run_manifest["group_abba_order"]: raise
ledger = BudgetLedger(..., global_hard_cap=schedule["global_hard_cap"])
_run_all_slices(schedule, ledger, provider, model)   # ← 需跳过 off reuse slice
merged = _merge_details(schedule["slices"])           # ← 需并入 off
completeness = _check_completeness(merged, schedule)
n_cases = sum(schedule["n_cases_per_year"].values())
gate_result = compute_6d_gate(merged, n_cases)
_generate_report(...)
arch = _create_archive(...)
```

- [ ] 6.1 GREEN：`run_dev` 新增参数 `v1_archive_dir`（6D v1 归档路径，含 dev_gate.json）和 `v1_runs_dir`（6D v1 runs/ 工作区路径，含 run_context.json）
- [ ] 6.2 GREEN：在 `_run_all_slices` 前调用 `v1_off = _verify_off_reuse(v1_archive_dir, v1_runs_dir, v2_frozen)`；校验失败 → `SystemExit(2)`（不消耗任何 API）
- [ ] 6.3 GREEN：`_run_all_slices` 跳过 `source == "v1_reuse"` 的 off slice
- [ ] 6.4 GREEN：`_merge_details(schedule["slices"], v1_off_data=v1_off)` 并入 off 数据
- [ ] 6.5 GREEN：`global_hard_cap` 用 on_limited 臂实际 hard_cap（243）而非完整 486（因为 off 不跑、不计入消耗）。**代码落点（P2-b）**：`run_dev` 现传 `schedule["global_hard_cap"]`（双臂 schedule = 486），需改为只算 `source=="run"` 的 slice：
  ```python
  run_cap = sum(s["hard_cap"] for s in schedule["slices"] if s["source"] == "run")  # 243
  ledger = BudgetLedger(str(stage_dir / "budget_ledger.json"), global_hard_cap=run_cap)
  ```
- [ ] 6.6 GREEN：report/audit 标注 off 来源 `6d-v1:<archive_id>`。**P2 强化**：把 `off_source`（值为 `6d-v1:<archive_id>`）和 `off_merged_details_sha256`（实际 off 数据的 SHA）补入 `SIXD_RECEIPT_REQUIRED_FIELDS`，使 `check_6d_gate` 强制校验 off provenance 存在——否则归档缺该证据也能过 gate。
- [ ] 6.7 RED：`test_run_dev_skips_off_reuse_slices`（P2-4 修法 b + 4 处夹具修正）：
  > **P2-4 修正**：不能只 mock `_run_slice` 返回 dict 而不写 detail/events——fake 不写 detail 也不记账会导致 merge 缺 on_limited main → `_check_completeness` SystemExit。**修法 (b)**：fake_run_slice **真实写 detail/events + 调 `ledger.record_slice_completed`**。
  >
  > **4 处夹具执行缺口（复审确认，必须并入）**：
  > 1. `record_slice_completed` 真实签名是 **三参** `(slice_id, actual_attempts, scheduled_calls)`（orchestrator :315），夹具只传两参 → TypeError。改为 `ledger.record_slice_completed(sid, scheduled, scheduled)`。
  > 2. `_prepare_run_context` mock **需建目录**：run_dev 非 resume 路径用 `tempfile.mkstemp(dir=str(runs_root))` 写 manifest，`tmp_path/"runs"` 不存在 → FileNotFoundError。mock 里需 `mkdir(parents=True)`。
  > 3. off mock **只造 c1 一行不够**：completeness 要求 31 题 × 3 repeats 每 cell 都有 off main。`_verify_off_reuse` 的 mock 返回必须覆盖 schedule 里的全部 case_ids，否则 `_check_completeness` SystemExit。
  > 4. archive/receipt 会**写真仓库**：`_create_archive` 默认落 `docs/phase6/6d-v2/`（`ARCHIVE_ROOT`），`_publish_receipt_atomic` 写 `runs_root/"gates"`。测试必须 monkeypatch `ARCHIVE_ROOT` 到 tmp_path（或 mock 这两个函数），否则污染真实产物目录 + `run_id exists` 二次运行失败。
  ```python
  def test_run_dev_skips_off_reuse_slices(monkeypatch, tmp_path):
      # 4. monkeypatch ARCHIVE_ROOT 到 tmp_path，避免写真仓库
      monkeypatch.setattr(orch, "ARCHIVE_ROOT", str(tmp_path / "archive"))
      calls = []
      def fake_run_slice(slice_info, ledger, provider, model, resume=False):
          calls.append(slice_info["slice_id"])
          os.makedirs(slice_info["output_dir"], exist_ok=True)
          with open(slice_info["detail_path"], "w", encoding="utf-8") as f:
              for cid in slice_info["case_ids"]:
                  f.write(json.dumps(_mk_on_limited_row(cid, slice_info)) + "\n")
          with open(slice_info["events_path"], "w", encoding="utf-8") as f:
              for _ in range(slice_info["scheduled_calls"]):
                  f.write(json.dumps({"kind": "call_attempt"}) + "\n")
          # 1. record_slice_completed 三参
          ledger.record_slice_completed(slice_info["slice_id"],
                                        slice_info["scheduled_calls"],
                                        slice_info["scheduled_calls"])
          return {"exit_code": 0, "actual_attempts": slice_info["scheduled_calls"]}
      monkeypatch.setattr(orch, "_run_slice", fake_run_slice)
      # 3. off mock 必须覆盖 schedule 全部 case_ids（31 题 × 3 repeats 每 cell 有 off main）
      monkeypatch.setattr(orch, "_verify_off_reuse",
                          lambda *a, **k: _all_off_rows_from_schedule(schedule))
      monkeypatch.setattr(orch, "_validate_frozen_protocol", lambda *a, **k: {})
      monkeypatch.setattr(orch, "_validate_phase1_receipt", lambda *a, **k: {})
      # 2. _prepare_run_context mock 需建目录
      def fake_prepare_run_context(output_dir, run_id, resume, run_manifest, code_fingerprint):
          runs_root = Path(output_dir) / "runs" / run_id
          runs_root.mkdir(parents=True, exist_ok=True)
          return runs_root, {}
      monkeypatch.setattr(orch, "_prepare_run_context", fake_prepare_run_context)
      orch.run_dev("deepseek", "deepseek-v4-flash", str(tmp_path), run_id="r1",
                   v1_archive_dir=".", v1_runs_dir=".", resume=False)
      off_ids = [c for c in calls if "b1a_time_off" in c]
      assert len(off_ids) == 0, "off (v1_reuse) slices must not be executed"
  ```
- [ ] 6.8 RED：`test_run_dev_merged_includes_off`：fake_run_slice（同 6.7，含 4 处夹具修正）+ `_verify_off_reuse` 返回覆盖全部 case_ids 的 off 行，断言 `_merge_details` 的 merged 同时含 off 行（来自复用）与 on_limited 行（来自 fake 写入）
- [ ] 6.9 RED：`test_run_dev_off_reuse_fail_blocks`：`_verify_off_reuse` 抛异常 → `run_dev` 不发起任何 slice（`_run_slice` 未被调用）。此测试无需 4 处夹具修正（off 校验在 `_run_all_slices` 之前短路）
- [ ] 6.10 GREEN：运行相关测试通过
- [ ] 6.11 COMMIT：`feat(6d-v2): wire off reuse into run_dev flow`

**验证：** run_dev 只跑 on_limited；off 复用校验失败则不消耗 API；merged 含 off+on_limited；global_hard_cap=243。

---

## Task 7: 阶段一离线门 + 全量回归 + dry-run

**目标：** 零 API 验证工程契约，确认无回归，orchestrator 可 dry-run。

> **v2 离线门是权威 receipt 生成者（P1-2）**：`phase6_6d_v2_offline_gate.py` 生成的 `phase1_receipt.json` **覆盖写** Task 3.10 的中间产物。其 schema 必须**保留 `_validate_phase1_receipt` 强校验的全部 6 字段**，否则 `run_dev`（v1 :1200-1249）拒启：
> 1. `status` = `PASS`
> 2. `n_routed` ≥ `PHASE1_N_ROUTED_MIN`（20）
> 3. `temporal_routed_cases_sha256` == manifest 的 canonical SHA
> 4. `n_routed` == manifest entries 数
> 5. `dataset_sha256_by_year` == manifest 各年 `dataset_sha256`（且对当前数据集文件逐字节重算一致）
> 6. `dataset_set_sha256` == `canonical(dataset_sha256_by_year)`
>
> 在此基础上**追加 v2 检查项**结果字段：`on_limited_no_relations`（注入无地支/天干关系）、`arm_fail_closed_ok`（`b1a_time_on_limited`+`ziwei_arm=none` 通过）、`off_reuse_precheck_ok`（off 复用预检通过）。

- [ ] 7.1 GREEN：实现 `phase6_6d_v2_offline_gate.py`：生成权威 receipt（保留 §3.4 列出的全部 6 字段 + 追加 v2 检查项字段）
- [ ] 7.2 GREEN：运行 `phase6_6d_v2_offline_gate.py --datasets 2024,2025 --output docs/phase6/6d-v2/temporal_routed_cases.json`，覆盖写 `docs/phase6/6d-v2/phase1_receipt.json`（PASS/BLOCKED）
- [ ] 7.2a GREEN：用 v1 orchestrator 的 `_validate_phase1_receipt` 校验 v2 receipt（确认 6 字段全保留，`run_dev` 不拒启）：
  ```powershell
  python -c "from scripts.phase6_6d_orchestrator import _validate_phase1_receipt; _validate_phase1_receipt('docs/phase6/6d-v2/phase1_receipt.json','docs/phase6/6d-v2/temporal_routed_cases.json'); print('v2 receipt passes v1 validation')"
  ```
- [ ] 7.3 RED：`test_phase6_6d_v2_offline_gate.py`：receipt PASS、N=31、6 字段全保留、追加字段存在、BLOCKED 分支（N<20 不覆盖）
- [ ] 7.4 GREEN：运行 Phase 6 广泛基线（同 Task 0.2），确认无新增失败
- [ ] 7.5 GREEN：dry-run 验证 schedule：
  ```powershell
  python -c "from scripts.phase6_6d_v2_orchestrator import _build_schedule; from pathlib import Path; s=_build_schedule('docs/phase6/6d-v2/dryrun'); on=[x for x in s['slices'] if x['arm']=='b1a_time_on_limited']; off=[x for x in s['slices'] if x['arm']=='b1a_time_off']; print('on_limited scheduled:', sum(x['scheduled_calls'] for x in on), 'cap:', sum(x['hard_cap'] for x in on)); print('off slices:', len(off), 'all v1_reuse:', all(x['source']=='v1_reuse' for x in off))"
  ```
  预期：on_limited scheduled=93 cap=243；off slices=15 全 v1_reuse
- [ ] 7.6 COMMIT：`test(6d-v2): offline gate pass, full regression, schedule dry-run`

**验证：** 离线门 PASS；回归无新增失败；dry-run schedule 正确（93/243，off 全 v1_reuse）。

---

## Task 8: 阶段二真实 paired dev（需用户明确批准 API）

**目标：** 运行 `off vs on_limited` paired dev，评估限制性注入有效性。

> **前提**：此阶段消耗真实 API（deepseek-v4-flash non-thinking，on_limited 臂 93 calls）。**必须用户明确批准后启动。**

- [ ] 8.1 用户批准 API 调用
- [ ] 8.2 运行：
  ```powershell
  python scripts/phase6_6d_v2_orchestrator.py run_dev --provider deepseek --model deepseek-v4-flash --output-dir docs/phase6/6d-v2 --run-id phase6-6d-v2-<date>-r1 --v1-archive-dir docs/phase6/6d/phase6-6d-v1-20260808-r1-6d-dev-2026-08-07-deepseek-deepseek-v4-flash-cc36fefa94c5 --v1-runs-dir docs/phase6/6d/runs/phase6-6d-v1-20260808-r1
  ```
- [ ] 8.3 off 复用校验（Task 4/6.2）通过
- [ ] 8.4 完整性门 + 基础设施门 + 准确率 gate
- [ ] 8.5 生成 `dev_gate.json` + `report.md` + 原子归档（off 来源标注 `6d-v1:<archive_id>`）
- [ ] 8.6 分析 paired_delta / min_case_delta / on_limited_acc vs 19.35%，按 spec §5.3 判定
- [ ] 8.7 COMMIT：`experiment(6d-v2): off vs on_limited paired dev`

**验证：** 原子归档完整；gate verdict 与 §5.3 成功标准对齐。

---

## 完成定义

1. Task 0-7 全部 GREEN + COMMIT
2. `_REASONED_ARM_MAP` 含 `b1a_time_on_limited` → none，测试通过（进程内 main + monkeypatch，不触发真实 API）
3. 版本常量 `TEMPORAL_CONTEXT_VERSION`/`EXPERIMENT_ID` = `6d-v2`，**三处字面量全改**（:1120/:1276/:1284），v2 可 resume 自己
4. off 复用校验器从 v1 `dev_gate.json`（归档）/`run_context.json`（runs/）读取 SHA 比对；off 数据从 slice 源头 `details.jsonl` 重建（不依赖 merged_details SHA）；漂移/缺失/experiment_id 异常拒绝
5. v2 `temporal_routed_cases.json` 由 Task 3.10 离线门生成，canonical SHA == v1（off 复用前提成立）
6. 独立 orchestrator schedule（on_limited 93/hard_cap 243）/gate（on_limited 聚合 + 拒绝 v1 on 遗留 + 分母 N×3）/report 契约确认
7. run_dev 流程：off 复用校验失败不消耗 API；off slice（v1_reuse）跳过**先于** ledger 判断；只跑 on_limited；merged 并入 off；`off_source`/`off_merged_details_sha256` 入 receipt
8. 阶段一离线门 PASS
9. 阶段二真实 dev 经用户批准后执行，产物原子归档

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| off 复用 SHA 漂移 | `_verify_off_reuse` fail-closed，漂移则 off 重跑（186 calls） |
| 复制改造漏改 `b1a_time_on` hardcode | Task 5 显式列出所有位置（:768,788,789,947,965）+ fail-closed 拒绝 v1 遗留 |
| 版本常量漏改 | Task 2 显式 + receipt/run_context 校验测试 |
| off slice 被误执行消耗 API | Task 3.8 跳过 v1_reuse slice + Task 6.7 测试 |
| 6D v1 目录被污染 | 独立 `docs/phase6/6d-v2/` + 只读 v1 归档 |
| 误以为 `run_context.json` 在归档目录 | **已实证：归档目录只有 `dev_gate.json`/`merged_details.jsonl`/slices；`run_context.json` 在 `runs/<user_run_id>/` 工作区。** Task 4 `_verify_off_reuse` 需同时接收 `v1_archive_dir` + `v1_runs_dir` |
| v1 `run_context.json` 无 temperature/profile/method 字段 | 已实证：这些是冻结常量，Task 4 直接用 `FROZEN_TEMPERATURE`/`FROZEN_PROFILE`/`FROZEN_METHOD` 比对，不从 run_context 读取 |
| **6D v1 归档 `merged_details_sha256` 与实际文件不匹配**（audit 记 `3539a5`，实际 `c4537d`） | **已实证**：Task 4 不硬性校验 merged SHA 与 audit 一致（否则永远 fail-closed）；改用 `_load_v1_off_data` 从 off slice 源头 `details.jsonl` 重建 off 数据；report 标注此 mismatch 为 6D v1 已知警示 |
| `experiment_id` 第三处字面量（:1284 resume 校验）漏改 | Task 2.3 引入 `EXPERIMENT_ID` 常量统一替换三处（:1120/:1276/:1284）；Task 2.4a 测试 v2 可 resume 自己 |
| 正向 subprocess 测试触发真实 API | Task 1.1 改为进程内 `main(argv)`（无 `--model-runner` → 走离线分支，不调模型）+ `--case-details-jsonl` 用 `tmp_path`（非 `NUL` 设备名）+ 断言 `rc != 2` 且 stdout 不含 `要求 arm`；无 monkeypatch（离线分支根本不调 `run_model_benchmark`） |
| v2 `temporal_routed_cases.json` 无 Task 生成 | Task 3.10-3.12 新增离线门生成步骤，先于 Task 4 |
| off provenance 未进 receipt | Task 6.6 把 `off_source`/`off_merged_details_sha256` 补入 `SIXD_RECEIPT_REQUIRED_FIELDS` |

回退：`--time-context-injection off`（默认），不修改 6D v1 归档。
