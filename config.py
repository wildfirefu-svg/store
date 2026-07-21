"""
Central configuration for 玄机子 (XuanJiZi).

All values can be overridden via environment variables.
Import this module and use the uppercase names directly.
"""
import os
import sys


def _load_dotenv():
    """Lightweight .env loader. Reads KEY=VALUE pairs from
    project-root/.env into os.environ without overriding existing values."""
    if getattr(sys, 'frozen', False):
        root = os.path.dirname(sys.executable)
    else:
        root = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(root, ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except (FileNotFoundError, OSError):
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

# ---- Server ports ----
API_PORT = int(os.environ.get("BAZI_API_PORT", "8000"))
MCP_PORT = int(os.environ.get("BAZI_MCP_PORT", "8001"))

# ---- CORS ----
CORS_ORIGINS = os.environ.get("BAZI_CORS_ORIGINS", "")
# Default when unset: only local origins. Production must be explicit.
_DEFAULT_ORIGINS = "http://localhost:8000,http://127.0.0.1:8000,http://localhost"
CORS_ORIGIN_LIST = [o.strip() for o in (CORS_ORIGINS or _DEFAULT_ORIGINS).split(",") if o.strip()]

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

# ---- LLM Provider Config ----
# Provider priority: deepseek > anthropic > kimi > glm > qwen
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")

# Default models per provider
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "kimi-k2.6")
GLM_MODEL = os.environ.get("GLM_MODEL", "glm-5.2")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3.7-plus")

# API Base URLs
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1/messages")
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
GLM_BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/")

# ---- Lunar calendar ----
IZTRO_TIMEOUT = int(os.environ.get("BAZI_IZTRO_TIMEOUT", "10"))

# ---- Security ----
ENV = os.environ.get("BAZI_ENV", "development").lower()

# Maximum request body size in bytes (default 1 MB)
MAX_BODY_SIZE = int(os.environ.get("BAZI_MAX_BODY_SIZE", str(1024 * 1024)))

# ---- Logging ----
LOG_LEVEL = os.environ.get("BAZI_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.environ.get("BAZI_LOG_FILE", "")  # empty = stderr only
