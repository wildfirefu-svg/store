# Phase 6 6B2 双管线+judge 实施计划 — 实施前审核报告

**审核日期**：2026-07-20（当前实际日期）
**审核文档**：`docs/superpowers/plans/2026-08-02-phase6-6b2-dual-system-judge.md`（v8，2557 行，17 任务）
**关联设计**：`docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md` v6 §7
**审核方式**：两路并行——代码库事实核验（17 项）+ 计划全文内部一致性审查；阻断项全部经本人逐点复验
**前置状态**：6B1 已证实有信号（Δ_dev=+7.08pp，两年均正，PROMOTE_CANDIDATE），6B2 触发条件成立
**审核结论**：**NEEDS_REVISION——3 个确认阻断 + 1 个待实施时验证的疑似阻断 + 6 个中优项。另：审核期间文件被并行修改（2512→2557 行），建议定稿后复核行号。**

---

## 一、确认阻断（必须修复）

### B1：judge 分歧率 60.8% 是无源数字，实测为 57.9%

计划 :675 `JUDGE_DISAGREEMENT_RATE = 0.608`、:1557 报告"实际 vs 60.8%"、:2534 自审清单"60.8% 修正"。全库搜索 60.8/0.608 仅命中计划自身；6B1 report.md/audit_index.json 均无此数。**实测** 6B1 merged_details（720 行）：b1a′↔b1b（即 dual 的 bazi↔ziwei 对）分歧率 = 139/240 = **57.9%**（2024: 58.3%，2025: 57.5%）；b1a′↔b1c = 52.5%。无任何口径得 60.8%。judge 预算修正依据错误，应改为实测 57.9%（或写明出处）。另：`JUDGE_DISAGREEMENT_RATE` 定义后无人引用（报告处硬编码字面量），应统一走常量。

### B2：`test_archive_refuses_incomplete_schedule`（:2042）必然错误失败

```python
sched=_build_schedule(str(tmp_path/"run"), years=["2024","2025"])
```

未传 `dataset_paths`，而 `_build_schedule`（:690-692）对缺失路径直接 `raise SystemExit("拒绝: 数据集路径不存在或未指定")`——**在 `with pytest.raises(SystemExit)` 块外**抛出，测试以错误方式失败且未触及被测目标。修复：传入两年 dataset 路径（对照 :1980 的正确写法），使 SystemExit 发生在 `generate_archive` 断言处。

### B3：`test_gate_final_2023_delta_minus_5pp_boundary`（:1942）浮点精确断言永假

`compute_gate`（:1491-1492）分别计算 `da = dual_correct/40`、`ba = b1a_correct/40` 再相减：fixture 为 dual 20/40=0.5、b1a 22/40=0.55，`0.5 - 0.55 = -0.050000000000000044 ≠ -0.05`（IEEE754；注意若按整数差 `(20-22)/40` 才精确等于 -0.05，但实现不是这么算的）。计划自己的同类边界测试（:1411）用的是 `abs(...) < 0.001` 容差——两处标准不一，这处必挂。修复：改容差断言。

### B4（待实施时验证）：2023 finalize 的 enriched 文件疑似双重哈希

审核方报告：`_compute_dataset_hashes`（:2130-2150）经 schedule dataset_path 计入 enriched 文件，另有 `workspace_dirs` rglob 路径重复计入，导致 finalize 的预登记 SHA 恒不匹配、2023 归档永远拒绝，且测试 mock 掉 generate_archive/finalize 覆盖不到。我抽查了 `_compute_dataset_hashes`（按 "_enriched" 文件名分类去重），**未能在审核时限内独立确认该机制**——实施 Task 16 时必须先写真实（非 mock）的 finalize 集成测试验证此路径。

---

## 二、审核方误报（已复验澄清）

**"`--model-runner` 缺值"不是 bug，方向相反。** `run_benchmark.py:1529` 确认 `--model-runner` 是 `store_true` 标志位（不带值），计划 :850 `"--model-runner",` 的写法**正确**。真正的问题是 **:596**：argv `["--resume","--model-runner","pytest","--case-details-jsonl",...]` 中 `"pytest"` 会成为无法识别的位置参数，`rb.main()` 在断言前即 SystemExit(2)。修复：删除该 stray 值（或改为正确的 `--model` 传参）。此条降级为中优（测试代码 bug，首跑即现形）。

