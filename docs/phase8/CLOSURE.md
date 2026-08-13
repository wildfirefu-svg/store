# Phase 8 Closure：婚姻类能力改进前提分析（已冻结）

> 关闭日期：2026-08-13。
> 本 closure 冻结 Phase 8 的最终结论、产物与对账状态；Phase 8 不再接受新改动，后续工作转入 Phase 9A/9B。

## 1. 冻结事实

| 项 | 冻结值 |
|---|---|
| 设计 | `docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md` v1.3.2（commit `90c536b` 起多轮修订） |
| 计划 | `docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md` v3.2（commit `edfd3af`） |
| 结论冻结 commit | `084a25f`（NEEDS_FIX 三轮修复：结构化事实/学理注入分离） |
| Phase 8 最终 HEAD | `0f74de2`（closure erratum：sealed spec v1.3.2 版本号修订后重冻结 manifest/provenance SHA） |
| 任务链 | Task 0–8 全部完成，阶段间对账通过 |
| C1 终态 | **C1_TERMINATED**（replay_count=1，160 题四态和=160；0018 changed_wrong_to_wrong、0034/0073 improved、harmed=3） |
| 最终缺口分布（171 知识项） | **检索不可见 112 / 注入缺失 39 / 计算缺失 19 / 知识缺失 1 / 模型未利用 0** |
| 题级 primary_gap | 计算缺失 19 / 检索不可见 16（35 题） |
| 探针四态 | computable 39 / no_interface 19（sihua 无独立流年四化接口）/ missing_input 0 / semantic_gap 0 |
| KB 等价性 | 59/59 ok，fallback_used=0，FTS 直接 MATCH 验证无 LIKE fallback |

## 2. 核心结论

1. 婚姻类 35 道 knowledge 错题的**主缺口为检索不可见**：KB/classic_texts 存在相关条文（112 项证据含命中 ID 与经典定位摘录），但官方 prompt 未注入任何学理规则。
2. 其次为**计算结果注入缺失**（39 项 computable 但 prompt 无大运/流年/四化序列）与**计算接口缺失**（19 项流年四化无独立引擎接口）。
3. 未发现官方 prompt 已注入学理但模型未利用的知识项（模型未利用=0，合法结果）。
4. C1 结论-选项映射转换器未达 PASS 门，C1 线关闭；不得重启、不得直接部署。

## 3. 产物与可复算状态

- 产物目录：`docs/phase8/marriage-capability/`（10 个 p8_*.py 脚本 + 冻结产物 + fts_behavior_probe.json）
- 测试：`tests/test_phase8_marriage_capability.py`（**84 passed**）；fixture：`tests/fixtures/phase8/c1_synth.jsonl`
- manifest：`phase8_freeze_manifest.json`（**28 条目**：10 脚本 + 4 上游输入 + 14 产物，四策略 SHA）
- provenance：`provenance.json`（27 条目，排除自身，重跑字节一致）
- 对账入口：`python docs/phase8/marriage-capability/p8_reconcile.py`（七节全量对账 exit 0）
- 全量回归：2202 passed / 0 failed（基线 2083）；ruff、mypy 通过
- 全程零 API、零生产代码改动

### manifest/provenance SHA（冻结值）

- `phase8_freeze_manifest.json`：见文件内 entries（28 项，四策略：git_canonical_lf 12 / json_canonical 9 / jsonl_canonical 5 / raw_bytes 2）
- `provenance.json`：total_entries=27，entries_by_strategy 分列
- 复核方式：`p8_reconcile.py manifest_disk` 节逐项复算（独立实现三种 canonical 口径）
- **closure erratum（2026-08-13，commit `0f74de2`）**：`9822d59` 修订 sealed_marriageset_spec.md 版本号引用（v1.3.1→v1.3.2）后未同步 manifest/provenance，reconcile 一度 FAIL（exit 1）；已重冻结该文件 SHA 并重生成 provenance，reconcile 恢复 exit 0。最终 HEAD 以本 erratum 提交为准。

## 4. 工程发现（供 Phase 9A 引用）

1. **FTS5 unicode61 中文漏检**：连续汉字序列为一个 token（无中文分词）；`红鸾` MATCH=0 / LIKE=2、`婚姻` MATCH=37 / LIKE=49、`姻缘` MATCH=0 / LIKE=2（已冻结于 `fts_behavior_probe.json`）。**Phase 9A 检索策略必须替代或组合 FTS**。
2. **注入判定语义**：prompt 分区（injected_context/question/options）后，星曜名/宫位名/干支等结构化事实出现 ≠ 学理注入（chart_fact_present 与 doctrine_injected 分离）。
3. **已知限制（P2）**：`_doctrine_injected` 按值排除结构化事实词，对含星名的断诀规则会整体排除；复用审计器于 enhanced/RAG prompt 前需 span-aware 检测（见 `p8_audit.py` docstring）。

## 5. 后续衔接

- **Phase 9A**（零 API 检索可行性）：只解决"检索不可见 112"，不混入大运/流年注入或 prompt 改写；只评价召回/注入质量，不评价准确率。设计见 `docs/superpowers/specs/2026-08-13-phase9a-marriage-retrieval-design.md`。
- **密封婚姻集采集**：数据来源与 curator 由用户裁决（见 Phase 9A 设计附录 A）。
- **Phase 9B**（配对实验 spec）：密封集就绪后冻结 power/门槛/回退护栏，单 treatment factor = marriage retrieval bundle；baseline = Phase 7 原协议；116 道非婚姻题作退化护栏。

## 6. 冻结纪律

- Phase 8 产物不得再改；确需修订时整文件版本化重冻结并对账。
- 44 道已知婚姻题只能用于开发与确认；任何改进的"效果声明"必须以密封集为准。
- 不重启 C1；不在 44 道已知题上宣称准确率提升；不把检索/大运流年/prompt 改写打包为单一 treatment。
