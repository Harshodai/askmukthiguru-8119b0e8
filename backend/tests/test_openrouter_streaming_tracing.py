import pytest

from app.config import settings
from services.cost_tracker import TokenAccumulator, token_accumulator_var
from services.openrouter_service import OpenRouterService


class FakeSpan:
    def __init__(self, name, attributes):
        self.name = name
        self.attributes = dict(attributes)
        self.exceptions = []

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def update_name(self, name):
        self.name = name

    def record_exception(self, exc):
        self.exceptions.append(exc)


class FakeSpanContext:
    def __init__(self, span):
        self.span = span

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeTracer:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, name, attributes=None):
        span = FakeSpan(name, attributes or {})
        self.spans.append(span)
        return FakeSpanContext(span)


class FakeTrace:
    def __init__(self, tracer):
        self.tracer = tracer

    def get_tracer(self, _name):
        return self.tracer


@pytest.fixture(autouse=True)
def _disable_budget_guard(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    monkeypatch.setattr(settings, "openrouter_enforce_model_policy", False)


@pytest.mark.asyncio
async def test_openrouter_generate_stream_with_provider_usage_and_cost(monkeypatch):
    import opentelemetry.trace

    fake_tracer = FakeTracer()
    monkeypatch.setattr(opentelemetry.trace, "get_tracer", lambda _name: fake_tracer)

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json=None, headers=None, **kwargs):
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

                    yield f"data: {json_lib.dumps({'choices': [{'delta': {'content': 'The mind is '}}]})}"
                    yield f"data: {json_lib.dumps({'choices': [{'delta': {'content': 'a river.'}}], 'usage': {'prompt_tokens': 24, 'completion_tokens': 8, 'cost': 0.005, 'prompt_tokens_details': {'cached_tokens': 10}}})}"
                    yield "data: [DONE]"

            return MockStreamResponse()

    async def fake_get_client(self):
        return MockAsyncClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    service = OpenRouterService()
    accumulator = TokenAccumulator()
    token = token_accumulator_var.set(accumulator)
    try:
        chunks = []
        async for chunk in service.generate_stream(
            system_prompt="You are a sage.",
            user_prompt="What is the mind?",
            model="google/gemini-2.5-flash",
            operation="generate",
        ):
            chunks.append(chunk)
    finally:
        token_accumulator_var.reset(token)

    assert "".join(chunks) == "The mind is a river."
    assert len(fake_tracer.spans) == 1
    span = fake_tracer.spans[0]
    assert span.attributes["gen_ai.system"] == "openrouter"
    assert span.attributes["gen_ai.request.model"] == "google/gemini-2.5-flash"
    assert span.attributes["gen_ai.operation.name"] == "generate"
    assert span.attributes["gen_ai.usage.input_tokens"] == 24
    assert span.attributes["gen_ai.usage.output_tokens"] == 8
    assert span.attributes["gen_ai.usage.cached_input_tokens"] == 10
    assert span.attributes["gen_ai.usage.cost"] == pytest.approx(0.005)

    assert accumulator.tokens_in == 24
    assert accumulator.tokens_out == 8
    assert accumulator.cost_usd == pytest.approx(0.005)
    assert accumulator.estimated_cost_usd == 0.0


@pytest.mark.asyncio
async def test_openrouter_generate_stream_fallback_when_usage_omitted(monkeypatch):
    import opentelemetry.trace

    fake_tracer = FakeTracer()
    monkeypatch.setattr(opentelemetry.trace, "get_tracer", lambda _name: fake_tracer)

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json=None, headers=None, **kwargs):
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

                    yield f"data: {json_lib.dumps({'choices': [{'delta': {'content': 'Inner peace begins with stillness.'}}]})}"
                    yield "data: [DONE]"

            return MockStreamResponse()

    async def fake_get_client(self):
        return MockAsyncClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    service = OpenRouterService()
    accumulator = TokenAccumulator()
    token = token_accumulator_var.set(accumulator)
    try:
        chunks = []
        async for chunk in service.generate_stream(
            system_prompt="Be a teacher.",
            user_prompt="Tell me about peace.",
            model="google/gemini-2.5-flash",
            operation="generate",
        ):
            chunks.append(chunk)
    finally:
        token_accumulator_var.reset(token)

    assert "".join(chunks) == "Inner peace begins with stillness."
    assert len(fake_tracer.spans) == 1
    span = fake_tracer.spans[0]
    assert span.attributes["gen_ai.system"] == "openrouter"
    assert span.attributes["gen_ai.request.model"] == "google/gemini-2.5-flash"
    assert span.attributes["gen_ai.operation.name"] == "generate"
    # Token counts were estimated from message & buffer text
    assert span.attributes["gen_ai.usage.input_tokens"] > 0
    assert span.attributes["gen_ai.usage.output_tokens"] > 0
    # Cost fell back to configured model rate rather than coercing to 0.0
    expected_fallback_cost = OpenRouterService._fallback_cost(
        span.attributes["gen_ai.usage.input_tokens"],
        span.attributes["gen_ai.usage.output_tokens"],
        "google/gemini-2.5-flash",
    )
    assert expected_fallback_cost > 0.0
    assert span.attributes["gen_ai.usage.cost"] == pytest.approx(expected_fallback_cost)

    assert accumulator.tokens_in == span.attributes["gen_ai.usage.input_tokens"]
    assert accumulator.tokens_out == span.attributes["gen_ai.usage.output_tokens"]
    assert accumulator.cost_usd == 0.0
    assert accumulator.estimated_cost_usd == pytest.approx(expected_fallback_cost)
