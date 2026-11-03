"""Owner-only local review candidate preview — HTTP route.

**This route is local-only and opt-in.** It serves the Phase-4
``local_review_candidate`` tier straight from the immutable candidate
manifests: no Qdrant read, no Qdrant write, no alias, no Redis, and no
LLM-authored teaching text. It is a review surface, not a product surface.

Guards (all must hold, or the route refuses):

1. ``first_person_local_review_enabled`` is true — an explicit local-only flag.
2. ``is_production`` is false. A production deployment refuses this route even
   if the flag is on: the corpus is an *automated-evidence candidate*, not a
   public-verified corpus, and the rights register is not owner-signed.
3. Every pinned artifact (tiers manifest, Phase-2 verdicts, rights manifest,
   rights join, speaker-conflict quarantine, serving contract) exists and
   matches its pinned sha256. A missing or modified artifact refuses the
   request instead of serving stale evidence.

The shipped contract's ``enabled=false`` field is public-release/artifact
metadata, not the runtime switch for this route. The separate authenticated
owner-preview route is enabled only when the environment-backed
``FIRST_PERSON_LOCAL_REVIEW_ENABLED`` flag is true and the process is
non-production; the contract and its hash are not changed here.

The HTTP path currently documents and expects English input. Its translator
helper is not wired into the route, and no external/provider translation or
distress assessor is invoked. The deterministic blocked-topic rail is not
general or multilingual crisis safety, and this route does not add provider
calls.

Every response carries the canonical two-line owner-only label::

    REVIEW CANDIDATE — NOT PUBLIC RELEASE
    AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION

and the evidence metadata (evidence policy, corpus version, collection,
manifest hashes). The label also appears on **every citation**, because a
citation can be copied out of the response.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from services.auth_service import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["First-Person Local Review (owner-only)"])

# The owner-only label, printed in the route's own responses so the label is
# visible even when a client renders only the status endpoint.
REVIEW_LABEL_LINES = (
    "REVIEW CANDIDATE — NOT PUBLIC RELEASE",
    "AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION",
)
REVIEW_LABEL = "\n".join(REVIEW_LABEL_LINES)
LOCAL_REVIEW_UNAVAILABLE_MESSAGE = "First-person local review is temporarily unavailable."

_SERVICE: Optional[Any] = None
_SERVICE_ERROR: str = ""


class LocalReviewQueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="English seeker question for the deterministic local-review topic rail",
    )
    teacher_id: Optional[str] = Field("both", description="'preethaji', 'krishnaji', or 'both'")
    max_clips: int = Field(3, ge=1, le=5)
    cache_bypass: bool = False

    @field_validator("query")
    @classmethod
    def _require_ascii_english_query(cls, value: str) -> str:
        if not value.isascii():
            raise ValueError("Query must contain ASCII English text only.")
        return value


def _local_review_allowed() -> tuple[bool, str]:
    """The local-only guard. Returns (allowed, reason)."""
    if not bool(getattr(settings, "first_person_local_review_enabled", False)):
        return False, "local_review_mode_disabled"
    if bool(getattr(settings, "is_production", False)):
        return False, "local_review_mode_refuses_production"
    return True, ""


def _build_service() -> Any:
    """Build (once) and start the local review service."""
    global _SERVICE, _SERVICE_ERROR
    if _SERVICE is not None:
        return _SERVICE
    from services.first_person_local_review import (
        LocalReviewError,
        LocalReviewService,
        load_local_review_config,
    )

    try:
        config = load_local_review_config(
            str(getattr(settings, "first_person_local_review_contract_path", "") or "") or None,
            repo_root=str(getattr(settings, "first_person_local_review_root", "") or "") or None,
        )
        service = LocalReviewService(config)
        service.startup_check()
    except LocalReviewError as exc:
        _SERVICE_ERROR = str(exc)
        logger.error("[LocalReviewRoute] refusing to start: %s", exc)
        raise
    _SERVICE = service
    _SERVICE_ERROR = ""
    return _SERVICE


def _translator() -> Any:
    """Retained translation helper; not wired into this HTTP route.

    The route currently accepts English input and uses the local service's
    deterministic blocked-topic rail, which is not general or multilingual
    crisis safety. If this helper is wired later, translation must remain
    query-only: the ANSWER is never translated or rewritten and stays the
    teacher's stored span text.
    """

    async def _translate(text: str) -> str:
        try:
            from app.language_utils import guardrail_text_for

            return await guardrail_text_for(text, None, "en")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LocalReviewRoute] query translation failed: %s", exc)
            return text

    return _translate


@router.post("/first-person/local-review/query")
async def local_review_query(
    req: LocalReviewQueryRequest,
    request: Request,
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Serve the English-input local review tier. Owner-only; never public."""
    allowed, reason = _local_review_allowed()
    if not allowed:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"First-person local review: {reason}",
                "review_label": REVIEW_LABEL,
                "review_label_lines": list(REVIEW_LABEL_LINES),
            },
        )

    try:
        service = _build_service()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[LocalReviewRoute] query: service build failed")
        raise HTTPException(
            status_code=503,
            detail={
                "message": LOCAL_REVIEW_UNAVAILABLE_MESSAGE,
                "review_label": REVIEW_LABEL,
                "review_label_lines": list(REVIEW_LABEL_LINES),
            },
        ) from exc

    start = time.monotonic()
    try:
        answer = service.query(
            req.query,
            teacher_id=req.teacher_id or "both",
            max_clips=req.max_clips,
            use_cache=not req.cache_bypass,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[LocalReviewRoute] query: service query failed")
        raise HTTPException(
            status_code=503,
            detail={
                "message": LOCAL_REVIEW_UNAVAILABLE_MESSAGE,
                "review_label": REVIEW_LABEL,
                "review_label_lines": list(REVIEW_LABEL_LINES),
            },
        ) from exc
    latency_ms = round((time.monotonic() - start) * 1000.0, 2)
    payload = answer.to_dict()
    payload["latency_ms"] = latency_ms
    payload["metadata"]["route"] = "/api/first-person/local-review/query"
    payload["metadata"]["local_only"] = True
    payload["metadata"]["review_label"] = REVIEW_LABEL
    payload["metadata"]["review_label_lines"] = list(REVIEW_LABEL_LINES)
    payload["metadata"]["qdrant_reads"] = 0
    payload["metadata"]["qdrant_writes"] = 0
    payload["metadata"]["alias_changes"] = 0
    logger.info(
        "[LocalReviewRoute] status=%s abstain=%s citations=%d evidence_policy=%s "
        "corpus_version=%s collection=%s latency_ms=%.2f",
        answer.status,
        answer.abstain_reason,
        len(answer.citations),
        answer.metadata.get("evidence_policy"),
        answer.metadata.get("corpus_version"),
        answer.metadata.get("collection"),
        latency_ms,
    )
    return payload


@router.get("/first-person/local-review/status")
async def local_review_status(_admin: dict = Depends(require_admin)) -> dict[str, Any]:
    """Report local-review availability to an authenticated local admin only."""
    allowed, reason = _local_review_allowed()
    if not allowed:
        return {
            "available": False,
            "reason": reason,
            "review_label": REVIEW_LABEL,
            "review_label_lines": list(REVIEW_LABEL_LINES),
        }
    try:
        service = _build_service()
    except Exception:  # noqa: BLE001
        logger.exception("[LocalReviewRoute] status: service build failed")
        return {
            "available": False,
            "reason": "artifact_verification_failed",
            "error": "Local review service unavailable; see server logs.",
            "review_label": REVIEW_LABEL,
            "review_label_lines": list(REVIEW_LABEL_LINES),
        }
    info = service.cache_info()
    return {
        "available": True,
        "review_label": REVIEW_LABEL,
        "review_label_lines": list(REVIEW_LABEL_LINES),
        "evidence_policy": info["evidence_policy"],
        "corpus_version": info["corpus_version"],
        "collection": info["collection"],
        "tier": service.config.tier,
        "cache": info,
        "qdrant_reads": 0,
        "qdrant_writes": 0,
        "alias_changes": 0,
    }
