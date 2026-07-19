"""Cache tier metrics, observability, and invalidation endpoints.

Exposes hit rates, sizes, and health for all cache tiers:
  1. Hot cache (in-memory dict)
  2. Exact cache (Redis key-value)
  3. Semantic cache (Qdrant vector search)
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase
from services.hot_cache import hot_cache

logger = logging.getLogger(__name__)

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
    except Exception:
        exact_stats = {"available": False, "error": "unavailable"}

    # --- Semantic cache (Qdrant, ~20-50ms) ---
    semantic_stats = {"available": False, "size": None}
    try:
        if container.semantic_cache and container.semantic_cache.is_available:
            if hasattr(container.semantic_cache, "stats"):
                semantic_stats = container.semantic_cache.stats()
            else:
                semantic_stats = {"available": True}
    except Exception:
        semantic_stats = {"available": False, "error": "unavailable"}

    return JSONResponse({
        "timestamp": int(time.time()),
        "tiers": {
            "hot": hot_stats,
            "exact": exact_stats,
            "semantic": semantic_stats,
        },
    })


@router.post("/admin/clear-cache")
async def clear_cache(
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_current_user_from_supabase),
) -> JSONResponse:
    """Flush all cache tiers. Admin only.

    Invalidates:
      - Hot cache (in-memory LRU)
      - Exact cache (Redis key-value)
      - Semantic cache (Qdrant vector-search collection)
    """
    if not user or not user.get("is_superuser"):
        raise HTTPException(status_code=403, detail="Admin access required")

    results: dict[str, str] = {}

    # 1. Hot cache
    try:
        hot_cache.clear()
        results["hot"] = "cleared"
    except Exception as e:
        results["hot"] = f"error: {e}"
        logger.warning("hot cache clear failed: %s", e)

    # 2. Exact cache (Redis)
    try:
        if container.exact_cache:
            container.exact_cache.invalidate_all()
            results["exact"] = "cleared"
        else:
            results["exact"] = "not available"
    except Exception as e:
        results["exact"] = f"error: {e}"
        logger.warning("exact cache clear failed: %s", e)

    # 3. Semantic cache (Qdrant)
    try:
        if container.semantic_cache and container.semantic_cache.is_available:
            container.semantic_cache.invalidate_all()
            results["semantic"] = "cleared"
        else:
            results["semantic"] = "not available"
    except Exception as e:
        results["semantic"] = f"error: {e}"
        logger.warning("semantic cache clear failed: %s", e)

    return JSONResponse({
        "status": "ok",
        "tiers": results,
    })