---

## 三、中优先级（6 项）

1. **Task 14 只有 prose**（:1564-1571）：17 个任务中唯一无测试代码、无实现代码的（writing-plans 标准的计划失败项）；`generate_report`（:1551 附近）同样只有一行内容清单、无实现无测试。两处必须补全。
2. **自审清单映射错误**：P0-5（ROLLBACK 归档保留 + BLOCKED 拒绝）证据全部在 Task 16（generate_archive 拒绝 BLOCKED_INCOMPLETE、test_archive_preserves_rollback_verdict、run_id 含 stage），清单却指向 Task 17；§7.3/§7.4 的执行链映射同样不精确（实际在 Task 17）。
3. **跨任务引用方向**：Task 10 注释"复用 Task 17 的 `_build_schedule`"方向反了（定义在 Task 10 :677，Task 17 是使用方）；`_load_events` 在 Task 11（:911/:938）使用、Task 16（:2180）才定义，无说明。
4. **P0-x 标签跨任务漂移**：P0-1 在 5 个 Task 各指不同事项；Task 15 出现清单中不存在的 P0-6（:1783/:1842/:1884）。审核可追溯性差，建议统一编号或改为按 Task 局部编号。
5. **小一致性**：`FROZEN_DATE` 重复定义（:659/:2091）；`DEV_REUSE_HARD_CAP` 与 `GLOBAL_HARD_CAP` 同为 1060 重复；`_process_slice`（:958）定义后无人调用；Task 13 :1450 模块内自导入 `parse_detail_identity`；`_build_schedule` 给 b1a slice 也写 `"profile":"baziqa_xjz_dual"`（:721，未消费但与 cmd 矛盾）。
6. **Task 4 目标文件**：`prompt_fingerprint` 在 `benchmark/runners/profiles.py:180`（不是 run_benchmark.py，run_benchmark.py:202 只是导入使用）——改动别找错文件。

---

## 四、已核验通过项

- **预算算术**：60 切片（2 年 × 3 repeats × 2 臂 × 5 组，8 题/片）；dual 30×24=720、b1a_prime 30×8=240，合计 960、global cap 1060——与 spec §8 一致；2023 终验 480/530 与 spec §7.4/§8 一致。（计划 :20"（240+720）"写法含糊，建议写明 dual 720 + b1a 240，但代码/测试自洽。）
- **代码库符号**：`render_reasoned_context(ziwei_arm="none"/"only")`（chart_context.py:368，未知识别值 raise）；`run_multi_turn_benchmark`（:1331）与 method 委托（:780-781）；`_attempt_with_ledger`（:370，含重试/record_call_meta/hard_cap）；`build_benchmark_prompt` 路由（:426-454，dual 插入点存在）；`ATTEMPT_STAGES` 含 bazi/ziwei/judge（:47）；profiles 注册表与 visibility 矩阵结构吻合；`_dual_write_detail` 依赖 `_append_jsonl`→`enrich_row` 补 attempt_key/terminal_state 的契约**真实存在**（run_benchmark.py:594-606 与 :263-277，审核方担心的"悬空"不成立）。
- **6B1 产物**：merged_details 720 行、attempt_key[2] 臂名 ∈ {b1a_prime,b1b,b1c}，B1-c advisory 冻结路径唯一存在。
- **2023 状态**：enriched 缺失属预期（密封设计，Task 15 enrichment 是真实依赖，排期不可跳过）；`OutputDirLock` 在 scripts/phase6_6b1d_orchestrator.py:92；BudgetLedger6B2 确为新建参数化（两处旧账本均硬编码）。
- **自审清单 24 项中 22 项**在正文有实证；核心数值（60 片/24/8/10/26/960/1060/480/530）跨任务一致。

---

## 五、判定

