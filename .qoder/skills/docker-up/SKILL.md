---
name: docker-up
description: 构建并启动玄机子 Docker 容器，包含健康检查验证
---
# Docker Skill — 玄机子

Build and run the BaZi API in Docker.

## Build + Start

```bash
docker compose up --build -d
```

Wait for healthy status, then verify.

## Verify

```bash
curl -s "http://localhost:${BAZI_API_PORT:-8000}/api/health"
```

Expected: `{"status":"ok","version":"1.0.0"}`

## View Logs

```bash
docker compose logs -f --tail=50
```

## Stop

```bash
docker compose down
```

## Rebuild from scratch (no cache)

```bash
docker compose build --no-cache
docker compose up -d
```

## Common issues

| Symptom | Fix |
|---------|-----|
| Configured API port already in use | `docker compose down` then retry, or change `BAZI_API_PORT` in `.env` |
| API key not found | Set the required API key variable in the project-root `.env`; Compose passes supported variables into the container |
| Health check fails | Check logs: `docker compose logs api` |
| Fonts missing in PDF | Ensure `fonts-noto-cjk` installed in Dockerfile |
