# Phase 7 MingLi-Bench 160 题冻结基线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **修订历史：** v1（按设计 v2.3 编写）→ v2（本地源码复审修订：6 P0 + 5 中优）→ v3（本地源码复审修订：3 P0 + 4 中优）→ v3.1（CONDITIONAL_PASS 两处中优闭环：Task 5 RED 预期修正——新测试在旧实现上失败、既有成功语义测试 GREEN 阶段才适配 Git 化夹具；Task 6.4 retest resume 身份全字段冻结——selected_case_ids/case_ids_sha256/scheduled_calls/hard_cap/attempt_stage 复用，禁止重算，漂移 fail-closed）

**Goal:** 按设计 v2.3 实现 Phase 7 测量链：adapter 双主键、runner detail 写 `chart_case_id`、stage fail-closed、官方 system prompt 进 payload、fetch provenance、Phase 7 orchestrator（含冻结 CLI 与端到端 fake-runner 测试）、零 API preflight；为阶段二真实测量（**需用户明确批准 API，本计划不含批准**）准备完备基础设施。

**Architecture:** 新建 `scripts/phase7_mingli_orchestrator.py`（参照 `scripts/phase6_6d_v2_orchestrator.py` 的 BudgetLedger/manifest 同源/原子归档模式）；改造 `benchmark/runners/mingli_bench_adapter.py`（双主键）、`benchmark/runners/run_benchmark.py`（detail 字段、system prompt 接线、stage choices、注释修正）、`benchmark/runners/resume_ledger.py`（ATTEMPT_STAGES）、`scripts/fetch_mingli_bench.py`（provenance）。

**设计依据：** `docs/superpowers/specs/2026-08-10-phase7-mingli-bench-baseline-design.md`（v2.3，已过多轮本地源码复审 PASS，入库 commit `15dd63f`）。

**设计冻结事实（执行者必须逐条遵守，不得再决策）：**

- 双主键：题目键 `case_id = mingli_ftb_0001`（官方 `id` 字段）；命盘键 `chart_case_id = case_1`（官方原始 `case_id`，fortune join 与聚类统计用）
- 官方数据实测分布：160 题 / 160 唯一 `ftb_NNNN` / 32 唯一 `case_N` / 每盘题数 = 30×5 + `case_19`×6 + `case_20`×4（**不是**每盘恰 5）
- 数据 SHA-256（pinned commit `b7433280fd86d7a7c27debbc47d0303c218f0bfd`，已三方核对一致）：
  - `data.json` = `528240929b23859656bf7ec0c126da92e2523c2cf091b11f83c0e8e377412054`（159402 bytes）
  - `fortune_api_results.json` = `e44ff5201486dc1917bbb24b6905a53e6a1359e76ada0eb8d5b2d9a5a88d29ed`（914720 bytes）
- runner 命令**不得传 `--ziwei-arm`**；`arm=phase7_mingli_baseline` 仅元数据，不进任何 reasoned 臂映射
- system prompt 切换条件精确为 `profile.profile_id == "mingli_official_cot_astro"`
- 单一 slice：单一 160 题 JSONL + 单一 case_ids_file；manifest 始终 `scheduled=160/hard_cap=180`；`max_cases` 合法转换仅 `{10 → 160}`
- 自动重试仅两类：网络（正常路径每键最多 3 次尝试 = 首次 + 2 重试）、截断（每键 ≤1）；parser invalid 无自动重试，走终态后 controlled retest
- **attempt stage 合法集合（全量冻结，已源码普查核实）**：`main, bazi, ziwei, judge, diversity_probe, anchor, dual, controlled_retest`——前 6 个为 `resume_ledger.py:25` 既有值，`anchor` 有既有测试真实使用（`tests/test_phase6_emit_samples.py:52`），`dual` 被 6B2 orchestrator 使用（`scripts/phase6_6b2_orchestrator.py:251`），`controlled_retest` 为本阶段新增
- `chart_case_id` 缺失拒绝**仅限** `mingli_official_cot_astro`；BaziQA profile 不报错
- 预算单一账本：main + retest 的 `call_attempt` 合计 ≤ 180；retest 由 orchestrator 预占剩余额度，resume 不重领（Task 6.4 公式）
- smoke 量化标准与 §8.1 十二条完整性硬门、§8.2 receipt 字段全集、`model_label = "DeepSeek-V4-Flash non-thinking"`，均见设计 §5/§8，本计划不重复豁免

---

## 实施边界与基线

只修改以下生产文件：

- `benchmark/runners/mingli_bench_adapter.py`（双主键改造）
- `benchmark/runners/run_benchmark.py`（detail 两处写 `chart_case_id`、`_call_once_messages` system prompt 接线、`--attempt-stage` choices、`:316` 注释修正）
- `benchmark/runners/resume_ledger.py`（`ATTEMPT_STAGES` 加 `dual`/`controlled_retest`）
- `scripts/fetch_mingli_bench.py`（`--manifest-out`、`--license-out`、`--source-dir` HEAD 校验、LICENSE SHA+副本）

只新建以下文件：

