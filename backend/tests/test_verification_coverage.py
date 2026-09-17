"""
Unit and regression tests for verification metadata coverage and pastoral claim filtering.
Ensures every terminal graph handler returns structured verification metadata
and that non-assertion pastoral guidance is not flagged as ungrounded claims.
"""

from unittest.mock import AsyncMock, patch

import pytest

from rag.nodes.generation import format_final_answer
from rag.nodes.intent import (
    handle_casual,
    handle_distress,
    handle_meditation,
)
from rag.nodes.short_circuit import (
    handle_fallback,
)
from services.lettuce_detect_service import _is_assertion, _split_claims


class TestTerminalVerificationCoverage:
    """Validate that all terminal nodes return a valid verification dictionary."""

    @pytest.mark.asyncio
    async def test_handle_casual_conversation_recall(self):
        state = {
            "question": "What did I just ask?",
            "intent": "CONVERSATION_RECALL",
            "chat_history": [{"role": "user", "content": "What is Ekam?"}],
        }
        res = await handle_casual(state)
        assert "verification" in res
        assert isinstance(res["verification"], dict)
        assert res["verification"]["passed"] is True
        assert res["verification"]["method"] == "conversation_recall_short_circuit"
        assert res["faithfulness_score"] == 1.0

    @pytest.mark.asyncio
    async def test_handle_casual_app_orientation(self):
        state = {
            "question": "What is this app?",
            "intent": "APP_ORIENTATION",
            "chat_history": [],
        }
        res = await handle_casual(state)
        assert "verification" in res
        assert res["verification"]["passed"] is True
        assert res["verification"]["method"] == "app_orientation_short_circuit"
        assert res["faithfulness_score"] == 1.0

    @pytest.mark.asyncio
    async def test_handle_casual_capability(self):
        state = {
            "question": "What do you remember about our conversation memory?",
            "chat_history": [],
        }
        res = await handle_casual(state)
        assert "verification" in res
        assert res["verification"]["passed"] is True
        assert res["verification"]["method"] == "capability_short_circuit"
        assert res["faithfulness_score"] == 1.0

    @pytest.mark.asyncio
    async def test_handle_casual_playful_edge(self):
        state = {
            "question": "Can practicing soul sync turn me into a golden statue?",
            "chat_history": [],
        }
        res = await handle_casual(state)
        assert "verification" in res
        assert res["verification"]["passed"] is True
        assert res["verification"]["method"] == "capability_short_circuit"

    @pytest.mark.asyncio
    async def test_handle_distress(self):
        state = {
            "question": "I am in deep suffering and despair today.",
            "chat_history": [],
            "relevant_docs": [
                {
                    "title": "Dissolving Suffering",
                    "content": "Suffering dissolves when there is mindful awareness of the inner state.",
                    "source_url": "https://youtube.com/watch?v=12345678901",
                }
            ],
        }
        with patch("rag.nodes.intent._services._ollama") as mock_ollama:
            mock_ollama.generate = AsyncMock(
                return_value="Beloved, suffering is a state of disconnection. Turn attention inward to the breath."
            )
            res = await handle_distress(state)
            assert "verification" in res
            assert res["verification"]["passed"] is True
            assert res["verification"]["method"] == "distress_safety_preemption"
            assert res["faithfulness_score"] == 1.0

    @pytest.mark.asyncio
    async def test_handle_meditation_start(self):
        state = {
            "question": "Guide me through Soul Sync practice",
            "meditation_step": 0,
        }
        res = await handle_meditation(state)
        assert "verification" in res
        assert res["verification"]["passed"] is True
        assert res["verification"]["method"] == "meditation_short_circuit"

    @pytest.mark.asyncio
    async def test_handle_meditation_step_advance(self):
        state = {
            "question": "next",
            "meditation_step": 1,
        }
        res = await handle_meditation(state)
        assert "verification" in res
        assert res["verification"]["passed"] is True
        assert res["verification"]["method"] == "meditation_short_circuit"
        assert res["meditation_step"] == 2

    @pytest.mark.asyncio
    async def test_handle_fallback_no_context(self):
        state = {
            "question": "Some completely unheard of esoteric query",
            "documents": [],
            "reranked_docs": [],
            "relevant_docs": [],
        }
        res = await handle_fallback(state)
        assert "verification" in res
        assert res["verification"]["passed"] is False
        assert res["verification"]["method"] == "no_context_short_circuit"
        assert res["faithfulness_score"] == 0.0

    @pytest.mark.asyncio
    async def test_handle_fallback_comparison(self):
        state = {
            "question": "What is the difference between meditation and contemplation?",
            "documents": [],
            "reranked_docs": [],
            "relevant_docs": [],
        }
        res = await handle_fallback(state)
        assert "verification" in res
        assert res["verification"]["passed"] is False
        assert res["verification"]["method"] == "limited_comparison_fallback"
        assert res["faithfulness_score"] == 0.0

    @pytest.mark.asyncio
    async def test_format_final_answer_has_verification(self):
        state = {
            "question": "What is Ekam?",
            "answer": "Ekam is a sacred sanctuary of consciousness in Southern India.",
            "relevant_docs": [{"title": "Ekam Tour", "source_url": "https://ekam.org"}],
            "verified": True,
            "is_faithful": True,
            "citations": [{"title": "Ekam Tour", "url": "https://ekam.org"}],
            "confidence_score": 9.5,
            "faithfulness_score": 1.0,
            "verification": {
                "passed": True,
                "method": "local_nli_entailment",
                "citations_verified": True,
            },
        }
        res = await format_final_answer(state)
        assert "verification" in res
        assert res["verification"]["passed"] is True
        assert res["verification"]["method"] == "local_nli_entailment"


class TestPastoralNonAssertionFiltering:
    """Validate that pastoral invitations and reflective guidance are filtered from factual claims."""

    def test_pastoral_imperatives_not_assertions(self):
        assert _is_assertion("Reflect on this deeply.") is False
        assert _is_assertion("🙏 Reflect on this deeply.") is False
        assert _is_assertion("Dear one, take a deep breath and observe your thoughts.") is False
        assert _is_assertion("Take a moment to sit quietly.") is False
        assert _is_assertion("Pause and notice the breath moving through you.") is False
        assert _is_assertion("May you experience deep peace and stillness.") is False
        assert _is_assertion("Close your eyes and bring your attention to your heart.") is False
        assert _is_assertion("Gently rest in this awareness.") is False

    def test_factual_doctrinal_statements_are_assertions(self):
        assert _is_assertion("The First Sacred Secret is to live with a spiritual vision.") is True
        assert _is_assertion("Soul Sync consists of six distinct meditation stages.") is True
        assert _is_assertion("Deeksha activates the frontal lobes of the brain.") is True
        assert _is_assertion("Ekam is located in Varadaiahpalem, Andhra Pradesh.") is True

    def test_split_claims_preserves_assertions_filters_pastoral(self):
        text = (
            "The First Sacred Secret is to live with a spiritual vision. "
            "When you live with spiritual vision, your inner state determines outer reality. "
            "🙏 Reflect on this deeply. "
            "Dear one, take a deep breath and sit with this truth."
        )
        claims = _split_claims(text)
        assert len(claims) == 2
        assert "The First Sacred Secret is to live with a spiritual vision." in claims[0]
        assert "When you live with spiritual vision" in claims[1]
