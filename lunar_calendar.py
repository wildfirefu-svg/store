"""Chinese lunar calendar conversion — delegates to iztro_py (Python312) for accuracy.

Falls back to built-in simplified algorithm if iztro is unavailable.
"""
import json
import os
import subprocess
import sys
from datetime import date

from config import IZTRO_TIMEOUT

def _find_python():
    """Find a Python interpreter that has iztro_py installed. Returns path or None."""
    # Try current Python first (most reliable)
    candidates = [sys.executable]

    # Try common Python paths on Windows
    for ver in ["312", "311", "313", "310"]:
        candidates.append(os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Programs", "Python", f"Python{ver}", "python.exe"
        ))

    # Try plain "python" / "python3" on PATH
    for name in ["python", "python3"]:
        import shutil
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)

    for py in candidates:
        if not py or not os.path.isfile(py):
            continue
        try:
            p = subprocess.run(
                [py, "-c", "import iztro_py"],
                capture_output=True, timeout=5,
            )
            if p.returncode == 0:
                return py
        except Exception:
            continue
    return None

_IZTRO_PYTHON = _find_python()

# ── Bridge via subprocess ──────────────────────────────────────

_IZTRO_BRIDGE = r"""
import json, sys
from iztro_py.utils.calendar import solar_to_lunar
from datetime import date, timedelta

op = sys.argv[1]
if op == 's2l':
    y, m, d = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    l = solar_to_lunar(y, m, d, False)
    print(json.dumps({'ly': l.year, 'lm': l.month, 'ld': l.day, 'leap': l.is_leap_month}))
elif op == 'l2s':
    ly, lm, ld = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    is_leap = sys.argv[5] == 'True' if len(sys.argv) > 5 else False
    estimate = date(ly, 2, 1)
    for offset in range(400):
        d = estimate + timedelta(days=offset)
        l = solar_to_lunar(d.year, d.month, d.day, False)
        if l.year == ly and l.month == lm and l.day == ld and l.is_leap_month == is_leap:
            print(json.dumps({'sy': d.year, 'sm': d.month, 'sd': d.day}))
            break
    else:
        print(json.dumps({'sy': ly, 'sm': lm, 'sd': ld}))
"""


