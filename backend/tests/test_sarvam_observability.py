import pytest

from app.config import settings
from services import sarvam_service
from services.sarvam_service import SarvamCloudService


class FakeSpan:
    def __init__(self, name, attributes):
        self.name = name
        self.attributes = dict(attributes)
        self.exceptions = []

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def update_name(self, name):
        self.name = name

    def set_status(self, status):
        pass

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


class FakeResponse:
    status_code = 200
    text = ""

    def raise_for_status(self):
        pass

    @staticmethod
    def json():
        return {
            "model": "sarvam-30b",
            "choices": [{"message": {"content": "A gentle answer"}}],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "total_tokens": 17,
            },
        }


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *_args, **_kwargs):
        return FakeResponse()


@pytest.mark.asyncio
async def test_sarvam_call_records_otel_span_attributes(monkeypatch):
    fake_tracer = FakeTracer()
    monkeypatch.setattr("services.gateways.sarvam_http.trace", FakeTrace(fake_tracer))
    monkeypatch.setattr("services.gateways.sarvam_http._has_otel", True)
    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")
    monkeypatch.setattr(settings, "sarvam_cloud_classify_model", "sarvam-30b")
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    service = SarvamCloudService()
    result = await service._call_api(
        messages=[{"role": "user", "content": "hello"}],
        model="sarvam-30b",
        max_tokens=64,
        operation="generate",
    )

    assert result == "A gentle answer"
    span = fake_tracer.spans[0]
    # OTel GenAI semantic conventions (migrated from project-local `llm.*` on
    # 2026-08-29). Langfuse and other GenAI-aware backends key off `gen_ai.*`;
    # the old names were silently ignored, so Sarvam usage never reached a
    # dashboard. Must stay identical in shape to the OpenRouter spans emitted
    # by app/llm_tracing.py.
    assert span.name == "generate sarvam-30b"
    assert span.attributes["gen_ai.system"] == "sarvam"
    assert span.attributes["gen_ai.request.model"] == "sarvam-30b"
    assert span.attributes["gen_ai.operation.name"] == "generate"
    assert span.attributes["gen_ai.request.attempt"] == 1
    assert span.attributes["http.status_code"] == 200
    assert span.attributes["gen_ai.usage.input_tokens"] == 12
    assert span.attributes["gen_ai.usage.output_tokens"] == 5
    assert span.attributes["gen_ai.usage.cost"] == pytest.approx((12 + 5) / 1000.0 * 0.0001)
    assert span.attributes["gen_ai.response.model"] == "sarvam-30b"


@pytest.mark.asyncio
async def test_sarvam_injects_reasoning_effort(monkeypatch):
    recorded_payloads = []

    class CapturingResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            pass

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "Hello"}}], "usage": {"total_tokens": 10}}

    class CapturingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, **kwargs):
            recorded_payloads.append(json)
            return CapturingResponse()

    monkeypatch.setattr("services.gateways.sarvam_http.trace", FakeTrace(FakeTracer()))
    monkeypatch.setattr("services.gateways.sarvam_http._has_otel", True)
    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", CapturingAsyncClient)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")
    monkeypatch.setattr(settings, "sarvam_reasoning_effort", "medium")
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    service = SarvamCloudService()

    # Test setting from settings
    await service.generate(system_prompt="system", user_prompt="hello", max_tokens=64)

    assert len(recorded_payloads) == 1
    assert recorded_payloads[0]["reasoning_effort"] == "medium"

    # Test explicit override in kwargs
    await service.generate(
        system_prompt="system", user_prompt="hello", max_tokens=64, reasoning_effort="low"
    )
    assert len(recorded_payloads) == 2
    assert recorded_payloads[1]["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_sarvam_reasoning_content_fallback(monkeypatch):
    class FallbackResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            pass

        @staticmethod
        def json():
            return {
                "choices": [
                    {
                        "message": {
                            "content": "   ",  # empty/whitespace content
                            "reasoning_content": "This is reasoning that serves as fallback.",
                        }
                    }
                ],
                "usage": {"total_tokens": 10},
            }

    class FallbackAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, **kwargs):
            return FallbackResponse()

    monkeypatch.setattr("services.gateways.sarvam_http.trace", FakeTrace(FakeTracer()))
    monkeypatch.setattr("services.gateways.sarvam_http._has_otel", True)
    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", FallbackAsyncClient)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    service = SarvamCloudService()
    result = await service.generate(system_prompt="system", user_prompt="hello", max_tokens=64)

    # Content should fall back to reasoning_content
    assert result == "This is reasoning that serves as fallback."


