# Phase 9A-Gold 设计：item-centered 人工 Gold 数据规约（零 API 采集协议）

**日期：** 2026-08-15
**状态：** v1.7（NEEDS_REVISION 七轮修订：positive_control 契约闭合、verification 空集产物、receipt 同构）
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
| G1 | 覆盖全部 112 项 | 每个 item_id 恰有一条**终态状态记录**（BLOCKED 明确未完成裁决） |
| G2 | 混合盲审 + 分歧裁决 | B 对混合包（全部 positive proposal + 抽中的 hard negative + filler，打乱、无类型/身份标记）统一四态打标；分歧→C 裁决或 BLOCKED；四态→派生结果映射冻结（§5） |
| G3 | 无正例项证据强化 | 冻结搜索计划逐步唯一执行 + 候选清单落盘可复算 + 全量审阅对账 + B 结构化复核（packet-only，标签 schema 与聚合规则冻结） |
| G4 | hard negative 门禁闭合 | 分层抽样算法完全冻结（分配/回流/RNG 状态）；扩审与 replacement 走版本化盲审轮次（r2/r3），不绕过 packet-only |
| G5 | 隔离强度诚实分级 | B = packet-only（含 verification 也走独立 packet）；A = access_attestation（诚实声明） |
| G6 | Gold 冻结后不可修改 | SHA 密封 + manifest + GOLD_RECEIPT + 禁改守护（配置 seal 前冻结，receipt 后激活） |
| G7 | 112 项判定语义冻结 | gold_item_definitions.json（含上游路径与 SHA）先于采集冻结 |

---

## 3. 角色契约与隔离（冻结）

**标注口径**：curator 均为人类；不允许 AI 初选/复核/裁决（零 LLM API 硬约束）。

**前置门**：`gold_roles.json` 必须在采集开始前指定 **A、B 两名互不相同的人类身份**（C 为可选备用）；未指定或身份相同 → `BLOCKED_ROLE_ASSIGNMENT`，采集不得开始。**分歧即决规则**：出现首个 A/B 分歧且 gold_roles.json 未指定 C 时，该 item 立即进入 `BLOCKED_ACQUISITION`，不得等待临时追加第三人后继续依赖裁决（C 只能在采集开始前冻结）。

**角色**：
- **curator_A（提议者）**：正例提议、hard negative 选择、结构化轨迹记录
- **curator_B（盲审者）**：对各轮混合盲审包统一四态打标；复核全部 no_positive 轨迹（经独立 verification packet，保持 packet-only）；hard negative 抽查与扩审（经版本化轮次 packet）
- **curator_C（裁决者，可选）**：仅当 A/B 分歧时介入；必须在采集开始前冻结于 gold_roles.json
- **开发者**：只提供冻结语料与工具，不参与标注决策

**隔离强度分级**（诚实声明）：

1. **B = packet-only 强隔离**：B 的工作目录**只含**各轮混合盲审包 + B verification packet + gold_item_definitions.json；**不含原始语料、不含 A 的任何产出**。**顺序门**（中优修订：非时间戳声明）：B workspace 发布器校验 `BLIND_PACKET_RECEIPT_rN.json` 存在且 SHA 匹配后，才把对应轮次 packet 复制进 B 目录——receipt 校验是 packet 交付的前置条件
2. **A = access_attestation**：A 需要直接检索原始语料，程序无法证明包装器是唯一读取路径。A 侧隔离固定为 **access_attestation**：gold_read_access.py 自动记录经包装器的读取，A 签署声明"未绕过包装器读取标签/packet 文件"；**不得声称"遗漏读取可检测"或"A 侧盲法可验证"**
3. **盲法可验证的部分**（reconcile 机器校验）：各轮盲审包 SHA 在 B 查看前冻结（发布器 receipt 门）、B 标签冻结后才解盲、packet 不含类型/身份/理由字段、B 目录清单不含语料与 A 产出、access log 中 B 无语料读取记录
4. GOLD_CLOSURE 必须如实记录两侧隔离等级：`B=packet_only`、`A=access_attestation`

---

## 4. 112 项定义与搜索计划冻结（先于采集）

