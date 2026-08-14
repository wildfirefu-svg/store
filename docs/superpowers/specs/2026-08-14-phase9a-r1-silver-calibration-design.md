# Phase 9A-R1 设计：silver relevance 标签校准（零 API）

**日期：** 2026-08-14
**状态：** v1.2（NEEDS_REVISION 二轮修订：effective_disagreement 门、确定性抽样算法、归因证据状态明确）
**前置：** Phase 9A 已冻结（QC_FAIL 终态，分歧 53.73% > 10%；manifest_v4 sealed；reconcile exit 0）
**范围冻结：** 只改 silver judge 的标签边界；**retriever、ranking、truncation、query 集、strategy_outputs 全部不变**；零 LLM API；不评价答案准确率。

**关键约束（P0 修订）**：Phase 9A 的 673 个 judgment pair 只覆盖 37 个 item（冻结分母 112 个中的 75 个零候选）。在 retriever/query/strategy_outputs 不变的前提下，judgeable_item_rate 理论上限 = 37/112 = **33.04%**，远低于 READY 门 90%。因此 **R1 终态不是 SILVER_RETRIEVAL_READY，而是 SILVER_LABEL_CALIBRATED / SILVER_LABEL_NOT_CALIBRATED**——只验证标签规则校准是否有效；检索 READY 需另立 R2 解决候选覆盖。

**归因证据状态（P0 修订）**：归因脚本与 36 条完整结果**当前未入库**（`.tmp/phase9a_r1_attribution.py` 为临时脚本，非版本化证据）。实施阶段 Task 1 将生成正式 `docs/phase9a/r1/attribution.py` + `attribution.json` 并冻结 SHA。

---

## 1. 归因结论（零 API，临时结果待 Task 1 正式冻结）

对 Phase 9A 的 36 条 QC 分歧做归因分析（`.tmp/phase9a_r1_attribution.py`）：

| 分歧方向 | 数量 | 占比 |
|---|---|---|
| partially_relevant → relevant | 31 | 86.1% |
| partially_relevant → irrelevant | 4 | 11.1% |
| irrelevant → partially_relevant | 1 | 2.8% |

**关键发现**：
- 31/31 分歧的 reason 均为 `syn=True cat_match=False`
- 其中 **26/31 的 query 无 category 参数**（silver 规则在 query 无 category 时强制 `cat_ok=False` → 降级 partial）
- 人工判断认为：同义词命中即足够（cat_match 的"一致性"要求过严，query 无 category 时不应降级）

**边界失准点**：`label_pair` 的 `cat_ok = bool(query_category) and str(doc.get("category") or "") == str(query_category)`——query 无 category 参数时 `bool(query_category)=False` → `cat_ok=False` → 强制降级 partial。但人工复核认为这些条文与 item 直接相关。

**结论**：当前失败更像**标签边界失准**（silver 将直接相关条文降成"部分相关"），不能据此判断检索器无效。

---

## 2. 校准目标与验收口径

**目标**：校准 silver 标签边界，使独立验证集上人工 QC 分歧率 ≤10%，证明标签规则修复有效。

| 编号 | 目标 | 验收口径 |
|---|---|---|
| R1-G1 | 标签边界校准规则冻结 | 新 RULE_SOURCE 在查看验证标签前冻结（SHA 落盘）；规则只改 cat_ok 边界，不改 syn_hit |
| R1-G2 | 独立验证集分层抽取 | 从剩余 606 条（673 - 67 开发校准集）中重新分层抽取；seed/算法/比例冻结；与开发校准集无重叠 |
| R1-G3 | 验证集 QC 分歧率 ≤10% | 人工复核验证集；分歧率 ≤10% 才允许判定校准有效 |
| R1-G4 | 校准后 judgment 生成 | 用校准后规则重新生成全部 673 条 judgment + summary；冻结 |
| R1-G5 | 产物与指纹 | 校准后 judgment/summary 产物冻结；**calibration_fingerprint.json**（新增，非 treatment fingerprint）；原 treatment_fingerprint 字节不变断言 |

**本阶段不评价**：答案准确率、模型行为变化、检索召回/噪声（R2 阶段）、任何增强效果声明。

---

## 3. 校准规则（冻结前草案）

**当前规则（v2，Phase 9A 冻结）**：
```python
cat_ok = bool(query_category) and str(doc.get("category") or "") == str(query_category)
if syn_hit and cat_ok:
    label = "relevant"
elif syn_hit:
    label = "partially_relevant"
else:
    label = "irrelevant"
```

