from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from app.telemetry_db import get_recent_traces

admin_router = APIRouter(tags=["admin"])

@admin_router.get("/traces")
async def fetch_telemetry_traces(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent traces for Admin UI."""
    return await get_recent_traces(limit)

# Add mock endpoints for other Admin UI routes to prevent 404s during transition
@admin_router.get("/prompts")
async def fetch_prompts() -> List[Dict[str, Any]]:
    return []

@admin_router.get("/evaluations")
async def fetch_evaluations() -> List[Dict[str, Any]]:
    return []
