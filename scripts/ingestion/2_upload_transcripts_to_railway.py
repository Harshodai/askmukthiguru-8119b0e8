#!/usr/bin/env python3
"""
Mukthi Guru — Phase 2: Upload Local Transcripts to Railway
==============================================================
Reads every .md transcript file written by Phase 1
(1_fetch_transcripts_local.py) — or by scripts/ingestion/extract_transcripts.py,
same output format — and forwards each one to the Railway backend's
POST /api/ingest/raw-text, which runs the rest of the pipeline there: chunk,
embed, Qdrant, RAPTOR, LightRAG, OKF.

Setup:
  1. Run Phase 1 first (or extract_transcripts.py) so .md files exist in
     scripts/ingestion/transcripts/.
  2. Get your admin access token: log into askmukthiguru.lovable.app as
     admin, open browser DevTools -> Application -> Local Storage ->
     the "sb-<project-ref>-auth-token" key -> copy the "access_token" field
     out of that JSON value. Tokens expire in ~1h — this phase is fast
     (network POSTs, not scraping), so one token is normally enough for a
     full run; re-export and re-run (resumable) if it isn't.
  3. export MUKTHI_ADMIN_TOKEN="<paste it here>"

Run:
  python3 scripts/ingestion/2_upload_transcripts_to_railway.py              # all fetched .md files
  python3 scripts/ingestion/2_upload_transcripts_to_railway.py --limit 3    # first 3, for testing

State (resumable): scripts/ingestion/upload_state.json tracks which video
IDs were already forwarded, so re-running only sends the new/failed ones.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency: pip install -r scripts/ingestion/requirements-local-fetch.txt")
    sys.exit(1)

TRANSCRIPTS_DIR = Path(os.environ.get("MUKTHI_TRANSCRIPTS_DIR", str(Path(__file__).resolve().parent / "transcripts")))
STATE_DIR = Path(os.environ.get("MUKTHI_STATE_DIR", str(Path(__file__).resolve().parent)))
STATE_FILE = STATE_DIR / "upload_state.json"
API_BASE = os.environ.get("MUKTHI_API_BASE", "https://api.askmukthiguru.com").rstrip("/")
ADMIN_TOKEN = os.environ.get("MUKTHI_ADMIN_TOKEN", "")

_FIELD_RE = re.compile(r"^\*\*([^:]+):\*\*\s*(.+)$")


def parse_transcript_md(path: Path) -> Optional[dict]:
    """Parses the `# Title` / `**Field:** value` / `## Transcript` format
    shared by 1_fetch_transcripts_local.py and extract_transcripts.py."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    fields: dict[str, str] = {}
    for line in lines:
        m = _FIELD_RE.match(line.strip())
        if m:
            fields[m.group(1).strip().lower()] = m.group(2).strip()

    video_id = fields.get("video id", "").strip("`") or path.stem
    url = fields.get("url", "") or f"https://www.youtube.com/watch?v={video_id}"

    marker = "## Transcript"
    idx = raw.find(marker)
    if idx == -1:
        return None
    text = raw[idx + len(marker):].strip()
    if not text or text == "_No transcript available._":
        return None

    return {"video_id": video_id, "url": url, "title": title or video_id, "text": text}


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"done": {}, "failed": {}}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def forward_to_railway(client: httpx.Client, item: dict) -> dict:
    resp = client.post(
        f"{API_BASE}/api/ingest/raw-text",
        json={
            "text": item["text"],
            "source_url": item["url"],
            "title": item["title"],
            "tags": ["general"],
            "max_accuracy": True,
        },
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Max files to upload (for testing)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between uploads (default 0.5)")
    args = parser.parse_args()

    if not ADMIN_TOKEN:
        print("ERROR: MUKTHI_ADMIN_TOKEN not set. See this script's docstring for how to get one.")
        sys.exit(1)

    if not TRANSCRIPTS_DIR.exists():
        print(f"ERROR: {TRANSCRIPTS_DIR} doesn't exist. Run Phase 1 first.")
        sys.exit(1)

    md_files = sorted(TRANSCRIPTS_DIR.glob("*.md"))
    if args.limit:
        md_files = md_files[: args.limit]

    state = load_state()
    print(f"\nUploading {len(md_files)} transcript(s) -> {API_BASE}/api/ingest/raw-text\n")

    ok_count = 0
    fail_count = 0
    skip_count = 0
    with httpx.Client() as client:
        for i, path in enumerate(md_files):
            item = parse_transcript_md(path)
            if not item:
                print(f"[{i + 1}/{len(md_files)}] [skip] {path.name}: unparseable or no transcript text")
                skip_count += 1
                continue

            video_id = item["video_id"]
            if video_id in state["done"]:
                print(f"[{i + 1}/{len(md_files)}] [skip] {video_id} already uploaded")
                skip_count += 1
                continue

            print(f"[{i + 1}/{len(md_files)}] {item['title']}")
            try:
                result = forward_to_railway(client, item)
                print(f"  [ok]   {video_id} -> job {result.get('job_id')}")
                state["done"][video_id] = {"job_id": result.get("job_id"), "file": path.name}
                state["failed"].pop(video_id, None)
                ok_count += 1
            except Exception as e:
                print(f"  [fail] {video_id}: {e}")
                state["failed"][video_id] = str(e)
                fail_count += 1
            save_state(state)

            if i < len(md_files) - 1:
                time.sleep(args.delay)

    print(f"\nDone. {ok_count} uploaded, {fail_count} failed, {skip_count} skipped this run.")
    print(f"State file: {STATE_FILE}")


if __name__ == "__main__":
    main()
