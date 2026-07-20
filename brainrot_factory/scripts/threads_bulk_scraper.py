"""
Threads Bulk Scraper
--------------------
Two modes:
  1. saved   — scrape your saved posts at threads.com/saved (requires login cookies)
  2. search  — scrape posts by keyword (public, cookies optional but recommended)

Output: JSON list of raw_content items ready for the pipeline.

Usage:
    # Scrape saved posts (no username needed)
    python scripts/threads_bulk_scraper.py --mode saved --limit 30

    # Scrape by keyword
    python scripts/threads_bulk_scraper.py --mode search --keyword "chuyện cười" --limit 50

    # Output to a file
    python scripts/threads_bulk_scraper.py --mode search --keyword "shipper" --limit 20 --out data/scraped_threads.json
"""

import argparse
import asyncio
import json
import re
import unicodedata
from pathlib import Path

from loguru import logger


COOKIE_PATH = Path("config/threads_cookies.json")
DEFAULT_OUT = Path("data/threads_bulk.json")

SCROLL_PAUSE = 2.5   # seconds between scrolls
MAX_SCROLLS = 40     # safety cap


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#x27;', "'", text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def _load_cookies() -> list:
    if not COOKIE_PATH.exists():
        logger.warning(f"No cookies found at {COOKIE_PATH}. Run threads_cookie_capture.py first.")
        return []
    with open(COOKIE_PATH, encoding="utf-8") as f:
        return json.load(f)


async def _setup_context(playwright, with_cookies: bool = True):
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    )

    if with_cookies:
        cookies = _load_cookies()
        if cookies:
            await context.add_cookies(cookies)
            logger.info(f"Loaded {len(cookies)} cookies")

    return browser, context


_NUM_PAT = re.compile(r'^\d+(\.\d+)?[KkMm]?$')
_SMALL_INT_PAT = re.compile(r'^\d{1,4}$')   # plain integer ≤ 9999 (gallery page indicator)
_UI_NOISE = {
    "Translate", "See translation", "Dịch", "See more", "Xem thêm",
    "·", "•",
    "Top View activity", "View activity", "Top View", "Top",
    "Reply", "Trả lời", "Like", "Thích",
    "Follow", "Following", "Theo dõi", "Đang theo dõi",
    "Pinned", "Được ghim",
}
_UI_NOISE_RE = re.compile(
    r'^(View\s+activity|Top\s+View|See\s+(more|translation)|Xem\s+thêm)$',
    re.IGNORECASE,
)


def _parse_post_text(raw: str) -> tuple[str, str, str, str, str, str, str]:
    """
    Parse inner_text of a [data-pressable-container] element.
    Returns: (author, timestamp, text, likes, replies, reposts, shares)

    Handles Threads quirks:
    - Gallery indicator: 'n / m' lines (image page numbers) → skip
    - UI noise: Translate, Top View activity, etc. → skip
    - Engagement counters: last 4 numbers = likes, replies, reposts, shares
    """
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if len(lines) < 2:
        return "", "", "", "0", "0", "0", "0"

    author = f"@{lines[0].lstrip('@')}"
    timestamp = lines[1]

    body_lines = []
    counters = []

    i = 2
    while i < len(lines):
        line = lines[i]

        # Skip UI noise
        if line in _UI_NOISE or _UI_NOISE_RE.match(line):
            i += 1
            continue

        # Gallery indicator: small_int "/" small_int  → skip all 3
        if (
            _SMALL_INT_PAT.match(line)
            and i + 2 < len(lines)
            and lines[i + 1] == "/"
            and _SMALL_INT_PAT.match(lines[i + 2])
        ):
            i += 3
            continue

        # Lone "/" separator
        if line == "/":
            i += 1
            continue

        # Engagement counter (number)
        if _NUM_PAT.match(line):
            counters.append(line)
            i += 1
            continue

        # Body text — only before counters start
        if not counters:
            body_lines.append(line)
        i += 1

    text = _normalize_text("\n".join(body_lines))
    likes   = counters[0] if len(counters) > 0 else "0"
    replies = counters[1] if len(counters) > 1 else "0"
    reposts = counters[2] if len(counters) > 2 else "0"
    shares  = counters[3] if len(counters) > 3 else "0"
    return author, timestamp, text, likes, replies, reposts, shares


async def _extract_posts_from_page(page, seen_ids: set) -> list:
    """Extract post cards from the current page DOM."""
    posts = []

    containers = await page.query_selector_all("[data-pressable-container]")

    for el in containers:
        try:
            raw = await el.inner_text()
            author, timestamp, text, likes, replies, reposts, shares = _parse_post_text(raw)

            if not text or len(text) < 20:
                continue

            post_id = str(hash(text[:100]))
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)

            # Post URL
            post_url = ""
            try:
                link = await el.query_selector("a[href*='/post/']")
                if link:
                    href = await link.get_attribute("href")
                    if href:
                        post_url = f"https://www.threads.com{href}" if href.startswith("/") else href
            except Exception:
                pass

            avatar_url, image_urls = await _extract_media(el)

            posts.append({
                "_id": post_id,
                "author": author,
                "timestamp": timestamp,
                "text": text[:600],
                "likes": likes,
                "url": post_url,
                "avatar_url": avatar_url,
                "images": image_urls,
            })

        except Exception:
            continue

    return posts


