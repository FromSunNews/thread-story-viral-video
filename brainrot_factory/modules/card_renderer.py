"""
Module 2 — Card Renderer
Renders Threads-style comment cards as PNG images using Playwright.
Outputs PNG files to output/jobs/{job_id}/cards/

Design: matches real Threads mobile app UI — black background, circular avatar,
bold white username, gray timestamp, white text, gray action icons.
"""

import asyncio
import base64
import hashlib
import re
from pathlib import Path

from loguru import logger


# ---------------------------------------------------------------------------
# Vietnamese profanity censor
# ---------------------------------------------------------------------------

def _load_viet_profanity() -> list[str]:
    """Load Vietnamese offensive words from bundled dataset (blue-eyes-vn/vietnamese-offensive-words)."""
    word_file = Path(__file__).parent.parent / "assets" / "data" / "vn_offensive_words.txt"
    words = []
    if word_file.exists():
        for line in word_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.append(line)
    return words


_VIET_PROFANITY = _load_viet_profanity()

# Build compiled regex once (case-insensitive, Unicode)
# Sort longest first so multi-word phrases match before their components
_CENSOR_PATTERN = re.compile(
    r'(?<!\w)(' + '|'.join(re.escape(p) for p in sorted(_VIET_PROFANITY, key=len, reverse=True)) + r')(?!\w)',
    re.IGNORECASE,
) if _VIET_PROFANITY else None


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _censor_text_html(text: str) -> str:
    """
    Returns HTML string with Vietnamese profanity wrapped in .censored spans.
    Non-profane parts are HTML-escaped normally.
    """
    if not _CENSOR_PATTERN:
        return _html_escape(text)
    parts = []
    last = 0
    for m in _CENSOR_PATTERN.finditer(text):
        parts.append(_html_escape(text[last:m.start()]))
        parts.append(f'<span class="censored">{_html_escape(m.group(0))}</span>')
        last = m.end()
    parts.append(_html_escape(text[last:]))
    return "".join(parts)


def _get_avatar_color(username: str) -> str:
    """Generate consistent gray-tone color for avatar placeholder based on username."""
    colors = ["#3A3A3A", "#404040", "#464646", "#3D3D3D", "#424242"]
    idx = int(hashlib.md5(username.encode()).hexdigest(), 16) % len(colors)
    return colors[idx]


def _get_initials(username: str) -> str:
    """Get 1-2 char initials from username."""
    clean = username.lstrip("@u/").strip()
    if not clean:
        return "?"
    parts = clean.replace("_", " ").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return clean[:2].upper()


async def _fetch_image_b64(url: str, timeout: int = 8) -> str:
    """Fetch image URL and return as base64 data URI. Returns '' on failure."""
    if not url:
        return ""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                if r.status == 200:
                    content_type = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
                    data = await r.read()
                    b64 = base64.b64encode(data).decode()
                    return f"data:{content_type};base64,{b64}"
    except Exception as e:
        logger.debug(f"Image fetch failed for {url[:60]}: {e}")
    return ""


async def _fetch_avatar_b64(url: str) -> str:
    """Fetch avatar image URL and return as base64 data URI. Returns '' on failure."""
    return await _fetch_image_b64(url, timeout=8)


