import pytest

from app.config import settings
from services.llm.nim_provider import NimProvider
from services.nim_service import NimService


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
        # Return mock JSON response
        if "completions" in url:
            model = json.get("model", "") if json else ""
            if json and ("meta/llama-3.1-8b-instruct" in model):
                return FakeResponse(data={
                    "choices": [{"message": {"content": "{\"intent\": \"FACTUAL\", \"complexity\": \"simple\"}"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6}
                })
            return FakeResponse()
        return FakeResponse(status_code=404)

    async def get(self, url, **kwargs):
        if url == "/models":
            return FakeResponse(data={"data": []})
        return FakeResponse(status_code=404)


@pytest.mark.asyncio
async def test_nim_service_generate(monkeypatch):
    monkeypatch.setattr(settings, "nim_api_key", "test-api-key")
    monkeypatch.setattr(settings, "nim_generation_model", "some-other-model")
    
    # Capture client initialization
    async def fake_get_client(self):
        return FakeAsyncClient()
    monkeypatch.setattr(NimService, "_get_http_client", fake_get_client)

    service = NimService()
    res = await service.generate(system_prompt="Be a monk.", user_prompt="What is Zen?")
    assert res == "A wise teaching on mindfulness."


@pytest.mark.asyncio
async def test_nim_provider_delegation(monkeypatch):
    monkeypatch.setattr(settings, "nim_api_key", "test-api-key")
    
    async def fake_get_client(self):
        return FakeAsyncClient()
    monkeypatch.setattr(NimService, "_get_http_client", fake_get_client)

    service = NimService()
    provider = NimProvider(service)

    # Test classify_intent_and_complexity
    res = await provider.classify_intent_and_complexity("What is Zen?")
    assert res == {"intent": "FACTUAL", "complexity": "simple"}
