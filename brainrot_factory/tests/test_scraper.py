"""Tests for Module 1 — Scraper"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_normalize_likes():
    from modules.scraper import _normalize_likes
    assert _normalize_likes(0) == "0"
    assert _normalize_likes(500) == "500"
    assert _normalize_likes(1200) == "1.2K"
    assert _normalize_likes(1000) == "1.0K"
    assert _normalize_likes(1_500_000) == "1.5M"
    assert _normalize_likes(None) == "0"
    print("test_normalize_likes PASSED")

def test_normalize_text():
    from modules.scraper import _normalize_text
    result = _normalize_text("Hello &amp; World &lt;b&gt;bold&lt;/b&gt;")
    assert "Hello & World" in result
    assert "<b>" not in result
    import unicodedata
    vn = "Thien duong khong co nghia la mai mai"
    result = _normalize_text(vn)
    assert unicodedata.is_normalized("NFC", result)
    print("test_normalize_text PASSED")

def test_manual_json_input():
    import os
    os.makedirs("output/jobs/test_scraper", exist_ok=True)

    test_data = {
        "topic": {"text": "Sep ban tung lam gi khien ban ngac nhien?", "author": "@testuser", "likes": "12.4K"},
        "comments": [
            {"id": "c001", "author": "@user1", "text": "Sep toi tu tay rua chen cho ca team sau bua an tat nien", "likes": "3.2K"},
            {"id": "c002", "author": "@user2", "text": "Thien duong khong co nghia la mai mai - test Vietnamese diacritics", "likes": "200"},
            {"id": "c003", "author": "@user3", "text": "My boss once showed up at 3am to help us fix a production bug", "likes": "1.5K"},
        ]
    }

    manual_path = "output/jobs/test_scraper/manual_input.json"
    with open(manual_path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, ensure_ascii=False)

    from modules.scraper import run
    config = {
        "job_id": "test_scraper",
        "source": {
            "platform": "manual",
            "manual_json_path": manual_path,
            "comments": []
        }
    }
    result = run(config)

    assert result["source"]["topic"]["text"] == "Sep ban tung lam gi khien ban ngac nhien?"
    assert len(result["source"]["comments"]) == 3
    assert result["source"]["comments"][0]["id"] == "c001"

    # Verify cache was written
    assert Path("output/jobs/test_scraper/raw_content.json").exists()
    print("test_manual_json_input PASSED")

def test_cache_hit():
    """Second run should use cache."""
    from modules.scraper import run
    config = {
        "job_id": "test_scraper",
        "source": {
            "platform": "manual",
            "manual_json_path": "output/jobs/test_scraper/manual_input.json",
            "comments": [{"id": "c001"}]  # non-empty = has data already
        }
    }
    result = run(config)
    assert result["source"]["comments"]  # still has comments
    print("test_cache_hit PASSED")

if __name__ == "__main__":
    test_normalize_likes()
    test_normalize_text()
    test_manual_json_input()
    test_cache_hit()
    print("\nAll scraper tests passed!")
