# Phase 6 6A1 严格 ≥3/5 投票同源配对基线（含 temp-0 锚定）实施计划 v10

> 状态：**v10（十轮审核修订，待最终放行）**
> 设计依据：`docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md` v6 §5（6A1 协议）、§2.1（报告口径：BaziQA macro-average by year + by_domain 为首类，trimmed mean 为准确率辅助）、§8（预算双列）、§10（顺序与阻塞规则）、§12（风险如实声明）。
> 审核记录：`docs/superpowers/plans/2026-07-20-phase6-6a1-strict-vote-review.md`（十轮合并）。v10 修复第九轮 1 阻断：
>   - **阻断**：`TestFreezeTemperatureMainCallSpy` 的 `write_report` stub 返回 `None`，但生产主流程随后 `summary.get("status") == "BLOCKED_INCOMPLETE"` 会抛 `AttributeError: 'NoneType' object has no attribute 'get'`，spy 断言无法执行；改为 `lambda *a, **k: {"status": "OK"}` 并锁定 `rc == 0`。
> 前置事实（已核验）：6A0 全部完成并收口（`8645f87`）；6A0 dev gate = **ROLLBACK**（Δ=−5.0pp），按设计 §10 回退规则，**6A1 全部臂上下文锁定 `legacy_v0`**；2021/2024 enriched 产物在位（`.tmp/phase6/enrich_manifest.json` entries，40/40）；评测设施（attempt key/resume manifest/重试账本/BudgetLedger/截断守卫）已在 6A0 落地并有真实运行验证。
> 纪律：每 Task TDD（先失败测试）；`git add` 只列精确路径；每任务提交前 4 组回归（`.tmp/g{1..4}.txt`，定义见执行纪律 #3）全绿；执行偏离逐条写入 commit 信息。

---

## 0. 设计 v6 §5 协议 → 本计划落点映射

| §5.2 协议条 | 落点 |
| --- | --- |
| 1. 每题同温度 T 采样 5 次，T 冻结 0.4 | runner `emit_samples` 模式（Task 2）；编排器采样臂切片（Task 3） |
| 2. 多样性试测（stage=`diversity_probe`，10 题，<60% → T=1.0，样本作废） | 编排器 probe 阶段 + `diversity_rate()`（**仅计 terminal_state=="parsed" 的 A/B/C/D**）+ `probe_rows_complete()`（不完整即 BLOCKED，Task 3） |
| 3. 锚定臂（stage=`anchor`，single@T=0，同时间窗） | `--attempt-stage anchor`（Task 2）+ AB/BA 交错调度（Task 3） |
| 4. `strict_majority()` ≥3 票当选、unresolved 计错、invalid 占 attempt、分母恒 5、禁止破平局 | `benchmark/runners/self_consistency.py::strict_majority`（Task 1，**不复用 `majority_vote`**） |
| 5. 同源配对：single@T=第 1 次采样；vote5=同 5 次聚合；single@0 独立同期；manifest 记调用顺序与原始响应路径 | 编排器聚合纯函数（Task 3）；detail 行 `raw_response_path`（已有）+ slice manifest（已有 + **`attempt_stage` 字段，决策 7 反转**） |
| 6. repeats 聚合：vote5 仅 repeat 内聚合；报每 repeat、三轮均值、逐题明细；禁止 15 次再投票 | `aggregate_metrics()` 按 (case_id, repeat_idx) 分组聚合 + 逐题 `case_records`（Task 3，测试锁定不跨 repeat） |
| 7. 首类指标：准确率、unresolved 率、配对四格表 ×2、成本比、by_domain、trimmed mean 准确率附列（设计 §2.1） | `write_report()`（Task 3）：`cost_metrics()`（prompt 字符 × 调用数 × repeats 代理）+ `by_domain_metrics()` + `acc_trimmed_mean`（三臂 repeat 准确率 `trimmed_mean`，描述性不入 gate）+ `case_details.jsonl` |
| enrichment entry 实体校验 | `run_phase6_6a1_ablation.py::validate_enrichment_entry(entry, enriched_path, expected_year, expected_as_of_date)`（v7 高优 4 + v8 阻断/高优 1：current + dev 共用，校验 year/output_path/SHA/**实际 JSONL 行数=row_count=40**/**as_of_date 绑定顶层**） |
| 审计复算可独立验证 summary | `build_phase6_audit_index.py::recompute_vote_accuracy(detail_rows, expected_case_ids, repeats=3)`（题级投票复算 + `_audit_validate_rows` 独立完整性 [v5 高优 6：拒重复逻辑键+精确行数+stage 验证] + `--mode vote` 默认检查 summary + 审计索引写 `summary_check` 字段 [v5 高优 5]，Task 3） |

§5.3 gate → Task 3 `gate_verdict()` / `recheck_verdict()` 纯函数 + Task 4/5 真实执行；**年份封死：dev 仅 2024、复核仅 2021、2022/2023 一律 exit 2（审核阻断 3）**；§8 预算 → 下文预算表 + `build_schedule` cap 和断言。

## 1. 计划期决策记录（冻结；设计未规定处的补白，均不发明、不放宽）

1. **上下文基线**：全部臂 `--chart-schema-version legacy_v0`（6A0 ROLLBACK 结论；设计 §10「增强臂失败回退上一稳定基线」）。
2. **臂/stage 命名**（attempt key 无温度字段——probe 两轮温度不同必须靠 arm 区分，否则键碰撞）：
   - 采样臂：`arm=vote5_samples`，`attempt_stage=main`，`sample_idx∈0..4`，`repeat_idx∈0..2`；
   - 锚定臂：`arm=anchor_single0`，`attempt_stage=anchor`，`sample_idx=0`；
   - 试测：`arm=probe_r1`（T=0.4）/ `arm=probe_r2`（T=1.0），`attempt_stage=diversity_probe`，`repeat_idx=-1`（与 smoke 同例，不进主指标）。
3. **single@T = `sample_idx=0`**：emit 循环按 sample_idx 升序串行调用，调用顺序即样本顺序，「同组 5 次的第 1 次」= sample_idx 0 行。
4. **T 冻结链**（设计 §5.2.2 只规定一次切换；第三次温度属发明，禁止）：
   - probe_r1（T=0.4）多样性 ≥ 60% → 冻结 T=0.4，probe_r2 不运行（0 调用）；
   - < 60% → 运行 probe_r2（T=1.0）；≥ 60% → 冻结 T=1.0；
   - probe_r2 仍 < 60% → **冻结 T=1.0 继续**，并在报告与 stage manifest 记录「低多样性（T=1.0 仍 <60%）」为预注册限制（设计 §12.1 已预见低多样性抬高 unresolved 率，unresolved 率首类指标兜底）。
5. **锚定臂禁止复用 6A0 `ctx_legacy` 旧 run**：设计 §5.2.3 要求同时间窗；跨时段比较只能 advisory（§12.5）。6A0 旧数据一字不读。
6. **聚合全部离线**：runner 只负责逐样本调用/记账/明细（`emit_samples`），不做任何投票；`strict_majority` 与 Δ 计算在编排器纯函数，测试全覆盖。
7. **`attempt_stage` 加入 `RESUME_MANIFEST_FIELDS`（v2 反转，第二轮审核高优 6）**：`--attempt-stage` 是调用者可控的结果定义参数；runner API 不强制 arm-stage 映射，同目录同 arm 先 main 后 anchor 续跑可过旧校验并混合 stage。加入字段后：stage 变更 resume 被拒（SystemExit 2）；旧 manifest 缺字段 fail-closed——合理且必要。
8. **probe 选题**：`split_ab_ba(case_ids, seed=20260717)` 的 `group_a[:10]`（复用 6A0 同一种子与函数，确定性、预注册）。
9. **审计索引工具扩展**：`scripts/build_phase6_audit_index.py` 增加 `--arms a,b`（默认原值不变）与 **`--mode vote`**：6A1 归档用 `recompute_vote_accuracy()` 题级投票复算（审核阻断 1），旧 `recompute_accuracy()` 保留服务单样本臂。
10. **emit 行字段集**：与 6A0 detail 行同构 + `sample_idx`/`n_samples`/`aggregate="emit_samples"`；每样本独立 `correct`（样本级诊断），vote5/single@T 的 case 级 correct 由编排器派生，不回写 runner。
11. **diversity 仅计合法选项（审核阻断 4）**：`diversity_rate()` 只统计 `terminal_state=="parsed"` 且答案 ∈ {A,B,C,D}；invalid/None/call_failed 不算"第二个选项"。probe 数据必须先过 `probe_rows_complete()`（恰好 10 题 × 每题 {0..4} 唯一 sample_idx），不完整 → BLOCKED_INCOMPLETE，不得计算比例。
12. **完整性检查全量化（审核阻断 2）**：`strict_rows_complete(rows, expected_case_ids, repeats)`——精确唯一 attempt（`40×3×5=600` 采样 + `40×3=120` 锚定）、无重复 (case,repeat,sample_idx)、无额外 case/repeat/未知 arm、每个预期 key 存在且 terminal_state 合法。任一不过 → BLOCKED_INCOMPLETE，不产出 verdict。
13. **CLI 年份封死 + 温度自动读取（审核阻断 3）**：非 recheck 仅 `--year 2024`，recheck 仅 `--year 2021`，其余组合（含 2022/2023、2024+recheck、2021 非 recheck）一律 exit 2（设计 §5.3：2022 不参与 6A1、2023 密封）；校验先于任何数据读取。复核温度**禁止人工转录**：`--dev-run-id` 从 `docs/phase6/<dev_run_id>/` 归档自动读取并核验（verdict==PROMOTE_CANDIDATE、profile/schema/provider/model 一致、manifest SHA-256 记录）。
14. **报告首类指标补齐（审核高优 5）**：`write_report()` 必含 `cost_ratio_vote5_vs_single_t` / `cost_ratio_vote5_vs_anchor`（prompt 字符 × 调用数代理，如实标注"API 未返回 token usage"）、per-case trimmed mean（复用 `benchmark.reports.accuracy_stats.trimmed_mean`）、`case_details.jsonl`（每题每 repeat：5 票/vote5/single@T/anchor/expected/correct/unresolved）、manifest 含切片执行顺序、case 分组哈希、scheduled/attempted/hard_cap 对账。
15. **校验段集合扩展（第一轮审核 B1）**：`run_model_benchmark` 的 `aggregate not in {"majority"}` 改为 `{"majority", "emit_samples"}`，否则 emit 分支永远不可达。
16. **case_id 唯一性（审核高优 7c）**：`build_main_schedule()` 断言 40 个**唯一** case_id（数量与唯一性双重）。
17. **审计复算独立完整性（v3 阻断 1）**：`recompute_vote_accuracy(detail_rows, expected_case_ids, repeats=3)` 接收预期 case IDs，独立执行精确完整性检查（sample 恰好 `40×3×5=600` 行、anchor 恰好 `40×3=120` 行、attempt key 唯一、无缺题/额外题/额外 repeat、终态合法）；审计脚本从 dataset 读取 40 个唯一 case ID 传入。审计 CLI 新增 `--check-summary` 自动与归档 `summary.json` 的 Δ1/Δ2/准确率/unresolved 比对，不一致退出非零（不依赖人工检查）。
18. **diversity 全 invalid 保留分母（v3 阻断 2）**：`diversity_rate(rows, expected_probe_case_ids)` 从 `expected_probe_case_ids` 预初始化 `per_case` 集合（全 invalid 题保留在分母、视为"不具多样性"）；6 diverse + 4 all-invalid = 0.6 而非 1.0。`probe_rows_complete` 仍前置校验恰好 10 题 × 5 样本。
19. **manifest 对账含 probe（v3 阻断 3）**：`write_report()` 接收 `executed_schedule = [probe_r1, optional probe_r2, *main_schedule]`；manifest `budget_reconciliation` 分别记录 `probe_scheduled` / `main_scheduled` / `scheduled_total` / `attempted_total` / `registered_hard_cap`；`slice_order` 含 probe 切片。
20. **anchor sample_idx 限定 0（v3 中优 4）**：`strict_rows_complete` 对 anchor 行 `sample_idx != 0` 直接 `ValueError`；末尾断言 `seen_sample == expected_sample` 且 `seen_anchor == expected_anchor`（额外集合也拒绝，不只是检查缺失）。
21. **trimmed_mean 用于准确率 + by_domain（v3 中优 5，设计 §2.1）**：`aggregate_metrics` 对三臂 repeat 准确率列表调用 `benchmark.reports.accuracy_stats.trimmed_mean`，作为描述性附列 `acc_trimmed_mean`（不入 gate）；新增 `by_domain_metrics(rows, ...)` 输出每个 domain 的 vote5/single_t/anchor 准确率及 Δ1/Δ2（描述性报告）。成本 `arm_total_chars` 乘 `repeats`，键名改 `arm_total_chars_per_run`（原"单 repeat 理论字符数"语义不清）。
22. **case_id 早期校验（v3 中优 6）**：新增 `validate_case_ids(case_ids)` 纯函数（数量==40 且唯一）；`main()` 在任何 probe 调用前即调用，畸形 dataset 立即 exit 2，不浪费 API 费用。
23. **g4 回归定义修正（v3 中优 7）**：移除 `test_accuracy_stats.py` / `test_claude_api.py` 忽略（实测 13 passed，非预损坏，且前者覆盖本计划直接使用的 `trimmed_mean`）；`fastapi` 缺失的 4 个模块（test_api/test_clients_api/test_rate_limit/test_visualization_api）改为环境要求（执行前 `pip install fastapi` 或在完整 dev 环境跑），不再以"HEAD 预损坏"名义忽略。
24. **审计 summary 默认检查（v4 阻断 1）**：`--mode vote` 默认必须检查 `docs/phase6/<run_id>/summary.json`（不再是可选 `--check-summary`）；summary 缺失或不一致直接 exit 2；新增 `--skip-summary-check` 仅诊断用（正式命令禁止使用）。Task 4/5 正式命令移除 `--check-summary`（已默认）。
25. **probe 完整性绑定预期 case（v4 阻断 2）**：`probe_rows_complete(rows, expected_probe_case_ids)` 改签名，严格验证：实际 case 集合恰好等于预期集合、arm ∈ {probe_r1, probe_r2}、`attempt_stage=="diversity_probe"`、`repeat_idx==-1`、每题 sample_idx 恰好 {0,1,2,3,4}、无额外行。`diversity_rate` 遇预期外 case 直接 `ValueError`（去掉 `setdefault`，不再扩大分母）。
26. **审计完整性独立（v4 高优 3）**：审计脚本实现自己的最小验证函数 `_audit_validate_rows`（可共享常量，但**不导入**生产 `strict_rows_complete`/`aggregate_metrics`），审计与生产完整性解耦，审计能发现生产完整性缺陷。
27. **validate_case_ids 结构化错误（v4 高优 4）**：`main()` 中 `validate_case_ids` 包 `try/except ValueError`，输出 JSON 错误 + exit 2（不是 traceback + exit 1）；新增 CLI 测试验证畸形 case_id 时 runner 调用次数为 0。
28. **dev 归档验证 8 项（v4 高优 5）**：`load_dev_temperature` 增加：summary `status=="OK"` / `year==2024` / `recheck==false` / manifest `run_id==dev_run_id` / 温度 ∈ {0.4, 1.0} / `temperature_freeze` 与 `sample_temperature` 一致 / dataset SHA 与已批准 2024 enriched manifest 对应 / 审计索引存在且 summary 比对已通过。
29. **g4 改名 core regression（v4 高优 6）**：g4 不再称"全量"，改名"core regression"（保留 4 个 fastapi 缺失模块忽略但明确标注）；只有 `pip install fastapi` 建立完整环境跑通 `python -m pytest tests/ -q -m "not e2e"` 才称"全量"。
30. **as_of_date 字段（v4 建议）**：`VoteConfig` 加 `as_of_date` 字段（从 enriched manifest 读取，非运行当天）；manifest 写入 `as_of_date`；resume manifest 哈希校验包含该字段。
31. **probe attempt_stage 索引修正（v5 阻断 1）**：`probe_rows_complete` 的 `stages.add(ak[6])` 改为 `stages.add(ak[3])`（attempt key 定义 ak[3]=attempt_stage、ak[6]=case_id，原实现读 case_id 必失败）；签名改 `(rows, expected_probe_case_ids, expected_arm)`，要求所有行 `arm == expected_arm`（禁止同文件混合 probe_r1 与 probe_r2）。
32. **probe_row fixture（v5 阻断 2）**：新增专用 `probe_row(case_id, sample_idx, letter, arm="probe_r1")` fixture（stage=`diversity_probe`、repeat_idx=-1），旧 `srow()` 只支持 vote5_samples/anchor_single0；旧 probe 测试逐个改用 `probe_row()` 并传 `expected_arm`。
33. **as_of_date 读 enrich_manifest（v5 阻断 3）**：读取路径改 `.tmp/phase6/enrich_manifest.json`（真实结构 `entries[]` 按 year 保存 output_path/output_sha256/row_count/as_of_date + 顶层 as_of_date）；验证 output_path 指向当前 enriched、实际文件 SHA 等于 output_sha256、row_count==40、entry 与顶层 as_of_date 一致；缺失或不一致立即 exit 2（fail-closed）。
34. **approved_2024_dataset_sha 强制传入（v5 高优 4）**：`load_dev_temperature` 的 `approved_2024_dataset_sha` 参数不再可选（None 时跳过是漏洞）；main 强制从 enrich_manifest 读取 2024 entry 的 output_sha256 后传入。
35. **审计索引 summary_check 字段（v5 高优 5）**：审计索引写入 `{"mode":"vote", "summary_check":{"status":"PASS","summary_sha256":"...","recomputed":{...}}, "dataset_sha256":"...", "run_id":"...", "year":...}`；2021 复核前验证这些字段（不只检查 `audit_index.exists()`）。
36. **_audit_validate_rows 拒重复逻辑键（v5 高优 6）**：拒绝重复 `(case, repeat, sample_idx)` 逻辑键（不只拒完全相同 attempt key）+ 断言精确行数 sample==600 / anchor==120 + 验证 sample stage==main、anchor stage==anchor（原实现允许 601 行冒充 600 行）。
37. **审计 CLI 测试真实目录（v5 高优 7）**：审计 CLI 测试改用真实目录结构 `<root>/<arm>/runs/<run_id>/slice_*/detail.jsonl` + 显式传 `--root <tmp_path>`（原测试用 `<run_id>/detail.jsonl` 不能覆盖真实 collect_run）。
38. **current/dev entry 区分（v6 阻断 1）**：main 同时读取 `current_entry`（args.year）与 `dev_entry`（固定 2024）；`approved_2024_dataset_sha` 始终取 `dev_entry["output_sha256"]`（2021 recheck 时不再误用 2021 SHA）；manifest `dataset_sha256` 记录 current，`dev_dataset_sha256` 记录 dev（复核模式）。
39. **ARCHIVE_ROOT 常量（v6 阻断 2）**：新增 `ARCHIVE_ROOT = PROJECT_ROOT / "docs" / "phase6"`；审计 main 用 `ARCHIVE_ROOT / args.run_id` 定位 summary.json 与 audit_index.json；测试 monkeypatch `ARCHIVE_ROOT`（不是含糊的 `ARCHIVE_DIR`，后者未定义会导致 AttributeError）。
40. **enrichment 验证补全（v6 高优 3）**：`enriched.is_file()` 前置检查（不存在直接 exit 2，避免 sha256_file traceback）；`as_of_date` 非空检查（空字符串 exit 2）；`Path(entry["output_path"]).resolve() == enriched.resolve()` 路径比较（Windows 路径统一 resolve）。
41. **温度冻结显式写入（v6 高优 4）**：T 冻结后 `probe_info["sample_temperature"] = temperature` 显式写入；`load_dev_temperature` 校验 `temperature_freeze.sample_temperature` 必存且等于 `manifest.sample_temperature`（去掉条件跳过，不允许静默通过）。
42. **summary_sha256 绑定（v6 高优 5）**：`load_dev_temperature` 验证 `summary_check.summary_sha256 == sha256_file(summary.json)`（审计后修改 summary 会被发现）+ `summary_check.recomputed` 的 Δ1/Δ2 与当前 summary 一致。
43. **workspace clean 前置检查（v6 高优 6）**：`_collect_workspace_state()` 在任何 API 调用前调用，`clean=False` 即 exit 2（采集失败也 fail-closed）；允许 dirty 的诊断运行需显式 `--allow-dirty`（正式命令禁止）。
44. **as_of_date 入 resume manifest（v6 高优 7）**：runner 新增 `--as-of-date` 参数，`run_slice()` 传入；`as_of_date` 加入 `RESUME_MANIFEST_FIELDS`（与决策 7 同口径，as_of_date 变更 resume 被拒）；`build_resume_manifest` 写入 `as_of_date` 字段。
45. **ARCHIVE_ROOT monkeypatch 层级（v7 阻断 1）**：审计测试 monkeypatch `ARCHIVE_ROOT` 必须指向归档**父目录**（`tmp_path / "phase6_archive"`），run 目录由审计 main 用 `ARCHIVE_ROOT / args.run_id` 拼出；原 patch 成 run 目录会双重嵌套导致 summary.json 找不到。
46. **probe_info 闭环测试（v7 阻断 2）**：v6 已写入 `probe_info["sample_temperature"]`，v7 补"生成 manifest -> 重新加载温度"闭环测试（构造完整 probe 流程生成 manifest，再用 `load_dev_temperature` 读取，验证 `temperature_freeze.sample_temperature` 字段确实存在且等于 manifest `sample_temperature`，非手工构造 manifest）。
47. **as_of_date resume 三场景测试（v7 阻断 3）**：v6 已加字段，v7 补测试：相同日期允许 resume / 日期变化拒绝 resume（SystemExit 2）/ 旧 manifest 缺 as_of_date 字段拒绝 resume（fail-closed）。
48. **validate_enrichment_entry 抽取（v7 高优 4）**：抽取纯函数 `validate_enrichment_entry(entry, enriched_path, expected_year)`，对 `current_entry` 与 `dev_entry` 都执行实体校验（output_path 存在且 resolve 等于 enriched、实际文件 SHA==output_sha256、row_count==EXPECTED_CASES、as_of_date 非空、entry.year==expected_year）；开发年度相同时复用结果（不重复校验）。
49. **--allow-dirty 与 --yes 互斥（v7 高优 5）**：`parser.error("--allow-dirty cannot be combined with --yes")` 拒绝组合；`--allow-dirty` 模式只执行离线配置检查（workspace 状态采集 + offline gate），不允许进入任何模型调用路径（probe/main 均不执行）。
50. **row_count 实际行数校验（v8 阻断）**：`validate_enrichment_entry` 加实际 JSONL 行数统计（`sum(1 for line in text.splitlines() if line.strip())`），要求 `actual_rows == entry["row_count"] == EXPECTED_CASES`。原 fixture "39 行文件 + row_count=40" 会被此校验拒，改用"40 行但含重复 case_id"精确触发 `validate_case_ids`。
51. **expected_as_of_date 参数（v8 高优 1）**：`validate_enrichment_entry(entry, enriched_path, expected_year, expected_as_of_date)`，对 current/dev 都校验 `entry["as_of_date"] == expected_as_of_date`（顶层日期），防止不同日期的 2024 entry 被接受。
52. **freeze_temperature 纯函数（v8 高优 2）**：抽取 `freeze_temperature(probe_info, temperature) -> dict` 纯函数（返回新字典，含 `sample_temperature`），生产主流程与闭环测试都调用；若生产删除该调用，测试立即失败。
53. **--allow-dirty CLI 测试（v8 高优 3）**：三条测试锁定策略——`--allow-dirty --yes` 组合被拒（parser.error 退出）/ 仅 `--allow-dirty` 时 fake `run_vote` 调用 0 次 / workspace dirty 且无 `--allow-dirty` 在 offline gate 前 exit 2。
54. **dry-run 返回码（v9 阻断）**：`test_only_allow_dirty_zero_run_vote_calls` 断言从 `rc != 0` 改为 `rc == 0`（对齐主流程"缺 --yes 时 return 0"的 dry-run 语义，不引入新退出码）；关键不变量仍是 `calls == []`（未进模型调用路径）。
55. **freeze_temperature main 调用 spy（v9 中优）**：新增 `TestFreezeTemperatureMainCallSpy`，用 spy 包装 `vote.freeze_temperature` 驱动 main（stub `run_vote` 避免真实模型调用），断言主流程调用 `freeze_temperature` 1 次且参数正确（生产删除该调用测试立即失败）；`TestProbeInfoRoundTrip` 文档描述收缩为"纯函数 + manifest 组合测试"。
56. **spy 测试 write_report stub 返回字典（v10 阻断）**：`TestFreezeTemperatureMainCallSpy` 的 `write_report` stub 从 `lambda *a, **k: None` 改为 `lambda *a, **k: {"status": "OK"}`；生产 main 随后 `summary.get("status") == "BLOCKED_INCOMPLETE"` 需 dict 参与；同时锁定 `rc == 0`（主流程正常终止）。

