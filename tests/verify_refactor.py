"""Verify the refactored app: JS modules load, chart renders, chat works."""
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
SCREEN = "f:/project/agent/tests/_verify_screens"

def ok(s):
    print(f"   [PASS] {s}")
def warn(s):
    print(f"   [WARN] {s}")
def fail(s):
    print(f"   [FAIL] {s}")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda err: errors.append(err.message))

        # 1. Load the page
        print("1. Loading page...")
        resp = page.goto(BASE, wait_until="domcontentloaded", timeout=15000)
        print(f"   HTTP {resp.status}")
        page.wait_for_timeout(2000)

        if errors:
            for e in errors[:3]:
                print(f"   [WARN] JS error: {e[:100]}")
        else:
            ok("No JS errors on page load")

        page.screenshot(path=f"{SCREEN}_01_load.png", full_page=True)

        # 2. Check that key UI elements exist
        print("\n2. Checking UI elements...")
        checks = {
            "mingzhu-panel": "#mingzhu-panel",
            "chat-area": "#chat-messages",
            "bazi-section": "#bazi-section",
            "report-column": ".report-column",
            "chat-input": "#chat-input",
            "add-mingzhu-btn": "#add-mingzhu-btn",
            "hehun-toggle-btn": "#hehun-toggle-btn",
            "liunian-toggle-btn": "#liunian-toggle-btn",
            "name-toggle-btn": "#name-toggle-btn",
            "zeri-toggle-btn": "#zeri-toggle-btn",
        }
        for name, sel in checks.items():
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    ok(f"{name}: visible")
                else:
                    warn(f"{name}: exists but hidden")
            except Exception as e:
                fail(f"{name}: NOT FOUND ({str(e)[:60]})")

        # 3. Click "+" to open add mingzhu modal
        print("\n3. Testing add mingzhu flow...")
        page.click("#panel-add-btn")
        page.wait_for_timeout(500)

        modal = page.locator("#add-mingzhu-modal")
        if modal.is_visible():
            ok("Modal opened")
        else:
            fail("Modal not visible")

        # Fill form using actual DOM IDs
        page.fill("#mingzhu-name", "TestMingzhu")
        page.fill("#pick-year", "1993")
        page.fill("#pick-month", "7")
        page.fill("#pick-day", "15")
        page.fill("#pick-hour", "14")
        page.fill("#pick-minute", "0")
        page.select_option("#mingzhu-gender", "male")
        page.fill("#mingzhu-location", "BeiJing")

        page.screenshot(path=f"{SCREEN}_02_form.png", full_page=True)

        # Click confirm
        page.click("#mingzhu-submit-btn")
        page.wait_for_timeout(3000)

        # Check chart area updated
        bazi_html = page.locator("#bazi-table").inner_html()
        if "wait" not in bazi_html.lower() and len(bazi_html) > 200:
            ok(f"BaZi chart rendered ({len(bazi_html)} chars)")
        else:
            warn(f"BaZi chart may not be rendered: {bazi_html[:100]}")

        # Check mingzhu list
        mz_items = page.locator("#mingzhu-list .mingzhu-item, #mingzhu-list li")
        count = mz_items.count()
        print(f"   Mingzhu list items: {count}")

        page.screenshot(path=f"{SCREEN}_03_chart.png", full_page=True)

        # 4. Test bazi/ziwei tab switch
        print("\n4. Testing chart tabs...")
        ziwei_tab = page.locator(".chart-tab[data-chart='ziwei']")
        ziwei_tab.click()
        page.wait_for_timeout(1000)
        ziwei_html = page.locator("#ziwei-table").inner_html()
        print(f"   Ziwei section: {len(ziwei_html)} chars")
        page.screenshot(path=f"{SCREEN}_04_ziwei.png", full_page=True)

        # Back to bazi
        bazi_tab = page.locator(".chart-tab[data-chart='bazi']")
        bazi_tab.click()
        page.wait_for_timeout(500)

        # 5. Test chat
        print("\n5. Testing chat...")
        page.fill("#chat-input", "analyze this bazi pattern")
        page.click("#chat-send-btn")
        page.wait_for_timeout(8000)

        chat_html = page.locator("#chat-messages").inner_html()
        if len(chat_html) > 200:
            ok(f"Chat has response ({len(chat_html)} chars)")
        else:
            warn(f"Chat may be empty: {chat_html[:200]}")

        page.screenshot(path=f"{SCREEN}_05_chat.png", full_page=True)

        # 6. Check report area
        print("\n6. Checking report area...")
        report_html = page.locator("#report-content").inner_html()
        if len(report_html) > 100:
            ok(f"Report content present ({len(report_html)} chars)")
        else:
            warn(f"Report may be empty: {report_html[:100]}")

        # Final JS errors
        if errors:
            print(f"\n[WARN] Total JS errors: {len(errors)}")
            for e in errors[:10]:
                print(f"   - {e[:120]}")
        else:
            print("\n[PASS] No JS errors throughout")

        page.screenshot(path=f"{SCREEN}_06_final.png", full_page=True)

        print(f"\nScreenshots saved to {SCREEN}_*.png")
        browser.close()

if __name__ == "__main__":
    run()
