# Phase 9A-Gold 设计：item-centered 人工 Gold 数据规约（零 API 采集协议）

**日期：** 2026-08-14
**状态：** v1.0（草案，待审核）
**裁决依据：** R1.5 关闭；路线为 **Gold 规约与采集 → Gold 密封 → R2 候选覆盖实验**（选项 2+3 组合）
**前置冻结：** Phase 9A（manifest_v4 sealed，QC_FAIL）+ Phase 9A-R1（manifest_v5 sealed，SILVER_LABEL_NOT_CALIBRATED，25/61）

---

## 1. 背景与动机

Phase 9A-R1 证明：词面 silver 规则（同义词共现 + category 一致性，含 v3 的 cat_ok 边界修订）与人类判断分歧 25/61（41%），且分歧呈双向语义性（误报 6 / 高估 5 / 仍降级 10）。**方向判断**：表层规则已到能力边界，进一步对齐需语义级判定。注意该归因尚未独立冻结（正式 attribution.json 仍是早期 36 条开发集归因），暂不作为封存结论引用。

由此裁决：放弃 R1.5 规则再校准，建立 item-centered 人工 Gold，作为 R2 候选覆盖实验与任何语义判定器的评测基准。

**为什么不能只标 673 条检索并集**：并集只覆盖 37/112 个知识项，剩余 75 项无候选。只标并集只能评估精度，无法评估 R2 要解决的候选召回与 112 项固定分母覆盖率。

---

## 2. 目标与验收口径

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | item-centered Gold 覆盖全部 112 项 | 每个 item_id 恰有一条 Gold 记录（正例锚定 或 no_relevant_document_found 裁决） |
| G2 | 每项 ≥1 条可靠正例 | curator 从冻结 KB/classic 语料选出，附完整来源定位与选择轨迹 |
| G3 | 无正例项双人裁决 | 找不到正例时记录完整检索轨迹，第二人独立复核后裁决 `no_relevant_document_found` |
| G4 | 每项 1–2 条 hard negative | 主题相邻但语义无关（字面撞车类），用于语义判定器评测 |
| G5 | R1 盲评材料只作候选 | 61 条盲评（含 human=relevant 条目）只能作为候选材料，经独立复核后才可并入 Gold，不自动升级 |
| G6 | Gold 冻结后开发者不得修改 | SHA 密封 + manifest 封存 + 禁改守护 |

**本阶段不评价**：答案准确率、检索器对比（属 R2）、任何增强效果声明。

---

## 3. Gold schema（冻结草案）

每个 item 一条记录（`gold_v1.json`，按 item_id 排序）：

```json
{
  "schema_version": "1.0",
  "item_id": "mingli_ftb_0002#k4",
  "case_id": "...",
  "status": "anchored | no_relevant_document_found",
  "positives": [
    {
      "canonical_key": "kb:gejue:hy_006 | classic:knowledge_base/.../all_rules.json:11:qtbj_000_011",
      "evidence_quote": "条文中的关键句（原文摘录，证明相关性）",
      "selection_trace": "curator 检索/浏览轨迹（查询词、路径、候选集大小）",
      "curator": "curator_A",
      "confirmed_by": "curator_B"
    }
  ],
  "hard_negatives": [
    {
      "canonical_key": "...",
      "why_negative": "字面撞车说明（如：含'桃花'但讲流年凶煞，非桃花知识点）",
      "curator": "curator_A"
    }
  ],
  "no_positive_trace": "（仅 status=no_relevant_document_found）完整检索轨迹：尝试的查询词/分类/书目 + 候选审阅范围",
  "adjudication": "（仅 no_relevant_document_found）第二人裁决记录：curator_B + 裁决理由"
}
```

**字段约束**：
- `positives` ≥1 当且仅当 `status=anchored`；`status=no_relevant_document_found` 时 `positives=[]` 且 `no_positive_trace`/`adjudication` 必填
- `hard_negatives` 1–2 条，两种 status 下都必填（hard negative 独立于正例存在性）
- `canonical_key` 必须与 Phase 9A 检索器的 canonical key 定义一致（kb:{table}:{id} / classic:{path}:{line}:{record_id}），且必须能被 `retriever.doc_text()` 解析出非空文本（机器校验）
- `evidence_quote` 必须是 document_text 的真实子串（机器校验，防虚构引用）

---

## 4. 采集协议（curator 工作流）

### 4.1 角色与隔离

