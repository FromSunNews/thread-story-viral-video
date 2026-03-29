"""Tests for Module 5 — Meme Engine"""
import os
import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def _get_test_config():
    return {
        "job_id": "test_meme",
        "source": {
            "comments": [
                {"id": "c001", "text": "Sếp tôi rất tốt bụng! Amazing boss!", "likes": "3.2K"},
                {"id": "c002", "text": "Tôi rất buồn khi nghe tin này, so sad", "likes": "200"},
                {"id": "c003", "text": "WOW omg this is so surprising and unexpected!", "likes": "1K"},
                {"id": "c004", "text": "Nothing special happened today", "likes": "50"},
            ]
        }
    }

def test_sentiment_simple():
    from modules.meme_engine import _analyze_sentiment_simple

    s, e = _analyze_sentiment_simple("Amazing happy great wonderful!")
    assert s == "POS"
    assert e == "joy"

    s, e = _analyze_sentiment_simple("This is terrible and bad")
    assert s == "NEG"

    s, e = _analyze_sentiment_simple("WOW omg so surprising!")
    assert e == "surprise"

    s, e = _analyze_sentiment_simple("normal day today")
    assert s == "NEU"
    assert e == "neutral"

    print("✅ test_sentiment_simple PASSED")

def test_db_init():
    from modules.meme_engine import _init_db
    os.makedirs("data", exist_ok=True)
    conn = _init_db(Path("data/test_meme.db"))

    # Verify tables exist
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    assert "memes" in table_names
    assert "job_history" in table_names
    conn.close()
    print("✅ test_db_init PASSED")

def test_full_meme_run():
    from modules.meme_engine import run
    config = _get_test_config()
    result = run(config)

    for comment in result["source"]["comments"]:
        assert "sentiment" in comment
        assert "emotion" in comment
        assert comment["sentiment"] in ("POS", "NEG", "NEU")
        assert comment["emotion"] in ("joy", "surprise", "anger", "sadness", "fear", "disgust", "neutral")

    print("✅ test_full_meme_run PASSED")
    for c in result["source"]["comments"]:
        print(f"   {c['id']}: {c['sentiment']}/{c['emotion']}")

if __name__ == "__main__":
    test_sentiment_simple()
    test_db_init()
    test_full_meme_run()
    print("\n🎉 All meme engine tests passed!")
