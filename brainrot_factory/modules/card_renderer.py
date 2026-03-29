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
    badge = comment.get("badge", "")  # e.g. "Author"

    # HTML: profanity gets blur-censored spans; rest is HTML-escaped
    text_escaped = _censor_text_html(text)
    author_display = author.lstrip("@")
    author_escaped = _html_escape(author_display)

    # Avatar size: topic gets 84px, comments get 66px (1.5x scale for readability)
    avatar_size = 84 if is_topic else 66

    # Avatar: real photo or dark gray circle with person silhouette (Threads default)
    silhouette_size = int(avatar_size * 0.62)
    if avatar_b64:
        avatar_img = f'<img src="{avatar_b64}" width="{avatar_size}" height="{avatar_size}" style="border-radius:50%;object-fit:cover;display:block;">'
    else:
        avatar_img = f'''<div style="
            width:{avatar_size}px;height:{avatar_size}px;border-radius:50%;
            background:#3A3A3A;
            display:flex;align-items:center;justify-content:center;
            overflow:hidden;flex-shrink:0;
        "><svg viewBox="0 0 24 24" width="{silhouette_size}" height="{silhouette_size}" fill="#888888">
            <circle cx="12" cy="8" r="3.5"/>
            <path d="M12 13.5c-5 0-8 2.5-8 5v1h16v-1c0-2.5-3-5-8-5z"/>
        </svg></div>'''

    # Comments: "+" follow button — WHITE bg, GRAY "+", BLACK border
    follow_dot = ""
    if not is_topic:
        follow_dot = '''<div style="
            position:absolute;bottom:-4px;right:-4px;
            width:33px;height:33px;border-radius:50%;
            background:#FFFFFF;border:3px solid #000000;
            display:flex;align-items:center;justify-content:center;
            font-size:20px;color:#666666;font-weight:300;line-height:1;
        ">+</div>'''

    avatar_html = f'''<div style="position:relative;width:{avatar_size}px;flex-shrink:0;">
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
            '<div style="margin-left:auto;padding-left:16px;flex-shrink:0;">'
            '<span style="font-size:36px;font-weight:600;color:#000000;background:#FFFFFF;'
            'padding:12px 33px;border-radius:33px;white-space:nowrap;display:inline-block;">Follow</span>'
            '</div>'
        )
    else:
        badge_html = f'<span style="color:#888888;font-weight:400;"> · {badge}</span>' if badge else ''
        username_suffix = f'<span style="{ts_style}">{timestamp}{badge_html}</span>'

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

    # Action icons — Threads-style, thin stroke, fully rounded/soft
    S = 'width="39" height="39" viewBox="0 0 24 24" fill="none" stroke="#888888" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"'

    # Heart: smooth outline heart
    heart_svg = f'''<svg {S}>
        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
    </svg>'''

    # Reply: smooth rounded oval bubble — single closed path
    reply_svg = f'''<svg {S}>
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
    </svg>'''

    # Repost: smooth curved cycle arrows (refresh-cw style — much softer than polylines)
    repost_svg = f'''<svg {S}>
        <path d="M23 4v6h-6"/>
        <path d="M1 20v-6h6"/>
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"/>
        <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14"/>
    </svg>'''

    # Share/Send: clean paper-plane outline
    share_svg = f'''<svg {S}>
        <line x1="22" y1="2" x2="11" y2="13"/>
        <polygon points="22 2 15 22 11 13 2 9 22 2"/>
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
    background: #000000;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  .card {{
    width: 1060px;
    padding: 33px 42px 27px 42px;
    background: #000000;
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

    # Fetch inline content images concurrently
    for item in items:
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
    if topic:
        topic_item = dict(topic)
        topic_item["id"] = "topic"
        topic_item["card_type"] = "topic"
        items.append(topic_item)

    for comment in source.get("comments", []):
        items.append(dict(comment))

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
