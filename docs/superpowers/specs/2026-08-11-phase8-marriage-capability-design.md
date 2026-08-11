# Phase 8 设计：婚姻类能力改进前提分析（零 API）

**日期：** 2026-08-11
**状态：** v1.3（局部复审修订：KB 冻结改最小 SQLite 快照（方案 A，查询前全量导出 + 等价性测试）、`missing_input` 改判 undetermined+reason、P8-2A 分析纪律、classic_texts 文件级 allowlist、SHA 四策略）→ v1.3.1（NEEDS_FIX 修订：P8-5 配对契约重写为同 case/同顺序/单 treatment factor + 允许不同/必须相同字段集合；P8-1.5 探针排除 `current_*` wall-clock 字段 + 双跑字节一致性测试）
**输入：** Phase 7 基线归档（`docs/phase7/phase7-mingli-v4flash-nt-20260811-r2/`）+ 错误归因 v2.1（`docs/phase7/error-analysis/`，commit `28aacf0`）
**核心原则（用户冻结）：先确定婚姻错误究竟缺什么，再决定改知识库、排盘引擎还是 prompt。直接添加婚姻规则很容易对 44 道已知题过拟合。**

---

## 1. 背景与动机

Phase 7 错误归因已冻结的稳固结论：

- 婚姻类是唯一统计显著短板：38/44 错（p=0.0008，18 项 Bonferroni 后仍显著）；其中 knowledge 35、option_confusion 3。
- 全题型塌陷，细粒度题型（多段/离婚 0/7、事件反查 0/3、应期 1/10）错误最干净。
- 注入链无结构性故障证据；但内容质量与模型利用深度未排除。
- C1（结论-选项一致性）直接可修复 3 题，上限 +1.875pp，只配作附带项。

**本阶段不产出任何 prompt 改动**，只产出"缺什么"的判定证据与后续实验的前置资产。

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 35 道婚姻 knowledge 错题的亚型拆分 | 机械规则落盘、逐题结果可复算；主/副亚型记录 |
| G2 | 逐题逐知识项可得性审计 | 缺口归类五类（知识缺失 / 检索不可见 / 计算缺失 / 注入缺失 / 模型未利用）+ `undetermined` 单列；逐项证据落盘；题级多标签 + 知识项级双口径汇总 |
| G3 | C1 一致性转换器历史回放筛选 | 160 题逐题 `old/new/expected/change_result`（含 `changed_wrong_to_wrong`）落盘；终态 `C1_PASS` 或 `C1_TERMINATED` 均允许阶段完成 |
| G4 | 密封婚姻题集 + 非婚姻护栏集规约 | 来源/规模/真值/许可/去重/选项平衡/power 检查/角色隔离冻结（采集另批） |
| G5 | 配对实验设计框架 | 单臂单层；门槛与护栏的冻结时点与形式写入本设计 |

### 2.2 非目标

- 不修改 prompt / 知识库 / 排盘引擎 / 任何生产代码；
- 不调用 LLM API；
- 不采集新题（P8-4 只冻结规约，采集执行需用户另行批准来源与预算）；
- 不做任何"婚姻规则"编写——本阶段输出的是缺口判定，不是补丁。

## 3. 已核实的来源事实（审计设计的地基）

| 来源 | 内容 | 婚姻相关覆盖 |
|---|---|---|
| 排盘引擎（`bazi_calculator.py`） | `calculate_dayun()`（`:813`）、`calculate_liunian()`（`:1915`）存在 | **函数存在 ≠ 35 题可可靠计算**：`calculate_liunian` 是从传入年份向后生成若干年，不是历史目标年份分析接口；四化现有实现基于出生年干排本命四化，逐目标流年四化接口未证实。逐项可否计算必须由 P8-1.5 探针实测 |
| 官方 astro（`fortune_api_results.json`） | 十二宫星名（含夫妻宫）、chinese_date、五行局 | 无大运序列、无流年映射、无四化 |
| 知识库（`knowledge-base/bazi_kb.db`） | gejue 976 / shishen_combos 1425 / ziwei_patterns 60 / shensha 81；**仅 `gejue_fts` 为 FTS5 虚表，其余为普通表** | 婚姻条文存在性待审计；蒸馏线 classic_texts 规则为独立工作线 |
| 当前 prompt（官方 CoT 复刻） | birth_info 原文 + astro 块 + CoT 指令 | 零婚姻规则、零大运流年序列、零四化表；官方 profile 无 RAG 注入（已核实） |

**初步假设（待探针与审计证实/证伪）**：婚姻应期/多段题所需的大运流年序列与四化可能"计算可得但未注入"；婚姻学理条文可能"存在但检索不可见"。不得直接采信。

**输入可得性约束（P8-2 前置，冻结）**：

