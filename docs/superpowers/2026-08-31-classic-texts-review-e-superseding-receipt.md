# Review E Superseding Receipt（清洁冻结链，已受跟踪）

> 日期：2026-08-31 ｜ 分支：`integration/classic-texts-clean` ｜ Supersedes：`docs/superpowers/2026-08-29-classic-texts-posix-cleanup-verification-receipt.md`（老 receipt 提交 `db54345`，仅对老链保持历史证据效力）
> 本文件是**受 git 跟踪的持久证据**，对应 closure 规格 `re_freeze_order` 步骤 9：先发布本 receipt，再推送并跑正式 CI。老链 receipt 不删除、不改写。

## 1. 结论

- **Windows 四文件回归：完整绿色**（同一命令、受测 HEAD `75558d7`、exit 0）。
- **逐文件新旧 blob 对照与 `review_e_supersession_policy` 预测完全一致**：恰 5 个代码侧文件 blob 变化，其余不变，无静默 SHA 复用。
- 受测 HEAD 上两道 `--check`（closure 九层验证 + manifests 冻结链验证）均 exit 0。
- Ubuntu 三个 POSIX 测试证据：**待推送后的正式 CI 提供**（本 receipt 发布于推送之前，顺序即步骤 9）。

## 2. 受测链身份

| 项 | 值 |
|---|---|
| base（origin/main） | `3d3b41cf65af487b03ca5233a109fee14191b88c` |
| C2（overlay candidate） | `80bc630396f31c6b6c122e49ef97f6d912e6f636`（tree `967f3f9edce4e7148cfb0d291208655661774a6f`） |
| tooling payload（S1） | `ba7cc51423e27502c8fc19fbdaa31bfe77807491` |
| freeze commit（S2） | `d7922bb932e8d572cd3c55d0aeca04442d7dd5f7` |
| freeze tag | `CLASSIC_ACCEPTANCE_FREEZE_V2` → tag 对象 `98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7` → `d7922bb9…` |
| freeze-anchor-record（S4） | `ed5493a94d0268b88f2dca448f963880e7cc1ad5` |
| S5（generator+tests 迁移） | `5f4f7c59b2baf75192e292738030c411669ace0f` |
| S6（closure 产物，**受测 HEAD**） | `75558d79662a638d92ab0db80760758d119cb6a8`（四文件回归运行期间 `git status --porcelain` 为空） |
| **phase-A tooling pin（本 receipt 必录项）** | `ed5493a94d0268b88f2dca448f963880e7cc1ad5` —— 与 closure 产物 JSON `source.tooling_blob_pin_commit` 一致 |
| generator blob | `9fa0fdc6b190316a9804e6cdd2be6a87bae92ff4`（= HEAD 上 `scripts/generate_acceptance_manifests.py` 的 git blob，本次 `ls-tree` 复核） |
| 冻结身份 manifests | identity `0279e30b92f70f8b7cce9c786070fc201cfc3fac86826ef6403b15ad90c5aad2`；chapter `ba8ab35e7b98e3a0578f7b62f758e2faff1bbe73d480e153c25b6c74b497d1cf` |

## 3. Touched blob 新旧对照（政策要求逐文件列出）

old = 老链最终态 `c537e78e78895579a6bd6859db5b9a3fb16927fb`（`acceptance/task1` HEAD，含 closure 生成器）；new = 受测 HEAD `75558d79662a638d92ab0db80760758d119cb6a8`。

