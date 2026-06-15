#!/usr/bin/env python3
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOLAR_TERMS = os.path.join(ROOT, 'knowledge-base', 'solar_terms.json')


def load_solar_terms(path=DEFAULT_SOLAR_TERMS):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_upcoming_terms(data, today=None, days_ahead=3):
    today = today or dt.date.today()
    end = today + dt.timedelta(days=days_ahead)
    result = []
    for key, value in data.items():
        if '|' not in key or not isinstance(value, list) or len(value) < 4:
            continue
        year_text, name = key.split('|', 1)
        try:
            term_date = dt.date(int(year_text), int(value[0]), int(value[1]))
        except Exception:
            continue
        if today <= term_date <= end:
            result.append({
                'name': name,
                'date': term_date.isoformat(),
                'hour': int(value[2]),
                'minute': int(value[3]),
                'is_jie': bool(value[4]) if len(value) > 4 else None,
            })
    return sorted(result, key=lambda x: x['date'])


def generate_push_message(client_name, term_name):
    return f"{client_name} 即将进入 {term_name} 节气，可结合命盘复盘近期运势变化。"


def main():
    data = load_solar_terms(DEFAULT_SOLAR_TERMS)
    print(json.dumps(get_upcoming_terms(data), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