- `knowledge-base/bazi_kb.db` 被 `.gitignore` 排除，fresh clone 不可得；`knowledge_base/classic_texts/` 存在并行未提交变更。因此：
  - **KB 冻结方式（选定方案 A：最小冻结 SQLite 快照）**：审计开始时、**任何查询之前**，把全部相关表（`gejue` 及 `gejue_fts` FTS5 虚表与索引、`shishen_combos`、`ziwei_patterns`、`shensha`）按**原表结构 + 全部行 + 全部可搜索字段**导出为 `docs/phase8/marriage-capability/kb_snapshot.db`（SQLite 文件，raw-byte SHA 落盘）；检索对该快照执行，与原库同 query 函数同语义（gejue 走 FTS5 MATCH，其余表为普通表查询——不得统称 FTS）。**禁止按查询结果只导出"相关字段/相关行"**——快照先于查询、全量导出。**快照等价性测试（冻结）**：固定查询集（审计用全部查询词）在原库与快照上分别执行，命中条文 ID、顺序、行数必须完全一致；同时核对 FTS shadow tables、表 schema 与行数，测试脚本与结果落盘。
  - **classic_texts 冻结方式**：冻结**文件 allowlist + 每文件 blob SHA + 可达 commit**（审计开始时落盘；`git show <commit>:<path>` 只能读具体文件，故冻结到文件粒度），读取一律走 git object，**禁止读工作区漂移版本**。

## 4. 任务分解（三阶段链 + 对账）

**阶段顺序（冻结）**：P8-1（亚型）→ **P8-2A（需求拆解，先于探针）** → P8-1.5（计算探针）→ P8-2B（四源核对 + 缺口归类）→ P8-3（C1 回放）→ P8-4/P8-5（规约/框架）。相邻阶段间做 case_id、知识项 ID、输入 SHA 三方对账，对账脚本落盘。

### P8-1 亚型拆分（35 题）

- 输入：`error_classification.jsonl` 中 `category=婚姻 且 error_type=knowledge` 的 35 题。
- 亚型枚举（冻结）：`婚姻状态` / `结婚离婚应期` / `多段婚姻` / `配偶特征` / `事件反查`。
- **亚型交叉处理（冻结）**：每题记 `primary_subtype` + `secondary_subtypes`；主亚型优先级：`多段婚姻 > 事件反查 > 配偶特征 > 结婚离婚应期 > 婚姻状态`（粒度越细优先级越高）。
- 复用 Phase 7 机械 bucket 规则映射（状况描述→婚姻状态、应期→结婚离婚应期、多段/离婚细节→多段婚姻、事件反查→事件反查、配偶特征→配偶特征；感情细节与其他逐题归并，依据落盘）。
- 产出 `subtype_split.json`，分布与 Phase 7 对账（35 = 主亚型之和）。

### P8-2A 需求拆解（先于探针）

- 对每题生成答对所需的最小知识/计算项清单，产出 **`required_knowledge.jsonl`**（35 行；每项有稳定 `item_id`：`{case_id}#k{序号}`，标注 `kind: computation | doctrine`）。
- **分析纪律（冻结）**：需求拆解属人工分析——分析者可看题目、选项与真值，**不得参考模型 raw_answer**（防止把模型错误反向写进"最小需求清单"）；须经第二人复核或一致性裁决，裁决记录落盘（`required_knowledge_review.md`：分歧点与裁决理由）。
- 该文件**先冻结（SHA 落盘）再进探针**；探针与归类只引用 `item_id`，不得改写需求清单。确需修订时整文件版本化重冻结并对账。

### P8-1.5 计算能力实测探针

对 P8-2A 中 `kind=computation` 的每项**实际调用引擎**：

- 记录：输入完整性（birth_info 字段是否够）、目标年份/范围、引擎输出或失败原因；
- 每项产出 **`computability_status` 四态（冻结）**：`computable / missing_input / no_interface / semantic_gap`；
- **输出字段稳定性（冻结，已核实 `bazi_calculator.py:896-912` 的 `date.today()` 依赖）**：探针记录引擎输出时**只保留稳定字段**（`direction`、`starting_age`、`days_to_junction`、`pillars` 等），**明确排除全部 `current_*` 字段**（`current_year`/`current_age`/`current_pillar` 由 wall clock 派生，跨年复算会漂移）；不修改生产引擎；
- **字节一致性测试（冻结）**：探针重复运行两次，产出逐字节一致（SHA 相同）方可入档；
- 产出 `computability_probe.json`（按 `item_id` 索引 + 稳定字段输出摘要）。

### P8-2B 四源核对与缺口归类

**schema 分层（冻结，消除枚举不闭合）**：

