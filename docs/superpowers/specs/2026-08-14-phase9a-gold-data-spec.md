# Phase 9A-Gold 设计：item-centered 人工 Gold 数据规约（零 API 采集协议）

**日期：** 2026-08-14
**状态：** v1.2（NEEDS_REVISION 二轮修订：物理目录隔离、双审分歧协议与双终态、删除 R1 候选路径、no_positive 证据强化、hard-negative 门禁闭合）
**裁决依据：** R1.5 关闭；路线为 **Gold 规约与采集 → Gold 密封 → R2 候选覆盖实验**（选项 2+3 组合）
**前置冻结：** Phase 9A（manifest_v4 sealed，QC_FAIL）+ Phase 9A-R1（manifest_v5 sealed，SILVER_LABEL_NOT_CALIBRATED，25/61）

---

## 1. 背景与动机

Phase 9A-R1 证明：词面 silver 规则与人类判断分歧 25/61（41%），分歧呈双向语义性。**方向判断**：表层规则已到能力边界（该归因尚未独立冻结，暂不作为封存结论）。裁决：放弃 R1.5，建立 item-centered 人工 Gold，作为 R2 候选覆盖实验与任何语义判定器的评测基准。

**为什么不能只标 673 条检索并集**：并集只覆盖 37/112 个知识项，剩余 75 项无候选；只标并集无法评估候选召回与 112 项固定分母覆盖率。

---

## 2. 目标、终态与验收口径

**双终态**（P0 修订：不为凑齐 112 项强行裁决）：

- `GOLD_READY`：112 项全部完成裁决（anchored 或 no_relevant_document_found_under_frozen_plan），双审与分歧处理全部闭合
- `GOLD_BLOCKED_ACQUISITION`：存在未闭合项（分歧未裁决 / 搜索计划未完整执行 / 角色未指定）——保留完整过程证据与阻塞原因，不强行裁决；两种终态都完整发布证据

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 覆盖全部 112 项 | 每个 item_id 恰有一条裁决完成记录 |
| G2 | 正例 A 提议 + B 盲审 + 分歧裁决 | B 独立标签（relevant/partial/irrelevant/uncertain）；一致→confirmed；分歧→第三人裁决或 BLOCKED_ACQUISITION |
| G3 | 无正例项证据强化 | 冻结搜索计划逐步唯一执行 + 候选全量审阅 + B 复核，状态记 `no_relevant_document_found_under_frozen_plan` |
| G4 | hard negative 门禁闭合 | 1–2 条（B 抽查协议冻结）或结构化 `no_hard_negative_found`（附搜索轨迹） |
| G5 | 角色隔离可验证 | 物理目录隔离 + 唯一读取包装器自动日志；无法隔离的环境只能称"访问声明" |
| G6 | Gold 冻结后不可修改 | SHA 密封 + manifest + GOLD_RECEIPT + 禁改守护（配置 seal 前冻结，receipt 后激活） |
| G7 | 112 项判定语义冻结 | gold_item_definitions.json（含上游路径与 SHA）先于采集冻结 |

---

## 3. 角色契约与隔离（冻结）

**标注口径**：curator 均为人类；不允许 AI 初选/复核/裁决（零 LLM API 硬约束）。

**角色**：
- **curator_A（提议者）**：112 项正例提议、hard negative 选择、结构化轨迹记录
- **curator_B（盲审者）**：对 A 的每条提议做**独立盲审**（标签 relevant/partial/irrelevant/uncertain，不看 A 结论）；复核全部 no_positive 轨迹；hard negative 抽查
- **curator_C（裁决者，按需）**：仅当 A/B 分歧时介入裁决；无分歧则不产生记录
- **开发者**：只提供冻结语料与工具，不参与标注决策

**身份前置门**：`gold_roles.json` 必须在采集开始前指定**两个（或三个）互不相同的人类身份**；未指定或身份相同 → 采集状态 `BLOCKED_ROLE_ASSIGNMENT`，不得开始。

**物理隔离协议**（P0 修订：访问日志必须由机制产生，非自报）：

