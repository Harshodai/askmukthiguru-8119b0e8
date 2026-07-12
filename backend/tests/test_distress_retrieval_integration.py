import pytest
from unittest.mock import AsyncMock, patch
from rag.states import GraphState
from rag.nodes.intent import handle_distress

@pytest.mark.asyncio
async def test_handle_distress_performs_inline_retrieval_when_empty():
    mock_retrieve = AsyncMock(return_value={"relevant_docs": [{"title": "Teachings", "content": "Be serene"}]})
    mock_ollama = AsyncMock()
    mock_ollama.generate.return_value = "Compassionate response"
    state = GraphState(question="I feel so anxious", chat_history=[], relevant_docs=[])
    
    with patch("rag.nodes.retrieval.retrieve_documents", mock_retrieve), \
         patch("rag.nodes.intent._services._ollama", mock_ollama), \
         patch("rag.nodes.intent._services._serene_mind", None):
        result = await handle_distress(state, config={})
        mock_retrieve.assert_called_once()
        assert mock_ollama.generate.call_count == 1
