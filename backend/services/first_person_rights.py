"""Canonical rights checks shared by first-person and multi-format serving boundaries."""

from __future__ import annotations

from typing import Optional

_NON_VIDEO_SOURCE_TYPES = frozenset(
    {"book", "audio", "podcast", "website", "course_event", "document"}
)


def source_is_authoritatively_licensed(
    *,
    source_url: object,
    video_id: object = None,
    domain_rights_status: object,
    source_type: Optional[str] = None,
    source_id: object = None,
) -> bool:
    """Require a resolver-stamped payload and a current curated-register match.

    A historical or caller-supplied ``licensed`` string is not sufficient by
    itself: the source must still resolve as licensed from the curated manifest.
    Supports both YouTube videos (identified by ``source_url`` + ``video_id``)
    and non-video authorized sources such as books, audio, courses, and official
    websites (identified by ``source_url`` or ``source_id`` when ``source_type``
    is a recognized non-video format). Resolver errors, missing identity, and
    missing status all fail closed.
    """
    if domain_rights_status != "licensed":
        return False
    normalized_url = str(source_url or "").strip()
    normalized_video_id = str(video_id or "").strip()
    normalized_source_id = str(source_id or "").strip()
    normalized_type = str(source_type or "").strip().lower()

    is_non_video = normalized_type in _NON_VIDEO_SOURCE_TYPES
    if not normalized_url and not normalized_source_id:
        return False
    if not is_non_video and not normalized_video_id:
        # Backward-compatible video invariant: YouTube/video records must carry a video_id
        # unless explicitly declared as a non-video source_type.
        return False

    try:
        from services.qdrant.indexer import resolve_source_rights_status

        lookup_url = normalized_url or normalized_source_id
        lookup_id = normalized_video_id or normalized_source_id or None
        return resolve_source_rights_status(lookup_url, lookup_id) == "licensed"
    except Exception:
        return False
