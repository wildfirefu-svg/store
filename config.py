"""
Central configuration for 玄机子 (XuanJiZi).

All values can be overridden via environment variables.
Import this module and use the uppercase names directly.
"""
import os

# ---- Server ports ----
API_PORT = int(os.environ.get("BAZI_API_PORT", "8000"))
MCP_PORT = int(os.environ.get("BAZI_MCP_PORT", "8001"))

# ---- CORS ----
CORS_ORIGINS = os.environ.get("BAZI_CORS_ORIGINS", "*")
# Split comma-separated origins into a list
CORS_ORIGIN_LIST = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

# ---- Rate limiting (per-IP sliding window) ----
# Format: "path_prefix:max_requests,window_seconds"
# Default applied when no specific prefix matches.
_RATE_LIMIT_RAW = os.environ.get(
    "BAZI_RATE_LIMITS",
    "default:120,60 /api/chat/stream:30,60 /api/analyze/pdf:10,60"
)
RATE_LIMITS = {}
for entry in _RATE_LIMIT_RAW.split():
    if ":" not in entry:
        continue
    prefix, spec = entry.split(":", 1)
    max_req, window = spec.split(",")
    RATE_LIMITS[prefix] = (int(max_req), int(window))

# Paths exempt from rate limiting (comma-separated)
RATE_LIMIT_EXEMPT_RAW = os.environ.get(
    "BAZI_RATE_LIMIT_EXEMPT",
    "/static,/api/health,/,/test,/tools,/card,/api/card,/favicon.ico"
)
RATE_LIMIT_EXEMPT = set(p.strip() for p in RATE_LIMIT_EXEMPT_RAW.split(",") if p.strip())

RATE_LIMIT_CLEAN_INTERVAL = int(os.environ.get("BAZI_RATE_CLEAN_INTERVAL", "300"))

# ---- Cache ----
CHART_CACHE_SIZE = int(os.environ.get("BAZI_CHART_CACHE_SIZE", "128"))

# ---- LLM / AI ----
MAX_TOKENS = int(os.environ.get("BAZI_MAX_TOKENS", "16384"))
DEFAULT_TEMPERATURE = float(os.environ.get("BAZI_TEMPERATURE", "0.3"))
DEEPSEEK_THINKING = os.environ.get("DEEPSEEK_THINKING", "disabled")
API_RETRIES = int(os.environ.get("BAZI_API_RETRIES", "2"))

# ---- Lunar calendar ----
IZTRO_TIMEOUT = int(os.environ.get("BAZI_IZTRO_TIMEOUT", "10"))

# ---- Security ----
ENV = os.environ.get("BAZI_ENV", "development").lower()
ALLOW_QUERY_API_KEY = os.environ.get(
    "BAZI_ALLOW_QUERY_API_KEY",
    "1" if ENV != "production" else "0",
) in ("1", "true", "True", "yes", "YES")

# Maximum request body size in bytes (default 1 MB)
MAX_BODY_SIZE = int(os.environ.get("BAZI_MAX_BODY_SIZE", str(1024 * 1024)))

# ---- Logging ----
LOG_LEVEL = os.environ.get("BAZI_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.environ.get("BAZI_LOG_FILE", "")  # empty = stderr only
