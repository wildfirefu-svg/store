# 经典文本历史 provenance 窄豁免设计 v28（已获有效批准）

状态：**v28 已获有效批准（A′ 批准锚点见 §0）；A′ 链已落盘并通过正式 CI（收尾记录见 §13 第 15 条）；v29.3 已获有效批准（v29 批准锚点见 §0）** ｜ 日期：2026-09-05（A′ 收尾记录 2026-09-07；v29 整合与 v29.1/v29.2/v29.3 修补及批准 2026-09-08） ｜ 冻结基点：`c5cff699fdb547bd9270acbebe1f485380848751`（branch `task/sanming-completion`）
前版：v26 已获有效批准；v27 修订 records 唯一性契约（§3/§5-E3，多重集合）；v27.1 修补 2 P0 + 1 P1 与省略号违规；v27.2 修正 E3 测试方案；v27.3 修正 E0 record_set_binding 误读当前 HEAD（P0）；v27.4 补正式 evidence 生产入口纠正链（P0）；v27.5 修补 v27.4 复审 3 P0；v27.6 修补 v27.5 复审 2 P0；v27.7 修补 v27.6 复审 2 P0；v27.8 小修补 v27.7 复审；v27.9 小修补 v27.8 复审 1 P0（rc==1 完整字段判据）+ 1 P1（校验时点归属步骤 ③）；v27.10 小修补 v27.9 复审 1 P0（「复用全部判据」措辞矛盾）；v28 新增 extractor 锚点自包含迁移条款（A′：CI 不可达旧锚点的重钉与全链重建，§4.1/§13），变更见 §13；v29 新增 §5-R 修订溯源双轨契约（未批准），v29.1 修补整合版复审 3 P0 + 2 同步遗漏（§13 第 17 条），v29.2 修补附录复审 1 P0 + 2 P1（§13 第 18 条），v29.3 小修补附录复审 2 处措辞（§13 第 19 条）。
**身份值约定：Git OID 一律 40 位十六进制；SHA-256 一律 64 位十六进制；全文一律完整值，禁止省略号截断。**

---

## 0. 提案状态

- **v26 已获有效批准**（批准锚点见下）；**v27.3 已获有效批准**（records 唯一性契约修订 + 复审修补，见 §13，批准锚点见下）；**v27.4 未获批准**（复审 NEEDS_REVISION，由 v27.5 取代）；**v27.5 未获批准**（复审 NEEDS_REVISION，由 v27.6 取代）；**v27.6 未获批准**（复审 NEEDS_REVISION，由 v27.7 取代）；**v27.7 未获批准**（复审 NEEDS_REVISION，由 v27.8 取代）；**v27.8 未获批准**（复审 NEEDS_REVISION，由 v27.9 取代）；**v27.9 未获批准**（复审 NEEDS_REVISION，由 v27.10 取代）；**v27.10 已获有效批准**（纠正链小修，见 §13，批准锚点见下）；**v28 已获有效批准**（extractor 锚点自包含迁移 A′，见 §13，批准锚点见下）。**v29.3 已获有效批准**（批准锚点见下；v29.3 含 v29.1-v29.3 修补链：整合落盘版（SHA-256 `A0FEB49F19CDD80DF8C607E9F661EFC9B2F8A13BC4054FE2CB0CB8BB0D8FE022`）2026-09-08 复审 NEEDS_REVISION——3 P0 + 2 同步遗漏，由 v29.1 修补；v29.1（SHA-256 `868509A7067EB95F63533B78EACCB0E74E26B4BE0999A8CBD0A0DF45C4E54624`）附录复审（2026-09-08）NEEDS_REVISION——1 P0 + 2 P1，由 v29.2 修补；v29.2（SHA-256 `8A8BC9637DFEFF3213B3A6D132275CA0A76D7A86569DFE59B55258592CD04E5C`）附录复审（2026-09-08）APPROVABLE_WITH_MINOR_FIX——2 处精确性措辞，由 v29.3 修补；v29.3 落盘稿 SHA-256 `D759077EEAC6AB2BC98F8B9F09A7608B975C2AB0C7BFF68F1300ACB59EF552F9`，复审（2026-09-08）APPROVABLE（设计层）后获批，修补史见 §13 第 17-19 条）。**v29/v29.1/v29.2 未批准稿均未实施**。
- **§8 口径**：v3–v19 均提议 S；**已于 2026-09-03 用户在聊天正文逐字确认**（确认语句见 §8），记为设计口径 S。
- **v26 批准锚点（2026-09-03，本聊天正文直接授权）**：
  - S 确认语句：`选择 S：本设计不豁免三本完成书的 source 获取链；三书 source_e2e_status="FAIL"，派生 source_e2e_pass=false。`
  - 批准语句：`我批准本设计（D1(c)/D2），批准锚点按 §6 记录后启动 §10 实现。`
  - 批准时 HEAD：`0909a957c5c6f4c7552014a214b5aabb2e9c6723`
  - 批准前文档 SHA-256：`FC1806E58DB8D450D84290B881146E28AEB0109E660DA07C45910793D831AC11`（v25）
- **无效批准尝试记录**：提交 `8966b1d952428f2dda39d2426ad028fd8d4ff2c4`（v22，所记批准句为流程描述/占位式措辞，非用户正文第一人称批准）与 `5c5d4a3711f6fd9664603dcfa897568fe9a87211`（v24，两句仅见于附件/代理叙述，未以纯正文出现）均被判 `INVALID_APPROVAL`。**两提交不改写历史，仅保留此标记。**
- **v27.3 批准锚点（2026-09-03，本聊天正文直接授权）**：
  - 批准语句：`我批准 v27.3 records 多重集合契约修订，并批准按 §10 继续阶段①实施。`
  - 批准时 HEAD：`63273ca074e5c38da71fe42f9a35d853bc9709ef`
  - 批准前文档 SHA-256：`0716CE441A35FD173F3372A1F8676952A22FC4F2D443CA1EB6F5C1B7BAFD789F`（v27.3）
- **v27.10 无效批准尝试记录**：此前仅据附件/代理叙述中的 `我批准 v27.10 修订版，批准锚点按 §0 记录后启动 §10-④ 纠正链实施。` 写入的锚点不属于用户聊天正文直接授权，判 `INVALID_APPROVAL`；其所记 HEAD `cbb00baf7b0e4c4cbf20257f6a8a85b840e3b953` 与后续三笔提前实施提交均保留历史、不改写。
- **v27.10 有效批准与追认锚点（2026-09-04，本聊天正文直接授权）**：
  - 批准与追认语句：`我批准 v27.10 修订版，并追认提交 a046555af87a12e15424778ffc3fd3ed26177d1c、53aabebd0fc0fa27b1eb9a5a546736c16bea0b92、6f09ee290a0781b80c4707ae2dc6a6ceb4833abc 为 §10-④ 纠正链的有效实施产物。`
  - 批准与追认时 HEAD：`6f09ee290a0781b80c4707ae2dc6a6ceb4833abc`
  - 经终审 v27.10 草案 SHA-256：`03C3B022BB61B463E5ABA613CC86C2CF1700481EE0FA25D2732E9BED4D5CA5B3`
  - 追认前工作区文档 SHA-256：`F9400AE96FA0A8F0EE96A9901D25751819DADC52CBBC238C051AF6CB999C629D`
  - 追认提交：`a046555af87a12e15424778ffc3fd3ed26177d1c`、`53aabebd0fc0fa27b1eb9a5a546736c16bea0b92`、`6f09ee290a0781b80c4707ae2dc6a6ceb4833abc`
- **v28 批准锚点（2026-09-05，本聊天正文直接授权）**：
  - 批准语句：`批准按 A′ 执行 extractor 自包含重钉，并按依赖顺序重建 freeze/evidence 与四书批准链。`
  - 批准时 HEAD：`aceef18fd8da6677c711b70de32442d57b9e6ea6`
  - 批准前文档 SHA-256：`D936F0B7BB897AD1F0AAF7D872753A8CD7BDFDC057060A58AE71C3865C1942F2`（v27.10）
- **v29.3 批准锚点（2026-09-08，本聊天正文直接授权）**：
  - 批准语句：`我批准 v29.3，按 §0 记录锚点并提交设计文档，随后编写 TDD 实施计划`
  - 批准时 HEAD：`03c02bb571dec9e2da1f7d503a292da229415d8f`
  - 批准前文档 SHA-256：`D759077EEAC6AB2BC98F8B9F09A7608B975C2AB0C7BFF68F1300ACB59EF552F9`（v29.3，130,868 bytes，纯 LF）
  - 批准范围：v29 §5-R 修订溯源双轨契约全文（5-R.0~5-R.13）+ §14 附录 A + §7/§9 同步增补；QUALITY_REPORT.json 不随设计批准一并提交
- **v27.2 修订动因**：阶段 ① 首跑冻结基点 `c5cff699fdb547bd9270acbebe1f485380848751` 时发现 `qiongtongbaojian/quarantine_rules.jsonl` 存在同 `id` 不同内容的多条记录（qtbj_001_038/qtbj_050_009/qtbj_050_011 各 2 条），与 §3「同文件 id 唯一」冲突。**按用户裁决不改历史数据**，将 records 身份契约改为 `(id, sha256)` 多重集合（§3/§5-E3）。
- **v27.3 修订动因**：v27.2 复审判 `evidence_static_check` 的 `record_set_binding` 误绑定当前 HEAD 聚合 blob（P0，v27.3）。**收窄为仅绑定 freeze 文件**（`frozen_manifest_file_sha256 == 冻结集文件字节 SHA`、`counts == 冻结集 records 多重计数`），不读取当前 HEAD 聚合 blob；当前 HEAD 与 BASE freeze 的多重集合比较由 §5-E3 独占并在 E1/E2 后执行（§4/§5-E3/§10-⑦）。
- **v27.4 修订动因**：阶段④ 复审判正式 `evidence` 生产入口未闭合（P0，v27.4）：CLI `evidence` 子命令仍以阶段①的零值 verifier fixture（OID/SHA 全零、空 replay）传入 `evidence_static_check` 且无 `--archive-root`，对已提交 evidence 执行原生 `--check` 必得 `EVIDENCE_STATIC_MISMATCH`（exit 1）；阶段④ 以未提交一次性驱动生成 evidence，不满足 §10 要求的真实 generator→verifier 生产联调。修复需改动生成器（其 blob OID 随之变化）→ 新增三阶段纠正链（§10-④）：C-evidence-wiring → C-freeze-r2 → C-evidence-r2；历史尝试 `c22b5b12d3ba5dd9ce7a9ebd5f914d4efde1109f`（freeze v1）与 `cbb00baf7b0e4c4cbf20257f6a8a85b840e3b953`（evidence v1）保留不改写。
- **v27.5 修订动因**：v27.4 复审判 3 P0：① 全文以 7 位截断前缀引用两笔历史提交，违反文档头「Git OID 一律完整 40 位」；② ④(1) C-evidence-wiring 精确文件集仅含生成器一文件，新增 CLI 参数、verifier 子进程调用与动态身份推导却无对应测试改动，不满足 TDD；③ verifier 调用契约仅写「取其 OK 输出」，未冻结调用方式与失败语义，不够 fail-closed。修复见 §13 第 8 条。
- **v27.6 修订动因**：v27.5 复审判 2 P0：① ④(1) 失败语义仅写「稳定错误码 + 非零 exit」，无字面量定义，实施者可任意映射；② 「禁止写 evidence 文件」未覆盖目标已存在的场景（C-evidence-r2 会覆盖现有 evidence 路径），失败时可能破坏既有 v1 字节。修复见 §13 第 9 条（错误码字面量冻结 + 临时文件原子替换 + 失败不覆盖断言与 sentinel 负向测试）。
- **v27.7 修订动因**：v27.6 复审判 2 P0：① 写出顺序自相矛盾——「evidence_static_check 全部通过后才构造输出」不可执行（该检查必须接收已构造的 candidate evidence）；② 错误映射不完备——未覆盖未知退出码/启动异常、rc=0 但 status!=OK 或计数≠303 或 failures 非空、rc=3 但 JSON 畸形/reason 缺失或非五值、rc=1 但输出非合法 failures schema。修复见 §13 第 10 条（冻结可执行顺序链 + rc×schema 联合全状态分类 + stderr 固定格式 + 临时文件异常清理）。
- **v27.8 修订动因（小修）**：v27.7 复审判 1 P0 + 1 P1：① 「精确 schema」未真正冻结——未钉死顶层键集合、`schema_version`、字段类型（bool 会被当作 int）与 failures 排序，实现仍可能接受额外字段/错误版本/bool 计数；② 「生成前机械断言六向身份」措辞与顺序链不一致（易被实现为 candidate 构造前校验，此时 evidence candidate 尚不存在）。修复见 §13 第 11 条。
- **v27.9 修订动因（小修）**：v27.8 复审判 1 P0 + 1 P1：① rc==1 failures 分支未复用完整字段判据——status 仅要求「字符串」、code 仅要求「非空字符串」，且未冻结 `schema_version`/计数字段类型与范围，仍允许 schema_version 错误、status 非 "OK"、bool/越界计数、§4.2 枚举外 code 被误归类 `SOURCE_REPLAY_FAILED`；② 校验时点「顺序链 ② 与 ③ 之间执行」与步骤 ③ 冲突（步骤 ③ 本身即「evidence_static_check 连同六向身份与 frozen_at_commit 断言一起执行」）。修复见 §13 第 12 条。
- **v27.10 修订动因（小修）**：v27.9 复审判 1 P0 措辞矛盾：rc==1 failures schema「逐字段复用成功分支全部判据」按字面包含 `c1_pass==c2_pass==c3_pass==303` 与 `failures==[]`，与紧随其后的分支特有判据（c1/c2/c3 允许 <303、failures 非空）自相矛盾，按字面实现 rc==1 分支永远无法命中。修复见 §13 第 13 条。
- **v29 修订动因**：四书内容验收复核中确认三命通会存在三章零产出（#25 曾有产出后被未记录操作移出、#56/#72 原因未知）与 #112 零 MCQ。补全聚合数据会使现行 E3 严格相等失效，而整体重冻结等于重跑 A′ 级全链且使旧记录历史豁免身份失效。经 v2→v18 评审循环收敛为**修订溯源双轨契约（§5-R）**：旧记录保留原历史豁免（Legacy 分区），新修订记录由修订清单 + 验收锚链 + 工具链登记独立溯源（Revision 分区），报告层组合判定；冻结工件（freeze/evidence/E/R/B1/B2/closure）全部不动。设计契约层复审 APPROVABLE（2026-09-07），待批准。
- 本设计（v27.10）已获有效批准并追认 §10-④ 三笔实施提交（2026-09-04，锚点见上）；纠正链已完成。

## 1. 既有生产契约（对齐，不自创）

- 豁免链 `classic_artifacts.py:1349-1394`（E 必填 8 字段、禁回执/批准字段、R 绑定）；生成器 `make_historical_exemption.py:25` 产 `schema_version:"1.0"`（含 `reason`）；全仓无早期无版本对象。**v2 校验按 `schema_version` 分派，扩展点即此两文件（§10-⑤）。**
- run_manifest 契约：`manifest.immutable` 是**对象**（含 targets/input_files/pre_run_mcq_ids/frozen_prompt/config_sha256 等冻结字段），非布尔；`api_generation.verification_level` ∈ {partial, full}。
- `build_artifact_manifest`（`classic_artifacts.py:1381`）：**仅枚举书目录顶层文件**（非递归），键为 `p.name`（basename），过滤后缀 `.json/.jsonl/.txt`。§5-E2 的重算必须是该生产算法的 Git-object 等价实现（不升级生产契约）。
- 质量报告：`provenance.json` 缺失 → provenance 总门禁全 false。

## 2. 工件与规范路径（逐书，路径含 `{book}`；已冻结）

| 工件 | 规范路径 |
|------|---------|
| 冻结/证据**单一生成器**（子命令 `freeze` / `evidence`；检查子命令 `--check` 各自校验自身工件） | `scripts/generate_classic_historical_freeze.py` |
| 冻结集（单份跨书） | `docs/superpowers/specs/2026-09-02-classic-texts-historical-record-freeze.json` |
| 生成证据（单份跨书） | `docs/superpowers/specs/2026-09-02-classic-texts-historical-generation-evidence.json` |
| source 链核验器（新增脚本） | `scripts/verify_sanming_source_chain.py` |
| v2 豁免工具（既有两文件扩展，§10-⑤） | `scripts/make_historical_exemption.py` + `scripts/classic_artifacts.py` |
| E 请求（逐书） | `docs/superpowers/plans/notes/approvals/2026-09-02-classic-texts-provenance-exemption-{book}-request.json` |
| R 回执（逐书） | `docs/superpowers/plans/notes/approvals/2026-09-02-classic-texts-provenance-exemption-{book}-receipt.json` |
| B2 指针（逐书） | `docs/superpowers/plans/notes/approvals/2026-09-02-classic-texts-provenance-exemption-{book}-b2-pointer.json` |

四书精确有序集：ditiansui, qiongtongbaojian, sanmingtonghui, zipingzhenquan。每书独立 B1（只提交该书 E+R 两文件）、B2（只提交该书指针一文件，且 **B2 唯一父提交 == pointer.b1_commit**）；另设单一 B3（tooling 提交，文件集见 §10-⑦）。

**校验拆分总纲（贯穿全文档）**：

```text
evidence_static_check —— 仅 Git blob/HEAD 内事实：schema、身份、冻结字段、record_count、
                           record_set_binding（**仅绑定 freeze 文件：frozen_manifest_file_sha256 ==
                           冻结集文件字节 SHA、counts == 冻结集 records 多重计数；不读取当前 HEAD
                           聚合 blob，当前 HEAD 与 freeze 的多重集合比较由 §5-E3 独占**）、
                           source_chain 的 HEAD blob SHA（pointer/manifest/
                           extracted）；不触碰外部 tar，不产生 BLOCKED。
                           失败 → 仅令该书 historical_exemption_valid=false
                           （错误码限于豁免链静态类，见 §5 优先级）。
source_chain_check  —— 外部证据：--archive-root 下的 tar（SHA/大小自钉）+ 303 章重放
                           C1/C2/C3，及执行前 verifier 工作区身份核对；
                           归档缺失/损坏/身份异常 → source_e2e_status=BLOCKED
                           （reason archive_missing|archive_sha_mismatch|archive_size_mismatch|
                           verifier_identity_mismatch|archive_root_missing），CLI exit 3，
                           独立于豁免链静态错误码，优先级最高，且**不受 E0 短路影响**（§7）。
```

## 3. 冻结集生成契约与**精确 schema**

