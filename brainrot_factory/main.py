"""
Brainrot Video Factory — CLI Orchestrator
Usage:
  python main.py --url <url> --platform reddit|threads|manual --job-id <id> --lang vi|en
  python main.py --topic <keyword> --subreddit <name> --lang vi|en
  python main.py --manual <json_path> --lang vi|en
"""

import argparse
import json
import sys
import traceback
import uuid
from pathlib import Path
from datetime import datetime

from loguru import logger

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(job_id: str, logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"{job_id}.log"
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
    logger.add(str(log_file), level="DEBUG", rotation="10 MB",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")
    logger.info(f"Logging to {log_file}")


# ---------------------------------------------------------------------------
# video_config.json helpers
# ---------------------------------------------------------------------------

PIPELINE_MODULES = [
    "scraper",
    "card_renderer",
    "tts_engine",
    "caption_sync",
    "meme_engine",
    "video_assembler",
]


def load_video_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_video_config(config_path: Path, video_config: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(video_config, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Module runner
# ---------------------------------------------------------------------------

def run_module(module_name: str, video_config: dict) -> dict:
    """Dynamically import and run a pipeline module."""
    import importlib
    mod = importlib.import_module(f"modules.{module_name}")
    result = mod.run(video_config)
    if result is None:
        result = {}
    return result


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Brainrot Video Factory — generate viral short-form videos from social media threads",
    )

    # Source selection
    source_group = parser.add_argument_group("Source")
    source_group.add_argument("--url", type=str, default=None,
                              help="Direct URL of a Reddit post or Threads post")
    source_group.add_argument("--platform", choices=["reddit", "threads", "manual"],
                              default=None, help="Source platform")
    source_group.add_argument("--topic", type=str, default=None,
                              help="Keyword/topic for Reddit discovery mode")
    source_group.add_argument("--subreddit", type=str, default=None,
                              help="Subreddit name for Reddit discovery mode (e.g. 'AmItheAsshole')")
    source_group.add_argument("--manual", type=str, default=None,
                              help="Path to a manual JSON input file")

    # Job metadata
    job_group = parser.add_argument_group("Job")
    job_group.add_argument("--job-id", type=str, default=None,
                           help="Unique job identifier (auto-generated if omitted)")
    job_group.add_argument("--lang", choices=["vi", "en"], default="en",
                           help="Output language for TTS and captions (default: en)")
    job_group.add_argument("--background", type=str, default=None,
                           help="Path to background video file (MP4)")
    job_group.add_argument("--bgm", type=str, default=None,
                           help="Path to background music file (MP3/WAV)")
    job_group.add_argument("--tts-rate", type=str, default=None,
                           help="TTS speech rate, e.g. '+50%%' for 1.5x, '-20%%' for 0.8x")

    # Pipeline control
    pipeline_group = parser.add_argument_group("Pipeline")
    pipeline_group.add_argument("--resume", action="store_true",
                                help="Skip modules that already completed successfully")
    pipeline_group.add_argument("--only", type=str, default=None,
                                help="Run only this single module (comma-separated list allowed)")

    return parser


def validate_args(args: argparse.Namespace) -> None:
    """Validate argument combinations and raise SystemExit on error."""
    modes = [
        args.url is not None,
        args.topic is not None or args.subreddit is not None,
        args.manual is not None,
    ]
    if sum(modes) > 1:
        logger.error("Specify only one of --url, --topic/--subreddit, or --manual")
        sys.exit(1)
    if args.url and args.platform is None:
        logger.error("--url requires --platform (reddit|threads|manual)")
        sys.exit(1)
    if args.manual and not Path(args.manual).exists():
        logger.error(f"Manual JSON file not found: {args.manual}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    # Resolve job_id
    job_id = args.job_id or f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # Import config (after arg parse so errors surface cleanly)
    try:
        import config as cfg
    except Exception as exc:
        print(f"[FATAL] Failed to import config: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(job_id, cfg.LOGS_DIR)
    logger.info(f"=== Brainrot Video Factory | job_id={job_id} | lang={args.lang} ===")
    logger.info(f"Device: {cfg.DEVICE} | TTS: {cfg.TTS_PROVIDER}")

    # Job output directory
    job_dir: Path = cfg.OUTPUT_DIR / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    config_path: Path = job_dir / "video_config.json"

    # Build initial video_config from CLI args + project config
    video_config = load_video_config(config_path)

    # Seed/override top-level metadata from CLI
    video_config.setdefault("job_id", job_id)
    video_config.setdefault("lang", args.lang)
    video_config.setdefault("job_dir", str(job_dir))
    video_config.setdefault("completed_modules", [])

    if args.url:
        video_config.setdefault("source", {}).update({
            "platform": args.platform,
            "url": args.url,
        })
    if args.topic:
        video_config.setdefault("source", {})["topic_keyword"] = args.topic
    if args.subreddit:
        video_config.setdefault("source", {}).update({
            "platform": "reddit",
            "subreddit": args.subreddit,
        })
    if args.manual:
        video_config.setdefault("source", {}).update({
            "platform": "manual",
            "manual_json_path": args.manual,
        })
    if args.background:
        video_config.setdefault("background", {})["file"] = args.background
    if args.bgm:
        video_config.setdefault("audio", {})["bgm"] = args.bgm
    if args.tts_rate:
        video_config.setdefault("audio", {})["tts_rate"] = args.tts_rate
    # Always inject bgm_volume from config so video_assembler reads correct value
    video_config.setdefault("audio", {}).setdefault("bgm_volume", cfg.BGM_VOLUME)

    # Ensure video output path is always set
    video_config.setdefault("video", {}).setdefault(
        "output_path", str(job_dir / "final_video.mp4")
    )

    # Inject project-level config values that modules may need
    video_config["cfg"] = {
        "device": cfg.DEVICE,
        "video_width": cfg.VIDEO_WIDTH,
        "video_height": cfg.VIDEO_HEIGHT,
        "video_fps": cfg.VIDEO_FPS,
        "video_bitrate": cfg.VIDEO_BITRATE,
        "tts_provider": cfg.TTS_PROVIDER,
        "voice_vi": cfg.VOICE_VI,
        "voice_en": cfg.VOICE_EN,
        "bgm_volume": cfg.BGM_VOLUME,
        "sfx_volume": cfg.SFX_VOLUME,
        "max_comments": cfg.MAX_COMMENTS,
        "min_comment_length": cfg.MIN_COMMENT_LENGTH,
        "whisper_device": cfg.WHISPER_DEVICE,
        "whisper_model_size": cfg.WHISPER_MODEL_SIZE,
        "meme_cooldown_videos": cfg.MEME_COOLDOWN_VIDEOS,
        "assets_dir": str(cfg.ASSETS_DIR),
        "output_dir": str(cfg.OUTPUT_DIR),
        "ffmpeg_encode_codec": cfg.FFMPEG_ENCODE_CODEC,
        "ffmpeg_encode_quality": cfg.FFMPEG_ENCODE_QUALITY,
    }

    save_video_config(config_path, video_config)

    # Determine which modules to run
    if args.only:
        modules_to_run = [m.strip() for m in args.only.split(",")]
        invalid = [m for m in modules_to_run if m not in PIPELINE_MODULES]
        if invalid:
            logger.error(f"Unknown module(s): {invalid}. Valid: {PIPELINE_MODULES}")
            sys.exit(1)
    else:
        modules_to_run = PIPELINE_MODULES

    completed = set(video_config.get("completed_modules", []))

    # ---------------------------------------------------------------------------
    # Pipeline execution
    # ---------------------------------------------------------------------------
    logger.info(f"Pipeline: {' -> '.join(modules_to_run)}")

    for module_name in modules_to_run:
        if args.resume and module_name in completed:
            logger.info(f"[SKIP] {module_name} (already completed)")
            continue

        logger.info(f"[RUN ] {module_name} ...")
        try:
            result = run_module(module_name, video_config)
        except ModuleNotFoundError as exc:
            logger.warning(f"[WARN] Module '{module_name}' not yet implemented: {exc}")
            result = {}
        except Exception as exc:
            logger.error(f"[FAIL] {module_name} raised an error: {exc}")
            logger.debug(traceback.format_exc())
            save_video_config(config_path, video_config)
            sys.exit(1)

        # Merge result back into video_config
        if isinstance(result, dict):
            video_config.update(result)

        # Mark module as completed
        completed.add(module_name)
        video_config["completed_modules"] = list(completed)
        save_video_config(config_path, video_config)
        logger.success(f"[DONE] {module_name}")

    # ---------------------------------------------------------------------------
    # Final output
    # ---------------------------------------------------------------------------
    final_path = video_config.get("final_video_path", "not yet produced")
    logger.success(f"=== Job complete! ===")
    logger.success(f"Output: {final_path}")
    logger.info(f"video_config saved to: {config_path}")
    print(f"\nFinal video: {final_path}")


if __name__ == "__main__":
    main()
