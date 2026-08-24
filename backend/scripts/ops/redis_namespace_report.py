"""Read-only Redis namespace cardinality and TTL report.

This script never reads values and never mutates Redis. It samples fixed key
patterns so operational identifiers and user-derived labels cannot create
unbounded output cardinality. Use it inside the Railway backend/worker image.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics

NAMESPACES: dict[str, str] = {
    "exact_query_cache": "mukthiguru:cache:*",
    "semantic_query_cache": "mukthiguru:semcache:*",
    "jobs": "job:*",
    "anonymous_quota": "anon_quota:*",
    "sessions": "session:*",
    "telemetry": "telemetry:*",
    "rate_limits": "rl:*",
    "second_brain": "second_brain:*",
}


def _summarize(client, pattern: str, scan_limit: int) -> dict:
    keys = 0
    expiring = 0
    nonexpiring = 0
    ttl_values: list[int] = []
    truncated = False
    for key in client.scan_iter(match=pattern, count=500):
        keys += 1
        ttl = int(client.ttl(key))
        if ttl == -2:
            continue
        if ttl < 0:
            nonexpiring += 1
        else:
            expiring += 1
            ttl_values.append(ttl)
        if keys >= scan_limit:
            truncated = True
            break

    return {
        "pattern": pattern,
        "keys_sampled": keys,
        "scan_limit": scan_limit,
        "truncated": truncated,
        "expiring_keys": expiring,
        "nonexpiring_keys": nonexpiring,
        "ttl_seconds_min": min(ttl_values) if ttl_values else None,
        "ttl_seconds_median": int(statistics.median(ttl_values)) if ttl_values else None,
        "ttl_seconds_max": max(ttl_values) if ttl_values else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", ""))
    parser.add_argument("--scan-limit", type=int, default=100_000)
    args = parser.parse_args()
    if not args.redis_url:
        raise SystemExit("REDIS_URL is required")
    if args.scan_limit < 1 or args.scan_limit > 1_000_000:
        raise SystemExit("--scan-limit must be between 1 and 1000000")

    import redis

    client = redis.from_url(
        args.redis_url,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=10,
    )
    client.ping()
    info = client.info(section="memory")
    report = {
        "read_only": True,
        "redis_used_memory_bytes": info.get("used_memory"),
        "redis_maxmemory_bytes": info.get("maxmemory"),
        "namespaces": {
            name: _summarize(client, pattern, args.scan_limit)
            for name, pattern in NAMESPACES.items()
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
