# Phase 9A-Gold 设计：item-centered 人工 Gold 数据规约（零 API 采集协议）

**日期：** 2026-08-15
**状态：** v1.3（NEEDS_REVISION 三轮修订：混合盲审包、隔离强度诚实分级、候选清单可复算契约、hard-negative 降级防虚假终态）
**裁决依据：** R1.5 关闭；路线为 **Gold 规约与采集 → Gold 密封 → R2 候选覆盖实验**（选项 2+3 组合）
**前置冻结：** Phase 9A（manifest_v4 sealed，QC_FAIL）+ Phase 9A-R1（manifest_v5 sealed，SILVER_LABEL_NOT_CALIBRATED，25/61）

---

## 1. 背景与动机

Phase 9A-R1 证明：词面 silver 规则与人类判断分歧 25/61（41%），分歧呈双向语义性。**方向判断**：表层规则已到能力边界（该归因尚未独立冻结，暂不作为封存结论）。裁决：放弃 R1.5，建立 item-centered 人工 Gold，作为 R2 候选覆盖实验与任何语义判定器的评测基准。

**为什么不能只标 673 条检索并集**：并集只覆盖 37/112 个知识项，剩余 75 项无候选；只标并集无法评估候选召回与 112 项固定分母覆盖率。

---

## 2. 目标、终态与验收口径

**双终态**（不为凑齐 112 项强行裁决）：

- `GOLD_READY`：112 项全部完成裁决（anchored 或 no_relevant_document_found_under_frozen_plan），双审与分歧处理全部闭合
- `GOLD_BLOCKED_ACQUISITION`：存在未闭合项——保留完整过程证据与阻塞原因；**blocked 项的未完成过程记录必须存在于 gold_acquisition_log.jsonl**；两种终态都完整发布证据（RECEIPT artifact 集合相同，见 §8）

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 覆盖全部 112 项 | 每个 item_id 恰有一条裁决完成记录 |
| G2 | 混合盲审 + 分歧裁决 | B 对混合包（proposal + hard negative + decoy，打乱、无类型/身份标记）统一四态打标；分歧→C 裁决或 BLOCKED |
| G3 | 无正例项证据强化 | 冻结搜索计划逐步唯一执行 + 候选清单落盘可复算 + 全量审阅对账 + B 结构化复核 |
| G4 | hard negative 门禁闭合 | 降级 no_hard_negative_found 仅在独立搜索计划完整执行且全候选审阅后允许；否则 BLOCKED_HARD_NEGATIVE_ACQUISITION |
| G5 | 隔离强度诚实分级 | B = packet-only（不暴露语料，强隔离）；A = access_attestation（程序无法证明唯一读取路径，诚实声明） |
| G6 | Gold 冻结后不可修改 | SHA 密封 + manifest + GOLD_RECEIPT + 禁改守护（配置 seal 前冻结，receipt 后激活） |
| G7 | 112 项判定语义冻结 | gold_item_definitions.json（含上游路径与 SHA）先于采集冻结 |

---

## 3. 角色契约与隔离（冻结）

**标注口径**：curator 均为人类；不允许 AI 初选/复核/裁决（零 LLM API 硬约束）。

**前置门**：`gold_roles.json` 必须在采集开始前指定 **A、B 两名互不相同的人类身份**（C 为可选备用）；未指定或身份相同 → `BLOCKED_ROLE_ASSIGNMENT`，采集不得开始。**分歧即决规则**：出现首个 A/B 分歧且 gold_roles.json 未指定 C 时，该 item 立即进入 `BLOCKED_ACQUISITION`，不得等待临时追加第三人后继续依赖裁决（C 只能在采集开始前冻结）。

