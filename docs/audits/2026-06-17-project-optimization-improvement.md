# Project Optimization Improvement Report

## 改进日期

2026-06-17

## 输入文档

- `docs/superpowers/plans/2026-06-17-project-optimization-implementation.md`
- `docs/audits/2026-06-17-project-audit.md`

## 本轮目标

补齐项目优化实施计划中尚未落地的稳定性、安全、诊断、测试隔离和质量评测文档工作，并在不覆盖前序 BaziQA / E2E / SSE 改动的前提下完成验证。

## 已完成改进

### 1. 生产鉴权安全开关

- `config.py` 新增：
  - `ENV`
  - `ALLOW_QUERY_API_KEY`
- `api_server.py` 鉴权中间件支持在生产环境禁用 `?api_key=`。
- 401 文案改为只推荐 `Authorization: Bearer`。
- 新增测试覆盖：
  - query key 被禁用时返回 401。
  - Bearer token 仍可通过。
  - query key 显式启用时仍兼容本地开发。

### 2. Provider-aware AI 错误诊断

- `_generate_fallback()` 文案改为同时提示 DeepSeek 与 Anthropic。
- fallback 文案加入 key、余额/额度、网络/API 可达性排查方向。
- 新增 API 单测覆盖 `DEEPSEEK_API_KEY`、`ANTHROPIC_API_KEY` 和本地分析文案。

### 3. 报告构建鲁棒性测试

- 为 `render_chart_table()` 增加空 `da_yun` 回归测试。
- 确认空大运时输出 `起运：N/A` 与 `当前大运：N/A`，不再抛出 `IndexError`。

### 4. 仓库产物与测试输出策略

- `.gitignore` 补充：
  - `benchmark/outputs/test_report_*.md`
  - `benchmark/reports/__pycache__/`
  - `quality/model_quality_report.json`
- 保留 `build/`、`dist/` 忽略规则。
- 未执行 `git rm --cached build dist`，因为计划要求该步骤需项目 owner 确认。

### 5. 长期运维文档

新增：

- `docs/AI_TROUBLESHOOTING.md`
- `docs/SECURITY.md`
- `docs/QUALITY_EVALUATION.md`

这些文档分别覆盖 AI 服务连接排查、生产安全配置、八字判断质量评测与回归门禁。

## 前序已完成并在本轮确认的计划项

以下内容在上一轮改进中已经落地，本轮未重复重写：

- E2E 自动启动临时 uvicorn 服务。
- E2E mock chat SSE，避免真实模型调用。
- SSE parser 改为跨 chunk 状态机。
- AI 回复最终渲染移除 raw `innerHTML`。
- Benchmark / BaziQA 评测链路初步建立。
- Dashboard 展示按年份、领域聚合指标。

## 验证结果

本轮执行并通过：

```powershell
python -m pytest tests/test_rate_limit.py tests/test_api.py::test_generate_fallback_mentions_deepseek_and_anthropic tests/test_report_builder.py::TestRenderChartTable::test_handles_empty_dayun -q
```

全量验证：

```powershell
python -m pytest -q
```

结果：

```text
259 passed, 1 warning
```

语法检查：

```powershell
python -m py_compile config.py api_server.py report_builder.py tests\test_rate_limit.py tests\test_api.py tests\test_report_builder.py
node --check static\js\api.js
node --check static\js\stream.js
node --check static\js\benchmark-dashboard.js
```

## 尚未执行的高风险操作

未执行以下操作：

```powershell
git rm -r --cached build dist
```

原因：该操作会把大量已跟踪打包产物从 Git 索引移除，计划中明确要求先由项目 owner 确认 release artifact 策略。

## 建议下一步

1. 确认是否从 Git 中移除 `build/` 和 `dist/` 已跟踪产物。
2. 若确认移除，执行 `git rm -r --cached build dist` 并单独提交。
3. 将本轮改进纳入一次安全/稳定性提交。
4. 后续 CI 可增加：
   - `python -m pytest -q`
   - `node --check static/js/api.js static/js/stream.js static/js/benchmark-dashboard.js`
   - `git status --short` 测试污染检查。
