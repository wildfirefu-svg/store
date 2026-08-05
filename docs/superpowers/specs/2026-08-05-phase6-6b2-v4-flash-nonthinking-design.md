# Phase 6 6B2：DeepSeek-V4-Flash Non-Thinking 实验协议设计

**日期：** 2026-08-05
**状态：** 已确认，待实施计划
**适用范围：** Phase 6 6B2 dev → reuse → final_2023 实验链

## 1. 背景与决策

6B2 原计划与历史 B1-c 产物使用 `deepseek-chat`。该旧模型标识已不再适合作为新实验的显式模型协议。新实验固定使用：

| 字段 | 冻结值 |
|---|---|
| provider | `deepseek` |
| model | `deepseek-v4-flash` |
| thinking mode | `disabled` |
| 报告标签 | `DeepSeek-V4-Flash non-thinking` |

本设计只约束 6B2 实验链，不改变 REST API、桌面端、MCP 服务或其他评测流程的 DeepSeek 行为。

旧 B1-c `deepseek-chat` 结果仅作为历史 advisory 展示，不参与任何 gate。6B2 的主要证据来自同一时段、同一模型协议下的 b1a′ 与 dual 对照。

### 1.1 文档性质与当前实现状态

本文是待实施的目标状态设计，不表示下列契约已经存在于当前代码。设计批准时的仓库现状如下：

| 目标契约 | 设计批准时状态 |
|---|---|
| `FROZEN_PROVIDER` / `FROZEN_MODEL` / `FROZEN_THINKING_MODE` / `MODEL_LABEL` | 尚未定义 |
| 同步 API 的 `thinking_mode` 参数及 payload 写入 | 尚未实现 |
| runner `--thinking-mode` | 尚未实现 |
| orchestrator `--resume` 与 `run_context.json` | 尚未实现 |
| resume manifest 的 `thinking_mode` | 尚未实现 |
| audit/receipt/gate 的 thinking mode 与 model label 绑定 | 尚未实现 |

这些项目是本设计后续实施计划的必做范围，不得在实现完成前启动合格的 V4-Flash non-thinking 实验。

### 1.2 既有 V4-Pro Thinking Run 的处置

设计批准期间曾启动以下旧协议运行：

```text
run directory: docs/phase6/6b2/runs/phase6-6b2-final-2023/
requested model: deepseek-v4-pro
observed mode: thinking（调用事件含 reasoning_tokens）
progress: smoke 已完成，dev 已进入正式切片
run_context.json: 不存在
process: PID 5432 已停止
classification: NONCOMPLIANT_V4_PRO_THINKING
```

该目录只保留作费用与失败路径审计，不属于本设计的证据集：

- 不进入任何 6B2 accuracy、delta、gate 或模型对比；
- 不允许以新协议补写 `run_context.json`；
- 不允许被 V4-Flash non-thinking 的 dev/reuse/final resume；
- 不自动删除、覆盖、迁移或改写其原始事件；
- 新实验必须使用从未存在过的全新 `run_id`。

## 2. 目标

1. 让 6B2 的每次真实模型调用显式使用 `deepseek-v4-flash` non-thinking。
2. 在调用前、断点恢复、归档和跨阶段准入中锁定同一模型协议。
3. 阻止旧模型、thinking 模式或未知运行目录的产物混入新实验。
4. 保留同一 `run_id` 下安全、可审计的中断恢复能力。
5. 让报告明确区分同期主对照与历史 advisory。

## 3. 非目标

- 不修改其他 DeepSeek 调用的默认 thinking 行为。
- 不重新计算或重写 B1-c 历史结果。
- 不改变 6B2 的题集、arm、repeat、预算、gate 阈值或 2023 密封规则。
- 不允许用环境变量静默覆盖 6B2 的冻结模型协议。
- 不把 `deepseek-v4-pro` 或其他模型作为本实验的兼容别名。

## 4. 冻结协议与入口约束

`scripts/phase6_6b2_orchestrator.py` 定义单一事实源：

```python
FROZEN_PROVIDER = "deepseek"
FROZEN_MODEL = "deepseek-v4-flash"
FROZEN_THINKING_MODE = "disabled"
MODEL_LABEL = "DeepSeek-V4-Flash non-thinking"
```

`run_dev`、`run_reuse`、`run_2023_final` 以及 CLI 入口都必须在创建锁、读取数据或调用模型前验证这些值。任何不一致均立即 `SystemExit`，不得消耗 API 预算。