- `computability_status`：四态（仅 computation 项，来自探针）；
- `gap_class`：五类 或 `undetermined`；
- 映射规则（冻结）：
  - `no_interface` → `计算缺失`（引擎能力/接口缺失）；
  - `missing_input` → `undetermined` 且 `undetermined_reason=input_missing`（数据/adapter 输入缺失，改进层与引擎无关，不得计入"计算缺失"误导 P8-5 选层）；
  - `semantic_gap` → `undetermined`（**不得计入五类因果分布**，报告中单列）；
  - `computable` 且未注入 → `注入缺失`；`computable` 且已注入 → 进入"模型未利用"判定；
  - doctrine 项无 computability_status，按 KB/astro/prompt 核对结果归 `检索不可见 / 知识缺失 / 模型未利用`；
- **多标签**：每个知识项独立标注；每题允许**多个 `gap_classes`**；`primary_gap` 仅从**已确定**的缺口类派生（题内全为 undetermined 时 primary_gap=undetermined）；优先级冻结 `计算缺失 > 注入缺失 > 检索不可见 > 知识缺失 > 模型未利用`，并列取高优先级并写 `primary_gap_reason`；
- 汇总双口径：题级多标签计数 + 知识项级计数；五类计数与 undetermined 分列，分母对账（知识项总数 = 五类 + undetermined）。
- KB 检索纪律（冻结）：对 §3 冻结的快照检索；查询词、扩展同义词表、命中条文 ID 全部落盘；**零命中只记 `not_found_by_frozen_search`**；标"知识缺失"需附快照检索记录 + classic_texts（git object 冻结版）核查记录。
- "模型未利用"必须引用 prompt 中确已存在的字段证据。
- 产出 `knowledge_audit.jsonl`（35 行）+ `knowledge_audit_summary.md`。

### P8-3 C1 一致性转换器：历史回放可行性筛选（含失败终态）

**定位（冻结）**：检测器在已知 3 个目标样本上设计，存在循环验证——本阶段结果最多称"历史回放可行性筛选"，回放通过仅允许进入密封集验证，不得直接接入正式 runner；推广门必须在未见密封输出上通过（属后续实验 spec）。

- **转换器完整性**：检测（正文结论→选项映射）+ 候选 letter 提取 + 实际重选；
- **逐题评估**：160 题全部记录 `old_letter / new_letter / expected / change_result`；`change_result` 枚举（冻结）：`improved / harmed / unchanged / changed_wrong_to_wrong`（错→错改写不得藏入 unchanged）；
- **终态（冻结，两种都允许 Phase 8 完成）**：
  - `C1_PASS`：0018/0034/0073 全 improved 且 harmed=0（全部 160 题）→ 允许进入未来密封验证；
  - `C1_TERMINATED`：未达上述门 → 保留完整回放结果，冻结终止结论，C1 线关闭；
  - **完成定义不得强迫假设成功**（防调规则过门）。
- 产出 `c1_detector.py` + `c1_detector_eval.json`。

### P8-4 密封婚姻题集 + 非婚姻护栏集规约（只冻结规约，不采集）

**婚姻密封集**：

- 来源独立于 MingLi-Bench 32 盘；与 Phase 7 全部 32 盘逐盘去重（出生信息级比对）；
- 真值来源与核验方式、许可风险：采集前由用户裁决并落盘；
- 规模：目标 ≥20 盘 × 每盘 ≥3 道婚姻题（应期/状态/多段均衡覆盖塌陷亚型）；**power 检查口径（冻结）**：以**最小有意义提升**（pp 阈值）为效应量、取保守效应范围、按**命盘内聚类**（同盘题非独立）估算——不得以 Phase 7 婚姻错误率缺口当作增强措施的预期收益；
- 选项构造规范与答案位置平衡（A/B/C/D 近似均匀）；
- **角色隔离（冻结，替代"任何人看过即降级"）**：curator（策划/真值裁决者）可见题集但**不得参与任何改进设计与实验操作**；developer/operator 不可见题目内容；建立访问日志（谁、何时、看过什么范围），泄漏即降级为确认集并如实记录；
- 内部再分按盘整体切分（命盘级裁决）。

**非婚姻护栏集（P8-5 回退护栏的载体，冻结）**：

- 首选：Phase 7 的 **116 道非婚姻题**作为公开确认护栏集（零采集成本，已看过 → 只能称确认性护栏）；
- 是否另建密封非婚姻配对集由用户在采集裁决时一并定；
- **用途限定**：护栏集只承担非婚姻退化检测，不与婚姻集混算主指标。

### P8-5 配对实验设计框架（本阶段只冻结框架）

