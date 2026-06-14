#!/usr/bin/env python3
"""
Report Builder — Python rendering engine for BaZi analysis reports.
Takes structured conclusions (from Agent) + chart JSON → renders complete Markdown.

Cuts token usage by ~60%: Agent outputs ~300 words of JSON conclusions instead of ~2000 words of markdown.

Usage:
    python report_builder.py --chart chart.json --mode 1 --conclusions analysis.json -o report.md
"""

import json, os, sys, argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ============================================================
# 1. FIXED REPORT SECTIONS (rendered from chart data)
# ============================================================

def render_chart_table(four_pillars, day_master, da_yun, tai_yuan, ming_gong, shen_gong):
    """Render the八字排盘 table."""
    lines = []
    lines.append('四柱          年柱          月柱          日柱          时柱')
    lines.append('------        ------        ------        ------        ------')

    for label, key in [('天干','gan'), ('地支','zhi'), ('藏干','cang_gan'), ('十神','shi_shen'), ('纳音','nayin'), ('空亡','kong_wang')]:
        vals = []
        for pk in ['year','month','day','hour']:
            p = four_pillars.get(pk, {})
            if key == 'cang_gan':
                cg = p.get('cang_gan', [])
                if isinstance(cg, list):
                    vals.append(' '.join(cg))
                else:
                    vals.append(str(cg))
            elif key == 'shi_shen':
                if pk == 'day':
                    vals.append('日主')
                else:
                    vals.append(p.get('shi_shen_gan', p.get('shi_shen', '')))
            elif key == 'kong_wang':
                vals.append(p.get('kong_wang', ''))
            else:
                vals.append(str(p.get(key, '')))
        lines.append(f'{label:<14}' + ''.join(f'{v:<14}' for v in vals))

    lines.append('')
    # 大运 info
    current_dy = None
    for d in da_yun:
        if d.get('is_current'):
            current_dy = d
            break
    dy_str = f'{current_dy["gan"]}{current_dy["zhi"]} ({current_dy.get("start_age","?")}-{current_dy.get("end_age","?")}岁)' if current_dy else 'N/A'
    lines.append(f'起运：{da_yun[0].get("start_age","?")}岁  当前大运：{dy_str}')
    lines.append(f'胎元：{tai_yuan.get("gan","")}{tai_yuan.get("zhi","")}  '
                 f'命宫：{ming_gong.get("gan","")}{ming_gong.get("zhi","")}  '
                 f'身宫：{shen_gong.get("gan","")}{shen_gong.get("zhi","")}')
    return '\n'.join(lines)


def render_wangshuai(wangshuai):
    """Render旺衰量化 section."""
    ws = wangshuai
    lines = []
    lines.append('| 维度 | 得分 | 说明 |')
    lines.append('|------|------|------|')
    for dim in ['得令','得地','得势','远近']:
        d = ws.get(dim, {})
        lines.append(f'| {dim} | {d.get("score","")} | {d.get("note","")} |')
    lines.append(f'| **综合** | **{ws.get("total", "")}** | **{ws.get("grade", "")}** |')
    return '\n'.join(lines)


def render_pattern(pattern):
    """Render格局判定 section."""
    p = pattern
    lines = []
    lines.append('| 判定项 | 结论 |')
    lines.append('|--------|------|')
    for key, label in [('name','格局主名'), ('sub_name','格局次名'), ('category','格局分类'),
                        ('verdict','格局成否'), ('break_flag','破格标志')]:
        lines.append(f'| {label} | {p.get(key, "")} |')
    if p.get('reasoning'):
        lines.append(f'\n{p["reasoning"]}')
    return '\n'.join(lines)


def render_yongshen(yongshen):
    """Render六位用神 section."""
    ys = yongshen
    lines = []
    lines.append('| 六位 | 干支 | 说明 |')
    lines.append('|------|------|------|')
    for role in ['用神','相神','喜神','忌神','仇神','闲神']:
        lines.append(f'| {role} | {ys.get(role, {}).get("ganzhi","")} | {ys.get(role, {}).get("note","")} |')
    if ys.get('assessment'):
        lines.append(f'\n{ys["assessment"]}')
    return '\n'.join(lines)


def render_dayun_table(da_yun):
    """Render大运列表."""
    lines = []
    lines.append('| # | 干支 | 起运年龄 | 十神 |')
    lines.append('|---|------|---------|------|')
    for d in da_yun[:10]:
        marker = ' ←当前' if d.get('is_current') else ''
        lines.append(f'| {d.get("index","")} | {d.get("gan","")}{d.get("zhi","")}{marker} | '
                     f'{d.get("start_age","")}-{d.get("end_age","")}岁 | '
                     f'{d.get("shi_shen_gan","")} |')
    return '\n'.join(lines)


