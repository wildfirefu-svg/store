# 测试调试报告 — 2026-06-17

## 范围

按用户要求"测试 + 调试 bug"，对当前主分支进行：

- 全量 pytest（含 e2e）
- 真实启动后端 + Playwright smoke 巡检
- 关键接口边界测试（404、405、路径穿越、限流、SSE 错误处理）

## 工具

新增三份本地调试脚本（运行结果写入 `.tmp/`，不提交产物）：

- [smoke_debug.py](file:///f:/project/agent/scripts/smoke_debug.py) — 启动后端 + Playwright 巡检主页、命主、聊天、工具栏、benchmark
- [edge_debug.py](file:///f:/project/agent/scripts/edge_debug.py) — 验证 404/405、路径穿越、限流
- [stream_debug.py](file:///f:/project/agent/scripts/stream_debug.py) — 验证 fake key 触发的 SSE 错误回退

## 全量测试

```text
262 passed, 1 skipped, 1 warning
```

包括上一轮的 BaziQA、安全、E2E、benchmark、stream parser 全部测试。

## Smoke 巡检结果

```json
{
  "errors": [],
  "network_failures": [],
  "checks": [
    {"endpoint": "/api/health", "status": 200, "ok": true},
    {"endpoint": "/api/charts", "status": 200, "ok": true},
    {"endpoint": "/api/benchmark/runs", "status": 200, "ok": true},
    {"endpoint": "/", "status": 200, "ok": true},
    {"endpoint": "/benchmark", "status": 200, "ok": true},
    {"endpoint": "chat-stream", "bubbles": 2, "ok": true}
  ],
  "console": []
}
```

无 console 错误、无网络失败、所有静态资源 200。

## 边界测试结果

```json
[
  {"name": "404", "got": 404},
  {"name": "GET /api/chart should be 405/404", "got": 405},
  {"name": "benchmark report 404", "got": 404},
  {"name": "benchmark report path traversal", "got": 404},
  {"name": "create chart", "got": 200},
  {"name": "rate-limit burst /api/health", "ok_count": 70, "rate_limited": 0}
]
```

`/api/health` 70 次未被限流是有意设计：健康检查不进入限流通道。  
路径穿越被 `os.path.commonpath` + 404 兜住，未泄露。  

## 发现并修复的 Bug

### Bug：`stream_chat` 在 `BAZI_API_RETRIES=0` 时静默 swallow 错误

**复现路径**：

1. 设置 `BAZI_API_RETRIES=0`
2. 提供任意无效的 `DEEPSEEK_API_KEY`（例如 `sk-fakekey-...`）
3. 通过 `/api/chat/stream` 触发 SSE

**修复前的实际输出**：

```text
event: tool
data: {"name": "四合出分析"}

event: reply
data: {"text": "正在调用玄机子 AI 分析…"}

event: done
```

前端只看到 "正在调用玄机子 AI 分析…"，然后无声结束，没有 ⚠️ 错误提示，也没有 fallback 文案。

**根因**：

[claude_api.py](file:///f:/project/agent/claude_api.py) 中

```python
for attempt in range(API_RETRIES):
    ...
```

当 `API_RETRIES=0` 时 `range(0)` 是空迭代器，整个 try/except 都不进入，函数直接 return，不再 yield 任何 `error` 事件。

**修复**：[claude_api.py](file:///f:/project/agent/claude_api.py#L401-L451)

```python
attempts = max(1, API_RETRIES)
for attempt in range(attempts):
    ...
    except urllib.error.HTTPError as e:
        ...
        if e.code == 429 and attempt == 0 and attempts > 1:
            time.sleep(2)
            continue
        yield {"type": "error", "text": ...}
```

至少尝试一次；只有在还能重试时才进入 retry 分支。

**修复后实际输出**：

```text
event: tool
event: reply  (正在调用玄机子 AI 分析…)
event: reply  (⚠️ API 错误 401: ...)
event: reply  (本地分析: 日主...，请配置 API Key 后重试)
event: done
```

前端能看到清晰错误提示和本地兜底分析。

**回归测试**：

新增 [test_stream_chat_yields_error_when_retries_zero](file:///f:/project/agent/tests/test_claude_api.py)：mock `urlopen` 抛 401，断言至少 yield 一个 `error` 事件。

## 影响评估

- 默认环境：`BAZI_API_RETRIES=2`，原代码也工作正常，此修复无行为变化。
- E2E 环境：之前已设 `BAZI_API_RETRIES=0`，一直暴露在这个 bug 里；E2E 因为 mock 了 SSE 路由所以没暴露。
- 任何运维通过环境变量临时关闭重试的场景，会立即受益。

## 验证

```powershell
python -m pytest -q                              # 262 passed, 1 skipped
python scripts\smoke_debug.py                    # errors: 0
python scripts\stream_debug.py                   # saw_error = True; saw_done = True
```

## 工作区状态

清理后只剩两个待提交改动：

- [claude_api.py](file:///f:/project/agent/claude_api.py)
- [tests/test_claude_api.py](file:///f:/project/agent/tests/test_claude_api.py)

以及三份新增调试脚本：

- [scripts/smoke_debug.py](file:///f:/project/agent/scripts/smoke_debug.py)
- [scripts/edge_debug.py](file:///f:/project/agent/scripts/edge_debug.py)
- [scripts/stream_debug.py](file:///f:/project/agent/scripts/stream_debug.py)
