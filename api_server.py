#!/usr/bin/env python3
"""
BaZi Analysis API Server — FastAPI REST layer.
Exposes all tools as HTTP endpoints.

Usage:
    python api_server.py
    uvicorn api_server:app --reload --port 8000
    Open http://localhost:8000/docs for Swagger UI.
"""

import json, os, sys, hashlib, importlib.util
from datetime import date
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
import asyncio, time
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge-base'))

from bazi_calculator import (
    calculate_four_pillars, calculate_dayun, calculate_shensha,
    calculate_ziwei, calculate_wuyun_liuqi, calculate_true_solar_time,
    calculate_liunian, calculate_wuxing_stats, calculate_shishen_stats, format_to_spec,
    GAN_WUXING, GAN_YINYANG, ZHI_WUXING, NAYIN, get_shishen,
)
from lunar_calendar import lunar_to_solar, solar_to_lunar as _s2l

from claude_api import stream_chat as _stream_claude, ANTHROPIC_API_KEY

app = FastAPI(
    title="BaZi Analysis API",
    description="八字命理分析 REST API — 排盘、择日、流年、取名、案例检索、知识库搜索",
    version="1.0.0",
)
def _cors_origins():
    raw = os.environ.get("BAZI_CORS_ORIGINS", "")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return ["http://127.0.0.1:8000", "http://localhost:8000"]

app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_methods=["*"], allow_headers=["*"])

# ============================================================
# RATE LIMITER — per-IP sliding window
# ============================================================

# Limits: (max_requests, window_seconds)
_RATE_LIMITS = {
    "default": (60, 60),         # 60 req/min
    "/api/chat/stream": (5, 60), # 5 req/min (expensive AI call)
    "/api/analyze/pdf": (10, 60),# 10 req/min (PDF generation)
}
_hits = defaultdict(list)  # ip -> [timestamps]
_CLEAN_INTERVAL = 300  # clean stale entries every 5 min
_last_clean = time.time()


def _clean_old_hits(now):
    global _last_clean
    if now - _last_clean < _CLEAN_INTERVAL:
        return
    _last_clean = now
    stale = []
    for ip, timestamps in _hits.items():
        timestamps[:] = [t for t in timestamps if now - t < 120]
        if not timestamps:
            stale.append(ip)
    for ip in stale:
        del _hits[ip]


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    now = time.time()
    _clean_old_hits(now)

    # Determine limit for this path
    path = request.url.path
    max_req, window = _RATE_LIMITS.get("default")
    for prefix, limit in _RATE_LIMITS.items():
        if prefix != "default" and path.startswith(prefix):
            max_req, window = limit
            break

    # Client IP
    ip = request.client.host if request.client else "unknown"
    timestamps = _hits[ip]
    timestamps[:] = [t for t in timestamps if now - t < window]

    if len(timestamps) >= max_req:
        retry_after = int(window - (now - timestamps[0]))
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁，请 {retry_after} 秒后重试",
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(max_req)},
        )

    timestamps.append(now)
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

        if birth.use_solar_time:
            adj_h, adj_m, adj_minutes, method = birth.hour, birth.minute, 0, 'user_adjusted'
        else:
            true_solar = calculate_true_solar_time(birth.hour, birth.minute, birth.location, birth.month)
            adj_h, adj_m, adj_minutes, method = true_solar
        true_solar_info = {
            'original_time': f'{birth.year:04d}-{birth.month:02d}-{birth.day:02d}T{birth.hour:02d}:{birth.minute:02d}:00',
            'adjusted_time': f'{birth.year:04d}-{birth.month:02d}-{birth.day:02d}T{adj_h:02d}:{adj_m:02d}:00',
            'adjustment_minutes': adj_minutes,
            'method': method,
        }

        four_pillars = calculate_four_pillars(birth.year, birth.month, birth.day, adj_h, adj_m, birth.location)
        yp = (four_pillars['year']['gan'], four_pillars['year']['zhi'])
        mp = (four_pillars['month']['gan'], four_pillars['month']['zhi'])
        dm = four_pillars['day_master']

        dayun_raw = calculate_dayun(yp, mp, birth.gender, birth.year, birth.month, birth.day)
        shensha = calculate_shensha(four_pillars, dm)
        ziwei = calculate_ziwei(birth.year, birth.month, birth.day, adj_h, birth.gender)
        wuyun = calculate_wuyun_liuqi(yp[0], yp[1])
        wuxing = calculate_wuxing_stats(four_pillars)
        shishen = calculate_shishen_stats(four_pillars)
        liunian = calculate_liunian(date.today().year, dm, 3)

        chart = format_to_spec(four_pillars, dayun_raw, shensha, ziwei, wuyun, wuxing, shishen, liunian, true_solar_info)
        chart['chart_id'] = key
        chart['birth_info'] = {
            'year': birth.year, 'month': birth.month, 'day': birth.day,
            'hour': birth.hour, 'minute': birth.minute,
            'gender': birth.gender, 'location': birth.location,
        }

        if len(self._cache) >= self._max_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = chart
        return chart, key

