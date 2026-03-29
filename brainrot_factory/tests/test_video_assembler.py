"""Tests for Module 6 — Video Assembler"""
import os
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def _get_test_config(with_audio=False):
    config = {
        "job_id": "test_video",
        "video": {
            "resolution": {"width": 1080, "height": 1920},
            "fps": 30,
            "output_path": "output/final/test_video.mp4"
        },
        "source": {
            "lang": "vi",
            "topic": {
                "text": "Test topic",
                "audio_duration": 3.0,
                "card_path": "",  # no card for basic test
            },
            "comments": [
                {
                    "id": "c001",
                    "text": "First comment",
                    "audio_duration": 4.0,
                    "card_path": "",
                    "meme_clip": "",
                    "sfx": "",
                    "sentiment": "POS",
                    "emotion": "joy"
                }
            ]
        },
        "audio": {
            "bgm": "",
            "bgm_volume": 0.12
        },
        "background": {
            "file": ""
        },
        "captions": {
            "ass_path": ""
        }
    }
    return config

def test_timeline_building():
    from modules.video_assembler import _build_timeline
    config = _get_test_config()
    timeline, total_duration = _build_timeline(config)

    assert len(timeline) >= 2  # at least topic + outro
    assert total_duration > 0

    # Check timeline is sorted by start time
    starts = [s["start"] for s in timeline]
    assert starts == sorted(starts)

    print(f"✅ test_timeline_building PASSED — {len(timeline)} segments, {total_duration:.1f}s total")

def test_ffmpeg_available():
    import subprocess
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    assert result.returncode == 0, "ffmpeg not installed"
    print("✅ test_ffmpeg_available PASSED")

def test_video_assembly_minimal():
    """Test assembly with just a black background (no assets needed)."""
    from modules.video_assembler import run
    config = _get_test_config()
    os.makedirs("output/final", exist_ok=True)

    result = run(config)

    output_path = result["video"]["output_path"]
    assert Path(output_path).exists(), f"Output not found: {output_path}"
    assert Path(output_path).stat().st_size > 1000, "Output file too small"

    print(f"✅ test_video_assembly_minimal PASSED")
    print(f"   Output: {output_path}")
    print(f"   Size: {result.get('output', {}).get('size_mb', '?')} MB")

if __name__ == "__main__":
    test_timeline_building()
    test_ffmpeg_available()
    test_video_assembly_minimal()
    print("\n🎉 All video assembler tests passed!")
