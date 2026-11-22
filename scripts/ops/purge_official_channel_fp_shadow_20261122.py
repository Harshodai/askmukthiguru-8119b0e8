#!/usr/bin/env python3
"""Safely purge only the malformed legacy official-channel shadow points.

Default mode is read-only. The archived per-video point-ID ledger and the exact
Qdrant namespace must agree before any target is accepted. Create a snapshot in
its own invocation; --apply requires that exact snapshot to exist and revalidates
the full target set immediately before deleting. Memgraph is inspection-only in
this utility because no restorable graph snapshot is part of this workflow.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in os.sys.path:
    os.sys.path.insert(0, str(BACKEND))

COLLECTION = "first_person_v13_shadow"
NAMESPACE = "official_channel_shadow_20261122"
OUTPUT_DIR = ROOT / ".work/background-ingestion/official-channel-shadow-20261122"
LEGACY_RESULTS = OUTPUT_DIR / "legacy-archive/20261122T101834Z/results.jsonl"
LEGACY_CONTENT_TYPE = "video_transcript"


def now() -> str:
    return datetime.now(UTC).isoformat()


def _report_path(mode: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return OUTPUT_DIR / f"purge-report-{mode}-{stamp}.json"


def expected_point_videos() -> dict[str, str]:
    """Load the immutable legacy run ledger and return point_id -> video_id."""
    if not LEGACY_RESULTS.is_file():
        raise FileNotFoundError(f"Required archived legacy results missing: {LEGACY_RESULTS}")

    expected: dict[str, str] = {}
    seen_rows = 0
    for line_number, line in enumerate(LEGACY_RESULTS.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid archived result JSON at line {line_number}: {exc}") from exc
        seen_rows += 1
        if row.get("collection") != COLLECTION or row.get("graph_namespace") != NAMESPACE:
            raise ValueError(f"Archived row {line_number} is outside the approved purge scope")

        point_ids = row.get("point_ids") or []
        if row.get("status") == "success":
            if not point_ids or len(point_ids) != int(row.get("clips_indexed") or 0):
                raise ValueError(f"Successful archived row {line_number} lacks a complete point-ID list")
            video_id = str(row.get("video_id") or "").strip()
            if not video_id:
                raise ValueError(f"Successful archived row {line_number} lacks video_id")
            for point_id in point_ids:
                point_id = str(point_id)
                if not point_id or point_id in expected:
                    raise ValueError(f"Duplicate or empty point ID in archived row {line_number}")
                expected[point_id] = video_id
        elif point_ids:
            raise ValueError(f"Failed archived row {line_number} unexpectedly lists point IDs")

    if seen_rows == 0 or not expected:
        raise ValueError("Archived legacy result ledger has no successful point IDs")
    return expected


def matching_points(client: Any) -> list[Any]:
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue

    found: list[Any] = []
    offset = None
    filt = Filter(must=[FieldCondition(key="ingest_namespace", match=MatchValue(value=NAMESPACE))])
    while True:
        rows, offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=filt,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        found.extend(rows)
        if offset is None:
            return found


def validate_exact_scope(points: list[Any], expected: dict[str, str]) -> None:
    """Refuse deletion unless manifest, Qdrant IDs, and legacy payloads agree exactly."""
    actual_ids = {str(point.id) for point in points}
    expected_ids = set(expected)
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)[:10]
        unexpected = sorted(actual_ids - expected_ids)[:10]
        raise RuntimeError(
            "Qdrant target IDs do not exactly match archived ledger "
            f"(expected={len(expected_ids)}, actual={len(actual_ids)}, "
            f"missing_sample={missing}, unexpected_sample={unexpected})"
        )

    for point in points:
        payload = point.payload or {}
        point_id = str(point.id)
        if payload.get("ingest_namespace") != NAMESPACE:
            raise RuntimeError(f"Point {point_id} has unexpected ingest_namespace")
        if str(payload.get("video_id") or "") != expected[point_id]:
            raise RuntimeError(f"Point {point_id} video_id does not match archived ledger")
        if payload.get("content_type") != LEGACY_CONTENT_TYPE:
            raise RuntimeError(f"Point {point_id} is not the expected legacy video_transcript record")
        if payload.get("record_type") == "retrieval_child" or payload.get("parent_unit_id"):
            raise RuntimeError(f"Point {point_id} appears to be a modern parent/child record")


def inspect_memgraph(report: dict[str, Any]) -> None:
    """Read namespace-scoped graph counts only; graph deletion requires a separate snapshot."""
    try:
        from neo4j import GraphDatabase
        from app.config import settings

        uri = settings.memgraph_uri or settings.neo4j_uri
        user = settings.memgraph_user or settings.neo4j_user
        password = settings.memgraph_password or settings.neo4j_password
        driver = GraphDatabase.driver(uri, auth=(user, password) if password else None)
        try:
            with driver.session() as session:
                rows = session.run(
                    "MATCH (n {ingest_namespace:$namespace}) "
                    "RETURN labels(n) AS labels, count(n) AS c",
                    namespace=NAMESPACE,
                )
                report["memgraph_namespace_node_counts"] = {
                    ",".join(sorted(row["labels"] or [])): row["c"] for row in rows
                }
                report["memgraph_namespace_relationship_count"] = session.run(
                    "MATCH (n {ingest_namespace:$namespace})-[r]-() RETURN count(r) AS c",
                    namespace=NAMESPACE,
                ).single()["c"]
        finally:
            driver.close()
    except Exception as exc:
        report["memgraph_inspection_error"] = f"{type(exc).__name__}: {exc}"


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--snapshot", action="store_true", help="create a Qdrant snapshot after exact-scope validation")
    modes.add_argument("--apply", action="store_true", help="delete exact target points; requires --snapshot-name")
    parser.add_argument("--snapshot-name", help="existing Qdrant snapshot required by --apply")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    mode = "apply" if args.apply else "snapshot" if args.snapshot else "dry-run"
    report_path = args.report or _report_path(mode)

    if args.apply and not args.snapshot_name:
        parser.error("--apply requires --snapshot-name from a prior --snapshot run")
    if args.snapshot_name and not (args.apply or args.snapshot):
        parser.error("--snapshot-name is only valid with --apply or --snapshot")

    from qdrant_client import QdrantClient
    from app.config import settings

    qdrant_url = settings.qdrant_url
    if not Path("/.dockerenv").exists() and "qdrant:6333" in qdrant_url:
        qdrant_url = qdrant_url.replace("qdrant:6333", "localhost:6333")
    client = QdrantClient(url=qdrant_url, timeout=120)
    expected = expected_point_videos()
    points = matching_points(client)
    validate_exact_scope(points, expected)
    total_before = client.count(collection_name=COLLECTION, exact=True).count

    report: dict[str, Any] = {
        "started_at": now(),
        "mode": mode,
        "collection": COLLECTION,
        "ingest_namespace": NAMESPACE,
        "source_ledger": str(LEGACY_RESULTS),
        "expected_point_count": len(expected),
        "matched_before": len(points),
        "matched_point_ids": sorted(str(point.id) for point in points),
        "collection_total_before": total_before,
        "qdrant_snapshot": None,
        "memgraph_mutation": "not_performed; separate restorable snapshot and approval required",
    }

    if args.snapshot:
        snapshot = client.create_snapshot(collection_name=COLLECTION)
        report["qdrant_snapshot"] = str(getattr(snapshot, "name", snapshot))
        report["snapshot_status"] = "created"
    elif args.apply:
        snapshots = client.list_snapshots(collection_name=COLLECTION)
        known_names = {str(getattr(snapshot, "name", snapshot)) for snapshot in snapshots}
        if args.snapshot_name not in known_names:
            raise RuntimeError(f"Required snapshot not found in {COLLECTION}: {args.snapshot_name}")
        report["qdrant_snapshot"] = args.snapshot_name
        if points:
            client.delete(
                collection_name=COLLECTION,
                points_selector=sorted(expected),
                wait=True,
            )
        after_points = matching_points(client)
        total_after = client.count(collection_name=COLLECTION, exact=True).count
        report["matched_after"] = len(after_points)
        report["collection_total_after"] = total_after
        if after_points or total_after != total_before - len(expected):
            report["apply_status"] = "post-delete validation failed"
            report["finished_at"] = now()
            inspect_memgraph(report)
            _write_report(report_path, report)
            return 2
        report["apply_status"] = "qdrant points deleted and exact count verified"
    else:
        report["snapshot_status"] = "not created; read-only dry run"

    if mode != "apply":
        report["matched_after"] = len(points)
        report["collection_total_after"] = total_before
    inspect_memgraph(report)
    report["finished_at"] = now()
    _write_report(report_path, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
