"""Tests for Module 2 — Card Renderer"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def _get_test_config():
    return {
        "job_id": "test_cards",
        "source": {
            "platform": "threads",
            "topic": {
                "author": "bbilikeu_22",
                "timestamp": "9h",
                "text": "ôm hôn sâu, bóp zú xong về ko nói gì qtam hết thì có phải bị ghost r ko ạ 🥹.\nT vs bạn này mập mờ 4 năm :) 2 đứa là bạn học c3 nhưng lên đh thì một đứa vẫn ở tp một đứa lên sg lúc này có tỏ tình hôn nhẹ xong ctay vào sg vì bạn nói ko muốn mình đợi bạn 4 năm ấy.\n4 năm trôi qua bạn về lại tp của bọn mình làm việc, hôm t5 hẹn gặp mình và nói là từ trc đến h đâu có bỏ rơi mình chưa từng nói là không thương mình xin hôn một cái :) và táy máy tay chân.\nHai đứa trong 4 năm ko có ai có ngiu cả, mình là",
                "likes": "117",
                "replies": "32",
                "reposts": "3",
                "shares": "139",
                "card_type": "topic"
            },
            "comments": [
                {
                    "id": "c001",
                    "author": "bbilikeu_22",
                    "timestamp": "9h",
                    "badge": "Author",
                    "text": "mình là nữ rất yêu bạn này, ko có danh phận nên mình rất tủi thân nhma mình rất muốn ở cạnh họ, sự hiện diện của họ thôi cũng thấy hạnh phúc rồi",
                    "likes": "10",
                    "replies": "",
                    "reposts": "",
                    "shares": ""
                },
                {
                    "id": "c002",
                    "author": "thomasnguyen1532",
                    "timestamp": "9h",
                    "text": "ừ b bị lợi dụng r",
                    "likes": "51",
                    "replies": "1",
                    "reposts": "",
                    "shares": ""
                },
                {
                    "id": "c003",
                    "author": "sayhitolittlewolf",
                    "timestamp": "7h",
                    "text": "bạn xứng đáng được yêu thương đúng cách hơn",
                    "likes": "28",
                    "replies": "",
                    "reposts": "",
                    "shares": ""
                }
            ]
        }
    }

def test_card_rendering():
    from modules.card_renderer import run
    config = _get_test_config()
    result = run(config)

    # Check topic card
    assert "card_path" in result["source"]["topic"]
    assert Path(result["source"]["topic"]["card_path"]).exists()

    # Check comment cards
    for comment in result["source"]["comments"]:
        assert "card_path" in comment, f"Missing card_path for {comment['id']}"
        assert Path(comment["card_path"]).exists(), f"Card file missing: {comment.get('card_path')}"

    print("test_card_rendering PASSED")
    print(f"   Cards saved to: output/jobs/test_cards/cards/")

def test_card_is_png():
    from modules.card_renderer import run
    from PIL import Image
    config = _get_test_config()
    result = run(config)

    card_path = result["source"]["comments"][0]["card_path"]
    img = Image.open(card_path)
    assert img.format == "PNG"
    print(f"test_card_is_png PASSED — size: {img.size}")

def test_vietnamese_rendering():
    """Test that Vietnamese diacritics render without corruption."""
    from modules.card_renderer import _render_threads_html
    html = _render_threads_html({
        "id": "vn_test",
        "author": "@testuser",
        "text": "Thien duong khong co nghia la mai mai — oi oi oi",
        "likes": "100"
    })
    assert "Thien duong" in html
    assert "mai mai" in html
    print("test_vietnamese_rendering PASSED")

def test_inline_images():
    """Test card rendering with inline images (like embedded order screenshots)."""
    from modules.card_renderer import run
    from PIL import Image

    config = {
        "job_id": "test_inline_images",
        "source": {
            "platform": "threads",
            "topic": {
                "author": "yasha.quin",
                "timestamp": "3/31/25",
                "text": "Trời oi, shipper giao đơn cho tui nma mẹ tui ở nhà nhận hộ, mẹ tui hỏi đơn gì thì ổng bảo là \"Hồng Bướm\"=))) về nhà mẹ t hỏi là \"con mua gì mà shipper nó bảo đơn hồng bướm\" thế t phải bóc ra cho mẹ t coi.\nCơ mà người t ngại là ông shipper cơ 🤙",
                "likes": "2.4K",
                "replies": "15",
                "reposts": "81",
                "shares": "151",
                "card_type": "topic",
                # dùng ảnh placeholder công khai để test
                "images": ["https://placehold.co/600x400/222/fff.png"]
            },
            "comments": [
                {
                    "id": "c001",
                    "author": "user_two_images",
                    "timestamp": "1h",
                    "text": "2 ảnh test",
                    "likes": "5",
                    "images": [
                        "https://placehold.co/300x300/333/fff.png",
                        "https://placehold.co/300x300/555/fff.png"
                    ]
                },
                {
                    "id": "c002",
                    "author": "user_three_images",
                    "timestamp": "2h",
                    "text": "3 ảnh test",
                    "likes": "3",
                    "images": [
                        "https://placehold.co/600x400/444/fff.png",
                        "https://placehold.co/300x300/666/fff.png",
                        "https://placehold.co/300x300/888/fff.png"
                    ]
                },
                {
                    "id": "c003",
                    "author": "user_no_image",
                    "timestamp": "3h",
                    "text": "Không có ảnh — case bình thường vẫn chạy ok",
                    "likes": "10"
                }
            ]
        }
    }

    result = run(config)

    for item_id in ["topic", "c001", "c002", "c003"]:
        if item_id == "topic":
            path = result["source"]["topic"]["card_path"]
        else:
            path = next(c["card_path"] for c in result["source"]["comments"] if c["id"] == item_id)
        assert Path(path).exists(), f"Card missing: {path}"
        img = Image.open(path)
        assert img.format == "PNG"
        print(f"  {item_id}: {img.size} OK")

    print("test_inline_images PASSED")
    print(f"   Cards: output/jobs/test_inline_images/cards/")


if __name__ == "__main__":
    test_vietnamese_rendering()
    test_card_rendering()
    test_card_is_png()
    test_inline_images()
    print("\nAll card renderer tests passed!")