| 类别 | 数量 | 内容 |
|---|---|---|
| 确认阻断 | 3 | B1 60.8% 无源（实测 57.9%）；B2 测试缺 dataset_paths；B3 浮点精确断言 |
| 待验证疑似阻断 | 1 | B4 2023 finalize 双重哈希（实施 Task 16 时先写真实集成测试） |
| 误报澄清 | 1 | "--model-runner 缺值"系 store_true 误读；真 bug 在 :596 stray positional（降中优） |
| 中优 | 6 | Task 14/generate_report 缺代码；清单映射；引用方向；P0 编号漂移；重复常量；Task 4 目标文件 |
| 通过 | 预算/符号/产物/2023 状态/22 项清单落实 | — |

修复 B1-B3 与 :596 后即可放行实施；B4 在实施 Task 16 时以真实集成测试先行验证；中优项建议同轮修订。


---

# 第二轮审核（外部 v10 审核 + Kimi 复核，2026-07-20）

> 第一轮见上文（3 确认阻断 + 1 待验证 + 6 中优）。本论为外部审核对修订后 v10（2622 行）的结论，全部 6 个 P0 经 Kimi 逐点源码复核**确认成立**。
> **合并结论：NEEDS_REVISION 维持——6 个 P0 必修 + 4 项遗留；修完后建议补一轮静态测试夹具核验再放行。**

## 第二轮 P0（Kimi 复核记录）

### P0-1：B1-a′ 门禁读取不存在的 `dual_stage` 字段（:905）——成立

`mains = [r for r in rows if r.get("dual_stage") == "main"]`。真实 B1-a′（b1a_prime 臂，direct_choice 路径）detail 行由 `enrich_row` 契约产出：有 `attempt_key`（[3]=stage）与 `terminal_state`，**无顶层 `dual_stage`**（该字段是 dual 管线专有）。过滤结果恒 0 → 每个正常 B1-a′ slice 返回 `B1A_MAIN count=0` 全灭。计划自有的 fixture 手写了 `dual_stage` 掩盖了真实行形。修复：统一从 `attempt_key[3]` 解析 stage（同时修正 fixture 去掉手写 dual_stage）。

### P0-2：B1-a′ 合法终态集合被缩小（:909）——成立

只允许 `("parsed", "call_failed")`；冻结契约 `TERMINAL_STATES = ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed")`（run_benchmark.py:48），`invalid`（parser 失败）是合法终态。一条合法 invalid 即整 slice 无法完成，且与 Task 14 容忍少量 parser invalid 的设定自相矛盾。

### P0-3：完成态 resume 只比 SHA、不比当前 manifest（:951-969）——成立

现状只验证 runner manifest 文件存在 + SHA 与 status 记录一致 + events 存在 + actual_attempts 一致——只能证明"旧文件没被改"，不能证明"旧配置 == 当前代码/prompt/数据/参数"。代码漂移后旧 manifest 与旧 SHA 仍匹配，会被错误跳过。修复：复用 runner 的 `build_resume_manifest()`/`check_resume_manifest()`（6A1 已建立的逐字段比对 + fail-closed 机制）或 6B1D 的 manifest 校验。

### P0-4：Task 9 resume 测试三处不可执行（:582-603）——成立（三处全部核实）

- detail 为 `d.jsonl` → runner 找 `d.manifest.json`，测试却创建 `details.manifest.json`（文件名不匹配）；
- manifest 内容 `{"completed":True,"slice_id":"s1","resume_field":"v"}` 缺少全部 ~20 个 RESUME_MANIFEST_FIELDS，`check_resume_manifest` 必拒；
- `dataset.jsonl` 仅 `{"case_id":"Q1"}`，过不了 visibility gate。
修复：用真实 `build_resume_manifest()` 产物写 manifest（正确文件名）+ 合法 case，或显式 monkeypatch visibility 过滤。

### P0-5：crash-resume 的 `record_slice_completed` 未传臂上下文（:968）——成立

`ledger.record_slice_completed(slice_id, actual)` 未传 arm。若进程在写 slice_status.json 后、写 ledger 前崩溃，dual slice 恢复时按默认（B1-a′ 8-10）范围校验，正常 16-26 次调用将被拒。修复：完成记录携带臂/预期范围（实现时核对 BudgetLedger6B2.record_slice_completed 的校验默认值）。