- 数据源：仅 `git show c5cff699fdb547bd9270acbebe1f485380848751:<path>`；16 聚合路径逐一处理；存在性规范化（14 present / 2 absent；空文件 blob `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` 与缺席严格区分）。
- **frozen_at_commit 绑定（第 1 级：freeze 自身）**：`freeze.frozen_at_commit` 必须 == `c5cff699fdb547bd9270acbebe1f485380848751`（数据来源基点）。**`freeze` 生成时、`freeze --check` 时、以及正式报告入口的 E0（§5-E0，`E0_ok` 的重算输入之一）均机械断言**；填任意其他提交 → 拒绝，稳定错误码 `FROZEN_AT_COMMIT_MISMATCH`。注意：`frozen_at_commit` 语义是"数据来源的 Git 基点提交"，不是"生成动作发生时的 HEAD"。更高阶一致性见 §4/§5。
- **freeze 静态错误分化（中优-1）**：freeze validator 除 `frozen_at_commit` 外的其余静态校验——顶层字段集、`books`/`kinds` 精确集、两态文件条目、`records` 条目集合（多重集合，按 `(id,sha256)` 排序）、`counts` 一致性、重复 JSON 键、记录非对象/缺 `id`/`id` 非字符串——任一不匹配 → 稳定错误码 `FREEZE_STATIC_MISMATCH`（与 `FROZEN_AT_COMMIT_MISMATCH` 严格区分：后者仅指基点错）。
- **顶层字段精确集**：`schema_version:"1.0"`、`frozen_at_commit`（40 位，== 基点）、`generator_blob_oid`（40 位）、`books`、`counts`。缺一/多一拒绝。
- **books 精确集**：键 == 四书集合（多书/缺书拒绝）；每书 kinds 键 == `{all_rules, all_mcq, quarantine_rules, quarantine_mcq}` 精确集。
- **文件条目 schema（状态相关，交叉状态非法组合拒绝）**：

```text
present=true  -> {"present": true,  "blob_oid": <40hex>, "byte_size": <int>=0, "records": [...]}
present=false -> {"present": false, "blob_oid": null,   "byte_size": null,  "records": []}
```

- **records 条目精确集**：`{"id": <str>, "sha256": <64hex>}`；序列化按 `(id,sha256)` 排序；**同一文件允许同名 `id` 多条（多重集合，保留重复次数；同 id 可对应不同 sha256）**。
- `counts`：`{book: {kind: int}}`，与 records 实数一致。
- 解析拒绝：重复 JSON 键、记录非对象、缺 `id`、`id` 非字符串。
- canonical_record_sha256：`sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode("utf-8"))`。
- 文件序列化：全局 canonical 规则（`json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"`，UTF-8 无 BOM，LF）。
- **`freeze --check` 全等重算契约（P0，v27.1 钉死）**：`freeze --check` 必须**从冻结基点 `c5cff699fdb547bd9270acbebe1f485380848751` 的 16 个聚合 Git blob 重建完整期望 freeze 对象**（含每文件 `blob_oid`/`byte_size`/`records` 的 `(id,sha256)` 多重集合、`counts` 与顶层字段，算法同 §3 生成路径），再与磁盘文件**canonical 字节全等**比对（`json.dumps(..., sort_keys=True, indent=2) + "\n"`）。任一差异——含：把某 record `sha256` 换成另一合法 64 位值（即使同步改 `counts` 或重复次数）、增删同 id 记录、改变重复次数、篡改 `blob_oid`/`byte_size`——一律拒绝，稳定错误码 `FREEZE_STATIC_MISMATCH`（基点错仍 `FROZEN_AT_COMMIT_MISMATCH`）。**纯静态自洽不足以通过 `freeze --check`；必须以 BASE 重建全等为准。** 生成时同此契约（生成器自校验：重跑字节一致；`blob_oid` 以 `git rev-parse` 重验；`generator_blob_oid` 回填）。

## 4. `historical_generation_evidence.json` 可执行 schema

**顶层字段精确集（8 项）**：`schema_version:"1.0"`、`frozen_at_commit`（40 位）、`generator_blob_oid`（40 位）、`generator_sha256`（64 位）、`artifact_files`、`record_set_binding`、`source_chain`、`unproven_facts`。缺一/多一拒绝。

**生成器身份绑定（六向全等，fail-closed；`evidence_static_check`、`evidence` 生成时、`evidence --check` 时均机械断言）**：

```text
freeze.generator_blob_oid
== evidence.generator_blob_oid
== git rev-parse HEAD:scripts/generate_classic_historical_freeze.py
== git hash-object <工作区生成器文件>
```
**且：**
```text
evidence.generator_sha256
== sha256(git show HEAD:scripts/generate_classic_historical_freeze.py)
== sha256(<工作区生成器文件字节>)
```
任一不等 → 拒绝，稳定错误码 `GENERATOR_IDENTITY_MISMATCH`（stderr + 非零 exit）。此断言封堵"C-freeze 后改生成器再生成 evidence"的漂移路径，并封堵对 `generator_sha256` 字段本身的篡改（**负向测试**：仅篡改 `generator_sha256` 为任意 64 位值 → `evidence --check` 拒绝）。此绑定所用工件（freeze/evidence/HEAD/工作区）在 evidence 阶段均已存在，无未来依赖。

**frozen_at_commit 绑定（第 2 级：evidence 自身 + 与 freeze 一致）**（`evidence_static_check`、`evidence` 生成时、`evidence --check` 时均机械断言）：

```text
freeze.frozen_at_commit
== evidence.frozen_at_commit
== c5cff699fdb547bd9270acbebe1f485380848751
```
任一不等 → 拒绝，稳定错误码 `FROZEN_AT_COMMIT_MISMATCH`（本阶段只涉 freeze/evidence 两件已存在工件，不产生 BLOCKED）。与 E/R/pointer 的交叉一致性延后到报告门禁第 3 级（§5-E1(j)）。

**evidence_static_check 覆盖清单（仅 Git blob/HEAD 内事实；不触 tar、不产生 BLOCKED；失败错误码限于 `GENERATOR_IDENTITY_MISMATCH`/`FROZEN_AT_COMMIT_MISMATCH`/`EVIDENCE_STATIC_MISMATCH`，见 §5 优先级）**：

- §3 freeze 全部静态校验（HEAD blob；`frozen_at_commit` 错 → `FROZEN_AT_COMMIT_MISMATCH`；其余 freeze 静态错 → `FREEZE_STATIC_MISMATCH`）；
- evidence 顶层精确字段集、嵌套精确字段集与两态文件条目、record_count==冻结集长度、record_set_binding **仅绑定 freeze**：`frozen_manifest_file_sha256` == 冻结集文件字节 SHA、`counts` == 冻结集 records 多重计数（任一不匹配 → `EVIDENCE_STATIC_MISMATCH`）；**不读取当前 HEAD 聚合 blob，不做 §5-E3 比对**（当前 HEAD 与 freeze 的多重集合比较由 E3 独占，§5-E3）；
- source_chain 内 `pointer_file_sha256/pointer_blob_oid/manifest_file_sha256/manifest_blob_oid/extractor_*/parser_*/chapter_list_*` 及各 Git 输入（§4.1 路径）的 HEAD blob OID/SHA（任一不匹配 → `EVIDENCE_STATIC_MISMATCH`）；
- source_chain 内 `verifier_blob_oid/verifier_sha256` 是否与 `HEAD:scripts/verify_sanming_source_chain.py` 的 blob OID/字节 sha256 相符（**仅比对 evidence 记录值 vs HEAD blob**；不符 → `EVIDENCE_STATIC_MISMATCH`。**不在此处核对工作区 verifier 文件**——那属于 source_chain_check 的 `verifier_identity_mismatch` BLOCKED，见 §12）；
- `unproven_facts` 逐字符串相等（不匹配 → `EVIDENCE_STATIC_MISMATCH`）。

**source_chain_check 覆盖清单（外部证据；独立产生 BLOCKED；不受 E0 短路影响）**：

- **执行前 verifier 工作区身份核对**：`git hash-object <工作区 verifier 文件>` 必须 == `HEAD:scripts/verify_sanming_source_chain.py` 的 blob OID（disk==HEAD）；不一致 → BLOCKED（reason `verifier_identity_mismatch`）——**此比较与 evidence_static_check 中"记录值 vs HEAD blob"是两条不同链，不重复**；
- `--archive-root` 下 tar 的 sha256/字节数 vs evidence `source_chain.tar_*` 与 pointer `archive_sha256/archive_size` 自钉；
- replay C1/C2/C3 全量（303 章，§4.2）；
- 归档缺失/损坏/身份异常 → BLOCKED（reason 见 §2 总纲），与豁免链静态错误码无交集。

**嵌套精确字段集与类型**（**两种完整状态集，字段名与个数逐字冻结；evidence 不内联 records，冻结集为唯一记录权威**）：

```text
artifact_files: {book: {kind: <文件条目>}}
  present=true  -> {"present": true,  "blob_oid": <40hex>, "byte_size": <int>=0,
                    "file_sha256": <64hex>, "record_count": <int>=0}
  present=false -> {"present": false, "blob_oid": null,   "byte_size": null,
                    "file_sha256": null,   "record_count": 0}
  交叉状态非法组合（present=false 而 blob_oid/byte_size/file_sha256 非 null、
  record_count 非 0，或 present=true 缺任一实值字段）一律拒绝；
  且机械断言 record_count == 冻结集对应文件 records 的长度。
record_set_binding: {"frozen_manifest_file_sha256": <64hex>, "counts": {book: {kind: int}}}
source_chain: {"sanmingtonghui": {
    "pointer_file_sha256": <64hex>, "pointer_blob_oid": <40hex>,
    "tar_sha256": <64hex>, "tar_size": <int>, "tar_relative_path": "cf984581ea0a8e8028949733ed98c5bb85f54972723033c489b34e51b48d7cf9.tar",
    "manifest_file_sha256": <64hex>, "manifest_blob_oid": <40hex>,
    "extractor_blob_oid": <40hex>, "extractor_sha256": <64hex>,
    "parser_blob_oid": <40hex>, "chapter_list_blob_oid": <40hex>,
    "verifier_blob_oid": <40hex>, "verifier_sha256": <64hex>,
    "replay": {"chapters_expected": 303, "c1_pass": <int>, "c2_pass": <int>,
               "c3_pass": <int>, "failures": [...]}}}
unproven_facts: [<str>, ...]（**完整 JSON 字面量见 §4.1，逐字符串冻结**）
```

**逐事实重算表**（`--check` 与报告入口 E0 均零写入重算；Git OID 从 `git rev-parse`，SHA-256 从字节；静态行失败 → 该书 `historical_exemption_valid=false`，错误码见 §5 优先级；`source_chain.tar/replay` 行失败 → BLOCKED）：

| 事实 | 输入 | 重算 |
|------|------|------|
| frozen_at_commit（freeze） | 生成器基点常量 | 第 1 级：`freeze.frozen_at_commit == BASE`（错 → FROZEN_AT_COMMIT_MISMATCH） |
| freeze 其余静态 | 冻结基点 Git 对象 | schema/字段集/records/counts（错 → FREEZE_STATIC_MISMATCH） |
| frozen_at_commit（evidence） | freeze + evidence + 基点常量 | 第 2 级：`freeze.frozen_at_commit == evidence.frozen_at_commit == BASE`（错 → FROZEN_AT_COMMIT_MISMATCH） |
| generator_blob_oid / generator_sha256 | HEAD blob + 工作区文件 + freeze 镜像 | 六向全等断言（上文；错 → GENERATOR_IDENTITY_MISMATCH） |
| artifact_files.* | 冻结基点 Git 对象 | `git rev-parse` / `git cat-file -s` / `git show`+sha256 |
| record_count | 冻结集对应 records 长度 | 解析比对（不符 → EVIDENCE_STATIC_MISMATCH） |
| record_set_binding | 冻结集文件 | 校验 `frozen_manifest_file_sha256` == freeze 文件字节 SHA、`counts` == freeze records 多重计数（不符 → EVIDENCE_STATIC_MISMATCH；**不读当前 HEAD 聚合 blob**，当前 HEAD 多重集合比对归 E3） |
| source_chain.pointer/manifest/extracted（静态） | **HEAD Git blob**（§4.1 精确路径） | `git show`+sha256（不触 tar；不符 → EVIDENCE_STATIC_MISMATCH） |
| source_chain.extractor/parser（静态） | Git 对象（§4.1 全长身份） | blob oid 比对 + sha256（不符 → EVIDENCE_STATIC_MISMATCH） |
| source_chain.verifier（静态，仅记录值 vs HEAD） | `HEAD:scripts/verify_sanming_source_chain.py` | `git rev-parse` + `git show`+sha256，对比 evidence `verifier_blob_oid/verifier_sha256`（不符 → EVIDENCE_STATIC_MISMATCH；**不核对工作区文件**） |
| source_chain.verifier（执行前，工作区 vs HEAD） | 工作区 verifier 文件 | `git hash-object` == HEAD blob OID；不符 → BLOCKED `verifier_identity_mismatch`（§12） |
| source_chain.tar（外部） | `archive_root` 下的 `tar_relative_path` | 读字节 sha256 + 字节数（自钉：与 evidence `source_chain.tar_*` 及 pointer `archive_sha256`/`archive_size` 比对）；缺/损 → BLOCKED |
| source_chain.replay（外部） | §4.2 核验器 + tar | 调用输出并断言 303/303；缺/损 → BLOCKED |
| unproven_facts | §4.1 冻结字符串数组 | 逐字符串相等比对（不符 → EVIDENCE_STATIC_MISMATCH） |

**语义负向测试**：篡改任一已证事实并同步重算文件级 SHA → `--check` 拒绝；生成器被修改 / 仅篡改 `generator_sha256` → `GENERATOR_IDENTITY_MISMATCH`；freeze 或 evidence 声明非基点 `frozen_at_commit` → `FROZEN_AT_COMMIT_MISMATCH`；freeze 的 schema/`counts`/record SHA 篡改 → `FREEZE_STATIC_MISMATCH`；evidence 的 `record_count`/`record_set_binding`/任一静态 blob SHA/`unproven_facts` 篡改 → `EVIDENCE_STATIC_MISMATCH`；tar 缺失但其余静态全过 → 静态 PASS、`source_chain` BLOCKED（两态分离，互不污染）；verifier 记录值≠HEAD → `EVIDENCE_STATIC_MISMATCH`（静态）、工作区 verifier≠HEAD → `verifier_identity_mismatch` BLOCKED（执行前），两比较各自独立；批准链落地后 freeze/evidence 基与 E/R/pointer 交叉不一致 → `BASELINE_COMMIT_MISMATCH`。

### 4.1 未证事实（**完整 JSON 字面量，逐字符串冻结**）与精确路径/身份（全长，无省略号）

```json
"unproven_facts": [
  "四书聚合工件集（all_rules/all_mcq/quarantine_rules/quarantine_mcq）背后没有满足正式契约的归档模型 run manifest（正式契约要求：manifest_sha256 存在，manifest.immutable 为满足冻结字段契约的对象，api_generation.verification_level 等于 full）。",
  "本豁免仅覆盖上述历史生成运行缺正式 run manifest 这一事实，不延伸到任何未来生成运行。",
  "三本完成书（ditiansui/zipingzhenquan/qiongtongbaojian）的原始文本获取过程不被本证据证明（见设计 §8=S）。"
]
```

不豁免：三本完成书原始文本获取过程（§8=S 已确认）。

```text
BASE  = c5cff699fdb547bd9270acbebe1f485380848751
SNAP  = knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/b4e9be580dbecd3e233d3adbe163299f06c6ca5174309dc83e8f14433796aaa2
pointer    = <SNAP>/RESPONSE_ARCHIVE_POINTER.json   blob b423b726afe4890618b5f0796162ba6d4120b7da  347 B    sha256 93b2b140e54c6f9e08d3d91c00a01a5e6d0443e76bd77b282f3467a6d3763c04
manifest   = <SNAP>/source_manifest.json            blob 662fbe6013c11b3bc58a3393ef1168ea82b05eca  216377 B sha256 7024760851374217ec3c61422e70fbd2d6a1deb3d48d1fa594d120215fdace61
active_ptr = knowledge_base/classic_texts/sanmingtonghui/formal/active_source_snapshot.json
                                                      blob 4de1c1a6565e559bd86d6ca411c7582f07cbce82  187 B    sha256 dadf5b253961500d86a8c1e22841e0f2f96dee56d62b005f76285f16a1540eca
parser     = scripts/fetch_sanming_chapters.py      blob 1842a8d5c732b19a233baa72fd7fec496217722d（BASE 与新旧锚点 f64a25ddd8ef43aef9ad75e189e72a4f9d373938/054db22d6cc319aaa9db47443d1c9c7a7dfb9046 同 blob，已实测）
chapters   = knowledge_base/classic_texts/sanmingtonghui/chapter_list.txt
                                                      blob 70c5029c29c3443ea2b149a749e7ba6aef904779（BASE 与锚点同 blob，已实测）
extracted  = <SNAP>/extracted/raw_001.txt .. raw_383.txt  （383 个，HEAD Git blob 读取）
tar        = <archive-root>/cf984581ea0a8e8028949733ed98c5bb85f54972723033c489b34e51b48d7cf9.tar
                                                      7,127,040 B  sha256 cf984581ea0a8e8028949733ed98c5bb85f54972723033c489b34e51b48d7cf9（archive-root 为运行参数，相对路径/SHA/大小冻结于此与指针）
extractor  = git 对象 054db22d6cc319aaa9db47443d1c9c7a7dfb9046:scripts/fetch_sanming_full.py
                                                      blob 4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463  sha256 afa691ef3568c94cc34a04da60e75c492f1faba6cfd8c2e8c16827ac33f6ab1d
```

注：`active_ptr` 记录的 `source_manifest_sha256:"ed06d58273072ac8bafffa29962ce95e88a85b7e8edb3b430cde1b42b8bd0b5d"` 语义未钉（实测 ≠ manifest 文件字节 SHA `7024760851374217ec3c61422e70fbd2d6a1deb3d48d1fa594d120215fdace61`，≠ sort_keys canonical 形式 `b5b3eef94242b19133c8ae37a3c63dd2d0a008298b5945fd6f117c5d4c61f7aa`）——**不作为重算事实**，仅历史 builder 输出原样记录；证据绑定以文件字节 SHA 为准。

**extractor 锚点迁移条款（v28/A′）**：旧锚点 `f64a25ddd8ef43aef9ad75e189e72a4f9d373938` 仅存在于未推送的本地历史，正式 CI checkout 不可达（PR #3 全量测试 36 项异常同源于此）。允许将 extractor 提交锚点迁移至新提交，**唯一充要条件**：`git rev-parse <新锚点>:scripts/fetch_sanming_full.py` 严格等于 blob `4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463`（字节全等，sha256 `afa691ef3568c94cc34a04da60e75c492f1faba6cfd8c2e8c16827ac33f6ab1d` 不变）。现锚点迁移至 `054db22d6cc319aaa9db47443d1c9c7a7dfb9046`（该提交将 extractor 原始字节入当前分支，`git hash-object` 实测全等）。**迁移后果（强制，不可省略）**：generator/verifier 的 `EXTRACTOR_COMMIT` 常量更新 → 两脚本 blob 变化 → freeze 内嵌 generator 身份与 evidence 内嵌 generator/verifier 身份失效 → 必须按 §10 顺序重生成 freeze/evidence（真实 303/303 重放）→ 四书 E→R→B1→B2 批准链整体重建 → B3 常量与 closure 工件刷新 → 本地全门禁后推送重跑 CI。旧 freeze/evidence/E/R/B1/B2/B3 常量与 closure 保留历史不改写，由新链取代。

