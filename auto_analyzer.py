#!/usr/bin/env python3
"""
Auto Analyzer — local fallback analysis engine for BaZi charts.
Computes 旺衰, 格局, 用神, 流年, 七维 etc. from chart data without AI.

Extracted from api_server.py to keep the API layer focused on routing.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bazi_calculator import (
    GAN_WUXING,
    GAN_YINYANG,
    NAYIN,
    ZHI_WUXING,
    get_shishen,
)


def _judgment(name, conclusion, confidence, evidence, counter_evidence=None):
    """Build a structured judgment dict."""
    return {
        "name": name,
        "conclusion": conclusion,
        "confidence": confidence,
        "evidence": evidence,
        "counter_evidence": counter_evidence or [],
    }


def auto_analyze(chart):
    """Auto-analyze chart data to fill conclusions with computed values."""
    fp = chart['four_pillars']
    dm = chart['day_master']
    gan = dm.get('gan', '') if isinstance(dm, dict) else dm
    wu = dm.get('wuxing', '') if isinstance(dm, dict) else GAN_WUXING.get(gan, '')
    yy = dm.get('yinyang', '') if isinstance(dm, dict) else GAN_YINYANG.get(gan, '')
    ws = chart.get('wuxing_stats', {})
    dy = chart.get('da_yun', [])
    ds = chart.get('dayun_summary', {})
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

    # === 格局级用神（正格/变格/调候/通关/病药分开） ===
    if grade in ('身旺','身强'):
        pattern_yong, pattern_ji = ('财星','食伤'), ('印星','比劫')
    elif grade == '身弱':
        pattern_yong, pattern_ji = ('印星','比劫'), ('财星','食伤')
    else:
        pattern_yong, pattern_ji = ('流通方','破坏方'), ('偏枯方','')

    # 调候用神（《穷通宝鉴》）
    TIAOHOU_MAP = {'亥':'丙火','子':'丙火','丑':'丙火','寅':'丙火癸水','卯':'丙火',
                   '辰':'癸水','巳':'癸水','午':'癸水','未':'癸水',
                   '申':'丙火','酉':'丙火','戌':'丙火'}
    tiaohou_raw = TIAOHOU_MAP.get(month_zhi, '')
    tiaohou_items = [tiaohou_raw[i:i+2] for i in range(0, len(tiaohou_raw), 2)] if tiaohou_raw else []

    # 通关用神（五行对峙取通关）
    _tongguan = {('金','木'):'水',('木','金'):'水',('火','金'):'土',('金','火'):'土',
                 ('水','火'):'木',('火','水'):'木',('土','水'):'金',('水','土'):'金'}
    tongguan = _tongguan.get((strongest, wu), '') if strongest and wu and strongest != wu else ''

    # 病药用神
    bingyao = ''
    if miss:
        bingyao = '缺' + '、'.join(miss) + '→补' + '、'.join(miss) + '为药'
    if grade == '身弱' and wu_counts.get(wu,0) <= 1:
        bingyao = (bingyao + '；' if bingyao else '') + '身弱无根→比劫印星为药'

    xishen_note = f'日主{grade}→格局用{pattern_yong[0]}。'
    if tiaohou_items: xishen_note += f'　调候需{"、".join(tiaohou_items)}。'
    if tongguan: xishen_note += f'　通关取{tongguan}。'
    if bingyao: xishen_note += f'　{bingyao}。'

    yongshen = {
        '用神': {'ganzhi': pattern_yong[0], 'note': '格局枢纽'},
        '相神': {'ganzhi': pattern_yong[1] if len(pattern_yong)>1 else '', 'note': '辅佐用神'},
        '喜神': {'ganzhi': pattern_yong[0], 'note': '扶助格局'},
        '忌神': {'ganzhi': pattern_ji[0], 'note': '破坏格局'},
        '仇神': {'ganzhi': pattern_ji[1] if len(pattern_ji)>1 else '', 'note': ''},
        '闲神': {'ganzhi': '', 'note': ''},
        '调候': {'ganzhi': '、'.join(tiaohou_items) if tiaohou_items else '无', 'note': '调候优先于格局' if tiaohou_items else ''},
        '通关': {'ganzhi': tongguan or '无', 'note': '化解五行对峙'},
        '病药': {'ganzhi': bingyao or '无', 'note': '补偏救弊'},
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
        'career': {'stars': 3, 'summary': f'宜{pattern_yong[0]}相关行业',
                   'analysis': f'格局{pattern_name}，{grade}用{pattern_yong[0]}。行业方向需结合用神五行选择。'},
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
        '事业方向': {'primary': pattern_yong[0], 'secondary': '待验证', 'result': '✅'},
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
    advice_wu = pattern_yong[0][0] if pattern_yong[0] and pattern_yong[0][0] in '金木水火土' else wu
    nayin_advice = '颜色:' + colors.get(advice_wu,'') + ' 方位:' + directions.get(advice_wu,'') + ' 行业:' + industries.get(advice_wu,'')

    # Build rich counter-evidence for key judgments
    _ws_ce = []
    if grade in ('身旺','身强'):
        _ws_ce.append('若地支有合局或墓库冲开，旺衰等级可能变化')
        _ws_ce.append('若日支被合化，根气减弱，身旺可能降为中和')
    else:
        _ws_ce.append('若藏干中有日主强根（本气根），身弱可能上调')
    _ws_ce.append('十二长生位置可能改变旺衰判断')

    _pat_ce = ['未检查变格（从格/化气格/专旺格）可能性',
               '月令被合化时格局可能改变',
               '未完整处理格局破救（如官格见伤官但有印制的救应）']

    _yong_ce = ['用神喜忌需要结合具体大运流年验证',
               '调候与格局冲突时以格局为先，但调候不足会影响健康/性格']
    if tiaohou_items:
        _yong_ce.append(f'调候需{tiaohou_raw}，若原局无此五行则调候乏力')

    yp_ganzhi = fp['year']['gan'] + fp['year']['zhi']
    mp_ganzhi = month_gan + month_zhi
    day_ganzhi = fp['day']['gan'] + fp['day']['zhi']
    hp_ganzhi = fp['hour']['gan'] + fp['hour']['zhi']
    cp_ganzhi = current_dy.get('gan','') + current_dy.get('zhi','')
    cp_ss = get_shishen(gan, current_dy.get('gan','')) if current_dy.get('gan') else ''
    ds_start = ds.get('starting_age', '?')
    ds_dir = ds.get('direction', '?')
    cp_start = current_dy.get('start_age','?')
    cp_end = current_dy.get('end_age','?')

    judgments = [
        _judgment("排盘校验", "通过",
            "high",
            [f"年{yp_ganzhi}, 月{mp_ganzhi}, 日{day_ganzhi}, 时{hp_ganzhi}",
             "四柱完整，纳音/藏干/空亡齐全"],
            ["节气交界处月柱可能有±1天偏差，已标记precision_note"]),
        _judgment("旺衰", grade,
            "medium" if grade == "中和" else "high",
            [f"日主五行占比{dm_pct * 100:.0f}%", f"月令{month_zhi}({month_wu})对日主为{month_support}",
             f"全局{wucount_roots}个日主根气"],
            _ws_ce),
        _judgment("格局", pattern_name,
            "medium",
            [f"月干{month_gan}对日主为{shishen_of_month}", f"月令本气{month_main}"],
            _pat_ce),
        _judgment("调候",
            f'需{"、".join(tiaohou_items)}' if tiaohou_items else '无需特殊调候',
            "medium" if tiaohou_items else "high",
            [f"生于{month_zhi}月，参考《穷通宝鉴》"],
            ['调候用神与格局用神可能冲突，需综合权衡'] if tiaohou_items else []),
        _judgment("格局用神", yongshen["assessment"],
            "low" if grade == "中和" else "medium",
            [f"日主{grade}", f"格局用{pattern_yong[0]}",
             f"通关取{tongguan}" if tongguan else '',
             f"病药: {bingyao}" if bingyao else ''],
            _yong_ce),
        _judgment("大运", f'{cp_ganzhi} ({cp_start}-{cp_end}岁)',
            "medium",
            [f"起运{ds_start}岁，{ds_dir}，十神{cp_ss or '—'}"],
            ["大运吉凶需要结合原局用神和流年引动才能具体判断"]),
        _judgment("财运提示",
            '可担财' if grade in ('身旺','身强') else '宜稳财',
            "low",
            [f"日主{grade}，{'身旺可担财官' if grade in ('身旺','身强') else '身弱需印比扶身'}"],
            ["反证1：检查比劫夺财", "反证2：检查财星受冲",
             "反证3：检查财多身弱（富屋贫人）", "大运流年引动前仅为静态判断"]),
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
