"""Unit tests for the LightRAG OpenRouter retry predicate.

llm_func in lightrag_service wraps container.openrouter.generate() in a
tenacity @retry. Only transient failures (network/timeout, 429, retryable
5xx) may be retried — permanent failures (401 auth, 400/422 validation)
must fail fast so the default-LLM fallback runs immediately instead of
burning 3 stale attempts.
"""

import logging

import httpx
import pytest
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from services.lightrag_service import (
    _TRANSIENT_OPENROUTER_STATUSES,
    _is_transient_openrouter_error,
)

_PERMANENT_HTTP_STATUSES = [400, 401, 403, 404, 422]
_TRANSIENT_HTTP_STATUSES = sorted(_TRANSIENT_OPENROUTER_STATUSES)


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError("test failure", request=request, response=response)


@pytest.mark.parametrize("status", _PERMANENT_HTTP_STATUSES)
def test_predicate_rejects_permanent_http_statuses(status):
    assert not _is_transient_openrouter_error(_http_status_error(status))


@pytest.mark.parametrize("status", _TRANSIENT_HTTP_STATUSES)
def test_predicate_accepts_transient_http_statuses(status):
    assert _is_transient_openrouter_error(_http_status_error(status))


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        httpx.RemoteProtocolError("server closed connection"),
        ConnectionError("connection reset by peer"),
        OSError("socket failure"),
        TimeoutError("deadline exceeded"),
    ],
)
def test_predicate_accepts_network_and_timeout_errors(exc):
    assert _is_transient_openrouter_error(exc)


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("Empty or invalid response from OpenRouter API"),
        KeyError("choices"),
        RuntimeError("unexpected failure"),
    ],
)
def test_predicate_rejects_other_exceptions(exc):
    assert not _is_transient_openrouter_error(exc)


def _build_retry_wrapper(fake_generate):
    """Mirror the @retry used inside lightrag_service.llm_func (same
    predicate, stop and reraise), with the backoff collapsed to zero so the
    transient tests stay fast."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0, min=0, max=0),
        retry=retry_if_exception(_is_transient_openrouter_error),
        before_sleep=before_sleep_log(logging.getLogger("lightrag_service"), logging.WARNING),
        reraise=True,
    )
    async def _openrouter_with_retry():
        return await fake_generate()

    return _openrouter_with_retry


async def _run_with_fallback(wrapped):
    """Same fallback shape as llm_func: an exception lands on response = ''."""
    try:
        return await wrapped()
    except Exception:
        return ""


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 400, 422])
async def test_permanent_error_calls_generate_once_then_falls_back(status):
    calls = {"n": 0}

    async def fake_generate():
        calls["n"] += 1
        raise _http_status_error(status)

    response = await _run_with_fallback(_build_retry_wrapper(fake_generate))
    assert calls["n"] == 1
    assert response == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        _http_status_error(429),
        _http_status_error(503),
        _http_status_error(504),
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
    ],
)
async def test_transient_error_retries_three_times_then_falls_back(exc):
    calls = {"n": 0}

    async def fake_generate():
        calls["n"] += 1
        raise exc

    response = await _run_with_fallback(_build_retry_wrapper(fake_generate))
    assert calls["n"] == 3
    assert response == ""
