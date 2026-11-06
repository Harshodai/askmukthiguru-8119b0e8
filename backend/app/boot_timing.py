"""Boot-time measurement (NEW-RW-8, RW-06).

Records how long each start-up phase takes and logs one line, so the first Railway
deploy shows the real number behind runbook risk R-5 (LightRAG wait of up to 120 s
plus background init of up to 180 s, against a 330 s deploy healthcheck).

No behaviour depends on this module. It never raises into the caller.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import contextmanager


def worst_case_boot_seconds(*, lightrag_timeout_s: float, background_timeout_s: float) -> float:
    """Longest the two bounded start-up phases can take together."""
    return lightrag_timeout_s + background_timeout_s


class BootTimer:
    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._t0: float | None = None
        self._phases: list[tuple[str, float, str, float | None]] = []

    def start(self) -> None:
        self._t0 = self._now()

    def record(
        self, name: str, seconds: float, *, outcome: str = "ok", budget_s: float | None = None
    ) -> None:
        self._phases.append((name, seconds, outcome, budget_s))

    def mark_last(self, outcome: str) -> None:
        """Relabel the outcome of the most recent phase (for example "timeout")."""
        if self._phases:
            name, seconds, _, budget = self._phases[-1]
            self._phases[-1] = (name, seconds, outcome, budget)

    @contextmanager
    def phase(self, name: str, *, budget_s: float | None = None):
        began = self._now()
        outcome = "ok"
        try:
            yield
        except BaseException:
            outcome = "failed"
            raise
        finally:
            self.record(name, self._now() - began, outcome=outcome, budget_s=budget_s)

    def total_seconds(self) -> float:
        if self._t0 is None:
            return 0.0
        return self._now() - self._t0

    def summary(self, *, accepting: bool) -> str:
        parts = []
        for name, seconds, outcome, budget in self._phases:
            text = f"{name}={seconds:.1f}s"
            if budget is not None:
                text += f"/{budget:g}s"
            if outcome != "ok":
                text += f"({outcome})"
            parts.append(text)
        parts.append(f"total={self.total_seconds():.1f}s")
        parts.append(f"accepting={'yes' if accepting else 'no'}")
        return "Boot timing: " + " ".join(parts)

    def log(
        self,
        logger: logging.Logger,
        *,
        healthcheck_timeout_s: float,
        margin_s: float = 30.0,
        accepting: bool = True,
    ) -> None:
        """Log the summary. Warn if the measured phases leave under `margin_s`
        of the deploy healthcheck budget (import time before lifespan is not in
        this total, so a thin margin here is already a red flag)."""
        try:
            logger.info(self.summary(accepting=accepting))
            phase_total = sum(seconds for _, seconds, _, _ in self._phases)
            if healthcheck_timeout_s - phase_total < margin_s:
                logger.warning(
                    "Boot margin under %.0fs: phases took %.1fs of the %.0fs deploy healthcheck "
                    "(import time not included). Consider a LightRAG skip flag (runbook R-5).",
                    margin_s,
                    phase_total,
                    healthcheck_timeout_s,
                )
        except Exception:  # pragma: no cover - logging must never break startup
            logger.debug("boot timing log failed", exc_info=True)
