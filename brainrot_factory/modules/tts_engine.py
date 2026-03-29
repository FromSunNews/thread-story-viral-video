"""
Module 3 — TTS Engine
Generates voiceover audio and word-level timestamps using edge-tts.
Outputs MP3 + SRT files to output/jobs/{job_id}/audio/
"""

import asyncio
import json
import os
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

from modules.text_normalizer import normalize as _ai_normalize, normalize_batch as _ai_normalize_batch


# Vietnamese internet slang → spoken form
# Order matters: longer/more specific patterns first
_VI_SLANG = {
    # --- Profanity euphemisms ---
    r'\bclm\b':     'cái lùm mía',
    r'\bđmm\b':     'đù má',
    r'\bđm\b':      'đù má',
    r'\bvkl\b':     'vãi kẹo lạc',
    r'\bvcl\b':     'vãi cả lúa',
    r'\bvl\b':      'vãi lúa',
    r'\bcc\b':      'cái con',
    r'\bcmn\b':     'cái mặt này',
    r'\bkí lùm\b':  'kí lùm',

    # --- Abbreviations (negation / affirmation) ---
    r'\bkp\b':      'không phải',
    r'\bkđ\b':      'không đúng',
    r'\bkb\b':      'không biết',
    r'\bkc\b':      'không có',
    r'\bkq\b':      'kết quả',
    r'\bkk\b':      'không không',
    r'\bkô\b':      'không',
    r'\bko\b':      'không',
    r'\bk\b':       'không',
    r'\bdc\b':      'được',
    r'\bdk\b':      'được',
    r'\bđc\b':      'được',
    r'\bđk\b':      'được',
    r'\br\b':       'rồi',
    r'\bnr\b':      'nhà rồi',
    r'\brr\b':      'rồi rồi',

    # --- Common chat abbreviations ---
    r'\bnma\b':     'nhưng mà',
    r'\bnhma\b':    'nhưng mà',
    r'\bmà\b':      'mà',
    r'\btrc\b':     'trước',
    r'\bsau\b':     'sau',
    r'\bbt\b':      'bình thường',
    r'\bbth\b':     'bình thường',
    r'\bbh\b':      'bây giờ',
    r'\bntn\b':     'như thế nào',
    r'\bnv\b':      'nhân vật',
    r'\bnn\b':      'nguyên nhân',
    r'\bhqua\b':    'hôm qua',
    r'\bhna\b':     'hôm nay',
    r'\bhn\b':      'hôm nay',
    r'\bms\b':      'mới',
    r'\bmk\b':      'mình',
    r'\bmh\b':      'mình',
    r'\bt\b':       'tôi',
    r'\ba\b':       'anh',
    r'\bc\b':       'chị',
    r'\be\b':       'em',
    r'\bu\b':       'ừ',
    r'\buh\b':      'ừ',
    r'\bb\b':       'bạn',
    r'\bmn\b':      'mọi người',
    r'\bcn\b':      'còn',
    r'\bcg\b':      'cũng',
    r'\bcx\b':      'cũng',
    r'\bcũng\b':    'cũng',
    r'\bck\b':      'chồng',
    r'\bvk\b':      'vợ',
    r'\bbff\b':     'bạn thân',
    r'\bfam\b':     'gia đình',

    # --- Expressions / reactions ---
    r'\bomg\b':     'ôi trời',
    r'\bwtf\b':     'ôi trời ơi',
    r'\blmao\b':    '',
    r'\blol\b':     '',
    r'\bhaha\b':    '',
    r'\bhuhu\b':    '',
    r'\bhihi\b':    '',
    r'\bloz\b':     '',
    r'\bxd\b':      '',
    r'\bok\b':      'ô kê',
    r'\bokay\b':    'ô kê',
    r'\byes\b':     'đúng rồi',
    r'\bnope\b':    'không',
    r'\bno\b':      'không',

    # --- Products / brands commonly abbreviated ---
    r'\bbvs\b':     'băng vệ sinh',
    r'\bshb\b':     'shop',
    r'\bsdt\b':     'số điện thoại',
    r'\bđt\b':      'điện thoại',
    r'\bpn\b':      'phụ nữ',
    r'\bgt\b':      'giới thiệu',
    r'\btt\b':      'thanh toán',
    r'\bck\b':      'chuyển khoản',
    r'\bđh\b':      'đơn hàng',
    r'\bsp\b':      'sản phẩm',
    r'\bvc\b':      'vận chuyển',
    r'\bgiao\b':    'giao',

    # --- Laugh / filler patterns (drop) ---
    r'={1,}[)>]{2,}': '',      # =))) =>>
    r':{1,}[)>]{2,}': '',      # :))) :>>
    r'\^{2,}':      '',
    r'heh+':        '',
    r'he+':         '',
    r'ha{3,}':      '',
    r'hi{3,}':      '',
    r'hu{3,}':      '',

    # --- Punctuation / typography ---
    r'~+':          '',        # trailing tildes
    r'!{2,}':       '!',       # multiple exclamation → one
    r'\?{2,}':      '?',
}