**校准规则（v3，草案）**：
```python
# 边界修订：query 无 category 参数时，cat_ok 不参与判定（同义词命中即 relevant）
if query_category is None or query_category == "":
    cat_ok = True  # 无 category 约束时，不降级
else:
    cat_ok = str(doc.get("category") or "") == str(query_category)
if syn_hit and cat_ok:
    label = "relevant"
elif syn_hit:
    label = "partially_relevant"
else:
    label = "irrelevant"
```

**变更点**：仅当 query 有 category 参数时才校验 cat_match；query 无 category 时 `cat_ok=True`（不降级）。

**预期影响**：31 条 `partially_relevant → relevant` 分歧中，26 条（query 无 category）将转为 relevant；剩余 5 条（query 有 category 但 doc category 不匹配）保持 partial（需人工复核确认）。

**冻结纪律**：新 RULE_SOURCE 必须在查看验证标签前冻结（SHA 落盘）；校准后 judgment 重新生成并冻结。

---

## 4. 验证集抽取（独立分层，口径冻结）

**开发校准集**：Phase 9A 的 67 条（已人工复核，用于校准规则设计）。

**独立验证集**（从剩余 606 条中分层抽取，口径全部冻结）：
- **sample_size = 61**（精确值，必须精确抽取 61 条，不允许"实际可抽取数"降级）
- **seed = 20260814**（新 seed，不同于开发校准集的 20260813）
- **最大允许分歧数 = floor(61 × 0.10) = 6**（离散阈值，非百分比）
- **uncertain 计数（P0 修订）**：**effective_disagreement = disagreement_count + uncertain_count**（uncertain 计入失败预算，防全 uncertain 绕过门禁）；SILVER_LABEL_CALIBRATED 当且仅当 effective_disagreement ≤ 6
- **分层维度**：item_id；**必须覆盖全部 37 个 item**（冻结数据实算：剩余 606 pair 覆盖全部 37 item，每 item 至少 1 条剩余 pair，零候选 item = 0）
- **无重叠**：验证集与开发校准集无交集（按 (item_id, canonical_key) 排除）
- **reviewer 盲法**：reviewer 不得看到 silver label、开发集标签、归因结论；只提供条文文本 + item 描述
- **fail-closed**：任一 item 无候选或总候选不足 61 → `BLOCKED_INPUT_DRIFT`（不允许继续判定）

**抽样算法（P0 修订，确定性无放回，函数级冻结）**：
```python
def pair_key(row):
    return (row["item_id"], row["canonical_key"])

rng = random.Random(20260814)
first = [rng.choice(sorted(pairs_by_item[item_id], key=pair_key)) for item_id in sorted(pairs_by_item)]
selected_keys = {pair_key(row) for row in first}
remaining = sorted(
    (row for row in all_remaining_pairs if pair_key(row) not in selected_keys),
    key=pair_key,
)
extra = rng.sample(remaining, 24)
sample = first + extra
# 断言：len(sample) == 61；len({row["item_id"] for row in sample}) == 37；sample ∩ development_set == ∅；len({pair_key(row) for row in sample}) == 61
```

**冻结**：验证集样本列表在 silver 校准规则与任何 v3 label 生成前冻结（SHA 落盘；P0 修订：与执行顺序统一——样本先冻结，规则后冻结）。

---

## 5. 执行顺序（冻结）

1. **归因冻结**：归因脚本 + 36 条分歧完整结果入库（`docs/phase9a/r1/attribution.py` + `attribution.json`，SHA 落盘；**当前未入库，实施阶段生成**）。
2. **验证集样本冻结**：从 Phase 9A sealed 的原始 606 pair 生成并冻结 `qc_sample_list_v2.json`（**在生成或查看任何 v3 label 前**，P0 修订：消除选择偏差）。
3. **校准规则冻结**：新 RULE_SOURCE（v3）冻结（SHA 落盘）；`silver_judge_v3.py`（版本化新文件，非修改 sealed 的 silver_judge.py）冻结。
4. **校准 judgment 生成**：用新规则重新生成 `silver_relevance_judgment_v3.jsonl`（全部 673 条）+ `silver_judgment_summary_v3.json`；冻结。
5. **人工 QC 复核**：验证集人工复核（盲法）。
6. **终态判定**：SILVER_LABEL_CALIBRATED（effective_disagreement ≤6）或 SILVER_LABEL_NOT_CALIBRATED（>6）；**无论是否超过 6，都继续发布对应终态与证据**（P0 修订：失败分支完整封存）。
7. **产物封存**：校准后 judgment/summary/验证集/指纹冻结；manifest_v5 封存。

