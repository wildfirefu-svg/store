# Phase 6 6A1 严格投票实施计划 — 审核报告（两轮合并）

> 本文档由两轮审核合并而成：第一轮（Kimi，2026-07-18）结论"有条件批准（1 阻断 + 3 中优）"；
> 第二轮（外部审核，同日）结论"NEEDS_REVISION（4 阻断 + 3 高优）"。
> 两轮交集项已合并去重；第二轮的全部断言经 Kimi 逐条源码复核确认成立（见下文核验记录）。
> **合并后最终结论：NEEDS_REVISION——5 个阻断 + 4 个高优/完整性问题，修订后复审。**

---

## 第一轮审核（Kimi）结论摘要

- **B1（阻断）**：`run_model_benchmark:677-678` 校验段 `{"majority"}` 集合未随 argparse 扩展，emit_samples 必被旧检查拒绝。→ 第二轮未列出但仍有效，**合并保留为阻断 #5**。
- **M1（中优）**：编排器文件名 `run_phase6_6a1_vote.py` vs `run_phase6_6a1_ablation.py` 不一致。→ 与第二轮高优 #7(a) 重复，合并。
- **M2（中优）**：`strict_rows_complete` 漏检锚定行整体缺失。→ 被第二轮阻断 #2 完全覆盖（更系统性），合并。
- ~~M3（中优）~~：`strict_majority` typing 导入未交代。→ **撤销**：第二轮确认 `from typing import ... Optional, Sequence ...` 已存在于 `benchmark/runners/self_consistency.py:3`。

---

## 第二轮审核（外部）结论与 Kimi 复核记录

### 阻断 1：审计索引复算逻辑不适用于 vote5 —— **成立（接受）**

- 审核断言：`recompute_accuracy()` 按每条 detail 直接统计 `correct`，vote5_samples 每题 5 行 → 复算得到"单样本准确率"而非严格 ≥3/5 题级准确率；计划测试每题仅 1 行，掩盖了问题。
- Kimi 复核：`scripts/build_phase6_audit_index.py:72-92` 确为按行统计（`correct = sum(1 for r in sel if r.get("correct"))`，按 arm×repeat 过滤，无题级聚合）。
- 处置：审计工具新增 `recompute_vote_accuracy()`（按 (case,repeat) 聚合 5 样本 strict_majority，派生 vote5/single@T/anchor 三臂准确率、Δ1/Δ2、unresolved、四格表）；测试改用每题 5 样本的真实行形。

### 阻断 2：完整性检查可能静默缩小统计分母 —— **成立（接受，覆盖第一轮 M2）**

- 审核断言：`strict_rows_complete()` 只检查已出现的 key——(case,repeat) 采样臂整体缺失、anchor 整体缺失、整题缺失、sample_idx 重复行（set 掩盖）、多出 repeat/case/未知 arm 均不可可靠拦截。
- Kimi 复核：属实（计划 :868-882 的 set 推导对重复行与缺失键均不可见；`aggregate_metrics` 的 `next()` 会裸抛 StopIteration）。
- 处置：签名改 `strict_rows_complete(rows, expected_case_ids, repeats)`——精确唯一 attempt 数（600 采样 + 120 锚定）、无重复、无额外 case/repeat/arm、每个预期 key 存在且终态合法；完整性不过返回 BLOCKED_INCOMPLETE，不得产出 verdict。补 7 条异常场景测试。

### 阻断 3：CLI 没有封死年份 + 温度人工转录 —— **成立（接受）**

- 审核断言：`--year` 任意值可过，且数据读取在校验之前；`--year 2022/2023`、`--year 2024 --recheck`、`--year 2021`（非 recheck）四种错误组合均可运行，违反预注册约束；2021 温度不应人工抄写。
- Kimi 复核：设计 §5.3（:222）确认"复核预注册仅 2021，2022 不参与 6A1，2023 唯一最终集（:289-296 密封）"；计划 main() 确实先读 enriched 再无任何年份校验。
- 处置：CLI 在读取数据前强制——非 recheck 仅 2024、recheck 仅 2021、其余 exit 2；四种错误组合测试。复核温度改 `--dev-run-id`，从归档 dev manifest/summary 自动读取并核验（verdict=PROMOTE_CANDIDATE、profile/schema/provider/model 一致、manifest SHA-256 记录）。

