#!/usr/bin/env python3
"""
Mukthi Guru — Phase 1: Fetch YouTube Transcripts Locally
============================================================
Fetches every video's transcript for the 20 playlists (or a given URL) from
THIS machine — your residential IP, not Railway's flagged datacenter IP —
and writes each one as a standalone .md file. No upload here, no admin
token needed for this phase at all.

Run Phase 2 (2_upload_transcripts_to_railway.py) afterward to send the
fetched .md files to Railway for the rest of the pipeline (chunk, embed,
Qdrant, RAPTOR, LightRAG, OKF). Splitting fetch from upload means a fetch
run that takes hours isn't gated on a Supabase admin token that expires in
~1h — only the (fast) upload phase needs a fresh token.

Deliberately self-contained (no backend package import) — see
requirements-local-fetch.txt / Dockerfile.local-fetch.

Run:
  python3 scripts/ingestion/1_fetch_transcripts_local.py                 # all 20 playlists
  python3 scripts/ingestion/1_fetch_transcripts_local.py --limit 3       # first 3 videos, for testing
  python3 scripts/ingestion/1_fetch_transcripts_local.py --url "https://www.youtube.com/watch?v=BMJrDu-folk"

Output: scripts/ingestion/transcripts/<video_id>.md (gitignored), one file
per video, YAML-ish frontmatter (video_id/url/title/method/fetched_at) then
the raw transcript text. Safe to re-run — videos with an existing .md file
are skipped.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("Missing dependency: pip install -r scripts/ingestion/requirements-local-fetch.txt")
    sys.exit(1)

OUT_DIR = Path(os.environ.get("MUKTHI_TRANSCRIPTS_DIR", str(Path(__file__).resolve().parent / "transcripts")))
DEFAULT_LANGUAGES = ["en", "hi", "te", "kn", "ta", "mr"]

# Same 20 playlists as scripts/ingestion/bulk_ingest_async.py::PLAYLIST_URLS.
# Duplicated here (not imported) to keep this script dependency-free from the
# backend package — see module docstring.
PLAYLIST_URLS = [
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDt1cdrKnT1AZs4UHpFU5wo",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAVXIxzJLscsY7bdpB8vhxU",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCZoSlsJgsCRwAKSn9k1YuK",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDmh7p1PgnP-_tgUYqyXPtL",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCTBAlMLmObAThmuHcXNEOX",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYA7uSMmmEKwe0Obgz1d1jRc",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYC595WV7FBH289VgWl3b7ag",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYD-DlHYhKWl0emMFdZ1RVRS",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYASfJzL48hq1SCn2R-hgzc0",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBSc9RMV9VRiVmHaMH-O39W",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDEhRkk3-4HfMC4779U5iDU",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYASkt24BpnguWFJxbVH9msA",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAmto9MigKY42WaYh3VA9WX",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCAolwoj_qQuhhFdUiwhfpB",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBf8aBXcB4fvJBBHB4qY4Id",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAnKphMrZs9FnKHLvDp5mz9",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBi5t50biQKPGiGVy_tl5x5",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCTKE3_cQvMGNUwB4LeXXjI",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAZ4sVGeWaQwelTckkbftBt",
]


def extract_video_id(url: str) -> Optional[str]:
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None


def is_playlist_url(url: str) -> bool:
    return "list=" in url


def get_playlist_video_urls(playlist_url: str) -> list[dict]:
    """Flat-extract a playlist's videos via yt-dlp (no download)."""
    import yt_dlp

    ydl_opts = {"quiet": True, "extract_flat": True, "no_warnings": True}
    videos: list[dict] = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(playlist_url, download=False)
        except Exception as e:
            print(f"  [fail] could not expand playlist {playlist_url}: {e}")
            return []
        for entry in (result or {}).get("entries") or []:
            if entry and entry.get("id"):
                videos.append({
                    "video_id": entry["id"],
                    "url": f"https://www.youtube.com/watch?v={entry['id']}",
                    "title": entry.get("title", ""),
                })
    return videos


def fetch_transcript(video_id: str, languages: list[str]) -> tuple[Optional[str], str]:
    """Manual captions first, then auto. Returns (text_or_None, method_or_reason)."""
    api = YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
    except Exception as e:
        return None, f"list_error: {e}"

    try:
        t = transcript_list.find_manually_created_transcript(languages)
        fetched = t.fetch()
        text = " ".join(s.text for s in fetched)
        if text.strip():
            return text.strip(), "manual"
    except Exception:
        pass

    try:
        t = transcript_list.find_generated_transcript(languages)
        fetched = t.fetch()
        text = " ".join(s.text for s in fetched)
        if text.strip():
            return text.strip(), "auto"
    except Exception:
        pass

    return None, "no_transcript"


def write_transcript_md(video: dict, text: str, method: str) -> Path:
    """Same heading format scripts/ingestion/extract_transcripts.py::write_md()
    already uses, so either script's output is interchangeable with
    2_upload_transcripts_to_railway.py. This fetch path is lighter (flat
    playlist extraction only) so Channel/Published/Description aren't
    available — omitted rather than faked."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{video['video_id']}.md"
    title = video.get("title") or video["video_id"]
    content = (
        f"# {title}\n\n"
        f"**Video ID:** `{video['video_id']}`\n"
        f"**URL:** {video['url']}\n"
        f"**Method:** {method}\n"
        f"**Fetched:** {datetime.now(timezone.utc).isoformat()}\n\n"
        f"## Transcript\n\n{text}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def process_video(video: dict, languages: list[str]) -> bool:
    video_id = video["video_id"]
    out_path = OUT_DIR / f"{video_id}.md"
    if out_path.exists():
        print(f"  [skip] {video_id} already fetched ({out_path.name})")
        return True

    text, method = fetch_transcript(video_id, languages)
    if not text:
        print(f"  [fail] {video_id}: {method}")
        return False

    path = write_transcript_md(video, text, method)
    print(f"  [ok]   {video_id} ({method}, {len(text)} chars) -> {path}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="Single video or playlist URL (default: all 20 PLAYLIST_URLS)")
    parser.add_argument("--limit", type=int, default=None, help="Max videos to process (for testing)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between videos (default 1)")
    args = parser.parse_args()

    urls = [args.url] if args.url else PLAYLIST_URLS

    videos: list[dict] = []
    for url in urls:
        if is_playlist_url(url):
            print(f"Expanding playlist: {url}")
            videos.extend(get_playlist_video_urls(url))
        else:
            vid = extract_video_id(url)
            if vid:
                videos.append({"video_id": vid, "url": url, "title": ""})

    if args.limit:
        videos = videos[: args.limit]

    print(f"\nFetching {len(videos)} video(s) -> {OUT_DIR}/\n")
    ok_count = 0
    fail_count = 0
    for i, video in enumerate(videos):
        print(f"[{i + 1}/{len(videos)}] {video.get('title') or video['video_id']}")
        if process_video(video, DEFAULT_LANGUAGES):
            ok_count += 1
        else:
            fail_count += 1
        if i < len(videos) - 1:
            time.sleep(args.delay)

    print(f"\nDone. {ok_count} fetched, {fail_count} failed.")
    print(f"Next: python3 scripts/ingestion/2_upload_transcripts_to_railway.py")


if __name__ == "__main__":
    main()