### P0-6：Task 14 仍只有 prose（:1622-1629）——成立

4 个一行式 step，无测试代码、无实现、无 pytest 命令与预期。smoke 是真实实验启动门禁，按 writing-plans 标准属计划失败项，升级为 P0：必须补成完整 TDD 任务（smoke gate 实现 + 集成测试实现 + 命令与预期）。

## 遗留项（复核确认仍在）

- `JUDGE_DISAGREEMENT_RATE = 0.608` 无出处（:675；实测 139/240=57.9%，见第一轮 B1）；最坏情况预算 960/1060 不变。
- `:2000` 仍为 `assert gate["delta_2023"]==-0.05` 精确比较（应为 `pytest.approx(-0.05)`；第一轮 B3 同款）。
- `generate_report` 仍仅一行内容清单，无接口/实现/测试。
- `_load_events`（:965 使用）与 `_sha256_file`（:957 使用）均到 Task 16 才定义，违反"每个任务独立可绿"。

## 已确认修复（外部审核认定，Kimi 抽查）

- stray `--model-runner pytest` 已删除（新 argv :598-599 无位置参数）✓
- `test_archive_refuses_incomplete_schedule` 已补 dataset_paths ✓
- B1-a′ 命令已补 `--ziwei-arm none`/`--output-dir`/`--as-of-date`/schema ✓（外部认定）
- runner manifest 不再被 slice_status.json 覆盖 ✓（外部认定）
- 2023 归档显式传 raw dataset path ✓（外部认定）

## 放行条件（合并两轮）

1. 修完第二轮 6 个 P0（dual_stage→attempt_key[3]、终态全集、当前 manifest 重构比对、Task 9 测试三处、record_slice_completed 带臂、Task 14 完整 TDD 化）；
2. 清理遗留 4 项（60.8%→实测或标注、float→approx、generate_report 补全、`_load_events`/`_sha256_file` 定义前置或就地定义）；
3. 补一轮静态测试夹具核验（所有 fixture 行形与真实 detail 行契约逐字段比对）；
4. 复核文件当前处于活跃并行修订中（2512→2622 行），定稿后复核行号。


---

# v11 修订完成记录（Kimi 执行，2026-07-20）

第二轮 6 个 P0 + 4 遗留项已全部落入 `2026-08-02-phase6-6b2-dual-system-judge.md`（v10 → v11，2622 → 2936 行）：

| # | 修订 | 落点 |
|---|---|---|
| P0-1 | 门禁 stage 统一从 `attempt_key[3]` 解析（含 `_stage()` 助手） | 完整性检查 b1a/dual/judge 过滤全部改写 |
| P0-2 | B1-a′ 合法终态恢复全集（5 态，对齐 TERMINAL_STATES） | 完整性检查 B1A_TERMINAL 分支 |
| P0-3 | 完成态 resume 改为 `build_resume_manifest` 重建当前配置 + 逐字段比对（fail-closed），新增 `_slice_runner_args` 助手 | slice resume 路径 |
| P0-4 | Task 9 测试三处全修：manifest 文件名 `d.manifest.json`、真实 `build_resume_manifest` 产物、visibility 显式 monkeypatch、argv 补 `--arm dual`；fixture 移除手写 dual_stage | Task 9 resume 测试 |
| P0-5 | `record_slice_completed(slice_id, actual, arm=slice_info["arm"])` | slice resume 路径 |
| P0-6 | Task 14 补全为完整 TDD（6 个 smoke 测试 + 1 个集成测试 + `determine_smoke_state`/`verify_smoke_completed` 完整实现 + pytest 命令与预期 + commit 步骤） | Task 14 全节替换 |
| 遗留 1 | `JUDGE_DISAGREEMENT_RATE` 0.608（无源）→ **0.579**（实测 139/240，注明仅作报告参照、最坏预算 960/1060 不变） | 常量 + generate_report + 自审清单 |
| 遗留 2 | `assert gate["delta_2023"]==-0.05` → `pytest.approx(-0.05)` | Task 13 测试 |
| 遗留 3 | `generate_report` 补接口/实现（准确率 by_arm、judge 触发率、parser rate、预算对账、B1-c advisory 标注）+ `TestGenerateReport` 字段与产物文件测试 | Task 13 报告节 |
| 遗留 4 | `_sha256_file`/`_load_events`/`_slice_runner_args` 定义前移至 Task 11 helpers；Task 16 同模块重复定义改为引用注释（Task 15 的在另一模块 sealed_workflow.py，属合法） | Task 11/16 |
| 修订中新增发现 | `compute_gate` 的 dual 聚合同样用 `r.get("dual_stage")`（第二轮未列出）——已一并无差别修复为 attempt_key[3] | Task 13 compute_gate |
| 修订中新增发现 | Task 14 集成测试初稿误用 8 题切片级完整性门禁于 2 case（会恒报 CASE_COUNT）——已改为 judge 触发/答案断言并注明边界 | Task 14 测试 |

