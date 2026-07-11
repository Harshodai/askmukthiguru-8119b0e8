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
        if count >= self._threshold:
            logger.warning(
                "User %s exceeded %d LLM calls in %.0fs (count=%d) — possible abuse probe",
                user_id[:12], self._threshold, self._window, count,
            )
        return count

    def count(self, user_id: str) -> int:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            timestamps = self._calls.get(user_id, [])
            timestamps[:] = [t for t in timestamps if t > cutoff]
            return len(timestamps)


_user_monitor = None


def get_user_monitor() -> UserUsageMonitor:
    global _user_monitor
    if _user_monitor is None:
        _user_monitor = UserUsageMonitor()
    return _user_monitor
