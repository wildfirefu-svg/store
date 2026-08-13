# Phase 9A 设计：婚姻知识检索可行性（零 API）

**日期：** 2026-08-13
**状态：** v1.0（草案，待用户过审）
**前置：** Phase 8 已冻结（`docs/phase8/CLOSURE.md`；缺口分布 112/39/19/1/0；C1_TERMINATED）
**范围冻结：** 只解决"检索不可见 112"缺口；**不混入**大运/流年注入、prompt 改写；**不重启 C1**；**零 LLM API**；不评价答案准确率。

---

## 1. 目标与验收口径

**目标**：验证婚姻知识检索能否**稳定取回正确知识**——对 35 道开发题中 112 项"检索不可见"doctrine 知识项，评估候选检索策略的召回覆盖率、来源/去重/排序、注入长度与噪声，并输出冻结的 retrieval bundle 与指纹。

| 编号 | 目标 | 验收口径 |
|---|---|---|
| 9A-G1 | 中文 FTS 替代检索策略 | 至少 2 个候选策略（含 FTS 替代方案）在固定 query 集上双跑字节一致、无漏检（对照 fts_behavior_probe.json 已知漏检词） |
| 9A-G2 | required knowledge 召回覆盖率 | 112 项检索不可见知识项中，每项至少取回 1 条相关条文的比例（目标 ≥90%）；取回结果与 KB 快照/classic 冻结版命中对账 |
| 9A-G3 | 来源/去重/排序 | 每命中记录来源（kb_snapshot.db 表 / classic_texts 冻结文件）、(file,line) 去重、稳定排序（双跑一致） |
| 9A-G4 | 注入长度与噪声 | 每题 bundle 注入文本长度（字符数 + 估算 token）落盘；噪声（无关命中）比例抽样评估 |
| 9A-G5 | 冻结 bundle + 指纹 | `retrieval_bundle.json`（JSON canonical SHA）+ 策略指纹 + manifest 冻结 |

**本阶段不评价**：答案准确率、模型行为变化、任何增强效果声明。

---

## 2. 输入与冻结基线（Phase 8 复用）

- 知识项清单：`docs/phase8/marriage-capability/required_knowledge.jsonl`（171 项；本阶段只处理 112 项检索不可见 doctrine 项）
- 审计证据：`knowledge_audit.jsonl`（每项含 kb_queries query_id/hit_ids + classic_queries 定位摘录——作为召回黄金标准的候选集）
- KB 快照：`kb_snapshot.db`（六入口映射表，journal_mode=DELETE，只读）
- classic_texts 冻结版：`classic_texts_freeze.json` + git object（禁止读工作区漂移版）
- 查询集：`kb_query_set.json`（53 个聚合查询，199 query_specs 溯源）
- FTS 行为基线：`fts_behavior_probe.json`（红鸾 MATCH=0/LIKE=2 等）
- 检索语义纪律：query 词/同义词表/命中条文 ID 全部落盘；零命中记 `not_found_by_frozen_search`

---

## 3. 候选检索策略（冻结评估对象）

| 策略 | 描述 | 已知风险 |
|---|---|---|
| S1 LIKE | 带 category 的 LIKE 子串匹配（bazi_kb.py search_gejue category 分支语义，现审计路径） | 无排序；单字词噪声 |
| S2 FTS5 单字展开 | 把多字检索词拆为单字 token 的 FTS MATCH 组合（`"结" OR "婚"` 短语结构），修复 unicode61 多字漏检 | 召回膨胀；rank 语义变化 |
| S3 双字滑窗 | 中文字符 bigram 子串召回（query 与条文做双字交集打分） | 实现成本；打分口径需冻结 |
| S4 同义词扩展 | 冻结词表（结婚/婚期/成婚/姻缘/婚恋；红鸾/天喜 等）组合 S1 并查 | 词表需人工裁决并冻结 |
| S5 classic 联合 | S1 结果 + classic_texts 冻结版检索（已有 search_frozen 实现）合并去重 | 来源混合的排序口径 |

**评估协议（冻结）**：全部策略在同一固定 query 集（kb_query_set 的 112 项相关 query + fts_behavior_probe 的 3 个漏检词 + 每入口 1 个探针）上执行；逐策略落盘命中（ID/来源/排序/去重后计数）；双跑字节一致门。

---

## 4. 召回黄金标准与覆盖率口径