async def _scroll_and_collect(page, limit: int) -> list:
    """Scroll page, collecting posts until limit reached."""
    seen_ids: set = set()
    all_posts = []
    scroll_count = 0

    while len(all_posts) < limit and scroll_count < MAX_SCROLLS:
        new = await _extract_posts_from_page(page, seen_ids)
        all_posts.extend(new)
        logger.info(f"  Collected {len(all_posts)}/{limit} posts (scroll {scroll_count+1})")

        if len(all_posts) >= limit:
            break

        # Scroll down
        prev_height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(SCROLL_PAUSE)

        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == prev_height:
            logger.info("Reached end of page (no more content)")
            break

        scroll_count += 1

    return all_posts[:limit]


async def _get_first_reply(context, comment_url: str) -> str:
    """Visit a comment permalink and return the first reply text (container[1])."""
    if not comment_url:
        return ""
    page = await context.new_page()
    try:
        await page.goto(f"https://www.threads.com{comment_url}", wait_until="domcontentloaded", timeout=20000)
        containers = []
        for attempt in range(2):
            await asyncio.sleep(2 + attempt * 2)
            containers = await page.query_selector_all("[data-pressable-container]")
            if len(containers) >= 3:
                break
        # [0]=topic, [1]=comment itself, [2]=first reply
        if len(containers) >= 3:
            raw = await containers[2].inner_text()
            _, _, text, *_ = _parse_post_text(raw)
            return text[:300]
    except Exception:
        pass
    finally:
        await page.close()
    return ""


_PROFILE_PIC_SEGMENTS = ("t51.82787-19", "t51.2885-19", "t51.9999777-19")


def _is_profile_pic_url(src: str) -> bool:
    """Instagram/Threads CDN: profile pics use the -19 segment, content uses -15."""
    return any(seg in src for seg in _PROFILE_PIC_SEGMENTS)


async def _extract_media(el) -> tuple[str, list[str]]:
    """
    Extract avatar_url and post image URLs from a container element.
    Returns (avatar_url, [image_url, ...])
    - Avatar: first CDN img (profile pic segment or first img overall)
    - Post images: CDN imgs with content segment (-15 path), deduplicated
    """
    avatar_url = ""
    image_urls = []
    seen = set()
    try:
        imgs = await el.query_selector_all("img")
        for img in imgs:
            src = await img.get_attribute("src") or ""
            if not src or "http" not in src:
                continue
            is_cdn = any(d in src for d in ("fbcdn", "cdninstagram", "instagram"))
            if not is_cdn:
                continue
            if _is_profile_pic_url(src):
                # Profile picture — use first one as avatar, ignore the rest
                if not avatar_url:
                    avatar_url = src
            else:
                # Content image (t51.82787-15 etc.)
                base = src.split("?")[0]
                if base not in seen:
                    seen.add(base)
                    image_urls.append(src)
    except Exception:
        pass
    return avatar_url, image_urls


async def _extract_avatar_url(el) -> str:
    """Convenience wrapper — returns avatar URL only."""
    avatar_url, _ = await _extract_media(el)
    return avatar_url


async def _extract_comment_extras(el) -> dict:
    """Extract is_pinned and liked_by_author flags from a comment container."""
    extras = {"is_pinned": False, "liked_by_author": False}
    try:
        raw = await el.inner_text()
        lower = raw.lower()
        if "pinned" in lower or "được ghim" in lower or "đã ghim" in lower:
            extras["is_pinned"] = True
        # "Liked by author" text or heart-by-author indicator
        if "liked by author" in lower or "tác giả thích" in lower or "được tác giả thích" in lower:
            extras["liked_by_author"] = True
        # Also check aria-label attributes
        if not extras["liked_by_author"]:
            els = await el.query_selector_all("[aria-label]")
            for ae in els:
                label = (await ae.get_attribute("aria-label") or "").lower()
                if "author" in label and ("like" in label or "heart" in label):
                    extras["liked_by_author"] = True
                    break
    except Exception:
        pass
    return extras


