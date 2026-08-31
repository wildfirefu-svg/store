# 设计：经典文本候选数据人工验收（修订 v5.0，干净链重冻结）

- 状态：**已批准 v4.6.1（Approved，LOCAL_ONLY）** — 批准范围仅限**本地人工验收设计与工具链**（含 §4.2/§4.4 的 382 勘误、§6 仲裁降级删除 finding 但保留分母语义、§12 工具链硬契约）；正式门禁、候选数据接受标记、Phase 8 重冻结、远端发布**全部维持 BLOCKED**（解除条件见 §11）
- 日期：2026-08-20（v4.6 修订/批准 2026-08-23；v4.6.1 草案/修订/APPROVABLE 2026-08-23；v4.6.1 有效批准 2026-08-24）
- **v5.0 重冻结（2026-08-31，干净集成链）**：按集成闭包重冻结顺序，候选数据迁移至干净链 C2 `80bc630396f31c6b6c122e49ef97f6d912e6f636`（origin/main `3d3b41cf65af487b03ca5233a109fee14191b88c` 全树 + 698 闭包 blob，四门禁 + 窄树负对照机械验证），冻结链以 `CLASSIC_ACCEPTANCE_FREEZE_V2` 重建（三对象模型不变）；旧 v4.x 链（V1 tag、候选 `51eb92b`）原样保留于 `acceptance/task1` 作为 LOCAL_ONLY 历史证据。§12.1 硬契约冻结值同步更新为 v5.0 链值。
- 关联：`knowledge_base/classic_texts/NON_COMPLIANT_CANDIDATE.md`
- 实施计划：`docs/superpowers/plans/2026-08-23-classic-texts-manual-acceptance-tooling.md`（v2 草案；v4.6.1 已授权修订计划为 v2，但**计划本身仍需独立复审通过后才可作为实施依据**，工具链 fake smoke 通过后再启动真实人工审核）
- 目标：对 `NON_COMPLIANT_CANDIDATE` 候选数据做**可复算、统计口径一致、判定状态机唯一可编码（含复核/仲裁状态）、验证器三对象冻结校验（固定 freeze ref + 锚定 tag object OID，锚定值由 LOCAL_ONLY 锚点记录承载）、发布锚点可恢复**的人工抽检，输出不可变审核包，据冻结状态机决策接受/扩样/拒绝。

### 批准记录（v4.6.1，有效批准，记录提交 2026-08-24）

- **批准人**：项目负责人（复审者）。
- **批准原文（逐字，由批准人在聊天正文直接发送，非引用块/附件/转述）**：

  > 批准 v4.6.1 作为 LOCAL_ONLY 人工验收设计修订（含 382 勘误、仲裁降级删除 finding 但保留分母、§12 工具链硬契约）；正式门禁继续 BLOCKED；据 v4.6.1 修订实施计划为 v2。

- **原文 SHA-256**：`44463d312b56045fc4548e60de3ed591e1fe9beb09a554854672cd274f678150`
- **批准记录提交**：`e86515f`，提交日期 2026-08-24（author/commit date 2026-08-24 15:45:19 +0800）。**提交日期只证明批准记录何时入库，不单独证明会话审批发生时间**；审批时点以会话记录为准（批准原文由批准人在聊天正文逐字直接发送）。
- **批准范围**：v4.6.1 设计（含 §4.2/§4.4 的 382 勘误、§6 仲裁降级删除 finding 但保留 reviewed 分母、§12 生产模式冻结锁定 + fake 模式 test_only 标记 + 三方身份互异 + CLI 严格解析 + finalize 回执闭环）作为 LOCAL_ONLY 人工验收依据。本批准**授权将实施计划修订为 v2**，但**不构成对计划 v2 本身的批准**——计划需独立复审通过后方可作为实施依据。据此进入：计划 v2 复审 → 离线工具 + fake smoke → 真实人工审核。
- **不批准（维持封锁）**：Git 历史迁移（LFS/重写）、远端 tag 发布与保护规则、Phase 8 重冻结。仅当最终 verdict 为 `ACCEPT` 时才另立设计逐项审批。
- 冻结锚点记录（`freeze-anchor-record.json`）的 `overall_state` 与 `provenance.independent_approval` 字段不受本批准影响——本批准对象是**设计**，非冻结锚点、非正式门禁。v4.6.1 §12.1 明确：生产工具门禁要求该记录 `record_type=freeze-anchor-record`、`status=LOCAL_ONLY`、`overall_state` 精确匹配、顶层无 `independent_approval` 键、`provenance.independent_approval=="none"`。

### 撤回的无效批准尝试（v4.6.1，审计记录）

- **提交**：`3967000`（2026-08-23），曾把状态写为"已批准 v4.6.1（Approved，LOCAL_ONLY）"，并记录原文 SHA-256 `44463d312b56045fc4548e60de3ed591e1fe9beb09a554854672cd274f678150`。
- **撤回原因**：该提交依据的是复审消息中的**建议引用块**，而复审消息已明确声明"引用块只是建议文本，不构成正式批准"；实现者未在聊天正文直接发送批准原文，`APPROVABLE` 仅表示"可以批准"不等于 `APPROVED`。SHA 计算正确但只能证明文本内容，不能证明文本由批准人直接发出。
- **处理**：纠正提交 `5065b57` 不重写历史、不 reset，仅将设计状态恢复为 Draft / APPROVABLE；`3967000` 作为审计痕迹保留，其"已批准"声明作废。本提交（有效批准提交）在批准人于聊天正文逐字直接发送批准原文后创建，取代撤回的无效尝试。

### v4.6.1 修订草案（2026-08-23，已批准）

v4.6 实施计划复审（NEEDS_REVISION）暴露 4 项流程/语义缺口，经四轮草案修订（提交 `383c11c` → `a5a972d` → `106aa0e` → `d87b240`，均为 Draft），最终复审结论为 `APPROVABLE`（无剩余阻断项），并由项目负责人于 2026-08-24 在聊天正文逐字直接发送批准原文，有效批准为本 v4.6.1（有效批准记录提交 `e86515f`，日期 2026-08-24）：

