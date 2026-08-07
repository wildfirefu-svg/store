---
name: quality-gate
description: 一键运行完整提交前门禁链（ruff → mypy → affected_tests → smoke）
trigger: 用户要求运行完整门禁、提交前检查、或需要一次性验证所有静态检查与聚焦测试时使用；单文件快速迭代优先用 test-suite skill
output: 门禁链逐段结果（每段 pass/fail + 关键输出），任一失败即停止并给出失败段的具体信息与修复方向
validation: 四段命令退出码均为 0；失败时输出具体失败项（lint 规则号 / 类型错误 / 断言信息），不输出笼统报错
---
# Quality Gate Skill — 玄机子

依次运行完整提交前门禁链，任一段失败即停止并报告。各段配置以 `ruff.toml`、`mypy.ini`、`scripts/affected_tests.py` 为准。

## Steps

1. Lint：`ruff check .`（基线 E9/F821，配置见 `ruff.toml`）。失败时输出具体规则号与文件位置。
2. Type check：`mypy`（增量白名单，配置见 `mypy.ini`）。失败时输出具体类型错误。
3. 受影响测试（两阶段流程，不得直接 `--run`）：
   1. 干跑：`python scripts/affected_tests.py`，只读测试映射。
   2. 若 stdout 含 `FULL_SUITE`：告知触发原因（tests/ 或 pytest.ini / requirements*.txt 变更）与预计范围（全量套件），等待用户明确批准；批准后执行 `python scripts/affected_tests.py --run`。无人值守或用户未回复：停在本段，不得默认为批准。
   3. 否则：直接执行 `python scripts/affected_tests.py --run`。
   4. 若干跑输出 `# no test mapping needed for changed files`（纯文档改动等）：本段直接通过，不执行 `--run`。
4. Smoke：`python scripts/verify_smoke.py`。

## 边界

- 与 test-suite skill 的分工：test-suite 按变更面选择测试范围；quality-gate 负责完整静态 + 动态门禁链。
- 不跳过任何段；不为"看起来对"省略第 3 段的用户批准。
- 与 quality-check skill 的分工：quality-check 负责领域质量审计（八字计算准确性/幻觉检测）；quality-gate 只跑工程门禁链。
