"""
Mukthi Guru — Standardized API Error Contracts

Provides a consistent ErrorResponse schema (API design principles: Pattern 1).
All route handlers and exception handlers should use these instead of raw
HTTPException string ``detail`` fields.

Machine-readable error codes allow frontend to i18n errors without string matching.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardized error envelope for all API error responses.

    Example JSON (timestamp is Python's datetime.now(UTC).isoformat() format):
        {
          "error": "RetrievalTimeout",
          "message": "Vector retrieval exceeded 30s timeout",
          "details": {"provider": "qdrant", "timeout_ms": 30000},
          "request_id": "req-abc123",
          "timestamp": "2026-07-08T06:00:00.123456+00:00"
        }
    Note: timestamp uses Python's isoformat() which emits '+00:00' (not 'Z').
    """

    error: str = Field(description="Machine-readable PascalCase error code")
    message: str = Field(description="Human-readable description for display")
    details: Optional[dict] = Field(default=None, description="Structured context about the error")
    request_id: Optional[str] = Field(default=None, description="Correlation ID from X-Request-ID header")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 UTC timestamp of when the error occurred",
    )


# ---- Standard error factories -----------------------------------------------

def not_found(resource: str, identifier: str) -> ErrorResponse:
    """404 — resource could not be located."""
    return ErrorResponse(
        error="NotFound",
        message=f"{resource} '{identifier}' not found",
        details={"resource": resource, "identifier": identifier},
    )


def provider_unavailable(provider: str, reason: str = "") -> ErrorResponse:
    """503 — LLM or vector store provider is down / circuit open."""
    return ErrorResponse(
        error="ProviderUnavailable",
        message=f"LLM provider '{provider}' is unavailable. Try again shortly.",
        details={"provider": provider, "reason": reason} if reason else {"provider": provider},
    )


def validation_failed(field: str, reason: str) -> ErrorResponse:
    """422 — business-level validation failure (beyond Pydantic schema)."""
    return ErrorResponse(
        error="ValidationFailed",
        message=f"Field '{field}' is invalid: {reason}",
        details={"field": field, "reason": reason},
    )


def retrieval_timeout(timeout_ms: int, query_preview: str = "") -> ErrorResponse:
    """504 — embedding / vector retrieval exceeded timeout."""
    return ErrorResponse(
        error="RetrievalTimeout",
        message=f"Retrieval exceeded {timeout_ms}ms timeout. Please retry.",
        details={"timeout_ms": timeout_ms, "query_preview": query_preview[:80]},
    )


def rate_limited(retry_after_seconds: int = 60) -> ErrorResponse:
    """429 — client hit rate limit."""
    return ErrorResponse(
        error="RateLimited",
        message=f"Too many requests. Please wait {retry_after_seconds}s before retrying.",
        details={"retry_after_seconds": retry_after_seconds},
    )


def internal_error(error_type: str = "InternalError", context: str = "") -> ErrorResponse:
    """500 — unhandled internal error (safe, no stack traces)."""
    return ErrorResponse(
        error=error_type,
        message="An internal error occurred. Our team has been notified.",
        details={"context": context} if context else None,
    )