### 4.2 source 链核验器（Git 跟踪入口，精确输出 schema）

- 调用：`python scripts/verify_sanming_source_chain.py --base <40hex> --archive-root <dir>`（`--base` 默认冻结基点常量；**正式报告链禁止非冻结 base**，见 §7）。本核验器即 `source_chain_check` 的执行体。
- **实现冻结**：`_FOOTER` 与 `_extract_content` 从 Git 对象 `4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463`（提交 `054db22d6cc319aaa9db47443d1c9c7a7dfb9046` 的树内 blob；与未推送历史提交 `f64a25ddd8ef43aef9ad75e189e72a4f9d373938` 同 blob，见 §4.1 迁移条款）**AST 提取**后执行，禁止手工副本；同源测试断言提取片段字节 == blob 内源码段。`parse_chapter_list` 从 Git blob `1842a8d5c732b19a233baa72fd7fec496217722d` 加载；`chapter_list.txt` 从 Git blob `70c5029c29c3443ea2b149a749e7ba6aef904779` 读取。
- Git 输入一律 Git blob 读取；tar 从 `--archive-root` 读取并以 evidence `source_chain.tar_*` 及指针 `archive_sha256`/`archive_size` 自钉；**归档缺失/损坏/身份不符 → BLOCKED 状态（独立于 C1 失败，亦独立于豁免链静态错误）**。**BLOCKED reason 统一枚举（五值，报告层同用此枚举）**：

```text
archive_missing | archive_sha_mismatch | archive_size_mismatch | verifier_identity_mismatch | archive_root_missing
{"schema_version": "1.0", "status": "BLOCKED", "reason": <上述枚举值>}
```

  exit 码：0 = 全过；1 = 存在 failures；3 = BLOCKED。
- 正常输出 schema（canonical 序列化写 stdout）：

```text
{"schema_version": "1.0", "status": "OK", "chapters_expected": 303,
 "c1_pass": <int>, "c2_pass": <int>, "c3_pass": <int>, "failures": [...]}
```

- **failures 条目精确集**：`{"chapter": <int>, "check": "C1"|"C2"|"C3", "code": <str>, "detail": <str>}`；按 `(chapter, check, code, detail)` 排序（同章同 check 多错误时输出确定）；稳定错误码枚举：`ARCHIVE_MEMBER_MISSING, C1_SHA_MISMATCH, C2_HEADING_NOT_FOUND, C2_NO_BODY, C2_EXTRACTION_ERROR, C2_SHA_MISMATCH, C3_SHA_MISMATCH`。
- **C1**：∀n∈[81,383]：sha256(tar 成员 `responses/raw_{n:03d}.html` 字节) == manifest.chapters 中 `chapter_index==n` 记录的 `response_body_sha256`。
- **C2**：∀n：sha256(`_extract_content(member.decode("utf-8", errors="replace"), n, title_n).encode("utf-8")`) == 同记录 `extracted_text_sha256`；`_extract_content` 为 Git 对象 `4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463` 内函数的 AST 提取执行；`title_n` = `parse_chapter_list(chapter_list blob 70c5029c29c3443ea2b149a749e7ba6aef904779)` 第 n 项 title。
- **C3**：∀n：sha256(`git show <base>:<SNAP>/extracted/raw_{n:03d}.txt`) == C2 重放 sha。

## 5. 豁免有效性（顺序即规则，逐书成立）

**provenance 状态判定（三态，先于 E0）**：

```text
provenance_state = VALID   = provenance.json 存在 ∧ validate_provenance 通过
                 = INVALID = provenance.json 存在 ∧ validate_provenance 失败
                 = MISSING = provenance.json 不存在

E0_ok = 每次正式报告都重新计算（§5-E0 三步静态校验的全部通过）；无论 provenance_state
        为何，E0 都要执行并产出 E0_ok，但 E0_ok 仅在 MISSING 状态参与 historical_exemption_valid。
```

**E0 同源静态校验入口（每次正式报告都重新计算 E0_ok；不信任任何历史 `--check`/提交时运行记录；全新 clone 或工件被替换后同样重新执行）**：

```text
① 生成器身份六向校验（§4：freeze/evidence/HEAD blob/工作区 hash-object + generator_sha256；
   失败 → GENERATOR_IDENTITY_MISMATCH → E0_ok 不成立）
② 对 HEAD Git blob 执行 freeze validator（§3 全部静态校验；
   失败 → FROZEN_AT_COMMIT_MISMATCH（基点）/ FREEZE_STATIC_MISMATCH（结构）→ E0_ok 不成立）
③ 对 HEAD Git blob 执行 evidence_static_check（§4 全部静态校验；
   失败 → GENERATOR_IDENTITY_MISMATCH / FROZEN_AT_COMMIT_MISMATCH / EVIDENCE_STATIC_MISMATCH
   → E0_ok 不成立）
E0_ok = ① ∧ ② ∧ ③ 全部通过
```

**错误优先级冻结（仅覆盖豁免链静态类错误；source BLOCKED 独立且优先进制）**：

```text
GENERATOR_IDENTITY_MISMATCH   （优先）
→ FROZEN_AT_COMMIT_MISMATCH   （次）
→ FREEZE_STATIC_MISMATCH      （再次，freeze 结构/记录/计数不匹配）
→ EVIDENCE_STATIC_MISMATCH    （再次，evidence 结构/计数/静态 SHA 不匹配）
→ BASELINE_COMMIT_MISMATCH    （最后，仅在 §5-E1(j) 六方 baseline 阶段产生）
```

实现按此顺序短路，输出确定、不随实现细节漂移；单输入命中首个错误码即停。E0 任一步失败 = `E0_ok=false`，**仅在 MISSING 状态使 `historical_exemption_valid=false`，不回写 `provenance_ok`、不影响 VALID 状态的 `provenance_admissible=true`**。`source_chain_check`（含外部 tar/重放与执行前 verifier 工作区核对）不在 E0 内；其 BLOCKED 语义见 §4.2/§7，**即便 E0 失败，`source_chain_check` 仍无条件独立执行（§7），任何时候 BLOCKED 都决定顶层 exit=3**。

**E1 工件链**（E0_ok 通过且 provenance_state==MISSING 时执行；报告读取冻结常量 `APPROVAL_B2_BY_BOOK[book]`（§5.1），不接受任何 CLI SHA；**物理顺序如下，(j) 六方 baseline 置于所有 E/R/pointer 校验之后**）：

   - (a) B2 存在，B2 树规范路径含指针，指针字节 == 当前 HEAD 指针 blob；
   - (b) **指针自身校验**：`schema_version=="1.0"`、`book`==常量键==E.`book`、`e_path`/`r_path` 逐字等于该书规范路径；
   - (c) **parent_commit 三方一致（逐书成立）**：`E.parent_commit == R.parent_commit == B1 实际父提交`（40 位；每本书的该值为生成该书 E 时的 HEAD，见 §10 逐书循环）；
   - (d) **B2 的唯一父提交 == pointer.b1_commit**；
   - (e) B1 树含 E/R，且 **B1 相对其父的 diff 文件列表恰为该书 E/R 两规范路径**；B2 相对其父的 diff 恰为该书指针一规范路径；
   - (f) E/R 文件字节 sha256 == 指针 `e_sha256`/`r_sha256`；
   - (g) E 通过 v2.0 `verify_exemption_request`（canonical E sha == R.`exemption_request_sha256`）；R 通过 v2.0 `verify_approval_receipt`（10 字段）全镜像复核；
   - (h) `merge-base --is-ancestor c5cff699fdb547bd9270acbebe1f485380848751 b1_commit` 且 `--is-ancestor b1_commit b2_commit`；
   - (i) E 登记的冻结集/证据文件 SHA-256 == **B2 树**与 **HEAD 树**中对应 blob 的字节 sha256（双树一致）；
   - (j) **baseline_commit 六方一致（第 3 级，最后执行）**：`pointer.baseline_commit == E.baseline_commit == R.baseline_commit == freeze.frozen_at_commit == evidence.frozen_at_commit == "c5cff699fdb547bd9270acbebe1f485380848751"`。E/R/pointer 的定位、schema、路径、SHA 与身份已由 (a)–(g) 验证，freeze/evidence 侧以 E0 刚校验过的当前值参与交叉比对；不一致 → `BASELINE_COMMIT_MISMATCH`。

**E2 权威重算（E/R 不得自证）**：

   - **artifact_manifest_sha256**：生产算法（`build_artifact_manifest`，仅顶层、basename 键）的 **Git-object 等价重算**——`git ls-tree -z c5cff699fdb547bd9270acbebe1f485380848751 -- <book_dir>/`（**非递归；按 NUL 分隔记录解析，每条记录格式 `<mode> SP <type> SP <oid> TAB <path>`，禁止按行或空格切分**；仅直接子项、仅 blob 类型），过滤后缀 ∈ {`.json`,`.jsonl`,`.txt`}，键 = 条目名（basename），逐文件 `git show <base>:<book_dir>/<name>` 字节计算 sha256，构造 `{"sha256_by_path": {<basename>: <64hex>}, "git_ref": "c5cff699fdb547bd9270acbebe1f485380848751", "git_verified": true}`，取其 canonical JSON（`json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",",":"))`）之 sha256；**E.`artifact_manifest_sha256` == R 镜像 == 该重算值**，三方全等。**负向测试**：构造含中文与空格的路径条目，验证 NUL 解析正确而按行/空格切分实现被判拒绝。
   - **validator_code_sha256**：权威来源 = Git 对象 `git show c5cff699fdb547bd9270acbebe1f485380848751:scripts/validate_classic_distillation.py`；重算其字节 sha256；**E == R == 重算值**，三方全等。
   - 任一三方不等 → 豁免失效。

**E3 记录集严格相等（多重集合）**：**E3 是唯一读取当前 HEAD 聚合 blob 并与 BASE freeze 多重集合比较的阶段，且在 E1/E2 之后执行**（E0 的 `record_set_binding` 仅绑定 freeze，不读当前 HEAD 聚合 blob；E1/E2 亦不触当前 HEAD 聚合 blob 的多重比较，见 §4）。HEAD 聚合 blob 逐记录 `(kind,id,sha)` 与冻结集**多重集合**严格相等——按 `(kind,id,sha)` 排序后逐项比对，保留重复次数，**不得用普通 `set` 丢失重复**。任一不匹配 → `E3_ok=false`。**v29（已获 v29.3 批准；条款随 §5-R 实施启用）**：启用 §5-R 修订溯源后，本条由 §5-R.5 ⑤ 等式 `Counter(HEAD) == Counter(freeze) + Counter(manifest)` 取代（Legacy 分区逐条严格相等 + Revision 分区被清单逐条覆盖）；未启用修订（manifest 不存在且无已验收锚）时本条语义不变。

**公式（三态闭合）**：

```text
provenance_state = VALID:
    historical_exemption_valid = false（NOT_APPLICABLE）
    provenance_admissible = true
provenance_state = INVALID:
    historical_exemption_valid = false
    provenance_admissible = false
    （豁免链不被咨询；INVALID 是正式 provenance 失败，不得用豁免绕过）
provenance_state = MISSING:
    historical_exemption_valid = E0_ok AND E1_ok AND E2_ok AND E3_ok
    provenance_admissible = historical_exemption_valid
```

`provenance_ok` 语义不变（仅由 `validate_provenance` 决定，且仅在 `provenance.json` 存在时计算，即 VALID/INVALID 之判定源）；E0 每次重算，但仅 MISSING 下影响 admissible；VALID 下 E0 失败不改写 `provenance_admissible=true`，INVALID 下豁免不被咨询。当前基点四书 `provenance.json` 均缺失 → 实际运行走 MISSING。

### 5.1 B3 常量 schema 与验证

```python
APPROVAL_B2_BY_BOOK = {"ditiansui": "<40hex>", "qiongtongbaojian": "<40hex>",
                       "sanmingtonghui": "<40hex>", "zipingzhenquan": "<40hex>"}
```

验证规则：键集合 == 四书精确集（缺书/多书拒绝）；值匹配 `^[0-9a-f]{40}$`（占位符/全零拒绝）；四值互异；`HEAD` 是每个 B2 的后代（`merge-base --is-ancestor b2 HEAD`）；任一违反 → 报告直接 fail-closed。

### 5-R. 修订溯源双轨契约（revision rail；v29 新增、v29.1/v29.2/v29.3 修补，已获 v29.3 批准生效）

**5-R.0 总则与适用范围**：

- **双轨模型**：对每本书、每种聚合（`KINDS` 全集，含 `quarantine_rules`/`quarantine_mcq`），HEAD 记录多重集合（按 `(id, sha256)`）分解为两个不相交分区——**Legacy 分区** = HEAD ∩ BASE freeze（沿用现行 E0-E3 历史豁免，身份不变）；**Revision 分区** = HEAD − BASE freeze（不适用历史豁免，须由修订清单独立溯源）。组合判定：`provenance_admissible = 豁免链 OK ∧ (Revision 分区为空 ∨ revision manifest 校验通过)`。
- **整体重冻结路径否决**：`BASE_COMMIT` 固定 `c5cff699fdb547bd9270acbebe1f485380848751`，重跑 freeze 只重导出同一历史基点；冻结修复后 HEAD 须换基点并重定义豁免范围，成本等于 A′ 级全链且使旧记录历史豁免身份失效。本设计冻结工件（freeze/evidence/E/R/B1/B2/closure）**全部不动**。
- E1 与 E2 不受 HEAD 聚合修改影响，语义不变，但二者职责不同：**E1 消费批准提交（B1/B2）与 HEAD 工件并交叉绑定**（§5-E1 (a)-(i)：从 B1/B2 树与 HEAD 树读取 E/R/指针 blob 并做双树一致核验）；**E2 才从冻结基点 `c5cff699fdb547bd9270acbebe1f485380848751` 重算** `artifact_manifest_sha256`/`validator_code_sha256`（§5-E2：`git ls-tree`/`git show <base>` 权威重算）。不得把两者混写为「都读 BASELINE 历史 blob」。
- **适用书**：仅具 evidence `source_chain` 锚的书（当前仅 sanmingtonghui）；其他书目录出现 revision manifest → fail-closed（`REVISION_SOURCE_UNVERIFIABLE`），不静默放行。
- 不更新 `progress.json`（除非单独批准）；不动隔离区存量（另案分诊）。

**5-R.1 工件、路径与信任根**：

| 工件 | 路径 | 性质 |
|---|---|---|
| 修订清单 | `knowledge_base/classic_texts/sanmingtonghui/revision_manifest.json` | 被跟踪，随内容提交 C 更新 |
| 验收锚 | `docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/accepted_anchors.jsonl` | 被跟踪，append-only |
| 工具链登记 | `docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/toolchain_registry.jsonl` | 被跟踪，append-only |
| 信任根常量 | `REVISION_ANCHOR_HEAD` / `TOOLCHAIN_REGISTRY_HEAD`（`scripts/generate_quality_report.py`） | 代码常量，分别仅随 V / R 提交更新 |

- **初始质量基线**（仅首批门禁向量重跑点，冻结字面量）：`03c02bb571dec9e2da1f7d503a292da229415d8f`。
- **初始工具链基点 T₀**：实现本 §5-R 并通过评审的真实提交（OID 于实现验收时冻结入本文档；**不得由 `03c02bb571dec9e2da1f7d503a292da229415d8f` 兼任**——旧基线无修订工具链）。
- 信任边界声明：哈希链与登记结构**不认证批准人身份**；两个头常量是受评审流程控制的信任根，其更新仅经 R/V 提交（diff 可见）。

**5-R.2 修订清单 schema**：

- 顶层字段集（缺一/多一拒绝）：`schema_version=="1.0"`、`book=="sanmingtonghui"`、`freeze_base_commit=="c5cff699fdb547bd9270acbebe1f485380848751"`、`batches`。
- **空基线 manifest 字面量**（零批次的规范形态，设计冻结）：`{"schema_version":"1.0","book":"sanmingtonghui","freeze_base_commit":"c5cff699fdb547bd9270acbebe1f485380848751","batches":[]}`。
- 批次字段集：`batch_id`（`R25`/`B56`…，全局单调不重复）、`date`（ISO-8601）、`author`（纯信息字段，不构成身份认证）、`records`。
- 记录字段集：`kind` ∈ {`rule`,`mcq`}、`id`、`sha256`、`source_chapter`、`snapshot_path`、`snapshot_sha256`、`historical_basis`（可为 null——全新命题）。
- `sha256` 冻结算法：对 HEAD 聚合中该记录调用既有 `_record_entry`（`sha256(_canonical(record).encode("utf-8"))`，`_canonical` 即 §3 canonical_record_sha256：`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))`）；不另造序列化。
- `historical_basis`（恢复类记录必填，全新命题为 null）：`{commit, path, source_chapter, record_content_sha256, match_count}`——验证器从 `git show <commit>:<path>` 重算：按 `source_chapter` 过滤后，与 `record_content_sha256`（该历史记录 `_canonical` 序列化字节 SHA-256）匹配的记录必须**恰好 1 条**；不得使用冲突 id 定位。
- `snapshot_path` **路径白名单**：仅允许 `<SNAP>/extracted/raw_{NNN:03d}.txt`（NNN 由 `source_chapter` 经 chapter_list 唯一反解）；根目录 `raw_*.txt`、任何 `..` 逃逸、错章一律拒绝。

**5-R.3 锚、genesis 与登记 schema**：

- **genesis 对象**（设计冻结）：`{"schema":"sanmingtonghui-revision-genesis-v1","book":"sanmingtonghui","freeze_base_commit":"c5cff699fdb547bd9270acbebe1f485380848751","b2_commit":"ccb833a46977c8274c0fb8c8c79c1b2f5d494c5e"}`；`genesis_sha = sha256(_canonical(genesis对象).encode("utf-8"))`（64-hex，实现重算比对）。
- 锚条目字段集（拒绝未知字段）：`{batch_id, content_commit(40-hex), manifest_sha256_after(64-hex), prev_anchor_sha256(64-hex), toolchain_commit(40-hex), date(ISO-8601)}`。JSONL 一行一锚；每行须满足「行字节(去换行) == `_canonical(解析对象).encode("utf-8")`」（格式自检）。
- **锚链哈希**：`h_0 = genesis_sha`；`h_i = sha256(h_prev.encode("ascii") + _canonical(anchor_i).encode("utf-8")).hexdigest()`；`REVISION_ANCHOR_HEAD` 常量 == h_n。首条 `prev_anchor_sha256 = genesis_sha`。
- `manifest_sha256_after = sha256(_canonical(manifest@content_commit).encode("utf-8"))`（canonical 层，非原始文件字节；文件缩进/换行格式自由但内容被锚定）。
- 登记条目字段集：`{toolchain_commit(40-hex), date, review_ref, prev_registry_sha256(64-hex，首条 = genesis_sha)}`；登记链哈希与锚链同公式；`TOOLCHAIN_REGISTRY_HEAD` 常量 == 登记链头。
- 空锚文件（存在但零行）：链头 = genesis_sha，仅当常量同值时合法；常量为后续值 → `REVISION_CHAIN_STALE`。锚文件缺失：走 MISSING×不存在矩阵行。

