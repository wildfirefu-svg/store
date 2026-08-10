# Phase 7 设计 v2.3：MingLi-Bench 完整集（160 题）冻结基线测量

**日期：** 2026-08-10
**状态：** v2.3（按 v2.2 复审结论修订：`chart_case_id` 缺失拒绝限定 `mingli_official_cot_astro`、`dual` 与 `controlled_retest` 一并入 vocabulary 兼容 6B2），待确认后进入 writing-plans
**修订历史：** v1（草案）→ v2（执行链与设计契约闭环）→ v2.1（双主键、`--ziwei-arm` 禁令、精确 profile 条件、单一 slice 状态机、独立 retest 产物与全局预算、完整性硬门、smoke 量化、receipt 补全、model_label、指纹列文件）→ v2.2（`chart_case_id` detail 显式写入与交叉验证、网络重试次数口径修正、`ATTEMPT_STAGES` fail-closed 校验、smoke 逐 attempt key 对账）→ v2.3（`chart_case_id` 门禁限定 profile 防 BaziQA 全局回归、`dual` 保留入 vocabulary 防 6B2 链路断裂）
**适用范围：** 用 Phase 6 冻结的推理配置，对 MingLi-Bench 完整 160 题做一次**纯测量**基线
**前置：** Phase 6 已关闭（最终协议 single B1-a′）；MingLi 基础设施部分存在（fetch 脚本 / adapter / 官方 prompt profile / Phase 1 前 20 题历史 smoke）

---

## 1. 背景与动机

- 仓库目前只有 MingLi-Bench 官方 2025 年前 20 题的**历史链路 smoke（60%）**——该次运行使用 `--shuffle-options --shuffle-seed 42` 且未启用当前官方 profile（`docs/PHASE1_BASELINE_SUMMARY.md` §3.3），只能称"历史链路 smoke"，不能作为同协议小样本结果，更不能代表完整 160 题指标。
- Phase 6 四条协议层候选路线全部闭合，最终操作协议冻结为 single B1-a′（v4-flash non-thinking，T=0，单次调用）。
- 本阶段回答：**冻结推理配置在 MingLi-Bench 完整集上的表现是多少**，与 BaziQA holdout（~29–32%）形成跨基准对照。
- **只做测量**：不新增 prompt、不接 RAG、不加规则、不调参。知识库蒸馏（滴天髓/子平真诠/三命通会）是独立路线，其产物不得混入本基线。

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 冻结 MingLi-Bench 数据与配置 | pinned commit + 数据 SHA + LICENSE SHA/副本入库 `docs/phase7/`（非 .tmp） |
| G2 | 完整 160 题单遍测量 | 官方 prompt（含官方 system prompt 真实进入 payload）+ 冻结推理配置 |
| G3 | 跨基准对照 | 与 BaziQA holdout 最终协议结果并列，显式标注协议差异 |
| G4 | 证据可复算 | manifest / receipt / detail 行 / 原子归档 / 代码指纹，全部字段本设计冻结（§8） |

### 2.2 非目标

- 不做任何 prompt / RAG / 规则改动（测量对象是当前冻结状态）
- 不做多臂对照、投票、双管线、时间注入（Phase 6 已排除）
- 不把 MingLi 160 题用于后续调优（§3.4 密封决策）
- 不评估知识库蒸馏产物（独立路线，进入任何准确率实验前须先过许可/SHA/质量/去重/答案泄漏检查）
- **不实现 `mingli_trimmed` 评分器**（见 §3.6：该字段当前只是 profile 字符串，无生产者）

## 3. 关键设计决策

### 3.0 题目/命盘双主键（v2 审核 P0-1，数据缺陷已实测核实；v2.1 审核 P0 并入 detail 透传修正）

官方数据实测（pinned commit `b7433280`，2026-08-10 核验）：`data.json` 160 题，每题有唯一 `id=ftb_NNNN`；`case_id=case_N` 是**命盘分组键**，仅 32 个唯一值，同盘多题共享。每盘题数**并非**恰好 5：`case_19`=6 题、`case_20`=4 题、其余 30 盘各 5 题（合计 160）。`fortune_api_results.json` 是 32 条 list，以 `case_N` 为键。

