from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.telemetry_db import get_recent_traces
from services.auth_service import get_current_user_from_supabase

admin_router = APIRouter(
    tags=["admin"],
)

@admin_router.get("/traces")
async def fetch_telemetry_traces(
    limit: int = 50,
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Fetch recent traces for Admin UI. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_recent_traces(min(limit, 200))

@admin_router.get("/prompts")
async def fetch_prompts(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return []

@admin_router.get("/evaluations")
async def fetch_evaluations(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return []
@admin_router.get("/kpis")
async def fetch_kpis(
    from_date: str = None,
    to_date: str = None,
    user: Dict = Depends(get_current_user_from_supabase),
) -> Dict[str, Any]:
    """Fetch aggregated KPIs for Admin UI. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from app.telemetry_db import get_kpis
    return await get_kpis(from_date, to_date)