**残留说明**：各 Task 测试 fixture 中手写 `dual_stage` 的行未逐一删除——门禁与聚合均已改为 attempt_key[3] 后，这些字段成为无害的诊断附列（与"顶层 dual_stage 仅诊断附列"的注释一致）；实施时如确认 `_dual_write_detail` 不写顶层 dual_stage，可顺手清理，不阻断。

建议：放行前由外部审核对 v11 做一轮静态夹具核验（所有 fixture 行形 vs 真实 detail 契约），重点核对 Task 9 新测试与 Task 14 新代码的可执行性。


---

# 第三轮审核复核 + v12 修订记录（Kimi，2026-07-20）

## 第三轮审核（外部）4 P0 复核结论：全部成立

| P0 | Kimi 复核证据 |
|---|---|
| #1 `build_resume_manifest(args, None)` 不可运行 + `_slice_runner_args` 字段错位 | `run_benchmark.py:203-221` 确认函数直接读 `profile.profile_id`/`chart_schema_version`（None → AttributeError）、`args.case_ids_file`（None guard）；schedule slice 字段实为 `repeat`（非 repeat_idx）、无 provider/model/hard_cap、全 arm 写死 dual profile/method、缺 case_ids_file |
| #2 Smoke 测试/实现不可执行 | `self._write_smoke` ×4（模块函数误作实例方法）；`_mk_case` 全文未定义；fake 返回裸 "A" 而 Task 6 全部 fixture 用 `最终答案：X`（chart_context.py:337 parser）；`result["case_details"]` 为 case 级汇总非 stage 明细；6+1=7 却写 8 passed；smoke 未接入任何执行链 |
| #3 `generate_report` 与账本接口不匹配 + 聚合口径错误 | `BudgetLedger6B2.total_attempted` 为 int 属性（:814 `self.total_attempted = 0`），`total_attempted()` → TypeError；测试伪造同名 lambda 掩盖；`_accuracy_by_arm` 按 stage 行计数（dual 每题 2-3 行）非 case 级最终准确率 |
| #4 缺 dev/reuse 可执行入口 | 全文无 `main()`/`run_dev()`/`run_reuse()`；Task 17 标题含复用验证但只实现 `run_2023_final`；无 CLI 可启动 2024/2025 dev 或 2021/2022 reuse |

中优复核：Task 9 重复测试名（:585/:588 相邻两 def，旧版残头未清）成立；Task 16 `_sha256_file` 同模块二次定义（:2471）成立；完成态应直接调 `check_resume_manifest`（:226 起，含 `<MISSING>` 语义）成立；dual 分支终态校验缺失成立。

## v12 修订落点（全部完成，2937 → 3130+ 行）