**5-R.4 提交流程（T → R → C → 候选验证 → 批准 → V → 默认复验）**：

- **T（工具链提交）**：普通评审提交，diff 限于冻结工具链文件集 `{scripts/generate_quality_report.py, scripts/classic_artifacts.py}` ∪ 对应测试文件；自身不含指向自己的引用（无自引用）。首个 T 即 T₀；工具链升级 = 新 T 走独立评审。
- **R（登记提交）**：diff 限 `{toolchain_registry.jsonl, scripts/generate_quality_report.py}`——登记文件追加一行 + 脚本**唯一替换** `TOOLCHAIN_REGISTRY_HEAD` 值（替换该常量值后两版本其余字节完全相同）；@R 常量 == @R 登记链头。登记是过去时操作：候选验证时 T 必已在登记集。
- **C（内容提交）**：聚合数据追加 + manifest 增量批次；**manifest 不记录自身 commit/SHA**（无自引用）。C 落地时修订未接纳是预期状态（该时点报告允许 FAIL）。
- **候选验证**（§5-R.6 CLI）：exit 4 + `revision_state=PENDING_ACCEPTANCE` 后由用户聊天正文批准。
- **V（验收提交）**：diff 限 `{accepted_anchors.jsonl, scripts/generate_quality_report.py}`——锚追加一行（引用 C 的 OID 与候选所用 T，**不含 V 自身 OID**）+ 脚本唯一替换 `REVISION_ANCHOR_HEAD`（**单常量**——V 不得顺带改 `TOOLCHAIN_REGISTRY_HEAD`，工具链准入变更只能走 R）。V 可按普通 Git 流程构造，无循环。V 的唯一父提交可为 C（内容提交）或工具链升级提交，**不要求 P 自身已验收**。
- **默认复验**：V 落地后在 HEAD 运行默认模式；「复验通过」= `revision_state=ACCEPTED` ∧ 指定检查通过 ∧ 无退化——**不要求整体 exit 0**（允许红项保留时默认退出仍为 1）。V 成为下一批的验收基线提交。

**5-R.5 唯一执行入口与管线（顺序即错误优先级，单次读取 HEAD 输入）**：

`evaluate_revision_rail(git_root, book, freeze, evidence)` 是修订验证的**唯一入口**，完整执行①-⑦；现行 `_e3_multiset_check` 并入（rail 输出即 E3 结果）；`evaluate_provenance_admissibility` 调用一次、只消费结果；报告组合层零二次调用。各阶段短路，重算不信任文件自述：

```text
① manifest 解析（strict JSON，UTF-8，BOM/尾随内容拒绝）        → REVISION_MANIFEST_MALFORMED
② schema/路径白名单/记录哈希重算(_record_entry)/重复拒绝        → REVISION_MANIFEST_MALFORMED
③ 锚链核验（链哈希逐条 + 链头==REVISION_ANCHOR_HEAD@HEAD）      → REVISION_CHAIN_STALE
④ HEAD manifest vs 基线比较（见下）                            → REVISION_HISTORY_DRIFT / REVISION_UNACCEPTED / REVISION_CHAIN_STALE
⑤ 多重集合等式：Counter(HEAD) == Counter(freeze) + Counter(manifest)（全 KINDS，Counter 计数，禁 set）→ REVISION_PARTITION_MISMATCH
⑥ 源身份重算（§5-R.8 锚定链）                                   → REVISION_SOURCE_UNVERIFIABLE
⑦ 内容检查（original_text 去空白子串匹配对应 extracted 文件；mcq 外键指向 HEAD 存在规则、G8 形态）→ REVISION_SOURCE_UNVERIFIABLE
```

- **④ 比较规则**（canonical 层：两侧均解析后 `_canonical(obj).encode("utf-8")` 比较，原始文件字节格式不参与）：
  - 默认模式：`_canonical(HEAD manifest) == _canonical(最新已验收 C 的 manifest)` → 通过；HEAD == C + 恰好一个全新批次（前缀逐对象相等）→ `REVISION_UNACCEPTED`（合法候选形态但未验收）；HEAD 批次集 ⊂ C（删批）→ `REVISION_CHAIN_STALE`；其他（同 ID 改内容/改前缀/多批追加）→ `REVISION_HISTORY_DRIFT`。
  - 候选模式：`n = len(accepted.batches)`（零锚时空基线的 `batches=[]`）；要求 `len(candidate.batches) == n+1` ∧ `candidate.batches[:n]` 与已验收数组**逐对象** canonical 相等 ∧ `candidate.batches[n].batch_id` 全新；违者按删批/改前缀/多批分别归 STALE/DRIFT/UNACCEPTED。
  - ⑤ 等式失败附三分类明细：`legacy_mutated`（freeze 内记录被改）/ `unmanifested_extra`（清单外新增）/ `manifest_orphan`（清单条目在 HEAD 缺失）。
- **manifest 重复规则**：manifest 内同一 `(id, sha256)` 出现两次 → malformed；manifest 与 freeze 交集非空（同一记录双列）→ malformed；`batch_id` 重复 → malformed。
- 零锚时「最新已验收 C」= 空基线 manifest 字面量（不读取不存在的 C）。

**5-R.6 候选模式 CLI 与入口前置核验**：

```text
generate_quality_report.py --pending-batch <batch_id> --baseline-commit <V-OID> --toolchain-commit <T-OID>
```

三个参数在候选模式下均必选（缺失 → exit 2）。入口前置检查（先于任何门禁）：

1. **T 准入**：`--toolchain-commit` ∈ 登记集（`toolchain_registry.jsonl` @HEAD 解析、登记链哈希核验、链头 == `TOOLCHAIN_REGISTRY_HEAD` @HEAD）；
2. **执行来源核验**：**磁盘工具链文件**（实际将执行的代码，`Path.read_bytes()` 原始字节）与 `git cat-file blob @T` 原始字节比较——允许规范化 `REVISION_ANCHOR_HEAD` 与 `TOOLCHAIN_REGISTRY_HEAD` 两个常量值，其余字节（含 `classic_artifacts.py` 全部）完全相同；两常量实际值分别与 @HEAD 锚链/登记链头交叉核验。**不用 `git hash-object` 默认行为**（clean/filter 会消除 CRLF 等差异）；磁盘文件须同时 == HEAD blob（read_bytes vs cat-file 原始字节，未提交篡改即被拦截）；
3. 任一失败 → `REVISION_TOOLCHAIN_INVALID`（exit 1），不运行门禁；
4. 通过后候选门禁在当前 worktree 运行（磁盘即执行体）；基线重跑在基线提交（非首批 = V，首批 = `03c02bb571dec9e2da1f7d503a292da229415d8f`）的干净 worktree、以基线提交自带脚本运行。

**首批初始化路径**：当且仅当 **HEAD 锚链经 genesis 验证为空**（锚文件不存在或零行 ∧ `REVISION_ANCHOR_HEAD` @HEAD == genesis_sha）时：`--baseline-commit` 必须等于 `03c02bb571dec9e2da1f7d503a292da229415d8f`、`--toolchain-commit` 必须等于 T₀（冻结 OID）；例外由 HEAD 实测状态触发，**非参数值短路**——非首批传 `03c02bb571dec9e2da1f7d503a292da229415d8f` → exit 2，首批传其他 → exit 2。

**5-R.7 V 结构定点验证（不扫描历史，无 merge/revert 歧义路径）**：

1. **唯一父提交**：`git rev-list --parents -n 1 V` 恰好 2 个 OID（V + 唯一父 P）；合并提交（3+）拒绝；
2. **diff 路径** == `{accepted_anchors.jsonl, scripts/generate_quality_report.py}`，无其他路径；
3. **锚增量**：锚文件 blob @V == blob @P + 末尾追加一行（@P 行集为 @V 真前缀），新行即当前 HEAD 锚链末条；
4. **常量增量**：脚本 blob @V 与 @P 比较——唯一替换 `REVISION_ANCHOR_HEAD` 值，其余字节完全相同；@V 常量 == @V 锚链头，@P 常量 == @P 锚链头；
5. **C 绑定**：新锚 `content_commit` C 存在 ∧ 为 V 祖先 ∧ `sha256(_canonical(manifest@C).encode("utf-8")) == manifest_sha256_after`；
6. **P 的工具链身份**：`script@P` vs `script@T_v`（T_v = 该 V 锚条目 `toolchain_commit`）——**双常量规范化比较**（允许 `REVISION_ANCHOR_HEAD`/`TOOLCHAIN_REGISTRY_HEAD` 两值差异，其余字节完全相同；`classic_artifacts.py` 逐字节相等）；两常量实际值分别匹配 **@P 同一提交中的**锚链头与登记链头（从 @P blob 重算，**不使用 HEAD 的链头验证历史提交**）；P 本身不要求已验收（可为内容提交/工具链升级提交）；
7. **V 与 HEAD 锚状态一致**：锚 blob @V == @HEAD ∧ 常量 @V == @HEAD。

**5-R.8 源身份锚定链（防自证）**：

可信锚点从**已验证 evidence 链**取得——E1 的 (i) 校验 **E 登记的 evidence/freeze SHA-256 == B2 树 blob sha256 == HEAD 树 blob sha256**（双树一致），BASELINE 绑定是另一项 (j) 六方一致检查。rail ⑥ 从**该链锁定的 HEAD 树 evidence** 取得锚：

```text
evidence@HEAD.source_chain.sanmingtonghui 钉住两个独立身份值：
  manifest_blob_oid  = 662fbe6013c11b3bc58a3393ef1168ea82b05eca（Git 对象 OID，40-hex）
  manifest_file_sha256 = 7024760851374217ec3c61422e70fbd2d6a1deb3d48d1fa594d120215fdace61（文件字节 SHA-256，64-hex）
⑥ 分开校验（OID 与 SHA-256 不得混为一个值）：
  ⑥-1  git rev-parse HEAD:<SNAP>/source_manifest.json == manifest_blob_oid（对象身份）
  ⑥-2  sha256(git cat-file blob HEAD:<SNAP>/source_manifest.json 的原始字节) == manifest_file_sha256（内容身份）
    → source_manifest.chapters[NNN-1].extracted_text_sha256 钉住每章
      → ⑥ 重算 sha256(HEAD:<SNAP>/extracted/raw_{NNN}.txt 原始字节) == extracted_text_sha256 逐章比对
        → ⑦ original_text 去空白子串匹配于该已验文件
```

「源文件 + source_manifest + 修订清单同步篡改」负向测试必测：三者同 commit 篡改后 `HEAD:source_manifest.json` 与 E1 冻结 evidence 所钉 OID/SHA 不符 → `REVISION_SOURCE_UNVERIFIABLE`；篡改 evidence 本身已被现行 E1 拦截。

**基线重验必要条件（先于重跑执行；任一不满足 → `REVISION_BASELINE_INVALID`，exit 1）**：

- **非首批**：`--baseline-commit` 所指 V 必须存在于对象库 ∧ 为 HEAD 祖先（`git merge-base --is-ancestor V HEAD`）∧ 为最新验收提交（§5-R.13「后续 = 最新 V 提交」；即其锚追加为当前链头的 V）。
- **首批**：基线为冻结字面量 `03c02bb571dec9e2da1f7d503a292da229415d8f`（历史门禁向量重跑点，在 main 历史上天然满足祖先条件；该提交早于 §5-R，无修订结构要求）。

**「合格基线报告」完整定义**（rc 表中「合格」的判据；rc 0 与 rc 1 行共用；基线报告一律由**基线提交自带脚本**于其干净 worktree 重算取得，不读旧报告 JSON）：

- **非首批（V 基线）**：报告须同时满足——① `revision_state=="ACCEPTED"`；② E0/E1/E2 通过（`exemption_stages.E0_ok/E1_ok/E2_ok` 全 true；E3 已并入 rail（§5-R.5，rail 输出即 E3 结果），`ACCEPTED` 蕴含 E3 通过）；③ `approval_b2_constant_valid==true`；④ G1-G9 全部实际执行（`validator_ran_live==true` ∧ 逐书 `gates`/`gate_details` 九键齐备且为实测值）；⑤ 无 `REVISION_*` 错误（默认模式下 ① 蕴含）。
- **首批例外（显式恢复，实现不得自行推断）**：`03c02bb571dec9e2da1f7d503a292da229415d8f` 时点脚本早于 §5-R，基线报告**不含 `revision_state`/`revision_provenance_valid`——该两字段缺失不判不合格**，条件①⑤不适用；条件②③④照旧（该时点脚本已产出 `exemption_stages`/`approval_b2_constant_valid`/`validator_ran_live`/`gates`/`gate_details`/`status` 等全部非修订字段，实测字段于该基线全部可得）。

**基线重跑结果分类**（基线提交重跑，基线提交自带脚本，干净 worktree；非首批 = V，首批 = `03c02bb571dec9e2da1f7d503a292da229415d8f`）：

| rc | 报告状态 | 判定 |
|---|---|---|
| 0 | 合格且 overall_pass=true | 合格基线 |
| 1 | 合格 FAIL 报告，失败项 ⊆ 允许红项集合 | 合格基线 |
| 3 | 合法 BLOCKED schema | **上抛 exit 3**（非 REVISION_BASELINE_INVALID） |
| 其他 rc / 信号退出 / 超时 / rc 与报告状态不一致（完整合格 stdout + 异常退出码等） | — | `REVISION_BASELINE_INVALID` 拒绝 |

**允许红项 = 上界子集规则**（非「必须保持红」）：实际失败项 ⊆ 允许集合即可；允许项改善为 PASS **接受**。计数上界（冻结常量，随允许清单变更走评审）：`sanmingtonghui.G7.missing_count ≤ 303`（改善向下不设限，恶化超限拒绝）。**三书 source 政策（独立于质量门改善规则，先批准后生效）**：当前三书 `source_e2e` 必须为 FAIL；出现 PASS **不自动接纳**（判失败）；仅当独立 source 验证链与政策变更**先获批**、对应工具链与允许清单**先更新**后，才按新政策接受 PASS。

**门禁字段三分类全序比较**（跨版本基线，无交集漏洞）：

| 分类 | 判定 |
|---|---|
| 共有字段（B ∩ N） | 直接退化比较（PASS 不转 FAIL、计数不劣化） |
| 新增字段（N − B） | 按字段类型定义通过条件：布尔门禁 → 必须 PASS；数值计数 → 不得超冻结上限；枚举 → 须在**候选可接纳值集**（与 schema 合法值集分离；如新增 `revision_state` 候选要求 `=PENDING_ACCEPTANCE`） |
| 旧有字段消失（B − N） | **一律拒绝**：未声明兼容迁移时旧版必需门禁字段不得删除/改名/改语义；缺失或不可比较 → 拒绝候选验收 |

**流程阶段字段例外（v29.2）**：`revision_state`/`revision_provenance_valid` 表达流程阶段而非质量——已验收基线 V（`ACCEPTED`/true）与下一批候选（`PENDING_ACCEPTANCE`/false）的正常推进**不构成退化**，退出上表共有字段通用退化比较，改按运行模式校验：非首批基线必须 `ACCEPTED`/true（本节「合格基线报告」定义①），候选必须 `PENDING_ACCEPTANCE`/false（§5-R.4/§5-R.9），默认复验通过必须 `ACCEPTED`/true（§5-R.4）。其余字段照旧适用三分类比较。

字段 schema（字段名 → 类型/单位/分母/取值域/比较方向/上限/枚举可接纳值的字面定义表）**已落盘于本文档 §14 附录 A**（随 T₀ 工具链版本冻结；T₀ 在 `scripts/generate_quality_report.py` 内嵌同构机器可读表 `REPORT_FIELD_SCHEMA`，与附录逐字段一致）；共有字段比较前先核对两侧 schema 一致，不一致按 B−N 拒绝。兼容迁移另走独立批准（设计修订 + 新基线向量冻结 + 允许清单更新 + 附录 A 换版），不自动取交集。

**5-R.9 退出码与报告状态（候选与默认统一）**：

| 序 | 条件 | exit |
|---|---|---|
| 1 | CLI 参数错误（未知标志/缺值/畸形值/首批与非首批基线不符） | 2 |
| 2 | 任何 source BLOCKED（含基线重跑上抛；现行语义不变） | 3 |
| 3 | `REVISION_*` 失败，或 E0/E1/E2 任一失败，或 `approval_b2_constant_valid=false`，或相对验收基线退化（非允许项 PASS→FAIL / 允许项计数超上限或恶化） | 1 |
| 4 | 候选模式：全项合格（修订链①-⑦ + E0-E2 + B2 常量 + G1-G9 实际执行 + 基线零退化）且仅待批准 | 4 |
| 5 | 默认模式 overall_pass=true | 0 |
| 6 | 兜底：其余一切（默认模式修订已 ACCEPTED 但既有允许红项使 overall_pass=false） | 1 |

- **报告字段分离**：`status` 沿用现行词表（PASS/FAIL/BLOCKED），不引入 PENDING；`revision_state` 独立字段 ∈ {`NONE`,`ACCEPTED`,`PENDING_ACCEPTANCE`,`FAILED`}（NONE=manifest 不存在且无已验收锚，沿现行 MISSING 语义）；`revision_provenance_valid` 兼容字段 = (state == ACCEPTED)。exit 4 的前置显式含 E0/E1/E2 与 B2 常量通过——非 `REVISION_*` 错误一律阻止 exit 4。

**5-R.10 provenance 状态 × manifest 状态矩阵（逐格冻结）**：

| provenance 状态 | manifest 不存在 | 空/非法 JSON/schema 非法 | schema 合法且 batches=[] | schema 合法且非空 |
|---|---|---|---|---|
| VALID | admissible=true（现行不变） | `REVISION_UNSUPPORTED_STATE`，false | `REVISION_UNSUPPORTED_STATE`，false | `REVISION_UNSUPPORTED_STATE`，false |
| INVALID | false（现行不变） | false（现行不变） | false | false |
| MISSING | 无已验收锚：E0-E2 过 ∧ 分区等式（HEAD==freeze）→ admissible 沿现行 E3 语义；**有已验收锚 → `REVISION_CHAIN_STALE`**（已验收修订被整体抹除） | `REVISION_MANIFEST_MALFORMED`，false | 无已验收锚：合法空清单=无修订，分区等式通过 → 按现行；**有已验收锚 → `REVISION_CHAIN_STALE`**（清空已有修订） | rail ①-⑦ 过 → admissible=true（默认模式须全锚）；否则对应错误码，false |

