# Acceptance 集成闭包 v3.1（可执行门禁 + 基础设施迁移层）

> 日期：2026-08-29 ｜ 由 `scripts/generate_acceptance_integration_closure.py` 生成（勿手改）
> 复跑：`generate` 重算重写；`--check` 零写入核验；干净分支/CI 用 `--check --candidate-commit <C2> --base-commit <base> --no-legacy --tooling-pin-commit <phase-A 完整 SHA>`

## 0. 本轮修订

- **P0-1（门禁可执行化）**：四条门禁不再是字符串。`build_candidate_overlay_tree()` 在临时 index（GIT_INDEX_FILE）中以 `read-tree <base>` + 698 次 `update-index --cacheinfo` 真实构造 C2 覆盖树；`verify_candidate_tree()` 对树执行四条断言（零删除 / blob 全匹配 / diff 恰 695 / 闭包外逐字节不变）。负对照 `build_narrow_candidate_tree()` 构造“仅 698 路径”的错误树，验证器必须拒绝（gate1 + gate3），并有专项测试。

- **P0-2（基础设施随链迁移）**：生成器、测试与两个产物组成 integration-infrastructure 层（4 路径），计入 `migration_total`，与 17 工具、698 数据同属迁移链；生成器不退役——`--candidate-commit/--base-commit/--no-legacy` 使其在干净分支与 CI 上无需旧候选对象即可复跑全部门禁。

- **P1（完整钉值）**：工具钉值提交为完整 40 位 `ed5493a94d0268b88f2dca448f963880e7cc1ad5`，`verify()` 以 `rev-parse <full>^{commit}` 往返校验；base/candidate 参数同样要求完整 40 位。

- **P0（pin 外部信任根）**：no-legacy 模式下 `--tooling-pin-commit` 为强制参数——`generate` 与 `--check` 缺失即用法错误（退出码 2）；验证器绝不从磁盘 JSON 或运行时 HEAD 自举 pin，`build_closure` 如实记录其实际使用的 pin，`verify()` 交叉核对记录 pin 与请求 pin——把记录 pin 换成内容相同的其他提交无法自证；重冻结步骤 7、CI 命令与 superseding receipt 显式携带完整 phase-A SHA。

## 1. 闭包总量

| 层 | 路径数 | 字节 |
|---|---:|---:|
| 工具/测试/冻结文档（钉值 blob） | 17 | 1594169 |
| 候选数据（覆盖进 C2） | 698 | 14997976 |
| 闭包基础设施（生成器/测试/产物，随链迁移） | 4 | — |
| **迁移总计** | **719** | **16592145** |

- 分组：derived_root_raw=303, extracted_raw=383, quarantine=1, rules_mcq_output=8, snapshot_identity=3。
- 与 `3d3b41cf65af487b03ca5233a109fee14191b88c`：数据 overlap=9（同 blob 3）、变更 695；工具 overlap=1。

## 2. 排除集

- 3 个超大 blob（不在读取闭包内）：`QUALITY_REPORT.json`（354001243）、`provenance.json`（314130603）、`remediation_meta.json`（312701489）
- 蒸馏轨道 10 路径、Phase 8 证据 2 路径（单独任务）
- `knowledge_base` 其余变更 2 个

## 3. 构造政策与可执行门禁

No history cherry-pick from the 129 unpushed commits. C2 is an OVERLAY commit: start from the FULL origin/main tree and replace/add exactly the 698 candidate data paths with their recorded old-candidate blobs; every other origin/main path stays byte-identical; parent = the integration branch base so C2 stays reachable and pushable. The construction is performed and checked by build_candidate_overlay_tree() and verify_candidate_tree() in the tracked generator, NOT by manual steps. The 17 tooling paths and the 4 infrastructure paths land as normal commits on top; the code-side binding files are patched to C2 first (re-freeze order step 2).