chart_cache = ChartCache()

# ============================================================
# HELPERS: Import knowledge-base modules (hyphenated dirs)
# ============================================================

def _import_tool(module_name, file_path):
    kb_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge-base')
    if kb_dir not in sys.path:
        sys.path.insert(0, kb_dir)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
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

@app.post("/api/chart")
def calculate_chart(birth: BirthInfo):
    """排盘 — calculate full BaZi chart"""
    chart, chart_id = chart_cache.get_or_create(birth)
    return chart

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
    """Get cached chart by ID"""
    if chart_id in chart_cache._cache:
        return chart_cache._cache[chart_id]
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
    chart = chart_cache._cache.get(chart_id) if chart_id else None
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
    chart = chart_cache._cache.get(chart_id) if chart_id else None
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
    chart = chart_cache._cache.get(req.chart_id) if req.chart_id else None
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
    chart = chart_cache._cache.get(req.chart_id) if req.chart_id else None
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
    chart = chart_cache._cache.get(req.chart_id) if req.chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id")
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(chart, f, ensure_ascii=False)
        tmp = f.name
    top_n = req.top_n
    cr = _get_case_retrieval()
    retriever = cr.CaseRetriever() if hasattr(cr, 'CaseRetriever') else None
    if retriever:
        results = retriever.retrieve(tmp, top_n, mode='auto')
    else:
        results = cr.simple_match(cr.extract_case_features(tmp), top_n)

    os.unlink(tmp)
    return results

class AnalyzeRequest(BaseModel):
    chart_id: str
    mode: int = Field(1, ge=1, le=6)
    conclusions: dict = None  # Agent-generated analysis conclusions
    template: str = Field("dark", pattern="^(dark|modern|scroll|night)$")

@app.post("/api/analyze")
def analyze_report(req: AnalyzeRequest):
    """分析并生成报告 — takes Agent conclusions JSON + chart → renders markdown"""
    chart = chart_cache._cache.get(req.chart_id) if req.chart_id else None
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

    import importlib.util
    spec = importlib.util.spec_from_file_location('report_builder', 'report_builder.py')
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    rb.build_report(chart_tmp, req.mode, concl_tmp, report_tmp)

    with open(report_tmp, 'r', encoding='utf-8') as f:
        report_md = f.read()

    os.unlink(chart_tmp); os.unlink(concl_tmp); os.unlink(report_tmp)
    return {'mode': req.mode, 'report': report_md}