- 形态（配对契约，冻结）：baseline 与 enhanced 使用**完全相同的 case、顺序与调度**；baseline 保持 Phase 7 冻结协议且其协议指纹**必须匹配 Phase 7 归档值**；enhanced 只允许**一个预声明 treatment factor** 变化（注入 / 检索 / prompt 之一），全部非 treatment 字段逐项相等；enhanced 侧额外记录 `treatment_type`、`treatment_config`、`treatment_fingerprint`（指纹按 treatment 预期变化，其余指纹不变）；manifest 明确列出**允许不同字段集合**与**必须相同字段集合**。多个候选方向分别成臂、分别实验，**不得把多层增强打包后仍称"唯一变量"**；臂集合由 P8-2B 题级多标签分布决定；
- **指纹组成冻结（v1.3.1 增补；仓库无现成 `protocol_fingerprint` 字段，writing-plans 必须按本条精确定义）**：
  - baseline 必须与 Phase 7 归档相同：profile、prompt fingerprint、provider/model、thinking_mode、temperature、method 及其余推理参数；
  - 配对两臂必须相同：dataset / case / 顺序 / 调度及全部非 treatment 字段；
  - 允许变化：预声明 treatment 字段及对应 `treatment_fingerprint`；
  - Phase 8 新编排代码使用**独立的 `phase8_code_fingerprint`**（范围在实施计划中列文件冻结）；**不得**机械要求整个 `phase7_code_fingerprint` 与历史值相同（新增 Phase 8 编排代码必然改变九文件范围外的代码面，而 `phase7_code_fingerprint` 覆盖的九文件若含被 treatment 合法修改的文件，按 treatment 记录漂移理由）。
- **冻结时点**：提升门槛（最小收益 pp）、回退护栏（护栏集最大允许退化）、样本量与区间估计方法，在密封集就绪后的实验 spec 中冻结并过审，**先于任何实验运行**；
- 评估协议沿用 Phase 7 硬门与证据链（git-canonical-lf SHA、完整性门禁适配新集）。

## 5. 反过拟合护栏（冻结）

1. 44 道已知婚姻题只能用于开发与确认；任何改进的"效果声明"必须以密封集为准。
2. P8-2B 的缺口归类若指向"加规则"，规则内容必须来自学理来源（KB 快照/经典 git object），**禁止从 44 题的错误样例反推规则**。
3. 每个候选改进必须声明预期获益的亚型与机制，不允许"试试看"式改动。
4. C1 历史回放结果不得直接部署（§P8-3 定位）。

## 6. 产物完整性与可复算纪律（冻结）

- **SHA 策略按文件类型分列（冻结，消除"canonical 与 git-canonical-lf"措辞冲突）**：
  - JSON：`canonical JSON SHA`（`sort_keys=True, ensure_ascii=False, separators=(",", ":")`，带末尾换行 `\n`）；
  - JSONL：逐行 canonical JSON、**保持冻结行序**、每行及文件末尾均 `\n`；
  - SQLite/其他二进制：**raw-byte SHA**；
  - 普通 Git 文本产物：`git-canonical-lf`；
- 记录输入文件 SHA、脚本 SHA、KB 快照 raw-byte SHA、classic_texts 冻结 allowlist（commit + 每文件 blob SHA）；
- 附对账脚本（复算入口）；
- 阶段间对账：case_id / item_id / 输入 SHA 三方核对，脚本落盘。

## 7. 产出物清单

```text
docs/phase8/marriage-capability/
├── subtype_split.json          # P8-1（主/副亚型 + 归并依据）
├── required_knowledge.jsonl    # P8-2A（先冻结，item_id 稳定）
├── required_knowledge_review.md # P8-2A 第二人复核/一致性裁决记录
├── computability_probe.json    # P8-1.5（item_id 索引，四态实测）
├── kb_snapshot.db              # §3 KB 最小冻结 SQLite 快照（raw-byte SHA 落盘）
├── classic_texts_freeze.json   # §3 文件 allowlist + 每文件 blob SHA + 可达 commit
├── knowledge_audit.jsonl       # P8-2B 逐题审计（35 行，多标签）
├── knowledge_audit_summary.md  # P8-2B 汇总（双口径 + undetermined 单列）
├── c1_detector.py              # P8-3 转换器（纯文本规则）
├── c1_detector_eval.json       # P8-3 回放评估（四态 change_result）
├── sealed_marriageset_spec.md  # P8-4 双集规约
└── provenance.json             # §6 全部 SHA 与对账入口
```

## 8. 完成定义

1. 本设计 v1.3.1 过审；
2. P8-1/P8-2A/P8-1.5/P8-2B/P8-3 产出落盘，阶段间对账通过（35 题、item_id 一致、SHA 一致）；
3. C1 终态为 `C1_PASS` 或 `C1_TERMINATED` 之一，结论闭合；
4. P8-4 双集规约冻结（不含采集）；P8-5 框架冻结（门槛数值留待实验 spec）；
5. 全程零 API、零生产代码改动；产物满足 §6 可复算纪律。
