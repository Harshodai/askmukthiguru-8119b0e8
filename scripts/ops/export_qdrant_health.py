#!/usr/bin/env python3
"""export_qdrant_health.py — Qdrant Health, Optimizer, and Snapshot Observability.

Queries Qdrant cluster and collection telemetry, computes key SLIs:
  - Optimizer status (1=ok, 0=error/stuck)
  - Deleted points ratio (deleted / total)
  - Snapshot age in hours (hours since newest snapshot)
Updates Prometheus gauges in app.metrics and outputs health reports.

Usage:
    python -m scripts.ops.export_qdrant_health
    python -m scripts.ops.export_qdrant_health --collection spiritual_wisdom_contextual
    python -m scripts.ops.export_qdrant_health --dry-run
    python -m scripts.ops.export_qdrant_health --json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
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
from app.metrics import (
    QDRANT_DELETED_POINTS_RATIO,
    QDRANT_OPTIMIZER_STATUS,
    QDRANT_SNAPSHOT_AGE_HOURS,
)

logger = logging.getLogger("export_qdrant_health")


def _parse_iso_datetime(dt_str: str) -> datetime:
    """Safely parse ISO datetime string to UTC aware datetime."""
    dt_clean = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(dt_clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def get_collection_snapshot_age_hours(client: QdrantClient, collection_name: str) -> float:
    """Return hours elapsed since the latest snapshot of collection_name, or -1.0 if none exist."""
    try:
        snapshots = client.list_snapshots(collection_name)
        if not snapshots:
            return -1.0

        now = datetime.now(tz=UTC)
        newest_dt: Optional[datetime] = None

        for snap in snapshots:
            creation_time_str = getattr(snap, "creation_time", None)
            if creation_time_str:
                try:
                    dt = _parse_iso_datetime(creation_time_str)
                    if newest_dt is None or dt > newest_dt:
                        newest_dt = dt
                except Exception:
                    continue

        if newest_dt is None:
            return -1.0

        age_seconds = (now - newest_dt).total_seconds()
        return max(0.0, age_seconds / 3600.0)
    except Exception as e:
        logger.warning("Failed to list snapshots for %s: %s", collection_name, e)
        return -1.0


def check_qdrant_health(
    qdrant_url: Optional[str] = None,
    api_key: Optional[str] = None,
    target_collection: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Inspect Qdrant health telemetry, update Prometheus gauges, and return report."""
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
            url = url.replace("://qdrant:", "://localhost:")

    key = (
        api_key
        or os.environ.get("QDRANT_API_KEY")
        or getattr(settings, "qdrant_api_key", None)
        or None
    )

    client = QdrantClient(url=url, api_key=key, timeout=30)
    now = datetime.now(tz=UTC)

    if target_collection:
        collections = [target_collection]
    else:
        try:
            col_list = client.get_collections().collections
            collections = [c.name for c in col_list]
        except Exception as e:
            logger.error("Failed to list collections from %s: %e", url, e)
            return {"status": "error", "error": str(e), "collections": {}}

    report: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "qdrant_url": url,
        "dry_run": dry_run,
        "collections": {},
    }

    all_ok = True

    for col in sorted(collections):
        try:
            info = client.get_collection(col)
            points_count = int(getattr(info, "points_count", 0) or 0)
            segments_count = int(getattr(info, "segments_count", 0) or 0)
            indexed_vectors_count = int(getattr(info, "indexed_vectors_count", 0) or 0)

            # Optimizer status evaluation
            raw_opt_status = getattr(info, "optimizer_status", "ok")
            if hasattr(raw_opt_status, "value"):
                opt_str = str(raw_opt_status.value).lower()
            else:
                opt_str = str(raw_opt_status).lower()

            is_opt_ok = opt_str in {"ok", "optimizersstatusoneof.ok"}
            opt_gauge_val = 1.0 if is_opt_ok else 0.0
            if not is_opt_ok:
                all_ok = False

            # Deleted points ratio calculation
            # Qdrant reports active points_count. If segments or telemetry details deleted count, use it.
            deleted_count = int(getattr(info, "deleted_points_count", 0) or 0)
            total_points = points_count + deleted_count
            deleted_ratio = (deleted_count / total_points) if total_points > 0 else 0.0

            # Snapshot age
            snapshot_age_hours = get_collection_snapshot_age_hours(client, col)

            col_data = {
                "status": str(getattr(info, "status", "unknown")),
                "optimizer_status": opt_str,
                "optimizer_ok": is_opt_ok,
                "points_count": points_count,
                "segments_count": segments_count,
                "indexed_vectors_count": indexed_vectors_count,
                "deleted_points_count": deleted_count,
                "deleted_points_ratio": round(deleted_ratio, 4),
                "snapshot_age_hours": round(snapshot_age_hours, 2),
            }
            report["collections"][col] = col_data

            if not dry_run:
                QDRANT_OPTIMIZER_STATUS.labels(collection=col).set(opt_gauge_val)
                QDRANT_DELETED_POINTS_RATIO.labels(collection=col).set(deleted_ratio)
                if snapshot_age_hours >= 0:
                    QDRANT_SNAPSHOT_AGE_HOURS.labels(collection=col).set(snapshot_age_hours)

        except Exception as col_err:
            logger.warning("Error fetching info for collection %s: %s", col, col_err)
            report["collections"][col] = {"error": str(col_err)}
            all_ok = False
            if not dry_run:
                QDRANT_OPTIMIZER_STATUS.labels(collection=col).set(0.0)

    report["overall_ok"] = all_ok
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Qdrant health and optimizer metrics")
    parser.add_argument("--collection", help="Specific collection to inspect (default: all)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print report without setting Prometheus gauges"
    )
    parser.add_argument("--json", action="store_true", help="Output report in JSON format")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    report = check_qdrant_health(target_collection=args.collection, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=== Qdrant Health & Optimizer Telemetry ===")
        print(f"URL: {report.get('qdrant_url')} | Dry-run: {report.get('dry_run')}")
        print(
            f"{'Collection':<36} {'Status':<8} {'Optimizer':<10} {'Points':<8} {'Segments':<9} {'Snap Age (h)':<12}"
        )
        print("-" * 88)
        for name, data in report.get("collections", {}).items():
            if "error" in data:
                print(f"{name:<36} ERROR: {data['error']}")
                continue
            snap_str = (
                f"{data['snapshot_age_hours']}h" if data["snapshot_age_hours"] >= 0 else "none"
            )
            print(
                f"{name:<36} {data['status']:<8} {data['optimizer_status']:<10} "
                f"{data['points_count']:<8} {data['segments_count']:<9} {snap_str:<12}"
            )
        print("-" * 88)
        print(f"Overall Status: {'HEALTHY' if report.get('overall_ok') else 'DEGRADED/ERROR'}\n")

    return 0 if report.get("overall_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
