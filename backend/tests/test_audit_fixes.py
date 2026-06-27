from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from app.config import settings
from rag.states import GraphState
from rag.nodes.verification import reflect_on_answer, verify_answer
from rag.nodes.generation import format_final_answer
from rag.nodes.short_circuit import rewrite_query

@pytest.mark.asyncio
async def test_reflect_on_answer_caches_lettuce_detect(monkeypatch):
    # Mock LettuceDetect
    mock_ld = MagicMock()
    mock_ld.score_faithfulness = MagicMock(return_value={"score": 0.9, "sentences": []})
    
    with patch("rag.nodes._services._lettuce_detect", mock_ld):
        state = {
            "query_tier": "standard",
            "answer": "This is a long spiritual answer that requires reflection and verification and should not be bypassed. " * 3, # Length > 150
            "relevant_docs": [{"text": "doc text long enough to pass verification context check. " * 5}], # Length > 200
            "question": "test question",
            "rewritten_query": None,
        }
        
        # reflect_on_answer should compute and return lettuce_detect_result
        res_reflect = await reflect_on_answer(state)
        assert "lettuce_detect_result" in res_reflect
        assert res_reflect["lettuce_detect_result"]["score"] == 0.9
        
        # Populate result into state
        state["lettuce_detect_result"] = res_reflect["lettuce_detect_result"]
        
        # Mock verify_answer's score_faithfulness to verify it is NOT called
        mock_ld.score_faithfulness.reset_mock()
        
        res_verify = await verify_answer(state)
        assert res_verify["is_faithful"] is True
        mock_ld.score_faithfulness.assert_not_called()

@pytest.mark.asyncio
async def test_format_final_answer_gating_floor(monkeypatch):
    state = {
        "is_faithful": True,
        "verification": {"passed": True},
        "confidence_score": 3.0,  # Below default gating floor of 4.0
        "answer": "Grounded answer",
        "citations": [],
        "intent": "QUERY",
        "retry_count": 2,  # Prevent retrying, go straight to fallback
    }
    
    # Should fall back due to confidence score below settings.confidence_gating_floor (4.0)
    res = await format_final_answer(state)
    assert "final_answer" in res
    assert "I don't have that specific teaching" in res["final_answer"]

@pytest.mark.asyncio
async def test_rewrite_query_validation(monkeypatch):
    mock_ollama = MagicMock()
    # Mock rewrite_query to return an invalid/empty result
    mock_ollama.rewrite_query = AsyncMock(return_value="")
    
    with patch("rag.nodes._services._ollama", mock_ollama):
        state = {
            "rewrite_count": 0,
            "question": "Original question",
            "rewritten_query": None,
            "grading_reasons": [],
        }
        
        # Should fallback to original query if rewrite is empty
        res = await rewrite_query(state)
        assert res["rewritten_query"] == "Original question"
        assert res["rewrite_count"] == 1
