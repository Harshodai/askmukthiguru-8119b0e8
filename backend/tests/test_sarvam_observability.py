import pytest

from services import sarvam_service
from services.sarvam_service import SarvamCloudService
from app.config import settings


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
    monkeypatch.setattr(sarvam_service, "trace", FakeTrace(fake_tracer))
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
    assert span.name == "llm.sarvam.chat"
    assert span.attributes["llm.provider"] == "sarvam"
    assert span.attributes["llm.model_name"] == "sarvam-30b"
    assert span.attributes["llm.operation"] == "generate"
    assert span.attributes["llm.request.attempt"] == 1
    assert span.attributes["http.status_code"] == 200
    assert span.attributes["llm.token_count.prompt"] == 12
    assert span.attributes["llm.token_count.completion"] == 5
    assert span.attributes["llm.token_count.total"] == 17


@pytest.mark.asyncio
async def test_sarvam_injects_reasoning_effort(monkeypatch):
    recorded_payloads = []

    class CapturingResponse:
        status_code = 200
        text = ""
        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "Hello"}}],
                "usage": {"total_tokens": 10}
            }

    class CapturingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, headers=None, json=None):
            recorded_payloads.append(json)
            return CapturingResponse()

    monkeypatch.setattr(sarvam_service, "trace", FakeTrace(FakeTracer()))
    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", CapturingAsyncClient)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")
    monkeypatch.setattr(settings, "sarvam_reasoning_effort", "medium")
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    service = SarvamCloudService()
    
    # Test setting from settings
    await service.generate(
        system_prompt="system",
        user_prompt="hello",
        max_tokens=64
    )
    
    assert len(recorded_payloads) == 1
    assert recorded_payloads[0]["reasoning_effort"] == "medium"

    # Test explicit override in kwargs
    await service.generate(
        system_prompt="system",
        user_prompt="hello",
        max_tokens=64,
        reasoning_effort="low"
    )
    assert len(recorded_payloads) == 2
    assert recorded_payloads[1]["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_sarvam_reasoning_content_fallback(monkeypatch):
    class FallbackResponse:
        status_code = 200
        text = ""
        @staticmethod
        def json():
            return {
                "choices": [{
                    "message": {
                        "content": "   ",  # empty/whitespace content
                        "reasoning_content": "This is reasoning that serves as fallback."
                    }
                }],
                "usage": {"total_tokens": 10}
            }

    class FallbackAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, headers=None, json=None):
            return FallbackResponse()

    monkeypatch.setattr(sarvam_service, "trace", FakeTrace(FakeTracer()))
    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", FallbackAsyncClient)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-30b")
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    service = SarvamCloudService()
    result = await service.generate(
        system_prompt="system",
        user_prompt="hello",
        max_tokens=64
    )

    # Content should fall back to reasoning_content
    assert result == "This is reasoning that serves as fallback."


