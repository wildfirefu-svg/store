# POSIX 进程清理验证 Receipt（Review E，已受跟踪）

> 日期：2026-08-29 ｜ 分支：`acceptance/task1` ｜ Review：E（CLI 子进程超时 / 进程树回收 / 失败路径泄漏）
> 本文件是**受 git 跟踪的持久证据**：临时验证分支已删除、GitHub Actions 日志会过期，run/head/blob 标识固化于此以便日后追溯。

## 1. 结论

- **Review E 判定：进程清理修复 PASS**（`25fe4c4` plan / `430191e` tests）。
- **整体分支仍不可合并**：CI run 总结论是 **failure**，不是完整全绿；失败仅来自被刻意排除的冻结 payload。
- 机械确认范围：**Windows 与 Ubuntu 两个平台上，CLI 子进程超时、进程树回收、失败路径无泄漏均通过。**

## 2. CI 证据（ubuntu-latest，权威门禁同平台）

| 项 | 值 |
|---|---|
| GitHub run | https://github.com/wildfirefu-svg/store/actions/runs/33232643357 |
| run_id | `33232643357` |
| runner / job | `ubuntu-latest` / `posix-review` |
| 命令 | `python -m pytest tests/test_classic_acceptance_review.py -v --tb=short --timeout=120 --ignore=tests/test_e2e.py` |
| workflow blob | `845f6ac60fbefcceb2557ededbe602c32118e803` |
| 总结论 | **failure**（4 failed / 54 passed / 4 skipped / 5 errors，27.44s） |

总结论 failure 的唯一原因：缺 `docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json`（一次性分支刻意排除的冻结 payload）。**9 个 fail/error 全部是这个 FileNotFoundError，与进程超时/回收无关。**

### 三个 POSIX 专属测试：实际执行且全部 PASSED（非 skipped）

| 测试 | ubuntu-latest | 覆盖 |
|---|---|---|
| `test_run_cli_result_reports_uncertain_cleanup_when_killpg_fails` | **PASSED** | os.killpg PermissionError → cleanup_ok=False；finally 回收 |
| `test_run_cli_result_reaps_descendant_after_group_leader_exits` | **PASSED** | 组长退出孙进程仍存活；killpg(已知 pgid=proc.pid) 回收，cleanup_ok=True |
| `test_cleanup_finally_reaps_when_read_json_fails` | **PASSED** | 注入 read_json OSError + killpg PermissionError；finally 凭已知根 pid 回收，不依赖 pids JSON |

Windows 专属测试在 ubuntu 上正确 SKIPPED：`..._when_taskkill_fails[×2]`、`..._read_json_fails_windows`。

## 3. 代码同一性证明（CI 跑的就是 Review E 代码）

一次性验证分支 `ci/acceptance-posix-probe`（head `0abd912cedf98065632ccbf8bc66813e6284652b`）从 `origin/main @ 3d3b41cf` 长出；受测依赖集 5 个文件的 git blob SHA 在 `0abd912` 与分支 HEAD `430191e` 上**逐字节一致**：

| 文件 | blob SHA（0abd912 == 430191e） |
|---|---|
| `tests/test_classic_acceptance_review.py` | `09760df093604a67adc7023f26edceffb272c0bd` |
| `tests/classic_acceptance_fixtures.py` | `e2d1efb8d174a7358e9f6f9eef43e35430049fc0` |
| `scripts/classic_acceptance_common.py` | `72e275b65a7c8ea5bd1606c6b5ee1f836e72c498` |
| `scripts/classic_acceptance_sampling.py` | `703b44cf5d47354d3dbf9f670d46c5fa0d6be20f` |
| `scripts/classic_acceptance_review.py` | `9e91a8e4a856e92f86311db4f5b9b486fadf7546` |

非破坏性：该分支历史里 `QUALITY_REPORT.json` 始终是 origin 的 6,381 字节版本（不引入 337.6MB blob），未改 `acceptance/task1` 历史，未碰冻结 tag。临时远端分支、本地分支、本地 worktree 均已删除。临时提交现已由证据 tag `ACCEPTANCE_POSIX_PROBE_EVIDENCE_V1`（tag 对象 `8d2938e21ca6758011b2e31ae2919e2f42f5389b`，已推送 origin）锚定，git GC 后仍可复算。

## 4. Windows 本地回归