def render_liunian_table(liunian_analysis):
    """Render流年表格."""
    lines = []
    lines.append('| 年份 | 流年干支 | 大运关系 | 用神状态 | 重点领域 | 吉凶 |')
    lines.append('|------|---------|---------|---------|---------|------|')
    for entry in liunian_analysis.get('years', []):
        lines.append(f'| {entry.get("year","")} | {entry.get("ganzhi","")} | '
                     f'{entry.get("dayun_rel","")} | {entry.get("yongshen","")} | '
                     f'{entry.get("focus","")} | {entry.get("ji_xiong","")} |')
    if liunian_analysis.get('note'):
        lines.append(f'\n{liunian_analysis["note"]}')
    return '\n'.join(lines)


def render_seven_dims(seven_dims):
    """Render七维人生解读."""
    lines = []
    dim_labels = {
        'personality': '性格特质', 'career': '事业方向', 'wealth': '财运分析',
        'love': '感情婚姻', 'health': '健康提示', 'study': '学业文昌', 'liunian': '流年运势'
    }
    for key, label in dim_labels.items():
        d = seven_dims.get(key, {})
        stars = d.get('stars', 3)
        star_str = '⭐' * stars + '☆' * (5 - stars)
        summary = d.get('summary', '')
        analysis = d.get('analysis', '')
        lines.append(f'### {label} {star_str} — {summary}')
        lines.append(analysis)
        lines.append('')
    return '\n'.join(lines)


def render_cross_validation(cv, mode_name, secondary_name):
    """Render双系统交叉验证."""
    lines = []
    lines.append(f'| 维度 | {mode_name} | {secondary_name} | 结果 |')
    lines.append('|------|---------|------|------|')
    for dim in ['旺衰','格局/层次','事业方向','财运判断','婚姻质量']:
        d = cv.get(dim, {})
        lines.append(f'| {dim} | {d.get("primary","")} | {d.get("secondary","")} | {d.get("result","")} |')
    if cv.get('divergence'):
        lines.append(f'\n### 分歧说明\n{cv["divergence"]}')
    return '\n'.join(lines)


def render_source_tracing(tracing):
    """Render命理依据溯源."""
    lines = []
    lines.append('| 结论 | 依据 | 出处 |')
    lines.append('|------|------|------|')
    for t in tracing:
        lines.append(f'| {t.get("conclusion","")} | {t.get("basis","")} | {t.get("source","")} |')
    return '\n'.join(lines)


def render_portrait(portrait):
    """Render 命主画像 — a plain-language narrative portrait."""
    if not portrait or not portrait.get('narrative'):
        return ''
    lines = []
    lines.append(portrait.get('narrative', ''))
    if portrait.get('advice'):
        lines.append(f'\n**给您的建议**: {portrait["advice"]}')
    return '\n'.join(lines)


# ============================================================
# 2. MODE-SPECIFIC REPORT ASSEMBLER
# ============================================================

def render_judgments(judgments):
    if not judgments:
        return ""
    lines = [
        "## 判断依据与置信度",
        "",
        "| 判断 | 结论 | 置信度 | 依据 | 反证/限制 |",
        "|---|---|---|---|---|",
    ]
    for item in judgments:
        evidence = "<br>".join(item.get("evidence", []))
        counter = "<br>".join(item.get("counter_evidence", []))
        lines.append(
            f"| {item.get('name', '')} | {item.get('conclusion', '')} | "
            f"{item.get('confidence', '')} | {evidence} | {counter} |"
        )
    lines.append("")
    return "\n".join(lines)


# ============================================================
# 1b. LIUNIAN DETAILED REPORT RENDERERS (mode 7)
# ============================================================

def _stars(n):
    """Convert 1-5 score to star string."""
    n = max(1, min(5, int(n)))
    return '★' * n + '☆' * (5 - n)


def render_liunian_overview(overview, liunian_info, dayun_info):
    """Render 年运总览 section."""
    lines = []
    lines.append('## 一、年运总览\n')

    # Liunian stem-branch interpretation
    lg = liunian_info.get('ganzhi', '')
    ls = liunian_info.get('shishen', '')
    dy = dayun_info or {}
    dy_ganzhi = f'{dy.get("gan","")}{dy.get("zhi","")}' if dy else ''
    lines.append(f'流年**{lg}**，十神为**{ls}**。')
    if dy_ganzhi:
        lines.append(f'当前正行**{dy_ganzhi}**大运（{dy.get("start_age","?")}-{dy.get("end_age","?")}岁）。')
    lines.append('')

    # Star ratings table
    avg = overview.get('avg_scores', {})
    lines.append('| 维度 | 评分 |')
    lines.append('|------|------|')
    for dim in ['career', 'wealth', 'love', 'health']:
        score = avg.get(dim, 0)
        label = {'career': '事业', 'wealth': '财运', 'love': '感情', 'health': '健康'}[dim]
        lines.append(f'| {label} | {_stars(score)} |')
    total = sum(avg.values()) / max(len(avg), 1)
    lines.append(f'| **综合** | **{_stars(round(total))}** |')
    lines.append('')

    # Key themes
    themes = overview.get('key_themes', [])
    if themes:
        lines.append('**年度主题：** ' + '、'.join(themes))
        lines.append('')
    return '\n'.join(lines)


