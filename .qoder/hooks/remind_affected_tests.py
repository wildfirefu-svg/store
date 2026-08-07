#!/usr/bin/env python3
"""PostToolUse hook: remind to run affected tests after editing scripts/benchmark.

Never blocks (always exit 0). Reads one JSON event from stdin.
Stdlib only; never echoes prompts, env values, or suspected secrets.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WATCHED_PREFIXES = ("scripts/", "benchmark/")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    try:
        event = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return 0
    if not isinstance(event, dict):
        return 0
    if event.get("tool_name") not in ("Write", "Edit"):
        return 0
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    path = str(tool_input.get("file_path") or "")
    p = Path(os.path.normpath(path))
    if p.is_absolute():
        try:
            p = p.relative_to(PROJECT_ROOT)
        except ValueError:
            return 0
    posix = p.as_posix()
    if posix.startswith(WATCHED_PREFIXES):
        print(
            f"{posix} changed; consider: python scripts/affected_tests.py"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
