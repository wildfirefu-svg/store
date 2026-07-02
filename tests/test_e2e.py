#!/usr/bin/env python3
"""E2E tests for BaZi analysis web app using Playwright."""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

BASE = "http://127.0.0.1:8000"

pytestmark = [pytest.mark.e2e]


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    global BASE
    port = _free_port()
    BASE = f"http://127.0.0.1:{port}"

    tmp_dir = Path(".tmp")
    tmp_dir.mkdir(exist_ok=True)
    log_path = tmp_dir / "e2e-uvicorn.log"
    log_file = log_path.open("w", encoding="utf-8")
    db_path = tmp_path_factory.mktemp("e2e-db") / "e2e.db"
    env = os.environ.copy()
    env.setdefault("BAZI_API_RETRIES", "0")
    env.setdefault("DEEPSEEK_API_KEY", "test-e2e-no-real-call")
    env["BAZI_DB_PATH"] = str(db_path)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{BASE}/api/health", timeout=1) as resp:
                    if resp.status == 200:
                        yield BASE
                        return
            except Exception:
                time.sleep(0.5)
        pytest.fail(f"E2E server failed to start; see {log_path}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log_file.close()


@pytest.fixture(scope="module")
def browser(live_server):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser) -> Page:
    p = browser.new_page(viewport={"width": 1400, "height": 900})
    p.route(
        "**/api/chat/stream**",
        lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream; charset=utf-8"},
            body='event: reply\ndata: {"text":"E2E mock reply","tool":null}\n\nevent: done\ndata: {"corrections":0}\n\n',
        ),
    )
    p.goto(BASE, wait_until="domcontentloaded")
    p.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e) {} }")
    p.reload(wait_until="domcontentloaded")
    p.wait_for_timeout(1000)
    yield p
    p.close()


def create_chart(page, name="E2E测试"):
    page.evaluate(
        """() => {
            const modal = document.getElementById('add-mingzhu-modal');
            if (modal) modal.classList.add('hidden');
            const input = document.getElementById('mingzhu-name');
            if (input) input.value = '';
        }"""
    )
    page.click("#add-mingzhu-btn")
    page.wait_for_selector("#add-mingzhu-modal:not(.hidden)")
    page.fill("#mingzhu-name", name)
    page.fill("#mingzhu-location", "北京")
    page.click("#mingzhu-submit-btn")
    try:
        page.wait_for_function(
            "name => Array.from(document.querySelectorAll('.mingzhu-card'))"
            ".some(el => el.textContent.includes(name))",
            arg=name,
            timeout=30000,
        )
    except Exception as exc:
        body_text = page.locator("body").text_content(timeout=2000) or ""
        raise AssertionError(
            f"Chart card for {name} did not appear after submit. Body={body_text[:500]}"
        ) from exc
    page.wait_for_timeout(1000)


class TestChartCreation:
    def test_create_chart(self, page):
        create_chart(page, "E2E测试")

        cards = page.locator(".mingzhu-card").all()
        assert len(cards) >= 1, "命主卡片应该出现"

        bazi = page.locator("#bazi-table").text_content() or ""
        assert len(bazi) > 20, "八字表格应该有内容"

    def test_auto_overview_generated(self, page):
        create_chart(page, "总览测试")
        report = page.locator("#report-content").text_content() or ""
        assert "等待输入" not in report, "总览报告不应该显示等待输入"
        assert "输入出生信息后，报告将在此显示" not in report, "总览报告不应该停留在占位文案"
        assert "命盘总览" in report, "总览报告应该包含标题"
        assert "日主" in report, "总览报告应该包含日主信息"
        assert "可信度说明" in report, "总览报告应该包含可信度说明"


class TestChat:
    def test_send_message_streams_response(self, page):
        create_chart(page, "聊天测试")
        page.fill("#chat-input", "你好")
        page.click("#chat-send-btn")
        page.wait_for_selector(".chat-msg.agent .bubble", timeout=10000)

        bubbles = page.locator(".chat-msg.agent .bubble").all()
        assert len(bubbles) >= 1, "至少应有一条 agent 回复"

        text = page.locator(".chat-messages").text_content() or ""
        assert "连接失败" not in text, "不应该出现连接失败"
        assert "暂不可用" not in text, "不应该出现暂不可用"

    def test_deep_report_routes_to_deep_report_tab(self, page):
        page.unroute("**/api/chat/stream**")
        page.route(
            "**/api/chat/stream**",
            lambda route: route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream; charset=utf-8"},
                body=(
                    'event: report\n'
                    'data: {"text":"# 深度报告\\n## 一、八字排盘\\n正文","tab":"deep_report"}\n\n'
                    'event: done\n'
                    'data: {"corrections":0}\n\n'
                ),
            ),
        )
        create_chart(page, "深度报告测试")
        page.fill("#chat-input", "深度报告")
        page.click("#chat-send-btn")
        page.wait_for_function(
            "() => (document.getElementById('report-status')?.textContent || '').includes('完成')",
            timeout=10000,
        )

        tabs = page.locator("#report-tabs").text_content() or ""
        report = page.locator("#report-content").text_content() or ""
        assert "深度报告" in tabs
        assert "深度报告" in report


class TestMultiMingzhu:
    def test_switch_mingzhu_correctly(self, page):
        create_chart(page, "切换测试一")
        create_chart(page, "切换测试二")

        # 当前展示的命主应包含最近创建的命主名
        body = page.locator("body").text_content() or ""
        assert "切换测试二" in body, "最近创建的命主应该成为当前命主"


class TestToolBars:
    @pytest.fixture(autouse=True)
    def ensure_mingzhu(self, page):
        try:
            page.wait_for_selector(".mingzhu-card", timeout=2000)
        except Exception:
            pass
        cards = page.locator(".mingzhu-card").all()
        if len(cards) == 0:
            create_chart(page, "工具栏测试")
        page.evaluate(
            "() => { const m = document.getElementById('add-mingzhu-modal'); if (m) m.remove(); }"
        )
        page.wait_for_timeout(400)

    def test_zeri_toolbar_opens(self, page):
        page.click("#zeri-toggle-btn")
        page.wait_for_timeout(500)
        bar = page.locator("#zeri-bar")
        assert not bar.evaluate("el => el.classList.contains('hidden')"), "择日栏应该可见"

    def test_name_toolbar_opens(self, page):
        page.click("#name-toggle-btn")
        page.wait_for_timeout(500)
        bar = page.locator("#name-bar")
        assert not bar.evaluate("el => el.classList.contains('hidden')"), "取名栏应该可见"
