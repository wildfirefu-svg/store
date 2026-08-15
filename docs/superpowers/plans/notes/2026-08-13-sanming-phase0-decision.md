# 阶段 0 门禁决策（2026-08-13 Sanming 完成计划）

- **日期**：2026-08-13
- **计划**：`docs/superpowers/plans/2026-08-13-classic-distillation-sanming-completion.md`
- **决策**：**分支 B（正式改测试/门禁契约）**
- **决策人**：审核方（本会话用户确认）

## 依据

本计划的核心交付是评测闭环与门禁契约的硬化，全部落在「代码行为 + 测试/门禁契约」层面：

- GenerationIndex 40/64 幂等契约（首条 `previous_index_sha256=None`、`genesis_commit` 40-hex）；
- completed 幂等 entry 精确匹配 `(batch_id, completed_receipt_sha256, genesis_commit)`；
- cleanup fail-closed：`_retry_pending_cleanup` 显式返回 `noop/cleaned/blocked`，`blocked` 映射为
  `completed_cleanup_blocked`（不吞身份校验错误、不进入 `completed_idempotent`）；
- progress 逐记录映射（mapped/conflicts/unmappable + canonical SHA，1727 条守恒）；
- 备份目录内容指纹冻结进 completed receipt，删除目标与指纹取自已认证 receipt 冻结值。

以上均属分支 B（正式改测试/门禁契约）范畴。本计划**不涉及** `bazi_kb.db` 快照/重建契约，
无需先修分支 A，因此选定分支 B。

## 落地

- 随本计划文档一并提交（同一 commit）。
- 干净 worktree：`G:\project\agent-sanming`，分支 `codex/sanming-completion`。