## 2. 预算（设计 §8 双列；reserve = scheduled 10% 向上取整到 10）

### dev 2024：scheduled 820 / hard_cap 910

| 切片 | arm/stage | 调用数 scheduled | hard_cap |
| --- | --- | ---: | ---: |
| probe_r1（10 题 × 5，T=0.4） | probe_r1/diversity_probe | 50 | 55 |
| probe_r2（条件运行，T=1.0） | probe_r2/diversity_probe | 50 | 55 |
| 采样臂 ×3 repeats × 2 组（20 题 × 5） | vote5_samples/main | 100 × 6 = 600 | 110 × 6 = 660 |
| 锚定臂 ×3 repeats × 2 组（20 题 × 1） | anchor_single0/anchor | 20 × 6 = 120 | caps 和 = 140 |
| **合计** | | **820** | **910** |

锚定 6 切片 cap 分配 `(24, 23, 23, 23, 23, 24)`（和 140）；probe_r2 不运行时实际硬顶 855 ≤ 910（储备不用即不支出）。

### 2021 复核（仅 dev gate 判 PROMOTE_CANDIDATE 时触发）：scheduled 720 / hard_cap 800

| 切片 | 调用数 scheduled | hard_cap |
| --- | ---: | ---: |
| 采样臂 100 × 6 | 600 | 110 × 6 = 660 |
| 锚定臂 20 × 6 | 120 | caps 和 = 140（同上分配） |
| **合计** | **720** | **800** |

无 probe（T 由 `--dev-run-id` 从 dev 归档自动读取并核验，决策 13）。

### 调度顺序（同时间窗 + AB/BA）

```text
probe_r1 → [probe_r2 条件]
每 repeat r∈{0,1,2}：sample(r, group_a) → anchor(r, group_a) → anchor(r, group_b) → sample(r, group_b)
```

锚定臂与同组采样臂背靠背（A 组采样先行、B 组锚定先行，镜像平衡顺序效应）。

---

## Task 1：`strict_majority()` 严格投票纯函数

**文件**：`benchmark/runners/self_consistency.py`（追加，不动 `majority_vote`/`sample_answers`）；`tests/test_strict_vote.py`（新增）。

注：`Sequence`/`Optional` 导入已存在于 `self_consistency.py:3`（两轮审核均确认），无需新增导入。

- [ ] **Step 1：写失败测试 `tests/test_strict_vote.py`（完整代码）**

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.self_consistency import strict_majority


class TestStrictMajority:
    """设计 §5.2.4：≥3 票当选；无 3 票 → None（unresolved 计错）；
    None/invalid 票留在分母（len(votes) 恒 5）；禁止任何形式破平局。"""

    def test_three_of_five_wins(self):
        assert strict_majority(["A", "A", "A", "B", "C"]) == "A"      # 3/1/1

    def test_two_two_one_unresolved(self):
        assert strict_majority(["A", "A", "B", "B", "C"]) is None     # 2/2/1 无破平局

    def test_two_one_one_one_unresolved(self):
        assert strict_majority(["A", "A", "B", "C", "D"]) is None     # 2/1/1/1 不取相对多数

    def test_none_votes_stay_in_denominator(self):
        # 3 有效 A + 2 invalid(None) → 仍 3/5 当选（分母恒 5）
        assert strict_majority(["A", "A", "A", None, None]) == "A"
        # 2 有效 A + 3 invalid → 2/5 < 3 → unresolved
        assert strict_majority(["A", "A", None, None, None]) is None

    def test_all_none_unresolved(self):
        assert strict_majority([None, None, None, None, None]) is None

    def test_exact_threshold_boundary(self):
        assert strict_majority(["B", "B", "B", "A", "A"]) == "B"      # 恰好 3 票当选

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            strict_majority([])

    def test_custom_threshold(self):
        # threshold 参数化（默认 3）；双达阈值并存只可能 n>5，此时返回 None 不任选
        assert strict_majority(["A", "A", "B", "B"], threshold=2) is None
        assert strict_majority(["A", "A", "A", "A"], threshold=4) == "A"
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_strict_vote.py -q` → `ImportError`。

- [ ] **Step 3：实现（追加到 `benchmark/runners/self_consistency.py` 末尾，完整代码）**

```python
def strict_majority(votes: Sequence[Optional[str]], threshold: int = 3) -> Optional[str]:
    """严格多数投票（Phase 6 6A1，设计 §5.2.4）。

    与 majority_vote 的区别：majority_vote 取相对多数并按首次出现破平局
    （2/1/1/1 会选出 2 票选项），不满足严格协议，故新增且**不复用**。

    - 任一选项票数 >= threshold 且唯一 → 该选项；
    - 否则（含双达阈值、无达阈值、全 None）→ None（unresolved，按错误计入分母）；
    - None 票（invalid/call_failed）不参与计票但留在 votes 长度内——分母恒为采样次数；
    - 禁止任何形式的破平局。
    """
    if len(votes) == 0:
        raise ValueError("strict_majority requires at least one vote")
    counts: dict = {}
    for vote in votes:
        if vote is None:
            continue
        counts[vote] = counts.get(vote, 0) + 1
    winners = [label for label, n in counts.items() if n >= threshold]
    return winners[0] if len(winners) == 1 else None
```

- [ ] **Step 4：运行确认全绿 + 回归**（本文件为纯函数追加，跑 Task 文件 + g2 组即可；g1/g3/g4 提交前全跑）。

- [ ] **Step 5：提交（精确路径）**

```powershell
git add benchmark/runners/self_consistency.py tests/test_strict_vote.py
git commit -m "feat(phase6): strict_majority 严格 ≥3/5 投票（6A1，不复用 majority_vote）"
```

---

## Task 2：runner `emit_samples` 逐样本模式 + `--attempt-stage` + manifest 扩展

**文件**：`benchmark/runners/run_benchmark.py`（8 处外科手术修改）；`tests/phase6_helpers.py`（测试设施增补）；`tests/test_phase6_emit_samples.py`（新增）。

**修改清单**（全部为追加/参数透传，不改既有 `majority` 路径行为）：

| # | 位置锚点 | 修改 |
| --- | --- | --- |
| 1 | argparse L1332 | `--aggregate` choices 增加 `"emit_samples"`；新增 `--attempt-stage`（default `"main"`） |
| 2 | L1408 ctx 初始化 | `attempt_stage="main"` → `attempt_stage=args.attempt_stage` |
| 3 | `Phase6Context.enrich_row` L263 | attempt key 取 `sample_idx=int(row.get("sample_idx") or 0)` |
| 4 | `_attempt_with_ledger`/`_call_with_optional_ledger`/`call_model_sync` | 各加 `sample_idx=0` 透传 |
| 5 | main() L1440-1443 resume 过滤 | emit 模式跳过 case 级预过滤，completed 集传入 `run_model_benchmark(completed_keys=...)` 按样本跳过 |
| 6 | `run_model_benchmark` 校验段 L675-678 + per-case 循环 L957 前 | **既有集合 `{"majority"}` 扩为 `{"majority", "emit_samples"}`（审核 B1）** + emit 校验追加 + emit 分支 |
| 7 | `RESUME_MANIFEST_FIELDS` L121 + `build_resume_manifest` L168 | **加 `attempt_stage` 字段（决策 7 反转）**；旧 manifest 缺字段由 `check_resume_manifest` 自然 fail-closed |
| 8 | `run_model_benchmark` 签名 | 加 `completed_keys=None`（配合 #5） |

- [ ] **Step 0：测试设施增补（`tests/phase6_helpers.py`，精确追加）**

```python
# RunnerEnv.__init__ 内追加（self.received 下一行）：
        self.received_kw: list = []       # 每次模型调用的 **kw（temperature 等），按调用顺序

# RunnerEnv._fake_call 替换为：
    def _fake_call(self, messages, **kw):
        self.received.append(messages)
        self.received_kw.append(kw)
        action, payload = self._script.pop(0)
        if action in ("fail", "crash"):
            raise payload
        return payload

# RunnerEnv 增补方法（model_succeeds_then_crash 之后）：
    def model_sequence(self, texts: list) -> None:
        """按序返回不同响应（emit_samples 逐样本差异化用）；耗尽后恒返回 "A"。"""
        self._script = [("ok", t) for t in texts] + [("ok", "A")] * 1000
```

- [ ] **Step 1：写失败测试 `tests/test_phase6_emit_samples.py`（完整代码）**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.phase6_helpers import RunnerEnv

EMIT = ["--n-samples", "5", "--aggregate", "emit_samples",
        "--profile", "baziqa_xjz_direct", "--chart-schema-version", "legacy_v0",
        "--arm", "vote5_samples", "--sample-temperature", "0.4"]


def _keys(rows):
    return {tuple(r["attempt_key"]) for r in rows}


class TestEmitSamples:
    def test_emit_writes_per_sample_rows(self, tmp_path, monkeypatch):
        """每 case 写 5 行；attempt key 10 字段且 sample_idx 0..4 互异；行带 emit 标记。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10
        for r in rows:
            assert r["aggregate"] == "emit_samples" and r["n_samples"] == 5
            assert r["sample_idx"] in range(5)
            assert r["attempt_key"][3] == "main"               # 默认 attempt_stage
        per_case = {}
        for r in rows:
            per_case.setdefault(r["case_id"], set()).add(r["attempt_key"][8])
        assert per_case == {"c0": {0, 1, 2, 3, 4}, "c1": {0, 1, 2, 3, 4}}

    def test_emit_uses_sample_temperature(self, tmp_path, monkeypatch):
        """5 个样本全部以 sample_temperature=0.4 发起（非 --temperature 0.0）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        temps = [kw.get("temperature") for kw in env.received_kw]
        assert temps == [0.4] * 5

    def test_attempt_stage_param_flows_to_keys(self, tmp_path, monkeypatch):
        """--attempt-stage anchor → 全部行 attempt_key[3] == 'anchor'。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT + ["--attempt-stage", "anchor"]) == 0
        assert {r["attempt_key"][3] for r in env.read_detail()} == {"anchor"}

    def test_emit_resume_per_sample(self, tmp_path, monkeypatch):
        """7 次成功后崩溃（c0 5 + c1 头 2）；resume 只补 c1 余 3 样本；
        最终键集合 == 一次性运行（续跑幂等）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_succeeds_then_crash("A", successes=7)
        env.run_expect_crash(extra_argv=EMIT)
        env.model_returns("A")
        assert env.run(resume=True, extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10 and len(_keys(rows)) == 10     # 无重复键

    def test_emit_case_level_prefilter_not_applied(self, tmp_path, monkeypatch):
        """全量后删掉 c0 的 sample 1-4 行（留 sample 0）→ resume 恰好补 4 次调用；
        若错误沿用 case 级预过滤（sample_idx=0 键已完成），c0 会被整体跳过（0 次）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        kept = [r for r in env.read_detail()
                if not (r["case_id"] == "c0" and r["sample_idx"] != 0)]
        env.detail.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                      for r in kept), encoding="utf-8")
        before = len(env.received)
        assert env.run(resume=True, extra_argv=EMIT) == 0
        assert len(env.received) - before == 4                 # 只补 c0 样本 1-4
        rows = env.read_detail()
        assert len(rows) == 10 and len(_keys(rows)) == 10

    def test_emit_sample_failure_row_and_budget(self, tmp_path, monkeypatch):
        """头 3 次网络失败 → c0/sample0 重试耗尽写 call_failed 行（占分母），
        后续样本继续；总调用 3 + 9 = 12；重试账本只记 sample0。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_fails(times=3)
        assert env.run(extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10
        failed = [r for r in rows if r["terminal_state"] == "call_failed"]
        assert len(failed) == 1 and failed[0]["case_id"] == "c0" \
            and failed[0]["sample_idx"] == 0
        assert len(env.read_events("call_attempt")) == 12
        assert len(env.read_events("model_call_failed")) == 3
        assert {tuple(e["attempt_key"]) for e in env.read_events("model_call_failed")} \
            == {tuple(failed[0]["attempt_key"])}

    def test_emit_hard_cap_exit3_and_blocked_resume(self, tmp_path, monkeypatch):
        """hard_cap=3 → exit 3（BLOCKED_INCOMPLETE）；manifest 锁 cap，同 cap resume 仍 3
        且不新增调用（设计 §12.6：追加预算须新开 run/slice 目录，不得改 cap 续跑）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(scheduled_calls=10, hard_cap=3, extra_argv=EMIT) == 3
        assert len(env.read_events("call_attempt")) == 3
        assert env.run(resume=True, scheduled_calls=10, hard_cap=3, extra_argv=EMIT) == 3
        assert len(env.read_events("call_attempt")) == 3

    def test_emit_requires_profile_and_n_samples(self, tmp_path, monkeypatch):
        """emit_samples 无 profile → ValueError；n_samples=1 → ValueError。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        with pytest.raises(ValueError, match="emit_samples"):
            env.run(extra_argv=["--n-samples", "5", "--aggregate", "emit_samples"])
        with pytest.raises(ValueError, match="emit_samples"):
            env.run(extra_argv=["--n-samples", "1", "--aggregate", "emit_samples",
                                "--profile", "baziqa_xjz_direct",
                                "--chart-schema-version", "legacy_v0"])

    def test_emit_manifest_records_vote_fields(self, tmp_path, monkeypatch):
        """manifest 记录 aggregate/n_samples/sample_temperature/attempt_stage/temperature。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        m = json.loads((tmp_path / "detail.manifest.json").read_text(encoding="utf-8"))
        assert m["aggregate"] == "emit_samples" and m["n_samples"] == 5
        assert m["sample_temperature"] == 0.4 and m["temperature"] == 0.0
        assert m["attempt_stage"] == "main"                    # 决策 7 反转

    def test_resume_rejects_attempt_stage_change(self, tmp_path, monkeypatch):
        """决策 7 反转：先以 main 跑，再以 --attempt-stage anchor 续跑 → SystemExit(2)
        （manifest attempt_stage 不一致 fail-closed；同目录混合 stage 被禁止）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        with pytest.raises(SystemExit) as exc:
            env.run(resume=True, extra_argv=EMIT + ["--attempt-stage", "anchor"])
        assert exc.value.code == 2
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_phase6_emit_samples.py -q`（argparse 拒绝 `--aggregate emit_samples` / `ValueError` 缺失等）。

- [ ] **Step 3：实现（8 处，完整代码）**

**(1) argparse（L1332 附近）**

```python
    parser.add_argument('--aggregate', default='majority', choices=['majority', 'emit_samples'],
                        help='Aggregation strategy; emit_samples = Phase 6 6A1 逐样本明细（聚合离线）')
    parser.add_argument('--attempt-stage', default='main',
                        help='Phase 6 attempt key 的 attempt_stage（main/anchor/diversity_probe/...）')
    parser.add_argument('--as-of-date', default='',
                        help='v6 高优 7：enrichment 锚定日期，入 resume manifest')
```