- `scripts/phase7_mingli_orchestrator.py`
- `tests/test_phase7_mingli_baseline.py`（runner 侧：detail 字段、system prompt payload、stage 校验）
- `tests/test_phase7_mingli_orchestrator.py`（orchestrator 侧：CLI、argv 同源、env 净化、状态机、预算预占、完整性硬门、smoke 判定、原子发布、receipt、fake-runner 端到端）

既有测试文件仅追加/改造用例：`tests/test_mingli_bench_adapter.py`（双主键）、`tests/test_phase6_resume.py`（stage vocabulary）、`tests/test_fetch_mingli_bench.py`（夹具 Git 化改造，Task 5 P0-1）。

不修改：`bazi_calculator.py`、`benchmark/formatters/*`（`mingli_prompt.py` 只引用不改）、`claude_api.py`、`config.py`、`scripts/phase6_*` 全部、`scripts/run_mingli_bench.py`（旧 wrapper 保持原样，Phase 7 不走它）、**`AGENTS.md`（v3 冻结：本轮不改，从 Task 8.5 移除自由裁量）**。

**工作区警告（Task 0 必须处理）：** 工作区存在他人的知识库蒸馏变更（v3 复审时实况：`knowledge_base/classic_texts/**` 七个文件 unstaged 修改 + `scripts/distill_lib.py`、`scripts/regen_mcq.py`、`.tmp_verify.py`、`docs/phase6/6d/ablation_holdout_combined.jsonl`、`knowledge_base/classic_texts/_regen_mcq_log.txt` 等 untracked；具体以 Task 0.2 记录的实况为准）。**本计划所有 commit 必须用显式 pathspec，绝不允许 `git commit -a` 或裸 `git commit`**；每个 COMMIT 步骤必须先 `git add -- <精确文件>` 并用 `git diff --cached --name-only` 核对暂存清单恰好等于本任务文件集。把他人变更卷进 Phase 7 提交，或新建文件因未 `git add` 而漏出提交，均视为任务失败。

### TDD 约定

每个任务遵循 RED-GREEN-COMMIT：
- **RED**：先写测试，运行确认失败（`python -m pytest <file> -q`）
- **GREEN**：实现最小代码使测试通过
- **COMMIT**：`git add -- <文件>` → `git diff --cached --name-only` 核对 → `git commit -m "..." -- <同一文件列表>`
- 合并前全量回归（见 Task 8）

---

## Task 0: 基线验证与受控工作区检查

**目标：** 确认起始状态，记录基线，隔离他人变更。

- [ ] 0.1 确认设计基线已入库：
  ```powershell
  git log --oneline -1
  # 应显示 15dd63f docs(phase7): freeze MingLi-Bench 160-question baseline design v2.3
  git status --short docs/superpowers/specs/2026-08-10-phase7-mingli-bench-baseline-design.md
  # 应无输出
  ```
- [ ] 0.2 记录他人工作区变更**全口径基线**（porcelain + **所有非 Phase 7 变更/未跟踪文件**的 SHA，供 Task 8.4 同口径比对）：
  ```powershell
  git status --porcelain=v1 | Out-File .tmp/phase7-workspace-baseline.txt
  python -c "
  import hashlib, os
  lines = open('.tmp/phase7-workspace-baseline.txt', encoding='utf-8').read().splitlines()
  for line in lines:
      path = line[3:].strip()
      if path and os.path.isfile(path) and 'phase7' not in path:
          print(hashlib.sha256(open(path, 'rb').read()).hexdigest(), path)
  " | Out-File -Append .tmp/phase7-workspace-baseline.txt
  ```
  （显式 `import os`，不用 `glob.os` 内部属性；覆盖 porcelain 列出的全部文件，不只两个脚本。porcelain 路径含空格/引号的边界情形如出现，先处理再记录，不得静默跳过。）
- [ ] 0.3 运行定向基线并记录：
  ```powershell
  python -m pytest tests/test_mingli_bench_adapter.py tests/test_fetch_mingli_bench.py tests/test_run_mingli_bench_cli.py tests/test_phase6_resume.py tests/test_phase6_profiles.py tests/test_phase6_emit_samples.py -q --basetemp .tmp/pytest-phase7-plan-baseline
  ```
  记录 passed/failed 到 `.tmp/phase7-baseline.txt`。这些文件的全绿是后续任务的回归底线。
- [ ] 0.4 普查既有 `--attempt-stage` 使用值（仓库约定用 `rg`，不用 `grep`）：
  ```powershell
  rg -n "attempt-stage|attempt_stage" scripts/ tests/ benchmark/ -g "*.py"
  ```
  把所有实际出现的 stage 值记入 `.tmp/phase7-baseline.txt`。**合法集合已全量冻结**（见计划头部）：`main, bazi, ziwei, judge, diversity_probe, anchor, dual, controlled_retest`。已知在用值：`main`（多处）、`anchor`（`tests/test_phase6_emit_samples.py:52`）、`dual`（`scripts/phase6_6b2_orchestrator.py:251`）。若发现该集合**之外**的值，**停下来回报**，不得擅自扩 vocabulary。

---

## Task 1: adapter 双主键改造（设计 §3.0）

