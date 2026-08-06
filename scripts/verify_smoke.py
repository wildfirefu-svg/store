#!/usr/bin/env python3
"""Run a focused smoke test and record the result for harness evidence."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = PROJECT_ROOT / ".better-harness"
RESULT_FILE = RESULT_DIR / "verify-smoke.result.json"
CLAIM = "focused smoke tests passed"


def find_python() -> str:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    venv_python_posix = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_python_posix.exists():
        return str(venv_python_posix)
    return sys.executable


def main() -> int:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    python = find_python()
    # Fast, core pytest files: calculator pillars + frontend asset checks.
    command = [
        python,
        "-m",
        "pytest",
        "tests/test_bazi_calculator_pillars.py",
        "tests/test_frontend_assets.py",
        "-q",
        "--tb=short",
    ]

    started_at = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    finished_at = datetime.now(timezone.utc).isoformat()

    passed = proc.returncode == 0
    result = {
        "claim": CLAIM,
        "status": "verified" if passed else "failed",
        "command": " ".join(command),
        "exitCode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "startedAt": started_at,
        "finishedAt": finished_at,
    }

    RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"claim": result["claim"], "status": result["status"], "exitCode": result["exitCode"]}))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
