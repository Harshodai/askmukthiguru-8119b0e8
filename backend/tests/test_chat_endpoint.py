import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app, get_current_user_from_supabase
from app.dependencies import get_container, ServiceContainer

client = TestClient(app)

def mock_get_current_user():
    return {"id": "test-user-id", "email": "test@example.com"}

def mock_get_container():
    mock_container = MagicMock(spec=ServiceContainer)
    # Mock guardrails
    mock_container.guardrails = AsyncMock()
    mock_container.guardrails.check_input.return_value = {"blocked": False, "reason": None}
    mock_container.guardrails.check_output.return_value = {"blocked": False, "reason": None}
    mock_container.guardrails.is_available = True
    mock_container.guardrails.provider_name = "mock_provider"
    
    # Mock serene_mind
    mock_assessment = MagicMock()
    mock_assessment.level.value = 1
    mock_container.serene_mind = AsyncMock()
    mock_container.serene_mind.analyze_with_history.return_value = mock_assessment
    
    # Mock RAG pipeline
    mock_container.rag_graph = AsyncMock()
    mock_container.rag_graph.ainvoke.return_value = {
        "final_answer": "This is a mocked response",
        "meditation_step": 0,
        "citations": [],
        "intent": "general"
    }
    
    # Mock semantic cache
    mock_container.semantic_cache = MagicMock()
    mock_container.semantic_cache.get.return_value = None
    mock_container.semantic_cache.is_available = True
    
    # Mock Ollama
    mock_container.ollama = AsyncMock()
    mock_container.ollama.health_check.return_value = True
    
    # Mock Qdrant and OCR
    mock_container.qdrant = MagicMock()
    mock_container.qdrant.health_check = lambda: True
    mock_container.qdrant.count = lambda: 100
    mock_container.ocr = MagicMock()
    mock_container.ocr.health_check = lambda: True
    
    # Mock language router
    from services.language_router import LanguageDetection, LanguageCode
    mock_lang = LanguageDetection(
        primary=LanguageCode.EN,
        confidence=0.9,
        is_codemixed=False,
        scripts_detected=["Latin"],
        recommendation="sarvam-30b"
    )
    mock_container.language_router = MagicMock()
    mock_container.language_router.detect.return_value = mock_lang
    
    # Mock profile service
    mock_container.profile_service = AsyncMock()
    mock_container.profile_service.get_profile.return_value = {}
    mock_container.user_profile = {}

    # Mock health_status
    mock_container.health_status = AsyncMock()
    mock_container.health_status.return_value = {
        "qdrant": True,
        "ollama": True,
        "embedding": True,
        "ocr": True,
        "guardrails": True,
        "semantic_cache": True,
        "total_chunks": 100
    }

    return mock_container

app.dependency_overrides[get_current_user_from_supabase] = mock_get_current_user
app.dependency_overrides[get_container] = mock_get_container

from unittest.mock import patch

@patch('app.main.log_query_trace')
def test_chat_endpoint_success(mock_log_query_trace):
    """Verify that the chat endpoint correctly returns a ChatResponse."""
    payload = {
        "user_message": "Hello Mukthi Guru",
        "session_id": "test-session",
        "messages": []
    }
    response = client.post("/api/chat", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert data["response"] == "This is a mocked response"
    assert data.get("blocked") is not True

@patch('app.main.log_query_trace')
def test_chat_endpoint_empty_message(mock_log_query_trace):
    """Verify that an empty message returns a 400 error."""
    payload = {
        "user_message": "   ",
        "session_id": "test-session",
        "messages": []
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 400