adapter 现状（`mingli_bench_adapter.py:239`/`:245`）把命盘 `case_id` 直接作为题目主键，实测两道共享 `case_1` 的题归一化后 `normalized_ids=['mingli_case_1','mingli_case_1']`：attempt key 碰撞、resume 按命盘而非题目跳过、同盘题共享 retry counter、`predictions[case_id]` 互相覆盖、`score_choice_answers()` 可能把同一预测套到同盘多题。

**必须改造 adapter，冻结双主键**：

```text
case_id       = mingli_ftb_0001   # 题目唯一键（官方 id 字段 + mingli_ 前缀），用于 attempt key / resume / predictions / scoring
chart_case_id = case_1            # 命盘分组键（官方原始 case_id，不加前缀），用于 fortune join 与命盘级聚类统计
```

- `chart_case_id` 作为新字段写入 normalized 行。
- **detail 显式写入（v2.1 审核 P0；v2.2 复审限定门禁范围，已源码核实）**：runner 的 detail 是显式字典构造，不会自动透传 normalized 行字段——call_failed 路径（`run_benchmark.py:1353`）与正常/invalid 路径（`run_benchmark.py:1432`）均无 `chart_case_id`。不改造则 32 命盘 macro、聚类 bootstrap、§8.1 命盘门禁全部无法落地。冻结方案：**runner 的 main 与 retest 所有终态 detail 构造处显式写入 `chart_case_id`**（取 `case.get('chart_case_id')`）。**缺失拒绝必须限定 profile**：fail-closed 报错（而非静默置 None）仅在 `profile_id == "mingli_official_cot_astro"` 时生效；BaziQA profile 的数据没有该字段，通用 detail 路径无条件拒绝会造成全局回归——非 MingLi official profile 下该字段按 `None` 记录或不写入，不报错。归档前 orchestrator 把 detail 行与 normalized dataset 按题目 `case_id` 交叉验证（§8.1 第 4/12 条）。
- fortune join 一律使用 `chart_case_id`（原始 `case_N`），不得再用题目 `case_id`。
- 同盘 5 题（或 4/6 题）现在各自有独立 attempt key、独立 retry counter、独立 prediction。

### 3.1 测量臂定义（单一臂）

| 维度 | 值 | 来源 |
|---|---|---|
| provider / model | `deepseek` / `deepseek-v4-flash` | Phase 6 冻结 |
| thinking_mode / temperature | `disabled` / `0.0`（**必须真实进入 API payload**，见 §3.3） | Phase 6 冻结 |
| 调用协议 | 单次调用（无投票/双管线/注入） | Phase 6 冻结 |
| prompt | MingLi 官方 CoT（`mingli_official_cot_astro` profile → `format_official_cot_prompt` + `OFFICIAL_SYSTEM_PROMPT`） | 与官方方法层对齐 |
| chart 数据 | 官方预计算 `fortune_api_results.json` 注入（`--astro`），schema `approved_v1` | profile 约束 |
| RAG / few-shot / APB / shuffle | **全部关闭且 fail-closed**（见 §3.5） | 纯基线 |
| 评分 | 主指标 = 首跑 exact-match micro accuracy（见 §3.6） | 本设计冻结 |

**协议平移的诚实声明**：B1-a′ 的 `baziqa_xjz_reasoned` profile 是 BaziQA 专用（`legacy_v0` + reasoned 输出协议），不适用于 MingLi。平移到 MingLi 的是**推理配置**（模型/thinking/T/单次调用）；prompt 层用 MingLi 官方 prompt 实现**方法层对齐**（prompt/astro 注入与官方方法论一致）。模型、API 版本、并发、运行时间均不同，本测量数字**不得**当作与公开基准数字的严格横向排名。

### 3.2 执行载体：新建 Phase 7 orchestrator（v1 的 P0-1；v2 审核 P0-2、P0-4 并入）

