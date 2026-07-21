from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_container
from app.main import app, get_current_user_from_supabase

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_coalescer():
    async def dummy_get_or_run(key, callback):
        return await callback()

    mock_coalescer_obj = MagicMock()
    mock_coalescer_obj.get_or_run = AsyncMock(side_effect=dummy_get_or_run)

    with patch("app.main.coalescer.get_or_run", side_effect=dummy_get_or_run), \
         patch("app.coalescer.build_coalescer", return_value=mock_coalescer_obj):
        yield


def mock_get_current_user():
    return {"id": "test-user-id", "email": "test@example.com"}


def mock_get_container():
    mock_container = MagicMock()
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
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "final_answer": "This is a mocked response",
        "meditation_step": 0,
        "citations": [],
        "intent": "general",
    }
    mock_container.rag_graph = mock_graph
    mock_container.standard_graph = mock_graph
    mock_container.fast_graph = mock_graph
    mock_container.deep_graph = mock_graph

    # Mock semantic cache
    mock_container.exact_cache = MagicMock()
    mock_container.exact_cache.get.return_value = None
    mock_container.semantic_cache = MagicMock()
    mock_container.semantic_cache.get.return_value = None
    mock_container.semantic_cache.is_available = True

    from app.coalescer import _InMemoryCoalescer
    mock_container.coalescer = _InMemoryCoalescer()

    # Mock Ollama
    mock_container.ollama = AsyncMock()
    mock_container.ollama.health_check.return_value = True
    mock_container.ollama._circuit = MagicMock()
    mock_container.ollama._circuit.can_execute.return_value = True

    # Mock _service for circuit checking
    mock_service = MagicMock()
    mock_service._circuit = MagicMock()
    mock_service._circuit.can_execute.return_value = True
    mock_container.ollama._service = mock_service

    async def dummy_translate(text, src, tgt):
        return f"translated_{text}"

    mock_container.ollama.translate_text = dummy_translate

    # Mock Translation
    mock_container.translation = AsyncMock()
    async def dummy_translate_text(*, text: str, source_lang: str, target_lang: str, **kwargs):
        return f"translated_{text}"
    mock_container.translation.translate_text = dummy_translate_text


    # Mock Qdrant and OCR
    mock_container.qdrant = MagicMock()
    mock_container.qdrant.health_check = lambda: True
    mock_container.qdrant.count = lambda: 100
    mock_container.ocr = MagicMock()
    mock_container.ocr.health_check = lambda: True

    # Mock language router
    from services.language_router import LanguageCode, LanguageDetection

    mock_lang = LanguageDetection(
        primary=LanguageCode.EN,
        confidence=0.9,
        is_codemixed=False,
        scripts_detected=["Latin"],
        recommendation="sarvam-30b",
    )
    mock_container.language_router = MagicMock()
    mock_container.language_router.detect.return_value = mock_lang

    # Mock profile service
    mock_container.profile_service = AsyncMock()
    mock_container.profile_service.get_profile.return_value = {}
    mock_container.user_profile = None  # None to avoid triggering ConversationMemory save attempt if not needed, or we can leave as is

    # Mock health_status
    mock_container.health_status = AsyncMock()
    mock_container.health_status.return_value = {
        "qdrant": True,
        "ollama": True,
        "embedding": True,
        "ocr": True,
        "guardrails": True,
        "semantic_cache": True,
        "total_chunks": 100,
    }

    # Mock Supabase client validating table, columns, and .eq() arguments
    def mock_table(table_name):
        query_mock = MagicMock()
        if table_name == "conversations":
            def select_fn(cols):
                sel_mock = MagicMock()
                def eq_fn(field, val):
                    eq_mock = MagicMock()
                    if field == "id" and val == "test-session":
                        eq_mock.execute.return_value.data = [{"user_id": "test-user-id"}]
                    else:
                        eq_mock.execute.return_value.data = []
                    return eq_mock
                sel_mock.eq = eq_fn
                return sel_mock
            query_mock.select = select_fn
        elif table_name == "chat_messages":
            def select_fn(*args, **kwargs):
                sel_mock = MagicMock()
                def eq_fn(field, val):
                    eq_mock = MagicMock()
                    def order_fn(sort_col, desc=False):
                        ord_mock = MagicMock()
                        ord_mock.execute.return_value.data = []
                        return ord_mock
                    eq_mock.order = order_fn
                    return eq_mock
                sel_mock.eq = eq_fn
                return sel_mock
            query_mock.select = select_fn
        return query_mock

    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = mock_table
    mock_container.supabase_client = mock_supabase
    mock_container.job_queue = None
    return mock_container






app.dependency_overrides[get_current_user_from_supabase] = mock_get_current_user
app.dependency_overrides[get_container] = mock_get_container


@patch("app.main.telemetry_sink.log_query_trace")
def test_chat_endpoint_success(mock_log_query_trace):
    """Verify that the chat endpoint correctly returns a ChatResponse."""
    payload = {"user_message": "Hello Mukthi Guru", "session_id": "test-session", "messages": []}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert data["response"] == "This is a mocked response"
    assert data.get("blocked") is not True


@patch("app.main.telemetry_sink.log_query_trace")
def test_chat_endpoint_empty_message(mock_log_query_trace):
    """Verify that an empty message returns a 400 error."""
    payload = {"user_message": "   ", "session_id": "test-session", "messages": []}
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 400


@patch("app.main.telemetry_sink.log_query_trace")
def test_chat_endpoint_indic_translation(mock_log_query_trace):
    """Verify that the chat endpoint translates Indic languages to and from English."""
    payload = {
        "user_message": "नमस्ते",  # Namaste in Hindi
        "session_id": "test-session",
        "messages": [],
        "language": "hi",
    }
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    # The pipeline should return the translated final answer
    assert data["response"] == "translated_This is a mocked response"


