---
name: scripts-safety
type: specific_files
globs: scripts/**
description: scripts/ 目录的安全与契约约束
---

本规则复述并细化 AGENTS.md 对 `scripts/` 的约束，不引入新豁免。

- 门禁与验证脚本（verify_smoke / verify_ci / verify_runtime / affected_tests）只增能力，不破坏既有 CLI 契约与退出码语义。
- 运行评测/编排脚本（phase6_*、run_*）前先确认预算参数（题集、repeat、模型）；不确定就先干跑或问。
- 实验指纹范围文件（_CODE_SCOPE 等）缺失时必须 fail-closed 抛异常终止，不得静默降级。
- `scripts/` 下的运行产物（日志、中间 JSON）不进 git 跟踪。
