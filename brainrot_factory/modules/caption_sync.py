"""
Module 4 — Caption Sync
Generates ASS (Advanced SubStation Alpha) karaoke subtitles
synchronized with TTS audio timestamps.
Outputs .ass files to output/jobs/{job_id}/captions/
"""

import json
import math
from pathlib import Path

from loguru import logger


ASS_HEADER = """\
[Script Info]
Title: Brainrot Factory Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Be Vietnam Pro,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,50,1
Style: Highlight,Be Vietnam Pro,52,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _fmt_ass_time(seconds: float) -> str:
    """Format seconds to ASS timestamp: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _group_words_into_lines(timestamps: list, max_words: int = 5) -> list:
    """
    Group word timestamps into subtitle lines (max N words per line).
    Returns list of line groups, each with start/end time and words.
    """
    if not timestamps:
        return []

    lines = []
    current_line = []

    for ts in timestamps:
        current_line.append(ts)
        if len(current_line) >= max_words:
            lines.append(current_line)
            current_line = []

    if current_line:
        lines.append(current_line)

    return lines


def _build_karaoke_line(words: list, global_offset: float = 0.0) -> tuple:
    """
    Build a single ASS karaoke dialogue line.
    Returns (start_time, end_time, ass_text)

    Uses \\k tags: duration in centiseconds before that syllable highlights.
    """
    if not words:
        return 0, 0, ""

    start_time = words[0]["start"] + global_offset
    end_time = words[-1]["end"] + global_offset

    ass_parts = []
    for word in words:
        # Duration of this word in centiseconds
        dur_cs = int((word["end"] - word["start"]) * 100)
        dur_cs = max(dur_cs, 5)  # minimum 5cs
        ass_parts.append(f"{{\\k{dur_cs}}}{word['word']}")

    ass_text = " ".join(ass_parts)
    return start_time, end_time, ass_text


def _build_ass_for_segment(
    timestamps: list,
    start_offset: float,
    segment_id: str
) -> list:
    """
    Build ASS dialogue lines for one TTS segment (one comment).
    All word times are relative to segment start; add start_offset for global timeline.
    """
    if not timestamps:
        return []

    lines = _group_words_into_lines(timestamps, max_words=5)
    dialogue_lines = []

    for line_words in lines:
        t_start, t_end, ass_text = _build_karaoke_line(line_words, global_offset=start_offset)
        # Add small buffer after line end
        t_end = min(t_end + 0.1, t_end + 0.1)

        dialogue = (
            f"Dialogue: 0,{_fmt_ass_time(t_start)},{_fmt_ass_time(t_end)},"
            f"Default,,0,0,0,,{ass_text}"
        )
        dialogue_lines.append(dialogue)

    return dialogue_lines


def _build_full_ass(config: dict) -> tuple:
    """
    Build complete ASS file from the full video timeline.
    Returns (ass_content: str, srt_path: str)
    """
    source = config["source"]
    job_id = config["job_id"]

    # Build timeline offsets: each segment starts after previous ends
    # Intro: 2.5s, then comments, then 3s outro
    current_time = 2.5  # skip intro

    all_dialogues = []

    # Topic segment
    topic = source.get("topic", {})
    if topic.get("timestamps") and topic.get("audio_duration"):
        segs = _build_ass_for_segment(
            topic["timestamps"],
            start_offset=current_time,
            segment_id="topic"
        )
        all_dialogues.extend(segs)
        current_time += topic["audio_duration"]

    for comment in source.get("comments", []):
        if not comment.get("timestamps"):
            current_time += comment.get("audio_duration", 4.0)
            current_time += 2.5  # meme clip gap
            continue

        segs = _build_ass_for_segment(
            comment["timestamps"],
            start_offset=current_time,
            segment_id=comment["id"]
        )
        all_dialogues.extend(segs)

        current_time += comment.get("audio_duration", 4.0)
        current_time += 2.5  # meme clip

    ass_content = ASS_HEADER + "\n".join(all_dialogues) + "\n"
    return ass_content


def run(config: dict) -> dict:
    """
    Module 4 entry point.
    Builds ASS karaoke subtitle file for the full video.
    """
    job_id = config["job_id"]
    captions_dir = Path(f"output/jobs/{job_id}/captions")
    captions_dir.mkdir(parents=True, exist_ok=True)

    ass_path = captions_dir / "captions.ass"

    logger.info("Building karaoke captions...")
    ass_content = _build_full_ass(config)

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    # Count dialogue lines
    n_lines = ass_content.count("\nDialogue:")
    logger.info(f"Caption file written: {ass_path} ({n_lines} dialogue lines)")

    config["captions"] = {"ass_path": str(ass_path)}
    return config