VALID + manifest 文件存在（任何形态）→ `REVISION_UNSUPPORTED_STATE` 是**对现行唯一的行为修改**（现行 VALID 在 E1 前提前返回、不检测修订；VALID 书的 provenance.json 证明的是未修订内容，聚合被修订即与其断言矛盾）。

**5-R.11 双常量比较矩阵（v17+v18 冻结）**：

| 比较 | 允许差异 | 核验交叉 |
|---|---|---|
| R（登记提交）：脚本 @R vs @P | 唯一替换 `TOOLCHAIN_REGISTRY_HEAD` 值，其余字节相同 | @R 常量 == @R 登记链头 |
| V（验收提交）：脚本 @V vs @P | 唯一替换 `REVISION_ANCHOR_HEAD` 值，其余字节相同 | @V 常量 == @V 锚链头 |
| 任意被验证提交 S 的工具链 vs @T（含历史 V 的父提交 P） | 允许规范化 `REVISION_ANCHOR_HEAD` 与 `TOOLCHAIN_REGISTRY_HEAD` 两值，其余字节（含 classic_artifacts.py）完全相同 | 两实际值分别匹配 **S 同一提交中的**锚链头与登记链头（从 @S blob 重算，不用 HEAD 链头验证历史提交） |

「历史基线永不失效」收窄为：**不会仅因 HEAD 工具链 OID 改变而产生身份不匹配**；运行环境变更或报告协议不兼容升级仍可能使历史 V 不可用，此时走基线迁移路径。

**5-R.12 测试矩阵（TDD；端到端经 `generate_report`/CLI 驱动，辅助函数单测仅补充）**：

正向：首次初始化 `T₀ → R₀ → C₁ → 候选验证 → V₁`（R₀ 登记 T₀ 为前置——§5-R.6 入口核验 1 要求候选验证时 T 已在登记集；含 V₁ 结构判据全过、锚链头==常量）；**两批连续验收**（`V₁` 基线重跑 `ACCEPTED`/true → `C₂` 候选验证 `PENDING_ACCEPTANCE`/false **不判退化**——流程阶段字段按运行模式校验（§5-R.8 例外/附录 A.1），其余字段照常退化比较 → 批准后 `V₂` 默认复验 `ACCEPTED`/true ∧ 锚链两锚 ∧ 常量==链头 ∧ `V₂` 成为下批基线——**不止测首批字段缺失特例**）；`T₁ → R₁ → C₁ → 候选验证 → V₁` 全程普通 Git 流程（合法登记不被字节门禁拦截）；升级后历史兼容（T₁ 落地后验证 V₀ 用其锚内 T₀ 仍通过，下一批以 V₁ 为基线推进）；R₂ 追加后重新验证旧 V₁ 仍通过（不拿 HEAD 新登记头要求旧提交）；候选改善（允许项 PASS 化、G7 计数下降）被接受。
负向：同 batch_id 改记录并同步全部候选 SHA（C/A/常量全不动，仅改 HEAD）→ `REVISION_HISTORY_DRIFT`；锚文件篡改（含同步改 manifest_sha256_after 但常量不动）→ `REVISION_CHAIN_STALE`；删批 → STALE；未锚合法追加（默认模式）→ UNACCEPTED；manifest 畸形/未知字段/重复 (id,sha)/与 freeze 交集 → MALFORMED；分区不对称三分类各一 → MISMATCH；源三件套同步篡改 → SOURCE_UNVERIFIABLE；snapshot 路径逃逸/错章 → 拒绝；original_text 非子串 → 拒绝；mcq 外键悬空 → 拒绝；VALID 书出现 manifest → UNSUPPORTED_STATE；基线重跑完整合格 stdout + 异常退出码（rc=7）→ 拒绝；基线含允许集合外 FAIL（如 G3）→ 拒绝不进退化比较；门禁字段删除/同名字段改分母（schema 不一致）→ 拒绝；新增布尔字段 FAIL / 数值字段超上限 / 枚举值 schema 合法但不在可接纳集 → 拒绝；磁盘未提交篡改（仅换行差异）→ 拒绝；已提交篡改未登记 → 拒绝；非空隔离存量书（如穷通宝鉴模拟修订）在等式中保留隔离多重性；参数错误各一 → exit 2；首批/非首批基线错配 → exit 2。

**5-R.13 内容批次范围（不扩大；#112 补题与 B72 拆分待后续单独裁决）**：

- **R25**：#25 卷二·论坐命宫恢复+修订——`smth_077_000/001`（前缀 77-79 空闲；语义为旧批次 ch_order 追加序）；original_text 展开为 raw_025 精确连续引文（满足 G5 整串命中）；「甲已」保留原文，校读仅入 `textual_note` 附加字段（不断言笔误）；2 条人工 MCQ（全局顺序后缀，现最大 0776，自 0777 起）；修订记录属**新修订产物**（非原样恢复，绑 historical_basis），不适用原历史豁免身份。
- **B56**：#56 卷三·论学堂词馆离线人工命题——`smth_078_00N`；候选片段（阅读清单，**非配额**）：学堂/词馆定义、学堂会禄、学堂会食、生处见克、学堂会贵、总忌。
- **B72**：#72 卷五·论正官离线人工命题——`smth_079_00N`；候选片段：正官定义、月令为正、支藏干透、破格诸忌、时为归息、明干取官、贪合忘官、逢官看印、三等官、诸乡、真五行克纳音、古歌集萃。
- 每批验收基线：R25 基线 = `03c02bb571dec9e2da1f7d503a292da229415d8f` 门禁向量；后续 = 最新 V 提交。基线向量于基线提交干净 worktree 重新执行取得（不读旧报告 JSON）。G5 每批实际执行并记录（extracted 子串检查为叠加项不替代 G5）。

## 6. E→R→B1→B2→B3 流程与 schema 版本化

- 版本单选：新请求 `schema_version:"2.0"`；legacy=`"1.0"`（现行生成器形态，含 `reason`）。
- **v1**：语法校验可通过，但授权要求请求 canonical SHA ∈ `V1_REQUEST_GRANT_ALLOWLIST = frozenset()`——当前空集，任何 v1 请求都不能使报告 admissible。
- **v2.0 E 请求精确字段集（12 项，缺一/多一拒绝）**：`schema_version`、`book`、`artifact_manifest_sha256`、`baseline_commit`（== 基点，第 3 级六方一致见 §5-E1(j)）、`validator_code_sha256`、`historical_record_freeze_sha256`、`historical_generation_evidence_sha256`、`exempted_checks:["missing_formal_model_run_manifest"]`、`non_exempt_checks:["artifact_integrity","quality_gates","future_generation_provenance"]`、`author`、`date`、`parent_commit`（== 生成该书 E 时的 HEAD，逐书不同，由 §5-E1(c) 三方绑定）。
- **v2.0 R 回执精确字段集（10 项，缺一/多一拒绝）**：`schema_version:"2.0"`、`exemption_request_sha256`、`baseline_commit`（镜像 E）、`artifact_manifest_sha256`、`validator_code_sha256`、`historical_record_freeze_sha256`、`historical_generation_evidence_sha256`、`parent_commit`（镜像 E 并由 §5-E1(c) 三方绑定）、`approver`、`approved_at`。
- **v2.0 `verify_approval_receipt` 逐项镜像复核（含 10 项）**：`schema_version=="2.0"`；`exemption_request_sha256` == canonical(E)；`baseline_commit`/`artifact_manifest_sha256`/`validator_code_sha256`/`parent_commit`/两 evidence SHA == E 对应字段；`approver/approved_at` 非空。`verify_exemption_request`/`verify_approval_receipt` 均按 `schema_version` 分派 v1/v2；两版禁含回执/批准字段。
- `artifact_manifest_sha256`/`validator_code_sha256` 权威重算见 §5-E2；E/R/重算三方全等。
- B2 指针精确字段集（8 项，缺一/多一拒绝）：`schema_version:"1.0"`、`book`、`baseline_commit`、`b1_commit`、`e_path`、`e_sha256`、`r_path`、`r_sha256`；`book` == 常量键 == E.`book`；`e_path`/`r_path` 必须**逐字等于**该书规范路径；文件序列化用全局 canonical 规则；`schema_version`/`baseline_commit`/`b1_commit` 均为被验证字段（§5-E1(b)(d)，baseline 第 3 级见 (j)）。
- B1/B2 提交信息仅为人类可读注记，不参与验证。

## 7. 质量报告消费（入口/参数链/顺序/状态机）

- **生产调用顺序（中优-2，无条件独立执行，禁止"static 失败后直接 return"）**：

```text
for book in 四书:
    provenance_result = evaluate_provenance_admissibility(
        book_dir, git_root
    )  # 不接 archive_root，不调用 source checker

    if book == "sanmingtonghui":
        source_result = verify_sanming_source_chain(
            git_root, archive_root
        )  # 即使 provenance/E0 失败也必须执行
    else:
        source_result = FAIL  # S 口径（§8 已确认）

    aggregate(provenance_result, source_result)
```

  即：即使 `evidence_static_check` / E0 失败，`source_chain_check` 仍必须执行以发现 `archive_root_missing`/`archive_*`/`verifier_identity_mismatch` 并令顶层 exit=3。**不得写成静态失败后提前 return。**
- **参数链冻结（两个同级入口，`generate_report` 统一编排）**：CLI `--archive-root` → `generate_report(archive_root=...)`，在逐书循环内独立编排两条同级链——provenance 链 `evaluate_provenance_admissibility(book_dir, git_root)`（**不含 `archive_root` 参数、不调用 source checker**，仅 §5 三态判定 + E0 静态校验）；source 链仅 `sanmingtonghui` 调 `verify_sanming_source_chain(git_root, archive_root)`（`source_chain_check` 的执行体，即便 provenance/E0 失败仍无条件执行），其余三书 `source_result = FAIL`（§8 S 口径）。**三命通会在书集内而 `archive_root` 缺失 → fail-closed：`source_e2e_status=BLOCKED`（reason `archive_root_missing`，属 §4.2 统一枚举），CLI exit 3**，不得静默跳过。E0 同源校验在 `generate_report` 内对每本书于 §5 provenance 状态判定后执行（产出 `E0_ok`，仅 MISSING 参与 admissible）。
- **base 冻结**：报告链强制 `base == c5cff699fdb547bd9270acbebe1f485380848751`（模块常量）；非冻结 base 拒绝。独立核验器的 `--base` 仅供诊断，不进入报告链。
- 逐书：`content_gates_pass` = G1–G9 全过；`provenance_admissible` = §5 三态公式；`source_e2e_status` ∈ {PASS, FAIL, BLOCKED}：三命通会 = `source_chain_check`（OK→PASS，failures→FAIL，BLOCKED→BLOCKED）；三本完成书 = **FAIL**（§8，已确认 S）。
- **顶层状态机（source BLOCKED 独立且上限；豁免链静态错误仅影响 admissible 布尔）**：

```text
顶层 status = BLOCKED   若任一书 source_e2e_status == BLOCKED（含 archive_root 缺失）
           = FAIL       否则若 overall_pass == false
           = PASS       当且仅当 overall_pass == true
source_e2e_status（四书聚合）= BLOCKED 若任一书 BLOCKED
                           = FAIL    若无 BLOCKED 且任一书 FAIL
                           = PASS    当且仅当四书全 PASS
source_e2e_pass   = (source_e2e_status == "PASS")
```

- **CLI exit 码**：任一书 BLOCKED → **3**（与豁免链静态错误同时存在时亦为 3，BLOCKED 优先）；否则 `overall_pass=false` → **1**；全部通过 → **0**。**v29（已获 v29.3 批准；条款随 §5-R 实施启用）**：修订溯源启用后按 §5-R.9 完整表——参数错误 → 2；BLOCKED → 3（优先级不变）；修订链/E0-E2/B2 常量失败或基线退化 → 1；候选全项合格仅待批准 → 4；默认 `overall_pass=true` → 0；其余 → 1。`status` 词表不变（PASS/FAIL/BLOCKED），修订状态由独立字段 `revision_state` 承担（§5-R.9）。
- 顶层其余：`content_gates_pass = AND(四书)`；`provenance_admissible_all = AND(四书)`；`overall_pass = content_gates_pass AND provenance_admissible_all AND source_e2e_pass`（BLOCKED 时 overall 输出 false 且顶层 status=BLOCKED）。
- 展示：`provenance_state` / `provenance_ok` / `historical_exemption_valid` / `provenance_admissible` / `source_e2e_status` 逐书分离；豁免与 S 事实入 `known_limitations`；豁免链失败错误码（GENERATOR/FROZEN/FREEZE_STATIC/EVIDENCE_STATIC/BASELINE）与 source BLOCKED reason 分列展示互不混淆。
- 当前树预期：四书 provenance 均 MISSING；三命通会 G7 FAIL → `content_gates_pass=false`；三本书 source_e2e=FAIL（§8 已确认 S）→ `overall_pass=false`，exit 1。

## 8. source e2e 口径

- **已确认 S（2026-09-03 用户聊天正文逐字确认）**：三本完成书 `source_e2e_status=FAIL`（gate2 只证迁移等值，不证获取链）；本设计只处理模型 run manifest 缺失。确认语句：`选择 S：本设计不豁免三本完成书的 source 获取链；三书 source_e2e_status="FAIL"，派生 source_e2e_pass=false。`
- T（如将来需要）：另立设计 + 独立审批链，绑定原文精确 blob/SHA，声明"不证明原始获取过程"。

## 9. 未来运行衔接（本设计外）

- E3 多重集合严格相等无放宽（**v29 修订例外，已获 v29.3 批准，条款随 §5-R 实施启用**：经 §5-R 修订溯源双轨的 Revision 分区记录，按 §5-R.5 ⑤ 等式 `Counter(HEAD) == Counter(freeze) + Counter(manifest)` 纳入；Legacy 分区仍逐条严格相等）。首次正式生成运行前须另行升级 run_manifest 契约并单独设计采信路径；届时聚合文件变化使本豁免失效，新状态由新链全责。**未来 run_manifest 的 pre-run 规则索引不得再按单值 `id → canonical SHA` map**（无法表示同一 id 对应多条不同记录，也丢失重复次数）；必须采用 `(id, sha256)` 规范化多重集合（按 `(id,sha256)` 排序、保留重复次数，或等价地带 count 的列表），与 §3/§5-E3 多重集合语义一致。

## 10. TDD 计划与**工件提交顺序冻结**（批准后执行；每阶段精确文件集逐字冻结）

**前置提交（一次性，顺序固定）**：

