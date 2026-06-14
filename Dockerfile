# ================================================================
# 玄机子 — Multi-stage Docker build
# Stage 1: install system deps + pip packages
# Stage 2: copy app + runtime deps only → smaller final image
# ================================================================

FROM python:3.11-slim AS builder

# Install system deps needed for PDF fonts (fonts-noto-cjk)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps to a user-local prefix
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ── Final stage ──
FROM python:3.11-slim

# Copy system fonts from builder
COPY --from=builder /usr/share/fonts /usr/share/fonts
RUN fc-cache -f 2>/dev/null || true

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# Copy application (excluding items in .dockerignore)
COPY . .

# Build knowledge base (SQLite FTS5) — must succeed for full functionality
RUN python -c "import sys; sys.path.insert(0, 'knowledge-base'); \
    from bazi_kb import BaziKnowledgeBase; \
    kb = BaziKnowledgeBase(); \
    kb.build(); \
    print(f'KB built: {kb.stats()}'); \
    kb.close()"

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["python", "-u", "api_server.py"]
