#!/usr/bin/env python3
"""Run a clean-browser Xuanjizi report quality check against a local URL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BAD_PATTERNS = [
    "巳午未会火局",
    "丑为火库",
    "月令财星当令",
]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out-dir", default=".tmp/ui-report-quality")
    parser.add_argument("--timeout-ms", type=int, default=240000)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"base_url": args.base_url, "errors": [], "signals": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.on("pageerror", lambda err: result["errors"].append(f"pageerror: {err}"))
        page.on("requestfailed", lambda req: result["errors"].append(f"requestfailed: {req.url} {req.failure}"))

        page.goto(args.base_url, wait_until="domcontentloaded", timeout=30000)
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        page.reload(wait_until="domcontentloaded", timeout=30000)
        page.click("#add-mingzhu-btn")
        page.wait_for_selector("#add-mingzhu-modal:not(.hidden)", timeout=10000)
        page.fill("#mingzhu-name", "质量验收命主")
        page.fill("#pick-year", "1990")
        page.fill("#pick-month", "5")
        page.fill("#pick-day", "12")
        page.fill("#pick-hour", "8")
        page.fill("#pick-minute", "30")
        page.select_option("#mingzhu-gender", "female")
        page.fill("#mingzhu-location", "北京")
        page.click("#mingzhu-submit-btn")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('.mingzhu-card')).some(el => el.textContent.includes('质量验收命主'))",
            timeout=30000,
        )

        overview = page.locator("#report-content").text_content(timeout=3000) or ""
        if "命盘总览" not in overview:
            result["errors"].append("overview missing 命盘总览")

        page.check("#trusted-mode-toggle")
        page.fill("#chat-input", "报告")
        page.click("#chat-send-btn")
        try:
            page.wait_for_function(
                "() => (document.getElementById('report-status')?.textContent || '').includes('完成')",
                timeout=args.timeout_ms,
            )
        except PlaywrightTimeoutError:
            result["errors"].append("AI report did not finish before timeout")

        report = page.locator("#report-content").text_content(timeout=5000) or ""
        table_count = page.locator("#report-content table").count()
        body = page.locator("body").text_content(timeout=5000) or ""
        page.screenshot(path=str(out_dir / "ui-report-quality.png"), full_page=True)
        (out_dir / "ui-report-quality-report.txt").write_text(report, encoding="utf-8")

        result["signals"] = {
            "report_chars": len(report),
            "table_count": table_count,
            "has_disclaimer": "免责声明" in report or "仅供参考" in report,
            "has_validation_note": "系统校验提示" in report,
            "has_connection_error": any(term in body for term in ["连接失败", "暂不可用", "API 错误"]),
            "bad_patterns": [pattern for pattern in BAD_PATTERNS if pattern in report],
        }

        if result["signals"]["report_chars"] < 2500:
            result["errors"].append("report shorter than 2500 chars")
        if result["signals"]["table_count"] < 5:
            result["errors"].append("report has fewer than 5 rendered tables")
        if not result["signals"]["has_disclaimer"]:
            result["errors"].append("report missing disclaimer")
        if result["signals"]["has_connection_error"]:
            result["errors"].append("page contains AI connection error")
        if result["signals"]["bad_patterns"] and not result["signals"]["has_validation_note"]:
            result["errors"].append("bad BaZi claims present without 系统校验提示")

        (out_dir / "ui-report-quality.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        browser.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