orchestrator CLI 保留 provider/model 参数以便调用清晰和 receipt 交叉验证，但只接受冻结值。orchestrator 不提供可自由选择的 thinking 参数；它始终从冻结常量读取 `disabled`。只有内部 runner CLI 新增 `--thinking-mode`，且 6B2 orchestrator 每次都显式传入 `disabled`。

## 5. 仅限 6B2 的 API 参数链

参数沿以下路径显式传递：

```text
phase6_6b2_orchestrator
  → run_benchmark --thinking-mode disabled
  → 6B2 dual/b1a′ 模型调用
  → call_model_messages_sync_with_meta(..., thinking_mode="disabled")
  → DeepSeek request payload
       {"thinking": {"type": "disabled"}}
```

### 5.1 API 接口兼容性

`claude_api.py` 的同步调用接口增加可选 `thinking_mode=None` 参数：

- provider 为 `deepseek` 且显式传入 `disabled` 时，payload 写入 `{"thinking":{"type":"disabled"}}`。
- 未显式传入时，保持当前行为，不向同步 payload 自动增加 thinking 字段。
- 非 DeepSeek provider 收到 thinking mode 时应拒绝，避免记录值与真实请求不一致。
- 6B2 runner 必须显式传入冻结值，不得依赖 `DEEPSEEK_THINKING` 环境变量。

### 5.2 响应模型核验

同步 API metadata 记录响应中的 `model`。冻结响应标识是大小写敏感的精确字符串 `deepseek-v4-flash`；`DeepSeek-V4-Flash` 或其他展示名称不视为等价。若响应提供该字段且不等于冻结标识，本次调用标记失败并阻断 smoke。响应未提供 model 时保留缺失事实，不伪造实际模型名称；请求协议仍由 manifest 与事件记录证明。

## 6. Run Context 与全新运行

### 6.1 首次创建

首次启动 dev（未传 `--resume`）时，`runs/<run_id>/` 必须不存在。入口创建目录后原子写入 `run_context.json`：

```json
{
  "provider": "deepseek",
  "model": "deepseek-v4-flash",
  "thinking_mode": "disabled",
  "model_label": "DeepSeek-V4-Flash non-thinking",
  "code_fingerprint": "<sha256>",
  "created_at": "<iso8601>"
}
```

不得从缺少 `run_context.json` 的既有目录推断协议，也不得自动补写旧目录。

### 6.2 中断恢复

同一实验中断后允许使用相同 `run_id` 恢复，但调用方必须显式传入 orchestrator `--resume`。未传 `--resume` 时，只要 run 目录已存在就拒绝。传入 `--resume` 时必须同时满足：

- `run_context.json` 完整且与冻结协议一致；
- 当前代码指纹一致；
- slice resume manifest 一致；
- provider、model、thinking mode 一致；
- 已有 smoke、events、details、ledger 属于同一运行上下文。

任一条件不满足即拒绝恢复，不覆盖旧文件，不创建“兼容”manifest。

### 6.3 阶段状态

- dev receipt 尚未发布且显式传入 `--resume`：允许合法 dev 恢复。
- dev receipt 已发布：拒绝再次执行 dev，只允许进入 reuse。
- reuse receipt 已发布：拒绝再次执行 reuse，只允许进入 final_2023。
- reuse 与 final_2023 必须沿用 dev 的同一 `run_id` 和 run context。

## 7. Manifest、审计与跨阶段绑定

### 7.1 Resume Manifest

`thinking_mode` 加入 `RESUME_MANIFEST_FIELDS` 并由 `build_resume_manifest()` 写入。缺字段、值变化或旧 manifest 均拒绝 resume。

runner command 与 manifest 重建必须同源读取 slice 中的冻结字段，避免命令使用 `disabled` 而 manifest 记录其他值。

### 7.2 Slice 与调用证据

slice 配置、`slice_status.json` 和调用事件记录以下协议字段：

- provider；
- requested model；
- thinking mode；
- 可用时的 response model。

### 7.3 Audit 与 Receipt

`audit_index.json` 与阶段 receipt 增加必填字段：

```json
{
  "model": "deepseek-v4-flash",
  "thinking_mode": "disabled",
  "model_label": "DeepSeek-V4-Flash non-thinking"
}
```

`RECEIPT_REQUIRED_FIELDS` 加入 `thinking_mode` 和 `model_label`。`check_stage_gate()` 必须验证：

1. receipt 与 audit 字段一致；
2. receipt 与当前冻结协议一致；
3. dev、reuse 及 final_2023 使用相同 thinking mode；
4. `expected_user_run_id`、provider、model、代码指纹继续满足既有约束。

## 8. 报告与结论口径

`summary.json` 和 Markdown 报告固定展示：