---

## 6. 产物与指纹（版本化，非覆盖 sealed）

**主冻结产物**（全部版本化新文件，不修改 Phase 9A sealed 产物）：
- `silver_judge_v3.py`（v3 规则，新 SHA）
- `silver_relevance_judgment_v3.jsonl`（校准后，新 SHA）
- `silver_judgment_summary_v3.json`（校准后，新 SHA）
- `qc_sample_list_v2.json`（验证集，新 SHA）
- `qc_human_review_v2.jsonl`（验证集人工复核，新 SHA）
- `qc_result_v2.json`（验证集分歧判定，新 SHA）
- `calibration_fingerprint.json`（新增：silver_judge_v3_py + judgment_v3 + summary_v3 + 验证集 + 归因证据的 SHA）
- `manifest_v5.json`（校准后封存）

**treatment_fingerprint 不变**：retriever/query/strategy_outputs 全部不变，原 treatment_fingerprint.json 字节不变（断言）。

**replay 证据**：
- ~~`retrieval_bundle_dev_v3.jsonl`~~（**已删除**：R1 只验证标签规则，retriever/候选/排序不变，bundle 属 R2 阶段）

---

## 7. 明确不做（冻结边界）

- 不改 retriever、ranking、truncation、query 集、strategy_outputs（全部保持 Phase 9A 冻结状态）。
- 不评价答案准确率；不在 44 道已知婚姻题上宣称提升。
- 不混入大运/流年注入、prompt 改写；不重启 C1。
- 密封集数据不进入本任务；curator 数据位置只提供给独立受限 curator 任务。
- **不用开发校准集（67 条）验证校准规则**（过拟合风险）；必须用独立验证集。

---

## 8. 终态与完成定义

**终态（两种都允许 Phase 9A-R1 完成）**：

- `SILVER_LABEL_CALIBRATED`：验证集 **effective_disagreement ≤ 6**（disagreement_count + uncertain_count），校准规则有效。
- `SILVER_LABEL_NOT_CALIBRATED`：验证集 effective_disagreement >6——保留完整评估结果与失败原因，不得为过门修改规则或 judgment。

**完成定义**：
1. 归因结论冻结（归因脚本 + 36 条分歧完整结果入库，SHA 落盘）。
2. 校准规则（v3）在查看验证标签前冻结。
3. 独立验证集分层抽取并冻结（61 条，seed=20260814，确定性无放回算法，与开发校准集无重叠，37 个 item 目标覆盖）。
4. 验证集人工 QC **effective_disagreement ≤6**（CALIBRATED）或 >6（NOT_CALIBRATED）。
5. 校准后 judgment/summary 生成并冻结（版本化新文件）。
6. 终态为 SILVER_LABEL_CALIBRATED 或 SILVER_LABEL_NOT_CALIBRATED 之一，结论闭合。
7. 全程零 API、零生产代码改动。

**后续衔接**：
- **R2**（候选覆盖）：若 R1 校准有效，另立 R2 解决 75 个零候选 item 的覆盖问题（需改 retriever/query/strategy_outputs，超出本阶段范围）。
- **Phase 9B**：待 R1 + R2 均完成且密封婚姻集就绪后，才进入配对实验 spec。

---

## 附录 A：归因数据（36 条分歧完整表）

归因脚本：`.tmp/phase9a_r1_attribution.py`（零 API，可复算）。

**分歧分布**：
- partially_relevant → relevant：31 条（86.1%）
  - reason 全部为 `syn=True cat_match=False`
  - 其中 query 无 category 参数：26 条
  - 其中 query 有 category 但 doc category 不匹配：5 条
- partially_relevant → irrelevant：4 条（11.1%）
  - 全部为 classic 条文，人工判断为"文本含词但语义无关"
- irrelevant → partially_relevant：1 条（2.8%）
  - `mingli_ftb_0085#k7 | kb:gejue:hy_002`，人工判断为"提到女性婚姻应期，虽非直接断诀但相关"

**校准规则预期影响**：
- 26 条（query 无 category）→ relevant（边界修订直接覆盖）
- 5 条（query 有 category 但 doc 不匹配）→ 保持 partial（需人工复核确认是否合理）
- 4 条（partial → irrelevant）→ 需人工复核确认是否语义无关
- 1 条（irrelevant → partial）→ 需人工复核确认是否相关
