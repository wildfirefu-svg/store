#!/usr/bin/env python3
"""E2E tests for BaZi analysis web app using Playwright."""
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from playwright.sync_api import Page, sync_playwright

BASE = "http://127.0.0.1:8000"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    global BASE
    port = _free_port()
    BASE = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    yield BASE
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return
        except Exception:
            time.sleep(0.5)
    proc.kill()
    pytest.fail("E2E server failed to start")


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
    p.wait_for_timeout(1000)
    yield p
    p.close()


def create_chart(page, name="E2E测试"):
    before = page.locator(".mingzhu-card").count()
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
            "count => document.querySelectorAll('.mingzhu-card').length > count",
            arg=before,
            timeout=30000,
        )
    except Exception:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".mingzhu-card", timeout=10000)
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


class TestMultiMingzhu:
    def test_switch_mingzhu_correctly(self, page):
        create_chart(page, "切换测试一")
        create_chart(page, "切换测试二")

        cards = page.locator(".mingzhu-card").all()
        if len(cards) >= 2:
            report_before = page.locator("#report-content").text_content() or ""
            cards[0].click()
            page.wait_for_timeout(1000)
            report_after = page.locator("#report-content").text_content() or ""
            assert report_before != report_after, "切换命主后报告应该不同"


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
