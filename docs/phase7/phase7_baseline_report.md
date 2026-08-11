# Phase 7 基线报告：MingLi-Bench 完整 160 题冻结测量

**日期：** 2026-08-11
**run_id：** `phase7-mingli-v4flash-nt-20260811-r2`
**设计：** `docs/superpowers/specs/2026-08-10-phase7-mingli-bench-baseline-design.md`（v2.3，commit `15dd63f`）
**计划：** `docs/superpowers/plans/2026-08-10-phase7-mingli-bench-baseline.md`（v3.1，commit `1a66e06`）
**归档：** `docs/phase7/phase7-mingli-v4flash-nt-20260811-r2/`（receipt + audit_index + merged_details + run context/manifest，SHA 链完整）
**一句话结论：冻结推理配置（DeepSeek-V4-Flash non-thinking，T=0，单次调用）在 MingLi-Bench 完整 160 题上的首跑 exact-match micro accuracy = 53/160 = 33.13%（Wilson 95% [26.30%, 40.74%]），与 BaziQA holdout 同模型同推理配置结果（28.75%）处于同一量级。**

---

## 1. 测量配置（全部经 receipt/manifest 核验）

| 维度 | 值 |
|---|---|
| provider / model | `deepseek` / `deepseek-v4-flash`（response_model 逐行核验 160/160 一致，缺失 0） |
| thinking_mode / temperature | `disabled` / `0.0`（成功调用逐行核验） |
| prompt | MingLi 官方 CoT（`mingli_official_cot_astro`；`OFFICIAL_SYSTEM_PROMPT` 真实进入 payload，Task 4 起生效） |
| chart 注入 | 官方预计算 `fortune_api_results.json`（`--astro`，32/32 盘命中） |
| RAG / few-shot / APB / shuffle | 全 false（env 净化 + manifest 四 false） |
| 数据 | pinned commit `b7433280fd86d7a7c27debbc47d0303c218f0bfd`；data.json / fortune SHA 与冻结值一致 |
| 预算 | scheduled=160 / hard_cap=180；实际 `call_attempt` = **160**（零重试、零截断、零复测） |

## 2. 主指标（首跑口径，分母固定 160）

| 指标 | 值 |
|---|---|
| **首跑 exact-match micro accuracy** | **53/160 = 33.13%** |
| Wilson 95% 区间 | [26.30%, 40.74%] |
| 命盘级 macro accuracy（32 盘等权） | 33.02% |
| 32 命盘聚类 bootstrap 95%（B=10000，seed=42） | [25.00%, 41.25%] |

parser 终态分布：`parsed 160 / invalid 0 / call_failed 0`（parser_rate = 1.0）。160 题不是独立样本（32 盘 × 4–6 题），区间估计以聚类 bootstrap 为准。

## 3. 分类别准确率

按年份：

| 年份 | 准确率 |
|---|---|
| 2022 | 16/40 = 40.0% |
| 2023 | 15/40 = 37.5% |
| 2024 | 10/40 = 25.0% |
| 2025 | 12/40 = 30.0% |

按 12 类别：

| 类别 | 准确率 | 类别 | 准确率 |
|---|---|---|---|
| 家庭 | 10/22 = 45.5% | 财运 | 8/13 = 61.5% |
| 性格 | 7/14 = 50.0% | 事业 | 6/25 = 24.0% |
| 健康 | 7/17 = 41.2% | 婚姻 | 6/44 = 13.6% |
| 子女 | 3/6 = 50.0% | 学业 | 3/11 = 27.3% |
| 灾劫 | 2/2 = 100% | 运势 | 1/2 = 50.0% |
| 外貌 | 0/3 = 0% | 官非 | 0/1 = 0% |

