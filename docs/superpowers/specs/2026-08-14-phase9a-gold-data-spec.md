# Phase 9A-Gold 设计：item-centered 人工 Gold 数据规约（零 API 采集协议）

**日期：** 2026-08-14
**状态：** v1.1（NEEDS_REVISION 修订：双人确认契约、item 定义冻结、结构化轨迹、无泄漏导出链、完整 stage 机、R2 指标拆分、RECEIPT 发布链）
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
| G1 | item-centered Gold 覆盖全部 112 项 | 每个 item_id 恰有一条 Gold 记录（anchored 或 no_relevant_document_found） |
| G2 | 每项 ≥1 条可靠正例（anchored 项） | curator_A 从冻结语料选出，**curator_B 100% 独立复核确认**，附结构化来源定位与选择轨迹 |
| G3 | 无正例项 100% 双人裁决 | 冻结搜索计划全部执行 + 结构化轨迹 + curator_B 独立复核后裁决 `no_relevant_document_found` |
| G4 | hard negative 1–2 条或结构化终态 | 每项 1–2 条字面撞车条目；确无近似负例时记 `no_hard_negative_found`（结构化理由）；B 抽样 20% 复核且记录 QC 结果 |
| G5 | R1 盲评材料只作候选（无泄漏导出链） | 冻结导出脚本生成候选 packet（无 label/reason/序号），A 不接触，B 独立复核后才可并入 Gold |
| G6 | Gold 冻结后开发者不得修改 | SHA 密封 + manifest 封存 + GOLD_RECEIPT + 禁改守护 |
| G7 | 112 项判定语义完整冻结 | gold_item_definitions.json（含上游路径与 SHA）先于采集冻结 |

**本阶段不评价**：答案准确率、检索器对比（属 R2）、任何增强效果声明。

---

## 3. 角色契约（冻结）

**标注口径**：curator_A 与 curator_B **均为人类**；不允许 AI 初选、AI 生成候选或 AI 代写轨迹/理由（零 LLM API 是本规约硬约束）。

- **curator_A（采集者）**：独立完成 112 项正例选择、hard negative 选择、结构化轨迹记录；**不得查看** silver_relevance_judgment.jsonl / silver_relevance_judgment_v3.jsonl / qc_human_review.jsonl / qc_human_review_v2.jsonl / **R1 候选 packet**（防间接提示）
- **curator_B（复核裁决者）**：**100% 独立复核全部正例**（不看 A 的结论，只看 item 定义 + 条文）；**100% 复核全部 no_relevant_document_found**（含轨迹完整性）；抽样 20% 复核 hard negative（确定性抽样，seed 冻结）；独立复核 R1 候选 packet
- **开发者**：只提供冻结语料与工具（定义导出、候选导出、校验脚本），不参与标注决策

**身份与访问记录**：采集开始前冻结 `gold_roles.json`（curator_A/curator_B 身份标识、分工、盲法约束清单）；采集期维护 `gold_access_log.jsonl`（每次读取语料/候选 packet 的记录：角色、时间、读取对象），密封时一并冻结。盲法检查：reconcile 校验 access log 中 A 无 R1 packet 与任何标签文件的读取记录。

---

## 4. 112 项定义冻结（先于采集）

生成并冻结 `gold_item_definitions.json`（顶层 `{"items": [...]}`，112 元素，按 item_id 排序）：

```json
{
  "schema_version": "1.0",
  "item_id": "mingli_ftb_0002#k4",
  "case_id": "...",
  "required_term": "结婚 | 婚期 | 桃花",
  "query_specs": [ ... ],
  "item_description": "required_term=...; query_terms=...",
  "upstream": {
    "required_knowledge_path": "docs/phase8/marriage-capability/required_knowledge.jsonl",
    "required_knowledge_sha256": "...",
    "knowledge_audit_path": "docs/phase8/marriage-capability/knowledge_audit.jsonl",
    "knowledge_audit_sha256": "..."
  }
}
```

字段来源与 Phase 9A-R1 packet 构造一致（required_term 来自 knowledge_audit 的 prompt_evidence；query_specs 来自 required_knowledge），并记录上游文件路径与 SHA——**112 项判定语义不随上游文件漂移**（上游漂移时 reconcile fail-closed）。

---

## 5. Gold schema（冻结草案）

