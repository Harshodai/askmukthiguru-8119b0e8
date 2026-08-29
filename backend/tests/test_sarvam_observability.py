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
    reasons = [s.attributes.get("gen_ai.retry_reason") for s in fake_tracer.spans]
    assert "tier_limit" in reasons


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
    reasons = [s.attributes.get("gen_ai.retry_reason") for s in fake_tracer.spans]
    assert "context_window" in reasons


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
    reasons = [s.attributes.get("gen_ai.retry_reason") for s in fake_tracer.spans]
    assert "key_rotation" in reasons