def render_liunian_monthly_table(months):
    """Render 逐月详解 12-month detailed table."""
    lines = []
    lines.append('## 二、逐月详解\n')
    lines.append('| 月 | 干支 | 十神 | 评分 | 事业 | 财运 | 感情 | 健康 | 神煞 | 宜 | 忌 |')
    lines.append('|------|------|------|------|------|------|------|------|------|----|----|')
    for m in months:
        sz = _stars(m.get('overall_score', 3))
        shensha = ','.join(m.get('shensha', [])[:2]) or '—'
        yi = ','.join(m.get('yi', [])[:2]) or '—'
        ji = ','.join(m.get('ji', [])[:2]) or '—'
        lines.append(
            f'| {m.get("month","")} | {m.get("ganzhi","")} | {m.get("shishen","")} | '
            f'{sz} | {_stars(m.get("career",{}).get("score",3))} | '
            f'{_stars(m.get("wealth",{}).get("score",3))} | '
            f'{_stars(m.get("love",{}).get("score",3))} | '
            f'{_stars(m.get("health",{}).get("score",3))} | '
            f'{shensha} | {yi} | {ji} |')
    lines.append('')
    return '\n'.join(lines)


def render_liunian_quarterly(months, overview):
    """Render 季度运势 section."""
    lines = []
    lines.append('## 三、季度运势\n')
    q_labels = [('春', 1, 3), ('夏', 4, 6), ('秋', 7, 9), ('冬', 10, 12)]
    best_month = overview.get('best_month', {}).get('month', '')
    worst_month = overview.get('worst_month', {}).get('month', '')

    lines.append('| 季度 | 月份 | 平均评分 | 亮点月 | 需注意 |')
    lines.append('|------|------|---------|--------|--------|')
    for qname, start, end in q_labels:
        qm = [m for m in months if start <= m.get('month', 0) <= end]
        if not qm:
            continue
        avg = sum(m.get('overall_score', 50) for m in qm) / len(qm)
        highlights = [str(m['month']) for m in qm if str(m.get('month','')) == str(best_month)]
        cautions = [str(m['month']) for m in qm if str(m.get('month','')) == str(worst_month)]
        lines.append(f'| {qname} | {start}-{end}月 | {_stars(round(avg))} | '
                     f'{",".join(highlights) if highlights else "—"}月 | '
                     f'{",".join(cautions) if cautions else "—"}月 |')
    lines.append('')
    return '\n'.join(lines)


def render_liunian_best_months(months, overview):
    """Render 最佳月份 section."""
    lines = []
    lines.append('## 四、最佳月份详解\n')
    good = overview.get('good_months', [])[:3]
    if not good:
        # Fallback: top 3 by overall_score
        sorted_months = sorted(months, key=lambda m: m.get('overall_score', 0), reverse=True)
        good = [m['month'] for m in sorted_months[:3]]
    for mn in good:
        m = next((x for x in months if x.get('month') == mn), None)
        if m:
            interactions = '、'.join(m.get('interactions', [])) or '无特殊冲合'
            lines.append(f'1. **{mn}月（{m.get("ganzhi","")}，{m.get("shishen","")}）**')
            lines.append(f'   综合评分 {m.get("overall_score","")}，{interactions}。')
            if m.get('career', {}).get('notes'):
                lines.append(f'   事业：{m["career"]["notes"]}')
            if m.get('wealth', {}).get('notes'):
                lines.append(f'   财运：{m["wealth"]["notes"]}')
            lines.append('')
    return '\n'.join(lines)


def render_liunian_caution_months(months, overview):
    """Render 高风险月份 section."""
    lines = []
    lines.append('## 五、高风险月份与化解\n')
    caution = overview.get('caution_months', [])[:3]
    if not caution:
        sorted_months = sorted(months, key=lambda m: m.get('overall_score', 100))
        caution = [m['month'] for m in sorted_months[:2]]
    for mn in caution:
        m = next((x for x in months if x.get('month') == mn), None)
        if m:
            risks = '、'.join(m.get('interactions', [])) or '评分偏低'
            lines.append(f'1. **{mn}月（{m.get("ganzhi","")}，{m.get("shishen","")}）**')
            lines.append(f'   风险：{risks}。')
            lines.append(f'   化解：保持低调，避免重大决策。可参考宜忌调整日常安排。')
            lines.append('')
    return '\n'.join(lines)


