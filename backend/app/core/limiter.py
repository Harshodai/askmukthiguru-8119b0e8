import logging
import os
import uuid

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.security_utils import is_benchmark_request

logger = logging.getLogger(__name__)

_HEALTH_EXEMPT_PATHS = frozenset({
    "/api/health",
    "/api/healthz",
    "/api/ready",
    "/metrics",
    "/health",
})


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

if _rate_limit_storage_uri:
    logger.info("Rate limiting uses explicit storage override")
    limiter = Limiter(
        key_func=_rate_limit_key_func,
        storage_uri=_rate_limit_storage_uri,
        default_limits=["200/minute"],
    )
elif _redis_url and _redis_url.lower().startswith(_redis_schemes):
    logger.info("Rate limiting backed by Redis")
    limiter = Limiter(
        key_func=_rate_limit_key_func,
        storage_uri=_redis_url,
        default_limits=["200/minute"],  # High default for benchmark key
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