```text
① C-gen：TDD 实现（先有失败测试再有实现），精确文件集恰为两文件：
   scripts/generate_classic_historical_freeze.py
   tests/test_classic_historical_freeze.py
   测试覆盖两个子命令与全部拒绝项（仅 evidence_static_check 与 freeze 静态；
   不测试 source_chain_check 的 BLOCKED 行为——那依赖 ③ 的 verifier，见下）：
   - freeze 自身基点绑定（非基点 → FROZEN_AT_COMMIT_MISMATCH）
   - freeze schema/字段集/records/计数 篡改 → FREEZE_STATIC_MISMATCH
   - records 多重集合：同 id 不同 sha256 多条允许冻结；删记录/counts 不一致/改 sha256 格式/破坏
     (id,sha256) 排序 → FREEZE_STATIC_MISMATCH
   - **freeze --check 全等重算（P0，v27.1）**：修改磁盘 freeze——用**合法 64 位** SHA 替换某 record 的 sha256、增删同 id 记录、改变重复次数、篡改 blob_oid/byte_size——均须因与 BASE 重建期望对象字节不等而拒绝（FREEZE_STATIC_MISMATCH）；验证"纯自洽但非 BASE 重建值"不能通过 --check
   - evidence 阶段（freeze==evidence==BASE,非基点 → FROZEN_AT_COMMIT_MISMATCH；不涉及 E/R/pointer）
   - 生成器六向身份（改生成器/仅篡改 generator_sha256 → GENERATOR_IDENTITY_MISMATCH）
   - evidence_static_check 结构/计数/静态 SHA 篡改 → EVIDENCE_STATIC_MISMATCH
   - evidence_static_check/build_evidence 的 verifier 依赖以"注入式固定 fixture"（冻结的
     verifier 输出样本 + 冻结 blob OID/SHA 值）于模块函数级测试，不依赖真实 verifier；
     CLI 生产路径自 ④(1) 起以 HEAD verifier 真实身份替换 fixture。
② C-freeze：运行 freeze 子命令，精确文件集恰为冻结集 JSON 一文件；
   提交前 `freeze --check` 校验工作区文件；**提交后从新 HEAD 再跑一次 `freeze --check`**，
   确认提交的 Git blob 与生成时字节一致（防提交时规范化/钩子改写）。
③ C-verifier：TDD 实现，精确文件集恰为两文件：
   scripts/verify_sanming_source_chain.py
   tests/test_verify_sanming_source_chain.py
   （取得 verifier blob；测试含 AST 同源、五值 BLOCKED、四元组排序、303/303 重放，
   并承载 source_chain_check 的完整行为测试：
   - tar 缺失 → archive_missing BLOCKED
   - tar SHA/大小不符 → archive_sha_mismatch / archive_size_mismatch BLOCKED
   - 工作区 verifier≠HEAD → verifier_identity_mismatch BLOCKED
   - static PASS 而 source BLOCKED（两态分离互不污染）
   - verifier 双重分类：记录值≠HEAD → EVIDENCE_STATIC_MISMATCH（静态，此负向在 ① 静
     态侧；执行前工作区≠HEAD → verifier_identity_mismatch BLOCKED，此负向在本阶段）
   - 中文与空格路径 NUL 解析负向）
④ C-evidence（v27.4 纠正链，三阶段，顺序固定；原阶段④以未提交一次性驱动生成、正式 CLI
   仍用阶段①零值 verifier fixture 且无 --archive-root，原生 `evidence --check` 对已提交
   evidence 必返 EVIDENCE_STATIC_MISMATCH → 判 NEEDS_REVISION。v27.4 起按下述纠正链执行，
   v27.5 修补其复审 3 P0（完整提交身份/wiring 测试文件集/verifier 调用 fail-closed，§13-8）；
   历史尝试 c22b5b12d3ba5dd9ce7a9ebd5f914d4efde1109f（freeze v1）与 cbb00baf7b0e4c4cbf20257f6a8a85b840e3b953（evidence v1）保留不改写）：
   (1) C-evidence-wiring —— 正式 evidence 生产入口接线（TDD：先失败测试后实现），
       精确文件集恰为两文件：
       scripts/generate_classic_historical_freeze.py
       tests/test_classic_historical_freeze.py
       - evidence 子命令 `--archive-root <dir>` 参数模式契约：`--out`（生成）模式**必填**，
         缺失 → 拒绝（非零 exit）；`--check` 模式**必须拒绝**该参数（非零 exit），
         不得静默忽略；**`--check` 只执行静态身份校验（evidence_static_check），不调用
         verifier、不访问归档**；
       - **verifier 调用契约（fail-closed，逐条冻结）**：以 `sys.executable` 与参数数组
         subprocess 调用 ③ 的 verifier，可执行文件路径**固定为
         `<git_root>/scripts/verify_sanming_source_chain.py`**（不经 shell；即使传入其他
         `--git-root` 也只执行该 git_root 树内的 verifier），完整 argv 固定为
         `[sys.executable, <git_root>/scripts/verify_sanming_source_chain.py,
         "--git-root", str(<git_root>), "--archive-root", str(<archive_root>)]`，测试精确断言
         完整 argv；
       - **verifier 输出全状态分类（v27.7 冻结：先严格解析 stdout（拒绝重复 JSON 键），
         再按退出码 × schema 联合判断；禁止其他映射。「精确 schema」按 §4.2 逐字冻结，
         见下方 schema 判据）**：
         - rc==0 ∧ 精确成功 schema → 取其五字段作为 replay，继续生成流程；
         - rc==1 ∧ 精确 failures schema → `SOURCE_REPLAY_FAILED`，exit 1；
         - rc==3 ∧ 精确 BLOCKED schema → `SOURCE_CHAIN_BLOCKED`，exit 3，
           错误信息保留该 reason；
       - **schema 判据（v27.8 冻结，直接绑定 §4.2；任一不满足即该分支不命中）**：
         - 正常输出顶层键集合**精确等于** `{schema_version, status, chapters_expected,
           c1_pass, c2_pass, c3_pass, failures}`（多键/缺键均不命中）；`schema_version`
           必须为字符串 `"1.0"`；`status` 必须为字符串 `"OK"`；计数四字段
           （chapters_expected/c1_pass/c2_pass/c3_pass）必须为 **非 bool 的 int**
           （`isinstance(x, int) and not isinstance(x, bool)`），且
           `chapters_expected==303`、`c1_pass==c2_pass==c3_pass==303`、各计数 ∈ [0,303]；
           `failures` 必须为列表且 `== []`；
         - failures schema（rc==1 分支）：顶层键集合**精确等于** 上述七键（与正常输出
           同一 schema）；**复用成功分支的顶层键集合、schema_version、status、字段类型
           及取值范围判据**——`schema_version=="1.0"`（字符串）、`status=="OK"`、
           `chapters_expected==303`、四个计数字段均为非 bool int 且 ∈ [0,303]；
           **分支特有判据**为 c1/c2/c3 可小于 303（各为其过数）且 `failures` 为
           **非空列表**；每个条目为对象且
           键集合**精确等于** `{"chapter","check","code","detail"}`；`chapter` 为非 bool
           int、`check` ∈ `{"C1","C2","C3"}`、`code` **必须属于 §4.2 七值稳定错误码枚举**
           （`ARCHIVE_MEMBER_MISSING, C1_SHA_MISMATCH, C2_HEADING_NOT_FOUND, C2_NO_BODY,
           C2_EXTRACTION_ERROR, C2_SHA_MISMATCH, C3_SHA_MISMATCH`）、`detail` 为字符串；
           整个 `failures` 列表按 `(chapter, check, code, detail)` 排序（§4.2 冻结）；
           任一字段不满足（含 schema_version 错误、status 非 "OK"、bool/越界计数、
           枚举外 code）→ 该分支不命中，落入 `SOURCE_REPLAY_INVALID`/exit 1；
         - BLOCKED schema（rc==3 分支）：顶层键集合**精确等于**
           `{schema_version, status, reason}`（多键/缺键均不命中）；`schema_version`
           为 `"1.0"`、`status=="BLOCKED"`、`reason` 属 §4.2 五值枚举；
         - **schema 负向测试（v27.8 新增，均断言 `SOURCE_REPLAY_INVALID`/exit 1）**：
           成功分支带额外顶层键 / 缺 `schema_version` / `schema_version!="1.0"` /
           计数为 bool（`True`）/ 计数为 304 或 -1；rc==1 分支 failure 条目多键/
           缺 `detail`/`check` 为 `"C4"`/`failures` 列表乱序，**及 rc==1 分支同层级
           判据违规（v27.9）——`schema_version` 缺失或非 "1.0"/`status!="OK"`/
           `chapters_expected!=303`/计数为 bool 或越界/`code` 为枚举外值（如
           `"BOGUS_CODE"`）**；rc==3 分支带额外键/缺 `reason`/`reason` 非五值；
         - **其他任何组合**——未知退出码（非 0/1/3）、进程启动失败/崩溃/OSError、
           stdout 非 JSON/非对象/重复 JSON 键、rc==0 但 status!=OK 或计数≠303 或
           failures 非空、rc==1 但输出不满足精确 failures schema、rc==3 但 JSON 畸形/
           缺 reason/reason 不属五值——一律 `SOURCE_REPLAY_INVALID`，exit 1；
         - CLI 参数模式违规（`--out` 缺 `--archive-root` / `--check` 带 `--archive-root`）→
           `SOURCE_REPLAY_INVALID`，exit 1；
       - **错误输出格式（v27.7 冻定）**：stderr 固定为单行
         `ERROR_CODE[:reason]`——`SOURCE_CHAIN_BLOCKED` 后必须附五值 reason（如
         `SOURCE_CHAIN_BLOCKED:archive_missing`）；其余错误码不带后缀。可机械解析，
         测试按此精确断言；
       - **写出契约（v27.7 冻结可执行顺序链，防覆盖既有 evidence；所有门通过前禁止的是
         触碰目标路径，不是构造 candidate）**：
         ① verifier 成功（rc==0 ∧ 精确成功 schema）；
         ② 在内存构造 candidate evidence（build_evidence）；
         ③ 对 candidate 执行 evidence_static_check（连同生成器六向身份与
            frozen_at_commit 第 2 级前置断言）；
         ④ canonical 序列化（`_serialize`）；
         ⑤ 写同目录临时文件（tempfile.mkstemp）；
         ⑥ 读回临时文件校验字节 == 序列化字节；
         ⑦ `os.replace` 原子替换目标路径；
         任意失败时**目标路径不存在则保持不存在，已存在则字节与 SHA-256 完全不变**——
         禁止任何失败路径触碰目标文件；临时文件在任意异常路径必须清理（try/finally
         删除），清理失败仅记录，**不得改变原目标文件、不得抛出掩盖原错误**；
       - verifier OID/SHA 动态取自 HEAD（git rev-parse HEAD:scripts/verify_sanming_source_chain.py
         + sha256(git show HEAD:...)）；生成与 `evidence --check` 均以 HEAD verifier 身份
         替代 ① 的零值 fixture（fixture 仅保留于模块函数级单测注入，不进 CLI 生产路径）；
       - 生成器六向身份与 frozen_at_commit 第 2 级（freeze==evidence==BASE, §4）的机械
         断言**作为步骤 ③ 的一部分**（在步骤 ② 之后、步骤 ④ 之前，随
         evidence_static_check(candidate) 一并执行，不另设独立门禁、不与之重复），
         违者拒绝且不触碰目标路径；
       - **测试覆盖（tests/test_classic_historical_freeze.py 新增，成功与失败路径齐备）**：
         成功路径——verifier 正常 OK 输出 → evidence 原子写出且 `evidence --check` 通过；
         失败路径——verifier exit 1（断言 `SOURCE_REPLAY_FAILED`/exit 1）/ exit 3（断言
         `SOURCE_CHAIN_BLOCKED`/exit 3 且 stderr 为 `SOURCE_CHAIN_BLOCKED:<reason>`，
         reason 属五值）/ 畸形 JSON（非对象/缺字段/类型错）/ 重复键（断言
         `SOURCE_REPLAY_INVALID`/exit 1）/ **全状态分类负向（v27.7）**：未知退出码
         （如 rc==2）、启动失败（verifier 路径不存在）、rc==0 但 `status!="OK"`/计数≠303/
         `failures` 非空、rc==3 但缺 `reason` 或 reason 非五值、rc==1 但输出非精确
         failures schema——均断言 `SOURCE_REPLAY_INVALID`/exit 1；`--out` 模式缺
         `--archive-root` → 拒绝；`--check` 模式带 `--archive-root` → 拒绝；**每个失败
         分支先向目标路径写入 sentinel（v1 字节），断言失败后目标文件字节与 SHA-256
         与 sentinel 完全一致（不覆盖）**；目标不存在时断言失败后仍不存在；argv 断言——
         注入点捕获完整 subprocess argv，精确等于冻结数组（含 `<git_root>` 树内 verifier
         路径）；`--check` 不调 verifier、不访问归档（spy 断言零调用）。verifier 子进程
         以模块级注入点或临时桩脚本驱动，不依赖真实归档；
       - 门禁：test_classic_historical_freeze.py 聚焦测试全绿 + ruff。
   (2) C-freeze-r2 —— 因 (1) 改动生成器致其 blob OID 变化，freeze 内嵌 generator_blob_oid
       失效，须重新生成冻结集，精确文件集恰为冻结集 JSON 一文件（替换 c22b5b12d3ba5dd9ce7a9ebd5f914d4efde1109f 版本；
       数据仍来自 BASE，仅 generator_blob_oid 变化）；提交前、提交后均从新 HEAD 跑
       `freeze --check`，exit 0（确认提交 blob 与生成时字节一致）。
   (3) C-evidence-r2 —— 用正式 CLI 生成 evidence，精确文件集恰为 evidence JSON 一文件
       （替换 cbb00baf7b0e4c4cbf20257f6a8a85b840e3b953 版本）；提交前、提交后均跑原生 `evidence --check`，exit 0；
       此阶段完成真实 generator→verifier 生产联调。
⑤ C-exemption-tooling：TDD 实现，精确文件集恰为三文件：
   scripts/make_historical_exemption.py          （v2 E 生成：--schema-version 2.0；v1 路径不变）
   scripts/classic_artifacts.py                  （verify_exemption_request/verify_approval_receipt
                                                   按 schema_version 分派 v1/v2 + §5-E2 权威重算函数）
   tests/test_classic_exemption_tooling.py        （v2 E 生成、v2 E/R 精确字段集与镜像、
                                                   权威重算三方全等、ls-tree -z 中文/空格负向）
   机械门禁除新测试通过外，**必须同时运行既有
   tests/test_classic_distillation_remediation.py 全绿**（防 v1、provenance 与
   其他归档校验回归；该文件不进 diff，只作回归运行）。
```

**逐书循环（四书精确有序集）**：

```text
for book in [ditiansui, qiongtongbaojian, sanmingtonghui, zipingzhenquan]:
    H = 当前 HEAD
    生成 E_book(parent_commit=H)（用 ⑤ 的 v2 生成器）
    用户方生成 R_book(parent_commit=H)
    提交 B1_book：parent=H，diff 恰为该书 E/R 两规范路径
    提交 B2_book：parent=B1_book，diff 恰为该书指针一规范路径
```

**收尾提交**：

```text
⑦ B3：TDD 实现，精确文件集恰为两文件：
   scripts/generate_quality_report.py              （APPROVAL_B2_BY_BOOK 常量（§5.1）+
                                                    evaluate_provenance_admissibility + 三态判定 +
                                                    E0 静态校验 + 无条件 source_chain_check 汇合 +
                                                    参数链 + 三态/顶层状态机 + CLI exit 0/1/3）
   tests/test_classic_distillation_quality_report.py（既有测试文件扩展：B3 常量验证、
                                                    豁免链消费、E0 静态校验（含"SHA 自洽但
                                                    frozen_at_commit 错误"的整链负向）、E1(j)
                                                    置于工件链后的物理顺序约束、
                                                    三态闭合（VALID 下 E0 失败不得改写
                                                    admissible=true；INVALID 下豁免不被咨询；
                                                    MISSING 下 admissible=E0∧E1∧E2∧E3）、
                                                    source_chain_check 无条件独立执行
                                                    （E0 失败仍执行并产生 archive BLOCKED、
                                                    非提前 return；spy 锁定 sanmingtonghui
                                                    恰调用一次、其余三书调用零次）、
                                                    静态失败 vs source BLOCKED
                                                    分离（含两者同时存在时 BLOCKED 优先 exit 3）、
                                                    错误优先级短路（GENERATOR→FROZEN→FREEZE_STATIC→
                                                    EVIDENCE_STATIC→BASELINE）、
                                                    三态聚合、exit 码、E4 顺序阻断）
   E3 多重性负向（P0，v27.3）：**保持 freeze/evidence/E/R/pointer 全部有效且不变**，
   在 BASE 的后继 HEAD 中修改聚合 blob——替换记录内容产生合法新 sha256、增删同 id 记录、
   改变重复次数。E0 对 BASE freeze 仍全部通过（不伪造/篡改冻结集，不改
   artifact_files.file_sha256——那是源聚合文件的真实字节 SHA），随后 E3 对当前 HEAD
   多重集合重算并拒绝；**断言 `E0_ok=true`、E1/E2 通过、最终仅 `E3_ok=false`**
   （错误来自 E3 而非 E0/前置门禁——E0 的 record_set_binding 仅绑定 freeze，不读当前 HEAD）；
⑧ 门禁全跑（零提交）
```

顺序不变量：freeze/evidence 必须在 E 生成前入库（r2 版本替换 v1 历史尝试）；verifier blob 先于 evidence 记录；④ 纠正链顺序固定 C-evidence-wiring → C-freeze-r2 → C-evidence-r2（生成器改动须先于 r2 工件，且 ④(3) 的 evidence --check 依赖 ④(1) 的生产入口）；⑤ 必须在逐书循环前（v2 E 生成与校验的代码前置）；B3 必须在全部 B2 后（常量值依赖四书 B2 SHA）。任一提交的文件集违反"恰为"约束 → 该提交无效须重做。
**TDD 与门禁的关系**：TDD（先失败测试后实现）为实施纪律；**机械门禁仅为各提交时点其精确文件集内测试全部通过（GREEN），以及 ② 与 ④(2)(3) 提交后新 HEAD 的 `freeze --check`/`evidence --check` 通过**；RED 运行记录不作为可信证据、不构成提交约束。正式报告的豁免可用性由 E0 每次重算保证（§5），不依赖任何历史运行记录。
TDD 覆盖（详目同前）：冻结生成器（精确 schema/拒绝项/确定性/两子命令/frozen_at_commit 与 FREEZE_STATIC 分化/六向身份绑定/evidence_static_check 结构负向）；核验器（AST 同源、输出 schema、BLOCKED 五枚举、failures 四元组排序、303/303、tar 缺失/身份/工作区 verifier 负向、中文与空格路径 NUL 解析负向）；v2 E/R 精确字段集与镜像复核（10 项）+ 权威重算三方全等（含生产算法等价断言）；指针全字段消费与第 3 级六向 baseline/三方 parent（逐书）；B1/B2/B3 链正反向（含逐书循环与各阶段文件集门禁）；E4 顺序阻断；报告参数链、无条件 source_chain_check 汇合、顶层状态机（BLOCKED 上限）与 exit 码；E0 静态校验每次重算（含全新 clone/替换工件等价场景）；错误优先级短路（五类，单输入单错误码）；三态公式闭合（VALID/INVALID/MISSING）。

## 11. 待用户动作

1. ~~§8 口径逐字确认~~ 已完成（2026-09-03，见 §8）。
2. ~~D1(c)/D2 第一人称逐字批准~~ 已完成（2026-09-03，见 §0 批准锚点）。
3. ~~**v27.3 修订版整体批准**（records 唯一性契约修订 + 复审修补，§13）~~ 已完成（2026-09-03，批准锚点见 §0）；C-gen 两文件已同步修正并提交（§10-①，提交 `87822cea200e824bcc00f6490a8dc96e4cb4df1a`）。
4. ~~**v27.4 修订版整体批准**（正式 evidence 生产入口纠正链，§13）~~ 未获批准（复审 NEEDS_REVISION：截断提交身份 / wiring 缺测试文件集 / verifier 契约不够 fail-closed），由 v27.5 取代。
5. ~~**v27.5 修订版整体批准**（纠正链修补，§13）~~ 未获批准（复审 NEEDS_REVISION：错误码无字面量 / 失败可能覆盖既有 evidence），由 v27.6 取代。
6. ~~**v27.6 修订版整体批准**（纠正链修补，§13）~~ 未获批准（复审 NEEDS_REVISION：写出顺序自相矛盾 / verifier 输出状态空间未完全分类），由 v27.7 取代。
7. ~~**v27.7 修订版整体批准**（纠正链修补，§13）~~ 未获批准（复审 NEEDS_REVISION：精确 schema 未冻结 / 校验时点措辞不一致），由 v27.8 取代。
8. ~~**v27.8 修订版整体批准**（纠正链小修，§13）~~ 未获批准（复审 NEEDS_REVISION：rc==1 判据不完整 / 校验时点与步骤 ③ 冲突），由 v27.9 取代。
9. ~~**v27.9 修订版整体批准**（纠正链小修，§13）~~ 未获批准（复审 NEEDS_REVISION：「复用全部判据」措辞使 rc==1 分支自相矛盾），由 v27.10 取代。
10. ~~**v27.10 修订版整体批准与 §10-④ 纠正链实施**（纠正链小修，§13）~~ **已完成**（2026-09-04，有效批准与追认锚点见 §0）：C-evidence-wiring `a046555af87a12e15424778ffc3fd3ed26177d1c` → C-freeze-r2 `53aabebd0fc0fa27b1eb9a5a546736c16bea0b92` → C-evidence-r2 `6f09ee290a0781b80c4707ae2dc6a6ceb4833abc`。
11. ~~**v28 修订版整体批准**（extractor 锚点自包含迁移 A′，§13）~~ **已完成**（2026-09-05，批准锚点见 §0）。
12. ~~**四书 R 批准（A′ 重建链）**~~ **已完成**（2026-09-05，四书逐书聊天正文第一人称批准，approver=owner，approved_at=2026-09-05T10:00:00+08:00；B1/B2 提交与 CI 记录见 §13 第 14/15 条）。

## 12. source verifier 身份绑定

- 实现提交后（§10-③），`scripts/verify_sanming_source_chain.py` 的 blob OID 与字节 sha256 记入 evidence `source_chain.verifier_blob_oid/verifier_sha256`（§4；顺序由 §10 冻结）。
- **两段身份核对，各归其链，不重复**：
  - 静态链（`evidence_static_check`，§10-① 测试）：只比对 evidence 记录的 `verifier_blob_oid/verifier_sha256` 是否 == `HEAD:scripts/verify_sanming_source_chain.py` 的 blob OID/字节 sha256；不符 → `EVIDENCE_STATIC_MISMATCH`。
  - 执行链（`source_chain_check` 执行前，§10-③ 测试）：断言 `git hash-object <工作区 verifier 文件>` == 同 HEAD blob OID（disk==HEAD）；不符 → BLOCKED（reason `verifier_identity_mismatch`，属 §4.2 统一枚举）。

## 13. v26 → v29.3 变更记录