**目标：** `load_and_normalize` 产出题目唯一键 + 命盘分组键；fortune join 改用命盘键。

**关键事实（已核实）：**
- 现状 `benchmark/runners/mingli_bench_adapter.py:239`/`:245` 用 `entry["case_id"]`（命盘键）作题目主键，同盘题碰撞。
- 官方数据每题有 `id=ftb_NNNN`（160 唯一）、`case_id=case_N`（32 唯一）。
- 既有测试夹具（`tests/test_mingli_bench_adapter.py:130-174`）**无 `id` 字段**（如 `case_121` 官方形状、`fixture_c001_q1` 旧形状），期望 `mingli_case_121` / `mingli_fixture_c001_q1`。**这些测试必须保持全绿**——缺 `id` 时回退旧行为，不得 fail-closed（fail-closed 的唯一性断言在 Task 7 preflight 对真实数据执行）。

- [ ] 1.1 RED：在 `tests/test_mingli_bench_adapter.py` 追加：
  - `test_official_entries_with_id_get_unique_question_keys`：两条 entry 共享 `case_id="case_1"`、`id="ftb_0001"`/`"ftb_0002"` → normalized `case_id == ["mingli_ftb_0001", "mingli_ftb_0002"]`（互不相同），两行 `chart_case_id == "case_1"`。
  - `test_fortune_join_uses_chart_case_id`：`include_astro=True`，fortune 索引键为原始 `case_1` → 两条同盘题都命中 `chart_input`。
  - `test_missing_id_falls_back_to_case_id_key`：无 `id` 的 entry（`case_121`）→ `case_id == "mingli_case_121"` 且 `chart_case_id == "case_121"`（既有行为回归锁）。
  - `test_already_namespaced_id_not_double_prefixed`：`id` 已带 `mingli_` 前缀 → 不二次加前缀。
  运行确认 4 条新测试 FAIL、既有测试仍 PASS。
- [ ] 1.2 GREEN：改 `mingli_bench_adapter.py` `load_and_normalize`：
  - 题目键：`qid = entry.get("id")`；有 `qid` 则 `case_id = mingli_{qid}`（已带前缀不重复加）；无则走现有 `case_id` 命名空间逻辑。
  - `chart_case_id = str(entry.get("case_id") or "")`，写入 row。
  - fortune 查找改为 `fortune_data.get(chart_case_id)`（删除对命名空间键的兜底查找 `fortune_data.get(case_id)`——命名空间键不可能在 fortune 索引中，该兜底是死代码；**先确认既有测试无依赖再删，有依赖则保留并在 commit 信息说明**）。
- [ ] 1.3 运行 `tests/test_mingli_bench_adapter.py` 全绿 + `tests/test_run_mingli_bench_cli.py`、`tests/test_mingli_canonical.py` 无回归。
- [ ] 1.4 COMMIT：
  ```powershell
  git add -- benchmark/runners/mingli_bench_adapter.py tests/test_mingli_bench_adapter.py
  git diff --cached --name-only   # 必须恰好为上述 2 个文件
  git commit -m "feat(phase7): dual primary keys in mingli adapter..." -- benchmark/runners/mingli_bench_adapter.py tests/test_mingli_bench_adapter.py
  ```

---

## Task 2: runner detail 显式写 `chart_case_id`（设计 §3.0，profile 限定）

**目标：** main/retest 所有终态 detail 带 `chart_case_id`；缺失拒绝仅限 `mingli_official_cot_astro`。

**关键事实（已核实）：**
- detail 是显式字典构造：call_failed 路径 `run_benchmark.py:1353`、正常/invalid 路径 `:1432`，两处均无 `chart_case_id`，不会自动透传。
- profile 判定可用全局 `_PHASE6_CTX.profile_id`（`:185`），或构造点所在函数的局部 `profile`/`profile_formatter`（执行时以实际作用域为准，二选一，保持两处一致）。
- 集成测试可复用 `tests/test_phase6_emit_samples.py` 的 `RunnerEnv` harness 模式（tmp 环境 + monkeypatch 模型层 + argv 驱动 runner），case 数据走 `RunnerEnv` 支持的注入方式；若 `RunnerEnv` 不支持自定义 case 字段，按其模式写一个最小等价物并在 commit 说明。

- [ ] 2.1 RED：新建 `tests/test_phase7_mingli_baseline.py`：
  - 辅助函数（建议 `_detail_chart_case_id(case, profile_id)`）三例单元测试：mingli official + 有值 → 返回值；mingli official + 缺失 → `RuntimeError`（fail-closed）；baziqa profile + 缺失 → `None`（不报错）。
  - 集成例 1（正常/invalid 路径 `:1432`）：profile=mingli_official_cot_astro + 带 `chart_case_id="case_1"` 的 case，模型返回答案 → detail 行 `chart_case_id == "case_1"`；模型返回不可解析文本（invalid 终态）→ detail 行同样带该字段。
  - 集成例 2（call_failed 路径 `:1353`）：模型层抛异常耗尽重试 → `failure_detail["chart_case_id"] == "case_1"`。
  运行确认 FAIL。
