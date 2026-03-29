#!/usr/bin/env python3
"""
Asset Sorter — interactive CLI to classify meme images, videos, and SFX audio
into emotion-tagged folders.

Usage:
    python tools/sort_assets.py

Drop files into assets/inbox/ then run. For each file:
  - Preview opens automatically (macOS `open` command)
  - Press a key to assign emotion → file moves to correct folder
  - Video  → assets/memes/{emotion}/
  - Image  → assets/memes_img/{emotion}/
  - Audio  → assets/sfx/  OR  assets/backgrounds_music/{emotion}/
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
INBOX     = BASE_DIR / "assets" / "inbox"

EMOTIONS = {
    "1": "joy",
    "2": "surprise",
    "3": "anger",
    "4": "disgust",
    "5": "fear",
    "6": "sadness",
    "7": "neutral",
}

VIDEO_EXTS  = {".mp4", ".mov", ".avi", ".webm"}
IMAGE_EXTS  = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
AUDIO_EXTS  = {".mp3", ".wav", ".ogg", ".m4a"}

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
RED    = "\033[91m"
DIM    = "\033[2m"


def clear():
    os.system("clear")


def open_preview(path: Path):
    """Open file with system default app (macOS)."""
    try:
        subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def close_preview(path: Path):
    """Best-effort close: kill QuickTime / Preview after moving on."""
    name = path.suffix.lower()
    if name in VIDEO_EXTS:
        subprocess.run(["osascript", "-e", 'tell application "QuickTime Player" to close every document'],
                       capture_output=True)
    elif name in IMAGE_EXTS:
        subprocess.run(["osascript", "-e", 'tell application "Preview" to close every window'],
                       capture_output=True)


def get_dest(path: Path, emotion: str, audio_type: str = "sfx") -> Path:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return BASE_DIR / "assets" / "memes" / emotion / path.name
    elif ext in IMAGE_EXTS:
        return BASE_DIR / "assets" / "memes_img" / emotion / path.name
    elif ext in AUDIO_EXTS:
        if audio_type == "bgm":
            return BASE_DIR / "assets" / "backgrounds_music" / emotion / path.name
        else:
            return BASE_DIR / "assets" / "sfx" / path.name
    return BASE_DIR / "assets" / "inbox" / path.name


def file_type_label(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return f"{CYAN}VIDEO MEME{RESET}"
    elif ext in IMAGE_EXTS:
        return f"{YELLOW}IMAGE MEME{RESET}"
    elif ext in AUDIO_EXTS:
        return f"{GREEN}AUDIO{RESET}"
    return "UNKNOWN"


def ask_audio_type() -> str:
    print(f"\n  Audio type?  {BOLD}[s]{RESET} SFX meme sound   {BOLD}[b]{RESET} BGM background music")
    while True:
        ch = input("  → ").strip().lower()
        if ch in ("s", "b", ""):
            return "bgm" if ch == "b" else "sfx"


def emotion_menu() -> str:
    lines = [f"\n  {BOLD}Emotion:{RESET}"]
    for k, v in EMOTIONS.items():
        lines.append(f"    {BOLD}[{k}]{RESET} {v}")
    lines.append(f"    {BOLD}[s]{RESET} skip (keep in inbox)")
    lines.append(f"    {BOLD}[q]{RESET} quit")
    print("\n".join(lines))
    while True:
        ch = input("  → ").strip().lower()
        if ch in EMOTIONS or ch in ("s", "q"):
            return ch


def process_file(path: Path, idx: int, total: int) -> bool:
    """Returns False if user quit."""
    clear()
    ext = path.suffix.lower()
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"  {DIM}[{idx}/{total}]{RESET}  {file_type_label(path)}")
    print(f"  {BOLD}{path.name}{RESET}")
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")

    open_preview(path)

    audio_type = "sfx"
    if ext in AUDIO_EXTS:
        audio_type = ask_audio_type()

    choice = emotion_menu()

    close_preview(path)

    if choice == "q":
        return False
    if choice == "s":
        print(f"  {DIM}skipped{RESET}")
        return True

    emotion = EMOTIONS[choice]
    dest = get_dest(path, emotion, audio_type)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Handle name collision
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        i = 1
        while dest.exists():
            dest = dest.parent / f"{stem}_{i}{suffix}"
            i += 1

    shutil.move(str(path), str(dest))
    rel = dest.relative_to(BASE_DIR)
    print(f"\n  {GREEN}✓{RESET}  {path.name}  →  {BOLD}{rel}{RESET}\n")
    input("  (press Enter to continue)")
    return True


def main():
    INBOX.mkdir(parents=True, exist_ok=True)

    files = sorted(
        f for f in INBOX.iterdir()
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS
    )

    if not files:
        print(f"\n{YELLOW}Inbox trống.{RESET}")
        print(f"Drop file vào:  {BOLD}{INBOX}{RESET}")
        print("Rồi chạy lại script.\n")
        sys.exit(0)

    print(f"\n{BOLD}Asset Sorter{RESET} — {len(files)} file(s) in inbox\n")

    for i, f in enumerate(files, 1):
        if not process_file(f, i, len(files)):
            break

    clear()
    remaining = sum(1 for f in INBOX.iterdir()
                    if f.is_file() and f.suffix.lower() in VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS)
    print(f"\n{GREEN}{BOLD}Done!{RESET}  {remaining} file(s) remaining in inbox.\n")


if __name__ == "__main__":
    main()
