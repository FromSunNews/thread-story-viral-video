#!/usr/bin/env python3
"""
Download & classify YouTube playlist memes into emotion folders.

Usage:
    python scripts/download_classify_memes.py
    python scripts/download_classify_memes.py --dry-run   # classify only, no download
    python scripts/download_classify_memes.py --batch 20  # classify N at a time
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLeMAp3_qNZsNogslW-2E4wLAGSHwrHFYA"
MEMES_DIR = Path(__file__).parent.parent / "assets" / "memes_emotions"
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
CLASSIFY_MODELS = [
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "minimax/minimax-m2.5:free",
    "google/gemma-3-27b-it:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "google/gemma-3-12b-it:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
]
PROGRESS_FILE = Path(__file__).parent / ".meme_download_progress.json"

EMOTION_FOLDERS = sorted([d.name for d in MEMES_DIR.iterdir() if d.is_dir()])

SYSTEM_PROMPT = f"""Bạn là AI phân loại video meme vào đúng thư mục cảm xúc.

Danh sách thư mục có sẵn:
{chr(10).join(f'- {f}' for f in EMOTION_FOLDERS)}

Với mỗi video meme (chỉ dựa vào tên video), hãy chọn thư mục PHÙ HỢP NHẤT.
Trả về ĐÚNG tên thư mục, mỗi dòng một kết quả theo format: N. folder_name"""

# ---------------------------------------------------------------------------
# Keyword-based classifier (fast, no API needed)
# ---------------------------------------------------------------------------

import re as _re

_KEYWORD_RULES: list[tuple[list[str], str]] = [
    # Surprise / shock
    (["wow", "what the", "wtf", "omg", "oh my god", "ảo", "ngỡ ngàng", "shock", "sốc",
      "không tin", "unbelievable", "really", "actually", "wait what"], "ngac_nhien"),
    # Sadness / crying
    (["crying", "cry", "why you cry", "buồn", "sad", "khóc", "tears"], "buon_dau_long"),
    # Excitement / joy
    (["funny", "laugh", "haha", "lol", "vui", "hài", "cuoi", "fun",
      "phan khích", "excited", "yay", "dance", "nhảy"], "phan_khich"),
    # Cool / sigma
    (["cool", "thug", "sigma", "chad", "slay", "swag", "ngầu"], "cool_ngau"),
    # Anger
    (["tức", "angry", "rage", "mad", "tuc gian", "điên", "grrr"], "tuc_gian"),
    # Thinking / smart
    (["thinking", "think", "thong minh", "brain", "smart", "genius",
      "suy nghĩ", "big brain", "200 iq"], "thong_minh"),
    # Awkward
    (["awkward", "cringe", "embarrass", "xấu hổ", "ngượng"], "awkward"),
    # Proud / flex
    (["good job", "well done", "proud", "tự hào", "flex", "win", "winner",
      "brent rambo", "thumbs up", "approve"], "tu_hao"),
    # No / refuse
    (["deo tin", "đéo tin", "no way", "nah", "nope", "phủ nhận",
      "reject", "deny", "không tin"], "khong_tin"),
    # Reveal / surprise plot
    (["á à", "thì ra", "plot twist", "reveal", "bí mật", "tiet lo"], "ngo_ra"),
    # Screaming / panic
    (["aaaa", "aaa", "scream", "la hét", "panic", "help", "run", "run away",
      "running", "chạy", "kinh hoàng", "terrif"], "kich_dong"),
    # Gay / LGBTQ meme
    (["im gay", "gay", "lgbt", "rainbow"], "joke_gay"),
    # NPC
    (["npc", "robot", "android", "ai meme", "bot"], "npc"),
    # Wow / Ricardo Milos (dance)
    (["ricardo", "milos", "coffin dance", "dancing coffin", "funeral",
      "astronomia"], "phan_khich"),
    # Flex / money / showing off
    (["money", "rich", "giàu", "tiền", "wealth"], "flex"),
    # Sad + nostalgic
    (["nhớ", "nostalgia", "old times", "memories", "quá khứ"], "qua_khu"),
    # Confusion
    (["confused", "huh", "kho hieu", "không hiểu", "what?", "explain"], "kho_hieu"),
    # Disappointment
    (["disappointed", "thất vọng", "sad face", "that vong"], "that_vong"),
    # Fear
    (["scared", "fear", "sợ", "so hai", "ghost", "horror", "creepy"], "so_hai"),
    # Agreement
    (["yes", "agree", "ừ", "đồng ý", "dong tinh", "right", "true"], "dong_tinh"),
    # Relatable struggle
    (["struggle", "yếu đuối", "helpless", "bat luc", "bất lực", "can't",
      "cannot", "failed"], "bat_luc"),
    # Stunned / speechless
    (["speechless", "stunned", "soc", "jaw drop", "gasp"], "soc_nang"),
    # Overthinking / delusional
    (["delulu", "overthink", "obsess", "ảo tưởng"], "delulu"),
    # Down bad
    (["down bad", "simp", "crush", "love sick", "thương"], "down_bad"),
    # Awkward/cringe
    (["awkward", "cringe", "embarrass", "xấu hổ", "ngượng", "shame"], "xau_ho"),
    # Trollface / troll / joke
    (["troll", "problem?", "u mad", "trolo"], "joke_do_mixi"),
    # Crying + laughing
    (["crying laughing", "😂", "😭", "wheeze"], "phan_khich"),
    # Thug life / don't care
    (["don't care", "dont care", "không quan tâm", "yolo", "whatever"], "khong_quan_tam"),
    # Suspicious / skeptical
    (["suspicious", "sus", "hmm", "side eye", "squint"], "kho_tin"),
    # Spiderman pointing / blame
    (["spiderman", "spider-man", "pointing", "who did", "blame"], "bi_phan_bon"),
    # Anime
    (["anime", "waifu", "kawaii", "senpai"], "phan_khich"),
    # Power up / strong
    (["power", "strong", "super", "ultra", "level up", "mạnh"], "manh_me"),
    # Mind blown
    (["mind blown", "explosion", "brain explode", "math lady", "math woman"], "ngac_nhien"),
    # Happy / wholesome
    (["happy", "smile", "wholesome", "hạnh phúc", "cute", "aww"], "phan_khich"),
    # Coffin / death
    (["coffin", "funeral", "dead", "rip", "r.i.p", "died", "death"], "buon_dau_long"),
    # Deal with it / sunglasses
    (["deal with it", "sunglasses", "thug life", "420 blaze"], "cool_ngau"),
    # This is fine / OK
    (["this is fine", "its fine", "ok this is", "fine dog"], "binh_than"),
    # Surprised pikachu
    (["pikachu", "surprised", "shock face", "open mouth"], "ngac_nhien"),
    # Flexing / showing off
    (["flex", "brag", "show off", "look at me", "boss"], "flex"),
    # Awkward look
    (["awkward look", "look away", "whistle", "không biết"], "bi_hieu_lam"),
    # Shrug
    (["shrug", "idk", "dunno", "meh", "¯\\_(ツ)_/¯"], "binh_than"),
    # FBI / police
    (["fbi", "police", "cop", "arrest", "swat", "raid"], "kich_dong"),
    # Fire / explosion
    (["fire", "explosion", "boom", "bomb", "nuke", "burn"], "kich_dong"),
    # Hope / wish
    (["hope", "wish", "please", "hy vọng", "mong"], "hy_vong"),
    # Regret
    (["regret", "hối hận", "hoi han", "mistake", "wrong"], "hoi_han"),
    # Betrayal
    (["betray", "backstab", "lừa đảo", "lua dao", "snake"], "lua_dao"),
    # Crying baby / whining
    (["baby crying", "whine", "wah", "boo hoo"], "noi_kho"),
    # Color / rainbow
    (["7 color", "rainbow color", "colour", "neon", "colorful"], "phan_khich"),
    # Slow motion / epic
    (["slow motion", "epic", "cinematic", "dramatic"], "plot_twist"),
    # A few moments later / time skip
    (["later", "moment later", "a few", "time skip", "meanwhile"], "plot_twist"),
    # Hardbass / Slav
    (["hardbass", "slav", "gopnik", "bass"], "phan_khich"),
    # Blood / violence
    (["blood", "gore", "violent", "fight", "combat", "battle"], "kich_dong"),
    # Cat meme
    (["cat meme", "cat vibing", "nyan cat", "ceiling cat", "grumpy cat"], "phan_khich"),
    # Pepe
    (["pepe", "feels good", "feels bad", "smug frog", "sad frog"], "binh_than"),
    # No reaction
    (["no reaction", "straight face", "poker face", "dead inside"], "binh_than"),
    # Oops / fail
    (["oops", "fail", "whoops", "accident", "mistake moment"], "bat_luc"),
    # Music / dance
    (["music", "song", "beat", "vibe", "groove"], "phan_khich"),
]


def _keyword_classify(title: str) -> str | None:
    """Classify based on title keywords. Returns folder name or None."""
    lower = title.lower()
    for keywords, folder in _KEYWORD_RULES:
        if any(kw in lower for kw in keywords):
            if folder in EMOTION_FOLDERS:
                return folder
    return None


# ---------------------------------------------------------------------------
# Step 1: Get playlist video list
# ---------------------------------------------------------------------------

def get_playlist_videos() -> list[dict]:
    """Fetch video id + title from playlist using yt-dlp."""
    print("Fetching playlist metadata...")
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(id)s|||%(title)s", PLAYLIST_URL],
        capture_output=True, text=True, timeout=120
    )
    videos = []
    for line in result.stdout.strip().splitlines():
        if "|||" in line:
            vid_id, title = line.split("|||", 1)
            videos.append({"id": vid_id.strip(), "title": title.strip()})
    print(f"  Found {len(videos)} videos")
    return videos


# ---------------------------------------------------------------------------
# Step 2: AI classify titles in batches
# ---------------------------------------------------------------------------

def classify_by_keywords(videos: list[dict]) -> tuple[dict[str, str], list[dict]]:
    """
    Classify using keyword rules. Returns (classified_dict, unmatched_list).
    """
    classified = {}
    unmatched = []
    for v in videos:
        folder = _keyword_classify(v["title"])
        if folder:
            classified[v["id"]] = folder
        else:
            unmatched.append(v)
    return classified, unmatched


def classify_batch(titles_with_ids: list[dict], client) -> dict[str, str]:
    """Classify a batch of videos. Returns {id: folder_name}."""
    numbered = "\n".join(
        f"{i+1}. [{v['id']}] {v['title']}"
        for i, v in enumerate(titles_with_ids)
    )
    user_prompt = (
        f"Phân loại {len(titles_with_ids)} video meme sau vào đúng thư mục cảm xúc.\n"
        f"Trả về danh sách có số thứ tự, định dạng: N. folder_name\n\n"
        f"{numbered}"
    )

    for model in CLASSIFY_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=len(titles_with_ids) * 20,
                temperature=0,
            )
            raw = resp.choices[0].message.content
            if not raw:
                continue

            # Parse "1. folder_name" lines
            results = {}
            for line in raw.strip().splitlines():
                line = line.strip()
                import re
                m = re.match(r'^(\d+)\.\s*(\S+)', line)
                if m:
                    idx = int(m.group(1)) - 1
                    folder = m.group(2).strip().rstrip('.,')
                    if 0 <= idx < len(titles_with_ids) and folder in EMOTION_FOLDERS:
                        results[titles_with_ids[idx]["id"]] = folder

            if len(results) >= len(titles_with_ids) * 0.8:  # 80% success threshold
                print(f"  Classified via {model} ({len(results)}/{len(titles_with_ids)})")
                return results
            else:
                print(f"  {model}: only {len(results)}/{len(titles_with_ids)} parsed, trying next...")
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                print(f"  {model}: rate-limited, trying next...")
            elif "404" in err:
                print(f"  {model}: not found, trying next...")
            else:
                print(f"  {model}: {err[:80]}")

    # Fallback: assign "ngac_nhien" for unclassified
    print("  WARNING: all models failed, defaulting to 'ngac_nhien'")
    return {v["id"]: "ngac_nhien" for v in titles_with_ids}


def classify_all(videos: list[dict], batch_size: int = 20) -> dict[str, str]:
    """
    Classify all videos. Strategy:
    1. Keyword rules (fast, no API)
    2. AI for unmatched titles (if API key available)
    3. Fallback: 'ngac_nhien'
    """
    # Step 1: keyword matching
    print(f"\nStep 1: Keyword classification...")
    classification, unmatched = classify_by_keywords(videos)
    print(f"  Keyword matched: {len(classification)}/{len(videos)}")
    print(f"  Need AI for: {len(unmatched)} videos")

    # Step 2: AI for unmatched
    if unmatched and OPENROUTER_KEY:
        from openai import OpenAI
        client = OpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")
        total_batches = (len(unmatched) + batch_size - 1) // batch_size
        print(f"\nStep 2: AI classification ({total_batches} batches)...")

        for i in range(0, len(unmatched), batch_size):
            batch = unmatched[i:i + batch_size]
            batch_num = i // batch_size + 1
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} videos)...")
            result = classify_batch(batch, client)
            classification.update(result)

            for v in batch[:2]:
                folder = result.get(v["id"], "?")
                print(f"    [{folder}] {v['title'][:60]}")

            if batch_num < total_batches:
                time.sleep(3)

    # Step 3: fallback → _unclassified folder for manual review
    unclassified_count = 0
    for v in videos:
        if v["id"] not in classification:
            classification[v["id"]] = "_unclassified"
            unclassified_count += 1
    if unclassified_count:
        # Create _unclassified folder
        (MEMES_DIR / "_unclassified").mkdir(exist_ok=True)
        print(f"  {unclassified_count} videos → _unclassified/ (review manually)")

    return classification


# ---------------------------------------------------------------------------
# Step 3: Download videos
# ---------------------------------------------------------------------------

def download_video(video_id: str, folder: str, dry_run: bool = False) -> bool:
    """Download a single video into the emotion folder."""
    target_dir = MEMES_DIR / folder
    target_dir.mkdir(exist_ok=True)

    # Check if already downloaded
    existing = list(target_dir.glob(f"{video_id}.*"))
    if existing:
        print(f"  SKIP (exists): {video_id} → {folder}/")
        return True

    url = f"https://www.youtube.com/watch?v={video_id}"
    if dry_run:
        print(f"  DRY-RUN: would download {video_id} → {folder}/")
        return True

    print(f"  Downloading {video_id} → {folder}/")
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "--merge-output-format", "mp4",
                "--no-playlist",
                "-o", str(target_dir / "%(id)s.%(ext)s"),
                "--no-warnings",
                "--quiet",
                url,
            ],
            timeout=180,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {video_id}")
        return False
    except Exception as e:
        print(f"  ERROR: {video_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {}


def save_progress(data: dict):
    PROGRESS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Classify only, no download")
    parser.add_argument("--batch", type=int, default=20, help="Classify batch size (default 20)")
    parser.add_argument("--no-ai", action="store_true", help="Skip AI classification (use saved progress)")
    args = parser.parse_args()

    if not OPENROUTER_KEY and not args.no_ai:
        print("ERROR: OPENROUTER_API_KEY not set in .env")
        sys.exit(1)

    # Load existing progress
    progress = load_progress()
    classification = progress.get("classification", {})

    # Step 1: Get video list
    videos = get_playlist_videos()

    # Step 2: Classify (skip already classified)
    if not args.no_ai:
        unclassified = [v for v in videos if v["id"] not in classification]
        if unclassified:
            print(f"\n{len(unclassified)} videos need classification ({len(classification)} already done)")
            new_classifications = classify_all(unclassified, batch_size=args.batch)
            classification.update(new_classifications)
            progress["classification"] = classification
            save_progress(progress)
            print(f"\nClassification saved to {PROGRESS_FILE}")
        else:
            print(f"\nAll {len(videos)} videos already classified")

    # Step 3: Download
    print(f"\n{'DRY-RUN: ' if args.dry_run else ''}Downloading {len(videos)} videos...")
    downloaded = progress.get("downloaded", [])
    failed = []

    for i, video in enumerate(videos):
        vid_id = video["id"]
        folder = classification.get(vid_id, "ngac_nhien")

        if vid_id in downloaded and not args.dry_run:
            continue

        print(f"[{i+1}/{len(videos)}] {video['title'][:50]}")
        ok = download_video(vid_id, folder, dry_run=args.dry_run)

        if ok and not args.dry_run:
            downloaded.append(vid_id)
            progress["downloaded"] = downloaded
            if i % 10 == 0:
                save_progress(progress)
        elif not ok:
            failed.append(vid_id)

    save_progress(progress)

    print(f"\n{'='*50}")
    print(f"Done! Downloaded: {len(downloaded)}, Failed: {len(failed)}")
    if failed:
        print(f"Failed IDs: {failed[:10]}{'...' if len(failed)>10 else ''}")


if __name__ == "__main__":
    main()