@patch("app.main.telemetry_sink.log_query_trace")
def test_chat_endpoint_cache_hit_with_guardrails(mock_log_query_trace):
    """Verify that cached responses are checked by output guardrails before returning."""
    # Setup mock container with a cached response that would be blocked by guardrails
    mock_container = MagicMock()
    from app.coalescer import _InMemoryCoalescer
    mock_container.coalescer = _InMemoryCoalescer()
    mock_container.guardrails = AsyncMock()
    mock_container.guardrails.check_input.return_value = {"blocked": False, "reason": None}
    # Mock guardrails output check to block the response
    mock_container.guardrails.check_output.return_value = {
        "blocked": True,
        "reason": "Output moderated: medical_advice",
        "moderated_response": "I want to keep our conversation focused on spiritual wisdom. Let me share the teachings instead. 🙏",
    }
    mock_container.guardrails.is_available = True
    mock_container.guardrails.provider_name = "mock_provider"

    # Mock other dependencies
    mock_container.serene_mind = AsyncMock()
    mock_assessment = MagicMock()
    mock_assessment.level.value = 1
    mock_container.serene_mind.analyze_with_history.return_value = mock_assessment

    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "final_answer": "This is a mocked response",
        "meditation_step": 0,
        "citations": [],
        "intent": "general",
    }
    mock_container.rag_graph = mock_graph
    mock_container.standard_graph = mock_graph
    mock_container.fast_graph = mock_graph
    mock_container.deep_graph = mock_graph

    # Mock semantic cache to return a cached response
    mock_container.exact_cache = MagicMock()
    mock_container.exact_cache.get.return_value = None
    mock_container.semantic_cache = MagicMock()
    mock_container.semantic_cache.get.return_value = {
        "response": "Take 2 aspirin and call me in the morning.",  # This would be blocked by medical advice guardrails
        "intent": "general",
        "meditation_step": 0,
        "citations": [],
    }
    mock_container.semantic_cache.is_available = True

    mock_container.ollama = AsyncMock()
    mock_container.ollama.health_check.return_value = True
    mock_container.ollama._circuit = MagicMock()
    mock_container.ollama._circuit.can_execute.return_value = True

    # Mock _service for circuit checking
    mock_service = MagicMock()
    mock_service._circuit = MagicMock()
    mock_service._circuit.can_execute.return_value = True
    mock_container.ollama._service = mock_service

    async def dummy_translate(text, src, tgt):
        return f"translated_{text}"

    mock_container.ollama.translate_text = dummy_translate

    mock_container.translation = AsyncMock()
    async def dummy_translate_text(*, text: str, source_lang: str, target_lang: str, **kwargs):
        return f"translated_{text}"
    mock_container.translation.translate_text = dummy_translate_text


    mock_container.qdrant = MagicMock()
    mock_container.qdrant.health_check = lambda: True
    mock_container.qdrant.count = lambda: 100
    mock_container.ocr = MagicMock()
    mock_container.ocr.health_check = lambda: True

    from services.language_router import LanguageCode, LanguageDetection

    mock_lang = LanguageDetection(
        primary=LanguageCode.EN,
        confidence=0.9,
        is_codemixed=False,
        scripts_detected=["Latin"],
        recommendation="sarvam-30b",
    )
    mock_container.language_router = MagicMock()
    mock_container.language_router.detect.return_value = mock_lang

    mock_container.user_profile = None
    mock_container.health_status = AsyncMock()
    mock_container.health_status.return_value = {
        "qdrant": True,
        "ollama": True,
        "embedding": True,
        "ocr": True,
        "guardrails": True,
        "semantic_cache": True,
        "total_chunks": 100,
    }
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().execute.return_value.data = [{"user_id": "test-user-id"}]
    mock_supabase.table().select().eq().order().execute.return_value.data = []
    mock_container.supabase_client = mock_supabase
    mock_container.job_queue = None


    # Temporarily override the container dependency
    app.dependency_overrides[get_container] = lambda: mock_container

    payload = {"user_message": "Hello Mukthi Guru", "session_id": "test-session", "messages": []}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    # The response should be the moderated version from guardrails, not the original cached response
    assert (
        data["response"]
        == "I want to keep our conversation focused on spiritual wisdom. Let me share the teachings instead. 🙏"
    )
    assert (
        data.get("blocked") is not True
    )  # blocked field indicates if the endpoint blocked input, not output moderation

    # Restore original mock
    app.dependency_overrides[get_container] = mock_get_container


def test_chat_endpoint_unauthorized_conversation_owner():
    """Verify that accessing another user's conversation returns 403 Forbidden."""
    def unauthorized_table(table_name):
        query_mock = MagicMock()
        if table_name == "conversations":
            sel_mock = MagicMock()
            def eq_fn(field, val):
                eq_mock = MagicMock()
                eq_mock.execute.return_value.data = [{"user_id": "different-user-id"}]
                return eq_mock
            sel_mock.eq = eq_fn
            query_mock.select.return_value = sel_mock
        return query_mock

    mock_unauth_supabase = MagicMock()
    mock_unauth_supabase.table.side_effect = unauthorized_table

    container = mock_get_container()
    container.supabase_client = mock_unauth_supabase

    app.dependency_overrides[get_container] = lambda: container

    try:
        payload = {"user_message": "Hello", "session_id": "unauthorized-session", "messages": []}
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 403
        assert "Unauthorized" in response.json().get("detail", "")
    finally:
        app.dependency_overrides[get_container] = mock_get_container

