#!/usr/bin/env python3
"""
Mukthi Guru — Batched Local Transcription & Railway Ingestion Pipeline
========================================================================
Orchestrates the complete split-pipeline end-to-end:
1. Runs local transcript fetching on your residential machine (bypassing
   Railway datacenter IP blocking) for each playlist.
2. Identifies and parses speaker metadata (Sri Preethaji / Sri Krishnaji).
3. Immediately pushes each playlist's batch of transcripts to Railway
   (/api/ingest/raw-text) as soon as the playlist finishes fetching,
   rather than waiting hours for all 20 playlists to complete first.
4. Railway Celery workers asynchronously chunk, embed, index into Qdrant,
   generate RAPTOR summaries, extract LightRAG knowledge graph, and
   materialize OKF entities into Neo4j.
5. Manages auth tokens gracefully: if MUKTHI_ADMIN_TOKEN expires mid-run,
   the script pauses cleanly, preserving state, and resumes without rework.

Usage:
  # Test with first 2 videos per playlist:
  python3 scripts/ingestion/run_batched_ingestion_pipeline.py --limit-per-playlist 2

  # Full 20-playlist execution:
  export MUKTHI_ADMIN_TOKEN="<your_admin_token>"
  python3 scripts/ingestion/run_batched_ingestion_pipeline.py

  # Single playlist or custom URL:
  python3 scripts/ingestion/run_batched_ingestion_pipeline.py --url "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDt1cdrKnT1AZs4UHpFU5wo"
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

# Load sibling scripts dynamically
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

fetch_spec = importlib.util.spec_from_file_location("fetch_module", SCRIPT_DIR / "1_fetch_transcripts_local.py")
fetch_mod = importlib.util.module_from_spec(fetch_spec)
fetch_spec.loader.exec_module(fetch_mod)

upload_spec = importlib.util.spec_from_file_location("upload_module", SCRIPT_DIR / "2_upload_transcripts_to_railway.py")
upload_mod = importlib.util.module_from_spec(upload_spec)
upload_spec.loader.exec_module(upload_mod)

PLAYLIST_URLS = fetch_mod.PLAYLIST_URLS
fetch_playlist_transcripts = fetch_mod.fetch_playlist_transcripts
process_video = fetch_mod.process_video
extract_video_id = fetch_mod.extract_video_id
is_playlist_url = fetch_mod.is_playlist_url
DEFAULT_LANGUAGES = fetch_mod.DEFAULT_LANGUAGES

upload_batch_to_railway = upload_mod.upload_batch_to_railway
API_BASE = upload_mod.API_BASE
TRANSCRIPTS_DIR = fetch_mod.OUT_DIR

BATCH_STATE_FILE = SCRIPT_DIR / "batched_pipeline_state.json"


def load_pipeline_state() -> dict:
    if BATCH_STATE_FILE.exists():
        try:
            return json.loads(BATCH_STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "completed_playlists": [],
        "in_progress_playlist": None,
        "total_fetched": 0,
        "total_uploaded": 0,
        "total_failed": 0,
    }


def save_pipeline_state(state: dict) -> None:
    tmp = BATCH_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(BATCH_STATE_FILE)


def run_pipeline(
    playlist_urls: list[str],
    limit_per_playlist: int | None = None,
    api_base: str = API_BASE,
    admin_token: str = "",
    delay_fetch: float = 0.75,
    delay_upload: float = 0.5,
    dry_run_upload: bool = False,
    enable_whisper_fallback: bool = False,
) -> None:
    state = load_pipeline_state()
    total_playlists = len(playlist_urls)

    print("=" * 70)
    print(f"🚀 MUKTHI GURU: BATCHED LOCAL FETCH & RAILWAY INGESTION PIPELINE")
    print(f"   Playlists to process: {total_playlists}")
    print(f"   Target Railway API:   {api_base}")
    print(f"   Transcripts directory: {TRANSCRIPTS_DIR}")
    print(f"   Whisper fallback:     {enable_whisper_fallback}")
    print("=" * 70)

    grand_fetched = state.get("total_fetched", 0)
    grand_uploaded = state.get("total_uploaded", 0)
    grand_failed = state.get("total_failed", 0)

    for p_idx, playlist_url in enumerate(playlist_urls, start=1):
        if playlist_url in state.get("completed_playlists", []):
            print(f"\n[{p_idx}/{total_playlists}] ⏩ Playlist already completed in previous run: {playlist_url}")
            continue

        print(f"\n{'━' * 70}")
        print(f"📦 [Playlist {p_idx}/{total_playlists}] Starting Local Fetch: {playlist_url}")
        print(f"{'━' * 70}")

        state["in_progress_playlist"] = playlist_url
        save_pipeline_state(state)

        # Step A: Local fetch on residential machine
        if is_playlist_url(playlist_url):
            ok_c, fail_c, videos = fetch_playlist_transcripts(
                playlist_url,
                limit=limit_per_playlist,
                delay=delay_fetch,
                languages=DEFAULT_LANGUAGES,
                enable_whisper_fallback=enable_whisper_fallback,
            )
            vids = [v["video_id"] for v in videos]
        else:
            vid = extract_video_id(playlist_url)
            if vid:
                video = {"video_id": vid, "url": playlist_url, "title": "", "speaker": "Unknown"}
                if process_video(video, DEFAULT_LANGUAGES, enable_whisper_fallback=enable_whisper_fallback):
                    ok_c, fail_c, vids = 1, 0, [vid]
                else:
                    ok_c, fail_c, vids = 0, 1, [vid]
            else:
                print(f"  [error] Invalid URL: {playlist_url}")
                continue

        grand_fetched += ok_c
        grand_failed += fail_c

        # Step A.5: Autonomous Ingestion Subagent Review & Manifest Sealing
        try:
            from scripts.ingestion.ingestion_subagent import IngestionSubagent
            subagent = IngestionSubagent()
            corpus_base = REPO_ROOT / "scripts" / "ingestion" / "corpus"
            for v_id in vids:
                pkg_path = corpus_base / v_id
                if pkg_path.is_dir():
                    res = subagent.review_and_seal_package(pkg_path)
                    print(f"  🤖 [subagent] Audited {v_id}: status={res.status}, ledger_entries={res.ledger_entries_count}")
        except Exception as e:
            print(f"  ⚠️ [subagent] Subagent review warning: {e}")

        # Step B: Immediate Batch Upload to Railway for this playlist
        target_md_files = [TRANSCRIPTS_DIR / f"{v_id}.md" for v_id in vids if (TRANSCRIPTS_DIR / f"{v_id}.md").exists()]
        print(f"\n📤 [Playlist {p_idx}/{total_playlists}] Pushing {len(target_md_files)} transcript(s) to Railway...")

        if dry_run_upload:
            print("  [dry run] Upload skipped due to --dry-run-upload flag.")
            up_ok, up_fail, up_skip = len(target_md_files), 0, 0
        else:
            if not admin_token:
                print("\n⚠️  MUKTHI_ADMIN_TOKEN is empty! Cannot upload batch to Railway.")
                print("   Please export MUKTHI_ADMIN_TOKEN and run again to resume.")
                sys.exit(1)

            up_ok, up_fail, up_skip, expired = upload_batch_to_railway(
                target_md_files,
                api_base=api_base,
                admin_token=admin_token,
                delay=delay_upload,
            )

            if expired:
                print("\n" + "!" * 70)
                print("⚠️  MUKTHI_ADMIN_TOKEN has expired or is unauthorized!")
                print("   Current progress has been saved in batched_pipeline_state.json.")
                print("   1. Log into https://askmukthiguru.lovable.app")
                print("   2. Copy fresh access_token from DevTools -> LocalStorage")
                print("   3. export MUKTHI_ADMIN_TOKEN='<fresh_token>'")
                print("   4. Re-run this script to resume instantly.")
                print("!" * 70)
                sys.exit(2)

        grand_uploaded += up_ok

        print(f"✅ [Playlist {p_idx}/{total_playlists}] Batch Finished: {ok_c} fetched, {up_ok} uploaded, {up_skip} already-done, {fail_c + up_fail} failed.")

        # Mark playlist complete
        if playlist_url not in state["completed_playlists"]:
            state["completed_playlists"].append(playlist_url)
        state["in_progress_playlist"] = None
        state["total_fetched"] = grand_fetched
        state["total_uploaded"] = grand_uploaded
        state["total_failed"] = grand_failed
        save_pipeline_state(state)

    print("\n" + "=" * 70)
    print("🎉 ALL PLAYLIST BATCHES PROCESSED SUCCESSFULLY!")
    print(f"   Total Fetched:  {grand_fetched}")
    print(f"   Total Uploaded: {grand_uploaded}")
    print(f"   Total Failed:   {grand_failed}")
    print(f"   State file:     {BATCH_STATE_FILE}")
    print("=" * 70)


def main() -> None:
    # Ponytail: self-check when invoked with --self-check
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        print("Running Ponytail self-check on batched pipeline orchestrator...")
        assert len(PLAYLIST_URLS) == 20
        assert is_playlist_url(PLAYLIST_URLS[0]) is True
        assert extract_video_id("https://www.youtube.com/watch?v=BMJrDu-folk") == "BMJrDu-folk"
        state = load_pipeline_state()
        assert isinstance(state, dict)
        print("✅ Ponytail pipeline orchestrator self-check passed!")
        sys.exit(0)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="Process single playlist or video URL instead of all 20")
    parser.add_argument("--limit-per-playlist", type=int, default=None, help="Max videos per playlist (useful for test runs)")
    parser.add_argument("--api-base", default=API_BASE, help=f"Railway API base URL (default {API_BASE})")
    parser.add_argument("--delay-fetch", type=float, default=0.75, help="Delay between local fetches in seconds")
    parser.add_argument("--delay-upload", type=float, default=0.5, help="Delay between Railway uploads in seconds")
    parser.add_argument("--dry-run-upload", action="store_true", help="Fetch locally but do not upload to Railway")
    parser.add_argument("--enable-whisper-fallback", action="store_true", help="Download audio and use local Whisper for videos without captions")
    args = parser.parse_args()

    token = os.environ.get("MUKTHI_ADMIN_TOKEN", "").strip()
    if not token and not args.dry_run_upload:
        print("Note: MUKTHI_ADMIN_TOKEN is not currently exported in your environment.")
        print("If you only want to test local fetching, use: --dry-run-upload")
        print("Otherwise, export MUKTHI_ADMIN_TOKEN before running for live upload.")

    urls = [args.url] if args.url else PLAYLIST_URLS

    run_pipeline(
        playlist_urls=urls,
        limit_per_playlist=args.limit_per_playlist,
        api_base=args.api_base,
        admin_token=token,
        delay_fetch=args.delay_fetch,
        delay_upload=args.delay_upload,
        dry_run_upload=args.dry_run_upload,
        enable_whisper_fallback=args.enable_whisper_fallback,
    )


if __name__ == "__main__":
    main()