def render_liunian_recommendations(recommendations):
    """Render 年度建言 section."""
    lines = []
    lines.append('## 六、年度建言\n')
    if isinstance(recommendations, list):
        for i, r in enumerate(recommendations):
            if isinstance(r, dict):
                lines.append(f'{i+1}. **【{r.get("priority","建议")}】** {r.get("text","")}')
            else:
                lines.append(f'{i+1}. {str(r)}')
    else:
        lines.append(str(recommendations))
    lines.append('')
    return '\n'.join(lines)


def build_mode7_report(chart, conclusions):
    """Build Mode 7 (流年详批) report.

    Expects conclusions to have:
        - overview: from generate_year_calendar() output
        - months: list of 12 month dicts
        - liunian_info: {ganzhi, shishen}
        - dayun_info: current dayun pillar dict
        - recommendations: list of advice items
    """
    fp = chart['four_pillars']
    dm = chart.get('day_master', {})
    bi = chart.get('birth_info', {})
    dm_gan = dm.get('gan', '') if isinstance(dm, dict) else str(dm)

    overview = conclusions.get('overview', {})
    months = conclusions.get('months', [])
    liunian_info = conclusions.get('liunian_info', {})
    dayun_info = conclusions.get('dayun_info') or conclusions.get('current_dayun', {})
    recommendations = conclusions.get('recommendations', [])
    target_year = conclusions.get('target_year', bi.get('year', date.today().year))

    bdate = f'{bi.get("year","")}-{bi.get("month",""):02d}-{bi.get("day",""):02d}' if bi.get('year') else '未知'

    s = []
    s.append(f'# 【{target_year}年 流年详批报告】\n')
    s.append(f'命主：{bdate} 出生 | 日主{dm_gan}（{dm.get("wuxing","")}）\n')
    s.append(render_liunian_overview(overview, liunian_info, dayun_info))
    s.append(render_liunian_monthly_table(months))
    s.append(render_liunian_quarterly(months, overview))
    s.append(render_liunian_best_months(months, overview))
    s.append(render_liunian_caution_months(months, overview))
    s.append(render_liunian_recommendations(recommendations))
    return '\n'.join(s)


def build_mode1_report(chart, conclusions):
    """Build Mode 1 (子平真诠) report."""
    fp = chart['four_pillars']
    dm = chart['day_master']
    dy = chart['da_yun']
    bi = chart.get('birth_info', {})
    ty = chart.get('tai_yuan', {})
    mg = chart.get('ming_gong', {})
    sg = chart.get('shen_gong', {})

    gender = bi.get('gender', 'male')
    bdate = f'{bi.get("year","")}-{bi.get("month",""):02d}-{bi.get("day",""):02d}'

    sections = []
    sections.append(f'# 【子平真诠 · 格局命理深度报告】\n')
    sections.append(f'命主：{gender} | 出生：{bdate} | 真太阳时：北京时间\n')

    sections.append('## 一、八字排盘')
    sections.append(render_chart_table(fp, dm, dy, ty, mg, sg))

    sections.append('## 二、旺衰量化')
    sections.append(render_wangshuai(conclusions.get('wangshuai', {})))

    sections.append('## 三、月令提纲与格局判定')
    sections.append(render_pattern(conclusions.get('pattern', {})))

    sections.append('## 四、六位用神体系')
    sections.append(render_yongshen(conclusions.get('yongshen', {})))

    sections.append('## 五、行运分析')
    sections.append(render_dayun_table(dy))
    sections.append(render_liunian_table(conclusions.get('liunian', {})))

    sections.append('## 六、七维人生解读')
    sections.append(render_seven_dims(conclusions.get('seven_dims', {})))

    sections.append('## 七、纳音气质与补益')
    nayin = conclusions.get('nayin', {})
    sections.append(f'- **年柱纳音**: {nayin.get("year_nayin","")} — {nayin.get("description","")}')
    sections.append(f'- **五行补益**: {nayin.get("advice","")}')

    sections.append('## 八、双系统交叉验证 (子平真诠 × 盲派)')
    sections.append(render_cross_validation(conclusions.get('cross_validation', {}), '子平真诠', '盲派'))

    sections.append('## 九、命理依据溯源')
    sections.append(render_source_tracing(conclusions.get('source_tracing', [])))
    jt = render_judgments(conclusions.get('judgments', []))
    if jt: sections.append(jt)

    portrait = render_portrait(conclusions.get('portrait', {}))
    if portrait:
        sections.append('## 十、命主画像')
        sections.append(portrait)

    sections.append(f'## 十{"一" if portrait else ""}、免责声明')
    sections.append('> 本报告中的任何「吉凶」「运势」「应期」判断均为传统命理理论在特定干支组合下的学术推演，'
                   '不代表对未发生事件的断言，不构成任何形式的预测、建议或决策依据。')

    return '\n\n'.join(sections)