1. **抽样总量以冻结公式为准（§4.2/§4.4 勘误）**：卷十一层 MCQ `367×2%=7.34 → round_half_up → 7`（v4.6 表内误记 8），MCQ 随机合计 **188**（跨四书 128+42+13+5）、总量 **188+194=382**；规则总量 609 不变。本勘误由项目负责人 2026-08-23 会话裁定"公式为准"。
2. **仲裁降级语义明确（§6）**：仲裁判 `ADJUDICATED_NON_CRITICAL` 后，该 finding **从 canonical 集删除**（不进入 critical，也不进入 minor），但**该审核条目仍计入已审分母**；条目 verdict 按剩余 findings 重算，无剩余 finding 时为 `PASS`。分母不得因删除 finding 而缩小。
3. **验收工具链硬契约（新增 §12）**：生产模式必须 fail-closed 锁定冻结候选提交、章节/身份 manifest SHA、freeze chain；锚点记录门禁校验 `record_type`/`status`/`overall_state`，顶层无 `independent_approval`，且 `provenance.independent_approval=="none"`（两者均纳入 fail-closed 门禁，任一变化即非零退出）；fake 模式产物强制标记 `test_only=true` 且 `finalize` 拒绝收尾。
4. **复核/仲裁身份契约（§8.2/§12）**：primary 可有多个首审人，arbitration 按 entry 记录对应 `reviewer_first`；仲裁人必须全局独立（不在 primary `reviewer_list`、不等于二审人），primary/second/arbitrator 在每个仲裁 entry 上两两互异；CLI 必须拒绝未知参数、缺值与多余 positional；`finalize` 拒绝未被报告绑定却额外传入的回执；LOCAL_ONLY 阶段为"身份声明 + 内容绑定"，不具备密码学签名或独立身份认证能力。

### 批准记录（v4.6，记录提交 2026-08-23）

- **批准人**：项目负责人（复审者），以会话指示形式给出；原文与其 SHA-256 记录于此，供与会话记录比对核验。
- **审批原文**（逐字）：

  > 批准 v4.6 作为 LOCAL_ONLY 人工验收设计；正式门禁继续 BLOCKED；暂不迁移 Git 历史、不发布远端 tag、不批准 Phase 8。

- **原文 SHA-256**：`010b93566ffd79683a37da19d7ac40d1825337098968d64303eb0f98e5f95f8f`
- **批准记录提交**：`d8f6697`，提交日期 2026-08-23（author date 2026-08-23 10:39:51 +0800）。v4.6 批准记录原写"2026-08-22"系笔误，本版据实校正；**提交日期只证明批准记录何时入库，不单独证明会话审批发生时间**，审批时点以会话记录为准。审批原文与 SHA 不变。
- **批准范围**：v4.6 设计（含三对象冻结链、`LOCAL_FREEZE_VERIFIED` 状态）作为 LOCAL_ONLY 人工验收依据；据此进入实施计划（writing-plans）→ 离线工具 + fake smoke → 真实人工审核。v4.6.1 新增/修订条款（§4.2/§4.4 勘误、§6 仲裁语义、§12 工具链契约）**尚待批准**，不在 v4.6 批准范围内。
- **不批准（维持封锁）**：Git 历史迁移（LFS/重写）、远端 tag 发布与保护规则、Phase 8 重冻结。仅当最终 verdict 为 `ACCEPT` 时才另立设计逐项审批。
- 冻结锚点记录（`freeze-anchor-record.json`）的 `overall_state` 与 `provenance.independent_approval` 字段不受本批准影响——本批准对象是**设计**，非冻结锚点、非正式门禁。

## 0. 路线定位（不变）

先内容抽检 → 决策 →（仅接受后）审批 Phase 8 重冻结 → 配置外部 artifact store → 干净工作区正式门禁。本设计即使全绿，`overall_pass=false` 历史事实保留。

---

## 1. 冻结身份：机器可读 manifest（修订 P0-1）

### 1.1 三对象模型（修订 P0-1）

三个角色唯一、相互独立的提交对象（不再有"tooling_commit 自引用"）：

- **`candidate_commit = 80bc630396f31c6b6c122e49ef97f6d912e6f636`**（v5.0 干净链 C2）：仅作为**被读取的数据提交**（四书输出、快照、raw、Phase 8 文件均从它 `git show` 读取）。其中不存在生成器与两个 manifest，不在其上运行任何工具。
- **`tooling_payload_commit`**：包含生成器、设计、manifests 的提交（由 freeze receipt 记录）。该提交内的 `acceptance-freeze.json` 是 **PENDING 占位**。**`--check` 从不从 payload/HEAD 读取 receipt**——占位是设计使然（v4.2 的 P0-1 正是把"receipt 已定稿的提交"与"receipt 指向的提交"混为一谈），不是缺陷。**验证器机械校验 payload 自包含**：payload 内必须存在生成器 blob，且其 blob OID / LF SHA 与 receipt `generator` 记录一致（v4.3 P0-2 修订——此前只校验"当前运行脚本"，payload 本身可以不含生成器）。
- **`freeze_commit`**：**annotated tag `CLASSIC_ACCEPTANCE_FREEZE_V2` 指向的提交**，持有**已定稿 receipt**，且**相对 payload 只允许修改 receipt 一个文件**、payload 必须是其祖先（两者均由验证器机械校验，v4.3 中优修订）。freeze receipt 不记录自身提交 SHA（内容寻址提交无法自引用）。

**freeze tag 信任根（独立机制，v4.6 修订：降级为 freeze-anchor-record（LOCAL_ONLY），不再称"审批"；勿与 §8.3 混淆）**：§8.3 定义的是**验收结果 tag**（`ACCEPTED_LEGACY_CANDIDATE-*`，仅内容接受后存在），不是本冻结 tag 的信任根。冻结 tag 的唯一信任机制是**锚定值机械核对**：tag 名到 tag object 的绑定是**可变引用**（"tag object 本身不可变"不等于"tag 名到 object 的绑定不可变"），验证器强制要求 `--expected-freeze-tag-oid <40-hex>` 并与 `git rev-parse refs/tags/CLASSIC_ACCEPTANCE_FREEZE_V2` 的解析值比对，不一致即 fail-closed——本地把 tag 改指向新的自洽 annotated tag 会被立即拦截。