def _render_threads_html(comment: dict) -> str:
    """
    Render a single Threads-style comment card as self-contained HTML.
    Matches the real Threads mobile app layout:
    - Pure black/transparent background, no card box
    - Circular avatar (photo or gray placeholder with initials)
    - Bold white username + gray timestamp on same row
    - White comment text
    - Gray action icons (heart, reply, repost, share) with counts
    """
    author = comment.get("author", "@user")
    text = comment.get("text", "")
    likes = comment.get("likes", "0")
    timestamp = comment.get("timestamp", "Just now")
    avatar_b64 = comment.get("avatar_b64", "")
    is_topic = comment.get("card_type") == "topic"
    badge = comment.get("badge", "")
    is_pinned = comment.get("is_pinned", False)

    # HTML: profanity gets blur-censored spans; rest is HTML-escaped
    text_escaped = _censor_text_html(text)
    author_display = author.lstrip("@")
    author_escaped = _html_escape(author_display)

    # Avatar size: topic gets 84px, comments get 66px (1.5x scale for readability)
    avatar_size = 120 if is_topic else 96

    # Avatar: real photo or dark gray circle with person silhouette (Threads default)
    silhouette_size = int(avatar_size * 0.62)
    if avatar_b64:
        avatar_img = f'<img src="{avatar_b64}" style="width:{avatar_size}px;height:{avatar_size}px;border-radius:50%;object-fit:cover;display:block;flex-shrink:0;">'
    else:
        avatar_img = f'''<div style="
            width:{avatar_size}px;height:{avatar_size}px;border-radius:50%;
            background:#2E2E2E;
            display:flex;align-items:center;justify-content:center;
            overflow:hidden;flex-shrink:0;
        "><svg viewBox="0 0 24 24" width="{silhouette_size}" height="{silhouette_size}" fill="#888888">
            <circle cx="12" cy="8.5" r="3.5"/>
            <path d="M12 14c-5.33 0-8 2.67-8 4v1.5h16V18c0-1.33-2.67-4-8-4z"/>
        </svg></div>'''

    # "+" follow button on avatar (topic AND comments)
    follow_dot = ""
    if True:
        follow_dot = '''<div style="
            position:absolute;bottom:-4px;right:-4px;
            width:40px;height:40px;border-radius:50%;
            background:#FFFFFF;border:3px solid #181818;
            display:flex;align-items:center;justify-content:center;
        "><svg viewBox="0 0 24 24" width="20" height="20" fill="none"
              stroke="#222" stroke-width="2.8" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
        </svg></div>'''

    avatar_html = f'''<div style="position:relative;width:{avatar_size}px;height:{avatar_size}px;flex-shrink:0;">
        {avatar_img}
        {follow_dot}
    </div>'''

    # Header layout:
    # Topic:   [username] [timestamp]  →auto→  [Follow]
    # Comment: [username] [timestamp · badge?]  →auto→  [❤ tiny-avatar?] [···]
    ts_style = 'font-size:36px;color:#888888;margin-left:12px;white-space:nowrap;font-weight:400;flex-shrink:0;'

    # Three-dot menu SVG (always on comments)
    dots_svg = (
        '<svg width="33" height="33" viewBox="0 0 24 24" fill="#888888">'
        '<circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>'
        '</svg>'
    )

    if is_topic:
        username_suffix = f'<span style="{ts_style}">{timestamp}</span>'
        header_right = (
            f'<div style="margin-left:auto;padding-left:16px;flex-shrink:0;">'
            f'{dots_svg}'
            f'</div>'
        )
    else:
        badge_html = f'<span style="color:#888888;font-weight:400;"> · {badge}</span>' if badge else ''
        # Pinned indicator: pin icon + label
        pin_html = ""
        if is_pinned:
            pin_html = (
                '<span style="color:#888888;font-weight:400;display:inline-flex;'
                'align-items:center;gap:5px;margin-left:10px;">'
                '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" '
                'stroke="#888888" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M12 2l2 6h5l-4 3 1.5 6L12 14l-4.5 3L9 11 5 8h5z"/>'
                '</svg>Pinned</span>'
            )
        username_suffix = f'<span style="{ts_style}">{timestamp}{badge_html}{pin_html}</span>'

        # Right side: optional ❤ + tiny avatar, then ···
        liked_by = comment.get("liked_by", "")
        liked_by_b64 = comment.get("liked_by_avatar_b64", "")
        liked_html = ""
        if liked_by:
            # Liked indicator: avatar circle with small deep-red ❤ badge at bottom-left
            if liked_by_b64:
                avatar_inner = (
                    f'<img src="{liked_by_b64}" width="42" height="42" '
                    f'style="border-radius:50%;object-fit:cover;display:block;">'
                )
            else:
                avatar_inner = (
                    '<div style="width:42px;height:42px;border-radius:50%;'
                    'background:#6B4C38;overflow:hidden;'
                    'display:flex;align-items:center;justify-content:center;">'
                    '<svg viewBox="0 0 24 24" width="26" height="26" fill="#9A7060">'
                    '<circle cx="12" cy="8" r="3.5"/>'
                    '<path d="M12 13.5c-5 0-8 2.5-8 5v1h16v-1c0-2.5-3-5-8-5z"/>'
                    '</svg></div>'
                )
            # ❤ badge overlapping bottom-left of avatar
            heart_badge = (
                '<div style="position:absolute;bottom:-2px;left:-4px;'
                'width:18px;height:18px;border-radius:50%;background:#000;'
                'display:flex;align-items:center;justify-content:center;">'
                '<svg viewBox="0 0 24 24" width="13" height="13" fill="#C00020">'
                '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3'
                'c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5'
                'c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>'
                '</svg></div>'
            )
            liked_html = (
                f'<div style="position:relative;width:42px;height:42px;flex-shrink:0;">'
                f'{avatar_inner}{heart_badge}'
                f'</div>'
            )
        header_right = (
            f'<div style="margin-left:auto;display:flex;align-items:center;gap:10px;'
            f'flex-shrink:0;padding-left:12px;">'
            f'{liked_html}{dots_svg}'
            f'</div>'
        )

    topic_timestamp_row = ""  # unused, timestamp now always inline

    # Action icons — exact SVG paths from Threads source code
    C = 'fill="#888888"'

    heart_svg = f'''<svg width="42" height="40" viewBox="-0.5 0 25 24" {C}>
        <path d="M16.5 2C14.8335 2 13.2217 2.70703 12 3.93652C10.7783 2.70704 9.1665 2 7.5 2C3.3785 2 0.5 5.08423 0.5 9.5C0.5 14.1284 4.84516 19.4619 11.311 22.7719C11.5267 22.8827 11.7633 22.9379 12 22.9379C12.2367 22.9379 12.4733 22.8827 12.689 22.7719C19.1548 19.4619 23.5 14.1284 23.5 9.5C23.5 5.08423 20.6217 2 16.5 2ZM12 20.8764C6.30767 17.8962 2.5 13.3467 2.5 9.5C2.5 6.15893 4.4625 4 7.5 4C9.5 4 11.25 5.75 12 7.5C12.75 5.75 14.5 4 16.5 4C19.5377 4 21.5 6.15893 21.5 9.5C21.5 13.3467 17.6923 17.8962 12 20.8764Z"/>
    </svg>'''

    reply_svg = f'''<svg width="42" height="42" viewBox="0 0 24 24" {C}>
        <path fill-rule="evenodd" clip-rule="evenodd" d="M12 3C7.02944 3 3 7.02944 3 12C3 16.9706 7.02944 21 12 21C13.414 21 14.7492 20.6747 15.9373 20.0956C16.1277 20.0028 16.3428 19.9728 16.5514 20.0101L20.7565 20.7619L19.9927 16.5927C19.954 16.3815 19.9843 16.1633 20.0792 15.9707C20.6685 14.7742 21 13.4273 21 12C21 7.02944 16.9706 3 12 3ZM1 12C1 5.92486 5.92488 1 12 1C18.0752 1 23 5.92488 23 12C23 13.6205 22.649 15.1615 22.018 16.549L22.9836 21.8198C23.0427 22.1423 22.94 22.4733 22.7086 22.7056C22.4773 22.938 22.1468 23.0421 21.824 22.9844L16.512 22.0348C15.1341 22.6553 13.6061 23 12 23C5.92488 23 1 18.0752 1 12Z"/>
    </svg>'''

    repost_svg = f'''<svg width="42" height="42" viewBox="0 0 24 24" {C}>
        <path d="M4.51617 6.9986C6.13179 4.58593 8.88099 2.99979 11.9995 2.99979C15.7267 2.99979 18.9259 5.26459 20.2927 8.49676C20.5079 9.00543 21.0946 9.24341 21.6033 9.0283C22.1119 8.81318 22.3499 8.22644 22.1348 7.71777C20.466 3.7716 16.5582 0.999786 11.9995 0.999786C8.27776 0.999786 4.9897 2.84823 2.99988 5.67416V2.9986C2.99988 2.44631 2.55216 1.9986 1.99988 1.9986C1.44759 1.9986 0.999878 2.44631 0.999878 2.9986V7.9986C0.999878 8.55088 1.44759 8.9986 1.99988 8.9986H6.99988C7.55216 8.9986 7.99988 8.55088 7.99988 7.9986C7.99988 7.44631 7.55216 6.9986 6.99988 6.9986H4.51617Z"/>
        <path d="M2.39572 14.9713C2.90439 14.7562 3.49113 14.9942 3.70625 15.5029C5.07309 18.735 8.27228 20.9998 11.9995 20.9998C15.118 20.9998 17.8672 19.4137 19.4828 17.001H16.9991C16.4468 17.001 15.9991 16.5533 15.9991 16.001C15.9991 15.4487 16.4468 15.001 16.9991 15.001H21.9991C22.5514 15.001 22.9991 15.4487 22.9991 16.001V21.001C22.9991 21.5533 22.5514 22.001 21.9991 22.001C21.4468 22.001 20.9991 21.5533 20.9991 21.001V18.3255C19.0093 21.1514 15.7212 22.9998 11.9995 22.9998C7.44077 22.9998 3.53298 20.228 1.86419 16.2818C1.64908 15.7732 1.88705 15.1864 2.39572 14.9713Z"/>
    </svg>'''

    share_svg = f'''<svg width="42" height="42" viewBox="0 0 24 24" {C}>
        <path fill-rule="evenodd" clip-rule="evenodd" d="M7.2474 1.49853C4.18324 -0.187039 0.600262 2.64309 1.53038 6.01431L3.18181 12L1.53038 17.9857C0.600277 21.3569 4.18324 24.1871 7.2474 22.5015L20.8245 15.0329C23.2153 13.7177 23.2153 10.2823 20.8244 8.96712L7.2474 1.49853ZM3.45835 5.48239C2.99873 3.81649 4.76927 2.41796 6.28345 3.25089L19.8605 10.7195C20.0016 10.7971 20.123 10.8923 20.2247 11H4.98064L3.45835 5.48239ZM4.98064 13L3.45835 18.5176C2.99873 20.1835 4.76927 21.5821 6.28345 20.7491L19.8605 13.2805C20.0016 13.2029 20.123 13.1078 20.2247 13H4.98064Z"/>
    </svg>'''

    replies = comment.get("replies", "0")
    reposts = comment.get("reposts", "0")
    shares = comment.get("shares", "0")

    # Inline images block (appears below text, above actions)
    images_b64_list = comment.get("images_b64", [])
    images_html = ""
    if images_b64_list:
        n = len(images_b64_list)
        if n == 1:
            # Single image: full width, rounded corners
            images_html = f'''<div style="margin-top:6px;border-radius:18px;overflow:hidden;max-width:100%;">
                <img src="{images_b64_list[0]}" style="width:100%;display:block;border-radius:18px;">
            </div>'''
        elif n == 2:
            # Two images side by side
            imgs = "".join(
                f'<img src="{b}" style="width:calc(50% - 3px);border-radius:14px;object-fit:cover;aspect-ratio:1/1;">'
                for b in images_b64_list[:2]
            )
            images_html = f'<div style="display:flex;gap:6px;margin-top:6px;">{imgs}</div>'
        else:
            # 3+ images: first one large, rest in a row below (max 4 total)
            first = f'<img src="{images_b64_list[0]}" style="width:100%;border-radius:14px;object-fit:cover;aspect-ratio:16/9;">'
            rest = "".join(
                f'<img src="{b}" style="width:calc(33.3% - 4px);border-radius:12px;object-fit:cover;aspect-ratio:1/1;">'
                for b in images_b64_list[1:4]
            )
            rest_row = f'<div style="display:flex;gap:6px;">{rest}</div>' if rest else ""
            images_html = f'<div style="display:flex;flex-direction:column;gap:6px;margin-top:6px;">{first}{rest_row}</div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #181818;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  .card {{
    width: 1060px;
    padding: 33px 42px 27px 42px;
    background: #181818;
    display: flex;
    flex-direction: row;
    gap: 24px;
    align-items: flex-start;
  }}
  .content-col {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 15px;
    min-width: 0;
  }}
  .header-row {{
    display: flex;
    align-items: center;
  }}
  .username {{
    font-size: 45px;
    font-weight: 700;
    color: #FFFFFF;
    line-height: 1.2;
    white-space: nowrap;
  }}
  .comment-text {{
    font-size: 45px;
    color: #E8E8E8;
    line-height: 1.6;
    word-break: break-word;
    white-space: pre-wrap;
    margin-top: 3px;
  }}
  .actions {{
    display: flex;
    align-items: center;
    gap: 36px;
    margin-top: 9px;
  }}
  .action {{
    display: flex;
    align-items: center;
    gap: 10px;
    color: #888888;
    font-size: 36px;
    line-height: 1;
  }}
  .action svg {{ display: block; flex-shrink: 0; }}
  .censored {{
    display: inline-block;
    filter: blur(8px);
    background: rgba(100,100,100,0.45);
    border-radius: 5px;
    padding: 0 4px;
    user-select: none;
  }}
