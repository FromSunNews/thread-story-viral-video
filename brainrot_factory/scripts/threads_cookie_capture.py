"""
Threads Cookie Capture
----------------------
Opens a visible browser, lets you log in to Threads,
then saves session cookies to config/threads_cookies.json.

Usage:
    python scripts/threads_cookie_capture.py
"""

import asyncio
import json
from pathlib import Path

from loguru import logger


THREADS_URL = "https://www.threads.net"
COOKIE_PATH = Path("config/threads_cookies.json")


async def capture():
    from playwright.async_api import async_playwright

    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        logger.info("Opening browser — please log in to Threads...")
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-size=1280,900"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        page = await context.new_page()
        await page.goto(THREADS_URL)

        logger.info("Waiting for you to log in... (press Enter here when done)")
        input("  → Log in on the browser, then press Enter to save cookies: ")

        cookies = await context.cookies()
        with open(COOKIE_PATH, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)

        logger.success(f"Saved {len(cookies)} cookies → {COOKIE_PATH}")
        await browser.close()


def main():
    asyncio.run(capture())


if __name__ == "__main__":
    main()