**(2) ctx 初始化（L1408）**

```python
            arm=args.arm, attempt_stage=args.attempt_stage,
```

**(3) `enrich_row`（L263-266，sample_idx 从行取）**

```python
    def enrich_row(self, row):
        key = self.attempt_key_for({"case_id": row.get("case_id"),
                                    "_permutation_id": row.get("permutation_id")},
                                   sample_idx=int(row.get("sample_idx") or 0))
        row["attempt_key"] = list(key)
        ...  # 其余不变
```

**(4) sample_idx 透传（3 个函数，签名与一行调用）**

```python
def _attempt_with_ledger(case, call_once, sample_idx=0):
    ...
    key = ctx.attempt_key_for(case or {}, sample_idx=sample_idx)
    ...

def _call_with_optional_ledger(messages, provider, model, case, temperature, timeout,
                               rag_k, retrieval_mode, option_evidence_k,
                               suppress_rag, suppress_apb, sample_idx=0):
    call_once = lambda: _call_once_messages(...)
    if _PHASE6_CTX is None:
        ...
    return _attempt_with_ledger(case, call_once, sample_idx=sample_idx)

def call_model_sync(prompt, provider, model, case=None, temperature=None, timeout=300,
                    rag_k=2, retrieval_mode='legacy', option_evidence_k=2,
                    suppress_rag=False, suppress_apb=False, sample_idx=0):
    messages = [{"role": "user", "content": prompt}]
    return _call_with_optional_ledger(
        messages, provider, model, case, temperature, timeout,
        rag_k, retrieval_mode, option_evidence_k, suppress_rag, suppress_apb,
        sample_idx=sample_idx)
```

**(5) main() resume 过滤（L1440-1443 替换）**

```python
    completed_keys = None
    if args.profile and args.resume:
        completed = load_completed_keys(os.path.abspath(args.case_details_jsonl))
        ctx = _PHASE6_CTX
        if args.aggregate == "emit_samples":
            completed_keys = completed      # emit：case 级预过滤会误丢部分完成 case，改按样本跳过
        else:
            cases = [c for c in cases if ctx.attempt_key_for(c) not in completed]
```

`run_model_benchmark(...)` 调用处加 `completed_keys=completed_keys`；函数签名加 `completed_keys=None`。

**(6) 校验段 + emit 分支（`run_model_benchmark`）**

**校验段集合扩展（审核 B1，L677-678 替换）**：

```python
    if aggregate not in {"majority", "emit_samples"}:
        raise ValueError(f"run_model_benchmark: aggregate {aggregate!r} is not supported")
```

校验段追加（L678 之后）：

```python
    if aggregate == "emit_samples":
        if not isinstance(n_samples, int) or n_samples < 2:
            raise ValueError("emit_samples 需要 n_samples > 1（6A1 逐样本模式）")
        if _PHASE6_CTX is None:
            raise ValueError("emit_samples 仅支持 Phase 6 profile 模式（需 attempt 账本/续跑/manifest）")
```

循环分支（per-case 循环内 prompt 构造之后、既有 `try:`（L957）之前插入，完整代码；`_HardCapExhausted` 非 RuntimeError 自然冒泡 → main 映射 exit 3）：

```python
        if aggregate == "emit_samples":
            # 6A1（设计 §5.2）：逐样本独立调用/记账/明细；聚合完全离线（编排器 strict_majority）。
            # 每样本：sample_idx 入 attempt key（独立终态/重试账本/续跑），
            # temperature=sample_temperature；失败样本写 call_failed 行（占分母）后继续。
            ctx = _PHASE6_CTX
            pending = [i for i in range(n_samples)
                       if not completed_keys
                       or ctx.attempt_key_for(case, sample_idx=i) not in completed_keys]
            if not pending:
                continue                    # resume：该 case 5 样本全部完成
            for sample_idx in pending:
                try:
                    raw = call_model_sync(
                        prompt, provider, model, case=case,
                        temperature=sample_temperature, sample_idx=sample_idx,
                        **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
                    )
                    meta = extract_choice_with_meta(raw)
                    s_pred = meta["choice"]
                    ev = score_case_evidence(case, raw)
                    sf = score_safety(raw)
                    s_detail = {
                        "case_id": case_id, "domain": case.get("domain", "unknown"),
                        "question": case.get("question", "")[:50],
                        "expected_answer": expected, "predicted_answer": s_pred,
                        "raw_answer": raw, "correct": s_pred == expected,
                        "evidence_coverage": ev.get("coverage", 0.0),
                        "safety_score": sf.get("score", 0.0),
                        "parser_source": meta.get("source"), "parser_valid": meta.get("valid"),
                        "rag_k": rag_k, "retrieval_mode": retrieval_mode,
                        "rag_trace": [], "option_evidence": {}, "option_evidence_coverage": {},
                        "retrieved_answer_leak": False, "config_id": config_id,
                        "call_success": True,
                        "permutation_id": case.get("_permutation_id"),
                        "label_map": case.get("answer_label_map") or {},
                        "predicted_identity": s_pred,
                        "correct_identity": case.get("_original_answer"),
                        "mode": "off-3",
                        "parser_failure_reason": classify_parser_failure(
                            raw_answer=raw, parsed_choice=s_pred,
                            valid=meta.get("valid", False),
                            label_map=case.get("answer_label_map") or {}, call_success=True),
                        "sample_idx": sample_idx, "n_samples": n_samples,
                        "aggregate": aggregate,
                    }
                except RuntimeError as e:
                    if not str(e).startswith("model_call_failed"):
                        raise   # 崩溃类冒泡（Policy A）
                    s_detail = {
                        "case_id": case_id, "domain": case.get("domain", "unknown"),
                        "question": case.get("question", "")[:50],
                        "expected_answer": expected, "predicted_answer": None,
                        "raw_answer": "", "correct": False,
                        "error": str(e)[:120],
                        "evidence_coverage": 0.0, "safety_score": 0.0,
                        "parser_source": None, "parser_valid": False,
                        "rag_k": rag_k, "retrieval_mode": retrieval_mode,
                        "rag_trace": [], "option_evidence": {}, "option_evidence_coverage": {},
                        "retrieved_answer_leak": False, "config_id": config_id,
                        "call_success": False,
                        "permutation_id": case.get("_permutation_id"),
                        "label_map": case.get("answer_label_map") or {},
                        "predicted_identity": None,
                        "correct_identity": case.get("_original_answer"),
                        "mode": "off-3",
                        "parser_failure_reason": "model_call_failed",
                        "sample_idx": sample_idx, "n_samples": n_samples,
                        "aggregate": aggregate,
                    }
                case_details.append(s_detail)
                _append_jsonl(case_details_jsonl, s_detail)
                time.sleep(1)
            predictions[case_id] = s_detail.get("raw_answer") or ""
            continue
```

（`expected = extract_choice(case.get("answer"))` 与 `prompt` 在分支前已按既有代码求得；若现有位置在分支之后，则在分支首行补 `expected = extract_choice(case.get('answer'))`，实施时以当前文件锚点为准并在 commit 中登记。）

**(7) manifest 加 `attempt_stage`（决策 7 反转）**

```python
RESUME_MANIFEST_FIELDS: tuple = (
    "dataset_sha256", "case_ids_sha256", "profile_id", "chart_schema_version",
    "arm", "attempt_stage", "repeat_idx", "provider", "model",
    "temperature", "sample_temperature", "n_samples", "aggregate", "method",
    "prompt_template_sha256", "code_sha256", "scheduled_calls", "hard_cap",
    "as_of_date",                              # v6 高优 7：enrichment 锚定日期
)
```

`build_resume_manifest`（L168 起）返回字典中增加：

```python
        "attempt_stage": getattr(args, "attempt_stage", "main"),
        "as_of_date": getattr(args, "as_of_date", ""),       # v6 高优 7
```

（`check_resume_manifest`（:203 起）按 `RESUME_MANIFEST_FIELDS` 逐一比对--旧 manifest 无该字段 -> 不一致 -> SystemExit(2) fail-closed，无需改比对逻辑。）

**(8) `run_model_benchmark` 签名**

```python
def run_model_benchmark(cases, provider, model, prompt_version, ..., resume_append=False,
                        completed_keys=None):
```

- [ ] **Step 4：运行确认全绿 + 4 组回归**。

- [ ] **Step 5：提交（精确路径）**

```powershell
git add benchmark/runners/run_benchmark.py tests/phase6_helpers.py tests/test_phase6_emit_samples.py
git commit -m "feat(phase6): runner emit_samples 逐样本模式 + --attempt-stage 入 manifest（6A1）"
```

---

## Task 3：6A1 编排器 `scripts/run_phase6_6a1_ablation.py`

**职责**：离线 gate（legacy_v0 可见性 + 泄漏）、probe 多样性试测与 T 冻结（仅合法选项 + 完整性 BLOCKED）、AB/BA 12 切片调度、阶段预算（复用 6A0 `BudgetLedger`）、全量完整性检查、严格聚合与 Δ1/Δ2、配对四格表、unresolved 率、成本代理、verdict、报告与 manifest、CLI 年份封死与 dev 温度自动读取。
**测试**：`tests/test_phase6_6a1_vote.py`。**辅助扩展**：`scripts/build_phase6_audit_index.py` 加 `--arms` + `--mode vote` + `recompute_vote_accuracy()`（决策 9，审核阻断 1）。

- [ ] **Step 1：写失败测试 `tests/test_phase6_6a1_vote.py`（完整代码）**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase6_6a1_ablation import (
    ANCHOR_CAPS,
    PROFILE_ID,
    VoteConfig,
    aggregate_metrics,
    build_main_schedule,
    cost_metrics,
    diversity_rate,
    evaluate_t_switch,
    gate_verdict,
    load_dev_temperature,
    main as vote_main,
    probe_rows_complete,
    run_vote,
    strict_rows_complete,
    validate_case_ids,
)
from tests.phase6_helpers import RunnerSpy

CASE_IDS = [f"c{i}" for i in range(40)]
PROBE_IDS = [f"c{i}" for i in range(10)]


def fake_vote_config(**overrides):
    base = dict(run_id="t", year=2024, root=Path(".tmp/x"), enriched_path=Path("e.jsonl"))
    base.update(overrides)
    return VoteConfig(**base)


def srow(case_id, repeat, sample_idx, letter, arm="vote5_samples", terminal="parsed"):
    """构造采样/锚定行（真实行形状：臂/repeat/sample 在 attempt_key 内）。"""
    stage = {"vote5_samples": "main", "anchor_single0": "anchor"}[arm]
    return {"case_id": case_id, "correct": letter == "B",
            "expected_answer": "B", "predicted_answer": letter,
            "terminal_state": terminal,
            "attempt_key": ["ds", PROFILE_ID, arm, stage, "deepseek", "deepseek-chat",
                            case_id, repeat, sample_idx, "p0"]}


def probe_row(case_id, sample_idx, letter, arm="probe_r1", terminal="parsed"):
    """v5 阻断 2：构造 probe 行（arm=probe_r1/probe_r2、stage=diversity_probe、repeat_idx=-1）。
    srow 只支持 vote5_samples/anchor_single0，probe 测试必须用本 fixture。"""
    assert arm in ("probe_r1", "probe_r2")
    return {"case_id": case_id, "correct": letter == "B",
            "expected_answer": "B", "predicted_answer": letter,
            "terminal_state": terminal,
            "attempt_key": ["ds", PROFILE_ID, arm, "diversity_probe", "deepseek",
                            "deepseek-chat", case_id, -1, sample_idx, "p0"]}


class TestDiversity:
    def test_rate_and_switch_decision(self):
        # 6/10 题 ≥2 个不同合法选项 → 0.6 → 冻结 0.4，不跑 r2
        rows = []
        for i in range(10):
            letters = ["A", "A", "B", "A", "A"] if i < 6 else ["A"] * 5
            for j, L in enumerate(letters):
                rows.append(probe_row(f"c{i}", j, L))
        assert diversity_rate(rows, PROBE_IDS) == 0.6
        assert evaluate_t_switch(0.6, None) == ("freeze", 0.4)
        assert evaluate_t_switch(0.5, None) == ("probe_r2", 0.4)
        assert evaluate_t_switch(0.5, 0.7) == ("freeze", 1.0)
        assert evaluate_t_switch(0.5, 0.4) == ("freeze_low_diversity", 1.0)

    def test_invalid_not_counted_as_second_option(self):
        # 4×A(parsed) + 1 条 call_failed -> None 不算第二选项（v2 阻断 4）-> 0 diverse / 10 题分母 = 0.0
        rows = []
        for i in range(10):
            for j in range(4):
                rows.append(probe_row(f"c{i}", j, "A"))
            rows.append(probe_row(f"c{i}", 4, None, terminal="call_failed"))
        assert diversity_rate(rows, PROBE_IDS) == 0.0

    def test_all_invalid_stays_in_denominator(self):
        """v3 阻断 2：6 diverse + 4 all-invalid -> 0.6（全 invalid 题保留分母，而非 6/6=1.0）。"""
        rows = []
        for i in range(10):
            if i < 6:
                for j, L in enumerate(["A", "A", "B", "A", "A"]):
                    rows.append(probe_row(f"c{i}", j, L))
            else:
                for j in range(5):
                    rows.append(probe_row(f"c{i}", j, None, terminal="call_failed"))
        assert diversity_rate(rows, PROBE_IDS) == 0.6

    def test_probe_completeness_required(self):
        # v5 阻断 1+2：probe_row + expected_arm；不足 10 题/重复 sample_idx/缺样本 -> 不完整
        with pytest.raises(ValueError, match="不完整"):
            probe_rows_complete([probe_row(f"c{i}", j, "A") for i in range(9) for j in range(5)],
                                PROBE_IDS, "probe_r1")
        with pytest.raises(ValueError, match="不完整"):
            probe_rows_complete([probe_row(f"c{i}", j, "A") for i in range(10) for j in [0, 0, 1, 2, 3]],
                                PROBE_IDS, "probe_r1")
        with pytest.raises(ValueError, match="不完整"):
            probe_rows_complete([probe_row(f"c{i}", j, "A") for i in range(10) for j in [0, 1, 2, 3]],
                                PROBE_IDS, "probe_r1")
        probe_rows_complete([probe_row(f"c{i}", j, "A") for i in range(10) for j in range(5)],
                            PROBE_IDS, "probe_r1")


class TestSchedule:
    def test_main_schedule_order_and_caps(self):
        sched = build_main_schedule(fake_vote_config(), CASE_IDS)
        assert len(sched) == 12
        seq = [(s.arm, s.group) for s in sched[:4]]
        assert seq == [("vote5_samples", "group_a"), ("anchor_single0", "group_a"),
                       ("anchor_single0", "group_b"), ("vote5_samples", "group_b")]
        assert sum(s.hard_cap for s in sched) == 660 + sum(ANCHOR_CAPS)
        assert sum(s.scheduled_calls for s in sched) == 720
        sample = [s for s in sched if s.arm == "vote5_samples"][0]
        anchor = [s for s in sched if s.arm == "anchor_single0"][0]
        assert (sample.n_samples, sample.temperature) == (5, 0.4)
        assert (anchor.n_samples, anchor.temperature) == (1, 0.0)
        assert sample.stage == "main" and anchor.stage == "anchor"

    def test_schedule_requires_40(self):
        with pytest.raises(ValueError):
            build_main_schedule(fake_vote_config(), CASE_IDS[:39])

    def test_schedule_requires_unique_case_ids(self):
        # 40 个 case_id 但有重复 → 拒绝（审核高优 7c）
        dup = CASE_IDS[:39] + ["c0"]
        with pytest.raises(ValueError, match="唯一"):
            build_main_schedule(fake_vote_config(), dup)


def _full_rows(per_repeat_correct_v5, per_repeat_correct_s0):
    """构造 40 题 × 3 repeats：采样臂每题 5 行（3B2A → vote5 恒 B）+ 锚定行。"""
    rows = []
    for rep in range(3):
        for i in range(40):
            cid = f"c{i}"
            v5_win = i < per_repeat_correct_v5[rep]
            letters = ["B", "B", "B", "A", "A"] if v5_win else ["A", "A", "A", "B", "B"]
            for j, L in enumerate(letters):
                rows.append(srow(cid, rep, j, L))
            rows.append(srow(cid, rep, 0, "B" if i < per_repeat_correct_s0[rep] else "A",
                             arm="anchor_single0"))
    return rows


