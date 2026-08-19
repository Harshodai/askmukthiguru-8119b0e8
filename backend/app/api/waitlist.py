"""Consent-required early-access waitlist intake."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/waitlist", tags=["Waitlist"])


class WaitlistSignup(BaseModel):
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=100)
    consent_to_contact: bool = Field(
        description="Explicit permission to retain the email for early-access updates."
    )
    source: Optional[str] = Field(default=None, max_length=80)


class WaitlistResponse(BaseModel):
    status: str
    message: str


@router.post("/", response_model=WaitlistResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.registration_rate_limit)
async def signup_waitlist(
    request: Request,
    payload: WaitlistSignup,
    container: ServiceContainer = Depends(get_container),
) -> WaitlistResponse:
    """Store opt-in details without revealing whether the email already exists."""
    del request
    if not settings.waitlist_enabled:
        raise HTTPException(status_code=503, detail="Waitlist is not open yet.")
    if not payload.consent_to_contact:
        raise HTTPException(
            status_code=422, detail="Consent is required before contact details are retained."
        )
    supabase = getattr(container, "supabase_client", None)
    if supabase is None:
        raise HTTPException(status_code=503, detail="Waitlist is temporarily unavailable.")
    row = {
        "email": str(payload.email).strip().lower(),
        "name": payload.name.strip() if payload.name else None,
        "source": payload.source.strip() if payload.source else "website",
    }
    try:
        supabase.table("waitlist_entries").upsert(row, on_conflict="email_key").execute()
    except Exception:
        logger.exception("Waitlist write failed")
        raise HTTPException(status_code=503, detail="Waitlist is temporarily unavailable.")
    return WaitlistResponse(
        status="accepted",
        message="Thank you. We will contact you when early access opens.",
    )
