"""In-memory sliding-window adapter for anonymous message quotas.

Used as a safe fallback when Redis is unavailable and in tests/sandboxes.
Thread-safe but not shared across processes — acceptable for dev or single-node
fall-back; production should use AnonQuotaRedisAdapter.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import ClassVar

from services.anon_quota_port import AnonQuotaPort, QuotaResult


class AnonQuotaMemoryAdapter(AnonQuotaPort):
    """Per-process in-memory sliding window for anonymous message quotas."""

    _windows: ClassVar[dict[str, deque[float]]] = {}
    _lock = asyncio.Lock()

    def _now(self) -> float:
        return time.monotonic()

    def _window_for(self, session_id: str) -> deque[float]:
        if session_id not in self._windows:
            self._windows[session_id] = deque()
        return self._windows[session_id]

    def _prune(self, window: deque[float], cutoff: float) -> None:
        while window and window[0] < cutoff:
            window.popleft()

    def _result(self, window: deque[float], limit: int, window_seconds: float, allowed: bool) -> QuotaResult:
        remaining = max(0, limit - len(window))
        retry_after: int | None = None
        if not allowed and window:
            retry_after = max(0, int(window[0] + window_seconds - self._now()) + 1)
        return QuotaResult(
            allowed=allowed,
            remaining=remaining,
            total_limit=limit,
            retry_after_seconds=retry_after,
        )

    async def check_and_record(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
    ) -> QuotaResult:
        async with self._lock:
            window = self._window_for(session_id)
            now = self._now()
            cutoff = now - window_seconds
            self._prune(window, cutoff)
            allowed = len(window) < limit
            if allowed:
                window.append(now)
            return self._result(window, limit, window_seconds, allowed)

    async def inspect(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
    ) -> QuotaResult:
        async with self._lock:
            window = self._window_for(session_id)
            cutoff = self._now() - window_seconds
            self._prune(window, cutoff)
            remaining = max(0, limit - len(window))
            return QuotaResult(allowed=remaining > 0, remaining=remaining, total_limit=limit)

    async def reset(self, session_id: str) -> None:
        async with self._lock:
            self._windows.pop(session_id, None)


if __name__ == "__main__":
    async def _self_check():
        adapter = AnonQuotaMemoryAdapter()
        sid = "anon:test"
        for i in range(6):
            r = await adapter.check_and_record(sid, 5, 1.0)
            assert (i < 5) == r.allowed, f"iteration {i}: {r}"
        blocked = await adapter.inspect(sid, 5, 1.0)
        assert not blocked.allowed and blocked.remaining == 0
        await asyncio.sleep(1.05)
        refreshed = await adapter.check_and_record(sid, 5, 1.0)
        assert refreshed.allowed, f"expected refresh after window, got {refreshed}"
        await adapter.reset(sid)
        empty = await adapter.inspect(sid, 5, 1.0)
        assert empty.remaining == 5
        print("anon_quota_memory OK")

    asyncio.run(_self_check())
