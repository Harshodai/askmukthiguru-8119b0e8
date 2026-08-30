"""Warm the semantic cache by running doctrine benchmark queries through the pipeline."""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

from app.dependencies import get_container
from app.main import app  # FastAPI app
from benchmarks.question_bank import (
    BEAUTIFUL_STATE,
    DEEKSHA_NEUROSCIENCE,
    FOUR_SACRED_SECRETS,
    MEDITATION,
    SOUL_SYNC,
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


import re

from app.sanitization import sanitize_log_input


def _mask_secret(val: Optional[str]) -> str:
    """Mask sensitive secrets/tokens as token[:4] + '***'."""
    if not val:
        return ""
    s = str(val)
    if len(s) <= 4:
        return "***"
    return f"{s[:4]}***"


def _redact_secrets(text: Optional[str]) -> str:
    """Redact bearer tokens, auth tokens, API keys, or secret headers from log output."""
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"(?i)(bearer\s+)([A-Za-z0-9_\-\.]{4})[A-Za-z0-9_\-\.]*", r"\1\2***", s)
    s = re.sub(
        r"(?i)(api[_-]?key|secret|password|auth[_-]?token|token|authorization)(\s*[:=]\s*['\"]?)([A-Za-z0-9_\-\.]{4})[A-Za-z0-9_\-\.]*(['\"]?)",
        r"\1\2\3***\4",
        s,
    )
    return s


async def warm() -> int:
    """Run all sample queries through the chat endpoint and populate cache."""
    import time

    from httpx import AsyncClient

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
                resp = await client.post(
                    "/api/chat",
                    json={
                        "messages": [],
                        "user_message": q,
                    },
                )
                if resp.status_code == 200:
                    cached += 1
            except Exception as exc:
                clean_exc = sanitize_log_input(_redact_secrets(str(exc)))
                print(f"  Query {i + 1} failed: {clean_exc}")
            dur = time.time() - start
            print(f"  [{i + 1}/{len(queries)}] Query processed ({dur:.1f}s)")
    print(f"Done. {cached}/{len(queries)} responses cached.")
    return cached


if __name__ == "__main__":
    result = asyncio.run(warm())
    sys.exit(0 if result else 1)