现有 `scripts/run_mingli_bench.py` 只是归一化 wrapper：不转发 `--profile` / `--thinking-mode` / `--scheduled-calls` / `--hard-cap` / `--resume` / `--arm` / `--attempt-stage`，直接跑它不会建立 Phase 6 context、账本和 resume manifest，`thinking_mode=disabled` 也不会进 payload。

**决策：新建 `scripts/phase7_mingli_orchestrator.py`**（参照 6D 系列 orchestrator 架构），职责：

- 调改造后的 adapter 归一化（§3.0 双主键）→ 生成 160 题 JSONL（一次性，SHA 入 manifest）
- 构造 runner 命令，**显式转发全部冻结字段**：

  ```text
  --profile mingli_official_cot_astro --method direct_choice
  --thinking-mode disabled --temperature 0.0
  --arm phase7_mingli_baseline --attempt-stage main
  --scheduled-calls 160 --hard-cap 180
  --case-ids-file <160 个题目唯一 case_id 的文件> --as-of-date <冻结日期>
  ```

  **不得传 `--ziwei-arm`**（见下）。
- BudgetLedger（沿用 6D 语义）、**单一 slice 调度**（见下）、merge、原子归档、receipt 发布
- **argv 同源测试**：orchestrator 生成的 argv 与 manifest 构造参数逐项一致（仿 6B2/6D 的 ManifestHomology 测试）

**`--ziwei-arm none` 禁令（v2 审核 P0-2，已源码核实）**：`profiles._visibility_base()`（`profiles.py:118`）只要 `ziwei_arm` 非 None 就先进入 reasoned-arm 矩阵；实测 `ziwei_arm="none"` 时 required 为空集，官方 astro 三个 required marker（`八字命盘信息：`/`紫微命盘信息：`/`十二宫位星曜分布：`）完全失效。因此：

- MingLi official 命令**不传 `--ziwei-arm`**（保持 None），可见性门禁走 `profiles.py:172-175` 的 `mingli_official_cot_astro` 分支；
- `arm=phase7_mingli_baseline` 只是 attempt key / manifest 元数据，**不得**加入任何 reasoned 臂映射（`_REASONED_ARM_MAP` 等）；
- **测试冻结**：official profile + `ziwei_arm=None` 时，`visibility_requirements` 必须返回官方 astro 三 marker 为 required；orchestrator argv 断言不含 `--ziwei-arm`。

**单一 slice 调度（v2 审核 P0-4，设计阶段冻结，不再留给实施计划）**：

1. 单一 160 题 normalized JSONL；
2. 单一 `case_ids_file`，含 160 个**题目唯一** `case_id`（`mingli_ftb_*`）；
3. 首次运行 `max_cases=10`（runner 既有参数），但 manifest 从一开始即为 `scheduled=160 / hard_cap=180`；
4. smoke 通过后，**同一路径、同一 manifest**，以 `max_cases=160 --resume` 续跑；
5. `smoke_size=10` 与执行阶段（`smoke_first_pass` / `main_resume`）进入 run context 与 audit；
6. `max_cases` 不在 `RESUME_MANIFEST_FIELDS`（已核实 `resume_ledger.py:127-136`），故 `10 → 160` 推进技术上不触发 manifest 拒绝；run context 必须**冻结合法状态转换集合为 `{10 → 160}`**，其它任何 `max_cases` 变化一律拒绝；
7. **不允许**拆成 32 个 runner slice。

### 3.3 官方 system prompt 必须真实进入 payload（v1 的 P0-2；v2 审核 P0-3 修正条件字段）

现状（已核实）：`OFFICIAL_SYSTEM_PROMPT`（`mingli_prompt.py:19`）仅被 `profiles.py:276` 的 prompt 指纹引用，**从未进入请求 payload**——`run_benchmark.py:600` 的 system prompt 恒为 `_resolve_system_prompt()` 的通用 `SYSTEM_PROMPT_BENCHMARK`。这制造"指纹证明官方 prompt 已生效"的假象。

**必须改造**：模型调用构造 system message 时，使用 `OFFICIAL_SYSTEM_PROMPT` 的**精确冻结条件**（v2 审核 P0-3：`EvalProfile` 无 `prompt_version` 字段，`prompt_style` 才是字段名；runner 的 `--prompt-version` 默认 `srp_v1`，属另一套历史参数）：

