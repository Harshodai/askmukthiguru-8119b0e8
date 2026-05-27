import logging
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Use Redis-backed storage when REDIS_URL is available so rate limits
# are enforced across all horizontally-scaled pods.
_redis_url = os.environ.get("REDIS_URL")

if _redis_url:
    logger.info("Rate limiting backed by Redis")
    limiter = Limiter(key_func=get_remote_address, storage_uri=_redis_url)
else:
    logger.warning(
        "REDIS_URL not set; rate-limit storage is in-memory (per pod). "
        "Deploy REDIS_URL env var for cross-pod rate limiting."
    )
    limiter = Limiter(key_func=get_remote_address)
