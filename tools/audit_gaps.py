#!/usr/bin/env python3
"""Audit remaining gaps in the BaZi agent system."""
import json
import os

issues = []

# 1. search.py still uses JSON directly
for f in ['knowledge-base/search.py', 'knowledge-base/search_gejue.py']:
    if os.path.exists(f):
        with open(f, encoding='utf-8') as fh:
            c = fh.read()
        if 'bazi_kb' not in c:
            issues.append((f'{f} uses JSON not SQLite KB', 'medium'))

# 2. 合婚 standalone script
if not os.path.exists('knowledge-base/hehun.py'):
    issues.append(('合婚 has JSON data but no standalone .py script', 'medium'))

# 3. Tests for new modules
for t in ['test_bazi_kb.py', 'test_api.py']:
    if not os.path.exists(f'tests/{t}'):
        issues.append((f'Missing {t}', 'quick'))

# 4. case_db missing birth hours
with open('tests/case_db.json', encoding='utf-8') as f:
    db = json.load(f)
no_hour = sum(1 for c in db['cases'] if c.get('hour', 0) == 0)
issues.append((f'{no_hour}/{len(db["cases"])} cases have hour=0', 'medium'))

# 5. chuanren.py
chuanren = 'knowledge-base/chuanren.py'
if os.path.exists(chuanren):
    with open(chuanren, encoding='utf-8') as f:
        lines = f.read().count('\n') + 1
    issues.append((f'chuanren.py: {lines}L, least polished tool', 'medium'))

# 6. SYSTEM_ARCHITECTURE.md stale
arch = 'docs/SYSTEM_ARCHITECTURE.md'
if os.path.exists(arch):
    with open(arch, encoding='utf-8') as f:
        c = f.read()
    if 'api_server.py' not in c:
        issues.append(('SYSTEM_ARCHITECTURE.md missing Phase 1 updates', 'quick'))
    if 'bazi_kb.py' not in c:
        issues.append(('SYSTEM_ARCHITECTURE.md missing bazi_kb.py', 'quick'))

# 7. solar_terms verification
with open('knowledge-base/solar_terms.json', encoding='utf-8') as f:
    st = json.load(f)
entries = st.get('entries', st)
verified = sum(1 for e in entries.values() if isinstance(e, dict) and e.get('verified'))
issues.append((f'solar_terms: {verified}/{len(entries)} verified', 'low'))

# 8. Agent missing case_retrieval
agent = '.claude/agents/bazi-multi-system-reader.md'
if os.path.exists(agent):
    with open(agent, encoding='utf-8') as f:
        c = f.read()
    if 'case_retrieval' not in c.lower():
        issues.append(('Agent missing case_retrieval tool reference', 'quick'))
    if 'bazi_kb' not in c.lower():
        issues.append(('Agent missing bazi_kb reference', 'quick'))

# 9. Duplicate/overlapping search tools
search_py = sum(1 for f in os.listdir('knowledge-base') if f.startswith('search') and f.endswith('.py'))
issues.append((f'{search_py} search backends (search.py/search_gejue.py/search_vector.py) - unify to SQLite KB', 'medium'))

# 10. model quality scores
quality = 'quality/model_quality_report_v2.json'
if os.path.exists(quality):
    with open(quality, encoding='utf-8') as f:
        q = json.load(f)
    s = q.get('summary', {})
    issues.append((f'Model quality: avg={s.get("overall_avg_score",0)}, positive={s.get("positive_match_rate","0%")}', 'medium'))

print('Remaining improvement opportunities:')
print('=' * 60)
for effort in ['quick', 'medium', 'low']:
    label = {'quick': 'QUICK (<30min)', 'medium': 'MEDIUM (1-3h)', 'low': 'LOW priority'}[effort]
    print(f'\n--- {label} ---')
    for desc, eff in issues:
        if eff == effort:
            print(f'  * {desc}')