class TestCompleteness:
    """审核阻断 2：完整性全量断言；任一异常 → ValueError（上层映射 BLOCKED_INCOMPLETE）。"""

    def test_full_ok(self):
        strict_rows_complete(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, 3)

    def test_missing_case(self):
        rows = [r for r in _full_rows([40, 40, 40], [35, 35, 35]) if r["case_id"] != "c0"]
        with pytest.raises(ValueError, match="不完整"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_missing_anchor(self):
        rows = [r for r in _full_rows([40, 40, 40], [35, 35, 35])
                if not (r["case_id"] == "c0" and r["attempt_key"][7] == 0
                        and r["attempt_key"][2] == "anchor_single0")]
        with pytest.raises(ValueError, match="不完整"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_duplicate_sample(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c0", 0, 0, "B"))
        with pytest.raises(ValueError, match="重复"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_extra_repeat(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c0", 5, 0, "B"))
        with pytest.raises(ValueError, match="额外 repeat"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_extra_case(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c99", 0, 0, "B"))
        with pytest.raises(ValueError, match="额外 case"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_unknown_arm(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        bad = srow("c0", 0, 0, "B")
        bad["attempt_key"][2] = "mystery_arm"
        rows.append(bad)
        with pytest.raises(ValueError, match="未知 arm"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_bad_terminal_state(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows[0]["terminal_state"] = "weird"
        with pytest.raises(ValueError, match="终态"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_extra_anchor_sample_idx_rejected(self):
        """v3 中优 4：anchor sample_idx != 0 直接拒绝（不允许 0..4）。"""
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c0", 0, 1, "B", arm="anchor_single0"))   # anchor idx=1
        with pytest.raises(ValueError, match="anchor"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_extra_sample_set_rejected(self):
        """v3 中优 4：额外 sample 行（超范围 idx）也拒绝，不只检查缺失。"""
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c0", 0, 5, "B"))   # sample_idx=5 超范围
        with pytest.raises(ValueError, match="sample_idx|额外"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_aggregate_blocked_on_incomplete(self):
        rows = [r for r in _full_rows([40, 40, 40], [35, 35, 35]) if r["case_id"] != "c0"]
        with pytest.raises(ValueError, match="不完整"):
            aggregate_metrics(rows, CASE_IDS, repeats=3)


class TestAggregate:
    def test_metrics_and_verdict_promote(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        m = aggregate_metrics(rows, CASE_IDS, repeats=3)
        assert m["acc"]["vote5"] == [1.0, 1.0, 1.0]
        assert m["acc"]["single_t"] == [1.0, 1.0, 1.0]
        assert m["acc"]["anchor"] == [0.875, 0.875, 0.875]
        assert m["delta1_pp"] == 0.0 and m["delta2_pp"] == 12.5
        assert m["unresolved_rate"] == 0.0
        assert gate_verdict(3.0, 0.0) == "PROMOTE_CANDIDATE"
        assert gate_verdict(3.0, -0.5) == "AGGREGATION_EFFECT_ONLY"
        assert gate_verdict(2.9, 5.0) == "NON_INFERIOR"
        assert gate_verdict(-3.0, 0.0) == "ROLLBACK"
        assert gate_verdict(0.0, 5.0) == "NON_INFERIOR"

    def test_unresolved_counts_wrong_and_rate(self):
        rows = []
        for rep in range(3):
            for i in range(40):
                for j, L in enumerate(["B", "B", "A", "A", "C"]):
                    rows.append(srow(f"c{i}", rep, j, L))
                rows.append(srow(f"c{i}", rep, 0, "B", arm="anchor_single0"))
        m = aggregate_metrics(rows, CASE_IDS, repeats=3)
        assert m["acc"]["vote5"] == [0.0, 0.0, 0.0]
        assert m["unresolved_rate"] == 1.0
        assert m["delta1_pp"] == -100.0

    def test_no_cross_repeat_aggregation(self):
        rows = []
        for rep in range(3):
            win = rep == 0
            for i in range(40):
                letters = ["B", "B", "B", "A", "A"] if win else ["A", "A", "A", "B", "B"]
                for j, L in enumerate(letters):
                    rows.append(srow(f"c{i}", rep, j, L))
                rows.append(srow(f"c{i}", rep, 0, "B" if win else "A", arm="anchor_single0"))
        m = aggregate_metrics(rows, CASE_IDS, repeats=3)
        assert m["acc"]["vote5"] == [1.0, 0.0, 0.0]
        assert m["per_repeat_delta1"] == [0.0, 0.0, 0.0]
        assert m["delta1_pp"] == 0.0

    def test_four_grid(self):
        m = aggregate_metrics(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, repeats=3)
        assert m["four_grid_vote5_vs_anchor"] == {"both": 105, "vote5_only": 15,
                                                  "anchor_only": 0, "neither": 0}

    def test_case_records_fields(self):
        # 首类指标（审核高优 5）：逐题明细 5 票/vote5/single@T/anchor/correct/unresolved
        m = aggregate_metrics(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, repeats=3)
        recs = m["case_records"]
        assert len(recs) == 120
        r0 = next(r for r in recs if r["case_id"] == "c0" and r["repeat_idx"] == 0)
        assert len(r0["votes"]) == 5
        assert r0["vote5"] == "B" and r0["single_t"] == "B" and r0["anchor"] == "B"
        assert r0["expected"] == "B" and r0["unresolved"] is False
        assert r0["vote5_correct"] is True
        bad = next(r for r in recs if r["case_id"] == "c39" and r["repeat_idx"] == 0)
        assert bad["anchor"] == "A" and bad["anchor_correct"] is False

    def test_acc_trimmed_mean_field(self):
        """v3 中优 5：三臂 repeat 准确率的 trimmed_mean 附列（不入 gate，设计 §2.1）。"""
        m = aggregate_metrics(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, repeats=3)
        assert set(m["acc_trimmed_mean"].keys()) == {"vote5", "single_t", "anchor"}
        # vote5 = [1.0, 1.0, 1.0]，trimmed_mean(0.1) 截尾后仍 1.0
        assert m["acc_trimmed_mean"]["vote5"] == 1.0
        assert m["acc_trimmed_mean"]["anchor"] == 0.875

    def test_by_domain_metrics(self):
        """v3 中优 5：by_domain 输出每个 domain 的三臂准确率及 Δ（设计 §2.1）。"""
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        for r in rows:
            r["domain"] = "d0" if int(r["case_id"][1:]) < 20 else "d1"
        m = aggregate_metrics(rows, CASE_IDS, repeats=3)
        bd = m["by_domain"]
        assert set(bd.keys()) == {"d0", "d1"}
        # d0=c0-c19：vote5 全对，anchor 全对（i<35）
        assert bd["d0"]["vote5"] == 1.0
        assert bd["d0"]["anchor"] == 1.0
        # d1=c20-c39：vote5 全对，anchor c20-c34 对(15)/c35-c39 错(5) -> 0.75
        assert bd["d1"]["vote5"] == 1.0
        assert bd["d1"]["anchor"] == 0.75


class TestAuditRecompute:
    """v3 阻断 1：审计复算必须是题级投票 + 独立完整性检查 + 与归档 summary 自动比对。"""

    def test_recompute_vote_accuracy(self):
        from scripts.build_phase6_audit_index import recompute_vote_accuracy
        out = recompute_vote_accuracy(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, repeats=3)
        assert out["acc"]["vote5"] == [1.0, 1.0, 1.0]
        assert out["acc"]["single_t"] == [1.0, 1.0, 1.0]
        assert out["acc"]["anchor"] == [0.875, 0.875, 0.875]
        assert out["delta1_pp"] == 0.0 and out["delta2_pp"] == 12.5
        assert out["unresolved"] == 0

    def test_recompute_differs_from_per_row(self):
        # 按行统计会把 vote5 的 3B2A 样本算成 60%，题级投票是 100%——两者必须区分
        from scripts.build_phase6_audit_index import recompute_accuracy, recompute_vote_accuracy
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        vote = recompute_vote_accuracy(rows, CASE_IDS, repeats=3)
        per_row = recompute_accuracy(rows, arms=("vote5_samples", "anchor_single0"))
        assert vote["acc"]["vote5"] == [1.0, 1.0, 1.0]
        assert per_row["per_arm"]["vote5_samples"][0]["accuracy"] == 0.6

    def test_recompute_rejects_incomplete_rows(self):
        """v3 阻断 1：缺整题/缺 anchor/重复行 -> ValueError，不静默缩小分母。"""
        from scripts.build_phase6_audit_index import recompute_vote_accuracy
        full = _full_rows([40, 40, 40], [35, 35, 35])
        # 缺整题（c0 两臂全丢）
        with pytest.raises(ValueError, match="不完整|缺失"):
            recompute_vote_accuracy([r for r in full if r["case_id"] != "c0"], CASE_IDS, repeats=3)
        # 缺 anchor（c0 的 anchor 行丢，sample 保留）
        with pytest.raises(ValueError, match="不完整|缺失"):
            recompute_vote_accuracy([r for r in full if not (r["case_id"] == "c0"
                and r["attempt_key"][2] == "anchor_single0")], CASE_IDS, repeats=3)
        # 重复 sample 行
        dup = full + [srow("c0", 0, 0, "B")]
        with pytest.raises(ValueError, match="重复"):
            recompute_vote_accuracy(dup, CASE_IDS, repeats=3)

    def test_check_summary_match(self, tmp_path):
        """v3 阻断 1：审计复算与归档 summary.json 自动比对，不一致返回 False。"""
        from scripts.build_phase6_audit_index import recompute_vote_accuracy, check_summary_match
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        recomputed = recompute_vote_accuracy(rows, CASE_IDS, repeats=3)
        bad = tmp_path / "summary.json"
        bad.write_text(json.dumps({"delta1_pp": 99.9, "delta2_pp": 12.5,
            "acc": recomputed["acc"], "unresolved": 0}), encoding="utf-8")
        assert not check_summary_match(recomputed, bad)
        good = tmp_path / "summary.json"
        good.write_text(json.dumps({"delta1_pp": 0.0, "delta2_pp": 12.5,
            "acc": recomputed["acc"], "unresolved_rate": 0.0,
            "unresolved": 0}), encoding="utf-8")
        assert check_summary_match(recomputed, good)


class TestYearSeal:
    """审核阻断 3：dev 仅 2024；复核仅 2021；其余一律 exit 2（校验先于数据读取）。"""

    def test_dev_rejects_non_2024(self):
        assert vote_main(["--run-id", "x", "--year", "2022"]) == 2
        assert vote_main(["--run-id", "x", "--year", "2023"]) == 2

    def test_recheck_rejects_non_2021(self):
        assert vote_main(["--run-id", "x", "--year", "2024", "--recheck",
                          "--dev-run-id", "d"]) == 2

    def test_dev_mode_rejects_2021(self):
        assert vote_main(["--run-id", "x", "--year", "2021"]) == 2


def _dev_archive(tmp_path, verdict="PROMOTE_CANDIDATE", temp=0.4):
    d = tmp_path / "dev-1"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(
        {"sample_temperature": temp, "profile_id": PROFILE_ID,
         "chart_schema_version": "legacy_v0", "provider": "deepseek",
         "model": "deepseek-chat"}), encoding="utf-8")
    (d / "summary.json").write_text(json.dumps({"verdict": verdict}), encoding="utf-8")
    return d


class TestDevRunId:
    def test_reads_temperature_and_verdict(self, tmp_path):
        _dev_archive(tmp_path)
        t, info = load_dev_temperature("dev-1", archive_dir=tmp_path,
                                       provider="deepseek", model="deepseek-chat")
        assert t == 0.4
        assert info["verdict"] == "PROMOTE_CANDIDATE"
        assert info["dev_run_id"] == "dev-1" and info["dev_manifest_sha256"]

    def test_rejects_non_promote(self, tmp_path):
        _dev_archive(tmp_path, verdict="NON_INFERIOR")
        with pytest.raises(ValueError, match="PROMOTE_CANDIDATE"):
            load_dev_temperature("dev-1", archive_dir=tmp_path,
                                 provider="deepseek", model="deepseek-chat")

    def test_rejects_config_mismatch(self, tmp_path):
        _dev_archive(tmp_path)
        with pytest.raises(ValueError, match="不一致"):
            load_dev_temperature("dev-1", archive_dir=tmp_path,
                                 provider="deepseek", model="other-model")


class TestCost:
    def test_cost_metrics(self):
        # 40 题 × 100 字符 × 3 repeats：vote5=60000，单臂=12000，比值 5.0（v3 中优 5）
        m = cost_metrics([100] * 40, repeats=3)
        assert m["arm_total_chars_per_run"] == {"vote5": 60000, "single_t": 12000, "anchor": 12000}
        assert m["cost_ratio_vote5_vs_single_t"] == 5.0
        assert m["cost_ratio_vote5_vs_anchor"] == 5.0
        assert m["per_case_chars_trimmed_mean"] == 100.0


class TestRunVote:
    def test_slices_in_order_and_ledger(self, tmp_path):
        spy = RunnerSpy()
        cfg = fake_vote_config(root=tmp_path)
        sched = build_main_schedule(cfg, CASE_IDS)
        result = run_vote(cfg, sched, slice_runner=spy)
        assert result["status"] == "OK"
        assert len(spy.calls) == 12
        result2 = run_vote(cfg, sched, slice_runner=spy)
        assert result2["status"] == "OK"        # 幂等：不触发溢出

    def test_blocked_incomplete_on_exit3(self, tmp_path):
        class Spy3(RunnerSpy):
            def __call__(self, slice_run, **kw):
                super().__call__(slice_run, **kw)
                return type("R", (), {"exit_code": 3, "records": [], "calls_attempted": 0})
        cfg = fake_vote_config(root=tmp_path)
        result = run_vote(cfg, build_main_schedule(cfg, CASE_IDS), slice_runner=Spy3())
        assert result["status"] == "BLOCKED_INCOMPLETE"


class TestValidateCaseIds:
    """v3 中优 6：case_id 早期校验，probe 前即拒绝畸形 dataset。"""

    def test_valid_40_unique(self):
        validate_case_ids(CASE_IDS)

    def test_rejects_short(self):
        with pytest.raises(ValueError, match="40"):
            validate_case_ids(CASE_IDS[:39])

    def test_rejects_duplicate(self):
        with pytest.raises(ValueError, match="唯一"):
            validate_case_ids(CASE_IDS[:39] + ["c0"])


class TestManifestReconciliation:
    """v3 阻断 3：manifest 预算对账与 slice_order 含 probe。"""

    def test_manifest_includes_probe(self, tmp_path):
        from scripts.run_phase6_6a1_ablation import (
            _build_manifest, build_probe_slice, build_main_schedule,
            VoteConfig, split_ab_ba,
        )
        config = VoteConfig(run_id="t", year=2024, root=tmp_path,
                            enriched_path=tmp_path / "e.jsonl")
        group_a, _ = split_ab_ba(CASE_IDS, config.seed)
        probe = build_probe_slice(config, group_a, "probe_r1", 0.4)
        main_sched = build_main_schedule(config, CASE_IDS)
        executed = [probe, *main_sched]
        manifest = _build_manifest(
            config, executed, attempted=770, temperature=0.4,
            probe_info={"rate_r1": 0.7, "action_r1": "freeze", "sample_temperature": 0.4},
            case_ids=CASE_IDS, dataset_sha256="abc", groups_sha256="def",
            dev_dataset_sha256="abc")
        br = manifest["budget_reconciliation"]
        assert br["probe_scheduled"] == 50
        assert br["main_scheduled"] == 720
        assert br["scheduled_total"] == 770
        assert br["attempted_total"] == 770
        assert br["registered_hard_cap"] == 910
        assert any("probe_r1" in s for s in manifest["slice_order"])
        assert len(manifest["slice_order"]) == 13   # 1 probe + 12 main


class TestProbeCaseBinding:
    """v4 阻断 2 + v5 阻断 1+2：probe_rows_complete 绑定预期 case + expected_arm；
    diversity_rate 拒绝预期外 case。probe 测试必须用 probe_row（非 srow）。"""

    def test_probe_rejects_wrong_case_set(self):
        """probe 结果混入另外 10 题 -> 集合不匹配 -> ValueError（不再只看题数）。"""
        from scripts.run_phase6_6a1_ablation import probe_rows_complete
        expected = [f"c{i}" for i in range(10)]
        rows = [probe_row(f"c{i + 100}", j, "A") for i in range(10) for j in range(5)]
        with pytest.raises(ValueError, match="集合不匹配"):
            probe_rows_complete(rows, expected, "probe_r1")

    def test_probe_rejects_wrong_arm(self):
        """v5 阻断 1：arm != expected_arm -> ValueError（禁止混合 probe_r1/r2）。"""
        from scripts.run_phase6_6a1_ablation import probe_rows_complete
        expected = [f"c{i}" for i in range(10)]
        rows = [probe_row(f"c{i}", j, "A", arm="probe_r2") for i in range(10) for j in range(5)]
        with pytest.raises(ValueError, match="arm 异常"):
            probe_rows_complete(rows, expected, "probe_r1")

    def test_diversity_rejects_unexpected_case(self):
        """diversity_rate 遇预期外 case -> ValueError（不再 setdefault 扩大分母）。"""
        from scripts.run_phase6_6a1_ablation import diversity_rate
        expected = [f"c{i}" for i in range(10)]
        rows = [probe_row("c999", 0, "A")]
        with pytest.raises(ValueError, match="预期外 case"):
            diversity_rate(rows, expected)


class TestAuditCliSummaryCheck:
    """v4 阻断 1 + v5 高优 7：审计 --mode vote 默认检查 summary，mismatch 时 main() 返回非零。
    v5 高优 7：测试用真实目录结构 <root>/<arm>/runs/<run_id>/slice_*/detail.jsonl + --root。"""

    @staticmethod
    def _write_real_slices(tmp_path, rows):
        """按 collect_run 真实目录写 detail.jsonl（arm 遍历 vote5_samples/anchor_single0）。"""
        by_arm = {}
        for r in rows:
            by_arm.setdefault(r["attempt_key"][2], []).append(r)
        for arm, arm_rows in by_arm.items():
            slice_dir = tmp_path / arm / "runs" / "6a1-2024-001" / "slice_main_0"
            slice_dir.mkdir(parents=True)
            (slice_dir / "detail.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in arm_rows) + "\n",
                encoding="utf-8")

    def test_audit_main_returns_nonzero_on_summary_mismatch(self, tmp_path, monkeypatch):
        """构造 summary.json 与复算结果不一致 -> main() 返回 2（真实目录 + --root）。"""
        import scripts.build_phase6_audit_index as audit
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        self._write_real_slices(tmp_path, rows)
        (tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl").parent.mkdir(parents=True,
                                                                                           exist_ok=True)
        (tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl").write_text(
            "\n".join(json.dumps({"case_id": f"c{i}"}) for i in range(40)) + "\n", encoding="utf-8")
        archive_root = tmp_path / "phase6_archive"
        archive = archive_root / "6a1-2024-001"
        archive.mkdir(parents=True)
        (archive / "summary.json").write_text(json.dumps({
            "delta1_pp": 99.9, "delta2_pp": 12.5,
            "acc": {"vote5": [1.0, 1.0, 1.0], "single_t": [1.0, 1.0, 1.0],
                    "anchor": [0.875, 0.875, 0.875]},
            "unresolved_rate": 0.0,
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(audit, "ARCHIVE_ROOT", archive_root)
        rc = audit.main(["--run-id", "6a1-2024-001", "--year", "2024",
                         "--arms", "vote5_samples,anchor_single0", "--mode", "vote",
                         "--root", str(tmp_path)])
        assert rc == 2

    def test_audit_main_skip_summary_check_returns_zero(self, tmp_path, monkeypatch):
        """--skip-summary-check 诊断模式 -> 不检查，返回 0（真实目录 + --root）。"""
        import scripts.build_phase6_audit_index as audit
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        self._write_real_slices(tmp_path, rows)
        (tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl").parent.mkdir(parents=True,
                                                                                           exist_ok=True)
        (tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl").write_text(
            "\n".join(json.dumps({"case_id": f"c{i}"}) for i in range(40)) + "\n", encoding="utf-8")
        archive_root = tmp_path / "phase6_archive"
        archive = archive_root / "6a1-2024-001"
        archive.mkdir(parents=True)
        (archive / "summary.json").write_text(json.dumps({"delta1_pp": 99.9}),
                                              encoding="utf-8")
        monkeypatch.setattr(audit, "ARCHIVE_ROOT", archive_root)
        rc = audit.main(["--run-id", "6a1-2024-001", "--year", "2024",
                         "--arms", "vote5_samples,anchor_single0", "--mode", "vote",
                         "--skip-summary-check", "--root", str(tmp_path)])
        assert rc == 0


class TestValidateCaseIdsCli:
    """v4 高优 4：畸形 case_id -> 结构化 JSON 错误 + exit 2 + runner 调用 0 次。"""

    def test_invalid_case_ids_returns_2_and_zero_calls(self, tmp_path, monkeypatch):
        """v6 测试缺口 + v8 阻断：40 行文件但含一个重复 case_id，通过实体校验后被
        validate_case_ids 拒（不再靠"39 行 + row_count=40"这种会被 v8 实体校验拒的方式）。"""
        import scripts.run_phase6_6a1_ablation as vote
        enriched = tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
        enriched.parent.mkdir(parents=True)
        # 40 行但含一个重复 case_id（39 唯一 + 1 重复）
        rows = [{"case_id": f"c{i}"} for i in range(39)] + [{"case_id": "c0"}]
        enriched.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        # v8 阻断：manifest row_count=40 与实际 40 行一致，SHA 与实际文件匹配
        manifest = tmp_path / "enrich_manifest.json"
        manifest.write_text(json.dumps({
            "as_of_date": "2024-01-01",
            "entries": [{"year": 2024, "output_path": str(enriched),
                         "output_sha256": vote.sha256_file(enriched),
                         "row_count": 40, "as_of_date": "2024-01-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vote, "_collect_workspace_state",
                            lambda: {"clean": True, "dirty_files": [], "file_sha256": {}})
        calls = []
        monkeypatch.setattr(vote, "run_vote", lambda *a, **k: calls.append(1) or {"status": "OK"})
        monkeypatch.setattr(vote, "offline_gate", lambda c: [])
        rc = vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path), "--yes"])
        assert rc == 2
        assert calls == []   # runner 未被调用


class TestProbeInfoRoundTrip:
    """v7 阻断 2：freeze_temperature 纯函数 + manifest 组合测试。
    v9 中优收口：本测试不驱动生产 main，只验证"纯函数写入 -> _build_manifest 保留 ->
    load_dev_temperature 读取"的字段链路；生产 main 是否真正调用 freeze_temperature 由
    TestFreezeTemperatureMainCallSpy 覆盖。"""

    def test_manifest_round_trip_has_sample_temperature(self, tmp_path, monkeypatch):
        """probe 流程生成的 manifest 必须含 temperature_freeze.sample_temperature，
        load_dev_temperature 读取时该字段必存且等于 manifest.sample_temperature。"""
        import scripts.run_phase6_6a1_ablation as vote
        # 构造合法 dataset + manifest
        enriched = tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
        enriched.parent.mkdir(parents=True)
        enriched.write_text("\n".join(json.dumps({"case_id": f"c{i}"}) for i in range(40)) + "\n",
                            encoding="utf-8")
        manifest = tmp_path / "enrich_manifest.json"
        manifest.write_text(json.dumps({
            "as_of_date": "2024-01-01",
            "entries": [{"year": 2024, "output_path": str(enriched),
                         "output_sha256": vote.sha256_file(enriched),
                         "row_count": 40, "as_of_date": "2024-01-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vote, "_collect_workspace_state",
                            lambda: {"clean": True, "dirty_files": [], "file_sha256": {}})
        # 模拟 probe 流程：用 freeze_temperature 纯函数（生产 main 也调用同一函数，
        # 若生产删除该调用，本测试立即失败）
        temperature = 0.4
        probe_info = vote.freeze_temperature({"rate_r1": 0.7, "action_r1": "freeze"}, temperature)
        assert probe_info["sample_temperature"] == temperature      # v8 高优 2：断言纯函数确写入
        config = vote.VoteConfig(run_id="dev", year=2024, root=tmp_path,
                                 enriched_path=enriched, as_of_date="2024-01-01",
                                 dev_dataset_sha256=vote.sha256_file(enriched))
        executed = [vote.build_probe_slice(config, [f"c{i}" for i in range(40)],
                                           "probe_r1", temperature)]
        m = vote._build_manifest(config, executed, attempted=50, temperature=temperature,
                                 probe_info=probe_info, case_ids=[f"c{i}" for i in range(40)],
                                 dataset_sha256=vote.sha256_file(enriched),
                                 groups_sha256="g", dev_dataset_sha256=config.dev_dataset_sha256)
        # 写入归档
        archive_dir = tmp_path / "phase6" / "dev"
        archive_dir.mkdir(parents=True)
        (archive_dir / "manifest.json").write_text(json.dumps(m, ensure_ascii=False),
                                                   encoding="utf-8")
        # v7 阻断 2：load_dev_temperature 要求 summary.json + audit_index.json 完整
        (archive_dir / "summary.json").write_text(json.dumps({
            "status": "OK", "verdict": "PROMOTE_CANDIDATE", "year": 2024,
            "recheck": False, "delta1_pp": 0.0, "delta2_pp": 0.0,
        }, ensure_ascii=False), encoding="utf-8")
        summary_sha = vote.sha256_file(archive_dir / "summary.json")
        (archive_dir / "audit_index.json").write_text(json.dumps({
            "mode": "vote", "run_id": "dev", "year": 2024,
            "dataset_sha256": config.dev_dataset_sha256,
            "summary_check": {"status": "PASS", "summary_sha256": summary_sha,
                              "recomputed": {"delta1_pp": 0.0, "delta2_pp": 0.0}},
        }, ensure_ascii=False), encoding="utf-8")
        # 闭环：load_dev_temperature 读取，验证 sample_temperature 字段存在且一致
        temperature_loaded, _ = vote.load_dev_temperature(
            "dev", archive_dir=tmp_path / "phase6",
            provider="deepseek", model="deepseek-chat",
            approved_2024_dataset_sha=config.dev_dataset_sha256)
        assert temperature_loaded == temperature
        assert m["temperature_freeze"]["sample_temperature"] == temperature


class TestAsOfDateResume:
    """v7 阻断 3：as_of_date resume 三场景测试。
    真实签名：build_resume_manifest(args, profile) / check_resume_manifest(manifest_path, current)。"""

    def _make_args(self, as_of_date, tmp_path):
        """构造带 as_of_date 属性的 args namespace + profile（最小桩）。"""
        import argparse
        from pathlib import Path
        ns = argparse.Namespace(
            as_of_date=as_of_date, attempt_stage="main",
            dataset=str(tmp_path / "ds.jsonl"), case_ids_file=None,
            arm="vote5_samples", repeat_idx=0, provider="deepseek", model="deepseek-chat",
            temperature=0.4, sample_temperature=0.4, n_samples=5,
            aggregate="emit_samples", method="strict_majority",
            scheduled_calls=50, hard_cap=60,
        )
        (tmp_path / "ds.jsonl").write_text("x\n", encoding="utf-8")
        profile = argparse.Namespace(
            profile_id="baziqa_v1", chart_schema_version="v1",
            prompt_template="", system_prompt="", user_prompt_template="",
            parser_mode="strict", aggregation="strict_majority",
        )
        return ns, profile

    def test_same_date_allows_resume(self, tmp_path):
        """相同 as_of_date -> resume 允许（check_resume_manifest 不抛 SystemExit）。"""
        from benchmark.runners.run_benchmark import build_resume_manifest, check_resume_manifest
        args, profile = self._make_args("2024-01-01", tmp_path)
        new_manifest = build_resume_manifest(args, profile)
        old_path = tmp_path / "resume.json"
        old_path.write_text(json.dumps(new_manifest, ensure_ascii=False), encoding="utf-8")
        check_resume_manifest(str(old_path), new_manifest)  # 不抛异常即通过

    def test_date_change_rejects_resume(self, tmp_path):
        """as_of_date 变化 -> SystemExit(2) 拒绝 resume。"""
        import pytest
        from benchmark.runners.run_benchmark import build_resume_manifest, check_resume_manifest
        args_old, profile = self._make_args("2024-01-01", tmp_path)
        old_manifest = build_resume_manifest(args_old, profile)
        old_path = tmp_path / "resume.json"
        old_path.write_text(json.dumps(old_manifest, ensure_ascii=False), encoding="utf-8")
        args_new, _ = self._make_args("2024-02-01", tmp_path)
        new_manifest = build_resume_manifest(args_new, profile)
        with pytest.raises(SystemExit) as ei:
            check_resume_manifest(str(old_path), new_manifest)
        assert ei.value.code == 2

    def test_missing_date_in_old_manifest_rejects_resume(self, tmp_path):
        """旧 manifest 缺 as_of_date 字段 -> SystemExit(2) fail-closed。"""
        import pytest
        from benchmark.runners.run_benchmark import build_resume_manifest, check_resume_manifest
        args, profile = self._make_args("2024-01-01", tmp_path)
        new_manifest = build_resume_manifest(args, profile)
        old_manifest = {k: v for k, v in new_manifest.items() if k != "as_of_date"}
        old_path = tmp_path / "resume.json"
        old_path.write_text(json.dumps(old_manifest, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(SystemExit) as ei:
            check_resume_manifest(str(old_path), new_manifest)
        assert ei.value.code == 2


class TestValidateEnrichmentEntry:
    """v7 高优 4 + v8 阻断/高优 1：validate_enrichment_entry 纯函数测试。"""

    def _write_valid_enriched(self, path: Path, n_rows: int = 40):
        """写 n_rows 唯一 case_id 的 enriched.jsonl。"""
        rows = [{"case_id": f"c{i}"} for i in range(n_rows)]
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def test_valid_entry_returns_sha(self, tmp_path):
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40,
                 "as_of_date": "2024-01-01"}
        assert validate_enrichment_entry(entry, enriched, 2024, "2024-01-01") == entry["output_sha256"]

    def test_wrong_year_rejected(self, tmp_path):
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2023, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40,
                 "as_of_date": "2024-01-01"}
        with pytest.raises(ValueError, match="year 异常"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_path_mismatch_rejected(self, tmp_path):
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        other = tmp_path / "other.jsonl"
        self._write_valid_enriched(other)
        entry = {"year": 2024, "output_path": str(other),
                 "output_sha256": vote.sha256_file(other), "row_count": 40,
                 "as_of_date": "2024-01-01"}
        with pytest.raises(ValueError, match="output_path 与 enriched_path 不一致"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_sha_mismatch_rejected(self, tmp_path):
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": "wrong", "row_count": 40, "as_of_date": "2024-01-01"}
        with pytest.raises(ValueError, match="output_sha256 不匹配"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_actual_row_count_mismatch_rejected(self, tmp_path):
        """v8 阻断：实际 39 行但 row_count 声明 40 -> 拒（原漏洞正是此场景）。"""
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched, n_rows=39)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40,
                 "as_of_date": "2024-01-01"}
        with pytest.raises(ValueError, match="实际行数"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_as_of_date_mismatch_with_top_rejected(self, tmp_path):
        """v8 高优 1：entry.as_of_date != expected_as_of_date -> 拒。"""
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40,
                 "as_of_date": "2024-02-01"}
        with pytest.raises(ValueError, match="as_of_date 与顶层不一致"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_empty_as_of_date_rejected(self, tmp_path):
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40, "as_of_date": ""}
        with pytest.raises(ValueError, match="as_of_date 为空"):
            validate_enrichment_entry(entry, enriched, 2024, "")


class TestAllowDirtyCli:
    """v8 高优 3：--allow-dirty 策略 CLI 测试锁定。"""

    def _prepare_valid_dataset(self, tmp_path):
        """写合法 40 行 dataset + enrich_manifest（供 CLI 用）。"""
        import scripts.run_phase6_6a1_ablation as vote
        enriched = tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
        enriched.parent.mkdir(parents=True)
        rows = [{"case_id": f"c{i}"} for i in range(40)]
        enriched.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        (tmp_path / "enrich_manifest.json").write_text(json.dumps({
            "as_of_date": "2024-01-01",
            "entries": [{"year": 2024, "output_path": str(enriched),
                         "output_sha256": vote.sha256_file(enriched),
                         "row_count": 40, "as_of_date": "2024-01-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        return enriched

    def test_allow_dirty_with_yes_rejected(self, tmp_path):
        """--allow-dirty --yes 组合被 parser.error 拒（SystemExit 2）。"""
        import pytest
        import scripts.run_phase6_6a1_ablation as vote
        with pytest.raises(SystemExit) as ei:
            vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path),
                       "--allow-dirty", "--yes"])
        assert ei.value.code == 2

    def test_only_allow_dirty_zero_run_vote_calls(self, tmp_path, monkeypatch):
        """仅 --allow-dirty（无 --yes）时 fake run_vote 调用 0 次（不进模型调用路径）。
        v9 阻断：主流程缺 --yes 走 dry-run 语义 return 0；关键不变量是 calls == []。"""
        import scripts.run_phase6_6a1_ablation as vote
        self._prepare_valid_dataset(tmp_path)
        calls = []
        monkeypatch.setattr(vote, "run_vote", lambda *a, **k: calls.append(1) or {"status": "OK"})
        monkeypatch.setattr(vote, "offline_gate", lambda c: [])
        rc = vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path),
                        "--allow-dirty"])
        assert calls == []                              # runner 0 次（关键不变量）
        assert rc == 0                                  # dry-run 语义

    def test_dirty_without_allow_exits_before_offline_gate(self, tmp_path, monkeypatch):
        """workspace dirty 且无 --allow-dirty -> offline_gate 前 exit 2（fake gate 不被调用）。"""
        import scripts.run_phase6_6a1_ablation as vote
        self._prepare_valid_dataset(tmp_path)
        monkeypatch.setattr(vote, "_collect_workspace_state",
                            lambda: {"clean": False, "dirty_files": ["scripts/run_phase6_6a1_ablation.py M"],
                                     "file_sha256": {}})
        gate_calls = []
        monkeypatch.setattr(vote, "offline_gate", lambda c: gate_calls.append(1) or [])
        rc = vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path), "--yes"])
        assert rc == 2
        assert gate_calls == []                         # offline_gate 未被调用


class TestFreezeTemperatureMainCallSpy:
    """v9 中优：spy 包装 freeze_temperature 驱动生产 main，断言主流程确实调用。
    若生产 main 删除 `probe_info = freeze_temperature(...)` 那一行，本测试立即失败。"""

    def test_main_invokes_freeze_temperature_once(self, tmp_path, monkeypatch):
        import scripts.run_phase6_6a1_ablation as vote
        # 合法 dataset + manifest（复用 TestAllowDirtyCli 的准备逻辑）
        enriched = tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
        enriched.parent.mkdir(parents=True)
        rows = [{"case_id": f"c{i}"} for i in range(40)]
        enriched.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        (tmp_path / "enrich_manifest.json").write_text(json.dumps({
            "as_of_date": "2024-01-01",
            "entries": [{"year": 2024, "output_path": str(enriched),
                         "output_sha256": vote.sha256_file(enriched),
                         "row_count": 40, "as_of_date": "2024-01-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vote, "_collect_workspace_state",
                            lambda: {"clean": True, "dirty_files": [], "file_sha256": {}})
        monkeypatch.setattr(vote, "offline_gate", lambda c: [])
        # stub probe/main：run_vote 每次返回 OK；probe 后从 glob 读 rows -> stub 返回空
        # 走 probe_rows_complete + diversity_rate -> stub diversity_rate 直接给冻结 0.4 分支
        monkeypatch.setattr(vote, "run_vote", lambda *a, **k: {"status": "OK"})
        monkeypatch.setattr(vote, "probe_rows_complete", lambda *a, **k: None)
        monkeypatch.setattr(vote, "diversity_rate", lambda *a, **k: 0.7)  # >= 0.6 -> freeze 0.4
        monkeypatch.setattr(vote, "evaluate_t_switch", lambda r1, r2: ("freeze", 0.4))
        monkeypatch.setattr(vote, "write_report",
                            lambda *a, **k: {"status": "OK"})  # v10 阻断：返回 dict 避免 .get 崩
        # spy freeze_temperature（生产 main 内部通过模块属性调用，monkeypatch 生效）
        real = vote.freeze_temperature
        spy_calls = []
        def spy(info, temp):
            spy_calls.append((dict(info), temp))
            return real(info, temp)
        monkeypatch.setattr(vote, "freeze_temperature", spy)
        rc = vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path), "--yes"])
        assert rc == 0                                   # v10 阻断：锁定主流程正常终止
        assert len(spy_calls) == 1                       # 主流程调用 1 次
        info, temp = spy_calls[0]
        assert temp == 0.4                               # 参数正确
        assert "sample_temperature" not in info          # 传入 info 尚未含该字段
```

- [ ] **Step 2：运行确认失败** → `ModuleNotFoundError`。

- [ ] **Step 3：实现（完整代码）**

**(a) `scripts/build_phase6_audit_index.py` 扩展（决策 9）**

`main()` 加 `parser.add_argument("--arms", default="ctx_approved,ctx_legacy")` 与 `parser.add_argument("--mode", choices=["row", "vote"], default="row")` 与 `parser.add_argument("--root", default=".tmp/phase6")`（v5 高优 7：测试显式传 tmp_path）；**v6 阻断 2**：模块顶部定义 `ARCHIVE_ROOT = PROJECT_ROOT / "docs" / "phase6"`，main 用 `archive_dir = ARCHIVE_ROOT / args.run_id` 定位 `summary.json` 与 `audit_index.json`（测试 monkeypatch `ARCHIVE_ROOT`）；`--mode vote` 时从 dataset 读取 40 个唯一 case ID 作为 `expected_case_ids`，调用 `recompute_vote_accuracy(run["detail_rows"], expected_case_ids, repeats=3)`，否则旧路径（`recompute_accuracy(run["detail_rows"], arms=tuple(args.arms.split(",")), repeats=3)`）。**v4 阻断 1**：`--mode vote` 默认必须检查同目录 `summary.json`（`check_summary_match`），不一致或缺失直接 exit 2；新增 `parser.add_argument("--skip-summary-check", action="store_true")` 仅诊断用（正式命令禁止）。**v5 高优 5**：审计索引 `audit_index.json` 写入 `{"mode":"vote", "summary_check":{"status":"PASS"|"FAIL","summary_sha256":"...","recomputed":{...}}, "dataset_sha256":"...", "run_id":"...", "year":...}`（2021 复核前验证这些字段）。`recompute_accuracy` 签名改 `(detail_rows, arms=("ctx_approved","ctx_legacy"), repeats=3)`，函数体内两臂引用参数化（旧默认不变）。新增：

```python
def _audit_validate_rows(detail_rows: list, expected_case_ids: list, repeats: int) -> None:
    """v4 高优 3 + v5 高优 6：审计脚本自己的最小完整性验证（不导入生产函数）。
    v5 新增：拒绝重复逻辑键 (case, repeat, sample_idx)（不只拒完全相同 attempt key）+
    断言精确行数 sample==600 / anchor==120 + 验证 sample stage==main、anchor stage==anchor。"""
    expected = set(expected_case_ids)
    seen_sample, seen_anchor, seen_keys = set(), set(), set()
    sample_count, anchor_count = 0, 0
    for r in detail_rows:
        ak = r.get("attempt_key") or [None] * 10
        key = tuple(ak)
        if key in seen_keys:
            raise ValueError(f"审计完整性：重复 attempt key {key}")
        seen_keys.add(key)
        cid = r.get("case_id")
        if cid not in expected:
            raise ValueError(f"审计完整性：预期外 case {cid}")
        arm = ak[2]
        stage = ak[3]                  # v5: ak[3]=attempt_stage
        rep = ak[7]
        idx = ak[8]
        terminal = r.get("terminal_state")
        if terminal not in TERMINAL_OK:
            raise ValueError(f"审计完整性：终态非法 {terminal}（{cid}）")
        if arm == "vote5_samples":
            if stage != "main":
                raise ValueError(f"审计完整性：sample stage 非 main：{stage}（{cid}）")
            if idx not in {0, 1, 2, 3, 4}:
                raise ValueError(f"审计完整性：sample_idx 越界 {idx}（{cid}）")
            logical = (cid, rep, idx)
            if logical in seen_sample:
                raise ValueError(f"审计完整性：重复逻辑键 {logical}（attempt key 不同）")
            seen_sample.add(logical)
            sample_count += 1
        elif arm == "anchor_single0":
            if stage != "anchor":
                raise ValueError(f"审计完整性：anchor stage 非 anchor：{stage}（{cid}）")
            if idx != 0:
                raise ValueError(f"审计完整性：anchor sample_idx 非 0（{cid}）")
            logical = (cid, rep)
            if logical in seen_anchor:
                raise ValueError(f"审计完整性：重复 anchor 逻辑键 {logical}")
            seen_anchor.add(logical)
            anchor_count += 1
        else:
            raise ValueError(f"审计完整性：未知 arm {arm}（{cid}）")
    exp_sample = {(c, r, i) for c in expected for r in range(repeats) for i in range(5)}
    exp_anchor = {(c, r) for c in expected for r in range(repeats)}
    if seen_sample != exp_sample:
        miss = len(exp_sample - seen_sample)
        extra = len(seen_sample - exp_sample)
        raise ValueError(f"审计完整性：sample 集合不匹配（缺失 {miss}，额外 {extra}）")
    if seen_anchor != exp_anchor:
        miss = len(exp_anchor - seen_anchor)
        extra = len(seen_anchor - exp_anchor)
        raise ValueError(f"审计完整性：anchor 集合不匹配（缺失 {miss}，额外 {extra}）")
    if sample_count != len(expected) * repeats * 5:
        raise ValueError(f"审计完整性：sample 行数 {sample_count} != {len(expected) * repeats * 5}")
    if anchor_count != len(expected) * repeats:
        raise ValueError(f"审计完整性：anchor 行数 {anchor_count} != {len(expected) * repeats}")


def recompute_vote_accuracy(detail_rows: list, expected_case_ids: list, repeats: int = 3) -> dict:
    """v3 阻断 1：题级投票复算 + 独立完整性检查（缺题/缺 anchor/重复 -> ValueError，不静默缩小分母）。
    v4 高优 3：完整性检查改用审计脚本自己的 _audit_validate_rows，不再导入生产 strict_rows_complete。

    按 (case, repeat) 聚合 5 样本 strict_majority，派生 vote5 / single@T(sample_idx=0) /
    anchor 三臂准确率与 Δ1/Δ2、unresolved。与 recompute_accuracy 的区别：后者按行统计
    （仅适用单样本臂），本函数按题级投票。"""
    _audit_validate_rows(detail_rows, expected_case_ids, repeats)
    from benchmark.runners.self_consistency import strict_majority
    acc = {"vote5": [], "single_t": [], "anchor": []}
    unresolved = 0
    for rep in range(repeats):
        cases = sorted(expected_case_ids)
        n_v5 = n_st = n_an = 0
        for cid in cases:
            srows = sorted((r for r in detail_rows
                            if r["case_id"] == cid
                            and (r.get("attempt_key") or [None] * 10)[2] == "vote5_samples"
                            and (r.get("attempt_key") or [None] * 10)[7] == rep),
                           key=lambda r: (r.get("attempt_key") or [None] * 10)[8])
            arow = next((r for r in detail_rows
                         if r["case_id"] == cid
                         and (r.get("attempt_key") or [None] * 10)[2] == "anchor_single0"
                         and (r.get("attempt_key") or [None] * 10)[7] == rep))
            votes = [r["predicted_answer"] if r.get("terminal_state") == "parsed" else None
                     for r in srows]
            v5 = strict_majority(votes)
            if v5 is None:
                unresolved += 1
            exp = srows[0]["expected_answer"]
            n_v5 += (v5 is not None and v5 == exp)
            n_st += (srows[0].get("terminal_state") == "parsed"
                     and srows[0]["predicted_answer"] == exp)
            n_an += bool(arow and arow.get("terminal_state") == "parsed"
                         and arow["predicted_answer"] == exp)
        n = len(cases) or 1
        acc["vote5"].append(round(n_v5 / n, 4))
        acc["single_t"].append(round(n_st / n, 4))
        acc["anchor"].append(round(n_an / n, 4))
    d1 = [round((a - b) * 100, 2) for a, b in zip(acc["vote5"], acc["single_t"])]
    d2 = [round((a - b) * 100, 2) for a, b in zip(acc["vote5"], acc["anchor"])]
    total = len(expected_case_ids) * repeats
    return {"acc": acc, "per_repeat_delta1": d1, "per_repeat_delta2": d2,
            "delta1_pp": round(sum(d1) / repeats, 2),
            "delta2_pp": round(sum(d2) / repeats, 2),
            "unresolved": unresolved,
            "unresolved_rate": round(unresolved / max(total, 1), 4)}


def check_summary_match(recomputed: dict, summary_path) -> bool:
    """v3 阻断 1：审计复算与归档 summary.json 自动比对。不一致返回 False（CLI 退出非零）。"""
    import json as _json
    from pathlib import Path as _Path
    s = _json.loads(_Path(summary_path).read_text(encoding="utf-8"))
    if abs(float(s.get("delta1_pp", 0)) - recomputed["delta1_pp"]) > 0.01:
        return False
    if abs(float(s.get("delta2_pp", 0)) - recomputed["delta2_pp"]) > 0.01:
        return False
    for arm in ("vote5", "single_t", "anchor"):
        sa = s.get("acc", {}).get(arm, [])
        ra = recomputed["acc"][arm]
        if len(sa) != len(ra) or any(abs(a - b) > 0.001 for a, b in zip(sa, ra)):
            return False
    if abs(float(s.get("unresolved_rate", 0)) - recomputed["unresolved_rate"]) > 0.001:
        return False
    return True
```

**(b) `scripts/run_phase6_6a1_ablation.py`（新文件，完整代码）**

```python
"""Phase 6 6A1 编排器：严格 ≥3/5 投票同源配对 + temp-0 锚定（设计 v6 §5）。

probe 多样性试测（仅合法选项 + 完整性 BLOCKED）→ AB/BA 12 切片 → 全量完整性检查
→ 离线严格聚合（strict_majority，不跨 repeat）→ Δ1/Δ2 + 四格表 + unresolved + 成本代理 → verdict。
决策逻辑均为无网络纯函数；真实模型调用仅经 run_slice 子进程边界发起。
上下文基线 legacy_v0（6A0 ROLLBACK，设计 §10）。预算复用 6A0 BudgetLedger。
CLI 年份封死（dev 仅 2024 / 复核仅 2021）；复核温度 --dev-run-id 自动读取。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
ARCHIVE_ROOT = PROJECT_ROOT / "docs" / "phase6"        # v6 阻断 2：归档根目录

from benchmark.formatters.baziqa_prompt import format_direct_choice_prompt
from benchmark.formatters.chart_context import render_chart_context
from benchmark.formatters.leak_scan import scan_prompt_for_leaks
from benchmark.reports.accuracy_stats import trimmed_mean
from benchmark.runners.profiles import assert_visibility, resolve_profile
from benchmark.runners.self_consistency import strict_majority
from scripts.build_phase6_audit_index import sha256_file
from scripts.enrich_baziqa_chart_input import load_jsonl
from scripts.run_phase6_6a0_ablation import (
    BudgetLedger,
    BudgetLedgerCorrupt,
    split_ab_ba,
    _git_head,
)

WORKSPACE_FILES = (
    "scripts/run_phase6_6a1_ablation.py",
    "scripts/build_phase6_audit_index.py",
    "benchmark/runners/run_benchmark.py",
    "benchmark/runners/self_consistency.py",
)


def _collect_workspace_state() -> dict:
    """v5 门禁：收集实验范围文件的 dirty 状态与 SHA（真实 API 实验前要求无未提交修改）。"""
    import subprocess
    try:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *WORKSPACE_FILES],
            cwd=PROJECT_ROOT, text=True).strip().splitlines()
    except Exception:
        return {"collect_error": "git status failed"}
    return {
        "dirty_files": [l.strip() for l in dirty if l.strip()],
        "clean": len(dirty) == 0,
        "file_sha256": {f: sha256_file(PROJECT_ROOT / f) for f in WORKSPACE_FILES
                        if (PROJECT_ROOT / f).exists()},
    }

PROFILE_ID = "baziqa_xjz_direct"
SCHEMA = "legacy_v0"                      # 6A0 ROLLBACK 锁定（设计 §10）
EXPECTED_CASES = 40
N_SAMPLES = 5
PROBE_CASES = 10
DIVERSITY_THRESHOLD = 0.6
DEFAULT_T = 0.4
FALLBACK_T = 1.0
ARM_SAMPLE = "vote5_samples"
ARM_ANCHOR = "anchor_single0"
ANCHOR_CAPS = (24, 23, 23, 23, 23, 24)    # 和 140
SAMPLE_CAPS = (110,) * 6                  # 和 660
PROBE_CAP = 55
VALID_LETTERS = frozenset("ABCD")
TERMINAL_OK = frozenset(("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed"))


@dataclass(frozen=True)
class VoteConfig:
    run_id: str
    year: int
    root: Path
    enriched_path: Path
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    repeats: int = 3
    seed: int = 20260717
    stage_hard_cap: int = 910               # 2021 复核：800
    resume: bool = True
    as_of_date: str = ""                    # v4 建议：从 enriched manifest 读取，非运行当天
    dev_dataset_sha256: str = ""            # v6 阻断 1：2024 批准 SHA（复核模式传入）


@dataclass(frozen=True)
class VoteSlice:
    purpose: str                            # "probe" | "main"
    repeat_idx: int                         # probe 固定 -1
    arm: str
    stage: str
    group: str
    case_ids: tuple
    n_samples: int
    temperature: float                      # 采样臂=sample_temperature；锚定=0.0
    scheduled_calls: int
    hard_cap: int


# ---------- 纯函数：probe 多样性（审核阻断 4） ----------

def diversity_rate(rows: list, expected_probe_case_ids: list) -> float:
    """每题 ≥2 个不同合法选项的比例。只计 terminal_state=="parsed" 且答案 ∈ A/B/C/D
    （invalid/None/call_failed 不算第二个选项——审核阻断 4；不查看答案正确性——设计 §5.2.2）。"""
    per_case = {cid: set() for cid in expected_probe_case_ids}
    for r in rows:
        if r.get("terminal_state") != "parsed":
            continue
        ans = r.get("predicted_answer")
        cid = r["case_id"]
        if cid not in per_case:
            raise ValueError(f"预期外 case：{cid} 不在 probe 集合")
        if ans in VALID_LETTERS:
            per_case[cid].add(ans)
    if not per_case:
        return 0.0
    diverse = sum(1 for s in per_case.values() if len(s) >= 2)
    return round(diverse / len(per_case), 4)


def probe_rows_complete(rows: list, expected_probe_case_ids: list, expected_arm: str) -> None:
    """probe 数据完整性（v5 阻断 1）：严格验证 case 集合恰好等于预期 + arm==expected_arm +
    attempt_stage（ak[3]）==diversity_probe + repeat_idx（ak[7]）==-1 + 每题 sample_idx（ak[8]）
    恰好 {0,1,2,3,4} + 无额外行。不再只验证题数。
    v5 修正：attempt_stage 索引 ak[6] -> ak[3]（ak[6] 是 case_id）。
    v5 新增 expected_arm：禁止同文件混合 probe_r1 与 probe_r2。"""
    expected = set(expected_probe_case_ids)
    counts, per_case, arms, stages, repeats = {}, {}, set(), set(), set()
    for r in rows:
        cid = r["case_id"]
        counts[cid] = counts.get(cid, 0) + 1
        ak = r.get("attempt_key") or [None] * 10
        per_case.setdefault(cid, set()).add(ak[8])
        arms.add(ak[2])
        stages.add(ak[3])                   # v5: ak[3]=attempt_stage（原 ak[6] 是 case_id）
        repeats.add(ak[7])                  # ak[7]=repeat_idx
    actual = set(per_case.keys())
    if actual != expected:
        miss = expected - actual
        extra = actual - expected
        raise ValueError(f"不完整：probe case 集合不匹配（缺失 {len(miss)}，额外 {len(extra)}）")
    if arms != {expected_arm}:
        raise ValueError(f"不完整：probe arm 异常 {arms}，预期 {{expected_arm}}")
    if stages - {"diversity_probe"}:
        raise ValueError(f"不完整：attempt_stage 异常 {stages}")
    if repeats - {-1}:
        raise ValueError(f"不完整：repeat_idx 异常 {repeats}")
    for cid, idxs in per_case.items():
        if counts[cid] != N_SAMPLES or idxs != {0, 1, 2, 3, 4}:
            raise ValueError(f"不完整：probe {cid} 行数={counts[cid]} sample_idx={sorted(idxs)}")


def evaluate_t_switch(rate_r1: float, rate_r2) -> tuple:
    """T 冻结链（计划决策 4）：返回 (action, T)。r2 未运行传 None。"""
    if rate_r1 >= DIVERSITY_THRESHOLD:
        return ("freeze", DEFAULT_T)
    if rate_r2 is None:
        return ("probe_r2", DEFAULT_T)
    if rate_r2 >= DIVERSITY_THRESHOLD:
        return ("freeze", FALLBACK_T)
    return ("freeze_low_diversity", FALLBACK_T)


# ---------- 纯函数：调度 ----------

def validate_case_ids(case_ids: list) -> None:
    """v3 中优 6：case_id 早期校验，probe 前即拒绝畸形 dataset（不浪费 API 费用）。"""
    if len(case_ids) != EXPECTED_CASES:
        raise ValueError(f"6A1 要求 {EXPECTED_CASES} 个 case_id，实得 {len(case_ids)}")
    if len(set(case_ids)) != EXPECTED_CASES:
        raise ValueError(f"case_id 不唯一：{len(case_ids)} 项中仅 {len(set(case_ids))} 个唯一")


def validate_enrichment_entry(entry: dict, enriched_path: Path, expected_year: int,
                              expected_as_of_date: str) -> str:
    """v7 高优 4 + v8 阻断/高优 1：enrichment entry 实体校验纯函数（current 与 dev 共用）。
    返回 entry 的 output_sha256（供 manifest 记录）。
    校验：entry.year==expected_year、output_path 存在且 resolve 等于 enriched_path、
    实际文件 SHA==output_sha256、**实际 JSONL 行数==entry.row_count==EXPECTED_CASES**（v8 阻断）、
    as_of_date==expected_as_of_date 且非空（v8 高优 1：与顶层日期绑定）。"""
    if entry.get("year") != expected_year:
        raise ValueError(f"entry year 异常：{entry.get('year')} != {expected_year}")
    out_path = Path(entry["output_path"])
    if not out_path.is_file():
        raise ValueError(f"enriched 文件不存在：{out_path}")
    if out_path.resolve() != enriched_path.resolve():
        raise ValueError(f"output_path 与 enriched_path 不一致：{out_path} != {enriched_path}")
    actual_sha = sha256_file(out_path)
    if actual_sha != entry.get("output_sha256"):
        raise ValueError(f"output_sha256 不匹配：期望 {entry.get('output_sha256')}，实际 {actual_sha}")
    # v8 阻断：统计实际 JSONL 行数，不能只信 entry.row_count
    actual_rows = sum(1 for line in out_path.read_text(encoding="utf-8").splitlines()
                      if line.strip())
    if actual_rows != entry.get("row_count"):
        raise ValueError(f"实际行数与 row_count 不一致：{actual_rows} != {entry.get('row_count')}")
    if actual_rows != EXPECTED_CASES:
        raise ValueError(f"实际行数异常：{actual_rows} != {EXPECTED_CASES}")
    if not entry.get("as_of_date"):
        raise ValueError("as_of_date 为空")
    if entry["as_of_date"] != expected_as_of_date:
        raise ValueError(f"as_of_date 与顶层不一致：{entry['as_of_date']} != {expected_as_of_date}")
    return entry["output_sha256"]


def freeze_temperature(probe_info: dict, temperature: float) -> dict:
    """v8 高优 2：温度冻结纯函数（返回新字典，含 sample_temperature 字段）。
    生产主流程与闭环测试都调用；若生产删除该调用，测试直接失败（不再手工补写字段）。"""
    return {**probe_info, "sample_temperature": temperature}


def build_probe_slice(config: VoteConfig, case_ids: list, arm: str,
                      temperature: float) -> VoteSlice:
    return VoteSlice("probe", -1, arm, "diversity_probe", "probe",
                     tuple(case_ids[:PROBE_CASES]), N_SAMPLES, temperature,
                     PROBE_CASES * N_SAMPLES, PROBE_CAP)


def build_main_schedule(config: VoteConfig, case_ids: list,
                        sample_temperature: float = DEFAULT_T) -> list:
    if len(case_ids) != EXPECTED_CASES or len(set(case_ids)) != EXPECTED_CASES:
        raise ValueError(f"6A1 要求 {EXPECTED_CASES} 个唯一 case_id，"
                         f"实得 {len(case_ids)}（唯一 {len(set(case_ids))}）")
    group_a, group_b = split_ab_ba(case_ids, config.seed)
    groups = {"group_a": group_a, "group_b": group_b}
    schedule = []
    sample_count = 0
    anchor_count = 0
    for rep in range(config.repeats):
        for arm, stage, group, n, temp, sched in (
                (ARM_SAMPLE, "main", "group_a", N_SAMPLES, sample_temperature, 100),
                (ARM_ANCHOR, "anchor", "group_a", 1, 0.0, 20),
                (ARM_ANCHOR, "anchor", "group_b", 1, 0.0, 20),
                (ARM_SAMPLE, "main", "group_b", N_SAMPLES, sample_temperature, 100)):
            if arm == ARM_SAMPLE:
                cap = SAMPLE_CAPS[sample_count]
                sample_count += 1
            else:
                cap = ANCHOR_CAPS[anchor_count]
                anchor_count += 1
            schedule.append(VoteSlice("main", rep, arm, stage, group, groups[group],
                                      n, temp, sched, cap))
    if sum(s.hard_cap for s in schedule) != 660 + sum(ANCHOR_CAPS):
        raise ValueError("cap 和异常")
    return schedule


# ---------- 纯函数：完整性与严格聚合（审核阻断 2） ----------

def strict_rows_complete(rows: list, expected_case_ids: list, repeats: int) -> None:
    """决策数据完整性（审核阻断 2）：唯一 attempt 数精确、无重复、无额外 case/repeat/arm、
    每个预期 (case, repeat) 两臂齐全、终态合法。任一不过 → 上层映射 BLOCKED_INCOMPLETE。"""
    expected_cases = set(expected_case_ids)
    seen_sample, seen_anchor = set(), set()
    for r in rows:
        ak = r.get("attempt_key") or [None] * 10
        arm, rep, idx, cid = ak[2], ak[7], ak[8], r.get("case_id")
        if cid not in expected_cases:
            raise ValueError(f"额外 case：{cid}")
        if not isinstance(rep, int) or not (0 <= rep < repeats):
            raise ValueError(f"额外 repeat：{rep}（{cid}）")
        if r.get("terminal_state") not in TERMINAL_OK:
            raise ValueError(f"终态非法：{r.get('terminal_state')}（{cid}）")
        key = (cid, rep, idx)
        if not isinstance(idx, int) or not (0 <= idx < N_SAMPLES):
            raise ValueError(f"额外 sample_idx：{idx}（{cid}）")
        if arm == ARM_SAMPLE:
            if key in seen_sample:
                raise ValueError(f"重复行：采样 {key}")
            seen_sample.add(key)
        elif arm == ARM_ANCHOR:
            if idx != 0:
                raise ValueError(f"anchor 行 sample_idx 必须 0，实得 {idx}（{cid}）")
            if key in seen_anchor:
                raise ValueError(f"重复行：锚定 {key}")
            seen_anchor.add(key)
        else:
            raise ValueError(f"未知 arm：{arm}（{cid}）")
    expected_sample = {(c, rep, i) for c in expected_cases
                       for rep in range(repeats) for i in range(N_SAMPLES)}
    expected_anchor = {(c, rep, 0) for c in expected_cases for rep in range(repeats)}
    if seen_sample != expected_sample:
        miss_s = expected_sample - seen_sample
        extra_s = seen_sample - expected_sample
        raise ValueError(f"不完整：采样集合不匹配（缺失 {len(miss_s)}，额外 {len(extra_s)}）")
    if seen_anchor != expected_anchor:
        miss_a = expected_anchor - seen_anchor
        extra_a = seen_anchor - expected_anchor
        raise ValueError(f"不完整：锚定集合不匹配（缺失 {len(miss_a)}，额外 {len(extra_a)}）")


def aggregate_metrics(rows: list, expected_case_ids: list, repeats: int) -> dict:
    """按 (case, repeat) 聚合：vote5=strict_majority(5 样本)；single@T=sample_idx 0；锚定=anchor 行。
    unresolved/invalid/call_failed 计错；禁止跨 repeat（§5.2.6）。
    完整性不过 → ValueError（上层映射 BLOCKED_INCOMPLETE，不产出 verdict）。"""
    strict_rows_complete(rows, expected_case_ids, repeats)
    acc = {"vote5": [], "single_t": [], "anchor": []}
    per_repeat_delta1, per_repeat_delta2 = [], []
    unresolved = 0
    grid_t = {"both": 0, "vote5_only": 0, "single_t_only": 0, "neither": 0}
    grid_a = {"both": 0, "vote5_only": 0, "anchor_only": 0, "neither": 0}
    case_records = []
    for rep in range(repeats):
        cases = sorted(expected_case_ids)
        n_v5 = n_st = n_an = 0
        for cid in cases:
            srows = sorted((r for r in rows
                            if r["case_id"] == cid
                            and (r.get("attempt_key") or [None] * 10)[2] == ARM_SAMPLE
                            and (r.get("attempt_key") or [None] * 10)[7] == rep),
                           key=lambda r: r["attempt_key"][8])
            arow = next(r for r in rows
                        if r["case_id"] == cid
                        and (r.get("attempt_key") or [None] * 10)[2] == ARM_ANCHOR
                        and (r.get("attempt_key") or [None] * 10)[7] == rep)
            votes = [r["predicted_answer"] if r["terminal_state"] == "parsed" else None
                     for r in srows]
            v5 = strict_majority(votes)
            if v5 is None:
                unresolved += 1
            exp = srows[0]["expected_answer"]
            ok_v5 = v5 is not None and v5 == exp
            ok_st = (srows[0]["terminal_state"] == "parsed"
                     and srows[0]["predicted_answer"] == exp)
            ok_an = (arow["terminal_state"] == "parsed"
                     and arow["predicted_answer"] == exp)
            n_v5 += ok_v5; n_st += ok_st; n_an += ok_an
            grid_t["both" if ok_v5 and ok_st else
                   "vote5_only" if ok_v5 else
                   "single_t_only" if ok_st else "neither"] += 1
            grid_a["both" if ok_v5 and ok_an else
                   "vote5_only" if ok_v5 else
                   "anchor_only" if ok_an else "neither"] += 1
            case_records.append({
                "case_id": cid, "repeat_idx": rep,
                "domain": srows[0].get("domain", "unknown"),
                "votes": votes, "vote5": v5,
                "single_t": srows[0]["predicted_answer"]
                            if srows[0]["terminal_state"] == "parsed" else None,
                "anchor": arow["predicted_answer"]
                          if arow["terminal_state"] == "parsed" else None,
                "expected": exp, "unresolved": v5 is None,
                "vote5_correct": ok_v5, "single_t_correct": ok_st, "anchor_correct": ok_an,
            })
        n = len(cases)
        acc["vote5"].append(round(n_v5 / n, 4))
        acc["single_t"].append(round(n_st / n, 4))
        acc["anchor"].append(round(n_an / n, 4))
        per_repeat_delta1.append(round((n_v5 - n_st) / n * 100, 2))
        per_repeat_delta2.append(round((n_v5 - n_an) / n * 100, 2))
    total = len(expected_case_ids) * repeats
    from benchmark.reports.accuracy_stats import trimmed_mean
    acc_trimmed_mean = {arm: round(trimmed_mean(acc[arm], 0.1), 4)
                        for arm in ("vote5", "single_t", "anchor")}
    by_domain = {}
    for domain in sorted({r.get("domain", "unknown") for r in case_records}):
        d_recs = [r for r in case_records if r.get("domain", "unknown") == domain]
        dn = len(d_recs)
        v5 = sum(r["vote5_correct"] for r in d_recs) / dn
        st = sum(r["single_t_correct"] for r in d_recs) / dn
        an = sum(r["anchor_correct"] for r in d_recs) / dn
        by_domain[domain] = {
            "vote5": round(v5, 4), "single_t": round(st, 4), "anchor": round(an, 4),
            "delta1_pp": round((v5 - st) * 100, 2), "delta2_pp": round((v5 - an) * 100, 2),
            "n": dn,
        }
    return {
        "acc": acc,
        "per_repeat_delta1": per_repeat_delta1,
        "per_repeat_delta2": per_repeat_delta2,
        "delta1_pp": round(sum(per_repeat_delta1) / repeats, 2),
        "delta2_pp": round(sum(per_repeat_delta2) / repeats, 2),
        "acc_trimmed_mean": acc_trimmed_mean,
        "by_domain": by_domain,
        "unresolved_rate": round(unresolved / max(total, 1), 4),
        "four_grid_vote5_vs_single_t": grid_t,
        "four_grid_vote5_vs_anchor": grid_a,
        "case_records": case_records,
        "call_failed": sum(1 for r in rows if r.get("terminal_state") == "call_failed"),
    }


def gate_verdict(delta1_pp: float, delta2_pp: float) -> str:
    """设计 §5.3 dev gate。"""
    if delta1_pp >= 3.0:
        return "PROMOTE_CANDIDATE" if delta2_pp >= 0.0 else "AGGREGATION_EFFECT_ONLY"
    if delta1_pp <= -3.0:
        return "ROLLBACK"
    return "NON_INFERIOR"


def recheck_verdict(delta1_year: float, delta2_year: float) -> str:
    """设计 §5.3 复核（仅 2021）：双条件通过方确认。"""
    return "PROMOTE_CONFIRMED" if delta1_year >= 2.0 and delta2_year >= 0.0 \
        else "RECHECK_FAILED"


# ---------- 纯函数：成本代理（审核高优 5） ----------

def cost_metrics(per_case_chars: list, repeats: int = 3) -> dict:
    """成本代理（设计 §5.2.7 首类指标）：API 不返回 token usage，用 prompt 字符数 × 调用数 × repeats。
    vote5 = 5 调用/题/轮；single@T 与 anchor 各 1 调用/题/轮。
    v3 中优 5：arm_total_chars 乘 repeats，键名改 arm_total_chars_per_run。"""
    total = sum(per_case_chars)
    totals = {"vote5": total * N_SAMPLES * repeats, "single_t": total * repeats,
              "anchor": total * repeats}
    return {"metric": "prompt_chars_proxy",
            "note": "API 未返回 token usage；prompt 字符数 × 调用数 × repeats 为成本代理",
            "per_case_chars_trimmed_mean": round(trimmed_mean(per_case_chars, 0.1), 1),
            "arm_total_chars_per_run": totals,
            "cost_ratio_vote5_vs_single_t": round(totals["vote5"] / max(totals["single_t"], 1), 2),
            "cost_ratio_vote5_vs_anchor": round(totals["vote5"] / max(totals["anchor"], 1), 2)}


def _prompt_chars_per_case(enriched_rows: list) -> list:
    out = []
    for row in enriched_rows:
        rendered = render_chart_context(row, SCHEMA)
        out.append(len(format_direct_choice_prompt(row, chart_context_text=rendered)))
    return out


# ---------- 纯函数：dev 温度自动读取（审核阻断 3） ----------

def load_dev_temperature(dev_run_id: str, archive_dir: Path, provider: str, model: str,
                         approved_2024_dataset_sha: str) -> tuple:
    """复核温度来源（v4 高优 5 + v5 高优 4）：从已归档 dev manifest/summary 自动读取并核验 8 项，
    禁止人工转录。返回 (temperature, info)。archive_dir = PROJECT_ROOT/docs/phase6。
    v5 高优 4：approved_2024_dataset_sha 改必填（main 强制从 enrich_manifest 读取传入）。
    8 项：status==OK / verdict==PROMOTE_CANDIDATE / year==2024 / recheck==false /
    manifest run_id==dev_run_id / 温度 ∈ {0.4,1.0} / temperature_freeze==sample_temperature /
    dataset SHA 与已批准 2024 enriched manifest 对应；审计索引存在且 summary 比对通过。"""
    d = Path(archive_dir) / dev_run_id
    for name in ("manifest.json", "summary.json"):
        if not (d / name).exists():
            raise ValueError(f"dev 归档缺失：{d / name}")
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != "OK":
        raise ValueError(f"dev summary status 非 OK：{summary.get('status')}")
    if summary.get("verdict") != "PROMOTE_CANDIDATE":
        raise ValueError(f"dev verdict 非 PROMOTE_CANDIDATE：{summary.get('verdict')}")
    if summary.get("year") != 2024:
        raise ValueError(f"dev summary year 非 2024：{summary.get('year')}")
    if summary.get("recheck") is not False:
        raise ValueError(f"dev summary recheck 非 false：{summary.get('recheck')}")
    if manifest.get("run_id") != dev_run_id:
        raise ValueError(f"dev manifest run_id 不一致：{manifest.get('run_id')} != {dev_run_id}")
    for k, expect in (("profile_id", PROFILE_ID), ("chart_schema_version", SCHEMA),
                      ("provider", provider), ("model", model)):
        if manifest.get(k) != expect:
            raise ValueError(f"dev manifest {k} 不一致：{manifest.get(k)} != {expect}")
    temperature = float(manifest["sample_temperature"])
    if temperature not in (DEFAULT_T, FALLBACK_T):
        raise ValueError(f"dev 温度非法 {temperature}，只能 {DEFAULT_T} 或 {FALLBACK_T}")
    tfreeze = manifest.get("temperature_freeze", {})
    # v6 高优 4：sample_temperature 必存且一致（去掉条件跳过，不允许静默通过）
    if "sample_temperature" not in tfreeze:
        raise ValueError(f"dev temperature_freeze 缺 sample_temperature 字段")
    if abs(float(tfreeze["sample_temperature"]) - temperature) > 0.001:
        raise ValueError(f"temperature_freeze.sample_temperature({tfreeze['sample_temperature']})"
                         f" 与 sample_temperature({temperature}) 不一致")
    dataset_sha = manifest.get("dataset_sha256")
    if dataset_sha != approved_2024_dataset_sha:
        raise ValueError(f"dataset SHA 与已批准 2024 enriched manifest 不对应")
    audit_index = d / "audit_index.json"
    if not audit_index.exists():
        raise ValueError(f"dev 审计索引缺失：{audit_index}")
    ai = json.loads(audit_index.read_text(encoding="utf-8"))
    if ai.get("mode") != "vote":
        raise ValueError(f"dev 审计索引 mode 非 vote：{ai.get('mode')}")
    sc = ai.get("summary_check", {})
    if sc.get("status") != "PASS":
        raise ValueError(f"dev 审计 summary_check 非 PASS：{sc.get('status')}")
    # v6 高优 5：summary_sha256 绑定当前 summary.json 内容（审计后修改 summary 会被发现）
    summary_sha = sha256_file(d / "summary.json")
    if sc.get("summary_sha256") != summary_sha:
        raise ValueError(f"dev 审计 summary_sha256 与当前 summary.json 不一致")
    # v6 高优 5：recomputed 的 Δ1/Δ2 与当前 summary 一致
    recomputed = sc.get("recomputed", {})
    if abs(float(recomputed.get("delta1_pp", 0)) - float(summary.get("delta1_pp", 0))) > 0.01:
        raise ValueError(f"dev 审计 recomputed Δ1 与 summary 不一致")
    if abs(float(recomputed.get("delta2_pp", 0)) - float(summary.get("delta2_pp", 0))) > 0.01:
        raise ValueError(f"dev 审计 recomputed Δ2 与 summary 不一致")
    if ai.get("dataset_sha256") != dataset_sha:
        raise ValueError(f"dev 审计索引 dataset_sha256 不一致")
    if ai.get("run_id") != dev_run_id:
        raise ValueError(f"dev 审计索引 run_id 不一致：{ai.get('run_id')}")
    if ai.get("year") != 2024:
        raise ValueError(f"dev 审计索引 year 非 2024：{ai.get('year')}")
    info = {"verdict": summary["verdict"], "dev_run_id": dev_run_id,
            "dev_manifest_sha256": sha256_file(d / "manifest.json"),
            "dataset_sha256": dataset_sha, "temperature": temperature}
    return temperature, info


# ---------- 离线 gate / 真实边界 ----------

def offline_gate(config: VoteConfig) -> list:
    """legacy_v0 单上下文：可见性矩阵 + 泄漏扫描（无网络）。"""
    failures = []
    if not config.enriched_path.exists():
        return [f"enriched 文件缺失: {config.enriched_path}"]
    profile = resolve_profile(PROFILE_ID, SCHEMA)
    for row in load_jsonl(config.enriched_path):
        cid = row.get("case_id")
        rendered = render_chart_context(row, SCHEMA)
        for v in assert_visibility(rendered, profile, SCHEMA):
            failures.append(f"{cid}: {v}")
        prompt = format_direct_choice_prompt(row, chart_context_text=rendered)
        for hit in scan_prompt_for_leaks(prompt, row):
            failures.append(f"{cid}: leak {hit.kind} {hit.detail}")
    return failures


def run_slice(slice_run: VoteSlice, config: VoteConfig, **kwargs) -> object:
    """真实边界：子进程调用 runner（emit_samples / 单轮锚定）。--repeat-idx 原样透传。"""
    run_dir = (config.root / slice_run.arm / "runs" / config.run_id
               / f"slice_{slice_run.purpose}_{slice_run.repeat_idx}_{slice_run.group}")
    run_dir.mkdir(parents=True, exist_ok=True)
    ids_file = run_dir / "case_ids.json"
    ids_file.write_text(json.dumps(list(slice_run.case_ids), ensure_ascii=False),
                        encoding="utf-8")
    argv = [
        sys.executable, "-m", "benchmark.runners.run_benchmark",
        "--dataset", str(config.enriched_path),
        "--model-runner", "--provider", config.provider, "--model", config.model,
        "--profile", PROFILE_ID, "--chart-schema-version", SCHEMA,
        "--arm", slice_run.arm, "--attempt-stage", slice_run.stage,
        "--as-of-date", config.as_of_date,               # v6 高优 7
        "--repeat-idx", str(slice_run.repeat_idx),
        "--case-ids-file", str(ids_file),
        "--case-details-jsonl", str(run_dir / "detail.jsonl"),
        "--output-dir", str(run_dir),
        "--scheduled-calls", str(slice_run.scheduled_calls),
        "--hard-cap", str(slice_run.hard_cap),
        "--temperature", "0.0",
        "--n-samples", str(slice_run.n_samples),
        "--sample-temperature", str(slice_run.temperature),
    ]
    if slice_run.n_samples > 1:
        argv += ["--aggregate", "emit_samples"]
    if config.resume:
        argv.append("--resume")
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=PROJECT_ROOT)
    calls_attempted = 0
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        try:
            calls_attempted = int(json.loads(summary_path.read_text(encoding="utf-8"))
                                  .get("calls_attempted") or 0)
        except Exception:
            calls_attempted = 0
    if not calls_attempted:
        events_path = run_dir / "detail.events.jsonl"
        if events_path.exists():
            calls_attempted = sum(
                1 for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line).get("kind") == "call_attempt")
    return type("SliceResult", (), {"exit_code": proc.returncode, "records": [],
                                    "calls_attempted": calls_attempted,
                                    "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]})


def run_vote(config: VoteConfig, schedule: list, slice_runner=None) -> dict:
    """与 6A0 run_ablation 同语义：schedule 调用方传入；BudgetLedger 按 slice_id 幂等。"""
    runner = slice_runner or (lambda s, **kw: run_slice(s, config, **kw))
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    for s in schedule:
        slice_id = f"{s.purpose}_{s.repeat_idx}_{s.arm}_{s.group}"
        try:
            attempted = ledger.attempted_for(slice_id)
            overflow = (ledger.total_attempted() + (s.hard_cap - attempted)
                        > config.stage_hard_cap)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if attempted > s.hard_cap:
            return {"status": "BLOCKED_INCOMPLETE",
                    "reason": f"budget ledger inconsistent: {slice_id}"}
        if overflow:
            return {"status": "FAILED",
                    "reason": f"stage budget overflow at {slice_id}",
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx, "group": s.group}}
        result = runner(s, scheduled_calls=s.scheduled_calls, hard_cap=s.hard_cap)
        try:
            ledger.record(slice_id, s.hard_cap, getattr(result, "calls_attempted", 0) or 0)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if result.exit_code == 3:
            return {"status": "BLOCKED_INCOMPLETE",
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx, "group": s.group}}
        if result.exit_code != 0:
            return {"status": "FAILED", "exit_code": result.exit_code,
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx}}
    return {"status": "OK", "attempted": ledger.total_attempted()}


def _load_run_rows(config: VoteConfig) -> list:
    rows = []
    for arm in (ARM_SAMPLE, ARM_ANCHOR):
        runs_dir = config.root / arm / "runs" / config.run_id
        if not runs_dir.exists():
            continue
        for detail in sorted(runs_dir.glob("slice_main_*/detail.jsonl")):
            for line in detail.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def _build_manifest(config: VoteConfig, executed_schedule: list, attempted: int,
                    temperature: float, probe_info: dict, case_ids: list,
                    dataset_sha256: str, groups_sha256: str,
                    dev_dataset_sha256: str = "") -> dict:
    """v3 阻断 3：manifest 构造纯函数（不读磁盘，便于测试）。
    executed_schedule 含 probe（[probe_r1, optional probe_r2, *main]），
    budget_reconciliation 分别记录 probe/main scheduled、attempted_total、registered_hard_cap。
    v6 阻断 1：dev_dataset_sha256 记录 2024 批准 SHA（复核模式才非空）。"""
    probe_scheduled = sum(s.scheduled_calls for s in executed_schedule
                         if getattr(s, "group", "") == "probe")
    main_scheduled = sum(s.scheduled_calls for s in executed_schedule
                         if getattr(s, "group", "") != "probe")
    return {
        "run_id": config.run_id, "seed": config.seed, "profile_id": PROFILE_ID,
        "chart_schema_version": SCHEMA, "sample_temperature": temperature,
        "as_of_date": config.as_of_date,
        "temperature_freeze": probe_info,
        "dataset_sha256": dataset_sha256,
        "dev_dataset_sha256": dev_dataset_sha256 or dataset_sha256,  # v6 阻断 1
        "case_groups_sha256": groups_sha256,
        "slice_order": [f"{s.arm}:{s.repeat_idx}:{s.group}" for s in executed_schedule],
        "budget_reconciliation": {
            "probe_scheduled": probe_scheduled,
            "main_scheduled": main_scheduled,
            "scheduled_total": probe_scheduled + main_scheduled,
            "attempted_total": attempted,
            "registered_hard_cap": config.stage_hard_cap,
        },
        "provider": config.provider, "model": config.model, "code_hash": _git_head(),
        "workspace_state": _collect_workspace_state(),
        "reproducibility_note": "请求不携带 seed；复现依赖 detail 行 raw_answer 与调用顺序",
    }


def write_report(config: VoteConfig, case_ids: list, temperature: float,
                 probe_info: dict, executed_schedule: list, enriched_rows: list,
                 attempted: int, recheck: bool = False) -> dict:
    """首类指标全量产出（v3 中优 5）：准确率/Δ/四格/unresolved/成本/逐题明细/对账/
    acc_trimmed_mean/by_domain。executed_schedule 含 probe（v3 阻断 3）。"""
    rows = _load_run_rows(config)
    try:
        m = aggregate_metrics(rows, case_ids, config.repeats)
    except ValueError as e:
        return {"run_id": config.run_id, "status": "BLOCKED_INCOMPLETE",
                "reason": f"完整性检查未过：{e}"}
    verdict = (recheck_verdict(m["delta1_pp"], m["delta2_pp"]) if recheck
               else gate_verdict(m["delta1_pp"], m["delta2_pp"]))
    pollution = m["call_failed"] > len(case_ids) * 0.05
    cost = cost_metrics(_prompt_chars_per_case(enriched_rows), repeats=config.repeats)
    out_dir = ARCHIVE_ROOT / config.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"run_id": config.run_id, "year": config.year, "status": "OK",
               "sample_temperature": temperature, "recheck": recheck,
               **{k: v for k, v in m.items() if k != "case_records"},
               "cost": cost, "verdict": verdict, "pollution_flag": pollution,
               "stage_hard_cap": config.stage_hard_cap}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    with (out_dir / "case_details.jsonl").open("w", encoding="utf-8") as f:
        for rec in m["case_records"]:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    group_a, group_b = split_ab_ba(case_ids, config.seed)
    groups_sha256 = sha256_file(_write_tmp_json(config.root / "budget"
                                                / f"{config.run_id}_groups.json",
                                                {"group_a": list(group_a),
                                                 "group_b": list(group_b)}))
    manifest = _build_manifest(config, executed_schedule, attempted, temperature,
                               probe_info, case_ids,
                               dataset_sha256=sha256_file(config.enriched_path),
                               groups_sha256=groups_sha256,
                               dev_dataset_sha256=config.dev_dataset_sha256)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    lines = [
        f"# 6A1 严格投票报告（{config.run_id}，{config.year}{'，2021 复核' if recheck else ''}）",
        "",
        f"- T = {temperature}（冻结链：{json.dumps(probe_info, ensure_ascii=False)}）",
        f"- Δ1（vote5−single@T，同源）= {m['delta1_pp']}pp（每 repeat：{m['per_repeat_delta1']}）",
        f"- Δ2（vote5−single@0，锚定）= {m['delta2_pp']}pp（每 repeat：{m['per_repeat_delta2']}）",
        f"- 准确率 vote5/single@T/anchor：{m['acc']['vote5']} / {m['acc']['single_t']} / {m['acc']['anchor']}",
        f"- unresolved 率：{m['unresolved_rate']}（>20% 为显著发现，不否决）",
        f"- 四格 vote5×single@T：{json.dumps(m['four_grid_vote5_vs_single_t'], ensure_ascii=False)}",
        f"- 四格 vote5×anchor：{json.dumps(m['four_grid_vote5_vs_anchor'], ensure_ascii=False)}",
        f"- 成本代理（{cost['metric']}）：vote5/single@T/anchor 总字符 = "
        f"{cost['arm_total_chars_per_run']}；比值 {cost['cost_ratio_vote5_vs_single_t']} / "
        f"{cost['cost_ratio_vote5_vs_anchor']}；trimmed mean {cost['per_case_chars_trimmed_mean']}",
        f"- 准确率 trimmed mean（附列，不入 gate）：{m['acc_trimmed_mean']}",
        f"- by_domain（设计 §2.1）：{json.dumps(m['by_domain'], ensure_ascii=False)}",
        f"- call_failed：{m['call_failed']}（污染标注：{'是' if pollution else '否'}）",
        f"- 判定：**{verdict}**",
        "",
        "如实声明：API 未返回 token usage（成本为 prompt 字符 × 调用数代理）；采样不可由 seed 复现；"
        "40 题样本，2 题即 5pp，禁止过度表述。逐题明细见 case_details.jsonl。",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def _write_tmp_json(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 6A1 严格投票编排器")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--root", type=Path, default=Path(".tmp/phase6"))
    parser.add_argument("--recheck", action="store_true",
                        help="2021 复核模式：无 probe，必须 --dev-run-id")
    parser.add_argument("--dev-run-id", default=None,
                        help="复核模式必填：dev 运行归档（docs/phase6/<id>/）")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="v6 高优 6：允许实验范围文件 dirty（仅诊断，正式命令禁止）")
    args = parser.parse_args(argv)

    # v7 高优 5：--allow-dirty 与 --yes 互斥（allow-dirty 只能离线诊断，不进模型调用路径）
    if args.allow_dirty and args.yes:
        parser.error("--allow-dirty cannot be combined with --yes")

    # v6 高优 6：workspace clean 在任何 API 调用前检查（采集失败也 fail-closed）
    if not args.allow_dirty:
        workspace = _collect_workspace_state()
        if "collect_error" in workspace or not workspace.get("clean"):
            print(json.dumps({"status": "WORKSPACE_DIRTY", "workspace": workspace},
                             ensure_ascii=False))
            return 2

    # 年份封死（审核阻断 3）：先于任何数据读取。dev 仅 2024；复核仅 2021；2022/2023 密封。
    if args.recheck and args.year != 2021:
        print("复核模式仅允许 --year 2021（2022/2023 密封，设计 §5.3）")
        return 2
    if not args.recheck and args.year != 2024:
        print("dev 模式仅允许 --year 2024（2022/2023 密封，设计 §5.3）")
        return 2

    enriched = args.root / "datasets" / f"baziqa_contest8_{args.year}_holdout_enriched.jsonl"
    hard_cap = 800 if args.recheck else 910
    # v5 阻断 3 + v6 阻断 1：从 enrich_manifest.json 读取 current_entry(args.year) 与 dev_entry(2024)
    if not enriched.is_file():                       # v6 高优 3：前置存在检查
        print(json.dumps({"status": "ENRICHED_MISSING", "path": str(enriched)},
                         ensure_ascii=False))
        return 2
    enrich_manifest = args.root / "enrich_manifest.json"
    if not enrich_manifest.exists():
        print(json.dumps({"status": "ENRICH_MANIFEST_MISSING",
                          "path": str(enrich_manifest)}, ensure_ascii=False))
        return 2
    em = json.loads(enrich_manifest.read_text(encoding="utf-8"))
    current_entry = next((e for e in em.get("entries", []) if e.get("year") == args.year), None)
    if not current_entry:
        print(json.dumps({"status": "ENRICH_ENTRY_MISSING", "year": args.year},
                         ensure_ascii=False))
        return 2
    dev_entry = next((e for e in em.get("entries", []) if e.get("year") == 2024), None)
    if not dev_entry:                                 # v6 阻断 1：dev_entry 必须存在（复核模式用）
        print(json.dumps({"status": "DEV_ENTRY_MISSING"}, ensure_ascii=False))
        return 2
    # v7 高优 4 + v8 阻断/高优 1：先取顶层 as_of_date，传入 validate_enrichment_entry
    top_as_of_date = em.get("as_of_date", "")
    if not top_as_of_date:
        print(json.dumps({"status": "TOP_AS_OF_DATE_EMPTY"}, ensure_ascii=False))
        return 2
    try:
        current_sha = validate_enrichment_entry(current_entry, enriched, args.year, top_as_of_date)
        if args.year == 2024:
            dev_sha = current_sha                     # 开发年度相同，复用结果
        else:
            dev_enriched = args.root / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
            dev_sha = validate_enrichment_entry(dev_entry, dev_enriched, 2024, top_as_of_date)
    except ValueError as e:
        print(json.dumps({"status": "ENRICH_ENTRY_INVALID", "reason": str(e)},
                         ensure_ascii=False))
        return 2
    as_of_date = top_as_of_date                       # v8 高优 1：顶层日期已在 entry 校验绑定
    # v6 阻断 1：approved_2024_dataset_sha 始终取 dev_entry(2024)，不用 current_entry
    approved_dataset_sha = dev_sha
    config = VoteConfig(run_id=args.run_id, year=args.year, root=args.root,
                        enriched_path=enriched, provider=args.provider,
                        model=args.model, stage_hard_cap=hard_cap,
                        as_of_date=as_of_date,
                        dev_dataset_sha256=approved_dataset_sha)
    failures = offline_gate(config)
    if failures:
        print(json.dumps({"status": "OFFLINE_GATE_FAILED", "failures": failures[:20]},
                         ensure_ascii=False))
        return 1
    enriched_rows = list(load_jsonl(enriched))
    case_ids = [str(r["case_id"]) for r in enriched_rows]
    try:
        validate_case_ids(case_ids)
    except ValueError as e:
        print(json.dumps({"status": "INVALID_CASE_IDS", "reason": str(e)},
                         ensure_ascii=False))
        return 2
    group_a, _ = split_ab_ba(case_ids, config.seed)
    probe_slices = []

    probe_info = {"mode": "recheck" if args.recheck else "dev"}
    if args.recheck:
        if not args.dev_run_id:
            print("复核模式必须 --dev-run-id（从 dev 归档自动读取温度，禁止人工转录）")
            return 2
        try:
            temperature, info = load_dev_temperature(
                args.dev_run_id, archive_dir=ARCHIVE_ROOT,
                provider=config.provider, model=config.model,
                approved_2024_dataset_sha=approved_dataset_sha)
        except ValueError as e:
            print(str(e))
            return 2
        probe_info.update(info)
    else:
        r1 = build_probe_slice(config, group_a, "probe_r1", DEFAULT_T)
        print(f"probe_r1：{r1.scheduled_calls} 次调用（cap {r1.hard_cap}）")
        if not args.yes:
            print("加 --yes 确认预算后执行")
            return 0
        result = run_vote(config, [r1])
        probe_slices.append(r1)
        if result["status"] != "OK":
            print(json.dumps(result, ensure_ascii=False))
            return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
        r1_rows = []
        for detail in (config.root / "probe_r1" / "runs" / config.run_id
                       ).glob("slice_probe_*/detail.jsonl"):
            r1_rows += [json.loads(x) for x in
                        detail.read_text(encoding="utf-8").splitlines() if x.strip()]
        try:
            probe_rows_complete(r1_rows, list(group_a[:PROBE_CASES]), "probe_r1")
        except ValueError as e:
            print(json.dumps({"status": "BLOCKED_INCOMPLETE", "reason": str(e)},
                             ensure_ascii=False))
            return 3
        rate1 = diversity_rate(r1_rows, list(group_a[:PROBE_CASES]))
        action, temperature = evaluate_t_switch(rate1, None)
        probe_info.update({"rate_r1": rate1, "action_r1": action})
        if action == "probe_r2":
            r2 = build_probe_slice(config, group_a, "probe_r2", FALLBACK_T)
            result = run_vote(config, [r2])
            probe_slices.append(r2)
            if result["status"] != "OK":
                print(json.dumps(result, ensure_ascii=False))
                return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
            r2_rows = []
            for detail in (config.root / "probe_r2" / "runs" / config.run_id
                           ).glob("slice_probe_*/detail.jsonl"):
                r2_rows += [json.loads(x) for x in
                            detail.read_text(encoding="utf-8").splitlines() if x.strip()]
            try:
                probe_rows_complete(r2_rows, list(group_a[:PROBE_CASES]), "probe_r2")
            except ValueError as e:
                print(json.dumps({"status": "BLOCKED_INCOMPLETE", "reason": str(e)},
                                 ensure_ascii=False))
                return 3
            rate2 = diversity_rate(r2_rows, list(group_a[:PROBE_CASES]))
            action, temperature = evaluate_t_switch(rate1, rate2)
            probe_info.update({"rate_r2": rate2, "action_r2": action})
        print(f"T 冻结为 {temperature}（{probe_info}）")
    probe_info = freeze_temperature(probe_info, temperature)      # v8 高优 2：纯函数抽取

    schedule = build_main_schedule(config, case_ids, sample_temperature=temperature)
    executed_schedule = [*probe_slices, *schedule]
    total = sum(s.scheduled_calls for s in executed_schedule)
    print(f"主实验：{total} 次调用（cap {sum(s.hard_cap for s in executed_schedule)}），"
          f"切片 {len(executed_schedule)}，T={temperature}")
    if not args.yes:
        print("加 --yes 确认预算后执行")
        return 0
    result = run_vote(config, schedule)
    if result["status"] != "OK":
        print(json.dumps(result, ensure_ascii=False))
        return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
    summary = write_report(config, case_ids, temperature, probe_info,
                           executed_schedule, enriched_rows,
                           attempted=result.get("attempted", 0), recheck=args.recheck)
    if summary.get("status") == "BLOCKED_INCOMPLETE":
        print(json.dumps(summary, ensure_ascii=False))
        return 3
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

注意 `build_main_schedule` 里采样臂 cap 取法：按已排采样切片数索引 `SAMPLE_CAPS`（0..5）；锚定臂按序取 `ANCHOR_CAPS`。测试 `test_main_schedule_order_and_caps` 锁定 cap 和 = 660+140。

- [ ] **Step 4：运行确认全绿 + 4 组回归**。

- [ ] **Step 5：提交（精确路径）**

```powershell
git add scripts/run_phase6_6a1_ablation.py scripts/build_phase6_audit_index.py tests/test_phase6_6a1_vote.py
git commit -m "feat(phase6): 6A1 编排器（probe T 冻结 + AB/BA + 全量完整性 + 严格聚合 + 成本 + 年份封死）"
```

---

## Task 4：真实执行——dev 2024（scheduled ≤820 / hard_cap 910）

**前置核对（全部满足才执行）**：Task 1–3 合入且 4 组回归全绿；**v5 门禁：完整 dev 环境**（`pip install -r requirements-dev.txt` 后 `python -m pytest tests/ -q -m "not e2e"` 全绿，含 fastapi 相关测试）；`.env` 含 `DEEPSEEK_API_KEY`；`.tmp/phase6/enrich_manifest.json` 在位且 2024 entry 通过校验（40 题、SHA 匹配）；**实验范围文件（`scripts/run_phase6_6a1_ablation.py`、`scripts/build_phase6_audit_index.py`、`benchmark/runners/run_benchmark.py`、`benchmark/runners/self_consistency.py`）无未提交修改**，scoped dirty 状态与文件 SHA 写入 manifest（`workspace_state` 字段）。

- [ ] **Step 1：probe（50 次真实调用，可先无 --yes 干跑看预算）**

```powershell
python scripts/run_phase6_6a1_ablation.py --run-id 6a1-2024-001 --year 2024 --yes
```

预期：离线 gate 通过；probe_r1 完成且 `probe_rows_complete` 通过；打印 T 冻结结果（`rate_r1` 与 action；若触发 probe_r2 再 50 次）。probe 完整性不过 → exit 3（BLOCKED_INCOMPLETE），排查后续跑，不得进入主实验。

- [ ] **Step 2：主实验（720 次真实调用，接续同一命令自动完成；中断重跑同一命令即可，resume 幂等）**

预期产物：`docs/phase6/6a1-2024-001/{report.md, summary.json, manifest.json, case_details.jsonl}`。完整性不过 → exit 3，不产出 verdict。

- [ ] **Step 3：审计索引归档**

```powershell
python scripts/build_phase6_audit_index.py --run-id 6a1-2024-001 --year 2024 --arms vote5_samples,anchor_single0 --mode vote
git add docs/phase6/6a1-2024-001
git commit -m "docs(phase6): 6A1 2024 dev gate 运行结果（verdict=<实际判定>，T=<冻结值>）"
```

审计复算（题级投票）默认与 `summary.json` 自动比对（v4 阻断 1：`--mode vote` 默认检查，不一致 exit 2）；不一致 -> 排查，不得归档。

- [ ] **Step 4：判读（设计 §5.3）**

- `PROMOTE_CANDIDATE` → 进入 Task 5（2021 复核）；
- `AGGREGATION_EFFECT_ONLY` / `NON_INFERIOR` / `ROLLBACK` → 不进入 Task 5，protocol=single 写入结论，6B1 以 single 继续（设计 §10 不整体停工）。

## Task 5（条件触发）：2021 复核（scheduled 720 / hard_cap 800）

**仅当 Task 4 判 PROMOTE_CANDIDATE 才执行。** 温度由 `--dev-run-id` 自动读取 dev 归档并核验（verdict/profile/schema/provider/model/SHA-256），禁止人工转录。

- [ ] **Step 1：复核运行**

```powershell
python scripts/run_phase6_6a1_ablation.py --run-id 6a1-2021-001 --year 2021 --recheck --dev-run-id 6a1-2024-001 --yes
```

- [ ] **Step 2：归档与判读**

```powershell
python scripts/build_phase6_audit_index.py --run-id 6a1-2021-001 --year 2021 --arms vote5_samples,anchor_single0 --mode vote
git add docs/phase6/6a1-2021-001
git commit -m "docs(phase6): 6A1 2021 复核结果（verdict=<实际判定>）"
```

- `PROMOTE_CONFIRMED`（Δ1_year ≥ +2pp 且 Δ2_year ≥ 0）→ vote5 成为后续臂默认协议；
- `RECHECK_FAILED` → 不设默认，结论如实记录，6B1 以 protocol=single 继续。
- **2022 不在本阶段打开**（设计 §5.3：杜绝选择性验证）；CLI 已硬封（非 2024/2021 一律 exit 2）。

---

## 设计 gate 映射表（设计 v6 ↔ 本计划任务 ↔ 验证）

| 设计条目 | 位置 | 任务 | 验证 |
| --- | --- | --- | --- |
| T 冻结 0.4 / 多样性试测 / 切换 1.0 | §5.2.1-2 | Task 3 | `diversity_rate`（仅合法 parsed）/`evaluate_t_switch` 单测 + 真实 probe |
| probe 样本作废与完整性 | §5.2.2 / 审核阻断 4 | Task 3 | `probe_rows_complete`（<10 题/重复/缺样本 → BLOCKED） |
| 锚定臂同时间窗 single@0 | §5.2.3 | Task 2/3 | `--attempt-stage` 键测试 + AB/BA 顺序测试 |
| strict_majority ≥3/5、无破平局、invalid 占分母 | §5.2.4 | Task 1 | 8 条边界单测（3/1/1、2/2/1、2/1/1/1、None 分母等） |
| 同源配对 single@T=sample0；原始响应持久化 | §5.2.5 | Task 2/3 | emit 行 sample_idx 测试；`raw_response_path` 沿用 |
| repeats 内聚合、禁止 15 次再投票 | §5.2.6 | Task 3 | `test_no_cross_repeat_aggregation` |
| 完整性不过 → BLOCKED_INCOMPLETE | §4.4.2 / 审核阻断 2 | Task 3 | `strict_rows_complete` 7 条异常场景 + `test_aggregate_blocked_on_incomplete` + write_report 不产出 verdict |
| 首类指标四件套 + trimmed mean 附列 | §5.2.7 / §2.1 | Task 3 | 四格表/unresolved/`cost_metrics`/`case_records` 字段测试；报告字段 |
| 审计复算题级投票（非按行） | 6A0 收口延展 / 审核阻断 1 | Task 3/4/5 | `recompute_vote_accuracy` + `test_recompute_differs_from_per_row`；归档一致方可 commit |
| dev gate 四分支 verdict | §5.3 | Task 3/4 | `gate_verdict` 边界（+3/−3、Δ2 符号） |
| 2021 复核双条件、2022/2023 密封 | §5.3 / 审核阻断 3 | Task 3/5 | `TestYearSeal` 四种错误组合；`recheck_verdict` 单测；CLI 硬性封死 |
| 复核温度自动读取禁止人工转录 | 审核阻断 3 | Task 3/5 | `TestDevRunId`（读取/非 PROMOTE 拒/配置不一致拒） |
| 预算双列 820/910、720/800 | §8 | Task 3 | `build_main_schedule` cap 和断言 + BudgetLedger 幂等测试 |
| attempt_stage 入 resume manifest | 审核高优 6 / 决策 7 反转 | Task 2 | manifest 字段测试 + stage 变更 resume 拒绝测试 |
| BLOCKED_INCOMPLETE 不得决策 | §4.4.2 / §10 | Task 3 | exit 3 → BLOCKED 测试；判读步骤明示 |
| unresolved >20% 显著发现不否决 | §5.3 | Task 3 | 报告字段 + 测试 |

## 执行纪律（与 6A0 计划同款，执行代理必读）

1. **TDD**：每任务先写失败测试并运行确认失败，再实现；不回改测试迁就实现。
2. **git 纪律**：`git add` 只列该任务精确路径；禁止 `git add -A` / `git add tests/` / `git add .`。
3. **回归（4 组，命令固定）**：

```powershell
$env:HF_HUB_OFFLINE=1; $env:TRANSFORMERS_OFFLINE=1
# g1：本计划新增/改动测试
python -m pytest tests/test_strict_vote.py tests/test_phase6_emit_samples.py tests/test_phase6_6a1_vote.py -q > .tmp/g1.txt
# g2：runner 与投票原语回归
python -m pytest tests/test_benchmark_runner.py -q > .tmp/g2.txt
# g3：Phase 6 设施（profile/泄漏/上下文/审计/6A0 编排器）回归
python -m pytest tests/ -k "phase6 or profile or leak or chart_context or audit or 6a0" -q > .tmp/g3.txt
# g4：core regression（v4 高优 6：不再称"全量"；保留 4 个 fastapi 缺失模块忽略并明确标注；
#      完整环境 pip install fastapi 后跑 `python -m pytest tests/ -q -m "not e2e"` 才称"全量"）
python -m pytest tests/ -q -m "not e2e" --ignore=tests/test_api.py --ignore=tests/test_clients_api.py --ignore=tests/test_rate_limit.py --ignore=tests/test_visualization_api.py -p no:cacheprovider > .tmp/g4.txt
```

4. **不伪造运行结果**：`docs/phase6/<run_id>/` 与 `.tmp/phase6/**` 由真实运行生成；实现阶段只写代码与测试。
5. **设计缺口处理**：第三次温度切换、probe 选题规则等——按计划 §1 决策记录呈现，不发明、不静默放宽；决策 7 反转（attempt_stage 入 manifest）已在 §1 登记。
6. **真实调用纪律**：Task 4/5 涉及真实 API 费用；先 probe 小步验证再主实验；中断重跑同一命令（resume 幂等）；任何 BLOCKED_INCOMPLETE（含完整性/probe 完整性/预算）排查后续跑，不得进入决策。
7. **密钥纪律**：`DEEPSEEK_API_KEY` 只读 `.env`；日志/报告/manifest 不得出现密钥。