**角色**：
- **curator_A（提议者）**：正例提议、hard negative 选择、结构化轨迹记录
- **curator_B（盲审者）**：对混合盲审包统一四态打标（不看任何类型/身份标记）；复核全部 no_positive 轨迹（含结构化独立抽查检索）；hard negative 抽查
- **curator_C（裁决者，可选）**：仅当 A/B 分歧时介入；必须在采集开始前冻结于 gold_roles.json
- **开发者**：只提供冻结语料与工具，不参与标注决策

**隔离强度分级**（P0 修订：诚实声明，删除不可证实的强声明）：

1. **B = packet-only 强隔离**：B 的工作目录**只含**混合盲审包（含条文全文）+ gold_item_definitions.json；**不含原始语料、不含 A 的任何产出**。B 的读取面被 packet 内容限定，无需访问语料即可完成盲审
2. **A = access_attestation**：A 需要直接检索原始语料，程序无法证明包装器是唯一读取路径（A 可绕过包装器直接读文件）。因此 A 侧隔离固定为 **access_attestation（访问声明）**：gold_read_access.py 自动记录经包装器的读取，A 签署声明"未绕过包装器读取标签/packet 文件"；**不得声称"遗漏读取可检测"或"A 侧盲法可验证"**
3. **盲法可验证的部分**（reconcile 机器校验）：混合盲审包 SHA 在 B 查看前冻结、B 标签冻结后才解盲、packet 不含类型/身份/理由字段、B 目录清单不含语料与 A 产出、access log 中 B 无语料读取记录
4. GOLD_CLOSURE 必须如实记录两侧隔离等级：`B=packet_only`、`A=access_attestation`

---

## 4. 112 项定义与搜索计划冻结（先于采集）

**gold_item_definitions.json**（顶层 `{"schema_version": "1.0", "items": [...]}`，112 元素，按 item_id 排序）：每项含 item_id/case_id/required_term/query_specs/item_description + 上游 required_knowledge/knowledge_audit 路径与 SHA。上游漂移 → reconcile fail-closed。

**gold_search_plans.json**：每 item 一份搜索计划，每步冻结 `step_id / entrypoint / args / query_terms / filters / corpus_snapshot_sha256`。

**执行契约**（P0 修订：候选清单可复算）：

执行器 `gold_search_exec.py` 将每个步骤的**不可变结果**追加写入 `gold_search_results.jsonl`，每行：

```json
{
  "step_id": "0002k4_s1",
  "item_id": "mingli_ftb_0002#k4",
  "ordered_candidate_keys": ["kb:gejue:hy_002", "kb:gejue:hy_006", "..."],
  "candidate_keys_sha256": "...",
  "candidate_count": 12
}
```

**冻结规则**：
- **key 排序与去重**：ordered_candidate_keys = 检索原始返回按 canonical_key 字典序排序 + 去重（与 Phase 9A sort_key 的 doc_key 分量一致）
- **SHA canonical 规则**：candidate_keys_sha256 = sha256(json.dumps(ordered_candidate_keys, separators=(",", ":")) + "\n")（jsonl_canonical 口径）
- **唯一终态**：每个 step_id 在 gold_search_results.jsonl 中恰有一行；重复执行或缺失 → 该 item BLOCKED
- **审阅对账**：`reviewed_canonical_keys == ordered_candidate_keys`（严格集合相等，机器校验）；漏审 → BLOCKED
- **引用完整性**：`trace_step_refs` 的格式冻结为 `step_id@canonical_key`（非模糊的 step#序号）；reconcile 校验每个引用能在 gold_search_results.jsonl 对应 step_id 的 ordered_candidate_keys 中解析到该 canonical_key（referential integrity）
- **诚实口径**：top-K 未命中不能证明语料无正例；该状态只声明 `no_relevant_document_found_under_frozen_plan`

---

## 5. Gold schema（冻结草案）

