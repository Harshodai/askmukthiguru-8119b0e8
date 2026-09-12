"""Tests for canonical memory resilience and chaos testing — Phase 20."""
import time

import pytest

from services.canonical_memory.resilience import (
    CircuitBreaker,
    CircuitState,
    ChaosScenario,
    ChaosTestRunner,
    FailureMode,
    GracefulDegradation,
    get_circuit_breaker,
    get_graceful_degradation,
)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class TestCircuitBreakerClosedOnSuccess:
    def test_starts_closed(self):
        cb = get_circuit_breaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_success_stays_closed(self):
        cb = get_circuit_breaker()
        cb.call(lambda: "ok")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_success_resets_failures(self):
        cb = get_circuit_breaker()
        cb._on_failure()
        cb._on_failure()
        assert cb.failure_count == 2
        cb.call(lambda: "ok")
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerOpensAfterFailures:
    def test_opens_at_threshold(self):
        cb = get_circuit_breaker(failure_threshold=3)
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("timeout")))
            except ConnectionError:
                pass
        assert cb.state == CircuitState.OPEN

    def test_open_circuit_rejects_calls(self):
        cb = get_circuit_breaker(failure_threshold=2)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("down")))
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN
        with pytest.raises(RuntimeError, match="Circuit breaker OPEN"):
            cb.call(lambda: "should not run")

    def test_custom_threshold(self):
        cb = get_circuit_breaker(failure_threshold=1)
        try:
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerHalfOpenRecovery:
    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("down")))
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        # Next call attempt transitions to HALF_OPEN
        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("down")))
            except RuntimeError:
                pass
        time.sleep(0.02)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("still down")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerReset:
    def test_reset_from_open(self):
        cb = get_circuit_breaker(failure_threshold=1)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_reset_from_closed(self):
        cb = get_circuit_breaker()
        cb._on_failure()
        cb._on_failure()
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_callable_after_reset(self):
        cb = get_circuit_breaker(failure_threshold=1)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        except RuntimeError:
            pass
        cb.reset()
        result = cb.call(lambda: "working")
        assert result == "working"


# ---------------------------------------------------------------------------
# Graceful Degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradationFallback:
    def test_primary_succeeds(self):
        gd = get_graceful_degradation()
        result = gd.with_fallback(lambda: "primary", lambda: "fallback")
        assert result == "primary"
        assert not gd.is_degraded()

    def test_fallback_on_primary_failure(self):
        gd = get_graceful_degradation()

        def primary():
            raise RuntimeError("primary down")

        result = gd.with_fallback(primary, lambda: "fallback_result")
        assert result == "fallback_result"
        assert gd.is_degraded()

    def test_fallback_count_increments(self):
        gd = get_graceful_degradation()

        def primary():
            raise RuntimeError("fail")

        gd.with_fallback(primary, lambda: "fb1")
        gd.with_fallback(primary, lambda: "fb2")
        assert gd.fallback_count() == 2

    def test_primary_args_forwarded(self):
        gd = get_graceful_degradation()
        result = gd.with_fallback(lambda x, y: x + y, lambda: "fallback", 3, 4)
        assert result == 7

    def test_fallback_args_forwarded(self):
        gd = get_graceful_degradation()

        def primary():
            raise RuntimeError("fail")

        result = gd.with_fallback(primary, lambda x: f"fb_{x}", "hello")
        assert result == "fb_hello"


class TestGracefulDegradationRecovery:
    def test_recover_resets_state(self):
        gd = get_graceful_degradation()

        def primary():
            raise RuntimeError("fail")

        gd.with_fallback(primary, lambda: "fb")
        assert gd.is_degraded()
        gd.recover()
        assert not gd.is_degraded()
        assert gd.fallback_count() == 0

    def test_recover_then_primary_works(self):
        gd = get_graceful_degradation()
        call_count = 0

        def sometimes_failing():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first call fails")
            return "recovered"

        result = gd.with_fallback(sometimes_failing, lambda: "fb")
        assert result == "fb"
        gd.recover()
        result = gd.with_fallback(sometimes_failing, lambda: "fb")
        assert result == "recovered"
        assert not gd.is_degraded()


