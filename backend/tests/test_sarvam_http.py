"""Regression test for SarvamHTTPGateway 429 key-rotation bounding (audit finding 9).

With N>1 keys, every key rate-limited by Sarvam must be tried at most once per
request attempt; when the whole key set is exhausted the gateway must stop
rotating and surface the 429 instead of spinning in the retry loop.
"""

from types import SimpleNamespace

import httpx
import pytest

from services.gateways import sarvam_http
from services.gateways.sarvam_http import SarvamHTTPGateway


def _mock_settings() -> SimpleNamespace:
    # Non-production fixture credentials — mocked HTTP client, no real API calls.
    return SimpleNamespace(
        sarvam_api_key="key-a,key-b",  # gitleaks:allow
        sarvam_30b_api_key=None,
        sarvam_30b_endpoint=None,
        sarvam_base_url="https://api.sarvam.ai/v1",
        llm_timeout=10,
        llm_max_retries=2,
        sarvam_max_tokens=4096,
    )


@pytest.mark.asyncio
async def test_429_rotation_is_bounded_and_raises_when_all_keys_exhausted(monkeypatch):
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(429, text="rate limited")

    # Capture the real client class BEFORE monkeypatching: sarvam_http.httpx is
    # the same module object as this test's httpx, so the patch is visible to
    # the factory itself; calling the patched name would recurse into the
    # factory and blow up with "multiple values for keyword argument 'transport'".
    real_async_client = httpx.AsyncClient

    def client_factory(**kwargs) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(sarvam_http, "settings", _mock_settings())
    monkeypatch.setattr(sarvam_http.httpx, "AsyncClient", client_factory)
    monkeypatch.setenv("SARVAM_RPM_LIMIT", "0")

    gateway = SarvamHTTPGateway()

    with pytest.raises(httpx.HTTPStatusError):
        await gateway.call(
            messages=[{"role": "user", "content": "hello"}],
            model="sarvam-30b",
            max_retries=2,
        )

    n_keys = 2
    max_retries = 2
    per_attempt = n_keys  # each key tried once, then raise
    assert request_count == per_attempt * max_retries, (
        f"429 rotation not bounded: {request_count} requests for {n_keys} keys"
    )
    assert request_count >= n_keys


def test_is_chat_priority_classification(monkeypatch):
    """Verify that requests are accurately classified into chat vs background priority."""
    monkeypatch.setattr(sarvam_http, "settings", _mock_settings())
    gateway = SarvamHTTPGateway()

    # Explicit is_chat flag takes highest precedence
    assert gateway._is_chat_priority(is_chat=True, operation="batch_ingest") is True
    assert gateway._is_chat_priority(is_chat=False, operation="chat") is False

    # Explicit priority takes next precedence
    assert gateway._is_chat_priority(priority="chat") is True
    assert gateway._is_chat_priority(priority="high") is True
    assert gateway._is_chat_priority(priority="interactive") is True
    assert gateway._is_chat_priority(priority="background") is False
    assert gateway._is_chat_priority(priority="low") is False

    # Operation name inference
    assert gateway._is_chat_priority(operation="generate") is True
    assert gateway._is_chat_priority(operation="classification") is True
    assert gateway._is_chat_priority(operation="verification") is True
    assert gateway._is_chat_priority(operation="l1_extract") is False
    assert gateway._is_chat_priority(operation="batch_ingest") is False
    assert gateway._is_chat_priority(operation="l3_persona") is False
    assert gateway._is_chat_priority(operation="entity_resolution") is False


@pytest.mark.asyncio
async def test_chat_priority_reservation_active_tracking(monkeypatch):
    """Verify that active chat requests are tracked so background workers yield."""
    import asyncio
    import json

    monkeypatch.setattr(sarvam_http, "settings", _mock_settings())
    monkeypatch.setenv("SARVAM_RPM_LIMIT", "60")

    chat_started = asyncio.Event()
    chat_can_finish = asyncio.Event()
    execution_order: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        op = body.get("model", "")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "mock response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    real_async_client = httpx.AsyncClient

    def client_factory(**kwargs) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(sarvam_http.httpx, "AsyncClient", client_factory)

    gateway = SarvamHTTPGateway()

    # Verify initial state
    assert gateway._active_chat_requests == 0

    async def run_chat():
        async with gateway._chat_state_lock:
            gateway._active_chat_requests += 1
        chat_started.set()
        await chat_can_finish.wait()
        async with gateway._chat_state_lock:
            gateway._active_chat_requests = max(0, gateway._active_chat_requests - 1)
        execution_order.append("chat")

    async def run_background():
        await chat_started.wait()
        # Should execute call with is_chat=False
        res = await gateway.call(
            messages=[{"role": "user", "content": "bg task"}],
            model="sarvam-30b",
            is_chat=False,
        )
        execution_order.append("background")
        return res

    # Start chat holding the active state
    chat_task = asyncio.create_task(run_chat())
    bg_task = asyncio.create_task(run_background())

    # Wait for chat to start and confirm active state is tracked
    await chat_started.wait()
    assert gateway._active_chat_requests == 1

    # Allow background a moment to start and notice active chat (and yield)
    await asyncio.sleep(0.1)
    assert execution_order == []

    # Now let chat complete
    chat_can_finish.set()
    await asyncio.gather(chat_task, bg_task)

    assert gateway._active_chat_requests == 0
    assert execution_order == ["chat", "background"]

