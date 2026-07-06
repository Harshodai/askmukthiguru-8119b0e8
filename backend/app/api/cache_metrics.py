"""Cache tier metrics and observability endpoint.

Exposes hit rates, sizes, and health for all cache tiers:
  1. Hot cache (in-memory dict)
  2. Exact cache (Redis key-value)
  3. Semantic cache (Qdrant vector search)
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase
from services.hot_cache import hot_cache

router = APIRouter(tags=["Metrics"])


@router.get("/api/metrics/cache")
async def cache_metrics(
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_current_user_from_supabase),
) -> JSONResponse:
    """Return cache tier statistics for production monitoring. Admin only."""
    if not user or not user.get("is_superuser"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    # --- Hot cache (in-memory, <1ms) ---
    hot_stats = hot_cache.stats()

    # --- Exact cache (Redis, ~1-5ms) ---
    exact_stats = {"available": False, "size": None}
    try:
        if container.exact_cache:
            # Support get_stats() or fallback to basic info
            if hasattr(container.exact_cache, "stats"):
                exact_stats = container.exact_cache.stats()
            elif hasattr(container.exact_cache, "keys"):
                exact_stats = {
                    "available": True,
                    "size": len(container.exact_cache.keys()) if callable(container.exact_cache.keys) else None,
                }
            else:
                exact_stats = {"available": True}
    except Exception as e:
        exact_stats = {"available": False, "error": str(e)[:120]}

    # --- Semantic cache (Qdrant, ~20-50ms) ---
    semantic_stats = {"available": False, "size": None}
    try:
        if container.semantic_cache and container.semantic_cache.is_available:
            if hasattr(container.semantic_cache, "stats"):
                semantic_stats = container.semantic_cache.stats()
            else:
                semantic_stats = {"available": True}
    except Exception as e:
        semantic_stats = {"available": False, "error": str(e)[:120]}

    return JSONResponse({
        "timestamp": int(time.time()),
        "tiers": {
            "hot": hot_stats,
            "exact": exact_stats,
            "semantic": semantic_stats,
        },
    })
