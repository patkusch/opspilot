"""Regenerate docs/hero.png: a real 2x screenshot of the running app.

Start the app first (uvicorn app.main:app --port 8000), then run this with any
Python that has Playwright and a Chromium installed:

    python docs/make_hero.py [http://127.0.0.1:8000]

It resets the demo data, types "write off everything" as Priya Shah, previews
the plan, approves the run, and crops the screenshot to the part that shows
the guardrails working. No text or number on the page is touched. To keep the picture a sensible
height it gives the list of written-off items the same scrolling box the page
already gives the escalated list, and scrolls the escalated list so three
kinds of refusal sit side by side.
The page loads Tailwind from a CDN, so the machine needs internet access.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "hero.png"
INTENT = "write off everything"
OPERATOR = "Priya Shah"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1152, "height": 900}, device_scale_factor=2,
                                color_scheme="dark")
        page.goto(URL, wait_until="networkidle")
        page.click("#reset")
        page.wait_for_function("document.querySelector('#s-open').textContent.trim() === '60'")

        page.fill("#intent", INTENT)
        page.fill("#operator", OPERATOR)
        page.click("#preview")
        page.wait_for_selector("#plan:not(.hidden)")
        page.click("#run")
        page.wait_for_selector("#result:not(.hidden)")
        page.wait_for_timeout(1200)  # let the smooth scroll and the queue refresh settle

        # Bring three different refusals into view in the escalated list:
        # over the dual-control line, a few pounds over the write-off limit, too fresh.
        page.evaluate("""() => {
          const [left, pane] = document.querySelectorAll('#plan div[class~="space-y-1.5"]');
          left.classList.add('max-h-80', 'overflow-auto');
          const row = [...pane.children].find(r => r.textContent.includes('BRK-2021'));
          pane.scrollTop = row.offsetTop - pane.offsetTop - 8;
          window.scrollTo(0, 0);
        }""")
        page.wait_for_timeout(300)

        box = page.evaluate("""() => {
          const top = document.querySelector('#intent').closest('section').getBoundingClientRect().top + scrollY;
          const bottom = document.querySelector('#result').getBoundingClientRect().bottom + scrollY;
          return {top, bottom};
        }""")
        pad = 16
        clip = {"x": 0, "y": max(box["top"] - pad, 0), "width": 1152,
                "height": box["bottom"] - box["top"] + 2 * pad}
        page.screenshot(path=str(OUT), full_page=True, clip=clip)
        browser.close()
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
