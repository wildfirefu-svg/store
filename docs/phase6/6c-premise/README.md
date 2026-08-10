# 6C 前提筛选报告：未观察到规则可检测事实矛盾对错题的富集信号

**日期：** 2026-08-10
**状态：** 前提筛选完成，6C 未达启动门槛（`PRECONDITION_NOT_MET / NOT_STARTED`）
**性质：** 探索性前提筛选（非预注册门禁——该门槛在本次分析中首次设定，无更早的冻结记录）

## 1. 问题

6C 候选方向（claim verifier）的启动前提：当前最优单管线基线的错题中，规则可检测的事实矛盾（十神归属错误、干支关系错误、五行属性错误）应显著富集于错题组。若不富集，claim verifier 作为"错题纠错器"缺乏数据支持。

**筛选门槛（本次设定，非预注册）**：错题组行级矛盾率 ≥ 对题组 2 倍，且绝对值 ≥ 20%。

## 2. 数据与方法

- **数据源**：`docs/phase6/6b2/phase6-6b2-v4flash-nt-20260805-r2-6b2-dev-2026-07-17-deepseek-deepseek-v4-flash-642ba3da19d5/merged_details.jsonl`
  - SHA-256：`274a3fd8393fd0c4cee6663598c28f16e406da3365e18ebc433f3b4aff688b25`
  - B1-a′ 臂（`b1a_prime`），240 行 parsed = **80 个唯一 case × 3 repeats**（重复运行，非 240 个独立样本）
- **分析脚本**：`claim_contradiction_analysis.py`（本目录，从归档位置可直接运行）
  - SHA-256：`4fcd8f97dea0659eaa23b03583f033e05a989eb38a191cb9768693869591fbf9`
  - 检测规则版本以该脚本哈希为准（正则抽取三类声明：十神归属 / 干支关系 / 五行属性）
- **结果产物**：`claim_contradiction_report.json`（本目录）
  - SHA-256：`c4c9ee8619e8d75a068673c3a58e7410870aff986430a56c83bcdd91011ac4d8`
- **依赖数据集**（脚本经 chart_input 间接依赖）：
  - `benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl` SHA-256：`219460fe4d001430664144328d054ca960b48486a1641f711be2b3f40f195c32`
  - `benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl` SHA-256：`96275b90f1304053e004cd7acab8fbd8f77a75c5caa5893b9d51d3da885ab1ad`
- **复算锚定 commit**：`aabd983`（脚本修复后重跑产物字节级一致，见 §7）
- **校验引擎**：十神 `bazi_calculator.get_shishen`（支取本气）；干支关系 `benchmark/formatters/bazi_time_context.compute_branch_relation`；五行 `bazi_report_validator.GAN_WUXING` + 标准支五行表
- **零 API**，复算命令：

```powershell
.venv/Scripts/python docs/phase6/6c-premise/claim_contradiction_analysis.py
# 重新生成 docs/phase6/6c-premise/claim_contradiction_report.json，
# 其 SHA-256 应等于 c4c9ee8619e8d75a068673c3a58e7410870aff986430a56c83bcdd91011ac4d8
```

## 3. 结果

| 指标 | 错题组（171 行 / 69 case） | 对题组（69 行 / 38 case） |
|---|---|---|
| 含 ≥1 条矛盾的行占比 | 15.79%（27/171） | 14.49%（10/69） |
| 矛盾声明 / 声明总数 | 1.71%（32/1871） | 2.05%（15/731） |
| 排除 unverifiable 后声明级 | 1.73% | 2.07% |

> **样本结构注意**：错题组 69 case 与对题组 38 case **存在重叠**——同一 case 的不同 repeat 可分别答错、答对，两组 case 数相加不等于独立 case 数（全集为 80 个唯一 case）。行（240 = 80×3）为重复评测单元，非独立样本。

- 行级风险比 ≈ **1.09**；Fisher 双侧检验：行级 p = 1.0，声明级 p ≈ 0.623
- 行级风险比朴素 95% 区间约 **0.56–2.13**（暂时忽略 case 聚类）

## 4. 结论（措辞按外部审计修正）

> 在当前检测覆盖范围内，事实矛盾未表现出对错误答案的富集信号，且未达到 6C 启动的前提筛选门槛。**该结果不排除规则未覆盖的事实错误，也不构成对广义因果假设的统计否定**（240 行为 80 case 的重复运行，区间估计仍包含 2 倍效应）。

## 5. 覆盖边界（诚实声明）

- 纯正则抽取，仅覆盖**显式带干/支主语**的声明（约 11 条/行，其中五行属性断言约 64%）。
- "财星过旺""官杀混杂"等**不指名干支**的十神表述未进入抽取，也无法被规则引擎校验——属于该检测方式天然够不到的部分。
- unverifiable 约 1.3%（相破/暗合/天干相冲，项目关系表未定义），非主要不确定来源。
- 点估计未达到 2 倍筛选门槛，但**当前样本量和聚类结构不足以在统计意义上排除 2 倍效应**（朴素 95% 区间 0.56–2.13 仍包含 2）。

## 6. 决策

6C（claim verifier）不按"错题纠错器"定位启动。面向用户报告文本的事实一致性 verifier 转入独立产品 backlog（另立目标与指标），不属于准确率 Phase 6 范围。见 Phase 6 总收尾报告。

## 7. 复算验证记录（2026-08-10）

脚本初次归档时路径锚点错误（`REPO_ROOT` 指向 `docs/phase6`，无法 import 引擎模块），外部复审发现并修正为 `parents[3]`，输出路径改为脚本同目录。修正后从归档位置完整重跑：

- 重新生成的 `claim_contradiction_report.json` SHA-256 = `c4c9ee8619e8d75a068673c3a58e7410870aff986430a56c83bcdd91011ac4d8`，**与初版产物字节级一致**（分析结果确定性可复现）；
- 修正后脚本 SHA-256 = `4fcd8f97dea0659eaa23b03583f033e05a989eb38a191cb9768693869591fbf9`（§2 记录的是修正后版本）。
