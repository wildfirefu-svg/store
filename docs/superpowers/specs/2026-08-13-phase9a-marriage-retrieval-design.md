# Phase 9A 设计：婚姻知识检索可行性（零 API）

**日期：** 2026-08-13
**状态：** v1.1（NEEDS_REVISION 修订：独立 relevance judgment、retriever 主冻结、双终态、规模/排序/截断数值化）
**前置：** Phase 8 已冻结（`docs/phase8/CLOSURE.md`，最终 HEAD `0f74de2`；缺口分布 112/39/19/1/0；C1_TERMINATED）
**范围冻结：** 只解决"检索不可见 112"缺口；**不混入**大运/流年注入、prompt 改写；**不重启 C1**；**零 LLM API**；不评价答案准确率。

---

## 1. 目标与验收口径

**目标**：验证婚姻知识检索能否**稳定取回正确知识**——对 35 道开发题中 112 项"检索不可见"doctrine 知识项，基于**独立 relevance judgment**评估候选检索策略的召回、排序、注入长度与噪声，并冻结**可迁移的 retriever**（而非开发题预计算 bundle）。

| 编号 | 目标 | 验收口径 |
|---|---|---|
| 9A-G1 | 中文 FTS 替代检索策略 | 至少 2 个候选策略（含 FTS 替代方案）在固定 query 集上双跑字节一致、无漏检（对照 fts_behavior_probe.json 已知漏检词） |
| 9A-G2 | relevance judgment 冻结 | 112 项在策略执行前由独立 reviewer 完成逐项裁决（relevant IDs / hard negatives / 理由 / reviewer / SHA），检索开发者不参与 |
| 9A-G3 | 召回覆盖率 | 按冻结 relevance judgment 计算：每项取回 ≥1 条 relevant 条文的比例；目标 ≥90%（双终态见 §8） |
| 9A-G4 | 来源/去重/排序 | 每命中记录 canonical document key（KB=表+ID；classic=冻结路径+行号）；总排序键 `(-score, source_priority, category, stable_document_id)` 冻结；双跑一致 |
| 9A-G5 | 注入长度与噪声 | 每题 bundle 注入文本长度（字符数 + 估算 token）落盘；噪声（无关命中）比例按 relevance judgment 计算 |
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
| S2 FTS5 单字展开 | 多字检索词拆为单字 token 的 FTS MATCH 组合，修复 unicode61 多字漏检 | 召回膨胀；rank 语义变化 |
| S3 双字滑窗 | 中文字符 bigram 子串召回（query 与条文做双字交集打分） | 实现成本；打分口径需冻结 |
| S4 同义词扩展 | 冻结词表（结婚/婚期/成婚/姻缘/婚恋；红鸾/天喜 等）组合 S1 并查 | 词表需人工裁决并冻结 |
| S5 classic 联合 | S1 结果 + classic_texts 冻结版检索（已有 search_frozen 实现）合并去重 | 来源混合的排序口径 |

**评估协议（冻结）**：全部策略在同一固定 query 集（§2.1 的 198 个 item-query + fts_behavior_probe 3 个漏检词 + 每入口 1 个探针）上执行；逐策略落盘命中（canonical key/来源/排序/去重后计数）；双跑字节一致门。

---

## 4. relevance judgment（P0-2 修订：独立于策略的黄金标准）

**Phase 8 命中只称 `candidate_pool`**（11557 条跨 query 候选，含重复），不得称黄金标准——它们由 S1 类 LIKE 生成，与被评策略同源即循环。

建立独立 relevance judgment 的流程（**策略执行前冻结**）：

1. **独立 reviewer**：relevance judgment 由独立 reviewer 完成，**检索开发者不得参与**（角色分离：开发者实现策略，reviewer 只裁决相关性）。
2. **逐项裁决**：112 项 × candidate_pool 去重后的候选条文，reviewer 逐条标注：
   - `relevant`：该条文确实回答/支撑该知识项所需学理；
   - `hard_negative`：明确无关但字面命中（防止策略仅靠字面匹配过门）；
   - 判断理由（一句话）；
   - reviewer 标识 + 裁决日期。
3. **冻结**：`relevance_judgment.jsonl`（JSONL canonical，SHA 落盘；含 112 项 × 候选的完整标注 + 每项 relevant/hard_negative 汇总）。
4. **质检**：10% 人类抽查仅作质检（核对 reviewer 标注质量），**不代替黄金标准建立**。
5. 覆盖率计算只依据冻结的 relevance_judgment.jsonl；未取回项清单附 `not_found_by_frozen_search` 标记与原因。

---

## 5. 注入长度与噪声（数值化，P0-2/中优先级修订）

- **截断配置（冻结数值）**：
  - N（每条文截断）：**200 字符**（rule/original_text 前 200 字符；选择规则：断诀条文长度分布 P90 上界，实施时按实际分布复核并记录于 config）
  - M（每知识项最多条文数）：**5 条**（与 Phase 8 KB 入口 top_n 默认对齐）
  - K（每题注入总字符预算）：**1200 字符**（≈800 token，按中文字符 1.5 字符/token 估算；实施时按每题目数 × M × 平均条文长复核，超预算时按排序键截断）
- 长度落盘：每 bundle 字符数 + 估算 token 数（口径：中文字符 1.5 字符/token，落盘声明）。
- 噪声率：按 relevance_judgment 统计每 item bundle 中 non-relevant 比例；噪声率与预算冲突时给出权衡建议（截断/排序/阈值），作为 RETRIEVAL_READY 判定的输入之一。

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

## 8. 终态与完成定义（中优先级修订：双终态）

**终态（两种都允许 Phase 9A 完成）**：

- `RETRIEVAL_READY`：112 项 relevance-judged 覆盖率 ≥90%，且噪声率 ≤ 预算阈值（预算阈值在实施开始前冻结于 truncation_config 的附注），排序/去重/指纹全部对账通过。
- `RETRIEVAL_NOT_READY`：未达上述门——保留完整评估结果与失败原因（逐项未取回清单），**不得为过门而修改策略或 relevance judgment**；结论闭合，转入设计修订。

**完成定义**：
1. 至少 2 个候选策略完成评估，双跑字节一致；FTS 漏检词在替代策略下无漏检。
2. relevance_judgment.jsonl 冻结（112 项全量，SHA 落盘；检索开发者未参与）。
3. retriever 及全部配置冻结（§6 主冻结产物），treatment_fingerprint 可复算。
4. 注入长度与噪声按冻结配置落盘，给出与预算的权衡结论。
5. 终态为 RETRIEVAL_READY 或 RETRIEVAL_NOT_READY 之一，结论闭合。
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