```python
profile.profile_id == "mingli_official_cot_astro"
```

采用精确 profile ID 而非 `dataset == "mingli" and prompt_style == "official"`，避免未来其它 MingLi official 变体被静默套用。改造后指纹引用才名副其实。**测试必须检查真实发出的 system message 内容**（mock API 调用层捕获 payload），不只是 formatter 快照。

### 3.4 环境干预 fail-closed 净化（v1 的 P0-3）

runner 会读继承环境变量 `BAZI_RAG` / `BAZI_RAG_CORPUS` / `BAZI_FEWSHOT_FILE` / `BAZI_APB_BLOCK`（`run_benchmark.py:529`/`:542` 等），wrapper 又会把整个环境复制给子进程。用户环境残留一个变量就污染"纯基线"。

**必须**：

1. orchestrator 构造子进程 env 时**显式删除**上述 4 个变量（不是依赖父环境干净）；
2. manifest / run context / receipt 记录 `rag=false`、`fewshot=false`、`apb=false`、`shuffle_options=false`；
3. **污染环境负向测试**：父进程设 `BAZI_RAG=1` 等变量后跑 orchestrator，断言子进程 env 无这些变量且 manifest 记录全 false。

### 3.5 密封决策 + smoke 与单遍的统一（v1 的 P0-4；状态机见 §3.2 单一 slice 冻结）

**完整 160 集为密封终测。** v1 的"先 smoke ≤10 题再跑 160"会让 smoke 题被调用两次，违反单遍测量。冻结为：

- **smoke = 主测的前 10 题首跑**：从一开始使用同一份 `scheduled=160 / hard_cap=180` manifest 与单一 BudgetLedger（§3.2）；
- smoke（前 10 题）通过 §5 量化标准后，用 `--resume` 续跑剩余 150 题；
- **最终基线使用每题首次终态**；前 10 题不得以任何理由重跑（§3.6 复测除外）；
- 预算为**单一账本**：scheduled=160 / hard_cap=180（重试与复测储备共用），不设独立的 smoke 硬顶。

### 3.6 评分口径与复测状态机（v1 的 P0-5、P0-6；v2 审核 P0-5 修正）

**评分口径（冻结）**：

- **主指标**：160 题首次 attempt 的 exact-match micro accuracy（`correct` 对 `expected_answer`），分母固定 = 160（含 invalid/call_failed 按错误计）。**删除"`mingli_trimmed` 既有设施"陈述**——`profile.scoring_profile` 字段当前无任何生产者消费（`run_benchmark.py:2008` 直接调 `score_choice_answers`）。
- **辅助**：按年份、按 12 类别、按 32 命盘（`chart_case_id` 分组）的准确率；命盘级 macro accuracy（32 盘等权）。
- **区间估计**：除 160 题 Wilson 区间外，必须增加 **32 命盘聚类 bootstrap** 或命盘级 macro 对照——160 题不是独立样本（32 盘 × 4–6 题）。

**自动重试只有两类（v2 审核 P0-5 修正；v2.1 审核中优 1 口径修正，已源码核实 `run_benchmark.py:327-344`）**：

| 类型 | 触发 | 预算 | 决策权 |
|---|---|---|---|
| 网络/瞬态重试 | runner 内部（provider/网络异常；**正常执行路径每键最多 3 次网络尝试 = 首次 + 2 次重试**，`_attempt_with_ledger` 在 `retry_counts >= 3` 时调用前拒绝） | hard_cap 储备 | runner 自动 |
| 截断重试 | `finish_reason != 'stop'`（每键 ≤1 次，窄重试） | hard_cap 储备 | runner 自动 |
| **终态后受控复测** | 仅 `invalid` 与最终 `call_failed` | **计入全局 hard_cap**（orchestrator 预占，见下） | orchestrator，每题最多 1 次 |