def _preprocess_text(text: str, lang: str = "vi") -> str:
    """Normalize text for TTS: strip emoji, expand slang, clean whitespace."""
    # Strip all unicode emoji/symbol characters
    text = re.sub(
        u"[\U0001F600-\U0001F64F"   # emoticons
        u"\U0001F300-\U0001F5FF"    # symbols & pictographs
        u"\U0001F680-\U0001F6FF"    # transport & map
        u"\U0001F700-\U0001F77F"    # alchemical
        u"\U0001F780-\U0001F7FF"    # geometric
        u"\U0001F800-\U0001F8FF"    # supplemental arrows
        u"\U0001F900-\U0001F9FF"    # supplemental symbols
        u"\U0001FA00-\U0001FA6F"    # chess symbols
        u"\U0001FA70-\U0001FAFF"    # symbols extended-A
        u"\U00002600-\U000026FF"    # misc symbols
        u"\U00002700-\U000027BF"    # dingbats
        u"\U0000FE00-\U0000FE0F"    # variation selectors
        u"\U0001F1E0-\U0001F1FF"    # flags
        u"]+",
        '', text, flags=re.UNICODE
    )
    text = unicodedata.normalize("NFC", text)

    # Expand Vietnamese internet slang (case-insensitive)
    if lang == "vi":
        for pattern, replacement in _VI_SLANG.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Remove markdown bold/italic markers
    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)

    # Ellipsis / multiple dots → comma pause (plain text, edge-tts handles naturally)
    text = re.sub(r'\.{3,}', ', ', text)
    text = text.replace("…", ', ')

    # Em-dash / mid-word dash used as pause → comma
    text = re.sub(r'\s*[–—]\s*', ', ', text)

    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _words_from_text(text: str) -> list:
    """Split text into word tokens (handles Vietnamese space-separated syllables)."""
    return [w for w in text.split() if w]


