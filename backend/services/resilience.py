"""
Mukthi Guru — Distributed Resilience & Backoff Module

Implements AWS Well-Architected exponential backoff with Full Jitter:
    sleep = random.uniform(0, min(max_delay_s, base_delay_s * (2 ** (attempt - 1))))

Prevents synchronization and thundering-herd retry storms during downstream
service throttling and transient outages.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, Optional, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FullJitterBackoff:
    """Configurable exponential backoff with AWS Full Jitter."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_s: float = 0.5,
        max_delay_s: float = 15.0,
        retry_exceptions: tuple[type[Exception], ...] = (
            TimeoutError,
            ConnectionError,
            httpx.HTTPError,
        ),
        is_retryable: Optional[Callable[[Exception], bool]] = None,
        sleep_fn: Optional[Callable[[float], Awaitable[None]]] = None,
    ) -> None:
        if max_retries < 1:
            raise ValueError(f"max_retries must be >= 1, got {max_retries}")
        if base_delay_s <= 0:
            raise ValueError(f"base_delay_s must be > 0, got {base_delay_s}")
        if max_delay_s < base_delay_s:
            raise ValueError(
                f"max_delay_s ({max_delay_s}) must be >= base_delay_s ({base_delay_s})"
            )

        self.max_retries = max_retries
        self.base_delay_s = base_delay_s
        self.max_delay_s = max_delay_s
        self.retry_exceptions = retry_exceptions
        self.is_retryable = is_retryable
        self.sleep_fn = sleep_fn or asyncio.sleep

    def compute_ceiling(self, attempt: int) -> float:
        """Calculate the deterministic exponential backoff ceiling for a given attempt (1-indexed)."""
        return min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))

    def compute_delay(self, attempt: int) -> float:
        """Calculate random delay uniformly drawn from [0, ceiling]."""
        ceiling = self.compute_ceiling(attempt)
        return random.uniform(0.0, ceiling)

    def should_retry(self, exc: Exception) -> bool:
        """Determine if an exception qualifies for retry."""
        if self.is_retryable is not None:
            return bool(self.is_retryable(exc))
        return isinstance(exc, self.retry_exceptions)

    async def execute(
        self,
        coro_fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute the coroutine function with Full Jitter retries."""
        fn_name = getattr(coro_fn, "__name__", str(coro_fn))

        for attempt in range(1, self.max_retries + 1):
            try:
                return await coro_fn(*args, **kwargs)
            except Exception as exc:
                if not self.should_retry(exc):
                    logger.debug(
                        "Non-retryable exception in %s on attempt %d: %s (%s)",
                        fn_name,
                        attempt,
                        type(exc).__name__,
                        exc,
                    )
                    raise

                if attempt >= self.max_retries:
                    logger.error(
                        "Exhausted all %d retries for %s. Final error: %s (%s)",
                        self.max_retries,
                        fn_name,
                        type(exc).__name__,
                        exc,
                    )
                    raise

                delay = self.compute_delay(attempt)
                ceiling = self.compute_ceiling(attempt)
                logger.warning(
                    "Transient error in %s (attempt %d/%d): %s (%s). "
                    "Retrying in %.3fs (Full Jitter ceiling: %.3fs)",
                    fn_name,
                    attempt,
                    self.max_retries,
                    type(exc).__name__,
                    exc,
                    delay,
                    ceiling,
                )
                await self.sleep_fn(delay)

        raise RuntimeError("Unexpected end of retry loop without return or raise")


async def call_with_full_jitter(
    coro_fn: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 3,
    base_delay_s: float = 0.5,
    max_delay_s: float = 15.0,
    retry_exceptions: tuple[type[Exception], ...] = (
        TimeoutError,
        ConnectionError,
        httpx.HTTPError,
    ),
    is_retryable: Optional[Callable[[Exception], bool]] = None,
    sleep_fn: Optional[Callable[[float], Awaitable[None]]] = None,
    **kwargs: Any,
) -> T:
    """
    Executes an async callable with AWS Well-Architected exponential backoff and Full Jitter.

    Args:
        coro_fn: An async callable that returns an awaitable (invoked fresh on each attempt).
        *args: Positional arguments for coro_fn.
        max_retries: Total number of attempts allowed before raising (default 3).
        base_delay_s: Initial backoff delay in seconds (default 0.5).
        max_delay_s: Maximum delay ceiling in seconds (default 15.0).
        retry_exceptions: Tuple of exception types to retry on.
        is_retryable: Optional custom filter predicate returning bool for an exception.
        sleep_fn: Optional async sleep function (default asyncio.sleep).
        **kwargs: Keyword arguments for coro_fn.

    Returns:
        The return value of coro_fn.
    """
    backoff = FullJitterBackoff(
        max_retries=max_retries,
        base_delay_s=base_delay_s,
        max_delay_s=max_delay_s,
        retry_exceptions=retry_exceptions,
        is_retryable=is_retryable,
        sleep_fn=sleep_fn,
    )
    return await backoff.execute(coro_fn, *args, **kwargs)
