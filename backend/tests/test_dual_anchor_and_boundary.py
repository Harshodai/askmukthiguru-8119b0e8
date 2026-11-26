"""Unit tests for dual-anchor concept alignment and relationship safety boundary de-escalation."""

import pytest

from app.config import settings
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.guardrail_stage import OutputGuardrailStage
from guardrails.lightweight_handler import (
    RELATIONSHIP_SAFETY_BOUNDARY,
    needs_relationship_safety_boundary,
)
from services.first_person_context_store import _clean_concept_ids
from services.first_person_graph_expansion import expand_query_concepts


def test_fallback_enabled_default_is_false():
    """MANDATORY OWNER DIRECTIVE: fallback must remain false to prevent ungrounded stitching."""
    assert getattr(settings, "first_person_llm_fallback_enabled", None) is False


def test_relationship_boundary_enabled_default_is_false():
    """Owner directive: unsolicited domestic violence banner is suppressed by default."""
    assert getattr(settings, "relationship_safety_boundary_enabled", None) is False


@pytest.mark.parametrize(
    "query",
    [
        "How do I heal hurt in my relationships?",
        "Should I forgive my spouse after an argument?",
        "My partner and I have conflict, how do we heal?",
    ],
)
def test_relationship_repair_queries_detected_for_intent(query):
    assert needs_relationship_safety_boundary(query) is True


from unittest.mock import AsyncMock, MagicMock


def _make_ctx(question: str, answer: str) -> PipelineContext:
    container = MagicMock()
    container.guardrails.check_output = AsyncMock(
        return_value={"blocked": False, "reason": "", "moderated_response": ""}
    )
    container.translation.translate_text = AsyncMock(return_value="[hi] boundary")
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=question,
        final_answer=answer,
        state={"user_msg_en": question},
    )
    return ctx


@pytest.mark.asyncio
async def test_guardrail_stage_omits_boundary_when_disabled():
    ctx = _make_ctx(
        "How do I heal hurt in my relationships?",
        "Forgiving someone and letting go of your hurt is necessary for mental peace.",
    )
    await OutputGuardrailStage().run(ctx)
    assert ctx.final_answer == "Forgiving someone and letting go of your hurt is necessary for mental peace."
    assert RELATIONSHIP_SAFETY_BOUNDARY not in ctx.final_answer


@pytest.mark.asyncio
async def test_guardrail_stage_appends_boundary_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(settings, "relationship_safety_boundary_enabled", True)
    ctx = _make_ctx(
        "How do I heal hurt in my relationships?",
        "Forgiving someone and letting go of your hurt is necessary for mental peace.",
    )
    await OutputGuardrailStage().run(ctx)
    assert ctx.final_answer.startswith("Forgiving someone and letting go of your hurt is necessary for mental peace.")
    assert ctx.final_answer.rstrip().endswith(RELATIONSHIP_SAFETY_BOUNDARY)


def test_clean_concept_ids_expands_case_and_tokens():
    raw = ["relationship healing", "Hurt", "meditation"]
    cleaned = _clean_concept_ids(raw)
    # Check lowercase for topic_ids match
    assert "relationship" in cleaned
    assert "healing" in cleaned
    assert "hurt" in cleaned
    assert "meditation" in cleaned
    # Check capitalized for entity_ids match
    assert "Relationship" in cleaned
    assert "Hurt" in cleaned
    assert "Meditation" in cleaned


def test_expand_query_concepts_includes_relational_seeds(monkeypatch):
    from types import SimpleNamespace

    from rag.kg_expansion import resolve_concepts_in_query

    query = "How do I heal hurt in my relationships?"
    seeds = resolve_concepts_in_query(query)
    assert any("relationship" in c.lower() for c in seeds)
    assert any("hurt" in c.lower() for c in seeds)

    # With graph driver present, expand_query_concepts forwards normalized neighbors fail-open.
    monkeypatch.setattr("app.dependencies.get_container", lambda: SimpleNamespace(neo4j_driver=object()))

    async def _mock_expand(q, driver, **kwargs):
        return [*resolve_concepts_in_query(q), "Relationship Healing"]

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _mock_expand)
    concepts = expand_query_concepts(query)
    assert any("relationship" in c.lower() for c in concepts)
    assert any("hurt" in c.lower() for c in concepts)
