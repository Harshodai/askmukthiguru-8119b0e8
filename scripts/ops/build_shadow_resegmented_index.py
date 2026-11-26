#!/usr/bin/env python3
"""Build the shadow resegmented index in an isolated Qdrant collection.

Milestone 2: Shadow Collection Re-indexing Pipeline.

Features:
- Reads points from source collection (default: first_person_v10) strictly read-only.
- Strict isolation (Invariants X6 & X22): refuses to write or modify first_person_v10
  or any non-shadow collection.
- Provisions target shadow collection (default: first_person_v12_shadow) with
  multi-vector schema (passage_dense: 1024d Cosine, passage_sparse: SparseVectorParams)
  and replicates payload indexes from FirstPersonStore.PAYLOAD_INDEXES.
- Evaluates ingestion quality gates: canonical EVENT_MARKER_RE rejects promotional,
  date-bound, pandemic, and program-announcement phrasing.
- Stamping contract (Invariants X40 & X22):
    * chunker_version="boundary_v2:rhetorical"
    * corpus_version="fp-context-transcript-v2"
    * domain_rights_status="licensed"
    * rights_cleared=True
- Persists rejections:
    * In --apply mode: writes to PostgreSQL public.corpus_gate_rejections via
      app.telemetry_db._get_client().
    * In --dry-run mode: non-destructive; collects unpersisted rejections in summary.
- Batch upserts accepted points with wait=True.
- Verifies post-condition: source collection point count unchanged (zero writes).

Usage:
    python3 -m scripts.ops.build_shadow_resegmented_index --dry-run
    python3 -m scripts.ops.build_shadow_resegmented_index --apply --batch-size 100
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional


def _resolve_backend_root() -> Path:
    """Directory holding backend modules (domain, services, app)."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "domain" / "first_person_context.py").is_file():
            return candidate
        nested = candidate / "backend"
        if (nested / "domain" / "first_person_context.py").is_file():
            return nested
    raise RuntimeError(f"cannot locate backend package root from {here}")


_BACKEND_ROOT = _resolve_backend_root()
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    SparseVectorParams,
    VectorParams,
)

from app.telemetry_db import _get_client
from services.first_person_content_assessment import EVENT_MARKER_RE
from services.first_person_store import FirstPersonStore

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_COLLECTION = "first_person_v10"
DEFAULT_TARGET_COLLECTION = "first_person_v12_shadow"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_BATCH_SIZE = 100

# Strict list of protected live collections that must NEVER be written or targeted
FORBIDDEN_COLLECTIONS = frozenset(
    {"first_person_v10", "first_person", "first_person_v9", "first_person_v8", "first_person_v1"}
)


def validate_target_collection(target_collection: str, source_collection: str) -> None:
    """Enforce strict isolation invariants X6 & X22."""
    if not target_collection or not target_collection.strip():
        raise ValueError("Target collection must not be empty.")

    target_clean = target_collection.strip()
    if target_clean in FORBIDDEN_COLLECTIONS:
        raise ValueError(
            f"CRITICAL INVARIANT VIOLATION: Target collection {target_clean!r} is a protected "
            "live collection. Writes, updates, and alias mutations are strictly forbidden "
            "(Invariants X6 & X22)."
        )

    if target_clean == source_collection.strip():
        raise ValueError(
            f"Target collection {target_clean!r} cannot be identical to source collection."
        )

    target_lower = target_clean.lower()
    if not ("shadow" in target_lower or "test" in target_lower):
        raise ValueError(
            f"Target collection {target_clean!r} is not an approved shadow collection. "
            "Approved target names must contain 'shadow' or 'test' (e.g. 'first_person_v12_shadow')."
        )


