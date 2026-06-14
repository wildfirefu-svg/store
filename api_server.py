#!/usr/bin/env python3
"""
BaZi Analysis API Server — FastAPI REST layer.
Exposes all tools as HTTP endpoints.

Usage:
    python api_server.py
    uvicorn api_server:app --reload --port 8000
    Open http://localhost:8000/docs for Swagger UI.
"""

import json, os, sys, hashlib, importlib.util, threading, logging
from datetime import date
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
import asyncio, time, calendar
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge-base'))

from bazi_calculator import (
    calculate_true_solar_time, compute_chart,
)
from lunar_calendar import lunar_to_solar, solar_to_lunar as _s2l
from auto_analyzer import auto_analyze as _auto_analyze

from claude_api import stream_chat as _stream_claude, ANTHROPIC_API_KEY
import data_store
from config import (
    API_PORT, CORS_ORIGIN_LIST, CORS_ORIGINS,
    RATE_LIMITS, RATE_LIMIT_EXEMPT, RATE_LIMIT_CLEAN_INTERVAL,
    CHART_CACHE_SIZE, MAX_BODY_SIZE, LOG_LEVEL, LOG_FILE,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename=LOG_FILE or None,
)
logger = logging.getLogger('api')

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info(f'BaZi Analysis API starting')
    yield
    # Shutdown
    logger.info("Shutting down...")
    chart_cache._cache.clear()
    with _pdf_jobs_lock:
        for job in list(_pdf_jobs.values()):
            path = job.get('pdf_path', '')
            if path and os.path.isfile(path):
                try: os.unlink(path)
                except Exception: pass
        _pdf_jobs.clear()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="BaZi Analysis API",
    description="八字命理分析 REST API — 排盘、择日、流年、取名、案例检索、知识库搜索",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGIN_LIST if CORS_ORIGIN_LIST else ["*"],
                    allow_methods=["*"], allow_headers=["*"])

# ============================================================
# RATE LIMITER — per-IP sliding window
# ============================================================

# Limits loaded from config.py (env-overridable)
_RATE_LIMITS = RATE_LIMITS
_RATE_LIMIT_EXEMPT = RATE_LIMIT_EXEMPT
_hits = defaultdict(list)  # ip -> [timestamps]
_hits_lock = threading.Lock()
_CLEAN_INTERVAL = RATE_LIMIT_CLEAN_INTERVAL
_last_clean = time.time()


def _clean_old_hits(now):
    global _last_clean
    if now - _last_clean < _CLEAN_INTERVAL:
        return
    _last_clean = now
    with _hits_lock:
        stale = []
        for ip, timestamps in _hits.items():
            timestamps[:] = [t for t in timestamps if now - t < 120]
            if not timestamps:
                stale.append(ip)
        for ip in stale:
            del _hits[ip]


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path

    # Skip rate limiting for static files, health, etc.
    for exempt in _RATE_LIMIT_EXEMPT:
        if path == exempt or path.startswith(exempt + "/") or path.startswith(exempt + "?"):
            return await call_next(request)

    now = time.time()
    _clean_old_hits(now)

    # Determine limit for this path
    max_req, window = _RATE_LIMITS.get("default")
    for prefix, limit in _RATE_LIMITS.items():
        if prefix != "default" and path.startswith(prefix):
            max_req, window = limit
            break

    # Client IP
    ip = request.client.host if request.client else "unknown"
    with _hits_lock:
        timestamps = _hits[ip]
        timestamps[:] = [t for t in timestamps if now - t < window]

        if len(timestamps) >= max_req:
            retry_after = int(window - (now - timestamps[0]))
            _inc_metric('rate_limit_hits')
            return JSONResponse(
                status_code=429,
                content={"detail": f"请求过于频繁，请 {retry_after} 秒后重试"},
                headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(max_req)},
            )

        timestamps.append(now)
    _inc_metric('requests_total')
    response = await call_next(request)
    return response


# ============================================================
# AUTH MIDDLEWARE — optional API key protection
# ============================================================

