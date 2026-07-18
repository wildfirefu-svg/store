# Phase 6 6A0 已批准上下文、五维 Profile 与评测设施硬化 实施计划 v7

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态**：v1 = NEEDS_REVISION（4 实现阻塞 + 完整性）→ v2 = NEEDS_REVISION（3 阻塞 + 占位符）→ v3 = NEEDS_REVISION（2 阻塞）→ v4 = NEEDS_REVISION（2 阻塞 + 1 附带）→ v5 = NEEDS_REVISION（3 个 manifest 内部矛盾）→ v6 = CONDITIONAL_APPROVAL（1 个局部启动守卫）→ **v7 = APPROVED**（守卫改任一产物检查 + resume-first 崩溃残留测试；评审授权补完即批准，进入执行）

**Goal:** 实现设计 v6 的阶段 6A0——已批准八字上下文（`approved_v1`）与固定模板渲染、防泄漏分级扫描、五维评测 profile（含四个命名配置与 (profile, schema_version) 可见性矩阵）、MingLi 数据前置与归一化可见性、以及 resume-safe 评测设施（10 字段 attempt key、append/resume、重试账本、双列预算与 `BLOCKED_INCOMPLETE`），并以 12 切片 AB/BA 配对消融完成 2024 dev gate。

**Architecture:** 新增独立模块 `benchmark/formatters/chart_context.py`（渲染）、`benchmark/formatters/leak_scan.py`（扫描）、`benchmark/formatters/mingli_prompt.py`（官方 CoT）、`benchmark/runners/profiles.py`（profile 注册表与路由）与编排脚本 `scripts/run_phase6_6a0_ablation.py`（离线 gate + AB/BA 切片调度 + 预算 + 报告）；对 `benchmark/runners/run_benchmark.py` 做外科手术式增量（新增 CLI 与钩子，默认行为向后兼容）；所有决策逻辑写成无网络纯函数并由专用单测覆盖，真实模型仅通过 runner 既有调用边界（`call_model_sync` / `call_model_messages_with_history`）发起。

**Tech Stack:** Python 3.11+、标准库（`argparse`、`dataclasses`、`hashlib`、`json`、`math`、`pathlib`、`re`、`random`、`subprocess`、`datetime`）、pytest、现有 enrichment / runner / report 组件。

**设计依据（v6，行号以该文件为准）：**

- 数据角色与隔离、as_of_date、SHA-256：`docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md` §3.1（L81–94）
- MingLi 数据前置：§3.2（L96–103）
- 已批准 schema、denylist、模板、泄漏分级、AB/BA：§4.2（L111–120）
- 五维 profile、四命名配置、可见性矩阵：§4.3（L122–154）
- attempt key、重试账本、双列预算、BLOCKED_INCOMPLETE、append/resume：§4.4（L156–178）
- 落点：§4.5（L180–186）；验证与 gate：§4.6（L188–195）
- 预算：§8（L303–328，6A0 scheduled 260 / hard_cap 290）；阻塞规则：§10（L347）；Gate 汇总：§11（L353–354）

**范围边界：**

- 本计划仅覆盖 **6A0**。6A1/6B1/6B2 的实施计划在对应前置 gate 通过后另行编写（触发条件见文末），禁止在本计划中提前实现 `strict_majority()`、锚定臂、双管线或 judge。
- 不修改 `benchmark/datasets/*.jsonl` 原始文件；enriched 产物只写入 `.tmp/phase6/`。
- 不注入任何当前日期流年；`kong_wang`（含 `four_pillars.<pillar>.kong_wang` 占位键）与 `liu_nian` 字段保持 denylist，渲染器永不读取。
- 2023 保持密封：enrichment 默认年度为 2021/2022/2024/2025；2023 的 enrichment 需显式 `--include-2023` 并记入 manifest（enrichment 只生成输入侧 chart_input，不等于打开评测）。

## 修订记录（v1 → v2）

| # | 评审意见 | v2 处理 |
| --- | --- | --- |
| 阻 1 | AB/BA 未落地：6 次全量 arm-run 无法实现题组相反顺序 | Task 9 改为**每 repeat 4 个 20 题切片、共 12 切片**；`build_schedule` 纯函数生成全序列，测试逐切片断言 `(arm, case_ids)` 与 cap；每 repeat cap `[23,23,22,22]`（和 90）×3 + smoke 20 = 290 |
| 阻 2 | `render_chart_context(chart_input, "legacy_v0")` 丢失姓名/嵌套 birth，无法与 `format_birth_line(case)` 等价 | 签名改为 `render_chart_context(case, schema_version, as_of_date=None)`；legacy_v0 直接委托 `format_birth_line(case)`；fixture 改为完整 case 记录（含 `person`）；身份头四行在两臂间逐字节一致（决策记录见 Task 1） |
| 阻 3 | profile 未真正控制五维，`--method` 可独立指定造成口径漂移 | `profiles.py` 新增 `derive_method` / `derive_formatter`；runner 以 profile 为五维唯一来源，`--method` 显式值与推导值冲突即 `SystemExit(2)`；四个命名配置各一条端到端路由测试（mingli_official_cot_astro 在 Task 5 落地，前置缺失时拒绝执行并退出码 4） |
| 阻 4 | 跨 resume 重试测试前提不成立（第 3 次会成功并被 resume 跳过） | 改为注入**非重试异常模拟崩溃**：2 次 `model_call_failed` 后进程死亡（events=[1,2]、无终态），resume 后第 3 次失败 → `call_failed`（events=[1,2,3]） |
| 完整性 | "实现要点"散文、未定义 fixture、commit 占位符、git 暂存过宽 | 关键模块给出可执行实现代码与共享测试设施（`RunnerEnv`/`RunnerSpy`/`fake_config`）完整定义；MingLi commit 固定为 `b7433280fd86d7a7c27debbc47d0303c218f0bfd`；全部 `git add` 收窄为精确路径 |

## 修订记录（v2 → v3）

| # | 评审意见（v2 复审） | v3 处理 |
| --- | --- | --- |
| 阻 1 | `--smoke-only` 过滤 schedule 后 `run_ablation` 内部重新 `build_schedule`，smoke 实际会跑全量 260 次 | `run_ablation(config, schedule, slice_runner=None)` 改收**已构建的 schedule**；`main()` 传过滤后的 schedule；既有两个 run_ablation 测试改为先 `build_schedule` 再传入；新增 `test_run_ablation_smoke_schedule_single_call`（smoke schedule → `spy.calls == 1`） |
| 阻 2 | smoke 切片经 `max(slice_run.repeat_idx, 0)` 变成 repeat 0，与正式 repeat 0 group_a approved 切片的 attempt key 完全相同，`--resume` 会跳过正式 20 题复用 smoke 结果 | 去掉 `max(...)`，`--repeat-idx` 原样透传（smoke 恒 `-1`；runner argparse `type=int` 接受负数；`Phase6Context` 中 `int(repeat_idx or 0)` 对 -1 保留原值）；不新增 attempt stage（保持设计冻结 6 元组）；新增 `test_smoke_attempt_keys_disjoint_from_main`：对 13 个切片逐切片建键并断言 smoke 键集与 12 个主切片键集不相交 |
| 阻 3 | hard cap 不跨 resume 持久化：成功调用不写事件、`calls_attempted` 每次启动归零，中断后续跑可静默突破预算；同一 arm 多切片共用同一 detail/events，切片账本与阶段账本不分 | ① **每次模型调用（含成功）先写 `call_attempt` 事件再调用**，失败再写 `model_call_failed`；`Phase6Context.__init__` resume 时 `calls_attempted = load_call_attempt_count(events_path)`；`load_retry_counts` 只数 `kind == "model_call_failed"`；② 每切片独立目录 `arm/runs/<run_id>/slice_{purpose}_{repeat}_{group}/`（detail/events/summary 均在其中），报告聚合改 glob `slice_*/detail.jsonl`；③ 新增 `BudgetLedger` 阶段总账本（`.tmp/phase6/budget/<run_id>.jsonl`），切片启动前检查 `total_attempted + slice.hard_cap > stage_hard_cap` 即返回 `FAILED/stage budget overflow`，切片完成后按实际 `calls_attempted` 记账；④ 新增 `test_calls_attempted_restored_across_resume`（成功 2 次后第 3 次调用时崩溃、崩溃 attempt 已记账；resume 后 hard_cap=3 额度已耗尽，c3 不得执行）与 `test_stage_budget_ledger_overflow_aborts` |
| 占位符 | Task 6 Step 5/7 审计清单为 `<...>` 占位；Task 5 MingLi CoT 模板标注"下为占位形态" | 审计结果填实：9 个需补 `--overwrite` 的精确文件/行号清单 + 7 条豁免核对结论（见 Task 6 Step 5）；CoT 模板改为**实现冻结版 `mingli_official_cot_v1`**，Task 5 Step 5 勘察只做核验——仓库已有官方模板且实质差异 → 停下汇报（偏离发现，不静默替换）；无或仅措辞差异 → 生成 golden 继续 |

## 修订记录（v3 → v4）

| # | 评审意见（v3 复审） | v4 处理 |
| --- | --- | --- |
| 阻 1 | `BudgetLedger` 追加式记账不具 resume 幂等：runner 的 `calls_attempted` 是切片级累计值，smoke-only 后接全量会把 smoke 的 20 次重复记成 40，侵蚀 30 次重试储备并最终误报 overflow；启动前检查 `total + slice.hard_cap` 也未扣除该切片已消费额度 | 账本改**按 `slice_id` 幂等覆盖**（JSON dict：`slice_id → {calls_attempted, hard_cap, timestamp}`），`record` 取 `max(旧值, 新值)` 防异常路径回退；阶段总数 = 各 slice_id 最新值之和；启动前检查改 `total_attempted() + (hard_cap − attempted_for(slice_id)) > stage_hard_cap`（已完成切片只按剩余额度预占）；`run_slice` 在 summary 缺失（崩溃路径）时从切片 events 数 `call_attempt` 兜底。新增 2 测试：smoke-only 后接全量 smoke 仍记 20、完整实验再次 resume 总数不变且不误报 |
| 阻 2 | 截断守卫位于 `if args.profile:` 分支内，旧脚本均不传 `--profile` 永不触发；v3"9 个调用方补 `--overwrite`"无作用且扩大改动面 | 采纳评审推荐：**守卫仅服务 Phase 6**，9 个旧脚本及其测试**零修改**；Task 6 Step 5 审计结论改为"0 个调用方需要适配"（保留逐文件核对依据），Step 7 `git add` 移除 9 个脚本路径；推翻 v3 对应结论 |

## 修订记录（v4 → v5）

| # | 评审意见（v4 复审） | v5 处理 |
| --- | --- | --- |
| 阻 1 | 缺 resume manifest 校验：temperature、prompt/代码/数据哈希不进 attempt key，须由 manifest 约束（设计 L168）；v4 resume 只恢复 key/计数，改 temperature、模板、数据、代码、切片、预算任一仍可静默续跑 | 每切片 detail 旁新增 `detail.manifest.json`（13 字段：dataset/case_ids SHA-256、profile_id、chart_schema_version、arm/repeat_idx、provider/model/sample_temperature、prompt_template_sha256、code_sha256、scheduled_calls/hard_cap）；首跑创建（原子写），`--resume` 逐字段全等否则 `SystemExit(2)` 并打印 diff；`prompt_fingerprint(profile)`（profiles.py）与 `_code_fingerprint()`（实验范围 6 文件 bytes 拼接哈希）纯函数化；测试：首跑建 manifest、6 字段参数化篡改拒绝、真实数据变更拒绝 |
| 阻 2 | `BudgetLedger._load` 损坏即 `{}` 属 fail-open，预算可静默突破；`attempted_for > hard_cap` 会使 remaining_cap 变负失真 | **fail-closed**：JSON 损坏/结构错/非 int/负值/`calls_attempted > hard_cap` 一律抛 `BudgetLedgerCorrupt`，`run_ablation` 转 `BLOCKED_INCOMPLETE`（reason 含 `budget ledger corrupt`）；record 时同样校验新值；schedule 与账本 cap 背离（remaining < 0）显式报 `budget ledger inconsistent`；写入改临时文件 + `os.replace` 原子替换。新增 3 测试：损坏 JSON、超 cap 记录、原子写无 .tmp 残留 |
| 附带 | 设计 L176"禁止任何启动路径截断"与 profile 分支 `--overwrite` 冲突 | **移除 `--overwrite`**：CLI 不再注册；守卫改为"detail 已存在且非 `--resume` → `SystemExit(2)`，提示换新 run/slice 目录"；`test_truncation_guard_requires_intent` 改写（首跑成功 → 无 --resume 拒绝 → --resume 续跑成功）；文件结构 CLI 清单同步 |

## 修订记录（v5 → v6）

| # | 评审意见（v5 复审） | v6 处理 |
| --- | --- | --- |
| 阻 1 | resume 等价测试与 manifest 契约冲突：首跑传 `--case-ids-file [c0,c1]`、resume 不传（全量 4 题），`case_ids_sha256` 漂移必被 `SystemExit(2)`，永远得不到预期 4 键 | 重写 `test_resume_skips_completed_and_key_set_matches_one_shot`：两次运行使用**完全相同的 case 集合**；首跑 `model_succeeds_then_crash("A", successes=2)` 在 c2 调用时进程崩溃（仅 c0/c1 终态），resume 用同一 dataset 续跑至 4 键，与一次性运行键集合一致 |
| 阻 2 | manifest 只记 `sample_temperature`——6A0 为 `n_samples=1`，真正控制模型调用的是 `args.temperature`（仓库已核实：`--temperature` 默认 0.0、`--n-samples` 默认 1），temperature 0→1 后 manifest 仍一致可续跑；参数化篡改测试只证明"存储文件被改能检测"，未证明配置漂移能进入 current manifest | manifest 扩至 **17 字段**：新增 `temperature`/`n_samples`/`aggregate`/`method`（`method` 记录 4e `resolve_method` 后的生效值，接线顺序保证 resolve 先于 `build_resume_manifest`）；篡改参数化补 `temperature`/`method` 达 8 字段；新增 `test_resume_manifest_config_drift_refused`：resume 传 `--temperature 1.0`（CLI 配置漂移，非篡改存储文件）→ `SystemExit(2)` |
| 阻 3 | 旧 detail/events 在而 manifest 缺失时被放行——按当前配置新建 manifest 后继续混合旧结果，fail-open；`stored.get(k)` 让"字段缺失且 current 为 None"误判相等 | **三态语义**：detail/events/manifest 全无 → 首跑创建（含 `--resume` 首跑）；manifest 在 → 校验后续跑；detail 或 events 在而 manifest 缺失 → 打印 `MANIFEST_MISSING` 后 `SystemExit(2)` fail-closed。`check_resume_manifest` 改逐字段 `k not in stored` 判缺失，缺失记 `"<MISSING>"` 进 diff。新增 2 测试：manifest 被删后续跑拒绝、删 `case_ids_sha256` 字段（current 为 None）拒绝 |

## 修订记录（v6 → v7）

| # | 评审意见（v6 复审，CONDITIONAL_APPROVAL） | v7 处理 |
| --- | --- | --- |
| 附带 | 非 resume 启动守卫只检查 detail：`--resume` 首跑在首个终态写入前崩溃会残留 manifest/events（detail 不存在），误用无 `--resume` 命令时守卫不拒绝，`Phase6Context(resume=False)` 不恢复 events 中的 `calls_attempted`，静默重置单切片预算 | 守卫前置并改为**任一产物检查**：detail/events/manifest 任一存在且非 `--resume` → 打印 `ARTIFACT_EXISTS` 后 `SystemExit(2)`。状态机固定：三者全无 ± `--resume` → 首跑（resume-first 允许）；任一产物 + 无 `--resume` → 拒绝；manifest + `--resume` → 校验续跑；detail/events 在而 manifest 缺失 + `--resume` → 拒绝。新增 `test_resume_first_crash_artifacts_guard`（`successes=0` 第一次调用即崩溃 → 仅留 manifest/events → 无 `--resume` 拒绝、`--resume` 可续跑）。经评审授权补完即标 APPROVED |

---

## 文件结构

**Create:**

- `benchmark/formatters/chart_context.py` — `CHART_CONTEXT_TEMPLATE` 渲染器（legacy_v0 / approved_v1）、已批准字段 presence、本命紫微宫位段。
- `benchmark/formatters/leak_scan.py` — 防泄漏分级扫描纯函数。
- `benchmark/formatters/mingli_prompt.py` — MingLi 官方 CoT prompt（模板来源经 Task 5 核实）。
- `benchmark/runners/profiles.py` — 五维 `EvalProfile`、四个命名配置、路由推导、可见性 required/forbidden 矩阵。
- `scripts/enrich_phase6_chart_input.py` — Phase 6 enrichment 薄封装（as_of_date、输出 `.tmp/phase6/datasets/`、SHA-256 manifest 条目）。
- `scripts/fetch_mingli_bench.py` — MingLi-Bench 数据获取前置（固定 commit `b7433280fd86d7a7c27debbc47d0303c218f0bfd`、SHA-256、许可证记录；失败记 BLOCKED）。
- `scripts/run_phase6_6a0_ablation.py` — 6A0 编排器（离线 gate、AB/BA 切片调度、预算接线、Δ 与判定、报告）。
- `tests/test_chart_context.py`、`tests/test_leak_scan.py`、`tests/test_phase6_profiles.py`、`tests/test_enrich_phase6_chart_input.py`、`tests/test_fetch_mingli_bench.py`、`tests/test_phase6_resume.py`、`tests/test_phase6_retry_budget.py`、`tests/test_phase6_6a0_ablation.py`
- `tests/phase6_helpers.py` — 共享测试设施（`RunnerEnv` / `RunnerSpy` / `fake_config` / case fixture 构造器，定义见下）。
- `tests/fixtures/phase6/` — 完整 case 记录 fixture（`case_sample_{1,2,3}.json`，含 `person` 与 `chart_input`）与 golden 渲染快照（`approved_v1_case{1,2,3}.txt`、`legacy_v0_case1.txt`、`mingli_prompt_golden.txt`、`mingli_official_prompt_template.txt`）。

**Modify:**

- `benchmark/formatters/baziqa_prompt.py` — `format_direct_choice_prompt` / `format_multi_turn_context` 增加可选 `chart_context_text` 参数（默认 None = 现有行为，向后兼容）。
- `benchmark/runners/run_benchmark.py` — 新增 CLI（`--profile`、`--chart-schema-version`、`--arm`、`--repeat-idx`、`--case-ids-file`、`--resume`、`--scheduled-calls`、`--hard-cap`；**无 `--overwrite`**——设计 §4.4.3 禁止任何启动路径截断，重跑换新 run/slice 目录）；`--method` 默认值改 `None` + profile 冲突解析；`--profile` 分支内新增截断守卫（detail/events/manifest 任一产物存在且非 `--resume` 即拒绝，不影响无 profile 的旧调用路径）与 resume manifest 校验（17 字段逐字段全等 + 字段完整性；不一致、或旧 detail/events 在而 manifest 缺失，均 `SystemExit(2)` fail-closed）；attempt key 与终态写入；模型调用边界包重试账本；原始响应持久化。
- `benchmark/runners/mingli_bench_adapter.py` — 归一化产物补齐 canonical `chart_input`（bazi 白名单 + `palaces` → 本命紫微段输入），供 approved_v1 渲染。
- `benchmark/reports/accuracy_stats.py` — 新增 `trimmed_mean()`；`benchmark/reports/generate_report.py` — 按 scoring_profile 附列 trimmed mean。

**Do not modify:** `benchmark/datasets/*.jsonl`、`bazi_calculator.py`（本阶段不改计算器；`kong_wang` 缺口仅记录）、`benchmark/runners/self_consistency.py`、**全部既有调用方脚本/PS1 零修改**（截断守卫仅在 `--profile` 分支内生效，旧调用方不进入该路径——Task 6 Step 5 审计结论）。

**Runtime only（不入 Git）：** `.tmp/phase6/**`（enriched 数据、manifest、attempt 明细、事件日志、原始响应、run 状态）；`docs/phase6/<run_id>/{report.md,manifest.json,summary.json}` 由真实运行后生成，实现阶段不伪造。

## 固定接口与数据结构

以下签名与常量一经写入不得改名；后续任务与 6A1+ 计划依赖它们。

```python
# benchmark/formatters/chart_context.py
from __future__ import annotations

CHART_CONTEXT_TEMPLATE_VERSION = "approved_v1"
SCHEMA_VERSIONS = ("legacy_v0", "approved_v1")

APPROVED_BAZI_FIELDS: tuple[str, ...] = (
    "four_pillars", "day_master", "nayin_wuxing", "wuxing_stats", "shishen_stats",
    "branch_relations", "shensha", "da_yun",
    "tai_yuan", "ming_gong", "shen_gong", "true_solar_info",
)
DENYLIST_FIELDS: tuple[str, ...] = ("kong_wang", "liu_nian")

def render_chart_context(
    case: dict,
    schema_version: str = CHART_CONTEXT_TEMPLATE_VERSION,
    as_of_date: str | None = None,
) -> str:
    """case 为完整题目记录（含 person 与 chart_input）。
    legacy_v0   → 与 format_birth_line(case) 逐字节一致；
    approved_v1 → 身份头四行（与 format_birth_line 的姓名/性别/出生/地点逐字节一致）
                  + 固定模板渲染 case["chart_input"] 批准字段；
                  chart_input.ziwei 存在时追加本命紫微宫位段。
    永不读取 kong_wang / liu_nian（含 four_pillars.<pillar>.kong_wang 占位键）。
    同一 case + 同一 as_of_date 输出跨进程逐字节一致。"""

def approved_field_presence(chart_input: dict) -> dict[str, bool]:
    """返回 APPROVED_BAZI_FIELDS 每项在 chart_input 中是否有可用数据。"""
```

```python
# benchmark/formatters/leak_scan.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class LeakHit:
    kind: str    # "answer_metadata" | "extra_exposure" | "eval_result"
    detail: str

def scan_prompt_for_leaks(prompt: str, case: dict) -> list[LeakHit]:
    """硬失败规则（设计 §4.2.4）；正常选项块内出现正确选项文本、身份字段均不产生 LeakHit。"""
```

```python
# benchmark/runners/profiles.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class EvalProfile:
    profile_id: str
    dataset: str             # "baziqa" | "mingli"
    prompt_style: str        # "official" | "xjz_direct"
    interaction_mode: str    # "direct" | "multi_turn"
    chart_schema_version: str
    scoring_profile: str     # "baziqa_macro" | "mingli_trimmed"

PROFILES: dict[str, EvalProfile]  # 四个命名配置，键即 profile_id

def resolve_profile(name: str, chart_schema_version: str | None = None) -> EvalProfile: ...
def derive_method(profile: EvalProfile) -> str:
    """interaction_mode → runner method：multi_turn→"multi_turn"，direct→"direct_choice"。
    profile 是五维唯一来源；runner 不得接受与之冲突的显式 --method。"""
def derive_formatter(profile: EvalProfile) -> str:
    """(dataset, prompt_style, interaction_mode) → formatter 标识：
    (baziqa, official, multi_turn) → "format_multi_turn"
    (baziqa, xjz_direct, direct)   → "format_direct_choice_prompt"
    (mingli, official, direct)     → "format_official_cot_prompt"
    (mingli, xjz_direct, direct)   → "format_direct_choice_prompt\""""
def visibility_requirements(
    profile: EvalProfile, chart_schema_version: str,
) -> tuple[frozenset[str], frozenset[str]]: ...   # 设计 §4.3 矩阵
def assert_visibility(rendered_text: str, profile: EvalProfile, chart_schema_version: str) -> list[str]:
    """渲染文本上的 required/forbidden 子串断言，返回违规列表（空表=通过）。"""
def prompt_fingerprint(profile: EvalProfile) -> str:
    """prompt/模板指纹（resume manifest 字段）：模板版本+常量+渲染器与 formatter 源码 SHA-256。"""
```

