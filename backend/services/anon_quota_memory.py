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

# Capacity of a per-session window deque. Slots beyond this cannot be tracked
# in memory: a limit above this would be silently under-enforced, so such
# limits are rejected instead.
_MAX_WINDOW_SIZE = 200


class AnonQuotaMemoryAdapter(AnonQuotaPort):
    """Per-process in-memory sliding window for anonymous message quotas."""

    def __init__(self, max_sessions: int = 500, max_limit: int | None = None) -> None:
        # Window members are (timestamp, reservation_id, claim_deadline)
        # tuples so release() can remove exactly the slot it was given and a
        # reservation never claimed by its deadline (a dropped queued job) is
        # reaped instead of burning a slot for the rest of the window. A None
        # deadline means the reservation was claimed and counts until natural
        # window expiry.
        self._max_sessions = max_sessions
        # Optional cap on the per-call limit (degraded mode): the effective
        # limit becomes min(caller_limit, max_limit).
        self._max_limit = max_limit
        self._windows: dict[str, deque[tuple[float, str, float | None]]] = {}
        self._lock = asyncio.Lock()

    def _effective_limit(self, limit: int) -> int:
        """Apply the configured cap, then reject limits the window cannot enforce."""
        if self._max_limit is not None:
            limit = min(limit, self._max_limit)
        if limit > _MAX_WINDOW_SIZE:
            raise ValueError(
                f"limit {limit} exceeds in-memory window capacity {_MAX_WINDOW_SIZE}"
            )
        return limit

    def _now(self) -> float:
        return time.monotonic()

    def _window_for(self, session_id: str) -> deque[tuple[float, str, float | None]]:
        if session_id not in self._windows:
            self._windows[session_id] = deque(maxlen=_MAX_WINDOW_SIZE)
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
        """Drop expired/empty session windows and enforce max_sessions capacity so memory is bounded."""
        now = self._now()
        cutoff = now - window_seconds
        empty_sessions = [
            sid for sid, window in self._windows.items()
            if not window or window[-1][0] < cutoff
        ]
        for sid in empty_sessions:
            self._windows.pop(sid, None)

        if len(self._windows) >= self._max_sessions:
            excess = len(self._windows) - self._max_sessions + 1
            sorted_sessions = sorted(
                self._windows.items(),
                key=lambda item: item[1][-1][0] if item[1] else 0.0,
            )
            for sid, _ in sorted_sessions[:excess]:
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
        limit = self._effective_limit(limit)
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
        limit = self._effective_limit(limit)
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
        # Limits the deque cannot enforce are rejected, not silently truncated.
        for bad_limit in (201, 1000):
            try:
                await adapter.check_and_record(sid, bad_limit, 1.0, 30.0)
                raise AssertionError(f"limit {bad_limit} should be rejected")
            except ValueError:
                pass
        # The degraded cap is applied before the capacity validation.
        capped = AnonQuotaMemoryAdapter(max_limit=3)
        r = await capped.check_and_record(sid, 5, 1.0, 30.0)
        assert r.total_limit == 3
        print("anon_quota_memory OK")

    asyncio.run(_self_check())
