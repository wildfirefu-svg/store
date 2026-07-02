#!/usr/bin/env python3
"""Manual verification helper for all report generation modes."""

import json, os, sys, tempfile, traceback
from datetime import datetime

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bazi_calculator as bc
import auto_analyzer as aa
import report_builder as rb


# ── 命主 ──────────────────────────────────────────────────────────────
MINGZHU = {
    'year': 1963, 'month': 7, 'day': 9, 'hour': 8, 'minute': 0,
    'gender': 'male', 'location': 'Beijing',
    'name': '测试命主',
}

HEHUN_PARTNER = {
    'year': 1993, 'month': 9, 'day': 3, 'hour': 14, 'minute': 0,
    'gender': 'female', 'location': 'Beijing',
    'name': '合婚对象',
}


def build_chart(info):
    """Use calculator functions to build a dict compatible with
    auto_analyzer + report_builder.
    """
    y, m, d = info['year'], info['month'], info['day']
    hr, mn = info['hour'], info['minute']

    y_gan, y_zhi = bc.get_year_pillar(y, m, d, hr, mn)
    d_gan, d_zhi = bc.get_day_pillar(y, m, d)
    m_gan, m_zhi = bc.get_month_pillar(y, y_gan, m, d, hr, mn)
    h_gan, h_zhi = bc.get_hour_pillar(d_gan, hr, mn)

    _CG = {'子': ['癸'], '丑': ['己', '癸', '辛'], '寅': ['甲', '丙', '戊'],
           '卯': ['乙'], '辰': ['戊', '乙', '癸'], '巳': ['丙', '戊', '庚'],
           '午': ['丁', '己'], '未': ['己', '丁', '乙'], '申': ['庚', '壬', '戊'],
           '酉': ['辛'], '戌': ['戊', '辛', '丁'], '亥': ['壬', '甲']}
    pillars = [
        ('year', y_gan, y_zhi),
        ('month', m_gan, m_zhi),
        ('day', d_gan, d_zhi),
        ('hour', h_gan, h_zhi),
    ]
    four_pillars = {}
    for key, g, z in pillars:
        kw_g, kw_z = bc.get_kongwang(g, z)
        cg = list(_CG.get(z, []))
        four_pillars[key] = {
            'gan': g, 'zhi': z,
            'cang_gan': cg,
            'shi_shen_gan': bc.get_shishen(d_gan, g) if key != 'day' else '',
            'shi_shen_zhi_main': cg[0] if cg else '',
            'nayin': bc.NAYIN.get(g + z, ''),
            'kong_wang': kw_g + kw_z,
        }

    dm = {'gan': d_gan, 'wuxing': bc.GAN_WUXING[d_gan],
          'yinyang': bc.GAN_YINYANG[d_gan]}

    # 简化五行统计
    all_gans = [y_gan, m_gan, d_gan, h_gan]
    all_zhis = [y_zhi, m_zhi, d_zhi, h_zhi]
    wu_map = {'金': 0, '木': 0, '水': 0, '火': 0, '土': 0}
    for g in all_gans:
        w = bc.GAN_WUXING.get(g, '')
        wu_map[w] = wu_map.get(w, 0) + 1
    for z in all_zhis:
        w = bc.ZHI_WUXING.get(z, '')
        wu_map[w] = wu_map.get(w, 0) + 1

    ws = {'jin': wu_map['金'], 'mu': wu_map['木'], 'shui': wu_map['水'],
          'huo': wu_map['火'], 'tu': wu_map['土']}
    ws['missing'] = [k for k, v in wu_map.items() if v == 0]
    ws['strongest'] = max(wu_map, key=wu_map.get) if any(wu_map.values()) else ''

    direction = '顺行' if (info.get('gender') == 'male' and bc.GAN_YINYANG.get(y_gan) == '阳') or \
                            (info.get('gender') == 'female' and bc.GAN_YINYANG.get(y_gan) == '阴') else '逆行'

    start_age = 8
    gan_idx = bc.TIANGAN.index(d_gan)
    zhi_idx = bc.DIZHI.index(d_zhi)
    dy = []
    for i in range(8):
        if direction == '顺行':
            gi = (gan_idx + i + 1) % 10
            zi = (zhi_idx + i + 1) % 12
        else:
            gi = (gan_idx - i - 1) % 10
            zi = (zhi_idx - i - 1) % 12
        dy.append({
            'gan': bc.TIANGAN[gi], 'zhi': bc.DIZHI[zi],
            'start_age': start_age + i * 10,
            'end_age': start_age + (i + 1) * 10 - 1,
            'is_current': (start_age + i * 10) <= (2026 - y) < (start_age + (i + 1) * 10),
        })

    ty_g, ty_z = bc.get_taiyuan(m_gan, m_zhi, y_gan, y_zhi)

    return {
        'four_pillars': four_pillars,
        'day_master': dm,
        'birth_info': info,
        'wuxing_stats': ws,
        'da_yun': dy,
        'dayun_summary': {'starting_age': start_age, 'direction': direction},
        'tai_yuan': {'gan': ty_g, 'zhi': ty_z},
        'ming_gong': {'gan': '', 'zhi': bc.get_minggong(m_zhi, h_zhi)},
        'shen_gong': {'gan': '', 'zhi': bc.get_shengong(m_zhi, h_zhi)},
    }


def check(report_text: str, min_chars: int = 200) -> dict:
    """Return a diagnostic dict for a rendered report."""
    lines = report_text.strip().split('\n')
    non_empty = [l for l in lines if l.strip()]
    return {
        'ok': len(report_text) >= min_chars,
        'chars': len(report_text),
        'lines': len(lines),
        'non_empty_lines': len(non_empty),
        'headings': sum(1 for l in non_empty if l.startswith('#')),
    }


