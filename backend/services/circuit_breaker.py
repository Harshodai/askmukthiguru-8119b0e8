"""
Mukthi Guru — Provider-Agnostic Circuit Breaker Framework

Design Patterns:
  - Abstract Base Class: Defines common circuit breaker interface
  - Registry Pattern: Central registry for provider-specific breakers
  - Factory Pattern: Creates appropriate breaker based on LLM provider config
  - Strategy Pattern: Different breaker configurations per provider

All LLM providers (Sarvam, Ollama, OpenRouter, etc.) register their circuit breakers
with the registry. The active breaker is determined by LLM_PROVIDER config.
"""

from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Type

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation - requests pass through
    OPEN = "open"          # Failing - requests rejected immediately
    HALF_OPEN = "half_open"  # Testing recovery - limited requests allowed


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker errors."""
    pass


class CircuitOpenException(CircuitBreakerError):
    """Raised when circuit breaker is OPEN and request is rejected."""

    def __init__(self, provider: str, message: str = None):
        self.provider = provider
        super().__init__(message or f"Circuit breaker OPEN for {provider} - requests rejected")


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker instance."""
    provider: str
    failure_threshold: int = 5
    recovery_timeout: float = 90.0
    half_open_max_calls: int = 3
    # Optional: custom exception types that count as failures
    failure_exceptions: tuple = (Exception,)


@dataclass
class BaseCircuitBreaker(abc.ABC):
    """
    Abstract base class for provider-specific circuit breakers.

    All implementations must provide:
    - can_execute(): Check if request should be allowed
    - record_success(): Called on successful request
    - record_failure(): Called on failed request
    - get_state(): Current circuit state
    """

    config: CircuitBreakerConfig
    _failures: int = field(default=0, repr=False)
    _last_failure_time: Optional[float] = field(default=None, repr=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _half_open_calls: int = field(default=0, repr=False)

    @abc.abstractmethod
    def can_execute(self) -> bool:
        """Check if a request can be executed (circuit allows it)."""
        pass

    @abc.abstractmethod
    def record_success(self) -> None:
        """Record a successful request."""
        pass

    @abc.abstractmethod
    def record_failure(self, error: Exception = None) -> None:
        """Record a failed request."""
        pass

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "provider": self.config.provider,
            "state": self._state.value,
            "failures": self._failures,
            "last_failure_time": self._last_failure_time,
            "half_open_calls": self._half_open_calls,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "half_open_max_calls": self.config.half_open_max_calls,
            }
        }

    def _transition_to_open(self, reason: str = "") -> None:
        """Transition circuit to OPEN state."""
        self._state = CircuitState.OPEN
        logger.warning(f"Circuit breaker [{self.config.provider}] → OPEN {reason}")

    def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state."""
        self._state = CircuitState.HALF_OPEN
        self._half_open_calls = 0
        logger.info(f"Circuit breaker [{self.config.provider}] → HALF_OPEN (testing recovery)")

    def _transition_to_closed(self) -> None:
        """Transition circuit to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._half_open_calls = 0
        logger.info(f"Circuit breaker [{self.config.provider}] → CLOSED (recovered)")


