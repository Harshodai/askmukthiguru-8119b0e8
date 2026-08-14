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
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from services.health_monitor import HealthMonitor

from app.config import settings
from app.constants import CIRCUIT_BREAKER_CONFIGS, CircuitBreakerProvider

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
    failure_exceptions: tuple = (Exception,)

    @classmethod
    def from_provider(cls, provider: str) -> CircuitBreakerConfig:
        """Create config from provider name using centralized constants."""
        config = CIRCUIT_BREAKER_CONFIGS.get(provider)
        if config:
            return cls(provider=provider, **config)
        # Fallback defaults
        return cls(provider=provider)


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
    _half_open_in_flight: int = field(default=0, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

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
        """Get current circuit state atomically."""
        with self._lock:
            return self._state

    def get_stats(self) -> dict:
        """Get circuit breaker statistics atomically."""
        with self._lock:
            return {
                "provider": self.config.provider,
                "state": self._state.value,
                "failures": self._failures,
                "last_failure_time": self._last_failure_time,
                "half_open_calls": self._half_open_calls,
                "half_open_in_flight": self._half_open_in_flight,
                "config": {
                    "failure_threshold": self.config.failure_threshold,
                    "recovery_timeout": self.config.recovery_timeout,
                    "half_open_max_calls": self.config.half_open_max_calls,
                }
            }

    def _transition_to_open(self, reason: str = "") -> None:
        """Transition circuit to OPEN state."""
        previous_state = self._state.value
        self._previous_state = previous_state
        self._state = CircuitState.OPEN
        logger.warning(
            "Circuit breaker state change",
            extra={
                "provider": self.config.provider,
                "previous_state": previous_state,
                "new_state": "open",
                "reason": reason,
                "failures": self._failures,
                "threshold": self.config.failure_threshold,
            },
        )
        self._notify_state_change("open", reason)
        self._update_gauges()

    def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state."""
        previous_state = self._state.value
        self._previous_state = previous_state
        self._state = CircuitState.HALF_OPEN
        self._half_open_calls = 0
        self._half_open_in_flight = 0
        logger.warning(
            "Circuit breaker state change",
            extra={
                "provider": self.config.provider,
                "previous_state": previous_state,
                "new_state": "half_open",
                "reason": "recovery_timeout_elapsed",
                "half_open_max_calls": self.config.half_open_max_calls,
            },
        )
        self._notify_state_change("half_open", "recovery_timeout_elapsed")
        self._update_gauges()

    def _transition_to_closed(self) -> None:
        """Transition circuit to CLOSED state."""
        previous_state = self._state.value
        self._previous_state = previous_state
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._half_open_calls = 0
        self._half_open_in_flight = 0
        logger.info(
            "Circuit breaker state change",
            extra={
                "provider": self.config.provider,
                "previous_state": previous_state,
                "new_state": "closed",
                "reason": "recovery_successful",
            },
        )
        self._notify_state_change("closed", "recovery_successful")
        self._update_gauges()

    def _notify_state_change(self, new_state: str, reason: str) -> None:
        """Hook for external alerting - can be overridden or extended."""
        # Emit metric for monitoring
        try:
            from app.metrics import CIRCUIT_BREAKER_STATE_CHANGES
            CIRCUIT_BREAKER_STATE_CHANGES.labels(
                provider=self.config.provider,
                from_state=self._state.value if hasattr(self, '_previous_state') else 'unknown',
                to_state=new_state,
                reason=reason,
            ).inc()
        except Exception:
            pass  # Metrics optional

    def _update_gauges(self) -> None:
        """Update Prometheus gauge metrics for current state."""
        try:
            from app.metrics import CIRCUIT_BREAKER_FAILURES, CIRCUIT_BREAKER_STATE
            state_map = {"closed": 0, "half_open": 1, "open": 2}
            CIRCUIT_BREAKER_STATE.labels(provider=self.config.provider).set(state_map.get(self._state.value, 0))
            CIRCUIT_BREAKER_FAILURES.labels(provider=self.config.provider).set(self._failures)
        except Exception:
            pass  # Metrics optional


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

    _phi_monitor: Optional[HealthMonitor] = field(default=None, repr=False)

    def can_execute(self) -> bool:
        """Atomically decide and reserve a request slot."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                if settings.phi_accrual_enabled:
                    try:
                        from services.health_monitor import HealthMonitor as _HM
                        monitor = _HM()
                        phi = monitor.get_phi(self.config.provider)
                        is_healthy = monitor.is_healthy(self.config.provider)
                        if not is_healthy:
                            self._transition_to_open(f"phi={phi:.2f} > threshold")
                            return False
                    except Exception as _e:
                        logger.debug("[circuit breaker] suppressed non-critical error: %s", _e)
                return True

            if self._state == CircuitState.OPEN:
                if (
                    self._last_failure_time is not None
                    and (time.monotonic() - self._last_failure_time) >= self.config.recovery_timeout
                ):
                    self._transition_to_half_open()
                else:
                    return False

            # HALF_OPEN: reserve admission atomically so concurrent callers
            # cannot exceed the probe budget.
            if self._half_open_calls + self._half_open_in_flight >= self.config.half_open_max_calls:
                return False
            self._half_open_in_flight += 1
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight > 0:
                    self._half_open_in_flight -= 1
                self._half_open_calls += 1
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self._transition_to_closed()
            elif self._state == CircuitState.CLOSED:
                self._failures = max(0, self._failures - 1)
            self._update_gauges()

    def record_failure(self, error: Exception = None) -> None:
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.monotonic()

            if settings.phi_accrual_enabled:
                try:
                    from services.health_monitor import HealthMonitor as _HM
                    monitor = _HM()
                    monitor.record_heartbeat(self.config.provider, success=False)
                except Exception as _e:
                    logger.debug("[circuit breaker] suppressed non-critical error: %s", _e)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight > 0:
                    self._half_open_in_flight -= 1
                self._transition_to_open("(failed during half-open test)")
            elif self._state == CircuitState.CLOSED:
                if self._failures >= self.config.failure_threshold:
                    self._transition_to_open(f"(threshold={self.config.failure_threshold} reached)")
            self._update_gauges()

    def reset(self, reason: str = "manual_reset") -> None:
        """Reset the breaker through one audited, metric-aware transition."""
        with self._lock:
            previous_state = self._state.value
            self._previous_state = previous_state
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._last_failure_time = None
            self._half_open_calls = 0
            self._half_open_in_flight = 0
            self._notify_state_change("closed", reason)
            self._update_gauges()


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
    Uses centralized constants for provider names and configs.
    """

    breakers = {}

    for provider in CircuitBreakerProvider:
        config = CircuitBreakerConfig.from_provider(provider.value)
        breakers[provider.value] = DefaultCircuitBreaker(config)

    return breakers


def initialize_circuit_breakers(registry: CircuitBreakerRegistry = None) -> CircuitBreakerRegistry:
    """
    Initialize all circuit breakers and register them.

    Called during application startup from ServiceContainer.
    """
    if registry is None:
        registry = get_circuit_breaker_registry()

    # Services (qdrant/embedding/web_search/sarvam/openrouter) self-register their
    # REAL breaker via get_circuit_breaker_registry().register(...) in their own
    # __init__, which runs before this function in ServiceContainer's build order.
    # Only fill a default for a provider with no real breaker registered yet --
    # overwriting one here would silently replace the object every service actually
    # calls can_execute()/record_success() on with a phantom that never sees traffic.
    breakers = create_default_breakers()
    for provider, breaker in breakers.items():
        if registry.get(provider) is None:
            registry.register(provider, breaker)

    # Set active provider based on config
    from app.config import settings
    active_provider = settings.llm_provider
    registry.set_active(active_provider)

    logger.info(f"Circuit breakers initialized. Active provider: {active_provider}")
    return registry
