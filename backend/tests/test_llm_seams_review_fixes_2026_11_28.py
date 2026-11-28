"""Review fixes for the 2026-11-28 LLM seams.

Providers built only when selected; pins only tighten the global provider policy;
a pinned gate failure is a WARNING (model id and pins, never prompt text); a bridge
with an unavailable provider declines instead of raising.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.container import ServiceContainer
from services import first_person_pipeline as fpp
from services.circuit_breaker import get_circuit_breaker_registry
from services.llm_factory import LLMServiceFactory

# --- container: nim / vllm only when selected --------------------------------------------


def _build(monkeypatch, choice, **cfg):
    created = []

    def _create(name):
        created.append(name)
        return SimpleNamespace(name=name)

    monkeypatch.setattr(LLMServiceFactory, "create", staticmethod(_create))
    monkeypatch.setattr(settings, "first_person_llm_provider", choice)
    for key, value in cfg.items():
        monkeypatch.setattr(settings, key, value)
    holder = SimpleNamespace()
    ServiceContainer._build_first_person_providers(holder)
    return holder, created


def test_defaults_construct_neither_provider_even_with_keys_set(monkeypatch):
    registry = get_circuit_breaker_registry()
    before = registry.get("openrouter")
    holder, created = _build(
        monkeypatch, "openrouter", nim_api_key="nvapi-test", vllm_base_url="http://v/v1"
    )
    assert created == [] and holder.nim is None and holder.vllm is None
    assert registry.get("openrouter") is before  # no NimService -> no re-registered breaker


def test_selected_provider_is_built_alone(monkeypatch):
    holder, created = _build(
        monkeypatch, "nim", nim_api_key="nvapi-test", vllm_base_url="http://v/v1"
    )
    assert created == ["nim"] and holder.nim.name == "nim" and holder.vllm is None
    holder, created = _build(
        monkeypatch, "vllm", nim_api_key="nvapi-test", vllm_base_url="http://v/v1"
    )
    assert created == ["vllm"] and holder.vllm.name == "vllm" and holder.nim is None
    # services/ cannot import rag (import_layer_lint): the container injects the HyDE prompt.
    from rag.prompts import HYDE_PROMPT

    assert holder.vllm.hyde_prompt == HYDE_PROMPT


def test_selected_but_unconfigured_stays_none_so_resolution_raises(monkeypatch):
    holder, created = _build(monkeypatch, "vllm", vllm_base_url="")
    assert created == [] and holder.vllm is None
    holder, created = _build(monkeypatch, "nim", nim_api_key="")
    assert created == [] and holder.nim is None


# --- pins only tighten --------------------------------------------------------------------


def test_defaults_validate():
    Settings(_env_file=None)


def test_pin_cannot_loosen_disabled_provider_fallbacks():
    with pytest.raises(ValidationError, match="loosen"):
        Settings(
            _env_file=None,
            openrouter_allow_provider_fallbacks=False,
            first_person_scorer_allow_fallbacks=True,
        )
    # tightening, or restating the policy, is fine
    Settings(_env_file=None, first_person_scorer_allow_fallbacks=False)
    Settings(
        _env_file=None,
        openrouter_allow_provider_fallbacks=False,
        first_person_scorer_allow_fallbacks=False,
    )


def test_only_must_be_a_subset_of_the_allowlist():
    with pytest.raises(ValidationError, match="not a subset"):
        Settings(
            _env_file=None,
            openrouter_allowed_providers="DeepInfra,Together",
            first_person_scorer_provider_only=["Fireworks"],
        )
    Settings(
        _env_file=None,
        openrouter_allowed_providers="DeepInfra,Together",
        first_person_scorer_provider_only=["deepinfra"],
    )
    # no allowlist: any pin is a tightening
    Settings(_env_file=None, first_person_scorer_provider_only=["Fireworks"])


def test_malformed_pin_value_is_a_boot_time_validation_error():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, first_person_scorer_zdr="maybe")


@pytest.mark.asyncio
async def test_call_api_refuses_a_loosening_pin_even_if_settings_were_bypassed(monkeypatch):
    from tests.test_scorer_provider_pins_2026_11_28 import _body

    monkeypatch.setattr(settings, "openrouter_allow_provider_fallbacks", False)
    with pytest.raises(ValueError, match="loosen"):
        await _body(monkeypatch, provider_overrides={"allow_fallbacks": True})
    monkeypatch.setattr(settings, "openrouter_allow_provider_fallbacks", True)
    monkeypatch.setattr(settings, "openrouter_allowed_providers", "DeepInfra")
    with pytest.raises(ValueError, match="subset"):
        await _body(monkeypatch, provider_overrides={"only": ["Fireworks"]})
    body = await _body(monkeypatch, provider_overrides={"only": ["deepinfra"]})
    assert body["provider"]["only"] == ["deepinfra"]


# --- pinned gate failure is loud ------------------------------------------------------------

QUESTION = "SECRET-QUESTION-TEXT-9921"
CLIPS = [{"verbatim_text": "x " * 30, "video_id": "v", "start_ms": 0, "end_ms": 1000}]


class _Llm:
    async def generate(self, **kwargs):
        return "I'm currently experiencing a temporary connectivity issue"


@pytest.mark.asyncio
async def test_pinned_unusable_reply_logs_a_warning_with_model_and_pins(monkeypatch, caplog):
    monkeypatch.setattr(settings, "first_person_relevance_model", "anthropic/claude-haiku-5.5")
    monkeypatch.setattr(settings, "first_person_scorer_quantizations", ["bf16"])
    with caplog.at_level(logging.INFO, logger=fpp.logger.name):
        verdict = await fpp._relevance_select_scored_async(QUESTION, CLIPS, _Llm())
    assert verdict == fpp._RELEVANCE_INDETERMINATE
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warned
    text = warned[-1].getMessage()
    assert "anthropic/claude-haiku-5.5" in text and '"quantizations": ["bf16"]' in text
    assert QUESTION not in caplog.text


@pytest.mark.asyncio
async def test_pinned_provider_exception_logs_a_warning(monkeypatch, caplog):
    class _Boom:
        async def generate(self, **kwargs):
            raise httpx.ConnectError("no endpoints match")

    monkeypatch.setattr(settings, "first_person_scorer_zdr", True)
    with caplog.at_level(logging.INFO, logger=fpp.logger.name):
        await fpp._relevance_select_scored_async(QUESTION, CLIPS, _Boom())
    assert any(
        r.levelno == logging.WARNING and "pins active" in r.getMessage() for r in caplog.records
    )


@pytest.mark.asyncio
async def test_unpinned_failure_stays_at_info(caplog):
    with caplog.at_level(logging.INFO, logger=fpp.logger.name):
        await fpp._relevance_select_scored_async(QUESTION, CLIPS, _Llm())
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [r for r in caplog.records if "Relevance check" in r.getMessage()]


# --- bridge: an unavailable provider declines, it never raises --------------------------------


@pytest.mark.asyncio
async def test_bridge_declines_when_the_selected_provider_is_unavailable(monkeypatch):
    from app.pipeline.stages import first_person_bridge as bridge

    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_llm_provider", "vllm")

    async def _bridge(self, ctx):
        bridge._fp_pipeline(SimpleNamespace(openrouter=object(), vllm=None))

    stage = bridge.FirstPersonBridgeStage()
    monkeypatch.setattr(bridge.FirstPersonBridgeStage, "_bridge", _bridge)
    declined = AsyncMock(return_value="declined")
    monkeypatch.setattr(bridge.FirstPersonBridgeStage, "_decline", declined)
    assert await stage.run(SimpleNamespace()) == "declined"
    declined.assert_awaited_once()
    assert declined.await_args.args[1] == "error"