# ============================================================
# 2b. Mode 2: 滴天髓
# ============================================================

def build_mode2_report(chart, conclusions):
    fp = chart['four_pillars']
    dm = chart['day_master']
    dy = chart['da_yun']
    bi = chart.get('birth_info', {})
    ty = chart.get('tai_yuan', {})
    mg = chart.get('ming_gong', {})
    sg = chart.get('shen_gong', {})
    gender = bi.get('gender', 'male')
    bdate = f'{bi.get("year","")}-{bi.get("month",""):02d}-{bi.get("day",""):02d}'

    s = []
    s.append('# 【滴天髓 · 五行辨证深度报告】\n')
    s.append(f'命主：{gender} | 出生：{bdate}\n')

    s.append('## 一、八字排盘 + 旺衰量化')
    s.append(render_chart_table(fp, dm, dy, ty, mg, sg))
    s.append(render_wangshuai(conclusions.get('wangshuai', {})))

    s.append('## 二、日主气势分析')
    qi = conclusions.get('qi_analysis', {})
    s.append(f'- **日主**: {dm.get("gan","")}（{dm.get("yinyang","")}{dm.get("wuxing","")}）')
    s.append(f'- **十二长生**: {qi.get("changsheng","")} — {qi.get("changsheng_meaning","")}')
    s.append(f'- **从格判定**: {qi.get("cong_ge","")}')

    s.append('## 三、五行真假分析')
    wtf = conclusions.get('wuxing_true_false', '')
    s.append(json.dumps(wtf, ensure_ascii=False) if isinstance(wtf, dict) else str(wtf))

    s.append('## 四、五行源流')
    sf = conclusions.get('source_flow', '')
    s.append(json.dumps(sf, ensure_ascii=False) if isinstance(sf, dict) else str(sf))

    s.append('## 五、中和评估')
    bal = conclusions.get('balance', '')
    s.append(json.dumps(bal, ensure_ascii=False) if isinstance(bal, dict) else str(bal))

    s.append('## 六、寒暖燥湿')
    cw = conclusions.get('cold_warm', '')
    s.append(json.dumps(cw, ensure_ascii=False) if isinstance(cw, dict) else str(cw))

    s.append('## 七、清浊判断')
    cl = conclusions.get('clarity', '')
    s.append(json.dumps(cl, ensure_ascii=False) if isinstance(cl, dict) else str(cl))

    s.append('## 八、辨证七论')
    st = conclusions.get('seven_topics', '')
    s.append(json.dumps(st, ensure_ascii=False) if isinstance(st, dict) else str(st))

    s.append('## 九、命局层次总结')
    ts = conclusions.get('tier_summary', '')
    s.append(json.dumps(ts, ensure_ascii=False) if isinstance(ts, dict) else str(ts))

    s.append('## 十、五行调候与补益')
    nayin = conclusions.get('nayin', {})
    s.append(f'- 补益: {nayin.get("advice","")}')

    s.append('## 十一、命理依据溯源')
    s.append(render_source_tracing(conclusions.get('source_tracing', [])))
    jt = render_judgments(conclusions.get('judgments', []))
    if jt: s.append(jt)

    s.append('## 十二、双系统交叉验证 (滴天髓 × 子平真诠)')
    s.append(render_cross_validation(conclusions.get('cross_validation', {}), '滴天髓', '子平真诠'))

    portrait = render_portrait(conclusions.get('portrait', {}))
    if portrait:
        s.append('## 十三、命主画像')
        s.append(portrait)
    dis_num = '十四' if portrait else '十三'
    s.append(f'## {dis_num}、免责声明')
    s.append('> 本报告中的任何「吉凶」「运势」「应期」判断均为传统命理理论在特定干支组合下的学术推演，不代表对未发生事件的断言，不构成任何形式的预测、建议或决策依据。')

    return '\n\n'.join(s)


# ============================================================
# 2c. Mode 3: 紫微斗数
# ============================================================

