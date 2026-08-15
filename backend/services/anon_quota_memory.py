"""In-memory sliding-window adapter for anonymous message quotas.

Used as a safe fallback when Redis is unavailable and in tests/sandboxes.
Thread-safe but not shared across processes — acceptable for dev or single-node
fall-back; production should use AnonQuotaRedisAdapter.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque

from services.anon_quota_port import AnonQuotaPort, QuotaResult


class AnonQuotaMemoryAdapter(AnonQuotaPort):
    """Per-process in-memory sliding window for anonymous message quotas."""

    def __init__(self) -> None:
        # Window members are (timestamp, reservation_id, claim_deadline)
        # tuples so release() can remove exactly the slot it was given and a
        # reservation never claimed by its deadline (a dropped queued job) is
        # reaped instead of burning a slot for the rest of the window. A None
        # deadline means the reservation was claimed and counts until natural
        # window expiry.
        self._windows: dict[str, deque[tuple[float, str, float | None]]] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        return time.monotonic()

    def _window_for(self, session_id: str) -> deque[tuple[float, str, float | None]]:
        if session_id not in self._windows:
            self._windows[session_id] = deque()
        return self._windows[session_id]

    def _prune(self, window: deque[tuple[float, str, float | None]], cutoff: float, now: float) -> None:
        while window and window[0][0] < cutoff:
            window.popleft()
        # Reap members whose claim deadline passed (dropped jobs). A full scan
        # rather than a head check: a committed head can sit in front of an
        # expired reservation whenever the claim deadline is shorter than the
        # window.
        expired = [i for i, (_, _, dl) in enumerate(window) if dl is not None and dl < now]
        for i in reversed(expired):
            del window[i]

    def _prune_empty_sessions(self, window_seconds: float) -> None:
        """Drop expired/empty session windows so idle sessions do not leak."""
        now = self._now()
        cutoff = now - window_seconds
        empty_sessions = [
            sid for sid, window in self._windows.items()
            if not window or window[-1][0] < cutoff
        ]
        for sid in empty_sessions:
            self._windows.pop(sid, None)

    def _result(
        self,
        window: deque[tuple[float, str, float | None]],
        limit: int,
        window_seconds: float,
        allowed: bool,
        reservation_id: str | None = None,
    ) -> QuotaResult:
        remaining = max(0, limit - len(window))
        retry_after: int | None = None
        if not allowed and window:
            retry_after = max(0, int(window[0][0] + window_seconds - self._now()) + 1)
        return QuotaResult(
            allowed=allowed,
            remaining=remaining,
            total_limit=limit,
            retry_after_seconds=retry_after,
            reservation_id=reservation_id,
        )

    async def check_and_record(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
        claim_ttl_seconds: float,
    ) -> QuotaResult:
        async with self._lock:
            self._prune_empty_sessions(window_seconds)
            window = self._window_for(session_id)
            now = self._now()
            cutoff = now - window_seconds
            self._prune(window, cutoff, now)
            allowed = len(window) < limit
            reservation_id: str | None = None
            if allowed:
                reservation_id = str(uuid.uuid4())
                window.append((now, reservation_id, now + claim_ttl_seconds))
            return self._result(window, limit, window_seconds, allowed, reservation_id)

    async def inspect(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
    ) -> QuotaResult:
        async with self._lock:
            self._prune_empty_sessions(window_seconds)
            window = self._window_for(session_id)
            now = self._now()
            cutoff = now - window_seconds
            self._prune(window, cutoff, now)
            remaining = max(0, limit - len(window))
            return QuotaResult(allowed=remaining > 0, remaining=remaining, total_limit=limit)

    async def reset(self, session_id: str) -> None:
        async with self._lock:
            self._windows.pop(session_id, None)

    async def claim(self, session_id: str, reservation_id: str) -> None:
        async with self._lock:
            window = self._windows.get(session_id)
            if not window:
                return
            for i, (_, rid, _) in enumerate(window):
                if rid == reservation_id:
                    window[i] = (window[i][0], rid, None)
                    break

    async def release(self, session_id: str, reservation_id: str) -> None:
        async with self._lock:
            window = self._windows.get(session_id)
            if not window:
                return
            for i, (_, rid, _) in enumerate(window):
                if rid == reservation_id:
                    del window[i]
                    break


if __name__ == "__main__":
    async def _self_check():
        adapter = AnonQuotaMemoryAdapter()
        sid = "anon:test"
        for i in range(6):
            r = await adapter.check_and_record(sid, 5, 1.0, 30.0)
            assert (i < 5) == r.allowed, f"iteration {i}: {r}"
        blocked = await adapter.inspect(sid, 5, 1.0)
        assert not blocked.allowed and blocked.remaining == 0
        await asyncio.sleep(1.05)
        refreshed = await adapter.check_and_record(sid, 5, 1.0, 30.0)
        assert refreshed.allowed, f"expected refresh after window, got {refreshed}"
        await adapter.reset(sid)
        empty = await adapter.inspect(sid, 5, 1.0)
        assert empty.remaining == 5
        # Release returns the slot so a failed interaction does not burn quota
        reserved = await adapter.check_and_record(sid, 5, 1.0, 30.0)
        assert reserved.reservation_id is not None
        await adapter.release(sid, reserved.reservation_id)
        assert (await adapter.inspect(sid, 5, 1.0)).remaining == 5
        # A claim keeps the slot until natural window expiry.
        claimed = await adapter.check_and_record(sid, 5, 1.0, 30.0)
        await adapter.claim(sid, claimed.reservation_id)
        assert (await adapter.inspect(sid, 5, 1.0)).remaining == 4
        # An unclaimed reservation past its deadline is reaped (dropped job).
        dropped = await adapter.check_and_record(sid, 5, 1.0, 0.05)
        assert dropped.reservation_id is not None
        await asyncio.sleep(0.06)
        assert (await adapter.inspect(sid, 5, 1.0)).remaining == 4
        print("anon_quota_memory OK")

    asyncio.run(_self_check())
