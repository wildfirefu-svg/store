# Phase 9A 设计：婚姻知识检索可行性（零 API）

**日期：** 2026-08-13
**状态：** v1.3.3（NEEDS_REVISION 五轮修订：judgeable 并集防重复扣除、QC 样本列表冻结时机移至 pool 后、QC 只审计不改标签、目标措辞对齐 silver）
**前置：** Phase 8 已冻结（`docs/phase8/CLOSURE.md`，最终 HEAD `0f74de2`；缺口分布 112/39/19/1/0；C1_TERMINATED）
**范围冻结：** 只解决"检索不可见 112"缺口；**不混入**大运/流年注入、prompt 改写；**不重启 C1**；**零 LLM API**；不评价答案准确率。

---

## 1. 目标与验收口径

**目标**：验证婚姻知识检索能否**稳定复现与冻结 silver 判据一致的检索结果**（结论限于工程可复现性，不声称语义正确性，§4.3）——对 35 道开发题中 112 项"检索不可见"doctrine 知识项，基于冻结的 **silver relevance judgment** 评估候选检索策略的召回、排序、注入长度与噪声，并冻结**可迁移的 retriever**（而非开发题预计算 bundle）。

| 编号 | 目标 | 验收口径 |
|---|---|---|
| 9A-G1 | 中文 FTS 替代检索策略 | 至少 2 个候选策略（含 FTS 替代方案）在固定 query 集上双跑字节一致、无漏检（对照 fts_behavior_probe.json 已知漏检词）；**结论限于工程可复现性，不声称语义相关性**（silver 同源限制，§4.3） |
| 9A-G2 | relevance judgment 冻结 | 策略实现与配置冻结 → 执行 S1–S5 形成 pooled candidates → 隐去策略来源 → **逐 (item_id, canonical_document_key) pair 盲标**（silver judgment，规则 SHA 冻结 + 10% 人类质检）→ judgment 冻结 |
| 9A-G3 | 召回覆盖率 | 按冻结 silver judgment 计算 **macro weighted_recall**（§5.1 口径）；**分母固定为全部 112 项**（no_gold_mass/UNJUDGEABLE 计未覆盖）；目标 ≥90%（双终态见 §8）；binary item coverage 分母同为 112 |
| 9A-G4 | 来源/去重/排序 | 每命中记录 canonical document key（KB=表+ID；classic=冻结路径+行号）；总排序键 `(-score, source_priority, category, stable_document_id)` 冻结；双跑一致 |
| 9A-G5 | 注入长度与噪声 | 每题 bundle 注入文本长度（字符数 + 估算 token）落盘；噪声（无关命中）按 **bundle_noise**（§5.1 口径）计算 |
| 9A-G6 | 冻结可迁移 retriever | retriever 实现 SHA + query extractor/schema + 同义词表 + ranking/truncation config + source snapshot SHA + treatment fingerprint（§6） |

**本阶段不评价**：答案准确率、模型行为变化、任何增强效果声明。

---

## 2. 输入与冻结基线（Phase 8 复用）

- 知识项清单：`docs/phase8/marriage-capability/required_knowledge.jsonl`（171 项；本阶段只处理 112 项检索不可见 doctrine 项）
- 审计证据：`knowledge_audit.jsonl`（每项 kb_queries query_id/hit_ids + classic_queries 定位摘录）——**仅作 candidate_pool，不作黄金标准**（P0-2 修订）
- KB 快照：`kb_snapshot.db`（六入口映射表，journal_mode=DELETE，只读）
- classic_texts 冻结版：`classic_texts_freeze.json` + git object（禁止读工作区漂移版）
- 查询集：`kb_query_set.json`（53 个聚合查询，199 query_specs 溯源）
- FTS 行为基线：`fts_behavior_probe.json`（红鸾 MATCH=0/LIKE=2 等）
- 检索语义纪律：query 词/同义词表/命中条文 ID 全部落盘；零命中记 `not_found_by_frozen_search`

