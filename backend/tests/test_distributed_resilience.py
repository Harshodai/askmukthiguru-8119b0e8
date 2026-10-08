"""
Mukthi Guru — Unit tests for Distributed Resilience & Full Jitter Backoff.

Validates:
1. Ceiling bounds: sleep delay in [0, min(max_delay_s, base_delay_s * 2^(attempt - 1))].
2. Statistical jitter properties across multiple attempts and samples.
3. Eventual success: transient errors retry and return the final successful result.
4. Immediate exit on non-retryable errors (ValueError, HTTP 401, 403, 404, 429).
5. Exception re-raise on exhaustion (attempts exhausted -> original exception propagated).
6. Retry on transient HTTP 5xx errors using OpenRouter and NIM error filters.
"""

from __future__ import annotations

import httpx
import pytest

from services.nim_service import _is_retryable_nim_error
from services.openrouter_service import _is_retryable_openrouter_error
from services.resilience import FullJitterBackoff, call_with_full_jitter


def _make_http_status_error(
    status_code: int, url: str = "https://api.example.com/test"
) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", url)
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code} Error",
        request=request,
        response=response,
    )


class MockSleepRecorder:
    """Records sleep invocations without delaying test execution."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)


# ==============================================================================
# 1. Ceiling Bounds & Jitter Calculations
# ==============================================================================


def test_full_jitter_ceiling_calculation():
    """Verify deterministic exponential backoff ceiling calculation."""
    backoff = FullJitterBackoff(max_retries=5, base_delay_s=0.5, max_delay_s=6.0)

    # attempt 1: 0.5 * 2^0 = 0.5
    assert backoff.compute_ceiling(1) == 0.5
    # attempt 2: 0.5 * 2^1 = 1.0
    assert backoff.compute_ceiling(2) == 1.0
    # attempt 3: 0.5 * 2^2 = 2.0
    assert backoff.compute_ceiling(3) == 2.0
    # attempt 4: 0.5 * 2^3 = 4.0
    assert backoff.compute_ceiling(4) == 4.0
    # attempt 5: 0.5 * 2^4 = 8.0 -> capped at max_delay_s (6.0)
    assert backoff.compute_ceiling(5) == 6.0
    # attempt 10: capped at max_delay_s (6.0)
    assert backoff.compute_ceiling(10) == 6.0


def test_full_jitter_delay_bounds_and_distribution():
    """Delays must be strictly bounded in [0, ceiling] with non-zero spread."""
    backoff = FullJitterBackoff(max_retries=4, base_delay_s=1.0, max_delay_s=10.0)

    for attempt in range(1, 5):
        ceiling = backoff.compute_ceiling(attempt)
        samples = [backoff.compute_delay(attempt) for _ in range(500)]

        # Bounds check
        assert all(0.0 <= s <= ceiling for s in samples)

        # Full jitter distribution check: min near 0, max near ceiling, mean near ceiling / 2
        min_val = min(samples)
        max_val = max(samples)
        mean_val = sum(samples) / len(samples)

        assert min_val < ceiling * 0.15
        assert max_val > ceiling * 0.85
        assert 0.35 * ceiling <= mean_val <= 0.65 * ceiling


def test_full_jitter_invalid_configuration():
    """Verify constructor parameter validations."""
    with pytest.raises(ValueError, match="max_retries must be >= 1"):
        FullJitterBackoff(max_retries=0)

    with pytest.raises(ValueError, match="base_delay_s must be > 0"):
        FullJitterBackoff(base_delay_s=0.0)

    with pytest.raises(ValueError, match="max_delay_s .* must be >= base_delay_s"):
        FullJitterBackoff(base_delay_s=5.0, max_delay_s=2.0)


# ==============================================================================
# 2. Eventual Success
# ==============================================================================


@pytest.mark.asyncio
async def test_call_with_full_jitter_eventual_success():
    """Function fails on attempts 1 and 2, then succeeds on attempt 3."""
    recorder = MockSleepRecorder()
    attempts = 0

    async def flaky_operation(arg1: str, kw: int = 10) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("Connection refused")
        return f"success:{arg1}:{kw}"

    result = await call_with_full_jitter(
        flaky_operation,
        "test_arg",
        kw=42,
        max_retries=4,
        base_delay_s=1.0,
        max_delay_s=8.0,
        sleep_fn=recorder.sleep,
    )

    assert result == "success:test_arg:42"
    assert attempts == 3
    assert len(recorder.sleeps) == 2

    # Verify sleep delays were bounded by attempt 1 and 2 ceilings
    assert 0.0 <= recorder.sleeps[0] <= 1.0  # attempt 1 ceiling: 1.0 * 2^0 = 1.0
    assert 0.0 <= recorder.sleeps[1] <= 2.0  # attempt 2 ceiling: 1.0 * 2^1 = 2.0


# ==============================================================================
# 3. Immediate Exit on Non-Retryable Errors
# ==============================================================================


@pytest.mark.asyncio
async def test_immediate_exit_on_value_error():
    """ValueError is non-retryable and must abort immediately on attempt 1."""
    recorder = MockSleepRecorder()
    attempts = 0

    async def bad_payload_operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("Malformed JSON argument")

    with pytest.raises(ValueError, match="Malformed JSON argument"):
        await call_with_full_jitter(
            bad_payload_operation,
            max_retries=4,
            base_delay_s=1.0,
            sleep_fn=recorder.sleep,
        )

    assert attempts == 1
    assert len(recorder.sleeps) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 404, 429])
async def test_immediate_exit_on_openrouter_non_retryable_http_statuses(status_code: int):
    """OpenRouter: 401, 403, 404, 429 must fail immediately with 0 retries."""
    recorder = MockSleepRecorder()
    attempts = 0

    async def api_call():
        nonlocal attempts
        attempts += 1
        raise _make_http_status_error(status_code)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await call_with_full_jitter(
            api_call,
            max_retries=3,
            base_delay_s=1.0,
            is_retryable=_is_retryable_openrouter_error,
            sleep_fn=recorder.sleep,
        )

    assert exc_info.value.response.status_code == status_code
    assert attempts == 1
    assert len(recorder.sleeps) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 404, 429])
async def test_immediate_exit_on_nim_non_retryable_http_statuses(status_code: int):
    """NIM: 401, 403, 404, 429 must fail immediately with 0 retries."""
    recorder = MockSleepRecorder()
    attempts = 0

    async def api_call():
        nonlocal attempts
        attempts += 1
        raise _make_http_status_error(status_code)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await call_with_full_jitter(
            api_call,
            max_retries=3,
            base_delay_s=1.0,
            is_retryable=_is_retryable_nim_error,
            sleep_fn=recorder.sleep,
        )

    assert exc_info.value.response.status_code == status_code
    assert attempts == 1
    assert len(recorder.sleeps) == 0


# ==============================================================================
# 4. Exception Re-raise on Exhaustion
# ==============================================================================


@pytest.mark.asyncio
async def test_call_with_full_jitter_exhaustion_reraises_original_error():
    """All retries fail -> original exception is propagated, attempts match max_retries."""
    recorder = MockSleepRecorder()
    attempts = 0

    async def persistently_failing_operation():
        nonlocal attempts
        attempts += 1
        req = httpx.Request("POST", "https://api.example.com")
        raise httpx.ConnectTimeout(f"Timed out on attempt {attempts}", request=req)

    with pytest.raises(httpx.ConnectTimeout, match="Timed out on attempt 3"):
        await call_with_full_jitter(
            persistently_failing_operation,
            max_retries=3,
            base_delay_s=0.5,
            max_delay_s=4.0,
            sleep_fn=recorder.sleep,
        )

    assert attempts == 3
    assert len(recorder.sleeps) == 2
    assert 0.0 <= recorder.sleeps[0] <= 0.5  # attempt 1 ceiling
    assert 0.0 <= recorder.sleeps[1] <= 1.0  # attempt 2 ceiling


# ==============================================================================
# 5. Retry on Transient HTTP 5xx Server Errors
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "predicate",
    [_is_retryable_openrouter_error, _is_retryable_nim_error],
    ids=["openrouter_filter", "nim_filter"],
)
async def test_transient_500_server_error_retries_and_recovers(predicate):
    """500/502/503 errors must be retried and succeed once upstream recovers."""
    recorder = MockSleepRecorder()
    attempts = 0

    async def flaky_server():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _make_http_status_error(503)
        return {"choices": [{"message": {"content": "ok"}}]}

    result = await call_with_full_jitter(
        flaky_server,
        max_retries=3,
        base_delay_s=0.5,
        is_retryable=predicate,
        sleep_fn=recorder.sleep,
    )

    assert result["choices"][0]["message"]["content"] == "ok"
    assert attempts == 2
    assert len(recorder.sleeps) == 1
    assert 0.0 <= recorder.sleeps[0] <= 0.5


# ==============================================================================
# 6. Custom Retry Filter Predicates
# ==============================================================================


@pytest.mark.asyncio
async def test_custom_predicate_filtering():
    """Custom is_retryable predicate determines whether to retry."""
    recorder = MockSleepRecorder()
    attempts = 0

    class CustomServiceError(Exception):
        def __init__(self, message: str, can_retry: bool):
            super().__init__(message)
            self.can_retry = can_retry

    async def custom_task():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise CustomServiceError("Transient db lock", can_retry=True)
        if attempts == 2:
            raise CustomServiceError("Permanent schema violation", can_retry=False)
        return "success"

    def custom_filter(exc: Exception) -> bool:
        return isinstance(exc, CustomServiceError) and exc.can_retry

    with pytest.raises(CustomServiceError, match="Permanent schema violation"):
        await call_with_full_jitter(
            custom_task,
            max_retries=5,
            base_delay_s=0.5,
            is_retryable=custom_filter,
            sleep_fn=recorder.sleep,
        )

    assert attempts == 2
    assert len(recorder.sleeps) == 1
