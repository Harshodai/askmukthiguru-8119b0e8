"""Stream-leg refusal (CA-4): a refusal/content_filter finish_reason must
propagate as ProviderRefusalError WITHOUT recording a circuit failure —
same semantics as the non-stream path. Regression test for the missing
`except ProviderRefusalError` in the streaming retry loop (review 2026-10-14):
before the fix the refusal fell into generic `except Exception`, which called
`record_failure()` and logged a provider-error on a healthy provider.
"""

import pytest

from app.config import settings
from services.openrouter_service import OpenRouterService, ProviderRefusalError


@pytest.fixture(autouse=True)
def _disable_budget_guard(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    monkeypatch.setattr(settings, "openrouter_enforce_model_policy", False)


def _refusal_client():
    import services.openrouter_service as or_mod

    real_client_cls = or_mod.httpx.AsyncClient

    class MockStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            import json as json_lib

            yield f"data: {json_lib.dumps({'choices': [{'delta': {}, 'finish_reason': 'refusal'}]})}"
            yield "data: [DONE]"

    class MockAsyncClient(real_client_cls):
        def stream(self, method, url, json=None, headers=None, **kwargs):
            return MockStreamResponse()

    async def fake_get_client(self):
        return MockAsyncClient()

    return fake_get_client


@pytest.mark.asyncio
async def test_stream_refusal_propagates_without_circuit_failure(monkeypatch):
    import opentelemetry.trace

    class _Span:
        def set_attribute(self, *a, **k):
            pass

        def record_exception(self, e):
            pass

    class _Ctx:
        def __enter__(self):
            return _Span()

        def __exit__(self, *a):
            return False

    class _Tracer:
        def start_as_current_span(self, *a, **k):
            return _Ctx()

    monkeypatch.setattr(opentelemetry.trace, "get_tracer", lambda _name: _Tracer())
    monkeypatch.setattr(OpenRouterService, "_get_http_client", _refusal_client())

    service = OpenRouterService()
    failures = []
    monkeypatch.setattr(service._circuit, "record_failure", lambda *a, **k: failures.append(1))

    with pytest.raises(ProviderRefusalError):
        async for _ in service.generate_stream(
            system_prompt="You are a sage.",
            user_prompt="What is the mind?",
            model="google/gemini-2.5-flash",
            operation="generate",
        ):
            pass
    assert failures == [], "refusal must not record a circuit-breaker failure"
