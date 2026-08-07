---
name: benchmark-conventions
type: specific_files
globs: benchmark/**
description: benchmark/ 模块职责边界与运行产物约束
---

本规则复述并细化 AGENTS.md 对 `benchmark/` 的约束，不引入新豁免。

- 模块职责：`runners/` 负责执行与 resume/ledger，`formatters/` 负责输入构造，`scorers/` 负责评分；改动跨模块时先读各模块既有入口。
- resume/ledger 子系统入口在 `benchmark/runners/resume_ledger.py`；断点恢复逻辑不得绕过 ledger 直写。
- `benchmark/outputs/` 是运行产物目录，不得手改其中文件；评测结论以 report/gate 产物为证。
- `benchmark/datasets/*.jsonl` 是被跟踪的数据产物，禁改（与 AGENTS.md §4 同步）。
