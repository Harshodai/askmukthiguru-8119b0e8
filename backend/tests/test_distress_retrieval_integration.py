from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.nodes.intent import handle_distress
from rag.states import GraphState
from services.serene_mind_engine import DistressAssessment, DistressLevel


@pytest.mark.asyncio
async def test_handle_distress_safe_template_without_llm_or_retrieval():
    """Verify handle_distress delivers safe template without LLM generation or inline retrieval."""
    mock_ollama = AsyncMock()
    mock_serene = MagicMock()
    mock_serene.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    )
    mock_serene.get_response = MagicMock(return_value="Safe Serene Mind practice.")

    state = GraphState(question="I feel so anxious", chat_history=[], relevant_docs=[])

    with (
        patch("rag.nodes.intent._services._ollama", mock_ollama),
        patch("rag.nodes.intent._services._serene_mind", mock_serene),
    ):
        result = await handle_distress(state, config={})
        assert mock_ollama.generate.call_count == 0
        assert "Safe Serene Mind practice" in result["final_answer"]
        assert result["citations"] == []
        assert result["intent"] == "DISTRESS"
        assert result["route_decision"] == "distress"
