# 经典文本历史 provenance 窄豁免设计 v25（已批准 Approved）

状态：**v25 已批准（Approved）** ｜ 日期：2026-09-03 ｜ 冻结基点：`c5cff699fdb547bd9270acbebe1f485380848751`（branch `task/sanming-completion`）
前版：v24 批准提交被判 INVALID_APPROVAL（两句未以纯正文出现）；v25 以用户纯正文直接发送的 S 句与第一人称批准句重新批准，变更见 §13。
**身份值约定：Git OID 一律 40 位十六进制；SHA-256 一律 64 位十六进制；全文一律完整值，禁止省略号截断。**

---

## 0. 提案状态

- D1(c) 与 D2 公式：**已于 2026-09-03 用户在聊天正文以第一人称逐字批准**，批准锚点如下。
- **§8 口径**：v3–v19 均提议 S；**已于 2026-09-03 用户在聊天正文逐字确认**（确认语句见 §8），记为设计口径 S。
- **批准锚点（2026-09-03，纯正文）**：
  - S 确认语句：`选择 S：本设计不豁免三本完成书的 source 获取链；三书 source_e2e_status="FAIL"，派生 source_e2e_pass=false。`
  - 批准语句：`我批准本设计（D1(c)/D2），批准锚点按 §6 记录后启动 §10 实现。`
  - 批准时 HEAD：`5c5d4a3711f6fd9664603dcfa897568fe9a87211`
  - 批准前文档 SHA-256：`1063A74835207B2F1B635DA0DB302E4C55BFEDCEE096CAC8196571FF6C10F21C`（v24）
- **无效批准尝试记录**：提交 `8966b1d952428f2dda39d2426ad028fd8d4ff2c4`（v22，所记批准句为流程描述/占位式措辞，非用户正文第一人称批准）与 `5c5d4a3711f6fd9664603dcfa897568fe9a87211`（v24，两句仅见于附件/代理叙述，未以纯正文出现）均被判 `INVALID_APPROVAL`。**两提交不改写历史，仅保留此标记。**
- 本设计已整体获批；§10 实施可启动。

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
                           record_set_binding、source_chain 的 HEAD blob SHA（pointer/manifest/
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
- **freeze 静态错误分化（中优-1）**：freeze validator 除 `frozen_at_commit` 外的其余静态校验——顶层字段集、`books`/`kinds` 精确集、两态文件条目、`records` 条目集合（id 唯一/排序）、`counts` 一致性、重复 JSON 键、记录非对象/缺 `id`/`id` 非字符串——任一不匹配 → 稳定错误码 `FREEZE_STATIC_MISMATCH`（与 `FROZEN_AT_COMMIT_MISMATCH` 严格区分：后者仅指基点错）。
- **顶层字段精确集**：`schema_version:"1.0"`、`frozen_at_commit`（40 位，== 基点）、`generator_blob_oid`（40 位）、`books`、`counts`。缺一/多一拒绝。
- **books 精确集**：键 == 四书集合（多书/缺书拒绝）；每书 kinds 键 == `{all_rules, all_mcq, quarantine_rules, quarantine_mcq}` 精确集。
- **文件条目 schema（状态相关，交叉状态非法组合拒绝）**：

```text
present=true  -> {"present": true,  "blob_oid": <40hex>, "byte_size": <int>=0, "records": [...]}
present=false -> {"present": false, "blob_oid": null,   "byte_size": null,  "records": []}
```

- **records 条目精确集**：`{"id": <str>, "sha256": <64hex>}`；按 `id` 排序；同文件 id 唯一。
- `counts`：`{book: {kind: int}}`，与 records 实数一致。
- 解析拒绝：重复 JSON 键、记录非对象、缺 `id`、`id` 非字符串。
- canonical_record_sha256：`sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode("utf-8"))`。
- 文件序列化：全局 canonical 规则（`json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"`，UTF-8 无 BOM，LF）。
- 生成器自校验：重跑字节一致；`blob_oid` 以 `git rev-parse` 重验；`generator_blob_oid` 回填。

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
- evidence 顶层精确字段集、嵌套精确字段集与两态文件条目、record_count==冻结集长度、record_set_binding 计数与 §5-E3 一致（任一不匹配 → `EVIDENCE_STATIC_MISMATCH`）；
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
| record_set_binding | 冻结集文件 + 当前 HEAD 聚合 blob | 解析计数 + §5-E3 比对（不符 → EVIDENCE_STATIC_MISMATCH） |
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
parser     = scripts/fetch_sanming_chapters.py      blob 1842a8d5c732b19a233baa72fd7fec496217722d（BASE 与锚点 f64a25ddd8ef43aef9ad75e189e72a4f9d373938 同 blob，已实测）
chapters   = knowledge_base/classic_texts/sanmingtonghui/chapter_list.txt
                                                      blob 70c5029c29c3443ea2b149a749e7ba6aef904779（BASE 与锚点同 blob，已实测）
