"""D2 span-provenance scratch end-to-end check.

Scratch-only. Never touches production collections: the collection name is
always a fresh ``d2span_scratch_<timestamp>`` and is deleted afterwards
(even on failure), mirroring ingest_e2e_scratch_check.py discipline.

What it proves, with REAL segment timing from an already-extracted video:
  1. BoundaryChunker.chunk_with_spans returns chunks parallel to spans.
  2. _resolve_chunk_timing_from_cache maps those chunks to real
     (start, end) seconds seeded into the whisperx cache.
  3. The resolved timing survives _embed_and_index onto Qdrant payloads
     (chunk_start/chunk_end present, asr_method stamped).
  4. A length-mismatched timing array is dropped (None), never guessed.
  5. ensure_timing_payload_index creates a float index on chunk_start and a
     time-range scroll filter returns the in-window points.

Usage (run from backend/):
    .venv/bin/python -m scripts.ops.d2_span_provenance_scratch_check              # dry run
    .venv/bin/python -m scripts.ops.d2_span_provenance_scratch_check --run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/scripts/ops -> backend
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.append(str(REPO_ROOT))

DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_VIDEO_ID = "cHAJiF2byzg"
SCRATCH_PREFIX = "d2span_scratch_"


def _print_plan(video_id: str, qdrant_url: str) -> None:
    print("DRY RUN -- plan (pass --run to execute):")
    print(
        f"  1. Read real segments from scripts/ingestion/corpus/{video_id}/canonical_segments.json"
    )
    print("  2. Seed them into the whisperx cache under a scratch video id (no audio re-run)")
    print("  3. chunk_with_spans + _resolve_chunk_timing_from_cache -> real (start, end)")
    print(f"  4. _embed_and_index into a fresh '{SCRATCH_PREFIX}<ts>' collection at {qdrant_url}")
    print("  5. Assert payload timing + mismatch-drop + float payload index + range scroll")
    print("  6. DELETE the scratch collection")


def _check(label: str, condition: bool, results: list) -> None:
    results.append((label, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")


def run(video_id: str, qdrant_url: str) -> int:
    import os

    os.environ["QDRANT_URL"] = qdrant_url

    from ingest.boundary_chunker import split_text_with_spans
    from ingest.pipeline import (
        EmbedIndexConfig,
        IngestionPipeline,
        _resolve_chunk_timing_from_cache,
    )
    from services.embedding_service import EmbeddingService
    from services.qdrant_service import QdrantService
    from services.whisper_local_service import (
        cache_whisperx_result,
        clear_cached_whisperx_result,
    )

    collection = f"{SCRATCH_PREFIX}{int(time.time())}"
    assert collection.startswith(SCRATCH_PREFIX), "refusing a non-scratch collection name"

    real_segments = json.loads(
        (
            REPO_ROOT / "scripts" / "ingestion" / "corpus" / video_id / "canonical_segments.json"
        ).read_text()
    )["segments"]
    assert real_segments, f"no segments for {video_id}"

    scratch_vid = f"{collection}_vid"
    cache_whisperx_result(
        scratch_vid,
        {
            "segments": [
                {"text": s["text"], "start": s["start"], "end": s["end"]}
                for s in real_segments
                if s.get("text")
            ],
            "method": "whisperx_aligned_diarized",
            "align_method": None,
        },
    )

    results: list = []
    qdrant_svc = QdrantService(collection=collection)
    qdrant_svc.init_collection()
    try:
        print("\nSpan/timing assertions:")
        full_text = " ".join(s["text"] for s in real_segments if s.get("text"))
        chunks, spans = split_text_with_spans(full_text)
        _check("chunker returned parallel chunks and spans", len(chunks) > 0, results)
        _check(
            "chunks/spans length match",
            len(chunks) == len(spans),
            results,
        )

        starts, ends, asr_method, _ = _resolve_chunk_timing_from_cache(scratch_vid, chunks)
        _check("resolver arrays align to chunks", len(starts) == len(chunks), results)
        n_timed = sum(1 for s, e in zip(starts, ends) if s is not None and e is not None)
        _check(f"real timing resolved on {n_timed}/{len(chunks)} chunks", n_timed > 0, results)
        _check(
            "timing is ordered and sane",
            all((s is None and e is None) or (0.0 <= s <= e) for s, e in zip(starts, ends)),
            results,
        )

        print("\nIndexing assertions:")
        source_url = f"https://www.youtube.com/watch?v={video_id}"
        pipeline = IngestionPipeline(qdrant_svc, EmbeddingService(), MagicMock())
        # Scratch run: never write a real Supabase kb_sources telemetry row.
        pipeline._kb_sources_disabled = True
        n = pipeline._embed_and_index(
            EmbedIndexConfig(
                chunks=list(chunks),
                source_url=source_url,
                title="D2 span-provenance scratch",
                content_type="video",
                source_type="video",
                video_id=scratch_vid,
                chunk_starts=list(starts),
                chunk_ends=list(ends),
                asr_method=asr_method,
            )
        )
        _check("chunks were indexed", n > 0, results)

        points, _ = qdrant_svc._client.scroll(
            collection_name=collection, limit=500, with_payload=True
        )
        timed = [p for p in points if p.payload.get("chunk_start") is not None]
        _check(
            f"payloads carry real chunk_start ({len(timed)}/{len(points)})", len(timed) > 0, results
        )
        _check(
            "payloads stamp asr_method",
            all(p.payload.get("asr_method") == "whisperx_aligned_diarized" for p in points),
            results,
        )

        print("\nMismatch-drop assertion:")
        n2 = pipeline._embed_and_index(
            EmbedIndexConfig(
                chunks=["A scratch teaching about stillness and the quiet mind within."],
                source_url=source_url + "#mismatch",
                title="D2 mismatch scratch",
                content_type="video",
                chunk_starts=[1.0, 2.0],  # 2 entries for 1 chunk
            )
        )
        pts2, _ = qdrant_svc._client.scroll(
            collection_name=collection, limit=500, with_payload=True
        )
        mm = [p for p in pts2 if (p.payload.get("source_url") or "").endswith("#mismatch")]
        _check(
            "mismatched array dropped to None",
            bool(mm) and mm[0].payload.get("chunk_start") is None,
            results,
        )
        assert n2 >= 0

        print("\nPayload-index assertions:")
        ok = qdrant_svc.ensure_timing_payload_index("chunk_start")
        _check("float payload index created", ok, results)
        info = qdrant_svc._client.get_collection(collection)
        indexes = (
            getattr(getattr(info, "payload_schema", None), "get", lambda *a: None)("chunk_start")
            if hasattr(getattr(info, "payload_schema", None), "get")
            else getattr(info, "payload_schema", {}).get("chunk_start")
        )
        _check(f"index visible on collection ({indexes})", indexes is not None, results)

        from qdrant_client.http.models import FieldCondition, Filter, Range

        lo = timed[0].payload["chunk_start"]
        hits, _ = qdrant_svc._client.scroll(
            collection_name=collection,
            limit=500,
            with_payload=True,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="chunk_start", range=Range(gte=float(lo), lte=float(lo) + 0.001)
                    )
                ]
            ),
        )
        _check("time-range scroll returns in-window points", len(hits) > 0, results)
    finally:
        try:
            qdrant_svc._client.delete_collection(collection)
            print(f"\nDeleted scratch collection '{collection}'")
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            print(f"\nWARNING: failed to delete scratch collection '{collection}': {exc}")
        clear_cached_whisperx_result(scratch_vid)

    passed = sum(1 for _, ok_ in results if ok_)
    print(f"\n{passed}/{len(results)} assertions passed. Collection: {collection}")
    return 0 if passed == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--video-id", default=DEFAULT_VIDEO_ID)
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    args = parser.parse_args()
    if not args.run:
        _print_plan(args.video_id, args.qdrant_url)
        return 0
    return run(args.video_id, args.qdrant_url)


if __name__ == "__main__":
    sys.exit(main())
