import logging
import os
import uuid

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.security_utils import is_benchmark_request

logger = logging.getLogger(__name__)

_HEALTH_EXEMPT_PATHS = frozenset(
    {
        "/api/health",
        "/api/healthz",
        "/api/ready",
        "/metrics",
        "/health",
    }
)


def _rate_limit_key_func(request: Request) -> str:
    """Custom key function that exempts benchmark + health-check requests from rate limiting.

    Benchmark exemption is delegated to the shared ``is_benchmark_request``
    guard (constant-time BENCHMARK_SECRET compare, config-only, gated to
    ENABLE_TEST_AUTH=true AND non-production) — never JWT_SECRET, never a raw
    os.environ read. On a match we return a unique per-request key so it is
    effectively whitelisted, preventing 429 cascades during benchmark runs
    while production traffic stays protected.

    Health/readiness probes are exempt unconditionally — Railway health checks
    must never 429 or the deployment is marked unhealthy (cascading failure).

    Behind Railway's edge, ``get_remote_address`` reads the per-request client
    IP that uvicorn's ``--proxy-headers`` populates from X-Forwarded-For (see
    start_railway.py), so each seeker gets their own bucket instead of all
    traffic collapsing onto the edge IP.
    """
    if request.url.path in _HEALTH_EXEMPT_PATHS:
        return f"health_exempt_{uuid.uuid4().hex}"

    if is_benchmark_request(request):
        # Return a unique per-request key so it never accumulates
        return f"benchmark_exempt_{uuid.uuid4().hex}"

    return get_remote_address(request)


# Tests can request a dedicated in-memory limiter while still supplying
# REDIS_URL to application services that require a real integration dependency.
# Production never sets this override: it must use the configured Redis-backed
# limiter rather than silently creating a per-pod budget.
_rate_limit_storage_uri = os.environ.get("RATE_LIMIT_STORAGE_URI", "").strip()
_redis_url = os.environ.get("REDIS_URL", "").strip()
_redis_schemes = ("redis://", "rediss://", "unix://")


# Live chaos-testing discovery (2026-09-05, chat production audit): when
# Redis becomes unreachable AFTER startup (not just a cold-start probe),
# slowapi's Redis-backed limiter raised redis.exceptions.ConnectionError
# uncaught from inside the route dependency chain, turning EVERY request —
# not just rate-limit checks — into an HTTP 500. This directly violated the
# documented invariant (root CLAUDE.md, "Redis Degradation": no request may
# fail with 500 on a Redis outage) and was never live-tested before. slowapi
# has first-class support for exactly this: in_memory_fallback_enabled
# switches the limiter to a per-pod in-memory backend the first time the
# configured storage raises, so rate limiting keeps working (just no longer
# cross-pod) instead of the request itself failing. swallow_errors is the
# last-resort backstop if even that fallback path raises for some other
# reason — the request proceeds unlimited rather than 500ing.
_REDIS_OUTAGE_KWARGS = {
    "in_memory_fallback_enabled": True,
    "in_memory_fallback": ["200/minute"],
    "swallow_errors": True,
}

if _rate_limit_storage_uri:
    logger.info("Rate limiting uses explicit storage override")
    limiter = Limiter(
        key_func=_rate_limit_key_func,
        storage_uri=_rate_limit_storage_uri,
        default_limits=["200/minute"],
        **_REDIS_OUTAGE_KWARGS,
    )
elif _redis_url and _redis_url.lower().startswith(_redis_schemes):
    logger.info("Rate limiting backed by Redis")
    limiter = Limiter(
        key_func=_rate_limit_key_func,
        storage_uri=_redis_url,
        default_limits=["200/minute"],  # High default for benchmark key
        **_REDIS_OUTAGE_KWARGS,
    )
else:
    if _redis_url:
        logger.warning(
            f"REDIS_URL '{_redis_url[:20]}...' is not a valid Redis URI; "
            "rate-limit storage is in-memory (per pod)."
        )
    else:
        logger.warning(
            "REDIS_URL not set; rate-limit storage is in-memory (per pod). "
            "Deploy REDIS_URL env var for cross-pod rate limiting."
        )
    limiter = Limiter(
        key_func=_rate_limit_key_func,
        default_limits=["200/minute"],
    )