extracted  = <SNAP>/extracted/raw_001.txt .. raw_383.txt  （383 个，HEAD Git blob 读取）
tar        = <archive-root>/cf984581ea0a8e8028949733ed98c5bb85f54972723033c489b34e51b48d7cf9.tar
                                                      7,127,040 B  sha256 cf984581ea0a8e8028949733ed98c5bb85f54972723033c489b34e51b48d7cf9（archive-root 为运行参数，相对路径/SHA/大小冻结于此与指针）
extractor  = git 对象 f64a25ddd8ef43aef9ad75e189e72a4f9d373938:scripts/fetch_sanming_full.py
                                                      blob 4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463  sha256 afa691ef3568c94cc34a04da60e75c492f1faba6cfd8c2e8c16827ac33f6ab1d
```

注：`active_ptr` 记录的 `source_manifest_sha256:"ed06d58273072ac8bafffa29962ce95e88a85b7e8edb3b430cde1b42b8bd0b5d"` 语义未钉（实测 ≠ manifest 文件字节 SHA `7024760851374217ec3c61422e70fbd2d6a1deb3d48d1fa594d120215fdace61`，≠ sort_keys canonical 形式 `b5b3eef94242b19133c8ae37a3c63dd2d0a008298b5945fd6f117c5d4c61f7aa`）——**不作为重算事实**，仅历史 builder 输出原样记录；证据绑定以文件字节 SHA 为准。

### 4.2 source 链核验器（Git 跟踪入口，精确输出 schema）

- 调用：`python scripts/verify_sanming_source_chain.py --base <40hex> --archive-root <dir>`（`--base` 默认冻结基点常量；**正式报告链禁止非冻结 base**，见 §7）。本核验器即 `source_chain_check` 的执行体。
- **实现冻结**：`_FOOTER` 与 `_extract_content` 从 Git 对象 `4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463`（提交 `f64a25ddd8ef43aef9ad75e189e72a4f9d373938` 的树内 blob）**AST 提取**后执行，禁止手工副本；同源测试断言提取片段字节 == blob 内源码段。`parse_chapter_list` 从 Git blob `1842a8d5c732b19a233baa72fd7fec496217722d` 加载；`chapter_list.txt` 从 Git blob `70c5029c29c3443ea2b149a749e7ba6aef904779` 读取。
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

**E3 记录集严格相等**：HEAD 聚合 blob 逐记录 `(kind,id,sha)` 与冻结集严格相等。

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

- **CLI exit 码**：任一书 BLOCKED → **3**（与豁免链静态错误同时存在时亦为 3，BLOCKED 优先）；否则 `overall_pass=false` → **1**；全部通过 → **0**。
- 顶层其余：`content_gates_pass = AND(四书)`；`provenance_admissible_all = AND(四书)`；`overall_pass = content_gates_pass AND provenance_admissible_all AND source_e2e_pass`（BLOCKED 时 overall 输出 false 且顶层 status=BLOCKED）。
- 展示：`provenance_state` / `provenance_ok` / `historical_exemption_valid` / `provenance_admissible` / `source_e2e_status` 逐书分离；豁免与 S 事实入 `known_limitations`；豁免链失败错误码（GENERATOR/FROZEN/FREEZE_STATIC/EVIDENCE_STATIC/BASELINE）与 source BLOCKED reason 分列展示互不混淆。
- 当前树预期：四书 provenance 均 MISSING；三命通会 G7 FAIL → `content_gates_pass=false`；三本书 source_e2e=FAIL（§8 已确认 S）→ `overall_pass=false`，exit 1。

## 8. source e2e 口径

- **已确认 S（2026-09-03 用户聊天正文逐字确认）**：三本完成书 `source_e2e_status=FAIL`（gate2 只证迁移等值，不证获取链）；本设计只处理模型 run manifest 缺失。确认语句：`选择 S：本设计不豁免三本完成书的 source 获取链；三书 source_e2e_status="FAIL"，派生 source_e2e_pass=false。`
- T（如将来需要）：另立设计 + 独立审批链，绑定原文精确 blob/SHA，声明"不证明原始获取过程"。

## 9. 未来运行衔接（本设计外）

- E3 严格相等无放宽。首次正式生成运行前须另行升级 run_manifest 契约（逐 ID pre-run rule canonical SHA map）并单独设计采信路径；届时聚合文件变化使本豁免失效，新状态由新链全责。

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
   - evidence 阶段（freeze==evidence==BASE,非基点 → FROZEN_AT_COMMIT_MISMATCH；不涉及 E/R/pointer）
   - 生成器六向身份（改生成器/仅篡改 generator_sha256 → GENERATOR_IDENTITY_MISMATCH）
   - evidence_static_check 结构/计数/静态 SHA 篡改 → EVIDENCE_STATIC_MISMATCH
   - evidence 子命令的 verifier 依赖以"注入式固定 fixture"（冻结的 verifier 输出样本
     + 冻结 blob OID/SHA 值）测试，不依赖真实 verifier。
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
④ C-evidence：运行 evidence 子命令（真实调用 ③ 的 verifier），精确文件集恰为
   evidence JSON 一文件。生成前机械断言生成器六向身份与 frozen_at_commit 第 2 级
   （freeze==evidence==BASE, §4），违者拒绝；提交后从新 HEAD 再跑一次
   `evidence --check`（同 ②）。此阶段做真实 generator→verifier 联调。
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
⑧ 门禁全跑（零提交）
```

