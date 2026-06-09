"""Warm the semantic cache by running doctrine benchmark queries through the pipeline."""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

from app.main import app  # FastAPI app
from app.dependencies import get_container
from benchmarks.question_bank import (
    FOUR_SACRED_SECRETS,
    DEEKSHA_NEUROSCIENCE,
    SOUL_SYNC,
    BEAUTIFUL_STATE,
    MEDITATION,
)


def _collect_sample_queries() -> list[str]:
    """Gather a representative sample of doctrine queries."""
    queries: list[str] = []
    for bank in (FOUR_SACRED_SECRETS, DEEKSHA_NEUROSCIENCE, SOUL_SYNC, BEAUTIFUL_STATE, MEDITATION):
        for _, q in bank:
            queries.append(q)
    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped[:120]


async def warm() -> int:
    """Run all sample queries through the chat endpoint and populate cache."""
    from httpx import AsyncClient
    import time

    container = get_container()
    if not container.semantic_cache:
        print("No semantic cache configured; exiting.")
        return 0

    queries = _collect_sample_queries()
    print(f"Warming cache with {len(queries)} queries...")
    cached = 0
    async with AsyncClient(app=app, base_url="http://test") as client:
        for i, q in enumerate(queries):
            start = time.time()
            try:
                resp = await client.post("/api/chat", json={
                    "messages": [],
                    "user_message": q,
                })
                if resp.status_code == 200:
                    cached += 1
            except Exception as exc:
                print(f"  Query {i + 1} failed: {exc}")
            dur = time.time() - start
            print(f"  [{i + 1}/{len(queries)}] {q[:50]}... ({dur:.1f}s)")
    print(f"Done. {cached}/{len(queries)} responses cached.")
    return cached


if __name__ == "__main__":
    result = asyncio.run(warm())
    sys.exit(0 if result else 1)