`gold_v1.json` 顶层：`{"schema_version": "1.0", "item_count": 112, "acquisition_verdict": "GOLD_READY | GOLD_BLOCKED_ACQUISITION", "items": [...]}`（中优修订：verdict_source 更名 acquisition_verdict），items 按 item_id 排序。**gold_v1.json 只保存裁决完成后的派生结果**；过程记录在 `gold_acquisition_log.jsonl`（密封时一并冻结，含 blocked 项的未完成过程记录）。

```json
{
  "item_id": "mingli_ftb_0002#k4",
  "status": "anchored | no_relevant_document_found_under_frozen_plan | BLOCKED_ACQUISITION | BLOCKED_HARD_NEGATIVE_ACQUISITION",
  "collection_trace_ref": "trace_0002k4",
  "positives": [
    {
      "canonical_key": "kb:gejue:hy_006",
      "evidence_quote": "条文中的关键句（原文摘录）",
      "trace_step_refs": ["0002k4_s1@kb:gejue:hy_006"],
      "resolution": "confirmed | third_party_adjudicated"
    }
  ],
  "hard_negatives": [
    {
      "canonical_key": "...",
      "collision_terms": ["桃花"],
      "evidence_quote": "撞车词的上下文摘录",
      "why_negative": "含'桃花'但讲流年凶煞，非桃花知识点",
      "trace_step_refs": ["0002k4_hn_s1@..."],
      "b_reviewed": false,
      "b_review_result": "not_sampled"
    }
  ],
  "hard_negative_status": "found | no_hard_negative_found",
  "no_positive_evidence": {
    "executed_step_ids": ["0002k4_s1", "0002k4_s2"],
    "search_plan_sha256": "...",
    "plan_fully_executed": true,
    "all_candidates_reviewed": true,
    "b_verification": {
      "curator": "curator_B",
      "verdict": "no_relevant_document_found_under_frozen_plan",
      "verification_step_ids": ["0002k4_bv1"],
      "rationale": "复核结论（必填）"
    }
  },
  "blocked_reason": "（仅 BLOCKED 状态）结构化阻塞原因"
}
```

**item 级轨迹**：每个 item 恰有一份 collection_trace（存于 gold_acquisition_log.jsonl，trace_id = `trace_{item_id}`）；positive/hard negative 只引用 `trace_step_refs`，不携带轨迹副本。

**混合盲审包**（P0 修订：B 的盲审不得泄露 A 结论）：

1. **构成**：A 的全部 positive proposal 条目 + 全部 hard negative 候选条目 + **decoy 条目**（从冻结语料确定性随机抽取、与任何 item 无提议关系的条文，数量冻结为 max(正例数, 负例数) 的 50%，seed=20260815）
2. **字段**：每条仅含 blind_id（重新编号）/ item_id / canonical_key / document_text；**不含** proposal 类型、A 身份、A 理由、来源阶段、collision_terms
3. **打乱与冻结**：确定性打乱（seed=20260815）→ 生成 `gold_blind_review_packet.jsonl` → **冻结 packet SHA（code_frozen）→ 之后 B 才可查看**
4. **B 输出**：对全部条目统一输出 `relevant / partially_relevant / irrelevant / uncertain` + note，写入 `gold_b_labels.jsonl` 并冻结
5. **解盲**：仅在 B 标签冻结后进行（reconcile 校验时间序：packet SHA 冻结 < B 标签冻结 < 解盲映射生成）；解盲映射（blind_id → proposal 类型）由工具生成并留痕
6. **判定语义**：B=relevant 的 proposal 条目 → confirmed 候选；B=partially_relevant/irrelevant/uncertain → 分歧（C 裁决或 BLOCKED）；decoy 条目用于检测 B 的标签基线（decoy 中 relevant 比例异常高 → 记录于 closure 作为盲审质量信号）

**双审分歧流程**：A proposal → B 盲审四态标签（混合包）→ 解盲比对 → B=relevant 则 confirmed；否则分歧 → C 裁决（third_party_adjudicated）或该 item BLOCKED_ACQUISITION。gold_v1.json 只写 confirmed / third_party_adjudicated（final=relevant）的结果。

