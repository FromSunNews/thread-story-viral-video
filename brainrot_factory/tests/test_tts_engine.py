"""Tests for Module 3 — TTS Engine"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def _get_test_config():
    return {
        "job_id": "test_tts",
        "source": {
            "platform": "manual",
            "lang": "vi",
            "topic": {
                "text": "Sếp bạn từng làm gì khiến bạn ngạc nhiên?",
                "author": "@testuser",
                "likes": "12.4K",
                "card_type": "topic"
            },
            "comments": [
                {
                    "id": "c001",
                    "author": "@user1",
                    "text": "Sếp tôi tự tay rửa chén cho cả team",
                    "likes": "3.2K"
                },
                {
                    "id": "c002",
                    "author": "@user2",
                    "text": "My boss helped us fix a production bug at midnight",
                    "likes": "200"
                }
            ]
        },
        "audio": {
            "tts_provider": "edge_tts",
            "voice_vi": "vi-VN-HoaiMyNeural",
            "voice_en": "en-US-AriaNeural"
        }
    }

def test_preprocess_text():
    from modules.tts_engine import _preprocess_text
    result = _preprocess_text("Hello  world...", "en")
    assert "…" in result  # ellipsis normalized
    assert "  " not in result  # no double spaces

    vn = "Thiên  đường..."
    result = _preprocess_text(vn, "vi")
    assert "Thiên đường" in result
    print("✅ test_preprocess_text PASSED")

def test_write_srt():
    from modules.tts_engine import _write_srt
    import os
    os.makedirs("output/jobs/test_tts/audio", exist_ok=True)

    timestamps = [
        {"word": "Hello", "start": 0.0, "end": 0.4},
        {"word": "world", "start": 0.5, "end": 0.9},
        {"word": "test", "start": 1.0, "end": 1.4},
    ]
    out = Path("output/jobs/test_tts/audio/test.srt")
    _write_srt(timestamps, out)

    assert out.exists()
    content = out.read_text()
    assert "Hello" in content
    assert "00:00:00,000" in content
    print("✅ test_write_srt PASSED")

def test_tts_generation():
    """Test actual TTS generation with edge-tts."""
    import os
    os.makedirs("output/jobs/test_tts/audio", exist_ok=True)

    from modules.tts_engine import run
    config = _get_test_config()
    result = run(config)

    # Check topic audio was generated
    assert result["source"]["topic"].get("audio_duration", 0) > 0

    # Check at least first comment
    c001 = next(c for c in result["source"]["comments"] if c["id"] == "c001")
    assert c001.get("audio_duration", 0) > 0
    assert Path(c001.get("audio_path", "")).exists()

    print(f"✅ test_tts_generation PASSED")
    print(f"   Topic duration: {result['source']['topic'].get('audio_duration')}s")
    print(f"   c001 duration: {c001.get('audio_duration')}s")

if __name__ == "__main__":
    test_preprocess_text()
    test_write_srt()
    test_tts_generation()
    print("\n🎉 All TTS tests passed!")
