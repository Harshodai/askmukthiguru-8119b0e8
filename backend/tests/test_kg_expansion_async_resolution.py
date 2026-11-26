from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import rag.kg_expansion as kg_expansion
from app.config import settings


class _Session:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def run(self, _query: str, *, concept: str, **_kwargs):
        self.calls.append(concept)
        return [{"neighbor": f"{concept} Related"}]


class _Driver:
    def __init__(self) -> None:
        self.session_instance = _Session()

    def session(self):
        return self.session_instance


@pytest.mark.asyncio
async def test_graph_expansion_awaits_dynamic_resolver_inside_async_path(monkeypatch) -> None:
    monkeypatch.setattr(settings, "kg_dynamic_concept_resolution_enabled", True)
    monkeypatch.setattr(kg_expansion, "_find_concepts_in_query", lambda _query: [])
    resolver = AsyncMock(return_value=["Emotional Hurt", "Forgiveness"])
    monkeypatch.setattr("services.ontology_resolver.resolve_query_concepts_llm_async", resolver)
    driver = _Driver()

    neighbors = await kg_expansion.expand_query_via_kg(
        "How do I understand emotional distance?",
        driver,
        max_hops=1,
        max_entities=4,
        timeout=1.0,
    )

    resolver.assert_awaited_once()
    assert resolver.await_args.kwargs["timeout_s"] <= 0.75
    assert driver.session_instance.calls == ["Emotional Hurt", "Forgiveness"]
    assert neighbors == ["Emotional Hurt Related", "Forgiveness Related"]


@pytest.mark.asyncio
async def test_dynamic_concept_resolution_is_off_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "kg_dynamic_concept_resolution_enabled", False)
    resolver = AsyncMock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr("services.ontology_resolver.resolve_query_concepts_llm_async", resolver)
    monkeypatch.setattr(kg_expansion, "_find_concepts_in_query", lambda _query: ["Meditation"])

    concepts = await kg_expansion.resolve_concepts_in_query_async("What is happening?")

    resolver.assert_not_awaited()
    assert concepts == ["Meditation"]


@pytest.mark.asyncio
async def test_throwaway_loop_caller_can_forbid_dynamic_provider_resolution(monkeypatch) -> None:
    monkeypatch.setattr(settings, "kg_dynamic_concept_resolution_enabled", True)
    monkeypatch.setattr(kg_expansion, "_find_concepts_in_query", lambda _query: ["Meditation"])
    resolver = AsyncMock(side_effect=AssertionError("must stay on the request loop"))
    monkeypatch.setattr("services.ontology_resolver.resolve_query_concepts_llm_async", resolver)

    concepts = await kg_expansion.resolve_concepts_in_query_async(
        "How do I meditate?",
        allow_dynamic=False,
    )

    resolver.assert_not_awaited()
    assert concepts == ["Meditation"]


@pytest.mark.asyncio
async def test_async_dynamic_resolution_failure_preserves_deterministic_concepts(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "kg_dynamic_concept_resolution_enabled", True)
    monkeypatch.setattr(kg_expansion, "_find_concepts_in_query", lambda _query: ["Beautiful State"])

    async def _fail(*_args, **_kwargs):
        raise TimeoutError("provider timeout")

    monkeypatch.setattr("services.ontology_resolver.resolve_query_concepts_llm_async", _fail)
    concepts = await kg_expansion.resolve_concepts_in_query_async(
        "How do I move beyond fear?", timeout_s=0.1
    )

    assert concepts == ["Beautiful State"]
