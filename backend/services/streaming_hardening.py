"""
Unit 18 — Streaming Response Hardening

Provides a guarded async generator wrapper that catches mid-stream errors
from LLM providers (Ollama, Krutrim, etc.) and yields a graceful sentinel
instead of silently dropping the connection.

Design:
  - StreamInterruptedError: typed exception carrying the partial text and reason
  - guarded_stream(): wraps any AsyncIterator[str]; on error yields sentinel + raises
  - stream_with_recovery(): attempts retry up to max_retries times before fallback
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable
from typing import Callable

logger = logging.getLogger(__name__)

STREAM_ERROR_SENTINEL = "\n\n[Response was interrupted. Please try again.]"


class StreamInterruptedError(Exception):
    """Raised when an LLM stream is cut mid-response.

    Carries the partial text generated before the interruption so callers
    can inspect how much content was delivered before the failure.
    """

    def __init__(self, partial_text: str, reason: str) -> None:
        self.partial_text = partial_text
        self.reason = reason
        super().__init__(f"Stream interrupted after {len(partial_text)} chars: {reason}")


async def guarded_stream(
    generator: AsyncIterator[str],
    on_error_sentinel: str = STREAM_ERROR_SENTINEL,
) -> AsyncIterator[str]:
    """Wrap an async token generator; catch errors and yield a sentinel.

    Usage::

        async for token in guarded_stream(ollama_service.generate_stream(...)):
            yield token

    On any exception mid-stream:
      1. The sentinel string is yielded so the client sees a graceful message.
      2. ``StreamInterruptedError`` is raised with ``partial_text`` attached.

    Args:
        generator: The upstream async generator yielding string tokens.
        on_error_sentinel: The string to yield when an error is detected.
            Defaults to ``STREAM_ERROR_SENTINEL``.
    """
    partial: list[str] = []
    try:
        async for chunk in generator:
            partial.append(chunk)
            yield chunk
    except Exception as exc:
        logger.warning(
            f"guarded_stream caught mid-stream error after {len(partial)} chunks: "
            f"{type(exc).__name__}: {exc}"
        )
        yield on_error_sentinel
        raise StreamInterruptedError("".join(partial), str(exc)) from exc


async def stream_with_recovery(
    generator_factory: Callable[[], Awaitable[AsyncIterator[str]]],
    max_retries: int = 1,
    on_error_sentinel: str = STREAM_ERROR_SENTINEL,
) -> AsyncIterator[str]:
    """Attempt the stream, retrying up to max_retries times on interruption.

    On the final attempt, falls back to guarded_stream which yields the
    sentinel and raises StreamInterruptedError.

    Args:
        generator_factory: Async callable that returns a fresh generator each call.
        max_retries: Number of additional attempts after the first failure.
        on_error_sentinel: Sentinel yielded on unrecoverable failure.

    Example::

        async for token in stream_with_recovery(
            lambda: ollama_service.generate_stream(system, user),
            max_retries=1,
        ):
            yield token
    """
    for attempt in range(max_retries + 1):
        is_last = attempt == max_retries
        partial: list[str] = []
        try:
            gen = await generator_factory()
            async for chunk in gen:
                partial.append(chunk)
                yield chunk
            return  # Stream completed successfully
        except StreamInterruptedError:
            raise  # Already handled by guarded_stream on last attempt
        except Exception as exc:
            logger.warning(
                f"stream_with_recovery: attempt {attempt + 1}/{max_retries + 1} failed "
                f"after {len(partial)} chunks: {type(exc).__name__}: {exc}"
            )
            if is_last:
                yield on_error_sentinel
                raise StreamInterruptedError("".join(partial), str(exc)) from exc
            # else: retry — don't yield anything, start fresh
            logger.info(f"stream_with_recovery: retrying (attempt {attempt + 2})...")
