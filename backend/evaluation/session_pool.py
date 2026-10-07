"""Benchmark Anonymous Session Pool — Distributed Systems Evaluation Invariant B1.

Pre-mints and leases persistent anonymous session tokens to benchmark workers.
Eliminates the 5 requests / 60 seconds rate limit bottleneck on `/api/auth/anon-session`,
reducing full benchmark suite runtime from ~17 hours to ~2-3 hours.

Invariants:
1. Warmup spacing: Pre-mint calls are spaced by >= 12.5s (4.8 req/min < 5 req/min limit).
2. Token reuse: Tokens are stateless HMAC signatures with indefinite lifetime; workers
   reuse leased tokens across questions.

Do NOT wire this into bench.py (tried and reverted 2026-09-26): /api/chat
enforces an anonymous quota of 5 messages per session per 24 h, so a reused
token gets a 429 with Retry-After ~24 h after five questions and the run
stalls for a day. The benchmark mints one session per question instead; at its
pace that stays under the anon-session limit. Reuse would only work with an
authenticated or quota-exempt benchmark identity.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class BenchmarkSessionPool:
    """Pre-mints and leases persistent anonymous session tokens to workers."""

    def __init__(
        self,
        endpoint: str,
        pool_size: int = 4,
        client: Optional[httpx.AsyncClient] = None,
        warmup_delay_s: float = 12.5,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.pool_size = max(1, pool_size)
        self._external_client = client
        self._warmup_delay_s = warmup_delay_s
        self._pool: asyncio.Queue[str] = asyncio.Queue()
        self._warmed = False

    async def warm_up(self) -> int:
        """
        Pre-mint anonymous session tokens respecting the 5 req / 60s rate limit.
        Returns the number of successfully minted tokens.
        """
        client = self._external_client or httpx.AsyncClient()
        minted = 0
        try:
            logger.info(
                "Warming up benchmark session pool (size=%d, delay=%.1fs)...",
                self.pool_size,
                self._warmup_delay_s,
            )
            for i in range(self.pool_size):
                url = f"{self.endpoint}/api/auth/anon-session"
                resp = await client.post(url, timeout=15.0)
                resp.raise_for_status()
                data = resp.json()
                token = data.get("token") or data.get("session_id")
                if not token:
                    raise ValueError(f"No token returned from {url}: {data}")
                await self._pool.put(token)
                minted += 1
                logger.info(
                    "Minted session %d/%d (token_prefix=%s)",
                    minted,
                    self.pool_size,
                    token[:12],
                )
                if i < self.pool_size - 1 and self._warmup_delay_s > 0:
                    await asyncio.sleep(self._warmup_delay_s)
            self._warmed = True
        finally:
            if not self._external_client:
                await client.aclose()
        return minted

    def add_token(self, token: str) -> None:
        """Add an externally minted or pre-computed HMAC token to the pool."""
        self._pool.put_nowait(token)
        self._warmed = True

    @property
    def is_warmed(self) -> bool:
        return self._warmed

    @property
    def available_count(self) -> int:
        return self._pool.qsize()

    @asynccontextmanager
    async def acquire_session(self) -> AsyncGenerator[str, None]:
        """Lease a session token to a worker task and return it on completion."""
        token = await self._pool.get()
        try:
            yield token
        finally:
            await self._pool.put(token)
