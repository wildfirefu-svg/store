"""单独验证：fake DEEPSEEK_API_KEY 时 /api/chat/stream 是否优雅返回 SSE error。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
DB_PATH = TMP / "stream-test.db"


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    TMP.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log = (TMP / "stream-test.log").open("w", encoding="utf-8")

    env = os.environ.copy()
    env["BAZI_DB_PATH"] = str(DB_PATH)
    env["BAZI_API_RETRIES"] = "0"
    env["DEEPSEEK_API_KEY"] = "sk-fakekey-for-stream-debug-99999999"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
    )

    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base}/api/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        else:
            print("server did not start; see", log.name)
            return 2

        body = json.dumps(
            {"name": "Stream", "year": 1990, "month": 1, "day": 1, "hour": 9, "minute": 0,
             "gender": "male", "location": "北京"}
        ).encode("utf-8")
        req = urllib.request.Request(
            base + "/api/chart",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            chart = json.loads(resp.read().decode("utf-8"))
        chart_id = chart.get("chart_id")
        print("chart_id =", chart_id)
        if not chart_id:
            return 3

        params = urllib.parse.urlencode({"chart_id": chart_id, "message": "hello stream"})
        url = f"{base}/api/chat/stream?{params}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            print("stream content-type =", resp.headers.get("Content-Type"))
            saw_error = False
            saw_done = False
            collected = []
            t0 = time.time()
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                collected.append(line)
                if line.startswith("event:"):
                    print(line)
                if "DEEPSEEK_API_KEY" in line or "ANTHROPIC_API_KEY" in line:
                    print("[ok] fallback message present")
                if line.startswith("data:") and "本地分析" in line:
                    saw_error = True
                if line == "event: done":
                    saw_done = True
                if time.time() - t0 > 30:
                    break
            print("saw_error =", saw_error, "saw_done =", saw_done)
            (TMP / "stream-test-output.txt").write_text("\n".join(collected[:500]), encoding="utf-8")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
