"""CA-3 (schema-constrained scorer JSON) + CA-4 (refusal stop_reason plumbing).

Host-side, mocks/fakes only — no provider calls, no store writes.
"""

import json

import pytest

from app.config import settings
from services.first_person_pipeline import (
    _RELEVANCE_INDETERMINATE,
    _relevance_select,
)
from services.openrouter_service import ProviderRefusalError


class _SyncLLM:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc = reply, exc
        self.calls, self.kwargs = [], {}

    def generate(self, system_prompt="", user_prompt="", **kw):
        self.calls.append((system_prompt, user_prompt))
        self.kwargs.update(kw)
        if self.exc:
            raise self.exc
        return self.reply


def _clips(n=3):
    return [{"verbatim_text": f"clip {i}"} for i in range(n)]


# ---- CA-3: schema-constrained JSON output ------------------------------------

HAIKU = "anthropic/claude-haiku-5.5"


def test_ca3_json_schema_requested_for_haiku_and_valid_scores_served(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_model", HAIKU)
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 2)
    llm = _SyncLLM(json.dumps({"scores": [3, 1, 0]}))
    assert _relevance_select("q?", _clips(3), llm) == 0
    # CA-1 unchanged: temperature still omitted for this model.
    assert llm.kwargs.get("temperature") is None
    # CA-3: the scorer carries the schema request.
    rf = llm.kwargs.get("response_format")
    assert isinstance(rf, dict) and rf.get("type") == "json_schema"
    assert rf["json_schema"]["name"] == "relevance_scores"
    assert llm.kwargs.get("max_tokens") == 1024
    # The prompt asks for JSON on this path, not comma-separated integers.
    assert '"scores"' in llm.calls[0][0]


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        "3,1,0",  # one path: CSV is NOT accepted on the JSON-schema path
        '{"nope": [3, 1, 0]}',
        '{"scores": "x"}',
        '{"scores": [3, "x", 0]}',
        '{"scores": [true, 1, 0]}',
        '{"scores": [3, 1]}',  # wrong count
        '{"scores": [3, 1, 9]}',  # out of range
        '{"scores": [3.0, 1, 0]}',  # float, not int
        '{"scores": [3, 1, 0, 2]}',  # more scores than clips (never truncated)
        'here are the scores: {"scores": [3, 1, 0]}',  # prose around object
        '{"scores": [3, 1, 0]} hope this helps',  # trailing prose
        "",
    ],
)
def test_ca3_malformed_json_is_indeterminate(monkeypatch, reply):
    monkeypatch.setattr(settings, "first_person_relevance_model", HAIKU)
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 2)
    assert _relevance_select("q?", _clips(3), _SyncLLM(reply)) == _RELEVANCE_INDETERMINATE


def test_ca3_markdown_fenced_json_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_model", HAIKU)
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 2)
    fenced = '```json\n{"scores": [3, 1, 0]}\n```'
    assert _relevance_select("q?", _clips(3), _SyncLLM(fenced)) == 0


def test_ca3_non_schema_models_keep_comma_parse_and_no_response_format(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_model", "deepseek/deepseek-chat")
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 2)
    llm = _SyncLLM("3,1,0")
    assert _relevance_select("q?", _clips(3), llm) == 0
    assert "response_format" not in llm.kwargs
    assert llm.kwargs.get("temperature") == 0.0
    assert "comma-separated integers" in llm.calls[0][0]


@pytest.mark.asyncio
async def test_ca3_call_api_forwards_response_format(monkeypatch):
    """_call_api whitelist must pass response_format through (was dropped)."""
    from services.openrouter_service import OpenRouterService

    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)
    monkeypatch.setattr(settings, "openrouter_enforce_model_policy", False)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    captured = []

    class MockClient:
        async def post(self, url, json=None, headers=None, **kwargs):
            captured.append(json)
            return _OkResponse({"choices": [{"message": {"content": "ok"}}]})

    async def fake_get_client(self):
        return MockClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)
    service = OpenRouterService()
    rf = {"type": "json_schema", "json_schema": {"name": "relevance_scores"}}
    res = await service.generate(
        system_prompt="s", user_prompt="u", model="x-model", response_format=rf
    )
    assert res == "ok"
    assert captured[-1].get("response_format") == rf


class _OkResponse:
    def __init__(self, data, status_code=200):
        self._data, self.status_code = data, status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


# ---- CA-4: refusal stop_reason plumbing --------------------------------------

REFUSAL_CHOICES = [
    # OpenAI-style: finish_reason=refusal + message.refusal
    [{"message": {"content": None, "refusal": "policy: no"}, "finish_reason": "refusal"}],
    # Filter-style stop reason, empty content
    [{"message": {"content": ""}, "finish_reason": "content_filter"}],
]


@pytest.mark.asyncio
@pytest.mark.parametrize("choices", REFUSAL_CHOICES)
async def test_ca4_call_api_raises_on_refusal_stop_reason(monkeypatch, choices):
    from services.openrouter_service import OpenRouterService

    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)
    monkeypatch.setattr(settings, "openrouter_enforce_model_policy", False)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")

    class MockClient:
        async def post(self, url, json=None, headers=None, **kwargs):
            return _OkResponse({"choices": choices})

    async def fake_get_client(self):
        return MockClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)
    service = OpenRouterService()
    with pytest.raises(ProviderRefusalError):
        await service.generate(system_prompt="s", user_prompt="u", model="x-model")


@pytest.mark.asyncio
async def test_ca4_refusal_does_not_trip_circuit_breaker(monkeypatch):
    from services.openrouter_service import OpenRouterService

    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)
    monkeypatch.setattr(settings, "openrouter_enforce_model_policy", False)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")

    class MockClient:
        async def post(self, url, json=None, headers=None, **kwargs):
            return _OkResponse(
                {
                    "choices": [
                        {
                            "message": {"content": None, "refusal": "policy: no"},
                            "finish_reason": "refusal",
                        }
                    ]
                }
            )

    async def fake_get_client(self):
        return MockClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)
    service = OpenRouterService()
    before = service._circuit._failures
    with pytest.raises(ProviderRefusalError):
        await service.generate(system_prompt="s", user_prompt="u", model="x-model")
    assert service._circuit._failures == before


def test_ca4_refusal_maps_to_indeterminate_with_distinct_log(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(settings, "first_person_relevance_min_score", 2)
    err = ProviderRefusalError("OpenRouter refusal during generate (stop_reason=refusal)")
    with caplog.at_level(logging.INFO):
        got = _relevance_select("q?", _clips(2), _SyncLLM(exc=err))
    assert got == _RELEVANCE_INDETERMINATE
    assert any("refused by provider" in r.message for r in caplog.records)
    # Distinct from the below-min path (which returns None, not -1) and from
    # the generic timeout/error + unparseable lines.
    assert not any("unparseable output" in r.message for r in caplog.records)
    assert not any("timeout/error" in r.message for r in caplog.records)


def test_ca4_below_min_still_returns_none_not_indeterminate(monkeypatch):
    """Indeterminate (-1) vs below-min (None) distinction preserved."""
    monkeypatch.setattr(settings, "first_person_relevance_model", "")
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 3)
    assert _relevance_select("q?", _clips(3), _SyncLLM("1,1,0")) is None


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
