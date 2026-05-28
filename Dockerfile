FROM python:3.11-slim

WORKDIR /app

# Install system deps for PDF generation (weasyprint deps optional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Build knowledge base (SQLite FTS5)
RUN python -c "import sys; sys.path.insert(0, 'knowledge-base'); \
    from bazi_kb import BaziKnowledgeBase; \
    kb = BaziKnowledgeBase(); kb.build(); kb.close()" 2>/dev/null || true

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["python", "-u", "api_server.py"]