async def _scrape_comments(context, post_url: str, max_comments: int = 6) -> list:
    """Visit a post URL, scrape comments + 1 reply each."""
    if not post_url:
        return []
    page = await context.new_page()
    comments = []
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)

        # Wait until containers appear, retry up to 3 times
        containers = []
        for attempt in range(3):
            await asyncio.sleep(3 + attempt * 2)  # 3s, 5s, 7s
            containers = await page.query_selector_all("[data-pressable-container]")
            if len(containers) >= 2:
                break
            logger.debug(f"    Retry {attempt+1}: found {len(containers)} containers for {post_url}")

        # Get comment permalink links from the page
        links = await page.query_selector_all("a[href*='/post/']")
        comment_hrefs = []
        seen = set()
        for link in links:
            h = await link.get_attribute("href")
            if h and h not in seen and post_url.split("/post/")[1] not in h:
                seen.add(h)
                comment_hrefs.append(h)

        for i, el in enumerate(containers[1:max_comments + 1]):  # skip [0] = topic
            try:
                raw = await el.inner_text()
                author, timestamp, text, likes, replies, reposts, shares = _parse_post_text(raw)
                if not text or len(text) < 10:
                    continue

                avatar_url, image_urls = await _extract_media(el)
                extras = await _extract_comment_extras(el)

                # Get 1 reply if comment has its own permalink
                first_reply = ""
                if i < len(comment_hrefs):
                    first_reply = await _get_first_reply(context, comment_hrefs[i])

                comments.append({
                    "id": f"c{i+1:03d}",
                    "author": author,
                    "text": text[:500],
                    "likes": likes,
                    "timestamp": timestamp,
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
    except Exception as e:
        logger.warning(f"Failed to scrape comments for {post_url}: {e}")
    finally:
        await page.close()
    return comments


async def scrape_saved(limit: int, max_comments: int = 6) -> list:
    """Scrape saved posts at threads.com/saved (requires login cookies)."""
    from playwright.async_api import async_playwright

    url = "https://www.threads.com/saved"
    logger.info(f"Scraping saved posts: {url}")

    async with async_playwright() as p:
        browser, context = await _setup_context(p, with_cookies=True)
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        if "login" in page.url or "accounts" in page.url:
            logger.error("Redirected to login — cookies may be expired. Run threads_cookie_capture.py again.")
            await browser.close()
            return []

        posts = await _scroll_and_collect(page, limit)

        # Scrape comments for each post
        for i, post in enumerate(posts):
            if post.get("url"):
                logger.info(f"  [{i+1}/{len(posts)}] Fetching comments: {post['url']}")
                post["comments"] = await _scrape_comments(context, post["url"], max_comments)
                logger.info(f"    → {len(post['comments'])} comments")
            else:
                post["comments"] = []

        await browser.close()

    logger.success(f"Collected {len(posts)} saved posts with comments")
    return posts


async def scrape_search(keyword: str, limit: int, max_comments: int = 6) -> list:
    """Scrape Threads search results for a keyword."""
    from playwright.async_api import async_playwright

    encoded = keyword.replace(" ", "%20")
    url = f"https://www.threads.com/search?q={encoded}&serp_type=default"
    logger.info(f"Searching Threads: {url}")

    async with async_playwright() as p:
        browser, context = await _setup_context(p, with_cookies=COOKIE_PATH.exists())
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        posts = await _scroll_and_collect(page, limit)

        # Scrape comments for each post
        for i, post in enumerate(posts):
            if post.get("url"):
                logger.info(f"  [{i+1}/{len(posts)}] Fetching comments: {post['url']}")
                post["comments"] = await _scrape_comments(context, post["url"], max_comments)
                logger.info(f"    → {len(post['comments'])} comments")
            else:
                post["comments"] = []

        await browser.close()

    logger.success(f"Collected {len(posts)} posts for keyword '{keyword}'")
    return posts


def _to_raw_content_format(posts: list) -> list:
    """Convert bulk posts to raw_content.json format for the pipeline."""
    results = []
    for post in posts:
        results.append({
            "topic": {
                "author": post["author"],
                "text": post["text"],
                "likes": post["likes"],
                "timestamp": post.get("timestamp", ""),
                "avatar_url": post.get("avatar_url", ""),
                "images": post.get("images", []),
                "card_type": "topic"
            },
            "comments": post.get("comments", []),
            "url": post.get("url", "")
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="Threads Bulk Scraper")
    parser.add_argument("--mode", choices=["saved", "search"], required=True)
    parser.add_argument("--keyword", help="Search keyword (for --mode search)")
    parser.add_argument("--limit", type=int, default=30, help="Max posts to collect")
    parser.add_argument("--max-comments", type=int, default=6, help="Max comments per post")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT), help="Output JSON path")
    args = parser.parse_args()

    if args.mode == "saved":
        posts = asyncio.run(scrape_saved(args.limit, args.max_comments))
    else:
        if not args.keyword:
            parser.error("--keyword required for search mode")
        posts = asyncio.run(scrape_search(args.keyword, args.limit, args.max_comments))

    if not posts:
        logger.warning("No posts collected.")
        return

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Save raw list
    raw_list = _to_raw_content_format(posts)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw_list, f, indent=2, ensure_ascii=False)

    logger.success(f"Saved {len(raw_list)} items → {out_path}")
    print(f"\nNext step: pick a post and run the pipeline with:")
    print(f"  python main.py --manual {out_path} --index 0")


if __name__ == "__main__":
    main()