**crash/resume 记账语义单列**：`before_call` 先记账后调用（Policy A），崩溃可能留下只有 pre-call journal 的残缺 attempt，跨 crash/resume 累计 `call_attempt` 可达 4——这是崩溃续跑的账本语义，**不得**表述为"第 3 次重试"。`run_benchmark.py:316` 的 docstring"每键最多 3 次重试（4 次尝试）"与实际门禁不符，实施时一并修正注释。

**parser invalid 没有自动格式重试**——v2 中"截断/格式重试是 runner 既有逻辑"的表述不准确，已删除。parser invalid 直接落终态，只能走终态后受控复测。

**受控复测规则（冻结，v2 审核 P0-5 全量修订）**：

- **`controlled_retest` 与 `dual` 一并加入冻结 vocabulary 并新增 fail-closed 校验（v2.1 审核中优 2；v2.2 复审兼容既有链路，已源码核实）**：`ATTEMPT_STAGES`（`resume_ledger.py:25`）当前只是常量，`build_attempt_key()`（`:29`）不做成员检查，`--attempt-stage`（`run_benchmark.py:1753`）也无 `choices` 约束——现状下它只是元数据约定。同时 `ATTEMPT_STAGES` 当前**不含 `dual`**，而 6B2 orchestrator 实际传 `--attempt-stage dual`（`phase6_6b2_orchestrator.py:251`）；直接 `choices=ATTEMPT_STAGES` 会阻断已归档的 6B2 执行链。改造必须四件套同时落地：(a) `dual` 与 `controlled_retest` **一并**加入 `ATTEMPT_STAGES`；(b) 新增显式 fail-closed 校验（`--attempt-stage` 加 `choices=ATTEMPT_STAGES`，或 runner 启动时对 `args.attempt_stage` 断言成员资格）；(c) **测试未知 stage 被拒绝**（如 `--attempt-stage bogus` 必须以非零退出拒绝）；(d) **6B2 回归测试**：`--attempt-stage dual` 仍可正常通过校验（防既有链路被门禁误杀）。attempt key 第 4 位区分，不与 main 行冲突。
- **复测使用独立产物**：`retest/detail.jsonl`、`retest/events.jsonl`、独立 resume manifest（`attempt_stage=controlled_retest` 从建 manifest 起就是该值）。**禁止**复用 main 的 detail 路径再改 stage——派生 manifest 的 `attempt_stage=main` 已冻结，篡改会被 `check_resume_manifest` 拒绝，这是正确行为。
- **预算全局预占**：orchestrator 从单一账本计算剩余额度（`180 − main 已消耗 call_attempt`），把复测所需额度**预占**后拨付给 retest runner；retest runner 的局部 `hard_cap` = 预占额度，**不得**重新获得 180 次额度。全局 `call_attempt` 总数（main events + retest events 合计）≤ 180。
- **储备不足时**：按固定题目顺序（`mingli_ftb_` id 升序）依次复测，耗尽即停；因预算不足未复测的 eligible 题必须逐题列入报告。
- 每题最多 1 次；仅 `invalid` / 最终 `call_failed` 可复测（eligible 集冻结）。
- **首跑终态始终进入正式准确率**（invalid/call_failed 按错误计入分母 160，与 Phase 6 口径一致）；复测结果只作稳定性附注，并列报告。
- 复测清单（哪些题、为什么、复测前后终态）必须进报告。

### 3.7 数据获取 provenance 补强（v1 的 P0-7）

`fetch_mingli_bench.py` 现状：`--source-dir` 路径不验证 git HEAD 却写死 pinned_commit；manifest 默认写 `.tmp/phase6/`。必须增加：

- `--manifest-out` 参数（本设计指向 `docs/phase7/mingli_fetch_manifest.json`）；
- `--source-dir` 必须执行 `git rev-parse HEAD` 并与 pinned commit `b7433280fd86d7a7c27debbc47d0303c218f0bfd` 比对，非 git 来源或 HEAD 不符 → BLOCKED（exit 4）；
- LICENSE 文件 SHA-256 + 正文副本存入 `docs/phase7/`（官方该 commit 声明 MIT）；
- 数据文件 SHA、字节数、pinned commit、LICENSE SHA 四者交叉入 manifest。