- **curator_A（采集者）**：独立完成 112 项正例锚定与 hard negative 选择；**不得查看** silver_relevance_judgment.jsonl / silver_relevance_judgment_v3.jsonl / qc_human_review.jsonl / qc_human_review_v2.jsonl（防标签污染）
- **curator_B（裁决者）**：复核全部 `no_relevant_document_found` 裁决；抽样复核 ≥20% 的正例锚定（确定性抽样，seed 冻结）
- **开发者**：只提供冻结语料与工具（canonical key 校验脚本），不参与标注决策

### 4.2 单项采集流程

1. 读 item 的 required_knowledge（prompt_evidence.required_term + query_specs）
2. 在冻结语料中检索：关键词（term + 同义词表）→ 分类浏览 → 书目定位；记录轨迹
3. 找到候选 → 判断是否直接支持该知识点 → 摘录 evidence_quote → 记为正例
4. 找不到 → 记录完整 no_positive_trace → 提交 curator_B 裁决
5. 从检索候选中挑选 1–2 条 hard negative（优先选字面撞车条目，正是 R1 发现的误报类型）

### 4.3 R1 盲评材料的复用规则

- 61 条盲评中 human=relevant 的 43 条 pair 可生成**候选正例清单**（canonical_key 已在 673 并集内）
- 但每条必须经 curator_B **独立复核**（不看 human_label，只看 item 需求 + 条文）确认后才能写入 Gold
- 未通过复核的条目记入 `gold_r1_candidates_rejected.json`（留痕，不进 Gold）
- 这条路径只加速采集，不降低标准

---

## 5. 冻结与密封

1. **采集期**：Gold 记录增量写入工作文件（不进 manifest）
2. **完成后**：生成 `gold_v1.json`（全量，按 item_id 排序）+ `gold_manifest.json`：
   - 冻结 gold_v1.json（json_canonical）
   - 冻结采集工具代码（canonical key 校验脚本）
   - 冻结上游引用：manifest_v4（KB/classic 语料冻结基线）、item_query_map（112 项定义）
   - stage 机：config_frozen → sealed（Gold 无代码执行阶段，跳过 code_frozen 需 manifest helper 支持或按相邻链处理——实施时确认）
3. **密封后**：gold_v1.json 加入禁改守护（Qoder Hook 禁改数据产物清单）；任何修订必须新建 gold_v2.json
4. **对账入口**：`reconcile_gold.py`（逐项 SHA + canonical key 可解析 + evidence_quote 子串校验 + 112 项完整性）

---

## 6. 与 R2 的衔接（Gold 密封后另立设计）

- **R2 评估对象**：字符检索（现 S1-S5）、BM25、embedding、reranker（对比实验，单一变量）
- **指标**（112 项固定分母）：
  - Recall@K：item 的 Gold 正例出现在 top-K 的比例
  - 112 项覆盖率：至少 1 条正例进入 top-K 的 item 比例（no_relevant_document_found 项计 0 并单独报告数量）
  - bundle 噪声：top-K 中非 Gold（非正例且非 hard negative 标注）条目的处理规则在 R2 设计冻结
- **语义判定器纪律**：任何 LLM/embedding judge 必须先对 Gold 评测（与人工 Gold 的一致率过门）才可用于 R2 辅助评估；**模型判断本身永远不是 Gold，不接入正式检索链**

---

## 7. 明确不做（冻结边界）

- 不做 R1.5（词面规则再校准关闭）
- 不把 LLM/embedding judge 接入正式检索链（只是待测方案）
- 不修改 Phase 9A / R1 任何 sealed 产物
- Gold 不用于 44 道已知婚姻题的准确率声明；效果声明仍以密封集为准
- 密封婚姻集数据不进入 Gold 采集（两套数据角色隔离：Gold=开发评估基准，密封集=最终效果裁决）

---

## 8. 完成定义

1. 本规约通过审核（字段 schema、采集协议、双人裁决、密封方式全部冻结）
2. 112 项全部有 Gold 记录（anchored 或 no_relevant_document_found），正例 ≥1（anchored 项）、hard negative 1–2（全部项）
3. 全部机器校验通过（canonical key 可解析、evidence_quote 子串真实、112 项完整）
4. curator_B 完成全部 no_relevant_document_found 裁决 + ≥20% 正例抽样复核
5. gold_v1.json + gold_manifest.json 密封，reconcile_gold exit 0
6. Gold 加入禁改守护清单
7. 全程零 LLM API（采集是人工 + 本地工具；检索工具只用冻结语料）