```python
# benchmark/runners/run_benchmark.py（新增，均为纯函数或常量）
ATTEMPT_KEY_FIELDS: tuple[str, ...] = (
    "dataset_id", "profile_id", "arm", "attempt_stage", "provider", "model",
    "case_id", "repeat_idx", "sample_idx", "permutation_id",
)
ATTEMPT_STAGES = ("main", "bazi", "ziwei", "judge", "diversity_probe", "anchor")
TERMINAL_STATES = ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed")

def build_attempt_key(dataset_id, profile_id, arm, attempt_stage, provider, model,
                      case_id, repeat_idx, sample_idx, permutation_id) -> tuple: ...
def compute_hard_cap(scheduled_calls: int) -> int: ...  # +10% 向上取整到 10 的倍数
def load_completed_keys(detail_path) -> set[tuple]: ...
def load_retry_counts(events_path) -> dict[tuple, int]: ...   # 只数 kind=="model_call_failed"，按 key 取 retry_idx 最大值
def load_call_attempt_count(events_path) -> int: ...          # 数 kind=="call_attempt" 行数（含成功调用）
def resolve_method(profile_name: str | None, explicit_method: str | None) -> str:
    """profile 给定时返回 derive_method(profile)；显式 --method 与推导值冲突 → SystemExit(2)；
    未给 profile → explicit_method or "direct_choice"（旧行为）。"""

# resume manifest（设计 L168：temperature/模板/代码/数据哈希不进 attempt key，由 manifest 约束）
RESUME_MANIFEST_FIELDS: tuple[str, ...] = (
    "dataset_sha256", "case_ids_sha256", "profile_id", "chart_schema_version",
    "arm", "repeat_idx", "provider", "model",
    "temperature", "sample_temperature", "n_samples", "aggregate", "method",
    "prompt_template_sha256", "code_sha256", "scheduled_calls", "hard_cap",
)
def build_resume_manifest(args, profile) -> dict: ...      # 17 字段全集；case_ids_file 为 None 时该字段记 None
def check_resume_manifest(manifest_path, current: dict) -> None:
    """--resume 前置：字段完整性（k not in stored 记 "<MISSING>"）+ 逐字段全等，
    任一不一致打印 diff 后 SystemExit(2)，禁止续跑。"""
def _atomic_write_json(path, payload: dict) -> None: ...   # 临时文件 + os.replace
def _code_fingerprint() -> str: ...                        # 实验范围 6 文件 bytes 拼接 SHA-256
```

attempt 明细新增字段与 retry 事件格式（`attempt_key` 10 字段、`terminal_state`、`raw_response_path`）。events 每行 `{kind, attempt_key, retry_idx, error_type, timestamp}`，两种 kind：**`call_attempt`**——每次模型调用尝试（含成功与失败）在发起前写入，`retry_idx`/`error_type` 为 null，是 `calls_attempted` 跨 resume 恢复的唯一依据；**`model_call_failed`**——可重试失败后写入，`retry_idx` 从 1 计含首次，上限 3，跨 resume 不重置。预算语义：`scheduled_calls` + `hard_cap = compute_hard_cap(scheduled)`；每次模型调用尝试（含重试）先写 `call_attempt` 事件记账后调用；`calls_attempted` 达到 hard_cap 后禁止新尝试；仍有非终态逻辑 attempt → `BLOCKED_INCOMPLETE`：summary 写 `"status": "BLOCKED_INCOMPLETE"`、退出码 3、数据保留、追加预算须显式登记 manifest。

```python
# scripts/run_phase6_6a0_ablation.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class AblationConfig:
    run_id: str
    year: int
    root: Path
    enriched_path: Path
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    repeats: int = 3
    smoke_size: int = 20
    seed: int = 20260717
    as_of_date: str = "2026-07-17"
    stage_scheduled: int = 260
    stage_hard_cap: int = 290
    resume: bool = True

@dataclass(frozen=True)
class SliceRun:
    purpose: str                 # "smoke" | "main"
    repeat_idx: int              # smoke 固定 -1
    arm: str                     # "ctx_approved" | "ctx_legacy"
    group: str                   # "group_a" | "group_b" | "smoke"
    case_ids: tuple[str, ...]
    scheduled_calls: int
    hard_cap: int

def split_ab_ba(case_ids: list[str], seed: int) -> tuple[tuple[str, ...], tuple[str, ...]]: ...
def build_schedule(config: AblationConfig, case_ids: list[str]) -> list[SliceRun]:
    """smoke(20, cap 20, ctx_approved, group_a 题) + 每 repeat 4 切片：
    [group_a approved, group_a legacy, group_b legacy, group_b approved]，
    每切片 20 题 scheduled 20，cap 按 [23, 23, 22, 22] 分配；
    3 repeats 主切片 cap 和 270 + smoke 20 = 290 = stage_hard_cap。"""
def gate_verdict(delta_pp: float) -> str:
    """>= +2 → "ADOPT"；0 <= d < +2 → "ADOPT_FOUNDATION"；< 0 → "ROLLBACK"。"""
def run_ablation(config: AblationConfig, schedule: list[SliceRun], slice_runner=None) -> dict:
    """执行**给定的** schedule（函数内不得重建）；每切片启动前做 BudgetLedger 溢出检查
    （total + 该切片剩余额度 = hard_cap − attempted_for(slice_id)），完成后按 slice_id
    幂等记账；返回 {"status", ...}。"""
def run_slice(config: AblationConfig, slice_run: SliceRun):
    """单切片执行：run_dir = root/<arm>/runs/<run_id>/slice_{purpose}_{repeat_idx}_{group}/；
    --repeat-idx 原样透传（smoke 为 -1，禁止 max 修正）。"""

class BudgetLedger:
    """阶段总预算账本（config.root/budget/<run_id>.jsonl，root 默认 .tmp/phase6）：
    JSON dict 存储 slice_id → {"calls_attempted", "hard_cap", "timestamp"}；
    按 slice_id 幂等覆盖（resume 重跑同一切片不重复累计），record 取 max(旧值, 新值)
    防异常路径回退；**fail-closed**：JSON 损坏/结构错/非 int/负值/calls > cap
    一律抛 BudgetLedgerCorrupt（run_ablation 转 BLOCKED_INCOMPLETE）；
    写入经临时文件 + os.replace 原子替换；阶段总数 = 各 slice_id 最新值之和。"""
    def __init__(self, path: Path): ...
    def total_attempted(self) -> int: ...
    def attempted_for(self, slice_id: str) -> int: ...
    def record(self, slice_id: str, hard_cap: int, calls_attempted: int) -> None: ...

class BudgetLedgerCorrupt(Exception):
    """预算账本损坏：JSON 坏/结构错/非 int/负值/calls_attempted > hard_cap——fail-closed。"""
```

### 共享测试设施（`tests/phase6_helpers.py`，完整定义，各测试文件 import 使用）

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase6_6a0_ablation import AblationConfig


def make_case(case_id: str = "c1", answer: str = "B", person_id: str = "p1") -> dict:
    """最小合法 BaziQA case；chart_input 按需经 with_chart 注入。"""
    return {
        "case_id": case_id, "answer": answer, "domain": "wealth",
        "question": "命主财运如何？", "options": ["A 普通", "B 富裕", "C 破财", "D 平稳"],
        "source_year": "2024",
        "person": {
            "person_id": person_id, "name": f"命主{person_id}", "gender": "male",
            "birth": {"year": 1990, "month": 1, "day": 2, "hour": 3, "minute": 0, "place": "北京"},
        },
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


class RunnerEnv:
    """run_benchmark 进程内集成测试环境：monkeypatch 模型边界，脚本化成功/失败/崩溃。"""

    def __init__(self, tmp_path: Path, monkeypatch, n_cases: int = 4):
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.dataset = tmp_path / "cases.jsonl"
        self.detail = tmp_path / "detail.jsonl"
        self.events = tmp_path / "detail.events.jsonl"
        self.summary = tmp_path / "summary.json"
        write_jsonl(self.dataset, [make_case(f"c{i}") for i in range(n_cases)])
        self._script: list[tuple[str, object]] = []

    # ---- 模型脚本 ----
    def model_returns(self, text: str) -> None:
        self._script = [("ok", text)] * 1000

    def model_fails(self, times: int) -> None:
        self._script = [("fail", RuntimeError("model_call_failed: boom"))] * times + [("ok", "A")] * 1000

    def model_fails_then_crash(self, failures: int) -> None:
        """先 N 次可重试网络失败，再抛非重试异常模拟进程崩溃。"""
        self._script = (
            [("fail", RuntimeError("model_call_failed: net"))] * failures
            + [("crash", RuntimeError("unexpected crash"))]
        )

    def model_succeeds_then_crash(self, text: str, successes: int) -> None:
        """先 N 次成功返回，再抛非重试异常模拟进程崩溃（calls_attempted 恢复测试用）。"""
        self._script = [("ok", text)] * successes + [("crash", RuntimeError("unexpected crash"))]

    def _fake_call(self, messages, **kw):
        action, payload = self._script.pop(0)
        if action in ("fail", "crash"):
            raise payload
        return payload

    # ---- 运行 ----
    def run(self, resume: bool = False, model: str = "deepseek-chat",
            scheduled_calls: int | None = None, hard_cap: int | None = None,
            profile: str | None = None, extra_argv: list[str] | None = None) -> int:
        import run_benchmark_proxy  # tests 内薄封装：转发到 benchmark.runners.run_benchmark.main(argv)
        self.monkeypatch.setattr("claude_api.call_model_messages_sync", self._fake_call)
        argv = ["--dataset", str(self.dataset), "--model-runner", "--provider", "deepseek",
                "--model", model, "--case-details-jsonl", str(self.detail),
                "--output-dir", str(self.tmp)]
        if resume:
            argv.append("--resume")
        if scheduled_calls is not None:
            argv += ["--scheduled-calls", str(scheduled_calls)]
        if hard_cap is not None:
            argv += ["--hard-cap", str(hard_cap)]
        if profile:
            argv += ["--profile", profile]
        argv += extra_argv or []
        return run_benchmark_proxy.main(argv)

    def run_expect_crash(self, **kw) -> None:
        import pytest
        with pytest.raises(RuntimeError, match="unexpected crash"):
            self.run(**kw)

    def run_subprocess(self, argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "benchmark.runners.run_benchmark", *argv],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )

    # ---- 读取 ----
    def read_detail(self) -> list[dict]:
        if not self.detail.exists():
            return []
        return [json.loads(x) for x in self.detail.read_text(encoding="utf-8").splitlines() if x.strip()]

    def read_events(self, kind: str | None = None) -> list[dict]:
        if not self.events.exists():
            return []
        rows = [json.loads(x) for x in self.events.read_text(encoding="utf-8").splitlines() if x.strip()]
        if kind is not None:
            rows = [r for r in rows if r.get("kind") == kind]
        return rows


class RunnerSpy:
    """编排器 arm-run 边界探针：记录每次调用的 SliceRun 与 kwargs，返回脚本化结果。"""

    def __init__(self):
        self.calls: list = []

    def __call__(self, slice_run, **kwargs):
        self.calls.append(type("Call", (), {"slice": slice_run, "kwargs": kwargs}))
        return type("ArmRunResult", (), {"exit_code": 0, "records": [], "calls_attempted": 0})


def fake_config(**overrides) -> AblationConfig:
    base = dict(run_id="test-run", year=2024, root=Path(".tmp/phase6/test"),
                enriched_path=Path("enriched.jsonl"))
    base.update(overrides)
    return AblationConfig(**base)
```

（`run_benchmark_proxy`：若 `benchmark/runners/run_benchmark.py` 的入口不是 `main(argv)` 形式，Task 6 第一步先把 `main()` 重构为 `main(argv=None)` 可注入形式——argparse 支持传参，属向后兼容改动；并在 `tests/` 加 `run_benchmark_proxy.py` 薄封装。）

---

## Task 1：已批准上下文渲染器 `chart_context.py` + 快照 / denylist / 确定性测试

**目的**：落地设计 §4.2 的固定模板渲染（`approved_v1`）与旧上下文等价渲染（`legacy_v0`），消除"模型可见上下文不完整/不确定"变量。

**已核实的渲染目标（`benchmark/formatters/baziqa_prompt.py:1-32`）**：`format_birth_line(case)` 输出 = 身份 4 行（`姓名：`／`性别：`／`出生：`／`地点：`）+ 当 `chart_input.four_pillars` 存在时追加 `四柱：年柱 甲子，…` 与 `日主：X（Y，Z）` 两紧凑行。因此：

- `legacy_v0` = `format_birth_line(case)` **全量输出**（含紧凑四柱/日主行），即当前线上旧上下文；
- `approved_v1` 的身份头 = `format_birth_line` 输出的**前 4 行**（不含紧凑四柱/日主行，避免与批准字段段重复），随后接固定模板各段。

**两个决策记录（写入提交信息与最终报告，复审时确认）：**

1. **身份头策略 = `passthrough`**：approved_v1 身份头与 legacy_v0 前 4 行逐字节一致。理由：AB/BA 消融要求两臂唯一变量是批准字段段；若 approved 臂另换 subject ID 方案，身份呈现差异会成为第二变量。设计 §4.2.4 的"BaziQA 使用匿名化 subject ID"由数据集自身满足（`person.name` 形如"1980年广东出生女性"，已伪匿名化）。manifest 声明 `identity_strategy = "passthrough_pseudo_anonymized_dataset"`。
2. **神煞渲染规则 = 计算器输出按输入顺序全量渲染**：设计 §4.2.1 写"神煞（批准子集）"但未枚举子集，属设计缺口；本计划不发明子集，按 `shensha[]` 输入顺序全量渲染（确定性由输入顺序保证），作为决策记录呈现。

- [ ] **Step 1：提取完整 case fixture（3 个不同 person_id，含 `person` 与 `chart_input`）**

先写提取脚本 `.tmp/extract_phase6_fixtures.py`：

```python
import json
from pathlib import Path

rows = [
    json.loads(line)
    for line in Path("benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl")
    .read_text(encoding="utf-8").splitlines()
    if line.strip()
]
seen: dict[str, dict] = {}
for row in rows:
    pid = row["person"]["person_id"]
    if pid not in seen and row.get("chart_input"):
        seen[pid] = row
    if len(seen) == 3:
        break
assert len(seen) == 3, "不同 person_id 的 enriched 记录不足 3 条"
out = Path("tests/fixtures/phase6")
out.mkdir(parents=True, exist_ok=True)
for i, row in enumerate(seen.values(), 1):
    (out / f"case_sample_{i}.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
    )
print([r["person"]["person_id"] for r in seen.values()])
```

运行：

```powershell
python .tmp/extract_phase6_fixtures.py
```

验收：打印 3 个互不相同的 person_id；`tests/fixtures/phase6/case_sample_{1,2,3}.json` 各含完整 `person`（姓名/性别/嵌套 birth/place）与 `chart_input`。

- [ ] **Step 2：写失败测试 `tests/test_chart_context.py`（完整代码）**

```python
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.baziqa_prompt import format_birth_line
from benchmark.formatters.chart_context import (
    APPROVED_BAZI_FIELDS,
    approved_field_presence,
    render_chart_context,
)

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "phase6"
CASE_IDS = (1, 2, 3)
AS_OF = "2026-07-17"


def load_fixture(i: int) -> dict:
    return json.loads((FIXTURE_DIR / f"case_sample_{i}.json").read_text(encoding="utf-8"))


def identity_header(case: dict) -> str:
    """format_birth_line 输出的前 4 行（姓名/性别/出生/地点）。"""
    return "\n".join(format_birth_line(case).split("\n")[:4])


@pytest.mark.parametrize("i", CASE_IDS)
def test_legacy_v0_byte_identical_to_format_birth_line(i: int):
    case = load_fixture(i)
    assert render_chart_context(case, "legacy_v0") == format_birth_line(case)


@pytest.mark.parametrize("i", CASE_IDS)
def test_approved_v1_identity_header_byte_identical(i: int):
    case = load_fixture(i)
    assert render_chart_context(case, "approved_v1", as_of_date=AS_OF).startswith(
        identity_header(case)
    )


@pytest.mark.parametrize("i", CASE_IDS)
def test_approved_v1_golden_snapshot(i: int):
    golden = FIXTURE_DIR / f"approved_v1_case{i}.txt"
    rendered = render_chart_context(load_fixture(i), "approved_v1", as_of_date=AS_OF)
    if os.environ.get("PHASE6_UPDATE_GOLDEN") == "1":
        golden.write_text(rendered, encoding="utf-8")
    assert rendered == golden.read_text(encoding="utf-8")


def test_legacy_v0_golden_snapshot():
    golden = FIXTURE_DIR / "legacy_v0_case1.txt"
    rendered = render_chart_context(load_fixture(1), "legacy_v0")
    if os.environ.get("PHASE6_UPDATE_GOLDEN") == "1":
        golden.write_text(rendered, encoding="utf-8")
    assert rendered == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("i", CASE_IDS)
def test_render_deterministic_across_processes(i: int):
    fixture = FIXTURE_DIR / f"case_sample_{i}.json"
    code = (
        "import json,sys;sys.path.insert(0,'.');"
        "from benchmark.formatters.chart_context import render_chart_context;"
        f"case=json.load(open(r'{fixture}',encoding='utf-8'));"
        f"sys.stdout.write(render_chart_context(case,'approved_v1',as_of_date='{AS_OF}'))"
    )
    outs = [
        subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, cwd=PROJECT_ROOT
        ).stdout
        for _ in range(2)
    ]
    assert outs[0] == outs[1]
    assert outs[0] == render_chart_context(load_fixture(i), "approved_v1", as_of_date=AS_OF)


def test_as_of_date_does_not_change_output():
    """approved_v1 无日期相关字段：as_of_date 仅入 manifest，不影响渲染。"""
    case = load_fixture(1)
    assert render_chart_context(case, "approved_v1", as_of_date="2026-07-17") == (
        render_chart_context(case, "approved_v1", as_of_date="2099-01-01")
    )


def test_denylist_values_never_rendered():
    case = load_fixture(1)
    case["chart_input"]["liu_nian"] = [{"year": 2099, "gan_zhi": "SENTINEL_LIUNIAN"}]
    for pillar in case["chart_input"]["four_pillars"].values():
        pillar["kong_wang"] = "SENTINEL_KONGWANG"
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert "SENTINEL_LIUNIAN" not in rendered
    assert "SENTINEL_KONGWANG" not in rendered


def test_unknown_schema_version_raises():
    with pytest.raises(ValueError, match="unknown schema_version"):
        render_chart_context(load_fixture(1), "v999")


@pytest.mark.parametrize("i", CASE_IDS)
def test_approved_field_presence_full(i: int):
    presence = approved_field_presence(load_fixture(i)["chart_input"])
    assert set(presence) == set(APPROVED_BAZI_FIELDS)
    missing = [k for k, ok in presence.items() if not ok]
    assert not missing, f"批准字段缺失: {missing}"


def test_approved_field_presence_partial():
    presence = approved_field_presence({"four_pillars": {}})
    assert presence["four_pillars"] is False
    assert presence["da_yun"] is False


@pytest.mark.parametrize("i", CASE_IDS)
def test_ziwei_section_rendered_when_present(i: int):
    case = load_fixture(i)
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    if case["chart_input"].get("ziwei"):
        assert "【紫微斗数·本命】" in rendered
```

- [ ] **Step 3：运行确认全部失败**

```powershell
python -m pytest tests/test_chart_context.py -q
```

预期：`ModuleNotFoundError: No module named 'benchmark.formatters.chart_context'`（golden 测试也不例外，因为 import 阶段即失败）。

- [ ] **Step 4：实现 `benchmark/formatters/chart_context.py`（完整代码）**

key 路径均经真实 enriched 数据核实（`four_pillars.<year|month|day|hour>.{gan,zhi,gan_wuxing,zhi_wuxing,shi_shen_gan,shi_shen_zhi_main,cang_gan[],cang_gan_shi_shen[],nayin,kong_wang占位}`、`day_master.{gan,wuxing,yinyang,shier_changsheng}`、`da_yun[].{index,gan,zhi,start_age,end_age,shi_shen_gan,shi_shen_zhi,is_current}`、`dayun_summary.{direction,starting_age,current_pillar}`、`tai_yuan/ming_gong/shen_gong.{gan,zhi,nayin}`、`true_solar_info.{original_time,adjusted_time,adjustment_minutes,method,location_matched}`、`shensha[].{name,position,meaning}`、`branch_relations[].{type,pillars,detail}`、`wuxing_stats.{jin,mu,shui,huo,tu,missing,strongest,weakest}`、`shishen_stats.{counts,missing,missing_human}`、`nayin_wuxing.{year,month,day,hour}`、`ziwei.{basic_info,twelve_palaces,si_hua}`）：

```python
"""Phase 6A0 已批准命盘上下文渲染器（schema 版本化，确定性输出）。

确定性契约：同一 case + 同一 schema_version + 同一 as_of_date → 跨进程逐字节一致。
denylist：kong_wang / liu_nian（含 four_pillars.<pillar>.kong_wang 占位键）永不读取。
"""
from __future__ import annotations

import json

from benchmark.formatters.baziqa_prompt import format_birth_line

CHART_CONTEXT_TEMPLATE_VERSION = "approved_v1"
SCHEMA_VERSIONS = ("legacy_v0", "approved_v1")

APPROVED_BAZI_FIELDS: tuple[str, ...] = (
    "four_pillars",
    "day_master",
    "nayin_wuxing",
    "wuxing_stats",
    "shishen_stats",
    "branch_relations",
    "shensha",
    "da_yun",
    "tai_yuan",
    "ming_gong",
    "shen_gong",
    "true_solar_info",
)
DENYLIST_FIELDS: tuple[str, ...] = ("kong_wang", "liu_nian")

_PILLAR_ORDER = ("year", "month", "day", "hour")
_PILLAR_LABEL = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
_WUXING_ORDER = ("jin", "mu", "shui", "huo", "tu")
_WUXING_LABEL = {"jin": "金", "mu": "木", "shui": "水", "huo": "火", "tu": "土"}


def render_chart_context(
    case: dict,
    schema_version: str = CHART_CONTEXT_TEMPLATE_VERSION,
    as_of_date: str | None = None,
) -> str:
    """case 为完整题目记录（含 person 与 chart_input）。

    legacy_v0   → 与 format_birth_line(case) 逐字节一致；
    approved_v1 → 身份头 4 行（与 format_birth_line 前 4 行逐字节一致）
                  + 固定模板渲染 chart_input 批准字段；
                  chart_input.ziwei 存在时追加本命紫微宫位段。
    as_of_date 当前不影响 approved_v1 输出（无日期相关批准字段），仅入 manifest。
    """
    if schema_version == "legacy_v0":
        return format_birth_line(case)
    if schema_version != "approved_v1":
        raise ValueError(f"unknown schema_version: {schema_version!r}")
    chart = case.get("chart_input") or {}
    # 按"键存在"渲染：BaziQA enriched 全键（空列表字段也渲染"无"段）；
    # MingLi 归一化输入仅含部分八字键，缺失段跳过（可见性由 profiles 矩阵按 profile 断言）。
    sections = [_identity_header(case)]
    if "four_pillars" in chart:
        sections.append(_render_four_pillars(chart["four_pillars"]))
    if "day_master" in chart:
        sections.append(_render_day_master(chart["day_master"]))
    if "da_yun" in chart:
        sections.append(_render_da_yun(chart["da_yun"], chart.get("dayun_summary") or {}))
    if all(k in chart for k in ("tai_yuan", "ming_gong", "shen_gong")):
        sections.append(_render_three_palaces(chart))
    if "true_solar_info" in chart:
        sections.append(_render_true_solar(chart["true_solar_info"]))
    if "nayin_wuxing" in chart:
        sections.append(_render_nayin(chart["nayin_wuxing"]))
    if "wuxing_stats" in chart:
        sections.append(_render_wuxing_stats(chart["wuxing_stats"]))
    if "shishen_stats" in chart:
        sections.append(_render_shishen_stats(chart["shishen_stats"]))
    if "branch_relations" in chart:
        sections.append(_render_branch_relations(chart["branch_relations"]))
    if "shensha" in chart:
        sections.append(_render_shensha(chart["shensha"]))
    if chart.get("ziwei"):
        sections.append(_render_ziwei(chart["ziwei"]))
    return "\n\n".join(sections) + "\n"


def approved_field_presence(chart_input: dict) -> dict[str, bool]:
    """返回 APPROVED_BAZI_FIELDS 每项在 chart_input 中是否有可用数据。"""
    fp = chart_input.get("four_pillars") or {}
    fp_ok = all(
        key in fp
        and all(
            sub in fp[key]
            for sub in (
                "gan", "zhi", "gan_wuxing", "zhi_wuxing", "shi_shen_gan",
                "shi_shen_zhi_main", "cang_gan", "cang_gan_shi_shen", "nayin",
            )
        )
        for key in _PILLAR_ORDER
    )
    nayin = chart_input.get("nayin_wuxing") or {}
    return {
        "four_pillars": fp_ok,
        "day_master": bool(chart_input.get("day_master")),
        "nayin_wuxing": all(k in nayin for k in _PILLAR_ORDER),
        "wuxing_stats": bool(chart_input.get("wuxing_stats")),
        "shishen_stats": bool(chart_input.get("shishen_stats")),
        "branch_relations": "branch_relations" in chart_input,
        "shensha": "shensha" in chart_input,
        "da_yun": bool(chart_input.get("da_yun")),
        "tai_yuan": bool(chart_input.get("tai_yuan")),
        "ming_gong": bool(chart_input.get("ming_gong")),
        "shen_gong": bool(chart_input.get("shen_gong")),
        "true_solar_info": bool(chart_input.get("true_solar_info")),
    }


def _identity_header(case: dict) -> str:
    """与 format_birth_line 前 4 行逐字节一致（姓名/性别/出生/地点）。"""
    return "\n".join(format_birth_line(case).split("\n")[:4])


