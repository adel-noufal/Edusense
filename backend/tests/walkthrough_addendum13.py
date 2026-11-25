"""U1 + U2 walkthrough: what the instructor actually does in the browser.

U1 — Sessions > Ended, open "View Resources" on the LAST row of the list (the
30th row when the library is long enough). The modal must sit inside the
viewport and open with the page scroll unchanged, which is exactly what failed
before: the dialog was centred in the whole document, far below the fold.

U2 — the API must send "...Z" and the Knowledge Base must render Cairo time
(Africa/Cairo) for the same instant.

Run with the backend (8000) and Vite (5173) up; verify.bat runs this after
verify_extras.py starts both servers. Screenshots land in docs/screenshots/.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5173"
EMAIL = "instructor@edusense.local"
PASSWORD = "Password123"
ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS " if condition else "FAIL ") + name + ("" if condition else f"  <- {detail}"))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def login(page) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page.locator('input[autocomplete="email"]').fill(EMAIL)
    page.locator('input[autocomplete="current-password"]').fill(PASSWORD)
    page.locator("form").locator("button").last.click()
    page.wait_for_url("**/instructor**", timeout=20000)


def api_json(page, path: str):
    return page.evaluate(
        """async (path) => {
            const token = localStorage.getItem('edusense_token')
            const response = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${token}` } })
            if (!response.ok) return { __error: response.status }
            return await response.json()
        }""",
        path,
    )


def run_u1(page) -> None:
    page.goto(f"{BASE_URL}/instructor/sessions", wait_until="networkidle")
    page.get_by_role("button", name=re.compile(r"Ended \(\d+\)")).click()
    page.wait_for_timeout(400)

    rows = page.locator('[data-testid="session-row"]')
    total = rows.count()
    print(f"U1 ended rows on page 1: {total}")
    check("U1 ended list paginates at 20 rows", total <= 20, f"found {total}")
    if total == 0:
        check("U1 has ended sessions to open", False, "no ended sessions in this database")
        return

    # A long Ended list is exactly the case that broke: scroll to the bottom
    # before clicking the last row's button.
    page.mouse.wheel(0, 4000)
    page.wait_for_timeout(300)
    scroll_before = page.evaluate("window.scrollY")

    last_row = rows.nth(total - 1)
    last_row.locator('[data-testid="view-resources"]').click()
    page.wait_for_selector('[data-testid="modal-panel"]', timeout=5000)
    page.wait_for_timeout(300)

    box = page.locator('[data-testid="modal-panel"]').bounding_box()
    viewport = page.viewport_size
    scroll_after = page.evaluate("window.scrollY")
    body_overflow = page.evaluate("getComputedStyle(document.body).overflow")

    print(f"U1 modal box={box} viewport={viewport} scrollY {scroll_before}->{scroll_after}")
    check(
        "U1 modal is inside the viewport",
        bool(box) and box["y"] >= 0 and box["x"] >= 0
        and box["y"] + box["height"] <= viewport["height"] + 1
        and box["x"] + box["width"] <= viewport["width"] + 1,
        f"box={box} viewport={viewport}",
    )
    check("U1 opening the modal does not scroll the page", scroll_before == scroll_after,
          f"{scroll_before} -> {scroll_after}")
    check("U1 body scroll is locked behind the modal", body_overflow == "hidden", body_overflow)

    page.screenshot(path=str(SHOTS / "add13-u1-resources-modal.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    check("U1 Esc closes the modal",
          page.locator('[data-testid="modal-panel"]').count() == 0,
          "modal still visible after Escape")

    page.locator('[data-testid="ended-search"]').fill("zzz-no-such-session-zzz")
    page.wait_for_timeout(300)
    check("U1 search filters the ended list",
          page.locator('[data-testid="session-row"]').count() == 0,
          "search did not filter")
    page.locator('[data-testid="ended-search"]').fill("")


def run_u2(page) -> None:
    sessions = api_json(page, "/sessions")
    stamps = []

    def walk(value, path="$"):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str) and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", item):
                    stamps.append((f"{path}.{key}", item))
                else:
                    walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(sessions)
    naive = [f"{key}={value}" for key, value in stamps if not value.endswith("Z")]
    print(f"U2 session timestamps checked: {len(stamps)}")
    check("U2 /api/sessions returns UTC timestamps ending in Z", not naive, "; ".join(naive[:5]))

    sources = api_json(page, "/rag/sources")
    items = sources if isinstance(sources, list) else (sources.get("sources") or [])
    if not items:
        check("U2 knowledge base has a document to display", False, "no sources returned")
        return
    raw = items[0].get("ingested_at") or ""
    check("U2 /api/rag/sources returns UTC timestamps ending in Z", raw.endswith("Z"), raw)

    page.goto(f"{BASE_URL}/instructor/knowledge-base", wait_until="networkidle")
    page.wait_for_timeout(800)
    expand = page.locator('[data-testid="library-expand"]').first
    if expand.count() == 0:
        check("U2 knowledge base library card is visible", False, "no library card found")
        return
    expand.click()
    page.wait_for_timeout(300)
    page.screenshot(path=str(SHOTS / "add13-u2-kb-indexed-time.png"))
    if raw:
        expected = (
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
            .astimezone(ZoneInfo("Africa/Cairo"))
            .strftime("%H:%M")
        )
        shown = page.locator('[data-testid="library-indexed"]').first.inner_text()
        print(f"U2 raw={raw} expected Cairo {expected} shown='{shown}'")
        check(
            "U2 knowledge base shows Cairo time for the ingested_at instant",
            expected in shown,
            f"expected {expected} (Africa/Cairo), shown '{shown}' from {raw}",
        )


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            timezone_id="Africa/Cairo",
            locale="en-GB",
        )
        page = context.new_page()
        login(page)
        run_u1(page)
        run_u2(page)
        browser.close()

    print("FAILURES:", json.dumps(FAILURES))
    print("WALKTHROUGH_EXIT=", 1 if FAILURES else 0)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
