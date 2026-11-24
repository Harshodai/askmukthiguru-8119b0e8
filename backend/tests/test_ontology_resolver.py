from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
try:
    from services.ontology_resolver import (
        resolve_query_concepts_llm,
        resolve_query_concepts_llm_async,
        _fallback_token_concepts,
    )
except ImportError:
    from backend.services.ontology_resolver import (
        resolve_query_concepts_llm,
        resolve_query_concepts_llm_async,
        _fallback_token_concepts,
    )


@pytest.mark.asyncio
async def test_resolve_query_concepts_llm_async_with_mock_llm():
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value='{"concepts": ["Relationship", "Hurt", "Forgiveness"]}')
    
    concepts = await resolve_query_concepts_llm_async("How do I heal hurt with my spouse?", llm_service=mock_llm)
    assert "Relationship" in concepts
    assert "Hurt" in concepts
    assert "Forgiveness" in concepts


def test_fallback_token_concepts():
    query = "How do I deal with intense anger and grief?"
    tokens = _fallback_token_concepts(query)
    assert "Deal" in tokens or "Anger" in tokens
    assert "Grief" in tokens
    assert "How" not in tokens
    assert "The" not in tokens


def test_resolve_query_concepts_llm_sync_fallback():
    # Calling without LLM service should cleanly fall back to token extraction
    concepts = resolve_query_concepts_llm("How to dissolve suffering in relationships?", llm_service=None)
    assert len(concepts) > 0
    assert any("Suffering" in c or "Relationships" in c for c in concepts)