1. **manifest 链**：`_slice_runner_args(slice_info, provider, model)` 与 `_build_runner_cmd` 冻结配置同源（per-arm profile/method/ziwei_arm、repeat→repeat_idx、case_ids_file、per-arm hard_cap、FROZEN_*）；resume 完成态改 `resolve_profile` 真实对象 + `check_resume_manifest` 官方比对；schedule slice dict 改 per-arm profile/method + 补 `case_ids_file`；Task 9 测试改真实 profile + `case_ids_file=None` 对齐 argv。
2. **Task 14**：`self._write_smoke` ×4 → 模块调用；新增 `_mk_case`（含字段形状 hedge）；fake 输出 `分析：…\n最终答案：X` reasoned 格式；stage 明细改读落盘 `detail.jsonl`；预期 8→7 passed。
3. **报告**：`ledger.total_attempted`（属性）；`_accuracy_final` 按 compute_gate 同口径（共识→bazi、分歧→judge、双侧 unresolved→不计对）计算 dual 最终准确率；测试 fixture 重写（c0 共识对/c1 judge 错 → 0.5 精确可断）。
4. **入口**：新增 Task 17b——`run_dev`/`run_reuse`/`main` CLI（`--stage dev|reuse|final-2023`），dev 链含 smoke 前置（blocked_corrupt 即拒绝）、schedule→ledger→slice→merge→gate→report 全串；4 条执行链测试（顺序/spy/阻塞/reuse stage/CLI 拒绝）。
5. **中优**：删除 Task 9 重复测试名（:585 残头）；Task 16 `_sha256_file` 同模块重复定义改引用注释；完整性门禁 dual 分支补逐行 5 态终态校验。

**残留风险（如实声明）**：v12 新增的 `_slice_runner_args`/`_accuracy_final`/Task 17b 执行链尚未经外部静态核验；`_run_smoke_slice`/`_smoke_case_ids` 为计划内小型辅助，实现时与 Task 10 group 划分同源对齐。建议下一轮审核重点：manifest 字段与 `_build_runner_cmd` argv 的逐字段同源性、Task 17b 测试的 spy 断言可执行性。


---

# 第四轮审核复核 + v13 修订记录（Kimi，2026-07-20）

## 第四轮审核（外部）5 P0 复核结论：全部成立

| P0 | Kimi 复核证据 |
|---|---|
| #1 阶段链未闭合 | `run_reuse` 无 `check_stage_gate`（函数存在于 :2120 且 run_2023_final :2889 有同款用法）；dev/reuse 不写 gate 准入文件；未调 `generate_archive`；`main()` 用 `(output_dir, provider, model, resume=)` 调 `run_2023_final(provider, model, gate_root, archive_root)`（:2882）→ TypeError |
| #2 smoke helper 占位 + 约束冲突 | `_run_smoke_slice`/`_smoke_case_ids` 仅一句 hedge；2 题 smoke 撞 8 题完整性门禁、dual 16 次账本下限、预算不入账——成立 |
| #3 smoke 状态机/parser 门禁 | 旧逻辑"任意 ziwei 行即 completed"会把崩溃现场误判完成；call_failed 计入 parser 成功——成立 |
| #4 报告聚合缺 year | `_accuracy_final` 用 (case_id, repeat)——2024/2025 复用 Q1-Q40 会跨年覆盖（240 格压 120）；judge 触发率分母同样——成立 |
| #5 v12 测试不可执行 | dev 链 mock 的 schedule 缺 `global_hard_cap`（KeyError）；`TestDualIntegration` 未 init `_PHASE6_CTX`（fake_call 读 `rb._PHASE6_CTX.attempt_stage` → AttributeError）——成立 |

审核方"manifest 字段与 runner 20 字段契约基本一致"的认定经复核属实（:203-221 字段逐一比对）。

## v13 修订落点（全部完成）

1. **执行链闭合**：`run_reuse` 先 `check_stage_gate("reuse")`（读 gates/dev_gate.json 要求 PROMOTE_CANDIDATE）；dev/reuse 原子写 `{stage}_gate.json`（tmp+replace）；链尾 `generate_archive()`；`main()` final-2023 调用对齐真实签名。
2. **smoke 真实实现**：`_smoke_case_ids`（2024 前 2 题确定性）+ `_run_smoke_slice` 完整代码——独立小账本（scheduled 8 / cap 10 / slice_min=1，预算可审计）、`_run_slice` 加 `integrity="smoke"` 分支（smoke 口径：每题 bazi+ziwei 恰 1 行、judge ∈{0,1}、5 态全集，绕开 8 题门禁与 16 次下限）。
3. **smoke 状态机/门禁**：`determine_smoke_state` 加 `expected_case_ids`，completed 需每题 bazi+ziwei 齐全（崩溃现场→resume）；`verify_smoke_completed` 任何 call_failed 即拒且 parser rate 分母剔除 call_failed。新增 2 条测试（partial→resume、call_failed→blocked），smoke 共 8 条。
4. **聚合键含 year**：`_accuracy_final` 与 judge 触发率分母均以 (year, repeat, case_id) 聚合（attempt_key[0] 数据集名提取年份）。
5. **测试修正**：dev 链 mock 补 `global_hard_cap` + archive/gate 文件/准入 mock；`TestDualIntegration` 先 `init_phase6_context`（真实 Phase6Context 构造，run_benchmark.py:249-262 签名核验过）；新增 `TestManifestHomology`（argv 解析 namespace 与 `_slice_runner_args` 两路 manifest 全等断言）。

