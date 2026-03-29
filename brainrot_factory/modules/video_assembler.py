"""
Module 6 — Video Assembler
Composites all layers into a final 1080x1920 MP4 video.
Layers: background loop + card overlay + meme clips + BGM + SFX + karaoke captions.
Output: H.264, 30fps, 8-10 Mbps, AAC 192kbps
"""

import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from loguru import logger


def _make_brand_image(text: str, fontsize: int, opacity: float, output_path: str) -> tuple[int, int]:
    """
    Render brand watermark text as a transparent PNG using Pillow.
    Returns (width, height) of the generated image.
    """
    from PIL import Image, ImageDraw, ImageFont

    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    font = None
    for fc in font_candidates:
        if Path(fc).exists():
            try:
                font = ImageFont.truetype(fc, fontsize)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # Measure text size — textbbox offsets may be non-zero, account for them
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    # bbox = (left, top, right, bottom) — left/top can be negative
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad = 16
    w = text_w + pad * 2
    h = text_h + pad * 2

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw position: offset so bbox top-left lands at (pad, pad)
    draw_x = pad - bbox[0]
    draw_y = pad - bbox[1]

    alpha = int(opacity * 255)
    # Black border — fully opaque, 3px thick in all directions
    border = 3
    for dx in range(-border, border + 1):
        for dy in range(-border, border + 1):
            if dx != 0 or dy != 0:
                draw.text((draw_x + dx, draw_y + dy), text, font=font, fill=(0, 0, 0, 255))
    draw.text((draw_x, draw_y), text, font=font, fill=(255, 255, 255, alpha))

    img.save(output_path, "PNG")
    return w, h


def _check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _check_ass_filter() -> bool:
    """Check if the ass subtitle filter is available in this ffmpeg build."""
    try:
        result = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "ass":
                return True
        return False
    except Exception:
        return False


def _get_video_duration(path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", path
        ], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        for stream in data["streams"]:
            if stream.get("codec_type") == "video":
                return float(stream.get("duration", 0))
        return float(data["streams"][0].get("duration", 0))
    except Exception as e:
        logger.warning(f"Could not get duration for {path}: {e}")
        return 10.0


def _build_timeline(config: dict) -> list:
    """
    Build flat timeline of segments from config.
    Returns list of segment dicts with absolute start/end times.
    """
    timeline = []
    current_time = 0.0

    source = config["source"]

    # Intro: topic card + TTS (2.5s min)
    topic = source.get("topic", {})
    topic_duration = max(topic.get("audio_duration", 0) + 0.5, 2.5)

    timeline.append({
        "type": "topic",
        "start": current_time,
        "end": current_time + topic_duration,
        "card_path": topic.get("card_path", ""),
        "audio_path": topic.get("audio_path", ""),
        "duration": topic_duration
    })
    current_time += topic_duration

    # Comments
    for comment in source.get("comments", []):
        # Card slide-in + TTS
        comment_duration = max(comment.get("audio_duration", 0) + 0.5, 3.0)

        timeline.append({
            "type": "comment",
            "id": comment["id"],
            "start": current_time,
            "end": current_time + comment_duration,
            "card_path": comment.get("card_path", ""),
            "audio_path": comment.get("audio_path", ""),
            "duration": comment_duration
        })
        current_time += comment_duration

        # Meme segment — video clip OR static image
        meme_clip = comment.get("meme_clip", "")
        meme_image = comment.get("meme_image", "")
        meme_source_type = comment.get("meme_type", "video")

        if meme_source_type == "image" and meme_image and Path(meme_image).exists():
            meme_duration = 3.0  # static image shown for 3s
            timeline.append({
                "type": "meme",
                "start": current_time,
                "end": current_time + meme_duration,
                "meme_path": meme_image,
                "meme_source_type": "image",
                "sfx_path": comment.get("sfx", ""),
                "duration": meme_duration,
            })
            current_time += meme_duration
        elif meme_clip and Path(meme_clip).exists():
            meme_duration = _get_video_duration(meme_clip)
            if meme_duration > 0:
                timeline.append({
                    "type": "meme",
                    "start": current_time,
                    "end": current_time + meme_duration,
                    "meme_path": meme_clip,
                    "meme_source_type": "video",
                    "sfx_path": comment.get("sfx", ""),
                    "duration": meme_duration,
                })
                current_time += meme_duration

    # Outro: 3 seconds
    timeline.append({
        "type": "outro",
        "start": current_time,
        "end": current_time + 3.0,
        "duration": 3.0
    })
    current_time += 3.0

    return timeline, current_time  # timeline, total_duration


