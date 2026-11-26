"""
Scoped cache invalidation tool.

Purges stale response/semantic caches without performing a global Redis flush,
strictly adhering to Invariant X35.

Preserves:
- Spend tracking (openrouter-spend:*)
- Quota limits (anon_quota:*)
- Background jobs (job:*)
- Celery queues

Usage:
    backend/.venv/bin/python scripts/ops/flush_stale_runtime_cache.py --redis-url redis://...
"""

import argparse
import logging
import sys

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CACHE_PATTERNS = [
    "mukthiguru:semcache:*",
    "mukthiguru:cache:*",
    "cache:first_person_exact:*",
    "spiritual_expansion:*",
]

def purge_stale_cache(redis_url: str) -> int:
    client = redis.from_url(redis_url)
    total_deleted = 0

    for pattern in CACHE_PATTERNS:
        cursor = 0
        pattern_keys = []
        while True:
            cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
            pattern_keys.extend(keys)
            if cursor == 0:
                break

        if pattern_keys:
            deleted = client.delete(*pattern_keys)
            total_deleted += deleted
            logger.info("Purged %d keys matching pattern '%s'", deleted, pattern)
        else:
            logger.info("No keys matched pattern '%s'", pattern)

    logger.info("Scoped cache purge completed. Total stale keys deleted: %d", total_deleted)
    return total_deleted

def main():
    parser = argparse.ArgumentParser(description="Purge stale runtime response caches from Redis.")
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379",
        help="Redis connection URL (e.g. redis://:password@localhost:6379/0)",
    )
    args = parser.parse_args()

    try:
        purge_stale_cache(args.redis_url)
    except Exception as e:
        logger.error("Failed to purge Redis cache: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