锚定值的**承载（诚实声明，v4.6 修订）**：
- 锚定值记录于**冻结锚点记录文件** `docs/superpowers/specs/2026-08-20-classic-texts-freeze-anchor-record.json`（v4.5 曾命名 "approval"，v4.6 依复审降级改名——**它不是审批**：由实现者创建并维护、与设计文档同仓库提交，`record_type=freeze-anchor-record`、`status=LOCAL_ONLY`、`provenance.independent_approval="none"`）。记录内容：tag 名、tag object OID、freeze_commit、payload、candidate、generator、manifests 全量值、创建来源（implementer）、远端发布状态与证据。**其唯一合法作用是把锚定值从隐藏的测试常量变为显式可审的工件**——不是独立信任边界。
- **当前总体状态**：`LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED`（记录 `overall_state` 字段）。**真正的独立审批**须在实现者控制之外记录：独立审批人的**原文、原文 SHA-256、审批人身份、时间**；在此之前不宣称存在任何审批。
- **一致性机械锁定（仅防无意漂移，非信任边界）**：`tests/test_generate_acceptance_manifests.py` 强制 锚点记录 ↔ 本地 tag ↔ 设计锚点行 三方一致（记录、设计、测试三者本可一起修改——该锁定只覆盖"改一处漏两处"的意外，不覆盖合谋篡改）。
- **远端发布——当前被结构性阻断，未完成**：冻结 tag 可达历史含三个超 GitHub 100 MiB 单文件硬上限的候选 provenance blob（354 MiB `QUALITY_REPORT.json`、314 MiB `provenance.json`，均由 `16c72b4` 引入；312 MiB `remediation_meta.json`，由 `f64a25d` 引入——v4.6 修正了 v4.5 误记的引入提交），tag 永远无法按现状推送；且候选提交 `51eb92b` 不在远端 main 历史内，远端校验还额外需要候选对象。两次推送尝试的完整报错、阻断 blob 清单与三个解决方案（LFS 迁移 / 外部 artifact store / 维持本地锚点并把远端发布列为正式门禁前置条件）**如实记录于锚点记录 `remote_publication` 字段**——其中历史重写/大文件迁移**须另立设计并显式批准**后方可执行。远端发布与受保护 tag 规则（平台侧配置，git 客户端无法配置）在证据归档前**不宣称已满足**，记为正式门禁前置条件（§8.3/§10.4），正式门禁维持 **BLOCKED**。**v5.0 重冻结进展**：干净集成链 C2 `80bc630396f31c6b6c122e49ef97f6d912e6f636` 以 origin/main `3d3b41cf65af487b03ca5233a109fee14191b88c` 全树为基底，三个超大 provenance blob 均不在其可达历史内（main 版本仅 6,381/332 字节，`provenance.json` 不存在），本条结构性阻断在该链上按构造解除；受控推送、正式 CI 与受保护 tag 规则仍为后续受控步骤。
- 重冻结时必须同步更新：锚点记录（含远端发布状态）、§1.2 锚点行、远端 tag（若已解除阻断）；三方一致性由测试机械锁定；换锚定值本身即显式重冻结决策。

执行规则：**所有工具（生成器、`--check`、抽样脚本）在 `freeze_commit` 的干净 detached worktree 运行**（该提交同时含冻结生成器与已定稿 receipt）；所有候选数据只经 `git show candidate_commit:path` 读取。候选提交不因工具运行被污染。

候选 tag 提交：`f64a25d…`、`16c72b4…`（已打 tag）；整改提交 `4d77062…`、`51eb92b…`（未打 tag）。

抽检基准提交 = `51eb92b…`（数据）；工具基准提交 = `tooling_payload_commit`（工具内容）+ `freeze_commit`（已定稿 receipt，锚定 OID 的 tag 指向）。禁止在脏主工作区切换；核对/抽样一律用 detached worktree。

### 1.2 身份 manifest（唯一机器可执行来源）

已生成并冻结：**`docs/superpowers/specs/2026-08-20-classic-texts-candidate-identity-manifest.json`**（LF canonical SHA-256 `7366d6a9d6cc07a641d876e25ccaff0cfdff52c19a62d475dad95a52f27a4cca`，提交内 LF 字节）。

包含（全部为提交内 LF 字节身份）：
- 8 个输出文件：`path` + 40 位 `blob_oid` + 64 位 `sha256_lf` + `size_bytes` + `candidate_commit`；
- 3 个 Phase 8 漂移文件；
- 快照身份 3 项（manifest/active/pointer）；
- **权威原文 383 个** `extracted/raw_NNN.txt` + **派生根目录 raw 303 个**（`derived_root_raw_303`，标注为派生副本）；
- `generator` 元数据（路径、算法版本、生成器 LF SHA、candidate commit）。

设计文档不再内嵌截断指纹；一切核对以 manifest 为准。任何 `…` 截断、文档表格与 manifest 不一致，以 manifest 为最终裁决。

**独立复算/验证命令（冻结，v4.3 P0-1/P0-2 修订：锚定 OID + payload 自包含）**：

```
python scripts/generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid <tag-object-oid>
```

`--freeze-ref` 与 `--expected-freeze-tag-oid` 均为**强制参数**（禁止默认 HEAD；tag 名是可变引用，`<tag-object-oid>` 锚定值从冻结锚点记录 `2026-08-20-classic-texts-freeze-anchor-record.json` 的 `expected_tag_oid` 字段读取——该记录为 LOCAL_ONLY 的实现者工件，不是审批）。验证器 fail-closed（任一不符非零退出）：
1. ref 存在且为 annotated tag；
2. **解析出的 tag object OID == `--expected-freeze-tag-oid` 锚定值**（tag 改指新自洽冻结在此被拦截）；
3. 从 tag 指向的 freeze_commit 读取 `acceptance-freeze.json`（**唯一机器可裁决冻结层**，与 HEAD 无关）；
4. receipt 字段校验（freeze_tag / candidate_commit / payload / generator 记录 / manifests SHA 齐全且格式合法）；
5. payload 是 freeze_commit 的祖先，且 freeze_commit 相对 payload **只改 receipt**（`git diff --name-only` 恰为 receipt 路径）；
6. payload 的 committed manifests LF SHA == receipt 冻结值；
7. **payload 内生成器存在且为 blob，blob OID / LF SHA == receipt generator 记录**（payload 自包含验证）；
8. 内存重生成（候选数据经 `git show candidate_commit:path`）== 冻结值；
9. 运行中生成器 blob/LF SHA == 冻结值（运行者必须是冻结生成器）。

