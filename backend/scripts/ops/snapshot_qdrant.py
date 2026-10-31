#!/usr/bin/env python3
"""snapshot_qdrant.py — Qdrant Snapshot Lifecycle and Observability Tool.

Creates, lists, and restores collection snapshots with --dry-run support and
updates the QDRANT_SNAPSHOT_AGE_HOURS Prometheus metric.

Usage:
    python -m scripts.ops.snapshot_qdrant --collection spiritual_wisdom_contextual --list
    python -m scripts.ops.snapshot_qdrant --collection spiritual_wisdom_contextual --create --dry-run
    python -m scripts.ops.snapshot_qdrant --collection spiritual_wisdom_contextual --create
    python -m scripts.ops.snapshot_qdrant --collection spiritual_wisdom_contextual --restore <snapshot_name> --into-collection scratch_restore --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
if (_HERE.parents[2] / "backend").is_dir():
    _BACKEND = _HERE.parents[2] / "backend"
else:
    _BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from qdrant_client import QdrantClient

from app.config import settings
from app.metrics import QDRANT_SNAPSHOT_AGE_HOURS

logger = logging.getLogger("snapshot_qdrant")


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _get_qdrant_client(
    qdrant_url: Optional[str] = None, api_key: Optional[str] = None
) -> tuple[QdrantClient, str]:
    """Build QdrantClient with explicit container/host URL fallback.

    Rewriting `qdrant` to `localhost` is opt-in: inside a container with broken
    DNS it silently targets a *different instance* than the operator named, so
    it requires `QDRANT_ALLOW_LOCALHOST_FALLBACK=true`.
    """
    url = (
        qdrant_url
        or os.environ.get("QDRANT_URL")
        or getattr(settings, "qdrant_url", "http://localhost:6333")
    )
    if "://qdrant:" in url:
        import socket

        try:
            socket.gethostbyname("qdrant")
        except socket.gaierror:
            if os.environ.get("QDRANT_ALLOW_LOCALHOST_FALLBACK", "").strip().lower() not in (
                "1",
                "true",
                "yes",
            ):
                raise RuntimeError(
                    f"cannot resolve host 'qdrant' from {url!r}; refusing to silently retarget "
                    "the run at localhost. Fix networking, or set "
                    "QDRANT_ALLOW_LOCALHOST_FALLBACK=true to opt in."
                )
            logger.warning("Host 'qdrant' unresolvable; falling back to localhost (opt-in)")
            url = url.replace("://qdrant:", "://localhost:")

    key = (
        api_key
        or os.environ.get("QDRANT_API_KEY")
        or getattr(settings, "qdrant_api_key", None)
        or None
    )
    return QdrantClient(url=url, api_key=key, timeout=120), url


def _parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO datetime string to UTC aware datetime."""
    dt_clean = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(dt_clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def list_collection_snapshots(
    client: QdrantClient, collection_name: str, update_metric: bool = True
) -> list[dict[str, Any]]:
    """List snapshots for a collection and optionally update snapshot age metric."""
    snapshots = client.list_snapshots(collection_name)
    now = datetime.now(tz=UTC)
    results: list[dict[str, Any]] = []
    newest_dt: Optional[datetime] = None

    for s in snapshots:
        name = getattr(s, "name", str(s))
        creation_time_str = getattr(s, "creation_time", None)
        size_bytes = getattr(s, "size", 0)
        checksum = getattr(s, "checksum", None)

        dt = None
        age_hours = -1.0
        if creation_time_str:
            try:
                dt = _parse_iso_datetime(creation_time_str)
                age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
                if newest_dt is None or dt > newest_dt:
                    newest_dt = dt
            except Exception:
                pass

        results.append(
            {
                "name": name,
                "creation_time": creation_time_str,
                "size_mb": round(size_bytes / (1024 * 1024), 2) if size_bytes else 0.0,
                "checksum": checksum,
                "age_hours": round(age_hours, 2) if age_hours >= 0 else None,
            }
        )

    if update_metric:
        if newest_dt is not None:
            newest_age_hours = max(0.0, (now - newest_dt).total_seconds() / 3600.0)
            QDRANT_SNAPSHOT_AGE_HOURS.labels(collection=collection_name).set(newest_age_hours)
        elif not snapshots:
            # No snapshots recorded
            QDRANT_SNAPSHOT_AGE_HOURS.labels(collection=collection_name).set(9999.0)

    # Sort descending by creation time
    results.sort(key=lambda x: str(x.get("creation_time") or ""), reverse=True)
    return results


def create_collection_snapshot(
    client: QdrantClient, collection_name: str, dry_run: bool = False
) -> dict[str, Any]:
    """Create a new collection snapshot or report dry run."""
    now = datetime.now(tz=UTC)
    if dry_run:
        simulated_name = f"{collection_name}-dryrun-{now.strftime('%Y-%m-%d-%H-%M-%S')}.snapshot"
        logger.info(
            "[DRY-RUN] Would create snapshot for collection %s: %s", collection_name, simulated_name
        )
        return {
            "status": "dry_run",
            "collection": collection_name,
            "snapshot_name": simulated_name,
            "created_at": now.isoformat(),
        }

    logger.info("Triggering snapshot creation on collection: %s", collection_name)
    snap_desc = client.create_snapshot(collection_name=collection_name)
    snap_name = getattr(snap_desc, "name", str(snap_desc))

    # Fresh snapshot age is 0.0 hours
    QDRANT_SNAPSHOT_AGE_HOURS.labels(collection=collection_name).set(0.0)

    return {
        "status": "created",
        "collection": collection_name,
        "snapshot_name": snap_name,
        "created_at": now.isoformat(),
        "details": str(snap_desc),
    }


def restore_collection_snapshot(
    client: QdrantClient,
    collection_name: str,
    snapshot_name: str,
    into_collection: Optional[str] = None,
    dry_run: bool = False,
    allow_overwrite: bool = False,
) -> dict[str, Any]:
    """Restore a collection snapshot into an explicit, distinct target collection.

    A restore is destructive: Qdrant's recover_snapshot overwrites the target
    collection. Refusing the three defaults that used to make that dangerous:
      * target defaults to the live source collection;
      * `snapshot_name` may be an arbitrary URL (`http://…`) — a remote location
        the operator never vetted;
      * the target may already hold serving data.
    """
    if not into_collection:
        raise ValueError(
            "restore requires an explicit --into-collection; refusing to overwrite the "
            "live collection by default"
        )

    target = into_collection
    if target == collection_name:
        raise ValueError(
            f"refusing to restore snapshot {snapshot_name!r} into its own source collection "
            f"{collection_name!r}; restore into a scratch collection, validate, then swap "
            "the alias in a separate gated step"
        )

    for label, value in (("target collection", target), ("snapshot name", snapshot_name)):
        if "://" in value:
            raise ValueError(
                f"{label} {value!r} looks like a URL; snapshot locations must be resolved "
                "from the Qdrant server's own snapshot store"
            )
        if not _SAFE_NAME_RE.match(value):
            raise ValueError(f"{label} {value!r} is not a safe collection/snapshot name")

    target_points = 0
    if allow_overwrite:
        try:
            target_points = int(getattr(client.get_collection(target), "points_count", 0) or 0)
        except Exception:
            target_points = 0
        if target_points > 0:
            raise ValueError(
                f"target collection {target!r} already holds {target_points} points; "
                "restore into an empty scratch collection instead"
            )
    else:
        try:
            client.get_collection(target)
        except Exception:
            target_points = 0
        else:
            raise ValueError(
                f"target collection {target!r} already exists; pass --allow-overwrite only "
                "if you intend to replace it"
            )

    if dry_run:
        logger.info(
            "[DRY-RUN] Would restore snapshot %s (from %s) into collection %s",
            snapshot_name,
            collection_name,
            target,
        )
        return {
            "status": "dry_run",
            "source_collection": collection_name,
            "target_collection": target,
            "snapshot_name": snapshot_name,
            "existing_target_points": target_points,
        }

    logger.info("Restoring snapshot %s from %s into %s", snapshot_name, collection_name, target)

    # Use Qdrant recover snapshot API
    # Snapshot location is resolved against this server's own snapshot store.
    url_base = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
    snapshot_url = f"{url_base}/collections/{collection_name}/snapshots/{snapshot_name}"

    recovered = client.recover_snapshot(
        collection_name=target,
        location=snapshot_url,
        wait=True,
    )

    # Update metric for the restored collection
    QDRANT_SNAPSHOT_AGE_HOURS.labels(collection=target).set(0.0)

    return {
        "status": "recovered",
        "source_collection": collection_name,
        "target_collection": target,
        "snapshot_name": snapshot_name,
        "result": str(recovered),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Qdrant Snapshot Manager & Metric Reporter")
    parser.add_argument(
        "--collection",
        default=getattr(settings, "qdrant_collection", "spiritual_wisdom_contextual"),
        help="Target collection (default: spiritual_wisdom_contextual)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List snapshots and report age")
    group.add_argument("--create", action="store_true", help="Create a new collection snapshot")
    group.add_argument("--restore", help="Restore specified snapshot name or location")

    parser.add_argument(
        "--into-collection",
        help="Target collection for restore (required; must differ from --collection)",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="permit restoring into an existing collection (refused by default)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate action without mutating Qdrant"
    )
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.restore and not args.into_collection:
        parser.error("--restore requires --into-collection (never the live collection)")

    client, url = _get_qdrant_client()

    if args.list:
        snaps = list_collection_snapshots(client, args.collection, update_metric=not args.dry_run)
        if args.json:
            print(json.dumps({"collection": args.collection, "snapshots": snaps}, indent=2))
        else:
            print(f"=== Snapshots for collection '{args.collection}' ({url}) ===")
            if not snaps:
                print("  No snapshots found.")
            else:
                print(f"{'Snapshot Name':<60} {'Size (MB)':<10} {'Age (h)':<10} {'Created'}")
                print("-" * 105)
                for s in snaps:
                    age_str = f"{s['age_hours']}h" if s["age_hours"] is not None else "unknown"
                    print(f"{s['name']:<60} {s['size_mb']:<10} {age_str:<10} {s['creation_time']}")
                print("-" * 105)
        return 0

    elif args.create:
        res = create_collection_snapshot(client, args.collection, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(
                f"[{res['status'].upper()}] Snapshot created: {res['snapshot_name']} for {res['collection']}"
            )
        return 0

    elif args.restore:
        try:
            res = restore_collection_snapshot(
                client,
                collection_name=args.collection,
                snapshot_name=args.restore,
                into_collection=args.into_collection,
                dry_run=args.dry_run,
                allow_overwrite=args.allow_overwrite,
            )
        except ValueError as exc:
            print(json.dumps({"status": "refused", "reason": str(exc)}, indent=2))
            return 2
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(
                f"[{res['status'].upper()}] Restored snapshot {res['snapshot_name']} into {res['target_collection']}"
            )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
