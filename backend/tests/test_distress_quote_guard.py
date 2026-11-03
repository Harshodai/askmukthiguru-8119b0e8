"""Regressions for distress evidence and the no-generation boundary.

Only a successful/weak-match first-person result or bridge result from the normal
gated pipeline may add teaching text below SEVERE. Raw ``first_person_clip``
state is ignored; the handler never probes a provider or availability service to
upgrade it. See ``rag/nodes/intent.py::handle_distress``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.meditation import get_distress_response
from rag.nodes.intent import handle_distress
from rag.states import GraphState
from services.serene_mind_engine import DistressAssessment, DistressLevel

_FABRICATED_ANSWER = (
    "Sri Preethaji teaches us that the mind often clings to suffering. "
    '"When you connect with your Inner Truth," Sri Preethaji says, '
    '"you step into the vastness of your being, where anxiety and resentment '
    "lose their grip. You realize that these emotions are not who you are"
    '—they are simply waves passing through the ocean of your consciousness."'
)

_DOCS = [
    {
        "title": "Suffering and the Mind",
        "text": (
            "The mind clings to past hurt and future fear. Observation dissolves "
            "the grip of the Suffering State."
        ),
    }
]


@pytest.mark.asyncio
async def test_handle_distress_ignores_unbound_raw_first_person_clip():
    """A raw clip-shaped field cannot inject unverifiable text into safety output."""
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value=_FABRICATED_ANSWER)

    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    )

    state = GraphState(
        question="How does Inner Truth help dissolve chronic anxiety and hidden resentments?",
        chat_history=[],
        relevant_docs=_DOCS,
        first_person_clip={"verbatim_text": _FABRICATED_ANSWER, "speaker": "Sri Preethaji"},
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
    assert final_answer, "final_answer must not be empty"
    assert '"' not in final_answer, (
        "the raw clip text must not be appended to the distress template"
    )
    # Raw state has no pipeline-gated evidence contract and is omitted entirely.
    assert "waves passing through the ocean" not in final_answer, (
        "raw first_person_clip state must be dropped whole, not demoted"
    )


@pytest.mark.asyncio
async def test_handle_distress_serves_gated_first_person_result_with_template():
    """A successful pipeline-gated source quote is appended byte-for-byte."""
    import hashlib

    from services.first_person_pipeline import FirstPersonPipelineResult

    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value="must not be generated")

    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    )
    serene_mock.get_response = MagicMock(return_value=get_distress_response())
    video_id = "dQw4w9WgXcQ"
    gated_quote = "Observe what is."
    quoted_verbatim_text = f'"{gated_quote}"'
    source_url = f"https://www.youtube.com/watch?v={video_id}&t=99s"
    gated_result = FirstPersonPipelineResult(
        answer_text=f"**Sri Preethaji**\n\n{quoted_verbatim_text}\n\n{source_url}",
        citations=[
            {
                "source_title": "Observation",
                "source_url": source_url,
                "video_id": video_id,
                "start_ms": 99_000,
                "end_ms": 100_000,
                "timestamp_seconds": 99,
                "speaker": "Sri Preethaji",
                "speaker_verified": True,
                "verbatim_text": quoted_verbatim_text,
                "transcript_hash": hashlib.sha256(quoted_verbatim_text.encode()).hexdigest(),
                "is_verbatim": True,
            }
        ],
        status="success",
        is_direct_answer=True,
        latency_ms=10.0,
        fp_served=True,
    )

    state = GraphState(
        question="How does Inner Truth help dissolve chronic anxiety and hidden resentments?",
        chat_history=[],
        relevant_docs=_DOCS,
        first_person_result=gated_result,
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
    assert quoted_verbatim_text in final_answer
    assert len(result.get("citations", [])) == 1
    assert result["citations"][0]["verbatim_text"] == quoted_verbatim_text
    assert result["citations"][0]["speaker_verified"] is True
    assert result["citations"][0]["source_url"] == source_url
    assert result["citations"][0]["video_id"] == video_id


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
