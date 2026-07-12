import pytest

from app.config import settings
from services.llm.openrouter_provider import OpenRouterProvider
from services.openrouter_service import OpenRouterService


class FakeResponse:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {
            "choices": [{"message": {"content": "A wise teaching on mindfulness."}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 8,
                "total_tokens": 18,
            },
        }

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.headers = kwargs.get("headers", {})

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, **kwargs):
        # Return mock JSON response for completions
        if "completions" in url:
            model = json.get("model", "") if json else ""
            # Generation model test expects default response
            if "some-other-model" in model:
                return FakeResponse()
            # Classification model test expects intent/complexity response
            return FakeResponse(data={
                "choices": [{"message": {"content": "INTENT: FACTUAL\nCOMPLEXITY: simple"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 6}
            })
        return FakeResponse()

    async def get(self, url, **kwargs):
        if url == "/models":
            return FakeResponse(data={"data": []})
        return FakeResponse(status_code=404)


@pytest.mark.asyncio
async def test_openrouter_service_generate(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    monkeypatch.setattr(settings, "openrouter_generation_model", "some-other-model")
    
    # Capture client initialization
    async def fake_get_client(self):
        return FakeAsyncClient()
    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    service = OpenRouterService()
    res = await service.generate(system_prompt="Be a monk.", user_prompt="What is Zen?")
    assert res == "A wise teaching on mindfulness."


@pytest.mark.asyncio
async def test_openrouter_provider_delegation(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    
    async def fake_get_client(self):
        return FakeAsyncClient()
    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    service = OpenRouterService()
    provider = OpenRouterProvider(service)

    # Test classify_intent_and_complexity
    res = await provider.classify_intent_and_complexity("What is Zen?")
    assert res == {"intent": "FACTUAL", "complexity": "simple"}


@pytest.mark.asyncio
async def test_openrouter_service_anthropic_caching(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    
    captured_calls = []

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, **kwargs):
            captured_calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse(data={
                "choices": [{"message": {"content": "Zen is peace."}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "prompt_tokens_details": {
                        "cached_tokens": 40
                    }
                }
            })

    async def fake_get_client(self):
        return MockAsyncClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    service = OpenRouterService()
    
    # 1. Test standard Anthropic model call
    with caplog.at_level(logging.INFO):
        res = await service.generate(
            system_prompt="Be a Zen master.",
            user_prompt="Explain mindfulness.",
            model="anthropic/claude-3-5-sonnet"
        )
    
    assert res == "Zen is peace."
    assert len(captured_calls) == 1
    call = captured_calls[0]
    
    # Verify model
    assert call["json"]["model"] == "anthropic/claude-3-5-sonnet"
    
    # Verify structured system prompt
    messages = call["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert isinstance(messages[0]["content"], list)
    assert messages[0]["content"][0]["type"] == "text"
    assert messages[0]["content"][0]["text"] == "Be a Zen master."
    assert messages[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    
    # Verify headers
    assert call["headers"] is not None
    assert call["headers"].get("anthropic-beta") == "prompt-caching-2024-07-31"

    # Verify logging of cached tokens
    assert any("OpenRouter Cache Hit: cached_tokens=40" in record.message for record in caplog.records)

    # 2. Test standard non-Anthropic model call (should not modify payload or send headers)
    captured_calls.clear()
    res = await service.generate(
        system_prompt="Be a Zen master.",
        user_prompt="Explain mindfulness.",
        model="meta-llama/llama-3.1-8b-instruct"
    )
    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["json"]["model"] == "meta-llama/llama-3.1-8b-instruct"
    messages = call["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert isinstance(messages[0]["content"], str)
    assert call["headers"] is None or "anthropic-beta" not in call["headers"]


@pytest.mark.asyncio
async def test_openrouter_service_anthropic_caching_stream(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    
    captured_calls = []

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json=None, headers=None, **kwargs):
            captured_calls.append({
                "method": method,
                "url": url,
                "json": json,
                "headers": headers
            })
            
            class MockStreamResponse:
                async def __aenter__(self):
                    return self
                async def __aexit__(self, exc_type, exc, tb):
                    pass
                def raise_for_status(self):
                    pass
                async def aiter_lines(self):
                    import json as json_lib
                    chunk = {
                        "choices": [{"delta": {"content": "Mindfulness is simple."}}]
                    }
                    yield f"data: {json_lib.dumps(chunk)}"
                    yield "data: [DONE]"
            
            return MockStreamResponse()

    async def fake_get_client(self):
        return MockAsyncClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    service = OpenRouterService()
    
    # 1. Test Anthropic streaming
    chunks = []
    async for chunk in service.generate_stream(
        system_prompt="Be a monk.",
        user_prompt="What is now?",
        model="anthropic/claude-3-5-sonnet"
    ):
        chunks.append(chunk)

    assert "".join(chunks) == "Mindfulness is simple."
    assert len(captured_calls) == 1
    call = captured_calls[0]
    
    # Verify model and stream payload
    assert call["json"]["model"] == "anthropic/claude-3-5-sonnet"
    assert call["json"]["stream"] is True
    
    # Verify structured system prompt
    messages = call["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert isinstance(messages[0]["content"], list)
    assert messages[0]["content"][0]["type"] == "text"
    assert messages[0]["content"][0]["text"] == "Be a monk."
    assert messages[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    
    # Verify headers
    assert call["headers"] is not None
    assert call["headers"].get("anthropic-beta") == "prompt-caching-2024-07-31"

    # 2. Test standard streaming (should not format messages or set headers)
    captured_calls.clear()
    chunks = []
    async for chunk in service.generate_stream(
        system_prompt="Be a monk.",
        user_prompt="What is now?",
        model="meta-llama/llama-3.1-8b-instruct"
    ):
        chunks.append(chunk)

    assert len(captured_calls) == 1
    call = captured_calls[0]
    messages = call["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert isinstance(messages[0]["content"], str)
    assert call["headers"] is None or "anthropic-beta" not in call["headers"]