- [ ] 2.2 GREEN：实现辅助函数；`run_benchmark.py:1353` 与 `:1432` 两处 detail 字典各加一行 `"chart_case_id": _detail_chart_case_id(case, <profile_id>)`。
- [ ] 2.3 运行新测试 + `tests/test_phase6_resume.py` + `tests/test_phase6_emit_samples.py` 全绿。
- [ ] 2.4 COMMIT：
  ```powershell
  git add -- benchmark/runners/run_benchmark.py tests/test_phase7_mingli_baseline.py
  git diff --cached --name-only   # 必须恰好为上述 2 个文件
  git commit -m "feat(phase7): write chart_case_id into runner terminal details..." -- benchmark/runners/run_benchmark.py tests/test_phase7_mingli_baseline.py
  ```

---

## Task 3: `ATTEMPT_STAGES` 扩 vocabulary + fail-closed 校验 + 注释修正（设计 §3.6）

**目标：** `dual`、`controlled_retest` 合法化；未知 stage 拒绝；既有 `anchor`/`dual` 链路不受影响。

**关键事实（已核实）：**
- `resume_ledger.py:25` 现有 `("main", "bazi", "ziwei", "judge", "diversity_probe", "anchor")`，无 `dual`/`controlled_retest`；`build_attempt_key()`（`:29`）无成员检查；`run_benchmark.py:1753` `--attempt-stage` 无 `choices`。
- `anchor` 有既有测试在用（`tests/test_phase6_emit_samples.py:52`）、`dual` 被 6B2 使用（`scripts/phase6_6b2_orchestrator.py:251`）——choices 必须含全量 8 值（见计划头部冻结集合）。
- `run_benchmark.py:316` docstring"每键最多 3 次重试（4 次尝试）"与实际门禁（`:328` `retry_counts >= 3` 调用前拒绝 → 正常路径每键最多 3 次尝试）不符。

- [ ] 3.1 RED：在 `tests/test_phase6_resume.py` 追加：
  - `dual`、`controlled_retest` ∈ `ATTEMPT_STAGES`；全量集合恰为冻结的 8 值。
  - `--attempt-stage bogus` 解析即拒绝（argparse choices → `SystemExit` 非 0；用 runner main 的 argv 解析层测试，参照该文件既有 argparse 测试模式）。
  - `--attempt-stage main` / `anchor` / `dual` / `controlled_retest` 解析通过。
  运行确认 FAIL。
- [ ] 3.2 GREEN：
  - `resume_ledger.py:25` 改为 `("main", "bazi", "ziwei", "judge", "diversity_probe", "anchor", "dual", "controlled_retest")`。
  - `run_benchmark.py:1753` 加 `choices=ATTEMPT_STAGES`（确认该处能 import 到，循环导入则用启动时断言替代并在 commit 说明）。
  - 修正 `run_benchmark.py:316` 注释为："正常执行路径每键最多 3 次网络尝试（首次 + 2 次重试）；`before_call` 先记账后调用，crash/resume 可因 pre-call journal 累计 call_attempt=4，属崩溃续跑账本语义，不算第 3 次重试。"
- [ ] 3.3 回归：`tests/test_phase6_resume.py` + `tests/test_phase6_emit_samples.py` + `tests/test_phase6_6b1d_profiles.py` + `tests/test_phase6_profiles.py` 全绿；对照 Task 0.4 清单确认无冻结集合之外的 stage 被 choices 拒绝。
- [ ] 3.4 COMMIT：
  ```powershell
  git add -- benchmark/runners/resume_ledger.py benchmark/runners/run_benchmark.py tests/test_phase6_resume.py
  git diff --cached --name-only   # 必须恰好为上述 3 个文件
  git commit -m "feat(phase7): fail-closed attempt-stage vocabulary incl dual and controlled_retest..." -- benchmark/runners/resume_ledger.py benchmark/runners/run_benchmark.py tests/test_phase6_resume.py
  ```

---

## Task 4: 官方 system prompt 真实进入 payload（设计 §3.3）

**目标：** `mingli_official_cot_astro` 的 system message = `OFFICIAL_SYSTEM_PROMPT`；其它 profile 不变。

**关键事实（已核实）：**
- `run_benchmark.py:591-607` `_call_once_messages` 经 `:600` `_resolve_system_prompt(...)` 恒得通用 `SYSTEM_PROMPT_BENCHMARK`；`_PHASE6_CTX` 在 `:604` 已被同函数使用，可直接取 `profile_id`。
- `OFFICIAL_SYSTEM_PROMPT` 在 `benchmark/formatters/mingli_prompt.py:19`（该文件只引用不改）。

- [ ] 4.1 RED：在 `tests/test_phase7_mingli_baseline.py` 追加（mock `claude_api.call_model_messages_sync_with_meta` 捕获 `system_prompt` 实参）：
  - ctx.profile_id = `mingli_official_cot_astro` → 捕获值 == `OFFICIAL_SYSTEM_PROMPT`。
  - ctx.profile_id = `baziqa_xjz_reasoned` → 捕获值 == `_resolve_system_prompt` 结果（非 OFFICIAL）。
  - ctx 为 None → 行为与改造前逐字节一致。
  运行确认 FAIL。
