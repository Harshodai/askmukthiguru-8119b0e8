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


class _ResponseWithoutCost:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"message": {"content": "Grounded guidance."}}],
            "usage": {
                "prompt_tokens": 1_000,
                "completion_tokens": 2_000,
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
    assert accumulator.estimated_cost_usd == 0.0


@pytest.mark.asyncio
async def test_openrouter_missing_cost_uses_model_rate_without_changing_answer(monkeypatch):
    class _Client:
        async def post(self, url, json=None, **kwargs):
            return _ResponseWithoutCost()

    async def _client(self):
        return _Client()

    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    monkeypatch.setattr(
        settings,
        "openrouter_generation_model",
        "qwen/qwen3-30b-a3b-instruct-2507",
    )
    monkeypatch.setattr(OpenRouterService, "_get_http_client", _client)
    service = OpenRouterService()
    accumulator = TokenAccumulator()
    token = token_accumulator_var.set(accumulator)
    try:
        answer = await service.generate("system", "question", max_tokens=1600)
    finally:
        token_accumulator_var.reset(token)

    assert answer == "Grounded guidance."
    assert accumulator.cost_usd == 0.0
    assert accumulator.estimated_cost_usd == pytest.approx(
        (1_000 * 0.04815 + 2_000 * 0.1931) / 1_000_000
    )


def test_openrouter_usage_cost_distinguishes_missing_and_zero():
    assert OpenRouterService._usage_cost({}) is None
    assert OpenRouterService._usage_cost({"cost": None}) == 0.0
    assert OpenRouterService._usage_cost({"cost": "0.0125"}) == pytest.approx(0.0125)
    assert OpenRouterService._usage_cost({"cost": "invalid"}) is None


def test_openrouter_gemini_fallback_rates_are_accounted_when_provider_omits_cost():
    production_estimate = OpenRouterService._fallback_cost(
        1_000,
        2_000,
        "google/gemini-2.5-flash",
    )
    assert production_estimate == pytest.approx((1_000 * 0.30 + 2_000 * 2.50) / 1_000_000)

    configured_default_estimate = OpenRouterService._fallback_cost(
        1_000,
        2_000,
        "google/gemini-3.6-flash",
    )
    assert configured_default_estimate == pytest.approx(
        (1_000 * 0.75 + 2_000 * 3.75) / 1_000_000
    )