def _render_four_pillars(fp: dict) -> str:
    lines = ["【四柱】"]
    for key in _PILLAR_ORDER:
        p = fp[key]
        cang = "、".join(
            f"{gan}({shen})" for gan, shen in zip(p["cang_gan"], p["cang_gan_shi_shen"])
        )
        lines.append(
            f"{_PILLAR_LABEL[key]}：{p['gan']}{p['zhi']}"
            f"（{p['gan']}·{p['gan_wuxing']}／{p['zhi']}·{p['zhi_wuxing']}）"
            f" 十神：{p['shi_shen_gan']}／{p['shi_shen_zhi_main']}（主气）"
            f" 藏干：{cang} 纳音：{p['nayin']}"
        )
    return "\n".join(lines)


def _render_day_master(dm: dict) -> str:
    return (
        "【日主】\n"
        f"日主：{dm['gan']}（{dm['wuxing']}·{dm['yinyang']}）"
        f" 十二长生：{dm['shier_changsheng']}"
    )


def _render_da_yun(da_yun: list, summary: dict) -> str:
    lines = ["【大运】"]
    lines.append(
        f"起运：{summary.get('starting_age', '')}岁（{summary.get('direction', '')}）"
        f" 当前大运：{summary.get('current_pillar', '')}"
    )
    for item in da_yun:
        mark = "〔当前〕" if item.get("is_current") else ""
        lines.append(
            f"{item['index']}. {item['gan']}{item['zhi']}"
            f"（{item['start_age']}-{item['end_age']}岁）"
            f" 十神：{item['shi_shen_gan']}／{item['shi_shen_zhi']}{mark}"
        )
    return "\n".join(lines)


def _render_three_palaces(chart: dict) -> str:
    ty, mg, sg = chart["tai_yuan"], chart["ming_gong"], chart["shen_gong"]
    return (
        "【胎元／命宫／身宫】\n"
        f"胎元：{ty['gan']}{ty['zhi']}（{ty['nayin']}）"
        f" 命宫：{mg['gan']}{mg['zhi']}（{mg['nayin']}）"
        f" 身宫：{sg['gan']}{sg['zhi']}（{sg['nayin']}）"
    )


def _render_true_solar(ts: dict) -> str:
    matched = ts["location_matched"]
    matched_text = ("是" if matched else "否") if isinstance(matched, bool) else str(matched)
    return (
        "【真太阳时校正】\n"
        f"原时间：{ts['original_time']} 校正后：{ts['adjusted_time']}"
        f"（{ts['adjustment_minutes']}分钟，方法：{ts['method']}，地点匹配：{matched_text}）"
    )


def _render_nayin(nayin: dict) -> str:
    return (
        "【纳音五行】\n"
        + "　".join(f"{_PILLAR_LABEL[k]}：{nayin[k]}" for k in _PILLAR_ORDER)
    )


def _render_wuxing_stats(ws: dict) -> str:
    counts = " ".join(f"{_WUXING_LABEL[k]}{ws[k]}" for k in _WUXING_ORDER)
    missing = "、".join(str(x) for x in ws["missing"]) if ws["missing"] else "无"
    return (
        "【五行统计】\n"
        f"{counts}；缺：{missing}；最旺：{ws['strongest']}；最弱：{ws['weakest']}"
    )


def _render_shishen_stats(ss: dict) -> str:
    counts = " ".join(f"{name}{num}" for name, num in ss["counts"].items())
    missing = "、".join(str(x) for x in ss["missing"]) if ss["missing"] else "无"
    return f"【十神统计】\n{counts}；缺：{missing}"


def _render_branch_relations(relations: list) -> str:
    lines = ["【地支关系】"]
    if not relations:
        lines.append("无")
    for rel in relations:
        pillars = "、".join(str(x) for x in rel["pillars"])
        lines.append(f"{rel['type']}：{pillars}（{rel['detail']}）")
    return "\n".join(lines)


def _render_shensha(shensha: list) -> str:
    lines = ["【神煞】"]
    if not shensha:
        lines.append("无")
    for item in shensha:
        lines.append(f"{item['name']}（{item['position']}）：{item['meaning']}")
    return "\n".join(lines)


def _star_names(stars: list) -> str:
    names = [str(s.get("name", "")) if isinstance(s, dict) else str(s) for s in stars]
    return "、".join(n for n in names if n) or "无"


def _fmt_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _render_ziwei(ziwei: dict) -> str:
    info = ziwei["basic_info"]
    lines = ["【紫微斗数·本命】"]
    lines.append(
        f"命宫：{info['ming_gong_gan_zhi']} 身宫：{info['shen_gong_position']}"
        f" 五行局：{info['wu_xing_ju']} 命主：{info['ming_zhu']} 身主：{info['shen_zhu']}"
    )
    for palace in ziwei["twelve_palaces"]:
        mains = "、".join(
            f"{s['name']}（{s['brightness']}）" for s in palace["main_stars"]
        ) or "无"
        sg = "〔身宫〕" if palace.get("is_shengong") else ""
        lines.append(
            f"{palace['name']}（{palace['position']}·{palace['tian_gan']}）{sg}"
            f" 主星：{mains} 辅星：{_star_names(palace['auxiliary_stars'])}"
            f" 大限：{_fmt_value(palace['daxian'])}"
        )
    si_hua = ziwei.get("si_hua")
    if si_hua:
        lines.append("四化：" + json.dumps(si_hua, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)
```

- [ ] **Step 5：生成 golden 快照并人工复核**

```powershell
$env:PHASE6_UPDATE_GOLDEN="1"
python -m pytest tests/test_chart_context.py -q
Remove-Item Env:PHASE6_UPDATE_GOLDEN
```

人工 diff 4 个 golden 文件（`approved_v1_case{1,2,3}.txt`、`legacy_v0_case1.txt`）：确认无 `kong_wang`/`liu_nian` 内容、身份头正确、批准字段各段齐全、紫微段存在。复核后再次运行必须全绿：

```powershell
python -m pytest tests/test_chart_context.py -q
```

- [ ] **Step 6：提交（精确路径，禁止 `git add tests/`）**

```powershell
git add benchmark/formatters/chart_context.py tests/test_chart_context.py tests/fixtures/phase6/case_sample_1.json tests/fixtures/phase6/case_sample_2.json tests/fixtures/phase6/case_sample_3.json tests/fixtures/phase6/approved_v1_case1.txt tests/fixtures/phase6/approved_v1_case2.txt tests/fixtures/phase6/approved_v1_case3.txt tests/fixtures/phase6/legacy_v0_case1.txt
git commit -m "feat(phase6): 6A0 已批准上下文渲染器（schema 版本化 + denylist + 快照）"
```

---

## Task 2：防泄漏分级扫描 `leak_scan.py`

**目的**：落地设计 §4.2.4——硬失败三类（答案元数据、选项块外额外暴露正确选项、历史评测结果），明确豁免正常 A/B/C/D 选项块与身份字段。纯函数，供编排器离线 gate 与 runner 运行期抽查共用。

- [ ] **Step 1：写失败测试 `tests/test_leak_scan.py`（完整代码）**

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.leak_scan import scan_prompt_for_leaks
from tests.phase6_helpers import make_case


def base_prompt(case: dict) -> str:
    opts = "\n".join(case["options"])
    return (
        "你是一位严谨的八字命理评测助手。\n"
        f"## 命主信息\n姓名：{case['person']['name']}\n"
        f"## 问题\n{case['question']}\n## 选项\n{opts}\n请直接回答选项字母。"
    )


def test_clean_prompt_no_hits():
    case = make_case()
    assert scan_prompt_for_leaks(base_prompt(case), case) == []


def test_answer_metadata_hard_fail():
    case = make_case()
    hits = scan_prompt_for_leaks(base_prompt(case) + "\n正确答案：B", case)
    assert any(h.kind == "answer_metadata" for h in hits)


def test_eval_result_hard_fail():
    case = make_case()
    hits = scan_prompt_for_leaks(base_prompt(case) + "\n上届选手准确率 80%", case)
    assert any(h.kind == "eval_result" for h in hits)


def test_extra_exposure_hard_fail():
    case = make_case(answer="B")  # options[1] = "B 富裕"
    prompt = base_prompt(case) + "\n解析：本例应选富裕，理由略。"
    hits = scan_prompt_for_leaks(prompt, case)
    assert any(h.kind == "extra_exposure" for h in hits)


def test_options_block_is_exempt():
    # 正常选项块必然包含正确选项文本，不产生任何 hit
    case = make_case()
    assert scan_prompt_for_leaks(base_prompt(case), case) == []


def test_identity_fields_exempt():
    case = make_case()
    prompt = base_prompt(case) + "\n补充：命主 1990年1月2日 出生于北京。"
    assert scan_prompt_for_leaks(prompt, case) == []
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_leak_scan.py -q` → `ModuleNotFoundError`。

- [ ] **Step 3：实现 `benchmark/formatters/leak_scan.py`（完整代码）**

```python
"""防泄漏分级扫描（设计 §4.2.4）。

硬失败三类：answer_metadata / extra_exposure / eval_result。
明确豁免：正常 A/B/C/D 选项块（必含正确选项文本）、身份字段（姓名/出生/地点，
属输入协议声明项）。纯函数；命中即 LeakHit，由调用方决定 gate 失败。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LeakHit:
    kind: str  # "answer_metadata" | "extra_exposure" | "eval_result"
    detail: str


_ANSWER_METADATA_PATTERNS = (
    re.compile(r"(?i)\bcorrect[_\s]?answer\b"),
    re.compile(r"(?i)\banswer[_\s]?key\b"),
    re.compile(r"正确答案"),
    re.compile(r"标准答案"),
    re.compile(r"答案[:：]"),
)
_EVAL_RESULT_PATTERNS = (
    re.compile(r"准确率"),
    re.compile(r"得分率"),
    re.compile(r"(?i)\baccuracy\b"),
    re.compile(r"赛事排名"),
    re.compile(r"历届.{0,12}(答对|正确率)"),
)


def scan_prompt_for_leaks(prompt: str, case: dict) -> list[LeakHit]:
    hits: list[LeakHit] = []
    for pat in _ANSWER_METADATA_PATTERNS:
        m = pat.search(prompt)
        if m:
            hits.append(LeakHit("answer_metadata", f"命中答案元数据 {pat.pattern!r} @{m.start()}"))
    for pat in _EVAL_RESULT_PATTERNS:
        m = pat.search(prompt)
        if m:
            hits.append(LeakHit("eval_result", f"命中评测结果 {pat.pattern!r} @{m.start()}"))
    hits.extend(_scan_extra_exposure(prompt, case))
    return hits


def _option_core(option: str) -> str:
    """去掉字母前缀的选项核心文本（'A 普通' → '普通'）。"""
    text = str(option)
    if text[:1] in "ABCD" and len(text) > 1 and text[1] in " .、　":
        return text[2:].strip() if text[1] == " " else text[1:].strip(" .、　")
    return text


def _scan_extra_exposure(prompt: str, case: dict) -> list[LeakHit]:
    answer = str(case.get("answer") or "")
    options = case.get("options") or []
    idx = "ABCD".find(answer)
    if idx < 0 or idx >= len(options):
        return []
    core = _option_core(options[idx])
    if len(core) < 2:
        return []
    spans = [m.span() for m in re.finditer(re.escape(core), prompt)]
    if len(spans) <= 1:
        return []  # 仅在选项块内出现一次
    block = _options_block_span(prompt, options)
    outside = [
        s for s in spans
        if block is None or s[0] < block[0] or s[0] >= block[1]
    ]
    if outside:
        return [LeakHit("extra_exposure", f"正确选项文本 {core!r} 在选项块外出现 {len(outside)} 次")]
    return []


def _options_block_span(prompt: str, options: list) -> tuple[int, int] | None:
    """包含全部选项核心文本的最小连续区域；任一缺失返回 None（保守判块外）。"""
    positions = []
    for opt in options:
        core = _option_core(opt)
        if not core:
            return None
        pos = prompt.find(core)
        if pos < 0:
            return None
        positions.append((pos, pos + len(core)))
    return min(p[0] for p in positions), max(p[1] for p in positions)
```

误报纪律：选项块外重复出现正确选项文本一律保守判硬失败；确属自然文本误报时人工复核记录，不自动豁免、不改扫描器放行。

- [ ] **Step 4：运行确认全绿** `python -m pytest tests/test_leak_scan.py -q`

- [ ] **Step 5：提交（精确路径）**

```powershell
git add benchmark/formatters/leak_scan.py tests/test_leak_scan.py
git commit -m "feat(phase6): 防泄漏分级扫描（三类硬失败 + 选项块/身份豁免）"
```

---

## Task 3：Phase 6 enrichment 薄封装 `scripts/enrich_phase6_chart_input.py`

**目的**：落地设计 §3.1/§4.5——固定 `as_of_date`、输出 `.tmp/phase6/datasets/`、SHA-256 manifest、批准字段覆盖率 100% 校验；2023 默认排除（密封）。复用 `scripts/enrich_baziqa_chart_input.py` 的 `enrich_row` / `load_jsonl` / `write_jsonl`（已核实签名：`enrich_row(row, compute_chart_fn=compute_chart)`，`compute_chart(year, month, day, hour, minute, gender, place)`）。

**已知易变字段纪律（写入报告）**：`da_yun[].is_current` 与 `dayun_summary.current_pillar` 随运行日期漂移；enrichment 产物对同一运行日确定，跨日再生成时这些字段与文件 SHA-256 可能变化，属预期。**配对实验两臂必须共用同一 enriched 文件与 manifest 条目，禁止两臂各自生成。**

- [ ] **Step 1：写失败测试 `tests/test_enrich_phase6_chart_input.py`（完整代码）**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.enrich_phase6_chart_input as enrich6


def fake_chart(year, month, day, hour, minute, gender, place) -> dict:
    """满足批准字段 presence 的最小合成 chart_input。"""
    pillar = {
        "gan": "甲", "zhi": "子", "gan_wuxing": "木", "zhi_wuxing": "水",
        "shi_shen_gan": "比肩", "shi_shen_zhi_main": "正印",
        "cang_gan": ["癸"], "cang_gan_shi_shen": ["正印"],
        "nayin": "海中金", "kong_wang": "占位",
    }
    return {
        "four_pillars": {k: dict(pillar) for k in ("year", "month", "day", "hour")},
        "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳", "shier_changsheng": "沐浴"},
        "nayin_wuxing": {k: "海中金" for k in ("year", "month", "day", "hour")},
        "wuxing_stats": {"jin": 1, "mu": 2, "shui": 1, "huo": 2, "tu": 2,
                         "missing": [], "strongest": "木", "weakest": "金"},
        "shishen_stats": {"counts": {"比肩": 2}, "missing": [], "missing_human": ""},
        "branch_relations": [],
        "shensha": [{"name": "天乙贵人", "position": "年干", "meaning": "主贵人扶助"}],
        "da_yun": [{"index": 1, "gan": "丙", "zhi": "寅", "start_age": 3, "end_age": 12,
                    "shi_shen_gan": "食神", "shi_shen_zhi": "比肩", "is_current": False}],
        "tai_yuan": {"gan": "乙", "zhi": "卯", "nayin": "大溪水"},
        "ming_gong": {"gan": "丙", "zhi": "辰", "nayin": "沙中土"},
        "shen_gong": {"gan": "丁", "zhi": "巳", "nayin": "沙中土"},
        "true_solar_info": {"original_time": "1990-01-02 03:00", "adjusted_time": "1990-01-02 02:48",
                            "adjustment_minutes": -12, "method": "经度修正", "location_matched": True},
        "liu_nian": [{"year": 2099, "gan_zhi": "SENTINEL"}],  # 计算器固有输出，denylist 不读
    }


