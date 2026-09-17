"""Aggregate health, readiness, circuit-breaker, and metrics endpoints."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from fastapi.responses import JSONResponse, Response

import app.dependencies as _app_deps
from app.config import settings
from app.dependencies import ServiceContainer, get_container, get_container_async
from app.metrics import HEALTH_CHECK_TOTAL, metrics_endpoint
from app.runtime_artifacts import inspect_runtime_artifacts
from app.runtime_metrics import observe_queue_depths
from app.sanitization import sanitize_log_input
from services.auth_service import get_current_user_from_supabase, require_aal2

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)

# Dedicated bounded pool for this module's own blocking probes (qdrant,
# embedding, exact-cache telemetry, OCR, neo4j/memgraph). Deliberately
# separate from asyncio's shared default executor, which chat traffic's
# embedding/rerank/memory/admin calls also compete for (see
# services/embedding_service.py's _EMBED_EXECUTOR for the same pattern) --
# a healthcheck that queues behind chat-traffic thread starvation cannot
# report on that starvation. Small and fixed: this is a liveness probe, not
# a workload.
_HEALTH_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="health-check")

# Hard ceiling on /api/health's total wall time, independent of how many
# downstream checks misbehave or how their individual per-check timeouts
# compose. 2026-09 incident: /api/health itself hung for minutes under
# concurrent load with no response at all -- per-check asyncio.wait_for()
# timeouts only bound a check that actually yields to the event loop
# (see the _check_neo4j fix below for one that didn't), and even where they
# do bound correctly, checks ran serially, so the worst case was the SUM of
# every per-check timeout, not the max. This wraps the whole check sequence
# so the endpoint always answers by this deadline no matter what.
_HEALTH_HARD_BOUND_SECONDS = 12.0


def _availability_flag(service) -> bool:
    """Return a JSON-safe availability flag for optional service adapters.

    Adapters expose ``is_available`` as a boolean in production, but test doubles
    and partially initialized plugins may expose truthy sentinel objects. Never
    place those objects directly in a JSON response.
    """
    if service is None:
        return False
    return bool(getattr(service, "is_available", False))


_MANUAL_RESET_COOLDOWN_SECONDS = 30.0
_manual_reset_lock = threading.Lock()
_manual_reset_last: dict[str, float] = {}


async def _claim_manual_reset_slot(operator_id: str) -> tuple[bool, int]:
    """Claim a global reset slot; production fails closed if Redis is down."""
    key = f"askmukthiguru:circuit-reset:{operator_id}"
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            acquired = await client.set(
                key, str(time.time()), nx=True, ex=int(_MANUAL_RESET_COOLDOWN_SECONDS)
            )
            if acquired:
                return True, 0
            ttl = await client.ttl(key)
            return False, max(1, int(ttl))
        finally:
            await client.aclose()
    except Exception as exc:
        if getattr(settings, "is_production", True):
            logger.error("Circuit reset rate-limit Redis unavailable; failing closed: %s", exc)
            return False, int(_MANUAL_RESET_COOLDOWN_SECONDS)
        # Local/test fallback only. Development must still exercise a cooldown.
        now = time.monotonic()
        with _manual_reset_lock:
            previous_reset = _manual_reset_last.get(operator_id)
            if previous_reset is not None and now - previous_reset < _MANUAL_RESET_COOLDOWN_SECONDS:
                return False, int(_MANUAL_RESET_COOLDOWN_SECONDS - (now - previous_reset)) + 1
            _manual_reset_last[operator_id] = now
        return True, 0


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
async def health_endpoint(
    container: ServiceContainer = Depends(get_container_async),
) -> JSONResponse:
    """Comprehensive service health with go/no-go status for each service.

    Returns per-service status, latency, and an overall 'ready' flag. Hard-
    bounded to _HEALTH_HARD_BOUND_SECONDS total wall time regardless of how
    downstream checks behave -- see that constant's docstring.
    """
    try:
        return await asyncio.wait_for(
            _build_health_response(container), timeout=_HEALTH_HARD_BOUND_SECONDS
        )
    except TimeoutError:
        HEALTH_CHECK_TOTAL.labels(result="not_ready").inc()
        logger.error(
            "/api/health exceeded its %ss hard bound; returning unhealthy without waiting further",
            _HEALTH_HARD_BOUND_SECONDS,
        )
        return JSONResponse(
            {
                "ready": False,
                "status": "unhealthy",
                "message": f"health check exceeded {_HEALTH_HARD_BOUND_SECONDS}s hard bound",
                "services": {},
            },
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def _build_health_response(container: ServiceContainer) -> JSONResponse:
    if not _app_deps.startup_complete:
        HEALTH_CHECK_TOTAL.labels(result="not_ready").inc()
        return JSONResponse(
            {
                "ready": False,
                "status": "starting",
                "message": "Server is still starting up",
                "startup_error": _app_deps.startup_error,
                "services": {},
            }
        )

    loop = asyncio.get_running_loop()
    results = {}

    async def check(name: str, coro, critical: bool = False) -> None:
        s = time.perf_counter()
        try:
            ok = await asyncio.wait_for(coro, timeout=3.0)
            latency = int((time.perf_counter() - s) * 1000)
            results[name] = {"ok": ok, "latency_ms": latency, "critical": critical}
        except TimeoutError:
            results[name] = {
                "ok": False,
                "latency_ms": 3000,
                "critical": critical,
                "error": "timeout",
            }
        except Exception as exc:
            logger.exception("Health check failed for %s: %s", name, exc)
            results[name] = {
                "ok": False,
                "latency_ms": int((time.perf_counter() - s) * 1000),
                "critical": critical,
                "error": "Service check failed",
            }

    # Infrastructure
    await check(
        "qdrant",
        loop.run_in_executor(_HEALTH_EXECUTOR, container.qdrant.health_check),
        critical=True,
    )
    await check("redis", _check_redis(container), critical=True)
    await check("neo4j", _check_neo4j(container), critical=False)

    # LLM
    # health_check() alone pings the provider's raw HTTP endpoint directly --
    # every provider adapter (Sarvam/Ollama/OpenRouter/NIM) does this without
    # consulting its own circuit breaker, so a wedged-OPEN breaker (the
    # 2026-09-15 incident: every chat rejected in 11ms by the breaker while
    # this very ping succeeded at 216ms) still reports "llm: ok". The
    # breaker's own read-only probe (is_circuit_open(), same fix that closed
    # that incident on the request-gating path in PipelineCoordinator) must
    # also gate this status signal, or the signal stays unfalsifiable by the
    # exact failure it exists to catch.
    await check("llm", container.ollama.health_check(), critical=True)
    if results["llm"]["ok"] and getattr(container.ollama, "is_circuit_open", None):
        try:
            if container.ollama.is_circuit_open():
                results["llm"]["ok"] = False
                results["llm"]["error"] = "circuit_open"
        except Exception as exc:
            logger.debug("LLM circuit probe failed during health check: %s", exc)

    # Embedding — S7: functional probe. The old check (`_encoder is not None`)
    # was presence, not function: a primary loaded at the wrong dimension passed
    # it while every dense search 400s. Encode one token and verify the vector
    # width equals the configured dimension (also warms a cold encoder).
    try:
        emb_svc = container.embedding

        # H-FALSE-5: this must exercise the same _EMBED_EXECUTOR pool live chat
        # queries use, not a separate _HEALTH_EXECUTOR — a starved/exhausted
        # _EMBED_EXECUTOR is exactly the failure this probe exists to catch,
        # and a health check that runs on its own private executor can't see it.
        async def _probe_async():
            async_method = getattr(emb_svc, "encode_single_full_async", None)
            if inspect.iscoroutinefunction(async_method):
                r = await async_method("ok")
                return r.get("dense")
            if hasattr(emb_svc, "encode_single_full"):
                return await asyncio.to_thread(
                    lambda: emb_svc.encode_single_full("ok").get("dense")
                )
            r = await asyncio.to_thread(emb_svc.encode, "ok")
            return r.get("dense") if isinstance(r, dict) else r

        vec = await asyncio.wait_for(_probe_async(), timeout=5.0)
        dim = len(vec) if vec is not None else None
        embed_ok = dim == settings.embedding_dimension
        results["embedding"] = {
            "ok": bool(embed_ok),
            "latency_ms": 0,
            "critical": True,
            "dim": dim,
        }
        if not embed_ok:
            results["embedding"]["error"] = (
                f"dim {dim} != configured {settings.embedding_dimension}"
            )
    except Exception as exc:
        logger.exception("Embedding health check failed: %s", exc)
        results["embedding"] = {
            "ok": False,
            "latency_ms": 0,
            "critical": True,
            "error": "Embedding check failed",
        }

    # Curated knowledge inputs are a critical readiness dependency. Keep the
    # complete artifact report in deep health while using its required-only
    # signal for the release decision; an optional reranker cache may be cold.
    artifact_report = inspect_runtime_artifacts()
    results["runtime_artifacts"] = {
        "ok": bool(artifact_report.get("readiness_ok", False)),
        "latency_ms": 0,
        "critical": True,
        "missing_required": artifact_report.get("missing_required", []),
        "present": artifact_report.get("present", 0),
        "total": artifact_report.get("total", 0),
    }

    # Guardrails — normalize mock/optional service values before JSON encoding.
    guardrails_available = bool(getattr(container.guardrails, "is_available", False))
    guardrails_provider = getattr(container.guardrails, "provider_name", "unknown")
    if not isinstance(guardrails_provider, str):
        guardrails_provider = "unknown"
    results["guardrails"] = {
        "ok": guardrails_available,
        "latency_ms": 0,
        "critical": False,
        "provider": guardrails_provider,
    }

    # Caches
    results["exact_cache"] = {
        "ok": _availability_flag(container.exact_cache),
        "latency_ms": 0,
        "critical": False,
    }
    if container.exact_cache and hasattr(container.exact_cache, "telemetry_snapshot"):
        try:
            cache_snapshot = await loop.run_in_executor(
                _HEALTH_EXECUTOR, container.exact_cache.telemetry_snapshot
            )
            if not isinstance(cache_snapshot, dict):
                cache_snapshot = {}
            snapshot_values = {
                "keys": cache_snapshot.get("keys", 0),
                "nonexpiring_keys": cache_snapshot.get("nonexpiring", 0),
                "max_keys": cache_snapshot.get("max_keys", 0),
            }
            for key, value in snapshot_values.items():
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    snapshot_values[key] = 0
            results["exact_cache"].update(snapshot_values)
        except Exception as exc:
            logger.debug("Exact-cache telemetry unavailable during health check: %s", exc)
    results["semantic_cache"] = {
        "ok": _availability_flag(container.semantic_cache),
        "latency_ms": 0,
        "critical": False,
    }

    # Graphs
    results["fast_graph"] = {
        "ok": container.fast_graph is not None,
        "latency_ms": 0,
        "critical": True,
    }
    results["standard_graph"] = {
        "ok": container.standard_graph is not None,
        "latency_ms": 0,
        "critical": True,
    }
    results["deep_graph"] = {
        "ok": container.deep_graph is not None,
        "latency_ms": 0,
        "critical": False,
    }
    graph_warmup_status = getattr(container, "graph_warmup_status", "unknown")
    if graph_warmup_status not in {"warming_up", "ready"}:
        graph_warmup_status = "unknown"
    results["graph_warmup"] = {
        "ok": graph_warmup_status in {"warming_up", "ready"},
        "status": graph_warmup_status,
        "latency_ms": 0,
        "critical": False,
    }

    job_queue = getattr(container, "job_queue", None)
    queue_size = getattr(job_queue, "queue_size", 0) if job_queue else 0
    if not isinstance(queue_size, (int, float)) or isinstance(queue_size, bool):
        queue_size = 0
    observe_queue_depths({"job": queue_size})
    # Job Queue
    results["job_queue"] = {
        "ok": job_queue is not None,
        "latency_ms": 0,
        "critical": False,
        "queue_size": queue_size,
    }

    # P1-OPS-8: chat admission-control contention (per-replica semaphore)
    from app.api.chat import get_chat_backpressure

    backpressure = dict(get_chat_backpressure() or {})
    for key in ("max_concurrent", "in_flight"):
        value = backpressure.get(key, 0)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            backpressure[key] = 0
    backpressure["admission_limited"] = bool(backpressure.get("admission_limited", False))
    # ok was hardcoded True regardless of admission_limited -- the signal
    # could never go red for the exact condition (chat semaphore saturated,
    # new requests stalling) it reports on. Same invariant violation as the
    # llm/circuit-breaker gap above: falsifiable by nothing.
    results["chat_backpressure"] = {
        "ok": not backpressure["admission_limited"],
        "latency_ms": 0,
        "critical": False,
        **backpressure,
    }

    # LightRAG
    # critical=False (2026-09-06, prod-readiness fix): root CLAUDE.md's own
    # failover invariant documents LightRAG/Neo4j degradation as a graceful
    # fallback (retrieval drops to pure Qdrant + BM25), not a hard failure —
    # and rag/nodes/retrieval.py's retrieve_documents always calls
    # retrieve_for_single_query with lightrag=None regardless, so this
    # component isn't even reachable from the live chat path today. Marking
    # it critical meant a single slow Neo4j session at boot (init has a 120s
    # timeout with no retry) permanently failed /api/health's `ready` flag
    # for the rest of the process lifetime, which would take an otherwise
    # healthy pod out of rotation forever under any real readiness probe.
    results["lightrag"] = {
        "ok": not container.lightrag_degraded,
        "latency_ms": 0,
        "critical": False,
    }

    # OCR
    await check(
        "ocr", loop.run_in_executor(_HEALTH_EXECUTOR, container.ocr.health_check), critical=False
    )

    # Overall
    critical_ok = all(v["ok"] for v in results.values() if v.get("critical"))
    all_ok = all(v["ok"] for v in results.values())

    HEALTH_CHECK_TOTAL.labels(result="ready" if critical_ok else "not_ready").inc()

    return JSONResponse(
        {
            "ready": critical_ok,
            "status": "healthy" if all_ok else ("degraded" if critical_ok else "unhealthy"),
            "services": results,
        }
    )


async def _check_redis(container) -> bool:
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.close()
        return True
    except Exception:
        return False


def _check_neo4j_sync(container) -> bool:
    try:
        driver = container.neo4j_driver
        if driver is None:
            return False
        with driver.session() as session:
            session.run("RETURN 1")
        return True
    except Exception:
        return False


async def _check_neo4j(container) -> bool:
    """Async wrapper around the synchronous Memgraph/Neo4j driver call.

    The driver's session()/run() are blocking calls with no `await` inside
    them, so a bare `async def` wrapping them directly (as this used to be)
    has no yield point for asyncio.wait_for()'s timeout to act on -- a slow
    or hung driver call would block the single event-loop thread itself,
    not just this one check, freezing every other request in the process
    (including this same endpoint's other checks). Routed through the
    dedicated _HEALTH_EXECUTOR so it can actually be bounded and can't be
    starved by chat traffic's own to_thread() calls.
    """
    return await asyncio.get_running_loop().run_in_executor(
        _HEALTH_EXECUTOR, _check_neo4j_sync, container
    )


@router.get("/api/health/services")
async def services_health_endpoint(
    container: ServiceContainer = Depends(get_container_async),
) -> JSONResponse:
    """Alias for /api/health — comprehensive service health with go/no-go per service."""
    return await health_endpoint(container)


@router.get("/api/health/mfa")
async def health_mfa(user: dict = Depends(require_aal2)) -> dict:
    """Probe endpoint for MFA step-up (AAL2) enforcement.

    Returns 200 only when the caller has aal='aal2' on their identity.
    Useful for verifying require_aal2 wiring and for release readiness checks.
    """
    return {"ok": True, "aal": "aal2"}


@router.get("/api/ready")
async def readiness_endpoint(
    container: ServiceContainer = Depends(get_container_async),
) -> JSONResponse:
    """
    Kubernetes readiness probe endpoint.

    Unlike /api/health (liveness), this checks that critical services
    (Qdrant vector DB, LLM provider) are ready to serve requests.
    Returns 503 if not ready.
    """
    health = await container.health_status()

    # Check circuit breaker via the public LLMProvider.is_circuit_open() probe.
    # H-FALSE-1 (2026-09-17): the old implementation drilled into _service._circuit
    # (a private path tied to the pre-refactor provider shape). The new provider
    # hierarchy exposes is_circuit_open() on LLMProvider base (services/llm/base.py)
    # and has no _service._circuit, so the hasattr guards silently fell through to
    # circuit_breaker_ok=True even when the breaker was OPEN — the same invariant
    # violation as F1 (closed in /api/health via BaseCircuitBreaker.is_open()). Use
    # the same public probe here so both endpoints are consistent: non-reserving
    # (does not consume a half-open slot) and provider-shape-agnostic.
    circuit_breaker_ok = True
    circuit_state = "unknown"
    try:
        _is_open_fn = getattr(container.ollama, "is_circuit_open", None)
        if callable(_is_open_fn):
            if _is_open_fn():
                circuit_breaker_ok = False
                circuit_state = "open"
            else:
                circuit_state = "closed"
    except Exception as _cb_exc:
        logger.debug("Circuit breaker probe failed in /api/ready: %s", _cb_exc)

    critical_ok = health.get("qdrant", False) and health.get("ollama", False) and circuit_breaker_ok

    if not critical_ok:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "qdrant": health.get("qdrant", False),
                "llm": health.get("ollama", False),
                "circuit_breaker": circuit_state,
                "message": "Critical services not ready"
                if (health.get("qdrant", False) and health.get("ollama", False))
                else "Circuit breaker OPEN",
            },
        )

    return JSONResponse(
        {
            "ready": True,
            "qdrant": True,
            "llm": True,
            "circuit_breaker": circuit_state,
            "total_chunks": -1,  # Redacted
        }
    )


def _require_admin(user: dict) -> None:
    if not user or not user.get("is_superuser"):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/api/circuit-breaker/status")
async def circuit_breaker_status(
    container: ServiceContainer = Depends(get_container_async),
    user: dict = Depends(require_aal2),
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


@router.post("/api/circuit-breaker/reset")
async def circuit_breaker_reset_endpoint(
    user: dict = Depends(require_aal2),
) -> dict:
    """Manually reset the active circuit breaker to CLOSED. Admin only."""
    _require_admin(user)
    operator_id = str(user.get("id") or "unknown")
    allowed, retry_after = await _claim_manual_reset_slot(operator_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Circuit-breaker reset is temporarily rate limited",
            headers={"Retry-After": str(retry_after)},
        )
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
        active_breaker.reset(reason="manual_reset")
        logger.info(
            "Circuit breaker manually reset",
            extra={
                "provider": provider,
                "previous_state": previous_state,
                "operator_id": sanitize_log_input(operator_id),
                "action": "circuit_breaker_reset",
            },
        )
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
    auth_headers = {
        k: v
        for k, v in headers.items()
        if k.lower() in ("authorization", "cookie", "x-test-key", "content-type")
    }
    return {
        "all_headers_count": len(headers),
        "auth_headers": auth_headers,
        "has_authorization": "authorization" in headers,
        "has_cookie": "cookie" in headers,
        "has_x_test_key": "x-test-key" in headers,
    }


@router.get("/metrics")
async def get_metrics(user: dict = Depends(require_aal2)) -> Response:
    """Prometheus metrics endpoint. Admin only — may expose system internals."""
    _require_admin(user)
    data, content_type = metrics_endpoint()
    return Response(content=data, media_type=content_type)
