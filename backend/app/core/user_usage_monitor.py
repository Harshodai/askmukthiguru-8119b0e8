"""
Per-user LLM call rate monitor (detect, not prevent).

Logs a warning when a user exceeds a threshold of LLM calls per minute.
This is purely observability — does not block requests.
"""

import logging
import time
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)

# Anonymous callers are keyed per session, so keys rotate; cap the dict.
MAX_TRACKED_KEYS = 10_000


class UserUsageMonitor:
    """In-memory sliding window counter per user.

    Thread-safe. Logs a warning when user exceeds `warn_threshold` calls
    within `window_seconds`. Cleanup of stale entries happens on every call.
    """

    def __init__(self, window_seconds: float = 60.0, warn_threshold: int = 30):
        self._window = window_seconds
        self._threshold = warn_threshold
        self._lock = Lock()
        self._calls: dict[str, list[float]] = defaultdict(list)

    def record(self, user_id: str) -> int:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            timestamps = self._calls[user_id]
            timestamps.append(now)
            timestamps[:] = [t for t in timestamps if t > cutoff]
            count = len(timestamps)
            if len(self._calls) > MAX_TRACKED_KEYS:
                self._evict(cutoff, keep=user_id)
        if count >= self._threshold:
            logger.warning(
                "User %s exceeded %d LLM calls in %.0fs (count=%d) — possible abuse probe",
                user_id[:12],
                self._threshold,
                self._window,
                count,
            )
        return count

    def _evict(self, cutoff: float, keep: str) -> None:
        """Caller holds the lock. Drop empty/expired keys, then oldest-active."""
        for k in [k for k, v in self._calls.items() if k != keep and (not v or v[-1] <= cutoff)]:
            del self._calls[k]
        # ponytail: O(n) sort only when still over cap (>10k live keys in one window)
        if len(self._calls) > MAX_TRACKED_KEYS:
            # evict down to 90% so the sort amortises over ~1k records
            target = MAX_TRACKED_KEYS * 9 // 10
            oldest = sorted((k for k in self._calls if k != keep), key=lambda k: self._calls[k][-1])
            for k in oldest[: len(self._calls) - target]:
                del self._calls[k]

    def count(self, user_id: str) -> int:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            timestamps = [t for t in self._calls.get(user_id, []) if t > cutoff]
            if timestamps:
                self._calls[user_id][:] = timestamps
            else:
                self._calls.pop(user_id, None)
            return len(timestamps)


_user_monitor = None


def get_user_monitor() -> UserUsageMonitor:
    global _user_monitor
    if _user_monitor is None:
        _user_monitor = UserUsageMonitor()
    return _user_monitor
