---
name: dev
description: 启动玄机子开发服务器并验证运行状态
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
