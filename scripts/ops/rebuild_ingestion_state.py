#!/usr/bin/env python3
"""
rebuild_ingestion_state.py — Rebuild bulk_ingest_state.json from Qdrant ground truth
=======================================================================================

backend/scripts/ingestion/bulk_ingest_state.json currently marks all 763 seed
URLs status="failed" (a budget-exhausted run snapshot). But IngestionCheckpoint
.is_processed() skips ANY url with a checkpoint entry present, regardless of
its status value (confirmed 2026-09-04 by reading ingest/handlers/checkpoint.py
and scripts/ingestion/bulk_ingest_video.py) — so as-is, re-running the bulk
ingest script would report "All 763 sources are already processed" and retry
NOTHING, even the ~430 URLs that genuinely never landed in Qdrant.

This script queries spiritual_wisdom_contextual directly for the real set of
successfully-ingested video_ids, then rewrites the checkpoint file to:
  - KEEP an entry (in the exact shape the real success path writes —
    {"timestamp": <epoch float>}, no "status" key) for every URL confirmed
    present in Qdrant, so it's never re-ingested/duplicated.
  - DROP the entry entirely for every URL not found in Qdrant, so
    is_processed() returns False and bulk_ingest_video.py retries it next run.

Backs up the original file before writing. Read-only against Qdrant.

Usage:
    cd /path/to/askmukthiguru  (repo root)
    python3 scripts/ops/rebuild_ingestion_state.py --dry-run
    python3 scripts/ops/rebuild_ingestion_state.py --apply
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

try:
    from qdrant_client import QdrantClient
except ImportError:
    print("ERROR: qdrant-client not installed. Run: pip install qdrant-client")
    sys.exit(1)

_repo_root = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv  # type: ignore

    for _env_path in (_repo_root / "backend" / ".env", _repo_root / ".env"):
        if _env_path.exists():
            load_dotenv(dotenv_path=_env_path, override=False)
            break
except ImportError:
    pass

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "spiritual_wisdom_contextual")
STATE_FILE = _repo_root / "backend" / "scripts" / "ingestion" / "bulk_ingest_state.json"
SEED_FILE = _repo_root / "scripts" / "ingestion" / "all_ingest_urls.txt"
DEFAULT_TENANT = "oneness"

_VIDEO_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{11})")


def extract_video_id(url: str) -> str | None:
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


def fetch_confirmed_video_ids(client: QdrantClient) -> set[str]:
    print(f"Scrolling {COLLECTION} for confirmed video_ids...")
    confirmed: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=["video_id"],
            with_vectors=False,
        )
        for p in points:
            vid = (p.payload or {}).get("video_id")
            if vid:
                confirmed.add(vid)
        if not offset:
            break
    print(f"  {len(confirmed)} distinct video_ids confirmed present in {COLLECTION}")
    return confirmed


def main(dry_run: bool) -> None:
    print("\n" + "=" * 60)
    print("Rebuild Ingestion State From Qdrant Ground Truth")
    print(f"  Qdrant: {QDRANT_URL}")
    print(f"  Collection: {COLLECTION}")
    print(f"  State file: {STATE_FILE}")
    print(f"  Dry-run: {dry_run}")
    print("=" * 60 + "\n")

    if not SEED_FILE.exists():
        print(f"ERROR: seed file not found: {SEED_FILE}")
        sys.exit(1)
    if not STATE_FILE.exists():
        print(f"ERROR: state file not found: {STATE_FILE}")
        sys.exit(1)

    seed_urls = [line.strip() for line in SEED_FILE.read_text().splitlines() if line.strip()]
    print(f"Seed list: {len(seed_urls)} URLs")

    try:
        client = QdrantClient(url=QDRANT_URL, timeout=15)
    except Exception as e:
        print(f"ERROR: cannot connect to Qdrant: {e}")
        sys.exit(1)

    confirmed_video_ids = fetch_confirmed_video_ids(client)

    lock_path = STATE_FILE.with_suffix(STATE_FILE.suffix + ".ckpt.lock")
    lock_fh = lock_path.open("a+")
    try:
        if hasattr(fcntl, "flock"):
            fcntl.flock(lock_fh, fcntl.LOCK_EX)

        old_state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        print(f"Current state file: {len(old_state)} entries (all should say status=failed)\n")

        kept, dropped, unmatched = 0, 0, 0
        new_state: dict = {}
        now = time.time()
        for url in seed_urls:
            vid = extract_video_id(url)
            key = f"tenant:{DEFAULT_TENANT}:{url}"
            if vid is None:
                unmatched += 1
                # Can't verify — preserve whatever the old file said (fail safe: never
                # silently mark an unparseable source as either done or retry-able
                # based on a guess).
                if key in old_state:
                    new_state[key] = old_state[key]
                continue
            if vid in confirmed_video_ids:
                # Real success path writes {"timestamp": ...} with no "status" key
                # (ingest/handlers/checkpoint.py:save via bulk_ingest_video.py's
                # `checkpoint.save, src` call with no metadata arg) — match that
                # shape exactly so this looks identical to an organic success entry.
                new_state[key] = {
                    "timestamp": now,
                    "verified_by": "rebuild_ingestion_state.py",
                    "verified_against": COLLECTION,
                }
                kept += 1
            else:
                dropped += 1  # omit entirely -> is_processed() returns False -> retried

        print(f"Result: {kept} confirmed-success (kept), {dropped} not-in-Qdrant (dropped, will retry), "
              f"{unmatched} unparseable URL (preserved as-is)\n")

        if dry_run:
            print("DRY-RUN: no files written.")
            print(f"Would shrink state file from {len(old_state)} to {len(new_state)} entries.")
            return

        backup_path = STATE_FILE.with_name(f"{STATE_FILE.name}.bak_{int(now)}")
        shutil.copy2(STATE_FILE, backup_path)
        print(f"Backup written: {backup_path}")

        # Atomic tempfile write with fsync + os.replace
        fd, tmp_path = tempfile.mkstemp(dir=STATE_FILE.parent, prefix=".rebuild-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(new_state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, STATE_FILE)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

        print(f"State file rewritten: {len(new_state)} entries (was {len(old_state)})")
        print("Next bulk_ingest_video.py run will retry the dropped (genuinely-missing) sources"
              " and skip the confirmed-success ones.")
    finally:
        try:
            if hasattr(fcntl, "flock"):
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
        finally:
            lock_fh.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild ingestion state from Qdrant ground truth")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("pass --dry-run or --apply")
    main(dry_run=args.dry_run)
