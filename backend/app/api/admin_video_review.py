"""Admin video-approval API: which videos may be served to users.

Mounted at ``/api/admin/fp-videos``. Every route needs an AAL2 superuser (the same
``_require_admin`` dependency as the rest of the admin API). Writes also need a
CSRF token bound to the admin's user id.

The page records a HUMAN decision per video. It never writes the machine-measured
``speaker_verified`` field, never writes Qdrant, and an approval cannot override a
serve-time gate (see ``services/first_person_video_decisions.py``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.api.admin import _require_admin
from app.config import settings
from app.dependencies import ServiceContainer, get_container_async
from app.sanitization import sanitize_log_input
from app.security_utils import generate_csrf_token, validate_csrf_token
from services.first_person_video_decisions import (
    GRADES,
    MAX_NOTES_LEN,
    MAX_REASON_LEN,
    SPEAKER_CHECKS,
    VIDEO_ID_RE,
    VideoDecisionError,
    VideoDecisionStore,
    VideoDecisionValidationError,
)
from services.first_person_video_review import (
    APPROVED_FILTERS,
    MAX_PAGE,
    VERIFIED_FILTERS,
    aggregate_live,
    build_rows,
    filter_rows,
    load_inventory,
    scroll_child_payloads,
    summarize,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-video-review"])

CSRF_TTL_S = 3600
CSRF_HEADER = "X-CSRF-Token"
LIVE_CACHE_TTL_S = 60.0
_LIVE_CACHE: dict[str, Any] = {"at": 0.0, "collection": "", "data": None}

VideoIdPath = Path(..., pattern=VIDEO_ID_RE.pattern, description="11-character YouTube video id")


class VideoDecisionRequest(BaseModel):
    """The full human decision for one video. ``null`` clears a field."""

    model_config = ConfigDict(extra="forbid")

    admin_approved: Optional[StrictBool] = None
    human_speaker_check: Optional[Literal["confirmed", "rejected"]] = None
    grade: Optional[Literal["A", "B", "C", "D", "F"]] = None
    notes: Optional[str] = Field(default=None, max_length=MAX_NOTES_LEN)
    reason: Optional[str] = Field(default=None, max_length=MAX_REASON_LEN)


def _csrf_secret() -> str:
    return str(
        getattr(settings, "csrf_secret", None) or getattr(settings, "jwt_secret", None) or ""
    )


def _user_id(user: dict) -> str:
    return str(user.get("id") or "")


async def _require_csrf(request: Request, user: dict = Depends(_require_admin)) -> dict:
    secret = _csrf_secret()
    if not secret:
        # No signing secret configured: refuse writes rather than skip the check.
        raise HTTPException(status_code=503, detail="CSRF protection is not configured")
    token = request.headers.get(CSRF_HEADER, "")
    uid = _user_id(user)
    parts = token.split(".")
    # validate_csrf_token checks the signature and age; the user binding is checked here.
    if (
        not uid
        or len(parts) != 4
        or parts[2] != uid
        or not validate_csrf_token(token, secret, uid, ttl=CSRF_TTL_S)
    ):
        raise HTTPException(status_code=403, detail="Invalid or expired CSRF token")
    return user


def _store() -> VideoDecisionStore:
    return VideoDecisionStore()


def _qdrant_client(container: ServiceContainer) -> Any:
    client = getattr(container, "qdrant_client", None)
    if client is None and hasattr(container, "qdrant"):
        client = getattr(container.qdrant, "_client", None) or getattr(
            container.qdrant, "client", None
        )
    return client


async def _live_evidence(
    container: ServiceContainer, *, refresh: bool
) -> tuple[Optional[dict[str, dict[str, Any]]], str]:
    """Machine evidence per video from the v10 collection (read-only), or None if unreadable."""
    collection = str(settings.first_person_context_collection or "").strip()
    if not collection:
        return None, ""
    now = time.monotonic()
    if (
        not refresh
        and _LIVE_CACHE["data"] is not None
        and _LIVE_CACHE["collection"] == collection
        and now - _LIVE_CACHE["at"] < LIVE_CACHE_TTL_S
    ):
        return _LIVE_CACHE["data"], collection
    client = _qdrant_client(container)
    if client is None:
        return None, collection
    try:
        payloads = await asyncio.to_thread(scroll_child_payloads, client, collection)
    except Exception as exc:  # noqa: BLE001 - Qdrant down must not take the page down
        logger.warning("[VideoReview] live evidence unavailable: %s", sanitize_log_input(str(exc)))
        return None, collection
    data = aggregate_live(payloads)
    _LIVE_CACHE.update(at=now, collection=collection, data=data)
    return data, collection


def _load_decisions() -> dict:
    try:
        return _store().load()
    except VideoDecisionError as exc:
        logger.error("[VideoReview] %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Video decisions file is invalid. Serving is blocked until it is repaired.",
        ) from exc


@router.get("/csrf")
async def get_csrf_token(user: dict = Depends(_require_admin)) -> dict[str, Any]:
    """A short-lived token the page sends back in the X-CSRF-Token header on writes."""
    secret = _csrf_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="CSRF protection is not configured")
    return {
        "token": generate_csrf_token(secret, _user_id(user), CSRF_TTL_S),
        "ttl_seconds": CSRF_TTL_S,
        "header": CSRF_HEADER,
    }


@router.get("")
async def list_videos(
    channel: Optional[str] = Query(None, max_length=200),
    verified: Optional[Literal["none", "partial", "full"]] = Query(
        None, description="Machine-measured speaker verification across the video's v10 spans"
    ),
    approved: Optional[Literal["approved", "rejected", "undecided"]] = Query(None),
    in_v10: Optional[bool] = Query(None, description="false lists videos missing from v10"),
    q: Optional[str] = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    refresh: bool = Query(False, description="Bypass the 60 s live-evidence cache"),
    user: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    decisions = _load_decisions()
    live, collection = await _live_evidence(container, refresh=refresh)
    inventory = await asyncio.to_thread(load_inventory)
    all_rows = build_rows(inventory, live, decisions)
    rows = filter_rows(
        all_rows, channel=channel, verified=verified, approved=approved, in_v10=in_v10, query=q
    )
    return {
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "rows": rows[offset : offset + limit],
        "summary": summarize(all_rows),
        "channels": sorted({r["channel"] for r in all_rows}),
        "live": live is not None,
        "collection": collection,
        "filters": {"verified": list(VERIFIED_FILTERS), "approved": list(APPROVED_FILTERS)},
        "options": {"grades": list(GRADES), "speaker_checks": list(SPEAKER_CHECKS)},
    }


@router.get("/{video_id}")
async def get_video(
    video_id: str = VideoIdPath,
    user: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    decisions = _load_decisions()
    live, _ = await _live_evidence(container, refresh=False)
    inventory = await asyncio.to_thread(load_inventory)
    rows = [r for r in build_rows(inventory, live, decisions) if r["video_id"] == video_id]
    if not rows:
        raise HTTPException(status_code=404, detail="Unknown video")
    try:
        audit = _store().audit(video_id, limit=50)
    except VideoDecisionError as exc:
        raise HTTPException(status_code=503, detail="Audit log is unreadable") from exc
    return {"video": rows[0], "audit": audit}


@router.put("/{video_id}")
async def put_video_decision(
    payload: VideoDecisionRequest,
    video_id: str = VideoIdPath,
    user: dict = Depends(_require_csrf),
) -> dict[str, Any]:
    """Replace the human decision for one video. The machine speaker field is not touched."""
    try:
        decision = _store().set_decision(
            video_id,
            actor=_user_id(user),
            admin_approved=payload.admin_approved,
            human_speaker_check=payload.human_speaker_check,
            grade=payload.grade,
            notes=payload.notes,
            reason=payload.reason,
        )
    except VideoDecisionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VideoDecisionError as exc:
        logger.error("[VideoReview] write failed: %s", exc)
        raise HTTPException(status_code=503, detail="Decision could not be saved") from exc
    logger.info(
        "Admin %s set video decision %s: approved=%s speaker_check=%s grade=%s",
        sanitize_log_input(_user_id(user)),
        sanitize_log_input(video_id),
        decision.admin_approved,
        decision.human_speaker_check,
        decision.grade,
    )
    return {
        "ok": True,
        "video_id": video_id,
        "decision": None if decision.is_empty else decision.as_dict(),
        "blocks_serving": decision.blocks_serving,
    }
