#!/usr/bin/env python3
"""Read-only corpus health snapshot for the first-person context collection.

Emits audits/corpus_health/snapshot_<iso_timestamp>.json with per-collection
metrics. Never writes to Qdrant.

Usage:
    python scripts/ops/corpus_health_snapshot.py \\
        [--url QDRANT_URL] [--collection NAME] [--out-dir DIR]

Environment:
    QDRANT_URL               Qdrant base URL (default: http://localhost:6333)
    FIRST_PERSON_ACTIVE_COLLECTION  Collection name (default: first_person)

X22: read-only by design. No alias changes, no collection writes.
X40: no rights decisions made here — this is observation only.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

try:
    from qdrant_client import QdrantClient
except ImportError:
    print("ERROR: qdrant-client not installed. Run: pip install qdrant-client", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_BATCH = 250


def _git_info() -> tuple[str, str]:
    """Return (short_sha, full_sha). Falls back to 'unknown' on failure."""
    try:
        short = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
        full = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
        return short, full
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.error("git metadata unavailable: %s", exc)
        return "unknown", "unknown"


def snapshot(url: str, collection: str, out_dir: Path) -> Path:
    """Scroll the collection and emit a health snapshot JSON."""
    client = QdrantClient(url=url, timeout=30)

    # Verify collection exists
    try:
        info = client.get_collection(collection)
        total_declared = info.points_count or 0
    except Exception as exc:
        logger.error("Cannot reach collection '%s' at %s: %s", collection, url, exc)
        sys.exit(1)

    logger.info("Scrolling '%s' (%d declared points) …", collection, total_declared)

    completeness: Counter[str] = Counter()
    rights: Counter[str] = Counter()
    embedding_model: Counter[str] = Counter()
    record_types: Counter[str] = Counter()
    speaker_verified_count = 0
    parent_child_counts: dict[str, int] = {}  # parent_id -> child count
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
            p = point.payload or {}
            total_seen += 1
            rt = str(p.get("record_type", "unknown"))
            record_types[rt] += 1
            completeness[str(p.get("completeness_status", "unknown"))] += 1
            rights[str(p.get("domain_rights_status", "unknown"))] += 1
            em = str(p.get("embedding_model_family", "unknown"))
            embedding_model[em] += 1
            if p.get("speaker_verified") is True:
                speaker_verified_count += 1
            if rt == "retrieval_child":
                pid = str(p.get("parent_id", ""))
                if pid:
                    parent_child_counts[pid] = parent_child_counts.get(pid, 0) + 1

        if next_offset is None:
            break
        offset = next_offset

    parent_count = record_types.get("parent_unit", 0)
    child_count = record_types.get("retrieval_child", 0)
    single_child_parents = sum(1 for c in parent_child_counts.values() if c == 1)

    short_sha, full_sha = _git_info()
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")

    snap = {
        "schema_version": "corpus_health_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "collection": collection,
        "qdrant_url": url,
        "total_points": total_seen,
        "total_declared": total_declared,
        "parent_count": parent_count,
        "child_count": child_count,
        "single_child_parent_count": single_child_parents,
        "speaker_verified_count": speaker_verified_count,
        "completeness_distribution": dict(completeness),
        "rights_distribution": dict(rights),
        "embedding_model_family_distribution": dict(embedding_model),
        "record_type_distribution": dict(record_types),
        "builder_version": short_sha,
        "commit_sha": full_sha,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"snapshot_{ts}.json"
    out_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False))
    logger.info("Snapshot written to %s", out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        help="Qdrant base URL",
    )
    parser.add_argument(
        "--collection",
        default=os.environ.get("FIRST_PERSON_ACTIVE_COLLECTION", "first_person"),
        help="Collection name",
    )
    parser.add_argument(
        "--out-dir",
        default="audits/corpus_health",
        help="Output directory for snapshot JSON",
    )
    args = parser.parse_args()
    out_path = snapshot(args.url, args.collection, Path(args.out_dir))
    print(str(out_path))


if __name__ == "__main__":
    main()
