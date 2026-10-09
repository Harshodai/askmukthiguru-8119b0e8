#!/usr/bin/env python3
"""Quarantine spiritual / miracle promise clips from first-person serving (Hard Stop H4).

Audit 2026-10-05 Hard Stop H4:
Clips making outcome promises (e.g. "your problems melt like ice in the heat of the sun",
"guaranteed miracle") must be quarantined from serving by setting
`first_person_eligible=False` in Qdrant first_person_v7 (specifically clip mmpmX3-qfc4).

Usage:
    PYTHONPATH=backend .venv/bin/python -m scripts.ops.quarantine_promise_clips \\
        --collection first_person_v7 --video-id mmpmX3-qfc4 [--apply]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
# Same file lives in backend/scripts/ops/ and scripts/ops/ (tests/test_repo_layout.py
# pins them identical), so find backend/ from either location.
_BACKEND = _ROOT if (_ROOT / "services").is_dir() else _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import settings
from services.first_person_store import (
    _OUTCOME_PROMISE_CLIP_RE,
    BLOCKED_PROMISE_POINT_IDS,
)

logger = logging.getLogger("quarantine_promise_clips")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def quarantine_promise_clips(
    collection: str = "first_person_v7",
    video_id: str = "mmpmX3-qfc4",
    client: Any | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Find and quarantine clips matching video_id or _OUTCOME_PROMISE_CLIP_RE.

    Sets `first_person_eligible=False` and `quarantine_reason='outcome_promise_H4'`.
    """
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    if client is None:
        try:
            client = QdrantClient(
                url=settings.qdrant_url,
                api_key=getattr(settings, "qdrant_api_key", None)
                or os.getenv("QDRANT_API_KEY")
                or None,
                timeout=10,
            )
        except Exception as e:
            logger.warning("Could not connect to Qdrant at %s: %s", settings.qdrant_url, e)
            return {
                "collection": collection,
                "video_id": video_id,
                "status": "connection_error",
                "error": str(e),
                "quarantined_count": 0,
                "points": [],
            }

    points_to_quarantine = []

    try:
        # 1. Search for video_id points
        offset = None
        while True:
            scroll_filter = Filter(
                must=[FieldCondition(key="video_id", match=MatchValue(value=video_id))]
            )
            points, offset = client.scroll(
                collection_name=collection,
                scroll_filter=scroll_filter,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                pl = p.payload or {}
                if pl.get("first_person_eligible") is False:
                    continue
                points_to_quarantine.append(
                    {
                        "point_id": str(p.id),
                        "video_id": pl.get("video_id"),
                        "text": pl.get("verbatim_text", "")[:80],
                        "reason": f"video_id_{video_id}",
                    }
                )
            if offset is None:
                break

        # 2. Also scan for any clips matching _OUTCOME_PROMISE_CLIP_RE or BLOCKED_PROMISE_POINT_IDS
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=collection,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                pl = p.payload or {}
                if pl.get("first_person_eligible") is False:
                    continue
                pid = str(p.id)
                v_text = pl.get("verbatim_text", "")
                vid = pl.get("video_id", "")
                if pid in BLOCKED_PROMISE_POINT_IDS or vid in BLOCKED_PROMISE_POINT_IDS:
                    if not any(pt["point_id"] == pid for pt in points_to_quarantine):
                        points_to_quarantine.append(
                            {
                                "point_id": pid,
                                "video_id": vid,
                                "text": v_text[:80],
                                "reason": "blocked_promise_point_id",
                            }
                        )
                elif _OUTCOME_PROMISE_CLIP_RE.search(v_text):
                    if not any(pt["point_id"] == pid for pt in points_to_quarantine):
                        points_to_quarantine.append(
                            {
                                "point_id": pid,
                                "video_id": vid,
                                "text": v_text[:80],
                                "reason": "outcome_promise_regex",
                            }
                        )
            if offset is None:
                break

        quarantined_ids = [pt["point_id"] for pt in points_to_quarantine]
        if points_to_quarantine and not dry_run:
            client.set_payload(
                collection_name=collection,
                payload={
                    "first_person_eligible": False,
                    "quarantine_reason": "outcome_promise_H4",
                },
                points=quarantined_ids,
            )
            logger.info(
                "Successfully quarantined %d clips in %s (dry_run=%s)",
                len(quarantined_ids),
                collection,
                dry_run,
            )
        else:
            logger.info(
                "Found %d candidate clips in %s (dry_run=%s)",
                len(points_to_quarantine),
                collection,
                dry_run,
            )

        return {
            "collection": collection,
            "video_id": video_id,
            "status": "success",
            "quarantined_count": len(points_to_quarantine),
            "dry_run": dry_run,
            "points": points_to_quarantine,
        }

    except Exception as e:
        logger.warning("Error inspecting/quarantining clips in Qdrant: %s", e)
        return {
            "collection": collection,
            "video_id": video_id,
            "status": "error",
            "error": str(e),
            "quarantined_count": len(points_to_quarantine),
            "points": points_to_quarantine,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="first_person_v7", help="Qdrant collection name")
    parser.add_argument("--video-id", default="mmpmX3-qfc4", help="Video ID to quarantine")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not write")
    parser.add_argument("--apply", action="store_true", help="Apply updates to Qdrant")
    args = parser.parse_args(argv)

    is_dry = args.dry_run or not args.apply
    result = quarantine_promise_clips(
        collection=args.collection,
        video_id=args.video_id,
        dry_run=is_dry,
    )
    print(
        f"Quarantine Result: status={result.get('status')}, "
        f"quarantined={result.get('quarantined_count')} clips (dry_run={is_dry})"
    )
    for p in result.get("points", []):
        print(
            f"  - Point {p['point_id']} ({p.get('video_id')}): {p.get('reason')} - {p.get('text')}"
        )
    return 0 if result.get("status") in ("success", "connection_error") else 1


if __name__ == "__main__":
    sys.exit(main())