## 4. 阶段一：零 API preflight（先于任何真实调用）

1. **数据冻结**：改造后的 fetch（§3.7）→ `docs/phase7/mingli_fetch_manifest.json` + LICENSE 副本。
2. **完整性核验（fail-closed 断言，v2 审核 P0-1 口径，按实测分布修正）**：
   - `data.json` 恰 160 题；题目唯一 `id`（`ftb_NNNN`）160 个无重无缺失；
   - 命盘 `case_id` 恰 32 个唯一值；
   - 每盘题数分布**冻结为实测值**：30 盘 × 5 题 + `case_19` × 6 题 + `case_20` × 4 题（**不是**"每盘恰 5 题"，官方实测分布如此，硬编码期望值入 preflight）；
   - 年份（2022–2025，经 `_infer_year` 由 `question_number` 推导）与 12 类别分布记录；
   - 每题可经改造后 adapter 归一化，产出 160 个唯一 `case_id`（`mingli_ftb_*`）+ 32 个唯一 `chart_case_id`；
   - fortune join 使用 `chart_case_id`，32 盘全部在 `fortune_api_results.json` 命中（`--astro` 无缺失）。
3. **协议核验**：`mingli_official_cot_astro` profile 解析通过；**§3.3 改造后**的官方 prompt 渲染快照 + system message payload 测试通过；parser 在合成样例上可解析；**official profile + `ziwei_arm=None` 的可见性门禁 required/forbidden 断言通过**（v2 审核 P0-2 测试：三 astro marker 必须在 required）。
4. **环境净化核验**：§3.4 负向测试通过。
5. **预算核验**：单一账本 scheduled=160 / hard_cap=180；run context 冻结 `max_cases` 合法转换 `{10 → 160}`（§3.2）。
6. **preflight receipt**：`docs/phase7/preflight_receipt.json`（PASS/BLOCKED + 全部 SHA + 检查项）；BLOCKED 不进阶段二。

## 5. 阶段二：真实测量（需用户明确批准 API）

1. **smoke = 前 10 题首跑**（`max_cases=10`，同一份 160/180 manifest）。**量化通过标准（v2 审核中优 1；v2.1 审核中优 3 对账公式精化，冻结）**：
   - terminal detail 恰 10 条；
   - `call_failed = 0`；
   - 官方 astro 可见性门禁 10/10 PASS（`gate_blocked = 0`）；
   - parser 成功率 ≥ 90%（10 题中 parsed ≥ 9）；
   - **逐 attempt key 对账**（不用全局总数公式）：每个已完成的 smoke attempt key 满足 `call_attempt 事件数 = 1 + 该键 kind=model_call_failed 事件数`；且不存在只有 pre-call journal、无对应终态 detail 的残缺 attempt。
   任一不达标则不 resume，修复后按 resume 语义续跑（前 10 题已落盘终态不重跑）。
2. **主测续跑**：`max_cases=160 --resume` 完成剩余 150 题（合计 160 首次 attempt）；run context 校验状态转换为冻结的 `10 → 160`。
3. **受控复测**：仅 §3.6 状态机允许的题，独立 `retest/` 产物 + 全局预算预占。
4. **归档**：先过 §8 完整性硬门（`completeness_verdict`），再原子归档 + receipt 发布，落盘 `docs/phase7/`。

## 6. 报告内容（预声明）

- 主指标：首跑 exact-match micro accuracy（分母 160）+ Wilson 区间 + **32 命盘聚类 bootstrap / 命盘级 macro**
- 按年份 / 12 类别 / 32 命盘（`chart_case_id`）的分类别准确率
- parser 终态分布（parsed / invalid / call_failed）与 parser_rate
- 受控复测清单与结果（含因预算不足未复测的 eligible 题；首跑值仍为官方基线值）
- **跨基准对照表**：MingLi 160（本测）vs BaziQA 2024/2025 holdout（Phase 6 归档值），显式标注协议差异（prompt、题目分布、chart 数据来源、运行时间均不同）
- 与 Phase 1 前 20 题结果的对照，标注其为**历史链路 smoke**（shuffle + 非官方 profile），不作同协议比较