1. **目录隔离**：三个互不重叠的物理工作目录
   - `gold_workspace/A/`：item 定义 + 冻结语料只读导出 + 采集工具；**不含** R1/Phase 9A 任何 judgment/review/packet 文件
   - `gold_workspace/B/`：item 定义 + 冻结语料只读导出 + 独立盲审 packet（仅 item 定义 + 条文，**不含** A 的提议结论）
   - `gold_workspace/shared_frozen/`：只读语料导出源（生成后 SHA 冻结）
2. **唯一读取包装器**：A/B 对语料的一切读取必须经 `gold_read_access.py`（code_frozen 冻结）；包装器自动追加 access log（角色、时间、读取对象、来源目录）——日志由机制产生，遗漏读取即无日志记录
3. **盲法校验**：reconcile 校验 A 目录文件清单不含任何标签文件、access log 中 A 无标签/packet 读取记录
4. **诚实声明**：本地单机环境下这是**进程级隔离 + 自动日志**，非 OS 级权限强制；GOLD_CLOSURE 必须如实记录隔离强度等级（process_isolation + auto_log），不得称为权限级盲法证据；若环境无法提供包装器机制，只能称"访问声明"（access_attestation），终态证据等级相应降级记录

---

## 4. 112 项定义与搜索计划冻结（先于采集）

**gold_item_definitions.json**（顶层 `{"schema_version": "1.0", "items": [...]}`，112 元素，按 item_id 排序）：每项含 item_id/case_id/required_term/query_specs/item_description + 上游 required_knowledge/knowledge_audit 路径与 SHA。上游漂移 → reconcile fail-closed。

**gold_search_plans.json**（P0 修订：证据强化）：每 item 一份搜索计划，每个步骤冻结：

```json
{
  "step_id": "0002k4_s1",
  "entrypoint": "search_gejue",
  "args": {},
  "query_terms": ["婚期", "结婚"],
  "filters": {},
  "corpus_snapshot_sha256": "..."
}
```

**执行约束**：
- 每个计划步骤**恰好执行一次**（执行记录带 step_id，重复执行或缺失 → 该 item BLOCKED）
- 执行记录必须含 `candidate_keys_sha256`（该步全部返回候选 key 列表的 canonical SHA）与 `candidate_count`
- `reviewed_canonical_keys` 必须**完整覆盖**该步候选全集（对账：reviewed 集合 == 候选集合；漏审 → 该 item BLOCKED）
- **诚实口径**：top-K 检索未命中不能证明整个冻结语料无正例；该状态只能声明为 `no_relevant_document_found_under_frozen_plan`（计划范围内未找到），不得简写为绝对结论

---

## 5. Gold schema（冻结草案）

`gold_v1.json` 顶层：`{"schema_version": "1.0", "item_count": 112, "verdict_source": "GOLD_READY | GOLD_BLOCKED_ACQUISITION", "items": [...]}`，items 按 item_id 排序。**gold_v1.json 只保存裁决完成后的派生结果**；过程记录（提议/盲审/裁决）在 `gold_acquisition_log.jsonl`（密封时一并冻结）。

```json
{
  "item_id": "mingli_ftb_0002#k4",
  "status": "anchored | no_relevant_document_found_under_frozen_plan | BLOCKED_ACQUISITION",
  "collection_trace_ref": "trace_0002k4",
  "positives": [
    {
      "canonical_key": "kb:gejue:hy_006",
      "evidence_quote": "条文中的关键句（原文摘录）",
      "trace_step_refs": ["0002k4_s1#3"],
      "resolution": "confirmed | third_party_adjudicated"
    }
  ],
  "hard_negatives": [
    {
      "canonical_key": "...",
      "collision_terms": ["桃花"],
      "evidence_quote": "撞车词的上下文摘录",
      "why_negative": "含'桃花'但讲流年凶煞，非桃花知识点",
      "b_reviewed": false,
      "b_review_result": "not_sampled"
    }
  ],
  "hard_negative_status": "found | no_hard_negative_found",
  "no_positive_evidence": {
    "executed_steps": [
      {
        "step_id": "0002k4_s1",
        "entrypoint": "search_gejue",
        "args": {},
        "corpus_snapshot_sha256": "...",
        "candidate_keys_sha256": "...",
        "candidate_count": 12,
        "reviewed_canonical_keys": ["...（完整列表）"]
      }
    ],
    "corpus_sections_checked": ["kb:gejue", "classic:qiongtongbaojian/all_rules.json"],
    "search_plan_sha256": "...",
    "plan_fully_executed": true,
    "all_candidates_reviewed": true
  },
  "adjudication": {
    "curator": "curator_B",
    "verdict": "no_relevant_document_found_under_frozen_plan",
    "rationale": "复核结论（必填）"
  },
  "blocked_reason": "（仅 BLOCKED_ACQUISITION）结构化阻塞原因"
}
```

