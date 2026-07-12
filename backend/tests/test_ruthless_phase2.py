import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.feedback import router
from app.constants import FEEDBACK_LESSONS_FILE_PATH
from rag.nodes.generation import classify_user_familiarity, context_engineer
from rag.states import GraphState


def test_classify_user_familiarity():
    # Seeker (default)
    assert classify_user_familiarity("hello, how are you?", []) == "Seeker"
    
    # Practitioner
    assert classify_user_familiarity("I want a meditation instruction", []) == "Practitioner"
    
    # Advanced Meditator
    assert classify_user_familiarity("tell me about deeksha", []) == "Advanced Meditator"


@pytest.mark.asyncio
async def test_context_engineer_cost_steering():
    # Long history (4 turns = 8 messages)
    chat_history = [{"role": "user", "content": "hi"}] * 8
    
    state = GraphState(
        question="Can you help me?",
        chat_history=chat_history,
        intent="FACTUAL",
        relevant_docs=[],
        meditation_step=0,
        detected_language="en",
        memory_context="",
        assistant_system_prompt=None,
    )
    
    # Run context_engineer
    result = await context_engineer(state)
    
    assert "query_tier" in result
    assert result["query_tier"] == "tier2_simple"
    assert "COST STEERING" in result["context_layers"]["instructions"]


@pytest.mark.asyncio
async def test_feedback_lessons_mining():
    # Ensure lessons file is cleaned first
    if os.path.exists(FEEDBACK_LESSONS_FILE_PATH):
        try:
            os.remove(FEEDBACK_LESSONS_FILE_PATH)
        except Exception:
            pass

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    from services.auth_service import get_current_user_from_supabase
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {"id": "user123", "is_superuser": True}

    # Mock get_container
    mock_container = MagicMock()
    mock_container.ollama = AsyncMock()
    mock_container.ollama.generate.return_value = '{"category": "hallucination", "analysis": "Refined correctly", "suggested_correction": "Add rule"}'

    # Mock container in refiner background task
    with patch("app.core.refiner.get_container", return_value=mock_container):
        # Post negative feedback (rating <= 0)
        response = client.post(
            "/feedback/",
            json={
                "query": "Who is PK?",
                "answer": "PK is a robot.",
                "rating": -1,
                "feedback_text": "Wrong answer",
                "metadata_json": {"chunks": "Mock context"},
            }
        )
        assert response.status_code == 200

        # Retrieve feedback-lessons
        response_lessons = client.get("/feedback/feedback-lessons")
        assert response_lessons.status_code == 200
        lessons = response_lessons.json()
        assert len(lessons) >= 1
        assert lessons[0]["query"] == "Who is PK?"
        assert lessons[0]["category"] == "hallucination"
        assert lessons[0]["suggested_correction"] == "Add rule"

    # Clean up lessons file
    if os.path.exists(FEEDBACK_LESSONS_FILE_PATH):
        try:
            os.remove(FEEDBACK_LESSONS_FILE_PATH)
        except Exception:
            pass
