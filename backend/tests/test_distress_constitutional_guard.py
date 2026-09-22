"""R4/R5: handle_distress() short-circuits straight to END (graph_strategies.py),
bypassing reflect_on_answer/verify_answer -- so check_persona_adherence's
impersonation and "no diksha/absolution/blessing" checks (rag/nodes/verification.py)
never ran on the single highest-stakes path in the product, even though the prompt
built in handle_distress explicitly instructs the model to speak "as if the guru is
speaking directly." See rag/nodes/intent.py::handle_distress.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.meditation import get_distress_response
from rag.nodes.intent import handle_distress
from rag.states import GraphState
from services.serene_mind_engine import DistressAssessment, DistressLevel

_DOCS = [
    {
        "title": "Suffering and the Mind",
        "text": (
            "The mind clings to past hurt and future fear. Observation dissolves "
            "the grip of the Suffering State."
        ),
    }
]


async def _run_distress(question: str, fabricated_answer: str, level: DistressLevel):
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value=fabricated_answer)

    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=level, confidence=0.7)
    )
    serene_mock.get_response = MagicMock(return_value=get_distress_response())

    state = GraphState(question=question, chat_history=[], relevant_docs=_DOCS)

    with (
        patch("rag.nodes.intent._services._serene_mind", serene_mock),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        return await handle_distress(state, config={})


@pytest.mark.asyncio
async def test_handle_distress_catches_blessing_claim_and_substitutes_safe_fallback():
    """A blessing/diksha claim reaching a person in distress is the exact failure
    mode R4 exists to close -- the model free-generates guru-voice prose here and
    nothing downstream (format_final_answer, reflect_on_answer) ever re-checks it."""
    fabricated = (
        "I hear the weight you are carrying. Receive this deeksha through these "
        "words: you are absolved of this suffering, and I bless you on this path."
    )
    result = await _run_distress(
        "I can't stop crying and I don't know what to do with this pain",
        fabricated,
        DistressLevel.MODERATE,
    )

    final_answer = result.get("final_answer", "")
    assert final_answer, "final_answer must not be empty"
    assert "deeksha" not in final_answer.lower()
    assert "absolved" not in final_answer.lower()
    assert "i bless you" not in final_answer.lower()
    # Must still be a caring, non-empty response with helpline contacts, not a
    # bare rejection -- see mission constraint #3.
    assert "serene mind" in final_answer.lower() or "meditation" in final_answer.lower()


@pytest.mark.asyncio
async def test_handle_distress_severe_still_carries_helplines_after_substitution():
    """SEVERE-tier crisis_info is prepended to the draft before the guard runs;
    a caught violation discards that draft wholesale, so the fallback template
    (which always embeds helplines) must be the thing that ships -- not a
    response silently missing crisis contacts."""
    fabricated = "As Sri Preethaji, I now confer upon you initiation into peace."
    result = await _run_distress(
        "I don't want to be here anymore, I want to end my life",
        fabricated,
        DistressLevel.SEVERE,
    )

    final_answer = result.get("final_answer", "")
    assert "sri preethaji, i" not in final_answer.lower()
    assert final_answer, "final_answer must not be empty"
    # get_distress_response() always renders a helpline block regardless of style.
    assert any(marker in final_answer for marker in ("iCall", "988", "helpline", "Helpline"))


@pytest.mark.asyncio
async def test_handle_distress_clean_answer_is_untouched():
    """Negative control: a clean, grounded answer must not be discarded."""
    clean = (
        "The teachings remind us that suffering is a doorway to transformation. "
        "Sri Preethaji often speaks about observing thought without fighting it."
    )
    result = await _run_distress(
        "Why do I keep suffering the same way over and over?",
        clean,
        DistressLevel.MILD,
    )

    final_answer = result.get("final_answer", "")
    assert "suffering is a doorway to transformation" in final_answer


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
