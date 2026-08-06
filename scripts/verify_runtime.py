#!/usr/bin/env python3
"""Start api_server.py, health-check it, and record the result for harness evidence."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = PROJECT_ROOT / ".better-harness"
RESULT_FILE = RESULT_DIR / "verify-runtime.result.json"
START_TIMEOUT_SECONDS = 30


def _elapsed_seconds(started_monotonic: float) -> float:
    return round(time.monotonic() - started_monotonic, 2)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_python() -> str:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    venv_python_posix = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_python_posix.exists():
        return str(venv_python_posix)
    return sys.executable


def wait_for_health(
    url: str,
    timeout: float,
    process: subprocess.Popen | None = None,
) -> tuple[bool, str]:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        if process is not None:
            return_code = process.poll()
            if return_code is not None:
                return False, f"server process exited with code {return_code}"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body = response.read().decode("utf-8", errors="replace")
                if response.status == 200 and '"status"' in body:
                    return True, body
                last_error = f"status={response.status} body={body[:200]}"
        except urllib.error.HTTPError as e:
            last_error = f"HTTPError {e.code}: {e.reason}"
        except Exception as e:
            last_error = str(e)
        time.sleep(0.5)
    return False, last_error


def main() -> int:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    health_port = find_free_port()
    health_url = f"http://127.0.0.1:{health_port}/api/health"
    env = os.environ.copy()
    env["BAZI_API_PORT"] = str(health_port)
    # Disable API keys for startup so the server can reach health without them.
    env.setdefault("DEEPSEEK_API_KEY", "")
    env.setdefault("ANTHROPIC_API_KEY", "")

    python = find_python()
    command = [python, "api_server.py"]

    started_at = datetime.now(timezone.utc).isoformat()
    started_monotonic = time.monotonic()
    proc: subprocess.Popen | None = None
    status = "verified"
    exit_code = 0
    details: dict = {"command": " ".join(command), "healthUrl": health_url}

    try:
        proc = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ok, health_response = wait_for_health(
            health_url, START_TIMEOUT_SECONDS, proc
        )
        details["startupSeconds"] = _elapsed_seconds(started_monotonic)
        details["healthResponse"] = health_response

        if not ok:
            status = "failed"
            exit_code = 1
            details["error"] = f"Health check did not pass within {START_TIMEOUT_SECONDS}s: {health_response}"
        else:
            details["error"] = None
    except Exception as e:
        status = "failed"
        exit_code = 1
        details["error"] = f"Exception while running runtime check: {e}"
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            stdout, stderr = proc.communicate(timeout=5)
            details["stdoutTail"] = stdout[-2000:] if stdout else ""
            details["stderrTail"] = stderr[-2000:] if stderr else ""

    finished_at = datetime.now(timezone.utc).isoformat()
    result = {
        "claim": "runtime behavior",
        "status": status,
        "command": " ".join(command),
        "exitCode": exit_code,
        "details": details,
        "startedAt": started_at,
        "finishedAt": finished_at,
    }

    RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"claim": result["claim"], "status": result["status"], "exitCode": result["exitCode"]}))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
