"""Chinese lunar calendar conversion — delegates to iztro_py (Python312) for accuracy.

Falls back to built-in simplified algorithm if iztro is unavailable.
"""
import json
import os
import subprocess
import sys
from datetime import date

_IZTRO_PYTHON = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "Python", "Python312", "python.exe"
)

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
    """Call iztro via Python312 subprocess. Returns parsed JSON or None on failure."""
    try:
        p = subprocess.run(
            [_IZTRO_PYTHON, "-c", _IZTRO_BRIDGE, op] + [str(a) for a in args],
            capture_output=True, text=True, timeout=10,
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
    # Fallback: simplified
    return (year, month, day, False)


def lunar_to_solar(lunar_year, lunar_month, lunar_day, is_leap=False):
    """Convert lunar date → (solar_year, solar_month, solar_day)."""
    r = _call_iztro("l2s", lunar_year, lunar_month, lunar_day, is_leap)
    if r:
        return (r["sy"], r["sm"], r["sd"])
    return (lunar_year, lunar_month, lunar_day)
