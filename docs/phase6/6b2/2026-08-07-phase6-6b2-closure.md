# Phase 6 6B2 实验关闭声明

**日期：** 2026-08-07
**状态：** 已关闭（CLOSED）
**关闭提交：** 本文件所在 commit
**前置证据：** `docs/phase6/6b2/evidence/phase6-6b2-v4flash-nt-20260805-r2/`（SHA 已锁定，不可修改）

## 1. 关闭决定

Phase 6 6B2（DeepSeek-V4-Flash non-thinking 双管线实验）经 dev 阶段实测与 2025 零 API 错误归因，判定为 **ROLLBACK**。本声明正式关闭 6B2 实验链。

## 2. 冻结状态

以下状态自本声明起冻结，未经新设计文档批准不得变更：

| 项 | 冻结值 |
|---|---|
| verdict | `ROLLBACK` |
| protocol | `single`（不开放 dual 为晋级协议） |
| reuse 阶段 | 不开放 |
| final_2023 阶段 | 不开放 |
| B1-c 角色 | 仅 advisory，不参与任何 gate |
| 原始大型归档 | 不入 Git（`runs/` 目录保持 untracked） |
| evidence pack SHA | 锁定，不可修改 |

## 3. 证据基础

关闭决策基于以下已归档证据（commit `acb63a1`）：

### 3.1 dev 阶段实测结果

- **2025 净变化**：+7/120（+5.83pp）
- **rescue/regression**：17 rescue / 10 regression
- **描述性配对二项检验**：p=0.2478（不显著）
- **信号集中度**：净增益最高的 3 道题合计贡献全部 +7，不能视为稳定全局改进

### 3.2 按域净变化

| domain | Δ | 解读 |
|---|---|---|
| annual_fortune | -16.67% | 退化（时间定位域） |
| career | -7.41% | 退化（时间定位域） |
| family | +25.00% | rescue（非时间域，紫微臂贡献） |
| relationship | +19.05% | rescue（非时间域，紫微臂贡献） |
| health | 0.00% | 无变化 |
| study | +66.67% | rescue（n=3，样本过小） |
| unknown | +2.38% | 微弱 |

### 3.3 结论

- 双管线不是稳定的全局改进
- 退化集中在时间定位域（annual_fortune / career）
- rescue 集中在非时间域（family / relationship），来自紫微臂
- 净增益高度集中，不能推翻整体 ROLLBACK
- 后续不应继续扩大 judge/双臂调用预算

## 4. 可复用设施

ROLLBACK 只否定"双管线晋级"，不否定以下可复用设施（已在 `codex/6b2-v4flash` 分支提交）：

| 设施 | commit | 说明 |
|---|---|---|
| 冻结协议门禁 | `6ce815d` | `_validate_frozen_protocol` |
| non-thinking API payload | `c04a8b8` | `thinking: disabled` |
| Runner thinking-mode 传递 | `802e59b` | `--thinking-mode {disabled}` |
| Slice/manifest/status 同源 | `093163f` | thinking mode 贯穿 |
| run context 与安全恢复 | `b4fe1a0` | fresh/resume/拒收 |
| archive/receipt/gate | `344d993` | 跨阶段证据链 |
| 报告与 B1-c advisory | `8b2d7fc` | B1-c 不参与 gate |
| fake runner 三阶段闭环 | `fb6a9f8` | dev -> reuse -> final_2023 |
| B1-c SHA 归一化 | `2eec30a` | CRLF/LF 不敏感 |
| slim rollback evidence | `acb63a1` | 精简证据包 |

这些设施在 6D v1 中可复用（如冻结协议门禁、receipt 契约模式），但 6D 是独立实验链，不延续 6B2 的 schedule/gate/receipt。

## 5. 6B2 与 6D 的关系

| 维度 | 6B2 | 6D v1 |
|---|---|---|
| 协议 | dual（已 ROLLBACK） | single |
| 实验臂 | b1a_prime + dual | b1a_time_off + b1a_time_on |
| orchestrator | `phase6_6b2_orchestrator.py`（归档） | `phase6_6d_orchestrator.py`（新建） |
| gate | `dual_merged_acc >= 0.325` | paired Δ gate |
| sealed | `phase6_6b2_sealed_workflow.py`（归档） | 不需要 |
| reuse/final | 已关闭 | 无（只有 dev） |
| 证据 | `evidence/phase6-6b2-v4flash-nt-20260805-r2/`（锁定） | 独立新目录 |

**6D 是后续独立实验，不是 6B2 的延续。** 6D 不 resume 任何 6B2 run，不共享 6B2 的 schedule/gate/receipt。

## 6. 后续路径

1. **6D v1**：确定性时间上下文注入（设计已放行，spec v6.1 commit `a2bb6e0`）
   - 目标：解决 annual_fortune / career 退化的根因（时间上下文不足）
   - 范围：八字命局 × 大运 × 目标流年，不含紫微动态流年
   - 评估：两阶段（零 API 离线门 + 真实 paired dev）
2. **6C**：GroundedClaim Verifier（后置）
   - 启动条件：6D v1 评估显示确定性注入未改善退化，且逐题复核证明主要错误是事实矛盾
3. **6D v2**：动态紫微流年（后置）
   - 启动条件：6D v1 显示正向收益，且 family/relationship rescue 在排除紫微臂后消失

## 7. 不可逆性

本关闭声明一旦提交：
- 6B2 verdict 不可从 ROLLBACK 改为 PROMOTE
- 6B2 protocol 不可从 single 改为 dual
- 6B2 reuse/final 不可重新开放
- 6B2 evidence pack SHA 不可修改
- 6B2 原始归档不可入 Git

如需重新评估双管线，必须新建独立实验（如 6B3），不得复活 6B2。