def _call_iztro(op, *args):
    """Call iztro via subprocess. Returns parsed JSON or None on failure."""
    if _IZTRO_PYTHON is None:
        return None
    try:
        p = subprocess.run(
            [_IZTRO_PYTHON, "-c", _IZTRO_BRIDGE, op] + [str(a) for a in args],
            capture_output=True, text=True, timeout=IZTRO_TIMEOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if p.returncode == 0 and p.stdout.strip():
            return json.loads(p.stdout.strip())
    except Exception:
        pass
    return None


def solar_to_lunar(year, month, day):
    """Convert solar date → (lunar_year, lunar_month, lunar_day, is_leap)."""
    r = _call_iztro("s2l", year, month, day)
    if r:
        return (r["ly"], r["lm"], r["ld"], r.get("leap", False))
    return _builtin_solar_to_lunar(year, month, day)


def lunar_to_solar(lunar_year, lunar_month, lunar_day, is_leap=False):
    """Convert lunar date → (solar_year, solar_month, solar_day)."""
    r = _call_iztro("l2s", lunar_year, lunar_month, lunar_day, is_leap)
    if r:
        return (r["sy"], r["sm"], r["sd"])
    return _builtin_lunar_to_solar(lunar_year, lunar_month, lunar_day, is_leap)


# =============================================================================
# Built-in lunar calendar (1900-2100) — fallback when iztro unavailable
# =============================================================================

# Each int encodes one lunar year:
#   bits 0-3: leap month number (0=no leap)
#   bits 4-15: months 1-12 → 0=29d, 1=30d (bit 4+i for month i)
#   bits 16-19: leap month info (bit 16: 0=29d, 1=30d)
_LUNAR_YEARS = [
    0x04bd8,0x04ae0,0x0a570,0x054d5,0x0d260,0x0d950,0x16554,0x056a0,0x09ad0,0x055d2, # 1900-1909
    0x04ae0,0x0a5b6,0x0a4d0,0x0d250,0x1d255,0x0b540,0x0d6a0,0x0ada2,0x095b0,0x14977, # 1910-1919
    0x04970,0x0a4b0,0x0b4b5,0x06a50,0x06d40,0x1ab54,0x02b60,0x09570,0x052f2,0x04970, # 1920-1929
    0x06566,0x0d4a0,0x0ea50,0x06e95,0x05ad0,0x02b60,0x186e3,0x092e0,0x1c8d7,0x0c950, # 1930-1939
    0x0d4a0,0x1d8a6,0x0b550,0x056a0,0x1a5b4,0x025d0,0x092d0,0x0d2b2,0x0a950,0x0b557, # 1940-1949
    0x06ca0,0x0b550,0x15355,0x04da0,0x0a5b0,0x14573,0x052b0,0x0a9a8,0x0e950,0x06aa0, # 1950-1959
    0x0aea6,0x0ab50,0x04b60,0x0aae4,0x0a570,0x05260,0x0f263,0x0d950,0x05b57,0x056a0, # 1960-1969
    0x096d0,0x04dd5,0x04ad0,0x0a4d0,0x0d4d4,0x0d250,0x0d558,0x0b540,0x0b6a0,0x195a6, # 1970-1979
    0x095b0,0x049b0,0x0a974,0x0a4b0,0x0b27a,0x06a50,0x06d40,0x0af46,0x0ab60,0x09570, # 1980-1989
    0x04af5,0x04970,0x064b0,0x074a3,0x0ea50,0x06b58,0x05ac0,0x0ab60,0x096d5,0x092e0, # 1990-1999
    0x0c960,0x0d954,0x0d4a0,0x0da50,0x07552,0x056a0,0x0abb7,0x025d0,0x092d0,0x0cab5, # 2000-2009
    0x0a950,0x0b4a0,0x0baa4,0x0ad50,0x055d9,0x04ba0,0x0a5b0,0x15176,0x052b0,0x0a930, # 2010-2019
    0x07954,0x06aa0,0x0ad50,0x05b52,0x04b60,0x0a6e6,0x0a4e0,0x0d260,0x0ea65,0x0d530, # 2020-2029
    0x05aa0,0x076a3,0x096d0,0x04afb,0x04ad0,0x0a4d0,0x1d0b6,0x0d250,0x0d520,0x0dd45, # 2030-2039
    0x0b5a0,0x056d0,0x055b2,0x049b0,0x0a577,0x0a4b0,0x0aa50,0x1b255,0x06d20,0x0ada0, # 2040-2049
    0x14b63,0x09370,0x049f8,0x04970,0x064b0,0x168a6,0x0ea50,0x06b20,0x1a6c4,0x0aae0, # 2050-2059
    0x0a2e0,0x0d2e3,0x0c960,0x0d557,0x0d4a0,0x0da50,0x05d55,0x056a0,0x0a6d0,0x055d4, # 2060-2069
    0x052d0,0x0a9b8,0x0a950,0x0b4a0,0x0b6a6,0x0ad50,0x055a0,0x0aba4,0x0a5b0,0x052b0, # 2070-2079
    0x0b273,0x06930,0x07337,0x06aa0,0x0ad50,0x14b55,0x04b60,0x0a570,0x054e4,0x0d160, # 2080-2089
    0x0e968,0x0d520,0x0daa0,0x16aa6,0x056d0,0x04ae0,0x0a9d4,0x0a4d0,0x0d150,0x0f252, # 2090-2099
    0x0d520  # 2100
]

# Solar term data for month boundaries (simplified: approximate day-of-year)
_START_YEAR = 1900
_BASE_SOLAR_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]  # non-leap


def _days_in_solar_year(y):
    return 366 if (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0) else 365


def _solar_day_of_year(y, m, d):
    """Day-of-year (1-366) for a solar date."""
    base = _BASE_SOLAR_DAYS[m - 1] + d
    if m > 2 and _days_in_solar_year(y) == 366:
        base += 1
    return base


