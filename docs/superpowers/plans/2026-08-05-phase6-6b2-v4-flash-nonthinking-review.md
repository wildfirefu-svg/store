# 实施计划审核：Phase 6 6B2 DeepSeek-V4-Flash Non-Thinking

**审核日期**：2026-07-20 | **审核文档**：`docs/superpowers/plans/2026-08-05-phase6-6b2-v4-flash-nonthinking.md`（1063 行，9 任务）
**关联设计**：`docs/superpowers/specs/2026-08-05-phase6-6b2-v4-flash-nonthinking-design.md`（已审，通过+4 中优）
**审核方式**：子代理全量核查（spec 覆盖/实现正确性/测试可执行性/内部一致性/遗留项）+ 关键阻断项本人复验
**审核结论**：**NEEDS_REVISION——1 个阻断 + 2 个中优 + 8 个低优。修掉阻断与既有测试连带清单后可进入实施。**

---

## 一、总体评价

计划质量高：spec §4-§11 全部条目有落点；实现代码锚点精确（`claude_api.py:144-246` 同步接口、runner 调用漏斗 `_call_once_messages`、orchestrator/sealed_workflow 各自边界清晰、无循环导入）；TDD 节奏完整；同源纪律（`_build_runner_cmd`/`_slice_runner_args` 只读 `slice_info["thinking_mode"]`）落实到位；spec 审核遗留 #1（响应模型匹配）已按大小写敏感精确匹配双侧钉死。

## 二、阻断（1 项，本人复验确认）

### B1：Task 2 新增 `_Resp` 与既有夹具同名冲突，绿灯必翻车

`tests/test_claude_api.py:91-103` 已有 `_Resp`（`read()` 硬编码返回 `{"choices":[{"message":{"content":"A"}}]}`），既有测试 `test_call_model_messages_sync_sends_temperature`（:106-125）依赖该硬编码——它把**请求 payload** 传给 `_Resp(captured["payload"])` 并期望解析出 "A"。计划（:165-177）在文件后部重定义 `_Resp`（`read()` 返回构造入参 JSON），此后既有测试的 fake 返回请求 payload（无 `choices` 键）→ 解析为空 → `assert out == "A"` 必失败。

**修复**：新夹具改名（如 `_JsonResp`），或按新夹具契约同步改写既有测试。计划必须写明，否则 Task 2 Step 4"全文件通过"无法达成。

## 三、中优（2 项）

### M1：既有测试连带失败清单未列出（本人复验确认）

冻结校验与新签名会让一批既有测试失败，但计划未授权修改它们：

- `tests/test_phase6_6b2.py:1339`：`run_dev("deepseek", "deepseek-chat", ...)` → 冻结拒绝
- `:1642/:1725/:1751/:1761`：`run_dev/run_reuse/run_2023_final("p", "m", ...)` → 冻结拒绝
- `TestRunDirIsolation`：`generate_report` 的 `fake_report` 无 `run_id` 形参 → TypeError
- `TestTask16GenerateArchive` / `TestAtomicArchive` / `TestSmokeAttemptedInAudit` / `TestDash6b2UserRunId`：`generate_archive(..., "p", "m" / "deepseek-chat")` → 冻结拒绝
- `TestTask11RunnerCmd` 与 `TestManifestHomology` 的 slice 夹具无 `thinking_mode` 键 → 硬读 `slice_info["thinking_mode"]` KeyError

改动都是机械性的（换冻结值/补字段/加 `**kw`），但"只碰必须碰的"纪律下实施者需要**逐 Task Step 1 显式授权的连带夹具更新清单**。

### M2：`thinking_mode` 入 `RESUME_MANIFEST_FIELDS` 的跨实验影响未声明

该字段集是 Phase 6 全局共享（`run_benchmark.py:153-159`）。加入后，6A0/6A1/6B1 时代的旧 manifest resume 时以 `<MISSING>` fail-closed（`check_resume_manifest` :240-247）——行为本身正确，但计划在实施边界只字未提，旧实验在飞者会"意外"被拒。补一行影响声明即可。

## 四、低优（8 项，实施时顺手收口）

1. 缺"环境变量不静默覆盖"的钉死测试（spec §3 明文禁止项）
2. `slice_status` 未记录 response model（spec §7.2 字面要求；events 层已有，可论证但偏离字面）
3. Task 5 新写 `_atomic_write_json` 与 orchestrator 既有同名函数（:981-988）重复定义；`os.mkdir` 未处理 `runs/` 父目录缺失
4. Task 5/9 的报错文案 `run_context.json missing` 未在实现步骤钉死，措辞漂移会双红
5. Task 8（fake runner 全链）无代码骨架——四件套契约复刻是全计划最重执行风险
6. 计划行 720 测试类名误写 `TestFingerprintCriticalCoverage`（实为 `TestCodeFingerprintCriticalCoverage`）
7. 32.5% 阈值无显式锚定声明（spec 审核遗留 #2 未完全落地，仅笼统"不改阈值"）
8. 全文无 "v18" 字样，未交代与 6B2 v18 计划的先后关系（实际已合入，文档欠一句）

## 五、已核验通过（摘要）

- **Spec 覆盖**：§4-§11 全条目有落点（含 §5.2 响应模型缺失不伪造、§6.3 阶段状态机、§8 B1-c 排除文案逐字一致、§9 失败处理分行覆盖、§11 基线已复跑 148 passed）
- **实现正确性**：payload 插入位置与既有结构兼容；非 DeepSeek 拒绝在 urlopen 之前；runner 唯一调用漏斗 `_call_once_messages` 透传可行；response_model_mismatch 抛于成功分支外不吃重试预算；run_context 原子写/独占创建/不吞 KeyboardInterrupt；sealed↔orchestrator import 关系安全（函数内延迟导入）
- **同源纪律**：`_build_schedule`/`_build_smoke_slices` 统一注入 `FROZEN_THINKING_MODE`；`_SCHED_HASH_SLICE_KEYS` 加键使协议进 schedule hash；`RESUME_MANIFEST_FIELDS` 写法与既有 `as_of_date` 同款
- **锚点抽查**：9 处文件:行号锚点全部命中（orchestrator/sealed_workflow/run_benchmark/claude_api/tests）
- **误伤面**：`call_model_messages_sync` 尾部可选参数对既有调用方零影响；除 B1/M1 清单外无其他不向后兼容点

## 六、判定

| 类别 | 数量 | 内容 |
|---|---|---|
| 阻断 | 1 | B1 `_Resp` 夹具同名冲突 |
| 中优 | 2 | M1 既有测试连带清单；M2 旧 manifest 影响声明 |
| 低优 | 8 | 见第四节 |

修复 B1 + 补齐 M1 清单后即可放行实施；M2 与低优项建议同轮修订。