### 2.1 查询规模（冻结分母）

- **53** 个去重聚合查询（kb_query_set.json）
- **112** 个检索不可见知识项
- **198** 个 item→query 引用（112 项的 query_specs 总数）
- 评估以 **item→query→candidate** 三层映射为分母：每 (item, query) 对独立计命中；聚合为 item 级覆盖率时按"该 item 任一 query 取回 relevant 条文"计。
- 映射与分母落盘：`docs/phase9a/retrieval/item_query_map.json`（112×198 全量，含 query_id 溯源）。

---

## 3. 候选检索策略（冻结评估对象）

| 策略 | 描述 | 已知风险 |
|---|---|---|
| S1 LIKE | 带 category 的 LIKE 子串匹配（bazi_kb.py search_gejue category 分支语义，现审计路径） | 无排序；单字词噪声 |
| S2 FTS5 单字展开 | 多字检索词拆为单字 token 的 FTS MATCH 组合（**待证伪**：unicode61 把连续中文作整体 token，单字 MATCH 通常同样不命中——实测'红鸾'与'鸾' MATCH 均为 0；保留为候选策略，描述不作预称修复） | 大概率无效；rank 语义变化 |
| S3 双字滑窗 | 中文字符 bigram 子串召回（query 与条文做双字交集打分） | 实现成本；打分口径需冻结 |
| S4 同义词扩展 | 冻结词表（结婚/婚期/成婚/姻缘/婚恋；红鸾/天喜 等）组合 S1 并查 | 词表需人工裁决并冻结 |
| S5 classic 联合 | S1 结果 + classic_texts 冻结版检索（已有 search_frozen 实现）合并去重 | 来源混合的排序口径 |

**评估协议（冻结）**：全部策略在同一固定 query 集（§2.1 的 198 个 item-query + fts_behavior_probe 3 个漏检词 + **单字探针（鸾/缘，实施时补录于检索探针集）** + 每入口 1 个探针）上执行；逐策略落盘命中（canonical key/来源/排序/去重后计数）；双跑字节一致门。

---

## 4. relevance judgment（P0-2 修订：盲标闭环，独立于任何单一策略）

**Phase 8 命中只称 `candidate_pool`，不得称黄金标准**（它们由 S1 类 LIKE 生成，与被评策略同源即循环）。

### 4.1 candidate_pool 口径（P0-1 修订：KB + classic 合并，标注主键 = item-document pair）

- **KB 源**：112 项 198 query_specs 的 `evidence.kb_queries[].hit_ids`，含重复 **2,902**，唯一条文 **546**（canonical key = 表名/入口名 + ID，如 `gejue:ss2_021`；裸 ID 去重为 537，其中 9 个 ID 在 shensha / shishen_combos / xiangyi 表间碰撞且为不同条文）。
- **classic 源**：`evidence.classic_queries[].hits`，含重复 **8,655**，唯一条文 **1,973**（canonical key = 冻结路径 + 行号 + record_id）。
- **合并 pool**：含重复 **11,557**。
- **标注主键（冻结）**：相关性是 item 特定的——同一条文对 item A relevant、对 item B partial、对 item C irrelevant。**标注主键 = (item_id, canonical_document_key)**，reviewer 必须逐 pair 标注，不得跨 item 复用标签。
- **pair 规模**：Phase 8 原始 pool 的唯一 item-document pair = **11,411**；S1–S5 top-10 pooling 后实际 pair 数**重新计算并记录**于 `silver_relevance_judgment.jsonl` 的 `pool_stats.actual_pair_count`（不得用全局 2,519 文档数代替）。
- 两源都参与评价（S1–S5 均可能命中两源），故按合并 pool 冻结。

### 4.2 盲标闭环流程（P0 修订：QC 样本冻结时机与顺序可执行）

