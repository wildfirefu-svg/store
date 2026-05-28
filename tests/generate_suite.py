"""Generate comprehensive test suite: coverage matrix + calendar + real persons."""
import json, os, random
from datetime import date

TIANGAN = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
DIZHI = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
ref = date(1900, 1, 1)

def get_day_pillar(y, m, d):
    days = (date(y, m, d) - ref).days
    idx = (days + 10) % 60
    return TIANGAN[idx%10] + DIZHI[idx%12]

# ===== 1. Coverage Matrix (~750) =====
coverage = []
for year in range(1950, 2051, 5):
    for month in [1, 4, 7, 10]:
        for day in [1, 15]:
            for hour in [0, 6, 12, 18, 23]:
                for gender in ['male', 'female']:
                    dp = get_day_pillar(year, month, day)
                    coverage.append({
                        'id': f'COV{len(coverage)+1:04d}',
                        'year': year, 'month': month, 'day': day,
                        'hour': hour, 'gender': gender,
                        'expected': {'day': dp, 'day_master': dp[0]},
                        'note': f'覆盖矩阵-{year}-{month:02d}'
                    })

# Deduplicate dates, keep varied hours
seen = set()
uniq = []
for c in coverage:
    k = (c['year'], c['month'], c['day'])
    if k not in seen or len(uniq) < 700:
        seen.add(k)
        uniq.append(c)
coverage = uniq[:750]

# ===== 2. Calendar Verification (~220) =====
calendar = []
for year in range(1950, 2051):
    for month in range(1, 13):
        for day in [1, 15]:
            dp = get_day_pillar(year, month, day)
            eff_year = year if not (month == 1 or (month == 2 and day < 4)) else year - 1
            yp_idx = (eff_year - 4) % 60
            yp = TIANGAN[yp_idx%10] + DIZHI[yp_idx%12]
            calendar.append({
                'id': f'CAL{len(calendar)+1:04d}',
                'year': year, 'month': month, 'day': day,
                'hour': 12, 'gender': 'male',
                'expected': {'year': yp, 'day': dp, 'day_master': dp[0]},
                'note': f'万年历-{year}-{month:02d}-{day:02d}'
            })

random.seed(42)
calendar = random.sample(calendar, min(220, len(calendar)))

# ===== 3. Real Persons (~50 in 1900-2100 range) =====
persons_raw = [
    ('毛泽东',1893,12,26,8,'male'),('周恩来',1898,3,5,8,'male'),
    ('邓小平',1904,8,22,8,'male'),('鲁迅',1881,9,25,8,'male'),
    ('钱学森',1911,12,11,8,'male'),('袁隆平',1930,9,7,8,'male'),
    ('屠呦呦',1930,12,30,8,'female'),('杨振宁',1922,10,1,8,'male'),
    ('金庸',1924,3,10,8,'male'),('李小龙',1940,11,27,7,'male'),
    ('成龙',1954,4,7,8,'male'),('周星驰',1962,6,22,8,'male'),
    ('周杰伦',1979,1,18,8,'male'),('马云',1964,9,10,8,'male'),
    ('马化腾',1971,10,29,8,'male'),('任正非',1944,10,25,8,'male'),
    ('姚明',1980,9,12,8,'male'),('刘翔',1983,7,13,8,'male'),
    ('王菲',1969,8,8,8,'female'),('张国荣',1956,9,12,8,'male'),
    ('梅艳芳',1963,10,10,8,'female'),('邓丽君',1953,1,29,8,'female'),
    ('乔布斯',1955,2,24,8,'male'),('比尔盖茨',1955,10,28,22,'male'),
    ('马斯克',1971,6,28,8,'male'),('爱因斯坦',1879,3,14,11,'male'),
    ('曼德拉',1918,7,18,8,'male'),('居里夫人',1867,11,7,8,'female'),
    ('孙中山',1866,11,12,8,'male'),('蒋介石',1887,10,31,12,'male'),
    ('李政道',1926,11,24,8,'male'),('郎朗',1982,6,14,8,'male'),
    ('刘德华',1961,9,27,8,'male'),('张学友',1961,7,10,8,'male'),
    ('郭富城',1965,10,26,8,'male'),('黎明',1966,12,11,8,'male'),
    ('林青霞',1954,11,3,8,'female'),('张曼玉',1964,9,20,8,'female'),
    ('巩俐',1965,12,31,8,'female'),('章子怡',1979,2,9,8,'female'),
    ('李连杰',1963,4,26,8,'male'),('甄子丹',1963,7,27,8,'male'),
    ('吴京',1974,4,3,8,'male'),('黄家驹',1962,6,10,8,'male'),
    ('崔健',1961,8,2,8,'male'),('窦唯',1969,10,14,8,'male'),
    ('雷军',1969,12,16,8,'male'),('刘强东',1973,3,10,8,'male'),
    ('张一鸣',1983,4,1,8,'male'),('王兴',1979,2,18,8,'male'),
]

persons = []
for name, y, m, d, h, g in persons_raw:
    if y < 1900 or y > 2100:
        continue
    dp = get_day_pillar(y, m, d)
    eff_year = y if not (m == 1 or (m == 2 and d < 4)) else y - 1
    yp_idx = (eff_year - 4) % 60
    yp = TIANGAN[yp_idx%10] + DIZHI[yp_idx%12]
    persons.append({
        'id': f'PER{len(persons)+1:03d}',
        'year': y, 'month': m, 'day': d,
        'hour': h, 'gender': g,
        'expected': {'year': yp, 'day': dp, 'day_master': dp[0]},
        'note': name
    })

# Merge
all_cases = coverage + calendar + persons
dataset = {
    '$schema': 'P5 comprehensive test suite',
    'description': f'Coverage({len(coverage)}) + Calendar({len(calendar)}) + Persons({len(persons)}) = {len(all_cases)}',
    'test_cases': all_cases,
    'validation_rules': {'year':'0','month':'0','day':'0','hour':'0','day_master':'0','dayun_dir':'0'}
}

path = os.path.join(os.path.dirname(__file__), 'test_suite.json')
with open(path, 'w', encoding='utf-8') as f:
    json.dump(dataset, f, ensure_ascii=False, indent=1)

print(f'Saved: {len(all_cases)} cases ({os.path.getsize(path)} bytes)')
print(f'  Coverage matrix: {len(coverage)}')
print(f'  Calendar: {len(calendar)}')
print(f'  Persons: {len(persons)}')
