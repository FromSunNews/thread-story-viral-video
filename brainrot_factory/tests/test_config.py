"""
Tests for config.py — verifies directory creation, value types, and device validity.
Run with: python -m pytest tests/test_config.py -v
"""

import sys
from pathlib import Path

# Ensure brainrot_factory package root is on the path when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import config


class TestDirectoryCreation:
    """All configured directories should be creatable (or already exist)."""

    def test_base_dir_exists(self):
        assert config.BASE_DIR.exists(), f"BASE_DIR does not exist: {config.BASE_DIR}"

    def test_assets_dir_can_be_created(self, tmp_path):
        # The actual ASSETS_DIR lives under BASE_DIR; we just verify the path resolves correctly
        assert isinstance(config.ASSETS_DIR, Path)

    def test_output_dir_can_be_created(self, tmp_path):
        assert isinstance(config.OUTPUT_DIR, Path)

    def test_data_dir_can_be_created(self, tmp_path):
        assert isinstance(config.DATA_DIR, Path)

    def test_templates_dir_can_be_created(self, tmp_path):
        assert isinstance(config.TEMPLATES_DIR, Path)

    def test_logs_dir_can_be_created(self, tmp_path):
        assert isinstance(config.LOGS_DIR, Path)

    def test_all_dirs_are_under_base(self):
        for attr in ("ASSETS_DIR", "OUTPUT_DIR", "DATA_DIR", "TEMPLATES_DIR", "LOGS_DIR"):
            d = getattr(config, attr)
            assert str(d).startswith(str(config.BASE_DIR)), (
                f"{attr} ({d}) is not under BASE_DIR ({config.BASE_DIR})"
            )

    def test_create_all_configured_dirs(self, tmp_path):
        """Verify each directory can actually be mkdir'd without error."""
        dirs_to_create = [
            config.ASSETS_DIR,
            config.OUTPUT_DIR,
            config.DATA_DIR,
            config.TEMPLATES_DIR,
            config.LOGS_DIR,
            config.OUTPUT_DIR / "jobs",
            config.OUTPUT_DIR / "final",
        ]
        for d in dirs_to_create:
            d.mkdir(parents=True, exist_ok=True)
            assert d.exists(), f"Could not create directory: {d}"


class TestConfigValueTypes:
    """Config values must have the correct Python types."""

    # --- Path types ---
    def test_base_dir_is_path(self):
        assert isinstance(config.BASE_DIR, Path)

    def test_assets_dir_is_path(self):
        assert isinstance(config.ASSETS_DIR, Path)

    def test_output_dir_is_path(self):
        assert isinstance(config.OUTPUT_DIR, Path)

    def test_data_dir_is_path(self):
        assert isinstance(config.DATA_DIR, Path)

    def test_templates_dir_is_path(self):
        assert isinstance(config.TEMPLATES_DIR, Path)

    def test_logs_dir_is_path(self):
        assert isinstance(config.LOGS_DIR, Path)

    # --- String types ---
    def test_device_is_str(self):
        assert isinstance(config.DEVICE, str)

    def test_ffmpeg_codec_is_str(self):
        assert isinstance(config.FFMPEG_ENCODE_CODEC, str)

    def test_ffmpeg_quality_is_str(self):
        assert isinstance(config.FFMPEG_ENCODE_QUALITY, str)

    def test_whisper_device_is_str(self):
        assert isinstance(config.WHISPER_DEVICE, str)

    def test_whisper_model_size_is_str(self):
        assert isinstance(config.WHISPER_MODEL_SIZE, str)

    def test_tts_provider_is_str(self):
        assert isinstance(config.TTS_PROVIDER, str)

    def test_voice_vi_is_str(self):
        assert isinstance(config.VOICE_VI, str)

    def test_voice_en_is_str(self):
        assert isinstance(config.VOICE_EN, str)

    def test_video_bitrate_is_str(self):
        assert isinstance(config.VIDEO_BITRATE, str)

    def test_reddit_user_agent_is_str(self):
        assert isinstance(config.REDDIT_USER_AGENT, str)

    # --- Integer types ---
    def test_video_width_is_int(self):
        assert isinstance(config.VIDEO_WIDTH, int)

    def test_video_height_is_int(self):
        assert isinstance(config.VIDEO_HEIGHT, int)

    def test_video_fps_is_int(self):
        assert isinstance(config.VIDEO_FPS, int)

    def test_max_comments_is_int(self):
        assert isinstance(config.MAX_COMMENTS, int)

    def test_min_comment_length_is_int(self):
        assert isinstance(config.MIN_COMMENT_LENGTH, int)

    def test_meme_cooldown_is_int(self):
        assert isinstance(config.MEME_COOLDOWN_VIDEOS, int)

    # --- Float types ---
    def test_request_delay_is_float(self):
        assert isinstance(config.REQUEST_DELAY, float)

    def test_bgm_volume_is_float(self):
        assert isinstance(config.BGM_VOLUME, float)

    def test_sfx_volume_is_float(self):
        assert isinstance(config.SFX_VOLUME, float)

    # --- Bool types ---
    def test_playwright_headless_is_bool(self):
        assert isinstance(config.PLAYWRIGHT_HEADLESS, bool)

    # --- Sensible value ranges ---
    def test_video_width_positive(self):
        assert config.VIDEO_WIDTH > 0

    def test_video_height_positive(self):
        assert config.VIDEO_HEIGHT > 0

    def test_video_fps_positive(self):
        assert config.VIDEO_FPS > 0

    def test_bgm_volume_range(self):
        assert 0.0 <= config.BGM_VOLUME <= 1.0

    def test_sfx_volume_range(self):
        assert 0.0 <= config.SFX_VOLUME <= 1.0

    def test_max_comments_positive(self):
        assert config.MAX_COMMENTS > 0

    def test_request_delay_non_negative(self):
        assert config.REQUEST_DELAY >= 0


class TestDevice:
    """DEVICE must be a valid PyTorch compute target."""

    VALID_DEVICES = {"mps", "cpu", "cuda"}

    def test_device_is_valid(self):
        assert config.DEVICE in self.VALID_DEVICES, (
            f"DEVICE '{config.DEVICE}' is not one of {self.VALID_DEVICES}"
        )

    def test_device_is_mps_or_cpu(self):
        """On Apple Silicon the project expects mps or cpu only."""
        assert config.DEVICE in {"mps", "cpu"}, (
            f"Expected 'mps' or 'cpu', got '{config.DEVICE}'"
        )

    def test_whisper_device_is_cpu(self):
        """Whisper is pinned to CPU per M2 optimization settings."""
        assert config.WHISPER_DEVICE == "cpu", (
            f"WHISPER_DEVICE should be 'cpu', got '{config.WHISPER_DEVICE}'"
        )