**item 级轨迹**（中优修订）：每个 item 恰有一份 `collection_trace`（存于 gold_acquisition_log.jsonl，trace_id = `trace_{item_id}`）；positive 只引用 `trace_step_refs`，不各自携带轨迹副本，避免同 item 多份轨迹漂移。

**双审流程**（P0 修订：分歧处理协议）：

1. **A proposal**：A 提议正例（canonical_key + evidence_quote + trace 引用），记入 acquisition log
2. **B blind review**：B 独立打标 `relevant / partially_relevant / irrelevant / uncertain`（不看 A 结论），记入 log
3. **分歧处理**：
   - B=relevant → `confirmed`（与 A 提议意图一致）
   - B=partially_relevant / irrelevant / uncertain → **分歧** → curator_C 裁决（`third_party_adjudicated`，记录裁决者与理由）或该 item 进入 `BLOCKED_ACQUISITION`
   - **不允许**为凑数强行裁决；C 未指定或裁决未完成 → 保持 BLOCKED
4. **派生结果**：只有 confirmed / third_party_adjudicated（final=relevant）的提议才写入 gold_v1.json positives

**no_positive 双审**：A 提交完整执行证据 → B 复核（轨迹完整性 + 独立抽查检索）→ 一致则裁决 `no_relevant_document_found_under_frozen_plan`；B 认为可能存在正例 → 分歧 → C 裁决或 BLOCKED。

---

## 6. hard-negative 门禁（冻结）

**schema 状态组合**（P0 修订：闭合）：
- `b_reviewed=false + b_review_result="not_sampled"`（未被抽中）
- `b_reviewed=true + b_review_result ∈ {confirmed, rejected, uncertain}`

**抽查协议**（QC 配置冻结 `gold_hn_qc_config.json`）：
- seed=20260814；分层维度=item_id；样本数 = ceil(hard_negative 总数 × 20%)；确定性抽样算法与样本列表冻结（`gold_hn_qc_sample_list.json`，采集完成后、B 抽查前生成并冻结）
- **失败门**：抽查出现任何 rejected/uncertain → **扩大到 100% 复核**全部 hard negative
  - 100% 复核后仍 rejected 的条目：删除该 hard negative，A 重选一条并经 B 复核；重选后仍 rejected → 该 item `hard_negative_status=no_hard_negative_found`
  - 100% 复核后仍 uncertain 的条目：该 item `hard_negative_status=no_hard_negative_found`（保守处理，附理由）

**no_hard_negative_found**：必须附结构化搜索轨迹（复用 collection_trace 的 step 引用 + `no_hard_negative_reason`），不接受纯自由文本。

---

## 7. R1 材料处置（P0 修订：删除候选复用路径）

**裁决**：删除 R1 盲评候选复用路径。理由：「所有 positive 均 A 提议 + B 盲审」「A 不得接触 R1 packet」「R1 候选由 B 复核直接入 Gold」三条件不可同时成立；引入 curator_C 专用于候选路径只增加角色复杂度，收益（加速采集）不值得破坏协议一致性。

- 不生成 export_r1_gold_candidates.py、不生成候选 packet
- R1 的 61 条盲评与 673 judgment 仅作为历史证据，完全排除在 Gold 采集输入之外
- A 与 B 的采集输入只有 gold_item_definitions.json + 冻结语料

---

## 8. 冻结与密封（完整发布链）

**stage 机**：`None → config_frozen → code_frozen → sealed`