`gold_v1.json` 顶层结构：`{"schema_version": "1.0", "item_count": 112, "items": [...]}`（对象，非裸数组），items 按 item_id 排序。

```json
{
  "item_id": "mingli_ftb_0002#k4",
  "status": "anchored | no_relevant_document_found",
  "positives": [
    {
      "canonical_key": "kb:gejue:hy_006",
      "evidence_quote": "条文中的关键句（原文摘录，证明相关性）",
      "selection_trace": { "search_steps": [...], "corpus_sections_checked": [...] },
      "curator": "curator_A",
      "confirmed_by": "curator_B",
      "confirmation_note": "B 独立复核结论（必填）"
    }
  ],
  "hard_negatives": [
    {
      "canonical_key": "...",
      "collision_terms": ["桃花"],
      "evidence_quote": "条文中撞车词的上下文摘录",
      "why_negative": "含'桃花'但讲流年凶煞，非桃花知识点",
      "curator": "curator_A",
      "b_reviewed": true,
      "b_review_result": "confirmed | skipped_sampling"
    }
  ],
  "hard_negative_status": "found | no_hard_negative_found",
  "no_positive_evidence": {
    "search_steps": [
      {
        "entrypoint": "search_gejue",
        "args": {},
        "query_terms": ["婚期", "结婚"],
        "filters": {},
        "candidate_count": 0,
        "reviewed_canonical_keys": []
      }
    ],
    "corpus_sections_checked": ["kb:gejue", "kb:xiangyi", "classic:qiongtongbaojian/all_rules.json"],
    "search_plan_sha256": "..."
  },
  "adjudication": {
    "curator": "curator_B",
    "verdict": "no_relevant_document_found",
    "rationale": "复核结论与理由（必填）",
    "trace_complete": true
  }
}
```

**字段约束**：
- `positives` ≥1 当且仅当 `status=anchored`；每条 positive 必须有 `confirmed_by` + `confirmation_note`（100% 双审）
- `status=no_relevant_document_found` 时：`no_positive_evidence.search_plan_sha256` 必须等于冻结搜索计划中该 item 的计划 SHA；`adjudication.trace_complete=true` 且 curator_B 裁决必填
- `hard_negatives` 1–2 条（`hard_negative_status=found`）或空（`hard_negative_status=no_hard_negative_found`，需附结构化理由字段 `no_hard_negative_reason`）
- `canonical_key` 必须能被 `retriever.doc_text()` 解析出非空文本（机器校验）
- `evidence_quote` 必须是 document_text 的真实子串（机器校验，防虚构引用）
- **轨迹为结构化字段**（search_steps/corpus_sections_checked/search_plan_sha256），自由文本仅用于理由说明；机器可验证搜索计划执行覆盖

**搜索计划冻结**：采集前冻结 `gold_search_plans.json`（每 item 一份计划：entrypoint/args/query_terms/filters/必查 corpus sections），SHA 记录；`no_relevant_document_found` 只有在计划全部执行（search_steps 覆盖计划全部条目）且 B 复核后才允许。

---

## 6. R1 候选无泄漏导出链（冻结）

**导出脚本** `export_r1_gold_candidates.py`（独立冻结，code_frozen 阶段）：
- 输入：R1 qc_human_review_v2.jsonl（human=relevant 的 43 条）+ gold_item_definitions.json + 冻结语料
- 输出：`gold_r1_candidates_packet.jsonl`，每行**只含** item 定义（item_id/required_term/item_description）、canonical_key、document_text（完整）、source_location
- **禁止输出**：human_label、silver label、reason、note、原始复核序号、任何可反推标签的字段
- 顺序：脚本冻结 → 生成 packet → 冻结 packet SHA → **之后** B 才可查看
- A 不得接触该 packet（access log 校验）
- B 独立复核（只看 item 定义 + 条文）：通过 → 写入 Gold positives（confirmed_by=B，selection_trace 记 `source: r1_candidate_packet`）；未通过 → `gold_r1_candidates_rejected.json`（留痕，不进 Gold）

---

## 7. 冻结与密封（完整发布链）

**stage 机**（沿用 phase9a_manifest 相邻链，无跳级）：

```text
None → config_frozen → code_frozen → sealed
```

