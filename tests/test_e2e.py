#!/usr/bin/env python3
"""E2E tests for BaZi analysis web app using Playwright."""
import pytest
from playwright.sync_api import sync_playwright, Page

BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser) -> Page:
    p = browser.new_page(viewport={"width": 1400, "height": 900})
    p.goto(BASE, wait_until="domcontentloaded")
    p.wait_for_timeout(2000)
    yield p
    p.close()


class TestChartCreation:
    def test_create_chart(self, page):
        """排盘: 输入出生信息，验证命主卡片出现"""
        page.click("#add-mingzhu-btn")
        page.wait_for_selector("#add-mingzhu-modal:not(.hidden)")
        page.fill("#mingzhu-name", "E2E测试")
        page.fill("#mingzhu-location", "北京")
        page.click("#mingzhu-submit-btn")
        page.wait_for_timeout(3000)

        cards = page.locator(".mingzhu-card").all()
        assert len(cards) >= 1, "命主卡片应该出现"

        # Check bazi table rendered
        bazi = page.locator("#bazi-table").text_content() or ""
        assert len(bazi) > 20, "八字表格应该有内容"

    def test_auto_overview_generated(self, page):
        """验证自动生成总览报告"""
        report = page.locator("#report-content").text_content() or ""
        # Should have meaningful content, not just placeholder
        assert "等待输入" not in report, "总览报告不应该显示等待输入"


class TestChat:
    def test_send_message_streams_response(self, page):
        """发送对话消息，验证 AI 流式回复"""
        page.fill("#chat-input", "你好")
        page.click("#chat-send-btn")
        page.wait_for_timeout(8000)

        bubbles = page.locator(".chat-msg.agent .bubble").all()
        assert len(bubbles) >= 1, "至少应有一条 agent 回复"

        # Verify no connection failure
        text = page.locator(".chat-messages").text_content() or ""
        assert "连接失败" not in text, "不应该出现连接失败"
        assert "暂不可用" not in text, "不应该出现暂不可用"


class TestMultiMingzhu:
    def test_switch_mingzhu_correctly(self, page):
        """切换命主，验证聊天和报告区域更新"""
        # Add second mingzhu
        page.click("#add-mingzhu-btn")
        page.wait_for_selector("#add-mingzhu-modal:not(.hidden)")
        page.fill("#mingzhu-name", "切换测试")
        page.fill("#pick-year", "2000")
        page.fill("#pick-month", "3")
        page.fill("#pick-day", "20")
        page.click("#mingzhu-submit-btn")
        page.wait_for_timeout(3000)

        cards = page.locator(".mingzhu-card").all()
        if len(cards) >= 2:
            report_before = page.locator("#report-content").text_content() or ""
            cards[0].click()
            page.wait_for_timeout(2000)
            report_after = page.locator("#report-content").text_content() or ""
            # Reports should differ between mingzhu
            assert report_before != report_after, "切换命主后报告应该不同"


class TestToolBars:
    @pytest.fixture(autouse=True)
    def ensure_mingzhu(self, page):
        """Ensure at least one mingzhu exists for toolbar tests."""
        cards = page.locator(".mingzhu-card").all()
        if len(cards) == 0:
            page.click("#add-mingzhu-btn")
            page.wait_for_selector("#add-mingzhu-modal:not(.hidden)")
            page.fill("#mingzhu-name", "工具栏测试")
            page.fill("#mingzhu-location", "北京")
            page.click("#mingzhu-submit-btn")
            page.wait_for_timeout(3000)

    def test_zeri_toolbar_opens(self, page):
        """择日工具栏可以打开"""
        page.click("#zeri-toggle-btn")
        page.wait_for_timeout(500)
        bar = page.locator("#zeri-bar")
        assert not bar.evaluate("el => el.classList.contains('hidden')"), "择日栏应该可见"

    def test_name_toolbar_opens(self, page):
        """取名工具栏可以打开"""
        page.click("#name-toggle-btn")
        page.wait_for_timeout(500)
        bar = page.locator("#name-bar")
        assert not bar.evaluate("el => el.classList.contains('hidden')"), "取名栏应该可见"
