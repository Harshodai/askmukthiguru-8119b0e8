"""Bulk video ingestion CLI.

Usage:
    python -m scripts.ingestion.bulk_ingest_video --input /path/to/videos --workers 2
    python -m scripts.ingestion.bulk_ingest_video --input /path/to/videos --dry-run
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest.video_pipeline import VideoPipeline
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService


def discover_videos(path: str) -> list[str]:
    """List all video files under a directory or return a single file."""
    p = Path(path)
    if p.is_file():
        return [str(p)]
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}
    return [str(f) for f in p.rglob("*") if f.suffix.lower() in video_exts]


async def ingest_single(pipeline: VideoPipeline, file: str, dry_run: bool) -> dict:
    if dry_run:
        return {"file": file, "status": "dry_run"}
    try:
        result = await pipeline.ingest_video(file)
        return {
            "file": file,
            "chunks": result.chunks_ingested,
            "duration": result.duration_seconds,
            "status": result.status,
        }
    except Exception as e:
        return {"file": file, "status": "error", "error": str(e)}


async def main(input_path: str, workers: int, dry_run: bool) -> None:
    files = discover_videos(input_path)
    if not files:
        print(f"No video files found at {input_path}")
        sys.exit(1)

    print(f"Found {len(files)} video(s) at {input_path}, dry_run={dry_run}, workers={workers}")

    if dry_run:
        for f in files:
            print("  [dry-run]", f)
        return

    pipeline = VideoPipeline(
        qdrant_service=QdrantService(),
        embedding_service=EmbeddingService(),
    )

    semaphore = asyncio.Semaphore(workers)

    async def wrapped(file: str) -> dict:
        async with semaphore:
            return await ingest_single(pipeline, file, dry_run)

    # Run with progress
    results = []
    for i, coro in enumerate(asyncio.as_completed([wrapped(f) for f in files])):
        result = await coro
        results.append(result)
        done = i + 1
        total = len(files)
        status = result.get("status", "?")
        print(f"  [{done}/{total}] {Path(result['file']).name} -> {status}")

    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"Done: {ok}/{len(results)} succeeded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk video ingestion")
    parser.add_argument("--input", required=True, help="Directory or single video file")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent workers")
    parser.add_argument("--dry-run", action="store_true", help="List what would be ingested")
    args = parser.parse_args()
    asyncio.run(main(args.input, args.workers, args.dry_run))
