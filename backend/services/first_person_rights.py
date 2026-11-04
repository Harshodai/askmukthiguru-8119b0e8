"""Canonical rights checks shared by first-person serving boundaries."""

from __future__ import annotations


def source_is_authoritatively_licensed(
    *, source_url: object, video_id: object, domain_rights_status: object
) -> bool:
    """Require a resolver-stamped payload and a current curated-register match.

    A historical or caller-supplied ``licensed`` string is not sufficient by
    itself: the source must still resolve as licensed from the curated manifest.
    Resolver errors, missing identity, and missing status all fail closed.
    """
    if domain_rights_status != "licensed":
        return False
    normalized_url = str(source_url or "").strip()
    normalized_video_id = str(video_id or "").strip()
    if not normalized_url or not normalized_video_id:
        return False
    try:
        from services.qdrant.indexer import resolve_source_rights_status

        return resolve_source_rights_status(normalized_url, normalized_video_id) == "licensed"
    except Exception:
        return False
