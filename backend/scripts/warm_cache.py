#!/usr/bin/env python3
"""Cache Warmup Script — Pre-fills hot cache, exact cache, and semantic cache with FAQ queries.

Usage:
    cd backend && python scripts/warm_cache.py [--base-url http://localhost:8000]

Fires common spiritual FAQ queries through the /api/chat endpoint to populate all
cache tiers. After running, subsequent identical queries return in <10ms from hot cache.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from argparse import ArgumentParser
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"
CACHE_CAP = 6  # minutes to pause between batches (rate limit friendly)
BATCH_SIZE = 5   # queries per batch

# Common FAQ queries — these are real questions users ask
FAQ_QUERIES = [
    # Core teachings
    "What is the Beautiful State?",
    "What are the Four Sacred Secrets?",
    "Who are Sri Preethaji and Sri Krishnaji?",
    "What is Soul Sync meditation?",
    "What is Deeksha or Oneness Blessing?",
    # Practices
    "How do I practice breath awareness?",
    "What is the Serene Mind technique?",
    "How can I surrender to the divine?",
    "What is the power of intention?",
    "How do I release suffering?",
    # Foundational concepts
    "What is Ekam?",
    "What is consciousness?",
    "What is karma?",
    "What is dharma?",
    "What is meditation?",
    # Emotional wellness
    "How do I find inner peace?",
    "How do I handle anxiety?",
    "How do I cultivate gratitude?",
    "What is self-love?",
    "How do I let go of the past?",
    # Events & programs
    "What is Manifest 2026?",
    "What are the 12 powers?",
    "What is the Oneness Movement?",
    "Where is Ekam World Centre?",
    "How can I attend a satsang?",
]


def _build_payload(query: str) -> dict[str, Any]:
    return {
        "user_message": query,
        "messages": [],
        "session_id": f"warmup-{int(time.time())}",
        "language": "en",
    }


async def _warm_query(client: httpx.AsyncClient, base_url: str, query: str, index: int, total: int) -> dict[str, Any]:
    """Fire a single query and return timing metadata."""
    url = f"{base_url}/api/chat"
    payload = _build_payload(query)
    start = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, timeout=120.0)
        latency = (time.perf_counter() - start) * 1000
        status = "ok" if resp.status_code == 200 else f"err-{resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            cache_hit = data.get("cache_hit", False)
            route = data.get("route_decision", "unknown")
            latency_ms = data.get("latency_ms", 0)
        else:
            cache_hit = False
            route = "unknown"
            latency_ms = 0
        return {
            "query": query,
            "status": status,
            "latency_ms": round(latency, 1),
            "cache_hit": cache_hit,
            "route": route,
            "body_latency_ms": latency_ms,
            "index": index,
            "total": total,
        }
    except Exception as e:
        return {
            "query": query,
            "status": f"exc-{type(e).__name__}",
            "latency_ms": 0,
            "cache_hit": False,
            "route": "unknown",
            "body_latency_ms": 0,
            "index": index,
            "total": total,
        }


async def warm_cache(base_url: str = BASE_URL) -> None:
    """Warm all cache tiers by firing FAQ queries."""
    total = len(FAQ_QUERIES)
    print(f"🚀 Warming cache with {total} FAQ queries against {base_url}/api/chat")
    print("-" * 60)

    results: list[dict] = []
    async with httpx.AsyncClient() as client:
        for i in range(0, total, BATCH_SIZE):
            batch = FAQ_QUERIES[i : i + BATCH_SIZE]
            tasks = [_warm_query(client, base_url, q, j + i, total) for j, q in enumerate(batch)]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)

            for r in batch_results:
                indicator = "✅" if r["status"] == "ok" else "❌"
                print(f"{indicator} [{r['index'] + 1}/{r['total']}] {r['query'][:45]:<45} | {r['status']} | {r['latency_ms']:>6.1f}ms")

            if i + BATCH_SIZE < total:
                await asyncio.sleep(1.0)

    print("-" * 60)

    ok_count = sum(1 for r in results if r["status"] == "ok")
    avg_latency = sum(r["latency_ms"] for r in results) / max(len(results), 1)
    print(f"✅ Warmup complete: {ok_count}/{total} queries succeeded")
    print(f"📊 Average latency: {avg_latency:.1f}ms")
    print("🔥 Hot cache, Exact cache, and Semantic cache now pre-filled!")


if __name__ == "__main__":
    parser = ArgumentParser(description="Warm cache with FAQ queries")
    parser.add_argument("--base-url", default=BASE_URL, help="Base URL of the backend API")
    args = parser.parse_args()
    asyncio.run(warm_cache(base_url=args.base_url))