不依赖文档人工比对。**整体重冻结攻击（新 payload + 新自洽 receipt + tag 改指）**被第 2 层（锚定 OID 不匹配）拦截；即使操作者误用攻击者提供的 OID，第 8/9 层仍以候选数据重生成与运行生成器比对兜底。生成器 blob OID/LF SHA 见 manifest `generator` 元数据（内容派生，HEAD 无关）。

**当前冻结锚点（v5.0）**：`CLASSIC_ACCEPTANCE_FREEZE_V2` tag object OID = `98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7`（指向 freeze_commit `d7922bb9…`，payload `ba7cc51…`）。锚定值的载体为冻结锚点记录 `2026-08-20-classic-texts-freeze-anchor-record.json`（LOCAL_ONLY，实现者工件，非审批；远端发布状态：结构性阻断已按构造解除、待受控推送，详见其 `remote_publication` 字段；总体状态 `LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED`）；本行与测试均从该记录核对，三方一致性由 `test_anchor_record_matches_real_tag` / `test_anchor_record_matches_design_doc` / `test_anchor_record_matches_freeze_chain` 机械锁定（防无意漂移，非信任边界）。

---

## 2. 验收总体与权威原文（修订 P0-2）

### 2.1 被验收输出

- 四书 `all_rules.json`（全部规则）+ `all_mcq.jsonl`（全部 MCQ）：sanmingtonghui 8043/6103、qiongtongbaojian 2312/2120、ditiansui 799/646、zipingzhenquan 156/155。
- Phase 8 三个漂移文件（含 `qiongtongbaojian/quarantine_rules.jsonl`）作完整性审核（存在性、行格式、计数一致）。
- 零产出章节（§3）作完整性审核。

### 2.2 权威原文源（唯一）

- **权威原文 = formal snapshot 的 `extracted/raw_NNN.txt`（383 个，`raw_001..raw_383`）**，身份见 identity manifest。
- **根目录 `raw_*.txt` 中的 numeric 303 个（`raw_081..raw_383.txt`）为派生副本**，不作溯源基准。
- **legacy 标题文件（`raw_001_卷一_…txt` 等）** 与 `raw_text_shas` 的 basename 键**不能**唯一验证两套路径；**不再宣称 `provenance.raw_text_shas` 验证全部 686 个路径**。
- 溯源对照只使用 §3 章节身份 manifest 中每个章的 `raw_source_path`（即 extracted 权威路径）。

### 2.3 原文规范化规则（冻结）

溯源对照（判定 `source_mismatch`）使用：
1. 删除全部空白（Unicode `\s+`）后子串匹配；
2. 全角/半角标点**不归一**（须逐字一致）；
3. 繁体/简体**不自动转换**（以 raw 原文为准）；
4. `original_text` 定位失败即记 Critical `source_mismatch`。

规范化函数实现 SHA 由抽样脚本冻结并随 `sample_manifest.json` 记录。

---

## 3. 章节身份（修订 P0-3：冻结 manifest，不再文字声明）

### 3.1 口径澄清（重要更正）

**`source_chapter` 与 validator G7 非同口径。** G7 仅比较 `chapter_list` 与 `progress.done`，不读取规则 `source_chapter`，也不经 `source_rule_id` 映射 MCQ。本设计的零产出识别基于 `source_chapter` 口径，**独立于 G7**。

### 3.2 冻结 `chapter_identity_manifest.json`

已生成并冻结：**`docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json`**（LF canonical SHA-256 `8687f681537204b18b7743913225c408e4957699b5a036846f90eaba8aeffe4e`，提交内 LF 字节）。

内容（对 sanmingtonghui 383 章）：
- `chapter_index` 1–383、`title`、`is_legacy`（**legacy 80 章 / 唯一标题 80 个**，分别记录于 `legacy_chapter_count` 与 `legacy_unique_title_count`）；
- `raw_source_path`（extracted 权威路径，383/383 有值）；
- **`source_chapter_title_to_index`**（全 383 个标题→章映射，`source_chapter_title_map_count=383`；用于解析规则 `source_chapter` 的标题形式；非 legacy-only——字段语义已修正）；
- 每章 `rule_ids` / `mcq_ids`（MCQ 经 `source_rule_id`→规则→章）；
- `zero_rule` / `zero_mcq` 状态；
- **恰好一次断言**：全部 8043 规则、6103 MCQ 各恰好映射到一章（已断言通过）；
- `generator` 元数据（路径 `scripts/generate_acceptance_manifests.py`、算法版本、生成器 LF SHA、candidate commit）——**映射可复现**。

**独立复算/验证命令（冻结）**：`python scripts/generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid <tag-object-oid>`——见 §1.2（锚定 OID 比对、payload 自包含生成器校验、祖先 + 仅改 receipt 约束、regenerated == committed-at-payload == 冻结期望值、运行生成器比对），漂移非零退出；全文不再内嵌截断/单值 SHA，冻结身份以 `acceptance-freeze.json` 为唯一机器裁决。本设计的 identity/chapter manifest LF SHA 与 freeze receipt 一致：identity `0279e30b…`、chapter `ba8ab35e…`。

### 3.3 零产出章（权威，来自 manifest）

- **0 规则章**：ch 25、56、72（3）
- **0 MCQ 章**：ch 25、26、56、72、112（5）

> 与 v1/v2 差异来源：本清单基于冻结章节 manifest 的 `source_chapter` 口径。复审据 ID/raw 视图的"ch77-80 无规则"与本清单不同——该差异已由 manifest 的"恰好一次映射 + legacy 标题映射 + raw_source_path"闭环消解；审核包仍要求审核人核对两视图并记录。

对零产出章：核对 `raw_source_path` 存在性（缺失 → 记 `source_missing`，见 §6 判定矩阵直接 REJECT；存在但模型未产出 → 记 `zero_output` 诊断）。

---

## 4. 确定性抽样（修订：哈希编码 + 精确 k）

### 4.1 选择算法（跨 Python 可复算，无冒号歧义）

不用 `random.shuffle`。对候选 item 计算：

