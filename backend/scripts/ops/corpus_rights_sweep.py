#!/usr/bin/env python3
"""Corpus rights sweep: find spans whose source is not cleared, optionally mark them revoked.

Scrolls the active Qdrant collection and asks the rights register whether each span's
source is cleared. The register is the one the serving path and the builders use
(``services.qdrant.indexer.resolve_source_rights_status``, backed by the manifest at
``first_person_serving_contract.RIGHTS_MANIFEST_RELPATH``). ``docs/rights/CONTENT-RIGHTS.md``
is a prose table of owner statements, not machine-readable, so it is NOT parsed here.

Default is a dry run. With --owner-approve it sets ``domain_rights_status="revoked"`` and
``rights_cleared=False`` on the uncleared spans. It never deletes.

Usage:
    python scripts/ops/corpus_rights_sweep.py \\
        [--url URL] [--collection NAME] [--max-revoke-fraction 0.5] [--owner-approve]

X22: Qdrant writes ONLY with --owner-approve. Default is a dry run.
X40: a source missing from the register is unverified, never licensed.
Refuses to write when the register is empty or when it would revoke more than
--max-revoke-fraction of the collection (a register that failed to load must not revoke
the whole corpus).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

try:
    from qdrant_client import QdrantClient
except ImportError:
    print("ERROR: qdrant-client not installed.", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_BATCH = 250
_WRITE_BATCH = 100


def _find_backend() -> Path:
    """Locate the backend package root whether run from backend/scripts/ops or scripts/ops."""
    here = Path(__file__).resolve()
    for root in (here.parents[2], here.parents[2] / "backend"):
        if (root / "services" / "qdrant" / "indexer.py").is_file():
            return root
    logger.error("Cannot locate backend/services/qdrant/indexer.py from %s", here)
    sys.exit(1)


def load_resolver():
    """Return (resolve_source_rights_status, cleared_register_size)."""
    backend = _find_backend()
    sys.path.insert(0, str(backend))
    try:
        from services.qdrant import indexer
    except ImportError as exc:
        logger.error("Cannot import the rights resolver from %s: %s", backend, exc)
        sys.exit(1)
    try:
        register = indexer._load_rights_register()
    except Exception as exc:  # RightsRegisterUnavailable and any import-time failure
        logger.error("Rights register unreadable: %s", exc)
        sys.exit(1)
    cleared = sum(1 for is_cleared in register.values() if is_cleared)
    logger.info("Rights register: %d keys, %d cleared.", len(register), cleared)
    return indexer.resolve_source_rights_status, cleared


def sweep(
    url: str,
    collection: str,
    *,
    owner_approve: bool,
    max_revoke_fraction: float,
) -> None:
    resolve, cleared = load_resolver()
    if cleared == 0:
        logger.error("Rights register has no cleared entries; refusing to sweep (X40).")
        sys.exit(1)

    client = QdrantClient(url=url, timeout=60)
    try:
        info = client.get_collection(collection)
        logger.info("Collection '%s': %d declared points.", collection, info.points_count)
    except Exception as exc:
        logger.error("Cannot reach collection '%s' at %s: %s", collection, url, exc)
        sys.exit(1)

    uncleared: dict[str, list[str]] = defaultdict(list)  # video_id -> point ids
    unidentified: list[str] = []  # no video_id and no source_url: reported, never revoked
    total_seen = 0
    offset = None
    while True:
        result, next_offset = client.scroll(
            collection_name=collection,
            limit=_BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not result:
            break
        for point in result:
            total_seen += 1
            payload = point.payload or {}
            if payload.get("domain_rights_status") == "revoked":
                continue
            video_id = str(payload.get("video_id") or "")
            source_url = str(payload.get("source_url") or "")
            if not video_id and not source_url:
                unidentified.append(str(point.id))
                continue
            if resolve(source_url=source_url, video_id=video_id or None) != "licensed":
                uncleared[video_id or source_url].append(str(point.id))
        if next_offset is None:
            break
        offset = next_offset

    total_uncleared = sum(len(ids) for ids in uncleared.values())
    logger.info(
        "Scanned %d points: %d uncleared across %d sources, %d without any source identity.",
        total_seen,
        total_uncleared,
        len(uncleared),
        len(unidentified),
    )
    if unidentified:
        print(f"\n{len(unidentified)} points carry neither video_id nor source_url (not revoked).")
    if not uncleared:
        print("All identifiable spans resolve to a cleared source.")
        return

    print(f"\nSpans whose source is NOT cleared ({total_uncleared} total):")
    for source, ids in sorted(uncleared.items(), key=lambda item: -len(item[1])):
        print(f"  {source}: {len(ids)} spans")

    if not owner_approve:
        print(
            f"\nDRY RUN: re-run with --owner-approve to mark {total_uncleared} spans revoked."
            "\nNo Qdrant writes made. (X22)"
        )
        return

    fraction = total_uncleared / max(total_seen, 1)
    if fraction > max_revoke_fraction:
        logger.error(
            "Refusing to revoke %.1f%% of the collection (limit %.1f%%). Check the rights "
            "register before raising --max-revoke-fraction.",
            fraction * 100,
            max_revoke_fraction * 100,
        )
        sys.exit(1)

    point_ids = [pid for ids in uncleared.values() for pid in ids]
    written = 0
    failed = 0
    for i in range(0, len(point_ids), _WRITE_BATCH):
        batch_ids = point_ids[i : i + _WRITE_BATCH]
        try:
            client.set_payload(
                collection_name=collection,
                payload={"domain_rights_status": "revoked", "rights_cleared": False},
                points=batch_ids,
                wait=True,
            )
            written += len(batch_ids)
            logger.info("Marked %d/%d spans revoked.", written, len(point_ids))
        except Exception as exc:
            failed += len(batch_ids)
            logger.error("Failed to mark batch %d-%d revoked: %s", i, i + len(batch_ids), exc)
    print(f"\nMarked {written}/{len(point_ids)} spans revoked ({failed} failed).")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument(
        "--collection",
        default=os.environ.get("FIRST_PERSON_ACTIVE_COLLECTION", "first_person"),
    )
    parser.add_argument(
        "--max-revoke-fraction",
        type=float,
        default=0.5,
        help="Refuse to write if more than this fraction of points would be revoked.",
    )
    parser.add_argument(
        "--owner-approve",
        action="store_true",
        help="Actually write the revocation to Qdrant (X22: required for writes).",
    )
    args = parser.parse_args()
    sweep(
        args.url,
        args.collection,
        owner_approve=args.owner_approve,
        max_revoke_fraction=args.max_revoke_fraction,
    )


if __name__ == "__main__":
    main()
