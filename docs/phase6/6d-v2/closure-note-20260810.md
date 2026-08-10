# 6D-v2 收尾说明（closure note）

**日期：** 2026-08-10
**run_id：** `phase6-6d-v2-20260810-r1`
**归档：** `docs/phase6/6d-v2/phase6-6d-v2-20260810-r1-6d-dev-2026-08-07-deepseek-deepseek-v4-flash-5368d89567dd/`
**正式 verdict：** `NON_INFERIOR`（paired_delta = +3.23pp，min_case_delta = -1/3）

本说明记录外部证据审计（2026-08-10）要求的两处报告措辞修正与一项单位澄清。归档内的 `report.md` / `audit_index.json` / `dev_gate.json` 已被哈希锁定，不修改；修正以本文件为准。

## 1. 措辞修正：跨实验比较只构成方向性支持

on_limited（22/93 = 23.66%）> 完整 on（18/93 = 19.35%，来自 6D v1 历史运行）满足预注册的独立比较。但完整 on 并非同期第三臂，存在跨实验时间环境差异（spec §4.1.1 已声明该风险，§5.3 注明「需单独验证」）。因此：

> 跨实验结果为「关系带偏」假设提供**方向性支持**，不构成因果确证。

## 2. 单位澄清：attempt 级与题级聚合

- **93 个 paired attempts（重复评测单元）**：10 胜、7 负、76 平，净 +3 个正确单元（paired_delta = 3/93 = +3.23pp）
- **31 道题聚合**：8 题净改善、7 题净退化、16 题不变

此前口头总结中的「改善 10 / 退化 7」是 paired attempts 口径，不是题数。

## 3. 协议决策

按 spec §4.5 决策语义执行：verdict `NON_INFERIOR` → **6D 时间注入方向关闭，启动 6C**。6D 线三臂证据已闭合：完整注入 on 弱负向（-1.08pp），限制性注入 on_limited 正向但未达 PROMOTE 阈值（+3.23pp < +5pp，N=31 下为噪声量级信号）。

## 4. 证据完整性备注

- `.gitignore:75`（`docs/phase6/*/runs/`）使 runs 工作区默认不入库；为保证全新 clone 可重放四层 provenance 校验，已强制入库 5 个小型运行元数据：`run_context.json`、`run_manifest.json`、`dev/report.md`、`dev/summary.json`、`dev/budget_ledger.json`。runs/ 下的 slice 原始目录与归档内容重复，不入库。
- 归档 `audit_index.json` / `merged_details.jsonl` / `dev_gate.json` 的哈希链在提交时完整；若未来检出环境的行尾归一化（CRLF/LF）导致字节级 SHA 漂移，以 slice 级 `details.jsonl` 重建数据为准（6D v1 已有同类先例，见 v2 计划 P1-5 记录）。