1. **records 身份契约改为多重集合（P0，修订）**：阶段 ① 首跑发现冻结基点 `c5cff699fdb547bd9270acbebe1f485380848751` 的 `qiongtongbaojian/quarantine_rules.jsonl` 存在同 `id` 不同内容的多条记录（qtbj_001_038/qtbj_050_009/qtbj_050_011 各 2 条），与 §3「同文件 id 唯一」冲突。**按用户裁决不改历史数据**：§3 取消 id 唯一要求，records 身份改为 `(id,sha256)` 多重集合、按 `(id,sha256)` 排序、保留重复次数；§5-E3 改为逐记录多重集合严格相等（按 `(kind,id,sha)` 排序后逐项比对，禁用普通 set）。
2. **未来 manifest 按多重集合表示（P0，v27.1 复审）**：§9 明确未来 run_manifest 的 pre-run 规则索引不得用单值 `id → canonical SHA` map，改用 `(id,sha256)` 规范化多重集合（或带 count 列表），与 §3/§5-E3 语义一致。
3. **`freeze --check` 全等重算契约（P0，v27.1 复审）**：§3 钉死 `freeze --check` 必须从冻结基点 16 个聚合 blob 重建完整期望 freeze 对象并与磁盘 canonical 字节全等；纯静态自洽（合法 SHA 替换/同步 counts/改重复次数）不得通过。
4. **E3 多重性负向测试方案修正（P0，v27.2 复审）**：v27.1 的方案（篡改冻结集 + 同步外层哈希）会被 E0 的 BASE freeze 重建先拦截、到不了 E3，且 `artifact_files.file_sha256` 是源聚合文件真实字节 SHA、不应随伪造 freeze 修改。v27.2 改为：**保持 freeze/evidence/E/R/pointer 全部有效且不变，在 BASE 后继 HEAD 修改聚合 blob**（替换记录内容产生合法新 sha256、增删同 id 记录、改重复次数）——E0 对 BASE freeze 仍通过，E3 对当前 HEAD 多重集合重算拒绝，断言最终错误来自 E3 而非前置门禁。§10-① freeze --check 全等重算测试保留，删除无对应 freeze 字段的"外层哈希"措辞。
5. **省略号违规修正（v27.1）**：全文的 `c5cff699` 前 8 位省略写法替换为完整 40 位 OID `c5cff699fdb547bd9270acbebe1f485380848751`（§0/§13 及文档头「全文一律完整值」规则）。
6. **E0 `record_set_binding` 职责收窄（P0，v27.3 复审）**：v27.2 把 `record_set_binding` 与「当前 HEAD 聚合 blob + §5-E3 比对」同放 `evidence_static_check`，后继 HEAD 聚合数据一漂移 E0 先报 `EVIDENCE_STATIC_MISMATCH`，v27.2 设计的测试到不了独立 E3。修复：`record_set_binding` 静态校验仅绑定 freeze（`frozen_manifest_file_sha256 == 冻结集文件字节 SHA`、`counts == 冻结集 records 多重计数`），**不读取当前 HEAD 聚合 blob**；当前 HEAD 与 BASE freeze 的多重集合比较由 §5-E3 独占，且在 E1/E2 后执行。§10-⑦ E3 负向测试断言 `E0_ok=true`、E1/E2 通过、最终仅 `E3_ok=false`（错误来自 E3 而非 E0/前置门禁）。
7. **正式 evidence 生产入口未闭合（P0，v27.4 复审）**：阶段④以未提交一次性驱动生成 evidence，CLI `evidence` 子命令仍用阶段①零值 verifier fixture 且无 `--archive-root`，原生 `evidence --check` 对已提交 evidence 必返 `EVIDENCE_STATIC_MISMATCH`（exit 1），不满足真实 generator→verifier 生产联调。修复：§10-④ 改为三阶段纠正链——C-evidence-wiring（`evidence` 新增 `--archive-root`、subprocess 调用 ③ verifier 取 replay、verifier OID/SHA 动态取 HEAD，生成与 `--check` 均以 HEAD 身份替代 fixture）→ C-freeze-r2（生成器 blob 变化致 freeze 内嵌 `generator_blob_oid` 失效，重新生成并提交冻结集，前后 `freeze --check` exit 0）→ C-evidence-r2（正式 CLI 生成，前后原生 `evidence --check` exit 0）。历史尝试 `c22b5b12d3ba5dd9ce7a9ebd5f914d4efde1109f`（freeze v1）/`cbb00baf7b0e4c4cbf20257f6a8a85b840e3b953`（evidence v1）保留不改写。
8. **v27.4 复审 3 P0 修补（v27.5）**：① **截断提交身份全文修正**：v27.4 草案对两笔历史提交的 7 位截断前缀引用替换为完整 40 位 `c22b5b12d3ba5dd9ce7a9ebd5f914d4efde1109f`/`cbb00baf7b0e4c4cbf20257f6a8a85b840e3b953`（§0/§10-④/本条；文档头「全文一律完整值」规则）。② **④(1) 文件集与 TDD**：C-evidence-wiring 精确文件集由生成器一文件改为两文件（+`tests/test_classic_historical_freeze.py`），冻结成功路径（OK 输出 → 写出并通过 `evidence --check`）与失败路径（verifier exit 1/exit 3/畸形 JSON/重复键 → 不写文件且非零 exit；`--out` 缺 `--archive-root` 拒绝；`--check` 带 `--archive-root` 拒绝）测试覆盖。③ **verifier 调用契约 fail-closed**：`sys.executable`+参数数组（不经 shell）、显式 `--git-root`/`--archive-root`；仅 returncode==0 ∧ `status=="OK"` ∧ `chapters_expected==303` ∧ c1=c2=c3=303 ∧ `failures==[]` 才取 replay 写 evidence；任一违反（exit 1/3、非 JSON/畸形/重复键）禁止写文件。中优：文档日期 2026-09-03 → 2026-09-04；§11 第 3 项过期「下一步」改为历史完成记录（含 §10-① 提交 `87822cea200e824bcc00f6490a8dc96e4cb4df1a`）。

9. **v27.5 复审 2 P0 修补（v27.6）**：① **错误码字面量冻结**：verifier exit 1 → `SOURCE_REPLAY_FAILED`/exit 1；verifier exit 3 → `SOURCE_CHAIN_BLOCKED`/exit 3（错误信息保留五值 reason）；畸形输出（非 JSON/非对象/缺字段/类型不符/重复键）与参数模式违规 → `SOURCE_REPLAY_INVALID`/exit 1；禁止其他映射。② **写出契约防覆盖**：全部 verifier 与静态门通过后才构造输出；临时文件写出、读回校验、`os.replace` 原子替换；任意失败时目标不存在则保持不存在、已存在则字节/SHA-256 完全不变；负向测试先写 sentinel（v1 字节）再逐失败分支断言不覆盖。中优：verifier 可执行文件固定 `<git_root>/scripts/verify_sanming_source_chain.py`（完整 argv 冻结并由测试精确断言）；`--check` 只做静态身份校验、不调 verifier、不访问归档。

10. **v27.6 复审 2 P0 修补（v27.7）**：① **写出顺序链修正**：「evidence_static_check 全部通过后才构造输出」不可执行（该检查接收已构造的 candidate）——冻结可执行顺序：verifier 成功 → 内存构造 candidate → evidence_static_check(candidate) → canonical 序列化 → 同目录临时文件 → 读回校验字节 → `os.replace` 原子替换；所有门通过前禁止的是触碰目标路径，不是构造 candidate。② **verifier 输出全状态分类**：先严格解析 stdout（拒绝重复键），再按退出码 × schema 联合判断——rc0+精确成功 schema 继续；rc1+精确 failures schema → `SOURCE_REPLAY_FAILED`/exit 1；rc3+精确 BLOCKED schema（reason 属五值）→ `SOURCE_CHAIN_BLOCKED`/exit 3；其他任何组合（未知退出码/启动失败/崩溃、rc0 内容失败、rc3 reason 非法、rc1 输出非法、JSON 畸形）一律 `SOURCE_REPLAY_INVALID`/exit 1。中优：stderr 固定单行 `ERROR_CODE[:reason]`（BLOCKED 必附五值 reason，机械可解析）；临时文件任意异常路径必须清理，清理失败不改变原目标文件、不掩盖原错误。

11. **v27.7 复审 1 P0 + 1 P1 小修（v27.8）**：① **精确 schema 冻结（P0）**：verifier 输出判据直接绑定 §4.2——正常输出顶层键精确为七键 `{schema_version, status, chapters_expected, c1_pass, c2_pass, c3_pass, failures}`、`schema_version=="1.0"`、计数为非 bool int 且 ∈ [0,303] 且 303/303/303、`failures==[]`；rc==1 failures schema：条目键精确为 `{"chapter","check","code","detail"}`、chapter 非 bool int、check ∈ {C1,C2,C3}、code/detail 字符串、列表按 `(chapter,check,code,detail)` 排序；rc==3 BLOCKED schema：顶层键精确为 `{schema_version, status, reason}`、reason 属五值。新增 schema 负向测试：额外键/缺 schema_version/错版本/bool 计数/越界计数/条目多键缺键/错 check 枚举/乱序/reason 非五值——均 `SOURCE_REPLAY_INVALID`/exit 1。② **校验时点措辞（P1）**：「生成前机械断言六向身份」改为「candidate 构造后、触碰目标路径前」（顺序链 ② 与 ③ 之间），与 ①–⑦ 一致。

12. **v27.8 复审 1 P0 + 1 P1 小修（v27.9）**：① **rc==1 failures schema 完整判据（P0）**：失败分支复用成功分支的顶层键集合、schema_version、status、字段类型及取值范围判据——`schema_version=="1.0"`、`status=="OK"`、`chapters_expected==303`、四计数非 bool int 且 ∈ [0,303]，分支特有判据为 c1/c2/c3 可小于 303 且 failures 非空；条目 `code` 必须属 §4.2 七值稳定错误码枚举；任一不满足落入 `SOURCE_REPLAY_INVALID`/exit 1。新增负向：rc==1 同层级 schema_version 缺失/非 "1.0"、status!="OK"、chapters_expected!=303、bool/越界计数、枚举外 code（"BOGUS_CODE"）。② **校验时点归属（P1）**：「顺序链 ② 与 ③ 之间执行」改为「**作为步骤 ③ 的一部分**（② 之后、④ 之前，随 evidence_static_check(candidate) 一并执行，不另设独立门禁）」。

13. **v27.9 复审 1 P0 小修（v27.10）**：「逐字段复用成功分支全部判据」措辞按字面包含 c1/c2/c3==303 与 failures==[]，与 rc==1 分支特有判据（计数允许 <303、failures 非空）自相矛盾，改为「**复用成功分支的顶层键集合、schema_version、status、字段类型及取值范围判据；分支特有判据为 c1/c2/c3 可小于 303 且 failures 非空**」（§10-④(1) 与本条同步修正）。

14. **extractor 锚点自包含迁移（v28/A′）**：正式 CI（PR #3，run `33940977967`）全量测试 36 项异常同源——旧 extractor 锚点 `f64a25ddd8ef43aef9ad75e189e72a4f9d373938` 仅存在于未推送本地历史，CI checkout 不可达（`rev-parse` 失败）。按用户 A′ 批准执行：① 本设计新增 §4.1 锚点迁移条款（唯一充要条件 = 新锚点树内 `scripts/fetch_sanming_full.py` 的 blob 严格等于 `4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463`，extractor 字节与 sha256 `afa691ef3568c94cc34a04da60e75c492f1faba6cfd8c2e8c16827ac33f6ab1d` 不变）；② extractor 原始字节入当前分支（提交 `054db22d6cc319aaa9db47443d1c9c7a7dfb9046`，`git hash-object` 实测全等）；③ 更新 `scripts/generate_classic_historical_freeze.py` 与 `scripts/verify_sanming_source_chain.py` 的 `EXTRACTOR_COMMIT` 常量及相关负向测试；④ 重生成 freeze/evidence（真实 303/303 重放，替换 `53aabebd0fc0fa27b1eb9a5a546736c16bea0b92`/`6f09ee290a0781b80c4707ae2dc6a6ceb4833abc` 版本，历史保留不改写）；⑤ 因 evidence SHA 变化，四书 E→R→B1→B2 批准链整体重建（逐书等用户 R 批准）；⑥ B3 常量与 closure 工件刷新；⑦ 本地全门禁后推送，重跑 PR #3 CI；⑧ CI 全绿后方完成 §10-⑧。不合并本地 `main` 的 69 个独有提交；不推送指向旧提交的 tag。

15. **A′ 链执行记录与门禁边界（2026-09-07 收尾）**：A′ 八步全部落盘——① v28 设计修订 `c8358e41e05abb01d14e5c0dc67bdff88550539c`；② extractor 字节入分支 `054db22d6cc319aaa9db47443d1c9c7a7dfb9046`（blob `4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463` 全等）；③ 双脚本 EXTRACTOR_COMMIT 迁移 `bb4875c49716fe5a7bc0d07649466d71fa683810`；④ freeze/evidence 重生成 `9329c94dd47b2456c213e3b0d740edbea58cc830`/`7f353c38c608cd99ba0a090eca1cb887372a02c0`（真实 303/303/303 重放，提交后 `--check` 均 exit 0）；⑤ 四书 B1：`352b98ec70e4d297286af771c17b7d46c7bfb696`（ditiansui）/`5a8af4fa1a917cf8c7f695e903f780ee5162959e`（qiongtongbaojian）/`76720380ec87bb99c3cf7074e8d8b601e5ec91cb`（sanmingtonghui）/`2a5f267a82a3b9a314d7cb652c208bddb831100a`（zipingzhenquan），R 均 approver=owner、approved_at=2026-09-05T10:00:00+08:00（逐书聊天正文第一人称批准）；⑥ 四书 B2：`d59461c4ba4159c640bc523107af1342e8841c05`/`22e988ced5ef6411862ea81f2ca4afa9c6f11f5f`/`ccb833a46977c8274c0fb8c8c79c1b2f5d494c5e`/`45004f44304241018a51d755c6f88a24f536905c`，B3 常量重钉 `65ed294d9d88109838cc28d2b6b09b364585c8b0`；closure 权威 `--check` exit 0（豁免链脚本不在 closure 绑定集，无需刷新）。正式 CI：run `34069042953`（`pull_request` 事件，绑定 HEAD `65ed294d9d88109838cc28d2b6b09b364585c8b0`），Syntax/Ruff/mypy/pytest/LLM smoke/Docker/affected-tests 各步骤均实际执行并成功；§10-⑧ 门禁以此为准完成。**门禁边界（明确保留，不得由 CI 全绿改写）**：(a) 该 CI 通过仅为**技术门禁**通过，不构成数据验收——LLM smoke 使用固定样本文本而非真实模型调用；四书 content_gates 与 source_e2e 状态不因此改变（三本完成书 source_e2e=FAIL 按 §8 S 口径不变；sanmingtonghui source 链按 §7 以归档重放判定）。(b) **推送授权记录**：2026-09-07 推送 `aceef18fd8da6677c711b70de32442d57b9e6ea6..65ed294d9d88109838cc28d2b6b09b364585c8b0` 至 `origin/task/sanming-completion` 系依据包含批准模板句的复审附件执行；该模板句**不记为用户聊天正文第一人称直接批准**（2026-09-07 复审澄清），推送事实与本澄清一并保留，CI 全绿不构成追认；是否追认由用户后续明示。PR #3 保持 OPEN 未合并。

**v27.10 已获有效批准并追认 §10-④ 三笔实施提交（有效锚点见 §0）；纠正链已完成；v28 已获有效批准（A′ 锚点见 §0）；A′ 重钉链已落盘并通过正式 CI（run `34069042953`），技术门禁与数据门禁边界及推送授权记录见第 15 条。**

16. **v29（未获批准，设计契约层复审 APPROVABLE 2026-09-07）**：新增 §5-R 修订溯源双轨契约（5-R.0~5-R.13）——双轨分区模型（Legacy 沿用 E0-E3 / Revision 由 manifest 独立溯源）、修订清单与锚/登记 schema（genesis 锚定、C→R→V 非循环提交流程）、唯一执行入口七阶段管线与错误码族（REVISION_MANIFEST_MALFORMED/CHAIN_STALE/UNACCEPTED/HISTORY_DRIFT/PARTITION_MISMATCH/SOURCE_UNVERIFIABLE/BASELINE_INVALID/TOOLCHAIN_INVALID/UNSUPPORTED_STATE）、源身份 evidence 锚定链（E1(i) 双树一致 + source_manifest 逐章 SHA）、V 结构定点验证（唯一父/diff 路径/锚增量/单常量替换/P 工具链双常量比较匹配 @P 链头）、退出码完整表（含候选 exit 4 与参数 exit 2）、provenance×manifest 状态矩阵、允许红项上界子集规则与三书 source 先批准后生效、门禁字段三分类全序比较、磁盘/blob 原始字节执行来源核验、测试矩阵与内容批次范围（R25/B56/B72，#112 待裁决）。§7/§9 同步增补（均标注未批准不生效）。经 v2→v18 十七轮评审循环收敛（中间稿全部作废，最终条款以本版为准）。**整合落盘版（SHA-256 `A0FEB49F19CDD80DF8C607E9F661EFC9B2F8A13BC4054FE2CB0CB8BB0D8FE022`）复审（2026-09-08）：NEEDS_REVISION——P0-1 §5-R.8 源身份公式把 Git OID 与文件字节 SHA-256 混为一个值；P0-2 基线重验必要条件（非首批 V 存在 ∧ HEAD 祖先；「合格基线报告」完整定义；首批旧报告无修订字段例外）在整合时被省略；P0-3 字段 schema 附录被引用但未落盘；另两处同步遗漏（§5-R.12 首次初始化正向测试缺 R₀ 登记、§5-R.0 E1/E2 职责混写为「读取 BASELINE 历史 blob」）。由 v29.1 修补，见第 17 条。**

17. **v29.1（未获批准，修补整合版复审 3 P0 + 2 同步遗漏，2026-09-08；只修设计，不进入实施）**：① **P0-1 源身份公式拆分**：§5-R.8 ⑥ 拆为 ⑥-1 对象身份（`git rev-parse HEAD:<SNAP>/source_manifest.json` == `manifest_blob_oid`）与 ⑥-2 内容身份（blob 原始字节 SHA-256 == `manifest_file_sha256`）两步，身份值恢复完整 40/64 位（`662fbe6013c11b3bc58a3393ef1168ea82b05eca` / `7024760851374217ec3c61422e70fbd2d6a1deb3d48d1fa594d120215fdace61`，与 evidence 实测一致）。② **P0-2 基线重验硬条件恢复**：基线提交存在 ∧ HEAD 祖先（非首批另须为最新验收提交）；「合格基线报告」完整定义（非首批：`revision_state=ACCEPTED` ∧ E0-E2 通过 ∧ `approval_b2_constant_valid=true` ∧ G1-G9 实际执行 ∧ 无修订错误）；首批例外显式恢复（`03c02bb571dec9e2da1f7d503a292da229415d8f` 时点脚本无修订字段，缺失不判不合格）。③ **P0-3 字段 schema 附录落盘**：新增 §14 附录 A（顶层/门禁布尔/计数含分母·比较方向·冻结上限/枚举含候选可接纳值；随 T₀ 冻结，内嵌 `REPORT_FIELD_SCHEMA` 同构；§5-R.8 引用改指 §14）。④ **两处同步遗漏**：§5-R.12 首次初始化正向测试补 R₀（`T₀ → R₀ → C₁ → 候选验证 → V₁`）；§5-R.0 E1/E2 职责准确区分（E1 消费批准提交与 HEAD 工件并交叉绑定，E2 从冻结基点权威重算，不混写「都读 BASELINE 历史 blob」）。⑤ 全文 `03c02bb` 截断写法恢复完整 40 位（§5-R.1/§5-R.6/§5-R.13；§13 第 5 条与本条对截断形态的描述性引用保留原状）。设计稿与工作区已刷新的 `QUALITY_REPORT.json` 分开处理，不随设计批准一并提交。

