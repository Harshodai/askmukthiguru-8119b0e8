#!/usr/bin/env python3
"""Standalone operator CLI for YouTube video intelligent clipping.

Usage:
    python -m scripts.ops.youtube_clipper_cli --video path/to/video.mp4 --vtt path/to/sub.vtt [options]

Options:
    --chapters JSON_FILE    JSON file containing list of semantic chapters.
    --out DIR               Base output directory (default: 'youtube-clips/<datetime>/').
    --no-burn               Do not burn subtitles into video.
    --no-bilingual          Do not generate bilingual subtitles.
    --no-summary            Do not generate summary Markdown.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path

# Ensure backend root is on sys.path
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2] if _HERE.parents[1].name == "scripts" else _HERE.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.youtube_clipper.models import Chapter, ClipperOptions
from services.youtube_clipper.pipeline import process_chapter, validate_chapter_coverage


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone YouTube Video Intelligent Clipper")
    parser.add_argument("--video", required=True, help="Path to downloaded source MP4 video")
    parser.add_argument("--vtt", required=True, help="Path to downloaded source VTT subtitles")
    parser.add_argument("--title", default="YouTube Video", help="Source video title")
    parser.add_argument("--duration", type=float, default=0.0, help="Total video duration in seconds")
    parser.add_argument("--chapters", required=True, help="Path to JSON file containing chapter list")
    parser.add_argument("--out", default=None, help="Output directory (defaults to youtube-clips/<timestamp>)")
    parser.add_argument("--no-burn", dest="burn", action="store_false", default=True, help="Disable subtitle burn-in")
    parser.add_argument("--no-bilingual", dest="bilingual", action="store_false", default=True, help="Disable bilingual subtitles")
    parser.add_argument("--target-lang", default="zh", help="Bilingual subtitle target language code (default: zh)")
    parser.add_argument("--no-summary", dest="summary", action="store_false", default=True, help="Disable summary Markdown")
    args = parser.parse_args()

    video_path = Path(args.video)
    vtt_path = Path(args.vtt)
    if not video_path.exists():
        print(f"ERROR: Video file not found: {video_path}", file=sys.stderr)
        return 1
    if not vtt_path.exists():
        print(f"ERROR: VTT subtitle file not found: {vtt_path}", file=sys.stderr)
        return 1

    chapters_file = Path(args.chapters)
    if not chapters_file.exists():
        print(f"ERROR: Chapters JSON file not found: {chapters_file}", file=sys.stderr)
        return 1

    try:
        raw_chapters = json.loads(chapters_file.read_text(encoding="utf-8"))
        chapters = [
            Chapter(
                index=c.get("index", idx + 1),
                title=c["title"],
                start_time=float(c["start_time"]),
                end_time=float(c["end_time"]),
                summary=c.get("summary", ""),
                keywords=c.get("keywords", []),
            )
            for idx, c in enumerate(raw_chapters)
        ]
    except Exception as e:
        print(f"ERROR: Failed to parse chapters JSON: {e}", file=sys.stderr)
        return 2

    # Coverage validation if duration provided
    if args.duration > 0:
        cov = validate_chapter_coverage(chapters, args.duration)
        if not cov.is_valid:
            print("WARNING: Chapter coverage issues detected:\n  " + "\n  ".join(cov.errors), file=sys.stderr)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"youtube-clips/{timestamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    options = ClipperOptions(
        burn_subtitles=args.burn,
        translate_bilingual=args.bilingual,
        target_lang=args.target_lang,
        generate_summary=args.summary,
    )

    translator_func = None
    if options.translate_bilingual:
        try:
            from services.translation.factory import TranslationProviderFactory

            translation_service = TranslationProviderFactory.create_provider()
        except Exception as exc:
            print(f"ERROR: Could not initialize translation provider: {exc}", file=sys.stderr)
            return 3

        def translate_batch(texts: list[str]) -> list[str]:
            async def _translate() -> list[str]:
                return [
                    await translation_service.translate_text(
                        text=text,
                        source_lang="en",
                        target_lang=options.target_lang,
                    )
                    for text in texts
                ]

            return asyncio.run(_translate())

        translator_func = translate_batch

    print(f"\nProcessing {len(chapters)} chapters into: {out_dir}")
    for ch in chapters:
        print(f"  [Chapter {ch.index}] {ch.title} ({ch.start_time:.1f}s -> {ch.end_time:.1f}s)...")
        artifacts = process_chapter(
            video_path=video_path,
            vtt_path=vtt_path,
            chapter=ch,
            video_title=args.title,
            options=options,
            base_output_dir=out_dir,
            translator_func=translator_func,
        )
        print(f"    - Clip MP4: {artifacts.clip_mp4}")
        if artifacts.srt_path:
            print(f"    - SRT (zero-offset): {artifacts.srt_path}")
        if artifacts.bilingual_srt_path:
            print(f"    - Bilingual SRT: {artifacts.bilingual_srt_path}")
        if artifacts.subtitled_mp4:
            print(f"    - Subtitled MP4: {artifacts.subtitled_mp4}")
        if artifacts.summary_md:
            print(f"    - Summary MD: {artifacts.summary_md}")

    print("\n Clipping completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