class QueuedResponse:
    def __init__(self, status_code, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {
            "model": "sarvam-30b",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"status {self.status_code}")

    def json(self):
        return self._payload


class QueuedAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None, **kwargs):
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_sarvam_tier_limit_retry_records_reason(monkeypatch):
    fake_tracer = FakeTracer()
    monkeypatch.setattr("services.gateways.sarvam_http.trace", FakeTrace(fake_tracer))
    monkeypatch.setattr("services.gateways.sarvam_http._has_otel", True)

    class Client(QueuedAsyncClient):
        _responses = [
            QueuedResponse(
                400,
                text="exceeds the maximum allowed for max_tokens for your subscription tier free: 2048",
            ),
            QueuedResponse(200),
        ]

    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", Client)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")
    monkeypatch.setattr(settings, "llm_max_retries", 2)

    service = SarvamCloudService()
    result = await service._call_api(
        messages=[{"role": "user", "content": "hello"}],
        model="sarvam-30b",
        max_tokens=64,
        operation="generate",
    )

    assert result == "ok"
    assert len(fake_tracer.spans) == 2
    # First span failed on 400 tier limit
    assert fake_tracer.spans[0].attributes.get("gen_ai.retry_reason") == "tier_limit"
    # Second span succeeded and recorded usage & cost
    assert fake_tracer.spans[1].attributes.get("gen_ai.retry_reason") is None
    assert fake_tracer.spans[1].attributes["http.status_code"] == 200
    assert fake_tracer.spans[1].attributes["gen_ai.usage.input_tokens"] == 1
    assert fake_tracer.spans[1].attributes["gen_ai.usage.output_tokens"] == 1
    assert fake_tracer.spans[1].attributes["gen_ai.usage.cost"] == pytest.approx((1 + 1) / 1000.0 * 0.0001)
    assert fake_tracer.spans[1].attributes["gen_ai.response.model"] == "sarvam-30b"


@pytest.mark.asyncio
async def test_sarvam_context_window_retry_records_reason(monkeypatch):
    fake_tracer = FakeTracer()
    monkeypatch.setattr("services.gateways.sarvam_http.trace", FakeTrace(fake_tracer))
    monkeypatch.setattr("services.gateways.sarvam_http._has_otel", True)

    class Client(QueuedAsyncClient):
        _responses = [
            QueuedResponse(
                422,
                text=(
                    "prompt_tokens (100) + max_tokens (4096) = 4196 exceeds the "
                    "model context window of 4096"
                ),
            ),
            QueuedResponse(200),
        ]

    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", Client)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")
    monkeypatch.setattr(settings, "llm_max_retries", 2)

    service = SarvamCloudService()
    result = await service._call_api(
        messages=[{"role": "user", "content": "hello"}],
        model="sarvam-30b",
        max_tokens=4096,
        operation="generate",
    )

    assert result == "ok"
    assert len(fake_tracer.spans) == 2
    # First span failed on 422 context window reduction
    assert fake_tracer.spans[0].attributes.get("gen_ai.retry_reason") == "context_window"
    # Second span succeeded
    assert fake_tracer.spans[1].attributes.get("gen_ai.retry_reason") is None
    assert fake_tracer.spans[1].attributes["http.status_code"] == 200
    assert fake_tracer.spans[1].attributes["gen_ai.usage.cost"] == pytest.approx((1 + 1) / 1000.0 * 0.0001)


