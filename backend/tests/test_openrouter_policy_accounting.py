import pytest

from app.config import settings
from services.cost_tracker import TokenAccumulator, token_accumulator_var
from services.openrouter_service import OpenRouterService


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"message": {"content": "Grounded guidance."}}],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 40,
                "cost": 0.0125,
            },
        }


@pytest.mark.asyncio
async def test_openrouter_policy_caps_request_and_records_actual_usage(monkeypatch):
    captured = {}

    class _Client:
        async def post(self, url, json=None, **kwargs):
            captured.update(json or {})
            return _Response()

    async def _client(self):
        return _Client()

    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    monkeypatch.setattr(OpenRouterService, "_get_http_client", _client)
    service = OpenRouterService()
    accumulator = TokenAccumulator()
    token = token_accumulator_var.set(accumulator)
    try:
        answer = await service.generate("system", "question", max_tokens=1600)
    finally:
        token_accumulator_var.reset(token)

    assert answer == "Grounded guidance."
    assert captured["max_tokens"] == settings.llm_max_tokens_fast
    assert captured["provider"]["data_collection"] == "deny"
    assert captured["provider"]["allow_fallbacks"] is True
    assert accumulator.tokens_in == 120
    assert accumulator.tokens_out == 40
    assert accumulator.cost_usd == pytest.approx(0.0125)
