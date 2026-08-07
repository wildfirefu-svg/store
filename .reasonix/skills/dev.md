---
name: dev
description: 启动玄机子开发服务器并验证运行状态
trigger: 用户需要启动本地开发/调试服务器，或要求访问 Web UI、API docs、健康检查端点时使用；不需要运行测试或容器化部署
output: 后台运行的 Uvicorn 服务进程，以及 Web UI（http://localhost:8000）、API docs、健康检查三个访问地址
validation: 启动输出中出现 "Uvicorn running on" 或 "Started server process"，且 http://localhost:8000/api/health 可访问
---
# Dev Server Skill — 玄机子

Start the BaZi development server, wait for it to come up, and report the access URL.

## Steps

1. Run `python api_server.py` in the background using `run_background` with `waitSec: 8`
2. Look for "Uvicorn running on" or "Started server process" in the startup output
3. Once the server is up, report:
   - Web UI: http://localhost:8000
   - API docs: http://localhost:8000/docs
   - Health check: http://localhost:8000/api/health
4. Do NOT run tests or lints after starting — just confirm it's running

## Troubleshooting

- If port 8000 is in use:
  - On Windows PowerShell: `Get-NetTCPConnection -LocalPort 8000 | Select-Object -ExpandProperty OwningProcess`, then use `Stop-Process -Id <PID>` only after confirming the target process
  - On Linux/macOS: `lsof -i :8000`, then stop the confirmed process
- If imports fail: check that `requirements.txt` deps are installed
- If the server fails silently: check the API key variables in the project-root `.env`
