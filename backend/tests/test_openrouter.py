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