# ---------------------------------------------------------------------------
# Chaos Test Runner
# ---------------------------------------------------------------------------


class TestChaosWriteResilience:
    def test_write_under_normal(self):
        runner = ChaosTestRunner()
        result = runner.test_memory_write_resilience("test_user")
        assert result["passed"] is True
        assert result["degraded"] is False
        assert result["candidate_valid"] is True


class TestChaosRetrievalFallback:
    def test_retrieval_degrades_gracefully(self):
        runner = ChaosTestRunner()
        result = runner.test_retrieval_resilience("test_user", "hello")
        assert result["passed"] is True
        assert result["degraded"] is True
        assert result["results"] == []


class TestChaosPartialWrite:
    def test_partial_write_detected(self):
        runner = ChaosTestRunner()
        result = runner.test_partial_write_recovery("test_user")
        assert result["passed"] is True
        assert result["partial_data"] is False


class TestChaosAllScenarios:
    def test_all_scenarios_pass(self):
        runner = ChaosTestRunner()
        report = runner.run_all_scenarios("chaos_user")
        assert report["all_passed"] is True
        assert report["failed"] == 0
        assert report["passed"] == report["total_scenarios"]
        assert len(report["scenarios"]) == report["total_scenarios"]

    def test_circuit_breaker_scenario(self):
        runner = ChaosTestRunner()
        result = runner.test_circuit_breaker_integration("test_user")
        assert result["passed"] is True
        assert result["circuit_state"] == "open"
        assert result["failures_injected"] >= 3

    def test_degradation_scenario(self):
        runner = ChaosTestRunner()
        result = runner.test_graceful_degradation_integration("test_user")
        assert result["passed"] is True
        assert result["degraded"] is True
        assert result["result"] == "degraded_response"


class TestFailureModeEnum:
    def test_all_modes_defined(self):
        modes = list(FailureMode)
        assert len(modes) == 7
        assert FailureMode.DB_TIMEOUT.value == "db_timeout"
        assert FailureMode.DB_UNAVAILABLE.value == "db_unavailable"
        assert FailureMode.VECTOR_UNAVAILABLE.value == "vector_unavailable"
        assert FailureMode.LLM_UNAVAILABLE.value == "llm_unavailable"
        assert FailureMode.PARTIAL_FAILURE.value == "partial_failure"
        assert FailureMode.SLOW_RESPONSE.value == "slow_response"
        assert FailureMode.MEMORY_EXHAUSTION.value == "memory_exhaustion"

    def test_modes_are_strings(self):
        for mode in FailureMode:
            assert isinstance(mode.value, str)

    def test_circuit_state_values(self):
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestChaosScenarioDataclass:
    def test_scenario_creation(self):
        s = ChaosScenario(
            name="test",
            description="desc",
            failure_mode=FailureMode.DB_TIMEOUT,
        )
        assert s.name == "test"
        assert s.duration_seconds == 0.1
        assert s.expect_degraded is True

    def test_runner_has_scenarios(self):
        assert len(ChaosTestRunner.SCENARIOS) == 5
        names = {s.name for s in ChaosTestRunner.SCENARIOS}
        assert "db_timeout" in names
        assert "vector_unavailable" in names
        assert "partial_failure" in names
        assert "slow_response" in names
        assert "llm_unavailable" in names


class TestInjectFailure:
    def test_inject_returns_completed(self):
        runner = ChaosTestRunner()
        result = runner.inject_failure(FailureMode.DB_TIMEOUT, duration_seconds=0.01)
        assert result["completed"] is True
        assert result["failure_mode"] == "db_timeout"
        assert result["duration"] >= 0.0