async def _generate_edge_tts(text: str, voice: str, output_mp3: Path, output_srt: Path, rate: str = "+0%") -> float:
    """
    Generate TTS audio + word-boundary SRT using edge-tts.
    Returns duration in seconds.
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")

    audio_data = bytearray()
    word_boundaries = []

    async for event in communicate.stream():
        if event["type"] == "audio":
            audio_data.extend(event["data"])
        elif event["type"] == "WordBoundary":
            word_boundaries.append({
                "word": event["text"],
                "offset": event["offset"],   # in 100-nanosecond units
                "duration": event["duration"]
            })

    # Write MP3
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    with open(output_mp3, "wb") as f:
        f.write(bytes(audio_data))

    # Convert offsets from 100ns units to seconds
    timestamps = []
    for wb in word_boundaries:
        start_s = wb["offset"] / 10_000_000
        dur_s = wb["duration"] / 10_000_000
        timestamps.append({
            "word": wb["word"],
            "start": round(start_s, 3),
            "end": round(start_s + dur_s, 3)
        })

    # Calculate total duration
    duration = timestamps[-1]["end"] if timestamps else 0.0
    # Add small buffer
    duration += 0.3

    # Write SRT
    _write_srt(timestamps, output_srt)

    return duration, timestamps


def _write_srt(timestamps: list, output_path: Path) -> None:
    """Write word-level SRT subtitle file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _fmt_time(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        ms = int((secs % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, ts in enumerate(timestamps, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_time(ts['start'])} --> {_fmt_time(ts['end'])}")
        lines.append(ts["word"])
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


async def _process_comments_async(config: dict) -> dict:
    """Process all comments asynchronously."""
    job_id = config["job_id"]
    source = config["source"]
    lang = source.get("lang", "vi")
    audio_cfg = config.get("audio", {})

    # Base voices: topic always uses female, comments alternate male/female
    VOICES_VI = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]  # Female, Male
    VOICES_EN = ["en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural", "en-US-EricNeural"]
    voice_topic = audio_cfg.get("voice_vi", "vi-VN-HoaiMyNeural") if lang == "vi" else audio_cfg.get("voice_en", VOICES_EN[0])
    tts_rate = audio_cfg.get("tts_rate", "+0%")

    audio_dir = Path(f"output/jobs/{job_id}/audio")
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: apply hardcoded slang dict FIRST so AI normalizer sees clean text
    def _expand_slang(text: str) -> str:
        for pattern, replacement in _VI_SLANG.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    if lang == "vi":
        if source.get("topic", {}).get("text"):
            source["topic"]["text"] = _expand_slang(source["topic"]["text"])
        for c in source.get("comments", []):
            c["text"] = _expand_slang(c.get("text", ""))

    # Step 2: AI batch normalize (context/grammar cleanup)
    if lang == "vi":
        logger.info("Normalizing texts (expand abbreviations, remove emoticons)...")
        all_texts = []
        if source.get("topic", {}).get("text"):
            all_texts.append(source["topic"]["text"])
        for c in source.get("comments", []):
            all_texts.append(c.get("text", ""))

        normalized = _ai_normalize_batch(all_texts)

        idx = 0
        if source.get("topic", {}).get("text"):
            source["topic"]["text"] = normalized[idx]; idx += 1
        for c in source.get("comments", []):
            c["text"] = normalized[idx]; idx += 1

    # Process topic
    topic = source.get("topic", {})
    if topic and topic.get("text"):
        text = _preprocess_text(topic["text"], lang)
        mp3_path = audio_dir / "topic.mp3"
        srt_path = audio_dir / "topic.srt"

        if mp3_path.exists():
            logger.debug("Skipping topic TTS (already exists)")
            # Load existing duration
            try:
                from mutagen.mp3 import MP3
                duration = MP3(mp3_path).info.length
            except:
                duration = len(text.split()) * 0.35
            config["source"]["topic"]["audio_path"] = str(mp3_path)
            config["source"]["topic"]["audio_duration"] = round(duration, 2)
        else:
            logger.info(f"TTS: topic ({len(text)} chars) voice={voice_topic}")
            for attempt in range(3):
                try:
                    duration, timestamps = await _generate_edge_tts(text, voice_topic, mp3_path, srt_path, rate=tts_rate)
                    config["source"]["topic"]["audio_path"] = str(mp3_path)
                    config["source"]["topic"]["audio_duration"] = round(duration, 2)
                    config["source"]["topic"]["timestamps"] = timestamps
                    break
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"TTS failed for topic after 3 attempts: {e}")
                        config["source"]["topic"]["audio_duration"] = 3.0
                    else:
                        await asyncio.sleep(2 ** attempt)

    # Process each comment — alternate voice per comment for variety
    voice_pool = VOICES_VI if lang == "vi" else VOICES_EN
    for comment_idx, comment in enumerate(source.get("comments", [])):
        cid = comment["id"]
        text = _preprocess_text(comment["text"], lang)
        mp3_path = audio_dir / f"{cid}.mp3"
        srt_path = audio_dir / f"{cid}.srt"

        # Pick voice: cycle through pool so each comment sounds different
        comment_voice = voice_pool[comment_idx % len(voice_pool)]

        if mp3_path.exists() and comment.get("audio_path"):
            logger.debug(f"Skipping TTS for {cid} (already exists)")
            continue

        logger.info(f"TTS: {cid} ({len(text)} chars) voice={comment_voice}")

        for attempt in range(3):
            try:
                duration, timestamps = await _generate_edge_tts(text, comment_voice, mp3_path, srt_path, rate=tts_rate)
                comment["audio_path"] = str(mp3_path)
                comment["audio_duration"] = round(duration, 2)
                comment["timestamps"] = timestamps
                logger.debug(f"  -> {cid}: {duration:.1f}s, {len(timestamps)} words")
                break
            except Exception as e:
                if attempt == 2:
                    logger.error(f"TTS failed for {cid} after 3 attempts: {e}")
                    comment["audio_duration"] = len(text.split()) * 0.35
                    comment["timestamps"] = []
                else:
                    logger.warning(f"TTS attempt {attempt+1} failed for {cid}: {e}")
                    await asyncio.sleep(2 ** attempt)

    return config


def run(config: dict) -> dict:
    """
    Module 3 entry point.
    Generates TTS audio and SRT timestamps for all comments.
    """
    logger.info("Starting TTS generation...")
    try:
        loop = asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
        config = loop.run_until_complete(_process_comments_async(config))
    except RuntimeError:
        config = asyncio.run(_process_comments_async(config))

    total = len(config["source"].get("comments", []))
    done = sum(1 for c in config["source"].get("comments", []) if c.get("audio_path"))
    logger.info(f"TTS complete: {done}/{total} comments")
    return config