**gold_item_definitions.json**（顶层 `{"schema_version": "1.0", "items": [...]}`，112 元素，按 item_id 排序）：每项含 item_id/case_id/required_term/query_specs/item_description + 上游 required_knowledge/knowledge_audit 路径与 SHA。上游漂移 → reconcile fail-closed。

**gold_search_plans.json**：每 item 一份搜索计划（含正例检索步骤与 hard-negative 检索步骤），每步冻结 `step_id / entrypoint / args / query_terms / filters / corpus_snapshot_sha256`。

**gold_b_verification_plans.json**（P0 修订：全量预冻结，解决 config 阶段无法预知 no-positive 子集的矛盾）：**采集前为全部 112 项**冻结 B 复核检索计划（entrypoint/args/query_terms/filters，step_id 前缀 `_bv`）；最终只执行 A 声明 no_positive 的子集（未执行项的计划保留但结果为空，reconcile 校验执行子集与 A 声明一致）。不得在 config_frozen 后修改原计划文件。

**执行契约**（候选清单可复算）：

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
- **key 排序与去重**：先按 canonical_key 字典序排序、再去重（顺序冻结：排序在去重前）
- **SHA canonical 规则**：`candidate_keys_sha256 = sha256(json.dumps(ordered_candidate_keys, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")`
- **唯一终态**：每个 step_id 在 gold_search_results.jsonl 中恰有一行；重复执行或缺失 → 该 item BLOCKED
- **审阅对账**：`reviewed_canonical_keys == ordered_candidate_keys`（严格集合相等，机器校验）；漏审 → BLOCKED
- **引用完整性**：`trace_step_refs` 格式冻结为 `step_id@canonical_key`；reconcile 校验每个引用能在对应 step_id 的 ordered_candidate_keys 中解析到该 canonical_key
- **诚实口径**：top-K 未命中不能证明语料无正例；该状态只声明 `no_relevant_document_found_under_frozen_plan`

**B verification 执行与标签**（P0 修订：schema 与聚合规则冻结）：

1. 冻结执行器机械运行 `gold_b_verification_plans.json` 的 no-positive 子集 → 结果落盘 gold_search_results.jsonl（`_bv` 步骤）→ 生成独立 `gold_b_verification_packet.jsonl`（仅 item 定义 + 候选条文全文，不含 A 结论）→ **冻结 packet SHA** → **发布器顺序门**（中优修订：校验 `B_VERIFICATION_PACKET_RECEIPT.json` 存在且 SHA 匹配后才复制进 B 目录，与混合盲审包同构）→ B 只审核该 packet
   - **空集产物**（同步项）：若无 item 声明 no_positive，仍生成空的 `gold_b_verification_packet.jsonl`（0 行）+ 空的 `gold_b_verification_labels.jsonl`（0 行）+ 对应 receipt（行数=0），否则固定基础 artifact 集合无法满足
   - **receipt 同构**（同步项）：`B_VERIFICATION_PACKET_RECEIPT.json` 字段与盲审 packet receipt 同构：`packet_sha256` + `packet_lines`（行数）+ `candidate_keys_sha256`（该 packet 全部候选 key 集合的 canonical SHA）
2. **B verification 标签 schema**（冻结，写入 `gold_b_verification_labels.jsonl`）：每行 `{step_id, item_id, canonical_key, verification_label, note, evidence_quote}`；`verification_label ∈ {relevant, partially_relevant, irrelevant, uncertain}`；note 必填；**evidence_quote 条件必填**（中优修订：verification_label ∈ {relevant, partially_relevant} 时必填，irrelevant/uncertain 时可空）
3. **覆盖约束**：标签必须恰好覆盖该 `_bv` 步骤的全部候选（无缺失/重复/额外）；违反 → 该 item BLOCKED
4. **聚合规则**（冻结）：**仅当该 item 全部 `_bv` 候选均为 `irrelevant`** 才允许确认 `no_relevant_document_found_under_frozen_plan`；出现任何 relevant/partially_relevant/uncertain → 进入 A/B 分歧（C 裁决或 BLOCKED）；B 找到疑似正例时必须引用 `canonical_key + evidence_quote`（写入标签行）
5. **B 全程不接触语料**

---

## 5. Gold schema 与混合盲审（冻结草案）

