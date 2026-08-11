"""Unit tests for AdaptiveConcurrencyThrottle — no network, no YouTube calls."""

import asyncio

import pytest

from ingest.youtube_loader import AdaptiveConcurrencyThrottle


@pytest.mark.asyncio
async def test_throttle_stays_at_max_permits_on_all_success():
    throttle = AdaptiveConcurrencyThrottle(max_permits=5, window_size=10, failure_threshold=0.4)
    for _ in range(20):
        await throttle.record_outcome(True)
    assert throttle._current_permits == 5


@pytest.mark.asyncio
async def test_throttle_shrinks_on_sustained_failures():
    throttle = AdaptiveConcurrencyThrottle(max_permits=5, window_size=10, failure_threshold=0.4)
    # 5/10 failures = 50% failure rate, exceeds 40% threshold
    for _ in range(5):
        await throttle.record_outcome(False)
    for _ in range(5):
        await throttle.record_outcome(True)
    assert throttle._current_permits < 5


@pytest.mark.asyncio
async def test_throttle_never_drops_below_one():
    throttle = AdaptiveConcurrencyThrottle(max_permits=2, window_size=5, failure_threshold=0.4)
    # Sustained 100% failure across many windows
    for _ in range(50):
        await throttle.record_outcome(False)
    assert throttle._current_permits >= 1


@pytest.mark.asyncio
async def test_throttle_waits_for_full_window_before_acting():
    throttle = AdaptiveConcurrencyThrottle(max_permits=5, window_size=10, failure_threshold=0.4)
    # Only 3 outcomes recorded — below window_size, must not shrink yet
    for _ in range(3):
        await throttle.record_outcome(False)
    assert throttle._current_permits == 5


@pytest.mark.asyncio
async def test_throttle_shrinks_once_per_failure_episode():
    """Hysteresis: one permit per hot episode; reset only when the rate cools below threshold."""
    throttle = AdaptiveConcurrencyThrottle(max_permits=5, window_size=10, failure_threshold=0.4)

    # Non-full window never shrinks
    for _ in range(3):
        await throttle.record_outcome(False)
    assert throttle._current_permits == 5

    # 10 failures fill the window at 100% failure -> exactly one shrink (5 -> 4)
    for _ in range(10):
        await throttle.record_outcome(False)
    assert throttle._current_permits == 4

    # Window still hot (100% failure) -> no further shrinking within this episode
    for _ in range(5):
        await throttle.record_outcome(False)
    assert throttle._current_permits == 4

    # 10 successes cool the window below the threshold -> episode resets
    for _ in range(10):
        await throttle.record_outcome(True)
    assert throttle._current_permits == 4

    # A new hot episode may shrink once more (4 -> 3)
    for _ in range(10):
        await throttle.record_outcome(False)
    assert throttle._current_permits == 3


@pytest.mark.asyncio
async def test_throttle_acquire_release_bounds_concurrency():
    throttle = AdaptiveConcurrencyThrottle(max_permits=2, window_size=100, failure_threshold=0.4)
    concurrent_count = 0
    max_concurrent_seen = 0
    lock = asyncio.Lock()

    async def worker():
        nonlocal concurrent_count, max_concurrent_seen
        await throttle.acquire()
        try:
            async with lock:
                concurrent_count += 1
                max_concurrent_seen = max(max_concurrent_seen, concurrent_count)
            await asyncio.sleep(0.01)
        finally:
            async with lock:
                concurrent_count -= 1
            throttle.release()

    await asyncio.gather(*[worker() for _ in range(10)])
    assert max_concurrent_seen <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