```
key = length_prefixed(SEED_bytes) ++ length_prefixed(book) ++ length_prefixed(type) ++ length_prefixed(stratum_index) ++ length_prefixed(item_id)
score = sha256(key)
```

- `length_prefixed(s)` = `u32(len(s_bytes)) ++ s_bytes`（大端），杜绝冒号/分隔符歧义；item_id 含任意字符也不影响唯一编码。
- `SEED` = `0xA5C0DE20260820`（十进制 `46655431411894304`），8 字节大端。
- `type` ∈ {`rule`,`mcq`}；`stratum_index` 见 §4.2。
- 同 `(book,type,stratum)` 内按 `score` 升序取前 `k`；**并列平局**以 `item_id` 字典序为次级排序。
- 抽样脚本冻结 SEED、算法版本、stratum 表、k 表、哈希实现 SHA，输出 `sample_manifest.json`。

### 4.2 精确 k（冻结，删除"百分比+手工值并存"）

sanmingtonghui（9 层，k 为 3% 规则 / 2% MCQ，min 5，`round_half_up`）：

| stratum | 卷段 | 章节 | 规则 | k_rules | MCQ | k_mcq |
|---|---|---|---|---|---|---|
| 1 | 卷一–卷四 | 1–80 | 1542 | 46 | 777 | 16 |
| 2 | 卷五 | 81–89 | 74 | 5 | 59 | 5 |
| 3 | 卷六 | 90–162 | 708 | 21 | 593 | 12 |
| 4 | 卷七 | 163–184 | 291 | 9 | 211 | 5 |
| 5 | 卷九 | 185–244 | 1320 | 40 | 1226 | 25 |
| 6 | 卷八 | 245–304 | 1274 | 38 | 1187 | 24 |
| 7 | 卷十 | 305–346 | 1108 | 33 | 843 | 17 |
| 8 | 卷十一 | 347–367 | 505 | 15 | 367 | 7 |
| 9 | 卷十二 | 368–383 | 1221 | 37 | 840 | 17 |
| 合计 | | | 8043 | **244** | 6103 | **128** |

其余三书（精确 k，与比例一致，不再另列手工值）：

| 书 | 规则数 | k_rules(=3%) | MCQ 数 | k_mcq(=2%) |
|---|---|---|---|---|
| qiongtongbaojian | 2312 | **69** | 2120 | **42** |
| ditiansui | 799 | **24** | 646 | **13** |
| zipingzhenquan | 156 | **5** | 155 | **5** |

### 4.3 边界章（必抽，规则+MCQ 全量）与去重

- 边界章：ch 1、80、81、90、163、185、245、305、347、368、383。
- 边界实测（source_chapter 口径，以章节 manifest 为准）：**规则 267、MCQ 194**（ch1:14/14、ch80:1/1、ch81:2/2、ch90:15/14、ch163:28/4、ch185:40/38、ch245:35/32、ch305:15/14、ch347:12/9、ch368:81/49、ch383:24/17）。
- **去重**：随机样本从"非边界"项抽取；边界项移出随机框；最终分母 = 去重后唯一已审项（规则/MCQ 分母分别记录）。

### 4.4 工作量（修正实算）

- 规则：随机 244+69+24+5 = **342** + 边界 267 = **609**；
- MCQ：随机 128+42+13+5 = **188** + 边界 194 = **382**；
- 合计 **609 规则 + 382 MCQ + 零产出/完整性项**，约 **3–5 人日**。（废弃 v2 的"约660=631"手工和；MCQ 总量 382 系 v4.6.1 勘误，卷十一层 k_mcq 按冻结公式 `round_half_up(367×2%)=7`，原表值 8 系残留手工笔误，见 §4.2。）

---

## 5. 错误定义（findings[] + PASS_WITH_MINOR）

每项可含多条 `findings[]`。`verdict` 三值：`PASS` / `PASS_WITH_MINOR`（≥1 条 minor、0 条 critical）/ `FAIL`（≥1 条 critical）。

- Critical：`distortion`、`answer_wrong`、`unsupported`、`hallucination`、`source_mismatch`（定义同 v2）。
- Minor：`wording`、`condition_omission`、`option_noise`、`citation_bias`（定义同 v2）。

---

## 6. 判定状态机（修订 P0-2/P0-3：唯一、可编码、优先级冻结）

以下为**唯一判定算法**，逐条按优先级执行（满足即终止；禁止跨书/跨类型均值，禁止并行口径并存）。每条可机械编码为伪代码。

### 6.1 指标（全部按"单书 × 单类型"分离）

- `R_b = rule_critical_fail_rate_b`（书 b 规则）＝ critical 失败**规则数** / 已审规则数
- `M_b = mcq_critical_fail_rate_b` ＝ critical 失败**MCQ 数** / 已审 MCQ 数
- `rMinor_b / mMinnor_b` ＝ 该书该类型的 `PASS_WITH_MINOR` 占比（minor-only 项数 / 已审项数）
- 边界：`B_R_b / B_M_b` ＝ 该书边界集 critical 项数（边界已全量审核，不设"扩样"）

### 6.2 优先级判定（REJECT 优先）

```
1. INTEGRITY:
   if any zero-output chapter's raw_source_path missing        -> REJECT
   if any phase8 drift file missing (per identity manifest)    -> REJECT

2. BOUNDARY（P0-3：复核/仲裁入状态机）:
   边界任一 critical（B_R_b 或 B_M_b > 0）→ SECOND_REVIEW_PENDING：
     第二审核人复核该边界项（§8.2）
     ├─ 二审同意（仍 critical）        -> ADJUDICATED_CRITICAL -> REJECT
     └─ 二审不同意（判非 critical）    -> ARBITRATION_PENDING -> 第三审核人仲裁（§8.2）
          ├─ 仲裁维持 critical          -> ADJUDICATED_CRITICAL -> REJECT
          └─ 仲裁改判非 critical        -> ADJUDICATED_NON_CRITICAL（v4.6.1：该 finding 从 canonical 集**删除**，不进入 critical 也不进入 minor，条目 verdict 按剩余 findings 重算；继续后续门禁）
   （边界已全量审核，无新增样本；不再称"边界扩样"）
   最终指标、边界门与 verdict 一律基于 **ADJUDICATED canonical finding**（仲裁后定稿），不基于首轮原始判定。

3. STRATUM_CASCADE:
   if any stratum rule_critical_fail_rate > 8%                 -> REJECT（直接，不"全量复核后"；fail-closed）

4. REJECT_GATE:
   if R_b > 5% or M_b > 5% or rMinor_b > 15% or mMinnor_b > 15%  -> REJECT

5. EXPAND_GATE (单书 × 单类型；状态机显式输入 `expanded_pairs` 集合，已扩样的对不再触发):
   if (b, rule) not in expanded_pairs and 5% >= R_b > 2%  -> mark EXPAND(book=b, type=rule)
   if (b, mcq) not in expanded_pairs and 5% >= M_b > 2%  -> mark EXPAND(book=b, type=mcq)
   （minor 不触发扩样；minor 超标在规则 4 已 REJECT）
   若任一 (b,type) 已 ∈ expanded_pairs 且其 critical 仍 ∈ (2%, 5%]  -> REJECT（fail-closed，禁止二次扩样）

6. ACCEPT:
   only if no rule 1-5 fired, i.e. every book×type: critical <= 2% and minor <= 15%，
   且边界无 critical，无 source_missing -> ACCEPT
```

