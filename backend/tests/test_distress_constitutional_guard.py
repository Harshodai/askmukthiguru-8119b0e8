"""R4: distress short-circuits straight to END, so its persona guard must run
over both the clinician-reviewed template and any teaching from the normal gated
first-person pipeline. Raw clip state is not a trusted teaching result. See
``rag/nodes/intent.py::handle_distress``.
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


def _gated_first_person_result(verbatim_text: str):
    """Construct a synthetic success result with source-matched citation fields."""
    import hashlib

    from services.first_person_pipeline import FirstPersonPipelineResult

    video_id = "dQw4w9WgXcQ"
    source_url = f"https://www.youtube.com/watch?v={video_id}&t=99s"
    return FirstPersonPipelineResult(
        answer_text=f"**Sri Preethaji**\n\n{verbatim_text}\n\n{source_url}",
        citations=[
            {
                "source_title": "Test source clip",
                "source_url": source_url,
                "video_id": video_id,
                "start_ms": 99_000,
                "end_ms": 100_000,
                "timestamp_seconds": 99,
                "speaker": "Sri Preethaji",
                "speaker_verified": True,
                "verbatim_text": verbatim_text,
                "transcript_hash": hashlib.sha256(verbatim_text.encode()).hexdigest(),
                "is_verbatim": True,
            }
        ],
        status="success",
        is_direct_answer=True,
        latency_ms=10.0,
        fp_served=True,
    )


async def _run_distress(
    question: str,
    candidate_text: str,
    level: DistressLevel,
    *,
    include_gated_result: bool = True,
):
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value=candidate_text)

    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=level, confidence=0.7)
    )
    serene_mock.get_response = MagicMock(return_value=get_distress_response())

    state_values = {
        "question": question,
        "chat_history": [],
        "relevant_docs": _DOCS,
    }
    if include_gated_result:
        state_values["first_person_result"] = _gated_first_person_result(candidate_text)
    state = GraphState(
        **state_values,
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", serene_mock),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})
        assert mock_ollama.generate.call_count == 0, (
            "LLM generate must never be called on distress path"
        )
        return result


@pytest.mark.asyncio
async def test_handle_distress_catches_blessing_claim_and_substitutes_safe_fallback():
    """A blessing/diksha claim in a gated teaching still triggers the persona guard."""
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
async def test_handle_distress_severe_template_still_carries_helplines_without_teaching():
    """SEVERE distress remains template-only and carries the required helplines."""
    fabricated = "As Sri Preethaji, I now confer upon you initiation into peace."
    result = await _run_distress(
        "I don't want to be here anymore, I want to end my life",
        fabricated,
        DistressLevel.SEVERE,
        include_gated_result=False,
    )

    final_answer = result.get("final_answer", "")
    assert "sri preethaji, i" not in final_answer.lower()
    assert fabricated not in final_answer
    assert result.get("citations") == []
    assert final_answer, "final_answer must not be empty"
    # get_distress_response() always renders a helpline block regardless of style.
    assert any(marker in final_answer for marker in ("iCall", "988", "helpline", "Helpline"))


@pytest.mark.asyncio
async def test_handle_distress_clean_answer_is_untouched():
    """Negative control: a clean, grounded, VERIFIABLE answer must not be discarded.

    The handler receives only a successful result from the normal first-person
    pipeline; the matching source citation represents the gates already passed.
    """
    clean = (
        "The teachings remind us that suffering is a doorway to transformation. "
        "Sri Preethaji often speaks about observing thought without fighting it."
    )
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value=clean)
    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MILD, confidence=0.7)
    )
    serene_mock.get_response = MagicMock(return_value=get_distress_response())
    state = GraphState(
        question="Why do I keep suffering the same way over and over?",
        chat_history=[],
        relevant_docs=_DOCS,
        first_person_result=_gated_first_person_result(clean),
    )
    with (
        patch("rag.nodes.intent._services._serene_mind", serene_mock),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})
        assert mock_ollama.generate.call_count == 0, (
            "LLM generate must never be called on distress path"
        )

    final_answer = result.get("final_answer", "")
    assert "suffering is a doorway to transformation" in final_answer


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
