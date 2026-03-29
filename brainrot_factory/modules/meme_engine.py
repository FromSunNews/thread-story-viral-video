"""
Module 5 — Meme/SFX Engine
Analyzes comment sentiment, selects matching meme clips + SFX.
Tracks usage in SQLite to prevent repetition within 5 videos.
"""

import json
import os
import random
import sqlite3
from pathlib import Path

from loguru import logger


EMOTION_SFX = {}  # populated dynamically by _scan_sfx_library


def _init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize or open the meme index SQLite database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            emotion TEXT NOT NULL,
            meme_type TEXT NOT NULL DEFAULT 'video',
            usage_count INTEGER DEFAULT 0,
            last_used_job TEXT DEFAULT NULL
        )
    """)
    # Add meme_type column if upgrading from old schema
    try:
        conn.execute("ALTER TABLE memes ADD COLUMN meme_type TEXT NOT NULL DEFAULT 'video'")
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            meme_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def _scan_meme_library(conn: sqlite3.Connection, assets_dir: Path) -> None:
    """Scan assets/memes/ (video) and assets/memes_img/ (image) folders."""
    # Video memes
    memes_dir = assets_dir / "memes"
    if not memes_dir.exists():
        return

    for emotion_dir in memes_dir.iterdir():
        if not emotion_dir.is_dir():
            continue
        emotion = emotion_dir.name
        for clip in emotion_dir.glob("*.mp4"):
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO memes (path, emotion, meme_type) VALUES (?, ?, 'video')",
                    (str(clip), emotion)
                )
            except:
                pass

    # Image memes (jpg/png/gif/webp)
    img_dir = assets_dir / "memes_img"
    if img_dir.exists():
        for emotion_dir in img_dir.iterdir():
            if not emotion_dir.is_dir():
                continue
            emotion = emotion_dir.name
            for img in emotion_dir.glob("*"):
                if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO memes (path, emotion, meme_type) VALUES (?, ?, 'image')",
                            (str(img), emotion)
                        )
                    except:
                        pass

    conn.commit()


def _analyze_sentiment_simple(text: str) -> tuple:
    """
    Simple rule-based sentiment analysis (no GPU required).
    Returns (sentiment: 'POS'|'NEG'|'NEU', emotion: str)
    """
    text_lower = text.lower()

    # Positive indicators
    pos_words = ["great", "amazing", "love", "happy", "wonderful", "excellent", "good", "nice",
                 "tốt", "hay", "vui", "thích", "tuyệt", "giỏi", "đẹp", "ngon", "xịn"]
    neg_words = ["bad", "terrible", "hate", "awful", "horrible", "worst", "sad", "angry",
                 "tệ", "xấu", "buồn", "tức", "ghét", "chán", "dở", "khó chịu"]
    surprise_words = ["wow", "omg", "surprised", "shocking", "unexpected", "unbelievable",
                      "trời", "ôi", "ngạc nhiên", "bất ngờ", "choáng", "sốc"]

    pos_score = sum(1 for w in pos_words if w in text_lower)
    neg_score = sum(1 for w in neg_words if w in text_lower)
    surprise_score = sum(1 for w in surprise_words if w in text_lower)

    if surprise_score >= 1:
        return "POS", "surprise"
    elif pos_score > neg_score:
        if pos_score >= 2:
            return "POS", "joy"
        return "POS", "joy"
    elif neg_score > pos_score:
        if any(w in text_lower for w in ["hate", "ghét", "tức", "angry"]):
            return "NEG", "anger"
        if any(w in text_lower for w in ["sad", "cry", "buồn", "khóc"]):
            return "NEG", "sadness"
        return "NEG", "disgust"

    return "NEU", "neutral"


def _analyze_sentiment_transformers(text: str) -> tuple:
    """
    HuggingFace-based sentiment analysis (better accuracy, requires torch).
    Falls back to simple if torch unavailable.
    """
    try:
        from transformers import pipeline
        # Use a small multilingual model
        classifier = pipeline(
            "text-classification",
            model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
            max_length=128,
            truncation=True
        )
        result = classifier(text[:512])[0]
        label = result["label"].upper()

        if "POS" in label or "POSITIVE" in label:
            sentiment = "POS"
        elif "NEG" in label or "NEGATIVE" in label:
            sentiment = "NEG"
        else:
            sentiment = "NEU"

        # Transformer gives broad sentiment — refine emotion with keyword analysis
        _, emotion = _analyze_sentiment_simple(text)

        # If simple returned neutral but transformer is confident POS/NEG, override
        if emotion == "neutral":
            if sentiment == "POS":
                emotion = "joy"
            elif sentiment == "NEG":
                emotion = "disgust"

        return sentiment, emotion
    except Exception as e:
        logger.debug(f"Transformers sentiment failed, using simple: {e}")
        return _analyze_sentiment_simple(text)


def _select_meme(conn: sqlite3.Connection, emotion: str, job_id: str,
                 cooldown: int = 5, used_in_job: set = None,
                 meme_type: str = None) -> tuple:
    """
    Select a meme for the given emotion that hasn't been used recently.
    meme_type: 'video' | 'image' | None (any)
    Returns (path, meme_type) or ("", "video") if none available.
    """
    if used_in_job is None:
        used_in_job = set()

    recent = conn.execute(
        "SELECT meme_path FROM job_history ORDER BY created_at DESC LIMIT ?",
        (cooldown * 10,)
    ).fetchall()
    recent_paths = {r[0] for r in recent} | used_in_job

    FALLBACK_EMOTIONS = {
        "joy":      ["surprise", "neutral"],
        "surprise": ["joy", "neutral"],
        "anger":    ["disgust", "fear", "neutral"],
        "disgust":  ["anger", "neutral"],
        "fear":     ["surprise", "neutral"],
        "sadness":  ["neutral", "disgust"],
        "neutral":  ["joy", "surprise"],
    }

    emotions_to_try = [emotion] + FALLBACK_EMOTIONS.get(emotion, []) + ["neutral"]
    type_filter = "AND meme_type = ?" if meme_type else ""

    for try_emotion in emotions_to_try:
        params = [try_emotion]
        if meme_type:
            params.append(meme_type)
        if recent_paths:
            rows = conn.execute(
                f"SELECT path, meme_type FROM memes WHERE emotion = ? {type_filter} AND path NOT IN ({','.join('?' * len(recent_paths))})",
                params + list(recent_paths)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT path, meme_type FROM memes WHERE emotion = ? {type_filter}",
                params
            ).fetchall()
        if rows:
            chosen_path, chosen_type = random.choice(rows)
            break
    else:
        params = list(used_in_job)
        if meme_type:
            type_clause = f"AND meme_type = '{meme_type}'"
        else:
            type_clause = ""
        rows = conn.execute(
            f"SELECT path, meme_type FROM memes WHERE 1=1 {type_clause}"
            + (f" AND path NOT IN ({','.join('?' * len(used_in_job))})" if used_in_job else "")
            + " ORDER BY usage_count ASC LIMIT 10",
            params
        ).fetchall()
        if not rows:
            return "", "video"
        chosen_path, chosen_type = random.choice(rows)

    conn.execute(
        "UPDATE memes SET usage_count = usage_count + 1, last_used_job = ? WHERE path = ?",
        (job_id, chosen_path)
    )
    conn.execute(
        "INSERT INTO job_history (job_id, meme_path) VALUES (?, ?)",
        (job_id, chosen_path)
    )
    conn.commit()

    return chosen_path, chosen_type


def _scan_sfx_library(assets_dir: Path) -> None:
    """Scan assets/sfx/{emotion}/ folders and populate EMOTION_SFX."""
    sfx_dir = assets_dir / "sfx"
    if not sfx_dir.exists():
        return
    audio_exts = {".mp3", ".wav", ".ogg", ".m4a"}
    for emotion_dir in sfx_dir.iterdir():
        if emotion_dir.is_dir():
            files = [str(f) for f in emotion_dir.iterdir() if f.suffix.lower() in audio_exts]
            if files:
                EMOTION_SFX[emotion_dir.name] = files
    # Also support flat assets/sfx/*.mp3 (legacy)
    flat = [str(f) for f in sfx_dir.iterdir() if f.is_file() and f.suffix.lower() in audio_exts]
    if flat:
        EMOTION_SFX.setdefault("neutral", []).extend(flat)


def _select_sfx(emotion: str) -> str:
    """Randomly select a SFX for the given emotion. Falls back to neutral."""
    FALLBACK = ["surprise", "joy", "neutral"]
    for em in [emotion] + FALLBACK:
        candidates = EMOTION_SFX.get(em, [])
        existing = [p for p in candidates if Path(p).exists()]
        if existing:
            return random.choice(existing)
    return ""


def run(config: dict) -> dict:
    """
    Module 5 entry point.
    Analyzes sentiment and assigns meme clips + SFX to each comment.
    """
    job_id = config["job_id"]
    db_path = Path("data/meme_index.db")

    conn = _init_db(db_path)
    _scan_meme_library(conn, Path("assets"))
    _scan_sfx_library(Path("assets"))

    use_transformers = os.getenv("USE_TRANSFORMERS_SENTIMENT", "false").lower() == "true"

    logger.info("Analyzing sentiment and selecting memes...")

    # Load original emotions from manual_input.json (if available) to avoid stale pipeline values
    original_emotions: dict = {}
    manual_path = config.get("source", {}).get("manual_json_path")
    if manual_path and Path(manual_path).exists():
        try:
            import json as _json
            with open(manual_path, encoding="utf-8") as _f:
                _orig = _json.load(_f)
            for _c in _orig.get("comments", []):
                if _c.get("emotion"):
                    original_emotions[_c["id"]] = _c["emotion"]
            logger.debug(f"Loaded original emotions for {len(original_emotions)} comments from manual input")
        except Exception as e:
            logger.debug(f"Could not load original emotions: {e}")

    used_in_job: set = set()

    for comment in config["source"].get("comments", []):
        text = comment.get("text", "")
        cid = comment.get("id", "")

        # Prefer original manual emotion > pipeline emotion > sentiment analysis
        preset_emotion = original_emotions.get(cid) or None

        # Use pre-set emotion from input JSON if available; otherwise run sentiment analysis
        if preset_emotion:
            emotion = preset_emotion
            sentiment = "POS" if emotion in ("joy", "surprise") else ("NEG" if emotion in ("anger", "disgust", "sadness", "fear") else "NEU")
            logger.debug(f"  {cid}: using pre-set emotion={emotion}")
        elif use_transformers:
            sentiment, emotion = _analyze_sentiment_transformers(text)
        else:
            sentiment, emotion = _analyze_sentiment_simple(text)

        comment["sentiment"] = sentiment
        comment["emotion"] = emotion

        # Randomly choose video meme or image meme (50/50 when both types exist)
        has_video = conn.execute("SELECT 1 FROM memes WHERE meme_type='video' LIMIT 1").fetchone()
        has_image = conn.execute("SELECT 1 FROM memes WHERE meme_type='image' LIMIT 1").fetchone()

        if has_video and has_image:
            # 75% video, 25% image
            chosen_type = random.choices(["video", "image"], weights=[75, 25])[0]
        elif has_image:
            chosen_type = "image"
        else:
            chosen_type = "video"

        meme_path, meme_type = _select_meme(conn, emotion, job_id,
                                            used_in_job=used_in_job,
                                            meme_type=chosen_type)
        if meme_path:
            used_in_job.add(meme_path)

        comment["meme_type"] = meme_type   # 'video' | 'image'
        if meme_type == "image":
            comment["meme_clip"] = ""
            comment["meme_image"] = meme_path
        else:
            comment["meme_clip"] = meme_path
            comment["meme_image"] = ""

        # Select SFX (used for both types — image meme plays sfx instead of video audio)
        sfx_path = _select_sfx(emotion)
        comment["sfx"] = sfx_path

        logger.debug(f"  {comment['id']}: {sentiment}/{emotion} → [{meme_type}] {Path(meme_path).name if meme_path else 'none'}")

    conn.close()

    assigned = sum(1 for c in config["source"]["comments"] if c.get("emotion"))
    logger.info(f"Meme/SFX assigned to {assigned} comments")
    return config
