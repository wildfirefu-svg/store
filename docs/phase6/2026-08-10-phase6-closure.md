# Phase 6 总收尾报告：准确率候选路线全部闭合

**日期：** 2026-08-10
**状态：** Phase 6 关闭
**最终评测协议：** single B1-a′（`baziqa_xjz_reasoned` / `direct_choice` / deepseek-v4-flash non-thinking / T=0）——这是**经过候选路线门禁后的最终操作协议**，不是已证明的全局最优协议。

---

## 1. 各路线终态

| 路线 | 假设 | 终态 | 关键证据 |
|---|---|---|---|
| 6A1 严格 ≥3/5 投票 | 投票提升准确率 | **ROLLBACK** | Δ1 = −3.33pp（要求 ≥+3pp），Δ2 = −10.0pp，unresolved 25%；2021 复核未打开。归档 `docs/phase6/6a1-2024-001/` |
| 6B1 紫微信号探针 | 本命紫微上下文有可利用信号 | 有信号 → 触发 6B2 | 归档 `docs/phase6/6b1/`、`docs/phase6/6b1d/` |
| 6B2 双管线 + judge | 双管线优于同期单管线且过绝对门槛 | **ROLLBACK** | Δ_dev = +2.92pp（要求 ≥+4pp），dual 31.67%（门槛 32.5%），judge 触发率 55.83%；protocol 保持 single。归档 `docs/phase6/6b2/phase6-6b2-v4flash-nt-20260805-r2-6b2-dev-2026-07-17-deepseek-deepseek-v4-flash-642ba3da19d5/` |
| 6D v1 完整时间注入 | 确定性时间上下文提升时间定位题 | **NON_INFERIOR**（弱负向） | paired 净 −1（off 20.43% vs on 19.35%）。归档 `docs/phase6/6d/` |
| 6D-v2 限制性时间注入 | 省略干支关系可逆转退化 | **NON_INFERIOR / CLOSED** | paired_delta +3.23pp（< +5pp PROMOTE 阈值，N=31 噪声量级），min_case_delta −1/3。归档 `docs/phase6/6d-v2/`（含 closure note） |
| 6C claim verifier | 事实矛盾富集于错题 | **PRECONDITION_NOT_MET / NOT_STARTED** | 行级矛盾率 15.79% vs 14.49%（风险比 1.09，Fisher p=1.0）；未达前提筛选门槛。归档 `docs/phase6/6c-premise/` |

措辞说明（按外部审计修正）：6C 的前提筛选为探索性分析（门槛为本次设定，非预注册）；其结果**不构成对广义因果假设的统计否定**，仅表明在当前检测覆盖范围内无富集信号、不达启动门槛。

## 2. 结论

四条候选路线（投票、紫微双管线、时间注入、声明校验）均未能通过各自门禁。Phase 6 的产出不是准确率提升，而是：

1. **硬化的评测设施**：fail-closed resume manifest、预算账本、原子归档、四层 provenance、AB/BA 调度、attempt key 幂等续跑；
2. **完整的负证据链**：每条路线都有可复算的归档与 receipt，排除的假设不再占用后续预算；
3. **最终操作协议** single B1-a′：在所有候选路线门禁后的保留协议。

## 3. 转入产品 backlog（不属于 Phase 6）

- **报告文本事实一致性 verifier**：以 6C 前提分析的声明抽取/校验链路为起点，面向用户报告输出质量守门。需另立目标与指标（如报告事实错误率、用户可见矛盾数），不承诺准确率收益。

## 4. 证据索引

- 6A1：`docs/phase6/6a1-2024-001/`（report / manifest / audit_index）
- 6B1/6B1D：`docs/phase6/6b1/`、`docs/phase6/6b1d/`
- 6B2：`docs/phase6/6b2/`（含 2026-08-07-phase6-6b2-closure.md）
- 6D v1：`docs/phase6/6d/`（run + 归档 + 根因分析）
- 6D-v2：`docs/phase6/6d-v2/`（归档 + closure-note-20260810.md）
- 6C 前提：`docs/phase6/6c-premise/`（脚本 + JSON + README，含 SHA 溯源）
- 设计与计划：`docs/superpowers/specs/`、`docs/superpowers/plans/`（2026-07-17 主设计 v 系列及各阶段专项）
