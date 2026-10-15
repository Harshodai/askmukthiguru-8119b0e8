"""Reproduces the ground-truthed fabrication in docs/GURU_DEMO_READINESS.md §4E.1.

handle_distress() free-generates its own answer and returns straight to END,
bypassing format_final_answer — so `_unquote_unverifiable_spans` never ran on
this path. A question routed through the distress handler shipped a quotation
attributed to Sri Preethaji ("...waves passing through the ocean of
consciousness") that appears in neither the corpus nor the OKF bundle. See
`rag/nodes/intent.py::handle_distress`.
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
async def test_handle_distress_strips_fabricated_quote_not_in_context():
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
        "quotation marks around an unverifiable span must be stripped, "
        "same as the QUERY path's format_final_answer guard"
    )
    # The clip carries no stored transcript hash, so it fails the serve-time
    # integrity gate (services.first_person_pipeline._passes_integrity_gate,
    # added 9ab02892) and is omitted ENTIRELY — §4E.1's spans are absent from
    # both stores, so they must not reach the seeker even quote-stripped.
    # The verified-clip branch is pinned by the companion test below.
    assert "waves passing through the ocean" not in final_answer, (
        "an unverified clip must be dropped whole, not demoted"
    )


@pytest.mark.asyncio
async def test_handle_distress_serves_integrity_gated_clip_with_template():
    """HANDOFF 2026-10-14 safety-lane direction: MODERATE distress answers with
    the safety boundary PLUS a verified verbatim clip. A clip carrying a
    matching transcript_hash + allowlisted speaker passes the real serve-time
    gate (same fixture rule as test_distress_constitutional_guard.py's negative
    control) and reaches the seeker byte-for-byte; the test above pins the
    failing side of the same gate."""
    import hashlib

    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value=_FABRICATED_ANSWER)

    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    )
    serene_mock.get_response = MagicMock(return_value=get_distress_response())

    state = GraphState(
        question="How does Inner Truth help dissolve chronic anxiety and hidden resentments?",
        chat_history=[],
        relevant_docs=_DOCS,
        first_person_clip={
            "verbatim_text": _FABRICATED_ANSWER,
            "transcript_hash": hashlib.sha256(_FABRICATED_ANSWER.encode()).hexdigest(),
            "speaker": "Sri Preethaji",
        },
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
    assert "Here is a recorded teaching from Sri Preethaji:" in final_answer
    assert "waves passing through the ocean" in final_answer, (
        "a gate-passing clip must reach the seeker (demotion, not deletion)"
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
