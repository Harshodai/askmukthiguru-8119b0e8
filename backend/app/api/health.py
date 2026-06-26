"""Aggregate health, readiness, circuit-breaker, and metrics endpoints."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from fastapi import status as http_status

from app.config import settings
from app.dependencies import ServiceContainer, get_container
from app.metrics import metrics_endpoint
from services.auth_service import get_current_user_from_supabase
from services.circuit_breaker import CircuitState

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


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


@router.get("/api/health")
async def health_endpoint(container: ServiceContainer = Depends(get_container)) -> JSONResponse:
    """
    Health check endpoint.

    Returns status of all backend services and total indexed chunks.
    """
    health = await container.health_status()

    # Only core services determine healthy/degraded status
    # Optional services (OCR, guardrails) don't affect overall health
    core_services = {"qdrant", "embedding", "ollama"}  # ollama = universal LLM provider
    all_healthy = all(v for k, v in health.items() if k in core_services)

    body = {
        "status": "healthy" if all_healthy else "degraded",
        "services": {
            k: (v if isinstance(v, bool) else True)
            for k, v in health.items()
            if k not in ["qdrant_count", "guardrails_provider"]
        },
        "total_chunks": 0 if not all_healthy else -1,  # Redact exact count
    }
    return JSONResponse(body)


@router.get("/api/ready")
async def readiness_endpoint(container: ServiceContainer = Depends(get_container)) -> JSONResponse:
    """
    Kubernetes readiness probe endpoint.

    Unlike /api/health (liveness), this checks that critical services
    (Qdrant vector DB, LLM provider) are ready to serve requests.
    Returns 503 if not ready.
    """
    health = await container.health_status()

    # Check circuit breaker for Sarvam Cloud
    circuit_breaker_ok = True
    circuit_state = "unknown"
    if hasattr(container.ollama, "_service"):
        svc = container.ollama._service
        if hasattr(svc, "_circuit"):
            circuit_state = svc._circuit.get_state().value
            circuit_breaker_ok = circuit_state == "closed"

    critical_ok = health.get("qdrant", False) and health.get("ollama", False) and circuit_breaker_ok

    if not critical_ok:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "qdrant": health.get("qdrant", False),
                "llm": health.get("ollama", False),
                "circuit_breaker": circuit_state,
                "message": "Critical services not ready" if (health.get("qdrant", False) and health.get("ollama", False)) else "Circuit breaker OPEN",
            },
        )

    return JSONResponse({
        "ready": True,
        "qdrant": True,
        "llm": True,
        "circuit_breaker": circuit_state,
        "total_chunks": -1,  # Redacted
    })


@router.get("/api/circuit-breaker/status")
async def circuit_breaker_status(container: ServiceContainer = Depends(get_container)) -> dict:
    """
    Get circuit breaker status for all registered providers.

    Useful for debugging circuit breaker state without needing to reset it.
    """
    try:
        registry = container.circuit_breaker_registry
        if not registry:
            return {"status": "error", "message": "Circuit breaker registry not initialized"}

        all_stats = registry.get_all_stats()
        active_provider = registry.get_active_provider()

        # Also check the Sarvam service circuit breaker directly
        sarvam_circuit = None
        if hasattr(container.ollama, "_service"):
            svc = container.ollama._service
            if hasattr(svc, "_circuit"):
                sarvam_circuit = svc._circuit.get_stats()

        return {
            "status": "ok",
            "active_provider": active_provider,
            "registry_breakers": all_stats,
            "sarvam_service_circuit": sarvam_circuit,
            "llm_provider_config": container.ollama.__class__.__name__,
        }
    except Exception as e:
        logger.error(f"Circuit breaker status failed: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/api/circuit-breaker/reset")
async def circuit_breaker_reset_endpoint() -> dict:
    """
    Manually reset the active circuit breaker to CLOSED.

    Use when the circuit has been OPEN for a long time (e.g. after
    a temporary API outage) and you want to allow traffic immediately
    instead of waiting for the auto-recovery timeout.

    Works with any LLM provider (Sarvam, Ollama, OpenRouter, etc.)
    based on the currently active provider in the registry.
    """
    # Access the circuit breaker through the dependency container
    try:
        container = get_container()
        # Use provider-agnostic circuit breaker registry
        active_breaker = container.circuit_breaker_registry.get_active()
        if not active_breaker:
            return {
                "status": "error",
                "message": "No active circuit breaker found. Check LLM_PROVIDER config.",
            }

        provider = container.circuit_breaker_registry.get_active_provider()
        previous_state = active_breaker.get_state().value
        active_breaker._state = CircuitState.CLOSED
        active_breaker._failures = 0
        active_breaker._last_failure_time = None
        active_breaker._half_open_calls = 0
        logger.info(f"Circuit breaker [{provider}] manually reset (was {previous_state}) → CLOSED")
        return {
            "status": "ok",
            "provider": provider,
            "previous_state": previous_state,
            "current_state": "closed",
            "message": f"Circuit breaker for {provider} has been reset. New requests will be attempted.",
        }
    except AttributeError as e:
        logger.error(f"Circuit breaker reset failed: {e}")
        return {
            "status": "error",
            "message": "Could not access circuit breaker. Ensure services are initialized.",
        }


@router.get("/api/debug/headers")
async def debug_headers(request: Request) -> dict:
    """Debug endpoint to see what headers are received."""
    headers = dict(request.headers)
    # Filter for auth-related headers
    auth_headers = {k: v for k, v in headers.items() if k.lower() in ('authorization', 'cookie', 'x-test-key', 'content-type')}
    return {
        "all_headers_count": len(headers),
        "auth_headers": auth_headers,
        "has_authorization": "authorization" in headers,
        "has_cookie": "cookie" in headers,
        "has_x_test_key": "x-test-key" in headers,
    }


@router.get("/metrics")
async def get_metrics(user: dict = Depends(get_current_user_from_supabase)) -> Response:
    """Prometheus metrics endpoint."""
    data, content_type = metrics_endpoint()
    return Response(content=data, media_type=content_type)
