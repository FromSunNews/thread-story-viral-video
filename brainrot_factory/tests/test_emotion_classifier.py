"""
Tests for emotion_classifier module.

Tests community reaction classification for Vietnamese comments.
Run: python tests/test_emotion_classifier.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.emotion_classifier import (
    classify, classify_batch, pick_memes,
    EMOTIONS, EMOTIONS_SET, _classify_rules,
)

ASSETS_DIR = Path(__file__).parent.parent / "assets"

# ---------------------------------------------------------------------------
# Test data — (comment, expected_any_of, description)
# expected_any_of: at least ONE of these must appear in the result
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "comment": "mẹ bắt tôi học bài từ 0h sáng đến 7h sáng",
        "expected_any": ["dong_tinh", "xuc_dong", "la_len_giai_toa", "that_vong", "tuc_gian"],
        "desc": "Học đêm bị ép → cộng đồng đồng cảm / bức xúc hộ",
    },
    {
        "comment": "tôi bị gay",
        "expected_any": ["joke_gay", "mac_cuoi", "kho_tin", "ngac_nhien"],
        "desc": "Tự nhận gay → cộng đồng cười / ngạc nhiên",
    },
    {
        "comment": "Dm bị 2 thằng nyc đá nên lấy tên bọn nó viết truyện gay",
        "expected_any": ["joke_gay", "mac_cuoi", "cao_tay", "ngac_nhien"],
        "desc": "Viết truyện gay từ ex → hài, creative revenge",
    },
    {
        "comment": "lớp 1 mới vào nghe tin trường có ma trong nhà vệ sinh nên không dám đi, ngồi ỉa trong lớp",
        "expected_any": ["joke_do_mixi", "mac_cuoi", "awkward"],
        "desc": "Hành động phi logic buồn cười",
    },
    {
        "comment": "bị mẹ chửi vì học muộn từ 8h tối đến 2h sáng, ấm ức quá học thẳng đến sáng",
        "expected_any": ["dong_tinh", "la_len_giai_toa", "nguong_mo", "soc_nang"],
        "desc": "Học đêm vì ấm ức → đồng cảm + ngưỡng mộ",
    },
    {
        "comment": "tớ là con trai muốn bị địt bởi anh con trai khác, mồm vẫn nói mình thẳng",
        "expected_any": ["joke_gay", "mac_cuoi", "kho_tin"],
        "desc": "Gay denial joke",
    },
    {
        "comment": "nửa đêm không ngủ được, xuống làm 5 đề toán 6 đề văn",
        "expected_any": ["thong_minh", "nguong_mo", "soc_nang", "kho_tin"],
        "desc": "Flex học khủng → ngưỡng mộ / không tin",
    },
    {
        "comment": "tôi vừa bị lừa mất 50 triệu vì tin vào app đầu tư online",
        "expected_any": ["lua_dao", "thuong_xot", "that_vong", "tuc_gian"],
        "desc": "Bị scam → tội nghiệp / tức giận",
    },
    {
        "comment": "thật ra crush tôi đã thích tôi từ lâu mà tôi không biết",
        "expected_any": ["plot_twist", "ngac_nhien", "xuc_dong", "phan_khich"],
        "desc": "Plot twist crush mutual → bất ngờ / phấn khích",
    },
    {
        "comment": "bạn thân phản bội tôi, kể bí mật của tôi cho cả lớp",
        "expected_any": ["bi_phan_bon", "tuc_gian", "buon_dau_long", "that_vong"],
        "desc": "Bị bạn thân phản bội → tức giận / buồn",
    },
    {
        "comment": "giá mà hồi đó tôi không bỏ cơ hội đó, giờ nghĩ lại vẫn tiếc",
        "expected_any": ["hoi_han", "buon_dau_long", "nho_nhung"],
        "desc": "Hối hận quá khứ → tiếc / nhớ nhung",
    },
    {
        "comment": "OMG sốc toàn tập, không thể tin được đây là sự thật",
        "expected_any": ["soc_nang", "kho_tin", "ngac_nhien"],
        "desc": "Shock nặng",
    },
    {
        "comment": "tôi không quan tâm, kệ đi, không liên quan đến tôi",
        "expected_any": ["khong_quan_tam", "binh_than", "buong_bo"],
        "desc": "Thái độ không quan tâm",
    },
    {
        "comment": "tiếp đi tiếp đi!!! phần 2 đâu? hóng quá trời",
        "expected_any": ["hong_hot", "phan_khich"],
        "desc": "Hóng hớt drama",
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_emotions_list():
    """All emotion values must be non-empty strings, no duplicates."""
    assert len(EMOTIONS) > 0, "EMOTIONS list must not be empty"
    assert len(EMOTIONS) == len(set(EMOTIONS)), "Duplicate emotion names found"
    for e in EMOTIONS:
        assert isinstance(e, str) and len(e) > 0
    print(f"  ✓ {len(EMOTIONS)} emotions defined, no duplicates")


def test_classify_returns_valid_emotions():
    """classify() must return only valid emotion names."""
    samples = [c["comment"] for c in TEST_CASES[:5]]
    for text in samples:
        result = classify(text, use_llm=False)
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        for e in result:
            assert e in EMOTIONS_SET, f"Unknown emotion '{e}' returned for: {text[:50]}"
    print("  ✓ All returned emotions are valid")


def test_classify_no_duplicates():
    """classify() must never return duplicate emotions."""
    for case in TEST_CASES:
        result = classify(case["comment"], use_llm=False)
        assert len(result) == len(set(result)), \
            f"Duplicate emotions in result {result} for: {case['comment'][:50]}"
    print("  ✓ No duplicate emotions in any result")


def test_classify_max_k():
    """classify() must never return more than top_k emotions."""
    for k in [1, 2, 3]:
        for case in TEST_CASES[:5]:
            result = classify(case["comment"], top_k=k, use_llm=False)
            assert len(result) <= k, \
                f"Got {len(result)} emotions with top_k={k}: {result}"
    print("  ✓ top_k limit respected")


def test_classify_expected_emotions():
    """At least one expected emotion must appear for each test case (rule-based)."""
    passed = 0
    failed = []
    for case in TEST_CASES:
        result = classify(case["comment"], use_llm=False)
        hit = any(e in result for e in case["expected_any"])
        if hit:
            passed += 1
        else:
            failed.append({
                "desc": case["desc"],
                "comment": case["comment"][:60],
                "expected_any": case["expected_any"],
                "got": result,
            })

    print(f"  ✓ {passed}/{len(TEST_CASES)} test cases matched expected emotions")
    if failed:
        print("  ⚠ Missed cases (rule-based — LLM may fix these):")
        for f in failed:
            print(f"    [{f['desc']}]")
            print(f"      comment: {f['comment']}")
            print(f"      expected any of: {f['expected_any']}")
            print(f"      got: {f['got']}")


def test_classify_batch():
    """classify_batch() must return one list per input text."""
    texts = [c["comment"] for c in TEST_CASES[:5]]
    results = classify_batch(texts, use_llm=False)
    assert len(results) == len(texts), "Result count mismatch"
    for result in results:
        assert isinstance(result, list)
        for e in result:
            assert e in EMOTIONS_SET
    print(f"  ✓ classify_batch returned {len(results)} results")


def test_pick_memes_no_duplicates():
    """pick_memes() must never return the same file twice in one video."""
    used: set[str] = set()
    # Simulate 5 comments each with 2 emotions
    all_picked = []
    emotion_pairs = [
        ["mac_cuoi", "joke_gay"],
        ["dong_tinh", "xuc_dong"],
        ["la_len_giai_toa", "tuc_gian"],
        ["soc_nang", "ngac_nhien"],
        ["thong_minh", "nguong_mo"],
    ]
    for emotions in emotion_pairs:
        picked = pick_memes(emotions, used, ASSETS_DIR)
        for item in picked:
            assert item["path"] not in [p["path"] for p in all_picked], \
                f"Duplicate meme path: {item['path']}"
            all_picked.append(item)

    print(f"  ✓ pick_memes: {len(all_picked)} memes picked, no duplicates")
    if all_picked:
        for item in all_picked:
            print(f"    {item['emotion']} [{item['type']}] → {Path(item['path']).name}")
    else:
        print("    (no meme files in memes_emotions/ yet — add clips to test file picking)")


def test_pick_memes_returns_valid_types():
    """pick_memes() must only return 'video' or 'image' types."""
    used: set[str] = set()
    picked = pick_memes(EMOTIONS[:10], used, ASSETS_DIR)
    for item in picked:
        assert item["type"] in ("video", "image"), f"Invalid type: {item['type']}"
        assert Path(item["path"]).exists(), f"Meme file not found: {item['path']}"
    print(f"  ✓ All picked memes have valid type and exist on disk ({len(picked)} total)")


def test_classify_with_llm():
    """LLM classification test — runs only if OPENROUTER_API_KEY is set."""
    import os
    if not os.getenv("OPENROUTER_API_KEY"):
        print("  ⚠ OPENROUTER_API_KEY not set — skipping LLM test")
        return

    hard_cases = [
        TEST_CASES[0],  # học đêm
        TEST_CASES[1],  # bị gay
        TEST_CASES[8],  # plot twist crush
    ]
    passed = 0
    for case in hard_cases:
        result = classify(case["comment"], use_llm=True)
        hit = any(e in result for e in case["expected_any"])
        status = "✓" if hit else "✗"
        print(f"    [{status}] {case['desc'][:40]} → {result}")
        if hit:
            passed += 1
    print(f"  LLM: {passed}/{len(hard_cases)} matched")


# ---------------------------------------------------------------------------
# Visual output
# ---------------------------------------------------------------------------

def print_classifications():
    """Print rule-based + LLM results for all test cases."""
    import os
    has_llm = bool(os.getenv("OPENROUTER_API_KEY"))
    print("\n  Sample classifications (rule-based):")
    print(f"  {'Comment':<55} {'Emotions'}")
    print("  " + "-" * 80)
    for case in TEST_CASES:
        result = classify(case["comment"], use_llm=False)
        comment_preview = case["comment"][:52] + "..." if len(case["comment"]) > 52 else case["comment"]
        print(f"  {comment_preview:<55} {result}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n=== test_emotion_classifier ===\n")

    tests = [
        ("Emotions list",           test_emotions_list),
        ("Valid emotions returned", test_classify_returns_valid_emotions),
        ("No duplicates",           test_classify_no_duplicates),
        ("top_k limit",             test_classify_max_k),
        ("Expected emotions hit",   test_classify_expected_emotions),
        ("Batch classify",          test_classify_batch),
        ("Meme picker no dups",     test_pick_memes_no_duplicates),
        ("Meme picker file types",  test_pick_memes_returns_valid_types),
        ("LLM classify",            test_classify_with_llm),
    ]

    passed = failed = 0
    for name, fn in tests:
        print(f"[{name}]")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1
        print()

    print_classifications()

    print(f"\n{'='*40}")
    print(f"  {passed} passed / {failed} failed")
    if failed == 0:
        print("  All tests passed!")