### 阻断 4：多样性试测把 invalid 当第二选项 —— **成立（接受）**

- 审核断言：`predicted_answer` 直接入集合，`["A","A","A","A",None]` 被误判为 2 个不同结果，可能错误触发/阻止 T 切换。
- Kimi 复核：属实（计划 :742 `per_case.setdefault(...).add(r.get("predicted_answer"))`，不过滤终态与合法性）。
- 处置：`diversity_rate()` 仅统计 `terminal_state=="parsed"` 且答案 ∈ A/B/C/D；新增 `probe_rows_complete()`（恰好 10 题 × 每题 {0..4} 唯一 sample_idx，重复/缺题/缺样本即不完整）；probe 不完整 → BLOCKED，不得计算比例。补 invalid/缺行/重复/不足 10 题测试。

### 高优 5：报告未落地设计承诺的全部首类指标 —— **成立（接受）**

- 审核断言：设计要求成本比、trimmed mean、逐题明细、调用顺序与原始响应路径；`write_report()` 缺成本指标（`cost_proxy` 导入未用）。
- Kimi 复核：属实（计划 :749 import cost_proxy 后全文未调用；report.md 无成本/trimmed/逐题明细字段）。`benchmark.reports.accuracy_stats.trimmed_mean` 存在（:35）可复用。
- 处置：`write_report()` 补——`cost_ratio_vote5_vs_single_t` / `cost_ratio_vote5_vs_anchor`（prompt 字符 × 调用数代理，如实标注）、per-case trimmed mean、`case_details.jsonl`（每题每 repeat 的 5 票/vote5/single@T/anchor/correct/unresolved）、manifest 增加切片执行顺序、case 分组哈希、scheduled/attempted/cap 对账；补字段级测试。

### 高优 6：`attempt_stage` 必须进入 resume manifest —— **成立（接受，反转计划 §1 决策 7）**

- 审核断言：`--attempt-stage` 是新增调用者可控的结果定义参数；runner API 不强制 arm-stage 映射，同目录同 arm 先 main 后 anchor 续跑可过 manifest 校验并混合 stage。
- Kimi 复核：`RESUME_MANIFEST_FIELDS`（run_benchmark.py:121-126）确无 attempt_stage；`check_resume_manifest`（:203 起）按字段逐一比对，加入字段后旧 manifest 缺字段自然 fail-closed（SystemExit 2），行为合理。
- 处置：计划 §1 决策 7 正式反转——`attempt_stage` 加入 `RESUME_MANIFEST_FIELDS` 与 `build_resume_manifest`；测试 stage 变更后 resume 被拒。

### 高优 7：验收命令与文件命名不完整 —— **成立（接受，含第一轮 M1）**

- (a) 文件名不一致 → 统一 `run_phase6_6a1_ablation.py`（合并第一轮 M1）；
- (b) `.tmp/g{1..4}.txt` 四组回归未定义 → 计划执行纪律 #3 给出四条确切命令；
- (c) `build_main_schedule()` 只验数量不验唯一 → 增加 40 个唯一 case_id 断言。

---

## 合并判定汇总

| 类别 | 数量 | 内容 |
|---|---|---|
| 阻断 | 5 | #1 审计 vote 复算；#2 完整性检查重构；#3 年份封死 + dev-run-id；#4 diversity 仅合法选项；#5（第一轮 B1）校验段 aggregate 集合扩展 |
| 高优 | 4 | #5 报告首类指标；#6 attempt_stage 入 manifest；#7a 文件名统一；#7b/c 四组回归定义 + case 唯一性 |
| 已确认无问题 | 40+ 项 | 见第一轮报告第四节；第二轮另确认 typing import 具备、`_HardCapExhausted` 非 RuntimeError、预算算术、AB/BA 顺序 |

**修订要求**：计划 v2 须覆盖全部 5+4 项；修订后复审通过方可进入实施。