@pytest.mark.asyncio
async def test_sarvam_context_window_sarvam_m_upgrade_retry_records_reason(monkeypatch):
    fake_tracer = FakeTracer()
    monkeypatch.setattr("services.gateways.sarvam_http.trace", FakeTrace(fake_tracer))
    monkeypatch.setattr("services.gateways.sarvam_http._has_otel", True)

    class Client(QueuedAsyncClient):
        _responses = [
            QueuedResponse(
                422,
                text="exceeds the model context window",
            ),
            QueuedResponse(200, payload={
                "model": "sarvam-30b",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            }),
        ]

    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", Client)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-m")
    monkeypatch.setattr(settings, "llm_max_retries", 2)

    service = SarvamCloudService()
    result = await service._call_api(
        messages=[{"role": "user", "content": "hello"}],
        model="sarvam-m",
        max_tokens=2048,
        operation="generate",
    )

    assert result == "ok"
    assert len(fake_tracer.spans) == 2
    # First span on sarvam-m failed with context_window retry reason
    assert fake_tracer.spans[0].attributes.get("gen_ai.retry_reason") == "context_window"
    assert fake_tracer.spans[0].attributes["gen_ai.request.model"] == "sarvam-m"
    # Second span upgraded to sarvam-30b and succeeded
    assert fake_tracer.spans[1].attributes.get("gen_ai.retry_reason") is None
    assert fake_tracer.spans[1].attributes["gen_ai.request.model"] == "sarvam-30b"
    assert fake_tracer.spans[1].attributes["http.status_code"] == 200
    assert fake_tracer.spans[1].attributes["gen_ai.usage.cost"] == pytest.approx((20 + 10) / 1000.0 * 0.0001)
    assert fake_tracer.spans[1].attributes["gen_ai.response.model"] == "sarvam-30b"


@pytest.mark.asyncio
async def test_sarvam_key_rotation_retry_records_reason(monkeypatch):
    fake_tracer = FakeTracer()
    monkeypatch.setattr("services.gateways.sarvam_http.trace", FakeTrace(fake_tracer))
    monkeypatch.setattr("services.gateways.sarvam_http._has_otel", True)

    class Client(QueuedAsyncClient):
        _responses = [
            QueuedResponse(429, text="rate limited"),
            QueuedResponse(200),
        ]

    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", Client)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key-1,test-key-2")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")
    monkeypatch.setattr(settings, "llm_max_retries", 2)

    service = SarvamCloudService()
    result = await service._call_api(
        messages=[{"role": "user", "content": "hello"}],
        model="sarvam-30b",
        max_tokens=64,
        operation="generate",
    )

    assert result == "ok"
    assert len(fake_tracer.spans) == 2
    # First span hit 429 and rotated key
    assert fake_tracer.spans[0].attributes.get("gen_ai.retry_reason") == "key_rotation"
    # Second span succeeded with rotated key
    assert fake_tracer.spans[1].attributes.get("gen_ai.retry_reason") is None
    assert fake_tracer.spans[1].attributes["http.status_code"] == 200
    assert fake_tracer.spans[1].attributes["gen_ai.usage.cost"] == pytest.approx((1 + 1) / 1000.0 * 0.0001)


@pytest.mark.asyncio
async def test_sarvam_http_gateway_direct_observability_and_cost(monkeypatch):
    from services.gateways.sarvam_http import SarvamHTTPGateway

    fake_tracer = FakeTracer()
    monkeypatch.setattr("services.gateways.sarvam_http.trace", FakeTrace(fake_tracer))
    monkeypatch.setattr("services.gateways.sarvam_http._has_otel", True)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")

    class DirectResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "model": "sarvam-30b",
                "choices": [{"message": {"content": "direct answer"}}],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 25,
                    "total_tokens": 75,
                },
            }

    class DirectAsyncClient:
        async def post(self, url, headers=None, json=None, **kwargs):
            return DirectResponse()

    async def mock_get_client():
        return DirectAsyncClient()

    gateway = SarvamHTTPGateway()
    monkeypatch.setattr(gateway, "_get_http_client", mock_get_client)

    result = await gateway.call(
        messages=[{"role": "user", "content": "test question"}],
        model="sarvam-30b",
        max_tokens=100,
        operation="custom_op",
    )

    assert result == "direct answer"
    assert len(fake_tracer.spans) == 1
    span = fake_tracer.spans[0]
    assert span.name == "custom_op sarvam-30b"
    assert span.attributes["gen_ai.system"] == "sarvam"
    assert span.attributes["gen_ai.operation.name"] == "custom_op"
    assert span.attributes["gen_ai.request.model"] == "sarvam-30b"
    assert span.attributes["http.status_code"] == 200
    assert span.attributes["gen_ai.usage.input_tokens"] == 50
    assert span.attributes["gen_ai.usage.output_tokens"] == 25
    expected_cost = (50 + 25) / 1000.0 * 0.0001
    assert span.attributes["gen_ai.response.model"] == "sarvam-30b"