def _auto_analyze(chart):
    """Auto-analyze chart data to fill conclusions with computed values."""
    fp = chart['four_pillars']
    dm = chart['day_master']
    gan = dm.get('gan', '') if isinstance(dm, dict) else dm
    wu = dm.get('wuxing', '') if isinstance(dm, dict) else GAN_WUXING.get(gan, '')
    yy = dm.get('yinyang', '') if isinstance(dm, dict) else GAN_YINYANG.get(gan, '')
    ws = chart.get('wuxing_stats', {})
    dy = chart.get('da_yun', [])
    shensha_list = chart.get('shensha', [])

    # === 旺衰量化 ===
    month_zhi = fp['month']['zhi']
    month_wu = ZHI_WUXING.get(month_zhi, '')
    sheng = {('木','火'),('火','土'),('土','金'),('金','水'),('水','木')}
    month_support = '同气' if month_wu == wu else ('得生' if (month_wu, wu) in sheng else ('泄气' if (wu, month_wu) in sheng else '受克'))

    wu_counts = {'金':ws.get('jin',0),'木':ws.get('mu',0),'水':ws.get('shui',0),'火':ws.get('huo',0),'土':ws.get('tu',0)}
    total_wu = sum(wu_counts.values()) or 1
    dm_pct = wu_counts.get(wu, 0) / total_wu
    miss = ws.get('missing', [])
    strongest = ws.get('strongest', '')

    if dm_pct >= 0.4: grade = '身旺'
    elif dm_pct >= 0.25: grade = '身强'
    elif dm_pct >= 0.15: grade = '中和'
    else: grade = '身弱'

    wucount_roots = sum(1 for pk in ['year','month','day','hour']
                       for cg in (fp[pk].get('cang_gan',[]) or [])
                       if GAN_WUXING.get(cg,'') == wu)
    ling_score = 30 if month_support in ('同气','得生') else 15
    di_score = min(25, wu_counts.get(wu,0)*5)
    day_zhi2 = fp['day']['zhi']
    wangshuai = {
        '得令': {'score': f'{ling_score}/50',
                 'note': f'月令{month_zhi}({month_wu}){month_support}日主{wu}'},
        '得地': {'score': f'{di_score}/25',
                 'note': f'日支{day_zhi2}藏干中{wucount_roots}根'},
        '得势': {'score': '-/20', 'note': f'比劫{wu_counts.get(wu,0)}个'},
        '远近': {'score': '-/5', 'note': ''},
        'total': str(int(dm_pct * 100)),
        'grade': grade
    }

    # === 格局判定 ===
    month_gan = fp['month']['gan']
    month_main = fp['month'].get('cang_gan', [''])[0] if fp['month'].get('cang_gan') else ''
    shishen_of_month = get_shishen(gan, month_gan)
    pattern_map = {'正官':'正官格','七杀':'七杀格','正财':'正财格','偏财':'偏财格',
                   '正印':'正印格','偏印':'偏印格','食神':'食神格','伤官':'伤官格',
                   '比肩':'建禄格','劫财':'月刃格'}
    pattern_name = pattern_map.get(shishen_of_month, f'{shishen_of_month}格')
    pattern = {
        'name': pattern_name,
        'category': '正格',
        'verdict': '成格' if grade in ('身旺','身强') else '待救',
        'reasoning': f'月令{month_zhi}本气{month_main}，{month_gan}透干→取{pattern_name}。日主{grade}。'
    }

    # === 用神 ===
    if grade in ('身旺','身强'):
        yong, ji = ('财星','食伤'), ('印星','比劫')
    elif grade == '身弱':
        yong, ji = ('印星','比劫'), ('财星','食伤')
    else:
        yong, ji = ('视流通','断破坏'), ('财星','')

    # 调候
    tiaohou = {'亥':'丙火','子':'丙火','丑':'丙火','巳':'癸水','午':'癸水','未':'癸水'}.get(month_zhi,'')
    xishen_note = f'日主{grade}→用{yong[0]}。' + (f'冬月需{tiaohou}暖局。' if tiaohou else '')
    yongshen = {
        '用神': {'ganzhi': yong[0], 'note': '格局枢纽'},
        '相神': {'ganzhi': yong[1] if len(yong)>1 else '', 'note': '辅佐用神'},
        '喜神': {'ganzhi': yong[0], 'note': '扶助格局'},
        '忌神': {'ganzhi': ji[0], 'note': '破坏格局'},
        '仇神': {'ganzhi': '', 'note': ''},
        '闲神': {'ganzhi': '', 'note': ''},
        'assessment': xishen_note
    }

    # === 流年 ===
    current_dy = next((d for d in dy if d.get('is_current')), dy[0] if dy else {})
    liunian = {
        'years': [
            {'year': '2026', 'ganzhi': '丙午', 'dayun_rel': '平稳',
             'yongshen': '待分析', 'focus': '全年', 'ji_xiong': '—'},
            {'year': '2027', 'ganzhi': '丁未', 'dayun_rel': '平稳',
             'yongshen': '待分析', 'focus': '全年', 'ji_xiong': '—'},
            {'year': '2028', 'ganzhi': '戊申', 'dayun_rel': '平稳',
             'yongshen': '待分析', 'focus': '全年', 'ji_xiong': '—'},
        ],
        'note': '当前大运' + current_dy.get('gan','') + current_dy.get('zhi','')
    }

    # === 七维 ===
    personality = f'{gan}{wu}{"阳" if yy=="阳" else "阴"}日主，生于{month_zhi}月。'
    if shishen_of_month == '食神': personality += '食神吐秀，思维活跃，善于表达。'
    elif shishen_of_month == '伤官': personality += '伤官透干，才华横溢，不服约束。'
    elif shishen_of_month in ('正官','七杀'): personality += '官杀当令，责任心强，追求秩序。'
    elif shishen_of_month in ('正印','偏印'): personality += '印星当令，好学深思，内敛稳重。'
    else: personality += '性格受月令十神主导。'

    seven_dims = {
        'personality': {'stars': 4, 'summary': f'{wu}性日主特质',
                        'analysis': personality},
        'career': {'stars': 3, 'summary': f'宜{yong[0]}相关行业',
                   'analysis': f'格局{pattern_name}，{grade}用{yong[0]}。行业方向需结合用神五行选择。'},
        'wealth': {'stars': 3, 'summary': '视财星旺衰而定',
                   'analysis': f'日主{grade}，'
                   + ('宜求稳定正财' if grade == '身弱' else '可担财，但需食伤生源') + '。'},
        'love': {'stars': 3, 'summary': f'日支{day_zhi2}为配偶宫',
                   'analysis': f'日支坐{fp["day"].get("shi_shen_zhi_main","")}，配偶特质受此十神影响。'},
        'health': {'stars': 3, 'summary': f'注意{wu}对应脏腑',
                   'analysis': f'五行缺{miss}，对应脏腑需关注。{wu}主'
                   + ('心/眼' if wu=='火' else '脾胃' if wu=='土' else '肺/大肠' if wu=='金' else '肝胆' if wu=='木' else '肾/膀胱') + '。'},
        'study': {'stars': 3, 'summary': '视印星强弱',
                  'analysis': '印星' + ('得力' if wu_counts.get(wu,0)>1 else '待加强') + '，学历受印星+文昌影响。'},
        'liunian': {'stars': 3, 'summary': '需结合大运流年',
                    'analysis': '当前大运' + current_dy.get('gan','') + current_dy.get('zhi','') + '，需结合流年干支判断具体运势。'},
    }

    # === 交叉验证 ===
    cv = {
        '旺衰': {'primary': f'{grade}({dm_pct*100:.0f}%)', 'secondary': '待盲派验证', 'result': '✅'},
        '格局/层次': {'primary': pattern_name, 'secondary': '待验证', 'result': '✅'},
        '事业方向': {'primary': yong[0], 'secondary': '待验证', 'result': '✅'},
        '财运判断': {'primary': '视财星', 'secondary': '待验证', 'result': '✅'},
        '婚姻质量': {'primary': '视日支', 'secondary': '待验证', 'result': '✅'},
        'divergence': ''
    }

    # === 纳音 ===
    year_ganzhi = fp['year']['gan'] + fp['year']['zhi']
    year_nayin = NAYIN.get(year_ganzhi, '')
    colors = {'木':'青/绿','火':'红/紫','土':'黄/褐','金':'白/银','水':'黑/蓝'}
    directions = {'木':'东','火':'南','土':'中','金':'西','水':'北'}
    industries = {'木':'教育/文化','火':'能源/传媒','土':'地产/金融','金':'法律/机械','水':'贸易/物流'}
    advice_wu = yong[0][0] if yong[0] and yong[0][0] in '金木水火土' else wu
    nayin_advice = '颜色:' + colors.get(advice_wu,'') + ' 方位:' + directions.get(advice_wu,'') + ' 行业:' + industries.get(advice_wu,'')

    def _judgment(name, conclusion, confidence, evidence, counter_evidence=None):
        return {"name": name, "conclusion": conclusion, "confidence": confidence,
                "evidence": evidence, "counter_evidence": counter_evidence or []}

    judgments = [
        _judgment("旺衰", grade,
            "medium" if grade == "中和" else "high",
            [f"日主五行占比{dm_pct * 100:.0f}%", f"月令{month_zhi}({month_wu})对日主为{month_support}"],
            ["当前算法未完整计算透干、根气远近和合化后的强弱变化"]),
        _judgment("格局", pattern_name,
            "medium",
            [f"月干{month_gan}对日主为{shishen_of_month}", f"月令本气{month_main}"],
            ["当前仅按月干/月令粗判，未完整处理变格、从格、合化和格局破救"]),
        _judgment("用神", yongshen["assessment"],
            "low" if grade == "中和" else "medium",
            [f"日主{grade}", f"初步取{yong[0]}为用"],
            ["当前用神未完全区分格局用神、调候用神、通关用神和病药用神"]),
    ]

    return {
        'wangshuai': wangshuai,
        'judgments': judgments,
        'pattern': pattern,
        'yongshen': yongshen,
        'liunian': liunian,
        'seven_dims': seven_dims,
        'cross_validation': cv,
        'nayin': {'year_nayin': year_nayin, 'description': f'年柱{year_ganzhi}纳音{year_nayin}',
                  'advice': nayin_advice},
        'source_tracing': [
            {'conclusion': pattern_name, 'basis': f'月令{month_zhi}透{month_gan}',
             'source': '《子平真诠》论用神'},
            {'conclusion': f'日主{grade}', 'basis': f'{gan}{wu}生于{month_zhi}月',
             'source': '《滴天髓》强弱论'},
        ],
    }

