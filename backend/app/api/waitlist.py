"""Retired waitlist route (410). Launch signup is the `subscribe_launch_updates` RPC only."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container_async

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
    container: ServiceContainer = Depends(get_container_async),
) -> WaitlistResponse:
    """Retired: one signup path means one consent, throttle, erase and retention contract.

    This route upserted without `consent_to_contact` and with source "website", which the
    database trigger rejects, so it never stored anything. Nothing is read or written here.
    """
    del request, payload, container
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Launch signup moved to the in-app launch updates form.",
    )