def build_mode3_report(chart, conclusions):
    fp = chart['four_pillars']
    dm = chart['day_master']
    dy = chart['da_yun']
    bi = chart.get('birth_info', {})
    ziwei = chart.get('ziwei', {})
    gender = bi.get('gender', 'male')
    bdate = f'{bi.get("year","")}-{bi.get("month",""):02d}-{bi.get("day",""):02d}'

    s = []
    s.append('# 【紫微斗数 · 十二宫星曜深度报告】\n')
    s.append(f'命主：{gender} | 出生：{bdate}\n')

    s.append('## 一、命盘综述')
    zw = conclusions.get('ziwei_summary', {})
    s.append(f'- **命宫**: {zw.get("ming_gong","")} — {zw.get("main_star","")}')
    s.append(f'- **身宫**: {zw.get("shen_gong","")}')
    s.append(f'- **五行局**: {zw.get("wuxing_ju","")}')
    s.append(f'- **格局**: {zw.get("pattern","")}')

    s.append('## 二、十二宫逐宫精析')
    tp = conclusions.get('twelve_palaces', '')
    s.append(json.dumps(tp, ensure_ascii=False) if isinstance(tp, (dict, list)) else str(tp))

    s.append('## 三、四化飞星')
    sh = conclusions.get('si_hua', '')
    s.append(json.dumps(sh, ensure_ascii=False) if isinstance(sh, (dict, list)) else str(sh))

    s.append('## 四、当前大限专题')
    dx = conclusions.get('daxian', '')
    s.append(json.dumps(dx, ensure_ascii=False) if isinstance(dx, dict) else str(dx))

    s.append('## 五、双系统交叉验证 (紫微斗数 × 盲派)')
    s.append(render_cross_validation(conclusions.get('cross_validation', {}), '紫微斗数', '盲派'))

    portrait = render_portrait(conclusions.get('portrait', {}))
    if portrait:
        s.append('## 六、命主画像')
        s.append(portrait)
    dis_num = '七' if portrait else '六'
    s.append(f'## {dis_num}、免责声明')
    s.append('> 本报告中的任何「吉凶」「运势」「应期」判断均为传统命理理论在特定干支组合下的学术推演，不代表对未发生事件的断言，不构成任何形式的预测、建议或决策依据。')

    return '\n\n'.join(s)


# ============================================================
# 2d. Mode 4: 盲派
# ============================================================

def build_mode4_report(chart, conclusions):
    fp = chart['four_pillars']
    dm = chart['day_master']
    dy = chart['da_yun']
    bi = chart.get('birth_info', {})
    ty = chart.get('tai_yuan', {})
    mg = chart.get('ming_gong', {})
    sg = chart.get('shen_gong', {})
    gender = bi.get('gender', 'male')
    bdate = f'{bi.get("year","")}-{bi.get("month",""):02d}-{bi.get("day",""):02d}'

    s = []
    s.append('# 【盲派 · 做功象意实战报告】\n')
    s.append(f'命主：{gender} | 出生：{bdate}\n')

    s.append('## 一、八字排盘')
    s.append(render_chart_table(fp, dm, dy, ty, mg, sg))

    s.append('## 二、做功分析')
    s.append(conclusions.get('zuo_gong', ''))

    s.append('## 三、宾主分析')
    s.append(conclusions.get('bin_zhu', ''))

    s.append('## 四、财官实战')
    s.append(conclusions.get('cai_guan', ''))

    s.append('## 五、应期预报')
    s.append(conclusions.get('ying_qi', ''))

    s.append('## 六、关键人生节点')
    s.append(conclusions.get('key_nodes', ''))

    s.append('## 七、双系统交叉验证 (盲派 × 子平真诠)')
    s.append(render_cross_validation(conclusions.get('cross_validation', {}), '盲派', '子平真诠'))

    portrait = render_portrait(conclusions.get('portrait', {}))
    if portrait:
        s.append('## 八、命主画像')
        s.append(portrait)
    dis_num = '九' if portrait else '八'
    s.append(f'## {dis_num}、免责声明')
    s.append('> 本报告中的任何「吉凶」「运势」「应期」判断均为传统命理理论在特定干支组合下的学术推演，不代表对未发生事件的断言，不构成任何形式的预测、建议或决策依据。')

    return '\n\n'.join(s)


# ============================================================
# 2e. Mode 5: 四合出
# ============================================================

def build_mode5_report(chart, conclusions):
    bi = chart.get('birth_info', {})
    gender = bi.get('gender', 'male')
    bdate = f'{bi.get("year","")}-{bi.get("month",""):02d}-{bi.get("day",""):02d}'

    s = []
    s.append('# 【四派综合分析 · 四合出报告】\n')
    s.append(f'命主：{gender} | 出生：{bdate}\n')

    s.append('## 共识结论')
    s.append(conclusions.get('consensus', ''))

    s.append('## 旺衰量化基准')
    s.append(render_wangshuai(conclusions.get('wangshuai', {})))

    s.append('## 各派要点对比')
    s.append(conclusions.get('schools_comparison', ''))

    s.append('## 星平合参（八字←→紫微交叉验证）')
    s.append(conclusions.get('xing_ping', ''))

    s.append('## 分歧说明')
    s.append(conclusions.get('divergence_full', ''))

    s.append('## 应期共识')
    s.append(conclusions.get('ying_qi_consensus', ''))

    portrait = render_portrait(conclusions.get('portrait', {}))
    if portrait:
        s.append('## 命主画像')
        s.append(portrait)

    s.append('## 纳音气质 + 五行补益')
    nayin = conclusions.get('nayin', {})
    s.append(f'- **年柱纳音**: {nayin.get("year_nayin","")}')
    s.append(f'- **纳音解读**: {nayin.get("description","")}')
    s.append(f'- **五行补益**: {nayin.get("advice","")}')

    s.append('## 双系统交叉验证 (子平真诠 × 盲派)')
    s.append(render_cross_validation(conclusions.get('cross_validation', {}), '子平真诠', '盲派'))

    s.append('## 命理依据溯源')
    s.append(render_source_tracing(conclusions.get('source_tracing', [])))
    jt = render_judgments(conclusions.get('judgments', []))
    if jt: s.append(jt)

    s.append('## 免责声明')
    s.append('> 本报告中的任何「吉凶」「运势」「应期」判断均为传统命理理论在特定干支组合下的学术推演，不代表对未发生事件的断言，不构成任何形式的预测、建议或决策依据。')

    return '\n\n'.join(s)