- [ ] 4.2 GREEN：`_call_once_messages` 中按 `_PHASE6_CTX is not None and _PHASE6_CTX.profile_id == "mingli_official_cot_astro"` 切换 system_prompt 为 `OFFICIAL_SYSTEM_PROMPT`（函数内局部 import `mingli_prompt`，避免顶层循环导入）。
- [ ] 4.3 回归：`tests/test_phase7_mingli_baseline.py` + `tests/test_phase6_profiles.py` 全绿；`prompt_fingerprint` 未变（`profiles.py:256` 逻辑未动，指纹值不应漂移——跑相关指纹测试确认）。
- [ ] 4.4 COMMIT：
  ```powershell
  git add -- benchmark/runners/run_benchmark.py tests/test_phase7_mingli_baseline.py
  git diff --cached --name-only   # 必须恰好为上述 2 个文件
  git commit -m "fix(phase7): route OFFICIAL_SYSTEM_PROMPT into payload for mingli_official_cot_astro..." -- benchmark/runners/run_benchmark.py tests/test_phase7_mingli_baseline.py
  ```

---

## Task 5: fetch provenance 补强（设计 §3.7）

**目标：** `--manifest-out`、`--license-out`、`--source-dir` git HEAD 校验、LICENSE SHA+副本；**既有夹具 Git 化改造**。

**关键事实（已核实）：** `scripts/fetch_mingli_bench.py` 现状：`--source-dir` 不验 HEAD（`:61-65`）；manifest 写死 `.tmp/phase6/`（`:19`）；LICENSE 只记一句话（`:46-51`）。`PINNED_COMMIT` 是模块常量（`:16`），测试可 monkeypatch。**既有 `tests/test_fetch_mingli_bench.py:13-37` 的 `make_source()` 是普通非 Git 目录且 `test_fetch_from_source_dir` 期望退出 0——HEAD 校验落地后该测试必变 BLOCKED，必须同步改造夹具（v2 复审 P0-1）。**

**参数冻结（不再留"建议"）：**
- `--manifest-out`：manifest 输出路径，本阶段传 `docs/phase7/mingli_fetch_manifest.json`；默认值保持 `.tmp/phase6/mingli_fetch_manifest.json` 以兼容既有测试。
- `--license-out`：LICENSE 副本输出**目录**，默认 `docs/phase7/`；副本文件名保持源文件名（如 `LICENSE`）；manifest 新增 `license_sha256` 与 `license_copy_path` 两个字段。
- 测试用临时 git 仓库必须先设 repo-local 身份：`git config user.name test` + `git config user.email test@example.com`（不得依赖全局 git 配置）。

**既有夹具改造冻结（与功能实现同任务、同 commit）：**
- `make_source()` 改为初始化临时 Git 仓库（`git init` + repo-local user 配置 + 提交全部文件），返回 repo 路径与其 HEAD sha；
- `test_fetch_from_source_dir` 把 `PINNED_COMMIT` monkeypatch 为该临时 HEAD，并**显式传 `--manifest-out`/`--license-out` 指向 tmp 路径**（不得写真实 `docs/phase7/`）；
- `test_missing_required_file_blocked` 的目录同样先 Git 化且 HEAD 匹配——确保实际测试的是"缺文件"，而非提前被"非 Git 来源"阻断；
- `test_missing_source_dir_blocked`（不存在路径）保持非 Git 即拒，语义不变。

- [ ] 5.1 RED（v3 复审修正：旧实现 `--source-dir` 路径完全忽略 `PINNED_COMMIT`，仅 monkeypatch 它不会自然产生红灯；既有成功语义测试在 RED 阶段保持原样、允许继续通过）：
  - 既有三个测试**不动**，确认仍全绿（旧实现上）。
  - 追加新用例（在旧实现上必须 FAIL）：
    - `--manifest-out <path>` / `--license-out <dir>`：旧 argparse 不认识参数 → 失败；GREEN 后断言 manifest 写到指定路径、LICENSE 副本落盘且 manifest 含 `license_sha256` + `license_copy_path`；
    - `--source-dir` 指向非 git 目录 → 期望退出 4 + BLOCKED（旧实现返回 0 → 红）；
    - `--source-dir` git 仓库但 HEAD ≠ pinned（monkeypatch `PINNED_COMMIT` 为另一值）→ 期望 BLOCKED（旧实现不校验返回 0 → 红）；
    - `--source-dir` HEAD == pinned → 期望 OK（旧实现也返回 0，此例在红绿两阶段都应通过，作回归锁）。
  运行确认：新用例除最后一例外 FAIL，既有三测试 PASS。
- [ ] 5.2 GREEN：实现两参数 + HEAD 校验；**同步骤适配 Git 化夹具**（`make_source()` 返回 repo 路径 + HEAD、成功测试 monkeypatch `PINNED_COMMIT` 为临时 HEAD 并显式传 tmp `--manifest-out`/`--license-out`、`test_missing_required_file_blocked` Git 化且 HEAD 匹配）；保持网络 clone 路径（无 `--source-dir`）既有行为不变。
- [ ] 5.3 回归：`tests/test_fetch_mingli_bench.py` 全绿（含改造后的既有三测试）。
- [ ] 5.4 COMMIT：
  ```powershell
  git add -- scripts/fetch_mingli_bench.py tests/test_fetch_mingli_bench.py
  git diff --cached --name-only   # 必须恰好为上述 2 个文件
  git commit -m "feat(phase7): fetch provenance (manifest-out/license-out/HEAD verify)..." -- scripts/fetch_mingli_bench.py tests/test_fetch_mingli_bench.py
  ```

