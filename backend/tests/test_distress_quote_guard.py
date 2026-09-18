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
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", serene_mock),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert final_answer, "final_answer must not be empty"
    assert '"' not in final_answer, (
        "quotation marks around an unverifiable span must be stripped, "
        "same as the QUERY path's format_final_answer guard"
    )
    # Demotion, not deletion: the grounded prose still reaches the seeker.
    assert "waves passing through the ocean" in final_answer


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