## 7. 预算

| 项 | scheduled | hard_cap |
|---|---|---|
| 主测（含前 10 题 smoke 首跑） | 160 | 180 |
| 受控复测 | 从 180 储备支出（orchestrator 预占剩余额度；最多 20 次，与重试共享） | — |
| 合计硬顶 | — | **180**（main + retest 的 `call_attempt` 合计；超出须显式登记） |

## 8. 证据链字段冻结（v1 中优项；v2 审核 P0-6 + 中优 2/3/4 并入）

### 8.1 归档完整性硬门（v2 审核 P0-6，fail-closed）

归档前必须逐项断言，任一失败 → `completeness_verdict = BLOCKED_INCOMPLETE`，**不得发布基线 receipt**：

```text
1.  main detail 首跑终态行数 = 160
2.  main 唯一题目 case_id（mingli_ftb_*）= 160
3.  每个 case_id 恰 1 个 main 终态
4.  唯一 chart_case_id = 32，且每盘题数 = 冻结分布（30×5 + case_19×6 + case_20×4）
5.  终态仅属于冻结枚举（parsed / invalid / call_failed；本臂不出现 unresolved/judge_unresolved）
6.  first_pass 分母固定 = 160
7.  controlled_retest 每题 ≤ 1，且 retest 行的 case_id ⊆ main 终态为 invalid/call_failed 的集合
8.  main + retest 的 call_attempt 事件合计 ≤ 180
9.  merged_details SHA-256 与 audit index 记录一致
10. 所有成功调用的 thinking_mode = disabled
11. response_model 有值时必须等于 deepseek-v4-flash
12. 每行 main/retest detail 的 chart_case_id 与 normalized dataset 按题目 case_id join 完全一致（无缺失、无错位）
```

可见性 `gate_blocked`、manifest 漂移、main 缺题、main 题数 ≠ 160，均判 `BLOCKED_INCOMPLETE`。

### 8.2 receipt 必需字段

`check` 函数 fail-closed 校验存在性与一致性（v2 审核中优 2 的增补字段已并入）：

```text
stage, run_id, user_run_id, archive_dir, audit_index_sha256,
provider, model, thinking_mode, temperature, model_label,
profile, method, arm, attempt_stage,
code_fingerprint, prompt_fingerprint（含真实生效的 OFFICIAL_SYSTEM_PROMPT）,
mingli_data_sha256, fortune_api_sha256, normalized_jsonl_sha256,
pinned_commit, license_sha256,
rag, fewshot, apb, shuffle_options（全 false）,
scheduled_calls, hard_cap, attempted,
first_pass_accuracy, parser_rate, terminal_state_counts,
completeness_verdict, smoke_size,
question_id_count（=160）, chart_case_count（=32）,
response_model_values, response_model_missing_count
```

- **`model_label` 冻结值**（v2 审核中优 3）：`DeepSeek-V4-Flash non-thinking`。
- `response_model_values`：detail 行中实际出现的 response model 取值集合（期望恰为 `{"deepseek-v4-flash"}`）；`response_model_missing_count`：无该字段的行数（计入审计，不掩盖）。

### 8.3 audit index

上述全部 + main/retest detail/events/manifest SHA + merged_details SHA + completeness 逐项断言结果 + 复测清单（含未复测 eligible 题）+ run context（含 `smoke_size`、`max_cases` 状态转换记录）。

### 8.4 代码指纹范围（v2 审核中优 4，列出具体文件）

`_code_fingerprint()` 的 `_CODE_SCOPE` 已覆盖 runner/profiles/formatter/API client；Phase 7 必须在其基础上**显式并入**以下文件（或建立独立的 `phase7_code_fingerprint` 字段与之并列，二选一在实施计划中定，但范围不得缩减）：