@pytest.mark.asyncio
async def test_sarvam_generate_stream_observability_and_token_tracking(monkeypatch):
    import opentelemetry.trace
    from services.cost_tracker import TokenAccumulator, token_accumulator_var

    fake_tracer = FakeTracer()
    monkeypatch.setattr(opentelemetry.trace, "get_tracer", lambda _name: fake_tracer)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")

    class StreamResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            import json as json_lib

            yield f"data: {json_lib.dumps({'choices': [{'delta': {'content': 'Spiritual '}}]})}"
            yield f"data: {json_lib.dumps({'choices': [{'delta': {'content': 'wisdom.'}}], 'usage': {'prompt_tokens': 15, 'completion_tokens': 5}})}"
            yield "data: [DONE]"

    class StreamAsyncClient:
        def stream(self, method, url, headers=None, json=None, **kwargs):
            class StreamCtx:
                async def __aenter__(self):
                    return StreamResponse()

                async def __aexit__(self, exc_type, exc, tb):
                    pass

            return StreamCtx()

    async def mock_get_client(self):
        return StreamAsyncClient()

    monkeypatch.setattr(SarvamCloudService, "_get_http_client", mock_get_client)

    service = SarvamCloudService()
    accumulator = TokenAccumulator()
    token = token_accumulator_var.set(accumulator)
    try:
        chunks = []
        async for chunk in service.generate_stream("Be wise.", "What is peace?"):
            chunks.append(chunk)
    finally:
        token_accumulator_var.reset(token)

    assert "".join(chunks) == "Spiritual wisdom."
    assert len(fake_tracer.spans) == 1
    span = fake_tracer.spans[0]
    assert span.attributes["gen_ai.system"] == "sarvam"
    assert span.attributes["gen_ai.request.model"] == "sarvam-30b"
    assert span.attributes["gen_ai.operation.name"] == "generate"
    assert span.attributes["http.status_code"] == 200
    assert span.attributes["gen_ai.usage.input_tokens"] == 15
    assert span.attributes["gen_ai.usage.output_tokens"] == 5
    expected_cost = (15 + 5) / 1000.0 * 0.0001
    assert span.attributes["gen_ai.usage.cost"] == pytest.approx(expected_cost)

    assert accumulator.tokens_in == 15
    assert accumulator.tokens_out == 5
    assert accumulator.cost_usd == pytest.approx(expected_cost)


@pytest.mark.asyncio
async def test_sarvam_generate_stream_fallback_token_estimation_when_usage_omitted(monkeypatch):
    import opentelemetry.trace
    from services.cost_tracker import TokenAccumulator, token_accumulator_var

    fake_tracer = FakeTracer()
    monkeypatch.setattr(opentelemetry.trace, "get_tracer", lambda _name: fake_tracer)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")

    class StreamResponseNoUsage:
        status_code = 200

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            import json as json_lib

            yield f"data: {json_lib.dumps({'choices': [{'delta': {'content': 'Mindful living and calm.'}}]})}"
            yield "data: [DONE]"

    class StreamAsyncClient:
        def stream(self, method, url, headers=None, json=None, **kwargs):
            class StreamCtx:
                async def __aenter__(self):
                    return StreamResponseNoUsage()

                async def __aexit__(self, exc_type, exc, tb):
                    pass

            return StreamCtx()

    async def mock_get_client(self):
        return StreamAsyncClient()

    monkeypatch.setattr(SarvamCloudService, "_get_http_client", mock_get_client)

    service = SarvamCloudService()
    accumulator = TokenAccumulator()
    token = token_accumulator_var.set(accumulator)
    try:
        chunks = []
        async for chunk in service.generate_stream("You are a teacher.", "Explain meditation."):
            chunks.append(chunk)
    finally:
        token_accumulator_var.reset(token)

    assert "".join(chunks) == "Mindful living and calm."
    assert len(fake_tracer.spans) == 1
    span = fake_tracer.spans[0]
    assert span.attributes["gen_ai.system"] == "sarvam"
    assert span.attributes["gen_ai.request.model"] == "sarvam-30b"
    assert span.attributes["gen_ai.operation.name"] == "generate"
    assert span.attributes["gen_ai.usage.input_tokens"] > 0
    assert span.attributes["gen_ai.usage.output_tokens"] > 0
    assert span.attributes["gen_ai.usage.cost"] > 0.0

    assert accumulator.tokens_in > 0
    assert accumulator.tokens_out > 0
    assert accumulator.cost_usd > 0.0