</style>
</head>
<body>
<div class="card">
  <div style="flex-shrink:0;">{avatar_html}</div>
  <div class="content-col">
    <div class="header-row">
      <span class="username">{author_escaped}</span>
      {username_suffix}
      {header_right}
    </div>
    <div class="comment-text">{text_escaped}</div>
    {images_html}
    <div class="actions">
      <div class="action">{heart_svg}<span>{likes}</span></div>
      <div class="action">{reply_svg}<span>{replies}</span></div>
      <div class="action">{repost_svg}<span>{reposts}</span></div>
      <div class="action">{share_svg}<span>{shares}</span></div>
    </div>
  </div>
</div>
</body>
</html>"""
    return html


async def _render_cards_async(items: list, output_dir: Path) -> list:
    """Render all cards using a single Playwright browser instance."""
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)

    # Fetch all avatars concurrently before opening browser
    logger.info("Fetching avatar images...")
    avatar_urls = [item.get("avatar_url", "") for item in items]
    avatar_b64s = await asyncio.gather(*[_fetch_avatar_b64(url) for url in avatar_urls])
    for item, b64 in zip(items, avatar_b64s):
        item["avatar_b64"] = b64
        if b64:
            logger.debug(f"Avatar fetched for {item.get('id', '?')}")

    # For comments liked by author: set liked_by_avatar_b64 = topic author's avatar
    topic_avatar_b64 = next(
        (it.get("avatar_b64", "") for it in items if it.get("card_type") == "topic"), ""
    )
    for item in items:
        if item.get("liked_by") and not item.get("liked_by_avatar_b64"):
            item["liked_by_avatar_b64"] = topic_avatar_b64

    # Fetch inline content images concurrently
    # If images_b64 already provided (pre-fetched), keep them; otherwise fetch from URLs
    for item in items:
        if item.get("images_b64"):
            continue  # already have base64 data
        image_urls = item.get("images", [])
        if image_urls:
            logger.debug(f"Fetching {len(image_urls)} image(s) for {item.get('id', '?')}")
            item["images_b64"] = await asyncio.gather(*[_fetch_image_b64(u) for u in image_urls])
        else:
            item["images_b64"] = []

    rendered = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1100, "height": 1920})
        page = await context.new_page()

        for item in items:
            card_id = item.get("id", "topic")
            out_path = output_dir / f"{card_id}.png"

            html = _render_threads_html(item)
            await page.set_content(html, wait_until="domcontentloaded")
            await asyncio.sleep(0.2)

            # Screenshot just the card element
            card_el = await page.query_selector(".card")
            if card_el:
                await card_el.screenshot(path=str(out_path), omit_background=False)
            else:
                await page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": 1060, "height": 300})

            item["card_path"] = str(out_path)
            rendered.append(item)
            logger.debug(f"Rendered card: {out_path}")

        await browser.close()

    return rendered


def run(config: dict) -> dict:
    """
    Module 2 entry point.
    Renders PNG cards for topic and all comments.
    Returns config with card_path set for each comment and topic.
    """
    job_id = config["job_id"]
    source = config["source"]

    cards_dir = Path(f"output/jobs/{job_id}/cards")

    # Build list of items to render: topic + comments
    items = []

    topic = source.get("topic", {})
    topic_author = topic.get("author", "")

    if topic:
        topic_item = dict(topic)
        topic_item["id"] = "topic"
        topic_item["card_type"] = "topic"
        items.append(topic_item)

    for comment in source.get("comments", []):
        c = dict(comment)
        # If author liked this comment, surface it in the card's liked_by field
        if c.get("liked_by_author") and not c.get("liked_by"):
            c["liked_by"] = topic_author
        items.append(c)

    logger.info(f"Rendering {len(items)} cards (Threads UI style)...")
    try:
        loop = asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
        rendered = loop.run_until_complete(_render_cards_async(items, cards_dir))
    except RuntimeError:
        rendered = asyncio.run(_render_cards_async(items, cards_dir))

    # Update config with card paths
    for item in rendered:
        if item.get("id") == "topic":
            config["source"]["topic"]["card_path"] = item.get("card_path", "")
        else:
            for comment in config["source"]["comments"]:
                if comment["id"] == item["id"]:
                    comment["card_path"] = item.get("card_path", "")
                    break

    logger.info(f"Rendered {len(rendered)} cards to {cards_dir}")
    return config
