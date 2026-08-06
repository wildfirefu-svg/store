# Task 9 Scope Expansion Decision Record

**Date:** 2026-08-05
**Status:** Confirmed
**Related Plan:** docs/superpowers/plans/2026-08-05-phase6-6b2-v4-flash-nonthinking.md Task 9

## 1. Deviation

Task 9 Step 5 (Git scope) does not list scripts/phase6_6b1_orchestrator.py or scripts/phase6_6b1_smoke.py. Two commits were added during Task 9 execution to make Step 3 (broad Phase 6 regression) reproducible:

| Commit | File | Reason |
|---|---|---|
| c02ba46 | scripts/phase6_6b1_orchestrator.py | tests/test_phase6_6b1.py imports this module; file never entered Git, causing collection error |
| a931f9d | scripts/phase6_6b1_smoke.py | tests/test_phase6_6b1.py imports smoke_gate; file never entered Git, causing 3 failures |

## 2. Why Necessary

- Plan Task 9 Step 3 requires running Get-ChildItem tests -Filter test_phase6_*.py full regression
- test_phase6_6b1.py is a 6B1 phase test (last modified 1fd61ed), predating 6B2
- The modules under test existed in main working dir but were never git add-ed
- Without these files, broad regression cannot pass the no-new-failures condition

## 3. Impact

- Code integrity: both files copied verbatim from main working dir, SHA-256 identical
- 6B2 scope: these are 6B1 modules, no code dependency on 6B2 protocol layer
- Test result: broad regression went from 494 passed / 107 failed / 3 error to 713 passed / 0 failed
- Git history: commits prefixed fix(6b1): to distinguish from 6B2 feat(6b2): commits

## 4. Decision

Accept these two commits as necessary Task 9 scope expansion. They do not modify 6B2 protocol code; they only fill missing 6B1 test dependencies so broad regression is reproducible in worktrees.

## 5. Follow-up

Main branch should also track these two files to prevent the same issue in future worktrees. This is outside the 6B2 plan scope and requires independent action.