`zero_output`（raw 存在但模型未产出）为诊断项，不进接受/拒绝（规则 1 只处理 `source_missing`）。

### 6.3 扩样执行（P0-3 不相交 + P0-4 作用范围冻结）

扩样作用于**触发书 × 触发类型的全部 strata**（门禁在书×类型层判定，不针对单个 stratum；不产生"某触发层"）。

对每个触发 `(book, type)`，在其每个 stratum 上：

```
remaining_population(stratum) =
    full_population(book,type,stratum)
    - initial_random_sample_ids(book,type,stratum)
    - mandatory_boundary_ids(book,type,stratum)

expand_score = sha256(
    length_prefixed(SEED) ++ length_prefixed(EXPAND_TAG)
    ++ length_prefixed(book) ++ length_prefixed(type)
    ++ length_prefixed(stratum) ++ length_prefixed(item_id))
```

- 新样本 = 该 stratum `remaining_population` 内按 `expand_score` 升序取前 `k`（**与首轮保证不相交**，因从补集中取）。
- `EXPAND_TAG` = `bytes([0x45,0x58,0x50])`（`"EXP"`）。
- **扩样数量（P0-4：按 stratum 精确公式，禁用单一 2k）**：

```
added_s = min(k_s, len(remaining_population_s))     # 每层实际新增
final_s = initial_s + added_s                        # 每层最终样本
final_book_type_total = Σ_s final_s                  # 书×类型最终总量 = 各层之和
```

  `k_s` 为 §4.2 冻结的该层 k；`remaining_population_s` 不足时取全部剩余（含 0）。
- **分母** = 去重后唯一已审项（首轮+扩样，逐层 `final_s` 累计）。
- **剩余不足**：某 stratum `remaining_population_s` < `k_s` → 取全部剩余；若某 stratum 为 0 → 该层无新增（不阻塞其他层）。
- **多触发并行**：所有满足 EXPAND_GATE 的 `(book,type)` 在**同一轮**并行扩样（新增样本一次性确定），随后统一重判一次。
- **禁止可选停止**：判定仅由 §6.2 驱动；扩样后 `expanded_pairs` 加入已扩对，再次处于 `(2%,5%]` 即 fail-closed REJECT。

### 6.4 状态汇总（`expanded_pairs` + 复核/仲裁状态为显式输入）

```
ADJUDICATION 前置（P0-3；v4.6.1 明确 non_critical 语义）：所有 critical finding 进入
  SECOND_REVIEW_PENDING ->（二审同意）ADJUDICATED_CRITICAL
                        ->（二审不同意）ARBITRATION_PENDING ->
                             ADJUDICATED_CRITICAL     -> 保留为 canonical critical
                             ADJUDICATED_NON_CRITICAL -> 该 finding 从 canonical 集删除
                                                       （不进 critical、不进 minor；条目
                                                        verdict 按剩余 findings 重算）
  指标 R_b / M_b / 边界 B_* 一律基于 ADJUDICATED canonical finding。v4.6.1 明确分母口径：
  仲裁判 ADJUDICATED_NON_CRITICAL 的 finding 从 canonical 集删除（不计入 critical 分子、
  不计入 minor-only 分子），但**该审核条目仍计入已审条目分母（reviewed count）**；条目
  verdict 按剩余 findings 重算，剩余零条 finding 时 verdict=PASS。分母不得因删除 finding
  而缩小——禁止用"删条目"人为压低失败率。

判定：
状态 = (pending_expands: set, expanded_pairs: set, adjudicated: set)
INITIAL: expanded_pairs = {}
  先跑 ADJUDICATION 前置（全部 critical 定稿为 canonical）
  再跑 §6.2（基于 canonical finding）
  -> ACCEPT | REJECT | 收集 EXPAND 集 P（非空）
EXPAND: 对 P 并行扩样（§6.3），expanded_pairs += P
  重跑 ADJUDICATION + §6.2（expanded_pairs 已含 P）
  -> ACCEPT | REJECT（§6.2 规则 5 保证：已扩对仍 (2%,5%] -> REJECT；无二次扩样）
```

---

## 8. 审核包发布链（修订 P0-4：不可变 receipt 链，包内不内嵌复核/仲裁）

**唯一发布路径（冻结）**：

```
primary_review_package_v1.json         （审核人逐项填写；含逐项 verdict/findings + overall_stats + zero_output_report + reviewer_list；不含 second_review/arbitration）
        ↓ 计算 SHA-256
second_review_receipt_v1.json          （独立不可变：全部 critical 的第二审核人复核结果；绑定 primary 包 SHA）
        ↓ 按需
arbitration_receipt_v1.json            （独立不可变：第三审核人仲裁记录，绑定 primary+second 的 SHA）
        ↓
final_acceptance_package_v1.json       （组装：引用 primary/second/arbitration 各 SHA + sample_manifest SHA + final_verdict）
        ↓ 计算 SHA-256
annotated tag 绑定（指向 audit commit，见 §8.3）
```

- **primary 包一经计算 SHA 即冻结**；second_review 与 arbitration 是**独立文件**（不写入 primary 包，避免字节漂移）。
- 任一阶段发现需修正 → 生成**新版本文件**（如 `_v2`），不原地改动已冻结文件；`final_acceptance_package` 记录所用版本与各自 SHA。