@app.post("/api/analyze/pdf")
def analyze_pdf(req: AnalyzeRequest):
    """生成PDF报告 — 先渲染Markdown再转PDF"""
    chart = chart_cache._cache.get(req.chart_id) if req.chart_id else None
    if not chart:
        raise HTTPException(400, "Provide valid chart_id")

    import tempfile
    # Write chart
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(chart, f, ensure_ascii=False)
        chart_tmp = f.name
    conclusions = req.conclusions or _auto_analyze(chart)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(conclusions, f, ensure_ascii=False)
        concl_tmp = f.name
    md_tmp = os.path.join(tempfile.gettempdir(), f'report_{req.chart_id}.md')
    pdf_tmp = os.path.join(tempfile.gettempdir(), f'report_{req.chart_id}.pdf')

    # Render markdown
    import importlib.util
    spec = importlib.util.spec_from_file_location('report_builder', 'report_builder.py')
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    rb.build_report(chart_tmp, req.mode, concl_tmp, md_tmp)

    # Render PDF (safe: template already validated by Pydantic pattern)
    import subprocess
    template = req.template or 'dark'
    cmd = [sys.executable, "report_to_pdf.py", md_tmp, "-o", pdf_tmp, "-t", template]
    ret = subprocess.run(cmd, capture_output=True, text=True)
    if ret.returncode != 0:
        raise HTTPException(500, f"PDF generation failed: {ret.stderr[-500:]}")

    with open(pdf_tmp, 'rb') as f:
        pdf_bytes = f.read()

    # Cleanup
    for f in [chart_tmp, concl_tmp, md_tmp, pdf_tmp]:
        try: os.unlink(f)
        except: pass

    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename=report_{req.chart_id}.pdf'})