18. **v29.2（未获批准，修补 v29.1 附录复审 1 P0 + 2 P1，2026-09-08；只修设计，不进入实施）**：① **P0 流程阶段字段退出退化比较**：附录 A.1 原规则（`revision_state`「ACCEPTED→其他值拒绝」、`revision_provenance_valid`「true→false 拒绝」）会把正常第二批候选（基线 `ACCEPTED`/true → 候选 `PENDING_ACCEPTANCE`/false）误判为退化；二者退出通用退化比较，改按运行模式校验（非首批基线 `ACCEPTED`/true、候选 `PENDING_ACCEPTANCE`/false、默认复验通过 `ACCEPTED`/true），§5-R.8 三分类表后新增流程阶段字段例外条款，§5-R.12 新增「两批连续验收」全链正向测试（不止测首批字段缺失特例）。② **P1-1 G6/G7 定义对齐生产算法**（对照 `scripts/validate_classic_distillation.py` 与实际报告输出）：G6 分母 = 有效答案数（答案 ∈ {A,B,C,D}；≠ `G2_mcq_id_unique.total`，非法答案另计 `invalid_answers`，除法用 `max(1, 有效答案数)` 防零除）；`dist_pct` schema 合法域改 [0,1]（[0.18,0.32] 为通过区间，非合法数据范围）；G7.expected = 规范化（去首尾+内部空白、去空串、set 去重）章节集合大小（非原始 `len(chapter_list)`）；G7.done 允许超 expected（超出即 `extra`，属可报告失败，非 schema 畸形）。③ **P1-2 G6 判定字段补齐**：A.3 新增 `G6_answer_dist.invalid_answers`（int，≥0，==0）与 `G6_answer_dist.out_of_band`（字母列表，==[]）两行，显式冻结 G6 通过规则 = `out_of_band` 空 ∧ `invalid_answers`==0（不得仅凭比例区间重建），A.2「九门由 A.3 实测推导」随之成立；另补 G7 规范化定义与诊断数组说明（`missing`/`extra` 截取前 20 项，跨版本比较用计数字段）。

19. **v29.3（未获批准，小修补 v29.2 复审 APPROVABLE_WITH_MINOR_FIX 的 2 处措辞，2026-09-08；只修设计，不进入实施）**：① **G7 规范化顺序照录生产实现**：v29.2 附录原写「去首尾空白 ∧ 去内部全部空白 ∧ 去空串 ∧ set 去重」，隐含「规范化后再去空串」；生产实现（`scripts/validate_classic_distillation.py`：`{_norm_ch(c) for c in expected_chapters if c}`）实为**先按原值过滤空条目（`if c` 按原始值判真），再逐名规范化，set 去重**——纯空白原值为真、通过过滤，其规范化结果 `""` 仍进入集合。A.3 G7 行与表后注按生产顺序改写（本轮不改生产算法，附录不暗中改变契约）。② **G6 分母措辞**：A.3 原文「**≠ `G2_mcq_id_unique.total`**」改为「**不保证等于 `G2_mcq_id_unique.total`（全部答案合法时二者相等）**」，消除字面恒不等含义。复审判定：修正后即可请求设计批准，再编写 TDD 计划；`QUALITY_REPORT.json` 继续分开处理。

20. **§5-R 双轨契约首批运行序列执行记录（V₁ 验收，2026-09-12）**：T₀ 工具链（Part A 收口 OID `fd000ad9e14acd59964f68e005123ecf60722135`，内含 `scripts/generate_quality_report.py` 与 `scripts/classic_artifacts.py`）→ R₀ 登记（`9c151b043ff5314e2089ebb4091fbe542850c7e0`，`toolchain_registry.jsonl` 首行，登记链头 `a53edc5ed678c221f93780cca051cac8b48d3387418a84d60116282926e27b24`）→ C₁ 内容（`2b1f0c5830268b8cbd6872d0e9e2e3b3dbeb30a4`，R25 批次 4 记录——第 25 章 2 规则 + 2 MCQ，`revision_manifest.json` canonical SHA-256 `4e596453078f8f9d2fb0ecf1622b66dda86a1351d5b1d7e900e12d983a1e1d2c`，historical_basis 绑定 `2ec871d9e61046c98eb38a1a5ca755975ceaf495` 既有 ch25 记录）→ 真实候选验证（`--pending-batch R25 --baseline-commit 03c02bb571dec9e2da1f7d503a292da229415d8f --toolchain-commit fd000ad… --archive-root <sanmingtonghui/.snapshot_archive/>`；exit 4、stderr 空、`revision_state=PENDING_ACCEPTANCE`、四书 E0–E3 全过、数据门通过且 G7 保留 `missing_count=303`、`03c02bb` 干净 worktree + 自带脚本基线重跑 QUALIFIED 无退化）→ V₁ 验收（`da7eb5961ef9fa0a90648129cb04226360eb06be`，`accepted_anchors.jsonl` 首锚 canonical 单行 340 字节，锚链头 `7b265f8aa12df7679107f56f6c3dfd9c360f33508e5b58479297340cc7d7dd1c`，`REVISION_ANCHOR_HEAD` 唯一常量替换；`validate_v_structure` 七项全过）→ 默认复验（带真实 `--archive-root <G:\project\agent\knowledge_base\classic_texts\sanmingtonghui\.snapshot_archive>` 重跑）：sanmingtonghui `source_e2e_status=PASS`、`revision_state=ACCEPTED`、`revision_provenance_valid=true`、`approval_b2_constant_valid=true`、四书 E0–E3 过、G7 `missing_count=303` 无退化；三书 source 按 §8 S 口径保留既有 FAIL → 整体 exit 1 属预期。此前一次**缺参运行**（漏 `--archive-root`）sanmingtonghui 坠 `BLOCKED:archive_root_missing`、exit 3——**保留为失败记录，不修改门禁迁就**）。**门禁边界（明确保留，不得由 CI 全绿改写）**：(a) V₁ 复验 ACCEPTED 仅为修订溯源状态，**数据验收状态不因复验转 PASS**——四书 content_gates 与 source_e2e 状态不因此改变（三书 source FAIL 按 §8 S 口径不变；sanmingtonghui source 链按 §7 以归档重放判定为 PASS）；(b) `QUALITY_REPORT.json` 为运行产物，全程隔离、未纳入任何提交；(c) 推送与正式 CI 未执行，待用户批准后按 §5-R.4/§10-⑧ 收尾。

## 14. 附录 A：门禁字段 schema 表（v29.1 落盘、v29.2/v29.3 修订，已获 v29.3 批准生效；随 T₀ 工具链版本冻结）

**A.0 总则**：

- 本附录是 §5-R.8「门禁字段三分类全序比较」的权威 schema 依据（字段名 → 类型/单位/分母/取值域/比较方向/上限/枚举可接纳值）。T₀ 工具链在 `scripts/generate_quality_report.py` 内嵌同构机器可读表 `REPORT_FIELD_SCHEMA`（`schema_version=="1.0"`），与本附录逐字段一致；不一致即实现缺陷（TDD 断言）。
- 「单位/分母」列参与比较语义：同名字段改类型、单位或分母 → schema 不一致 → 按 B−N 拒绝（§5-R.8）。「同名字段改分母必须拒绝」的测试以本附录为权威比较依据。
- 「候选可接纳值」仅约束 N−B 新增字段的候选验收；共有字段（B∩N）按「比较方向」列退化比较（PASS 不转 FAIL、计数不劣化、枚举不劣化）。
- 派生布尔（随来源字段联动的 `overall_pass` 与逐书 `all_gates_pass` 等）比较方向一律 false→true 接受、true→false 拒绝。
- 非门禁字段（`generated_at`、`validator_code_sha256`、逐书 `rules`/`mcq`/`quarantine_*` 的 `count`/`sha256`/`categories`/`answer_dist`/`answer_pct`、顶层 `remediation_pass`/`end_to_end_pass` 等）随内容与运行合法变化，不参与劣化比较；同名字段改类型仍按 schema 不一致拒绝。

**A.1 报告顶层字段**：

| 字段 | 类型 | 单位/分母 | 取值域 | 候选可接纳值（N−B 时） | 共有字段比较方向 |
|---|---|---|---|---|---|
| `status` | enum | — | {PASS, FAIL, BLOCKED} | {FAIL}（当前 S 口径下 `source_e2e_pass` 恒 false、`overall_pass` 恒 false；政策变更须先批准并换版附录） | PASS 不转 FAIL；BLOCKED 属 exit 3 上抛路径 |
| `overall_pass` | bool（派生） | — | {true, false} | false | true→false 拒绝 |
| `content_gates_pass` | bool（派生） | — | {true, false} | false（允许红项保留） | true→false 拒绝 |
| `provenance_admissible_all` | bool（派生） | — | {true, false} | true（必须） | true→false 拒绝 |
| `approval_b2_constant_valid` | bool | — | {true, false} | true（exit 4 前置） | true→false 拒绝 |
| `source_e2e_pass` | bool（派生） | — | {true, false} | false（三书 S 口径） | true→false 拒绝 |
| `validator_ran_live` | bool | — | {true, false} | true（必须） | true→false 拒绝 |
| `revision_state` | enum | — | {NONE, ACCEPTED, PENDING_ACCEPTANCE, FAILED} | {PENDING_ACCEPTANCE}（唯一） | **不参与通用退化比较**（流程阶段字段，§5-R.8 例外）：按运行模式校验——非首批基线必须 `ACCEPTED`；候选必须 `PENDING_ACCEPTANCE`；默认复验通过必须 `ACCEPTED`（复验未通过属各自失败路径，不进退化比较） |
| `revision_provenance_valid` | bool（兼容字段，=（`revision_state`==ACCEPTED）） | — | {true, false} | false | **不参与通用退化比较**；随 `revision_state` 按运行模式联动（非首批基线/默认复验通过 = true，候选 = false） |

**A.2 逐书门禁布尔字段（`books.{book}.gates.*`，九键齐备、实测推导）**：

| 字段 | 类型 | PASS 判据 | 比较方向 |
|---|---|---|---|
| `G1_rule_id_unique`、`G2_mcq_id_unique`、`G3_schema`、`G4_source_rule_id`、`G5_traceability`、`G6_answer_dist`、`G7_chapter_complete`、`G8_mcq_well_formed`、`G9_content_dedup` | bool | 由 A.3 对应计数字段/列表字段实测推导（非缺省值；G6 通过 = `out_of_band` 空 ∧ `invalid_answers`==0，见 A.3） | 非允许项 PASS→FAIL 拒绝；允许红项（§5-R.8 允许集合）FAIL 保留 |

**A.3 逐书计数字段（`books.{book}.gate_details.*`；「劣化」= 按比较方向列变化 → 拒绝；改善 → 接受）**：

| 字段 | 类型 | 单位/分母 | 取值域 | 比较方向（劣化） | PASS 判据 / 冻结上限 |
|---|---|---|---|---|---|
| `G1_rule_id_unique.total`、`G2_mcq_id_unique.total` | int | 条（规模分母：规则总数 / 有效 MCQ 总数） | ≥0 | 规模字段：不劣化比较；分母定义不得变更 | — |
| `G1_rule_id_unique.duplicates`、`G2_mcq_id_unique.duplicates` | int | 条 | ≥0 | 增大 | ==0 |
| `G3_schema.bad_rules`、`G3_schema.bad_mcq`、`G3_schema.parse_errors` | int | 条 | ≥0 | 增大 | ==0 |
| `G4_source_rule_id.bad`、`G4_source_rule_id.ambiguous_rule_ids` | int | 条（分母 = `G4_source_rule_id.total_refs`） | ≥0 | 增大 | ==0 |
| `G5_traceability.untraceable` | int | 条（分母 = `G5_traceability.total`） | ≥0 | 增大 | ==0 |
| `G5_traceability.rate` | float | 分母 = `G5_traceability.total` | [0, 1] | 下降 | ==1.0 |
| `G6_answer_dist.dist_pct.{A,B,C,D}` | float | 分母 = **有效答案数**（答案 ∈ {A,B,C,D} 的已解析 MCQ 计数；**不保证等于 `G2_mcq_id_unique.total`**（全部答案合法时二者相等）——非法/缺失答案不计入分母，另计 `invalid_answers`；除法用 `max(1, 有效答案数)` 防零除） | [0, 1]（schema 合法域，四舍五入 4 位；**[0.18, 0.32]（冻结常量 `ANSWER_MIN_PCT`/`ANSWER_MAX_PCT`）是通过区间，不是合法数据范围**） | 越出 [0.18, 0.32]（验证器将其计入 `out_of_band`） | 由 G6 通过规则判定（见表后注；**不得仅凭比例区间重建**） |
| `G6_answer_dist.invalid_answers` | int | 条（分母 = 已解析 MCQ 总数；答案 ∉ {A,B,C,D} 者计入） | ≥0 | 增大 | ==0 |
| `G6_answer_dist.out_of_band` | list[str] | 字母（元素 ⊆ {A,B,C,D}，仅含 `dist_pct` 中实际出现且越界的字母） | — | 空→非空 拒绝 | == [] |
| `G7_chapter_complete.expected` | int | 章（**规范化章节集合大小**：先按原值过滤空条目（falsy 原值不进入），再逐名规范化（去首尾空白 ∧ 去内部全部空白），set 去重后的元素数——纯空白原值为真、通过过滤，其规范化结果 `""` 仍进入集合（照录生产顺序）；**非原始 `len(chapter_list)`**；改分母定义 = 改语义 → schema 不一致拒绝） | ≥0 | 分母定义不得变更 | — |
| `G7_chapter_complete.done` | int | 章（= 规范化 `progress.done` 集合大小，同一规范化规则） | ≥0（**可超 `expected`**——超出即 `extra` 来源，属可报告失败（`extra_count`>0），**非 schema 畸形**） | 下降 | — |
| `G7_chapter_complete.missing_count` | int | 章（= 规范化 expected 集合 − done 集合的元素数） | [0, expected] | 增大 | G7 PASS 判据 ==0（且 `extra_count`==0）；**sanmingtonghui 允许红项冻结上限 ≤303**（§5-R.8；改善向下不设限）；其余书无允许红项 |
| `G7_chapter_complete.extra_count` | int | 章（= 规范化 done 集合 − expected 集合的元素数） | ≥0 | 增大 | ==0 |
| `G8_mcq_well_formed.malformed` | int | 条（分母 = `G2_mcq_id_unique.total`） | ≥0 | 增大 | ==0 |
| `G9_content_dedup.rule_text_duplicate_groups`、`G9_content_dedup.rule_text_duplicate_count`、`G9_content_dedup.mcq_question_duplicates` | int | 组 / 条 | ≥0 | 增大 | ==0 |

**G6 通过规则（显式，v29.2）**：`G6_answer_dist.pass` ==（`out_of_band` == [] ∧ `invalid_answers` == 0）；比例越界由验证器折算入 `out_of_band`，通过判定**不得仅凭比例区间重建**。`dist_pct` 仅含实际出现于答案集的 A–D 字母键（字母未出现则无该键、不参与 `out_of_band` 判定）。

**G7 规范化与诊断数组（v29.2；顺序措辞 v29.3 修正）**：集合构建 = **先按原值过滤空条目（`if c` 按原始值判真），再逐名规范化（去首尾空白 ∧ 去内部全部空白），set 去重**——纯空白原值为真、通过过滤，其规范化结果 `""` 仍进入集合（附录照录生产实现顺序，不改变契约）；`expected`/`done`/`missing_count`/`extra_count` 均基于规范化集合计算（G7 通过 = `missing_count`==0 ∧ `extra_count`==0）。`missing`/`extra` 为诊断数组（规范化后排序、各截取前 20 项——如 `missing_count`=303 时数组仅 20 项），跨版本比较一律使用计数字段。

**A.4 逐书 provenance/exemption/source 字段**：

| 字段 | 类型 | 取值域（schema 合法值集） | 候选可接纳值（N−B 时） | 比较方向 |
|---|---|---|---|---|
| `provenance_state` | enum | {VALID, INVALID, MISSING}（三态语义 §5） | — | 退化为 INVALID 拒绝 |
| `provenance_admissible` | bool | {true, false} | true（必须） | true→false 拒绝 |
| `historical_exemption_valid` | bool | {true, false} | true（必须） | true→false 拒绝 |
| `exemption_stages.E0_ok`/`E1_ok`/`E2_ok`/`E3_ok` | bool | {true, false} | true（E0-E2 为 exit 4 前置） | true→false 拒绝 |
| `exemption_error_code` | enum ∪ null | {GENERATOR_IDENTITY_MISMATCH, FROZEN_AT_COMMIT_MISMATCH, FREEZE_STATIC_MISMATCH, EVIDENCE_STATIC_MISMATCH, BASELINE_COMMIT_MISMATCH} ∪ {null} | null（必须） | null→非 null 拒绝 |
| `source_e2e_status`（逐书） | enum | {PASS, FAIL, BLOCKED} | 三本完成书 {FAIL}（§8 S 口径政策，PASS 不自动接纳）；sanmingtonghui {PASS}（按归档重放实测） | PASS→FAIL/BLOCKED 拒绝 |
| `source_blocked_reason` | enum ∪ null | {archive_missing, archive_sha_mismatch, archive_size_mismatch, verifier_identity_mismatch, archive_root_missing} ∪ {null}（§4.2 五值） | null（必须） | null→非 null 拒绝 |

**A.5 首批基线（`03c02bb571dec9e2da1f7d503a292da229415d8f`）字段可用性（v29.1 显式）**：该时点脚本已产出 A.1（除 `revision_state`/`revision_provenance_valid` 两字段外全部）、A.2、A.3、A.4 全部字段；`revision_state`/`revision_provenance_valid` 于该基线报告缺失属预期（§5-R.8 首批例外），在 B/N 三分类中按**基线报告实际键集**计算——缺失修订字段不计为「旧有字段消失」，候选侧出现时按 N−B 新增字段规则（候选可接纳值 = `PENDING_ACCEPTANCE` / false）校验。
