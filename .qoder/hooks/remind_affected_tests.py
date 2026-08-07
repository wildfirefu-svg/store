#!/usr/bin/env python3
"""PostToolUse hook: remind to run affected tests after editing scripts/benchmark.

Never blocks (always exit 0). Reads one JSON event from stdin.
Stdlib only; never echoes prompts, env values, or suspected secrets.
"""
from __future__ import annotations

import json
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
    cwd = str(event.get("cwd") or "")
    path = str(tool_input.get("file_path") or "")
    p = Path(path.replace("\\", "/"))
    if not p.is_absolute():
        p = (Path(cwd) if cwd else PROJECT_ROOT) / p
    resolved = p.resolve(strict=False)
    try:
        rel = resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return 0
    posix = rel.as_posix()
    if posix.startswith(WATCHED_PREFIXES):
        print(
            f"{posix} changed; consider: python scripts/affected_tests.py"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
