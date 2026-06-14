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
curl -s http://localhost:8000/api/health
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
| Port 8000 already in use | `docker compose down` then retry, or change port in `docker-compose.yml` |
| API key not found | Ensure `.anthropic_key` or `.deepseek_key` exists in project root; Docker mounts it read-only |
| Health check fails | Check logs: `docker compose logs app` |
| Fonts missing in PDF | Ensure `fonts-noto-cjk` installed in Dockerfile |