# ============================================================
# 2f. Mode 6: 合婚
# ============================================================

def build_mode6_report(chart, conclusions):
    p1 = conclusions.get('person1', {})
    p2 = conclusions.get('person2', {})
    bi1 = p1.get('birth_info', {})
    bi2 = p2.get('birth_info', {})
    gender1 = bi1.get('gender', 'male')
    gender2 = bi2.get('gender', 'female')
    bdate1 = f'{bi1.get("year","")}-{bi1.get("month",""):02d}-{bi1.get("day",""):02d}'
    bdate2 = f'{bi2.get("year","")}-{bi2.get("month",""):02d}-{bi2.get("day",""):02d}'

    s = []
    s.append('# 【合婚分析 · 双盘对比深度报告】\n')
    s.append(f'甲方：{gender1} | 出生：{bdate1} | 日主：{p1.get("day_master","")}')
    s.append(f'乙方：{gender2} | 出生：{bdate2} | 日主：{p2.get("day_master","")}\n')

    s.append('## 一、甲方八字排盘')
    s.append(conclusions.get('chart1_display', ''))

    s.append('## 二、甲方核心命理')
    s.append(conclusions.get('person1_core', ''))

    s.append('## 三、乙方八字排盘')
    s.append(conclusions.get('chart2_display', ''))

    s.append('## 四、乙方核心命理')
    s.append(conclusions.get('person2_core', ''))

    s.append('## 五、日主旺衰对比')
    s.append(conclusions.get('wangshuai_compare', ''))

    s.append('## 六、日支婚宫互动')
    s.append(conclusions.get('rizhu_interaction', ''))

    s.append('## 七、配偶星交叉')
    s.append(conclusions.get('spouse_star', ''))

    s.append('## 八、用神互补性')
    s.append(conclusions.get('xishen_complement', ''))

    s.append('## 九、纳音气场 + 天干合化')
    s.append(conclusions.get('nayin_hehua', ''))

    s.append('## 十、大运同步性')
    s.append(conclusions.get('dayun_sync', ''))

    s.append('## 十一、双系统交叉验证')
    s.append(conclusions.get('cross_validation_text', ''))

    s.append('## 十二、综合判断')
    s.append(conclusions.get('final_judgment', ''))

    portrait = render_portrait(conclusions.get('portrait', {}))
    if portrait:
        s.append('## 十三、命主画像')
        s.append(portrait)
    dis_num = '十四' if portrait else '十三'
    s.append(f'## {dis_num}、免责声明')
    s.append('> 本报告中的任何「吉凶」「运势」「应期」判断均为传统命理理论在特定干支组合下的学术推演，不代表对未发生事件的断言，不构成任何形式的预测、建议或决策依据。合婚分析仅供参考，婚姻幸福取决于双方的用心经营。')

    return '\n\n'.join(s)


# ============================================================
# 3. GENERIC REPORT BUILDER (any mode)
# ============================================================

REPORT_BUILDERS = {
    1: build_mode1_report,
    2: build_mode2_report,
    3: build_mode3_report,
    4: build_mode4_report,
    5: build_mode5_report,
    6: build_mode6_report,
    7: build_mode7_report,
}


def build_report(chart_path, mode, conclusions_path, output_path=None):
    """Build complete markdown report from chart + conclusions."""
    with open(chart_path, 'r', encoding='utf-8') as f:
        chart = json.load(f)
    with open(conclusions_path, 'r', encoding='utf-8') as f:
        conclusions = json.load(f)

    builder = REPORT_BUILDERS.get(mode, build_mode1_report)
    report = builder(chart, conclusions)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        return output_path
    return report


# ============================================================
# 4. CONCLUSIONS SCHEMA (for Agent reference)
# ============================================================