---

## Task 6: Phase 7 orchestrator（设计 §3.2/§3.4/§3.5/§3.6/§8）

**目标：** 新建 `scripts/phase7_mingli_orchestrator.py`：冻结 CLI + 单一 slice 调度 + 预算 + 硬门 + 归档 + receipt + 端到端 fake-runner 测试。参照 `scripts/phase6_6d_v2_orchestrator.py` 的 `BudgetLedger`（`:351`）、`_build_runner_command`/`_slice_runner_args` 同源对（`:505`/`:540`）、`_check_completeness`（`:839`）、`_create_archive`（`:1173`）、`_publish_receipt_atomic`（`:1280`）、`_prepare_run_context`（`:1370`）、`_validate_run_id`（`:1441`）。

每个子任务独立 RED-GREEN；测试集中放 `tests/test_phase7_mingli_orchestrator.py`。

**CLI 冻结（v2 P0-2；v3 P0-2 补 run_id/resume 契约）：**

```text
python scripts/phase7_mingli_orchestrator.py preflight [--work-dir .tmp/phase7]
    零 API：数据完整性 + 协议 + 环境净化 + 预算核验 → docs/phase7/preflight_receipt.json
python scripts/phase7_mingli_orchestrator.py run --run-id <safe-id> [--resume] [--output-dir .tmp/phase7/run]
    生产链：归一化 → smoke(max_cases=10) → 判定 → resume(max_cases=160) → retest → 硬门 → 归档+receipt
退出码：0 = PASS/成功；2 = 用法/manifest/状态机/run_id 契约类拒绝；4 = BLOCKED（对齐 fetch 的 BLOCKED_EXIT）
`run` 内部按 run context 状态机自驱动，不需要用户分步调 runner；阶段二批准后直接执行 `run`。
```

**run_id / 跨进程 resume 契约（v3 P0-2 冻结）：**
- `--run-id` 必填，安全字符集校验（对齐 6D `_validate_run_id`）；非法或 path traversal（含 `..`、路径分隔符、空白）→ 退出 2。
- 同一 `run_id` 已有产物目录但未传 `--resume` → 拒绝（退出 2），防误覆盖。
- 传 `--resume` 但 run context / manifest 缺失 → 拒绝（退出 2）。
- smoke 后进程崩溃：同一 `run_id --resume` 从 run context 记录的阶段继续（剩余题续跑，已落盘终态不重跑）。
- 该 `run_id` 已发布 receipt 后再次执行 `run`（无论是否 `--resume`）→ 拒绝（退出 2），防已发布实验重复计费。
- 以上五种情形每种至少 1 个测试。

- [ ] 6.1 CLI 骨架 + argv 同源：`main()` argparse 两子命令 + 上述退出码契约 + `--run-id`/`--resume` 契约校验；`_build_runner_command()` 产出设计 §3.2 冻结 argv（含 `--profile mingli_official_cot_astro --method direct_choice --thinking-mode disabled --temperature 0.0 --arm phase7_mingli_baseline --attempt-stage main --scheduled-calls 160 --hard-cap 180 --case-ids-file ... --as-of-date ...`）。测试：两子命令解析、非法子命令退出 2、run_id 五情形、argv **不含 `--ziwei-arm`**、`_slice_runner_args()` 重建参数与 argv 逐项一致（仿 6B2 ManifestHomology）。
- [ ] 6.2 env 净化：`_build_child_env()` 显式删除 `BAZI_RAG`/`BAZI_RAG_CORPUS`/`BAZI_FEWSHOT_FILE`/`BAZI_APB_BLOCK`；负向测试：父环境设 4 变量 → 子 env 无；manifest/run context 记录 `rag=false fewshot=false apb=false shuffle_options=false`。
- [ ] 6.3 `max_cases` 状态机：run context 记录 `smoke_size=10` 与阶段（`smoke_first_pass`/`main_resume`）；合法转换集合 `{10 → 160}`，其它（10→20、160→10、无 smoke 记录直接 160）拒绝（退出 2）；测试覆盖合法与三种非法。
- [ ] 6.4 BudgetLedger + retest 预算预占（公式冻结，v2 P0-3 修订 + v3 P0-3 resume 契约）：

  首次进入 retest：
  ```text
  allocation        = 180 − call_attempt(main events 合计)
  scheduled_calls   = min(len(eligible), allocation)   # eligible = main 终态 invalid/call_failed，按 mingli_ftb_ 升序
  retest manifest.hard_cap = allocation                 # 写入 retest resume manifest 冻结
  ```
  retest 崩溃后 resume（身份全字段冻结复用，v3 复审补全）：
  ```text
  从既有 retest manifest 读取并复用以下冻结字段，禁止重算 eligible、禁止重新排序、禁止生成新 case IDs 文件：
    selected_case_ids（含顺序）、case_ids_sha256、scheduled_calls、hard_cap=allocation、attempt_stage=controlled_retest
  runner 用同一 --hard-cap <allocation> --resume
  已消耗从 retest events 的 call_attempt 恢复
  启动前断言 call_attempt(main) + call_attempt(retest) ≤ 180
  ```
  额度不足时按序耗尽即停；**两类未复测题都入报告**：未入选的 eligible + 入选但因重试挤占未执行的 selected。测试：三值计算、顺序、两类清单、retest argv 为 `--attempt-stage controlled_retest --scheduled-calls <selected> --hard-cap <allocation>`；**"retest 部分完成 → 崩溃 → resume 不重领预算"**：合成 retest events 已消耗 k 次，resume 后 hard_cap 不变、剩余额度 = allocation − k、全程总和不超 180；**首次运行与 resume 重建的 retest manifest/argv 全字段同源**（上述五字段逐项一致）；**任一 selected IDs、scheduled_calls、hard_cap 漂移时 fail-closed**（退出 2）。