按 32 命盘（`chart_case_id`，格式 对/题数）：case_1 1/5、case_2 3/5、case_3 2/5、case_4 2/5、case_5 3/5、case_6 0/5、case_7 1/5、case_8 4/5、case_9 3/5、case_10 2/5、case_11 1/5、case_12 1/5、case_13 2/5、case_14 2/5、case_15 1/5、case_16 3/5、case_17 0/5、case_18 3/5、case_19 1/6、case_20 0/4、case_21 1/5、case_22 2/5、case_23 3/5、case_24 0/5、case_25 1/5、case_26 2/5、case_27 0/5、case_28 3/5、case_29 3/5、case_30 0/5、case_31 0/5、case_32 3/5。7 盘全错、1 盘 4/5，盘间方差显著，印证聚类区间的必要性。

## 4. smoke 与受控复测

- **smoke（前 10 题首跑）**：`smoke_verdict.passed=True`（冻结于 run context/audit index）——terminal detail 恰 10、call_failed=0、gate_blocked=0、parsed 10/10、逐 attempt key 对账一致。判定以冻结的 `smoke_verdict` 为准。
- **受控复测**：eligible 集为空（main 终态无 invalid/call_failed），`scheduled_calls=0`，未发生复测；三类清单（retested / unselected_eligible / selected_not_executed）均为空，见 audit index `retest_report`。

## 5. 完整性硬门与证据链

十二条硬门 **全部通过，verdict=COMPLETE**（160 终态 / 160 唯一题目 ID / 每题恰 1 终态 / 32 命盘分布 30×5+case_19×6+case_20×4 / 终态枚举合法 / 分母 160 / 无复测越权 / call_attempt 160≤180 / merged SHA 一致 / thinking_mode 逐行 disabled / response_model 逐行一致 / chart_case_id join 逐行一致）。

SHA 交叉核验（本报告撰写时重算）：merged_details、mingli_data、fortune_api 与 audit index 记录一致。receipt 字段全集见 `phase7_baseline_receipt.json`（`model_label="DeepSeek-V4-Flash non-thinking"`、`completeness_verdict=COMPLETE` 等）。

**r1 说明**：首个 run_id（`...-r1`）在首个模型调用前因 orchestrator 切片目录缺陷中止（零 API 消耗），缺陷修复（`b3e3e2a`）后按 fail-closed 契约不可 resume，本报告全部为 r2 数据。r1 现场保留于 `.tmp` 备查。

## 6. 跨基准对照（显式标注协议差异）

| 基准 | 协议 | 结果 |
|---|---|---|
| **MingLi-Bench 160（本测）** | v4-flash non-thinking T=0 单次 + **MingLi 官方 CoT prompt + 官方 astro 注入** | **33.13%**（53/160，Wilson [26.30, 40.74]，聚类 [25.00, 41.25]） |
| BaziQA 2024 holdout（6B2 r2 归档） | 同模型同推理配置 + `baziqa_xjz_reasoned` prompt（legacy_v0） | 33.33%（40/120，attempt 级 = 40 题 × 3 repeats） |
| BaziQA 2025 holdout（6B2 r2 归档） | 同上 | 24.17%（29/120） |
| BaziQA 两年合并 | 同上 | 28.75%（69/240） |

协议差异（设计 §3.1 诚实声明）：prompt 层不同（官方 CoT vs xjz_reasoned）、题目分布与领域不同、chart 数据来源不同（官方预计算 vs 本仓排盘）、运行时间不同。两组数字**只证明同一冻结推理配置在两个基准上处于同一量级（约 25–33%），不构成严格横向排名**。

与 Phase 1 前 20 题（60%）不作同协议比较：该次为**历史链路 smoke**（`--shuffle-options` + 非官方 profile + 仅 20 题），样本量与协议均不对齐。

## 7. 已知限制与 backlog

- 单次运行、T=0；结果为点估计 + 区间，不含运行间方差（单次调用协议下题级方差主要来自题目采样）。
- 婚姻类 13.6%（6/44）为最大类别且显著低于均值，是后续错误分析的优先对象（本阶段不做任何调优）。
- backlog：`fetch_mingli_bench.py` 改 `git show HEAD:<file>` 字节直取（Windows autocrlf 加固）；`TestCaseSearch`/`TestBaziCaseSearch` 本机 torch 段错误（预存环境问题）。