- **config_frozen**：gold_item_definitions.json、gold_roles.json（含 BLOCKED_ROLE_ASSIGNMENT 门）、gold_search_plans.json、gold_hn_qc_config.json、上游引用（manifest_v4、required_knowledge/knowledge_audit SHA）、**禁改守护配置**（中优修订：守护配置在 seal 前冻结，receipt 后只激活不修改）
- **code_frozen**：gold_read_access.py（读取包装器）、gold_validate.py、reconcile_gold.py、gold_search_exec.py（计划执行器，记录 candidate_keys_sha256）
- **sealed**：gold_v1.json、gold_acquisition_log.jsonl、gold_access_log.jsonl、gold_hn_qc_sample_list.json、GOLD_CLOSURE.md

**密封发布链**：

1. 采集完成 → gold_validate.py 全过（112 项完整 / canonical key 可解析 / evidence_quote 子串真实 / 搜索计划执行覆盖 / 候选全量审阅 / 双审记录完整）
2. 发布 gold_v1.json 及审计产物 → 冻结条目 → `set_stage(sealed)`
3. **最后发布 `GOLD_RECEIPT.json`**（不加入 manifest，避免循环）：
   - `manifest_sha256`：sealed manifest 的 json_canonical SHA
   - `artifacts` **精确集合**（中优修订）：`{"gold_v1.json", "gold_acquisition_log.jsonl", "gold_access_log.jsonl", "gold_hn_qc_sample_list.json", "GOLD_CLOSURE.md"}`，每项 sha256/size/strategy
   - `verdict`：GOLD_READY | GOLD_BLOCKED_ACQUISITION + 统计（anchored/no_positive/blocked 计数）
4. **reconcile_gold.py**：逐项 SHA + RECEIPT 精确集合与绑定 + 112 项完整性 + 双审闭合校验（每条 positive 有 resolution、每个分歧有裁决或 BLOCKED）+ access log 盲法校验 + 恒等关系校验
5. **恢复协议**：sealed 无 RECEIPT → 校验产物 SHA 与 manifest 一致后补发；其他漂移 fail-closed
6. **禁改守护**：GOLD_RECEIPT 发布后激活 config_frozen 阶段已冻结的守护配置（gold_v1.json + gold_manifest.json 加入禁改清单）；修订必须新建 gold_v2.json

---

## 9. 与 R2 的衔接（Gold 密封后另立设计）

- **R2 评估对象**：字符检索（现 S1-S5）、BM25、embedding、reranker（对比实验，单一变量）
- **指标口径**：
  - `anchor_recall@K`：仅 anchored 项为分母（macro/weighted 公式留待 R2 设计冻结，中优修订：本规约不使用未定义表述）
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
- 不为凑齐 112 项强行裁决分歧（BLOCKED_ACQUISITION 是合法终态）
- 不修改 Phase 9A / R1 任何 sealed 产物
- Gold 不用于 44 道已知婚姻题的准确率声明；效果声明以密封集为准
- 密封婚姻集数据不进入 Gold 采集

---

## 11. 完成定义

1. 本规约通过审核
2. gold_roles.json 指定互不相同的人类身份（否则 BLOCKED_ROLE_ASSIGNMENT，采集不得开始）
3. gold_item_definitions.json / gold_search_plans.json / gold_hn_qc_config.json / 守护配置冻结（config_frozen）；工具代码冻结（code_frozen）
4. 采集完成或明确阻塞：112 项全部有状态记录（anchored / no_relevant_document_found_under_frozen_plan / BLOCKED_ACQUISITION）
5. 双审闭合：每条 positive 有 B 盲审标签 + resolution；每个分歧有 C 裁决或 BLOCKED；no_positive 有 B 复核裁决
6. 机器校验全过：canonical key 可解析、evidence_quote 子串真实、搜索计划逐步唯一执行、候选全量审阅对账、hard negative 抽查协议执行（含失败门升级逻辑）
7. 终态 GOLD_READY（全部闭合）或 GOLD_BLOCKED_ACQUISITION（阻塞项 + 原因完整记录）；两分支都完整发布证据
8. sealed + GOLD_RECEIPT 发布，reconcile_gold exit 0；禁改守护激活
9. 全程零 LLM API；隔离强度等级在 GOLD_CLOSURE 如实记录（process_isolation + auto_log 或 access_attestation）