### 8.1 primary 包 schema

```json
{ "item": { "book": "…", "type": "rule|mcq", "id": "…", "source_chapter": 193 },
  "verdict": "PASS|PASS_WITH_MINOR|FAIL",
  "findings": [ { "severity": "critical|minor", "category": "…", "evidence_text": "…", "note": "…", "reviewer": "…", "reviewed_at": "…" } ] }
```

包级字段：`sample_manifest_sha256`、`overall_stats`（分对象/分书/分层/边界）、`zero_output_report`、`reviewer_list`。**不含** `critical_second_review` / `arbitration_log`（它们在独立 receipt）。

### 8.2 复核与仲裁

- **全部 critical finding 第二审核人独立复核** → `second_review_receipt_v1.json`（每项：原文 id、首审判定、二审判定、证据引用）。
- **仲裁**：二审不同意某 critical → 第三审核人（审核组长）仲裁 → `arbitration_receipt_v1.json`（裁决理由 + 三方身份声明与绑定链 SHA；LOCAL_ONLY 阶段不具备密码学签名或独立身份认证能力，身份互异与绑定契约见 §12.3）。
- 复核/仲裁均以独立文件追加，**绝不改写 primary 包**。

### 8.3 绑定（唯一路径：audit commit + annotated tag，无 receipt 二义）

**唯一发布路径**：只使用 annotated tag，不再用独立 `receipt.json`（`receipt.json` 选项已废弃）。

1. 将全部审核文件（`primary_review_package`、`second_review_receipt`、`arbitration_receipt`、`final_acceptance_package`、`sample_manifest`）提交到**独立 audit commit**（不并入候选提交）。
2. annotated tag **指向该 audit commit**（而非候选提交 `51eb92b`——候选提交不可能包含后生成的审核文件）。
3. tag message 记录闭环锚点：candidate **tree SHA**（`git rev-parse 51eb92b^{tree}`）、各审核文件完整 SHA、`sample_manifest` SHA、最终 verdict、审核人名单。
4. tag 名：`ACCEPTED_LEGACY_CANDIDATE-<audit-commit-sha>`（完整哈希，不用 `<book>-<sha8>`）。
5. **信任根（唯一机制，修订）**：冻结 **tag object OID**（`git rev-parse <tagname>^{tag}`，annotated tag 对象自身哈希）作为不可变信任根。保护机制**唯一选定为"受保护 tag 规则"**：audit commit + annotated tag 推送到配置了受保护 tag 规则的远端（禁止删除/改指/force-push 该 tag）；tag object OID 记录于 audit 包回执，用于本地核验远端未改指。**本条针对验收结果 tag（`ACCEPTED_LEGACY_CANDIDATE-*`）；冻结 tag（`CLASSIC_ACCEPTANCE_FREEZE_V1`）的信任机制独立定义于 §1.1/§1.2（`--expected-freeze-tag-oid` 锚定值机械核对），二者不可混用。** **正式门禁前置条件（v4.3 中优修订）**：远端受保护 tag 规则须有**可验证证据**（远端配置导出/规则 JSON/审批回执文件，随门禁产物归档）；仅有设计声明不满足门禁。**不采用**签名 annotated tag（GPG 密钥管理超范围）或独立审批回执（无远端强制力）作为替代机制。
6. **可恢复性**：审核文件随 audit commit 永久可取得；复算由 `--check`（§1.2）与 `sample_manifest` 生成器保证。外部 artifact store 归档（§10.3）作为补充，不替代 audit commit 锚点。

---

## 9. 抽检覆盖项（同 v2，不变）

- 383 章卷段 + 边界章（规则与 MCQ 均覆盖）。
- 规则原文与出处一致性（以 extracted 权威原文 + §2.3 规范化规则）。
- 条件/主体/结论曲解、MCQ 唯一答案、explanation 支持、重复/答案泄露/幻觉、零产出完整性。

> **统计口径警示**：zipingzhenquan 每类仅抽 5 项，ditiansui 部分层接近 min——这些门的判定只能解释为**项目级验收规则**（§6.2），**不声称具有总体统计保证**（尤其小样本下的置信度不成立）。总体推断仅对 sanmingtonghui 主分层（k≥5，多数层 ≥15）在 §5 报告加权估计时给出，且仅作诊断。

---

## 10. 决策后动作（仅内容接受后触发，不变）

1. 标记 `ACCEPTED_LEGACY_CANDIDATE`（§8.1 强绑定 tag），保留历史事实。
2. 审批 Phase 8 重冻结（3 个 blob，身份见 identity manifest）。
3. 配置外部 artifact store 上传 tar 生成回执。
4. 干净工作区正式门禁（detached worktree、pre-run manifest、禁改工作区、核对 HEAD/diff/指纹、exit 0）；**门禁产出保留 JUnit XML 证据**——测试内存/资源类瞬态失败须修复根因后重跑取绿，不得以"重跑通过"掩盖既有失败（v4.2 中优项）。

---

## 11. 风险与开放项

- 抽样非穷尽；边界章必抽覆盖交接/稠密段。
- 卷段级联（>8%）采用 fail-closed REJECT，偏严；如需放宽须在终审中显式修改。
- 审核人名单未预设；k/门槛/SEED 为提案值，终审确认后由脚本冻结。
- 通过后 `overall_pass=false` 保持。

---

## 12. 验收工具链硬契约（v4.6.1 新增，实施计划必须满足）

本节约束抽样/审核/判定/终局工具（`classic_acceptance_common.py` / `_sampling.py` / `_review.py`）的行为，是 LOCAL_ONLY 工具链的强制契约，不依赖测试自觉。

### 12.1 生产模式 fail-closed 锁定冻结输入

真实人工验收（`--candidate-commit <40-hex>` 模式）必须在任一读取前机械校验以下全部条件，任一不符即非零退出并打印具体失配项：