- **config_frozen**：gold_item_definitions.json、gold_roles.json、gold_search_plans.json、上游引用（manifest_v4、required_knowledge/knowledge_audit SHA）
- **code_frozen**：export_r1_gold_candidates.py、gold_validate.py（canonical key/evidence_quote/112 完整性校验）、reconcile_gold.py、gold_r1_candidates_packet.jsonl（冻结输入）
- **sealed**：gold_v1.json、gold_access_log.jsonl、gold_r1_candidates_rejected.json、GOLD_CLOSURE.md

**密封发布链**（沿用 R1 finalize 已验证模式）：

1. 采集完成 → 机器校验全部通过（gold_validate.py）→ 发布 `gold_v1.json` 及审计产物
2. 冻结条目并 `set_stage(sealed)`
3. **最后发布 `GOLD_RECEIPT.json`**：绑定 sealed manifest SHA + 每 artifact 的 sha256/size/strategy + 112 项完整性统计；RECEIPT 不加入 manifest（避免循环）
4. **对账入口 `reconcile_gold.py`**：逐项 SHA + RECEIPT 绑定 + 112 项完整性 + 100% 双审记录校验（每条 positive 有 confirmed_by）+ access log 盲法校验
5. **恢复协议**：sealed 无 RECEIPT → 校验产物 SHA 与 manifest 一致后补发 RECEIPT；其他任何漂移 fail-closed
6. **禁改守护时点**：GOLD_RECEIPT 发布后，gold_v1.json + gold_manifest.json 加入 Qoder Hook 禁改数据产物清单；任何修订必须新建 gold_v2.json

---

## 8. 与 R2 的衔接（Gold 密封后另立设计）

- **R2 评估对象**：字符检索（现 S1-S5）、BM25、embedding、reranker（对比实验，单一变量）
- **指标口径**（P0 修订：拆分，避免无正例项惩罚检索器）：
  - `anchor_recall@K`：仅 anchored 项为分母，Gold 正例出现在 top-K 的加权比例
  - `fixed_112_retrievability`：命中 ≥1 条正例的 item 数 / 112
  - `gold_answerable_rate`：anchored 项数 / 112
  - `no_positive_rate`：无正例项数 / 112
  - **恒等约束**：`fixed_112_retrievability 理论上限 = gold_answerable_rate`（reconcile 校验该关系）
  - bundle 噪声口径（top-K 中非 Gold 标注条目的处理）在 R2 设计冻结
- **门槛纪律**：Gold 冻结前不设置 R2 数值门槛；门槛在 R2 设计中基于 Gold 统计分布冻结
- **语义判定器纪律**：任何 LLM/embedding judge 必须先对 Gold 评测（与人工 Gold 的一致率过门）才可用于 R2 辅助评估；**模型判断本身永远不是 Gold，不接入正式检索链**

---

## 9. 明确不做（冻结边界）

- 不做 R1.5（词面规则再校准关闭）
- 不把 LLM/embedding judge 接入正式检索链（只是待测方案）
- 不允许 AI 参与标注（初选/复核/裁决均为人类，零 LLM API）
- 不修改 Phase 9A / R1 任何 sealed 产物
- Gold 不用于 44 道已知婚姻题的准确率声明；效果声明仍以密封集为准
- 密封婚姻集数据不进入 Gold 采集（两套数据角色隔离：Gold=开发评估基准，密封集=最终效果裁决）

---

## 10. 完成定义

1. 本规约通过审核（schema、角色契约、搜索计划、发布链全部冻结）
2. gold_item_definitions.json（112 项 + 上游 SHA）与 gold_search_plans.json 冻结（config_frozen）
3. 采集完成：112 项全部有 Gold 记录；anchored 项正例 ≥1 且 100% 双审；hard negative 1–2 条或结构化 no_hard_negative_found
4. 机器校验全过：canonical key 可解析、evidence_quote 子串真实、112 项完整、搜索计划执行覆盖、双审记录完整
5. curator_B 完成 100% 正例复核 + 100% no_relevant_document_found 裁决 + 20% hard negative 抽查（QC 结果记录）
6. gold_v1.json + gold_manifest.json sealed + GOLD_RECEIPT.json 发布，reconcile_gold exit 0
7. 禁改守护启用（GOLD_RECEIPT 发布后）
8. 全程零 LLM API；access log 证明盲法（A 无标签/packet 读取记录）
