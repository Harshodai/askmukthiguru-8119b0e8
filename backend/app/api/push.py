"""
Push notification API routes (Task 7 — mobile app launch).

- POST /push/register  : register/upsert a device token (auth optional; user_id derived from auth only).
- POST /push/send       : admin-only broadcast / targeted push.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import get_container
from schemas.push import (
    PushRegisterRequest,
    PushRegisterResponse,
    PushSendRequest,
    PushSendResponse,
)
from services.auth_service import get_current_user_from_supabase

router = APIRouter(prefix="/push", tags=["Push"])


def _require_admin(user: Optional[dict]) -> None:
    """Reject non-admin callers. service_role tokens and admin-role users pass."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("is_superuser") or user.get("role") == "service_role":
        return
    raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/register", response_model=PushRegisterResponse)
@limiter.limit(settings.push_register_rate_limit)
async def register_device(
    request: Request,
    payload: PushRegisterRequest,
    user: Optional[dict] = Depends(get_current_user_from_supabase),
):
    """Register or refresh a device token. Anonymous devices allowed (no user_id)."""
    # Derive user_id exclusively from the authenticated session — never trust payload.user_id.
    user_id = user.get("id") if user and not user.get("is_anonymous") else None
    service = get_container().push_service
    device_id = await service.register_device(
        platform=payload.platform,
        token=payload.token,
        user_id=user_id,
    )
    return PushRegisterResponse(ok=True, device_id=device_id)


@router.post("/send", response_model=PushSendResponse)
@limiter.limit(settings.push_send_rate_limit)
async def send_push(
    request: Request,
    payload: PushSendRequest,
    user: dict = Depends(get_current_user_from_supabase),
):
    """Admin-only: send a push to a user (or broadcast if user_id is None)."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("is_anonymous"):
        raise HTTPException(status_code=401, detail="Authentication required")
    _require_admin(user)
    service = get_container().push_service
    result = await service.send(
        user_id=payload.user_id,
        title=payload.title,
        body=payload.body,
        deep_link=payload.deep_link,
        data=payload.data,
    )
    return PushSendResponse(
        ok=bool(result.get("ok", True)),
        sent=int(result.get("sent", 0)),
        failed=int(result.get("failed", 0)),
        errors=list(result.get("errors", []) or []),
    )