def _build_lunar_days(lunar_info):
    """Convert a lunar year info int into list of (month, days, is_leap) for each lunar month."""
    months = []
    leap_month = lunar_info & 0xf
    for lm in range(1, 13):
        days = 30 if (lunar_info >> (4 + lm - 1)) & 1 else 29
        months.append((lm, days, False))
        if lm == leap_month:
            leap_days = 30 if (lunar_info >> 16) & 1 else 29
            months.append((lm, leap_days, True))
    return months, leap_month


def _builtin_solar_to_lunar(year, month, day):
    """Convert solar date to lunar date using built-in lookup table."""
    # Pre-compute offsets: solar-day-of-1900 for each lunar year's start
    if not hasattr(_builtin_solar_to_lunar, '_start_days'):
        start_days = []
        current_start = 31 - 1  # Lunar 1900 starts on 1900-01-31, 0-indexed
        for i in range(len(_LUNAR_YEARS)):
            start_days.append(current_start)
            months_data, _ = _build_lunar_days(_LUNAR_YEARS[i])
            current_start += sum(d for _, d, _ in months_data)
        _builtin_solar_to_lunar._start_days = start_days

    start_days = _builtin_solar_to_lunar._start_days

    # Days from 1900-01-01 to target date
    total_days = 0
    for y in range(_START_YEAR, year):
        total_days += _days_in_solar_year(y)
    total_days += _solar_day_of_year(year, month, day) - 1

    # Find which lunar year contains this day
    lunar_year = _START_YEAR
    for i in range(len(start_days) - 1):
        if start_days[i] <= total_days < start_days[i + 1]:
            lunar_year = _START_YEAR + i
            total_days -= start_days[i]
            break
    else:
        last_i = len(start_days) - 1
        if total_days >= start_days[last_i]:
            lunar_year = _START_YEAR + last_i
            total_days -= start_days[last_i]

    idx = lunar_year - _START_YEAR
    if idx < 0 or idx >= len(_LUNAR_YEARS):
        return (year, month, day, False)

    months_data, _ = _build_lunar_days(_LUNAR_YEARS[idx])
    for lm, ld_count, is_leap in months_data:
        if total_days < ld_count:
            return (lunar_year, lm, total_days + 1, is_leap)
        total_days -= ld_count

    return (year, month, day, False)


def _builtin_lunar_to_solar(lunar_year, lunar_month, lunar_day, is_leap):
    """Convert lunar date to solar date using built-in lookup table."""
    if lunar_year < _START_YEAR:
        return (lunar_year, lunar_month, lunar_day)

    # Days from 1900-01-01 to start of lunar year
    total_days = 0
    for y in range(_START_YEAR, lunar_year):
        total_days += _days_in_solar_year(y)

    # Add days of lunar months before target month
    idx = lunar_year - _START_YEAR
    if idx >= len(_LUNAR_YEARS):
        return (lunar_year, lunar_month, lunar_day)

    months_data, _ = _build_lunar_days(_LUNAR_YEARS[idx])
    for lm, ld_count, is_leap_month in months_data:
        if lm == lunar_month and is_leap_month == is_leap:
            total_days += lunar_day - 1
            break
        total_days += ld_count
    else:
        # Month not found — add full lunar year and month offset
        total_days += lunar_day - 1

    # Convert day count back to solar date
    y = _START_YEAR
    while total_days >= _days_in_solar_year(y):
        total_days -= _days_in_solar_year(y)
        y += 1

    # Find month and day
    is_leap_year = _days_in_solar_year(y) == 366
    for m in range(1, 13):
        month_days = _BASE_SOLAR_DAYS[m] - _BASE_SOLAR_DAYS[m - 1] if m > 1 else 31
        if m == 2:
            month_days = 29 if is_leap_year else 28
        elif m in [4, 6, 9, 11]:
            month_days = 30
        else:
            month_days = 31
        if m > 2 and is_leap_year:
            # Adjust for leap day offset
            pass
        if total_days < month_days:
            return (y, m, total_days + 1)
        total_days -= month_days

    return (y, 12, total_days + 1)
