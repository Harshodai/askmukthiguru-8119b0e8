"""Aggregate /healthz endpoint for the FastAPI backend.

Exposes a single route that performs deep-health checks on Qdrant,
Redis, and Ollama and returns a combined status + per-service latency.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi import status as http_status

from app.dependencies import ServiceContainer, get_container

router = APIRouter(tags=["Health"])


async def _health_check(name: str, coro) -> dict:
    s = time.perf_counter()
    try:
        await asyncio.wait_for(coro, timeout=2.0)
        return {"name": name, "ok": True, "latency_ms": int((time.perf_counter() - s) * 1000)}
    except Exception as exc:
        return {"name": name, "ok": False, "error": str(exc)[:120]}


@router.get("/api/healthz")
async def healthz(container: ServiceContainer = Depends(get_container)) -> JSONResponse:
    """Aggregate deep-health check for Qdrant, Redis, and Ollama."""
    loop = asyncio.get_running_loop()

    async def _qdrant_coro() -> bool:
        return await loop.run_in_executor(None, container.qdrant.health_check)

    async def _redis_coro() -> bool:
        if container.exact_cache and getattr(container.exact_cache, "_redis", None):
            return await loop.run_in_executor(None, container.exact_cache._redis.ping)
        return False

    checks = await asyncio.gather(
        _health_check("qdrant", _qdrant_coro()),
        _health_check("redis", _redis_coro()),
        _health_check("ollama", container.ollama.health_check()),
    )
    ok = all(x["ok"] for x in checks)
    return JSONResponse(
        {"ok": ok, "checks": checks},
        status_code=http_status.HTTP_200_OK if ok else http_status.HTTP_503_SERVICE_UNAVAILABLE,
    )
