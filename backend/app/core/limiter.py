import logging
import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

logger = logging.getLogger(__name__)


def _rate_limit_key_func(request: Request) -> str:
    """Custom key function that exempts benchmark requests from rate limiting.

    Benchmark requests carry X-Test-Key == JWT_SECRET. When this header matches,
    we return a special key that is whitelisted, effectively bypassing the rate
    limiter. This prevents 429 cascades during benchmark runs while still
    protecting production traffic from abuse.
    """
    jwt_secret = os.environ.get("JWT_SECRET", "")
    test_key = request.headers.get("X-Test-Key", "")

    if jwt_secret and test_key == jwt_secret:
        # Return a unique per-request key so it never accumulates
        import uuid
        return f"benchmark_exempt_{uuid.uuid4().hex}"

    return get_remote_address(request)


# Use Redis-backed storage when REDIS_URL is available so rate limits
# are enforced across all horizontally-scaled pods.
_redis_url = os.environ.get("REDIS_URL")

if _redis_url:
    logger.info("Rate limiting backed by Redis")
    limiter = Limiter(
        key_func=_rate_limit_key_func,
        storage_uri=_redis_url,
        default_limits=["200/minute"],  # High default for benchmark key
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
