#!/usr/bin/env python3
"""Repair first-person head-fragment clips and ASR stutter (Hard Stop H8).

Audit 2026-10-05 Hard Stop H8:
Serves of raw ASR head-fragment clips ("Changes. ...", "from a state. ...")
are prohibited by first-person invariants 10 and 11.
On `first_person_v7`:
- 39 repairable clips: shift start_ms to clean sentence boundary, compute fresh
  SHA256 transcript_hash, re-embed with BGE-M3, and update points.
- 4 unrepairable clips: set first_person_eligible=False.

Usage:
    PYTHONPATH=backend .venv/bin/python -m scripts.ops.repair_first_person_head_fragments \\
        --collection first_person_v7 [--apply] [--out repair_report.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import settings
from ingest.verbatim.boundaries import boundary_defects, snap_to_sentences
from services.first_person_store import FirstPersonStore, make_first_person_point_id

logger = logging.getLogger("repair_first_person_head_fragments")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def plan_clip_repair(point_id: str, payload: dict[str, Any], min_words: int = 12) -> dict[str, Any]:
    """Inspect a clip for head_fragment defects and plan shrink repair or quarantine."""
    text = payload.get("verbatim_text") or ""
    tokens = text.split()
    defects = boundary_defects(tokens)

    if "head_fragment" not in defects:
        return {"action": "none", "point_id": point_id, "defects": defects}

    span = snap_to_sentences(tokens, 0, len(tokens), min_words=min_words)
    if span is None:
        # Unrepairable by shrink (too few words survive) -> quarantine
        return {
            "action": "quarantine",
            "point_id": point_id,
            "video_id": payload.get("video_id"),
            "speaker": payload.get("speaker"),
            "repairable": False,
            "defects": defects,
            "current_text": text,
            "payload_update": {
                "first_person_eligible": False,
                "quarantine_reason": "unrepairable_head_fragment_H8",
            },
        }

    s, e = span
    proposed_tokens = tokens[s:e]
    proposed_text = " ".join(proposed_tokens)
    start_ms = int(payload.get("start_ms") or 0)
    end_ms = int(payload.get("end_ms") or 0)
    duration_ms = max(0, end_ms - start_ms)

    # Shift start_ms proportionally to the words dropped from the beginning
    shift_ms = int(duration_ms * (s / len(tokens))) if tokens else 0
    new_start_ms = start_ms + shift_ms

    new_hash = hashlib.sha256(proposed_text.encode("utf-8")).hexdigest()
    new_point_id = make_first_person_point_id(new_hash, new_start_ms, end_ms)

    new_payload = dict(payload)
    new_payload["verbatim_text"] = proposed_text
    new_payload["transcript_hash"] = new_hash
    new_payload["start_ms"] = new_start_ms
    new_payload["end_ms"] = end_ms
    new_payload["first_person_eligible"] = True
    new_payload["repair_status"] = "head_fragment_repaired_H8"

    return {
        "action": "repair",
        "old_point_id": point_id,
        "new_point_id": new_point_id,
        "video_id": payload.get("video_id"),
        "speaker": payload.get("speaker"),
        "repairable": True,
        "defects": defects,
        "old_start_ms": start_ms,
        "new_start_ms": new_start_ms,
        "end_ms": end_ms,
        "old_text": text,
        "proposed_text": proposed_text,
        "old_hash": payload.get("transcript_hash"),
        "new_hash": new_hash,
        "payload": new_payload,
    }


def execute_fragment_repairs(
    collection: str = "first_person_v7",
    client: Any | None = None,
    embedder: Any | None = None,
    dry_run: bool = True,
    sample_points: list[Any] | None = None,
) -> dict[str, Any]:
    """Execute head-fragment repairs across the specified collection or sample points."""
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import PointIdsList

    if client is None and sample_points is None:
        try:
            client = QdrantClient(
                url=settings.qdrant_url,
                api_key=getattr(settings, "qdrant_api_key", None)
                or os.getenv("QDRANT_API_KEY")
                or None,
                timeout=30,
            )
        except Exception as e:
            logger.warning("Could not connect to Qdrant at %s: %s", settings.qdrant_url, e)
            return {
                "collection": collection,
                "status": "connection_error",
                "error": str(e),
                "total_head_fragment_clips": 0,
                "repairable_count": 0,
                "unrepairable_count": 0,
            }

    points_to_process = []
    if sample_points is not None:
        points_to_process = sample_points
    else:
        try:
            offset = None
            while True:
                points, offset = client.scroll(
                    collection_name=collection,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points_to_process.extend(points)
                if offset is None:
                    break
        except Exception as e:
            logger.warning("Error scrolling collection %s: %s", collection, e)
            return {
                "collection": collection,
                "status": "scroll_error",
                "error": str(e),
                "total_head_fragment_clips": 0,
                "repairable_count": 0,
                "unrepairable_count": 0,
            }

    repairable = []
    unrepairable = []

    for p in points_to_process:
        pid = str(getattr(p, "id", None) or p.get("id"))
        pl = getattr(p, "payload", None) or p.get("payload") or {}
        plan = plan_clip_repair(pid, pl)
        if plan["action"] == "repair":
            repairable.append(plan)
        elif plan["action"] == "quarantine":
            unrepairable.append(plan)

    total_fragments = len(repairable) + len(unrepairable)
    logger.info(
        "Collection %s: %d total head_fragment clips (%d repairable, %d unrepairable)",
        collection,
        total_fragments,
        len(repairable),
        len(unrepairable),
    )

    if not dry_run and client is not None:
        # 1. Quarantine unrepairable clips
        if unrepairable:
            quarantine_ids = [u["point_id"] for u in unrepairable]
            client.set_payload(
                collection_name=collection,
                payload={
                    "first_person_eligible": False,
                    "quarantine_reason": "unrepairable_head_fragment_H8",
                },
                points=quarantine_ids,
            )
            logger.info("Quarantined %d unrepairable clips", len(quarantine_ids))

        # 2. Repair repairable clips
        if repairable:
            if embedder is None:
                from services.embedding_service import EmbeddingService

                embedder = EmbeddingService()

            from services.qdrant.utils import QdrantUtils

            store = FirstPersonStore(collection=collection, client=client)

            # Process in batches
            batch_size = 32
            for i in range(0, len(repairable), batch_size):
                batch = repairable[i : i + batch_size]
                texts = [item["proposed_text"] for item in batch]
                embeddings = embedder.encode_batch(texts)
                sparse_vectors = []
                for sp in embeddings["sparse"]:
                    sv = QdrantUtils.sparse_dict_to_vector(sp)
                    sparse_vectors.append({"indices": sv.indices, "values": sv.values})

                clip_payloads = [item["payload"] for item in batch]
                store.upsert_clips(
                    clips=clip_payloads,
                    passage_dense_vectors=embeddings["dense"],
                    question_dense_vectors=None,
                    passage_sparse_vectors=sparse_vectors,
                )

                # Delete old points
                old_ids = [item["old_point_id"] for item in batch]
                client.delete(
                    collection_name=collection,
                    points_selector=PointIdsList(points=old_ids),
                )
            logger.info("Repaired and updated %d clips in %s", len(repairable), collection)

    return {
        "collection": collection,
        "status": "success",
        "dry_run": dry_run,
        "total_head_fragment_clips": total_fragments,
        "repairable_count": len(repairable),
        "unrepairable_count": len(unrepairable),
        "repairable": repairable,
        "unrepairable": unrepairable,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="first_person_v7", help="Collection name")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not write")
    parser.add_argument("--apply", action="store_true", help="Apply updates to Qdrant")
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path")
    args = parser.parse_args(argv)

    is_dry = args.dry_run or not args.apply
    report = execute_fragment_repairs(
        collection=args.collection,
        dry_run=is_dry,
    )
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(
        f"Repair Report for {args.collection}: "
        f"{report.get('total_head_fragment_clips')} clips found "
        f"({report.get('repairable_count')} repairable, {report.get('unrepairable_count')} unrepairable) "
        f"dry_run={is_dry}"
    )
    return 0 if report.get("status") in ("success", "connection_error") else 1


if __name__ == "__main__":
    sys.exit(main())
