# Phase 8 Freeze v2 Superseding Receipt（marriage-capability，已受跟踪）

> 日期：2026-09-01 ｜ 分支：`task/phase8-marriage-capability`（基于 `integration/classic-texts-clean` @ `1f266be`）｜ Supersedes：Phase 8 冻结 v1（`docs/phase8/marriage-capability/phase8_freeze_manifest.json` 旧状态，仅留历史效力）
> **[RATIFIED，2026-09-01]** 用户在聊天正文直接追认，追认句原文逐字："我追认并批准 Phase 8 计划的 D1=A、D2=A、D3，批准现有 Task 1–6 技术成果进入重新验证；Task 7 推送仍需另行批准。"。追认记录轨迹：486465b 首次落盘本句 → c16a36e 将其 revert（HOLD 恢复）→ 用户在聊天正文再次直接发送同一追认句 → 本提交据以重新记录。58a7e36 判定无效的代理转述记录继续保留于提交历史。据此：D1=A（supersede `classic_texts_freeze.json`）、D2=A（移除 `bazi_kb.db` raw_bytes 钉定）、D3=Task 1–6 技术成果批准进入重新验证；Task 7 推送另行批准。计划文档：`docs/superpowers/plans/2026-08-31-phase8-marriage-capability-fix-or-waiver.md`（审批边界修订 `ed5a069`）。

## 1. 结论

- Phase 8 冻结域 v2 落盘并通过全部门禁：`110 passed`（85 phase8 + 25 closure）、`p8_reconcile.py` exit 0（七节全 ok）、closure `--check` exit 0、manifests `--check` exit 0（acceptance 冻结链未触碰）。
- 受测 HEAD：`f5578d4`（本 receipt 的父提交），工作树干净。
- CI run `33383577945` 的 4 个确定性失败（两作业一致：`4 failed, 2542 passed, 37 skipped`）对应三个根因，全部按批准方案处置。

## 2. 三个根因与处置（机械证据见计划文档 §0）

1. **迁移诱导冻结漂移**：`classic_texts_freeze.json` 钉 main 时代 blob（`frozen_commit a06a3373…`），C2 overlay 按闭包携带候选 blob，8 个钉定文件中 **3 个漂移**（pytest 首错即停使 CI 只报 1 个）。→ D1=A：以当前 HEAD 重生成冻结记录。
2. **路径未归一化 + 冻结后环境漂移**：`p8_kb_snapshot.py:187-188` 用 `str()` 写 OS 原生分隔符；冻结后 SQLite/FTS5 演进使重建行为漂移（6 个 gejue 查询翻转，CI=本机翻转集一致；主 worktree DB 至今仍为冻结字节证明从未重建）。→ TDD 修复 `.as_posix()`（新增守卫测试）+ 当前环境整体重生成。
3. **raw_bytes 钉可重建产物结构不可满足**：`bazi_kb.db` 被 gitignore、CI 每次重建，字节永不符合冻结记录。→ D2=A：从 manifest 移除该条目（28→27），语义完整性由 `TestKbSnapshot`/`TestKbEquivalence` 承担。

## 3. 新旧 SHA 对照（策略口径与 manifest 一致；old 取 `ed5a069` 树）

| 文件 | 策略 | old | new | 判定 |
|---|---|---|---|---|
| `docs/phase8/marriage-capability/classic_texts_freeze.json` | json_canonical | `0dd288d413a304ae136a6b7851d251949f2cb131885c8be9616d3cac10f3c3b0` | `bf9d2e64ed00990b6a44d6f84fe01b04134c7ea9b5399b9b71c6a06e5d61af16` | 变（frozen_commit `a06a3373…`→`4266fb65ad5ce4c990b39f3862630455f595246b`） |
| `docs/phase8/marriage-capability/kb_equivalence.json` | json_canonical | `0203cc742e6b93d4a47b4cbf7333bf6a6405f624bfeb08388e27d344aa4ebf09` | `d8975364ccc85a23730a753d66e54a866fa316f2c2030e923dd8309e8f265a38` | 变（路径 POSIX 化；summary 均 `total 59 / ok 59 / fallback 0`） |
| `docs/phase8/marriage-capability/kb_query_set.json` | json_canonical | `abf143f318acf1bef266a8213beb20b92a0a6d00d0cbbc177517f3d17cae6328` | 同 old | **不变**（字节稳定） |
| `docs/phase8/marriage-capability/kb_snapshot.db` | raw_bytes | `071504d297610b0cd42cd2b7dc2d4ababe29da2ce3931bf2d456b708464c1266` | `e06e35dcce74e53f5cced57b1529e7e815404752c8d005471d38a8a26c5d16e4` | 变（当前环境重生成） |
| `docs/phase8/marriage-capability/phase8_freeze_manifest.json` | （根清单，无自钉） | `6cf3ded3293e6203ecf13e3d2f384cbbe2d48f56957ec74b54d1ede46fae9529` | `2a910e62770f783d295544f62326e0604e38a0e91d16edc85d4da217526617ec` | 变（条目 28→27） |
| `docs/phase8/marriage-capability/provenance.json` | json_canonical | `92aa6c2497572c514d0a98c7375d913971479d7f3be1991edd34d937e4893b1a` | `de875678a33fd29ef791e27442a8dd39e10e0b11c5c7f32bc636b4b46177f1c6` | 变（manifest 派生投影） |
| `docs/phase8/marriage-capability/p8_kb_snapshot.py` | git_canonical_lf | `c855d83eb6a43f6bbdf544c224089b4878f261527e19b412e41aa157605b6a82` | `cab7ffc9a7e2c88ed9abc15e6877216bbfe91c49ef223319998cf758ab908a90` | 变（`.as_posix()` 两行） |
| `knowledge-base/bazi_kb.db` | raw_bytes（**已移除**） | `115bace4efa66fd82455dc4e8c79610d7f6c751585e47769583caaf1ab7fb83e` | — | 条目删除；该文件不入库、可重建，字节钉定在任何重建后必然失效（计划 §0.4） |