1. `candidate_commit` 精确等于冻结值 `80bc630396f31c6b6c122e49ef97f6d912e6f636`（v5.0 干净链 C2）（禁止"任意 40 位 commit 都能跑"）。
2. 章节 manifest（`--chapter-manifest`）按 LF 规范化字节的 SHA-256 等于冻结锚点记录中 `manifests["2026-08-20-classic-texts-chapter-identity-manifest.json"]` = `ba8ab35e7b98e3a0578f7b62f758e2faff1bbe73d480e153c25b6c74b497d1cf`。
3. 身份 manifest（由冻结锚点记录 `manifests["2026-08-20-classic-texts-candidate-identity-manifest.json"]` = `0279e30b92f70f8b7cce9c786070fc201cfc3fac86826ef6403b15ad90c5aad2` 定位）存在且其 SHA 一致；工具据此校验 8 个输出文件的 `sha256_lf` 与候选提交实际字节一致。
4. 冻结链可验证：运行 `python scripts/generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid <anchor.expected_tag_oid>`（锚定值从 `freeze-anchor-record.json` 读取，禁止硬编码或测试常量），子进程必须 exit 0；失败即阻断验收工具。
5. 上述冻结值的来源唯一为 `docs/superpowers/specs/2026-08-20-classic-texts-freeze-anchor-record.json`。工具读取该记录并**机械校验**（全部 fail-closed，任一缺失或变化即非零退出，必须另走重冻结审批才能解除）：
   - `record_type == "freeze-anchor-record"`；
   - `status == "LOCAL_ONLY"`；
   - `overall_state == "LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED"`（精确匹配）；
   - **顶层不存在 `independent_approval` 键**——该锚点记录是实现者工件，不得自证批准；若未来在记录顶层出现该键即 fail-closed；
   - `provenance` 必须是对象，且 `provenance.independent_approval == "none"`（精确匹配）。校验该值等于 `"none"` **不是**让记录自证批准，而是禁止记录在实现者控制下产生虚假的 `"approved"` 声明——字段被改成非 `"none"` 值（含 `"approved"`/缺失/类型错误）一律 fail-closed；真正的独立批准必须记录在实现者控制之外的工件中（§1.1），届时通过重冻结改变锚点与冻结链，而非改写本字段。

实现入口建议：`classic_acceptance_common.py` 提供 `verify_frozen_inputs(candidate_commit, chapter_manifest_path, identity_manifest_path)`，所有生产模式子命令在执行前调用一次。fake 模式（`--data-root`）不调用。

### 12.2 fake 模式强制标记

`--data-root <dir>` 模式仅用于单测/fake smoke/e2e：

1. 所有产出文件（sample/expansion/packet/decision/final）顶层必须包含 `"test_only": true` 与 `"data_source": {"kind": "dir", "root": "<abs path>"}`。
2. `finalize` 在 `test_only=true` 时必须非零退出并提示"fake 产物不得进入最终验收"；`decide` 在 fake 模式下允许输出报告，但报告必须带 `test_only=true`。
3. 生产模式产物不得出现 `test_only` 字段（或必须为 `false`）。
4. fake 数据不得写入 `knowledge_base/`、`docs/superpowers/specs/` 等跟踪目录；只写 `--out <dir>`（真实运行用 `.tmp/` 下运行目录）。

### 12.3 复核/仲裁身份三方互异（设计 §8.2 闭合）

1. primary 包 `reviewer_list` 必须非空；每项 finding 的 `reviewer` 必须属于该列表。
2. second-review receipt 的顶层 `reviewer`（二审人）必须**不等于** primary 任一首审 finding 的 reviewer（即首审/二审不得同一人）；receipt 内每条目 `reviewer` 必须等于顶层 `reviewer`。
3. arbitration receipt 必须显式包含两个顶层身份：`reviewer_second`（二审人，必须等于 second receipt 顶层 `reviewer`）、`arbitrator`（仲裁人）。**仲裁人必须全局独立**：`arbitrator` 不得出现在 primary `reviewer_list` 中（即不得是任何 finding 的首审人，不限于当前 entry），也必须不等于 `reviewer_second`。
4. 因 primary 包可有多个首审人，arbitration **每条目**必须记录该 critical finding 对应的 `reviewer_first`（取自 primary 该 finding 的 `reviewer`），并校验其属于 primary `reviewer_list`；该 entry 的 `reviewer_first` 必须不同于 `reviewer_second` 与 `arbitrator`（三方在该 entry 上两两互异，不同条目可有不同首审人）。第 3 条的全局独立约束保证仲裁人对**所有**条目都是真正第三方。三者均必须带非空 `reviewed_at`（ISO-8601 字符串）；每条目 `arbitrator` 必须等于顶层 `arbitrator`，且 `reasoning` 非空。
5. LOCAL_ONLY 复核/仲裁链使用**身份字段 + SHA 绑定链**（无 GPG）：second receipt 绑定 primary SHA，arbitration receipt 同时绑定 primary + second SHA；三方身份字段按上述规则两两互异即本阶段的**LOCAL_ONLY 三方身份声明与内容绑定**。它**不具备密码学签名或独立身份认证能力**（任何人都能在本地填写任意身份字符串），仅在记录层面固定"谁声称复核了什么"。远端受保护 tag 与真正的密码学签名/独立身份认证仍属正式门禁前置条件（§8.3/§10），不在本工具链范围。

### 12.4 CLI 严格解析

1. 未知 `--flag`、缺值的 `--flag`（位于行尾）、未声明的 positional 参数一律非零退出并打印 usage；禁止静默忽略。
2. 每个子命令显式声明它接受的 flag 集合与是否允许 positional；`parse_flags` 升级为 `parse_flags(argv, allowed, repeatable=())`，对不在 `allowed`/`repeatable` 中的 `--name` 抛错。
3. 必填 flag 缺失、路径不存在、SHA 长度非法（非 64 位十六进制）均 fail-closed。

### 12.5 finalize 回执绑定闭环

`finalize` 必须拒绝：

1. 决策报告未绑定却通过 `--second`/`--arbitration` 传入的回执（即传入文件存在但报告对应 SHA 字段为 null/不同）——防止调用者误以为回执已纳入最终包。
2. 决策报告绑定了 second/arbitration SHA 却未通过对应 `--second`/`--arbitration` 传入文件，或传入文件 SHA 与报告绑定值不一致。
3. `final_acceptance_package_v1.json` 的每个 SHA 字段必须与磁盘实参字节一致；`final_verdict` 必须等于报告 `verdict` 且属于 `{ACCEPT, REJECT}`。