class DefaultCircuitBreaker(BaseCircuitBreaker):
    """
    Default circuit breaker implementation with standard behavior.

    Behavior:
    - CLOSED: Normal operation, failures counted
    - After failure_threshold failures → OPEN
    - OPEN: Requests rejected immediately for recovery_timeout seconds
    - After timeout → HALF_OPEN (allows half_open_max_calls test requests)
    - HALF_OPEN: If all test calls succeed → CLOSED, if any fails → OPEN
    """

    def can_execute(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self._last_failure_time and (time.time() - self._last_failure_time) > self.config.recovery_timeout:
                self._transition_to_half_open()
                return True
            return False

        # HALF_OPEN: Allow limited test calls
        return self._half_open_calls < self.config.half_open_max_calls

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.config.half_open_max_calls:
                self._transition_to_closed()
        elif self._state == CircuitState.CLOSED:
            # Decay failure count on success
            self._failures = max(0, self._failures - 1)

    def record_failure(self, error: Exception = None) -> None:
        self._failures += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._transition_to_open("(failed during half-open test)")
        elif self._state == CircuitState.CLOSED:
            if self._failures >= self.config.failure_threshold:
                self._transition_to_open(f"(threshold={self.config.failure_threshold} reached)")


class CircuitBreakerRegistry:
    """
    Registry for circuit breakers - manages provider-specific breakers.

    Usage:
        registry = CircuitBreakerRegistry()
        registry.register("sarvam", DefaultCircuitBreaker(config))
        registry.register("ollama", DefaultCircuitBreaker(config))

        active_breaker = registry.get_active()  # Based on LLM_PROVIDER config
        if active_breaker.can_execute():
            # proceed with request
    """

    def __init__(self):
        self._breakers: Dict[str, BaseCircuitBreaker] = {}
        self._active_provider: Optional[str] = None

    def register(self, provider: str, breaker: BaseCircuitBreaker) -> None:
        """Register a circuit breaker for a provider."""
        self._breakers[provider.lower()] = breaker
        logger.info(f"Registered circuit breaker for provider: {provider}")

    def unregister(self, provider: str) -> None:
        """Unregister a circuit breaker."""
        provider_key = provider.lower()
        if provider_key in self._breakers:
            del self._breakers[provider_key]
            logger.info(f"Unregistered circuit breaker for provider: {provider}")

    def get(self, provider: str) -> Optional[BaseCircuitBreaker]:
        """Get a specific provider's circuit breaker."""
        return self._breakers.get(provider.lower())

    def set_active(self, provider: str) -> None:
        """Set the active provider (based on LLM_PROVIDER config)."""
        provider_key = provider.lower()
        if provider_key not in self._breakers:
            logger.warning(f"No circuit breaker registered for provider: {provider}")
        self._active_provider = provider_key
        logger.info(f"Active circuit breaker provider set to: {provider}")

    def get_active(self) -> Optional[BaseCircuitBreaker]:
        """Get the currently active circuit breaker."""
        if self._active_provider:
            return self._breakers.get(self._active_provider)
        return None

    def get_active_provider(self) -> Optional[str]:
        """Get the active provider name."""
        return self._active_provider

    def get_all_stats(self) -> dict:
        """Get stats for all registered breakers."""
        return {
            provider: breaker.get_stats()
            for provider, breaker in self._breakers.items()
        }


# Global registry instance
_circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get or create the global circuit breaker registry."""
    global _circuit_breaker_registry
    if _circuit_breaker_registry is None:
        _circuit_breaker_registry = CircuitBreakerRegistry()
    return _circuit_breaker_registry


def create_default_breakers() -> Dict[str, DefaultCircuitBreaker]:
    """
    Create default circuit breakers for all known providers.

    Returns dict of provider -> breaker for registration.
    """
    from app.config import settings

    breakers = {}

    # Sarvam Cloud breaker
    sarvam_config = CircuitBreakerConfig(
        provider="sarvam",
        failure_threshold=5,
        recovery_timeout=90.0,  # Longer timeout for cloud API
        half_open_max_calls=3,
    )
    breakers["sarvam"] = DefaultCircuitBreaker(sarvam_config)

    # Ollama breaker
    ollama_config = CircuitBreakerConfig(
        provider="ollama",
        failure_threshold=3,
        recovery_timeout=60.0,  # Shorter timeout for local
        half_open_max_calls=1,
    )
    breakers["ollama"] = DefaultCircuitBreaker(ollama_config)

    # OpenRouter breaker (future)
    openrouter_config = CircuitBreakerConfig(
        provider="openrouter",
        failure_threshold=5,
        recovery_timeout=60.0,
        half_open_max_calls=3,
    )
    breakers["openrouter"] = DefaultCircuitBreaker(openrouter_config)

    return breakers


def initialize_circuit_breakers(registry: CircuitBreakerRegistry = None) -> CircuitBreakerRegistry:
    """
    Initialize all circuit breakers and register them.

    Called during application startup from ServiceContainer.
    """
    if registry is None:
        registry = get_circuit_breaker_registry()

    breakers = create_default_breakers()
    for provider, breaker in breakers.items():
        registry.register(provider, breaker)

    # Set active provider based on config
    from app.config import settings
    active_provider = settings.llm_provider
    registry.set_active(active_provider)

    logger.info(f"Circuit breakers initialized. Active provider: {active_provider}")
    return registry