def _load_auth_key():
    """Load API key from env var or local file. Empty string = auth disabled."""
    key = os.environ.get("BAZI_API_KEY", "")
    if key:
        return key
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bazi_api_key")
    try:
        with open(key_file, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

_BAZI_API_KEY = _load_auth_key()

# Public paths that never require auth
_PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/", "/test", "/tools"}

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not _BAZI_API_KEY:
        return await call_next(request)

    path = request.url.path

    # Public paths — always allow
    if path in _PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)

    # Check Bearer token in Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token == _BAZI_API_KEY:
            return await call_next(request)

    # Check query parameter
    if request.query_params.get("api_key") == _BAZI_API_KEY:
        return await call_next(request)

    return JSONResponse(
        status_code=401,
        content={"detail": "需要有效的 API Key。请在 Authorization 头中提供 Bearer token，或通过 ?api_key= 参数传递。"},
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---- Request body size limit (DoS protection) ----
@app.middleware("http")
async def body_size_limit_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header"},
            )
        if length > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": f"请求体过大，最大允许 {MAX_BODY_SIZE // 1024} KB"},
            )
    return await call_next(request)


# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")

# ============================================================
# MODELS
# ============================================================

class BirthInfo(BaseModel):
    year: int = Field(..., ge=1900, le=2100)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=31)
    hour: int = Field(0, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    gender: str = Field("male", pattern="^(male|female)$")
    location: str = Field("Beijing")
    use_solar_time: bool = Field(False, description="If True, birth.hour/minute already adjusted to true solar time, skip server adjustment")

    @field_validator('day')
    @classmethod
    def validate_day(cls, v, info):
        """Reject impossible dates like February 30."""
        month = info.data.get('month')
        year = info.data.get('year')
        if month and year:
            max_day = calendar.monthrange(year, month)[1]
            if v > max_day:
                raise ValueError(f'{year}年{month}月最多{max_day}天，不能是{v}日')
        return v

class ChartCache:
    def __init__(self, max_size=128):
        self._cache = {}
        self._max_size = max_size

    def _make_key(self, birth: BirthInfo) -> str:
        raw = f"{birth.year}{birth.month}{birth.day}{birth.hour}{birth.minute}{birth.gender}{birth.location}{birth.use_solar_time}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def get_or_create(self, birth: BirthInfo):
        key = self._make_key(birth)
        if key in self._cache:
            return self._cache[key], key

        chart = compute_chart(
            birth.year, birth.month, birth.day,
            birth.hour, birth.minute, birth.gender, birth.location,
            use_solar_time=birth.use_solar_time,
        )
        chart['chart_id'] = key

        if len(self._cache) >= self._max_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = chart
        return chart, key

chart_cache = ChartCache(max_size=CHART_CACHE_SIZE)

# ============================================================
# HELPERS: Import knowledge-base modules (hyphenated dirs)
# ============================================================

_tool_cache = {}

def _import_tool(module_name, file_path):
    """Cached lazy import for any module. Adds file's parent dir to sys.path."""
    if module_name in _tool_cache:
        return _tool_cache[module_name]
    # Ensure the module's parent directory is on sys.path for relative imports
    parent_dir = os.path.dirname(os.path.abspath(file_path))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None:
        raise ImportError(f"Cannot find module {module_name} at {file_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _tool_cache[module_name] = mod
    return mod

def _get_zeri():
    return _import_tool('zeri', 'knowledge-base/zeri.py')

def _get_liunian():
    return _import_tool('liunian_calendar', 'knowledge-base/liunian_calendar.py')

def _get_name_analysis():
    return _import_tool('name_analysis', 'knowledge-base/name_analysis.py')

def _get_case_retrieval():
    return _import_tool('case_retrieval', 'knowledge-base/case_retrieval.py')

def _get_kb():
    kb_mod = _import_tool('bazi_kb', 'knowledge-base/bazi_kb.py')
    return kb_mod.BaziKnowledgeBase()

# ============================================================
# FRONTEND ROUTES
# ============================================================

@app.get("/", response_class=HTMLResponse)
def frontend_index():
    """首页 — 八字排盘输入"""
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/test", response_class=HTMLResponse)
def frontend_test():
    with open("templates/test_minimal.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/tools", response_class=HTMLResponse)
def frontend_tools():
    """自助工具页面"""
    with open("templates/tools.html", "r", encoding="utf-8") as f:
        return f.read()

# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ============================================================
# PROMETHEUS METRICS
# ============================================================

_metrics = {
    'requests_total': 0,
    'rate_limit_hits': 0,
    'charts_created': 0,
    'charts_cached': 0,
    'pdf_jobs_total': 0,
    'pdf_jobs_active': 0,
}
_metrics_lock = threading.Lock()

def _inc_metric(name, delta=1):
    with _metrics_lock:
        _metrics[name] = _metrics.get(name, 0) + delta


@app.get("/api/metrics")
def metrics():
    """Prometheus-compatible metrics endpoint."""
    with _metrics_lock:
        req_total = _metrics['requests_total']
        rl_hits = _metrics['rate_limit_hits']
        charts = _metrics['charts_created']
        cached = len(chart_cache._cache)
        pdf_total = _metrics['pdf_jobs_total']
        pdf_active = len(_pdf_jobs)
    lines = [
        '# HELP bazi_requests_total Total HTTP requests served',
        '# TYPE bazi_requests_total counter',
        f'bazi_requests_total {req_total}',
        '# HELP bazi_rate_limit_hits_total Total rate limit rejections',
        '# TYPE bazi_rate_limit_hits_total counter',
        f'bazi_rate_limit_hits_total {rl_hits}',
        '# HELP bazi_charts_created_total Total charts created',
        '# TYPE bazi_charts_created_total counter',
        f'bazi_charts_created_total {charts}',
        '# HELP bazi_charts_cached Current charts in memory cache',
        '# TYPE bazi_charts_cached gauge',
        f'bazi_charts_cached {cached}',
        '# HELP bazi_pdf_jobs_active Current active PDF generation jobs',
        '# TYPE bazi_pdf_jobs_active gauge',
        f'bazi_pdf_jobs_active {pdf_active}',
    ]
    return Response('\n'.join(lines) + '\n', media_type='text/plain')

@app.post("/api/chart")
def calculate_chart(birth: BirthInfo):
    """排盘 — calculate full BaZi chart, persist to local DB"""
    chart, chart_id = chart_cache.get_or_create(birth)
    _inc_metric('charts_created')
    # Auto-save to local database for persistence
    try:
        name = birth.location or '命主'
        data_store.save_chart(
            chart_id=chart_id,
            name=name,
            birth_info={'year': birth.year, 'month': birth.month, 'day': birth.day,
                        'hour': birth.hour, 'minute': birth.minute,
                        'gender': birth.gender, 'location': birth.location},
            chart_data=chart
        )
    except Exception as e:
        logger.warning(f"Failed to persist chart {chart_id}: {e}", exc_info=True)
    return chart


# ============================================================
# PERSISTENCE API — chart list, chat history, reports
# ============================================================

class SaveChartRequest(BaseModel):
    chart_id: str
    name: str = ""
    birth_info: dict = {}
    chart_data: dict = {}

class ChatMessageRequest(BaseModel):
    role: str
    text: str
    tool: Optional[str] = None

class SaveReportRequest(BaseModel):
    chart_id: str
    tab_id: str
    content: str


@app.get("/api/charts")
def api_list_charts():
    """List all saved charts from local database."""
    try:
        return data_store.list_charts()
    except Exception:
        return []


@app.get("/api/charts/{chart_id}/data")
def api_get_chart_data(chart_id: str):
    """Get full chart data from local database."""
    data = data_store.get_chart(chart_id)
    if not data:
        raise HTTPException(404, "Chart not found in local storage")
    return data


@app.post("/api/charts/save")
def api_save_chart(req: SaveChartRequest):
    """Save/update chart in local database (for frontend sync)."""
    try:
        data_store.save_chart(req.chart_id, req.name, req.birth_info, req.chart_data)
        # Invalidate memory cache so next read gets updated data
        chart_cache._cache.pop(req.chart_id, None)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/charts/{chart_id}")
def api_delete_chart(chart_id: str):
    """Delete chart + history + reports from local database."""
    try:
        data_store.delete_chart(chart_id)
        # Also clear from memory cache
        chart_cache._cache.pop(chart_id, None)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/charts/{chart_id}/history")
def api_get_chat_history(chart_id: str):
    """Get chat history for a chart."""
    try:
        return data_store.get_chat_history(chart_id)
    except Exception:
        return []


@app.post("/api/charts/{chart_id}/history")
def api_append_chat_message(chart_id: str, req: ChatMessageRequest):
    """Append a chat message to persistent storage."""
    try:
        data_store.append_chat_message(chart_id, req.role, req.text, req.tool)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/charts/{chart_id}/reports")
def api_get_reports(chart_id: str):
    """Get all saved report tabs for a chart."""
    try:
        return data_store.get_reports(chart_id)
    except Exception:
        return {}


@app.post("/api/charts/reports/save")
def api_save_report(req: SaveReportRequest):
    """Save a report tab to persistent storage."""
    try:
        data_store.save_report(req.chart_id, req.tab_id, req.content)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/solar-time")
def get_solar_time(birth: BirthInfo):
    """Get true solar time adjusted hour/minute for preview"""
    adj_h, adj_m, adj_minutes, method = calculate_true_solar_time(
        birth.hour, birth.minute, birth.location, birth.month
    )
    return {
        'original_hour': birth.hour,
        'original_minute': birth.minute,
        'adjusted_hour': adj_h,
        'adjusted_minute': adj_m,
        'adjustment_minutes': adj_minutes,
        'method': method,
    }

class LunarDate(BaseModel):
    year: int = Field(..., ge=1900, le=2100)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=30)
    is_leap: bool = False

@app.post("/api/lunar-to-solar")
def convert_lunar_to_solar(ld: LunarDate):
    """Convert lunar calendar date to solar date."""
    sy, sm, sd = lunar_to_solar(ld.year, ld.month, ld.day, ld.is_leap)
    return {'solar_year': sy, 'solar_month': sm, 'solar_day': sd}

@app.get("/api/chart/{chart_id}")
def get_chart(chart_id: str):
    """Get chart by ID — from memory cache or persistent DB."""
    chart = _get_chart(chart_id)
    if chart:
        return chart
    raise HTTPException(404, "Chart not found. POST /api/chart first.")

class ZeriRequest(BaseModel):
    chart_id: str
    year: int = None
    month: int = None
    purpose: str = "通用"
    top_n: int = 5
    xishen: str = None

@app.post("/api/tools/zeri")
def tool_zeri(req: ZeriRequest):
    """择日 — personalized auspicious date selection"""
    chart_id = req.chart_id
    chart = _get_chart(chart_id) if chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id from POST /api/chart")

    zeri = _get_zeri()
    year = req.year or date.today().year
    month = req.month or date.today().month
    purpose = req.purpose or '通用'
    top_n = req.top_n or 5
    xishen = req.xishen
    xishen_list = [x.strip() for x in xishen.split(',')] if xishen else None

    dates = zeri.find_good_dates(year, month, purpose, top_n, chart, xishen_list)
    return {'purpose': purpose, 'year': year, 'month': month, 'dates': dates}

class LiunianRequest(BaseModel):
    chart_id: str
    target_year: int = None

@app.post("/api/tools/liunian")
def tool_liunian(req: LiunianRequest):
    """流年日历 — 12-month fortune calendar"""
    chart_id = req.chart_id
    chart = _get_chart(chart_id) if chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id")

    lc = _get_liunian()
    target_year = req.target_year or date.today().year
    birth = chart.get('birth_info', {})
    by = birth.get('year', target_year - 35)
    bm = birth.get('month', 1)
    bd = birth.get('day', 1)
    bh = birth.get('hour', 8)
    bg = birth.get('gender', 'male')
    cal = lc.generate_year_calendar(by, bm, bd, bh, bg, target_year, chart)
    return cal

class NameEvalRequest(BaseModel):
    chart_id: str
    name: str
    gender: str = "male"

@app.post("/api/tools/name/eval")
def tool_name_eval(req: NameEvalRequest):
    """名字评测 — evaluate existing name against chart"""
    chart = _get_chart(req.chart_id) if req.chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id")
    na = _get_name_analysis()
    return na.evaluate_name(req.name[0], req.name[1:], chart, req.gender)

class NameGenRequest(BaseModel):
    chart_id: str
    surname: str = "张"
    gender: str = "male"
    top_n: int = 5

@app.post("/api/tools/name/gen")
def tool_name_gen(req: NameGenRequest):
    """取名推荐 — generate name suggestions matching chart"""
    chart = _get_chart(req.chart_id) if req.chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id")
    na = _get_name_analysis()
    return na.generate_names(req.surname, chart, req.gender, req.top_n)

class CaseSearchRequest(BaseModel):
    chart_id: str
    top_n: int = 5

@app.post("/api/tools/case/search")
def tool_case_search(req: CaseSearchRequest):
    """案例检索 — find similar benchmark cases"""
    chart = _get_chart(req.chart_id) if req.chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id")
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(chart, f, ensure_ascii=False)
        tmp = f.name
    try:
        top_n = req.top_n
        cr = _get_case_retrieval()
        retriever = cr.CaseRetriever() if hasattr(cr, 'CaseRetriever') else None
        if retriever:
            results = retriever.retrieve(tmp, top_n, mode='auto')
        else:
            results = cr.simple_match(cr.extract_case_features(tmp), top_n)
        return results
    finally:
        os.unlink(tmp)

class AnalyzeRequest(BaseModel):
    chart_id: str
    mode: int = Field(1, ge=1, le=7)
    conclusions: dict = None  # Agent-generated analysis conclusions
    template: str = Field("dark", pattern="^(dark|modern|scroll|night)$")

@app.post("/api/analyze")
def analyze_report(req: AnalyzeRequest):
    """分析并生成报告 — takes Agent conclusions JSON + chart → renders markdown"""
    chart = _get_chart(req.chart_id) if req.chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id")

    import tempfile
    # Write chart to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(chart, f, ensure_ascii=False)
        chart_tmp = f.name

    # Use default conclusions if none provided
    conclusions = req.conclusions or _auto_analyze(chart)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(conclusions, f, ensure_ascii=False)
        concl_tmp = f.name

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        report_tmp = f.name

    try:
        rb = _import_tool('report_builder', 'report_builder.py')
        rb.build_report(chart_tmp, req.mode, concl_tmp, report_tmp)

        with open(report_tmp, 'r', encoding='utf-8') as f:
            report_md = f.read()

        return {'mode': req.mode, 'report': report_md}
    finally:
        os.unlink(chart_tmp); os.unlink(concl_tmp); os.unlink(report_tmp)


# ============================================================
# ASYNC PDF JOB SYSTEM
# ============================================================

_pdf_jobs = {}           # job_id -> {status, pdf_path, filename, error, created_at}
_pdf_jobs_lock = threading.Lock()
_PDF_JOB_TTL = 3600      # auto-clean jobs older than 1 hour


def _clean_old_pdf_jobs(now):
    with _pdf_jobs_lock:
        stale = [jid for jid, j in _pdf_jobs.items()
                 if now - j.get('created_at', now) > _PDF_JOB_TTL]
        for jid in stale:
            path = _pdf_jobs[jid].get('pdf_path', '')
            if path and os.path.isfile(path):
                try: os.unlink(path)
                except: pass
            del _pdf_jobs[jid]


def _run_pdf_job(job_id, chart, conclusions, mode, template):
    """Run PDF generation in a thread (blocking I/O + subprocess)."""
    import tempfile, subprocess
    chart_tmp = concl_tmp = md_tmp = pdf_tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(chart, f, ensure_ascii=False)
            chart_tmp = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(conclusions, f, ensure_ascii=False)
            concl_tmp = f.name
        md_tmp = os.path.join(tempfile.gettempdir(), f'report_{job_id}.md')
        pdf_tmp = os.path.join(tempfile.gettempdir(), f'report_{job_id}.pdf')

        rb = _import_tool('report_builder', 'report_builder.py')
        rb.build_report(chart_tmp, mode, concl_tmp, md_tmp)

        cmd = [sys.executable, "report_to_pdf.py", md_tmp, "-o", pdf_tmp, "-t", template or 'dark']
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode != 0:
            raise RuntimeError(ret.stderr[-500:])

        with _pdf_jobs_lock:
            _pdf_jobs[job_id] = {
                'status': 'done',
                'pdf_path': pdf_tmp,
                'filename': f'report_{job_id}.pdf',
                'created_at': _pdf_jobs.get(job_id, {}).get('created_at', time.time()),
            }
    except Exception as e:
        with _pdf_jobs_lock:
            _pdf_jobs[job_id] = {
                'status': 'error',
                'error': str(e)[:500],
                'created_at': _pdf_jobs.get(job_id, {}).get('created_at', time.time()),
            }
        for fp in [pdf_tmp]:
            if fp and os.path.isfile(fp):
                try: os.unlink(fp)
                except: pass
    finally:
        for fp in [chart_tmp, concl_tmp, md_tmp]:
            if fp and os.path.isfile(fp):
                try: os.unlink(fp)
                except: pass


@app.post("/api/analyze/pdf")
async def analyze_pdf_async(req: AnalyzeRequest):
    """生成PDF报告（异步）— 立即返回 job_id，不阻塞请求"""
    chart = _get_chart(req.chart_id) if req.chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id")

    conclusions = req.conclusions or _auto_analyze(chart)
    job_id = hashlib.md5(f"{req.chart_id}{time.time()}".encode()).hexdigest()[:12]

    now = time.time()
    _clean_old_pdf_jobs(now)
    with _pdf_jobs_lock:
        _pdf_jobs[job_id] = {'status': 'processing', 'created_at': now}

    loop = asyncio.get_event_loop()
    _inc_metric('pdf_jobs_total')
    loop.run_in_executor(None, _run_pdf_job, job_id, chart, conclusions, req.mode, req.template)

    return {'job_id': job_id, 'status': 'processing',
            'check_url': f'/api/jobs/{job_id}'}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    """查询 PDF 生成任务状态"""
    with _pdf_jobs_lock:
        job = _pdf_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found or expired")
    return {'job_id': job_id, 'status': job['status'],
            'error': job.get('error'),
            'download_url': f'/api/jobs/{job_id}/download' if job['status'] == 'done' else None}


@app.get("/api/jobs/{job_id}/download")
def job_download(job_id: str):
    """下载已完成的 PDF 报告"""
    with _pdf_jobs_lock:
        job = _pdf_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found or expired")
    if job['status'] != 'done':
        raise HTTPException(409, f"Job not ready (status: {job['status']})")
    if not job.get('pdf_path') or not os.path.isfile(job['pdf_path']):
        raise HTTPException(500, "PDF file missing")

    from fastapi.responses import FileResponse
    return FileResponse(job['pdf_path'], media_type='application/pdf',
                        filename=job.get('filename', f'report_{job_id}.pdf'))


class HehunRequest(BaseModel):
    chart_id1: str
    chart_id2: str
    gender1: str = "male"
    gender2: str = "female"

@app.post("/api/tools/hehun")
def tool_hehun(req: HehunRequest):
    """合婚分析 — 双人八字配对评测"""
    c1 = _get_chart(req.chart_id1)
    c2 = _get_chart(req.chart_id2)
    if not c1 or not c2:
        raise HTTPException(400, "Provide two valid chart_ids from POST /api/chart")

    import tempfile
    t1 = os.path.join(tempfile.gettempdir(), f'hehun_c1_{req.chart_id1}.json')
    t2 = os.path.join(tempfile.gettempdir(), f'hehun_c2_{req.chart_id2}.json')
    try:
        json.dump(c1, open(t1, 'w', encoding='utf-8'), ensure_ascii=False)
        json.dump(c2, open(t2, 'w', encoding='utf-8'), ensure_ascii=False)

        hh = _import_tool('hehun', 'knowledge-base/hehun.py')
        result = hh.hehun_analysis(t1, t2, req.gender1, req.gender2)
        return result
    finally:
        for f in [t1, t2]:
            try: os.unlink(f)
            except: pass


class CompareRequest(BaseModel):
    chart_id1: str
    chart_id2: str

@app.post("/api/tools/compare")
def tool_compare(req: CompareRequest):
    """通用命盘对比 — 多维度比较两个八字命盘（不限合婚）"""
    c1 = _get_chart(req.chart_id1)
    c2 = _get_chart(req.chart_id2)
    if not c1 or not c2:
        raise HTTPException(400, "Provide two valid chart_ids")

    from bazi_calculator import compare_charts
    return compare_charts(c1, c2)


def _sse_event(event_type, data):
    """Format an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_chart_fetch_lock = threading.Lock()

def _get_chart(chart_id):
    """Get chart from memory cache, falling back to data_store DB."""
    chart = chart_cache._cache.get(chart_id)
    if chart:
        return chart
    # Restore from persistent DB (survives server restart)
    # Use lock to prevent concurrent duplicate DB fetches for the same key
    with _chart_fetch_lock:
        # Double-check: another request may have fetched and cached while we waited
        chart = chart_cache._cache.get(chart_id)
        if chart:
            return chart
        try:
            db_data = data_store.get_chart(chart_id)
            if db_data and db_data.get('chart_data'):
                chart = db_data['chart_data']
                chart_cache._cache[chart_id] = chart  # warm the cache
                return chart
        except Exception:
            pass
    return None


@app.get("/api/chat/stream")
async def chat_stream(chart_id: str, message: str):
    """SSE streaming chat — pre-analyzes chart, searches KB, then calls AI."""
    chart = _get_chart(chart_id)
    if not chart:
        async def err_stream():
            yield _sse_event('reply', {'text': '请先提供出生信息进行排盘。'})
            yield _sse_event('done', {'corrections': 0})
        return StreamingResponse(err_stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    report_tab = "overview"

    # ---- Pre-analysis: compute structured judgments, search KB ----
    try:
        conclusions = _auto_analyze(chart)
    except Exception:
        conclusions = {}

    # Search knowledge base for relevant gejue
    kb_gejue = []
    topic_kw_map = {
        'wealth': '财运 财星 投资',
        'marriage': '婚姻 夫妻 感情 配偶',
        'career': '事业 官运 官职 升迁',
        'health': '健康 疾病 寿元 身体',
        'name': '取名 姓名',
        'sihechu': '格局 用神 旺衰 命运',
        'overview': '命盘 格局 用神 运势',
        'liunian': '流年 太岁 运势 吉凶',
    }
    def _detect_tab(msg):
        if any(kw in msg for kw in ['财运','发财','投资','赚钱','破财']): return 'wealth'
        if any(kw in msg for kw in ['感情','婚姻','结婚','恋爱','桃花','夫妻']): return 'marriage'
        if any(kw in msg for kw in ['事业','工作','官运','升职','跳槽','创业']): return 'career'
        if any(kw in msg for kw in ['健康','疾病','身体']): return 'health'
        if any(kw in msg for kw in ['名字','取名','改名']): return 'name'
        if any(kw in msg for kw in ['流年','今年','明年','2025','2026','2027','2028','生肖运']): return 'liunian'
        return 'sihechu'

    report_tab = _detect_tab(message)
    kb_query = topic_kw_map.get(report_tab, '格局 用神')
    try:
        kb = _get_kb()
        kb_results = kb.fulltext_search(kb_query, 5)
        kb.close()
        kb_gejue = [r.get('text', '')[:200] for r in kb_results if r.get('text')]
    except Exception:
        kb_gejue = []

    # Build enriched chart with pre-analysis injected
    enriched = dict(chart)
    if conclusions:
        enriched['_analysis'] = conclusions

    async def event_stream():
        reply_text = ""
        report_text = ""

        tool_name_map = {'wealth': '流年分析', 'marriage': '命盘分析', 'career': '流年分析',
                         'health': '命盘分析', 'name': '取名分析', 'sihechu': '四合出分析',
                         'liunian': '流年详批'}
        tool_name = tool_name_map.get(report_tab, '四合出分析')

        yield _sse_event('tool', {'name': tool_name})
        yield _sse_event('reply', {'text': '正在调用玄机子 AI 分析…\n\n'})
        await asyncio.sleep(0.05)

        # Add KB gejue to the user message
        enriched_msg = message
        if kb_gejue:
            enriched_msg += '\n\n## 相关经典歌诀（参考）\n' + '\n'.join(f'- {g}' for g in kb_gejue[:3])

        in_report = False

        for event in _stream_claude(enriched, enriched_msg):
            if event.get('type') == 'error':
                yield _sse_event('reply', {'text': '\n\n⚠️ ' + (event.get('text') or '')})
                fallback = _generate_fallback(chart)
                reply_text += fallback
                yield _sse_event('reply', {'text': fallback})
                break

            if event.get('type') == 'text_delta':
                delta = event.get('text') or ''
                if not delta:
                    continue
                reply_text += delta
                report_text += delta

                if not in_report and '#' in delta:
                    in_report = True

                if not in_report:
                    yield _sse_event('reply', {'text': delta})
                else:
                    yield _sse_event('report', {'text': report_text, 'tab': report_tab})

            elif event.get('type') == 'message_delta':
                stop_reason = event.get('stop_reason', '')
                if stop_reason == 'max_tokens':
                    yield _sse_event('reply', {'text': '\n\n⚠️ 报告因长度限制被截断，可输入"继续"获取后续内容。'})

        yield _sse_event('done', {'corrections': 0})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _generate_fallback(chart):
    """Fallback analysis when API is unavailable."""
    dm = chart['day_master']
    gan = dm.get('gan', '') if isinstance(dm, dict) else dm
    wu = dm.get('wuxing', '') if isinstance(dm, dict) else ''
    ws = chart.get('wuxing_stats', {})
    total = sum([ws.get('金',0), ws.get('木',0), ws.get('水',0), ws.get('火',0), ws.get('土',0)]) or 1
    dm_pct = (ws.get(wu, 0) / total) if total else 0
    if dm_pct >= 0.4: grade = '身旺'
    elif dm_pct >= 0.2: grade = '中和'
    else: grade = '身弱'
    return f'\n\n⚠️ AI 服务暂不可用（请设置 ANTHROPIC_API_KEY）。\n\n**本地分析**: 日主{gan}{wu}，{grade}（日主占比{int(dm_pct*100)}%）。\n\n请配置 API Key 后重试以获取四合出深度报告。'


@app.get("/api/kb/search")
def kb_search(q: str = Query(..., description="Search query"), top: int = Query(10, ge=1, le=50)):
    """知识库检索 — search gejue, shensha, nayin, etc."""
    kb = _get_kb()
    results = kb.fulltext_search(q, top)
    kb.close()
    return {'query': q, 'count': len(results), 'results': results}

@app.get("/api/kb/stats")
def kb_stats():
    """知识库统计"""
    kb = _get_kb()
    stats = kb.stats()
    kb.close()
    return stats

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    import uvicorn
    logger.info(f'Starting BaZi Analysis API on http://localhost:{API_PORT}')
    logger.info(f'Swagger UI: http://localhost:{API_PORT}/docs')
    uvicorn.run(app, host='0.0.0.0', port=API_PORT)