**自审补充**：Task 14 预期 9 passed（smoke 8 + 集成 1）；Task 17b 预期 6 passed（链 5 + 同源性 1）；`_ns_from_argv` 测试内解析器已注明类型还原口径。

**残留风险（如实声明）**：`integrity="smoke"` 分支需落到 Task 11 的 `_run_slice` 实现（计划已登记签名变更）；`tmp_path_global` 全局传递在实施时可改实例属性。建议下一轮审核聚焦：smoke 分支与 `_run_slice` 主流程的交互、gate 准入文件与 `check_stage_gate` 的读取契约是否字段级吻合。


---

# 第五轮审核复核 + v14 修订记录（Kimi，2026-07-20）

## 第五轮审核（外部）4 P0 复核结论：全部成立

| P0 | Kimi 复核证据 |
|---|---|
| #1 smoke 参数未落入 Task 11 | Task 11 `_run_slice` 签名确无 `integrity` 参数（:1025），Task 17b 调用 `integrity="smoke"` 必 TypeError；四层子问题（26 预占 vs cap 10、record 16-26 范围、8 题门禁、details.manifest.json vs detail.manifest.json）逐一比对成立；"配套修改一段描述"违反无占位要求 |
| #2 gate 发布顺序 + run 隔离 | v13 链确为 gate 文件先于 report/archive；`--run-id` 解析后全文未使用（grep 证实）；共用 output_dir 导致 ledger 共享问题成立 |
| #3 新测试确定失败 | `_build_runner_cmd` 写 case_ids.json 前无 mkdir（:847 区域，FileNotFoundError）；`_ns_from_argv` 缺 sample_temperature/n_samples 默认（build_resume_manifest 直读 :213-215 → AttributeError）；reuse mock `setdefault(...) or {...}` 返回字符串——三处全部成立 |
| #4 崩溃 slice 无法 resume | is_resume 仅在 slice_status.json 存在时设置（:1045-1074）；崩溃窗口（runner 已产出、status 未写）下 runner fail-closed 拒绝——成立 |

中优复核：SMOKE_SCHEDULED=8 高估（最坏 2×3=6）成立；smoke 账本未并入审计成立；`_PHASE6_CTX` 全局污染成立；`generate_archive` 缺 dataset_paths 成立（run_2023_final :2977 的调用证明该参数存在）。

## v14 修订落点（全部完成）

1. **Task 11 `_run_slice` 完整重写**（非描述登记）：`integrity="slice"|"smoke"` 入签名；smoke 分支——SMOKE_HARD_CAP 预占、manifest 按 detail_path 推导（detail.jsonl→detail.manifest.json）、`_smoke_integrity` 完整实现（每题 bazi+ziwei 恰 1 行/judge∈{0,1}/5 态全集/case 数动态）、record 走构造范围（arm="smoke"）；**partial resume 三态**：status 缺失但 runner 三件套任一存在 → 自动 resume。
2. **receipt 顺序与指纹**：compute_gate → report → archive 自验 → 原子发布 receipt（verdict/stage/archive_dir/audit_index_sha256/provider/model/code_fingerprint/dataset_sha256/smoke_attempted）；run 隔离 `exp_root/{gates,archive,runs/<run_id>}`，`--run-id` 真正参与路径。
3. **测试修复**：homology 测试先建 slice 目录；`_ns_from_argv` 补 sample_temperature=0.4/n_samples=1 默认；reuse mock 改显式 dict 返回；`_build_runner_cmd` 写文件前 makedirs。
4. **中优**：SMOKE_SCHEDULED 8→6；receipt 增 `smoke_attempted`（smoke 账本并入审计）；TestDualIntegration finally 复位 ctx；`generate_archive` 补 `dataset_paths`。