```text
scripts/phase7_mingli_orchestrator.py      # orchestrator 全文
scripts/fetch_mingli_bench.py              # fetch 全文
benchmark/runners/mingli_bench_adapter.py  # adapter 全文（含双主键改造）
benchmark/runners/run_benchmark.py         # runner（_CODE_SCOPE 已有）
benchmark/runners/resume_ledger.py         # resume ledger（_CODE_SCOPE 已有）
benchmark/runners/profiles.py              # profiles（_CODE_SCOPE 已有）
benchmark/formatters/mingli_prompt.py      # MingLi formatter（_CODE_SCOPE 已有）
claude_api.py                              # API client（_CODE_SCOPE 已有）
config.py                                  # provider 配置（_CODE_SCOPE 已有）
```

### 8.5 原子发布链

tmp 写入 → SHA 校验 → `os.replace`；归档自验（merged_details SHA 重算一致）；receipt 从磁盘读回校验后发布（沿用 6D v1 的 TOCTOU 修正模式）。

## 9. 风险与回退

| 风险 | 缓解 |
|---|---|
| 题目主键碰撞（同盘题共享 case_id） / `chart_case_id` 不进 detail | §3.0 双主键改造 + runner detail 显式写入 + §4 完整性断言（160 唯一题目 ID / 32 唯一命盘 ID / 冻结分布）+ §8.1 第 12 条交叉验证 |
| `--ziwei-arm none` 绕过官方可见性门禁 | §3.2 禁令 + argv 断言 + `ziwei_arm=None` 门禁测试 |
| 官方 system prompt 未进 payload（指纹假象） | §3.3 精确 profile ID 条件改造 + payload 级测试 |
| 环境污染（RAG/few-shot/APB） | §3.4 显式删除 + 负向测试 + manifest 四 false |
| smoke 题被二次调用 / slice 拆分漂移 | §3.2 单一 slice + `max_cases` 状态转换冻结 `{10 → 160}` + resume 续跑 |
| 复测绕过首跑口径或重领预算 / stage 门禁误杀既有链路 | §3.6 独立 retest 产物 + `dual`/`controlled_retest` 一并入 vocabulary + stage fail-closed 校验（含 6B2 `dual` 回归测试）+ 全局预占 + 每题 ≤1 |
| 部分运行误发 receipt | §8.1 完整性硬门，`BLOCKED_INCOMPLETE` 不发布 |
| `mingli_trimmed` 空头字段 | §3.6 删除该陈述，主指标 exact-match |
| fetch 来源不可证 | §3.7 HEAD 校验 + LICENSE SHA + manifest-out |
| 命盘聚类夸大显著性 | §3.6 聚类 bootstrap / macro 并列（32 盘 × 4–6 题，非独立样本） |
| 蒸馏产物混入 | 非目标排除 + env 净化 + profile 无检索 |
| 行尾/字节 SHA 漂移（6B2/6D 先例） | 归档自验 + slice 级重建兜底 |

## 10. 完成定义

1. 本设计 v2.3 复审确认（两处共享 runner 回归风险闭环）
2. §3.0/§3.2/§3.3/§3.6/§3.7 的 adapter/orchestrator/runner/resume ledger/fetch 改造完成且测试全绿（含双主键归一化、main/retest detail 显式写入 `chart_case_id` 且缺失拒绝仅限 `mingli_official_cot_astro`（BaziQA profile 不报错）、argv 同源且不含 `--ziwei-arm`、`ziwei_arm=None` 官方门禁、payload system message、污染负向、`max_cases 10→160` 状态机、未知 attempt stage 拒绝、`--attempt-stage dual` 6B2 回归通过、retest 独立产物与全局预算、HEAD 校验）
3. preflight receipt = PASS（全部 SHA/检查项入 `docs/phase7/`）
4. smoke（前 10 题首跑，量化标准全过）→ resume 主测完成 → §8.1 硬门 COMPLETE → 归档 + receipt + 报告落盘
5. 跨基准对照表产出（含聚类区间与协议差异标注）
6. 全程无 prompt/RAG/规则语义改动（除 §3.3 的 system prompt 接线——它是"让声明的配置真实生效"，不是新增干预）

实施计划在本设计 v2.3 确认后单独编写；**阶段二需用户明确批准 API 后启动**。
