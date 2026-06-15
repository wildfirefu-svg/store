#!/usr/bin/env python3
"""
BaZi MCP Server — expose BaZi analysis tools via Model Context Protocol.

Supported transports:
    stdio  — for Claude Desktop / any MCP stdio client (default)
    sse    — HTTP SSE transport for remote clients

Usage:
    python mcp_server.py                      # stdio
    python mcp_server.py --transport sse      # SSE on http://0.0.0.0:8001/sse
"""

import json, os, sys, hashlib, importlib.util, argparse, logging
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import MCP_PORT, LOG_LEVEL, LOG_FILE

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename=LOG_FILE or None,
)
logger = logging.getLogger('mcp')

from mcp.server.fastmcp import FastMCP

from bazi_calculator import (
    calculate_true_solar_time, compute_chart, compare_charts,
)

# ---------------------------------------------------------------------------
mcp = FastMCP("bazi-server")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _calc_chart(year, month, day, hour=0, minute=0, gender="male", location="Beijing"):
    return compute_chart(year, month, day, hour, minute, gender, location)


_tool_cache = {}

def _import_tool(module_name, file_path):
    if module_name in _tool_cache:
        return _tool_cache[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
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

# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

@mcp.tool()
def bazi_paipan(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    gender: str = "male",
    location: str = "Beijing",
) -> str:
    """排盘 — 根据出生信息计算完整八字命盘。

    返回四柱（年柱/月柱/日柱/时柱）、日主、十神、大运、神煞、
    紫微斗数、五运六气、五行统计、流年、真太阳时校正等信息。
    """
    chart = _calc_chart(year, month, day, hour, minute, gender, location)
    return json.dumps(chart, ensure_ascii=False, indent=2)


@mcp.tool()
def bazi_true_solar_time(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    location: str = "Beijing",
) -> str:
    """真太阳时校正 — 将北京时间转换为出生地的真太阳时。

    返回校正后的时间和校正量。八字排盘前应先做真太阳时校正。
    """
    true_solar = calculate_true_solar_time(hour, minute, location, month)
    adj_h, adj_m, adj_minutes, method = true_solar
    result = {
        'original': f'{hour:02d}:{minute:02d}',
        'adjusted': f'{adj_h:02d}:{adj_m:02d}',
        'offset_minutes': adj_minutes,
        'method': method,
        'location': location,
        'date': f'{year:04d}-{month:02d}-{day:02d}',
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def bazi_zeri(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    gender: str = "male",
    location: str = "Beijing",
    target_year: int | None = None,
    target_month: int | None = None,
    purpose: str = "通用",
    top_n: int = 5,
    xishen: str = "",
) -> str:
    """择日 — 根据八字命盘选取吉日。

    针对特定用途（结婚/开业/出行/搬家/通用），结合命盘喜忌选出最有利的日期。
    可选参数 xishen 指定喜用神（如"金,水"），留空则自动推断。
    """
    chart = _calc_chart(year, month, day, hour, minute, gender, location)
    zeri = _get_zeri()

    target_year = target_year or date.today().year
    target_month = target_month or date.today().month
    xishen_list = [x.strip() for x in xishen.split(',') if x.strip()] if xishen else None

    dates = zeri.find_good_dates(target_year, target_month, purpose, top_n, chart, xishen_list)
    return json.dumps({
        'purpose': purpose,
        'target_year': target_year,
        'target_month': target_month,
        'dates': dates,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def bazi_liunian(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    gender: str = "male",
    location: str = "Beijing",
    target_year: int | None = None,
) -> str:
    """流年日历 — 生成全年12个月的运势日历。

    为每个月分析事业/财运/感情/健康评分及宜忌建议。
    """
    chart = _calc_chart(year, month, day, hour, minute, gender, location)
    lc = _get_liunian()
    target_year = target_year or date.today().year

    cal = lc.generate_year_calendar(
        year, month, day, hour, gender, target_year, chart
    )
    return json.dumps(cal, ensure_ascii=False, indent=2)


@mcp.tool()
def bazi_name_eval(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    gender: str = "male",
    location: str = "Beijing",
    name: str = "",
) -> str:
    """名字评测 — 评估姓名对八字命盘的匹配度。

    分析五格数理、三才配置、五行匹配、音律、字义等维度，
    给出综合评分和改进建议。name 为完整姓名（含姓氏）。
    """
    if len(name) < 2:
        return json.dumps({'error': '请提供完整姓名（含姓氏），至少两个字'}, ensure_ascii=False)

    chart = _calc_chart(year, month, day, hour, minute, gender, location)
    na = _get_name_analysis()
    surname = name[0]
    given_name = name[1:]
    result = na.evaluate_name(surname, given_name, chart, gender)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def bazi_name_gen(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    gender: str = "male",
    location: str = "Beijing",
    surname: str = "张",
    top_n: int = 5,
) -> str:
    """取名推荐 — 根据八字命盘喜用神推荐吉利名字。

    分析日主强弱和喜用神，从字库中筛选五行匹配、数理吉利的名字组合。
    """
    chart = _calc_chart(year, month, day, hour, minute, gender, location)
    na = _get_name_analysis()
    names = na.generate_names(surname, chart, gender, top_n)
    result = {
        'surname': surname,
        'gender': gender,
        'count': len(names) if isinstance(names, list) else 0,
        'names': names if isinstance(names, list) else [],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def bazi_case_search(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    gender: str = "male",
    location: str = "Beijing",
    top_n: int = 5,
) -> str:
    """案例检索 — 在案例库中搜索与当前命盘最相似的历史案例。

    按日主、五行结构、格局等特征进行匹配，返回相似案例供参考。
    """
    import tempfile
    chart = _calc_chart(year, month, day, hour, minute, gender, location)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(chart, f, ensure_ascii=False)
        tmp = f.name

    try:
        cr = _get_case_retrieval()
        if hasattr(cr, 'CaseRetriever'):
            retriever = cr.CaseRetriever()
            results = retriever.retrieve(tmp, top_n, mode='auto')
        else:
            features = cr.extract_case_features(tmp)
            results = cr.simple_match(features, top_n)
        return json.dumps(results, ensure_ascii=False, indent=2)
    finally:
        os.unlink(tmp)


@mcp.tool()
def bazi_kb_search(query: str, top: int = 10) -> str:
    """知识库检索 — 搜索八字知识库（歌诀、神煞、纳音、基础理论等）。

    支持全文搜索，返回相关知识和出处。
    """
    kb = _get_kb()
    results = kb.fulltext_search(query, top)
    kb.close()
    return json.dumps({
        'query': query,
        'count': len(results),
        'results': results,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def bazi_kb_stats() -> str:
    """知识库统计 — 返回八字知识库的整体统计信息。"""
    kb = _get_kb()
    stats = kb.stats()
    kb.close()
    return json.dumps(stats, ensure_ascii=False, indent=2)


@mcp.tool()
def bazi_compare(
    year1: int, month1: int, day1: int, hour1: int = 0, minute1: int = 0,
    gender1: str = "male", location1: str = "Beijing",
    year2: int = 0, month2: int = 0, day2: int = 0, hour2: int = 0, minute2: int = 0,
    gender2: str = "male", location2: str = "Beijing",
) -> str:
    """通用命盘对比 — 多维度比较两个八字命盘。

    对比五行分布、日主关系、纳音关系、神煞交集、大运阶段、紫微斗数等维度。
    不限合婚用途，可用于合作伙伴、亲子关系等任意两人命盘的对比分析。

    需要提供两个人的完整出生信息。
    """
    c1 = _calc_chart(year1, month1, day1, hour1, minute1, gender1, location1)
    c2 = _calc_chart(year2, month2, day2, hour2, minute2, gender2, location2)
    result = compare_charts(c1, c2)
    return json.dumps(result, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BaZi MCP Server')
    parser.add_argument(
        '--transport', choices=['stdio', 'sse'], default='stdio',
        help='Transport protocol (default: stdio)'
    )
    parser.add_argument(
        '--port', type=int, default=MCP_PORT,
        help=f'SSE listen port (default: {MCP_PORT})'
    )
    args = parser.parse_args()

    if args.transport == 'sse':
        logger.info(f'BaZi MCP Server starting on http://0.0.0.0:{args.port}/sse')
        mcp.settings.host = '0.0.0.0'
        mcp.settings.port = args.port
        mcp.run(transport='sse')
    else:
        mcp.run(transport='stdio')