| 文件 | old blob | new blob | 判定 |
|---|---|---|---|
| `scripts/classic_acceptance_common.py` | `72e275b65a7c8ea5bd1606c6b5ee1f836e72c498` | `2761e8589bb44b471d493323edb09a5fe26d449d` | **变**（FROZEN_* 4 常量重绑 C2 链） |
| `tests/classic_acceptance_fixtures.py` | `e2d1efb8d174a7358e9f6f9eef43e35430049fc0` | `e393cdd67b830d3c0d8cc29b3311c9312776abc3` | **变**（COMMIT 常量重绑） |
| `scripts/generate_acceptance_manifests.py` | `4012500ab0754f3a93608461e2913ab05869dc8b` | `9fa0fdc6b190316a9804e6cdd2be6a87bae92ff4` | **变**（COMMIT_DEFAULT/FREEZE_TAG 重绑；新值==冻结 generator blob） |
| `tests/test_generate_acceptance_manifests.py` | `5bbba5169dd26750cafd2d12bace0dcb9d2aa5ed` | `d861d6a4bd32ff3efa58ce27293873a0cd3abddb` | **变**（COMMIT 常量重绑） |
| `scripts/generate_acceptance_integration_closure.py` | `e7b7381246faf055fb20dfe682349d56a645ba0a` | `9df3eea22cb9d79627fdaf04147b3f118a097b48` | **变**（OLD_CANDIDATE→C2、TOOLING_PIN_COMMIT→`ed5493a…`、S5 三项适配） |
| `scripts/classic_acceptance_sampling.py` | `703b44cf5d47354d3dbf9f670d46c5fa0d6be20f` | 同 old | 不变（政策预测 ✓） |
| `scripts/classic_acceptance_review.py` | `9e91a8e4a856e92f86311db4f5b9b486fadf7546` | 同 old | 不变（政策预测 ✓） |
| `tests/test_classic_acceptance_review.py` | `09760df093604a67adc7023f26edceffb272c0bd` | 同 old | 不变（政策预测 ✓） |

交叉核对：前表 5 个身份 blob（common/fixtures/sampling/review 脚本/review 测试）与 closure 产物 JSON `review_e_code_identity_blobs` 五项逐一相等。新链 `code_freeze_touch_list.short_sha_only = []`（政策预测 ✓）。

## 4. Windows 复跑证据

- **四文件全量**：`python -m pytest tests/test_classic_acceptance_sampling.py tests/test_classic_acceptance_review.py tests/test_classic_acceptance_e2e.py tests/test_generate_acceptance_manifests.py -q`（解释器 `G:\project\agent\.venv\Scripts\python.exe`，cwd `G:\project\agent-clean`）→ **135 passed, 3 skipped in 762.77s (0:12:42)，exit 0**。3 个 skip 恰为 POSIX-only 清理测试。
- **聚焦清理**：`python -m pytest tests/test_classic_acceptance_review.py -q -k cleanup` → **4 passed, 2 skipped, 61 deselected in 21.67s，exit 0**（2 skip 为 POSIX-only）。
- **本机资源门禁记录（诚实留痕）**：同一命令此前三次被本机 commit-charge 耗尽阻断——①133 passed/3 skipped/2 failed（Git 大 pack 无法映射）；②134/3/1（Git 子进程启动失败，该用例单独运行通过）；③明确 `WinError 1455 页面文件太小` + `MemoryError` + git malloc 失败。诊断：RAM 15.93 GB，页面文件 C: 2MB + G: 3287MB，commit limit 19.14 GB、free ≈2.6 GB，`AutomaticManagedPagefile=False`，repo pack 351.50 MiB/496 loose。三次失败均为资源类，无断言或身份漂移。缓解：repo-local git 内存旋钮 `core.bigFileThreshold=64m`、`core.packedGitLimit=512m`、`core.packedGitWindowSize=32m`、`core.deltaBaseCacheLimit=96m`、`pack.windowMemory=64m`、`pack.threads=1`，未重启系统；随后同一命令一次全绿。

## 5. 受测 HEAD 同点 `--check` 复跑（2026-08-31）

- `python scripts/generate_acceptance_integration_closure.py --check --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 --base-commit 3d3b41cf65af487b03ca5233a109fee14191b88c --no-legacy --tooling-pin-commit ed5493a94d0268b88f2dca448f963880e7cc1ad5` → **exit 0**（完整 pin 为外部冻结输入，未从磁盘/HEAD 自举）。
- `python scripts/generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid 98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7` → **exit 0**，输出：tag 对象→freeze commit→payload→candidate 链一致；两 manifests `regenerated==committed==frozen`；generator blob==frozen；`freeze check OK`。

## 6. Ubuntu 复跑（待正式 CI）

三个 POSIX-only 测试（blob 与老链逐字节一致，`09760df0…` 未变）：

1. `test_run_cli_result_reports_uncertain_cleanup_when_killpg_fails`
2. `test_run_cli_result_reaps_descendant_after_group_leader_exits`
3. `test_cleanup_finally_reaps_when_read_json_fails`

将在推送 `integration/classic-texts-clean` 后的正式 `ubuntu-latest` CI 上执行；Windows-only 变体在 ubuntu 上应正确 SKIPPED。本 receipt 发布于推送之前，符合步骤 9 顺序。

