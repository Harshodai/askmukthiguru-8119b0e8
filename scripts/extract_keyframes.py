"""Extract selected still frames from a supplied product-demo video.

This utility deliberately writes only to an explicit artifact directory and never
assumes a tracked demo render or composition project exists in the repository.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

DEFAULT_SCENES = [
    ("scene_01", "00:00:04"),
    ("scene_02", "00:00:11"),
    ("scene_03", "00:00:18"),
    ("scene_04", "00:00:26"),
    ("scene_05", "00:00:35"),
    ("scene_06", "00:00:50"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract review keyframes from a supplied video.")
    parser.add_argument("video", type=Path, help="Input video path; this file is not committed or modified.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/video-review/keyframes"),
        help="Ignored output directory for generated PNG frames.",
    )
    args = parser.parse_args()
    if not args.video.is_file():
        parser.error(f"video does not exist: {args.video}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for label, timestamp in DEFAULT_SCENES:
        output = args.output_dir / f"{label}.png"
        command = [
            "ffmpeg", "-y", "-ss", timestamp, "-i", str(args.video),
            "-vframes", "1", "-q:v", "2", str(output),
        ]
        subprocess.run(command, check=True)
        print(f"{label} [{timestamp}] -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
