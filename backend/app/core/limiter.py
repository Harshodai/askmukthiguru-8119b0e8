import hmac
import logging
import os
import uuid

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings

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

    Benchmark requests must match BENCHMARK_SECRET — never JWT_SECRET. When the
    header matches (with hmac.compare_digest), we return a special key that is
    whitelisted, effectively bypassing the rate limiter. This prevents 429
    cascades during benchmark runs while still protecting production traffic
    from abuse.

    Health/readiness probes are exempt unconditionally — Railway health checks
    must never 429 or the deployment is marked unhealthy (cascading failure).
    """
    if request.url.path in _HEALTH_EXEMPT_PATHS:
        return f"health_exempt_{uuid.uuid4().hex}"

    benchmark_secret = getattr(settings, "benchmark_secret", "") or os.environ.get(
        "BENCHMARK_SECRET", ""
    )
    test_key = request.headers.get("X-Test-Key", "")

    if (
        settings.enable_test_auth
        and not settings.is_production
        and benchmark_secret
        and test_key
        and hmac.compare_digest(test_key, benchmark_secret)
    ):
        # Return a unique per-request key so it never accumulates
        return f"benchmark_exempt_{uuid.uuid4().hex}"

    return get_remote_address(request)


# Use Redis-backed storage only when REDIS_URL is explicitly configured and valid.
# Empty strings or invalid URIs must fall back to in-memory to keep tests and
# single-node local dev running without a Redis dependency.
_redis_url = os.environ.get("REDIS_URL", "").strip()
_redis_schemes = ("redis://", "rediss://", "unix://")

if _redis_url and _redis_url.lower().startswith(_redis_schemes):
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