- 四文件全量：`python -m pytest tests/test_classic_acceptance_review.py tests/test_classic_acceptance_sampling.py tests/test_classic_acceptance_e2e.py tests/test_generate_acceptance_manifests.py --timeout=120` → **135 passed, 3 skipped in 718.26s**（3 个 skip 正是上述 POSIX 专属测试）。
- 聚焦清理：**6 passed, 3 skipped**；ruff 干净；`scripts/verify_smoke.py` exit 0；`git merge-tree main HEAD` exit 0。

## 5. 不属 Review E 的剩余合并阻断

1. 337.6MB `knowledge_base/classic_texts/QUALITY_REPORT.json` 未推送历史 + 重冻结方案。
2. 缺冻结 payload（chapter-identity manifest）导致的正式 CI 失败。
3. Phase 8 历史红灯（frozen-blob 漂移）。

## 6. 可复算

- Linux：`pip install pytest pytest-timeout` 后 `python -m pytest tests/test_classic_acceptance_review.py -v --timeout=120 -k "killpg_fails or group_leader_exits or read_json_fails"`（windows-only 变体显示 SKIPPED）。
- Windows：`python -m pytest tests/test_classic_acceptance_review.py -v --timeout=120`。
- 证据复原：`git show ACCEPTANCE_POSIX_PROBE_EVIDENCE_V1:.github/workflows/posix-probe.yml`（临时 workflow，blob `845f6ac60fbefcceb2557ededbe602c32118e803`）。

---

