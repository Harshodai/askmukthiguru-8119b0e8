"""Shared exceptions for Sarvam Cloud service.

Breaks circular imports between sarvam_service.py and the HTTP gateway.
"""

# Re-export the canonical CircuitOpenException from the circuit-breaker module
# so that the gateway and the service agree on the same class.
from services.circuit_breaker import CircuitOpenException


class QuotaExceededError(Exception):
    """Raised when the Sarvam Cloud API has exceeded its quota/credits."""

    pass


class NonRetryableError(Exception):
    """Raised when an error occurs that should not be retried (e.g. client errors 4xx)."""

    pass
