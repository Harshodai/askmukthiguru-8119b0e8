"""Opt-in provider pins for first-person gate calls (2026-11-28).

Unset: no new keyword, request body byte-identical, cache fingerprint unchanged.
Set: the pinned OpenRouter provider fields reach the request.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings, settings
from services import first_person_pipeline as fpp
from services.openrouter_service import OpenRouterService


def test_defaults_are_unset():
    s = Settings(_env_file=None)
    assert s.first_person_scorer_provider_only == []
    assert s.first_person_scorer_quantizations == []
    assert s.first_person_scorer_require_parameters is False
    assert s.first_person_scorer_zdr is False
    assert s.first_person_scorer_allow_fallbacks is None


def test_env_parsing_accepts_csv_json_and_empty(monkeypatch):
    monkeypatch.setenv("FIRST_PERSON_SCORER_PROVIDER_ONLY", "DeepInfra, Together")
    monkeypatch.setenv("FIRST_PERSON_SCORER_QUANTIZATIONS", '["bf16"]')
    monkeypatch.setenv("FIRST_PERSON_SCORER_ALLOW_FALLBACKS", "")
    s = Settings(_env_file=None)
    assert s.first_person_scorer_provider_only == ["DeepInfra", "Together"]
    assert s.first_person_scorer_quantizations == ["bf16"]
    assert s.first_person_scorer_allow_fallbacks is None
    monkeypatch.setenv("FIRST_PERSON_SCORER_ALLOW_FALLBACKS", "false")
    assert Settings(_env_file=None).first_person_scorer_allow_fallbacks is False


def test_unset_helper_returns_empty_dict():
    assert fpp.scorer_provider_kwargs() == {}


def test_set_helper_returns_only_the_set_fields(monkeypatch):
    monkeypatch.setattr(settings, "first_person_scorer_quantizations", ["bf16", "fp8"])
    monkeypatch.setattr(settings, "first_person_scorer_zdr", True)
    monkeypatch.setattr(settings, "first_person_scorer_allow_fallbacks", False)
    assert fpp.scorer_provider_kwargs() == {
        "provider_overrides": {
            "quantizations": ["bf16", "fp8"],
            "zdr": True,
            "allow_fallbacks": False,
        }
    }


# --- request bodies -----------------------------------------------------------------------


class _Capture:
    def __init__(self):
        self.bodies: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0001},
            },
        )


async def _body(monkeypatch, **kwargs) -> dict:
    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)
    OpenRouterService.reset_shared_rate_limiter()
    svc = OpenRouterService()
    cap = _Capture()
    svc._http_client = httpx.AsyncClient(
        base_url="https://example.invalid/v1", transport=httpx.MockTransport(cap.handler)
    )
    import asyncio

    svc._http_client_loop = asyncio.get_running_loop()
    await svc.generate("sys", "user", model=svc._gen_model, **kwargs)
    assert len(cap.bodies) == 1
    return cap.bodies[0]


@pytest.mark.asyncio
async def test_request_body_identical_with_pins_unset(monkeypatch):
    plain = await _body(monkeypatch)
    helper = await _body(monkeypatch, **fpp.scorer_provider_kwargs())
    assert plain == helper
    assert set(plain["provider"]) <= {
        "allow_fallbacks",
        "data_collection",
        "order",
        "sort",
        "preferred_max_latency",
        "preferred_min_throughput",
    }


@pytest.mark.asyncio
async def test_pins_reach_the_provider_object_and_keep_data_collection(monkeypatch):
    base = await _body(monkeypatch)
    monkeypatch.setattr(settings, "first_person_scorer_provider_only", ["DeepInfra"])
    monkeypatch.setattr(settings, "first_person_scorer_quantizations", ["bf16"])
    monkeypatch.setattr(settings, "first_person_scorer_require_parameters", True)
    monkeypatch.setattr(settings, "first_person_scorer_zdr", True)
    monkeypatch.setattr(settings, "first_person_scorer_allow_fallbacks", False)
    pinned = await _body(monkeypatch, **fpp.scorer_provider_kwargs())
    prov = pinned["provider"]
    assert prov["only"] == ["DeepInfra"]
    assert prov["quantizations"] == ["bf16"]
    assert prov["require_parameters"] is True
    assert prov["zdr"] is True
    assert prov["allow_fallbacks"] is False
    assert prov["data_collection"] == base["provider"]["data_collection"] == "deny"
    assert {k: v for k, v in pinned.items() if k != "provider"} == {
        k: v for k, v in base.items() if k != "provider"
    }


@pytest.mark.asyncio
async def test_pin_cannot_override_data_collection(monkeypatch):
    with pytest.raises(ValueError, match="unsupported provider_overrides"):
        await _body(monkeypatch, provider_overrides={"data_collection": "allow"})


# --- every gate call carries the pins; the fingerprint only moves when pinned ---------------


class _Llm:
    def __init__(self, reply="YES"):
        self.calls: list[dict] = []
        self.reply = reply

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply

    _generate_fast = generate


@pytest.mark.answerability_real
@pytest.mark.asyncio
async def test_answerability_call_carries_pins_only_when_set(monkeypatch):
    llm = _Llm()
    await fpp._async_answerability_check("q", llm)
    assert "provider_overrides" not in llm.calls[-1]
    monkeypatch.setattr(settings, "first_person_scorer_zdr", True)
    await fpp._async_answerability_check("q", llm)
    assert llm.calls[-1]["provider_overrides"] == {"zdr": True}


@pytest.mark.asyncio
async def test_relevance_scorer_and_joint_sufficiency_carry_pins(monkeypatch):
    monkeypatch.setattr(settings, "first_person_scorer_quantizations", ["bf16"])
    llm = _Llm(reply="3")
    clips = [{"verbatim_text": "x " * 30, "video_id": "v", "start_ms": 0, "end_ms": 1000}]
    await fpp._relevance_select_scored_async("q", clips, llm)
    assert llm.calls and llm.calls[-1]["provider_overrides"] == {"quantizations": ["bf16"]}
    llm2 = _Llm(reply="SUFFICIENT")
    await fpp._joint_sufficiency_verdict("q", "", "clip", llm2, [])
    assert llm2.calls[-1]["provider_overrides"] == {"quantizations": ["bf16"]}


@pytest.mark.asyncio
async def test_judge_calls_carry_pins_but_distress_kwargs_do_not(monkeypatch):
    from services import first_person_judge as judge

    monkeypatch.setattr(settings, "first_person_scorer_zdr", True)
    assert "provider_overrides" not in judge.judge_call_kwargs("anthropic/claude-haiku-5.5")
    assert judge._gate_pins() == {"provider_overrides": {"zdr": True}}
    llm = _Llm(reply='{"best": null}')
    await judge.comparative_select_async(
        "q", [{"verbatim_text": "a b c"}, {"verbatim_text": "d e f"}], llm, timeout_s=5
    )
    assert llm.calls[-1]["provider_overrides"] == {"zdr": True}


def test_fingerprint_unchanged_when_unset_and_changed_when_pinned(monkeypatch):
    from unittest.mock import Mock

    pipe = fpp.FirstPersonPipeline(store=Mock(), serene_mind_engine=Mock())
    unset_components = pipe._serving_policy_components("a", "b")
    assert "scorer_routing" not in unset_components  # key set identical to before this change
    unset = pipe._serving_policy_fingerprint("a", "b")
    monkeypatch.setattr(settings, "first_person_scorer_zdr", True)
    assert pipe._serving_policy_components("a", "b")["scorer_routing"] == '{"zdr": true}'
    assert pipe._serving_policy_fingerprint("a", "b") != unset
    monkeypatch.setattr(settings, "first_person_scorer_zdr", False)
    assert pipe._serving_policy_fingerprint("a", "b") == unset
