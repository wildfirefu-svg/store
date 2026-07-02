#!/usr/bin/env python3
"""Manual verification helper for report generation edge cases."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bazi_calculator as bc, auto_analyzer as aa, report_builder as rb

cases = [
    {'name': '子时女',  'year': 1990, 'month': 5,  'day': 15, 'hour': 23, 'minute': 30, 'gender': 'female'},
    {'name': '早子时',  'year': 2000, 'month': 1,  'day': 1,  'hour': 0,  'minute': 30, 'gender': 'male'},
    {'name': '立春前',  'year': 2018, 'month': 2,  'day': 1,  'hour': 10, 'minute': 0,  'gender': 'male'},
    {'name': '八字全',  'year': 1985, 'month': 10, 'day': 25, 'hour': 14, 'minute': 0,  'gender': 'female'},
]

_CG = {'子':['癸'],'丑':['己','癸','辛'],'寅':['甲','丙','戊'],'卯':['乙'],
       '辰':['戊','乙','癸'],'巳':['丙','戊','庚'],'午':['丁','己'],
       '未':['己','丁','乙'],'申':['庚','壬','戊'],'酉':['辛'],
       '戌':['戊','辛','丁'],'亥':['壬','甲']}

def build(info):
    y, m, d = info['year'], info['month'], info['day']
    hr, mn = info['hour'], info['minute']
    yg, yz = bc.get_year_pillar(y, m, d, hr, mn)
    dg, dz = bc.get_day_pillar(y, m, d)
    mg, mz = bc.get_month_pillar(y, yg, m, d, hr, mn)
    hg, hz = bc.get_hour_pillar(dg, hr, mn)
    four = {}
    for key, g, z in [('year', yg, yz), ('month', mg, mz), ('day', dg, dz), ('hour', hg, hz)]:
        kw1, kw2 = bc.get_kongwang(g, z)
        cg = list(_CG.get(z, []))
        four[key] = {'gan': g, 'zhi': z, 'cang_gan': cg,
                     'shi_shen_gan': bc.get_shishen(dg, g) if key != 'day' else '',
                     'nayin': bc.NAYIN.get(g+z, ''), 'kong_wang': kw1+kw2}
    dm = {'gan': dg, 'wuxing': bc.GAN_WUXING[dg], 'yinyang': bc.GAN_YINYANG[dg]}
    wum = {'金':0,'木':0,'水':0,'火':0,'土':0}
    for g in [yg,mg,dg,hg]: wum[bc.GAN_WUXING.get(g,'')] += 1
    for z in [yz,mz,dz,hz]: wum[bc.ZHI_WUXING.get(z,'')] += 1
    ws = {'jin':wum['金'],'mu':wum['木'],'shui':wum['水'],'huo':wum['火'],'tu':wum['土'],
          'missing':[k for k,v in wum.items() if v==0], 'strongest':max(wum, key=wum.get)}
    direction = '顺行' if (info.get('gender')=='male' and bc.GAN_YINYANG.get(yg)=='阳') or \
                            (info.get('gender')=='female' and bc.GAN_YINYANG.get(yg)=='阴') else '逆行'
    gi0, zi0 = bc.TIANGAN.index(dg), bc.DIZHI.index(dz)
    dy = []
    for i in range(8):
        gi = (gi0+i+1)%10 if direction=='顺行' else (gi0-i-1)%10
        zi = (zi0+i+1)%12 if direction=='顺行' else (zi0-i-1)%12
        dy.append({'gan': bc.TIANGAN[gi], 'zhi': bc.DIZHI[zi],
                   'start_age': 8+i*10, 'end_age': 8+(i+1)*10-1,
                   'is_current': (8+i*10) <= (2026-y) < (8+(i+1)*10)})
    tyg, tyz = bc.get_taiyuan(mg, mz, yg, yz)
    return {'four_pillars': four, 'day_master': dm, 'birth_info': info,
            'wuxing_stats': ws, 'da_yun': dy,
            'dayun_summary': {'starting_age': 8, 'direction': direction},
            'tai_yuan': {'gan': tyg, 'zhi': tyz},
            'ming_gong': {'gan':'', 'zhi': bc.get_minggong(mz, hz)},
            'shen_gong': {'gan':'', 'zhi': bc.get_shengong(mz, hz)}}

print('\n=== 命主一览 ===')
print('{:8} {:8} {:20} {:8}'.format('名称', '日主', '四柱', '旺衰'))
for c in cases:
    ch = build(c)
    pillars = ' '.join(ch['four_pillars'][k]['gan']+ch['four_pillars'][k]['zhi'] for k in ['year','month','day','hour'])
    conc = aa.auto_analyze(ch)
    print('{:8} {:8} {:20} {:8}'.format(c['name'], ch['day_master']['gan']+ch['day_master']['wuxing'], pillars, conc['wangshuai']['grade']))

print('\n=== 所有命主 × 所有模式 ===')
builders = [('mode1', rb.build_mode1_report), ('mode2', rb.build_mode2_report),
            ('mode3', rb.build_mode3_report), ('mode4', rb.build_mode4_report),
            ('mode5', rb.build_mode5_report), ('mode7', rb.build_mode7_report)]
total_ok, total_fail = 0, 0
for c in cases:
    ch = build(c)
    conc = aa.auto_analyze(ch)
    line = [c['name']]
    for name, b in builders:
        try:
            r = b(ch, conc)
            ok = len(r) >= 100
            line.append('OK' if ok else 'SHORT')
            if ok: total_ok += 1
            else: total_fail += 1
        except Exception as e:
            line.append('ERR')
            total_fail += 1
            print(f'  ERROR in {c["name"]} {name}: {e}')
    print(' '.join('{:8}'.format(x) for x in line))

# 合婚
ch1, ch2 = build(cases[0]), build(cases[1])
hehun = {'person1':{'birth_info':ch1['birth_info'],'day_master':ch1['day_master']['gan']},
         'person2':{'birth_info':ch2['birth_info'],'day_master':ch2['day_master']['gan']},
         'chart1_display':'甲','chart2_display':'乙','person1_core':'身强','person2_core':'身弱',
         'wangshuai_compare':'X','rizhu_interaction':'X','spouse_star':'X','xishen_complement':'X',
         'nayin_hehua':'X','dayun_sync':'X','cross_validation_text':'X','final_judgment':'X'}
try:
    r = rb.build_mode6_report(ch1, hehun)
    if len(r) >= 100:
        print('{:8} OK'.format('合婚'))
        total_ok += 1
    else:
        print('{:8} SHORT'.format('合婚'))
        total_fail += 1
except Exception as e:
    print('{:8} ERR'.format('合婚'), e)
    total_fail += 1

print(f'\n汇总: OK={total_ok}, FAIL={total_fail}')
sys.exit(0 if total_fail == 0 else 1)