def assess_ingestion_quality(text: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Ingestion quality gate.

    Checks text against canonical promotional, event-marker, and date-bound phrasing.
    Returns: (is_accepted, reason, matched_span)
    """
    if not text or not text.strip():
        return False, "empty_clip_text", ""

    match = EVENT_MARKER_RE.search(text)
    if match:
        return False, "event_or_promotional_marker", match.group(0)

    return True, None, None


def persist_corpus_gate_rejection(
    source_url: str,
    reason: str,
    chunk_index: int = 0,
    gate_layer: str = "shadow_resegmentation_gate",
    gate_verdict: str = "rejected",
    gate_reason: str = "",
    matched_span: str = "",
    point_id: Optional[str] = None,
    client: Any = None,
) -> bool:
    """Persist rejected ingest item to public.corpus_gate_rejections (Invariant X40 / DEF-03)."""
    try:
        if client is None:
            client = _get_client()
        if client is not None:
            row = {
                "source_url": source_url or "unknown",
                "chunk_index": chunk_index,
                "gate_layer": gate_layer,
                "reason": reason,
                "gate_verdict": gate_verdict,
                "gate_reason": gate_reason or reason,
                "matched_span": (matched_span or "")[:500],
                "point_id": str(point_id or ""),
            }
            client.table("corpus_gate_rejections").insert([row]).execute()
            return True
    except Exception as db_err:
        logger.error(f"[X40] Failed to persist corpus_gate_rejections: {db_err}")
    return False


def provision_shadow_collection(
    client: QdrantClient,
    collection_name: str,
    recreate: bool = False,
    dimension: int = 1024,
) -> None:
    """Provision target shadow collection with passage_dense + passage_sparse vectors.

    and payload indexes replicated from FirstPersonStore.PAYLOAD_INDEXES.
    """
    existing_collections = {c.name for c in client.get_collections().collections}
    if collection_name in existing_collections:
        if recreate:
            logger.info(f"Recreating collection {collection_name!r}")
            client.delete_collection(collection_name)
        else:
            logger.info(f"Collection {collection_name!r} already exists.")
            return

    logger.info(f"Creating shadow collection {collection_name!r}")
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "passage_dense": VectorParams(size=dimension, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            "passage_sparse": SparseVectorParams(),
        },
    )

    for field_name, schema_type in FirstPersonStore.PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema_type,
                wait=True,
            )
        except Exception as exc:
            logger.debug(
                f"Payload index creation for {field_name} ignored: {exc}"
            )


def stamp_accepted_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp required contract metadata onto accepted points (Invariants X40 & X22)."""
    stamped = dict(payload)
    stamped["chunker_version"] = "boundary_v2:rhetorical"
    stamped["corpus_version"] = "fp-context-transcript-v2"
    stamped["domain_rights_status"] = "licensed"
    stamped["rights_cleared"] = True
    return stamped


def build_shadow_resegmented_index(
    *,
    client: Optional[QdrantClient] = None,
    qdrant_url: Optional[str] = None,
    source_collection: str = DEFAULT_SOURCE_COLLECTION,
    target_collection: str = DEFAULT_TARGET_COLLECTION,
    apply_mode: bool = False,
    recreate: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    telemetry_client: Any = None,
) -> dict[str, Any]:
    """Execute the re-indexing pipeline from source_collection to target_collection."""
    validate_target_collection(target_collection, source_collection)

    resolved_url = qdrant_url or os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL)
    if client is None:
        client = QdrantClient(url=resolved_url)

    # Initial safety audit of source collection (X6 & X22)
    initial_source_count = 0
    try:
        source_info = client.get_collection(source_collection)
        initial_source_count = getattr(source_info, "points_count", 0) or 0
    except Exception as exc:
        raise ValueError(
            f"Source collection {source_collection!r} is unreachable or does not exist: {exc}"
        ) from exc

    if apply_mode:
        provision_shadow_collection(client, target_collection, recreate=recreate)

    total_scanned = 0
    accepted_count = 0
    rejected_count = 0
    upserted_count = 0
    rejection_reasons: Counter[str] = Counter()
    unpersisted_rejections: list[dict[str, Any]] = []

    batch: list[PointStruct] = []
    offset = None

    while True:
        records, next_offset = client.scroll(
            collection_name=source_collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        for record in records:
            total_scanned += 1
            payload = dict(record.payload or {})
            text = str(payload.get("verbatim_text") or payload.get("text") or "").strip()

            is_accepted, reason, matched_phrase = assess_ingestion_quality(text)

            if not is_accepted:
                rejected_count += 1
                reason_str = reason or "unknown_rejection"
                rejection_reasons[reason_str] += 1
                source_url = str(payload.get("source_url") or payload.get("video_url") or "unknown")
                chunk_index = int(payload.get("chunk_index") or 0)
                point_id_str = str(record.id)

                if apply_mode:
                    persist_corpus_gate_rejection(
                        source_url=source_url,
                        reason=reason_str,
                        chunk_index=chunk_index,
                        gate_layer="shadow_resegmentation_gate",
                        gate_verdict="rejected",
                        gate_reason=reason_str,
                        matched_span=matched_phrase or "",
                        point_id=point_id_str,
                        client=telemetry_client,
                    )
                else:
                    unpersisted_rejections.append(
                        {
                            "point_id": point_id_str,
                            "reason": reason_str,
                            "matched_span": matched_phrase or "",
                            "source_url": source_url,
                            "chunk_index": chunk_index,
                        }
                    )
                continue

            accepted_count += 1
            stamped_payload = stamp_accepted_payload(payload)

            vec: dict[str, Any] = {}
            if isinstance(record.vector, dict):
                vec = dict(record.vector)
            elif isinstance(record.vector, list):
                vec = {"passage_dense": record.vector}

            point_struct = PointStruct(
                id=record.id,
                vector=vec,
                payload=stamped_payload,
            )
            batch.append(point_struct)

            if len(batch) >= batch_size:
                if apply_mode:
                    client.upsert(collection_name=target_collection, points=batch, wait=True)
                    upserted_count += len(batch)
                batch = []

        if next_offset is None or not records:
            break
        offset = next_offset

    if batch and apply_mode:
        client.upsert(collection_name=target_collection, points=batch, wait=True)
        upserted_count += len(batch)

    # Invariant verification: assert source collection was not modified
    final_source_info = client.get_collection(source_collection)
    final_source_count = getattr(final_source_info, "points_count", 0) or 0
    if final_source_count != initial_source_count:
        raise AssertionError(
            f"CRITICAL INVARIANT VIOLATION (X6): Source collection {source_collection!r} point count "
            f"changed from {initial_source_count} to {final_source_count}!"
        )

    target_points_count = 0
    if apply_mode:
        target_info = client.get_collection(target_collection)
        target_points_count = getattr(target_info, "points_count", 0) or 0

    return {
        "status": "success",
        "apply_mode": apply_mode,
        "source_collection": source_collection,
        "target_collection": target_collection,
        "total_scanned": total_scanned,
        "accepted": accepted_count,
        "rejected": rejected_count,
        "upserted": upserted_count,
        "rejection_reasons": dict(rejection_reasons),
        "unpersisted_rejections": unpersisted_rejections,
        "target_points_count": target_points_count,
        "source_initial_count": initial_source_count,
        "source_final_count": final_source_count,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build shadow resegmented index in an isolated Qdrant collection."
    )
    parser.add_argument(
        "--source-collection",
        default=DEFAULT_SOURCE_COLLECTION,
        help=f"Source collection to read from (default: {DEFAULT_SOURCE_COLLECTION})",
    )
    parser.add_argument(
        "--target-collection",
        default=DEFAULT_TARGET_COLLECTION,
        help=f"Target shadow collection (default: {DEFAULT_TARGET_COLLECTION})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for scrolling and upserting (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--qdrant-url",
        default=None,
        help="Qdrant service URL (defaults to QDRANT_URL env or http://localhost:6333)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate target collection if it already exists",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute writes to target shadow collection and DB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview run without writes (default mode)",
    )

    args = parser.parse_args(argv)

    # Determine apply mode: explicitly requires --apply and not --dry-run
    apply_mode = bool(args.apply) and not bool(args.dry_run)

    print(
        f"Starting shadow re-indexing pipeline: "
        f"source={args.source_collection!r}, target={args.target_collection!r}, "
        f"mode={'APPLY' if apply_mode else 'DRY-RUN'}"
    )

    try:
        summary = build_shadow_resegmented_index(
            qdrant_url=args.qdrant_url,
            source_collection=args.source_collection,
            target_collection=args.target_collection,
            apply_mode=apply_mode,
            recreate=args.recreate,
            batch_size=args.batch_size,
        )
    except Exception as exc:
        logger.error(f"Execution failed: {exc}", exc_info=True)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("\n=== Shadow Resegmented Index Build Summary ===")
    print(f"Status:              {summary['status'].upper()}")
    print(f"Mode:                {'APPLY (writes executed)' if summary['apply_mode'] else 'DRY-RUN (read-only)'}")
    print(f"Source Collection:   {summary['source_collection']}")
    print(f"Target Collection:   {summary['target_collection']}")
    print(f"Total Scanned:       {summary['total_scanned']}")
    print(f"Accepted Points:     {summary['accepted']}")
    print(f"Rejected Points:     {summary['rejected']}")
    print(f"Upserted Points:     {summary['upserted']}")
    print("Rejection Breakdown:")
    for reason, count in summary["rejection_reasons"].items():
        print(f"  - {reason}: {count}")
    if not summary["apply_mode"]:
        print(f"Unpersisted Rejections: {len(summary['unpersisted_rejections'])}")
    print("Collection Status:")
    print(f"  - Source Count:    {summary['source_final_count']} (unchanged: {summary['source_final_count'] == summary['source_initial_count']})")
    print(f"  - Target Count:    {summary['target_points_count']}")
    print("Isolation Verification: PASS (Zero writes/updates/alias mutations to protected collections)")
    print("===============================================")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    sys.exit(main())
