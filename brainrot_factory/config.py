import os
import torch
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"

# M2 Optimizations
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
FFMPEG_ENCODE_CODEC = "h264_videotoolbox"
FFMPEG_ENCODE_QUALITY = "65"
WHISPER_DEVICE = "cpu"
WHISPER_MODEL_SIZE = "tiny"
PLAYWRIGHT_HEADLESS = True
PLAYWRIGHT_BROWSER = "chromium"

# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_BITRATE = "8M"

# TTS
TTS_PROVIDER = "edge_tts"  # edge_tts | fpt_ai | kokoro
VOICE_VI = "vi-VN-HoaiMyNeural"
VOICE_EN = "en-US-AriaNeural"
BGM_VOLUME = 0.6
SFX_VOLUME = 0.80

# Scraper
MAX_COMMENTS = int(os.getenv("MAX_COMMENTS", "5"))
MIN_COMMENT_LENGTH = 30
REQUEST_DELAY = 3.0  # seconds between Threads requests
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = "brainrot_factory/1.0"

# Meme engine
MEME_COOLDOWN_VIDEOS = 5  # how many videos before a clip can repeat

# API keys (optional)
FPT_AI_KEY = os.getenv("FPT_AI_KEY", "")
KLIPY_API_KEY = os.getenv("KLIPY_API_KEY", "")
