"""L-CIRCUIT-IDLE-1: a long idle period must never mark a dependency unhealthy.

The reported symptom was the breaker opening on the first request after an idle
night. AccrualFailureDetector recomputes phi only when a heartbeat arrives, right
after stamping that arrival, so the "gap since last heartbeat" it measures is ~0
and idleness cannot inflate phi. These tests pin that with a controlled clock so
a future "check phi on a timer" change cannot silently reintroduce the trap.
"""

from unittest.mock import patch

import pytest

from services.health_monitor import AccrualFailureDetector

HOUR = 3600.0


def _warm(det: AccrualFailureDetector, clock: list[float], n: int = 10, every: float = 2.0) -> None:
    for _ in range(n):
        clock[0] += every
        det.record_heartbeat(clock[0], success=True)


@pytest.mark.unit
def test_first_success_after_idle_night_stays_healthy():
    clock = [1_000.0]
    with patch("services.health_monitor.time.time", side_effect=lambda: clock[0]):
        det = AccrualFailureDetector("openrouter")
        _warm(det, clock)

        clock[0] += 10 * HOUR  # overnight, zero traffic
        assert det.is_healthy  # nothing recomputes while idle

        det.record_heartbeat(clock[0], success=True)

    assert det.phi == 0.0
    assert det.is_healthy
    assert det.state == "CLOSED"


@pytest.mark.unit
def test_single_failure_after_idle_night_does_not_open():
    clock = [1_000.0]
    with patch("services.health_monitor.time.time", side_effect=lambda: clock[0]):
        det = AccrualFailureDetector("openrouter")
        _warm(det, clock)
        clock[0] += 10 * HOUR
        det.record_heartbeat(clock[0], success=False)

    assert det.is_healthy


@pytest.mark.unit
def test_three_consecutive_failures_still_open_and_one_success_heals():
    clock = [1_000.0]
    with patch("services.health_monitor.time.time", side_effect=lambda: clock[0]):
        det = AccrualFailureDetector("openrouter")
        _warm(det, clock)
        for _ in range(3):
            clock[0] += 1.0
            det.record_heartbeat(clock[0], success=False)
        assert not det.is_healthy

        clock[0] += 1.0
        det.record_heartbeat(clock[0], success=True)

    assert det.is_healthy


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
