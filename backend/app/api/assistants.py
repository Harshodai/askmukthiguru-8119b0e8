from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.assistant_authorization import list_visible_assistants, redeem_assistant_invite
from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_optional_user

router = APIRouter(prefix="/assistants", tags=["Assistants"])


class InviteRedeemRequest(BaseModel):
    invite_code: str = Field(..., min_length=1, max_length=256)


@router.get("")
async def assistants_catalog(
    user: Optional[dict] = Depends(get_optional_user),
    container: ServiceContainer = Depends(get_container),
):
    """Return public assistants plus the current user's authorized private assistants."""
    items = await list_visible_assistants(user, container)
    return {
        "assistants": [
            {
                "id": item.id,
                "slug": item.slug,
                "name": item.name,
                "description": item.description,
                "avatar_url": item.avatar_url,
                "starter_questions": list(item.starter_questions),
                "visibility": item.visibility,
            }
            for item in items
        ]
    }


@router.post("/redeem")
async def assistants_redeem(
    body: InviteRedeemRequest,
    user: Optional[dict] = Depends(get_optional_user),
    container: ServiceContainer = Depends(get_container),
):
    result = await redeem_assistant_invite(body.invite_code, user, container)
    return {"ok": True, **result}
