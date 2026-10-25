"""reasoning_effort kwarg: Anthropic scorer gets an effort level, not a 200-token cap.

Audit 2026-10-25 (review R2): the provider-wide ``reasoning.max_tokens = max_tokens // 4``
left the relevance scorer a 200-token reasoning budget, below OpenRouter's documented
1024 minimum for Anthropic models. Callers can now ask for an effort level instead.
"""

import pytest

from app.config import settings
from services.openrouter_service import OpenRouterService


async def _payload_for(monkeypatch, **gen_kwargs):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-mock-key")
    service = OpenRouterService()
    captured = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [{"message": {"content": "3"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1},
            }

    class _Client:
        async def post(self, url, json=None, headers=None, **kwargs):
            captured["payload"] = json
            return _Resp()

    async def _get_client(self):
        return _Client()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", _get_client)
    await service.generate("sys", "user", **gen_kwargs)
    return captured["payload"], service


@pytest.mark.asyncio
async def test_reasoning_effort_replaces_token_cap(monkeypatch):
    payload, service = await _payload_for(
        monkeypatch, max_tokens=2048, operation="verify", reasoning_effort="low"
    )
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["max_tokens"] == service._policy.output_ceiling("verify")
    assert payload["max_tokens"] > 1024


@pytest.mark.asyncio
async def test_default_reasoning_cap_is_unchanged(monkeypatch):
    payload, _ = await _payload_for(monkeypatch, max_tokens=800)
    assert payload["reasoning"] == {"max_tokens": 200}


@pytest.mark.asyncio
async def test_unknown_effort_value_is_ignored(monkeypatch):
    payload, _ = await _payload_for(monkeypatch, max_tokens=800, reasoning_effort="ultra")
    assert payload["reasoning"] == {"max_tokens": 200}
