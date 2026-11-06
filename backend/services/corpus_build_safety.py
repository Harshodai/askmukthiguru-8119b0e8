"""Write-safety helpers for the offline first-person corpus builders.

NEW-ING-1 (DATA-20, DATA-21): rights come from the rights register through the
same resolver the serving path uses, never from a hard-coded channel list.
NEW-ING-2 (DATA-22, DATA-23): per-video writes are upsert-then-delete, an
attempted write is verified, and every run leaves a manifest of what was
planned, written, verified and failed.

Pure Python with no acoustic or embedding imports, so CI can test it without
torch. The builder scripts import it (``services.corpus_build_safety``).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

LICENSED = "licensed"


@dataclass(frozen=True)
class RightsDecision:
    """Whether a video may be built into a servable collection, and the stamp to write."""

    cleared: bool
    domain_rights_status: str
    reason: str


def video_rights_decision(
    *,
    video_id: str,
    source_url: str,
    resolver: Optional[Callable[[str, str], str]] = None,
) -> RightsDecision:
    """Decide rights for one video from the rights register (fail closed).

    ``resolver`` defaults to ``services.qdrant.indexer.resolve_source_rights_status``,
    the function the serve path calls, so a build can never clear a video that
    serving would refuse. A video with no register row, or a row whose rights
    are not confirmed (withdrawn, missing evidence, pending review), is not
    cleared. A register that cannot be read raises: the caller aborts the build.
    """
    vid = str(video_id or "").strip()
    url = str(source_url or "").strip()
    if not vid or not url:
        return RightsDecision(False, "unverified", "missing_identity")
    if resolver is None:
        from services.qdrant.indexer import resolve_source_rights_status as resolver
    status = str(resolver(url, vid) or "unverified")
    if status == LICENSED:
        return RightsDecision(True, LICENSED, "register_licensed")
    return RightsDecision(False, status, "register_not_licensed")


@dataclass
class BuildRunManifest:
    """Per-run record of a corpus build (NEW-ING-2). Written atomically."""

    collection: str
    corpus_version: str
    started_at: str
    dry_run: bool
    planned: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    snapshots: list[str] = field(default_factory=list)
    finished_at: Optional[str] = None
    exit_status: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection": self.collection,
            "corpus_version": self.corpus_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "dry_run": self.dry_run,
            "exit_status": self.exit_status,
            "counts": {
                "planned": len(self.planned),
                "written": len(self.written),
                "verified": len(self.verified),
                "failed": len(self.failed),
                "skipped": len(self.skipped),
            },
            "planned": sorted(self.planned),
            "written": sorted(self.written),
            "verified": sorted(self.verified),
            "failed": dict(sorted(self.failed.items())),
            "skipped": dict(sorted(self.skipped.items())),
            "snapshots": list(self.snapshots),
        }

    def write(self, path: Path) -> None:
        """Atomic write (invariant 20): temp file in the same directory, then os.replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}_{time.time_ns()}")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)


class EmptyBuildError(RuntimeError):
    """A build that would write nothing is refused (invariant 4)."""


def refuse_empty_build(planned: Iterable[Any], *, dry_run: bool) -> None:
    if not dry_run and not list(planned):
        raise EmptyBuildError("refusing an empty build: no video is planned for writing")


@dataclass(frozen=True)
class VideoWriteResult:
    status: str  # verified | failed
    reason: str
    written: int = 0
    deleted_stale: int = 0


def _video_point_ids(qdrant: Any, collection: str, video_id: str) -> set[Any]:
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    vid_filter = Filter(must=[FieldCondition(key="video_id", match=MatchValue(value=video_id))])
    ids: set[Any] = set()
    offset = None
    while True:
        page, offset = qdrant.scroll_page(
            collection=collection,
            offset=offset,
            limit=500,
            with_payload=False,
            scroll_filter=vid_filter,
        )
        for point in page:
            if getattr(point, "id", None) is not None:
                ids.add(str(point.id))
        if offset is None:
            return ids


def write_video_points(
    qdrant: Any, *, collection: str, video_id: str, points: list[Any]
) -> VideoWriteResult:
    """Replace one video's points: upsert the new set first, then delete the stale ones.

    The old order (delete every point of the video, then upsert) left the video
    with no points when the upsert failed, and its cleanup then deleted ids the
    collection held before the run (deterministic ids are reused). Here:

    1. The video's current ids are read. If that fails nothing is written.
    2. The new points are upserted. On failure only ids that did not exist
       before are deleted, so the previous version stays as it was.
    3. Ids of the old version that the new set does not contain are deleted.
    4. The video's ids are read again and must equal the new set exactly.
    """
    new_ids = {str(p.id) for p in points}
    if not new_ids:
        return VideoWriteResult("failed", "no_points")
    try:
        before = _video_point_ids(qdrant, collection, video_id)
    except Exception as exc:  # noqa: BLE001 - any client error means "state unknown"
        logger.error("Video %s: existing-point scan failed (%s); not written", video_id, exc)
        return VideoWriteResult("failed", "existing_scan_failed")
    try:
        qdrant.upsert_points(points, collection=collection, wait=True)
    except Exception as exc:  # noqa: BLE001 - any client error means "state unknown"
        logger.error("Video %s: upsert failed (%s)", video_id, exc)
        introduced = sorted(new_ids - before)
        if introduced:
            try:
                qdrant.delete_points_by_ids(introduced, collection=collection)
            except Exception as cleanup_exc:  # noqa: BLE001
                logger.error(
                    "Video %s: removing %d new ids after the failed upsert also failed: %s",
                    video_id,
                    len(introduced),
                    cleanup_exc,
                )
                return VideoWriteResult("failed", "upsert_failed_cleanup_failed")
        return VideoWriteResult("failed", "upsert_failed")
    stale = sorted(before - new_ids)
    if stale:
        try:
            qdrant.delete_points_by_ids(stale, collection=collection)
        except Exception as exc:  # noqa: BLE001
            logger.error("Video %s: stale delete failed (%s)", video_id, exc)
            return VideoWriteResult("failed", "stale_delete_failed", written=len(new_ids))
    try:
        after = _video_point_ids(qdrant, collection, video_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Video %s: post-write verification scan failed (%s)", video_id, exc)
        return VideoWriteResult("failed", "verify_scan_failed", written=len(new_ids))
    if after != new_ids:
        return VideoWriteResult(
            "failed", "verify_mismatch", written=len(new_ids), deleted_stale=len(stale)
        )
    return VideoWriteResult("verified", "ok", written=len(new_ids), deleted_stale=len(stale))