1. **先冻结**全部策略代码、query 集、同义词表、ranking/truncation 配置及其 SHA（§6 主冻结产物）；**同时冻结 QC 参数**（抽样 seed、抽样算法、10% 比例、最大允许分歧率 10%）。
2. **执行 S1–S5**，取所有策略候选**并集**；pooling depth 冻结（**每策略每 (item,query) 取 top-10**，执行前确定，落盘于 ranking_config）；**重算实际 item-document pair 数并记录**。
3. **隐去候选来源策略**（reviewer 看不到命中来自哪个策略），对 pooled candidates 逐 **(item_id, canonical_document_key) pair 盲标**；检索开发者不得参与。
   **标签闭合枚举（冻结）**：`relevant / partially_relevant / irrelevant / uncertain`；`hard_negative` 是 `irrelevant` 的额外属性（仅标注于字面命中的无关候选，防策略仅靠字面匹配过门），不单列类别；每条标注附理由 + 标注规则版本 + 日期。
4. **冻结** `silver_relevance_judgment.jsonl`（逐 pair 标注 + 每 item 汇总 + `pool_stats.actual_pair_count`，SHA 落盘）。
5. **QC 门（pool 生成后立即执行，早于指标计算）**：基于 pooled pairs 按已冻结 seed/算法/比例**立即生成并冻结 QC 样本列表**（SHA 落盘）；人类复核执行**一致性审计**——**QC 只审计，不修改 silver 标签**；分歧率 >10% → 直接 `SILVER_RETRIEVAL_NOT_READY`。
6. **一次性计算**各策略指标（§5 weighted_recall / bundle_noise）——**仅在 QC 门通过后执行一次**，禁止看到结果后修改策略或 judgment。

### 4.3 reviewer 身份（执行条件冻结）

- **reviewer = 本地确定性规则初标（silver）**：基于冻结规则（同义词表共现 + category 一致性 + canonical key 溯源），规则代码 SHA 冻结；**不调用任何 LLM API**（零 API 硬约束）。
- **产物性质**：本阶段产出称 **silver relevance judgment**，**不得暗示完整人工 gold**；10% 人类抽查仅质检校正。
- **标注规则与检索策略同源风险（P0 修订）**：silver 规则与 S3/S4 检索策略依赖同类特征（同义词共现/类别一致性），因此本阶段终态**只证明检索器与冻结 silver 判据的一致性与工程可复现性，不得声称取回了语义正确的命理知识**；语义相关性声明必须依赖独立人工 gold（后续独立工作线）。
- **人工 QC（P0 修订：执行前冻结参数，样本列表 pool 后冻结）**：抽样 seed、抽样算法、10% 比例与**最大允许分歧率 10%**（人类复核与 silver 标签不一致占比）在策略执行前冻结于 QC 配置并 SHA 落盘；**QC 样本列表在 pool 生成后立即生成并冻结**（早于 silver 结果检查和指标计算）；**QC 只做一致性审计，不修改 silver 标签**；分歧率超过门槛 → 直接 `SILVER_RETRIEVAL_NOT_READY`，不得仅修正抽中标签后继续。
- 人工 gold 建立（如需）为独立后续工作线，不阻塞本阶段双终态判定。

---

## 5. 注入长度与噪声（指标拆分，P0-2 修订）

- **截断配置（冻结数值）**：
  - N（每条文截断）：**200 字符**（rule/original_text 前 200 字符；选择规则：断诀条文长度分布 P90 上界，实施时按实际分布复核并记录于 config）
  - M（每知识项最多条文数）：**5 条**（与 Phase 8 KB 入口 top_n 默认对齐）
  - K（每题注入总字符预算）：**1200 字符**（≈800 token，按中文字符 1.5 字符/token 估算；实施时按每题目数 × M × 平均条文长复核，超预算时按排序键截断）
- 长度落盘：每 bundle 字符数 + 估算 token 数（口径：中文字符 1.5 字符/token，落盘声明）。

### 5.1 指标定义（冻结；权重：relevant=1，partially_relevant=0.5）