def make_row(case_id: str) -> dict:
    return {
        "case_id": case_id, "answer": "B", "domain": "wealth",
        "question": "q", "options": ["A 甲", "B 乙", "C 丙", "D 丁"], "source_year": "2021",
        "person": {"person_id": f"p_{case_id}", "name": "某", "gender": "male",
                   "birth": {"year": 1990, "month": 1, "day": 2, "hour": 3, "minute": 0, "place": "北京"}},
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    src = tmp_path / "benchmark" / "datasets"
    src.mkdir(parents=True)
    for year in (2021, 2022, 2023):
        rows = [make_row(f"{year}_c{i}") for i in range(2)]
        (src / f"baziqa_contest8_{year}_holdout.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    monkeypatch.setattr(enrich6, "compute_chart", fake_chart)
    return tmp_path


def run_main(env_tmp, argv):
    out_dir = env_tmp / "out"
    manifest = env_tmp / "manifest.json"
    return enrich6.main([*argv, "--out-dir", str(out_dir), "--manifest", str(manifest)]), out_dir, manifest


def test_enrich_years_and_manifest(env):
    code, out_dir, manifest = run_main(env, ["--years", "2021", "2022", "--as-of-date", "2026-07-17"])
    assert code == 0
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["as_of_date"] == "2026-07-17"
    assert m["includes_sealed_2023"] is False
    assert [e["year"] for e in m["entries"]] == [2021, 2022]
    for entry in m["entries"]:
        assert len(entry["source_sha256"]) == 64
        assert len(entry["output_sha256"]) == 64
        assert all(v.endswith("/2") and v.startswith("2/") for v in entry["approved_coverage"].values())
    rows = [json.loads(x) for x in (out_dir / "baziqa_contest8_2021_holdout_enriched.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert all(r.get("chart_input") for r in rows)


def test_2023_rejected_by_default(env):
    with pytest.raises(SystemExit):
        run_main(env, ["--years", "2023", "--as-of-date", "2026-07-17"])


def test_include_2023_flag(env):
    code, _, manifest = run_main(
        env, ["--years", "2021", "--include-2023", "--as-of-date", "2026-07-17"]
    )
    assert code == 0
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["includes_sealed_2023"] is True
    assert 2023 in [e["year"] for e in m["entries"]]


def test_coverage_shortfall_fails_closed(env, monkeypatch):
    def broken_chart(*a, **kw):
        chart = fake_chart(*a, **kw)
        del chart["da_yun"]
        return chart
    monkeypatch.setattr(enrich6, "compute_chart", broken_chart)
    with pytest.raises(SystemExit, match="批准字段覆盖率未达 100%"):
        run_main(env, ["--years", "2021", "--as-of-date", "2026-07-17"])


def test_strip_denylisted():
    obj = {"a": {"kong_wang": 1, "b": [{"liu_nian": 2, "c": 3}]}}
    assert enrich6.strip_denylisted(obj) == {"a": {"b": [{"c": 3}]}}
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_enrich_phase6_chart_input.py -q` → `ModuleNotFoundError`。

- [ ] **Step 3：实现 `scripts/enrich_phase6_chart_input.py`（完整代码）**

```python
"""Phase 6A0 enrichment 薄封装：固定 as_of_date、输出 .tmp/phase6/datasets/、SHA-256 manifest。

不修改 benchmark/datasets/ 原始文件；2023 默认排除（密封），--include-2023 仅生成
输入侧 chart_input，不等于打开评测。enrich_row 对已有 chart_input 的行幂等跳过；
计算器异常（TypeError/ValueError/KeyError）时该行无 chart_input，由覆盖率门禁 fail-closed。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from bazi_calculator import compute_chart
from benchmark.formatters.chart_context import APPROVED_BAZI_FIELDS, approved_field_presence
from scripts.enrich_baziqa_chart_input import enrich_row, load_jsonl, write_jsonl

DEFAULT_YEARS = (2021, 2022, 2024, 2025)
SEALED_YEAR = 2023
DATASET_TEMPLATE = "benchmark/datasets/baziqa_contest8_{year}_holdout.jsonl"
OUTPUT_TEMPLATE = "baziqa_contest8_{year}_holdout_enriched.jsonl"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_denylisted(obj):
    """递归删除 denylist 键（kong_wang / liu_nian），用于跨版本一致性比较。"""
    if isinstance(obj, dict):
        return {
            k: strip_denylisted(v)
            for k, v in obj.items()
            if k not in ("kong_wang", "liu_nian")
        }
    if isinstance(obj, list):
        return [strip_denylisted(v) for v in obj]
    return obj


def enrich_year(year: int, as_of_date: str, out_dir: Path, root: Path = PROJECT_ROOT) -> dict:
    src = root / DATASET_TEMPLATE.format(year=year)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / OUTPUT_TEMPLATE.format(year=year)
    rows = [enrich_row(r, compute_chart) for r in load_jsonl(src)]
    write_jsonl(dst, rows)
    total = len(rows)
    if total == 0:
        raise SystemExit(f"空数据集：{src}")
    coverage: dict[str, int] = {}
    for row in rows:
        chart = row.get("chart_input") or {}
        for field, ok in approved_field_presence(chart).items():
            coverage[field] = coverage.get(field, 0) + int(ok)
    missing = {k: total - v for k, v in coverage.items() if v != total}
    if missing:
        raise SystemExit(f"批准字段覆盖率未达 100%: {missing}（{year}）")
    return {
        "year": year,
        "source_path": str(src.relative_to(root)),
        "source_sha256": sha256_file(src),
        "output_path": str(dst.relative_to(root)),
        "output_sha256": sha256_file(dst),
        "row_count": total,
        "approved_fields": list(APPROVED_BAZI_FIELDS),
        "approved_coverage": {k: f"{v}/{total}" for k, v in sorted(coverage.items())},
        "as_of_date": as_of_date,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 enrichment 薄封装")
    parser.add_argument("--years", type=int, nargs="*", default=list(DEFAULT_YEARS))
    parser.add_argument("--include-2023", action="store_true")
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--out-dir", type=Path, default=Path(".tmp/phase6/datasets"))
    parser.add_argument("--manifest", type=Path, default=Path(".tmp/phase6/enrich_manifest.json"))
    args = parser.parse_args(argv)

    years = sorted(set(args.years))
    if args.include_2023:
        years = sorted(set(years) | {SEALED_YEAR})
    elif SEALED_YEAR in years:
        raise SystemExit(
            "2023 为密封集：需显式 --include-2023（仅生成输入侧 chart_input，不等于打开评测）"
        )

    entries = [enrich_year(y, args.as_of_date, args.out_dir) for y in years]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": args.as_of_date,
        "includes_sealed_2023": args.include_2023,
        "identity_strategy": "passthrough_pseudo_anonymized_dataset",
        "note": "chart_input 中 kong_wang/liu_nian 为计算器固有输出，渲染层 denylist 永不读取",
        "entries": entries,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"years": [e["year"] for e in entries], "manifest": str(args.manifest)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4：运行确认全绿** `python -m pytest tests/test_enrich_phase6_chart_input.py -q`

- [ ] **Step 5：真实 enrichment（2021/2022/2024/2025，真实计算器，无网络）**

```powershell
python scripts/enrich_phase6_chart_input.py --as-of-date 2026-07-17
```

验收：`.tmp/phase6/datasets/` 四个 enriched 文件；`.tmp/phase6/enrich_manifest.json` 覆盖率全部 `40/40`（各年度题量以实际为准）；打印 years = [2021, 2022, 2024, 2025]。

- [ ] **Step 6：与已提交 2024/2025 enriched 的一致性核对（denylist 剔除后）**

```powershell
python -c "import json,sys;sys.path.insert(0,'.');from scripts.enrich_phase6_chart_input import strip_denylisted;old=[json.loads(x) for x in open('benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl',encoding='utf-8')];new=[json.loads(x) for x in open('.tmp/phase6/datasets/baziqa_contest8_2024_holdout_enriched.jsonl',encoding='utf-8')];diff=[r['case_id'] for r,n in zip(old,new) if strip_denylisted(r.get('chart_input',{}).get('four_pillars',{}))!=strip_denylisted(n.get('chart_input',{}).get('four_pillars',{}))];print('four_pillars 不一致行:',diff)"
```

预期输出 `four_pillars 不一致行: []`；非空则说明计算器行为漂移，停下来人工复核，不得继续。`is_current`/`current_pillar` 等易变字段不在本断言内（纪律见上）。

- [ ] **Step 7：提交（精确路径；`.tmp/` 产物不入 Git）**

```powershell
git add scripts/enrich_phase6_chart_input.py tests/test_enrich_phase6_chart_input.py
git commit -m "feat(phase6): enrichment 薄封装（as_of_date + SHA-256 manifest + 覆盖率 fail-closed）"
```

---

## Task 4：五维 profile 注册表 `benchmark/runners/profiles.py` + 可见性矩阵

**目的**：落地设计 §4.3——profile 是 dataset / prompt_style / interaction_mode / chart_schema_version / scoring_profile 五维的唯一来源；可见性按 `(profile_id, chart_schema_version)` 二元组决定 required/forbidden（legacy 对照臂不被 approved 门禁误杀，串扰可被检出）。

**决策记录 3（复审确认）**：设计矩阵行 `mingli_* × approved_v1` 写"八字字段 + 紫微宫位名"。经核实 MingLi adapter 白名单（`mingli_bench_adapter.py:36`）只可能提供八字核心六字段（`four_pillars/day_master/shishen_stats/wuxing_stats/branch_relations/shensha`），`da_yun/胎命身宫/真太阳时/纳音` 源数据没有。MingLi 的 required 因此定义为**八字核心六字段段标 + 紫微宫位名**，缺口字段作为 MingLi 线已知限制写入 manifest 与报告——不虚构、不静默放宽：若勘察后确认连核心六字段也不全，记 BLOCKED 发现并向用户汇报。

**任务边界**：本任务只交付 profiles 模块与纯函数单测；runner 接线（`--profile`、`resolve_method`、四条端到端路由测试）在 Task 6。

- [ ] **Step 1：写失败测试 `tests/test_phase6_profiles.py`（完整代码）**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.chart_context import render_chart_context
from benchmark.runners.profiles import (
    PROFILES,
    assert_visibility,
    derive_formatter,
    derive_method,
    prompt_fingerprint,
    resolve_profile,
)

FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "phase6" / "case_sample_1.json"
AS_OF = "2026-07-17"


def load_case() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_four_named_configs_five_dims():
    expected = {
        "baziqa_official_multi_turn": ("baziqa", "official", "multi_turn", "approved_v1", "baziqa_macro"),
        "baziqa_xjz_direct": ("baziqa", "xjz_direct", "direct", "approved_v1", "baziqa_macro"),
        "mingli_official_cot_astro": ("mingli", "official", "direct", "approved_v1", "mingli_trimmed"),
        "mingli_xjz_direct": ("mingli", "xjz_direct", "direct", "approved_v1", "mingli_trimmed"),
    }
    assert set(PROFILES) == set(expected)
    for pid, dims in expected.items():
        p = PROFILES[pid]
        assert (p.dataset, p.prompt_style, p.interaction_mode,
                p.chart_schema_version, p.scoring_profile) == dims


def test_resolve_profile_schema_override():
    p = resolve_profile("baziqa_xjz_direct", "legacy_v0")
    assert p.chart_schema_version == "legacy_v0"
    assert p.dataset == "baziqa"


def test_resolve_profile_unknown_exits():
    with pytest.raises(SystemExit):
        resolve_profile("nope")
    with pytest.raises(SystemExit):
        resolve_profile("baziqa_xjz_direct", "v999")


def test_derive_method_mapping():
    assert derive_method(resolve_profile("baziqa_official_multi_turn")) == "multi_turn"
    for pid in ("baziqa_xjz_direct", "mingli_official_cot_astro", "mingli_xjz_direct"):
        assert derive_method(resolve_profile(pid)) == "direct_choice"


def test_derive_formatter_all_four():
    assert derive_formatter(resolve_profile("baziqa_official_multi_turn")) == "format_multi_turn"
    assert derive_formatter(resolve_profile("baziqa_xjz_direct")) == "format_direct_choice_prompt"
    assert derive_formatter(resolve_profile("mingli_official_cot_astro")) == "format_official_cot_prompt"
    assert derive_formatter(resolve_profile("mingli_xjz_direct")) == "format_direct_choice_prompt"


def test_visibility_baziqa_approved_passes_on_fixture():
    rendered = render_chart_context(load_case(), "approved_v1", as_of_date=AS_OF)
    assert assert_visibility(rendered, resolve_profile("baziqa_xjz_direct"), "approved_v1") == []


def test_visibility_mingli_approved_requires_ziwei():
    case = load_case()
    profile = resolve_profile("mingli_xjz_direct")
    if case["chart_input"].get("ziwei"):
        rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
        assert assert_visibility(rendered, profile, "approved_v1") == []
    case["chart_input"].pop("ziwei", None)
    rendered_no_ziwei = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    violations = assert_visibility(rendered_no_ziwei, profile, "approved_v1")
    assert any("【紫微斗数·本命】" in v for v in violations)


def test_visibility_legacy_arm_anti_crosstalk():
    case = load_case()
    profile = resolve_profile("baziqa_xjz_direct", "legacy_v0")
    legacy = render_chart_context(case, "legacy_v0")
    assert assert_visibility(legacy, profile, "legacy_v0") == []
    approved = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    violations = assert_visibility(approved, profile, "legacy_v0")
    assert violations
    assert all(v.startswith("forbidden 命中") for v in violations)


def test_visibility_denylist_label_caught():
    rendered = render_chart_context(load_case(), "approved_v1", as_of_date=AS_OF)
    poisoned = rendered + "\n【流年】\n2027年：测试\n"
    violations = assert_visibility(poisoned, resolve_profile("baziqa_xjz_direct"), "approved_v1")
    assert any("【流年】" in v for v in violations)


def test_prompt_fingerprint_stable_and_sensitive(monkeypatch):
    """resume manifest 字段：指纹跨调用确定；模板常量任一变化 → 指纹变化。"""
    from benchmark.formatters import chart_context

    p = resolve_profile("baziqa_xjz_direct", "approved_v1")
    fp1 = prompt_fingerprint(p)
    assert prompt_fingerprint(p) == fp1
    monkeypatch.setattr(chart_context, "CHART_CONTEXT_TEMPLATE",
                        chart_context.CHART_CONTEXT_TEMPLATE + " ")
    assert prompt_fingerprint(p) != fp1
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_phase6_profiles.py -q` → `ModuleNotFoundError`。

- [ ] **Step 3：实现 `benchmark/runners/profiles.py`（完整代码）**

```python
"""五维评测 profile 注册表与路由（设计 §4.3）。profile 是五维唯一来源。

可见性矩阵按 (profile.dataset, chart_schema_version) 二元组决定 required/forbidden；
forbidden 只用"段标／字段标"级子串，避免神煞释义等自然文本误杀。
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class EvalProfile:
    profile_id: str
    dataset: str             # "baziqa" | "mingli"
    prompt_style: str        # "official" | "xjz_direct"
    interaction_mode: str    # "direct" | "multi_turn"
    chart_schema_version: str
    scoring_profile: str     # "baziqa_macro" | "mingli_trimmed"


PROFILES: dict[str, EvalProfile] = {
    p.profile_id: p
    for p in (
        EvalProfile("baziqa_official_multi_turn",
                    "baziqa", "official", "multi_turn", "approved_v1", "baziqa_macro"),
        EvalProfile("baziqa_xjz_direct",
                    "baziqa", "xjz_direct", "direct", "approved_v1", "baziqa_macro"),
        EvalProfile("mingli_official_cot_astro",
                    "mingli", "official", "direct", "approved_v1", "mingli_trimmed"),
        EvalProfile("mingli_xjz_direct",
                    "mingli", "xjz_direct", "direct", "approved_v1", "mingli_trimmed"),
    )
}

SCHEMA_VERSIONS = ("legacy_v0", "approved_v1")


def resolve_profile(name: str, chart_schema_version: str | None = None) -> EvalProfile:
    try:
        profile = PROFILES[name]
    except KeyError:
        raise SystemExit(f"未知 profile: {name!r}；可选：{sorted(PROFILES)}")
    if chart_schema_version is not None:
        if chart_schema_version not in SCHEMA_VERSIONS:
            raise SystemExit(
                f"未知 chart_schema_version: {chart_schema_version!r}；可选：{SCHEMA_VERSIONS}"
            )
        profile = replace(profile, chart_schema_version=chart_schema_version)
    return profile


def derive_method(profile: EvalProfile) -> str:
    """interaction_mode → runner method；runner 不得接受与之冲突的显式 --method。"""
    return "multi_turn" if profile.interaction_mode == "multi_turn" else "direct_choice"


_FORMATTER_MAP = {
    ("baziqa", "official", "multi_turn"): "format_multi_turn",
    ("baziqa", "xjz_direct", "direct"): "format_direct_choice_prompt",
    ("mingli", "official", "direct"): "format_official_cot_prompt",
    ("mingli", "xjz_direct", "direct"): "format_direct_choice_prompt",
}


def derive_formatter(profile: EvalProfile) -> str:
    try:
        return _FORMATTER_MAP[(profile.dataset, profile.prompt_style, profile.interaction_mode)]
    except KeyError:
        raise SystemExit(f"无 formatter 映射: {profile}")


_APPROVED_BAZI_MARKERS = frozenset({
    "【四柱】", "【日主】", "【大运】", "【胎元／命宫／身宫】", "【真太阳时校正】",
    "【纳音五行】", "【五行统计】", "【十神统计】", "【地支关系】", "【神煞】",
    "藏干", "起运",
})
_MINGLI_BAZI_CORE_MARKERS = frozenset({
    "【四柱】", "【日主】", "【五行统计】", "【十神统计】", "【地支关系】", "【神煞】",
})
_ZIWEI_MARKERS = frozenset({"【紫微斗数·本命】", "夫妻宫", "财帛宫", "官禄宫"})
_DENYLIST_MARKERS = frozenset({"【流年】", "空亡：", "空亡（"})
_APPROVED_ONLY_MARKERS = frozenset({
    "【四柱】", "【日主】", "【大运】", "【神煞】", "【紫微斗数·本命】",
    "【胎元／命宫／身宫】", "【真太阳时校正】", "【纳音五行】", "【五行统计】",
    "【十神统计】", "【地支关系】",
})


def visibility_requirements(
    profile: EvalProfile, chart_schema_version: str,
) -> tuple[frozenset[str], frozenset[str]]:
    if chart_schema_version == "legacy_v0":
        # 旧上下文对照臂：自身 schema 由渲染器逐字节等价保证；此处只做串扰检测。
        return frozenset(), _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS
    if chart_schema_version == "approved_v1":
        if profile.dataset == "mingli":
            # 决策记录 3：MingLi 源数据只有八字核心六字段 + palaces；缺口入报告。
            return _MINGLI_BAZI_CORE_MARKERS | _ZIWEI_MARKERS, _DENYLIST_MARKERS
        return _APPROVED_BAZI_MARKERS, _DENYLIST_MARKERS
    raise SystemExit(f"未知 chart_schema_version: {chart_schema_version!r}")


def assert_visibility(
    rendered_text: str, profile: EvalProfile, chart_schema_version: str,
) -> list[str]:
    """渲染文本上的 required/forbidden 子串断言，返回违规列表（空表 = 通过）。"""
    required, forbidden = visibility_requirements(profile, chart_schema_version)
    violations = [f"required 缺失: {m}" for m in sorted(required) if m not in rendered_text]
    violations += [f"forbidden 命中: {m}" for m in sorted(forbidden) if m in rendered_text]
    return violations


def prompt_fingerprint(profile: EvalProfile) -> str:
    """prompt/模板指纹（resume manifest 字段，设计 L168）：模板版本 + 模板常量 +
    渲染器与 profile formatter 源码，拼接后 SHA-256。模板文本、渲染逻辑或
    formatter 路由任一变化 → 指纹变化 → resume 拒绝。"""
    import hashlib
    import inspect

    from benchmark.formatters import baziqa_prompt, chart_context

    formatter = derive_formatter(profile)
    parts = [formatter,
             chart_context.CHART_CONTEXT_TEMPLATE_VERSION,
             chart_context.CHART_CONTEXT_TEMPLATE,
             inspect.getsource(chart_context.render_chart_context),
             inspect.getsource(baziqa_prompt.format_birth_line)]
    if formatter == "format_official_cot_prompt":
        from benchmark.formatters import mingli_prompt
        parts += [mingli_prompt.OFFICIAL_COT_TEMPLATE_VERSION,
                  inspect.getsource(mingli_prompt.format_official_cot_prompt)]
    elif formatter == "format_direct_choice_prompt":
        parts.append(inspect.getsource(baziqa_prompt.format_direct_choice_prompt))
    else:  # format_multi_turn
        parts.append(inspect.getsource(baziqa_prompt.format_multi_turn_context))
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()
```

- [ ] **Step 4：运行确认全绿** `python -m pytest tests/test_phase6_profiles.py -q`

- [ ] **Step 5：提交（精确路径）**

```powershell
git add benchmark/runners/profiles.py tests/test_phase6_profiles.py
git commit -m "feat(phase6): 五维 profile 注册表 + (profile,schema) 可见性矩阵"
```

---

## Task 5：MingLi 数据前置、归一化可见性与官方 CoT formatter

**目的**：落地设计 §3.2 数据前置与 §4.3 四层可见性的 MingLi 侧。`mingli_official_cot_astro` 的 formatter 与数据前置在本任务落地；其端到端路由测试（含前置缺失退出码 4）统一归 Task 6（runner 接线之后）。

**边界决定（复审确认）**：`data/mingli/` 为可复现外部数据（fetcher + 钉死 commit），**不入 Git**，在 `.gitignore` 追加一行；单条目样例 fixture 入 Git 供测试。

---

### Task 5 修订（2026-07-18，用户裁决 1B+2A，替代下方冲突内容）

**执行经过**：Step 1–5 已按原计划完成（fetcher 3 测试绿；真实拉取 OK，160 题/32 条 fortune 全 success；fixture `mingli_fortune_sample.json` 已截取）。Step 5 勘察命中两个"停下汇报"条款，用户裁决如下。

**勘察事实**（全量核实，非抽样）：

1. 32/32 条 fortune 均为 API 形状，**0 条含 `bazi` dict**——结构化八字核心六字段在真实数据中不存在；`chineseDate` 为四柱字符串（如 `"甲寅 戊辰 己亥 壬申"`）。
2. 宫位真实键名与 Step 8 原猜测键全部不符。已定稿映射（用户确认）：`soul`→命主、`body`→身主、`fiveElementsClass`→五行局、`earthlyBranchOfSoulPalace`→命宫、`earthlyBranchOfBodyPalace`→身宫、`name`→宫位名、`heavenlyStem`→天干、`earthlyBranch`→地支、`majorStars`→主星、`minorStars+adjectiveStars`→辅星、`decadal.range`→大限、`isBodyPalace`→身宫标记；星曜保留 name+brightness；**禁止兼容任何猜测键名**。命宫干支取 name=="命宫" 宫的 heavenlyStem+earthlyBranch（如"癸酉"）。
3. 官方 prompt 模板存在于 `mingli_bench/benchmark.py:209-321`，与冻结版三项判据全异（原文已存 `mingli_official_prompt_template.txt`）。

**裁决 1B**：`mingli_xjz_direct` 可见性矩阵维持不变（八字核心六段标+紫微），真实数据上必然 BLOCKED——状态名 `BLOCKED_PRECONDITION`，缺口如实入报告；`mingli_official_cot_astro` 使用**独立的官方 astro required**（不允许与 xjz 因 dataset 相同而共享 required）。

**裁决 2A**：弃用冻结版，`benchmark/formatters/mingli_prompt.py` 按官方模板 **1:1 复刻**（`mingli_official_replica_v1`），含官方 system prompt 常量、`答案：X` 格式、选项按 letter 排序、官方 astro 注入块。

**修订后交付物**（替代原 Step 6/8/9 冲突部分）：

- `profiles.py`：`visibility_requirements` 按 **profile_id** 分支——`mingli_official_cot_astro` → `_OFFICIAL_ASTRO_MARKERS = {"八字命盘信息：","紫微命盘信息：","十二宫位星曜分布："}`（结构性标记，astro 块注入即恒真，不依赖有星宫位，避免误杀）；`mingli_xjz_direct` → 原六段标+紫微不变。新增 `visibility_gate(rendered, profile, schema) -> "PASS" | "BLOCKED_PRECONDITION"`。
- adapter `to_canonical_chart_input`：bazi 形状透传六字段不变；API 形状产出 `{"ziwei": <按定稿映射>, "official_astro": {"chinese_date","time","five_elements_class","zodiac","palace_stars": {宫名: "主星 辅星(仅major+minor名，空格连接)"}}}`。`load_and_normalize` 调用点改为 `to_canonical_chart_input`，并携带 `row["birth_info"]`（官方模板"命主信息"需要）。
- `mingli_prompt.py`：`OFFICIAL_SYSTEM_PROMPT` + `format_official_cot_prompt(case)`（签名改为单参，astro 取自 `case["chart_input"]["official_astro"]`，缺标量字段按官方行为填"未知"；选项兼容 dict 与 "A. 文本" 归一化字符串并排序）。
- **测试修订**：
  - `test_real_sample_canonical_and_visibility` 改写：紫微字段与宫位映射通过；**精确断言**八字核心六段缺失（6 条 `required 缺失`，无其他违规）；`visibility_gate(...) == "BLOCKED_PRECONDITION"`。
  - 新增官方 profile 真实样例测试：官方 astro required 全过；prompt 与官方 golden 逐字节一致。
  - 新增 profile 隔离测试：同一真实数据，official → PASS、xjz → BLOCKED；两 profile required 集合不同。
  - 模型零调用测试**移交 Task 6**（runner 接线后才有生产锚点；Task 5 交付 `visibility_gate` 原语，Task 6 接线时断言 XJZ 可见性失败后模型调用次数为 0）。
  - golden 覆盖：system prompt、user prompt 全文、选项排序、`答案：X`、官方 astro 块（真实 fixture 驱动）。
- 既有 `test_load_and_normalize_supports_official_questions_payload` 的 `chart_input["chineseDate"]` 断言随 canonical 化失效，改为断言 `chart_input["official_astro"]["chinese_date"]`（执行偏离登记）。

---

- [ ] **Step 1：写 fetcher 失败测试 `tests/test_fetch_mingli_bench.py`（完整代码）**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.fetch_mingli_bench as fetcher


def make_source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "data").mkdir(parents=True)
    (src / "data" / "data.json").write_text(
        json.dumps([{"case_id": "m1"}], ensure_ascii=False), encoding="utf-8"
    )
    (src / "data" / "fortune_api_results.json").write_text(
        json.dumps({"m1": {"bazi": {}}}, ensure_ascii=False), encoding="utf-8"
    )
    (src / "LICENSE").write_text("MIT License", encoding="utf-8")
    return src


def test_fetch_from_source_dir(tmp_path, monkeypatch):
    src = make_source(tmp_path)
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(src)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pinned_commit"] == fetcher.PINNED_COMMIT
    assert [Path(f["path"]).name for f in manifest["files"]] == [
        "data.json", "fortune_api_results.json",
    ]
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])
    assert "LICENSE" in manifest["license"]


def test_missing_required_file_blocked(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(src)]) == fetcher.BLOCKED_EXIT


def test_missing_source_dir_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(tmp_path / "nope")]) == fetcher.BLOCKED_EXIT
    assert "BLOCKED" in capsys.readouterr().out
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_fetch_mingli_bench.py -q` → `ModuleNotFoundError`。

- [ ] **Step 3：实现 `scripts/fetch_mingli_bench.py`（完整代码；commit 钉死 `b7433280fd86d7a7c27debbc47d0303c218f0bfd`，经 GitHub API 核实为 2026-05-09 最新）**

```python
"""MingLi-Bench 数据获取前置（设计 §3.2）。

固定 commit、SHA-256、许可证记录；任何失败记 BLOCKED（退出码 4），不阻塞 BaziQA 线。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_URL = "https://github.com/DestinyLinker/MingLi-Bench"
PINNED_COMMIT = "b7433280fd86d7a7c27debbc47d0303c218f0bfd"
REQUIRED_FILES = ("data/data.json", "data/fortune_api_results.json")
DEST_DIR = Path("data/mingli")
MANIFEST_PATH = Path(".tmp/phase6/mingli_fetch_manifest.json")
BLOCKED_EXIT = 4


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=300)


def _copy_required(src_root: Path) -> list[dict]:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for rel in REQUIRED_FILES:
        src = src_root / rel
        if not src.exists():
            raise FileNotFoundError(f"必需文件缺失: {src}")
        dst = DEST_DIR / Path(rel).name
        shutil.copyfile(src, dst)
        entries.append({
            "path": str(dst), "sha256": sha256_file(dst), "bytes": dst.stat().st_size,
        })
    return entries


def _license_note(src_root: Path) -> str:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        p = src_root / name
        if p.exists():
            return f"{name} 存在（{p.stat().st_size} bytes）"
    return "未发现 LICENSE 文件；README 声明 MIT（需人工复核）"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MingLi-Bench 数据获取前置")
    parser.add_argument("--source-dir", type=Path, default=None,
                        help="本地已有仓库副本时跳过网络获取（测试/离线用）")
    parser.add_argument("--work-dir", type=Path, default=Path(".tmp/phase6/mingli_src"))
    args = parser.parse_args(argv)

    try:
        if args.source_dir is not None:
            src_root = args.source_dir
            if not src_root.exists():
                raise FileNotFoundError(f"--source-dir 不存在: {src_root}")
        else:
            src_root = args.work_dir
            if not (src_root / ".git").exists():
                src_root.parent.mkdir(parents=True, exist_ok=True)
                r = _git(["clone", "--no-checkout", REPO_URL, str(src_root)])
                if r.returncode != 0:
                    raise RuntimeError(f"git clone 失败: {r.stderr.strip()[:400]}")
            r = _git(["checkout", PINNED_COMMIT], cwd=src_root)
            if r.returncode != 0:
                raise RuntimeError(
                    f"git checkout {PINNED_COMMIT} 失败: {r.stderr.strip()[:400]}"
                )
            head = _git(["rev-parse", "HEAD"], cwd=src_root).stdout.strip()
            if head != PINNED_COMMIT:
                raise RuntimeError(f"HEAD {head} != 钉死 commit {PINNED_COMMIT}")

        entries = _copy_required(src_root)
        manifest = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "repo": REPO_URL,
            "pinned_commit": PINNED_COMMIT,
            "license": _license_note(src_root),
            "files": entries,
        }
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({"status": "OK", "files": [e["path"] for e in entries]},
                         ensure_ascii=False))
        return 0
    except Exception as exc:  # 任何失败 → BLOCKED（设计 §3.2）
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return BLOCKED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4：fetcher 单测全绿后，真实获取（需网络）**

```powershell
python -m pytest tests/test_fetch_mingli_bench.py -q
python scripts/fetch_mingli_bench.py
```

- 输出 `"status": "OK"`：继续 Step 5。
- 输出 `"status": "BLOCKED"`（无网络 / 仓库不可达 / commit 不存在）：按设计 §3.2/§10 记 BLOCKED——MingLi 线全部 gate 记 BLOCKED 并写明原因，**不阻塞 BaziQA 线**；Step 5–8 标记 BLOCKED，直接进 Task 6。

- [ ] **Step 5：schema 勘察（数据存在时执行；输出决定映射表与 fixture 形状）**

```powershell
python -c "import json;d=json.load(open('data/mingli/data.json',encoding='utf-8'));r=d[0] if isinstance(d,list) else d['questions'][0];print('data keys:',sorted(r));f=json.load(open('data/mingli/fortune_api_results.json',encoding='utf-8'));k=next(iter(f)) if isinstance(f,dict) else 0;e=(f[k] if isinstance(f,dict) else f[0]);print('fortune keys:',sorted(e));b=e.get('bazi');print('bazi keys:',sorted(b) if isinstance(b,dict) else type(b).__name__);a=(((e.get('api_response') or {}).get('data') or {}).get('data') or {});print('api data keys:',sorted(a) if isinstance(a,dict) else type(a).__name__);p=(a.get('palaces') or []) if isinstance(a,dict) else [];print('palace[0]:',json.dumps(p[0],ensure_ascii=False)[:600] if p else 'NONE')"
```

再截取一个最小真实条目作为测试 fixture，并**人工确认无真实姓名等敏感信息**（敏感则换条目重截）：

```powershell
python -c "import json,pathlib;f=json.load(open('data/mingli/fortune_api_results.json',encoding='utf-8'));k=next(iter(f)) if isinstance(f,dict) else None;e=f[k] if k is not None else f[0];pathlib.Path('tests/fixtures/phase6/mingli_fortune_sample.json').write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding='utf-8');print('fixture keys:',sorted(e))"
```

同时核验官方 prompt 模板来源（**核验-only，不静默替换实现**）：在 `.tmp/phase6/mingli_src/` 中检索官方评测 prompt（`git grep -n -i -e "prompt" -e "最终答案" -- '*.py' '*.md'`，工作目录 `.tmp/phase6/mingli_src`）。判定规则：

- 仓库含官方模板且与本计划冻结版 `mingli_official_cot_v1`（Step 8 代码）存在**实质差异**（指令结构、答案行格式、选项呈现方式任一不同）→ **停下汇报**：模板原文保存为 `tests/fixtures/phase6/mingli_official_prompt_template.txt` 供对照，作为偏离发现提交用户裁决，禁止继续后续 Step。
- 仓库不含官方模板，或仅措辞/空白差异 → 将勘察结论（来源文件路径，或"来源：README 协议描述，仓库无官方模板文件"）写入 `mingli_official_prompt_template.txt` 头部，继续以冻结版生成 golden。

- [ ] **Step 6：写归一化 / 可见性 / CoT 失败测试 `tests/test_mingli_canonical.py`（完整代码）**

```python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.chart_context import render_chart_context
from benchmark.formatters.mingli_prompt import format_official_cot_prompt
from benchmark.runners.mingli_bench_adapter import to_canonical_chart_input
from benchmark.runners.profiles import assert_visibility, resolve_profile

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "phase6"
SAMPLE = FIXTURE_DIR / "mingli_fortune_sample.json"
AS_OF = "2026-07-17"

BAZI_SHAPE = {
    "bazi": {
        "four_pillars": {
            k: {"gan": "甲", "zhi": "子", "gan_wuxing": "木", "zhi_wuxing": "水",
                "shi_shen_gan": "比肩", "shi_shen_zhi_main": "正印",
                "cang_gan": ["癸"], "cang_gan_shi_shen": ["正印"], "nayin": "海中金"}
            for k in ("year", "month", "day", "hour")
        },
        "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳", "shier_changsheng": "沐浴"},
        "shishen_stats": {"counts": {"比肩": 2}, "missing": [], "missing_human": ""},
        "wuxing_stats": {"jin": 1, "mu": 2, "shui": 1, "huo": 2, "tu": 2,
                         "missing": [], "strongest": "木", "weakest": "金"},
        "branch_relations": [],
        "shensha": [{"name": "天乙贵人", "position": "年干", "meaning": "主贵人扶助"}],
        "wuyun_liuqi": {"unapproved": True},
    }
}


def test_bazi_shape_canonical_drops_unapproved():
    canonical = to_canonical_chart_input(BAZI_SHAPE)
    assert "wuyun_liuqi" not in canonical
    for key in ("four_pillars", "day_master", "shishen_stats",
                "wuxing_stats", "branch_relations", "shensha"):
        assert key in canonical


def test_bazi_shape_renders_and_visibility_core_passes():
    case = {
        "person": {"name": "匿名命主", "gender": "female",
                   "birth": {"year": 1990, "month": 1, "day": 1, "hour": 0, "minute": 0, "place": "上海"}},
        "chart_input": to_canonical_chart_input(BAZI_SHAPE),
    }
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert "【四柱】" in rendered and "【神煞】" in rendered
    assert "【大运】" not in rendered  # MingLi 源数据缺口：缺失段跳过不虚构
    # bazi 形状无 palaces → 无紫微段：mingli 可见性须如实报缺
    violations = assert_visibility(rendered, resolve_profile("mingli_xjz_direct"), "approved_v1")
    assert any("【紫微斗数·本命】" in v for v in violations)


@pytest.mark.skipif(not SAMPLE.exists(), reason="mingli fixture 未生成（fetch 前置未完成）")
def test_real_sample_canonical_and_visibility():
    entry = json.loads(SAMPLE.read_text(encoding="utf-8"))
    canonical = to_canonical_chart_input(entry)
    case = {
        "person": {"name": "匿名命主", "gender": "male",
                   "birth": {"year": 1990, "month": 1, "day": 1, "hour": 0, "minute": 0, "place": "北京"}},
        "chart_input": canonical,
    }
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert rendered.strip()  # 逐题 rendered_chart_context 非空
    violations = assert_visibility(rendered, resolve_profile("mingli_xjz_direct"), "approved_v1")
    assert violations == [], f"真实样例可见性违规: {violations}"


def test_official_cot_prompt_golden():
    case = {
        "question": "命主今年财运如何？",
        "options": ["A 好", "B 差", "C 平", "D 先好后差"],
    }
    prompt = format_official_cot_prompt(case, "【命盘上下文】\n（此处为命盘）")
    golden = FIXTURE_DIR / "mingli_prompt_golden.txt"
    if os.environ.get("PHASE6_UPDATE_GOLDEN") == "1":
        golden.write_text(prompt, encoding="utf-8")
    assert prompt == golden.read_text(encoding="utf-8")


def test_official_cot_contains_chart_question_options():
    case = {"question": "QQQ", "options": ["A 一", "B 二", "C 三", "D 四"]}
    prompt = format_official_cot_prompt(case, "CHART_CTX_SENTINEL")
    assert "CHART_CTX_SENTINEL" in prompt and "QQQ" in prompt and "B 二" in prompt
```

并在 `tests/test_chart_context.py` **追加**部分字段容忍渲染回归测试（MingLi 形状驱动）：

```python
def test_render_tolerates_partial_chart_input():
    """MingLi 归一化输入仅含部分八字键：缺失段跳过，不抛异常、不虚构。"""
    case = load_fixture(1)
    case["chart_input"] = {
        "four_pillars": case["chart_input"]["four_pillars"],
        "day_master": case["chart_input"]["day_master"],
    }
    rendered = render_chart_context(case, "approved_v1", as_of_date=AS_OF)
    assert "【四柱】" in rendered
    assert "【大运】" not in rendered
    assert "【神煞】" not in rendered
```

- [ ] **Step 7：运行确认失败** `python -m pytest tests/test_mingli_canonical.py -q` → `ImportError`（`to_canonical_chart_input` / `mingli_prompt` 不存在）。

- [ ] **Step 8：实现 adapter `to_canonical_chart_input` 与 `benchmark/formatters/mingli_prompt.py`**

`benchmark/runners/mingli_bench_adapter.py` 追加（`load_and_normalize` 第 164 行调用点由 `_extract_chart_input` 改为 `to_canonical_chart_input`，`_extract_chart_input` 保留不动）：

```python
_CANONICAL_BAZI_KEYS = (
    "four_pillars", "day_master", "shishen_stats",
    "wuxing_stats", "branch_relations", "shensha",
)


def to_canonical_chart_input(fortune_entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把 mingli fortune 条目归一化为 approved_v1 可渲染的 canonical chart_input。

    bazi 形状：透传批准核心六字段（丢弃 wuyun_liuqi 等非批准键）。
    API 形状：palaces → 本命紫微段（canonical ziwei.twelve_palaces）；
    映射表按 Task 5 Step 5 勘察结果填写。缺失字段不虚构（fail-closed），
    由可见性矩阵与覆盖率报告如实呈现。
    """
    if not isinstance(fortune_entry, dict):
        return {}
    bazi = fortune_entry.get("bazi")
    if isinstance(bazi, dict):
        return {k: bazi[k] for k in _CANONICAL_BAZI_KEYS if k in bazi}
    api_data = (((fortune_entry.get("api_response") or {}).get("data") or {}).get("data") or {})
    if isinstance(api_data, dict) and api_data:
        canonical: Dict[str, Any] = {}
        palaces = api_data.get("palaces")
        if isinstance(palaces, list) and palaces:
            canonical["ziwei"] = {
                "basic_info": _canon_ziwei_basic_info(api_data),
                "twelve_palaces": [_canon_palace(p) for p in palaces],
            }
        return canonical
    return {}


def _canon_ziwei_basic_info(api_data: Dict[str, Any]) -> Dict[str, Any]:
    """按勘察结果映射命宫/身宫/五行局/命主/身主；源数据没有的键给空串。"""
    return {
        "ming_gong_gan_zhi": str(api_data.get("mingGong") or ""),
        "shen_gong_position": str(api_data.get("shenGong") or ""),
        "wu_xing_ju": str(api_data.get("wuXingJu") or ""),
        "ming_zhu": str(api_data.get("mingZhu") or ""),
        "shen_zhu": str(api_data.get("shenZhu") or ""),
    }


def _canon_palace(palace: Any) -> Dict[str, Any]:
    """按勘察结果映射单宫；此处键名必须与真实 palace 条目逐一核对后定稿。"""
    p = palace if isinstance(palace, dict) else {}
    return {
        "name": str(p.get("name") or ""),
        "position": str(p.get("position") or p.get("branch") or ""),
        "tian_gan": str(p.get("tianGan") or p.get("gan") or ""),
        "main_stars": [
            s if isinstance(s, dict) else {"name": str(s), "brightness": ""}
            for s in (p.get("mainStars") or p.get("main_stars") or [])
        ],
        "auxiliary_stars": list(p.get("auxiliaryStars") or p.get("auxiliary_stars") or []),
        "daxian": p.get("daxian") or p.get("daXian") or "",
        "is_shengong": bool(p.get("isShengong") or p.get("is_shengong")),
    }
```

`benchmark/formatters/mingli_prompt.py`（新文件；下方模板文本即**实现冻结版 `mingli_official_cot_v1`**——Step 5 勘察只做核验，发现实质差异须停下汇报，禁止静默替换）：

```python
"""MingLi 官方 CoT prompt（设计 §4.3 mingli_official_cot_astro）。

本模板为**实现冻结版 mingli_official_cot_v1**，评测可复现性以本文件为准。
勘察对照记录见 tests/fixtures/phase6/mingli_official_prompt_template.txt
（来源：MingLi-Bench 仓库，钉死 commit b7433280fd86d7a7c27debbc47d0303c218f0bfd；
若该仓库无官方模板文件，对照文件头部注明"来源：README 协议描述，仓库无官方模板文件"）。
"""
from __future__ import annotations

OFFICIAL_COT_TEMPLATE_VERSION = "mingli_official_cot_v1"


def format_official_cot_prompt(case: dict, chart_context_text: str) -> str:
    options = "\n".join(str(o) for o in case.get("options", []))
    return "\n\n".join([
        "你是一位严谨的命理评测助手。请根据命盘信息逐步推理后回答四选一题。",
        "## 命盘信息",
        chart_context_text,
        "## 问题",
        case.get("question", ""),
        "## 选项",
        options,
        "请逐步推理，最后一行只写：最终答案：X（X 为 A/B/C/D 之一）。",
    ])
```

- [ ] **Step 9：生成 golden 并复核**

```powershell
$env:PHASE6_UPDATE_GOLDEN="1"
python -m pytest tests/test_mingli_canonical.py tests/test_chart_context.py -q
Remove-Item Env:PHASE6_UPDATE_GOLDEN
```

人工 diff `mingli_prompt_golden.txt`：确认模板为冻结版 `mingli_official_cot_v1`、含 CoT 指令与"最终答案：X"格式，且勘察结论已写入 `mingli_official_prompt_template.txt` 头部。复核后 `python -m pytest tests/test_mingli_canonical.py tests/test_chart_context.py tests/test_phase6_profiles.py -q` 全绿。

- [ ] **Step 10：`.gitignore` 追加外部数据目录**

在 `.gitignore` 末尾追加一行 `data/mingli/`（Read 后 Edit，不顺手改其他行）。

- [ ] **Step 11：提交（精确路径）**

```powershell
git add scripts/fetch_mingli_bench.py tests/test_fetch_mingli_bench.py benchmark/runners/mingli_bench_adapter.py benchmark/formatters/mingli_prompt.py tests/test_mingli_canonical.py tests/test_chart_context.py tests/fixtures/phase6/mingli_fortune_sample.json tests/fixtures/phase6/mingli_official_prompt_template.txt tests/fixtures/phase6/mingli_prompt_golden.txt .gitignore
git commit -m "feat(phase6): MingLi 数据前置(钉死 commit) + canonical 归一化 + 官方 CoT formatter"
```

（fetch 前置 BLOCKED 时：`mingli_fortune_sample.json` / 两个 golden 文件不生成，上述 git add 中对应路径跳过并在提交信息注明 "MingLi 前置 BLOCKED：<原因>"；真实样例测试保持 skip。）

---

## Task 6：runner 接线——`--profile` 路由、截断守卫、resume 与 attempt key

**目的**：设计 §4.3/§4.4 的 runner 侧落地。已核实的改造锚点（行号以当前文件为准）：

- `run_benchmark.py:44` `build_benchmark_prompt`（直接路径唯一 prompt 收口，调用点 :405）；
- `:230` / `:247` 两个模型调用边界（函数体内 lazy import `claude_api.call_model_messages_sync`，可 monkeypatch）；
- `:276` `_prepare_jsonl`（"w" 截断），截断调用点 **:379（直接路径）、:812（multi_turn）、:1058（main 尾部 `_write_jsonl` 重写）三处**——resume 模式必须全部条件化，否则已完成记录被重写丢失；
- `:288` `_append_jsonl`（detail 写入唯一收口，attempt key / terminal_state 在此富化，零侵入循环体）；
- `:811` `run_multi_turn_benchmark`、`:933` `main(argv=None)`（已可注入）；`:1024` 全灭 `return 2`、`:1102` 正常 `return 0`。

**设计决定（复审确认）**：原始响应持久化 = detail 行内 `raw_answer` 字段（既有）+ `raw_response_path` 记录 detail 文件路径；不另建 raw 文件树（如实声明，满足重放审计的最小实现）。`--scheduled-calls` 仅作 manifest 对照，不强制截停；硬约束只有 `--hard-cap`。

**文件结构清单新增**（v2 增补）：`tests/test_phase6_runner_routing.py`（四条命名配置端到端路由 + method 冲突 + MingLi 前置退出码 4）。

**Task 6 增补（2026-07-18 用户裁决 1B 配套）**：runner 接线必须在 `assert_visibility` 失败（`visibility_gate(...) == "BLOCKED_PRECONDITION"`）时于**任何模型调用之前**短路；`test_phase6_runner_routing.py` 必须包含零调用测试——XJZ profile 可见性失败后，断言模型 runner 调用次数为 0（该要求原列于 Task 5，因 runner 生产锚点在 Task 6 而移交）。

- [ ] **Step 0：测试设施增补（`tests/phase6_helpers.py`，精确替换/追加）**

替换 `RunnerEnv.__init__` 与 `_fake_call`，追加 `read_summary`：

```python
    def __init__(self, tmp_path: Path, monkeypatch, n_cases: int = 4, case_factory=None):
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.dataset = tmp_path / "cases.jsonl"
        self.detail = tmp_path / "detail.jsonl"
        self.events = tmp_path / "detail.events.jsonl"
        self.summary = tmp_path / "summary.json"
        factory = case_factory or make_case
        write_jsonl(self.dataset, [factory(f"c{i}") for i in range(n_cases)])
        self._script: list[tuple[str, object]] = []
        self.received: list = []          # 每次模型调用的 messages，按调用顺序

    def _fake_call(self, messages, **kw):
        self.received.append(messages)
        action, payload = self._script.pop(0)
        if action in ("fail", "crash"):
            raise payload
        return payload

    def read_summary(self) -> dict:
        if not self.summary.exists():
            return {}
        return json.loads(self.summary.read_text(encoding="utf-8"))
```

并新增 `run_benchmark_proxy.py`（tests/ 下薄封装）：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.runners.run_benchmark import main  # noqa: F401
```

- [ ] **Step 1：写失败测试 A `tests/test_phase6_resume.py`（完整代码）**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.run_benchmark import (
    ATTEMPT_STAGES,
    RESUME_MANIFEST_FIELDS,
    build_attempt_key,
    load_completed_keys,
)
from tests.phase6_helpers import RunnerEnv


def key_of(**overrides):
    base = dict(dataset_id="d", profile_id="p", arm="a", attempt_stage="main",
                provider="deepseek", model="m", case_id="c1",
                repeat_idx=0, sample_idx=0, permutation_id="p0")
    base.update(overrides)
    return build_attempt_key(**base)


def test_attempt_key_no_collision_across_stages():
    keys = {key_of(attempt_stage=s) for s in ATTEMPT_STAGES}
    assert len(keys) == len(ATTEMPT_STAGES)
    assert key_of(attempt_stage="bazi") != key_of(attempt_stage="ziwei")
    assert key_of(arm="x") != key_of(arm="y")
    assert key_of(repeat_idx=0) != key_of(repeat_idx=1)


def test_truncation_guard_requires_intent(tmp_path, monkeypatch):
    """detail 已存在：无 --resume 一律拒绝（Phase 6 无 --overwrite 语义）；--resume 合法续跑。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0          # 首跑：detail 不存在
    with pytest.raises(SystemExit):
        env.run(profile="baziqa_xjz_direct")                  # 已存在且无 --resume → 拒绝
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0


def test_resume_manifest_created_on_first_run(tmp_path, monkeypatch):
    """首跑（含 --resume 首跑）在 detail 旁创建 detail.manifest.json，17 字段齐全。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    manifest = json.loads((tmp_path / "detail.manifest.json").read_text(encoding="utf-8"))
    for field in RESUME_MANIFEST_FIELDS:
        assert field in manifest
    assert manifest["profile_id"] == "baziqa_xjz_direct"
    assert manifest["temperature"] == 0.0              # 仓库 --temperature 默认 0.0（6A0 真实控制温度）
    assert manifest["n_samples"] == 1
    assert manifest["method"] == "direct_choice"       # profile 推导生效值（resolve 后记录）
    assert manifest["hard_cap"] is None or isinstance(manifest["hard_cap"], int)


@pytest.mark.parametrize("field,value", [
    ("dataset_sha256", "tamper"),                    # 数据变化
    ("temperature", 9.9),                            # 真实温度变化（n_samples=1 时控制调用）
    ("sample_temperature", 9.9),                     # 采样温度变化
    ("chart_schema_version", "legacy_v0"),           # schema 变化
    ("method", "multi_turn"),                        # 生效 method 变化
    ("prompt_template_sha256", "tamper"),            # prompt/模板变化
    ("code_sha256", "tamper"),                       # 代码变化
    ("hard_cap", 999),                               # 预算变化
])
def test_resume_manifest_mismatch_refused(tmp_path, monkeypatch, field, value):
    """manifest 任一字段不一致 → SystemExit(2)，禁止向旧 detail 续跑（设计 L168）。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    mpath = tmp_path / "detail.manifest.json"
    stored = json.loads(mpath.read_text(encoding="utf-8"))
    stored[field] = value
    mpath.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True)
    assert exc_info.value.code == 2


def test_resume_manifest_dataset_change_refused(tmp_path, monkeypatch):
    """真实数据变更（非篡改 manifest）→ dataset_sha256 漂移 → SystemExit(2)。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    env.dataset.write_text(env.dataset.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True)
    assert exc_info.value.code == 2


def test_resume_manifest_config_drift_refused(tmp_path, monkeypatch):
    """配置漂移（非篡改存储文件）：resume 时 --temperature 0.0→1.0 → current manifest 漂移 →
    SystemExit(2)。证明配置漂移真实进入 current manifest，而非仅能检测存储文件被改。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0   # 默认 --temperature 0.0
    env.model_returns("A")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True,
                extra_argv=["--temperature", "1.0"])
    assert exc_info.value.code == 2


def test_resume_refused_when_manifest_missing_but_detail_exists(tmp_path, monkeypatch):
    """旧 detail/events 在而 manifest 缺失（被删或旧版本遗留）→ fail-closed SystemExit(2)，
    不得基于当前配置新建 manifest 混合旧结果。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    (tmp_path / "detail.manifest.json").unlink()       # 模拟 manifest 被删/旧版本遗留
    env.model_returns("A")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True)
    assert exc_info.value.code == 2


def test_resume_manifest_field_missing_refused(tmp_path, monkeypatch):
    """manifest 字段缺失（如旧版缺 temperature）→ 缺失字段计入 diff，SystemExit(2)；
    即使 current 对应值为 None（此处 case_ids_sha256）也不得经 stored.get 误判相等放行。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct") == 0
    mpath = tmp_path / "detail.manifest.json"
    stored = json.loads(mpath.read_text(encoding="utf-8"))
    del stored["case_ids_sha256"]                      # current 为 None：get 语义会误判相等
    mpath.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    env.model_returns("A")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct", resume=True)
    assert exc_info.value.code == 2


def test_resume_first_crash_artifacts_guard(tmp_path, monkeypatch):
    """--resume 首跑在第一次调用时崩溃，仅留下 manifest/events（detail 不存在）：
    无 --resume 重跑必须 SystemExit(2)（任一产物守卫，防预算计数被静默重置）；
    --resume 可继续。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
    env.model_succeeds_then_crash("A", successes=0)   # 第一次模型调用即崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct", resume=True)   # resume-first 首跑
    assert not env.detail.exists()                     # 无终态写入
    assert (tmp_path / "detail.manifest.json").exists()
    assert len(env.read_events("call_attempt")) == 1   # 崩溃 attempt 已记账
    env.model_returns("A")
    with pytest.raises(SystemExit) as exc_info:
        env.run(profile="baziqa_xjz_direct")           # 无 --resume → 拒绝
    assert exc_info.value.code == 2
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0   # --resume 可继续
    assert len(load_completed_keys(env.detail)) == 2


def test_resume_skips_completed_and_key_set_matches_one_shot(tmp_path, monkeypatch):
    # 两次运行使用完全相同的 case 集合（manifest 契约：case_ids_sha256 不得漂移）；
    # 首跑在第 3 次模型调用时进程崩溃，resume 跳过已完成键续跑至完成，键集合与一次性运行一致。
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=4)
    env.model_succeeds_then_crash("A", successes=2)   # c0、c1 成功；c2 调用时进程崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct")
    assert len(env.read_detail()) == 2                 # 仅 c0、c1 终态
    env.model_returns("A")
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0
    resumed_keys = load_completed_keys(env.detail)
    assert len(resumed_keys) == 4
    # 一次性运行同 4 题
    oneshot = RunnerEnv(tmp_path / "oneshot", monkeypatch, n_cases=4)
    oneshot.model_returns("A")
    assert oneshot.run(profile="baziqa_xjz_direct") == 0
    assert resumed_keys == load_completed_keys(oneshot.detail)


def test_detail_rows_carry_attempt_key_and_terminal_state(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("B")  # 正确答案（make_case 默认 answer="B"）
    assert env.run(profile="baziqa_xjz_direct", extra_argv=["--arm", "ctx_approved",
                                                            "--repeat-idx", "0"]) == 0
    rows = env.read_detail()
    assert len(rows) == 1
    row = rows[0]
    assert row["attempt_key"][6] == "c0"            # case_id 槽位
    assert row["attempt_key"][1] == "baziqa_xjz_direct"
    assert row["attempt_key"][2] == "ctx_approved"
    assert row["terminal_state"] == "parsed"
    assert row["raw_response_path"].endswith("detail.jsonl")


def test_invalid_parse_is_terminal_not_retried(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("我完全不知道怎么选")   # 解析不出选项
    assert env.run(profile="baziqa_xjz_direct") == 0
    rows = env.read_detail()
    assert rows[0]["terminal_state"] == "invalid"
    assert env.read_events("model_call_failed") == []  # 解析失败不占网络重试额度
    assert len(env.read_events("call_attempt")) == 1   # 但成功记账一次调用
```

- [ ] **Step 2：写失败测试 B `tests/test_phase6_runner_routing.py`（完整代码）**

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.phase6_helpers import RunnerEnv, make_case

AS_OF_MARKERS = ("【四柱】", "【大运】", "【神煞】")

_ZIWEI = {
    "basic_info": {"ming_gong_gan_zhi": "甲子", "shen_gong_position": "午",
                   "wu_xing_ju": "水二局", "ming_zhu": "贪狼", "shen_zhu": "天同"},
    "twelve_palaces": [
        {"name": n, "position": "子", "tian_gan": "甲",
         "main_stars": [{"name": "紫微", "brightness": "庙"}],
         "auxiliary_stars": [], "daxian": "3-12", "is_shengong": False}
        for n in ("命宫", "兄弟宫", "夫妻宫", "子女宫", "财帛宫", "疾厄宫",
                  "迁移宫", "仆役宫", "官禄宫", "田宅宫", "福德宫", "父母宫")
    ],
    "si_hua": {},
}


def mingli_case(case_id: str = "c0", answer: str = "B") -> dict:
    case = make_case(case_id, answer)
    case["chart_input"] = {
        "four_pillars": {k: {"gan": "甲", "zhi": "子", "gan_wuxing": "木", "zhi_wuxing": "水",
                             "shi_shen_gan": "比肩", "shi_shen_zhi_main": "正印",
                             "cang_gan": ["癸"], "cang_gan_shi_shen": ["正印"],
                             "nayin": "海中金"}
                         for k in ("year", "month", "day", "hour")},
        "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳", "shier_changsheng": "沐浴"},
        "shishen_stats": {"counts": {"比肩": 2}, "missing": [], "missing_human": ""},
        "wuxing_stats": {"jin": 1, "mu": 2, "shui": 1, "huo": 2, "tu": 2,
                         "missing": [], "strongest": "木", "weakest": "金"},
        "branch_relations": [],
        "shensha": [{"name": "天乙贵人", "position": "年干", "meaning": "主贵人扶助"}],
        "ziwei": _ZIWEI,
    }
    return case


def last_user_text(env: RunnerEnv) -> str:
    return env.received[-1][-1]["content"]


def test_route_baziqa_xjz_direct_approved(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("B")
    assert env.run(profile="baziqa_xjz_direct") == 0
    text = last_user_text(env)
    for marker in AS_OF_MARKERS:
        assert marker in text
    assert "空亡" not in text


def test_route_baziqa_official_multi_turn(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
    env.model_returns("B")
    assert env.run(profile="baziqa_official_multi_turn") == 0
    first = env.received[0][0]["content"]       # multi_turn 首条 = 命主上下文
    assert "后续问题都围绕此命主" in first
    assert "【大运】" in first                  # approved 段标进入 multi_turn 上下文


def test_route_mingli_xjz_direct(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmark.runners.run_benchmark._mingli_data_ready", lambda: True)
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1, case_factory=mingli_case)
    env.model_returns("B")
    assert env.run(profile="mingli_xjz_direct") == 0
    assert "【紫微斗数·本命】" in last_user_text(env)


def test_route_mingli_official_cot_astro(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmark.runners.run_benchmark._mingli_data_ready", lambda: True)
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1, case_factory=mingli_case)
    env.model_returns("推理略。最终答案：B")
    assert env.run(profile="mingli_official_cot_astro") == 0
    text = last_user_text(env)
    assert "最终答案：" in text                 # CoT 输出协议
    assert "【紫微斗数·本命】" in text


def test_mingli_prerequisite_missing_exit_4(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmark.runners.run_benchmark._mingli_data_ready", lambda: False)
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1, case_factory=mingli_case)
    env.model_returns("B")
    assert env.run(profile="mingli_official_cot_astro") == 4
    assert env.received == []                   # 前置缺失：零模型调用


def test_method_profile_conflict_exit_2(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("B")
    with pytest.raises(SystemExit) as exc:
        env.run(profile="baziqa_official_multi_turn",
                extra_argv=["--method", "direct_choice"])
    assert exc.value.code == 2
```

- [ ] **Step 3：运行确认失败**

```powershell
python -m pytest tests/test_phase6_resume.py tests/test_phase6_runner_routing.py -q
```

预期：`ImportError`（`build_attempt_key` 等不存在）/ 路由断言失败（`--profile` 未实现）。

- [ ] **Step 4：实现 runner 修改（逐处，行号为当前文件锚点）**

**4a. `benchmark/formatters/baziqa_prompt.py`**：`format_direct_choice_prompt` 与 `format_multi_turn_context` 增加可选参数 `chart_context_text=None`，`## 命主信息` 段改用 `chart_context_text or format_birth_line(case)`；其余不动。

**4b. `benchmark/runners/run_benchmark.py` 顶部常量与纯函数**（import 区追加 `import hashlib`（若无），其后追加）：

```python
ATTEMPT_KEY_FIELDS: tuple = (
    "dataset_id", "profile_id", "arm", "attempt_stage", "provider", "model",
    "case_id", "repeat_idx", "sample_idx", "permutation_id",
)
ATTEMPT_STAGES = ("main", "bazi", "ziwei", "judge", "diversity_probe", "anchor")
TERMINAL_STATES = ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed")


def build_attempt_key(dataset_id, profile_id, arm, attempt_stage, provider, model,
                      case_id, repeat_idx, sample_idx, permutation_id):
    return (dataset_id, profile_id, arm, attempt_stage, provider, model,
            str(case_id), int(repeat_idx), int(sample_idx), permutation_id or "p0")


def compute_hard_cap(scheduled_calls: int) -> int:
    import math
    reserve = int(math.ceil(scheduled_calls * 0.10 / 10.0)) * 10
    return scheduled_calls + reserve


def load_completed_keys(detail_path) -> set:
    keys = set()
    if not detail_path or not os.path.exists(detail_path):
        return keys
    with open(detail_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get("attempt_key")
            if key and row.get("terminal_state") in TERMINAL_STATES:
                keys.add(tuple(key))
    return keys


def load_retry_counts(events_path) -> dict:
    """只数 kind=="model_call_failed" 事件，按 attempt_key 取 retry_idx 最大值。"""
    counts: dict = {}
    if not events_path or not os.path.exists(events_path):
        return counts
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") != "model_call_failed":
                continue
            key = tuple(row["attempt_key"])
            counts[key] = max(counts.get(key, 0), int(row["retry_idx"]))
    return counts


def load_call_attempt_count(events_path) -> int:
    """数 kind=="call_attempt" 事件行数——calls_attempted 跨 resume 恢复的唯一依据。"""
    if not events_path or not os.path.exists(events_path):
        return 0
    n = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            if json.loads(line).get("kind") == "call_attempt":
                n += 1
    return n


def resolve_method(profile_name, explicit_method):
    if profile_name:
        from benchmark.runners.profiles import derive_method, resolve_profile
        derived = derive_method(resolve_profile(profile_name))
        if explicit_method and explicit_method != derived:
            raise SystemExit(2)
        return derived
    return explicit_method or "direct_choice"


# ---- resume manifest（设计 L168：temperature/模板/代码/数据哈希不进 attempt key，由 manifest 约束）----

RESUME_MANIFEST_FIELDS: tuple = (
    "dataset_sha256", "case_ids_sha256", "profile_id", "chart_schema_version",
    "arm", "repeat_idx", "provider", "model",
    "temperature", "sample_temperature", "n_samples", "aggregate", "method",
    "prompt_template_sha256", "code_sha256", "scheduled_calls", "hard_cap",
)

_CODE_SCOPE: tuple = (
    "benchmark/runners/run_benchmark.py",
    "benchmark/runners/profiles.py",
    "benchmark/formatters/chart_context.py",
    "benchmark/formatters/baziqa_prompt.py",
    "benchmark/formatters/mingli_prompt.py",
    "benchmark/formatters/leak_scan.py",
)


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _code_fingerprint() -> str:
    """实验范围代码 SHA-256：范围内文件 bytes 按序拼接；任一文件改动 → 指纹变化 → resume 拒绝。"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    h = hashlib.sha256()
    for rel in _CODE_SCOPE:
        h.update(rel.encode())
        p = os.path.join(root, rel)
        h.update(open(p, "rb").read() if os.path.exists(p) else b"<missing>")
    return h.hexdigest()


def _atomic_write_json(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_resume_manifest(args, profile) -> dict:
    """当前运行的 manifest 字段全集；args.case_ids_file 为 None 时 case_ids_sha256 记 None
    （全集运行由 dataset_sha256 约束）。method 记录 4e `resolve_method` 后的生效值
    （接线顺序保证 resolve 先于本函数）；temperature 是 n_samples=1 时真正控制模型调用的
    温度（仓库 `--temperature` 默认 0.0），sample_temperature 仅 n_samples>1 生效仍记录。"""
    from benchmark.runners.profiles import prompt_fingerprint
    return {
        "dataset_sha256": _sha256_file(os.path.abspath(args.dataset)),
        "case_ids_sha256": (_sha256_file(os.path.abspath(args.case_ids_file))
                            if args.case_ids_file else None),
        "profile_id": profile.profile_id,
        "chart_schema_version": profile.chart_schema_version,
        "arm": args.arm or "default",
        "repeat_idx": args.repeat_idx,
        "provider": args.provider,
        "model": args.model,
        "temperature": args.temperature,
        "sample_temperature": args.sample_temperature,
        "n_samples": args.n_samples,
        "aggregate": args.aggregate,
        "method": args.method,
        "prompt_template_sha256": prompt_fingerprint(profile),
        "code_sha256": _code_fingerprint(),
        "scheduled_calls": args.scheduled_calls,
        "hard_cap": args.hard_cap,
    }


def check_resume_manifest(manifest_path: str, current: dict) -> None:
    """--resume 前置校验：字段完整性 + 逐字段完全匹配。缺失字段记 "<MISSING>" 进 diff
    （不得用 stored.get(k)——"字段缺失且 current 为 None"会误判相等放行）；任一不一致
    打印 diff 并 SystemExit(2)，禁止续跑。"""
    with open(manifest_path, "r", encoding="utf-8") as f:
        stored = json.load(f)
    diff = {}
    for k in RESUME_MANIFEST_FIELDS:
        if k not in stored:
            diff[k] = {"stored": "<MISSING>", "current": current.get(k)}
        elif stored[k] != current.get(k):
            diff[k] = {"stored": stored[k], "current": current.get(k)}
    if diff:
        print(json.dumps({"status": "MANIFEST_MISMATCH", "diff": diff}, ensure_ascii=False))
        raise SystemExit(2)
```

**4c. Phase6 运行上下文（同文件追加）**：

```python
class _HardCapExhausted(Exception):
    """hard_cap 耗尽：非 RuntimeError，循环体的 except RuntimeError 不捕获，冒泡到 main。"""


class Phase6Context:
    def __init__(self, dataset_id, profile_id, arm, attempt_stage, provider, model,
                 repeat_idx, detail_path, events_path, scheduled_calls, hard_cap, resume):
        self.dataset_id = dataset_id
        self.profile_id = profile_id
        self.arm = arm or "default"
        self.attempt_stage = attempt_stage
        self.provider = provider
        self.model = model
        self.repeat_idx = int(repeat_idx or 0)
        self.detail_path = detail_path
        self.events_path = events_path
        self.scheduled_calls = scheduled_calls
        self.hard_cap = hard_cap
        # 事件即账本：成功/失败调用都有 call_attempt 事件，resume 时全量恢复计数
        self.calls_attempted = load_call_attempt_count(events_path) if resume else 0
        self.retry_counts = load_retry_counts(events_path) if resume else {}

    def attempt_key_for(self, case, sample_idx=0):
        return build_attempt_key(
            self.dataset_id, self.profile_id, self.arm, self.attempt_stage,
            self.provider, self.model, case.get("case_id"), self.repeat_idx,
            sample_idx, case.get("_permutation_id") or "p0",
        )

    def before_call(self, key):
        if self.hard_cap is not None and self.calls_attempted >= self.hard_cap:
            raise _HardCapExhausted(f"hard_cap {self.hard_cap} 耗尽")
        _append_jsonl(self.events_path, {
            "kind": "call_attempt", "attempt_key": list(key),
            "retry_idx": None, "error_type": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        self.calls_attempted += 1   # 先写事件记账，再发起调用（含每次重试）

    def record_failure(self, key, exc):
        retry_idx = self.retry_counts.get(key, 0) + 1
        self.retry_counts[key] = retry_idx
        _append_jsonl(self.events_path, {
            "kind": "model_call_failed",
            "attempt_key": list(key), "retry_idx": retry_idx,
            "error_type": str(exc)[:120],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return retry_idx

    def enrich_row(self, row):
        key = self.attempt_key_for({"case_id": row.get("case_id"),
                                    "_permutation_id": row.get("permutation_id")})
        row["attempt_key"] = list(key)
        if row.get("error") or row.get("parser_failure_reason") == "model_call_failed":
            terminal = "call_failed"
        elif row.get("parser_valid") is False:
            terminal = "invalid"
        else:
            terminal = "parsed"
        row["terminal_state"] = terminal
        row["raw_response_path"] = self.detail_path
        return row


_PHASE6_CTX: Phase6Context | None = None


def init_phase6_context(ctx: Phase6Context | None) -> None:
    global _PHASE6_CTX
    _PHASE6_CTX = ctx


def _mingli_data_ready() -> bool:
    return os.path.exists(os.path.join("data", "mingli", "data.json")) and \
        os.path.exists(os.path.join("data", "mingli", "fortune_api_results.json"))
```

**4d. `_append_jsonl`（:288）富化**：写行前插入——

```python
    if _PHASE6_CTX is not None and _PHASE6_CTX.detail_path and \
            os.path.abspath(path) == os.path.abspath(_PHASE6_CTX.detail_path):
        row = _PHASE6_CTX.enrich_row(row)
```

**4e. 调用边界重试账本（:230 / :247）**：两函数主体抽为 `_call_once(...)`（保留原签名与 lazy import 行为），外层：

```python
def _attempt_with_ledger(case, call_once):
    if _PHASE6_CTX is None:
        return call_once()
    key = _PHASE6_CTX.attempt_key_for(case or {})
    while True:
        if _PHASE6_CTX.retry_counts.get(key, 0) >= 3:
            raise RuntimeError(f"model_call_failed: retry budget exhausted ({key[6]})")
        _PHASE6_CTX.before_call(key)
        try:
            return call_once()
        except RuntimeError as exc:
            if not str(exc).startswith("model_call_failed"):
                raise   # 非网络类 RuntimeError（如崩溃模拟）直接冒泡，不算重试
            _PHASE6_CTX.record_failure(key, exc)
```

`call_model_sync` / `call_model_messages_with_history` 改为 `return _attempt_with_ledger(case, lambda: _call_once(...))`（两函数各一份 `_call_once` 闭包，参数原样透传）。

**4f. `build_benchmark_prompt`（:44）与 formatter 分派**：

```python
def build_benchmark_prompt(case, method='direct_choice', phase4_exp_a=False,
                           chart_schema_version=None, profile_formatter=None):
    if profile_formatter == 'format_official_cot_prompt':
        from benchmark.formatters.mingli_prompt import format_official_cot_prompt
        from benchmark.formatters.chart_context import render_chart_context
        return format_official_cot_prompt(
            case, render_chart_context(case, chart_schema_version or 'approved_v1'))
    if method == 'two_stage_reasoning':
        return format_stage1_prompt(case, exp_a=phase4_exp_a)
    if method == 'structured_reasoning':
        return format_structured_reasoning_prompt(case)
    if method in ('direct_choice', 'multi_turn'):
        context_text = None
        if chart_schema_version:
            from benchmark.formatters.chart_context import render_chart_context
            context_text = render_chart_context(case, chart_schema_version)
        return format_direct_choice_prompt(case, chart_context_text=context_text)
    raise ValueError(f"Unsupported benchmark method: {method}")
```

**4g. `run_model_benchmark`（:357）**：签名追加 `chart_schema_version=None, profile_formatter=None, resume_append=False`；`:379` 的 `_prepare_jsonl(case_details_jsonl)` 改为 `if not resume_append: _prepare_jsonl(case_details_jsonl)`；`:405` 调用点追加 `chart_schema_version=chart_schema_version, profile_formatter=profile_formatter`；multi_turn 分发（:359）同步透传两个新参数。

**4h. `run_multi_turn_benchmark`（:811）**：签名追加 `chart_schema_version=None, resume_append=False`；`:812` 同 4g 条件化；`:824` 改为——

```python
        if chart_schema_version:
            from benchmark.formatters.chart_context import render_chart_context
            context_text = format_multi_turn_context(
                person_cases[0],
                chart_context_text=render_chart_context(person_cases[0], chart_schema_version),
            )
        else:
            context_text = format_multi_turn_context(person_cases[0])
```

**4i. `main()`（:933）CLI 与接线**：

- `--method` 的 `default='direct_choice'` 改 `default=None`（choices 不变）；
- 新增：

```python
    parser.add_argument('--profile', default=None, help='Phase 6 五维 profile（唯一五维来源）')
    parser.add_argument('--chart-schema-version', default=None, choices=['legacy_v0', 'approved_v1'])
    parser.add_argument('--arm', default=None)
    parser.add_argument('--repeat-idx', type=int, default=0)
    parser.add_argument('--case-ids-file', default=None, help='JSON 数组文件：仅运行其中 case_id')
    parser.add_argument('--resume', action='store_true', help='续跑：跳过已完成 attempt key')
    parser.add_argument('--scheduled-calls', type=int, default=None)
    parser.add_argument('--hard-cap', type=int, default=None)
```

（Phase 6 不注册 `--overwrite`：设计 §4.4.3 禁止任何启动路径截断；重跑只能换新 run/slice 目录。）

- `args = parser.parse_args(argv)` 之后插入（profile 接线 + 截断守卫 + resume manifest + 上下文初始化，完整代码）：

```python
    profile = None
    if args.profile:
        from benchmark.runners.profiles import derive_formatter, resolve_profile
        profile = resolve_profile(args.profile, args.chart_schema_version)
        if profile.dataset == "mingli" and not _mingli_data_ready():
            print(json.dumps({"status": "BLOCKED",
                              "reason": "MingLi 数据前置未完成：先运行 scripts/fetch_mingli_bench.py"},
                             ensure_ascii=False))
            return 4
        args.method = resolve_method(args.profile, args.method)
        detail_abs = os.path.abspath(args.case_details_jsonl) if args.case_details_jsonl else None
        events_abs = None                                  # detail_abs 为空时保持 None（旧行为）
        if detail_abs:
            manifest_path = (detail_abs[:-6] + ".manifest.json"
                             if detail_abs.endswith(".jsonl")
                             else detail_abs + ".manifest.json")
            events_abs = (detail_abs[:-6] + ".events.jsonl"
                          if detail_abs.endswith(".jsonl")
                          else detail_abs + ".events.jsonl")
            detail_exists = os.path.exists(detail_abs)
            manifest_exists = os.path.exists(manifest_path)
            artifact_exists = (detail_exists or manifest_exists
                               or os.path.exists(events_abs))
            if artifact_exists and not args.resume:
                # 任一运行产物存在（含 --resume 首跑崩溃残留的 manifest/events，此时
                # detail 可能不存在）→ 拒绝；否则 Phase6Context(resume=False) 不恢复
                # events 中的 calls_attempted，会静默重置单切片预算
                print(json.dumps({"status": "ARTIFACT_EXISTS", "detail": detail_abs,
                                  "reason": "已有 Phase 6 运行产物（detail/events/manifest 任一）；"
                                            "必须 --resume 续跑，或换用新的 run/slice 目录重跑"
                                            "（禁止任何启动路径截断，设计 §4.4.3）"},
                                 ensure_ascii=False))
                raise SystemExit(2)
            current_manifest = build_resume_manifest(args, profile)
            if manifest_exists:
                check_resume_manifest(manifest_path, current_manifest)  # 不一致 SystemExit(2)
            elif detail_exists or os.path.exists(events_abs):
                # 旧 detail/events 在而 manifest 缺失（被删或旧版本遗留）→ fail-closed，
                # 不得基于当前配置新建 manifest 混合旧结果
                print(json.dumps({"status": "MANIFEST_MISSING",
                                  "detail": detail_abs, "manifest": manifest_path,
                                  "reason": "detail/events 已存在但 manifest 缺失，无法验证旧结果"
                                            "与当前配置一致，禁止续跑（fail-closed，设计 L168）"},
                                 ensure_ascii=False))
                raise SystemExit(2)
            else:
                _atomic_write_json(manifest_path, current_manifest)     # 三态全无 → 首跑创建（含 --resume 首跑）
        init_phase6_context(Phase6Context(
            dataset_id=os.path.splitext(os.path.basename(args.dataset))[0],
            profile_id=profile.profile_id,
            arm=args.arm, attempt_stage="main",
            provider=args.provider, model=args.model,
            repeat_idx=args.repeat_idx,
            detail_path=detail_abs,
            events_path=events_abs,
            scheduled_calls=args.scheduled_calls, hard_cap=args.hard_cap,
            resume=args.resume,
        ))
    else:
        args.method = args.method or "direct_choice"
```

- `cases = load_jsonl(args.dataset)`（:983）之后插入：

```python
    if args.case_ids_file:
        with open(args.case_ids_file, "r", encoding="utf-8") as f:
            wanted = {str(x) for x in json.load(f)}
        cases = [c for c in cases if str(c.get("case_id")) in wanted]
    if args.profile and args.resume:
        completed = load_completed_keys(os.path.abspath(args.case_details_jsonl))
        ctx = _PHASE6_CTX
        cases = [c for c in cases if ctx.attempt_key_for(c) not in completed]
```

- `run_model_benchmark(...)` 调用（:988）参数追加 `chart_schema_version=profile.chart_schema_version if profile else None, profile_formatter=derive_formatter(profile) if profile else None, resume_append=args.resume`；整段调用包 try：

```python
        try:
            model_result = run_model_benchmark(...)
        except _HardCapExhausted:
            _write_phase6_summary(args, "BLOCKED_INCOMPLETE")
            return 3
```

- `:1058` `_write_jsonl(args.case_details_jsonl, case_details)` 改为 `if not args.resume: ...`（resume 时循环 append 已是完整记录，重写会丢旧行）；model_runner 分支末尾（`:1090` 后）追加 `if args.profile: _write_phase6_summary(args, "OK")`。

- `_write_phase6_summary(args, status)`（新函数）：

```python
def _write_phase6_summary(args, status):
    ctx = _PHASE6_CTX
    summary = {
        "status": status,
        "profile_id": args.profile,
        "arm": args.arm,
        "repeat_idx": args.repeat_idx,
        "scheduled_calls": args.scheduled_calls,
        "hard_cap": args.hard_cap,
        "calls_attempted": ctx.calls_attempted if ctx else None,
        "retry_total": sum(ctx.retry_counts.values()) if ctx else None,
    }
    os.makedirs(os.path.abspath(args.output_dir), exist_ok=True)
    with open(os.path.join(os.path.abspath(args.output_dir), "summary.json"),
              "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 5：调用方审计（截断守卫影响面）——审计已执行，结论：0 个调用方需要适配（v4 修正）**

审计命令（已跑）：

```powershell
git grep -n -e "case-details-jsonl" -e "_prepare_jsonl" -e "run_benchmark.py" -- "*.py" "*.ps1" "*.sh"
```

**关键事实**：截断守卫位于 `if args.profile:` 分支内（本任务 4e），只有显式传 `--profile` 的 Phase 6 调用才会进入；以下全部既有调用方均不传 `--profile`，走 else 分支（`args.method = args.method or "direct_choice"`），**永不触发守卫，零修改**。

逐一核对记录（9 个重复拉起 runner 的脚本/PS1——确认不受守卫影响，**保持原样**）：

| 文件 | 行 | 说明 |
| --- | --- | --- |
| `scripts/run_baziqa_fewshot_ablation.py` | 110 | few-shot 消融循环重复调用 runner；无 `--profile`，不受影响 |
| `scripts/run_baziqa_repeated_eval.py` | 27 | 重复评估，detail 路径固定；无 `--profile`，不受影响 |
| `scripts/run_baziqa_retrieval_ablation.py` | 151, 162 | 每 (config, repeat) 调用并写 details；无 `--profile`，不受影响 |
| `scripts/run_mingli_bench.py` | 86, 95 | 子进程调用 runner 写 case_details；无 `--profile`，不受影响 |
| `scripts/run_phase3_ablation.py` | 172, 184 | Phase 3 消融子进程调用；无 `--profile`，不受影响 |
| `scripts/run_phase5_c2_generalization.py` | 41 | Phase 5 泛化验证调用；无 `--profile`，不受影响 |
| `scripts/verify_baziqa_lovo.ps1` | 34 | 验证脚本重复执行；无 `--profile`，不受影响 |
| `scripts/verify_baziqa_rag_lift.ps1` | 37 | 验证脚本重复执行；无 `--profile`，不受影响 |
| `scripts/verify_baziqa_smoke.ps1` | 44 | 验证脚本重复执行；无 `--profile`，不受影响 |

**豁免（与守卫无关，仅登记核对）**：

- `scripts/analyze_baziqa_error_attribution.py`、`scripts/compute_retrieved_answer_leak.py`：`--case-details-jsonl` 是**输入**路径（读 detail 做归因/泄漏分析），不启动 runner。
- `scripts/dryrun_ablation_task4_1.py`、`tests/test_run_baziqa_retrieval_ablation_cli.py`：只解析/断言命令行 token，不真实执行 runner。
- `scripts/evaluate_hybrid_offline.py`：仅注释引用 chart 构造逻辑，无 runner 调用。
- `tests/test_benchmark_runner.py`（L28、L375）：detail 路径均为 `tmp_path` 下每测试全新目录。
- `tests/test_baziqa_error_attribution.py:18`：传给归因脚本的输入路径，非 runner。

执行代理核对义务：实现 4e 后，用 `git grep -n -- "--profile" -- "scripts/*.py" "scripts/*.ps1"` 再确认一次无旧调用方传 `--profile`；若有新增调用方传入，再评估是否受影响。

- [ ] **Step 6：全绿 + 回归**

```powershell
python -m pytest tests/test_phase6_resume.py tests/test_phase6_runner_routing.py -q
python -m pytest tests/ -q -m "not e2e"
```

全绿方进 Step 7。

- [ ] **Step 7：提交（精确路径；禁止 `git add -A`）**

```powershell
git add benchmark/runners/run_benchmark.py benchmark/formatters/baziqa_prompt.py tests/test_phase6_resume.py tests/test_phase6_runner_routing.py tests/phase6_helpers.py tests/run_benchmark_proxy.py
git commit -m "feat(phase6): runner 五维 profile 接线 + 截断守卫（无 --overwrite）+ resume manifest 校验 + attempt key（旧调用方零修改：守卫仅在 --profile 分支生效）"
```

---

## Task 7：重试账本跨 resume 与双列预算 BLOCKED_INCOMPLETE

**目的**：设计 §4.4.2 的完整行为验证——重试上限 3 跨 resume 不重置、`call_failed` 计入分母、hard_cap 耗尽判 BLOCKED_INCOMPLETE（退出码 3）且不得进入决策。

- [ ] **Step 1：写失败测试 `tests/test_phase6_retry_budget.py`（完整代码）**

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.run_benchmark import compute_hard_cap
from tests.phase6_helpers import RunnerEnv


@pytest.mark.parametrize("scheduled,expected", [
    (260, 290), (820, 910), (720, 800), (3600, 3960),
    (960, 1060), (3840, 4230), (480, 530), (1920, 2120),
])
def test_compute_hard_cap_design_values(scheduled, expected):
    assert compute_hard_cap(scheduled) == expected


def test_retry_then_success(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_fails(1)                       # 第 1 次失败，第 2 次成功
    assert env.run(profile="baziqa_xjz_direct") == 0
    assert len(env.read_events("model_call_failed")) == 1
    assert len(env.read_events("call_attempt")) == 2   # 失败 1 次 + 成功 1 次均记账
    assert env.read_detail()[0]["terminal_state"] == "parsed"


def test_retry_exhausted_call_failed(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_fails(3)                       # 3 次网络尝试全部失败
    assert env.run(profile="baziqa_xjz_direct") == 0
    events = env.read_events("model_call_failed")
    assert [e["retry_idx"] for e in events] == [1, 2, 3]
    assert len(env.read_events("call_attempt")) == 3   # 每次失败调用前均已记账
    row = env.read_detail()[0]
    assert row["terminal_state"] == "call_failed"
    assert row["correct"] is False           # call_failed 按错误计入分母


def test_retry_ledger_survives_crash_and_resume(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_fails_then_crash(2)            # 2 次网络失败后进程崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct")
    assert [e["retry_idx"] for e in env.read_events("model_call_failed")] == [1, 2]
    assert env.read_detail() == []           # 无终态
    assert len(env.read_events("call_attempt")) == 2
    env.model_fails(1)                       # resume：第 3 次（最后额度）仍失败
    assert env.run(profile="baziqa_xjz_direct", resume=True) == 0
    assert [e["retry_idx"] for e in env.read_events("model_call_failed")] == [1, 2, 3]
    assert len(env.read_events("call_attempt")) == 3   # 跨 resume 累计，不重置
    assert env.read_detail()[0]["terminal_state"] == "call_failed"


def test_hard_cap_exhausted_blocked_incomplete(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
    env.model_fails(100)                     # 所有调用都失败
    code = env.run(profile="baziqa_xjz_direct", scheduled_calls=2, hard_cap=4)
    assert code == 3
    summary = env.read_summary()
    assert summary["status"] == "BLOCKED_INCOMPLETE"
    assert summary["calls_attempted"] == 4   # 先记账后调用，耗尽即停


def test_calls_attempted_restored_across_resume(tmp_path, monkeypatch):
    """hard cap 跨 resume 持久化：成功调用同样记账；崩溃 attempt 已消耗额度，
    resume 后不得因计数器归零而获得新额度。"""
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=3)
    env.model_succeeds_then_crash("A", successes=2)   # c1、c2 成功；c3 调用时进程崩溃
    env.run_expect_crash(profile="baziqa_xjz_direct",
                         scheduled_calls=3, hard_cap=3)
    assert len(env.read_events("call_attempt")) == 3   # c3 的 attempt 已发起并记账
    assert len(env.read_detail()) == 2                 # 仅 c1、c2 终态
    env.model_returns("A")
    code = env.run(profile="baziqa_xjz_direct", resume=True,
                   scheduled_calls=3, hard_cap=3)
    assert code == 3                                   # 额度已耗尽 → BLOCKED_INCOMPLETE
    summary = env.read_summary()
    assert summary["status"] == "BLOCKED_INCOMPLETE"
    assert summary["calls_attempted"] == 3             # 从事件恢复，未归零
    assert len(env.read_events("call_attempt")) == 3   # 无新增调用
    assert len(env.read_detail()) == 2                 # c3 未再执行
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_phase6_retry_budget.py -q`

预期：`compute_hard_cap` ImportError / 预算行为断言失败（Task 6 已给实现骨架；本任务验证并补齐缺口）。

- [ ] **Step 3：补齐实现缺口**

Task 6 的 4b/4c/4e 已包含 `compute_hard_cap` 与账本主体；本步只处理 Step 2 暴露的差异（如 `_write_phase6_summary` 在 `_HardCapExhausted` 时 `calls_attempted` 计数、summary 字段）。改动必须让 Step 1 全部转绿，且不回改测试。

- [ ] **Step 4：全绿 + 回归**

```powershell
python -m pytest tests/test_phase6_retry_budget.py tests/test_phase6_resume.py -q
python -m pytest tests/ -q -m "not e2e"
```

- [ ] **Step 5：提交（精确路径）**

```powershell
git add benchmark/runners/run_benchmark.py tests/test_phase6_retry_budget.py
git commit -m "feat(phase6): 重试账本跨 resume + 双列预算 BLOCKED_INCOMPLETE"
```

---

## Task 8：`trimmed_mean` 与报告附列

**目的**：设计 §2.1/§4.5——MingLi 以 trimmed mean 为主指标、BaziQA 辅助。6A0 只交付统计函数与报告机制；MingLi 官方截尾比例待 Task 5 勘察核实，未核实前报告中 trimmed mean 仅作描述性附列、不入任何 gate。

- [ ] **Step 1：写失败测试 `tests/test_trimmed_mean.py`（完整代码）**

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.reports.accuracy_stats import trimmed_mean
from benchmark.reports.generate_report import generate_markdown_report


def test_trimmed_mean_known_values():
    assert trimmed_mean([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.1) == 5.5   # k=1，去 1 与 10
    assert trimmed_mean([0.2, 0.3, 0.9], 0.1) == (0.2 + 0.3 + 0.9) / 3  # k=0 不截


def test_trimmed_mean_edge_cases():
    assert trimmed_mean([], 0.1) == 0.0
    assert trimmed_mean([0.5], 0.1) == 0.5
    assert trimmed_mean([1, 100], 0.4) == 1.0 or trimmed_mean([1, 100], 0.4) == 50.5
    # n=2, k=0（int(2*0.4)=0）→ 不截，均值 50.5；断言以此为准：
    assert trimmed_mean([1, 100], 0.4) == 50.5


def test_report_lists_trimmed_mean_when_present():
    result = {
        "run_id": "t1", "provider": "deepseek", "model": "m", "method": "direct_choice",
        "prompt_version": "srp_v1", "reasoning_protocol": "xuanjizi_srp_v1",
        "choice_accuracy": {"accuracy": 0.5, "correct": 1, "total": 2},
        "evidence_score": 0.5, "safety_score": 1.0, "run_date": "2026-07-17",
        "accuracy_trimmed_mean": 0.475,
    }
    md = generate_markdown_report(result)
    assert "截尾均值" in md and "0.475" in md


def test_report_omits_trimmed_mean_when_absent():
    result = {
        "run_id": "t2", "provider": "deepseek", "model": "m", "method": "direct_choice",
        "prompt_version": "srp_v1", "reasoning_protocol": "xuanjizi_srp_v1",
        "choice_accuracy": {"accuracy": 0.5, "correct": 1, "total": 2},
        "evidence_score": 0.5, "safety_score": 1.0, "run_date": "2026-07-17",
    }
    assert "截尾均值" not in generate_markdown_report(result)
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_trimmed_mean.py -q` → `ImportError`。

- [ ] **Step 3：实现**

`benchmark/reports/accuracy_stats.py` 追加：

```python
def trimmed_mean(values: Iterable[float], proportion: float = 0.1) -> float:
    vals = sorted(float(v) for v in values)
    if not vals:
        return 0.0
    k = int(len(vals) * proportion)
    core = vals[k:len(vals) - k] if k else vals
    return sum(core) / len(core)
```

`benchmark/reports/generate_report.py`：`generate_markdown_report` 的"本报告生成信息"表中，当 `result.get("accuracy_trimmed_mean") is not None` 时追加一行 `| 截尾均值 | {result["accuracy_trimmed_mean"]} |`（Read 后 Edit，只动该表区域）。

- [ ] **Step 4：全绿 + 回归**

```powershell
python -m pytest tests/test_trimmed_mean.py -q
python -m pytest tests/ -q -m "not e2e"
```

- [ ] **Step 5：提交（精确路径）**

```powershell
git add benchmark/reports/accuracy_stats.py benchmark/reports/generate_report.py tests/test_trimmed_mean.py
git commit -m "feat(phase6): trimmed_mean 统计与报告附列（描述性，不入 gate）"
```

---

## Task 9：编排器 `scripts/run_phase6_6a0_ablation.py`——AB/BA 12 切片调度、离线 gate、Δ 判定与报告

**目的**：落地设计 §4.2.5（AB/BA 平衡配对）与 §4.6（离线 gate + dev gate）。**v1 评审阻 1 修复核心**：每个 repeat 不是 2 次全量 arm-run，而是 **4 个 20 题切片**；组 A 先 approved 后 legacy，组 B 先 legacy 后 approved，逐切片控制执行顺序与预算。

**调度结构（设计期冻结）**：40 题按 seed 固定分两组（各 20）。每 repeat 4 切片，顺序恒为 `[group_a approved, group_a legacy, group_b legacy, group_b approved]`，cap 恒为 `[23, 23, 22, 22]`（和 90）；3 repeats 主切片 cap 和 270 + smoke 20（group_a 题、ctx_approved、canary 无储备）= **290 = 阶段 hard_cap**。smoke 与 repeat 0 的 group_a approved 题目重叠是刻意的 canary 复测（预算已含，设计 §8 260+30）。**每切片独立输出目录** `slice_{purpose}_{repeat}_{group}/`（detail/events/summary 均在其中，报告聚合 glob `slice_*/detail.jsonl`）；smoke 恒 `repeat_idx=-1` 原样透传，与主切片 attempt key 天然不相交（canary 复测真实发起调用，不被 resume 跳过）；**阶段预算由 `BudgetLedger`**（`config.root/budget/<run_id>.jsonl`）**按 slice_id 幂等记账**（同一切片重复完成时覆盖旧值、取 max 防回退；阶段总数 = 各切片最新值之和），切片启动前按 `total + (cap − 该切片已计)` 预占检查（resume 不重复占额），完成后按实际 `calls_attempted` 记账（崩溃路径从切片 events 兜底计数）。

**成本口径（如实声明）**：模型 API 只回文本、不返回 token usage；报告的"token 与成本对比"以**各臂 prompt 字符数 + 调用次数**为代理指标并明确标注，不伪造 token 数。`call_failed` 计数单列，超过题目数 5% 标注"环境污染"（设计 §12.6）。

- [ ] **Step 1：写失败测试 `tests/test_phase6_6a0_ablation.py`（完整代码）**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase6_6a0_ablation import (
    PROFILE_ID,
    AblationConfig,
    BudgetLedger,
    SliceRun,
    aggregate_delta,
    build_schedule,
    gate_verdict,
    offline_gate,
    run_ablation,
    split_ab_ba,
)
from tests.phase6_helpers import RunnerSpy, fake_config, write_jsonl

CASE_IDS = [f"c{i}" for i in range(40)]


def test_split_ab_ba_deterministic_and_disjoint():
    a1, b1 = split_ab_ba(CASE_IDS, seed=20260717)
    a2, b2 = split_ab_ba(CASE_IDS, seed=20260717)
    assert (a1, b1) == (a2, b2)
    assert len(a1) == len(b1) == 20
    assert set(a1).isdisjoint(set(b1))
    assert set(a1) | set(b1) == set(CASE_IDS)


def test_build_schedule_full_sequence():
    """阻 1：逐切片断言 (purpose, repeat, arm, group, case_ids, scheduled, cap) 全序列。"""
    config = fake_config()
    group_a, group_b = split_ab_ba(CASE_IDS, seed=config.seed)
    schedule = build_schedule(config, CASE_IDS)
    assert len(schedule) == 13                      # 1 smoke + 3 repeats × 4 切片

    s = schedule[0]
    assert (s.purpose, s.repeat_idx, s.arm, s.group) == ("smoke", -1, "ctx_approved", "smoke")
    assert s.case_ids == group_a                    # smoke 用 group_a 20 题（canary 复测）
    assert (s.scheduled_calls, s.hard_cap) == (20, 20)

    expected_order = [("ctx_approved", "group_a"), ("ctx_legacy", "group_a"),
                      ("ctx_legacy", "group_b"), ("ctx_approved", "group_b")]
    expected_caps = [23, 23, 22, 22]
    for repeat in range(3):
        for j, ((arm, group), cap) in enumerate(zip(expected_order, expected_caps)):
            s = schedule[1 + repeat * 4 + j]
            assert (s.purpose, s.repeat_idx, s.arm, s.group) == ("main", repeat, arm, group)
            assert s.case_ids == (group_a if group == "group_a" else group_b)
            assert (s.scheduled_calls, s.hard_cap) == (20, cap)


def test_build_schedule_cap_sums():
    schedule = build_schedule(fake_config(), CASE_IDS)
    main_caps = [s.hard_cap for s in schedule if s.purpose == "main"]
    assert len(main_caps) == 12
    assert sum(main_caps) == 270
    assert sum(main_caps) + schedule[0].hard_cap == 290 == fake_config().stage_hard_cap
    assert sum(s.scheduled_calls for s in schedule) == 260 == fake_config().stage_scheduled


def test_build_schedule_requires_40_cases():
    with pytest.raises(ValueError):
        build_schedule(fake_config(), CASE_IDS[:39])


@pytest.mark.parametrize("delta,expected", [
    (2.0, "ADOPT"), (5.0, "ADOPT"),
    (1.99, "ADOPT_FOUNDATION"), (0.0, "ADOPT_FOUNDATION"),
    (-0.01, "ROLLBACK"), (-7.5, "ROLLBACK"),
])
def test_gate_verdict_boundaries(delta, expected):
    assert gate_verdict(delta) == expected


def test_run_ablation_invokes_slices_in_order(tmp_path):
    config = fake_config(root=tmp_path)
    spy = RunnerSpy()
    schedule = build_schedule(config, CASE_IDS)
    run_ablation(config, schedule, slice_runner=spy)   # schedule 由调用方构建传入
    assert len(spy.calls) == 13
    for call, expected in zip(spy.calls, schedule):
        assert call.slice == expected
        assert call.kwargs["hard_cap"] == expected.hard_cap
        assert call.kwargs["scheduled_calls"] == expected.scheduled_calls


def test_run_ablation_smoke_schedule_single_call(tmp_path):
    """阻 1：--smoke-only 语义——传入 smoke schedule 时只执行 1 个切片（函数内不得重建）。"""
    config = fake_config(root=tmp_path)
    spy = RunnerSpy()
    smoke_schedule = [s for s in build_schedule(config, CASE_IDS) if s.purpose == "smoke"]
    assert len(smoke_schedule) == 1
    result = run_ablation(config, smoke_schedule, slice_runner=spy)
    assert len(spy.calls) == 1
    assert spy.calls[0].slice.purpose == "smoke"
    assert result["status"] == "OK"


def test_smoke_attempt_keys_disjoint_from_main(tmp_path):
    """阻 2：smoke（repeat_idx=-1）与 12 个主切片的 attempt key 集合不相交。"""
    from benchmark.runners.run_benchmark import build_attempt_key

    config = fake_config(root=tmp_path)
    schedule = build_schedule(config, CASE_IDS)

    def keys_for(slice_run):
        return {
            build_attempt_key("baziqa", PROFILE_ID, slice_run.arm, "main",
                              config.provider, config.model, cid,
                              slice_run.repeat_idx, 0, "p0")
            for cid in slice_run.case_ids
        }

    smoke_keys = keys_for(schedule[0])
    assert smoke_keys
    for s in schedule[1:]:
        assert smoke_keys.isdisjoint(keys_for(s)), (
            f"smoke 与 {s.arm}/{s.group}/r{s.repeat_idx} 键碰撞")


class _FailingSpy(RunnerSpy):
    def __init__(self, fail_at: int):
        super().__init__()
        self.fail_at = fail_at

    def __call__(self, slice_run, **kwargs):
        super().__call__(slice_run, **kwargs)
        code = 3 if len(self.calls) == self.fail_at else 0
        return type("ArmRunResult", (), {"exit_code": code, "records": [],
                                         "calls_attempted": 0})


def test_run_ablation_aborts_on_blocked_incomplete(tmp_path):
    config = fake_config(root=tmp_path)
    spy = _FailingSpy(fail_at=2)
    result = run_ablation(config, build_schedule(config, CASE_IDS), slice_runner=spy)
    assert len(spy.calls) == 2                      # 第 2 切片退出码 3 → 后续切片不执行
    assert result["status"] == "BLOCKED_INCOMPLETE"


def test_stage_budget_ledger_overflow_aborts(tmp_path):
    """阻 3：阶段总账本——已记账额度 + 下一切片剩余 cap 超过阶段 hard_cap 即中止，不发起任何调用。"""
    config = fake_config(root=tmp_path)
    ledger_path = tmp_path / "budget" / f"{config.run_id}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps({"external_prior": {"hard_cap": 280, "calls_attempted": 280,
                                       "timestamp": "2026-07-17T00:00:00"}}),
        encoding="utf-8")
    spy = RunnerSpy()
    result = run_ablation(config, build_schedule(config, CASE_IDS), slice_runner=spy)
    assert spy.calls == []                          # 首切片即中止
    assert result["status"] == "FAILED"
    assert "budget" in result["reason"]


class _CountingSpy(RunnerSpy):
    """按切片 scheduled_calls 报告实际调用数（模拟真实跑满且无重试的切片）。"""

    def __call__(self, slice_run, **kwargs):
        super().__call__(slice_run, **kwargs)
        return type("ArmRunResult", (), {"exit_code": 0, "records": [],
                                         "calls_attempted": slice_run.scheduled_calls})


def test_stage_ledger_idempotent_smoke_then_full(tmp_path):
    """v4 阻 1：smoke-only 后接全量，smoke 切片额度按 slice_id 幂等，不重复累计。"""
    config = fake_config(root=tmp_path)
    schedule = build_schedule(config, CASE_IDS)
    spy = _CountingSpy()
    smoke_schedule = [s for s in schedule if s.purpose == "smoke"]
    assert run_ablation(config, smoke_schedule, slice_runner=spy)["status"] == "OK"
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    smoke_id = "smoke_-1_ctx_approved_smoke"
    assert ledger.attempted_for(smoke_id) == 20
    assert ledger.total_attempted() == 20
    assert run_ablation(config, schedule, slice_runner=spy)["status"] == "OK"
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    assert ledger.attempted_for(smoke_id) == 20     # 不变成 40
    assert ledger.total_attempted() == 260          # 13 切片 × 20，smoke 不重复计


def test_stage_ledger_resume_no_phantom_overflow(tmp_path):
    """v4 阻 1：完整实验再次 resume，阶段总数不变，不误报 overflow。"""
    config = fake_config(root=tmp_path)
    schedule = build_schedule(config, CASE_IDS)
    spy = _CountingSpy()
    assert run_ablation(config, schedule, slice_runner=spy)["status"] == "OK"
    first = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl").total_attempted()
    assert first == 260
    # 再次"resume"：各切片报告相同累计值，启动前检查只按剩余额度预占
    assert run_ablation(config, schedule, slice_runner=spy)["status"] == "OK"
    assert BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl").total_attempted() == first


def test_stage_ledger_corrupt_json_blocked(tmp_path):
    """v5 阻 2：账本 JSON 损坏 → fail-closed（BLOCKED_INCOMPLETE），不发起任何调用。"""
    config = fake_config(root=tmp_path)
    ledger_path = tmp_path / "budget" / f"{config.run_id}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("{not json", encoding="utf-8")
    spy = RunnerSpy()
    result = run_ablation(config, build_schedule(config, CASE_IDS), slice_runner=spy)
    assert spy.calls == []
    assert result["status"] == "BLOCKED_INCOMPLETE"
    assert "budget ledger corrupt" in result["reason"]


def test_stage_ledger_over_cap_record_blocked(tmp_path):
    """v5 阻 2：calls_attempted > hard_cap 的账本记录 → fail-closed（负值/结构错误同路径）。"""
    config = fake_config(root=tmp_path)
    ledger_path = tmp_path / "budget" / f"{config.run_id}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps({
        "main_0_ctx_approved_group_a": {"hard_cap": 23, "calls_attempted": 24,
                                        "timestamp": "2026-07-17T00:00:00"}}),
        encoding="utf-8")
    spy = RunnerSpy()
    result = run_ablation(config, build_schedule(config, CASE_IDS), slice_runner=spy)
    assert spy.calls == []
    assert result["status"] == "BLOCKED_INCOMPLETE"
    assert "budget ledger corrupt" in result["reason"]


def test_stage_ledger_atomic_write(tmp_path):
    """v5 阻 2：账本经临时文件 + os.replace 原子替换，无 .tmp 残留；覆盖语义保持幂等。"""
    config = fake_config(root=tmp_path)
    ledger = BudgetLedger(tmp_path / "budget" / f"{config.run_id}.jsonl")
    ledger.record("s1", 23, 20)
    ledger.record("s1", 23, 21)                          # 同 slice_id 覆盖
    assert not (tmp_path / "budget" / f"{config.run_id}.jsonl.tmp").exists()
    assert ledger.attempted_for("s1") == 21
    assert ledger.total_attempted() == 21


def detail_row(case_id, correct, repeat_idx, arm):
    return {"case_id": case_id, "correct": correct, "repeat_idx": repeat_idx,
            "arm": arm, "terminal_state": "parsed"}


def test_aggregate_delta_and_verdict():
    rows = []
    for repeat in range(3):
        for i in range(20):
            rows.append(detail_row(f"a{i}", i < 12, repeat, "ctx_approved"))   # 60%
            rows.append(detail_row(f"b{i}", i < 12, repeat, "ctx_approved"))
            rows.append(detail_row(f"a{i}", i < 10, repeat, "ctx_legacy"))     # 50%
            rows.append(detail_row(f"b{i}", i < 10, repeat, "ctx_legacy"))
    agg = aggregate_delta(rows, repeats=3)
    assert agg["per_repeat_delta_pp"] == [10.0, 10.0, 10.0]
    assert agg["delta_dev_pp"] == 10.0
    assert agg["verdict"] == "ADOPT"


def _write_enriched(path: Path, case_ids, leak: str | None = None):
    fixture = json.loads((PROJECT_ROOT / "tests" / "fixtures" / "phase6" / "case_sample_1.json")
                         .read_text(encoding="utf-8"))
    rows = []
    for cid in case_ids:
        row = json.loads(json.dumps(fixture))
        row["case_id"] = cid
        if leak:
            row["question"] = row["question"] + leak
        rows.append(row)
    write_jsonl(path, rows)


def test_offline_gate_passes_and_detects_leak(tmp_path):
    enriched = tmp_path / "enriched.jsonl"
    _write_enriched(enriched, ["c0", "c1"])
    config = fake_config(root=tmp_path, enriched_path=enriched)
    assert offline_gate(config) == []
    _write_enriched(enriched, ["c0", "c1"], leak="（正确答案：B）")
    failures = offline_gate(config)
    assert any("leak" in f or "泄漏" in f for f in failures)
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_phase6_6a0_ablation.py -q` → `ModuleNotFoundError`。

- [ ] **Step 3：实现 `scripts/run_phase6_6a0_ablation.py`（完整代码）**

```python
"""Phase 6 6A0 编排器：离线 gate、AB/BA 12 切片调度、双列预算接线、Δ 与判定、报告。

决策逻辑均为无网络纯函数（可单测）；真实模型调用仅经 run_slice 子进程边界发起。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.baziqa_prompt import format_direct_choice_prompt
from benchmark.formatters.chart_context import (
    CHART_CONTEXT_TEMPLATE_VERSION,
    approved_field_presence,
    render_chart_context,
)
from benchmark.formatters.leak_scan import scan_prompt_for_leaks
from benchmark.runners.profiles import assert_visibility, resolve_profile
from scripts.enrich_baziqa_chart_input import load_jsonl

ARMS = ("ctx_approved", "ctx_legacy")
ARM_SCHEMA = {"ctx_approved": "approved_v1", "ctx_legacy": "legacy_v0"}
SLICE_ORDER = (("ctx_approved", "group_a"), ("ctx_legacy", "group_a"),
               ("ctx_legacy", "group_b"), ("ctx_approved", "group_b"))
SLICE_CAPS = (23, 23, 22, 22)
PROFILE_ID = "baziqa_xjz_direct"
EXPECTED_CASES = 40


@dataclass(frozen=True)
class AblationConfig:
    run_id: str
    year: int
    root: Path
    enriched_path: Path
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    repeats: int = 3
    smoke_size: int = 20
    seed: int = 20260717
    as_of_date: str = "2026-07-17"
    stage_scheduled: int = 260
    stage_hard_cap: int = 290
    resume: bool = True


@dataclass(frozen=True)
class SliceRun:
    purpose: str                 # "smoke" | "main"
    repeat_idx: int              # smoke 固定 -1
    arm: str                     # "ctx_approved" | "ctx_legacy"
    group: str                   # "group_a" | "group_b" | "smoke"
    case_ids: tuple[str, ...]
    scheduled_calls: int
    hard_cap: int


def split_ab_ba(case_ids: list[str], seed: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids = list(case_ids)
    random.Random(seed).shuffle(ids)
    half = len(ids) // 2
    return tuple(ids[:half]), tuple(ids[half:])


def build_schedule(config: AblationConfig, case_ids: list[str]) -> list[SliceRun]:
    if len(case_ids) != EXPECTED_CASES:
        raise ValueError(f"6A0 dev gate 要求 {EXPECTED_CASES} 题，实得 {len(case_ids)}")
    group_a, group_b = split_ab_ba(case_ids, config.seed)
    schedule = [SliceRun("smoke", -1, "ctx_approved", "smoke", group_a, config.smoke_size,
                         config.smoke_size)]
    groups = {"group_a": group_a, "group_b": group_b}
    for repeat in range(config.repeats):
        for (arm, group), cap in zip(SLICE_ORDER, SLICE_CAPS):
            schedule.append(SliceRun("main", repeat, arm, group, groups[group],
                                     config.smoke_size, cap))
    total_cap = sum(s.hard_cap for s in schedule)
    if total_cap != config.stage_hard_cap:
        raise ValueError(f"切片 cap 和 {total_cap} != 阶段 hard_cap {config.stage_hard_cap}")
    return schedule


def gate_verdict(delta_pp: float) -> str:
    if delta_pp >= 2.0:
        return "ADOPT"
    if delta_pp >= 0.0:
        return "ADOPT_FOUNDATION"
    return "ROLLBACK"


def aggregate_delta(rows: list[dict], repeats: int) -> dict:
    def accuracy(arm: str, repeat: int) -> float:
        # repeat ∈ range(repeats)；smoke 行 repeat_idx=-1 被 == 比较天然排除，不进主指标
        sel = [r for r in rows
               if r.get("arm") == arm and int(r.get("repeat_idx", -1)) == repeat]
        if not sel:
            raise ValueError(f"缺数据：arm={arm} repeat={repeat}")
        return sum(1 for r in sel if r.get("correct")) / len(sel)

    per_repeat = []
    for repeat in range(repeats):
        per_repeat.append(round((accuracy("ctx_approved", repeat)
                                 - accuracy("ctx_legacy", repeat)) * 100, 2))
    delta_dev = round(sum(per_repeat) / len(per_repeat), 2)
    return {
        "per_repeat_delta_pp": per_repeat,
        "delta_dev_pp": delta_dev,
        "verdict": gate_verdict(delta_dev),
        "call_failed": sum(1 for r in rows if r.get("terminal_state") == "call_failed"),
    }


def offline_gate(config: AblationConfig) -> list[str]:
    """无网络离线 gate：批准字段 presence、可见性矩阵、泄漏扫描。返回失败列表（空=通过）。"""
    failures: list[str] = []
    if not config.enriched_path.exists():
        return [f"enriched 文件缺失: {config.enriched_path}（先运行 Task 3 enrichment）"]
    rows = load_jsonl(config.enriched_path)
    profile = resolve_profile(PROFILE_ID)
    for row in rows:
        cid = row.get("case_id")
        presence = approved_field_presence(row.get("chart_input") or {})
        missing = [k for k, ok in presence.items() if not ok]
        if missing:
            failures.append(f"{cid}: 批准字段缺失 {missing}")
            continue
        for arm, schema in ARM_SCHEMA.items():
            rendered = render_chart_context(row, schema, as_of_date=config.as_of_date)
            arm_profile = resolve_profile(PROFILE_ID, schema)
            for v in assert_visibility(rendered, arm_profile, schema):
                failures.append(f"{cid}/{arm}: {v}")
            prompt = format_direct_choice_prompt(row, chart_context_text=rendered)
            for hit in scan_prompt_for_leaks(prompt, row):
                failures.append(f"{cid}/{arm}: leak {hit.kind} {hit.detail}")
    return failures


def run_slice(slice_run: SliceRun, config: AblationConfig, **kwargs) -> object:
    """真实边界：子进程调用 runner。测试中以 RunnerSpy 替换。

    每切片独立目录 slice_{purpose}_{repeat}_{group}/（detail/events/summary 均在其中），
    --repeat-idx 原样透传（smoke 为 -1，禁止 max 修正——否则与 repeat 0 键碰撞）。
    """
    run_dir = (config.root / slice_run.arm / "runs" / config.run_id
               / f"slice_{slice_run.purpose}_{slice_run.repeat_idx}_{slice_run.group}")
    run_dir.mkdir(parents=True, exist_ok=True)
    ids_file = run_dir / "case_ids.json"
    ids_file.write_text(json.dumps(list(slice_run.case_ids), ensure_ascii=False),
                        encoding="utf-8")
    detail_path = run_dir / "detail.jsonl"
    argv = [
        sys.executable, "-m", "benchmark.runners.run_benchmark",
        "--dataset", str(config.enriched_path),
        "--model-runner", "--provider", config.provider, "--model", config.model,
        "--profile", PROFILE_ID,
        "--chart-schema-version", ARM_SCHEMA[slice_run.arm],
        "--arm", slice_run.arm,
        "--repeat-idx", str(slice_run.repeat_idx),
        "--case-ids-file", str(ids_file),
        "--case-details-jsonl", str(detail_path),
        "--output-dir", str(run_dir),
        "--scheduled-calls", str(slice_run.scheduled_calls),
        "--hard-cap", str(slice_run.hard_cap),
    ]
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
        # 崩溃路径：summary 缺失/为 0 时以事件日志为准（call_attempt 含成功与失败调用）
        events_path = run_dir / "detail.events.jsonl"
        if events_path.exists():
            calls_attempted = sum(
                1 for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line).get("kind") == "call_attempt")
    return type("ArmRunResult", (), {"exit_code": proc.returncode, "records": [],
                                     "calls_attempted": calls_attempted,
                                     "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]})


class BudgetLedgerCorrupt(Exception):
    """预算账本损坏：JSON 坏/结构错/非 int/负值/calls_attempted > hard_cap——一律 fail-closed。"""


class BudgetLedger:
    """阶段总预算账本（config.root/budget/<run_id>.jsonl）：**按 slice_id 幂等 + fail-closed**。

    JSON dict 存储 slice_id → {"calls_attempted", "hard_cap", "timestamp"}。
    runner 的 calls_attempted 是切片级累计值（resume 时从事件恢复），因此同一切片
    重复完成时**覆盖**而非追加——smoke-only 后接全量不会把 smoke 记成两倍。
    record 取 max(旧值, 新值)：崩溃等异常路径 summary 缺失时账本不回退。
    **fail-closed**：账本 JSON 损坏、结构错误、非 int、负值、calls_attempted > hard_cap
    一律抛 BudgetLedgerCorrupt（run_ablation 转 BLOCKED_INCOMPLETE）——预算是安全约束，
    损坏时宁可停工也不静默放行。写入经临时文件 + os.replace 原子替换，中断不留半文件。
    正常运行下各切片 cap 和 == 阶段 hard_cap，启动前检查永不触发。
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    @staticmethod
    def _validate(data: dict) -> dict:
        if not isinstance(data, dict):
            raise BudgetLedgerCorrupt("账本顶层结构非 dict")
        for slice_id, row in data.items():
            if not isinstance(row, dict):
                raise BudgetLedgerCorrupt(f"{slice_id}: 记录非 dict")
            calls, cap = row.get("calls_attempted"), row.get("hard_cap")
            if not isinstance(calls, int) or not isinstance(cap, int):
                raise BudgetLedgerCorrupt(f"{slice_id}: calls_attempted/hard_cap 非 int")
            if calls < 0 or cap < 0:
                raise BudgetLedgerCorrupt(f"{slice_id}: 负值 calls={calls} cap={cap}")
            if calls > cap:
                raise BudgetLedgerCorrupt(
                    f"{slice_id}: calls_attempted {calls} > hard_cap {cap}")
        return data

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except BudgetLedgerCorrupt:
            raise
        except Exception as exc:
            raise BudgetLedgerCorrupt(f"账本 JSON 损坏: {self.path}: {exc}") from exc
        return self._validate(data)

    def total_attempted(self) -> int:
        return sum(int(v["calls_attempted"]) for v in self._load().values())

    def attempted_for(self, slice_id: str) -> int:
        return int((self._load().get(slice_id) or {}).get("calls_attempted") or 0)

    def record(self, slice_id: str, hard_cap: int, calls_attempted: int) -> None:
        data = self._load()
        prev = int((data.get(slice_id) or {}).get("calls_attempted") or 0)
        new_row = {"hard_cap": int(hard_cap),
                   "calls_attempted": max(prev, int(calls_attempted)),
                   "timestamp": datetime.now().isoformat(timespec="seconds")}
        self._validate({slice_id: new_row})   # 新值同样 fail-closed（runner 自报超 cap 即损坏）
        data[slice_id] = new_row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self.path) + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)            # 原子替换，中断不留半文件


def run_ablation(config: AblationConfig, schedule: list[SliceRun], slice_runner=None) -> dict:
    """执行**给定的** schedule（函数内不得重建——否则 main() 的 --smoke-only 过滤失效）。

    阶段预算经 BudgetLedger 按 slice_id 幂等累计；每切片启动前检查
    total + (hard_cap − 该切片已计)（已完成切片只按剩余额度预占，resume 不重复计），
    完成后按实际 calls_attempted 记账（含失败中止路径——已发起的调用必须入账）。
    账本损坏（BudgetLedgerCorrupt）或 schedule 与账本背离（remaining < 0）→
    BLOCKED_INCOMPLETE，fail-closed，不得进入决策。
    """
    runner = slice_runner or (lambda s, **kw: run_slice(s, config, **kw))
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    for slice_run in schedule:
        slice_id = f"{slice_run.purpose}_{slice_run.repeat_idx}_{slice_run.arm}_{slice_run.group}"
        try:
            attempted = ledger.attempted_for(slice_id)
            overflow = (ledger.total_attempted() + (slice_run.hard_cap - attempted)
                        > config.stage_hard_cap)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if attempted > slice_run.hard_cap:
            return {"status": "BLOCKED_INCOMPLETE",
                    "reason": f"budget ledger inconsistent: {slice_id} attempted {attempted} "
                              f"> slice hard_cap {slice_run.hard_cap}"}
        if overflow:
            return {"status": "FAILED",
                    "reason": f"stage budget overflow: attempted {ledger.total_attempted()} "
                              f"+ remaining cap {slice_run.hard_cap - attempted} ({slice_id}) "
                              f"> {config.stage_hard_cap}",
                    "abort_at": {"arm": slice_run.arm, "repeat_idx": slice_run.repeat_idx,
                                 "group": slice_run.group}}
        result = runner(slice_run, scheduled_calls=slice_run.scheduled_calls,
                        hard_cap=slice_run.hard_cap)
        try:
            ledger.record(slice_id, slice_run.hard_cap,
                          getattr(result, "calls_attempted", 0) or 0)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if result.exit_code == 3:
            return {"status": "BLOCKED_INCOMPLETE", "abort_at": {
                "arm": slice_run.arm, "repeat_idx": slice_run.repeat_idx,
                "group": slice_run.group}}
        if result.exit_code != 0:
            return {"status": "FAILED", "exit_code": result.exit_code,
                    "abort_at": {"arm": slice_run.arm, "repeat_idx": slice_run.repeat_idx}}
    return {"status": "OK"}


def cost_proxy(config: AblationConfig, rows: list[dict]) -> dict:
    """成本代理指标：各臂 prompt 字符数（API 不返回 token usage，如实标注）。"""
    out = {}
    by_id = {str(r.get("case_id")): r for r in rows}
    for arm, schema in ARM_SCHEMA.items():
        total = 0
        for row in by_id.values():
            rendered = render_chart_context(row, schema, as_of_date=config.as_of_date)
            total += len(format_direct_choice_prompt(row, chart_context_text=rendered))
        out[arm] = {"prompt_chars_total": total,
                    "prompt_chars_mean": round(total / max(len(by_id), 1))}
    return {"metric": "prompt_chars_proxy", "note": "API 未返回 token usage；字符数为成本代理", "arms": out}


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, cwd=PROJECT_ROOT).stdout.strip()
    except Exception:
        return "unknown"


def write_report(config: AblationConfig, case_ids: list[str]) -> dict:
    rows = []
    for arm in ARMS:
        runs_dir = config.root / arm / "runs" / config.run_id
        if not runs_dir.exists():
            continue
        for detail in sorted(runs_dir.glob("slice_*/detail.jsonl")):   # 每切片独立目录聚合
            for line in detail.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
    enriched_rows = load_jsonl(config.enriched_path)
    agg = aggregate_delta(rows, config.repeats)
    n_cases = len(case_ids)
    pollution = agg["call_failed"] > n_cases * 0.05
    out_dir = PROJECT_ROOT / "docs" / "phase6" / config.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"run_id": config.run_id, "year": config.year, "status": "OK",
               "as_of_date": config.as_of_date, **agg,
               "pollution_flag": pollution,
               "stage_scheduled": config.stage_scheduled,
               "stage_hard_cap": config.stage_hard_cap}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    manifest = {
        "run_id": config.run_id, "seed": config.seed, "as_of_date": config.as_of_date,
        "profile_id": PROFILE_ID, "template_version": CHART_CONTEXT_TEMPLATE_VERSION,
        "identity_strategy": "passthrough_pseudo_anonymized_dataset",
        "group_split": split_ab_ba(case_ids, config.seed),
        "slice_order": [f"{s.arm}:{s.group}:r{s.repeat_idx}" for s in build_schedule(config, case_ids)],
        "provider": config.provider, "model": config.model,
        "code_hash": _git_head(),
        "enriched_path": str(config.enriched_path),
        "reproducibility_note": "请求不携带 seed；复现依赖 detail 行 raw_answer 与调用顺序",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    proxy = cost_proxy(config, enriched_rows)
    lines = [
        f"# 6A0 上下文消融报告（{config.run_id}，{config.year}）",
        "",
        f"- Δ_dev = {agg['delta_dev_pp']}pp（每 repeat：{agg['per_repeat_delta_pp']}）",
        f"- 判定：**{agg['verdict']}**（≥+2 ADOPT；0≤Δ<+2 ADOPT_FOUNDATION；<0 ROLLBACK）",
        f"- call_failed：{agg['call_failed']}（{n_cases} 题；污染标注：{'是' if pollution else '否'}）",
        f"- 成本代理（prompt 字符数，非 token）：{json.dumps(proxy['arms'], ensure_ascii=False)}",
        "",
        "如实声明：API 未返回 token usage，成本对比为字符数代理；采样不可由 seed 复现。",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 6A0 上下文消融编排器")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--root", type=Path, default=Path(".tmp/phase6"))
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--yes", action="store_true", help="确认预算后发起真实模型调用")
    args = parser.parse_args(argv)

    enriched = args.root / "datasets" / f"baziqa_contest8_{args.year}_holdout_enriched.jsonl"
    config = AblationConfig(run_id=args.run_id, year=args.year, root=args.root,
                            enriched_path=enriched, provider=args.provider, model=args.model)
    failures = offline_gate(config)
    if failures:
        print(json.dumps({"status": "OFFLINE_GATE_FAILED", "failures": failures[:20]},
                         ensure_ascii=False))
        return 1
    case_ids = [str(r["case_id"]) for r in load_jsonl(enriched)]
    schedule = build_schedule(config, case_ids)
    if args.smoke_only:
        schedule = [s for s in schedule if s.purpose == "smoke"]
    total = sum(s.scheduled_calls for s in schedule)
    cap = sum(s.hard_cap for s in schedule)
    print(f"即将发起 {total} 次模型调用（hard_cap {cap}），切片数 {len(schedule)}")
    if not args.yes:
        print("加 --yes 确认预算后执行")
        return 0
    result = run_ablation(config, schedule)   # schedule 已按 --smoke-only 过滤；默认走 run_slice 子进程
    if result["status"] != "OK":
        print(json.dumps(result, ensure_ascii=False))
        return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
    if args.smoke_only:
        print(json.dumps({"status": "SMOKE_OK"}, ensure_ascii=False))
        return 0
    summary = write_report(config, case_ids)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

注意 `run_ablation(config, schedule, slice_runner=None)` 的边界契约：schedule 由**调用方**构建（`main()` 在 `--smoke-only` 时先过滤再传入），函数内不得重建——否则 smoke 过滤失效（阻 1）；`slice_runner` 缺省时内部绑定 config 走 `run_slice` 子进程，测试以 RunnerSpy 替换；阶段预算由 `BudgetLedger`（`config.root/budget/<run_id>.jsonl`）**按 slice_id 幂等记账**（resume 覆盖旧值不重复累计），溢出即 `FAILED/stage budget overflow`（阻 3）。

- [ ] **Step 4：运行确认全绿 + 回归**

```powershell
python -m pytest tests/test_phase6_6a0_ablation.py -q
python -m pytest tests/ -q -m "not e2e"
```

- [ ] **Step 5：提交（精确路径）**

```powershell
git add scripts/run_phase6_6a0_ablation.py tests/test_phase6_6a0_ablation.py
git commit -m "feat(phase6): 6A0 编排器（AB/BA 12 切片 + 离线 gate + Δ 判定 + 报告）"
```

---

## Task 10：真实执行——2024 dev gate（40 题 × 3 repeats，AB/BA）

**前置核对（全部满足才执行）**：Task 1–9 已合入且 `python -m pytest tests/ -q -m "not e2e"` 全绿；`.env` 含 `DEEPSEEK_API_KEY`；Task 3 enrichment 产物与 manifest 在位（覆盖率 40/40 × 4 年度）；工作区干净（`git status`）。

- [ ] **Step 1：离线 gate + smoke canary（20 次调用）**

```powershell
python scripts/run_phase6_6a0_ablation.py --run-id 6a0-2024-001 --year 2024 --smoke-only --yes
```

预期：离线 gate 通过（无 `OFFLINE_GATE_FAILED`）；smoke 切片退出码 0，输出 `"status": "SMOKE_OK"`。任何失败：停下排查，不得直接进全量。

- [ ] **Step 2：全量执行（scheduled 260 / hard_cap 290）**

```powershell
python scripts/run_phase6_6a0_ablation.py --run-id 6a0-2024-001 --year 2024 --yes
```

预期时长约 1–2 小时（260 次调用 ×（模型延迟 + 1s sleep），重试从 30 次储备支出）。中断可直接重跑同一命令（`--resume` 默认开，切片级续跑）。

- [ ] **Step 3：读取结果（由运行生成，禁止伪造）**

产物：`docs/phase6/6a0-2024-001/{report.md, summary.json, manifest.json}`。判读：

- `OFFLINE_GATE_FAILED` / `BLOCKED_INCOMPLETE`：按设计 §10 处理（排查故障源后续跑；BLOCKED_INCOMPLETE 不得进入决策）。
- `verdict = ADOPT`（Δ ≥ +2pp）：approved_v1 成为 6A1 默认上下文。
- `verdict = ADOPT_FOUNDATION`（0 ≤ Δ < +2pp）：默认采用（地基性质），报告中标注。
- `verdict = ROLLBACK`（Δ < 0）：回退记录，**6A1 沿用旧上下文 legacy_v0 继续**（设计 §10 阻塞规则：增强臂失败回退上一稳定基线，不整体停工）。

- [ ] **Step 4：结果归档提交（精确路径）**

```powershell
git add docs/phase6/6a0-2024-001/report.md docs/phase6/6a0-2024-001/summary.json docs/phase6/6a0-2024-001/manifest.json
git commit -m "docs(phase6): 6A0 2024 dev gate 运行结果（verdict=<实际判定>）"
```

---

## 设计 gate 映射表（设计 v6 行号 ↔ 本计划任务 ↔ 验证）

| 设计条目 | 设计 v6 行号 | 计划任务 | 验证方式 |
| --- | --- | --- | --- |
| 已批准字段 schema | L113（§4.2.1） | Task 1/3 | `approved_field_presence` 全量 + 覆盖率 fail-closed |
| denylist（kong_wang/liu_nian） | L114（§4.2.2） | Task 1 | sentinel 值永不渲染测试 |
| 模板逐字节稳定 + 版本 | L115（§4.2.3） | Task 1 | golden 快照 + 跨进程确定性 |
| 泄漏分级扫描 | L116–119（§4.2.4） | Task 2/9 | 单测 + 离线 gate 全量扫描 |
| AB/BA 平衡配对 | L120（§4.2.5） | Task 9 | 13 切片全序列断言（含 cap 分配） |
| 五维 profile + 四命名配置 | L122–144（§4.3） | Task 4/6 | 五维断言 + 端到端路由测试 ×4 |
| (profile, schema) 可见性矩阵 | L145–154 | Task 4/5/6 | required/forbidden 断言 + 串扰检测 |
| attempt key 10 字段 | L158–168（§4.4.1） | Task 6 | 多 stage/arm/repeat 无碰撞测试 |
| resume manifest 字段约束 | L168（§4.4.1） | Task 6 | 首跑创建（17 字段）+ 篡改 8 字段/配置漂移（--temperature）/真实数据变更/manifest 缺失/字段缺失拒绝（均 SystemExit(2)） |
| 终态集合 + 重试账本 | L169–175（§4.4.2） | Task 6/7 | 跨 resume 账本、call_failed 计错 |
| append/resume 禁截断 | L176（§4.4.3） | Task 6 | 任一产物（detail/events/manifest）截断守卫（无 `--overwrite`）+ resume-first 崩溃残留守卫 + 续跑键集合 = 一次性运行 |
| 复现性如实声明 | L177（§4.4.4） | Task 6/9 | `raw_response_path` + manifest note |
| 双列预算 + BLOCKED_INCOMPLETE | L174–175、L303–328（§8） | Task 7 | `compute_hard_cap` 8 组设计值 + 退出码 3 |
| 阶段账本幂等 + fail-closed | L303–328（§8）、§4.4 | Task 9 | smoke/全量幂等 2 测试 + 损坏/超 cap/原子写 3 测试 |
| MingLi 数据前置 | L96–103（§3.2） | Task 5 | fetcher（钉死 commit）+ 退出码 4 |
| MingLi 四层可见性 | L154 | Task 5 | 归一化单测 + 真实样例可见性 + golden prompt |
| trimmed mean | L185（§4.5） | Task 8 | 已知值/边界单测 + 报告附列 |
| 6A0 离线 gate | L190（§4.6） | Task 9 | `offline_gate` 通过/泄漏检出测试 |
| 6A0 dev gate Δ 判定 | L191–194（§4.6） | Task 9/10 | `aggregate_delta`/`gate_verdict` 边界测试 + 真实运行 |
| 6A0 预算 260/290 | L195、L318（§8） | Task 9 | cap 和 = 290 断言 |
| as_of_date / SHA-256 / 密封 2023 | L89–94（§3.1） | Task 3 | manifest 字段 + 2023 拒绝测试 |
| 报告：token/成本对比、call_failed 污染标注 | L120、L367（§12.6） | Task 9 | report.md 字段（字符数代理如实标注） |

## 后续阶段触发条件（本计划范围外，仅登记）

| 触发 | 条件 | 动作 |
| --- | --- | --- |
| 6A1 计划编写 | 6A0 dev gate 完成（ADOPT / ADOPT_FOUNDATION / ROLLBACK 任一，ROLLBACK 则 6A1 用 legacy_v0）；设施离线 gate 全过 | 按设计 §5 另写 6A1 计划（`strict_majority()`、多样性试测、temp-0 锚定臂）；禁止在本计划提前实现 |
| 6B1 计划编写 | 6A1 gate 完成（PROMOTE 与否均可，protocol 按 6A1 结论） | 按设计 §6 另写 6B1 计划 |
| MingLi 线 | Task 5 fetch 前置 BLOCKED | MingLi 全部 gate 记 BLOCKED 并写明原因；BaziQA 线不受影响（设计 §3.2/§10） |
| 2023 | 任何情况下不在 6A0 打开 | enrichment 需显式 `--include-2023` 且只生成输入侧（Task 3 已强制） |

## 执行纪律（执行代理必读）

1. **TDD**：每任务先写失败测试并运行确认失败，再实现；不回改测试迁就实现——测试错了先停下来对齐计划。
2. **git 纪律**：每任务 `git add` 只列该任务精确路径；禁止 `git add -A`、`git add tests/`、`git add .`。
3. **回归**：每任务提交前跑 `python -m pytest tests/ -q -m "not e2e"` 全绿；合并前（Task 10 后）跑全量 `python -m pytest tests/ -q`。
4. **不伪造运行结果**：`docs/phase6/<run_id>/` 与 `.tmp/phase6/**` 由真实运行生成；实现阶段只写代码与测试。
5. **设计缺口处理**：神煞"批准子集"未枚举、MingLi 官方截尾比例未核实、`si_hua` 结构未定——按计划内决策记录呈现，不发明、不静默放宽。
6. **状态纪律**：本计划已为 **APPROVED**（v7，第七轮评审 CONDITIONAL_APPROVAL 的唯一附带项已补齐并经评审授权直接批准），允许进入 Task 1 执行；执行中偏离计划的每一处都要在任务提交的 commit 信息中说明理由。
7. **密钥纪律**：`DEEPSEEK_API_KEY` 只读 `.env`；日志/报告/manifest 中不得出现密钥。