**classic_texts_freeze 8 项 blob 对照**（HEAD vs main `3d3b41cf`）：漂移 3 项——`qiongtongbaojian/all_rules.json` `7325c350…`→`dc10d574…`、`qiongtongbaojian/quarantine_rules.jsonl` `fef8051c…`→`e8c7c13e…`、`sanmingtonghui/all_rules.json` `74eaaa09…`→`97716ca0…`；不变 5 项（ditiansui/all `df67639d…`、ditiansui/quar `e69de29b…`、sanmingtonghui/quar `e69de29b…`、zipingzhenquan/all `6ccf684b…`、zipingzhenquan/quar `e69de29b…`）。

## 4. 执行链与计划外适配（如实披露）

提交链：`45ce7f5`（计划）→ `ed5a069`（审批边界修订）→ `4266fb6`（Task 1 路径归一化 + 守卫测试）→ `4c694ee`（touch-binding 期望 11→12 + closure 测试断言同步 + 顺带收尾陈旧 `classic_texts_freeze.json` 的暂存删除）→ `cb30cab`（Phase 8 v2 工件）→ `c12c7f1`（closure 产物按 phase8 树再生成）→ `f5578d4`（infra blob 重记录）→ 本 receipt。

计划外适配两笔，均为再生成门禁按设计拦截后的最小处置：

1. **closure touch-binding 期望 11→12**：本计划文档自身在验证命令中携带完整 C2 SHA（与 2026-08-23 tooling 计划文档同性质），recompute 扫描得 12 个 binding 文件，S5 时代常量仍为 11；`generate`/`--check` 依设计拒绝不一致状态。同步更新生成器常量与测试断言；钉树与全部树级门禁不变（deletions 3686、short-prefix-only 0、tooling bytes 1594169、pin `ed5493a`）。
2. **closure 产物按 phase8 树再生成 + infra blob 重记录**：closure 按设计在 HEAD 记录 infra 源文件 blob（"artifacts are regenerated after the code commit"），因此须在代码提交定稿后（含 amend）再生成一次；合并回集成分支时该处 closure 需再次按合并树再生成。

## 5. 环境记录

- Windows；Python 3.14.6（仓库 venv）；sqlite 3.50.4；KB 输入 `knowledge-base/gejue.json` 自 `c6f3c57`（2026-05-28）未变。

## 6. 可复算

```powershell
python -m pytest tests/test_phase8_marriage_capability.py tests/test_generate_acceptance_integration_closure.py -q   # 110 passed
python docs/phase8/marriage-capability/p8_reconcile.py                                                               # exit 0，七节全 ok
python scripts/generate_acceptance_integration_closure.py --check --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 --base-commit 3d3b41cf65af487b03ca5233a109fee14191b88c --no-legacy --tooling-pin-commit ed5493a94d0268b88f2dca448f963880e7cc1ad5   # exit 0
python scripts/generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid 98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7                                            # exit 0
```

---

