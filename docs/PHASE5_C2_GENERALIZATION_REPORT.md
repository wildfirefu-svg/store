# Phase 5 C2 独立泛化验证报告

> Run ID: `phase5-c2-generalization-v1`
> 执行日期: 2026-07-15
> 分支: `phase5-c2-generalization` (commit `d1cd722`)
> 固定口径: provider=deepseek, model=deepseek-chat, temperature=0.0, RAG/few-shot/APB/two-stage=off

## 结论

**ROLLBACK — C2 在离线预筛阶段即失败，未发起任何模型 API 调用。**

2021 和 2022 两个独立年度 holdout 的 offline gate 均未通过（4 项硬门槛中各有 3 项失败）。按设计 §5.1 + §5.5，任一年度 offline gate 失败即终止该年度实验、不调用模型。本次两年同时失败，Phase 5 在离线阶段终止，0 次 API 调用、0 费用、未解封 2023。

## 失败模式

| 指标 | 2021 | 2022 | 门槛 | 判定 |
|---|---|---|---|---|
| top_score_hit_rate | 0.6207 | 0.5862 | > 0.35 | ✅ 两年均通过 |
| score_answer_correlation | -0.0462 | 0.0806 | > 0.10 | ❌ 两年均失败 |
| neutral_option_rate | 0.7241 | 0.6552 | < 0.50 | ❌ 两年均失败 |
| strong_signal_option_rate | 0.1897 | 0.2759 | > 0.30 | ❌ 两年均失败 |

C2 适用性: 两年均为 29 生效题 / 11 空转题 (72.5% 生效率)。

三个失败项指向同一根因：

1. **C2 评分与正确答案几乎无相关** — 2021 甚至是负相关 (-0.046)。C2 的命理规则打分对独立年度的题没有区分正确答案的能力。
2. **过半选项落入 neutral (50 分)** — 65-72% 的选项拿到默认分，C2 规则触发不足。
3. **强信号选项不足 30%** — C2 很少给出明确倾向，难以作为模型的有效参考。

对比: 2024/2025 是 C2 规则的校准集，gate 当时通过。这直接验证了设计文档 §1 的担忧："C2 规则针对 2024/2025 holdout 错误样式做过校准，当前结果不能证明独立泛化。" 本次在未参与校准的 2021/2022 上，离线信号即不达标。

## 执行过程

### 预检 (Step 1-2)

- `DEEPSEEK_API_KEY`: `.env` 已配置，脚本运行时经 `config._load_dotenv()` 自动加载。
- `BAZI_RAG` / `BAZI_FEWSHOT_FILE` / `BAZI_APB_BLOCK`: 均为 off，符合固定口径。
- 实验作用域: 原有三个未提交的 C2 文件 (`per_option_scorer.py` / `baziqa_prompt.py` / `run_benchmark.py`)，已审查确认属 C2 核心实现并提交 (commit `d1cd722`)，作用域随后 clean。

### 离线阶段 (Step 3)

对 2021/2022 各 40 题 (共 80 题) 执行 enrichment + scorer-only gate。enrichment chart_input 覆盖率 100%，核心信号字段完整。两年 offline gate 均失败，按设计终止，不进入 API 配对阶段。

### 未执行

- API 配对实验 (2021/2022): 因 offline gate 失败未启动。
- 2023 解封: 因未达到 NON_INFERIOR，2023 保持密封。

## 落盘产物

```
.tmp/phase5_generalization/
├── manifest.json                  run_id / fingerprint / git_commit / scope_hashes / seal_audit_note
├── summary.json                   decision=ROLLBACK, reason=offline_gate_failed, offline 完整证据
├── datasets/
│   ├── baziqa_2021_enriched.jsonl   40 题, chart_input 100% 覆盖
│   └── baziqa_2022_enriched.jsonl   40 题
└── offline/
    ├── 2021.json                    gate 四项数值/阈值/margin + 完整 scorer_summary + c2_applicability
    └── 2022.json
```

## 复现命令

```powershell
# 从干净状态运行 (会重新 enrichment + offline gate, gate 失败即停, 不调 API)
python scripts/run_phase5_c2_generalization.py --run-id phase5-c2-generalization-v1

# 中断恢复 (enrichment/attempts 按唯一键跳过)
python scripts/run_phase5_c2_generalization.py --run-id phase5-c2-generalization-v1 --resume
```

## 归因与后续

C2 规则在独立年度泛化失败，根因在于规则针对 2024/2025 校准过紧、对未参与校准年度的错误样式覆盖不足 (neutral 过高、强信号不足)。这并非编排框架问题 — 离线 gate 正是为此设计的前置防护，按预期在 API 调用前拦截了无效实验。

后续若要推进 C2 泛化，需先在更多年度数据上扩充/重校准规则，使 offline gate 在独立年度达标，再重新发起 Phase 5 验证。当前结论: **C2 不具备向独立年度泛化的能力，不建议进入 MingLi-Bench 非退化验证。**
