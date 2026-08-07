---
name: core-boundary
type: always_apply
description: 玄机子核心代码边界、禁改数据产物与验证入口选择规则
---

本规则复述 AGENTS.md §4 / §9 的约束，不引入新豁免。规则与 AGENTS.md 不一致时，以删除或修正本规则为准，不得放宽 AGENTS.md。

## 核心代码边界

`bazi_calculator.py` 是排盘核心引擎，`scripts/` 含验证与门禁脚本；两者变更受核心代码边界约束，动手前先读对应文件与调用方。

## 禁改清单（被跟踪的数据产物，与 AGENTS.md §4 同步）

- `knowledge-base/*.json`
- `tests/case_db.json`
- `data/*.json`
- `benchmark/datasets/*.jsonl`

## 验证入口选择（与 AGENTS.md §9 入口表同步）

改动后按要验证的声明选择对应验证入口，不要求每次改动运行全部脚本：

| 要验证的声明 | 入口 |
|---|---|
| focused smoke tests passed | `python scripts/verify_smoke.py` |
| CI workflow configuration | `python scripts/verify_ci.py` |
| runtime behavior | `python scripts/verify_runtime.py` |
| 变更范围的最小测试集 | `python scripts/affected_tests.py`（先干跑；FULL_SUITE 需用户批准后再 `--run`） |
