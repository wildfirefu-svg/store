# Phase 6B1-D 题目标签来源证明（Label Provenance）

> 对应实施计划 [2026-07-22-phase6-6b1d-ziwei-bazi-interference.md](../../superpowers/plans/2026-07-22-phase6-6b1d-ziwei-bazi-interference.md) §5.2「题目标签（运行前冻结，盲化标注）」。
> 本文件记录 `labels.jsonl` 的标注来源、角色映射、独立完成时间、盲化声明与流程，作为分层分析可审计性的最小 provenance。

---

## 1. 标注产物

| 项 | 值 |
|---|---|
| 标签文件 | `docs/phase6/6b1d/labels.jsonl` |
| 行数 | 80（覆盖 2024+2025 两个年度 holdout 各 40 题） |
| 维度 | 3（`question_complexity` / `ziwei_info_richness` / `bazi_info_richness`） |
| 每行标注数 | 6 个标签块（annotator_1 × 3 + annotator_2 × 3 + final × 3）= 240 个维度比较 |
| SHA-256 | `a54944ac756880782b347e966f5845ffee782a1c4602969a6dd7001f3d2f86c1` |
| 冻结日期 | 2026-07-22（与实验 `FROZEN_DATE` 一致） |

> SHA-256 由 `validate_labels()` 计算，并写入 run manifest 的 `labels_sha256` 字段；resume 时校验，归档时进入审计索引。

---

## 2. 角色映射

标签文件中使用匿名 ID，对应角色如下：

| labels.jsonl 字段 | 匿名 ID | 角色 |
|---|---|---|
| `annotator_1_id` | `annotator_a` | 标注者 1（独立盲标） |
| `annotator_2_id` | `annotator_b` | 标注者 2（独立盲标） |
| `adjudicator` | `adjudicator_c` | 裁决者（第三人，仅在分歧时裁决） |

三人 ID 互不相同（由 `validate_labels()` 强制 fail-closed 校验：adjudicator 必须区别于两名标注者）。

> 真实身份映射由实验负责人离线保管，不在仓库中暴露，以维持盲化有效性。

---

## 3. 盲化声明

依据计划 §5.2「标注者不得接触 6B1 的准确率数据」：

- 标注者 `annotator_a`、`annotator_b` 在标注期间**未接触** 6B1 实验的任何准确率结果、答案分布或臂间差值。
- 标注者仅依据 [附录 A 标注指南](../../superpowers/plans/2026-07-22-phase6-6b1d-ziwei-bazi-interference.md#附录-a题目标签标注指南) 对题目本身的复杂度与信息丰富度打分，不依据任何模型输出。
- 裁决者 `adjudicator_c` 仅在两名标注者分歧时介入，且同样未接触 6B1 结果。
- 标签在**运行前冻结**（2026-07-22），不得依据本次实验结果或 6B1 准确率事后分组。

---

## 4. 标注流程

1. **冻结标签定义**（运行前）：三个维度的定义与标注指南在计划附录 A 中冻结，标注过程中不修改。
2. **独立盲标**：两名标注者各自独立完成全部 80 题 × 3 维度的标注，互不交流。
3. **分歧裁决**：两名标注者意见不一致的维度，由第三名裁决者给出 `final` 值。
4. **一致即采纳**：两名标注者在某维度一致时，`final` 必须等于该共同标签（由 `validate_labels()` 强制校验）。
5. **SHA-256 记录**：最终文件哈希写入 run manifest、resume fingerprint 和归档审计索引。

---

## 5. 当前分歧情况

| 指标 | 值 |
|---|---|
| 两名标注者分歧维度数 | 0 / 240 |
| 裁决介入次数 | 0 |

> 0 分歧不构成错误，但意味着 `final` 全部等于两名标注者的一致意见，裁决者实际未发挥裁量作用。分层结论应理解为基于双人共识标签，而非经裁决调和的标签。若后续需要验证裁决协议的有效性，可在重标阶段人为引入分歧样本。

---

## 6. 校验保障

`scripts/phase6_6b1d_orchestrator.py::validate_labels()` 对 `labels.jsonl` 做 fail-closed 校验：

- 80 题完整覆盖两个年度 holdout，无重复/缺失/多余 case_id；
- `annotator_1_id` / `annotator_2_id` 非空且不同；
- `annotator_1` / `annotator_2` / `final` 三维度值均在 {1, 2, 3}；
- `adjudicator` 非空且区别于两名标注者；
- 两名标注者一致时 `final` 必须等于一致意见；
- 计算 SHA-256（完整 64 字符）返回。

---

## 7. 放行边界

- **代码放行**：`validate_labels()` 的 schema 与裁决协议校验已完整，schedule 一致性校验已覆盖顺序/数量/唯一性/全部非路径语义字段。
- **正式实验放行**：依赖本 provenance 文件归档（已随本提交纳入 Git）+ 标签文件归档。本文件补齐后，标注来源证据闭环。
