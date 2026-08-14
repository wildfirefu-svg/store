# Phase 9A-R1 设计：silver relevance 标签校准（零 API）

**日期：** 2026-08-14
**状态：** v1.0（草案，待用户过审）
**前置：** Phase 9A 已冻结（QC_FAIL 终态，分歧 53.73% > 10%；manifest_v4 sealed；reconcile exit 0）
**范围冻结：** 只改 silver judge 的标签边界；**retriever、ranking、truncation、query 集、strategy_outputs 全部不变**；零 LLM API；不评价答案准确率。

---

## 1. 归因结论（零 API，已冻结）

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

**目标**：校准 silver 标签边界，使独立验证集上人工 QC 分歧率 ≤10%，然后重新计算召回与噪声。

| 编号 | 目标 | 验收口径 |
|---|---|---|
| R1-G1 | 标签边界校准规则冻结 | 新 RULE_SOURCE 在查看验证标签前冻结（SHA 落盘）；规则只改 cat_ok 边界，不改 syn_hit |
| R1-G2 | 独立验证集分层抽取 | 从剩余 606 条（673 - 67 开发校准集）中重新分层抽取；seed/算法/比例冻结；与开发校准集无重叠 |
| R1-G3 | 验证集 QC 分歧率 ≤10% | 人工复核验证集；分歧率 ≤10% 才允许计算指标 |
| R1-G4 | 重新计算召回与噪声 | 用校准后 judgment 重新计算 weighted_recall/bundle_noise/binary coverage/judgeable_rate；终态 SILVER_RETRIEVAL_READY 或 NOT_READY |
| R1-G5 | 产物与指纹 | 校准后 judgment/summary/eval 产物冻结；treatment_fingerprint 更新（新 silver_judge_py SHA） |

**本阶段不评价**：答案准确率、模型行为变化、任何增强效果声明。

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

## 4. 验证集抽取（独立分层）

**开发校准集**：Phase 9A 的 67 条（已人工复核，用于校准规则设计）。

**独立验证集**：从剩余 606 条（673 - 67）中重新分层抽取：
- **分层维度**：item_id（与开发校准集相同的 37 个 item 的剩余 pair）
- **抽样比例**：10%（约 60 条）
- **seed**：新 seed（不同于开发校准集的 20260813，避免过拟合）
- **算法**：与开发校准集相同的分层抽样（每 item floor 分配 + 余数补足）
- **无重叠**：验证集与开发校准集无交集（按 (item_id, canonical_key) 排除）

**冻结**：验证集样本列表在 silver 校准规则冻结后、查看验证标签前生成并冻结（SHA 落盘）。

---

## 5. 执行顺序（冻结）

1. **归因冻结**：本设计 §1 的归因结论落盘（36 条分歧的完整归因表）。
2. **校准规则冻结**：新 RULE_SOURCE（v3）冻结（SHA 落盘）；silver_judge.py 修改后重冻结。
3. **校准 judgment 生成**：用新规则重新生成 silver_relevance_judgment.jsonl（全部 673 条）+ summary；冻结。
4. **验证集抽取**：从剩余 606 条分层抽取 ~60 条；冻结样本列表。
5. **人工 QC 复核**：验证集人工复核（分歧率 ≤10% 才继续）。
6. **指标重算**：用校准后 judgment 重新计算 weighted_recall/bundle_noise/binary coverage/judgeable_rate。
7. **终态判定**：SILVER_RETRIEVAL_READY（分歧 ≤10% 且指标过门）或 SILVER_RETRIEVAL_NOT_READY。
8. **产物封存**：校准后 judgment/summary/eval/指纹冻结；manifest_v5 封存。

---

## 6. 产物与指纹

**主冻结产物**：
- `silver_judge.py`（v3 规则，新 SHA）
- `silver_relevance_judgment.jsonl`（校准后，新 SHA）
- `silver_judgment_summary.json`（校准后，新 SHA）
- `qc_sample_list_v2.json`（验证集，新 SHA）
- `qc_human_review_v2.jsonl`（验证集人工复核，新 SHA）
- `qc_result_v2.json`（验证集分歧判定，新 SHA）
- `retrieval_eval_v2.json`（校准后终态，新 SHA）
- `treatment_fingerprint_v2.json`（更新 silver_judge_py SHA）
- `manifest_v5.json`（校准后封存）

**replay 证据**：
- `retrieval_bundle_dev_v2.jsonl`（校准后 bundle，仅供复现）

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

- `SILVER_RETRIEVAL_READY`：验证集 QC 分歧率 ≤10%，且校准后指标过门（judgeable_item_rate ≥90%、macro weighted_recall ≥90%、macro bundle_noise ≤20%、binary item coverage ≥90%）。
- `SILVER_RETRIEVAL_NOT_READY`：验证集分歧率 >10% 或指标未过门——保留完整评估结果与失败原因，不得为过门修改规则或 judgment。

**完成定义**：
1. 归因结论冻结（36 条分歧完整归因表）。
2. 校准规则（v3）在查看验证标签前冻结。
3. 独立验证集分层抽取并冻结（与开发校准集无重叠）。
4. 验证集人工 QC 分歧率 ≤10%（QC_PASS）或 >10%（QC_FAIL）。
5. 校准后指标重算（QC_PASS 时）或 not_computed（QC_FAIL 时）。
6. 终态为 SILVER_RETRIEVAL_READY 或 SILVER_RETRIEVAL_NOT_READY 之一，结论闭合。
7. 全程零 API、零生产代码改动。

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