**残留风险（如实声明）**：`check_stage_gate` 现有实现只验 verdict（:2120），receipt 新指纹字段的校验强化落在 Task 15/17 的该函数上——下一轮审核应核对其字段级契约；`BudgetLedger6B2.record_slice_completed` 对 arm="smoke" 的构造范围回退需在实施时用 Task 11 测试锁定。


---

# 第六轮审核复核 + v15 修订记录（Kimi，2026-07-20）

## 第六轮审核（外部）5 P0 复核结论：全部成立

| P0 | Kimi 复核证据 |
|---|---|
| #1 smoke 预算未贯通 runner | `_build_runner_cmd` 按 arm=="dual" 给 smoke 传 `--hard-cap 26 --max-cases 8`；`_slice_runner_args` manifest 记 26——成立 |
| #2 `record_slice_completed(arm="smoke")` 必败 | :857-869 实为 `8/10 if b1a_prime else 16/26`，smoke 落 else；`slice_min/slice_max` 从未使用——成立 |
| #3 receipt 用未定义 `_git_head()` | 全文 grep 无定义（计划中是指纹函数 `_compute_experiment_code_fingerprint` :2625）；smoke 账本默认 1060 加载会被一致性拒绝——成立 |
| #4 receipt 只写不验 | `check_stage_gate`（:2213）确只读 verdict；`audit_index_sha256=None` 继续发布属 fail-open——成立 |
| #5 smoke judge 未按分歧基数 | 旧 `_smoke_integrity` 只查 judge≤1，缺共识禁 judge/分歧必 judge/未知 stage 拒绝——成立 |

## v15 修订落点（全部完成）

1. **预算单源化**：slice 自带冻结 `hard_cap`/`max_cases`/`scheduled_calls`（smoke=10/2/6、b1a=10/8/8、dual=26/8/24），`_build_runner_cmd`/`_slice_runner_args`/外层预占全部只读 slice 字段；partial resume 按 `hard_cap − 已有 attempts` 预占剩余量（中优）。
2. **账本**：`record_slice_completed` 改 `ARM_RANGES.get(arm, (self.slice_min, self.slice_max))`——b1a/dual 原范围不变，smoke 走构造范围；边界测试（1/10 过、0/11 拒、幂等）列入 Task 11。
3. **receipt**：`_git_head()` → `_compute_experiment_code_fingerprint()` 且强制等于 audit_index 的 code_fingerprint；audit_index 缺失即拒绝发布；smoke 账本按原构造参数（10/1/10）加载。
4. **准入强化**：`check_stage_gate` 重写为 7 项字段级校验（必需字段/stage/archive+audit 存在/audit SHA/receipt×audit 交叉指纹/provider/model/当前代码指纹），`TestGateReceipt` 3 条真实最小 audit_index 测试（roundtrip/缺 audit 拒/stale provider 拒）。
5. **smoke 完整性**：judge 按分歧基数（共识/双 unresolved→0、分歧/单侧→恰 1）、未知 stage 拒绝。
6. **中优**：`SMOKE_SCHEDULED` 8→6 且说明同步；`TestDualIntegration` finally 复位 `_PHASE6_CTX(None)`；`generate_archive` 补 `dataset_paths`；新增 `test_smoke_homology`（cmd 与 manifest 同为 10/2/6）；`_ns_from_argv` 提为模块级测试辅助并清理内联残留。

**残留风险（如实声明）**：`record_slice_completed` 的构造范围回退语义需在实施时与 BudgetLedger6B2 既有 `_load()` 一致性校验联合验证；archive 目录名是否已含 run_id（中优第 4 条）取决于 Task 16 `generate_archive` 的目录构造——v15 已在 receipt 记录 `run_id`，目录级隔离若 Task 16 未落实，实施时补 `run_id` 入归档目录名并更新 Task 16 测试。
