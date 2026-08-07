# Spec 审核：Phase 6 6B2 DeepSeek-V4-Flash Non-Thinking 实验协议设计

**审核日期**：2026-07-20 | **审核文档**：`docs/superpowers/specs/2026-08-05-phase6-6b2-v4-flash-nonthinking-design.md`（232 行）
**审核结论**：**通过（无阻断），4 条中优 + 2 条如实备注。代码库事实核验全部成立。**

---

## 一、总体评价

设计聚焦且克制：只约束 6B2 实验链（dev→reuse→final_2023），不动 REST/桌面/MCP 与其他评测流程；冻结协议单一事实源（`FROZEN_PROVIDER/MODEL/THINKING_MODE`）+ 入口零调用预检 + run_context 防旧目录混入 + manifest/audit/receipt 三处交叉绑定 + B1-c 降级为历史 advisory——与 Phase 6 既有的 fail-closed/指纹/准入纪律一脉相承。测试策略全部非网络、TDD、可执行。

## 二、代码库事实核验（全部成立）

| Spec 断言 | 核验 |
|---|---|
| 同步调用接口 `call_model_messages_sync_with_meta` 存在，spec 在其上增加可选 `thinking_mode` | 成立（`claude_api.py:144`）；当前同步 payload **不含** thinking 字段（:165-210 逐行确认），spec"未显式传入时保持当前行为"的前提准确 |
| payload 形状 `{"thinking":{"type":"disabled"}}` | 与现有流式路径约定完全一致（`claude_api.py:413-417`：`DEEPSEEK_THINKING` env → `payload["thinking"]={"type": ...}`）——spec 复用了正确的既有形状 |
| `deepseek-v4-flash` 为显式新模型标识 | config 默认 `DEEPSEEK_MODEL="deepseek-v4-pro"`（`config.py:91`）；v4-flash 经 `--model` 显式传入，不依赖 config/env，符合 spec"不允许环境变量静默覆盖" |
| runner CLI 需新增 `--thinking-mode` | 当前不存在（grep 确认），spec 明确为新增项，且只有 runner 内层提供、orchestrator 恒传 disabled——方向正确 |
| 6A1/6B1 历史臂用 `deepseek-chat` | 属实（6a1-2024-001、6b1 归档均为 deepseek-chat）；B1-c 降级 advisory 与此一致 |
| `RECEIPT_REQUIRED_FIELDS` / `check_stage_gate` / `runs/<run_id>` 布局 | 均为 6B2 计划 v15 已有产物，spec §7.3/§6 引用一致 |

## 三、中优意见（4 条）

1. **§5.2 响应模型精确匹配可能误伤**：`model != "deepseek-v4-flash"` 即调用失败——若 API 返回带日期后缀的模型 ID（如 `deepseek-v4-flash-20250801`）或大小写差异，会误阻断 smoke。建议改为规范化匹配（前缀/小写比较）或在 spec 中写死"以响应原样记录，仅当明确可判定为不同模型族时才失败"。
2. **32.5% 绝对准确率门槛的锚定问题**：该阈值 = deepseek-chat 真实基线 27.5% + 5pp（设计 v6 §7.3 冻结）。换用 v4-flash 后基线可能漂移，spec §3 非目标"不改变 gate 阈值"是合法选择（预注册不可中途改），但**建议 spec 明确声明**：阈值保持 32.5% 是"沿用 deepseek-chat 时代的冻结值"，v4-flash 的基线对照以同期 b1a′ 为主（这正是 spec §1 已采用的口径——建议把这句话写进 §7 或 §8，堵住"换模型后阈值虚高/虚低"的评审追问）。
3. **`thinking_mode` 入 `RESUME_MANIFEST_FIELDS` 的兼容性**：旧 manifest（6A1 时代）无此字段 → fail-closed。对 6B2 新实验无碍，但应在 spec 加一句说明："6A1 既有归档不因此失效——其 resume 语义不变（它不带 thinking_mode 校验），本字段仅约束 6B2 新 run"。避免读者误读为全局破坏。
4. **与 6B2 计划的落地顺序**：spec 依赖的 `run_context.json`、`--thinking-mode` 入 cmd、receipt/audit 新字段，都需要 6B2 计划先行定稿（计划当前 v15，另有 v16 修订项：准入接线/预算公式/audit fixture/run_id 归档）。建议在 spec §11 验收标准前加"前置：6B2 实施计划 v16 定稿"，避免计划与 spec 各自悬空。

## 四、如实备注（2 条，非问题）

- spec §6.2 "未传 `--resume` 且 run 目录已存在即拒绝" 恰好闭合了第六轮审核遗留的"`_run_dev_reuse` 的 `resume` 参数未进入行为判断"中优项——方向一致，实施时把该入口检查放在 `run_dev/run_reuse` 首行。
- 冻结协议预检失败"发生在创建 run 目录之前"与 §6.1"入口创建目录后原子写入 run_context.json"的顺序需明确为：校验 → 建目录 → 写 context（当前文本顺序已正确，实现时勿颠倒）。

## 五、判定

无阻断项。4 条中优中，**#1（响应模型匹配规则）与 #2（阈值锚定声明）建议实施前落入 spec**；#3/#4 为文字补充。通过后可进入 writing-plans，其计划应与 6B2 实施计划 v16 合并或明确先后关系。
