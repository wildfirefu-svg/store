# CLAUDE.md

Claude Code 专用补充。**通用规则全部在 [AGENTS.md](AGENTS.md)（中文，权威版本）**：最高原则、技术栈、常用命令、验证入口、Git 与沟通风格都以它为准。冲突时以 AGENTS.md 和用户显式指令为准。

本文件只记录 Claude 特有的工作方式，不重复通用规则。

## Claude 专用补充

- **探索用子代理**：大范围读文件/定位代码时用 subagent（Task/Agent 工具），保持主上下文干净。
- **上下文是稀缺资源**：同一问题连续两次纠正仍失败就停下，总结已学到的内容，建议用户开新会话并给更明确的提示。
- **UI 改动要视觉验证**：改动前后各截图，描述可见差异，别只看代码。
- **有 CLI 就用 CLI**：`gh`、`docker` 等工具存在时优先用，比读文档或未鉴权打 API 更省上下文。
- **提交署名**：不加 `Co-Authored-By: Claude`，除非项目明确要求。
- **技能**：本机 Superpowers 技能（`brainstorming`、`systematic-debugging`、`writing-plans` 等）命中时先读其 `SKILL.md`；路由细节见 AGENTS.md 第 10 节。

## Project Learnings（Claude）

- （空）
