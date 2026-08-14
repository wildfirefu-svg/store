# Phase 9A Closure：婚姻知识检索可行性（QC_FAIL 终态）

> 关闭日期：2026-08-14。
> 本 closure 冻结 Phase 9A 的最终结论、产物与对账状态；Phase 9A 不再接受新改动，后续工作转入 Phase 9B（待密封集就绪）。

## 1. 冻结事实

| 项 | 冻结值 |
|---|---|
| 设计 | `docs/superpowers/specs/2026-08-13-phase9a-marriage-retrieval-design.md` v1.3.3（commit `c29862f`） |
| 计划 | `docs/superpowers/plans/2026-08-13-phase9a-marriage-retrieval.md` v2.5.5（commit `9ff6d08`） |
| 终态 | **SILVER_RETRIEVAL_NOT_READY**（QC_FAIL 分支：人工 QC 分歧率 53.73% > 冻结上限 10%） |
| QC 复核 | 67/67 条人工复核完成；分歧 36/67（53.73%） |
| 指标 | **not_computed**（QC_FAIL 分支不计算召回率/噪声，不生成 bundle） |
| 产物 | qc_result.json + retrieval_eval.json + RECEIPT.json（QC_FAIL 精确 artifact 集合） |
| manifest | `manifest_v2.json`（27 条目，sealed；原 manifest.json 保留不动，supersedes 关系记录于 migration 元数据） |
| 对账入口 | `python docs/phase9a/retrieval/reconcile9a.py`（逐项 expected==actual + RECEIPT 证据链 + 终态校验） |

## 2. 核心结论

1. **silver 规则与人工复核分歧率 53.73%**，远超冻结上限 10%——silver 初标规则（同义词共现 + category 一致性）与人工判断存在系统性偏差，检索可行性**未证实**。
2. **不计算检索指标**：按协议，QC_FAIL 分支不计算 weighted_recall/bundle_noise/binary coverage，不生成 bundle；终态/原因/产物完整发布。
3. **工程可复现性已验证**：全部产物 SHA 可复算、双跑字节一致、freeze-before-use 门生效、append-only manifest 完整。
4. **结论限定**：本阶段只证明"检索器与冻结 silver 判据的一致性与工程可复现性"，**不构成语义相关性或检索效果的声明**；语义相关性声明必须依赖独立人工 gold（后续独立工作线）。

## 3. 产物清单（QC_FAIL 分支）

| 产物 | 说明 |
|---|---|
| `qc_result.json` | 分歧判定结果（53.73% > 10% → SILVER_RETRIEVAL_NOT_READY） |
| `retrieval_eval.json` | 终态（verdict=SILVER_RETRIEVAL_NOT_READY, qc_state=QC_FAIL, metrics=not_computed） |
| `RECEIPT.json` | 发布完成标记（含两 artifact 的 sha256/size/strategy + verdict） |
| `treatment_fingerprint.json` | 组件 SHA 单源（retriever/run_strategies/strategy_store/query_extractor/配置/上游输入） |
| `manifest_v2.json` | 27 条目 sealed（含 migration 元数据：supersedes manifest.json + 原 SHA） |
| `reconcile9a.py` | 对账入口（逐项 expected==actual + RECEIPT 证据链 + 终态校验） |

## 4. 后续衔接

- **Phase 9B**（配对实验 spec）：待密封婚姻集就绪后冻结 power/门槛/回退护栏；单 treatment factor = marriage retrieval bundle；baseline = Phase 7 原协议；116 道非婚姻题作退化护栏。
- **人工 gold 建立**：如需语义相关性声明，需独立人工标注工作线（不阻塞本阶段双终态判定）。
- **silver 规则修订**：若需重跑，需修订 silver 规则（RULE_SOURCE 变更 → 重冻结 → 重跑全链路），不得在本冻结产物上修改。

## 5. 冻结纪律

- Phase 9A 产物不得再改；确需修订时以新版本号新建文件并重新走 seal 流程，旧版保留不动。
- 44 道已知婚姻题只能用于开发与确认；任何改进的"效果声明"必须以密封集为准。
- 不重启 C1；不在 44 道已知题上宣称准确率提升；不把检索/大运流年/prompt 改写打包为单一 treatment。