- [ ] 6.5 smoke 量化判定（设计 §5）：输入 smoke 后 detail/events，断言 terminal detail 恰 10 条、`call_failed=0`、`gate_blocked=0`、parsed ≥ 9、逐 attempt key 对账（每键 `call_attempt 数 = 1 + model_call_failed 事件数`、无残缺 pre-call journal）；测试覆盖全过 + 五种失败各一。
- [ ] 6.6 完整性硬门（设计 §8.1 十二条）：`_check_completeness()` 逐条断言，任一失败 `completeness_verdict = BLOCKED_INCOMPLETE`；第 4/12 条用 normalized dataset 交叉验证 `chart_case_id`（分布 30×5 + `case_19`×6 + `case_20`×4；detail 行与 normalized 按题目 `case_id` join 一致）。**测试覆盖冻结：十二条每条至少 1 个独立负向测试 + 1 个 COMPLETE 正例，共 ≥13 个测试**；合成 160 行夹具（ftb_0001–ftb_0160 / case_1–case_32 / 19 盘 6 题、20 盘 4 题）。
- [ ] 6.7 receipt + 原子发布（直接复用 6D 已验证契约，不得自造变体）：
  - 发布函数签名与 `phase6_6d_v2_orchestrator.py:1280` 对齐：`validated_bytes` + `expected_sha256` 必填，缺 `validated_bytes` 直接 SystemExit；写 tmp → 重算 SHA 比对 → `os.replace`；**禁止**校验后重读可变源。
  - corruption-hook 测试：monkeypatch 使 tmp 写入后字节被篡改（或 SHA 函数被 hook），断言 (a) hook 确实被触发、(b) 发布被拒且 tmp 被清理、(c) 目标 receipt 不存在。
  - `audit_index.json` 生成（含 main/retest detail/events/manifest SHA + merged_details SHA + 硬门逐项结果 + 复测清单 + run context）；发布 receipt 前重算校验 audit index SHA，缺失或漂移 → 禁止发布（退出 4）。
- [ ] 6.8 `phase7_code_fingerprint` 四层交叉验证：指纹覆盖设计 §8.4 九文件（`_CODE_SCOPE` 不动，orchestrator 侧独立字段）；**同时写入** run manifest、run context、audit index、receipt 四处；测试断言四层值一致且与现算值一致，任一层缺失/漂移即拒绝。
- [ ] 6.9 端到端 fake-runner 集成测试（no-network，v3 中优加固）：测试内嵌 fake runner（monkeypatch `subprocess.run` 或注入 stub 脚本，生成合规 detail/events/manifest）；**同时把真实网络/API 入口 monkeypatch 为"调用即失败"**（`claude_api.call_model_messages_sync_with_meta`、`scripts/fetch_mingli_bench` 的网络 clone 路径、`subprocess` 中任何指向真实 runner 的调用），证明测试链零网络。走完整 `preflight → run(smoke→resume→retest→硬门→归档+receipt)` 链；断言：退出码、run context 状态转换记录、retest argv 预算参数、receipt 字段全集、audit index SHA 一致。另测硬门失败分支：fake runner 产出缺 1 题 → 退出 4 且无 receipt。
- [ ] 6.10 自验：`python -m pytest tests/test_phase7_mingli_orchestrator.py -q` 全绿；`python -m ruff check scripts/phase7_mingli_orchestrator.py tests/test_phase7_mingli_orchestrator.py` 干净。
- [ ] 6.11 COMMIT：
  ```powershell
  git add -- scripts/phase7_mingli_orchestrator.py tests/test_phase7_mingli_orchestrator.py
  git diff --cached --name-only   # 必须恰好为上述 2 个文件
  git commit -m "feat(phase7): orchestrator with frozen CLI, budget ledger, hard gates, atomic publish..." -- scripts/phase7_mingli_orchestrator.py tests/test_phase7_mingli_orchestrator.py
  ```

---

## Task 7: 零 API preflight 执行（设计 §4，真实数据，无 LLM API）