def main():
    print(f"{'='*70}\n 测试命主: {MINGZHU['name']} "
          f"({MINGZHU['year']}-{MINGZHU['month']:02d}-{MINGZHU['day']:02d} "
          f"{MINGZHU['hour']:02d}:{MINGZHU['minute']:02d}, "
          f"{'男' if MINGZHU['gender']=='male' else '女'})\n{'='*70}")

    chart = build_chart(MINGZHU)
    conclusions = aa.auto_analyze(chart)
    print(f"✓ 八字排盘成功 - 日主: {chart['day_master']['gan']}{chart['day_master']['wuxing']}")
    print(f"  四柱: {chart['four_pillars']['year']['gan']}{chart['four_pillars']['year']['zhi']} "
          f"{chart['four_pillars']['month']['gan']}{chart['four_pillars']['month']['zhi']} "
          f"{chart['four_pillars']['day']['gan']}{chart['four_pillars']['day']['zhi']} "
          f"{chart['four_pillars']['hour']['gan']}{chart['four_pillars']['hour']['zhi']}")
    print(f"  五行统计: {json.dumps(chart['wuxing_stats'], ensure_ascii=False)}")
    print(f"  旺衰结论: {conclusions['wangshuai']['grade']}")
    print(f"  格局: {conclusions['pattern']['name']}")
    print()

    modes = {
        1: ('子平真诠 · 格局命理', rb.build_mode1_report),
        2: ('滴天髓 · 五行辨证', rb.build_mode2_report),
        3: ('紫微斗数 · 十二宫星曜', rb.build_mode3_report),
        4: ('盲派 · 做功象意', rb.build_mode4_report),
        5: ('四合出 · 综合分析', rb.build_mode5_report),
        7: ('流年详批', rb.build_mode7_report),
    }

    results = []
    for mode, (name, builder) in modes.items():
        try:
            text = builder(chart, conclusions)
            diag = check(text)
            status = 'PASS' if diag['ok'] else 'WARN'
            print(f"  [{status}] Mode {mode}: {name:<22} "
                  f"→ {diag['chars']} chars, {diag['headings']} headings, "
                  f"{diag['non_empty_lines']} lines")
            results.append((mode, name, status, diag, text))
        except Exception as exc:
            print(f"  [FAIL] Mode {mode}: {name:<22} → {type(exc).__name__}: {exc}")
            traceback.print_exc()
            results.append((mode, name, 'FAIL', {'chars': 0}, ''))

    # Mode 6 合婚测试
    print()
    try:
        chart2 = build_chart(HEHUN_PARTNER)
        hehun_concl = {
            'person1': {'birth_info': chart['birth_info'],
                        'day_master': chart['day_master']['gan']},
            'person2': {'birth_info': chart2['birth_info'],
                        'day_master': chart2['day_master']['gan']},
            'chart1_display': '甲方八字排盘（略 - 测试用）',
            'chart2_display': '乙方八字排盘（略 - 测试用）',
            'person1_core': f"日主{chart['day_master']['gan']}，"
                           f"{aa.auto_analyze(chart)['wangshuai']['grade']}",
            'person2_core': f"日主{chart2['day_master']['gan']}，"
                           f"{aa.auto_analyze(chart2)['wangshuai']['grade']}",
            'wangshuai_compare': '双方旺衰对比（测试用）',
            'rizhu_interaction': '日支互动分析（测试用）',
            'spouse_star': '配偶星交叉（测试用）',
            'xishen_complement': '用神互补性（测试用）',
            'nayin_hehua': '纳音气场 + 天干合化（测试用）',
            'dayun_sync': '大运同步性（测试用）',
            'cross_validation_text': '双系统交叉验证（测试用）',
            'final_judgment': '综合判断：参考合婚报告详情（测试用）',
        }
        text = rb.build_mode6_report(chart, hehun_concl)
        diag = check(text)
        status = 'PASS' if diag['ok'] else 'WARN'
        print(f"  [{status}] Mode 6: {'合婚分析 · 双盘对比':<22} "
              f"→ {diag['chars']} chars, {diag['headings']} headings")
        results.append((6, '合婚分析', status, diag, text))
    except Exception as exc:
        print(f"  [FAIL] Mode 6: 合婚分析 → {type(exc).__name__}: {exc}")
        traceback.print_exc()
        results.append((6, '合婚分析', 'FAIL', {'chars': 0}, ''))

    print()
    passed = sum(1 for _, _, s, _, _ in results if s == 'PASS')
    warned = sum(1 for _, _, s, _, _ in results if s == 'WARN')
    failed = sum(1 for _, _, s, _, _ in results if s == 'FAIL')
    print(f"结果: PASS={passed}, WARN={warned}, FAIL={failed}")

    # 保存示例报告到磁盘（方便人工检查）
    out_dir = os.path.join(tempfile.gettempdir(), 'bazi_report_test')
    os.makedirs(out_dir, exist_ok=True)
    for mode, name, status, diag, text in results:
        if status != 'FAIL' and text:
            safe = name.replace(' ', '_').replace('·', '_')
            path = os.path.join(out_dir, f'mode{mode}_{safe}.md')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
    print(f"\n报告样本已保存到: {out_dir}")

    # 保存 chart + conclusions JSON 供调试
    with open(os.path.join(out_dir, 'chart.json'), 'w', encoding='utf-8') as f:
        json.dump(chart, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, 'conclusions.json'), 'w', encoding='utf-8') as f:
        json.dump(conclusions, f, ensure_ascii=False, indent=2)

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