```json
{
  "receipt_schema": "posix_cleanup_verification_receipt_v1",
  "date": "2026-08-29",
  "review": "Review E (process timeout / process-tree cleanup / failure-path leak)",
  "review_verdict": "PASS for the process-cleanup fix; branch as a whole NOT mergeable",
  "branch": {
    "name": "acceptance/task1",
    "tested_head_commit": "430191e47be78d2ee15a232f75fc803243e11f09",
    "plan_commit": "25fe4c494134cc1b7bb0d348e48d49ed1294efda",
    "tests_commit": "430191e47be78d2ee15a232f75fc803243e11f09"
  },
  "ci_run": {
    "github_repo": "wildfirefu-svg/store",
    "url": "https://github.com/wildfirefu-svg/store/actions/runs/33232643357",
    "run_id": "33232643357",
    "runner": "ubuntu-latest",
    "job": "posix-review",
    "workflow_file": ".github/workflows/posix-probe.yml (throwaway, deleted with the branch; recoverable via git show ACCEPTANCE_POSIX_PROBE_EVIDENCE_V1:.github/workflows/posix-probe.yml)",
    "workflow_blob_sha": "845f6ac60fbefcceb2557ededbe602c32118e803",
    "command": "python -m pytest tests/test_classic_acceptance_review.py -v --tb=short --timeout=120 --ignore=tests/test_e2e.py",
    "overall_conclusion": "failure",
    "overall_conclusion_note": "NOT a full CI green. The failure is solely the missing frozen payload docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json which was intentionally excluded from the throwaway branch.",
    "summary": {
      "failed": 4,
      "passed": 54,
      "skipped": 4,
      "errors": 5
    }
  },
  "throwaway_probe_branch": {
    "name": "ci/acceptance-posix-probe",
    "base": "origin/main @ 3d3b41cf65af487b03ca5233a109fee14191b88c",
    "head_commit": "0abd912cedf98065632ccbf8bc66813e6284652b",
    "evidence_tag": "ACCEPTANCE_POSIX_PROBE_EVIDENCE_V1",
    "evidence_tag_object_sha": "8d2938e21ca6758011b2e31ae2919e2f42f5389b",
    "evidence_tag_pushed_to_origin": true,
    "deleted_remote": true,
    "deleted_local_branch": true,
    "deleted_local_worktree": true,
    "note": "Grew from origin/main (where QUALITY_REPORT.json is the 6381-byte origin version); history therefore never contained the 337.6 MB blob, never touched acceptance/task1 history, and never touched the freeze tag."
  },
  "code_identity_proof": {
    "note": "git blob SHAs (sha1) are byte-for-byte identical between the throwaway CI commit 0abd912 and the branch HEAD 430191e, proving ubuntu-latest executed exactly the Review E code. The probe commit is anchored by the annotated tag ACCEPTANCE_POSIX_PROBE_EVIDENCE_V1 (tag object 8d2938e21ca6758011b2e31ae2919e2f42f5389b, pushed to origin), so this proof remains recomputable after git GC.",
    "blobs": {
      "tests/test_classic_acceptance_review.py": "09760df093604a67adc7023f26edceffb272c0bd",
      "tests/classic_acceptance_fixtures.py": "e2d1efb8d174a7358e9f6f9eef43e35430049fc0",
      "scripts/classic_acceptance_common.py": "72e275b65a7c8ea5bd1606c6b5ee1f836e72c498",
      "scripts/classic_acceptance_sampling.py": "703b44cf5d47354d3dbf9f670d46c5fa0d6be20f",
      "scripts/classic_acceptance_review.py": "9e91a8e4a856e92f86311db4f5b9b486fadf7546"
    }
  },
  "posix_tests_executed_on_ubuntu": [
    {
      "test": "test_run_cli_result_reports_uncertain_cleanup_when_killpg_fails",
      "platform": "posix-only (skipif win32)",
      "result_ubuntu": "PASSED",
      "covers": "os.killpg PermissionError -> cleanup_ok=False; finally reaps the tree"
    },
    {
      "test": "test_run_cli_result_reaps_descendant_after_group_leader_exits",
      "platform": "posix-only (skipif win32)",
      "result_ubuntu": "PASSED",
      "covers": "group leader exits while grandchild survives; killpg(known pgid=proc.pid) reaps descendant; cleanup_ok=True"
    },
    {
      "test": "test_cleanup_finally_reaps_when_read_json_fails",
      "platform": "posix-only (skipif win32)",
      "result_ubuntu": "PASSED",
      "covers": "injected read_json OSError + killpg PermissionError; finally reaps via known root pid independent of the pids JSON; no leak"
    },
    {
      "test": "test_run_cli_result_reports_uncertain_cleanup_when_taskkill_fails[taskkill-times-out]",
      "platform": "windows-only (skipif not win32)",
      "result_ubuntu": "SKIPPED"
    },
    {
      "test": "test_run_cli_result_reports_uncertain_cleanup_when_taskkill_fails[taskkill-nonzero-exit]",
      "platform": "windows-only (skipif not win32)",
      "result_ubuntu": "SKIPPED"
    },
    {
      "test": "test_cleanup_finally_reaps_when_read_json_fails_windows",
      "platform": "windows-only (skipif not win32)",
      "result_ubuntu": "SKIPPED"
    }
  ],
  "windows_local_regression": {
    "command": "python -m pytest tests/test_classic_acceptance_review.py tests/test_classic_acceptance_sampling.py tests/test_classic_acceptance_e2e.py tests/test_generate_acceptance_manifests.py --timeout=120",
    "result": "135 passed, 3 skipped in 718.26s",
    "note": "The 3 skips on Windows are exactly the three POSIX-only tests above.",
    "focused_cleanup_run": "6 passed, 3 skipped",
    "ruff": "clean",
    "smoke": "scripts/verify_smoke.py exit 0",
    "merge_tree": "git merge-tree main HEAD exit 0"
  },
  "ci_failures_not_in_scope": {
    "root_cause": "FileNotFoundError: docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json",
    "failed": [
      "test_validate_primary_cli_rejects_nonfrozen_chapter_manifest",
      "test_validate_second_cli_rejects_nonfrozen_chapter_manifest",
      "test_validate_arbitration_cli_rejects_nonfrozen_chapter_manifest",
      "test_decide_production_report_data_source"
    ],
    "errors": [
      "test_real_packet",
      "test_finalize_production_happy_path",
      "test_finalize_production_rejects_stray_second",
      "test_decide_production_rejects_tampered_source_chapter",
      "test_finalize_production_no_overwrite_leaves_frozen_package"
    ],
    "note": "All 4 failures + 5 errors are the missing frozen chapter-identity payload (large-file / re-freeze track), unrelated to subprocess timeout or process-tree cleanup."
  },
  "remaining_merge_blockers_outside_review_e": [
    "337.6 MB knowledge_base/classic_texts/QUALITY_REPORT.json in unpushed history + re-freeze decision.",
    "Official CI failure caused by the missing frozen payload (chapter-identity manifest).",
    "Phase 8 historical red (frozen-blob drift)."
  ],
  "reproduction": {
    "posix": "On any Linux host with python3.11: pip install pytest pytest-timeout; python -m pytest tests/test_classic_acceptance_review.py -v --timeout=120 -k 'killpg_fails or group_leader_exits or read_json_fails' (the windows-only variants report SKIPPED).",
    "windows": "python -m pytest tests/test_classic_acceptance_review.py -v --timeout=120"
  }
}
```