`gold_v1.json` 顶层：`{"schema_version": "1.0", "item_count": 112, "acquisition_verdict": "GOLD_READY | GOLD_BLOCKED_ACQUISITION", "items": [...]}`，items 按 item_id 排序。**gold_v1.json 只保存裁决完成后的派生结果**；过程记录在 `gold_acquisition_log.jsonl`（密封时一并冻结，含 blocked 项的未完成过程记录）。

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
  "hard_negative_status": "found | no_hard_negative_found | not_applicable",
  "no_positive_evidence": {
    "executed_step_ids": ["0002k4_s1", "0002k4_s2"],
    "search_plan_sha256": "...",
    "plan_fully_executed": true,
    "all_candidates_reviewed": true,
    "b_verification": {
      "curator": "curator_B",
      "verdict": "no_relevant_document_found_under_frozen_plan",
      "verification_step_ids": ["0002k4_bv1"],
      "verification_label_refs": ["gold_b_verification_labels.jsonl#0002k4_bv1"],
      "rationale": "复核结论（必填）"
    }
  },
  "blocked_reason": "（仅 BLOCKED 状态）结构化阻塞原因"
}
```

**组合约束**（中优修订）：`status` 为 BLOCKED_* 时 `hard_negative_status` 必须为 `not_applicable`，避免 blocked item 同时写成 `found` 的语义不清。`hard_negative_status` 完整枚举：`found | no_hard_negative_found | not_applicable`。

**item 级轨迹**：每个 item 恰有一份 collection_trace（存于 gold_acquisition_log.jsonl，trace_id = `trace_{item_id}`）；positive/hard negative 只引用 `trace_step_refs`，不携带轨迹副本。

### 5.1 混合盲审轮次（P0 修订：版本化）

**轮次版本化**（扩审与 replacement 不绕过 packet-only）：

- **r1（初始轮）**：全部 positive proposal + 抽中的 hard negative（抽样先于 packet 构造冻结，见 §6）+ filler
- **r2（扩审轮）**：仅当 r1 抽查触发失败门时生成——包含**全部剩余未审 hard negative**（80% 部分）+ **positive controls 与 filler**（P0 修订：r2/r3 混入已 confirmed 的 positive 条目与 filler，使 B 无法由轮次推出类型，保持类型盲审）；r2 只能在 r1 触发扩审后生成
- **r3（replacement 轮）**：仅当扩审后存在 rejected 且 A 重选 replacement 时生成——包含 replacement 条目 + **positive controls 与 filler**（同上）；replacement 不得绕过 packet-only 直接交 B 复核

**r2/r3 类型盲审保持**（P0 修订）：r2/r3 混入的 positive controls 从已 confirmed 的 positive 中确定性抽取（数量 = 该轮真实 HN 条数，seed 按轮次派生），filler 算法同 r1；B 仅凭轮次无法推出条目类型。

**positive_control 契约**（P0 修订：闭合）：

- **类型与结果语义**：`proposal_type = positive_control`；派生结果 = **diagnostic_only**（不参与终态判定）；**不修改原 positive 的 resolution**（B 再次标为 partial/irrelevant 不推翻已确认正例）；**不进入 A/B 分歧或 Gold 计数**；control 的标签分布仅进入 GOLD_CLOSURE 诊断
- **确定性抽取**：control pool = 已 confirmed 的 positive 条目按 `(item_id, canonical_key)` 字典序排序；**优先无放回抽取**；若 confirmed positive 数量 < 本轮真实 HN 条数 → **允许有放回循环抽取**（按序循环，非随机重抽；记录 `reused=true` 标记）；若 confirmed positive 数量为 0（r2 发生在任何 positive confirmed 之前）→ `BLOCKED_BLIND_PACKET_INPUT`
- **引用与复用**：每条 control 记录 `source_positive_ref`（指向原 positive 的 canonical_key + item_id）；**同一轮内同一 control 可重复出现**（有放回循环时）；**跨轮复用允许**（r2/r3 可从同一 control pool 抽取）
- **诊断语义**：control 的 B 标签分布（relevant 比例）仅作盲审质量信号记录于 closure；不是质量门，无阈值无失败行为

**轮次生成器 fail-closed 校验**（中优修订）：r2/r3 生成器必须校验前一轮 label receipt 存在且 SHA 匹配 + 触发条件真实成立（r2：r1 抽查有 rejected/uncertain；r3：扩审后有 rejected 且 replacement 条目存在），否则拒绝生成。

每轮独立产物：`gold_blind_review_packet_rN.jsonl` / `gold_b_labels_rN.jsonl` / `gold_blind_unblind_map_rN.json` / `BLIND_PACKET_RECEIPT_rN.json` / `B_LABEL_RECEIPT_rN.json`。

**混合包构成与字段**（每轮相同规则）：
- 每条仅含 blind_id（本轮内重新编号）/ item_id / canonical_key / document_text；**不含** proposal 类型、A 身份、A 理由、来源阶段、collision_terms
- **filler 算法**（中优修订：decoy 更名 filler，明确诊断性质）：
  - 逐 item 计算：`n_filler_i = ceil(max(n_positive_i, n_sampled_hn_i) × 0.5)`（ceil 取整冻结）
  - 候选池：冻结语料全部 canonical_key 按字典序排序，排除该 item 已使用的 key（proposal + 抽中 HN + 前轮已用 filler）
  - 抽取：**独立 RNG** `random.Random(20260815 + stable_hash(item_id))`（按 item_id 派生 seed，避免与全局打乱共用隐含 RNG 状态）无放回抽取 n_filler_i 条
  - **stable_hash 精确定义**（P0 修订：跨进程可复现）：`stable_hash(item_id) = int.from_bytes(hashlib.sha256(item_id.encode("utf-8")).digest()[:8], "big")`
  - 候选不足 → `BLOCKED_BLIND_PACKET_INPUT`
  - filler 归属其检索来源 item 的 item_id；filler 的 B 标签**不参与终态判定**，仅作为**分布诊断**信号记录于 GOLD_CLOSURE（filler 中 relevant 比例异常高提示 B 标签基线漂移；**不得称错误率**——filler 是随机未使用文档，不保证语义无关）
- **打乱与编号**：本轮全部条目合并后按**轮次派生独立 seed**（P0 修订：`20260815 + N`，N=轮次号，避免 r1/r2/r3 共用隐含 RNG 语义）全局打乱（全局 RNG 独立于 filler 抽取 RNG）→ 对最终顺序依次生成 blind_id（`blind_r{N}_001` 起递增）→ 生成 packet → **冻结 packet SHA（code_frozen）→ 发布器 receipt 门 → B 才收到**

**B 标签 schema**（冻结，`gold_b_labels_rN.jsonl`）：每行 `{blind_id, item_id, canonical_key, label, note, packet_sha256}`；label ∈ 四态；note 必填；blind_id 恰好覆盖该轮 packet（无重复/额外）；每行携带该轮 packet SHA。

**四态 → 派生结果映射**（P0 修订：冻结，解盲工具与 reconcile 共用同一映射，禁止各自重写）：

| 条目类型 | B 标签 | 派生结果 |
|---|---|---|
| positive proposal | relevant | confirmed |
| positive proposal | partially_relevant / irrelevant / uncertain | disagreement |
| hard negative | irrelevant | confirmed |
| hard negative | relevant / partially_relevant | rejected |
| hard negative | uncertain | uncertain |
| positive_control | 任意 | diagnostic_only（不修改原 resolution，不参与终态） |
| filler | 任意 | diagnostic_only（不参与终态） |

**解盲证据链**（每轮独立）：

- `BLIND_PACKET_RECEIPT_rN.json`：绑定该轮 packet SHA + packet 行数
- `B_LABEL_RECEIPT_rN.json`：绑定该轮 label 文件 SHA + packet SHA + **标签行数 + blind_id 集合 SHA + packet 行数**（中优修订：不只文件 SHA）
- `gold_blind_unblind_map_rN.json`：blind_id → {proposal_type, canonical_key, item_id}；**同时绑定该轮 packet SHA 与 label SHA**
- 解盲映射**只能在该轮 B_LABEL_RECEIPT 发布后生成**（生成器校验 label receipt 存在且 SHA 匹配，否则 fail-closed）
- 全部进入 manifest（sealed）、最终 GOLD_RECEIPT（版本化 artifact 列表，见 §8）、reconcile 校验

**双审分歧流程**：A proposal → B 盲审四态标签（混合包）→ 解盲比对（冻结映射）→ proposal confirmed 或分歧；HN confirmed/rejected/uncertain 按映射派生。分歧 → C 裁决（third_party_adjudicated）或该 item BLOCKED_ACQUISITION。gold_v1.json 只写 confirmed / third_party_adjudicated（final=relevant）的 positive 结果。

**no_positive 双审**：A 提交完整执行证据 → 冻结执行器运行 B verification 计划 → B 审核 verification packet（标签落盘）→ 聚合规则判定（§4）→ 一致则裁决；分歧 → C 裁决或 BLOCKED。

---

## 6. hard-negative 门禁（冻结）

**schema 状态组合**：
- `b_reviewed=false + b_review_result="not_sampled"`
- `b_reviewed=true + b_review_result ∈ {confirmed, rejected, uncertain}`（由冻结映射派生）

**分层抽样算法**（P0 修订：完全可复算，`gold_hn_qc_config.json` 冻结）：

- **候选排序键**：hard negative 候选按 `(item_id, canonical_key)` 字典序排序
- **分层维度**：item_id（112 层）
- **每层最低样本数**：`floor(n_hn_i × 0.2)`（n_hn_i = 该 item 的 HN 候选数；最低 0）
- **全局目标样本数**：`ceil(hard_negative 总数 × 20%)`（精确值写入配置）
- **余数分配**：全局目标 - 各层最低之和 = 余数 R；按 item_id 字典序逐层补足（每层 +1 直到 R 用尽或该层候选用尽）
- **回流**：某层候选少于配额时，其缺口回流到剩余层（按 item_id 字典序继续补足）
- **RNG**：**全局单实例** `random.Random(20260814)`；每层内用该实例无放回抽取该层配额数
- **最终样本列表**必须精确等于该算法输出（机器校验）
- **时序冻结**：样本列表 `gold_hn_qc_sample_list.json` 在**r1 盲审包构造之前**生成并冻结 SHA；抽中的 HN 进 r1 包，未抽中保持 not_sampled

**失败门与扩审**：
- r1 抽查出现任何 rejected/uncertain → 触发扩审 → **生成 r2 盲审包**（全部剩余未审 HN）→ B 复核 → 100% 复核的 rejected/uncertain 记录**不得删除**（全部留痕于 acquisition log）

**replacement 与降级规则**（防虚假"未找到"）：
- 扩审后 rejected 的条目：A 可重选一条 replacement（**必须附来源轨迹 trace_step_refs**）→ **生成 r3 盲审包** → B 复核；replacement 仍 rejected → 不得再重选
- **`no_hard_negative_found` 仅当**：该 item 的**独立 hard-negative 搜索计划**（gold_search_plans.json 中 hn 类步骤）完整执行（每步恰一次、候选清单落盘）且**全部候选完成审阅**、且审阅后无可用条目——才允许此状态
- **两次候选失败 ≠ 未找到**：未满足上述条件时，状态记 `BLOCKED_HARD_NEGATIVE_ACQUISITION`（该 item 正例裁决不受影响，但 Gold 终态不得为 GOLD_READY）
- 最终无法闭合 → 计入 `GOLD_BLOCKED_ACQUISITION`；**采集失败不得改写为"未找到"**

---

## 7. R1 材料处置（冻结：排除）

删除 R1 盲评候选复用路径。不生成导出脚本与候选 packet；R1 材料仅作历史证据，完全排除在 Gold 采集输入之外。

---

## 8. 冻结与密封（完整发布链）

**stage 机**：`None → config_frozen → code_frozen → sealed`

- **config_frozen**：gold_item_definitions.json、gold_roles.json、gold_search_plans.json、gold_b_verification_plans.json、gold_hn_qc_config.json、上游引用（manifest_v4、required_knowledge/knowledge_audit SHA）、禁改守护配置
- **code_frozen**：gold_read_access.py、gold_search_exec.py、gold_blind_packet_builder.py、gold_unblind_mapper.py（解盲映射生成器，含冻结四态映射）、gold_validate.py、reconcile_gold.py、gold_hn_qc_sample_list.json（r1 构造前冻结）、**gold_blind_review_packet_r1.jsonl（packet SHA 冻结）**、**gold_b_verification_packet.jsonl（packet SHA 冻结）**；后续轮次（r2/r3）packet 在生成时按 code_frozen 追加冻结（manifest 允许 code_frozen 阶段追加新条目，append-only）
- **sealed**：gold_v1.json、gold_acquisition_log.jsonl、gold_search_results.jsonl、各轮 gold_b_labels_rN.jsonl、各轮 gold_blind_unblind_map_rN.json、各轮 BLIND_PACKET_RECEIPT_rN.json、各轮 B_LABEL_RECEIPT_rN.json、gold_b_verification_labels.jsonl、gold_access_log.jsonl、B_VERIFICATION_PACKET_RECEIPT.json、GOLD_CLOSURE.md

**密封发布链**：

1. 采集完成（或明确阻塞）→ gold_validate.py 全过（112 项状态完整 / canonical key 可解析 / evidence_quote 子串真实 / 搜索计划执行覆盖 / 候选集合严格相等对账 / 引用完整性 / 双审闭合 / 盲审 receipt 绑定链与时间序 / 四态映射共用校验）
2. 发布产物 → 冻结条目 → `set_stage(sealed)`
3. **最后发布 `GOLD_RECEIPT.json`**（不加入 manifest）：
   - `manifest_sha256`：sealed manifest json_canonical SHA
   - `artifacts` **版本化列表**（中优修订：非固定单文件名，按实际轮数展开）：基础项 `{"gold_v1.json", "gold_acquisition_log.jsonl", "gold_search_results.jsonl", "gold_access_log.jsonl", "gold_b_verification_labels.jsonl", "gold_b_verification_packet.jsonl", "B_VERIFICATION_PACKET_RECEIPT.json", "GOLD_CLOSURE.md"}` + 每轮项 `{gold_blind_review_packet_rN.jsonl, gold_b_labels_rN.jsonl, gold_blind_unblind_map_rN.json, BLIND_PACKET_RECEIPT_rN.json, B_LABEL_RECEIPT_rN.json}`（N=1..实际轮数）+ `gold_hn_qc_sample_list.json`；每项 sha256/size/strategy；**两种终态集合规则相同**（按实际轮数展开）
   - `acquisition_verdict` + 统计（anchored / no_positive / blocked 计数 + 实际盲审轮数）
4. **reconcile_gold.py**：逐项 SHA + RECEIPT 版本化集合与绑定 + 112 项完整性 + 双审闭合 + **盲审 receipt 绑定链**（每轮 packet receipt 绑 packet SHA、label receipt 绑 label SHA + packet SHA + 行数/blind_id 集合 SHA、unblind map 绑 packet SHA + label SHA、unblind map 生成晚于 label receipt）+ 引用完整性 + 候选集合对账 + access log（B 侧）校验 + 四态映射共用校验
5. **恢复协议**：sealed 无 RECEIPT → 校验产物 SHA 与 manifest 一致后补发；其他漂移 fail-closed
6. **禁改守护**：GOLD_RECEIPT 发布后激活 config_frozen 阶段已冻结的守护配置；修订必须新建 gold_v2.json

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
3. config/code 阶段全部条目冻结（含各轮盲审包 SHA 与 B verification packet SHA 先于 B 查看；HN 抽查样本先于 r1 构造冻结）
4. 采集完成或明确阻塞：112 项全部有终态状态记录
5. 双审闭合：各轮盲审包四态标签冻结后解盲（receipt 绑定链完整）；每条 positive 有 resolution；每个分歧有 C 裁决或 BLOCKED；no_positive 有 B 结构化复核（verification_label_refs 可解析、聚合规则满足）
6. 机器校验全过：canonical key 可解析、evidence_quote 子串真实、候选清单落盘可复算、reviewed == candidates 严格相等、trace_step_refs 引用完整、hard negative 分层抽样精确等于算法输出（含失败门、扩审轮次、降级条件）
7. 终态 GOLD_READY 或 GOLD_BLOCKED_ACQUISITION；两分支都完整发布证据（RECEIPT 版本化集合；blocked 项过程记录存在）
8. sealed + GOLD_RECEIPT 发布，reconcile_gold exit 0；禁改守护激活
9. 全程零 LLM API；GOLD_CLOSURE 如实记录隔离等级（B=packet_only，A=access_attestation）与 filler 分布诊断
