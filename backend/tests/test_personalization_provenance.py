import asyncio
from types import SimpleNamespace

from app.pipeline.result import PersonalizationProvenance, PipelineResult
from app.schemas import ChatResponse
from services.second_brain.context_adapter import (
    build_private_context_links,
    format_private_context_links,
)


def test_private_context_adapter_reports_graph_matches_for_the_exact_query() -> None:
    item = SimpleNamespace(
        id="memory-1",
        user_id="11111111-1111-1111-1111-111111111111",
        kind="reflection",
        text="I keep returning to stillness and the Beautiful State.",
        confidence=0.9,
    )
    links = build_private_context_links(
        "11111111-1111-1111-1111-111111111111",
        "How can I return to stillness?",
        [item],
    )
    assert links
    assert links[0].entity_ids
    rendered = format_private_context_links(links)
    assert "Personal context graph matches: 1" in rendered
    assert "memory-1" in rendered


def test_public_chat_contract_carries_personalization_without_private_text() -> None:
    result = PipelineResult(
        final_answer="Use the practice you saved earlier.",
        personalization_provenance=PersonalizationProvenance(
            used=True,
            profile_preferences=True,
            personal_memory=True,
            private_graph_links=2,
        ),
    )
    payload = result.to_chat_response()
    assert payload["personalization_provenance"]["private_graph_links"] == 2
    assert "saved earlier" not in str(payload["personalization_provenance"])
    parsed = ChatResponse(**payload)
    assert parsed.personalization_provenance["personal_memory"] is True