CONCLUSIONS_SCHEMA = {
    "wangshuai": {
        "得令": {"score": "35/50", "note": "月令未土不生丁火"},
        "得地": {"score": "18/25", "note": "日支酉金无根"},
        "得势": {"score": "12/20", "note": "天干无丙丁"},
        "远近": {"score": "3/5", "note": "时干有助"},
        "total": "68",
        "grade": "身强"
    },
    "pattern": {
        "name": "正官格",
        "sub_name": "",
        "category": "正格",
        "verdict": "成格",
        "break_flag": "无",
        "reasoning": "月令本气为己土→七杀格。但年干透甲木正印，杀印相生..."
    },
    "yongshen": {
        "用神": {"ganzhi": "甲木(正印)", "note": "化杀生身，格局枢纽"},
        "相神": {"ganzhi": "庚金(正财)", "note": "生官护印"},
        "喜神": {"ganzhi": "壬水(正官)", "note": "官印相生"},
        "忌神": {"ganzhi": "丙火(劫财)", "note": "比劫夺财"},
        "仇神": {"ganzhi": "", "note": ""},
        "闲神": {"ganzhi": "", "note": ""},
        "assessment": "用神甲木得年干透出，有亥中甲根，用神有力。..."
    },
    "liunian": {
        "years": [
            {"year": "2026", "ganzhi": "丙午", "dayun_rel": "大运生流年",
             "yongshen": "用神受生", "focus": "事业/财运", "ji_xiong": "大吉"},
        ],
        "note": "当前大运壬戌(42-51岁): 壬水正官+戌土..."
    },
    "seven_dims": {
        "personality": {"stars": 4, "summary": "外柔内刚，思维缜密",
                        "analysis": "丁火日主坐酉金偏财..."},
        "career": {"stars": 4, "summary": "宜文职管理，体制内发展",
                   "analysis": "正官格配正印..."},
        "wealth": {"stars": 3, "summary": "正财稳定，偏财勿求",
                   "analysis": "..."},
        "love": {"stars": 3, "summary": "...", "analysis": "..."},
        "health": {"stars": 3, "summary": "...", "analysis": "..."},
        "study": {"stars": 4, "summary": "...", "analysis": "..."},
        "liunian": {"stars": 4, "summary": "...", "analysis": "..."}
    },
    "cross_validation": {
        "旺衰": {"primary": "身强(68分)", "secondary": "中功(财星有根)", "result": "✅"},
        "格局/层次": {"primary": "正官格成格,中上", "secondary": "财官功,中上", "result": "✅"},
        "事业方向": {"primary": "文职管理", "secondary": "财官体制", "result": "✅"},
        "财运判断": {"primary": "正财为主", "secondary": "财星有根", "result": "✅"},
        "婚姻质量": {"primary": "日支偏财", "secondary": "日支无冲", "result": "✅"},
        "divergence": ""  # Only filled if there's real divergence
    },
    "nayin": {
        "year_nayin": "剑锋金",
        "description": "刚硬锋利，需火煅之",
        "advice": "颜色:红/紫 方位:南 行业:文化/教育"
    },
    "source_tracing": [
        {"conclusion": "正官格", "basis": "月令本气为己土", "source": "《子平真诠》论正官"},
        {"conclusion": "用神甲木", "basis": "身旺+正官格→用印", "source": "《子平真诠》论用神"},
    ],
    "portrait": {
        "narrative": "您是一位外表温和、内心坚韧的人。丁火日主赋予您敏锐的感知力...\n\n"
                      "少年时期（0-16岁）：年柱XX为您打下了...的基础。\n"
                      "青年时期（17-32岁）：月柱XX带来...\n"
                      "中年时期（33-48岁）：日柱XX是您人生的核心阶段...\n"
                      "晚年时期（49岁+）：时柱XX预示...\n\n"
                      "当前大运（XX岁-XX岁）：这十年您将...\n"
                      "未来三年：2026年您可能...2027年...2028年...",
        "advice": "建议您在XX方面多留意，XX年是重要转折点。"
    }
}


# ============================================================
# 5. CLI
# ============================================================

def main():
    ap = argparse.ArgumentParser(description='Report Builder — structured conclusions → markdown')
    ap.add_argument('--chart', '-c', required=True, help='Chart JSON from calculator')
    ap.add_argument('--mode', '-m', type=int, default=1, help='Analysis mode (1-6)')
    ap.add_argument('--conclusions', '-j', required=True, help='Conclusions JSON from Agent')
    ap.add_argument('--output', '-o', required=True, help='Output markdown file')
    ap.add_argument('--schema', action='store_true', help='Print conclusions JSON schema')
    args = ap.parse_args()

    if args.schema:
        print(json.dumps(CONCLUSIONS_SCHEMA, ensure_ascii=False, indent=2))
        return

    build_report(args.chart, args.mode, args.conclusions, args.output)
    size = os.path.getsize(args.output)
    print(f'Report built: {args.output} ({size} bytes)')


if __name__ == '__main__':
    main()
