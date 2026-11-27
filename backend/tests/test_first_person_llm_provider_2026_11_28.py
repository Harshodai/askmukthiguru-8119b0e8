"""first_person_llm_provider: which LLM object the first-person path uses (2026-11-28)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from services.first_person_llm_provider import (
    FirstPersonLLMProviderUnavailable,
    resolve_first_person_llm,
)


def _c(**kw):
    return SimpleNamespace(**kw)


def test_default_is_openrouter_and_the_legacy_chain_is_unchanged():
    assert Settings(_env_file=None).first_person_llm_provider == "openrouter"
    or_, nim, oll = object(), object(), object()
    assert resolve_first_person_llm(_c(openrouter=or_, nim=nim, ollama=oll)) is or_
    assert resolve_first_person_llm(_c(openrouter=None, nim=nim, ollama=oll)) is nim
    assert resolve_first_person_llm(_c(ollama=oll)) is oll  # the canonical-LLM alias is live
    assert resolve_first_person_llm(_c()) is None


@pytest.mark.parametrize("choice", ["vllm", "nim"])
def test_selection_returns_that_provider(monkeypatch, choice):
    monkeypatch.setattr(settings, "first_person_llm_provider", choice)
    target = object()
    c = _c(openrouter=object(), ollama=object(), **{choice: target})
    assert resolve_first_person_llm(c) is target


@pytest.mark.parametrize("choice", ["vllm", "nim"])
def test_missing_provider_raises_and_never_falls_back_to_openrouter(monkeypatch, choice):
    monkeypatch.setattr(settings, "first_person_llm_provider", choice)
    c = _c(openrouter=object(), ollama=object(), vllm=None, nim=None)
    with pytest.raises(FirstPersonLLMProviderUnavailable, match=choice):
        resolve_first_person_llm(c)


def test_unknown_provider_name_is_rejected_by_settings():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, first_person_llm_provider="ollama")


def test_bridge_pipeline_gets_the_selected_provider(monkeypatch):
    from app.pipeline.stages import first_person_bridge as bridge

    monkeypatch.setattr(settings, "first_person_llm_provider", "vllm")
    seen = {}
    monkeypatch.setattr("app.api.first_person._pipeline", lambda *a: seen.setdefault("a", a))
    vllm = object()
    bridge._fp_pipeline(_c(openrouter=object(), vllm=vllm, embedding=None))
    assert seen["a"][-1] is vllm
    monkeypatch.setattr(settings, "first_person_llm_provider", "openrouter")
    seen.clear()
    or_ = object()
    bridge._fp_pipeline(_c(openrouter=or_, vllm=vllm, embedding=None))
    assert seen["a"][-1] is or_


def test_hyde_provider_default_unchanged_and_selection_routes(monkeypatch):
    from app.pipeline.stages.first_person_bridge import _hyde_provider

    llm = Mock(spec=["generate_hyde"])
    vllm = Mock(spec=["generate_hyde"])
    c = _c(llm=llm, openrouter=Mock(spec=["generate_hyde"]), vllm=vllm)
    assert _hyde_provider(c) is llm  # today: canonical llm first
    monkeypatch.setattr(settings, "first_person_llm_provider", "vllm")
    assert _hyde_provider(c) is vllm
    with pytest.raises(FirstPersonLLMProviderUnavailable):
        _hyde_provider(_c(llm=llm, vllm=None))


def test_fingerprint_unchanged_on_default_and_rekeyed_otherwise(monkeypatch):
    from services.first_person_pipeline import FirstPersonPipeline

    pipe = FirstPersonPipeline(store=Mock(), serene_mind_engine=Mock())
    assert "llm_provider" not in pipe._serving_policy_components("a", "b")
    base = pipe._serving_policy_fingerprint("a", "b")
    monkeypatch.setattr(settings, "first_person_llm_provider", "vllm")
    assert pipe._serving_policy_components("a", "b")["llm_provider"] == "vllm"
    assert pipe._serving_policy_fingerprint("a", "b") != base