顺序不变量：freeze/evidence 必须在 E 生成前入库；verifier blob 先于 evidence 记录；⑤ 必须在逐书循环前（v2 E 生成与校验的代码前置）；B3 必须在全部 B2 后（常量值依赖四书 B2 SHA）。任一提交的文件集违反"恰为"约束 → 该提交无效须重做。
**TDD 与门禁的关系**：TDD（先失败测试后实现）为实施纪律；**机械门禁仅为各提交时点其精确文件集内测试全部通过（GREEN），以及 ②④ 提交后新 HEAD 的 `freeze --check`/`evidence --check` 通过**；RED 运行记录不作为可信证据、不构成提交约束。正式报告的豁免可用性由 E0 每次重算保证（§5），不依赖任何历史运行记录。
TDD 覆盖（详目同前）：冻结生成器（精确 schema/拒绝项/确定性/两子命令/frozen_at_commit 与 FREEZE_STATIC 分化/六向身份绑定/evidence_static_check 结构负向）；核验器（AST 同源、输出 schema、BLOCKED 五枚举、failures 四元组排序、303/303、tar 缺失/身份/工作区 verifier 负向、中文与空格路径 NUL 解析负向）；v2 E/R 精确字段集与镜像复核（10 项）+ 权威重算三方全等（含生产算法等价断言）；指针全字段消费与第 3 级六向 baseline/三方 parent（逐书）；B1/B2/B3 链正反向（含逐书循环与各阶段文件集门禁）；E4 顺序阻断；报告参数链、无条件 source_chain_check 汇合、顶层状态机（BLOCKED 上限）与 exit 码；E0 静态校验每次重算（含全新 clone/替换工件等价场景）；错误优先级短路（五类，单输入单错误码）；三态公式闭合（VALID/INVALID/MISSING）。

## 11. 待用户动作

1. ~~§8 口径逐字确认~~ 已完成（2026-09-03，见 §8）。
2. ~~D1(c)/D2 第一人称逐字批准~~ 已完成（2026-09-03，见 §0 批准锚点）。

## 12. source verifier 身份绑定

- 实现提交后（§10-③），`scripts/verify_sanming_source_chain.py` 的 blob OID 与字节 sha256 记入 evidence `source_chain.verifier_blob_oid/verifier_sha256`（§4；顺序由 §10 冻结）。
- **两段身份核对，各归其链，不重复**：
  - 静态链（`evidence_static_check`，§10-① 测试）：只比对 evidence 记录的 `verifier_blob_oid/verifier_sha256` 是否 == `HEAD:scripts/verify_sanming_source_chain.py` 的 blob OID/字节 sha256；不符 → `EVIDENCE_STATIC_MISMATCH`。
  - 执行链（`source_chain_check` 执行前，§10-③ 测试）：断言 `git hash-object <工作区 verifier 文件>` == 同 HEAD blob OID（disk==HEAD）；不符 → BLOCKED（reason `verifier_identity_mismatch`，属 §4.2 统一枚举）。

## 13. v24 → v25 变更记录

1. **有效批准（流程）**：用户于 2026-09-03 在聊天正文以**纯正文**直接发送 S 选择句与第一人称批准句（`我批准本设计（D1(c)/D2），批准锚点按 §6 记录后启动 §10 实现。`）；流程状态由 Draft 转为 Approved；§0 更新批准锚点（S 确认语句、批准语句、批准时 HEAD `5c5d4a3711f6fd9664603dcfa897568fe9a87211`、批准前文档 SHA-256）。v24 的 `5c5d4a3` 与 v22 的 `8966b1d` 均标记为无效批准尝试。**§10 实施可启动。**