**no_positive 双审**：A 提交完整执行证据 → B 结构化复核：`b_verification.verification_step_ids` 引用 B 独立执行的抽查检索步骤（结果同样落盘 gold_search_results.jsonl，step_id 前缀 `_bv`），不允许只有自由文本 rationale → 一致则裁决；B 认为可能有正例 → 分歧 → C 裁决或 BLOCKED。

---

## 6. hard-negative 门禁（冻结）

**schema 状态组合**：
- `b_reviewed=false + b_review_result="not_sampled"`
- `b_reviewed=true + b_review_result ∈ {confirmed, rejected, uncertain}`

**抽查协议**（`gold_hn_qc_config.json` 冻结）：
- seed=20260814；分层维度=item_id；样本数 = **ceil(hard_negative 总数 × 20%)**（精确值写入配置）；确定性抽样；**样本列表 `gold_hn_qc_sample_list.json` 在解盲前生成并冻结 SHA**
- **失败门**：抽查出现任何 rejected/uncertain → 扩大 **100% 复核**全部 hard negative；100% 复核的 rejected/uncertain 记录**不得删除**（全部留痕于 acquisition log）

**replacement 与降级规则**（P0 修订：防虚假"未找到"）：
- 100% 复核后 rejected 的条目：A 可重选一条 replacement（**必须附来源轨迹 trace_step_refs**）→ B 复核；replacement 仍 rejected → 不得再重选
- **`no_hard_negative_found` 仅当**：该 item 的**独立 hard-negative 搜索计划**（gold_search_plans.json 中 hn 类步骤）完整执行（每步恰一次、候选清单落盘）且**全部候选完成审阅**、且审阅后无可用条目——才允许此状态
- **两次候选失败 ≠ 未找到**：未满足上述条件时，状态记 `BLOCKED_HARD_NEGATIVE_ACQUISITION`（该 item 正例裁决不受影响，但 Gold 终态不得为 GOLD_READY）
- 最终无法闭合 → 计入 `GOLD_BLOCKED_ACQUISITION`；**采集失败不得改写为"未找到"**

---

## 7. R1 材料处置（冻结：排除）

删除 R1 盲评候选复用路径（三条件不可同时成立，见 v1.2 裁决）。不生成导出脚本与候选 packet；R1 材料仅作历史证据，完全排除在 Gold 采集输入之外。

---

## 8. 冻结与密封（完整发布链）

**stage 机**：`None → config_frozen → code_frozen → sealed`

- **config_frozen**：gold_item_definitions.json、gold_roles.json、gold_search_plans.json、gold_hn_qc_config.json、上游引用（manifest_v4、required_knowledge/knowledge_audit SHA）、禁改守护配置
- **code_frozen**：gold_read_access.py、gold_search_exec.py、gold_blind_packet_builder.py（混合盲审包生成器）、gold_validate.py、reconcile_gold.py、**gold_blind_review_packet.jsonl（packet SHA 冻结）**
- **sealed**：gold_v1.json、gold_acquisition_log.jsonl、gold_search_results.jsonl、gold_b_labels.jsonl、gold_access_log.jsonl、gold_hn_qc_sample_list.json、GOLD_CLOSURE.md

**密封发布链**：

1. 采集完成（或明确阻塞）→ gold_validate.py 全过（112 项状态完整 / canonical key 可解析 / evidence_quote 子串真实 / 搜索计划执行覆盖 / 候选集合严格相等对账 / 引用完整性 / 双审闭合 / 盲审时间序）
2. 发布产物 → 冻结条目 → `set_stage(sealed)`
3. **最后发布 `GOLD_RECEIPT.json`**（不加入 manifest）：
   - `manifest_sha256`：sealed manifest json_canonical SHA
   - `artifacts` 精确集合（**两种终态相同**，中优修订）：`{"gold_v1.json", "gold_acquisition_log.jsonl", "gold_search_results.jsonl", "gold_b_labels.jsonl", "gold_access_log.jsonl", "gold_hn_qc_sample_list.json", "GOLD_CLOSURE.md"}`，每项 sha256/size/strategy
   - `acquisition_verdict` + 统计（anchored / no_positive / blocked 计数）