```text
Model protocol: DeepSeek-V4-Flash non-thinking
Provider: deepseek
Requested model: deepseek-v4-flash
Thinking mode: disabled
Run ID: <run_id>
B1-c: historical deepseek-chat advisory only; excluded from all gates
Primary comparison: concurrent b1a′ vs dual
```

B1-c advisory 不得进入 delta、accuracy gate、promote/rollback 判定或显著性结论。报告可以展示其数量与冻结 SHA，但必须同时展示上述限制文案。

## 9. 失败处理

| 条件 | 处理 |
|---|---|
| provider/model/thinking mode 不匹配 | smoke 前拒绝，零 API 调用 |
| 已有 run 目录缺少 context | 拒绝，不自动迁移 |
| run context 或 manifest 漂移 | 拒绝 resume |
| dev/reuse/final receipt thinking mode 不一致 | 阶段准入失败 |
| 响应 model 明确不是 V4-Flash | 调用失败；smoke 阻断 |
| dev/reuse 已发布后重跑同阶段 | 拒绝，避免覆盖和重复计费 |
| B1-c 缺失或 SHA 不符 | 保持既有 fail-closed；不得用替代产物 |

冻结协议预检失败发生在创建 run 目录之前，只向调用方返回明确错误且不产生实验产物。`run_context.json` 已创建后的所有拒绝必须在该 run 的持久化状态中保留原因。不得通过删除失败题、重建旧 manifest 或修改统计分母恢复实验。

## 10. 测试策略

采用 TDD，测试不访问网络。

### 10.1 冻结入口

- 非 `deepseek` provider 零调用拒绝；
- 非 `deepseek-v4-flash` 模型零调用拒绝；
- thinking mode 非 `disabled` 零调用拒绝；
- CLI 与三个公共入口使用同一验证函数。

### 10.2 API Payload

- 6B2 同步调用精确包含 `{"thinking":{"type":"disabled"}}`；
- 非 6B2 同步调用不自动增加 thinking 字段；
- 非 DeepSeek provider 不接受 6B2 thinking 参数；
- response model 不匹配时 smoke 失败。

### 10.3 Manifest 与恢复

- manifest 写入 `thinking_mode=disabled`；
- 缺字段或字段漂移拒绝 resume；
- 新 run 创建、显式 `--resume` 的合法中断恢复、未带 `--resume` 的既有目录拒绝、旧目录拒绝、已完成阶段重跑拒绝；
- runner argv 与 manifest 的 thinking mode 同源一致。

### 10.4 Audit、Receipt 与报告

- audit/receipt 写入并交叉验证 thinking mode 与 model label；
- dev/reuse/final 任一字段漂移均拒绝；
- 报告包含固定模型标签和 B1-c advisory 限制；
- B1-c 数据不参与 gate 的回归断言。

### 10.5 执行链

- fake model runner 覆盖 dev → reuse → final_2023 协议传递；
- smoke、预算、resume、归档现有测试继续通过；
- 完成后运行 6B2 定向套件及 Phase 6 非网络回归套件。

## 11. 验收标准

### 11.1 P0 实施前置闸

以下项目全部实现并通过定向测试后，才能进入真实 smoke 验收：

- [ ] orchestrator 定义并统一使用四个冻结常量；
- [ ] 同步 DeepSeek API 接受显式 `thinking_mode` 并写入 non-thinking payload；
- [ ] runner CLI 支持并向模型调用传递 `--thinking-mode disabled`；
- [ ] orchestrator 支持显式 `--resume`，并原子创建/校验 `run_context.json`；
- [ ] resume manifest 必填并校验 `thinking_mode`；
- [ ] audit、receipt 与 `check_stage_gate` 必填并交叉校验 thinking mode/model label；
- [ ] `NONCOMPLIANT_V4_PRO_THINKING` 目录被新协议入口与 resume 测试拒绝；
- [ ] 实施前重新运行并记录回归基线；设计批准时已独立验证的定向基线为 148 passed，Phase 6 广泛基线由实施计划重新采集，不沿用口头数字。

### 11.2 真实实验验收

满足以下全部条件才允许启动真实 dev smoke：

1. 6B2 只能以 `deepseek/deepseek-v4-flash/disabled` 启动；
2. fake API 观测到同步 payload 的 thinking 字段；
3. manifest、run context、audit、receipt 和报告均记录同一协议；
4. 任何跨阶段或 resume 漂移均 fail-closed；
5. 全新 run ID 规则与合法恢复规则均有测试；
6. B1-c 明确为不参与 gate 的历史 advisory；
7. 定向及 Phase 6 回归测试通过；
8. 实验代码与设计、实施计划已进入 Git。
