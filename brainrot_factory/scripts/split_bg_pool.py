#!/usr/bin/env python3
"""
split_bg_pool.py

Splits a long background video (e.g. minecraft parkour) into a pool of short clips.
Pools live in:
  assets/backgrounds/pool/1min/
  assets/backgrounds/pool/2min/
  assets/backgrounds/pool/3min/

Usage:
  python split_bg_pool.py --input <video.mp4> [--durations 60 120 180]

Clip picker (for use in other scripts):
  from scripts.split_bg_pool import pick_clips
  clips = pick_clips(duration_seconds=60, target_total=300)
  # returns a list of clip paths that loop/rotate to fill ~300 seconds
"""

import argparse
import math
import os
import random
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
POOL_DIR = PROJECT_DIR / "assets" / "backgrounds" / "pool"

DURATION_LABELS = {60: "1min", 120: "2min", 180: "3min"}


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

def get_video_duration(path: Path) -> float:
    """Return video duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def split_video(input_path: Path, clip_duration: int, output_dir: Path):
    """
    Split input_path into non-overlapping clips of clip_duration seconds.
    Clips are named clip_0001.mp4, clip_0002.mp4, …
    Skips clips that already exist (safe to re-run).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    total = get_video_duration(input_path)
    n_clips = int(total // clip_duration)

    if n_clips == 0:
        print(f"  [WARN] Video is shorter than {clip_duration}s — no clips created.")
        return

    print(f"  Splitting into {n_clips} clips of {clip_duration}s …")

    for i in range(n_clips):
        out_file = output_dir / f"clip_{i+1:04d}.mp4"
        if out_file.exists():
            print(f"    skip {out_file.name} (already exists)")
            continue

        start = i * clip_duration
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", str(input_path),
                "-t", str(clip_duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac",
                "-avoid_negative_ts", "make_zero",
                str(out_file),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"    created {out_file.name}")

    print(f"  Done — {n_clips} clips in {output_dir}")


def build_pools(input_path: Path, durations: list[int]):
    """Split input video into all requested duration pools."""
    print(f"\nSource: {input_path}")
    total = get_video_duration(input_path)
    print(f"Total duration: {total:.1f}s ({total/60:.1f} min)\n")

    for dur in durations:
        label = DURATION_LABELS.get(dur, f"{dur}s")
        out_dir = POOL_DIR / label
        print(f"[{label}] → {out_dir}")
        split_video(input_path, dur, out_dir)


# ---------------------------------------------------------------------------
# Clip picker (used by video assembly pipeline)
# ---------------------------------------------------------------------------

def list_pool(duration_seconds: int) -> list[Path]:
    """Return all clip paths in the matching pool, sorted."""
    label = DURATION_LABELS.get(duration_seconds)
    if label is None:
        raise ValueError(
            f"duration_seconds must be one of {list(DURATION_LABELS.keys())}, got {duration_seconds}"
        )
    pool_dir = POOL_DIR / label
    if not pool_dir.exists():
        raise FileNotFoundError(
            f"Pool '{label}' not found at {pool_dir}. "
            "Run split_bg_pool.py first."
        )
    clips = sorted(pool_dir.glob("clip_*.mp4"))
    if not clips:
        raise FileNotFoundError(f"No clips found in {pool_dir}")
    return clips


def pick_clips(
    duration_seconds: int,
    target_total: float,
    shuffle: bool = True,
    seed: int | None = None,
) -> list[Path]:
    """
    Return an ordered list of clip paths whose combined duration fills
    target_total seconds.  Rotates through the pool as many times as needed;
    never repeats a clip until the whole pool has been used (round-robin).

    Args:
        duration_seconds: clip length to draw from (60, 120, or 180)
        target_total:     total seconds of background needed
        shuffle:          randomise pool order each round-trip
        seed:             fix random seed for reproducibility

    Returns:
        List of Path objects — concatenate these to fill target_total.
    """
    pool = list(list_pool(duration_seconds))
    if seed is not None:
        random.seed(seed)

    n_needed = math.ceil(target_total / duration_seconds)
    result: list[Path] = []

    while len(result) < n_needed:
        round_pool = pool[:]
        if shuffle:
            random.shuffle(round_pool)
        result.extend(round_pool)

    return result[:n_needed]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Split a long background video into pooled short clips."
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        type=Path,
        help="Path to the source video (e.g. minecraft_parkour.mp4)",
    )
    parser.add_argument(
        "--durations", "-d",
        nargs="+",
        type=int,
        default=[60, 120, 180],
        metavar="SECONDS",
        help="Clip durations to generate (default: 60 120 180)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    build_pools(args.input, args.durations)


if __name__ == "__main__":
    main()