## 7. 可复算

```powershell
# 四文件全量（plan 文档 :6661 原命令）
python -m pytest tests/test_classic_acceptance_sampling.py tests/test_classic_acceptance_review.py tests/test_classic_acceptance_e2e.py tests/test_generate_acceptance_manifests.py -q
# 聚焦清理
python -m pytest tests/test_classic_acceptance_review.py -q -k cleanup
# closure 九层验证（pin 为外部输入）
python scripts/generate_acceptance_integration_closure.py --check --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 --base-commit 3d3b41cf65af487b03ca5233a109fee14191b88c --no-legacy --tooling-pin-commit ed5493a94d0268b88f2dca448f963880e7cc1ad5
# manifests 冻结链验证
python scripts/generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid 98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7
# blob 对照
git ls-tree c537e78e78895579a6bd6859db5b9a3fb16927fb -- scripts tests
git ls-tree 75558d79662a638d92ab0db80760758d119cb6a8 -- scripts tests
```

---

```json
{
  "receipt_schema": "review_e_superseding_receipt_v1",
  "date": "2026-08-31",
  "supersedes": {
    "receipt_file": "docs/superpowers/2026-08-29-classic-texts-posix-cleanup-verification-receipt.md",
    "receipt_commit": "db54345",
    "note": "Old receipt remains valid as historical evidence for the old chain (acceptance/task1); this receipt supersedes it for the clean chain only."
  },
  "branch": {
    "name": "integration/classic-texts-clean",
    "tested_head_commit": "75558d79662a638d92ab0db80760758d119cb6a8",
    "worktree_clean_during_regression": true
  },
  "chain": {
    "base_commit": "3d3b41cf65af487b03ca5233a109fee14191b88c",
    "candidate_commit": "80bc630396f31c6b6c122e49ef97f6d912e6f636",
    "candidate_tree": "967f3f9edce4e7148cfb0d291208655661774a6f",
    "tooling_payload_commit": "ba7cc51423e27502c8fc19fbdaa31bfe77807491",
    "freeze_commit": "d7922bb932e8d572cd3c55d0aeca04442d7dd5f7",
    "freeze_tag": "CLASSIC_ACCEPTANCE_FREEZE_V2",
    "freeze_tag_object_oid": "98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7",
    "freeze_anchor_record_commit": "ed5493a94d0268b88f2dca448f963880e7cc1ad5",
    "generator_migration_commit": "5f4f7c59b2baf75192e292738030c411669ace0f",
    "closure_artifacts_commit": "75558d79662a638d92ab0db80760758d119cb6a8",
    "phase_a_tooling_pin_commit": "ed5493a94d0268b88f2dca448f963880e7cc1ad5",
    "phase_a_tooling_pin_note": "Recorded in the closure artifact JSON source.tooling_blob_pin_commit; passed as an external frozen input to --check; never bootstrapped from disk JSON or runtime HEAD.",
    "generator_blob_oid": "9fa0fdc6b190316a9804e6cdd2be6a87bae92ff4",
    "identity_manifest_sha256": "0279e30b92f70f8b7cce9c786070fc201cfc3fac86826ef6403b15ad90c5aad2",
    "chapter_manifest_sha256": "ba8ab35e7b98e3a0578f7b62f758e2faff1bbe73d480e153c25b6c74b497d1cf"
  },
  "blob_supersession_table": {
    "old_base_commit": "c537e78e78895579a6bd6859db5b9a3fb16927fb",
    "new_base_commit": "75558d79662a638d92ab0db80760758d119cb6a8",
    "cross_checked_against": "closure JSON review_e_code_identity_blobs (5 identity blobs match exactly)",
    "files": [
      {"path": "scripts/classic_acceptance_common.py", "old": "72e275b65a7c8ea5bd1606c6b5ee1f836e72c498", "new": "2761e8589bb44b471d493323edb09a5fe26d449d", "changed": true},
      {"path": "tests/classic_acceptance_fixtures.py", "old": "e2d1efb8d174a7358e9f6f9eef43e35430049fc0", "new": "e393cdd67b830d3c0d8cc29b3311c9312776abc3", "changed": true},
      {"path": "scripts/generate_acceptance_manifests.py", "old": "4012500ab0754f3a93608461e2913ab05869dc8b", "new": "9fa0fdc6b190316a9804e6cdd2be6a87bae92ff4", "changed": true},
      {"path": "tests/test_generate_acceptance_manifests.py", "old": "5bbba5169dd26750cafd2d12bace0dcb9d2aa5ed", "new": "d861d6a4bd32ff3efa58ce27293873a0cd3abddb", "changed": true},
      {"path": "scripts/generate_acceptance_integration_closure.py", "old": "e7b7381246faf055fb20dfe682349d56a645ba0a", "new": "9df3eea22cb9d79627fdaf04147b3f118a097b48", "changed": true},
      {"path": "scripts/classic_acceptance_sampling.py", "old": "703b44cf5d47354d3dbf9f670d46c5fa0d6be20f", "new": "703b44cf5d47354d3dbf9f670d46c5fa0d6be20f", "changed": false},
      {"path": "scripts/classic_acceptance_review.py", "old": "9e91a8e4a856e92f86311db4f5b9b486fadf7546", "new": "9e91a8e4a856e92f86311db4f5b9b486fadf7546", "changed": false},
      {"path": "tests/test_classic_acceptance_review.py", "old": "09760df093604a67adc7023f26edceffb272c0bd", "new": "09760df093604a67adc7023f26edceffb272c0bd", "changed": false}
    ],
    "policy_conformance": "Exactly the five predicted code-side blobs changed; no silent SHA reuse; new-chain short_sha_only list is empty."
  },
  "windows_local_regression": {
    "four_file_command": "python -m pytest tests/test_classic_acceptance_sampling.py tests/test_classic_acceptance_review.py tests/test_classic_acceptance_e2e.py tests/test_generate_acceptance_manifests.py -q",
    "four_file_result": "135 passed, 3 skipped in 762.77s (0:12:42)",
    "four_file_exit_code": 0,
    "focused_cleanup_command": "python -m pytest tests/test_classic_acceptance_review.py -q -k cleanup",
    "focused_cleanup_result": "4 passed, 2 skipped, 61 deselected in 21.67s",
    "focused_cleanup_exit_code": 0,
    "skips_note": "All skips on Windows are the POSIX-only cleanup tests."
  },
  "resource_gate_record": {
    "blocked_attempts": [
      {"n": 1, "summary": "133 passed, 3 skipped, 2 failed", "failure_class": "git large pack could not be mapped"},
      {"n": 2, "summary": "134 passed, 3 skipped, 1 failed", "failure_class": "git subprocess failed to start; the failing case passed when run alone"},
      {"n": 3, "summary": "explicit WinError 1455 (page file too small) + MemoryError + git malloc failure", "failure_class": "commit-charge exhaustion"}
    ],
    "diagnosis": "RAM 15.93 GB; page files C: 2MB + G: 3287MB; commit limit 19.14 GB with ~2.6 GB free; AutomaticManagedPagefile=False; repo pack 351.50 MiB / 496 loose objects.",
    "mitigation": "Repo-local git memory knobs, no reboot: core.bigFileThreshold=64m, core.packedGitLimit=512m, core.packedGitWindowSize=32m, core.deltaBaseCacheLimit=96m, pack.windowMemory=64m, pack.threads=1.",
    "assertion_or_identity_drift_found": false
  },
  "head_checks": [
    {"command": "generate_acceptance_integration_closure.py --check --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 --base-commit 3d3b41cf65af487b03ca5233a109fee14191b88c --no-legacy --tooling-pin-commit ed5493a94d0268b88f2dca448f963880e7cc1ad5", "exit_code": 0, "date": "2026-08-31"},
    {"command": "generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid 98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7", "exit_code": 0, "output_summary": "tag->freeze->payload->candidate chain consistent; both manifests regenerated==committed==frozen; generator blob==frozen; freeze check OK", "date": "2026-08-31"}
  ],
  "ubuntu_rerun": {
    "status": "pending_official_ci",
    "order_note": "re_freeze_order step 9: publish this receipt, then push and run official CI; the three POSIX tests execute there.",
    "tests": [
      "test_run_cli_result_reports_uncertain_cleanup_when_killpg_fails",
      "test_run_cli_result_reaps_descendant_after_group_leader_exits",
      "test_cleanup_finally_reaps_when_read_json_fails"
    ],
    "covering_blob_unchanged": "tests/test_classic_acceptance_review.py = 09760df093604a67adc7023f26edceffb272c0bd (identical to old chain)"
  }
}
```
