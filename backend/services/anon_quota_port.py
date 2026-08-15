"""Anonymous message-quota port (Clean Architecture).

The quota domain is intentionally tiny: a single question "can this
anonymous session send one more message?" with a sliding window. Ports
hide whether the window lives in Redis, memory, or a future SQL table.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class QuotaResult:
    """Result of an anonymous quota check."""

    allowed: bool
    remaining: int
    total_limit: int
    retry_after_seconds: int | None = None

    @property
    def quota_exceeded(self) -> bool:
        return not self.allowed


class AnonQuotaPort(ABC):
    """Storage-agnostic anonymous message-quota port."""

    @abstractmethod
    async def check_and_record(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
    ) -> QuotaResult:
        """Atomically record one message and return the resulting quota state."""

    @abstractmethod
    async def inspect(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
    ) -> QuotaResult:
        """Return current quota state without recording a new message."""

    @abstractmethod
    async def reset(self, session_id: str) -> None:
        """Clear the quota window for a session (e.g. after sign-up)."""


if __name__ == "__main__":
    from dataclasses import asdict

    ok = QuotaResult(allowed=True, remaining=4, total_limit=5)
    blocked = QuotaResult(allowed=False, remaining=0, total_limit=5, retry_after_seconds=3600)
    assert ok.allowed and not ok.quota_exceeded
    assert not blocked.allowed and blocked.quota_exceeded
    print("anon_quota_port OK", asdict(ok))
