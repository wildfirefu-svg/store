#!/usr/bin/env python3
"""P5 Consistency Test — cross-validate 子平/滴天髓/盲派 pattern judgments."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def validate_consistency(patterns_data):
    cases = patterns_data['test_cases']
    rules = patterns_data['consistency_rules']
    results = {'total': len(cases), 'errors': [], 'warnings': []}

    for tc in cases:
        rid = tc['id']
        zp = tc['ziping']
        dt = tc['ditian']
        mp = tc['mangpai']

        # Rule 1: 旺衰一致性
        zp_ws = zp.get('yongshen_imply', '')
        dt_ws = dt['wangshuai']
        wangshuai_map = {'身旺': 3, '身强': 2, '中和': 1.5, '身弱': 1, '身衰': 0.5}
        # Check if pattern-yongshen implies specific body strength
        # 子平用神→身旺用财官, 身弱用印比
        implied_ws = None
        ys = zp.get('yongshen', '')
        if ys in '甲乙丙丁戊己庚辛壬癸':
            # This is just a placeholder check — real validation needs element analysis
            pass

        # Rule 2: 格局-做功对应
        pattern = zp['pattern']
        gong = mp['gong_type']
        # Expected mappings
        valid_mappings = {
            '正官格': ['官功', '印功'],
            '七杀格': ['官功', '印功', '无功'],
            '正财格': ['财功', '无功'],
            '偏财格': ['财功'],
            '正印格': ['印功', '无功'],
            '偏印格': ['印功', '无功'],
            '食神格': ['食伤功'],
            '伤官格': ['食伤功'],
            '建禄格': ['食伤功', '财功'],
            '月刃格': ['无功', '食伤功'],
            '官杀混杂': ['官功', '无功'],
        }
        if pattern in valid_mappings and gong not in valid_mappings[pattern]:
            results['warnings'].append({
                'id': rid, 'note': tc.get('note', ''),
                'rule': 'pattern_gong_match',
                'detail': f'{pattern} → {gong} (expected: {valid_mappings[pattern]})'
            })

        # Rule 3: 层次-功力对应
        level = zp['level']
        strength = mp['gong_strength']
        valid_levels = {
            '上格': ['大功'], '中格': ['大功', '中功'],
            '中格偏下': ['中功', '小功'], '下格': ['小功', '无功'],
        }
        if level in valid_levels and strength not in valid_levels[level]:
            results['warnings'].append({
                'id': rid, 'note': tc.get('note', ''),
                'rule': 'level_gong_match',
                'detail': f'{level} ←→ {strength}'
            })

        # Rule 4: 流通-格局相关
        flow = dt['flow']
        status = zp['status']
        valid_flow = {
            '成格': ['顺畅', '有阻'],
            '待救': ['顺畅', '有阻'],
            '破格': ['有阻', '断'],
        }
        if status in valid_flow and flow not in valid_flow[status]:
            results['errors'].append({
                'id': rid, 'note': tc.get('note', ''),
                'rule': 'flow_status_match',
                'detail': f'{status} ←→ flow={flow} (expected: {valid_flow[status]})'
            })

        # Rule 5: 无根本矛盾
        contradictions = []
        if zp['status'] == '破格' and mp['gong_strength'] == '大功':
            contradictions.append('破格不该有大功')
        if dt['wangshuai'] == '身旺' and mp['gong_strength'] == '无功' and zp['status'] == '成格':
            contradictions.append('成格身旺不该无功')
        if zp['status'] == '成格' and dt['flow'] == '断':
            contradictions.append('成格不该流断')
        for c in contradictions:
            results['errors'].append({
                'id': rid, 'note': tc.get('note', ''),
                'rule': 'no_contradiction',
                'detail': c
            })

    return results

def run():
    path = os.path.join(os.path.dirname(__file__), 'test_patterns.json')
    data = json.load(open(path, encoding='utf-8'))
    results = validate_consistency(data)

    total = results['total']
    errors = len(results['errors'])
    warnings = len(results['warnings'])
    consistency = ((total * 5) - errors * 2 - warnings) / (total * 5) * 100

    print('=== 格局一致性测试 ===')
    print(f'Total cases: {total}')
    print(f'Errors: {errors}, Warnings: {warnings}')
    print(f'Consistency score: {consistency:.1f}%')
    print()

    if errors:
        print(f'=== Errors ({errors}) ===')
        for e in results['errors']:
            print(f'  {e["id"]} ({e["note"]}): [{e["rule"]}] {e["detail"]}')
        print()
    if warnings:
        print(f'=== Warnings ({warnings}) ===')
        for w in results['warnings']:
            print(f'  {w["id"]} ({w["note"]}): [{w["rule"]}] {w["detail"]}')
        print()

    # Milestone
    if consistency >= 90:
        print(f'PASS: Consistency {consistency:.1f}% >= 90%')
    else:
        print(f'BELOW: Consistency {consistency:.1f}% — review flagged cases')

    # Save
    out = os.path.join(os.path.dirname(__file__), 'consistency_report.json')
    json.dump(results, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Report: {out}')

if __name__ == '__main__':
    run()