def _build_ffmpeg_command(config: dict, timeline: list, total_duration: float, output_path: str) -> list:
    """
    Build the FFmpeg command to assemble the full video.
    Uses filter_complex for compositing.
    """
    job_id = config["job_id"]
    background_file = config.get("background", {}).get("file", "")
    bgm_file = config.get("audio", {}).get("bgm", "")
    bgm_volume = config.get("audio", {}).get("bgm_volume", 0.12)
    captions_path = config.get("captions", {}).get("ass_path", "")

    cmd = ["ffmpeg", "-y"]

    # Input 0: background video (loop)
    if background_file and Path(background_file).exists():
        cmd += ["-stream_loop", "-1", "-i", background_file]
    else:
        # Black background as fallback
        cmd += [
            "-f", "lavfi",
            "-i", f"color=c=black:size=1080x1920:rate=30:duration={total_duration}"
        ]

    input_idx = 1

    # Collect all audio inputs
    audio_inputs = []
    filter_parts = []

    # Background: scale and crop to 1080x1920
    filter_parts.append(f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,trim=duration={total_duration}[bg]")
    current_video = "[bg]"

    # Brand watermark — DVD screensaver bounce, sits above bg but below all content layers
    brand_cfg = config.get("branding", {})
    brand_text = brand_cfg.get("text", "FSN")
    brand_opacity = brand_cfg.get("opacity", 0.30)
    brand_fontsize = brand_cfg.get("fontsize", 72)
    # Speed in px/s — different x/y speeds so they never sync (avoids corner lock)
    brand_speed_x = brand_cfg.get("speed_x", 130)
    brand_speed_y = brand_cfg.get("speed_y", 90)

    brand_png = str(Path(tempfile.mkdtemp()) / "brand_watermark.png")
    _make_brand_image(brand_text, brand_fontsize, brand_opacity, brand_png)

    cmd += ["-loop", "1", "-i", brand_png]
    brand_input = input_idx
    input_idx += 1

    # Bouncing overlay: triangular wave reflects text off all 4 edges
    filter_parts.append(
        f"[{brand_input}:v]scale=iw:ih,setsar=1[brand_img]"
    )
    filter_parts.append(
        f"{current_video}[brand_img]overlay="
        f"x='abs(mod(t*{brand_speed_x},2*(W-w))-(W-w))':"
        f"y='abs(mod(t*{brand_speed_y},2*(H-h))-(H-h))'"
        f"[bg_branded]"
    )
    current_video = "[bg_branded]"

    # Overlay cards
    for seg in timeline:
        if seg["type"] in ("topic", "comment") and seg.get("card_path") and Path(seg.get("card_path", "")).exists():
            cmd += ["-i", seg["card_path"]]
            card_input = input_idx
            input_idx += 1

            # Scale card to full video width, center vertically in upper half
            enable_expr = f"between(t,{seg['start']:.2f},{seg['end']:.2f})"
            prev_video = current_video
            scaled_label = f"[cs{card_input}]"
            out_label = f"[v{card_input}]"
            filter_parts.append(f"[{card_input}:v]scale=1080:-1{scaled_label}")
            filter_parts.append(
                f"{prev_video}{scaled_label}overlay=x=(W-w)/2:y=500:enable='{enable_expr}'{out_label}"
            )
            current_video = out_label

    # Pre-render meme clips/images to temp MP4 files
    meme_temp_files = {}
    for seg in timeline:
        if seg["type"] != "meme":
            continue
        meme_D = max(seg["duration"], 0.5)
        source_path = seg.get("meme_path", "")
        if not source_path or not Path(source_path).exists():
            continue
        key = (source_path, meme_D)
        if key not in meme_temp_files:
            tmp = Path(f"/tmp/meme_prerender_{abs(hash(key))}.mp4")
            if not tmp.exists():
                is_image = seg.get("meme_source_type", "video") == "image"
                if is_image:
                    # Static image → looped video (no audio stream)
                    pre = [
                        "ffmpeg", "-y",
                        "-loop", "1", "-t", str(meme_D), "-i", source_path,
                        "-vf", "scale=1080:-2,pad=1080:1920:0:(1920-ih)/2:black,setsar=1,fps=30,format=yuv420p",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                        "-an",
                        str(tmp)
                    ]
                else:
                    pre = [
                        "ffmpeg", "-y", "-t", str(meme_D), "-i", source_path,
                        "-vf", "scale=1080:-2,pad=1080:1920:0:(1920-ih)/2:black,setsar=1,fps=30,format=yuv420p",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                        "-c:a", "aac", "-ar", "48000",
                        str(tmp)
                    ]
                subprocess.run(pre, capture_output=True)
                logger.debug(f"Pre-rendered meme ({seg.get('meme_source_type','video')}): {source_path} → {tmp}")
            meme_temp_files[key] = tmp

    # Overlay memes — video memes include audio; image memes use SFX instead
    for seg in timeline:
        if seg["type"] != "meme":
            continue
        source_path = seg.get("meme_path", "")
        if not source_path or not Path(source_path).exists():
            continue
        meme_D = max(seg["duration"], 0.5)
        key = (source_path, meme_D)
        tmp = meme_temp_files.get(key)
        if not tmp:
            continue

        is_image = seg.get("meme_source_type", "video") == "image"
        cmd += ["-i", str(tmp)]
        meme_input = input_idx
        input_idx += 1

        meme_label = f"[mv{meme_input}]"
        enable_expr = f"between(t,{seg['start']:.2f},{seg['end']:.2f})"
        prev_video = current_video
        out_label = f"[vm{meme_input}]"

        filter_parts.append(
            f"[{meme_input}:v]setpts=PTS-STARTPTS+{seg['start']}/TB{meme_label}"
        )
        filter_parts.append(
            f"{prev_video}{meme_label}overlay=x=0:y=0:enable='{enable_expr}'{out_label}"
        )
        current_video = out_label

        if is_image:
            # Image meme: play SFX instead of video audio
            sfx_path = seg.get("sfx_path", "")
            if sfx_path and Path(sfx_path).exists():
                cmd += ["-i", sfx_path]
                sfx_input = input_idx
                input_idx += 1
                sfx_label = f"[sfxa{sfx_input}]"
                filter_parts.append(
                    f"[{sfx_input}:a]asetpts=PTS-STARTPTS,volume=1.0,"
                    f"adelay={int(seg['start']*1000)}|{int(seg['start']*1000)},"
                    f"apad=whole_dur={total_duration}{sfx_label}"
                )
                audio_inputs.append(sfx_label)
        else:
            # Video meme: use its own audio track
            meme_audio_label = f"[mema{meme_input}]"
            filter_parts.append(
                f"[{meme_input}:a]"
                f"asetpts=PTS-STARTPTS,"
                f"volume=0.8,"
                f"adelay={int(seg['start']*1000)}|{int(seg['start']*1000)},"
                f"apad=whole_dur={total_duration}"
                f"{meme_audio_label}"
            )
            audio_inputs.append(meme_audio_label)

    # Add BGM — use stream_loop on input for reliable looping
    if bgm_file and Path(bgm_file).exists():
        cmd += ["-stream_loop", "-1", "-i", bgm_file]
        bgm_idx = input_idx
        input_idx += 1
        filter_parts.append(
            f"[{bgm_idx}:a]atrim=duration={total_duration},asetpts=PTS-STARTPTS,volume={bgm_volume},afade=t=in:st=0:d=1.5,afade=t=out:st={total_duration-2}:d=2[bgm_out]"
        )
        audio_inputs.append("[bgm_out]")

    # Add TTS audio for each segment
    for seg in timeline:
        if seg.get("audio_path") and Path(seg.get("audio_path", "")).exists():
            cmd += ["-i", seg["audio_path"]]
            tts_idx = input_idx
            input_idx += 1
            label = f"[tts_{tts_idx}]"
            filter_parts.append(
                f"[{tts_idx}:a]adelay={int(seg['start']*1000)}|{int(seg['start']*1000)},apad=whole_dur={total_duration}{label}"
            )
            audio_inputs.append(label)


    # Mix all audio
    if audio_inputs:
        filter_parts.append(
            f"{''.join(audio_inputs)}amix=inputs={len(audio_inputs)}:duration=longest:normalize=0[audio_out]"
        )

    # Apply captions — only if ass filter is available in this ffmpeg build
    if captions_path and Path(captions_path).exists() and _check_ass_filter():
        abs_ass = str(Path(captions_path).resolve())
        # FFmpeg filter_complex requires escaping backslashes, colons, single quotes
        abs_ass_escaped = abs_ass.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        filter_parts.append(
            f"{current_video}ass='{abs_ass_escaped}'[v_final]"
        )
        current_video = "[v_final]"
    elif captions_path and Path(captions_path).exists():
        logger.warning("ass subtitle filter not available in this ffmpeg build — captions skipped")

    # Build filter_complex
    filter_complex = ";".join(filter_parts)
    cmd += ["-filter_complex", filter_complex]

    # Map outputs — filter_complex output labels keep their brackets for -map
    cmd += ["-map", current_video]
    if audio_inputs:
        cmd += ["-map", "[audio_out]"]
    else:
        cmd += ["-an"]

    # Encoding
    codec = os.getenv("FFMPEG_ENCODE_CODEC", "h264_videotoolbox")
    # Try hardware encoder, fallback to libx264
    cmd += [
        "-c:v", codec,
        "-b:v", "8M",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-t", str(total_duration),
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        output_path
    ]

    return cmd


def _fallback_assemble(config: dict, timeline: list, total_duration: float, output_path: str) -> bool:
    """
    Simpler FFmpeg assembly: concatenate audio files with black background.
    Used as fallback if main assembly fails.
    """
    logger.warning("Using fallback video assembly (black background, audio only)")

    # Collect audio segments
    tts_files = []
    for seg in timeline:
        if seg.get("audio_path") and Path(seg.get("audio_path", "")).exists():
            tts_files.append((seg["start"], seg["audio_path"]))

    if not tts_files:
        logger.warning("No audio files — assembling silent video fallback")
        # Build silent video only
        cmd_silent = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:size=1080x1920:rate=30:duration={total_duration}",
            "-c:v", "libx264", "-t", str(total_duration), "-movflags", "+faststart", output_path
        ]
        result = subprocess.run(cmd_silent, capture_output=True, text=True)
        return result.returncode == 0

    # Create silent base
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:size=1080x1920:rate=30:duration={total_duration}",
        "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:duration={total_duration}",
    ]

    filter_parts = ["[0:v]setsar=1[v]"]
    audio_inputs = ["[1:a]"]

    for i, (start, audio_path) in enumerate(tts_files):
        cmd += ["-i", audio_path]
        idx = i + 2
        label = f"[a{idx}]"
        filter_parts.append(
            f"[{idx}:a]adelay={int(start*1000)}|{int(start*1000)},apad=whole_dur={total_duration}{label}"
        )
        audio_inputs.append(label)

    filter_parts.append(
        f"{''.join(audio_inputs)}amix=inputs={len(audio_inputs)}:duration=longest:normalize=0[aout]"
    )

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[v]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(total_duration),
        "-movflags", "+faststart",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _pick_random_background(config: dict) -> str:
    """
    If no background file specified (or file missing), pick a random part
    from any subfolder inside assets/backgrounds/.
    """
    import random as _random
    bg_file = config.get("background", {}).get("file", "")
    if bg_file and Path(bg_file).exists():
        return bg_file

    bg_root = Path("assets/backgrounds")
    if not bg_root.exists():
        return ""

    all_parts = []
    for folder in bg_root.iterdir():
        if folder.is_dir():
            all_parts.extend(folder.glob("*.mp4"))

    if not all_parts:
        return ""

    chosen = str(_random.choice(all_parts))
    logger.info(f"Background: {chosen}")
    return chosen


