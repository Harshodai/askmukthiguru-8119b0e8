#!/usr/bin/env python3
"""Standalone operator CLI for YouTube Transcript acquisition.

Usage:
    python -m scripts.ops.youtube_transcript_cli --url "https://www.youtube.com/watch?v=..." [options]

Options:
    --list-subs         Only list available manual and auto subtitles without downloading.
    --lang LANG         Target language code (default: 'en').
    --out DIR           Output directory for artifacts (default: 'outputs/transcripts').
    --txt / --no-txt    Enable or disable deduplicated plain text generation (default: enabled).
    --allow-whisper     Allow fallback to Whisper if no captions exist.
    --confirm-whisper   Provide explicit consent to download audio and run Whisper.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure backend root is on sys.path
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2] if _HERE.parents[1].name == "scripts" else _HERE.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.youtube_transcript.downloader import (
    download_transcript,
    list_subtitles,
)
from services.youtube_transcript.models import (
    TranscriptDownloadRequest,
    TranscriptError,
    WhisperConsentRequiredError,
)
from services.youtube_transcript.preflight import (
    check_ytdlp_installed,
    get_ytdlp_install_instructions,
    get_ytdlp_version,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone YouTube Transcript Downloader")
    parser.add_argument("--url", required=True, help="YouTube video URL or ID")
    parser.add_argument(
        "--list-subs", action="store_true", help="List available subtitles and exit"
    )
    parser.add_argument("--lang", default="en", help="Target subtitle language (default: en)")
    parser.add_argument("--out", default="outputs/transcripts", help="Output directory")
    parser.add_argument(
        "--no-txt",
        dest="generate_txt",
        action="store_false",
        default=True,
        help="Disable plain text output",
    )
    parser.add_argument(
        "--allow-whisper", action="store_true", help="Allow Whisper fallback if subtitles missing"
    )
    parser.add_argument(
        "--confirm-whisper",
        action="store_true",
        help="Confirm audio download and Whisper processing",
    )
    args = parser.parse_args()

    if not check_ytdlp_installed():
        print("ERROR: yt-dlp is not installed or not found on PATH.", file=sys.stderr)
        inst = get_ytdlp_install_instructions()
        print(
            f"Install guidance:\n  Primary: {inst['primary']}\n  Details: {inst['official_repo']}",
            file=sys.stderr,
        )
        return 1

    ver = get_ytdlp_version()
    if ver:
        print(f"[preflight] yt-dlp version: {ver}")

    if args.list_subs:
        try:
            res = list_subtitles(args.url)
            print(f"\nSubtitles for: {res.title} [{res.video_id}]")
            print(f"  Manual subtitles ({len(res.manual_subtitles)}):")
            for t in res.manual_subtitles:
                print(f"    - {t.language_code}: {t.name}")
            print(f"  Automatic captions ({len(res.auto_subtitles)}):")
            for t in res.auto_subtitles:
                print(f"    - {t.language_code}: {t.name}")
            return 0
        except TranscriptError as e:
            print(f"ERROR: {e.message}", file=sys.stderr)
            return 2

    req = TranscriptDownloadRequest(
        url=args.url,
        target_language=args.lang,
        prefer_manual=True,
        allow_auto=True,
        allow_whisper=args.allow_whisper,
        whisper_consent=args.confirm_whisper,
        output_dir=Path(args.out),
        generate_txt=args.generate_txt,
    )

    try:
        result = download_transcript(req)
        print("\n Transcript Download Complete:")
        print(f"  Title: {result.title}")
        print(f"  Video ID: {result.video_id}")
        print(f"  Source: {result.source_type.value}")
        print(f"  Language: {result.language}")
        print(f"  VTT Artifact: {result.vtt_path}")
        if result.txt_path:
            print(f"  TXT Artifact: {result.txt_path}")
        print(f"  Stats: {result.character_count} chars, {result.line_count} lines")
        print(f"  SHA256: {result.file_sha256}")
        return 0
    except WhisperConsentRequiredError as e:
        print(f"\n[CONSENT REQUIRED] {e.message}", file=sys.stderr)
        print(
            "To proceed with Whisper transcription, pass: --allow-whisper --confirm-whisper",
            file=sys.stderr,
        )
        return 3
    except TranscriptError as e:
        print(f"ERROR [{e.code.value}]: {e.message}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