- **weighted_recall_i（召回侧，主指标）**：策略取回的该 item 命中中 relevant 权重总和 / 该 item 在冻结 silver judgment 中的全部 relevant 权重总和。
- **bundle_noise_i（精确侧）**：该 item bundle 中 `irrelevant` 数 / bundle 中 relevant+partially_relevant+irrelevant 数。
- **binary item coverage（分母固定 112，P0 修订）**：该 item 是否取回 ≥1 条 relevant 权重>0 的条文（0/1）；**分母 = 全部 112 项**，no_gold_mass / UNJUDGEABLE 一律计 0（未覆盖），不得从分母剔除。
- **judgeable_item_rate（P0 修订，硬门）**：`(112 − |UNJUDGEABLE ∪ no_gold_mass|) / 112`（**集合并集**——UNJUDGEABLE 天然满足 gold mass=0，不得重复扣除），作为 READY 独立硬门（≥90%），防止不可判定项缩小有效分母。
- **gold mass=0 处理（冻结）**：item 在 silver judgment 中 relevant+partial 权重总和 = 0 → 该 item 不计入 weighted_recall 分子分母（其 binary coverage 计 0，见上），单独报告为 `no_gold_mass`。
- **uncertain 与 UNJUDGEABLE（冻结）**：item 的标注中 relevant+partial+irrelevant 数为 0（全部 uncertain）→ 该 item 进入 `UNJUDGEABLE`（其 binary coverage 计 0，见上），单独报告。
- **macro 口径**：macro weighted_recall = 非 UNJUDGEABLE 且 gold mass>0 的 item 的 weighted_recall_i 等权平均；**有效分母与 judgeable_item_rate 同时落盘**。
- **未标注新命中处理（冻结）**：策略执行后新命中但不在 pooled candidates 的条文标注为 `unlabeled`，不参与指标计算但计数落盘；若某 item 的取回命中全部为 unlabeled（≥1 条）则按 fail-closed 计该 item 未取回。
- **quarantine 命中（冻结）**：classic quarantine 文件命中**禁止进入最终 bundle**（只作佐证，与 Phase 8 语义一致）。

---

## 6. 产物与指纹（P0-4 修订：主冻结 retriever，开发题 bundle 仅作 replay 证据）

`docs/phase9a/retrieval/` 目录（新建）：

**主冻结产物（可迁移，服务未见密封题集）：**
- `retriever.py`（实现 SHA：git_canonical_lf）
- `query_extractor.py`（item→query 提取规则 + schema；SHA）
- `synonym_table.json`（冻结同义词表；JSON canonical SHA）
- `ranking_config.json`（排序键 `(-score, source_priority, category, stable_document_id)` + score 定义 + source_priority 映射；JSON canonical SHA）
- `truncation_config.json`（N/M/K 数值 + 选择规则；JSON canonical SHA）
- `source_snapshot_sha.json`（kb_snapshot.db + classic_texts_freeze 的 SHA 引用）
- `treatment_fingerprint.json`（上述全部 SHA 组合指纹——Phase 9B enhanced 臂的 treatment fingerprint 依据）
- `retrieval_eval.json`：逐策略 × 逐 (item,query) 命中/覆盖率/长度/噪声评估（JSON canonical）

**replay 证据（开发题 bundle，非主冻结）：**
- `retrieval_bundle_dev.json`：35 道开发题在选定策略下的注入 bundle（来源 + 条文 + 排序 + 去重），仅供 Phase 9A 结论复现与 Phase 9B 开发核对。

**文档与纪律：**
- `retrieval_strategy_notes.md`：策略对比结论与选定理由（含双终态判定依据）
- 冻结纪律：复用 Phase 8 的 p8_freeze 原子写与 manifest 模式；对账脚本增量（9A 节）
- 测试：`tests/test_phase9a_retrieval.py`（覆盖率对账、双跑字节一致、去重/排序稳定性、指纹复算）

---

## 7. 明确不做（冻结边界）