- **黄金标准候选集**：`knowledge_audit.jsonl` 中每 doctrine 项的 `evidence.kb_queries[].hit_ids` + `classic_queries[].hits`（Phase 8 已冻结的逐项证据）。
- **覆盖率定义**：策略取回条文与黄金标准候选集的**条文 ID 交集**（同源）或**同 (file,line)**（classic）非空 → 该知识项"取回相关条文"。
- **人工抽查**：覆盖率结果按 10% 抽样人工核验"取回条文是否确实相关"（防黄金标准自身噪声）；核验记录落盘。
- 112 项中未取回项的清单必须附逐项 `not_found_by_frozen_search` 标记与原因。

---

## 5. 注入长度与噪声

- 每知识项 bundle = 取回条文的 rule/original_text 字段（截断策略冻结：每条文 ≤N 字符，每项 ≤M 条，每题 ≤K 字符）。
- 长度落盘：每 bundle 字符数 + 估算 token 数（按中文字符近似 1 token/1.5 字符的口径落盘，口径冻结）。
- 噪声评估：按知识项抽 10% 人工标注"相关/部分相关/无关"，噪声率 = 无关/(相关+部分相关+无关)；噪声率与注入预算冲突时给出权衡建议（截断/排序/阈值）。

---

## 6. 产物与指纹（冻结）

- `docs/phase9a/retrieval/` 目录（新建）：
  - `retrieval_eval.json`：逐策略 × 逐知识项命中/覆盖率/长度/噪声评估（JSON canonical）
  - `retrieval_bundle.json`：选定策略（或策略组合）下每题的最终注入 bundle（来源 + 条文 + 排序 + 去重；JSON canonical）
  - `retrieval_strategy_notes.md`：策略对比结论与选定理由
  - `retrieval_fingerprint.json`：bundle 的 SHA 四策略 + 策略指纹（query 集 SHA + 词表 SHA + 截断参数）
- 冻结纪律：复用 Phase 8 的 p8_freeze 原子写与 manifest 模式；对账脚本增量（9A 节）。
- 测试：`tests/test_phase9a_retrieval.py`（覆盖率对账、双跑字节一致、去重/排序稳定性、指纹复算）。

---

## 7. 明确不做（冻结边界）

- 不调用任何 LLM/网络 API；不修改 `bazi_calculator.py`、`knowledge-base/`、`knowledge_base/`、prompt 模板。
- 不评价答案准确率；不在 44 道已知婚姻题上宣称提升。
- 不混入大运/流年/四化注入（那是注入缺失 39 + 计算缺失 19 的独立工作线）。
- 不重启 C1；不做 prompt 改写。
- 密封集就绪前不设计"增强效果"claim。

---

## 8. 完成定义

1. 至少 2 个候选策略完成评估，双跑字节一致；FTS 漏检词在替代策略下无漏检。
2. 112 项召回覆盖率 ≥90%（含人工抽查 10%），未取回项逐项记录原因。
3. retrieval_bundle.json 冻结（SHA 四策略 + 指纹），对账 exit 0。
4. 注入长度与噪声落盘，给出与预算的权衡结论。
5. 全程零 API、零生产代码改动。

---

## 附录 A：密封婚姻集采集裁决点（用户裁决，已落盘）

采集前置条件（设计 v1.3.1 §P8-4 冻结要求）：

| 裁决点 | 选项/要求 | 状态 |
|---|---|---|
| A1 数据来源 | 自有/内部命盘数据 | **已裁决（2026-08-13）** |
| A2 许可证与合规 | 自有数据无再发布风险，归属盘点待 curator 启动时确认 | **已裁决** |
| A3 curator 任命 | AI 代理担任 curator，人类复核真值 | **已裁决（2026-08-13）** |
| A4 真值双人核验 | AI curator 一审 + 人类复核，分歧记录落盘 | 机制冻结，人选已定 |
| A5 规模与平衡 | ≥20 新盘 × ≥3 题；应期/状态/多段均衡；A/B/C/D 近似均匀 | 已冻结 |
| A6 去重 | 与 Phase 7 全部 32 盘出生信息级去重 | 已冻结 |
| A7 访问日志 | 谁、何时、看过什么范围；泄漏降级为确认集 | 已冻结 |

**裁决记录**：详见 `docs/superpowers/specs/sealed_acquisition_decision.md`（唯一事实源）。