**目标：** 真实拉取 pinned 数据 + preflight 子命令全断言 PASS，落盘 `docs/phase7/`。**此任务需要外网（git clone GitHub），不需要 LLM API；无外网则记录 BLOCKED 原因并停在此任务。**

- [ ] 7.1 执行改造后 fetch：
  ```powershell
  python scripts/fetch_mingli_bench.py --manifest-out docs/phase7/mingli_fetch_manifest.json --license-out docs/phase7
  ```
  断言：退出码 0；manifest 的 pinned_commit 经 `git rev-parse HEAD` 证明；`data.json`/`fortune_api_results.json` 的 SHA-256 与本计划头部冻结值一致；LICENSE SHA + 正文副本在 `docs/phase7/`。
- [ ] 7.2 执行 preflight 子命令（入口已在 Task 6 CLI 冻结，不再另选）：
  ```powershell
  python scripts/phase7_mingli_orchestrator.py preflight
  ```
  逐项断言并产出 `docs/phase7/preflight_receipt.json`：
  - 完整性：`data.json` 恰 160 题；唯一 `id` 160；唯一 `case_id` 32；分布 30×5 + `case_19`×6 + `case_20`×4；adapter 归一化产出 160 唯一 `case_id` + 32 唯一 `chart_case_id`；fortune join 32/32 命中；年份（`_infer_year` 由 `question_number` 推导，2022–2025）与 12 类别分布记录。
  - 协议：`mingli_official_cot_astro` 解析通过；official profile + `ziwei_arm=None` 的 `visibility_requirements` required 恰含三 astro marker（`八字命盘信息：`/`紫微命盘信息：`/`十二宫位星曜分布：`）；parser 合成样例可解析。
  - 环境净化负向测试通过（6.2）；预算核验 scheduled=160/hard_cap=180 + `{10→160}` 状态机冻结（6.3）。
- [ ] 7.3 `preflight_receipt.json` verdict = PASS；任一断言失败 → BLOCKED，**修复后重跑，不得带 BLOCKED 进入 Task 8 收尾**。
- [ ] 7.4 COMMIT（**枚举文件，不用目录通配**，v3 中优）：
  ```powershell
  git add -- docs/phase7/mingli_fetch_manifest.json docs/phase7/LICENSE docs/phase7/preflight_receipt.json
  git diff --cached --name-only   # 必须恰好为上述文件（LICENSE 文件名以 fetch 实际落盘为准，先 ls docs/phase7 核对）
  git commit -m "chore(phase7): preflight receipt + fetch manifest + LICENSE copy..." -- docs/phase7/mingli_fetch_manifest.json docs/phase7/LICENSE docs/phase7/preflight_receipt.json
  ```

---

## Task 8: 全量回归与收尾

- [ ] 8.1 受影响测试门控：`python scripts/affected_tests.py --run`。
- [ ] 8.2 全量非 E2E：`python -m pytest -m "not e2e" -q`，对照 `.tmp/phase7-baseline.txt`，不得新增失败。
- [ ] 8.3 机械化门禁：`python -m ruff check .`（`ruff.toml`）+ `python -m mypy`（`mypy.ini` 白名单内文件若被本计划触碰须过）。
- [ ] 8.4 工作区审计（与 Task 0.2 同口径）：`git status --porcelain=v1` + 同批文件 SHA 重算，与 `.tmp/phase7-workspace-baseline.txt` 比对——他人知识库蒸馏变更集合未被任何 Phase 7 commit 卷走、内容未被修改（SHA 一致）；`git log --oneline` 逐条核对本计划 commit 均带显式 pathspec 且暂存清单合规。
- [ ] ~~8.5~~ **（v3 冻结删除）本轮不改 `AGENTS.md`**；Phase 7 orchestrator 的目录要点更新留给阶段二完成后的独立文档任务。

---

## Task 9（BLOCKED — 需用户明确批准 API，本计划未获批准）

**未经用户在会话中明确批准，不得执行本任务任何步骤。** 批准后的执行序列（设计 §5；CLI 已在 Task 6 冻结，orchestrator 内部自驱动 smoke→resume→retest→硬门→归档）：

- [ ] 9.1 执行 `python scripts/phase7_mingli_orchestrator.py run --run-id <批准的 run-id>`；确认 smoke（`max_cases=10`）后 6.5 量化判定全过才进入 resume（orchestrator 内部门禁，失败即退出 4）。
- [ ] 9.2 主测续跑完成后确认 run context 状态转换为 `10 → 160`、main detail 160 行。
- [ ] 9.3 受控复测产物核验：`retest/detail.jsonl`、`retest/events.jsonl`、独立 manifest（`hard_cap` = 首次冻结的 allocation）；全局 `call_attempt` 合计 ≤ 180；未复测清单（两类）入报告。
- [ ] 9.4 硬门 COMPLETE → 原子归档 + receipt + `audit_index.json` 落盘 `docs/phase7/`。
- [ ] 9.5 报告：设计 §6 预声明内容（主指标 + Wilson + 32 盘聚类 bootstrap/macro、分类别、终态分布、复测清单、跨基准对照表）。
