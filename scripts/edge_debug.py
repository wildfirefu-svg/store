"""更深入的边界 bug 排查：实跑后端 + 触发真实路径。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
DB_PATH = TMP / "edge.db"


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_health(base: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def request(base: str, path: str, method: str = "GET", headers: dict | None = None, body: bytes | None = None,
            stream_lines: int = 0) -> dict:
    req = urllib.request.Request(base + path, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if stream_lines:
                lines: list[str] = []
                for _ in range(stream_lines):
                    raw = resp.readline()
                    if not raw:
                        break
                    lines.append(raw.decode("utf-8", errors="replace").rstrip("\n"))
                return {"status": resp.status, "lines": lines}
            return {"status": resp.status, "body": resp.read().decode("utf-8", errors="replace")[:300]}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", errors="replace")[:300]}
    except Exception as e:
        return {"status": -1, "error": f"{type(e).__name__}: {e}"}


def main() -> int:
    TMP.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log = (TMP / "edge-uvicorn.log").open("w", encoding="utf-8")

    env = os.environ.copy()
    env["BAZI_DB_PATH"] = str(DB_PATH)
    env.setdefault("BAZI_API_RETRIES", "0")
    env.setdefault("DEEPSEEK_API_KEY", "edge-test-no-real-call")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
    )

    findings: dict = {"base": base, "checks": []}

    try:
        if not wait_health(base):
            findings["checks"].append({"stage": "boot", "ok": False})
            print(json.dumps(findings, ensure_ascii=False, indent=2))
            return 2

        # 1) 不存在的路径
        r = request(base, "/no-such-page-xyz")
        findings["checks"].append({"name": "404", "expected": 404, "got": r["status"]})

        # 2) GET on a POST-only endpoint
        r = request(base, "/api/chart")
        findings["checks"].append({"name": "GET /api/chart should be 405/404", "got": r["status"]})

        # 3) benchmark report not found
        r = request(base, "/api/benchmark/report/nonexistent-id")
        findings["checks"].append({"name": "benchmark report 404", "expected": 404, "got": r["status"]})

        # 4) 路径穿越
        r = request(base, "/api/benchmark/report/../../etc/passwd")
        findings["checks"].append({"name": "benchmark report path traversal", "got": r["status"]})

        # 5) chat stream with fake key -> 应优雅返回 SSE error 行
        chart_body = json.dumps(
            {
                "name": "Edge",
                "year": 1990,
                "month": 1,
                "day": 1,
                "hour": 9,
                "minute": 0,
                "gender": "male",
                "location": "北京",
            }
        ).encode("utf-8")
        r = request(base, "/api/chart", method="POST", headers={"Content-Type": "application/json"}, body=chart_body)
        chart_status = r["status"]
        findings["checks"].append({"name": "create chart", "got": chart_status})
        chart_id = ""
        if chart_status == 200:
            try:
                chart_id = json.loads(r["body"]).get("chart_id") or ""
            except Exception:
                pass

        if chart_id:
            params = f"chart_id={chart_id}&message=ping"
            r = request(base, f"/api/chat/stream?{params}", stream_lines=20)
            joined = "\n".join(r.get("lines", []))
            findings["checks"].append(
                {
                    "name": "chat stream with fake key",
                    "got": r.get("status"),
                    "has_event": "event:" in joined,
                    "has_data": "data:" in joined,
                    "preview": joined[:300],
                }
            )

        # 6) 速率限制：连续打 70 次 /api/health
        burst = []
        for _ in range(70):
            burst.append(request(base, "/api/health")["status"])
        findings["checks"].append(
            {
                "name": "rate-limit burst /api/health",
                "ok_count": sum(1 for s in burst if s == 200),
                "rate_limited": sum(1 for s in burst if s == 429),
            }
        )

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        with (TMP / "edge-report.json").open("w", encoding="utf-8") as f:
            json.dump(findings, f, ensure_ascii=False, indent=2)
        print(f"edge report -> {TMP / 'edge-report.json'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
