from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services import circuit_breaker as cb


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value


def _breaker(clock, *, threshold=2, recovery=10.0, probes=2):
    config = cb.CircuitBreakerConfig(
        provider="ollama",
        failure_threshold=threshold,
        recovery_timeout=recovery,
        half_open_max_calls=probes,
    )
    breaker = cb.DefaultCircuitBreaker(config)
    return breaker


def test_recovery_uses_monotonic_clock_and_closes_after_probe_success(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cb.time, "monotonic", clock.monotonic)
    breaker = _breaker(clock, probes=2)

    breaker.record_failure(RuntimeError("one"))
    breaker.record_failure(RuntimeError("two"))
    assert breaker.get_state() is cb.CircuitState.OPEN
    assert breaker.can_execute() is False

    clock.value += 10.0
    assert breaker.can_execute() is True
    assert breaker.can_execute() is True
    assert breaker.can_execute() is False

    breaker.record_success()
    breaker.record_success()
    assert breaker.get_state() is cb.CircuitState.CLOSED
    assert breaker.get_stats()["failures"] == 0


def test_half_open_admission_is_atomic_under_concurrency(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cb.time, "monotonic", clock.monotonic)
    breaker = _breaker(clock, probes=3)
    breaker.record_failure(RuntimeError("one"))
    breaker.record_failure(RuntimeError("two"))
    clock.value += 10.0

    with ThreadPoolExecutor(max_workers=20) as pool:
        decisions = list(pool.map(lambda _: breaker.can_execute(), range(20)))

    assert sum(decisions) == 3
    assert breaker.get_stats()["half_open_in_flight"] == 3


def test_failed_half_open_probe_reopens_and_reset_clears_state(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cb.time, "monotonic", clock.monotonic)
    breaker = _breaker(clock, probes=1)
    breaker.record_failure(RuntimeError("one"))
    breaker.record_failure(RuntimeError("two"))
    clock.value += 10.0
    assert breaker.can_execute() is True
    breaker.record_failure(RuntimeError("still down"))
    assert breaker.get_state() is cb.CircuitState.OPEN

    breaker.reset()
    assert breaker.get_state() is cb.CircuitState.CLOSED
    stats = breaker.get_stats()
    assert stats["failures"] == 0
    assert stats["last_failure_time"] is None
    assert stats["half_open_in_flight"] == 0


@pytest.mark.asyncio
async def test_operator_reset_is_post_only_admin_and_rate_limited(monkeypatch):
    from app.api import health

    registry = cb.CircuitBreakerRegistry()
    breaker = _breaker(FakeClock(), threshold=1)
    registry.register("ollama", breaker)
    registry.set_active("ollama")
    breaker.record_failure(RuntimeError("down"))
    monkeypatch.setattr(
        health,
        "get_container",
        lambda: SimpleNamespace(circuit_breaker_registry=registry),
    )
    health._manual_reset_last.clear()
    monkeypatch.setattr(health.settings, "is_production", False)
    user = {"id": "task-75-operator", "is_superuser": True}

    result = await health.circuit_breaker_reset_endpoint(user)
    assert result["status"] == "ok"
    assert breaker.get_state() is cb.CircuitState.CLOSED

    with pytest.raises(HTTPException) as exc_info:
        await health.circuit_breaker_reset_endpoint(user)
    assert exc_info.value.status_code == 429

    with pytest.raises(HTTPException) as exc_info:
        await health.circuit_breaker_reset_endpoint({"id": "ordinary-user"})
    assert exc_info.value.status_code == 403
