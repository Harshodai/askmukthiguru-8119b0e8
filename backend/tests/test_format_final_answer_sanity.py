"""L-OUTPUT-SANITY-1 through the real node: garbage / outage text never reports passed."""
import pytest

from rag.nodes.generation import format_final_answer


def _state(answer, **extra):
    base = {
        "question": "What is the Beautiful State?",
        "answer": answer,
        "intent": "FACTUAL",
        "query_tier": "standard",
        "relevant_docs": [{"text": "The Beautiful State is calm and joyful.", "source_url": "u", "title": "t"}],
        "citations": [],
        "is_faithful": True,
        "confidence_score": 9.0,
        "verification": {"passed": True, "method": "lettuce", "citations_verified": True},
        "detected_language": "en",
    }
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_exclamation_garbage_not_passed():
    out = await format_final_answer(_state("!" * 136))
    assert out["verification"]["passed"] is False
    assert out["verification"]["method"].startswith("output_sanity_gate")
    assert "!!!!" not in out["final_answer"]


@pytest.mark.asyncio
async def test_connection_issue_text_not_passed():
    msg = (
        "I'm here and listening. However, I'm experiencing a temporary connection issue "
        "with my backend services. Please try again shortly."
    )
    out = await format_final_answer(_state(msg))
    assert out["verification"]["passed"] is False
    assert out["grounding_state"] == "degraded"
    assert "try again" in out["final_answer"].lower() or "ask again" in out["final_answer"].lower()


@pytest.mark.asyncio
async def test_casual_handler_outage_text_gets_warm_fallback(monkeypatch):
    from rag.nodes import _services, intent

    class _Gw:
        async def generate(self, **kw):
            return "I'm here and listening. However, I'm experiencing a temporary connection issue."

    monkeypatch.setattr(_services, "_llm_gateway", _Gw(), raising=False)
    out = await intent.handle_casual({"question": "hello", "chat_history": []})
    assert "connection issue" not in out["final_answer"].lower()
    assert "Namaste" in out["final_answer"]
