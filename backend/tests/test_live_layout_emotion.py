import sys

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:5173"
EMAIL = "student@edusense.local"
PASSWORD = "Password123"


def login(page):
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page.locator('input[autocomplete="email"]').fill(EMAIL)
    page.locator('input[autocomplete="current-password"]').fill(PASSWORD)
    page.locator("form").locator("button").last.click()
    page.wait_for_url("**/student", timeout=15000)


def test_layout_and_emotion():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            permissions=["camera", "microphone"],
        )
        page = context.new_page()
        login(page)

        viewports = [
            (1366, 768),
            (1536, 864),
            (1920, 1080),
            (820, 1180),
            (390, 844),
        ]
        routes = [
            "/student",
            "/instructor/knowledge-base",
            "/instructor/chatbot",
        ]

        for width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            role_routes = routes if width >= 820 else ["/student"]
            for route in role_routes:
                page.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=30000)
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                )
                assert not overflow, f"horizontal overflow at {width}x{height}: {route}"
                print(f"LAYOUT PASS {width}x{height} {route}")

        page.set_viewport_size({"width": 1366, "height": 768})
        page.goto(f"{BASE_URL}/student", wait_until="networkidle", timeout=30000)
        capture = page.get_by_text("Capture & Analyze", exact=False)
        if capture.count():
            capture.first.click()
            page.wait_for_timeout(3500)
            resolving_text = page.get_by_text("Analyzing...", exact=True)
            assert resolving_text.count() == 0, "emotion analysis remained stuck in Analyzing"
            print("EMOTION PASS analyzing state resolved")
        else:
            print("EMOTION SKIP capture control not present")

        context.close()
        browser.close()


if __name__ == "__main__":
    test_layout_and_emotion()