def run(config: dict) -> dict:
    """
    Module 6 entry point.
    Assembles all components into the final video.
    """
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg not found. Install with: brew install ffmpeg")

    job_id = config["job_id"]
    output_path = config["video"]["output_path"]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Auto-pick background if not set or missing
    picked_bg = _pick_random_background(config)
    if picked_bg:
        config.setdefault("background", {})["file"] = picked_bg

    logger.info("Building video timeline...")
    timeline, total_duration = _build_timeline(config)
    config["timeline"] = timeline

    logger.info(f"Total video duration: {total_duration:.1f}s ({len(timeline)} segments)")
    logger.info(f"Output: {output_path}")

    # Build FFmpeg command
    cmd = _build_ffmpeg_command(config, timeline, total_duration, output_path)

    logger.info("Running FFmpeg...")
    logger.debug(f"FFmpeg cmd: {' '.join(cmd[:10])}...")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.warning(f"Primary FFmpeg failed, trying fallback...")
        logger.debug(f"FFmpeg stderr: {result.stderr[-2000:]}")

        # Try with libx264 instead of hardware encoder
        cmd_fallback = [c if c != "h264_videotoolbox" else "libx264" for c in cmd]
        result2 = subprocess.run(cmd_fallback, capture_output=True, text=True)

        if result2.returncode != 0:
            # Last resort: simple fallback
            success = _fallback_assemble(config, timeline, total_duration, output_path)
            if not success:
                raise RuntimeError(f"Video assembly failed. FFmpeg error: {result.stderr[-1000:]}")

    if Path(output_path).exists():
        size_mb = Path(output_path).stat().st_size / 1024 / 1024
        logger.info(f"Video assembled: {output_path} ({size_mb:.1f} MB, {total_duration:.1f}s)")
        config["output"] = {"path": output_path, "size_mb": round(size_mb, 1), "duration": round(total_duration, 1)}
    else:
        raise RuntimeError(f"Output file not created: {output_path}")

    return config
