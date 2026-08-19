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
