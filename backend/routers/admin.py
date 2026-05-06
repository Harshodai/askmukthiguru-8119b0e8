from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.telemetry_db import get_recent_traces
from services.auth_service import current_active_user
from models.user import User as AuthUser

admin_router = APIRouter(
    tags=["admin"],
    dependencies=[Depends(current_active_user)],
)

@admin_router.get("/traces")
async def fetch_telemetry_traces(
    limit: int = 50,
    user: AuthUser = Depends(current_active_user),
) -> List[Dict[str, Any]]:
    """Fetch recent traces for Admin UI. Requires authentication."""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_recent_traces(min(limit, 200))

@admin_router.get("/prompts")
async def fetch_prompts(
    user: AuthUser = Depends(current_active_user),
) -> List[Dict[str, Any]]:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return []

@admin_router.get("/evaluations")
async def fetch_evaluations(
    user: AuthUser = Depends(current_active_user),
) -> List[Dict[str, Any]]:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return []
