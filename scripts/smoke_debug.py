"""手动 smoke 调试脚本：启动后端 -> 浏览主要页面 -> 巡检 API -> 收集错误。

用法（PowerShell）：
  python scripts/smoke_debug.py

输出位置：
  .tmp/smoke-uvicorn.log
  .tmp/smoke-screenshots/*.png
  .tmp/smoke-report.json
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
from contextlib import closing
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
SHOTS = TMP / "smoke-screenshots"
DB_PATH = TMP / "smoke.db"


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


def http_get(base: str, path: str, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(base + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def main() -> int:
    TMP.mkdir(exist_ok=True)
    SHOTS.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = TMP / "smoke-uvicorn.log"
    log_file = log_path.open("w", encoding="utf-8")

    env = os.environ.copy()
    env["BAZI_DB_PATH"] = str(DB_PATH)
    env.setdefault("BAZI_API_RETRIES", "0")
    env.setdefault("DEEPSEEK_API_KEY", "smoke-test-no-real-call")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
    )

    report: dict = {"base": base, "port": port, "errors": [], "checks": [], "console": [], "network_failures": []}

    try:
        if not wait_health(base):
            report["errors"].append({"stage": "boot", "detail": f"health did not become ready; see {log_path}"})
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2

        for endpoint in ("/api/health", "/api/charts", "/api/benchmark/runs", "/", "/benchmark"):
            status, body = http_get(base, endpoint)
            ok = status == 200
            sample = body[:120] if isinstance(body, str) else ""
            report["checks"].append({"endpoint": endpoint, "status": status, "ok": ok, "sample": sample})
            if not ok:
                report["errors"].append({"stage": f"GET {endpoint}", "status": status, "sample": sample})

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})

            page.on("console", lambda msg: report["console"].append({"type": msg.type, "text": msg.text}))
            page.on("pageerror", lambda err: report["errors"].append({"stage": "pageerror", "detail": str(err)}))
            page.on(
                "requestfailed",
                lambda req: report["network_failures"].append(
                    {"url": req.url, "method": req.method, "failure": req.failure}
                ),
            )

            page.route(
                "**/api/chat/stream**",
                lambda route: route.fulfill(
                    status=200,
                    headers={"Content-Type": "text/event-stream; charset=utf-8"},
                    body='event: reply\ndata: {"text":"smoke reply","tool":null}\n\nevent: done\ndata: {"corrections":0}\n\n',
                ),
            )

            page.goto(base, wait_until="networkidle", timeout=15000)
            page.screenshot(path=str(SHOTS / "01_home.png"), full_page=True)

            # 创建命主
            page.click("#add-mingzhu-btn")
            page.wait_for_selector("#add-mingzhu-modal:not(.hidden)")
            page.fill("#mingzhu-name", "Smoke")
            page.fill("#mingzhu-location", "北京")
            page.click("#mingzhu-submit-btn")
            try:
                page.wait_for_function(
                    "Array.from(document.querySelectorAll('.mingzhu-card')).some(el => el.textContent.includes('Smoke'))",
                    timeout=15000,
                )
            except Exception as e:
                report["errors"].append({"stage": "create_mingzhu", "detail": str(e)})
                page.screenshot(path=str(SHOTS / "02_create_failed.png"), full_page=True)
                browser.close()
                return 3

            page.screenshot(path=str(SHOTS / "02_after_create.png"), full_page=True)

            # 工具栏巡检
            for btn_id, bar_id, name in [
                ("#zeri-toggle-btn", "#zeri-bar", "zeri"),
                ("#name-toggle-btn", "#name-bar", "name"),
            ]:
                page.click(btn_id)
                page.wait_for_timeout(300)
                bar = page.locator(bar_id)
                hidden = bar.evaluate("el => el.classList.contains('hidden')")
                if hidden:
                    report["errors"].append({"stage": f"toolbar_{name}", "detail": f"{bar_id} still hidden"})
                page.click(btn_id)
                page.wait_for_timeout(200)

            page.screenshot(path=str(SHOTS / "03_toolbars.png"), full_page=True)

            # 聊天
            page.fill("#chat-input", "smoke 你好")
            page.click("#chat-send-btn")
            try:
                page.wait_for_selector(".chat-msg.agent .bubble", timeout=10000)
                bubbles = page.locator(".chat-msg.agent .bubble").count()
                report["checks"].append({"endpoint": "chat-stream", "bubbles": bubbles, "ok": bubbles >= 1})
            except Exception as e:
                report["errors"].append({"stage": "chat", "detail": str(e)})

            page.screenshot(path=str(SHOTS / "04_chat.png"), full_page=True)

            # benchmark 仪表盘
            page.goto(base + "/benchmark", wait_until="networkidle", timeout=15000)
            page.screenshot(path=str(SHOTS / "05_benchmark.png"), full_page=True)

            browser.close()

    except Exception:
        report["errors"].append({"stage": "fatal", "detail": traceback.format_exc()})
        return 4
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()
        with (TMP / "smoke-report.json").open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"smoke report -> {TMP / 'smoke-report.json'}")
        print(f"errors: {len(report['errors'])}; network_failures: {len(report['network_failures'])}")

    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
