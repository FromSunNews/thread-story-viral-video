"""
Standalone worker: scrapes one Threads URL and prints JSON to stdout.
Called as a subprocess by modules/scraper.py to ensure clean Playwright state.

Usage:
    python scripts/threads_scraper_worker.py <url> <max_comments>
"""

import asyncio
import json
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))


async def scrape(url: str, max_comments: int) -> dict:
    from playwright.async_api import async_playwright
    from scripts.threads_bulk_scraper import (
        _setup_context, _parse_post_text, _extract_media,
        _extract_comment_extras, _get_first_reply,
    )

    async with async_playwright() as p:
        browser, context = await _setup_context(p, with_cookies=True)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for React to render containers
            try:
                await page.wait_for_selector("[data-pressable-container]", timeout=20000)
            except Exception:
                pass

            containers = await page.query_selector_all("[data-pressable-container]")

            if not containers:
                return {
                    "topic": {"text": f"Could not load {url}", "author": "@user",
                              "likes": "0", "card_type": "topic"},
                    "comments": [],
                    "url": url,
                }

            # Topic
            topic_raw = await containers[0].inner_text()
            t_author, t_ts, t_text, t_likes, t_replies, t_reposts, t_shares = _parse_post_text(topic_raw)
            t_avatar, t_images = await _extract_media(containers[0])

            topic = {
                "text": t_text[:600] or url,
                "author": t_author or "@threads_user",
                "likes": t_likes,
                "replies": t_replies,
                "reposts": t_reposts,
                "shares": t_shares,
                "timestamp": t_ts,
                "avatar_url": t_avatar,
                "images": t_images,
                "card_type": "topic",
            }

            # Comment permalink links
            links = await page.query_selector_all("a[href*='/post/']")
            post_slug = url.split("/post/")[-1].split("?")[0]
            comment_hrefs = []
            seen_hrefs = set()
            for link in links:
                h = await link.get_attribute("href") or ""
                if h and h not in seen_hrefs and post_slug not in h:
                    seen_hrefs.add(h)
                    comment_hrefs.append(h)

            # Comments
            comments = []
            for i, el in enumerate(containers[1:max_comments + 1]):
                try:
                    raw = await el.inner_text()
                    author, ts, text, likes, replies, reposts, shares = _parse_post_text(raw)
                    if not text or len(text) < 10:
                        continue

                    avatar_url, image_urls = await _extract_media(el)
                    extras = await _extract_comment_extras(el)

                    first_reply = ""
                    if i < len(comment_hrefs):
                        first_reply = await _get_first_reply(context, comment_hrefs[i])

                    comments.append({
                        "id": f"c{i+1:03d}",
                        "author": author,
                        "text": text[:500],
                        "likes": likes,
                        "timestamp": ts,
                        "avatar_url": avatar_url,
                        "images": image_urls,
                        "is_pinned": extras["is_pinned"],
                        "liked_by_author": extras["liked_by_author"],
                        "first_reply": first_reply,
                        "replies": replies,
                        "reposts": reposts,
                        "shares": shares,
                        "badge": "",
                        "liked_by": "",
                        "sentiment": None,
                        "emotion": None,
                    })
                except Exception:
                    continue

        finally:
            await browser.close()

    return {"topic": topic, "comments": comments, "url": url}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: worker.py <url> <max_comments>"}))
        sys.exit(1)

    url = sys.argv[1]
    max_comments = int(sys.argv[2])

    result = asyncio.run(scrape(url, max_comments))
    # Print JSON to stdout; all other logs go to stderr
    print(json.dumps(result, ensure_ascii=False))
