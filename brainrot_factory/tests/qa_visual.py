"""
QA Visual Validation — Uses Playwright + PIL to validate card renders.
Captures screenshots and inspects image quality.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

REPORT = []

def log(msg, status="INFO"):
    icon = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️", "WARN": "⚠️"}.get(status, "•")
    print(f"{icon} {msg}")
    REPORT.append({"status": status, "msg": msg})


# ─── TEST 1: Card HTML renders correctly in browser ───────────────────────────

async def test_card_html_playwright():
    """Use Playwright to render a card and capture a screenshot for visual inspection."""
    from playwright.async_api import async_playwright
    from modules.card_renderer import _render_threads_html

    test_items = [
        {
            "id": "qa_vi",
            "author": "@nguyen_van_a",
            "text": "Sếp tôi một lần tự tay rửa bát cho cả phòng sau bữa tiệc tất niên. Mọi người đều ngạc nhiên và cảm động lắm.",
            "likes": "3.2K",
            "card_type": "comment"
        },
        {
            "id": "qa_en",
            "author": "@john_doe",
            "text": "My boss showed up at 3am to help us fix a production outage. Unbelievable dedication!",
            "likes": "1.5K",
            "card_type": "comment"
        },
        {
            "id": "qa_topic",
            "author": "@threads_official",
            "text": "Sếp bạn từng làm gì khiến bạn ngạc nhiên nhất?",
            "likes": "12.4K",
            "card_type": "topic"
        },
        {
            "id": "qa_long",
            "author": "@long_text_user",
            "text": "Thiên đường không có nghĩa là mãi mãi — ơi ơi ơi. Cuộc sống có những lúc thăng trầm nhưng quan trọng là chúng ta luôn đứng dậy sau mỗi lần vấp ngã và tiếp tục hành trình của mình với tất cả sức mạnh và niềm tin.",
            "likes": "8.7K",
            "card_type": "comment"
        }
    ]

    Path("output/jobs/qa_test/cards").mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1200, "height": 2000})
        page = await context.new_page()

        for item in test_items:
            html = _render_threads_html(item, "threads")
            await page.set_content(html, wait_until="domcontentloaded")
            await asyncio.sleep(0.5)

            # Full page screenshot for inspection
            screenshot_path = f"output/jobs/qa_test/cards/qa_screenshot_{item['id']}.png"
            await page.screenshot(path=screenshot_path, full_page=True)

            # Element screenshot
            card_el = await page.query_selector(".card")
            if card_el:
                card_path = f"output/jobs/qa_test/cards/{item['id']}.png"
                await card_el.screenshot(path=card_path, omit_background=True)

                # Validate with PIL
                from PIL import Image
                img = Image.open(card_path)

                # Check dimensions
                w, h = img.size
                if w < 900:
                    log(f"Card {item['id']} too narrow: {w}px (expected ~1000)", "FAIL")
                elif w > 1100:
                    log(f"Card {item['id']} too wide: {w}px", "WARN")
                else:
                    log(f"Card {item['id']}: {w}x{h}px ✓", "PASS")

                # Check it's not all black (rendering failed)
                import numpy as np
                arr = np.array(img)
                mean_brightness = arr[:,:,:3].mean()
                if mean_brightness < 10:
                    log(f"Card {item['id']} appears black (rendering failure)", "FAIL")
                else:
                    log(f"Card {item['id']} brightness: {mean_brightness:.1f} (OK)", "PASS")

                # Check RGBA mode
                if img.mode != "RGBA":
                    log(f"Card {item['id']} mode is {img.mode} (expected RGBA)", "WARN")
                else:
                    log(f"Card {item['id']} is RGBA transparent PNG ✓", "PASS")

                # Check Vietnamese text rendered (not tofu boxes)
                # Do a pixel color check at expected text position
                if item["id"] == "qa_vi":
                    # Sample middle area for non-black pixels
                    mid_y = h // 2
                    mid_row = arr[mid_y, :, :3]
                    non_dark = (mid_row.max(axis=1) > 100).sum()
                    if non_dark < 50:
                        log("Vietnamese text may not be rendering (mostly dark pixels)", "WARN")
                    else:
                        log(f"Vietnamese text rendering OK ({non_dark} bright pixels in middle row)", "PASS")
            else:
                log(f"Card {item['id']}: .card element not found in page", "FAIL")

        # Get Chrome DevTools performance metrics
        metrics = await page.evaluate("() => JSON.stringify(window.performance.timing)")
        log(f"Browser DevTools timing captured", "INFO")

        await browser.close()

    log(f"Visual card tests complete. Screenshots saved to output/jobs/qa_test/cards/", "INFO")


# ─── TEST 2: Full pipeline end-to-end ──────────────────────────────────────────

def test_full_pipeline():
    """Run the complete 6-module pipeline with a manual test job."""
    import subprocess
    import os

    os.makedirs("output/jobs/qa_e2e", exist_ok=True)

    # Create test input
    test_input = {
        "topic": {
            "text": "Sếp bạn từng làm gì khiến bạn ngạc nhiên nhất?",
            "author": "@vietlife",
            "likes": "12.4K"
        },
        "comments": [
            {
                "id": "c001",
                "author": "@nguyen_van_a",
                "text": "Sếp tôi tự tay rửa bát cho cả team sau bữa tiệc tất niên. Ai cũng ngạc nhiên.",
                "likes": "3.2K"
            },
            {
                "id": "c002",
                "author": "@tran_thi_b",
                "text": "Boss của mình tự đi mua cơm cho cả phòng khi làm thêm giờ. Không ai dám tin.",
                "likes": "2.1K"
            },
            {
                "id": "c003",
                "author": "@le_van_c",
                "text": "Sếp cũ của tôi tự viết thư tay cảm ơn từng nhân viên cuối năm. Rất xúc động.",
                "likes": "1.8K"
            }
        ]
    }

    with open("output/jobs/qa_e2e/manual_input.json", "w", encoding="utf-8") as f:
        json.dump(test_input, f, ensure_ascii=False, indent=2)

    log("Starting end-to-end pipeline test...", "INFO")

    # Run each module individually and check output
    modules_results = {}

    import importlib
    import sys

    cfg = {
        "job_id": "qa_e2e",
        "video": {
            "resolution": {"width": 1080, "height": 1920},
            "fps": 30,
            "output_path": "output/final/qa_e2e.mp4"
        },
        "source": {
            "platform": "manual",
            "lang": "vi",
            "manual_json_path": "output/jobs/qa_e2e/manual_input.json",
            "comments": []
        },
        "audio": {
            "tts_provider": "edge_tts",
            "voice_vi": "vi-VN-HoaiMyNeural",
            "voice_en": "en-US-AriaNeural",
            "bgm": "",
            "bgm_volume": 0.12
        },
        "background": {"file": ""},
        "captions": {"ass_path": ""}
    }

    module_sequence = [
        ("scraper", "modules.scraper"),
        ("card_renderer", "modules.card_renderer"),
        ("tts_engine", "modules.tts_engine"),
        ("caption_sync", "modules.caption_sync"),
        ("meme_engine", "modules.meme_engine"),
        ("video_assembler", "modules.video_assembler"),
    ]

    for mod_name, mod_path in module_sequence:
        try:
            import time
            t0 = time.time()
            mod = importlib.import_module(mod_path)
            cfg = mod.run(cfg)
            elapsed = time.time() - t0
            log(f"Module {mod_name}: OK ({elapsed:.1f}s)", "PASS")
            modules_results[mod_name] = "PASS"

            # Module-specific validations
            if mod_name == "scraper":
                assert cfg["source"].get("topic"), "topic missing"
                assert len(cfg["source"].get("comments", [])) > 0, "no comments"
                log(f"  → {len(cfg['source']['comments'])} comments scraped", "INFO")

            elif mod_name == "card_renderer":
                cards_ok = sum(1 for c in cfg["source"]["comments"] if Path(c.get("card_path", "")).exists())
                log(f"  → {cards_ok}/{len(cfg['source']['comments'])} cards rendered", "INFO" if cards_ok == len(cfg["source"]["comments"]) else "WARN")

            elif mod_name == "tts_engine":
                audio_ok = sum(1 for c in cfg["source"]["comments"] if c.get("audio_duration", 0) > 0)
                total_dur = sum(c.get("audio_duration", 0) for c in cfg["source"]["comments"])
                log(f"  → {audio_ok} TTS segments, total audio: {total_dur:.1f}s", "INFO")

            elif mod_name == "caption_sync":
                ass_path = cfg.get("captions", {}).get("ass_path", "")
                if ass_path and Path(ass_path).exists():
                    content = Path(ass_path).read_text()
                    n_lines = content.count("Dialogue:")
                    log(f"  → ASS caption: {n_lines} dialogue lines", "INFO")

            elif mod_name == "meme_engine":
                emotions = [c.get("emotion") for c in cfg["source"]["comments"]]
                log(f"  → Emotions detected: {emotions}", "INFO")

            elif mod_name == "video_assembler":
                out_path = cfg.get("output", {}).get("path", cfg["video"]["output_path"])
                if Path(out_path).exists():
                    size = Path(out_path).stat().st_size / 1024 / 1024
                    log(f"  → Output: {out_path} ({size:.1f} MB)", "INFO")

                    # Probe the output video
                    import subprocess as sp
                    probe = sp.run(
                        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", out_path],
                        capture_output=True, text=True
                    )
                    if probe.returncode == 0:
                        probe_data = json.loads(probe.stdout)
                        for stream in probe_data.get("streams", []):
                            if stream.get("codec_type") == "video":
                                log(f"  → Video: {stream.get('codec_name')}, {stream.get('width')}x{stream.get('height')}, {stream.get('avg_frame_rate')}fps", "PASS")
                            elif stream.get("codec_type") == "audio":
                                log(f"  → Audio: {stream.get('codec_name')}, {stream.get('sample_rate')}Hz", "PASS")
                else:
                    log(f"  Output file missing: {out_path}", "FAIL")

        except Exception as e:
            import traceback
            log(f"Module {mod_name}: FAILED — {e}", "FAIL")
            log(f"  Traceback: {traceback.format_exc()[-500:]}", "FAIL")
            modules_results[mod_name] = f"FAIL: {e}"

    return modules_results, cfg


# ─── TEST 3: Chrome DevTools API validation ────────────────────────────────────

async def test_devtools_card_metrics():
    """Use Playwright CDP (Chrome DevTools Protocol) to validate card rendering metrics."""
    from playwright.async_api import async_playwright
    from modules.card_renderer import _render_threads_html

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Enable CDP
        cdp = await context.new_cdp_session(page)

        html = _render_threads_html({
            "id": "devtools_test",
            "author": "@devtools_user",
            "text": "Thiên đường không có nghĩa là mãi mãi — testing Chrome DevTools validation",
            "likes": "999",
            "card_type": "comment"
        })

        await page.set_content(html, wait_until="domcontentloaded")
        await asyncio.sleep(0.5)

        # Get layout metrics via CDP
        layout = await cdp.send("Page.getLayoutMetrics")
        log(f"DevTools layout: contentSize={layout.get('contentSize', {})}", "INFO")

        # Get computed style of .card element
        card_info = await page.evaluate("""() => {
            const card = document.querySelector('.card');
            if (!card) return null;
            const style = window.getComputedStyle(card);
            const rect = card.getBoundingClientRect();
            return {
                width: rect.width,
                height: rect.height,
                backgroundColor: style.backgroundColor,
                borderRadius: style.borderRadius,
                fontSize: style.fontSize,
                color: style.color
            };
        }""")

        if card_info:
            log(f"DevTools card width: {card_info['width']:.0f}px (expected: ~1000)",
                "PASS" if 900 <= card_info['width'] <= 1100 else "FAIL")
            log(f"DevTools card height: {card_info['height']:.0f}px (expected: 160-520)",
                "PASS" if 160 <= card_info['height'] <= 520 else "WARN")
            log(f"DevTools bg color: {card_info['backgroundColor']}", "INFO")
            log(f"DevTools border-radius: {card_info['borderRadius']}", "INFO")
        else:
            log("DevTools: .card element not found", "FAIL")

        # Check for console errors
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        await page.evaluate("() => document.body.offsetHeight")  # force layout

        if errors:
            log(f"DevTools console errors: {errors}", "WARN")
        else:
            log("DevTools: no console errors ✓", "PASS")

        # Screenshot for visual report
        Path("output/jobs/qa_test/devtools").mkdir(parents=True, exist_ok=True)
        await page.screenshot(path="output/jobs/qa_test/devtools/card_devtools.png", full_page=True)
        log("DevTools screenshot captured: output/jobs/qa_test/devtools/card_devtools.png", "INFO")

        await browser.close()


# ─── TEST 4: Image Quality Analysis with PIL ───────────────────────────────────

def test_image_quality(cards_dir: str = "output/jobs/qa_test/cards"):
    """Analyze rendered card images for quality issues."""
    from PIL import Image, ImageStat
    import numpy as np

    cards_path = Path(cards_dir)
    png_files = list(cards_path.glob("*.png"))

    if not png_files:
        log(f"No PNG files found in {cards_dir}", "WARN")
        return

    log(f"Analyzing {len(png_files)} card images...", "INFO")

    for png_path in png_files:
        if "screenshot" in png_path.name:
            continue  # skip full page screenshots

        try:
            img = Image.open(png_path)
            w, h = img.size

            # Convert to RGBA if needed
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            arr = np.array(img)
            rgb = arr[:, :, :3]
            alpha = arr[:, :, 3]

            # Check card isn't completely transparent
            visible_pixels = (alpha > 10).sum()
            total_pixels = alpha.size
            visibility_pct = visible_pixels / total_pixels * 100

            if visibility_pct < 5:
                log(f"{png_path.name}: Nearly all transparent ({visibility_pct:.1f}% visible)", "FAIL")
                continue

            # Check color diversity (not just one flat color)
            r_std = rgb[:, :, 0].std()
            g_std = rgb[:, :, 1].std()
            b_std = rgb[:, :, 2].std()
            avg_std = (r_std + g_std + b_std) / 3

            # Check brightness distribution
            brightness = rgb.mean(axis=2)
            dark_pct = (brightness < 30).sum() / brightness.size * 100
            bright_pct = (brightness > 200).sum() / brightness.size * 100

            # Quality verdict
            if avg_std < 5:
                log(f"{png_path.name}: Low color variance (possible render failure)", "WARN")
            else:
                log(f"{png_path.name}: {w}x{h}px, visible={visibility_pct:.0f}%, variance={avg_std:.1f} ✓", "PASS")

            # Check aspect ratio is reasonable for a comment card
            if w > 0:
                aspect = h / w
                if aspect < 0.1 or aspect > 1.0:
                    log(f"{png_path.name}: Unusual aspect ratio {aspect:.2f} (w={w}, h={h})", "WARN")

        except Exception as e:
            log(f"{png_path.name}: Failed to analyze — {e}", "FAIL")


# ─── MAIN QA RUNNER ───────────────────────────────────────────────────────────

async def main():
    print("\n" + "="*60)
    print("🔍 BRAINROT VIDEO FACTORY — QA REPORT")
    print("="*60 + "\n")

    # Phase 1: Visual card rendering with Playwright
    print("\n--- Phase 1: Playwright Visual Card Tests ---")
    try:
        await test_card_html_playwright()
    except Exception as e:
        log(f"Playwright card test failed: {e}", "FAIL")
        import traceback; traceback.print_exc()

    # Phase 2: DevTools validation
    print("\n--- Phase 2: Chrome DevTools Metrics ---")
    try:
        await test_devtools_card_metrics()
    except Exception as e:
        log(f"DevTools test failed: {e}", "FAIL")

    # Phase 3: Image quality analysis
    print("\n--- Phase 3: PIL Image Quality Analysis ---")
    test_image_quality("output/jobs/qa_test/cards")

    # Phase 4: End-to-end pipeline
    print("\n--- Phase 4: End-to-End Pipeline Test ---")
    try:
        # Run in a thread to avoid nested asyncio.run() conflicts
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = loop.run_in_executor(pool, test_full_pipeline)
            modules_results, final_cfg = await future
    except Exception as e:
        log(f"E2E pipeline failed: {e}", "FAIL")
        import traceback; traceback.print_exc()
        modules_results = {}
        final_cfg = {}

    # Phase 5: Analyze final video output
    if final_cfg:
        print("\n--- Phase 5: Final Video Analysis ---")
        out_path = final_cfg.get("video", {}).get("output_path", "")
        if out_path and Path(out_path).exists():
            # Run ffprobe for detailed analysis
            import subprocess
            probe = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", out_path
            ], capture_output=True, text=True)
            if probe.returncode == 0:
                data = json.loads(probe.stdout)
                fmt = data.get("format", {})
                log(f"Video duration: {float(fmt.get('duration', 0)):.1f}s", "INFO")
                log(f"Video bitrate: {int(fmt.get('bit_rate', 0))//1000}kbps", "INFO")

                for stream in data.get("streams", []):
                    if stream["codec_type"] == "video":
                        log(f"Video stream: {stream['codec_name']} {stream['width']}x{stream['height']} @ {stream.get('avg_frame_rate', '?')}fps", "PASS")
                    elif stream["codec_type"] == "audio":
                        log(f"Audio stream: {stream['codec_name']} {stream.get('sample_rate', '?')}Hz", "PASS")

    # Final Report
    print("\n" + "="*60)
    print("📊 QA SUMMARY")
    print("="*60)

    passes = sum(1 for r in REPORT if r["status"] == "PASS")
    fails = sum(1 for r in REPORT if r["status"] == "FAIL")
    warns = sum(1 for r in REPORT if r["status"] == "WARN")

    print(f"✅ PASS: {passes}")
    print(f"❌ FAIL: {fails}")
    print(f"⚠️  WARN: {warns}")

    if modules_results:
        print("\nModule Results:")
        for mod, result in modules_results.items():
            icon = "✅" if result == "PASS" else "❌"
            print(f"  {icon} {mod}: {result}")

    # Save report
    report_path = Path("output/qa_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "summary": {"pass": passes, "fail": fails, "warn": warns},
            "modules": modules_results,
            "details": REPORT
        }, f, indent=2)
    print(f"\n📋 Full report saved: {report_path}")

    if fails > 0:
        print(f"\n⚠️  {fails} tests failed. Check report for details.")
        sys.exit(1)
    else:
        print("\n🎉 All critical tests PASSED!")

if __name__ == "__main__":
    asyncio.run(main())