- 不调用任何 LLM/网络 API；不修改 `bazi_calculator.py`、`knowledge-base/`、`knowledge_base/`、prompt 模板。
- 不评价答案准确率；不在 44 道已知婚姻题上宣称提升。
- 不混入大运/流年/四化注入（那是注入缺失 39 + 计算缺失 19 的独立工作线）。
- 不重启 C1；不做 prompt 改写。
- 密封集就绪前不设计"增强效果"claim。
- **不把开发题 bundle 当作可迁移产物**；只冻结 retriever 及其配置（§6）。

---

## 8. 终态与完成定义（双终态 + 门槛冻结）

**终态（两种都允许 Phase 9A 完成；P0 修订：命名限定 silver）**：

- `SILVER_RETRIEVAL_READY`：同时满足——
  - **judgeable_item_rate ≥ 90%**（§5.1 口径，防分母逃逸）；
  - **macro weighted_recall ≥ 90%**（§5.1 口径：非 UNJUDGEABLE 且 gold mass>0 的 item 等权平均）；
  - **macro bundle_noise ≤ 20%**（§5.1 口径）；
  - **binary item coverage ≥ 90%**（分母固定 112，no_gold_mass/UNJUDGEABLE 计 0）；
  - 题级最坏护栏：任一 item 的 bundle 若全部命中均为 irrelevant，则该 item 计失败（计入未取回）；
  - 人工 QC 分歧率 ≤ 10%（§4.3 冻结门槛）；
  - 排序/去重/指纹全部对账通过。
  **结论限定**：SILVER_RETRIEVAL_READY 只证明检索器与冻结 silver 判据的一致性和工程可复现性，**不构成语义相关性或检索效果的声明**。
- `SILVER_RETRIEVAL_NOT_READY`：未达上述任一门槛——保留完整评估结果与失败原因（逐项未取回清单 + UNJUDGEABLE/no_gold_mass/QC 分歧明细），**不得为过门而修改策略或 judgment**；结论闭合，转入设计修订。

**完成定义**：
1. 至少 2 个候选策略完成评估，双跑字节一致；FTS 漏检词在替代策略下无漏检。
2. silver_relevance_judgment.jsonl 冻结（逐 item-document pair 盲标，`pool_stats.actual_pair_count` 记录实际值，SHA 落盘；检索开发者未参与）。
3. retriever 及全部配置冻结（§6 主冻结产物），treatment_fingerprint 可复算。
4. 注入长度与噪声按冻结配置落盘，给出与预算的权衡结论。
5. 终态为 SILVER_RETRIEVAL_READY 或 SILVER_RETRIEVAL_NOT_READY 之一，结论闭合。
6. 全程零 API、零生产代码改动。

---

## 附录 A：密封婚姻集采集裁决点（用户裁决，已落盘）

采集前置条件（设计 v1.3.1 §P8-4 冻结要求）：

| 裁决点 | 选项/要求 | 状态 |
|---|---|---|
| A1 数据来源 | 自有/内部命盘数据 | **已裁决（2026-08-13）** |
| A2 许可证与合规 | **PENDING_VERIFICATION**（归属盘点完成前不得称"无风险"） | 已裁决，待盘点 |
| A3 curator 任命 | AI 代理担任 curator，人类复核真值；**权限隔离机制见 sealed_acquisition_decision.md v1.1** | **已裁决（2026-08-13）** |
| A4 真值双人核验 | AI curator 一审 + 人类复核，分歧记录落盘 | 机制冻结，人选已定 |
| A5 规模与平衡 | ≥20 新盘 × ≥3 题；应期/状态/多段均衡；A/B/C/D 近似均匀 | 已冻结 |
| A6 去重 | 与 Phase 7 全部 32 盘出生信息级去重 | 已冻结 |
| A7 访问日志 | 由权限边界产生（非代理自报）；谁、何时、看过什么范围；泄漏降级为确认集 | 已冻结 |

**裁决记录**：详见 `docs/superpowers/specs/sealed_acquisition_decision.md`（唯一事实源；v1.1 修订权限隔离方案）。
