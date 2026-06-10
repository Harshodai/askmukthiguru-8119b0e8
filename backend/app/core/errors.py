"""Domain-specific error types for the Mukthi Guru backend.

These exceptions carry structured context so callers can decide how to
recover or which telemetry sink to route to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorContext:
    """Immutable context attached to every domain error."""

    operation: str
    detail: str | None = None
    retryable: bool = True
    extra: dict[str, Any] | None = None

    def with_extra(self, **kwargs: Any) -> "ErrorContext":
        return ErrorContext(
            operation=self.operation,
            detail=self.detail,
            retryable=self.retryable,
            extra={**(self.extra or {}), **kwargs},
        )


class DomainError(Exception):
    """Base for all application-level errors."""

    def __init__(self, message: str, *, context: ErrorContext | None = None) -> None:
        super().__init__(message)
        self.context = context or ErrorContext(operation="unknown")


class ConfigurationError(DomainError):
    """Missing or invalid configuration. Never retry."""

    pass


class QuotaExceededError(DomainError):
    """External provider quota exhausted. Retry after backoff."""

    pass


class NonRetryableError(DomainError):
    """Client-side or validation error — do not retry."""

    pass


class CircuitOpenError(DomainError):
    """Circuit breaker is open — fail fast."""

    pass
