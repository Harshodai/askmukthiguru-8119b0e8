"""Aggregate health, readiness, circuit-breaker, and metrics endpoints."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi import status as http_status

from app.config import settings
import app.dependencies as _app_deps
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
        logger.warning("Health check %s failed: %s", name, exc)
        return {"name": name, "ok": False, "error": "unhealthy"}


@router.get("/api/healthz")
async def healthz() -> JSONResponse:
    """Liveness probe for Railway. Returns 200 always — Railway needs a simple
    alive/dead check, not deep service dependency checks (which live in /api/health).
    Deep checks cause deployment boot-loops when any dependency has a transient blip."""
    return JSONResponse(
        {"ok": True, "status": "alive"},
        status_code=http_status.HTTP_200_OK,
    )


@router.get("/api/health")
async def health_endpoint(container: ServiceContainer = Depends(get_container)) -> JSONResponse:
    """Comprehensive service health with go/no-go status for each service.

    Returns per-service status, latency, and an overall 'ready' flag.
    Useful for debugging startup hangs and production monitoring.
    """
    if not _app_deps.startup_complete:
        return JSONResponse({
            "ready": False,
            "status": "starting",
            "message": "Server is still starting up",
            "startup_error": _app_deps.startup_error,
            "services": {},
        })

    loop = asyncio.get_running_loop()
    results = {}

    async def check(name: str, coro, critical: bool = False):
        s = time.perf_counter()
        try:
            ok = await asyncio.wait_for(coro, timeout=3.0)
            latency = int((time.perf_counter() - s) * 1000)
            results[name] = {"ok": ok, "latency_ms": latency, "critical": critical}
        except asyncio.TimeoutError:
            results[name] = {"ok": False, "latency_ms": 3000, "critical": critical, "error": "timeout"}
        except Exception as exc:
            results[name] = {"ok": False, "latency_ms": int((time.perf_counter() - s) * 1000), "critical": critical, "error": str(exc)[:200]}

    # Infrastructure
    await check("qdrant", loop.run_in_executor(None, container.qdrant.health_check), critical=True)
    await check("redis", _check_redis(container), critical=True)
    await check("neo4j", _check_neo4j(container), critical=False)

    # LLM
    await check("llm", container.ollama.health_check(), critical=True)

    # Embedding
    try:
        embed_ok = container.embedding._encoder is not None
        results["embedding"] = {"ok": embed_ok, "latency_ms": 0, "critical": True}
    except Exception as exc:
        results["embedding"] = {"ok": False, "latency_ms": 0, "critical": True, "error": str(exc)[:200]}

    # Guardrails
    results["guardrails"] = {
        "ok": container.guardrails.is_available,
        "latency_ms": 0,
        "critical": False,
        "provider": container.guardrails.provider_name,
    }

    # Caches
    results["exact_cache"] = {
        "ok": container.exact_cache.is_available if container.exact_cache else False,
        "latency_ms": 0,
        "critical": False,
    }
    results["semantic_cache"] = {
        "ok": container.semantic_cache.is_available if container.semantic_cache else False,
        "latency_ms": 0,
        "critical": False,
    }

    # Graphs
    results["fast_graph"] = {"ok": container.fast_graph is not None, "latency_ms": 0, "critical": True}
    results["standard_graph"] = {"ok": container.standard_graph is not None, "latency_ms": 0, "critical": True}
    results["deep_graph"] = {"ok": container.deep_graph is not None, "latency_ms": 0, "critical": False}

    # Job Queue
    results["job_queue"] = {
        "ok": getattr(container, "job_queue", None) is not None,
        "latency_ms": 0,
        "critical": False,
        "queue_size": getattr(container.job_queue, "queue_size", 0) if getattr(container, "job_queue", None) else 0,
    }

    # LightRAG
    results["lightrag"] = {
        "ok": not container.lightrag_degraded,
        "latency_ms": 0,
        "critical": True,
    }

    # OCR
    await check("ocr", loop.run_in_executor(None, container.ocr.health_check), critical=False)

    # Overall
    critical_ok = all(v["ok"] for v in results.values() if v.get("critical"))
    all_ok = all(v["ok"] for v in results.values())

    return JSONResponse({
        "ready": critical_ok,
        "status": "healthy" if all_ok else ("degraded" if critical_ok else "unhealthy"),
        "services": results,
    })


async def _check_redis(container) -> bool:
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.close()
        return True
    except Exception:
        return False


async def _check_neo4j(container) -> bool:
    try:
        driver = container.neo4j_driver
        if driver is None:
            return False
        with driver.session() as session:
            session.run("RETURN 1")
        return True
    except Exception:
        return False


@router.get("/api/health/services")
async def services_health_endpoint(container: ServiceContainer = Depends(get_container)) -> JSONResponse:
    """Alias for /api/health — comprehensive service health with go/no-go per service."""
    return await health_endpoint(container)


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


def _require_admin(user: dict) -> None:
    if not user or not user.get("is_superuser"):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/api/circuit-breaker/status")
async def circuit_breaker_status(
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_current_user_from_supabase),
) -> dict:
    """
    Get circuit breaker status for all registered providers. Admin only.
    """
    _require_admin(user)
    try:
        registry = container.circuit_breaker_registry
        if not registry:
            return {"status": "error", "message": "Circuit breaker registry not initialized"}

        all_stats = registry.get_all_stats()
        active_provider = registry.get_active_provider()

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
        return {"status": "error", "message": "internal_error"}


@router.get("/api/circuit-breaker/reset")
async def circuit_breaker_reset_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
) -> dict:
    """Manually reset the active circuit breaker to CLOSED. Admin only."""
    _require_admin(user)
    try:
        container = get_container()
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
        logger.info(f"Circuit breaker [{provider}] manually reset (was {previous_state}) → CLOSED by admin {user.get('id')}")
        return {
            "status": "ok",
            "provider": provider,
            "previous_state": previous_state,
            "current_state": "closed",
            "message": f"Circuit breaker for {provider} has been reset.",
        }
    except AttributeError as e:
        logger.error(f"Circuit breaker reset failed: {e}")
        return {
            "status": "error",
            "message": "Could not access circuit breaker.",
        }


@router.get("/api/debug/headers")
async def debug_headers(
    request: Request,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict:
    """Debug endpoint. Disabled in production; admin-only otherwise."""
    if getattr(settings, "is_production", True):
        raise HTTPException(status_code=404, detail="Not found")
    _require_admin(user)
    headers = dict(request.headers)
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
    """Prometheus metrics endpoint. Admin only — may expose system internals."""
    _require_admin(user)
    data, content_type = metrics_endpoint()
    return Response(content=data, media_type=content_type)
