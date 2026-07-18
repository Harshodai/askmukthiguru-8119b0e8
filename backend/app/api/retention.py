from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase
from services.retention_service import STREAK_MILESTONES

router = APIRouter(prefix="/api/retention", tags=["retention"])
logger = logging.getLogger(__name__)


@router.get("/streak")
async def get_streak(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    uid = user.get("sub") or user.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    svc = getattr(container, "retention_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Retention service not available")
    state = await svc.get_streak(uid)
    return {
        "current": state.current,
        "longest": state.longest,
        "last_active": state.last_active,
        "freezes_available": state.freezes_available,
        "total_days": state.total_days,
        "at_risk": state.last_active is not None and svc._engine.at_risk(state),
    }


@router.post("/practice")
async def record_practice(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    uid = user.get("sub") or user.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    svc = getattr(container, "retention_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Retention service not available")
    before = await svc.get_streak(uid)
    state = await svc.record_practice(uid)
    is_new_milestone = (
        state.current in STREAK_MILESTONES
        and state.current != before.current
    )
    return {
        "current": state.current,
        "longest": state.longest,
        "freezes_available": state.freezes_available,
        "milestone": is_new_milestone,
    }


@router.get("/curve")
async def retention_curve(
    days: int = 30,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    if days < 1 or days > 365:
        raise HTTPException(
            status_code=422,
            detail="days must be between 1 and 365"
        )
    svc = getattr(container, "retention_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Retention service not available")
    curve = await svc.retention_curve(horizon_days=days)
    return curve
