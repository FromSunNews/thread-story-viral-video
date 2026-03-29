"""Tests for Module 4 — Caption Sync"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def _get_test_config():
    return {
        "job_id": "test_captions",
        "source": {
            "lang": "vi",
            "topic": {
                "text": "Test topic",
                "audio_duration": 3.0,
                "timestamps": [
                    {"word": "Test", "start": 0.0, "end": 0.4},
                    {"word": "topic", "start": 0.5, "end": 0.9},
                ]
            },
            "comments": [
                {
                    "id": "c001",
                    "text": "Sếp tôi rất tốt bụng với mọi người",
                    "audio_duration": 4.2,
                    "timestamps": [
                        {"word": "Sếp", "start": 0.0, "end": 0.3},
                        {"word": "tôi", "start": 0.3, "end": 0.6},
                        {"word": "rất", "start": 0.6, "end": 0.9},
                        {"word": "tốt", "start": 0.9, "end": 1.2},
                        {"word": "bụng", "start": 1.2, "end": 1.6},
                        {"word": "với", "start": 1.7, "end": 2.0},
                        {"word": "mọi", "start": 2.1, "end": 2.4},
                        {"word": "người", "start": 2.5, "end": 3.0},
                    ]
                }
            ]
        }
    }

def test_ass_format():
    from modules.caption_sync import _fmt_ass_time
    assert _fmt_ass_time(0) == "0:00:00.00"
    assert _fmt_ass_time(65.5) == "0:01:05.50"
    assert _fmt_ass_time(3661.25) == "1:01:01.25"
    print("✅ test_ass_format PASSED")

def test_group_words():
    from modules.caption_sync import _group_words_into_lines
    words = [{"word": f"word{i}", "start": i*0.3, "end": i*0.3+0.25} for i in range(12)]
    groups = _group_words_into_lines(words, max_words=5)
    assert len(groups) == 3  # 12 words → 3 lines of 4,4,4... actually 3 lines: 5,5,2
    assert len(groups[0]) == 5
    print("✅ test_group_words PASSED")

def test_ass_generation():
    import os
    os.makedirs("output/jobs/test_captions/captions", exist_ok=True)

    from modules.caption_sync import run
    config = _get_test_config()
    result = run(config)

    ass_path = Path(result["captions"]["ass_path"])
    assert ass_path.exists()

    content = ass_path.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert "Dialogue:" in content
    assert r"\k" in content  # karaoke tags present

    print("✅ test_ass_generation PASSED")
    print(f"   Lines: {content.count('Dialogue:')}")
    print(f"   File: {ass_path}")

if __name__ == "__main__":
    test_ass_format()
    test_group_words()
    test_ass_generation()
    print("\n🎉 All caption sync tests passed!")
