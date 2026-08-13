# knowledge_audit 汇总（P8-2B）

- 题数：35；知识项总数：171
- 分母对账（知识项级）：通过
- prompt_fingerprint：`e136106a8e8730020eb3631b32b6c24424beaf73f5f0fcbc82a274e2120cb22d`

## 知识项级 gap 分布

- 检索不可见：112
- 注入缺失：39
- 计算缺失：19
- 知识缺失：1

## 题级 primary_gap 分布

- 计算缺失：19
- 检索不可见：16

## 口径说明

- 五类与 undetermined 分列；题级多标签（gap_classes）+ 知识项级双口径汇总。
- 计算项映射：no_interface→计算缺失；missing_input→undetermined(input_missing)；semantic_gap→undetermined；computable 且未注入→注入缺失；computable 且已注入→模型未利用。
- doctrine 项：KB 快照/classic_texts 冻结版核查命中且 prompt 未注入→检索不可见；命中且已注入→模型未利用；双源零命中→知识缺失。
- classic_texts 冻结检索总命中：7（quarantine 命中只作佐证）。
