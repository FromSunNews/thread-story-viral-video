"""
Module 1 — Content Scraper
Fetches posts and comments from Reddit, Threads, or manual JSON input.
Outputs normalized raw_content.json to output/jobs/{job_id}/
"""

import asyncio
import json
import re
import time
import unicodedata
from pathlib import Path

from loguru import logger


def _normalize_likes(n) -> str:
    """Convert number to display string: 1200 -> '1.2K', 1500000 -> '1.5M'"""
    if n is None:
        return "0"
    try:
        n = int(n)
    except (ValueError, TypeError):
        return str(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _normalize_text(text: str) -> str:
    """Normalize Unicode to NFC, strip HTML entities."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    # Remove HTML entities
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#x27;', "'", text)
    text = re.sub(r'<[^>]+>', '', text)  # strip remaining HTML tags
    return text.strip()


def _fetch_reddit_praw(url_or_subreddit: str, topic_keyword: str, max_comments: int) -> dict:
    """Fetch from Reddit using PRAW."""
    import praw
    import os

    client_id = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        logger.warning("No Reddit API credentials, falling back to .json endpoint")
        return _fetch_reddit_json(url_or_subreddit, max_comments)

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="brainrot_factory/1.0"
    )

    if url_or_subreddit.startswith("http"):
        submission = reddit.submission(url=url_or_subreddit)
    else:
        # Subreddit search
        subreddit = reddit.subreddit(url_or_subreddit)
        results = list(subreddit.search(topic_keyword, sort="top", limit=5)) if topic_keyword else list(subreddit.hot(limit=5))
        if not results:
            raise ValueError(f"No posts found in r/{url_or_subreddit}")
        submission = results[0]

    submission.comments.replace_more(limit=0)

    topic = {
        "text": _normalize_text(submission.title),
        "author": f"u/{submission.author.name if submission.author else 'deleted'}",
        "likes": _normalize_likes(submission.score),
        "card_type": "topic"
    }

    comments = []
    for i, comment in enumerate(submission.comments.list()[:max_comments * 2]):
        text = _normalize_text(comment.body)
        if len(text) < 30 or text in ("[deleted]", "[removed]"):
            continue
        comments.append({
            "id": f"c{i+1:03d}",
            "author": f"u/{comment.author.name if comment.author else 'anon'}",
            "text": text,
            "likes": _normalize_likes(comment.score),
            "sentiment": None,
            "emotion": None
        })
        if len(comments) >= max_comments:
            break

    return {"topic": topic, "comments": comments, "url": getattr(submission, 'url', '')}


def _fetch_reddit_json(url: str, max_comments: int) -> dict:
    """Fallback: fetch Reddit via public .json API (no auth)."""
    import requests

    if not url.startswith("http"):
        raise ValueError("Need a full Reddit URL for .json fallback")

    json_url = url.rstrip("/") + ".json?limit=25"
    headers = {"User-Agent": "brainrot_factory/1.0"}

    for attempt in range(3):
        try:
            resp = requests.get(json_url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    post_data = data[0]["data"]["children"][0]["data"]
    comments_data = data[1]["data"]["children"]

    topic = {
        "text": _normalize_text(post_data["title"]),
        "author": f"u/{post_data.get('author', 'deleted')}",
        "likes": _normalize_likes(post_data.get("score", 0)),
        "card_type": "topic"
    }

    comments = []
    for i, c in enumerate(comments_data):
        if c["kind"] != "t1":
            continue
        text = _normalize_text(c["data"].get("body", ""))
        if len(text) < 30:
            continue
        comments.append({
            "id": f"c{i+1:03d}",
            "author": f"u/{c['data'].get('author', 'anon')}",
            "text": text,
            "likes": _normalize_likes(c["data"].get("score", 0)),
            "sentiment": None,
            "emotion": None
        })
        if len(comments) >= max_comments:
            break

    return {"topic": topic, "comments": comments, "url": url}


def _fetch_threads_subprocess(url: str, max_comments: int) -> dict:
    """
    Run Playwright in an isolated subprocess to avoid asyncio/PyTorch state pollution.
    The worker script prints JSON to stdout; we parse and return it.
    """
    import subprocess
    import sys

    worker = Path(__file__).parent.parent / "scripts" / "threads_scraper_worker.py"
    cmd = [sys.executable, str(worker), url, str(max_comments)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            logger.warning(f"Worker stderr: {proc.stderr[-800:]}")
        stdout = proc.stdout.strip()
        if not stdout:
            raise ValueError(f"Worker produced no output. stderr: {proc.stderr[-300:]}")
        result = json.loads(stdout)
        if "error" in result:
            raise ValueError(result["error"])
        return result
    except subprocess.TimeoutExpired:
        raise ValueError("Playwright worker timed out after 120s")


def _load_manual_json(json_path: str) -> dict:
    """Load and validate manual JSON input."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # Validate/normalize
    topic = data.get("topic", {})
    if "text" not in topic:
        topic["text"] = data.get("title", "Untitled")
    if "author" not in topic:
        topic["author"] = "@manual"
    if "likes" not in topic:
        topic["likes"] = "0"
    topic["card_type"] = "topic"

    comments = []
    for i, c in enumerate(data.get("comments", [])):
        text = _normalize_text(c.get("text", c.get("body", "")))
        if len(text) < 5:
            continue
        comments.append({
            "id": c.get("id", f"c{i+1:03d}"),
            "author": c.get("author", f"@user_{i+1}"),
            "text": text,
            "likes": str(c.get("likes", "0")),
            "replies": str(c.get("replies", "")),
            "reposts": str(c.get("reposts", "")),
            "shares": str(c.get("shares", "")),
            "timestamp": c.get("timestamp", ""),
            "badge": c.get("badge", ""),
            "liked_by": c.get("liked_by", ""),
            "sentiment": c.get("sentiment"),
            "emotion": c.get("emotion"),
        })

    # Also pass extra fields on topic
    topic.setdefault("replies", str(data.get("topic", {}).get("replies", "")))
    topic.setdefault("reposts", str(data.get("topic", {}).get("reposts", "")))
    topic.setdefault("shares", str(data.get("topic", {}).get("shares", "")))
    topic.setdefault("timestamp", data.get("topic", {}).get("timestamp", ""))

    return {
        "topic": topic,
        "comments": comments,
        "url": data.get("url", "")
    }


def run(config: dict) -> dict:
    """
    Module 1 entry point.
    Reads config["source"] to determine platform and fetch method.
    Returns updated config with source.topic and source.comments populated.
    """
    import os
    job_id = config["job_id"]
    source = config["source"]
    platform = source.get("platform", "manual")
    max_comments = int(os.getenv("MAX_COMMENTS", "5"))

    job_dir = Path(f"output/jobs/{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)
    cache_path = job_dir / "raw_content.json"

    # Check cache
    if cache_path.exists() and source.get("comments"):
        logger.info(f"Using cached content: {cache_path}")
        with open(cache_path) as f:
            cached = json.load(f)
        config["source"]["topic"] = cached["topic"]
        config["source"]["comments"] = cached["comments"]
        return config

    logger.info(f"Scraping platform: {platform}")

    if platform == "manual":
        manual_path = source.get("manual_json_path", "")
        if not manual_path:
            raise ValueError("manual_json_path required for manual platform")
        result = _load_manual_json(manual_path)

    elif platform == "reddit":
        url = source.get("url", "")
        subreddit = source.get("subreddit", "")
        keyword = source.get("topic_keyword", "")
        target = url if url else subreddit
        if not target:
            raise ValueError("url or subreddit required for reddit platform")
        result = _fetch_reddit_praw(target, keyword, max_comments)

    elif platform == "threads":
        url = source.get("url", "")
        if not url:
            raise ValueError("url required for threads platform")
        result = _fetch_threads_subprocess(url, max_comments)

    else:
        raise ValueError(f"Unknown platform: {platform}")

    # Update config
    config["source"]["topic"] = result["topic"]
    config["source"]["comments"] = result["comments"]
    if result.get("url"):
        config["source"]["url"] = result["url"]

    # Re-index comment IDs
    for i, c in enumerate(config["source"]["comments"]):
        c["id"] = f"c{i+1:03d}"

    # Cache result
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({
            "topic": result["topic"],
            "comments": config["source"]["comments"],
            "url": config["source"].get("url", "")
        }, f, indent=2, ensure_ascii=False)

    logger.info(f"Scraped {len(config['source']['comments'])} comments")
    return config