```json
{
  "receipt_schema": "phase8_freeze_v2_superseding_receipt_v1",
  "date": "2026-09-01",
  "branch": "task/phase8-marriage-capability",
  "tested_head_commit": "f5578d4",
  "based_on": "integration/classic-texts-clean @ 1f266bea84421eae1c20db240ef23beadd52814f",
  "approval": {"status": "RATIFIED", "ratified_at": "2026-09-01", "ratification_channel": "user direct first-person sentence in the chat body, re-sent after revert c16a36e", "ratification_sentence": "我追认并批准 Phase 8 计划的 D1=A、D2=A、D3，批准现有 Task 1–6 技术成果进入重新验证；Task 7 推送仍需另行批准。", "history": "first recorded in 486465b, reverted by c16a36e, re-recorded here after the user re-sent the identical sentence; the invalid agent-paraphrase record (58a7e36) remains in history", "d1": "A", "d2": "A", "d3": "tasks 1-6 technical output ratified for re-verification", "task7_push": "separate approval required"},
  "ci_evidence_input": {"run_id": "33383577945", "two_jobs_identical": "4 failed, 2542 passed, 37 skipped", "deterministic": true},
  "sha_supersession": {
    "old_base_commit": "ed5a069",
    "classic_texts_freeze.json": {"old": "0dd288d413a304ae136a6b7851d251949f2cb131885c8be9616d3cac10f3c3b0", "new": "bf9d2e64ed00990b6a44d6f84fe01b04134c7ea9b5399b9b71c6a06e5d61af16", "strategy": "json_canonical", "frozen_commit": {"old": "a06a3373a9aca926c104534dd0a441e9af0a6fea", "new": "4266fb65ad5ce4c990b39f3862630455f595246b"}},
    "kb_equivalence.json": {"old": "0203cc742e6b93d4a47b4cbf7333bf6a6405f624bfeb08388e27d344aa4ebf09", "new": "d8975364ccc85a23730a753d66e54a866fa316f2c2030e923dd8309e8f265a38", "strategy": "json_canonical", "git_blob": {"old": "afb141d49b3aef3a0bf4b6e5b1bdd2f996562c14", "new": "0c404200b60f8b2fb1cb91fc3f98193c8eed331f"}},
    "kb_query_set.json": {"old": "abf143f318acf1bef266a8213beb20b92a0a6d00d0cbbc177517f3d17cae6328", "new": "abf143f318acf1bef266a8213beb20b92a0a6d00d0cbbc177517f3d17cae6328", "strategy": "json_canonical", "changed": false},
    "kb_snapshot.db": {"old": "071504d297610b0cd42cd2b7dc2d4ababe29da2ce3931bf2d456b708464c1266", "new": "e06e35dcce74e53f5cced57b1529e7e815404752c8d005471d38a8a26c5d16e4", "strategy": "raw_bytes"},
    "phase8_freeze_manifest.json": {"old": "6cf3ded3293e6203ecf13e3d2f384cbbe2d48f56957ec74b54d1ede46fae9529", "new": "2a910e62770f783d295544f62326e0604e38a0e91d16edc85d4da217526617ec", "entries": {"old": 28, "new": 27}},
    "provenance.json": {"old": "92aa6c2497572c514d0a98c7375d913971479d7f3be1991edd34d937e4893b1a", "new": "de875678a33fd29ef791e27442a8dd39e10e0b11c5c7f32bc636b4b46177f1c6", "strategy": "json_canonical"},
    "p8_kb_snapshot.py": {"old": "c855d83eb6a43f6bbdf544c224089b4878f261527e19b412e41aa157605b6a82", "new": "cab7ffc9a7e2c88ed9abc15e6877216bbfe91c49ef223319998cf758ab908a90", "strategy": "git_canonical_lf"},
    "knowledge-base/bazi_kb.db": {"old": "115bace4efa66fd82455dc4e8c79610d7f6c751585e47769583caaf1ab7fb83e", "new": null, "strategy": "raw_bytes", "removed": true, "rationale": "gitignored rebuildable artifact; raw-bytes pin is unsatisfiable after any rebuild (plan section 0.4); semantic integrity gated by TestKbSnapshot and TestKbEquivalence"}
  },
  "classic_texts_blob_drift": {
    "changed": [
      {"path": "knowledge_base/classic_texts/qiongtongbaojian/all_rules.json", "old": "7325c350fe61a9d8fbe225009c045cd3343c557d", "new": "dc10d5749821e930a4ccb4af99ed25866094d0c5"},
      {"path": "knowledge_base/classic_texts/qiongtongbaojian/quarantine_rules.jsonl", "old": "fef8051c76d4f76c4156934abc70df354ca8f3c2", "new": "e8c7c13e1152206ef406fd6fdfaeebe53a34bfca"},
      {"path": "knowledge_base/classic_texts/sanmingtonghui/all_rules.json", "old": "74eaaa09b5a7ba8b53d9d83055aa6e1eb454b48e", "new": "97716ca0455e59167944569380b5fb8c0983ba46"}
    ],
    "unchanged": ["ditiansui/all_rules.json=df67639d2ffbc1904f7249e1bf6212e0799ff2d8", "ditiansui/quarantine_rules.jsonl=e69de29bb2d1d6434b8b29ae775ad8c2e48c5391", "sanmingtonghui/quarantine_rules.jsonl=e69de29bb2d1d6434b8b29ae775ad8c2e48c5391", "zipingzhenquan/all_rules.json=6ccf684bc1bc393050e5b2d7c95884c324648e42", "zipingzhenquan/quarantine_rules.jsonl=e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"]
  },
  "verification": {
    "pytest": "110 passed (85 phase8 + 25 closure)",
    "p8_reconcile_exit": 0,
    "closure_check_exit": 0,
    "manifests_check_exit": 0,
    "worktree_clean": true
  },
  "environment": {"os": "Windows", "python": "3.14.6", "sqlite": "3.50.4", "kb_input_gejue_unchanged_since": "c6f3c57 2026-05-28"},
  "out_of_scope_deviations": [
    "closure touch-binding expectation 11 -> 12 (generator constant + test assertion): the phase8 plan doc legitimately carries the full C2 SHA in its verification command; recomputed scan found 12 binding files",
    "closure artifacts regenerated for the phase8 tree and infra blob re-recorded after the code-commit amend, per the generator's designed regeneration order"
  ],
  "acceptance_freeze_chain_untouched": true
}
```
