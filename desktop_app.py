#!/usr/bin/env python3
"""
玄机子 · 八字命理分析 — 桌面版
双击运行即可，无需手动启动服务、无需打开浏览器。
"""

import sys
import os
import threading
import time


def _get_base_path():
    """Get application root dir — works both for dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = _get_base_path()
os.chdir(BASE_PATH)
sys.path.insert(0, BASE_PATH)

# For PyInstaller: extract bundled data to MEIPASS if available
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    import shutil
    meipass = sys._MEIPASS
    for subdir in ('templates', 'static', 'knowledge-base'):
        src = os.path.join(meipass, subdir)
        dst = os.path.join(BASE_PATH, subdir)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)

import webview
import uvicorn
from api_server import app

HOST = "127.0.0.1"
PORT = 8000


def start_server():
    """Start FastAPI in a daemon thread."""
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def main():
    # Start server in background
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    url = f"http://{HOST}:{PORT}"
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(url + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.3)

    # Create desktop window
    window = webview.create_window(
        title="玄机子 · 八字命理分析",
        url=url,
        width=1400,
        height=900,
        min_size=(960, 640),
        text_select=True,
        confirm_close=True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