4. **reconcile_gold.py**：逐项 SHA + RECEIPT 精确集合与绑定 + 112 项完整性 + 双审闭合（每条 positive 有 resolution；每个分歧有裁决或 BLOCKED；blocked 项过程记录存在）+ 盲审时间序 + 引用完整性 + 候选集合对账 + access log（B 侧）校验
5. **恢复协议**：sealed 无 RECEIPT → 校验产物 SHA 与 manifest 一致后补发；其他漂移 fail-closed
6. **禁改守护**：GOLD_RECEIPT 发布后激活 config_frozen 阶段已冻结的守护配置（gold_v1.json + gold_manifest.json 加入禁改清单）；修订必须新建 gold_v2.json

---

## 9. 与 R2 的衔接（Gold 密封后另立设计）

- **R2 评估对象**：字符检索（现 S1-S5）、BM25、embedding、reranker（对比实验，单一变量）
- **指标口径**：
  - `anchor_recall@K`：仅 anchored 项为分母（公式留待 R2 设计冻结）
  - `fixed_112_retrievability`：命中 ≥1 条正例的 item 数 / 112
  - `gold_answerable_rate`：anchored 项数 / 112
  - `no_positive_rate`：无正例项数 / 112
  - **恒等约束**：`fixed_112_retrievability 理论上限 = gold_answerable_rate`（reconcile 校验）
  - bundle 噪声口径在 R2 设计冻结
- **门槛纪律**：Gold 冻结前不设 R2 数值门槛
- **语义判定器纪律**：LLM/embedding judge 必须先对 Gold 评测过门才可用于 R2 辅助评估；模型判断永远不是 Gold，不接入正式检索链

---

## 10. 明确不做（冻结边界）

- 不做 R1.5；不把 LLM/embedding judge 接入正式检索链
- 不允许 AI 参与标注（零 LLM API）
- 不复用 R1 盲评材料作为 Gold 候选（§7）
- 不为凑齐 112 项强行裁决分歧；不把采集失败改写为"未找到"（BLOCKED 是合法终态）
- 不修改 Phase 9A / R1 任何 sealed 产物
- Gold 不用于 44 道已知婚姻题的准确率声明；效果声明以密封集为准
- 密封婚姻集数据不进入 Gold 采集

---

## 11. 完成定义

1. 本规约通过审核
2. gold_roles.json 指定 A、B 两名互不相同人类身份（C 可选但须采集前冻结；否则首个分歧即 BLOCKED）
3. config/code 阶段全部条目冻结（含混合盲审包 SHA 先于 B 查看）
4. 采集完成或明确阻塞：112 项全部有状态记录（anchored / no_relevant_document_found_under_frozen_plan / BLOCKED_*）
5. 双审闭合：混合盲审包四态标签冻结后解盲；每条 positive 有 resolution；每个分歧有 C 裁决或 BLOCKED；no_positive 有 B 结构化复核（verification_step_ids 可解析）
6. 机器校验全过：canonical key 可解析、evidence_quote 子串真实、候选清单落盘可复算、reviewed == candidates 严格相等、trace_step_refs 引用完整、hard negative 抽查协议执行（含失败门与降级条件）
7. 终态 GOLD_READY 或 GOLD_BLOCKED_ACQUISITION；两分支都完整发布证据（RECEIPT artifact 集合相同；blocked 项过程记录存在）
8. sealed + GOLD_RECEIPT 发布，reconcile_gold exit 0；禁改守护激活
9. 全程零 LLM API；GOLD_CLOSURE 如实记录隔离等级（B=packet_only，A=access_attestation）