- [gate] gate1 executable verify_candidate_tree: C2 vs base deletions == 0
- [gate] gate2 all 698 candidate data paths carry the exact old-candidate blob OIDs and sizes
- [gate] gate3 C2 vs base changed path set == 695 paths (698 minus 3 same-blob)
- [gate] gate4 every base path outside the closure is byte-identical in C2
- [gate] negative control: the narrow tree (698 paths only, no base) MUST be rejected (gate1 + gate3)

## 4. 复跑方式

```
python scripts/generate_acceptance_integration_closure.py generate
python scripts/generate_acceptance_integration_closure.py --check
# step 6b on the clean branch: regenerate artifacts for the NEW chain
python scripts/generate_acceptance_integration_closure.py generate --no-legacy --candidate-commit <C2> --base-commit <base> --tooling-pin-commit <phaseA>
# post-migration verification on the clean branch / CI (no old-candidate object needed):
python scripts/generate_acceptance_integration_closure.py --check --candidate-commit <C2> --base-commit <base> --no-legacy --tooling-pin-commit <phaseA>
python -m pytest tests/test_generate_acceptance_integration_closure.py -q --timeout=120
```
`--check` 每次运行都真实构造覆盖树与窄树并执行门禁断言；另覆盖引用计数、698 路径逐条 blob、分组守恒、排除集、工具 blob、origin/main 关系、触点清单（11 绑定 + 1 短前缀 + 2 产物豁免）、基础设施层完整性与钉值完整 SHA 往返；任一漂移非零退出。

## 5. 重冻结顺序（摘要）

1. construct C2 via build_candidate_overlay_tree(entries, base) and REQUIRE verify_candidate_tree(...) == [] before committing; the narrow-tree negative control must fail
2. patch the code-side binding files to reference C2: classic_acceptance_common.py FROZEN_CANDIDATE_COMMIT, classic_acceptance_fixtures.py COMMIT, generate_acceptance_manifests.py COMMIT_DEFAULT, test_generate_acceptance_manifests.py COMMIT, AND scripts/generate_acceptance_integration_closure.py OLD_CANDIDATE
3. migrate the integration infrastructure layer (generator + tests + regenerated closure artifacts) so the clean branch self-verifies
4. regenerate both identity manifests from C2 with the patched generator (its blob CHANGES; record the new generator blob OID in the regenerated freeze receipt); diff against frozen manifests - only candidate-commit- and generator-derived fields may differ
5. update acceptance-freeze.json + freeze-anchor-record.json + design doc anchors to the new chain (C2, new generator blob, new payload commit, new tag OID)
6. commit tooling + infrastructure; create tooling payload commit; finalize receipt in the freeze commit; tag new freeze tag
6b. on the clean branch regenerate the closure artifacts so the tooling OID table and infra blobs record THIS chain's committed blobs: python scripts/generate_acceptance_integration_closure.py generate --no-legacy --candidate-commit <C2> --base-commit <base> --tooling-pin-commit <phase-A tooling commit>; the recorded pin is the phase-A commit and NEVER has to equal HEAD (a phase-B artifact-only commit keeps the check green), then commit the artifacts as a separate commit
7. on the clean branch/CI run: python scripts/generate_acceptance_integration_closure.py --check --candidate-commit <C2> --base-commit <base> --no-legacy --tooling-pin-commit <phase-A tooling commit full 40-hex SHA>; the full phase-A pin SHA is an external frozen input carried by the CI command and the superseding receipt; then generate_acceptance_manifests.py --check against the new tag (Windows + Ubuntu)
8. run the four-file bounded regression on Windows and the three POSIX tests on Ubuntu
9. publish the superseding Review E receipt (it must record the full phase-A tooling pin SHA), then push and run official CI

Review E supersession 政策见 JSON：5 个代码侧常量文件 blob 必变（含本生成器的 OLD_CANDIDATE），新链 short-prefix-only 集合为空，其余钉值 blob 不变；需 Windows 四文件回归 + Ubuntu 三个 POSIX 测试的复跑证据与 superseding receipt。