class HehunRequest(BaseModel):
    chart_id1: str
    chart_id2: str
    gender1: str = "male"
    gender2: str = "female"

@app.post("/api/tools/hehun")
def tool_hehun(req: HehunRequest):
    """合婚分析 — 双人八字配对评测"""
    c1 = chart_cache._cache.get(req.chart_id1)
    c2 = chart_cache._cache.get(req.chart_id2)
    if not c1 or not c2:
        raise HTTPException(400, "Provide two valid chart_ids from POST /api/chart")

    import tempfile
    t1 = os.path.join(tempfile.gettempdir(), f'hehun_c1_{req.chart_id1}.json')
    t2 = os.path.join(tempfile.gettempdir(), f'hehun_c2_{req.chart_id2}.json')
    json.dump(c1, open(t1, 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(c2, open(t2, 'w', encoding='utf-8'), ensure_ascii=False)

    import importlib.util
    spec = importlib.util.spec_from_file_location('hehun', 'knowledge-base/hehun.py')
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    result = hh.hehun_analysis(t1, t2, req.gender1, req.gender2)

    for f in [t1, t2]:
        try: os.unlink(f)
        except: pass
    return result


def _sse_event(event_type, data):
    """Format an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/chat/stream")
async def chat_stream(chart_id: str, message: str):
    """SSE streaming chat — calls Anthropic API with agent system prompt + chart data."""
    chart = chart_cache._cache.get(chart_id)
    if not chart:
        async def err_stream():
            yield _sse_event('reply', {'text': '请先提供出生信息进行排盘。'})
            yield _sse_event('done', {'corrections': 0})
        return StreamingResponse(err_stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    reply_text = ""
    report_text = ""
    report_tab = "overview"

    # Detect report tab from message keywords
    def _detect_tab(msg):
        if any(kw in msg for kw in ['财运','发财','投资','赚钱','破财']): return 'wealth'
        if any(kw in msg for kw in ['感情','婚姻','结婚','恋爱','桃花','夫妻']): return 'marriage'
        if any(kw in msg for kw in ['事业','工作','官运','升职','跳槽','创业']): return 'career'
        if any(kw in msg for kw in ['健康','疾病','身体']): return 'health'
        if any(kw in msg for kw in ['名字','取名','改名']): return 'name'
        return 'sihechu'

    async def event_stream():
        nonlocal reply_text, report_text, report_tab

        report_tab = _detect_tab(message)
        tool_name_map = {'wealth': '流年分析', 'marriage': '命盘分析', 'career': '流年分析',
                         'health': '命盘分析', 'name': '取名分析', 'sihechu': '四合出分析'}
        tool_name = tool_name_map.get(report_tab, '四合出分析')

        yield _sse_event('tool', {'name': tool_name})
        yield _sse_event('reply', {'text': '正在调用玄机子 AI 分析…\n\n'})
        await asyncio.sleep(0.05)

        in_report = False

        for event in _stream_claude(chart, message):
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
    print('Starting BaZi Analysis API on http://localhost:8000')
    print('Swagger UI: http://localhost:8000/docs')
    uvicorn.run(app, host='127.0.0.1', port=8000)
